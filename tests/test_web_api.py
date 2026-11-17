import json
import math
import os
import re
import shutil
import sqlite3
from datetime import UTC, datetime

import pytest
import requests
from fastapi.testclient import TestClient

from tests.test_trader_paper import BAD_PRICES, BTC, DAY0, T0, FakeOKX, minutes
from trader import rules
from trader.intraday.types import SignalResult
from trader.ledger import BUDGET_ERROR, Fill, Ledger, Position
from trader.okx import DAY_MS, Bar, FundingEvent
from trader.paper import Paper, _move
from trader.prices import OFFICIAL
from trader.settings import Settings
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
from tradingagents.memory.log import TradingMemoryLog
from web.api import app as app_module, data
from web.api.app import create_app

NOW = datetime.fromtimestamp(T0 / 1000, UTC)  # 2026-01-10 00:30 UTC: trade date 2026-01-09
MINUTE = 60_000
HOUR = 60 * MINUTE


class CountingOKX(FakeOKX):
    """FakeOKX with closes 80,000 and 80,800 on the two days before DAY0 + DAY, counting calls."""

    def __init__(self):
        super().__init__(last=79_000.0)
        self.daily = [Bar(DAY0 - DAY_MS, 0, 0, 0, 80_000), Bar(DAY0, 0, 0, 0, 80_800)]
        self.calls = []

    def last_price(self, inst):
        self.calls.append(("last", inst))
        return super().last_price(inst)

    def bars(self, inst, bar, start_ms, end_ms):
        self.calls.append(("bars", inst))
        return super().bars(inst, bar, start_ms, end_ms)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(data, "_now", lambda: NOW)
    # Whether web/ui/dist is built on this machine must not change the API's answers.
    monkeypatch.setattr(app_module, "UI_DIST", tmp_path / "no_dist")


def record(home, coin, trade_date, written=None, **fields):
    """A research record; ``written``: the UTC milliseconds its file is dated."""
    path = home / "logs" / coin / "x" / f"full_states_log_{trade_date}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"company_of_interest": coin, "trade_date": trade_date, **fields}))
    if written is not None:
        os.utime(path, (written / 1000, written / 1000))
    return path


def build(tmp_path, okx=None, validated=True):
    """A client over a paper account; validated: a short BTC, three midnights, research of
    2026-01-09 done (BTC), blocked by the budget (ETH) and pending (SOL), and the records
    written some minutes after their research began."""
    settings = Settings(home=tmp_path)
    ledger = Ledger(settings.ledger_path)
    ledger.initialize(10_000.0, T0)
    if validated:
        ledger.record_attempt(
            "2026-01-08", BTC.research, DAY0 - DAY_MS + 10 * MINUTE, rating="Hold", error=None,
            tokens_in=80, tokens_out=40, cost_usd=2.0,
        )
        ledger.record_attempt(
            "2026-01-09", BTC.research, DAY0 + 10 * MINUTE, rating=None,
            error="RuntimeError: boom", tokens_in=10, tokens_out=5, cost_usd=0.5,
        )
        ledger.record_attempt(
            "2026-01-09", BTC.research, DAY0 + 20 * MINUTE, rating="Sell", error=None,
            tokens_in=100, tokens_out=50, cost_usd=1.0,
        )
        ledger.record_attempt(
            "2026-01-09", "ETH-USD", DAY0 + 25 * MINUTE, rating=None, error=BUDGET_ERROR,
            cost_usd=None,
        )
        ledger.commit(
            positions={BTC.swap: Position(-0.02, 80_000.0, 85_000.0)}, cash=10_000.0,
            fills=[
                Fill(DAY0 - DAY_MS, BTC.swap, 0.04, 79_000.0, 1.58, "trade", "2026-01-08"),
                Fill(T0, BTC.swap, -0.02, 80_000.0, 0.8, "trade", "2026-01-09"),
            ],
            funding=[(DAY0 + 8 * HOUR, BTC.swap, 0.0001, 0.16)],
            snapshots=[
                (DAY0, 10_000.0), (DAY0 + DAY_MS, 10_100.0), (DAY0 + 2 * DAY_MS, 10_050.0),
            ],
            meta={"validation_start": DAY0},
            executed=("2026-01-09", T0),
        )
        ledger.add_event(T0, "code_change", "a")
        ledger.add_event(T0 + MINUTE, "resume", "b")
        record(tmp_path, "BTC-USD", "2026-01-09", DAY0 + 28 * MINUTE, final_rating="Underweight")
        record(tmp_path, "BTC-USD", "2026-01-08", DAY0 - DAY_MS + 18 * MINUTE)
        record(tmp_path, "SOL-USD", "2026-01-09", DAY0 + 29 * MINUTE, final_rating="Hold")
    ledger.db.close()
    return TestClient(create_app(settings, okx or CountingOKX()))


def test_accounts_lists_the_paper_account_first(tmp_path):
    accounts = build(tmp_path).get("/api/accounts").json()
    assert [a["id"] for a in accounts] == ["paper", "intraday", "demo", "live"]
    account = accounts[0]
    assert account["id"] == "paper" and account["kind"] == "paper"
    assert account["capital"] == 10_000.0
    assert account["validation_start"] == "2026-01-10T00:00:00Z"
    assert account["halted"] is False
    assert account["watchlist"][0] == {
        "research": "BTC-USD", "swap": "BTC-USDT-SWAP", "spot": "BTC-USDT"
    }


def test_strategy_quotes_the_constants_the_trader_runs_on(tmp_path):
    body = build(tmp_path).get("/api/strategy").json()
    assert body["risk_per_unit"] == 0.02 and body["stop_atr_mult"] == 2.5
    assert body["rating_weights"] == {
        "Buy": 1.0, "Overweight": 0.5, "Underweight": -0.25, "Sell": -0.5
    }
    assert body["kill_drawdown"] == 0.2 and body["benchmark"] == "USDC-USD"
    assert body["analysts"] == ["market", "social", "news"]
    assert body["watchlist"] == ["BTC-USD", "ETH-USD", "SOL-USD"]
    assert body["holding_period_days"] == 5
    assert isinstance(body["deep_model"], str) and isinstance(body["quick_model"], str)


def test_overview_marks_the_account_and_sums_up_the_day(tmp_path):
    body = build(tmp_path).get("/api/accounts/paper/overview").json()
    assert body["equity"] == pytest.approx(10_020.0)  # short 0.02 from 80,000, marked at 79,000
    assert body["cash"] == 10_000.0 and body["peak"] == 10_000.0 and body["capital"] == 10_000.0
    assert body["drawdown"] == 0.0 and body["halted"] is False
    assert body["processed_to"] == "2026-01-10T00:30:00Z"
    assert body["validation_start"] == "2026-01-10T00:00:00Z"
    assert body["days"] == 2

    # The day is measured from today's midnight snapshot (10,000 at 2026-01-10 00:00).
    assert body["today"] == {
        "since": "2026-01-10T00:00:00Z", "pnl": pytest.approx(20.0), "pct": pytest.approx(0.002),
    }
    assert body["totals"] == {
        "unrealized": pytest.approx(20.0), "notional": pytest.approx(1_580.0),
        "leverage": pytest.approx(1_580 / 10_020), "realized": 0.0,
        "pnl": pytest.approx(20.0), "pnl_pct": pytest.approx(0.002),
    }

    # Net of the $1.50 spent after the first midnight: 10,000 / 10,098.5 / 10,048.5.
    strategy = body["performance"]["strategy"]
    assert strategy["cumulative"] == pytest.approx(0.00485)
    assert strategy["annualized"] == pytest.approx(1.00485 ** (365 / 2) - 1)
    assert strategy["max_drawdown"] == pytest.approx(1 - 10_048.5 / 10_098.5)
    assert strategy["calmar"] == pytest.approx(strategy["annualized"] / strategy["max_drawdown"])
    assert strategy["sharpe"] is not None
    # The baselines have closes for the first two midnights only: +1%, no drawdown.
    for name in ("equal_weight", "btc"):
        assert body["performance"][name]["cumulative"] == pytest.approx(0.01)
        assert body["performance"][name]["calmar"] is None

    assert body["llm"] == {
        "trade_date": "2026-01-09", "today": 1.5, "month": 3.5, "cap": None,
        "learned_days": 1, "learning_days": 7, "unknown": True,
    }

    [position] = body["positions"]
    assert position["inst"] == "BTC-USDT-SWAP" and position["coin"] == "BTC-USD"
    assert position["qty"] == -0.02 and position["entry"] == 80_000.0
    assert position["stop"] == 85_000.0 and position["price"] == 79_000.0
    assert position["notional"] == pytest.approx(1_580.0)
    assert position["unrealized"] == pytest.approx(20.0)
    assert position["unrealized_pct"] == pytest.approx(20 / 1_600)  # on 0.02 × 80,000 at entry
    assert position["stop_distance"] == pytest.approx(6_000 / 79_000)

    latest = body["latest"]
    assert latest["trade_date"] == "2026-01-09" and latest["executed"] is True
    assert latest["executed_at"] == "2026-01-10T00:30:00Z"
    btc, eth, sol = latest["coins"]
    assert btc == {
        "coin": "BTC-USD", "state": "done", "rating": "Sell", "error": None, "cost_usd": 1.5,
        # When the record was written, 8 minutes into the attempt that gave the rating.
        "published_at": "2026-01-10T00:28:00Z", "updated_at": None,
        "fills": [{"qty": -0.02, "price": 80_000.0}],
    }
    assert eth == {
        "coin": "ETH-USD", "state": "failed", "rating": None, "error": BUDGET_ERROR,
        "cost_usd": None, "published_at": None, "updated_at": None, "fills": [],
    }
    assert sol["state"] == "pending" and sol["cost_usd"] is None and sol["fills"] == []
    assert sol["published_at"] is None  # a record, but no rating in the ledger: nothing is out


def test_overview_before_the_validation_period(tmp_path):
    body = build(tmp_path, validated=False).get("/api/accounts/paper/overview").json()
    assert body["equity"] == 10_000.0 and body["positions"] == []
    assert body["validation_start"] is None and body["days"] == 0
    assert body["performance"] == {"strategy": None, "equal_weight": None, "btc": None}
    assert body["llm"]["today"] == 0 and body["llm"]["unknown"] is False
    assert body["latest"]["executed"] is False and body["latest"]["executed_at"] is None
    assert [c["state"] for c in body["latest"]["coins"]] == ["pending"] * 3
    # No midnight snapshot yet: no day to measure; the sums over a flat account are zero.
    assert body["today"] == {"since": None, "pnl": None, "pct": None}
    assert body["totals"] == {
        "unrealized": 0.0, "notional": 0.0, "leverage": 0.0, "realized": 0.0, "pnl": 0.0,
        "pnl_pct": 0.0,
    }


def test_overview_measures_the_day_from_the_last_midnight_written(tmp_path, monkeypatch):
    # 2026-01-13 00:30: the hourly job has not written the 01-13 midnight yet, so the day
    # runs from the latest snapshot there is, 01-12's 10,050, and ``since`` says so.
    monkeypatch.setattr(data, "_now", lambda: datetime(2026, 1, 13, 0, 30, tzinfo=UTC))
    body = build(tmp_path).get("/api/accounts/paper/overview").json()
    assert body["equity"] == pytest.approx(10_020.0)
    assert body["today"] == {
        "since": "2026-01-12T00:00:00Z", "pnl": pytest.approx(-30.0),
        "pct": pytest.approx(-30 / 10_050),
    }


def test_equity_aligns_the_baselines_with_the_midnights(tmp_path):
    body = build(tmp_path).get("/api/accounts/paper/equity").json()
    assert body["live"] == {"ts": "2026-01-10T00:30:00Z", "equity": pytest.approx(10_020.0)}
    assert [p["ts"] for p in body["points"]] == [
        "2026-01-10T00:00:00Z", "2026-01-11T00:00:00Z", "2026-01-12T00:00:00Z"
    ]
    assert [p["strategy"] for p in body["points"]] == [10_000.0, 10_100.0, 10_050.0]
    assert [p["strategy_net"] for p in body["points"]] == [10_000.0, 10_098.5, 10_048.5]
    assert [p["equal_weight"] for p in body["points"]] == [10_000.0, pytest.approx(10_100.0), None]
    assert [p["btc"] for p in body["points"]] == [10_000.0, pytest.approx(10_100.0), None]


def test_equity_has_no_points_before_the_validation_period(tmp_path):
    body = build(tmp_path, validated=False).get("/api/accounts/paper/equity").json()
    assert body["points"] == []
    assert body["live"]["equity"] == 10_000.0


def test_daily_runs_midnight_to_midnight_and_the_last_day_to_the_live_equity(tmp_path):
    body = build(tmp_path).get("/api/accounts/paper/daily").json()
    assert body["market"]["ok"] is True
    # Newest first: the day of the last snapshot (10,050) runs to the live 10,020 and is
    # partial; the two before run between their snapshots. The day's fills, funding and
    # LLM spend are the ones timed within it: the fill and the attempts of 01-09 are not.
    assert body["days"] == [
        {
            "date": "2026-01-12", "start_ts": "2026-01-12T00:00:00Z", "open": 10_050.0,
            "close": pytest.approx(10_020.0), "pnl": pytest.approx(-30.0),
            "pct": pytest.approx(-30 / 10_050), "transfers": 0.0, "fills": 0, "funding": 0.0,
            "llm_cost": 0.0, "partial": True,
        },
        {
            "date": "2026-01-11", "start_ts": "2026-01-11T00:00:00Z", "open": 10_100.0,
            "close": 10_050.0, "pnl": pytest.approx(-50.0), "pct": pytest.approx(-50 / 10_100),
            "transfers": 0.0, "fills": 0, "funding": 0.0, "llm_cost": 0.0, "partial": False,
        },
        {
            "date": "2026-01-10", "start_ts": "2026-01-10T00:00:00Z", "open": 10_000.0,
            "close": 10_100.0, "pnl": pytest.approx(100.0), "pct": pytest.approx(0.01),
            "transfers": 0.0, "fills": 1, "funding": pytest.approx(0.16), "llm_cost": pytest.approx(1.5),
            "partial": False,
        },
    ]
    # The month opens at its first midnight and closes where its last day does.
    assert body["months"] == [{
        "month": "2026-01", "open": 10_000.0, "close": pytest.approx(10_020.0),
        "pnl": pytest.approx(20.0), "pct": pytest.approx(0.002), "transfers": 0.0, "days": 3,
        "partial": True,
    }]


def test_daily_takes_a_limit_and_is_empty_before_the_validation_period(tmp_path):
    client = build(tmp_path)
    body = client.get("/api/accounts/paper/daily?limit=2").json()
    assert [d["date"] for d in body["days"]] == ["2026-01-12", "2026-01-11"]
    assert len(body["months"]) == 1  # the months are over every day, not the page
    assert client.get("/api/accounts/paper/daily?limit=0").status_code == 422
    empty = build(tmp_path / "fresh", validated=False).get("/api/accounts/paper/daily").json()
    assert empty == {"days": [], "months": [], "market": {"ok": True, "error": None, "since": None}}


def test_daily_without_quotes_leaves_the_day_in_progress_unpriced(tmp_path):
    okx = DownOKX()
    okx.down = True
    body = build(tmp_path, okx).get("/api/accounts/paper/daily").json()
    today, yesterday = body["days"][:2]
    assert today["close"] is None and today["pnl"] is None and today["pct"] is None
    assert today["partial"] is True and today["open"] == 10_050.0
    assert yesterday["pnl"] == pytest.approx(-50.0)  # the snapshots need no quote
    [month] = body["months"]
    assert month["close"] is None and month["pnl"] is None and month["days"] == 3
    assert body["market"]["ok"] is False


def test_fills_newest_first_with_since_and_limit(tmp_path):
    client = build(tmp_path)
    fills = client.get("/api/accounts/paper/fills").json()
    assert [f["trade_date"] for f in fills] == ["2026-01-09", "2026-01-08"]
    # Selling 0.02 of the 0.04 bought at 79,000 realizes 0.02 * 1,000 and leaves 0.02.
    assert fills[0] == {
        "ts": "2026-01-10T00:30:00Z", "inst": "BTC-USDT-SWAP", "coin": "BTC-USD", "qty": -0.02,
        "price": 80_000.0, "fee": 0.8, "reason": "trade", "trade_date": "2026-01-09",
        "realized": pytest.approx(20.0), "realized_net": pytest.approx(19.2),
        # 19.2 on the 0.02 sold, worth 1,580 at the entry of 79,000.
        "realized_pct": pytest.approx(19.2 / 1_580), "entry": pytest.approx(79_000.0),
        "position_after": pytest.approx(0.02),
        "fills": [],  # an order that came back in one fill: the row is the fill
    }
    assert fills[1]["realized"] == 0.0
    assert fills[1]["realized_net"] == pytest.approx(-1.58)
    assert (fills[1]["realized_pct"], fills[1]["entry"]) == (None, None)  # it opened: no return
    assert fills[1]["position_after"] == pytest.approx(0.04)
    since = client.get("/api/accounts/paper/fills", params={"since": "2026-01-10T00:00:00Z"})
    assert [f["trade_date"] for f in since.json()] == ["2026-01-09"]
    # A page that starts later still books from the first fill: the PnL does not change.
    assert since.json()[0]["realized"] == pytest.approx(20.0)
    assert len(client.get("/api/accounts/paper/fills", params={"limit": 1}).json()) == 1
    assert client.get("/api/accounts/paper/fills", params={"since": "yesterday"}).status_code == 422


def test_fill_pnl_follows_the_account_rule_through_a_flip_and_a_close(tmp_path):
    settings = Settings(home=tmp_path)
    ledger = Ledger(settings.ledger_path)
    ledger.initialize(10_000.0, T0)
    fills = [
        Fill(T0, BTC.swap, 0.04, 79_000.0, 1.58, "trade", "2026-01-09"),         # open long
        Fill(T0 + HOUR, BTC.swap, -0.06, 80_000.0, 2.4, "trade", "2026-01-10"),  # flip to short
        Fill(T0 + 2 * HOUR, BTC.swap, 0.02, 78_000.0, 0.78, "stop", None),      # close short
    ]
    ledger.commit(positions={}, cash=10_000.0 + 80.0 - 4.76, fills=fills)
    ledger.db.close()
    client = TestClient(create_app(settings, CountingOKX()))

    rows = client.get("/api/accounts/paper/fills").json()[::-1]
    # The flip realizes the whole long, 0.04 * (80,000 - 79,000), and opens the short
    # at 80,000; closing it at 78,000 realizes -0.02 * (78,000 - 80,000).
    assert [r["realized"] for r in rows] == [0.0, pytest.approx(40.0), pytest.approx(40.0)]
    assert [r["position_after"] for r in rows] == [
        pytest.approx(0.04), pytest.approx(-0.02), 0.0,
    ]
    assert [r["realized_net"] for r in rows] == [
        pytest.approx(-1.58), pytest.approx(37.6), pytest.approx(39.22),
    ]
    # The return is on what each fill closed, at its entry: the 0.04 long bought at
    # 79,000 (not the 0.06 the flip traded), then the 0.02 short sold at 80,000.
    assert [r["entry"] for r in rows] == [None, pytest.approx(79_000.0), pytest.approx(80_000.0)]
    assert [r["realized_pct"] for r in rows] == [
        None, pytest.approx(37.6 / (0.04 * 79_000)), pytest.approx(39.22 / (0.02 * 80_000)),
    ]
    # The same fills through the account's own booking give the same numbers.
    positions, booked = {}, []
    for f in fills:
        old = positions[f.inst].qty if f.inst in positions else 0.0
        booked.append(_move(positions, f.inst, old + f.qty, f.price, 0.0, f.ts, f.reason, []))
    assert [r["realized"] - rules.fee(r["qty"] * r["price"]) for r in rows] == pytest.approx(booked)


def test_fill_return_is_on_the_part_closed_at_the_average_entry(tmp_path):
    settings = Settings(home=tmp_path)
    ledger = Ledger(settings.ledger_path)
    ledger.initialize(10_000.0, T0)
    fills = [
        Fill(T0, BTC.swap, -0.1, 80_000.0, 4.0, "trade", None),             # open short
        Fill(T0 + HOUR, BTC.swap, -0.1, 78_000.0, 3.9, "trade", None),      # add: entry 79,000
        Fill(T0 + 2 * HOUR, BTC.swap, 0.05, 80_580.0, 2.0, "stop", None),   # buy back a quarter
    ]
    ledger.commit(positions={}, cash=10_000.0, fills=fills)
    ledger.db.close()
    client = TestClient(create_app(settings, CountingOKX()))

    opened, added, reduced = client.get("/api/accounts/paper/fills").json()[::-1]
    # Selling more of a short closes nothing: no return, only the fee.
    assert (opened["realized_pct"], opened["entry"]) == (None, None)
    assert (added["realized_pct"], added["entry"]) == (None, None)
    # Buying 0.05 back at 80,580 loses 0.05 * 1,580 and the fee, on 0.05 * 79,000 at entry.
    assert reduced["entry"] == pytest.approx(79_000.0)
    assert reduced["realized_net"] == pytest.approx(-79.0 - 2.0)
    assert reduced["realized_pct"] == pytest.approx(-81.0 / 3_950.0)
    assert reduced["position_after"] == pytest.approx(-0.15)


def _orders_of(tmp_path, fills, **params):
    settings = Settings(home=tmp_path)
    ledger = Ledger(settings.ledger_path)
    ledger.initialize(10_000.0, T0)
    ledger.commit(positions={}, cash=10_000.0, fills=fills)
    ledger.db.close()
    client = TestClient(create_app(settings, CountingOKX()))
    return client.get("/api/accounts/paper/fills", params=params).json()


def test_the_fills_an_order_was_split_into_are_one_row_with_the_fills_under_it(tmp_path):
    """The exchange fills a market order in pieces, each a fill of its own in the ledger:
    the table lists the order, its fills summed, and the pieces under it."""
    eth = "ETH-USDT-SWAP"
    orders = _orders_of(tmp_path, [
        Fill(T0, BTC.swap, -0.10, 80_000.0, 4.0, "trade", None),               # open a short
        # An hour on, the order that buys it back comes in three pieces within a second,
        # an ETH fill of the same run among them.
        Fill(T0 + HOUR, BTC.swap, 0.02, 79_000.0, 0.79, "trade", None),
        Fill(T0 + HOUR, eth, 1.0, 3_000.0, 1.5, "trade", None),
        Fill(T0 + HOUR + 1, BTC.swap, 0.03, 79_100.0, 1.1865, "trade", None),
        Fill(T0 + HOUR + 400, BTC.swap, 0.05, 79_200.0, 1.98, "trade", None),
    ])
    assert [(o["inst"], len(o["fills"])) for o in orders] == [(eth, 0), (BTC.swap, 3), (BTC.swap, 0)]
    order = orders[1]
    assert order["ts"] == "2026-01-10T01:30:00Z"  # its first fill's
    assert order["qty"] == pytest.approx(0.10)
    assert order["price"] == pytest.approx((0.02 * 79_000 + 0.03 * 79_100 + 0.05 * 79_200) / 0.10)
    assert order["fee"] == pytest.approx(0.79 + 1.1865 + 1.98)
    # 0.02 * 1,000 + 0.03 * 900 + 0.05 * 800 on the short from 80,000, less the fees, on
    # the 8,000 the 0.10 was worth at the entry.
    assert order["realized"] == pytest.approx(87.0)
    assert order["realized_net"] == pytest.approx(87.0 - 3.9565)
    assert order["realized_pct"] == pytest.approx((87.0 - 3.9565) / 8_000.0)
    assert (order["entry"], order["position_after"], order["reason"]) == (pytest.approx(80_000.0), 0.0, "trade")
    # The pieces, newest first as the table is, each as it was listed before.
    assert [f["qty"] for f in order["fills"]] == [0.05, 0.03, 0.02]
    assert [f["position_after"] for f in order["fills"]] == [0.0, pytest.approx(-0.05), pytest.approx(-0.08)]
    assert order["fills"][0]["realized_pct"] == pytest.approx((40.0 - 1.98) / 4_000.0)
    assert all("fills" not in f for f in order["fills"])
    assert sum(f["realized_net"] for f in order["fills"]) == pytest.approx(order["realized_net"])


def test_fills_apart_in_time_side_or_kind_are_orders_of_their_own(tmp_path):
    window = data.ORDER_WINDOW_MS
    orders = _orders_of(tmp_path, [
        Fill(T0, BTC.swap, 0.02, 80_000.0, 0.8, "trade", None),
        Fill(T0 + window, BTC.swap, 0.02, 80_000.0, 0.8, "trade", None),          # the same order still
        Fill(T0 + 2 * window + 1, BTC.swap, 0.02, 80_000.0, 0.8, "trade", None),  # too long after
        Fill(T0 + 2 * window + 2, BTC.swap, -0.01, 80_000.0, 0.4, "trade", None),  # the other side
        Fill(T0 + 2 * window + 3, BTC.swap, -0.01, 80_000.0, 0.4, "stop", None),   # another kind
        Fill(T0 + 2 * window + 4, BTC.swap, -0.01, 80_000.0, 0.4, "stop", None),
    ])[::-1]
    assert [(o["reason"], o["qty"], len(o["fills"])) for o in orders] == [
        ("trade", pytest.approx(0.04), 2), ("trade", 0.02, 0), ("trade", -0.01, 0), ("stop", pytest.approx(-0.02), 2),
    ]


def test_an_order_through_zero_returns_on_what_it_closed_and_limits_count_orders(tmp_path):
    fills = [
        Fill(T0, BTC.swap, 0.04, 79_000.0, 1.58, "trade", None),               # open long
        # One order sells 0.06: the first piece reduces, the second closes the rest and
        # opens 0.02 short, the third adds to the short.
        Fill(T0 + HOUR, BTC.swap, -0.01, 80_000.0, 0.4, "trade", None),
        Fill(T0 + HOUR, BTC.swap, -0.04, 80_100.0, 1.602, "trade", None),
        Fill(T0 + HOUR + 2, BTC.swap, -0.01, 80_200.0, 0.401, "trade", None),
    ]
    flip, opened = _orders_of(tmp_path, fills)
    assert flip["qty"] == pytest.approx(-0.06) and flip["position_after"] == pytest.approx(-0.02)
    # 0.01 * 1,000 + 0.03 * 1,100 realized on the long; the whole order's fees against it,
    # as on a single fill that flips; over the 0.04 * 79,000 it closed.
    assert flip["realized"] == pytest.approx(43.0)
    assert flip["realized_pct"] == pytest.approx((43.0 - 2.403) / 3_160.0)
    assert flip["entry"] == pytest.approx(79_000.0)
    assert [f["realized_pct"] is None for f in flip["fills"]] == [True, False, False]
    assert (opened["realized_pct"], opened["fills"]) == (None, [])
    # A limit counts orders, and one is never cut: all its fills come with it.
    (only,) = _orders_of(tmp_path / "limit", fills, limit=1)
    assert only == flip
    # An order that only opened or added has no return.
    (added,) = _orders_of(tmp_path / "add", [
        Fill(T0, BTC.swap, 0.01, 80_000.0, 0.4, "trade", None),
        Fill(T0 + 1, BTC.swap, 0.01, 80_010.0, 0.4, "trade", None),
    ])
    assert (added["realized_pct"], added["entry"], len(added["fills"])) == (None, None, 2)


def test_fill_pnl_and_funding_add_up_to_the_cash_the_account_made(tmp_path):
    settings = Settings(home=tmp_path)
    ledger = Ledger(settings.ledger_path)
    ledger.initialize(10_000.0, T0)
    okx = FakeOKX(
        minute=minutes(T0 - MINUTE, [80_000, 79_000, (78_000, 78_000, 74_000, 76_000)]),
        funding=[FundingEvent(T0 + MINUTE, 0.0001)],
    )
    paper = Paper(ledger, okx, (BTC,))
    paper.execute("2026-01-09", {BTC.research: "Buy"}, T0)  # 0.04 long at 80,040, stop 75,040
    paper.replay(T0 + 3 * MINUTE)                             # the third minute's low fills the stop
    cash, funding = ledger.get("cash"), ledger.funding_total()
    ledger.db.close()
    client = TestClient(create_app(settings, CountingOKX()))

    rows = client.get("/api/accounts/paper/fills").json()
    assert [r["reason"] for r in rows] == ["stop", "trade"]
    stop_price = 75_040 * 0.9995
    assert rows[0]["realized"] == pytest.approx(0.04 * (stop_price - 80_040))
    assert rows[0]["position_after"] == 0.0
    assert rows[1]["realized"] == 0.0
    assert funding == pytest.approx(-0.04 * 79_000 * 0.0001)
    # Realized less fees, plus funding, is exactly what the account's cash gained.
    assert sum(r["realized_net"] for r in rows) + funding == pytest.approx(cash - 10_000.0)


def test_funding_events_and_attempts(tmp_path):
    client = build(tmp_path)
    assert client.get("/api/accounts/paper/funding").json() == [{
        "ts": "2026-01-10T08:00:00Z", "inst": "BTC-USDT-SWAP", "coin": "BTC-USD",
        "rate": 0.0001, "amount": 0.16,
    }]
    assert client.get(
        "/api/accounts/paper/funding", params={"since": "2026-01-11T00:00:00Z"}
    ).json() == []
    assert client.get("/api/accounts/paper/events").json() == [
        {"ts": "2026-01-10T00:31:00Z", "kind": "resume", "text": "b"},
        {"ts": "2026-01-10T00:30:00Z", "kind": "code_change", "text": "a"},
    ]
    attempts = client.get("/api/accounts/paper/attempts").json()
    assert [(a["trade_date"], a["coin"], a["rating"]) for a in attempts] == [
        ("2026-01-09", "ETH-USD", None), ("2026-01-09", "BTC-USD", "Sell"),
        ("2026-01-09", "BTC-USD", None), ("2026-01-08", "BTC-USD", "Hold"),
    ]
    assert attempts[1] == {
        "trade_date": "2026-01-09", "coin": "BTC-USD", "ts": "2026-01-10T00:20:00Z",
        "rating": "Sell", "error": None, "tokens_in": 100, "tokens_out": 50, "cost_usd": 1.0,
    }
    assert attempts[0]["error"] == BUDGET_ERROR and attempts[0]["cost_usd"] is None


def test_events_and_attempts_take_since_and_limit(tmp_path):
    client = build(tmp_path)
    events = client.get("/api/accounts/paper/events", params={"limit": 1}).json()
    assert [e["kind"] for e in events] == ["resume"]  # the newest
    since = client.get("/api/accounts/paper/events", params={"since": "2026-01-10T00:31:00Z"})
    assert [e["kind"] for e in since.json()] == ["resume"]
    attempts = client.get("/api/accounts/paper/attempts", params={"limit": 2}).json()
    assert [(a["coin"], a["rating"]) for a in attempts] == [("ETH-USD", None), ("BTC-USD", "Sell")]
    since = client.get("/api/accounts/paper/attempts", params={"since": "2026-01-10T00:20:00Z"})
    assert [(a["coin"], a["rating"]) for a in since.json()] == [("ETH-USD", None), ("BTC-USD", "Sell")]
    for route in ("events", "attempts"):
        assert client.get(f"/api/accounts/paper/{route}", params={"limit": 0}).status_code == 422


def test_accuracy_is_zero_without_a_memory_log_and_scored_with_one(tmp_path):
    client = build(tmp_path)
    assert client.get("/api/accounts/paper/accuracy").json() == {
        "resolved": 0, "pending": 0, "unscored": 0, "holding": "", "benchmark": "USDC-USD",
        "by_rating": {},
    }
    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "memory" / "trading_memory.md")})
    log.store_decision("BTC-USD", "2026-01-08", "Rating: Buy\n\nx")
    log.update_with_outcome("BTC-USD", "2026-01-08", 0.03, 0.02, 5, "note", "2026-01-15")
    log.store_decision("BTC-USD", "2026-01-09", "Rating: Sell\n\nx")
    body = client.get("/api/accounts/paper/accuracy").json()
    assert body["resolved"] == 1 and body["pending"] == 1 and body["holding"] == "5 trading days"
    assert body["by_rating"] == {"Buy": {"count": 1, "hit_rate": 1.0, "mean_alpha": 0.02}}


def test_research_index_merges_the_records_with_the_attempts(tmp_path):
    rows = build(tmp_path).get("/api/research").json()
    assert rows == [
        # The record's rating over the attempts'; cost and tokens over every attempt of the day.
        # Started with the day's first attempt, the failed one; out when the record was written.
        {"coin": "BTC-USD", "trade_date": "2026-01-09", "rating": "Underweight", "cost_usd": 1.5,
         "tokens_in": 110, "tokens_out": 55, "started_at": "2026-01-10T00:10:00Z",
         "published_at": "2026-01-10T00:28:00Z", "executed_at": "2026-01-10T00:30:00Z",
         "update": None},
        # A record without attempts: only its file says when.
        {"coin": "SOL-USD", "trade_date": "2026-01-09", "rating": "Hold", "cost_usd": None,
         "tokens_in": None, "tokens_out": None, "started_at": None,
         "published_at": "2026-01-10T00:29:00Z", "executed_at": "2026-01-10T00:30:00Z",
         "update": None},
        # A trade date the account did not rebalance on.
        {"coin": "BTC-USD", "trade_date": "2026-01-08", "rating": "Hold", "cost_usd": 2.0,
         "tokens_in": 80, "tokens_out": 40, "started_at": "2026-01-09T00:10:00Z",
         "published_at": "2026-01-09T00:18:00Z", "executed_at": None, "update": None},
    ]


def test_research_index_does_not_count_a_budget_refusal_as_the_start(tmp_path):
    client = build(tmp_path)
    ledger = Ledger(Settings(home=tmp_path).ledger_path)
    ledger.record_attempt(
        "2026-01-09", "SOL-USD", DAY0 + 5 * MINUTE, rating=None, error=BUDGET_ERROR
    )
    rows = {(r["coin"], r["trade_date"]): r for r in client.get("/api/research").json()}
    assert rows["SOL-USD", "2026-01-09"]["started_at"] is None
    ledger.record_attempt("2026-01-09", "SOL-USD", DAY0 + 21 * MINUTE, rating="Hold", error=None)
    rows = {(r["coin"], r["trade_date"]): r for r in client.get("/api/research").json()}
    assert rows["SOL-USD", "2026-01-09"]["started_at"] == "2026-01-10T00:21:00Z"


def test_a_rerun_keeps_the_time_the_first_rating_was_published(tmp_path):
    client = build(tmp_path)
    ledger = Ledger(Settings(home=tmp_path).ledger_path)
    # trader.jobs._rerun: the first record copied with its time, then written over.
    first = tmp_path / "logs" / "BTC-USD" / "x" / "full_states_log_2026-01-09.json"
    kept = first.with_name("superseded_20260110T0722Z_full_states_log_2026-01-09.json")
    shutil.copy2(first, kept)
    record(tmp_path, "BTC-USD", "2026-01-09", T0 + 7 * HOUR, final_rating="Overweight")
    ledger.record_attempt(
        "2026-01-09", BTC.research, T0 + 7 * HOUR - 8 * MINUTE, rating="Buy", error=None
    )
    ledger.record_update("2026-01-09", BTC.research, T0 + 7 * HOUR, "Sell", "Buy")

    def btc():
        rows = client.get("/api/research").json()
        row = next(r for r in rows if (r["coin"], r["trade_date"]) == ("BTC-USD", "2026-01-09"))
        return row, client.get("/api/accounts/paper/overview").json()["latest"]["coins"][0]

    row, card = btc()
    # The kept copy is not a record of its own.
    assert [r["coin"] for r in client.get("/api/research").json()].count("BTC-USD") == 2
    assert row["rating"] == "Overweight" and row["started_at"] == "2026-01-10T00:10:00Z"
    assert row["published_at"] == "2026-01-10T00:28:00Z"  # the first run's, not the rerun's
    assert row["update"]["at"] == "2026-01-10T07:30:00Z"
    assert card["rating"] == "Buy" and card["published_at"] == "2026-01-10T00:28:00Z"
    assert card["updated_at"] == "2026-01-10T07:30:00Z"

    kept.unlink()  # the record left is the rerun's: when the first rating was out is not known
    row, card = btc()
    assert row["published_at"] is None and card["published_at"] is None
    assert row["update"]["at"] == card["updated_at"] == "2026-01-10T07:30:00Z"


def test_research_index_says_what_a_rerun_on_the_daily_candle_updated(tmp_path):
    client = build(tmp_path)
    ledger = Ledger(Settings(home=tmp_path).ledger_path)
    ledger.record_update("2026-01-09", BTC.research, T0 + 7 * HOUR, "Sell", "Underweight")
    # The 2026-01-08 record has no rating of its own: the attempts' last one counts.
    ledger.record_attempt("2026-01-08", BTC.research, T0, rating="Buy", error=None)
    rows = {(r["coin"], r["trade_date"]): r for r in client.get("/api/research").json()}
    assert rows["BTC-USD", "2026-01-09"]["update"] == {
        "from": "Sell", "to": "Underweight", "at": "2026-01-10T07:30:00Z",
    }
    assert rows["SOL-USD", "2026-01-09"]["update"] is None
    assert rows["BTC-USD", "2026-01-08"]["rating"] == "Buy"


def test_research_index_reads_a_ledger_from_before_the_research_updates(tmp_path):
    client = build(tmp_path)
    old = sqlite3.connect(Settings(home=tmp_path).ledger_path)
    old.execute("DROP TABLE updates")
    old.commit()
    old.close()
    assert [r["update"] for r in client.get("/api/research").json()] == [None, None, None]
    latest = client.get("/api/accounts/paper/overview").json()["latest"]
    assert [c["updated_at"] for c in latest["coins"]] == [None, None, None]


def test_research_index_reads_a_record_file_once_until_it_changes(tmp_path, monkeypatch):
    reads = []
    read_rating = data._read_rating
    monkeypatch.setattr(data, "_read_rating", lambda path: reads.append(path) or read_rating(path))
    client = build(tmp_path)
    first = client.get("/api/research").json()
    assert len(reads) == 3  # one per record
    assert client.get("/api/research").json() == first
    assert len(reads) == 3  # served from the cache
    record(tmp_path, "SOL-USD", "2026-01-09", final_rating="Overweight")  # rewritten
    rows = client.get("/api/research").json()
    assert len(reads) == 4 and [r["rating"] for r in rows if r["coin"] == "SOL-USD"] == ["Overweight"]
    sol = tmp_path / "logs" / "SOL-USD" / "x" / "full_states_log_2026-01-09.json"
    assert sol in data._RATINGS
    sol.unlink()
    assert [r["coin"] for r in client.get("/api/research").json()] == ["BTC-USD", "BTC-USD"]
    assert sol not in data._RATINGS  # a gone record is forgotten


def test_research_record_is_served_as_written(tmp_path):
    client = build(tmp_path)
    response = client.get("/api/research/BTC-USD/2026-01-09")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["final_rating"] == "Underweight"
    assert client.get("/api/research/ETH-USD/2026-01-09").status_code == 404
    assert client.get("/api/research/BTC-USD/2026-01-07").status_code == 404


@pytest.mark.parametrize("path", [
    "/api/research/btc-usd/2026-01-09",      # lower case
    "/api/research/BTC-USD/20260109",        # not a date
    "/api/research/%2E%2E/2026-01-09",       # "..", decoded by the server
    "/api/research/.hidden/2026-01-09",
])
def test_research_record_rejects_what_is_no_coin_or_date(tmp_path, path):
    assert build(tmp_path).get(path).status_code == 422


def test_research_record_path_cannot_leave_the_results_dir(tmp_path):
    (tmp_path / "full_states_log_2026-01-09.json").write_text("{}")
    client = build(tmp_path)
    # httpx resolves the dot segments: the request never reaches the research route.
    assert client.get("/api/research/../2026-01-09").status_code == 404
    assert client.get("/api/research/../../2026-01-09").status_code == 404


def test_unknown_account_and_missing_ledger_are_404(tmp_path):
    client = build(tmp_path)
    response = client.get("/api/accounts/nope/overview")
    assert response.status_code == 404 and "nope" in response.json()["detail"]
    empty = TestClient(create_app(Settings(home=tmp_path / "empty"), CountingOKX()))
    [account] = [a for a in empty.get("/api/accounts").json() if a["id"] == "paper"]
    assert account["capital"] is None and account["validation_start"] is None
    response = empty.get("/api/accounts/paper/overview")
    assert response.status_code == 404 and "ledger" in response.json()["detail"]
    assert empty.get("/api/research").status_code == 404


def test_quotes_are_cached_between_requests(tmp_path):
    okx = CountingOKX()
    client = build(tmp_path, okx)
    for _ in range(3):
        client.get("/api/accounts/paper/overview")
        client.get("/api/accounts/paper/equity")
    assert okx.calls.count(("last", BTC.swap)) == 1
    assert sum(1 for kind, _ in okx.calls if kind == "bars") == 3  # one spot series per coin


class DownOKX(CountingOKX):
    """CountingOKX whose every request fails like an unreachable host while ``down``."""

    def __init__(self):
        super().__init__()
        self.down = False

    def last_price(self, inst):
        if self.down:
            self.calls.append(("last", inst))
            raise requests.ConnectionError("Host is down")
        return super().last_price(inst)

    def bars(self, inst, bar, start_ms, end_ms):
        if self.down:
            self.calls.append(("bars", inst))
            raise requests.ConnectionError("Host is down")
        return super().bars(inst, bar, start_ms, end_ms)


def test_overview_and_equity_degrade_when_okx_is_down_from_the_start(tmp_path):
    okx = DownOKX()
    okx.down = True
    client = build(tmp_path, okx)

    response = client.get("/api/accounts/paper/overview")
    assert response.status_code == 200
    body = response.json()
    # What needs a quote is null; the ledger's own figures still show.
    assert body["equity"] is None and body["drawdown"] is None
    assert body["cash"] == 10_000.0 and body["peak"] == 10_000.0 and body["days"] == 2
    assert body["performance"]["strategy"]["cumulative"] == pytest.approx(0.00485)
    assert body["performance"]["equal_weight"] is None and body["performance"]["btc"] is None
    [position] = body["positions"]
    assert position["qty"] == -0.02 and position["entry"] == 80_000.0
    assert position["stop"] == 85_000.0
    assert position["price"] is None and position["notional"] is None
    assert position["unrealized"] is None and position["stop_distance"] is None
    assert position["unrealized_pct"] is None
    # The day has its base but no live equity to measure against; the marked sums are
    # null rather than partial, what the ledger alone gives still shows.
    assert body["today"] == {"since": "2026-01-10T00:00:00Z", "pnl": None, "pct": None}
    assert body["totals"] == {
        "unrealized": None, "notional": None, "leverage": None, "realized": 0.0, "pnl": None,
        "pnl_pct": None,
    }
    assert body["market"] == {
        "ok": False, "error": "ConnectionError: Host is down", "since": "2026-01-10T00:30:00Z",
    }

    equity = client.get("/api/accounts/paper/equity").json()
    assert equity["live"]["equity"] is None and equity["market"]["ok"] is False
    assert [p["strategy"] for p in equity["points"]] == [10_000.0, 10_100.0, 10_050.0]
    assert all(p["equal_weight"] is None and p["btc"] is None for p in equity["points"])
    # OKX was asked once, for the price, and is left alone for FAILURE_TTL after that.
    assert okx.calls == [("last", BTC.swap)]


def test_a_failed_quote_serves_the_last_one_until_okx_answers_again(tmp_path, monkeypatch):
    clock = [1_000.0]
    monkeypatch.setattr(data.time, "monotonic", lambda: clock[0])
    okx = DownOKX()
    client = build(tmp_path, okx)
    fresh = client.get("/api/accounts/paper/overview").json()
    assert fresh["equity"] == pytest.approx(10_020.0)
    assert fresh["market"] == {"ok": True, "error": None, "since": None}

    okx.down = True
    clock[0] += data.PRICE_TTL + 1  # the price expired, and asking for it again fails
    stale = client.get("/api/accounts/paper/overview").json()
    assert stale["equity"] == pytest.approx(10_020.0)  # marked at the last price known
    assert stale["positions"][0]["price"] == 79_000.0
    assert stale["performance"]["btc"]["cumulative"] == pytest.approx(0.01)  # cached candles
    assert stale["market"]["ok"] is False and stale["market"]["since"] == "2026-01-10T00:30:00Z"
    asked = len(okx.calls)
    clock[0] += data.FAILURE_TTL - 1
    client.get("/api/accounts/paper/overview")
    assert len(okx.calls) == asked  # within FAILURE_TTL OKX is not asked

    okx.down = False
    clock[0] += 2
    back = client.get("/api/accounts/paper/overview").json()
    assert back["market"] == {"ok": True, "error": None, "since": None}
    assert okx.calls[asked:] == [("last", BTC.swap)]


def test_a_market_failure_outside_the_degrading_routes_is_a_503(tmp_path, monkeypatch):
    def unreachable(*args, **kwargs):
        raise requests.ConnectionError("Host is down")

    monkeypatch.setattr(data, "overview", unreachable)
    response = build(tmp_path).get("/api/accounts/paper/overview")
    assert response.status_code == 503
    assert response.json()["detail"].endswith("ConnectionError: Host is down")


def test_the_web_never_writes_the_ledger(tmp_path):
    client = build(tmp_path)
    before = (tmp_path / "ledger.sqlite").read_bytes()
    for path in ("overview", "equity", "fills", "funding", "transfers", "events", "attempts", "accuracy"):
        assert client.get(f"/api/accounts/paper/{path}").status_code == 200
    assert client.get("/api/research").status_code == 200
    assert (tmp_path / "ledger.sqlite").read_bytes() == before


def test_root_without_a_built_ui_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "UI_DIST", tmp_path / "no_dist")
    response = build(tmp_path).get("/")
    assert response.status_code == 200 and "/api" in response.text


def test_a_built_ui_is_served_with_the_spa_fallback(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>ui</html>")
    (dist / "assets" / "app.js").write_text("js")
    monkeypatch.setattr(app_module, "UI_DIST", dist)
    client = build(tmp_path)
    assert client.get("/").text == "<html>ui</html>"
    assert client.get("/assets/app.js").text == "js"
    assert client.get("/research/BTC-USD").text == "<html>ui</html>"
    assert client.get("/api/nope").status_code == 404
    assert client.get("/api/accounts").status_code == 200


# -- models and the LLM settings (ADR 0007) ------------------------------------

# The .env of the machine under test: Anthropic models the catalog has not caught up
# with, spelt with dots as the API accepts them; an Anthropic key, no OpenAI key.
ENV_DEEP, ENV_QUICK = "claude-sonnet-5.5", "claude-haiku-5.5"
OPUS = {"model": "claude-opus-5-5", "provider": "anthropic", "price": None}  # priced by the table
HAIKU = {"model": "claude-haiku-5-5", "provider": "anthropic", "price": [0.2, 0.9]}
SWITCH = {"deep": OPUS, "quick": HAIKU, "confirm": True}
HAIKU_NOTE = OFFICIAL["claude-haiku-5-5"].note  # the table's remark on the price; sonnet has none
assert HAIKU_NOTE and not OFFICIAL["claude-sonnet-5-5"].note and not OFFICIAL["claude-opus-5-5"].note


@pytest.fixture
def llm_env(monkeypatch):
    monkeypatch.setitem(DEFAULT_CONFIG, "llm_provider", "anthropic")
    monkeypatch.setitem(DEFAULT_CONFIG, "deep_think_llm", ENV_DEEP)
    monkeypatch.setitem(DEFAULT_CONFIG, "quick_think_llm", ENV_QUICK)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("TRADER_PRICE_DEEP", "")
    monkeypatch.setenv("TRADER_PRICE_QUICK", "")


def fingerprints(home, paper=None, intraday=None):
    """Store the research fingerprints the two accounts' jobs would have recorded; the
    intraday ledger is created for it."""
    settings = Settings(home=home)
    if paper is not None:
        ledger = Ledger(settings.ledger_path)
        ledger.set("fingerprint", {"version": "0.7.1", "code": "abc", **paper})
        ledger.db.close()
    if intraday is not None:
        ledger = Ledger(settings.intraday_ledger_path)
        ledger.initialize(1_000.0, T0)
        ledger.set("fingerprint", {"prompt": "v1", **intraday})
        ledger.db.close()


def provider(body, provider_id):
    return next(p for p in body["providers"] if p["id"] == provider_id)


def test_models_shows_the_env_models_priced_by_the_table_and_the_catalog(tmp_path, llm_env):
    body = build(tmp_path).get("/api/models").json()
    assert body["current"] == {
        "deep": {"model": ENV_DEEP, "provider": "anthropic", "price": [2.0, 10.0],
                 "price_note": None},
        "quick": {"model": ENV_QUICK, "provider": "anthropic", "price": [0.1, 0.5],
                  "price_note": HAIKU_NOTE},
        "source": "env", "updated_at": None, "applied": {},  # no fingerprint recorded yet
    }
    assert body["history"] == []
    assert [p["id"] for p in body["providers"]] == list(MODEL_OPTIONS)
    assert all(m["id"] != "custom" for p in body["providers"] for m in p["models"])

    anthropic = provider(body, "anthropic")
    assert (anthropic["name"], anthropic["has_key"], anthropic["key_env"]) == (
        "Anthropic", True, "ANTHROPIC_API_KEY"
    )
    assert provider(body, "openai")["has_key"] is False
    assert (provider(body, "ollama")["has_key"], provider(body, "ollama")["key_env"]) == (True, None)
    assert provider(body, "ollama")["name"] == "Ollama（本地）"

    sonnet = next(m for m in anthropic["models"] if m["id"] == "claude-sonnet-5")
    assert sonnet["modes"] == ["quick", "deep"] and sonnet["in_catalog"] is True
    assert sonnet["label"].startswith("Claude Sonnet 5")
    assert sonnet["price"] == [2.0, 10.0] and sonnet["price_as_of"] == "2026-11-07"
    assert sonnet["price_source"].startswith("https://")
    assert sonnet["price_note"] == OFFICIAL["claude-sonnet-5"].note  # the table has a remark
    assert sonnet["price_until"] is None  # open-ended
    promo = next(m for m in provider(body, "openai")["models"] if m["id"] == "gpt-5.6")
    assert promo["price_until"] == "2026-11-30"  # a promotional rate names its last day
    opus = next(m for m in anthropic["models"] if m["id"] == "claude-opus-5-5")
    assert opus["price"] == [4.0, 20.0] and opus["price_note"] is None  # priced, nothing to say
    unpriced = next(m for m in provider(body, "google")["models"] if m["id"] == "gemini-3.5-flash")
    assert (
        unpriced["price"], unpriced["price_source"], unpriced["price_as_of"], unpriced["price_note"],
        unpriced["price_until"],
    ) == (None,) * 5

    # The current models the catalog lacks follow their provider's list, priced by the table.
    assert anthropic["models"][-2:] == [
        {"id": ENV_QUICK, "label": ENV_QUICK, "modes": ["quick"], "price": [0.1, 0.5],
         "price_source": sonnet["price_source"], "price_as_of": "2026-11-07", "price_until": None,
         "price_note": HAIKU_NOTE, "in_catalog": False},
        {"id": ENV_DEEP, "label": ENV_DEEP, "modes": ["deep"], "price": [2.0, 10.0],
         "price_source": sonnet["price_source"], "price_as_of": "2026-11-07", "price_until": None,
         "price_note": None, "in_catalog": False},
    ]


def test_models_tells_per_account_whether_its_fingerprint_names_the_current_models(
    tmp_path, llm_env
):
    client = build(tmp_path)
    fingerprints(tmp_path, paper={"deep": ENV_DEEP, "quick": ENV_QUICK}, intraday={"model": "old"})
    assert client.get("/api/models").json()["current"]["applied"] == {
        "paper": True, "intraday": False,
    }
    fingerprints(tmp_path, paper={"deep": ENV_DEEP, "quick": "old"}, intraday={"model": ENV_DEEP})
    assert client.get("/api/models").json()["current"]["applied"] == {
        "paper": False, "intraday": True,
    }
    # The live account's fingerprint is of the code and the signals it trades on (ADR
    # 0010): it names no model, so the live account is not among those that apply one.
    live = Ledger(Settings(home=tmp_path).live_ledger_path)
    live.initialize(1_000.0, T0)
    live.set("fingerprint", {"code": "abc", "signal": {"model": ENV_DEEP, "prompt": "v1"}})
    live.db.close()
    assert client.get("/api/models").json()["current"]["applied"] == {
        "paper": False, "intraday": True,
    }


def test_switching_the_models_writes_settings_json_and_nothing_else(tmp_path, llm_env):
    client = build(tmp_path)
    fingerprints(tmp_path, paper={"deep": ENV_DEEP, "quick": ENV_QUICK}, intraday={"model": ENV_DEEP})
    ledgers = [tmp_path / "ledger.sqlite", tmp_path / "intraday" / "ledger.sqlite"]
    before = [path.read_bytes() for path in ledgers]

    response = client.post("/api/settings/llm", json=SWITCH)
    assert response.status_code == 200, response.text
    body = response.json()
    current = body["current"]
    assert current["deep"] == {
        "model": "claude-opus-5-5", "provider": "anthropic", "price": [4.0, 20.0], "price_note": None,
    }
    # The hand-entered price is in effect; the note is still the table's remark on the model.
    assert current["quick"] == {
        "model": "claude-haiku-5-5", "provider": "anthropic", "price": [0.2, 0.9],
        "price_note": HAIKU_NOTE,
    }
    assert current["source"] == "settings"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", current["updated_at"])
    assert current["applied"] == {"paper": False, "intraday": False}  # until their next run
    assert body["history"] == [{
        "at": current["updated_at"], "deep": "claude-opus-5-5", "quick": "claude-haiku-5-5",
        "note": "web",
    }]
    # The hand-priced quick model is not in the catalog; the deep one is, so nothing is added.
    anthropic = provider(body, "anthropic")
    assert [m["id"] for m in anthropic["models"] if not m["in_catalog"]] == ["claude-haiku-5-5"]
    assert next(m for m in anthropic["models"] if m["id"] == "claude-opus-5-5")["in_catalog"]

    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["llm"] == {
        "deep_think_llm": "claude-opus-5-5", "deep_think_provider": "anthropic",
        "quick_think_llm": "claude-haiku-5-5", "quick_think_provider": "anthropic",
    }
    assert saved["prices"] == {"claude-opus-5-5": [4.0, 20.0], "claude-haiku-5-5": [0.2, 0.9]}
    assert client.get("/api/models").json() == body  # read again from the file, not cached
    assert [path.read_bytes() for path in ledgers] == before

    # The trader reads the same file: its next run researches with the new models.
    settings = Settings.with_overrides(tmp_path)
    assert (settings.price_deep, settings.price_quick) == ((4.0, 20.0), (0.2, 0.9))
    assert data.strategy(settings)["deep_model"] == "claude-opus-5-5"


def test_strategy_quotes_the_switched_models_without_a_restart(tmp_path, llm_env):
    client = build(tmp_path)
    before = client.get("/api/strategy").json()
    assert (before["deep_model"], before["quick_model"]) == (ENV_DEEP, ENV_QUICK)
    assert client.post("/api/settings/llm", json=SWITCH).status_code == 200
    after = client.get("/api/strategy").json()
    assert (after["deep_model"], after["quick_model"]) == ("claude-opus-5-5", "claude-haiku-5-5")
    assert {k: v for k, v in after.items() if k not in ("deep_model", "quick_model")} == {
        k: v for k, v in before.items() if k not in ("deep_model", "quick_model")
    }


def test_a_second_switch_extends_the_history_and_merges_the_prices(tmp_path, llm_env):
    client = build(tmp_path)
    assert client.post("/api/settings/llm", json=SWITCH).status_code == 200
    back = {
        "deep": {"model": ENV_DEEP, "provider": "anthropic", "price": None},
        "quick": {"model": "claude-haiku-5-5", "provider": "anthropic", "price": None},
        "confirm": True,
    }
    body = client.post("/api/settings/llm", json=back).json()
    assert body["current"]["deep"] == {
        "model": ENV_DEEP, "provider": "anthropic", "price": [2.0, 10.0], "price_note": None,
    }
    # A null price takes the table's, which replaces the hand-entered one saved last time.
    assert body["current"]["quick"]["price"] == [0.1, 0.5]
    assert [(h["deep"], h["quick"]) for h in body["history"]] == [
        (ENV_DEEP, "claude-haiku-5-5"), ("claude-opus-5-5", "claude-haiku-5-5"),
    ]
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["prices"] == {
        "claude-opus-5-5": [4.0, 20.0], "claude-haiku-5-5": [0.1, 0.5], ENV_DEEP: [2.0, 10.0],
    }


@pytest.mark.parametrize("change, detail", [
    ({"confirm": False}, "确认"),
    ({"deep": {**OPUS, "provider": "openai"}}, "密钥"),
    ({"deep": {**OPUS, "provider": "nobody"}}, "密钥"),
    ({"deep": {**OPUS, "model": "my-own-model"}}, "单价"),
    ({"quick": {**HAIKU, "price": [0.2, -0.9]}}, "不能为负"),
    ({"deep": {**OPUS, "model": " "}}, "模型 ID 为空"),
])
def test_a_switch_is_refused_without_confirmation_a_key_or_a_price(tmp_path, llm_env, change, detail):
    client = build(tmp_path)
    response = client.post("/api/settings/llm", json={**SWITCH, **change})
    assert response.status_code == 400 and detail in response.json()["detail"]
    assert not (tmp_path / "settings.json").exists()
    assert client.get("/api/models").json()["current"]["source"] == "env"


@pytest.mark.parametrize("body", [
    {"deep": OPUS, "confirm": True},                                  # no quick tier
    {**SWITCH, "quick": {**HAIKU, "price": [0.2, 0.9, 1.0]}},         # three numbers
    {**SWITCH, "quick": {**HAIKU, "price": "cheap"}},
    {**SWITCH, "deep": {"model": "claude-opus-5-5"}},                 # no provider
])
def test_a_misshapen_switch_is_422(tmp_path, llm_env, body):
    client = build(tmp_path)
    assert client.post("/api/settings/llm", json=body).status_code == 422
    assert not (tmp_path / "settings.json").exists()


def test_without_a_token_the_switch_is_open_and_says_so(tmp_path, llm_env):
    client = build(tmp_path)
    assert client.get("/api/models").json()["write_protected"] is False
    assert client.post("/api/settings/llm", json=SWITCH).status_code == 200


def test_with_a_token_the_switch_wants_it_as_a_bearer_token(tmp_path, llm_env, monkeypatch):
    monkeypatch.setenv("TRADER_WEB_TOKEN", "s3cret ")  # Settings strips it
    build(tmp_path)
    client = TestClient(create_app(Settings.with_overrides(tmp_path), CountingOKX()))
    assert client.get("/api/models").json()["write_protected"] is True
    for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic s3cret"}):
        response = client.post("/api/settings/llm", json=SWITCH, headers=headers)
        assert response.status_code == 401, headers
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert "令牌" in response.json()["detail"] and "s3cret" not in response.text
    assert not (tmp_path / "settings.json").exists()
    response = client.post("/api/settings/llm", json=SWITCH, headers={"Authorization": "Bearer s3cret"})
    assert response.status_code == 200, response.text
    assert (tmp_path / "settings.json").exists()
    # Reads never want the token.
    assert client.get("/api/accounts/paper/overview").status_code == 200


# -- the intraday account (ADR 0006) --------------------------------------------

MONTH0 = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)
# (ts, coin, result) in the order recorded. The first is of last month; the first three are
# before the validation period (DAY0); the last two are today's. The third failed and the
# fifth ran on a model with no price: the cost of both is unknown.
SIGNALS = [
    (MONTH0 - HOUR, "BTC-USD", SignalResult("Short", 1, "last month", None, 10, 1, 9.0)),
    (MONTH0 + HOUR, "BTC-USD", SignalResult("Long", 3, "breakout", None, 1_000, 200, 2.0)),
    (DAY0 - HOUR, "ETH-USD", SignalResult(None, None, "", "RuntimeError: boom")),
    (DAY0, "BTC-USD", SignalResult("Flat", 2, "range", None, 800, 100, 0.5)),
    (DAY0, "ETH-USD", SignalResult("Long", 1, "unpriced", None, 700, 90, None)),
]


# The daily research of 2026-01-09 as build() leaves it, as every account that researches
# nothing itself shows it: the ratings, without the daily account's fills and execution.
SHARED_LATEST = {
    # The ratings and when they were out; the execution is the daily account's, not shown.
    "trade_date": "2026-01-09", "executed": None, "executed_at": None, "coins": [
        {"coin": "BTC-USD", "state": "done", "rating": "Sell", "error": None, "cost_usd": 1.5,
         "published_at": "2026-01-10T00:28:00Z", "updated_at": None, "fills": []},
        {"coin": "ETH-USD", "state": "failed", "rating": None, "error": BUDGET_ERROR,
         "cost_usd": None, "published_at": None, "updated_at": None, "fills": []},
        {"coin": "SOL-USD", "state": "pending", "rating": None, "error": None, "cost_usd": None,
         "published_at": None, "updated_at": None, "fills": []},
    ],
}


def build_intraday(tmp_path, okx=None, validated=True, signals=SIGNALS):
    """build() with the intraday account beside the paper one: a long BTC, the paper
    account's three midnights and ``signals``; validated=False: a ledger only initialized."""
    client = build(tmp_path, okx)
    ledger = Ledger(Settings(home=tmp_path).intraday_ledger_path)
    ledger.initialize(10_000.0, T0)
    if validated:
        ledger.commit(
            positions={BTC.swap: Position(0.03, 78_000.0, 74_000.0)}, cash=10_000.0,
            snapshots=[(DAY0, 10_000.0), (DAY0 + DAY_MS, 10_100.0), (DAY0 + 2 * DAY_MS, 10_050.0)],
            meta={"validation_start": DAY0, "peak": 10_100.0},
        )
        for ts, coin, result in signals:
            ledger.record_signal(ts, coin, result)
    ledger.db.close()
    return client


def test_accounts_flag_the_intraday_the_exchange_and_the_real_money_accounts(tmp_path):
    accounts = build(tmp_path).get("/api/accounts").json()
    assert [(a["id"], a["kind"], a["intraday"], a["exchange"], a["live"]) for a in accounts] == [
        ("paper", "paper", False, False, False), ("intraday", "paper", True, False, False),
        ("demo", "demo", False, True, False), ("live", "live", False, True, True),
    ]


def test_signals_newest_first_in_the_shape_of_the_contract(tmp_path):
    signals = build_intraday(tmp_path).get("/api/accounts/intraday/signals").json()
    # Of the two of the same hour, the one recorded later comes first.
    assert signals == [
        {"ts": "2026-01-10T00:00:00Z", "coin": "ETH-USD", "signal": "Long", "conviction": 1,
         "reason": "unpriced", "error": None, "tokens_in": 700, "tokens_out": 90,
         "cost_usd": None},  # it ran: the cost is unknown, the signal is not a failure
        {"ts": "2026-01-10T00:00:00Z", "coin": "BTC-USD", "signal": "Flat", "conviction": 2,
         "reason": "range", "error": None, "tokens_in": 800, "tokens_out": 100, "cost_usd": 0.5},
        {"ts": "2026-01-09T23:00:00Z", "coin": "ETH-USD", "signal": None, "conviction": None,
         "reason": "", "error": "RuntimeError: boom", "tokens_in": 0, "tokens_out": 0,
         "cost_usd": None},  # failed: no signal, the error, no cost
        {"ts": "2026-01-01T01:00:00Z", "coin": "BTC-USD", "signal": "Long", "conviction": 3,
         "reason": "breakout", "error": None, "tokens_in": 1000, "tokens_out": 200,
         "cost_usd": 2.0},
        {"ts": "2025-12-31T23:00:00Z", "coin": "BTC-USD", "signal": "Short", "conviction": 1,
         "reason": "last month", "error": None, "tokens_in": 10, "tokens_out": 1, "cost_usd": 9.0},
    ]


def test_signals_since_and_limit(tmp_path):
    client = build_intraday(tmp_path)

    def asked(**params):
        response = client.get("/api/accounts/intraday/signals", params=params)
        assert response.status_code == 200
        return [(s["ts"], s["coin"]) for s in response.json()]

    # ``since`` keeps the signals at or after it, as the fills route does.
    assert asked(since="2026-01-10T00:00:00Z") == [
        ("2026-01-10T00:00:00Z", "ETH-USD"), ("2026-01-10T00:00:00Z", "BTC-USD")
    ]
    assert asked(since="2026-01-09T23:00:00Z")[-1] == ("2026-01-09T23:00:00Z", "ETH-USD")
    assert len(asked(since="2026-01-09T23:00:00Z")) == 3
    assert asked(since="2026-01-10T00:00:01Z") == []
    assert asked(since="2026-01-10T00:00:00") == asked(since="2026-01-10T00:00:00Z")  # UTC
    # ``limit`` keeps the newest, of those since.
    assert asked(limit=1) == [("2026-01-10T00:00:00Z", "ETH-USD")]
    assert asked(limit=2, since="2026-01-09T23:00:00Z") == [
        ("2026-01-10T00:00:00Z", "ETH-USD"), ("2026-01-10T00:00:00Z", "BTC-USD")
    ]
    assert len(asked(limit=3, since="2026-01-01T00:00:00Z")) == 3
    assert len(asked()) == 5
    for bad in ({"limit": 0}, {"since": "yesterday"}):
        assert client.get("/api/accounts/intraday/signals", params=bad).status_code == 422


def test_the_daily_account_has_no_signals_even_without_the_table(tmp_path):
    client = build_intraday(tmp_path)
    assert client.get("/api/accounts/paper/signals").json() == []
    # A ledger from before the signals table lacks it, and a reader does not create it.
    ledger = Ledger(Settings(home=tmp_path).ledger_path)
    ledger.db.execute("DROP TABLE signals")
    ledger.db.close()
    reader = Ledger(Settings(home=tmp_path).ledger_path, readonly=True)
    with pytest.raises(sqlite3.OperationalError):
        reader.signals()
    reader.db.close()
    response = client.get("/api/accounts/paper/signals")
    assert response.status_code == 200 and response.json() == []


def test_signals_without_a_ledger_is_404(tmp_path):
    response = build(tmp_path).get("/api/accounts/intraday/signals")  # only the paper ledger exists
    assert response.status_code == 404 and "ledger" in response.json()["detail"]
    empty = TestClient(create_app(Settings(home=tmp_path / "empty"), CountingOKX()))
    for account in ("paper", "intraday", "demo", "live"):
        response = empty.get(f"/api/accounts/{account}/signals")
        assert response.status_code == 404 and "ledger" in response.json()["detail"]


def test_intraday_overview_takes_the_llm_spend_from_the_signals(tmp_path):
    body = build_intraday(tmp_path).get("/api/accounts/intraday/overview").json()
    assert body["equity"] == pytest.approx(10_030.0)  # long 0.03 from 78,000, marked at 79,000
    assert body["cash"] == 10_000.0 and body["peak"] == 10_100.0
    assert body["drawdown"] == pytest.approx(70 / 10_100) and body["halted"] is False
    assert body["processed_to"] == "2026-01-10T00:30:00Z"
    assert body["validation_start"] == "2026-01-10T00:00:00Z"
    assert body["days"] == 2

    # Today (UTC 2026-01-10) spent 0.5 and a call of unknown cost; the month adds 2.0 and a
    # failed call; the 9.0 is of last month. Only the 0.5 is before the second and third
    # midnights, so the curve is 10,000 / 10,099.5 / 10,049.5, against 10,000 / 10,100 / 10,050
    # gross.
    assert body["llm"] == {
        "trade_date": "2026-01-10", "today": 0.5, "month": 2.5, "cap": None,
        "learned_days": 0, "learning_days": 0, "unknown": True,
    }
    assert body["latest"] == SHARED_LATEST
    strategy = body["performance"]["strategy"]
    assert strategy["cumulative"] == pytest.approx(0.00495)
    assert strategy["annualized"] == pytest.approx(1.00495 ** (365 / 2) - 1)
    assert strategy["max_drawdown"] == pytest.approx(1 - 10_049.5 / 10_099.5)
    assert strategy["calmar"] == pytest.approx(strategy["annualized"] / strategy["max_drawdown"])
    assert strategy["cumulative"] < 10_050.0 / 10_000.0 - 1  # less the signals' spend
    # The baselines are the daily account's: the same two closes, +1%, no drawdown.
    for name in ("equal_weight", "btc"):
        assert body["performance"][name]["cumulative"] == pytest.approx(0.01)
        assert body["performance"][name]["calmar"] is None

    [position] = body["positions"]
    assert position["inst"] == "BTC-USDT-SWAP" and position["coin"] == "BTC-USD"
    assert position["qty"] == 0.03 and position["entry"] == 78_000.0
    assert position["stop"] == 74_000.0 and position["price"] == 79_000.0
    assert position["notional"] == pytest.approx(2_370.0)
    assert position["unrealized"] == pytest.approx(30.0)
    assert position["stop_distance"] == pytest.approx(5_000 / 79_000)


def test_intraday_spend_of_unknown_cost_earlier_in_the_month_is_flagged(tmp_path):
    # Today's one signal is priced; the call of unknown cost is of an earlier day of the month.
    signals = [
        (MONTH0 + HOUR, "BTC-USD", SignalResult("Long", 3, "breakout", None, 1_000, 200, None)),
        (DAY0, "BTC-USD", SignalResult("Flat", 2, "range", None, 800, 100, 0.5)),
    ]
    body = build_intraday(tmp_path, signals=signals).get("/api/accounts/intraday/overview").json()
    assert body["llm"]["today"] == 0.5 and body["llm"]["month"] == 0.5
    assert body["llm"]["unknown"] is True


def test_intraday_overview_before_the_validation_period(tmp_path):
    body = build_intraday(tmp_path, validated=False).get("/api/accounts/intraday/overview").json()
    assert body["equity"] == 10_000.0 and body["positions"] == []
    assert body["validation_start"] is None and body["days"] == 0
    assert body["performance"] == {"strategy": None, "equal_weight": None, "btc": None}
    assert body["llm"] == {
        "trade_date": "2026-01-10", "today": 0, "month": 0, "cap": None,
        "learned_days": 0, "learning_days": 0, "unknown": False,
    }
    assert body["latest"] == SHARED_LATEST


def test_an_account_that_researches_nothing_shows_the_daily_research_read_only(tmp_path):
    client = build_intraday(tmp_path)
    daily = Settings(home=tmp_path).ledger_path
    before = daily.read_bytes()
    assert client.get("/api/accounts/intraday/overview").json()["latest"] == SHARED_LATEST
    assert daily.read_bytes() == before

    alone = tmp_path / "alone"
    ledger = Ledger(Settings(home=alone).intraday_ledger_path)
    ledger.initialize(10_000.0, T0)
    ledger.db.close()
    client = TestClient(create_app(Settings(home=alone), CountingOKX()))
    assert client.get("/api/accounts/intraday/overview").json()["latest"] is None
    assert not Settings(home=alone).ledger_path.exists()  # looked for, not created


def test_every_account_scores_the_shared_research(tmp_path):
    client = build_intraday(tmp_path)
    settings = Settings(home=tmp_path)
    for path in (settings.demo_ledger_path, settings.live_ledger_path):
        ledger = Ledger(path)
        ledger.initialize(1_000.0, T0)
        ledger.db.close()
    log = TradingMemoryLog({"memory_log_path": str(settings.memory_log_path)})
    log.store_decision("BTC-USD", "2026-01-08", "Rating: Underweight\n\nx")
    log.update_with_outcome("BTC-USD", "2026-01-08", -0.05, -0.03, 5, "note", "2026-01-15")
    paper = client.get("/api/accounts/paper/accuracy").json()
    # A bearish rating is right when the coin falls behind the benchmark.
    assert paper["by_rating"] == {"Underweight": {"count": 1, "hit_rate": 1.0, "mean_alpha": -0.03}}
    for account in ("intraday", "demo", "live"):
        assert client.get(f"/api/accounts/{account}/accuracy").json() == paper


def test_intraday_equity_nets_the_signals_spend(tmp_path):
    body = build_intraday(tmp_path).get("/api/accounts/intraday/equity").json()
    assert body["live"] == {"ts": "2026-01-10T00:30:00Z", "equity": pytest.approx(10_030.0)}
    assert [p["ts"] for p in body["points"]] == [
        "2026-01-10T00:00:00Z", "2026-01-11T00:00:00Z", "2026-01-12T00:00:00Z"
    ]
    assert [p["strategy"] for p in body["points"]] == [10_000.0, 10_100.0, 10_050.0]
    # The 0.5 of the signals from the first midnight on comes off the midnights after it; a
    # call of unknown cost comes off as nothing, and the signals before the validation period
    # do not count. The attempts (none in this ledger) are not asked.
    assert [p["strategy_net"] for p in body["points"]] == [10_000.0, 10_099.5, 10_049.5]
    assert [p["equal_weight"] for p in body["points"]] == [10_000.0, pytest.approx(10_100.0), None]
    assert [p["btc"] for p in body["points"]] == [10_000.0, pytest.approx(10_100.0), None]


def test_intraday_daily_takes_the_llm_spend_from_the_signals(tmp_path):
    body = build_intraday(tmp_path).get("/api/accounts/intraday/daily").json()
    # 01-10 has the two signals of that midnight: 0.5 and one of unknown cost, which
    # counts as nothing; the signals before the validation period are not asked.
    assert [(d["date"], d["llm_cost"], d["fills"]) for d in body["days"]] == [
        ("2026-01-12", 0.0, 0), ("2026-01-11", 0.0, 0), ("2026-01-10", 0.5, 0),
    ]
    assert body["days"][0]["close"] == pytest.approx(10_030.0)  # long 0.03 from 78,000 at 79,000


# -- prices that cannot be used ----------------------------------------------------


@pytest.mark.parametrize("price", [price for price, _ in BAD_PRICES])
def test_a_last_price_that_cannot_be_used_is_no_quote(tmp_path, price):
    okx = CountingOKX()
    okx.last = price
    client = build(tmp_path, okx)
    response = client.get("/api/accounts/paper/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["equity"] is None and body["positions"][0]["price"] is None
    assert body["market"] == {
        "ok": False, "since": "2026-01-10T00:30:00Z",
        "error": f"OKXError: OKX quotes {BTC.swap} at {price}, not a positive finite number",
    }
    equity = client.get("/api/accounts/paper/equity")
    assert equity.status_code == 200 and equity.json()["live"]["equity"] is None


def test_a_last_price_that_cannot_be_used_serves_the_last_usable_one(tmp_path, monkeypatch):
    clock = [1_000.0]
    monkeypatch.setattr(data.time, "monotonic", lambda: clock[0])
    okx = CountingOKX()
    client = build(tmp_path, okx)
    assert client.get("/api/accounts/paper/overview").json()["equity"] == pytest.approx(10_020.0)
    okx.last = math.nan
    clock[0] += data.PRICE_TTL + 1  # the price expired, and the one OKX serves now is NaN
    stale = client.get("/api/accounts/paper/overview").json()
    assert stale["equity"] == pytest.approx(10_020.0)  # marked at the last usable price
    assert stale["positions"][0]["price"] == 79_000.0 and stale["market"]["ok"] is False


@pytest.mark.parametrize("close", [price for price, _ in BAD_PRICES])
def test_the_baselines_leave_a_midnight_whose_close_cannot_be_used_unpriced(tmp_path, close):
    okx = CountingOKX()
    okx.daily = [Bar(DAY0 - DAY_MS, 0, 0, 0, 80_000), Bar(DAY0, 0, 0, 0, close)]
    response = build(tmp_path, okx).get("/api/accounts/paper/equity")
    assert response.status_code == 200
    points = response.json()["points"]
    assert [p["equal_weight"] for p in points] == [10_000.0, None, None]
    assert [p["btc"] for p in points] == [10_000.0, None, None]


@pytest.mark.parametrize("close", [price for price, _ in BAD_PRICES])
def test_without_a_usable_close_to_buy_at_the_overview_has_no_baselines(tmp_path, close):
    okx = CountingOKX()
    okx.daily = [Bar(DAY0 - DAY_MS, 0, 0, 0, close), Bar(DAY0, 0, 0, 0, 80_800)]
    response = build(tmp_path, okx).get("/api/accounts/paper/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["performance"]["equal_weight"] is None and body["performance"]["btc"] is None
    assert body["equity"] == pytest.approx(10_020.0) and body["market"]["ok"] is True
