"""Subprocess boundary for deterministic, allowlisted workbook execution."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .models import ExecutionResult, FormulaOverride, SandboxExperimentResult


class ExecutionFailed(RuntimeError):
    pass


def _execute_request(
    workbook: Path,
    payload: dict[str, Any],
    timeout_seconds: float,
    *,
    worker_module: str = "formulawitness.worker",
) -> dict[str, Any]:
    request = json.dumps({"workbook": str(workbook.resolve()), **payload})
    package_root = str(Path(__file__).resolve().parents[1])
    inherited_pythonpath = os.environ.get("PYTHONPATH", "")
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": package_root
        + (os.pathsep + inherited_pythonpath if inherited_pythonpath else ""),
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
    }
    with tempfile.TemporaryDirectory(prefix="formulawitness-worker-") as working_directory:
        try:
            completed = subprocess.run(
                [sys.executable, "-m", worker_module],
                input=request,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                cwd=working_directory,
                env=environment,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExecutionFailed(
                f"Worker exceeded the {timeout_seconds:g}-second execution limit"
            ) from exc
        except OSError as exc:
            raise ExecutionFailed(f"Worker could not start: {type(exc).__name__}") from exc
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ExecutionFailed(f"Worker returned invalid JSON: {completed.stderr[-500:]}") from exc
    if completed.returncode != 0 or not payload.get("ok"):
        raise ExecutionFailed(payload.get("error", completed.stderr[-500:]))
    return payload


def execute(
    workbook: Path, inputs: dict[str, Any], timeout_seconds: float = 8.0
) -> ExecutionResult:
    payload = _execute_request(workbook, {"inputs": inputs}, timeout_seconds)
    result = payload["results"][0]
    return ExecutionResult(
        workbook_sha256=payload["workbook_sha256"],
        inputs=result["inputs"],
        outputs=result["outputs"],
        formulas=payload["formulas"],
        dependencies=payload["dependencies"],
        elapsed_ms=payload["elapsed_ms"],
    )


def execute_batch(
    workbook: Path,
    input_cases: list[dict[str, Any]],
    timeout_seconds: float = 12.0,
) -> list[ExecutionResult]:
    payload = _execute_request(workbook, {"cases": input_cases}, timeout_seconds)
    return [
        ExecutionResult(
            workbook_sha256=payload["workbook_sha256"],
            inputs=result["inputs"],
            outputs=result["outputs"],
            formulas=payload["formulas"],
            dependencies=payload["dependencies"],
            elapsed_ms=payload["elapsed_ms"],
        )
        for result in payload["results"]
    ]


def execute_experiment(
    workbook: Path,
    *,
    sheet: str,
    overrides: dict[str, Any],
    observations: list[str] | tuple[str, ...],
    formula_overrides: list[FormulaOverride] | tuple[FormulaOverride, ...] = (),
    timeout_seconds: float = 8.0,
) -> SandboxExperimentResult:
    """Evaluate explicit cells and staged formulas in an isolated, policy-agnostic worker."""

    payload = _execute_request(
        workbook,
        {
            "sheet": sheet,
            "overrides": overrides,
            "observations": list(observations),
            "formula_overrides": [
                {
                    "cell": item.cell,
                    "old_formula_sha256": item.old_formula_sha256,
                    "new_formula": item.new_formula,
                }
                for item in formula_overrides
            ],
        },
        timeout_seconds,
        worker_module="formulawitness.experiment_worker",
    )
    return SandboxExperimentResult(
        workbook_sha256=payload["workbook_sha256"],
        sheet=payload["sheet"],
        observations=payload["observations"],
        dependencies=payload["dependencies"],
        formula_sha256=payload["formula_sha256"],
        applied_formula_overrides=tuple(payload["applied_formula_overrides"]),
        elapsed_ms=payload["elapsed_ms"],
    )
