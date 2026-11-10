"""The hourly job of the intraday account. Its dependencies come in as arguments so
tests can fake them; the signaler is T2's ``trader.intraday.signal.Signaler``."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime

from trader.intraday import report
from trader.intraday.paper import HOUR_MS, IntradayPaper, utc_date
from trader.intraday.types import SignalResult
from trader.jobs import error_text
from trader.ledger import Ledger, locked
from trader.notify import Notifier
from trader.okx import DAY_MS
from trader.settings import Coin, Settings

logger = logging.getLogger(__name__)

ALERT_INTERVAL_MS = 6 * HOUR_MS  # a failing run or an outage alerts at most this often
SIGNAL_RETRIES = 2  # more tries within the hour after a signal failed for a transient reason
SIGNAL_RETRY_WAIT_SECONDS = 60
OUTAGE_HOURS = 2  # consecutive hours with every coin failed before the alert
# What a transient failure's error text names: the provider overloaded (Anthropic's 529)
# or rate limiting, a connection or timeout, or a server-side error.
TRANSIENT = re.compile(
    r"Overloaded|RateLimit|Connection|Timeout|Timed out|ServiceUnavailable|InternalServer"
    r"|Error code: (429|5\d\d)",
    re.IGNORECASE,
)


def run(
    settings: Settings,
    paper: IntradayPaper,
    notifier: Notifier,
    signaler,
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Replay the account, decide this hour's signals, trade, and report.

    ``signaler`` answers ``run(coin, now_ms, position=...) -> SignalResult`` and
    ``fingerprint() -> dict``. The alerts of the opening replay (stops, a kill) and
    of the fingerprint check go out first. An hour is decided once (meta
    ``decided_hour``): a rerun within it only replays. A signal that failed for a
    transient reason (TRANSIENT) is asked again within the hour, SIGNAL_RETRIES times
    at most; a coin still without a signal keeps its position. An hour in which every
    coin failed counts toward meta ``outage_hours``; from OUTAGE_HOURS of them an
    alert goes out, and another when signals come back. While halted no signal is
    requested, to save its cost. A message goes out for an hour that had fills, and
    the summary of the UTC day before goes out on the first run of each day (meta
    ``summarized_day``). A failure alerts at most every ALERT_INTERVAL_MS (meta
    ``intraday_alerted_at``, shared with the outage alert), then raises so the
    scheduler records it.
    """
    try:
        _run(settings, paper, notifier, signaler, now_fn, sleep)
    except Exception as exc:
        now_ms = _ms(now_fn())
        if now_ms - paper.ledger.get("intraday_alerted_at", 0) >= ALERT_INTERVAL_MS:
            notifier.send(f"intraday 运行失败：{error_text(exc)}")
            paper.ledger.set("intraday_alerted_at", now_ms)
        raise


def _run(
    settings: Settings,
    paper: IntradayPaper,
    notifier: Notifier,
    signaler,
    now_fn: Callable[[], datetime],
    sleep: Callable[[float], None],
) -> None:
    ledger = paper.ledger
    now_ms = _ms(now_fn())
    hour = now_ms - now_ms % HOUR_MS
    with locked(settings.intraday_lock_path):
        alerts = paper.replay(now_ms)
    alerts += check_fingerprint(ledger, fingerprint(signaler, paper.watchlist), now_ms)
    for text in alerts:
        notifier.send(text)

    if ledger.get("decided_hour") != hour and not ledger.get("halted"):
        # The signals are requested unlocked: the calls take a while and touch no account state.
        results = _decide(signaler, paper.watchlist, ledger, now_fn, sleep)
        signals = {coin: result.signal for coin, result in results.items()}
        with locked(settings.intraday_lock_path):
            now_ms = _ms(now_fn())
            alerts = paper.replay(now_ms)
            alerts += paper.execute(signals, now_ms)
            ledger.set("decided_hour", hour)
        alerts += _outage(ledger, results, now_ms)
        for text in alerts:
            notifier.send(text)
        fills = ledger.fills(hour)
        if fills:
            notifier.send(report.hourly(paper, hour, signals, fills))

    today = utc_date(now_ms)
    if ledger.get("summarized_day") != today:
        notifier.send(report.daily(paper, utc_date(now_ms - DAY_MS), now_ms))
        ledger.set("summarized_day", today)


def fingerprint(signaler, watchlist: tuple[Coin, ...]) -> dict:
    """What the signals under validation run on: the signaler's fingerprint (model,
    prompt) and the coins signalled."""
    return {**signaler.fingerprint(), "watchlist": sorted(coin.research for coin in watchlist)}


def check_fingerprint(ledger: Ledger, current: dict, now_ms: int) -> list[str]:
    """Record ``current`` and, when it differs from the stored one, restart the
    validation period and return the alert. Any change restarts it: the signal's
    fingerprint (model, prompt, watchlist) has no code-only part, unlike the daily
    research."""
    stored = ledger.get("fingerprint")
    ledger.set("fingerprint", current)
    if stored is not None and "watchlist" in current and "watchlist" not in stored:
        # Recorded before the watchlist was part of the fingerprint: the first run
        # that names it only records it (the pool is taken as unchanged).
        stored = {**stored, "watchlist": current["watchlist"]}
    if stored is None or stored == current:
        return []
    ledger.set("validation_start", None)
    ledger.set("baseline_ref", None)
    text = f"日内信号的模型、提示词或自选池变了，验证期从下一次执行起重新计时：{stored} → {current}"
    ledger.add_event(now_ms, "validation_restart", text)
    return [text]


def _decide(
    signaler, watchlist: tuple[Coin, ...], ledger: Ledger,
    now_fn: Callable[[], datetime], sleep: Callable[[float], None],
) -> dict[str, SignalResult]:
    """Each coin's signal for the hour, by research ticker, every attempt recorded. A
    coin whose call failed for a transient reason is asked again after
    SIGNAL_RETRY_WAIT_SECONDS, SIGNAL_RETRIES times at most; its last answer counts."""
    positions = ledger.positions()
    results: dict[str, SignalResult] = {}
    pending = list(watchlist)
    for attempt in range(1 + SIGNAL_RETRIES):
        if attempt:
            sleep(SIGNAL_RETRY_WAIT_SECONDS)
        for coin in pending:
            ts = _ms(now_fn())
            result = _signal(signaler, coin, ts, positions.get(coin.swap))
            ledger.record_signal(ts, coin.research, result)
            results[coin.research] = result
        pending = [coin for coin in pending if transient(results[coin.research].error)]
        if not pending:
            break
    return results


def transient(error: str | None) -> bool:
    """Whether a signal's error text names a failure worth another try within the hour."""
    return error is not None and TRANSIENT.search(error) is not None


def _outage(ledger: Ledger, results: dict[str, SignalResult], now_ms: int) -> list[str]:
    """Count the hours in a row in which every coin's signal failed (meta
    ``outage_hours``): alert at OUTAGE_HOURS, throttled like a failing run, and say
    so once signals come back. Both go into the events too."""
    errors = [result.error for result in results.values()]
    if errors and all(errors):
        hours = ledger.get("outage_hours", 0) + 1
        ledger.set("outage_hours", hours)
        if hours < OUTAGE_HOURS:
            return []
        if now_ms - ledger.get("intraday_alerted_at", 0) < ALERT_INTERVAL_MS:
            return []
        ledger.set("intraday_alerted_at", now_ms)
        text = (
            f"日内信号已连续 {hours} 个整点全部失败，持仓维持不动，只有止损和熔断托底。"
            f"最近一次：{errors[-1][:200]}"
        )
        ledger.add_event(now_ms, "signal_outage", text)
        return [text]
    hours = ledger.get("outage_hours", 0)
    if hours:
        ledger.set("outage_hours", 0)
    if hours < OUTAGE_HOURS:
        return []
    text = f"日内信号已恢复，此前连续 {hours} 个整点全部失败。"
    ledger.add_event(now_ms, "signal_recovered", text)
    return [text]


def _signal(signaler, coin: Coin, now_ms: int, position) -> SignalResult:
    """The signaler's answer; a failed result should it raise after all (it promises not to)."""
    try:
        return signaler.run(coin, now_ms, position=position)
    except Exception as exc:
        logger.exception("signal for %s failed", coin.research)
        return SignalResult(None, None, "", error_text(exc))


def _ms(now: datetime) -> int:
    return int(now.timestamp() * 1000)
