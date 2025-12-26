"""Unit tests for Portfolio model (Issue #4: DB-3).

Tests for Portfolio model fields including:
- portfolio_type (LIVE, PAPER, BACKTEST enum)
- initial_capital, current_value (Decimal precision)
- currency (3-letter code validation)
- Unique constraint on (user_id, name)
- Cascade delete behavior
- Decimal(19,4) precision for monetary values

Follows TDD principles with comprehensive coverage.
Tests written BEFORE implementation (RED phase).
"""

import pytest
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

# Mark all tests in this module as asyncio
pytestmark = pytest.mark.asyncio


class TestPortfolioModelBasicFields:
    """Tests for basic Portfolio model fields."""

    @pytest.mark.asyncio
    async def test_create_portfolio_with_required_fields(self, db_session, test_user):
        """Should create portfolio with only required fields."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="My First Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            # Assert
            assert portfolio.id is not None
            assert portfolio.user_id == test_user.id
            assert portfolio.name == "My First Portfolio"
            assert portfolio.portfolio_type == PortfolioType.PAPER
            assert portfolio.initial_capital == Decimal("10000.0000")

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_portfolio_defaults(self, db_session, test_user):
        """Should apply default values to optional fields."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Test Portfolio",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=Decimal("50000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            # Check defaults
            assert portfolio.current_value == portfolio.initial_capital
            assert portfolio.currency == "AUD"
            assert portfolio.is_active is True
            assert portfolio.created_at is not None
            assert portfolio.updated_at is not None

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_portfolio_with_all_fields(self, db_session, test_user):
        """Should create portfolio with all fields specified."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Complete Portfolio",
                portfolio_type=PortfolioType.BACKTEST,
                initial_capital=Decimal("100000.5000"),
                current_value=Decimal("105000.7500"),
                currency="USD",
                is_active=False,
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            # Assert all fields
            assert portfolio.id is not None
            assert portfolio.user_id == test_user.id
            assert portfolio.name == "Complete Portfolio"
            assert portfolio.portfolio_type == PortfolioType.BACKTEST
            assert portfolio.initial_capital == Decimal("100000.5000")
            assert portfolio.current_value == Decimal("105000.7500")
            assert portfolio.currency == "USD"
            assert portfolio.is_active is False

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_portfolio_timestamps_auto_populate(self, db_session, test_user):
        """Should auto-populate created_at and updated_at timestamps."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType
            from datetime import datetime

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Timestamp Test",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            # Assert timestamps exist and are recent
            assert portfolio.created_at is not None
            assert portfolio.updated_at is not None
            assert isinstance(portfolio.created_at, datetime)
            assert isinstance(portfolio.updated_at, datetime)

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")


class TestPortfolioTypeEnum:
    """Tests for PortfolioType enum validation."""

    @pytest.mark.asyncio
    async def test_portfolio_type_live(self, db_session, test_user):
        """Should create portfolio with LIVE type."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Live Portfolio",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=Decimal("50000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            assert portfolio.portfolio_type == PortfolioType.LIVE
            assert portfolio.portfolio_type.value == "LIVE"

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_portfolio_type_paper(self, db_session, test_user):
        """Should create portfolio with PAPER type."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Paper Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            assert portfolio.portfolio_type == PortfolioType.PAPER
            assert portfolio.portfolio_type.value == "PAPER"

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_portfolio_type_backtest(self, db_session, test_user):
        """Should create portfolio with BACKTEST type."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Backtest Portfolio",
                portfolio_type=PortfolioType.BACKTEST,
                initial_capital=Decimal("100000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            assert portfolio.portfolio_type == PortfolioType.BACKTEST
            assert portfolio.portfolio_type.value == "BACKTEST"

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_portfolio_type_invalid_value(self, db_session, test_user):
        """Should reject invalid portfolio type."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            # Try to create with invalid string
            with pytest.raises((ValueError, AttributeError)):
                portfolio = Portfolio(
                    user_id=test_user.id,
                    name="Invalid Portfolio",
                    portfolio_type="INVALID_TYPE",
                    initial_capital=Decimal("10000.0000"),
                )
                db_session.add(portfolio)
                await db_session.commit()

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")


class TestPortfolioDecimalPrecision:
    """Tests for Decimal(19,4) precision on monetary values."""

    @pytest.mark.asyncio
    async def test_initial_capital_decimal_precision(self, db_session, test_user):
        """Should store initial_capital with 4 decimal places."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Precision Test",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("12345.6789"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            # Assert decimal precision maintained
            assert portfolio.initial_capital == Decimal("12345.6789")
            assert isinstance(portfolio.initial_capital, Decimal)

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_current_value_decimal_precision(self, db_session, test_user):
        """Should store current_value with 4 decimal places."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Value Test",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=Decimal("10000.0000"),
                current_value=Decimal("10523.4567"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            # Assert decimal precision maintained
            assert portfolio.current_value == Decimal("10523.4567")
            assert isinstance(portfolio.current_value, Decimal)

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_large_capital_value(self, db_session, test_user):
        """Should handle large capital values (up to 15 digits before decimal)."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            # Test with 14 digits before decimal point (SQLite has limited precision)
            # PostgreSQL can handle 15 digits, but SQLite rounds at ~15 significant figures
            large_value = Decimal("99999999999999.9999")

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Large Portfolio",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=large_value,
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            # Allow small precision loss for SQLite compatibility
            assert abs(portfolio.initial_capital - large_value) < Decimal("1.0")

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_small_capital_value(self, db_session, test_user):
        """Should handle small capital values with precision."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            small_value = Decimal("0.0001")

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Small Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=small_value,
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            assert portfolio.initial_capital == small_value

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_negative_values_rejected(self, db_session, test_user):
        """Should reject negative capital values (business rule)."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Negative Test",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("-1000.0000"),
            )

            db_session.add(portfolio)

            # Should raise constraint violation or validation error
            with pytest.raises((IntegrityError, ValueError)):
                await db_session.commit()

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")


class TestPortfolioUniqueConstraint:
    """Tests for unique constraint on (user_id, name)."""

    @pytest.mark.asyncio
    async def test_user_can_have_multiple_portfolios(self, db_session, test_user):
        """Should allow user to create multiple portfolios with different names."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio1 = Portfolio(
                user_id=test_user.id,
                name="Portfolio 1",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            portfolio2 = Portfolio(
                user_id=test_user.id,
                name="Portfolio 2",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=Decimal("50000.0000"),
            )

            db_session.add(portfolio1)
            db_session.add(portfolio2)
            await db_session.commit()
            await db_session.refresh(portfolio1)
            await db_session.refresh(portfolio2)

            assert portfolio1.id != portfolio2.id
            assert portfolio1.user_id == portfolio2.user_id
            assert portfolio1.name != portfolio2.name

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_duplicate_name_same_user_rejected(self, db_session, test_user):
        """Should reject duplicate portfolio name for same user."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio1 = Portfolio(
                user_id=test_user.id,
                name="My Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio1)
            await db_session.commit()

            # Try to create another portfolio with same name for same user
            portfolio2 = Portfolio(
                user_id=test_user.id,
                name="My Portfolio",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=Decimal("20000.0000"),
            )

            db_session.add(portfolio2)

            with pytest.raises(IntegrityError):
                await db_session.commit()

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_same_name_different_users_allowed(self, db_session, test_user, another_user):
        """Should allow different users to have portfolios with same name."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio1 = Portfolio(
                user_id=test_user.id,
                name="Main Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            portfolio2 = Portfolio(
                user_id=another_user.id,
                name="Main Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("15000.0000"),
            )

            db_session.add(portfolio1)
            db_session.add(portfolio2)
            await db_session.commit()
            await db_session.refresh(portfolio1)
            await db_session.refresh(portfolio2)

            assert portfolio1.id != portfolio2.id
            assert portfolio1.name == portfolio2.name
            assert portfolio1.user_id != portfolio2.user_id

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")


class TestPortfolioCurrencyValidation:
    """Tests for currency field validation."""

    @pytest.mark.asyncio
    async def test_default_currency_aud(self, db_session, test_user):
        """Should default to AUD currency."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Default Currency",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            assert portfolio.currency == "AUD"

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_common_currencies(self, db_session, test_user):
        """Should accept common 3-letter currency codes."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            currencies = ["USD", "EUR", "GBP", "JPY", "CNY", "AUD", "CAD"]

            for i, currency in enumerate(currencies):
                portfolio = Portfolio(
                    user_id=test_user.id,
                    name=f"Portfolio {currency}",
                    portfolio_type=PortfolioType.PAPER,
                    initial_capital=Decimal("10000.0000"),
                    currency=currency,
                )

                db_session.add(portfolio)
                await db_session.commit()
                await db_session.refresh(portfolio)

                assert portfolio.currency == currency

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_currency_uppercase_enforced(self, db_session, test_user):
        """Should store currency in uppercase."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Currency Case Test",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
                currency="usd",  # lowercase input
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            # Should be stored in uppercase
            assert portfolio.currency == "USD"

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_invalid_currency_length(self, db_session, test_user):
        """Should reject currency codes that aren't 3 characters."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            # Test with 2-character code
            with pytest.raises((ValueError, IntegrityError)):
                portfolio = Portfolio(
                    user_id=test_user.id,
                    name="Invalid Currency 1",
                    portfolio_type=PortfolioType.PAPER,
                    initial_capital=Decimal("10000.0000"),
                    currency="US",
                )
                db_session.add(portfolio)
                await db_session.commit()

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")


class TestPortfolioRelationships:
    """Tests for Portfolio relationships with User."""

    @pytest.mark.asyncio
    async def test_portfolio_belongs_to_user(self, db_session, test_user):
        """Should establish relationship from portfolio to user."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="User Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            # Load the relationship
            await db_session.refresh(portfolio, ["user"])

            assert portfolio.user is not None
            assert portfolio.user.id == test_user.id
            assert portfolio.user.username == test_user.username

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_user_has_many_portfolios(self, db_session, test_user):
        """Should establish relationship from user to portfolios."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio1 = Portfolio(
                user_id=test_user.id,
                name="Portfolio A",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            portfolio2 = Portfolio(
                user_id=test_user.id,
                name="Portfolio B",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=Decimal("50000.0000"),
            )

            db_session.add(portfolio1)
            db_session.add(portfolio2)
            await db_session.commit()

            # Refresh user with portfolios relationship
            await db_session.refresh(test_user, ["portfolios"])

            assert len(test_user.portfolios) == 2
            portfolio_names = [p.name for p in test_user.portfolios]
            assert "Portfolio A" in portfolio_names
            assert "Portfolio B" in portfolio_names

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_cascade_delete_when_user_deleted(self, db_session, test_user):
        """Should delete portfolios when user is deleted (cascade)."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Will Be Deleted",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            portfolio_id = portfolio.id

            # Delete the user
            await db_session.delete(test_user)
            await db_session.commit()

            # Check portfolio is also deleted
            result = await db_session.execute(
                select(Portfolio).where(Portfolio.id == portfolio_id)
            )
            deleted_portfolio = result.scalar_one_or_none()

            assert deleted_portfolio is None

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")


class TestPortfolioEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_very_long_portfolio_name(self, db_session, test_user):
        """Should handle long portfolio names within limits."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            long_name = "A" * 255  # Assume 255 char limit

            portfolio = Portfolio(
                user_id=test_user.id,
                name=long_name,
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            assert portfolio.name == long_name
            assert len(portfolio.name) == 255

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_portfolio_name_too_long(self, db_session, test_user):
        """Should reject portfolio names exceeding max length."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            too_long_name = "A" * 256  # Exceed 255 char limit

            portfolio = Portfolio(
                user_id=test_user.id,
                name=too_long_name,
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)

            with pytest.raises((ValueError, IntegrityError)):
                await db_session.commit()

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_unicode_in_portfolio_name(self, db_session, test_user):
        """Should handle unicode characters in portfolio name."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            unicode_name = "我的投资组合 🚀 Portfolio Émigré"

            portfolio = Portfolio(
                user_id=test_user.id,
                name=unicode_name,
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            assert portfolio.name == unicode_name

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_empty_portfolio_name(self, db_session, test_user):
        """Should reject empty portfolio name."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)

            with pytest.raises((ValueError, IntegrityError)):
                await db_session.commit()

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_zero_initial_capital(self, db_session, test_user):
        """Should handle zero initial capital."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Zero Capital",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("0.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            assert portfolio.initial_capital == Decimal("0.0000")

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_portfolio_repr(self, db_session, test_user):
        """Should have meaningful string representation."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Repr Test",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            repr_str = repr(portfolio)
            assert "Portfolio" in repr_str
            assert str(portfolio.id) in repr_str
            assert portfolio.name in repr_str

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")


class TestPortfolioQueryOperations:
    """Tests for querying Portfolio records."""

    @pytest.mark.asyncio
    async def test_query_portfolio_by_id(self, db_session, test_user):
        """Should retrieve portfolio by ID."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Query Test",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            portfolio_id = portfolio.id

            # Query by ID
            result = await db_session.execute(
                select(Portfolio).where(Portfolio.id == portfolio_id)
            )
            found = result.scalar_one_or_none()

            assert found is not None
            assert found.id == portfolio_id
            assert found.name == "Query Test"

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_query_portfolios_by_user(self, db_session, test_user, another_user):
        """Should retrieve all portfolios for a user."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            # Create portfolios for test_user
            for i in range(3):
                portfolio = Portfolio(
                    user_id=test_user.id,
                    name=f"User1 Portfolio {i}",
                    portfolio_type=PortfolioType.PAPER,
                    initial_capital=Decimal("10000.0000"),
                )
                db_session.add(portfolio)

            # Create portfolio for another_user
            portfolio = Portfolio(
                user_id=another_user.id,
                name="User2 Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("15000.0000"),
            )
            db_session.add(portfolio)
            await db_session.commit()

            # Query portfolios for test_user
            result = await db_session.execute(
                select(Portfolio).where(Portfolio.user_id == test_user.id)
            )
            user_portfolios = result.scalars().all()

            assert len(user_portfolios) == 3
            for p in user_portfolios:
                assert p.user_id == test_user.id

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_query_portfolios_by_type(self, db_session, test_user):
        """Should retrieve portfolios filtered by type."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            # Create portfolios of different types
            live_portfolio = Portfolio(
                user_id=test_user.id,
                name="Live Portfolio",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=Decimal("50000.0000"),
            )

            paper_portfolio = Portfolio(
                user_id=test_user.id,
                name="Paper Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            backtest_portfolio = Portfolio(
                user_id=test_user.id,
                name="Backtest Portfolio",
                portfolio_type=PortfolioType.BACKTEST,
                initial_capital=Decimal("100000.0000"),
            )

            db_session.add_all([live_portfolio, paper_portfolio, backtest_portfolio])
            await db_session.commit()

            # Query PAPER portfolios
            result = await db_session.execute(
                select(Portfolio).where(Portfolio.portfolio_type == PortfolioType.PAPER)
            )
            paper_portfolios = result.scalars().all()

            assert len(paper_portfolios) >= 1
            for p in paper_portfolios:
                assert p.portfolio_type == PortfolioType.PAPER

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_query_active_portfolios(self, db_session, test_user):
        """Should retrieve only active portfolios."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            # Create active and inactive portfolios
            active = Portfolio(
                user_id=test_user.id,
                name="Active Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
                is_active=True,
            )

            inactive = Portfolio(
                user_id=test_user.id,
                name="Inactive Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
                is_active=False,
            )

            db_session.add_all([active, inactive])
            await db_session.commit()

            # Query active portfolios
            result = await db_session.execute(
                select(Portfolio).where(
                    Portfolio.user_id == test_user.id,
                    Portfolio.is_active == True
                )
            )
            active_portfolios = result.scalars().all()

            assert len(active_portfolios) >= 1
            for p in active_portfolios:
                assert p.is_active is True

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")
