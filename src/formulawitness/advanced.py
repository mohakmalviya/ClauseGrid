"""Counterexample-guided FormulaWitness repair workflow."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from .artifacts import (
    counterexample_rows,
    evidence_graph,
    formula_diff,
    portable_audit_payload,
    report_rows,
    test_record,
    write_json,
)
from .budget import DEFAULT_RUN_BUDGET, BudgetLedger, RunBudget
from .formula import evaluate_cells, referenced_cells
from .models import AuditResult, Patch, Rule, TestCase
from .ooxml import calculation_cells, inspect_safety, patch_workbook, sha256_file
from .policy import (
    CORE_OUTPUTS,
    INPUT_CELL_MAP,
    PolicyAmbiguityError,
    ambiguity_gate,
    compile_rule_formulas,
    evaluate_approved_rules,
    extract_rules,
    verify_citations,
    verify_rule_sources,
    write_rules_yaml,
)
from .public_benchmark import visible_cases
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
WORKFLOW_VERSION = "witness-v2"


def _audit_result(payload: dict[str, Any]) -> AuditResult:
    data = dict(payload)
    patches = [Patch(**patch) for patch in data.pop("patches", [])]
    return AuditResult(**data, patches=patches)


def _load_approved_run(
    run_dir: Path,
    source_sha256: str,
    rules_sha256: str,
    case_manifest_hash: str,
) -> AuditResult | None:
    """Return an already-approved immutable run after validating its bindings."""

    approval_path = run_dir / "approval.json"
    if not approval_path.is_file():
        return None
    report_path = run_dir / "report.json"
    output = run_dir / "repaired.xlsx"
    if not report_path.is_file() or not output.is_file():
        raise ValueError("Approved run is incomplete and must not be overwritten")
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval_hash = approval.pop("approval_hash", None)
    if approval_hash != object_hash(approval):
        raise ValueError("Approved run manifest hash is invalid")
    result = _audit_result(json.loads(report_path.read_text(encoding="utf-8")))
    checks = {
        "source_sha256": source_sha256,
        "rules_sha256": rules_sha256,
        "case_manifest_hash": case_manifest_hash,
        "patch_hash": object_hash(formula_diff(result.patches)),
        "repaired_sha256": sha256_file(output),
    }
    if any(approval.get(key) != value for key, value in checks.items()):
        raise ValueError("Approved run bindings no longer match the requested audit")
    if result.approval_hash != approval_hash:
        raise ValueError("Approved report does not match its approval manifest")
    inspect_safety(output)
    result.output_workbook = str(output.resolve())
    result.artifact_dir = str(run_dir.resolve())
    return result


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
    values: dict[str, Any],
    formulas: dict[str, str],
    cases: list[TestCase],
    ledger: BudgetLedger,
    rules: list[Rule],
) -> list[dict[str, Any]]:
    ledger.charge_cases(len(cases))
    records: list[dict[str, Any]] = []
    for case in cases:
        expected = evaluate_approved_rules(case.inputs, rules)
        actual = _execute_in_memory(values, formulas, case)
        records.append(test_record(case, expected, actual, _mismatches(expected, actual)))
    return records


def _passing(records: list[dict[str, Any]]) -> int:
    return sum(record["status"] == "PASS" for record in records)


def _localize(records: list[dict[str, Any]], formulas: dict[str, str]) -> list[dict[str, Any]]:
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
        failed_covered = sum(
            any(cell in cones[output] for output in record["mismatched_cells"])
            for record in failing
        )
        if failed_covered == 0:
            continue
        passed_covered = sum(any(cell in cones[output] for output in CORE_OUTPUTS) for _ in passing)
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
                "affected_outputs": [output for output in CORE_OUTPUTS if cell in cones[output]],
                "rule_ids": list(RULES_BY_CELL[cell]),
            }
        )
    return sorted(
        candidates,
        key=lambda item: (-item["ochiai"], -item["direct_mismatch_count"], item["cell"]),
    )


def _apply_approval(
    result: AuditResult,
    workbook: Path,
    run_dir: Path,
    case_manifest_hash: str,
    trajectory: Trajectory,
    reviewer: str,
) -> AuditResult:
    if result.decision != "REPAIR" or not result.patches:
        raise ValueError("Only a frozen repair proposal can be approved")
    approval = {
        "actor": reviewer,
        "decision": "APPROVE",
        "source_sha256": result.source_sha256,
        "rules_sha256": result.rules_sha256,
        "case_manifest_hash": case_manifest_hash,
        "patch_hash": object_hash(formula_diff(result.patches)),
    }
    output = run_dir / "repaired.xlsx"
    if output.exists():
        raise ValueError("Run already contains a repair artifact and will not be overwritten")
    patch_workbook(
        workbook,
        output,
        {patch.cell: (patch.old_formula, patch.new_formula) for patch in result.patches},
        counterexample_rows(result.tests),
        report_rows(result.to_dict()),
    )
    approval["repaired_sha256"] = sha256_file(output)
    result.approval_hash = object_hash(approval)
    result.output_workbook = str(output.resolve())
    trajectory.record(
        "human-reviewer",
        "APPROVE",
        approval,
        {"approval_hash": result.approval_hash},
        artifact_refs=["repaired.xlsx"],
    )
    write_json(run_dir / "report.json", portable_audit_payload(result))
    write_json(run_dir / "approval.json", {**approval, "approval_hash": result.approval_hash})
    return result


def approve_advanced_proposal(
    workbook: Path,
    policy_pdf: Path,
    artifact_root: Path,
    run_id: str,
    reviewer: str,
    *,
    expected_proposal_hash: str | None = None,
) -> AuditResult:
    """Approve and apply the exact persisted proposal without rerunning diagnosis."""

    run_dir = artifact_root / run_id
    proposal_path = run_dir / "proposal.json"
    if not proposal_path.is_file():
        raise ValueError("Frozen proposal not found")
    if (run_dir / "approval.json").exists():
        raise ValueError("Proposal has already been approved")
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    if expected_proposal_hash and object_hash(proposal) != expected_proposal_hash:
        raise ValueError("Proposal manifest changed after review")
    if proposal.get("run_id") != run_id:
        raise ValueError("Proposal run identifier mismatch")

    safety = inspect_safety(workbook)
    rules = extract_rules(policy_pdf)
    verify_citations(policy_pdf, rules)
    ambiguity_gate(rules)
    cases = visible_cases()
    result = _audit_result(proposal["result"])
    patches = result.patches
    checks = {
        "source_sha256": safety["sha256"],
        "rules_sha256": object_hash([rule.__dict__ for rule in rules]),
        "case_manifest_hash": object_hash([case.__dict__ for case in cases]),
        "patch_hash": object_hash(formula_diff(patches)),
    }
    for key, expected in checks.items():
        if proposal.get(key) != expected:
            raise ValueError(f"Frozen proposal {key} no longer matches")
    if (
        result.source_sha256 != checks["source_sha256"]
        or result.rules_sha256 != checks["rules_sha256"]
    ):
        raise ValueError("Proposal result hashes no longer match")

    trajectory = Trajectory(run_dir / "trajectory.jsonl", run_id, resume=True)
    return _apply_approval(
        result,
        workbook,
        run_dir,
        checks["case_manifest_hash"],
        trajectory,
        reviewer,
    )


def run_advanced(
    workbook: Path,
    policy_pdf: Path,
    artifact_root: Path,
    reviewer: str | None = None,
    budget: RunBudget = DEFAULT_RUN_BUDGET,
) -> AuditResult:
    safety = inspect_safety(workbook)
    rules = extract_rules(policy_pdf)
    verify_citations(policy_pdf, rules)
    ledger = BudgetLedger(budget)
    rules_sha256 = object_hash([rule.__dict__ for rule in rules])
    ambiguity: PolicyAmbiguityError | None = None
    cases: list[TestCase] = []
    try:
        ambiguity_gate(rules)
        cases = visible_cases()
    except PolicyAmbiguityError as exc:
        ambiguity = exc
    case_manifest_hash = object_hash([case.__dict__ for case in cases]) if cases else None
    run_id = (
        "advanced-"
        + object_hash(
            {
                "source_sha256": safety["sha256"],
                "rules_sha256": rules_sha256,
                "case_manifest_hash": case_manifest_hash,
                "workflow_version": WORKFLOW_VERSION,
            }
        )[:12]
    )
    run_dir = artifact_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if ambiguity is None and case_manifest_hash is not None:
        existing = _load_approved_run(
            run_dir,
            str(safety["sha256"]),
            rules_sha256,
            case_manifest_hash,
        )
        if existing is not None:
            return existing
    trajectory = Trajectory(run_dir / "trajectory.jsonl", run_id)
    trajectory.record("ingest-agent", "INGEST", {"workbook": safety["sha256"]}, safety)
    trajectory.record(
        "rule-agent", "EXTRACT_RULES", {"policy": str(policy_pdf)}, [rule.rule_id for rule in rules]
    )
    if ambiguity is not None:
        trajectory.record(
            "rule-agent",
            "AMBIGUITY_GATE",
            [rule.rule_id for rule in rules],
            {"decision": "ABSTAIN", "reason": str(ambiguity)},
        )
        result = AuditResult(
            run_id=run_id,
            method="formulawitness-advanced",
            source_workbook=str(workbook.resolve()),
            source_sha256=safety["sha256"],
            rules_sha256=rules_sha256,
            decision="ABSTAIN",
            artifact_dir=str(run_dir.resolve()),
            budget=ledger.to_dict(),
        )
        write_rules_yaml(run_dir / "rules.yaml", rules)
        proposal = {
            "schema_version": 1,
            "run_id": run_id,
            "source_sha256": result.source_sha256,
            "rules_sha256": result.rules_sha256,
            "case_manifest_hash": None,
            "patch_hash": object_hash([]),
            "result": portable_audit_payload(result),
        }
        write_json(run_dir / "proposal.json", proposal)
        write_json(run_dir / "report.json", portable_audit_payload(result))
        return result

    assert case_manifest_hash is not None
    values, source_formulas = calculation_cells(workbook)
    verify_rule_sources(values, rules)
    compiled = compile_rule_formulas(rules)

    formulas = dict(source_formulas)
    ledger.charge_cases(len(cases))
    sandbox_results = execute_batch(workbook, [case.inputs for case in cases])
    records = []
    for case, sandbox_result in zip(cases, sandbox_results, strict=True):
        expected = evaluate_approved_rules(case.inputs, rules)
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
    localization = _localize(records, formulas)
    trajectory.record("localization-agent", "LOCALIZE", records, localization)
    patches: list[Patch] = []
    current_passes = _passing(records)
    for _ in range(3):
        best: tuple[int, str, list[dict[str, Any]]] | None = None
        for item in _localize(records, formulas):
            cell = item["cell"]
            if formulas.get(cell) == compiled.get(cell):
                continue
            candidate_formulas = {**formulas, cell: compiled[cell]}
            candidate_records = _run_cases(values, candidate_formulas, cases, ledger, rules)
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
    decision: Literal["REPAIR", "NO_CHANGE", "ABSTAIN"] = (
        "NO_CHANGE"
        if _passing(initial_records) == len(cases)
        else ("REPAIR" if _passing(records) == len(cases) else "ABSTAIN")
    )
    result = AuditResult(
        run_id=run_id,
        method="formulawitness-advanced",
        source_workbook=str(workbook.resolve()),
        source_sha256=safety["sha256"],
        rules_sha256=rules_sha256,
        tests=initial_records,
        suspicious_cells=localization,
        patches=patches,
        decision=decision,
        artifact_dir=str(run_dir.resolve()),
        budget=ledger.to_dict(),
    )
    write_rules_yaml(run_dir / "rules.yaml", rules)
    write_json(run_dir / "formula-diff.json", formula_diff(patches))
    write_json(run_dir / "evidence-graph.json", evidence_graph(rules, initial_records, patches))
    write_json(run_dir / "counterexamples.json", initial_records)
    proposal = {
        "schema_version": 1,
        "run_id": run_id,
        "source_sha256": result.source_sha256,
        "rules_sha256": result.rules_sha256,
        "case_manifest_hash": case_manifest_hash,
        "patch_hash": object_hash(formula_diff(patches)),
        "result": portable_audit_payload(result),
    }
    write_json(run_dir / "proposal.json", proposal)
    write_json(run_dir / "report.json", portable_audit_payload(result))
    if decision == "REPAIR" and reviewer:
        return approve_advanced_proposal(
            workbook,
            policy_pdf,
            artifact_root,
            run_id,
            reviewer,
            expected_proposal_hash=object_hash(proposal),
        )
    if decision == "NO_CHANGE":
        result.output_workbook = str(workbook.resolve())
    write_json(run_dir / "report.json", portable_audit_payload(result))
    return result
