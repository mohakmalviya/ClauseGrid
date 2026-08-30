"""Policy-only retrieval for the agent runtime.

This module intentionally does not import the frozen supplier policy compiler.  It exposes only
document text and mechanically verifiable citations selected at runtime.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

HARD_MAX_BYTES = 10_000_000
HARD_MAX_PAGES = 200
HARD_MAX_PAGE_CHARS = 40_000
HARD_MAX_TOTAL_CHARS = 2_000_000
POLICY_WORKER_TIMEOUT_SECONDS = 20.0
POLICY_WORKER_MEMORY_LIMIT_BYTES = 512 * 1024 * 1024
POLICY_WORKER_CPU_LIMIT_100NS = 15 * 10_000_000


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _assign_windows_job_object(process: subprocess.Popen[str]) -> int:
    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "Windows Job Object creation failed")
    information = ExtendedLimitInformation()
    information.BasicLimitInformation.PerProcessUserTimeLimit = POLICY_WORKER_CPU_LIMIT_100NS
    information.BasicLimitInformation.LimitFlags = 0x2 | 0x100 | 0x2000
    information.ProcessMemoryLimit = POLICY_WORKER_MEMORY_LIMIT_BYTES
    if not kernel32.SetInformationJobObject(
        job,
        9,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(job)
        raise OSError(error, "Windows Job Object limits could not be applied")
    process_handle = wintypes.HANDLE(int(cast(Any, process)._handle))
    if not kernel32.AssignProcessToJobObject(job, process_handle):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(job)
        raise OSError(error, "Policy worker could not enter the Windows Job Object")
    return int(job)


def _close_windows_handle(handle: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(wintypes.HANDLE(handle))


def _run_policy_worker(
    command: list[str],
    *,
    request: str,
    working_directory: str,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    if os.name != "nt":
        return subprocess.run(
            command,
            input=request,
            text=True,
            encoding="utf-8",
            errors="strict",
            capture_output=True,
            timeout=POLICY_WORKER_TIMEOUT_SECONDS,
            cwd=working_directory,
            env=environment,
            check=False,
        )
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
        cwd=working_directory,
        env=environment,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        job_handle = _assign_windows_job_object(process)
    except Exception:
        process.kill()
        process.communicate()
        raise
    try:
        try:
            stdout, stderr = process.communicate(
                request,
                timeout=POLICY_WORKER_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        _close_windows_handle(job_handle)


def _extract_pages_isolated(
    path: Path,
    *,
    max_bytes: int,
    max_pages: int,
    max_page_chars: int,
    max_total_chars: int,
) -> tuple[str, ...]:
    request = json.dumps(
        {
            "path": str(path),
            "max_bytes": max_bytes,
            "max_pages": max_pages,
            "max_page_chars": max_page_chars,
            "max_total_chars": max_total_chars,
        }
    )
    package_root = str(Path(__file__).resolve().parents[1])
    inherited_pythonpath = os.environ.get("PYTHONPATH", "")
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": package_root
        + (os.pathsep + inherited_pythonpath if inherited_pythonpath else ""),
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8:strict",
        "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1",
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
    }
    with tempfile.TemporaryDirectory(prefix="formulawitness-policy-") as working_directory:
        try:
            completed = _run_policy_worker(
                [sys.executable, "-m", "formulawitness.policy_worker"],
                request=request,
                working_directory=working_directory,
                environment=environment,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Policy parser exceeded the isolated execution time limit") from exc
        except OSError as exc:
            raise ValueError(f"Policy parser could not start: {type(exc).__name__}") from exc
    if len(completed.stdout) > max_total_chars * 6 + 100_000:
        raise ValueError("Policy parser output exceeds the safety limit")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Policy parser returned invalid output") from exc
    if completed.returncode != 0 or not isinstance(payload, dict) or not payload.get("ok"):
        error = payload.get("error", "isolated parser failed") if isinstance(payload, dict) else ""
        raise ValueError(f"Policy parser rejected document: {error}")
    raw_pages = payload.get("pages")
    if not isinstance(raw_pages, list) or not all(isinstance(page, str) for page in raw_pages):
        raise ValueError("Policy parser returned invalid pages")
    pages = tuple(raw_pages)
    if (
        len(pages) > max_pages
        or any(len(page) > max_page_chars for page in pages)
        or sum(len(page) for page in pages) > max_total_chars
    ):
        raise ValueError("Policy parser exceeded the requested extraction limits")
    return pages


@dataclass(frozen=True)
class PolicyHit:
    page: int
    start_char: int
    end_char: int
    exact_quote: str
    quote_sha256: str

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


class PolicyText:
    """Bounded, read-only view of an untrusted PDF policy."""

    def __init__(
        self,
        path: Path,
        *,
        max_bytes: int = 10_000_000,
        max_pages: int = 200,
        max_page_chars: int = 40_000,
        max_total_chars: int = 2_000_000,
    ):
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise ValueError("Policy must be an existing PDF")
        if path.stat().st_size > max_bytes:
            raise ValueError("Policy exceeds the byte-size limit")
        limits = (
            (max_bytes, HARD_MAX_BYTES),
            (max_pages, HARD_MAX_PAGES),
            (max_page_chars, HARD_MAX_PAGE_CHARS),
            (max_total_chars, HARD_MAX_TOTAL_CHARS),
        )
        if any(requested < 1 or requested > hard for requested, hard in limits):
            raise ValueError("Policy extraction limits exceed the hard safety profile")
        self.path = path.resolve()
        document_bytes = path.read_bytes()
        if len(document_bytes) > max_bytes:
            raise ValueError("Policy exceeds the byte-size limit")
        self.document_sha256 = hashlib.sha256(document_bytes).hexdigest()
        self.pages = _extract_pages_isolated(
            self.path,
            max_bytes=max_bytes,
            max_pages=max_pages,
            max_page_chars=max_page_chars,
            max_total_chars=max_total_chars,
        )
        if hashlib.sha256(path.read_bytes()).hexdigest() != self.document_sha256:
            raise ValueError("Policy changed during isolated extraction")

    def manifest(self) -> dict[str, str | int]:
        return {
            "document_sha256": self.document_sha256,
            "page_count": len(self.pages),
        }

    def read_page(
        self, page: int, *, start_char: int = 0, max_chars: int = 8_000
    ) -> dict[str, object]:
        if page < 1 or page > len(self.pages):
            raise ValueError("Policy page is out of range")
        if start_char < 0 or max_chars < 1 or max_chars > 12_000:
            raise ValueError("Policy text window is invalid")
        text = self.pages[page - 1]
        end = min(len(text), start_char + max_chars)
        return {
            "page": page,
            "start_char": start_char,
            "end_char": end,
            "text": text[start_char:end],
            "content_is_untrusted": True,
        }

    def search(
        self, query: str, *, max_results: int = 8, context_chars: int = 240
    ) -> list[PolicyHit]:
        query = _normalize(query)
        if len(query) < 2 or len(query) > 200:
            raise ValueError("Policy search query must contain 2-200 characters")
        if max_results < 1 or max_results > 20 or context_chars < 40 or context_chars > 1_000:
            raise ValueError("Policy search bounds are invalid")
        patterns = [re.compile(re.escape(word), re.IGNORECASE) for word in query.split()]
        hits: list[PolicyHit] = []
        for page_number, text in enumerate(self.pages, start=1):
            cursor = 0
            while cursor < len(text):
                first = patterns[0].search(text, cursor)
                if first is None:
                    break
                match_start = first.start()
                match_end = first.end()
                for pattern in patterns[1:]:
                    match = pattern.search(text, match_end)
                    if match is None:
                        match_end = -1
                        break
                    match_end = match.end()
                if match_end < 0:
                    break
                start = max(0, match_start - context_chars)
                end = min(len(text), match_end + context_chars)
                quote = text[start:end]
                hits.append(
                    PolicyHit(
                        page=page_number,
                        start_char=start,
                        end_char=end,
                        exact_quote=quote,
                        quote_sha256=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
                    )
                )
                if len(hits) >= max_results:
                    return hits
                cursor = match_end
        return hits

    def verify_citation(
        self,
        *,
        page: int,
        start_char: int,
        end_char: int,
        exact_quote: str,
    ) -> PolicyHit:
        if page < 1 or page > len(self.pages):
            raise ValueError("Citation page is out of range")
        text = self.pages[page - 1]
        if start_char < 0 or end_char <= start_char:
            raise ValueError("Citation offsets are invalid")
        if end_char > len(text) or text[start_char:end_char] != exact_quote:
            actual_start = text.find(exact_quote)
            if actual_start < 0 or text.find(exact_quote, actual_start + 1) >= 0:
                raise ValueError("Citation quote is not a unique exact policy passage")
            start_char = actual_start
            end_char = actual_start + len(exact_quote)
        return PolicyHit(
            page=page,
            start_char=start_char,
            end_char=end_char,
            exact_quote=exact_quote,
            quote_sha256=hashlib.sha256(exact_quote.encode("utf-8")).hexdigest(),
        )
