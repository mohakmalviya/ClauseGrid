from pathlib import Path

from evals.sealed.oracle import evaluate_policy
from formulawitness.formula import evaluate_cells, excel_serial
from formulawitness.ooxml import calculation_cells
from formulawitness.policy import (
    CORE_OUTPUTS,
    INPUT_CELL_MAP,
    compile_rule_formulas,
    evaluate_approved_rules,
    extract_rules,
)
from formulawitness.public_benchmark import DEFAULT_INPUTS

ROOT = Path(__file__).resolve().parents[2]


def test_policy_compiler_agrees_with_independent_oracle() -> None:
    raw = {
        INPUT_CELL_MAP[name]: excel_serial(value)
        if name in {"period_start", "period_end", "contract_start"}
        else value
        for name, value in DEFAULT_INPUTS.items()
        if name in INPUT_CELL_MAP
    }
    rules = extract_rules(ROOT / "policies/supplier_rebate_sla_policy.pdf")
    lookup_values = {
        "TIERSCHEDULE!A5": 0,
        "TIERSCHEDULE!A6": 100000,
        "TIERSCHEDULE!A7": 250000,
        "TIERSCHEDULE!A8": 500000,
        "TIERSCHEDULE!B5": 0,
        "TIERSCHEDULE!B6": 0.02,
        "TIERSCHEDULE!B7": 0.03,
        "TIERSCHEDULE!B8": 0.04,
    }
    actual, _ = evaluate_cells({**raw, **lookup_values}, compile_rule_formulas(rules))
    expected = evaluate_policy(DEFAULT_INPUTS)
    assert {cell: actual[cell] for cell in CORE_OUTPUTS} == expected


def test_formula_engine_matches_pristine_cached_scenario() -> None:
    workbook = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    values, formulas = calculation_cells(workbook)
    actual, dependencies = evaluate_cells(values, formulas)
    assert actual["S6"] == 7500
    assert actual["T6"] == "PAYABLE"
    assert dependencies["S6"] == ["R6"]


def test_policy_compiler_matches_oracle_for_partial_period_proration() -> None:
    inputs = {**DEFAULT_INPUTS, "contract_start": "2026-01-02"}
    rules = extract_rules(ROOT / "policies/supplier_rebate_sla_policy.pdf")
    assert evaluate_approved_rules(inputs, rules) == evaluate_policy(inputs)


def test_excel_round_is_half_away_from_zero_for_benchmark_values() -> None:
    values = {"A1": 2.675}
    actual, _ = evaluate_cells(values, {"B1": "=ROUND(A1,2)"})
    assert actual["B1"] == 2.68


def test_ordered_lookup_reads_qualified_range() -> None:
    values = {
        "A1": 250000,
        "TIERSCHEDULE!A5": 0,
        "TIERSCHEDULE!A6": 100000,
        "TIERSCHEDULE!A7": 250000,
        "TIERSCHEDULE!A8": 500000,
        "TIERSCHEDULE!B5": 0,
        "TIERSCHEDULE!B6": 0.02,
        "TIERSCHEDULE!B7": 0.03,
        "TIERSCHEDULE!B8": 0.04,
    }
    actual, dependencies = evaluate_cells(
        values,
        {"B1": "=LOOKUP(A1,TierSchedule!A5:A8,TierSchedule!B5:B8)"},
    )
    assert actual["B1"] == 0.03
    assert dependencies["B1"] == [
        "A1",
        "TIERSCHEDULE!A5",
        "TIERSCHEDULE!A6",
        "TIERSCHEDULE!A7",
        "TIERSCHEDULE!A8",
        "TIERSCHEDULE!B5",
        "TIERSCHEDULE!B6",
        "TIERSCHEDULE!B7",
        "TIERSCHEDULE!B8",
    ]


def test_iso_date_overrides_are_policy_neutral_and_not_address_specific() -> None:
    outputs, _ = evaluate_cells(
        {},
        {"Z17": "=Y11-X23"},
        {"X23": "2026-01-01", "Y11": "2026-01-03"},
    )

    assert outputs["Z17"] == 2
