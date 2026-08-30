from __future__ import annotations

import hashlib
import json
from pathlib import Path

from formulawitness.agent_budget import AgentBudgetLedger, AgentRuntimeLimits
from formulawitness.agent_state import AgentRunState, FalsifierVerdict
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


def test_only_one_unchanged_manager_baseline_is_accepted() -> None:
    manager, _, state, _, _ = _registries()
    first = _call(
        manager,
        "run_experiment",
        {
            "experiment_id": "observational-baseline",
            "sheet": "RebateCalc",
            "overrides": {},
            "observations": ["P6"],
            "purpose": "Register the current multiplier as one observational baseline.",
        },
    )
    assert first.ok

    repeated = _call(
        manager,
        "run_experiment",
        {
            "experiment_id": "unchanged-repeat",
            "sheet": "RebateCalc",
            "overrides": {},
            "observations": ["Q6"],
            "purpose": "Attempt another unchanged observation without a hypothesis.",
        },
    )
    assert not repeated.ok and "Only one unchanged observational baseline" in str(repeated.error)
    assert "unchanged-repeat" not in state.experiments

    discriminating = _call(
        manager,
        "run_experiment",
        {
            "experiment_id": "input-perturbation",
            "sheet": "RebateCalc",
            "overrides": {"H6": 0.9},
            "observations": ["P6"],
            "purpose": "Perturb one policy input to test causal multiplier behavior.",
        },
    )
    assert discriminating.ok

    renamed_duplicate = _call(
        manager,
        "run_experiment",
        {
            "experiment_id": "renamed-input-perturbation",
            "sheet": "RebateCalc",
            "overrides": {"H6": 0.9},
            "observations": ["P6"],
            "purpose": "Rename the same design without changing its causal intervention.",
        },
    )
    assert not renamed_duplicate.ok and "Duplicate experiment design" in str(
        renamed_duplicate.error
    )


def test_experiment_can_perturb_a_qualified_cross_sheet_raw_input() -> None:
    manager, _, _, _, _ = _registries()

    result = _call(
        manager,
        "run_experiment",
        {
            "experiment_id": "qualified-tier-input",
            "sheet": "RebateCalc",
            "overrides": {"TierSchedule!B7": 0.123},
            "observations": ["N6"],
            "purpose": "Perturb a cross-sheet lookup input to test causal tier behavior.",
        },
    )

    assert result.ok and isinstance(result.result, dict)
    observation = result.result["observation"]
    assert observation["observations"]["N6"] == 0.123


def test_experiment_cannot_override_a_cross_sheet_formula_as_raw_input() -> None:
    manager, _, _, _, _ = _registries()

    result = _call(
        manager,
        "run_experiment",
        {
            "experiment_id": "qualified-formula-input",
            "sheet": "RebateCalc",
            "overrides": {"Checks!E10": "PASS"},
            "observations": ["P6"],
            "purpose": "Attempt to replace a cross-sheet formula cache as if it were raw input.",
        },
    )

    assert not result.ok
    assert "cannot replace formula cell" in str(result.error)


def test_candidate_cannot_introduce_a_cross_sheet_formula_chain() -> None:
    manager, _, _, citation_id, old_hash = _registries()

    result = _stage(manager, citation_id, old_hash, "=Checks!E10")

    assert not result.ok
    assert "Cross-sheet formula-to-formula dependencies" in str(result.error)


def test_candidate_cannot_reference_a_missing_sheet() -> None:
    manager, _, _, citation_id, old_hash = _registries()

    result = _stage(manager, citation_id, old_hash, "=Missing!A1+1")

    assert not result.ok
    assert "worksheet that does not exist" in str(result.error)


def test_direct_formula_experiment_cannot_use_cross_sheet_formula_cache() -> None:
    manager, _, _, _, old_hash = _registries()

    result = _call(
        manager,
        "run_experiment",
        {
            "experiment_id": "cached-cross-sheet-formula",
            "sheet": "RebateCalc",
            "overrides": {"K6": "INVALID"},
            "observations": ["P6"],
            "formula_overrides": [
                {
                    "cell": "P6",
                    "old_formula_sha256": old_hash,
                    "new_formula": '=Checks!E10="PASS"',
                }
            ],
            "purpose": "Attempt to rely on a stale cached formula from another sheet.",
        },
    )

    assert not result.ok
    assert "Cross-sheet formula-to-formula dependencies" in str(result.error)


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


def test_falsifier_injects_missing_candidate_and_rejects_non_candidate_overrides() -> None:
    manager, falsifier, state, citation_id, old_hash = _registries()
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
    assert missing.ok
    applied = state.experiments["missing-candidate"].request["formula_overrides"]
    assert applied and applied[0]["new_formula"] == "=1"

    wrong = _experiment(falsifier, "wrong-candidate", old_hash, "=2", expected=0.6)
    assert not wrong.ok and "not an exact edit" in str(wrong.error)


def test_experiment_decodes_provider_stringified_json_arguments() -> None:
    manager, _, _, _, _ = _registries()
    result = _call(
        manager,
        "run_experiment",
        {
            "experiment_id": "stringified-arguments",
            "sheet": "RebateCalc",
            "overrides": '{"H6":0.94,"I6":0.02,"J6":0,"K6":"N"}',
            "observations": '["P6"]',
            "expectations": '[{"cell":"P6","expected":0.75}]',
            "purpose": "Accept semantically valid JSON emitted as nested strings.",
        },
    )

    assert result.ok


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
            "explanation": (
                "The exact policy citation and surviving falsifier verdict support repair."
            ),
            "evidence_ids": [citation_id],
        },
    )
    assert accepted.ok
    assert accepted.result is not None
    assert set(accepted.result["evidence_ids"]) == {citation_id, "current-survival"}


def test_human_escalation_requires_policy_and_executed_workbook_evidence() -> None:
    manager, _, _, citation_id, _ = _registries()

    no_evidence = _call(
        manager,
        "request_human",
        {
            "reason": "More investigation is needed before reaching a decision.",
            "evidence_ids": [],
        },
    )
    assert not no_evidence.ok and "policy citation" in str(no_evidence.error)

    policy_only = _call(
        manager,
        "request_human",
        {
            "reason": "The policy evidence needs to be compared with workbook behavior.",
            "evidence_ids": [citation_id],
        },
    )
    assert not policy_only.ok and "executed workbook experiment" in str(policy_only.error)

    experiment = _call(
        manager,
        "run_experiment",
        {
            "experiment_id": "human-escalation-observation",
            "sheet": "RebateCalc",
            "overrides": {},
            "observations": ["P6"],
            "purpose": "Register current workbook behavior before escalating ambiguity.",
        },
    )
    assert experiment.ok
    accepted = _call(
        manager,
        "request_human",
        {
            "reason": "The executed result leaves a material policy ambiguity for a reviewer.",
            "evidence_ids": [citation_id],
        },
    )
    assert accepted.ok
    assert accepted.result is not None
    assert set(accepted.result["evidence_ids"]) == {
        citation_id,
        "human-escalation-observation",
    }


def test_candidate_quote_template_reconstructs_and_validates_excel_formula() -> None:
    manager, _, state, citation_id, old_hash = _registries()
    corrected = list_formulas(REFERENCE)["RebateCalc!P6"]

    staged = _call(
        manager,
        "stage_candidate",
        {
            "edits": [
                {
                    "sheet": "RebateCalc",
                    "cell": "P6",
                    "old_formula_sha256": old_hash,
                    "new_formula_template": corrected.replace('"', "{DQ}"),
                    "rationale": "Use a JSON-safe representation of quoted Excel conditions.",
                    "evidence_ids": [citation_id],
                }
            ],
            "expected_invariants": ["Quoted Excel literals are reconstructed exactly"],
        },
    )

    assert staged.ok
    assert state.candidate is not None
    assert state.candidate.edits[0].new_formula == corrected


def test_candidate_structural_transform_derives_formula_from_guarded_source() -> None:
    manager, _, state, citation_id, old_hash = _registries()

    staged = _call(
        manager,
        "stage_candidate",
        {
            "edits": [
                {
                    "sheet": "RebateCalc",
                    "cell": "P6",
                    "old_formula_sha256": old_hash,
                    "formula_transform": "unwrap_outer_if_else",
                    "rationale": "Remove the faulty wrapper while preserving its else calculation.",
                    "evidence_ids": [citation_id],
                }
            ],
            "expected_invariants": ["The retained calculation remains parser-valid"],
        },
    )

    assert staged.ok
    assert state.candidate is not None
    candidate = state.candidate.edits[0].new_formula
    assert candidate.startswith("=IF(AND(")
    assert 'K6<>"Y"' in candidate


def test_no_change_requires_multiple_passing_branch_perturbations() -> None:
    manager, _, state, citation_id, _ = _registries()
    cases = (
        ("ordinary-both", {"H6": 0.94, "I6": 0.03, "J6": 0, "K6": "N"}, 0.6),
        ("ordinary-one", {"H6": 0.94, "I6": 0.01, "J6": 0, "K6": "N"}, 0.75),
        ("ordinary-none", {"H6": 0.98, "I6": 0.01, "J6": 0, "K6": "N"}, 1.0),
    )
    for experiment_id, overrides, expected in cases:
        result = _call(
            manager,
            "run_experiment",
            {
                "experiment_id": experiment_id,
                "sheet": "RebateCalc",
                "overrides": overrides,
                "observations": ["P6"],
                "expectations": [{"cell": "P6", "expected": expected}],
                "purpose": "Exercise one distinct ordinary SLA policy branch.",
            },
        )
        assert result.ok

    insufficient = _call(
        manager,
        "finish_no_change",
        {
            "explanation": "One passing row cannot justify preserving the workbook.",
            "evidence_ids": [citation_id, "ordinary-both"],
        },
    )
    assert not insufficient.ok and "at least three" in str(insufficient.error)
    assert state.decision is None

    accepted = _call(
        manager,
        "finish_no_change",
        {
            "explanation": "Three expected-output perturbations exercise changing formula branches.",
            "evidence_ids": [citation_id, *(item[0] for item in cases)],
        },
    )
    assert accepted.ok
    assert state.decision is not None and state.decision.decision == "NO_CHANGE"


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


def test_falsifier_receives_manager_experiments_for_edited_cells(tmp_path: Path) -> None:
    manager, _, state, citation_id, old_hash = _registries()
    experiment = _call(
        manager,
        "run_experiment",
        {
            "experiment_id": "edited-cell-counterexample",
            "sheet": "RebateCalc",
            "overrides": {"H6": 0.9, "K6": "Y"},
            "observations": ["P6"],
            "expectations": [{"cell": "P6", "expected": 0.75}],
            "purpose": "Expose waiver scope leakage at the candidate target.",
        },
    )
    assert experiment.ok
    assert _stage(manager, citation_id, old_hash, "=1").ok
    assert state.candidate is not None
    falsifier = FalsifierAgent(
        model=InvalidTerminalVerdictModel(),
        workbook=MUTANT,
        policy=PolicyText(POLICY),
        state=state,
        budget=AgentBudgetLedger(AgentRuntimeLimits(0, 1, 1, 1, 1_000, 1_000, 1, 0, 30.0)),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "focused-evidence"),
    )

    evidence = falsifier._supporting_evidence(state.candidate)

    focused = [item for item in evidence if item["evidence_id"] == "edited-cell-counterexample"]
    assert focused and focused[0]["kind"] == "manager_experiment_for_edited_cell"


def test_falsifier_receives_registered_citation_for_rule_named_in_rationale(
    tmp_path: Path,
) -> None:
    manager, _, state, citation_id, old_hash = _registries()
    source = state.citations[citation_id]
    rule_citation = source.model_copy(
        update={
            "citation_id": "citation-rule-202",
            "exact_quote": "RB-202 applies the ordinary service penalty.",
        }
    )
    state.citations[rule_citation.citation_id] = rule_citation
    assert _stage(manager, citation_id, old_hash, "=1").ok
    assert state.candidate is not None
    edit = state.candidate.edits[0].model_copy(update={"rationale": "Required by RB-202."})
    state.candidate = state.candidate.model_copy(update={"edits": (edit,)})
    falsifier = FalsifierAgent(
        model=InvalidTerminalVerdictModel(),
        workbook=MUTANT,
        policy=PolicyText(POLICY),
        state=state,
        budget=AgentBudgetLedger(AgentRuntimeLimits(0, 1, 1, 1, 1_000, 1_000, 1, 0, 30.0)),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "rule-evidence"),
    )

    evidence = falsifier._supporting_evidence(state.candidate)

    focused = [item for item in evidence if item["evidence_id"] == "citation-rule-202"]
    assert focused and focused[0]["kind"] == "manager_registered_rule_citation"


def test_inconclusive_falsification_stops_manager_without_more_model_turns() -> None:
    manager, _, state, citation_id, old_hash = _registries()
    assert _call(
        manager,
        "run_experiment",
        {
            "experiment_id": "manager-evidence",
            "sheet": "RebateCalc",
            "overrides": {"H6": 0.9},
            "observations": ["P6"],
            "expectations": [{"cell": "P6", "expected": 0.75}],
            "purpose": "Register evidence before an inconclusive independent check.",
        },
    ).ok
    assert _stage(manager, citation_id, old_hash, "=1").ok
    assert state.candidate is not None
    proposal_id = state.candidate.proposal_id
    registry = AgentToolRegistry(
        workbook=MUTANT,
        policy=PolicyText(POLICY),
        state=state,
        actor="audit-manager",
        charge_workbook_execution=lambda: None,
        falsify=lambda _: FalsifierVerdict(
            status="INCONCLUSIVE",
            proposal_id=proposal_id,
            experiment_ids=(),
            counterexamples=(),
            remaining_risks=("One edge case remains untested.",),
            explanation="Independent evidence was insufficient for authorization.",
        ),
        require_falsifier=True,
    )

    result = _call(registry, "falsify_candidate", {})

    assert result.ok
    assert state.decision is not None
    assert state.decision.decision == "ABSTAIN"
    assert "manager-evidence" in state.decision.evidence_ids
