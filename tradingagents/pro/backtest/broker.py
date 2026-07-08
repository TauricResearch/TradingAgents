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
    initial_equity: float = 100_000.0
    slippage: SlippageModel = field(default_factory=SlippageModel)
    commission: CommissionModel = field(default_factory=CommissionModel)
    liquidity: LiquidityModel = field(default_factory=LiquidityModel)

    def __post_init__(self):
        self.cash_pnl = 0.0  # realized pnl net of costs
        self.position: _OpenPosition | None = None
        self.closed: list[ClosedTrade] = []

    # --- equity ---------------------------------------------------------------

    def equity(self, mark_price: float | None = None) -> float:
        value = self.initial_equity + self.cash_pnl
        if self.position and mark_price is not None:
            sign = 1 if self.position.side == "BUY" else -1
            value += sign * (mark_price - self.position.entry_price) * self.position.quantity
        return value

    @property
    def position_open(self) -> bool:
        return self.position is not None

    # --- entries ----------------------------------------------------------------

    def open_from_recommendation(
        self, rec: TradeRecommendation, fill_bar: OHLCVBar
    ) -> bool:
        """Open at the fill bar's open (the bar after the decision), with
        slippage, commission, and the participation cap. Returns False when
        liquidity caps the order to nothing."""
        if self.position is not None:
            raise RuntimeError("v1 broker holds one position at a time")
        if rec.action is TradeAction.HOLD:
            raise ValueError("cannot open a HOLD recommendation")
        side = rec.action.value
        quantity = self.liquidity.cap_quantity(rec.position_size.quantity, fill_bar.volume)
        if quantity <= 0:
            return False
        entry = self.slippage.fill_price(fill_bar.open, side)
        fee = self.commission.cost(quantity, entry)
        self.position = _OpenPosition(
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
        return True

    # --- bar processing -----------------------------------------------------------

    def process_bar(self, bar: OHLCVBar) -> ClosedTrade | None:
        """Manage the open position against one bar; returns the trade if it
        fully closed on this bar."""
        pos = self.position
        if pos is None:
            return None
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

    def close_all(self, bar: OHLCVBar) -> ClosedTrade | None:
        """Force-close at the bar's close (end of data)."""
        pos = self.position
        if pos is None:
            return None
        long = pos.side == "BUY"
        exit_price = self.slippage.fill_price(bar.close, "SELL" if long else "BUY")
        self._exit(pos, pos.quantity, exit_price, bar.start, "end_of_data")
        return self._finalize(pos, bar.start)

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
        self.position = None
        return trade
