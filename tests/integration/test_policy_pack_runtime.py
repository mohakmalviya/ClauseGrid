import shutil
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

import formulawitness.policy_oracle as policy_oracle_module
import formulawitness.policy_pack_runtime as policy_pack_runtime_module
from formulawitness.models import ExecutionResult
from formulawitness.ooxml import calculation_cells, patch_workbook
from formulawitness.policy_pack import materialize_policy_pack
from formulawitness.policy_pack_runtime import verify_with_policy_pack
from formulawitness.trace import object_hash

ROOT = Path(__file__).resolve().parents[2]


def test_approved_pack_repeatedly_verifies_without_any_model_call() -> None:
    pack = materialize_policy_pack(ROOT)
    workbook = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"

    first = verify_with_policy_pack(workbook, pack)
    second = verify_with_policy_pack(workbook, pack)

    assert first["decision"] == "PASS"
    assert first["model_calls"] == 0
    assert first["model_required"] is False
    assert first["complete"] is True
    assert first["test_count"] == len(pack.tests)
    assert first["evidence_hash"] == second["evidence_hash"]
    assert first["run_id"] == second["run_id"]


def test_evidence_hash_binds_every_displayed_verdict_field() -> None:
    pack = materialize_policy_pack(ROOT)
    workbook = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    result = verify_with_policy_pack(workbook, pack)
    evidence_payload = {
        key: value for key, value in result.items() if key not in {"evidence_hash", "run_id"}
    }

    assert result["evidence_hash"] == object_hash(evidence_payload)
    verdict_fields = (
        "decision",
        "complete",
        "test_count",
        "passed_count",
        "failed_count",
        "error_count",
        "skipped_count",
        "failed_case_ids",
        "error_case_ids",
        "affected_rule_ids",
        "execution_mode",
        "model_calls",
        "model_required",
        "source_immutable",
    )
    for field in verdict_fields:
        tampered = deepcopy(evidence_payload)
        value = tampered[field]
        if isinstance(value, bool):
            tampered[field] = not value
        elif isinstance(value, int):
            tampered[field] = value + 1
        elif isinstance(value, str):
            tampered[field] = f"{value}-tampered"
        else:
            tampered[field] = [*value, "tampered"]
        assert object_hash(tampered) != result["evidence_hash"], field


def test_approved_suite_detects_every_public_formula_mutant() -> None:
    pack = materialize_policy_pack(ROOT)

    for index in range(1, 13):
        workbook = ROOT / f"workbooks/mutants/M{index:02d}_supplier_rebate.xlsx"
        result = verify_with_policy_pack(workbook, pack)
        assert result["decision"] == "FAIL", f"M{index:02d} escaped the approved suite"
        assert result["failed_count"] > 0


def test_approved_suite_preserves_every_clean_control_and_detects_hard_case() -> None:
    pack = materialize_policy_pack(ROOT)

    for index in range(1, 4):
        workbook = ROOT / f"workbooks/controls/C{index:02d}_supplier_rebate.xlsx"
        result = verify_with_policy_pack(workbook, pack)
        assert result["decision"] == "PASS", f"C{index:02d} is a false positive"
    hard = verify_with_policy_pack(ROOT / "workbooks/hard/H01_supplier_rebate.xlsx", pack)
    assert hard["decision"] == "FAIL"


def test_approved_suite_activates_floor_date_and_cap_constraints(tmp_path: Path) -> None:
    pack = materialize_policy_pack(ROOT)
    source = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    _, formulas = calculation_cells(source)
    mutations = {
        "floor-removed.xlsx": (
            "L6",
            "=E6-F6-G6",
            "INCONCLUSIVE",
            "GEN-ELIGIBLE-FLOOR",
        ),
        "day-floor-removed.xlsx": (
            "M6",
            "=C6-MAX(B6,D6)+1",
            "FAIL",
            "GEN-PRORATION-ZERO",
        ),
        "cap-removed.xlsx": ("S6", "=ROUND(R6,2)", "FAIL", "GEN-CAP-ACTIVE"),
    }

    for filename, (cell, replacement, expected_decision, required_case) in mutations.items():
        mutant = tmp_path / filename
        patch_workbook(
            source,
            mutant,
            {cell: (formulas[cell], replacement)},
            [],
            [],
        )
        result = verify_with_policy_pack(mutant, pack)
        assert result["decision"] == expected_decision
        case_ids = (
            result["error_case_ids"]
            if expected_decision == "INCONCLUSIVE"
            else result["failed_case_ids"]
        )
        assert required_case in case_ids
        if expected_decision == "INCONCLUSIVE":
            assert result["affected_rule_ids"] == []


def test_observed_violation_takes_precedence_over_incomplete_coverage(tmp_path: Path) -> None:
    pack = materialize_policy_pack(ROOT)
    source = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    _, formulas = calculation_cells(source)
    mixed = tmp_path / "violation-and-execution-gap.xlsx"
    patch_workbook(
        source,
        mixed,
        {"L6": (formulas["L6"], "=E6-F6-G6")},
        [],
        [],
    )

    result = verify_with_policy_pack(mixed, pack)

    assert result["decision"] == "FAIL"
    assert result["complete"] is False
    assert result["failed_count"] > 0
    assert result["error_count"] > 0


@pytest.mark.parametrize("invalid_actual", [True, "1.0", float("nan"), float("inf"), -float("inf")])
def test_numeric_outputs_reject_wrong_types_and_nonfinite_values(
    monkeypatch: pytest.MonkeyPatch, invalid_actual: object
) -> None:
    pack = materialize_policy_pack(ROOT)
    workbook = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    original_execute_batch = policy_pack_runtime_module.execute_batch

    def corrupt_numeric_output(
        path: Path, inputs: list[dict[str, object]]
    ) -> list[ExecutionResult]:
        results = original_execute_batch(path, inputs)
        outputs = dict(results[0].outputs)
        outputs["Q6"] = invalid_actual
        results[0] = replace(results[0], outputs=outputs)
        return results

    monkeypatch.setattr(policy_pack_runtime_module, "execute_batch", corrupt_numeric_output)

    result = verify_with_policy_pack(workbook, pack)

    assert result["decision"] == "FAIL"
    assert "Q6" in result["records"][0]["mismatched_cells"]


def test_runtime_oracle_is_not_the_spreadsheet_formula_engine() -> None:
    source = Path(policy_oracle_module.__file__ or "").read_text(encoding="utf-8")

    assert "from .formula" not in source
    assert "evaluate_cells" not in source


def test_verification_fails_if_source_changes_during_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pack = materialize_policy_pack(ROOT)
    workbook = tmp_path / "source.xlsx"
    shutil.copy2(ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx", workbook)
    original_execute_batch = policy_pack_runtime_module.execute_batch

    def mutate_after_execution(
        path: Path, inputs: list[dict[str, object]]
    ) -> list[ExecutionResult]:
        result = original_execute_batch(path, inputs)
        workbook.write_bytes(workbook.read_bytes() + b"changed")
        return result

    monkeypatch.setattr(policy_pack_runtime_module, "execute_batch", mutate_after_execution)

    with pytest.raises(RuntimeError, match="changed during"):
        verify_with_policy_pack(workbook, pack)


def test_verification_rejects_wrong_worker_hash_and_reordered_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = materialize_policy_pack(ROOT)
    workbook = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    original_execute_batch = policy_pack_runtime_module.execute_batch

    def wrong_hash(path: Path, inputs: list[dict[str, object]]) -> list[ExecutionResult]:
        results = original_execute_batch(path, inputs)
        results[0] = replace(results[0], workbook_sha256="0" * 64)
        return results

    monkeypatch.setattr(policy_pack_runtime_module, "execute_batch", wrong_hash)
    with pytest.raises(RuntimeError, match="different source hash"):
        verify_with_policy_pack(workbook, pack)

    def reordered_inputs(path: Path, inputs: list[dict[str, object]]) -> list[ExecutionResult]:
        results = original_execute_batch(path, inputs)
        results[0] = replace(results[0], inputs=results[1].inputs)
        return results

    monkeypatch.setattr(policy_pack_runtime_module, "execute_batch", reordered_inputs)
    with pytest.raises(RuntimeError, match="reordered or altered"):
        verify_with_policy_pack(workbook, pack)


def test_verification_rejects_in_memory_pack_mutation() -> None:
    pack = materialize_policy_pack(ROOT)
    pack.tests[0].expected["S6"] = -1

    with pytest.raises(ValueError, match="changed after approval"):
        verify_with_policy_pack(
            ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx",
            pack,
        )
