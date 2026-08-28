"""Write the public hash manifest that proves the benchmark is frozen."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.sealed.cases import held_out_cases
from formulawitness.ooxml import sha256_file
from formulawitness.public_benchmark import DEFECT_FAMILIES, WORKBOOK_CASES, visible_cases
from formulawitness.trace import object_hash


def main() -> None:
    root = ROOT
    payload = {
        "schema_version": 1,
        "benchmark": "SupplierRebate-SLA-16-v2",
        "frozen_on": "2026-08-29",
        "case_contract_revision": 2,
        "policy_sha256": sha256_file(root / "policies/supplier_rebate_sla_policy.pdf"),
        "pristine_sha256": sha256_file(root / "workbooks/reference/supplier_rebate_pristine.xlsx"),
        "workbooks": {
            case_id: sha256_file(root / relative)
            for case_id, relative in sorted(WORKBOOK_CASES.items())
        },
        "defect_families": DEFECT_FAMILIES,
        "visible_case_count": len(visible_cases()),
        "visible_manifest_sha256": object_hash([case.__dict__ for case in visible_cases()]),
        "held_out_case_count": len(held_out_cases()),
        "held_out_manifest_sha256": object_hash([case.__dict__ for case in held_out_cases()]),
        "held_out_payload_in_manifest": False,
        "note": "Revision 2 was created during a pre-submission adversarial audit to require a real ordered LOOKUP, proportional effective-date proration, and 48 held-out inputs disjoint from visible inputs. No repair logic was changed in response to revision-2 held-out scores. Scored repair workers receive neither held-out payload nor oracle.",
    }
    output = root / "fixtures/frozen-benchmark.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
