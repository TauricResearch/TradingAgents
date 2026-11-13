"""Repairing the ledger of an account on the exchange that no longer agrees with it
(#37): ``python -m trader <name> reconcile``, which a person runs, and confirms, while
the account is paused or halted. Nothing runs it by itself, and the window a sync reads
stays as it is.

``plan`` only reads. It reads the exchange's fills and funding fees again over a window
longer than a sync's: from the account's opening (meta ``processed_to``), or from as far
back as OKX keeps them (HISTORY_MS), to as far as the last sync could see (``synced_to``
plus CLOCK_SKEW_MS). Missing from the ledger is a fill whose bill id is not among those
booked lately (meta ``booked_bills``) and which no fill in the ledger matches (the ledger
keeps no bill ids: time, contract, quantity and price, each booked fill matching one),
and a funding fee at a time and contract with none booked. What the fills still do not
explain once those are booked, against the positions the last sync read from the
exchange, is adjusted: fills of reason ADJUST, without a fee, at the time of that sync,
that make the fills add up to the exchange's position. What the ledger holds and the
exchange does not is closed at the entry the fills give it, so that the dashboard's
replay (``paper._move``) realizes nothing on it; what the exchange holds and the fills do
not explain is opened at the exchange's average price.

``apply`` writes a plan in one transaction, with a ``reconcile`` event saying what was
booked and why, unless the ledger changed after the plan read it. The bill ids of what
it books join the booked ones, so that the next sync does not book them again. Cash is
not touched: it is the exchange's wallet, which had them all along. The pause stays:
``resume`` lifts it, once a sync finds the ledger and the exchange agree.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from trader.demo.account import DemoAccount
from trader.demo.settings import CLOCK_SKEW_MS
from trader.intraday.paper import utc_date
from trader.ledger import Fill, Ledger, Position
from trader.okx import DAY_MS
from trader.okx_private import ExchangeFill
from trader.paper import _move

ADJUST = "adjust"  # the reason of a fill that only makes the ledger agree with the exchange
HISTORY_MS = 90 * DAY_MS  # how far back OKX keeps fills (fills-history) and bills (bills-archive)
KINDS = {"trade": "调仓", "stop": "止损", "kill": "熔断", "manual": "非程序", ADJUST: "调整"}


class Refused(Exception):
    """Nothing was repaired, for the reason it says."""


@dataclass(frozen=True)
class Adjustment:
    """What the fills of ``inst`` add up to once the missing ones are booked (``have``),
    what the exchange held at the last sync (``want``), and the fills between the two."""

    inst: str
    have: float
    want: float
    fills: tuple[Fill, ...]


@dataclass(frozen=True)
class Repair:
    """What ``plan`` found to write. ``begin`` and ``end`` bound the window read again;
    ``clipped``: the account is older than what the exchange keeps, so what is missing
    from before ``begin`` can only be adjusted. ``bills`` are the bill ids of what is
    booked, with their times; ``stamp`` is the ledger as the plan read it."""

    begin: int
    end: int
    clipped: bool
    synced_to: int
    fills: tuple[Fill, ...]
    funding: tuple[tuple[int, str, float, float], ...]
    bills: dict[str, int]
    adjustments: tuple[Adjustment, ...]
    stamp: tuple

    @property
    def empty(self) -> bool:
        return not (self.fills or self.funding or self.adjustments)


def plan(account: DemoAccount, now_ms: int) -> Repair:
    """What it takes for the ledger to agree with the exchange (see the module); only
    reads. Raises Refused unless the account is paused or halted."""
    _repairable(account)
    ledger = account.ledger
    opened = ledger.get("processed_to")
    synced_to = ledger.get("synced_to", opened)
    begin, end = max(opened, now_ms - HISTORY_MS), synced_to + CLOCK_SKEW_MS
    booked: dict[str, int] = ledger.get("booked_bills") or {}

    def key(f: ExchangeFill) -> tuple[int, str, float, float]:
        qty = f.contracts * account.spec(f.inst).contract_value * (1 if f.side == "buy" else -1)
        return f.ts, f.inst, round(qty, 12), f.price

    unmatched = Counter((f.ts, f.inst, f.qty, f.price) for f in ledger.fills(begin))
    rows = account.private.fills(begin, end)
    # A fill booked lately has its copy in the ledger, which no other fill may match.
    for f in rows:
        if f.bill_id in booked:
            unmatched[key(f)] -= 1
    fills: list[Fill] = []
    bills: dict[str, int] = {}
    for f in rows:
        if f.bill_id in booked:
            continue
        k = key(f)
        if unmatched[k] > 0:
            unmatched[k] -= 1
            continue
        # OKX reports a paid fee as negative; the ledger keeps fees as costs.
        fills.append(Fill(f.ts, f.inst, k[2], f.price, -f.fee, account._reason(f), utc_date(f.ts)))
        bills[f.bill_id] = f.ts

    booked_funding = {(ts, inst) for ts, inst, _, _ in ledger.funding(begin)}
    funding: list[tuple[int, str, float, float]] = []
    for b in account.private.funding_bills(begin, end):
        if (b.ts, b.inst) not in booked_funding:
            funding.append((b.ts, b.inst, account._funding_rate(b.inst, b.ts), b.amount))
            bills[b.bill_id] = b.ts

    positions = ledger.positions()
    implied = ledger.net_fills()
    for f in fills:
        implied[f.inst] = implied.get(f.inst, 0.0) + f.qty
    entries = _entries([*ledger.fills(), *fills])
    adjustments: list[Adjustment] = []
    for inst in sorted(set(implied) | set(positions)):
        want = positions[inst].qty if inst in positions else 0.0
        have = round(implied.get(inst, 0.0), 12)
        if abs(want - have) <= 1e-9:
            continue
        closing, opening = _legs(have, want)
        legs = []
        if closing:
            legs.append(_adjusting(synced_to, inst, closing, entries[inst]))
        if opening:
            legs.append(_adjusting(synced_to, inst, opening, positions[inst].entry))
        adjustments.append(Adjustment(inst, have, want, tuple(legs)))
    return Repair(
        begin, end, opened < begin, synced_to, tuple(fills), tuple(funding), bills,
        tuple(adjustments), _stamp(ledger),
    )


def apply(account: DemoAccount, repair: Repair, now_ms: int, note: str = "") -> str:
    """Write ``repair`` (see the module), ``note`` saying why among its event; return
    the event's text. Raises Refused, writing nothing, unless the account is still
    paused or halted and its ledger as the plan read it."""
    _repairable(account)
    ledger = account.ledger
    if _stamp(ledger) != repair.stamp:
        raise Refused("账本在确认期间变了（多半是每小时的运行刚对过账），这份修复已经不对了：请重新运行")
    text = f"修复账本（python -m trader {account.profile.name} reconcile）：" + "；".join(_summary(repair))
    if note:
        text += f"；说明：{note}"
    ledger.commit(
        positions=ledger.positions(), cash=ledger.get("cash"),
        fills=[*repair.fills, *(f for a in repair.adjustments for f in a.fills)],
        funding=list(repair.funding),
        meta={"booked_bills": (ledger.get("booked_bills") or {}) | repair.bills, "mismatched": {}},
        events=[(now_ms, "reconcile", text)],
    )
    return text


def describe(repair: Repair) -> list[str]:
    """What ``repair`` would write, line by line, for the person who confirms it."""
    window = f"重读了 {_when(repair.begin)} 到 {_when(repair.end)} UTC 的成交和资金费"
    if repair.clipped:
        window += "（交易所只保留三个月：开户之后、这之前漏记的只能记成调整）"
    lines = [window]
    if repair.empty:
        return [*lines, "账本和交易所对得上：没有漏记的成交和资金费，持仓也一致，不用修复。"]
    if repair.fills:
        lines.append(f"补记漏掉的成交 {len(repair.fills)} 笔：")
        lines += [
            f"  {_when(f.ts)} {f.inst} {f.qty:+g} @ {f.price:,.2f}，手续费 {f.fee:,.2f}，{KINDS.get(f.reason, f.reason)}"
            for f in repair.fills
        ]
    if repair.funding:
        lines.append(f"补记漏掉的资金费 {len(repair.funding)} 笔：")
        lines += [f"  {_when(ts)} {inst} {amount:+,.4f} USDT" for ts, inst, _, amount in repair.funding]
    if repair.adjustments:
        lines.append(f"补记之后仍对不上的持仓，按 {_when(repair.synced_to)} UTC 那次对账读到的交易所持仓记成调整，不收手续费：")
        lines += [
            f"  {a.inst} 账本推算 {a.have:+g}，交易所 {a.want:+g}：调整 {_legs_text(a)}" for a in repair.adjustments
        ]
        lines.append("  账本多出来的部分按账本里的开仓均价平掉，不算盈亏；交易所多出来的部分按交易所的持仓均价记开仓。")
    return lines


def _repairable(account: DemoAccount) -> None:
    if not account.paused and not account.ledger.get("halted"):
        raise Refused(f"{account.profile.name} 账户没有暂停也没有熔断：只有暂停或熔断时才能修复账本")


def _legs(have: float, want: float) -> tuple[float, float]:
    """The part of ``have`` the exchange does not hold, to close, and the part of
    ``want`` the fills do not explain, to open: one of them when both are on one side,
    both when the sides differ."""
    if have and want and (have > 0) == (want > 0):
        return (0.0, want - have) if abs(want) > abs(have) else (want - have, 0.0)
    return -have, want


def _adjusting(ts: int, inst: str, qty: float, price: float) -> Fill:
    return Fill(ts, inst, round(qty, 12), price, 0.0, ADJUST, utc_date(ts))


def _entries(fills: list[Fill]) -> dict[str, float]:
    """The average entry of the position the fills add up to, per contract, as the
    dashboard replays them (``paper._move``)."""
    positions: dict[str, Position] = {}
    for f in sorted(fills, key=lambda f: f.ts):
        new = (positions[f.inst].qty if f.inst in positions else 0.0) + f.qty
        _move(positions, f.inst, 0.0 if abs(new) < 1e-9 else new, f.price, 0.0, f.ts, f.reason, [])
    return {inst: p.entry for inst, p in positions.items()}


def _stamp(ledger: Ledger) -> tuple:
    """What a plan read of the ledger, to tell whether it changed since."""
    return (
        ledger.get("synced_to"), ledger.get("booked_bills"), ledger.net_fills(),
        {inst: p.qty for inst, p in ledger.positions().items()}, len(ledger.funding()),
    )


def _summary(repair: Repair) -> list[str]:
    parts = []
    if repair.fills:
        parts.append(f"补记漏掉的成交 {len(repair.fills)} 笔")
    if repair.funding:
        parts.append(f"补记漏掉的资金费 {len(repair.funding)} 笔")
    parts += [
        f"{a.inst} 账本推算 {a.have:+g}，交易所 {a.want:+g}，记调整 {_legs_text(a)}" for a in repair.adjustments
    ]
    return parts


def _legs_text(adjustment: Adjustment) -> str:
    return "、".join(f"{f.qty:+g} @ {f.price:,.2f}" for f in adjustment.fills)


def _when(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d %H:%M")
