"""Zero-model recurring verification against an approved Policy Pack."""

from __future__ import annotations

import shutil
from copy import deepcopy
from decimal import Decimal
from math import isfinite
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .models import ExecutionResult
from .ooxml import inspect_safety, sha256_file
from .policy import CORE_OUTPUTS
from .policy_oracle import evaluate_rule_ir
from .policy_pack import (
    VERIFICATION_ENGINE_VERSION,
    MaterializedPolicyPack,
    validate_materialized_policy_pack,
)
from .runner import ExecutionFailed, execute_batch
from .trace import object_hash


def _same(cell: str, expected: Any, actual: Any) -> bool:
    if cell == "T6":
        return isinstance(expected, str) and isinstance(actual, str) and expected == actual
    numeric_types = (int, float, Decimal)
    if (
        isinstance(expected, bool)
        or isinstance(actual, bool)
        or not isinstance(expected, numeric_types)
        or not isinstance(actual, numeric_types)
    ):
        return False
    if not isfinite(float(expected)) or not isfinite(float(actual)):
        return False
    return abs(Decimal(str(expected)) - Decimal(str(actual))) <= Decimal("1e-8")


def verify_with_policy_pack(workbook: Path, pack: MaterializedPolicyPack) -> dict[str, Any]:
    """Run the frozen suite without constructing or calling any model client."""

    pack = deepcopy(pack)
    validate_materialized_policy_pack(pack)
    safety = inspect_safety(workbook)
    workbook_sha256 = str(safety["sha256"])
    with TemporaryDirectory(prefix="clausegrid-approved-pack-") as temporary:
        snapshot = Path(temporary) / "source.xlsx"
        shutil.copyfile(workbook, snapshot)
        if sha256_file(workbook) != workbook_sha256 or sha256_file(snapshot) != workbook_sha256:
            raise RuntimeError("Source workbook changed while creating its immutable snapshot")
        snapshot_safety = inspect_safety(snapshot)
        if snapshot_safety["sha256"] != workbook_sha256:
            raise RuntimeError("Immutable workbook snapshot does not match the approved input")
        execution_errors: dict[int, tuple[str, str]] = {}
        try:
            executions: list[ExecutionResult | None] = list(
                execute_batch(snapshot, [test.case.inputs for test in pack.tests])
            )
        except ExecutionFailed:
            executions = []
            consecutive_failures = 0
            for index, test in enumerate(pack.tests):
                try:
                    result = execute_batch(snapshot, [test.case.inputs])
                    if len(result) != 1:
                        raise ExecutionFailed("Worker returned an incomplete single-case result")
                    executions.append(result[0])
                    consecutive_failures = 0
                except ExecutionFailed:
                    executions.append(None)
                    execution_errors[index] = (
                        "ERROR",
                        "Workbook execution failed for this approved test",
                    )
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        for skipped_index in range(index + 1, len(pack.tests)):
                            executions.append(None)
                            execution_errors[skipped_index] = (
                                "SKIPPED",
                                "Test was not run after repeated workbook execution failures",
                            )
                        break
        if sha256_file(snapshot) != workbook_sha256:
            raise RuntimeError("Immutable workbook snapshot changed during verification")
        if sha256_file(workbook) != workbook_sha256:
            raise RuntimeError("Source workbook changed during Policy Pack verification")
    if len(executions) != len(pack.tests):
        raise RuntimeError("Workbook runner returned an incomplete Policy Pack result")

    records: list[dict[str, Any]] = []
    for index, (test, execution) in enumerate(zip(pack.tests, executions, strict=True)):
        recomputed_expected = evaluate_rule_ir(test.case.inputs, list(pack.operations))
        if recomputed_expected != test.expected:
            raise ValueError(f"Frozen expected result changed for {test.case.case_id}")
        if execution is None:
            status, execution_error = execution_errors[index]
            records.append(
                {
                    "case_id": test.case.case_id,
                    "category": test.case.category,
                    "origin": test.origin,
                    "rule_ids": list(test.case.provenance_rule_ids),
                    "status": status,
                    "mismatched_cells": [],
                    "expected": test.expected,
                    "actual": {cell: None for cell in CORE_OUTPUTS},
                    "execution_error": execution_error,
                }
            )
            continue
        if execution.workbook_sha256 != workbook_sha256:
            raise RuntimeError("Workbook runner returned results for a different source hash")
        if execution.inputs != test.case.inputs:
            raise RuntimeError("Workbook runner returned reordered or altered Policy Pack inputs")
        actual = {cell: execution.outputs.get(cell) for cell in CORE_OUTPUTS}
        mismatched = [
            cell for cell in CORE_OUTPUTS if not _same(cell, test.expected[cell], actual[cell])
        ]
        records.append(
            {
                "case_id": test.case.case_id,
                "category": test.case.category,
                "origin": test.origin,
                "rule_ids": list(test.case.provenance_rule_ids),
                "status": "PASS" if not mismatched else "FAIL",
                "mismatched_cells": mismatched,
                "expected": test.expected,
                "actual": actual,
            }
        )

    failed = [record for record in records if record["status"] == "FAIL"]
    errors = [record for record in records if record["status"] == "ERROR"]
    skipped = [record for record in records if record["status"] == "SKIPPED"]
    complete = not errors and not skipped
    evidence_payload = {
        "schema_version": 1,
        "workbook_sha256": workbook_sha256,
        "policy_pack_hash": pack.pack_hash,
        "mapping_pack_hash": pack.mapping_hash,
        "test_suite_hash": pack.test_suite_hash,
        "engine_version": VERIFICATION_ENGINE_VERSION,
        "records": records,
        "decision": "FAIL" if failed else ("PASS" if complete else "INCONCLUSIVE"),
        "complete": complete,
        "test_count": len(records),
        "passed_count": sum(record["status"] == "PASS" for record in records),
        "failed_count": len(failed),
        "error_count": len(errors),
        "skipped_count": len(skipped),
        "failed_case_ids": [str(record["case_id"]) for record in failed],
        "error_case_ids": [str(record["case_id"]) for record in errors],
        "affected_rule_ids": sorted(
            {str(rule_id) for record in failed for rule_id in record["rule_ids"]}
        ),
        "execution_mode": "DETERMINISTIC_APPROVED_PACK",
        "model_calls": 0,
        "model_required": False,
        "source_immutable": True,
    }
    validate_materialized_policy_pack(pack)
    evidence_hash = object_hash(evidence_payload)
    return {
        **evidence_payload,
        "run_id": f"pack-{evidence_hash[:12]}",
        "evidence_hash": evidence_hash,
    }
