import json
from pathlib import Path

import pytest

from formulawitness.trace import Trajectory, verify_trajectory


def test_trajectory_hash_chain_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "trajectory.jsonl"
    trace = Trajectory(path, "run-1")
    trace.record("rule-agent", "EXTRACT", {"a": 1}, {"b": 2})
    trace.record("repair-agent", "PROPOSE", {"b": 2}, {"c": 3})
    verified = verify_trajectory(path)
    assert verified["event_count"] == 2

    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    events[0]["output_hash"] = "0" * 64
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_trajectory(path)


def test_trajectory_hash_chain_covers_runtime_metadata_and_resume(tmp_path: Path) -> None:
    path = tmp_path / "trajectory.jsonl"
    trace = Trajectory(path, "run-1")
    trace.record("worker", "EXECUTE", {}, {}, elapsed_ms=17)

    event = json.loads(path.read_text(encoding="utf-8"))
    event["elapsed_ms"] = 18
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        verify_trajectory(path)
    with pytest.raises(ValueError, match="hash mismatch"):
        Trajectory(path, "run-1", resume=True)
