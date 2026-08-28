"""Public benchmark inputs available to both compared repair workflows."""

from __future__ import annotations

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
    return TestCase(case_id, category, {**DEFAULT_INPUTS, **updates}, rules)


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
                f"V{index + 5:02d}",
                "proration_full_period",
                ("RB-204", "RB-205"),
                contract_start="2026-01-01",
            ),
            _case(
                f"V{index + 6:02d}",
                "proration_89_of_90_days",
                ("RB-204", "RB-205"),
                contract_start="2026-01-02",
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


WORKBOOK_CASES = {
    **{f"M{i:02d}": f"workbooks/mutants/M{i:02d}_supplier_rebate.xlsx" for i in range(1, 13)},
    "H01": "workbooks/hard/H01_supplier_rebate.xlsx",
    "C01": "workbooks/controls/C01_supplier_rebate.xlsx",
    "C02": "workbooks/controls/C02_supplier_rebate.xlsx",
    "C03": "workbooks/controls/C03_supplier_rebate.xlsx",
}

MAX_PATCH_CELLS = {
    **{f"M{i:02d}": 1 for i in range(1, 13)},
    "H01": 3,
    "C01": 0,
    "C02": 0,
    "C03": 0,
}

DEFECT_FAMILIES = {
    "M01": "eligible-spend returns deduction",
    "M02": "eligible-spend pass-through deduction",
    "M03": "ordered tier lookup: first lower-bound selection",
    "M04": "ordered tier lookup: second lower-bound selection",
    "M05": "ordered tier lookup: third lower-bound selection",
    "M06": "delivery threshold boundary",
    "M07": "quality threshold boundary",
    "M08": "critical-incident precedence",
    "M09": "combined SLA penalty value",
    "M10": "waiver exception scope",
    "M11": "contract-effective proportional-proration denominator",
    "M12": "cap and multiplier order",
    "H01": "tier lookup + waiver scope + cap order interaction",
    "C01": "clean ordinary control",
    "C02": "clean boundary control",
    "C03": "clean waiver control",
}
