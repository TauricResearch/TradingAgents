import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.main import run_analysis
from cli.models import AnalystType


class _DummyLive:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakePropagator:
    def create_initial_state(self, ticker, analysis_date):
        return {"ticker": ticker, "analysis_date": analysis_date}

    def get_graph_args(self, callbacks=None):
        return {}


class _FakeGraphRunner:
    def stream(self, init_state, **kwargs):
        yield {
            "messages": [SimpleNamespace(id="msg-1", tool_calls=[])],
            "market_report": "시장 보고서 — 한글 검증",
            "final_trade_decision": "HOLD — 포지션 유지",
        }


class _FakeTradingAgentsGraph:
    def __init__(self, *args, **kwargs):
        self.propagator = _FakePropagator()
        self.graph = _FakeGraphRunner()

    def process_signal(self, signal):
        return signal


class CliUnicodeLoggingTests(unittest.TestCase):
    def test_run_analysis_writes_logs_and_reports_as_utf8(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "results"
            selections = {
                "ticker": "GOOGL",
                "analysis_date": "2026-04-05",
                "output_language": "Korean",
                "analysts": [AnalystType.MARKET],
                "research_depth": 1,
                "llm_provider": "codex",
                "backend_url": None,
                "shallow_thinker": "gpt-5.4",
                "deep_thinker": "gpt-5.4",
                "codex_reasoning_effort": "medium",
            }

            with (
                patch("cli.main.get_user_selections", return_value=selections),
                patch("cli.main.DEFAULT_CONFIG", {"results_dir": str(results_dir)}),
                patch("cli.main.TradingAgentsGraph", _FakeTradingAgentsGraph),
                patch("cli.main.StatsCallbackHandler", return_value=SimpleNamespace()),
                patch("cli.main.Live", _DummyLive),
                patch("cli.main.create_layout", return_value=object()),
                patch("cli.main.update_display"),
                patch("cli.main.update_analyst_statuses"),
                patch(
                    "cli.main.classify_message_type",
                    return_value=("Agent", "유니코드 메시지 — 로그 저장 검증"),
                ),
                patch("cli.main.typer.prompt", side_effect=["N", "N"]),
                patch("cli.main.console.print"),
            ):
                run_analysis()

            log_file = results_dir / "GOOGL" / "2026-04-05" / "message_tool.log"
            report_file = results_dir / "GOOGL" / "2026-04-05" / "reports" / "market_report.md"

            self.assertTrue(log_file.exists())
            self.assertTrue(report_file.exists())
            self.assertIn("유니코드 메시지 — 로그 저장 검증", log_file.read_text(encoding="utf-8"))
            self.assertIn("시장 보고서 — 한글 검증", report_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
