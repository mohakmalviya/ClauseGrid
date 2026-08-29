from __future__ import annotations

import json
from pathlib import Path

import pytest

from formulawitness.trace import Trajectory, verify_trajectory


def test_verifier_rejects_unhashed_unknown_event_fields(tmp_path: Path) -> None:
    path = tmp_path / "trajectory.jsonl"
    trace = Trajectory(path, "agent-trace-hardening")
    trace.record_agent_event(
        "controller",
        "FINAL_STATE",
        {"decision": "ABSTAIN"},
        model_id="test-model",
        prompt_version="test-v1",
    )
    event = json.loads(path.read_text(encoding="utf-8"))
    event["unhashed_approval"] = True
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown"):
        verify_trajectory(path)
