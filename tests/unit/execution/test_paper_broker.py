"""Tests for Paper Broker implementation.

Issue #26: [EXEC-25] Paper broker - simulation mode
"""

from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from tradingagents.execution import (
    PaperBroker,
    OrderRequest,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    AssetClass,
    PositionSide,
    ConnectionError,
    OrderError,
    InvalidOrderError,
    InsufficientFundsError,
)


class TestPaperBrokerInit:
    """Test PaperBroker initialization."""

    def test_default_initialization(self):
        """Test default broker initialization."""
        broker = PaperBroker()
        assert broker.name == "Paper"
        assert broker.initial_cash == Decimal("100000")
        assert broker.cash == Decimal("100000")
        assert broker.is_paper_trading is True
        assert broker.is_connected is False

    def test_custom_initial_cash(self):
        """Test initialization with custom initial cash."""
        broker = PaperBroker(initial_cash=Decimal("50000"))
        assert broker.initial_cash == Decimal("50000")
        assert broker.cash == Decimal("50000")

    def test_custom_slippage(self):
        """Test initialization with custom slippage."""
        broker = PaperBroker(slippage_percent=Decimal("0.1"))
        assert broker._slippage_percent == Decimal("0.1")

    def test_custom_fill_probability(self):
        """Test initialization with custom fill probability."""
        broker = PaperBroker(fill_probability=0.5)
        assert broker._fill_probability == 0.5

    def test_market_closed_initialization(self):
        """Test initialization with market closed."""
        broker = PaperBroker(market_open=False)
        assert broker._market_open is False

    def test_supported_asset_classes(self):
        """Test supported asset classes include all types."""
        broker = PaperBroker()
        assert AssetClass.EQUITY in broker.supported_asset_classes
        assert AssetClass.ETF in broker.supported_asset_classes
        assert AssetClass.CRYPTO in broker.supported_asset_classes
        assert AssetClass.FUTURE in broker.supported_asset_classes
        assert AssetClass.OPTION in broker.supported_asset_classes
        assert AssetClass.FOREX in broker.supported_asset_classes

    def test_custom_price_provider(self):
        """Test initialization with custom price provider."""
        def price_provider(symbol: str) -> Decimal:
            return Decimal("123.45")

        broker = PaperBroker(price_provider=price_provider)
        assert broker.get_simulated_price("ANY") == Decimal("123.45")


class TestPaperBrokerConnection:
    """Test PaperBroker connection methods."""

    @pytest.mark.asyncio
    async def test_connect_succeeds(self):
        """Test connect always succeeds."""
        broker = PaperBroker()
        result = await broker.connect()
        assert result is True
        assert broker.is_connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test disconnect."""
        broker = PaperBroker()
        await broker.connect()
        await broker.disconnect()
        assert broker.is_connected is False

    @pytest.mark.asyncio
    async def test_multiple_connects(self):
        """Test multiple connects work."""
        broker = PaperBroker()
        await broker.connect()
        await broker.connect()
        assert broker.is_connected is True


class TestPaperBrokerMarketStatus:
    """Test PaperBroker market status."""

    @pytest.mark.asyncio
    async def test_market_open_by_default(self):
        """Test market is open by default."""
        broker = PaperBroker()
        await broker.connect()
        assert await broker.is_market_open() is True

    @pytest.mark.asyncio
    async def test_market_closed(self):
        """Test market closed simulation."""
        broker = PaperBroker(market_open=False)
        await broker.connect()
        assert await broker.is_market_open() is False

    @pytest.mark.asyncio
    async def test_set_market_open(self):
        """Test changing market open status."""
        broker = PaperBroker(market_open=False)
        broker.set_market_open(True)
        await broker.connect()
        assert await broker.is_market_open() is True


class TestPaperBrokerPrices:
    """Test PaperBroker price simulation."""

    def test_set_and_get_price(self):
        """Test setting and getting prices."""
        broker = PaperBroker()
        broker.set_price("TEST", Decimal("99.99"))
        assert broker.get_simulated_price("TEST") == Decimal("99.99")

    def test_default_prices(self):
        """Test default prices for common symbols."""
        broker = PaperBroker()
        assert broker.get_simulated_price("AAPL") == Decimal("175.00")
        assert broker.get_simulated_price("MSFT") == Decimal("380.00")
        assert broker.get_simulated_price("SPY") == Decimal("470.00")

    def test_crypto_default_prices(self):
        """Test default crypto prices."""
        broker = PaperBroker()
        assert broker.get_simulated_price("BTCUSD") == Decimal("45000.00")
        assert broker.get_simulated_price("ETHUSD") == Decimal("2500.00")

    def test_futures_default_prices(self):
        """Test default futures prices."""
        broker = PaperBroker()
        assert broker.get_simulated_price("ES") == Decimal("4700.00")
        assert broker.get_simulated_price("NQ") == Decimal("16500.00")

    def test_unknown_symbol_generates_price(self):
        """Test unknown symbols generate random prices."""
        broker = PaperBroker()
        price = broker.get_simulated_price("UNKNOWN")
        # Should be around 100 +/- 10
        assert Decimal("80") < price < Decimal("120")


class TestPaperBrokerAccount:
    """Test PaperBroker account methods."""

    @pytest.mark.asyncio
    async def test_get_account_requires_connection(self):
        """Test get_account requires connection."""
        broker = PaperBroker()
        with pytest.raises(ConnectionError, match="Not connected"):
            await broker.get_account()

    @pytest.mark.asyncio
    async def test_get_account_basic(self):
        """Test basic account information."""
        broker = PaperBroker(initial_cash=Decimal("50000"))
        await broker.connect()

        account = await broker.get_account()
        assert account.account_type == "paper"
        assert account.status == "active"
        assert account.cash == Decimal("50000")
        assert account.portfolio_value == Decimal("50000")
        assert account.buying_power == Decimal("50000")
        assert account.account_id.startswith("PAPER-")

    @pytest.mark.asyncio
    async def test_get_account_with_positions(self):
        """Test account includes position values."""
        broker = PaperBroker(initial_cash=Decimal("100000"))
        broker.set_price("AAPL", Decimal("150"))
        await broker.connect()

        # Buy some shares
        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        account = await broker.get_account()
        # Cash reduced by purchase
        assert account.cash < Decimal("100000")
        # Portfolio includes position
        assert account.portfolio_value > account.cash


class TestPaperBrokerOrders:
    """Test PaperBroker order methods."""

    @pytest.mark.asyncio
    async def test_submit_market_buy_order(self):
        """Test submitting market buy order."""
        broker = PaperBroker(initial_cash=Decimal("100000"))
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        order = await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.quantity == Decimal("10")
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == Decimal("10")
        assert order.broker_order_id.startswith("PAPER-")

    @pytest.mark.asyncio
    async def test_submit_market_sell_order(self):
        """Test submitting market sell order."""
        broker = PaperBroker(initial_cash=Decimal("100000"))
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        # Buy first
        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        # Then sell
        order = await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.SELL, Decimal("5"))
        )

        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == Decimal("5")

    @pytest.mark.asyncio
    async def test_submit_limit_order_fills(self):
        """Test limit order that should fill."""
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        # Limit above market price - should fill
        order = await broker.submit_order(
            OrderRequest.limit("AAPL", OrderSide.BUY, Decimal("10"), Decimal("110"))
        )

        assert order.status == OrderStatus.FILLED
        assert order.filled_avg_price == Decimal("110")

    @pytest.mark.asyncio
    async def test_submit_limit_order_no_fill(self):
        """Test limit order that shouldn't fill."""
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        # Limit below market price - shouldn't fill
        order = await broker.submit_order(
            OrderRequest.limit("AAPL", OrderSide.BUY, Decimal("10"), Decimal("90"))
        )

        assert order.status == OrderStatus.NEW
        assert order.filled_quantity == Decimal("0")

    @pytest.mark.asyncio
    async def test_order_requires_connection(self):
        """Test order submission requires connection."""
        broker = PaperBroker()
        with pytest.raises(ConnectionError, match="Not connected"):
            await broker.submit_order(
                OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
            )

    @pytest.mark.asyncio
    async def test_invalid_order_quantity(self):
        """Test invalid order quantity."""
        broker = PaperBroker()
        await broker.connect()

        with pytest.raises(InvalidOrderError, match="quantity must be positive"):
            await broker.submit_order(
                OrderRequest.market("AAPL", OrderSide.BUY, Decimal("-10"))
            )

    @pytest.mark.asyncio
    async def test_insufficient_funds(self):
        """Test insufficient funds error."""
        broker = PaperBroker(initial_cash=Decimal("100"))
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        with pytest.raises(InsufficientFundsError, match="Insufficient funds"):
            await broker.submit_order(
                OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
            )

    @pytest.mark.asyncio
    async def test_slippage_on_buy(self):
        """Test slippage applied to buy orders."""
        broker = PaperBroker(slippage_percent=Decimal("1.0"))
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        order = await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("1"))
        )

        # 1% slippage on $100 = $101
        assert order.filled_avg_price == Decimal("101.00")

    @pytest.mark.asyncio
    async def test_slippage_on_sell(self):
        """Test slippage applied to sell orders."""
        broker = PaperBroker(slippage_percent=Decimal("1.0"))
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        # Buy first
        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        # Sell with slippage
        order = await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.SELL, Decimal("5"))
        )

        # 1% slippage on $100 = $99
        assert order.filled_avg_price == Decimal("99.00")


class TestPaperBrokerFillProbability:
    """Test PaperBroker fill probability."""

    @pytest.mark.asyncio
    async def test_zero_fill_probability(self):
        """Test orders don't fill with 0% probability."""
        broker = PaperBroker(fill_probability=0.0)
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        order = await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        assert order.status == OrderStatus.NEW
        assert order.filled_quantity == Decimal("0")

    @pytest.mark.asyncio
    async def test_full_fill_probability(self):
        """Test orders always fill with 100% probability."""
        broker = PaperBroker(fill_probability=1.0)
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        order = await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        assert order.status == OrderStatus.FILLED


class TestPaperBrokerCancelOrder:
    """Test PaperBroker cancel order."""

    @pytest.mark.asyncio
    async def test_cancel_unfilled_order(self):
        """Test cancelling unfilled order."""
        broker = PaperBroker(fill_probability=0.0)
        await broker.connect()

        order = await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        cancelled = await broker.cancel_order(order.broker_order_id)
        assert cancelled.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_filled_order_fails(self):
        """Test cannot cancel filled order."""
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("10"))
        await broker.connect()

        order = await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        with pytest.raises(OrderError, match="Cannot cancel filled order"):
            await broker.cancel_order(order.broker_order_id)

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order(self):
        """Test cancelling nonexistent order."""
        broker = PaperBroker()
        await broker.connect()

        with pytest.raises(OrderError, match="not found"):
            await broker.cancel_order("INVALID-123")


class TestPaperBrokerReplaceOrder:
    """Test PaperBroker replace order."""

    @pytest.mark.asyncio
    async def test_replace_order(self):
        """Test replacing an order."""
        broker = PaperBroker(fill_probability=0.0)
        await broker.connect()

        order = await broker.submit_order(
            OrderRequest.limit("AAPL", OrderSide.BUY, Decimal("10"), Decimal("100"))
        )

        # Replace with new quantity
        new_order = await broker.replace_order(
            order.broker_order_id,
            quantity=Decimal("20"),
        )

        assert new_order.quantity == Decimal("20")
        assert new_order.broker_order_id != order.broker_order_id

    @pytest.mark.asyncio
    async def test_replace_order_marks_old_replaced(self):
        """Test old order marked as replaced."""
        broker = PaperBroker(fill_probability=0.0)
        await broker.connect()

        order = await broker.submit_order(
            OrderRequest.limit("AAPL", OrderSide.BUY, Decimal("10"), Decimal("100"))
        )
        old_id = order.broker_order_id

        await broker.replace_order(old_id, quantity=Decimal("20"))

        old_order = await broker.get_order(old_id)
        assert old_order.status == OrderStatus.REPLACED


class TestPaperBrokerGetOrders:
    """Test PaperBroker get orders."""

    @pytest.mark.asyncio
    async def test_get_order(self):
        """Test getting single order."""
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("10"))
        await broker.connect()

        order = await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        retrieved = await broker.get_order(order.broker_order_id)
        assert retrieved.broker_order_id == order.broker_order_id

    @pytest.mark.asyncio
    async def test_get_order_not_found(self):
        """Test getting nonexistent order."""
        broker = PaperBroker()
        await broker.connect()

        with pytest.raises(OrderError, match="not found"):
            await broker.get_order("INVALID-123")

    @pytest.mark.asyncio
    async def test_get_orders_all(self):
        """Test getting all orders."""
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("10"))
        await broker.connect()

        await broker.submit_order(OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10")))
        await broker.submit_order(OrderRequest.market("AAPL", OrderSide.BUY, Decimal("20")))

        orders = await broker.get_orders()
        assert len(orders) == 2

    @pytest.mark.asyncio
    async def test_get_orders_filter_by_status(self):
        """Test filtering orders by status."""
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("10"))
        await broker.connect()

        # Create filled order
        await broker.submit_order(OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10")))

        # Create unfilled order
        broker._fill_probability = 0.0
        await broker.submit_order(OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10")))

        filled_orders = await broker.get_orders(status=OrderStatus.FILLED)
        assert len(filled_orders) == 1
        assert filled_orders[0].status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_get_orders_filter_by_symbols(self):
        """Test filtering orders by symbols."""
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("10"))
        broker.set_price("MSFT", Decimal("10"))
        await broker.connect()

        await broker.submit_order(OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10")))
        await broker.submit_order(OrderRequest.market("MSFT", OrderSide.BUY, Decimal("10")))

        aapl_orders = await broker.get_orders(symbols=["AAPL"])
        assert len(aapl_orders) == 1
        assert aapl_orders[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_orders_with_limit(self):
        """Test getting limited number of orders."""
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("10"))
        await broker.connect()

        for _ in range(5):
            await broker.submit_order(OrderRequest.market("AAPL", OrderSide.BUY, Decimal("1")))

        orders = await broker.get_orders(limit=3)
        assert len(orders) == 3


class TestPaperBrokerPositions:
    """Test PaperBroker position methods."""

    @pytest.mark.asyncio
    async def test_get_positions_empty(self):
        """Test getting positions when empty."""
        broker = PaperBroker()
        await broker.connect()

        positions = await broker.get_positions()
        assert positions == []

    @pytest.mark.asyncio
    async def test_get_positions_after_buy(self):
        """Test position created after buy."""
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        positions = await broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == Decimal("10")
        assert positions[0].side == PositionSide.LONG

    @pytest.mark.asyncio
    async def test_get_position_single(self):
        """Test getting single position."""
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        position = await broker.get_position("AAPL")
        assert position is not None
        assert position.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_position_not_found(self):
        """Test getting nonexistent position."""
        broker = PaperBroker()
        await broker.connect()

        position = await broker.get_position("AAPL")
        assert position is None

    @pytest.mark.asyncio
    async def test_position_pnl_calculation(self):
        """Test position P&L calculation."""
        broker = PaperBroker(slippage_percent=Decimal("0"))
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        # Buy at 100
        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        # Price goes up
        broker.set_price("AAPL", Decimal("110"))

        position = await broker.get_position("AAPL")
        assert position.unrealized_pnl == Decimal("100")  # 10 shares * $10 gain

    @pytest.mark.asyncio
    async def test_position_closed_on_sell(self):
        """Test position closed when fully sold."""
        broker = PaperBroker(slippage_percent=Decimal("0"))
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        # Buy
        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        # Sell all
        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.SELL, Decimal("10"))
        )

        position = await broker.get_position("AAPL")
        assert position is None

    @pytest.mark.asyncio
    async def test_position_partial_sell(self):
        """Test position reduced on partial sell."""
        broker = PaperBroker(slippage_percent=Decimal("0"))
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        # Buy
        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        # Partial sell
        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.SELL, Decimal("3"))
        )

        position = await broker.get_position("AAPL")
        assert position.quantity == Decimal("7")


class TestPaperBrokerQuotes:
    """Test PaperBroker quote methods."""

    @pytest.mark.asyncio
    async def test_get_quote(self):
        """Test getting quote."""
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        quote = await broker.get_quote("AAPL")
        assert quote.symbol == "AAPL"
        assert quote.last_price == Decimal("100")
        assert quote.bid_price is not None
        assert quote.ask_price is not None
        assert quote.bid_price < quote.ask_price

    @pytest.mark.asyncio
    async def test_quote_spread(self):
        """Test quote has bid/ask spread."""
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        quote = await broker.get_quote("AAPL")
        spread = quote.ask_price - quote.bid_price
        assert spread > Decimal("0")

    @pytest.mark.asyncio
    async def test_quote_requires_connection(self):
        """Test quote requires connection."""
        broker = PaperBroker()
        with pytest.raises(ConnectionError):
            await broker.get_quote("AAPL")


class TestPaperBrokerAssets:
    """Test PaperBroker asset methods."""

    @pytest.mark.asyncio
    async def test_get_asset_equity(self):
        """Test getting equity asset info."""
        broker = PaperBroker()
        await broker.connect()

        asset = await broker.get_asset("AAPL")
        assert asset.symbol == "AAPL"
        assert asset.asset_class == AssetClass.EQUITY
        assert asset.tradable is True

    @pytest.mark.asyncio
    async def test_get_asset_crypto(self):
        """Test getting crypto asset info."""
        broker = PaperBroker()
        await broker.connect()

        asset = await broker.get_asset("BTCUSD")
        assert asset.asset_class == AssetClass.CRYPTO

    @pytest.mark.asyncio
    async def test_get_asset_etf(self):
        """Test getting ETF asset info."""
        broker = PaperBroker()
        await broker.connect()

        asset = await broker.get_asset("SPY")
        assert asset.asset_class == AssetClass.ETF

    @pytest.mark.asyncio
    async def test_get_asset_future(self):
        """Test getting future asset info."""
        broker = PaperBroker()
        await broker.connect()

        asset = await broker.get_asset("ES")
        assert asset.asset_class == AssetClass.FUTURE


class TestPaperBrokerReset:
    """Test PaperBroker reset functionality."""

    @pytest.mark.asyncio
    async def test_reset_clears_positions(self):
        """Test reset clears all positions."""
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("10"))
        await broker.connect()

        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        broker.reset()

        positions = await broker.get_positions()
        assert positions == []

    @pytest.mark.asyncio
    async def test_reset_clears_orders(self):
        """Test reset clears all orders."""
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("10"))
        await broker.connect()

        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        broker.reset()

        orders = await broker.get_orders()
        assert orders == []

    @pytest.mark.asyncio
    async def test_reset_restores_cash(self):
        """Test reset restores initial cash."""
        broker = PaperBroker(initial_cash=Decimal("100000"))
        broker.set_price("AAPL", Decimal("1000"))
        await broker.connect()

        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        assert broker.cash < Decimal("100000")

        broker.reset()

        assert broker.cash == Decimal("100000")


class TestPaperBrokerCashManagement:
    """Test PaperBroker cash management."""

    @pytest.mark.asyncio
    async def test_buy_reduces_cash(self):
        """Test buying reduces cash."""
        broker = PaperBroker(
            initial_cash=Decimal("100000"),
            slippage_percent=Decimal("0"),
        )
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        # 10 shares at $100 = $1000
        assert broker.cash == Decimal("99000")

    @pytest.mark.asyncio
    async def test_sell_increases_cash(self):
        """Test selling increases cash."""
        broker = PaperBroker(
            initial_cash=Decimal("100000"),
            slippage_percent=Decimal("0"),
        )
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        # Buy first
        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        # Then sell at higher price
        broker.set_price("AAPL", Decimal("110"))
        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.SELL, Decimal("10"))
        )

        # Should have initial + profit
        # Buy: -$1000 (100*10), Sell: +$1100 (110*10) = +$100 profit
        assert broker.cash == Decimal("100100")


class TestPaperBrokerAveragePriceCalculation:
    """Test average price calculation for positions."""

    @pytest.mark.asyncio
    async def test_average_price_multiple_buys(self):
        """Test average price calculation with multiple buys."""
        broker = PaperBroker(slippage_percent=Decimal("0"))
        await broker.connect()

        # Buy 10 at $100
        broker.set_price("AAPL", Decimal("100"))
        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        # Buy 10 more at $120
        broker.set_price("AAPL", Decimal("120"))
        await broker.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        )

        position = await broker.get_position("AAPL")
        # Average: (10*100 + 10*120) / 20 = $110
        assert position.avg_entry_price == Decimal("110")
        assert position.quantity == Decimal("20")
