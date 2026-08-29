"""Generic, read-only workbook discovery tools for model-directed investigation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .formula import FormulaError, referenced_cells
from .ooxml import (
    inspect_safety,
    sheet_cells,
    workbook_formula_map,
    workbook_sheet_names,
)

CELL_ADDRESS_RE = re.compile(r"^(?P<column>[A-Z]{1,3})(?P<row>[1-9]\d*)$")
REGION_RE = re.compile(
    r"^(?P<first_column>[A-Z]{1,3})(?P<first_row>[1-9]\d*)"
    r"(?::(?P<last_column>[A-Z]{1,3})(?P<last_row>[1-9]\d*))?$"
)
MAX_REGION_CELLS = 1_000
MAX_TOOL_TEXT_CHARS = 250_000
MAX_FORMULAS = 2_000
MAX_FORMULA_CHARS = 8_192


@dataclass(frozen=True)
class SheetManifest:
    name: str
    used_range: str | None
    populated_cell_count: int
    formula_count: int


@dataclass(frozen=True)
class WorkbookManifest:
    workbook_sha256: str
    sheets: tuple[SheetManifest, ...]


@dataclass(frozen=True)
class CellObservation:
    reference: str
    value: Any
    formula: str | None


@dataclass(frozen=True)
class DependencyInspection:
    roots: tuple[str, ...]
    direct_dependencies: dict[str, tuple[str, ...]]
    transitive_dependencies: tuple[str, ...]


def _column_index(column: str) -> int:
    result = 0
    for character in column:
        result = result * 26 + ord(character) - 64
    return result


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _address_parts(address: str) -> tuple[int, int]:
    match = CELL_ADDRESS_RE.fullmatch(address.upper())
    if match is None:
        raise ValueError(f"Invalid A1 cell address: {address}")
    return _column_index(match.group("column")), int(match.group("row"))


def _sheet_name(requested: str, available: tuple[str, ...]) -> str:
    matches = [name for name in available if name.casefold() == requested.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Workbook sheet not found: {requested}")
    return matches[0]


def _region_addresses(region: str) -> list[str]:
    match = REGION_RE.fullmatch(region.strip().upper())
    if match is None:
        raise ValueError(f"Invalid A1 region: {region}")
    first_column = _column_index(match.group("first_column"))
    first_row = int(match.group("first_row"))
    last_column = _column_index(match.group("last_column") or match.group("first_column"))
    last_row = int(match.group("last_row") or match.group("first_row"))
    if last_column < first_column or last_row < first_row:
        raise ValueError("Descending workbook regions are unsupported")
    size = (last_column - first_column + 1) * (last_row - first_row + 1)
    if size > MAX_REGION_CELLS:
        raise ValueError(f"Workbook region exceeds the {MAX_REGION_CELLS}-cell limit")
    return [
        f"{_column_name(column)}{row}"
        for row in range(first_row, last_row + 1)
        for column in range(first_column, last_column + 1)
    ]


def workbook_manifest(path: Path) -> WorkbookManifest:
    """Describe workbook sheets and used ranges without assuming a template or layout."""

    safety = inspect_safety(path)
    sheets: list[SheetManifest] = []
    for name in workbook_sheet_names(path):
        values, formulas = sheet_cells(path, name)
        populated = set(values) | set(formulas)
        if populated:
            coordinates = [_address_parts(address) for address in populated]
            columns = [column for column, _ in coordinates]
            rows = [row for _, row in coordinates]
            used_range = (
                f"{_column_name(min(columns))}{min(rows)}:{_column_name(max(columns))}{max(rows)}"
            )
        else:
            used_range = None
        sheets.append(
            SheetManifest(
                name=name,
                used_range=used_range,
                populated_cell_count=len(populated),
                formula_count=len(formulas),
            )
        )
    return WorkbookManifest(str(safety["sha256"]), tuple(sheets))


def read_region(path: Path, sheet: str, region: str) -> tuple[CellObservation, ...]:
    """Read a bounded region as sheet-qualified values and formulas."""

    inspect_safety(path)
    actual_sheet = _sheet_name(sheet, workbook_sheet_names(path))
    values, formulas = sheet_cells(path, actual_sheet)
    result = tuple(
        CellObservation(
            reference=f"{actual_sheet}!{address}",
            value=values.get(address),
            formula=formulas.get(address),
        )
        for address in _region_addresses(region)
    )
    text_size = sum(
        len(str(item.value)) + (0 if item.formula is None else len(item.formula)) for item in result
    )
    if text_size > MAX_TOOL_TEXT_CHARS:
        raise ValueError("Workbook region exceeds the tool-result text limit")
    return result


def list_formulas(path: Path, sheet: str | None = None) -> dict[str, str]:
    """Return formulas keyed by fully qualified ``Sheet!A1`` references."""

    inspect_safety(path)
    formulas = workbook_formula_map(path)
    if len(formulas) > MAX_FORMULAS:
        raise ValueError(f"Workbook exceeds the {MAX_FORMULAS}-formula discovery limit")
    if any(len(formula) > MAX_FORMULA_CHARS for formula in formulas.values()):
        raise ValueError("Workbook formula exceeds the discovery text limit")
    if sum(len(key) + len(value) for key, value in formulas.items()) > MAX_TOOL_TEXT_CHARS:
        raise ValueError("Workbook formulas exceed the tool-result text limit")
    if sheet is None:
        return formulas
    actual_sheet = _sheet_name(sheet, workbook_sheet_names(path))
    prefix = f"{actual_sheet}!"
    return {
        reference: formula
        for reference, formula in formulas.items()
        if reference.startswith(prefix)
    }


def inspect_dependencies(path: Path, roots: tuple[str, ...] | list[str]) -> DependencyInspection:
    """Return a backward, sheet-qualified dependency graph for selected formula cells."""

    if not roots:
        raise ValueError("At least one dependency root is required")
    formulas = list_formulas(path)
    canonical_formulas = {reference.upper(): reference for reference in formulas}
    sheets = workbook_sheet_names(path)
    canonical_sheets = {name.upper(): name for name in sheets}

    def qualify(reference: str, current_sheet: str | None = None) -> str:
        raw = reference.replace("$", "").replace("'", "").upper()
        if "!" in raw:
            raw_sheet, address = raw.split("!", 1)
            display_sheet = canonical_sheets.get(raw_sheet, raw_sheet)
        else:
            if current_sheet is None:
                raise ValueError(f"Dependency root must be sheet-qualified: {reference}")
            display_sheet, address = current_sheet, raw
        _address_parts(address)
        canonical = f"{display_sheet}!{address}"
        return canonical_formulas.get(canonical.upper(), canonical)

    qualified_roots = tuple(qualify(root) for root in roots)
    direct: dict[str, tuple[str, ...]] = {}
    seen: set[str] = set()
    frontier = list(qualified_roots)
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        formula = formulas.get(current)
        if formula is None:
            direct[current] = ()
            continue
        current_sheet = current.split("!", 1)[0]
        try:
            dependencies = tuple(
                qualify(reference, current_sheet) for reference in referenced_cells(formula)
            )
        except FormulaError as exc:
            raise FormulaError(f"Could not inspect dependencies for {current}: {exc}") from exc
        direct[current] = dependencies
        frontier.extend(reference for reference in dependencies if reference not in seen)
    return DependencyInspection(qualified_roots, direct, tuple(sorted(seen - set(qualified_roots))))
