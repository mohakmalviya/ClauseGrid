"""Policy extraction, exact citation verification, and executable public rule model."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, cast

from pypdf import PdfReader

from .models import Rule, RuleIR, SourceSpan
from .policy_oracle import evaluate_rule_ir

RULE_SPECS = (
    (
        "RB-101",
        "Eligible spend",
        "L6",
        2,
        "Eligible spend equals gross eligible invoices minus returns and credits minus pass-through charges, floored at zero.",
        (),
        (),
    ),
    (
        "RB-102",
        "Ordered tier lookup boundaries",
        "N6",
        2,
        "The tier schedule is an ordered range lookup: the rebate rate is 0% when eligible spend is below $100,000; 2% from $100,000 inclusive to below $250,000; 3% from $250,000 inclusive to below $500,000; and 4% at $500,000 or above.",
        ("eligible_spend<100000", "eligible_spend<250000", "eligible_spend<500000"),
        ("RB-101",),
    ),
    (
        "RB-103",
        "Gross rebate",
        "O6",
        2,
        "Gross rebate equals eligible spend multiplied by the rebate rate, with no intermediate rounding.",
        (),
        ("RB-101", "RB-102"),
    ),
    (
        "RB-201",
        "Critical incident precedence",
        "P6",
        3,
        "One or more critical incidents sets the SLA multiplier to zero unless the critical-incident waiver is Y; this exclusion is evaluated before ordinary SLA penalties.",
        ("critical_incidents>=1",),
        (),
    ),
    (
        "RB-202",
        "Ordinary SLA penalties",
        "P6",
        3,
        "When critical exclusion does not apply, the SLA multiplier is 0.60 if on-time delivery is below 95% and defect rate is above 2%, 0.75 if exactly one of those conditions is true, and 1.00 otherwise.",
        ("on_time_rate<0.95", "defect_rate>0.02"),
        ("RB-201",),
    ),
    (
        "RB-203",
        "Waiver scope",
        "P6",
        3,
        "A critical-incident waiver waives only the critical exclusion; it does not waive an ordinary delivery or quality penalty.",
        (),
        ("RB-201", "RB-202"),
    ),
    (
        "RB-204",
        "Contract-effective active days",
        "M6",
        3,
        "Contract-effective active days are inclusive calendar days from the later of the period start and contract start through the period end, floored at zero.",
        (),
        (),
    ),
    (
        "RB-205",
        "Effective-date proration multiplier",
        "Q6",
        3,
        "The effective-date proration multiplier equals contract-effective active days divided by the inclusive calendar days in the settlement period, capped at 1.00 and floored at zero.",
        ("active_days/period_days", "multiplier<=1"),
        ("RB-204",),
    ),
    (
        "RB-301",
        "Adjustment order",
        "R6",
        4,
        "Adjusted rebate equals gross rebate multiplied by the SLA multiplier and then by the effective-date proration multiplier.",
        (),
        ("RB-103", "RB-201", "RB-202", "RB-203", "RB-205"),
    ),
    (
        "RB-302",
        "Cap and rounding",
        "S6",
        4,
        "The $20,000 cap is applied after all multipliers, and the resulting final rebate is rounded to two decimal places only after the cap is applied.",
        ("cap=20000", "round=2"),
        ("RB-301",),
    ),
    (
        "RB-303",
        "Decision code",
        "T6",
        4,
        "Decision code is EXCLUDED_CRITICAL for an unwaived critical incident, NO_REBATE when final rebate is zero for any other reason, and PAYABLE otherwise.",
        (),
        ("RB-201", "RB-302"),
    ),
)

INPUT_CELL_MAP = {
    "supplier_id": "A6",
    "period_start": "B6",
    "period_end": "C6",
    "contract_start": "D6",
    "gross_eligible_invoices": "E6",
    "returns_credits": "F6",
    "pass_through_charges": "G6",
    "on_time_rate": "H6",
    "defect_rate": "I6",
    "critical_incidents": "J6",
    "critical_waiver": "K6",
}
DATE_INPUT_NAMES = frozenset({"period_start", "period_end", "contract_start"})
CORE_OUTPUTS = ("L6", "M6", "N6", "O6", "P6", "Q6", "R6", "S6", "T6")

RULE_CLARIFIERS = {
    "RB-101": ("floored at zero",),
    "RB-102": ("ordered range lookup", "inclusive", "below $250,000", "below $500,000", "or above"),
    "RB-103": ("no intermediate rounding",),
    "RB-201": ("one or more", "unless", "evaluated before"),
    "RB-202": ("below 95%", "above 2%", "exactly one", "otherwise"),
    "RB-203": ("waives only", "does not waive"),
    "RB-204": ("contract-effective", "inclusive calendar days", "later of", "floored at zero"),
    "RB-205": (
        "effective-date proration",
        "divided by the inclusive calendar days",
        "capped at 1.00",
        "floored at zero",
    ),
    "RB-301": ("then by",),
    "RB-302": ("after all multipliers", "only after the cap"),
    "RB-303": ("for any other reason", "otherwise"),
}

VAGUE_TERMS = (
    "approximately",
    "around",
    "generally",
    "material",
    "reasonable",
    "significant",
    "substantially",
)


class PolicyAmbiguityError(ValueError):
    """Raised when a rule cannot safely become an executable oracle."""


def detect_ambiguity(text: str, required_clarifiers: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Return deterministic reasons that make a narrow policy rule non-executable."""

    normalized = _normalize(text).lower()
    reasons = [
        f"vague term: {term}"
        for term in VAGUE_TERMS
        if re.search(rf"\b{re.escape(term)}\b", normalized)
    ]
    reasons.extend(
        f"missing boundary/precedence language: {phrase}"
        for phrase in required_clarifiers
        if phrase.lower() not in normalized
    )
    return tuple(reasons)


def ambiguity_gate(rules: list[Rule]) -> None:
    """Fail closed before case generation when any extracted rule is unresolved."""

    blocking = [rule for rule in rules if rule.status != "EXACT" or rule.ambiguity_reasons]
    if blocking:
        details = "; ".join(
            f"{rule.rule_id}: {', '.join(rule.ambiguity_reasons) or rule.status}"
            for rule in blocking
        )
        raise PolicyAmbiguityError(f"Policy requires human clarification: {details}")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_rules(pdf_path: Path) -> list[Rule]:
    document = pdf_path.read_bytes()
    document_hash = _hash_bytes(document)
    reader = PdfReader(pdf_path)
    pages = [_normalize(page.extract_text() or "") for page in reader.pages]
    rules: list[Rule] = []
    for (
        rule_id,
        title,
        target,
        page_number,
        reference_quote,
        boundaries,
        dependencies,
    ) in RULE_SPECS:
        page_text = pages[page_number - 1]
        anchor = f"{rule_id} {title}"
        anchor_positions = [match.start() for match in re.finditer(re.escape(anchor), page_text)]
        if not anchor_positions:
            raise ValueError(f"Policy rule heading not found for {rule_id} on page {page_number}")
        start = anchor_positions[0] + len(anchor)
        markers = [match.start() for match in re.finditer(r"\bRB-\d{3}\b", page_text[start:])]
        stop_candidates = [start + marker for marker in markers]
        for marker in (
            "Required source fields",
            "Boundary control:",
            "Controlled calculation sequence",
        ):
            marker_position = page_text.find(marker, start)
            if marker_position >= 0:
                stop_candidates.append(marker_position)
        end = min(stop_candidates) if stop_candidates else len(page_text)
        raw_quote = page_text[start:end]
        start += len(raw_quote) - len(raw_quote.lstrip())
        quote = raw_quote.strip()
        end = start + len(quote)
        if not quote:
            raise ValueError(f"Policy clause is empty for {rule_id} on page {page_number}")
        span = SourceSpan(
            document_sha256=document_hash,
            page=page_number,
            start_char=start,
            end_char=start + len(quote),
            exact_quote=quote,
            quote_sha256=_hash_bytes(quote.encode("utf-8")),
        )
        ambiguity_reasons = detect_ambiguity(quote, RULE_CLARIFIERS[rule_id])
        status: Literal["EXACT", "AMBIGUOUS", "CONFLICT", "UNSUPPORTED"] = (
            "AMBIGUOUS" if ambiguity_reasons else "EXACT"
        )
        if len(anchor_positions) > 1:
            ambiguity_reasons += ("duplicate/conflicting rule identifier",)
            status = "CONFLICT"
        if _normalize(quote) != _normalize(reference_quote):
            ambiguity_reasons += ("clause differs from frozen approved interpretation",)
            if status == "EXACT":
                status = "AMBIGUOUS"
        rules.append(
            Rule(
                rule_id=rule_id,
                title=title,
                target=target,
                status=status,
                evidence=span,
                boundaries=tuple(boundaries),
                depends_on=tuple(dependencies),
                ambiguity_reasons=ambiguity_reasons,
            )
        )
    return rules


def verify_citations(pdf_path: Path, rules: list[Rule]) -> None:
    pages = [_normalize(page.extract_text() or "") for page in PdfReader(pdf_path).pages]
    document_hash = _hash_bytes(pdf_path.read_bytes())
    for rule in rules:
        span = rule.evidence
        if span.document_sha256 != document_hash:
            raise ValueError(f"Document hash mismatch for {rule.rule_id}")
        page = pages[span.page - 1]
        if page[span.start_char : span.end_char] != span.exact_quote:
            raise ValueError(f"Citation offsets failed for {rule.rule_id}")
        if _hash_bytes(span.exact_quote.encode("utf-8")) != span.quote_sha256:
            raise ValueError(f"Quote hash mismatch for {rule.rule_id}")


def _decimal_text(value: str) -> str:
    number = Decimal(value)
    return format(number.normalize(), "f") if number else "0"


def compile_rule_ir(rules: list[Rule]) -> list[RuleIR]:
    """Parse cited, unambiguous clauses into the narrow executable rule IR."""

    ambiguity_gate(rules)
    by_id = {rule.rule_id: rule for rule in rules}
    required = {spec[0] for spec in RULE_SPECS}
    if set(by_id) != required:
        raise PolicyAmbiguityError("Policy rule set does not match the controlled schema")

    tier_rule = by_id["RB-102"]
    tier_bounds = [
        match.group("number")
        for boundary in tier_rule.boundaries
        if (match := re.fullmatch(r"eligible_spend<(?P<number>\d+(?:\.\d+)?)", boundary))
    ]
    tier_percentages = re.findall(r"(\d+(?:\.\d+)?)%", tier_rule.evidence.exact_quote)
    if len(tier_bounds) != 3 or len(tier_percentages) != 4:
        raise PolicyAmbiguityError("RB-102 could not be compiled into an ordered tier lookup")
    tier_rates = [_decimal_text(str(Decimal(value) / 100)) for value in tier_percentages]

    sla_rule = by_id["RB-202"]
    sla_quote = sla_rule.evidence.exact_quote
    delivery = re.search(r"below (\d+(?:\.\d+)?)%", sla_quote)
    quality = re.search(r"above (\d+(?:\.\d+)?)%", sla_quote)
    multipliers = re.findall(r"\b(?:0|1)\.\d+\b", sla_quote)
    if not delivery or not quality or len(multipliers) != 3:
        raise PolicyAmbiguityError("RB-202 could not be compiled into SLA precedence")

    cap_match = re.search(r"\$(\d[\d,]*) cap", by_id["RB-302"].evidence.exact_quote)
    decision_codes = re.findall(r"\b[A-Z][A-Z_]+\b", by_id["RB-303"].evidence.exact_quote)
    if not cap_match or decision_codes != ["EXCLUDED_CRITICAL", "NO_REBATE", "PAYABLE"]:
        raise PolicyAmbiguityError("Settlement cap or decision codes could not be compiled")

    return [
        RuleIR("L6", "FLOORED_SUBTRACTION", ("RB-101",), {"floor": 0}),
        RuleIR("M6", "INCLUSIVE_ACTIVE_DAYS", ("RB-204",), {"floor": 0}),
        RuleIR(
            "N6",
            "ORDERED_RANGE_LOOKUP",
            ("RB-102",),
            {
                "lower_bounds": [cast(Any, value) for value in ["0", *tier_bounds]],
                "rates": [cast(Any, value) for value in tier_rates],
                "lookup_range": "TierSchedule!A5:A8",
                "result_range": "TierSchedule!B5:B8",
            },
        ),
        RuleIR("O6", "MULTIPLY", ("RB-103",), {"left": "L6", "right": "N6"}),
        RuleIR(
            "P6",
            "CRITICAL_THEN_SLA",
            ("RB-201", "RB-202", "RB-203"),
            {
                "incident_threshold": 1,
                "waiver_code": "Y",
                "delivery_threshold": _decimal_text(str(Decimal(delivery.group(1)) / 100)),
                "quality_threshold": _decimal_text(str(Decimal(quality.group(1)) / 100)),
                "both_multiplier": _decimal_text(multipliers[0]),
                "single_multiplier": _decimal_text(multipliers[1]),
                "pass_multiplier": _decimal_text(multipliers[2]),
            },
        ),
        RuleIR(
            "Q6",
            "ACTIVE_PERIOD_PRORATION",
            ("RB-204", "RB-205"),
            {"floor": 0, "cap": "1"},
        ),
        RuleIR("R6", "MULTIPLY", ("RB-301",), {"factors": ["O6", "P6", "Q6"]}),
        RuleIR(
            "S6",
            "CAP_THEN_ROUND",
            ("RB-302",),
            {"cap": cap_match.group(1).replace(",", ""), "digits": 2},
        ),
        RuleIR(
            "T6",
            "DECISION_PRECEDENCE",
            ("RB-201", "RB-303"),
            {
                "incident_threshold": 1,
                "waiver_code": "Y",
                "critical": decision_codes[0],
                "zero": decision_codes[1],
                "payable": decision_codes[2],
            },
        ),
    ]


def compile_rule_formulas(rules: list[Rule], row: int = 6) -> dict[str, str]:
    """Compile executable IR into Excel formulas without reading a pristine workbook."""

    ir = {item.target: item for item in compile_rule_ir(rules)}
    r = str(row)
    sla = ir["P6"].parameters
    decision = ir["T6"].parameters
    cap = ir["S6"].parameters
    lookup = ir["N6"].parameters
    return {
        f"L{r}": f"=MAX(0,E{r}-F{r}-G{r})",
        f"M{r}": f"=MAX(0,C{r}-MAX(B{r},D{r})+1)",
        f"N{r}": f"=LOOKUP(L{r},{lookup['lookup_range']},{lookup['result_range']})",
        f"O{r}": f"=L{r}*N{r}",
        f"P{r}": (
            f'=IF(AND(J{r}>={sla["incident_threshold"]},K{r}<>"{sla["waiver_code"]}"),0,'
            f"IF(AND(H{r}<{sla['delivery_threshold']},I{r}>{sla['quality_threshold']}),"
            f"{sla['both_multiplier']},IF(OR(H{r}<{sla['delivery_threshold']},"
            f"I{r}>{sla['quality_threshold']}),{sla['single_multiplier']},"
            f"{sla['pass_multiplier']})))"
        ),
        f"Q{r}": f"=MIN({ir['Q6'].parameters['cap']},M{r}/MAX(1,C{r}-B{r}+1))",
        f"R{r}": f"=O{r}*P{r}*Q{r}",
        f"S{r}": f"=ROUND(MIN(R{r},{cap['cap']}),{cap['digits']})",
        f"T{r}": (
            f'=IF(AND(J{r}>={decision["incident_threshold"]},K{r}<>"{decision["waiver_code"]}"),'
            f'"{decision["critical"]}",IF(S{r}=0,"{decision["zero"]}",'
            f'"{decision["payable"]}"))'
        ),
    }


def verify_rule_sources(values: dict[str, Any], rules: list[Rule]) -> None:
    """Verify workbook lookup data agrees with the policy-derived IR."""

    lookup_ir = next(item for item in compile_rule_ir(rules) if item.target == "N6")
    lower_bounds = cast(list[Any], lookup_ir.parameters["lower_bounds"])
    rates = cast(list[Any], lookup_ir.parameters["rates"])
    for index, (lower_bound, rate) in enumerate(zip(lower_bounds, rates, strict=True), start=5):
        bound_cell = f"TIERSCHEDULE!A{index}"
        rate_cell = f"TIERSCHEDULE!B{index}"
        if bound_cell not in values or rate_cell not in values:
            raise PolicyAmbiguityError(f"TierSchedule row {index} is missing")
        try:
            actual_bound = Decimal(str(values[bound_cell]))
            actual_rate = Decimal(str(values[rate_cell]))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise PolicyAmbiguityError(f"TierSchedule row {index} is not numeric") from exc
        if actual_bound != Decimal(str(lower_bound)) or actual_rate != Decimal(str(rate)):
            raise PolicyAmbiguityError(f"TierSchedule row {index} conflicts with cited rule RB-102")


def workbook_input_overrides(inputs: dict[str, Any]) -> dict[str, Any]:
    """Map typed benchmark inputs to explicit workbook sandbox values."""

    overrides: dict[str, Any] = {}
    for name, value in inputs.items():
        cell = INPUT_CELL_MAP.get(name)
        if cell is None:
            continue
        overrides[cell] = (
            {"kind": "date", "value": value}
            if name in DATE_INPUT_NAMES and isinstance(value, str)
            else value
        )
    return overrides


def evaluate_approved_rules(inputs: dict[str, Any], rules: list[Rule]) -> dict[str, Any]:
    """Compute expected outcomes without using the spreadsheet formula evaluator."""

    outputs = evaluate_rule_ir(inputs, compile_rule_ir(rules))
    return {cell: outputs[cell] for cell in CORE_OUTPUTS}


def write_rules_yaml(path: Path, rules: list[Rule]) -> None:
    blocking = [rule for rule in rules if rule.status != "EXACT"]
    payload = {
        "schema_version": 1,
        "policy_id": "SR-SLA-2026.1",
        "currency": "USD",
        "ambiguity_status": "requires_review" if blocking else "resolved",
        "rules": [
            {
                "id": rule.rule_id,
                "title": rule.title,
                "target": rule.target,
                "status": rule.status,
                "boundaries": list(rule.boundaries),
                "depends_on": list(rule.depends_on),
                "ambiguity_reasons": list(rule.ambiguity_reasons),
                "source": {
                    "document_sha256": rule.evidence.document_sha256,
                    "page": rule.evidence.page,
                    "start_char": rule.evidence.start_char,
                    "end_char": rule.evidence.end_char,
                    "quote": rule.evidence.exact_quote,
                    "quote_sha256": rule.evidence.quote_sha256,
                },
            }
            for rule in rules
        ],
        "executable_ir": (
            [
                {
                    "target": item.target,
                    "operation": item.operation,
                    "rule_ids": list(item.rule_ids),
                    "parameters": item.parameters,
                }
                for item in compile_rule_ir(rules)
            ]
            if not blocking
            else []
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
