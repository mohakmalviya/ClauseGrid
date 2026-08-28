"""Write the public hash manifest that proves the benchmark is frozen."""

from __future__ import annotations

import json
from pathlib import Path

from formulawitness.benchmark import WORKBOOK_CASES, held_out_cases, visible_cases
from formulawitness.ooxml import sha256_file
from formulawitness.trace import object_hash


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = {
        "schema_version": 1,
        "benchmark": "SupplierRebate-SLA-16",
        "frozen_on": "2026-08-29",
        "policy_sha256": sha256_file(root / "policies/supplier_rebate_sla_policy.pdf"),
        "pristine_sha256": sha256_file(root / "workbooks/reference/supplier_rebate_pristine.xlsx"),
        "workbooks": {
            case_id: sha256_file(root / relative)
            for case_id, relative in sorted(WORKBOOK_CASES.items())
        },
        "visible_case_count": len(visible_cases()),
        "visible_manifest_sha256": object_hash([case.__dict__ for case in visible_cases()]),
        "held_out_case_count": len(held_out_cases()),
        "held_out_manifest_sha256": object_hash([case.__dict__ for case in held_out_cases()]),
        "held_out_payload_published": False,
        "note": "Hashes were fixed before baseline/advanced optimization; scored repair workflows receive neither held-out payload nor oracle.",
    }
    output = root / "fixtures/frozen-benchmark.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
