"""Tests for the real-portfolio realized-P&L reader, recorder, and attribution
(memory/realized.py, option 9): CSV parsing, per-(ticker, entry_date)
aggregation, idempotent recording into the memory log, attribution joining,
benchmark alpha, and calibration integration. Fully offline — the benchmark
price fetch is monkeypatched the same way the settlement tests do it."""

from pathlib import Path

import pandas as pd
import pytest

from tradingagents.memory import TradingMemoryLog, settlement
from tradingagents.memory import calibration, realized

_SEP = TradingMemoryLog._SEPARATOR

HEADER = "ticker,shares,entry_date,entry_price,close_date,close_price,note\n"
DECISION_BUY = "Rating: Buy\nEnter at $189-192, 6% portfolio cap."
DECISION_SELL = "Rating: Sell\nExit position immediately."


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_log(tmp_path, filename="trading_memory.md"):
    return TradingMemoryLog({"memory_log_path": str(tmp_path / filename)})


def write_portfolio(tmp_path, rows: str, name="portfolio.csv"):
    p = tmp_path / name
    p.write_text(HEADER + rows, encoding="utf-8")
    return str(p)


def port_config(path, currency="EUR", benchmark=None):
    return {"portfolio": {"path": path, "format": "csv",
                          "currency": currency, "benchmark_ticker": benchmark}}


def _get_closes_stub(by_symbol):
    """A get_closes stand-in serving each symbol's series within the dates asked."""
    def get_closes(symbol, start_date, end_date):
        series = by_symbol[symbol]
        return series[(series.index >= start_date) & (series.index <= end_date)]
    return get_closes


# ---------------------------------------------------------------------------
# _num parsing
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNum:
    def test_plain(self):
        assert realized._num("950.00") == 950.0

    def test_thousands_separator(self):
        assert realized._num("1,234.56") == 1234.56

    def test_german_decimal_comma(self):
        assert realized._num("1.234,56") == 1234.56
        assert realized._num("12,5") == 12.5

    def test_currency_tail(self):
        assert realized._num("950.00 EUR") == 950.0

    def test_blank_and_na(self):
        assert realized._num("") is None
        assert realized._num(None) is None
        assert realized._num("n/a") is None
        assert realized._num("-") is None

    def test_garbage(self):
        assert realized._num("abc") is None


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestLoadPositions:
    def test_parses_open_and_closed(self, tmp_path):
        p = write_portfolio(tmp_path,
                            "# a comment\n"
                            "RHM.DE,20,2026-10-09,983.30,,\n"
                            "\n"
                            "RHM.DE,15,2026-10-09,983.30,2026-12-01,950.00,Tranche 1\n")
        pos = realized.load_positions(p)
        assert len(pos) == 2
        assert pos[0].is_closed is False
        assert pos[1].is_closed is True
        assert pos[1].realized_return == pytest.approx((950.0 - 983.30) / 983.30)
        assert pos[1].realized_pnl == pytest.approx((950.0 - 983.30) * 15)

    def test_case_insensitive_ticker_and_header(self, tmp_path):
        p = tmp_path / "p.csv"
        p.write_text("Ticker,Shares,Entry_Date,Entry_Price,Close_Date,Close_Price,Note\n"
                     "rhM.de,10,2026-10-09,100.0,2026-11-01,110.0,\n", encoding="utf-8")
        pos = realized.load_positions(p)
        assert len(pos) == 1
        assert pos[0].ticker == "RHM.DE"

    def test_half_filled_close_stays_open(self, tmp_path):
        p = write_portfolio(tmp_path, "RHM.DE,10,2026-10-09,100.0,2026-11-01,,\n")
        pos = realized.load_positions(p)
        assert len(pos) == 1
        assert pos[0].is_closed is False
        p2 = write_portfolio(tmp_path, "RHM.DE,10,2026-10-09,100.0,,55.5\n", name="p2.csv")
        pos2 = realized.load_positions(p2)
        assert pos2[0].is_closed is False  # price without a date

    def test_unvaluable_rows_skipped(self, tmp_path):
        p = write_portfolio(tmp_path,
                            ",10,2026-10-09,100.0,,\n"            # no ticker
                            "A.DE,0,2026-10-09,100.0,,\n"         # zero shares
                            "B.DE,10,2026-10-09,0,,\n"           # zero entry price
                            "C.DE,10,bad-date,100.0,,\n"
                            "D.DE,10,2026-10-09,100.0,,\n")
        pos = realized.load_positions(p)
        # "bad-date" rows are kept (dates are not validated numerically here);
        # the first three rows are dropped.
        assert [x.ticker for x in pos] == ["C.DE", "D.DE"]

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            realized.load_positions(tmp_path / "nope.csv")

    def test_missing_column_raises(self, tmp_path):
        p = tmp_path / "bad.csv"
        p.write_text("ticker,shares,entry_date\nRHM.DE,10,2026-10-09\n", encoding="utf-8")
        with pytest.raises(ValueError, match="entry_price"):
            realized.load_positions(p)

    def test_header_only(self, tmp_path):
        p = tmp_path / "h.csv"
        p.write_text(HEADER, encoding="utf-8")
        assert realized.load_positions(p) == []

    def test_quoted_note_with_comma(self, tmp_path):
        p = write_portfolio(tmp_path, 'RHM.DE,10,2026-10-09,100.0,2026-11-01,110.0,"cut, tranche 1"\n')
        pos = realized.load_positions(p)
        assert pos[0].note == "cut, tranche 1"


# ---------------------------------------------------------------------------
# Aggregation per (ticker, entry_date)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAggregation:
    def test_tranches_weighted(self):
        a = realized.RealizedTrade("RHM.DE", 10, "2026-10-09", 100.0, "2026-11-01", 110.0)
        b = realized.RealizedTrade("RHM.DE", 30, "2026-10-09", 110.0, "2026-11-05", 105.0)
        open_ = realized.RealizedTrade("RHM.DE", 50, "2026-10-09", 100.0)  # open
        agg = realized.aggregate_closed([a, b, open_])
        assert len(agg) == 1
        t = agg[0]
        assert t.shares == 40
        assert t.entry_price == pytest.approx((10 * 100.0 + 30 * 110.0) / 40)
        assert t.close_price == pytest.approx((10 * 110.0 + 30 * 105.0) / 40)
        assert t.close_date == "2026-11-05"  # latest close

    def test_load_realized_trades_closed_only(self, tmp_path):
        p = write_portfolio(tmp_path,
                            "A.DE,10,2026-10-09,100.0,,\n"
                            "A.DE,10,2026-10-09,100.0,2026-11-01,110.0,\n"
                            "B.DE,10,2026-10-09,100.0,2026-11-01,90.0,\n")
        trades = realized.load_realized_trades(p)
        assert [t.ticker for t in trades] == ["A.DE", "B.DE"]
        assert trades[0].realized_return == pytest.approx(0.10)
        assert trades[1].realized_return == pytest.approx(-0.10)


# ---------------------------------------------------------------------------
# Recording into the memory log
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRecord:
    def test_disabled_when_no_path(self, tmp_path):
        log = make_log(tmp_path)
        assert realized.record_realized_trades(log, {"portfolio": {"path": None}}) == []
        assert realized.record_realized_trades(log, {}) == []

    def test_records_closed_for_existing_entry(self, tmp_path):
        log = make_log(tmp_path)
        log.store_decision("RHM.DE", "2026-10-09", DECISION_SELL)
        p = write_portfolio(tmp_path, "RHM.DE,20,2026-10-09,983.30,2026-12-01,950.00,am Stop\n")
        cfg = port_config(p)
        recorded = realized.record_realized_trades(log, cfg)
        assert recorded == [("RHM.DE", "2026-10-09", pytest.approx((950.0 - 983.30) / 983.30))]
        entry = next(e for e in log.load_entries()
                     if e["ticker"] == "RHM.DE" and e["date"] == "2026-10-09")
        assert entry["realized"]["return"] == pytest.approx((950.0 - 983.30) / 983.30)
        assert entry["realized"]["close_date"] == "2026-12-01"
        assert entry["realized"]["note"] == "am Stop"
        # pending is not flipped by a realized record (it is not the anchor)
        assert entry["pending"] is True

    def test_idempotent_second_pass(self, tmp_path):
        log = make_log(tmp_path)
        log.store_decision("RHM.DE", "2026-10-09", DECISION_SELL)
        p = write_portfolio(tmp_path, "RHM.DE,20,2026-10-09,983.30,2026-12-01,950.00,\n")
        cfg = port_config(p)
        assert realized.record_realized_trades(log, cfg)
        assert realized.record_realized_trades(log, cfg) == []  # same return -> no-op

    def test_rerecords_when_return_changes(self, tmp_path):
        log = make_log(tmp_path)
        log.store_decision("RHM.DE", "2026-10-09", DECISION_SELL)
        p = write_portfolio(tmp_path, "RHM.DE,20,2026-10-09,983.30,2026-12-01,950.00,\n")
        cfg = port_config(p)
        realized.record_realized_trades(log, cfg)
        # user re-sells the rest at a different price (different aggregate return)
        Path(p).write_text(HEADER + "RHM.DE,20,2026-10-09,983.30,2026-12-15,910.00,\n", encoding="utf-8")
        recorded = realized.record_realized_trades(log, cfg)
        assert len(recorded) == 1
        assert recorded[0][2] == pytest.approx((910.0 - 983.30) / 983.30)
        entry = next(e for e in log.load_entries()
                     if e["ticker"] == "RHM.DE" and e["date"] == "2026-10-09")
        assert entry["realized"]["return"] == pytest.approx((910.0 - 983.30) / 983.30)
        assert entry["realized"]["close_date"] == "2026-12-15"

    def test_ignores_positions_the_model_never_analysed(self, tmp_path):
        log = make_log(tmp_path)
        log.store_decision("RHM.DE", "2026-10-09", DECISION_SELL)
        p = write_portfolio(tmp_path, "ZZZ.DE,10,2026-10-09,100.0,2026-11-01,110.0,\n")
        assert realized.record_realized_trades(log, port_config(p)) == []
        assert all(e["ticker"] != "ZZZ.DE" for e in log.load_entries())

    def test_ignores_open_positions(self, tmp_path):
        log = make_log(tmp_path)
        log.store_decision("RHM.DE", "2026-10-09", DECISION_BUY)
        p = write_portfolio(tmp_path, "RHM.DE,10,2026-10-09,100.0,,\n")
        assert realized.record_realized_trades(log, port_config(p)) == []

    def test_malformed_file_is_a_noop(self, tmp_path):
        log = make_log(tmp_path)
        log.store_decision("RHM.DE", "2026-10-09", DECISION_SELL)
        p = tmp_path / "bad.csv"
        p.write_text("ticker,shares,entry_date\nRHM.DE,10,2026-10-09\n", encoding="utf-8")
        assert realized.record_realized_trades(log, port_config(str(p))) == []
        entry = next(e for e in log.load_entries()
                     if e["ticker"] == "RHM.DE" and e["date"] == "2026-10-09")
        assert entry["realized"] is None


# ---------------------------------------------------------------------------
# Attribution (joining closed trades with the decisions that opened them)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAttribute:
    def test_joins_pnl_and_hit(self, tmp_path):
        log = make_log(tmp_path)
        log.store_decision("RHM.DE", "2026-10-09", DECISION_SELL)
        log.store_decision("A.DE", "2026-10-09", DECISION_BUY)
        p = write_portfolio(tmp_path,
                            "RHM.DE,20,2026-10-09,983.30,2026-12-01,950.00,\n"
                            "A.DE,10,2026-10-09,100.0,2026-11-01,110.0,\n")
        out = realized.attribute_realized(log, port_config(p))
        by_t = {a["ticker"]: a for a in out}
        assert by_t["RHM.DE"]["hit"] is True    # sold, it fell
        assert by_t["RHM.DE"]["pnl"] == pytest.approx((950.0 - 983.30) * 20)
        assert by_t["RHM.DE"]["rating"] == "Sell"
        assert by_t["A.DE"]["hit"] is True      # bought, it rose
        assert by_t["A.DE"]["pnl"] == pytest.approx(100.0)
        assert by_t["A.DE"]["currency"] == "EUR"

    def test_wrong_direction_is_a_miss(self, tmp_path):
        log = make_log(tmp_path)
        log.store_decision("A.DE", "2026-10-09", DECISION_BUY)
        p = write_portfolio(tmp_path, "A.DE,10,2026-10-09,100.0,2026-11-01,90.0,\n")
        out = realized.attribute_realized(log, port_config(p))
        assert out[0]["hit"] is False

    def test_skips_unanalysed(self, tmp_path):
        log = make_log(tmp_path)
        p = write_portfolio(tmp_path, "ZZZ.DE,10,2026-10-09,100.0,2026-11-01,110.0,\n")
        assert realized.attribute_realized(log, port_config(p)) == []

    def test_as_of_drops_future_closes(self, tmp_path):
        log = make_log(tmp_path)
        log.store_decision("A.DE", "2026-10-09", DECISION_BUY)
        p = write_portfolio(tmp_path, "A.DE,10,2026-10-09,100.0,2026-11-01,110.0,\n")
        cfg = port_config(p)
        assert len(realized.attribute_realized(log, cfg, as_of="2026-10-20")) == 0
        assert len(realized.attribute_realized(log, cfg, as_of="2026-11-01")) == 1
        assert len(realized.attribute_realized(log, cfg)) == 1  # no as_of -> all

    def test_benchmark_alpha(self, tmp_path, monkeypatch):
        log = make_log(tmp_path)
        log.store_decision("RHM.DE", "2026-10-09", DECISION_SELL)
        # benchmark rises steadily across the holding window (Oct 9 -> Dec 1)
        idx = pd.bdate_range("2026-10-05", "2026-12-05")
        bench = pd.Series([100.0 + 2 * i for i in range(len(idx))], index=idx)
        monkeypatch.setattr(settlement, "get_closes",
                            _get_closes_stub({"^GDAXI": bench}))
        p = write_portfolio(tmp_path, "RHM.DE,20,2026-10-09,983.30,2026-12-01,950.00,\n")
        cfg = port_config(p, benchmark="^GDAXI")
        out = realized.attribute_realized(log, cfg)
        # expected: realized return minus the benchmark's move over the window
        w = bench[(bench.index >= "2026-10-09") & (bench.index <= "2026-12-01")]
        ret = (950.0 - 983.30) / 983.30
        expected = ret - (float(w.iloc[-1]) - float(w.iloc[0])) / float(w.iloc[0])
        assert out[0]["alpha"] == pytest.approx(expected)

    def test_benchmark_fetch_failure_gives_none(self, tmp_path, monkeypatch):
        log = make_log(tmp_path)
        log.store_decision("RHM.DE", "2026-10-09", DECISION_SELL)

        def _boom(symbol, start_date, end_date):
            raise RuntimeError("offline")

        monkeypatch.setattr(settlement, "get_closes", _boom)
        p = write_portfolio(tmp_path, "RHM.DE,20,2026-10-09,983.30,2026-12-01,950.00,\n")
        out = realized.attribute_realized(log, port_config(p, benchmark="^GDAXI"))
        assert out[0]["alpha"] is None  # present but unknown, no crash


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRender:
    def test_empty(self):
        assert realized.render_realized_attribution([], "RHM.DE") == ""

    def test_same_and_cross(self):
        a = {"ticker": "RHM.DE", "entry_date": "2026-10-09", "return": -0.034,
             "pnl": -666.0, "currency": "EUR", "hit": True}
        b = {"ticker": "A.DE", "entry_date": "2026-10-09", "return": 0.10,
             "pnl": 100.0, "currency": "EUR", "hit": True}
        line = realized.render_realized_attribution([a, b], "RHM.DE")
        assert line.startswith("REALIZED P&L")
        assert "RHM.DE: 1 trade(s), 1/1 hit" in line
        assert "all tickers: 2 trade(s), 2/2 hit" in line
        assert "-666.00 EUR" in line

    def test_only_the_analysed_ticker(self):
        a = {"ticker": "RHM.DE", "entry_date": "2026-10-09", "return": -0.034,
             "pnl": -666.0, "currency": "EUR", "hit": True}
        line = realized.render_realized_attribution([a], "RHM.DE")
        assert "RHM.DE: 1 trade(s)" in line
        assert "all tickers" not in line  # no cross part when only one ticker


# ---------------------------------------------------------------------------
# Calibration integration
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCalibrationIntegration:
    def test_realized_bucket_counts(self, tmp_path):
        log = make_log(tmp_path)
        log.store_decision("RHM.DE", "2026-10-09", DECISION_SELL)
        p = write_portfolio(tmp_path, "RHM.DE,20,2026-10-09,983.30,2026-12-01,950.00,\n")
        realized.record_realized_trades(log, port_config(p))
        entries = log.load_entries()
        calib = calibration.build_calibration(entries, "RHM.DE", 5)
        assert calib["ticker"]["realized"]["n"] == 1
        assert calib["ticker"]["realized"]["hits"] == 1
        assert calib["ticker"]["realized"]["rate"] == 1.0
        assert calib["ticker"]["n"] == 1

    def test_render_puts_realized_first(self, tmp_path):
        log = make_log(tmp_path)
        log.store_decision("RHM.DE", "2026-10-09", DECISION_SELL)
        p = write_portfolio(tmp_path, "RHM.DE,20,2026-10-09,983.30,2026-12-01,950.00,\n")
        realized.record_realized_trades(log, port_config(p))
        line = calibration.render_calibration(
            calibration.build_calibration(log.load_entries(), "RHM.DE", 5), "RHM.DE")
        assert "realized 1/1" in line
        # realized is ground truth: when both exist, it leads the per-ticker part
        if "5d" in line:
            assert line.index("realized 1/1") < line.index("5d")

    def test_empty_log_stays_empty(self, tmp_path):
        line = calibration.render_calibration(
            calibration.build_calibration([], "RHM.DE", 5), "RHM.DE")
        assert line == ""
