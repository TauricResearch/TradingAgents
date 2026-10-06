"""Alerts: say when a stock, a screen or a filing changes.

Five kinds, each a condition over data the app already has:

    price         a stock's close crosses above or below a level, or moves more
                  than X% in a day (NSE bhavcopy closes, adjusted for splits and
                  bonuses; during the session, Yahoo's delayed quote when the
                  optional poller is on)
    metric        a condition in the screener's query language on one stock,
                  ``Price to Earning < 20 AND Promoter holding > 50``, on the live
                  metrics snapshot; it fires when the condition turns true
    screen        stocks entering or leaving a saved screen (or a preset), from
                  one live snapshot to the next
    filing        new documents for a stock or a watchlist's stocks: results,
                  shareholding patterns, corporate actions, credit ratings and
                  other announcements, as the India database records them
    shareholding  promoter holding moving more than X points from one quarterly
                  pattern to the next, or the pledged share rising by more than X

Edge-triggered. A condition alert fires when its condition goes from false to
true between two evaluations of different data, never again while it stays
true. The first evaluation after an alert is created, edited or re-enabled only
records where things stand; a condition that cannot be evaluated (missing data)
never fires, and its next known value starts afresh. Screen alerts fire on a
change of membership; filing and shareholding alerts on documents and patterns
that were not there before.

Idempotent. Each alert remembers the data it last saw (``state``): a trading
day, or the live snapshot's build time. Evaluating the same data again compares
it with what came before it, so it finds the same change, and the change's own
key (``alert_events.dedupe``, unique per alert) stops it being recorded twice.
A firing held back by the cooldown is remembered as handled, so it does not
fire later either.

Each firing goes to the in-app inbox (``alert_events``) with what tripped it and
the date of the data, then to whichever delivery channels the environment
configures (``delivery``). A failed delivery is noted on the inbox item; it never
stops the evaluation. Evaluation runs after ``tradingagents india sync-all``
(after the snapshot rebuild), as ``tradingagents india evaluate-alerts``, from
the Alerts page, and, for price alerts only, from ``PricePoller`` during market
hours when ``TRADINGAGENTS_ALERT_POLL_MINUTES`` is set.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.vendors.india import store
from tradingagents.screener import delivery, engine, screens, snapshot, userdb, watchlists

log = logging.getLogger(__name__)

KINDS = ("price", "metric", "screen", "filing", "shareholding")
PRICE_OPS = ("above", "below", "move")
DIRECTIONS = ("up", "down", "either")
SCREEN_CHANGES = ("enter", "leave", "both")
MEASURES = ("promoter", "pledge")
FILING_KINDS = {  # alert option -> documents.kind values (corporate actions have their own table)
    "results": ("results",),
    "shareholding": ("shareholding",),
    "corporate_action": (),
    "credit_rating": ("credit_rating",),
    "other": ("announcement", "board_meeting", "annual_report", "concall", "investor_presentation"),
}
FILING_LABELS = {"results": "results", "shareholding": "shareholding pattern", "corporate_action": "corporate action",
                 "credit_rating": "credit rating", "announcement": "announcement", "board_meeting": "board meeting",
                 "annual_report": "annual report", "concall": "concall", "investor_presentation": "investor presentation"}
MAX_ALERTS = 500
MAX_COOLDOWN_MINUTES = 30 * 24 * 60
CATCH_UP_BARS = 10  # trading days a price alert reads back over after a gap in evaluations
FILING_WINDOW_DAYS = 10  # a document dated this far back can still arrive late and fire
SCAN_LIMIT = 5000  # a screen alert reads this many matches at most
MAX_LISTED = 25  # stocks or filings one inbox item lists
MAX_HANDLED = 200  # firings (or held-back firings) an alert remembers
IST = timezone(timedelta(hours=5, minutes=30))
MARKET_HOURS = ((9, 15), (15, 30))
MIN_POLL_MINUTES = 5


class AlertError(ValueError):
    """An alert that cannot be saved or evaluated as it stands; ``errors`` carries a
    query's positional errors."""

    def __init__(self, message: str, errors: list[dict] | None = None):
        super().__init__(message)
        self.errors = errors or []


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _iso(when: datetime) -> str:
    return when.replace(microsecond=0).isoformat()


def _load(text, default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def _digest(*parts) -> str:
    return hashlib.sha1("\x1f".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _rs(value) -> str:
    return "—" if value is None else f"₹{value:,.2f}"


def _number(value, label: str, *, positive: bool = True) -> float:
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        raise AlertError(f"{label} must be a number.") from None
    if not math.isfinite(number) or (positive and number <= 0):
        raise AlertError(f"{label} must be a number above 0.")
    return number


def _short(number: float) -> str:
    return f"{number:,.2f}".rstrip("0").rstrip(".")


# --- Saving -------------------------------------------------------------------------------

def _row(conn, alert_id):
    try:
        alert_id = int(alert_id)
    except (TypeError, ValueError):
        raise AlertError("No such alert.") from None
    row = conn.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
    if row is None:
        raise AlertError("No such alert.")
    return row


def find_screen(conn, ref) -> dict | None:
    """A saved screen by id, or a preset by ``preset:<slug>``."""
    ref = str(ref or "")
    if ref.startswith("preset:"):
        return screens.get_preset(ref)
    return screens.get_screen(conn, int(ref)) if ref.isdigit() else None


def _stock(body: dict, india_conn) -> tuple[str, str]:
    symbol = str(body.get("symbol") or "").strip()
    if not symbol:
        raise AlertError("Choose the stock to watch.")
    found, rejected = watchlists.resolve([symbol], india_conn)
    if not found:
        reason = rejected[0]["reason"] if rejected else "not in the India database"
        raise AlertError(f"{symbol}: {reason}.")
    security = found[0][1]
    return security["isin"], watchlists.display_symbol(security)


def _definition(conn, body: dict, india_conn) -> dict:
    """The validated columns of an alert from the page's ``body``."""
    kind = body.get("kind")
    if kind not in KINDS:
        raise AlertError(f"An alert's kind is one of {', '.join(KINDS)}.")
    out: dict = {"kind": kind, "isin": None, "symbol": None, "watchlist_id": None}
    params: dict = {}
    target = ""
    if kind == "screen":
        screen = find_screen(conn, body.get("screen"))
        if screen is None:
            raise AlertError("Choose a saved screen (save the screen first).")
        on = body.get("on") or "both"
        if on not in SCREEN_CHANGES:
            raise AlertError("Say whether to tell you when stocks enter, leave, or both.")
        params = {"screen": str(screen["id"]), "on": on}
        verb = {"enter": "entering", "leave": "leaving", "both": "entering or leaving"}[on]
        target = f"Stocks {verb} “{screen['name']}”"
    elif kind in ("filing", "shareholding") and body.get("watchlistId") not in (None, ""):
        try:
            w = watchlists.get(conn, body["watchlistId"])
        except watchlists.WatchlistError as exc:
            raise AlertError(str(exc)) from None
        out["watchlist_id"] = w["id"]
        target = f"watchlist “{w['name']}”"
    else:
        out["isin"], out["symbol"] = _stock(body, india_conn)
        target = out["symbol"]
    if kind == "price":
        op = body.get("op")
        if op not in PRICE_OPS:
            raise AlertError("A price alert is above a level, below a level, or a daily move.")
        params = {"op": op}
        if op == "move":
            params["pct"] = _number(body.get("pct"), "The daily move (%)")
            params["direction"] = body.get("direction") or "either"
            if params["direction"] not in DIRECTIONS:
                raise AlertError("A move is up, down or either.")
            way = {"up": "rises", "down": "falls", "either": "moves"}[params["direction"]]
            name = f"{target} {way} {_short(params['pct'])}% or more in a day"
        else:
            params["level"] = _number(body.get("level"), "The price level")
            name = f"{target} {op} {_rs(params['level'])}"
    elif kind == "metric":
        query = str(body.get("query") or "").strip()
        checked = engine.validate(query, conn)
        if not checked["ok"]:
            raise AlertError(checked["errors"][0]["message"], checked["errors"])
        params = {"query": query}
        name = f"{target}: {' AND '.join(line.strip() for line in query.splitlines() if line.strip())}"[:120]
    elif kind == "filing":
        kinds = body.get("kinds") or list(FILING_KINDS)
        if not isinstance(kinds, list) or not kinds or any(k not in FILING_KINDS for k in kinds):
            raise AlertError(f"Filing kinds are among {', '.join(FILING_KINDS)}.")
        params = {"kinds": [k for k in FILING_KINDS if k in kinds]}
        name = f"New filings: {target}"
    elif kind == "shareholding":
        measure = body.get("measure") or "promoter"
        if measure not in MEASURES:
            raise AlertError("Watch promoter holding or the pledged share.")
        params = {"measure": measure, "points": _number(body.get("points"), "The change (percentage points)")}
        if measure == "promoter":
            params["direction"] = body.get("direction") or "either"
            if params["direction"] not in DIRECTIONS:
                raise AlertError("A change is up, down or either.")
            way = {"up": "up", "down": "down", "either": "±"}[params["direction"]]
            name = f"{target}: promoter holding {way} {_short(params['points'])} pts"
        else:
            name = f"{target}: pledged share up {_short(params['points'])} pts"
    else:  # screen
        name = target
    out["params"] = params
    out["name"] = " ".join(str(body.get("name") or "").split())[:120] or name
    try:
        cooldown = int(body.get("cooldownMinutes") or 0)
    except (TypeError, ValueError):
        raise AlertError("The cooldown is a number of minutes.") from None
    if not 0 <= cooldown <= MAX_COOLDOWN_MINUTES:
        raise AlertError("The cooldown is between 0 minutes and 30 days.")
    out["cooldown_minutes"] = cooldown
    expires = body.get("expiresOn") or None
    if expires is not None:
        try:
            expires = date.fromisoformat(str(expires)).isoformat()
        except ValueError:
            raise AlertError("The expiry is a date, YYYY-MM-DD.") from None
    out["expires_on"] = expires
    return out


def save(conn, body: dict, india_conn=None) -> dict:
    """Create an alert, or update the one ``body['id']`` names. A body of only
    ``id`` and ``enabled`` switches it on or off. A changed definition, and a
    switch back on, starts it afresh: its next evaluation is a new baseline."""
    now = _iso(_now())
    if body.get("id") not in (None, ""):
        old = _row(conn, body["id"])
        if set(body) <= {"id", "enabled"}:
            enabled = 1 if body.get("enabled") else 0
            with conn:
                conn.execute("UPDATE alerts SET enabled=?, updated_at=?"
                             + (", state=NULL, status=NULL" if enabled and not old["enabled"] else "")
                             + " WHERE id=?", (enabled, now, old["id"]))
            return get(conn, old["id"])
        d = _definition(conn, body, india_conn)
        enabled = 1 if body.get("enabled", True) else 0
        with conn:
            conn.execute("UPDATE alerts SET kind=?, name=?, isin=?, symbol=?, watchlist_id=?, params=?, enabled=?, "
                         "cooldown_minutes=?, expires_on=?, state=NULL, status=NULL, updated_at=? WHERE id=?",
                         (d["kind"], d["name"], d["isin"], d["symbol"], d["watchlist_id"], json.dumps(d["params"]),
                          enabled, d["cooldown_minutes"], d["expires_on"], now, old["id"]))
        return get(conn, old["id"])
    if conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] >= MAX_ALERTS:
        raise AlertError(f"At most {MAX_ALERTS} alerts.")
    d = _definition(conn, body, india_conn)
    with conn:
        cur = conn.execute("INSERT INTO alerts (kind, name, isin, symbol, watchlist_id, params, enabled, "
                           "cooldown_minutes, expires_on, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           (d["kind"], d["name"], d["isin"], d["symbol"], d["watchlist_id"], json.dumps(d["params"]),
                            1 if body.get("enabled", True) else 0, d["cooldown_minutes"], d["expires_on"], now, now))
    return get(conn, cur.lastrowid)


def delete(conn, alert_id) -> None:
    row = _row(conn, alert_id)
    with conn:
        conn.execute("DELETE FROM alerts WHERE id=?", (row["id"],))


def describe(row, fired: int = 0) -> dict:
    return {"id": row["id"], "kind": row["kind"], "name": row["name"], "symbol": row["symbol"], "isin": row["isin"],
            "watchlistId": row["watchlist_id"], "params": _load(row["params"], {}), "enabled": bool(row["enabled"]),
            "cooldownMinutes": row["cooldown_minutes"], "expiresOn": row["expires_on"],
            "status": _load(row["status"], None), "lastEvaluatedAt": row["last_evaluated_at"],
            "lastFiredAt": row["last_fired_at"], "createdAt": row["created_at"], "updatedAt": row["updated_at"],
            "fired": fired}


def list_alerts(conn) -> list[dict]:
    fired = dict(conn.execute("SELECT alert_id, COUNT(*) FROM alert_events WHERE alert_id IS NOT NULL "
                              "GROUP BY alert_id"))
    return [describe(r, fired.get(r["id"], 0)) for r in conn.execute("SELECT * FROM alerts ORDER BY id DESC")]


def get(conn, alert_id) -> dict:
    row = _row(conn, alert_id)
    fired = conn.execute("SELECT COUNT(*) FROM alert_events WHERE alert_id=?", (row["id"],)).fetchone()[0]
    return describe(row, fired)


# --- Evaluating ---------------------------------------------------------------------------

@dataclass
class Event:
    dedupe: str
    title: str
    body: str = ""
    detail: dict = field(default_factory=dict)
    data_date: str | None = None
    symbol: str | None = None


@dataclass
class Outcome:
    state: dict | None  # None keeps the state as it was
    status: dict
    events: list[Event] = field(default_factory=list)


@dataclass
class Context:
    user: object
    india: object
    now: datetime
    quotes: dict | None = None  # symbol -> delayed quote, when the poller evaluates


@dataclass
class Evaluation:
    evaluated: int = 0
    fired: list[int] = field(default_factory=list)  # inbox item ids
    suppressed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    deliveries: dict = field(default_factory=dict)  # inbox item id -> channel -> result


def step(state: dict | None, epoch: str, value) -> tuple[bool, object, dict] | None:
    """Record an observation of ``value`` at ``epoch`` (a trading day or a snapshot's
    build time, which sort in time order). Returns whether there was an earlier
    observation, the value it saw, and the new state; None for data older than
    already seen. Observing the same epoch again compares with the one before it,
    so a re-run finds the same change."""
    state = dict(state or {})
    seen = state.get("epoch")
    if seen is not None and epoch < seen:
        return None
    if seen == epoch:
        prev_epoch, prev = state.get("prev_epoch"), state.get("prev_value")
    else:
        prev_epoch, prev = seen, state.get("value")
    state.update(epoch=epoch, value=value, prev_epoch=prev_epoch, prev_value=prev)
    return prev_epoch is not None, prev, state


def rose(had_before: bool, prev, value) -> bool:
    """The edge: a known false before, true now."""
    return had_before and prev is False and value is True


def _price_truth(params: dict, price, prev_close) -> tuple[bool | None, float | None]:
    change = (price / prev_close - 1) * 100 if price is not None and prev_close else None
    op = params["op"]
    if price is None:
        return None, change
    if op == "above":
        return price >= params["level"], change
    if op == "below":
        return price <= params["level"], change
    if change is None:
        return None, None
    way = params.get("direction", "either")
    hit = change >= params["pct"] if way == "up" else change <= -params["pct"] if way == "down" \
        else abs(change) >= params["pct"]
    return hit, change


def _price(alert, params: dict, state: dict | None, ctx: Context) -> Outcome:
    symbol, isin = alert["symbol"], alert["isin"]
    today = ctx.now.astimezone(IST).date() if ctx.quotes is not None else ctx.now.date()
    bars = store.get_prices(isin, start=(today - timedelta(days=60)).isoformat(), conn=ctx.india)
    observations = []  # (day, price, previous close, source)
    if ctx.quotes is not None:
        quote = ctx.quotes.get(symbol)
        before = [b for b in bars if b["date"] < today.isoformat()]
        if quote is None or not before:
            return Outcome(None, {"ok": True, "message": "No delayed quote this time."})
        observations.append((today.isoformat(), quote["price"], before[-1]["close"], quote.get("source")))
    else:
        if len(bars) < 2:
            return Outcome(None, {"ok": False, "message": "No recent prices in the India database for this stock."})
        pairs = list(zip(bars[:-1], bars[1:], strict=True))[-CATCH_UP_BARS:]
        seen = (state or {}).get("epoch")
        pairs = [p for p in pairs if seen is None or p[1]["date"] >= seen]
        if seen is None:
            pairs = pairs[-1:]  # the first evaluation is a baseline at the latest close
        observations = [(b["date"], b["close"], a["close"], "NSE bhavcopy close") for a, b in pairs]
    events, value, last = [], None, None
    for day, price, prev_close, source in observations:
        value, change = _price_truth(params, price, prev_close)
        stepped = step(state, day, value)
        if stepped is None:
            continue
        had, prev, state = stepped
        last = (day, price, prev_close, change, source)
        if not rose(had, prev, value):
            continue
        intraday = ctx.quotes is not None
        verb = "trades at" if intraday else "closed at"
        if params["op"] == "move":
            title = f"{symbol} {'rose' if change > 0 else 'fell'} {abs(change):.2f}% ({_rs(prev_close)} to {_rs(price)})"
        else:
            title = f"{symbol} {verb} {_rs(price)}, {params['op']} {_rs(params['level'])}"
        events.append(Event(f"{params['op']}:{day}", title,
                            f"{'Delayed quote' if intraday else 'Close'} on {day}; previous close {_rs(prev_close)}.",
                            {"price": price, "previousClose": prev_close, "changePct": change,
                             "level": params.get("level"), "movePct": params.get("pct"), "source": source,
                             "date": day}, day, symbol))
    if last is None:
        return Outcome(None, {"ok": True, "message": "No new prices since the last evaluation."})
    day, price, prev_close, change, source = last
    status = {"ok": True, "value": value, "dataDate": day, "price": price, "changePct": change, "source": source}
    return Outcome(state, status, events)


def _snapshot_epoch(result: dict) -> tuple[str, str]:
    snap = result["snapshot"]
    return snap.get("built_at") or snap["data_date"], snap["data_date"]


def _metric(alert, params: dict, state: dict | None, ctx: Context) -> Outcome:
    isin, symbol, query = alert["isin"], alert["symbol"], params["query"]
    result = engine.run(query, isins=[isin], page_size=1, user_conn=ctx.user, india_conn=ctx.india)
    epoch, day = _snapshot_epoch(result)
    current = engine.run("", isins=[isin], columns=result["used"], show_used=False, page_size=1,
                         user_conn=ctx.user, india_conn=ctx.india)
    names = {c["id"]: c["name"] for c in current["columns"]}
    values = {names[k]: v for k, v in (current["rows"][0]["values"] if current["rows"] else {}).items()
              if k in result["used"]}
    if not current["rows"]:
        value, note = None, f"{symbol} is not in the live snapshot."
    elif result["total"]:
        value, note = True, "true"
    elif result["excluded"]:
        value, note = None, "unknown: a value the condition needs is missing"
    else:
        value, note = False, "false"
    stepped = step(state, epoch, value)
    if stepped is None:
        return Outcome(None, {"ok": True, "message": "The snapshot is older than the one last evaluated."})
    had, prev, new_state = stepped
    events = []
    if rose(had, prev, value):
        shown = ", ".join(f"{k} {_short(v) if isinstance(v, (int, float)) else v}" for k, v in values.items())
        events.append(Event(f"true:{epoch}", f"{symbol}: your condition is now true", f"{query}\nNow: {shown}.",
                            {"query": query, "values": values}, day, symbol))
    return Outcome(new_state, {"ok": True, "value": value, "message": note, "values": values, "dataDate": day},
                   events)


def _names(india, isins) -> dict[str, dict]:
    isins = list(isins)
    out = {}
    for i in range(0, len(isins), 500):
        chunk = isins[i:i + 500]
        for r in india.execute(f"SELECT isin, nse_symbol, bse_code, name FROM securities WHERE isin IN "
                               f"({', '.join('?' * len(chunk))})", chunk):
            out[r["isin"]] = {"symbol": watchlists.display_symbol(dict(r)), "name": r["name"]}
    return out


def _screen(alert, params: dict, state: dict | None, ctx: Context) -> Outcome:
    screen = find_screen(ctx.user, params["screen"])
    if screen is None:
        raise AlertError("Its saved screen was deleted.")
    result = engine.run(screen["query"], page_size=SCAN_LIMIT, max_page_size=SCAN_LIMIT,
                        user_conn=ctx.user, india_conn=ctx.india)
    epoch, day = _snapshot_epoch(result)
    members = sorted(r["isin"] for r in result["rows"])
    stepped = step(state, epoch, members)
    if stepped is None:
        return Outcome(None, {"ok": True, "message": "The snapshot is older than the one last evaluated."})
    had, prev, new_state = stepped
    events = []
    if had and prev is not None:
        on = params.get("on", "both")
        entered = sorted(set(members) - set(prev)) if on in ("enter", "both") else []
        left = sorted(set(prev) - set(members)) if on in ("leave", "both") else []
        if entered or left:
            names = _names(ctx.india, [*entered, *left])

            def listing(isins):
                return [names.get(i, {"symbol": i, "name": None}) for i in isins]

            parts = []
            if entered:
                parts.append(f"{len(entered)} entered")
            if left:
                parts.append(f"{len(left)} left")
            body = []
            for label, isins in (("Entered", entered), ("Left", left)):
                if isins:
                    shown = ", ".join(n["symbol"] for n in listing(isins[:MAX_LISTED]))
                    more = f" and {len(isins) - MAX_LISTED} more" if len(isins) > MAX_LISTED else ""
                    body.append(f"{label}: {shown}{more}.")
            events.append(Event(f"screen:{epoch}", f"“{screen['name']}”: {' and '.join(parts)}", "\n".join(body),
                                {"screen": params["screen"], "screenName": screen["name"],
                                 "entered": listing(entered[:200]), "left": listing(left[:200]),
                                 "members": len(members)}, day))
    return Outcome(new_state, {"ok": True, "value": len(members), "message": f"{len(members)} stocks match",
                               "dataDate": day}, events)


def _stocks(alert, ctx: Context) -> list[tuple[str, str]]:
    if alert["watchlist_id"]:
        try:
            w = watchlists.get(ctx.user, alert["watchlist_id"])
        except watchlists.WatchlistError:
            raise AlertError("Its watchlist was deleted.") from None
        return [(i["isin"], i["symbol"]) for i in w["items"]]
    return [(alert["isin"], alert["symbol"])]


def _filing(alert, params: dict, state: dict | None, ctx: Context) -> Outcome:
    stocks = dict(_stocks(alert, ctx))
    today = ctx.now.date()
    since = (state or {}).get("since") or (today - timedelta(days=FILING_WINDOW_DAYS)).isoformat()
    items = []  # (date, key, payload)
    isins = list(stocks)
    for i in range(0, len(isins), 400):
        chunk = isins[i:i + 400]
        marks = ", ".join("?" * len(chunk))
        kinds = [k for option in params["kinds"] for k in FILING_KINDS[option]]
        if kinds:
            for r in ctx.india.execute(
                    f"SELECT isin, date, kind, title, url FROM documents WHERE isin IN ({marks}) "
                    f"AND kind IN ({', '.join('?' * len(kinds))}) AND date >= ?", [*chunk, *kinds, since]):
                items.append((r["date"], _digest("doc", r["isin"], r["date"], r["kind"], r["title"]),
                              {"symbol": stocks[r["isin"]], "date": r["date"], "kind": r["kind"],
                               "label": FILING_LABELS.get(r["kind"], r["kind"]), "title": r["title"], "url": r["url"]}))
        if "corporate_action" in params["kinds"]:
            for r in ctx.india.execute(
                    f"SELECT isin, COALESCE(first_seen, ex_date) AS seen, ex_date, type, details "
                    f"FROM corporate_actions WHERE isin IN ({marks}) AND COALESCE(first_seen, ex_date) >= ?",
                    [*chunk, since]):
                items.append((r["seen"], _digest("ca", r["isin"], r["ex_date"], r["type"], r["details"]),
                              {"symbol": stocks[r["isin"]], "date": r["seen"], "kind": "corporate_action",
                               "label": f"corporate action ({r['type']})",
                               "title": f"{r['details']} (ex-date {r['ex_date']})", "url": None}))
    handled = set((state or {}).get("seen") or [])
    fresh = sorted((p for d, k, p in items if k not in handled), key=lambda p: (p["date"], p["symbol"]))
    newest = max((d for d, _, _ in items), default=since)
    window = (date.fromisoformat(newest) - timedelta(days=FILING_WINDOW_DAYS)).isoformat()
    next_since = max(since, min(window, today.isoformat()))
    new_state = {"since": next_since, "seen": sorted(k for d, k, _ in items if d >= next_since)}
    events = []
    if state is not None and fresh:
        keys = sorted(k for d, k, p in items if k not in handled)
        target = stocks[alert["isin"]] if alert["isin"] else f"your watchlist ({len(stocks)} stocks)"
        title = (f"{fresh[0]['symbol']}: new {fresh[0]['label']}" if len(fresh) == 1
                 else f"{len(fresh)} new filings for {target}")
        body = "\n".join(f"{p['symbol']} · {p['date']} · {p['label']}: {p['title']}" for p in fresh[:MAX_LISTED])
        if len(fresh) > MAX_LISTED:
            body += f"\n… and {len(fresh) - MAX_LISTED} more."
        events.append(Event(f"filings:{_digest(*keys)}", title, body, {"items": fresh[:200]},
                            max(p["date"] for p in fresh), fresh[0]["symbol"] if len(stocks) == 1 else None))
    status = {"ok": True, "message": f"Watching {len(stocks)} stock{'s' * (len(stocks) != 1)}"
                                     + ("" if state is not None else "; the baseline is set"),
              "dataDate": newest if items else None}
    return Outcome(new_state, status, events)


def _pledged(pattern: dict):
    return pattern["pledged_pct"] if pattern.get("pledged_pct") is not None else pattern.get("encumbered_pct")


def _shareholding(alert, params: dict, state: dict | None, ctx: Context) -> Outcome:
    stocks = _stocks(alert, ctx)
    quarters = dict((state or {}).get("quarters") or {})
    first = state is None
    tripped, newest = [], None
    for isin, symbol in stocks:
        patterns = store.get_shareholding(isin, conn=ctx.india)
        if not patterns:
            continue
        latest = patterns[-1]
        newest = max(newest or latest["quarter_end"], latest["quarter_end"])
        seen = quarters.get(isin)
        quarters[isin] = latest["quarter_end"]
        if first or seen is None or latest["quarter_end"] <= seen or len(patterns) < 2:
            continue
        before = patterns[-2]
        if params["measure"] == "promoter":
            now_v, then_v = latest.get("promoter_pct"), before.get("promoter_pct")
        else:
            now_v, then_v = _pledged(latest), _pledged(before)
        if now_v is None or then_v is None:
            continue
        change = now_v - then_v
        way = params.get("direction", "up" if params["measure"] == "pledge" else "either")
        points = params["points"]
        hit = change >= points if way == "up" else change <= -points if way == "down" else abs(change) >= points
        if hit:
            tripped.append({"symbol": symbol, "isin": isin, "quarter": latest["quarter_end"],
                            "previousQuarter": before["quarter_end"], "before": then_v, "now": now_v,
                            "change": change, "filedAt": latest.get("filed_at")})
    events = []
    if tripped:
        what = "Promoter holding" if params["measure"] == "promoter" else "Pledged share of promoter holding"
        lines = [f"{t['symbol']}: {what.lower()} {t['before']:.2f}% → {t['now']:.2f}% "
                 f"({t['change']:+.2f} pts, quarter to {t['quarter']})" for t in tripped[:MAX_LISTED]]
        title = (f"{tripped[0]['symbol']}: {what.lower()} {tripped[0]['change']:+.2f} pts" if len(tripped) == 1
                 else f"{what} changed at {len(tripped)} companies")
        events.append(Event(f"shp:{_digest(*sorted(t['isin'] + '@' + t['quarter'] for t in tripped))}", title,
                            "\n".join(lines), {"changes": tripped, "measure": params["measure"]},
                            max(t["quarter"] for t in tripped), tripped[0]["symbol"] if len(tripped) == 1 else None))
    status = {"ok": True, "message": f"Watching {len(stocks)} stock{'s' * (len(stocks) != 1)}"
                                     + ("; the baseline is set" if first else ""), "dataDate": newest}
    return Outcome({"quarters": quarters}, status, events)


EVALUATORS = {"price": _price, "metric": _metric, "screen": _screen, "filing": _filing, "shareholding": _shareholding}


def _record(conn, row, outcome: Outcome, now: datetime) -> tuple[list[int], int]:
    """Store an alert's outcome: its firings (minus duplicates and those the cooldown
    holds back), its state and its status, in one transaction."""
    old_state = _load(row["state"], None)
    state = outcome.state if outcome.state is not None else old_state
    handled = list((old_state or {}).get("handled") or [])
    fired, suppressed = [], 0
    last_fired = row["last_fired_at"]
    cooldown = timedelta(minutes=row["cooldown_minutes"] or 0)
    with conn:
        for e in outcome.events:
            if e.dedupe in handled or conn.execute("SELECT 1 FROM alert_events WHERE alert_id=? AND dedupe=?",
                                                   (row["id"], e.dedupe)).fetchone():
                continue
            handled.append(e.dedupe)
            if cooldown and last_fired and now - datetime.fromisoformat(last_fired) < cooldown:
                suppressed += 1
                continue
            cur = conn.execute("INSERT OR IGNORE INTO alert_events (alert_id, alert_name, kind, dedupe, fired_at, "
                               "data_date, title, body, detail, symbol) VALUES (?,?,?,?,?,?,?,?,?,?)",
                               (row["id"], row["name"], row["kind"], e.dedupe, _iso(now), e.data_date, e.title,
                                e.body, json.dumps(e.detail, default=str), e.symbol))
            if cur.rowcount:
                fired.append(cur.lastrowid)
                last_fired = _iso(now)
        if state is not None:
            state = {**state, "handled": handled[-MAX_HANDLED:]}
        status = {**outcome.status, "at": _iso(now), "fired": len(fired), "suppressed": suppressed}
        conn.execute("UPDATE alerts SET state=?, status=?, last_evaluated_at=?, last_fired_at=? WHERE id=?",
                     (json.dumps(state, default=str) if state is not None else None, json.dumps(status, default=str),
                      _iso(now), last_fired, row["id"]))
    return fired, suppressed


def _set_status(conn, row, status: dict, now: datetime) -> None:
    with conn:
        conn.execute("UPDATE alerts SET status=?, last_evaluated_at=? WHERE id=?",
                     (json.dumps({**status, "at": _iso(now)}), _iso(now), row["id"]))


def evaluate(user_conn, india_conn=None, *, now: datetime | None = None, kinds=None, quotes: dict | None = None,
             deliver: bool = True, alert_ids=None) -> Evaluation:
    """Evaluate every enabled, unexpired alert (of ``kinds``, or those ``alert_ids``
    names) on the data as it is now; record and deliver what fires."""
    now = (now or _now()).replace(microsecond=0)
    out = Evaluation()
    own = india_conn is None
    if own:
        india_conn = store.open_existing()
    try:
        rows = user_conn.execute("SELECT * FROM alerts ORDER BY id").fetchall()
        ctx = Context(user_conn, india_conn, now, quotes)
        for row in rows:
            if (kinds and row["kind"] not in kinds) or (alert_ids is not None and row["id"] not in alert_ids):
                continue
            if not row["enabled"]:
                out.skipped += 1
                continue
            if row["expires_on"] and now.date().isoformat() > row["expires_on"]:
                _set_status(user_conn, row, {"ok": True, "expired": True,
                                             "message": f"Expired on {row['expires_on']}; not evaluated."}, now)
                out.skipped += 1
                continue
            if india_conn is None:
                _set_status(user_conn, row, {"ok": False, "message": "There is no India database yet: "
                                                                     "python -m cli.main india sync-all"}, now)
                out.errors.append(f"{row['name']}: no India database")
                continue
            try:
                outcome = EVALUATORS[row["kind"]](row, _load(row["params"], {}), _load(row["state"], None), ctx)
            except Exception as exc:  # noqa: BLE001 — one broken alert must not stop the rest
                message = str(exc) if isinstance(exc, (AlertError, snapshot.SnapshotError, engine.ScreenerUnavailable,
                                                       ValueError)) else f"{type(exc).__name__}: {exc}"
                _set_status(user_conn, row, {"ok": False, "message": message}, now)
                out.errors.append(f"{row['name']}: {message}")
                continue
            fired, suppressed = _record(user_conn, row, outcome, now)
            out.evaluated += 1
            out.fired += fired
            out.suppressed += suppressed
    finally:
        if own and india_conn is not None:
            india_conn.close()
    if deliver:
        for event_id in out.fired:
            out.deliveries[event_id] = deliver_event(user_conn, event_id)
    return out


def deliver_event(conn, event_id: int) -> dict:
    """Send one inbox item through the configured channels and note how each went."""
    event = _event(conn.execute("SELECT * FROM alert_events WHERE id=?", (event_id,)).fetchone())
    try:
        results = delivery.deliver(event)
    except Exception as exc:  # noqa: BLE001 — delivery never breaks evaluation
        results = {"error": {"ok": False, "error": delivery.scrub(f"{type(exc).__name__}: {exc}")}}
    if results:
        with conn:
            conn.execute("UPDATE alert_events SET delivery=? WHERE id=?", (json.dumps(results), event_id))
    return results


# --- The inbox ------------------------------------------------------------------------------

def _event(row) -> dict:
    return {"id": row["id"], "alert_id": row["alert_id"], "alert_name": row["alert_name"], "kind": row["kind"],
            "fired_at": row["fired_at"], "data_date": row["data_date"], "title": row["title"], "body": row["body"],
            "detail": _load(row["detail"], {}), "symbol": row["symbol"], "read_at": row["read_at"],
            "delivery": _load(row["delivery"], {})}


def unread(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM alert_events WHERE read_at IS NULL").fetchone()[0]


def inbox(conn, *, unread_only: bool = False, alert_id=None, limit: int = 200) -> dict:
    where, args = [], []
    if unread_only:
        where.append("read_at IS NULL")
    if alert_id not in (None, ""):
        where.append("alert_id = ?")
        args.append(int(alert_id))
    sql = "SELECT * FROM alert_events" + (f" WHERE {' AND '.join(where)}" if where else "")
    rows = conn.execute(sql + " ORDER BY fired_at DESC, id DESC LIMIT ?", [*args, max(1, min(int(limit), 1000))])
    total = conn.execute("SELECT COUNT(*) FROM alert_events").fetchone()[0]
    return {"items": [_event(r) for r in rows], "unread": unread(conn), "total": total}


def _ids(ids) -> list[int] | None:
    if ids in (None, "all"):
        return None
    if not isinstance(ids, list):
        raise AlertError("Send the inbox items' ids as a list, or 'all'.")
    try:
        return [int(i) for i in ids]
    except (TypeError, ValueError):
        raise AlertError("Inbox item ids are numbers.") from None


def mark_read(conn, ids=None, read: bool = True) -> int:
    """Mark inbox items (all when ``ids`` is None) read, or unread again."""
    ids = _ids(ids)
    stamp = _iso(_now()) if read else None
    with conn:
        if ids is None:
            cur = conn.execute("UPDATE alert_events SET read_at=? WHERE read_at IS " + ("NULL" if read else "NOT NULL"),
                               (stamp,))
        else:
            cur = conn.executemany("UPDATE alert_events SET read_at=? WHERE id=?", [(stamp, i) for i in ids])
    return cur.rowcount


def delete_events(conn, ids=None) -> int:
    """Delete inbox items; with no ids, every item already read."""
    ids = _ids(ids)
    with conn:
        if ids is None:
            cur = conn.execute("DELETE FROM alert_events WHERE read_at IS NOT NULL")
        else:
            cur = conn.executemany("DELETE FROM alert_events WHERE id=?", [(i,) for i in ids])
    return cur.rowcount


# --- The intraday price poller ------------------------------------------------------------

def market_open(now: datetime | None = None) -> bool:
    """Whether NSE's normal session is on: 09:15 to 15:30 India time, Monday to
    Friday (exchange holidays are not known here; a quote that does not move then
    fires nothing)."""
    ist = (now or datetime.now(timezone.utc)).astimezone(IST)
    if ist.weekday() >= 5:
        return False
    (h0, m0), (h1, m1) = MARKET_HOURS
    minutes = ist.hour * 60 + ist.minute
    return h0 * 60 + m0 <= minutes <= h1 * 60 + m1


def poll_minutes() -> int:
    """The poller's interval: 0 (off, the default) unless TRADINGAGENTS_ALERT_POLL_MINUTES
    is set, and never under ``MIN_POLL_MINUTES``."""
    try:
        minutes = int(get_config().get("alert_poll_minutes") or 0)
    except (TypeError, ValueError):
        return 0
    return 0 if minutes <= 0 else max(MIN_POLL_MINUTES, minutes)


def _yahoo_quotes(symbols: list[str]) -> dict:
    from tradingagents.dataflows.vendors.yahoo.quotes import delayed_quotes

    return delayed_quotes(symbols)


class PricePoller:
    """Evaluates price alerts on Yahoo's delayed quotes every few minutes while NSE
    is open. Off unless TRADINGAGENTS_ALERT_POLL_MINUTES is set; quotes lag the
    exchange by about 15 minutes, and only price alerts read them."""

    def __init__(self, minutes: int, *, fetch=None, clock=None, user_path=None):
        self.minutes = max(MIN_POLL_MINUTES, int(minutes))
        self.fetch = fetch or _yahoo_quotes
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.user_path = user_path
        self.last: dict | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @classmethod
    def from_config(cls) -> PricePoller | None:
        minutes = poll_minutes()
        return cls(minutes) if minutes else None

    def run_once(self) -> Evaluation | None:
        now = self.clock()
        if not market_open(now):
            self.last = {"at": _iso(now.astimezone(IST)), "ran": False, "message": "NSE is closed"}
            return None
        user = userdb.connect(self.user_path)
        try:
            symbols = [r[0] for r in user.execute("SELECT DISTINCT symbol FROM alerts WHERE kind='price' AND "
                                                  "enabled=1 AND symbol IS NOT NULL")]
            if not symbols:
                self.last = {"at": _iso(now.astimezone(IST)), "ran": False, "message": "No price alerts"}
                return None
            quotes = self.fetch(symbols)
            local = now.astimezone().replace(tzinfo=None)
            result = evaluate(user, now=local, kinds={"price"}, quotes=quotes)
        finally:
            user.close()
        self.last = {"at": _iso(now.astimezone(IST)), "ran": True, "quotes": len(quotes),
                     "fired": len(result.fired), "errors": result.errors[:5]}
        return result

    def _loop(self) -> None:
        while not self._stop.wait(self.minutes * 60):
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001 — a failed poll waits for the next
                log.warning("Alert price poll failed: %s", delivery.scrub(str(exc)))
                self.last = {"at": _iso(self.clock().astimezone(IST)), "ran": False, "message": "failed"}

    def start(self) -> PricePoller:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="alert-price-poller", daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict:
        return {"enabled": True, "minutes": self.minutes, "marketOpen": market_open(self.clock()), "last": self.last,
                "note": "Yahoo Finance delayed quotes, about 15 minutes behind NSE; price alerts only."}
