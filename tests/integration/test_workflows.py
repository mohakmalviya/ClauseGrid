import json
from pathlib import Path

import pytest

from formulawitness.advanced import approve_advanced_proposal, run_advanced
from formulawitness.baseline import run_baseline
from formulawitness.evaluation import sealed_semantic_check
from formulawitness.ooxml import changed_core_formulas, changed_workbook_formulas, sha256_file
from formulawitness.policy import CORE_OUTPUTS
from formulawitness.trace import object_hash

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "policies/supplier_rebate_sla_policy.pdf"


def test_advanced_repairs_waiver_scope_and_preserves_source(tmp_path: Path) -> None:
    source = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    source_hash = sha256_file(source)
    result = run_advanced(source, POLICY, tmp_path, reviewer="test-reviewer")
    repaired = Path(result.output_workbook or "")
    assert result.decision == "REPAIR"
    assert [patch.cell for patch in result.patches] == ["P6"]
    assert sha256_file(source) == source_hash
    assert sealed_semantic_check(repaired) == (True, 48, None)
    assert list(changed_core_formulas(source, repaired, CORE_OUTPUTS)) == ["P6"]
    assert list(changed_workbook_formulas(source, repaired)) == ["RebateCalc!P6"]


def test_advanced_preserves_clean_boundary_control(tmp_path: Path) -> None:
    source = ROOT / "workbooks/controls/C02_supplier_rebate.xlsx"
    result = run_advanced(source, POLICY, tmp_path, reviewer="test-reviewer")
    assert result.decision == "NO_CHANGE"
    assert result.patches == []
    assert Path(result.output_workbook or "") == source.resolve()


def test_direct_baseline_cannot_solve_cross_rule_waiver_scope(tmp_path: Path) -> None:
    source = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    result = run_baseline(source, POLICY, tmp_path, reviewer="test-reviewer")
    assert result.decision == "NO_CHANGE"
    assert len(result.tests) == 20
    assert result.budget["model_id"] == "deterministic-offline-v1"
    assert (
        result.budget["workbook_case_executions_used"]
        <= result.budget["workbook_case_execution_limit"]
    )
    assert sealed_semantic_check(source)[0] is False


def test_hard_case_requires_three_minimal_formula_changes(tmp_path: Path) -> None:
    source = ROOT / "workbooks/hard/H01_supplier_rebate.xlsx"
    result = run_advanced(source, POLICY, tmp_path, reviewer="test-reviewer")
    repaired = Path(result.output_workbook or "")
    assert result.decision == "REPAIR"
    assert {patch.cell for patch in result.patches} == {"N6", "P6", "S6"}
    assert sealed_semantic_check(repaired) == (True, 48, None)


def test_approval_applies_exact_frozen_proposal(tmp_path: Path) -> None:
    source = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    proposed = run_advanced(source, POLICY, tmp_path)
    proposal_path = Path(proposed.artifact_dir or "") / "proposal.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))

    approved = approve_advanced_proposal(
        source,
        POLICY,
        tmp_path,
        proposed.run_id,
        "test-reviewer",
        expected_proposal_hash=object_hash(proposal),
    )
    assert approved.approval_hash
    assert Path(approved.output_workbook or "").is_file()


def test_tampered_proposal_is_rejected_before_workbook_write(tmp_path: Path) -> None:
    source = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    proposed = run_advanced(source, POLICY, tmp_path)
    run_dir = Path(proposed.artifact_dir or "")
    proposal_path = run_dir / "proposal.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    reviewed_hash = object_hash(proposal)
    proposal["result"]["patches"][0]["new_formula"] = "=0"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

    with pytest.raises(ValueError, match="changed after review"):
        approve_advanced_proposal(
            source,
            POLICY,
            tmp_path,
            proposed.run_id,
            "test-reviewer",
            expected_proposal_hash=reviewed_hash,
        )
    assert not (run_dir / "repaired.xlsx").exists()


def test_rerun_preserves_existing_approved_artifacts_byte_for_byte(tmp_path: Path) -> None:
    source = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    first = run_advanced(source, POLICY, tmp_path, reviewer="first-reviewer")
    run_dir = Path(first.artifact_dir or "")
    before = {path.name: sha256_file(path) for path in run_dir.iterdir() if path.is_file()}

    second = run_advanced(source, POLICY, tmp_path, reviewer="different-reviewer")
    after = {path.name: sha256_file(path) for path in run_dir.iterdir() if path.is_file()}
    assert second.approval_hash == first.approval_hash
    assert before == after


def test_rerun_rejects_tampered_approved_workbook(tmp_path: Path) -> None:
    source = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    first = run_advanced(source, POLICY, tmp_path, reviewer="test-reviewer")
    repaired = Path(first.output_workbook or "")
    with repaired.open("ab") as stream:
        stream.write(b"tampered")

    with pytest.raises(ValueError, match="bindings no longer match"):
        run_advanced(source, POLICY, tmp_path, reviewer="test-reviewer")


def test_independent_approved_runs_are_byte_reproducible(tmp_path: Path) -> None:
    source = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    first = run_advanced(source, POLICY, tmp_path / "first", reviewer="same-reviewer")
    second = run_advanced(source, POLICY, tmp_path / "second", reviewer="same-reviewer")

    assert sha256_file(Path(first.output_workbook or "")) == sha256_file(
        Path(second.output_workbook or "")
    )
    assert first.approval_hash == second.approval_hash
