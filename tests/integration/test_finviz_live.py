"""Live integration tests for the Finviz smart-money screener tools.

These tests make REAL HTTP requests to finviz.com via the ``finvizfinance``
library and therefore require network access.  No API key is needed — Finviz
is a free public screener.

The entire module is skipped automatically when ``finvizfinance`` is not
installed in the current environment.

Run only the Finviz live tests:
    pytest tests/integration/test_finviz_live.py -v -m integration

Run all integration tests:
    pytest tests/integration/ -v -m integration

Skip in unit-only CI (default):
    pytest tests/ --ignore=tests/integration -v  # live tests never run
"""

import pytest

# ---------------------------------------------------------------------------
# Guard — skip every test in this file if finvizfinance is not installed.
# ---------------------------------------------------------------------------

try:
    import finvizfinance  # noqa: F401

    _finvizfinance_available = True
except ImportError:
    _finvizfinance_available = False

pytestmark = pytest.mark.integration

_skip_if_no_finviz = pytest.mark.skipif(
    not _finvizfinance_available,
    reason="finvizfinance not installed — skipping live Finviz tests",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_RESULT_PREFIXES = (
    "Top 5 stocks for ",
    "No stocks matched",
    "Smart money scan unavailable",
)


def _assert_valid_result(result: str, label: str) -> None:
    """Assert that *result* is a well-formed string from _run_finviz_screen."""
    assert isinstance(result, str), f"{label}: expected str, got {type(result)}"
    assert len(result) > 0, f"{label}: result is empty"
    assert any(result.startswith(prefix) for prefix in _VALID_RESULT_PREFIXES), (
        f"{label}: unexpected result format:\n{result}"
    )


def _assert_ticker_rows(result: str, label: str) -> None:
    """When results were found, every data row must have the expected shape."""
    if not result.startswith("Top 5 stocks for "):
        pytest.skip(f"{label}: no market data returned today — skipping row assertions")

    lines = result.strip().split("\n")
    # First line is the header "Top 5 stocks for …:"
    data_lines = [l for l in lines[1:] if l.strip()]
    assert len(data_lines) >= 1, f"{label}: header present but no data rows"

    for line in data_lines:
        # Expected shape: "- TICKER (Sector) @ $Price"
        assert line.startswith("- "), f"{label}: row missing '- ' prefix: {line!r}"
        assert "@" in line, f"{label}: row missing '@' separator: {line!r}"
        assert "$" in line, f"{label}: row missing '$' price marker: {line!r}"


# ---------------------------------------------------------------------------
# _run_finviz_screen helper (tested indirectly via the public tools)
# ---------------------------------------------------------------------------


@_skip_if_no_finviz
class TestRunFinvizScreen:
    """
    Tests for the shared ``_run_finviz_screen`` helper.
    Exercised indirectly through the public LangChain tool wrappers.
    """

    def test_returns_string(self):
        from tradingagents.agents.utils.scanner_tools import get_unusual_volume_stocks

        result = get_unusual_volume_stocks.invoke({})
        assert isinstance(result, str)

    def test_result_is_non_empty(self):
        from tradingagents.agents.utils.scanner_tools import get_unusual_volume_stocks

        result = get_unusual_volume_stocks.invoke({})
        assert len(result) > 0

    def test_result_has_valid_prefix(self):
        from tradingagents.agents.utils.scanner_tools import get_unusual_volume_stocks

        result = get_unusual_volume_stocks.invoke({})
        _assert_valid_result(result, "unusual_volume")


# ---------------------------------------------------------------------------
# get_insider_buying_stocks
# ---------------------------------------------------------------------------


@_skip_if_no_finviz
class TestGetInsiderBuyingStocks:
    """Live tests for the insider-buying screener tool."""

    def test_returns_string(self):
        from tradingagents.agents.utils.scanner_tools import get_insider_buying_stocks

        result = get_insider_buying_stocks.invoke({})
        assert isinstance(result, str)

    def test_result_is_non_empty(self):
        from tradingagents.agents.utils.scanner_tools import get_insider_buying_stocks

        result = get_insider_buying_stocks.invoke({})
        assert len(result) > 0

    def test_result_has_valid_prefix(self):
        from tradingagents.agents.utils.scanner_tools import get_insider_buying_stocks

        result = get_insider_buying_stocks.invoke({})
        _assert_valid_result(result, "insider_buying")

    def test_data_rows_have_expected_shape(self):
        from tradingagents.agents.utils.scanner_tools import get_insider_buying_stocks

        result = get_insider_buying_stocks.invoke({})
        _assert_ticker_rows(result, "insider_buying")

    def test_no_error_message_on_success(self):
        from tradingagents.agents.utils.scanner_tools import get_insider_buying_stocks

        result = get_insider_buying_stocks.invoke({})
        # If finviz returned data or an empty result, there should be no error
        if result.startswith("Top 5 stocks for ") or result.startswith("No stocks matched"):
            assert "Finviz error" not in result


# ---------------------------------------------------------------------------
# get_unusual_volume_stocks
# ---------------------------------------------------------------------------


@_skip_if_no_finviz
class TestGetUnusualVolumeStocks:
    """Live tests for the unusual-volume screener tool."""

    def test_returns_string(self):
        from tradingagents.agents.utils.scanner_tools import get_unusual_volume_stocks

        result = get_unusual_volume_stocks.invoke({})
        assert isinstance(result, str)

    def test_result_is_non_empty(self):
        from tradingagents.agents.utils.scanner_tools import get_unusual_volume_stocks

        result = get_unusual_volume_stocks.invoke({})
        assert len(result) > 0

    def test_result_has_valid_prefix(self):
        from tradingagents.agents.utils.scanner_tools import get_unusual_volume_stocks

        result = get_unusual_volume_stocks.invoke({})
        _assert_valid_result(result, "unusual_volume")

    def test_data_rows_have_expected_shape(self):
        from tradingagents.agents.utils.scanner_tools import get_unusual_volume_stocks

        result = get_unusual_volume_stocks.invoke({})
        _assert_ticker_rows(result, "unusual_volume")

    def test_no_error_message_on_success(self):
        from tradingagents.agents.utils.scanner_tools import get_unusual_volume_stocks

        result = get_unusual_volume_stocks.invoke({})
        if result.startswith("Top 5 stocks for ") or result.startswith("No stocks matched"):
            assert "Finviz error" not in result

    def test_tickers_are_uppercase(self):
        """When data is returned, all ticker symbols must be uppercase."""
        from tradingagents.agents.utils.scanner_tools import get_unusual_volume_stocks

        result = get_unusual_volume_stocks.invoke({})
        if not result.startswith("Top 5 stocks for "):
            pytest.skip("No data returned today")

        lines = result.strip().split("\n")[1:]
        for line in lines:
            if not line.strip():
                continue
            # "- TICKER (…) @ $…"
            ticker = line.lstrip("- ").split(" ")[0]
            assert ticker == ticker.upper(), f"Ticker not uppercase: {ticker!r}"


# ---------------------------------------------------------------------------
# get_breakout_accumulation_stocks
# ---------------------------------------------------------------------------


@_skip_if_no_finviz
class TestGetBreakoutAccumulationStocks:
    """Live tests for the breakout-accumulation screener tool."""

    def test_returns_string(self):
        from tradingagents.agents.utils.scanner_tools import get_breakout_accumulation_stocks

        result = get_breakout_accumulation_stocks.invoke({})
        assert isinstance(result, str)

    def test_result_is_non_empty(self):
        from tradingagents.agents.utils.scanner_tools import get_breakout_accumulation_stocks

        result = get_breakout_accumulation_stocks.invoke({})
        assert len(result) > 0

    def test_result_has_valid_prefix(self):
        from tradingagents.agents.utils.scanner_tools import get_breakout_accumulation_stocks

        result = get_breakout_accumulation_stocks.invoke({})
        _assert_valid_result(result, "breakout_accumulation")

    def test_data_rows_have_expected_shape(self):
        from tradingagents.agents.utils.scanner_tools import get_breakout_accumulation_stocks

        result = get_breakout_accumulation_stocks.invoke({})
        _assert_ticker_rows(result, "breakout_accumulation")

    def test_no_error_message_on_success(self):
        from tradingagents.agents.utils.scanner_tools import get_breakout_accumulation_stocks

        result = get_breakout_accumulation_stocks.invoke({})
        if result.startswith("Top 5 stocks for ") or result.startswith("No stocks matched"):
            assert "Finviz error" not in result

    def test_at_most_five_rows_returned(self):
        """The screener caps output at 5 rows (hardcoded head(5))."""
        from tradingagents.agents.utils.scanner_tools import get_breakout_accumulation_stocks

        result = get_breakout_accumulation_stocks.invoke({})
        if not result.startswith("Top 5 stocks for "):
            pytest.skip("No data returned today")

        lines = [l for l in result.strip().split("\n")[1:] if l.strip()]
        assert len(lines) <= 5, f"Expected ≤5 rows, got {len(lines)}"

    def test_price_column_is_numeric(self):
        """Price values after '$' must be parseable as floats."""
        from tradingagents.agents.utils.scanner_tools import get_breakout_accumulation_stocks

        result = get_breakout_accumulation_stocks.invoke({})
        if not result.startswith("Top 5 stocks for "):
            pytest.skip("No data returned today")

        lines = [l for l in result.strip().split("\n")[1:] if l.strip()]
        for line in lines:
            price_part = line.split("@ $")[-1].strip()
            float(price_part)  # raises ValueError if not numeric


# ---------------------------------------------------------------------------
# All three tools together — smoke test
# ---------------------------------------------------------------------------


@_skip_if_no_finviz
class TestAllThreeToolsSmoke:
    """Quick smoke test running all three tools sequentially."""

    def test_all_three_return_strings(self):
        from tradingagents.agents.utils.scanner_tools import (
            get_breakout_accumulation_stocks,
            get_insider_buying_stocks,
            get_unusual_volume_stocks,
        )

        tools = [
            (get_insider_buying_stocks, "insider_buying"),
            (get_unusual_volume_stocks, "unusual_volume"),
            (get_breakout_accumulation_stocks, "breakout_accumulation"),
        ]
        for tool_fn, label in tools:
            result = tool_fn.invoke({})
            assert isinstance(result, str), f"{label}: expected str"
            assert len(result) > 0, f"{label}: empty result"
            _assert_valid_result(result, label)
