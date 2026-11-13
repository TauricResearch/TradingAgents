"""The demo account on the exchange: reconcile, keep the stops, execute the hour's signals.

The exchange is the fact and the ledger its copy plus our annotations (ADR 0008):
``sync`` reads balance, positions, new fills, funding and pending stops back into
the ledger before anything else happens, and flags what it cannot explain.
``manage_stops`` tightens each position's stop to the hour's quotes and makes the
exchange's pending conditional orders match, without a moment in which a position
has lost the stop it had: a stop is amended in place, or replaced only once its
successor is pending, and a position whose stop cannot be made to stand is closed
at market. ``execute`` sizes the intraday signals with the intraday constants
against the demo's own equity and sends market orders whose client ids make a
rerun harmless. ``protect`` gives the positions their stops when a step after the
orders has raised. A contract whose price or ATR is not a positive finite number is
neither traded nor has its stop moved (``quotes``), and an order that would leave a
position the rules never size is refused (``plan``).

One executor serves each account that trades on OKX (ADR 0010): a ``Profile`` says
which one it is, the demo's by default.

The kill switch (meta ``halted``) is tripped by a drawdown of KILL_DRAWDOWN in ``sync``,
or by a person with ``halt``, and is recorded before anything is closed: a run that
fails halfway leaves the account halted. Every sync of a halted account closes at market
what the exchange still holds, each contract on its own, and cancels the stops of the
contracts it no longer holds; a contract still held keeps its stop, and is closed again,
and alerted, on each sync until the exchange is flat.

An account may be paused (meta ``paused``), for the reasons meta ``pause_reasons`` keeps
with the time each entered: ``pause`` adds one and ``unpause`` lifts them all, each
recording an event of kind ``pause`` or ``unpause``. ``sync`` pauses the account for what
it cannot explain (ADR 0010): a fill the program did not cause, a change of the balance
other than a trade's or a funding fee's, a position the fills still do not explain at a
later sync, and equity above the profile's ``max_equity``. A paused
account syncs, books what it finds and alerts, and changes nothing on the exchange: its
``private`` is then a ``ReadOnly`` view that raises ``Paused`` on any call but a read,
so there is no setup, no stop kept, no order and no kill by drawdown; a drawdown to the
kill line, and a position without a stop, are problems left to a person. The kill a
person orders is the exception (ADR 0010): a halted account closes out, paused or not.
An account whose profile is ``born_paused`` is paused until its ledger says otherwise.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from trader import rules
from trader.demo.settings import (
    CLOCK_SKEW_MS,
    KILL_PREFIX,
    LEVERAGE,
    MARGIN_MODE,
    MISMATCH_GRACE_MS,
    ORDER_POLL_SECONDS,
    ORDER_POLLS,
    STOP_PREFIX,
    STOP_RETRY_SECONDS,
    STOP_TRIES,
    SYNC_OVERLAP_MS,
    TRADE_PREFIX,
)
from trader.intraday.paper import HOUR_MS, utc_date
from trader.intraday.settings import (
    ATR_BAR,
    ATR_BARS,
    REBALANCE_THRESHOLD,
    RISK_PER_UNIT,
    STOP_ATR_MULT,
    WEIGHTS,
)
from trader.ledger import Fill, Ledger, Position
from trader.okx import DAY_MS, OKX, REQUEST_ERRORS, ContractSpec
from trader.okx_private import (
    DUPLICATE_CLIENT_ID,
    FUNDING_BILL,
    TRADE_BILL,
    TRANSFER_BILL,
    Bill,
    ExchangeFill,
    OKXPrivate,
    OKXPrivateError,
    StopOrder,
)
from trader.paper import _midnights
from trader.settings import KILL_DRAWDOWN, MAX_COIN_EXPOSURE, WATCHLIST, Coin, Settings

logger = logging.getLogger(__name__)

Quotes = dict[str, tuple[float, float]]  # inst -> (last price, hourly ATR)
REASONS = ((TRADE_PREFIX, "trade"), (STOP_PREFIX, "stop"), (KILL_PREFIX, "kill"))
MANUAL = "manual"  # a fill the program did not cause
# How far over a coin's cap, as a share of it, a position the rules sized at the cap may come
# out: rules.to_quantity lets float noise round up to a whole lot, which adds under 1e-9.
ROUNDING = 1e-6
# OKX's codes for refusing a stop whose trigger the last price has already passed: 51278
# "SL trigger price cannot be lower than the last price" (a short's stop), 51280 "cannot
# be higher" (a long's). From OKX's error table, not yet met on the exchange (#42); a
# refusal under any other code goes the way of every other failed stop.
TRIGGER_PASSED = ("51278", "51280")


@dataclass(frozen=True)
class Profile:
    """Which account the executor is (ADR 0010). ``name`` labels the account's messages
    (``trader.notify.labeled``) and names its commands, its ledger and its lock in
    ``Settings`` (``<name>_ledger_path``, ``<name>_lock_path``) and the meta keys of its
    failure alerts and of its messages not sent yet. ``production`` is the environment
    of OKX its client must be of: the production one, with real money, or else simulated
    trading. The last three are the live account's guards (ADR 0010)."""

    name: str
    production: bool = False
    born_paused: bool = False  # paused until the ledger records otherwise (DemoAccount.paused)
    kill_final: bool = False  # a kill is never lifted: it ends the account's experiment (ADR 0010)
    fingerprinted: bool = False  # paused when the code or the Signal its orders follow changes
    max_equity: float | None = None  # paused with more equity than this, USDT
    max_position: float | None = None  # an order leaving a larger position is refused, USDT notional

    @property
    def resume_command(self) -> str:
        """The command that lifts the account's pause; with ``--kill``, its kill switch."""
        return f"python -m trader {self.name} resume"

    @property
    def after_kill(self) -> str:
        """What comes after a kill, as its alert and the daily summary say."""
        if self.kill_final:
            return f"按 ADR 0010，{self.name} 熔断一次就不再解除，实验到此结束。"
        return f"确认交易所里已经空仓、查明原因后，运行 {self.resume_command} --kill 解除。"

    def pause_alert(self, reason: str) -> str:
        """The alert of the account paused for ``reason``."""
        return f"暂停：{reason}。不再下新单，仓位和止损单原样保留；查明原因后运行 {self.resume_command} 解除。"

    @property
    def failures_key(self) -> str:
        """Meta: when the alert of each kind of failure of the account's runs last went out."""
        return f"{self.name}_failures_alerted"

    @property
    def unsent_key(self) -> str:
        """Meta: the account's messages Telegram has not taken yet (``trader.notify.Outbox``)."""
        return f"{self.name}_unsent"

    def ledger_path(self, settings: Settings) -> Path:
        return getattr(settings, f"{self.name}_ledger_path")

    def lock_path(self, settings: Settings) -> Path:
        return getattr(settings, f"{self.name}_lock_path")


DEMO = Profile("demo")


class Paused(RuntimeError):
    """A paused account was about to change something on the exchange."""


class ReadOnly:
    """The reads of an OKXPrivate: all a paused account may ask of the exchange. Any
    other call raises Paused before a request is sent."""

    READS = frozenset({
        "simulated", "base_url", "account_config", "balance", "positions", "pending_stops",
        "fills", "funding_bills", "bills", "order", "fee_rate",
    })

    def __init__(self, client: OKXPrivate):
        self._client = client

    def __getattr__(self, name: str):
        if name in self.READS:
            return getattr(self._client, name)
        raise Paused(f"the account is paused: {name} is not a read")


@dataclass(frozen=True)
class Planned:
    """An order of the hour as ``DemoAccount.plan`` sizes it: ``contracts`` of ``inst``
    take the position from ``old_qty`` to ``new_qty`` (coins) at about ``price``, for
    the coin's ``signal``. ``refused`` says why it must not be sent, when it must not."""

    inst: str
    signal: str | None
    old_qty: float
    new_qty: float
    contracts: float
    price: float
    atr: float
    refused: str | None = None

    @property
    def notional(self) -> float:
        return abs(round(self.new_qty - self.old_qty, 12)) * self.price


@dataclass
class Sync:
    """What a sync found. ``problems`` are the things that stop the account from
    trading this hour; ``alerts`` go out whatever happens. ``killed``: the kill switch
    sent close orders, which fill in a moment and one more sync books. ``paused``: the
    reasons the sync paused the account for, new ones only; ``holding``: what would pause
    it again were the pause lifted now (a position the fills do not explain, equity above
    the cap)."""

    equity: float
    cash: float
    positions: dict[str, Position]
    stops: list[StopOrder]
    fills: list[Fill]
    problems: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    killed: bool = False
    paused: list[str] = field(default_factory=list)
    holding: list[str] = field(default_factory=list)


class DemoAccount:
    def __init__(
        self,
        ledger: Ledger,
        okx: OKX,
        private: OKXPrivate,
        watchlist: tuple[Coin, ...] = WATCHLIST,
        sleep: Callable[[float], None] = time.sleep,
        profile: Profile = DEMO,
    ):
        if private.simulated == profile.production:
            where = "OKX's production environment" if profile.production else "OKX's simulated trading"
            raise ValueError(f"the {profile.name} account trades on {where}; this client is not on it")
        self.profile = profile
        self.ledger = ledger
        self.okx = okx          # public market data: last prices, candles, contract specs
        self._private = private  # the signed calls, through ``private``
        self.watchlist = watchlist
        self.sleep = sleep
        self._specs: dict[str, ContractSpec] = {}
        self._seq = 0  # keeps the client ids of one run apart

    @property
    def private(self) -> OKXPrivate:
        """The signed calls; while the account is paused, only those that read."""
        return ReadOnly(self._private) if self.paused else self._private

    @property
    def paused(self) -> bool:
        return bool(self.ledger.get("paused", self.profile.born_paused))

    @property
    def pause_reasons(self) -> list[dict]:
        """Why the account is paused: each reason's ``key``, ``text`` and ``since`` (when
        it entered, ms), in the order they entered."""
        return list(self.ledger.get("pause_reasons") or [])

    def pause(self, now_ms: int, reason: str, key: str | None = None) -> bool:
        """Pause the account for ``reason``, kept under ``key`` (the reason itself by
        default) with the time it entered, and record a ``pause`` event. False, and
        nothing written, when a reason under ``key`` already stands: each reason enters,
        and is alerted, once."""
        key = key or reason
        with self.ledger.transaction():
            reasons = self.pause_reasons
            if any(r["key"] == key for r in reasons):
                return False
            self.ledger.set("paused", True)
            self.ledger.set("pause_reasons", [*reasons, {"key": key, "text": reason, "since": now_ms}])
            self.ledger.add_event(now_ms, "pause", reason)
        return True

    def unpause(self, now_ms: int, reason: str) -> None:
        """Lift the pause and all its reasons, recording an ``unpause`` event."""
        with self.ledger.transaction():
            self.ledger.set("paused", False)
            self.ledger.set("pause_reasons", [])
            self.ledger.add_event(now_ms, "unpause", reason)

    def halt(self, now_ms: int, reason: str) -> None:
        """Trip the kill switch: meta ``halted`` and a ``kill`` event saying ``reason``,
        written before anything is closed; each sync from now on closes what is held."""
        with self.ledger.transaction():
            self.ledger.set("halted", True)
            self.ledger.add_event(now_ms, "kill", reason)

    # -- exchange setup -------------------------------------------------------

    def setup(self) -> list[str]:
        """Put the exchange account in the mode the demo trades in (ADR 0008): net
        position mode and cross margin at LEVERAGE on each watchlist contract. Safe to
        repeat. Returns what it changed."""
        notes = []
        if self.private.account_config().position_mode != "net_mode":
            self.private.set_position_mode(True)
            notes.append("持仓模式已切到单向（net_mode）")
        for coin in self.watchlist:
            self.private.set_leverage(coin.swap, LEVERAGE, MARGIN_MODE)
        notes.append(f"{len(self.watchlist)} 个合约杠杆设为 {MARGIN_MODE} {LEVERAGE}×")
        return notes

    def spec(self, inst: str) -> ContractSpec:
        if inst not in self._specs:
            self._specs[inst] = self.okx.contract_spec(inst)
        return self._specs[inst]

    def instruments(self, positions: dict[str, Position]) -> list[str]:
        """The watchlist's contracts, then any other the account still holds."""
        swaps = [coin.swap for coin in self.watchlist]
        return swaps + [inst for inst in positions if inst not in swaps]

    def quotes(
        self, hour: int, positions: dict[str, Position], now_ms: int, alerts: list[str],
    ) -> Quotes:
        """Last price and hourly ATR (ATR_BARS candles closed before ``hour``) of every
        contract the account quotes, as the intraday account measures them. A contract
        whose price or ATR is not a positive finite number is left out, and alerted
        (into ``alerts``, and an event ``quote_unusable``): it is not traded this hour
        (``plan``), and its stop is not moved (``manage_stops``)."""
        out = {}
        for inst in self.instruments(positions):
            hourly = self.okx.bars(inst, ATR_BAR, hour - (ATR_BARS + 5) * HOUR_MS, hour)
            atr_value = rules.atr(
                [b.high for b in hourly], [b.low for b in hourly], [b.close for b in hourly],
                days=ATR_BARS,
            )
            out[inst] = (self.okx.last_price(inst), atr_value)
        return self._usable(out, now_ms, alerts)

    def requote(self, quotes: Quotes, now_ms: int, alerts: list[str]) -> Quotes:
        """``quotes`` with each contract's last price read again, for the orders, which
        come minutes after the hour's first quotes; the ATR, of candles closed before
        the hour, stays. A price that is not usable is left out and alerted as in
        ``quotes``; a contract ``quotes`` left out stays out."""
        return self._usable(
            {inst: (self.okx.last_price(inst), atr_value) for inst, (_, atr_value) in quotes.items()},
            now_ms, alerts,
        )

    def _usable(self, quotes: Quotes, now_ms: int, alerts: list[str]) -> Quotes:
        """The quotes whose price and ATR are both positive finite numbers; every other
        one is alerted."""
        out = {}
        for inst, (price, atr_value) in quotes.items():
            if all(math.isfinite(x) and x > 0 for x in (price, atr_value)):
                out[inst] = (price, atr_value)
            else:
                self._alert(now_ms, "quote_unusable", alerts, (
                    f"报价不能用：{inst} 现价 {price:,.2f}，ATR {atr_value:,.2f}，都要是大于 0 的有限数；"
                    "这个币本小时不交易，止损也不按它调整"
                ))
        return out

    # -- reconciliation -------------------------------------------------------

    def sync(self, now_ms: int, desired_stops: dict[str, float | None] | None = None) -> Sync:
        """Read the exchange into the ledger and judge whether the account may trade.

        Fills, funding bills and the other bills since the last sync (less
        SYNC_OVERLAP_MS, up to CLOCK_SKEW_MS past now, deduplicated by bill id in meta
        ``booked_bills``) are booked, a fill the program did not cause as MANUAL. A stop
        that fired on the exchange is alerted with what it traded and made
        (``_fired_text``): its fills, unlike those of a close the program sent for want of
        a stop, which that close's own alert announced, carry no client id. The positions
        become the exchange's, each keeping the stop the ledger tracked for it
        (or the one in ``desired_stops``, set by an execution). One not in MARGIN_MODE
        at LEVERAGE is a problem. Cash is the wallet balance, equity includes unrealized
        PnL. Each UTC midnight passed since the last sync gets the current equity as its
        snapshot. A balance that cannot be read raises (``NoBalance``) before anything
        is booked.

        What the sync cannot explain pauses the account (``pause``, ADR 0010), before
        anything is judged on the equity: a MANUAL fill (a liquidation's among them), a
        bill other than a trade's or a funding fee's that changed the balance, a
        position the booked fills still do not explain at a sync MISMATCH_GRACE_MS after
        the one that first found it (until then a problem: the next hourly sync books
        a fill the exchange reports late), and equity above the profile's
        ``max_equity``. Each reason is alerted once, when it enters.

        The peak follows equity, and a drawdown of KILL_DRAWDOWN with positions open
        trips the kill switch (``halt``). A paused account trips nothing: the drawdown is
        a problem, and so is a position without a stop. While a bill nothing explains
        pauses the account, its equity measures nothing: the peak stays and the drawdown
        is not judged. A halted account's positions are closed at market (``_flatten``),
        and what that did, failed to do or found already flat is alerted.
        """
        ledger = self.ledger
        balance = self.private.balance()
        exchange = {p.inst: p for p in self.private.positions()}
        stops = self.private.pending_stops()
        since = ledger.get("synced_to", ledger.get("processed_to"))
        begin = since - SYNC_OVERLAP_MS
        booked: dict[str, int] = ledger.get("booked_bills") or {}
        fills, funding, manual, unexplained, problems, alerts = [], [], [], [], [], []
        fired: dict[str, list[tuple[float, Fill]]] = {}  # inst -> (contracts, fill) of its stop's fills
        end = now_ms + CLOCK_SKEW_MS
        for f in self.private.fills(begin, end):
            if f.bill_id in booked:
                continue
            qty = f.contracts * self.spec(f.inst).contract_value * (1 if f.side == "buy" else -1)
            reason = self._reason(f)
            if reason == MANUAL:
                manual.append(f)
            # OKX reports a paid fee as negative; the ledger keeps fees as costs.
            fill = Fill(f.ts, f.inst, round(qty, 12), f.price, -f.fee, reason, utc_date(f.ts))
            fills.append(fill)
            if reason == "stop" and not f.client_id:
                fired.setdefault(f.inst, []).append((f.contracts, fill))
            booked[f.bill_id] = f.ts
        for b in self.private.funding_bills(begin, end):
            if b.bill_id in booked:
                continue
            funding.append((b.ts, b.inst, self._funding_rate(b.inst, b.ts), b.amount))
            booked[b.bill_id] = b.ts
        for b in self.private.bills(begin, end):
            # A trade's bill and a funding fee's are what the fills and the funding book.
            if b.bill_id in booked or b.type in (TRADE_BILL, FUNDING_BILL) or not b.amount:
                continue
            unexplained.append(b)
            booked[b.bill_id] = b.ts
        booked = {bill: ts for bill, ts in booked.items() if ts >= begin}

        old = ledger.positions()
        alerts += [_fired_text(inst, legs, old.get(inst)) for inst, legs in fired.items()]
        positions: dict[str, Position] = {}
        for inst, p in exchange.items():
            qty = round(p.contracts * self.spec(inst).contract_value, 12)
            kept = old[inst].stop if inst in old and (old[inst].qty > 0) == (qty > 0) else None
            stop = (desired_stops or {}).get(inst, kept)
            positions[inst] = Position(qty, p.avg_price, stop)
            if p.margin_mode != MARGIN_MODE or round(p.leverage) != LEVERAGE:
                problems.append(
                    f"{inst} 在交易所是 {p.margin_mode} {p.leverage:g}×，不是设计的 {MARGIN_MODE} {LEVERAGE}×"
                )
        # The position the fills explain is what all booked fills add up to (the
        # account started flat), not the last position plus the new fills: a fill the
        # exchange reports late then settles the position taken from the exchange
        # without it, instead of counting on top of it.
        implied = ledger.net_fills()
        for f in fills:
            implied[f.inst] = implied.get(f.inst, 0.0) + f.qty
        reasons: list[tuple[str, str]] = []  # (key, text) of each reason to pause the account
        if manual:
            reasons.append((f"fill:{manual[0].bill_id}", "交易所里有不是程序下的成交：" + "；".join(
                f"{f.inst} {f.side} {f.contracts:g} 张 @ {f.price:,.2f}" for f in manual
            )))
        if unexplained:
            reasons.append((f"bill:{unexplained[0].bill_id}", "余额有成交和资金费以外的变动：" + "；".join(
                _bill_text(b) for b in unexplained
            )))
        holding: list[str] = []
        first_seen = ledger.get("mismatched") or {}
        mismatched: dict[str, int] = {}  # inst -> when a sync first found its position unexplained
        for inst in sorted(set(implied) | set(positions)):
            want = positions[inst].qty if inst in positions else 0.0
            have = implied.get(inst, 0.0)
            if abs(want - have) > 1e-9:
                text = f"账本与交易所持仓不一致：{inst} 账本推算 {have:+g}，交易所 {want:+g}，已按交易所为准"
                holding.append(text)
                mismatched[inst] = first_seen.get(inst, now_ms)
                if now_ms - mismatched[inst] >= MISMATCH_GRACE_MS:
                    reasons.append((f"position:{inst}", text))
                else:
                    problems.append(text)

        cash, equity = balance.cash, balance.equity
        cap = self.profile.max_equity
        if cap is not None and equity > cap:
            text = f"净值 {equity:,.2f} USDT 超过上限 {cap:,.0f} USDT"
            holding.append(text)
            reasons.append(("equity", text))
        paused = [text for key, text in reasons if self.pause(now_ms, text, key)]
        alerts += [self.profile.pause_alert(text) for text in paused]
        # While a bill nothing explains pauses the account, its equity measures nothing.
        unmeasured = any(r["key"].startswith("bill:") for r in self.pause_reasons)
        peak = ledger.get("peak") if unmeasured else max(ledger.get("peak"), equity)
        halted = ledger.get("halted")
        tripped = killed = False
        if (
            positions and not halted and not unmeasured
            and (drawdown := rules.drawdown(equity, peak)) >= KILL_DRAWDOWN
        ):
            if self.paused:
                # Closing changes the exchange: while paused, a person sees to it.
                problems.append(f"回撤已到熔断线 {KILL_DRAWDOWN:.0%}：账户暂停中，程序不平仓，请人工处理")
            else:
                self.halt(now_ms, f"回撤 {drawdown:.1%} 到了熔断线：净值 {equity:,.2f}，峰值 {peak:,.2f}")
                halted = tripped = True
        if halted:
            sent, stops, failed = self._flatten(now_ms, positions, stops)
            killed = bool(sent)
            if tripped:
                head = f"熔断：净值 {equity:,.2f} 比峰值 {peak:,.2f} 回撤 {drawdown:.1%}，停止交易"
            elif positions:
                head = f"熔断中：{'、'.join(positions)} 还有仓位"
            elif failed:
                head = "熔断中"
            else:
                head = "熔断后核实：交易所里已经空仓" if old else ""
            if head:
                closing = [f"已对 {'、'.join(sent)} 发出市价平仓"] if sent else []
                text = "；".join([head, *closing, *failed]) + "。" + (self.profile.after_kill if tripped else "")
                alerts.append(text)
                ledger.add_event(now_ms, "kill", text)
        elif self.paused:
            problems += [
                f"{inst} 有仓位没有止损单：账户暂停中，程序不补挂，请人工处理"
                for inst in positions if not any(s.inst == inst for s in stops)
            ]
        snapshots = [(m, equity) for m in _midnights(ledger.get("snapshot_to", since), now_ms)]
        ledger.commit(
            positions=positions, cash=cash, fills=fills, funding=funding, snapshots=snapshots,
            meta={
                "peak": peak, "halted": halted, "synced_to": now_ms, "snapshot_to": now_ms,
                "booked_bills": booked, "mismatched": mismatched, "equity": equity, "synced_at": now_ms,
                "problems": problems,
                "exchange_positions": {
                    inst: {"contracts": p.contracts, "avg_price": p.avg_price, "unrealized": p.unrealized,
                           "leverage": p.leverage, "margin_mode": p.margin_mode,
                           "liquidation_price": p.liquidation_price}
                    for inst, p in exchange.items()
                },
                "pending_stops": [
                    {"inst": s.inst, "side": s.side, "contracts": s.contracts, "trigger": s.trigger,
                     "client_id": s.client_id}
                    for s in stops
                ],
            },
        )
        return Sync(equity, cash, positions, stops, fills, problems, alerts, killed, paused, holding)

    def _flatten(
        self, now_ms: int, positions: dict[str, Position], stops: list[StopOrder]
    ) -> tuple[list[str], list[StopOrder], list[str]]:
        """Close at market each contract a halted account holds, each on its own, and
        cancel the stops of the contracts it no longer holds: a contract whose close
        fails keeps its stop until a sync finds it gone. This goes through the raw
        client, paused or not: the kill was tripped by a person, or by the drawdown of
        an account that was not paused (ADR 0010). Returns the contracts whose close was
        sent, the stops still pending and what failed."""
        sent, failed = [], []
        for inst in positions:
            try:
                self._private.close_position(inst, MARGIN_MODE, client_id=self._client_id(KILL_PREFIX, now_ms, inst))
                sent.append(inst)
            except REQUEST_ERRORS as exc:
                failed.append(f"{inst} 平仓失败（{_error(exc)}），止损单留着，下一次运行再平")
        loose = [s for s in stops if s.inst not in positions]
        pending = [s for s in stops if s.inst in positions]
        if loose:
            try:
                self._private.cancel_stops(loose)
            except REQUEST_ERRORS as exc:
                pending += loose
                failed.append(f"已平仓合约的 {len(loose)} 张止损单没撤掉（{_error(exc)}），下一次运行再撤")
        return sent, pending, failed

    def _reason(self, fill: ExchangeFill) -> str:
        """trade / stop / kill by the client id prefix; a stop's fill carries the algo's
        client id on its order rather than on the fill, so the order is looked up."""
        client_id = fill.client_id
        if not client_id:
            try:
                order = self.private.order(fill.inst, order_id=fill.order_id)
                client_id = order.algo_client_id or order.client_id
            except REQUEST_ERRORS:
                client_id = ""
        for prefix, reason in REASONS:
            if client_id.startswith(prefix):
                return reason
        return MANUAL

    def _funding_rate(self, inst: str, ts: int) -> float:
        """The rate that settled at ``ts`` (within a minute), from the public history; 0
        when OKX cannot say, since the bill already carries the amount."""
        try:
            events = self.okx.funding(inst, ts - 60_000, ts + 60_000)
        except REQUEST_ERRORS:
            return 0.0
        return min(events, key=lambda e: abs(e.ts - ts)).rate if events else 0.0

    # -- stops ----------------------------------------------------------------

    def manage_stops(
        self, now_ms: int, quotes: Quotes, stops: list[StopOrder], *, alerts: list[str] | None = None,
    ) -> tuple[list[str], list[str]]:
        """Tighten each position's stop to STOP_ATR_MULT ATRs from the last price (never
        loosen) and make the exchange's pending stops match: one reduce-only
        conditional order per position for its whole size at the ledger's stop; any
        other pending stop is cancelled. No position loses the stop it has on the way,
        and one whose stop cannot be made to stand is closed at market (``_keep_stop``).
        What fails for one contract is alerted and the others still get theirs; the
        ledger is committed whatever the exchange did. Marks the positions at the
        quotes. While halted only the ledger is updated.

        Returns the alerts and the contracts closed at market, whose fills the next
        sync books. The alerts are appended to ``alerts`` when it is given, so that
        the caller has them even when this raises."""
        ledger = self.ledger
        positions = ledger.positions()
        alerts = [] if alerts is None else alerts
        closed: list[str] = []
        for inst, pos in positions.items():
            if inst not in quotes:
                continue
            last, atr_value = quotes[inst]
            candidate = rules.initial_stop(last, pos.qty, atr_value, stop_mult=STOP_ATR_MULT)
            pos.stop = candidate if pos.stop is None else rules.tighten(pos.stop, candidate, pos.qty)
            pos.stop = self._tick(inst, pos.stop)
        marks = {inst: last for inst, (last, _) in quotes.items()}
        if not ledger.get("halted"):
            by_inst: dict[str, list[StopOrder]] = {}
            for s in stops:
                by_inst.setdefault(s.inst, []).append(s)
            for inst, own in by_inst.items():
                if inst not in positions:  # closed by a trade or a stop: its stop goes too
                    self._cancel(now_ms, inst, own, alerts, "已无持仓")
            for inst, pos in positions.items():
                contracts = self._contracts(pos.qty, inst)
                own = by_inst.get(inst, [])
                if pos.stop is None:  # no quote this run: nothing to place it at
                    if not any(_covers(s, contracts) for s in own):
                        self._alert(now_ms, "stop_failed", alerts, (
                            f"没有止损：{inst} {contracts:+g} 张没有覆盖全部仓位的止损单，"
                            "这次运行又没有它的报价，算不出止损价，请人工处理"
                        ))
                    continue
                last = quotes[inst][0] if inst in quotes else None
                if self._keep_stop(now_ms, inst, contracts, pos.stop, own, last, alerts):
                    closed.append(inst)
        ledger.commit(positions=positions, cash=ledger.get("cash"), meta={"marks": marks})
        return alerts, closed

    def _keep_stop(
        self, now_ms: int, inst: str, contracts: float, trigger: float,
        own: list[StopOrder], last: float | None, alerts: list[str],
    ) -> bool:
        """Leave the position of ``contracts`` in ``inst`` with one stop for all of it at
        ``trigger``, without a moment in which it has lost the stop it had; True when
        the position was closed at market instead.

        ``own`` are the stops pending for it. One that already matches stays and the
        others are cancelled. Otherwise, in this order:

        - a trigger the last price has already crossed is not sent to the exchange: the
          position is closed, as the paper account fills such a stop;
        - a single stop of our own on the closing side is amended in place;
        - when that fails, or there is none to amend (no stop, one on the other side
          or not ours, several), a new stop is placed beside what is there, and the
          others are cancelled only once it is read back as pending.

        After each request the pending stops are read again, and the next step follows
        what is there rather than what the answer said: a request that timed out is
        resent and may have gone through the first time. When the exchange refuses the
        trigger as already past the price, the position is closed. A position that
        still has a stop for its whole size keeps it, alerts, and is taken up again by
        the next run; one without is tried STOP_TRIES times, then closed. A request
        the exchange took but whose result cannot be read back is alerted and nothing
        more is done on its strength.
        """
        position = f"{inst} {contracts:+g} 张"

        def standing(pending: list[StopOrder]) -> list[StopOrder]:
            return [s for s in pending if self._matches(s, inst, contracts, trigger)]

        def unseen(done: str) -> bool:
            # The exchange took the request and then would not show its pending stops:
            # nothing is cancelled on the strength of an answer alone.
            self._alert(now_ms, "stop_failed", alerts, (
                f"止损待确认：{position}的止损 {trigger:,.2f} {done}，但读不回交易所的挂单来确认，"
                "别的止损单都没有动，下一次运行再核对"
            ))
            return False

        before = {s.algo_id for s in own}
        changed = not standing(own)
        if changed:
            if last is not None and rules.stop_fill(contracts, trigger, last, last, last) is not None:
                return self._close(now_ms, inst, alerts, (
                    f"{position}的止损价 {trigger:,.2f} 已被现价 {last:,.2f} 穿越，交易所里没有这张止损单"
                ))
            error: Exception | None = None
            # Only a stop of our own is amended: its fill is told by its client id.
            if len(own) == 1 and _reduces(own[0], contracts) and own[0].client_id.startswith(STOP_PREFIX):
                try:
                    self.private.amend_stop(own[0], contracts, trigger)
                except REQUEST_ERRORS as exc:
                    error = exc
                seen = self._pending(inst)
                if seen is None and error is None:
                    return unseen(f"已改单（{own[0].client_id}）")
                own = own if seen is None else seen
            client_id = ""
            for attempt in range(STOP_TRIES):
                if standing(own) or _trigger_passed(error):
                    break
                if attempt and any(_covers(s, contracts) for s in own):
                    break  # still covered by the stop it had: the next run tries again
                if attempt:
                    self.sleep(STOP_RETRY_SECONDS)
                client_id = client_id or self._client_id(STOP_PREFIX, now_ms, inst)
                try:
                    self.private.place_stop(inst, contracts, trigger, client_id, margin_mode=MARGIN_MODE)
                    error = None
                except REQUEST_ERRORS as exc:
                    error = exc
                seen = self._pending(inst)
                if seen is None and error is None:
                    return unseen(f"已下单（{client_id}）")
                own = own if seen is None else seen
            if not standing(own):
                reason = error or "下单的应答是成功，挂单里却没有"
                if _trigger_passed(error):
                    return self._close(now_ms, inst, alerts, (
                        f"{position}的止损 {trigger:,.2f} 被交易所拒绝，触发价已在现价另一侧（{reason}）"
                    ))
                covering = [s for s in own if _covers(s, contracts)]
                if covering:
                    self._alert(now_ms, "stop_failed", alerts, (
                        f"止损没更新：{position}的止损没能改到 {trigger:,.2f}（{reason}），"
                        f"交易所里仍是 {covering[0].trigger:,.2f} 的旧止损单，下一次运行再试"
                    ))
                    return False
                return self._close(now_ms, inst, alerts, (
                    f"{position}试了 {STOP_TRIES} 次都没挂上止损（{reason}）"
                ))
        kept = standing(own)[0]
        if changed:
            verb = "止损改到" if kept.algo_id in before else "止损"
            self.ledger.add_event(
                now_ms, "stop", f"{inst} {verb} {trigger:,.2f}（{abs(contracts):g} 张，{kept.client_id}）"
            )
        rest = [s for s in own if s.algo_id != kept.algo_id]
        if rest:
            self._cancel(now_ms, inst, rest, alerts, "止损已到位")
        return False

    def _pending(self, inst: str) -> list[StopOrder] | None:
        """The stops pending for ``inst`` right now; None when the exchange cannot be read."""
        try:
            return [s for s in self.private.pending_stops() if s.inst == inst]
        except REQUEST_ERRORS:
            return None

    def _cancel(self, now_ms: int, inst: str, stops: list[StopOrder], alerts: list[str], why: str) -> None:
        """Cancel pending stops ``inst`` no longer needs (``why``). One that will not go
        is alerted and left to the next run."""
        try:
            self.private.cancel_stops(stops)
        except REQUEST_ERRORS as exc:
            seen = self._pending(inst)
            unwanted = {s.algo_id for s in stops}
            if seen is None or any(s.algo_id in unwanted for s in seen):
                self._alert(now_ms, "stop_failed", alerts, (
                    f"止损单没撤掉：{inst} {why}，{len(stops)} 张多余的止损单没撤掉（{exc}），下一次运行再撤"
                ))
                return
        self.ledger.add_event(now_ms, "stop_cancelled", f"{inst} {why}，撤掉 {len(stops)} 张止损单")

    def _close(self, now_ms: int, inst: str, alerts: list[str], why: str) -> bool:
        """Close the position of ``inst`` at market because its stop cannot stand
        (``why``, which names the position); True once it is closed. The closing order
        carries a stop's client id, so the sync that books its fill reads it as a stop.
        It is tried STOP_TRIES times; when it still fails and the position is still
        there, the alert says so and the next run takes the position up again."""
        client_id = self._client_id(STOP_PREFIX, now_ms, inst)
        error: Exception | None = None
        for attempt in range(STOP_TRIES):
            if attempt:
                self.sleep(STOP_RETRY_SECONDS)
            try:
                self.private.close_position(inst, MARGIN_MODE, client_id=client_id)
                error = None
                break
            except REQUEST_ERRORS as exc:
                error = exc
        if error is not None:
            try:
                held = any(p.inst == inst for p in self.private.positions())
            except REQUEST_ERRORS:
                held = True
            if held:
                self._alert(now_ms, "stop_failed", alerts, (
                    f"紧急：{why}，市价平仓也失败（{error}），请立即人工处理；下一次运行会再试"
                ))
                return False
        self._alert(now_ms, "stop_closed", alerts, f"止损平仓：{why}，已市价平仓（{client_id}）")
        return True

    def _alert(self, now_ms: int, kind: str, alerts: list[str], text: str) -> None:
        alerts.append(text)
        self.ledger.add_event(now_ms, kind, text)

    def _matches(self, stop: StopOrder, inst: str, contracts: float, trigger: float) -> bool:
        tick = self.spec(inst).tick_size
        return _covers(stop, contracts) and abs(stop.trigger - trigger) <= (tick / 2 if tick else 1e-9)

    def protect(
        self, now_ms: int, quotes: Quotes, desired: dict[str, float | None], alerts: list[str],
    ) -> None:
        """The last line once a step after the hour's orders has raised: every position
        on the exchange still gets its stop or is closed, as ``manage_stops`` does it,
        without waiting for a sync, which is among what can have failed. The positions
        are read straight from the exchange into the ledger, each with the stop its
        trade set (``desired``) or the one it had; the fills behind them are the next
        sync's to book. The exchange is read up to STOP_TRIES times, as a stop is
        placed. Never raises: when it cannot do its work, the alert, kept among the
        events too, names the contracts that may be without a stop."""
        try:
            old = self.ledger.positions()
            positions: dict[str, Position] = {}
            for p in self._read(self.private.positions):
                qty = round(p.contracts * self.spec(p.inst).contract_value, 12)
                kept = old[p.inst].stop if p.inst in old and (old[p.inst].qty > 0) == (qty > 0) else None
                positions[p.inst] = Position(qty, p.avg_price, desired.get(p.inst, kept))
            self.ledger.commit(positions=positions, cash=self.ledger.get("cash"))
            self.manage_stops(now_ms, quotes, self._read(self.private.pending_stops), alerts=alerts)
        except Exception as exc:
            text = (
                f"紧急：下单之后出了错，补挂止损这一步也没做成（{type(exc).__name__}: {exc}），"
                f"{'、'.join(self.instruments(desired))} 的仓位可能没有止损，请立即人工检查"
            )
            alerts.append(text)
            with suppress(Exception):  # the ledger may be what failed
                self.ledger.add_event(now_ms, "stop_failed", text)

    def _read(self, read: Callable[[], list]) -> list:
        """``read()`` of the exchange, tried STOP_TRIES times while it does not answer."""
        for _ in range(STOP_TRIES - 1):
            try:
                return read()
            except REQUEST_ERRORS:
                self.sleep(STOP_RETRY_SECONDS)
        return read()

    # -- execution ------------------------------------------------------------

    def plan(self, signals: dict[str, str | None], equity: float, quotes: Quotes) -> list[Planned]:
        """The orders that take each contract toward the target its signal sets, as
        ``IntradayPaper.execute`` sizes it against ``equity`` and the ledger's positions,
        in watchlist order; none for a halted account. A contract without a quote
        (``quotes`` left it out) is not traded: its position is held, and counts toward
        the gross cap at its entry price. Only reads.

        An order that only reduces a position is never refused. Any other is refused
        when the position it leaves is over MAX_COIN_EXPOSURE of equity, which the rules
        never size, so the sizing went wrong, or over the profile's ``max_position``. A
        flip is judged by the position it opens, not by the size of the order, which
        also closes the old one."""
        if self.ledger.get("halted"):
            return []
        positions = self.ledger.positions()
        units, currents, targets = {}, {}, {}
        for coin in self.watchlist:
            pos = positions.get(coin.swap)
            if coin.swap not in quotes:
                currents[coin.swap] = targets[coin.swap] = pos.qty * pos.entry if pos else 0.0
                continue
            price, atr_value = quotes[coin.swap]
            currents[coin.swap] = pos.qty * price if pos else 0.0
            units[coin.swap] = rules.unit_notional(
                equity, atr_value, price, risk=RISK_PER_UNIT, stop_mult=STOP_ATR_MULT
            )
            targets[coin.swap] = rules.target_notional(
                signals.get(coin.research), units[coin.swap], currents[coin.swap], weights=WEIGHTS
            )
        targets = rules.apply_caps(targets, currents, equity)
        planned = []
        for coin in self.watchlist:
            inst = coin.swap
            if inst not in quotes:
                continue
            flatten = signals.get(coin.research) == "Flat" and inst in positions
            if not flatten and not rules.needs_trade(
                targets[inst], currents[inst], units[inst], threshold=REBALANCE_THRESHOLD
            ):
                continue
            price, atr_value = quotes[inst]
            spec = self.spec(inst)
            new_qty = rules.to_quantity(
                targets[inst], price, spec.contract_value, spec.lot_size, spec.min_size
            )
            old_qty = positions[inst].qty if inst in positions else 0.0
            if new_qty == old_qty:
                continue
            delta = round(new_qty - old_qty, 12)
            planned.append(Planned(
                inst, signals.get(coin.research), old_qty, new_qty, self._contracts(delta, inst),
                price, atr_value, self._refusal(inst, old_qty, new_qty, price, equity),
            ))
        return planned

    def _refusal(
        self, inst: str, old_qty: float, new_qty: float, price: float, equity: float,
    ) -> str | None:
        """Why the order taking ``inst`` from ``old_qty`` to ``new_qty`` must not be sent
        (``plan``); None when it may be."""
        if old_qty * new_qty >= 0 and abs(new_qty) < abs(old_qty):
            return None
        after = abs(new_qty) * price
        head = f"拒绝下单：{inst} 变动 {round(new_qty - old_qty, 12):+g}，成交后名义 {after:,.0f} USDT"
        if after > MAX_COIN_EXPOSURE * equity * (1 + ROUNDING):
            return f"{head}，超过净值 {equity:,.0f} 的 {MAX_COIN_EXPOSURE:g} 倍，可能是算错了"
        cap = self.profile.max_position
        if cap is not None and after > cap:
            return f"{head}，超过单币上限 {cap:,.0f} USDT"
        return None

    def execute(
        self, hour: int, signals: dict[str, str | None], now_ms: int, equity: float, quotes: Quotes,
        *, alerts: list[str] | None = None, desired: dict[str, float | None] | None = None,
    ) -> tuple[list[str], dict[str, float | None]]:
        """Send the hour's orders (``plan``) to the exchange as market orders; return the
        alerts and the stop each traded position should have (for the sync that follows).

        ``equity`` and the ledger's positions are the sync's just before. A refused order
        is alerted and not sent. The order's client id is the hour's: a rerun finds it
        already placed and only reads it back. An order not filled within ORDER_POLLS
        looks is left to the next sync. The first execution starts the validation
        period and fixes the baseline, as the paper accounts do.

        ``alerts`` and ``desired``, when given, are what is filled and returned: a
        caller that passes its own still has the alerts raised and the stops of the
        orders filled so far when a later order raises.
        """
        ledger = self.ledger
        alerts = [] if alerts is None else alerts
        desired = {} if desired is None else desired
        if ledger.get("halted"):
            return alerts, desired
        positions = ledger.positions()
        for planned in self.plan(signals, equity, quotes):
            inst, contracts = planned.inst, planned.contracts
            if planned.refused:
                alerts.append(planned.refused)
                ledger.add_event(now_ms, "order_refused", planned.refused)
                continue
            client_id = f"{TRADE_PREFIX}{hour // HOUR_MS}{_tag(inst)}"
            try:
                self.private.place_market(
                    inst, contracts, client_id, reduce_only=planned.new_qty == 0, margin_mode=MARGIN_MODE
                )
            except OKXPrivateError as exc:
                if exc.code != DUPLICATE_CLIENT_ID:
                    text = f"下单失败：{inst} {contracts:+g} 张：{exc}"
                    alerts.append(text)
                    ledger.add_event(now_ms, "order_failed", text)
                    continue
                logger.info("order %s was already placed; reading it back", client_id)
            order = self._await_fill(inst, client_id)
            if order is None:
                text = f"订单未成交：{inst} {client_id} 在 {ORDER_POLLS * ORDER_POLL_SECONDS:g} 秒内没有成交，以下次对账为准"
                alerts.append(text)
                ledger.add_event(now_ms, "order_pending", text)
                continue
            fill_price = order.avg_price or planned.price
            old_stop = positions[inst].stop if inst in positions else None
            desired[inst] = _stop_after(planned.old_qty, planned.new_qty, old_stop, fill_price, planned.atr)
            ledger.add_event(now_ms, "order", f"{inst} {contracts:+g} 张 @ {fill_price:,.2f}（{client_id}）")
        if ledger.get("validation_start") is None:
            # The validation period starts with this UTC day, the baseline buys at the
            # spot closes of the day before, as the paper accounts do.
            day_start = now_ms - now_ms % DAY_MS
            ledger.commit(
                positions=positions, cash=ledger.get("cash"), snapshots=[(day_start, equity)],
                meta={
                    "validation_start": day_start,
                    "baseline_ref": {
                        coin.research:
                            self.okx.bars(coin.spot, "1Dutc", day_start - DAY_MS, day_start)[-1].close
                        for coin in self.watchlist
                    },
                },
            )
        return alerts, desired

    def _await_fill(self, inst: str, client_id: str):
        """The order once filled; None when cancelled or still open after ORDER_POLLS looks."""
        for i in range(ORDER_POLLS):
            if i:
                self.sleep(ORDER_POLL_SECONDS)
            try:
                order = self.private.order(inst, client_id=client_id)
            except OKXPrivateError as exc:
                if exc.code == "51603":  # not visible yet
                    continue
                raise
            if order.state == "filled":
                return order
            if order.state in ("canceled", "mmp_canceled"):
                return None
        return None

    def resume(self, now_ms: int) -> None:
        """Lift a halt. The account is flat, so the peak restarts at its cash."""
        cash = self.ledger.get("cash")
        self.ledger.commit(
            positions=self.ledger.positions(), cash=cash, meta={"halted": False, "peak": cash}
        )
        self.ledger.add_event(now_ms, "resume", f"熔断解除，峰值重置为 {cash:,.2f}")

    # -- helpers --------------------------------------------------------------

    def _contracts(self, qty: float, inst: str) -> float:
        """Signed contract count of a coin quantity."""
        return round(qty / self.spec(inst).contract_value, 8)

    def _tick(self, inst: str, price: float) -> float:
        tick = self.spec(inst).tick_size
        return round(round(price / tick) * tick, 10) if tick else price

    def _client_id(self, prefix: str, now_ms: int, inst: str) -> str:
        self._seq += 1
        return f"{prefix}{now_ms // 1000}{_tag(inst)}{self._seq}"


def _error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:200]


def _bill_text(bill: Bill) -> str:
    """A bill nothing explains, as the pause it causes names it."""
    what = {"11": "转入", "12": "转出"}.get(bill.sub_type) if bill.type == TRANSFER_BILL else None
    what = what or f"账单类型 {bill.type}（子类型 {bill.sub_type}）"
    return f"{bill.inst} {what}".strip() + f" {bill.amount:+,.2f} USDT"


def _fired_text(inst: str, legs: list[tuple[float, Fill]], held: Position | None) -> str:
    """The alert of the stop of ``inst`` that fired on the exchange, from its fills
    (contracts, the fill booked): what it traded at what average price and, from the
    entry of the position the ledger held (``held``), what that made after the fees."""
    contracts = sum(c for c, _ in legs)
    qty = sum(f.qty for _, f in legs)
    price = sum(f.qty * f.price for _, f in legs) / qty
    fee = sum(f.fee for _, f in legs)
    text = f"止损成交：{inst} {'卖出' if qty < 0 else '买入'} {contracts:g} 张 @ {price:,.2f}"
    if held is None or (held.qty > 0) == (qty > 0):
        return text + "，账本里没有它平掉的仓位，算不出盈亏"
    pnl = -qty * (price - held.entry) - fee
    return text + f"，盈亏 {pnl:+,.2f} USDT（开仓均价 {held.entry:,.2f}，含手续费 {fee:,.2f}）"


def _stop_after(old_qty: float, new_qty: float, old_stop: float | None, fill_price: float, atr_value: float):
    """``rules.stop_after_trade`` with the intraday multiple; a position that somehow
    had no stop gets a fresh one."""
    if new_qty != 0 and old_stop is None and old_qty != 0 and (old_qty > 0) == (new_qty > 0):
        return rules.initial_stop(fill_price, new_qty, atr_value, stop_mult=STOP_ATR_MULT)
    return rules.stop_after_trade(old_qty, new_qty, old_stop, fill_price, atr_value, stop_mult=STOP_ATR_MULT)


def _reduces(stop: StopOrder, contracts: float) -> bool:
    """Whether a pending stop can only close a position of ``contracts`` (signed):
    reduce-only, on the side that sells a long or buys back a short."""
    return stop.reduce_only and stop.side == ("sell" if contracts > 0 else "buy")


def _covers(stop: StopOrder, contracts: float) -> bool:
    """Whether a pending stop closes the whole position of ``contracts``, wherever its
    trigger is."""
    return _reduces(stop, contracts) and abs(stop.contracts - abs(contracts)) < 1e-9


def _trigger_passed(error: Exception | None) -> bool:
    """Whether the exchange refused a stop because the price is already past its trigger."""
    return isinstance(error, OKXPrivateError) and error.code in TRIGGER_PASSED


def _tag(inst: str) -> str:
    """The coin part of an instrument id, for client order ids: BTC-USDT-SWAP -> btc."""
    return inst.split("-")[0].lower()
