"""SimBroker: position lifecycle against replayed bars.

Conservative intrabar policy: when a bar's range touches both the stop and
a take-profit, the stop is assumed to fill first (pessimistic for the
strategy). Take-profit ladders close fractions of the original quantity at
their levels; a stop closes the entire remainder. Fills embed slippage;
commissions are charged per fill on both sides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from tradingagents.contracts import OHLCVBar, TradeAction, TradeRecommendation
from tradingagents.pro.backtest.costs import CommissionModel, LiquidityModel, SlippageModel


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
    reason: str  # "stop" | "take_profit" | "end_of_data"
    recommendation_id: str


@dataclass
class _OpenPosition:
    recommendation: TradeRecommendation
    side: str
    quantity: float  # remaining
    original_quantity: float
    entry_price: float
    stop: float
    tp_levels: list[tuple[float, float]]  # (price, fraction of original) unfilled
    opened_at: datetime
    entry_commission: float
    realized: float = 0.0
    exit_notional: float = 0.0
    exit_quantity: float = 0.0
    last_reason: str = ""


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

    def __post_init__(self):
        self.cash_pnl = 0.0  # realized pnl net of costs
        self.positions: dict[str, _OpenPosition] = {}
        self.closed: list[ClosedTrade] = []

    # --- equity ---------------------------------------------------------------

    def equity(self, mark_price: float | None = None) -> float:
        value = self.initial_equity + self.cash_pnl
        if mark_price is not None:
            for pos in self.positions.values():
                sign = 1 if pos.side == "BUY" else -1
                value += sign * (mark_price - pos.entry_price) * pos.quantity
        return value

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
        entry = self.slippage.fill_price(fill_bar.open, side)
        fee = self.commission.cost(quantity, entry)
        self.positions[rec.id] = _OpenPosition(
            recommendation=rec,
            side=side,
            quantity=quantity,
            original_quantity=quantity,
            entry_price=entry,
            stop=rec.stop_loss,
            tp_levels=[(tp.price, tp.size_fraction) for tp in rec.take_profits],
            opened_at=fill_bar.start,
            entry_commission=fee,
        )
        self.cash_pnl -= fee
        return None

    # --- bar processing -----------------------------------------------------------

    def process_bar(self, bar: OHLCVBar) -> list[ClosedTrade]:
        """Manage every open position against one bar; returns the trades that
        fully closed on this bar (may be empty)."""
        closed: list[ClosedTrade] = []
        for pos in list(self.positions.values()):
            trade = self._manage(pos, bar)
            if trade is not None:
                closed.append(trade)
        return closed

    def _manage(self, pos: _OpenPosition, bar: OHLCVBar) -> ClosedTrade | None:
        long = pos.side == "BUY"
        stop_hit = bar.low <= pos.stop if long else bar.high >= pos.stop
        if stop_hit:
            exit_price = self.slippage.fill_price(pos.stop, "SELL" if long else "BUY")
            self._exit(pos, pos.quantity, exit_price, bar.start, "stop")
            return self._finalize(pos, bar.start)

        for price, fraction in list(pos.tp_levels):
            tp_hit = bar.high >= price if long else bar.low <= price
            if not tp_hit:
                continue
            close_quantity = min(fraction * pos.original_quantity, pos.quantity)
            exit_price = self.slippage.fill_price(price, "SELL" if long else "BUY")
            self._exit(pos, close_quantity, exit_price, bar.start, "take_profit")
            pos.tp_levels.remove((price, fraction))
            if pos.quantity <= 1e-12:
                return self._finalize(pos, bar.start)
        return None

    def close_all(self, bar: OHLCVBar) -> list[ClosedTrade]:
        """Force-close every open position at the bar's close (end of data)."""
        closed: list[ClosedTrade] = []
        for pos in list(self.positions.values()):
            long = pos.side == "BUY"
            exit_price = self.slippage.fill_price(bar.close, "SELL" if long else "BUY")
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
        trade = ClosedTrade(
            symbol=pos.recommendation.symbol,
            side=pos.side,
            quantity=pos.original_quantity,
            entry_price=pos.entry_price,
            exit_price=pos.exit_notional / pos.exit_quantity,
            opened_at=pos.opened_at,
            closed_at=ts,
            pnl=pos.realized - pos.entry_commission,
            reason=pos.last_reason,
            recommendation_id=pos.recommendation.id,
        )
        self.closed.append(trade)
        self.positions.pop(pos.recommendation.id, None)
        return trade
