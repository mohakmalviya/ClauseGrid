"""Command-line interface for FormulaWitness."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .advanced import run_advanced
from .baseline import run_baseline
from .evaluation import run_evaluation
from .ooxml import inspect_safety
from .trace import verify_trajectory


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("workbook", type=Path)
    parser.add_argument(
        "--policy", type=Path, default=_root() / "policies/supplier_rebate_sla_policy.pdf"
    )
    parser.add_argument("--artifacts", type=Path, default=_root() / "artifacts/runs")
    parser.add_argument(
        "--reviewer", help="Reviewer identity; omit to stop before writing a repair"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="formulawitness",
        description="Policy-grounded semantic repair for controlled .xlsx workbooks",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="Run fail-closed workbook safety checks")
    inspect_parser.add_argument("workbook", type=Path)
    baseline_parser = subparsers.add_parser("baseline", help="Run the direct-agent baseline")
    _add_common(baseline_parser)
    advanced_parser = subparsers.add_parser("advanced", help="Run the FormulaWitness workflow")
    _add_common(advanced_parser)
    eval_parser = subparsers.add_parser("eval", help="Run the frozen baseline/advanced benchmark")
    eval_parser.add_argument("--output", type=Path, default=_root() / "evals/results.json")
    demo_parser = subparsers.add_parser(
        "demo", help="Run the end-to-end difficult waiver-scope demo"
    )
    demo_parser.add_argument("--artifacts", type=Path, default=_root() / "artifacts/demo")
    demo_parser.add_argument("--reviewer", default="demo-reviewer")
    serve_parser = subparsers.add_parser("serve", help="Start the local review interface")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    trajectory_parser = subparsers.add_parser(
        "verify-trajectory",
        aliases=["replay"],
        help="Verify a JSONL trajectory hash chain (does not rerun the agent)",
    )
    trajectory_parser.add_argument("trajectory", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _root()
    if args.command == "inspect":
        print(json.dumps(inspect_safety(args.workbook), indent=2))
        return 0
    if args.command in {"baseline", "advanced"}:
        runner = run_baseline if args.command == "baseline" else run_advanced
        audit_result = runner(args.workbook, args.policy, args.artifacts, reviewer=args.reviewer)
        print(json.dumps(audit_result.to_dict(), indent=2, default=str))
        return 0 if audit_result.decision != "REJECT" else 2
    if args.command == "eval":
        evaluation_result = run_evaluation(root, args.output)
        print(
            json.dumps(
                {
                    "baseline_e2e_srr": evaluation_result["baseline"]["e2e_semantic_repair_rate"],
                    "advanced_e2e_srr": evaluation_result["advanced"]["e2e_semantic_repair_rate"],
                    "improvement_pp": evaluation_result["improvement_percentage_points"],
                    "advanced_clean_preservation": evaluation_result["advanced"][
                        "clean_preservation_rate"
                    ],
                    "output": str(args.output.resolve()),
                },
                indent=2,
            )
        )
        return 0 if all(evaluation_result["acceptance"].values()) else 1
    if args.command == "demo":
        workbook = root / "workbooks/mutants/M10_supplier_rebate.xlsx"
        demo_result = run_advanced(
            workbook,
            root / "policies/supplier_rebate_sla_policy.pdf",
            args.artifacts,
            reviewer=args.reviewer,
        )
        print(json.dumps(demo_result.to_dict(), indent=2, default=str))
        return 0
    if args.command == "serve":
        from .ui import serve

        serve(root, args.host, args.port)
        return 0
    if args.command in {"verify-trajectory", "replay"}:
        print(json.dumps(verify_trajectory(args.trajectory), indent=2))
        return 0
    raise AssertionError(args.command)
