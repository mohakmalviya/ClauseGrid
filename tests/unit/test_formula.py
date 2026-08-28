from pathlib import Path

from formulawitness.benchmark import DEFAULT_INPUTS
from formulawitness.formula import evaluate_cells, excel_serial
from formulawitness.ooxml import sheet_cells
from formulawitness.oracle import evaluate_policy
from formulawitness.policy import CORE_OUTPUTS, INPUT_CELL_MAP, compile_rule_formulas

ROOT = Path(__file__).resolve().parents[2]


def test_policy_compiler_agrees_with_independent_oracle() -> None:
    raw = {
        INPUT_CELL_MAP[name]: excel_serial(value)
        if name in {"period_start", "period_end", "contract_start"}
        else value
        for name, value in DEFAULT_INPUTS.items()
        if name in INPUT_CELL_MAP
    }
    actual, _ = evaluate_cells(raw, compile_rule_formulas())
    expected = evaluate_policy(DEFAULT_INPUTS)
    assert {cell: actual[cell] for cell in CORE_OUTPUTS} == expected


def test_formula_engine_matches_pristine_cached_scenario() -> None:
    workbook = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    values, formulas = sheet_cells(workbook, "RebateCalc")
    actual, dependencies = evaluate_cells(values, formulas)
    assert actual["S6"] == 7500
    assert actual["T6"] == "PAYABLE"
    assert dependencies["S6"] == ["R6"]


def test_excel_round_is_half_away_from_zero_for_benchmark_values() -> None:
    values = {"A1": 2.675}
    actual, _ = evaluate_cells(values, {"B1": "=ROUND(A1,2)"})
    assert actual["B1"] == 2.68
