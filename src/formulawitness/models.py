"""Typed, serializable records used throughout ClauseGrid."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True)
class SourceSpan:
    document_sha256: str
    page: int
    start_char: int
    end_char: int
    exact_quote: str
    quote_sha256: str


@dataclass(frozen=True)
class Rule:
    rule_id: str
    title: str
    target: str
    status: Literal["EXACT", "AMBIGUOUS", "CONFLICT", "UNSUPPORTED"]
    evidence: SourceSpan
    boundaries: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    ambiguity_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuleIR:
    """Executable policy operation derived from one or more cited rules."""

    target: str
    operation: str
    rule_ids: tuple[str, ...]
    parameters: dict[str, JsonValue]


@dataclass(frozen=True)
class TestCase:
    case_id: str
    category: str
    inputs: dict[str, JsonValue]
    provenance_rule_ids: tuple[str, ...]
    split: Literal["VISIBLE", "HELD_OUT"] = "VISIBLE"


@dataclass(frozen=True)
class Patch:
    cell: str
    old_formula: str
    new_formula: str
    rule_ids: tuple[str, ...]
    rationale: str


@dataclass
class AuditResult:
    run_id: str
    method: str
    source_workbook: str
    source_sha256: str
    rules_sha256: str
    tests: list[dict[str, Any]] = field(default_factory=list)
    suspicious_cells: list[dict[str, Any]] = field(default_factory=list)
    patches: list[Patch] = field(default_factory=list)
    decision: Literal["REPAIR", "NO_CHANGE", "ABSTAIN", "REJECT"] = "ABSTAIN"
    approval_hash: str | None = None
    output_workbook: str | None = None
    artifact_dir: str | None = None
    budget: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionResult:
    workbook_sha256: str
    inputs: dict[str, JsonValue]
    outputs: dict[str, JsonValue]
    formulas: dict[str, str]
    dependencies: dict[str, list[str]]
    elapsed_ms: int


@dataclass(frozen=True)
class FormulaOverride:
    """One guarded formula substitution used only inside a sandbox experiment."""

    cell: str
    old_formula_sha256: str
    new_formula: str


@dataclass(frozen=True)
class SandboxExperimentResult:
    workbook_sha256: str
    sheet: str
    observations: dict[str, JsonValue]
    dependencies: dict[str, list[str]]
    formula_sha256: dict[str, str]
    applied_formula_overrides: tuple[str, ...]
    elapsed_ms: int


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())
