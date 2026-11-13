"""The messages of an account on the exchange: an hour's fills, the daily summary, the
performance. The first two go out labeled with the account's name
(``trader.notify.labeled``) and do not name it themselves.

Equity is what the last sync read from the exchange (meta ``equity``); there is no
LLM cost of its own, the signals are the intraday account's.
"""

from __future__ import annotations

from datetime import UTC, datetime

from trader import rules
from trader.demo.account import DemoAccount
from trader.intraday.paper import utc_date
from trader.ledger import Fill, Position
from trader.okx import DAY_MS
from trader.report import baselines, net_equity, performance_line
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
    equity against the snapshot at the start of the day (the capital when there is
    none yet), the day's fills by kind, its funding, and the standing problems; for a
    paused account, that it is, and how many orders the day's shadow run recorded."""
    ledger = account.ledger
    day_start = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000)
    day_end = day_start + DAY_MS
    equity = ledger.get("equity", ledger.get("cash"))
    lines = [f"日报 · {day}"]
    if ledger.get("halted"):
        lines.append(f"⚠ 熔断中：已平仓，不再下单。确认后运行 {account.profile.resume_command} 恢复。")
    if account.paused:
        would = [ts for ts, _, _ in ledger.events(day_start, ("shadow_order",)) if ts < day_end]
        lines.append(
            f"⏸ 暂停中（影子运行）：不下单，昨日本该下 {len(would)} 笔，"
            f"明细见 python -m trader {account.profile.name} report"
        )
    bases = [e for ts, e in ledger.equity_series() if ts <= day_start]
    change = (
        f"较昨日零点 {equity / bases[-1] - 1:+.2%}" if bases and bases[-1]
        else f"较本金 {equity / ledger.get('capital') - 1:+.2%}"
    )
    peak = ledger.get("peak")
    lines.append(
        f"权益 {equity:,.2f} USDT，{change}，回撤 {rules.drawdown(equity, peak):.1%}（峰值 {peak:,.2f}）"
    )
    fills = [f for f in ledger.fills(day_start) if f.ts < day_end]
    reasons = [f.reason for f in fills]
    lines.append(
        f"昨日成交 {len(reasons)} 笔（调仓 {reasons.count('trade')}，止损 {reasons.count('stop')}，"
        f"熔断 {reasons.count('kill')}，非程序 {reasons.count('manual')}），"
        f"手续费 {sum(f.fee for f in fills):,.2f}，资金费 {_funding(ledger, day_start, day_end):+,.2f}"
    )
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
    series = net_equity(ledger)
    if not series:
        return f"{name} 账户还没开始：第一次执行之后才有绩效。"
    midnights, values = [t for t, _ in series], [v for _, v in series]
    equal, btc = baselines(account, midnights, values[0])
    fills = ledger.fills(midnights[0])
    reasons = [f.reason for f in fills]
    return "\n".join([
        f"{name} 绩效：自 {utc_date(midnights[0])} 起，共 {len(values) - 1} 天",
        performance_line(f"{name}（交易所权益）", values),
        performance_line("三币等权持有", equal),
        performance_line("BTC 单持", btc),
        f"成交 {len(fills)} 笔（调仓 {reasons.count('trade')}，止损 {reasons.count('stop')}，"
        f"熔断 {reasons.count('kill')}，非程序 {reasons.count('manual')}），"
        f"手续费 {sum(f.fee for f in fills):,.2f}，资金费 {ledger.funding_total(midnights[0]):+,.2f}",
    ])


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
