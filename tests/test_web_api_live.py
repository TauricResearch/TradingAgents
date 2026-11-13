"""The web API's view of the live account (ADR 0010): the fourth account in the list,
flagged as real money; the routes of an account that executes on an exchange, with its
pause read as its profile reads it and its shadow run told apart; the comparison with the
intraday account or with the demo one; and only 404s until live init opens its ledger."""

import pytest

from tests.test_trader_paper import BTC, DAY0, T0
from tests.test_web_api import HOUR, MINUTE
from tests.test_web_api_demo import build_demo
from trader.intraday.types import SignalResult
from trader.ledger import Fill, Ledger, Position
from trader.live.account import LIVE
from trader.okx import DAY_MS
from trader.settings import Settings
from web.api import data

ROUTES = (
    "overview", "equity", "daily", "fills", "funding", "events", "attempts", "signals",
    "execution", "mirror",
)


def build_live(tmp_path):
    """build_demo() with the live account beside the others, unlocked and trading: it
    followed the intraday BTC buy of T0's hour eight minutes after it with 0.01 at
    78,117, the one contract the exchange holds behind its stop."""
    client = build_demo(tmp_path)
    ledger = Ledger(Settings(home=tmp_path).live_ledger_path)
    ledger.initialize(1_000.0, T0)
    ledger.commit(
        positions={BTC.swap: Position(0.01, 78_117.0, 77_000.0)}, cash=999.61,
        fills=[Fill(T0 + 8 * MINUTE, BTC.swap, 0.01, 78_117.0, 0.39, "trade", "2026-01-10")],
        snapshots=[(DAY0, 1_000.0), (DAY0 + DAY_MS, 1_010.0), (DAY0 + 2 * DAY_MS, 1_002.0)],
        meta={
            "validation_start": DAY0, "peak": 1_010.0, "synced_at": T0 + 9 * MINUTE,
            "equity": 1_000.4, "decided_hour": DAY0, "paused": False, "setup_done": True,
            "exchange_positions": {
                BTC.swap: {
                    "contracts": 1.0, "avg_price": 78_117.0, "unrealized": 0.88, "leverage": 3.0,
                    "margin_mode": "cross", "liquidation_price": 52_000.0,
                },
            },
            "pending_stops": [{
                "inst": BTC.swap, "side": "sell", "contracts": 1.0, "trigger": 77_000.0,
                "client_id": "stp1btc9",
            }],
        },
    )
    ledger.db.close()
    return client


def open_live(tmp_path, now_ms=T0):
    """The live ledger as live init leaves it: no ``paused`` in its meta."""
    ledger = Ledger(Settings(home=tmp_path).live_ledger_path)
    ledger.initialize(1_000.0, now_ms)
    return ledger


def test_the_live_account_is_listed_last_as_real_money(tmp_path):
    *_, live = build_live(tmp_path).get("/api/accounts").json()
    assert (live["id"], live["kind"], live["exchange"], live["live"]) == ("live", "live", True, True)
    assert (live["capital"], live["validation_start"], live["halted"]) == (1_000.0, "2026-01-10T00:00:00Z", False)


def test_without_its_ledger_every_route_of_the_live_account_is_404(tmp_path):
    client = build_demo(tmp_path)  # live init has not run
    *_, live = client.get("/api/accounts").json()
    assert live["id"] == "live" and live["capital"] is None
    for route in ROUTES:
        response = client.get(f"/api/accounts/live/{route}")
        assert response.status_code == 404 and "ledger" in response.json()["detail"], route
    response = client.get("/api/accounts/demo/mirror", params={"against": "live"})
    assert response.status_code == 404 and "ledger" in response.json()["detail"]


def test_a_live_account_just_opened_is_paused_in_its_shadow_run(tmp_path):
    client = build_demo(tmp_path)
    open_live(tmp_path).db.close()
    body = client.get("/api/accounts/live/execution").json()
    assert (body["paused"], body["shadow_run"], body["pause_reasons"]) == (True, True, [])
    # The dashboard does not import trader.live, so it repeats the profile's flag.
    assert data.accounts(Settings(home=tmp_path))["live"].born_paused is LIVE.born_paused


def test_the_unlock_ends_the_shadow_run_and_a_later_pause_is_a_pause_with_its_reasons(tmp_path):
    client = build_demo(tmp_path)
    ledger = open_live(tmp_path)
    ledger.set("paused", False)  # live resume: the next run sets the account up and trades
    ledger.db.close()
    body = client.get("/api/accounts/live/execution").json()
    assert (body["paused"], body["shadow_run"]) == (False, False)

    ledger = Ledger(Settings(home=tmp_path).live_ledger_path)
    reason = {"key": "fingerprint", "text": "程序的代码变了，确认后再解除", "since": DAY0 + 2 * HOUR}
    ledger.commit(
        positions={}, cash=1_000.0,
        meta={"setup_done": True, "paused": True, "pause_reasons": [reason]},
    )
    ledger.db.close()
    body = client.get("/api/accounts/live/execution").json()
    assert (body["paused"], body["shadow_run"]) == (True, False)
    assert body["pause_reasons"] == [{"text": reason["text"], "since": "2026-01-10T02:00:00Z"}]


def test_live_execution_reads_the_last_reconciliation_as_the_job_left_it(tmp_path):
    body = build_live(tmp_path).get("/api/accounts/live/execution").json()
    assert (body["paused"], body["shadow_run"], body["halted"]) == (False, False, False)
    assert (body["equity"], body["cash"]) == (1_000.4, 999.61)
    assert body["decided_hour"] == "2026-01-10T00:00:00Z"
    (position,) = body["positions"]
    assert (position["coin"], position["contracts"], position["stop"]) == ("BTC-USD", 1.0, 77_000.0)
    (stop,) = body["stops"]
    assert (stop["side"], stop["trigger"]) == ("sell", 77_000.0)


def test_a_halted_live_account_says_so_on_every_route_that_tells(tmp_path):
    client = build_live(tmp_path)
    ledger = Ledger(Settings(home=tmp_path).live_ledger_path)
    ledger.set("halted", True)
    ledger.db.close()
    assert client.get("/api/accounts/live/execution").json()["halted"] is True
    assert client.get("/api/accounts/live/overview").json()["halted"] is True
    assert client.get("/api/accounts").json()[-1]["halted"] is True


def test_live_overview_has_no_llm_spend_and_marks_the_exchange_position(tmp_path):
    body = build_live(tmp_path).get("/api/accounts/live/overview").json()
    assert body["llm"] is None and body["latest"] is None
    assert body["equity"] == pytest.approx(999.61 + 0.01 * (79_000.0 - 78_117.0))  # marked at the quote
    assert body["performance"]["strategy"]["cumulative"] == pytest.approx(0.002)
    (position,) = body["positions"]
    assert (position["coin"], position["qty"], position["stop"]) == ("BTC-USD", 0.01, 77_000.0)


def test_live_beside_the_intraday_account_by_default_and_beside_the_demo_on_request(tmp_path):
    client = build_live(tmp_path)
    body = client.get("/api/accounts/live/mirror").json()
    assert body["against"] == "intraday"
    assert body["positions"][0]["own"] == {"qty": 0.01, "entry": 78_117.0, "stop": 77_000.0}
    assert body["positions"][0]["other"] == {"qty": 0.03, "entry": 78_000.0, "stop": 74_000.0}
    (trade,) = body["trades"]
    assert trade["own"]["price"] == 78_117.0 and trade["other"]["price"] == 78_000.0
    assert trade["slippage_bps"] == pytest.approx(15.0)
    assert body["summary"]["own_return"] == pytest.approx(0.002)
    assert body["summary"]["other_return"] == pytest.approx(0.005)

    body = client.get("/api/accounts/live/mirror", params={"against": "demo"}).json()
    assert body["against"] == "demo"
    assert body["positions"][0]["other"] == {"qty": 0.02, "entry": 78_039.0, "stop": 77_000.0}
    (trade,) = body["trades"]
    assert trade["other"] == {"ts": "2026-01-10T00:37:00Z", "qty": 0.02, "price": 78_039.0, "fee": 0.78}
    assert trade["slippage_bps"] == pytest.approx((78_117.0 - 78_039.0) / 78_039.0 * 10_000)
    assert [(p["own"], p["other"]) for p in body["equity"]] == [
        (0.0, 0.0),
        (pytest.approx(0.01), pytest.approx(0.005)),
        (pytest.approx(0.002), pytest.approx(0.004)),
    ]
    # The demo beside the live account is the same pairing the other way round.
    body = client.get("/api/accounts/demo/mirror", params={"against": "live"}).json()
    (trade,) = body["trades"]
    assert trade["own"]["price"] == 78_039.0 and trade["other"]["price"] == 78_117.0


def test_live_beside_the_demo_leaves_out_the_money_moved_into_the_demo(tmp_path):
    client = build_live(tmp_path)
    settings = Settings(home=tmp_path)
    demo = Ledger(settings.demo_ledger_path)
    # 10,040 moved in at 1.004 a unit bought 10,000 units: 20,080 is still 1.004 a unit.
    demo.commit(
        positions=demo.positions(), cash=demo.get("cash"), snapshots=[(DAY0 + 3 * DAY_MS, 20_080.0)],
        meta={"units": 20_000.0, "contributed": 20_040.0},
    )
    demo.db.close()
    live = Ledger(settings.live_ledger_path)
    live.commit(positions=live.positions(), cash=live.get("cash"), snapshots=[(DAY0 + 3 * DAY_MS, 1_004.0)])
    live.db.close()
    body = client.get("/api/accounts/live/mirror", params={"against": "demo"}).json()
    assert [(p["own"], p["other"]) for p in body["equity"]][-1] == (pytest.approx(0.004), pytest.approx(0.004))
    assert body["summary"]["other_return"] == pytest.approx(0.004)


def test_live_is_compared_with_the_intraday_account_or_the_other_exchange_account_only(tmp_path):
    client = build_live(tmp_path)
    for against in ("paper", "live", "nope"):
        response = client.get("/api/accounts/live/mirror", params={"against": against})
        assert response.status_code == 404 and "compared" in response.json()["detail"], against
    Settings(home=tmp_path).demo_ledger_path.unlink()
    response = client.get("/api/accounts/live/mirror", params={"against": "demo"})
    assert response.status_code == 404 and "ledger" in response.json()["detail"]


def test_live_signals_are_the_intraday_ones_and_an_hour_of_its_shadow_run_is_paused(tmp_path):
    client = build_demo(tmp_path)
    settings = Settings(home=tmp_path)
    intraday = Ledger(settings.intraday_ledger_path)
    for coin in ("BTC-USD", "ETH-USD", "SOL-USD"):
        intraday.record_signal(DAY0 + HOUR + 3 * MINUTE, coin, SignalResult("Long", 2, "up", None, 100, 10, 0.1))
    intraday.db.close()
    live = open_live(tmp_path, DAY0 + HOUR)  # opened in the 01:00 hour, so in its shadow run
    with live.transaction():
        live.add_event(DAY0 + HOUR + 10 * MINUTE, "shadow_order", "BTC-USDT-SWAP 买入 1 张，名义 780 USDT，信号 Long")
    live.commit(positions={}, cash=1_000.0, meta={"decided_hour": DAY0 + HOUR})
    live.db.close()
    rows = client.get("/api/accounts/live/signals").json()
    assert {r["coin"]: r["followed"] for r in rows if r["ts"] == "2026-01-10T01:03:00Z"} == {
        "BTC-USD": "paused", "ETH-USD": "paused", "SOL-USD": "paused",
    }
    # Before live init, the demo's hour of T0 among them: nothing to say.
    assert {r["followed"] for r in rows if r["ts"] < "2026-01-10T01:00:00Z"} == {None}
