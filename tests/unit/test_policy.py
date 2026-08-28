from dataclasses import replace
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from formulawitness.advanced import run_advanced
from formulawitness.policy import (
    RULE_SPECS,
    PolicyAmbiguityError,
    ambiguity_gate,
    compile_rule_formulas,
    compile_rule_ir,
    detect_ambiguity,
    extract_rules,
    verify_citations,
)

ROOT = Path(__file__).resolve().parents[2]


def test_all_policy_rules_have_exact_verified_citations() -> None:
    policy = ROOT / "policies/supplier_rebate_sla_policy.pdf"
    rules = extract_rules(policy)
    verify_citations(policy, rules)
    assert len(rules) == 11
    assert {rule.evidence.page for rule in rules} == {2, 3, 4}
    assert all(rule.status == "EXACT" for rule in rules)


def test_cited_rules_compile_to_explicit_lookup_and_proration_ir() -> None:
    policy = ROOT / "policies/supplier_rebate_sla_policy.pdf"
    rules = extract_rules(policy)
    ir = {item.target: item for item in compile_rule_ir(rules)}
    formulas = compile_rule_formulas(rules)

    assert ir["N6"].operation == "ORDERED_RANGE_LOOKUP"
    assert ir["N6"].parameters["lower_bounds"] == ["0", "100000", "250000", "500000"]
    assert ir["N6"].parameters["rates"] == ["0", "0.02", "0.03", "0.04"]
    assert ir["Q6"].operation == "ACTIVE_PERIOD_PRORATION"
    assert formulas["N6"] == "=LOOKUP(L6,TierSchedule!A5:A8,TierSchedule!B5:B8)"
    assert formulas["Q6"] == "=MIN(1,M6/MAX(1,C6-B6+1))"


def test_ambiguity_detector_flags_vague_or_missing_boundary_language() -> None:
    reasons = detect_ambiguity(
        "A reasonable rebate applies around $100,000.",
        ("inclusive", "below $100,000"),
    )
    assert "vague term: reasonable" in reasons
    assert "vague term: around" in reasons
    assert "missing boundary/precedence language: inclusive" in reasons


def test_ambiguity_gate_requires_human_clarification() -> None:
    policy = ROOT / "policies/supplier_rebate_sla_policy.pdf"
    rules = extract_rules(policy)
    ambiguous = replace(
        rules[0],
        status="AMBIGUOUS",
        ambiguity_reasons=("missing unit",),
    )
    with pytest.raises(PolicyAmbiguityError, match="human clarification"):
        ambiguity_gate([ambiguous, *rules[1:]])


def _write_ambiguous_policy(path: Path) -> None:
    document = canvas.Canvas(str(path))
    document.drawString(72, 760, "Synthetic policy ambiguity test")
    document.showPage()
    for page_number in (2, 3, 4):
        y = 760
        for rule_id, title, _target, rule_page, quote, _boundaries, _dependencies in RULE_SPECS:
            if rule_page != page_number:
                continue
            document.setFont("Helvetica-Bold", 8)
            document.drawString(40, y, f"{rule_id} {title}")
            y -= 14
            document.setFont("Helvetica", 7)
            if rule_id == "RB-102":
                quote = "The rebate rate is approximately 2% around $100,000."
            document.drawString(40, y, quote)
            y -= 24
        marker = {
            2: "Required source fields",
            3: "Boundary control:",
            4: "Controlled calculation sequence",
        }[page_number]
        document.drawString(40, y, marker)
        document.showPage()
    document.save()


def test_ambiguous_policy_abstains_before_repair(tmp_path: Path) -> None:
    policy = tmp_path / "ambiguous-policy.pdf"
    _write_ambiguous_policy(policy)
    rules = extract_rules(policy)
    assert next(rule for rule in rules if rule.rule_id == "RB-102").status == "AMBIGUOUS"

    workbook = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    result = run_advanced(workbook, policy, tmp_path / "artifacts", reviewer="test-reviewer")
    assert result.decision == "ABSTAIN"
    assert result.output_workbook is None
    assert result.tests == []
    assert result.patches == []
