"""
Resilient IBKR Connector
========================

Enhanced IBKR connection with auto-reconnection, circuit breakers,
and comprehensive error handling.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import time
from collections import deque

try:
    from ib_insync import (
        IB, Stock, Option, Future, Contract, MarketOrder,
        LimitOrder, StopOrder, BracketOrder, util
    )
    IBKR_AVAILABLE = True
except ImportError:
    IBKR_AVAILABLE = False

from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_retry, after_retry
)

from ..core.database import DatabaseManager, Position, Order, OrderStatus

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection state enumeration"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    CLOSED = "closed"


@dataclass
class ConnectionHealth:
    """Connection health metrics"""
    state: ConnectionState = ConnectionState.DISCONNECTED
    last_heartbeat: Optional[datetime] = None
    reconnect_attempts: int = 0
    total_reconnects: int = 0
    errors: deque = field(default_factory=lambda: deque(maxlen=100))
    latency_ms: float = 0.0
    messages_received: int = 0
    orders_placed: int = 0
    orders_failed: int = 0


class CircuitBreaker:
    """Circuit breaker pattern for connection management"""

    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        """
        Initialize circuit breaker

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting to close circuit
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open

    def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == "open":
            if (datetime.now() - self.last_failure_time).seconds > self.timeout:
                self.state = "half-open"
            else:
                raise Exception("Circuit breaker is open")

        try:
            result = func(*args, **kwargs)
            if self.state == "half-open":
                self.state = "closed"
                self.failures = 0
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure_time = datetime.now()

            if self.failures >= self.failure_threshold:
                self.state = "open"
                logger.error(f"Circuit breaker opened after {self.failures} failures")

            raise e

    def reset(self):
        """Reset circuit breaker"""
        self.failures = 0
        self.state = "closed"
        self.last_failure_time = None


class ResilientIBKRConnector:
    """
    Resilient IBKR connector with auto-reconnection and health monitoring
    """

    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 7497,
                 client_id: int = 1,
                 db_manager: Optional[DatabaseManager] = None,
                 max_reconnect_attempts: int = 10,
                 reconnect_delay: int = 5):
        """
        Initialize resilient IBKR connector

        Args:
            host: TWS/Gateway host
            port: Connection port
            client_id: Unique client ID
            db_manager: Database manager for persistence
            max_reconnect_attempts: Maximum reconnection attempts
            reconnect_delay: Initial delay between reconnection attempts
        """
        self.host = host
        self.port = port
        self.client_id = client_id
        self.db = db_manager

        self.ib: Optional[IB] = None
        self.health = ConnectionHealth()
        self.circuit_breaker = CircuitBreaker()

        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay

        # Callbacks
        self.on_connected_callback: Optional[Callable] = None
        self.on_disconnected_callback: Optional[Callable] = None
        self.on_error_callback: Optional[Callable] = None

        # Connection monitoring
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None

        # WebSocket for real-time data
        self._websocket_connected = False
        self._market_data_streams: Dict[str, Any] = {}

    # === Connection Management ===

    async def connect(self) -> bool:
        """
        Connect to IBKR with retry logic

        Returns:
            True if connected successfully
        """
        if not IBKR_AVAILABLE:
            logger.error("ib_insync not installed")
            return False

        self.health.state = ConnectionState.CONNECTING

        try:
            return await self._connect_with_retry()
        except Exception as e:
            logger.error(f"Failed to connect after all attempts: {e}")
            self.health.state = ConnectionState.ERROR
            self.health.errors.append({
                'timestamp': datetime.now(),
                'error': str(e),
                'type': 'connection'
            })
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(ConnectionError),
        before=before_retry(lambda retry_state: logger.info(
            f"Connection attempt {retry_state.attempt_number}"
        ))
    )
    async def _connect_with_retry(self) -> bool:
        """Internal connection with retry logic"""
        try:
            self.ib = IB()

            # Connect asynchronously
            await self.ib.connectAsync(
                host=self.host,
                port=self.port,
                clientId=self.client_id,
                timeout=10
            )

            # Verify connection
            if not self.ib.isConnected():
                raise ConnectionError("Connection established but not active")

            # Setup event handlers
            self._setup_event_handlers()

            # Start monitoring tasks
            await self._start_monitoring()

            self.health.state = ConnectionState.CONNECTED
            self.health.last_heartbeat = datetime.now()
            self.circuit_breaker.reset()

            logger.info(f"Connected to IBKR at {self.host}:{self.port}")

            # Request initial data
            self.ib.reqAccountUpdates()

            # Trigger callback
            if self.on_connected_callback:
                await self.on_connected_callback()

            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise ConnectionError(f"Failed to connect: {e}")

    async def disconnect(self):
        """Gracefully disconnect from IBKR"""
        self.health.state = ConnectionState.DISCONNECTED

        # Cancel monitoring tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._reconnect_task:
            self._reconnect_task.cancel()
        if self._monitor_task:
            self._monitor_task.cancel()

        # Disconnect
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()

        logger.info("Disconnected from IBKR")

        if self.on_disconnected_callback:
            await self.on_disconnected_callback()

    async def reconnect(self) -> bool:
        """
        Reconnect to IBKR with exponential backoff

        Returns:
            True if reconnected successfully
        """
        if self.health.state == ConnectionState.RECONNECTING:
            logger.warning("Already attempting to reconnect")
            return False

        self.health.state = ConnectionState.RECONNECTING
        self.health.reconnect_attempts = 0

        delay = self.reconnect_delay

        while self.health.reconnect_attempts < self.max_reconnect_attempts:
            self.health.reconnect_attempts += 1

            logger.info(f"Reconnection attempt {self.health.reconnect_attempts}"
                       f"/{self.max_reconnect_attempts}")

            # Disconnect existing connection
            if self.ib:
                try:
                    self.ib.disconnect()
                except:
                    pass

            # Attempt reconnection
            if await self.connect():
                self.health.total_reconnects += 1
                logger.info("Reconnection successful")
                return True

            # Exponential backoff
            await asyncio.sleep(delay)
            delay = min(delay * 2, 300)  # Max 5 minutes

        logger.error("Failed to reconnect after all attempts")
        self.health.state = ConnectionState.ERROR
        return False

    # === Event Handlers ===

    def _setup_event_handlers(self):
        """Setup IBKR event handlers"""
        if not self.ib:
            return

        # Connection events
        self.ib.connectedEvent += self._on_connected
        self.ib.disconnectedEvent += self._on_disconnected
        self.ib.errorEvent += self._on_error

        # Order events
        self.ib.orderStatusEvent += self._on_order_status
        self.ib.execDetailsEvent += self._on_exec_details

        # Market data events
        self.ib.tickerUpdateEvent += self._on_ticker_update

    def _on_connected(self):
        """Handle connection event"""
        logger.info("IBKR connection established")
        self.health.state = ConnectionState.CONNECTED
        self.health.last_heartbeat = datetime.now()

    def _on_disconnected(self):
        """Handle disconnection event"""
        logger.warning("IBKR connection lost")
        self.health.state = ConnectionState.DISCONNECTED

        # Trigger auto-reconnection
        if not self._reconnect_task or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self.reconnect())

    def _on_error(self, reqId: int, errorCode: int, errorString: str,
                  contract: Optional[Contract]):
        """Handle error events"""
        logger.error(f"IBKR Error: {errorCode} - {errorString}")

        self.health.errors.append({
            'timestamp': datetime.now(),
            'code': errorCode,
            'message': errorString,
            'contract': contract.symbol if contract else None
        })

        # Critical errors that require reconnection
        critical_errors = [504, 502, 1100, 1101, 1102]  # Connection lost codes
        if errorCode in critical_errors:
            logger.critical(f"Critical error detected: {errorCode}")
            if not self._reconnect_task or self._reconnect_task.done():
                self._reconnect_task = asyncio.create_task(self.reconnect())

        if self.on_error_callback:
            asyncio.create_task(self.on_error_callback(errorCode, errorString))

    def _on_order_status(self, trade):
        """Handle order status updates"""
        if self.db:
            # Update order in database
            asyncio.create_task(self._update_order_status(trade))

    def _on_exec_details(self, trade, fill):
        """Handle execution details"""
        logger.info(f"Order executed: {fill.contract.symbol} "
                   f"{fill.execution.side} {fill.execution.shares} "
                   f"@ {fill.execution.price}")

        if self.db:
            # Save trade to database
            asyncio.create_task(self._save_trade(trade, fill))

    def _on_ticker_update(self, ticker):
        """Handle ticker updates"""
        # Update market data streams
        if ticker.contract.symbol in self._market_data_streams:
            self._market_data_streams[ticker.contract.symbol] = {
                'last': ticker.last,
                'bid': ticker.bid,
                'ask': ticker.ask,
                'volume': ticker.volume,
                'timestamp': datetime.now()
            }

    # === Monitoring ===

    async def _start_monitoring(self):
        """Start monitoring tasks"""
        self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
        self._monitor_task = asyncio.create_task(self._connection_monitor())

    async def _heartbeat_monitor(self):
        """Monitor connection heartbeat"""
        while self.health.state in [ConnectionState.CONNECTED, ConnectionState.RECONNECTING]:
            try:
                if self.ib and self.ib.isConnected():
                    # Send heartbeat
                    start = time.time()
                    self.ib.reqCurrentTime()
                    self.health.latency_ms = (time.time() - start) * 1000
                    self.health.last_heartbeat = datetime.now()
                    self.health.messages_received += 1
                else:
                    # Connection lost
                    if self.health.state == ConnectionState.CONNECTED:
                        logger.warning("Heartbeat failed - connection lost")
                        self._on_disconnected()

                await asyncio.sleep(30)  # Check every 30 seconds

            except Exception as e:
                logger.error(f"Heartbeat monitor error: {e}")

    async def _connection_monitor(self):
        """Monitor overall connection health"""
        while self.health.state != ConnectionState.CLOSED:
            try:
                # Check if heartbeat is stale
                if self.health.last_heartbeat:
                    time_since_heartbeat = (datetime.now() - self.health.last_heartbeat).seconds

                    if time_since_heartbeat > 120:  # 2 minutes
                        logger.warning(f"No heartbeat for {time_since_heartbeat} seconds")

                        if self.health.state == ConnectionState.CONNECTED:
                            # Attempt reconnection
                            if not self._reconnect_task or self._reconnect_task.done():
                                self._reconnect_task = asyncio.create_task(self.reconnect())

                # Log health metrics periodically
                if self.health.messages_received % 100 == 0:
                    logger.info(f"Connection health: latency={self.health.latency_ms:.1f}ms, "
                               f"messages={self.health.messages_received}, "
                               f"orders={self.health.orders_placed}")

                await asyncio.sleep(60)  # Check every minute

            except Exception as e:
                logger.error(f"Connection monitor error: {e}")

    # === Enhanced Order Management ===

    async def place_bracket_order(self,
                                 ticker: str,
                                 action: str,
                                 quantity: int,
                                 entry_price: float,
                                 stop_loss: float,
                                 take_profit: float,
                                 idempotency_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Place a bracket order (entry + stop loss + take profit)

        Args:
            ticker: Stock symbol
            action: 'BUY' or 'SELL'
            quantity: Number of shares
            entry_price: Entry limit price
            stop_loss: Stop loss price
            take_profit: Take profit price
            idempotency_key: Unique key to prevent duplicate orders

        Returns:
            Dictionary with order IDs if successful
        """
        if not self._ensure_connected():
            return None

        try:
            # Check idempotency
            if idempotency_key and self.db:
                existing = self.db.get_session().query(Order).filter_by(
                    idempotency_key=idempotency_key
                ).first()
                if existing:
                    logger.info(f"Order already exists: {idempotency_key}")
                    return {'parent_id': existing.order_id}

            # Create contract
            contract = Stock(ticker, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)

            # Create bracket order
            bracket = BracketOrder(
                action=action,
                quantity=quantity,
                limitPrice=entry_price,
                stopLossPrice=stop_loss,
                takeProfitPrice=take_profit
            )

            # Place the bracket order
            trades = []
            for order in bracket:
                trade = self.ib.placeOrder(contract, order)
                trades.append(trade)
                await asyncio.sleep(0.1)

            # Wait for orders to be acknowledged
            await asyncio.sleep(1)

            # Verify orders
            parent_trade = trades[0]
            if parent_trade.orderStatus.status in ['Submitted', 'PreSubmitted']:
                logger.info(f"Bracket order placed for {ticker}")

                # Save to database
                if self.db:
                    await self._save_bracket_order(
                        trades, ticker, action, quantity,
                        entry_price, stop_loss, take_profit, idempotency_key
                    )

                self.health.orders_placed += 1

                return {
                    'parent_id': parent_trade.order.orderId,
                    'stop_loss_id': trades[1].order.orderId if len(trades) > 1 else None,
                    'take_profit_id': trades[2].order.orderId if len(trades) > 2 else None
                }
            else:
                logger.error(f"Bracket order failed: {parent_trade.orderStatus.status}")
                self.health.orders_failed += 1
                return None

        except Exception as e:
            logger.error(f"Error placing bracket order: {e}")
            self.health.orders_failed += 1
            self.health.errors.append({
                'timestamp': datetime.now(),
                'error': str(e),
                'type': 'order_placement'
            })
            return None

    async def cancel_order(self, order_id: int) -> bool:
        """
        Cancel an order

        Args:
            order_id: IBKR order ID

        Returns:
            True if cancelled successfully
        """
        if not self._ensure_connected():
            return False

        try:
            # Find the order
            for trade in self.ib.openTrades():
                if trade.order.orderId == order_id:
                    self.ib.cancelOrder(trade.order)
                    await asyncio.sleep(1)

                    # Update database
                    if self.db:
                        self.db.update_order_status(
                            str(order_id),
                            OrderStatus.CANCELLED,
                            cancelled_at=datetime.now()
                        )

                    logger.info(f"Order {order_id} cancelled")
                    return True

            logger.warning(f"Order {order_id} not found")
            return False

        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False

    async def modify_order(self, order_id: int, new_price: float) -> bool:
        """
        Modify an existing order

        Args:
            order_id: IBKR order ID
            new_price: New limit price

        Returns:
            True if modified successfully
        """
        if not self._ensure_connected():
            return False

        try:
            # Find and modify the order
            for trade in self.ib.openTrades():
                if trade.order.orderId == order_id:
                    trade.order.lmtPrice = new_price
                    self.ib.placeOrder(trade.contract, trade.order)
                    await asyncio.sleep(1)

                    logger.info(f"Order {order_id} modified to {new_price}")
                    return True

            logger.warning(f"Order {order_id} not found")
            return False

        except Exception as e:
            logger.error(f"Error modifying order: {e}")
            return False

    # === Real-time Data ===

    async def subscribe_market_data(self, ticker: str) -> bool:
        """
        Subscribe to real-time market data

        Args:
            ticker: Stock symbol

        Returns:
            True if subscribed successfully
        """
        if not self._ensure_connected():
            return False

        try:
            contract = Stock(ticker, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)

            # Request market data
            ticker_obj = self.ib.reqMktData(
                contract,
                genericTickList='',
                snapshot=False,
                regulatorySnapshot=False
            )

            self._market_data_streams[ticker] = ticker_obj

            logger.info(f"Subscribed to market data for {ticker}")
            return True

        except Exception as e:
            logger.error(f"Error subscribing to market data: {e}")
            return False

    def get_market_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get current market data for a ticker

        Args:
            ticker: Stock symbol

        Returns:
            Market data dictionary
        """
        if ticker in self._market_data_streams:
            ticker_obj = self._market_data_streams[ticker]
            return {
                'ticker': ticker,
                'last': ticker_obj.last,
                'bid': ticker_obj.bid,
                'ask': ticker_obj.ask,
                'volume': ticker_obj.volume,
                'high': ticker_obj.high,
                'low': ticker_obj.low,
                'close': ticker_obj.close,
                'timestamp': datetime.now()
            }
        return None

    # === Helper Methods ===

    def _ensure_connected(self) -> bool:
        """Ensure connection is active"""
        if not self.ib or not self.ib.isConnected():
            logger.error("Not connected to IBKR")
            return False
        return True

    async def _save_bracket_order(self, trades, ticker, action, quantity,
                                 entry_price, stop_loss, take_profit,
                                 idempotency_key):
        """Save bracket order to database"""
        if not self.db:
            return

        try:
            # Save parent order
            parent_trade = trades[0]
            parent_order = self.db.save_order({
                'order_id': str(parent_trade.order.orderId),
                'idempotency_key': idempotency_key,
                'ticker': ticker,
                'action': action,
                'order_type': 'LIMIT',
                'quantity': quantity,
                'limit_price': entry_price,
                'stop_loss_price': stop_loss,
                'take_profit_price': take_profit,
                'status': OrderStatus.SUBMITTED,
                'submitted_at': datetime.now()
            })

            # Save child orders
            if len(trades) > 1:
                # Stop loss order
                stop_trade = trades[1]
                self.db.save_order({
                    'order_id': str(stop_trade.order.orderId),
                    'ticker': ticker,
                    'action': 'SELL' if action == 'BUY' else 'BUY',
                    'order_type': 'STOP',
                    'quantity': quantity,
                    'stop_price': stop_loss,
                    'parent_order_id': parent_order.id,
                    'status': OrderStatus.PENDING
                })

            if len(trades) > 2:
                # Take profit order
                profit_trade = trades[2]
                self.db.save_order({
                    'order_id': str(profit_trade.order.orderId),
                    'ticker': ticker,
                    'action': 'SELL' if action == 'BUY' else 'BUY',
                    'order_type': 'LIMIT',
                    'quantity': quantity,
                    'limit_price': take_profit,
                    'parent_order_id': parent_order.id,
                    'status': OrderStatus.PENDING
                })

        except Exception as e:
            logger.error(f"Error saving bracket order: {e}")

    async def _update_order_status(self, trade):
        """Update order status in database"""
        if not self.db:
            return

        try:
            status_map = {
                'Submitted': OrderStatus.SUBMITTED,
                'Filled': OrderStatus.FILLED,
                'PartiallyFilled': OrderStatus.PARTIALLY_FILLED,
                'Cancelled': OrderStatus.CANCELLED,
                'Inactive': OrderStatus.REJECTED
            }

            db_status = status_map.get(trade.orderStatus.status, OrderStatus.PENDING)

            self.db.update_order_status(
                order_id=str(trade.order.orderId),
                status=db_status,
                filled_quantity=trade.orderStatus.filled,
                avg_fill_price=trade.orderStatus.avgFillPrice
            )

        except Exception as e:
            logger.error(f"Error updating order status: {e}")

    async def _save_trade(self, trade, fill):
        """Save executed trade to database"""
        if not self.db:
            return

        try:
            with self.db.get_session() as session:
                from ..core.database import Trade

                trade_record = Trade(
                    order_id=trade.order.orderId,
                    ticker=fill.contract.symbol,
                    action=fill.execution.side,
                    quantity=fill.execution.shares,
                    price=fill.execution.price,
                    commission=fill.commissionReport.commission if fill.commissionReport else 0,
                    executed_at=datetime.now()
                )

                session.add(trade_record)
                session.commit()

        except Exception as e:
            logger.error(f"Error saving trade: {e}")

    def get_health_metrics(self) -> Dict[str, Any]:
        """Get connection health metrics"""
        return {
            'state': self.health.state.value,
            'connected': self.health.state == ConnectionState.CONNECTED,
            'last_heartbeat': self.health.last_heartbeat.isoformat() if self.health.last_heartbeat else None,
            'latency_ms': self.health.latency_ms,
            'reconnect_attempts': self.health.reconnect_attempts,
            'total_reconnects': self.health.total_reconnects,
            'orders_placed': self.health.orders_placed,
            'orders_failed': self.health.orders_failed,
            'recent_errors': list(self.health.errors)[-5:] if self.health.errors else []
        }


# Example usage
async def main():
    """Example of using the resilient IBKR connector"""
    from ..core.database import DatabaseManager

    # Initialize database
    db = DatabaseManager("postgresql://trader:password@localhost/trading_db")

    # Create connector
    connector = ResilientIBKRConnector(
        host="127.0.0.1",
        port=7497,  # Paper trading
        db_manager=db
    )

    # Set callbacks
    async def on_connected():
        logger.info("Connected callback triggered")

    async def on_error(code, message):
        logger.error(f"Error callback: {code} - {message}")

    connector.on_connected_callback = on_connected
    connector.on_error_callback = on_error

    # Connect
    if await connector.connect():
        # Subscribe to market data
        await connector.subscribe_market_data("AAPL")

        # Place a bracket order
        result = await connector.place_bracket_order(
            ticker="AAPL",
            action="BUY",
            quantity=100,
            entry_price=150.00,
            stop_loss=145.00,
            take_profit=160.00
        )

        if result:
            logger.info(f"Bracket order placed: {result}")

        # Monitor for 5 minutes
        for _ in range(10):
            await asyncio.sleep(30)
            health = connector.get_health_metrics()
            logger.info(f"Health: {health}")

        # Disconnect
        await connector.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())