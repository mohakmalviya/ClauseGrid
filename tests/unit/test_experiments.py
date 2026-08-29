import ast
import hashlib
import subprocess
from pathlib import Path

import pytest

from formulawitness.models import FormulaOverride
from formulawitness.ooxml import formula_map, sha256_file
from formulawitness.runner import ExecutionFailed, _execute_request, execute_experiment

ROOT = Path(__file__).resolve().parents[2]
WORKBOOK = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"


def _formula_hash(formula: str) -> str:
    return hashlib.sha256(formula.encode("utf-8")).hexdigest()


def test_generic_experiment_uses_explicit_cells_without_policy_mappings() -> None:
    result = execute_experiment(
        WORKBOOK,
        sheet="RebateCalc",
        overrides={"E6": 123, "F6": 23, "G6": 0},
        observations=["L6", "E6"],
    )

    assert result.workbook_sha256 == sha256_file(WORKBOOK)
    assert result.sheet == "RebateCalc"
    assert result.observations == {"L6": 100, "E6": 123}
    assert result.dependencies["L6"] == ["E6", "F6", "G6"]
    assert result.applied_formula_overrides == ()


def test_formula_override_is_guarded_and_remains_sandbox_only() -> None:
    before_hash = sha256_file(WORKBOOK)
    source_formula = formula_map(WORKBOOK)["L6"]
    override = FormulaOverride("L6", _formula_hash(source_formula), "=E6+F6")

    result = execute_experiment(
        WORKBOOK,
        sheet="RebateCalc",
        overrides={"E6": 123, "F6": 23},
        observations=["L6"],
        formula_overrides=[override],
    )

    assert result.observations == {"L6": 146}
    assert result.applied_formula_overrides == ("L6",)
    assert sha256_file(WORKBOOK) == before_hash
    assert formula_map(WORKBOOK)["L6"] == source_formula


def test_formula_override_rejects_a_stale_old_formula_hash() -> None:
    with pytest.raises(ExecutionFailed, match="Old-formula hash guard failed"):
        execute_experiment(
            WORKBOOK,
            sheet="RebateCalc",
            overrides={},
            observations=["L6"],
            formula_overrides=[FormulaOverride("L6", "0" * 64, "=0")],
        )


def test_value_override_must_target_an_existing_non_formula_cell() -> None:
    with pytest.raises(ExecutionFailed, match="Value override target does not exist"):
        execute_experiment(
            WORKBOOK,
            sheet="RebateCalc",
            overrides={"A999": 1},
            observations=["L6"],
        )
    with pytest.raises(ExecutionFailed, match="cannot replace formula cell"):
        execute_experiment(
            WORKBOOK,
            sheet="RebateCalc",
            overrides={"L6": 1},
            observations=["L6"],
        )


def test_experiment_worker_has_no_policy_or_evaluator_imports() -> None:
    worker = ROOT / "src/formulawitness/experiment_worker.py"
    tree = ast.parse(worker.read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert not any(
        name.endswith(("policy", "public_benchmark", "evaluation")) or name.startswith("evals")
        for name in imports
    )


def test_worker_timeout_is_normalized_to_execution_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="worker", timeout=0.01)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ExecutionFailed, match="execution limit"):
        _execute_request(WORKBOOK, {"inputs": {}}, 0.01)
