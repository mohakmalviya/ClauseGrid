"""Fail-closed runtime budgets for model-directed audit agents.

This ledger is deliberately separate from :mod:`formulawitness.budget`, whose
contract is used by the legacy deterministic comparison.  All mutations first
validate every affected limit and only then commit the usage update.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from threading import Lock
from typing import Literal, TypedDict

AgentActor = Literal["manager", "falsifier"]


class AgentBudgetSnapshot(TypedDict):
    """JSON-serializable point-in-time view of limits and usage."""

    manager_turn_limit: int
    falsifier_turn_limit: int
    model_call_limit: int
    tool_call_limit: int
    input_token_limit: int
    output_token_limit: int
    workbook_execution_limit: int
    retry_limit: int
    elapsed_time_limit_seconds: float
    reported_cost_limit_usd: float | None
    manager_turns_used: int
    falsifier_turns_used: int
    model_calls_used: int
    tool_calls_used: int
    input_tokens_used: int
    output_tokens_used: int
    workbook_executions_used: int
    retries_used: int
    elapsed_time_seconds: float
    reported_cost_usd: float | None


@dataclass(frozen=True)
class AgentRuntimeLimits:
    """Hard limits for one complete manager/falsifier run.

    ``reported_cost_limit_usd`` constrains only costs actually reported by the
    caller.  It is optional because some model providers do not return cost
    data.  Token limits remain authoritative when cost is unavailable.
    """

    manager_turn_limit: int
    falsifier_turn_limit: int
    model_call_limit: int
    tool_call_limit: int
    input_token_limit: int
    output_token_limit: int
    workbook_execution_limit: int
    retry_limit: int
    elapsed_time_limit_seconds: float
    reported_cost_limit_usd: float | None = None

    def __post_init__(self) -> None:
        integer_limits = (
            ("manager_turn_limit", self.manager_turn_limit),
            ("falsifier_turn_limit", self.falsifier_turn_limit),
            ("model_call_limit", self.model_call_limit),
            ("tool_call_limit", self.tool_call_limit),
            ("input_token_limit", self.input_token_limit),
            ("output_token_limit", self.output_token_limit),
            ("workbook_execution_limit", self.workbook_execution_limit),
            ("retry_limit", self.retry_limit),
        )
        for name, value in integer_limits:
            _validate_non_negative_integer(name, value)
        _validate_non_negative_number("elapsed_time_limit_seconds", self.elapsed_time_limit_seconds)
        if self.reported_cost_limit_usd is not None:
            _validate_non_negative_number("reported_cost_limit_usd", self.reported_cost_limit_usd)


class AgentBudgetExceeded(RuntimeError):
    """Raised before a ledger mutation would exceed a configured limit."""

    def __init__(
        self,
        resource: str,
        attempted: float,
        limit: float,
    ) -> None:
        self.resource = resource
        self.attempted = attempted
        self.limit = limit
        super().__init__(f"Agent budget exceeded for {resource}: {attempted}>{limit}")


class AgentBudgetLedger:
    """Thread-safe, monotonic usage ledger for one agent runtime.

    A model response is recorded atomically with :meth:`record_model_call`.
    ``retries`` denotes additional physical model attempts, so a logical call
    with two retries consumes three model calls but one manager/falsifier turn.
    """

    def __init__(
        self,
        limits: AgentRuntimeLimits,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limits = limits
        self._clock = clock
        started_at = clock()
        if not math.isfinite(started_at):
            raise ValueError("clock must return a finite value")
        self._started_at = started_at
        self._last_clock = started_at
        self._lock = Lock()
        self._manager_turns = 0
        self._falsifier_turns = 0
        self._model_calls = 0
        self._tool_calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._workbook_executions = 0
        self._retries = 0
        self._reported_cost: Decimal | None = None

    def record_model_call(
        self,
        actor: AgentActor,
        *,
        input_tokens: int,
        output_tokens: int,
        retries: int = 0,
        reported_cost_usd: float | None = None,
    ) -> None:
        """Atomically charge a logical model turn and all physical attempts."""

        if actor not in ("manager", "falsifier"):
            raise ValueError(f"Unsupported agent actor: {actor}")
        _validate_non_negative_integer("input_tokens", input_tokens)
        _validate_non_negative_integer("output_tokens", output_tokens)
        _validate_non_negative_integer("retries", retries)
        cost_delta: Decimal | None = None
        if reported_cost_usd is not None:
            _validate_non_negative_number("reported_cost_usd", reported_cost_usd)
            cost_delta = Decimal(str(reported_cost_usd))

        with self._lock:
            elapsed = self._elapsed_unlocked()
            manager_turns = self._manager_turns + (1 if actor == "manager" else 0)
            falsifier_turns = self._falsifier_turns + (1 if actor == "falsifier" else 0)
            model_calls = self._model_calls + 1 + retries
            input_total = self._input_tokens + input_tokens
            output_total = self._output_tokens + output_tokens
            retry_total = self._retries + retries
            cost_total = self._reported_cost
            if cost_delta is not None:
                cost_total = (cost_total or Decimal(0)) + cost_delta

            checks: tuple[tuple[str, float, float], ...] = (
                ("elapsed_time_seconds", elapsed, self.limits.elapsed_time_limit_seconds),
                ("manager_turns", manager_turns, self.limits.manager_turn_limit),
                ("falsifier_turns", falsifier_turns, self.limits.falsifier_turn_limit),
                ("model_calls", model_calls, self.limits.model_call_limit),
                ("input_tokens", input_total, self.limits.input_token_limit),
                ("output_tokens", output_total, self.limits.output_token_limit),
                ("retries", retry_total, self.limits.retry_limit),
            )
            _require_within_limits(checks)
            if cost_total is not None and self.limits.reported_cost_limit_usd is not None:
                cost_limit = Decimal(str(self.limits.reported_cost_limit_usd))
                if cost_total > cost_limit:
                    raise AgentBudgetExceeded(
                        "reported_cost_usd", float(cost_total), float(cost_limit)
                    )

            self._manager_turns = manager_turns
            self._falsifier_turns = falsifier_turns
            self._model_calls = model_calls
            self._input_tokens = input_total
            self._output_tokens = output_total
            self._retries = retry_total
            self._reported_cost = cost_total

    def charge_tool_calls(self, count: int = 1) -> None:
        """Charge deterministic tool dispatches before executing them."""

        _validate_non_negative_integer("count", count)
        with self._lock:
            elapsed = self._elapsed_unlocked()
            proposed = self._tool_calls + count
            _require_within_limits(
                (
                    (
                        "elapsed_time_seconds",
                        elapsed,
                        self.limits.elapsed_time_limit_seconds,
                    ),
                    ("tool_calls", proposed, self.limits.tool_call_limit),
                )
            )
            self._tool_calls = proposed

    def charge_workbook_executions(self, count: int = 1) -> None:
        """Charge sandboxed workbook executions before running them."""

        _validate_non_negative_integer("count", count)
        with self._lock:
            elapsed = self._elapsed_unlocked()
            proposed = self._workbook_executions + count
            _require_within_limits(
                (
                    (
                        "elapsed_time_seconds",
                        elapsed,
                        self.limits.elapsed_time_limit_seconds,
                    ),
                    (
                        "workbook_executions",
                        proposed,
                        self.limits.workbook_execution_limit,
                    ),
                )
            )
            self._workbook_executions = proposed

    def charge_retries(self, count: int = 1) -> None:
        """Charge non-model retries; model retries belong in ``record_model_call``."""

        _validate_non_negative_integer("count", count)
        with self._lock:
            elapsed = self._elapsed_unlocked()
            proposed = self._retries + count
            _require_within_limits(
                (
                    (
                        "elapsed_time_seconds",
                        elapsed,
                        self.limits.elapsed_time_limit_seconds,
                    ),
                    ("retries", proposed, self.limits.retry_limit),
                )
            )
            self._retries = proposed

    def ensure_within_limits(self) -> None:
        """Fail if elapsed wall time has crossed its limit."""

        with self._lock:
            elapsed = self._elapsed_unlocked()
            _require_within_limits(
                (
                    (
                        "elapsed_time_seconds",
                        elapsed,
                        self.limits.elapsed_time_limit_seconds,
                    ),
                )
            )

    def snapshot(self) -> AgentBudgetSnapshot:
        """Return a detached dictionary accepted directly by ``json.dumps``."""

        with self._lock:
            elapsed = self._elapsed_unlocked()
            return {
                "manager_turn_limit": self.limits.manager_turn_limit,
                "falsifier_turn_limit": self.limits.falsifier_turn_limit,
                "model_call_limit": self.limits.model_call_limit,
                "tool_call_limit": self.limits.tool_call_limit,
                "input_token_limit": self.limits.input_token_limit,
                "output_token_limit": self.limits.output_token_limit,
                "workbook_execution_limit": self.limits.workbook_execution_limit,
                "retry_limit": self.limits.retry_limit,
                "elapsed_time_limit_seconds": self.limits.elapsed_time_limit_seconds,
                "reported_cost_limit_usd": self.limits.reported_cost_limit_usd,
                "manager_turns_used": self._manager_turns,
                "falsifier_turns_used": self._falsifier_turns,
                "model_calls_used": self._model_calls,
                "tool_calls_used": self._tool_calls,
                "input_tokens_used": self._input_tokens,
                "output_tokens_used": self._output_tokens,
                "workbook_executions_used": self._workbook_executions,
                "retries_used": self._retries,
                "elapsed_time_seconds": elapsed,
                "reported_cost_usd": (
                    float(self._reported_cost) if self._reported_cost is not None else None
                ),
            }

    def _elapsed_unlocked(self) -> float:
        now = self._clock()
        if not math.isfinite(now):
            raise RuntimeError("Budget clock returned a non-finite value")
        if now < self._last_clock:
            raise RuntimeError("Budget clock moved backwards")
        self._last_clock = now
        return now - self._started_at


def _validate_non_negative_integer(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _validate_non_negative_number(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _require_within_limits(
    checks: tuple[tuple[str, float, float], ...],
) -> None:
    for resource, attempted, limit in checks:
        if attempted > limit:
            raise AgentBudgetExceeded(resource, attempted, limit)
