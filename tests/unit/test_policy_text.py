import subprocess
import time
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

import formulawitness.policy_text as policy_text_module
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


def test_policy_parser_timeout_is_normalized_at_the_process_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "policy.pdf"
    _policy(path)

    def timeout(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="policy-worker", timeout=0.01)

    monkeypatch.setattr(policy_text_module, "_run_policy_worker", timeout)

    with pytest.raises(ValueError, match="isolated execution time limit"):
        PolicyText(path)


def test_policy_search_is_linear_for_repeated_missing_terms() -> None:
    policy = object.__new__(PolicyText)
    policy.pages = ("a" * 40_000,)

    started = time.perf_counter()
    hits = policy.search("a a a a b")

    assert hits == []
    assert time.perf_counter() - started < 0.5


def test_policy_worker_transport_accepts_a_unicode_document_path(tmp_path: Path) -> None:
    path = tmp_path / "정책.pdf"
    _policy(path)

    policy = PolicyText(path)

    assert policy.pages and "five percent" in policy.pages[0]
