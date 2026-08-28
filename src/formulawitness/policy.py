"""Policy extraction, exact citation verification, and executable public rule model."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .formula import evaluate_cells, excel_serial
from .models import Rule, SourceSpan

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
        "Tier boundaries",
        "N6",
        2,
        "The rebate rate is 0% when eligible spend is below $100,000; 2% from $100,000 inclusive to below $250,000; 3% from $250,000 inclusive to below $500,000; and 4% at $500,000 or above.",
        ("100000", "250000", "500000"),
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
        "Active days",
        "M6",
        3,
        "Active days are inclusive calendar days from the later of the period start and contract start through the period end, floored at zero.",
        (),
        (),
    ),
    (
        "RB-205",
        "Tenure multiplier",
        "Q6",
        3,
        "The tenure multiplier is 0.50 when active days are below 90 and 1.00 when active days are 90 or more.",
        ("active_days<90",),
        ("RB-204",),
    ),
    (
        "RB-301",
        "Adjustment order",
        "R6",
        4,
        "Adjusted rebate equals gross rebate multiplied by the SLA multiplier and then by the tenure multiplier.",
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
CORE_OUTPUTS = ("L6", "M6", "N6", "O6", "P6", "Q6", "R6", "S6", "T6")


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
    for rule_id, title, target, page_number, quote, boundaries, dependencies in RULE_SPECS:
        page_text = pages[page_number - 1]
        start = page_text.find(quote)
        if start < 0:
            raise ValueError(f"Policy citation not found for {rule_id} on page {page_number}")
        span = SourceSpan(
            document_sha256=document_hash,
            page=page_number,
            start_char=start,
            end_char=start + len(quote),
            exact_quote=quote,
            quote_sha256=_hash_bytes(quote.encode("utf-8")),
        )
        rules.append(
            Rule(
                rule_id=rule_id,
                title=title,
                target=target,
                status="EXACT",
                evidence=span,
                boundaries=tuple(boundaries),
                depends_on=tuple(dependencies),
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


def compile_rule_formulas(row: int = 6) -> dict[str, str]:
    r = str(row)
    return {
        f"L{r}": f"=MAX(0,E{r}-F{r}-G{r})",
        f"M{r}": f"=MAX(0,C{r}-MAX(B{r},D{r})+1)",
        f"N{r}": f"=IF(L{r}<100000,0,IF(L{r}<250000,0.02,IF(L{r}<500000,0.03,0.04)))",
        f"O{r}": f"=L{r}*N{r}",
        f"P{r}": f'=IF(AND(J{r}>=1,K{r}<>"Y"),0,IF(AND(H{r}<0.95,I{r}>0.02),0.6,IF(OR(H{r}<0.95,I{r}>0.02),0.75,1)))',
        f"Q{r}": f"=IF(M{r}<90,0.5,1)",
        f"R{r}": f"=O{r}*P{r}*Q{r}",
        f"S{r}": f"=ROUND(MIN(R{r},20000),2)",
        f"T{r}": f'=IF(AND(J{r}>=1,K{r}<>"Y"),"EXCLUDED_CRITICAL",IF(S{r}=0,"NO_REBATE","PAYABLE"))',
    }


def evaluate_approved_rules(inputs: dict[str, Any]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for name, cell in INPUT_CELL_MAP.items():
        value = inputs[name]
        raw[cell] = (
            excel_serial(value)
            if name in {"period_start", "period_end", "contract_start"}
            else value
        )
    outputs, _ = evaluate_cells(raw, compile_rule_formulas())
    return {cell: outputs[cell] for cell in CORE_OUTPUTS}


def write_rules_yaml(path: Path, rules: list[Rule]) -> None:
    payload = {
        "schema_version": 1,
        "policy_id": "SR-SLA-2026.1",
        "currency": "USD",
        "ambiguity_status": "resolved",
        "rules": [
            {
                "id": rule.rule_id,
                "title": rule.title,
                "target": rule.target,
                "status": rule.status,
                "boundaries": list(rule.boundaries),
                "depends_on": list(rule.depends_on),
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
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
