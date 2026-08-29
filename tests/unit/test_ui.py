from pathlib import Path

from formulawitness.ui import _summary_payload

ROOT = Path(__file__).resolve().parents[2]


def test_submission_summary_is_backed_by_committed_evidence() -> None:
    summary = _summary_payload(ROOT)
    report = (ROOT / "docs/SUBMISSION_REPORT.md").read_text(encoding="utf-8")

    assert summary["workbook_count"] == 16
    assert summary["hidden_cases_per_workbook"] == 48
    assert summary["baseline_e2e_srr"] == 33.333333333333336
    assert summary["advanced_e2e_srr"] == 100
    assert summary["improvement_pp"] == 66.66666666666666
    assert summary["advanced_clean_preservation"] == 100
    assert summary["advanced_hard_rate"] == 100
    assert summary["human_time_status"] == "not_measured"
    assert summary["model_api_cost_usd_per_task"] == {"baseline": 0.0, "advanced": 0.0}
    assert f"{summary['baseline_runtime_seconds']:.3f} s" in report
    assert f"{summary['advanced_runtime_seconds']:.3f} s" in report
    assert "Human time per task | Not measured | Not measured | No claim" in report
