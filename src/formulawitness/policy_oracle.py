"""Independent deterministic execution of approved supplier-rebate rule IR.

The policy oracle deliberately does not import the spreadsheet formula parser or
evaluator.  The two sides of an assurance comparison therefore cannot agree only
because they share the same formula-engine defect.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, cast

from .models import RuleIR


class PolicyOracleError(ValueError):
    """Raised when approved rule IR or its semantic inputs cannot be evaluated."""


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool):
        raise PolicyOracleError(f"{label} must be numeric")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PolicyOracleError(f"{label} must be numeric") from exc
    if not number.is_finite():
        raise PolicyOracleError(f"{label} must be finite")
    return number


def _integer(value: Any, label: str) -> int:
    number = _decimal(value, label)
    integral = number.to_integral_value()
    if number != integral:
        raise PolicyOracleError(f"{label} must be an integer")
    return int(integral)


def _date(value: Any, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise PolicyOracleError(f"{label} must be an ISO calendar date") from exc


def _required(inputs: dict[str, Any], key: str) -> Any:
    if key not in inputs:
        raise PolicyOracleError(f"Missing policy input: {key}")
    return inputs[key]


def _parameters(item: RuleIR) -> dict[str, Any]:
    return cast(dict[str, Any], item.parameters)


def evaluate_rule_ir(inputs: dict[str, Any], operations: list[RuleIR]) -> dict[str, Any]:
    """Evaluate the approved IR directly with Decimal/date semantics.

    This interpreter intentionally supports only the closed operation set emitted
    by the controlled supplier-rebate compiler.  Unknown or malformed operations
    fail closed rather than falling back to a model or spreadsheet formula.
    """

    outputs: dict[str, Any] = {}
    critical_excluded: bool | None = None
    for item in operations:
        parameters = _parameters(item)
        if item.operation == "FLOORED_SUBTRACTION":
            gross = _decimal(_required(inputs, "gross_eligible_invoices"), "gross invoices")
            returns = _decimal(_required(inputs, "returns_credits"), "returns and credits")
            passthrough = _decimal(
                _required(inputs, "pass_through_charges"), "pass-through charges"
            )
            floor = _decimal(parameters.get("floor"), "eligible-spend floor")
            outputs[item.target] = max(floor, gross - returns - passthrough)
            continue

        if item.operation == "INCLUSIVE_ACTIVE_DAYS":
            period_start = _date(_required(inputs, "period_start"), "period start")
            period_end = _date(_required(inputs, "period_end"), "period end")
            contract_start = _date(_required(inputs, "contract_start"), "contract start")
            active_day_floor = _integer(parameters.get("floor"), "active-day floor")
            outputs[item.target] = max(
                active_day_floor,
                (period_end - max(period_start, contract_start)).days + 1,
            )
            continue

        if item.operation == "ORDERED_RANGE_LOOKUP":
            eligible = _decimal(outputs.get("L6"), "eligible spend")
            raw_bounds = parameters.get("lower_bounds")
            raw_rates = parameters.get("rates")
            if not isinstance(raw_bounds, list) or not isinstance(raw_rates, list):
                raise PolicyOracleError("Ordered lookup requires bound and rate arrays")
            if not raw_bounds or len(raw_bounds) != len(raw_rates):
                raise PolicyOracleError("Ordered lookup bounds and rates must have equal length")
            bounds = [_decimal(value, "tier lower bound") for value in raw_bounds]
            rates = [_decimal(value, "tier rate") for value in raw_rates]
            if bounds != sorted(set(bounds)):
                raise PolicyOracleError("Tier lower bounds must be unique and ordered")
            matches = [rate for bound, rate in zip(bounds, rates, strict=True) if eligible >= bound]
            if not matches:
                raise PolicyOracleError("Eligible spend is outside the approved tier domain")
            outputs[item.target] = matches[-1]
            continue

        if item.operation == "MULTIPLY":
            if "factors" in parameters:
                raw_factors = parameters["factors"]
                if not isinstance(raw_factors, list) or not raw_factors:
                    raise PolicyOracleError("Multiply factors must be a non-empty array")
                factors = [_decimal(outputs.get(str(key)), f"factor {key}") for key in raw_factors]
            else:
                factors = [
                    _decimal(outputs.get(str(parameters.get("left"))), "left factor"),
                    _decimal(outputs.get(str(parameters.get("right"))), "right factor"),
                ]
            result = Decimal(1)
            for factor in factors:
                result *= factor
            outputs[item.target] = result
            continue

        if item.operation == "CRITICAL_THEN_SLA":
            incidents = _integer(_required(inputs, "critical_incidents"), "critical incidents")
            waiver = str(_required(inputs, "critical_waiver")).strip().upper()
            on_time = _decimal(_required(inputs, "on_time_rate"), "on-time rate")
            defect = _decimal(_required(inputs, "defect_rate"), "defect rate")
            incident_threshold = _integer(
                parameters.get("incident_threshold"), "incident threshold"
            )
            waiver_code = str(parameters.get("waiver_code", "")).upper()
            critical_excluded = incidents >= incident_threshold and waiver != waiver_code
            delivery_breach = on_time < _decimal(
                parameters.get("delivery_threshold"), "delivery threshold"
            )
            quality_breach = defect > _decimal(
                parameters.get("quality_threshold"), "quality threshold"
            )
            if critical_excluded:
                multiplier = Decimal(0)
            elif delivery_breach and quality_breach:
                multiplier = _decimal(parameters.get("both_multiplier"), "both multiplier")
            elif delivery_breach or quality_breach:
                multiplier = _decimal(parameters.get("single_multiplier"), "single multiplier")
            else:
                multiplier = _decimal(parameters.get("pass_multiplier"), "pass multiplier")
            outputs[item.target] = multiplier
            continue

        if item.operation == "ACTIVE_PERIOD_PRORATION":
            active_days = _integer(outputs.get("M6"), "active days")
            period_start = _date(_required(inputs, "period_start"), "period start")
            period_end = _date(_required(inputs, "period_end"), "period end")
            period_days = max(1, (period_end - period_start).days + 1)
            floor = _decimal(parameters.get("floor"), "proration floor")
            cap = _decimal(parameters.get("cap"), "proration cap")
            outputs[item.target] = min(
                cap,
                max(floor, Decimal(active_days) / Decimal(period_days)),
            )
            continue

        if item.operation == "CAP_THEN_ROUND":
            adjusted = _decimal(outputs.get("R6"), "adjusted rebate")
            cap = _decimal(parameters.get("cap"), "rebate cap")
            digits = _integer(parameters.get("digits"), "rounding digits")
            if digits < 0 or digits > 12:
                raise PolicyOracleError("Rounding digits are outside the approved range")
            quantum = Decimal(1).scaleb(-digits)
            outputs[item.target] = min(adjusted, cap).quantize(quantum, rounding=ROUND_HALF_UP)
            continue

        if item.operation == "DECISION_PRECEDENCE":
            if critical_excluded is None:
                incidents = _integer(_required(inputs, "critical_incidents"), "critical incidents")
                waiver = str(_required(inputs, "critical_waiver")).strip().upper()
                critical_excluded = (
                    incidents
                    >= _integer(parameters.get("incident_threshold"), "incident threshold")
                    and waiver != str(parameters.get("waiver_code", "")).upper()
                )
            final = _decimal(outputs.get("S6"), "final rebate")
            outputs[item.target] = (
                str(parameters.get("critical"))
                if critical_excluded
                else (str(parameters.get("zero")) if final == 0 else str(parameters.get("payable")))
            )
            continue

        raise PolicyOracleError(f"Unsupported approved policy operation: {item.operation}")

    required_targets = {"L6", "M6", "N6", "O6", "P6", "Q6", "R6", "S6", "T6"}
    missing = sorted(required_targets - outputs.keys())
    if missing:
        raise PolicyOracleError(f"Approved policy IR did not produce: {', '.join(missing)}")
    return {
        key: (float(value) if isinstance(value, Decimal) else value)
        for key, value in outputs.items()
    }
