"""Tests for the Industry Deep Dive improvements:

1. _extract_top_sectors() parses sector performance reports correctly
2. run_tool_loop nudge triggers when first response is short & no tool calls
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

    def test_returns_top_3_by_positive_1month(self):
        result = _extract_top_sectors(SAMPLE_SECTOR_REPORT, top_n=3)
        assert len(result) == 3
        assert result[0] == "energy"
        assert result[1] == "communication-services"
        assert result[2] == "technology"

    def test_returns_top_n_variable(self):
        result = _extract_top_sectors(SAMPLE_SECTOR_REPORT, top_n=5)
        assert len(result) == 5
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

    def test_negative_returns_do_not_outrank_positive_tailwinds(self):
        """Large drawdowns should not displace positive leadership."""
        report = """\
| Sector | 1-Day % | 1-Week % | 1-Month % | YTD % |
|--------|---------|----------|-----------|-------|
| Technology | +0.10% | +0.20% | +1.00% | +2.00% |
| Energy | -0.50% | -1.00% | -8.50% | -5.00% |
| Healthcare | +0.05% | +0.10% | +0.50% | +1.00% |
"""
        result = _extract_top_sectors(report, top_n=2)
        assert result == ["technology", "healthcare"]

    def test_all_returned_keys_are_valid(self):
        result = _extract_top_sectors(SAMPLE_SECTOR_REPORT, top_n=11)
        for key in result:
            assert key in VALID_SECTOR_KEYS

    def test_display_to_key_covers_all_sectors(self):
        display_names = [
            "technology", "healthcare", "financials", "energy",
            "consumer discretionary", "consumer staples", "industrials",
            "materials", "real estate", "utilities", "communication services",
        ]
        for name in display_names:
            assert name in _DISPLAY_TO_KEY, f"Missing mapping for '{name}'"
            assert _DISPLAY_TO_KEY[name] in VALID_SECTOR_KEYS

    def test_extracts_from_bullet_points(self):
        report = """
        Here are the top sectors:
        - Technology: The technology sector has been performing well.
        - Healthcare: Innovations in biotech are driving growth.
        - Energy - showing strong recovery.
        - Utilities
        """
        result = _extract_top_sectors(report, top_n=3)
        assert result == ["technology", "healthcare", "energy"]

    def test_extracts_from_numbered_lists(self):
        report = """
        Top performers this month:
        1. Financial Services: Interest rates are up.
        2. Consumer Staples - steady growth.
        3. Real Estate: Rebounding.
        """
        result = _extract_top_sectors(report, top_n=2)
        assert result == ["financial-services", "consumer-defensive"]

    def test_extracts_from_plain_text(self):
        report = "We recommend looking into technology, energy, and materials this quarter."
        result = _extract_top_sectors(report, top_n=3)
        assert result == ["technology", "energy", "basic-materials"]

    def test_extracts_with_mixed_capitalization_and_whitespace(self):
        report = """
        *  ComMunication SeRvices : strong user growth.
        * inDuStrials: Infrastructure spending is up.
        *   basiC MaTerials - high demand.
        """
        result = _extract_top_sectors(report, top_n=3)
        assert result == ["communication-services", "industrials", "basic-materials"]


# ---------------------------------------------------------------------------
# run_tool_loop nudge tests
# ---------------------------------------------------------------------------

class TestToolLoopNudge:
    """Verify the nudge mechanism in run_tool_loop."""

    def _make_chain(self, responses):
        chain = MagicMock()
        chain.invoke = MagicMock(side_effect=responses)
        return chain

    def _make_tool(self, name="my_tool"):
        tool = MagicMock()
        tool.name = name
        tool.invoke = MagicMock(return_value="tool result")
        return tool

    def test_long_response_no_nudge(self):
        long_text = "A" * 2100
        response = AIMessage(content=long_text, tool_calls=[])
        chain = self._make_chain([response])
        tool = self._make_tool()

        result = run_tool_loop(chain, [], [tool])
        assert result.content == long_text
        assert chain.invoke.call_count == 1

    def test_short_response_triggers_nudge(self):
        short_resp = AIMessage(content="Brief.", tool_calls=[])
        long_resp = AIMessage(content="A" * 2100, tool_calls=[])
        chain = self._make_chain([short_resp, long_resp])
        tool = self._make_tool()

        result = run_tool_loop(chain, [], [tool])
        assert result.content == long_resp.content
        assert chain.invoke.call_count == 2

        second_call_messages = chain.invoke.call_args_list[1][0][0]
        nudge_msgs = [m for m in second_call_messages if isinstance(m, HumanMessage)]
        assert len(nudge_msgs) == 1
        assert "MUST call at least one tool" in nudge_msgs[0].content

    def test_nudge_only_on_first_round(self):
        tool_call_resp = AIMessage(
            content="",
            tool_calls=[{"name": "my_tool", "args": {}, "id": "tc1"}],
        )
        short_resp = AIMessage(content="Done.", tool_calls=[])
        chain = self._make_chain([tool_call_resp, short_resp])
        tool = self._make_tool()

        result = run_tool_loop(chain, [], [tool])
        assert result.content == "Done."
        assert chain.invoke.call_count == 2

    def test_tool_calls_execute_normally(self):
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
