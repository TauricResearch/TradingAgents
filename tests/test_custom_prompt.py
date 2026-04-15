import tempfile
import unittest
from pathlib import Path

from cli.main import save_report_to_disk
from tradingagents.agents.utils.agent_utils import build_custom_prompt_context
from tradingagents.graph.propagation import Propagator


class CustomPromptTests(unittest.TestCase):
    def test_build_custom_prompt_context_is_empty_when_missing(self):
        self.assertEqual(build_custom_prompt_context("   "), "")

    def test_build_custom_prompt_context_formats_user_guidance(self):
        context = build_custom_prompt_context(
            "Long-term horizon; focus on earnings quality and capex discipline."
        )
        self.assertIn("Additional user instructions", context)
        self.assertIn("Long-term horizon", context)
        self.assertIn("explicit strategy constraints", context)

    def test_create_initial_state_stores_custom_prompt(self):
        state = Propagator().create_initial_state(
            "META",
            "2026-04-05",
            custom_prompt="Short-term swing trade; new positions only.",
        )
        self.assertEqual(
            state["custom_prompt"],
            "Short-term swing trade; new positions only.",
        )

    def test_save_report_to_disk_includes_custom_prompt_header(self):
        final_state = {
            "custom_prompt": "Long-term horizon; focus on capital allocation.",
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "investment_debate_state": {},
            "risk_debate_state": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = save_report_to_disk(
                final_state,
                "META",
                Path(tmpdir),
            )
            report_text = Path(report_path).read_text()

        self.assertIn("## Custom Prompt", report_text)
        self.assertIn("Long-term horizon", report_text)


if __name__ == "__main__":
    unittest.main()
