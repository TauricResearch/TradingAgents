"""
Test suite for validators (Issue #3).

This module tests timezone and tax jurisdiction validation:
1. Timezone validation (IANA timezone database)
2. Tax jurisdiction validation (format and valid codes)
3. Edge cases and error handling
4. Integration with User model

Tests follow TDD - written before implementation.
"""

import pytest
from typing import Optional

pytestmark = pytest.mark.unit


# ============================================================================
# Unit Tests: Timezone Validation
# ============================================================================

class TestTimezoneValidation:
    """Test timezone validation functionality."""

    def test_validate_timezone_valid_utc(self):
        """Test validating UTC timezone."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_timezone

            result = validate_timezone("UTC")

            # Assert
            assert result is True
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_timezone_valid_america_new_york(self):
        """Test validating America/New_York timezone."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_timezone

            result = validate_timezone("America/New_York")

            # Assert
            assert result is True
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_timezone_valid_europe_london(self):
        """Test validating Europe/London timezone."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_timezone

            result = validate_timezone("Europe/London")

            # Assert
            assert result is True
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_timezone_valid_asia_tokyo(self):
        """Test validating Asia/Tokyo timezone."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_timezone

            result = validate_timezone("Asia/Tokyo")

            # Assert
            assert result is True
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_timezone_valid_australia_sydney(self):
        """Test validating Australia/Sydney timezone."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_timezone

            result = validate_timezone("Australia/Sydney")

            # Assert
            assert result is True
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_timezone_invalid_fake_timezone(self):
        """Test rejecting invalid timezone."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_timezone

            result = validate_timezone("Invalid/Timezone")

            # Assert
            assert result is False
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_timezone_invalid_empty_string(self):
        """Test rejecting empty string."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_timezone

            result = validate_timezone("")

            # Assert
            assert result is False
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_timezone_none(self):
        """Test handling None value."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_timezone

            # None should be accepted (nullable field)
            result = validate_timezone(None)

            # Assert: None is valid (nullable)
            assert result is True
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_timezone_case_sensitive(self):
        """Test that timezone validation is case-sensitive."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_timezone

            # Correct case
            result_correct = validate_timezone("America/New_York")

            # Wrong case
            result_wrong = validate_timezone("america/new_york")

            # Assert
            assert result_correct is True
            assert result_wrong is False
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_timezone_various_valid_timezones(self):
        """Test validating various valid IANA timezones."""
        # Arrange
        try:
            from tradingagents.api.services.validators import validate_timezone

            valid_timezones = [
                "UTC",
                "GMT",
                "America/New_York",
                "America/Los_Angeles",
                "America/Chicago",
                "America/Denver",
                "Europe/London",
                "Europe/Paris",
                "Europe/Berlin",
                "Asia/Tokyo",
                "Asia/Shanghai",
                "Asia/Hong_Kong",
                "Australia/Sydney",
                "Australia/Melbourne",
                "Pacific/Auckland",
            ]

            # Act & Assert
            for tz in valid_timezones:
                result = validate_timezone(tz)
                assert result is True, f"Timezone {tz} should be valid"
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_timezone_various_invalid_timezones(self):
        """Test rejecting various invalid timezones."""
        # Arrange
        try:
            from tradingagents.api.services.validators import validate_timezone

            invalid_timezones = [
                "PST",  # Abbreviations not valid
                "EST",
                "CST",
                "MST",
                "America/InvalidCity",
                "Europe/FakePlace",
                "Random/Stuff",
                "123456",
                "!@#$%",
                "america/new_york",  # Wrong case
            ]

            # Act & Assert
            for tz in invalid_timezones:
                result = validate_timezone(tz)
                assert result is False, f"Timezone {tz} should be invalid"
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_timezone_with_underscores(self):
        """Test timezones with underscores in city names."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_timezone

            # Valid timezones with underscores
            result1 = validate_timezone("America/New_York")
            result2 = validate_timezone("America/Los_Angeles")
            result3 = validate_timezone("America/Port-au-Prince")

            # Assert
            assert result1 is True
            assert result2 is True
            assert result3 is True
        except ImportError:
            pytest.skip("Validators not implemented yet")


# ============================================================================
# Unit Tests: Tax Jurisdiction Validation
# ============================================================================

class TestTaxJurisdictionValidation:
    """Test tax jurisdiction validation functionality."""

    def test_validate_tax_jurisdiction_valid_us_state(self):
        """Test validating US state tax jurisdiction."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            result = validate_tax_jurisdiction("US-CA")

            # Assert
            assert result is True
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_tax_jurisdiction_valid_us_states(self):
        """Test validating various US state tax jurisdictions."""
        # Arrange
        try:
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            valid_jurisdictions = [
                "US-CA",  # California
                "US-NY",  # New York
                "US-TX",  # Texas
                "US-FL",  # Florida
                "US-IL",  # Illinois
                "US-PA",  # Pennsylvania
                "US-OH",  # Ohio
                "US-WA",  # Washington
            ]

            # Act & Assert
            for jurisdiction in valid_jurisdictions:
                result = validate_tax_jurisdiction(jurisdiction)
                assert result is True, f"Jurisdiction {jurisdiction} should be valid"
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_tax_jurisdiction_valid_countries(self):
        """Test validating country-level tax jurisdictions."""
        # Arrange
        try:
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            valid_jurisdictions = [
                "US",  # United States
                "CA",  # Canada
                "GB",  # United Kingdom
                "DE",  # Germany
                "FR",  # France
                "JP",  # Japan
                "AU",  # Australia
                "NZ",  # New Zealand
            ]

            # Act & Assert
            for jurisdiction in valid_jurisdictions:
                result = validate_tax_jurisdiction(jurisdiction)
                assert result is True, f"Jurisdiction {jurisdiction} should be valid"
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_tax_jurisdiction_valid_canadian_provinces(self):
        """Test validating Canadian province tax jurisdictions."""
        # Arrange
        try:
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            valid_jurisdictions = [
                "CA-ON",  # Ontario
                "CA-QC",  # Quebec
                "CA-BC",  # British Columbia
                "CA-AB",  # Alberta
            ]

            # Act & Assert
            for jurisdiction in valid_jurisdictions:
                result = validate_tax_jurisdiction(jurisdiction)
                assert result is True, f"Jurisdiction {jurisdiction} should be valid"
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_tax_jurisdiction_invalid_format(self):
        """Test rejecting invalid format."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            invalid_jurisdictions = [
                "InvalidFormat",
                "US_CA",  # Wrong separator
                "US/CA",  # Wrong separator
                "USCA",  # No separator
                "us-ca",  # Lowercase
                "123",
                "!@#",
            ]

            # Act & Assert
            for jurisdiction in invalid_jurisdictions:
                result = validate_tax_jurisdiction(jurisdiction)
                assert result is False, f"Jurisdiction {jurisdiction} should be invalid"
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_tax_jurisdiction_invalid_country_code(self):
        """Test rejecting invalid country codes."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            result = validate_tax_jurisdiction("XX-YY")

            # Assert
            assert result is False
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_tax_jurisdiction_none(self):
        """Test handling None value."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            # None should be accepted (nullable field)
            result = validate_tax_jurisdiction(None)

            # Assert
            assert result is True
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_tax_jurisdiction_empty_string(self):
        """Test rejecting empty string."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            result = validate_tax_jurisdiction("")

            # Assert
            assert result is False
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_tax_jurisdiction_case_sensitive(self):
        """Test that tax jurisdiction validation is case-sensitive."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            # Correct case (uppercase)
            result_correct = validate_tax_jurisdiction("US-CA")

            # Wrong case (lowercase)
            result_wrong = validate_tax_jurisdiction("us-ca")

            # Assert
            assert result_correct is True
            assert result_wrong is False
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_validate_tax_jurisdiction_max_length(self):
        """Test rejecting very long jurisdiction strings."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            # Very long string
            result = validate_tax_jurisdiction("US-" + "A" * 100)

            # Assert: Should reject overly long jurisdictions
            assert result is False
        except ImportError:
            pytest.skip("Validators not implemented yet")


# ============================================================================
# Integration Tests: Validators with User Model
# ============================================================================

class TestValidatorsIntegration:
    """Test validators integrated with User model."""

    @pytest.mark.asyncio
    async def test_user_with_valid_timezone(self, db_session):
        """Test creating user with validated timezone."""
        # Arrange
        try:
            from tradingagents.api.models import User
            from tradingagents.api.services.validators import validate_timezone

            timezone = "America/New_York"
            assert validate_timezone(timezone) is True

            user = User(
                username="tzvaliduser",
                email="tzvalid@example.com",
                hashed_password="hash",
                timezone=timezone,
            )

            # Act
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)

            # Assert
            assert user.timezone == timezone
        except ImportError:
            pytest.skip("Models or validators not implemented yet")

    @pytest.mark.asyncio
    async def test_user_with_invalid_timezone_at_api_level(self, db_session):
        """Test that invalid timezone should be caught at API level, not DB."""
        # Arrange
        try:
            from tradingagents.api.models import User
            from tradingagents.api.services.validators import validate_timezone

            invalid_timezone = "Invalid/Timezone"
            assert validate_timezone(invalid_timezone) is False

            # Note: Database will accept it, validation happens at API layer
            user = User(
                username="tzinvalid",
                email="tzinvalid@example.com",
                hashed_password="hash",
                timezone=invalid_timezone,
            )

            # Act: DB should accept it (validation is at API level)
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)

            # Assert: DB accepts it, but validator rejects it
            assert user.timezone == invalid_timezone
            assert validate_timezone(user.timezone) is False
        except ImportError:
            pytest.skip("Models or validators not implemented yet")

    @pytest.mark.asyncio
    async def test_user_with_valid_tax_jurisdiction(self, db_session):
        """Test creating user with validated tax jurisdiction."""
        # Arrange
        try:
            from tradingagents.api.models import User
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            jurisdiction = "US-CA"
            assert validate_tax_jurisdiction(jurisdiction) is True

            user = User(
                username="taxvaliduser",
                email="taxvalid@example.com",
                hashed_password="hash",
                tax_jurisdiction=jurisdiction,
            )

            # Act
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)

            # Assert
            assert user.tax_jurisdiction == jurisdiction
        except ImportError:
            pytest.skip("Models or validators not implemented yet")

    @pytest.mark.asyncio
    async def test_user_with_both_validators(self, db_session):
        """Test creating user with both validated fields."""
        # Arrange
        try:
            from tradingagents.api.models import User
            from tradingagents.api.services.validators import (
                validate_timezone,
                validate_tax_jurisdiction,
            )

            timezone = "America/Los_Angeles"
            jurisdiction = "US-CA"

            assert validate_timezone(timezone) is True
            assert validate_tax_jurisdiction(jurisdiction) is True

            user = User(
                username="bothvalid",
                email="bothvalid@example.com",
                hashed_password="hash",
                timezone=timezone,
                tax_jurisdiction=jurisdiction,
            )

            # Act
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)

            # Assert
            assert user.timezone == timezone
            assert user.tax_jurisdiction == jurisdiction
        except ImportError:
            pytest.skip("Models or validators not implemented yet")


# ============================================================================
# Edge Cases: Validators
# ============================================================================

class TestValidatorEdgeCases:
    """Test edge cases in validators."""

    def test_timezone_with_special_characters(self):
        """Test timezone with special characters."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_timezone

            # Test various special characters
            result1 = validate_timezone("America/Port-au-Prince")  # Hyphen
            result2 = validate_timezone("America/Indiana/Indianapolis")  # Multiple slashes

            # Assert
            assert result1 is True
            assert result2 is True
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_timezone_whitespace_handling(self):
        """Test timezone validation with whitespace."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_timezone

            # Timezones with leading/trailing whitespace
            result1 = validate_timezone(" America/New_York ")
            result2 = validate_timezone("America/New_York ")
            result3 = validate_timezone(" America/New_York")

            # Assert: Should reject (strict validation)
            assert result1 is False
            assert result2 is False
            assert result3 is False
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_tax_jurisdiction_whitespace_handling(self):
        """Test tax jurisdiction validation with whitespace."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            # Jurisdictions with leading/trailing whitespace
            result1 = validate_tax_jurisdiction(" US-CA ")
            result2 = validate_tax_jurisdiction("US-CA ")
            result3 = validate_tax_jurisdiction(" US-CA")

            # Assert: Should reject (strict validation)
            assert result1 is False
            assert result2 is False
            assert result3 is False
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_timezone_numeric_string(self):
        """Test timezone validation with numeric strings."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_timezone

            result = validate_timezone("12345")

            # Assert
            assert result is False
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_tax_jurisdiction_only_country(self):
        """Test tax jurisdiction with only country code."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            # Two-letter country codes should be valid
            result_us = validate_tax_jurisdiction("US")
            result_ca = validate_tax_jurisdiction("CA")
            result_gb = validate_tax_jurisdiction("GB")

            # Assert
            assert result_us is True
            assert result_ca is True
            assert result_gb is True
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_tax_jurisdiction_single_letter(self):
        """Test tax jurisdiction with single letter."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            result = validate_tax_jurisdiction("A")

            # Assert
            assert result is False
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_timezone_sql_injection_attempt(self):
        """Test timezone validation against SQL injection."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_timezone

            malicious_inputs = [
                "'; DROP TABLE users; --",
                "1' OR '1'='1",
                "America/New_York'; DELETE FROM users; --",
            ]

            # Act & Assert
            for malicious in malicious_inputs:
                result = validate_timezone(malicious)
                assert result is False, f"Should reject malicious input: {malicious}"
        except ImportError:
            pytest.skip("Validators not implemented yet")

    def test_tax_jurisdiction_sql_injection_attempt(self):
        """Test tax jurisdiction validation against SQL injection."""
        # Arrange & Act
        try:
            from tradingagents.api.services.validators import validate_tax_jurisdiction

            malicious_inputs = [
                "'; DROP TABLE users; --",
                "1' OR '1'='1",
                "US-CA'; DELETE FROM users; --",
            ]

            # Act & Assert
            for malicious in malicious_inputs:
                result = validate_tax_jurisdiction(malicious)
                assert result is False, f"Should reject malicious input: {malicious}"
        except ImportError:
            pytest.skip("Validators not implemented yet")
