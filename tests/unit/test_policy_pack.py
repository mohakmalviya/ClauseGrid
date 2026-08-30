import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import formulawitness.policy_pack as policy_pack_module
from formulawitness.policy_pack import (
    PolicyPackConfig,
    load_policy_pack_config,
    materialize_policy_pack,
)
from formulawitness.trace import object_hash

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "policy_packs/supplier-rebate-sla/v1.json"


def test_controlled_policy_pack_is_hash_bound_and_dual_reviewed() -> None:
    pack = materialize_policy_pack(ROOT)
    manifest = pack.public_manifest()

    assert pack.pack_hash == object_hash(pack.pack_payload)
    assert manifest["state"] == "ACTIVE_DEMO"
    assert manifest["approval_scope"] == "SYNTHETIC_DEMO"
    assert {approval["role"] for approval in manifest["approvals"]} == {
        "POLICY_OWNER",
        "CONTROLS_REVIEWER",
    }
    assert {approval["candidate_hash"] for approval in manifest["approvals"]} == {pack.pack_hash}
    assert manifest["unresolved_rule_count"] == 0
    assert manifest["generated_test_count"] >= 20
    assert manifest["regression_test_count"] == 1
    assert manifest["model_calls_for_recurring_audit"] == 0
    assert manifest["governance"]["availability"] == (
        "REQUIRED_PRODUCTION_WORKFLOW_NOT_IN_PUBLIC_DEMO"
    )
    assert len(pack.pack_hash) == len(pack.mapping_hash) == len(pack.test_suite_hash) == 64


def test_regression_expected_outcome_is_computed_not_configured() -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["regression_cases"][0]["expected"] = {"S6": 1234}

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PolicyPackConfig.model_validate(payload)


def test_high_risk_pack_requires_two_distinct_review_roles() -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["approvals"][1]["reviewer"] = payload["approvals"][0]["reviewer"]
    with pytest.raises(ValidationError, match="same reviewer"):
        PolicyPackConfig.model_validate(payload)

    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["approvals"] = payload["approvals"][:1]
    with pytest.raises(ValidationError, match="policy-owner and controls"):
        PolicyPackConfig.model_validate(payload)


def test_pack_rejects_changed_source_and_unknown_regression_inputs(tmp_path: Path) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["source_sha256"] = "0" * 64
    config = tmp_path / "source-changed.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="source document hash changed"):
        materialize_policy_pack(ROOT, config)

    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["regression_cases"][0]["input_updates"]["invented_input"] = 1
    config = tmp_path / "unknown-input.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown inputs"):
        materialize_policy_pack(ROOT, config)


def test_pack_rejects_approval_for_a_test_that_does_not_exist(tmp_path: Path) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["approvals"][0]["reviewed_case_ids"].append("GEN-NOT-A-REAL-TEST")
    config = tmp_path / "unknown-reviewed-test.json"
    config.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="references unknown tests"):
        materialize_policy_pack(ROOT, config)


def test_pack_hash_and_test_hash_are_stable() -> None:
    first = materialize_policy_pack(ROOT)
    second = materialize_policy_pack(ROOT)

    assert first.pack_hash == second.pack_hash
    assert first.test_suite_hash == second.test_suite_hash
    assert first.mapping_hash == second.mapping_hash
    assert load_policy_pack_config(CONFIG) == first.config


def test_implementation_hash_is_stable_across_checkout_line_endings(tmp_path: Path) -> None:
    lf = tmp_path / "lf.py"
    crlf = tmp_path / "crlf.py"
    lf.write_bytes(b"first = 1\nsecond = 2\n")
    crlf.write_bytes(b"first = 1\r\nsecond = 2\r\n")

    assert policy_pack_module._source_code_hash(lf) == policy_pack_module._source_code_hash(crlf)


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("regression", None),
        ("generator", "changed-generator-version"),
        ("mapping", "Z99"),
        ("worker", "0" * 64),
    ],
)
def test_release_change_requires_new_hash_bound_approvals(
    change: str,
    value: str | None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = CONFIG
    if change == "regression":
        payload = json.loads(CONFIG.read_text(encoding="utf-8"))
        payload["regression_cases"][0]["description"] += " Reviewed again."
        config = tmp_path / "changed-regression.json"
        config.write_text(json.dumps(payload), encoding="utf-8")
    elif change == "generator":
        monkeypatch.setattr(policy_pack_module, "TEST_GENERATOR_VERSION", value)
    elif change == "mapping":
        monkeypatch.setitem(
            policy_pack_module.INPUT_CELL_MAP,
            "gross_eligible_invoices",
            value,
        )
    else:
        implementation_hashes = policy_pack_module._implementation_hashes()
        implementation_hashes["isolated_worker"] = str(value)
        monkeypatch.setattr(
            policy_pack_module,
            "_implementation_hashes",
            lambda: implementation_hashes,
        )

    with pytest.raises(ValueError, match="release hash does not match"):
        materialize_policy_pack(ROOT, config)
