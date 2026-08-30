"""Observable model-controlled tool loop used by manager and falsifier agents."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from typing import Literal, Protocol

from .agent_budget import AgentBudgetExceeded, AgentBudgetLedger, AgentBudgetSnapshot
from .agent_state import CitationEvidence
from .agent_tools import AgentToolRegistry, ToolEnvelope
from .agent_types import (
    AssistantMessage,
    ChatMessage,
    ModelRequest,
    ModelRequestSettings,
    ModelTurn,
    NamedToolChoice,
    SystemMessage,
    ToolCall,
    ToolChoice,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)
from .model_client import ModelClientError
from .trace import Trajectory


class ChatModel(Protocol):
    def complete(self, request: ModelRequest) -> ModelTurn:
        """Return the next model-selected action."""


class ToolCallingAgent:
    """Let a model select tools and stopping actions from input-dependent observations."""

    def __init__(
        self,
        *,
        actor: Literal["audit-manager", "falsifier"],
        model: ChatModel,
        registry: AgentToolRegistry,
        budget: AgentBudgetLedger,
        trajectory: Trajectory,
        system_prompt: str,
        goal: str,
        prompt_version: str,
        is_terminal: Callable[[], bool],
        terminal_tool_names: tuple[str, ...] = (),
        terminal_tool_call_reserve: int = 1,
        coordination_tool_names: tuple[str, ...] = (),
        coordination_tool_call_reserve: int = 0,
        max_tokens_per_turn: int = 4_096,
        max_context_chars: int = 40_000,
        evidence_aware_coordination: bool = False,
        require_experiment_after_turns: int | None = None,
        experiment_attempt_limit: int | None = None,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ):
        self.actor = actor
        self.model = model
        self.registry = registry
        self.budget = budget
        self.trajectory = trajectory
        self.prompt_version = prompt_version
        self.is_terminal = is_terminal
        available_tools = {tool.name for tool in registry.specs}
        if not set(terminal_tool_names).issubset(available_tools):
            raise ValueError("Terminal tools must be present in the actor's registry")
        self.terminal_tool_names = terminal_tool_names
        if terminal_tool_call_reserve < 1:
            raise ValueError("Terminal tool-call reserve must be at least one")
        self.terminal_tool_call_reserve = terminal_tool_call_reserve
        if not set(coordination_tool_names).issubset(available_tools):
            raise ValueError("Coordination tools must be present in the actor's registry")
        if coordination_tool_call_reserve < 0:
            raise ValueError("Coordination tool-call reserve cannot be negative")
        if coordination_tool_names and (
            coordination_tool_call_reserve <= terminal_tool_call_reserve
        ):
            raise ValueError("Coordination reserve must exceed the terminal reserve")
        self.coordination_tool_names = coordination_tool_names
        self.coordination_tool_call_reserve = coordination_tool_call_reserve
        self.max_tokens_per_turn = max_tokens_per_turn
        if max_context_chars < 10_000:
            raise ValueError("Agent context limit must be at least 10,000 characters")
        self.max_context_chars = max_context_chars
        settings = getattr(model, "request_settings", ModelRequestSettings())
        if not isinstance(settings, ModelRequestSettings):
            raise TypeError("Model request_settings must be ModelRequestSettings")
        self.request_settings = settings
        self.evidence_aware_coordination = evidence_aware_coordination
        if require_experiment_after_turns is not None:
            if require_experiment_after_turns < 1:
                raise ValueError("Required-experiment turn threshold must be positive")
            if "run_experiment" not in available_tools:
                raise ValueError("Required-experiment mode needs a run_experiment tool")
        self.require_experiment_after_turns = require_experiment_after_turns
        if experiment_attempt_limit is not None and experiment_attempt_limit < 1:
            raise ValueError("Experiment attempt limit must be positive")
        self.experiment_attempt_limit = experiment_attempt_limit
        self.progress_callback = progress_callback
        self._last_input_tokens: int | None = None
        self._tool_result_cache: dict[str, ToolEnvelope] = {}
        self._tool_attempt_counts: dict[str, int] = {}
        self._observation_ledger: dict[str, dict[str, object]] = {}
        self._completed_one_shot_tools: set[str] = set()
        self._candidate_attempted = False
        self._stage_failures_since_experiment = 0
        self._exception_scope_mode = False
        self.messages: list[ChatMessage] = [
            SystemMessage(content=system_prompt),
            UserMessage(content=goal),
        ]

    def run(self) -> None:
        while not self.is_terminal():
            self._preflight_turn()
            snapshot = self.budget.snapshot()
            turns_remaining = self._turns_remaining(snapshot)
            input_budget_terminal = self._input_budget_requires_terminal(snapshot)
            tool_budget_terminal = self._tool_budget_requires_terminal(snapshot)
            final_turn = bool(self.terminal_tool_names) and (
                turns_remaining == 1 or input_budget_terminal or tool_budget_terminal
            )
            experiment_mode = not final_turn and self._experiment_required(snapshot)
            coordination_mode = (
                not final_turn
                and not experiment_mode
                and self._tool_budget_requires_coordination(snapshot)
            )
            tools = self._request_tools(
                final_turn=final_turn,
                coordination_mode=coordination_mode,
                experiment_mode=experiment_mode,
            )
            request_context_limit = self._request_context_limit(
                snapshot,
                final_turn=final_turn,
            )
            trailing_messages = self._budget_notice(
                turns_remaining=turns_remaining,
                input_budget_terminal=input_budget_terminal,
                tool_budget_terminal=tool_budget_terminal,
                coordination_mode=coordination_mode,
                experiment_mode=experiment_mode,
                context_limit=request_context_limit,
            )
            tool_choice: ToolChoice = "required"
            if len(tools) == 1:
                tool_choice = NamedToolChoice(name=tools[0].name)
            request = ModelRequest(
                messages=self._bounded_messages(
                    trailing_messages=trailing_messages,
                    max_context_chars=request_context_limit,
                ),
                tools=tools,
                tool_choice=tool_choice,
                parallel_tool_calls=(
                    self.request_settings.parallel_tool_calls
                    and not final_turn
                    and not coordination_mode
                    and not experiment_mode
                ),
                temperature=self.request_settings.temperature,
                top_p=self.request_settings.top_p,
                extra_body=self.request_settings.extra_body,
                max_tokens=min(
                    self.max_tokens_per_turn,
                    max(
                        1,
                        snapshot["output_token_limit"] - snapshot["output_tokens_used"],
                    ),
                ),
                attempt_limit=min(
                    6,
                    snapshot["model_call_limit"] - snapshot["model_calls_used"],
                    snapshot["retry_limit"] - snapshot["retries_used"] + 1,
                ),
            )
            self.trajectory.record_agent_event(
                self.actor,
                "MODEL_REQUEST",
                request.model_dump(mode="json"),
                model_id="pending-provider-response",
                prompt_version=self.prompt_version,
            )
            try:
                turn = self.model.complete(request)
            except ModelClientError as exc:
                actor: Literal["manager", "falsifier"] = (
                    "manager" if self.actor == "audit-manager" else "falsifier"
                )
                self.budget.record_model_call(
                    actor,
                    input_tokens=0,
                    output_tokens=0,
                    retries=exc.retry_count,
                )
                self.trajectory.record_agent_event(
                    self.actor,
                    "MODEL_ERROR",
                    {
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "status_code": exc.status_code,
                    },
                    model_id="pending-provider-response",
                    prompt_version=self.prompt_version,
                    retry_count=exc.retry_count,
                )
                raise
            self.budget.record_model_call(
                "manager" if self.actor == "audit-manager" else "falsifier",
                input_tokens=turn.usage.input_tokens,
                output_tokens=turn.usage.output_tokens,
                retries=turn.retry_count,
                reported_cost_usd=turn.usage.reported_cost_usd,
            )
            self._last_input_tokens = turn.usage.input_tokens
            self._notify_progress("model_response")
            self.trajectory.record_agent_event(
                self.actor,
                "MODEL_RESPONSE",
                {
                    "content": turn.content,
                    "tool_calls": [call.model_dump(mode="json") for call in turn.tool_calls],
                    "discarded_tool_calls": [
                        call.model_dump(mode="json") for call in turn.discarded_tool_calls
                    ],
                    "request_id": turn.request_id,
                    "response_id": turn.response_id,
                },
                model_id=turn.model,
                prompt_version=self.prompt_version,
                finish_reason=turn.finish_reason,
                usage=turn.usage.model_dump(mode="json"),
                elapsed_ms=turn.elapsed_ms,
                retry_count=turn.retry_count,
            )
            self.messages.append(turn.as_assistant_message())
            if not turn.tool_calls:
                self.messages.append(
                    UserMessage(
                        content=(
                            "A plain answer cannot finish this run. Select one available tool; "
                            "use a terminal tool only when its evidence guard is satisfied."
                        )
                    )
                )
                continue
            duplicate_notes: list[str] = []
            candidate_recovery_note = False
            for call in turn.tool_calls:
                if self.is_terminal():
                    break
                cache_key = self._cache_key(call)
                cache_hit = cache_key is not None and cache_key in self._tool_result_cache
                if not cache_hit:
                    self.budget.charge_tool_calls()
                self.trajectory.record_agent_event(
                    self.actor,
                    "TOOL_CALL",
                    call.model_dump(mode="json") | {"cache_hit": cache_hit},
                    model_id=turn.model,
                    prompt_version=self.prompt_version,
                )
                if cache_hit:
                    assert cache_key is not None
                    envelope = self._tool_result_cache[cache_key]
                    duplicate_notes.append(call.name)
                else:
                    self._tool_attempt_counts[call.name] = (
                        self._tool_attempt_counts.get(call.name, 0) + 1
                    )
                    if call.name == "stage_candidate":
                        self._candidate_attempted = True
                    envelope = self.registry.execute(call)
                    if call.name == "stage_candidate":
                        if envelope.ok:
                            self._stage_failures_since_experiment = 0
                        else:
                            self._stage_failures_since_experiment += 1
                            candidate_recovery_note = self._stage_failures_since_experiment == 2
                    elif call.name == "run_experiment" and envelope.ok:
                        self._stage_failures_since_experiment = 0
                    if cache_key is not None and envelope.ok:
                        self._tool_result_cache[cache_key] = envelope
                        self._register_observation(cache_key, call, envelope)
                        if call.name in {"policy_manifest", "workbook_manifest"}:
                            self._completed_one_shot_tools.add(call.name)
                self.trajectory.record_agent_event(
                    self.actor,
                    "TOOL_RESULT",
                    {
                        "call_id": call.call_id,
                        "tool": call.name,
                        "observation": {
                            "ok": envelope.ok,
                            "result": envelope.result,
                            "error": envelope.error,
                            "error_type": envelope.error_type,
                            "cache_hit": cache_hit,
                        },
                    },
                    model_id=turn.model,
                    prompt_version=self.prompt_version,
                )
                self.messages.append(
                    ToolResultMessage(
                        tool_call_id=call.call_id,
                        name=call.name,
                        content=envelope.to_model_json(),
                    )
                )
                self._notify_progress(
                    "tool_result",
                    tool=call.name,
                    ok=envelope.ok,
                )
            if duplicate_notes and not self.is_terminal():
                repeated = ", ".join(sorted(set(duplicate_notes)))
                self.messages.append(
                    UserMessage(
                        content=(
                            "Controller note: an exact duplicate read was served from cache and "
                            f"did not expand evidence ({repeated}). Choose a different or narrower "
                            "evidence action next."
                        )
                    )
                )
            if candidate_recovery_note and not self.is_terminal():
                self.messages.append(
                    UserMessage(
                        content=(
                            "Controller note: two candidate submissions were rejected. Do not "
                            "resubmit the same cell and formula. The next action is a fresh "
                            "workbook experiment that must discriminate a materially different "
                            "policy branch or dependency before another candidate is attempted."
                        )
                    )
                )

    def _bounded_messages(
        self,
        *,
        trailing_messages: tuple[ChatMessage, ...] = (),
        max_context_chars: int | None = None,
    ) -> tuple[ChatMessage, ...]:
        """Keep recent complete tool-call groups while the trajectory retains the full record."""

        context_limit = max_context_chars or self.max_context_chars
        serialized = sum(
            len(message.model_dump_json()) for message in [*self.messages, *trailing_messages]
        )
        if serialized <= context_limit:
            return (*self.messages, *trailing_messages)

        groups: list[list[ChatMessage]] = []
        current: list[ChatMessage] = []
        for message in self.messages[2:]:
            if isinstance(message, AssistantMessage) and current:
                groups.append(current)
                current = []
            current.append(message)
        if current:
            groups.append(current)

        base = list(self.messages[:2])
        # A controller notice may deliberately omit the ledger when the immutable base prompt
        # leaves no room. Do not reinsert an unbounded default ledger during compaction.
        ledger = "" if trailing_messages else self._evidence_ledger()
        summary = UserMessage(
            content=(
                "Earlier complete action groups were compacted after reaching the configured "
                "context limit. Their full requests, tool calls, and observations remain in the "
                "controller trajectory. Use registered handles from the controller evidence "
                "ledger below; re-query exact evidence while discovery tools remain available. "
                "Do not infer omitted facts." + ledger
            )
        )
        remaining = context_limit - sum(
            len(message.model_dump_json()) for message in [*base, summary, *trailing_messages]
        )
        selected: list[list[ChatMessage]] = []
        for group in reversed(groups):
            size = sum(len(message.model_dump_json()) for message in group)
            if size > remaining:
                if not selected:
                    compacted_group = self._compact_action_group(group, remaining)
                    compacted_size = sum(
                        len(message.model_dump_json()) for message in compacted_group
                    )
                    if compacted_size <= remaining:
                        selected.append(compacted_group)
                        remaining -= compacted_size
                break
            selected.append(group)
            remaining -= size
        if not selected:
            compacted_without_history = [*base, summary, *trailing_messages]
            if (
                sum(len(message.model_dump_json()) for message in compacted_without_history)
                <= context_limit
            ):
                return tuple(compacted_without_history)
            raise RuntimeError("Agent base context exceeds the context limit")
        compacted = [*base, summary]
        for group in reversed(selected):
            compacted.extend(group)
        compacted.extend(trailing_messages)
        return tuple(compacted)

    def _notify_progress(
        self,
        event: str,
        *,
        tool: str | None = None,
        ok: bool | None = None,
    ) -> None:
        """Publish non-sensitive progress without allowing UI failures to stop an audit."""

        if self.progress_callback is None:
            return
        payload: dict[str, object] = {
            "actor": self.actor,
            "event": event,
            "budget": self.budget.snapshot(),
        }
        if tool is not None:
            payload["tool"] = tool
        if ok is not None:
            payload["ok"] = ok
        try:
            self.progress_callback(payload)
        except Exception:  # noqa: BLE001 - observability must never control audit behavior
            return

    def _compact_action_group(
        self,
        group: list[ChatMessage],
        char_budget: int,
    ) -> list[ChatMessage]:
        """Preserve tool protocol IDs while bounding oversized parallel observations."""

        tool_results = [message for message in group if isinstance(message, ToolResultMessage)]
        if not tool_results or char_budget <= 0:
            return group
        fixed_chars = sum(
            len(message.model_dump_json())
            for message in group
            if not isinstance(message, ToolResultMessage)
        )
        preview_chars = max(
            0,
            (char_budget - fixed_chars) // len(tool_results) - 512,
        )
        while True:
            compacted: list[ChatMessage] = []
            for message in group:
                if not isinstance(message, ToolResultMessage):
                    compacted.append(message)
                    continue
                content = message.content
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                compacted.append(
                    message.model_copy(
                        update={
                            "content": json.dumps(
                                {
                                    "context_compacted": True,
                                    "original_chars": len(content),
                                    "sha256": digest,
                                    "preview": content[:preview_chars],
                                    "instruction": (
                                        "Full result remains in the trajectory; call the tool "
                                        "again with a narrower request when exact fields are needed."
                                    ),
                                },
                                sort_keys=True,
                                separators=(",", ":"),
                            )
                        }
                    )
                )
            actual_chars = sum(len(message.model_dump_json()) for message in compacted)
            if actual_chars <= char_budget or preview_chars == 0:
                return compacted
            excess_per_result = math.ceil((actual_chars - char_budget) / len(tool_results))
            preview_chars = max(0, preview_chars - excess_per_result - 32)

    def _request_tools(
        self,
        *,
        final_turn: bool,
        coordination_mode: bool = False,
        experiment_mode: bool = False,
    ) -> tuple[ToolSpec, ...]:
        if experiment_mode:
            tools = tuple(tool for tool in self.registry.specs if tool.name == "run_experiment")
            if len(tools) != 1:
                raise RuntimeError("Agent experiment phase has no unique run_experiment tool")
            return tools
        candidate_phase_names = self._candidate_phase_tool_names()
        if not final_turn and candidate_phase_names is not None:
            if self._experiment_attempt_limit_reached():
                candidate_phase_names.discard("run_experiment")
            tools = tuple(
                tool for tool in self.registry.specs if tool.name in candidate_phase_names
            )
            if not tools:
                raise RuntimeError("Agent candidate phase has no allowed tool")
            return tools
        if not final_turn and self._candidate_retry_required():
            tools = tuple(tool for tool in self.registry.specs if tool.name == "stage_candidate")
            if len(tools) != 1:
                raise RuntimeError("Agent candidate retry phase has no unique stage_candidate tool")
            return tools
        if not final_turn and self._candidate_evidence_recovery_required():
            tools = tuple(tool for tool in self.registry.specs if tool.name == "run_experiment")
            if len(tools) != 1:
                raise RuntimeError(
                    "Agent candidate recovery phase has no unique run_experiment tool"
                )
            return tools
        if not final_turn and not coordination_mode:
            unavailable = self._completed_one_shot_tools | self._unavailable_progress_tools()
            if self._experiment_attempt_limit_reached():
                unavailable.add("run_experiment")
            return tuple(tool for tool in self.registry.specs if tool.name not in unavailable)
        allowed = set(self.terminal_tool_names if final_turn else self.coordination_tool_names)
        if final_turn and self.actor == "audit-manager":
            filtered = allowed.difference(self._unavailable_progress_tools())
            # Keep at least one fail-closed terminal path even when its normal evidence
            # preconditions are unavailable; otherwise the controller could not stop safely.
            if filtered:
                allowed = filtered
        elif not final_turn:
            allowed.difference_update(self._unavailable_progress_tools())
            if self._experiment_attempt_limit_reached():
                allowed.discard("run_experiment")
        tools = tuple(tool for tool in self.registry.specs if tool.name in allowed)
        if not tools:
            phase = "terminal" if final_turn else "coordination"
            raise RuntimeError(f"Agent {phase} phase has no allowed tool")
        return tools

    def _experiment_attempt_limit_reached(self) -> bool:
        limit = self.experiment_attempt_limit
        if limit is None:
            limit = 8 if self.actor == "audit-manager" else 4
        return self._tool_attempt_counts.get("run_experiment", 0) >= limit

    def _unavailable_progress_tools(self) -> set[str]:
        """Hide manager actions whose mechanical preconditions do not yet exist."""

        if self.actor != "audit-manager":
            return set()
        state = getattr(self.registry, "state", None)
        if state is None or getattr(state, "candidate", None) is not None:
            return set()
        unavailable = {"falsify_candidate", "submit_repair"}
        citations = getattr(state, "citations", {})
        manager_experiments = [
            evidence
            for evidence in getattr(state, "experiments", {}).values()
            if getattr(evidence, "actor", None) == "audit-manager"
        ]
        if not citations or not manager_experiments:
            unavailable.update({"stage_candidate", "request_human"})
        elif self._stage_failures_since_experiment >= 2:
            unavailable.add("stage_candidate")
        if not citations or len(manager_experiments) < 3:
            unavailable.add("finish_no_change")
        elif self._tool_attempt_counts.get("finish_no_change", 0) >= 2:
            # A successful terminal call ends the loop. Reaching this branch means two
            # no-change attempts failed their evidence guard, so force a different outcome.
            unavailable.add("finish_no_change")
        return unavailable

    def _candidate_phase_tool_names(self) -> set[str] | None:
        """Advance staged manager candidates through mandatory independent falsification."""

        available = {tool.name for tool in self.registry.specs}
        if "falsify_candidate" not in available:
            return None
        state = getattr(self.registry, "state", None)
        if getattr(state, "candidate", None) is None:
            return None
        verdict = getattr(state, "falsifier_verdict", None)
        if verdict is None:
            return {"falsify_candidate"}
        if verdict.status == "SURVIVED":
            return {"submit_repair"}
        if verdict.status == "BROKEN":
            return {"run_experiment", "stage_candidate", "request_human"}
        return {"run_experiment", "stage_candidate", "request_human"}

    def _candidate_retry_required(self) -> bool:
        if not self._candidate_attempted:
            return False
        state = getattr(self.registry, "state", None)
        return bool(
            state is not None
            and getattr(state, "candidate", None) is None
            and getattr(state, "citations", {})
            and getattr(state, "experiments", {})
            and self._stage_failures_since_experiment < 2
        )

    def _candidate_evidence_recovery_required(self) -> bool:
        """Break repeated rejected candidate loops with fresh executable evidence."""

        if self.actor != "audit-manager" or self._stage_failures_since_experiment < 2:
            return False
        state = getattr(self.registry, "state", None)
        return bool(
            state is not None
            and getattr(state, "candidate", None) is None
            and not self._experiment_attempt_limit_reached()
        )

    def _budget_notice(
        self,
        *,
        turns_remaining: int,
        input_budget_terminal: bool = False,
        tool_budget_terminal: bool = False,
        coordination_mode: bool = False,
        experiment_mode: bool = False,
        context_limit: int | None = None,
    ) -> tuple[ChatMessage, ...]:
        if (
            (not self.terminal_tool_names or turns_remaining > 2)
            and not input_budget_terminal
            and not tool_budget_terminal
            and not coordination_mode
            and not experiment_mode
        ):
            return ()
        names = ", ".join(self.terminal_tool_names)
        if turns_remaining == 1 or input_budget_terminal or tool_budget_terminal:
            content = (
                "This is the final model turn allowed by the controller's remaining resource "
                "budget. Only terminal tools are "
                f"available ({names}); call one now. If the evidence is insufficient, choose the "
                "fail-closed terminal outcome rather than attempting more investigation."
            )
        elif experiment_mode:
            if self._exception_scope_mode:
                content = (
                    "Registered policy evidence contains a waiver, exception, or unless-clause "
                    "that no executed experiment has tested. Run one cross-product sandbox "
                    "experiment now: enable the exception while also activating an independent "
                    "ordinary violation, observe the governed formula output, and provide explicit "
                    "policy-derived expectations. Name the waiver or exception in the purpose. "
                    "Use only sheet names and cell coordinates from the successful workbook reads "
                    "below; never invent workbook coordinates." + self._workbook_coordinate_hint()
                )
            else:
                content = (
                    "The controller has observed enough discovery turns without executable "
                    "workbook evidence. Run one discriminating sandbox experiment now. Choose "
                    "input overrides, observations, and explicit expectations from the "
                    "policy/workbook evidence already registered; do not perform another "
                    "manifest, formula-list, or region read."
                )
        elif coordination_mode:
            names = ", ".join(self.coordination_tool_names)
            content = (
                "The controller has closed broad discovery to preserve the specialist and "
                "decision budget. Only coordination actions are available: "
                f"{names}. Run a targeted discriminating experiment when a material branch is "
                "still untested; otherwise stage the strongest evidence-backed candidate and "
                "invoke its falsifier, or finish/request human judgment when evidence is "
                "insufficient."
            )
        else:
            content = (
                "Controller budget notice: two action slots remain. Complete at most one final "
                f"high-information action, then finish through one of: {names}."
            )
        ledger_limit = 9_000
        if context_limit is not None:
            base_size = sum(len(message.model_dump_json()) for message in self.messages[:2])
            notice_size = len(UserMessage(content=content).model_dump_json())
            # _bounded_messages may add a short compaction explanation between the immutable
            # system/goal pair and this notice. Reserve room for that explanation and JSON
            # framing before deciding how much registered evidence can be repeated.
            ledger_limit = min(
                ledger_limit,
                max(0, context_limit - base_size - notice_size - 1_200),
            )
        return (UserMessage(content=content + self._evidence_ledger(max_chars=ledger_limit)),)

    def _workbook_coordinate_hint(self, *, max_chars: int = 2_500) -> str:
        """Repeat successful workbook reads next to forced experiment instructions."""

        useful = [
            entry
            for entry in self._observation_ledger.values()
            if entry.get("tool") in {"workbook_manifest", "read_region"}
        ]
        if not useful:
            return ""
        encoded = json.dumps(useful[-4:], sort_keys=True, separators=(",", ":"), default=str)
        if len(encoded) > max_chars:
            encoded = encoded[:max_chars] + "...[truncated]"
        return "\nSuccessful workbook coordinate evidence: " + encoded

    def _evidence_ledger(self, *, max_chars: int = 9_000) -> str:
        """Keep registered handles available when their original observations are compacted."""

        if max_chars <= 0:
            return ""
        state = getattr(self.registry, "state", None)
        if state is None:
            return ""

        citations = list(getattr(state, "citations", {}).values())
        # Preserve one broad citation per page plus recent citations without allowing repeated
        # searches to consume the whole model context. Broad page windows are the most reusable
        # handles after discovery closes.
        widest_by_page: dict[int, CitationEvidence] = {}
        for citation in citations:
            page = int(citation.page)
            current = widest_by_page.get(page)
            if current is None or (citation.end_char - citation.start_char) > (
                current.end_char - current.start_char
            ):
                widest_by_page[page] = citation
        selected_citations = list(widest_by_page.values())
        selected_ids = {citation.citation_id for citation in selected_citations}
        for citation in reversed(citations):
            if citation.citation_id not in selected_ids:
                selected_citations.append(citation)
                selected_ids.add(citation.citation_id)
            if len(selected_citations) >= 64:
                break
        selected_citations.sort(key=lambda item: (item.page, item.start_char, item.end_char))

        experiments = list(getattr(state, "experiments", {}).values())
        ledger: dict[str, object] = {
            "citations": [
                {
                    "id": citation.citation_id,
                    "page": citation.page,
                    "start": citation.start_char,
                    "end": citation.end_char,
                }
                for citation in selected_citations[:64]
            ],
            "experiments": [
                {
                    "id": evidence.experiment_id,
                    "actor": evidence.actor,
                    "proposal_id": evidence.proposal_id,
                    "has_expectations": bool(evidence.request.get("expectations")),
                    "candidate_sensitive_observations": list(
                        evidence.candidate_sensitive_observations
                    ),
                }
                for evidence in experiments[-64:]
            ],
            "candidate": None,
            "falsifier_verdict": None,
            "workbook_observations": self._bounded_observation_ledger(),
        }
        candidate = getattr(state, "candidate", None)
        if candidate is not None:
            ledger["candidate"] = {
                "proposal_id": candidate.proposal_id,
                "edits": [
                    {
                        "edit_id": edit.edit_id,
                        "sheet": edit.sheet,
                        "cell": edit.cell,
                        "evidence_ids": list(edit.evidence_ids),
                    }
                    for edit in candidate.edits
                ],
            }
        verdict = getattr(state, "falsifier_verdict", None)
        if verdict is not None:
            ledger["falsifier_verdict"] = {
                "status": verdict.status,
                "proposal_id": verdict.proposal_id,
                "experiment_ids": list(verdict.experiment_ids),
            }
        prefix = "\nController evidence ledger (registered handles; IDs may be cited directly): "

        def render(payload: dict[str, object]) -> str:
            return prefix + json.dumps(payload, sort_keys=True, separators=(",", ":"))

        rendered = render(ledger)
        if len(rendered) <= max_chars:
            return rendered

        # Bulky workbook previews are useful but reconstructible through their tools. Preserve
        # durable evidence handles and proposal state before spending context on those previews.
        ledger["workbook_observations"] = []
        rendered = render(ledger)
        if len(rendered) <= max_chars:
            return rendered

        citation_ids = [citation.citation_id for citation in selected_citations[-32:]]
        experiment_ids = [evidence.experiment_id for evidence in experiments[-24:]]
        compact: dict[str, object] = {
            "citation_ids": citation_ids,
            "experiment_ids": experiment_ids,
            "candidate": ledger["candidate"],
            "falsifier_verdict": ledger["falsifier_verdict"],
            "details_compacted": True,
        }
        rendered = render(compact)
        while len(rendered) > max_chars:
            if len(citation_ids) >= len(experiment_ids) and citation_ids:
                citation_ids.pop(0)
            elif experiment_ids:
                experiment_ids.pop(0)
            else:
                break
            rendered = render(compact)
        return rendered if len(rendered) <= max_chars else ""

    def _bounded_observation_ledger(self, *, max_chars: int = 14_000) -> list[dict[str, object]]:
        """Retain the newest useful reads without letting the compacting ledger overflow context."""

        selected: list[dict[str, object]] = []
        used = 2
        for entry in reversed(self._observation_ledger.values()):
            encoded = json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str)
            entry_size = len(encoded) + 1
            if selected and used + entry_size > max_chars:
                break
            if entry_size > max_chars:
                selected.append(
                    {
                        "tool": entry.get("tool"),
                        "arguments": entry.get("arguments"),
                        "result_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                        "result_preview": encoded[: max(0, max_chars - 512)],
                        "truncated": True,
                    }
                )
                break
            selected.append(entry)
            used += entry_size
        selected.reverse()
        return selected

    def _input_budget_requires_terminal(self, snapshot: AgentBudgetSnapshot) -> bool:
        """Reserve a final action before the next growing context would consume the token budget."""

        if not self.terminal_tool_names or self._last_input_tokens is None:
            return False
        remaining = int(snapshot["input_token_limit"] or 0) - int(
            snapshot["input_tokens_used"] or 0
        )
        conservative_next_request = max(1, math.ceil(self._last_input_tokens * 1.5))
        return remaining <= conservative_next_request

    def _tool_budget_requires_terminal(self, snapshot: AgentBudgetSnapshot) -> bool:
        if not self.terminal_tool_names:
            return False
        remaining = int(snapshot["tool_call_limit"] or 0) - int(snapshot["tool_calls_used"] or 0)
        return remaining <= self.terminal_tool_call_reserve

    def _tool_budget_requires_coordination(self, snapshot: AgentBudgetSnapshot) -> bool:
        if not self.coordination_tool_names:
            return False
        remaining = int(snapshot["tool_call_limit"] or 0) - int(snapshot["tool_calls_used"] or 0)
        state = getattr(self.registry, "state", None)
        actor_experiments = [
            evidence
            for evidence in getattr(state, "experiments", {}).values()
            if getattr(evidence, "actor", None) == self.actor
        ]
        if self.evidence_aware_coordination:
            has_experiment = bool(actor_experiments)
            if self.actor == "audit-manager":
                actor_turn_limit = int(snapshot["manager_turn_limit"] or 0)
                minimum_turn_reserve = 12
            else:
                actor_turn_limit = int(snapshot["falsifier_turn_limit"] or 0)
                minimum_turn_reserve = 6
            evidence_turn_reserve = max(
                minimum_turn_reserve,
                math.ceil(actor_turn_limit * 0.6),
            )
            if has_experiment and self._turns_remaining(snapshot) <= evidence_turn_reserve:
                return True
        if (
            self.evidence_aware_coordination
            and self.actor == "audit-manager"
            and (
                getattr(state, "candidate", None) is not None
                or getattr(state, "falsifier_verdict", None) is not None
            )
        ):
            return True
        if remaining > self.coordination_tool_call_reserve:
            return False
        if not self.evidence_aware_coordination:
            return True
        has_experiment = bool(actor_experiments)
        has_candidate = getattr(state, "candidate", None) is not None
        if has_experiment or has_candidate:
            return True
        return remaining <= self.terminal_tool_call_reserve + 2

    def _experiment_required(self, snapshot: AgentBudgetSnapshot) -> bool:
        self._exception_scope_mode = self._exception_scope_experiment_required(snapshot)
        if self._exception_scope_mode:
            return True
        threshold = self.require_experiment_after_turns
        if threshold is None or self._experiment_attempt_limit_reached():
            return False
        state = getattr(self.registry, "state", None)
        if state is None:
            return False
        candidate = getattr(state, "candidate", None)
        if self.actor == "audit-manager" and candidate is not None:
            return False
        if self.actor == "falsifier" and candidate is None:
            return False
        actor_experiments = [
            evidence
            for evidence in getattr(state, "experiments", {}).values()
            if getattr(evidence, "actor", None) == self.actor
        ]
        if actor_experiments:
            return False
        citations = getattr(state, "citations", {})
        if not citations:
            return False
        if self.actor == "audit-manager":
            turns_used = int(snapshot["manager_turns_used"] or 0)
        else:
            turns_used = int(snapshot["falsifier_turns_used"] or 0)
        return turns_used >= threshold

    def _exception_scope_experiment_required(self, snapshot: AgentBudgetSnapshot) -> bool:
        """Require one cross-product test when registered policy evidence contains an exception."""

        if self.actor != "audit-manager":
            return False
        state = getattr(self.registry, "state", None)
        if state is None or getattr(state, "candidate", None) is not None:
            return False
        citations = getattr(state, "citations", {}).values()
        policy_text = " ".join(str(getattr(item, "exact_quote", "")) for item in citations).lower()
        if not any(term in policy_text for term in ("waiver", "exception", "unless")):
            return False
        manager_experiments = [
            evidence
            for evidence in getattr(state, "experiments", {}).values()
            if getattr(evidence, "actor", None) == "audit-manager"
        ]
        for evidence in manager_experiments:
            request = getattr(evidence, "request", {})
            description = (
                str(request.get("purpose", ""))
                + " "
                + json.dumps(request.get("overrides", {}), sort_keys=True, default=str)
            ).lower()
            exception_covered = any(
                term in description for term in ("waiver", "exception", "unless")
            )
            explicitly_disabled = any(
                term in description for term in ("without waiver", "no waiver", "unwaived", '"n"')
            )
            ordinary_dimension_covered = any(
                term in description
                for term in (
                    "ordinary",
                    "delivery",
                    "quality",
                    "penalty",
                    "violation",
                    "breach",
                    "scope",
                    "cross-product",
                )
            )
            if exception_covered and ordinary_dimension_covered and not explicitly_disabled:
                return False
        attempts = self._tool_attempt_counts.get("run_experiment", 0)
        turns_used = int(snapshot["manager_turns_used"] or 0)
        threshold = self.require_experiment_after_turns or 1
        return attempts >= 3 and turns_used >= threshold

    def _cache_key(self, call: ToolCall) -> str | None:
        key_builder = getattr(self.registry, "cache_key", None)
        if not callable(key_builder):
            return None
        key = key_builder(call)
        return key if isinstance(key, str) else None

    def _register_observation(
        self,
        key: str,
        call: ToolCall,
        envelope: ToolEnvelope,
    ) -> None:
        result = envelope.result
        summary: object = result
        if call.name == "read_region" and isinstance(result, list):
            meaningful = [
                item
                for item in result
                if isinstance(item, dict)
                and (item.get("formula") is not None or item.get("value") is not None)
            ]
            summary = meaningful[:80]
        entry: dict[str, object] = {
            "tool": call.name,
            "arguments": call.arguments,
            "result": summary,
        }
        encoded = json.dumps(entry, sort_keys=True, default=str)
        if len(encoded) > 12_000:
            entry = {
                "tool": call.name,
                "arguments": call.arguments,
                "result_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                "result_preview": encoded[:10_000],
                "truncated": True,
            }
        self._observation_ledger[key] = entry

    def _request_context_limit(
        self,
        snapshot: AgentBudgetSnapshot,
        *,
        final_turn: bool,
    ) -> int:
        if not final_turn:
            return self.max_context_chars
        input_tokens_remaining = int(snapshot["input_token_limit"] or 0) - int(
            snapshot["input_tokens_used"] or 0
        )
        # Tool JSON is token-dense. A 1.25 chars/token ceiling is deliberately conservative
        # compared with live provider traces while preserving the base prompt and latest group.
        return min(
            self.max_context_chars,
            max(10_000, math.floor(max(0, input_tokens_remaining) * 1.25)),
        )

    def _turns_remaining(self, snapshot: AgentBudgetSnapshot) -> int:
        if self.actor == "audit-manager":
            used = int(snapshot["manager_turns_used"] or 0)
            limit = int(snapshot["manager_turn_limit"] or 0)
        else:
            used = int(snapshot["falsifier_turns_used"] or 0)
            limit = int(snapshot["falsifier_turn_limit"] or 0)
        model_calls_remaining = int(snapshot["model_call_limit"] or 0) - int(
            snapshot["model_calls_used"] or 0
        )
        tool_calls_remaining = int(snapshot["tool_call_limit"] or 0) - int(
            snapshot["tool_calls_used"] or 0
        )
        return min(limit - used, model_calls_remaining, tool_calls_remaining)

    def _preflight_turn(self) -> None:
        self.budget.ensure_within_limits()
        snapshot = self.budget.snapshot()
        if self.actor == "audit-manager":
            turns_used = snapshot["manager_turns_used"]
            turn_limit = snapshot["manager_turn_limit"]
            resource = "manager_turns"
        else:
            turns_used = snapshot["falsifier_turns_used"]
            turn_limit = snapshot["falsifier_turn_limit"]
            resource = "falsifier_turns"
        if turns_used >= turn_limit:
            raise AgentBudgetExceeded(
                resource,
                float(turns_used + 1),
                float(turn_limit),
            )
        if snapshot["model_calls_used"] >= snapshot["model_call_limit"]:
            raise AgentBudgetExceeded(
                "model_calls",
                float(snapshot["model_calls_used"] + 1),
                float(snapshot["model_call_limit"]),
            )
        if snapshot["input_tokens_used"] >= snapshot["input_token_limit"]:
            raise AgentBudgetExceeded(
                "input_tokens",
                float(snapshot["input_tokens_used"] + 1),
                float(snapshot["input_token_limit"]),
            )
        if snapshot["output_tokens_used"] >= snapshot["output_token_limit"]:
            raise AgentBudgetExceeded(
                "output_tokens",
                float(snapshot["output_tokens_used"] + 1),
                float(snapshot["output_token_limit"]),
            )
