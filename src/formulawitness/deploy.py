"""Environment-only production entry point for the public FormulaWitness demonstration."""

from __future__ import annotations

import os
from pathlib import Path

from .cli import main as cli_main
from .providers import QUBRID_DEFAULT_MODEL


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer") from exc
    if value < 1:
        raise SystemExit(f"{name} must be positive")
    return value


def _deployment_args() -> list[str]:
    """Build the public-server arguments entirely from non-secret environment metadata."""

    origin = os.environ.get("FORMULAWITNESS_PUBLIC_ORIGIN") or os.environ.get("RENDER_EXTERNAL_URL")
    if not origin:
        raise SystemExit("FORMULAWITNESS_PUBLIC_ORIGIN is required")
    provider = os.environ.get("FORMULAWITNESS_PROVIDER", "qubrid")
    model = os.environ.get("FORMULAWITNESS_MODEL", QUBRID_DEFAULT_MODEL)
    port = _positive_int("PORT", 10_000)
    artifacts = Path(os.environ.get("FORMULAWITNESS_ARTIFACT_ROOT", "/tmp/formulawitness"))
    max_global = _positive_int("FORMULAWITNESS_MAX_AUDITS_PER_HOUR", 6)
    max_client = _positive_int("FORMULAWITNESS_MAX_AUDITS_PER_CLIENT_HOUR", 2)
    return [
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


def main() -> int:
    """Start the public server without accepting credentials in process arguments."""

    return cli_main(_deployment_args())


if __name__ == "__main__":
    raise SystemExit(main())
