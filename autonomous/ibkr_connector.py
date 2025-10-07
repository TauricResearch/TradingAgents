"""
IBKR (Interactive Brokers) Connector
====================================

Manages live connection to IBKR TWS/Gateway for portfolio monitoring and trading.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import os

# Note: ib_insync needs to be installed
try:
    from ib_insync import IB, Stock, Contract, MarketOrder, LimitOrder, util
    IBKR_AVAILABLE = True
except ImportError:
    IBKR_AVAILABLE = False
    print("Warning: ib_insync not installed. Install with: pip install ib_insync")

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents a portfolio position"""
    ticker: str
    shares: int
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    percent_change: float


@dataclass
class AccountInfo:
    """Account information from IBKR"""
    net_liquidation: float
    buying_power: float
    cash_balance: float
    total_positions: int
    day_pnl: float
    total_pnl: float


class IBKRConnector:
    """
    Handles all interactions with Interactive Brokers API
    """

    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 7497,  # 7497 for TWS paper, 7496 for TWS live
                 client_id: int = 1):
        """
        Initialize IBKR connector

        Args:
            host: IP address of TWS/Gateway
            port: Port number (7497 for paper, 7496 for live)
            client_id: Unique client identifier
        """
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = None
        self.positions: Dict[str, Position] = {}
        self.account_info: Optional[AccountInfo] = None
        self.is_connected = False

    async def connect(self) -> bool:
        """Connect to IBKR TWS/Gateway"""
        if not IBKR_AVAILABLE:
            logger.error("ib_insync not installed")
            return False

        try:
            self.ib = IB()
            await self.ib.connectAsync(self.host, self.port, self.client_id)
            self.is_connected = True
            logger.info(f"Connected to IBKR at {self.host}:{self.port}")

            # Request account updates
            self.ib.reqAccountUpdates()

            return True
        except Exception as e:
            logger.error(f"Failed to connect to IBKR: {e}")
            self.is_connected = False
            return False

    async def disconnect(self):
        """Disconnect from IBKR"""
        if self.ib and self.is_connected:
            self.ib.disconnect()
            self.is_connected = False
            logger.info("Disconnected from IBKR")

    async def sync_portfolio(self) -> Dict[str, Position]:
        """
        Sync portfolio positions from IBKR

        Returns:
            Dictionary of positions keyed by ticker
        """
        if not self.is_connected:
            logger.error("Not connected to IBKR")
            return {}

        try:
            # Get all positions
            ib_positions = self.ib.positions()
            self.positions.clear()

            for pos in ib_positions:
                if pos.position != 0:  # Skip closed positions
                    ticker = pos.contract.symbol

                    # Get current market price
                    contract = Stock(ticker, 'SMART', 'USD')
                    self.ib.qualifyContracts(contract)
                    ticker_data = self.ib.reqMktData(contract, '', False, False)
                    await asyncio.sleep(1)  # Wait for price data

                    current_price = ticker_data.marketPrice()
                    if current_price is None or current_price <= 0:
                        current_price = ticker_data.last or pos.avgCost

                    market_value = pos.position * current_price
                    unrealized_pnl = market_value - (pos.position * pos.avgCost)
                    percent_change = ((current_price - pos.avgCost) / pos.avgCost) * 100

                    position = Position(
                        ticker=ticker,
                        shares=int(pos.position),
                        avg_cost=pos.avgCost,
                        current_price=current_price,
                        market_value=market_value,
                        unrealized_pnl=unrealized_pnl,
                        realized_pnl=0,  # Would need to track trades
                        percent_change=percent_change
                    )

                    self.positions[ticker] = position
                    logger.info(f"Synced position: {ticker} - {position.shares} shares @ ${current_price:.2f}")

            logger.info(f"Portfolio sync complete: {len(self.positions)} positions")
            return self.positions

        except Exception as e:
            logger.error(f"Error syncing portfolio: {e}")
            return self.positions

    async def get_account_info(self) -> Optional[AccountInfo]:
        """Get account information"""
        if not self.is_connected:
            return None

        try:
            account_values = self.ib.accountValues()

            # Extract key values
            values_dict = {av.tag: av.value for av in account_values}

            self.account_info = AccountInfo(
                net_liquidation=float(values_dict.get('NetLiquidation', 0)),
                buying_power=float(values_dict.get('BuyingPower', 0)),
                cash_balance=float(values_dict.get('TotalCashBalance', 0)),
                total_positions=len(self.positions),
                day_pnl=float(values_dict.get('DailyPnL', 0)),
                total_pnl=float(values_dict.get('UnrealizedPnL', 0))
            )

            return self.account_info

        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return None

    async def get_position(self, ticker: str) -> Optional[Position]:
        """Get specific position by ticker"""
        return self.positions.get(ticker)

    async def place_order(self,
                         ticker: str,
                         action: str,  # 'BUY' or 'SELL'
                         quantity: int,
                         order_type: str = 'LIMIT',
                         limit_price: Optional[float] = None,
                         stop_price: Optional[float] = None) -> Optional[str]:
        """
        Place an order (with safety checks)

        Args:
            ticker: Stock symbol
            action: 'BUY' or 'SELL'
            quantity: Number of shares
            order_type: 'MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT'
            limit_price: Limit price for limit orders
            stop_price: Stop price for stop orders

        Returns:
            Order ID if successful, None otherwise
        """
        if not self.is_connected:
            logger.error("Not connected to IBKR")
            return None

        # Safety check - require confirmation for large orders
        if quantity > 100 or (limit_price and limit_price * quantity > 10000):
            logger.warning(f"Large order detected: {action} {quantity} {ticker}")
            # In production, you'd want manual confirmation here

        try:
            # Create contract
            contract = Stock(ticker, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)

            # Create order based on type
            if order_type == 'MARKET':
                order = MarketOrder(action, quantity)
            elif order_type == 'LIMIT' and limit_price:
                order = LimitOrder(action, quantity, limit_price)
            else:
                logger.error(f"Unsupported order type: {order_type}")
                return None

            # Place the order
            trade = self.ib.placeOrder(contract, order)

            # Wait for order to be acknowledged
            await asyncio.sleep(1)

            if trade.orderStatus.status in ['Submitted', 'PreSubmitted', 'Filled']:
                logger.info(f"Order placed: {action} {quantity} {ticker} - ID: {trade.order.orderId}")
                return str(trade.order.orderId)
            else:
                logger.error(f"Order failed: {trade.orderStatus.status}")
                return None

        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    async def get_market_data(self, ticker: str) -> Optional[Dict[str, float]]:
        """
        Get real-time market data for a ticker

        Returns:
            Dictionary with price data
        """
        if not self.is_connected:
            return None

        try:
            contract = Stock(ticker, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)

            ticker_data = self.ib.reqMktData(contract, '', False, False)
            await asyncio.sleep(2)  # Wait for data

            return {
                'last': ticker_data.last or 0,
                'bid': ticker_data.bid or 0,
                'ask': ticker_data.ask or 0,
                'volume': ticker_data.volume or 0,
                'high': ticker_data.high or 0,
                'low': ticker_data.low or 0,
                'close': ticker_data.close or 0
            }

        except Exception as e:
            logger.error(f"Error getting market data for {ticker}: {e}")
            return None

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get portfolio summary"""
        if not self.positions:
            return {}

        total_value = sum(p.market_value for p in self.positions.values())
        total_cost = sum(p.shares * p.avg_cost for p in self.positions.values())
        total_pnl = sum(p.unrealized_pnl for p in self.positions.values())

        return {
            'total_value': total_value,
            'total_cost': total_cost,
            'total_unrealized_pnl': total_pnl,
            'total_percent_change': ((total_value - total_cost) / total_cost * 100) if total_cost > 0 else 0,
            'position_count': len(self.positions),
            'positions': [
                {
                    'ticker': p.ticker,
                    'shares': p.shares,
                    'value': p.market_value,
                    'pnl': p.unrealized_pnl,
                    'percent': p.percent_change
                }
                for p in self.positions.values()
            ]
        }


# Example usage
async def main():
    """Example of using the IBKR connector"""
    connector = IBKRConnector(port=7497)  # Paper trading port

    # Connect
    if await connector.connect():
        # Sync portfolio
        positions = await connector.sync_portfolio()
        print(f"Found {len(positions)} positions")

        # Get account info
        account = await connector.get_account_info()
        if account:
            print(f"Net Liquidation: ${account.net_liquidation:,.2f}")
            print(f"Buying Power: ${account.buying_power:,.2f}")

        # Get market data
        data = await connector.get_market_data("AAPL")
        if data:
            print(f"AAPL Last Price: ${data['last']}")

        # Disconnect
        await connector.disconnect()


if __name__ == "__main__":
    # For testing
    asyncio.run(main())