"""Hardened native-alpha transport for CommandCode Go pool models.

FormulaWitness owns orchestration, tools, budgets, and approval. This module only
translates the provider-neutral chat protocol to CommandCode's ``/alpha/generate``
contract. It never invokes the filesystem-capable CommandCode coding harness.
"""

from __future__ import annotations

import json
import os
import platform
import re
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, Self, cast
from urllib.parse import urlsplit

import httpx

from .model_client import OpenAICompatibleConfig

COMMAND_CODE_GO_MODELS = frozenset(
    {
        "deepseek/deepseek-v4-pro",
        "xiaomi/mimo-v2.5-pro",
        "xiaomi/mimo-v2.5",
        "Qwen/Qwen3.7-Max",
        "MiniMaxAI/MiniMax-M3",
    }
)

COMMAND_CODE_ALPHA_PATH = "/alpha/generate"
COMMAND_CODE_CLI_VERSION = "0.32.2"
COMMAND_CODE_OFFICIAL_HOST = "api.commandcode.ai"

DEFAULT_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_LINE_BYTES = 1024 * 1024
DEFAULT_MAX_EVENT_COUNT = 20_000


class CommandCodeNativeError(RuntimeError):
    """Safe provider error carrying retry-classification metadata."""

    def __init__(self, message: str, *, status_code: int | None):
        super().__init__(message)
        self.status_code = status_code


class CommandCodeFatalError(CommandCodeNativeError):
    """A request or native response is invalid and must not be retried."""


class CommandCodeTransientError(CommandCodeNativeError):
    """A temporary native-provider or stream failure may be retried."""


class StreamResponse(Protocol):
    status_code: int
    headers: Mapping[str, str]

    def iter_bytes(self, chunk_size: int | None = None) -> Iterator[bytes]:
        """Yield response bytes incrementally without buffering the whole response."""


class HttpClient(Protocol):
    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, Any],
    ) -> AbstractContextManager[StreamResponse]:
        """Open one streaming HTTP request."""

    def close(self) -> None:
        """Release sockets and connection-pool resources."""


class CommandCodeGoTransport:
    """Translate FormulaWitness turns to the bounded CommandCode alpha protocol.

    A client injected through ``client=`` is owned by this transport and is closed by
    :meth:`close`, matching the lifecycle of the default ``httpx.Client``.
    """

    def __init__(
        self,
        config: OpenAICompatibleConfig,
        *,
        client: HttpClient | None = None,
        cli_version: str | None = None,
        allow_localhost: bool = False,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
        max_event_count: int = DEFAULT_MAX_EVENT_COUNT,
        stream_deadline_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        if config.model not in COMMAND_CODE_GO_MODELS:
            raise ValueError(f"Model is not in the CommandCode Go pool: {config.model}")
        _validate_base_url(config.base_url, allow_localhost=allow_localhost)
        if max_response_bytes <= 0 or max_line_bytes <= 0 or max_event_count <= 0:
            raise ValueError("CommandCode stream bounds must be positive")
        deadline = (
            config.timeout_seconds if stream_deadline_seconds is None else stream_deadline_seconds
        )
        if deadline <= 0:
            raise ValueError("CommandCode stream deadline must be positive")

        self._config = config
        self._client = cast(
            HttpClient,
            client or httpx.Client(timeout=httpx.Timeout(config.timeout_seconds)),
        )
        self._cli_version = cli_version or os.environ.get(
            "COMMAND_CODE_CLI_VERSION", COMMAND_CODE_CLI_VERSION
        )
        self._max_response_bytes = max_response_bytes
        self._max_line_bytes = max_line_bytes
        self._max_event_count = max_event_count
        self._stream_deadline_seconds = deadline
        self._clock = clock
        self._closed = False

    def __enter__(self) -> Self:
        if self._closed:
            raise RuntimeError("CommandCode transport is closed")
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the owned HTTP client exactly once."""

        if self._closed:
            return
        self._closed = True
        self._client.close()

    def create_chat_completion(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("CommandCode transport is closed")
        if payload.get("model") != self._config.model:
            raise CommandCodeFatalError(
                "CommandCode request model does not match configured model",
                status_code=400,
            )
        session_id = str(uuid.uuid4())
        started = self._clock()
        accumulator = _CompletionAccumulator(
            model=str(payload.get("model") or self._config.model),
            response_id=session_id,
            max_response_bytes=self._max_response_bytes,
            max_line_bytes=self._max_line_bytes,
            max_event_count=self._max_event_count,
            deadline=self._stream_deadline_seconds,
            started=started,
            clock=self._clock,
        )
        try:
            with self._client.stream(
                "POST",
                f"{self._config.base_url.rstrip('/')}{COMMAND_CODE_ALPHA_PATH}",
                headers=self._headers(session_id),
                json=_alpha_body(payload, session_id),
            ) as response:
                _raise_for_http_status(response.status_code)
                accumulator.request_id = response.headers.get("x-request-id")
                for chunk in response.iter_bytes():
                    accumulator.consume_chunk(chunk)
                accumulator.finish_input()
                return accumulator.completion()
        except CommandCodeNativeError:
            raise
        except (httpx.TimeoutException, TimeoutError):
            raise CommandCodeTransientError(
                "CommandCode request timed out", status_code=408
            ) from None
        except (httpx.TransportError, ConnectionError, OSError):
            raise CommandCodeTransientError(
                "CommandCode transport was interrupted", status_code=503
            ) from None

    def _headers(self, session_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._config.api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "x-cli-environment": "production",
            "x-command-code-version": self._cli_version,
            "x-co-flag": "false",
            "x-project-slug": "formulawitness",
            "x-session-id": session_id,
            "x-taste-learning": "false",
        }


def _validate_base_url(base_url: str, *, allow_localhost: bool) -> None:
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError:
        raise ValueError("CommandCode base URL is invalid") from None
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("CommandCode base URL cannot contain credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("CommandCode base URL must not contain an API path")
    hostname = (parsed.hostname or "").lower()
    if hostname == COMMAND_CODE_OFFICIAL_HOST:
        if parsed.scheme != "https" or port not in {None, 443}:
            raise ValueError("Official CommandCode traffic requires HTTPS on port 443")
        return
    if allow_localhost and hostname in {"localhost", "127.0.0.1", "::1"}:
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Local CommandCode test URL must use HTTP or HTTPS")
        return
    raise ValueError("CommandCode base URL host is not allowed")


def _alpha_body(payload: Mapping[str, Any], session_id: str) -> dict[str, Any]:
    messages = payload.get("messages")
    if not isinstance(messages, Sequence) or isinstance(messages, str | bytes):
        raise TypeError("CommandCode messages must be a sequence")

    tool_names = _tool_name_by_id(messages)
    system_parts: list[str] = []
    alpha_messages: list[dict[str, Any]] = []
    for raw in messages:
        if not isinstance(raw, Mapping):
            raise TypeError("CommandCode message must be an object")
        role = raw.get("role")
        if role == "system":
            content = raw.get("content")
            if not isinstance(content, str):
                raise TypeError("CommandCode system content must be text")
            if content.strip():
                system_parts.append(content)
            continue
        converted = _alpha_message(raw, tool_names=tool_names)
        _append_alpha_message(alpha_messages, converted)

    max_tokens_raw = payload.get("max_tokens")
    if max_tokens_raw is None:
        max_tokens_raw = 4096
    if isinstance(max_tokens_raw, bool) or not isinstance(max_tokens_raw, int):
        raise TypeError("CommandCode max_tokens must be an integer")
    if max_tokens_raw <= 0:
        raise ValueError("CommandCode max_tokens must be positive")

    params: dict[str, Any] = {
        "stream": True,
        "messages": alpha_messages or [{"role": "user", "content": "Begin the audit."}],
        "max_tokens": max_tokens_raw,
        "model": str(payload.get("model") or ""),
    }
    if system_parts:
        params["system"] = "\n\n".join(system_parts)
    if payload.get("temperature") is not None:
        params["temperature"] = payload["temperature"]
    stop_sequences = _stop_sequences(payload)
    if stop_sequences:
        params["stop_sequences"] = stop_sequences
    tools = _alpha_tools(payload.get("tools"))
    if tools:
        params["tools"] = tools

    return {
        "mode": "custom-agent",
        "config": {
            "workingDir": "FormulaWitness",
            "date": "",
            "environment": f"{platform.system().lower()}-{platform.machine()}, Python",
            "structure": [],
            "isGitRepo": False,
            "currentBranch": "",
            "mainBranch": "main",
            "gitStatus": "",
            "recentCommits": [],
        },
        "memory": "",
        "threadId": session_id,
        "params": params,
    }


def _tool_name_by_id(messages: Sequence[Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    for message in messages:
        if not isinstance(message, Mapping) or message.get("role") != "assistant":
            continue
        calls = message.get("tool_calls") or []
        if not isinstance(calls, Sequence) or isinstance(calls, str | bytes):
            raise TypeError("Assistant tool calls must be a sequence")
        for call in calls:
            if not isinstance(call, Mapping):
                raise TypeError("Assistant tool call must be an object")
            function = call.get("function")
            if not isinstance(function, Mapping):
                raise TypeError("Assistant tool call function must be an object")
            call_id = call.get("id")
            name = function.get("name")
            if isinstance(call_id, str) and call_id and isinstance(name, str) and name:
                if call_id in names:
                    raise ValueError("Assistant history contains a duplicate tool call id")
                names[call_id] = name
    return names


def _append_alpha_message(messages: list[dict[str, Any]], converted: dict[str, Any]) -> None:
    if converted["role"] == "user" and messages and messages[-1]["role"] == "user":
        previous = str(messages[-1].get("content") or "")
        current = str(converted.get("content") or "")
        messages[-1]["content"] = "\n\n".join(part for part in (previous, current) if part.strip())
        return
    messages.append(converted)


def _alpha_message(message: Mapping[str, Any], *, tool_names: Mapping[str, str]) -> dict[str, Any]:
    role = message.get("role")
    if role == "user":
        content = message.get("content")
        if not isinstance(content, str):
            raise TypeError("CommandCode user content must be text")
        return {"role": "user", "content": content}
    if role == "assistant":
        blocks: list[dict[str, Any]] = []
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise TypeError("CommandCode assistant content must be text")
        if content:
            blocks.append({"type": "text", "text": content})
        calls = message.get("tool_calls") or []
        if not isinstance(calls, Sequence) or isinstance(calls, str | bytes):
            raise TypeError("Assistant tool calls must be a sequence")
        for call in calls:
            if not isinstance(call, Mapping):
                raise TypeError("Assistant tool call must be an object")
            function = call.get("function")
            if not isinstance(function, Mapping):
                raise TypeError("Assistant tool call function must be an object")
            call_id = call.get("id")
            name = function.get("name")
            if not isinstance(call_id, str) or not call_id:
                raise ValueError("Assistant tool call id is missing")
            if not isinstance(name, str) or not name:
                raise ValueError("Assistant tool name is missing")
            arguments = function.get("arguments") or "{}"
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    raise ValueError("Assistant tool arguments are malformed JSON") from None
            if not isinstance(arguments, Mapping):
                raise TypeError("Assistant tool arguments must be an object")
            blocks.append(
                {
                    "type": "tool-call",
                    "toolCallId": call_id,
                    "toolName": name,
                    "input": dict(arguments),
                }
            )
        if not blocks:
            raise ValueError("CommandCode assistant message has no visible content")
        return {"role": "assistant", "content": blocks}
    if role == "tool":
        call_id = message.get("tool_call_id")
        if not isinstance(call_id, str) or not call_id:
            raise ValueError("CommandCode tool result id is missing")
        content = message.get("content")
        if not isinstance(content, str):
            raise TypeError("CommandCode tool result must be text")
        name = message.get("name") or tool_names.get(call_id)
        block: dict[str, Any] = {
            "type": "tool-result",
            "toolCallId": call_id,
            "output": {
                "type": "error-text" if message.get("is_error") is True else "text",
                "value": content,
            },
        }
        if name:
            block["toolName"] = str(name)
        return {"role": "tool", "content": [block]}
    raise ValueError(f"Unsupported CommandCode message role: {role}")


def _stop_sequences(payload: Mapping[str, Any]) -> list[str]:
    raw = payload.get("stop_sequences")
    if raw is None:
        raw = payload.get("stop")
    if raw is None:
        return []
    if isinstance(raw, str):
        values: Sequence[Any] = [raw]
    elif isinstance(raw, Sequence) and not isinstance(raw, bytes):
        values = raw
    else:
        raise TypeError("CommandCode stop sequences must be text or a sequence")
    if len(values) > 16:
        raise ValueError("CommandCode stop sequence count exceeds 16")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or len(value) > 1024:
            raise ValueError("CommandCode stop sequence is invalid")
        result.append(value)
    return result


def _alpha_tools(raw_tools: Any) -> list[dict[str, Any]]:
    if raw_tools is None:
        return []
    if not isinstance(raw_tools, Sequence) or isinstance(raw_tools, str | bytes):
        raise TypeError("CommandCode tools must be a sequence")
    tools: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for raw in raw_tools:
        if not isinstance(raw, Mapping) or raw.get("type") != "function":
            raise TypeError("CommandCode supports function tools only")
        function = raw.get("function")
        if not isinstance(function, Mapping):
            raise TypeError("Function tool must be an object")
        name = function.get("name")
        schema = function.get("parameters") or {"type": "object"}
        if not isinstance(name, str) or not name:
            raise ValueError("Function tool name is missing")
        if name in seen_names:
            raise ValueError(f"Duplicate CommandCode tool name: {name}")
        if not isinstance(schema, Mapping):
            raise TypeError("Function tool input schema must be an object")
        seen_names.add(name)
        tool: dict[str, Any] = {"name": name, "input_schema": dict(schema)}
        if function.get("description"):
            tool["description"] = str(function["description"])
        tools.append(tool)
    return tools


_SKIP = object()
_DONE = object()


@dataclass
class _PendingToolInput:
    name: str
    chunks: list[str]
    byte_count: int = 0
    ended: bool = False
    arguments: dict[str, Any] | None = None
    parse_failed: bool = False


def _parse_stream_line(line: str | bytes) -> dict[str, Any] | object:
    if isinstance(line, bytes):
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError:
            raise CommandCodeFatalError(
                "CommandCode stream is not valid UTF-8", status_code=422
            ) from None
    else:
        text = line
    text = text.strip()
    if not text or text.startswith(":"):
        return _SKIP
    if text.startswith(("event:", "id:", "retry:")):
        return _SKIP
    if text.startswith("data:"):
        text = text[5:].strip()
    if not text:
        return _SKIP
    if text == "[DONE]":
        return _DONE
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        raise CommandCodeFatalError(
            "CommandCode stream contained malformed JSON", status_code=422
        ) from None
    if not isinstance(value, dict):
        raise CommandCodeFatalError("CommandCode stream event is not an object", status_code=422)
    return value


class _CompletionAccumulator:
    def __init__(
        self,
        *,
        model: str,
        response_id: str,
        max_response_bytes: int,
        max_line_bytes: int,
        max_event_count: int,
        deadline: float,
        started: float,
        clock: Callable[[], float],
    ):
        self.model = model
        self.response_id = response_id
        self.request_id: str | None = None
        self.max_response_bytes = max_response_bytes
        self.max_line_bytes = max_line_bytes
        self.max_event_count = max_event_count
        self.deadline = deadline
        self.started = started
        self.clock = clock
        self.response_bytes = 0
        self.line_buffer = bytearray()
        self.event_count = 0
        self.text_parts: list[str] = []
        self.calls: list[dict[str, Any]] = []
        self.call_ids: set[str] = set()
        self.pending_tool_inputs: dict[str, _PendingToolInput] = {}
        self.finish_reason = "stop"
        self.usage: dict[str, int] = {}
        self.reported_cost_usd: float | None = None
        self.saw_provider_metadata = False
        self.saw_terminal = False
        self.saw_done_marker = False

    def consume_chunk(self, chunk: bytes) -> None:
        self._check_deadline()
        if not isinstance(chunk, bytes):
            raise CommandCodeFatalError("CommandCode stream chunk is not bytes", status_code=422)
        self.response_bytes += len(chunk)
        if self.response_bytes > self.max_response_bytes:
            raise CommandCodeFatalError(
                "CommandCode stream exceeded the configured response limit", status_code=413
            )
        self.line_buffer.extend(chunk)
        while True:
            newline = self.line_buffer.find(b"\n")
            if newline < 0:
                break
            if newline > self.max_line_bytes:
                raise CommandCodeFatalError(
                    "CommandCode stream line exceeded the configured limit",
                    status_code=413,
                )
            line = bytes(self.line_buffer[:newline])
            del self.line_buffer[: newline + 1]
            self._consume_line(line)
        if len(self.line_buffer) > self.max_line_bytes:
            raise CommandCodeFatalError(
                "CommandCode stream line exceeded the configured limit", status_code=413
            )
        self._check_deadline()

    def finish_input(self) -> None:
        """Consume a final unterminated line after the byte stream closes."""

        if self.line_buffer:
            self._consume_line(bytes(self.line_buffer))
            self.line_buffer.clear()

    def _consume_line(self, line: bytes) -> None:
        parsed = _parse_stream_line(line)
        if parsed is _SKIP:
            return
        self.event_count += 1
        if self.event_count > self.max_event_count:
            raise CommandCodeFatalError(
                "CommandCode stream exceeded the configured event limit", status_code=413
            )
        if parsed is _DONE:
            if not self.saw_terminal:
                raise CommandCodeTransientError(
                    "CommandCode stream ended before a terminal event", status_code=503
                )
            if self.saw_done_marker:
                raise CommandCodeFatalError(
                    "CommandCode stream contained duplicate completion markers",
                    status_code=422,
                )
            self.saw_done_marker = True
            return
        if self.saw_done_marker:
            raise CommandCodeFatalError(
                "CommandCode stream emitted data after its terminal event", status_code=422
            )
        assert isinstance(parsed, dict)
        if self.saw_terminal:
            event_type = str(parsed.get("type") or parsed.get("event") or "")
            if event_type not in {"provider-metadata", "provider_metadata"}:
                raise CommandCodeFatalError(
                    "CommandCode stream emitted data after its terminal event",
                    status_code=422,
                )
            self._consume_provider_metadata(parsed)
            self._check_deadline()
            return
        self._consume_event(parsed)
        self._check_deadline()

    def _consume_event(self, event: Mapping[str, Any]) -> None:
        event_type = str(event.get("type") or event.get("event") or "")
        if event_type == "error":
            raise _native_stream_error(event)
        if event_type in {
            "reasoning-start",
            "reasoning_start",
            "reasoning-delta",
            "reasoning_delta",
            "reasoning-end",
            "reasoning_end",
        }:
            return
        if event_type in {"tool-input-start", "tool_input_start"}:
            self._start_tool_input(event)
            return
        if event_type in {"tool-input-delta", "tool_input_delta"}:
            self._append_tool_input(event)
            return
        if event_type in {"tool-input-end", "tool_input_end"}:
            self._end_tool_input(event)
            return
        if "tool" in event_type.lower() and "delta" in event_type.lower():
            raise CommandCodeFatalError("CommandCode returned a partial tool call", status_code=422)
        if event_type in {"text-delta", "text_delta", "output_text_delta"}:
            value = _first_present(event, "text", "delta", "content")
            if value is not None and not isinstance(value, str):
                raise CommandCodeFatalError("CommandCode text delta is not text", status_code=422)
            if value:
                self.text_parts.append(value)
            return
        if event_type in {"tool-call", "tool_call"}:
            self._validate_completed_tool_input(event)
            self._consume_tool_call(event)
            return
        if event_type in {"provider-metadata", "provider_metadata"}:
            self._consume_provider_metadata(event)
            return
        if event_type in {"finish", "done", "message_stop"}:
            self._consume_terminal(event)
            return
        # Forward-compatible metadata events are ignored, but can never satisfy
        # the mandatory terminal-event requirement.

    def _start_tool_input(self, event: Mapping[str, Any]) -> None:
        call_id = _first_present(event, "toolCallId", "tool_call_id", "id")
        name = _first_present(event, "toolName", "tool_name", "name")
        if not isinstance(call_id, str) or not call_id:
            raise CommandCodeFatalError("CommandCode tool input id is missing", status_code=422)
        if not isinstance(name, str) or not name:
            raise CommandCodeFatalError("CommandCode tool input name is missing", status_code=422)
        if call_id in self.call_ids or call_id in self.pending_tool_inputs:
            raise CommandCodeFatalError(
                "CommandCode returned a duplicate tool input id", status_code=422
            )
        self.pending_tool_inputs[call_id] = _PendingToolInput(name=name, chunks=[])

    def _append_tool_input(self, event: Mapping[str, Any]) -> None:
        call_id = _first_present(event, "toolCallId", "tool_call_id", "id")
        if not isinstance(call_id, str) or call_id not in self.pending_tool_inputs:
            raise CommandCodeFatalError(
                "CommandCode tool input delta has no matching start", status_code=422
            )
        pending = self.pending_tool_inputs[call_id]
        if pending.ended:
            raise CommandCodeFatalError(
                "CommandCode tool input delta followed its end event", status_code=422
            )
        delta = _first_present(event, "delta", "text", "content")
        if not isinstance(delta, str):
            raise CommandCodeFatalError("CommandCode tool input delta is not text", status_code=422)
        pending.byte_count += len(delta.encode("utf-8"))
        if pending.byte_count > self.max_line_bytes:
            raise CommandCodeFatalError(
                "CommandCode tool arguments exceeded the configured limit", status_code=413
            )
        pending.chunks.append(delta)

    def _end_tool_input(self, event: Mapping[str, Any]) -> None:
        call_id = _first_present(event, "toolCallId", "tool_call_id", "id")
        if not isinstance(call_id, str) or call_id not in self.pending_tool_inputs:
            raise CommandCodeFatalError(
                "CommandCode tool input end has no matching start", status_code=422
            )
        pending = self.pending_tool_inputs[call_id]
        if pending.ended:
            raise CommandCodeFatalError(
                "CommandCode returned a duplicate tool input end", status_code=422
            )
        try:
            arguments = json.loads("".join(pending.chunks) or "{}")
        except json.JSONDecodeError:
            pending.parse_failed = True
        else:
            if not isinstance(arguments, dict):
                pending.parse_failed = True
            else:
                pending.arguments = arguments
        pending.ended = True

    def _validate_completed_tool_input(self, event: Mapping[str, Any]) -> None:
        call_id = _first_present(event, "toolCallId", "tool_call_id", "id")
        if not isinstance(call_id, str):
            return
        pending = self.pending_tool_inputs.get(call_id)
        if pending is None:
            return
        if not pending.ended:
            raise CommandCodeFatalError("CommandCode returned a partial tool call", status_code=422)
        name = _first_present(event, "toolName", "tool_name", "name")
        if name != pending.name:
            raise CommandCodeFatalError(
                "CommandCode incremental tool name did not match the completed call",
                status_code=422,
            )
        arguments = _first_present(event, "input", "args", "arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = None
        if not isinstance(arguments, Mapping):
            raise CommandCodeFatalError(
                "CommandCode completed tool arguments are not an object",
                status_code=422,
            )
        if (
            not pending.parse_failed
            and pending.arguments is not None
            and dict(arguments) != pending.arguments
        ):
            raise CommandCodeFatalError(
                "CommandCode incremental tool arguments did not match the completed call",
                status_code=422,
            )
        del self.pending_tool_inputs[call_id]

    def _consume_provider_metadata(self, event: Mapping[str, Any]) -> None:
        if self.saw_provider_metadata:
            raise CommandCodeFatalError(
                "CommandCode stream contained duplicate provider metadata", status_code=422
            )
        metadata = _first_present(event, "providerMetadata", "provider_metadata")
        if not isinstance(metadata, Mapping):
            raise CommandCodeFatalError(
                "CommandCode provider metadata is not an object", status_code=422
            )
        gateway = metadata.get("gateway")
        if gateway is not None and not isinstance(gateway, Mapping):
            raise CommandCodeFatalError(
                "CommandCode gateway metadata is not an object", status_code=422
            )
        costs: list[Decimal] = []
        if isinstance(gateway, Mapping):
            for field in ("cost", "gatewayCost", "gateway_cost"):
                if field not in gateway or gateway[field] is None:
                    continue
                raw_cost = gateway[field]
                if isinstance(raw_cost, bool):
                    raise CommandCodeFatalError(
                        "CommandCode reported cost is invalid", status_code=422
                    )
                try:
                    cost = Decimal(str(raw_cost))
                except (InvalidOperation, ValueError):
                    raise CommandCodeFatalError(
                        "CommandCode reported cost is invalid", status_code=422
                    ) from None
                if not cost.is_finite() or cost < 0:
                    raise CommandCodeFatalError(
                        "CommandCode reported cost is invalid", status_code=422
                    )
                costs.append(cost)
        if costs and any(cost != costs[0] for cost in costs[1:]):
            raise CommandCodeFatalError(
                "CommandCode reported conflicting cost totals", status_code=422
            )
        if costs:
            self.reported_cost_usd = float(costs[0])
        self.saw_provider_metadata = True

    def _consume_tool_call(self, event: Mapping[str, Any]) -> None:
        if event.get("partial") is True:
            raise CommandCodeFatalError("CommandCode returned a partial tool call", status_code=422)
        call_id = _first_present(event, "toolCallId", "tool_call_id", "id")
        name = _first_present(event, "toolName", "tool_name", "name")
        if not isinstance(call_id, str) or not call_id:
            raise CommandCodeFatalError("CommandCode tool call id is missing", status_code=422)
        if not isinstance(name, str) or not name:
            raise CommandCodeFatalError("CommandCode tool call name is missing", status_code=422)
        if call_id in self.call_ids:
            raise CommandCodeFatalError(
                "CommandCode returned a duplicate tool call id", status_code=422
            )
        arguments = _first_present(event, "input", "args", "arguments")
        if arguments is None:
            arguments = {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                raise CommandCodeFatalError(
                    "CommandCode tool arguments are malformed JSON", status_code=422
                ) from None
        if not isinstance(arguments, Mapping):
            raise CommandCodeFatalError(
                "CommandCode tool arguments are not an object", status_code=422
            )
        self.call_ids.add(call_id)
        self.calls.append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(dict(arguments), sort_keys=True, separators=(",", ":")),
                },
            }
        )

    def _consume_terminal(self, event: Mapping[str, Any]) -> None:
        if self.pending_tool_inputs:
            raise CommandCodeFatalError("CommandCode returned a partial tool call", status_code=422)
        if self.saw_terminal:
            raise CommandCodeFatalError(
                "CommandCode stream contained duplicate terminal events", status_code=422
            )
        self.saw_terminal = True
        raw_reason = str(
            _first_present(event, "finishReason", "finish_reason", "rawFinishReason") or ""
        ).lower()
        if "tool" in raw_reason:
            self.finish_reason = "tool_calls"
        elif "length" in raw_reason or "max" in raw_reason:
            self.finish_reason = "length"
        usage = _first_present(event, "totalUsage", "total_usage", "usage")
        if usage is not None:
            if not isinstance(usage, Mapping):
                raise CommandCodeFatalError("CommandCode usage is not an object", status_code=422)
            prompt = _nonnegative_int(
                _first_present(usage, "inputTokens", "input_tokens", "prompt_tokens") or 0,
                field="input tokens",
            )
            completion = _nonnegative_int(
                _first_present(
                    usage,
                    "outputTokens",
                    "output_tokens",
                    "completionTokens",
                    "completion_tokens",
                )
                or 0,
                field="output tokens",
            )
            self.usage = {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
            }

    def completion(self) -> dict[str, Any]:
        self._check_deadline()
        if self.pending_tool_inputs:
            raise CommandCodeFatalError("CommandCode returned a partial tool call", status_code=422)
        if not self.saw_terminal:
            raise CommandCodeTransientError(
                "CommandCode stream closed before a terminal event", status_code=503
            )
        if self.calls:
            self.finish_reason = "tool_calls"
        content_raw = "".join(self.text_parts)
        content = content_raw if content_raw.strip() else None
        if content is None and not self.calls:
            raise CommandCodeTransientError(
                "CommandCode stream contained no observable output", status_code=503
            )
        return {
            "id": self.response_id,
            "request_id": self.request_id,
            "model": self.model,
            "choices": [
                {
                    "message": {"content": content, "tool_calls": self.calls},
                    "finish_reason": self.finish_reason,
                }
            ],
            "usage": self.usage,
            "reported_cost_usd": self.reported_cost_usd,
        }

    def _check_deadline(self) -> None:
        if self.clock() - self.started > self.deadline:
            raise CommandCodeTransientError(
                "CommandCode stream exceeded its total deadline", status_code=408
            )


def _first_present(values: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in values:
            return values[name]
    return None


def _nonnegative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise CommandCodeFatalError(f"CommandCode {field} is invalid", status_code=422)
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        raise CommandCodeFatalError(f"CommandCode {field} is invalid", status_code=422) from None
    if result < 0:
        raise CommandCodeFatalError(f"CommandCode {field} is invalid", status_code=422)
    return result


def _raise_for_http_status(status_code: int) -> None:
    if status_code < 300:
        return
    if status_code < 400:
        raise CommandCodeFatalError(
            f"CommandCode redirect was rejected (HTTP {status_code})",
            status_code=status_code,
        )
    if status_code in {408, 429} or status_code >= 500:
        category = "rate limited" if status_code == 429 else "temporarily unavailable"
        raise CommandCodeTransientError(
            f"CommandCode is {category} (HTTP {status_code})", status_code=status_code
        )
    category = "authentication rejected" if status_code in {401, 403} else "request rejected"
    raise CommandCodeFatalError(
        f"CommandCode {category} (HTTP {status_code})", status_code=status_code
    )


def _native_stream_error(event: Mapping[str, Any]) -> CommandCodeNativeError:
    error = event.get("error")
    detail = error if isinstance(error, Mapping) else event
    status_raw = _first_present(detail, "status", "statusCode", "status_code")
    status: int | None = None
    if status_raw is not None:
        try:
            status = int(status_raw)
        except (TypeError, ValueError, OverflowError):
            status = None
    code = _safe_error_label(_first_present(detail, "code", "type"))
    private_text = " ".join(
        str(value)
        for value in (
            _first_present(detail, "message", "detail"),
            _first_present(detail, "code", "type"),
        )
        if value is not None
    ).lower()
    transient = (
        status in {408, 429}
        or (status is not None and status >= 500)
        or any(
            marker in private_text
            for marker in (
                "network connection lost",
                "connection lost",
                "server_error",
                "temporarily unavailable",
                "timeout",
                "rate limit",
            )
        )
    )
    suffix = f"; code={code}" if code else ""
    if transient:
        return CommandCodeTransientError(
            f"CommandCode stream failed transiently{suffix}",
            status_code=status if status is not None else 503,
        )
    return CommandCodeFatalError(
        f"CommandCode stream rejected the request{suffix}", status_code=status
    )


def _safe_error_label(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^A-Za-z0-9_.-]", "", value)[:64]
