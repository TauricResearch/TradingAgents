"""Broker executor: bridges trading agent decisions to actual orders.

Converts swing_signal dicts from the trading pipeline into
real orders via the Kiwoom REST API.
"""

import logging
import math
from typing import Optional

from tradingagents.broker.kiwoom_client import KiwoomClient
from tradingagents.portfolio.state import Order, PortfolioState

logger = logging.getLogger(__name__)


class BrokerExecutor:
    """Executes trading decisions through Kiwoom Securities API."""

    def __init__(
        self,
        client: KiwoomClient,
        portfolio: PortfolioState,
        dry_run: bool = False,
    ):
        """
        Args:
            client: Authenticated KiwoomClient instance
            portfolio: Current portfolio state
            dry_run: If True, validate but don't send orders to broker
        """
        self.client = client
        self.portfolio = portfolio
        self.dry_run = dry_run

    def execute_signal(
        self,
        ticker: str,
        swing_signal: dict,
        market: str = "KRX",
        allow_add_to_existing: bool = False,
    ) -> Optional[dict]:
        """Execute a swing trading signal.

        Args:
            ticker: Stock code (e.g. '005930')
            swing_signal: Dict from signal_processing with action, entry_price,
                         stop_loss, take_profit, position_size_pct, etc.
            market: 'KRX' or 'US'
            allow_add_to_existing: If True, BUY can add to existing position (DCA).

        Returns:
            Execution result dict or None if skipped.
        """
        action = swing_signal.get("action", "PASS").upper()

        if action == "BUY":
            return self._execute_buy(
                ticker,
                swing_signal,
                market,
                allow_add_to_existing=allow_add_to_existing,
            )
        elif action == "SELL":
            return self._execute_sell(ticker, swing_signal, market)
        else:
            logger.info(f"PASS for {ticker}: {swing_signal.get('rationale', '')}")
            return None

    def _execute_buy(
        self,
        ticker: str,
        signal: dict,
        market: str,
        allow_add_to_existing: bool = False,
    ) -> dict:
        """Execute a BUY order."""
        has_existing = self.portfolio.has_position(ticker)

        # Validate portfolio capacity for NEW positions only.
        if not has_existing and not self.portfolio.can_add_position():
            logger.warning(f"Cannot buy {ticker}: max positions reached ({self.portfolio.max_positions})")
            return {"status": "rejected", "reason": "max_positions_reached", "ticker": ticker}

        if has_existing and not allow_add_to_existing:
            logger.warning(f"Cannot buy {ticker}: already holding position")
            return {"status": "rejected", "reason": "already_holding", "ticker": ticker}

        # Calculate position size
        position_size_pct = signal.get("position_size_pct") or 0.10
        position_size_pct = min(position_size_pct, self.portfolio.max_position_pct)
        target_capital = self.portfolio.total_capital * position_size_pct
        available = self.portfolio.available_capital

        existing_capital = (
            self.portfolio.positions[ticker].cost_basis if has_existing else 0.0
        )
        ticker_cap = self.portfolio.total_capital * self.portfolio.max_position_pct
        remaining_ticker_cap = max(0.0, ticker_cap - existing_capital)

        capital_to_use = min(target_capital, available, remaining_ticker_cap)
        if capital_to_use <= 0:
            reason = (
                "max_ticker_allocation_reached"
                if remaining_ticker_cap <= 0
                else "insufficient_capital"
            )
            logger.warning(f"Cannot buy {ticker}: {reason}")
            return {"status": "rejected", "reason": reason, "ticker": ticker}

        # Get current price from broker
        current_price = self.client.get_current_price_value(ticker)
        entry_price = signal.get("entry_price") or current_price

        if not entry_price or entry_price <= 0:
            logger.warning(f"Cannot buy {ticker}: no valid price")
            return {"status": "rejected", "reason": "no_price", "ticker": ticker}

        # Calculate quantity
        quantity = math.floor(capital_to_use / entry_price)
        if quantity <= 0:
            logger.warning(f"Cannot buy {ticker}: price {entry_price} exceeds available capital")
            return {"status": "rejected", "reason": "price_too_high", "ticker": ticker}

        # Build order
        order = Order(
            action="BUY",
            ticker=ticker,
            market=market,
            price=entry_price,
            stop_loss=signal.get("stop_loss") or entry_price * 0.95,
            take_profit=signal.get("take_profit") or entry_price * 1.15,
            quantity=quantity,
            position_size_pct=position_size_pct,
            max_hold_days=signal.get("max_hold_days") or 20,
            rationale=signal.get("rationale", ""),
        )

        result = {
            "status": "pending",
            "ticker": ticker,
            "action": "BUY",
            "is_add_on": has_existing,
            "quantity": quantity,
            "price": entry_price,
            "total_cost": quantity * entry_price,
            "position_size_pct": position_size_pct,
            "stop_loss": order.stop_loss,
            "take_profit": order.take_profit,
        }

        if self.dry_run:
            result["status"] = "dry_run"
            logger.info(
                f"[DRY RUN] BUY {ticker} x{quantity} @ {entry_price:,.0f} "
                f"(SL: {order.stop_loss:,.0f} / TP: {order.take_profit:,.0f})"
            )
            # Still update portfolio state for tracking
            self.portfolio.add_position(order)
            return result

        # Execute via Kiwoom API
        try:
            broker_result = self.client.buy(
                stock_code=ticker,
                quantity=quantity,
                price=0,  # Market order
                order_type="market",
            )

            return_code = int(broker_result.get("return_code", -1))

            if return_code == 0:
                result["status"] = "filled"
                result["order_no"] = broker_result.get("ord_no")
                result["broker_msg"] = broker_result.get("return_msg")
                self.portfolio.add_position(order)
                logger.info(f"BUY filled: {ticker} x{quantity} @ market (order #{result['order_no']})")
            else:
                result["status"] = "failed"
                result["broker_msg"] = broker_result.get("return_msg", "Unknown error")
                logger.error(f"BUY failed for {ticker}: {result['broker_msg']}")

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            logger.error(f"BUY error for {ticker}: {e}")

        return result

    def _execute_sell(self, ticker: str, signal: dict, market: str) -> dict:
        """Execute a SELL order."""
        if not self.portfolio.has_position(ticker):
            logger.warning(f"Cannot sell {ticker}: no position held")
            return {"status": "rejected", "reason": "no_position", "ticker": ticker}

        position = self.portfolio.positions[ticker]
        quantity = position.quantity

        # Get current price
        current_price = self.client.get_current_price_value(ticker)
        exit_price = current_price or signal.get("entry_price") or position.current_price

        result = {
            "status": "pending",
            "ticker": ticker,
            "action": "SELL",
            "quantity": quantity,
            "price": exit_price,
            "entry_price": position.entry_price,
            "pnl": (exit_price - position.entry_price) * quantity,
            "pnl_pct": (exit_price / position.entry_price - 1) * 100 if position.entry_price else 0,
        }

        if self.dry_run:
            result["status"] = "dry_run"
            logger.info(
                f"[DRY RUN] SELL {ticker} x{quantity} @ {exit_price:,.0f} "
                f"(PnL: {result['pnl']:+,.0f} / {result['pnl_pct']:+.1f}%)"
            )
            self.portfolio.close_position(ticker, exit_price, "agent_decision")
            return result

        # Execute via Kiwoom API
        try:
            broker_result = self.client.sell(
                stock_code=ticker,
                quantity=quantity,
                price=0,
                order_type="market",
            )

            return_code = int(broker_result.get("return_code", -1))

            if return_code == 0:
                result["status"] = "filled"
                result["order_no"] = broker_result.get("ord_no")
                result["broker_msg"] = broker_result.get("return_msg")
                self.portfolio.close_position(ticker, exit_price, "agent_decision")
                logger.info(f"SELL filled: {ticker} x{quantity} @ market (order #{result['order_no']})")
            else:
                result["status"] = "failed"
                result["broker_msg"] = broker_result.get("return_msg", "Unknown error")
                logger.error(f"SELL failed for {ticker}: {result['broker_msg']}")

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            logger.error(f"SELL error for {ticker}: {e}")

        return result

    def check_exit_conditions(self, trade_date: str) -> list[dict]:
        """Check all positions for exit conditions (SL/TP/max hold).

        Returns list of execution results for positions that were closed.
        """
        results = []

        for ticker, position in list(self.portfolio.positions.items()):
            current_price = self.client.get_current_price_value(ticker)
            if not current_price:
                continue

            position.current_price = current_price
            exit_reason = None

            if current_price <= position.stop_loss:
                exit_reason = "stop_loss"
            elif current_price >= position.take_profit:
                exit_reason = "take_profit"
            elif position.days_held >= position.max_hold_days:
                exit_reason = "max_hold"

            if exit_reason:
                logger.info(
                    f"Exit trigger [{exit_reason}] for {ticker}: "
                    f"price={current_price:,.0f} SL={position.stop_loss:,.0f} "
                    f"TP={position.take_profit:,.0f} days={position.days_held}"
                )
                signal = {"action": "SELL", "entry_price": current_price}
                result = self._execute_sell(ticker, signal, position.market)
                if result:
                    result["exit_reason"] = exit_reason
                    results.append(result)

        return results
