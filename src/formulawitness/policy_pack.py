"""Content-addressed approved Policy Pack materialization for the controlled demo.

The module implements one honest vertical slice for the supplier-rebate policy. It
does not claim to compile arbitrary policies. Pack configuration is versioned in
the repository, while exact cited rules, deterministic tests, expected outcomes,
and separate workbook mappings are materialized and hash-bound at runtime.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pypdf import PdfReader

from .models import Rule, RuleIR, TestCase
from .ooxml import sha256_file
from .policy import (
    CORE_OUTPUTS,
    INPUT_CELL_MAP,
    ambiguity_gate,
    compile_rule_ir,
    extract_rules,
    verify_citations,
)
from .policy_oracle import evaluate_rule_ir
from .public_benchmark import DEFAULT_INPUTS
from .trace import object_hash

PACK_SCHEMA_VERSION = 1
POLICY_ORACLE_VERSION = "supplier-rebate-rule-ir-v1"
TEST_GENERATOR_VERSION = "supplier-rebate-boundaries-v1"
MAPPING_VERSION = "supplier-rebate-row6-v1"
VERIFICATION_ENGINE_VERSION = "approved-pack-verifier-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class PackApproval(BaseModel):
    """One role-specific review recorded by a version-controlled demo pack."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reviewer: str = Field(min_length=3, max_length=128)
    role: Literal["POLICY_OWNER", "CONTROLS_REVIEWER"]
    candidate_hash: str
    reviewed_case_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("reviewer")
    @classmethod
    def reviewer_is_normalized(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("reviewer must not contain surrounding whitespace")
        return value

    @field_validator("candidate_hash")
    @classmethod
    def valid_candidate_hash(cls, value: str) -> str:
        if SHA256_RE.fullmatch(value) is None:
            raise ValueError("candidate_hash must be a lowercase SHA-256 digest")
        return value


class RegressionCaseSpec(BaseModel):
    """A human-discovered example whose expected result comes from approved rules."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    category: str = Field(min_length=3, max_length=128)
    description: str = Field(min_length=10, max_length=500)
    rule_ids: tuple[str, ...] = Field(min_length=1)
    input_updates: dict[str, Any]

    @field_validator("case_id")
    @classmethod
    def valid_case_id(cls, value: str) -> str:
        if IDENTIFIER_RE.fullmatch(value) is None:
            raise ValueError("case_id must be a stable identifier")
        return value


class PolicyPackConfig(BaseModel):
    """Reviewed release metadata kept separate from generated executable content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    policy_id: str
    version: str
    effective_from: date
    state: Literal["ACTIVE_DEMO"]
    risk_tier: Literal["HIGH"]
    source_document: str
    source_sha256: str
    approved_release_hash: str
    parent_pack_hash: str | None = None
    approval_scope: Literal["SYNTHETIC_DEMO"]
    approvals: tuple[PackApproval, ...]
    regression_cases: tuple[RegressionCaseSpec, ...] = ()

    @field_validator("policy_id", "version")
    @classmethod
    def valid_identifier(cls, value: str) -> str:
        if IDENTIFIER_RE.fullmatch(value) is None:
            raise ValueError("policy identifiers must be stable and path-safe")
        return value

    @field_validator("source_sha256", "approved_release_hash")
    @classmethod
    def valid_source_hash(cls, value: str) -> str:
        if SHA256_RE.fullmatch(value) is None:
            raise ValueError("release hashes must be lowercase SHA-256 digests")
        return value

    @field_validator("parent_pack_hash")
    @classmethod
    def valid_parent_hash(cls, value: str | None) -> str | None:
        if value is not None and SHA256_RE.fullmatch(value) is None:
            raise ValueError("parent_pack_hash must be a lowercase SHA-256 digest")
        return value

    @field_validator("source_document")
    @classmethod
    def relative_source_path(cls, value: str) -> str:
        candidate = PurePosixPath(value)
        if (
            candidate.is_absolute()
            or ".." in candidate.parts
            or candidate.suffix.casefold() != ".pdf"
        ):
            raise ValueError("source_document must be a relative PDF path")
        return candidate.as_posix()

    @model_validator(mode="after")
    def approval_quorum_and_unique_cases(self) -> PolicyPackConfig:
        roles = {approval.role for approval in self.approvals}
        reviewers = {approval.reviewer.casefold() for approval in self.approvals}
        if roles != {"POLICY_OWNER", "CONTROLS_REVIEWER"}:
            raise ValueError("high-risk packs require policy-owner and controls approvals")
        if len(reviewers) != len(self.approvals):
            raise ValueError("the same reviewer cannot satisfy both approval roles")
        case_ids = [case.case_id for case in self.regression_cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("regression case IDs must be unique")
        return self


@dataclass(frozen=True)
class MaterializedPolicyTest:
    case: TestCase
    origin: Literal["GENERATED", "REGRESSION"]
    rationale: str
    expected: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case.case_id,
            "category": self.case.category,
            "origin": self.origin,
            "rationale": self.rationale,
            "inputs": self.case.inputs,
            "rule_ids": list(self.case.provenance_rule_ids),
            "expected": self.expected,
        }


@dataclass(frozen=True)
class MaterializedPolicyPack:
    config: PolicyPackConfig
    source_page_count: int
    rules: tuple[Rule, ...]
    operations: tuple[RuleIR, ...]
    tests: tuple[MaterializedPolicyTest, ...]
    pack_payload: dict[str, Any]
    mapping_payload: dict[str, Any]
    pack_hash: str
    test_suite_hash: str
    mapping_hash: str

    def public_manifest(self) -> dict[str, Any]:
        generated = sum(test.origin == "GENERATED" for test in self.tests)
        regression = len(self.tests) - generated
        return {
            "schema_version": PACK_SCHEMA_VERSION,
            "policy_id": self.config.policy_id,
            "version": self.config.version,
            "effective_from": self.config.effective_from.isoformat(),
            "state": self.config.state,
            "risk_tier": self.config.risk_tier,
            "approval_scope": self.config.approval_scope,
            "approval_warning": (
                "This public pack uses synthetic demo-role approvals, not production identity."
            ),
            "approvals": [
                {
                    "reviewer": approval.reviewer,
                    "role": approval.role,
                    "candidate_hash": approval.candidate_hash,
                    "reviewed_case_ids": list(approval.reviewed_case_ids),
                }
                for approval in self.config.approvals
            ],
            "rule_count": len(self.rules),
            "unresolved_rule_count": sum(rule.status != "EXACT" for rule in self.rules),
            "generated_test_count": generated,
            "regression_test_count": regression,
            "test_count": len(self.tests),
            "pack_hash": self.pack_hash,
            "test_suite_hash": self.test_suite_hash,
            "mapping_hash": self.mapping_hash,
            "policy_oracle_version": POLICY_ORACLE_VERSION,
            "test_generator_version": TEST_GENERATOR_VERSION,
            "verification_engine_version": VERIFICATION_ENGINE_VERSION,
            "model_calls_for_recurring_audit": 0,
            "rules": [
                {
                    "rule_id": rule.rule_id,
                    "title": rule.title,
                    "status": rule.status,
                    "page": rule.evidence.page,
                    "exact_quote": rule.evidence.exact_quote,
                    "boundaries": list(rule.boundaries),
                }
                for rule in self.rules
            ],
            "regression_tests": [
                test.to_dict() for test in self.tests if test.origin == "REGRESSION"
            ],
            "governance": {
                "availability": "REQUIRED_PRODUCTION_WORKFLOW_NOT_IN_PUBLIC_DEMO",
                "public_demo_behavior": (
                    "The public site verifies one approved synthetic release and does not persist "
                    "drafts, approvals, supersession, or an audit-impact registry."
                ),
                "new_edge_case_flow": [
                    "capture minimal example",
                    "classify test gap policy ambiguity mapping drift engine gap or bad data",
                    "preview rule and historical impact",
                    "obtain policy owner and controls review",
                    "publish a new immutable version and rerun affected audits",
                ],
                "incorrect_policy_flow": [
                    "withdraw or supersede the incorrect version",
                    "approve corrected meaning as a new version",
                    "identify audits bound to the old hash",
                    "rerun affected workbooks without deleting old evidence",
                ],
            },
        }


def load_policy_pack_config(path: Path) -> PolicyPackConfig:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Policy Pack configuration could not be read: {path.name}") from exc
    return PolicyPackConfig.model_validate(payload)


def _test_case(
    case_id: str,
    category: str,
    rule_ids: tuple[str, ...],
    rationale: str,
    **updates: Any,
) -> tuple[TestCase, str]:
    return (
        TestCase(case_id, category, {**DEFAULT_INPUTS, **updates}, rule_ids),
        rationale,
    )


def _generated_cases(operations: list[RuleIR]) -> list[tuple[TestCase, str]]:
    by_target = {operation.target: operation for operation in operations}
    lookup = cast(dict[str, Any], by_target["N6"].parameters)
    sla = cast(dict[str, Any], by_target["P6"].parameters)
    thresholds = [float(value) for value in cast(list[Any], lookup["lower_bounds"])[1:]]
    delivery = float(str(sla["delivery_threshold"]))
    quality = float(str(sla["quality_threshold"]))
    cases = [
        _test_case(
            "GEN-ELIGIBLE-ORDINARY",
            "eligible_spend_ordinary",
            ("RB-101", "RB-102", "RB-103"),
            "ordinary eligible-spend calculation",
            gross_eligible_invoices=180000,
        ),
        _test_case(
            "GEN-DEDUCT-RETURNS",
            "eligible_spend_returns",
            ("RB-101",),
            "returns and credits are deducted",
            gross_eligible_invoices=260000,
            returns_credits=15000,
        ),
        _test_case(
            "GEN-DEDUCT-PASSTHROUGH",
            "eligible_spend_passthrough",
            ("RB-101",),
            "pass-through charges are deducted",
            gross_eligible_invoices=260000,
            pass_through_charges=15000,
        ),
        _test_case(
            "GEN-ELIGIBLE-FLOOR",
            "eligible_spend_floor_active",
            ("RB-101",),
            "deductions above gross invoices activate the zero floor",
            gross_eligible_invoices=10000,
            returns_credits=15000,
            pass_through_charges=5000,
        ),
    ]
    for threshold in thresholds:
        label = f"{threshold:g}"
        for suffix, delta in (("BELOW", -0.01), ("AT", 0.0), ("ABOVE", 0.01)):
            cases.append(
                _test_case(
                    f"GEN-TIER-{label}-{suffix}",
                    f"tier_{label}_{suffix.casefold()}",
                    ("RB-102",),
                    f"ordered tier boundary {suffix.casefold()} {label}",
                    gross_eligible_invoices=threshold + delta,
                )
            )
    for suffix, delta in (("BELOW", -0.0001), ("AT", 0.0), ("ABOVE", 0.0001)):
        cases.append(
            _test_case(
                f"GEN-DELIVERY-{suffix}",
                f"delivery_{suffix.casefold()}",
                ("RB-202",),
                f"delivery threshold {suffix.casefold()}",
                on_time_rate=delivery + delta,
            )
        )
        cases.append(
            _test_case(
                f"GEN-QUALITY-{suffix}",
                f"quality_{suffix.casefold()}",
                ("RB-202",),
                f"quality threshold {suffix.casefold()}",
                defect_rate=quality + delta,
            )
        )
    cases.extend(
        [
            _test_case(
                "GEN-CRITICAL-PRECEDENCE",
                "critical_precedence",
                ("RB-201",),
                "an unwaived critical incident takes precedence",
                critical_incidents=int(str(sla["incident_threshold"])),
                critical_waiver="N",
            ),
            _test_case(
                "GEN-SLA-BOTH",
                "both_sla_breaches",
                ("RB-202",),
                "combined delivery and quality breach",
                on_time_rate=delivery - 0.01,
                defect_rate=quality + 0.01,
            ),
            _test_case(
                "GEN-PRORATION-FULL",
                "full_period_proration",
                ("RB-204", "RB-205"),
                "contract is active for the full period",
                contract_start="2026-01-01",
            ),
            _test_case(
                "GEN-PRORATION-PARTIAL",
                "partial_period_proration",
                ("RB-204", "RB-205"),
                "contract starts one day into the period",
                contract_start="2026-01-02",
            ),
            _test_case(
                "GEN-PRORATION-ZERO",
                "zero_period_proration",
                ("RB-204", "RB-205"),
                "contract begins two days after the settlement period and activates the day floor",
                contract_start="2026-04-02",
            ),
            _test_case(
                "GEN-CAP-ACTIVE",
                "cap_active",
                ("RB-301", "RB-302"),
                "an unpenalized gross rebate above the limit activates the final cap",
                gross_eligible_invoices=600000,
            ),
            _test_case(
                "GEN-CAP-AFTER-PENALTY",
                "cap_after_penalty",
                ("RB-301", "RB-302"),
                "cap is applied after SLA and proration multipliers",
                gross_eligible_invoices=600000,
                on_time_rate=delivery - 0.01,
            ),
        ]
    )
    return cases


def _rule_payload(rule: Rule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "title": rule.title,
        "status": rule.status,
        "boundaries": list(rule.boundaries),
        "depends_on": list(rule.depends_on),
        "citation": asdict(rule.evidence),
    }


def _operation_payload(operation: RuleIR) -> dict[str, Any]:
    return {
        "target": operation.target,
        "operation": operation.operation,
        "rule_ids": list(operation.rule_ids),
        "parameters": operation.parameters,
    }


def _implementation_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    files = {
        "data_models": package / "models.py",
        "isolated_runner": package / "runner.py",
        "isolated_worker": package / "worker.py",
        "object_hashing": package / "trace.py",
        "ooxml_reader": package / "ooxml.py",
        "path_guard": package / "path_guard.py",
        "policy_compiler": package / "policy.py",
        "policy_oracle": package / "policy_oracle.py",
        "test_generator": package / "policy_pack.py",
        "verification_engine": package / "policy_pack_runtime.py",
        "workbook_formula_engine": package / "formula.py",
    }
    return {name: _source_code_hash(path) for name, path in sorted(files.items())}


def _source_code_hash(path: Path) -> str:
    """Hash UTF-8 source with canonical newlines across Git checkout platforms."""

    try:
        canonical = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Approved implementation source is unavailable: {path.name}") from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _release_payload(
    config: PolicyPackConfig,
    *,
    source_page_count: int,
    rules: tuple[Rule, ...] | list[Rule],
    operations: tuple[RuleIR, ...] | list[RuleIR],
    tests_payload: list[dict[str, Any]],
    test_suite_hash: str,
    mapping_payload: dict[str, Any],
    mapping_hash: str,
) -> dict[str, Any]:
    return {
        "schema_version": PACK_SCHEMA_VERSION,
        "policy_id": config.policy_id,
        "version": config.version,
        "effective_from": config.effective_from.isoformat(),
        "source_document_sha256": config.source_sha256,
        "source_page_count": source_page_count,
        "parent_pack_hash": config.parent_pack_hash,
        "risk_tier": config.risk_tier,
        "approval_scope": config.approval_scope,
        "policy_oracle_version": POLICY_ORACLE_VERSION,
        "test_generator_version": TEST_GENERATOR_VERSION,
        "mapping_version": MAPPING_VERSION,
        "verification_engine_version": VERIFICATION_ENGINE_VERSION,
        "implementation_hashes": _implementation_hashes(),
        "rules": [_rule_payload(rule) for rule in rules],
        "operations": [_operation_payload(operation) for operation in operations],
        "tests": tests_payload,
        "test_suite_hash": test_suite_hash,
        "mapping": mapping_payload,
        "mapping_hash": mapping_hash,
    }


def validate_materialized_policy_pack(pack: MaterializedPolicyPack) -> None:
    """Rebuild every content hash so shallow in-memory mutation fails closed."""

    tests_payload = [test.to_dict() for test in pack.tests]
    test_suite_hash = object_hash(
        {
            "policy_id": pack.config.policy_id,
            "version": pack.config.version,
            "generator": TEST_GENERATOR_VERSION,
            "tests": tests_payload,
        }
    )
    if test_suite_hash != pack.test_suite_hash:
        raise ValueError("Materialized Policy Pack test suite changed after approval")
    mapping_hash = object_hash(pack.mapping_payload)
    if mapping_hash != pack.mapping_hash:
        raise ValueError("Materialized Policy Pack mapping changed after approval")
    release_payload = _release_payload(
        pack.config,
        source_page_count=pack.source_page_count,
        rules=pack.rules,
        operations=pack.operations,
        tests_payload=tests_payload,
        test_suite_hash=test_suite_hash,
        mapping_payload=pack.mapping_payload,
        mapping_hash=mapping_hash,
    )
    if release_payload != pack.pack_payload or object_hash(release_payload) != pack.pack_hash:
        raise ValueError("Materialized Policy Pack content changed after approval")
    if pack.config.approved_release_hash != pack.pack_hash:
        raise ValueError("Materialized Policy Pack no longer matches its approved release hash")
    if any(approval.candidate_hash != pack.pack_hash for approval in pack.config.approvals):
        raise ValueError("Materialized Policy Pack no longer matches its approval records")


def materialize_policy_pack(root: Path, config_path: Path | None = None) -> MaterializedPolicyPack:
    config_file = config_path or root / "policy_packs/supplier-rebate-sla/v1.json"
    config = load_policy_pack_config(config_file)
    source = (root / config.source_document).resolve()
    try:
        source.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Policy Pack source escapes the repository root") from exc
    if sha256_file(source) != config.source_sha256:
        raise ValueError("Policy Pack source document hash changed")

    rules = extract_rules(source)
    verify_citations(source, rules)
    ambiguity_gate(rules)
    operations = compile_rule_ir(rules)
    rule_ids = {rule.rule_id for rule in rules}
    generated = _generated_cases(operations)
    materialized: list[MaterializedPolicyTest] = []
    seen_case_ids: set[str] = set()
    seen_inputs: set[str] = set()

    def add(case: TestCase, origin: Literal["GENERATED", "REGRESSION"], rationale: str) -> None:
        if case.case_id in seen_case_ids:
            raise ValueError(f"Duplicate Policy Pack test ID: {case.case_id}")
        missing_rules = sorted(set(case.provenance_rule_ids) - rule_ids)
        if missing_rules:
            raise ValueError(f"Policy test references unknown rules: {', '.join(missing_rules)}")
        input_hash = object_hash(case.inputs)
        if input_hash in seen_inputs:
            raise ValueError(f"Policy Pack contains duplicate semantic inputs: {case.case_id}")
        expected = evaluate_rule_ir(case.inputs, operations)
        materialized.append(MaterializedPolicyTest(case, origin, rationale, expected))
        seen_case_ids.add(case.case_id)
        seen_inputs.add(input_hash)

    for case, rationale in generated:
        add(case, "GENERATED", rationale)
    allowed_inputs = set(DEFAULT_INPUTS)
    for spec in config.regression_cases:
        unexpected = sorted(set(spec.input_updates) - allowed_inputs)
        if unexpected:
            raise ValueError(f"Regression case contains unknown inputs: {', '.join(unexpected)}")
        add(
            TestCase(
                spec.case_id,
                spec.category,
                {**DEFAULT_INPUTS, **spec.input_updates},
                spec.rule_ids,
            ),
            "REGRESSION",
            spec.description,
        )

    available_case_ids = {test.case.case_id for test in materialized}
    for approval in config.approvals:
        unknown_case_ids = sorted(set(approval.reviewed_case_ids) - available_case_ids)
        if unknown_case_ids:
            raise ValueError(
                f"Approval by {approval.reviewer} references unknown tests: "
                f"{', '.join(unknown_case_ids)}"
            )

    tests_payload = [test.to_dict() for test in materialized]
    test_suite_hash = object_hash(
        {
            "policy_id": config.policy_id,
            "version": config.version,
            "generator": TEST_GENERATOR_VERSION,
            "tests": tests_payload,
        }
    )
    mapping_payload = {
        "schema_version": 1,
        "mapping_version": MAPPING_VERSION,
        "policy_id": config.policy_id,
        "worksheet": "RebateCalc",
        "input_bindings": dict(sorted(INPUT_CELL_MAP.items())),
        "output_bindings": {cell: cell for cell in CORE_OUTPUTS},
    }
    mapping_hash = object_hash(mapping_payload)
    source_page_count = len(PdfReader(source).pages)
    pack_payload = _release_payload(
        config,
        source_page_count=source_page_count,
        rules=rules,
        operations=operations,
        tests_payload=tests_payload,
        test_suite_hash=test_suite_hash,
        mapping_payload=mapping_payload,
        mapping_hash=mapping_hash,
    )
    pack_hash = object_hash(pack_payload)
    if config.approved_release_hash != pack_hash:
        raise ValueError(
            "Approved Policy Pack release hash does not match materialized content: "
            f"expected {config.approved_release_hash}, computed {pack_hash}"
        )
    for approval in config.approvals:
        if approval.candidate_hash != pack_hash:
            raise ValueError(f"Approval by {approval.reviewer} does not attest release {pack_hash}")
    pack = MaterializedPolicyPack(
        config=config,
        source_page_count=source_page_count,
        rules=tuple(rules),
        operations=tuple(operations),
        tests=tuple(materialized),
        pack_payload=pack_payload,
        mapping_payload=mapping_payload,
        pack_hash=pack_hash,
        test_suite_hash=test_suite_hash,
        mapping_hash=mapping_hash,
    )
    validate_materialized_policy_pack(pack)
    return pack
