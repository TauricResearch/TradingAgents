"""Tests for the per-run trade-date clamp.

The clamp is the only thing preventing analysts from reading post-trade-date
data via tool calls — the model controls the date params, and the tools are
bound once into a static graph, so we cap LLM-supplied dates at run time
through a ContextVar.
"""

from unittest.mock import patch

import pytest

from tradingagents.agents.utils._date_clamp import (
    clamp,
    get_trade_date,
    maybe_note,
    reset_trade_date,
    set_trade_date,
)


@pytest.fixture
def trade_date():
    """Bind a known trade_date for the test and restore on teardown."""
    token = set_trade_date("2026-05-10")
    try:
        yield "2026-05-10"
    finally:
        reset_trade_date(token)


@pytest.mark.unit
class TestClampPureFunction:
    def test_passthrough_when_unset(self):
        # No trade_date bound — clamp is a no-op.
        assert get_trade_date() is None
        assert clamp("2099-01-01") == ("2099-01-01", False)

    def test_passthrough_when_input_none(self, trade_date):
        assert clamp(None) == (None, False)

    def test_passthrough_when_input_empty(self, trade_date):
        assert clamp("") == ("", False)

    def test_passthrough_when_unparseable(self, trade_date):
        # Bad input is returned untouched — dataflows already error on it.
        assert clamp("not-a-date") == ("not-a-date", False)

    def test_passthrough_when_before_trade_date(self, trade_date):
        assert clamp("2026-04-01") == ("2026-04-01", False)

    def test_passthrough_when_equal_to_trade_date(self, trade_date):
        assert clamp("2026-05-10") == ("2026-05-10", False)

    def test_clamps_when_after_trade_date(self, trade_date):
        assert clamp("2026-09-01") == ("2026-05-10", True)

    def test_clamp_logs_warning(self, trade_date, caplog):
        with caplog.at_level("WARNING"):
            clamp("2026-09-01", "end_date")
        assert any("end_date" in r.message and "2026-05-10" in r.message for r in caplog.records)


@pytest.mark.unit
class TestContextvarLifecycle:
    def test_set_and_reset_round_trip(self):
        assert get_trade_date() is None
        token = set_trade_date("2026-05-10")
        try:
            assert get_trade_date() == "2026-05-10"
        finally:
            reset_trade_date(token)
        assert get_trade_date() is None

    def test_nested_set_resets_to_outer(self):
        outer = set_trade_date("2026-01-01")
        try:
            inner = set_trade_date("2026-06-01")
            try:
                assert get_trade_date() == "2026-06-01"
            finally:
                reset_trade_date(inner)
            assert get_trade_date() == "2026-01-01"
        finally:
            reset_trade_date(outer)
        assert get_trade_date() is None


@pytest.mark.unit
class TestMaybeNote:
    def test_empty_when_not_clamped(self):
        assert maybe_note(False, "end_date") == ""

    def test_includes_label_and_asof_when_clamped(self, trade_date):
        note = maybe_note(True, "end_date")
        assert "end_date" in note
        assert "2026-05-10" in note
        assert note.endswith("\n\n")


# ---------------------------------------------------------------------------
# Integration with the @tool wrappers — confirms the clamp runs before
# route_to_vendor, so the vendor never sees a post-trade-date param.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestToolWrapperIntegration:
    def test_get_stock_data_clamps_end_date(self, trade_date):
        from tradingagents.agents.utils.core_stock_tools import get_stock_data

        with patch(
            "tradingagents.agents.utils.core_stock_tools.route_to_vendor",
            return_value="ok",
        ) as mock_route:
            result = get_stock_data.invoke({"symbol": "SPY", "start_date": "2026-04-01", "end_date": "2099-01-01"})

        mock_route.assert_called_once_with("get_stock_data", "SPY", "2026-04-01", "2026-05-10")
        assert "Note: end_date capped" in result
        assert "ok" in result

    def test_get_stock_data_passthrough_when_within_range(self, trade_date):
        from tradingagents.agents.utils.core_stock_tools import get_stock_data

        with patch(
            "tradingagents.agents.utils.core_stock_tools.route_to_vendor",
            return_value="ok",
        ) as mock_route:
            result = get_stock_data.invoke({"symbol": "SPY", "start_date": "2026-04-01", "end_date": "2026-05-01"})

        mock_route.assert_called_once_with("get_stock_data", "SPY", "2026-04-01", "2026-05-01")
        assert "Note:" not in result

    def test_get_news_clamps_end_date(self, trade_date):
        from tradingagents.agents.utils.news_data_tools import get_news

        with patch(
            "tradingagents.agents.utils.news_data_tools.route_to_vendor",
            return_value="ok",
        ) as mock_route:
            result = get_news.invoke({"ticker": "SPY", "start_date": "2026-04-01", "end_date": "2099-01-01"})

        mock_route.assert_called_once_with("get_news", "SPY", "2026-04-01", "2026-05-10")
        assert "Note: end_date capped" in result

    def test_get_global_news_clamps_curr_date(self, trade_date):
        from tradingagents.agents.utils.news_data_tools import get_global_news

        with patch(
            "tradingagents.agents.utils.news_data_tools.route_to_vendor",
            return_value="ok",
        ) as mock_route:
            result = get_global_news.invoke({"curr_date": "2099-01-01", "look_back_days": 7, "limit": 50})

        mock_route.assert_called_once_with("get_global_news", "2026-05-10", 7, 50)
        assert "Note: curr_date capped" in result

    def test_get_indicators_clamps_curr_date(self, trade_date):
        from tradingagents.agents.utils.technical_indicators_tools import get_indicators

        with patch(
            "tradingagents.agents.utils.technical_indicators_tools.route_to_vendor",
            return_value="ok",
        ) as mock_route:
            result = get_indicators.invoke(
                {
                    "symbol": "SPY",
                    "indicator": "rsi",
                    "curr_date": "2099-01-01",
                    "look_back_days": 30,
                }
            )

        mock_route.assert_called_once_with("get_indicators", "SPY", "rsi", "2026-05-10", 30)
        assert "Note: curr_date capped" in result

    def test_get_fundamentals_clamps_curr_date(self, trade_date):
        from tradingagents.agents.utils.fundamental_data_tools import get_fundamentals

        with patch(
            "tradingagents.agents.utils.fundamental_data_tools.route_to_vendor",
            return_value="ok",
        ) as mock_route:
            result = get_fundamentals.invoke({"ticker": "SPY", "curr_date": "2099-01-01"})

        mock_route.assert_called_once_with("get_fundamentals", "SPY", "2026-05-10")
        assert "Note: curr_date capped" in result

    def test_get_balance_sheet_clamps_curr_date(self, trade_date):
        from tradingagents.agents.utils.fundamental_data_tools import get_balance_sheet

        with patch(
            "tradingagents.agents.utils.fundamental_data_tools.route_to_vendor",
            return_value="ok",
        ) as mock_route:
            get_balance_sheet.invoke({"ticker": "SPY", "freq": "quarterly", "curr_date": "2099-01-01"})

        mock_route.assert_called_once_with("get_balance_sheet", "SPY", "quarterly", "2026-05-10")

    def test_get_insider_transactions_passes_asof(self, trade_date):
        from tradingagents.agents.utils.news_data_tools import get_insider_transactions

        with patch(
            "tradingagents.agents.utils.news_data_tools.route_to_vendor",
            return_value="ok",
        ) as mock_route:
            get_insider_transactions.invoke({"ticker": "SPY"})

        # Insider tool has no LLM-supplied date — it picks up the as-of from
        # the contextvar so the vendor can filter post-trade-date rows.
        mock_route.assert_called_once_with("get_insider_transactions", "SPY", as_of="2026-05-10")

    def test_get_insider_transactions_asof_none_when_unbound(self):
        from tradingagents.agents.utils.news_data_tools import get_insider_transactions

        assert get_trade_date() is None
        with patch(
            "tradingagents.agents.utils.news_data_tools.route_to_vendor",
            return_value="ok",
        ) as mock_route:
            get_insider_transactions.invoke({"ticker": "SPY"})

        mock_route.assert_called_once_with("get_insider_transactions", "SPY", as_of=None)

    def test_no_clamp_when_trade_date_unbound(self):
        # Outside propagate(), the tool should pass the model's date through
        # untouched — useful for ad-hoc shell use and tests that don't bind.
        from tradingagents.agents.utils.core_stock_tools import get_stock_data

        assert get_trade_date() is None
        with patch(
            "tradingagents.agents.utils.core_stock_tools.route_to_vendor",
            return_value="ok",
        ) as mock_route:
            result = get_stock_data.invoke({"symbol": "SPY", "start_date": "2026-04-01", "end_date": "2099-01-01"})

        mock_route.assert_called_once_with("get_stock_data", "SPY", "2026-04-01", "2099-01-01")
        assert "Note:" not in result


# ---------------------------------------------------------------------------
# Yfinance vendor: insider transactions filter when as_of is provided.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestYfinanceInsiderAsOf:
    def test_filters_rows_after_as_of(self):
        import pandas as pd

        from tradingagents.dataflows import y_finance

        frame = pd.DataFrame(
            {
                "Insider": ["A", "B", "C"],
                "Start Date": ["2026-01-01", "2026-05-01", "2099-01-01"],
                "Shares": [100, 200, 300],
            }
        )

        class _FakeTicker:
            insider_transactions = frame

        with patch.object(y_finance.yf, "Ticker", return_value=_FakeTicker()):
            result = y_finance.get_insider_transactions("SPY", as_of="2026-05-10")

        assert "2099-01-01" not in result
        assert "2026-05-01" in result
        assert "2026-01-01" in result

    def test_returns_helpful_message_when_filter_empties_frame(self):
        import pandas as pd

        from tradingagents.dataflows import y_finance

        frame = pd.DataFrame({"Insider": ["A"], "Start Date": ["2099-01-01"], "Shares": [100]})

        class _FakeTicker:
            insider_transactions = frame

        with patch.object(y_finance.yf, "Ticker", return_value=_FakeTicker()):
            result = y_finance.get_insider_transactions("SPY", as_of="2026-05-10")

        assert "on or before 2026-05-10" in result

    def test_no_filter_when_as_of_omitted(self):
        import pandas as pd

        from tradingagents.dataflows import y_finance

        frame = pd.DataFrame(
            {
                "Insider": ["A", "B"],
                "Start Date": ["2026-01-01", "2099-01-01"],
                "Shares": [100, 200],
            }
        )

        class _FakeTicker:
            insider_transactions = frame

        with patch.object(y_finance.yf, "Ticker", return_value=_FakeTicker()):
            result = y_finance.get_insider_transactions("SPY")

        assert "2099-01-01" in result
        assert "2026-01-01" in result
