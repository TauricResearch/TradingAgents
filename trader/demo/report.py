"""The messages of an account on the exchange: an hour's fills, the daily summary, the
performance. The first two go out labeled with the account's name
(``trader.notify.labeled``) and do not name it themselves.

Equity is what the last sync read from the exchange (meta ``equity``); there is no
LLM cost of its own, the signals are the intraday account's. Returns leave the transfers
out: they are the change of the equity per unit (``trader.ledger.Snapshot``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from trader import rules
from trader.demo.account import DemoAccount
from trader.intraday.paper import HOUR_MS, utc_date
from trader.ledger import Fill, Position
from trader.okx import DAY_MS
from trader.report import baselines, performance_line
from trader.settings import Coin


def hourly(account: DemoAccount, hour: int, signals: dict[str, str | None], fills: list[Fill]) -> str:
    """The message for an hour that traded: each traded coin's signal, fills and the
    position left, then the exchange equity."""
    positions = account.ledger.positions()
    when = datetime.fromtimestamp(hour / 1000, UTC).strftime("%m-%d %H:%M")
    lines = [f"{when} UTC"]
    for coin in account.watchlist:
        own = [f for f in fills if f.inst == coin.swap]
        if own:
            action = "；".join(_fill_text(f) for f in own)
            signal = signals.get(coin.research) or "无信号"
            lines.append(f"{_name(coin)}：{signal} → {action}；{_held(positions.get(coin.swap))}")
    lines.append(f"交易所权益 {account.ledger.get('equity', 0.0):,.2f} USDT")
    return "\n".join(lines)


def daily(account: DemoAccount, day: str, now_ms: int) -> str:
    """The summary of the UTC day ``day`` ("YYYY-MM-DD"), sent on the first run after it:
    the return since the snapshot at the start of the day (since the account opened
    when there is none yet), the day's fills by kind, its funding, its transfers when
    there were any, and the standing problems; for a
    paused account, that it is, how many orders the day's shadow run recorded, and why
    it is paused, since when, and what lifts it."""
    ledger = account.ledger
    day_start = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000)
    day_end = day_start + DAY_MS
    equity = ledger.get("equity", ledger.get("cash"))
    lines = [f"日报 · {day}"]
    if ledger.get("halted"):
        held = ledger.positions()
        state = f"交易所里还有 {len(held)} 个仓位，每次运行都再平" if held else "已平仓"
        lines.append(f"⚠ 熔断中：{state}，不再下单。{account.profile.after_kill}")
    if account.paused:
        would = [ts for ts, _, _ in ledger.events(day_start, ("shadow_order",)) if ts < day_end]
        lines.append(
            f"⏸ 暂停中（影子运行）：不下单，昨日本该下 {len(would)} 笔，"
            f"明细见 python -m trader {account.profile.name} report"
        )
        reasons = account.pause_reasons
        for reason in reasons:
            since = datetime.fromtimestamp(reason["since"] / 1000, UTC).strftime("%m-%d %H:%M")
            lines.append(f"  暂停原因（{since} UTC 起）：{reason['text']}")
        if not reasons:
            lines.append("  暂停原因：账本里没有记下")
        lines.append(f"  查明原因后运行 {account.profile.resume_command} 解除")
    bases = [s for s in ledger.snapshots() if s.ts <= day_start]
    # The equity in the units of the base: itself while no transfer came in between.
    change = (
        f"较昨日零点 {equity * (bases[-1].units / ledger.units()) / bases[-1].equity - 1:+.2%}"
        if bases and bases[-1].equity
        else f"较本金 {equity * (ledger.get('capital') / ledger.units()) / ledger.get('capital') - 1:+.2%}"
    )
    peak = ledger.get("peak")
    lines.append(
        f"权益 {equity:,.2f} USDT，{change}，回撤 {rules.drawdown(equity, peak):.1%}（峰值 {peak:,.2f}）"
    )
    fills = [f for f in ledger.fills(day_start) if f.ts < day_end]
    lines.append(
        f"昨日成交 {len(fills)} 笔（{_kinds(fills)}），"
        f"手续费 {sum(f.fee for f in fills):,.2f}，资金费 {_funding(ledger, day_start, day_end):+,.2f}"
    )
    moved = [amount for ts, amount in ledger.transfers(day_start) if ts < day_end]
    if moved:
        lines.append(f"昨日出入金 {_moved(moved)}，投入本金合计 {ledger.contributed():,.2f}，不算收益")
    problems = ledger.get("problems") or []
    if problems:
        lines.append(f"对账问题 {len(problems)} 项，最近一条：{problems[-1]}")
    synced = ledger.get("synced_at")
    if synced:
        lines.append(f"最近对账 {datetime.fromtimestamp(synced / 1000, UTC).strftime('%m-%d %H:%M')} UTC")
    return "\n".join(lines)


def full(account: DemoAccount) -> str:
    """Performance since the first execution, for ``python -m trader <name> report``."""
    ledger, name = account.ledger, account.profile.name
    start = ledger.get("validation_start")
    series = ledger.adjusted_series(start) if start is not None else []
    if not series:
        return f"{name} 账户还没开始：第一次执行之后才有绩效。"
    midnights, values = [t for t, _ in series], [v for _, v in series]
    equal, btc = baselines(account, midnights, values[0])
    fills = ledger.fills(midnights[0])
    moved = [amount for _, amount in ledger.transfers(midnights[0])]
    return "\n".join([
        f"{name} 绩效：自 {utc_date(midnights[0])} 起，共 {len(values) - 1} 天",
        performance_line(f"{name}（交易所权益）", values),
        performance_line("三币等权持有", equal),
        performance_line("BTC 单持", btc),
        f"成交 {len(fills)} 笔（{_kinds(fills)}），"
        f"手续费 {sum(f.fee for f in fills):,.2f}，资金费 {ledger.funding_total(midnights[0]):+,.2f}",
        *(
            [f"出入金 {_moved(moved)}，投入本金合计 {ledger.contributed():,.2f}：收益按时间加权，不算出入金"]
            if moved else []
        ),
    ])


def shadow(account: DemoAccount) -> str:
    """The orders the shadow run would have sent, by hour, and how many hours it sized
    none, for ``python -m trader <name> report``."""
    rows = account.ledger.events(kinds=("shadow_order", "shadow_none"))
    if not rows:
        return "影子运行还没有记录。"
    orders = [(ts, text) for ts, kind, text in rows if kind == "shadow_order"]
    lines = [f"影子运行：本该下的单 {len(orders)} 笔，另有 {len(rows) - len(orders)} 个小时没有要下的单"]
    for ts, text in orders:
        hour = datetime.fromtimestamp((ts - ts % HOUR_MS) / 1000, UTC).strftime("%m-%d %H:%M")
        lines.append(f"  {hour} UTC  {text}")
    return "\n".join(lines)


def _kinds(fills: list[Fill]) -> str:
    """The fills counted by kind; adjustments (``python -m trader <name> reconcile``)
    only when there are any."""
    reasons = [f.reason for f in fills]
    text = (
        f"调仓 {reasons.count('trade')}，止损 {reasons.count('stop')}，"
        f"熔断 {reasons.count('kill')}，非程序 {reasons.count('manual')}"
    )
    adjusted = reasons.count("adjust")
    return text + (f"，调整 {adjusted}" if adjusted else "")


def _moved(amounts: list[float]) -> str:
    """Transfers by direction: what came in, what went out, each when there was any."""
    parts = [
        f"{label} {len(own)} 笔 {sum(own):+,.2f}"
        for label, own in (("转入", [a for a in amounts if a > 0]), ("转出", [a for a in amounts if a < 0]))
        if own
    ]
    return "，".join(parts) + " USDT"


def _funding(ledger, start: int, end: int) -> float:
    return ledger.funding_total(start) - ledger.funding_total(end)


def _fill_text(fill: Fill) -> str:
    return f"{'买入' if fill.qty > 0 else '卖出'} {abs(fill.qty):g} @ {fill.price:,.2f}"


def _held(pos: Position | None) -> str:
    if pos is None:
        return "无持仓"
    stop = f"{pos.stop:,.2f}" if pos.stop is not None else "待挂"
    return f"持仓 {pos.qty:+g}，止损 {stop}"


def _name(coin: Coin) -> str:
    return coin.research.split("-")[0]
