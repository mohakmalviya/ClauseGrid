"""Safe OpenAI-compatible chat client with provider-neutral normalized results."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol, Self
from urllib.parse import urlsplit

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from .agent_types import (
    AssistantMessage,
    ModelRequest,
    ModelRequestSettings,
    ModelTurn,
    ModelUsage,
    NamedToolChoice,
    SystemMessage,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)


class ModelConfigurationError(ValueError):
    """The client cannot start because non-secret configuration is invalid or absent."""


class ModelClientError(RuntimeError):
    """Base class for safe errors emitted by the model boundary."""

    def __init__(self, message: str, *, status_code: int | None, retry_count: int):
        super().__init__(message)
        self.status_code = status_code
        self.retry_count = retry_count


class FatalModelError(ModelClientError):
    """A request failed in a way that must not be retried."""


class TransientModelError(ModelClientError):
    """A request exhausted its bounded retry allowance."""


class ModelProtocolError(ModelClientError):
    """The provider returned an unusable chat-completion shape."""


class OpenAICompatibleConfig(BaseModel):
    """Connection settings whose secret value is excluded from repr and serialization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key: SecretStr = Field(repr=False)
    timeout_seconds: float = Field(default=120.0, gt=0.0, le=600.0)
    min_request_interval_seconds: float = Field(default=0.0, ge=0.0, le=60.0)

    @field_validator("base_url")
    @classmethod
    def require_secure_endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Model base URL must be a plain absolute service endpoint")
        loopback = parsed.hostname.casefold() in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            raise ValueError("Model base URL requires HTTPS except for loopback development")
        return value.rstrip("/")

    @classmethod
    def from_env(
        cls,
        *,
        base_url: str,
        model: str,
        api_key_env: str = "NVIDIA_NIM_API_KEY",
        timeout_seconds: float = 120.0,
        min_request_interval_seconds: float = 0.0,
    ) -> OpenAICompatibleConfig:
        """Load a credential from process environment without reading or writing dotenv files."""

        value = os.environ.get(api_key_env)
        if value is None or not value.strip():
            raise ModelConfigurationError(
                f"Required credential environment variable is unset: {api_key_env}"
            )
        return cls(
            base_url=base_url,
            model=model,
            api_key=SecretStr(value.strip()),
            timeout_seconds=timeout_seconds,
            min_request_interval_seconds=min_request_interval_seconds,
        )


class RetryPolicy(BaseModel):
    """Deterministic bounded retry policy; max_attempts includes the first request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_attempts: int = Field(default=3, ge=1, le=6)
    base_delay_seconds: float = Field(default=0.5, ge=0.0, le=30.0)
    max_delay_seconds: float = Field(default=8.0, ge=0.0, le=120.0)


class ModelTransport(Protocol):
    """Injectable provider transport used by the normalized model client."""

    def create_chat_completion(self, payload: Mapping[str, Any]) -> Any:
        """Return one OpenAI-compatible chat completion or raise a provider error."""


class OpenAITransport:
    """Official OpenAI Python client configured for an OpenAI-compatible endpoint."""

    def __init__(self, config: OpenAICompatibleConfig, *, client: Any | None = None):
        self._client = client or OpenAI(
            api_key=config.api_key.get_secret_value(),
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=0,
        )

    def create_chat_completion(self, payload: Mapping[str, Any]) -> Any:
        return self._client.chat.completions.create(**dict(payload))

    def close(self) -> None:
        self._client.close()


class ModelClient:
    """Normalize chat completions while enforcing explicit retry and error semantics."""

    def __init__(
        self,
        config: OpenAICompatibleConfig,
        *,
        transport: ModelTransport | None = None,
        retry_policy: RetryPolicy | None = None,
        request_settings: ModelRequestSettings | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.perf_counter,
    ):
        self.config = config
        self._transport = transport or OpenAITransport(config)
        self._retry_policy = retry_policy or RetryPolicy()
        self.request_settings = request_settings or ModelRequestSettings()
        self._sleeper = sleeper
        self._clock = clock
        self._last_request_started: float | None = None
        self._closed = False

    def __enter__(self) -> Self:
        if self._closed:
            raise RuntimeError("Model client is closed")
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Release an owned provider transport exactly once when it supports closing."""

        if self._closed:
            return
        self._closed = True
        close = getattr(self._transport, "close", None)
        if callable(close):
            close()

    def complete(self, request: ModelRequest) -> ModelTurn:
        """Execute one bounded model request and return a provider-neutral response."""

        if self._closed:
            raise RuntimeError("Model client is closed")
        payload = _request_payload(self.config.model, request)
        start = self._clock()
        max_attempts = min(self._retry_policy.max_attempts, request.attempt_limit)
        protocol_retry_usage: list[ModelUsage] = []
        for attempt in range(max_attempts):
            self._pace_request()
            try:
                raw_response = self._transport.create_chat_completion(payload)
            except Exception as exc:  # noqa: BLE001 - provider SDKs have unrelated hierarchies
                status_code = _status_code(exc)
                retry_count = attempt
                safe_message = _safe_exception_text(
                    exc,
                    secret=self.config.api_key.get_secret_value(),
                )
                if not _is_retryable(exc, status_code):
                    raise FatalModelError(
                        f"Model request failed: {safe_message}",
                        status_code=status_code,
                        retry_count=retry_count,
                    ) from None
                if attempt + 1 >= max_attempts:
                    raise TransientModelError(
                        f"Model request exhausted retries: {safe_message}",
                        status_code=status_code,
                        retry_count=retry_count,
                    ) from None
                self._sleeper(self._retry_delay(exc, attempt))
                continue

            elapsed_ms = max(0, round((self._clock() - start) * 1000))
            if _response_has_no_observable_output(raw_response):
                usage = _response_usage(raw_response)
                if attempt + 1 >= max_attempts:
                    raise TransientModelError(
                        "Model request exhausted retries: provider repeatedly returned no "
                        "observable output",
                        status_code=503,
                        retry_count=attempt,
                    )
                protocol_retry_usage.append(usage)
                payload = _protocol_repair_payload(payload, previous_content=None)
                continue
            turn = _normalize_response(
                raw_response,
                configured_model=self.config.model,
                elapsed_ms=elapsed_ms,
                retry_count=attempt,
            )
            turn = _serialize_tool_calls(request, turn)
            try:
                _validate_response_contract(request, turn)
            except ModelProtocolError as exc:
                repair_instruction = _protocol_repair_instruction(request, turn)
                if repair_instruction is None:
                    raise
                if attempt + 1 >= max_attempts:
                    raise ModelProtocolError(
                        str(exc),
                        status_code=exc.status_code,
                        retry_count=attempt,
                    ) from None
                protocol_retry_usage.append(turn.usage)
                payload = _protocol_repair_payload(
                    payload,
                    instruction=repair_instruction,
                    previous_content=turn.content,
                )
                continue
            if protocol_retry_usage:
                turn = turn.model_copy(
                    update={"usage": _combined_usage([*protocol_retry_usage, turn.usage])}
                )
            return turn
        raise AssertionError("Retry loop ended without returning or raising")

    def _pace_request(self) -> None:
        interval = self.config.min_request_interval_seconds
        now = self._clock()
        if self._last_request_started is not None:
            remaining = interval - (now - self._last_request_started)
            if remaining > 0:
                self._sleeper(remaining)
                now = self._clock()
        self._last_request_started = now

    def _retry_delay(self, exc: Exception, attempt: int) -> float:
        retry_after = _retry_after_seconds(exc)
        if retry_after is None:
            retry_after = self._retry_policy.base_delay_seconds * (2**attempt)
        return min(retry_after, self._retry_policy.max_delay_seconds)


def _validate_response_contract(request: ModelRequest, turn: ModelTurn) -> None:
    """Enforce tool-choice guarantees even when a compatible endpoint ignores them."""

    calls = turn.tool_calls
    if request.tool_choice == "required" and not calls:
        raise ModelProtocolError(
            "Provider did not return a required tool call",
            status_code=None,
            retry_count=turn.retry_count,
        )
    if request.tool_choice == "none" and calls:
        raise ModelProtocolError(
            "Provider returned a tool call when tool use was disabled",
            status_code=None,
            retry_count=turn.retry_count,
        )
    if isinstance(request.tool_choice, NamedToolChoice) and (
        len(calls) != 1 or calls[0].name != request.tool_choice.name
    ):
        raise ModelProtocolError(
            f"Provider did not honor named tool choice: {request.tool_choice.name}",
            status_code=None,
            retry_count=turn.retry_count,
        )
    declared = {tool.name for tool in request.tools}
    undeclared = sorted({call.name for call in calls if call.name not in declared})
    if undeclared:
        raise ModelProtocolError(
            f"Provider returned undeclared tool calls: {', '.join(undeclared)}",
            status_code=None,
            retry_count=turn.retry_count,
        )


def _serialize_tool_calls(request: ModelRequest, turn: ModelTurn) -> ModelTurn:
    """Enforce serial orchestration locally when a compatible provider ignores the flag."""

    if request.parallel_tool_calls or request.tool_choice == "none" or len(turn.tool_calls) <= 1:
        return turn
    selected_index = 0
    if isinstance(request.tool_choice, NamedToolChoice):
        matching = [
            index
            for index, call in enumerate(turn.tool_calls)
            if call.name == request.tool_choice.name
        ]
        if matching:
            selected_index = matching[0]
    selected = turn.tool_calls[selected_index]
    discarded = tuple(call for index, call in enumerate(turn.tool_calls) if index != selected_index)
    return turn.model_copy(
        update={
            "tool_calls": (selected,),
            "discarded_tool_calls": discarded,
        }
    )


def _protocol_repair_instruction(request: ModelRequest, turn: ModelTurn) -> str | None:
    """Return a bounded correction for protocol drift that can be retried safely."""

    declared = {tool.name for tool in request.tools}
    undeclared = sorted({call.name for call in turn.tool_calls if call.name not in declared})
    if undeclared and request.tool_choice != "none":
        available = ", ".join(sorted(declared))
        attempted = ", ".join(undeclared)
        return (
            f"Your previous response called unavailable function(s): {attempted}. "
            f"The functions available on this turn are only: {available}. Call exactly one "
            "currently available function with a valid JSON argument object. Do not call a "
            "function merely because it appeared earlier in the conversation."
        )

    requires_tool = request.tool_choice == "required" or isinstance(
        request.tool_choice, NamedToolChoice
    )
    if not (requires_tool and not turn.tool_calls and bool(turn.content)):
        return None
    if isinstance(request.tool_choice, NamedToolChoice):
        return (
            "Your previous response did not contain the required function call. "
            f"Call {request.tool_choice.name} now with a valid JSON argument object. "
            "Do not answer with plain text."
        )
    names = ", ".join(tool.name for tool in request.tools)
    return (
        "Your previous response did not contain a required function call. Call exactly one "
        f"available function now ({names}) with a valid JSON argument object. Do not answer "
        "with plain text."
    )


def _protocol_repair_payload(
    payload: Mapping[str, Any],
    *,
    instruction: str | None = None,
    previous_content: str | None,
) -> dict[str, Any]:
    """Continue the same conversation with an explicit observable protocol correction."""

    if instruction is None:
        instruction = (
            "Your previous response did not contain a required function call. Return exactly one "
            "observable function call now. Do not answer with plain text."
        )
    messages = list(payload.get("messages", []))
    if previous_content:
        messages.append({"role": "assistant", "content": previous_content})
    messages.append({"role": "user", "content": instruction})
    return {**dict(payload), "messages": messages}


def _combined_usage(items: list[ModelUsage]) -> ModelUsage:
    costs = [item.reported_cost_usd for item in items if item.reported_cost_usd is not None]
    return ModelUsage(
        input_tokens=sum(item.input_tokens for item in items),
        output_tokens=sum(item.output_tokens for item in items),
        total_tokens=sum(item.total_tokens for item in items),
        cached_input_tokens=sum(item.cached_input_tokens for item in items),
        reported_cost_usd=(sum(costs) if costs else None),
    )


def _response_has_no_observable_output(response: Any) -> bool:
    """Recognize a well-shaped completion whose first choice contains no text or tool call."""

    try:
        choices = _member(response, "choices")
        if not isinstance(choices, (list, tuple)):
            return False
        if not choices:
            return True
        message = _member(choices[0], "message")
        content = _member(message, "content", default=None)
        calls = _member(message, "tool_calls", default=None)
        return not content and not calls
    except (TypeError, ValueError):
        return False


def _response_usage(response: Any) -> ModelUsage:
    return _normalize_usage(
        _member(response, "usage", default=None),
        reported_cost_usd=_member(response, "reported_cost_usd", default=None),
    )


def _request_payload(model: str, request: ModelRequest) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    for message in request.messages:
        if isinstance(message, (SystemMessage, UserMessage)):
            messages.append({"role": message.role, "content": message.content})
        elif isinstance(message, AssistantMessage):
            assistant: dict[str, Any] = {"role": "assistant", "content": message.content}
            if message.tool_calls:
                assistant["tool_calls"] = [
                    {
                        "id": call.call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(
                                call.arguments,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        },
                    }
                    for call in message.tool_calls
                ]
            messages.append(assistant)
        elif isinstance(message, ToolResultMessage):
            tool_result: dict[str, Any] = {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "content": message.content,
            }
            if message.name is not None:
                tool_result["name"] = message.name
            messages.append(tool_result)
        else:  # pragma: no cover - discriminated Pydantic union prevents this branch
            raise TypeError(f"Unsupported chat message: {type(message).__name__}")

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
    }
    if request.top_p is not None:
        payload["top_p"] = request.top_p
    if request.extra_body:
        payload["extra_body"] = request.extra_body
    if request.seed is not None:
        payload["seed"] = request.seed
    if request.tools:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in request.tools
        ]
        if isinstance(request.tool_choice, NamedToolChoice):
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": request.tool_choice.name},
            }
        else:
            payload["tool_choice"] = request.tool_choice
        payload["parallel_tool_calls"] = request.parallel_tool_calls
    elif request.tool_choice == "none":
        payload["tool_choice"] = "none"
    return payload


def _normalize_response(
    response: Any,
    *,
    configured_model: str,
    elapsed_ms: int,
    retry_count: int,
) -> ModelTurn:
    try:
        choices = _member(response, "choices")
        if not isinstance(choices, (list, tuple)) or not choices:
            raise ValueError("response has no choices")
        choice = choices[0]
        message = _member(choice, "message")
        content = _member(message, "content", default=None)
        if content is not None and not isinstance(content, str):
            raise ValueError("message content is not text")
        calls = _normalize_tool_calls(_member(message, "tool_calls", default=None))
        finish_reason_raw = _member(choice, "finish_reason", default=None)
        finish_reason = None if finish_reason_raw is None else str(finish_reason_raw)
        usage = _normalize_usage(
            _member(response, "usage", default=None),
            reported_cost_usd=_member(response, "reported_cost_usd", default=None),
        )
        model_raw = _member(response, "model", default=configured_model)
        response_id_raw = _member(response, "id", default=None)
        request_id_raw = _member(response, "_request_id", default=None)
        if request_id_raw is None:
            request_id_raw = _member(response, "request_id", default=None)
        return ModelTurn(
            response_id=None if response_id_raw is None else str(response_id_raw),
            request_id=None if request_id_raw is None else str(request_id_raw),
            model=str(model_raw),
            content=content,
            tool_calls=calls,
            finish_reason=finish_reason,
            usage=usage,
            elapsed_ms=elapsed_ms,
            retry_count=retry_count,
        )
    except ModelClientError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize all malformed provider objects
        raise ModelProtocolError(
            f"Provider returned an invalid chat completion: {exc}",
            status_code=None,
            retry_count=retry_count,
        ) from None


def _normalize_tool_calls(raw_calls: Any) -> tuple[ToolCall, ...]:
    if raw_calls is None:
        return ()
    if not isinstance(raw_calls, (list, tuple)):
        raise TypeError("message tool_calls is not a list")
    normalized: list[ToolCall] = []
    seen_ids: set[str] = set()
    for raw_call in raw_calls:
        call_type = _member(raw_call, "type", default="function")
        if call_type != "function":
            raise ValueError(f"unsupported tool call type: {call_type}")
        call_id = str(_member(raw_call, "id"))
        function = _member(raw_call, "function")
        name = str(_member(function, "name"))
        raw_arguments = _member(function, "arguments")
        if isinstance(raw_arguments, str):
            arguments = json.loads(raw_arguments)
        else:
            arguments = raw_arguments
        if not isinstance(arguments, dict):
            raise TypeError(f"tool arguments for {name} are not a JSON object")
        if call_id in seen_ids:
            raise ValueError(f"duplicate tool call identifier: {call_id}")
        seen_ids.add(call_id)
        normalized.append(ToolCall(call_id=call_id, name=name, arguments=arguments))
    return tuple(normalized)


def _normalize_usage(raw_usage: Any, *, reported_cost_usd: Any = None) -> ModelUsage:
    if raw_usage is None:
        return ModelUsage(reported_cost_usd=_normalized_reported_cost(reported_cost_usd))
    input_tokens = int(
        _member(raw_usage, "prompt_tokens", default=_member(raw_usage, "input_tokens", default=0))
        or 0
    )
    output_tokens = int(
        _member(
            raw_usage,
            "completion_tokens",
            default=_member(raw_usage, "output_tokens", default=0),
        )
        or 0
    )
    total_tokens_raw = _member(raw_usage, "total_tokens", default=None)
    total_tokens = (
        input_tokens + output_tokens if total_tokens_raw is None else int(total_tokens_raw)
    )
    details = _member(raw_usage, "prompt_tokens_details", default=None)
    cached_tokens = 0 if details is None else int(_member(details, "cached_tokens", default=0) or 0)
    return ModelUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_tokens,
        reported_cost_usd=_normalized_reported_cost(reported_cost_usd),
    )


def _normalized_reported_cost(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("reported model cost is not numeric")
    return float(value)


_MISSING = object()


def _member(value: Any, name: str, *, default: Any = _MISSING) -> Any:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
    elif hasattr(value, name):
        return getattr(value, name)
    if default is _MISSING:
        raise ValueError(f"missing field: {name}")
    return default


def _status_code(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None)
    if value is None:
        response = getattr(exc, "response", None)
        value = None if response is None else getattr(response, "status_code", None)
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _is_retryable(exc: Exception, status_code: int | None) -> bool:
    if status_code is not None:
        return status_code in {408, 429} or status_code >= 500
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    return type(exc).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "ConnectError",
        "ConnectTimeout",
        "ReadError",
        "ReadTimeout",
    }


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        headers = getattr(exc, "headers", None)
    if headers is None or not hasattr(headers, "get"):
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            when = parsedate_to_datetime(str(value))
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            return max(0.0, (when - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _safe_exception_text(exc: Exception, *, secret: str) -> str:
    text = str(exc) or type(exc).__name__
    if secret:
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)((?:api[-_ ]?key|token)\s*[:=]\s*)[^\s,;]+",
        r"\1[REDACTED]",
        text,
    )
    return text[:2000]
