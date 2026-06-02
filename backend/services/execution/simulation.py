"""SimulationTrader — wraps MockTradingEngine for paper trading."""
import logging
import sys
import os
from typing import Optional

from .base import BaseTraderInterface, OrderRequest, OrderResult

_logger = logging.getLogger(__name__)


def _ensure_project_in_path():
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    )
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


class SimulationTrader(BaseTraderInterface):
    """
    Paper-trading implementation backed by MockTradingEngine.

    Every call is forwarded to the existing mock_trading engine;
    no real broker API is contacted.
    """

    def __init__(self, portfolio_id: int = 1, initial_capital: float = 100_000.0, db=None):
        _ensure_project_in_path()
        from tradingagents.mock_trading.engine import MockTradingEngine
        from tradingagents.mock_trading.database import TradingDatabase

        if db is None:
            import tempfile
            _cache = os.environ.get(
                "TRADINGAGENTS_DATA_CACHE_DIR",
                tempfile.gettempdir(),
            )
            import pathlib
            pathlib.Path(_cache).mkdir(parents=True, exist_ok=True)
            db = TradingDatabase(db_path=str(pathlib.Path(_cache) / "mock_trading.db"))
        self._db = db
        self._engine = MockTradingEngine(
            portfolio_id=portfolio_id,
            initial_capital=initial_capital,
            db=self._db,
            slippage_tolerance_pct=1.0,
        )
        self._portfolio_id = portfolio_id

    @property
    def mode(self) -> str:
        return "simulation"

    @property
    def broker_name(self) -> str:
        return "simulation"

    def get_current_price(self, ticker: str) -> Optional[float]:
        try:
            return self._engine.get_current_price(ticker)
        except Exception as e:
            _logger.warning("Could not fetch price for %s: %s", ticker, e)
            return None

    def place_order(self, request: OrderRequest) -> OrderResult:
        try:
            from tradingagents.mock_trading.order_manager import PriceType

            if request.action == "BUY":
                order_id = self._engine.create_buy_order(
                    ticker=request.ticker,
                    quantity=request.quantity,
                    price_type=PriceType.CLOSE,
                    reference_price=request.reference_price,
                )
            else:
                order_id = self._engine.create_sell_order(
                    ticker=request.ticker,
                    quantity=request.quantity,
                    price_type=PriceType.CLOSE,
                    reference_price=request.reference_price,
                )

            execution_price = self.get_current_price(request.ticker) or request.reference_price
            success = self._engine.execute_order(
                order_id=order_id,
                execution_price=execution_price,
                quantity_filled=request.quantity,
                available_volume=request.quantity * 10,
                fees=0.0,
            )

            if success:
                return OrderResult(
                    order_id=order_id,
                    status="FILLED",
                    filled_price=execution_price,
                    filled_quantity=request.quantity,
                    message="Simulation order filled",
                )
            else:
                order = self._engine.order_mgr.get_order(order_id)
                return OrderResult(
                    order_id=order_id,
                    status=order.status.value if order else "REJECTED",
                    filled_price=None,
                    filled_quantity=None,
                    message="Order rejected or slippage exceeded",
                )
        except Exception as e:
            _logger.error("Simulation order failed for %s: %s", request.ticker, e, exc_info=True)
            return OrderResult(
                order_id="",
                status="REJECTED",
                filled_price=None,
                filled_quantity=None,
                message=str(e),
            )

    def cancel_order(self, order_id: str) -> bool:
        try:
            order = self._engine.order_mgr.get_order(order_id)
            if order and order.status.value == "PENDING":
                order.status = __import__(
                    "tradingagents.mock_trading.order_manager", fromlist=["OrderStatus"]
                ).OrderStatus.REJECTED
                return True
            return False
        except Exception:
            return False

    def get_balance(self) -> float:
        return self._engine.portfolio_mgr.cash_available

    def get_positions(self) -> dict[str, dict]:
        return dict(self._engine.portfolio_mgr.holdings)
