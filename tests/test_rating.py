"""Tests for the deterministic rating parser in ``tradingagents.agents.utils.rating``.

Covers the contract from issue #1170: an unrecognised or missing rating must never
silently become ``Hold``; canonical, markdown-wrapped, and harmless punctuation
variants parse; localized/fullwidth punctuation is normalised or surfaced; and the
5-tier rating stays distinct from the 3-tier trade action.
"""

import pytest

from tradingagents.agents.utils.rating import (
    RATING_REVIEW,
    RATINGS_5_TIER,
    extract_rating,
    parse_rating,
)


@pytest.mark.unit
class TestExtractRating:
    def test_all_five_tiers_via_label(self):
        for r in RATINGS_5_TIER:
            assert extract_rating(f"Rating: {r}") == r

    def test_markdown_bold_value(self):
        assert extract_rating("Rating: **Sell**\nExit immediately.") == "Sell"

    def test_markdown_bold_label(self):
        assert extract_rating("**Rating**: Underweight\nTrim exposure.") == "Underweight"

    def test_rendered_pm_markdown_shape(self):
        text = (
            "**Rating**: Buy\n\n"
            "**Executive Summary**: Enter at $189-192.\n\n"
            "**Investment Thesis**: AI capex cycle intact."
        )
        assert extract_rating(text) == "Buy"

    def test_label_wins_over_prose(self):
        text = "The sell thesis is weakened by guidance.\nRating: **Buy**\nEnter now."
        assert extract_rating(text) == "Buy"

    # --- The fix: unparseable is explicit, never a silent Hold -----------------

    def test_no_rating_returns_none(self):
        assert extract_rating("No clear directional signal at this time.") is None

    def test_empty_returns_none(self):
        assert extract_rating("") is None
        assert extract_rating("   \n  ") is None

    def test_review_sentinel_is_not_a_tier(self):
        assert RATING_REVIEW not in RATINGS_5_TIER

    # --- Fullwidth / localized punctuation -------------------------------------

    def test_fullwidth_colon_label(self):
        assert extract_rating("Rating：Overweight") == "Overweight"

    def test_fullwidth_parentheses_after_rating(self):
        assert extract_rating("Final rating: Sell（bearish）") == "Sell"

    def test_localized_label_with_english_rating(self):
        # Non-canonical label (评级) but a recognisable English rating word.
        assert extract_rating("评级：Overweight（超配）") == "Overweight"

    def test_fullwidth_colon_label_still_wins_over_prose(self):
        text = "The sell thesis is weak.\nRating：Buy\nStrong fundamentals."
        assert extract_rating(text) == "Buy"

    # --- Whole-word matching: no partial/substring false positives -------------

    @pytest.mark.parametrize("text", [
        "The buyer is holding out for a better price.",
        "A motivated seller emerged this quarter.",
        "Overweighting the growth sleeve is under review.",  # 'Overweighting' != 'Overweight'
    ])
    def test_longer_words_do_not_match(self, text):
        assert extract_rating(text) is None

    # --- Rating (5-tier) is not inferred as a trade action (3-tier) ------------

    def test_rating_not_mapped_to_trade_action(self):
        assert extract_rating("Rating: Overweight") == "Overweight"   # not "Buy"
        assert extract_rating("Rating: Underweight") == "Underweight"  # not "Sell"


@pytest.mark.unit
class TestParseRatingBackwardCompat:
    def test_parsed_value(self):
        assert parse_rating("Rating: Sell\nExit.") == "Sell"

    def test_default_when_unparseable(self):
        assert parse_rating("No clear directional signal.") == "Hold"

    def test_custom_default(self):
        assert parse_rating("Plain prose.", default="Underweight") == "Underweight"

    def test_default_is_only_a_fallback_not_a_match(self):
        # A real rating is returned even though the default differs.
        assert parse_rating("Rating: Buy", default="Sell") == "Buy"
