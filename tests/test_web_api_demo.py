"""The web API's view of the demo account (ADR 0008): the third account in the list,
its last reconciliation with the exchange, and the comparison with the intraday
account it follows."""

import pytest

from tests.test_trader_paper import BTC, DAY0, T0
from tests.test_web_api import HOUR, MINUTE, SIGNALS, build, build_intraday
from trader.intraday.types import SignalResult
from trader.ledger import Fill, Ledger, Position
from trader.okx import DAY_MS
from trader.settings import Settings

PROBLEM = "BTC-USDT-SWAP 在交易所是 cross 5×，不是设计的 cross 3×"


def build_demo(tmp_path, okx=None, with_intraday=True):
    """build_intraday() with the demo account beside the other two: the intraday account
    bought 0.03 BTC at 78,000 in the hour of T0 and the demo followed seven minutes later
    with 0.02 at 78,039; the exchange's view of the position and its stop are in the
    ledger's meta, as the job leaves them. with_intraday=False leaves the paper and the
    demo ledgers only."""
    client = build_intraday(tmp_path, okx) if with_intraday else build(tmp_path, okx)
    settings = Settings(home=tmp_path)
    if with_intraday:
        intraday = Ledger(settings.intraday_ledger_path)
        intraday.commit(
            positions=intraday.positions(), cash=10_000.0,
            fills=[Fill(T0, BTC.swap, 0.03, 78_000.0, 1.17, "trade", "2026-01-10")],
        )
        intraday.db.close()
    ledger = Ledger(settings.demo_ledger_path)
    ledger.initialize(10_000.0, T0)
    ledger.commit(
        positions={BTC.swap: Position(0.02, 78_039.0, 77_000.0)}, cash=9_999.2,
        fills=[Fill(T0 + 7 * MINUTE, BTC.swap, 0.02, 78_039.0, 0.78, "trade", "2026-01-10")],
        snapshots=[(DAY0, 10_000.0), (DAY0 + DAY_MS, 10_050.0), (DAY0 + 2 * DAY_MS, 10_040.0)],
        meta={
            "validation_start": DAY0, "peak": 10_050.0, "synced_at": T0 + 8 * MINUTE,
            "equity": 10_038.4, "decided_hour": DAY0, "problems": [PROBLEM],
            "exchange_positions": {
                BTC.swap: {
                    "contracts": 2.0, "avg_price": 78_039.0, "unrealized": 39.2, "leverage": 5.0,
                    "margin_mode": "cross", "liquidation_price": 55_000.0,
                },
            },
            "pending_stops": [{
                "inst": BTC.swap, "side": "sell", "contracts": 2.0, "trigger": 77_000.0,
                "client_id": "stp1btc1",
            }],
        },
    )
    ledger.db.close()
    return client


def test_demo_overview_has_no_llm_spend_and_marks_the_exchange_position(tmp_path):
    body = build_demo(tmp_path).get("/api/accounts/demo/overview").json()
    assert body["llm"] is None and body["latest"] is None
    assert body["equity"] == pytest.approx(9_999.2 + 0.02 * (79_000.0 - 78_039.0))  # marked at the quote
    assert body["days"] == 2
    assert body["performance"]["strategy"]["cumulative"] == pytest.approx(0.004)
    (position,) = body["positions"]
    assert (position["coin"], position["qty"], position["stop"]) == ("BTC-USD", 0.02, 77_000.0)


def test_demo_equity_is_the_exchanges_without_any_llm_netting(tmp_path):
    client = build_demo(tmp_path)
    body = client.get("/api/accounts/demo/equity").json()
    assert [(p["strategy"], p["strategy_net"]) for p in body["points"]] == [
        (10_000.0, 10_000.0), (10_050.0, 10_050.0), (10_040.0, 10_040.0)
    ]
    daily = client.get("/api/accounts/demo/daily").json()
    assert [d["llm_cost"] for d in daily["days"]] == [0.0, 0.0, 0.0]
    (fill,) = client.get("/api/accounts/demo/fills").json()
    assert (fill["coin"], fill["qty"], fill["fee"], fill["realized_net"]) == ("BTC-USD", 0.02, 0.78, -0.78)


def test_execution_reads_the_last_reconciliation_as_the_job_left_it(tmp_path):
    body = build_demo(tmp_path).get("/api/accounts/demo/execution").json()
    assert body == {
        "synced_at": "2026-01-10T00:38:00Z",
        "equity": 10_038.4,
        "cash": 9_999.2,
        "halted": False,
        "decided_hour": "2026-01-10T00:00:00Z",
        "problems": [PROBLEM],
        "positions": [{
            "inst": "BTC-USDT-SWAP", "coin": "BTC-USD", "contracts": 2.0, "avg_price": 78_039.0,
            "unrealized": 39.2, "leverage": 5.0, "margin_mode": "cross",
            "liquidation_price": 55_000.0, "stop": 77_000.0,
        }],
        "stops": [{
            "inst": "BTC-USDT-SWAP", "coin": "BTC-USD", "side": "sell", "contracts": 2.0,
            "trigger": 77_000.0, "client_id": "stp1btc1",
        }],
    }


def test_execution_of_a_fresh_demo_ledger_is_empty(tmp_path):
    client = build(tmp_path)
    ledger = Ledger(Settings(home=tmp_path).demo_ledger_path)
    ledger.initialize(10_000.0, T0)
    ledger.db.close()
    assert client.get("/api/accounts/demo/execution").json() == {
        "synced_at": None, "equity": None, "cash": 10_000.0, "halted": False,
        "decided_hour": None, "problems": [], "positions": [], "stops": [],
    }


def test_mirror_pairs_the_demo_trades_with_the_intraday_fills_of_the_hour(tmp_path):
    body = build_demo(tmp_path).get("/api/accounts/demo/mirror").json()
    assert body["positions"][0] == {
        "inst": "BTC-USDT-SWAP", "coin": "BTC-USD",
        "demo": {"qty": 0.02, "entry": 78_039.0, "stop": 77_000.0},
        "intraday": {"qty": 0.03, "entry": 78_000.0, "stop": 74_000.0},
        "same_side": True,
    }
    assert body["positions"][1] == {
        "inst": "ETH-USDT-SWAP", "coin": "ETH-USD", "demo": None, "intraday": None, "same_side": True,
    }
    (trade,) = body["trades"]
    assert trade["hour"] == "2026-01-10T00:00:00Z" and trade["coin"] == "BTC-USD"
    assert trade["demo"] == {"ts": "2026-01-10T00:37:00Z", "qty": 0.02, "price": 78_039.0, "fee": 0.78}
    assert trade["intraday"] == {"ts": "2026-01-10T00:30:00Z", "qty": 0.03, "price": 78_000.0, "fee": 1.17}
    assert trade["slippage_bps"] == pytest.approx(5.0)
    assert [(p["demo"], p["intraday"]) for p in body["equity"]] == [
        (0.0, 0.0),
        (pytest.approx(0.005), pytest.approx(0.01)),
        (pytest.approx(0.004), pytest.approx(0.005)),
    ]
    assert body["summary"] == {
        "trades": 1, "matched": 1, "avg_slippage_bps": pytest.approx(5.0),
        "demo_return": pytest.approx(0.004), "intraday_return": pytest.approx(0.005),
    }


def test_mirror_slippage_is_positive_when_the_demo_sold_lower(tmp_path):
    client = build_demo(tmp_path)
    ledger = Ledger(Settings(home=tmp_path).demo_ledger_path)
    ledger.commit(
        positions={}, cash=10_000.0,
        fills=[Fill(T0 + 9 * MINUTE, BTC.swap, -0.02, 77_961.0, 0.78, "trade", "2026-01-10")],
    )
    ledger.db.close()
    trades = client.get("/api/accounts/demo/mirror").json()["trades"]
    assert [t["demo"]["qty"] for t in trades] == [-0.02, 0.02]  # newest first
    assert trades[0]["slippage_bps"] == pytest.approx(5.0)


def test_mirror_without_a_matching_intraday_fill_has_no_slippage(tmp_path):
    client = build_demo(tmp_path)
    ledger = Ledger(Settings(home=tmp_path).intraday_ledger_path)
    ledger.db.execute("DELETE FROM fills")
    ledger.db.commit()
    ledger.db.close()
    body = client.get("/api/accounts/demo/mirror").json()
    (trade,) = body["trades"]
    assert trade["intraday"] is None and trade["slippage_bps"] is None
    assert body["summary"]["matched"] == 0 and body["summary"]["avg_slippage_bps"] is None


def test_mirror_takes_a_limit(tmp_path):
    client = build_demo(tmp_path)
    assert client.get("/api/accounts/demo/mirror", params={"limit": 0}).status_code == 422
    assert client.get("/api/accounts/demo/mirror", params={"limit": 1}).json()["summary"]["trades"] == 1


def test_execution_and_mirror_belong_to_the_demo_account_only(tmp_path):
    client = build_demo(tmp_path)
    for account in ("paper", "intraday"):
        for route in ("execution", "mirror"):
            response = client.get(f"/api/accounts/{account}/{route}")
            assert response.status_code == 404 and "exchange" in response.json()["detail"]
    # The mirror needs the intraday ledger beside the demo's.
    response = build_demo(tmp_path / "alone", with_intraday=False).get("/api/accounts/demo/mirror")
    assert response.status_code == 404 and "intraday" in response.json()["detail"]


# -- the signals it follows -------------------------------------------------------


def test_demo_signals_are_the_intraday_ones_with_what_the_demo_did_each_hour(tmp_path):
    """Hour by hour after the fixture's (BTC executed at T0+7min, decided_hour DAY0):
    01:00 the reconciliation found a problem, 02:00 no decision came in time, 03:00 the
    ETH order failed and the SOL one was refused while BTC needed nothing, 04:00 is not
    handled yet; the signals from before the demo account existed carry None."""
    client = build_demo(tmp_path)
    settings = Settings(home=tmp_path)
    long = SignalResult("Long", 2, "up", None, 100, 10, 0.1)
    intraday = Ledger(settings.intraday_ledger_path)
    for hour in (1, 2, 3, 4):
        for coin in ("BTC-USD", "ETH-USD", "SOL-USD"):
            intraday.record_signal(DAY0 + hour * HOUR + 3 * MINUTE, coin, long)
    intraday.db.close()
    demo = Ledger(settings.demo_ledger_path)
    with demo.transaction():
        demo.add_event(DAY0 + HOUR + 10 * MINUTE, "problem", PROBLEM)
        demo.add_event(DAY0 + 2 * HOUR + 25 * MINUTE, "skipped", "日内账户到 02:25 还没决定 02:00 这个小时，demo 本小时不交易")
        demo.add_event(DAY0 + 3 * HOUR + 10 * MINUTE, "order_failed", "下单失败：ETH-USDT-SWAP +3 张：/api/v5/trade/order failed with code 51008: Insufficient balance")
        demo.add_event(DAY0 + 3 * HOUR + 10 * MINUTE, "order_refused", "拒绝下单：SOL-USDT-SWAP 变动 +40 名义 6,000 USDT 超过净值 10,000 的 0.5 倍，可能是算错了")
        demo.add_event(DAY0 + 3 * HOUR + 10 * MINUTE, "order", "BTC-USDT-SWAP +0 张")
    demo.commit(positions=demo.positions(), cash=demo.get("cash"), meta={"decided_hour": DAY0 + 3 * HOUR})
    demo.db.close()

    rows = client.get("/api/accounts/demo/signals").json()
    assert len(rows) == len(SIGNALS) + 12 and rows[0]["ts"] == "2026-01-10T04:03:00Z"
    assert set(rows[0]) == {
        "ts", "coin", "signal", "conviction", "reason", "error", "tokens_in", "tokens_out", "cost_usd", "followed"
    }
    followed = {(r["ts"][11:16], r["coin"][:3]): r["followed"] for r in rows if r["ts"] >= "2026-01-10"}
    assert {k: v for k, v in followed.items() if k[0] >= "01:00"} == {
        ("04:03", "BTC"): "pending", ("04:03", "ETH"): "pending", ("04:03", "SOL"): "pending",
        ("03:03", "BTC"): "no_change", ("03:03", "ETH"): "failed", ("03:03", "SOL"): "failed",
        ("02:03", "BTC"): "skipped", ("02:03", "ETH"): "skipped", ("02:03", "SOL"): "skipped",
        ("01:03", "BTC"): "blocked", ("01:03", "ETH"): "blocked", ("01:03", "SOL"): "blocked",
    }
    # The fixture's hour: the BTC trade filled at 00:37, ETH needed nothing.
    assert followed[("00:00", "BTC")] == "executed" and followed[("00:00", "ETH")] == "no_change"
    # Before the demo account existed (its ledger opened at T0): nothing to say.
    before = [r["followed"] for r in rows if r["ts"] < "2026-01-10"]
    assert len(before) == 3 and before == [None, None, None]


def test_demo_signals_honour_since_and_limit_and_are_empty_without_any(tmp_path):
    client = build_demo(tmp_path)
    rows = client.get("/api/accounts/demo/signals", params={"limit": 2}).json()
    assert [(r["coin"], r["followed"]) for r in rows] == [("ETH-USD", "no_change"), ("BTC-USD", "executed")]
    rows = client.get("/api/accounts/demo/signals", params={"since": "2026-01-10T00:00:00Z"}).json()
    assert len(rows) == 2
    assert client.get("/api/accounts/demo/signals", params={"limit": 0}).status_code == 422
    fresh = build_demo(tmp_path / "fresh", with_intraday=True)
    Ledger(Settings(home=tmp_path / "fresh").intraday_ledger_path).db.execute("DELETE FROM signals").connection.commit()
    assert fresh.get("/api/accounts/demo/signals").json() == []

