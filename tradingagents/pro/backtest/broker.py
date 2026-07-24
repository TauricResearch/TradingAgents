"""SimBroker: position lifecycle against replayed bars.

Conservative intrabar policy: when a bar's range touches both the stop and
a take-profit, the stop is assumed to fill first (pessimistic for the
strategy). Take-profit ladders close fractions of the original quantity at
their levels; a stop closes the entire remainder. Fills embed slippage;
commissions are charged per fill on both sides.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from tradingagents.contracts import OHLCVBar, TradeAction, TradeRecommendation
from tradingagents.pro.backtest.costs import CommissionModel, LiquidityModel, SlippageModel

# max bars retained per symbol for ATR/chandelier trailing — bounds memory even
# for a long run; a trailing period beyond this is clamped to what's retained
_TRAIL_WINDOW_MAX = 512


def _participation(quantity: float, bar_volume: float) -> float:
    """Order size as a fraction of the bar's traded volume — the market-impact
    input for the slippage model. 0 when volume is unknown/zero."""
    return quantity / bar_volume if bar_volume and bar_volume > 0 else 0.0


@dataclass
class ClosedTrade:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float  # size-weighted across partial exits
    opened_at: datetime
    closed_at: datetime
    pnl: float  # net of commissions and slippage
    reason: str  # "stop" | "take_profit" | "breakeven" | "end_of_data"
    recommendation_id: str
    # R accounting: risk unit = original quantity × |entry - initial stop|
    initial_stop: float | None = None
    r_multiple: float | None = None  # realized pnl in R units
    planned_rr: float | None = None  # the ticket's size-weighted R:R


@dataclass
class _OpenPosition:
    # identity carried directly (not a TradeRecommendation) so a position can
    # be opened from either a recommendation OR a bare order-book fill (T2).
    symbol: str
    recommendation_id: str  # id that keys the position + joins memory/artifacts
    side: str
    quantity: float  # remaining
    original_quantity: float
    entry_price: float
    stop: float
    tp_levels: list[tuple[float, float]]  # (price, fraction of original) unfilled
    opened_at: datetime
    entry_commission: float
    planned_rr: float | None = None  # ticket's size-weighted R:R (for reporting)
    initial_stop: float = 0.0  # R unit; never mutated (stop may move to BE)
    at_breakeven: bool = False
    trailing_mode: str | None = None  # None | "pct" | "atr" | "chandelier"
    trailing_mult: float | None = None
    trailing_period: int | None = None  # ATR/chandelier lookback (bars)
    extreme: float | None = None  # best price seen since entry (trailing anchor)
    realized: float = 0.0
    exit_notional: float = 0.0
    exit_quantity: float = 0.0
    last_reason: str = ""


@dataclass
class PendingOrder:
    """A resting order in the book (track T2). Submitted on a decision bar and
    matched against subsequent bars until it fills, expires, or is cancelled.
    Entry orders carry their bracket (protective stop + take-profit ladder) so
    the same geometry attaches on fill that ``open_from_recommendation`` builds
    for the recommendation path."""

    id: str
    kind: str  # market | limit | stop_entry | stop_limit
    side: str  # BUY | SELL
    quantity: float
    limit_price: float | None = None
    stop_price: float | None = None
    stop_loss: float | None = None  # bracket: protective stop attached on fill
    take_profits: list[tuple[float, float]] = field(default_factory=list)
    trailing_mode: str | None = None  # None | "pct" | "atr" | "chandelier"
    trailing_mult: float | None = None  # % of extreme (pct) or ATR multiple
    trailing_period: int | None = None  # ATR/chandelier lookback (bars)
    planned_rr: float | None = None
    symbol: str = ""
    expires_after: int | None = None  # bars from submit; None = rest all run
    submitted_index: int = 0
    tag: str = ""
    state: str = "WORKING"  # WORKING | FILLED | CANCELLED | EXPIRED
    triggered: bool = False  # stop_limit: stop touched, now a resting limit
    reduce_only: bool = False  # only reduces/closes opposing same-symbol size,
    #                            never opens or flips (track T2 risk realism)


@dataclass
class SimBroker:
    """Holds up to ``max_open_positions`` concurrent positions in one symbol,
    each with its own stop + take-profit ladder. New entries are refused once
    the count cap or the aggregate gross-exposure cap (``max_gross_exposure_pct``
    of equity) is reached — so N fixed-fractional positions can't silently
    stack to N× exposure. Positions are keyed by recommendation id."""

    initial_equity: float = 100_000.0
    slippage: SlippageModel = field(default_factory=SlippageModel)
    commission: CommissionModel = field(default_factory=CommissionModel)
    liquidity: LiquidityModel = field(default_factory=LiquidityModel)
    max_open_positions: int = 3
    max_gross_exposure_pct: float = 30.0
    max_same_direction: int = 2
    # after the first take-profit rung fills, move the stop to entry plus a
    # small cost buffer: a trade that reached +1R can no longer become a
    # loss (exit reason "breakeven"). The buffer covers round-trip costs so
    # a breakeven exit nets ~0 instead of a costs-sized loss.
    breakeven_after_tp1: bool = True
    breakeven_buffer_pct: float = 0.0006

    def __post_init__(self):
        self.cash_pnl = 0.0  # realized pnl net of costs
        self.positions: dict[str, _OpenPosition] = {}
        self.closed: list[ClosedTrade] = []
        self.pending: dict[str, PendingOrder] = {}  # order book (T2)
        self._orders: dict[str, dict] = {}  # id -> lifecycle record (artifact)
        # per-symbol trailing-bar window, populated ONLY while an ATR/chandelier
        # position is open (the pct/none path never allocates → byte-identical)
        self._trail_bars: dict[str, deque] = {}

    @property
    def order_log(self) -> list[dict]:
        """Every order the book has seen, with its final disposition — the
        source for the per-run ``orders`` artifact (empty on the
        recommendation path, which never touches the book)."""
        return list(self._orders.values())

    def _record_order(self, order: PendingOrder, **updates) -> None:
        rec = self._orders.get(order.id)
        if rec is None:
            rec = {
                "id": order.id, "kind": order.kind, "side": order.side,
                "quantity": order.quantity, "limit_price": order.limit_price,
                "stop_price": order.stop_price, "stop_loss": order.stop_loss,
                "submitted_index": order.submitted_index, "tag": order.tag,
                "state": order.state, "fill_price": None, "filled_index": None,
            }
            self._orders[order.id] = rec
        rec.update(updates)

    # --- equity ---------------------------------------------------------------

    def equity(self, mark_price: float | None = None) -> float:
        value = self.initial_equity + self.cash_pnl
        if mark_price is not None:
            for pos in self.positions.values():
                sign = 1 if pos.side == "BUY" else -1
                value += sign * (mark_price - pos.entry_price) * pos.quantity
        return value

    def equity_marks(self, marks: dict[str, float]) -> float:
        """Portfolio equity: every open position marked at its OWN symbol's
        price (``marks[symbol]``); a symbol absent from ``marks`` is held at
        entry (zero unrealized). Foundation for the multi-symbol engine — the
        single-symbol ``equity(mark_price)`` above is unchanged."""
        value = self.initial_equity + self.cash_pnl
        for pos in self.positions.values():
            mark = marks.get(pos.symbol, pos.entry_price)
            sign = 1 if pos.side == "BUY" else -1
            value += sign * (mark - pos.entry_price) * pos.quantity
        return value

    def gross_notional_marks(self, marks: dict[str, float]) -> float:
        """Aggregate open exposure across symbols, each marked at its own
        price — the portfolio-heat input for the multi-symbol allocator."""
        return sum(marks.get(p.symbol, p.entry_price) * p.quantity
                   for p in self.positions.values())

    def accrue_funding(self, funding, marks: dict[str, float], hours: float) -> float:
        """Charge/credit perp funding on every open position for ``hours`` of
        holding, each marked at its symbol's price. Returns the net cash delta
        (also applied to ``cash_pnl``). Opt-in via a FundingModel; a spot
        backtest never calls this."""
        total = 0.0
        for pos in self.positions.values():
            mark = marks.get(pos.symbol, pos.entry_price)
            total += funding.cash_delta(mark * pos.quantity, pos.side, hours)
        self.cash_pnl += total
        return total

    @property
    def position_open(self) -> bool:
        return bool(self.positions)

    @property
    def open_count(self) -> int:
        return len(self.positions)

    def _gross_notional(self, mark_price: float) -> float:
        """Aggregate open exposure at ``mark_price`` (single symbol)."""
        return sum(mark_price * pos.quantity for pos in self.positions.values())

    # --- entries ----------------------------------------------------------------

    def open_from_recommendation(
        self, rec: TradeRecommendation, fill_bar: OHLCVBar
    ) -> str | None:
        """Open at the fill bar's open (the bar after the decision), with
        slippage, commission, and the participation cap. Returns None on
        success, else a rejection reason: ``max_open_positions`` (count cap),
        ``exposure_cap`` (aggregate gross exposure would exceed the limit), or
        ``liquidity`` (participation caps the order to nothing)."""
        if rec.action is TradeAction.HOLD:
            raise ValueError("cannot open a HOLD recommendation")
        if len(self.positions) >= self.max_open_positions:
            return "max_open_positions"
        side = rec.action.value
        if sum(1 for p in self.positions.values() if p.side == side) >= self.max_same_direction:
            return "same_direction_cap"
        quantity = self.liquidity.cap_quantity(rec.position_size.quantity, fill_bar.volume)
        if quantity <= 0:
            return "liquidity"
        mark = fill_bar.open
        equity = self.equity(mark_price=mark)
        prospective_gross = self._gross_notional(mark) + mark * quantity
        if equity > 0 and prospective_gross > (self.max_gross_exposure_pct / 100.0) * equity:
            return "exposure_cap"
        entry = self.slippage.fill_price_at(
            fill_bar.open, side, _participation(quantity, fill_bar.volume))
        fee = self.commission.cost(quantity, entry)
        self.positions[rec.id] = _OpenPosition(
            symbol=rec.symbol,
            recommendation_id=rec.id,
            planned_rr=rec.risk_reward,
            side=side,
            quantity=quantity,
            original_quantity=quantity,
            entry_price=entry,
            stop=rec.stop_loss,
            initial_stop=rec.stop_loss,
            tp_levels=[(tp.price, tp.size_fraction) for tp in rec.take_profits],
            opened_at=fill_bar.start,
            entry_commission=fee,
        )
        self.cash_pnl -= fee
        return None

    # --- pending-order book (T2) --------------------------------------------------

    def submit(self, order: PendingOrder) -> None:
        """Add a resting order to the book (matched from the next bar on)."""
        self.pending[order.id] = order
        self._record_order(order)

    def cancel(self, order_id: str) -> bool:
        """Cancel a working order; returns True if one was cancelled."""
        order = self.pending.pop(order_id, None)
        if order is None:
            return False
        order.state = "CANCELLED"
        self._record_order(order, state="CANCELLED")
        return True

    def match_pending(self, bar: OHLCVBar, index: int,
                      symbol: str | None = None) -> list[str]:
        """Match working orders against one bar, opening a position for each
        fill. Returns the filled order ids. Conservative intrabar policy,
        consistent with ``_manage``: a limit fills no better than its price
        unless the bar opened through it; a stop-entry that gaps through fills
        at the open (pessimistic). Terminal orders leave the book. ``symbol``
        restricts matching to that symbol's orders (the multi-symbol engine
        matches each symbol against its own bar); ``None`` matches all,
        byte-identical to the single-symbol path."""
        filled: list[str] = []
        for order in list(self.pending.values()):
            if order.state != "WORKING":
                continue
            if symbol is not None and order.symbol != symbol:
                continue
            raw = self._fill_price(order, bar)
            if raw is None:
                if (order.expires_after is not None
                        and index - order.submitted_index >= order.expires_after):
                    order.state = "EXPIRED"
                    self._record_order(order, state="EXPIRED")
                    self.pending.pop(order.id, None)
                continue
            reason = (self._reduce_from_fill(order, raw, bar) if order.reduce_only
                      else self._open_from_fill(order, raw, bar))
            if reason is None:
                order.state = "FILLED"
                # a reduce_only fill opens no position under order.id, so record
                # the reference fill level; an entry records its opened price
                fill_price = (raw if order.reduce_only
                              else self.positions[order.id].entry_price)
                self._record_order(
                    order, state="FILLED", filled_index=index,
                    fill_price=fill_price)
                filled.append(order.id)
            else:
                # a real fill level but a cap/parameter blocked the open — don't
                # let the order retry forever; drop it (rejection is terminal)
                order.state = "CANCELLED"
                self._record_order(order, state=f"rejected:{reason}")
            self.pending.pop(order.id, None)
        return filled

    def _fill_price(self, order: PendingOrder, bar: OHLCVBar) -> float | None:
        """Pre-slippage fill level for one order against a bar, or None if it
        does not trigger this bar."""
        long = order.side == "BUY"
        kind = order.kind
        if kind == "market":
            return bar.open
        if kind == "limit":
            if long and bar.low <= order.limit_price:
                return min(order.limit_price, bar.open)
            if not long and bar.high >= order.limit_price:
                return max(order.limit_price, bar.open)
            return None
        if kind == "stop_limit":
            if not order.triggered:
                hit = (bar.high >= order.stop_price if long
                       else bar.low <= order.stop_price)
                if not hit:
                    return None
                order.triggered = True  # becomes a resting limit from here
            # fill AT the limit when it lies within the bar's traded range —
            # no open-based improvement: the intrabar trigger time is unknown,
            # so we cannot assume the open (which may precede it) was fillable
            if bar.low <= order.limit_price <= bar.high:
                return order.limit_price
            return None
        if kind == "stop_entry":
            if long and bar.high >= order.stop_price:
                return max(order.stop_price, bar.open)  # gap-through → open
            if not long and bar.low <= order.stop_price:
                return min(order.stop_price, bar.open)
            return None
        return None

    def _open_from_fill(
        self, order: PendingOrder, raw_price: float, bar: OHLCVBar
    ) -> str | None:
        """Open a position from a filled order, applying the same caps/costs as
        the recommendation path. Returns None on success or a rejection reason.
        Entry orders must carry a protective stop (this engine is stop-based)."""
        if order.stop_loss is None:
            return "no_stop"
        if len(self.positions) >= self.max_open_positions:
            return "max_open_positions"
        if sum(1 for p in self.positions.values()
               if p.side == order.side) >= self.max_same_direction:
            return "same_direction_cap"
        quantity = self.liquidity.cap_quantity(order.quantity, bar.volume)
        if quantity <= 0:
            return "liquidity"
        equity = self.equity(mark_price=raw_price)
        prospective_gross = self._gross_notional(raw_price) + raw_price * quantity
        if equity > 0 and prospective_gross > (self.max_gross_exposure_pct / 100.0) * equity:
            return "exposure_cap"
        entry = self.slippage.fill_price_at(
            raw_price, order.side, _participation(quantity, bar.volume))
        fee = self.commission.cost(quantity, entry)
        self.positions[order.id] = _OpenPosition(
            symbol=order.symbol,
            recommendation_id=order.id,
            planned_rr=order.planned_rr,
            side=order.side,
            quantity=quantity,
            original_quantity=quantity,
            entry_price=entry,
            stop=order.stop_loss,
            initial_stop=order.stop_loss,
            tp_levels=list(order.take_profits),
            opened_at=bar.start,
            entry_commission=fee,
            trailing_mode=order.trailing_mode,
            trailing_mult=order.trailing_mult,
            trailing_period=order.trailing_period,
            extreme=entry,
        )
        self.cash_pnl -= fee
        return None

    def _reduce_from_fill(
        self, order: PendingOrder, raw_price: float, bar: OHLCVBar
    ) -> str | None:
        """Apply a reduce-only fill: close opposing same-symbol quantity (a SELL
        reduces longs, a BUY reduces shorts), capped at the order quantity so it
        can only shrink exposure — never open a new position or flip to the
        other side. Returns None on success, or a reason when there is nothing
        to reduce. Positions are reduced in insertion order (deterministic)."""
        opposing_side = "BUY" if order.side == "SELL" else "SELL"
        targets = [p for p in self.positions.values()
                   if p.symbol == order.symbol and p.side == opposing_side]
        if not targets:
            return "reduce_only_no_position"
        exit_price = self.slippage.fill_price_at(
            raw_price, order.side, _participation(order.quantity, bar.volume))
        remaining = order.quantity
        for pos in targets:
            if remaining <= 0:
                break
            qty = min(remaining, pos.quantity)
            self._exit(pos, qty, exit_price, bar.start, "reduce_only")
            remaining -= qty
            if pos.quantity <= 1e-12:
                self._finalize(pos, bar.start)
        return None

    # --- bar processing -----------------------------------------------------------

    def process_bar(self, bar: OHLCVBar, symbol: str | None = None) -> list[ClosedTrade]:
        """Manage open positions against one bar; returns the trades that fully
        closed on this bar (may be empty). ``symbol`` restricts management to
        that symbol's positions — the multi-symbol engine calls it once per
        symbol with that symbol's bar, so a position is only ever managed
        against its own instrument. ``None`` (single-symbol default) manages
        every position, byte-identical to before."""
        self._feed_trailing_window(bar, symbol)
        closed: list[ClosedTrade] = []
        for pos in list(self.positions.values()):
            if symbol is not None and pos.symbol != symbol:
                continue
            trade = self._manage(pos, bar)
            if trade is not None:
                closed.append(trade)
        return closed

    def _feed_trailing_window(self, bar: OHLCVBar, symbol: str | None) -> None:
        """Append this bar to the trailing window of each symbol that has an
        open ATR/chandelier position. No such position → nothing is stored, so
        the pct/none path is byte-identical to before."""
        symbols = {p.symbol for p in self.positions.values()
                   if (symbol is None or p.symbol == symbol)
                   and p.trailing_mode in ("atr", "chandelier")}
        for sym in symbols:
            window = self._trail_bars.setdefault(
                sym, deque(maxlen=_TRAIL_WINDOW_MAX))
            window.append(bar)

    def _manage(self, pos: _OpenPosition, bar: OHLCVBar) -> ClosedTrade | None:
        long = pos.side == "BUY"
        stop_hit = bar.low <= pos.stop if long else bar.high >= pos.stop
        if stop_hit:
            exit_price = self.slippage.fill_price_at(
                pos.stop, "SELL" if long else "BUY",
                _participation(pos.quantity, bar.volume))
            reason = "breakeven" if pos.at_breakeven else "stop"
            self._exit(pos, pos.quantity, exit_price, bar.start, reason)
            return self._finalize(pos, bar.start)

        for price, fraction in list(pos.tp_levels):
            tp_hit = bar.high >= price if long else bar.low <= price
            if not tp_hit:
                continue
            close_quantity = min(fraction * pos.original_quantity, pos.quantity)
            exit_price = self.slippage.fill_price_at(
                price, "SELL" if long else "BUY",
                _participation(close_quantity, bar.volume))
            self._exit(pos, close_quantity, exit_price, bar.start, "take_profit")
            pos.tp_levels.remove((price, fraction))
            if pos.quantity <= 1e-12:
                return self._finalize(pos, bar.start)
            if self.breakeven_after_tp1 and not pos.at_breakeven:
                # +1R is banked: the remainder can no longer lose. Stop
                # moves to entry ± cost buffer (a later touch exits ~flat).
                buffer = pos.entry_price * self.breakeven_buffer_pct
                pos.stop = (pos.entry_price + buffer if long
                            else pos.entry_price - buffer)
                pos.at_breakeven = True
        # position survived this bar: ratchet the trailing stop for NEXT bar
        # (using this bar's extreme, never to check this bar's own low/high —
        # the stop check above used the level the position entered the bar with)
        self._update_trailing(pos, bar, long)
        return None

    def _update_trailing(self, pos: _OpenPosition, bar: OHLCVBar, long: bool) -> None:
        """Ratchet the trailing stop toward the favorable extreme. Ratchet-only
        (never loosens); ``initial_stop`` stays fixed so the R unit is
        unchanged. Composes with breakeven (takes the tighter stop). Modes:
        ``pct`` (% of the extreme), ``atr`` (extreme − mult×ATR), ``chandelier``
        (highest-high/lowest-low over the lookback − mult×ATR)."""
        mode = pos.trailing_mode
        if not pos.trailing_mult or mode not in ("pct", "atr", "chandelier"):
            return
        price = bar.high if long else bar.low
        pos.extreme = (max(pos.extreme, price) if long
                       else min(pos.extreme, price)) if pos.extreme is not None else price
        if mode == "pct":
            trail = (pos.extreme * (1 - pos.trailing_mult) if long
                     else pos.extreme * (1 + pos.trailing_mult))
        else:
            window = self._trail_bars.get(pos.symbol)
            if not window:
                return
            period = pos.trailing_period or 14
            recent = list(window)[-period:]
            atr = self._atr(recent)
            if atr <= 0:
                return
            if mode == "atr":
                trail = (pos.extreme - pos.trailing_mult * atr if long
                         else pos.extreme + pos.trailing_mult * atr)
            else:  # chandelier: anchor on the window's extreme, not the position's
                hh = max(b.high for b in recent)
                ll = min(b.low for b in recent)
                trail = (hh - pos.trailing_mult * atr if long
                         else ll + pos.trailing_mult * atr)
        pos.stop = max(pos.stop, trail) if long else min(pos.stop, trail)

    @staticmethod
    def _atr(bars: list[OHLCVBar]) -> float:
        """Average true range over the bars (simple mean of per-bar true range;
        the first bar has no prior close, so its TR is just high−low)."""
        if not bars:
            return 0.0
        trs: list[float] = []
        prev_close: float | None = None
        for b in bars:
            tr = b.high - b.low
            if prev_close is not None:
                tr = max(tr, abs(b.high - prev_close), abs(b.low - prev_close))
            trs.append(tr)
            prev_close = b.close
        return sum(trs) / len(trs)

    def close_all(self, bar: OHLCVBar, symbol: str | None = None) -> list[ClosedTrade]:
        """Force-close open positions at the bar's close (end of data).
        ``symbol`` restricts the close to that symbol (the multi-symbol engine
        force-closes each symbol at ITS own final bar); ``None`` closes every
        position, byte-identical to before."""
        closed: list[ClosedTrade] = []
        for pos in list(self.positions.values()):
            if symbol is not None and pos.symbol != symbol:
                continue
            long = pos.side == "BUY"
            exit_price = self.slippage.fill_price_at(
                bar.close, "SELL" if long else "BUY",
                _participation(pos.quantity, bar.volume))
            self._exit(pos, pos.quantity, exit_price, bar.start, "end_of_data")
            closed.append(self._finalize(pos, bar.start))
        return closed

    # --- internals ------------------------------------------------------------------

    def _exit(self, pos: _OpenPosition, quantity: float, price: float,
              ts: datetime, reason: str) -> None:
        sign = 1 if pos.side == "BUY" else -1
        fee = self.commission.cost(quantity, price)
        pnl = sign * (price - pos.entry_price) * quantity - fee
        pos.realized += pnl
        pos.exit_notional += price * quantity
        pos.exit_quantity += quantity
        pos.quantity -= quantity
        pos.last_reason = reason
        self.cash_pnl += pnl

    def _finalize(self, pos: _OpenPosition, ts: datetime) -> ClosedTrade:
        net_pnl = pos.realized - pos.entry_commission
        risk_unit = pos.original_quantity * abs(pos.entry_price - pos.initial_stop)
        trade = ClosedTrade(
            symbol=pos.symbol,
            side=pos.side,
            quantity=pos.original_quantity,
            entry_price=pos.entry_price,
            exit_price=pos.exit_notional / pos.exit_quantity,
            opened_at=pos.opened_at,
            closed_at=ts,
            pnl=net_pnl,
            reason=pos.last_reason,
            recommendation_id=pos.recommendation_id,
            initial_stop=pos.initial_stop,
            r_multiple=(net_pnl / risk_unit) if risk_unit > 0 else None,
            planned_rr=pos.planned_rr,
        )
        self.closed.append(trade)
        self.positions.pop(pos.recommendation_id, None)
        return trade
