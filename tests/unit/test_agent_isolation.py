"""Static guardrails against policy-answer leakage into model-directed agents."""

from __future__ import annotations

import ast
from pathlib import Path

AGENT_MODULES = (
    "agent_loop.py",
    "agent_state.py",
    "agent_tools.py",
    "agentic.py",
    "falsifier.py",
    "workbook_tools.py",
    "experiment_worker.py",
)
FORBIDDEN_MODULES = {
    "advanced",
    "baseline",
    "benchmark",
    "evaluation",
    "policy",
    "public_benchmark",
}


def test_model_directed_runtime_does_not_import_answer_bearing_modules() -> None:
    package = Path(__file__).resolve().parents[2] / "src" / "formulawitness"
    violations: list[str] = []
    for filename in AGENT_MODULES:
        tree = ast.parse((package / filename).read_text(encoding="utf-8"), filename=filename)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported = node.module.lstrip(".").split(".")[0]
                if imported in FORBIDDEN_MODULES:
                    violations.append(f"{filename} imports {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported = alias.name.split(".")[-1]
                    if imported in FORBIDDEN_MODULES:
                        violations.append(f"{filename} imports {alias.name}")
    assert violations == []
