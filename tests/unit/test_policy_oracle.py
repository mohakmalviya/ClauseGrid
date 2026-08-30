from pathlib import Path

import pytest

from evals.sealed.oracle import evaluate_policy
from formulawitness.policy import compile_rule_ir, extract_rules
from formulawitness.policy_oracle import PolicyOracleError, evaluate_rule_ir
from formulawitness.public_benchmark import DEFAULT_INPUTS

ROOT = Path(__file__).resolve().parents[2]


def _operations():  # type: ignore[no-untyped-def]
    rules = extract_rules(ROOT / "policies/supplier_rebate_sla_policy.pdf")
    return compile_rule_ir(rules)


@pytest.mark.parametrize(
    "updates",
    [
        {},
        {"gross_eligible_invoices": 99_999.99},
        {"gross_eligible_invoices": 100_000},
        {"gross_eligible_invoices": 250_000},
        {"gross_eligible_invoices": 500_000},
        {"on_time_rate": 0.95, "defect_rate": 0.02},
        {"critical_incidents": 1, "critical_waiver": "N"},
        {
            "critical_incidents": 1,
            "critical_waiver": "Y",
            "on_time_rate": 0.94,
        },
        {"contract_start": "2026-01-02"},
        {"contract_start": "2026-04-01"},
    ],
)
def test_independent_rule_ir_oracle_matches_sealed_semantics(updates: dict[str, object]) -> None:
    inputs = {**DEFAULT_INPUTS, **updates}

    assert evaluate_rule_ir(inputs, _operations()) == evaluate_policy(inputs)


def test_policy_oracle_fails_closed_on_unknown_operation() -> None:
    operations = _operations()
    operations[0] = type(operations[0])(
        target=operations[0].target,
        operation="MODEL_FALLBACK",
        rule_ids=operations[0].rule_ids,
        parameters=operations[0].parameters,
    )

    with pytest.raises(PolicyOracleError, match="Unsupported approved policy operation"):
        evaluate_rule_ir(DEFAULT_INPUTS, operations)


def test_policy_oracle_rejects_missing_and_nonfinite_inputs() -> None:
    missing = dict(DEFAULT_INPUTS)
    missing.pop("gross_eligible_invoices")
    with pytest.raises(PolicyOracleError, match="Missing policy input"):
        evaluate_rule_ir(missing, _operations())

    invalid = {**DEFAULT_INPUTS, "gross_eligible_invoices": "NaN"}
    with pytest.raises(PolicyOracleError, match="must be finite"):
        evaluate_rule_ir(invalid, _operations())
