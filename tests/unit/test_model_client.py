from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import pytest

from formulawitness.agent_types import (
    ModelRequest,
    NamedToolChoice,
    SystemMessage,
    ToolSpec,
    UserMessage,
)
from formulawitness.model_client import (
    FatalModelError,
    ModelClient,
    ModelConfigurationError,
    ModelProtocolError,
    ModelTransport,
    OpenAICompatibleConfig,
    RetryPolicy,
    TransientModelError,
)


class ScriptedTransport(ModelTransport):
    def __init__(self, outcomes: list[Any]):
        self.outcomes = list(outcomes)
        self.payloads: list[Mapping[str, Any]] = []

    def create_chat_completion(self, payload: Mapping[str, Any]) -> Any:
        self.payloads.append(payload)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ClosableTransport(ScriptedTransport):
    def __init__(self, outcomes: list[Any]):
        super().__init__(outcomes)
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class ProviderFailure(Exception):
    def __init__(self, message: str, status_code: int, *, retry_after: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        headers = {} if retry_after is None else {"retry-after": retry_after}
        self.response = SimpleNamespace(status_code=status_code, headers=headers)


def response_with_tool_call() -> SimpleNamespace:
    function = SimpleNamespace(name="inspect_region", arguments='{"sheet":"Settlement"}')
    call = SimpleNamespace(id="call-1", type="function", function=function)
    message = SimpleNamespace(content=None, tool_calls=[call])
    choice = SimpleNamespace(message=message, finish_reason="tool_calls")
    usage = SimpleNamespace(
        prompt_tokens=12,
        completion_tokens=7,
        total_tokens=19,
        prompt_tokens_details=SimpleNamespace(cached_tokens=3),
    )
    return SimpleNamespace(
        id="completion-1",
        _request_id="request-1",
        model="test-model-2026",
        choices=[choice],
        usage=usage,
    )


def request() -> ModelRequest:
    return ModelRequest(
        messages=(
            SystemMessage(content="Investigate the workbook using evidence."),
            UserMessage(content="Find the policy defect."),
        ),
        tools=(
            ToolSpec(
                name="inspect_region",
                description="Inspect a bounded worksheet region.",
                parameters={
                    "type": "object",
                    "properties": {"sheet": {"type": "string"}},
                    "required": ["sheet"],
                    "additionalProperties": False,
                },
            ),
        ),
        tool_choice="required",
    )


def config(secret: str = "nim-secret-value") -> OpenAICompatibleConfig:
    return OpenAICompatibleConfig(
        base_url="https://example.invalid/v1",
        model="test-model",
        api_key=secret,
    )


def test_config_loads_key_from_environment_without_disclosing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "never-print-this-key"
    monkeypatch.setenv("TEST_MODEL_KEY", secret)
    loaded = OpenAICompatibleConfig.from_env(
        base_url="https://example.invalid/v1",
        model="test-model",
        api_key_env="TEST_MODEL_KEY",
    )

    assert loaded.api_key.get_secret_value() == secret
    assert secret not in repr(loaded)
    assert secret not in loaded.model_dump_json()

    monkeypatch.delenv("TEST_MODEL_KEY")
    with pytest.raises(ModelConfigurationError, match="TEST_MODEL_KEY"):
        OpenAICompatibleConfig.from_env(
            base_url="https://example.invalid/v1",
            model="test-model",
            api_key_env="TEST_MODEL_KEY",
        )


@pytest.mark.parametrize(
    "base_url",
    (
        "http://models.example.test/v1",
        "https://user:password@models.example.test/v1",
        "https://models.example.test/v1?token=secret",
    ),
)
def test_config_rejects_insecure_or_credential_bearing_base_urls(base_url: str) -> None:
    with pytest.raises(ValueError, match="base URL"):
        OpenAICompatibleConfig(base_url=base_url, model="test-model", api_key="secret")


def test_config_allows_loopback_http_for_local_gateway_development() -> None:
    loaded = OpenAICompatibleConfig(
        base_url="http://127.0.0.1:8082/v1/", model="test-model", api_key="secret"
    )
    assert loaded.base_url == "http://127.0.0.1:8082/v1"


def test_normalizes_tool_call_usage_and_wire_payload() -> None:
    transport = ScriptedTransport([response_with_tool_call()])
    client = ModelClient(config(), transport=transport, clock=lambda: 10.0)

    turn = client.complete(request())

    assert turn.model == "test-model-2026"
    assert turn.response_id == "completion-1"
    assert turn.request_id == "request-1"
    assert turn.tool_calls[0].call_id == "call-1"
    assert turn.tool_calls[0].name == "inspect_region"
    assert turn.tool_calls[0].arguments == {"sheet": "Settlement"}
    assert turn.usage.input_tokens == 12
    assert turn.usage.output_tokens == 7
    assert turn.usage.cached_input_tokens == 3
    assert turn.retry_count == 0
    payload = transport.payloads[0]
    assert payload["model"] == "test-model"
    assert payload["tool_choice"] == "required"
    assert payload["parallel_tool_calls"] is False


def test_retries_only_transient_failures_and_honors_retry_after() -> None:
    transient = ProviderFailure("rate limited", 429, retry_after="1.25")
    transport = ScriptedTransport([transient, response_with_tool_call()])
    delays: list[float] = []
    client = ModelClient(
        config(),
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.1),
        sleeper=delays.append,
        clock=lambda: 10.0,
    )

    turn = client.complete(request())

    assert turn.retry_count == 1
    assert len(transport.payloads) == 2
    assert delays == [1.25]


def test_fatal_failure_is_not_retried_and_redacts_credential() -> None:
    secret = "sensitive-nim-key"
    failure = ProviderFailure(f"Authorization: Bearer {secret}; api_key={secret}", 401)
    transport = ScriptedTransport([failure, response_with_tool_call()])
    client = ModelClient(config(secret), transport=transport)

    with pytest.raises(FatalModelError) as captured:
        client.complete(request())

    assert captured.value.status_code == 401
    assert captured.value.retry_count == 0
    assert secret not in str(captured.value)
    assert "[REDACTED]" in str(captured.value)
    assert len(transport.payloads) == 1


def test_transient_failure_reports_exhausted_bounded_attempts() -> None:
    failure = ProviderFailure("service unavailable", 503)
    transport = ScriptedTransport([failure, failure])
    client = ModelClient(
        config(),
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0),
        sleeper=lambda _: None,
    )

    with pytest.raises(TransientModelError) as captured:
        client.complete(request())

    assert captured.value.status_code == 503
    assert captured.value.retry_count == 1
    assert len(transport.payloads) == 2


def test_request_attempt_limit_caps_transport_retries() -> None:
    failure = ProviderFailure("service unavailable", 503)
    transport = ScriptedTransport([failure, response_with_tool_call()])
    client = ModelClient(
        config(),
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0),
        sleeper=lambda _: None,
    )

    with pytest.raises(TransientModelError) as captured:
        client.complete(request().model_copy(update={"attempt_limit": 1}))

    assert captured.value.retry_count == 0
    assert len(transport.payloads) == 1


def test_invalid_tool_arguments_fail_closed_without_retry() -> None:
    response = response_with_tool_call()
    response.choices[0].message.tool_calls[0].function.arguments = "not-json"
    transport = ScriptedTransport([response, response_with_tool_call()])
    client = ModelClient(config(), transport=transport)

    with pytest.raises(ModelProtocolError, match="invalid chat completion"):
        client.complete(request())

    assert len(transport.payloads) == 1


def test_required_tool_choice_repairs_one_plain_text_response() -> None:
    message = SimpleNamespace(content="I think the workbook is fine.", tool_calls=[])
    response = SimpleNamespace(
        id="completion-text",
        model="test-model",
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3, total_tokens=8),
    )
    transport = ScriptedTransport([response, response_with_tool_call()])
    client = ModelClient(
        config(),
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0),
    )

    turn = client.complete(request())

    assert turn.tool_calls[0].name == "inspect_region"
    assert turn.retry_count == 1
    assert turn.usage.input_tokens == 17
    assert turn.usage.output_tokens == 10
    assert len(transport.payloads) == 2
    repaired_messages = transport.payloads[1]["messages"]
    assert repaired_messages[-2] == {
        "role": "assistant",
        "content": "I think the workbook is fine.",
    }
    assert "Call exactly one available function now" in repaired_messages[-1]["content"]


def test_required_tool_choice_fails_closed_after_bounded_protocol_repairs() -> None:
    message = SimpleNamespace(content="I think the workbook is fine.", tool_calls=[])
    response = SimpleNamespace(
        id="completion-text",
        model="test-model",
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        usage=None,
    )
    transport = ScriptedTransport([response, response])
    client = ModelClient(
        config(),
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0),
    )

    with pytest.raises(ModelProtocolError, match="required tool call") as captured:
        client.complete(request())

    assert captured.value.retry_count == 1
    assert len(transport.payloads) == 2


def test_empty_completion_is_retried_and_usage_is_preserved() -> None:
    empty = SimpleNamespace(
        id="completion-empty",
        model="test-model",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, tool_calls=[]),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=0, total_tokens=5),
    )
    transport = ScriptedTransport([empty, response_with_tool_call()])
    client = ModelClient(
        config(),
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0),
    )

    turn = client.complete(request())

    assert turn.tool_calls[0].name == "inspect_region"
    assert turn.retry_count == 1
    assert turn.usage.input_tokens == 17
    assert turn.usage.output_tokens == 7
    repaired_messages = transport.payloads[1]["messages"]
    assert repaired_messages[-1]["role"] == "user"
    assert "did not contain a required function call" in repaired_messages[-1]["content"]


def test_repeated_empty_completion_exhausts_bounded_retries() -> None:
    empty = SimpleNamespace(
        id="completion-empty",
        model="test-model",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, tool_calls=[]),
                finish_reason="stop",
            )
        ],
        usage=None,
    )
    transport = ScriptedTransport([empty, empty])
    client = ModelClient(
        config(),
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0),
    )

    with pytest.raises(TransientModelError, match="no observable output") as captured:
        client.complete(request())

    assert captured.value.status_code == 503
    assert captured.value.retry_count == 1
    assert len(transport.payloads) == 2


def test_empty_choice_list_is_retried() -> None:
    empty = SimpleNamespace(
        id="completion-empty-choices",
        model="test-model",
        choices=[],
        usage=SimpleNamespace(prompt_tokens=4, completion_tokens=0, total_tokens=4),
    )
    transport = ScriptedTransport([empty, response_with_tool_call()])
    client = ModelClient(
        config(),
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0),
    )

    turn = client.complete(request())

    assert turn.tool_calls[0].name == "inspect_region"
    assert turn.retry_count == 1
    assert turn.usage.input_tokens == 16
    assert len(transport.payloads) == 2


def test_named_and_nonparallel_tool_contracts_are_enforced() -> None:
    named_request = request().model_copy(
        update={"tool_choice": NamedToolChoice(name="inspect_region")}
    )
    wrong = response_with_tool_call()
    wrong.choices[0].message.tool_calls[0].function.name = "other_tool"
    client = ModelClient(config(), transport=ScriptedTransport([wrong]))
    with pytest.raises(ModelProtocolError, match="named tool choice"):
        client.complete(named_request)

    duplicate = response_with_tool_call()
    second = SimpleNamespace(
        id="call-2",
        type="function",
        function=SimpleNamespace(name="inspect_region", arguments='{"sheet":"Other"}'),
    )
    duplicate.choices[0].message.tool_calls.append(second)
    transport = ScriptedTransport([duplicate, response_with_tool_call()])
    client = ModelClient(config(), transport=transport)
    repaired = client.complete(request())
    assert [call.call_id for call in repaired.tool_calls] == ["call-1"]
    assert repaired.retry_count == 1
    assert "multiple function calls" in transport.payloads[1]["messages"][-1]["content"]

    allowed = response_with_tool_call()
    allowed.choices[0].message.tool_calls.append(second)
    client = ModelClient(config(), transport=ScriptedTransport([allowed]))
    turn = client.complete(request().model_copy(update={"parallel_tool_calls": True}))
    assert [call.call_id for call in turn.tool_calls] == ["call-1", "call-2"]


def test_undeclared_tool_call_is_rejected_even_when_tool_use_is_required() -> None:
    response = response_with_tool_call()
    response.choices[0].message.tool_calls[0].function.name = "undeclared_tool"
    client = ModelClient(config(), transport=ScriptedTransport([response]))

    with pytest.raises(ModelProtocolError, match="undeclared tool calls: undeclared_tool"):
        client.complete(request())


def test_minimum_request_interval_paces_shared_provider_calls() -> None:
    transport = ScriptedTransport([response_with_tool_call(), response_with_tool_call()])
    now = [0.0]
    delays: list[float] = []

    def sleep(delay: float) -> None:
        delays.append(delay)
        now[0] += delay

    paced_config = OpenAICompatibleConfig(
        base_url="https://example.invalid/v1",
        model="test-model",
        api_key="secret",
        min_request_interval_seconds=2.0,
    )
    client = ModelClient(
        paced_config,
        transport=transport,
        sleeper=sleep,
        clock=lambda: now[0],
    )

    client.complete(request())
    client.complete(request())

    assert delays == [2.0]


def test_model_client_context_closes_transport_once() -> None:
    transport = ClosableTransport([response_with_tool_call()])
    client = ModelClient(config(), transport=transport)

    with client:
        client.complete(request())
    client.close()

    assert transport.close_calls == 1
    with pytest.raises(RuntimeError, match="closed"):
        client.complete(request())
