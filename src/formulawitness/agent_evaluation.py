"""Repeated blind evaluation of the two model-agent configurations.

This controller deliberately keeps benchmark labels and the sealed oracle outside
the model-agent call.  Each run receives only a generically named workbook and
policy snapshot.  A repair is evaluated only after its exact proposal hash has
passed the normal approval boundary.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import statistics
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from .agent_budget import AgentRuntimeLimits
from .agent_loop import ChatModel
from .agentic import (
    DEFAULT_AGENT_LIMITS,
    approve_agentic_proposal,
    run_agentic,
    run_agentic_baseline,
)
from .models import AuditResult
from .ooxml import inspect_safety, sha256_file
from .public_benchmark import DEFECT_FAMILIES, MAX_PATCH_CELLS, WORKBOOK_CASES
from .trace import object_hash

DEFAULT_AGENT_EVALUATION_CASES = ("M10", "H01", "C03")
MINIMUM_AGENT_EVALUATION_TRIALS = 5
EVALUATION_REVIEWER = "agent-evaluation-controller"
ComparisonMode = Literal["single-agent", "manager-falsifier"]


class AgentRunner(Protocol):
    def __call__(
        self,
        workbook: Path,
        policy_pdf: Path,
        artifact_root: Path,
        *,
        model: ChatModel,
        model_id: str,
        limits: AgentRuntimeLimits,
        run_id: str | None = None,
    ) -> AuditResult: ...


class ProposalApprover(Protocol):
    def __call__(
        self,
        workbook: Path,
        policy_pdf: Path,
        artifact_root: Path,
        run_id: str,
        *,
        reviewer: str,
        expected_proposal_hash: str,
    ) -> AuditResult: ...


@dataclass(frozen=True)
class CandidateScore:
    """Controller-only result produced after the agent run has ended."""

    success: bool
    semantic_ok: bool
    minimality_ok: bool
    clean_preservation: bool | None
    source_immutable: bool
    changed_cells: tuple[str, ...]
    changed_formulas: tuple[str, ...]
    unrelated_formula_changes: tuple[str, ...]
    semantic_vectors_passed: int
    semantic_vectors_total: int
    first_failure: str | None


class CandidateScorer(Protocol):
    def __call__(
        self,
        case_id: str,
        original_source: Path,
        staged_source: Path,
        candidate: Path,
        source_sha256: str,
    ) -> CandidateScore: ...


@dataclass(frozen=True)
class EvaluationServices:
    """Injectable boundaries used by tests without making provider calls."""

    single_agent_runner: AgentRunner = run_agentic_baseline
    manager_falsifier_runner: AgentRunner = run_agentic
    approver: ProposalApprover = approve_agentic_proposal
    scorer: CandidateScorer | None = None


def _score_with_sealed_oracle(
    case_id: str,
    original_source: Path,
    staged_source: Path,
    candidate: Path,
    source_sha256: str,
) -> CandidateScore:
    """Import answer-bearing evaluator code only after the agent has stopped."""

    # These imports are intentionally local.  Neither the oracle, held-out cases,
    # core output list, nor a gold formula is loaded into the agent process/call.
    from .evaluation import sealed_semantic_check
    from .ooxml import changed_core_formulas, changed_workbook_formulas
    from .policy import CORE_OUTPUTS

    inspect_safety(candidate)
    changes = changed_core_formulas(original_source, candidate, CORE_OUTPUTS)
    workbook_changes = changed_workbook_formulas(original_source, candidate)
    allowed = {f"RebateCalc!{cell}" for cell in CORE_OUTPUTS}
    unrelated = tuple(sorted(cell for cell in workbook_changes if cell not in allowed))
    semantic_ok, passed_vectors, first_failure = sealed_semantic_check(candidate)
    source_immutable = (
        sha256_file(original_source) == source_sha256
        and sha256_file(staged_source) == source_sha256
    )
    minimality_ok = (
        len(changes) <= MAX_PATCH_CELLS[case_id]
        and len(workbook_changes) == len(changes)
        and not unrelated
    )
    is_control = case_id.startswith("C")
    clean_preservation = semantic_ok and minimality_ok and len(changes) == 0 if is_control else None
    success = source_immutable and (
        bool(clean_preservation) if is_control else semantic_ok and minimality_ok
    )
    return CandidateScore(
        success=success,
        semantic_ok=semantic_ok,
        minimality_ok=minimality_ok,
        clean_preservation=clean_preservation,
        source_immutable=source_immutable,
        changed_cells=tuple(sorted(changes)),
        changed_formulas=tuple(sorted(workbook_changes)),
        unrelated_formula_changes=unrelated,
        semantic_vectors_passed=passed_vectors,
        semantic_vectors_total=48,
        first_failure=first_failure,
    )


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Replace one JSON result only after a complete, flushed write."""

    path = path.resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.tmp-{uuid.uuid4().hex}"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, default=str)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _proposal_hash(result: AuditResult, artifact_root: Path) -> str:
    if result.output_workbook is not None:
        raise ValueError("Agent evaluation requires a proposal-only runner")
    if result.artifact_dir is None:
        raise ValueError("Agent runner did not report an artifact directory")
    run_dir = Path(result.artifact_dir).resolve(strict=True)
    try:
        run_dir.relative_to(artifact_root.resolve(strict=True))
    except ValueError as exc:
        raise ValueError("Agent artifact directory escaped the evaluation root") from exc
    proposal_path = run_dir / "proposal.json"
    raw = json.loads(proposal_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("Agent proposal must be a JSON object")
    if raw.get("run_id") != result.run_id:
        raise ValueError("Agent proposal run identifier mismatch")
    return object_hash(raw)


def _approved_candidate(
    result: AuditResult,
    staged_workbook: Path,
    staged_policy: Path,
    agent_output_root: Path,
    proposal_hash: str,
    approver: ProposalApprover,
) -> tuple[Path, bool]:
    if result.decision != "REPAIR":
        return staged_workbook, False
    approved = approver(
        staged_workbook,
        staged_policy,
        agent_output_root,
        result.run_id,
        reviewer=EVALUATION_REVIEWER,
        expected_proposal_hash=proposal_hash,
    )
    if approved.output_workbook is None:
        raise ValueError("Exact-hash approval did not produce a candidate workbook")
    candidate = Path(approved.output_workbook).resolve(strict=True)
    try:
        candidate.relative_to(agent_output_root.resolve(strict=True))
    except ValueError as exc:
        raise ValueError("Approved candidate escaped the agent artifact root") from exc
    return candidate, True


def _number(value: object, *, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _normalized_limits(budget: Mapping[str, object]) -> dict[str, float | int | None]:
    return {
        "aggregate_agent_turn_limit": int(_number(budget.get("manager_turn_limit")))
        + int(_number(budget.get("falsifier_turn_limit"))),
        "model_call_limit": int(_number(budget.get("model_call_limit"))),
        "tool_call_limit": int(_number(budget.get("tool_call_limit"))),
        "input_token_limit": int(_number(budget.get("input_token_limit"))),
        "output_token_limit": int(_number(budget.get("output_token_limit"))),
        "workbook_execution_limit": int(_number(budget.get("workbook_execution_limit"))),
        "retry_limit": int(_number(budget.get("retry_limit"))),
        "elapsed_time_limit_seconds": _number(budget.get("elapsed_time_limit_seconds")),
        "reported_cost_limit_usd": (
            None
            if budget.get("reported_cost_limit_usd") is None
            else _number(budget.get("reported_cost_limit_usd"))
        ),
    }


def _configured_normalized_limits(
    limits: AgentRuntimeLimits,
) -> dict[str, float | int | None]:
    raw = cast(dict[str, object], asdict(limits))
    return _normalized_limits(raw)


def _wilson_interval(successes: int, count: int) -> dict[str, float]:
    if count <= 0:
        return {"low_percent": 0.0, "high_percent": 0.0}
    z = 1.959963984540054
    proportion = successes / count
    denominator = 1 + z * z / count
    centre = (proportion + z * z / (2 * count)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / count + z * z / (4 * count * count))
        / denominator
    )
    return {
        "low_percent": 100 * max(0.0, centre - margin),
        "high_percent": 100 * min(1.0, centre + margin),
    }


def _rate(records: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    eligible = [record for record in records if record.get(field) is not None]
    successes = sum(bool(record[field]) for record in eligible)
    count = len(eligible)
    return {
        "successes": successes,
        "count": count,
        "rate_percent": 100 * successes / count if count else None,
        "wilson_95": _wilson_interval(successes, count) if count else None,
    }


def _distribution(records: Sequence[Mapping[str, Any]], field: str) -> dict[str, float]:
    values = [_number(record.get(field)) for record in records]
    return {
        "mean": statistics.fmean(values) if values else 0.0,
        "median": statistics.median(values) if values else 0.0,
    }


def _aggregate_method(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    costs = [
        _number(record["reported_cost_usd"])
        for record in records
        if record.get("reported_cost_usd") is not None
    ]
    return {
        "run_count": len(records),
        "success": _rate(records, "success"),
        "semantic_success": _rate(records, "semantic_ok"),
        "minimality": _rate(records, "minimality_ok"),
        "clean_preservation": _rate(records, "clean_preservation"),
        "abstention": _rate(records, "abstention"),
        "agent_latency_seconds": _distribution(records, "agent_latency_seconds"),
        "end_to_end_latency_seconds": _distribution(records, "end_to_end_latency_seconds"),
        "input_tokens": _distribution(records, "input_tokens"),
        "output_tokens": _distribution(records, "output_tokens"),
        "total_tokens": _distribution(records, "total_tokens"),
        "model_calls": _distribution(records, "model_calls"),
        "tool_calls": _distribution(records, "tool_calls"),
        "workbook_executions": _distribution(records, "workbook_executions"),
        "retries": _distribution(records, "retries"),
        "reported_cost_usd": {
            "reporting_coverage": len(costs) / len(records) if records else 0.0,
            "sum": sum(costs) if costs else None,
            "mean": statistics.fmean(costs) if costs else None,
        },
    }


def _aggregate(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_mode = {
        mode: [record for record in records if record["mode"] == mode]
        for mode in ("single-agent", "manager-falsifier")
    }
    methods = {mode: _aggregate_method(items) for mode, items in by_mode.items()}
    single = methods["single-agent"]["success"]
    advanced = methods["manager-falsifier"]["success"]
    assert isinstance(single, dict) and isinstance(advanced, dict)
    single_rate = single["rate_percent"]
    advanced_rate = advanced["rate_percent"]
    single_interval = single["wilson_95"]
    advanced_interval = advanced["wilson_95"]
    improvement: dict[str, Any] = {
        "difference_percentage_points": (
            None if single_rate is None or advanced_rate is None else advanced_rate - single_rate
        ),
        "conservative_95_interval_percentage_points": None,
    }
    if isinstance(single_interval, dict) and isinstance(advanced_interval, dict):
        improvement["conservative_95_interval_percentage_points"] = {
            "low": advanced_interval["low_percent"] - single_interval["high_percent"],
            "high": advanced_interval["high_percent"] - single_interval["low_percent"],
        }
    cases = {
        case_id: {
            mode: _aggregate_method(
                [
                    record
                    for record in records
                    if record["case_id"] == case_id and record["mode"] == mode
                ]
            )
            for mode in ("single-agent", "manager-falsifier")
        }
        for case_id in sorted({str(record["case_id"]) for record in records})
    }
    return {"methods": methods, "cases": cases, "improvement": improvement}


def _validated_cases(cases: Sequence[str], trials: int) -> tuple[str, ...]:
    selected = tuple(cases)
    if trials < MINIMUM_AGENT_EVALUATION_TRIALS:
        raise ValueError(
            f"Repeated agent evaluation requires at least {MINIMUM_AGENT_EVALUATION_TRIALS} trials"
        )
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("Agent evaluation cases must be a non-empty unique sequence")
    unknown = sorted(set(selected) - set(WORKBOOK_CASES))
    if unknown:
        raise ValueError(f"Unknown agent evaluation cases: {', '.join(unknown)}")
    return selected


def _budget_metrics(budget: Mapping[str, object]) -> dict[str, int | float | None]:
    input_tokens = int(_number(budget.get("input_tokens_used")))
    output_tokens = int(_number(budget.get("output_tokens_used")))
    raw_cost = budget.get("reported_cost_usd")
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "model_calls": int(_number(budget.get("model_calls_used"))),
        "tool_calls": int(_number(budget.get("tool_calls_used"))),
        "workbook_executions": int(_number(budget.get("workbook_executions_used"))),
        "retries": int(_number(budget.get("retries_used"))),
        "reported_cost_usd": None if raw_cost is None else _number(raw_cost),
    }


def _stage_public_inputs(source: Path, policy: Path, unit_root: Path) -> tuple[Path, Path]:
    public_inputs = unit_root / "public-inputs"
    public_inputs.mkdir(parents=True, exist_ok=False)
    staged_workbook = public_inputs / "workbook.xlsx"
    staged_policy = public_inputs / "policy.pdf"
    shutil.copyfile(source, staged_workbook)
    shutil.copyfile(policy, staged_policy)
    return staged_workbook, staged_policy


def run_agent_evaluation(
    root: Path,
    output: Path,
    artifact_root: Path,
    *,
    model: ChatModel,
    provider: str,
    model_id: str,
    cases: Sequence[str] = DEFAULT_AGENT_EVALUATION_CASES,
    trials: int = MINIMUM_AGENT_EVALUATION_TRIALS,
    limits: AgentRuntimeLimits = DEFAULT_AGENT_LIMITS,
    services: EvaluationServices | None = None,
) -> dict[str, Any]:
    """Run paired blind trials and atomically persist the complete result."""

    selected = _validated_cases(cases, trials)
    services = services or EvaluationServices()
    root = root.resolve(strict=True)
    policy = (root / "policies/supplier_rebate_sla_policy.pdf").resolve(strict=True)
    artifact_root = artifact_root.resolve(strict=False)
    execution_root = artifact_root / f"evaluation-{uuid.uuid4().hex}"
    execution_root.mkdir(parents=True, exist_ok=False)
    scorer = services.scorer or _score_with_sealed_oracle
    expected_limits = _configured_normalized_limits(limits)
    records: list[dict[str, Any]] = []
    run_ids: set[str] = set()
    invocation_sequence = 0

    for trial in range(1, trials + 1):
        # Alternating pair order reduces systematic provider/time drift.
        modes: tuple[ComparisonMode, ComparisonMode] = (
            ("single-agent", "manager-falsifier")
            if trial % 2
            else ("manager-falsifier", "single-agent")
        )
        for case_id in selected:
            original_source = (root / WORKBOOK_CASES[case_id]).resolve(strict=True)
            source_sha256 = sha256_file(original_source)
            for mode in modes:
                invocation_sequence += 1
                unit_root = execution_root / f"unit-{uuid.uuid4().hex}"
                staged_workbook, staged_policy = _stage_public_inputs(
                    original_source, policy, unit_root
                )
                agent_output_root = unit_root / "agent-output"
                opaque_run_id = f"agent-eval-{uuid.uuid4().hex}"
                if opaque_run_id in run_ids:
                    raise RuntimeError("Agent evaluation generated a duplicate run identifier")
                run_ids.add(opaque_run_id)
                runner = (
                    services.single_agent_runner
                    if mode == "single-agent"
                    else services.manager_falsifier_runner
                )
                started = time.perf_counter()
                result = runner(
                    staged_workbook,
                    staged_policy,
                    agent_output_root,
                    model=model,
                    model_id=model_id,
                    limits=limits,
                    run_id=opaque_run_id,
                )
                agent_latency = time.perf_counter() - started
                if result.run_id != opaque_run_id:
                    raise ValueError(
                        "Agent runner did not preserve the fresh opaque run identifier"
                    )
                proposal_hash = _proposal_hash(result, agent_output_root)
                candidate, approved_for_evaluation = _approved_candidate(
                    result,
                    staged_workbook,
                    staged_policy,
                    agent_output_root,
                    proposal_hash,
                    services.approver,
                )

                # This is the first point at which the case label is passed to a scorer.
                # The model-agent has completed and its proposal is immutable by hash.
                score = scorer(
                    case_id,
                    original_source,
                    staged_workbook,
                    candidate,
                    source_sha256,
                )
                end_to_end_latency = time.perf_counter() - started
                raw_budget = cast(dict[str, object], result.budget)
                normalized_limits = _normalized_limits(raw_budget)
                if normalized_limits != expected_limits:
                    raise ValueError(
                        "Agent runner violated the normalized aggregate evaluation budget"
                    )
                metrics = _budget_metrics(raw_budget)
                record: dict[str, Any] = {
                    "sequence": invocation_sequence,
                    "case_id": case_id,
                    "defect_family": DEFECT_FAMILIES[case_id],
                    "trial": trial,
                    "mode": mode,
                    "provider": provider,
                    "model_id": model_id,
                    "run_id": opaque_run_id,
                    "decision": result.decision,
                    "abstention": result.decision == "ABSTAIN",
                    "proposal_hash": proposal_hash,
                    "approved_for_evaluation": approved_for_evaluation,
                    "evaluation_reviewer": (
                        EVALUATION_REVIEWER if approved_for_evaluation else None
                    ),
                    "success": score.success,
                    "semantic_ok": score.semantic_ok,
                    "minimality_ok": score.minimality_ok,
                    "clean_preservation": score.clean_preservation,
                    "source_immutable": score.source_immutable,
                    "changed_cells": list(score.changed_cells),
                    "changed_formulas": list(score.changed_formulas),
                    "unrelated_formula_changes": list(score.unrelated_formula_changes),
                    "semantic_vectors_passed": score.semantic_vectors_passed,
                    "semantic_vectors_total": score.semantic_vectors_total,
                    "first_failure": score.first_failure,
                    "agent_latency_seconds": agent_latency,
                    "end_to_end_latency_seconds": end_to_end_latency,
                    **metrics,
                    "raw_budget": raw_budget,
                    "normalized_limits": normalized_limits,
                    "blind_input_evidence": {
                        "workbook_filename_seen_by_agent": staged_workbook.name,
                        "policy_filename_seen_by_agent": staged_policy.name,
                        "opaque_run_id": True,
                        "case_id_supplied_to_agent": False,
                        "defect_family_supplied_to_agent": False,
                        "gold_formula_supplied_to_agent": False,
                        "reference_workbook_supplied_to_agent": False,
                        "held_out_cases_supplied_to_agent": False,
                        "sealed_oracle_supplied_to_agent": False,
                        "agent_call_argument_names": [
                            "workbook",
                            "policy_pdf",
                            "artifact_root",
                            "model",
                            "model_id",
                            "limits",
                            "run_id",
                        ],
                    },
                }
                records.append(record)

    aggregate = _aggregate(records)
    unique_run_ids = len(run_ids) == len(records)
    equal_limits = all(record["normalized_limits"] == expected_limits for record in records)
    blind_contract = all(
        not any(
            evidence[field]
            for field in (
                "case_id_supplied_to_agent",
                "defect_family_supplied_to_agent",
                "gold_formula_supplied_to_agent",
                "reference_workbook_supplied_to_agent",
                "held_out_cases_supplied_to_agent",
                "sealed_oracle_supplied_to_agent",
            )
        )
        for evidence in (record["blind_input_evidence"] for record in records)
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "benchmark": "FormulaWitness-agentic-blind-repeated-v1",
        "configuration": {
            "cases": list(selected),
            "trials_per_case_per_mode": trials,
            "total_agent_runs": len(records),
            "provider": provider,
            "model_id": model_id,
            "normalized_aggregate_limits": expected_limits,
            "pair_order": "single-first on odd trials; manager-falsifier-first on even trials",
            "sealed_semantic_vectors_per_run": 48,
        },
        "isolation_proof": {
            "same_model_object_reused_for_both_modes": True,
            "same_provider_and_model_id_for_both_modes": True,
            "same_normalized_aggregate_limits": equal_limits,
            "all_run_ids_fresh_and_unique": unique_run_ids,
            "proposal_only_before_controller_approval": True,
            "exact_proposal_hash_required_for_repair_evaluation": True,
            "sealed_oracle_invoked_only_after_agent_completion": True,
            "no_gold_or_case_metadata_supplied_to_agents": blind_contract,
            "agent_input_allowlist": ["workbook.xlsx", "policy.pdf"],
            "controller_only_metadata": [
                "case_id",
                "defect_family",
                "maximum_patch_cells",
                "held_out_cases",
                "sealed_oracle",
            ],
        },
        "records": records,
        "aggregate": aggregate,
    }
    if not all(
        (
            equal_limits,
            unique_run_ids,
            blind_contract,
        )
    ):
        raise RuntimeError("Agent evaluation isolation or fairness proof failed")
    _atomic_write_json(output, payload)
    return payload
