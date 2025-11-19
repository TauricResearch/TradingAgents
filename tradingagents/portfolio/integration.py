"""
Integration layer between the portfolio management system and TradingAgents.

This module provides functionality to connect the portfolio to the TradingAgentsGraph,
execute trading decisions from agents, and provide portfolio context to agents.
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any, Callable
import logging

from .portfolio import Portfolio
from .orders import MarketOrder, LimitOrder, OrderType
from .exceptions import (
    InvalidOrderError,
    InsufficientFundsError,
    IntegrationError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class TradingAgentsPortfolioIntegration:
    """
    Integrates portfolio management with TradingAgents framework.

    This class connects the portfolio to TradingAgentsGraph, executes
    decisions from agents, and provides portfolio context for decision-making.
    """

    def __init__(
        self,
        portfolio: Portfolio,
        price_fetcher: Optional[Callable[[str], Decimal]] = None
    ):
        """
        Initialize the integration layer.

        Args:
            portfolio: Portfolio instance to manage
            price_fetcher: Optional function to fetch current prices (ticker -> price)
                          If None, prices must be provided with each operation
        """
        self.portfolio = portfolio
        self.price_fetcher = price_fetcher
        self.execution_history: List[Dict[str, Any]] = []

        logger.info("Initialized TradingAgentsPortfolioIntegration")

    def execute_agent_decision(
        self,
        decision: Dict[str, Any],
        current_prices: Optional[Dict[str, Decimal]] = None
    ) -> Dict[str, Any]:
        """
        Execute a trading decision from TradingAgents.

        Expected decision format:
        {
            'action': 'buy' | 'sell' | 'hold',
            'ticker': str,
            'quantity': int | float | Decimal (optional, uses position sizing if not provided),
            'order_type': 'market' | 'limit' (optional, default 'market'),
            'limit_price': Decimal (required if order_type is 'limit'),
            'reasoning': str (optional),
        }

        Args:
            decision: Trading decision from agent
            current_prices: Optional dict of current prices

        Returns:
            Execution result with status and details

        Raises:
            IntegrationError: If decision format is invalid
            InvalidOrderError: If order cannot be executed
        """
        try:
            # Validate decision format
            if not isinstance(decision, dict):
                raise IntegrationError("Decision must be a dictionary")

            action = decision.get('action', '').lower()
            if action not in ['buy', 'sell', 'hold']:
                raise IntegrationError(f"Invalid action: {action}")

            ticker = decision.get('ticker')
            if not ticker:
                raise IntegrationError("Ticker is required")

            # Handle 'hold' action
            if action == 'hold':
                result = {
                    'status': 'success',
                    'action': 'hold',
                    'ticker': ticker,
                    'message': 'No action taken',
                }
                self._log_execution(decision, result)
                return result

            # Get current price
            current_price = self._get_price(ticker, current_prices)

            # Determine quantity
            quantity = self._determine_quantity(decision, ticker, current_price)

            # Create and execute order
            order = self._create_order(decision, ticker, quantity)

            # Execute order
            self.portfolio.execute_order(order, current_price)

            result = {
                'status': 'success',
                'action': action,
                'ticker': ticker,
                'quantity': str(quantity),
                'price': str(current_price),
                'order_type': decision.get('order_type', 'market'),
                'commission': str(self.portfolio.commission_rate),
                'reasoning': decision.get('reasoning', ''),
            }

            self._log_execution(decision, result)

            logger.info(
                f"Executed agent decision: {action} {ticker} "
                f"qty={quantity} price={current_price}"
            )

            return result

        except (InvalidOrderError, InsufficientFundsError) as e:
            # Trading errors - expected in normal operation
            result = {
                'status': 'failed',
                'action': decision.get('action'),
                'ticker': decision.get('ticker'),
                'error': str(e),
                'error_type': type(e).__name__,
            }
            self._log_execution(decision, result)
            logger.warning(f"Failed to execute decision: {e}")
            return result

        except Exception as e:
            # Unexpected errors
            result = {
                'status': 'error',
                'action': decision.get('action'),
                'ticker': decision.get('ticker'),
                'error': str(e),
                'error_type': type(e).__name__,
            }
            self._log_execution(decision, result)
            logger.error(f"Error executing decision: {e}", exc_info=True)
            raise IntegrationError(f"Failed to execute decision: {e}")

    def get_portfolio_context(
        self,
        current_prices: Optional[Dict[str, Decimal]] = None
    ) -> Dict[str, Any]:
        """
        Get portfolio context for agent decision-making.

        Provides current portfolio state, positions, and performance metrics
        that agents can use to make informed trading decisions.

        Args:
            current_prices: Optional dict of current prices

        Returns:
            Dictionary with portfolio context information
        """
        try:
            # Get current prices for all positions
            if current_prices is None and self.price_fetcher is not None:
                current_prices = {}
                for ticker in self.portfolio.positions.keys():
                    try:
                        current_prices[ticker] = self.price_fetcher(ticker)
                    except Exception as e:
                        logger.warning(f"Failed to fetch price for {ticker}: {e}")

            # Calculate portfolio metrics
            total_value = self.portfolio.total_value(current_prices)
            unrealized_pnl = self.portfolio.unrealized_pnl(current_prices) if current_prices else Decimal('0')
            realized_pnl = self.portfolio.realized_pnl()

            # Position details
            positions_context = []
            for ticker, position in self.portfolio.get_all_positions().items():
                pos_context = {
                    'ticker': ticker,
                    'quantity': str(position.quantity),
                    'cost_basis': str(position.cost_basis),
                    'is_long': position.is_long,
                }

                if current_prices and ticker in current_prices:
                    price = current_prices[ticker]
                    pos_context.update({
                        'current_price': str(price),
                        'market_value': str(position.market_value(price)),
                        'unrealized_pnl': str(position.unrealized_pnl(price)),
                        'unrealized_pnl_pct': str(position.unrealized_pnl_percent(price)),
                    })

                positions_context.append(pos_context)

            # Performance metrics (if we have enough data)
            performance = None
            try:
                if len(self.portfolio.trade_history) > 0:
                    metrics = self.portfolio.get_performance_metrics()
                    performance = {
                        'total_trades': metrics.total_trades,
                        'win_rate': str(metrics.win_rate),
                        'profit_factor': str(metrics.profit_factor),
                        'sharpe_ratio': str(metrics.sharpe_ratio),
                        'max_drawdown': str(metrics.max_drawdown),
                    }
            except Exception as e:
                logger.debug(f"Could not calculate performance metrics: {e}")

            context = {
                'total_value': str(total_value),
                'cash': str(self.portfolio.cash),
                'cash_pct': str(self.portfolio.cash / total_value if total_value > 0 else Decimal('1')),
                'invested_value': str(total_value - self.portfolio.cash),
                'unrealized_pnl': str(unrealized_pnl),
                'realized_pnl': str(realized_pnl),
                'total_pnl': str(unrealized_pnl + realized_pnl),
                'total_return': str((total_value - self.portfolio.initial_capital) / self.portfolio.initial_capital),
                'num_positions': len(self.portfolio.positions),
                'positions': positions_context,
                'performance': performance,
                'timestamp': datetime.now().isoformat(),
            }

            return context

        except Exception as e:
            logger.error(f"Error getting portfolio context: {e}", exc_info=True)
            raise IntegrationError(f"Failed to get portfolio context: {e}")

    def batch_execute_decisions(
        self,
        decisions: List[Dict[str, Any]],
        current_prices: Optional[Dict[str, Decimal]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple trading decisions in batch.

        Args:
            decisions: List of trading decisions
            current_prices: Optional dict of current prices

        Returns:
            List of execution results
        """
        results = []

        for decision in decisions:
            try:
                result = self.execute_agent_decision(decision, current_prices)
                results.append(result)
            except Exception as e:
                logger.error(f"Error in batch execution: {e}")
                results.append({
                    'status': 'error',
                    'decision': decision,
                    'error': str(e),
                })

        return results

    def rebalance_portfolio(
        self,
        target_weights: Dict[str, Decimal],
        current_prices: Dict[str, Decimal]
    ) -> List[Dict[str, Any]]:
        """
        Rebalance portfolio to target weights.

        Args:
            target_weights: Dictionary mapping ticker to target weight (as fraction)
            current_prices: Dictionary of current prices

        Returns:
            List of execution results

        Raises:
            ValidationError: If target weights are invalid
            IntegrationError: If rebalancing fails
        """
        try:
            # Validate target weights
            total_weight = sum(target_weights.values())
            if abs(total_weight - Decimal('1')) > Decimal('0.01'):
                raise ValidationError(
                    f"Target weights must sum to 1.0, got {total_weight}"
                )

            # Calculate current portfolio value
            current_value = self.portfolio.total_value(current_prices)

            # Calculate target values
            target_values = {
                ticker: current_value * weight
                for ticker, weight in target_weights.items()
            }

            # Calculate required trades
            decisions = []

            for ticker, target_value in target_values.items():
                current_position = self.portfolio.get_position(ticker)
                current_value_ticker = Decimal('0')

                if current_position and ticker in current_prices:
                    current_value_ticker = current_position.market_value(current_prices[ticker])

                # Calculate difference
                difference = target_value - current_value_ticker

                # Only trade if difference is significant (> 1% of target)
                if abs(difference) < target_value * Decimal('0.01'):
                    continue

                # Create decision
                if ticker in current_prices:
                    price = current_prices[ticker]
                    quantity = difference / price

                    decision = {
                        'action': 'buy' if quantity > 0 else 'sell',
                        'ticker': ticker,
                        'quantity': abs(quantity),
                        'order_type': 'market',
                        'reasoning': f'Rebalancing to target weight {target_weights[ticker]:.2%}',
                    }
                    decisions.append(decision)

            # Execute all rebalancing trades
            results = self.batch_execute_decisions(decisions, current_prices)

            logger.info(f"Completed portfolio rebalancing with {len(results)} trades")

            return results

        except Exception as e:
            logger.error(f"Error rebalancing portfolio: {e}", exc_info=True)
            raise IntegrationError(f"Failed to rebalance portfolio: {e}")

    def _get_price(
        self,
        ticker: str,
        current_prices: Optional[Dict[str, Decimal]] = None
    ) -> Decimal:
        """Get current price for a ticker."""
        # Try provided prices first
        if current_prices and ticker in current_prices:
            price = current_prices[ticker]
            if not isinstance(price, Decimal):
                price = Decimal(str(price))
            return price

        # Try price fetcher
        if self.price_fetcher:
            try:
                price = self.price_fetcher(ticker)
                if not isinstance(price, Decimal):
                    price = Decimal(str(price))
                return price
            except Exception as e:
                logger.error(f"Failed to fetch price for {ticker}: {e}")

        raise IntegrationError(
            f"No price available for {ticker}. "
            "Provide current_prices or configure price_fetcher."
        )

    def _determine_quantity(
        self,
        decision: Dict[str, Any],
        ticker: str,
        current_price: Decimal
    ) -> Decimal:
        """Determine trade quantity from decision."""
        # Check if quantity is explicitly provided
        if 'quantity' in decision:
            quantity = decision['quantity']
            if not isinstance(quantity, Decimal):
                quantity = Decimal(str(quantity))
            return quantity

        # Use position sizing if available
        if 'position_size_pct' in decision:
            pct = Decimal(str(decision['position_size_pct']))
            total_value = self.portfolio.total_value()
            position_value = total_value * pct
            quantity = position_value / current_price
            return quantity

        # Default: use 10% of portfolio
        total_value = self.portfolio.total_value()
        default_pct = Decimal('0.10')
        position_value = total_value * default_pct
        quantity = position_value / current_price

        logger.warning(
            f"No quantity specified for {ticker}, "
            f"using default 10% position size: {quantity}"
        )

        return quantity

    def _create_order(
        self,
        decision: Dict[str, Any],
        ticker: str,
        quantity: Decimal
    ):
        """Create an order from a decision."""
        action = decision.get('action', '').lower()
        order_type = decision.get('order_type', 'market').lower()

        # Adjust quantity sign based on action
        if action == 'sell':
            quantity = -abs(quantity)
        else:
            quantity = abs(quantity)

        # Create appropriate order type
        if order_type == 'market':
            return MarketOrder(ticker=ticker, quantity=quantity)
        elif order_type == 'limit':
            limit_price = decision.get('limit_price')
            if not limit_price:
                raise IntegrationError("limit_price required for limit orders")
            if not isinstance(limit_price, Decimal):
                limit_price = Decimal(str(limit_price))
            return LimitOrder(ticker=ticker, quantity=quantity, limit_price=limit_price)
        else:
            raise IntegrationError(f"Unsupported order type: {order_type}")

    def _log_execution(
        self,
        decision: Dict[str, Any],
        result: Dict[str, Any]
    ) -> None:
        """Log execution for audit trail."""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'decision': decision,
            'result': result,
        }
        self.execution_history.append(log_entry)

    def get_execution_history(
        self,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get execution history.

        Args:
            limit: Maximum number of entries to return (most recent first)

        Returns:
            List of execution log entries
        """
        if limit:
            return self.execution_history[-limit:]
        return self.execution_history.copy()

    def clear_execution_history(self) -> None:
        """Clear the execution history."""
        self.execution_history.clear()
        logger.info("Cleared execution history")
