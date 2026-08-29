from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from formulawitness import agentic
from formulawitness.agent_budget import AgentRuntimeLimits
from formulawitness.agentic import approve_agentic_proposal, run_agentic, run_agentic_baseline
from formulawitness.ooxml import changed_workbook_formulas, sha256_file
from formulawitness.trace import object_hash, verify_trajectory
from tests.integration.test_agentic_runtime import (
    MUTANT,
    POLICY,
    REFERENCE,
    InvestigatorFalsifierScript,
    SingleAgentScript,
)


def _proposal(tmp_path: Path) -> tuple[Path, Path, str, dict[str, Any]]:
    workbook = tmp_path / "source.xlsx"
    workbook.write_bytes(MUTANT.read_bytes())
    artifacts = tmp_path / "artifacts"
    result = run_agentic(
        workbook,
        POLICY,
        artifacts,
        model=InvestigatorFalsifierScript(),
        model_id="scripted-approval-hardening",
        run_id="agent-approval-hardening",
    )
    proposal_path = artifacts / result.run_id / "proposal.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    return workbook, artifacts, result.run_id, proposal


def _approve(
    workbook: Path,
    artifacts: Path,
    run_id: str,
    proposal: dict[str, Any],
    *,
    reviewer: str = "reviewer@example.test",
) -> Any:
    return approve_agentic_proposal(
        workbook,
        POLICY,
        artifacts,
        run_id,
        reviewer=reviewer,
        expected_proposal_hash=object_hash(proposal),
    )


def test_approval_rejects_unsafe_run_identifier(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="identifier"):
        approve_agentic_proposal(
            MUTANT,
            POLICY,
            tmp_path,
            "../outside",
            reviewer="reviewer@example.test",
            expected_proposal_hash="0" * 64,
        )


def test_single_agent_receives_the_same_aggregate_turn_budget(tmp_path: Path) -> None:
    limits = AgentRuntimeLimits(
        manager_turn_limit=2,
        falsifier_turn_limit=3,
        model_call_limit=8,
        tool_call_limit=8,
        input_token_limit=1_000,
        output_token_limit=1_000,
        workbook_execution_limit=3,
        retry_limit=1,
        elapsed_time_limit_seconds=30,
    )
    result = run_agentic_baseline(
        MUTANT,
        POLICY,
        tmp_path,
        model=SingleAgentScript(),
        model_id="scripted-budget-comparison",
        limits=limits,
        run_id="single-agent-aggregate-budget",
    )

    assert result.decision == "REPAIR"
    assert result.budget["manager_turn_limit"] == 5
    assert result.budget["falsifier_turn_limit"] == 0
    assert result.budget["model_call_limit"] == limits.model_call_limit


def test_approval_revalidates_persisted_agent_state(tmp_path: Path) -> None:
    workbook, artifacts, run_id, proposal = _proposal(tmp_path)
    state_path = artifacts / run_id / "agent-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["decision"]["explanation"] = "A different decision was inserted after the run."
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="state"):
        _approve(workbook, artifacts, run_id, proposal)


def test_approval_rejects_stale_falsifier_evidence_even_when_rehashed(tmp_path: Path) -> None:
    workbook, artifacts, run_id, proposal = _proposal(tmp_path)
    state_path = artifacts / run_id / "agent-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    experiment = state["experiments"]["falsifier-tested-revision"]
    experiment["proposal_id"] = "proposal-0000000000000000"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    proposal["agent_state_hash"] = object_hash(state)
    (artifacts / run_id / "proposal.json").write_text(json.dumps(proposal), encoding="utf-8")

    with pytest.raises(ValueError, match="stale candidate"):
        _approve(workbook, artifacts, run_id, proposal)


def test_approval_uses_snapshot_and_recovers_uncommitted_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook, artifacts, run_id, proposal = _proposal(tmp_path)
    run_dir = artifacts / run_id
    output = run_dir / "repaired.xlsx"
    output.write_bytes(b"uncommitted orphan")
    original_patch = agentic.patch_workbook
    snapshot_paths: list[Path] = []

    def mutate_live_source(source: Path, *args: Any, **kwargs: Any) -> None:
        snapshot_paths.append(source)
        assert source.resolve() != workbook.resolve()
        workbook.write_bytes(REFERENCE.read_bytes())
        original_patch(source, *args, **kwargs)

    monkeypatch.setattr(agentic, "patch_workbook", mutate_live_source)
    approved = _approve(workbook, artifacts, run_id, proposal)

    assert snapshot_paths and snapshot_paths[0].name.startswith(".source-snapshot-")
    assert approved.source_sha256 == proposal["source_sha256"]
    assert hashlib.sha256(workbook.read_bytes()).hexdigest() != approved.source_sha256
    assert output.read_bytes() != b"uncommitted orphan"
    assert changed_workbook_formulas(MUTANT, output) == {
        "RebateCalc!P6": (
            proposal["result"]["patches"][0]["old_formula"],
            proposal["result"]["patches"][0]["new_formula"],
        )
    }
    manifest = json.loads((run_dir / "approval.json").read_text(encoding="utf-8"))
    assert manifest["repaired_sha256"] == sha256_file(output)
    assert manifest["trajectory"] == verify_trajectory(run_dir / "trajectory.jsonl")


def test_approval_manifest_last_allows_retry_after_commit_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook, artifacts, run_id, proposal = _proposal(tmp_path)
    run_dir = artifacts / run_id
    original_write_json = agentic.write_json
    failed = False

    def fail_commit_marker(path: Path, payload: Any) -> None:
        nonlocal failed
        if path.name == "approval.json" and not failed:
            failed = True
            raise OSError("simulated commit-marker interruption")
        original_write_json(path, payload)

    monkeypatch.setattr(agentic, "write_json", fail_commit_marker)
    with pytest.raises(OSError, match="commit-marker"):
        _approve(workbook, artifacts, run_id, proposal)
    assert (run_dir / "repaired.xlsx").is_file()
    assert not (run_dir / "approval.json").exists()

    monkeypatch.setattr(agentic, "write_json", original_write_json)
    approved = _approve(workbook, artifacts, run_id, proposal)
    assert approved.approval_hash
    assert (run_dir / "approval.json").is_file()


def test_concurrent_approval_has_one_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook, artifacts, run_id, proposal = _proposal(tmp_path)
    original_patch = agentic.patch_workbook
    started = threading.Event()
    release = threading.Event()

    def slow_patch(*args: Any, **kwargs: Any) -> None:
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("approval race test did not release the winner")
        original_patch(*args, **kwargs)

    monkeypatch.setattr(agentic, "patch_workbook", slow_patch)
    with ThreadPoolExecutor(max_workers=2) as executor:
        winner = executor.submit(
            _approve,
            workbook,
            artifacts,
            run_id,
            proposal,
            reviewer="first-reviewer@example.test",
        )
        assert started.wait(timeout=5)
        loser = executor.submit(
            _approve,
            workbook,
            artifacts,
            run_id,
            proposal,
            reviewer="second-reviewer@example.test",
        )
        with pytest.raises(ValueError, match="already in progress"):
            loser.result(timeout=5)
        release.set()
        approved = winner.result(timeout=10)

    manifest = json.loads((artifacts / run_id / "approval.json").read_text(encoding="utf-8"))
    assert approved.approval_hash == manifest["approval_hash"]
    assert manifest["actor"] == "first-reviewer@example.test"
