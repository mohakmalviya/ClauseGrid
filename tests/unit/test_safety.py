from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from formulawitness.ooxml import WorkbookRejected, inspect_safety

ROOT = Path(__file__).resolve().parents[2]


def test_pristine_workbook_is_accepted() -> None:
    result = inspect_safety(ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx")
    assert result["formula_count"] == 9


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
