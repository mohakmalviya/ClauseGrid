from pathlib import Path

from formulawitness.policy import extract_rules, verify_citations

ROOT = Path(__file__).resolve().parents[2]


def test_all_policy_rules_have_exact_verified_citations() -> None:
    policy = ROOT / "policies/supplier_rebate_sla_policy.pdf"
    rules = extract_rules(policy)
    verify_citations(policy, rules)
    assert len(rules) == 11
    assert {rule.evidence.page for rule in rules} == {2, 3, 4}
    assert all(rule.status == "EXACT" for rule in rules)
