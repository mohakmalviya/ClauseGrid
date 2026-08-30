import ast
import hashlib
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from formulawitness.models import FormulaOverride
from formulawitness.ooxml import MAIN, formula_map, sha256_file
from formulawitness.runner import ExecutionFailed, _execute_request, execute_experiment

ROOT = Path(__file__).resolve().parents[2]
WORKBOOK = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"


def _formula_hash(formula: str) -> str:
    return hashlib.sha256(formula.encode("utf-8")).hexdigest()


def _self_qualified_dependency_workbook(tmp_path: Path) -> Path:
    target = tmp_path / "self-qualified.xlsx"
    changed = False
    with ZipFile(WORKBOOK) as source, ZipFile(target, "w", ZIP_DEFLATED) as output:
        for info in source.infolist():
            payload = source.read(info)
            if not changed and info.filename.startswith("xl/worksheets/"):
                root = ET.fromstring(payload)
                for cell in root.findall(".//x:c", {"x": MAIN}):
                    formula = cell.find("x:f", {"x": MAIN})
                    if cell.attrib.get("r") == "M6" and formula is not None:
                        formula.text = "RebateCalc!L6+1"
                        payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                        changed = True
                        break
            output.writestr(info, payload)
    assert changed
    return target


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


def test_generic_experiment_round_trips_a_tagged_date_override() -> None:
    result = execute_experiment(
        WORKBOOK,
        sheet="RebateCalc",
        overrides={"B6": {"kind": "date", "value": "2026-01-03"}},
        observations=["B6", "Q6"],
    )

    assert result.observations["B6"] == 46_025
    assert isinstance(result.observations["Q6"], (int, float))


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


def test_self_qualified_dependencies_use_live_raw_and_formula_overrides(tmp_path: Path) -> None:
    workbook = _self_qualified_dependency_workbook(tmp_path)
    raw_result = execute_experiment(
        workbook,
        sheet="RebateCalc",
        overrides={"E6": 123},
        observations=["M6"],
    )
    source_formula = formula_map(workbook)["L6"]
    formula_result = execute_experiment(
        workbook,
        sheet="RebateCalc",
        overrides={},
        observations=["M6"],
        formula_overrides=[FormulaOverride("L6", _formula_hash(source_formula), "=1")],
    )

    assert raw_result.observations["M6"] == 124
    assert formula_result.observations["M6"] == 2
    assert formula_result.dependencies["M6"] == ["L6"]


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
