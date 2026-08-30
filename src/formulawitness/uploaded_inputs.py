"""Fail-closed staging for local workbook-and-policy browser uploads."""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .formula import (
    FormulaError,
    evaluate_cells,
    validate_formula_dependency_graph,
    validate_formula_subset,
)
from .ooxml import inspect_safety, workbook_calculation_cells, workbook_sheet_names
from .policy_text import PolicyText
from .workbook_tools import list_formulas, workbook_manifest

MAX_WORKBOOK_BYTES = 25_000_000
MAX_POLICY_BYTES = 10_000_000
MAX_UPLOADS_PER_SERVER = 20
UPLOAD_TTL_SECONDS = 30 * 60


class UploadRejected(ValueError):
    """The supplied input is outside FormulaWitness's safe supported profile."""


class UploadTooLarge(UploadRejected):
    """The supplied body exceeds its byte limit."""


@dataclass(frozen=True)
class UploadResidue:
    """Minimal server-owned identity needed to retry cleanup after failed preflight."""

    upload_id: str
    workbook_path: Path


class UploadCleanupRequired(UploadRejected):
    """Preflight failed and operating-system cleanup must be retried by the server."""

    def __init__(self, message: str, residue: UploadResidue):
        super().__init__(message)
        self.residue = residue


@dataclass(frozen=True)
class StagedWorkbook:
    upload_id: str
    upload_dir: Path
    workbook_path: Path
    workbook_sha256: str
    package_entries: int
    formula_count: int
    sheets: tuple[dict[str, Any], ...]

    def public_manifest(self) -> dict[str, Any]:
        return {
            "upload_id": self.upload_id,
            "workbook_sha256": self.workbook_sha256,
            "package_entries": self.package_entries,
            "formula_count": self.formula_count,
            "sheets": list(self.sheets),
            "policy_required": True,
            "ready": False,
        }


@dataclass(frozen=True)
class UploadedAuditInput:
    upload_id: str
    workbook_path: Path
    policy_path: Path
    workbook_sha256: str
    policy_sha256: str
    package_entries: int
    formula_count: int
    sheets: tuple[dict[str, Any], ...]
    policy_page_count: int

    def public_manifest(self) -> dict[str, Any]:
        return {
            "upload_id": self.upload_id,
            "workbook_sha256": self.workbook_sha256,
            "policy_sha256": self.policy_sha256,
            "package_entries": self.package_entries,
            "formula_count": self.formula_count,
            "sheets": list(self.sheets),
            "policy_page_count": self.policy_page_count,
            "policy_required": True,
            "ready": True,
        }


def _write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _bounded_content(content: bytes, *, limit: int, label: str) -> None:
    if not content:
        raise UploadRejected(f"{label} upload is empty")
    if len(content) > limit:
        raise UploadTooLarge(f"{label} exceeds the {limit // 1_000_000} MB upload limit")


def _validate_formula_profile(workbook: Path) -> None:
    try:
        formulas = list_formulas(workbook)
    except ValueError as exc:
        raise UploadRejected(str(exc)) from exc
    for reference, formula in formulas.items():
        try:
            validate_formula_subset(formula)
        except FormulaError as exc:
            raise UploadRejected(
                f"Unsupported formula in {reference}: {exc}. "
                "FormulaWitness can execute only the documented supported formula profile."
            ) from exc
    sheet_names = workbook_sheet_names(workbook)
    try:
        validate_formula_dependency_graph(formulas, sheet_names)
    except FormulaError as exc:
        raise UploadRejected(str(exc)) from exc
    try:
        values, workbook_formulas = workbook_calculation_cells(workbook)
        evaluate_cells(values, workbook_formulas)
    except (FormulaError, ValueError, TypeError) as exc:
        raise UploadRejected(f"Workbook calculation preflight failed: {exc}") from exc


def stage_workbook(upload_root: Path, content: bytes) -> StagedWorkbook:
    """Write and preflight one calculation-focused XLSX under a server-generated path."""

    _bounded_content(content, limit=MAX_WORKBOOK_BYTES, label="Workbook")
    upload_root = upload_root.resolve(strict=False)
    upload_root.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4().hex
    upload_dir = upload_root / upload_id
    upload_dir.mkdir(mode=0o700)
    workbook = upload_dir / "workbook.xlsx"
    try:
        _write_exclusive(workbook, content)
        safety = inspect_safety(workbook)
        _validate_formula_profile(workbook)
        manifest = workbook_manifest(workbook)
        sheets = tuple(asdict(sheet) for sheet in manifest.sheets)
        if not sheets:
            raise UploadRejected("Workbook contains no worksheets")
        return StagedWorkbook(
            upload_id=upload_id,
            upload_dir=upload_dir,
            workbook_path=workbook,
            workbook_sha256=str(safety["sha256"]),
            package_entries=int(safety["entries"]),
            formula_count=int(safety["formula_count"]),
            sheets=sheets,
        )
    except Exception as exc:
        residue = UploadResidue(upload_id=upload_id, workbook_path=workbook)
        try:
            remove_upload(residue)
        except Exception as cleanup_exc:
            raise UploadCleanupRequired(str(exc), residue) from cleanup_exc
        raise


def stage_policy(staged: StagedWorkbook, content: bytes) -> UploadedAuditInput:
    """Attach and validate the governing PDF for an already-staged workbook."""

    _bounded_content(content, limit=MAX_POLICY_BYTES, label="Policy PDF")
    temporary = staged.upload_dir / ".policy-upload.pdf"
    destination = staged.upload_dir / "policy.pdf"
    try:
        _write_exclusive(temporary, content)
        policy = PolicyText(temporary)
        if not policy.pages or not any(page.strip() for page in policy.pages):
            raise UploadRejected("Policy PDF contains no extractable text")
        os.replace(temporary, destination)
        return UploadedAuditInput(
            upload_id=staged.upload_id,
            workbook_path=staged.workbook_path,
            policy_path=destination,
            workbook_sha256=staged.workbook_sha256,
            policy_sha256=policy.document_sha256,
            package_entries=staged.package_entries,
            formula_count=staged.formula_count,
            sheets=staged.sheets,
            policy_page_count=len(policy.pages),
        )
    except (OSError, UploadRejected):
        temporary.unlink(missing_ok=True)
        raise
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise UploadRejected("Policy PDF could not be parsed safely") from exc


def remove_upload(upload: StagedWorkbook | UploadedAuditInput | UploadResidue) -> None:
    """Remove a server-owned ephemeral upload directory."""

    upload_dir = upload.workbook_path.parent
    if upload_dir.name != upload.upload_id:
        raise ValueError("Upload directory identity does not match the upload identifier")
    try:
        shutil.rmtree(upload_dir)
    except FileNotFoundError:
        return
    if upload_dir.exists():
        raise OSError("Ephemeral upload directory could not be removed")


def sheet_names(upload: StagedWorkbook | UploadedAuditInput) -> tuple[str, ...]:
    """Expose the authoritative OOXML order for compact diagnostics."""

    return workbook_sheet_names(upload.workbook_path)
