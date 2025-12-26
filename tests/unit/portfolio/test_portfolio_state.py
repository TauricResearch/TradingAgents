"""Tests for Portfolio State module.

Issue #29: [PORT-28] Portfolio state - holdings, cash, mark-to-market
"""

import pytest
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from tradingagents.portfolio import (
    Currency,
    HoldingType,
    Holding,
    CashBalance,
    PortfolioSnapshot,
    PortfolioState,
    PriceProvider,
    ExchangeRateProvider,
)


# =============================================================================
# Test Fixtures
# =============================================================================


class MockPriceProvider:
    """Mock price provider for testing."""

    def __init__(self, prices: Optional[Dict[str, Decimal]] = None):
        self._prices = prices or {}

    def set_price(self, symbol: str, price: Decimal) -> None:
        self._prices[symbol] = price

    def get_price(self, symbol: str) -> Optional[Decimal]:
        return self._prices.get(symbol)

    def get_prices(self, symbols: List[str]) -> Dict[str, Decimal]:
        return {s: self._prices[s] for s in symbols if s in self._prices}


class MockExchangeRateProvider:
    """Mock exchange rate provider for testing."""

    def __init__(self, rates: Optional[Dict[tuple, Decimal]] = None):
        self._rates = rates or {}

    def set_rate(self, from_curr: Currency, to_curr: Currency, rate: Decimal) -> None:
        self._rates[(from_curr, to_curr)] = rate

    def get_rate(self, from_currency: Currency, to_currency: Currency) -> Optional[Decimal]:
        return self._rates.get((from_currency, to_currency))


@pytest.fixture
def price_provider():
    """Create a mock price provider."""
    return MockPriceProvider({
        "AAPL": Decimal("175.00"),
        "GOOGL": Decimal("140.00"),
        "MSFT": Decimal("380.00"),
    })


@pytest.fixture
def exchange_rate_provider():
    """Create a mock exchange rate provider."""
    provider = MockExchangeRateProvider()
    provider.set_rate(Currency.EUR, Currency.USD, Decimal("1.10"))
    provider.set_rate(Currency.GBP, Currency.USD, Decimal("1.27"))
    provider.set_rate(Currency.AUD, Currency.USD, Decimal("0.65"))
    provider.set_rate(Currency.JPY, Currency.USD, Decimal("0.0067"))
    return provider


@pytest.fixture
def sample_holding():
    """Create a sample holding."""
    return Holding(
        symbol="AAPL",
        quantity=Decimal("100"),
        avg_cost=Decimal("150.00"),
        current_price=Decimal("175.00"),
        currency=Currency.USD,
        asset_class="equity",
    )


@pytest.fixture
def empty_portfolio():
    """Create an empty portfolio."""
    return PortfolioState(base_currency=Currency.USD)


@pytest.fixture
def funded_portfolio():
    """Create a portfolio with cash."""
    portfolio = PortfolioState(base_currency=Currency.USD)
    portfolio.add_cash(Currency.USD, Decimal("100000"))
    return portfolio


# =============================================================================
# Holding Tests
# =============================================================================


class TestHolding:
    """Test Holding dataclass."""

    def test_holding_creation(self, sample_holding):
        """Test basic holding creation."""
        assert sample_holding.symbol == "AAPL"
        assert sample_holding.quantity == Decimal("100")
        assert sample_holding.avg_cost == Decimal("150.00")
        assert sample_holding.current_price == Decimal("175.00")

    def test_holding_type_long(self):
        """Test long holding type detection."""
        holding = Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("160"),
        )
        assert holding.holding_type == HoldingType.LONG

    def test_holding_type_short(self):
        """Test short holding type detection."""
        holding = Holding(
            symbol="AAPL",
            quantity=Decimal("-100"),
            avg_cost=Decimal("160"),
            current_price=Decimal("150"),
        )
        assert holding.holding_type == HoldingType.SHORT

    def test_abs_quantity(self):
        """Test absolute quantity calculation."""
        long_holding = Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("160"),
        )
        short_holding = Holding(
            symbol="AAPL",
            quantity=Decimal("-100"),
            avg_cost=Decimal("160"),
            current_price=Decimal("150"),
        )
        assert long_holding.abs_quantity == Decimal("100")
        assert short_holding.abs_quantity == Decimal("100")

    def test_cost_basis(self, sample_holding):
        """Test cost basis calculation."""
        # 100 shares * $150 = $15,000
        assert sample_holding.cost_basis == Decimal("15000.00")

    def test_market_value(self, sample_holding):
        """Test market value calculation."""
        # 100 shares * $175 = $17,500
        assert sample_holding.market_value == Decimal("17500.00")

    def test_unrealized_pnl_long_profit(self, sample_holding):
        """Test unrealized P&L for profitable long position."""
        # (175 - 150) * 100 = $2,500 profit
        assert sample_holding.unrealized_pnl == Decimal("2500.00")

    def test_unrealized_pnl_long_loss(self):
        """Test unrealized P&L for losing long position."""
        holding = Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("175"),
            current_price=Decimal("150"),
        )
        # (150 - 175) * 100 = -$2,500 loss
        assert holding.unrealized_pnl == Decimal("-2500")

    def test_unrealized_pnl_short_profit(self):
        """Test unrealized P&L for profitable short position."""
        holding = Holding(
            symbol="AAPL",
            quantity=Decimal("-100"),
            avg_cost=Decimal("175"),
            current_price=Decimal("150"),
        )
        # (175 - 150) * 100 = $2,500 profit (price went down)
        assert holding.unrealized_pnl == Decimal("2500")

    def test_unrealized_pnl_short_loss(self):
        """Test unrealized P&L for losing short position."""
        holding = Holding(
            symbol="AAPL",
            quantity=Decimal("-100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("175"),
        )
        # (150 - 175) * 100 = -$2,500 loss (price went up)
        assert holding.unrealized_pnl == Decimal("-2500")

    def test_unrealized_pnl_percent(self, sample_holding):
        """Test unrealized P&L percentage."""
        # 2500 / 15000 * 100 = 16.67%
        assert sample_holding.unrealized_pnl_percent == Decimal("16.67")

    def test_unrealized_pnl_percent_zero_cost(self):
        """Test unrealized P&L percent with zero cost basis."""
        holding = Holding(
            symbol="FREE",
            quantity=Decimal("100"),
            avg_cost=Decimal("0"),
            current_price=Decimal("10"),
        )
        assert holding.unrealized_pnl_percent == Decimal("0")

    def test_is_profitable(self, sample_holding):
        """Test is_profitable property."""
        assert sample_holding.is_profitable is True

        losing = Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("200"),
            current_price=Decimal("150"),
        )
        assert losing.is_profitable is False

    def test_update_price(self, sample_holding):
        """Test price update creates new holding."""
        new_price = Decimal("180.00")
        updated = sample_holding.update_price(new_price)

        assert updated is not sample_holding  # New instance
        assert updated.current_price == new_price
        assert updated.symbol == sample_holding.symbol
        assert updated.quantity == sample_holding.quantity
        assert updated.avg_cost == sample_holding.avg_cost


# =============================================================================
# CashBalance Tests
# =============================================================================


class TestCashBalance:
    """Test CashBalance dataclass."""

    def test_cash_balance_creation(self):
        """Test basic cash balance creation."""
        balance = CashBalance(
            currency=Currency.USD,
            available=Decimal("10000"),
            reserved=Decimal("500"),
        )
        assert balance.currency == Currency.USD
        assert balance.available == Decimal("10000")
        assert balance.reserved == Decimal("500")
        assert balance.total == Decimal("10500")

    def test_deposit(self):
        """Test depositing cash."""
        balance = CashBalance(currency=Currency.USD, available=Decimal("1000"))
        new_balance = balance.deposit(Decimal("500"))

        assert new_balance.available == Decimal("1500")
        assert balance.available == Decimal("1000")  # Original unchanged

    def test_deposit_negative_amount(self):
        """Test that negative deposit raises error."""
        balance = CashBalance(currency=Currency.USD, available=Decimal("1000"))
        with pytest.raises(ValueError, match="non-negative"):
            balance.deposit(Decimal("-100"))

    def test_withdraw(self):
        """Test withdrawing cash."""
        balance = CashBalance(currency=Currency.USD, available=Decimal("1000"))
        new_balance = balance.withdraw(Decimal("500"))

        assert new_balance.available == Decimal("500")

    def test_withdraw_insufficient_funds(self):
        """Test withdrawal with insufficient funds."""
        balance = CashBalance(currency=Currency.USD, available=Decimal("100"))
        with pytest.raises(ValueError, match="Insufficient"):
            balance.withdraw(Decimal("500"))

    def test_withdraw_negative_amount(self):
        """Test that negative withdrawal raises error."""
        balance = CashBalance(currency=Currency.USD, available=Decimal("1000"))
        with pytest.raises(ValueError, match="non-negative"):
            balance.withdraw(Decimal("-100"))

    def test_reserve(self):
        """Test reserving cash."""
        balance = CashBalance(currency=Currency.USD, available=Decimal("1000"))
        new_balance = balance.reserve(Decimal("300"))

        assert new_balance.available == Decimal("700")
        assert new_balance.reserved == Decimal("300")
        assert new_balance.total == Decimal("1000")

    def test_reserve_insufficient(self):
        """Test reserving more than available."""
        balance = CashBalance(currency=Currency.USD, available=Decimal("100"))
        with pytest.raises(ValueError, match="Insufficient"):
            balance.reserve(Decimal("500"))

    def test_release(self):
        """Test releasing reserved cash."""
        balance = CashBalance(
            currency=Currency.USD,
            available=Decimal("700"),
            reserved=Decimal("300"),
        )
        new_balance = balance.release(Decimal("200"))

        assert new_balance.available == Decimal("900")
        assert new_balance.reserved == Decimal("100")

    def test_release_too_much(self):
        """Test releasing more than reserved."""
        balance = CashBalance(
            currency=Currency.USD,
            available=Decimal("1000"),
            reserved=Decimal("100"),
        )
        with pytest.raises(ValueError, match="Insufficient reserved"):
            balance.release(Decimal("500"))


# =============================================================================
# PortfolioState Tests
# =============================================================================


class TestPortfolioState:
    """Test PortfolioState class."""

    def test_portfolio_creation(self, empty_portfolio):
        """Test basic portfolio creation."""
        assert empty_portfolio.base_currency == Currency.USD
        assert empty_portfolio.num_holdings == 0
        assert empty_portfolio.total_value == Decimal("0")

    def test_add_cash(self, empty_portfolio):
        """Test adding cash."""
        empty_portfolio.add_cash(Currency.USD, Decimal("10000"))

        assert empty_portfolio.total_cash == Decimal("10000")
        balance = empty_portfolio.get_cash(Currency.USD)
        assert balance.available == Decimal("10000")

    def test_add_cash_multiple_currencies(self, empty_portfolio):
        """Test adding cash in multiple currencies."""
        empty_portfolio.add_cash(Currency.USD, Decimal("10000"))
        empty_portfolio.add_cash(Currency.EUR, Decimal("5000"))

        # Without exchange rate provider, EUR converts at 1:1
        assert empty_portfolio.total_cash == Decimal("15000")

    def test_withdraw_cash(self, funded_portfolio):
        """Test withdrawing cash."""
        funded_portfolio.withdraw_cash(Currency.USD, Decimal("25000"))

        balance = funded_portfolio.get_cash(Currency.USD)
        assert balance.available == Decimal("75000")

    def test_reserve_cash(self, funded_portfolio):
        """Test reserving cash."""
        funded_portfolio.reserve_cash(Currency.USD, Decimal("10000"))

        balance = funded_portfolio.get_cash(Currency.USD)
        assert balance.available == Decimal("90000")
        assert balance.reserved == Decimal("10000")
        assert funded_portfolio.total_reserved_cash == Decimal("10000")

    def test_release_cash(self, funded_portfolio):
        """Test releasing reserved cash."""
        funded_portfolio.reserve_cash(Currency.USD, Decimal("10000"))
        funded_portfolio.release_cash(Currency.USD, Decimal("5000"))

        balance = funded_portfolio.get_cash(Currency.USD)
        assert balance.available == Decimal("95000")
        assert balance.reserved == Decimal("5000")

    def test_add_holding(self, funded_portfolio, sample_holding):
        """Test adding a holding."""
        funded_portfolio.add_holding(sample_holding)

        assert funded_portfolio.num_holdings == 1
        retrieved = funded_portfolio.get_holding("AAPL")
        assert retrieved is not None
        assert retrieved.symbol == "AAPL"
        assert retrieved.quantity == Decimal("100")

    def test_add_to_existing_holding(self, funded_portfolio):
        """Test adding to an existing holding (average cost)."""
        # Add first lot: 100 @ $150
        holding1 = Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("160"),
        )
        funded_portfolio.add_holding(holding1)

        # Add second lot: 100 @ $170
        holding2 = Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("170"),
            current_price=Decimal("160"),
        )
        funded_portfolio.add_holding(holding2)

        # Should have 200 shares at average cost of $160
        retrieved = funded_portfolio.get_holding("AAPL")
        assert retrieved is not None
        assert retrieved.quantity == Decimal("200")
        # (100 * 150 + 100 * 170) / 200 = 32000 / 200 = 160
        assert retrieved.avg_cost == Decimal("160")

    def test_close_position(self, funded_portfolio):
        """Test closing a position completely."""
        # Add 100 shares
        holding1 = Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("160"),
        )
        funded_portfolio.add_holding(holding1)

        # Sell 100 shares (net 0)
        holding2 = Holding(
            symbol="AAPL",
            quantity=Decimal("-100"),
            avg_cost=Decimal("160"),
            current_price=Decimal("160"),
        )
        funded_portfolio.add_holding(holding2)

        # Position should be closed
        assert funded_portfolio.get_holding("AAPL") is None
        assert funded_portfolio.num_holdings == 0

    def test_remove_holding(self, funded_portfolio, sample_holding):
        """Test removing a holding."""
        funded_portfolio.add_holding(sample_holding)
        assert funded_portfolio.num_holdings == 1

        removed = funded_portfolio.remove_holding("AAPL")
        assert removed is not None
        assert removed.symbol == "AAPL"
        assert funded_portfolio.num_holdings == 0

    def test_remove_nonexistent_holding(self, funded_portfolio):
        """Test removing a holding that doesn't exist."""
        removed = funded_portfolio.remove_holding("NOTREAL")
        assert removed is None

    def test_update_price(self, funded_portfolio, sample_holding):
        """Test updating price of a holding."""
        funded_portfolio.add_holding(sample_holding)

        success = funded_portfolio.update_price("AAPL", Decimal("180.00"))
        assert success is True

        holding = funded_portfolio.get_holding("AAPL")
        assert holding.current_price == Decimal("180.00")

    def test_update_price_nonexistent(self, funded_portfolio):
        """Test updating price of nonexistent holding."""
        success = funded_portfolio.update_price("NOTREAL", Decimal("100"))
        assert success is False

    def test_update_all_prices(self, price_provider):
        """Test updating all prices from provider."""
        portfolio = PortfolioState(
            base_currency=Currency.USD,
            price_provider=price_provider,
        )
        portfolio.add_holding(Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("150"),
        ))
        portfolio.add_holding(Holding(
            symbol="GOOGL",
            quantity=Decimal("50"),
            avg_cost=Decimal("130"),
            current_price=Decimal("130"),
        ))

        results = portfolio.update_all_prices()

        assert results["AAPL"] is True
        assert results["GOOGL"] is True
        assert portfolio.get_holding("AAPL").current_price == Decimal("175.00")
        assert portfolio.get_holding("GOOGL").current_price == Decimal("140.00")

    def test_total_holdings_value(self, funded_portfolio):
        """Test total holdings value calculation."""
        funded_portfolio.add_holding(Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("175"),
        ))
        funded_portfolio.add_holding(Holding(
            symbol="GOOGL",
            quantity=Decimal("50"),
            avg_cost=Decimal("130"),
            current_price=Decimal("140"),
        ))

        # AAPL: 100 * 175 = 17500
        # GOOGL: 50 * 140 = 7000
        # Total: 24500
        assert funded_portfolio.total_holdings_value == Decimal("24500.00")

    def test_total_value(self, funded_portfolio):
        """Test total portfolio value (holdings + cash)."""
        funded_portfolio.add_holding(Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("175"),
        ))

        # Cash: 100000
        # Holdings: 17500
        # Total: 117500
        assert funded_portfolio.total_value == Decimal("117500.00")

    def test_total_unrealized_pnl(self, funded_portfolio):
        """Test total unrealized P&L."""
        funded_portfolio.add_holding(Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("175"),
        ))
        funded_portfolio.add_holding(Holding(
            symbol="GOOGL",
            quantity=Decimal("50"),
            avg_cost=Decimal("150"),
            current_price=Decimal("140"),
        ))

        # AAPL: (175 - 150) * 100 = 2500
        # GOOGL: (140 - 150) * 50 = -500
        # Total: 2000
        assert funded_portfolio.total_unrealized_pnl == Decimal("2000.00")

    def test_total_cost_basis(self, funded_portfolio):
        """Test total cost basis."""
        funded_portfolio.add_holding(Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("175"),
        ))
        funded_portfolio.add_holding(Holding(
            symbol="GOOGL",
            quantity=Decimal("50"),
            avg_cost=Decimal("130"),
            current_price=Decimal("140"),
        ))

        # AAPL: 100 * 150 = 15000
        # GOOGL: 50 * 130 = 6500
        # Total: 21500
        assert funded_portfolio.total_cost_basis == Decimal("21500.00")

    def test_concentration(self, funded_portfolio):
        """Test position concentration."""
        funded_portfolio.add_holding(Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("200"),
        ))

        # Holdings: 20000, Cash: 100000, Total: 120000
        # AAPL concentration: 20000 / 120000 * 100 = 16.67%
        assert funded_portfolio.get_concentration("AAPL") == Decimal("16.67")

    def test_concentration_nonexistent(self, funded_portfolio):
        """Test concentration for nonexistent holding."""
        assert funded_portfolio.get_concentration("NOTREAL") == Decimal("0")

    def test_allocations(self, funded_portfolio):
        """Test getting allocations for all holdings."""
        funded_portfolio.add_holding(Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("100"),  # 10000
        ))
        funded_portfolio.add_holding(Holding(
            symbol="GOOGL",
            quantity=Decimal("100"),
            avg_cost=Decimal("130"),
            current_price=Decimal("100"),  # 10000
        ))

        # Total: 100000 cash + 20000 holdings = 120000
        allocations = funded_portfolio.get_allocations()

        assert len(allocations) == 2
        # Each holding is 10000 / 120000 * 100 = 8.33%
        assert allocations["AAPL"] == Decimal("8.33")
        assert allocations["GOOGL"] == Decimal("8.33")

    def test_asset_class_breakdown(self, funded_portfolio):
        """Test asset class breakdown."""
        funded_portfolio.add_holding(Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("100"),
            current_price=Decimal("100"),
            asset_class="equity",
        ))
        funded_portfolio.add_holding(Holding(
            symbol="SPY",
            quantity=Decimal("50"),
            avg_cost=Decimal("400"),
            current_price=Decimal("400"),
            asset_class="etf",
        ))

        # AAPL: 10000 (equity)
        # SPY: 20000 (etf)
        # Total holdings: 30000
        breakdown = funded_portfolio.get_asset_class_breakdown()

        # Equity: 10000 / 30000 * 100 = 33.33%
        # ETF: 20000 / 30000 * 100 = 66.67%
        assert breakdown["equity"] == Decimal("33.33")
        assert breakdown["etf"] == Decimal("66.67")


# =============================================================================
# Multi-Currency Tests
# =============================================================================


class TestMultiCurrency:
    """Test multi-currency functionality."""

    def test_holdings_in_different_currencies(self, exchange_rate_provider):
        """Test holdings in different currencies."""
        portfolio = PortfolioState(
            base_currency=Currency.USD,
            exchange_rate_provider=exchange_rate_provider,
        )

        # USD holding
        portfolio.add_holding(Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("175"),
            currency=Currency.USD,
        ))

        # EUR holding (converted at 1.10)
        portfolio.add_holding(Holding(
            symbol="ASML",
            quantity=Decimal("50"),
            avg_cost=Decimal("500"),
            current_price=Decimal("600"),
            currency=Currency.EUR,
        ))

        # AAPL: 100 * 175 = 17500 USD
        # ASML: 50 * 600 = 30000 EUR * 1.10 = 33000 USD
        # Total: 50500 USD
        assert portfolio.total_holdings_value == Decimal("50500.00")

    def test_cash_in_different_currencies(self, exchange_rate_provider):
        """Test cash in different currencies."""
        portfolio = PortfolioState(
            base_currency=Currency.USD,
            exchange_rate_provider=exchange_rate_provider,
        )

        portfolio.add_cash(Currency.USD, Decimal("10000"))
        portfolio.add_cash(Currency.EUR, Decimal("5000"))  # 5000 * 1.10 = 5500 USD
        portfolio.add_cash(Currency.GBP, Decimal("2000"))  # 2000 * 1.27 = 2540 USD

        # 10000 + 5500 + 2540 = 18040
        assert portfolio.total_cash == Decimal("18040.00")

    def test_currency_exposure(self, exchange_rate_provider):
        """Test currency exposure calculation."""
        portfolio = PortfolioState(
            base_currency=Currency.USD,
            exchange_rate_provider=exchange_rate_provider,
        )

        portfolio.add_cash(Currency.USD, Decimal("10000"))
        portfolio.add_holding(Holding(
            symbol="ASML",
            quantity=Decimal("10"),
            avg_cost=Decimal("500"),
            current_price=Decimal("1000"),
            currency=Currency.EUR,
        ))

        # EUR holding: 10 * 1000 = 10000 EUR * 1.10 = 11000 USD
        # Total: 10000 USD + 11000 USD = 21000 USD
        exposure = portfolio.get_currency_exposure()

        # USD: 10000 / 21000 * 100 = 47.62%
        # EUR: 11000 / 21000 * 100 = 52.38%
        assert exposure[Currency.USD] == Decimal("47.62")
        assert exposure[Currency.EUR] == Decimal("52.38")

    def test_exchange_rate_same_currency(self, exchange_rate_provider):
        """Test exchange rate for same currency is 1."""
        portfolio = PortfolioState(
            base_currency=Currency.USD,
            exchange_rate_provider=exchange_rate_provider,
        )

        rate = portfolio.get_exchange_rate(Currency.USD, Currency.USD)
        assert rate == Decimal("1")


# =============================================================================
# Snapshot Tests
# =============================================================================


class TestPortfolioSnapshot:
    """Test portfolio snapshot functionality."""

    def test_create_snapshot(self, funded_portfolio, sample_holding):
        """Test creating a portfolio snapshot."""
        funded_portfolio.add_holding(sample_holding)

        snapshot = funded_portfolio.create_snapshot()

        assert snapshot is not None
        assert isinstance(snapshot.timestamp, datetime)
        assert len(snapshot.holdings) == 1
        assert snapshot.total_portfolio_value == funded_portfolio.total_value

    def test_snapshot_immutability(self, funded_portfolio, sample_holding):
        """Test that snapshot is independent of portfolio changes."""
        funded_portfolio.add_holding(sample_holding)
        snapshot = funded_portfolio.create_snapshot()

        original_value = snapshot.total_portfolio_value

        # Modify portfolio
        funded_portfolio.add_holding(Holding(
            symbol="GOOGL",
            quantity=Decimal("100"),
            avg_cost=Decimal("140"),
            current_price=Decimal("140"),
        ))

        # Snapshot should be unchanged
        assert snapshot.total_portfolio_value == original_value

    def test_get_snapshots(self, funded_portfolio):
        """Test getting all snapshots."""
        funded_portfolio.create_snapshot()
        funded_portfolio.create_snapshot()
        funded_portfolio.create_snapshot()

        snapshots = funded_portfolio.get_snapshots()
        assert len(snapshots) == 3

    def test_get_latest_snapshot(self, funded_portfolio):
        """Test getting latest snapshot."""
        funded_portfolio.add_cash(Currency.USD, Decimal("1000"))
        funded_portfolio.create_snapshot(metadata={"version": 1})

        funded_portfolio.add_cash(Currency.USD, Decimal("2000"))
        funded_portfolio.create_snapshot(metadata={"version": 2})

        latest = funded_portfolio.get_latest_snapshot()
        assert latest.metadata["version"] == 2

    def test_get_latest_snapshot_empty(self, empty_portfolio):
        """Test getting latest snapshot when none exist."""
        assert empty_portfolio.get_latest_snapshot() is None

    def test_clear_snapshots(self, funded_portfolio):
        """Test clearing all snapshots."""
        funded_portfolio.create_snapshot()
        funded_portfolio.create_snapshot()

        count = funded_portfolio.clear_snapshots()

        assert count == 2
        assert len(funded_portfolio.get_snapshots()) == 0

    def test_snapshot_properties(self, funded_portfolio, sample_holding):
        """Test snapshot properties."""
        funded_portfolio.add_holding(sample_holding)
        snapshot = funded_portfolio.create_snapshot()

        assert snapshot.num_holdings == 1
        assert "AAPL" in snapshot.symbols
        assert snapshot.get_holding("AAPL") is not None
        assert snapshot.get_cash(Currency.USD) == Decimal("100000")


# =============================================================================
# Serialization Tests
# =============================================================================


class TestSerialization:
    """Test serialization and deserialization."""

    def test_to_dict(self, funded_portfolio, sample_holding):
        """Test converting portfolio to dictionary."""
        funded_portfolio.add_holding(sample_holding)

        data = funded_portfolio.to_dict()

        assert data["base_currency"] == "USD"
        assert "AAPL" in data["holdings"]
        assert data["holdings"]["AAPL"]["quantity"] == "100"
        assert data["summary"]["num_holdings"] == 1

    def test_from_dict(self, funded_portfolio, sample_holding):
        """Test creating portfolio from dictionary."""
        funded_portfolio.add_holding(sample_holding)
        data = funded_portfolio.to_dict()

        restored = PortfolioState.from_dict(data)

        assert restored.base_currency == Currency.USD
        assert restored.num_holdings == 1
        holding = restored.get_holding("AAPL")
        assert holding is not None
        assert holding.quantity == Decimal("100")

    def test_round_trip(self, funded_portfolio):
        """Test full serialization round trip."""
        funded_portfolio.add_holding(Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("175"),
        ))
        funded_portfolio.add_cash(Currency.EUR, Decimal("5000"))
        funded_portfolio.reserve_cash(Currency.USD, Decimal("10000"))

        data = funded_portfolio.to_dict()
        restored = PortfolioState.from_dict(data)

        assert restored.total_value == funded_portfolio.total_value
        assert restored.total_holdings_value == funded_portfolio.total_holdings_value
        assert restored.total_unrealized_pnl == funded_portfolio.total_unrealized_pnl


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_portfolio_metrics(self, empty_portfolio):
        """Test metrics on empty portfolio."""
        assert empty_portfolio.total_value == Decimal("0")
        assert empty_portfolio.total_holdings_value == Decimal("0")
        assert empty_portfolio.total_cash == Decimal("0")
        assert empty_portfolio.total_unrealized_pnl == Decimal("0")
        assert empty_portfolio.get_allocations() == {}

    def test_zero_quantity_holding(self):
        """Test holding with zero quantity."""
        holding = Holding(
            symbol="AAPL",
            quantity=Decimal("0"),
            avg_cost=Decimal("150"),
            current_price=Decimal("175"),
        )
        assert holding.cost_basis == Decimal("0")
        assert holding.market_value == Decimal("0")
        assert holding.unrealized_pnl == Decimal("0")

    def test_symbols_property(self, funded_portfolio):
        """Test getting list of symbols."""
        funded_portfolio.add_holding(Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("175"),
        ))
        funded_portfolio.add_holding(Holding(
            symbol="GOOGL",
            quantity=Decimal("50"),
            avg_cost=Decimal("140"),
            current_price=Decimal("140"),
        ))

        symbols = funded_portfolio.symbols
        assert len(symbols) == 2
        assert "AAPL" in symbols
        assert "GOOGL" in symbols

    def test_last_updated_tracking(self, empty_portfolio):
        """Test last_updated is updated on changes."""
        assert empty_portfolio.last_updated is None

        empty_portfolio.add_cash(Currency.USD, Decimal("1000"))
        first_update = empty_portfolio.last_updated
        assert first_update is not None

        empty_portfolio.add_holding(Holding(
            symbol="AAPL",
            quantity=Decimal("10"),
            avg_cost=Decimal("100"),
            current_price=Decimal("100"),
        ))
        second_update = empty_portfolio.last_updated
        assert second_update >= first_update

    def test_no_price_provider(self, empty_portfolio):
        """Test update_all_prices with no provider."""
        empty_portfolio.add_holding(Holding(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            current_price=Decimal("175"),
        ))

        results = empty_portfolio.update_all_prices()
        assert results == {}

    def test_holdings_property_returns_copy(self, funded_portfolio, sample_holding):
        """Test that holdings property returns a copy."""
        funded_portfolio.add_holding(sample_holding)

        holdings1 = funded_portfolio.holdings
        holdings2 = funded_portfolio.holdings

        assert holdings1 is not holdings2
        assert holdings1["AAPL"] is holdings2["AAPL"]  # Same Holding objects

    def test_cash_balances_property_returns_copy(self, funded_portfolio):
        """Test that cash_balances property returns a copy."""
        balances1 = funded_portfolio.cash_balances
        balances2 = funded_portfolio.cash_balances

        assert balances1 is not balances2

    def test_get_cash_creates_balance(self, empty_portfolio):
        """Test that get_cash creates a balance if it doesn't exist."""
        balance = empty_portfolio.get_cash(Currency.GBP)

        assert balance.currency == Currency.GBP
        assert balance.available == Decimal("0")
        assert balance.reserved == Decimal("0")
