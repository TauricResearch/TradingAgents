import tomllib
from pathlib import Path

from gui import export


def test_render_pdf_uses_matplotlib_pdf_backend():
    state = {
        "market_report": "Market details",
        "final_trade_decision": "BUY",
    }
    meta = {
        "ticker": "SPY",
        "trade_date": "2026-05-07",
        "decision": "BUY",
        "provider": "openai",
        "deep_model": "gpt-5.4",
        "quick_model": "gpt-5.4-mini",
        "run_id": "run-1",
    }

    pdf = export.render_pdf(state, meta)

    assert pdf.startswith(b"%PDF")
    assert export.has_pdf_support()


def test_gui_pdf_export_does_not_depend_on_xhtml2pdf():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    optional_dependencies = pyproject["project"]["optional-dependencies"]

    assert "xhtml2pdf>=0.2.13" not in optional_dependencies["gui"]
    assert "xhtml2pdf>=0.2.13" not in optional_dependencies["service"]
