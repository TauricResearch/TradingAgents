"""The intraday account's messages: an hour's fills, the daily summary, the performance.
The first two are laid out as ``trader.message`` says and go out labeled with the
account (``trader.notify.labeled``); they do not name it themselves.

Performance is equity net of the signals' LLM spend over the validation period,
set against buy-and-hold of the same coins on OKX spot (CONTEXT.md), with the
daily report's metrics. There is no rating accuracy section: hourly signals are
recorded, not settled (ADR 0006).
"""

from __future__ import annotations

from datetime import UTC, datetime

from trader import message, rules
from trader.intraday.paper import IntradayPaper, utc_date
from trader.ledger import Fill, Ledger
from trader.okx import DAY_MS
from trader.report import baselines, performance_line

# Appended to an equity figure marked at the last marks because OKX gave no price.
UNAVAILABLE = "（行情暂不可用，按最近一次标记价计）"


def hourly(
    paper: IntradayPaper, hour: int, signals: dict[str, str | None], fills: list[Fill]
) -> str:
    """The message for an hour that had fills: a paragraph for each filled coin (its
    signal, its trades, the position left), then the equity. ``fills`` are the hour's,
    from ``ledger.fills``."""
    positions = paper.ledger.positions()
    blocks = [[f"成交 · {message.when(hour)}"]]
    for coin in paper.watchlist:
        own = [f for f in fills if f.inst == coin.swap]
        if own:
            signal = signals.get(coin.research)
            blocks.append([
                f"{message.coin(coin.swap)} · {f'信号 {signal}' if signal else '无信号'}",
                *message.trades(own),
                message.held(positions.get(coin.swap)),
            ])
    equity, unavailable = paper.equity_now()
    blocks.append([f"净值 {equity:,.2f} USDT{UNAVAILABLE if unavailable else ''}"])
    return message.paragraphs(*blocks)


def daily(paper: IntradayPaper, day: str, now_ms: int) -> str:
    """The summary of the UTC day ``day`` ("YYYY-MM-DD"), sent on the first run after it.

    Equity is set against the snapshot at the start of ``day`` (against the capital
    when there is none yet); the day's fills and signals are counted by kind; the LLM
    cost of the day and of the month to date comes from the signals table.
    """
    ledger = paper.ledger
    day_start = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000)
    day_end = day_start + DAY_MS
    equity, unavailable = paper.equity_now()
    blocks = [[f"日报 · {message.day(day)}（UTC）"]]
    if ledger.get("halted"):
        blocks.append(["⚠ 熔断中：不求信号、不交易。确认后运行 python -m trader intraday resume 恢复。"])
    bases = [e for ts, e in ledger.equity_series() if ts <= day_start]
    change = (
        f"较 {message.day(day)} 零点 {equity / bases[-1] - 1:+.2%}" if bases
        else f"较本金 {equity / ledger.get('capital') - 1:+.2%}"
    )
    peak = ledger.get("peak")
    blocks.append([
        f"净值 {equity:,.2f} USDT{UNAVAILABLE if unavailable else ''}",
        f"{change} · 回撤 {rules.drawdown(equity, peak):.1%}（峰值 {peak:,.2f}）",
    ])
    reasons = [f.reason for f in ledger.fills(day_start) if f.ts < day_end]
    signals = [row[2] for row in ledger.signals(day_start) if row[0] < day_end]
    day_costs = [cost for ts, cost in ledger.signal_costs(day_start) if ts < day_end]
    month, unknown_month = ledger.signal_cost_since(_month_start_ms(now_ms))
    blocks.append([
        f"成交 {len(reasons)} 笔：调仓 {reasons.count('trade')} · "
        f"止损 {reasons.count('stop')} · 熔断 {reasons.count('kill')}",
        f"信号 {len(signals)} 次：Long {signals.count('Long')} · "
        f"Short {signals.count('Short')} · Flat {signals.count('Flat')} · 失败 {signals.count(None)}",
        f"AI 费用：当日 ${sum(c or 0.0 for c in day_costs):,.2f} · 本月 ${month:,.2f}"
        "（已从绩效扣除，没有预算上限）",
        *(["有调用费用未知，没算进去"] if None in day_costs or unknown_month else []),
    ])
    return message.paragraphs(*blocks)


def full(paper: IntradayPaper) -> str:
    """Performance of the validation period so far, for ``python -m trader intraday report``."""
    ledger = paper.ledger
    series = net_equity(ledger)
    if not series:
        return "日内盘验证期还没开始：第一次执行之后才有绩效。"
    midnights, values = [t for t, _ in series], [v for _, v in series]
    equal, btc = baselines(paper, midnights, values[0])
    spent, unknown = ledger.signal_cost_since(midnights[0])
    fills = ledger.fills(midnights[0])
    reasons = [f.reason for f in fills]
    return "\n".join([
        f"日内盘绩效：验证期自 {utc_date(midnights[0])} 起，共 {len(values) - 1} 天",
        performance_line("策略（扣 LLM 费用）", values),
        performance_line("三币等权买入持有", equal),
        performance_line("BTC 买入持有", btc),
        f"LLM 费用 ${spent:,.2f}，已从策略曲线扣除，没有月度预算上限"
        f"{'；另有调用费用未知' if unknown else ''}；"
        f"手续费 {sum(f.fee for f in fills):,.2f}；"
        f"资金费 {ledger.funding_total(midnights[0]):+,.2f}；"
        f"成交 {len(fills)} 笔（调仓 {reasons.count('trade')}，"
        f"止损 {reasons.count('stop')}，熔断 {reasons.count('kill')}）",
    ])


def net_equity(ledger: Ledger) -> list[tuple[int, float]]:
    """Midnight equity over the validation period, less the signals' LLM spend before
    each midnight (``trader.report.net_equity`` with the signals table for costs)."""
    start = ledger.get("validation_start")
    if start is None:
        return []
    costs = ledger.signal_costs(start)
    out, spent, i = [], 0.0, 0
    for ts, equity in ledger.equity_series(start):
        while i < len(costs) and costs[i][0] < ts:
            spent += costs[i][1] or 0.0
            i += 1
        out.append((ts, equity - spent))
    return out


def _month_start_ms(now_ms: int) -> int:
    first = datetime.fromtimestamp(now_ms / 1000, UTC).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    return int(first.timestamp() * 1000)
