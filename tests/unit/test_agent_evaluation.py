from __future__ import annotations

import ast
import json
import shutil
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from formulawitness import cli
from formulawitness.agent_budget import AgentRuntimeLimits
from formulawitness.agent_evaluation import (
    CandidateScore,
    EvaluationServices,
    run_agent_evaluation,
)
from formulawitness.agentic import DEFAULT_AGENT_LIMITS
from formulawitness.cli import build_parser
from formulawitness.model_client import ModelConfigurationError, OpenAICompatibleConfig
from formulawitness.models import AuditResult
from formulawitness.trace import object_hash


def _budget(limits: AgentRuntimeLimits, *, single_agent: bool) -> dict[str, Any]:
    effective = (
        replace(
            limits,
            manager_turn_limit=limits.manager_turn_limit + limits.falsifier_turn_limit,
            falsifier_turn_limit=0,
        )
        if single_agent
        else limits
    )
    return {
        **asdict(effective),
        "manager_turns_used": 2,
        "falsifier_turns_used": 0 if single_agent else 1,
        "model_calls_used": 3,
        "tool_calls_used": 4,
        "input_tokens_used": 100,
        "output_tokens_used": 20,
        "workbook_executions_used": 2,
        "retries_used": 1,
        "elapsed_time_seconds": 0.1,
        "reported_cost_usd": None,
    }


def _runner(
    mode: str,
    events: list[tuple[str, str]],
    calls: list[dict[str, Any]],
    *,
    decision: str,
) -> Callable[..., AuditResult]:
    def run(
        workbook: Path,
        policy_pdf: Path,
        artifact_root: Path,
        *,
        model: object,
        model_id: str,
        limits: AgentRuntimeLimits,
        run_id: str | None = None,
    ) -> AuditResult:
        assert run_id is not None
        events.append(("agent", run_id))
        calls.append(
            {
                "mode": mode,
                "workbook": workbook,
                "policy_pdf": policy_pdf,
                "artifact_root": artifact_root,
                "model": model,
                "model_id": model_id,
                "limits": limits,
                "run_id": run_id,
            }
        )
        run_dir = artifact_root / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "proposal.json").write_text(
            json.dumps({"run_id": run_id, "decision": decision}),
            encoding="utf-8",
        )
        return AuditResult(
            run_id=run_id,
            method=mode,
            source_workbook=str(workbook),
            source_sha256="source",
            rules_sha256="policy",
            decision=decision,  # type: ignore[arg-type]
            artifact_dir=str(run_dir),
            budget=_budget(limits, single_agent=mode == "single-agent"),
        )

    return run


def _approver(events: list[tuple[str, str]]) -> Callable[..., AuditResult]:
    def approve(
        workbook: Path,
        policy_pdf: Path,
        artifact_root: Path,
        run_id: str,
        *,
        reviewer: str,
        expected_proposal_hash: str,
    ) -> AuditResult:
        del policy_pdf
        events.append(("approval", run_id))
        proposal = json.loads(
            (artifact_root / run_id / "proposal.json").read_text(encoding="utf-8")
        )
        assert expected_proposal_hash == object_hash(proposal)
        assert reviewer == "agent-evaluation-controller"
        output = artifact_root / run_id / "repaired.xlsx"
        shutil.copyfile(workbook, output)
        return AuditResult(
            run_id=run_id,
            method="approval",
            source_workbook=str(workbook),
            source_sha256="source",
            rules_sha256="policy",
            decision="REPAIR",
            output_workbook=str(output),
        )

    return approve


def _scorer(events: list[tuple[str, str]]) -> Callable[..., CandidateScore]:
    def score(
        case_id: str,
        original_source: Path,
        staged_source: Path,
        candidate: Path,
        source_sha256: str,
    ) -> CandidateScore:
        del original_source, staged_source, source_sha256
        events.append(("scorer", candidate.parent.name))
        assert case_id == "M10"
        return CandidateScore(
            success=True,
            semantic_ok=True,
            minimality_ok=True,
            clean_preservation=None,
            source_immutable=True,
            changed_cells=("T7",),
            changed_formulas=("RebateCalc!T7",),
            unrelated_formula_changes=(),
            semantic_vectors_passed=48,
            semantic_vectors_total=48,
            first_failure=None,
        )

    return score


def test_repeated_evaluation_is_blind_paired_and_ordered(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    events: list[tuple[str, str]] = []
    calls: list[dict[str, Any]] = []
    services = EvaluationServices(
        single_agent_runner=_runner("single-agent", events, calls, decision="REPAIR"),
        manager_falsifier_runner=_runner("manager-falsifier", events, calls, decision="REPAIR"),
        approver=_approver(events),
        scorer=_scorer(events),
    )
    output = tmp_path / "result.json"

    result = run_agent_evaluation(
        root,
        output,
        tmp_path / "artifacts",
        model=object(),  # type: ignore[arg-type]
        provider="test-provider",
        model_id="test-model",
        cases=("M10",),
        trials=5,
        services=services,
    )

    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 1
    assert not list(tmp_path.glob("**/*.tmp-*"))
    assert len(result["records"]) == 10
    assert len({record["run_id"] for record in result["records"]}) == 10
    assert result["isolation_proof"] == {
        "same_model_object_reused_for_both_modes": True,
        "same_provider_and_model_id_for_both_modes": True,
        "same_normalized_aggregate_limits": True,
        "all_run_ids_fresh_and_unique": True,
        "proposal_only_before_controller_approval": True,
        "exact_proposal_hash_required_for_repair_evaluation": True,
        "sealed_oracle_invoked_only_after_agent_completion": True,
        "no_gold_or_case_metadata_supplied_to_agents": True,
        "agent_input_allowlist": ["workbook.xlsx", "policy.pdf"],
        "controller_only_metadata": [
            "case_id",
            "defect_family",
            "maximum_patch_cells",
            "held_out_cases",
            "sealed_oracle",
        ],
    }
    assert result["aggregate"]["methods"]["single-agent"]["success"][
        "rate_percent"
    ] == pytest.approx(100.0)
    assert (
        result["aggregate"]["methods"]["manager-falsifier"]["success"]["wilson_95"]["low_percent"]
        < 100
    )

    for call in calls:
        assert call["workbook"].name == "workbook.xlsx"
        assert call["policy_pdf"].name == "policy.pdf"
        assert "M10" not in str(call["workbook"])
        assert "M10" not in str(call["policy_pdf"])
        assert "M10" not in str(call["artifact_root"])
        assert "M10" not in call["run_id"]
        assert call["limits"] is DEFAULT_AGENT_LIMITS
        assert set(call) == {
            "mode",
            "workbook",
            "policy_pdf",
            "artifact_root",
            "model",
            "model_id",
            "limits",
            "run_id",
        }

    for index in range(0, len(events), 3):
        assert events[index][0] == "agent"
        assert events[index + 1] == ("approval", events[index][1])
        assert events[index + 2][0] == "scorer"


def test_fewer_than_five_trials_is_rejected_before_any_run(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least 5 trials"):
        run_agent_evaluation(
            tmp_path,
            tmp_path / "result.json",
            tmp_path / "artifacts",
            model=object(),  # type: ignore[arg-type]
            provider="test-provider",
            model_id="test-model",
            cases=("M10",),
            trials=4,
        )


def test_no_change_is_scored_without_controller_approval(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    events: list[tuple[str, str]] = []
    calls: list[dict[str, Any]] = []

    def reject_approval(*args: object, **kwargs: object) -> AuditResult:
        del args, kwargs
        raise AssertionError("NO_CHANGE must not cross the approval boundary")

    def score_clean(
        case_id: str,
        original_source: Path,
        staged_source: Path,
        candidate: Path,
        source_sha256: str,
    ) -> CandidateScore:
        del original_source, staged_source, source_sha256
        assert case_id == "C03"
        events.append(("scorer", candidate.name))
        return CandidateScore(
            success=True,
            semantic_ok=True,
            minimality_ok=True,
            clean_preservation=True,
            source_immutable=True,
            changed_cells=(),
            changed_formulas=(),
            unrelated_formula_changes=(),
            semantic_vectors_passed=48,
            semantic_vectors_total=48,
            first_failure=None,
        )

    services = EvaluationServices(
        single_agent_runner=_runner("single-agent", events, calls, decision="NO_CHANGE"),
        manager_falsifier_runner=_runner("manager-falsifier", events, calls, decision="NO_CHANGE"),
        approver=reject_approval,
        scorer=score_clean,
    )
    result = run_agent_evaluation(
        root,
        tmp_path / "result.json",
        tmp_path / "artifacts",
        model=object(),  # type: ignore[arg-type]
        provider="test-provider",
        model_id="test-model",
        cases=("C03",),
        trials=5,
        services=services,
    )

    assert all(not record["approved_for_evaluation"] for record in result["records"])
    assert all(record["clean_preservation"] for record in result["records"])
    assert {event for event, _ in events} == {"agent", "scorer"}


def test_answer_bearing_evaluator_imports_are_lazy() -> None:
    module_path = Path(__file__).resolve().parents[2] / "src/formulawitness/agent_evaluation.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    top_level_modules = {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "evaluation" not in top_level_modules
    assert "policy" not in top_level_modules
    assert all(not module.startswith("evals") for module in top_level_modules)


def test_agent_eval_cli_defaults_to_repeated_tight_case_set() -> None:
    args = build_parser().parse_args(["agent-eval", "--model", "test-model"])
    assert args.cases == ["M10", "H01", "C03"]
    assert args.trials == 5
    assert args.provider == "qubrid"
    assert not args.allow_external_processing
    consented = build_parser().parse_args(
        ["agent-eval", "--model", "test-model", "--allow-external-processing"]
    )
    assert consented.allow_external_processing


def test_cli_exposes_provider_presets_and_claude_alias() -> None:
    for provider in (
        "openai",
        "anthropic",
        "claude",
        "deepseek",
        "nvidia-nim",
        "opencode",
        "qubrid",
    ):
        args = build_parser().parse_args(
            ["agent", "workbook.xlsx", "--provider", provider, "--model", "model-id"]
        )
        assert args.provider == provider


def test_generic_provider_requires_endpoint_before_credential_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded_credentials = False

    def forbidden_build(**kwargs: object) -> object:
        del kwargs
        nonlocal loaded_credentials
        loaded_credentials = True
        raise AssertionError("provider builder must remain unreachable")

    monkeypatch.setattr(cli, "build_model_client", forbidden_build)
    args = build_parser().parse_args(
        ["agent-eval", "--provider", "openai-compatible", "--model", "test-model"]
    )

    with pytest.raises(ModelConfigurationError, match="--base-url"):
        cli._configured_model(args)
    assert not loaded_credentials


def test_remote_model_requires_consent_before_credential_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded_credentials = False

    def forbidden_load(cls: type[object], /, **kwargs: object) -> object:
        del cls, kwargs
        nonlocal loaded_credentials
        loaded_credentials = True
        raise AssertionError("credential loader must remain unreachable")

    monkeypatch.setattr(
        OpenAICompatibleConfig,
        "from_env",
        classmethod(forbidden_load),
    )
    args = build_parser().parse_args(["agent-eval", "--model", "test-model"])

    with pytest.raises(ModelConfigurationError, match="--allow-external-processing"):
        cli._configured_model(args)
    assert not loaded_credentials


def test_loopback_model_may_omit_external_processing_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORMULAWITNESS_TEST_MODEL_KEY", "test-secret")
    args = build_parser().parse_args(
        [
            "agent-eval",
            "--model",
            "test-model",
            "--provider",
            "openai-compatible",
            "--base-url",
            "http://127.0.0.1:9999/v1",
            "--api-key-env",
            "FORMULAWITNESS_TEST_MODEL_KEY",
        ]
    )

    client, provider, model_id = cli._configured_model(args)
    try:
        assert provider == "openai-compatible"
        assert model_id == "test-model"
    finally:
        client.close()


def test_agent_eval_cli_closes_model_client_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ClosingClient:
        closed = False

        def close(self) -> None:
            self.closed = True

    client = ClosingClient()

    def configured(args: object) -> tuple[ClosingClient, str, str]:
        del args
        return client, "test-provider", "test-model"

    def fail(*args: object, **kwargs: object) -> dict[str, Any]:
        del args, kwargs
        raise RuntimeError("simulated benchmark failure")

    monkeypatch.setattr(cli, "_configured_model", configured)
    monkeypatch.setattr(cli, "run_agent_evaluation", fail)

    with pytest.raises(RuntimeError, match="simulated benchmark failure"):
        cli.main(["agent-eval", "--model", "test-model"])
    assert client.closed
