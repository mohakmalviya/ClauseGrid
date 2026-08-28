"""Counterexample-guided FormulaWitness repair workflow."""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from pathlib import Path
from typing import Any

from .artifacts import (
    counterexample_rows,
    evidence_graph,
    formula_diff,
    report_rows,
    test_record,
    write_json,
)
from .benchmark import visible_cases
from .formula import evaluate_cells, referenced_cells
from .models import AuditResult, Patch, TestCase
from .ooxml import inspect_safety, patch_workbook, sheet_cells
from .policy import (
    CORE_OUTPUTS,
    INPUT_CELL_MAP,
    compile_rule_formulas,
    evaluate_approved_rules,
    extract_rules,
    verify_citations,
    write_rules_yaml,
)
from .runner import execute_batch
from .trace import Trajectory, object_hash

RULES_BY_CELL = {
    "L6": ("RB-101",),
    "M6": ("RB-204",),
    "N6": ("RB-102",),
    "O6": ("RB-103",),
    "P6": ("RB-201", "RB-202", "RB-203"),
    "Q6": ("RB-205",),
    "R6": ("RB-301",),
    "S6": ("RB-302",),
    "T6": ("RB-303",),
}


def _mismatches(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for cell in CORE_OUTPUTS:
        if cell == "T6":
            differs = expected[cell] != actual[cell]
        else:
            differs = abs(float(expected[cell]) - float(actual[cell])) > 1e-8
        if differs:
            result.append(cell)
    return result


def _execute_in_memory(
    values: dict[str, Any], formulas: dict[str, str], case: TestCase
) -> dict[str, Any]:
    overrides = {
        INPUT_CELL_MAP[name]: value for name, value in case.inputs.items() if name in INPUT_CELL_MAP
    }
    outputs, _ = evaluate_cells(values, formulas, overrides)
    return {cell: outputs[cell] for cell in CORE_OUTPUTS}


def _run_cases(
    values: dict[str, Any], formulas: dict[str, str], cases: list[TestCase]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case in cases:
        expected = evaluate_approved_rules(case.inputs)
        actual = _execute_in_memory(values, formulas, case)
        records.append(test_record(case, expected, actual, _mismatches(expected, actual)))
    return records


def _passing(records: list[dict[str, Any]]) -> int:
    return sum(record["status"] == "PASS" for record in records)


def _localize(
    records: list[dict[str, Any]], formulas: dict[str, str], compiled: dict[str, str]
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for record in records:
        counts.update(record["mismatched_cells"])
    dependencies = {cell: referenced_cells(formula) for cell, formula in formulas.items()}

    def dependency_cone(output: str) -> set[str]:
        seen: set[str] = set()
        frontier = [output]
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(dep for dep in dependencies.get(current, []) if dep in formulas)
        return seen

    cones = {cell: dependency_cone(cell) for cell in CORE_OUTPUTS}
    failing = [record for record in records if record["status"] == "FAIL"]
    passing = [record for record in records if record["status"] == "PASS"]
    candidates = []
    for cell in CORE_OUTPUTS:
        if formulas.get(cell) != compiled.get(cell):
            failed_covered = sum(
                any(cell in cones[output] for output in record["mismatched_cells"])
                for record in failing
            )
            passed_covered = sum(
                any(cell in cones[output] for output in CORE_OUTPUTS) for _ in passing
            )
            denominator = math.sqrt(len(failing) * (failed_covered + passed_covered))
            ochiai = failed_covered / denominator if denominator else 0.0
            candidates.append(
                {
                    "cell": cell,
                    "ochiai": round(ochiai, 6),
                    "failed_covered": failed_covered,
                    "passed_covered": passed_covered,
                    "direct_mismatch_count": counts[cell],
                    "failing_cases": sum(cell in record["mismatched_cells"] for record in records),
                    "affected_outputs": [
                        output for output in CORE_OUTPUTS if cell in cones[output]
                    ],
                    "rule_ids": list(RULES_BY_CELL[cell]),
                    "compiled_formula_differs": True,
                }
            )
    return sorted(
        candidates,
        key=lambda item: (-item["ochiai"], -item["direct_mismatch_count"], item["cell"]),
    )


def run_advanced(
    workbook: Path,
    policy_pdf: Path,
    artifact_root: Path,
    reviewer: str | None = None,
) -> AuditResult:
    safety = inspect_safety(workbook)
    rules = extract_rules(policy_pdf)
    verify_citations(policy_pdf, rules)
    cases = visible_cases()
    values, source_formulas = sheet_cells(workbook, "RebateCalc")
    compiled = compile_rule_formulas()
    run_id = (
        "advanced-" + hashlib.sha256(f"{safety['sha256']}|witness-v1".encode()).hexdigest()[:12]
    )
    run_dir = artifact_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    trajectory = Trajectory(run_dir / "trajectory.jsonl", run_id)
    trajectory.record("ingest-agent", "INGEST", {"workbook": safety["sha256"]}, safety)
    trajectory.record(
        "rule-agent", "EXTRACT_RULES", {"policy": str(policy_pdf)}, [rule.rule_id for rule in rules]
    )

    formulas = dict(source_formulas)
    sandbox_results = execute_batch(workbook, [case.inputs for case in cases])
    records = []
    for case, sandbox_result in zip(cases, sandbox_results, strict=True):
        expected = evaluate_approved_rules(case.inputs)
        actual = sandbox_result.outputs
        records.append(test_record(case, expected, actual, _mismatches(expected, actual)))
    trajectory.record(
        "counterexample-agent",
        "EXECUTE_COUNTEREXAMPLES",
        [case.case_id for case in cases],
        records,
        elapsed_ms=sandbox_results[0].elapsed_ms if sandbox_results else 0,
    )
    initial_records = records
    localization = _localize(records, formulas, compiled)
    trajectory.record("localization-agent", "LOCALIZE", records, localization)
    patches: list[Patch] = []
    current_passes = _passing(records)
    for _ in range(3):
        best: tuple[int, str, list[dict[str, Any]]] | None = None
        for item in _localize(records, formulas, compiled):
            cell = item["cell"]
            candidate_formulas = {**formulas, cell: compiled[cell]}
            candidate_records = _run_cases(values, candidate_formulas, cases)
            score = _passing(candidate_records)
            if score > current_passes and (best is None or (score, cell) > (best[0], best[1])):
                best = (score, cell, candidate_records)
        if best is None:
            break
        score, cell, candidate_records = best
        patches.append(
            Patch(
                cell=cell,
                old_formula=source_formulas[cell],
                new_formula=compiled[cell],
                rule_ids=RULES_BY_CELL[cell],
                rationale=f"Policy-compiled formula eliminates {score - current_passes} visible failures with one cell change.",
            )
        )
        formulas[cell] = compiled[cell]
        records = candidate_records
        current_passes = score
        if current_passes == len(cases):
            break
    trajectory.record("repair-agent", "PROPOSE_MINIMAL_PATCH", localization, formula_diff(patches))
    decision = (
        "NO_CHANGE"
        if _passing(initial_records) == len(cases)
        else ("REPAIR" if _passing(records) == len(cases) else "ABSTAIN")
    )
    result = AuditResult(
        run_id=run_id,
        method="formulawitness-advanced",
        source_workbook=str(workbook.resolve()),
        source_sha256=safety["sha256"],
        rules_sha256=object_hash([rule.__dict__ for rule in rules]),
        tests=initial_records,
        suspicious_cells=localization,
        patches=patches,
        decision=decision,
        artifact_dir=str(run_dir.resolve()),
    )
    write_rules_yaml(run_dir / "rules.yaml", rules)
    write_json(run_dir / "formula-diff.json", formula_diff(patches))
    write_json(run_dir / "evidence-graph.json", evidence_graph(rules, initial_records, patches))
    write_json(run_dir / "counterexamples.json", initial_records)
    if decision == "REPAIR" and reviewer:
        approval = {
            "actor": reviewer,
            "decision": "APPROVE",
            "source_sha256": result.source_sha256,
            "rules_sha256": result.rules_sha256,
            "case_manifest_hash": object_hash([case.__dict__ for case in cases]),
            "patch_hash": object_hash(formula_diff(patches)),
        }
        result.approval_hash = object_hash(approval)
        output = run_dir / "repaired.xlsx"
        patch_workbook(
            workbook,
            output,
            {patch.cell: (patch.old_formula, patch.new_formula) for patch in patches},
            counterexample_rows(initial_records),
            report_rows(result.to_dict()),
        )
        result.output_workbook = str(output.resolve())
        write_json(run_dir / "approval.json", {**approval, "approval_hash": result.approval_hash})
        trajectory.record(
            "human-reviewer",
            "APPROVE",
            approval,
            {"approval_hash": result.approval_hash},
            artifact_refs=["repaired.xlsx"],
        )
    elif decision == "NO_CHANGE":
        result.output_workbook = str(workbook.resolve())
    write_json(run_dir / "report.json", result.to_dict())
    return result
