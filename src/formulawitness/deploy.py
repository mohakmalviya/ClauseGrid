"""Environment-only production entry point for the public ClauseGrid demonstration."""

from __future__ import annotations

import os
from pathlib import Path

from .cli import main as cli_main
from .providers import QUBRID_DEFAULT_MODEL


def _environment(primary: str, legacy: str | None = None, default: str | None = None) -> str | None:
    """Read current branding first while preserving existing deployment variables."""

    value = os.environ.get(primary)
    if value is None and legacy is not None:
        value = os.environ.get(legacy)
    if value is None:
        value = default
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _positive_int(primary: str, legacy: str | None, default: int) -> int:
    raw = _environment(primary, legacy, str(default))
    assert raw is not None
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{primary} must be an integer") from exc
    if value < 1:
        raise SystemExit(f"{primary} must be positive")
    return value


def _boolean(primary: str, legacy: str | None, default: bool = False) -> bool:
    raw = _environment(primary, legacy, "true" if default else "false")
    assert raw is not None
    normalized = raw.casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise SystemExit(f"{primary} must be true or false")


def _deployment_args() -> list[str]:
    """Build the public-server arguments entirely from non-secret environment metadata."""

    origin = _environment(
        "CLAUSEGRID_PUBLIC_ORIGIN", "FORMULAWITNESS_PUBLIC_ORIGIN"
    ) or _environment("RENDER_EXTERNAL_URL")
    if not origin:
        raise SystemExit("CLAUSEGRID_PUBLIC_ORIGIN is required")
    provider = _environment("CLAUSEGRID_PROVIDER", "FORMULAWITNESS_PROVIDER", "qubrid")
    model = _environment("CLAUSEGRID_MODEL", "FORMULAWITNESS_MODEL", QUBRID_DEFAULT_MODEL)
    assert provider is not None and model is not None
    base_url = _environment("CLAUSEGRID_BASE_URL", "FORMULAWITNESS_BASE_URL")
    explicit_key_env = _environment("CLAUSEGRID_API_KEY_ENV", "FORMULAWITNESS_API_KEY_ENV")
    generic_key_env = "CLAUSEGRID_API_KEY" if _environment("CLAUSEGRID_API_KEY") else None
    api_key_env = explicit_key_env or generic_key_env
    admin_token_env = "CLAUSEGRID_ADMIN_TOKEN" if _environment("CLAUSEGRID_ADMIN_TOKEN") else None
    port = _positive_int("PORT", None, 10_000)
    artifact_value = _environment(
        "CLAUSEGRID_ARTIFACT_ROOT", "FORMULAWITNESS_ARTIFACT_ROOT", "/tmp/clausegrid"
    )
    assert artifact_value is not None
    artifacts = Path(artifact_value)
    max_global = _positive_int(
        "CLAUSEGRID_MAX_AUDITS_PER_HOUR", "FORMULAWITNESS_MAX_AUDITS_PER_HOUR", 6
    )
    max_client = _positive_int(
        "CLAUSEGRID_MAX_AUDITS_PER_CLIENT_HOUR",
        "FORMULAWITNESS_MAX_AUDITS_PER_CLIENT_HOUR",
        2,
    )
    public_uploads = _boolean(
        "CLAUSEGRID_ENABLE_PUBLIC_UPLOADS",
        "FORMULAWITNESS_ENABLE_PUBLIC_UPLOADS",
    )
    args = [
        "serve",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        "--artifacts",
        str(artifacts),
        "--public-origin",
        origin,
        "--max-audits-per-hour",
        str(max_global),
        "--max-audits-per-client-hour",
        str(max_client),
        "--provider",
        provider,
        "--model",
        model,
        "--allow-external-processing",
    ]
    if base_url:
        args.extend(["--base-url", base_url])
    if api_key_env:
        args.extend(["--api-key-env", api_key_env])
    if admin_token_env:
        args.extend(["--admin-token-env", admin_token_env])
    if public_uploads:
        args.append("--enable-public-uploads")
    return args


def main() -> int:
    """Start the public server without accepting credentials in process arguments."""

    return cli_main(_deployment_args())


if __name__ == "__main__":
    raise SystemExit(main())
