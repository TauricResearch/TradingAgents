"""The daily report and the performance summary.

Performance is equity net of LLM spend over the validation period, set against
buy-and-hold of the same coins on OKX spot over the same days (CONTEXT.md).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from trader import message, rules
from trader.ledger import BUDGET_ERROR, Ledger
from trader.okx import DAY_MS, REQUEST_ERRORS
from trader.paper import Paper
from trader.settings import BUDGET_LEARNING_DAYS
from tradingagents.backtest import summarize


def sharpe(values: list[float]) -> float | None:
    """Annualized Sharpe of daily values: 365 days a year, zero risk-free rate.
    None with fewer than two daily returns or none of them differing."""
    returns = [b / a - 1 for a, b in pairwise(values)]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    sd = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))
    return mean / sd * math.sqrt(365) if sd else None


def max_drawdown(values: list[float]) -> float:
    peak, worst = values[0], 0.0
    for value in values:
        peak = max(peak, value)
        worst = max(worst, rules.drawdown(value, peak))
    return worst


def annualized(values: list[float]) -> float:
    return (values[-1] / values[0]) ** (365 / (len(values) - 1)) - 1


def performance_line(name: str, values: list[float]) -> str:
    if len(values) < 2:
        return f"{name}：样本不足"
    ann, mdd = annualized(values), max_drawdown(values)
    return (
        f"{name}：累计 {values[-1] / values[0] - 1:+.2%}，年化 {ann:+.1%}，"
        f"Sharpe {_num(sharpe(values))}，最大回撤 {mdd:.2%}，"
        f"年化/回撤 {_num(ann / mdd if mdd else None)}"
    )


def net_equity(ledger: Ledger) -> list[tuple[int, float]]:
    """Midnight equity over the validation period, less the LLM spend before each midnight."""
    start = ledger.get("validation_start")
    if start is None:
        return []
    costs = ledger.costs(start)
    out, spent, i = [], 0.0, 0
    for ts, equity in ledger.equity_series(start):
        while i < len(costs) and costs[i][0] < ts:
            spent += costs[i][1] or 0.0
            i += 1
        out.append((ts, equity - spent))
    return out


def baselines(paper: Paper, midnights: list[int], capital: float) -> tuple[list[float], list[float]]:
    """Equal-weight and BTC-only buy-and-hold at each midnight, bought at the spot
    closes of the day before the validation period, the closes its research saw. A
    close ``rules.usable_prices`` refuses counts as missing: a midnight without every
    close it needs is left out."""
    start = midnights[0]
    closes = {
        coin.research: {
            b.ts: b.close
            for b in paper.okx.bars(coin.spot, "1Dutc", start - DAY_MS, midnights[-1])
            if rules.usable_prices(b.close)
        }
        for coin in paper.watchlist
    }
    equal, btc = [], []
    for midnight in midnights:
        # The equity at a midnight sets against the close of the day that ends there.
        if all(midnight - DAY_MS in s and start - DAY_MS in s for s in closes.values()):
            ratios = {c: s[midnight - DAY_MS] / s[start - DAY_MS] for c, s in closes.items()}
            equal.append(capital * sum(ratios.values()) / len(ratios))
            if "BTC-USD" in ratios:
                btc.append(capital * ratios["BTC-USD"])
    return equal, btc


def full(paper: Paper, memory_log_path: Path) -> str:
    """Performance of the validation period so far, for ``python -m trader report``."""
    ledger = paper.ledger
    series = net_equity(ledger)
    if not series:
        return "验证期还没开始：第一次执行之后才有绩效。"
    midnights, values = [t for t, _ in series], [v for _, v in series]
    equal, btc = baselines(paper, midnights, values[0])
    spent, unknown = ledger.cost_since(midnights[0])
    fills = ledger.fills(midnights[0])
    reasons = [f.reason for f in fills]
    return "\n".join([
        f"模拟盘绩效：验证期自 {_date(midnights[0])} 起，共 {len(values) - 1} 天",
        performance_line("策略（扣 LLM 费用）", values),
        performance_line("三币等权买入持有", equal),
        performance_line("BTC 买入持有", btc),
        f"LLM 费用 ${spent:,.2f}{'，另有调用费用未知' if unknown else ''}；"
        f"手续费 {sum(f.fee for f in fills):,.2f}；"
        f"资金费 {ledger.funding_total(midnights[0]):+,.2f}；"
        f"成交 {len(fills)} 笔（止损 {reasons.count('stop')}，熔断 {reasons.count('kill')}）",
        "",
        _accuracy(memory_log_path),
    ])


def daily(
    paper: Paper, trade_date: str, states: dict[str, tuple[str, str | None]], now_ms: int,
    month_start_ms: int, cap: float | None,
) -> str:
    """The report sent after each daily run, laid out as ``trader.message`` says: a
    paragraph per coin (its rating, the day's trades, the position left), then the
    account's figures. ``states`` maps research tickers to ``jobs.coin_state`` results.
    The report goes out even when OKX is down or serves a price ``rules.usable_prices``
    refuses: equity is then marked at the last marks (``Paper.equity_now``), the spot
    baseline is left out, and a last line says which. A coin whose rating a rerun on the
    trade date's daily candle replaced says so, with the rating it had before when that
    differs (#53)."""
    ledger = paper.ledger
    positions = ledger.positions()
    equity, marked = paper.equity_now()
    unavailable = ["净值按最近一次标记价计"] if marked else []
    blocks = [[f"日报 · 研判日 {message.day(trade_date)}"]]
    if ledger.get("halted"):
        blocks.append(["⚠ 熔断中：只研判，不交易。确认后运行 python -m trader resume 恢复。"])
    fills = [f for f in ledger.fills(now_ms - DAY_MS) if f.trade_date == trade_date]
    updates = {coin: old for _, coin, _, old, _ in ledger.updates(trade_date)}
    for coin in paper.watchlist:
        state, detail = states[coin.research]
        if state == "done" and coin.research in updates:
            old = updates[coin.research]
            head = f"{detail}（{message.rerun(old, detail)}）"
        elif state == "done":
            head = detail
        elif detail == BUDGET_ERROR:
            head = "未研判（本月 AI 预算已用完）"
        else:
            head = f"研判失败（{(detail or '')[:80]}）"
        own = [f for f in fills if f.inst == coin.swap]
        left = message.held(positions.get(coin.swap))
        blocks.append([
            f"{message.coin(coin.swap)} · {head}",
            *([*message.trades(own), left] if own else [f"不调仓 · {left}"]),
        ])

    series = ledger.equity_series()
    today_base = series[-1][1] if series else ledger.get("capital")
    peak = ledger.get("peak")
    figures = [
        f"净值 {equity:,.2f} USDT",
        f"今日 {equity / today_base - 1:+.2%} · 回撤 {rules.drawdown(equity, peak):.1%}（峰值 {peak:,.2f}）",
    ]
    start = ledger.get("validation_start")
    if start is not None:
        base = ledger.equity_series(start)[0][1]
        spent, _ = ledger.cost_since(start)
        # The baseline holds the coins the period started with; a coin added since
        # has no reference close and is left out of it, as is one whose reference close
        # ``rules.usable_prices`` refuses (``trader.paper._baseline_ref`` writes none).
        ref = ledger.get("baseline_ref") or {}
        held = [
            c for c in paper.watchlist if c.research in ref and rules.usable_prices(ref[c.research])
        ]
        figures.append(
            f"验证期 {equity / base - 1:+.2%} · 扣 AI 费用后 {(equity - spent) / base - 1:+.2%}"
        )
        try:
            spots = [paper.okx.last_price(c.spot) for c in held]
        except REQUEST_ERRORS:
            spots = None
        if spots is None or not rules.usable_prices(*spots):  # no mark to fall back on
            unavailable.append("三币等权现货略去")
        elif spots:
            ratios = [spot / ref[c.research] for spot, c in zip(spots, held, strict=True)]
            figures.append(f"同期三币等权现货 {sum(ratios) / len(ratios) - 1:+.2%}")

    today, unknown_today = ledger.cost_of(trade_date)
    month, unknown_month = ledger.cost_since(month_start_ms)
    if cap is None:
        learned = sum(1 for _, cost in ledger.daily_costs(trade_date) if cost is not None)
        limit = f"上限未定（已观察 {min(learned, BUDGET_LEARNING_DAYS)}/{BUDGET_LEARNING_DAYS} 天）"
    else:
        limit = f"上限 ${cap:,.2f}"
    figures.append(f"AI 费用：今日 ${today:,.2f} · 本月 ${month:,.2f} / {limit}")
    if unknown_today or unknown_month:
        figures.append("有调用费用未知，没算进去")
    if unavailable:
        figures.append(f"⚠ 行情暂不可用（OKX）：{'，'.join(unavailable)}。")
    return message.paragraphs(*blocks, figures)


def _accuracy(path: Path) -> str:
    if not path.is_file():
        return "评级准确度：还没有结算的评级。"
    return "评级准确度（结算 alpha，基准为持有现金）：\n" + summarize(path).render()


def _num(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _date(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).date().isoformat()
