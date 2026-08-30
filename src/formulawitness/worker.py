"""No-network-by-design workbook formula worker invoked in a separate process."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .formula import evaluate_cells
from .ooxml import calculation_cells, inspect_safety
from .policy import CORE_OUTPUTS, workbook_input_overrides


def main() -> int:
    started = time.perf_counter()
    try:
        request = json.loads(sys.stdin.read())
        workbook = Path(request["workbook"]).resolve()
        from .path_guard import restrict_file_access

        restrict_file_access(readable_files=(workbook,), writable_roots=(Path.cwd(),))
        safety = inspect_safety(workbook)
        values, formulas = calculation_cells(workbook)
        input_cases = request.get("cases", [request.get("inputs", {})])
        results = []
        for inputs in input_cases:
            overrides = workbook_input_overrides(inputs)
            calculated, dependencies = evaluate_cells(
                values, formulas, overrides, active_sheet="RebateCalc"
            )
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
