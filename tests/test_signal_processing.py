"""The rating heuristic that reads the decision's 5-tier rating.

The Portfolio Manager's rendered decision always carries a ``**Rating**: X``
header, so the rating is read deterministically; no second model call is made.
"""

import pytest

from tradingagents.agents.rating import RATING_REVIEW, RATINGS_5_TIER, extract_rating, parse_rating

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

    def test_no_rating_is_flagged_for_review_not_defaulted(self):
        # A decision nobody can read is not a Hold; recording one invents a call.
        assert parse_rating("No clear directional signal at this time.") == RATING_REVIEW

    def test_no_rating_custom_default(self):
        assert parse_rating("Plain prose.", default="Underweight") == "Underweight"

    def test_all_five_tiers_recognised(self):
        for r in RATINGS_5_TIER:
            assert parse_rating(f"Rating: {r}") == r

    def test_fullwidth_colon_is_parsed_not_reviewed(self):
        # `Rating：Overweight` (fullwidth colon) is read, not sent to review (#1170).
        assert parse_rating("Rating：Overweight\n理由はこちら。") == "Overweight"


@pytest.mark.unit
class TestExtractRating:
    def test_returns_none_when_absent(self):
        assert extract_rating("No directional call here.") is None
        assert extract_rating("") is None

    def test_whole_word_only(self):
        # substrings inside larger words must not match
        assert extract_rating("The buyer was holding shares.") is None

    def test_parse_rating_defaults_to_review(self):
        # The memory log tags an unreadable decision REVIEW, never a tradeable rating.
        assert parse_rating("No rating here.") == RATING_REVIEW
        assert parse_rating("No rating here.", default="Underweight") == "Underweight"


@pytest.mark.unit
class TestGraphSignalContract:
    """The graph-facing signal (TradingAgentsGraph.process_signal) honors the
    documented "5-tier or REVIEW" contract, not just the parser in isolation."""

    def _bare_graph(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        g = object.__new__(TradingAgentsGraph)
        return g

    def test_graph_surfaces_review(self):
        assert self._bare_graph().process_signal("no rating in here") == RATING_REVIEW

    def test_graph_returns_rating(self):
        assert self._bare_graph().process_signal("**Rating**: Sell") == "Sell"
