"""Measure representative ClauseGrid task runtime without reusing run artifacts."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from formulawitness.advanced import run_advanced
from formulawitness.baseline import run_baseline
from formulawitness.models import AuditResult

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
POLICY = ROOT / "policies/supplier_rebate_sla_policy.pdf"


def _measure(runner: Callable[..., AuditResult], repetitions: int, method: str) -> dict[str, Any]:
    samples: list[float] = []
    decisions: list[str] = []
    for index in range(repetitions):
        with tempfile.TemporaryDirectory(prefix=f"formulawitness-runtime-{method}-") as directory:
            started = time.perf_counter()
            result = runner(
                WORKBOOK,
                POLICY,
                Path(directory),
                reviewer=f"runtime-reviewer-{index + 1}",
            )
            samples.append(time.perf_counter() - started)
            decisions.append(result.decision)
    return {
        "repetitions": repetitions,
        "seconds": [round(sample, 6) for sample in samples],
        "median_seconds_per_task": round(statistics.median(samples), 6),
        "min_seconds_per_task": round(min(samples), 6),
        "max_seconds_per_task": round(max(samples), 6),
        "decisions": decisions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/submission/performance-results.json",
    )
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be at least 1")

    baseline = _measure(run_baseline, args.repetitions, "baseline")
    advanced = _measure(run_advanced, args.repetitions, "advanced")
    payload = {
        "schema_version": 1,
        "task": "M10 waiver-scope audit and repair",
        "workbook": WORKBOOK.name,
        "measurement": "end-to-end automated wall-clock time from call to final result",
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor() or "not reported by operating system",
        },
        "baseline": baseline,
        "advanced": advanced,
        "model_api_cost_usd_per_task": {"baseline": 0.0, "advanced": 0.0},
        "compute_cost_note": "Local compute was not monetized.",
        "human_time_per_task": {
            "status": "not_measured",
            "reason": "No qualified-reviewer timing study has been run; no time-saving claim is made.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
