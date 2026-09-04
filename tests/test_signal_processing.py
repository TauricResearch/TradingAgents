"""Tests for the shared rating heuristic and the SignalProcessor adapter.

The Portfolio Manager produces a typed PortfolioDecision via structured
output and renders it to markdown that always contains a ``**Rating**: X``
header.  The deterministic heuristic in ``tradingagents.agents.utils.rating``
is therefore sufficient to extract the rating downstream — no second LLM
call is needed — and SignalProcessor is now a thin adapter that delegates
to it.
"""

import pytest

from tradingagents.agents.utils.rating import (
    RATING_REVIEW,
    RATINGS_5_TIER,
    extract_rating,
    is_review,
    parse_rating,
)
from tradingagents.graph.signal_processing import SignalProcessor

# ---------------------------------------------------------------------------
# Heuristic parser
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseRating:
    def test_explicit_label_buy(self):
        assert parse_rating("Rating: Buy\nReasoning here.") == "Buy"

    def test_explicit_label_overweight(self):
        assert parse_rating("Rating: Overweight\nDetails.") == "Overweight"

    def test_explicit_label_with_markdown_bold_value(self):
        # Regression: Rating: **Sell** — markdown around the value.
        assert parse_rating("Rating: **Sell**\nExit immediately.") == "Sell"

    def test_explicit_label_with_markdown_bold_label(self):
        assert parse_rating("**Rating**: Underweight\nTrim exposure.") == "Underweight"

    def test_rendered_pm_markdown_shape(self):
        # The exact shape produced by render_pm_decision must always parse.
        text = (
            "**Rating**: Buy\n\n"
            "**Executive Summary**: Enter at $189-192, 6% portfolio cap.\n\n"
            "**Investment Thesis**: AI capex cycle intact; institutional flows constructive."
        )
        assert parse_rating(text) == "Buy"

    def test_explicit_label_wins_over_prose_with_markdown(self):
        text = (
            "The buy thesis is weakened by guidance.\n"
            "Rating: **Sell**\n"
            "Exit before earnings."
        )
        assert parse_rating(text) == "Sell"

    def test_no_rating_returns_default(self):
        assert parse_rating("No clear directional signal at this time.") == "Hold"

    def test_no_rating_custom_default(self):
        assert parse_rating("Plain prose.", default="Underweight") == "Underweight"

    def test_all_five_tiers_recognised(self):
        for r in RATINGS_5_TIER:
            assert parse_rating(f"Rating: {r}") == r


# ---------------------------------------------------------------------------
# SignalProcessor: thin adapter over the heuristic
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSignalProcessor:
    def test_returns_rating_from_pm_markdown(self):
        sp = SignalProcessor()
        md = "**Rating**: Overweight\n\n**Executive Summary**: Build gradually."
        assert sp.process_signal(md) == "Overweight"

    def test_makes_no_llm_calls(self):
        """SignalProcessor must not invoke the LLM it was constructed with —
        the rating is parseable from the rendered PM markdown directly."""
        from unittest.mock import MagicMock

        llm = MagicMock()
        sp = SignalProcessor(llm)
        sp.process_signal("Rating: Buy\nDetails.")
        llm.invoke.assert_not_called()
        llm.with_structured_output.assert_not_called()

    def test_unparseable_signal_is_review_not_silent_hold(self):
        # #1170: an unrecognizable decision must surface REVIEW, not a fabricated
        # tradeable Hold.
        sp = SignalProcessor()
        signal = sp.process_signal("Plain prose without a recommendation.")
        assert signal == RATING_REVIEW
        assert is_review(signal)
        assert signal not in RATINGS_5_TIER

    def test_fullwidth_colon_is_parsed_not_reviewed(self):
        # #1170: `Rating：Overweight` (fullwidth colon) used to defeat the regex
        # and silently become Hold; NFKC normalization now parses it.
        sp = SignalProcessor()
        assert sp.process_signal("Rating：Overweight\n理由はこちら。") == "Overweight"


@pytest.mark.unit
class TestExtractRating:
    def test_returns_none_when_absent(self):
        assert extract_rating("No directional call here.") is None
        assert extract_rating("") is None

    def test_whole_word_only(self):
        # substrings inside larger words must not match
        assert extract_rating("The buyer was holding shares.") is None

    def test_parse_rating_keeps_silent_default_for_compat(self):
        # parse_rating (used by the memory log) intentionally keeps Hold default.
        assert parse_rating("No rating here.") == "Hold"
        assert parse_rating("No rating here.", default="Underweight") == "Underweight"


@pytest.mark.unit
class TestGraphSignalContract:
    """The graph-facing signal (TradingAgentsGraph.process_signal) honors the
    documented "5-tier or REVIEW" contract, not just the parser in isolation."""

    def _bare_graph(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        g = object.__new__(TradingAgentsGraph)
        g.signal_processor = SignalProcessor()
        return g

    def test_graph_surfaces_review(self):
        assert self._bare_graph().process_signal("no rating in here") == RATING_REVIEW

    def test_graph_returns_rating(self):
        assert self._bare_graph().process_signal("**Rating**: Sell") == "Sell"
