"""How the accounts' Telegram messages are laid out, in plain text: no markup for
Telegram to refuse.

A message opens with what it is and when, Beijing time first and UTC in brackets, behind
the label of its account (``trader.notify.labeled``). Each coin has a short paragraph,
the account's figures one of their own, items on a line set apart by `` · ``. The fills
an order came back in read as one trade at their average price.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from itertools import groupby

from trader.ledger import Fill, Position

BEIJING = timezone(timedelta(hours=8))

DAILY = "日频"      # the label of the daily account's messages
INTRADAY = "日内"   # and of the intraday account's; an exchange account's is its name

_REASONS = {"stop": "止损", "kill": "熔断", "manual": "非程序", "adjust": "调整"}


def beijing(ms: int) -> str:
    """``11-17 15:00 北京``."""
    return datetime.fromtimestamp(ms / 1000, BEIJING).strftime("%m-%d %H:%M 北京")


def when(ms: int) -> str:
    """``11-17 15:00 北京（07:00 UTC）``."""
    return f"{beijing(ms)}（{datetime.fromtimestamp(ms / 1000, UTC):%H:%M} UTC）"


def day(date: str) -> str:
    """``11-16`` of the date ``2026-11-16``."""
    return date[5:]


def coin(inst: str) -> str:
    """``BTC`` of the contract ``BTC-USDT-SWAP`` or the research ticker ``BTC-USD``."""
    return inst.split("-")[0]


def paragraphs(*blocks: list[str]) -> str:
    """The blocks that have lines, a blank line between one and the next."""
    return "\n\n".join("\n".join(block) for block in blocks if block)


def trade(qty: float, price: float, count: int = 1, *notes: str) -> str:
    """``卖出 0.0147 @ 均价 64,658.61（2 笔）``: ``qty`` signed coins traded at ``price``,
    the average of ``count`` fills when there were several; ``notes`` go in the brackets."""
    several = count > 1
    text = f"{'买入' if qty > 0 else '卖出'} {abs(qty):g} @ {'均价 ' if several else ''}{price:,.2f}"
    notes = ((f"{count} 笔",) if several else ()) + notes
    return text + (f"（{' · '.join(notes)}）" if notes else "")


def trades(fills: list[Fill], held: float | None = None) -> list[str]:
    """A line for each run of ``fills`` on one side and of one kind, in their order: the
    pieces an order was filled in are one trade at their average price. A fill that was
    not a rebalancing trade says what it was.

    ``held`` is the position the last of them left, in signed coins (0 when flat). Given
    it, a rebalancing trade that only made the position smaller says so (``reduced``):
    it buys under a Short signal or sells under a Long one, and reads as a reversal
    without the word."""
    lines = []
    position = None if held is None else round(held - sum(f.qty for f in fills), 12)
    for (_, reason), run in groupby(fills, key=lambda f: (f.qty > 0, f.reason)):
        own = list(run)
        qty = round(sum(f.qty for f in own), 12)
        price = sum(f.qty * f.price for f in own) / qty
        notes = [_REASONS[reason]] if reason in _REASONS else []
        if position is not None:
            before, position = position, round(position + qty, 12)
            if not notes and (kind := reduced(before, position)):
                notes.append(kind)
        lines.append(trade(qty, price, len(own), *notes))
    return lines


def reduced(before: float, after: float) -> str | None:
    """``空头减仓`` or ``多头减仓`` of a trade that took a position of ``before`` signed coins
    to a smaller one on the same side, ``after``; None of one that opened, added to,
    closed or reversed it."""
    if before * after > 0 and abs(after) < abs(before):
        return "空头减仓" if before < 0 else "多头减仓"
    return None


def held(pos: Position | None) -> str:
    """``持仓 -0.0539 · 止损 65,701.40``; a stop the exchange does not hold yet reads 待挂."""
    if pos is None:
        return "无持仓"
    stop = f"{pos.stop:,.2f}" if pos.stop is not None else "待挂"
    return f"持仓 {pos.qty:+g} · 止损 {stop}"


def stopped(
    inst: str, qty: float, price: float, entry: float | None, pnl: float | None, count: int = 1
) -> str:
    """The message of a stop that closed ``inst``: the ``qty`` signed coins it traded at
    ``price`` (the average of ``count`` fills), the average ``entry`` of the position it
    closed, and ``pnl``, what that made after the fees, also as a return on what the
    coins closed cost at the entry. With no ``entry`` the books held no position for it
    to close, and there is no PnL to tell."""
    head = f"止损平仓 · {coin(inst)}"
    if entry is None or pnl is None:
        return "\n".join([head, trade(qty, price, count), "账本里没有它平掉的仓位，算不出盈亏"])
    return "\n".join([
        head,
        trade(qty, price, count, f"开仓均价 {entry:,.2f}"),
        f"盈亏 {pnl:+,.2f} USDT（{pnl / (abs(qty) * entry):+.2%}）",
    ])


def rerun(old: str | None, new: str) -> str:
    """What a rerun on the trade date's daily candle did to a rating that now reads
    ``new``."""
    if old is None:
        return "重跑前没有评级"
    return "重跑后不变" if old == new else f"重跑前是 {old}"


def research_update(ticker: str, trade_date: str, old: str | None, new: str) -> str:
    """The message of a rating a rerun on the trade date's daily candle replaced (#53):
    the rating that stands, with the one it replaced when that differs."""
    rating = f"{old} → {new}" if old not in (None, new) else f"{new}（{rerun(old, new)}）"
    return "\n".join([
        f"研判更新 · {coin(ticker)}",
        f"评级 {rating}",
        f"研判日 {day(trade_date)} · 用上了当天的日线",
    ])
