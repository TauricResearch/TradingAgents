"""Alerts on fixture data moving from one evaluation to the next: each kind fires on
its change, once, through the inbox and the (mocked) delivery channels."""

from __future__ import annotations

import json
import logging
import urllib.error
from datetime import date, datetime, timedelta, timezone

import pytest

import tradingagents.dataflows.config as config_module
from tests import phase4_db as p4, screener_db as fx
from tradingagents.dataflows.vendors.india import store
from tradingagents.screener import alerts, delivery, screens, snapshot, userdb, watchlists
from tradingagents.screener.alerts import IST, AlertError

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 2, 20, 0)
SECRETS = {"TELEGRAM_TOKEN": "123456:SECRET-TELEGRAM-TOKEN", "TELEGRAM_CHAT_ID": "SECRET-CHAT-42",
           "WEBHOOK_URL": "https://hooks.example.com/T000/SECRET-WEBHOOK-PATH", "SMTP_HOST": "smtp.example.com",
           "SMTP_USER": "secret-user@example.com", "SMTP_PASSWORD": "SECRET-SMTP-PASSWORD",
           "SMTP_TO": "me@example.com"}


@pytest.fixture
def india(tmp_path):
    path = tmp_path / "india.db"
    p4.build(path)
    conn = store.connect(path)
    rebuild(conn, "2026-10-02T20:00:00")
    config_module._config["india_db_path"] = str(path)
    yield conn
    conn.close()


@pytest.fixture
def user(tmp_path):
    conn = userdb.connect(tmp_path / "user.db")
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def no_channels(monkeypatch):
    for name in SECRETS:
        monkeypatch.delenv(delivery.PREFIX + name, raising=False)


def rebuild(conn, stamp: str) -> None:
    """The live snapshot rebuilt, stamped as built at ``stamp``."""
    snapshot.build_snapshot(conn)
    conn.execute("UPDATE snapshot_builds SET built_at=? WHERE as_of_date='live'", (stamp,))
    conn.execute("UPDATE metrics_snapshot SET built_at=? WHERE as_of_date='live'", (stamp,))
    conn.commit()


def bar(conn, day: str, close: float, isin: str = fx.GROWCO) -> None:
    store.upsert_prices(conn, [(isin, day, close, close, close, close, 10_000, "EQ", "test")])
    conn.commit()


def last_close(conn, isin=fx.GROWCO) -> float:
    return store.get_prices(isin, conn=conn)[-1]["close"]


def run(user, india, now=T0, **kw):
    return alerts.evaluate(user, india, now=now, **kw)


def titles(user) -> list[str]:
    return [e["title"] for e in alerts.inbox(user)["items"]]


# --- Price ---------------------------------------------------------------------------------

def test_a_price_cross_fires_once_on_the_rising_edge(user, india):
    before = last_close(india)
    assert 180 < before < 200
    alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 200}, india)
    first = run(user, india)
    assert first.evaluated == 1 and first.fired == []  # the baseline: below 200
    bar(india, "2026-10-05", 205)
    fired = run(user, india, T0 + timedelta(days=3))
    assert len(fired.fired) == 1
    [event] = alerts.inbox(user)["items"]
    assert event["title"] == "GROWCO.NS closed at ₹205.00, above ₹200.00" and event["data_date"] == "2026-10-05"
    assert event["detail"]["price"] == 205 and event["detail"]["previousClose"] == pytest.approx(before)
    assert run(user, india, T0 + timedelta(days=3, hours=1)).fired == []  # the same data again: nothing
    bar(india, "2026-10-06", 210)
    assert run(user, india, T0 + timedelta(days=4)).fired == []  # still above: no new edge
    bar(india, "2026-10-07", 190)
    assert run(user, india, T0 + timedelta(days=5)).fired == []
    bar(india, "2026-10-08", 201)
    assert len(run(user, india, T0 + timedelta(days=6)).fired) == 1
    assert len(alerts.inbox(user)["items"]) == 2


def test_already_true_when_created_does_not_fire(user, india):
    alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 150}, india)
    assert run(user, india).fired == []
    bar(india, "2026-10-05", 199)
    assert run(user, india, T0 + timedelta(days=3)).fired == []


def test_a_gap_between_evaluations_is_read_bar_by_bar(user, india):
    alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 200}, india)
    run(user, india)
    for day, close in (("2026-10-05", 195), ("2026-10-06", 205), ("2026-10-07", 199), ("2026-10-08", 206)):
        bar(india, day, close)
    out = run(user, india, T0 + timedelta(days=7))
    assert len(out.fired) == 2
    assert sorted(e["data_date"] for e in alerts.inbox(user)["items"]) == ["2026-10-06", "2026-10-08"]


def test_below_and_daily_moves(user, india):
    close = last_close(india)
    alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "below", "level": 180}, india)
    alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "move", "pct": 5}, india)
    alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "move", "pct": 5, "direction": "down"}, india)
    run(user, india)
    bar(india, "2026-10-05", round(close * 1.06, 2))
    run(user, india, T0 + timedelta(days=3))
    assert titles(user) == [f"GROWCO.NS rose 6.00% (₹{close:,.2f} to ₹{round(close * 1.06, 2):,.2f})"]
    bar(india, "2026-10-06", 170)
    run(user, india, T0 + timedelta(days=4))
    assert any(t.startswith("GROWCO.NS fell") for t in titles(user))
    assert any("below ₹180.00" in t for t in titles(user))


# --- Metric conditions ---------------------------------------------------------------------

def test_a_metric_condition_fires_when_it_turns_true(user, india):
    a = alerts.save(user, {"kind": "metric", "symbol": "GROWCO", "query": "Current price > 200\nPrice to earning > 0"},
                    india)
    assert a["name"] == "GROWCO.NS: Current price > 200 AND Price to earning > 0"
    run(user, india)
    assert alerts.get(user, a["id"])["status"]["value"] is False
    bar(india, "2026-10-05", 205)
    rebuild(india, "2026-10-05T20:00:00")
    out = run(user, india, T0 + timedelta(days=3))
    assert len(out.fired) == 1
    [event] = alerts.inbox(user)["items"]
    assert event["title"] == "GROWCO.NS: your condition is now true" and event["data_date"] == "2026-10-05"
    assert event["detail"]["values"]["Current price"] == 205
    assert run(user, india, T0 + timedelta(days=3, hours=2)).fired == []  # same snapshot: no double fire
    rebuild(india, "2026-10-05T21:00:00")  # a new snapshot, still true: no edge
    assert run(user, india, T0 + timedelta(days=3, hours=3)).fired == []


def test_a_condition_with_missing_data_never_fires(user, india):
    a = alerts.save(user, {"kind": "metric", "symbol": fx.NODATA, "query": "Return on equity > 10"}, india)
    run(user, india)
    rebuild(india, "2026-10-05T20:00:00")
    assert run(user, india, T0 + timedelta(days=3)).fired == []
    status = alerts.get(user, a["id"])["status"]
    assert status["value"] is None and "unknown" in status["message"]


def test_a_bad_condition_is_refused_with_its_position(user, india):
    with pytest.raises(AlertError) as caught:
        alerts.save(user, {"kind": "metric", "symbol": "GROWCO", "query": "Current price >> 200"}, india)
    error = caught.value.errors[0]
    assert {"message", "start", "end", "line", "col"} <= set(error) and error["start"] >= 14


def test_a_deleted_custom_ratio_is_reported_not_raised(user, india):
    ratio = screens.save_ratio(user, {"definition": "Double price = Current price * 2"})
    a = alerts.save(user, {"kind": "metric", "symbol": "GROWCO", "query": "Double price > 1"}, india)
    screens.delete_ratio(user, ratio.id)
    out = run(user, india)
    assert out.errors and not alerts.get(user, a["id"])["status"]["ok"]


# --- Screens --------------------------------------------------------------------------------

def test_screen_membership_changes_fire_with_who_entered_and_left(user, india):
    screen = screens.save_screen(user, {"name": "Pricey", "query": "Current price > 150"}, [])
    both = alerts.save(user, {"kind": "screen", "screen": screen["id"]}, india)
    entering = alerts.save(user, {"kind": "screen", "screen": screen["id"], "on": "enter"}, india)
    assert both["name"] == "Stocks entering or leaving “Pricey”"
    run(user, india)
    bar(india, "2026-10-05", 140)  # GROWCO leaves
    bar(india, "2026-10-05", 160, p4.ISINS["NEAR4000"])  # NEAR4000 enters
    rebuild(india, "2026-10-05T20:00:00")
    out = run(user, india, T0 + timedelta(days=3))
    assert len(out.fired) == 2
    by_alert = {e["alert_id"]: e for e in alerts.inbox(user)["items"]}
    event = by_alert[both["id"]]
    assert event["title"] == "“Pricey”: 1 entered and 1 left"
    assert [s["symbol"] for s in event["detail"]["entered"]] == ["NEAR4000.NS"]
    assert [s["symbol"] for s in event["detail"]["left"]] == ["GROWCO.NS"]
    assert by_alert[entering["id"]]["detail"]["left"] == []
    assert run(user, india, T0 + timedelta(days=3, hours=1)).fired == []
    rebuild(india, "2026-10-05T21:00:00")  # rebuilt, same members: nothing
    assert run(user, india, T0 + timedelta(days=3, hours=2)).fired == []


def test_presets_can_be_watched(user, india):
    a = alerts.save(user, {"kind": "screen", "screen": "preset:uptrend-large", "on": "leave"}, india)
    assert a["params"] == {"screen": "preset:uptrend-large", "on": "leave"}
    assert run(user, india).errors == []
    with pytest.raises(AlertError, match="saved screen"):
        alerts.save(user, {"kind": "screen", "screen": "999"}, india)


# --- Filings and shareholding -----------------------------------------------------------------

def test_new_filings_for_a_watchlist_fire_once(user, india):
    w = watchlists.save(user, {"name": "Core"})
    watchlists.add(user, w["id"], ["GROWCO", "LENDERBANK"], india)
    a = alerts.save(user, {"kind": "filing", "watchlistId": w["id"]}, india)
    now = datetime(2026, 10, 6, 20, 0)
    assert run(user, india, now).fired == []  # the baseline
    store.upsert_documents(india, [
        (fx.GROWCO, "2026-10-06", "results", "Consolidated results, period ended 2026-09-30", "https://x/r.xml", "t"),
        (fx.BANK, "2026-10-06", "credit_rating", "CRISIL reaffirms AAA", None, "NSE announcements"),
        (fx.GROWCO, "2026-01-01", "announcement", "Old news", None, "t"),
        (p4.ISINS["NEAR4000"], "2026-10-06", "results", "Not on the watchlist", None, "t")])
    store.upsert_action(india, isin=fx.GROWCO, ex_date="2026-10-20", type="dividend", details="DIV - RS 5 PER SH",
                        amount=5.0, seen="2026-10-06")
    india.commit()
    out = run(user, india, now + timedelta(hours=1))
    assert len(out.fired) == 1
    [event] = alerts.inbox(user)["items"]
    assert event["title"] == "3 new filings for your watchlist (2 stocks)" and event["alert_id"] == a["id"]
    kinds = sorted(i["kind"] for i in event["detail"]["items"])
    assert kinds == ["corporate_action", "credit_rating", "results"]
    assert run(user, india, now + timedelta(hours=2)).fired == []
    store.upsert_documents(india, [(fx.GROWCO, "2026-10-03", "shareholding", "Shareholding pattern, 2026-09-30",
                                    None, "t")])  # late, but inside the window
    india.commit()
    run(user, india, now + timedelta(hours=3))
    assert titles(user)[0] == "GROWCO.NS: new shareholding pattern"


def test_filing_kinds_filter_and_single_stock_targets(user, india):
    alerts.save(user, {"kind": "filing", "symbol": "GROWCO", "kinds": ["results"]}, india)
    now = datetime(2026, 10, 6, 20, 0)
    run(user, india, now)
    store.upsert_documents(india, [(fx.GROWCO, "2026-10-06", "results", "Q2 results", None, "t"),
                                   (fx.GROWCO, "2026-10-06", "board_meeting", "Board meeting", None, "t")])
    india.commit()
    run(user, india, now + timedelta(hours=1))
    [event] = alerts.inbox(user)["items"]
    assert event["title"] == "GROWCO.NS: new results" and event["symbol"] == "GROWCO.NS"


def pattern(conn, quarter_end, promoter, pledged, filed):
    store.upsert_shareholding(conn, isin=fx.GROWCO, quarter_end=quarter_end, filed_at=filed, filing_id=f"SHP-{quarter_end}",
                              source="test", values={"promoter_pct": promoter, "fii_pct": 18.0, "dii_pct": 12.0,
                                                     "public_pct": 100 - promoter - 30, "num_shareholders": 125_000,
                                                     "total_shares": 200_000_000, "pledged_pct": pledged,
                                                     "encumbered_pct": pledged})
    conn.commit()


def test_shareholding_changes_beyond_a_threshold_fire(user, india):
    promoter = alerts.save(user, {"kind": "shareholding", "symbol": "GROWCO", "measure": "promoter", "points": 1},
                           india)
    pledge = alerts.save(user, {"kind": "shareholding", "symbol": "GROWCO", "measure": "pledge", "points": 1}, india)
    falling = alerts.save(user, {"kind": "shareholding", "symbol": "GROWCO", "measure": "promoter", "points": 1,
                                 "direction": "down"}, india)
    run(user, india)
    pattern(india, "2026-09-30", 54.0, 2.0, "2026-10-15T12:00:00")
    out = run(user, india, datetime(2026, 10, 16, 9, 0))
    fired = {e["alert_id"]: e for e in alerts.inbox(user)["items"]}
    assert len(out.fired) == 2 and set(fired) == {promoter["id"], pledge["id"]} and falling["id"] not in fired
    assert fired[promoter["id"]]["title"] == "GROWCO.NS: promoter holding +2.00 pts"
    assert fired[pledge["id"]]["detail"]["changes"][0]["change"] == pytest.approx(1.5)
    assert run(user, india, datetime(2026, 10, 16, 10, 0)).fired == []


# --- Edge, cooldown, expiry, idempotency --------------------------------------------------------

def test_cooldown_holds_back_a_firing_for_good(user, india):
    alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 200, "cooldownMinutes": 120},
                india)
    run(user, india)
    t1 = datetime(2026, 10, 5, 20, 0)
    bar(india, "2026-10-05", 205)
    assert len(run(user, india, t1).fired) == 1
    bar(india, "2026-10-06", 190)
    run(user, india, t1 + timedelta(minutes=30))
    bar(india, "2026-10-07", 210)
    held = run(user, india, t1 + timedelta(minutes=60))
    assert held.fired == [] and held.suppressed == 1
    assert run(user, india, t1 + timedelta(minutes=180)).fired == []  # never fires late for the held-back edge
    bar(india, "2026-10-08", 190)
    bar(india, "2026-10-09", 220)
    assert len(run(user, india, t1 + timedelta(minutes=200)).fired) == 1


def test_expired_and_disabled_alerts_are_not_evaluated(user, india):
    expired = alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 200,
                                 "expiresOn": "2026-10-01"}, india)
    alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 200, "enabled": False},
                india)
    out = run(user, india)
    assert out.evaluated == 0 and out.skipped == 2
    assert alerts.get(user, expired["id"])["status"]["expired"]
    bar(india, "2026-10-05", 205)
    assert run(user, india, T0 + timedelta(days=3)).fired == []


def test_switching_back_on_starts_from_a_new_baseline(user, india):
    a = alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 200}, india)
    run(user, india)
    alerts.save(user, {"id": a["id"], "enabled": False})
    bar(india, "2026-10-05", 205)
    run(user, india, T0 + timedelta(days=3))
    alerts.save(user, {"id": a["id"], "enabled": True})
    assert alerts.get(user, a["id"])["status"] is None
    assert run(user, india, T0 + timedelta(days=3, hours=1)).fired == []  # a baseline, not a change


def test_no_double_fire_even_if_the_state_were_lost(user, india):
    a = alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 200}, india)
    run(user, india)
    before = user.execute("SELECT state FROM alerts WHERE id=?", (a["id"],)).fetchone()[0]
    bar(india, "2026-10-05", 205)
    assert len(run(user, india, T0 + timedelta(days=3)).fired) == 1
    with user:
        user.execute("UPDATE alerts SET state=? WHERE id=?", (before, a["id"]))  # as if the state never saved
    assert run(user, india, T0 + timedelta(days=3, hours=1)).fired == []
    assert len(alerts.inbox(user)["items"]) == 1


def test_one_broken_alert_does_not_stop_the_rest(user, india):
    w = watchlists.save(user, {"name": "Gone"})
    alerts.save(user, {"kind": "filing", "watchlistId": w["id"]}, india)
    watchlists.delete(user, w["id"])
    alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 200}, india)
    out = run(user, india)
    assert out.evaluated == 1 and out.errors == ["New filings: watchlist “Gone”: Its watchlist was deleted."]


def test_validation(user, india):
    for body, message in (({"kind": "nope"}, "kind"), ({"kind": "price", "symbol": "GROWCO", "op": "above"}, "level"),
                          ({"kind": "price", "symbol": "NOSUCH", "op": "above", "level": 1}, "India database"),
                          ({"kind": "price", "symbol": "GROWCO", "op": "move", "pct": -1}, "above 0"),
                          ({"kind": "filing", "symbol": "GROWCO", "kinds": ["gossip"]}, "Filing kinds"),
                          ({"kind": "price", "symbol": "GROWCO", "op": "above", "level": 1, "cooldownMinutes": -1},
                           "cooldown"),
                          ({"kind": "price", "symbol": "GROWCO", "op": "above", "level": 1, "expiresOn": "soon"},
                           "expiry")):
        with pytest.raises(AlertError, match=message):
            alerts.save(user, body, india)


def test_the_inbox_marks_read_and_clears(user, india):
    alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 200}, india)
    run(user, india)
    bar(india, "2026-10-05", 205)
    run(user, india, T0 + timedelta(days=3))
    assert alerts.unread(user) == 1
    [event] = alerts.inbox(user, unread_only=True)["items"]
    assert alerts.mark_read(user, [event["id"]]) == 1 and alerts.unread(user) == 0
    assert alerts.mark_read(user, [event["id"]], read=False) == 1 and alerts.unread(user) == 1
    alerts.mark_read(user)
    assert alerts.delete_events(user) == 1 and alerts.inbox(user)["total"] == 0


# --- Delivery --------------------------------------------------------------------------------

def configure(monkeypatch, names=SECRETS):
    for name, value in SECRETS.items():
        if name in names:
            monkeypatch.setenv(delivery.PREFIX + name, value)


def fire_one(user, india) -> alerts.Evaluation:
    alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 200}, india)
    run(user, india)
    bar(india, "2026-10-05", 205)
    return run(user, india, T0 + timedelta(days=3))


def test_delivery_failures_are_recorded_and_never_raised(user, india, monkeypatch, caplog):
    configure(monkeypatch, ("WEBHOOK_URL", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"))

    def unreachable(url, data, content_type):
        raise urllib.error.URLError(f"cannot reach {url}")
    monkeypatch.setattr(delivery, "_post", unreachable)
    with caplog.at_level(logging.WARNING):
        out = fire_one(user, india)
    assert len(out.fired) == 1
    [event] = alerts.inbox(user)["items"]
    assert set(event["delivery"]) == {"telegram", "webhook"}
    assert not event["delivery"]["webhook"]["ok"] and "cannot reach" in event["delivery"]["webhook"]["error"]
    text = json.dumps(event) + json.dumps(out.deliveries) + caplog.text
    for secret in SECRETS.values():
        assert secret not in text
    assert "SECRET" not in text


def test_deliveries_go_through_every_configured_channel(user, india, monkeypatch):
    configure(monkeypatch)
    posts, mails = [], []
    monkeypatch.setattr(delivery, "_post", lambda url, data, kind: posts.append((url, data, kind)))

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo(self):
            pass

        def has_extn(self, name):
            return True

        def starttls(self, context):
            pass

        def login(self, user, password):
            assert password == SECRETS["SMTP_PASSWORD"]

        def send_message(self, msg):
            mails.append(msg)
    monkeypatch.setattr(delivery.smtplib, "SMTP", FakeSMTP)
    fire_one(user, india)
    [event] = alerts.inbox(user)["items"]
    assert {k: v["ok"] for k, v in event["delivery"].items()} == {"telegram": True, "webhook": True, "email": True}
    webhook = json.loads(next(d for u, d, k in posts if u == SECRETS["WEBHOOK_URL"]))
    assert webhook["title"] == event["title"] and webhook["text"].startswith("🔔")
    assert mails[0]["To"] == "me@example.com" and "above" in mails[0]["Subject"]


def test_channel_status_never_shows_a_value(monkeypatch):
    configure(monkeypatch)
    status = json.dumps(delivery.status())
    assert all(secret not in status for secret in SECRETS.values())
    assert json.loads(status)["telegram"]["configured"] is True

    def refused(url, data, content_type):
        raise urllib.error.URLError(f"refused {url}")  # an error that quotes the URL, token and all
    monkeypatch.setattr(delivery, "_post", refused)
    result = delivery.send_test("telegram")
    assert not result["ok"] and SECRETS["TELEGRAM_TOKEN"] not in result["error"] and "bot***" in result["error"]


def test_channels_are_off_by_default():
    assert not any(c["configured"] for c in delivery.status().values())
    assert delivery.deliver({"title": "x"}) == {}


# --- The poller --------------------------------------------------------------------------------

def test_the_poller_is_off_by_default_and_never_faster_than_five_minutes():
    assert alerts.poll_minutes() == 0 and alerts.PricePoller.from_config() is None
    config_module._config["alert_poll_minutes"] = 2
    assert alerts.poll_minutes() == 5 and alerts.PricePoller.from_config().minutes == 5
    config_module._config["alert_poll_minutes"] = 15
    assert alerts.PricePoller.from_config().minutes == 15


@pytest.mark.parametrize(("when", "open_"), [
    (datetime(2026, 10, 10, 10, 0, tzinfo=IST), False),  # a Saturday
    (datetime(2026, 10, 9, 9, 14, tzinfo=IST), False),
    (datetime(2026, 10, 9, 9, 15, tzinfo=IST), True),
    (datetime(2026, 10, 9, 15, 30, tzinfo=IST), True),
    (datetime(2026, 10, 9, 15, 31, tzinfo=IST), False),
    (datetime(2026, 10, 9, 4, 0, tzinfo=timezone.utc), True),  # 04:00 UTC is 09:30 in India
])
def test_market_hours(when, open_):
    assert alerts.market_open(when) is open_


def test_the_poller_does_nothing_outside_market_hours(tmp_path):
    poller = alerts.PricePoller(5, fetch=lambda symbols: pytest.fail("fetched quotes while NSE was closed"),
                                clock=lambda: datetime(2026, 10, 9, 18, 0, tzinfo=IST), user_path=tmp_path / "u.db")
    assert poller.run_once() is None and poller.last["message"] == "NSE is closed"


def test_the_poller_fires_price_alerts_on_delayed_quotes_once_a_day(user, india, tmp_path):
    alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 200}, india)
    run(user, india)  # the evening baseline on the 2 October close
    fetched = []

    def fetch(symbols):
        fetched.append(symbols)
        return {"GROWCO.NS": {"price": 204.5, "time": "2026-10-05T11:00:00", "source": "Yahoo delayed"}}
    poller = alerts.PricePoller(5, fetch=fetch, clock=lambda: datetime(2026, 10, 5, 11, 0, tzinfo=IST),
                                user_path=tmp_path / "user.db")
    out = poller.run_once()
    assert fetched == [["GROWCO.NS"]] and len(out.fired) == 1
    [event] = alerts.inbox(user)["items"]
    assert event["title"] == "GROWCO.NS trades at ₹204.50, above ₹200.00" and event["detail"]["source"] == "Yahoo delayed"
    assert poller.run_once().fired == []  # the next poll the same day
    bar(india, "2026-10-05", 206)  # the evening's bhavcopy agrees
    assert run(user, india, datetime(2026, 10, 5, 20, 0)).fired == []
    assert date.fromisoformat(event["data_date"]) == date(2026, 10, 5)
