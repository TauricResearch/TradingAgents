import io

import pytest


def test_extract_text_from_markdown():
    from tradingagents.dataflows.user_research import _extract_text
    raw = "# Hello\n\nThis is *markdown*.".encode("utf-8")
    assert _extract_text(raw, "note.md").strip() == "# Hello\n\nThis is *markdown*.".strip()


def test_extract_text_from_txt():
    from tradingagents.dataflows.user_research import _extract_text
    raw = b"plain text content"
    assert _extract_text(raw, "note.txt").strip() == "plain text content"


def test_extract_text_from_pdf_with_text(tmp_path):
    """Synthesize a real PDF with a known text payload via reportlab.

    Skipped if reportlab is not installed (no shipped fixture)."""
    pytest.importorskip("reportlab", reason="reportlab needed to synthesize a PDF in-test")
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "TradingAgents test report content marker xyzzy123")
    c.save()
    pdf_bytes = buf.getvalue()

    from tradingagents.dataflows.user_research import _extract_text
    text = _extract_text(pdf_bytes, "report.pdf")
    assert "xyzzy123" in text


def test_extract_text_unsupported_extension():
    from tradingagents.dataflows.user_research import (
        _extract_text,
        ResearchExtractionError,
    )
    with pytest.raises(ResearchExtractionError):
        _extract_text(b"bytes", "weird.docx")


def test_extract_text_corrupt_pdf_raises():
    from tradingagents.dataflows.user_research import (
        _extract_text,
        ResearchExtractionError,
    )
    with pytest.raises(ResearchExtractionError):
        _extract_text(b"not a real pdf", "broken.pdf")
