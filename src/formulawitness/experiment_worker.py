"""Policy-agnostic subprocess for bounded workbook experiments."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from .formula import (
    FormulaError,
    evaluate_cells,
    json_value,
    normalize_override_value,
    validate_formula_dependency_graph,
    validate_formula_subset,
)
from .ooxml import calculation_cells, inspect_safety, workbook_formula_map, workbook_sheet_names

CELL_RE = re.compile(r"^[A-Z]{1,3}[1-9]\d*$")
MAX_OVERRIDES = 100
MAX_OBSERVATIONS = 100
MAX_FORMULA_OVERRIDES = 10


def _formula_hash(formula: str) -> str:
    return hashlib.sha256(formula.encode("utf-8")).hexdigest()


def _cell(value: Any) -> str:
    cell = str(value).replace("$", "").upper()
    if CELL_RE.fullmatch(cell) is None:
        raise ValueError(f"Invalid unqualified A1 cell address: {value}")
    return cell


def _sheet(requested: Any, available: tuple[str, ...]) -> str:
    matches = [name for name in available if name.casefold() == str(requested).casefold()]
    if len(matches) != 1:
        raise ValueError(
            f"Workbook sheet not found: {requested}. Available sheets: {', '.join(available)}"
        )
    return matches[0]


def _override_reference(value: Any, active_sheet: str, available: tuple[str, ...]) -> str:
    raw = str(value).replace("$", "")
    if "!" not in raw:
        return _cell(raw)
    requested_sheet, raw_cell = raw.rsplit("!", 1)
    actual_sheet = _sheet(requested_sheet.strip("'"), available)
    cell = _cell(raw_cell)
    if actual_sheet.casefold() == active_sheet.casefold():
        return cell
    return f"{actual_sheet.upper()}!{cell}"


def _bounded_mapping(
    value: Any,
    limit: int,
    label: str,
    *,
    active_sheet: str,
    available_sheets: tuple[str, ...],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object keyed by cell address")
    if len(value) > limit:
        raise ValueError(f"{label} exceeds the {limit}-cell limit")
    return {
        _override_reference(cell, active_sheet, available_sheets): cell_value
        for cell, cell_value in value.items()
    }


def main() -> int:
    started = time.perf_counter()
    try:
        request = json.loads(sys.stdin.read())
        workbook = Path(request["workbook"]).resolve()
        from .path_guard import restrict_file_access

        restrict_file_access(readable_files=(workbook,), writable_roots=(Path.cwd(),))
        safety = inspect_safety(workbook)
        sheet_names = workbook_sheet_names(workbook)
        sheet = _sheet(request["sheet"], sheet_names)
        values, formulas = calculation_cells(workbook, sheet)
        overrides = _bounded_mapping(
            request.get("overrides", {}),
            MAX_OVERRIDES,
            "overrides",
            active_sheet=sheet,
            available_sheets=sheet_names,
        )
        overrides = {cell: normalize_override_value(value) for cell, value in overrides.items()}
        workbook_formulas = workbook_formula_map(workbook)
        all_formula_references = {reference.upper() for reference in workbook_formulas}
        for cell in overrides:
            qualified_cell = cell if "!" in cell else f"{sheet}!{cell}"
            if qualified_cell.upper() in all_formula_references:
                raise ValueError(
                    f"Value override cannot replace formula cell {cell}; use formula_overrides"
                )
            if cell not in values:
                raise ValueError(f"Value override target does not exist: {cell}")

        raw_observations = request.get("observations", [])
        if not isinstance(raw_observations, list) or not raw_observations:
            raise ValueError("observations must be a non-empty list")
        if len(raw_observations) > MAX_OBSERVATIONS:
            raise ValueError(f"observations exceeds the {MAX_OBSERVATIONS}-cell limit")
        observations = [_cell(cell) for cell in raw_observations]

        raw_formula_overrides = request.get("formula_overrides", [])
        if not isinstance(raw_formula_overrides, list):
            raise TypeError("formula_overrides must be a list")
        if len(raw_formula_overrides) > MAX_FORMULA_OVERRIDES:
            raise ValueError(f"formula_overrides exceeds the {MAX_FORMULA_OVERRIDES}-formula limit")
        staged_formulas = dict(formulas)
        applied: list[str] = []
        for item in raw_formula_overrides:
            if not isinstance(item, dict):
                raise TypeError("Each formula override must be an object")
            cell = _cell(item.get("cell"))
            current = staged_formulas.get(cell)
            if current is None:
                raise ValueError(f"Formula override target is not a formula cell: {cell}")
            if _formula_hash(current) != item.get("old_formula_sha256"):
                raise ValueError(f"Old-formula hash guard failed for {cell}")
            candidate = str(item.get("new_formula", ""))
            if not candidate.startswith("="):
                raise FormulaError(f"Formula override must start with '=' for {cell}")
            validate_formula_subset(candidate)
            staged_formulas[cell] = candidate
            applied.append(cell)

        candidate_workbook_formulas = dict(workbook_formulas)
        candidate_workbook_formulas.update(
            {f"{sheet}!{cell}": formula for cell, formula in staged_formulas.items()}
        )
        validate_formula_dependency_graph(candidate_workbook_formulas, sheet_names)

        calculated, dependencies = evaluate_cells(
            values, staged_formulas, overrides, active_sheet=sheet
        )
        observed: dict[str, Any] = {}
        for cell in observations:
            if cell in calculated:
                observed[cell] = calculated[cell]
            elif cell in overrides:
                observed[cell] = json_value(overrides[cell])
            elif cell in values:
                observed[cell] = json_value(values[cell])
            else:
                raise ValueError(f"Observed cell does not exist: {cell}")
        response = {
            "ok": True,
            "workbook_sha256": safety["sha256"],
            "sheet": sheet,
            "observations": observed,
            "dependencies": {cell: dependencies.get(cell, []) for cell in observations},
            "formula_sha256": {
                cell: _formula_hash(staged_formulas[cell])
                for cell in observations
                if cell in staged_formulas
            },
            "applied_formula_overrides": applied,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001 - process boundary must fail closed
        response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    sys.stdout.write(json.dumps(response, sort_keys=True))
    return 0 if response["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
