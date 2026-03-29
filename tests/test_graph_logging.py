import json
import tempfile
import unittest
from pathlib import Path

from tradingagents.graph.trading_graph import TradingAgentsGraph


class GraphLoggingTests(unittest.TestCase):
    def test_log_state_uses_configured_results_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
            graph.config = {"results_dir": tmpdir}
            graph.ticker = "SPY"
            graph.log_states_dict = {}

            final_state = {
                "company_of_interest": "SPY",
                "trade_date": "2026-03-29",
                "market_report": "market",
                "sentiment_report": "sentiment",
                "news_report": "news",
                "fundamentals_report": "fundamentals",
                "investment_debate_state": {
                    "bull_history": "bull",
                    "bear_history": "bear",
                    "history": "history",
                    "current_response": "current",
                    "judge_decision": "judge",
                },
                "trader_investment_plan": "trade plan",
                "risk_debate_state": {
                    "aggressive_history": "aggressive",
                    "conservative_history": "conservative",
                    "neutral_history": "neutral",
                    "history": "risk history",
                    "judge_decision": "portfolio judge",
                },
                "investment_plan": "investment plan",
                "final_trade_decision": "HOLD",
            }

            graph._log_state("2026-03-29", final_state)

            log_path = (
                Path(tmpdir)
                / "TradingAgentsStrategy_logs"
                / "full_states_log_2026-03-29.json"
            )
            self.assertTrue(log_path.exists())

            payload = json.loads(log_path.read_text())
            self.assertIn("2026-03-29", payload)
            self.assertEqual(payload["2026-03-29"]["final_trade_decision"], "HOLD")


if __name__ == "__main__":
    unittest.main()
