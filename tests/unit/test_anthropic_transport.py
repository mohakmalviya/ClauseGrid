from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Self

import pytest

from formulawitness.agent_types import (
    AssistantMessage,
    ModelRequest,
    NamedToolChoice,
    SystemMessage,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)
from formulawitness.anthropic_transport import (
    MAX_RESPONSE_BYTES,
    AnthropicTransport,
)
from formulawitness.model_client import ModelClient, OpenAICompatibleConfig


class FakeResponse:
    def __init__(self, payload: Any, *, request_id: str = "request-anthropic-1"):
        self.payload = payload
        self.headers = {"request-id": request_id}
        self.status_code = 200

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self) -> list[bytes]:
        return [json.dumps(self.payload).encode("utf-8")]


class FakeHttpClient:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.closed = False

    def stream(self, method: str, url: str, *, json: dict[str, Any]) -> FakeResponse:
        self.calls.append((method, url, json))
        return self.response

    def close(self) -> None:
        self.closed = True


def config() -> OpenAICompatibleConfig:
    return OpenAICompatibleConfig(
        base_url="https://api.anthropic.com",
        model="claude-test-model",
        api_key="anthropic-secret",
    )


def tool() -> ToolSpec:
    return ToolSpec(
        name="inspect_region",
        description="Inspect a region.",
        parameters={
            "type": "object",
            "properties": {"sheet": {"type": "string"}},
            "required": ["sheet"],
            "additionalProperties": False,
        },
    )


def test_native_request_translation_and_response_normalization() -> None:
    raw_response = {
        "id": "msg_1",
        "model": "claude-test-model-20260829",
        "stop_reason": "tool_use",
        "content": [
            {"type": "thinking", "thinking": "not retained", "signature": "opaque"},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "inspect_region",
                "input": {"sheet": "Settlement"},
            },
        ],
        "usage": {
            "input_tokens": 21,
            "output_tokens": 8,
            "cache_read_input_tokens": 5,
        },
    }
    http_client = FakeHttpClient(FakeResponse(raw_response))
    transport = AnthropicTransport(config(), client=http_client)
    model = ModelClient(config(), transport=transport, clock=lambda: 1.0)
    request = ModelRequest(
        messages=(
            SystemMessage(content="Use evidence."),
            UserMessage(content="Inspect the defect."),
        ),
        tools=(tool(),),
        tool_choice="required",
        parallel_tool_calls=False,
    )

    turn = model.complete(request)

    assert turn.request_id == "request-anthropic-1"
    assert turn.response_id == "msg_1"
    assert turn.finish_reason == "tool_calls"
    assert turn.tool_calls[0].arguments == {"sheet": "Settlement"}
    assert turn.usage.input_tokens == 21
    assert turn.usage.output_tokens == 8
    assert turn.usage.cached_input_tokens == 5
    method, url, body = http_client.calls[0]
    assert method == "POST"
    assert url == "https://api.anthropic.com/v1/messages"
    assert body["system"] == "Use evidence."
    assert body["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "Inspect the defect."}]}
    ]
    assert body["tools"][0]["input_schema"] == tool().parameters
    assert body["tool_choice"] == {"type": "any", "disable_parallel_tool_use": True}
    assert "temperature" not in body
    assert "seed" not in body


def test_native_history_maps_assistant_tool_use_and_tool_result() -> None:
    raw_response = {
        "id": "msg_2",
        "model": "claude-test-model",
        "stop_reason": "tool_use",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_10",
                "name": "inspect_region",
                "input": {"sheet": "Settlement"},
            }
        ],
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }
    http_client = FakeHttpClient(FakeResponse(raw_response))
    model = ModelClient(config(), transport=AnthropicTransport(config(), client=http_client))
    request = ModelRequest(
        messages=(
            UserMessage(content="Inspect."),
            AssistantMessage(
                content=None,
                tool_calls=(
                    ToolCall(
                        call_id="toolu_9",
                        name="inspect_region",
                        arguments={"sheet": "Settlement"},
                    ),
                ),
            ),
            ToolResultMessage(
                tool_call_id="toolu_9",
                name="inspect_region",
                content='{"cell":"P6","formula":"=1"}',
            ),
        ),
        tools=(tool(),),
        tool_choice=NamedToolChoice(name="inspect_region"),
    )

    turn = model.complete(request)

    body = http_client.calls[0][2]
    assert body["messages"][1]["content"][0] == {
        "type": "tool_use",
        "id": "toolu_9",
        "name": "inspect_region",
        "input": {"sheet": "Settlement"},
    }
    assert body["messages"][2]["content"][0]["type"] == "tool_result"
    assert body["tool_choice"] == {
        "type": "tool",
        "name": "inspect_region",
        "disable_parallel_tool_use": True,
    }
    assert turn.tool_calls[0].call_id == "toolu_10"
    assert turn.finish_reason == "tool_calls"


def test_transport_rejects_oversized_response_and_closes_client() -> None:
    response = FakeResponse({"content": []})
    response.iter_bytes = lambda: [b"x" * (MAX_RESPONSE_BYTES + 1)]  # type: ignore[method-assign]
    http_client = FakeHttpClient(response)
    transport = AnthropicTransport(config(), client=http_client)

    with pytest.raises(ValueError, match="safety limit"):
        transport.create_chat_completion(
            {"model": "claude-test-model", "messages": [], "max_tokens": 32}
        )
    transport.close()
    assert http_client.closed


def test_anthropic_api_key_is_not_present_in_transport_repr() -> None:
    transport = AnthropicTransport(config(), client=SimpleNamespace())
    assert "anthropic-secret" not in repr(transport)
