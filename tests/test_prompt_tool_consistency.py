import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PromptToolConsistencyTests(unittest.TestCase):
    def test_social_prompt_matches_real_tool_signatures(self):
        source = (ROOT / "tradingagents" / "agents" / "analysts" / "social_media_analyst.py").read_text(encoding="utf-8")
        self.assertIn("get_social_sentiment(symbol, start_date, end_date)", source)
        self.assertIn("get_company_news(symbol, start_date, end_date)", source)
        self.assertNotIn("get_news(query, start_date, end_date)", source)
        self.assertNotIn("social media posts", source.lower())

    def test_news_prompt_matches_real_tool_signatures(self):
        source = (ROOT / "tradingagents" / "agents" / "analysts" / "news_analyst.py").read_text(encoding="utf-8")
        self.assertIn("get_company_news(symbol, start_date, end_date)", source)
        self.assertIn("get_macro_news(curr_date, look_back_days, limit, region, language)", source)
        self.assertIn("get_disclosures(symbol, start_date, end_date)", source)
        self.assertNotIn("get_news(query, start_date, end_date)", source)


if __name__ == "__main__":
    unittest.main()
