from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from formulawitness.agent_budget import AgentBudgetLedger, AgentRuntimeLimits
from formulawitness.agent_loop import ToolCallingAgent
from formulawitness.agent_state import AgentRunState, CitationEvidence
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
    assert "IDs may be cited directly" in notice


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
