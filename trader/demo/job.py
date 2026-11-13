"""The hourly job of an account on the exchange: the demo (ADR 0008), the live account
(ADR 0010). What it sends is labeled with the account's name.

Every run: set the exchange up once, sync, keep the stops, send what that raised.
Then, unless halted, already decided this hour, or stopped by a problem the sync
found, wait for the intraday account to decide the hour, read the prices again, size
its signals and trade, sync again, hang the stops of what was traded, and report the
hour's fills. A contract whose quote is unusable sits the hour out.
A position closed at market, for want of a stop or by the kill switch, is booked by
one more sync; a kill tripped by the sync before the orders leaves the hour untraded.
``halt`` trips the kill switch by hand. When a step after the orders raises, the
positions they left still get their stops (or are closed) before the run fails, and
the alerts gathered so far go out either way. The daily summary goes out on the first
run of each UTC day. The intraday ledger is opened read-only; this job never writes
it. A paused account (``DemoAccount.paused``) is synced and its problems alerted, and
nothing is set up, no stop kept, no order sent: its hour is a shadow run (ADR 0010),
recording the orders it would have sent (``shadow_order``), or why there are none
(``shadow_none``), and reporting no fills. So is the hour of an account a sync of the run
pauses. An account whose profile is ``fingerprinted`` is paused when the code or the
Signal its orders follow changes (``check_fingerprint``), looked at before anything is
set up and again once the hour's signals are there. ``resume`` lifts a pause. A run's
messages go through the account's outbox (``outbox``): what an earlier run could not
send goes out first, and what this one cannot waits for the next. A failure is alerted
by its kind (``alert_failure``).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

from trader import rules
from trader.demo import report
from trader.demo.account import DemoAccount, Planned, Profile, Quotes, Sync
from trader.demo.settings import (
    ALERT_INTERVAL_MS,
    HALT_SYNCS,
    INTRADAY_POLL_SECONDS,
    INTRADAY_WAIT_MS,
    KILL_SETTLE_SECONDS,
)
from trader.intraday.paper import HOUR_MS, utc_date
from trader.jobs import code_digest, error_text
from trader.ledger import Ledger, locked
from trader.notify import Notifier, Outbox, labeled
from trader.okx import DAY_MS
from trader.settings import KILL_DRAWDOWN, Settings

logger = logging.getLogger(__name__)


def run(
    settings: Settings,
    account: DemoAccount,
    notifier: Notifier,
    intraday: Ledger,
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """One hourly run, its messages sent through the account's outbox (``outbox``); a
    failure is alerted (``alert_failure``) and raised so the scheduler records it."""
    box = outbox(notifier, account.ledger, account.profile, lambda: _ms(now_fn()))
    try:
        _run(settings, account, box, intraday, now_fn, sleep)
    except Exception as exc:
        alert_failure(account.ledger, box, account.profile, exc, f"运行失败：{error_text(exc)}", _ms(now_fn()))
        raise


def outbox(notifier: Notifier, ledger: Ledger, profile: Profile, now_ms: Callable[[], int]) -> Outbox:
    """The outbox of the account's messages (meta ``Profile.unsent_key``), labeled with
    its name, once it has sent what it kept: what an earlier run could not send goes out
    ahead of this one's, and a failure's alert among it starts its kind's interval."""
    box = Outbox(labeled(notifier, profile.name), ledger, profile.unsent_key, now_ms)
    kinds = box.flush()
    if kinds:
        alerted = ledger.get(profile.failures_key) or {}
        ledger.set(profile.failures_key, alerted | dict.fromkeys(kinds, now_ms()))
    return box


def alert_failure(
    ledger: Ledger, box: Outbox, profile: Profile, exc: BaseException, text: str, now_ms: int
) -> None:
    """Alert the failure ``exc`` of the account's run with ``text``: each kind of error
    (``failure_kind``) at most every ALERT_INTERVAL_MS (meta ``Profile.failures_key``,
    kind -> when its alert went out), a new kind at once, and every failure, saying so,
    while the account may hold a position (``_exposed``). An alert waiting in the outbox
    holds back the next of its kind, whose interval starts when that one goes out."""
    kind = failure_kind(exc)
    alerted = ledger.get(profile.failures_key) or {}
    due = now_ms - alerted.get(kind, 0) >= ALERT_INTERVAL_MS
    if box.holds(kind) or not (due or _exposed(ledger)):
        return
    if not due:
        text += "（账户可能有仓位：恢复之前每次失败都报）"
    if box.send(text, kind=kind):
        alerted[kind] = now_ms
        ledger.set(profile.failures_key, {k: ts for k, ts in alerted.items() if now_ms - ts < ALERT_INTERVAL_MS})


def failure_kind(exc: BaseException) -> str:
    """The kind of error ``exc`` is, as its alerts are throttled: its type, with the code
    the exchange or the HTTP response gave it."""
    code = getattr(exc, "code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    return f"{type(exc).__name__} {code}" if code else type(exc).__name__


def _exposed(ledger: Ledger) -> bool:
    """Whether the account may hold a position: the ledger has one, or an order of the
    hour of the last sync went unconfirmed (``order_pending``) and may have filled since."""
    synced = ledger.get("synced_at") or 0
    return bool(ledger.positions()) or bool(ledger.events(synced - synced % HOUR_MS, ("order_pending",)))


def _run(
    settings: Settings,
    account: DemoAccount,
    notifier: Outbox,
    intraday: Ledger,
    now_fn: Callable[[], datetime],
    sleep: Callable[[float], None],
) -> None:
    ledger = account.ledger
    lock = account.profile.lock_path(settings)
    now_ms = _ms(now_fn())
    hour = now_ms - now_ms % HOUR_MS
    alerts: list[str] = []
    with _sending(notifier, alerts), locked(lock):
        if account.profile.fingerprinted:
            alerts += map(account.profile.pause_alert, check_fingerprint(account, intraday, now_ms))
        if not account.paused and not ledger.get("setup_done"):
            for note in account.setup():
                ledger.add_event(now_ms, "setup", note)
            ledger.set("setup_done", True)
        result = account.sync(now_ms)
        alerts += result.alerts
        if result.killed:
            result = _settled(account, alerts, now_fn, sleep)
        quotes = account.quotes(hour, result.positions, now_ms, alerts)
        if not account.paused:  # the sync pauses the account for what it cannot explain
            _, closed = account.manage_stops(now_ms, quotes, result.stops, alerts=alerts)
            if closed:
                result = _settled(account, alerts, now_fn, sleep)
        paused = account.paused
    for text in _standing(ledger, result.problems, now_ms):
        notifier.send(text)

    blocked = ledger.get("halted") or result.problems
    if paused and blocked and ledger.get("decided_hour") != hour:
        _shadow_none(ledger, now_ms, hour, result)
    elif not blocked and ledger.get("decided_hour") != hour:
        signals = _signals_for(intraday, hour, account, now_fn, sleep)
        if signals is None:
            ledger.add_event(
                now_ms, "skipped",
                f"日内账户到 {_clock(_ms(now_fn()))} 还没决定 {_clock(hour)} 这个小时，{account.profile.name} 本小时不交易",
            )
        else:
            alerts = []
            with _sending(notifier, alerts), locked(lock):
                now_ms = _ms(now_fn())
                if account.profile.fingerprinted:
                    # The hour is decided: the intraday ledger holds the fingerprint of its Signal.
                    alerts += map(account.profile.pause_alert, check_fingerprint(account, intraday, now_ms))
                result = account.sync(now_ms)  # the equity and positions the orders size against
                alerts += result.alerts
                if result.killed:
                    result = _settled(account, alerts, now_fn, sleep)
                if paused or account.paused:  # paused at any point of the run: a shadow hour
                    _shadow(account, hour, signals, now_ms, result, quotes, alerts)
                elif not result.problems and not ledger.get("halted"):
                    result = _trade(account, hour, signals, now_ms, result.equity, quotes, alerts, now_fn, sleep)
                    ledger.set("decided_hour", hour)
            for text in _standing(ledger, result.problems, now_ms):
                notifier.send(text)
            fills = [f for f in ledger.fills(hour) if f.reason == "trade"]
            if fills:
                notifier.send(report.hourly(account, hour, signals, fills))

    today = utc_date(now_ms)
    if ledger.get("summarized_day") != today:
        notifier.send(report.daily(account, utc_date(now_ms - DAY_MS), now_ms))
        ledger.set("summarized_day", today)


def halt(
    settings: Settings,
    account: DemoAccount,
    notifier: Notifier,
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
) -> list[str]:
    """The kill switch by hand (``python -m trader <name> halt``): trip it, positions open
    or not and paused or not (ADR 0010), close what the exchange holds, book the closes
    (through up to HALT_SYNCS syncs while closes are still being sent), and send how
    many positions were closed and how many are left. Returns what the syncs alerted and
    that summary, for the terminal. When a sync raises, the switch stays tripped and the
    hourly runs go on closing; that is sent, and the error raised."""
    notifier = labeled(notifier, account.profile.name)
    ledger = account.ledger
    with locked(account.profile.lock_path(settings)):
        now_ms = _ms(now_fn())
        if not ledger.get("halted"):
            account.halt(now_ms, f"人工熔断：python -m trader {account.profile.name} halt")
        try:
            result = account.sync(now_ms)
            held, lines = list(result.positions), list(result.alerts)
            for _ in range(HALT_SYNCS):
                if not result.killed:
                    break
                result = _settled(account, lines, now_fn, sleep)
        except Exception as exc:
            notifier.send(f"人工熔断：已停止交易，但这次没能平仓（{error_text(exc)}）；每小时的运行会接着平。")
            raise
    left = list(result.positions)
    summary = f"人工熔断：停止交易，平掉 {len(held) - len(left)} 个仓位，还剩 {len(left)} 个"
    if left:
        summary += f"（{'、'.join(left)}），下一次运行接着平"
    summary += "。" + account.profile.after_kill
    notifier.send(summary)
    return [*lines, summary]


class Refused(Exception):
    """``resume`` left the pause standing, for the reason it says."""


def resume(
    settings: Settings,
    account: DemoAccount,
    intraday: Ledger,
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[list[dict], Sync]:
    """Lift the account's pause (``python -m trader <name> resume``) once a sync just now
    finds nothing that pauses it; return the reasons lifted and what that sync found.

    The sync, and the fingerprint of a fingerprinted account, recorded anew (the resume
    is the person's look at the change, ADR 0010), come first. Raises Refused, the pause
    standing, when they found a reason not seen before, which the next resume lifts
    having said it; when what would pause the account again still holds
    (``Sync.holding``); or when an account not halted is down KILL_DRAWDOWN from its
    peak, so that its first sync with a position open would trip the kill switch."""
    ledger, profile = account.ledger, account.profile
    with locked(profile.lock_path(settings)):
        now_ms = _ms(now_fn())
        found = check_fingerprint(account, intraday, now_ms) if profile.fingerprinted else []
        result = account.sync(now_ms)
        found += result.paused
        if found:
            raise Refused(_listed("对账发现了新的暂停原因，这次不解除；看过之后再运行一次", found))
        if result.holding:
            raise Refused(_listed("这些情况还在，解除了也会再暂停", result.holding))
        peak = ledger.get("peak")
        drawdown = rules.drawdown(result.equity, peak)
        if not ledger.get("halted") and drawdown >= KILL_DRAWDOWN:
            way_out = (
                f"要结束实验就运行 python -m trader {profile.name} halt" if profile.kill_final
                else f"要平仓并重置峰值，先运行 python -m trader {profile.name} halt，再运行 {profile.resume_command} --kill"
            )
            raise Refused(
                f"回撤 {drawdown:.1%} 已到熔断线 {KILL_DRAWDOWN:.0%}（净值 {result.equity:,.2f}，峰值 {peak:,.2f}）："
                f"解除之后一有持仓就会熔断。回撤若来自转出的资金，出入金记账（#40）之前只能把钱转回；{way_out}。"
            )
        reasons = account.pause_reasons
        texts = "；".join(r["text"] for r in reasons) or "没有记下原因"
        account.unpause(now_ms, f"{profile.resume_command}：解除暂停（{texts}）")
    return reasons, result


def check_fingerprint(account: DemoAccount, intraday: Ledger, now_ms: int) -> list[str]:
    """Pause the account when what its orders follow (``fingerprint``) is not what it
    was at its last run, or its last resume, then record it (ADR 0010); the reason, when
    it is a new one. Each change is a reason of its own, alerted when found."""
    ledger = account.ledger
    current, stored = fingerprint(intraday), ledger.get("fingerprint")
    new = []
    if stored is not None and stored != current:
        text = "指纹变了：" + "，".join(
            f"{label}（{_change(stored.get(part), current.get(part))}）"
            for part, label in (("code", "trader/ 的代码"), ("signal", "Signal 的指纹"))
            if stored.get(part) != current.get(part)
        )
        if account.pause(now_ms, text):
            new.append(text)
    # Recorded after the pause, so that a run failing in between leaves the change to the next.
    ledger.set("fingerprint", current)
    return new


def fingerprint(intraday: Ledger) -> dict:
    """What the orders of an account follow: the code of ``trader/`` and the Signal's
    fingerprint (model, prompt, watchlist), as the intraday ledger last recorded it."""
    return {"code": trader_digest(), "signal": intraday.get("fingerprint")}


@cache
def trader_digest() -> str:
    """The ``code_digest`` of the ``trader/`` package, as this process first read it."""
    return code_digest(Path(__file__).resolve().parents[1])


def _change(old, new) -> str:
    if isinstance(old, dict) and isinstance(new, dict):
        return "，".join(
            f"{key} {old.get(key)} → {new.get(key)}" for key in sorted(old.keys() | new.keys())
            if old.get(key) != new.get(key)
        )
    return f"{old} → {new}"


def _listed(head: str, items: list[str]) -> str:
    return head + "：\n" + "\n".join(f"  {item}" for item in items)


def _trade(
    account: DemoAccount, hour: int, signals: dict[str, str | None], now_ms: int, equity: float,
    quotes: Quotes, alerts: list[str], now_fn: Callable[[], datetime], sleep: Callable[[float], None],
) -> Sync:
    """Send the hour's orders, book them and hang their stops; the last sync's result.
    The orders, the stops and their checks all go by prices read again just before the
    orders (``DemoAccount.requote``): ``quotes`` are minutes old by then. When a step
    raises, the positions the orders have left still get their stops or are closed
    (``DemoAccount.protect``) before the exception goes on. ``alerts`` gathers what
    every step raised, whether or not the next one fails."""
    quotes = account.requote(quotes, now_ms, alerts)
    desired: dict[str, float | None] = {}
    try:
        account.execute(hour, signals, now_ms, equity, quotes, alerts=alerts, desired=desired)
        result = account.sync(_ms(now_fn()), desired_stops=desired)
        alerts += result.alerts
        _, closed = account.manage_stops(_ms(now_fn()), quotes, result.stops, alerts=alerts)
    except Exception:
        account.protect(_ms(now_fn()), quotes, desired, alerts)
        raise
    return _settled(account, alerts, now_fn, sleep) if closed else result


def _shadow(
    account: DemoAccount, hour: int, signals: dict[str, str | None], now_ms: int, result: Sync,
    quotes: Quotes, alerts: list[str],
) -> None:
    """Record what a paused account would have sent this hour, and send nothing: an
    event per order ``plan`` sizes against the exchange's equity and positions, at
    prices read again as when trading (``shadow_order``), or one saying why there is
    none (``shadow_none``); a refused order is alerted and recorded as when trading.
    The hour is then decided, so a rerun records nothing new."""
    ledger = account.ledger
    if ledger.get("halted") or result.problems:
        _shadow_none(ledger, now_ms, hour, result)
        return
    planned = account.plan(signals, result.equity, account.requote(quotes, now_ms, alerts))
    for order in planned:
        if order.refused:
            alerts.append(order.refused)
            ledger.add_event(now_ms, "order_refused", order.refused)
        else:
            ledger.add_event(now_ms, "shadow_order", _would_send(order))
    if all(order.refused for order in planned):
        reason = "要下的单都被拒绝" if planned else "离目标仓位不远，或不到最小下单量"
        ledger.add_event(now_ms, "shadow_none", f"本小时不下单：{reason}")
    ledger.set("decided_hour", hour)


def _shadow_none(ledger: Ledger, now_ms: int, hour: int, result: Sync) -> None:
    """A paused account's hour that sizes no order, the account halted or its sync
    finding problems: said, and decided."""
    reason = "熔断中" if ledger.get("halted") else f"对账有 {len(result.problems)} 个问题"
    ledger.add_event(now_ms, "shadow_none", f"本小时不下单：{reason}")
    ledger.set("decided_hour", hour)


def _would_send(order: Planned) -> str:
    side = "买入" if order.contracts > 0 else "卖出"
    close = "，平仓" if order.new_qty == 0 else ""
    return (
        f"{order.inst} {side} {abs(order.contracts):g} 张{close}，名义 {order.notional:,.0f} USDT，"
        f"信号 {order.signal or '无信号'}"
    )


def _settled(
    account: DemoAccount, alerts: list[str], now_fn: Callable[[], datetime], sleep: Callable[[float], None],
) -> Sync:
    """The sync after positions were closed at market, for want of a stop or by the
    kill switch: the close orders fill in a moment, and this books them."""
    sleep(KILL_SETTLE_SECONDS)
    result = account.sync(_ms(now_fn()))
    alerts += result.alerts
    return result


@contextmanager
def _sending(notifier: Outbox, alerts: list[str]) -> Iterator[None]:
    """Send ``alerts`` when the block ends, also when it raises: what a failed run has
    done to a position (closed it, left it without a stop) still reaches the chat."""
    try:
        yield
    finally:
        for text in alerts:
            notifier.send(text)


def _signals_for(
    intraday: Ledger, hour: int, account: DemoAccount,
    now_fn: Callable[[], datetime], sleep: Callable[[float], None],
) -> dict[str, str | None] | None:
    """The intraday account's signals for ``hour`` once it has decided it (meta
    ``decided_hour``), waiting up to INTRADAY_WAIT_MS; None when it has not. A halted
    intraday account is flat, so the demo follows with Flat for every coin."""
    if intraday.get("halted"):
        account.ledger.add_event(
            _ms(now_fn()), "follow_halt", f"日内账户熔断中，{account.profile.name} 跟随平仓"
        )
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
            out.append(f"对账：{text}")
    if problems:
        ledger.set("problem_alerts", {t: ts for t, ts in sent.items() if now_ms - ts < ALERT_INTERVAL_MS})
    return out


def _clock(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%H:%M")


def _ms(now: datetime) -> int:
    return int(now.timestamp() * 1000)
