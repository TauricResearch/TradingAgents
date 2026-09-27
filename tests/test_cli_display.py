"""What the live display shows, and what the run log keeps.

The display drops a message it judges empty, and the state log is written for a
person to read afterwards. Both got that wrong in ways that hide real content.
"""

from __future__ import annotations

import json
import unittest

import pytest

from cli.display import (
    AnalystWallTimeTracker,
    extract_content_string,
    sync_analyst_tracker_from_chunk,
)
from tradingagents.graph.analyst_execution import build_analyst_execution_plan


@pytest.mark.unit
@pytest.mark.parametrize("text", ["0", "False", "None", "[]", "{}", "0.0"])
def test_a_message_that_reads_like_a_python_value_is_still_text(text):
    """These were parsed as Python and judged empty, so the message vanished."""
    assert extract_content_string(text) == text


@pytest.mark.unit
@pytest.mark.parametrize("value, expected", [
    ("  Hold  ", "Hold"),
    ("", None),
    ("   ", None),
    (None, None),
    ([], None),
    ({}, None),
    ({"text": "from a dict"}, "from a dict"),
    ([{"type": "text", "text": "part one"}, {"type": "text", "text": "part two"}], "part one part two"),
])
def test_the_other_shapes_are_unchanged(value, expected):
    assert extract_content_string(value) == expected


def _state(ticker, final="评级: 买入"):
    return {
        "company_of_interest": ticker, "trade_date": "2026-09-01",
        "market_report": "市场", "sentiment_report": "情绪", "news_report": "新闻",
        "fundamentals_report": "基本面", "investment_plan": "计划",
        "trader_investment_plan": "交易计划", "final_trade_decision": final,
        "investment_debate_state": {"bull_history": "", "bear_history": "", "history": "",
                                    "current_response": "", "judge_decision": "", "count": 0},
        "risk_debate_state": {"aggressive_history": "", "conservative_history": "",
                              "neutral_history": "", "history": "", "judge_decision": "",
                              "latest_speaker": "", "current_aggressive_response": "",
                              "current_conservative_response": "", "current_neutral_response": "",
                              "count": 0},
    }


def _bare_graph(tmp_path):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"results_dir": str(tmp_path)}
    return graph


@pytest.mark.unit
def test_the_state_log_keeps_non_ascii_readable(tmp_path):
    """Reports can be in any language; the log is read by a person."""
    _bare_graph(tmp_path)._log_state("2026-09-01", _state("600519.SS"))

    written = next(tmp_path.rglob("full_states_log*.json")).read_text(encoding="utf-8")
    assert "买入" in written
    assert "\\u" not in written
    assert json.loads(written)  # still valid JSON


@pytest.mark.unit
def test_the_live_display_does_not_scroll_the_terminal():
    """A layout taller than the window makes rich redraw by scrolling, which
    reads as flicker; the alternate screen holds it in place (#784). The final
    report prints after the live view ends, so nothing is lost when it closes."""
    import inspect

    import cli.main as m

    assert "screen=True" in inspect.getsource(m.run_analysis)


class AnalystWallTimeTrackerTests(unittest.TestCase):
    def test_records_wall_time_when_analyst_completes(self):
        plan = build_analyst_execution_plan(["market", "news"])
        tracker = AnalystWallTimeTracker(plan)

        tracker.mark_started("market", started_at=10.0)
        tracker.mark_completed("market", completed_at=13.5)

        self.assertEqual(tracker.format_summary(), "Analyst wall time: Market 3.50s")

    def test_formats_summary_in_plan_order(self):
        plan = build_analyst_execution_plan(["news", "market"])
        tracker = AnalystWallTimeTracker(plan)

        tracker.mark_started("market", started_at=20.0)
        tracker.mark_completed("market", completed_at=22.25)
        tracker.mark_started("news", started_at=10.0)
        tracker.mark_completed("news", completed_at=14.0)

        self.assertEqual(
            tracker.format_summary(),
            "Analyst wall time: News 4.00s | Market 2.25s",
        )

    def test_syncs_wall_time_from_sequential_chunks(self):
        plan = build_analyst_execution_plan(["market", "news"])
        tracker = AnalystWallTimeTracker(plan)

        sync_analyst_tracker_from_chunk(tracker, {}, now=10.0)
        self.assertEqual(tracker.format_summary(), "Analyst wall time: pending")

        sync_analyst_tracker_from_chunk(
            tracker,
            {"market_report": "done"},
            now=13.0,
        )
        self.assertEqual(tracker.format_summary(), "Analyst wall time: Market 3.00s")

        sync_analyst_tracker_from_chunk(
            tracker,
            {"market_report": "done", "news_report": "done"},
            now=18.0,
        )
        self.assertEqual(tracker.format_summary(), "Analyst wall time: Market 3.00s | News 5.00s")
