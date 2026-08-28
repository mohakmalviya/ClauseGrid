from pathlib import Path

from evals.sealed.cases import held_out_cases
from formulawitness.evaluation import run_evaluation
from formulawitness.public_benchmark import visible_cases
from formulawitness.trace import object_hash

ROOT = Path(__file__).resolve().parents[2]


def test_held_out_inputs_do_not_duplicate_visible_inputs() -> None:
    visible = {object_hash(case.inputs) for case in visible_cases()}
    held_out = {object_hash(case.inputs) for case in held_out_cases()}
    assert len(held_out) == 48
    assert visible.isdisjoint(held_out)


def test_advanced_improves_by_at_least_twenty_points_without_false_repairs(tmp_path: Path) -> None:
    output = tmp_path / "results.json"
    result = run_evaluation(ROOT, output)
    assert result["improvement_percentage_points"] >= 20
    assert result["advanced"]["clean_preservation_rate"] == 100
    assert all(result["acceptance"].values())
    assert b"\r\n" not in output.read_bytes()
