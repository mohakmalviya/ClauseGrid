from pathlib import Path

from formulawitness.advanced import run_advanced
from formulawitness.baseline import run_baseline
from formulawitness.evaluation import sealed_semantic_check
from formulawitness.ooxml import changed_core_formulas, sha256_file
from formulawitness.policy import CORE_OUTPUTS

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
    assert sealed_semantic_check(source)[0] is False


def test_hard_case_requires_three_minimal_formula_changes(tmp_path: Path) -> None:
    source = ROOT / "workbooks/hard/H01_supplier_rebate.xlsx"
    result = run_advanced(source, POLICY, tmp_path, reviewer="test-reviewer")
    repaired = Path(result.output_workbook or "")
    assert result.decision == "REPAIR"
    assert {patch.cell for patch in result.patches} == {"N6", "P6", "S6"}
    assert sealed_semantic_check(repaired) == (True, 48, None)
