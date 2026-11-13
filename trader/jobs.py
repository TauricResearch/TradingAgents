"""The daily and hourly jobs. Their dependencies come in as arguments so tests can fake them."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import tradingagents
from trader import report, rules
from trader.ledger import BUDGET_ERROR, Ledger, locked
from trader.notify import Notifier
from trader.paper import Paper
from trader.research import Researcher, build_config
from trader.settings import BUDGET_LEARNING_DAYS, MAX_ATTEMPTS, RETRY_WAIT_SECONDS, Coin, Settings

logger = logging.getLogger(__name__)

MARK_ALERT_INTERVAL_MS = 6 * 3600 * 1000


def daily(
    settings: Settings,
    paper: Paper,
    notifier: Notifier,
    researcher_factory: Callable[[], Researcher],
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Research every coin for the trade date, trade the account, send the report.

    The alerts of the opening replay (stops, a kill) and of the checks go out before
    the research, which can take hours and may fail. Safe to rerun for the same
    trade date: researched coins are skipped, a trade date executes once, and the
    report goes out once per state of the day.
    """
    ledger = paper.ledger
    trade_date = trade_date_for(now_fn())
    with locked(settings.lock_path):
        alerts = paper.replay(_ms(now_fn()))
    alerts += check_fingerprint(
        ledger, fingerprint(build_config(settings), paper.watchlist), _ms(now_fn())
    )
    alerts += _check_prices(settings, ledger, trade_date)
    for text in alerts:
        notifier.send(text)

    # Research runs unlocked, in rounds: each round tries every coin still
    # pending once, and a failed coin waits RETRY_WAIT_SECONDS for the next.
    researcher = None
    for round_no in range(MAX_ATTEMPTS):
        pending = [
            c for c in paper.watchlist if coin_state(ledger, trade_date, c.research)[0] == "pending"
        ]
        if not pending:
            break
        if round_no:
            sleep(RETRY_WAIT_SECONDS)
        for coin in pending:
            ts = _ms(now_fn())
            cap = budget_cap(ledger, trade_date)
            if cap is not None and ledger.cost_since(month_start_ms(now_fn()))[0] >= cap:
                ledger.record_attempt(trade_date, coin.research, ts, rating=None, error=BUDGET_ERROR)
                continue
            try:
                researcher = researcher or researcher_factory()
            except Exception as exc:
                logger.exception("could not build the researcher")
                ledger.record_attempt(
                    trade_date, coin.research, ts, rating=None, error=error_text(exc)
                )
                continue
            result = researcher.run(coin.research, trade_date)
            ledger.record_attempt(
                trade_date, coin.research, ts, rating=result.rating, error=result.error,
                tokens_in=result.tokens_in, tokens_out=result.tokens_out, cost_usd=result.cost_usd,
            )

    states = {c.research: coin_state(ledger, trade_date, c.research) for c in paper.watchlist}
    alerts = _count_failures(ledger, trade_date, states)
    ratings = {coin: detail if state == "done" else None for coin, (state, detail) in states.items()}
    with locked(settings.lock_path):
        now_ms = _ms(now_fn())
        alerts += paper.replay(now_ms)
        alerts += paper.execute(trade_date, ratings, now_ms)
    for text in alerts:
        notifier.send(text)
    # Report again only when the day changed state: a halt lifted before the
    # catch-up run lets it execute after the first report went out.
    key = [trade_date, ledger.executed(trade_date)]
    if ledger.get("reported") != key:
        cap = budget_cap(ledger, trade_date)
        notifier.send(report.daily(paper, trade_date, states, now_ms, month_start_ms(now_fn()), cap))
        ledger.set("reported", key)


def mark(
    settings: Settings,
    paper: Paper,
    notifier: Notifier,
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    """Replay the closed minutes and send their alerts. A failure alerts at most
    every six hours, then raises so the scheduler records it."""
    try:
        with locked(settings.lock_path):
            alerts = paper.replay(_ms(now_fn()))
    except Exception as exc:
        now_ms = _ms(now_fn())
        if now_ms - paper.ledger.get("mark_alerted_at", 0) >= MARK_ALERT_INTERVAL_MS:
            notifier.send(f"mark 运行失败：{error_text(exc)}")
            paper.ledger.set("mark_alerted_at", now_ms)
        raise
    for text in alerts:
        notifier.send(text)


def coin_state(ledger: Ledger, trade_date: str, coin: str) -> tuple[str, str | None]:
    """("done", rating), ("failed", last error) or ("pending", None).

    A coin is done once an attempt gave a rating (REVIEW included), and failed
    after MAX_ATTEMPTS errors or once the monthly budget blocked it.
    """
    attempts = ledger.attempts(trade_date, coin)
    for rating, _ in attempts:
        if rating is not None:
            return "done", rating
    if len(attempts) >= MAX_ATTEMPTS or any(e == BUDGET_ERROR for _, e in attempts):
        return "failed", attempts[-1][1]
    return "pending", None


def budget_cap(ledger: Ledger, trade_date: str) -> float | None:
    """The monthly LLM cap. Set once, from the first BUDGET_LEARNING_DAYS trade
    dates before ``trade_date`` whose cost is fully known; None until then."""
    cap = ledger.get("budget_cap")
    if cap is None:
        known = [cost for _, cost in ledger.daily_costs(trade_date) if cost is not None]
        if len(known) >= BUDGET_LEARNING_DAYS:
            cap = rules.monthly_cap(known[:BUDGET_LEARNING_DAYS])
            ledger.set("budget_cap", cap)
    return cap


def fingerprint(config: dict, watchlist: tuple[Coin, ...]) -> dict:
    """What the research under validation runs on: library version, models, code,
    and the coins researched."""
    return {
        "version": tradingagents.__version__,
        "deep": config["deep_think_llm"],
        "quick": config["quick_think_llm"],
        "code": code_digest(Path(tradingagents.__file__).parent),
        "watchlist": sorted(coin.research for coin in watchlist),
    }


def code_digest(root: Path) -> str:
    """A digest of the Python files under root, their paths and contents."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def check_fingerprint(ledger: Ledger, current: dict, now_ms: int) -> list[str]:
    """Record ``current`` and return an alert when it differs from the stored one.

    A new model, minor version or watchlist restarts the validation period; a code
    change within the version (a bug fix) is recorded and the period continues.
    """
    stored = ledger.get("fingerprint")
    ledger.set("fingerprint", current)
    if stored is not None and "watchlist" in current and "watchlist" not in stored:
        # Recorded before the watchlist was part of the fingerprint: the first run
        # that names it only records it (the pool is taken as unchanged).
        stored = {**stored, "watchlist": current["watchlist"]}
    if stored is None or stored == current:
        return []

    def series(fp: dict) -> tuple:
        minor = ".".join(fp["version"].split(".")[:2])
        return fp["deep"], fp["quick"], minor, fp.get("watchlist")

    if series(stored) != series(current):
        ledger.set("validation_start", None)
        ledger.set("baseline_ref", None)
        text = f"研判的模型、版本或自选池变了，验证期从下一次执行起重新计时：{stored} → {current}"
        ledger.add_event(now_ms, "validation_restart", text)
    else:
        text = f"tradingagents 代码变了（{stored['code']} → {current['code']}），验证期不重新计时"
        ledger.add_event(now_ms, "code_change", text)
    return [text]


def trade_date_for(now: datetime) -> str:
    """The trade date of a run at ``now``: the UTC day before it (ADR 0002)."""
    return (now.astimezone(UTC).date() - timedelta(days=1)).isoformat()


def month_start_ms(now: datetime) -> int:
    first = now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return _ms(first)


def error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]


def _count_failures(
    ledger: Ledger, trade_date: str, states: dict[str, tuple[str, str | None]]
) -> list[str]:
    """Count consecutive trade dates with a failed coin; alert from the second."""
    if ledger.get("failures_counted") == trade_date:
        return []
    failed = [coin for coin, (state, _) in states.items() if state != "done"]
    streak = ledger.get("failure_streak", 0) + 1 if failed else 0
    ledger.set("failure_streak", streak)
    ledger.set("failures_counted", trade_date)
    if streak >= 2:
        return [f"研判已连续 {streak} 天有币失败，这次是 {'、'.join(failed)}。"]
    return []


def _check_prices(settings: Settings, ledger: Ledger, trade_date: str) -> list[str]:
    """Alert, once per trade date, while a model price is unset: every run's cost is
    then unknown, so no budget cap gets set and the performance deducts nothing."""
    if settings.price_deep is not None and settings.price_quick is not None:
        return []
    if ledger.get("prices_alerted") == trade_date:
        return []
    ledger.set("prices_alerted", trade_date)
    return [
        "TRADER_PRICE_DEEP / TRADER_PRICE_QUICK 没有配置，LLM 费用按未知计："
        "月度预算上限定不下来，绩效也扣不到费用。"
    ]


def _ms(now: datetime) -> int:
    return int(now.timestamp() * 1000)
