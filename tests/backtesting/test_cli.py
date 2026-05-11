# tests/backtesting/test_cli.py
import pytest


@pytest.mark.unit
class TestBuildParser:
    def test_required_args(self):
        from tradingagents.backtesting.cli import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--ticker", "NVDA",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
        ])
        assert args.ticker == ["NVDA"]
        assert args.start == "2024-01-01"
        assert args.end == "2024-12-31"

    def test_defaults(self):
        from tradingagents.backtesting.cli import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--ticker", "NVDA",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
        ])
        assert args.freq == "monthly"
        assert args.workers == 2
        assert args.risk_free_rate == 0.0
        assert args.hold_days is None
        assert args.resume is False
        assert args.output is None

    def test_multiple_tickers(self):
        from tradingagents.backtesting.cli import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--ticker", "NVDA", "AAPL", "MSFT",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
        ])
        assert args.ticker == ["NVDA", "AAPL", "MSFT"]

    def test_all_optional_flags(self):
        from tradingagents.backtesting.cli import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--ticker", "NVDA",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
            "--freq", "weekly",
            "--hold-days", "5",
            "--workers", "4",
            "--risk-free-rate", "0.045",
            "--resume",
            "--output", "results.jsonl",
            "--analysts", "market", "news",
        ])
        assert args.freq == "weekly"
        assert args.hold_days == 5
        assert args.workers == 4
        assert args.risk_free_rate == pytest.approx(0.045)
        assert args.resume is True
        assert args.output == "results.jsonl"
        assert args.analysts == ["market", "news"]

    def test_missing_ticker_exits(self):
        from tradingagents.backtesting.cli import build_parser
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--start", "2024-01-01", "--end", "2024-12-31"])
