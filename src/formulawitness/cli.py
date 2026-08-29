"""Command-line interface for FormulaWitness."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

from .advanced import run_advanced
from .agent_evaluation import (
    DEFAULT_AGENT_EVALUATION_CASES,
    MINIMUM_AGENT_EVALUATION_TRIALS,
    run_agent_evaluation,
)
from .agentic import approve_agentic_proposal, run_agentic, run_agentic_baseline
from .baseline import run_baseline
from .model_client import (
    ModelClient,
    ModelConfigurationError,
)
from .ooxml import inspect_safety
from .providers import PROVIDER_PRESETS, build_model_client
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


def _add_model_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--provider",
        choices=tuple(PROVIDER_PRESETS),
        default="nvidia-nim",
        help=(
            "Model API provider. 'claude' is an alias for Anthropic; "
            "openai-compatible requires --base-url and --api-key-env"
        ),
    )
    parser.add_argument("--base-url")
    parser.add_argument(
        "--model",
        required=True,
        help="Explicit provider model ID; no model is selected implicitly",
    )
    parser.add_argument("--api-key-env")
    parser.add_argument(
        "--allow-external-processing",
        action="store_true",
        help=(
            "Explicitly allow sending workbook/policy-derived content to a non-loopback "
            "model endpoint"
        ),
    )


def _is_loopback_model_endpoint(base_url: str) -> bool:
    """Validate enough endpoint structure to gate consent before credential access."""

    parsed = urlsplit(base_url)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ModelConfigurationError("Model base URL must be a plain absolute service endpoint")
    loopback = parsed.hostname.casefold() in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise ModelConfigurationError(
            "Model base URL requires HTTPS except for loopback development"
        )
    return loopback


def _configured_model(args: argparse.Namespace) -> tuple[ModelClient, str, str]:
    """Build one server-side model client without accepting credential values as arguments."""

    preset = PROVIDER_PRESETS[str(args.provider)]
    base_url = args.base_url or preset.base_url
    if base_url is None:
        raise ModelConfigurationError("--base-url is required for --provider openai-compatible")
    if not _is_loopback_model_endpoint(base_url) and not args.allow_external_processing:
        raise ModelConfigurationError(
            "Remote model processing requires --allow-external-processing before credentials "
            "are loaded"
        )
    try:
        client, canonical_provider = build_model_client(
            provider=str(args.provider),
            model=args.model,
            base_url=base_url,
            api_key_env=args.api_key_env,
        )
    except ValueError as exc:
        raise ModelConfigurationError(str(exc)) from None
    return client, canonical_provider, str(args.model)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="formulawitness",
        description="Policy-grounded semantic repair for controlled .xlsx workbooks",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="Run fail-closed workbook safety checks")
    inspect_parser.add_argument("workbook", type=Path)
    baseline_parser = subparsers.add_parser(
        "baseline", help="Run the legacy deterministic direct baseline"
    )
    _add_common(baseline_parser)
    advanced_parser = subparsers.add_parser(
        "advanced", help="Run the legacy deterministic FormulaWitness workflow"
    )
    _add_common(advanced_parser)
    agent_parser = subparsers.add_parser(
        "agent", help="Run the model-directed manager/falsifier proposal pipeline"
    )
    agent_parser.add_argument("workbook", type=Path)
    agent_parser.add_argument(
        "--policy", type=Path, default=_root() / "policies/supplier_rebate_sla_policy.pdf"
    )
    agent_parser.add_argument("--artifacts", type=Path, default=_root() / "artifacts/runs")
    _add_model_options(agent_parser)
    agent_baseline_parser = subparsers.add_parser(
        "agent-baseline", help="Run the fair one-candidate model-agent comparison"
    )
    agent_baseline_parser.add_argument("workbook", type=Path)
    agent_baseline_parser.add_argument(
        "--policy", type=Path, default=_root() / "policies/supplier_rebate_sla_policy.pdf"
    )
    agent_baseline_parser.add_argument("--artifacts", type=Path, default=_root() / "artifacts/runs")
    _add_model_options(agent_baseline_parser)
    approve_agent_parser = subparsers.add_parser(
        "approve-agent", help="Apply one exact reviewed agent proposal to a workbook copy"
    )
    approve_agent_parser.add_argument("run_id")
    approve_agent_parser.add_argument("workbook", type=Path)
    approve_agent_parser.add_argument(
        "--policy", type=Path, default=_root() / "policies/supplier_rebate_sla_policy.pdf"
    )
    approve_agent_parser.add_argument("--artifacts", type=Path, default=_root() / "artifacts/runs")
    approve_agent_parser.add_argument("--proposal-hash", required=True)
    approve_agent_parser.add_argument("--reviewer", required=True)
    eval_parser = subparsers.add_parser("eval", help="Run the frozen baseline/advanced benchmark")
    eval_parser.add_argument("--output", type=Path, default=_root() / "evals/results.json")
    agent_eval_parser = subparsers.add_parser(
        "agent-eval",
        help="Run repeated blind single-agent vs manager/falsifier model trials",
    )
    agent_eval_parser.add_argument(
        "--cases",
        nargs="+",
        default=list(DEFAULT_AGENT_EVALUATION_CASES),
        metavar="CASE",
        help="Unique public workbook case IDs (default: M10 H01 C03)",
    )
    agent_eval_parser.add_argument(
        "--trials",
        type=int,
        default=MINIMUM_AGENT_EVALUATION_TRIALS,
        help="Trials per case per mode; must be at least 5",
    )
    agent_eval_parser.add_argument(
        "--artifacts",
        type=Path,
        default=_root() / "artifacts/agent-evaluation",
    )
    agent_eval_parser.add_argument(
        "--output",
        type=Path,
        default=_root() / "evals/agent-results.json",
    )
    _add_model_options(agent_eval_parser)
    demo_parser = subparsers.add_parser(
        "demo", help="Run the model-directed difficult waiver-scope proposal demo"
    )
    demo_parser.add_argument("--artifacts", type=Path, default=_root() / "artifacts/demo")
    _add_model_options(demo_parser)
    serve_parser = subparsers.add_parser("serve", help="Start the local review interface")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    _add_model_options(serve_parser)
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
    if args.command in {"agent", "agent-baseline"}:
        model_client, _, model_id = _configured_model(args)
        try:
            agent_runner = run_agentic if args.command == "agent" else run_agentic_baseline
            agent_result = agent_runner(
                args.workbook,
                args.policy,
                args.artifacts,
                model=model_client,
                model_id=model_id,
            )
        finally:
            model_client.close()
        print(json.dumps(agent_result.to_dict(), indent=2, default=str))
        return 0 if agent_result.decision != "REJECT" else 2
    if args.command == "approve-agent":
        approved = approve_agentic_proposal(
            args.workbook,
            args.policy,
            args.artifacts,
            args.run_id,
            reviewer=args.reviewer,
            expected_proposal_hash=args.proposal_hash,
        )
        print(json.dumps(approved.to_dict(), indent=2, default=str))
        return 0
    if args.command == "eval":
        # Keep sealed-evaluator code out of model-agent command startup.
        from .evaluation import run_evaluation

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
    if args.command == "agent-eval":
        model_client, provider, model_id = _configured_model(args)
        try:
            agent_evaluation = run_agent_evaluation(
                root,
                args.output,
                args.artifacts,
                model=model_client,
                provider=provider,
                model_id=model_id,
                cases=args.cases,
                trials=args.trials,
            )
        finally:
            model_client.close()
        methods = agent_evaluation["aggregate"]["methods"]
        print(
            json.dumps(
                {
                    "single_agent_success": methods["single-agent"]["success"],
                    "manager_falsifier_success": methods["manager-falsifier"]["success"],
                    "improvement": agent_evaluation["aggregate"]["improvement"],
                    "isolation_proof": agent_evaluation["isolation_proof"],
                    "output": str(args.output.resolve()),
                },
                indent=2,
            )
        )
        return 0
    if args.command == "demo":
        workbook = root / "workbooks/mutants/M10_supplier_rebate.xlsx"
        model_client, _, model_id = _configured_model(args)
        try:
            demo_result = run_agentic(
                workbook,
                root / "policies/supplier_rebate_sla_policy.pdf",
                args.artifacts,
                model=model_client,
                model_id=model_id,
            )
        finally:
            model_client.close()
        print(json.dumps(demo_result.to_dict(), indent=2, default=str))
        return 0
    if args.command == "serve":
        from .ui import serve

        model_client, provider, model_id = _configured_model(args)
        try:
            serve(
                root,
                args.host,
                args.port,
                model=model_client,
                provider=provider,
                model_id=model_id,
            )
        finally:
            model_client.close()
        return 0
    if args.command in {"verify-trajectory", "replay"}:
        print(json.dumps(verify_trajectory(args.trajectory), indent=2))
        return 0
    raise AssertionError(args.command)
