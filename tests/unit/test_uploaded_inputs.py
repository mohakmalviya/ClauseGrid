from __future__ import annotations

import io
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pypdf import PdfWriter

from formulawitness import uploaded_inputs
from formulawitness.ooxml import MAIN
from formulawitness.uploaded_inputs import (
    UploadCleanupRequired,
    UploadRejected,
    remove_upload,
    stage_policy,
    stage_workbook,
)

ROOT = Path(__file__).resolve().parents[2]
WORKBOOK = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
POLICY = ROOT / "policies/supplier_rebate_sla_policy.pdf"


def _workbook_with_formula(tmp_path: Path, formula: str) -> bytes:
    target = tmp_path / "unsupported.xlsx"
    changed = False
    with ZipFile(WORKBOOK) as source, ZipFile(target, "w", ZIP_DEFLATED) as output:
        for info in source.infolist():
            payload = source.read(info)
            if not changed and info.filename.startswith("xl/worksheets/"):
                root = ET.fromstring(payload)
                node = root.find(".//x:f", {"x": MAIN})
                if node is not None:
                    node.text = formula.removeprefix("=")
                    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    changed = True
            output.writestr(info, payload)
    assert changed
    return target.read_bytes()


def _workbook_with_cross_sheet_formula_dependency(tmp_path: Path) -> bytes:
    target = tmp_path / "cross-sheet-formula.xlsx"
    changed = False
    with ZipFile(WORKBOOK) as source, ZipFile(target, "w", ZIP_DEFLATED) as output:
        for info in source.infolist():
            payload = source.read(info)
            if not changed and info.filename.startswith("xl/worksheets/"):
                root = ET.fromstring(payload)
                cell = next(
                    (
                        item
                        for item in root.findall(".//x:c", {"x": MAIN})
                        if item.attrib.get("r") == "B5"
                        and item.find("x:f", {"x": MAIN}) is None
                        and item.find("x:v", {"x": MAIN}) is not None
                        and item.find("x:v", {"x": MAIN}).text == "0"
                    ),
                    None,
                )
                if cell is not None:
                    formula = ET.Element(f"{{{MAIN}}}f")
                    formula.text = "1"
                    cell.insert(0, formula)
                    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    changed = True
            output.writestr(info, payload)
    assert changed
    return target.read_bytes()


def _workbook_with_self_cycle(tmp_path: Path) -> bytes:
    target = tmp_path / "self-cycle.xlsx"
    changed = False
    with ZipFile(WORKBOOK) as source, ZipFile(target, "w", ZIP_DEFLATED) as output:
        for info in source.infolist():
            payload = source.read(info)
            if not changed and info.filename.startswith("xl/worksheets/"):
                root = ET.fromstring(payload)
                for cell in root.findall(".//x:c", {"x": MAIN}):
                    formula = cell.find("x:f", {"x": MAIN})
                    if formula is not None and cell.attrib.get("r"):
                        formula.text = f"{cell.attrib['r']}+1"
                        payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                        changed = True
                        break
            output.writestr(info, payload)
    assert changed
    return target.read_bytes()


def test_uploaded_workbook_and_policy_are_hash_bound_and_ready(tmp_path: Path) -> None:
    staged = stage_workbook(tmp_path / "uploads", WORKBOOK.read_bytes())

    assert staged.workbook_path.name == "workbook.xlsx"
    assert staged.formula_count >= 9
    assert {sheet["name"] for sheet in staged.sheets} >= {"RebateCalc", "TierSchedule"}
    assert staged.public_manifest()["ready"] is False

    ready = stage_policy(staged, POLICY.read_bytes())

    assert ready.workbook_path == staged.workbook_path
    assert ready.policy_path.name == "policy.pdf"
    assert ready.policy_page_count == 4
    assert ready.public_manifest()["ready"] is True
    assert len(ready.workbook_sha256) == 64
    assert len(ready.policy_sha256) == 64

    remove_upload(ready)
    assert not staged.upload_dir.exists()


def test_unsupported_formula_is_rejected_before_upload_is_registered(tmp_path: Path) -> None:
    upload_root = tmp_path / "uploads"

    with pytest.raises(UploadRejected, match="Unsupported function SUM"):
        stage_workbook(upload_root, _workbook_with_formula(tmp_path, "=SUM(A1:A2)"))

    assert list(upload_root.iterdir()) == []


def test_countif_with_a_value_dependent_criterion_is_rejected_during_preflight(
    tmp_path: Path,
) -> None:
    with pytest.raises(UploadRejected, match="literal equality criterion"):
        stage_workbook(
            tmp_path / "uploads",
            _workbook_with_formula(tmp_path, "=COUNTIF(E6:F6,K6)"),
        )


def test_value_dependent_formula_failure_is_rejected_during_calculation_preflight(
    tmp_path: Path,
) -> None:
    with pytest.raises(UploadRejected, match="calculation preflight.*Expected number"):
        stage_workbook(
            tmp_path / "uploads",
            _workbook_with_formula(tmp_path, "=LOOKUP(K6,K6:K6,E6:E6)"),
        )


def test_failed_preflight_cleanup_is_surfaced_with_a_retryable_server_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload_root = tmp_path / "uploads"
    with monkeypatch.context() as patch:
        patch.setattr(
            uploaded_inputs,
            "remove_upload",
            lambda _upload: (_ for _ in ()).throw(OSError("simulated file lock")),
        )
        with pytest.raises(UploadCleanupRequired, match="Unsupported function SUM") as captured:
            stage_workbook(upload_root, _workbook_with_formula(tmp_path, "=SUM(A1:A2)"))

    assert captured.value.residue.workbook_path.is_file()
    remove_upload(captured.value.residue)
    assert list(upload_root.iterdir()) == []


def test_policy_without_extractable_text_is_rejected_and_cleaned(tmp_path: Path) -> None:
    staged = stage_workbook(tmp_path / "uploads", WORKBOOK.read_bytes())
    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(stream)

    with pytest.raises(UploadRejected, match="no extractable text"):
        stage_policy(staged, stream.getvalue())

    assert staged.workbook_path.is_file()
    assert not (staged.upload_dir / "policy.pdf").exists()
    assert not (staged.upload_dir / ".policy-upload.pdf").exists()


def test_formula_preflight_reuses_the_agent_discovery_output_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        uploaded_inputs,
        "list_formulas",
        lambda _path: (_ for _ in ()).throw(
            ValueError("Workbook formulas exceed the tool-result text limit")
        ),
    )

    with pytest.raises(UploadRejected, match="tool-result text limit"):
        stage_workbook(tmp_path / "uploads", WORKBOOK.read_bytes())

    assert list((tmp_path / "uploads").iterdir()) == []


def test_cross_sheet_formula_chains_are_rejected_before_model_execution(tmp_path: Path) -> None:
    with pytest.raises(UploadRejected, match="Cross-sheet formula-to-formula"):
        stage_workbook(
            tmp_path / "uploads",
            _workbook_with_cross_sheet_formula_dependency(tmp_path),
        )


def test_missing_formula_sheet_is_rejected_before_model_execution(tmp_path: Path) -> None:
    with pytest.raises(UploadRejected, match="worksheet that does not exist"):
        stage_workbook(
            tmp_path / "uploads",
            _workbook_with_formula(tmp_path, "=Missing!A1+1"),
        )


def test_formula_cycles_are_rejected_before_model_execution(tmp_path: Path) -> None:
    with pytest.raises(UploadRejected, match="dependency cycle"):
        stage_workbook(tmp_path / "uploads", _workbook_with_self_cycle(tmp_path))


def test_aggregate_formula_dependency_expansion_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        uploaded_inputs,
        "list_formulas",
        lambda _path: {
            "RebateCalc!A1": "=AND("
            + ",".join(
                f"COUNTIF(A{start}:A{start + 9_999},0)=0" for start in range(1, 110_000, 10_000)
            )
            + ")"
        },
    )

    with pytest.raises(UploadRejected, match="dependency safety limit"):
        stage_workbook(tmp_path / "uploads", WORKBOOK.read_bytes())
