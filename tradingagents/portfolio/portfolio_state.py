"""Portfolio State Management.

This module provides portfolio state tracking including:
- Current holdings with cost basis and market values
- Multi-currency cash balances
- Real-time mark-to-market valuation
- Portfolio snapshots for historical analysis

Issue #29: [PORT-28] Portfolio state - holdings, cash, mark-to-market

Design Principles:
    - Multi-currency support with base currency conversion
    - Real-time pricing via pluggable PriceProvider
    - Immutable snapshots for historical tracking
    - Thread-safe state updates
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Set, Tuple, Union
import threading


class Currency(Enum):
    """Supported currencies."""
    USD = "USD"  # US Dollar
    EUR = "EUR"  # Euro
    GBP = "GBP"  # British Pound
    JPY = "JPY"  # Japanese Yen
    AUD = "AUD"  # Australian Dollar
    CAD = "CAD"  # Canadian Dollar
    CHF = "CHF"  # Swiss Franc
    HKD = "HKD"  # Hong Kong Dollar
    SGD = "SGD"  # Singapore Dollar
    NZD = "NZD"  # New Zealand Dollar


class HoldingType(Enum):
    """Type of holding."""
    LONG = "long"      # Long position (own the asset)
    SHORT = "short"    # Short position (borrowed and sold)


@dataclass
class Holding:
    """Individual holding/position in the portfolio.

    Attributes:
        symbol: Trading symbol
        quantity: Number of shares/contracts (positive for long, negative for short)
        avg_cost: Average cost per share
        current_price: Current market price per share
        currency: Currency of the holding
        asset_class: Type of asset (equity, etf, crypto, etc.)
        exchange: Exchange where traded
        acquired_at: When the position was first opened
        last_updated: When the holding was last updated
        metadata: Additional holding-specific data
    """
    symbol: str
    quantity: Decimal
    avg_cost: Decimal
    current_price: Decimal
    currency: Currency = Currency.USD
    asset_class: str = "equity"
    exchange: Optional[str] = None
    acquired_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def holding_type(self) -> HoldingType:
        """Determine if this is a long or short position."""
        return HoldingType.LONG if self.quantity >= 0 else HoldingType.SHORT

    @property
    def abs_quantity(self) -> Decimal:
        """Get absolute quantity."""
        return abs(self.quantity)

    @property
    def cost_basis(self) -> Decimal:
        """Total cost basis of the position."""
        return self.abs_quantity * self.avg_cost

    @property
    def market_value(self) -> Decimal:
        """Current market value of the position."""
        return self.abs_quantity * self.current_price

    @property
    def unrealized_pnl(self) -> Decimal:
        """Unrealized profit/loss.

        For long positions: (current_price - avg_cost) * quantity
        For short positions: (avg_cost - current_price) * abs(quantity)
        """
        if self.holding_type == HoldingType.LONG:
            return (self.current_price - self.avg_cost) * self.quantity
        else:
            # For shorts, profit when price decreases
            return (self.avg_cost - self.current_price) * self.abs_quantity

    @property
    def unrealized_pnl_percent(self) -> Decimal:
        """Unrealized P&L as percentage of cost basis."""
        if self.cost_basis == 0:
            return Decimal("0")
        return (self.unrealized_pnl / self.cost_basis * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @property
    def is_profitable(self) -> bool:
        """Check if position is currently profitable."""
        return self.unrealized_pnl > 0

    def update_price(self, new_price: Decimal) -> "Holding":
        """Create a new Holding with updated price.

        Returns a new Holding instance with the updated price.
        Holdings are treated as effectively immutable for snapshots.
        """
        return Holding(
            symbol=self.symbol,
            quantity=self.quantity,
            avg_cost=self.avg_cost,
            current_price=new_price,
            currency=self.currency,
            asset_class=self.asset_class,
            exchange=self.exchange,
            acquired_at=self.acquired_at,
            last_updated=datetime.now(),
            metadata=self.metadata.copy(),
        )


@dataclass
class CashBalance:
    """Cash balance in a specific currency.

    Attributes:
        currency: The currency
        available: Available cash (can be used for trading)
        reserved: Reserved cash (held for pending orders)
        total: Total cash (available + reserved)
    """
    currency: Currency
    available: Decimal = field(default_factory=lambda: Decimal("0"))
    reserved: Decimal = field(default_factory=lambda: Decimal("0"))

    @property
    def total(self) -> Decimal:
        """Total cash balance."""
        return self.available + self.reserved

    def deposit(self, amount: Decimal) -> "CashBalance":
        """Create new balance with deposited amount."""
        if amount < 0:
            raise ValueError("Deposit amount must be non-negative")
        return CashBalance(
            currency=self.currency,
            available=self.available + amount,
            reserved=self.reserved,
        )

    def withdraw(self, amount: Decimal) -> "CashBalance":
        """Create new balance with withdrawn amount."""
        if amount < 0:
            raise ValueError("Withdrawal amount must be non-negative")
        if amount > self.available:
            raise ValueError(f"Insufficient available cash: {self.available} < {amount}")
        return CashBalance(
            currency=self.currency,
            available=self.available - amount,
            reserved=self.reserved,
        )

    def reserve(self, amount: Decimal) -> "CashBalance":
        """Reserve cash from available balance."""
        if amount < 0:
            raise ValueError("Reserve amount must be non-negative")
        if amount > self.available:
            raise ValueError(f"Insufficient available cash to reserve: {self.available} < {amount}")
        return CashBalance(
            currency=self.currency,
            available=self.available - amount,
            reserved=self.reserved + amount,
        )

    def release(self, amount: Decimal) -> "CashBalance":
        """Release reserved cash back to available."""
        if amount < 0:
            raise ValueError("Release amount must be non-negative")
        if amount > self.reserved:
            raise ValueError(f"Insufficient reserved cash to release: {self.reserved} < {amount}")
        return CashBalance(
            currency=self.currency,
            available=self.available + amount,
            reserved=self.reserved - amount,
        )


class PriceProvider(Protocol):
    """Protocol for price data providers.

    Implementations can fetch prices from various sources:
    - Live broker APIs
    - Market data feeds
    - Cached/delayed prices
    - Historical data for backtesting
    """

    def get_price(self, symbol: str) -> Optional[Decimal]:
        """Get current price for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Current price or None if unavailable
        """
        ...

    def get_prices(self, symbols: List[str]) -> Dict[str, Decimal]:
        """Get current prices for multiple symbols.

        Args:
            symbols: List of trading symbols

        Returns:
            Dictionary of symbol -> price (only includes available prices)
        """
        ...


class ExchangeRateProvider(Protocol):
    """Protocol for currency exchange rate providers."""

    def get_rate(self, from_currency: Currency, to_currency: Currency) -> Optional[Decimal]:
        """Get exchange rate from one currency to another.

        Args:
            from_currency: Source currency
            to_currency: Target currency

        Returns:
            Exchange rate or None if unavailable
        """
        ...


@dataclass
class PortfolioSnapshot:
    """Immutable snapshot of portfolio state at a point in time.

    Used for historical tracking, performance analysis, and audit trails.

    Attributes:
        timestamp: When the snapshot was taken
        holdings: Dictionary of symbol -> Holding
        cash_balances: Dictionary of Currency -> CashBalance
        base_currency: Base currency for total value calculations
        total_holdings_value: Total market value of all holdings (in base currency)
        total_cash: Total cash across all currencies (in base currency)
        total_portfolio_value: Holdings + Cash (in base currency)
        unrealized_pnl: Total unrealized P&L (in base currency)
        metadata: Additional snapshot metadata
    """
    timestamp: datetime
    holdings: Dict[str, Holding]
    cash_balances: Dict[Currency, CashBalance]
    base_currency: Currency
    total_holdings_value: Decimal
    total_cash: Decimal
    total_portfolio_value: Decimal
    unrealized_pnl: Decimal
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def num_holdings(self) -> int:
        """Number of positions in the portfolio."""
        return len(self.holdings)

    @property
    def symbols(self) -> List[str]:
        """List of symbols held."""
        return list(self.holdings.keys())

    def get_holding(self, symbol: str) -> Optional[Holding]:
        """Get holding for a specific symbol."""
        return self.holdings.get(symbol)

    def get_cash(self, currency: Currency) -> Decimal:
        """Get available cash in a specific currency."""
        balance = self.cash_balances.get(currency)
        return balance.available if balance else Decimal("0")


class PortfolioState:
    """Live portfolio state with mark-to-market updates.

    This class manages the current state of a portfolio including:
    - Holdings with real-time price updates
    - Multi-currency cash balances
    - Mark-to-market valuation
    - Snapshot creation for historical tracking

    Thread-safe for concurrent updates.

    Example:
        >>> portfolio = PortfolioState(base_currency=Currency.USD)
        >>> portfolio.add_cash(Currency.USD, Decimal("10000"))
        >>> portfolio.add_holding(Holding(
        ...     symbol="AAPL",
        ...     quantity=Decimal("100"),
        ...     avg_cost=Decimal("150"),
        ...     current_price=Decimal("160"),
        ... ))
        >>> portfolio.total_value
        Decimal('26000.00')  # 10000 cash + 16000 holdings
    """

    def __init__(
        self,
        base_currency: Currency = Currency.USD,
        price_provider: Optional[PriceProvider] = None,
        exchange_rate_provider: Optional[ExchangeRateProvider] = None,
    ):
        """Initialize portfolio state.

        Args:
            base_currency: Base currency for valuation
            price_provider: Provider for real-time prices
            exchange_rate_provider: Provider for currency exchange rates
        """
        self._base_currency = base_currency
        self._price_provider = price_provider
        self._exchange_rate_provider = exchange_rate_provider

        self._holdings: Dict[str, Holding] = {}
        self._cash_balances: Dict[Currency, CashBalance] = {}
        self._snapshots: List[PortfolioSnapshot] = []

        self._lock = threading.RLock()
        self._last_updated: Optional[datetime] = None
        self._metadata: Dict[str, Any] = {}

    @property
    def base_currency(self) -> Currency:
        """Get base currency."""
        return self._base_currency

    @property
    def holdings(self) -> Dict[str, Holding]:
        """Get copy of current holdings."""
        with self._lock:
            return self._holdings.copy()

    @property
    def cash_balances(self) -> Dict[Currency, CashBalance]:
        """Get copy of current cash balances."""
        with self._lock:
            return self._cash_balances.copy()

    @property
    def symbols(self) -> List[str]:
        """Get list of symbols held."""
        with self._lock:
            return list(self._holdings.keys())

    @property
    def num_holdings(self) -> int:
        """Get number of holdings."""
        with self._lock:
            return len(self._holdings)

    @property
    def last_updated(self) -> Optional[datetime]:
        """Get last update timestamp."""
        return self._last_updated

    def get_holding(self, symbol: str) -> Optional[Holding]:
        """Get holding for a symbol."""
        with self._lock:
            return self._holdings.get(symbol)

    def get_cash(self, currency: Currency) -> CashBalance:
        """Get cash balance for a currency."""
        with self._lock:
            if currency not in self._cash_balances:
                self._cash_balances[currency] = CashBalance(currency=currency)
            return self._cash_balances[currency]

    def add_holding(self, holding: Holding) -> None:
        """Add or update a holding.

        If a holding for the symbol already exists, this updates the position
        using average cost basis calculation.
        """
        with self._lock:
            existing = self._holdings.get(holding.symbol)

            if existing is None:
                self._holdings[holding.symbol] = holding
            else:
                # Calculate new average cost for the combined position
                total_cost = (existing.cost_basis + holding.cost_basis)
                total_qty = existing.quantity + holding.quantity

                if total_qty == 0:
                    # Position closed
                    del self._holdings[holding.symbol]
                else:
                    new_avg_cost = total_cost / abs(total_qty)
                    self._holdings[holding.symbol] = Holding(
                        symbol=holding.symbol,
                        quantity=total_qty,
                        avg_cost=new_avg_cost,
                        current_price=holding.current_price,
                        currency=holding.currency,
                        asset_class=holding.asset_class,
                        exchange=holding.exchange or existing.exchange,
                        acquired_at=existing.acquired_at,
                        last_updated=datetime.now(),
                        metadata={**existing.metadata, **holding.metadata},
                    )

            self._last_updated = datetime.now()

    def remove_holding(self, symbol: str) -> Optional[Holding]:
        """Remove a holding completely."""
        with self._lock:
            holding = self._holdings.pop(symbol, None)
            if holding:
                self._last_updated = datetime.now()
            return holding

    def update_price(self, symbol: str, price: Decimal) -> bool:
        """Update price for a holding.

        Args:
            symbol: Trading symbol
            price: New price

        Returns:
            True if holding was found and updated, False otherwise
        """
        with self._lock:
            holding = self._holdings.get(symbol)
            if holding is None:
                return False

            self._holdings[symbol] = holding.update_price(price)
            self._last_updated = datetime.now()
            return True

    def update_all_prices(self) -> Dict[str, bool]:
        """Update prices for all holdings using the price provider.

        Returns:
            Dictionary of symbol -> success status
        """
        if self._price_provider is None:
            return {}

        with self._lock:
            symbols = list(self._holdings.keys())

        prices = self._price_provider.get_prices(symbols)
        results = {}

        with self._lock:
            for symbol in symbols:
                if symbol in prices:
                    self._holdings[symbol] = self._holdings[symbol].update_price(prices[symbol])
                    results[symbol] = True
                else:
                    results[symbol] = False

            self._last_updated = datetime.now()

        return results

    def add_cash(self, currency: Currency, amount: Decimal) -> None:
        """Add cash to a currency balance."""
        with self._lock:
            balance = self.get_cash(currency)
            self._cash_balances[currency] = balance.deposit(amount)
            self._last_updated = datetime.now()

    def withdraw_cash(self, currency: Currency, amount: Decimal) -> None:
        """Withdraw cash from a currency balance."""
        with self._lock:
            balance = self.get_cash(currency)
            self._cash_balances[currency] = balance.withdraw(amount)
            self._last_updated = datetime.now()

    def reserve_cash(self, currency: Currency, amount: Decimal) -> None:
        """Reserve cash for pending order."""
        with self._lock:
            balance = self.get_cash(currency)
            self._cash_balances[currency] = balance.reserve(amount)
            self._last_updated = datetime.now()

    def release_cash(self, currency: Currency, amount: Decimal) -> None:
        """Release reserved cash."""
        with self._lock:
            balance = self.get_cash(currency)
            self._cash_balances[currency] = balance.release(amount)
            self._last_updated = datetime.now()

    def get_exchange_rate(self, from_currency: Currency, to_currency: Currency) -> Decimal:
        """Get exchange rate between currencies.

        Args:
            from_currency: Source currency
            to_currency: Target currency

        Returns:
            Exchange rate (1.0 if same currency or no provider)
        """
        if from_currency == to_currency:
            return Decimal("1")

        if self._exchange_rate_provider is None:
            # Default to 1 if no provider (assume same currency)
            return Decimal("1")

        rate = self._exchange_rate_provider.get_rate(from_currency, to_currency)
        return rate if rate is not None else Decimal("1")

    def convert_to_base_currency(self, amount: Decimal, from_currency: Currency) -> Decimal:
        """Convert an amount to base currency."""
        rate = self.get_exchange_rate(from_currency, self._base_currency)
        return amount * rate

    @property
    def total_holdings_value(self) -> Decimal:
        """Get total market value of all holdings in base currency."""
        with self._lock:
            total = Decimal("0")
            for holding in self._holdings.values():
                value = holding.market_value
                if holding.currency != self._base_currency:
                    value = self.convert_to_base_currency(value, holding.currency)
                total += value
            return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def total_cash(self) -> Decimal:
        """Get total available cash in base currency."""
        with self._lock:
            total = Decimal("0")
            for balance in self._cash_balances.values():
                available = balance.available
                if balance.currency != self._base_currency:
                    available = self.convert_to_base_currency(available, balance.currency)
                total += available
            return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def total_reserved_cash(self) -> Decimal:
        """Get total reserved cash in base currency."""
        with self._lock:
            total = Decimal("0")
            for balance in self._cash_balances.values():
                reserved = balance.reserved
                if balance.currency != self._base_currency:
                    reserved = self.convert_to_base_currency(reserved, balance.currency)
                total += reserved
            return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def total_value(self) -> Decimal:
        """Get total portfolio value (holdings + cash) in base currency."""
        return (self.total_holdings_value + self.total_cash).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @property
    def total_unrealized_pnl(self) -> Decimal:
        """Get total unrealized P&L in base currency."""
        with self._lock:
            total = Decimal("0")
            for holding in self._holdings.values():
                pnl = holding.unrealized_pnl
                if holding.currency != self._base_currency:
                    pnl = self.convert_to_base_currency(pnl, holding.currency)
                total += pnl
            return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def total_cost_basis(self) -> Decimal:
        """Get total cost basis in base currency."""
        with self._lock:
            total = Decimal("0")
            for holding in self._holdings.values():
                cost = holding.cost_basis
                if holding.currency != self._base_currency:
                    cost = self.convert_to_base_currency(cost, holding.currency)
                total += cost
            return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def get_concentration(self, symbol: str) -> Decimal:
        """Get concentration of a holding as percentage of total portfolio value."""
        total = self.total_value
        if total == 0:
            return Decimal("0")

        with self._lock:
            holding = self._holdings.get(symbol)
            if holding is None:
                return Decimal("0")

            value = holding.market_value
            if holding.currency != self._base_currency:
                value = self.convert_to_base_currency(value, holding.currency)

            return (value / total * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def get_allocations(self) -> Dict[str, Decimal]:
        """Get allocation percentages for all holdings."""
        total = self.total_value
        if total == 0:
            return {}

        with self._lock:
            allocations = {}
            for symbol, holding in self._holdings.items():
                value = holding.market_value
                if holding.currency != self._base_currency:
                    value = self.convert_to_base_currency(value, holding.currency)
                allocations[symbol] = (value / total * 100).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            return allocations

    def get_asset_class_breakdown(self) -> Dict[str, Decimal]:
        """Get breakdown by asset class as percentage of total holdings value."""
        holdings_value = self.total_holdings_value
        if holdings_value == 0:
            return {}

        with self._lock:
            breakdown: Dict[str, Decimal] = {}
            for holding in self._holdings.values():
                value = holding.market_value
                if holding.currency != self._base_currency:
                    value = self.convert_to_base_currency(value, holding.currency)

                asset_class = holding.asset_class
                breakdown[asset_class] = breakdown.get(asset_class, Decimal("0")) + value

            # Convert to percentages
            for asset_class in breakdown:
                breakdown[asset_class] = (breakdown[asset_class] / holdings_value * 100).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

            return breakdown

    def get_currency_exposure(self) -> Dict[Currency, Decimal]:
        """Get exposure to each currency as percentage of total value."""
        total = self.total_value
        if total == 0:
            return {}

        with self._lock:
            exposure: Dict[Currency, Decimal] = {}

            # Holdings exposure
            for holding in self._holdings.values():
                value = holding.market_value
                if holding.currency != self._base_currency:
                    value = self.convert_to_base_currency(value, holding.currency)
                exposure[holding.currency] = exposure.get(holding.currency, Decimal("0")) + value

            # Cash exposure
            for balance in self._cash_balances.values():
                available = balance.available
                if balance.currency != self._base_currency:
                    available = self.convert_to_base_currency(available, balance.currency)
                exposure[balance.currency] = exposure.get(balance.currency, Decimal("0")) + available

            # Convert to percentages
            for currency in exposure:
                exposure[currency] = (exposure[currency] / total * 100).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

            return exposure

    def create_snapshot(self, metadata: Optional[Dict[str, Any]] = None) -> PortfolioSnapshot:
        """Create an immutable snapshot of current portfolio state.

        Args:
            metadata: Additional metadata to include in snapshot

        Returns:
            Immutable PortfolioSnapshot
        """
        with self._lock:
            snapshot = PortfolioSnapshot(
                timestamp=datetime.now(),
                holdings=self._holdings.copy(),
                cash_balances=self._cash_balances.copy(),
                base_currency=self._base_currency,
                total_holdings_value=self.total_holdings_value,
                total_cash=self.total_cash,
                total_portfolio_value=self.total_value,
                unrealized_pnl=self.total_unrealized_pnl,
                metadata=metadata or {},
            )
            self._snapshots.append(snapshot)
            return snapshot

    def get_snapshots(self) -> List[PortfolioSnapshot]:
        """Get all historical snapshots."""
        with self._lock:
            return self._snapshots.copy()

    def get_latest_snapshot(self) -> Optional[PortfolioSnapshot]:
        """Get the most recent snapshot."""
        with self._lock:
            return self._snapshots[-1] if self._snapshots else None

    def clear_snapshots(self) -> int:
        """Clear all snapshots.

        Returns:
            Number of snapshots cleared
        """
        with self._lock:
            count = len(self._snapshots)
            self._snapshots.clear()
            return count

    def to_dict(self) -> Dict[str, Any]:
        """Convert portfolio state to dictionary representation."""
        with self._lock:
            return {
                "base_currency": self._base_currency.value,
                "holdings": {
                    symbol: {
                        "symbol": h.symbol,
                        "quantity": str(h.quantity),
                        "avg_cost": str(h.avg_cost),
                        "current_price": str(h.current_price),
                        "market_value": str(h.market_value),
                        "unrealized_pnl": str(h.unrealized_pnl),
                        "currency": h.currency.value,
                        "asset_class": h.asset_class,
                    }
                    for symbol, h in self._holdings.items()
                },
                "cash_balances": {
                    currency.value: {
                        "available": str(balance.available),
                        "reserved": str(balance.reserved),
                        "total": str(balance.total),
                    }
                    for currency, balance in self._cash_balances.items()
                },
                "summary": {
                    "total_holdings_value": str(self.total_holdings_value),
                    "total_cash": str(self.total_cash),
                    "total_value": str(self.total_value),
                    "total_unrealized_pnl": str(self.total_unrealized_pnl),
                    "num_holdings": self.num_holdings,
                },
                "last_updated": self._last_updated.isoformat() if self._last_updated else None,
            }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        price_provider: Optional[PriceProvider] = None,
        exchange_rate_provider: Optional[ExchangeRateProvider] = None,
    ) -> "PortfolioState":
        """Create portfolio state from dictionary representation.

        Args:
            data: Dictionary representation from to_dict()
            price_provider: Optional price provider
            exchange_rate_provider: Optional exchange rate provider

        Returns:
            New PortfolioState instance
        """
        base_currency = Currency(data.get("base_currency", "USD"))
        portfolio = cls(
            base_currency=base_currency,
            price_provider=price_provider,
            exchange_rate_provider=exchange_rate_provider,
        )

        # Restore holdings
        for symbol, h_data in data.get("holdings", {}).items():
            holding = Holding(
                symbol=h_data["symbol"],
                quantity=Decimal(h_data["quantity"]),
                avg_cost=Decimal(h_data["avg_cost"]),
                current_price=Decimal(h_data["current_price"]),
                currency=Currency(h_data.get("currency", "USD")),
                asset_class=h_data.get("asset_class", "equity"),
            )
            portfolio._holdings[symbol] = holding

        # Restore cash balances
        for currency_str, balance_data in data.get("cash_balances", {}).items():
            currency = Currency(currency_str)
            portfolio._cash_balances[currency] = CashBalance(
                currency=currency,
                available=Decimal(balance_data["available"]),
                reserved=Decimal(balance_data.get("reserved", "0")),
            )

        return portfolio
