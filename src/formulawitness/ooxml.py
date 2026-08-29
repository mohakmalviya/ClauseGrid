"""Safe, narrow OOXML inspection and minimal formula patching."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from collections.abc import Iterable, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any, cast
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
    if path.stat().st_size > max_uncompressed:
        raise WorkbookRejected("Workbook package exceeds the compressed-size limit")
    package = path.read_bytes()
    package_sha256 = hashlib.sha256(package).hexdigest()
    try:
        archive_context = zipfile.ZipFile(io.BytesIO(package))
    except zipfile.BadZipFile as exc:
        raise WorkbookRejected("Workbook is not a valid OOXML ZIP package") from exc
    with archive_context as archive:
        infos = archive.infolist()
        if len(infos) > 1000 or sum(info.file_size for info in infos) > max_uncompressed:
            raise WorkbookRejected("Workbook package exceeds the safety limit")
        canonical_names = [info.filename.replace("\\", "/").casefold() for info in infos]
        if len(set(canonical_names)) != len(canonical_names):
            raise WorkbookRejected("Workbook package contains duplicate part names")
        for info in infos:
            normalized = info.filename.replace("\\", "/")
            if normalized.startswith("/") or ".." in normalized.split("/"):
                raise WorkbookRejected("Workbook package contains an unsafe part path")
            if info.flag_bits & 0x1:
                raise WorkbookRejected("Encrypted workbook package parts are unsupported")
            if info.file_size > 1_000_000 and info.compress_size * 200 < info.file_size:
                raise WorkbookRejected("Workbook package contains an excessive compression ratio")
        names = {info.filename.lower() for info in infos}
        required = {
            "[content_types].xml",
            "_rels/.rels",
            "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels",
        }
        forbidden = (
            "vbaproject.bin",
            "xl/macrosheets/",
            "xl/dialogsheets/",
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
        if not required <= names:
            raise WorkbookRejected("Workbook package is missing required OOXML parts")
        content_types = ET.fromstring(archive.read("[Content_Types].xml"))
        unsafe_content_types = {
            str(item.attrib.get("ContentType", "")).casefold()
            for item in content_types
            if any(
                marker in str(item.attrib.get("ContentType", "")).casefold()
                for marker in ("macroenabled", "vbaproject", "oleobject", "activex")
            )
        }
        if unsafe_content_types:
            raise WorkbookRejected("Workbook declares an unsupported active content type")
        package_relationships = ET.fromstring(archive.read("_rels/.rels"))
        office_documents = [
            relationship
            for relationship in package_relationships
            if relationship.attrib.get("Type", "").endswith("/officeDocument")
        ]
        if (
            len(office_documents) != 1
            or office_documents[0].attrib.get("Target", "").lstrip("/") != "xl/workbook.xml"
        ):
            raise WorkbookRejected("Workbook package has an invalid office-document relationship")
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        if workbook_root.find("x:definedNames", NS) is not None:
            raise WorkbookRejected("Defined names are outside the supported workbook profile")
        _sheet_paths(archive)
        formulas = _archive_formula_map(archive)
        unsafe_function = re.compile(
            r"\b(?:CALL|EVALUATE|EXEC|REGISTER\.ID|INDIRECT|OFFSET|NOW|TODAY|RAND|RANDBETWEEN|WEBSERVICE|RTD|HYPERLINK|FILTERXML|STOCKHISTORY)\s*\(",
            re.IGNORECASE,
        )
        external_formula = re.compile(
            r"(?:https?://|ftp://|\\\\|\[[^\]]+\][^!]*!|\|)", re.IGNORECASE
        )
        unsafe = [
            cell
            for cell, formula in formulas.items()
            if unsafe_function.search(formula) or external_formula.search(formula)
        ]
        if unsafe:
            raise WorkbookRejected(
                f"Volatile, DDE, or network-capable formulas are unsupported: {', '.join(unsafe)}"
            )
    return {
        "sha256": package_sha256,
        "entries": len(infos),
        "formula_count": len(formulas),
    }


def _sheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    relationship_rows = {rel.attrib["Id"]: rel.attrib for rel in relationships}
    if len(relationship_rows) != len(list(relationships)):
        raise WorkbookRejected("Workbook contains duplicate relationship identifiers")
    result: dict[str, str] = {}
    canonical_names: set[str] = set()
    canonical_targets: set[str] = set()
    sheets = workbook.find("x:sheets", NS)
    if sheets is None:
        raise WorkbookRejected("Workbook sheet manifest is missing")
    for sheet in sheets:
        name = sheet.attrib.get("name", "")
        if not name or name.casefold() in canonical_names:
            raise WorkbookRejected(
                "Workbook sheet names must be non-empty and case-insensitively unique"
            )
        canonical_names.add(name.casefold())
        relationship_id = sheet.attrib.get(f"{{{REL}}}id")
        relationship = relationship_rows.get(str(relationship_id))
        if relationship is None:
            raise WorkbookRejected(f"Worksheet relationship is missing: {name}")
        if not relationship.get("Type", "").endswith("/worksheet"):
            raise WorkbookRejected(f"Unsupported sheet relationship type: {name}")
        target = relationship["Target"].lstrip("/")
        resolved = target if target.startswith("xl/") else f"xl/{target}"
        if resolved not in archive.namelist():
            raise WorkbookRejected(f"Worksheet part is missing: {name}")
        if resolved.casefold() in canonical_targets:
            raise WorkbookRejected("Multiple sheet names reference the same worksheet part")
        canonical_targets.add(resolved.casefold())
        result[name] = resolved
    return result


def _archive_formula_map(archive: zipfile.ZipFile) -> dict[str, str]:
    result: dict[str, str] = {}
    for sheet_name, target in _sheet_paths(archive).items():
        root = ET.fromstring(archive.read(target))
        seen_cells: set[str] = set()
        for cell in root.findall(".//x:c", NS):
            address = cell.attrib.get("r", "").upper()
            if not address or address in seen_cells:
                raise WorkbookRejected(
                    f"Worksheet contains a duplicate or missing cell address: {sheet_name}"
                )
            seen_cells.add(address)
            formula = cell.find("x:f", NS)
            if formula is None:
                continue
            if formula.attrib:
                raise WorkbookRejected(
                    f"Shared, array, or data-table formulas are unsupported: {sheet_name}!{address}"
                )
            if formula.text is None:
                raise WorkbookRejected(f"Formula text is missing: {sheet_name}!{address}")
            result[f"{sheet_name}!{address}"] = "=" + formula.text
    return result


def workbook_sheet_names(path: Path) -> tuple[str, ...]:
    """Return workbook sheet names in package order without loading workbook code."""

    with zipfile.ZipFile(path) as archive:
        return tuple(_sheet_paths(archive))


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
            if not address or address in values:
                raise WorkbookRejected("Worksheet contains a duplicate or missing cell address")
            formula = cell.find("x:f", NS)
            value = cell.find("x:v", NS)
            if formula is not None and formula.attrib:
                raise WorkbookRejected("Shared, array, and data-table formulas are unsupported")
            if formula is not None and formula.text is not None:
                formulas[address] = "=" + formula.text
            if cell.attrib.get("t") == "inlineStr":
                inline = cell.find("x:is", NS)
                values[address] = (
                    None
                    if inline is None
                    else "".join(node.text or "" for node in inline.iter(f"{{{MAIN}}}t"))
                )
                continue
            if value is None or value.text is None:
                values[address] = None
                continue
            kind = cell.attrib.get("t")
            if kind == "s":
                values[address] = strings[int(value.text)]
            elif kind == "str":
                values[address] = value.text
            elif kind == "b":
                values[address] = value.text == "1"
            else:
                number = float(value.text)
                values[address] = int(number) if number.is_integer() else number
        return values, formulas


def calculation_cells(
    path: Path, sheet_name: str = "RebateCalc"
) -> tuple[dict[str, Any], dict[str, str]]:
    """Return calculation-sheet formulas plus qualified values from every sheet."""

    values, formulas = sheet_cells(path, sheet_name)
    with zipfile.ZipFile(path) as archive:
        sheet_names = tuple(_sheet_paths(archive))
    for source_sheet in sheet_names:
        source_values, _ = sheet_cells(path, source_sheet)
        values.update(
            {f"{source_sheet.upper()}!{address}": value for address, value in source_values.items()}
        )
    return values, formulas


def formula_map(path: Path, sheet_name: str = "RebateCalc") -> dict[str, str]:
    return sheet_cells(path, sheet_name)[1]


def workbook_formula_map(path: Path) -> dict[str, str]:
    """Return every formula in every original workbook sheet."""

    with zipfile.ZipFile(path) as archive:
        return _archive_formula_map(archive)


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


def _make_sheet(rows: Iterable[Iterable[Any]], widths: Sequence[float]) -> bytes:
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
    return cast(bytes, ET.tostring(root, encoding="utf-8", xml_declaration=True))


def _serialize_package_manifest(root: ET.Element, namespace: str) -> bytes:
    """Serialize package manifests with the unprefixed namespace OpenXML expects."""
    text = ET.tostring(root, encoding="unicode", xml_declaration=False)
    match = re.match(r"<(?P<prefix>ns\d+):", text)
    if match is None:
        return cast(bytes, ET.tostring(root, encoding="utf-8", xml_declaration=True))
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
    """Apply guarded formula patches and add evidence sheets to a copied package.

    Patch keys may be fully qualified as ``Sheet!A1``. Unqualified keys retain the
    legacy behavior and target ``RebateCalc``.
    """

    inspect_safety(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as input_zip:
        names = input_zip.namelist()
        sheet_paths = _sheet_paths(input_zip)
        canonical_sheets = {name.casefold(): name for name in sheet_paths}
        modified_roots: dict[str, ET.Element] = {}
        patched_references: set[str] = set()
        for reference, (expected_old, new_formula) in patches.items():
            if "!" in reference:
                requested_sheet, address = reference.rsplit("!", 1)
            else:
                requested_sheet, address = "RebateCalc", reference
            sheet_name = canonical_sheets.get(requested_sheet.casefold())
            if sheet_name is None:
                raise WorkbookRejected(f"Patch sheet missing: {requested_sheet}")
            address = address.replace("$", "").upper()
            if re.fullmatch(r"[A-Z]{1,3}[1-9]\d*", address) is None:
                raise WorkbookRejected(f"Invalid patch target: {reference}")
            qualified_reference = f"{sheet_name}!{address}"
            if qualified_reference in patched_references:
                raise WorkbookRejected(f"Duplicate patch target: {qualified_reference}")
            patched_references.add(qualified_reference)
            sheet_path = sheet_paths[sheet_name]
            sheet_root = modified_roots.setdefault(
                sheet_path, ET.fromstring(input_zip.read(sheet_path))
            )
            cells = {
                cell.attrib.get("r", "").upper(): cell for cell in sheet_root.findall(".//x:c", NS)
            }
            cell = cells.get(address)
            if cell is None:
                raise WorkbookRejected(f"Patch target missing: {qualified_reference}")
            formula_node = cell.find("x:f", NS)
            current = "=" + (formula_node.text or "") if formula_node is not None else ""
            if current != expected_old:
                raise WorkbookRejected(f"Old-formula guard failed for {qualified_reference}")
            assert formula_node is not None
            formula_node.text = new_formula.removeprefix("=")
            cached = cell.find("x:v", NS)
            if cached is not None:
                cell.remove(cached)

        workbook_root = ET.fromstring(input_zip.read("xl/workbook.xml"))
        rels_root = ET.fromstring(input_zip.read("xl/_rels/workbook.xml.rels"))
        content_root = ET.fromstring(input_zip.read("[Content_Types].xml"))
        for relationship in list(rels_root):
            if relationship.attrib.get("Type", "").endswith("/calcChain"):
                rels_root.remove(relationship)
        for override in list(content_root):
            if override.attrib.get("PartName", "").casefold() == "/xl/calcchain.xml":
                content_root.remove(override)
        sheets_node = workbook_root.find("x:sheets", NS)
        assert sheets_node is not None
        existing_sheet_names = {sheet.attrib.get("name", "").casefold() for sheet in sheets_node}
        reserved_names = {"counterexamples", "formulawitness_report"}
        if existing_sheet_names & reserved_names:
            raise WorkbookRejected("Workbook already contains a reserved evidence sheet")

        # Formula caches can otherwise expose values calculated from the old candidate.
        for sheet_path in sheet_paths.values():
            sheet_root = modified_roots.setdefault(
                sheet_path, ET.fromstring(input_zip.read(sheet_path))
            )
            for cell in sheet_root.findall(".//x:c", NS):
                if cell.find("x:f", NS) is not None:
                    cached = cell.find("x:v", NS)
                    if cached is not None:
                        cell.remove(cached)

        calc_properties = workbook_root.find("x:calcPr", NS)
        if calc_properties is None:
            calc_properties = ET.SubElement(workbook_root, f"{{{MAIN}}}calcPr")
        calc_properties.attrib.update(
            {"calcMode": "auto", "fullCalcOnLoad": "1", "forceFullCalc": "1"}
        )
        next_sheet_id = max(int(sheet.attrib["sheetId"]) for sheet in sheets_node) + 1
        existing_targets = {
            (target if target.startswith("xl/") else f"xl/{target}")
            for target in (rel.attrib["Target"].lstrip("/") for rel in rels_root)
        }
        existing_relationship_ids = {rel.attrib["Id"] for rel in rels_root}
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
            rid_index = sheet_number
            rid = f"rIdFormulaWitness{rid_index}"
            while rid in existing_relationship_ids:
                rid_index += 1
                rid = f"rIdFormulaWitness{rid_index}"
            existing_relationship_ids.add(rid)
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
            **{
                sheet_path: ET.tostring(
                    sheet_root,
                    encoding="utf-8",
                    xml_declaration=True,
                )
                for sheet_path, sheet_root in modified_roots.items()
            },
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
                if info.filename.casefold() == "xl/calcchain.xml":
                    continue
                payload = replacements.pop(info.filename, None)
                output_zip.writestr(
                    deepcopy(info), payload if payload is not None else input_zip.read(info)
                )
            for name, payload in replacements.items():
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 0
                info.external_attr = 0
                output_zip.writestr(info, payload)

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


def changed_workbook_formulas(before: Path, after: Path) -> dict[str, tuple[str, str]]:
    old = workbook_formula_map(before)
    new = workbook_formula_map(after)
    return {
        cell: (old.get(cell, ""), new.get(cell, ""))
        for cell in sorted(old.keys() | new.keys())
        if old.get(cell) != new.get(cell)
    }
