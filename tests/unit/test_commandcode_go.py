from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any

import pytest
from pydantic import SecretStr

from formulawitness.agent_types import (
    AssistantMessage,
    ModelRequest,
    SystemMessage,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)
from formulawitness.commandcode_go import (
    COMMAND_CODE_CLI_VERSION,
    CommandCodeFatalError,
    CommandCodeGoTransport,
    CommandCodeNativeError,
    CommandCodeTransientError,
    StreamResponse,
)
from formulawitness.model_client import ModelClient, OpenAICompatibleConfig


class FakeResponse:
    def __init__(
        self,
        lines: Sequence[str | bytes] | None = None,
        *,
        status_code: int = 200,
        iteration_error: BaseException | None = None,
    ) -> None:
        self.lines = lines or []
        self.status_code = status_code
        self.headers: Mapping[str, str] = {"x-request-id": "request-commandcode-1"}
        self.iteration_error = iteration_error

    def iter_bytes(self, chunk_size: int | None = None) -> Iterator[bytes]:
        del chunk_size
        for line in self.lines:
            yield (line.encode("utf-8") if isinstance(line, str) else line) + b"\n"
        if self.iteration_error is not None:
            raise self.iteration_error


class FakeStream(AbstractContextManager[StreamResponse]):
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.entered = False
        self.exited = False

    def __enter__(self) -> StreamResponse:
        self.entered = True
        return self.response

    def __exit__(self, *_exc: object) -> None:
        self.exited = True


class ChunkedFakeResponse(FakeResponse):
    def __init__(self, chunks: Sequence[bytes]) -> None:
        super().__init__([])
        self.chunks = chunks

    def iter_bytes(self, chunk_size: int | None = None) -> Iterator[bytes]:
        del chunk_size
        yield from self.chunks


class FakeHttpClient:
    def __init__(
        self,
        response: FakeResponse | None = None,
        *,
        stream_error: BaseException | None = None,
    ) -> None:
        self.response = response or successful_text_response()
        self.stream_error = stream_error
        self.url = ""
        self.method = ""
        self.headers: Mapping[str, str] = {}
        self.body: Mapping[str, Any] = {}
        self.stream_context: FakeStream | None = None
        self.closed = False
        self.close_calls = 0

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, Any],
    ) -> AbstractContextManager[StreamResponse]:
        if self.stream_error is not None:
            raise self.stream_error
        self.method = method
        self.url = url
        self.headers = headers
        self.body = json
        self.stream_context = FakeStream(self.response)
        return self.stream_context

    def close(self) -> None:
        self.closed = True
        self.close_calls += 1


def config(
    *,
    base_url: str = "https://api.commandcode.ai",
    secret: str = "command-code-secret",
) -> OpenAICompatibleConfig:
    return OpenAICompatibleConfig(
        base_url=base_url,
        model="xiaomi/mimo-v2.5",
        api_key=SecretStr(secret),
        timeout_seconds=30,
    )


def payload(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "model": "xiaomi/mimo-v2.5",
        "messages": [{"role": "user", "content": "Inspect the workbook."}],
        "temperature": 0.0,
        "max_tokens": 1024,
    }
    result.update(overrides)
    return result


def successful_text_response(text: str = "done") -> FakeResponse:
    return FakeResponse(
        [
            f'data: {{"type":"text-delta","text":"{text}"}}',
            (
                'data: {"type":"finish","finishReason":"stop",'
                '"totalUsage":{"inputTokens":4,"outputTokens":1}}'
            ),
            "data: [DONE]",
        ]
    )


def test_preserves_native_tool_history_and_normalizes_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COMMAND_CODE_CLI_VERSION", raising=False)
    response = FakeResponse(
        [
            'data: {"type":"reasoning-start"}',
            'data: {"type":"reasoning-delta","text":"private reasoning"}',
            'data: {"type":"reasoning-end"}',
            (
                'data: {"type":"tool-call","toolCallId":"call-2",'
                '"toolName":"read_region","input":{"sheet":"RebateCalc","region":"P6:P6"}}'
            ),
            (
                'data: {"type":"finish","finishReason":"tool-calls",'
                '"totalUsage":{"inputTokens":40,"outputTokens":9}}'
            ),
            "data: [DONE]",
        ]
    )
    http = FakeHttpClient(response)
    transport = CommandCodeGoTransport(config(), client=http)
    model = ModelClient(config(), transport=transport)
    tool = ToolSpec(
        name="read_region",
        description="Read a bounded worksheet region.",
        parameters={
            "type": "object",
            "properties": {
                "sheet": {"type": "string"},
                "region": {"type": "string"},
            },
            "required": ["sheet", "region"],
            "additionalProperties": False,
        },
    )
    request = ModelRequest(
        messages=(
            SystemMessage(content="Use tools and report observable evidence."),
            UserMessage(content="Inspect the workbook."),
            AssistantMessage(
                tool_calls=(
                    ToolCall(
                        call_id="call-1",
                        name="read_region",
                        arguments={"sheet": "RebateCalc", "region": "A1:T10"},
                    ),
                )
            ),
            ToolResultMessage(
                tool_call_id="call-1",
                name="read_region",
                content='{"ok":true}',
            ),
        ),
        tools=(tool,),
        tool_choice="required",
    )

    turn = model.complete(request)

    assert http.method == "POST"
    assert http.url == "https://api.commandcode.ai/alpha/generate"
    assert http.headers["Authorization"] == "Bearer command-code-secret"
    assert http.headers["x-command-code-version"] == COMMAND_CODE_CLI_VERSION == "0.32.2"
    assert http.stream_context is not None and http.stream_context.exited
    assert http.body["mode"] == "custom-agent"
    params = http.body["params"]
    assert params["system"] == "Use tools and report observable evidence."
    assert params["tools"][0]["input_schema"] == tool.parameters
    assert params["messages"][1]["content"][0]["type"] == "tool-call"
    assert params["messages"][2]["content"][0]["type"] == "tool-result"
    assert turn.request_id == "request-commandcode-1"
    assert turn.tool_calls[0].call_id == "call-2"
    assert turn.tool_calls[0].arguments == {"sheet": "RebateCalc", "region": "P6:P6"}
    assert turn.usage.input_tokens == 40
    assert turn.usage.output_tokens == 9
    assert turn.content is None


def test_validates_native_incremental_tool_input_before_accepting_full_call() -> None:
    response = FakeResponse(
        [
            (
                'data: {"type":"tool-input-start","id":"call-2",'
                '"toolName":"read_region","dynamic":false}'
            ),
            'data: {"type":"tool-input-delta","id":"call-2","delta":"{\\"sheet\\":"}',
            (
                'data: {"type":"tool-input-delta","id":"call-2",'
                '"delta":"\\"RebateCalc\\",\\"region\\":\\"P6:P6\\"}"}'
            ),
            'data: {"type":"tool-input-end","id":"call-2"}',
            (
                'data: {"type":"tool-call","toolCallId":"call-2",'
                '"toolName":"read_region","input":{"sheet":"RebateCalc","region":"P6:P6"}}'
            ),
            'data: {"type":"finish","finishReason":"tool-calls"}',
            (
                'data: {"type":"provider-metadata","providerMetadata":'
                '{"gateway":{"cost":"0.000029","gatewayCost":"0.000029"}}}'
            ),
            "data: [DONE]",
        ]
    )
    transport = CommandCodeGoTransport(config(), client=FakeHttpClient(response))

    result = transport.create_chat_completion(payload())

    call = result["choices"][0]["message"]["tool_calls"][0]
    assert call["id"] == "call-2"
    assert call["function"]["name"] == "read_region"
    assert call["function"]["arguments"] == '{"region":"P6:P6","sheet":"RebateCalc"}'
    assert result["reported_cost_usd"] == pytest.approx(0.000029)


def test_ignores_malformed_preview_only_when_authoritative_full_call_is_valid() -> None:
    response = FakeResponse(
        [
            'data: {"type":"tool-input-start","id":"call-2","toolName":"inspect"}',
            'data: {"type":"tool-input-delta","id":"call-2","delta":"{"}',
            'data: {"type":"tool-input-end","id":"call-2"}',
            (
                'data: {"type":"tool-call","toolCallId":"call-2",'
                '"toolName":"inspect","input":{"sheet":"RebateCalc"}}'
            ),
            'data: {"type":"finish","finishReason":"tool-calls"}',
        ]
    )
    transport = CommandCodeGoTransport(config(), client=FakeHttpClient(response))

    result = transport.create_chat_completion(payload())

    call = result["choices"][0]["message"]["tool_calls"][0]
    assert call["function"]["arguments"] == '{"sheet":"RebateCalc"}'


@pytest.mark.parametrize(
    "events",
    [
        [
            'data: {"type":"tool-input-delta","id":"a","delta":"{}"}',
        ],
        [
            'data: {"type":"tool-input-start","id":"a","toolName":"x"}',
            'data: {"type":"tool-input-delta","id":"a","delta":"{"}',
            'data: {"type":"tool-input-end","id":"a"}',
        ],
        [
            'data: {"type":"tool-input-start","id":"a","toolName":"x"}',
            'data: {"type":"tool-input-delta","id":"a","delta":"{}"}',
            'data: {"type":"tool-input-end","id":"a"}',
            ('data: {"type":"tool-call","toolCallId":"a","toolName":"different","input":{}}'),
        ],
        [
            'data: {"type":"tool-input-start","id":"a","toolName":"x"}',
            'data: {"type":"tool-input-delta","id":"a","delta":"{\\"a\\":1}"}',
            'data: {"type":"tool-input-end","id":"a"}',
            'data: {"type":"tool-call","toolCallId":"a","toolName":"x","input":{"a":2}}',
        ],
        [
            'data: {"type":"tool-input-start","id":"a","toolName":"x"}',
            'data: {"type":"tool-input-delta","id":"a","delta":"{}"}',
            'data: {"type":"finish","finishReason":"tool-calls"}',
        ],
    ],
)
def test_rejects_invalid_incremental_tool_input_lifecycles(events: list[str]) -> None:
    transport = CommandCodeGoTransport(config(), client=FakeHttpClient(FakeResponse(events)))
    with pytest.raises(CommandCodeFatalError):
        transport.create_chat_completion(payload())


def test_ports_user_merge_error_tool_result_name_and_stop_sequences() -> None:
    http = FakeHttpClient()
    transport = CommandCodeGoTransport(config(), client=http)
    raw = payload(
        messages=[
            {"role": "system", "content": "System one."},
            {"role": "system", "content": "System two."},
            {"role": "user", "content": "First"},
            {"role": "user", "content": "Second"},
            {
                "role": "assistant",
                "content": None,
                "reasoning_content": "must not be replayed",
                "tool_calls": [
                    {
                        "id": "call-a",
                        "type": "function",
                        "function": {"name": "inspect", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-a",
                "content": "failed safely",
                "is_error": True,
            },
        ],
        stop=["END", "HALT"],
    )

    transport.create_chat_completion(raw)

    params = http.body["params"]
    assert params["system"] == "System one.\n\nSystem two."
    assert params["messages"][0] == {"role": "user", "content": "First\n\nSecond"}
    assistant = params["messages"][1]["content"][0]
    assert assistant == {
        "type": "tool-call",
        "toolCallId": "call-a",
        "toolName": "inspect",
        "input": {},
    }
    tool_result = params["messages"][2]["content"][0]
    assert tool_result["toolName"] == "inspect"
    assert tool_result["output"] == {"type": "error-text", "value": "failed safely"}
    assert params["stop_sequences"] == ["END", "HALT"]
    assert http.body["config"]["structure"] == []
    assert http.body["config"]["gitStatus"] == ""


def test_frames_events_incrementally_across_network_chunks() -> None:
    response = ChunkedFakeResponse(
        [
            b'data: {"type":"text-',
            b'delta","text":"chunked"}\ndata: {"type":"finish",',
            b'"finishReason":"stop"}\ndata: [DONE]\n',
        ]
    )
    transport = CommandCodeGoTransport(config(), client=FakeHttpClient(response))

    result = transport.create_chat_completion(payload())

    assert result["choices"][0]["message"]["content"] == "chunked"


@pytest.mark.parametrize(
    ("base_url", "allow_localhost", "match"),
    [
        ("http://api.commandcode.ai", False, "requires HTTPS"),
        ("https://evil.example", False, "host is not allowed"),
        ("http://127.0.0.1:8765", False, "host is not allowed"),
        ("https://api.commandcode.ai/provider/v1", False, "must not contain"),
        ("https://user:password@api.commandcode.ai", False, "plain absolute"),
    ],
)
def test_rejects_unsafe_commandcode_base_urls(
    base_url: str, allow_localhost: bool, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        CommandCodeGoTransport(
            config(base_url=base_url),
            client=FakeHttpClient(),
            allow_localhost=allow_localhost,
        )


def test_allows_localhost_only_with_explicit_test_flag() -> None:
    local = config(base_url="http://127.0.0.1:8765")
    transport = CommandCodeGoTransport(
        local,
        client=FakeHttpClient(),
        allow_localhost=True,
    )
    assert transport.create_chat_completion(payload())["choices"][0]["message"]["content"] == "done"


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (302, CommandCodeFatalError),
        (401, CommandCodeFatalError),
        (403, CommandCodeFatalError),
        (429, CommandCodeTransientError),
        (500, CommandCodeTransientError),
        (503, CommandCodeTransientError),
    ],
)
def test_classifies_http_status_without_exposing_response_body(
    status: int, error_type: type[CommandCodeNativeError]
) -> None:
    transport = CommandCodeGoTransport(
        config(), client=FakeHttpClient(FakeResponse(status_code=status))
    )

    with pytest.raises(error_type) as captured:
        transport.create_chat_completion(payload())

    assert captured.value.status_code == status
    assert "command-code-secret" not in str(captured.value)


def test_rejects_request_model_mismatch_before_network() -> None:
    http = FakeHttpClient()
    transport = CommandCodeGoTransport(config(), client=http)

    with pytest.raises(CommandCodeFatalError, match="does not match"):
        transport.create_chat_completion(payload(model="xiaomi/mimo-v2.5-pro"))

    assert http.url == ""


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("Bearer command-code-secret"), ConnectionError("command-code-secret")],
)
def test_sanitizes_stream_open_failures(failure: BaseException) -> None:
    transport = CommandCodeGoTransport(config(), client=FakeHttpClient(stream_error=failure))

    with pytest.raises(CommandCodeTransientError) as captured:
        transport.create_chat_completion(payload())

    assert "command-code-secret" not in str(captured.value)
    assert captured.value.status_code in {408, 503}


def test_iteration_timeout_is_transient_and_response_is_closed() -> None:
    http = FakeHttpClient(
        FakeResponse(
            ['data: {"type":"text-delta","text":"partial"}'],
            iteration_error=TimeoutError("private transport detail"),
        )
    )
    transport = CommandCodeGoTransport(config(), client=http)

    with pytest.raises(CommandCodeTransientError, match="timed out"):
        transport.create_chat_completion(payload())

    assert http.stream_context is not None and http.stream_context.exited


def test_missing_terminal_event_is_transient() -> None:
    transport = CommandCodeGoTransport(
        config(),
        client=FakeHttpClient(FakeResponse(['data: {"type":"text-delta","text":"truncated"}'])),
    )

    with pytest.raises(CommandCodeTransientError, match="terminal event"):
        transport.create_chat_completion(payload())


def test_done_marker_cannot_replace_native_terminal_event() -> None:
    transport = CommandCodeGoTransport(
        config(), client=FakeHttpClient(FakeResponse(["data: [DONE]"]))
    )
    with pytest.raises(CommandCodeTransientError, match="terminal event"):
        transport.create_chat_completion(payload())


@pytest.mark.parametrize(
    "bad_line",
    [
        "data: not-json",
        "data: []",
        b"data: \xff",
    ],
)
def test_rejects_malformed_stream_lines(bad_line: str | bytes) -> None:
    transport = CommandCodeGoTransport(config(), client=FakeHttpClient(FakeResponse([bad_line])))
    with pytest.raises(CommandCodeFatalError):
        transport.create_chat_completion(payload())


def test_rejects_duplicate_and_partial_tool_events() -> None:
    duplicate = [
        'data: {"type":"tool-call","toolCallId":"same","toolName":"x","input":{}}',
        'data: {"type":"tool-call","toolCallId":"same","toolName":"x","input":{}}',
    ]
    partial = ['data: {"type":"tool-call-delta","toolCallId":"a","delta":"fragment"}']
    for lines in (duplicate, partial):
        transport = CommandCodeGoTransport(config(), client=FakeHttpClient(FakeResponse(lines)))
        with pytest.raises(CommandCodeFatalError):
            transport.create_chat_completion(payload())


def test_rejects_missing_tool_identity_and_malformed_arguments() -> None:
    cases = [
        'data: {"type":"tool-call","toolName":"x","input":{}}',
        'data: {"type":"tool-call","toolCallId":"a","input":{}}',
        ('data: {"type":"tool-call","toolCallId":"a","toolName":"x","arguments":"not-json"}'),
    ]
    for line in cases:
        transport = CommandCodeGoTransport(config(), client=FakeHttpClient(FakeResponse([line])))
        with pytest.raises(CommandCodeFatalError):
            transport.create_chat_completion(payload())


def test_rejects_data_after_terminal_event() -> None:
    response = FakeResponse(
        [
            'data: {"type":"text-delta","text":"ok"}',
            'data: {"type":"finish","finishReason":"stop"}',
            'data: {"type":"text-delta","text":"late"}',
        ]
    )
    transport = CommandCodeGoTransport(config(), client=FakeHttpClient(response))
    with pytest.raises(CommandCodeFatalError, match="after its terminal"):
        transport.create_chat_completion(payload())


@pytest.mark.parametrize(
    "metadata",
    [
        '{"type":"provider-metadata","providerMetadata":[]}',
        '{"type":"provider-metadata","providerMetadata":{"gateway":[]}}',
        ('{"type":"provider-metadata","providerMetadata":{"gateway":{"cost":"-0.1"}}}'),
        (
            '{"type":"provider-metadata","providerMetadata":'
            '{"gateway":{"cost":"0.1","gatewayCost":"0.2"}}}'
        ),
    ],
)
def test_rejects_invalid_post_terminal_provider_metadata(metadata: str) -> None:
    response = FakeResponse(
        [
            'data: {"type":"text-delta","text":"ok"}',
            'data: {"type":"finish","finishReason":"stop"}',
            f"data: {metadata}",
        ]
    )
    transport = CommandCodeGoTransport(config(), client=FakeHttpClient(response))
    with pytest.raises(CommandCodeFatalError):
        transport.create_chat_completion(payload())


def test_rejects_duplicate_post_terminal_provider_metadata() -> None:
    metadata = 'data: {"type":"provider-metadata","providerMetadata":{"gateway":{"cost":"0.1"}}}'
    response = FakeResponse(
        [
            'data: {"type":"text-delta","text":"ok"}',
            'data: {"type":"finish","finishReason":"stop"}',
            metadata,
            metadata,
        ]
    )
    transport = CommandCodeGoTransport(config(), client=FakeHttpClient(response))
    with pytest.raises(CommandCodeFatalError, match="duplicate provider metadata"):
        transport.create_chat_completion(payload())


def test_reasoning_is_not_observable_output() -> None:
    response = FakeResponse(
        [
            'data: {"type":"reasoning-delta","text":"hidden chain"}',
            'data: {"type":"finish","finishReason":"stop"}',
            "data: [DONE]",
        ]
    )
    transport = CommandCodeGoTransport(config(), client=FakeHttpClient(response))
    with pytest.raises(CommandCodeTransientError, match="no observable output") as captured:
        transport.create_chat_completion(payload())
    assert captured.value.status_code == 503


@pytest.mark.parametrize(
    ("bound", "match"),
    [
        ("line", "line exceeded"),
        ("response", "response limit"),
        ("events", "event limit"),
    ],
)
def test_enforces_stream_size_and_event_bounds(bound: str, match: str) -> None:
    if bound == "line":
        lines = ['data: {"type":"text-delta","text":"far too long"}']
        transport = CommandCodeGoTransport(
            config(), client=FakeHttpClient(FakeResponse(lines)), max_line_bytes=20
        )
    elif bound == "response":
        lines = [
            'data: {"type":"text-delta","text":"aaaaaaaaaaaaaaaaaaaaaaaa"}',
            'data: {"type":"text-delta","text":"bbbbbbbbbbbbbbbbbbbbbbbb"}',
        ]
        transport = CommandCodeGoTransport(
            config(), client=FakeHttpClient(FakeResponse(lines)), max_response_bytes=80
        )
    else:
        lines = [
            'data: {"type":"text-delta","text":"one"}',
            'data: {"type":"finish","finishReason":"stop"}',
        ]
        transport = CommandCodeGoTransport(
            config(), client=FakeHttpClient(FakeResponse(lines)), max_event_count=1
        )
    with pytest.raises(CommandCodeFatalError, match=match):
        transport.create_chat_completion(payload())


def test_enforces_total_stream_deadline() -> None:
    ticks = iter([0.0, 2.0])
    transport = CommandCodeGoTransport(
        config(),
        client=FakeHttpClient(successful_text_response()),
        stream_deadline_seconds=1.0,
        clock=lambda: next(ticks, 2.0),
    )
    with pytest.raises(CommandCodeTransientError, match="deadline"):
        transport.create_chat_completion(payload())


@pytest.mark.parametrize(
    ("status", "message", "expected"),
    [
        (429, "Bearer command-code-secret rate limit", CommandCodeTransientError),
        (400, "Bearer command-code-secret invalid request", CommandCodeFatalError),
    ],
)
def test_native_error_events_are_classified_and_sanitized(
    status: int, message: str, expected: type[CommandCodeNativeError]
) -> None:
    line = (
        'data: {"type":"error","error":'
        f'{{"status":{status},"code":"provider / code","message":"{message}"}}}}'
    )
    transport = CommandCodeGoTransport(config(), client=FakeHttpClient(FakeResponse([line])))
    with pytest.raises(expected) as captured:
        transport.create_chat_completion(payload())
    assert "command-code-secret" not in str(captured.value)
    assert "providercode" in str(captured.value)


def test_context_manager_closes_owned_client_once() -> None:
    http = FakeHttpClient()
    transport = CommandCodeGoTransport(config(), client=http)

    with transport:
        transport.create_chat_completion(payload())

    transport.close()
    assert http.closed
    assert http.close_calls == 1
    with pytest.raises(RuntimeError, match="closed"):
        transport.create_chat_completion(payload())
