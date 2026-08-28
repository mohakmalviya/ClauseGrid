"""Safe, narrow OOXML inspection and minimal formula patching."""

from __future__ import annotations

import hashlib
import re
import zipfile
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"x": MAIN, "r": REL, "pr": PKG_REL, "ct": CONTENT}
ET.register_namespace("", MAIN)
ET.register_namespace("r", REL)


class WorkbookRejected(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_safety(path: Path, max_uncompressed: int = 25_000_000) -> dict[str, Any]:
    if path.suffix.lower() != ".xlsx":
        raise WorkbookRejected("Only ordinary .xlsx workbooks are accepted")
    if not path.is_file():
        raise WorkbookRejected(f"Workbook not found: {path}")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > 1000 or sum(info.file_size for info in infos) > max_uncompressed:
            raise WorkbookRejected("Workbook package exceeds the safety limit")
        names = {info.filename.lower() for info in infos}
        forbidden = (
            "vbaproject.bin",
            "xl/externallinks/",
            "xl/embeddings/",
            "xl/activex/",
            "xl/connections.xml",
            "xl/querytables/",
        )
        matches = sorted(name for name in names if any(item in name for item in forbidden))
        if matches:
            raise WorkbookRejected(f"Unsupported active or external content: {matches[0]}")
        for info in infos:
            if info.filename.endswith(".rels"):
                root = ET.fromstring(archive.read(info))
                for relationship in root:
                    if relationship.attrib.get("TargetMode", "").lower() == "external":
                        raise WorkbookRejected("External relationships are not accepted")
        formulas = formula_map(path, "RebateCalc")
        volatile = re.compile(
            r"\b(?:INDIRECT|OFFSET|NOW|TODAY|RAND|RANDBETWEEN)\s*\(", re.IGNORECASE
        )
        unsafe = [cell for cell, formula in formulas.items() if volatile.search(formula)]
        if unsafe:
            raise WorkbookRejected(f"Volatile formulas are unsupported: {', '.join(unsafe)}")
    return {"sha256": sha256_file(path), "entries": len(infos), "formula_count": len(formulas)}


def _sheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {rel.attrib["Id"]: rel.attrib["Target"].lstrip("/") for rel in relationships}
    result: dict[str, str] = {}
    sheets = workbook.find("x:sheets", NS)
    if sheets is None:
        raise WorkbookRejected("Workbook sheet manifest is missing")
    for sheet in sheets:
        target = targets[sheet.attrib[f"{{{REL}}}id"]]
        result[sheet.attrib["name"]] = target if target.startswith("xl/") else f"xl/{target}"
    return result


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.iter(f"{{{MAIN}}}t")) for item in root]


def sheet_cells(path: Path, sheet_name: str) -> tuple[dict[str, Any], dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        target = _sheet_paths(archive).get(sheet_name)
        if not target:
            raise WorkbookRejected(f"Required sheet missing: {sheet_name}")
        root = ET.fromstring(archive.read(target))
        strings = _shared_strings(archive)
        values: dict[str, Any] = {}
        formulas: dict[str, str] = {}
        for cell in root.findall(".//x:c", NS):
            address = cell.attrib.get("r", "").upper()
            formula = cell.find("x:f", NS)
            value = cell.find("x:v", NS)
            if formula is not None and formula.text is not None:
                formulas[address] = "=" + formula.text
            if value is None or value.text is None:
                values[address] = None
                continue
            kind = cell.attrib.get("t")
            if kind == "s":
                values[address] = strings[int(value.text)]
            elif kind in {"str", "inlineStr"}:
                values[address] = value.text
            elif kind == "b":
                values[address] = value.text == "1"
            else:
                number = float(value.text)
                values[address] = int(number) if number.is_integer() else number
        return values, formulas


def formula_map(path: Path, sheet_name: str = "RebateCalc") -> dict[str, str]:
    return sheet_cells(path, sheet_name)[1]


def _inline_cell(address: str, value: Any, style: int | None = None) -> ET.Element:
    attributes = {"r": address, "t": "inlineStr"}
    if style is not None:
        attributes["s"] = str(style)
    cell = ET.Element(f"{{{MAIN}}}c", attributes)
    inline = ET.SubElement(cell, f"{{{MAIN}}}is")
    text = ET.SubElement(inline, f"{{{MAIN}}}t")
    text.text = "" if value is None else str(value)
    return cell


def _column_name(index: int) -> str:
    value = index + 1
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _make_sheet(rows: Iterable[Iterable[Any]], widths: list[float]) -> bytes:
    root = ET.Element(f"{{{MAIN}}}worksheet")
    views = ET.SubElement(root, f"{{{MAIN}}}sheetViews")
    view = ET.SubElement(views, f"{{{MAIN}}}sheetView", {"workbookViewId": "0"})
    ET.SubElement(
        view,
        f"{{{MAIN}}}pane",
        {"ySplit": "1", "topLeftCell": "A2", "activePane": "bottomLeft", "state": "frozen"},
    )
    columns = ET.SubElement(root, f"{{{MAIN}}}cols")
    for index, width in enumerate(widths, start=1):
        ET.SubElement(
            columns,
            f"{{{MAIN}}}col",
            {"min": str(index), "max": str(index), "width": str(width), "customWidth": "1"},
        )
    sheet_data = ET.SubElement(root, f"{{{MAIN}}}sheetData")
    for row_index, row_values in enumerate(rows, start=1):
        row_attributes = {"r": str(row_index)}
        if row_index == 1:
            row_attributes.update({"ht": "26", "customHeight": "1"})
        row = ET.SubElement(sheet_data, f"{{{MAIN}}}row", row_attributes)
        for column_index, value in enumerate(row_values):
            row.append(
                _inline_cell(
                    f"{_column_name(column_index)}{row_index}",
                    value,
                    33 if row_index == 1 else None,
                )
            )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _serialize_package_manifest(root: ET.Element, namespace: str) -> bytes:
    """Serialize package manifests with the unprefixed namespace OpenXML expects."""
    text = ET.tostring(root, encoding="unicode", xml_declaration=False)
    match = re.match(r"<(?P<prefix>ns\d+):", text)
    if match is None:
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)
    prefix = match.group("prefix")
    text = text.replace(f"<{prefix}:", "<").replace(f"</{prefix}:", "</")
    text = text.replace(f' xmlns:{prefix}="{namespace}"', f' xmlns="{namespace}"')
    return b'<?xml version="1.0" encoding="utf-8"?>' + text.encode("utf-8")


def patch_workbook(
    source: Path,
    destination: Path,
    patches: dict[str, tuple[str, str]],
    counterexample_rows: list[list[Any]],
    report_rows: list[list[Any]],
) -> None:
    """Apply validated formula patches and add evidence sheets to a copied package."""
    inspect_safety(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as input_zip:
        names = input_zip.namelist()
        sheet_paths = _sheet_paths(input_zip)
        calc_path = sheet_paths["RebateCalc"]
        calc_root = ET.fromstring(input_zip.read(calc_path))
        cells = {cell.attrib.get("r", "").upper(): cell for cell in calc_root.findall(".//x:c", NS)}
        for address, (expected_old, new_formula) in patches.items():
            cell = cells.get(address.upper())
            if cell is None:
                raise WorkbookRejected(f"Patch target missing: {address}")
            formula_node = cell.find("x:f", NS)
            current = "=" + (formula_node.text or "") if formula_node is not None else ""
            if current != expected_old:
                raise WorkbookRejected(f"Old-formula guard failed for {address}")
            assert formula_node is not None
            formula_node.text = new_formula.removeprefix("=")
            cached = cell.find("x:v", NS)
            if cached is not None:
                cell.remove(cached)

        workbook_root = ET.fromstring(input_zip.read("xl/workbook.xml"))
        rels_root = ET.fromstring(input_zip.read("xl/_rels/workbook.xml.rels"))
        content_root = ET.fromstring(input_zip.read("[Content_Types].xml"))
        sheets_node = workbook_root.find("x:sheets", NS)
        assert sheets_node is not None
        next_sheet_id = max(int(sheet.attrib["sheetId"]) for sheet in sheets_node) + 1
        existing_targets = {rel.attrib["Target"].lstrip("/") for rel in rels_root}
        sheet_number = 1
        while (
            f"xl/worksheets/sheet{sheet_number}.xml" in existing_targets
            or f"xl/worksheets/sheet{sheet_number}.xml" in names
        ):
            sheet_number += 1

        additions: dict[str, bytes] = {}
        for name, rows, widths in (
            ("Counterexamples", counterexample_rows, [12, 24, 24, 12, 20, 52, 34, 34]),
            ("FormulaWitness_Report", report_rows, [30, 84]),
        ):
            rid = f"rIdFormulaWitness{sheet_number}"
            target = f"xl/worksheets/sheet{sheet_number}.xml"
            ET.SubElement(
                sheets_node,
                f"{{{MAIN}}}sheet",
                {"name": name, "sheetId": str(next_sheet_id), f"{{{REL}}}id": rid},
            )
            ET.SubElement(
                rels_root,
                f"{{{PKG_REL}}}Relationship",
                {
                    "Id": rid,
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
                    "Target": f"/{target}",
                },
            )
            ET.SubElement(
                content_root,
                f"{{{CONTENT}}}Override",
                {
                    "PartName": f"/{target}",
                    "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
                },
            )
            additions[target] = _make_sheet(rows, widths)
            next_sheet_id += 1
            sheet_number += 1

        replacements = {
            calc_path: ET.tostring(
                calc_root,
                encoding="utf-8",
                xml_declaration=True,
            ),
            "xl/workbook.xml": ET.tostring(
                workbook_root,
                encoding="utf-8",
                xml_declaration=True,
            ),
            "xl/_rels/workbook.xml.rels": _serialize_package_manifest(rels_root, PKG_REL),
            "[Content_Types].xml": _serialize_package_manifest(content_root, CONTENT),
            **additions,
        }
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as output_zip:
            for info in input_zip.infolist():
                payload = replacements.pop(info.filename, None)
                output_zip.writestr(
                    deepcopy(info), payload if payload is not None else input_zip.read(info)
                )
            for name, payload in replacements.items():
                output_zip.writestr(name, payload)

    inspect_safety(destination)


def changed_core_formulas(
    before: Path, after: Path, cells: Iterable[str]
) -> dict[str, tuple[str, str]]:
    old = formula_map(before)
    new = formula_map(after)
    return {
        cell: (old.get(cell, ""), new.get(cell, ""))
        for cell in cells
        if old.get(cell) != new.get(cell)
    }
