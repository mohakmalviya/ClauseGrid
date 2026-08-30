"""Explicit model-provider presets and provider-neutral client construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .agent_types import ModelRequestSettings
from .anthropic_transport import AnthropicTransport
from .model_client import ModelClient, ModelTransport, OpenAICompatibleConfig, RetryPolicy

TransportKind = Literal["openai-compatible", "anthropic"]

NVIDIA_LIGHTNING_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
QUBRID_DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3.2"
DEEPSEEK_V4_MODEL_PREFIX = "deepseek-v4-"


@dataclass(frozen=True)
class ProviderPreset:
    canonical_name: str
    base_url: str | None
    api_key_env: str | None
    transport: TransportKind
    min_request_interval_seconds: float = 0.0


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        "openai", "https://api.openai.com/v1", "OPENAI_API_KEY", "openai-compatible"
    ),
    "anthropic": ProviderPreset(
        "anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY", "anthropic"
    ),
    "claude": ProviderPreset(
        "anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY", "anthropic"
    ),
    "deepseek": ProviderPreset(
        "deepseek", "https://api.deepseek.com", "DEEPSEEK_API_KEY", "openai-compatible"
    ),
    "nvidia-nim": ProviderPreset(
        "nvidia-nim",
        "https://integrate.api.nvidia.com/v1",
        "NVIDIA_NIM_API_KEY",
        "openai-compatible",
        1.6,
    ),
    "opencode": ProviderPreset(
        "opencode",
        "https://opencode.ai/zen/v1",
        "OPENCODE_API_KEY",
        "openai-compatible",
    ),
    "qubrid": ProviderPreset(
        "qubrid",
        "https://platform.qubrid.com/v1",
        "QUBRID_API_KEY",
        "openai-compatible",
    ),
    "openrouter": ProviderPreset(
        "openrouter",
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
        "openai-compatible",
    ),
    "groq": ProviderPreset(
        "groq",
        "https://api.groq.com/openai/v1",
        "GROQ_API_KEY",
        "openai-compatible",
    ),
    "together": ProviderPreset(
        "together",
        "https://api.together.ai/v1",
        "TOGETHER_API_KEY",
        "openai-compatible",
    ),
    "gemini": ProviderPreset(
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "GEMINI_API_KEY",
        "openai-compatible",
    ),
    "mistral": ProviderPreset(
        "mistral",
        "https://api.mistral.ai/v1",
        "MISTRAL_API_KEY",
        "openai-compatible",
    ),
    "xai": ProviderPreset(
        "xai",
        "https://api.x.ai/v1",
        "XAI_API_KEY",
        "openai-compatible",
    ),
    "openai-compatible": ProviderPreset("openai-compatible", None, None, "openai-compatible"),
}


def build_model_client(
    *,
    provider: str,
    model: str,
    base_url: str | None,
    api_key_env: str | None,
) -> tuple[ModelClient, str]:
    preset = PROVIDER_PRESETS[provider]
    resolved_base_url = base_url or preset.base_url
    resolved_api_key_env = api_key_env or preset.api_key_env
    if resolved_base_url is None:
        raise ValueError("--base-url is required for --provider openai-compatible")
    if resolved_api_key_env is None:
        raise ValueError("--api-key-env is required for --provider openai-compatible")
    config = OpenAICompatibleConfig.from_env(
        base_url=resolved_base_url,
        model=model,
        api_key_env=resolved_api_key_env,
        min_request_interval_seconds=preset.min_request_interval_seconds,
    )
    transport: ModelTransport | None
    if preset.transport == "anthropic":
        transport = AnthropicTransport(config)
    else:
        transport = None
    client = ModelClient(
        config,
        transport=transport,
        request_settings=_request_settings(preset.canonical_name, model),
        retry_policy=RetryPolicy(
            max_attempts=4,
            base_delay_seconds=5.0,
            max_delay_seconds=30.0,
        ),
    )
    return client, preset.canonical_name


def _request_settings(provider: str, model: str) -> ModelRequestSettings:
    """Apply documented model settings without changing other provider/model pairs."""

    if provider == "deepseek" and model.startswith(DEEPSEEK_V4_MODEL_PREFIX):
        # DeepSeek V4 enables thinking by default, but its Chat Completions thinking
        # mode rejects the named tool_choice used for ClauseGrid's terminal actions.
        # Non-thinking mode supports forced named tools and needs no hidden-reasoning
        # replay between tool turns.
        return ModelRequestSettings(
            parallel_tool_calls=False,
            extra_body={"thinking": {"type": "disabled"}},
        )
    if provider == "nvidia-nim" and model == NVIDIA_LIGHTNING_MODEL:
        return ModelRequestSettings(
            temperature=1.0,
            top_p=0.95,
            parallel_tool_calls=False,
            extra_body={
                "chat_template_kwargs": {"enable_thinking": True},
                "reasoning_budget": 2_048,
            },
        )
    if provider == "qubrid" and model == QUBRID_DEFAULT_MODEL:
        return ModelRequestSettings(
            temperature=1.0,
            top_p=0.95,
            parallel_tool_calls=False,
        )
    return ModelRequestSettings()
