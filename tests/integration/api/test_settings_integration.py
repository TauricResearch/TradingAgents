"""Integration tests for Settings model (Issue #5: DB-4).

Integration tests covering:
- Settings creation with related User entity
- Querying settings by user
- Updating settings for a user
- Complex alert preferences scenarios
- Multi-user settings isolation
- Settings deletion and cascade behavior

Follows TDD principles with comprehensive coverage.
Tests written BEFORE implementation (RED phase).
"""

import pytest
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

# Mark all tests in this module as asyncio
pytestmark = pytest.mark.asyncio


class TestSettingsIntegration:
    """Integration tests for Settings model with User relationship."""

    @pytest.mark.asyncio
    async def test_create_settings_for_user(self, db_session, test_user):
        """Should create settings for a user and retrieve them."""
        try:
            from tradingagents.api.models.settings import Settings, RiskProfile

            # Create settings
            settings = Settings(
                user_id=test_user.id,
                risk_profile=RiskProfile.MODERATE,
                risk_score=Decimal("6.0"),
                max_position_pct=Decimal("15.0"),
                max_portfolio_risk_pct=Decimal("3.0"),
                investment_horizon_years=7,
                alert_preferences={
                    "email": {
                        "enabled": True,
                        "address": test_user.email,
                        "alert_types": ["price_alert", "portfolio_alert"]
                    }
                },
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            # Retrieve settings by user_id
            result = await db_session.execute(
                select(Settings).where(Settings.user_id == test_user.id)
            )
            retrieved_settings = result.scalar_one()

            # Verify
            assert retrieved_settings.id == settings.id
            assert retrieved_settings.user_id == test_user.id
            assert retrieved_settings.risk_profile == RiskProfile.MODERATE
            assert retrieved_settings.risk_score == Decimal("6.0")
            assert retrieved_settings.alert_preferences["email"]["address"] == test_user.email

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_update_user_settings(self, db_session, test_user):
        """Should update existing settings for a user."""
        try:
            from tradingagents.api.models.settings import Settings, RiskProfile

            # Create initial settings
            settings = Settings(
                user_id=test_user.id,
                risk_profile=RiskProfile.CONSERVATIVE,
                risk_score=Decimal("3.0"),
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            initial_id = settings.id

            # Update settings
            settings.risk_profile = RiskProfile.AGGRESSIVE
            settings.risk_score = Decimal("8.5")
            settings.max_position_pct = Decimal("25.0")
            settings.alert_preferences = {
                "sms": {
                    "enabled": True,
                    "phone": "+1234567890",
                }
            }

            await db_session.commit()
            await db_session.refresh(settings)

            # Verify updates
            assert settings.id == initial_id  # Same record
            assert settings.risk_profile == RiskProfile.AGGRESSIVE
            assert settings.risk_score == Decimal("8.5")
            assert settings.max_position_pct == Decimal("25.0")
            assert settings.alert_preferences["sms"]["phone"] == "+1234567890"

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_settings_isolation_between_users(self, db_session, test_user, second_user):
        """Should maintain separate settings for different users."""
        try:
            from tradingagents.api.models.settings import Settings, RiskProfile

            # Create settings for first user
            settings1 = Settings(
                user_id=test_user.id,
                risk_profile=RiskProfile.CONSERVATIVE,
                risk_score=Decimal("2.0"),
                max_position_pct=Decimal("5.0"),
            )
            db_session.add(settings1)

            # Create settings for second user
            settings2 = Settings(
                user_id=second_user.id,
                risk_profile=RiskProfile.AGGRESSIVE,
                risk_score=Decimal("9.0"),
                max_position_pct=Decimal("30.0"),
            )
            db_session.add(settings2)

            await db_session.commit()

            # Retrieve settings for first user
            result1 = await db_session.execute(
                select(Settings).where(Settings.user_id == test_user.id)
            )
            user1_settings = result1.scalar_one()

            # Retrieve settings for second user
            result2 = await db_session.execute(
                select(Settings).where(Settings.user_id == second_user.id)
            )
            user2_settings = result2.scalar_one()

            # Verify isolation
            assert user1_settings.id != user2_settings.id
            assert user1_settings.risk_profile == RiskProfile.CONSERVATIVE
            assert user2_settings.risk_profile == RiskProfile.AGGRESSIVE
            assert user1_settings.max_position_pct == Decimal("5.0")
            assert user2_settings.max_position_pct == Decimal("30.0")

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_complex_alert_preferences_workflow(self, db_session, test_user):
        """Should handle complex alert preferences updates."""
        try:
            from tradingagents.api.models.settings import Settings

            # Start with email alerts only
            settings = Settings(
                user_id=test_user.id,
                alert_preferences={
                    "email": {
                        "enabled": True,
                        "address": "user@example.com",
                        "alert_types": ["price_alert"]
                    }
                },
            )
            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            # Add SMS alerts
            settings.alert_preferences = {
                "email": {
                    "enabled": True,
                    "address": "user@example.com",
                    "alert_types": ["price_alert", "portfolio_alert"]
                },
                "sms": {
                    "enabled": True,
                    "phone": "+1234567890",
                    "alert_types": ["critical_alert"],
                    "rate_limit": {"max_per_hour": 5}
                }
            }
            await db_session.commit()
            await db_session.refresh(settings)

            # Verify complex structure
            assert "email" in settings.alert_preferences
            assert "sms" in settings.alert_preferences
            assert len(settings.alert_preferences["email"]["alert_types"]) == 2
            assert settings.alert_preferences["sms"]["rate_limit"]["max_per_hour"] == 5

            # Disable email, keep SMS - must reassign entire dict for SQLAlchemy to track change
            updated_prefs = dict(settings.alert_preferences)
            updated_prefs["email"] = dict(updated_prefs["email"])
            updated_prefs["email"]["enabled"] = False
            settings.alert_preferences = updated_prefs
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.alert_preferences["email"]["enabled"] is False
            assert settings.alert_preferences["sms"]["enabled"] is True

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_query_settings_by_risk_profile(self, db_session, test_user, second_user):
        """Should query settings by risk profile."""
        try:
            from tradingagents.api.models.settings import Settings, RiskProfile
            from tradingagents.api.models import User
            from tradingagents.api.services.auth_service import hash_password

            # Create third user
            user3 = User(
                username="user3",
                email="user3@example.com",
                hashed_password=hash_password("password123"),
            )
            db_session.add(user3)
            await db_session.commit()
            await db_session.refresh(user3)

            # Create settings with different risk profiles
            settings1 = Settings(user_id=test_user.id, risk_profile=RiskProfile.CONSERVATIVE)
            settings2 = Settings(user_id=second_user.id, risk_profile=RiskProfile.AGGRESSIVE)
            settings3 = Settings(user_id=user3.id, risk_profile=RiskProfile.CONSERVATIVE)

            db_session.add_all([settings1, settings2, settings3])
            await db_session.commit()

            # Query conservative profiles
            result = await db_session.execute(
                select(Settings).where(Settings.risk_profile == RiskProfile.CONSERVATIVE)
            )
            conservative_settings = result.scalars().all()

            # Verify
            assert len(conservative_settings) == 2
            assert all(s.risk_profile == RiskProfile.CONSERVATIVE for s in conservative_settings)

            # Query aggressive profiles
            result = await db_session.execute(
                select(Settings).where(Settings.risk_profile == RiskProfile.AGGRESSIVE)
            )
            aggressive_settings = result.scalars().all()

            assert len(aggressive_settings) == 1
            assert aggressive_settings[0].user_id == second_user.id

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_settings_with_user_deletion(self, db_session):
        """Should handle settings cleanup when user is deleted."""
        try:
            from tradingagents.api.models.settings import Settings, RiskProfile
            from tradingagents.api.models import User
            from tradingagents.api.services.auth_service import hash_password

            # Create user
            user = User(
                username="tempuser",
                email="temp@example.com",
                hashed_password=hash_password("password123"),
            )
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)

            # Create settings
            settings = Settings(
                user_id=user.id,
                risk_profile=RiskProfile.MODERATE,
            )
            db_session.add(settings)
            await db_session.commit()

            settings_id = settings.id
            user_id = user.id

            # Delete user
            await db_session.delete(user)
            await db_session.commit()

            # Verify settings were cascade deleted
            result = await db_session.execute(
                select(Settings).where(Settings.id == settings_id)
            )
            deleted_settings = result.scalar_one_or_none()

            assert deleted_settings is None

            # Verify user is also deleted
            result = await db_session.execute(
                select(User).where(User.id == user_id)
            )
            deleted_user = result.scalar_one_or_none()

            assert deleted_user is None

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")
