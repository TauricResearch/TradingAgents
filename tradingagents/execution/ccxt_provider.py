"""
CCXT Execution Provider.

Provides crypto trading execution via CCXT library.
Supports 100+ exchanges (Binance, Coinbase, Kraken, etc.).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from .base import (
    ExecutionProvider,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
)

# Optional sandbox for safe code eval (OpenSandbox pattern) — no hard dep
try:
    from .sandbox import run_in_sandbox  # noqa: F401
except ImportError:
    run_in_sandbox = None  # type: ignore


class CCXTProvider(ExecutionProvider):
    """CCXT execution provider for crypto trading."""

    def __init__(self):
        self._exchange = None
        self._exchange_id = None

    @property
    def name(self) -> str:
        return "ccxt"

    @property
    def supported_markets(self) -> list[str]:
        return ["CRYPTO"]

    def connect(
        self,
        credentials: dict,
        exchange_id: str = "binance",
    ) -> bool:
        """
        Connect to a crypto exchange.

        Args:
            credentials: Dict with 'apiKey', 'secret', and optionally 'password'
            exchange_id: Exchange ID (e.g., 'binance', 'coinbase', 'kraken')

        Returns:
            True if connected successfully
        """
        try:
            import ccxt

            exchange_class = getattr(ccxt, exchange_id)
            self._exchange = exchange_class({
                'apiKey': credentials.get('apiKey') or os.environ.get(f'{exchange_id.upper()}_API_KEY'),
                'secret': credentials.get('secret') or os.environ.get(f'{exchange_id.upper()}_SECRET'),
                'password': credentials.get('password'),
                'enableRateLimit': True,
            })

            # Load markets
            self._exchange.load_markets()
            self._exchange_id = exchange_id

            return True

        except Exception as e:
            print(f"Error connecting to {exchange_id}: {e}")
            return False

    def disconnect(self):
        """Disconnect from the exchange."""
        self._exchange = None
        self._exchange_id = None

    def get_balance(self) -> dict[str, float]:
        """Get account balance."""
        if not self._exchange:
            raise RuntimeError("Not connected to exchange")

        try:
            balance = self._exchange.fetch_balance()
            return {
                asset: float(info['free'])
                for asset, info in balance.items()
                if isinstance(info, dict) and 'free' in info and float(info['free']) > 0
            }
        except Exception as e:
            print(f"Error fetching balance: {e}")
            return {}

    def get_position(self, symbol: str) -> Optional[dict]:
        """Get current position for a symbol."""
        if not self._exchange:
            raise RuntimeError("Not connected to exchange")

        try:
            position = self._exchange.fetch_position(symbol)
            return {
                'symbol': position['symbol'],
                'side': position['side'],
                'quantity': float(position['contracts']),
                'entry_price': float(position.get('entryPrice', 0)),
                'unrealized_pnl': float(position.get('unrealizedPnl', 0)),
                'leverage': float(position.get('leverage', 1)),
            }
        except Exception as e:
            print(f"Error fetching position for {symbol}: {e}")
            return None

    def place_order(self, request: OrderRequest) -> OrderResult:
        """Place an order on the exchange."""
        if not self._exchange:
            raise RuntimeError("Not connected to exchange")

        try:
            # Prepare order parameters
            params = {}
            if request.time_in_force:
                params['timeInForce'] = request.time_in_force

            # Place order
            order = self._exchange.create_order(
                symbol=request.symbol,
                type=request.order_type.value,
                side=request.side.value,
                amount=request.quantity,
                price=request.price,
                params=params,
            )

            return OrderResult(
                order_id=order['id'],
                symbol=order['symbol'],
                side=OrderSide(order['side']),
                order_type=OrderType(order['type']),
                quantity=float(order['amount']),
                filled_quantity=float(order.get('filled', 0)),
                price=float(order.get('average', order.get('price', 0))),
                status=self._map_status(order['status']),
                fees=float(order.get('fee', {}).get('cost', 0)),
                metadata={'exchange': self._exchange_id},
            )

        except Exception as e:
            print(f"Error placing order: {e}")
            raise

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        if not self._exchange:
            raise RuntimeError("Not connected to exchange")

        try:
            self._exchange.cancel_order(order_id)
            return True
        except Exception as e:
            print(f"Error cancelling order {order_id}: {e}")
            return False

    def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """Get order status."""
        if not self._exchange:
            raise RuntimeError("Not connected to exchange")

        try:
            order = self._exchange.fetch_order(order_id)
            return OrderResult(
                order_id=order['id'],
                symbol=order['symbol'],
                side=OrderSide(order['side']),
                order_type=OrderType(order['type']),
                quantity=float(order['amount']),
                filled_quantity=float(order.get('filled', 0)),
                price=float(order.get('average', order.get('price', 0))),
                status=self._map_status(order['status']),
                fees=float(order.get('fee', {}).get('cost', 0)),
                metadata={'exchange': self._exchange_id},
            )
        except Exception as e:
            print(f"Error fetching order {order_id}: {e}")
            return None

    def _map_status(self, exchange_status: str) -> OrderStatus:
        """Map exchange status to OrderStatus."""
        status_map = {
            'open': OrderStatus.PENDING,
            'closed': OrderStatus.FILLED,
            'canceled': OrderStatus.CANCELLED,
            'cancelled': OrderStatus.CANCELLED,
            'expired': OrderStatus.CANCELLED,
            'rejected': OrderStatus.REJECTED,
        }
        return status_map.get(exchange_status.lower(), OrderStatus.PENDING)

    def get_ticker(self, symbol: str) -> Optional[dict]:
        """Get current ticker price."""
        if not self._exchange:
            raise RuntimeError("Not connected to exchange")

        try:
            ticker = self._exchange.fetch_ticker(symbol)
            return {
                'symbol': ticker['symbol'],
                'last': float(ticker['last']),
                'bid': float(ticker['bid']),
                'ask': float(ticker['ask']),
                'high': float(ticker['high']),
                'low': float(ticker['low']),
                'volume': float(ticker['baseVolume']),
            }
        except Exception as e:
            print(f"Error fetching ticker for {symbol}: {e}")
            return None


# Global instance
_ccxt_provider: CCXTProvider | None = None


def get_ccxt_provider() -> CCXTProvider:
    """Get or create the global CCXT provider."""
    global _ccxt_provider
    if _ccxt_provider is None:
        _ccxt_provider = CCXTProvider()
    return _ccxt_provider
