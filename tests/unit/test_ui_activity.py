import json
import shutil
import subprocess

import pytest

from formulawitness.ui import HTML, _public_activity_event


def test_public_activity_event_exposes_only_bounded_observable_metadata() -> None:
    event = _public_activity_event(
        {
            "actor": "audit-manager",
            "event": "tool_result",
            "tool": "run_experiment",
            "ok": True,
            "budget": {
                "manager_turns_used": 4,
                "manager_turn_limit": 20,
                "elapsed_time_seconds": 12.6,
            },
            "arguments": {"secret": "must-not-leak"},
            "result": {"private": "must-not-leak"},
            "model": "private-model-id",
            "provider": "private-provider",
        },
        sequence=7,
    )

    assert event == {
        "sequence": 7,
        "event": "tool_result",
        "actor": "audit-manager",
        "phase": "Audit manager",
        "turn": 4,
        "turn_limit": 20,
        "elapsed_seconds": 12.6,
        "tool": "run_experiment",
        "ok": True,
    }
    encoded = json.dumps(event)
    assert "secret" not in encoded
    assert "private-model-id" not in encoded
    assert "private-provider" not in encoded


def test_public_activity_event_rejects_untrusted_names() -> None:
    running = _public_activity_event(
        {
            "actor": "falsifier",
            "event": "tool_call",
            "tool": "run_experiment",
            "budget": {},
        },
        sequence=1,
    )
    assert running["event"] == "tool_call"
    assert running["tool"] == "run_experiment"
    assert "ok" not in running

    event = _public_activity_event(
        {
            "actor": "unexpected-agent",
            "event": "private_reasoning",
            "tool": "read_region<script>",
            "budget": {},
        },
        sequence=1,
    )

    assert event["actor"] == "audit-manager"
    assert event["event"] == "progress"
    assert "tool" not in event


def test_ui_renders_live_activity_without_exposing_reasoning_or_using_unsafe_html() -> None:
    assert "Live agent activity" in HTML
    assert "renderActivityFeed(job.activity||[]" in HTML
    assert "run_experiment:['Run sandbox test'" in HTML
    assert "Selecting the next allowed evidence action" in HTML
    assert "splitFormulaSegments" in HTML
    assert "appendReadableNarrative($('diagnosis'),decision.explanation)" in HTML
    assert "appendFalsifierNarrative($('falsifier'),v,data.experiments||[])" in HTML
    assert "View complete falsifier explanation" in HTML
    assert "Formula referenced" in HTML
    assert ".innerHTML" not in HTML


def _split_formula_segments(value: str) -> list[dict[str, str]]:
    """Execute the browser's pure formula splitter without requiring a DOM."""

    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("Node.js is required to exercise the inline JavaScript formatter")

    start = HTML.index("function splitFormulaSegments(")
    end = HTML.index("\nfunction ", start + 1)
    function_source = HTML[start:end]
    declarations = "\n".join(
        line
        for line in HTML[:start].splitlines()
        if line.startswith("const ") and "FORMULA" in line.upper()
    )
    program = "\n".join(
        (
            declarations,
            function_source,
            f"process.stdout.write(JSON.stringify(splitFormulaSegments({json.dumps(value)})));",
        )
    )
    completed = subprocess.run(
        [node_binary, "-e", program],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert isinstance(result, list)
    return result


def test_formula_formatter_extracts_only_the_actual_excel_formula() -> None:
    formula = '=IF(AND(J6>=1,K6<>"Y"),0,IF(H6<0.95,0.6,1))'
    explanation = (
        f"The candidate formula is {formula}. "
        "Experiment 1 (J6=1, K6=N, H6=0.9) observed T6=EXCLUDED_CRITICAL. "
        "Experiment 2 (J6=1, K6=Y, H6=0.96) observed P6=1."
    )

    segments = _split_formula_segments(explanation)

    assert [segment["value"] for segment in segments if segment["type"] == "formula"] == [formula]
    assert "".join(segment["value"] for segment in segments) == explanation
