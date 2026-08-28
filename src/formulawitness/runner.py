"""Subprocess boundary for deterministic, allowlisted workbook execution."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .models import ExecutionResult


class ExecutionFailed(RuntimeError):
    pass


def _execute_request(
    workbook: Path, payload: dict[str, Any], timeout_seconds: float
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
        completed = subprocess.run(
            [sys.executable, "-m", "formulawitness.worker"],
            input=request,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            cwd=working_directory,
            env=environment,
            check=False,
        )
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
