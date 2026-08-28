"""Sealed, one-shot semantic evaluation kept outside both repair workflows."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .advanced import run_advanced
from .baseline import run_baseline
from .benchmark import MAX_PATCH_CELLS, WORKBOOK_CASES, held_out_cases
from .formula import evaluate_cells
from .ooxml import changed_core_formulas, inspect_safety, sha256_file, sheet_cells
from .oracle import evaluate_policy
from .policy import CORE_OUTPUTS, INPUT_CELL_MAP


def _same(actual: Any, expected: Any, cell: str) -> bool:
    if cell == "T6":
        return actual == expected
    return abs(float(actual) - float(expected)) <= 1e-8


def sealed_semantic_check(workbook: Path) -> tuple[bool, int, str | None]:
    values, formulas = sheet_cells(workbook, "RebateCalc")
    passed = 0
    for case in held_out_cases():
        overrides = {
            INPUT_CELL_MAP[name]: value
            for name, value in case.inputs.items()
            if name in INPUT_CELL_MAP
        }
        outputs, _ = evaluate_cells(values, formulas, overrides)
        expected = evaluate_policy(case.inputs)
        if all(_same(outputs[cell], expected[cell], cell) for cell in CORE_OUTPUTS):
            passed += 1
        else:
            return False, passed, case.case_id
    return True, passed, None


def evaluate_method(
    method: str,
    root: Path,
    policy_pdf: Path,
    artifact_root: Path,
) -> dict[str, Any]:
    runner: Callable[..., Any] = run_advanced if method == "advanced" else run_baseline
    records: list[dict[str, Any]] = []
    for case_id, relative in WORKBOOK_CASES.items():
        source = root / relative
        before_hash = sha256_file(source)
        result = runner(
            source, policy_pdf, artifact_root / method / case_id, reviewer="sealed-eval-reviewer"
        )
        candidate = Path(result.output_workbook) if result.output_workbook else source
        inspect_safety(candidate)
        changes = changed_core_formulas(source, candidate, CORE_OUTPUTS)
        semantic_ok, passed_vectors, first_failure = sealed_semantic_check(candidate)
        source_immutable = sha256_file(source) == before_hash
        minimality_ok = len(changes) <= MAX_PATCH_CELLS[case_id]
        clean_ok = case_id.startswith("C") and len(changes) == 0
        mutation_ok = not case_id.startswith("C") and semantic_ok and minimality_ok
        success = source_immutable and (
            clean_ok and semantic_ok if case_id.startswith("C") else mutation_ok
        )
        records.append(
            {
                "case_id": case_id,
                "decision": result.decision,
                "changed_cells": sorted(changes),
                "semantic_vectors_passed": passed_vectors,
                "semantic_vectors_total": 48,
                "first_failure": first_failure,
                "semantic_ok": semantic_ok,
                "minimality_ok": minimality_ok,
                "source_immutable": source_immutable,
                "success": success,
                "run_id": result.run_id,
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
        "records": records,
    }


def run_evaluation(root: Path, output: Path) -> dict[str, Any]:
    policy_pdf = root / "policies/supplier_rebate_sla_policy.pdf"
    artifact_root = root / "artifacts/runs/evaluation"
    baseline = evaluate_method("baseline", root, policy_pdf, artifact_root)
    advanced = evaluate_method("advanced", root, policy_pdf, artifact_root)
    improvement = advanced["e2e_semantic_repair_rate"] - baseline["e2e_semantic_repair_rate"]
    payload = {
        "schema_version": 1,
        "benchmark": "SupplierRebate-SLA-16",
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
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
