import unittest

import pytest

from tradingagents.agents.utils.rating import RATINGS_5_TIER, parse_rating


@pytest.mark.unit
class RatingsTierTests(unittest.TestCase):
    def test_ordered_correctly(self):
        self.assertEqual(RATINGS_5_TIER, ("Buy", "Overweight", "Hold", "Underweight", "Sell"))


@pytest.mark.unit
class ParseRatingTests(unittest.TestCase):
    def test_english_rating_label(self):
        self.assertEqual(parse_rating("**Rating**: Buy\nGreat setup"), "Buy")

    def test_english_rating_hyphen(self):
        self.assertEqual(parse_rating("rating - Sell\nBad outlook"), "Sell")

    def test_chinese_rating_label(self):
        self.assertEqual(parse_rating("评级：买入\n理由充分"), "Buy")

    def test_chinese_decision_label(self):
        self.assertEqual(parse_rating("决策：增持\n适当加仓"), "Overweight")

    def test_chinese_word_in_text(self):
        self.assertEqual(parse_rating("建议：清仓"), "Sell")

    def test_chinese_text_no_label(self):
        self.assertEqual(parse_rating("股票基本面良好，建议持有"), "Hold")

    def test_english_word_in_text(self):
        self.assertEqual(parse_rating("Overall we recommend to Hold position"), "Hold")

    def test_fallback_to_default_when_no_rating(self):
        self.assertEqual(parse_rating("No clear signal here", default="Hold"), "Hold")

    def test_markdown_bold_tolerance(self):
        self.assertEqual(parse_rating("**Rating**: **Sell**\nExit"), "Sell")

    def test_underweight_rating(self):
        self.assertEqual(parse_rating("Rating: Underweight\nReduce"), "Underweight")

    def test_overweight_chinese(self):
        self.assertEqual(parse_rating("建议：超配\n看好"), "Overweight")


if __name__ == "__main__":
    unittest.main()
