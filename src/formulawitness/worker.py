"""No-network-by-design workbook formula worker invoked in a separate process."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .formula import evaluate_cells
from .ooxml import inspect_safety, sheet_cells
from .policy import CORE_OUTPUTS, INPUT_CELL_MAP


def main() -> int:
    started = time.perf_counter()
    try:
        request = json.loads(sys.stdin.read())
        workbook = Path(request["workbook"]).resolve()
        safety = inspect_safety(workbook)
        values, formulas = sheet_cells(workbook, "RebateCalc")
        input_cases = request.get("cases", [request.get("inputs", {})])
        results = []
        for inputs in input_cases:
            overrides = {
                INPUT_CELL_MAP[name]: value
                for name, value in inputs.items()
                if name in INPUT_CELL_MAP
            }
            calculated, dependencies = evaluate_cells(values, formulas, overrides)
            results.append(
                {
                    "inputs": inputs,
                    "outputs": {cell: calculated[cell] for cell in CORE_OUTPUTS},
                }
            )
        response = {
            "ok": True,
            "workbook_sha256": safety["sha256"],
            "results": results,
            "formulas": {cell: formulas[cell] for cell in CORE_OUTPUTS},
            "dependencies": {cell: dependencies[cell] for cell in CORE_OUTPUTS},
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001 - process boundary must fail closed
        response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    sys.stdout.write(json.dumps(response, sort_keys=True))
    return 0 if response["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
