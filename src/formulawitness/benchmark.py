"""Frozen visible and held-out cases for SupplierRebate-SLA-16."""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from .models import TestCase

DEFAULT_INPUTS: dict[str, Any] = {
    "supplier_id": "SUP-1042",
    "period_start": "2026-01-01",
    "period_end": "2026-03-31",
    "contract_start": "2025-01-01",
    "gross_eligible_invoices": 250000,
    "returns_credits": 0,
    "pass_through_charges": 0,
    "on_time_rate": 0.98,
    "defect_rate": 0.01,
    "critical_incidents": 0,
    "critical_waiver": "N",
}


def _case(case_id: str, category: str, rules: tuple[str, ...], **updates: Any) -> TestCase:
    inputs = {**DEFAULT_INPUTS, **updates}
    return TestCase(case_id, category, inputs, rules)


def visible_cases() -> list[TestCase]:
    cases = [
        _case("V01", "ordinary", ("RB-101", "RB-102", "RB-103"), gross_eligible_invoices=180000),
        _case(
            "V02",
            "deduction_returns",
            ("RB-101",),
            gross_eligible_invoices=260000,
            returns_credits=15000,
        ),
        _case(
            "V03",
            "deduction_passthrough",
            ("RB-101",),
            gross_eligible_invoices=260000,
            pass_through_charges=15000,
        ),
    ]
    index = 4
    for threshold in (100000, 250000, 500000):
        for delta, label in ((-0.01, "below"), (0, "at"), (0.01, "above")):
            cases.append(
                _case(
                    f"V{index:02d}",
                    f"tier_{threshold}_{label}",
                    ("RB-102",),
                    gross_eligible_invoices=threshold + delta,
                )
            )
            index += 1
    cases.extend(
        [
            _case(f"V{index:02d}", "delivery_boundary", ("RB-202",), on_time_rate=0.95),
            _case(f"V{index + 1:02d}", "quality_boundary", ("RB-202",), defect_rate=0.02),
            _case(
                f"V{index + 2:02d}",
                "critical_precedence",
                ("RB-201",),
                critical_incidents=1,
                critical_waiver="N",
            ),
            _case(
                f"V{index + 3:02d}",
                "both_sla_breaches",
                ("RB-202",),
                on_time_rate=0.94,
                defect_rate=0.03,
            ),
            _case(
                f"V{index + 4:02d}",
                "waiver_scope",
                ("RB-203",),
                on_time_rate=0.94,
                defect_rate=0.01,
                critical_incidents=1,
                critical_waiver="Y",
            ),
            _case(
                f"V{index + 5:02d}", "tenure_90", ("RB-204", "RB-205"), contract_start="2026-01-01"
            ),
            _case(
                f"V{index + 6:02d}", "tenure_89", ("RB-204", "RB-205"), contract_start="2026-01-02"
            ),
            _case(
                f"V{index + 7:02d}",
                "cap_after_penalty",
                ("RB-301", "RB-302"),
                gross_eligible_invoices=600000,
                on_time_rate=0.94,
            ),
        ]
    )
    return cases


def held_out_cases(seed: int = 913_771) -> list[TestCase]:
    cases: list[TestCase] = []

    def add(category: str, rules: tuple[str, ...], **updates: Any) -> None:
        inputs = {**DEFAULT_INPUTS, **updates}
        cases.append(TestCase(f"H{len(cases) + 1:02d}", category, inputs, rules, "HELD_OUT"))

    for threshold in (100000, 250000, 500000):
        add("threshold_below", ("RB-102",), gross_eligible_invoices=threshold - 0.01)
        add("threshold_at", ("RB-102",), gross_eligible_invoices=threshold)
        add("threshold_above", ("RB-102",), gross_eligible_invoices=threshold + 0.01)
        add(
            "threshold_after_deduction",
            ("RB-101", "RB-102"),
            gross_eligible_invoices=threshold + 1000,
            returns_credits=1000,
        )
    for rate in (0.9499, 0.95, 0.9501):
        add("delivery_boundary", ("RB-202",), on_time_rate=rate)
    for rate in (0.0199, 0.02, 0.0201):
        add("quality_boundary", ("RB-202",), defect_rate=rate)
    add("sla_both", ("RB-202",), on_time_rate=0.93, defect_rate=0.04)
    add("sla_delivery", ("RB-202",), on_time_rate=0.93, defect_rate=0.01)
    add("sla_quality", ("RB-202",), on_time_rate=0.98, defect_rate=0.04)
    add("sla_neither", ("RB-202",), on_time_rate=0.98, defect_rate=0.01)
    add("critical_one", ("RB-201",), critical_incidents=1, critical_waiver="N")
    add(
        "critical_waived_delivery",
        ("RB-201", "RB-203"),
        critical_incidents=1,
        critical_waiver="Y",
        on_time_rate=0.93,
    )
    add("critical_two", ("RB-201",), critical_incidents=2, critical_waiver="N", defect_rate=0.04)
    add(
        "waiver_both",
        ("RB-203",),
        critical_incidents=2,
        critical_waiver="Y",
        on_time_rate=0.93,
        defect_rate=0.04,
    )
    period_end = date(2026, 3, 31)
    for days in (45, 89, 90, 91):
        start = period_end - timedelta(days=days - 1)
        add("tenure_boundary", ("RB-204", "RB-205"), contract_start=start.isoformat())
    add("returns_only", ("RB-101",), gross_eligible_invoices=310000, returns_credits=33000)
    add("passthrough_only", ("RB-101",), gross_eligible_invoices=310000, pass_through_charges=33000)
    add(
        "both_deductions",
        ("RB-101",),
        gross_eligible_invoices=310000,
        returns_credits=17000,
        pass_through_charges=19000,
    )
    add(
        "zero_floor",
        ("RB-101",),
        gross_eligible_invoices=10000,
        returns_credits=8000,
        pass_through_charges=7000,
    )
    rng = random.Random(seed)
    for _ in range(8):
        gross = rng.randint(110_000, 640_000) + rng.choice((0.13, 0.37, 0.79))
        returns = rng.randint(0, 12_000)
        passthrough = rng.randint(0, 12_000)
        add(
            "seeded_interior",
            ("RB-101", "RB-102", "RB-202", "RB-205", "RB-302"),
            gross_eligible_invoices=gross,
            returns_credits=returns,
            pass_through_charges=passthrough,
            on_time_rate=rng.choice((0.931, 0.971)),
            defect_rate=rng.choice((0.011, 0.031)),
            critical_incidents=rng.choice((0, 0, 1)),
            critical_waiver=rng.choice(("N", "Y")),
        )
    add("cap_clean", ("RB-302",), gross_eligible_invoices=650000)
    add("cap_delivery", ("RB-301", "RB-302"), gross_eligible_invoices=650000, on_time_rate=0.93)
    add(
        "cap_both",
        ("RB-301", "RB-302"),
        gross_eligible_invoices=650000,
        on_time_rate=0.93,
        defect_rate=0.04,
    )
    add(
        "cap_short_tenure",
        ("RB-205", "RB-302"),
        gross_eligible_invoices=900000,
        contract_start="2026-03-01",
    )
    add(
        "delivery_exact_with_quality",
        ("RB-202",),
        gross_eligible_invoices=510000,
        on_time_rate=0.95,
        defect_rate=0.04,
    )
    add(
        "quality_exact_with_delivery",
        ("RB-202",),
        gross_eligible_invoices=510000,
        on_time_rate=0.93,
        defect_rate=0.02,
    )
    assert len(cases) == 48, len(cases)
    return cases


WORKBOOK_CASES = {
    **{f"M{i:02d}": f"workbooks/mutants/M{i:02d}_supplier_rebate.xlsx" for i in range(1, 13)},
    "H01": "workbooks/hard/H01_supplier_rebate.xlsx",
    "C01": "workbooks/controls/C01_supplier_rebate.xlsx",
    "C02": "workbooks/controls/C02_supplier_rebate.xlsx",
    "C03": "workbooks/controls/C03_supplier_rebate.xlsx",
}


MAX_PATCH_CELLS = {**{f"M{i:02d}": 1 for i in range(1, 13)}, "H01": 3, "C01": 0, "C02": 0, "C03": 0}
