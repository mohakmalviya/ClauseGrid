from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.sealed.oracle import evaluate_policy
from formulawitness.agent_state import CandidateEdit
from formulawitness.formula import (
    FormulaError,
    evaluate_cells,
    excel_serial,
    referenced_cells,
    transform_formula,
    validate_formula_dependency_graph,
    validate_formula_subset,
)
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
        {"X23": 45_000, "Y11": 45_000},
        {"Z17": "=Y11-X23"},
        {
            "X23": {"kind": "date", "value": "2026-01-01"},
            "Y11": {"kind": "date", "value": "2026-01-03"},
        },
    )

    assert outputs["Z17"] == 2


def test_iso_shaped_text_override_preserves_an_existing_text_cell_type() -> None:
    outputs, _ = evaluate_cells(
        {"A1": "2026-01-01"},
        {"B1": '=A1="2026-01-01"'},
        {"A1": "2026-01-01"},
    )

    assert outputs["B1"] is True


def test_iso_shaped_text_override_remains_text_over_an_existing_numeric_cell() -> None:
    outputs, _ = evaluate_cells(
        {"A1": 1},
        {"B1": '=A1="2026-01-01"'},
        {"A1": "2026-01-01"},
    )

    assert outputs["B1"] is True


def test_tagged_date_override_rejects_an_invalid_calendar_date() -> None:
    with pytest.raises(FormulaError, match="valid calendar date"):
        evaluate_cells(
            {"A1": 1},
            {"B1": "=A1"},
            {"A1": {"kind": "date", "value": "2026-02-30"}},
        )


def test_structural_formula_transform_unwraps_hash_guardable_outer_if() -> None:
    source = '=IF(K6="Y",1,IF(AND(J6>=1,K6<>"Y"),0,IF(H6<0.95,0.75,1)))'

    transformed = transform_formula(source, "unwrap_outer_if_else")
    values = {"H6": 0.9, "J6": 1, "K6": "Y"}
    actual, _ = evaluate_cells(values, {"P6": transformed})

    assert transformed.startswith("=IF(AND(")
    assert 'K6<>"Y"' in transformed
    assert actual["P6"] == 0.75


def test_formula_profile_rejects_unsupported_functions_before_execution() -> None:
    with pytest.raises(FormulaError, match="Unsupported function SUM"):
        validate_formula_subset("=SUM(A1:A10)")


def test_formula_range_expansion_is_bounded_to_prevent_memory_amplification() -> None:
    with pytest.raises(FormulaError, match="10000-cell safety limit"):
        referenced_cells("=LOOKUP(A1,A1:XFD1048576,B1:XFD1048576)")


def test_formula_references_must_fit_inside_the_excel_grid() -> None:
    with pytest.raises(FormulaError, match="Excel worksheet grid"):
        validate_formula_subset("=A1048577+1")


def test_countif_supports_bounded_equality_checks_used_by_control_sheets() -> None:
    values = {"A1": "PASS", "A2": "FAIL", "A3": "fail"}

    actual, _ = evaluate_cells(values, {"B1": '=COUNTIF(A1:A3,"FAIL")'})

    assert actual["B1"] == 2


@pytest.mark.parametrize(
    "formula,error",
    [
        ("=MAX(A1:A2)", "scalar arguments"),
        ("=AND(A1:A2)", "scalar arguments"),
        ("=LOOKUP(A1,A2,B2)", "value and two ranges"),
        ('=COUNTIF(A1,"x")', "range and one equality criterion"),
        ('=COUNTIF(A1:A2,"*")', "literal equality criteria"),
        ('=COUNTIF(A1:A2,">0")', "literal equality criteria"),
        ("=A0+1", "Excel worksheet grid"),
        ("=LOOKUP(A1,A1:B2,C1:D2)", "one-dimensional ranges"),
    ],
)
def test_formula_profile_rejects_shapes_the_evaluator_cannot_execute(
    formula: str, error: str
) -> None:
    with pytest.raises(FormulaError, match=error):
        validate_formula_subset(formula)


def test_candidate_formulas_use_the_exact_executable_subset_validator() -> None:
    with pytest.raises(ValidationError, match="scalar arguments"):
        CandidateEdit(
            sheet="Sheet1",
            cell="B1",
            old_formula_sha256="a" * 64,
            new_formula="=AND(A1:A2)",
            rationale="This invalid range shape must fail before staging.",
            evidence_ids=("citation-000000000000",),
        )


def test_text_comparison_is_case_insensitive_like_excel() -> None:
    actual, _ = evaluate_cells({"A1": "YES"}, {"B1": '=IF(A1="yes",1,0)'})

    assert actual["B1"] == 1


def test_comparisons_do_not_coerce_text_and_numbers_to_the_same_type() -> None:
    actual, _ = evaluate_cells(
        {"C1": True},
        {
            "A1": '=1="1"',
            "A2": '=1<"1"',
            "A3": '=C1="TRUE"',
        },
    )

    assert actual == {"A1": False, "A2": True, "A3": False}


def test_blank_cells_follow_excel_equality_idioms() -> None:
    actual, _ = evaluate_cells(
        {},
        {
            "A1": '=B1=""',
            "A2": "=B1=0",
            "A3": '=B1="not blank"',
        },
    )

    assert actual == {"A1": True, "A2": True, "A3": False}


def test_countif_handles_blank_and_mixed_cells_without_false_failures() -> None:
    actual, _ = evaluate_cells({"A1": 0, "A3": "not numeric"}, {"B1": "=COUNTIF(A1:A3,0)"})

    assert actual["B1"] == 2


def test_formula_dependency_validation_rejects_chains_too_deep_to_execute_safely() -> None:
    formulas = {f"Sheet1!A{row}": f"=A{row + 1}" for row in range(1, 1_200)}
    formulas["Sheet1!A1200"] = "=1"

    with pytest.raises(FormulaError, match="dependency depth"):
        validate_formula_dependency_graph(formulas, ("Sheet1",))


def test_evaluator_uses_dependency_order_without_composing_python_recursion() -> None:
    formulas = {f"A{row}": f"=A{row + 1}" for row in range(1, 200)}
    formulas["A200"] = "=" + "+".join("1" for _ in range(601))
    qualified = {f"Sheet1!{cell}": formula for cell, formula in formulas.items()}

    validate_formula_dependency_graph(qualified, ("Sheet1",))
    outputs, _ = evaluate_cells({}, formulas)

    assert outputs["A1"] == 601


def test_explicit_active_sheet_references_use_live_formulas_and_overrides() -> None:
    outputs, dependencies = evaluate_cells(
        {"A1": 10, "SHEET1!A1": 10},
        {"A1": "=1", "B1": "=Sheet1!A1+1", "C1": "=Sheet1!D1+1"},
        {"D1": 20},
        active_sheet="Sheet1",
    )

    assert outputs["B1"] == 2
    assert outputs["C1"] == 21
    assert dependencies["B1"] == ["A1"]
    assert dependencies["C1"] == ["D1"]
