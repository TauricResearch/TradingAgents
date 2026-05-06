from unittest.mock import patch


def test_tool_returns_markdown_when_compute_succeeds():
    from tradingagents.agents.utils.range_stats_tool import get_range_stats

    fake_stats = {
        "symbol": "AAPL",
        "trade_date": "2026-05-06",
        "today": {"effective_date": "2026-05-06",
                  "open": 100.0, "close": 101.0, "volume": 1000000},
        "metrics": {
            m: {w: {"low": 90, "high": 110,
                    "pct_above_low": 12.2, "pct_below_high": -8.2, "position_pct": 55.0}
                for w in ("52w", "6m", "3m", "1m")}
            for m in ("open", "close", "volume")
        },
    }
    with patch("tradingagents.agents.utils.range_stats_tool.compute_range_stats",
               return_value=fake_stats):
        result = get_range_stats.invoke({"symbol": "AAPL", "trade_date": "2026-05-06"})
    assert "Range Stats for AAPL" in result
    assert "## Close" in result


def test_tool_returns_friendly_string_when_compute_unavailable():
    from tradingagents.agents.utils.range_stats_tool import get_range_stats
    from tradingagents.dataflows.range_stats import RangeStatsUnavailable

    with patch("tradingagents.agents.utils.range_stats_tool.compute_range_stats",
               side_effect=RangeStatsUnavailable("nope")):
        result = get_range_stats.invoke({"symbol": "ZZZ", "trade_date": "2026-05-06"})
    assert "unavailable" in result.lower()
    assert "ZZZ" in result
