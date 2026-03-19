"""Tests for the Industry Deep Dive improvements:

1. _extract_top_sectors() parses sector performance reports correctly
2. Enriched get_industry_performance_yfinance returns price columns
3. run_tool_loop nudge triggers when first response is short & no tool calls
"""

import pytest
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tradingagents.agents.scanners.industry_deep_dive import (
    VALID_SECTOR_KEYS,
    _DISPLAY_TO_KEY,
    _extract_top_sectors,
)
from tradingagents.agents.utils.tool_runner import (
    run_tool_loop,
    MAX_TOOL_ROUNDS,
    MIN_REPORT_LENGTH,
)


# ---------------------------------------------------------------------------
# _extract_top_sectors tests
# ---------------------------------------------------------------------------

SAMPLE_SECTOR_REPORT = """\
# Sector Performance Overview
# Data retrieved on: 2026-03-17 12:00:00

| Sector | 1-Day % | 1-Week % | 1-Month % | YTD % |
|--------|---------|----------|-----------|-------|
| Technology | +0.45% | +1.20% | +5.67% | +12.30% |
| Healthcare | -0.12% | -0.50% | -2.10% | +3.40% |
| Financials | +0.30% | +0.80% | +3.25% | +8.10% |
| Energy | +1.10% | +2.50% | +7.80% | +15.20% |
| Consumer Discretionary | -0.20% | -0.10% | -1.50% | +2.00% |
| Consumer Staples | +0.05% | +0.30% | +0.90% | +4.50% |
| Industrials | +0.25% | +0.60% | +2.80% | +6.70% |
| Materials | +0.40% | +1.00% | +4.20% | +9.30% |
| Real Estate | -0.35% | -0.80% | -3.40% | -1.20% |
| Utilities | +0.10% | +0.20% | +1.10% | +5.60% |
| Communication Services | +0.55% | +1.50% | +6.30% | +11.00% |
"""


class TestExtractTopSectors:
    """Verify _extract_top_sectors parses the table correctly."""

    def test_returns_top_3_by_absolute_1month(self):
        result = _extract_top_sectors(SAMPLE_SECTOR_REPORT, top_n=3)
        assert len(result) == 3
        # Energy (+7.80%), Communication Services (+6.30%), Technology (+5.67%)
        assert result[0] == "energy"
        assert result[1] == "communication-services"
        assert result[2] == "technology"

    def test_returns_top_n_variable(self):
        result = _extract_top_sectors(SAMPLE_SECTOR_REPORT, top_n=5)
        assert len(result) == 5
        # All should be valid sector keys
        for key in result:
            assert key in VALID_SECTOR_KEYS, f"Invalid key: {key}"

    def test_empty_report_returns_defaults(self):
        result = _extract_top_sectors("", top_n=3)
        assert result == VALID_SECTOR_KEYS[:3]

    def test_none_report_returns_defaults(self):
        result = _extract_top_sectors(None, top_n=3)
        assert result == VALID_SECTOR_KEYS[:3]

    def test_garbage_report_returns_defaults(self):
        result = _extract_top_sectors("not a table at all\njust random text", top_n=3)
        assert result == VALID_SECTOR_KEYS[:3]

    def test_negative_returns_sorted_by_absolute_value(self):
        """Sectors with large negative moves should rank high (big movers)."""
        report = """\
| Sector | 1-Day % | 1-Week % | 1-Month % | YTD % |
|--------|---------|----------|-----------|-------|
| Technology | +0.10% | +0.20% | +1.00% | +2.00% |
| Energy | -0.50% | -1.00% | -8.50% | -5.00% |
| Healthcare | +0.05% | +0.10% | +0.50% | +1.00% |
"""
        result = _extract_top_sectors(report, top_n=2)
        assert result[0] == "energy"  # |-8.50| > |1.00|

    def test_all_returned_keys_are_valid(self):
        result = _extract_top_sectors(SAMPLE_SECTOR_REPORT, top_n=11)
        for key in result:
            assert key in VALID_SECTOR_KEYS

    def test_display_to_key_covers_all_sectors(self):
        """Every sector name that appears in the ETF performance table
        should map to a valid key."""
        display_names = [
            "technology", "healthcare", "financials", "energy",
            "consumer discretionary", "consumer staples", "industrials",
            "materials", "real estate", "utilities", "communication services",
        ]
        for name in display_names:
            assert name in _DISPLAY_TO_KEY, f"Missing mapping for '{name}'"
            assert _DISPLAY_TO_KEY[name] in VALID_SECTOR_KEYS


# ---------------------------------------------------------------------------
# run_tool_loop nudge tests
# ---------------------------------------------------------------------------

class TestToolLoopNudge:
    """Verify the nudge mechanism in run_tool_loop."""

    def _make_chain(self, responses):
        """Create a mock chain that returns responses in sequence."""
        chain = MagicMock()
        chain.invoke = MagicMock(side_effect=responses)
        return chain

    def _make_tool(self, name="my_tool"):
        tool = MagicMock()
        tool.name = name
        tool.invoke = MagicMock(return_value="tool result")
        return tool

    def test_long_response_no_nudge(self):
        """A long first response (no tool calls) should be returned as-is."""
        long_text = "A" * 2100  # must exceed MIN_REPORT_LENGTH (2000)
        response = AIMessage(content=long_text, tool_calls=[])
        chain = self._make_chain([response])
        tool = self._make_tool()

        result = run_tool_loop(chain, [], [tool])
        assert result.content == long_text
        assert chain.invoke.call_count == 1

    def test_short_response_triggers_nudge(self):
        """A short first response triggers a nudge, then the LLM is re-invoked."""
        short_resp = AIMessage(content="Brief.", tool_calls=[])
        long_resp = AIMessage(content="A" * 2100, tool_calls=[])
        chain = self._make_chain([short_resp, long_resp])
        tool = self._make_tool()

        result = run_tool_loop(chain, [], [tool])
        assert result.content == long_resp.content
        assert chain.invoke.call_count == 2

        # The second invoke should have received a HumanMessage nudge
        second_call_messages = chain.invoke.call_args_list[1][0][0]
        nudge_msgs = [m for m in second_call_messages if isinstance(m, HumanMessage)]
        assert len(nudge_msgs) == 1
        assert "MUST call at least one tool" in nudge_msgs[0].content

    def test_nudge_only_on_first_round(self):
        """Nudge should NOT trigger after tools have been used."""
        # Round 1: LLM calls a tool
        tool_call_resp = AIMessage(
            content="",
            tool_calls=[{"name": "my_tool", "args": {}, "id": "tc1"}],
        )
        # Round 2: LLM returns a short text — no nudge expected
        short_resp = AIMessage(content="Done.", tool_calls=[])
        chain = self._make_chain([tool_call_resp, short_resp])
        tool = self._make_tool()

        result = run_tool_loop(chain, [], [tool])
        assert result.content == "Done."
        assert chain.invoke.call_count == 2

    def test_tool_calls_execute_normally(self):
        """Normal tool-calling flow should still work unchanged."""
        tool_call_resp = AIMessage(
            content="",
            tool_calls=[{"name": "my_tool", "args": {"x": 1}, "id": "tc1"}],
        )
        final_resp = AIMessage(content="Final report" * 50, tool_calls=[])
        chain = self._make_chain([tool_call_resp, final_resp])
        tool = self._make_tool()

        result = run_tool_loop(chain, [], [tool])
        tool.invoke.assert_called_once_with({"x": 1})
        assert "Final report" in result.content


# ---------------------------------------------------------------------------
# Enriched industry performance tests
# ---------------------------------------------------------------------------

class TestEnrichedIndustryPerformance:
    """Verify that get_industry_performance_yfinance now returns price columns.

    These tests require network access to Yahoo Finance.  If the host is not
    reachable (e.g. in sandboxed CI), they are automatically skipped.
    """

    @pytest.fixture(autouse=True)
    def _require_yahoo(self):
        import socket
        try:
            socket.setdefaulttimeout(3)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(
                ("query2.finance.yahoo.com", 443)
            )
        except (socket.error, OSError):
            pytest.skip("Yahoo Finance not reachable")

    def test_technology_has_price_columns(self):
        from tradingagents.dataflows.yfinance_scanner import (
            get_industry_performance_yfinance,
        )

        result = get_industry_performance_yfinance("technology")
        assert "# Industry Performance: Technology" in result
        # New columns should be present in the header
        assert "1-Day %" in result
        assert "1-Week %" in result
        assert "1-Month %" in result

    def test_table_has_seven_columns(self):
        from tradingagents.dataflows.yfinance_scanner import (
            get_industry_performance_yfinance,
        )

        result = get_industry_performance_yfinance("technology")
        lines = result.strip().split("\n")
        # Find the header separator line
        sep_lines = [l for l in lines if l.startswith("|") and "---" in l]
        assert len(sep_lines) >= 1
        # Count columns in separator
        cols = [c.strip() for c in sep_lines[0].split("|")[1:-1]]
        assert len(cols) == 7, f"Expected 7 columns, got {len(cols)}: {cols}"

    def test_healthcare_sector_key(self):
        from tradingagents.dataflows.yfinance_scanner import (
            get_industry_performance_yfinance,
        )

        result = get_industry_performance_yfinance("healthcare")
        assert "Industry Performance: Healthcare" in result
        assert "1-Day %" in result
