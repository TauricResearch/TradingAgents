"""The hourly job of the intraday account. Its dependencies come in as arguments so
tests can fake them; the signaler is T2's ``trader.intraday.signal.Signaler``."""

from __future__ import annotations

import logging
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

ALERT_INTERVAL_MS = 6 * HOUR_MS  # a failing run alerts at most this often


def run(
    settings: Settings,
    paper: IntradayPaper,
    notifier: Notifier,
    signaler,
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    """Replay the account, decide this hour's signals, trade, and report.

    ``signaler`` answers ``run(coin, now_ms, position=...) -> SignalResult`` and
    ``fingerprint() -> dict``. The alerts of the opening replay (stops, a kill) and
    of the fingerprint check go out first. An hour is decided once (meta
    ``decided_hour``): a rerun within it only replays. While halted no signal is
    requested, to save its cost. A message goes out for an hour that had fills, and
    the summary of the UTC day before goes out on the first run of each day (meta
    ``summarized_day``). A failure alerts at most every ALERT_INTERVAL_MS (meta
    ``intraday_alerted_at``), then raises so the scheduler records it.
    """
    try:
        _run(settings, paper, notifier, signaler, now_fn)
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
) -> None:
    ledger = paper.ledger
    now_ms = _ms(now_fn())
    hour = now_ms - now_ms % HOUR_MS
    with locked(settings.intraday_lock_path):
        alerts = paper.replay(now_ms)
    alerts += check_fingerprint(ledger, signaler.fingerprint(), now_ms)
    for text in alerts:
        notifier.send(text)

    if ledger.get("decided_hour") != hour and not ledger.get("halted"):
        # The signals are requested unlocked: the calls take a while and touch no account state.
        positions = ledger.positions()
        signals = {}
        for coin in paper.watchlist:
            ts = _ms(now_fn())
            result = _signal(signaler, coin, ts, positions.get(coin.swap))
            ledger.record_signal(ts, coin.research, result)
            signals[coin.research] = result.signal
        with locked(settings.intraday_lock_path):
            now_ms = _ms(now_fn())
            alerts = paper.replay(now_ms)
            alerts += paper.execute(signals, now_ms)
            ledger.set("decided_hour", hour)
        for text in alerts:
            notifier.send(text)
        fills = ledger.fills(hour)
        if fills:
            notifier.send(report.hourly(paper, hour, signals, fills))

    today = utc_date(now_ms)
    if ledger.get("summarized_day") != today:
        notifier.send(report.daily(paper, utc_date(now_ms - DAY_MS), now_ms))
        ledger.set("summarized_day", today)


def check_fingerprint(ledger: Ledger, current: dict, now_ms: int) -> list[str]:
    """Record ``current`` and, when it differs from the stored one, restart the
    validation period and return the alert. Any change restarts it: the signal's
    fingerprint (model, prompt) has no code-only part, unlike the daily research."""
    stored = ledger.get("fingerprint")
    ledger.set("fingerprint", current)
    if stored is None or stored == current:
        return []
    ledger.set("validation_start", None)
    ledger.set("baseline_ref", None)
    text = f"日内信号的模型或提示词变了，验证期从下一次执行起重新计时：{stored} → {current}"
    ledger.add_event(now_ms, "validation_restart", text)
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
