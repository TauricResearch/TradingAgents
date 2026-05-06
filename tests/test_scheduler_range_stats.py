"""Range-stats injection in scheduler._push_full_report."""

from unittest.mock import patch


def _fake_stats():
    return {
        "symbol": "AAPL", "trade_date": "2026-05-06",
        "today": {"effective_date": "2026-05-06",
                  "open": 100.0, "close": 101.0, "volume": 1_000_000},
        "metrics": {
            m: {w: {"low": 90.0, "high": 110.0,
                    "pct_above_low": 12.2, "pct_below_high": -8.2, "position_pct": 55.0}
                for w in ("52w", "6m", "3m", "1m")}
            for m in ("open", "close", "volume")
        },
    }


def _stub_state():
    """Minimal full state shape that _push_full_report consumes."""
    return {
        "market_report": "stub-market",
        "fundamentals_report": "stub-fund",
        "sentiment_report": "stub-sent",
        "news_report": "stub-news",
        "investment_plan": "stub-plan",
        "trader_investment_decision": "stub-trader",
        "investment_debate_state": {},
        "risk_debate_state": {},
    }


def test_full_report_includes_range_stats_block_when_available():
    import scheduler

    sent: list[str] = []

    def _capture(chat_id, msg, **_):
        sent.append(msg)
        return True, "ok"

    with patch("scheduler.notify.send_telegram", side_effect=_capture), \
         patch("scheduler._load_full_state", return_value=_stub_state()), \
         patch("scheduler.compute_range_stats", return_value=_fake_stats()):
        scheduler._push_full_report(
            chat_id="123",
            slug="usr",
            ticker="AAPL",
            trade_date="2026-05-06",
            decision="BUY",
        )
    assert any("📊 Range Stats" in m for m in sent), \
        f"Expected a range-stats block in sent messages: {sent}"


def test_full_report_skips_range_stats_block_when_unavailable():
    import scheduler
    from tradingagents.dataflows.range_stats import RangeStatsUnavailable

    sent: list[str] = []

    def _capture(chat_id, msg, **_):
        sent.append(msg)
        return True, "ok"

    with patch("scheduler.notify.send_telegram", side_effect=_capture), \
         patch("scheduler._load_full_state", return_value=_stub_state()), \
         patch("scheduler.compute_range_stats", side_effect=RangeStatsUnavailable("x")):
        scheduler._push_full_report(
            chat_id="123",
            slug="usr",
            ticker="AAPL",
            trade_date="2026-05-06",
            decision="BUY",
        )
    assert not any("📊 Range Stats" in m for m in sent), \
        f"Range-stats block should be omitted when compute fails: {sent}"


def test_full_report_skips_range_stats_block_on_unexpected_exception():
    """Generic exception in compute_range_stats must not abort the report."""
    import scheduler

    sent: list[str] = []

    def _capture(chat_id, msg, **_):
        sent.append(msg)
        return True, "ok"

    with patch("scheduler.notify.send_telegram", side_effect=_capture), \
         patch("scheduler._load_full_state", return_value=_stub_state()), \
         patch("scheduler.compute_range_stats", side_effect=RuntimeError("boom")):
        scheduler._push_full_report(
            chat_id="123",
            slug="usr",
            ticker="AAPL",
            trade_date="2026-05-06",
            decision="BUY",
        )
    # The headline must still go out even if range-stats blew up.
    assert any("AAPL" in m and "Decision" in m for m in sent), \
        f"Headline should always be sent: {sent}"
    # No range-stats block.
    assert not any("📊 Range Stats" in m for m in sent), sent
