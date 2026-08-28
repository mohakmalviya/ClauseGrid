"""Fair single-pass direct-repair baseline without structured experimentation."""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from .artifacts import formula_diff, portable_audit_payload, report_rows, test_record, write_json
from .budget import DEFAULT_RUN_BUDGET, BudgetLedger, RunBudget
from .formula import evaluate_cells
from .models import AuditResult, Patch, Rule, TestCase
from .ooxml import calculation_cells, formula_map, inspect_safety, patch_workbook
from .policy import (
    CORE_OUTPUTS,
    INPUT_CELL_MAP,
    evaluate_approved_rules,
    extract_rules,
    verify_citations,
    write_rules_yaml,
)
from .public_benchmark import visible_cases
from .runner import execute_batch
from .trace import Trajectory, object_hash

SEMANTIC_CELL_MAP = {
    **INPUT_CELL_MAP,
    "eligible_spend": "L6",
    "active_days": "M6",
}
BOUNDARY_RE = re.compile(r"^(?P<name>[a-z_]+)(?P<op><=|>=|<|>)(?P<number>\d+(?:\.\d+)?)$")
FORMULA_NUMBER_RE = re.compile(r"(?<![A-Z0-9_])(?P<number>\d+(?:\.\d+)?)", re.IGNORECASE)
POLICY_NUMBER_RE = re.compile(r"\$?(?P<number>\d[\d,]*(?:\.\d+)?)\s*(?P<percent>%)?")


def _policy_numbers(rule: Rule) -> set[Decimal]:
    values: set[Decimal] = set()
    for match in POLICY_NUMBER_RE.finditer(rule.evidence.exact_quote):
        value = Decimal(match.group("number").replace(",", ""))
        values.add(value / 100 if match.group("percent") else value)
    lowered = rule.evidence.exact_quote.lower()
    if re.search(r"\bzero\b", lowered):
        values.add(Decimal(0))
    if re.search(r"\bone\b", lowered):
        values.add(Decimal(1))
    for boundary in rule.boundaries:
        boundary_match = BOUNDARY_RE.match(boundary)
        if boundary_match:
            values.add(Decimal(boundary_match.group("number")))
    return values


def _direct_candidate(formulas: dict[str, str], rules: list[Rule]) -> Patch | None:
    """Make one generic policy-derived edit without mutation-specific lookup data."""

    rules_by_target: dict[str, list[Rule]] = {}
    for rule in rules:
        rules_by_target.setdefault(rule.target, []).append(rule)

    for cell, target_rules in rules_by_target.items():
        formula = formulas.get(cell, "")
        rule_ids = tuple(rule.rule_id for rule in target_rules)
        for rule in target_rules:
            for boundary in rule.boundaries:
                match = BOUNDARY_RE.match(boundary)
                if not match or match.group("name") not in SEMANTIC_CELL_MAP:
                    continue
                source_cell = SEMANTIC_CELL_MAP[match.group("name")]
                number = match.group("number")
                found = re.search(rf"{source_cell}(?P<op><=|>=|<|>){re.escape(number)}", formula)
                if found and found.group("op") != match.group("op"):
                    old = found.group(0)
                    new = f"{source_cell}{match.group('op')}{number}"
                    return Patch(
                        cell,
                        formula,
                        formula.replace(old, new),
                        rule_ids,
                        f"Direct reading aligns {source_cell} with cited boundary {boundary}.",
                    )

        expected_numbers = set().union(*(_policy_numbers(rule) for rule in target_rules))
        current_matches = list(FORMULA_NUMBER_RE.finditer(formula))
        current_numbers = {Decimal(match.group("number")) for match in current_matches}
        extra = current_numbers - expected_numbers
        missing = expected_numbers - current_numbers
        if len(extra) == 1 and len(missing) == 1:
            old_value = next(iter(extra))
            new_value = next(iter(missing))
            match = next(
                item for item in current_matches if Decimal(item.group("number")) == old_value
            )
            new_formula = formula[: match.start()] + str(new_value) + formula[match.end() :]
            return Patch(
                cell,
                formula,
                new_formula,
                rule_ids,
                "Direct reading replaces one formula constant absent from the cited clauses.",
            )
    return None


def _mismatches(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    for cell in CORE_OUTPUTS:
        differs = (
            expected[cell] != actual[cell]
            if cell == "T6"
            else abs(float(expected[cell]) - float(actual[cell])) > 1e-8
        )
        if differs:
            mismatches.append(cell)
    return mismatches


def _simulate_cases(
    values: dict[str, Any],
    formulas: dict[str, str],
    cases: list[TestCase],
    ledger: BudgetLedger,
    rules: list[Rule],
) -> list[dict[str, Any]]:
    ledger.charge_cases(len(cases))
    records: list[dict[str, Any]] = []
    for case in cases:
        overrides = {
            INPUT_CELL_MAP[name]: value
            for name, value in case.inputs.items()
            if name in INPUT_CELL_MAP
        }
        outputs, _ = evaluate_cells(values, formulas, overrides)
        actual = {cell: outputs[cell] for cell in CORE_OUTPUTS}
        expected = evaluate_approved_rules(case.inputs, rules)
        records.append(test_record(case, expected, actual, _mismatches(expected, actual)))
    return records


def _passing(records: list[dict[str, Any]]) -> int:
    return sum(record["status"] == "PASS" for record in records)


def run_baseline(
    workbook: Path,
    policy_pdf: Path,
    artifact_root: Path,
    reviewer: str | None = None,
    budget: RunBudget = DEFAULT_RUN_BUDGET,
) -> AuditResult:
    safety = inspect_safety(workbook)
    rules = extract_rules(policy_pdf)
    verify_citations(policy_pdf, rules)
    formulas = formula_map(workbook)
    values, source_formulas = calculation_cells(workbook)
    cases = visible_cases()
    ledger = BudgetLedger(budget)
    run_id = "baseline-" + hashlib.sha256(f"{safety['sha256']}|direct-v1".encode()).hexdigest()[:12]
    run_dir = artifact_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    trajectory = Trajectory(run_dir / "trajectory.jsonl", run_id)
    trajectory.record(
        "direct-agent", "INGEST", {"workbook": safety["sha256"]}, {"formula_count": len(formulas)}
    )
    ledger.charge_cases(len(cases))
    sandbox_results = execute_batch(workbook, [case.inputs for case in cases])
    records: list[dict[str, Any]] = []
    for case, sandbox_result in zip(cases, sandbox_results, strict=True):
        expected = evaluate_approved_rules(case.inputs, rules)
        records.append(
            test_record(
                case,
                expected,
                sandbox_result.outputs,
                _mismatches(expected, sandbox_result.outputs),
            )
        )
    trajectory.record(
        "direct-agent",
        "EXECUTE_VISIBLE_CASES",
        [case.case_id for case in cases],
        records,
        elapsed_ms=sandbox_results[0].elapsed_ms if sandbox_results else 0,
    )
    candidate = _direct_candidate(formulas, rules)
    patches: list[Patch] = []
    if candidate:
        candidate_formulas = {**source_formulas, candidate.cell: candidate.new_formula}
        candidate_records = _simulate_cases(values, candidate_formulas, cases, ledger, rules)
        if _passing(candidate_records) > _passing(records):
            patches.append(candidate)
    decision: Literal["REPAIR", "NO_CHANGE"] = "REPAIR" if patches else "NO_CHANGE"
    result = AuditResult(
        run_id=run_id,
        method="direct-agent-baseline",
        source_workbook=str(workbook.resolve()),
        source_sha256=safety["sha256"],
        rules_sha256=object_hash([rule.rule_id for rule in rules]),
        tests=records,
        patches=patches,
        decision=decision,
        artifact_dir=str(run_dir.resolve()),
        budget=ledger.to_dict(),
    )
    trajectory.record("direct-agent", "DIRECT_REPAIR", formulas, formula_diff(patches))
    write_rules_yaml(run_dir / "rules.yaml", rules)
    write_json(run_dir / "formula-diff.json", formula_diff(patches))
    if patches and reviewer:
        approval = {
            "actor": reviewer,
            "source_sha256": result.source_sha256,
            "patch_hash": object_hash(formula_diff(patches)),
            "decision": "APPROVE",
        }
        result.approval_hash = object_hash(approval)
        output = run_dir / "repaired.xlsx"
        patch_workbook(
            workbook,
            output,
            {patch.cell: (patch.old_formula, patch.new_formula) for patch in patches},
            [["No structured counterexamples in direct-agent baseline"]],
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
    elif not patches:
        result.output_workbook = str(workbook.resolve())
    write_json(run_dir / "report.json", portable_audit_payload(result))
    return result
