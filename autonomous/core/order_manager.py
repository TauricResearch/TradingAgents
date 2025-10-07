"""
Order Management System
=======================

Comprehensive order lifecycle management with state machine,
validation, and execution tracking.
"""

import asyncio
import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from dataclasses import dataclass, field
import json

from transitions import Machine
from pydantic import BaseModel, Field, validator

from .database import (
    DatabaseManager, Order, OrderStatus, Trade,
    Signal, Position
)

logger = logging.getLogger(__name__)


class OrderType(str, Enum):
    """Order type enumeration"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TRAILING_STOP = "TRAILING_STOP"
    BRACKET = "BRACKET"


class OrderSide(str, Enum):
    """Order side enumeration"""
    BUY = "BUY"
    SELL = "SELL"


class OrderValidationError(Exception):
    """Order validation error"""
    pass


class OrderExecutionError(Exception):
    """Order execution error"""
    pass


# === Pydantic Models for Validation ===

class OrderRequest(BaseModel):
    """Order request with validation"""
    ticker: str = Field(..., min_length=1, max_length=10)
    side: OrderSide
    quantity: int = Field(..., gt=0, le=100000)
    order_type: OrderType
    limit_price: Optional[Decimal] = Field(None, gt=0, le=1000000)
    stop_price: Optional[Decimal] = Field(None, gt=0, le=1000000)
    time_in_force: str = Field(default="DAY")  # DAY, GTC, IOC, FOK
    idempotency_key: Optional[str] = None
    signal_id: Optional[int] = None
    notes: Optional[str] = None

    # Risk management
    stop_loss: Optional[Decimal] = Field(None, gt=0)
    take_profit: Optional[Decimal] = Field(None, gt=0)
    max_slippage: Optional[Decimal] = Field(default=Decimal("0.01"))  # 1%

    @validator('ticker')
    def validate_ticker(cls, v):
        """Validate ticker symbol"""
        # Basic validation - alphanumeric only
        if not v.isalnum():
            raise ValueError(f"Invalid ticker symbol: {v}")
        return v.upper()

    @validator('limit_price')
    def validate_limit_price(cls, v, values):
        """Validate limit price for limit orders"""
        if values.get('order_type') in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
            if v is None:
                raise ValueError("Limit price required for limit orders")
        return v

    @validator('stop_price')
    def validate_stop_price(cls, v, values):
        """Validate stop price for stop orders"""
        if values.get('order_type') in [OrderType.STOP, OrderType.STOP_LIMIT,
                                        OrderType.TRAILING_STOP]:
            if v is None:
                raise ValueError("Stop price required for stop orders")
        return v

    class Config:
        use_enum_values = True


@dataclass
class OrderContext:
    """Context for order execution"""
    request: OrderRequest
    order_id: Optional[str] = None
    ibkr_order_id: Optional[int] = None
    db_order: Optional[Order] = None
    position: Optional[Position] = None
    signal: Optional[Signal] = None
    validation_errors: List[str] = field(default_factory=list)
    execution_errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


# === Order State Machine ===

class OrderStateMachine:
    """
    State machine for order lifecycle management

    States:
    - pending: Initial state
    - validated: Order validated
    - risk_checked: Risk checks passed
    - submitted: Sent to broker
    - acknowledged: Broker acknowledged
    - partially_filled: Partially executed
    - filled: Fully executed
    - cancelled: Cancelled
    - rejected: Rejected by broker or risk
    - failed: System failure
    """

    # State transitions
    states = [
        'pending', 'validated', 'risk_checked', 'submitted',
        'acknowledged', 'partially_filled', 'filled',
        'cancelled', 'rejected', 'failed'
    ]

    # Valid transitions
    transitions = [
        # Forward flow
        {'trigger': 'validate', 'source': 'pending', 'dest': 'validated'},
        {'trigger': 'check_risk', 'source': 'validated', 'dest': 'risk_checked'},
        {'trigger': 'submit', 'source': 'risk_checked', 'dest': 'submitted'},
        {'trigger': 'acknowledge', 'source': 'submitted', 'dest': 'acknowledged'},
        {'trigger': 'partial_fill', 'source': ['acknowledged', 'partially_filled'],
         'dest': 'partially_filled'},
        {'trigger': 'fill', 'source': ['acknowledged', 'partially_filled'],
         'dest': 'filled'},

        # Cancellation
        {'trigger': 'cancel', 'source': ['pending', 'validated', 'risk_checked',
                                         'submitted', 'acknowledged', 'partially_filled'],
         'dest': 'cancelled'},

        # Rejection
        {'trigger': 'reject', 'source': ['validated', 'risk_checked', 'submitted'],
         'dest': 'rejected'},

        # Failure
        {'trigger': 'fail', 'source': '*', 'dest': 'failed'},
    ]

    def __init__(self, context: OrderContext):
        """Initialize state machine"""
        self.context = context
        self.machine = Machine(
            model=self,
            states=OrderStateMachine.states,
            transitions=OrderStateMachine.transitions,
            initial='pending',
            auto_transitions=False,
            send_event=True,
            after_state_change=self._on_state_change
        )

    def _on_state_change(self, event):
        """Log state changes"""
        logger.info(f"Order {self.context.order_id}: {event.transition.source} "
                   f"-> {event.transition.dest}")


# === Order Manager ===

class OrderManager:
    """
    Manages order lifecycle from creation to execution
    """

    def __init__(self,
                 db_manager: DatabaseManager,
                 ibkr_connector,
                 risk_manager=None):
        """
        Initialize order manager

        Args:
            db_manager: Database manager
            ibkr_connector: IBKR connector instance
            risk_manager: Risk manager instance
        """
        self.db = db_manager
        self.ibkr = ibkr_connector
        self.risk_manager = risk_manager

        # Track active orders
        self.active_orders: Dict[str, OrderStateMachine] = {}

        # Execution metrics
        self.metrics = {
            'orders_created': 0,
            'orders_submitted': 0,
            'orders_filled': 0,
            'orders_cancelled': 0,
            'orders_rejected': 0,
            'orders_failed': 0,
            'total_volume': 0,
            'total_commission': Decimal('0.00')
        }

    async def create_order(self, request: OrderRequest) -> Tuple[bool, OrderContext]:
        """
        Create and process a new order

        Args:
            request: Order request

        Returns:
            Tuple of (success, order context)
        """
        try:
            # Create order context
            context = OrderContext(
                request=request,
                order_id=str(uuid.uuid4())
            )

            # Create state machine
            state_machine = OrderStateMachine(context)
            self.active_orders[context.order_id] = state_machine

            self.metrics['orders_created'] += 1

            # Process through state machine
            success = await self._process_order(state_machine)

            return success, context

        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return False, None

    async def _process_order(self, state_machine: OrderStateMachine) -> bool:
        """
        Process order through state machine

        Args:
            state_machine: Order state machine

        Returns:
            True if order successfully submitted
        """
        context = state_machine.context

        try:
            # Step 1: Validate
            if not await self._validate_order(state_machine):
                state_machine.reject()
                return False

            state_machine.validate()

            # Step 2: Risk check
            if not await self._check_risk(state_machine):
                state_machine.reject()
                return False

            state_machine.check_risk()

            # Step 3: Submit to broker
            if not await self._submit_order(state_machine):
                state_machine.fail()
                return False

            state_machine.submit()

            # Step 4: Wait for acknowledgment
            if not await self._wait_for_acknowledgment(state_machine):
                state_machine.fail()
                return False

            state_machine.acknowledge()

            return True

        except Exception as e:
            logger.error(f"Order processing error: {e}")
            state_machine.fail()
            await self._save_order_state(state_machine)
            return False

    async def _validate_order(self, state_machine: OrderStateMachine) -> bool:
        """
        Validate order request

        Args:
            state_machine: Order state machine

        Returns:
            True if valid
        """
        context = state_machine.context
        request = context.request

        # Check idempotency
        if request.idempotency_key:
            existing = await self._check_idempotency(request.idempotency_key)
            if existing:
                context.validation_errors.append("Duplicate order")
                return False

        # Market hours check
        if not self._is_market_open():
            if request.order_type == OrderType.MARKET:
                context.validation_errors.append("Market closed for market orders")
                return False

        # Position validation
        if request.side == OrderSide.SELL:
            position = await self._get_position(request.ticker)
            if not position or position.shares < request.quantity:
                context.validation_errors.append("Insufficient shares to sell")
                return False
            context.position = position

        # Price validation
        market_price = await self._get_market_price(request.ticker)
        if market_price:
            # Check for unreasonable prices
            if request.limit_price:
                price_diff = abs(float(request.limit_price) - market_price) / market_price
                if price_diff > 0.10:  # More than 10% away
                    context.validation_errors.append(
                        f"Limit price {request.limit_price} is >10% from market {market_price}"
                    )

        # Check trading halts
        if await self._is_halted(request.ticker):
            context.validation_errors.append(f"{request.ticker} is halted")
            return False

        return len(context.validation_errors) == 0

    async def _check_risk(self, state_machine: OrderStateMachine) -> bool:
        """
        Perform risk checks

        Args:
            state_machine: Order state machine

        Returns:
            True if risk checks pass
        """
        if not self.risk_manager:
            return True

        context = state_machine.context
        request = context.request

        try:
            # Check with risk manager
            risk_result = await self.risk_manager.check_order(
                ticker=request.ticker,
                side=request.side.value,
                quantity=request.quantity,
                price=float(request.limit_price or 0)
            )

            if not risk_result['approved']:
                context.validation_errors.extend(risk_result.get('reasons', []))
                return False

            # Add risk metadata
            context.metadata['risk_score'] = risk_result.get('risk_score')
            context.metadata['position_impact'] = risk_result.get('position_impact')

            return True

        except Exception as e:
            logger.error(f"Risk check error: {e}")
            context.validation_errors.append(f"Risk check failed: {e}")
            return False

    async def _submit_order(self, state_machine: OrderStateMachine) -> bool:
        """
        Submit order to broker

        Args:
            state_machine: Order state machine

        Returns:
            True if submitted successfully
        """
        context = state_machine.context
        request = context.request

        try:
            # Prepare for bracket order if stop loss/take profit specified
            if request.stop_loss and request.take_profit:
                result = await self.ibkr.place_bracket_order(
                    ticker=request.ticker,
                    action=request.side.value,
                    quantity=request.quantity,
                    entry_price=float(request.limit_price),
                    stop_loss=float(request.stop_loss),
                    take_profit=float(request.take_profit),
                    idempotency_key=request.idempotency_key
                )

                if result:
                    context.ibkr_order_id = result['parent_id']
                    context.metadata['bracket_order'] = result

            else:
                # Regular order
                order_result = await self.ibkr.place_order(
                    ticker=request.ticker,
                    action=request.side.value,
                    quantity=request.quantity,
                    order_type=request.order_type.value,
                    limit_price=float(request.limit_price) if request.limit_price else None,
                    stop_price=float(request.stop_price) if request.stop_price else None
                )

                if order_result:
                    context.ibkr_order_id = order_result

            if context.ibkr_order_id:
                # Save to database
                await self._save_order_to_db(state_machine)
                self.metrics['orders_submitted'] += 1
                return True

            context.execution_errors.append("Failed to submit order to broker")
            return False

        except Exception as e:
            logger.error(f"Order submission error: {e}")
            context.execution_errors.append(str(e))
            return False

    async def _wait_for_acknowledgment(self, state_machine: OrderStateMachine,
                                      timeout: int = 5) -> bool:
        """
        Wait for broker acknowledgment

        Args:
            state_machine: Order state machine
            timeout: Timeout in seconds

        Returns:
            True if acknowledged
        """
        context = state_machine.context
        start_time = datetime.now()

        while (datetime.now() - start_time).seconds < timeout:
            # Check order status with broker
            if context.ibkr_order_id:
                # In real implementation, would check actual order status
                # For now, assume acknowledged
                return True

            await asyncio.sleep(0.5)

        context.execution_errors.append("Acknowledgment timeout")
        return False

    async def update_order_status(self, order_id: str,
                                 new_status: str,
                                 **kwargs):
        """
        Update order status from broker events

        Args:
            order_id: Order ID
            new_status: New status
            **kwargs: Additional status info
        """
        if order_id not in self.active_orders:
            return

        state_machine = self.active_orders[order_id]
        context = state_machine.context

        try:
            # Update state machine
            if new_status == 'FILLED':
                state_machine.fill()
                self.metrics['orders_filled'] += 1
                self.metrics['total_volume'] += context.request.quantity

            elif new_status == 'PARTIALLY_FILLED':
                state_machine.partial_fill()
                context.metadata['filled_quantity'] = kwargs.get('filled_quantity', 0)

            elif new_status == 'CANCELLED':
                state_machine.cancel()
                self.metrics['orders_cancelled'] += 1

            elif new_status == 'REJECTED':
                state_machine.reject()
                self.metrics['orders_rejected'] += 1

            # Update database
            if context.db_order:
                self.db.update_order_status(
                    order_id=context.ibkr_order_id,
                    status=OrderStatus[new_status],
                    **kwargs
                )

            # Clean up if terminal state
            if new_status in ['FILLED', 'CANCELLED', 'REJECTED', 'FAILED']:
                del self.active_orders[order_id]

        except Exception as e:
            logger.error(f"Error updating order status: {e}")

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order

        Args:
            order_id: Order ID

        Returns:
            True if cancelled successfully
        """
        if order_id not in self.active_orders:
            logger.warning(f"Order {order_id} not found")
            return False

        state_machine = self.active_orders[order_id]
        context = state_machine.context

        try:
            # Cancel with broker
            if context.ibkr_order_id:
                success = await self.ibkr.cancel_order(context.ibkr_order_id)
                if success:
                    state_machine.cancel()
                    await self._save_order_state(state_machine)
                    del self.active_orders[order_id]
                    return True

            return False

        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False

    # === Helper Methods ===

    async def _check_idempotency(self, idempotency_key: str) -> Optional[Order]:
        """Check for duplicate orders"""
        with self.db.get_session() as session:
            return session.query(Order).filter_by(
                idempotency_key=idempotency_key
            ).first()

    async def _get_position(self, ticker: str) -> Optional[Position]:
        """Get current position for ticker"""
        with self.db.get_session() as session:
            return session.query(Position).filter_by(ticker=ticker).first()

    async def _get_market_price(self, ticker: str) -> Optional[float]:
        """Get current market price"""
        market_data = self.ibkr.get_market_data(ticker)
        if market_data:
            return market_data['last']
        return None

    async def _is_halted(self, ticker: str) -> bool:
        """Check if ticker is halted"""
        # Would check with market data provider
        return False

    def _is_market_open(self) -> bool:
        """Check if market is open"""
        now = datetime.now()
        # Simplified check - would use market calendar
        return (9 <= now.hour < 16 and
                now.weekday() < 5)  # Mon-Fri

    async def _save_order_to_db(self, state_machine: OrderStateMachine):
        """Save order to database"""
        context = state_machine.context
        request = context.request

        order_data = {
            'order_id': str(context.ibkr_order_id),
            'idempotency_key': request.idempotency_key,
            'ticker': request.ticker,
            'action': request.side.value,
            'order_type': request.order_type.value,
            'quantity': request.quantity,
            'limit_price': request.limit_price,
            'stop_price': request.stop_price,
            'stop_loss_price': request.stop_loss,
            'take_profit_price': request.take_profit,
            'status': OrderStatus.SUBMITTED,
            'signal_id': request.signal_id,
            'notes': request.notes,
            'submitted_at': datetime.now()
        }

        context.db_order = self.db.save_order(order_data)

    async def _save_order_state(self, state_machine: OrderStateMachine):
        """Save order state to database"""
        context = state_machine.context
        if context.db_order:
            # Update order with final state
            self.db.update_order_status(
                order_id=str(context.ibkr_order_id),
                status=OrderStatus[state_machine.state.upper()],
                notes=json.dumps({
                    'validation_errors': context.validation_errors,
                    'execution_errors': context.execution_errors,
                    'metadata': context.metadata
                })
            )

    def get_active_orders(self) -> List[Dict[str, Any]]:
        """Get all active orders"""
        active = []
        for order_id, state_machine in self.active_orders.items():
            context = state_machine.context
            active.append({
                'order_id': order_id,
                'ticker': context.request.ticker,
                'side': context.request.side.value,
                'quantity': context.request.quantity,
                'state': state_machine.state,
                'created_at': context.created_at.isoformat()
            })
        return active

    def get_metrics(self) -> Dict[str, Any]:
        """Get order manager metrics"""
        return {
            **self.metrics,
            'active_orders': len(self.active_orders),
            'fill_rate': (self.metrics['orders_filled'] /
                         max(self.metrics['orders_submitted'], 1)) * 100
        }


# Example usage
async def main():
    """Example of using the order manager"""
    from .database import DatabaseManager
    from ..connectors.ibkr_resilient import ResilientIBKRConnector

    # Initialize components
    db = DatabaseManager("postgresql://trader:password@localhost/trading_db")
    ibkr = ResilientIBKRConnector(db_manager=db)
    order_manager = OrderManager(db, ibkr)

    # Create an order
    order_request = OrderRequest(
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("150.00"),
        stop_loss=Decimal("145.00"),
        take_profit=Decimal("160.00"),
        idempotency_key=str(uuid.uuid4())
    )

    success, context = await order_manager.create_order(order_request)

    if success:
        logger.info(f"Order created: {context.order_id}")
    else:
        logger.error(f"Order failed: {context.validation_errors}")

    # Check metrics
    print(order_manager.get_metrics())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())