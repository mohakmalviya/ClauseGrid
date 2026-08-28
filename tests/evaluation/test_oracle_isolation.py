import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_repair_workflows_cannot_import_hidden_cases_or_oracle() -> None:
    for name in ("advanced.py", "baseline.py", "agent_worker.py"):
        imports = _imports(ROOT / "src/formulawitness" / name)
        assert not (
            {module.rsplit(".", 1)[-1] for module in imports}
            & {"benchmark", "oracle", "evaluation"}
        )


def test_hidden_oracle_is_lazy_loaded_after_agent_process() -> None:
    source = (ROOT / "src/formulawitness/evaluation.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_imports = {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "oracle" not in top_level_imports
    assert "benchmark" not in top_level_imports


def test_agent_runtime_cannot_import_sealed_evaluator(tmp_path: Path) -> None:
    script = (
        "import importlib.util,json;"
        "print(json.dumps({"
        "'sealed':importlib.util.find_spec('evals'),"
        "'oracle':importlib.util.find_spec('formulawitness.oracle')"
        "},default=str))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(completed.stdout) == {"sealed": None, "oracle": None}


def test_agent_file_capability_cannot_read_unstaged_secret(tmp_path: Path) -> None:
    public = tmp_path / "public.txt"
    secret = tmp_path / "sealed.txt"
    output = tmp_path / "output"
    public.write_text("public", encoding="utf-8")
    secret.write_text("sealed", encoding="utf-8")
    output.mkdir()
    script = (
        "from pathlib import Path;"
        "from formulawitness.path_guard import restrict_file_access;"
        f"restrict_file_access(readable_files=(Path({str(public)!r}),),"
        f"writable_roots=(Path({str(output)!r}),));"
        f"assert Path({str(public)!r}).read_text()=='public';"
        f"Path({str(secret)!r}).read_text()"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=output,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "FileCapabilityError" in completed.stderr
