"""Fair single-pass direct-repair baseline without structured experimentation."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .artifacts import formula_diff, report_rows, write_json
from .models import AuditResult, Patch
from .ooxml import formula_map, inspect_safety, patch_workbook
from .policy import extract_rules, verify_citations, write_rules_yaml
from .trace import Trajectory, object_hash


def _direct_candidate(formulas: dict[str, str]) -> Patch | None:
    substitutions = (
        (
            "N6",
            "<=100000",
            "<100000",
            ("RB-102",),
            "Policy says the first upper boundary is strict.",
        ),
        (
            "N6",
            "<=250000",
            "<250000",
            ("RB-102",),
            "Policy says the second upper boundary is strict.",
        ),
        (
            "N6",
            "<=500000",
            "<500000",
            ("RB-102",),
            "Policy says the third upper boundary is strict.",
        ),
        ("P6", "H6<=0.95", "H6<0.95", ("RB-202",), "95% is explicitly not a delivery breach."),
        ("P6", "I6>=0.02", "I6>0.02", ("RB-202",), "2% is explicitly not a quality breach."),
        ("P6", "J6>1", "J6>=1", ("RB-201",), "One or more incidents triggers exclusion."),
        ("P6", "),0.5,IF(OR", "),0.6,IF(OR", ("RB-202",), "The both-breach multiplier is 0.60."),
        ("Q6", "M6<=90", "M6<90", ("RB-205",), "The tenure reduction applies below 90 days."),
    )
    for cell, old_fragment, new_fragment, rules, reason in substitutions:
        formula = formulas.get(cell, "")
        if old_fragment in formula:
            return Patch(
                cell, formula, formula.replace(old_fragment, new_fragment, 1), rules, reason
            )
    return None


def run_baseline(
    workbook: Path,
    policy_pdf: Path,
    artifact_root: Path,
    reviewer: str | None = None,
) -> AuditResult:
    safety = inspect_safety(workbook)
    rules = extract_rules(policy_pdf)
    verify_citations(policy_pdf, rules)
    formulas = formula_map(workbook)
    run_id = "baseline-" + hashlib.sha256(f"{safety['sha256']}|direct-v1".encode()).hexdigest()[:12]
    run_dir = artifact_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    trajectory = Trajectory(run_dir / "trajectory.jsonl", run_id)
    trajectory.record(
        "direct-agent", "INGEST", {"workbook": safety["sha256"]}, {"formula_count": len(formulas)}
    )
    candidate = _direct_candidate(formulas)
    patches = [candidate] if candidate else []
    decision = "REPAIR" if patches else "NO_CHANGE"
    result = AuditResult(
        run_id=run_id,
        method="direct-agent-baseline",
        source_workbook=str(workbook.resolve()),
        source_sha256=safety["sha256"],
        rules_sha256=object_hash([rule.rule_id for rule in rules]),
        patches=patches,
        decision=decision,
        artifact_dir=str(run_dir.resolve()),
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
    write_json(run_dir / "report.json", result.to_dict())
    return result
