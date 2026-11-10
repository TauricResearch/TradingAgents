"""The hourly job of the demo account (ADR 0008).

Every run: set the exchange up once, sync, keep the stops, send what that raised.
Then, unless halted, already decided this hour, or stopped by a problem the sync
found, wait for the intraday account to decide the hour, size its signals and
trade, sync again, re-hang the stops, and report the hour's fills. The daily
summary goes out on the first run of each UTC day. The intraday ledger is opened
read-only; this job never writes it.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from trader.demo import report
from trader.demo.account import DemoAccount
from trader.demo.settings import (
    ALERT_INTERVAL_MS,
    INTRADAY_POLL_SECONDS,
    INTRADAY_WAIT_MS,
    KILL_SETTLE_SECONDS,
)
from trader.intraday.paper import HOUR_MS, utc_date
from trader.jobs import error_text
from trader.ledger import Ledger, locked
from trader.notify import Notifier
from trader.okx import DAY_MS
from trader.settings import Settings

logger = logging.getLogger(__name__)


def run(
    settings: Settings,
    account: DemoAccount,
    notifier: Notifier,
    intraday: Ledger,
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """One hourly run; a failure alerts at most every ALERT_INTERVAL_MS (meta
    ``demo_alerted_at``) and is raised so the scheduler records it."""
    try:
        _run(settings, account, notifier, intraday, now_fn, sleep)
    except Exception as exc:
        now_ms = _ms(now_fn())
        if now_ms - account.ledger.get("demo_alerted_at", 0) >= ALERT_INTERVAL_MS:
            notifier.send(f"demo 运行失败：{error_text(exc)}")
            account.ledger.set("demo_alerted_at", now_ms)
        raise


def _run(
    settings: Settings,
    account: DemoAccount,
    notifier: Notifier,
    intraday: Ledger,
    now_fn: Callable[[], datetime],
    sleep: Callable[[float], None],
) -> None:
    ledger = account.ledger
    now_ms = _ms(now_fn())
    hour = now_ms - now_ms % HOUR_MS
    with locked(settings.demo_lock_path):
        if not ledger.get("setup_done"):
            for note in account.setup():
                ledger.add_event(now_ms, "setup", note)
            ledger.set("setup_done", True)
        result = account.sync(now_ms)
        alerts = list(result.alerts)
        if result.killed:
            # The close orders fill in a moment; book them before anything else.
            sleep(KILL_SETTLE_SECONDS)
            result = account.sync(_ms(now_fn()))
            alerts += result.alerts
        quotes = account.quotes(hour, result.positions)
        alerts += account.manage_stops(now_ms, quotes, result.stops)
    for text in alerts:
        notifier.send(text)
    for text in _standing(ledger, result.problems, now_ms):
        notifier.send(text)

    if not ledger.get("halted") and ledger.get("decided_hour") != hour and not result.problems:
        signals = _signals_for(intraday, hour, account, now_fn, sleep)
        if signals is None:
            ledger.add_event(
                now_ms, "skipped",
                f"日内账户到 {_clock(_ms(now_fn()))} 还没决定 {_clock(hour)} 这个小时，demo 本小时不交易",
            )
        else:
            with locked(settings.demo_lock_path):
                now_ms = _ms(now_fn())
                result = account.sync(now_ms)  # the equity and positions the orders size against
                if result.problems:
                    trade_alerts = []
                else:
                    trade_alerts, desired = account.execute(hour, signals, now_ms, result.equity, quotes)
                    result = account.sync(_ms(now_fn()), desired_stops=desired)
                    trade_alerts += account.manage_stops(_ms(now_fn()), quotes, result.stops)
                    ledger.set("decided_hour", hour)
            for text in trade_alerts + result.alerts:
                notifier.send(text)
            for text in _standing(ledger, result.problems, now_ms):
                notifier.send(text)
            fills = [f for f in ledger.fills(hour) if f.reason == "trade"]
            if fills:
                notifier.send(report.hourly(account, hour, signals, fills))

    today = utc_date(now_ms)
    if ledger.get("summarized_day") != today:
        notifier.send(report.daily(account, utc_date(now_ms - DAY_MS), now_ms))
        ledger.set("summarized_day", today)


def _signals_for(
    intraday: Ledger, hour: int, account: DemoAccount,
    now_fn: Callable[[], datetime], sleep: Callable[[float], None],
) -> dict[str, str | None] | None:
    """The intraday account's signals for ``hour`` once it has decided it (meta
    ``decided_hour``), waiting up to INTRADAY_WAIT_MS; None when it has not. A halted
    intraday account is flat, so the demo follows with Flat for every coin."""
    if intraday.get("halted"):
        account.ledger.add_event(_ms(now_fn()), "follow_halt", "日内账户熔断中，demo 跟随平仓")
        return {coin.research: "Flat" for coin in account.watchlist}
    started = _ms(now_fn())
    while intraday.get("decided_hour") != hour:
        if _ms(now_fn()) - started >= INTRADAY_WAIT_MS:
            return None
        sleep(INTRADAY_POLL_SECONDS)
    return hour_signals(intraday, hour)


def hour_signals(intraday: Ledger, hour: int) -> dict[str, str | None]:
    """Each coin's last signal recorded since ``hour``, by research ticker; the last
    attempt of the hour counts, as in the intraday job."""
    out: dict[str, str | None] = {}
    for _ts, coin, signal, *_ in intraday.signals(since_ms=hour):  # newest first
        out.setdefault(coin, signal)
    return out


def _standing(ledger: Ledger, problems: list[str], now_ms: int) -> list[str]:
    """Alert each problem at most every ALERT_INTERVAL_MS (meta ``problem_alerts``,
    text -> when); every problem goes into the events."""
    sent = ledger.get("problem_alerts") or {}
    out = []
    for text in problems:
        ledger.add_event(now_ms, "problem", text)
        if now_ms - sent.get(text, 0) >= ALERT_INTERVAL_MS:
            sent[text] = now_ms
            out.append(f"demo 对账：{text}")
    if problems:
        ledger.set("problem_alerts", {t: ts for t, ts in sent.items() if now_ms - ts < ALERT_INTERVAL_MS})
    return out


def _clock(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%H:%M")


def _ms(now: datetime) -> int:
    return int(now.timestamp() * 1000)
