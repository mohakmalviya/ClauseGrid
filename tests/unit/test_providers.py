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


def test_missing_preset_key_names_the_expected_environment_variable() -> None:
    with pytest.raises(ModelConfigurationError, match="DEEPSEEK_API_KEY"):
        providers.build_model_client(
            provider="deepseek",
            model="deepseek-chat",
            base_url=None,
            api_key_env=None,
        )
