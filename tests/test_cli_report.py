from datetime import date, datetime, timezone

import pytest

from tradingagents.research_platform.cli_report import (
    _build_manual_signal,
    build_parser,
    main,
)
from tradingagents.research_platform.data_contracts import (
    DataProvenance,
    FundamentalSnapshot,
    NewsItem,
    PriceBar,
)
from tradingagents.research_platform.yfinance_provider import YFinanceDataUnavailableError


class FakeProvider:
    name = "fixture"

    def get_price_bars(self, identity, start, end, *, as_of_date=None):
        return [
            _bar(identity.symbol, date(2026, 1, 1), 100),
            _bar(identity.symbol, date(2026, 1, 2), 105),
            _bar(identity.symbol, date(2026, 1, 3), 110),
            _bar(identity.symbol, date(2026, 1, 5), 120),
        ]

    def get_fundamentals(self, identity, *, as_of_date=None):
        return [
            FundamentalSnapshot(
                symbol=identity.symbol,
                period_end=date(2026, 1, 5),
                fiscal_period="snapshot",
                currency="USD",
                metrics={"market_cap": 3000000000000},
                provenance=_provenance(identity.symbol, date(2026, 1, 5)),
            )
        ]

    def get_news(self, identity, start, end, *, as_of_date=None):
        return [
            NewsItem(
                symbol=identity.symbol,
                title="Nvidia launches platform",
                published_at=datetime(2026, 1, 4, 15, 30, tzinfo=timezone.utc),
                as_of_date=date(2026, 1, 5),
                provider="Example News",
                url="https://example.com/nvda",
                summary="Summary.",
                source_id="news-1",
            )
        ]


class FailingProvider:
    name = "failing-yfinance"

    def get_price_bars(self, identity, start, end, *, as_of_date=None):
        raise YFinanceDataUnavailableError("rate limited")

    def get_fundamentals(self, identity, *, as_of_date=None):
        raise AssertionError("workflow should stop after price failure")

    def get_news(self, identity, start, end, *, as_of_date=None):
        raise AssertionError("workflow should stop after price failure")


def _provenance(symbol: str, day: date) -> DataProvenance:
    return DataProvenance(
        provider="fixture",
        as_of_date=day,
        retrieved_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        source="fixture",
        vendor_symbol=symbol,
    )


def _bar(symbol: str, day: date, close: float) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        date=day,
        open=close,
        high=close,
        low=close,
        close=close,
        adjusted_close=close,
        volume=1000,
        currency="USD",
        provenance=_provenance(symbol, day),
    )


def test_manual_signal_parser_accepts_percent_inputs():
    args = build_parser().parse_args(
        [
            "NVDA",
            "--as-of",
            "2026-01-05",
            "--direction",
            "buy",
            "--signal-date",
            "2026-01-02",
            "--position-pct",
            "5",
            "--expected-return-pct",
            "12",
            "--stop-loss-pct",
            "8",
            "--confidence",
            "75",
        ]
    )

    signal = _build_manual_signal(args)

    assert signal.as_of_date == date(2026, 1, 2)
    assert signal.proposed_position_pct == 0.05
    assert signal.expected_return_pct == 0.12
    assert signal.stop_loss_pct == 0.08
    assert signal.confidence == 0.75


def test_parser_accepts_yfinance_cache_dir(tmp_path):
    args = build_parser().parse_args(["NVDA", "--yfinance-cache-dir", str(tmp_path)])

    assert args.yfinance_cache_dir == str(tmp_path)


def test_cli_requires_direction_for_signal_fields():
    with pytest.raises(SystemExit):
        main(["NVDA", "--position-pct", "5"], provider_factory=lambda _args: FakeProvider())


def test_cli_returns_data_provider_error_without_traceback(capsys):
    code = main(
        ["NVDA", "--as-of", "2026-01-05"],
        provider_factory=lambda _args: FailingProvider(),
    )

    captured = capsys.readouterr()

    assert code == 2
    assert captured.out == ""
    assert "Data provider error: rate limited" in captured.err



def test_cli_returns_data_provider_error_when_provider_creation_fails(capsys):
    def failing_factory(_args):
        raise YFinanceDataUnavailableError("cache unavailable")

    code = main(["NVDA", "--as-of", "2026-01-05"], provider_factory=failing_factory)

    captured = capsys.readouterr()

    assert code == 2
    assert captured.out == ""
    assert "Data provider error: cache unavailable" in captured.err


def test_cli_runs_workflow_with_fake_provider_and_writes_report(tmp_path, capsys):
    code = main(
        [
            "nvda",
            "--as-of",
            "2026-01-05",
            "--lookback-days",
            "4",
            "--output-dir",
            str(tmp_path / "reports"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--direction",
            "buy",
            "--signal-date",
            "2026-01-02",
            "--position-pct",
            "20",
            "--confidence",
            "80",
            "--max-single-position-pct",
            "10",
        ],
        provider_factory=lambda _args: FakeProvider(),
    )

    out = capsys.readouterr().out
    report_path = tmp_path / "reports" / "NVDA_2026-01-05.md"

    assert code == 0
    assert "Report written:" in out
    assert "Risk decision: reduce" in out
    assert report_path.exists()
    assert "Personal Research Report: NVDA" in report_path.read_text(encoding="utf-8")
    assert (tmp_path / "cache" / "prices" / "NVDA.jsonl").exists()
