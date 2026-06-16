from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from opencloude_agent.run import (
    DEFAULT_WATCHLIST,
    MarketWatcher,
    OpenClaudeContinuousAgent,
    OpportunityScanner,
    PaperPortfolio,
    ReportWriter,
    RiskGuard,
)


class OpenClaudeAgentTests(unittest.TestCase):
    def test_portfolio_starts_with_ten_thousand_usd(self):
        portfolio = PaperPortfolio()

        self.assertEqual(10_000.0, portfolio.cash_usd)
        self.assertEqual(10_000.0, portfolio.to_dict()["total_value_usd"])

    def test_portfolio_simulates_buy_and_sell(self):
        portfolio = PaperPortfolio()

        cost = portfolio.simulate_buy("AAPL", 10, 100.0)
        self.assertEqual(1000.0, cost)
        self.assertEqual(9000.0, portfolio.cash_usd)
        self.assertEqual(10.0, portfolio.positions["AAPL"])

        proceeds = portfolio.simulate_sell("AAPL", 4, 120.0)
        self.assertEqual(480.0, proceeds)
        self.assertEqual(6.0, portfolio.positions["AAPL"])
        self.assertEqual(9480.0, portfolio.cash_usd)

    def test_scanner_limits_candidates(self):
        scanner = OpportunityScanner(max_candidates=1)
        snapshot = {
            "AAPL": {
                "close": 200.0,
                "volume": 10_000_000.0,
                "return_20d": 0.10,
                "benchmark_return_20d": 0.02,
            },
            "MSFT": {
                "close": 400.0,
                "volume": 5_000_000.0,
                "return_20d": 0.03,
                "benchmark_return_20d": 0.02,
            },
        }

        opportunities = scanner.scan(snapshot)

        self.assertEqual(1, len(opportunities))
        self.assertEqual("AAPL", opportunities[0].ticker)

    def test_risk_guard_marks_missing_opportunities_as_watch(self):
        risk_guard = RiskGuard()
        summary = risk_guard.evaluate({"total_value_usd": 10_000.0, "positions": {}}, [])

        self.assertEqual("watch", summary["overall_level"])
        self.assertIn("No opportunities selected", " ".join(summary["warnings"]))

    def test_report_writer_creates_jsonl_and_daily_summary(self):
        with TemporaryDirectory() as temp_dir:
            writer = ReportWriter(Path(temp_dir))
            writer.append_jsonl("watch_log.jsonl", {"ticker": "AAPL", "close": 1.0})
            writer.write_daily_summary(
                {
                    "timestamp": "2026-06-16T00:00:00Z",
                    "risk_summary": {"overall_level": "safe"},
                    "portfolio": {"cash_usd": 10_000.0, "equity_usd": 0.0, "total_value_usd": 10_000.0},
                    "opportunities": [],
                    "decisions": [],
                }
            )

            continuous_dir = Path(temp_dir) / "continuous"
            self.assertTrue((continuous_dir / "watch_log.jsonl").exists())
            self.assertTrue((continuous_dir / "daily_summary.md").exists())
            self.assertEqual(
                {"ticker": "AAPL", "close": 1.0},
                json.loads((continuous_dir / "watch_log.jsonl").read_text(encoding="utf-8")),
            )

    def test_market_watcher_parser_handles_yfinance_multiindex_columns(self):
        data = pd.DataFrame(
            {
                ("AAPL", "Close"): [100.0, 101.0, 100.0, 103.0, 104.0, 100.0, 108.0, 110.0],
                ("AAPL", "Volume"): [1_000, 1_010, 1_020, 1_030, 1_040, 1_100, 1_150, 1_200],
                ("SPY", "Close"): [200.0, 200.0, 201.0, 201.0, 202.0, 202.0, 204.0, 205.0],
            }
        )
        data.columns = pd.MultiIndex.from_tuples(data.columns, names=["Ticker", "Price"])

        watcher = MarketWatcher()

        snapshot = watcher.snapshot_from_dataframe(data, ["AAPL"])

        self.assertEqual(110.0, snapshot["AAPL"]["close"])
        self.assertEqual(1200.0, snapshot["AAPL"]["volume"])
        self.assertAlmostEqual(0.0185, snapshot["AAPL"]["return_1d"], places=4)
        self.assertAlmostEqual(0.10, snapshot["AAPL"]["return_5d"], places=4)
        self.assertIsNone(snapshot["AAPL"]["benchmark_return_20d"])

    def test_report_writer_appends_text_log(self):
        with TemporaryDirectory() as temp_dir:
            writer = ReportWriter(Path(temp_dir))

            writer.append_text("log.txt", "Cycle completed: no opportunities selected.")

            log_path = Path(temp_dir) / "continuous" / "log.txt"

            self.assertEqual(
                "Cycle completed: no opportunities selected.\n",
                log_path.read_text(encoding="utf-8"),
            )

    def test_market_watcher_parser_handles_empty_dataframe(self):
        watcher = MarketWatcher()

        self.assertEqual({}, watcher.snapshot([]))


if __name__ == "__main__":
    unittest.main()
