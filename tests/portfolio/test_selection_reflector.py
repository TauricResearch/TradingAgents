import pytest
import pandas as pd
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage
from tradingagents.portfolio.selection_reflector import (
    fetch_price_trend, fetch_news_summary, generate_lesson, reflect_on_scan
)

@pytest.fixture
def mock_yf_download(monkeypatch):
    def _mock_download(tickers, start, end, **kwargs):
        dates = pd.date_range(start, periods=5)
        # Ticker goes up then down
        ticker_closes = [100.0, 110.0, 105.0, 90.0, 85.0]
        # SPY goes up steadily
        spy_closes = [400.0, 402.0, 405.0, 407.0, 410.0]

        df = pd.DataFrame({
            "AAPL": ticker_closes,
            "SPY": spy_closes
        }, index=dates)

        return df

    monkeypatch.setattr("yfinance.download", _mock_download)
    return _mock_download

def test_fetch_price_data_normal(mock_yf_download):
    terminal_return, spy_return, mfe_pct, mae_pct, days_to_peak, top_move_dates = fetch_price_trend("AAPL", "2025-01-01", "2025-01-05")

    assert terminal_return == pytest.approx(-15.0)  # (85 - 100) / 100 * 100
    assert spy_return == pytest.approx(2.5)      # (410 - 400) / 400 * 100
    assert mfe_pct == pytest.approx(10.0)     # (110 - 100) / 100 * 100
    assert mae_pct == pytest.approx(-15.0)    # (85 - 100) / 100 * 100
    assert days_to_peak == 1                  # Peak is at index 1 (2025-01-02)
    assert len(top_move_dates) == 3

def test_fetch_price_data_single_day(monkeypatch):
    monkeypatch.setattr("yfinance.download", lambda *args, **kwargs: pd.DataFrame({"AAPL": [100.0], "SPY": [400.0]}))
    terminal_return, spy_return, mfe_pct, mae_pct, days_to_peak, top_move_dates = fetch_price_trend("AAPL", "2025-01-01", "2025-01-01")
    assert terminal_return is None
    assert spy_return is None
    assert mfe_pct is None
    assert mae_pct is None
    assert days_to_peak is None
    assert top_move_dates == []

def test_fetch_news_summary_weighted(monkeypatch):
    def mock_get_company_news(ticker, start, end):
        if start == "2025-01-01":
            return "- Start news 1\n- Start news 2\n- Start news 3"
        elif start == "2025-01-02":
            return "- Top move 1\n- Top move 1b"
        elif start == "2025-01-04":
            return "- Top move 2"
        return ""
    monkeypatch.setattr("tradingagents.portfolio.selection_reflector.get_company_news", mock_get_company_news)

    summary = fetch_news_summary("AAPL", "2025-01-01", "2025-01-05", ["2025-01-02", "2025-01-04"])
    assert "- Start news 1" in summary
    assert "- Start news 2" in summary
    assert "- Start news 3" not in summary  # Only taking 2 start news
    assert "- Top move 1" in summary
    assert "- Top move 1b" not in summary # Only taking 1 from each top move date
    assert "- Top move 2" in summary

def test_generate_lesson_valid():
    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content='```json\n{"situation": "test sit", "screening_advice": "test screen", "exit_advice": "test exit", "sentiment": "negative"}\n```')

    cand = {"ticker": "AAPL", "sector": "Tech", "thesis_angle": "growth", "rationale": "good", "conviction": "high"}

    lesson = generate_lesson(llm, cand, -10.0, 2.0, 5.0, -12.0, 5, "news", 30)

    assert lesson is not None
    assert lesson["situation"] == "test sit"
    assert lesson["screening_advice"] == "test screen"
    assert lesson["exit_advice"] == "test exit"
    assert lesson["sentiment"] == "negative"

def test_generate_lesson_mfe_mae_in_prompt():
    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content='{"situation": "a", "screening_advice": "b", "exit_advice": "c", "sentiment": "neutral"}')

    cand = {"ticker": "AAPL"}
    generate_lesson(llm, cand, -10.0, 2.0, 5.1, -12.2, 5, "news", 30)

    call_args = llm.invoke.call_args[0][0]
    prompt_text = call_args[0].content

    assert "MFE): +5.1%" in prompt_text
    assert "MAE): -12.2%" in prompt_text
    assert "Day 5" in prompt_text

def test_generate_lesson_bad_json():
    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content='Not a JSON')

    lesson = generate_lesson(llm, {}, -10.0, 2.0, 5.0, -12.0, 5, "news", 30)
    assert lesson is None

def test_reflect_on_scan_no_file(monkeypatch):
    llm = MagicMock()
    monkeypatch.setattr("tradingagents.portfolio.selection_reflector.load_scan_candidates", lambda date: [])
    lessons = reflect_on_scan("2025-01-01", "2025-01-31", llm, 30)
    assert lessons == []
