from __future__ import annotations

import pytest

from formulawitness.deploy import _deployment_args
from formulawitness.providers import QUBRID_DEFAULT_MODEL


def test_deployment_args_use_render_origin_and_qubrid_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FORMULAWITNESS_PUBLIC_ORIGIN", raising=False)
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://formulawitness.example")
    monkeypatch.setenv("PORT", "12345")

    args = _deployment_args()

    assert args[:5] == ["serve", "--host", "0.0.0.0", "--port", "12345"]
    assert args[args.index("--public-origin") + 1] == "https://formulawitness.example"
    assert args[args.index("--provider") + 1] == "qubrid"
    assert args[args.index("--model") + 1] == QUBRID_DEFAULT_MODEL
    assert "--allow-external-processing" in args
    assert all("KEY" not in item and "TOKEN" not in item for item in args)


def test_deployment_args_require_origin_and_positive_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FORMULAWITNESS_PUBLIC_ORIGIN", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    with pytest.raises(SystemExit, match="PUBLIC_ORIGIN"):
        _deployment_args()

    monkeypatch.setenv("FORMULAWITNESS_PUBLIC_ORIGIN", "https://demo.example")
    monkeypatch.setenv("FORMULAWITNESS_MAX_AUDITS_PER_HOUR", "0")
    with pytest.raises(SystemExit, match="positive"):
        _deployment_args()
