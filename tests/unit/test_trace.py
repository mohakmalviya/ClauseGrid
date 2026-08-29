import json
from pathlib import Path

import pytest

from formulawitness.trace import Trajectory, redact_secrets, verify_trajectory


def test_trajectory_hash_chain_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "trajectory.jsonl"
    trace = Trajectory(path, "run-1")
    trace.record(
        "rule-agent",
        "EXTRACT",
        {"a": 1},
        {"b": 2},
        instruction="Extract cited rules.",
        tool="policy.extract_rules",
        input_summary={"documents": 1},
        output_summary={"rules": 1},
        feedback="Continue to repair.",
    )
    trace.record(
        "repair-agent",
        "PROPOSE",
        {"b": 2},
        {"c": 3},
        instruction="Propose a minimal repair.",
        tool="repair.compile",
        input_summary={"rules": 1},
        output_summary={"patches": 1},
        feedback="Wait for approval.",
    )
    verified = verify_trajectory(path)
    assert verified["event_count"] == 2

    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert events[0]["schema_version"] == 2
    assert events[0]["instruction"] == "Extract cited rules."
    assert events[0]["tool"] == "policy.extract_rules"
    assert events[0]["output_summary"] == {"rules": 1}
    assert events[0]["feedback"] == "Continue to repair."
    assert events[0]["retry_count"] == 0
    events[0]["output_hash"] = "0" * 64
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_trajectory(path)


def test_trajectory_hash_chain_covers_runtime_metadata_and_resume(tmp_path: Path) -> None:
    path = tmp_path / "trajectory.jsonl"
    trace = Trajectory(path, "run-1")
    trace.record(
        "worker",
        "EXECUTE",
        {},
        {},
        instruction="Execute the visible cases.",
        tool="worker.execute_batch",
        input_summary={"cases": 0},
        output_summary={"passes": 0},
        feedback="Execution complete.",
        elapsed_ms=17,
    )

    event = json.loads(path.read_text(encoding="utf-8"))
    event["elapsed_ms"] = 18
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        verify_trajectory(path)
    with pytest.raises(ValueError, match="hash mismatch"):
        Trajectory(path, "run-1", resume=True)


def test_agent_trace_preserves_observable_cycle_and_redacts_credentials(tmp_path: Path) -> None:
    path = tmp_path / "trajectory.jsonl"
    trace = Trajectory(path, "agent-run")
    trace.record_agent_event(
        "audit-manager",
        "TOOL_CALL",
        {
            "tool_call": {"name": "list_sheets", "arguments": {}},
            "authorization": "Bearer should-never-appear",
            "observation": "Authorization: Bearer another-secret",
        },
        model_id="test-model",
        prompt_version="manager-v1",
        usage={"input_tokens": 10, "output_tokens": 4},
    )

    event = json.loads(path.read_text(encoding="utf-8"))
    assert event["schema_version"] == 3
    assert event["payload"]["tool_call"]["name"] == "list_sheets"
    assert event["payload"]["authorization"] == "[REDACTED]"
    assert "should-never-appear" not in path.read_text(encoding="utf-8")
    assert "another-secret" not in path.read_text(encoding="utf-8")
    assert verify_trajectory(path)["event_count"] == 1


def test_redact_secrets_does_not_remove_token_usage() -> None:
    assert redact_secrets({"output_tokens": 7, "api_key": "secret"}) == {
        "output_tokens": 7,
        "api_key": "[REDACTED]",
    }
