"""Independent semantic oracle; it reads neither workbook formulas nor public rule code."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def evaluate_policy(inputs: dict[str, Any]) -> dict[str, Any]:
    gross = _decimal(inputs["gross_eligible_invoices"])
    returns = _decimal(inputs["returns_credits"])
    passthrough = _decimal(inputs["pass_through_charges"])
    on_time = _decimal(inputs["on_time_rate"])
    defect = _decimal(inputs["defect_rate"])
    incidents = int(inputs["critical_incidents"])
    waiver = str(inputs["critical_waiver"]).upper()
    period_start = date.fromisoformat(str(inputs["period_start"]))
    period_end = date.fromisoformat(str(inputs["period_end"]))
    contract_start = date.fromisoformat(str(inputs["contract_start"]))

    eligible = max(Decimal(0), gross - returns - passthrough)
    active_days = max(0, (period_end - max(period_start, contract_start)).days + 1)
    period_days = max(1, (period_end - period_start).days + 1)
    if eligible < Decimal(100000):
        tier = Decimal(0)
    elif eligible < Decimal(250000):
        tier = Decimal("0.02")
    elif eligible < Decimal(500000):
        tier = Decimal("0.03")
    else:
        tier = Decimal("0.04")
    gross_rebate = eligible * tier
    critical_excluded = incidents >= 1 and waiver != "Y"
    delivery_breach = on_time < Decimal("0.95")
    quality_breach = defect > Decimal("0.02")
    if critical_excluded:
        sla = Decimal(0)
    elif delivery_breach and quality_breach:
        sla = Decimal("0.60")
    elif delivery_breach or quality_breach:
        sla = Decimal("0.75")
    else:
        sla = Decimal(1)
    proration = min(Decimal(1), Decimal(active_days) / Decimal(period_days))
    adjusted = gross_rebate * sla * proration
    final = min(adjusted, Decimal(20000)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    decision = (
        "EXCLUDED_CRITICAL" if critical_excluded else ("NO_REBATE" if final == 0 else "PAYABLE")
    )
    return {
        "L6": float(eligible),
        "M6": active_days,
        "N6": float(tier),
        "O6": float(gross_rebate),
        "P6": float(sla),
        "Q6": float(proration),
        "R6": float(adjusted),
        "S6": float(final),
        "T6": decision,
    }
