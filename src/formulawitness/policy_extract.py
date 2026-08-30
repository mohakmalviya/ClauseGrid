"""In-process PDF extraction primitive used only by the disposable policy worker."""

from __future__ import annotations

import io
import re

from pypdf import PdfReader


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_policy_pages(
    document_bytes: bytes,
    *,
    max_pages: int,
    max_page_chars: int,
    max_total_chars: int,
) -> tuple[str, ...]:
    """Extract bounded normalized text; the caller must provide process isolation."""

    reader = PdfReader(io.BytesIO(document_bytes), strict=True)
    if len(reader.pages) > max_pages:
        raise ValueError("Policy exceeds the page limit")
    pages: list[str] = []
    total_characters = 0
    for page in reader.pages:
        text = _normalize(page.extract_text() or "")
        if len(text) > max_page_chars:
            raise ValueError("Policy page exceeds the text limit")
        total_characters += len(text)
        if total_characters > max_total_chars:
            raise ValueError("Policy exceeds the extracted-text limit")
        pages.append(text)
    return tuple(pages)
