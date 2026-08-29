from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from formulawitness.ooxml import MAIN, changed_workbook_formulas, patch_workbook, sha256_file
from formulawitness.workbook_tools import (
    inspect_dependencies,
    list_formulas,
    read_region,
    workbook_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
WORKBOOK = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"


def test_manifest_discovers_sheets_and_used_ranges_without_a_template() -> None:
    manifest = workbook_manifest(WORKBOOK)
    sheets = {sheet.name: sheet for sheet in manifest.sheets}

    assert manifest.workbook_sha256
    assert {"RebateCalc", "TierSchedule"} <= set(sheets)
    assert sheets["RebateCalc"].used_range is not None
    assert sheets["RebateCalc"].formula_count >= 9
    assert sheets["TierSchedule"].formula_count == 0


def test_read_region_returns_sheet_qualified_cells_and_formulas() -> None:
    cells = read_region(WORKBOOK, "rebatecalc", "L6:P6")

    assert [cell.reference for cell in cells] == [
        "RebateCalc!L6",
        "RebateCalc!M6",
        "RebateCalc!N6",
        "RebateCalc!O6",
        "RebateCalc!P6",
    ]
    assert all(cell.formula and cell.formula.startswith("=") for cell in cells)


def test_read_region_rejects_unbounded_or_descending_requests() -> None:
    with pytest.raises(ValueError, match="cell limit"):
        read_region(WORKBOOK, "RebateCalc", "A1:ZZ100")
    with pytest.raises(ValueError, match="Descending"):
        read_region(WORKBOOK, "RebateCalc", "P6:L6")


def test_formula_listing_is_fully_qualified_and_filterable_by_sheet() -> None:
    formulas = list_formulas(WORKBOOK, "RebateCalc")

    assert "RebateCalc!P6" in formulas
    assert all(reference.startswith("RebateCalc!") for reference in formulas)
    assert list_formulas(WORKBOOK, "TierSchedule") == {}


def test_dependency_inspection_qualifies_local_and_cross_sheet_references() -> None:
    inspection = inspect_dependencies(WORKBOOK, ["rebatecalc!S6"])

    assert inspection.roots == ("RebateCalc!S6",)
    assert "RebateCalc!R6" in inspection.direct_dependencies["RebateCalc!S6"]
    assert "RebateCalc!L6" in inspection.transitive_dependencies
    assert "TierSchedule!A5" in inspection.transitive_dependencies
    assert "TierSchedule!B8" in inspection.transitive_dependencies


def test_guarded_patch_accepts_sheet_qualified_targets_and_preserves_source(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "patched.xlsx"
    source_hash = sha256_file(WORKBOOK)
    old_formula = list_formulas(WORKBOOK)["Checks!B5"]

    patch_workbook(
        WORKBOOK,
        destination,
        {"Checks!B5": (old_formula, "=1")},
        [["case"]],
        [["report"]],
    )

    assert sha256_file(WORKBOOK) == source_hash
    assert changed_workbook_formulas(WORKBOOK, destination) == {"Checks!B5": (old_formula, "=1")}
    with ZipFile(destination) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        calc = workbook.find(f"{{{MAIN}}}calcPr")
        assert calc is not None
        assert calc.attrib["calcMode"] == "auto"
        assert calc.attrib["fullCalcOnLoad"] == "1"
        assert calc.attrib["forceFullCalc"] == "1"
        assert "xl/calcChain.xml" not in archive.namelist()
