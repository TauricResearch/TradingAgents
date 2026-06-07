from copy import deepcopy
from unittest import mock

import pytest

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.india import bse, flows, filings, macro, nse, yfinance_india
from tradingagents.dataflows.india.quality import (
    DataQuality,
    render_data_quality_block,
    unavailable_response,
)
from tradingagents.dataflows.india.symbols import IndiaSymbolError


@pytest.fixture(autouse=True)
def reset_dataflow_config():
    set_config(deepcopy(DEFAULT_CONFIG))
    yield
    set_config(deepcopy(DEFAULT_CONFIG))


@pytest.mark.unit
def test_data_quality_current_renders_source_coverage_and_warning():
    quality = DataQuality.current(
        "unit_test_source",
        coverage="mocked coverage",
        confidence="medium",
        warnings=["verify with official filings"],
    )

    assert quality.to_dict()["source"] == "unit_test_source"
    block = render_data_quality_block(quality)
    assert "Data quality:" in block
    assert "Source: unit_test_source" in block
    assert "Coverage: mocked coverage" in block
    assert "Warnings: verify with official filings" in block


@pytest.mark.unit
def test_unavailable_response_carries_no_fabrication_instruction():
    result = unavailable_response("NSE", "RELIANCE.NS", "blocked in test")
    assert result.startswith("UNAVAILABLE: blocked in test")
    assert "Symbol: RELIANCE.NS" in result
    assert "Confidence: unavailable" in result
    assert "Do not estimate or fabricate this data" in result


@pytest.mark.unit
def test_local_filings_reads_text_csv_and_lists_pdf(tmp_path):
    base = tmp_path / "RELIANCE.NS"
    (base / "concall").mkdir(parents=True)
    (base / "results").mkdir()
    (base / "annual_report").mkdir()
    (base / "concall" / "q1.txt").write_text("Management commentary", encoding="utf-8")
    (base / "results" / "q1.csv").write_text("quarter,revenue\nQ1FY26,100\n", encoding="utf-8")
    (base / "annual_report" / "fy25.pdf").write_bytes(b"%PDF-1.4")

    result = filings.get_local_filing_notes("RELIANCE", root=tmp_path)

    assert "# Local Filing Notes: RELIANCE.NS" in result
    assert "Management commentary" in result
    assert "| quarter | revenue |" in result
    assert "PDF files are present but OCR/heavy extraction is intentionally not enabled" in result
    assert "Coverage: 2 text/CSV/markdown file(s) read; 1 PDF file(s) listed without extraction" in result
    assert "Confidence: medium" in result


@pytest.mark.unit
def test_local_filings_missing_returns_unavailable(tmp_path):
    result = filings.get_local_filing_notes("RELIANCE.NS", root=tmp_path)
    assert result.startswith("UNAVAILABLE:")
    assert "No local filings found" in result
    assert "Confidence: unavailable" in result


@pytest.mark.unit
def test_local_filings_rejects_unsafe_symbol(tmp_path):
    with pytest.raises(IndiaSymbolError):
        filings.get_local_filing_notes("../RELIANCE", root=tmp_path)


@pytest.mark.unit
def test_yfinance_india_stock_data_normalizes_and_appends_quality(monkeypatch):
    called = {}

    def fake_stock_data(symbol, start_date, end_date):
        called["args"] = (symbol, start_date, end_date)
        return "mock ohlcv"

    monkeypatch.setattr(yfinance_india, "get_YFin_data_online", fake_stock_data)

    result = yfinance_india.get_india_stock_data("reliance", "2026-06-01", "2026-06-05")

    assert called["args"] == ("RELIANCE.NS", "2026-06-01", "2026-06-05")
    assert "mock ohlcv" in result
    assert "Source: yfinance_india" in result
    assert "Coverage: OHLCV 2026-06-01 to 2026-06-05" in result
    assert "Yahoo Finance is a third-party fallback source" in result
    assert "Symbol: RELIANCE.NS" in result


@pytest.mark.unit
def test_yfinance_india_rejects_non_india_before_vendor_call(monkeypatch):
    fake_stock_data = mock.Mock(return_value="should not be called")
    monkeypatch.setattr(yfinance_india, "get_YFin_data_online", fake_stock_data)

    with pytest.raises(IndiaSymbolError):
        yfinance_india.get_india_stock_data("AAPL", "2026-06-01", "2026-06-05")

    fake_stock_data.assert_not_called()


@pytest.mark.unit
def test_nse_bse_placeholders_are_unavailable_and_symbol_normalized():
    nse_result = nse.get_nse_corporate_announcements("RELIANCE", "2026-06-01", "2026-06-05")
    bse_result = bse.get_bse_results("RELIANCE.BO")

    assert nse_result.startswith("UNAVAILABLE:")
    assert "Symbol: RELIANCE.NS" in nse_result
    assert "Source: NSE" in nse_result
    assert "Do not estimate or fabricate this data" in nse_result

    assert bse_result.startswith("UNAVAILABLE:")
    assert "Symbol: RELIANCE.BO" in bse_result
    assert "Source: BSE" in bse_result


@pytest.mark.unit
def test_nse_bse_placeholders_reject_non_india_symbols():
    with pytest.raises(IndiaSymbolError):
        nse.get_nse_financial_results("AAPL", "2026-06-01", "2026-06-05")
    with pytest.raises(IndiaSymbolError):
        bse.get_bse_shareholding("SPY")


@pytest.mark.unit
def test_macro_context_is_explicitly_unavailable_with_configured_queries():
    result = macro.get_india_macro_context("2026-06-05", look_back_days=5)
    assert "UNAVAILABLE: Official RBI/MOSPI/DBIE macro datapoints are unavailable" in result
    assert "RBI monetary policy repo rate India liquidity" in result
    assert "Confidence: unavailable" in result


@pytest.mark.unit
def test_flows_interfaces_return_unavailable_sentinels():
    result = flows.get_fii_dii_cash_flows("5 days ending 2026-06-05")
    assert result.startswith("UNAVAILABLE:")
    assert "Symbol: FII_DII" in result
    assert "Source: India flows" in result
    assert "Do not estimate or fabricate this data" in result
