import pytest

from tradingagents.web.models import AnalysisRequest
from tradingagents.web.preferences import MAX_RECENT_REQUESTS, latest_request, recent_requests, remember_request


def _request(ticker: str, quick: str = "gpt-5.4-mini") -> AnalysisRequest:
    return AnalysisRequest(
        ticker=ticker,
        analysis_date="2026-04-30",
        output_language="English",
        analysts=["market", "news"],
        research_depth=1,
        llm_provider="openai",
        backend_url="https://api.openai.com/v1",
        quick_think_llm=quick,
        deep_think_llm="gpt-5.4",
    )


@pytest.mark.unit
def test_remember_request_stores_latest_first(tmp_path):
    path = tmp_path / "prefs.json"

    remember_request(_request("SPY"), path)
    remember_request(_request("BTC-USD"), path)

    cached = recent_requests(path)
    assert [request.ticker for request in cached] == ["BTC-USD", "SPY"]
    assert latest_request(path).ticker == "BTC-USD"


@pytest.mark.unit
def test_remember_request_deduplicates_and_caps_entries(tmp_path):
    path = tmp_path / "prefs.json"

    for idx in range(MAX_RECENT_REQUESTS + 3):
        remember_request(_request(f"T{idx}"), path)
    remember_request(_request("T3"), path)

    cached = recent_requests(path)
    assert len(cached) == MAX_RECENT_REQUESTS
    assert cached[0].ticker == "T3"
    assert [request.ticker for request in cached].count("T3") == 1
