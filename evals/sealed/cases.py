"""Evaluator-only deterministic held-out vectors."""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from formulawitness.models import TestCase
from formulawitness.public_benchmark import DEFAULT_INPUTS


def held_out_cases(seed: int = 913_771) -> list[TestCase]:
    cases: list[TestCase] = []

    def add(category: str, rules: tuple[str, ...], **updates: Any) -> None:
        inputs = {**DEFAULT_INPUTS, **updates}
        cases.append(TestCase(f"H{len(cases) + 1:02d}", category, inputs, rules, "HELD_OUT"))

    for threshold in (100000, 250000, 500000):
        add(
            "lookup_near_below",
            ("RB-101", "RB-102"),
            gross_eligible_invoices=threshold + 1233.993,
            returns_credits=1234,
        )
        add(
            "lookup_near_above_a",
            ("RB-101", "RB-102"),
            gross_eligible_invoices=threshold + 1234.002,
            returns_credits=1234,
        )
        add(
            "lookup_near_above_b",
            ("RB-101", "RB-102"),
            gross_eligible_invoices=threshold + 1234.008,
            returns_credits=1234,
        )
        add(
            "threshold_after_deduction",
            ("RB-101", "RB-102"),
            gross_eligible_invoices=threshold + 1000,
            returns_credits=1000,
        )
    for offset, rate in enumerate((0.9499, 0.95, 0.9501)):
        add(
            "delivery_boundary",
            ("RB-202",),
            gross_eligible_invoices=331000 + offset,
            on_time_rate=rate,
        )
    for offset, rate in enumerate((0.0199, 0.02, 0.0201)):
        add(
            "quality_boundary",
            ("RB-202",),
            gross_eligible_invoices=341000 + offset,
            defect_rate=rate,
        )
    add("sla_both", ("RB-202",), on_time_rate=0.93, defect_rate=0.04)
    add("sla_delivery", ("RB-202",), on_time_rate=0.93, defect_rate=0.01)
    add("sla_quality", ("RB-202",), on_time_rate=0.98, defect_rate=0.04)
    add(
        "sla_neither",
        ("RB-202",),
        gross_eligible_invoices=252345.67,
        on_time_rate=0.98,
        defect_rate=0.01,
    )
    add(
        "critical_one",
        ("RB-201",),
        gross_eligible_invoices=261111,
        critical_incidents=1,
        critical_waiver="N",
    )
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
    for offset, days in enumerate((45, 89, 90, 91)):
        start = period_end - timedelta(days=days - 1)
        add(
            "effective_date_proration",
            ("RB-204", "RB-205"),
            gross_eligible_invoices=271000 + offset,
            contract_start=start.isoformat(),
        )
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
        add(
            "seeded_interior",
            ("RB-101", "RB-102", "RB-202", "RB-205", "RB-302"),
            gross_eligible_invoices=rng.randint(110_000, 640_000) + rng.choice((0.13, 0.37, 0.79)),
            returns_credits=rng.randint(0, 12_000),
            pass_through_charges=rng.randint(0, 12_000),
            on_time_rate=rng.choice((0.931, 0.971)),
            defect_rate=rng.choice((0.011, 0.031)),
            critical_incidents=rng.choice((0, 0, 1)),
            critical_waiver=rng.choice(("N", "Y")),
        )
    add("cap_clean", ("RB-302",), gross_eligible_invoices=650000)
    add(
        "cap_delivery",
        ("RB-301", "RB-302"),
        gross_eligible_invoices=650000,
        on_time_rate=0.93,
    )
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
