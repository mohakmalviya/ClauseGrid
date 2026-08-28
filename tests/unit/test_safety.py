from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from formulawitness.ooxml import MAIN, WorkbookRejected, inspect_safety

ROOT = Path(__file__).resolve().parents[2]


def test_pristine_workbook_is_accepted() -> None:
    result = inspect_safety(ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx")
    assert result["formula_count"] >= 9


def test_external_relationship_is_rejected_before_formula_execution(tmp_path: Path) -> None:
    workbook = tmp_path / "external.xlsx"
    relationships = b"""<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="x" Target="https://example.invalid/data.xlsx" TargetMode="External"/></Relationships>"""
    with ZipFile(workbook, "w", ZIP_DEFLATED) as archive:
        archive.writestr("_rels/.rels", relationships)
    with pytest.raises(WorkbookRejected, match="External relationships"):
        inspect_safety(workbook)


def test_macro_extension_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.xlsm"
    path.write_bytes(b"not a workbook")
    with pytest.raises(WorkbookRejected, match="ordinary .xlsx"):
        inspect_safety(path)


@pytest.mark.parametrize(
    "formula",
    (
        '=WEBSERVICE("https://example.invalid/data")',
        "=cmd|' /C whoami'!A0",
        "='[external.xlsx]Sheet1'!A1",
    ),
)
def test_unsafe_formula_on_non_calculation_sheet_is_rejected(tmp_path: Path, formula: str) -> None:
    source = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    workbook = tmp_path / "unsafe.xlsx"
    with ZipFile(source) as input_archive, ZipFile(workbook, "w", ZIP_DEFLATED) as output_archive:
        for info in input_archive.infolist():
            payload = input_archive.read(info)
            if info.filename == "xl/worksheets/sheet3.xml":
                root = ET.fromstring(payload)
                sheet_data = root.find(f"{{{MAIN}}}sheetData")
                assert sheet_data is not None
                row = ET.SubElement(sheet_data, f"{{{MAIN}}}row", {"r": "99"})
                cell = ET.SubElement(row, f"{{{MAIN}}}c", {"r": "A99"})
                node = ET.SubElement(cell, f"{{{MAIN}}}f")
                node.text = formula.removeprefix("=")
                payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            output_archive.writestr(info, payload)
    with pytest.raises(WorkbookRejected, match="DDE, or network-capable"):
        inspect_safety(workbook)
