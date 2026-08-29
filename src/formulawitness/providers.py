"""Explicit model-provider presets and provider-neutral client construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .anthropic_transport import AnthropicTransport
from .model_client import ModelClient, ModelTransport, OpenAICompatibleConfig, RetryPolicy

TransportKind = Literal["openai-compatible", "anthropic"]


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
        retry_policy=RetryPolicy(
            max_attempts=4,
            base_delay_seconds=5.0,
            max_delay_seconds=30.0,
        ),
    )
    return client, preset.canonical_name
