from __future__ import annotations

import hashlib
import json
from pathlib import Path

from formulawitness.agent_budget import AgentRuntimeLimits
from formulawitness.agent_types import ModelRequest, ModelTurn, ModelUsage, ToolCall
from formulawitness.agentic import (
    approve_agentic_proposal,
    run_agentic,
    run_agentic_baseline,
)
from formulawitness.ooxml import changed_workbook_formulas
from formulawitness.policy_text import PolicyText
from formulawitness.trace import object_hash, verify_trajectory
from formulawitness.workbook_tools import list_formulas

ROOT = Path(__file__).resolve().parents[2]
MUTANT = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
REFERENCE = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
POLICY = ROOT / "policies/supplier_rebate_sla_policy.pdf"


def _turn(call_id: str, name: str, arguments: dict[str, object]) -> ModelTurn:
    return ModelTurn(
        model="scripted-agent-test",
        tool_calls=(ToolCall(call_id=call_id, name=name, arguments=arguments),),
        finish_reason="tool_calls",
        usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        elapsed_ms=1,
    )


class InvestigatorFalsifierScript:
    """Scripted transport proves orchestration behavior, not repair performance."""

    def __init__(self) -> None:
        policy = PolicyText(POLICY)
        quote = policy.pages[2]
        seed = {
            "document_sha256": policy.document_sha256,
            "page": 3,
            "start_char": 0,
            "end_char": len(quote),
            "exact_quote": quote,
            "quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        }
        self.citation_id = "citation-" + object_hash(seed)[:12]
        old_formula = list_formulas(MUTANT)["RebateCalc!P6"]
        old_hash = hashlib.sha256(old_formula.encode("utf-8")).hexdigest()
        correct_formula = list_formulas(REFERENCE)["RebateCalc!P6"]
        evidence = (self.citation_id, "manager-observation")
        self.manager = [
            _turn(
                "m1",
                "read_policy_page",
                {
                    "page": 3,
                    "start_char": 0,
                    "max_chars": len(quote),
                },
            ),
            _turn(
                "m2",
                "run_experiment",
                {
                    "experiment_id": "manager-observation",
                    "sheet": "RebateCalc",
                    "overrides": {},
                    "observations": ["P6"],
                    "formula_overrides": [],
                    "purpose": "Record current behavior before proposing a formula change.",
                },
            ),
            _turn(
                "m3",
                "stage_candidate",
                {
                    "edits": [
                        {
                            "sheet": "RebateCalc",
                            "cell": "P6",
                            "old_formula_sha256": old_hash,
                            "new_formula": "=1",
                            "rationale": "First hypothesis intentionally requires adversarial testing.",
                            "evidence_ids": list(evidence),
                        }
                    ],
                    "expected_invariants": ["Unrelated formulas remain unchanged"],
                },
            ),
            _turn("m4", "falsify_candidate", {}),
            _turn(
                "m5",
                "stage_candidate",
                {
                    "edits": [
                        {
                            "sheet": "RebateCalc",
                            "cell": "P6",
                            "old_formula_sha256": old_hash,
                            "new_formula": correct_formula,
                            "rationale": "Revise the formula after the falsifier broke the first hypothesis.",
                            "evidence_ids": list(evidence),
                        }
                    ],
                    "expected_invariants": ["Unrelated formulas remain unchanged"],
                },
            ),
            _turn("m6", "falsify_candidate", {}),
            _turn(
                "m7",
                "submit_repair",
                {
                    "explanation": "The revised minimal proposal survived independent experiments.",
                    "evidence_ids": [
                        *evidence,
                        "falsifier-tested-revision",
                    ],
                },
            ),
        ]
        self.falsifier = [
            _turn(
                "f1",
                "run_experiment",
                {
                    "experiment_id": "falsifier-broke-first",
                    "sheet": "RebateCalc",
                    "overrides": {"H6": 0.94, "I6": 0.03, "J6": 1, "K6": "Y"},
                    "observations": ["P6"],
                    "expectations": [{"cell": "P6", "expected": 0.6}],
                    "formula_overrides": [
                        {
                            "cell": "P6",
                            "old_formula_sha256": old_hash,
                            "new_formula": "=1",
                        }
                    ],
                    "purpose": "Challenge whether the first candidate preserves current behavior.",
                },
            ),
            _turn(
                "f2",
                "report_falsification",
                {
                    "status": "BROKEN",
                    "experiment_ids": ["falsifier-broke-first"],
                    "counterexamples": ["The candidate forces P6 to one for the observed row."],
                    "remaining_risks": [],
                    "explanation": "An executed counterexample breaks the first candidate.",
                },
            ),
            _turn(
                "f3",
                "run_experiment",
                {
                    "experiment_id": "falsifier-tested-revision",
                    "sheet": "RebateCalc",
                    "overrides": {"H6": 0.94, "I6": 0.03, "J6": 1, "K6": "Y"},
                    "observations": ["P6"],
                    "expectations": [{"cell": "P6", "expected": 0.6}],
                    "formula_overrides": [
                        {
                            "cell": "P6",
                            "old_formula_sha256": old_hash,
                            "new_formula": correct_formula,
                        }
                    ],
                    "purpose": "Challenge the revised candidate in the sandbox.",
                },
            ),
            _turn(
                "f4",
                "report_falsification",
                {
                    "status": "SURVIVED",
                    "experiment_ids": ["falsifier-tested-revision"],
                    "counterexamples": [],
                    "remaining_risks": ["Unit script is not a blind performance evaluation."],
                    "explanation": "The revised candidate survived the executed adversarial check.",
                },
            ),
        ]
        self.manager_requests: list[ModelRequest] = []
        self.falsifier_requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelTurn:
        system = request.messages[0]
        actor_is_falsifier = system.content.lower().startswith(
            "you are formulawitness's independent falsifier"
        )
        if actor_is_falsifier:
            self.falsifier_requests.append(request)
            return self.falsifier.pop(0)
        self.manager_requests.append(request)
        return self.manager.pop(0)


class SingleAgentScript:
    def __init__(self) -> None:
        policy = PolicyText(POLICY)
        quote = policy.pages[2]
        seed = {
            "document_sha256": policy.document_sha256,
            "page": 3,
            "start_char": 0,
            "end_char": len(quote),
            "exact_quote": quote,
            "quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        }
        citation_id = "citation-" + object_hash(seed)[:12]
        old_formula = list_formulas(MUTANT)["RebateCalc!P6"]
        old_hash = hashlib.sha256(old_formula.encode("utf-8")).hexdigest()
        correct_formula = list_formulas(REFERENCE)["RebateCalc!P6"]
        evidence = [citation_id, "baseline-source", "baseline-candidate"]
        self.turns = [
            _turn(
                "b1",
                "read_policy_page",
                {"page": 3, "start_char": 0, "max_chars": len(quote)},
            ),
            _turn(
                "b2",
                "run_experiment",
                {
                    "experiment_id": "baseline-source",
                    "sheet": "RebateCalc",
                    "overrides": {"H6": 0.94, "I6": 0.03, "J6": 1, "K6": "Y"},
                    "observations": ["P6"],
                    "purpose": "Observe source behavior for the waiver interaction.",
                },
            ),
            _turn(
                "b3",
                "stage_candidate",
                {
                    "edits": [
                        {
                            "sheet": "RebateCalc",
                            "cell": "P6",
                            "old_formula_sha256": old_hash,
                            "new_formula": correct_formula,
                            "rationale": "One candidate grounded in the observed waiver interaction.",
                            "evidence_ids": [citation_id, "baseline-source"],
                        }
                    ],
                    "expected_invariants": ["Unrelated formulas remain unchanged"],
                },
            ),
            _turn(
                "b4",
                "run_experiment",
                {
                    "experiment_id": "baseline-candidate",
                    "sheet": "RebateCalc",
                    "overrides": {"H6": 0.94, "I6": 0.03, "J6": 1, "K6": "Y"},
                    "observations": ["P6"],
                    "expectations": [{"cell": "P6", "expected": 0.6}],
                    "formula_overrides": [
                        {
                            "cell": "P6",
                            "old_formula_sha256": old_hash,
                            "new_formula": correct_formula,
                        }
                    ],
                    "purpose": "Validate the one allowed candidate in the sandbox.",
                },
            ),
            _turn(
                "b5",
                "submit_repair",
                {
                    "explanation": "The one candidate passed its sandbox validation.",
                    "evidence_ids": evidence,
                },
            ),
        ]

    def complete(self, request: ModelRequest) -> ModelTurn:
        return self.turns.pop(0)


def test_model_directed_loop_revises_after_falsifier_counterexample(tmp_path: Path) -> None:
    model = InvestigatorFalsifierScript()
    source_hash = hashlib.sha256(MUTANT.read_bytes()).hexdigest()
    limits = AgentRuntimeLimits(
        manager_turn_limit=10,
        falsifier_turn_limit=6,
        model_call_limit=20,
        tool_call_limit=20,
        input_token_limit=10_000,
        output_token_limit=10_000,
        workbook_execution_limit=5,
        retry_limit=2,
        elapsed_time_limit_seconds=30,
    )

    result = run_agentic(
        MUTANT,
        POLICY,
        tmp_path,
        model=model,
        model_id="scripted-agent-test",
        limits=limits,
        run_id="agent-behavior-test",
    )

    assert result.decision == "REPAIR"
    discovery_requests = [
        request
        for request in model.manager_requests
        if "search_policy" in {tool.name for tool in request.tools}
    ]
    assert all(request.parallel_tool_calls for request in discovery_requests)
    assert [tool.name for tool in model.manager_requests[3].tools] == ["falsify_candidate"]
    assert [tool.name for tool in model.manager_requests[5].tools] == ["falsify_candidate"]
    assert [tool.name for tool in model.manager_requests[6].tools] == ["submit_repair"]
    assert model.manager_requests[-1].parallel_tool_calls is False
    first_falsifier_goal = model.falsifier_requests[0].messages[1].content
    assert model.citation_id in first_falsifier_goal
    assert "manager-observation" in first_falsifier_goal
    assert "record_sha256" in first_falsifier_goal
    assert result.output_workbook is None
    assert hashlib.sha256(MUTANT.read_bytes()).hexdigest() == source_hash
    state = (tmp_path / result.run_id / "agent-state.json").read_text(encoding="utf-8")
    assert state.count("proposal-") >= 2
    fifth_manager_request = model.manager_requests[4].model_dump_json()
    assert "BROKEN" in fifth_manager_request
    trace = tmp_path / result.run_id / "trajectory.jsonl"
    assert verify_trajectory(trace)["event_count"] >= 20
    trace_text = trace.read_text(encoding="utf-8")
    assert '"actor": "audit-manager"' in trace_text
    assert '"actor": "falsifier"' in trace_text

    proposal_path = tmp_path / result.run_id / "proposal.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    approved = approve_agentic_proposal(
        MUTANT,
        POLICY,
        tmp_path,
        result.run_id,
        reviewer="reviewer@example.test",
        expected_proposal_hash=object_hash(proposal),
    )
    assert approved.output_workbook is not None
    assert changed_workbook_formulas(MUTANT, Path(approved.output_workbook)) == {
        "RebateCalc!P6": (result.patches[0].old_formula, result.patches[0].new_formula)
    }
    assert hashlib.sha256(MUTANT.read_bytes()).hexdigest() == source_hash


def test_single_agent_baseline_has_one_candidate_and_no_falsifier(tmp_path: Path) -> None:
    result = run_agentic_baseline(
        MUTANT,
        POLICY,
        tmp_path,
        model=SingleAgentScript(),
        model_id="scripted-single-agent",
        run_id="single-agent-test",
    )

    assert result.decision == "REPAIR"
    assert result.method == "formulawitness-agentic-single-agent-baseline-v1"
    trace = (tmp_path / result.run_id / "trajectory.jsonl").read_text(encoding="utf-8")
    assert '"actor": "falsifier"' not in trace
