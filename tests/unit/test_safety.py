from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZIP_LZMA, ZipFile

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


def test_duplicate_package_parts_are_rejected(tmp_path: Path) -> None:
    source = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    workbook = tmp_path / "duplicate.xlsx"
    with ZipFile(source) as input_archive, ZipFile(workbook, "w", ZIP_DEFLATED) as output_archive:
        workbook_xml = input_archive.read("xl/workbook.xml")
        for info in input_archive.infolist():
            output_archive.writestr(info, input_archive.read(info))
        with pytest.warns(UserWarning, match="Duplicate name"):
            output_archive.writestr("xl/workbook.xml", workbook_xml)

    with pytest.raises(WorkbookRejected, match="duplicate part names"):
        inspect_safety(workbook)


def test_defined_names_and_array_formulas_are_rejected(tmp_path: Path) -> None:
    source = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    for mode, expected in (
        ("defined-name", "Defined names"),
        ("array-formula", "array"),
    ):
        workbook = tmp_path / f"{mode}.xlsx"
        array_modified = False
        with (
            ZipFile(source) as input_archive,
            ZipFile(workbook, "w", ZIP_DEFLATED) as output_archive,
        ):
            for info in input_archive.infolist():
                payload = input_archive.read(info)
                if mode == "defined-name" and info.filename == "xl/workbook.xml":
                    root = ET.fromstring(payload)
                    names = ET.SubElement(root, f"{{{MAIN}}}definedNames")
                    item = ET.SubElement(names, f"{{{MAIN}}}definedName", {"name": "Hidden"})
                    item.text = 'WEBSERVICE("https://example.invalid")'
                    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                if (
                    mode == "array-formula"
                    and not array_modified
                    and info.filename.startswith("xl/worksheets/")
                ):
                    root = ET.fromstring(payload)
                    formula = root.find(".//x:f", {"x": MAIN})
                    if formula is not None:
                        formula.attrib["t"] = "array"
                        formula.attrib["ref"] = "L6:L7"
                        payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                        array_modified = True
                output_archive.writestr(info, payload)
        if mode == "array-formula":
            assert array_modified

        with pytest.raises(WorkbookRejected, match=expected):
            inspect_safety(workbook)


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


def test_workbook_xml_entity_declarations_are_rejected_before_parsing(tmp_path: Path) -> None:
    source = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    workbook = tmp_path / "entity.xlsx"
    with ZipFile(source) as input_archive, ZipFile(workbook, "w", ZIP_DEFLATED) as output:
        for info in input_archive.infolist():
            payload = input_archive.read(info)
            if info.filename == "xl/workbook.xml":
                declaration = b'<!DOCTYPE workbook [<!ENTITY amplify "entity">]>'
                payload = payload.replace(b"?>", b"?>" + declaration, 1)
            output.writestr(info, payload)

    with pytest.raises(WorkbookRejected, match="XML declarations"):
        inspect_safety(workbook)


def test_utf16_xml_entity_declarations_cannot_bypass_the_xml_profile(tmp_path: Path) -> None:
    source = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    workbook = tmp_path / "utf16-entity.xlsx"
    malicious = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<!DOCTYPE workbook [<!ENTITY amplify "expanded">]>'
        f'<workbook xmlns="{MAIN}">&amplify;</workbook>'
    ).encode("utf-16")
    with ZipFile(source) as input_archive, ZipFile(workbook, "w", ZIP_DEFLATED) as output:
        for info in input_archive.infolist():
            payload = malicious if info.filename == "xl/workbook.xml" else input_archive.read(info)
            output.writestr(info, payload)

    with pytest.raises(WorkbookRejected, match="UTF-8 encoding"):
        inspect_safety(workbook)


def test_entity_declaration_in_an_optional_xml_part_is_rejected(tmp_path: Path) -> None:
    source = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    workbook = tmp_path / "styles-entity.xlsx"
    changed = False
    with ZipFile(source) as input_archive, ZipFile(workbook, "w", ZIP_DEFLATED) as output:
        for info in input_archive.infolist():
            payload = input_archive.read(info)
            if info.filename == "xl/styles.xml":
                declaration = b'<!DOCTYPE styleSheet [<!ENTITY amplify "expanded">]>'
                payload = payload.replace(b"?>", b"?>" + declaration, 1)
                changed = True
            output.writestr(info, payload)
    assert changed

    with pytest.raises(WorkbookRejected, match="XML declarations.*styles.xml"):
        inspect_safety(workbook)


@pytest.mark.parametrize("compression", (ZIP_BZIP2, ZIP_LZMA))
def test_non_deflate_zip_compression_is_rejected_before_part_decode(
    tmp_path: Path, compression: int
) -> None:
    source = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    workbook = tmp_path / f"compression-{compression}.xlsx"
    with ZipFile(source) as input_archive, ZipFile(workbook, "w") as output:
        for info in input_archive.infolist():
            payload = input_archive.read(info)
            method = compression if info.filename == "xl/styles.xml" else ZIP_DEFLATED
            output.writestr(info.filename, payload, compress_type=method)

    with pytest.raises(WorkbookRejected, match="unsupported compression method"):
        inspect_safety(workbook)


@pytest.mark.parametrize(
    "fragment",
    (
        (
            f'<conditionalFormatting xmlns="{MAIN}" sqref="A1">'
            '<cfRule type="expression" priority="1">'
            '<formula>LEN(WEBSERVICE("https://example.invalid"))&gt;0</formula>'
            "</cfRule></conditionalFormatting>"
        ),
        (
            f'<dataValidations xmlns="{MAIN}" count="1">'
            '<dataValidation type="custom" sqref="A1">'
            '<formula1>LEN(WEBSERVICE("https://example.invalid"))&gt;0</formula1>'
            "</dataValidation></dataValidations>"
        ),
        (
            f'<extLst xmlns="{MAIN}" xmlns:x14="http://schemas.microsoft.com/office/'
            'spreadsheetml/2009/9/main" '
            'xmlns:xm="http://schemas.microsoft.com/office/excel/2006/main">'
            '<ext uri="test"><x14:cfRule type="expression" priority="1">'
            '<xm:f>LEN(WEBSERVICE("https://example.invalid"))&gt;0</xm:f>'
            "</x14:cfRule></ext></extLst>"
        ),
    ),
)
def test_formula_bearing_worksheet_features_are_rejected(tmp_path: Path, fragment: str) -> None:
    source = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    workbook = tmp_path / "formula-bearing-feature.xlsx"
    changed = False
    with ZipFile(source) as input_archive, ZipFile(workbook, "w", ZIP_DEFLATED) as output:
        for info in input_archive.infolist():
            payload = input_archive.read(info)
            if not changed and info.filename.startswith("xl/worksheets/"):
                root = ET.fromstring(payload)
                root.append(ET.fromstring(fragment))
                payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                changed = True
            output.writestr(info, payload)
    assert changed

    with pytest.raises(WorkbookRejected, match="formula-bearing content"):
        inspect_safety(workbook)


def test_ooxml_cell_records_must_use_addresses_inside_the_excel_grid(tmp_path: Path) -> None:
    source = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    workbook = tmp_path / "invalid-address.xlsx"
    changed = False
    with ZipFile(source) as input_archive, ZipFile(workbook, "w", ZIP_DEFLATED) as output:
        for info in input_archive.infolist():
            payload = input_archive.read(info)
            if not changed and info.filename.startswith("xl/worksheets/"):
                root = ET.fromstring(payload)
                cell = root.find(".//x:c", {"x": MAIN})
                if cell is not None:
                    cell.set("r", "A0")
                    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    changed = True
            output.writestr(info, payload)
    assert changed

    with pytest.raises(WorkbookRejected, match="outside the Excel grid"):
        inspect_safety(workbook)


def test_non_finite_numeric_cells_are_rejected(tmp_path: Path) -> None:
    source = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    workbook = tmp_path / "non-finite.xlsx"
    changed = False
    with ZipFile(source) as input_archive, ZipFile(workbook, "w", ZIP_DEFLATED) as output:
        for info in input_archive.infolist():
            payload = input_archive.read(info)
            if not changed and info.filename.startswith("xl/worksheets/"):
                root = ET.fromstring(payload)
                for cell in root.findall(".//x:c", {"x": MAIN}):
                    value = cell.find("x:v", {"x": MAIN})
                    if value is not None and cell.attrib.get("t") not in {"s", "str", "b"}:
                        value.text = "NaN"
                        payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                        changed = True
                        break
            output.writestr(info, payload)
    assert changed

    with pytest.raises(WorkbookRejected, match="must be finite"):
        inspect_safety(workbook)


def test_relocated_active_content_relationship_type_is_rejected(tmp_path: Path) -> None:
    source = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    workbook = tmp_path / "relocated-connection.xlsx"
    with ZipFile(source) as input_archive, ZipFile(workbook, "w", ZIP_DEFLATED) as output:
        for info in input_archive.infolist():
            payload = input_archive.read(info)
            if info.filename == "xl/_rels/workbook.xml.rels":
                root = ET.fromstring(payload)
                namespace = root.tag.partition("}")[0].removeprefix("{")
                ET.SubElement(
                    root,
                    f"{{{namespace}}}Relationship",
                    {
                        "Id": "rRelocatedConnection",
                        "Type": (
                            "http://schemas.openxmlformats.org/officeDocument/2006/"
                            "relationships/connections"
                        ),
                        "Target": "/custom/relocated-control.xml",
                    },
                )
                payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            output.writestr(info, payload)

    with pytest.raises(WorkbookRejected, match="relationship type.*connections"):
        inspect_safety(workbook)


def test_unknown_part_content_type_is_rejected_even_at_a_relocated_path(tmp_path: Path) -> None:
    source = ROOT / "workbooks/reference/supplier_rebate_pristine.xlsx"
    workbook = tmp_path / "relocated-active-part.xlsx"
    with ZipFile(source) as input_archive, ZipFile(workbook, "w", ZIP_DEFLATED) as output:
        for info in input_archive.infolist():
            payload = input_archive.read(info)
            if info.filename == "[Content_Types].xml":
                root = ET.fromstring(payload)
                namespace = root.tag.partition("}")[0].removeprefix("{")
                ET.SubElement(
                    root,
                    f"{{{namespace}}}Override",
                    {
                        "PartName": "/custom/payload.bin",
                        "ContentType": "application/vnd.ms-office.activeX",
                    },
                )
                payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            output.writestr(info, payload)
        output.writestr("custom/payload.bin", b"not executable in this test")

    with pytest.raises(WorkbookRejected, match="outside the .*safe profile"):
        inspect_safety(workbook)
