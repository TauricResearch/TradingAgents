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

from functools import cache

import pytest
import requests

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


# Cache each live tool invocation once per module to avoid 20+ repeated
# external calls in this test file.
@cache
def _cached_live_tool_output(tool_name: str) -> str:
    from tradingagents.agents.utils import scanner_tools as _scanner_tools
    return getattr(_scanner_tools, tool_name).invoke({})

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


_INVALID_FILTER_MARKER = "Invalid filter"


def _assert_no_invalid_filter_error(result: str, label: str) -> None:
    """Assert result does not contain a Finviz 'Invalid filter' error.

    Distinguishes code bugs (wrong filter name/value hardcoded in the tool)
    from acceptable transient failures (network errors, rate limits).
    Catches both 'Invalid filter 'name'' and 'Invalid filter option 'value''.
    """
    assert _INVALID_FILTER_MARKER not in result, (
        f"{label}: Finviz filter string is invalid — this is a code bug, "
        f"not a transient network issue:\n{result}"
    )


def _assert_ticker_rows(result: str, label: str) -> None:
    """When results were found, every data row must have the expected shape."""
    if not result.startswith("Top 5 stocks for "):
        pytest.skip(f"{label}: no market data returned today — skipping row assertions")

    lines = result.strip().split("\n")
    # First line is the header "Top 5 stocks for …:"
    data_lines = [line for line in lines[1:] if line.strip()]
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

        result = _cached_live_tool_output("get_unusual_volume_stocks")
        assert isinstance(result, str)

    def test_result_is_non_empty(self):

        result = _cached_live_tool_output("get_unusual_volume_stocks")
        assert len(result) > 0

    def test_result_has_valid_prefix(self):

        result = _cached_live_tool_output("get_unusual_volume_stocks")
        _assert_valid_result(result, "unusual_volume")


# ---------------------------------------------------------------------------
# get_insider_buying_stocks
# ---------------------------------------------------------------------------


@_skip_if_no_finviz
class TestGetInsiderBuyingStocks:
    """Live tests for the insider-buying screener tool."""

    def test_returns_string(self):

        result = _cached_live_tool_output("get_insider_buying_stocks")
        assert isinstance(result, str)

    def test_result_is_non_empty(self):

        result = _cached_live_tool_output("get_insider_buying_stocks")
        assert len(result) > 0

    def test_result_has_valid_prefix(self):

        result = _cached_live_tool_output("get_insider_buying_stocks")
        _assert_valid_result(result, "insider_buying")

    def test_data_rows_have_expected_shape(self):

        result = _cached_live_tool_output("get_insider_buying_stocks")
        _assert_ticker_rows(result, "insider_buying")

    def test_no_error_message_on_success(self):

        result = _cached_live_tool_output("get_insider_buying_stocks")
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

        result = _cached_live_tool_output("get_unusual_volume_stocks")
        assert isinstance(result, str)

    def test_result_is_non_empty(self):

        result = _cached_live_tool_output("get_unusual_volume_stocks")
        assert len(result) > 0

    def test_result_has_valid_prefix(self):

        result = _cached_live_tool_output("get_unusual_volume_stocks")
        _assert_valid_result(result, "unusual_volume")

    def test_data_rows_have_expected_shape(self):

        result = _cached_live_tool_output("get_unusual_volume_stocks")
        _assert_ticker_rows(result, "unusual_volume")

    def test_no_error_message_on_success(self):

        result = _cached_live_tool_output("get_unusual_volume_stocks")
        if result.startswith("Top 5 stocks for ") or result.startswith("No stocks matched"):
            assert "Finviz error" not in result

    def test_tickers_are_uppercase(self):
        """When data is returned, all ticker symbols must be uppercase."""

        result = _cached_live_tool_output("get_unusual_volume_stocks")
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

        result = _cached_live_tool_output("get_breakout_accumulation_stocks")
        assert isinstance(result, str)

    def test_result_is_non_empty(self):

        result = _cached_live_tool_output("get_breakout_accumulation_stocks")
        assert len(result) > 0

    def test_result_has_valid_prefix(self):

        result = _cached_live_tool_output("get_breakout_accumulation_stocks")
        _assert_valid_result(result, "breakout_accumulation")

    def test_data_rows_have_expected_shape(self):

        result = _cached_live_tool_output("get_breakout_accumulation_stocks")
        _assert_ticker_rows(result, "breakout_accumulation")

    def test_no_error_message_on_success(self):

        result = _cached_live_tool_output("get_breakout_accumulation_stocks")
        if result.startswith("Top 5 stocks for ") or result.startswith("No stocks matched"):
            assert "Finviz error" not in result

    def test_at_most_five_rows_returned(self):
        """The screener caps output at 5 rows (hardcoded head(5))."""

        result = _cached_live_tool_output("get_breakout_accumulation_stocks")
        if not result.startswith("Top 5 stocks for "):
            pytest.skip("No data returned today")

        lines = [line for line in result.strip().split("\n")[1:] if line.strip()]
        assert len(lines) <= 5, f"Expected ≤5 rows, got {len(lines)}"

    def test_price_column_is_numeric(self):
        """Price values after '$' must be parseable as floats."""

        result = _cached_live_tool_output("get_breakout_accumulation_stocks")
        if not result.startswith("Top 5 stocks for "):
            pytest.skip("No data returned today")

        lines = [line for line in result.strip().split("\n")[1:] if line.strip()]
        for line in lines:
            price_part = line.split("@ $")[-1].strip()
            float(price_part)  # raises ValueError if not numeric


# ---------------------------------------------------------------------------
# All three tools together — smoke test
# ---------------------------------------------------------------------------


@_skip_if_no_finviz
class TestNoInvalidFilterErrors:
    """Assert that none of the three tools produce an 'Invalid filter' error.

    The existing tests accept 'Smart money scan unavailable' as a valid result
    to tolerate network/rate-limit failures.  This class tightens that: it
    rejects results where Finviz rejected the *filter name itself* (a code bug
    in the hardcoded filter dict), while still permitting genuine transient
    failures.  All calls hit the real finviz.com — no mocks.
    """

    def test_insider_buying_filter_is_valid(self):

        result = _cached_live_tool_output("get_insider_buying_stocks")
        _assert_no_invalid_filter_error(result, "insider_buying")

    def test_unusual_volume_filter_is_valid(self):

        result = _cached_live_tool_output("get_unusual_volume_stocks")
        _assert_no_invalid_filter_error(result, "unusual_volume")

    def test_breakout_accumulation_filter_is_valid(self):

        result = _cached_live_tool_output("get_breakout_accumulation_stocks")
        _assert_no_invalid_filter_error(result, "breakout_accumulation")

    def test_all_three_tools_no_invalid_filter(self):
        """Single test exercising all three tools — useful for quick CI smoke run."""
        tools = [
            ("get_insider_buying_stocks", "insider_buying"),
            ("get_unusual_volume_stocks", "unusual_volume"),
            ("get_breakout_accumulation_stocks", "breakout_accumulation"),
        ]
        for tool_name, label in tools:
            result = _cached_live_tool_output(tool_name)
            _assert_no_invalid_filter_error(result, label)


@_skip_if_no_finviz
class TestAllThreeToolsSmoke:
    """Quick smoke test running all three tools sequentially."""

    def test_all_three_return_strings(self):
        tools = [
            ("get_insider_buying_stocks", "insider_buying"),
            ("get_unusual_volume_stocks", "unusual_volume"),
            ("get_breakout_accumulation_stocks", "breakout_accumulation"),
        ]
        for tool_name, label in tools:
            result = _cached_live_tool_output(tool_name)
            assert isinstance(result, str), f"{label}: expected str"
            assert len(result) > 0, f"{label}: empty result"
            _assert_valid_result(result, label)


@pytest.mark.enable_socket()
class TestFinvizVixFuturesLive:
    """Live checks for direct Finviz VX futures page access.

    This validates that we can reach the futures endpoint directly (not only
    equity quote pages) and that returned HTML includes expected VX/VIX context.
    """

    def test_vx_futures_page_is_reachable_and_has_vix_context(self):
        url = "https://finviz.com/futures_charts.ashx?t=VX&p=h"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/115.0.0.0 Safari/537.36"
            )
        }

        try:
            response = requests.get(url, headers=headers, timeout=20)
        except requests.RequestException as exc:
            pytest.skip(f"Finviz futures endpoint not reachable: {exc}")

        assert response.status_code == 200, (
            f"Expected 200 from Finviz futures endpoint, got {response.status_code}"
        )

        html = response.text
        html_lower = html.lower()
        assert "access denied" not in html_lower, "Finviz blocked the request"
        assert "captcha" not in html_lower, "Finviz returned anti-bot challenge"

        # Stable page-level checks avoid fragile CSS-selector coupling.
        assert "<title>" in html_lower and "</title>" in html_lower
        assert "futures" in html_lower
        assert "vix" in html_lower

        # Confirm there is at least one percentage value on the page.
        import re

        pct_matches = re.findall(r"[-+]?\d+(?:\.\d+)?%", html)
        print(f"Finviz VX futures percentage tokens (sample): {pct_matches[:5]}")
        assert pct_matches, "Expected percentage values on Finviz VX futures page"
