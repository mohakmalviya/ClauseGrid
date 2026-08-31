from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast

import pytest

from formulawitness.agent_budget import AgentBudgetLedger, AgentRuntimeLimits
from formulawitness.agent_loop import ToolCallingAgent
from formulawitness.agent_state import (
    AgentRunState,
    CandidateEdit,
    CandidateProposal,
    CitationEvidence,
    ExperimentEvidence,
    FalsifierVerdict,
)
from formulawitness.agent_tools import AgentToolRegistry, ToolEnvelope
from formulawitness.agent_types import (
    AssistantMessage,
    ModelRequest,
    ModelTurn,
    ModelUsage,
    NamedToolChoice,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
)
from formulawitness.trace import Trajectory


def _spec(name: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"Exercise the {name} action.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    )


class DeadlineRegistry:
    def __init__(self, terminal: dict[str, bool]) -> None:
        self.specs = (_spec("inspect"), _spec("report_falsification"))
        self.terminal = terminal

    def execute(self, call: ToolCall) -> ToolEnvelope:
        if call.name == "report_falsification":
            self.terminal["done"] = True
        return ToolEnvelope(ok=True, tool=call.name, result={"accepted": True})


class DeadlineModel:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelTurn:
        self.requests.append(request)
        if len(self.requests) == 1:
            call = ToolCall(call_id="inspect-1", name="inspect", arguments={})
        else:
            call = ToolCall(call_id="report-1", name="report_falsification", arguments={})
        return ModelTurn(
            model="deadline-test",
            tool_calls=(call,),
            finish_reason="tool_calls",
            usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            elapsed_ms=1,
        )


class CoordinationRegistry:
    def __init__(self, terminal: dict[str, bool]) -> None:
        self.specs = (
            _spec("inspect"),
            _spec("stage_candidate"),
            _spec("request_human"),
        )
        self.terminal = terminal
        self.state: AgentRunState | None = None

    def execute(self, call: ToolCall) -> ToolEnvelope:
        if call.name == "request_human":
            self.terminal["done"] = True
        return ToolEnvelope(ok=True, tool=call.name, result={"accepted": True})


class CoordinationModel:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelTurn:
        self.requests.append(request)
        name = "inspect" if len(self.requests) == 1 else "request_human"
        return ModelTurn(
            model="coordination-test",
            tool_calls=(ToolCall(call_id=f"call-{len(self.requests)}", name=name, arguments={}),),
            finish_reason="tool_calls",
            usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            elapsed_ms=1,
        )


class CacheRegistry:
    def __init__(self, terminal: dict[str, bool]) -> None:
        self.specs = (_spec("inspect"), _spec("report_falsification"))
        self.terminal = terminal
        self.execute_counts = {"inspect": 0, "report_falsification": 0}

    def cache_key(self, call: ToolCall) -> str | None:
        if call.name == "inspect":
            return json.dumps(
                {"arguments": call.arguments, "tool": call.name},
                sort_keys=True,
                separators=(",", ":"),
            )
        return None

    def execute(self, call: ToolCall) -> ToolEnvelope:
        self.execute_counts[call.name] += 1
        if call.name == "report_falsification":
            self.terminal["done"] = True
        return ToolEnvelope(ok=True, tool=call.name, result={"accepted": True})


class DuplicateReadModel:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelTurn:
        self.requests.append(request)
        turn = len(self.requests)
        name = "inspect" if turn < 3 else "report_falsification"
        return ModelTurn(
            model="duplicate-read-test",
            tool_calls=(
                ToolCall(
                    call_id=f"call-{turn}",
                    name=name,
                    arguments={"region": "A1:B2"} if name == "inspect" else {},
                ),
            ),
            finish_reason="tool_calls",
            usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            elapsed_ms=1,
        )


class ExperimentProgressRegistry:
    def __init__(self, terminal: dict[str, bool]) -> None:
        self.specs = (_spec("inspect"), _spec("run_experiment"), _spec("request_human"))
        self.terminal = terminal
        self.state = AgentRunState(
            run_id="experiment-progress",
            source_sha256="1" * 64,
            policy_sha256="2" * 64,
        )
        citation = CitationEvidence(
            citation_id="citation-123456789abc",
            document_sha256="2" * 64,
            page=2,
            start_char=0,
            end_char=20,
            exact_quote="Policy experiment rule.",
            quote_sha256="3" * 64,
        )
        self.state.citations[citation.citation_id] = citation

    def execute(self, call: ToolCall) -> ToolEnvelope:
        if call.name == "run_experiment":
            self.state.experiments["experiment-progress"] = ExperimentEvidence(
                experiment_id="experiment-progress",
                actor="audit-manager",
                request={"expectations": []},
                observation={"observations": {"A1": 1}},
            )
        if call.name == "request_human":
            self.terminal["done"] = True
        return ToolEnvelope(ok=True, tool=call.name, result={"accepted": True})


class ExperimentProgressModel:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelTurn:
        self.requests.append(request)
        turn = len(self.requests)
        if turn <= 2:
            name = "inspect"
        elif turn == 3:
            name = "run_experiment"
        else:
            name = "request_human"
        return ModelTurn(
            model="experiment-progress-test",
            tool_calls=(ToolCall(call_id=f"progress-{turn}", name=name, arguments={}),),
            finish_reason="tool_calls",
            usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            elapsed_ms=1,
        )


def _limits(
    *,
    falsifier_turns: int = 2,
    model_calls: int = 4,
    tool_calls: int = 4,
    input_tokens: int = 1_000,
) -> AgentRuntimeLimits:
    return AgentRuntimeLimits(
        manager_turn_limit=0,
        falsifier_turn_limit=falsifier_turns,
        model_call_limit=model_calls,
        tool_call_limit=tool_calls,
        input_token_limit=input_tokens,
        output_token_limit=1_000,
        workbook_execution_limit=0,
        retry_limit=1,
        elapsed_time_limit_seconds=30.0,
    )


@pytest.mark.parametrize(
    ("falsifier_turns", "model_calls", "tool_calls"),
    [(2, 4, 4), (4, 2, 4), (4, 4, 2)],
)
def test_final_turn_exposes_and_forces_only_terminal_tool(
    tmp_path: Path, falsifier_turns: int, model_calls: int, tool_calls: int
) -> None:
    terminal = {"done": False}
    model = DeadlineModel()
    registry = DeadlineRegistry(terminal)
    loop = ToolCallingAgent(
        actor="falsifier",
        model=model,
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(
            _limits(
                falsifier_turns=falsifier_turns,
                model_calls=model_calls,
                tool_calls=tool_calls,
            )
        ),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "deadline-test"),
        system_prompt="Test system prompt.",
        goal="Inspect once and then report.",
        prompt_version="deadline-test-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("report_falsification",),
    )

    loop.run()

    assert terminal["done"] is True
    assert len(model.requests) == 2
    first, final = model.requests
    assert {tool.name for tool in first.tools} == {"inspect", "report_falsification"}
    assert "two action slots remain" in first.messages[-1].content.lower()
    assert [tool.name for tool in final.tools] == ["report_falsification"]
    assert final.tool_choice == NamedToolChoice(name="report_falsification")
    assert final.parallel_tool_calls is False
    assert "final model turn" in final.messages[-1].content.lower()


def _manager_state_with_falsifier_verdict(
    status: Literal["BROKEN", "SURVIVED"],
) -> AgentRunState:
    state = AgentRunState(
        run_id=f"terminal-{status.lower()}",
        source_sha256="1" * 64,
        policy_sha256="2" * 64,
    )
    state.candidate = CandidateProposal(
        source_sha256=state.source_sha256,
        policy_sha256=state.policy_sha256,
        edits=(
            CandidateEdit(
                sheet="Sheet1",
                cell="A1",
                old_formula_sha256="3" * 64,
                new_formula="=2",
                rationale="Exercise state-aware terminal action selection.",
                evidence_ids=("citation-123456789abc",),
            ),
        ),
        expected_invariants=("Unrelated cells remain unchanged.",),
    )
    state.falsifier_verdict = FalsifierVerdict(
        status=status,
        proposal_id=state.candidate.proposal_id,
        experiment_ids=("falsifier-check",),
        counterexamples=("The candidate failed an independent check.",)
        if status == "BROKEN"
        else (),
        remaining_risks=(),
        explanation="Independent verification completed for the staged candidate.",
    )
    return state


class CandidateTerminalRegistry:
    def __init__(self, status: Literal["BROKEN", "SURVIVED"]) -> None:
        self.specs = tuple(
            _spec(name) for name in ("submit_repair", "finish_no_change", "request_human")
        )
        self.state = _manager_state_with_falsifier_verdict(status)

    def execute(self, call: ToolCall) -> ToolEnvelope:
        return ToolEnvelope(ok=True, tool=call.name, result={"accepted": True})


def test_broken_candidate_final_mode_exposes_only_request_human(tmp_path: Path) -> None:
    registry = CandidateTerminalRegistry("BROKEN")
    loop = ToolCallingAgent(
        actor="audit-manager",
        model=CoordinationModel(),
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(
            AgentRuntimeLimits(
                manager_turn_limit=2,
                falsifier_turn_limit=0,
                model_call_limit=2,
                tool_call_limit=2,
                input_token_limit=1_000,
                output_token_limit=1_000,
                workbook_execution_limit=0,
                retry_limit=0,
                elapsed_time_limit_seconds=30,
            )
        ),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "broken-terminal"),
        system_prompt="Test terminal actions after broken falsification.",
        goal="Expose only a safe terminal action.",
        prompt_version="broken-terminal-v1",
        is_terminal=lambda: False,
        terminal_tool_names=("submit_repair", "finish_no_change", "request_human"),
    )

    tools = loop._request_tools(final_turn=True)

    assert [tool.name for tool in tools] == ["request_human"]


def test_rejected_last_terminal_action_uses_fallback_without_extra_model_call(
    tmp_path: Path,
) -> None:
    terminal = {"done": False}
    fallback_reasons: list[str] = []

    class RejectingTerminalRegistry:
        specs = (_spec("request_human"),)

        def execute(self, call: ToolCall) -> ToolEnvelope:
            return ToolEnvelope(
                ok=False,
                tool=call.name,
                error="Evidence guard rejected the terminal action",
                error_type="ValueError",
            )

    class LastTurnModel:
        def __init__(self) -> None:
            self.requests: list[ModelRequest] = []

        def complete(self, request: ModelRequest) -> ModelTurn:
            self.requests.append(request)
            return ModelTurn(
                model="last-turn-test",
                tool_calls=(ToolCall(call_id="terminal-20", name="request_human", arguments={}),),
                finish_reason="tool_calls",
                usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15),
                elapsed_ms=1,
            )

    limits = AgentRuntimeLimits(
        manager_turn_limit=20,
        falsifier_turn_limit=0,
        model_call_limit=25,
        tool_call_limit=5,
        input_token_limit=1_000,
        output_token_limit=1_000,
        workbook_execution_limit=0,
        retry_limit=0,
        elapsed_time_limit_seconds=30,
    )
    budget = AgentBudgetLedger(limits)
    for _ in range(19):
        budget.record_model_call("manager", input_tokens=0, output_tokens=0)
    model = LastTurnModel()

    def terminal_fallback(reason: str) -> None:
        fallback_reasons.append(reason)
        terminal["done"] = True

    loop = ToolCallingAgent(
        actor="audit-manager",
        model=model,
        registry=cast(AgentToolRegistry, RejectingTerminalRegistry()),
        budget=budget,
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "terminal-fallback"),
        system_prompt="Test the last-turn fallback.",
        goal="Stop safely after a rejected terminal action.",
        prompt_version="terminal-fallback-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("request_human",),
        terminal_fallback=terminal_fallback,
    )

    loop.run()

    assert terminal["done"] is True
    assert fallback_reasons == ["final_terminal_action_was_rejected"]
    assert len(model.requests) == 1
    assert model.requests[0].tool_choice == NamedToolChoice(name="request_human")
    assert budget.snapshot()["manager_turns_used"] == 20
    trace = (tmp_path / "trajectory.jsonl").read_text(encoding="utf-8")
    assert '"event_type": "TERMINAL_FALLBACK"' in trace


def test_survived_candidate_final_mode_exposes_only_submit_repair(tmp_path: Path) -> None:
    registry = CandidateTerminalRegistry("SURVIVED")
    loop = ToolCallingAgent(
        actor="audit-manager",
        model=CoordinationModel(),
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(
            AgentRuntimeLimits(
                manager_turn_limit=2,
                falsifier_turn_limit=0,
                model_call_limit=2,
                tool_call_limit=2,
                input_token_limit=1_000,
                output_token_limit=1_000,
                workbook_execution_limit=0,
                retry_limit=0,
                elapsed_time_limit_seconds=30,
            )
        ),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "survived-terminal"),
        system_prompt="Test terminal actions after survived falsification.",
        goal="Expose only repair submission.",
        prompt_version="survived-terminal-v1",
        is_terminal=lambda: False,
        terminal_tool_names=("submit_repair", "finish_no_change", "request_human"),
    )

    tools = loop._request_tools(final_turn=True)

    assert [tool.name for tool in tools] == ["submit_repair"]


def test_terminal_tool_must_exist_in_registry(tmp_path: Path) -> None:
    registry = DeadlineRegistry({"done": False})

    with pytest.raises(ValueError, match="Terminal tools"):
        ToolCallingAgent(
            actor="falsifier",
            model=DeadlineModel(),
            registry=cast(AgentToolRegistry, registry),
            budget=AgentBudgetLedger(_limits()),
            trajectory=Trajectory(tmp_path / "trajectory.jsonl", "bad-terminal"),
            system_prompt="Test system prompt.",
            goal="Reject an unknown terminal tool.",
            prompt_version="deadline-test-v1",
            is_terminal=lambda: False,
            terminal_tool_names=("missing",),
        )


def test_duplicate_deterministic_read_is_cached_without_consuming_tool_budget(
    tmp_path: Path,
) -> None:
    terminal = {"done": False}
    model = DuplicateReadModel()
    registry = CacheRegistry(terminal)
    trajectory_path = tmp_path / "trajectory.jsonl"
    loop = ToolCallingAgent(
        actor="falsifier",
        model=model,
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(_limits(falsifier_turns=3, model_calls=3, tool_calls=3)),
        trajectory=Trajectory(trajectory_path, "duplicate-read-test"),
        system_prompt="Test duplicate deterministic read caching.",
        goal="Read one region twice, then report.",
        prompt_version="duplicate-read-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("report_falsification",),
    )

    loop.run()

    assert terminal["done"] is True
    assert registry.execute_counts == {"inspect": 1, "report_falsification": 1}
    records = [
        json.loads(line) for line in trajectory_path.read_text(encoding="utf-8").splitlines()
    ]
    inspect_calls = [
        record
        for record in records
        if record["event_type"] == "TOOL_CALL" and record["payload"]["name"] == "inspect"
    ]
    assert [record["payload"]["cache_hit"] for record in inspect_calls] == [False, True]


def test_controller_requires_experiment_after_bounded_discovery_turns(tmp_path: Path) -> None:
    terminal = {"done": False}
    registry = ExperimentProgressRegistry(terminal)
    model = ExperimentProgressModel()
    limits = AgentRuntimeLimits(
        manager_turn_limit=4,
        falsifier_turn_limit=0,
        model_call_limit=4,
        tool_call_limit=4,
        input_token_limit=1_000,
        output_token_limit=1_000,
        workbook_execution_limit=1,
        retry_limit=1,
        elapsed_time_limit_seconds=30,
    )
    loop = ToolCallingAgent(
        actor="audit-manager",
        model=model,
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(limits),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "experiment-progress"),
        system_prompt="Test bounded discovery-to-experiment progress.",
        goal="Inspect twice, execute evidence, then escalate.",
        prompt_version="experiment-progress-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("request_human",),
        require_experiment_after_turns=2,
    )

    loop.run()

    experiment_request = model.requests[2]
    assert [tool.name for tool in experiment_request.tools] == ["run_experiment"]
    assert experiment_request.tool_choice == NamedToolChoice(name="run_experiment")
    assert experiment_request.parallel_tool_calls is False
    notice = cast(str, experiment_request.messages[-1].content)
    assert "Run one discriminating sandbox experiment now" in notice


def test_formula_cell_value_rejection_forces_dependency_recovery(tmp_path: Path) -> None:
    terminal = {"done": False}

    class RecoveryRegistry(ExperimentProgressRegistry):
        def __init__(self) -> None:
            super().__init__(terminal)
            self.specs = (
                _spec("inspect"),
                _spec("inspect_dependencies"),
                _spec("run_experiment"),
                _spec("request_human"),
            )
            self.experiment_attempts = 0

        def execute(self, call: ToolCall) -> ToolEnvelope:
            if call.name == "run_experiment":
                self.experiment_attempts += 1
                if self.experiment_attempts == 1:
                    return ToolEnvelope(
                        ok=False,
                        tool=call.name,
                        error=(
                            "Value override cannot replace formula cell L6; "
                            "use formula_overrides"
                        ),
                        error_type="ExecutionFailed",
                    )
            return super().execute(call)

    class RecoveryModel:
        def __init__(self) -> None:
            self.requests: list[ModelRequest] = []

        def complete(self, request: ModelRequest) -> ModelTurn:
            self.requests.append(request)
            actions = (
                ("inspect", {}),
                ("inspect", {}),
                (
                    "run_experiment",
                    {"sheet": "RebateCalc", "overrides": {"L6": 1}},
                ),
                ("inspect_dependencies", {"roots": ["RebateCalc!L6"]}),
                (
                    "run_experiment",
                    {"sheet": "RebateCalc", "overrides": {"J6": 1}},
                ),
                ("request_human", {}),
            )
            name, arguments = actions[len(self.requests) - 1]
            return ModelTurn(
                model="dependency-recovery-test",
                tool_calls=(
                    ToolCall(
                        call_id=f"recovery-{len(self.requests)}",
                        name=name,
                        arguments=arguments,
                    ),
                ),
                finish_reason="tool_calls",
                usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15),
                elapsed_ms=1,
            )

    registry = RecoveryRegistry()
    model = RecoveryModel()
    loop = ToolCallingAgent(
        actor="audit-manager",
        model=model,
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(
            AgentRuntimeLimits(6, 0, 6, 6, 2_000, 2_000, 2, 1, 30.0)
        ),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "dependency-recovery"),
        system_prompt="Recover safely from a formula-cell value override.",
        goal="Inspect dependencies before retrying with actual input cells.",
        prompt_version="dependency-recovery-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("request_human",),
        require_experiment_after_turns=2,
        experiment_attempt_limit=3,
    )

    loop.run()

    assert [tool.name for tool in model.requests[3].tools] == ["inspect_dependencies"]
    assert model.requests[3].tool_choice == NamedToolChoice(name="inspect_dependencies")
    assert "RebateCalc!L6" in cast(str, model.requests[3].messages[-1].content)
    assert [tool.name for tool in model.requests[4].tools] == ["run_experiment"]
    assert model.requests[4].tool_choice == NamedToolChoice(name="run_experiment")
    assert registry.experiment_attempts == 2
    assert terminal["done"] is True


def test_evidence_closes_broad_discovery_with_eighteen_manager_turns_reserved(
    tmp_path: Path,
) -> None:
    terminal = {"done": False}
    registry = ExperimentProgressRegistry(terminal)

    class EvidenceCoordinationModel:
        def __init__(self) -> None:
            self.requests: list[ModelRequest] = []

        def complete(self, request: ModelRequest) -> ModelTurn:
            self.requests.append(request)
            turn = len(self.requests)
            name = "inspect" if turn <= 12 else "run_experiment"
            if turn > 13:
                name = "request_human"
            return ModelTurn(
                model="evidence-coordination-test",
                tool_calls=(ToolCall(call_id=f"evidence-{turn}", name=name, arguments={}),),
                finish_reason="tool_calls",
                usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15),
                elapsed_ms=1,
            )

    model = EvidenceCoordinationModel()
    loop = ToolCallingAgent(
        actor="audit-manager",
        model=model,
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(
            AgentRuntimeLimits(
                manager_turn_limit=30,
                falsifier_turn_limit=0,
                model_call_limit=30,
                tool_call_limit=30,
                input_token_limit=10_000,
                output_token_limit=10_000,
                workbook_execution_limit=2,
                retry_limit=1,
                elapsed_time_limit_seconds=30,
            )
        ),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "evidence-coordination"),
        system_prompt="Test evidence-aware coordination.",
        goal="Discover, experiment, then coordinate.",
        prompt_version="evidence-coordination-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("request_human",),
        terminal_tool_call_reserve=1,
        coordination_tool_names=("run_experiment", "request_human"),
        coordination_tool_call_reserve=10,
        evidence_aware_coordination=True,
        require_experiment_after_turns=12,
    )

    loop.run()

    assert [tool.name for tool in model.requests[12].tools] == ["run_experiment"]
    assert {tool.name for tool in model.requests[13].tools} == {
        "run_experiment",
        "request_human",
    }
    assert "inspect" not in {tool.name for tool in model.requests[13].tools}
    assert terminal["done"] is True


def test_falsifier_is_forced_from_discovery_to_experiment_then_verdict(tmp_path: Path) -> None:
    terminal = {"done": False}

    class FalsifierProgressRegistry:
        def __init__(self) -> None:
            self.specs = (
                _spec("inspect"),
                _spec("run_experiment"),
                _spec("report_falsification"),
            )
            self.state = AgentRunState(
                run_id="falsifier-progress",
                source_sha256="1" * 64,
                policy_sha256="2" * 64,
            )
            self.state.candidate = CandidateProposal(
                source_sha256="1" * 64,
                policy_sha256="2" * 64,
                edits=(
                    CandidateEdit(
                        sheet="Sheet1",
                        cell="A1",
                        old_formula_sha256="3" * 64,
                        new_formula="=1",
                        rationale="Candidate used to exercise falsifier progress controls.",
                        evidence_ids=("citation-123456789abc",),
                    ),
                ),
                expected_invariants=("A1 remains numeric",),
            )
            self.state.citations["citation-123456789abc"] = CitationEvidence(
                citation_id="citation-123456789abc",
                document_sha256="2" * 64,
                page=1,
                start_char=0,
                end_char=20,
                exact_quote="Candidate policy rule.",
                quote_sha256="4" * 64,
            )

        def execute(self, call: ToolCall) -> ToolEnvelope:
            if call.name == "run_experiment":
                self.state.experiments["falsifier-progress"] = ExperimentEvidence(
                    experiment_id="falsifier-progress",
                    actor="falsifier",
                    request={"expectations": [{"cell": "A1", "expected": 1}]},
                    observation={"observations": {"A1": 1}},
                )
            elif call.name == "report_falsification":
                terminal["done"] = True
            return ToolEnvelope(ok=True, tool=call.name, result={"accepted": True})

    class FalsifierProgressModel:
        def __init__(self) -> None:
            self.requests: list[ModelRequest] = []

        def complete(self, request: ModelRequest) -> ModelTurn:
            self.requests.append(request)
            turn = len(self.requests)
            name = "inspect" if turn <= 6 else "run_experiment"
            if turn > 7:
                name = "report_falsification"
            return ModelTurn(
                model="falsifier-progress-test",
                tool_calls=(ToolCall(call_id=f"falsifier-{turn}", name=name, arguments={}),),
                finish_reason="tool_calls",
                usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15),
                elapsed_ms=1,
            )

    registry = FalsifierProgressRegistry()
    model = FalsifierProgressModel()
    loop = ToolCallingAgent(
        actor="falsifier",
        model=model,
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(
            AgentRuntimeLimits(
                manager_turn_limit=0,
                falsifier_turn_limit=14,
                model_call_limit=14,
                tool_call_limit=30,
                input_token_limit=10_000,
                output_token_limit=10_000,
                workbook_execution_limit=2,
                retry_limit=1,
                elapsed_time_limit_seconds=30,
            )
        ),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "falsifier-progress"),
        system_prompt="Test falsifier progress controls.",
        goal="Inspect, execute one candidate-sensitive experiment, then report.",
        prompt_version="falsifier-progress-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("report_falsification",),
        terminal_tool_call_reserve=8,
        coordination_tool_names=("run_experiment", "report_falsification"),
        coordination_tool_call_reserve=10,
        evidence_aware_coordination=True,
        require_experiment_after_turns=6,
    )

    loop.run()

    assert [tool.name for tool in model.requests[6].tools] == ["run_experiment"]
    assert {tool.name for tool in model.requests[7].tools} == {
        "run_experiment",
        "report_falsification",
    }
    assert "inspect" not in {tool.name for tool in model.requests[7].tools}
    assert terminal["done"] is True
    loop._tool_attempt_counts["run_experiment"] = 4
    capped_tools = loop._request_tools(final_turn=False, coordination_mode=True)
    assert [tool.name for tool in capped_tools] == ["report_falsification"]


def test_input_budget_reserves_terminal_turn_before_hard_limit(tmp_path: Path) -> None:
    terminal = {"done": False}
    model = DeadlineModel()
    loop = ToolCallingAgent(
        actor="falsifier",
        model=model,
        registry=cast(AgentToolRegistry, DeadlineRegistry(terminal)),
        budget=AgentBudgetLedger(
            _limits(
                falsifier_turns=4,
                model_calls=4,
                tool_calls=4,
                input_tokens=100,
            )
        ),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "input-reserve-test"),
        system_prompt="Test system prompt.",
        goal="Inspect once and then report.",
        prompt_version="input-reserve-test-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("report_falsification",),
    )

    model.complete = lambda request: (  # type: ignore[method-assign]
        model.requests.append(request)
        or ModelTurn(
            model="deadline-test",
            tool_calls=(
                ToolCall(
                    call_id=f"call-{len(model.requests)}",
                    name=("inspect" if len(model.requests) == 1 else "report_falsification"),
                    arguments={},
                ),
            ),
            finish_reason="tool_calls",
            usage=ModelUsage(
                input_tokens=60 if len(model.requests) == 1 else 10,
                output_tokens=5,
                total_tokens=65 if len(model.requests) == 1 else 15,
            ),
            elapsed_ms=1,
        )
    )

    loop.run()

    assert terminal["done"] is True
    assert len(model.requests) == 2
    assert [tool.name for tool in model.requests[1].tools] == ["report_falsification"]
    assert "remaining resource budget" in model.requests[1].messages[-1].content


def test_tool_budget_reserve_stops_parallel_exploration_early(tmp_path: Path) -> None:
    terminal = {"done": False}
    model = DeadlineModel()
    loop = ToolCallingAgent(
        actor="falsifier",
        model=model,
        registry=cast(AgentToolRegistry, DeadlineRegistry(terminal)),
        budget=AgentBudgetLedger(_limits(falsifier_turns=4, model_calls=4, tool_calls=5)),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "tool-reserve-test"),
        system_prompt="Test system prompt.",
        goal="Inspect once and preserve four tool slots for terminal coordination.",
        prompt_version="tool-reserve-test-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("report_falsification",),
        terminal_tool_call_reserve=4,
    )

    loop.run()

    assert terminal["done"] is True
    assert len(model.requests) == 2
    assert [tool.name for tool in model.requests[1].tools] == ["report_falsification"]
    assert model.requests[1].parallel_tool_calls is False


def test_coordination_boundary_closes_discovery_before_terminal_reserve(
    tmp_path: Path,
) -> None:
    terminal = {"done": False}
    model = CoordinationModel()
    registry = CoordinationRegistry(terminal)
    registry.state = AgentRunState(
        run_id="coordination-test",
        source_sha256="1" * 64,
        policy_sha256="2" * 64,
    )
    citation = CitationEvidence(
        citation_id="citation-123456789abc",
        document_sha256="2" * 64,
        page=3,
        start_char=10,
        end_char=30,
        exact_quote="Registered policy evidence.",
        quote_sha256="3" * 64,
    )
    registry.state.citations[citation.citation_id] = citation
    registry.state.experiments["coordination-observation"] = ExperimentEvidence(
        experiment_id="coordination-observation",
        actor="audit-manager",
        request={"overrides": {"A1": 1}},
        observation={"observations": {"A1": 1}},
    )
    loop = ToolCallingAgent(
        actor="audit-manager",
        model=model,
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(
            AgentRuntimeLimits(
                manager_turn_limit=4,
                falsifier_turn_limit=0,
                model_call_limit=4,
                tool_call_limit=6,
                input_token_limit=1_000,
                output_token_limit=1_000,
                workbook_execution_limit=0,
                retry_limit=1,
                elapsed_time_limit_seconds=30,
            )
        ),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "coordination-test"),
        system_prompt="Test system prompt.",
        goal="Inspect once, then coordinate.",
        prompt_version="coordination-test-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("request_human",),
        terminal_tool_call_reserve=1,
        coordination_tool_names=("stage_candidate", "request_human"),
        coordination_tool_call_reserve=5,
    )

    loop.run()

    assert terminal["done"] is True
    assert {tool.name for tool in model.requests[0].tools} == {
        "inspect",
        "stage_candidate",
        "request_human",
    }
    assert {tool.name for tool in model.requests[1].tools} == {
        "stage_candidate",
        "request_human",
    }
    assert model.requests[1].parallel_tool_calls is False
    notice = cast(str, model.requests[1].messages[-1].content)
    assert "closed broad discovery" in notice
    assert citation.citation_id in notice
    assert citation.exact_quote in notice
    assert "IDs may be cited directly" in notice


def test_impossible_manager_actions_are_hidden_before_executable_evidence(
    tmp_path: Path,
) -> None:
    terminal = {"done": False}
    registry = CoordinationRegistry(terminal)
    registry.state = AgentRunState(
        run_id="precondition-filter",
        source_sha256="1" * 64,
        policy_sha256="2" * 64,
    )
    registry.state.citations["citation-123456789abc"] = CitationEvidence(
        citation_id="citation-123456789abc",
        document_sha256="2" * 64,
        page=1,
        start_char=0,
        end_char=20,
        exact_quote="Policy evidence exists.",
        quote_sha256="3" * 64,
    )
    loop = ToolCallingAgent(
        actor="audit-manager",
        model=CoordinationModel(),
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(_limits()),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "precondition-filter"),
        system_prompt="Test progress preconditions.",
        goal="Do not advertise actions that cannot pass validation.",
        prompt_version="precondition-filter-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("request_human",),
    )

    tools = loop._request_tools(final_turn=False)

    assert [tool.name for tool in tools] == ["inspect"]


def test_failed_evidence_ready_candidate_attempt_forces_candidate_retry(tmp_path: Path) -> None:
    terminal = {"done": False}
    registry = CoordinationRegistry(terminal)
    registry.state = AgentRunState(
        run_id="candidate-retry",
        source_sha256="1" * 64,
        policy_sha256="2" * 64,
    )
    citation = CitationEvidence(
        citation_id="citation-123456789abc",
        document_sha256="2" * 64,
        page=3,
        start_char=0,
        end_char=20,
        exact_quote="Candidate policy rule.",
        quote_sha256="3" * 64,
    )
    registry.state.citations[citation.citation_id] = citation
    registry.state.experiments["candidate-observation"] = ExperimentEvidence(
        experiment_id="candidate-observation",
        actor="audit-manager",
        request={"overrides": {"A1": 1}},
        observation={"observations": {"A1": 1}},
    )
    loop = ToolCallingAgent(
        actor="audit-manager",
        model=CoordinationModel(),
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(_limits()),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "candidate-retry"),
        system_prompt="Test candidate retry phase.",
        goal="Retry a malformed evidence-backed candidate.",
        prompt_version="candidate-retry-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("request_human",),
    )
    loop._candidate_attempted = True

    tools = loop._request_tools(final_turn=False)

    assert [tool.name for tool in tools] == ["stage_candidate"]


def test_two_rejected_candidates_force_fresh_experiment_before_another_retry(
    tmp_path: Path,
) -> None:
    terminal = {"done": False}

    class RecoveryRegistry(CoordinationRegistry):
        def __init__(self) -> None:
            super().__init__(terminal)
            self.specs = (
                _spec("inspect"),
                _spec("run_experiment"),
                _spec("stage_candidate"),
                _spec("request_human"),
            )
            self.state = AgentRunState(
                run_id="candidate-recovery",
                source_sha256="1" * 64,
                policy_sha256="2" * 64,
            )
            citation = CitationEvidence(
                citation_id="citation-123456789abc",
                document_sha256="2" * 64,
                page=1,
                start_char=0,
                end_char=20,
                exact_quote="Candidate recovery rule.",
                quote_sha256="3" * 64,
            )
            self.state.citations[citation.citation_id] = citation
            self.state.experiments["initial-evidence"] = ExperimentEvidence(
                experiment_id="initial-evidence",
                actor="audit-manager",
                request={"overrides": {"A1": 1}},
                observation={"observations": {"A1": 1}},
            )

    registry = RecoveryRegistry()
    loop = ToolCallingAgent(
        actor="audit-manager",
        model=CoordinationModel(),
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(_limits()),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "candidate-recovery"),
        system_prompt="Test candidate recovery phase.",
        goal="Recover from repeated rejected candidates.",
        prompt_version="candidate-recovery-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("request_human",),
    )
    loop._candidate_attempted = True
    loop._stage_failures_since_experiment = 2

    tools = loop._request_tools(final_turn=False)

    assert [tool.name for tool in tools] == ["run_experiment"]
    assert "stage_candidate" in loop._unavailable_progress_tools()


def test_two_rejected_no_change_attempts_remove_that_coordination_action(
    tmp_path: Path,
) -> None:
    terminal = {"done": False}
    registry = CoordinationRegistry(terminal)
    registry.specs = (
        _spec("inspect"),
        _spec("stage_candidate"),
        _spec("finish_no_change"),
        _spec("request_human"),
    )
    registry.state = AgentRunState(
        run_id="no-change-recovery",
        source_sha256="1" * 64,
        policy_sha256="2" * 64,
    )
    citation = CitationEvidence(
        citation_id="citation-123456789abc",
        document_sha256="2" * 64,
        page=1,
        start_char=0,
        end_char=20,
        exact_quote="No-change policy rule.",
        quote_sha256="3" * 64,
    )
    registry.state.citations[citation.citation_id] = citation
    for index in range(3):
        experiment_id = f"no-change-{index}"
        registry.state.experiments[experiment_id] = ExperimentEvidence(
            experiment_id=experiment_id,
            actor="audit-manager",
            request={"expectations": [{"cell": "A1", "expected": 1}]},
            observation={"comparisons": [{"cell": "A1", "matches": True}]},
        )
    loop = ToolCallingAgent(
        actor="audit-manager",
        model=CoordinationModel(),
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(_limits()),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "no-change-recovery"),
        system_prompt="Test no-change recovery.",
        goal="Remove repeatedly rejected terminal actions.",
        prompt_version="no-change-recovery-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("finish_no_change", "request_human"),
        coordination_tool_names=(
            "stage_candidate",
            "finish_no_change",
            "request_human",
        ),
        coordination_tool_call_reserve=2,
    )
    loop._tool_attempt_counts["finish_no_change"] = 2

    tools = loop._request_tools(final_turn=False, coordination_mode=True)
    final_tools = loop._request_tools(final_turn=True)

    assert {tool.name for tool in tools} == {"stage_candidate", "request_human"}
    assert [tool.name for tool in final_tools] == ["request_human"]


def test_inconclusive_candidate_requires_new_evidence_or_revision_before_refalsifying(
    tmp_path: Path,
) -> None:
    terminal = {"done": False}

    class CandidatePhaseRegistry:
        def __init__(self) -> None:
            self.specs = tuple(
                _spec(name)
                for name in (
                    "run_experiment",
                    "stage_candidate",
                    "falsify_candidate",
                    "request_human",
                )
            )
            self.state = AgentRunState(
                run_id="inconclusive-candidate",
                source_sha256="1" * 64,
                policy_sha256="2" * 64,
            )
            self.state.candidate = CandidateProposal(
                source_sha256="1" * 64,
                policy_sha256="2" * 64,
                edits=(
                    CandidateEdit(
                        sheet="Sheet1",
                        cell="A1",
                        old_formula_sha256="3" * 64,
                        new_formula="=1",
                        rationale="Candidate used to test inconclusive phase control.",
                        evidence_ids=("citation-123456789abc",),
                    ),
                ),
                expected_invariants=("A1 remains numeric",),
            )
            self.state.falsifier_verdict = FalsifierVerdict(
                status="INCONCLUSIVE",
                proposal_id=self.state.candidate.proposal_id,
                experiment_ids=(),
                counterexamples=(),
                explanation="The first independent check lacked conclusive evidence.",
                remaining_risks=("Candidate boundary is untested.",),
            )

        def execute(self, call: ToolCall) -> ToolEnvelope:
            return ToolEnvelope(ok=True, tool=call.name, result={"accepted": True})

    registry = CandidatePhaseRegistry()
    loop = ToolCallingAgent(
        actor="audit-manager",
        model=CoordinationModel(),
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(_limits()),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "inconclusive-candidate"),
        system_prompt="Test inconclusive candidate phase.",
        goal="Require new evidence or a revised proposal.",
        prompt_version="inconclusive-candidate-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("request_human",),
    )

    tools = loop._request_tools(final_turn=False)

    assert {tool.name for tool in tools} == {
        "run_experiment",
        "stage_candidate",
        "request_human",
    }


def test_policy_exception_forces_cross_product_experiment_before_preservation(
    tmp_path: Path,
) -> None:
    terminal = {"done": False}
    registry = ExperimentProgressRegistry(terminal)
    citation = next(iter(registry.state.citations.values()))
    registry.state.citations[citation.citation_id] = citation.model_copy(
        update={"exact_quote": "A waiver removes only the critical exception."}
    )
    for index in range(3):
        registry.state.experiments[f"ordinary-{index}"] = ExperimentEvidence(
            experiment_id=f"ordinary-{index}",
            actor="audit-manager",
            request={
                "purpose": "Test an ordinary boundary.",
                "overrides": {"A1": index},
            },
            observation={"observations": {"B1": index}},
        )
    limits = AgentRuntimeLimits(10, 0, 12, 12, 10_000, 10_000, 4, 1, 30.0)
    budget = AgentBudgetLedger(limits)
    for _ in range(3):
        budget.record_model_call("manager", input_tokens=10, output_tokens=5)
    loop = ToolCallingAgent(
        actor="audit-manager",
        model=CoordinationModel(),
        registry=cast(AgentToolRegistry, registry),
        budget=budget,
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "exception-scope"),
        system_prompt="Test exception coverage.",
        goal="Do not preserve without testing exception scope.",
        prompt_version="exception-scope-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("request_human",),
        require_experiment_after_turns=1,
        experiment_attempt_limit=4,
    )
    loop._tool_attempt_counts["run_experiment"] = 3

    assert loop._experiment_required(budget.snapshot())
    notice = loop._budget_notice(turns_remaining=7, experiment_mode=True)
    assert "cross-product" in cast(str, notice[0].content)

    loop._tool_attempt_counts["run_experiment"] = 4
    assert not loop._experiment_required(budget.snapshot())
    assert not loop._exception_scope_mode
    loop._tool_attempt_counts["run_experiment"] = 3

    registry.state.experiments["without-waiver"] = ExperimentEvidence(
        experiment_id="without-waiver",
        actor="audit-manager",
        request={
            "purpose": "Test critical incident without waiver.",
            "overrides": {"A1": 1, "C1": "N"},
        },
        observation={"observations": {"B1": 0}},
    )
    assert loop._exception_scope_experiment_required(budget.snapshot())

    registry.state.experiments["waiver-cross"] = ExperimentEvidence(
        experiment_id="waiver-cross",
        actor="audit-manager",
        request={
            "purpose": "Test waiver scope with an independent violation.",
            "overrides": {"A1": 1, "C1": "Y"},
        },
        observation={"observations": {"B1": 0.75}},
    )
    assert not loop._exception_scope_experiment_required(budget.snapshot())


def test_oversized_parallel_group_is_compacted_without_breaking_tool_protocol(
    tmp_path: Path,
) -> None:
    terminal = {"done": False}
    loop = ToolCallingAgent(
        actor="falsifier",
        model=DeadlineModel(),
        registry=cast(AgentToolRegistry, DeadlineRegistry(terminal)),
        budget=AgentBudgetLedger(_limits()),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "parallel-compaction-test"),
        system_prompt="Test system prompt.",
        goal="Preserve the latest complete action group.",
        prompt_version="parallel-compaction-test-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("report_falsification",),
        max_context_chars=10_000,
    )
    calls = (
        ToolCall(call_id="call-a", name="inspect", arguments={"part": "a"}),
        ToolCall(call_id="call-b", name="inspect", arguments={"part": "b"}),
    )
    loop.messages.extend(
        [
            AssistantMessage(content=None, tool_calls=calls),
            ToolResultMessage(
                tool_call_id="call-a",
                name="inspect",
                content="a" * 9_000,
            ),
            ToolResultMessage(
                tool_call_id="call-b",
                name="inspect",
                content='{"formula":"' + '=IF(A1="quoted",1,0)' * 500 + '"}',
            ),
        ]
    )

    bounded = loop._bounded_messages(max_context_chars=10_000)

    assistant = next(message for message in bounded if isinstance(message, AssistantMessage))
    results = [message for message in bounded if isinstance(message, ToolResultMessage)]
    assert [call.call_id for call in assistant.tool_calls] == ["call-a", "call-b"]
    assert [message.tool_call_id for message in results] == ["call-a", "call-b"]
    assert all(json.loads(message.content)["context_compacted"] for message in results)
    assert sum(len(message.model_dump_json()) for message in bounded) <= 10_000


def test_terminal_notice_bounds_large_controller_evidence_ledger(tmp_path: Path) -> None:
    terminal = {"done": False}
    registry = CoordinationRegistry(terminal)
    registry.state = AgentRunState(
        run_id="bounded-controller-ledger",
        source_sha256="1" * 64,
        policy_sha256="2" * 64,
    )
    for index in range(48):
        citation = CitationEvidence(
            citation_id=f"citation-{index:012d}",
            document_sha256="2" * 64,
            page=(index % 4) + 1,
            start_char=index * 10,
            end_char=index * 10 + 100,
            exact_quote="Registered policy evidence.",
            quote_sha256="3" * 64,
        )
        registry.state.citations[citation.citation_id] = citation
    for index in range(32):
        experiment_id = f"experiment-{index:012d}"
        registry.state.experiments[experiment_id] = ExperimentEvidence(
            experiment_id=experiment_id,
            actor="audit-manager",
            request={"expectations": [{"cell": "A1", "expected": index}]},
            observation={"observations": {"A1": index}},
        )

    loop = ToolCallingAgent(
        actor="audit-manager",
        model=CoordinationModel(),
        registry=cast(AgentToolRegistry, registry),
        budget=AgentBudgetLedger(_limits()),
        trajectory=Trajectory(tmp_path / "trajectory.jsonl", "bounded-controller-ledger"),
        system_prompt="S" * 3_500,
        goal="G" * 1_000,
        prompt_version="bounded-controller-ledger-v1",
        is_terminal=lambda: terminal["done"],
        terminal_tool_names=("request_human",),
        max_context_chars=10_000,
    )
    for index in range(6):
        loop._observation_ledger[f"read-{index}"] = {
            "tool": "read_region",
            "arguments": {"sheet": "Inputs", "start": "A1", "end": "Z100"},
            "result": "x" * 10_000,
        }
    loop.messages.extend(
        [
            AssistantMessage(
                content=None,
                tool_calls=(ToolCall(call_id="inspect-large", name="inspect", arguments={}),),
            ),
            ToolResultMessage(
                tool_call_id="inspect-large",
                name="inspect",
                content="y" * 12_000,
            ),
        ]
    )

    notice = loop._budget_notice(
        turns_remaining=1,
        input_budget_terminal=True,
        context_limit=10_000,
    )
    bounded = loop._bounded_messages(
        trailing_messages=notice,
        max_context_chars=10_000,
    )

    assert sum(len(message.model_dump_json()) for message in bounded) <= 10_000
    assert "final model turn" in notice[0].content
    assert "Controller evidence ledger" in notice[0].content
    assert "Registered policy evidence." in notice[0].content
