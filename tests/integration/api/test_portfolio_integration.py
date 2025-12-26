"""Integration tests for Portfolio model (Issue #4: DB-3).

Tests for Portfolio model integration with:
- User model relationships
- Database constraints and transactions
- Complex query scenarios
- Concurrent operations
- Portfolio lifecycle management

Follows TDD principles - tests written BEFORE implementation.
"""

import pytest
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

# Mark all tests in this module as asyncio
pytestmark = pytest.mark.asyncio


class TestPortfolioUserIntegration:
    """Integration tests for Portfolio-User relationships."""

    @pytest.mark.asyncio
    async def test_create_portfolio_for_user(self, db_session, test_user):
        """Should create portfolio linked to user."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Integration Test Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("25000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)
            await db_session.refresh(test_user, ["portfolios"])

            # Verify both sides of relationship
            assert portfolio.user_id == test_user.id
            assert portfolio in test_user.portfolios

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_user_with_multiple_portfolio_types(self, db_session, test_user):
        """Should allow user to have different portfolio types."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            live = Portfolio(
                user_id=test_user.id,
                name="Live Trading",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=Decimal("100000.0000"),
                currency="USD",
            )

            paper = Portfolio(
                user_id=test_user.id,
                name="Paper Trading",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
                currency="USD",
            )

            backtest = Portfolio(
                user_id=test_user.id,
                name="Historical Backtest",
                portfolio_type=PortfolioType.BACKTEST,
                initial_capital=Decimal("50000.0000"),
                currency="USD",
            )

            db_session.add_all([live, paper, backtest])
            await db_session.commit()

            # Refresh and verify
            await db_session.refresh(test_user, ["portfolios"])

            assert len(test_user.portfolios) == 3

            types = {p.portfolio_type for p in test_user.portfolios}
            assert PortfolioType.LIVE in types
            assert PortfolioType.PAPER in types
            assert PortfolioType.BACKTEST in types

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_portfolios_deleted_with_user(self, db_session, db_engine):
        """Should cascade delete portfolios when user is deleted."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType
            from tradingagents.api.models.user import User
            from tradingagents.api.services.auth_service import hash_password

            # Create a temporary user
            temp_user = User(
                username="tempuser",
                email="temp@example.com",
                hashed_password=hash_password("TempPass123!"),
            )

            db_session.add(temp_user)
            await db_session.commit()
            await db_session.refresh(temp_user)

            # Create portfolios for temp user
            portfolio1 = Portfolio(
                user_id=temp_user.id,
                name="Portfolio 1",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            portfolio2 = Portfolio(
                user_id=temp_user.id,
                name="Portfolio 2",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=Decimal("50000.0000"),
            )

            db_session.add_all([portfolio1, portfolio2])
            await db_session.commit()

            portfolio1_id = portfolio1.id
            portfolio2_id = portfolio2.id

            # Delete the user
            await db_session.delete(temp_user)
            await db_session.commit()

            # Verify portfolios are deleted
            result = await db_session.execute(
                select(Portfolio).where(
                    Portfolio.id.in_([portfolio1_id, portfolio2_id])
                )
            )
            remaining = result.scalars().all()

            assert len(remaining) == 0

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_multiple_users_same_portfolio_name(self, db_session, test_user, another_user):
        """Should allow different users to have portfolios with same name."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            common_name = "Main Portfolio"

            portfolio1 = Portfolio(
                user_id=test_user.id,
                name=common_name,
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            portfolio2 = Portfolio(
                user_id=another_user.id,
                name=common_name,
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("15000.0000"),
            )

            db_session.add_all([portfolio1, portfolio2])
            await db_session.commit()

            # Query to verify both exist
            result = await db_session.execute(
                select(Portfolio).where(Portfolio.name == common_name)
            )
            portfolios = result.scalars().all()

            assert len(portfolios) == 2
            user_ids = {p.user_id for p in portfolios}
            assert test_user.id in user_ids
            assert another_user.id in user_ids

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")


class TestPortfolioTransactions:
    """Integration tests for portfolio transaction scenarios."""

    @pytest.mark.asyncio
    async def test_update_portfolio_value(self, db_session, test_user):
        """Should update current_value while preserving initial_capital."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Value Update Test",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            # Update current value
            original_capital = portfolio.initial_capital
            portfolio.current_value = Decimal("12500.7500")
            await db_session.commit()
            await db_session.refresh(portfolio)

            # Verify
            assert portfolio.initial_capital == original_capital
            assert portfolio.current_value == Decimal("12500.7500")

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_deactivate_portfolio(self, db_session, test_user):
        """Should deactivate portfolio without deleting it."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Deactivation Test",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=Decimal("50000.0000"),
                is_active=True,
            )

            db_session.add(portfolio)
            await db_session.commit()
            portfolio_id = portfolio.id

            # Deactivate
            portfolio.is_active = False
            await db_session.commit()

            # Verify still exists but inactive
            result = await db_session.execute(
                select(Portfolio).where(Portfolio.id == portfolio_id)
            )
            found = result.scalar_one()

            assert found is not None
            assert found.is_active is False

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_rollback_on_constraint_violation(self, db_session, test_user):
        """Should rollback transaction on unique constraint violation."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            # Capture user_id BEFORE any operations to avoid lazy load after rollback
            user_id = test_user.id

            # Create first portfolio
            portfolio1 = Portfolio(
                user_id=user_id,
                name="Unique Test",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio1)
            await db_session.commit()

            # Try to create duplicate
            portfolio2 = Portfolio(
                user_id=user_id,
                name="Unique Test",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=Decimal("20000.0000"),
            )

            db_session.add(portfolio2)

            with pytest.raises(IntegrityError):
                await db_session.commit()

            # Rollback
            await db_session.rollback()

            # Verify only first portfolio exists (use stored user_id to avoid lazy load)
            result = await db_session.execute(
                select(Portfolio).where(
                    Portfolio.user_id == user_id,
                    Portfolio.name == "Unique Test"
                )
            )
            portfolios = result.scalars().all()

            assert len(portfolios) == 1
            assert portfolios[0].portfolio_type == PortfolioType.PAPER

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")


class TestPortfolioComplexQueries:
    """Integration tests for complex portfolio queries."""

    @pytest.mark.asyncio
    async def test_aggregate_total_capital_by_user(self, db_session, test_user):
        """Should calculate total capital across all user portfolios."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            # Create multiple portfolios
            portfolios_data = [
                ("Portfolio A", Decimal("10000.0000")),
                ("Portfolio B", Decimal("25000.0000")),
                ("Portfolio C", Decimal("15000.5000")),
            ]

            for name, capital in portfolios_data:
                portfolio = Portfolio(
                    user_id=test_user.id,
                    name=name,
                    portfolio_type=PortfolioType.PAPER,
                    initial_capital=capital,
                )
                db_session.add(portfolio)

            await db_session.commit()

            # Aggregate query
            result = await db_session.execute(
                select(func.sum(Portfolio.initial_capital)).where(
                    Portfolio.user_id == test_user.id
                )
            )
            total = result.scalar()

            expected = Decimal("50000.5000")
            assert total == expected

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_count_portfolios_by_type(self, db_session, test_user):
        """Should count portfolios grouped by type."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            # Create portfolios of different types
            types_count = {
                PortfolioType.LIVE: 2,
                PortfolioType.PAPER: 3,
                PortfolioType.BACKTEST: 1,
            }

            for ptype, count in types_count.items():
                for i in range(count):
                    portfolio = Portfolio(
                        user_id=test_user.id,
                        name=f"{ptype.value} Portfolio {i}",
                        portfolio_type=ptype,
                        initial_capital=Decimal("10000.0000"),
                    )
                    db_session.add(portfolio)

            await db_session.commit()

            # Count by type
            for ptype, expected_count in types_count.items():
                result = await db_session.execute(
                    select(func.count()).where(
                        Portfolio.user_id == test_user.id,
                        Portfolio.portfolio_type == ptype
                    )
                )
                count = result.scalar()
                assert count == expected_count

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_filter_portfolios_by_value_range(self, db_session, test_user):
        """Should filter portfolios by current value range."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            # Create portfolios with different values
            portfolios_data = [
                ("Small", Decimal("1000.0000")),
                ("Medium", Decimal("25000.0000")),
                ("Large", Decimal("100000.0000")),
            ]

            for name, capital in portfolios_data:
                portfolio = Portfolio(
                    user_id=test_user.id,
                    name=name,
                    portfolio_type=PortfolioType.PAPER,
                    initial_capital=capital,
                    current_value=capital,
                )
                db_session.add(portfolio)

            await db_session.commit()

            # Query portfolios with value between 10k and 50k
            result = await db_session.execute(
                select(Portfolio).where(
                    Portfolio.user_id == test_user.id,
                    Portfolio.current_value >= Decimal("10000.0000"),
                    Portfolio.current_value <= Decimal("50000.0000")
                )
            )
            filtered = result.scalars().all()

            assert len(filtered) == 1
            assert filtered[0].name == "Medium"

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_order_portfolios_by_value(self, db_session, test_user):
        """Should order portfolios by current value."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            # Create portfolios
            portfolios_data = [
                ("Portfolio A", Decimal("50000.0000")),
                ("Portfolio B", Decimal("10000.0000")),
                ("Portfolio C", Decimal("25000.0000")),
            ]

            for name, capital in portfolios_data:
                portfolio = Portfolio(
                    user_id=test_user.id,
                    name=name,
                    portfolio_type=PortfolioType.PAPER,
                    initial_capital=capital,
                    current_value=capital,
                )
                db_session.add(portfolio)

            await db_session.commit()

            # Query ordered by value descending
            result = await db_session.execute(
                select(Portfolio)
                .where(Portfolio.user_id == test_user.id)
                .order_by(Portfolio.current_value.desc())
            )
            ordered = result.scalars().all()

            assert len(ordered) == 3
            assert ordered[0].name == "Portfolio A"
            assert ordered[1].name == "Portfolio C"
            assert ordered[2].name == "Portfolio B"

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")


class TestPortfolioMultiCurrency:
    """Integration tests for multi-currency portfolio scenarios."""

    @pytest.mark.asyncio
    async def test_portfolios_in_different_currencies(self, db_session, test_user):
        """Should support portfolios in different currencies."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            currencies = ["USD", "EUR", "GBP", "JPY", "AUD"]

            for currency in currencies:
                portfolio = Portfolio(
                    user_id=test_user.id,
                    name=f"{currency} Portfolio",
                    portfolio_type=PortfolioType.PAPER,
                    initial_capital=Decimal("10000.0000"),
                    currency=currency,
                )
                db_session.add(portfolio)

            await db_session.commit()

            # Query portfolios by currency
            for currency in currencies:
                result = await db_session.execute(
                    select(Portfolio).where(
                        Portfolio.user_id == test_user.id,
                        Portfolio.currency == currency
                    )
                )
                found = result.scalar_one()
                assert found.currency == currency

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_group_portfolios_by_currency(self, db_session, test_user):
        """Should group and count portfolios by currency."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            # Create portfolios with different currencies
            currency_data = [
                ("USD", 3),
                ("EUR", 2),
                ("AUD", 1),
            ]

            for currency, count in currency_data:
                for i in range(count):
                    portfolio = Portfolio(
                        user_id=test_user.id,
                        name=f"{currency} Portfolio {i}",
                        portfolio_type=PortfolioType.PAPER,
                        initial_capital=Decimal("10000.0000"),
                        currency=currency,
                    )
                    db_session.add(portfolio)

            await db_session.commit()

            # Count by currency
            for currency, expected_count in currency_data:
                result = await db_session.execute(
                    select(func.count()).where(
                        Portfolio.user_id == test_user.id,
                        Portfolio.currency == currency
                    )
                )
                count = result.scalar()
                assert count == expected_count

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")


class TestPortfolioLifecycle:
    """Integration tests for portfolio lifecycle management."""

    @pytest.mark.asyncio
    async def test_portfolio_creation_to_deletion_lifecycle(self, db_session, test_user):
        """Should support full lifecycle: create, update, deactivate, delete."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            # 1. Create
            portfolio = Portfolio(
                user_id=test_user.id,
                name="Lifecycle Test",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            portfolio_id = portfolio.id
            assert portfolio.is_active is True

            # 2. Update value
            portfolio.current_value = Decimal("12000.0000")
            await db_session.commit()
            await db_session.refresh(portfolio)

            assert portfolio.current_value == Decimal("12000.0000")

            # 3. Deactivate
            portfolio.is_active = False
            await db_session.commit()
            await db_session.refresh(portfolio)

            assert portfolio.is_active is False

            # 4. Delete
            await db_session.delete(portfolio)
            await db_session.commit()

            # Verify deleted
            result = await db_session.execute(
                select(Portfolio).where(Portfolio.id == portfolio_id)
            )
            deleted = result.scalar_one_or_none()

            assert deleted is None

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_reactivate_deactivated_portfolio(self, db_session, test_user):
        """Should allow reactivating a deactivated portfolio."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Reactivation Test",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
                is_active=False,
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            assert portfolio.is_active is False

            # Reactivate
            portfolio.is_active = True
            await db_session.commit()
            await db_session.refresh(portfolio)

            assert portfolio.is_active is True

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_migrate_portfolio_type(self, db_session, test_user):
        """Should allow changing portfolio type (e.g., PAPER to LIVE)."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Migration Test",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            assert portfolio.portfolio_type == PortfolioType.PAPER

            # Migrate to LIVE
            portfolio.portfolio_type = PortfolioType.LIVE
            await db_session.commit()
            await db_session.refresh(portfolio)

            assert portfolio.portfolio_type == PortfolioType.LIVE

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")


class TestPortfolioConcurrency:
    """Integration tests for concurrent portfolio operations."""

    @pytest.mark.asyncio
    async def test_concurrent_value_updates(self, db_session, test_user):
        """Should handle concurrent updates to portfolio value."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            portfolio = Portfolio(
                user_id=test_user.id,
                name="Concurrency Test",
                portfolio_type=PortfolioType.LIVE,
                initial_capital=Decimal("10000.0000"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            # Simulate concurrent updates
            updates = [
                Decimal("10500.0000"),
                Decimal("11000.0000"),
                Decimal("10750.0000"),
            ]

            for new_value in updates:
                portfolio.current_value = new_value
                await db_session.commit()
                await db_session.refresh(portfolio)

            # Final value should be last update
            assert portfolio.current_value == Decimal("10750.0000")

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_bulk_portfolio_creation(self, db_session, test_user):
        """Should handle bulk creation of multiple portfolios."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType

            # Create 10 portfolios in bulk
            portfolios = []
            for i in range(10):
                portfolio = Portfolio(
                    user_id=test_user.id,
                    name=f"Bulk Portfolio {i}",
                    portfolio_type=PortfolioType.PAPER,
                    initial_capital=Decimal(f"{(i + 1) * 1000}.0000"),
                )
                portfolios.append(portfolio)

            db_session.add_all(portfolios)
            await db_session.commit()

            # Verify all created
            result = await db_session.execute(
                select(func.count()).where(Portfolio.user_id == test_user.id)
            )
            count = result.scalar()

            assert count == 10

        except ImportError:
            pytest.skip("Portfolio model not yet implemented (TDD RED phase)")
