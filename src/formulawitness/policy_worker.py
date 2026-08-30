"""Disposable, resource-bounded PDF text extraction process."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

HARD_MAX_BYTES = 10_000_000
HARD_MAX_PAGES = 200
HARD_MAX_PAGE_CHARS = 40_000
HARD_MAX_TOTAL_CHARS = 2_000_000
POSIX_MEMORY_LIMIT_BYTES = 512 * 1024 * 1024
POSIX_CPU_LIMIT_SECONDS = 15


def _apply_resource_limits() -> None:
    try:
        resource: Any = importlib.import_module("resource")
    except ImportError:
        return
    for resource_kind, requested in (
        (resource.RLIMIT_AS, POSIX_MEMORY_LIMIT_BYTES),
        (resource.RLIMIT_CPU, POSIX_CPU_LIMIT_SECONDS),
    ):
        _, current_hard = resource.getrlimit(resource_kind)
        limit = (
            requested if current_hard == resource.RLIM_INFINITY else min(requested, current_hard)
        )
        resource.setrlimit(resource_kind, (limit, limit))


def _bounded_integer(request: dict[str, Any], name: str, hard_limit: int) -> int:
    value = int(request[name])
    if value < 1 or value > hard_limit:
        raise ValueError(f"Policy worker limit is invalid: {name}")
    return value


def main() -> int:
    try:
        _apply_resource_limits()
        request = json.loads(sys.stdin.read())
        if not isinstance(request, dict):
            raise TypeError("Policy worker request must be an object")
        max_bytes = _bounded_integer(request, "max_bytes", HARD_MAX_BYTES)
        max_pages = _bounded_integer(request, "max_pages", HARD_MAX_PAGES)
        max_page_chars = _bounded_integer(request, "max_page_chars", HARD_MAX_PAGE_CHARS)
        max_total_chars = _bounded_integer(request, "max_total_chars", HARD_MAX_TOTAL_CHARS)
        path = Path(str(request["path"])).resolve()
        document_bytes = path.read_bytes()
        if not document_bytes or len(document_bytes) > max_bytes:
            raise ValueError("Policy exceeds the byte-size limit")
        from .policy_extract import extract_policy_pages

        pages = extract_policy_pages(
            document_bytes,
            max_pages=max_pages,
            max_page_chars=max_page_chars,
            max_total_chars=max_total_chars,
        )
        print(json.dumps({"ok": True, "pages": pages}, ensure_ascii=True))
        return 0
    except Exception as exc:  # noqa: BLE001 - process boundary must fail closed
        print(
            json.dumps(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
