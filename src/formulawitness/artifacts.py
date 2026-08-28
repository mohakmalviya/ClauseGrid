"""Evidence pack generation for audit and review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import AuditResult, Patch, Rule, TestCase


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def portable_audit_payload(result: AuditResult) -> dict[str, Any]:
    """Serialize an audit without host-specific absolute paths."""

    payload = result.to_dict()
    payload["source_workbook"] = Path(result.source_workbook).name
    payload["artifact_dir"] = "."
    payload["output_workbook"] = "repaired.xlsx" if result.output_workbook else None
    return payload


def formula_diff(patches: list[Patch]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "changed_cell_count": len(patches),
        "changes": [
            {
                "cell": patch.cell,
                "before": patch.old_formula,
                "after": patch.new_formula,
                "rule_ids": list(patch.rule_ids),
                "rationale": patch.rationale,
            }
            for patch in patches
        ],
    }


def evidence_graph(
    rules: list[Rule], tests: list[dict[str, Any]], patches: list[Patch]
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for rule in rules:
        nodes.append(
            {
                "id": f"rule:{rule.rule_id}",
                "type": "rule",
                "label": rule.title,
                "page": rule.evidence.page,
            }
        )
    for test in tests:
        case_id = test["case_id"]
        nodes.append(
            {
                "id": f"case:{case_id}",
                "type": "counterexample",
                "label": test["category"],
                "status": test["status"],
            }
        )
        for rule_id in test["rule_ids"]:
            edges.append({"from": f"rule:{rule_id}", "to": f"case:{case_id}", "type": "generates"})
        for cell in test["mismatched_cells"]:
            node_id = f"cell:{cell}"
            if not any(node["id"] == node_id for node in nodes):
                nodes.append({"id": node_id, "type": "formula_cell", "label": cell})
            edges.append({"from": f"case:{case_id}", "to": node_id, "type": "fails_at"})
    for patch in patches:
        patch_id = f"patch:{patch.cell}"
        nodes.append({"id": patch_id, "type": "patch", "label": patch.cell})
        edges.append({"from": f"cell:{patch.cell}", "to": patch_id, "type": "repairs"})
        for rule_id in patch.rule_ids:
            edges.append({"from": f"rule:{rule_id}", "to": patch_id, "type": "supports"})
    return {"schema_version": 1, "nodes": nodes, "edges": edges}


def counterexample_rows(tests: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = [
        ["Case", "Category", "Rule IDs", "Status", "Mismatch cells", "Inputs", "Expected", "Actual"]
    ]
    for test in tests:
        inputs = test["inputs"]
        key_inputs = "; ".join(
            [
                f"gross={inputs['gross_eligible_invoices']}",
                f"returns={inputs['returns_credits']}",
                f"pass_through={inputs['pass_through_charges']}",
                f"on_time={inputs['on_time_rate']}",
                f"defect={inputs['defect_rate']}",
                f"incidents={inputs['critical_incidents']}",
                f"waiver={inputs['critical_waiver']}",
                f"contract_start={inputs['contract_start']}",
            ]
        )
        focus = test["mismatched_cells"] or ["S6", "T6"]
        expected = "; ".join(f"{cell}={test['expected'][cell]}" for cell in focus)
        actual = "; ".join(f"{cell}={test['actual'][cell]}" for cell in focus)
        rows.append(
            [
                test["case_id"],
                test["category"],
                ", ".join(test["rule_ids"]),
                test["status"],
                ", ".join(test["mismatched_cells"]),
                key_inputs,
                expected,
                actual,
            ]
        )
    return rows


def report_rows(report: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = [["FormulaWitness review report", "Value"]]
    for key in ("run_id", "method", "decision", "source_sha256", "rules_sha256", "approval_hash"):
        rows.append([key, report.get(key, "")])
    rows.append(["changed_cell_count", len(report.get("patches", []))])
    rows.append(["visible_cases", len(report.get("tests", []))])
    rows.append(
        ["note", "Source workbook preserved; this copy contains reviewer-approved changes only."]
    )
    return rows


def test_record(
    case: TestCase, expected: dict[str, Any], actual: dict[str, Any], mismatches: list[str]
) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "category": case.category,
        "rule_ids": list(case.provenance_rule_ids),
        "inputs": case.inputs,
        "expected": expected,
        "actual": actual,
        "mismatched_cells": mismatches,
        "status": "FAIL" if mismatches else "PASS",
    }
