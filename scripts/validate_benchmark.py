"""Author-side benchmark mutation and oracle-independence validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from formulawitness.benchmark import held_out_cases
from formulawitness.formula import evaluate_cells
from formulawitness.ooxml import formula_map, inspect_safety, sheet_cells
from formulawitness.oracle import evaluate_policy
from formulawitness.policy import CORE_OUTPUTS, INPUT_CELL_MAP


def differs(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    for cell in CORE_OUTPUTS:
        if cell == "T6":
            if actual[cell] != expected[cell]:
                return True
        elif abs(float(actual[cell]) - float(expected[cell])) > 1e-8:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("artifacts/benchmark-validation.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    pristine = root / "workbooks/reference/supplier_rebate_pristine.xlsx"
    pristine_formulas = formula_map(pristine)
    cases = held_out_cases()
    results: list[dict[str, Any]] = []
    for workbook in sorted((root / "workbooks/mutants").glob("M*.xlsx")):
        inspect_safety(workbook)
        values, formulas = sheet_cells(workbook, "RebateCalc")
        changed = [cell for cell in CORE_OUTPUTS if formulas[cell] != pristine_formulas[cell]]
        kills = 0
        for case in cases:
            overrides = {
                INPUT_CELL_MAP[name]: value
                for name, value in case.inputs.items()
                if name in INPUT_CELL_MAP
            }
            outputs, _ = evaluate_cells(values, formulas, overrides)
            if differs(outputs, evaluate_policy(case.inputs)):
                kills += 1
        results.append(
            {
                "case": workbook.stem.split("_")[0],
                "changed_cells": changed,
                "hidden_vectors_killed": kills,
            }
        )
    failures = [
        item
        for item in results
        if len(item["changed_cells"]) != 1 or item["hidden_vectors_killed"] < 2
    ]
    payload = {
        "schema_version": 1,
        "hidden_case_count": len(cases),
        "mutants": results,
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
    }
    output = (root / args.output).resolve() if not args.output.is_absolute() else args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
