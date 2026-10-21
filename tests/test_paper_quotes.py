"""Market-data faults cannot invent fills or prevent unrelated research scans."""

import sys
from datetime import date
from types import SimpleNamespace

import pytest

from tradingagents.paper import cli
from tradingagents.paper.engine import Bar, Book


DAY = "2026-10-21"


class FakeHistory:
    def __init__(self, rows):
        self.rows = rows
        self.empty = not rows

    def iterrows(self):
        for day, values in self.rows:
            yield SimpleNamespace(date=lambda day=day: date.fromisoformat(day)), values


def row(open_, high, low, close, day=DAY):
    return (day, {"Open": open_, "High": high, "Low": low, "Close": close})


def fake_yahoo(monkeypatch, results):
    class Ticker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, **kwargs):
            value = results[self.symbol]
            if isinstance(value, BaseException):
                raise value
            return FakeHistory(value)

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=Ticker))


def valid():
    return {
        "SPY": [row(600, 605, 595, 603)],
        "GBPUSD=X": [row(1.33, 1.34, 1.32, 1.33)],
        "AAPL": [row(200, 203, 199, 202)],
    }


def test_invalid_optional_stock_skips_only_that_symbol(monkeypatch, capsys):
    data = valid() | {"JPM": [row(200, 199, 201, 202)]}
    fake_yahoo(monkeypatch, data)
    issues = {}
    bars = cli.fetch_daily(list(data), DAY, DAY, errors=issues)
    assert set(bars) == {"SPY", "GBPUSD=X", "AAPL"}
    assert "JPM" in issues
    assert "SKIPPED JPM" in capsys.readouterr().err
    assert bars["AAPL"][DAY] == Bar(200, 203, 199, 202)


@pytest.mark.parametrize("critical", ["SPY", "GBPUSD=X", "JPM"])
def test_essential_price_errors_abort_without_fabricating(monkeypatch, critical):
    data = valid() | {"JPM": [row(200, 199, 201, 202)]}
    data[critical] = [row(200, 199, 201, 202)]
    fake_yahoo(monkeypatch, data)
    with pytest.raises(ValueError, match=f"Required price feed for {critical}"):
        cli.fetch_daily(list(data), DAY, DAY, required={"JPM"}, errors={})


def test_optional_vendor_outage_does_not_block_other_symbols(monkeypatch):
    data = valid() | {"JPM": RuntimeError("HTTP 429")}
    fake_yahoo(monkeypatch, data)
    issues = {}
    bars = cli.fetch_daily(list(data), DAY, DAY, errors=issues)
    assert "JPM" not in bars
    assert "HTTP 429" in issues["JPM"]
    assert "AAPL" in bars


def test_bad_latest_bar_never_falls_back_to_prior_close(monkeypatch):
    prior = "2026-10-20"
    data = valid() | {"JPM": [row(200, 204, 197, 202, prior), row(202, 201, 204, 203)]}
    fake_yahoo(monkeypatch, data)
    issues = {}
    quotes = cli.fetch_daily(list(data), prior, DAY, errors=issues)
    assert "JPM" not in quotes
    assert "bad latest session" in issues["JPM"]


def test_invalid_price_feed_does_not_mutate_existing_ledger(monkeypatch, tmp_path):
    data = valid() | {"JPM": [row(200, 199, 201, 202)]}
    fake_yahoo(monkeypatch, data)
    path = tmp_path / "portfolio.json"
    book = Book.new(DAY)
    cli.write_book(path, book)
    monkeypatch.setattr(cli, "last_safe_session", lambda: DAY)
    seen = {}

    def record_research(book, quotes, tickers, path, stop_pct):
        seen["quotes"] = set(quotes)
        return book, 0

    monkeypatch.setattr(cli, "run_agents", record_research)
    assert cli.main(["--state", str(path), "run", "--tickers", "AAPL", "JPM"]) == 0
    loaded = cli.read_book(path)
    assert loaded.cash_gbp == pytest.approx(10000)
    assert loaded.positions == {} and loaded.orders == []
    assert any(e["type"] == "MARKET_DATA_ERROR" and e["ticker"] == "JPM"
               for e in loaded.events)
    assert "AAPL" in seen["quotes"] and "JPM" not in seen["quotes"]


def test_invalid_held_stock_aborts_with_ledger_unchanged(monkeypatch, tmp_path):
    data = valid() | {"JPM": [row(200, 199, 201, 202)]}
    fake_yahoo(monkeypatch, data)
    path = tmp_path / "portfolio.json"
    book = Book.new(DAY)
    book.positions["JPM"] = {"ticker": "JPM"}
    cli.write_book(path, book)
    before = path.read_text()
    monkeypatch.setattr(cli, "last_safe_session", lambda: DAY)
    assert cli.main(["--state", str(path), "run", "--tickers", "AAPL", "JPM"]) == 1
    assert path.read_text() == before
