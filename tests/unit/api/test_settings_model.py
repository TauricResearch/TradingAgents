"""Unit tests for Settings model (Issue #5: DB-4).

Tests for Settings model fields including:
- RiskProfile enum (CONSERVATIVE, MODERATE, AGGRESSIVE)
- risk_score (0-10 validation)
- max_position_pct (0-100 validation)
- max_portfolio_risk_pct (0-100 validation)
- investment_horizon_years (>=0 validation)
- alert_preferences (JSON structure)
- One-to-one relationship with User
- Unique constraint on user_id
- Cascade delete behavior
- CheckConstraints for numeric bounds

Follows TDD principles with comprehensive coverage.
Tests written BEFORE implementation (RED phase).
"""

import pytest
import json
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

# Mark all tests in this module as asyncio
pytestmark = pytest.mark.asyncio


class TestSettingsBasicFields:
    """Tests for basic Settings model fields."""

    @pytest.mark.asyncio
    async def test_create_settings_with_required_fields(self, db_session, test_user):
        """Should create settings with only required fields (user_id)."""
        try:
            from tradingagents.api.models.settings import Settings, RiskProfile

            settings = Settings(
                user_id=test_user.id,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            # Assert
            assert settings.id is not None
            assert settings.user_id == test_user.id

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_settings_defaults(self, db_session, test_user):
        """Should apply default values to optional fields."""
        try:
            from tradingagents.api.models.settings import Settings, RiskProfile

            settings = Settings(
                user_id=test_user.id,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            # Check defaults
            assert settings.risk_profile == RiskProfile.MODERATE
            assert settings.risk_score == Decimal("5.0")
            assert settings.max_position_pct == Decimal("10.0")
            assert settings.max_portfolio_risk_pct == Decimal("2.0")
            assert settings.investment_horizon_years == 5
            assert settings.alert_preferences == {}
            assert settings.created_at is not None
            assert settings.updated_at is not None

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_settings_with_all_fields(self, db_session, test_user):
        """Should create settings with all fields specified."""
        try:
            from tradingagents.api.models.settings import Settings, RiskProfile

            alert_prefs = {
                "email": {
                    "enabled": True,
                    "address": "user@example.com",
                    "alert_types": ["price_alert", "portfolio_alert"]
                },
                "sms": {
                    "enabled": True,
                    "phone": "+1234567890",
                    "rate_limit": {"max_per_hour": 5}
                }
            }

            settings = Settings(
                user_id=test_user.id,
                risk_profile=RiskProfile.AGGRESSIVE,
                risk_score=Decimal("8.5"),
                max_position_pct=Decimal("25.0"),
                max_portfolio_risk_pct=Decimal("5.0"),
                investment_horizon_years=10,
                alert_preferences=alert_prefs,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            # Assert all fields
            assert settings.id is not None
            assert settings.user_id == test_user.id
            assert settings.risk_profile == RiskProfile.AGGRESSIVE
            assert settings.risk_score == Decimal("8.5")
            assert settings.max_position_pct == Decimal("25.0")
            assert settings.max_portfolio_risk_pct == Decimal("5.0")
            assert settings.investment_horizon_years == 10
            assert settings.alert_preferences == alert_prefs

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_settings_timestamps_auto_populate(self, db_session, test_user):
        """Should auto-populate created_at and updated_at timestamps."""
        try:
            from tradingagents.api.models.settings import Settings
            from datetime import datetime

            settings = Settings(
                user_id=test_user.id,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            # Assert timestamps exist and are recent
            assert settings.created_at is not None
            assert settings.updated_at is not None
            assert isinstance(settings.created_at, datetime)
            assert isinstance(settings.updated_at, datetime)

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")


class TestRiskProfileEnum:
    """Tests for RiskProfile enum validation."""

    @pytest.mark.asyncio
    async def test_risk_profile_conservative(self, db_session, test_user):
        """Should create settings with CONSERVATIVE risk profile."""
        try:
            from tradingagents.api.models.settings import Settings, RiskProfile

            settings = Settings(
                user_id=test_user.id,
                risk_profile=RiskProfile.CONSERVATIVE,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.risk_profile == RiskProfile.CONSERVATIVE
            assert settings.risk_profile.value == "CONSERVATIVE"

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_risk_profile_moderate(self, db_session, test_user):
        """Should create settings with MODERATE risk profile."""
        try:
            from tradingagents.api.models.settings import Settings, RiskProfile

            settings = Settings(
                user_id=test_user.id,
                risk_profile=RiskProfile.MODERATE,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.risk_profile == RiskProfile.MODERATE
            assert settings.risk_profile.value == "MODERATE"

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_risk_profile_aggressive(self, db_session, test_user):
        """Should create settings with AGGRESSIVE risk profile."""
        try:
            from tradingagents.api.models.settings import Settings, RiskProfile

            settings = Settings(
                user_id=test_user.id,
                risk_profile=RiskProfile.AGGRESSIVE,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.risk_profile == RiskProfile.AGGRESSIVE
            assert settings.risk_profile.value == "AGGRESSIVE"

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_risk_profile_invalid_value(self, db_session, test_user):
        """Should reject invalid risk profile values."""
        try:
            from tradingagents.api.models.settings import Settings

            # Attempting to use invalid value should raise ValueError
            with pytest.raises((ValueError, AttributeError)):
                settings = Settings(
                    user_id=test_user.id,
                    risk_profile="INVALID_RISK_PROFILE",
                )
                db_session.add(settings)
                await db_session.commit()

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")


class TestRiskScoreValidation:
    """Tests for risk_score field validation (0-10 range)."""

    @pytest.mark.asyncio
    async def test_risk_score_minimum_valid(self, db_session, test_user):
        """Should accept risk_score of 0 (minimum valid)."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
                risk_score=Decimal("0.0"),
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.risk_score == Decimal("0.0")

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_risk_score_maximum_valid(self, db_session, test_user):
        """Should accept risk_score of 10 (maximum valid)."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
                risk_score=Decimal("10.0"),
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.risk_score == Decimal("10.0")

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_risk_score_mid_range(self, db_session, test_user):
        """Should accept mid-range risk_score values."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
                risk_score=Decimal("5.5"),
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.risk_score == Decimal("5.5")

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_risk_score_out_of_range(self, db_session, test_user):
        """Should reject risk_score outside 0-10 range."""
        try:
            from tradingagents.api.models.settings import Settings
            from sqlalchemy.exc import IntegrityError

            # Store user_id before async operations to avoid lazy load after rollback
            user_id = test_user.id

            # Test negative value
            settings = Settings(
                user_id=user_id,
                risk_score=Decimal("-1.0"),
            )
            db_session.add(settings)

            with pytest.raises(IntegrityError):
                await db_session.commit()

            await db_session.rollback()

            # Test value > 10
            settings2 = Settings(
                user_id=user_id,
                risk_score=Decimal("11.0"),
            )
            db_session.add(settings2)

            with pytest.raises(IntegrityError):
                await db_session.commit()

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")


class TestMaxPositionPctValidation:
    """Tests for max_position_pct field validation (0-100 range)."""

    @pytest.mark.asyncio
    async def test_max_position_pct_minimum_valid(self, db_session, test_user):
        """Should accept max_position_pct of 0."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
                max_position_pct=Decimal("0.0"),
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.max_position_pct == Decimal("0.0")

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_max_position_pct_maximum_valid(self, db_session, test_user):
        """Should accept max_position_pct of 100."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
                max_position_pct=Decimal("100.0"),
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.max_position_pct == Decimal("100.0")

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_max_position_pct_out_of_range(self, db_session, test_user):
        """Should reject max_position_pct outside 0-100 range."""
        try:
            from tradingagents.api.models.settings import Settings
            from sqlalchemy.exc import IntegrityError

            # Store user_id before async operations to avoid lazy load after rollback
            user_id = test_user.id

            # Test negative value
            settings = Settings(
                user_id=user_id,
                max_position_pct=Decimal("-1.0"),
            )
            db_session.add(settings)

            with pytest.raises(IntegrityError):
                await db_session.commit()

            await db_session.rollback()

            # Test value > 100
            settings2 = Settings(
                user_id=user_id,
                max_position_pct=Decimal("101.0"),
            )
            db_session.add(settings2)

            with pytest.raises(IntegrityError):
                await db_session.commit()

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")


class TestMaxPortfolioRiskPctValidation:
    """Tests for max_portfolio_risk_pct field validation (0-100 range)."""

    @pytest.mark.asyncio
    async def test_max_portfolio_risk_pct_minimum_valid(self, db_session, test_user):
        """Should accept max_portfolio_risk_pct of 0."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
                max_portfolio_risk_pct=Decimal("0.0"),
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.max_portfolio_risk_pct == Decimal("0.0")

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_max_portfolio_risk_pct_maximum_valid(self, db_session, test_user):
        """Should accept max_portfolio_risk_pct of 100."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
                max_portfolio_risk_pct=Decimal("100.0"),
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.max_portfolio_risk_pct == Decimal("100.0")

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_max_portfolio_risk_pct_out_of_range(self, db_session, test_user):
        """Should reject max_portfolio_risk_pct outside 0-100 range."""
        try:
            from tradingagents.api.models.settings import Settings
            from sqlalchemy.exc import IntegrityError

            # Store user_id before async operations to avoid lazy load after rollback
            user_id = test_user.id

            # Test negative value
            settings = Settings(
                user_id=user_id,
                max_portfolio_risk_pct=Decimal("-1.0"),
            )
            db_session.add(settings)

            with pytest.raises(IntegrityError):
                await db_session.commit()

            await db_session.rollback()

            # Test value > 100
            settings2 = Settings(
                user_id=user_id,
                max_portfolio_risk_pct=Decimal("101.0"),
            )
            db_session.add(settings2)

            with pytest.raises(IntegrityError):
                await db_session.commit()

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")


class TestInvestmentHorizonValidation:
    """Tests for investment_horizon_years field validation (>=0)."""

    @pytest.mark.asyncio
    async def test_investment_horizon_valid_positive(self, db_session, test_user):
        """Should accept positive investment horizon values."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
                investment_horizon_years=15,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.investment_horizon_years == 15

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_investment_horizon_zero_valid(self, db_session, test_user):
        """Should accept investment horizon of 0."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
                investment_horizon_years=0,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.investment_horizon_years == 0

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_investment_horizon_negative_invalid(self, db_session, test_user):
        """Should reject negative investment horizon values."""
        try:
            from tradingagents.api.models.settings import Settings
            from sqlalchemy.exc import IntegrityError

            settings = Settings(
                user_id=test_user.id,
                investment_horizon_years=-1,
            )
            db_session.add(settings)

            with pytest.raises(IntegrityError):
                await db_session.commit()

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")


class TestAlertPreferencesJSON:
    """Tests for alert_preferences JSON field."""

    @pytest.mark.asyncio
    async def test_alert_preferences_empty_dict(self, db_session, test_user):
        """Should accept empty dict as alert preferences."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
                alert_preferences={},
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.alert_preferences == {}

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_alert_preferences_email_config(self, db_session, test_user):
        """Should store email alert preferences."""
        try:
            from tradingagents.api.models.settings import Settings

            email_prefs = {
                "email": {
                    "enabled": True,
                    "address": "user@example.com",
                    "alert_types": ["price_alert", "portfolio_alert", "execution_alert"]
                }
            }

            settings = Settings(
                user_id=test_user.id,
                alert_preferences=email_prefs,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.alert_preferences == email_prefs
            assert settings.alert_preferences["email"]["enabled"] is True
            assert settings.alert_preferences["email"]["address"] == "user@example.com"

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_alert_preferences_sms_config(self, db_session, test_user):
        """Should store SMS alert preferences."""
        try:
            from tradingagents.api.models.settings import Settings

            sms_prefs = {
                "sms": {
                    "enabled": True,
                    "phone": "+1234567890",
                    "alert_types": ["critical_alert"],
                    "rate_limit": {"max_per_hour": 5, "max_per_day": 20}
                }
            }

            settings = Settings(
                user_id=test_user.id,
                alert_preferences=sms_prefs,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.alert_preferences == sms_prefs
            assert settings.alert_preferences["sms"]["phone"] == "+1234567890"
            assert settings.alert_preferences["sms"]["rate_limit"]["max_per_hour"] == 5

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_alert_preferences_multiple_channels(self, db_session, test_user):
        """Should store preferences for multiple alert channels."""
        try:
            from tradingagents.api.models.settings import Settings

            multi_channel_prefs = {
                "email": {
                    "enabled": True,
                    "address": "user@example.com",
                    "alert_types": ["price_alert", "portfolio_alert"]
                },
                "sms": {
                    "enabled": True,
                    "phone": "+1234567890",
                    "rate_limit": {"max_per_hour": 5}
                },
                "push": {
                    "enabled": False,
                    "device_tokens": []
                }
            }

            settings = Settings(
                user_id=test_user.id,
                alert_preferences=multi_channel_prefs,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.alert_preferences == multi_channel_prefs
            assert "email" in settings.alert_preferences
            assert "sms" in settings.alert_preferences
            assert "push" in settings.alert_preferences

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_alert_preferences_nested_structure(self, db_session, test_user):
        """Should handle deeply nested JSON structures."""
        try:
            from tradingagents.api.models.settings import Settings

            nested_prefs = {
                "email": {
                    "enabled": True,
                    "address": "user@example.com",
                    "filters": {
                        "price_alerts": {
                            "min_change_pct": 5.0,
                            "symbols": ["AAPL", "GOOGL", "MSFT"]
                        },
                        "portfolio_alerts": {
                            "thresholds": {
                                "daily_loss": -2.0,
                                "daily_gain": 5.0
                            }
                        }
                    }
                }
            }

            settings = Settings(
                user_id=test_user.id,
                alert_preferences=nested_prefs,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.alert_preferences == nested_prefs
            assert settings.alert_preferences["email"]["filters"]["price_alerts"]["min_change_pct"] == 5.0

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_alert_preferences_rate_limiting(self, db_session, test_user):
        """Should store rate limiting configuration."""
        try:
            from tradingagents.api.models.settings import Settings

            rate_limit_prefs = {
                "sms": {
                    "enabled": True,
                    "phone": "+1234567890",
                    "rate_limit": {
                        "max_per_hour": 5,
                        "max_per_day": 20,
                        "max_per_week": 100,
                        "cooldown_minutes": 15
                    }
                }
            }

            settings = Settings(
                user_id=test_user.id,
                alert_preferences=rate_limit_prefs,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.alert_preferences["sms"]["rate_limit"]["max_per_hour"] == 5
            assert settings.alert_preferences["sms"]["rate_limit"]["max_per_day"] == 20
            assert settings.alert_preferences["sms"]["rate_limit"]["cooldown_minutes"] == 15

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_alert_preferences_update(self, db_session, test_user):
        """Should allow updating alert preferences."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
                alert_preferences={"email": {"enabled": False}},
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            # Update preferences
            settings.alert_preferences = {
                "email": {"enabled": True, "address": "new@example.com"}
            }
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.alert_preferences["email"]["enabled"] is True
            assert settings.alert_preferences["email"]["address"] == "new@example.com"

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_alert_preferences_null_allowed(self, db_session, test_user):
        """Should allow NULL alert preferences if column is nullable."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
                alert_preferences=None,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            # Should default to empty dict or be None
            assert settings.alert_preferences is None or settings.alert_preferences == {}

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")


class TestUserRelationship:
    """Tests for Settings-User one-to-one relationship."""

    @pytest.mark.asyncio
    async def test_settings_belongs_to_user(self, db_session, test_user):
        """Should establish relationship between settings and user."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            # Verify relationship
            assert settings.user_id == test_user.id
            # If relationship is set up, we should be able to access user
            # assert settings.user == test_user  # Uncomment when relationship is implemented

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_one_settings_per_user_constraint(self, db_session, test_user):
        """Should enforce unique constraint - one settings per user."""
        try:
            from tradingagents.api.models.settings import Settings
            from sqlalchemy.exc import IntegrityError

            # Create first settings
            settings1 = Settings(user_id=test_user.id)
            db_session.add(settings1)
            await db_session.commit()

            # Try to create second settings for same user
            settings2 = Settings(user_id=test_user.id)
            db_session.add(settings2)

            with pytest.raises(IntegrityError):
                await db_session.commit()

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_settings_cascade_delete_with_user(self, db_session, test_user):
        """Should cascade delete settings when user is deleted."""
        try:
            from tradingagents.api.models.settings import Settings
            from tradingagents.api.models import User

            # Create settings
            settings = Settings(user_id=test_user.id)
            db_session.add(settings)
            await db_session.commit()

            settings_id = settings.id

            # Delete user
            await db_session.delete(test_user)
            await db_session.commit()

            # Verify settings was deleted
            result = await db_session.execute(
                select(Settings).where(Settings.id == settings_id)
            )
            deleted_settings = result.scalar_one_or_none()

            assert deleted_settings is None

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_multiple_users_can_have_settings(self, db_session, test_user, second_user):
        """Should allow multiple users to have their own settings."""
        try:
            from tradingagents.api.models.settings import Settings, RiskProfile

            # Create settings for first user
            settings1 = Settings(
                user_id=test_user.id,
                risk_profile=RiskProfile.CONSERVATIVE,
            )
            db_session.add(settings1)

            # Create settings for second user
            settings2 = Settings(
                user_id=second_user.id,
                risk_profile=RiskProfile.AGGRESSIVE,
            )
            db_session.add(settings2)

            await db_session.commit()
            await db_session.refresh(settings1)
            await db_session.refresh(settings2)

            # Verify both settings exist with different configurations
            assert settings1.user_id == test_user.id
            assert settings1.risk_profile == RiskProfile.CONSERVATIVE
            assert settings2.user_id == second_user.id
            assert settings2.risk_profile == RiskProfile.AGGRESSIVE

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")


class TestSettingsConstraints:
    """Tests for database constraints and edge cases."""

    @pytest.mark.asyncio
    async def test_risk_score_boundary_values(self, db_session, test_user):
        """Should accept exact boundary values for risk_score."""
        try:
            from tradingagents.api.models.settings import Settings

            # Test 0 exactly
            settings1 = Settings(user_id=test_user.id, risk_score=Decimal("0"))
            db_session.add(settings1)
            await db_session.commit()
            assert settings1.risk_score == Decimal("0")

            await db_session.delete(settings1)
            await db_session.commit()

            # Test 10 exactly (with new user since one-to-one)
            from tradingagents.api.models import User
            from tradingagents.api.services.auth_service import hash_password

            user2 = User(
                username="testuser2",
                email="test2@example.com",
                hashed_password=hash_password("password123"),
            )
            db_session.add(user2)
            await db_session.commit()
            await db_session.refresh(user2)

            settings2 = Settings(user_id=user2.id, risk_score=Decimal("10"))
            db_session.add(settings2)
            await db_session.commit()
            assert settings2.risk_score == Decimal("10")

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_percentage_boundary_values(self, db_session, test_user):
        """Should accept exact boundary values for percentage fields."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
                max_position_pct=Decimal("0"),
                max_portfolio_risk_pct=Decimal("100"),
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.max_position_pct == Decimal("0")
            assert settings.max_portfolio_risk_pct == Decimal("100")

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_decimal_precision_preserved(self, db_session, test_user):
        """Should preserve decimal precision for numeric fields."""
        try:
            from tradingagents.api.models.settings import Settings

            settings = Settings(
                user_id=test_user.id,
                risk_score=Decimal("7.5"),
                max_position_pct=Decimal("15.25"),
                max_portfolio_risk_pct=Decimal("3.75"),
            )

            db_session.add(settings)
            await db_session.commit()
            await db_session.refresh(settings)

            assert settings.risk_score == Decimal("7.5")
            assert settings.max_position_pct == Decimal("15.25")
            assert settings.max_portfolio_risk_pct == Decimal("3.75")

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_required_user_id_constraint(self, db_session):
        """Should require user_id (NOT NULL constraint)."""
        try:
            from tradingagents.api.models.settings import Settings
            from sqlalchemy.exc import IntegrityError

            settings = Settings(
                risk_profile="MODERATE",
                # user_id intentionally missing
            )
            db_session.add(settings)

            with pytest.raises(IntegrityError):
                await db_session.commit()

        except ImportError:
            pytest.skip("Settings model not yet implemented (TDD RED phase)")
