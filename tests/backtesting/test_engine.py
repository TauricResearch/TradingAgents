# tests/backtesting/test_engine.py
import json
from datetime import datetime
import pytest

from tradingagents.backtesting.models import BacktestResult


@pytest.mark.unit
class TestGenerateDates:
    def test_monthly(self):
        from tradingagents.backtesting.engine import generate_dates
        dates = generate_dates("2024-01-01", "2024-03-31", "monthly")
        assert dates == ["2024-01-01", "2024-02-01", "2024-03-01"]

    def test_weekly_all_mondays(self):
        from tradingagents.backtesting.engine import generate_dates
        dates = generate_dates("2024-01-01", "2024-01-29", "weekly")
        for d in dates:
            assert datetime.strptime(d, "%Y-%m-%d").weekday() == 0  # Monday

    def test_biweekly(self):
        from tradingagents.backtesting.engine import generate_dates
        dates = generate_dates("2024-01-01", "2024-01-15", "biweekly")
        assert len(dates) == 2

    def test_invalid_freq_raises(self):
        from tradingagents.backtesting.engine import generate_dates
        with pytest.raises(ValueError, match="Unsupported freq"):
            generate_dates("2024-01-01", "2024-12-31", "daily")


@pytest.mark.unit
class TestJSONLHelpers:
    def test_load_completed_pairs_missing_file(self, tmp_path):
        from tradingagents.backtesting.engine import load_completed_pairs
        result = load_completed_pairs(str(tmp_path / "missing.jsonl"))
        assert result == set()

    def test_load_completed_pairs_skips_errors(self, tmp_path):
        from tradingagents.backtesting.engine import load_completed_pairs
        f = tmp_path / "results.jsonl"
        f.write_text(
            '{"ticker":"NVDA","trade_date":"2024-01-01","error":null,"rating":"Buy",'
            '"direction":1,"raw_output":"","run_duration_seconds":10.0}\n'
            '{"ticker":"NVDA","trade_date":"2024-02-01","error":"timeout","rating":null,'
            '"direction":null,"raw_output":"","run_duration_seconds":0.0}\n',
            encoding="utf-8",
        )
        completed = load_completed_pairs(str(f))
        assert ("NVDA", "2024-01-01") in completed
        assert ("NVDA", "2024-02-01") not in completed  # failed → retry on resume

    def test_append_result_writes_valid_json(self, tmp_path):
        from tradingagents.backtesting.engine import append_result
        f = tmp_path / "out.jsonl"
        r = BacktestResult(ticker="AAPL", trade_date="2024-01-15", rating="Buy", direction=1)
        append_result(str(f), r)
        lines = f.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["ticker"] == "AAPL"
        assert obj["rating"] == "Buy"
        assert obj["error"] is None

    def test_append_result_creates_parent_dirs(self, tmp_path):
        from tradingagents.backtesting.engine import append_result
        nested = str(tmp_path / "deep" / "path" / "out.jsonl")
        append_result(nested, BacktestResult(ticker="X", trade_date="2024-01-01"))
        assert (tmp_path / "deep" / "path" / "out.jsonl").exists()


@pytest.mark.unit
class TestBacktestEngine:
    def test_run_calls_propagate_once_per_date(self, tmp_path):
        from unittest.mock import MagicMock, patch
        from tradingagents.backtesting.engine import BacktestEngine

        with patch("tradingagents.backtesting.engine.TradingAgentsGraph") as MockGraph:
            instance = MockGraph.return_value
            instance.propagate.return_value = (
                {"final_trade_decision": "**Rating**: Buy\n"},
                "Buy",
            )
            engine = BacktestEngine(
                tickers=["NVDA"],
                start_date="2024-01-01",
                end_date="2024-01-31",
                freq="monthly",
                output_file=str(tmp_path / "out.jsonl"),
            )
            results = engine.run()

        assert len(results) == 1
        assert results[0].ticker == "NVDA"
        assert results[0].rating == "Buy"
        assert results[0].direction == 1
        assert results[0].error is None

    def test_run_records_error_without_aborting(self, tmp_path):
        from unittest.mock import MagicMock, patch
        from tradingagents.backtesting.engine import BacktestEngine

        with patch("tradingagents.backtesting.engine.TradingAgentsGraph") as MockGraph:
            instance = MockGraph.return_value
            instance.propagate.side_effect = RuntimeError("LLM unavailable")
            engine = BacktestEngine(
                tickers=["NVDA"],
                start_date="2024-01-01",
                end_date="2024-01-31",
                freq="monthly",
                output_file=str(tmp_path / "out.jsonl"),
            )
            results = engine.run()

        assert len(results) == 1
        assert results[0].error == "LLM unavailable"
        assert results[0].rating is None
        assert results[0].direction is None

    def test_resume_skips_completed_pairs(self, tmp_path):
        from unittest.mock import MagicMock, patch
        from tradingagents.backtesting.engine import BacktestEngine

        out = tmp_path / "out.jsonl"
        out.write_text(
            '{"ticker":"NVDA","trade_date":"2024-01-01","error":null,"rating":"Buy",'
            '"direction":1,"raw_output":"","run_duration_seconds":5.0}\n',
            encoding="utf-8",
        )
        with patch("tradingagents.backtesting.engine.TradingAgentsGraph") as MockGraph:
            instance = MockGraph.return_value
            engine = BacktestEngine(
                tickers=["NVDA"],
                start_date="2024-01-01",
                end_date="2024-01-31",
                freq="monthly",
                output_file=str(out),
            )
            results = engine.run(resume=True)

        instance.propagate.assert_not_called()
        assert results == []

    def test_results_written_to_jsonl(self, tmp_path):
        from unittest.mock import patch
        from tradingagents.backtesting.engine import BacktestEngine
        import json

        out = tmp_path / "out.jsonl"
        with patch("tradingagents.backtesting.engine.TradingAgentsGraph") as MockGraph:
            instance = MockGraph.return_value
            instance.propagate.return_value = ({"final_trade_decision": ""}, "Hold")
            engine = BacktestEngine(
                tickers=["AAPL"],
                start_date="2024-01-01",
                end_date="2024-01-31",
                freq="monthly",
                output_file=str(out),
            )
            engine.run()

        lines = out.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["ticker"] == "AAPL"
        assert obj["rating"] == "Hold"
