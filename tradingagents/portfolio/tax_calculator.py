"""Australian Capital Gains Tax Calculator.

This module provides Australian CGT calculations including:
- CGT calculations with 50% discount for assets held >12 months
- Tax year reports (Australian financial year: July-June)
- Currency conversion for foreign assets
- Capital loss tracking and carry-forward
- FIFO cost basis calculations

Issue #32: [PORT-31] Australian CGT calculator - 50% discount, tax reports

Design Principles:
    - ATO-compliant CGT calculations
    - Australian financial year (July 1 - June 30)
    - Support for various asset classes
    - Comprehensive audit trail
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union


class CGTMethod(Enum):
    """CGT calculation method."""
    DISCOUNT = "discount"     # 50% discount for assets held >12 months
    INDEXATION = "indexation"  # Historical indexation method (pre-1999)
    OTHER = "other"           # No special treatment


class AssetType(Enum):
    """Type of CGT asset."""
    SHARES = "shares"                 # Australian shares
    FOREIGN_SHARES = "foreign_shares"  # Foreign shares
    ETF = "etf"                       # Exchange-traded funds
    CRYPTOCURRENCY = "cryptocurrency"  # Digital assets
    PROPERTY = "property"             # Real estate
    COLLECTABLES = "collectables"     # Art, jewellery, etc.
    OTHER = "other"


@dataclass
class CGTAssetAcquisition:
    """Record of an asset acquisition (cost base parcel).

    Attributes:
        acquisition_date: When the asset was acquired
        quantity: Number of units acquired
        cost_per_unit: Cost per unit in acquisition currency
        total_cost_aud: Total cost in AUD (after currency conversion)
        currency: Currency of acquisition (for foreign assets)
        exchange_rate: Exchange rate used for conversion (if foreign)
        incidental_costs: Brokerage, legal fees, etc.
        asset_id: Optional asset identifier
        metadata: Additional acquisition data
    """
    acquisition_date: date
    quantity: Decimal
    cost_per_unit: Decimal
    total_cost_aud: Decimal
    currency: str = "AUD"
    exchange_rate: Optional[Decimal] = None
    incidental_costs: Decimal = field(default_factory=lambda: Decimal("0"))
    asset_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def cost_base_per_unit(self) -> Decimal:
        """Cost base per unit including incidental costs."""
        if self.quantity == 0:
            return Decimal("0")
        return (self.total_cost_aud + self.incidental_costs) / self.quantity

    @property
    def total_cost_base(self) -> Decimal:
        """Total cost base including incidental costs."""
        return self.total_cost_aud + self.incidental_costs


@dataclass
class CGTDisposal:
    """Record of an asset disposal.

    Attributes:
        disposal_date: When the asset was disposed
        symbol: Asset symbol
        quantity: Number of units disposed
        proceeds_per_unit: Proceeds per unit in disposal currency
        total_proceeds_aud: Total proceeds in AUD
        currency: Currency of proceeds
        exchange_rate: Exchange rate used for conversion
        incidental_costs: Selling costs (brokerage, etc.)
        matched_acquisitions: Acquisitions used for cost base (FIFO)
        metadata: Additional disposal data
    """
    disposal_date: date
    symbol: str
    quantity: Decimal
    proceeds_per_unit: Decimal
    total_proceeds_aud: Decimal
    currency: str = "AUD"
    exchange_rate: Optional[Decimal] = None
    incidental_costs: Decimal = field(default_factory=lambda: Decimal("0"))
    matched_acquisitions: List[Tuple[CGTAssetAcquisition, Decimal]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def net_proceeds(self) -> Decimal:
        """Net proceeds after selling costs."""
        return self.total_proceeds_aud - self.incidental_costs


@dataclass
class CGTEvent:
    """A CGT event (disposal of an asset).

    Attributes:
        event_date: Date of the CGT event
        symbol: Asset symbol
        asset_type: Type of asset
        disposal: Disposal record
        gross_gain: Capital gain/loss before discount
        discount_eligible: Whether 50% discount applies
        discount_amount: Amount of discount (if eligible)
        net_gain: Net capital gain/loss after discount
        holding_period_days: Days between acquisition and disposal
        cgt_method: CGT calculation method used
        tax_year: Australian tax year (ending June 30)
        metadata: Additional event data
    """
    event_date: date
    symbol: str
    asset_type: AssetType
    disposal: CGTDisposal
    gross_gain: Decimal
    discount_eligible: bool
    discount_amount: Decimal
    net_gain: Decimal
    holding_period_days: int
    cgt_method: CGTMethod
    tax_year: int  # Year ending (e.g., 2024 for FY2023-24)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_gain(self) -> bool:
        """Check if this is a capital gain."""
        return self.net_gain > 0

    @property
    def is_loss(self) -> bool:
        """Check if this is a capital loss."""
        return self.net_gain < 0


@dataclass
class TaxYearSummary:
    """Summary of CGT events for an Australian tax year.

    Attributes:
        tax_year: Australian tax year (year ending June 30)
        start_date: Start of tax year (July 1)
        end_date: End of tax year (June 30)
        total_gains: Total capital gains (before applying losses)
        total_losses: Total capital losses
        losses_applied: Losses applied against gains
        carried_forward_losses: Losses carried forward from previous years
        losses_to_carry: Losses to carry forward to next year
        net_capital_gain: Net capital gain after losses
        discounted_gains: Total gains eligible for discount
        discount_applied: Total discount amount applied
        taxable_gain: Final taxable capital gain
        events: List of CGT events in this year
        metadata: Additional summary data
    """
    tax_year: int
    start_date: date
    end_date: date
    total_gains: Decimal
    total_losses: Decimal
    losses_applied: Decimal
    carried_forward_losses: Decimal
    losses_to_carry: Decimal
    net_capital_gain: Decimal
    discounted_gains: Decimal
    discount_applied: Decimal
    taxable_gain: Decimal
    events: List[CGTEvent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def num_events(self) -> int:
        """Number of CGT events in this tax year."""
        return len(self.events)

    @property
    def num_gains(self) -> int:
        """Number of gain events."""
        return sum(1 for e in self.events if e.is_gain)

    @property
    def num_losses(self) -> int:
        """Number of loss events."""
        return sum(1 for e in self.events if e.is_loss)


class AustralianCGTCalculator:
    """Australian Capital Gains Tax calculator.

    Implements Australian CGT rules including:
    - 50% discount for assets held more than 12 months
    - FIFO (First In, First Out) cost base matching
    - Capital loss tracking and carry-forward
    - Australian financial year (July-June)
    - Currency conversion for foreign assets

    Example:
        >>> calculator = AustralianCGTCalculator()
        >>> calculator.add_acquisition(
        ...     symbol="CBA.AX",
        ...     acquisition_date=date(2023, 1, 15),
        ...     quantity=Decimal("100"),
        ...     cost_per_unit=Decimal("95.50"),
        ... )
        >>> event = calculator.dispose(
        ...     symbol="CBA.AX",
        ...     disposal_date=date(2024, 3, 20),
        ...     quantity=Decimal("50"),
        ...     proceeds_per_unit=Decimal("110.25"),
        ... )
        >>> print(f"Net gain: ${event.net_gain}")
    """

    # CGT discount rate for eligible assets
    DISCOUNT_RATE = Decimal("0.50")

    # Minimum holding period for discount (in days)
    DISCOUNT_HOLDING_DAYS = 365  # > 12 months

    def __init__(self, base_currency: str = "AUD"):
        """Initialize the CGT calculator.

        Args:
            base_currency: Base currency for calculations (should be AUD)
        """
        self.base_currency = base_currency
        self._holdings: Dict[str, List[CGTAssetAcquisition]] = {}
        self._asset_types: Dict[str, AssetType] = {}
        self._events: List[CGTEvent] = []
        self._carried_forward_losses: Decimal = Decimal("0")

    @staticmethod
    def get_tax_year(event_date: date) -> int:
        """Get Australian tax year for a date.

        Australian tax year runs July 1 to June 30.
        Returns the year in which the tax year ends.

        Args:
            event_date: Date to check

        Returns:
            Tax year (year ending) - e.g., 2024 for FY2023-24
        """
        if event_date.month >= 7:
            # July onwards is next tax year
            return event_date.year + 1
        else:
            # January to June is current calendar year
            return event_date.year

    @staticmethod
    def get_tax_year_dates(tax_year: int) -> Tuple[date, date]:
        """Get start and end dates for an Australian tax year.

        Args:
            tax_year: Tax year (year ending)

        Returns:
            Tuple of (start_date, end_date)
        """
        start = date(tax_year - 1, 7, 1)
        end = date(tax_year, 6, 30)
        return start, end

    def set_asset_type(self, symbol: str, asset_type: AssetType) -> None:
        """Set the asset type for a symbol.

        Args:
            symbol: Asset symbol
            asset_type: Type of asset
        """
        self._asset_types[symbol] = asset_type

    def get_asset_type(self, symbol: str) -> AssetType:
        """Get the asset type for a symbol.

        Args:
            symbol: Asset symbol

        Returns:
            Asset type (defaults to SHARES if not set)
        """
        return self._asset_types.get(symbol, AssetType.SHARES)

    def add_acquisition(
        self,
        symbol: str,
        acquisition_date: date,
        quantity: Decimal,
        cost_per_unit: Decimal,
        currency: str = "AUD",
        exchange_rate: Optional[Decimal] = None,
        incidental_costs: Decimal = Decimal("0"),
        asset_type: Optional[AssetType] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CGTAssetAcquisition:
        """Add an asset acquisition (purchase).

        Args:
            symbol: Asset symbol
            acquisition_date: Date of acquisition
            quantity: Number of units acquired
            cost_per_unit: Cost per unit in acquisition currency
            currency: Currency of acquisition
            exchange_rate: Exchange rate to AUD (for foreign assets)
            incidental_costs: Brokerage and other acquisition costs
            asset_type: Type of asset
            metadata: Additional data

        Returns:
            The created CGTAssetAcquisition record
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if cost_per_unit < 0:
            raise ValueError("Cost per unit must be non-negative")

        # Calculate total cost in AUD
        total_cost = quantity * cost_per_unit
        if currency != "AUD":
            if exchange_rate is None:
                raise ValueError("Exchange rate required for foreign currency acquisitions")
            total_cost_aud = total_cost * exchange_rate
        else:
            total_cost_aud = total_cost
            exchange_rate = Decimal("1")

        acquisition = CGTAssetAcquisition(
            acquisition_date=acquisition_date,
            quantity=quantity,
            cost_per_unit=cost_per_unit,
            total_cost_aud=total_cost_aud,
            currency=currency,
            exchange_rate=exchange_rate,
            incidental_costs=incidental_costs,
            metadata=metadata or {},
        )

        if symbol not in self._holdings:
            self._holdings[symbol] = []
        self._holdings[symbol].append(acquisition)

        # Sort by acquisition date (FIFO order)
        self._holdings[symbol].sort(key=lambda x: x.acquisition_date)

        if asset_type:
            self._asset_types[symbol] = asset_type

        return acquisition

    def get_holdings(self, symbol: str) -> List[CGTAssetAcquisition]:
        """Get current holdings for a symbol.

        Args:
            symbol: Asset symbol

        Returns:
            List of acquisition parcels (in FIFO order)
        """
        return self._holdings.get(symbol, []).copy()

    def get_holding_quantity(self, symbol: str) -> Decimal:
        """Get total quantity held for a symbol.

        Args:
            symbol: Asset symbol

        Returns:
            Total quantity held
        """
        holdings = self._holdings.get(symbol, [])
        return sum(h.quantity for h in holdings)

    def dispose(
        self,
        symbol: str,
        disposal_date: date,
        quantity: Decimal,
        proceeds_per_unit: Decimal,
        currency: str = "AUD",
        exchange_rate: Optional[Decimal] = None,
        incidental_costs: Decimal = Decimal("0"),
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CGTEvent:
        """Dispose of an asset (sell).

        Uses FIFO matching to determine cost base.

        Args:
            symbol: Asset symbol
            disposal_date: Date of disposal
            quantity: Number of units disposed
            proceeds_per_unit: Proceeds per unit in disposal currency
            currency: Currency of proceeds
            exchange_rate: Exchange rate to AUD (for foreign currencies)
            incidental_costs: Brokerage and other selling costs
            metadata: Additional data

        Returns:
            The CGT event for this disposal

        Raises:
            ValueError: If insufficient holdings for disposal
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        holdings = self._holdings.get(symbol, [])
        total_held = sum(h.quantity for h in holdings)

        if quantity > total_held:
            raise ValueError(f"Insufficient holdings: have {total_held}, trying to dispose {quantity}")

        # Calculate total proceeds in AUD
        total_proceeds = quantity * proceeds_per_unit
        if currency != "AUD":
            if exchange_rate is None:
                raise ValueError("Exchange rate required for foreign currency disposals")
            total_proceeds_aud = total_proceeds * exchange_rate
        else:
            total_proceeds_aud = total_proceeds
            exchange_rate = Decimal("1")

        # Match acquisitions using FIFO
        remaining = quantity
        matched: List[Tuple[CGTAssetAcquisition, Decimal]] = []
        total_cost_base = Decimal("0")
        weighted_holding_days = 0

        new_holdings = []
        for acquisition in holdings:
            if remaining <= 0:
                new_holdings.append(acquisition)
                continue

            if acquisition.quantity <= remaining:
                # Use entire parcel
                matched.append((acquisition, acquisition.quantity))
                total_cost_base += acquisition.total_cost_base
                days_held = (disposal_date - acquisition.acquisition_date).days
                weighted_holding_days += days_held * int(acquisition.quantity)
                remaining -= acquisition.quantity
            else:
                # Partial use of parcel
                matched.append((acquisition, remaining))
                fraction = remaining / acquisition.quantity
                total_cost_base += acquisition.total_cost_base * fraction
                days_held = (disposal_date - acquisition.acquisition_date).days
                weighted_holding_days += days_held * int(remaining)

                # Create remaining parcel
                remaining_parcel = CGTAssetAcquisition(
                    acquisition_date=acquisition.acquisition_date,
                    quantity=acquisition.quantity - remaining,
                    cost_per_unit=acquisition.cost_per_unit,
                    total_cost_aud=acquisition.total_cost_aud * (Decimal("1") - fraction),
                    currency=acquisition.currency,
                    exchange_rate=acquisition.exchange_rate,
                    incidental_costs=acquisition.incidental_costs * (Decimal("1") - fraction),
                    asset_id=acquisition.asset_id,
                    metadata=acquisition.metadata,
                )
                new_holdings.append(remaining_parcel)
                remaining = Decimal("0")

        self._holdings[symbol] = new_holdings

        # Create disposal record
        disposal = CGTDisposal(
            disposal_date=disposal_date,
            symbol=symbol,
            quantity=quantity,
            proceeds_per_unit=proceeds_per_unit,
            total_proceeds_aud=total_proceeds_aud,
            currency=currency,
            exchange_rate=exchange_rate,
            incidental_costs=incidental_costs,
            matched_acquisitions=matched,
            metadata=metadata or {},
        )

        # Calculate gain/loss
        net_proceeds = disposal.net_proceeds
        gross_gain = net_proceeds - total_cost_base

        # Calculate weighted average holding period
        # Handle fractional quantities by using float division with rounding
        if quantity > 0:
            avg_holding_days = int(weighted_holding_days / float(quantity))
        else:
            avg_holding_days = 0

        # Determine if discount eligible
        discount_eligible = (
            gross_gain > 0 and
            avg_holding_days > self.DISCOUNT_HOLDING_DAYS
        )

        # Calculate discount
        if discount_eligible:
            discount_amount = gross_gain * self.DISCOUNT_RATE
            net_gain = gross_gain - discount_amount
            cgt_method = CGTMethod.DISCOUNT
        else:
            discount_amount = Decimal("0")
            net_gain = gross_gain
            cgt_method = CGTMethod.OTHER

        # Create CGT event
        event = CGTEvent(
            event_date=disposal_date,
            symbol=symbol,
            asset_type=self.get_asset_type(symbol),
            disposal=disposal,
            gross_gain=gross_gain.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            discount_eligible=discount_eligible,
            discount_amount=discount_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            net_gain=net_gain.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            holding_period_days=avg_holding_days,
            cgt_method=cgt_method,
            tax_year=self.get_tax_year(disposal_date),
            metadata=metadata or {},
        )

        self._events.append(event)
        return event

    def get_events(self, tax_year: Optional[int] = None) -> List[CGTEvent]:
        """Get CGT events, optionally filtered by tax year.

        Args:
            tax_year: Optional tax year to filter by

        Returns:
            List of CGT events
        """
        if tax_year is None:
            return self._events.copy()
        return [e for e in self._events if e.tax_year == tax_year]

    def set_carried_forward_losses(self, amount: Decimal) -> None:
        """Set carried forward losses from previous years.

        Args:
            amount: Loss amount to carry forward (should be positive)
        """
        if amount < 0:
            raise ValueError("Carried forward losses must be non-negative")
        self._carried_forward_losses = amount

    def get_carried_forward_losses(self) -> Decimal:
        """Get current carried forward losses."""
        return self._carried_forward_losses

    def calculate_tax_year_summary(
        self,
        tax_year: int,
        apply_carried_losses: bool = True,
    ) -> TaxYearSummary:
        """Calculate CGT summary for a tax year.

        The ATO rules for applying capital losses:
        1. Capital losses must first be applied to capital gains
        2. Current year losses applied first, then carried forward losses
        3. Losses are applied to discount gains BEFORE the discount
        4. Excess losses are carried forward (never expire)

        Args:
            tax_year: Australian tax year (year ending)
            apply_carried_losses: Whether to apply carried forward losses

        Returns:
            TaxYearSummary with complete CGT calculations
        """
        events = self.get_events(tax_year)
        start_date, end_date = self.get_tax_year_dates(tax_year)

        # Separate gains and losses
        gains = [e for e in events if e.is_gain]
        losses = [e for e in events if e.is_loss]

        # Calculate totals (using gross gain for gains before discount)
        # Use Decimal("0") as start to ensure result is Decimal, not int
        total_gains = sum((e.gross_gain for e in gains), Decimal("0"))
        total_losses = abs(sum((e.net_gain for e in losses), Decimal("0")))

        # Discounted vs non-discounted gains
        discounted_gains = sum(
            (e.gross_gain for e in gains if e.discount_eligible), Decimal("0")
        )
        non_discounted_gains = sum(
            (e.gross_gain for e in gains if not e.discount_eligible), Decimal("0")
        )

        # Available losses (current year + carried forward)
        carried_forward = self._carried_forward_losses if apply_carried_losses else Decimal("0")
        total_available_losses = total_losses + carried_forward

        # Apply losses to gains
        # First, apply to non-discounted gains
        losses_to_non_discounted = min(total_available_losses, non_discounted_gains)
        remaining_losses = total_available_losses - losses_to_non_discounted

        # Then, apply remaining losses to discounted gains (before discount)
        losses_to_discounted = min(remaining_losses, discounted_gains)
        remaining_losses = remaining_losses - losses_to_discounted

        # Calculate net gains after losses
        net_non_discounted = non_discounted_gains - losses_to_non_discounted
        net_discounted_before_discount = discounted_gains - losses_to_discounted

        # Apply 50% discount to remaining discounted gains
        discount_applied = net_discounted_before_discount * self.DISCOUNT_RATE
        net_discounted_after_discount = net_discounted_before_discount - discount_applied

        # Final taxable gain
        taxable_gain = net_non_discounted + net_discounted_after_discount
        taxable_gain = max(Decimal("0"), taxable_gain)  # Can't be negative

        # Calculate losses applied and to carry forward
        losses_applied = losses_to_non_discounted + losses_to_discounted
        losses_to_carry = remaining_losses

        # Net capital gain (before considering losses for report)
        net_capital_gain = total_gains - total_losses
        if apply_carried_losses:
            net_capital_gain -= carried_forward

        return TaxYearSummary(
            tax_year=tax_year,
            start_date=start_date,
            end_date=end_date,
            total_gains=total_gains.quantize(Decimal("0.01")),
            total_losses=total_losses.quantize(Decimal("0.01")),
            losses_applied=losses_applied.quantize(Decimal("0.01")),
            carried_forward_losses=carried_forward.quantize(Decimal("0.01")),
            losses_to_carry=losses_to_carry.quantize(Decimal("0.01")),
            net_capital_gain=net_capital_gain.quantize(Decimal("0.01")),
            discounted_gains=discounted_gains.quantize(Decimal("0.01")),
            discount_applied=discount_applied.quantize(Decimal("0.01")),
            taxable_gain=taxable_gain.quantize(Decimal("0.01")),
            events=events,
        )

    def generate_tax_report(
        self,
        tax_year: int,
        include_details: bool = True,
    ) -> Dict[str, Any]:
        """Generate a tax report for the ATO.

        Args:
            tax_year: Australian tax year (year ending)
            include_details: Whether to include detailed transaction list

        Returns:
            Dictionary with tax report data
        """
        summary = self.calculate_tax_year_summary(tax_year)

        report = {
            "tax_year": f"FY{tax_year - 1}-{str(tax_year)[-2:]}",
            "period": {
                "start": summary.start_date.isoformat(),
                "end": summary.end_date.isoformat(),
            },
            "summary": {
                "total_capital_gains": str(summary.total_gains),
                "total_capital_losses": str(summary.total_losses),
                "net_capital_gain": str(summary.net_capital_gain),
                "discount_method_gains": str(summary.discounted_gains),
                "cgt_discount_applied": str(summary.discount_applied),
                "prior_year_losses_applied": str(summary.carried_forward_losses),
                "current_year_losses_applied": str(summary.losses_applied - summary.carried_forward_losses),
                "losses_carried_forward": str(summary.losses_to_carry),
                "taxable_capital_gain": str(summary.taxable_gain),
            },
            "statistics": {
                "number_of_disposals": summary.num_events,
                "number_of_gains": summary.num_gains,
                "number_of_losses": summary.num_losses,
            },
        }

        if include_details:
            report["transactions"] = [
                {
                    "date": event.event_date.isoformat(),
                    "symbol": event.symbol,
                    "asset_type": event.asset_type.value,
                    "quantity": str(event.disposal.quantity),
                    "proceeds": str(event.disposal.total_proceeds_aud),
                    "cost_base": str(sum(
                        acq.total_cost_base * (qty / acq.quantity)
                        for acq, qty in event.disposal.matched_acquisitions
                    )),
                    "gross_gain_loss": str(event.gross_gain),
                    "holding_period_days": event.holding_period_days,
                    "discount_eligible": event.discount_eligible,
                    "discount_amount": str(event.discount_amount),
                    "net_gain_loss": str(event.net_gain),
                }
                for event in summary.events
            ]

        return report

    def get_unrealised_gains(self, current_prices: Dict[str, Decimal]) -> Dict[str, Dict[str, Decimal]]:
        """Calculate unrealised gains for current holdings.

        Args:
            current_prices: Dictionary of symbol -> current price in AUD

        Returns:
            Dictionary of symbol -> {quantity, cost_base, market_value, unrealised_gain}
        """
        result = {}

        for symbol, holdings in self._holdings.items():
            if not holdings:
                continue

            total_quantity = sum(h.quantity for h in holdings)
            total_cost_base = sum(h.total_cost_base for h in holdings)

            if symbol in current_prices:
                market_value = total_quantity * current_prices[symbol]
                unrealised_gain = market_value - total_cost_base
            else:
                market_value = Decimal("0")
                unrealised_gain = Decimal("0")

            result[symbol] = {
                "quantity": total_quantity,
                "cost_base": total_cost_base.quantize(Decimal("0.01")),
                "market_value": market_value.quantize(Decimal("0.01")),
                "unrealised_gain": unrealised_gain.quantize(Decimal("0.01")),
            }

        return result

    def clear(self) -> None:
        """Clear all holdings, events, and carried losses."""
        self._holdings.clear()
        self._asset_types.clear()
        self._events.clear()
        self._carried_forward_losses = Decimal("0")
