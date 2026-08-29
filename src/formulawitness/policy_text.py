"""Policy-only retrieval for the agent runtime.

This module intentionally does not import the frozen supplier policy compiler.  It exposes only
document text and mechanically verifiable citations selected at runtime.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from pypdf import PdfReader


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


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
        self.path = path.resolve()
        document_bytes = path.read_bytes()
        if len(document_bytes) > max_bytes:
            raise ValueError("Policy exceeds the byte-size limit")
        self.document_sha256 = hashlib.sha256(document_bytes).hexdigest()
        reader = PdfReader(io.BytesIO(document_bytes), strict=True)
        if len(reader.pages) > max_pages:
            raise ValueError("Policy exceeds the page limit")
        self.pages = tuple(_normalize(page.extract_text() or "") for page in reader.pages)
        if any(len(page) > max_page_chars for page in self.pages):
            raise ValueError("Policy page exceeds the text limit")
        if sum(len(page) for page in self.pages) > max_total_chars:
            raise ValueError("Policy exceeds the extracted-text limit")

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
        words = [re.escape(word) for word in query.split()]
        pattern = re.compile(".*?".join(words), re.IGNORECASE)
        hits: list[PolicyHit] = []
        for page_number, text in enumerate(self.pages, start=1):
            for match in pattern.finditer(text):
                start = max(0, match.start() - context_chars)
                end = min(len(text), match.end() + context_chars)
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
