from pathlib import Path

from formulawitness.evaluation import run_evaluation

ROOT = Path(__file__).resolve().parents[2]


def test_advanced_improves_by_at_least_twenty_points_without_false_repairs(tmp_path: Path) -> None:
    result = run_evaluation(ROOT, tmp_path / "results.json")
    assert result["improvement_percentage_points"] >= 20
    assert result["advanced"]["clean_preservation_rate"] == 100
    assert all(result["acceptance"].values())
