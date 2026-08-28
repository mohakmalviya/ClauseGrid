"""Sealed, one-shot semantic evaluation kept outside both repair workflows."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

from .formula import FormulaError, evaluate_cells
from .ooxml import (
    calculation_cells,
    changed_core_formulas,
    changed_workbook_formulas,
    inspect_safety,
    sha256_file,
)
from .policy import CORE_OUTPUTS, INPUT_CELL_MAP
from .public_benchmark import DEFECT_FAMILIES, MAX_PATCH_CELLS, WORKBOOK_CASES


def _same(actual: Any, expected: Any, cell: str) -> bool:
    if cell == "T6":
        return bool(actual == expected)
    return abs(float(actual) - float(expected)) <= 1e-8


def sealed_semantic_check(workbook: Path) -> tuple[bool, int, str | None]:
    # Imported only inside the evaluator process, after the repair worker exits.
    from evals.sealed.cases import held_out_cases
    from evals.sealed.oracle import evaluate_policy

    values, formulas = calculation_cells(workbook)
    passed = 0
    for case in held_out_cases():
        overrides = {
            INPUT_CELL_MAP[name]: value
            for name, value in case.inputs.items()
            if name in INPUT_CELL_MAP
        }
        try:
            outputs, _ = evaluate_cells(values, formulas, overrides)
        except FormulaError as exc:
            return False, passed, f"{case.case_id}: {type(exc).__name__}"
        expected = evaluate_policy(case.inputs)
        if all(_same(outputs[cell], expected[cell], cell) for cell in CORE_OUTPUTS):
            passed += 1
        else:
            return False, passed, case.case_id
    return True, passed, None


def _run_isolated_agent(
    method: str,
    source: Path,
    policy_pdf: Path,
    artifact_root: Path,
) -> dict[str, Any]:
    artifact_root.mkdir(parents=True, exist_ok=True)
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "formulawitness.agent_worker",
            method,
            str(source),
            str(policy_pdf),
            str(artifact_root),
            "--reviewer",
            "sealed-eval-reviewer",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=artifact_root,
        env=environment,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Isolated {method} worker failed: {completed.stderr[-500:]}")
    try:
        return cast(dict[str, Any], json.loads(completed.stdout))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Isolated {method} worker returned invalid JSON") from exc


def _require_agent_output(result: dict[str, Any], output_root: Path, source: Path) -> Path:
    raw = result.get("output_workbook")
    if not raw:
        return source
    candidate = Path(str(raw)).resolve()
    if candidate == source.resolve():
        return candidate
    try:
        candidate.relative_to(output_root.resolve())
    except ValueError as exc:
        raise RuntimeError(
            "Repair worker returned an output outside its artifact directory"
        ) from exc
    if not candidate.is_file():
        raise RuntimeError("Repair worker did not produce the declared workbook")
    return candidate


def evaluate_method(
    method: str,
    root: Path,
    policy_pdf: Path,
    artifact_root: Path,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for case_id, relative in WORKBOOK_CASES.items():
        source = root / relative
        before_hash = sha256_file(source)
        case_root = artifact_root / method / case_id
        public_inputs = case_root / "public-inputs"
        public_inputs.mkdir(parents=True, exist_ok=True)
        staged_source = public_inputs / "workbook.xlsx"
        staged_policy = public_inputs / "policy.pdf"
        shutil.copyfile(source, staged_source)
        shutil.copyfile(policy_pdf, staged_policy)
        agent_output = case_root / "agent-output"
        result = _run_isolated_agent(
            method,
            staged_source,
            staged_policy,
            agent_output,
        )
        candidate = _require_agent_output(result, agent_output, staged_source)
        inspect_safety(candidate)
        changes = changed_core_formulas(source, candidate, CORE_OUTPUTS)
        workbook_changes = changed_workbook_formulas(source, candidate)
        unrelated_changes = sorted(
            cell
            for cell in workbook_changes
            if cell not in {f"RebateCalc!{core_cell}" for core_cell in CORE_OUTPUTS}
        )
        semantic_ok, passed_vectors, first_failure = sealed_semantic_check(candidate)
        source_immutable = sha256_file(source) == before_hash
        minimality_ok = (
            len(changes) <= MAX_PATCH_CELLS[case_id]
            and len(workbook_changes) == len(changes)
            and not unrelated_changes
        )
        clean_ok = case_id.startswith("C") and len(changes) == 0
        mutation_ok = not case_id.startswith("C") and semantic_ok and minimality_ok
        success = source_immutable and (
            clean_ok and semantic_ok if case_id.startswith("C") else mutation_ok
        )
        records.append(
            {
                "case_id": case_id,
                "defect_family": DEFECT_FAMILIES[case_id],
                "decision": result["decision"],
                "changed_cells": sorted(changes),
                "changed_formulas": sorted(workbook_changes),
                "unrelated_formula_changes": unrelated_changes,
                "semantic_vectors_passed": passed_vectors,
                "semantic_vectors_total": 48,
                "first_failure": first_failure,
                "semantic_ok": semantic_ok,
                "minimality_ok": minimality_ok,
                "source_immutable": source_immutable,
                "success": success,
                "run_id": result["run_id"],
                "budget": result["budget"],
            }
        )
    mutants = [record for record in records if record["case_id"].startswith("M")]
    controls = [record for record in records if record["case_id"].startswith("C")]
    hard = next(record for record in records if record["case_id"] == "H01")
    return {
        "method": method,
        "determinism": "one run required; workflow and model policy are deterministic",
        "primary_metric": "End-to-End Semantic Repair Rate",
        "e2e_semantic_repair_rate": 100
        * sum(record["success"] for record in mutants)
        / len(mutants),
        "clean_preservation_rate": 100
        * sum(record["success"] for record in controls)
        / len(controls),
        "hard_multi_rule_rate": 100.0 if hard["success"] else 0.0,
        "model_id": records[0]["budget"]["model_id"],
        "token_limit": records[0]["budget"]["token_limit"],
        "workbook_case_execution_limit": records[0]["budget"]["workbook_case_execution_limit"],
        "records": records,
    }


def run_evaluation(root: Path, output: Path) -> dict[str, Any]:
    policy_pdf = root / "policies/supplier_rebate_sla_policy.pdf"
    with tempfile.TemporaryDirectory(prefix="formulawitness-sealed-eval-") as directory:
        artifact_root = Path(directory)
        baseline = evaluate_method("baseline", root, policy_pdf, artifact_root)
        advanced = evaluate_method("advanced", root, policy_pdf, artifact_root)
    improvement = advanced["e2e_semantic_repair_rate"] - baseline["e2e_semantic_repair_rate"]
    payload = {
        "schema_version": 1,
        "benchmark": "SupplierRebate-SLA-16-v2",
        "hidden_case_count_per_workbook": 48,
        "oracle": "independent Python Decimal/date implementation",
        "baseline": baseline,
        "advanced": advanced,
        "improvement_percentage_points": improvement,
        "acceptance": {
            "advanced_at_least_20pp_better": improvement >= 20,
            "advanced_no_more_false_repairs": advanced["clean_preservation_rate"]
            >= baseline["clean_preservation_rate"],
            "advanced_clean_preservation_100": advanced["clean_preservation_rate"] == 100,
            "fair_budget_contract": all(
                baseline[key] == advanced[key]
                for key in ("model_id", "token_limit", "workbook_case_execution_limit")
            ),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
