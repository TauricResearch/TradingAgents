"""
Lumibot Execution Provider.

Provides multi-asset trading execution via Lumibot library.
Supports stocks, options, futures, and crypto.
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


class LumibotProvider(ExecutionProvider):
    """Lumibot execution provider for multi-asset trading."""

    def __init__(self):
        self._broker = None
        self._broker_name = None

    @property
    def name(self) -> str:
        return "lumibot"

    @property
    def supported_markets(self) -> list[str]:
        return ["US", "CRYPTO", "OPTIONS", "FUTURES"]

    def connect(
        self,
        credentials: dict,
        broker_name: str = "alpaca",
    ) -> bool:
        """
        Connect to a broker via Lumibot.

        Args:
            credentials: Dict with API keys for the broker
            broker_name: Broker name (e.g., 'alpaca', 'tradier', 'ib')

        Returns:
            True if connected successfully
        """
        try:
            from lumibot.brokers import Alpaca, Tradier, InteractiveBrokers

            broker_classes = {
                'alpaca': Alpaca,
                'tradier': Tradier,
                'ib': InteractiveBrokers,
            }

            broker_class = broker_classes.get(broker_name)
            if not broker_class:
                raise ValueError(f"Unsupported broker: {broker_name}")

            # Get credentials from env if not provided
            api_key = credentials.get('apiKey') or os.environ.get(f'{broker_name.upper()}_API_KEY')
            secret = credentials.get('secret') or os.environ.get(f'{broker_name.upper()}_SECRET')

            self._broker = broker_class({
                'api_key': api_key,
                'secret': secret,
            })
            self._broker_name = broker_name

            return True

        except Exception as e:
            print(f"Error connecting to {broker_name}: {e}")
            return False

    def disconnect(self):
        """Disconnect from the broker."""
        self._broker = None
        self._broker_name = None

    def get_balance(self) -> dict[str, float]:
        """Get account balance."""
        if not self._broker:
            raise RuntimeError("Not connected to broker")

        try:
            account = self._broker.get_account()
            return {
                'cash': float(account.cash),
                'portfolio_value': float(account.portfolio_value),
                'buying_power': float(account.buying_power),
            }
        except Exception as e:
            print(f"Error fetching balance: {e}")
            return {}

    def get_position(self, symbol: str) -> Optional[dict]:
        """Get current position for a symbol."""
        if not self._broker:
            raise RuntimeError("Not connected to broker")

        try:
            position = self._broker.get_position(symbol)
            if position:
                return {
                    'symbol': position.symbol,
                    'quantity': float(position.quantity),
                    'entry_price': float(position.avg_entry_price),
                    'current_price': float(position.current_price),
                    'unrealized_pnl': float(position.unrealized_pnl),
                    'asset_type': position.asset.asset_type,
                }
            return None
        except Exception as e:
            print(f"Error fetching position for {symbol}: {e}")
            return None

    def place_order(self, request: OrderRequest) -> OrderResult:
        """Place an order via Lumibot."""
        if not self._broker:
            raise RuntimeError("Not connected to broker")

        try:
            from lumibot.entities import Asset, Order

            # Create asset
            asset = Asset(
                symbol=request.symbol,
                asset_type=self._get_asset_type(request.metadata.get('asset_type', 'stock')),
            )

            # Map order type
            order_type_map = {
                OrderType.MARKET: 'market',
                OrderType.LIMIT: 'limit',
                OrderType.STOP: 'stop',
                OrderType.STOP_LIMIT: 'stop_limit',
            }

            # Create order
            order = self._broker.create_order(
                asset=asset,
                quantity=request.quantity,
                side=request.side.value,
                order_type=order_type_map.get(request.order_type, 'market'),
                limit_price=request.price,
                stop_price=request.stop_price,
            )

            # Submit order
            submitted_order = self._broker.submit_order(order)

            return OrderResult(
                order_id=submitted_order.identifier,
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                quantity=request.quantity,
                filled_quantity=0,  # Lumibot fills asynchronously
                price=None,
                status=OrderStatus.PENDING,
                metadata={'broker': self._broker_name},
            )

        except Exception as e:
            print(f"Error placing order: {e}")
            raise

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        if not self._broker:
            raise RuntimeError("Not connected to broker")

        try:
            self._broker.cancel_order(order_id)
            return True
        except Exception as e:
            print(f"Error cancelling order {order_id}: {e}")
            return False

    def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """Get order status."""
        if not self._broker:
            raise RuntimeError("Not connected to broker")

        try:
            order = self._broker.get_order(order_id)
            if order:
                return OrderResult(
                    order_id=order.identifier,
                    symbol=order.asset.symbol,
                    side=OrderSide(order.side),
                    order_type=OrderType(order.type),
                    quantity=float(order.quantity),
                    filled_quantity=float(order.filled_quantity),
                    price=float(order.fill_price) if order.fill_price else None,
                    status=self._map_status(order.status),
                    metadata={'broker': self._broker_name},
                )
            return None
        except Exception as e:
            print(f"Error fetching order {order_id}: {e}")
            return None

    def _map_status(self, lumibot_status: str) -> OrderStatus:
        """Map Lumibot status to OrderStatus."""
        status_map = {
            'pending': OrderStatus.PENDING,
            'fill': OrderStatus.FILLED,
            'partial_fill': OrderStatus.PARTIALLY_FILLED,
            'canceled': OrderStatus.CANCELLED,
            'cancelled': OrderStatus.CANCELLED,
            'error': OrderStatus.REJECTED,
        }
        return status_map.get(lumibot_status.lower(), OrderStatus.PENDING)

    def _get_asset_type(self, asset_type_str: str) -> str:
        """Map asset type string to Lumibot asset type."""
        asset_type_map = {
            'stock': 'stock',
            'option': 'option',
            'future': 'future',
            'crypto': 'crypto',
        }
        return asset_type_map.get(asset_type_str.lower(), 'stock')


# Global instance
_lumibot_provider: LumibotProvider | None = None


def get_lumibot_provider() -> LumibotProvider:
    """Get or create the global Lumibot provider."""
    global _lumibot_provider
    if _lumibot_provider is None:
        _lumibot_provider = LumibotProvider()
    return _lumibot_provider
