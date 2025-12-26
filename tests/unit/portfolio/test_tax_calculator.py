"""Tests for Australian CGT Calculator.

Issue #32: [PORT-31] Australian CGT calculator - 50% discount, tax reports

Tests cover:
- CGT enums and dataclasses
- Acquisition and disposal recording
- FIFO cost basis matching
- 50% CGT discount for holdings >12 months
- Tax year calculations (July-June)
- Capital loss tracking and carry-forward
- Tax report generation
- Foreign currency conversions
- Edge cases and validation
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from tradingagents.portfolio.tax_calculator import (
    CGTMethod,
    AssetType,
    CGTAssetAcquisition,
    CGTDisposal,
    CGTEvent,
    TaxYearSummary,
    AustralianCGTCalculator,
)


# ==============================================================================
# CGTMethod Enum Tests
# ==============================================================================


class TestCGTMethod:
    """Tests for CGTMethod enum."""

    def test_discount_value(self):
        """Test DISCOUNT method value."""
        assert CGTMethod.DISCOUNT.value == "discount"

    def test_indexation_value(self):
        """Test INDEXATION method value."""
        assert CGTMethod.INDEXATION.value == "indexation"

    def test_other_value(self):
        """Test OTHER method value."""
        assert CGTMethod.OTHER.value == "other"

    def test_all_methods_exist(self):
        """Test all expected methods exist."""
        methods = [m for m in CGTMethod]
        assert len(methods) == 3
        assert CGTMethod.DISCOUNT in methods
        assert CGTMethod.INDEXATION in methods
        assert CGTMethod.OTHER in methods


# ==============================================================================
# AssetType Enum Tests
# ==============================================================================


class TestAssetType:
    """Tests for AssetType enum."""

    def test_shares_value(self):
        """Test SHARES type value."""
        assert AssetType.SHARES.value == "shares"

    def test_foreign_shares_value(self):
        """Test FOREIGN_SHARES type value."""
        assert AssetType.FOREIGN_SHARES.value == "foreign_shares"

    def test_etf_value(self):
        """Test ETF type value."""
        assert AssetType.ETF.value == "etf"

    def test_cryptocurrency_value(self):
        """Test CRYPTOCURRENCY type value."""
        assert AssetType.CRYPTOCURRENCY.value == "cryptocurrency"

    def test_property_value(self):
        """Test PROPERTY type value."""
        assert AssetType.PROPERTY.value == "property"

    def test_collectables_value(self):
        """Test COLLECTABLES type value."""
        assert AssetType.COLLECTABLES.value == "collectables"

    def test_other_value(self):
        """Test OTHER type value."""
        assert AssetType.OTHER.value == "other"

    def test_all_types_exist(self):
        """Test all expected asset types exist."""
        types = [t for t in AssetType]
        assert len(types) == 7


# ==============================================================================
# CGTAssetAcquisition Tests
# ==============================================================================


class TestCGTAssetAcquisition:
    """Tests for CGTAssetAcquisition dataclass."""

    def test_create_basic_acquisition(self):
        """Test creating a basic AUD acquisition."""
        acq = CGTAssetAcquisition(
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("95.50"),
            total_cost_aud=Decimal("9550"),
        )
        assert acq.acquisition_date == date(2023, 1, 15)
        assert acq.quantity == Decimal("100")
        assert acq.cost_per_unit == Decimal("95.50")
        assert acq.total_cost_aud == Decimal("9550")
        assert acq.currency == "AUD"
        assert acq.exchange_rate is None
        assert acq.incidental_costs == Decimal("0")

    def test_acquisition_with_incidental_costs(self):
        """Test acquisition with brokerage fees."""
        acq = CGTAssetAcquisition(
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("95.50"),
            total_cost_aud=Decimal("9550"),
            incidental_costs=Decimal("19.95"),
        )
        assert acq.incidental_costs == Decimal("19.95")
        assert acq.total_cost_base == Decimal("9569.95")

    def test_cost_base_per_unit(self):
        """Test cost base per unit calculation."""
        acq = CGTAssetAcquisition(
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("95.50"),
            total_cost_aud=Decimal("9550"),
            incidental_costs=Decimal("50"),
        )
        # (9550 + 50) / 100 = 96.00
        assert acq.cost_base_per_unit == Decimal("96")

    def test_cost_base_per_unit_zero_quantity(self):
        """Test cost base per unit with zero quantity."""
        acq = CGTAssetAcquisition(
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("0"),
            cost_per_unit=Decimal("95.50"),
            total_cost_aud=Decimal("0"),
        )
        assert acq.cost_base_per_unit == Decimal("0")

    def test_foreign_acquisition(self):
        """Test foreign currency acquisition."""
        acq = CGTAssetAcquisition(
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("50"),
            cost_per_unit=Decimal("150"),  # USD
            total_cost_aud=Decimal("11250"),  # After AUD conversion
            currency="USD",
            exchange_rate=Decimal("1.50"),
        )
        assert acq.currency == "USD"
        assert acq.exchange_rate == Decimal("1.50")
        assert acq.total_cost_aud == Decimal("11250")


# ==============================================================================
# CGTDisposal Tests
# ==============================================================================


class TestCGTDisposal:
    """Tests for CGTDisposal dataclass."""

    def test_create_basic_disposal(self):
        """Test creating a basic disposal."""
        disposal = CGTDisposal(
            disposal_date=date(2024, 3, 20),
            symbol="CBA.AX",
            quantity=Decimal("50"),
            proceeds_per_unit=Decimal("110.25"),
            total_proceeds_aud=Decimal("5512.50"),
        )
        assert disposal.disposal_date == date(2024, 3, 20)
        assert disposal.symbol == "CBA.AX"
        assert disposal.quantity == Decimal("50")
        assert disposal.total_proceeds_aud == Decimal("5512.50")

    def test_net_proceeds_calculation(self):
        """Test net proceeds after selling costs."""
        disposal = CGTDisposal(
            disposal_date=date(2024, 3, 20),
            symbol="CBA.AX",
            quantity=Decimal("50"),
            proceeds_per_unit=Decimal("110.25"),
            total_proceeds_aud=Decimal("5512.50"),
            incidental_costs=Decimal("19.95"),
        )
        assert disposal.net_proceeds == Decimal("5492.55")


# ==============================================================================
# CGTEvent Tests
# ==============================================================================


class TestCGTEvent:
    """Tests for CGTEvent dataclass."""

    def test_is_gain(self):
        """Test capital gain detection."""
        disposal = CGTDisposal(
            disposal_date=date(2024, 3, 20),
            symbol="CBA.AX",
            quantity=Decimal("50"),
            proceeds_per_unit=Decimal("110.25"),
            total_proceeds_aud=Decimal("5512.50"),
        )
        event = CGTEvent(
            event_date=date(2024, 3, 20),
            symbol="CBA.AX",
            asset_type=AssetType.SHARES,
            disposal=disposal,
            gross_gain=Decimal("737.50"),
            discount_eligible=True,
            discount_amount=Decimal("368.75"),
            net_gain=Decimal("368.75"),
            holding_period_days=430,
            cgt_method=CGTMethod.DISCOUNT,
            tax_year=2024,
        )
        assert event.is_gain is True
        assert event.is_loss is False

    def test_is_loss(self):
        """Test capital loss detection."""
        disposal = CGTDisposal(
            disposal_date=date(2024, 3, 20),
            symbol="CBA.AX",
            quantity=Decimal("50"),
            proceeds_per_unit=Decimal("80"),
            total_proceeds_aud=Decimal("4000"),
        )
        event = CGTEvent(
            event_date=date(2024, 3, 20),
            symbol="CBA.AX",
            asset_type=AssetType.SHARES,
            disposal=disposal,
            gross_gain=Decimal("-775"),
            discount_eligible=False,
            discount_amount=Decimal("0"),
            net_gain=Decimal("-775"),
            holding_period_days=430,
            cgt_method=CGTMethod.OTHER,
            tax_year=2024,
        )
        assert event.is_gain is False
        assert event.is_loss is True


# ==============================================================================
# TaxYearSummary Tests
# ==============================================================================


class TestTaxYearSummary:
    """Tests for TaxYearSummary dataclass."""

    def test_num_events(self):
        """Test event count property."""
        summary = TaxYearSummary(
            tax_year=2024,
            start_date=date(2023, 7, 1),
            end_date=date(2024, 6, 30),
            total_gains=Decimal("1000"),
            total_losses=Decimal("200"),
            losses_applied=Decimal("200"),
            carried_forward_losses=Decimal("0"),
            losses_to_carry=Decimal("0"),
            net_capital_gain=Decimal("800"),
            discounted_gains=Decimal("1000"),
            discount_applied=Decimal("400"),
            taxable_gain=Decimal("400"),
            events=[],
        )
        assert summary.num_events == 0

    def test_num_gains_and_losses(self):
        """Test gain and loss count properties."""
        disposal1 = CGTDisposal(
            disposal_date=date(2024, 1, 15),
            symbol="CBA.AX",
            quantity=Decimal("50"),
            proceeds_per_unit=Decimal("110"),
            total_proceeds_aud=Decimal("5500"),
        )
        event1 = CGTEvent(
            event_date=date(2024, 1, 15),
            symbol="CBA.AX",
            asset_type=AssetType.SHARES,
            disposal=disposal1,
            gross_gain=Decimal("500"),
            discount_eligible=True,
            discount_amount=Decimal("250"),
            net_gain=Decimal("250"),
            holding_period_days=400,
            cgt_method=CGTMethod.DISCOUNT,
            tax_year=2024,
        )
        disposal2 = CGTDisposal(
            disposal_date=date(2024, 2, 15),
            symbol="NAB.AX",
            quantity=Decimal("50"),
            proceeds_per_unit=Decimal("25"),
            total_proceeds_aud=Decimal("1250"),
        )
        event2 = CGTEvent(
            event_date=date(2024, 2, 15),
            symbol="NAB.AX",
            asset_type=AssetType.SHARES,
            disposal=disposal2,
            gross_gain=Decimal("-250"),
            discount_eligible=False,
            discount_amount=Decimal("0"),
            net_gain=Decimal("-250"),
            holding_period_days=100,
            cgt_method=CGTMethod.OTHER,
            tax_year=2024,
        )
        summary = TaxYearSummary(
            tax_year=2024,
            start_date=date(2023, 7, 1),
            end_date=date(2024, 6, 30),
            total_gains=Decimal("500"),
            total_losses=Decimal("250"),
            losses_applied=Decimal("250"),
            carried_forward_losses=Decimal("0"),
            losses_to_carry=Decimal("0"),
            net_capital_gain=Decimal("250"),
            discounted_gains=Decimal("500"),
            discount_applied=Decimal("125"),
            taxable_gain=Decimal("125"),
            events=[event1, event2],
        )
        assert summary.num_events == 2
        assert summary.num_gains == 1
        assert summary.num_losses == 1


# ==============================================================================
# AustralianCGTCalculator - Tax Year Tests
# ==============================================================================


class TestTaxYearCalculations:
    """Tests for Australian tax year calculations."""

    def test_tax_year_july_date(self):
        """Test tax year for July date (start of new FY)."""
        # July 1, 2023 is in FY2023-24 (tax year 2024)
        assert AustralianCGTCalculator.get_tax_year(date(2023, 7, 1)) == 2024

    def test_tax_year_june_date(self):
        """Test tax year for June date (end of FY)."""
        # June 30, 2024 is in FY2023-24 (tax year 2024)
        assert AustralianCGTCalculator.get_tax_year(date(2024, 6, 30)) == 2024

    def test_tax_year_january_date(self):
        """Test tax year for January date."""
        # January 15, 2024 is in FY2023-24 (tax year 2024)
        assert AustralianCGTCalculator.get_tax_year(date(2024, 1, 15)) == 2024

    def test_tax_year_december_date(self):
        """Test tax year for December date."""
        # December 15, 2023 is in FY2023-24 (tax year 2024)
        assert AustralianCGTCalculator.get_tax_year(date(2023, 12, 15)) == 2024

    def test_tax_year_dates(self):
        """Test getting tax year start and end dates."""
        start, end = AustralianCGTCalculator.get_tax_year_dates(2024)
        assert start == date(2023, 7, 1)
        assert end == date(2024, 6, 30)


# ==============================================================================
# AustralianCGTCalculator - Acquisition Tests
# ==============================================================================


class TestAcquisitions:
    """Tests for asset acquisition recording."""

    def test_add_basic_acquisition(self):
        """Test adding a basic AUD acquisition."""
        calculator = AustralianCGTCalculator()
        acq = calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("95.50"),
        )
        assert acq.quantity == Decimal("100")
        assert acq.cost_per_unit == Decimal("95.50")
        assert acq.total_cost_aud == Decimal("9550")
        assert calculator.get_holding_quantity("CBA.AX") == Decimal("100")

    def test_add_acquisition_with_brokerage(self):
        """Test adding acquisition with incidental costs."""
        calculator = AustralianCGTCalculator()
        acq = calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("95.50"),
            incidental_costs=Decimal("19.95"),
        )
        assert acq.incidental_costs == Decimal("19.95")
        assert acq.total_cost_base == Decimal("9569.95")

    def test_add_foreign_acquisition(self):
        """Test adding a foreign currency acquisition."""
        calculator = AustralianCGTCalculator()
        acq = calculator.add_acquisition(
            symbol="AAPL",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("50"),
            cost_per_unit=Decimal("150"),  # USD
            currency="USD",
            exchange_rate=Decimal("1.50"),  # AUD per USD
        )
        assert acq.currency == "USD"
        assert acq.exchange_rate == Decimal("1.50")
        # 50 * 150 * 1.50 = 11250
        assert acq.total_cost_aud == Decimal("11250")

    def test_add_multiple_acquisitions_same_symbol(self):
        """Test adding multiple parcels of same asset."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("95.50"),
        )
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 6, 20),
            quantity=Decimal("50"),
            cost_per_unit=Decimal("100"),
        )
        assert calculator.get_holding_quantity("CBA.AX") == Decimal("150")
        holdings = calculator.get_holdings("CBA.AX")
        assert len(holdings) == 2
        # Should be sorted by acquisition date (FIFO)
        assert holdings[0].acquisition_date == date(2023, 1, 15)
        assert holdings[1].acquisition_date == date(2023, 6, 20)

    def test_acquisition_with_asset_type(self):
        """Test setting asset type on acquisition."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="BTC",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("0.5"),
            cost_per_unit=Decimal("30000"),
            asset_type=AssetType.CRYPTOCURRENCY,
        )
        assert calculator.get_asset_type("BTC") == AssetType.CRYPTOCURRENCY

    def test_acquisition_invalid_quantity(self):
        """Test acquisition with invalid quantity."""
        calculator = AustralianCGTCalculator()
        with pytest.raises(ValueError, match="Quantity must be positive"):
            calculator.add_acquisition(
                symbol="CBA.AX",
                acquisition_date=date(2023, 1, 15),
                quantity=Decimal("0"),
                cost_per_unit=Decimal("95.50"),
            )

    def test_acquisition_negative_quantity(self):
        """Test acquisition with negative quantity."""
        calculator = AustralianCGTCalculator()
        with pytest.raises(ValueError, match="Quantity must be positive"):
            calculator.add_acquisition(
                symbol="CBA.AX",
                acquisition_date=date(2023, 1, 15),
                quantity=Decimal("-10"),
                cost_per_unit=Decimal("95.50"),
            )

    def test_foreign_acquisition_missing_exchange_rate(self):
        """Test foreign acquisition without exchange rate."""
        calculator = AustralianCGTCalculator()
        with pytest.raises(ValueError, match="Exchange rate required"):
            calculator.add_acquisition(
                symbol="AAPL",
                acquisition_date=date(2023, 1, 15),
                quantity=Decimal("50"),
                cost_per_unit=Decimal("150"),
                currency="USD",
            )


# ==============================================================================
# AustralianCGTCalculator - Disposal Tests
# ==============================================================================


class TestDisposals:
    """Tests for asset disposal and CGT calculation."""

    def test_basic_disposal_with_gain(self):
        """Test basic disposal with capital gain."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("95.50"),
        )
        event = calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2023, 6, 20),  # Less than 12 months
            quantity=Decimal("50"),
            proceeds_per_unit=Decimal("110.25"),
        )
        assert event.symbol == "CBA.AX"
        assert event.disposal.quantity == Decimal("50")
        # Proceeds: 50 * 110.25 = 5512.50
        # Cost: 50 * 95.50 = 4775
        # Gain: 5512.50 - 4775 = 737.50
        assert event.gross_gain == Decimal("737.50")
        assert event.discount_eligible is False  # Less than 12 months
        assert event.net_gain == Decimal("737.50")
        assert event.cgt_method == CGTMethod.OTHER

    def test_disposal_with_discount(self):
        """Test disposal eligible for 50% CGT discount."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("95.50"),
        )
        event = calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2024, 3, 20),  # More than 12 months
            quantity=Decimal("50"),
            proceeds_per_unit=Decimal("110.25"),
        )
        assert event.discount_eligible is True
        assert event.gross_gain == Decimal("737.50")
        assert event.discount_amount == Decimal("368.75")
        assert event.net_gain == Decimal("368.75")
        assert event.cgt_method == CGTMethod.DISCOUNT

    def test_disposal_with_loss_no_discount(self):
        """Test disposal with capital loss (no discount on losses)."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("95.50"),
        )
        event = calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2024, 3, 20),  # More than 12 months
            quantity=Decimal("50"),
            proceeds_per_unit=Decimal("80"),  # Selling at loss
        )
        # Proceeds: 50 * 80 = 4000
        # Cost: 50 * 95.50 = 4775
        # Loss: 4000 - 4775 = -775
        assert event.gross_gain == Decimal("-775.00")
        assert event.discount_eligible is False  # No discount on losses
        assert event.discount_amount == Decimal("0.00")
        assert event.net_gain == Decimal("-775.00")
        assert event.is_loss is True

    def test_disposal_fifo_matching(self):
        """Test FIFO cost basis matching."""
        calculator = AustralianCGTCalculator()
        # First parcel at $90
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        # Second parcel at $100
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 6, 20),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("100"),
        )
        # Dispose 150 shares - should use first 100 at $90, then 50 at $100
        event = calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2023, 9, 15),
            quantity=Decimal("150"),
            proceeds_per_unit=Decimal("105"),
        )
        # Proceeds: 150 * 105 = 15750
        # Cost: 100 * 90 + 50 * 100 = 9000 + 5000 = 14000
        # Gain: 15750 - 14000 = 1750
        assert event.gross_gain == Decimal("1750.00")
        # Remaining should be 50 shares at $100
        assert calculator.get_holding_quantity("CBA.AX") == Decimal("50")

    def test_disposal_partial_parcel(self):
        """Test partial disposal of a parcel."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("95.50"),
        )
        calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2023, 6, 20),
            quantity=Decimal("30"),
            proceeds_per_unit=Decimal("100"),
        )
        # Remaining should be 70 shares
        assert calculator.get_holding_quantity("CBA.AX") == Decimal("70")
        holdings = calculator.get_holdings("CBA.AX")
        assert len(holdings) == 1
        assert holdings[0].quantity == Decimal("70")

    def test_disposal_insufficient_holdings(self):
        """Test disposal with insufficient holdings."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("95.50"),
        )
        with pytest.raises(ValueError, match="Insufficient holdings"):
            calculator.dispose(
                symbol="CBA.AX",
                disposal_date=date(2023, 6, 20),
                quantity=Decimal("150"),
                proceeds_per_unit=Decimal("100"),
            )

    def test_disposal_no_holdings(self):
        """Test disposal with no holdings."""
        calculator = AustralianCGTCalculator()
        with pytest.raises(ValueError, match="Insufficient holdings"):
            calculator.dispose(
                symbol="CBA.AX",
                disposal_date=date(2023, 6, 20),
                quantity=Decimal("50"),
                proceeds_per_unit=Decimal("100"),
            )

    def test_disposal_with_selling_costs(self):
        """Test disposal with incidental (selling) costs."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("95.50"),
        )
        event = calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2023, 6, 20),
            quantity=Decimal("50"),
            proceeds_per_unit=Decimal("110"),
            incidental_costs=Decimal("19.95"),
        )
        # Net proceeds: 50 * 110 - 19.95 = 5480.05
        # Cost: 50 * 95.50 = 4775
        # Gain: 5480.05 - 4775 = 705.05
        assert event.gross_gain == Decimal("705.05")


# ==============================================================================
# AustralianCGTCalculator - Tax Year Summary Tests
# ==============================================================================


class TestTaxYearSummary:
    """Tests for tax year summary calculations."""

    def test_simple_summary_with_gains(self):
        """Test summary with only gains."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2022, 7, 1),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2023, 10, 15),  # FY2024, >12 months
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("110"),
        )
        summary = calculator.calculate_tax_year_summary(2024)
        # Gross gain: 100 * (110 - 90) = 2000
        assert summary.total_gains == Decimal("2000.00")
        assert summary.total_losses == Decimal("0.00")
        assert summary.discounted_gains == Decimal("2000.00")
        # Discount: 2000 * 0.50 = 1000
        assert summary.discount_applied == Decimal("1000.00")
        assert summary.taxable_gain == Decimal("1000.00")

    def test_summary_with_losses_applied(self):
        """Test summary with losses applied to gains."""
        calculator = AustralianCGTCalculator()
        # Gain asset
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2022, 7, 1),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        # Loss asset
        calculator.add_acquisition(
            symbol="NAB.AX",
            acquisition_date=date(2022, 7, 1),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("35"),
        )
        # Dispose with gain
        calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2023, 10, 15),
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("110"),
        )
        # Dispose with loss
        calculator.dispose(
            symbol="NAB.AX",
            disposal_date=date(2023, 11, 15),
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("25"),
        )
        summary = calculator.calculate_tax_year_summary(2024)
        assert summary.total_gains == Decimal("2000.00")
        assert summary.total_losses == Decimal("1000.00")
        assert summary.losses_applied == Decimal("1000.00")

    def test_summary_with_carried_forward_losses(self):
        """Test summary with carried forward losses."""
        calculator = AustralianCGTCalculator()
        calculator.set_carried_forward_losses(Decimal("500"))
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2022, 7, 1),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2023, 10, 15),
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("110"),
        )
        summary = calculator.calculate_tax_year_summary(2024)
        assert summary.carried_forward_losses == Decimal("500.00")
        # Gross gain 2000 - 500 carried loss = 1500
        # Then 50% discount = 750 taxable
        assert summary.taxable_gain == Decimal("750.00")

    def test_summary_excess_losses_carry_forward(self):
        """Test excess losses are carried forward."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2022, 7, 1),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        calculator.add_acquisition(
            symbol="NAB.AX",
            acquisition_date=date(2022, 7, 1),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("50"),
        )
        # Small gain
        calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2023, 10, 15),
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("95"),
        )
        # Large loss
        calculator.dispose(
            symbol="NAB.AX",
            disposal_date=date(2023, 11, 15),
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("20"),
        )
        summary = calculator.calculate_tax_year_summary(2024)
        assert summary.total_gains == Decimal("500.00")  # 100 * (95-90)
        assert summary.total_losses == Decimal("3000.00")  # 100 * (50-20)
        assert summary.taxable_gain == Decimal("0.00")
        assert summary.losses_to_carry == Decimal("2500.00")  # 3000 - 500

    def test_summary_no_events(self):
        """Test summary with no events for tax year."""
        calculator = AustralianCGTCalculator()
        summary = calculator.calculate_tax_year_summary(2024)
        assert summary.num_events == 0
        assert summary.total_gains == Decimal("0.00")
        assert summary.total_losses == Decimal("0.00")
        assert summary.taxable_gain == Decimal("0.00")


# ==============================================================================
# AustralianCGTCalculator - Tax Report Tests
# ==============================================================================


class TestTaxReport:
    """Tests for tax report generation."""

    def test_generate_basic_report(self):
        """Test generating a basic tax report."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2022, 7, 1),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2023, 10, 15),
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("110"),
        )
        report = calculator.generate_tax_report(2024)
        assert report["tax_year"] == "FY2023-24"
        assert report["period"]["start"] == "2023-07-01"
        assert report["period"]["end"] == "2024-06-30"
        assert "summary" in report
        assert "statistics" in report
        assert "transactions" in report

    def test_report_summary_values(self):
        """Test report summary values."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2022, 7, 1),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2023, 10, 15),
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("110"),
        )
        report = calculator.generate_tax_report(2024)
        summary = report["summary"]
        assert summary["total_capital_gains"] == "2000.00"
        assert summary["total_capital_losses"] == "0.00"
        assert summary["discount_method_gains"] == "2000.00"
        assert summary["cgt_discount_applied"] == "1000.00"
        assert summary["taxable_capital_gain"] == "1000.00"

    def test_report_without_details(self):
        """Test report without transaction details."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2022, 7, 1),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2023, 10, 15),
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("110"),
        )
        report = calculator.generate_tax_report(2024, include_details=False)
        assert "transactions" not in report

    def test_report_statistics(self):
        """Test report statistics."""
        calculator = AustralianCGTCalculator()
        # Two gains, one loss
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2022, 7, 1),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        calculator.add_acquisition(
            symbol="BHP.AX",
            acquisition_date=date(2022, 7, 1),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("40"),
        )
        calculator.add_acquisition(
            symbol="NAB.AX",
            acquisition_date=date(2022, 7, 1),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("35"),
        )
        calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2023, 10, 15),
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("110"),
        )
        calculator.dispose(
            symbol="BHP.AX",
            disposal_date=date(2023, 10, 15),
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("50"),
        )
        calculator.dispose(
            symbol="NAB.AX",
            disposal_date=date(2023, 10, 15),
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("25"),
        )
        report = calculator.generate_tax_report(2024)
        stats = report["statistics"]
        assert stats["number_of_disposals"] == 3
        assert stats["number_of_gains"] == 2
        assert stats["number_of_losses"] == 1


# ==============================================================================
# AustralianCGTCalculator - Unrealised Gains Tests
# ==============================================================================


class TestUnrealisedGains:
    """Tests for unrealised gains calculation."""

    def test_unrealised_gains_calculation(self):
        """Test calculating unrealised gains."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        result = calculator.get_unrealised_gains({"CBA.AX": Decimal("110")})
        assert result["CBA.AX"]["quantity"] == Decimal("100")
        assert result["CBA.AX"]["cost_base"] == Decimal("9000.00")
        assert result["CBA.AX"]["market_value"] == Decimal("11000.00")
        assert result["CBA.AX"]["unrealised_gain"] == Decimal("2000.00")

    def test_unrealised_loss_calculation(self):
        """Test calculating unrealised losses."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        result = calculator.get_unrealised_gains({"CBA.AX": Decimal("80")})
        assert result["CBA.AX"]["unrealised_gain"] == Decimal("-1000.00")

    def test_unrealised_gains_missing_price(self):
        """Test unrealised gains with missing price."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        result = calculator.get_unrealised_gains({})
        assert result["CBA.AX"]["market_value"] == Decimal("0.00")
        assert result["CBA.AX"]["unrealised_gain"] == Decimal("0.00")

    def test_unrealised_gains_multiple_parcels(self):
        """Test unrealised gains with multiple acquisition parcels."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 6, 15),
            quantity=Decimal("50"),
            cost_per_unit=Decimal("100"),
        )
        result = calculator.get_unrealised_gains({"CBA.AX": Decimal("110")})
        assert result["CBA.AX"]["quantity"] == Decimal("150")
        # Cost: 100 * 90 + 50 * 100 = 14000
        assert result["CBA.AX"]["cost_base"] == Decimal("14000.00")
        # Value: 150 * 110 = 16500
        assert result["CBA.AX"]["market_value"] == Decimal("16500.00")
        assert result["CBA.AX"]["unrealised_gain"] == Decimal("2500.00")


# ==============================================================================
# AustralianCGTCalculator - Edge Cases Tests
# ==============================================================================


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_exactly_365_days_no_discount(self):
        """Test holding exactly 365 days (not eligible for discount)."""
        calculator = AustralianCGTCalculator()
        acq_date = date(2023, 1, 15)
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=acq_date,
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        # Exactly 365 days later
        disposal_date = acq_date + timedelta(days=365)
        event = calculator.dispose(
            symbol="CBA.AX",
            disposal_date=disposal_date,
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("110"),
        )
        # Must be MORE than 365 days for discount
        assert event.discount_eligible is False

    def test_366_days_eligible_for_discount(self):
        """Test holding 366 days (eligible for discount)."""
        calculator = AustralianCGTCalculator()
        acq_date = date(2023, 1, 15)
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=acq_date,
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        disposal_date = acq_date + timedelta(days=366)
        event = calculator.dispose(
            symbol="CBA.AX",
            disposal_date=disposal_date,
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("110"),
        )
        assert event.discount_eligible is True

    def test_zero_cost_acquisition(self):
        """Test acquisition with zero cost (e.g., inheritance)."""
        calculator = AustralianCGTCalculator()
        acq = calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("0"),
        )
        assert acq.total_cost_aud == Decimal("0")
        event = calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2024, 3, 20),
            quantity=Decimal("100"),
            proceeds_per_unit=Decimal("100"),
        )
        # All proceeds are gain
        assert event.gross_gain == Decimal("10000.00")

    def test_very_small_quantities(self):
        """Test with very small quantities (fractional shares)."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="BRK.A",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("0.001"),
            cost_per_unit=Decimal("500000"),
        )
        event = calculator.dispose(
            symbol="BRK.A",
            disposal_date=date(2023, 6, 20),
            quantity=Decimal("0.001"),
            proceeds_per_unit=Decimal("510000"),
        )
        assert event.gross_gain == Decimal("10.00")

    def test_clear_calculator(self):
        """Test clearing all calculator data."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2023, 1, 15),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        calculator.set_carried_forward_losses(Decimal("1000"))
        calculator.clear()
        assert calculator.get_holding_quantity("CBA.AX") == Decimal("0")
        assert calculator.get_carried_forward_losses() == Decimal("0")
        assert len(calculator.get_events()) == 0

    def test_set_and_get_asset_type(self):
        """Test setting and getting asset type."""
        calculator = AustralianCGTCalculator()
        calculator.set_asset_type("BTC", AssetType.CRYPTOCURRENCY)
        assert calculator.get_asset_type("BTC") == AssetType.CRYPTOCURRENCY
        # Default type for unknown asset
        assert calculator.get_asset_type("UNKNOWN") == AssetType.SHARES

    def test_invalid_carried_forward_losses(self):
        """Test setting invalid carried forward losses."""
        calculator = AustralianCGTCalculator()
        with pytest.raises(ValueError, match="non-negative"):
            calculator.set_carried_forward_losses(Decimal("-100"))

    def test_get_events_all(self):
        """Test getting all events."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2022, 7, 1),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2023, 10, 15),
            quantity=Decimal("50"),
            proceeds_per_unit=Decimal("110"),
        )
        calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2024, 10, 15),
            quantity=Decimal("50"),
            proceeds_per_unit=Decimal("120"),
        )
        all_events = calculator.get_events()
        assert len(all_events) == 2

    def test_get_events_filtered_by_year(self):
        """Test getting events filtered by tax year."""
        calculator = AustralianCGTCalculator()
        calculator.add_acquisition(
            symbol="CBA.AX",
            acquisition_date=date(2022, 7, 1),
            quantity=Decimal("100"),
            cost_per_unit=Decimal("90"),
        )
        calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2023, 10, 15),  # FY2024
            quantity=Decimal("50"),
            proceeds_per_unit=Decimal("110"),
        )
        calculator.dispose(
            symbol="CBA.AX",
            disposal_date=date(2024, 10, 15),  # FY2025
            quantity=Decimal("50"),
            proceeds_per_unit=Decimal("120"),
        )
        fy2024_events = calculator.get_events(tax_year=2024)
        assert len(fy2024_events) == 1
        fy2025_events = calculator.get_events(tax_year=2025)
        assert len(fy2025_events) == 1


# ==============================================================================
# Module Import Tests
# ==============================================================================


class TestModuleImports:
    """Tests for module imports."""

    def test_import_from_portfolio_module(self):
        """Test importing from portfolio module."""
        from tradingagents.portfolio import (
            CGTMethod,
            AssetType,
            CGTAssetAcquisition,
            CGTDisposal,
            CGTEvent,
            TaxYearSummary,
            AustralianCGTCalculator,
        )
        assert CGTMethod is not None
        assert AssetType is not None
        assert CGTAssetAcquisition is not None
        assert CGTDisposal is not None
        assert CGTEvent is not None
        assert TaxYearSummary is not None
        assert AustralianCGTCalculator is not None

    def test_calculator_constants(self):
        """Test calculator constants."""
        assert AustralianCGTCalculator.DISCOUNT_RATE == Decimal("0.50")
        assert AustralianCGTCalculator.DISCOUNT_HOLDING_DAYS == 365
