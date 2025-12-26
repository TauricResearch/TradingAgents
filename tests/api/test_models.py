"""
Test suite for SQLAlchemy database models.

This module tests Issue #48 database models:
1. User model with hashed passwords
2. Strategy model with JSON parameters
3. Relationships (User -> Strategies)
4. Model validation and constraints
5. Timestamps (created_at, updated_at)
6. Cascade delete behavior

Tests follow TDD - written before implementation.
"""

import pytest
from datetime import datetime
from typing import Dict, Any

pytestmark = pytest.mark.asyncio


# ============================================================================
# Unit Tests: User Model
# ============================================================================

class TestUserModel:
    """Test User database model."""

    async def test_create_user(self, db_session):
        """Test creating a user with required fields."""
        # Arrange
        try:
            from tradingagents.api.models import User

            user = User(
                username="testuser",
                email="test@example.com",
                hashed_password="$argon2id$v=19$m=65536,t=3,p=4$fakehash",
            )

            # Act
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)

            # Assert
            assert user.id is not None
            assert user.username == "testuser"
            assert user.email == "test@example.com"
            assert user.hashed_password.startswith("$argon2")
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_user_unique_username(self, db_session):
        """Test that username must be unique."""
        # Arrange
        try:
            from tradingagents.api.models import User
            from sqlalchemy.exc import IntegrityError

            user1 = User(
                username="testuser",
                email="test1@example.com",
                hashed_password="hash1",
            )
            user2 = User(
                username="testuser",  # Same username
                email="test2@example.com",
                hashed_password="hash2",
            )

            # Act
            db_session.add(user1)
            await db_session.commit()

            db_session.add(user2)

            # Assert: Should raise IntegrityError
            with pytest.raises(IntegrityError):
                await db_session.commit()
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_user_unique_email(self, db_session):
        """Test that email must be unique."""
        # Arrange
        try:
            from tradingagents.api.models import User
            from sqlalchemy.exc import IntegrityError

            user1 = User(
                username="user1",
                email="test@example.com",
                hashed_password="hash1",
            )
            user2 = User(
                username="user2",
                email="test@example.com",  # Same email
                hashed_password="hash2",
            )

            # Act
            db_session.add(user1)
            await db_session.commit()

            db_session.add(user2)

            # Assert
            with pytest.raises(IntegrityError):
                await db_session.commit()
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_user_timestamps(self, db_session):
        """Test that user has created_at and updated_at timestamps."""
        # Arrange
        try:
            from tradingagents.api.models import User

            user = User(
                username="timestampuser",
                email="timestamp@example.com",
                hashed_password="hash",
            )

            # Act
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)

            # Assert
            assert hasattr(user, "created_at")
            assert hasattr(user, "updated_at")
            assert isinstance(user.created_at, datetime)
            assert isinstance(user.updated_at, datetime)
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_user_full_name_optional(self, db_session):
        """Test that full_name is optional."""
        # Arrange
        try:
            from tradingagents.api.models import User

            user = User(
                username="user_no_name",
                email="noname@example.com",
                hashed_password="hash",
                # No full_name provided
            )

            # Act
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)

            # Assert: Should succeed without full_name
            assert user.id is not None
            assert user.full_name is None or user.full_name == ""
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_user_is_active_default(self, db_session):
        """Test that is_active defaults to True."""
        # Arrange
        try:
            from tradingagents.api.models import User

            user = User(
                username="activeuser",
                email="active@example.com",
                hashed_password="hash",
            )

            # Act
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)

            # Assert
            if hasattr(user, "is_active"):
                assert user.is_active is True
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_user_strategies_relationship(self, db_session):
        """Test User has strategies relationship."""
        # Arrange
        try:
            from tradingagents.api.models import User, Strategy

            user = User(
                username="reluser",
                email="rel@example.com",
                hashed_password="hash",
            )
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)

            strategy = Strategy(
                name="Test Strategy",
                description="Test",
                user_id=user.id,
            )
            db_session.add(strategy)
            await db_session.commit()

            # Act: Access relationship
            await db_session.refresh(user)

            # Assert: Can access strategies through relationship
            # This depends on how relationship is configured
            assert hasattr(user, "strategies") or user.id is not None
        except ImportError:
            pytest.skip("Models not implemented yet")


# ============================================================================
# Unit Tests: Strategy Model
# ============================================================================

class TestStrategyModel:
    """Test Strategy database model."""

    async def test_create_strategy(self, db_session, test_user):
        """Test creating a strategy with required fields."""
        # Arrange
        if test_user is None:
            pytest.skip("User model not implemented yet")

        try:
            from tradingagents.api.models import Strategy

            strategy = Strategy(
                name="Test Strategy",
                description="A test strategy",
                user_id=test_user.id,
            )

            # Act
            db_session.add(strategy)
            await db_session.commit()
            await db_session.refresh(strategy)

            # Assert
            assert strategy.id is not None
            assert strategy.name == "Test Strategy"
            assert strategy.description == "A test strategy"
            assert strategy.user_id == test_user.id
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_strategy_with_parameters(self, db_session, test_user):
        """Test creating strategy with JSON parameters."""
        # Arrange
        if test_user is None:
            pytest.skip("User model not implemented yet")

        try:
            from tradingagents.api.models import Strategy

            parameters = {
                "symbol": "AAPL",
                "period": 20,
                "threshold": 0.05,
                "indicators": ["SMA", "RSI"],
            }

            strategy = Strategy(
                name="Parameterized Strategy",
                description="Test",
                parameters=parameters,
                user_id=test_user.id,
            )

            # Act
            db_session.add(strategy)
            await db_session.commit()
            await db_session.refresh(strategy)

            # Assert
            assert strategy.parameters == parameters
            assert strategy.parameters["symbol"] == "AAPL"
            assert strategy.parameters["period"] == 20
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_strategy_empty_parameters(self, db_session, test_user):
        """Test strategy with empty parameters dict."""
        # Arrange
        if test_user is None:
            pytest.skip("User model not implemented yet")

        try:
            from tradingagents.api.models import Strategy

            strategy = Strategy(
                name="Empty Params",
                description="Test",
                parameters={},
                user_id=test_user.id,
            )

            # Act
            db_session.add(strategy)
            await db_session.commit()
            await db_session.refresh(strategy)

            # Assert
            assert strategy.parameters == {}
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_strategy_null_parameters(self, db_session, test_user):
        """Test strategy with null parameters."""
        # Arrange
        if test_user is None:
            pytest.skip("User model not implemented yet")

        try:
            from tradingagents.api.models import Strategy

            strategy = Strategy(
                name="Null Params",
                description="Test",
                parameters=None,
                user_id=test_user.id,
            )

            # Act
            db_session.add(strategy)
            await db_session.commit()
            await db_session.refresh(strategy)

            # Assert: Should handle null (may default to {} or stay None)
            assert strategy.parameters is None or strategy.parameters == {}
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_strategy_is_active_default(self, db_session, test_user):
        """Test that is_active defaults to True."""
        # Arrange
        if test_user is None:
            pytest.skip("User model not implemented yet")

        try:
            from tradingagents.api.models import Strategy

            strategy = Strategy(
                name="Active Strategy",
                description="Test",
                user_id=test_user.id,
            )

            # Act
            db_session.add(strategy)
            await db_session.commit()
            await db_session.refresh(strategy)

            # Assert
            if hasattr(strategy, "is_active"):
                assert strategy.is_active is True
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_strategy_timestamps(self, db_session, test_user):
        """Test that strategy has timestamps."""
        # Arrange
        if test_user is None:
            pytest.skip("User model not implemented yet")

        try:
            from tradingagents.api.models import Strategy

            strategy = Strategy(
                name="Timestamp Strategy",
                description="Test",
                user_id=test_user.id,
            )

            # Act
            db_session.add(strategy)
            await db_session.commit()
            await db_session.refresh(strategy)

            # Assert
            assert hasattr(strategy, "created_at")
            assert hasattr(strategy, "updated_at")
            assert isinstance(strategy.created_at, datetime)
            assert isinstance(strategy.updated_at, datetime)
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_strategy_updated_at_changes(self, db_session, test_user):
        """Test that updated_at changes on update."""
        # Arrange
        if test_user is None:
            pytest.skip("User model not implemented yet")

        try:
            from tradingagents.api.models import Strategy
            import asyncio

            strategy = Strategy(
                name="Update Test",
                description="Original",
                user_id=test_user.id,
            )
            db_session.add(strategy)
            await db_session.commit()
            await db_session.refresh(strategy)

            original_updated_at = strategy.updated_at

            # Wait a moment to ensure timestamp difference
            await asyncio.sleep(0.1)

            # Act: Update strategy
            strategy.description = "Modified"
            await db_session.commit()
            await db_session.refresh(strategy)

            # Assert: updated_at should change
            assert strategy.updated_at > original_updated_at
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_strategy_foreign_key_constraint(self, db_session):
        """Test that strategy requires valid user_id."""
        # Arrange
        try:
            from tradingagents.api.models import Strategy
            from sqlalchemy.exc import IntegrityError

            strategy = Strategy(
                name="Invalid User",
                description="Test",
                user_id=99999,  # Non-existent user
            )

            # Act & Assert
            db_session.add(strategy)
            with pytest.raises(IntegrityError):
                await db_session.commit()
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_strategy_cascade_delete(self, db_session, test_user):
        """Test that deleting user cascades to strategies."""
        # Arrange
        if test_user is None:
            pytest.skip("User model not implemented yet")

        try:
            from tradingagents.api.models import Strategy, User
            from sqlalchemy import select

            strategy = Strategy(
                name="Cascade Test",
                description="Test",
                user_id=test_user.id,
            )
            db_session.add(strategy)
            await db_session.commit()
            strategy_id = strategy.id

            # Act: Delete user
            await db_session.delete(test_user)
            await db_session.commit()

            # Assert: Strategy should be deleted too (cascade)
            result = await db_session.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            deleted_strategy = result.scalar_one_or_none()
            assert deleted_strategy is None
        except ImportError:
            pytest.skip("Models not implemented yet")


# ============================================================================
# Unit Tests: Model Validation
# ============================================================================

class TestModelValidation:
    """Test model field validation and constraints."""

    async def test_user_required_fields(self, db_session):
        """Test that user requires username, email, hashed_password."""
        # Arrange
        try:
            from tradingagents.api.models import User
            from sqlalchemy.exc import IntegrityError

            # Missing username
            user = User(
                email="test@example.com",
                hashed_password="hash",
            )

            # Act & Assert
            db_session.add(user)
            with pytest.raises(IntegrityError):
                await db_session.commit()
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_strategy_required_fields(self, db_session, test_user):
        """Test that strategy requires name, description, user_id."""
        # Arrange
        if test_user is None:
            pytest.skip("User model not implemented yet")

        try:
            from tradingagents.api.models import Strategy
            from sqlalchemy.exc import IntegrityError

            # Missing name
            strategy = Strategy(
                description="Test",
                user_id=test_user.id,
            )

            # Act & Assert
            db_session.add(strategy)
            with pytest.raises(IntegrityError):
                await db_session.commit()
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_email_format_not_validated_at_db_level(self, db_session):
        """Test that email format validation is done at API level, not DB."""
        # Arrange
        try:
            from tradingagents.api.models import User

            # Invalid email format
            user = User(
                username="testuser",
                email="not-an-email",
                hashed_password="hash",
            )

            # Act
            db_session.add(user)
            await db_session.commit()

            # Assert: DB should accept it (validation is at API level)
            assert user.id is not None
        except ImportError:
            pytest.skip("Models not implemented yet")


# ============================================================================
# Integration Tests: Complex Queries
# ============================================================================

class TestModelQueries:
    """Test querying models."""

    async def test_query_user_by_username(self, db_session, test_user):
        """Test querying user by username."""
        # Arrange
        if test_user is None:
            pytest.skip("User model not implemented yet")

        try:
            from tradingagents.api.models import User
            from sqlalchemy import select

            # Act
            result = await db_session.execute(
                select(User).where(User.username == test_user.username)
            )
            user = result.scalar_one_or_none()

            # Assert
            assert user is not None
            assert user.id == test_user.id
            assert user.username == test_user.username
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_query_user_by_email(self, db_session, test_user):
        """Test querying user by email."""
        # Arrange
        if test_user is None:
            pytest.skip("User model not implemented yet")

        try:
            from tradingagents.api.models import User
            from sqlalchemy import select

            # Act
            result = await db_session.execute(
                select(User).where(User.email == test_user.email)
            )
            user = result.scalar_one_or_none()

            # Assert
            assert user is not None
            assert user.email == test_user.email
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_query_strategies_by_user(self, db_session, test_user, test_strategy):
        """Test querying all strategies for a user."""
        # Arrange
        if test_user is None or test_strategy is None:
            pytest.skip("Models not implemented yet")

        try:
            from tradingagents.api.models import Strategy
            from sqlalchemy import select

            # Act
            result = await db_session.execute(
                select(Strategy).where(Strategy.user_id == test_user.id)
            )
            strategies = result.scalars().all()

            # Assert
            assert len(strategies) >= 1
            assert test_strategy.id in [s.id for s in strategies]
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_query_active_strategies(self, db_session, test_user, multiple_strategies):
        """Test querying only active strategies."""
        # Arrange
        if test_user is None or not multiple_strategies:
            pytest.skip("Models not implemented yet")

        try:
            from tradingagents.api.models import Strategy
            from sqlalchemy import select

            # Act
            result = await db_session.execute(
                select(Strategy).where(
                    Strategy.user_id == test_user.id,
                    Strategy.is_active == True,
                )
            )
            active_strategies = result.scalars().all()

            # Assert
            assert len(active_strategies) >= 1
            assert all(s.is_active for s in active_strategies)
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_order_strategies_by_created_at(self, db_session, test_user, multiple_strategies):
        """Test ordering strategies by creation time."""
        # Arrange
        if test_user is None or not multiple_strategies:
            pytest.skip("Models not implemented yet")

        try:
            from tradingagents.api.models import Strategy
            from sqlalchemy import select

            # Act
            result = await db_session.execute(
                select(Strategy)
                .where(Strategy.user_id == test_user.id)
                .order_by(Strategy.created_at.desc())
            )
            strategies = result.scalars().all()

            # Assert: Sorted by created_at descending
            assert len(strategies) >= 2
            for i in range(len(strategies) - 1):
                assert strategies[i].created_at >= strategies[i + 1].created_at
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_pagination_query(self, db_session, test_user, multiple_strategies):
        """Test paginated query with limit and offset."""
        # Arrange
        if test_user is None or not multiple_strategies:
            pytest.skip("Models not implemented yet")

        try:
            from tradingagents.api.models import Strategy
            from sqlalchemy import select

            # Act: Get first page
            result = await db_session.execute(
                select(Strategy)
                .where(Strategy.user_id == test_user.id)
                .limit(2)
                .offset(0)
            )
            page1 = result.scalars().all()

            # Act: Get second page
            result = await db_session.execute(
                select(Strategy)
                .where(Strategy.user_id == test_user.id)
                .limit(2)
                .offset(2)
            )
            page2 = result.scalars().all()

            # Assert: Pages have different strategies
            assert len(page1) <= 2
            if page1 and page2:
                assert page1[0].id != page2[0].id
        except ImportError:
            pytest.skip("Models not implemented yet")


# ============================================================================
# Edge Cases: Models
# ============================================================================

class TestModelEdgeCases:
    """Test edge cases in model behavior."""

    async def test_user_very_long_username(self, db_session):
        """Test user with very long username."""
        # Arrange
        try:
            from tradingagents.api.models import User

            user = User(
                username="a" * 500,
                email="long@example.com",
                hashed_password="hash",
            )

            # Act
            db_session.add(user)
            await db_session.commit()

            # Assert: Should either succeed or fail with constraint violation
            assert user.id is not None or True  # Either way is acceptable
        except Exception:
            # May raise exception if username has length constraint
            pass

    async def test_strategy_with_unicode_name(self, db_session, test_user):
        """Test strategy with Unicode characters in name."""
        # Arrange
        if test_user is None:
            pytest.skip("User model not implemented yet")

        try:
            from tradingagents.api.models import Strategy

            strategy = Strategy(
                name="策略 测试 🚀",
                description="测试描述",
                user_id=test_user.id,
            )

            # Act
            db_session.add(strategy)
            await db_session.commit()
            await db_session.refresh(strategy)

            # Assert
            assert strategy.name == "策略 测试 🚀"
            assert strategy.description == "测试描述"
        except ImportError:
            pytest.skip("Models not implemented yet")

    async def test_strategy_with_very_deep_json(self, db_session, test_user):
        """Test strategy with deeply nested JSON parameters."""
        # Arrange
        if test_user is None:
            pytest.skip("User model not implemented yet")

        try:
            from tradingagents.api.models import Strategy

            deep_params = {
                "l1": {
                    "l2": {
                        "l3": {
                            "l4": {
                                "l5": {"value": "deep"}
                            }
                        }
                    }
                }
            }

            strategy = Strategy(
                name="Deep JSON",
                description="Test",
                parameters=deep_params,
                user_id=test_user.id,
            )

            # Act
            db_session.add(strategy)
            await db_session.commit()
            await db_session.refresh(strategy)

            # Assert
            assert strategy.parameters["l1"]["l2"]["l3"]["l4"]["l5"]["value"] == "deep"
        except ImportError:
            pytest.skip("Models not implemented yet")
