import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tradingagents.scheduled.runner import execute_scheduled_run, load_scheduled_config, main


class _FakeStatsHandler:
    def get_stats(self):
        return {
            "llm_calls": 12,
            "tool_calls": 7,
            "tokens_in": 1024,
            "tokens_out": 2048,
        }


class _FakeTradingAgentsGraph:
    def __init__(self, selected_analysts, debug=False, config=None, callbacks=None):
        self.selected_analysts = selected_analysts
        self.debug = debug
        self.config = config or {}
        self.callbacks = callbacks or []

    def propagate(self, ticker, trade_date, analysis_date=None):
        if ticker == "FAIL":
            raise RuntimeError("synthetic failure")

        final_state = {
            "company_of_interest": ticker,
            "trade_date": trade_date,
            "analysis_date": analysis_date or trade_date,
            "market_report": f"## Market\n{ticker} market analysis",
            "sentiment_report": f"## Sentiment\n{ticker} sentiment analysis",
            "news_report": f"## News\n{ticker} news analysis",
            "fundamentals_report": f"## Fundamentals\n{ticker} fundamentals analysis",
            "investment_debate_state": {
                "bull_history": f"{ticker} bull case",
                "bear_history": f"{ticker} bear case",
                "history": "debate transcript",
                "current_response": "",
                "judge_decision": f"{ticker} research manager decision",
            },
            "trader_investment_plan": f"{ticker} trading plan",
            "investment_plan": f"{ticker} investment plan",
            "risk_debate_state": {
                "aggressive_history": f"{ticker} aggressive case",
                "conservative_history": f"{ticker} conservative case",
                "neutral_history": f"{ticker} neutral case",
                "history": "risk transcript",
                "judge_decision": f"{ticker} final portfolio decision",
            },
            "final_trade_decision": f"{ticker} final trade decision",
        }
        return final_state, "BUY"


class ScheduledAnalysisTests(unittest.TestCase):
    def test_execute_scheduled_run_archives_outputs_and_builds_site(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "scheduled_analysis.toml"
            archive_dir = root / "archive"
            site_dir = root / "site"
            config_path.write_text(
                f"""
[run]
tickers = ["NVDA", "FAIL"]
analysts = ["market", "social", "news", "fundamentals"]
output_language = "Korean"
trade_date_mode = "latest_available"
timezone = "Asia/Seoul"
continue_on_ticker_error = true

[llm]
provider = "codex"
quick_model = "gpt-5.4"
deep_model = "gpt-5.4"
codex_reasoning_effort = "medium"

[storage]
archive_dir = "{archive_dir.as_posix()}"
site_dir = "{site_dir.as_posix()}"

[site]
title = "Daily Reports"
subtitle = "Automated"
""",
                encoding="utf-8",
            )

            config = load_scheduled_config(config_path)
            with (
                patch("tradingagents.scheduled.runner.TradingAgentsGraph", _FakeTradingAgentsGraph),
                patch("tradingagents.scheduled.runner.StatsCallbackHandler", _FakeStatsHandler),
                patch("tradingagents.scheduled.runner.resolve_trade_date", return_value="2026-04-04"),
            ):
                manifest = execute_scheduled_run(config, run_label="test")

            self.assertEqual(manifest["status"], "partial_failure")
            self.assertEqual(manifest["summary"]["successful_tickers"], 1)
            self.assertEqual(manifest["summary"]["failed_tickers"], 1)
            self.assertEqual(manifest["settings"]["provider"], "codex")
            self.assertEqual(manifest["settings"]["deep_model"], "gpt-5.4")
            self.assertEqual(manifest["settings"]["quick_model"], "gpt-5.4")
            self.assertEqual(manifest["tickers"][0]["analysis_date"], manifest["started_at"][:10])

            run_dir = archive_dir / "runs" / manifest["started_at"][:4] / manifest["run_id"]
            self.assertTrue((run_dir / "run.json").exists())
            self.assertTrue((run_dir / "tickers" / "NVDA" / "report" / "complete_report.md").exists())
            self.assertTrue((run_dir / "tickers" / "FAIL" / "error.json").exists())

            index_html = (site_dir / "index.html").read_text(encoding="utf-8")
            run_html = (site_dir / "runs" / manifest["run_id"] / "index.html").read_text(encoding="utf-8")
            ticker_html = (site_dir / "runs" / manifest["run_id"] / "NVDA.html").read_text(encoding="utf-8")

            self.assertIn("Daily Reports", index_html)
            self.assertIn("partial failure", index_html)
            self.assertIn("NVDA", run_html)
            self.assertIn("Rendered report", ticker_html)
            self.assertIn("Analysis date", ticker_html)
            self.assertTrue((site_dir / "downloads" / manifest["run_id"] / "NVDA" / "complete_report.md").exists())

    def test_main_site_only_rebuilds_from_existing_archive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive_dir = root / "archive"
            site_dir = root / "site"
            run_dir = archive_dir / "runs" / "2026" / "20260405T091300_seed"
            ticker_dir = run_dir / "tickers" / "NVDA" / "report"
            ticker_dir.mkdir(parents=True, exist_ok=True)
            (ticker_dir / "complete_report.md").write_text("# Test report", encoding="utf-8")
            analysis_dir = run_dir / "tickers" / "NVDA"
            (analysis_dir / "analysis.json").write_text("{}", encoding="utf-8")
            (analysis_dir / "final_state.json").write_text("{}", encoding="utf-8")
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "run_id": "20260405T091300_seed",
                        "label": "seed",
                        "status": "success",
                        "started_at": "2026-04-05T09:13:00+09:00",
                        "finished_at": "2026-04-05T09:20:00+09:00",
                        "timezone": "Asia/Seoul",
                        "settings": {
                            "provider": "codex",
                            "quick_model": "gpt-5.4",
                            "deep_model": "gpt-5.4",
                            "codex_reasoning_effort": "medium",
                            "output_language": "Korean",
                            "analysts": ["market", "social", "news", "fundamentals"],
                            "trade_date_mode": "latest_available",
                            "max_debate_rounds": 1,
                            "max_risk_discuss_rounds": 1,
                        },
                        "summary": {
                            "total_tickers": 1,
                            "successful_tickers": 1,
                            "failed_tickers": 0,
                        },
                        "tickers": [
                            {
                                "ticker": "NVDA",
                                "status": "success",
                                "analysis_date": "2026-04-05",
                                "trade_date": "2026-04-04",
                                "decision": "BUY",
                                "started_at": "2026-04-05T09:13:00+09:00",
                                "finished_at": "2026-04-05T09:20:00+09:00",
                                "duration_seconds": 420.0,
                                "metrics": {
                                    "llm_calls": 10,
                                    "tool_calls": 7,
                                    "tokens_in": 1000,
                                    "tokens_out": 2000,
                                },
                                "artifacts": {
                                    "analysis_json": "tickers/NVDA/analysis.json",
                                    "report_markdown": "tickers/NVDA/report/complete_report.md",
                                    "final_state_json": "tickers/NVDA/final_state.json",
                                    "graph_log_json": None,
                                },
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            config_path = root / "scheduled_analysis.toml"
            config_path.write_text(
                f"""
[run]
tickers = ["NVDA"]

[storage]
archive_dir = "{archive_dir.as_posix()}"
site_dir = "{site_dir.as_posix()}"
""",
                encoding="utf-8",
            )

            exit_code = main(["--config", str(config_path), "--site-only"])

            self.assertEqual(exit_code, 0)
            self.assertTrue((site_dir / "index.html").exists())
            self.assertIn("NVDA", (site_dir / "runs" / "20260405T091300_seed" / "NVDA.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
