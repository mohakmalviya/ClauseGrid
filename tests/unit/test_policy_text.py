from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from formulawitness.policy_text import PolicyText


def _policy(path: Path) -> None:
    pdf = canvas.Canvas(str(path))
    pdf.drawString(72, 720, "Invoices above 100 receive a five percent rebate after returns.")
    pdf.save()


def test_policy_search_and_exact_citation_are_runtime_selected(tmp_path: Path) -> None:
    path = tmp_path / "policy.pdf"
    _policy(path)
    policy = PolicyText(path)

    hit = policy.search("five percent")[0]
    verified = policy.verify_citation(
        page=hit.page,
        start_char=hit.start_char,
        end_char=hit.end_char,
        exact_quote=hit.exact_quote,
    )

    assert verified.quote_sha256 == hit.quote_sha256
    assert policy.read_page(1)["content_is_untrusted"] is True
    assert policy.manifest()["page_count"] == 1


def test_unique_exact_quote_repairs_incorrect_model_offsets(tmp_path: Path) -> None:
    path = tmp_path / "policy.pdf"
    _policy(path)
    policy = PolicyText(path)

    verified = policy.verify_citation(
        page=1,
        start_char=0,
        end_char=len(policy.pages[0]),
        exact_quote="five percent rebate",
    )

    assert policy.pages[0][verified.start_char : verified.end_char] == "five percent rebate"


def test_policy_byte_limit_is_checked_before_pdf_parsing(tmp_path: Path) -> None:
    path = tmp_path / "oversized.pdf"
    path.write_bytes(b"%PDF-1.4\n" + b"x" * 100)

    with pytest.raises(ValueError, match="byte-size limit"):
        PolicyText(path, max_bytes=32)
