from __future__ import annotations

import pytest

from formulawitness import providers
from formulawitness.anthropic_transport import AnthropicTransport
from formulawitness.model_client import ModelConfigurationError, OpenAITransport


@pytest.mark.parametrize(
    ("provider", "env_name", "expected_provider", "transport_type"),
    (
        ("openai", "OPENAI_API_KEY", "openai", OpenAITransport),
        ("anthropic", "ANTHROPIC_API_KEY", "anthropic", AnthropicTransport),
        ("claude", "ANTHROPIC_API_KEY", "anthropic", AnthropicTransport),
        ("deepseek", "DEEPSEEK_API_KEY", "deepseek", OpenAITransport),
        ("nvidia-nim", "NVIDIA_NIM_API_KEY", "nvidia-nim", OpenAITransport),
        ("opencode", "OPENCODE_API_KEY", "opencode", OpenAITransport),
        ("qubrid", "QUBRID_API_KEY", "qubrid", OpenAITransport),
        ("openrouter", "OPENROUTER_API_KEY", "openrouter", OpenAITransport),
        ("groq", "GROQ_API_KEY", "groq", OpenAITransport),
        ("together", "TOGETHER_API_KEY", "together", OpenAITransport),
        ("gemini", "GEMINI_API_KEY", "gemini", OpenAITransport),
        ("mistral", "MISTRAL_API_KEY", "mistral", OpenAITransport),
        ("xai", "XAI_API_KEY", "xai", OpenAITransport),
    ),
)
def test_provider_presets_load_their_own_environment_key(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    env_name: str,
    expected_provider: str,
    transport_type: type[object],
) -> None:
    monkeypatch.setenv(env_name, "provider-secret")

    client, canonical = providers.build_model_client(
        provider=provider,
        model="provider/model-id",
        base_url=None,
        api_key_env=None,
    )
    try:
        assert canonical == expected_provider
        assert isinstance(client._transport, transport_type)
        assert client.config.model == "provider/model-id"
    finally:
        client.close()


def test_generic_provider_requires_explicit_endpoint_and_key_name() -> None:
    with pytest.raises(ValueError, match="--base-url"):
        providers.build_model_client(
            provider="openai-compatible",
            model="local-model",
            base_url=None,
            api_key_env=None,
        )

    with pytest.raises(ValueError, match="--api-key-env"):
        providers.build_model_client(
            provider="openai-compatible",
            model="local-model",
            base_url="http://127.0.0.1:9000/v1",
            api_key_env=None,
        )


def test_preset_accepts_a_generic_deployment_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUSEGRID_API_KEY", "generic-provider-secret")

    client, canonical = providers.build_model_client(
        provider="anthropic",
        model="claude-model-id",
        base_url=None,
        api_key_env="CLAUSEGRID_API_KEY",
    )
    try:
        assert canonical == "anthropic"
        assert isinstance(client._transport, AnthropicTransport)
        assert client.config.api_key.get_secret_value() == "generic-provider-secret"
    finally:
        client.close()


def test_missing_preset_key_names_the_expected_environment_variable() -> None:
    with pytest.raises(ModelConfigurationError, match="DEEPSEEK_API_KEY"):
        providers.build_model_client(
            provider="deepseek",
            model="deepseek-chat",
            base_url=None,
            api_key_env=None,
        )


def test_opencode_uses_official_zen_chat_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_API_KEY", "provider-secret")

    client, canonical = providers.build_model_client(
        provider="opencode",
        model="big-pickle",
        base_url=None,
        api_key_env=None,
    )
    try:
        assert canonical == "opencode"
        assert client.config.base_url == "https://opencode.ai/zen/v1"
        assert client.config.model == "big-pickle"
    finally:
        client.close()


def test_nvidia_lightning_uses_its_documented_agent_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "provider-secret")

    client, canonical = providers.build_model_client(
        provider="nvidia-nim",
        model=providers.NVIDIA_LIGHTNING_MODEL,
        base_url=None,
        api_key_env=None,
    )
    try:
        assert canonical == "nvidia-nim"
        assert client.request_settings.temperature == 1.0
        assert client.request_settings.top_p == 0.95
        assert client.request_settings.parallel_tool_calls is False
        assert client.request_settings.extra_body == {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": 2_048,
        }
    finally:
        client.close()


def test_qubrid_default_uses_catalog_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUBRID_API_KEY", "provider-secret")

    client, canonical = providers.build_model_client(
        provider="qubrid",
        model=providers.QUBRID_DEFAULT_MODEL,
        base_url=None,
        api_key_env=None,
    )
    try:
        assert canonical == "qubrid"
        assert client.config.base_url == "https://platform.qubrid.com/v1"
        assert client.request_settings.temperature == 1.0
        assert client.request_settings.top_p == 0.95
        assert client.request_settings.parallel_tool_calls is False
        assert client.request_settings.extra_body == {}
    finally:
        client.close()
