"""Native Anthropic Messages API transport normalized to FormulaWitness turns."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx

from .model_client import OpenAICompatibleConfig

ANTHROPIC_VERSION = "2023-06-01"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class AnthropicTransport:
    """Translate the internal OpenAI-shaped wire request to Anthropic Messages."""

    def __init__(self, config: OpenAICompatibleConfig, *, client: Any | None = None):
        self._config = config
        self._client = client or httpx.Client(
            timeout=config.timeout_seconds,
            follow_redirects=False,
            headers={
                "x-api-key": config.api_key.get_secret_value(),
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
        )

    def create_chat_completion(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = _to_anthropic_request(payload)
        with self._client.stream(
            "POST", _messages_url(self._config.base_url), json=body
        ) as response:
            response.raise_for_status()
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ValueError("Anthropic response exceeded the configured safety limit")
            decoded = json.loads(raw)
            request_id = response.headers.get("request-id")
        return _to_openai_response(decoded, request_id=request_id)

    def close(self) -> None:
        self._client.close()


def _messages_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/messages" if base.endswith("/v1") else f"{base}/v1/messages"


def _to_anthropic_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    system_parts: list[str] = []
    messages: list[dict[str, Any]] = []

    def append_message(role: str, blocks: list[dict[str, Any]]) -> None:
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].extend(blocks)
        else:
            messages.append({"role": role, "content": blocks})

    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list):
        raise TypeError("messages must be a list")
    for raw_message in raw_messages:
        if not isinstance(raw_message, Mapping):
            raise TypeError("message must be an object")
        role = raw_message.get("role")
        content = raw_message.get("content")
        if role == "system":
            if not isinstance(content, str):
                raise TypeError("system content must be text")
            system_parts.append(content)
        elif role == "user":
            if not isinstance(content, str):
                raise TypeError("user content must be text")
            append_message("user", [{"type": "text", "text": content}])
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            if content is not None:
                if not isinstance(content, str):
                    raise TypeError("assistant content must be text")
                if content:
                    blocks.append({"type": "text", "text": content})
            for raw_call in raw_message.get("tool_calls") or []:
                function = raw_call["function"]
                arguments = function["arguments"]
                tool_input = json.loads(arguments) if isinstance(arguments, str) else arguments
                if not isinstance(tool_input, dict):
                    raise TypeError("tool arguments must decode to an object")
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": str(raw_call["id"]),
                        "name": str(function["name"]),
                        "input": tool_input,
                    }
                )
            append_message("assistant", blocks)
        elif role == "tool":
            if not isinstance(content, str):
                raise TypeError("tool result content must be text")
            append_message(
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": str(raw_message["tool_call_id"]),
                        "content": content,
                    }
                ],
            )
        else:
            raise ValueError(f"unsupported message role: {role}")

    body: dict[str, Any] = {
        "model": str(payload["model"]),
        "messages": messages,
        "max_tokens": int(payload["max_tokens"]),
    }
    if system_parts:
        body["system"] = "\n\n".join(system_parts)

    raw_tools = payload.get("tools") or []
    if raw_tools:
        tools: list[dict[str, Any]] = []
        for raw_tool in raw_tools:
            function = raw_tool["function"]
            tools.append(
                {
                    "name": str(function["name"]),
                    "description": str(function.get("description") or ""),
                    "input_schema": function["parameters"],
                }
            )
        body["tools"] = tools
        body["tool_choice"] = _tool_choice(
            payload.get("tool_choice", "auto"),
            parallel=bool(payload.get("parallel_tool_calls", True)),
        )
    return body


def _tool_choice(raw_choice: Any, *, parallel: bool) -> dict[str, Any]:
    disable_parallel = not parallel
    if isinstance(raw_choice, Mapping):
        function = raw_choice.get("function")
        if not isinstance(function, Mapping) or not function.get("name"):
            raise ValueError("named tool choice is malformed")
        return {
            "type": "tool",
            "name": str(function["name"]),
            "disable_parallel_tool_use": True,
        }
    choice_map = {
        "auto": "auto",
        "required": "any",
        "none": "none",
    }
    if raw_choice not in choice_map:
        raise ValueError(f"unsupported tool choice: {raw_choice}")
    result: dict[str, Any] = {"type": choice_map[raw_choice]}
    if raw_choice != "none":
        result["disable_parallel_tool_use"] = disable_parallel
    return result


def _to_openai_response(raw: Any, *, request_id: str | None) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise TypeError("Anthropic response must be an object")
    content = raw.get("content")
    if not isinstance(content, list):
        raise TypeError("Anthropic response content must be a list")
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, Mapping):
            raise TypeError("Anthropic content block must be an object")
        block_type = block.get("type")
        if block_type == "text":
            text_parts.append(str(block.get("text") or ""))
        elif block_type == "tool_use":
            tool_input = block.get("input")
            if not isinstance(tool_input, dict):
                raise TypeError("Anthropic tool input must be an object")
            tool_calls.append(
                {
                    "id": str(block["id"]),
                    "type": "function",
                    "function": {
                        "name": str(block["name"]),
                        "arguments": json.dumps(
                            tool_input,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    },
                }
            )
        elif block_type in {"thinking", "redacted_thinking"}:
            # Never persist or expose provider reasoning blocks.
            continue
        else:
            raise ValueError(f"unsupported Anthropic content block: {block_type}")

    usage = raw.get("usage") or {}
    if not isinstance(usage, Mapping):
        raise TypeError("Anthropic usage must be an object")
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    stop_reason = raw.get("stop_reason")
    finish_map = {"tool_use": "tool_calls", "max_tokens": "length"}
    finish_reason = finish_map.get(str(stop_reason), stop_reason)
    return {
        "id": raw.get("id"),
        "request_id": request_id,
        "model": raw.get("model"),
        "choices": [
            {
                "message": {
                    "content": "".join(text_parts) or None,
                    "tool_calls": tool_calls,
                },
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "prompt_tokens_details": {"cached_tokens": cache_read},
        },
    }
