"""
Risk Gate — programmatic hard limits that no agent signal can override.

The gate sits between the signal mapper and the broker.  Every proposed
order is validated here before execution.  If any rule fires, the order
is rejected with a human-readable reason and logged.

Rules (checked in order):
  1. Market must be open (or explicitly bypassed for paper testing).
  2. Circuit breaker: daily P&L loss limit.
  3. Minimum cash reserve must remain intact after the trade.
  4. Maximum total portfolio exposure cap.
  5. Maximum single-position size cap (prevents over-concentration).
  6. Duplicate buy guard (don't add to a position already at the cap).
  7. Sell guard: can only sell what is actually held.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from tradingbot.broker.base import BrokerAdapter, OrderSide
from tradingbot.broker.signal_mapper import OrderInstruction
from tradingbot.portfolio.database import PortfolioDatabase

logger = logging.getLogger(__name__)


@dataclass
class RiskVerdict:
    approved: bool
    reason: str
    adjusted_qty: Optional[float] = None  # set when qty was capped, not rejected


class RiskGate:
    """
    Validates an OrderInstruction against portfolio-level hard limits.

    All limit values come from tradingbot/config.py so they can be
    adjusted via environment variables without changing code.
    """

    def __init__(
        self,
        broker: BrokerAdapter,
        db: PortfolioDatabase,
        max_single_position_pct: float = 0.10,
        max_total_exposure_pct: float = 0.80,
        daily_loss_limit_pct: float = -0.02,
        min_cash_reserve: float = 1_000.0,
        require_market_open: bool = True,
    ):
        self._broker = broker
        self._db = db
        self._max_single_pct = max_single_position_pct
        self._max_exposure_pct = max_total_exposure_pct
        self._daily_loss_limit = daily_loss_limit_pct
        self._min_cash_reserve = min_cash_reserve
        self._require_market_open = require_market_open

    # ------------------------------------------------------------------ #
    # Primary entry point                                                  #
    # ------------------------------------------------------------------ #

    def validate(
        self,
        ticker: str,
        instruction: OrderInstruction,
        proposed_qty: float,
        proposed_price: float,
    ) -> RiskVerdict:
        """
        Validate a proposed trade.

        Args:
            ticker:          Ticker symbol.
            instruction:     OrderInstruction from SignalMapper.
            proposed_qty:    Number of shares the runner wants to trade.
            proposed_price:  Current market price per share.

        Returns:
            RiskVerdict with approved=True/False and a reason string.
            If approved with an adjusted_qty, the runner should use that
            quantity instead of the originally proposed one.
        """
        if not instruction.should_trade:
            return RiskVerdict(approved=False, reason="Signal does not require a trade")

        # ---- Rule 1: market hours ----------------------------------------
        if self._require_market_open and not self._broker.is_market_open():
            return RiskVerdict(
                approved=False,
                reason="Market is closed — order not submitted",
            )

        # ---- Rule 2: circuit breaker ------------------------------------
        verdict = self._check_circuit_breaker()
        if verdict:
            return verdict

        account = self._broker.get_account()
        positions = self._broker.get_positions()
        portfolio_value = account.equity
        invested_value = sum(p.market_value for p in positions)

        if instruction.side == OrderSide.BUY:
            return self._validate_buy(
                ticker, proposed_qty, proposed_price, account, portfolio_value, invested_value
            )
        else:
            return self._validate_sell(ticker, proposed_qty)

    # ------------------------------------------------------------------ #
    # BUY validation                                                       #
    # ------------------------------------------------------------------ #

    def _validate_buy(
        self,
        ticker: str,
        qty: float,
        price: float,
        account,
        portfolio_value: float,
        invested_value: float,
    ) -> RiskVerdict:
        trade_value = qty * price

        # ---- Rule 3: minimum cash reserve --------------------------------
        cash_after = account.cash - trade_value
        if cash_after < self._min_cash_reserve:
            max_spend = account.cash - self._min_cash_reserve
            if max_spend <= 0:
                return RiskVerdict(
                    approved=False,
                    reason=f"Cash ${account.cash:.2f} at minimum reserve "
                           f"${self._min_cash_reserve:.2f} — no buy allowed",
                )
            # Cap qty to what we can afford while keeping reserve
            capped_qty = max_spend / price
            logger.warning(
                "Buy qty capped from %.4f to %.4f to maintain cash reserve", qty, capped_qty
            )
            qty = capped_qty
            trade_value = qty * price

        # ---- Rule 4: total exposure cap ----------------------------------
        new_invested = invested_value + trade_value
        if portfolio_value > 0 and (new_invested / portfolio_value) > self._max_exposure_pct:
            allowed_invested = portfolio_value * self._max_exposure_pct
            headroom = allowed_invested - invested_value
            if headroom <= 0:
                return RiskVerdict(
                    approved=False,
                    reason=f"Total exposure {invested_value/portfolio_value:.1%} already at "
                           f"cap {self._max_exposure_pct:.0%}",
                )
            capped_qty = headroom / price
            logger.warning(
                "Buy qty capped from %.4f to %.4f due to exposure limit", qty, capped_qty
            )
            qty = capped_qty
            trade_value = qty * price

        # ---- Rule 5: single-position size cap ----------------------------
        existing_pos = self._broker.get_position(ticker)
        existing_value = existing_pos.market_value if existing_pos else 0.0
        new_pos_value = existing_value + trade_value

        if portfolio_value > 0 and (new_pos_value / portfolio_value) > self._max_single_pct:
            allowed_pos_value = portfolio_value * self._max_single_pct
            room = allowed_pos_value - existing_value
            if room <= 0:
                return RiskVerdict(
                    approved=False,
                    reason=f"{ticker} position {existing_value/portfolio_value:.1%} already at "
                           f"single-position cap {self._max_single_pct:.0%}",
                )
            capped_qty = room / price
            logger.warning(
                "Buy qty capped from %.4f to %.4f due to single-position cap", qty, capped_qty
            )
            qty = capped_qty

        if qty < 0.001:
            return RiskVerdict(approved=False, reason="Computed buy qty rounds to zero after caps")

        return RiskVerdict(approved=True, reason="All risk checks passed", adjusted_qty=round(qty, 4))

    # ------------------------------------------------------------------ #
    # SELL validation                                                      #
    # ------------------------------------------------------------------ #

    def _validate_sell(self, ticker: str, qty: float) -> RiskVerdict:
        existing = self._broker.get_position(ticker)
        if existing is None or existing.qty < 0.001:
            return RiskVerdict(
                approved=False,
                reason=f"No open position in {ticker} to sell",
            )
        # Cap sell qty to what is actually held
        safe_qty = min(qty, existing.qty)
        if safe_qty != qty:
            logger.warning(
                "Sell qty capped from %.4f to %.4f (available holding)", qty, safe_qty
            )
        return RiskVerdict(approved=True, reason="Sell approved", adjusted_qty=round(safe_qty, 4))

    # ------------------------------------------------------------------ #
    # Circuit breaker                                                      #
    # ------------------------------------------------------------------ #

    def _check_circuit_breaker(self) -> Optional[RiskVerdict]:
        """Return a rejection verdict if today's loss limit is breached."""
        today = date.today().isoformat()
        snap = self._db.get_latest_snapshot()
        if snap is None or snap.snapshot_date != today:
            return None  # No intraday reference yet — allow trading

        if snap.daily_pnl_pct < self._daily_loss_limit:
            return RiskVerdict(
                approved=False,
                reason=f"Circuit breaker: daily P&L {snap.daily_pnl_pct:.2%} "
                       f"breached limit {self._daily_loss_limit:.2%} — "
                       "all new buys halted for today",
            )
        return None
