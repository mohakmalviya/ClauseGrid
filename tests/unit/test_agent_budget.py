import json

import pytest

from formulawitness.agent_budget import (
    AgentBudgetExceeded,
    AgentBudgetLedger,
    AgentRuntimeLimits,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def limits(**overrides: object) -> AgentRuntimeLimits:
    values: dict[str, object] = {
        "manager_turn_limit": 3,
        "falsifier_turn_limit": 2,
        "model_call_limit": 8,
        "tool_call_limit": 10,
        "input_token_limit": 1_000,
        "output_token_limit": 500,
        "workbook_execution_limit": 6,
        "retry_limit": 3,
        "elapsed_time_limit_seconds": 30.0,
        "reported_cost_limit_usd": None,
    }
    values.update(overrides)
    return AgentRuntimeLimits(**values)  # type: ignore[arg-type]


def test_model_call_charges_turn_attempts_tokens_retries_and_cost_atomically() -> None:
    ledger = AgentBudgetLedger(limits(reported_cost_limit_usd=0.3))

    ledger.record_model_call(
        "manager",
        input_tokens=100,
        output_tokens=20,
        retries=1,
        reported_cost_usd=0.1,
    )
    ledger.record_model_call(
        "falsifier",
        input_tokens=70,
        output_tokens=10,
        reported_cost_usd=0.2,
    )

    snapshot = ledger.snapshot()
    assert snapshot["manager_turns_used"] == 1
    assert snapshot["falsifier_turns_used"] == 1
    assert snapshot["model_calls_used"] == 3
    assert snapshot["input_tokens_used"] == 170
    assert snapshot["output_tokens_used"] == 30
    assert snapshot["retries_used"] == 1
    assert snapshot["reported_cost_usd"] == pytest.approx(0.3)


def test_failed_model_charge_changes_no_counter() -> None:
    ledger = AgentBudgetLedger(limits(output_token_limit=5))
    before = ledger.snapshot()

    with pytest.raises(AgentBudgetExceeded) as error:
        ledger.record_model_call("manager", input_tokens=3, output_tokens=6, retries=1)

    assert error.value.resource == "output_tokens"
    after = ledger.snapshot()
    for field in (
        "manager_turns_used",
        "model_calls_used",
        "input_tokens_used",
        "output_tokens_used",
        "retries_used",
    ):
        assert after[field] == before[field]


def test_exact_limit_is_allowed_and_next_charge_fails_closed() -> None:
    ledger = AgentBudgetLedger(limits(tool_call_limit=2, workbook_execution_limit=2, retry_limit=1))
    ledger.charge_tool_calls(2)
    ledger.charge_workbook_executions(2)
    ledger.charge_retries()

    with pytest.raises(AgentBudgetExceeded, match="tool_calls"):
        ledger.charge_tool_calls()
    with pytest.raises(AgentBudgetExceeded, match="workbook_executions"):
        ledger.charge_workbook_executions()
    with pytest.raises(AgentBudgetExceeded, match="retries"):
        ledger.charge_retries()

    snapshot = ledger.snapshot()
    assert snapshot["tool_calls_used"] == 2
    assert snapshot["workbook_executions_used"] == 2
    assert snapshot["retries_used"] == 1


def test_elapsed_time_is_checked_before_mutation() -> None:
    clock = FakeClock()
    ledger = AgentBudgetLedger(limits(elapsed_time_limit_seconds=5.0), clock=clock)
    clock.now += 5.0
    ledger.charge_tool_calls()
    clock.now += 0.001

    with pytest.raises(AgentBudgetExceeded) as error:
        ledger.charge_tool_calls()

    assert error.value.resource == "elapsed_time_seconds"
    assert ledger.snapshot()["tool_calls_used"] == 1


def test_snapshot_is_detached_and_json_serializable() -> None:
    ledger = AgentBudgetLedger(limits())
    ledger.record_model_call("manager", input_tokens=4, output_tokens=2)
    snapshot = ledger.snapshot()

    encoded = json.dumps(snapshot, sort_keys=True)
    snapshot["manager_turns_used"] = 99

    assert '"reported_cost_usd": null' in encoded
    assert ledger.snapshot()["manager_turns_used"] == 1


@pytest.mark.parametrize(
    ("field", "value", "exception"),
    [
        ("manager_turn_limit", -1, ValueError),
        ("tool_call_limit", True, TypeError),
        ("elapsed_time_limit_seconds", float("inf"), ValueError),
        ("reported_cost_limit_usd", -0.01, ValueError),
    ],
)
def test_invalid_limits_are_rejected(
    field: str,
    value: float | bool,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        limits(**{field: value})


def test_cost_limit_failure_is_atomic() -> None:
    ledger = AgentBudgetLedger(limits(reported_cost_limit_usd=0.1))

    with pytest.raises(AgentBudgetExceeded, match="reported_cost_usd"):
        ledger.record_model_call(
            "manager", input_tokens=10, output_tokens=5, reported_cost_usd=0.11
        )

    snapshot = ledger.snapshot()
    assert snapshot["manager_turns_used"] == 0
    assert snapshot["model_calls_used"] == 0
    assert snapshot["reported_cost_usd"] is None


def test_invalid_deltas_and_clock_regression_fail_closed() -> None:
    clock = FakeClock()
    ledger = AgentBudgetLedger(limits(), clock=clock)

    with pytest.raises(ValueError, match="non-negative"):
        ledger.charge_tool_calls(-1)
    with pytest.raises(ValueError, match="Unsupported agent actor"):
        ledger.record_model_call(  # type: ignore[arg-type]
            "reviewer", input_tokens=0, output_tokens=0
        )
    clock.now -= 1.0
    with pytest.raises(RuntimeError, match="moved backwards"):
        ledger.ensure_within_limits()

    clock.now = 100.0
    assert ledger.snapshot()["tool_calls_used"] == 0
