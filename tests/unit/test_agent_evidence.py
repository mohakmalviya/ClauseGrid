from __future__ import annotations

import hashlib
import json
from pathlib import Path

from formulawitness.agent_budget import AgentBudgetLedger, AgentRuntimeLimits
from formulawitness.agent_state import AgentRunState
from formulawitness.agent_tools import AgentToolRegistry, ToolEnvelope
from formulawitness.agent_types import ModelRequest, ModelTurn, ModelUsage, ToolCall
from formulawitness.falsifier import FalsifierAgent
from formulawitness.policy_text import PolicyText
from formulawitness.trace import Trajectory
from formulawitness.workbook_tools import list_formulas

ROOT = Path(__file__).resolve().parents[2]
MUTANT = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
REFERENCE = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
POLICY = ROOT / "policies/supplier_rebate_sla_policy.pdf"


def _call(registry: AgentToolRegistry, name: str, arguments: dict[str, object]) -> ToolEnvelope:
    return registry.execute(ToolCall(call_id=f"call-{name}", name=name, arguments=arguments))


def test_model_experiment_view_compacts_redundant_evidence_without_mutating_it() -> None:
    result = {
        "experiment_id": "experiment-1",
        "actor": "audit-manager",
        "proposal_id": None,
        "candidate_edit_ids": [],
        "candidate_sensitive_observations": [],
        "request": {"purpose": "Persisted in full state"},
        "observation": {
            "workbook_sha256": "a" * 64,
            "sheet": "Sheet1",
            "observations": {"A1": 1},
            "dependencies": {"A1": ["B1", "C1"]},
            "formula_sha256": {"A1": "b" * 64},
            "applied_formula_overrides": [],
            "comparisons": [{"cell": "A1", "matches": True}],
            "elapsed_ms": 1,
        },
    }
    envelope = ToolEnvelope(ok=True, tool="run_experiment", result=result)

    model_view = json.loads(envelope.to_model_json())["result"]

    assert "request" not in model_view
    assert "dependencies" not in model_view["observation"]
    assert model_view["observation"]["observations"] == {"A1": 1}
    assert result["observation"]["dependencies"] == {"A1": ["B1", "C1"]}


def _registries() -> tuple[AgentToolRegistry, AgentToolRegistry, AgentRunState, str, str]:
    policy = PolicyText(POLICY)
    state = AgentRunState(
        run_id="evidence-guard-test",
        source_sha256=hashlib.sha256(MUTANT.read_bytes()).hexdigest(),
        policy_sha256=policy.document_sha256,
    )
    manager = AgentToolRegistry(
        workbook=MUTANT,
        policy=policy,
        state=state,
        actor="audit-manager",
        charge_workbook_execution=lambda: None,
        require_falsifier=True,
    )
    falsifier = AgentToolRegistry(
        workbook=MUTANT,
        policy=policy,
        state=state,
        actor="falsifier",
        charge_workbook_execution=lambda: None,
    )
    citation_result = _call(
        manager,
        "read_policy_page",
        {"page": 3, "start_char": 0, "max_chars": len(policy.pages[2])},
    )
    assert citation_result.ok and isinstance(citation_result.result, dict)
    citation = citation_result.result["citation"]
    assert isinstance(citation, dict)
    citation_id = str(citation["citation_id"])
    old_formula = list_formulas(MUTANT)["RebateCalc!P6"]
    old_hash = hashlib.sha256(old_formula.encode("utf-8")).hexdigest()
    return manager, falsifier, state, citation_id, old_hash


def _stage(
    manager: AgentToolRegistry,
    citation_id: str,
    old_hash: str,
    formula: str,
) -> ToolEnvelope:
    return _call(
        manager,
        "stage_candidate",
        {
            "edits": [
                {
                    "sheet": "RebateCalc",
                    "cell": "P6",
                    "old_formula_sha256": old_hash,
                    "new_formula": formula,
                    "rationale": "Policy-grounded hypothesis for adversarial verification.",
                    "evidence_ids": [citation_id],
                }
            ],
            "expected_invariants": ["Ordinary SLA penalties remain effective"],
        },
    )


def _experiment(
    falsifier: AgentToolRegistry,
    experiment_id: str,
    old_hash: str,
    formula: str,
    *,
    expected: float | None,
) -> ToolEnvelope:
    arguments: dict[str, object] = {
        "experiment_id": experiment_id,
        "sheet": "RebateCalc",
        "overrides": {"H6": 0.94, "I6": 0.03, "J6": 1, "K6": "Y"},
        "observations": ["P6"],
        "formula_overrides": [
            {
                "cell": "P6",
                "old_formula_sha256": old_hash,
                "new_formula": formula,
            }
        ],
        "purpose": "Attempt to falsify the exact staged candidate under waiver interaction.",
    }
    if expected is not None:
        arguments["expectations"] = [{"cell": "P6", "expected": expected}]
    return _call(falsifier, "run_experiment", arguments)


def test_falsifier_rejects_missing_and_non_candidate_formula_overrides() -> None:
    manager, falsifier, _, citation_id, old_hash = _registries()
    assert _stage(manager, citation_id, old_hash, "=1").ok

    missing = _call(
        falsifier,
        "run_experiment",
        {
            "experiment_id": "missing-candidate",
            "sheet": "RebateCalc",
            "overrides": {},
            "observations": ["P6"],
            "expectations": [{"cell": "P6", "expected": 1}],
            "purpose": "This deliberately omits the staged formula candidate.",
        },
    )
    assert not missing.ok and "apply the staged candidate" in str(missing.error)

    wrong = _experiment(falsifier, "wrong-candidate", old_hash, "=2", expected=0.6)
    assert not wrong.ok and "not an exact edit" in str(wrong.error)


def test_conclusive_verdict_requires_expectations_and_mechanical_outcome() -> None:
    manager, falsifier, state, citation_id, old_hash = _registries()
    assert _stage(manager, citation_id, old_hash, "=1").ok
    no_expectation = _experiment(falsifier, "no-expectation", old_hash, "=1", expected=None)
    assert not no_expectation.ok and "explicit expected observations" in str(no_expectation.error)
    assert "no-expectation" not in state.experiments

    assert _experiment(falsifier, "graded-pass", old_hash, "=1", expected=1).ok

    assert _experiment(falsifier, "reproduced-mismatch", old_hash, "=1", expected=0.6).ok
    false_survival = _call(
        falsifier,
        "report_falsification",
        {
            "status": "SURVIVED",
            "experiment_ids": ["reproduced-mismatch"],
            "counterexamples": [],
            "remaining_risks": [],
            "explanation": "A mismatch cannot be reported as candidate survival.",
        },
    )
    assert not false_survival.ok and "every cited expected observation" in str(false_survival.error)


def test_evidence_from_an_old_proposal_cannot_validate_a_revision() -> None:
    manager, falsifier, state, citation_id, old_hash = _registries()
    assert _stage(manager, citation_id, old_hash, "=1").ok
    assert _experiment(falsifier, "candidate-a", old_hash, "=1", expected=0.6).ok
    old_proposal_id = state.candidate.proposal_id if state.candidate is not None else ""

    corrected = list_formulas(REFERENCE)["RebateCalc!P6"]
    assert _stage(manager, citation_id, old_hash, corrected).ok
    assert state.candidate is not None and state.candidate.proposal_id != old_proposal_id
    stale = _call(
        falsifier,
        "report_falsification",
        {
            "status": "BROKEN",
            "experiment_ids": ["candidate-a"],
            "counterexamples": ["Stale evidence from the prior proposal."],
            "remaining_risks": [],
            "explanation": "A prior candidate experiment cannot decide the revision.",
        },
    )
    assert not stale.ok and "another candidate" in str(stale.error)


def test_repair_decision_requires_policy_and_current_falsifier_evidence() -> None:
    manager, falsifier, _, citation_id, old_hash = _registries()
    corrected = list_formulas(REFERENCE)["RebateCalc!P6"]
    assert _stage(manager, citation_id, old_hash, corrected).ok
    assert _experiment(falsifier, "current-survival", old_hash, corrected, expected=0.6).ok
    verdict = _call(
        falsifier,
        "report_falsification",
        {
            "status": "SURVIVED",
            "experiment_ids": ["current-survival"],
            "counterexamples": [],
            "remaining_risks": ["The bounded test set cannot prove all future inputs."],
            "explanation": "The exact candidate passed the explicit expected observation.",
        },
    )
    assert verdict.ok

    missing_policy = _call(
        manager,
        "submit_repair",
        {
            "explanation": "Experiment-only evidence is insufficient for a policy repair.",
            "evidence_ids": ["current-survival"],
        },
    )
    assert not missing_policy.ok and "policy citation" in str(missing_policy.error)

    accepted = _call(
        manager,
        "submit_repair",
        {
            "explanation": "The exact policy citation and falsifier experiment support repair.",
            "evidence_ids": [citation_id, "current-survival"],
        },
    )
    assert accepted.ok


class InvalidTerminalVerdictModel:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelTurn:
        self.requests.append(request)
        return ModelTurn(
            model="invalid-terminal-test",
            tool_calls=(
                ToolCall(
                    call_id="invalid-verdict",
                    name="report_falsification",
                    arguments={
                        "status": "SURVIVED",
                        "experiment_ids": [],
                        "counterexamples": [],
                        "remaining_risks": [],
                        "explanation": "This conclusive verdict deliberately lacks evidence.",
                    },
                ),
            ),
            finish_reason="tool_calls",
            usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            elapsed_ms=1,
        )


def test_invalid_final_falsifier_verdict_falls_back_to_inconclusive(tmp_path: Path) -> None:
    manager, _, state, citation_id, old_hash = _registries()
    assert _stage(manager, citation_id, old_hash, "=1").ok
    assert state.candidate is not None
    model = InvalidTerminalVerdictModel()
    limits = AgentRuntimeLimits(
        manager_turn_limit=0,
        falsifier_turn_limit=1,
        model_call_limit=2,
        tool_call_limit=2,
        input_token_limit=1_000,
        output_token_limit=1_000,
        workbook_execution_limit=0,
        retry_limit=0,
        elapsed_time_limit_seconds=30.0,
    )
    falsifier = FalsifierAgent(
        model=model,
        workbook=MUTANT,
        policy=PolicyText(POLICY),
        state=state,
        budget=AgentBudgetLedger(limits),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "invalid-terminal"),
    )

    verdict = falsifier.run(state.candidate)

    assert verdict.status == "INCONCLUSIVE"
    assert "falsifier_turns" in verdict.remaining_risks[0]
    assert len(model.requests) == 1
    assert [tool.name for tool in model.requests[0].tools] == ["report_falsification"]
