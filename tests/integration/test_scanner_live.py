"""Integration tests for scanner data functions — require network access.

These tests hit real yfinance and vendor APIs. Excluded from default pytest run.

Run with:
    pytest tests/integration/ -v          # all integration tests
    pytest tests/integration/ -v -m integration  # integration-marked only
"""

import pytest


# ---------------------------------------------------------------------------
# Scanner tool tests (yfinance-backed)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_market_movers_day_gainers():
    from tradingagents.agents.utils.scanner_tools import get_market_movers

    result = get_market_movers.invoke({"category": "day_gainers"})
    assert isinstance(result, str)
    assert "# Market Movers:" in result
    assert "| Symbol |" in result


@pytest.mark.integration
def test_market_movers_day_losers():
    from tradingagents.agents.utils.scanner_tools import get_market_movers

    result = get_market_movers.invoke({"category": "day_losers"})
    assert isinstance(result, str)
    assert "# Market Movers:" in result
    assert "| Symbol |" in result


@pytest.mark.integration
def test_market_movers_most_actives():
    from tradingagents.agents.utils.scanner_tools import get_market_movers

    result = get_market_movers.invoke({"category": "most_actives"})
    assert isinstance(result, str)
    assert "# Market Movers:" in result
    assert "| Symbol |" in result


@pytest.mark.integration
def test_market_indices():
    from tradingagents.agents.utils.scanner_tools import get_market_indices

    result = get_market_indices.invoke({})
    assert isinstance(result, str)
    assert "# Major Market Indices" in result
    assert "| Index |" in result
    assert "S&P 500" in result
    assert "Dow Jones" in result


@pytest.mark.integration
def test_sector_performance():
    from tradingagents.agents.utils.scanner_tools import get_sector_performance

    result = get_sector_performance.invoke({})
    assert isinstance(result, str)
    assert "# Sector Performance Overview" in result
    assert "| Sector |" in result


@pytest.mark.integration
def test_industry_performance_technology():
    from tradingagents.agents.utils.scanner_tools import get_industry_performance

    result = get_industry_performance.invoke({"sector_key": "technology"})
    assert isinstance(result, str)
    assert "# Industry Performance: Technology" in result
    assert "| Company |" in result


@pytest.mark.integration
def test_topic_news():
    from tradingagents.agents.utils.scanner_tools import get_topic_news

    result = get_topic_news.invoke({"topic": "market", "limit": 3})
    assert isinstance(result, str)
    assert "# News for Topic: market" in result
    assert len(result) > 100


# ---------------------------------------------------------------------------
# yfinance dataflow tests (direct function calls)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_yfinance_sector_performance_all_11_sectors():
    from tradingagents.dataflows.yfinance_scanner import get_sector_performance_yfinance

    result = get_sector_performance_yfinance()
    assert "| Sector |" in result
    for sector in [
        "Technology", "Healthcare", "Financials", "Energy",
        "Consumer Discretionary", "Consumer Staples", "Industrials",
        "Materials", "Real Estate", "Utilities", "Communication Services",
    ]:
        assert sector in result, f"Missing sector: {sector}"


@pytest.mark.integration
def test_yfinance_sector_performance_numeric_percentages():
    from tradingagents.dataflows.yfinance_scanner import get_sector_performance_yfinance

    result = get_sector_performance_yfinance()
    lines = result.strip().split("\n")
    data_lines = [
        l for l in lines
        if l.startswith("| ") and "Sector" not in l and "---" not in l
    ]
    assert len(data_lines) == 11, f"Expected 11 data rows, got {len(data_lines)}"
    for line in data_lines:
        cols = [c.strip() for c in line.split("|")[1:-1]]
        assert len(cols) == 5, f"Expected 5 columns in: {line}"
        day_pct = cols[1]
        assert "%" in day_pct or day_pct == "N/A", f"Bad 1-day value: {day_pct}"


@pytest.mark.integration
def test_yfinance_industry_performance_real_symbols():
    from tradingagents.dataflows.yfinance_scanner import get_industry_performance_yfinance

    result = get_industry_performance_yfinance("technology")
    assert "| Company |" in result or "| Company " in result
    assert "NVDA" in result or "AAPL" in result or "MSFT" in result


@pytest.mark.integration
def test_yfinance_industry_performance_no_na_symbols():
    from tradingagents.dataflows.yfinance_scanner import get_industry_performance_yfinance

    result = get_industry_performance_yfinance("technology")
    lines = result.strip().split("\n")
    data_lines = [
        l for l in lines
        if l.startswith("| ") and "Company" not in l and "---" not in l
    ]
    for line in data_lines:
        cols = [c.strip() for c in line.split("|")[1:-1]]
        assert cols[1] != "N/A", f"Symbol is N/A in line: {line}"


@pytest.mark.integration
def test_yfinance_industry_performance_healthcare():
    from tradingagents.dataflows.yfinance_scanner import get_industry_performance_yfinance

    result = get_industry_performance_yfinance("healthcare")
    assert "Industry Performance: Healthcare" in result


@pytest.mark.integration
def test_yfinance_industry_performance_price_columns():
    from tradingagents.dataflows.yfinance_scanner import get_industry_performance_yfinance

    result = get_industry_performance_yfinance("technology")
    assert "# Industry Performance: Technology" in result
    assert "1-Day %" in result
    assert "1-Week %" in result
    assert "1-Month %" in result


@pytest.mark.integration
def test_yfinance_industry_performance_seven_columns():
    from tradingagents.dataflows.yfinance_scanner import get_industry_performance_yfinance

    result = get_industry_performance_yfinance("technology")
    lines = result.strip().split("\n")
    sep_lines = [l for l in lines if l.startswith("|") and "---" in l]
    assert len(sep_lines) >= 1
    cols = [c.strip() for c in sep_lines[0].split("|")[1:-1]]
    assert len(cols) == 7, f"Expected 7 columns, got {len(cols)}: {cols}"


# ---------------------------------------------------------------------------
# Vendor fallback integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_route_to_vendor_sector_performance():
    from tradingagents.dataflows.interface import route_to_vendor

    result = route_to_vendor("get_sector_performance")
    assert "Sector Performance Overview" in result


@pytest.mark.integration
def test_route_to_vendor_industry_performance():
    from tradingagents.dataflows.interface import route_to_vendor

    result = route_to_vendor("get_industry_performance", "technology")
    assert "Industry Performance" in result


# ---------------------------------------------------------------------------
# Vendor routing tests (moved from tests/unit/test_scanner_routing.py)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestScannerRouting:
    """Verify that scanner_data=alpha_vantage routes to AV implementations."""

    def setup_method(self):
        """Set config to use alpha_vantage for scanner_data."""
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.dataflows.config import set_config

        config = DEFAULT_CONFIG.copy()
        config["data_vendors"]["scanner_data"] = "alpha_vantage"
        set_config(config)

    def test_vendor_resolves_to_alpha_vantage(self):
        from tradingagents.dataflows.interface import get_vendor

        vendor = get_vendor("scanner_data")
        assert vendor == "alpha_vantage"

    def test_market_movers_routes_to_av(self, av_api_key):
        from tradingagents.dataflows.interface import route_to_vendor

        result = route_to_vendor("get_market_movers", "day_gainers")
        assert isinstance(result, str)
        assert "Market Movers" in result

    def test_market_indices_routes_to_av(self, av_api_key):
        from tradingagents.dataflows.interface import route_to_vendor

        result = route_to_vendor("get_market_indices")
        assert isinstance(result, str)
        assert "Market Indices" in result or "Index" in result

    def test_sector_performance_routes_to_av(self, av_api_key):
        from tradingagents.dataflows.interface import route_to_vendor

        result = route_to_vendor("get_sector_performance")
        assert isinstance(result, str)
        assert "Sector" in result

    def test_industry_performance_routes_to_av(self, av_api_key):
        from tradingagents.dataflows.interface import route_to_vendor

        result = route_to_vendor("get_industry_performance", "technology")
        assert isinstance(result, str)
        assert "|" in result

    def test_topic_news_routes_to_av(self, av_api_key):
        from tradingagents.dataflows.interface import route_to_vendor

        result = route_to_vendor("get_topic_news", "market", limit=3)
        assert isinstance(result, str)
        assert "News" in result


@pytest.mark.integration
class TestFallbackRouting:
    """Verify that scanner_data=yfinance routes to yfinance implementations."""

    def setup_method(self):
        """Set config to use yfinance for scanner_data."""
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.dataflows.config import set_config

        config = DEFAULT_CONFIG.copy()
        config["data_vendors"]["scanner_data"] = "yfinance"
        set_config(config)

    def test_yfinance_fallback_works(self):
        """When configured for yfinance, scanner tools should use yfinance."""
        from tradingagents.dataflows.interface import route_to_vendor

        result = route_to_vendor("get_market_movers", "day_gainers")
        assert isinstance(result, str)
        assert "Market Movers" in result
