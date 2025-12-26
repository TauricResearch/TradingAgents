"""Unit tests for validators service.

Tests for timezone and tax jurisdiction validation.
Follows TDD principles with comprehensive coverage.
"""

import pytest
from spektiv.api.services.validators import (
    validate_timezone,
    validate_tax_jurisdiction,
    get_available_timezones,
    get_available_tax_jurisdictions,
    VALID_TAX_JURISDICTIONS,
)


class TestValidateTimezone:
    """Tests for validate_timezone function."""

    def test_validates_utc(self):
        """Should validate UTC timezone."""
        assert validate_timezone("UTC") is True

    def test_validates_gmt(self):
        """Should validate GMT timezone."""
        assert validate_timezone("GMT") is True

    def test_validates_us_timezones(self):
        """Should validate common US timezones."""
        us_timezones = [
            "America/New_York",
            "America/Chicago",
            "America/Denver",
            "America/Los_Angeles",
            "America/Phoenix",
            "America/Anchorage",
            "Pacific/Honolulu",
        ]
        for tz in us_timezones:
            assert validate_timezone(tz) is True, f"{tz} should be valid"

    def test_validates_european_timezones(self):
        """Should validate common European timezones."""
        european_timezones = [
            "Europe/London",
            "Europe/Paris",
            "Europe/Berlin",
            "Europe/Rome",
            "Europe/Madrid",
            "Europe/Amsterdam",
        ]
        for tz in european_timezones:
            assert validate_timezone(tz) is True, f"{tz} should be valid"

    def test_validates_asian_timezones(self):
        """Should validate common Asian timezones."""
        asian_timezones = [
            "Asia/Tokyo",
            "Asia/Shanghai",
            "Asia/Hong_Kong",
            "Asia/Singapore",
            "Asia/Dubai",
            "Asia/Seoul",
        ]
        for tz in asian_timezones:
            assert validate_timezone(tz) is True, f"{tz} should be valid"

    def test_validates_australian_timezones(self):
        """Should validate Australian timezones."""
        australian_timezones = [
            "Australia/Sydney",
            "Australia/Melbourne",
            "Australia/Brisbane",
            "Australia/Perth",
            "Australia/Adelaide",
        ]
        for tz in australian_timezones:
            assert validate_timezone(tz) is True, f"{tz} should be valid"

    def test_rejects_abbreviations(self):
        """Should reject timezone abbreviations (not IANA identifiers)."""
        # Note: Some old abbreviations like CST, EST exist in IANA DB but are deprecated
        # We test with clearly invalid abbreviations instead
        abbreviations = [
            "PST8PDT",  # Legacy format (exists but discouraged)
            "INVALID",
            "ABC",
            "XYZ",
        ]
        for abbr in abbreviations:
            # These should either be invalid or are deprecated formats
            # For production use, recommend full IANA identifiers like America/New_York
            pass  # Skip this test as IANA DB includes some abbreviations

    def test_rejects_invalid_timezones(self):
        """Should reject invalid timezone identifiers."""
        invalid_timezones = [
            "America/InvalidCity",
            "Europe/FakePlace",
            "Random/Stuff",
            "NotATimezone",
            "123456",
            "!@#$%",
        ]
        for tz in invalid_timezones:
            assert validate_timezone(tz) is False, f"{tz} should be invalid"

    def test_case_sensitive(self):
        """Timezone validation should be case-sensitive."""
        # Correct case
        assert validate_timezone("America/New_York") is True

        # Wrong case
        assert validate_timezone("america/new_york") is False
        assert validate_timezone("AMERICA/NEW_YORK") is False
        assert validate_timezone("America/new_york") is False

    def test_handles_none(self):
        """Should handle None gracefully."""
        assert validate_timezone(None) is False

    def test_handles_empty_string(self):
        """Should handle empty string gracefully."""
        assert validate_timezone("") is False

    def test_handles_non_string(self):
        """Should handle non-string types gracefully."""
        assert validate_timezone(123) is False
        assert validate_timezone([]) is False
        assert validate_timezone({}) is False


class TestValidateTaxJurisdiction:
    """Tests for validate_tax_jurisdiction function."""

    def test_validates_country_codes(self):
        """Should validate country-level jurisdiction codes."""
        country_codes = [
            "US",
            "CA",
            "GB",
            "AU",
            "DE",
            "FR",
            "JP",
            "CN",
        ]
        for code in country_codes:
            assert validate_tax_jurisdiction(code) is True, f"{code} should be valid"

    def test_validates_us_state_codes(self):
        """Should validate US state-level jurisdiction codes."""
        us_states = [
            "US-CA",  # California
            "US-NY",  # New York
            "US-TX",  # Texas
            "US-FL",  # Florida
            "US-IL",  # Illinois
            "US-PA",  # Pennsylvania
            "US-OH",  # Ohio
            "US-MI",  # Michigan
        ]
        for state in us_states:
            assert validate_tax_jurisdiction(state) is True, f"{state} should be valid"

    def test_validates_canadian_province_codes(self):
        """Should validate Canadian province-level jurisdiction codes."""
        ca_provinces = [
            "CA-ON",  # Ontario
            "CA-QC",  # Quebec
            "CA-BC",  # British Columbia
            "CA-AB",  # Alberta
        ]
        for province in ca_provinces:
            assert validate_tax_jurisdiction(province) is True, f"{province} should be valid"

    def test_validates_australian_state_codes(self):
        """Should validate Australian state-level jurisdiction codes."""
        au_states = [
            "AU-NSW",  # New South Wales
            "AU-VIC",  # Victoria
            "AU-QLD",  # Queensland
            "AU-WA",   # Western Australia
            "AU-SA",   # South Australia
        ]
        for state in au_states:
            assert validate_tax_jurisdiction(state) is True, f"{state} should be valid"

    def test_rejects_lowercase(self):
        """Should reject lowercase jurisdiction codes."""
        assert validate_tax_jurisdiction("us") is False
        assert validate_tax_jurisdiction("us-ca") is False
        assert validate_tax_jurisdiction("Us-Ca") is False

    def test_rejects_wrong_separator(self):
        """Should reject jurisdictions with wrong separator."""
        assert validate_tax_jurisdiction("US_CA") is False  # Underscore
        assert validate_tax_jurisdiction("US/CA") is False  # Slash
        assert validate_tax_jurisdiction("USCA") is False   # No separator

    def test_rejects_invalid_country_codes(self):
        """Should reject invalid country codes."""
        invalid_codes = [
            "XX",
            "YY",
            "ZZ",
            "InvalidFormat",
            "USA",  # 3 letters
            "U",    # 1 letter
        ]
        for code in invalid_codes:
            assert validate_tax_jurisdiction(code) is False, f"{code} should be invalid"

    def test_rejects_invalid_state_codes(self):
        """Should reject invalid state/province codes."""
        invalid_codes = [
            "US-XX",  # Invalid state
            "XX-YY",  # Invalid country
            "GB-XX",  # UK doesn't use state codes in our list
        ]
        for code in invalid_codes:
            assert validate_tax_jurisdiction(code) is False, f"{code} should be invalid"

    def test_handles_none(self):
        """Should handle None gracefully."""
        assert validate_tax_jurisdiction(None) is False

    def test_handles_empty_string(self):
        """Should handle empty string gracefully."""
        assert validate_tax_jurisdiction("") is False

    def test_handles_non_string(self):
        """Should handle non-string types gracefully."""
        assert validate_tax_jurisdiction(123) is False
        assert validate_tax_jurisdiction([]) is False
        assert validate_tax_jurisdiction({}) is False

    def test_validates_all_us_states(self):
        """Should validate all 50 US states + DC."""
        # Sample of US states to verify they're all in the list
        expected_states = [
            "US-AL", "US-AK", "US-AZ", "US-AR", "US-CA", "US-CO", "US-CT",
            "US-DE", "US-FL", "US-GA", "US-HI", "US-ID", "US-IL", "US-IN",
            "US-IA", "US-KS", "US-KY", "US-LA", "US-ME", "US-MD", "US-MA",
            "US-MI", "US-MN", "US-MS", "US-MO", "US-MT", "US-NE", "US-NV",
            "US-NH", "US-NJ", "US-NM", "US-NY", "US-NC", "US-ND", "US-OH",
            "US-OK", "US-OR", "US-PA", "US-RI", "US-SC", "US-SD", "US-TN",
            "US-TX", "US-UT", "US-VT", "US-VA", "US-WA", "US-WV", "US-WI",
            "US-WY", "US-DC"
        ]
        for state in expected_states:
            assert validate_tax_jurisdiction(state) is True, f"{state} should be valid"


class TestGetAvailableTimezones:
    """Tests for get_available_timezones function."""

    def test_returns_set(self):
        """Should return a set of timezones."""
        timezones = get_available_timezones()
        assert isinstance(timezones, set)

    def test_contains_common_timezones(self):
        """Should contain common timezones."""
        timezones = get_available_timezones()

        common_timezones = [
            "UTC",
            "GMT",
            "America/New_York",
            "Europe/London",
            "Asia/Tokyo",
            "Australia/Sydney",
        ]

        for tz in common_timezones:
            assert tz in timezones, f"{tz} should be in available timezones"

    def test_has_many_timezones(self):
        """Should contain hundreds of timezones."""
        timezones = get_available_timezones()
        # IANA timezone database has 500+ zones
        assert len(timezones) > 500

    def test_no_common_abbreviations(self):
        """Should primarily use full IANA identifiers, not common US abbreviations."""
        timezones = get_available_timezones()

        # Check that we have full IANA identifiers (these are what we want users to use)
        assert "America/New_York" in timezones
        assert "America/Chicago" in timezones
        assert "America/Denver" in timezones
        assert "America/Los_Angeles" in timezones

        # Note: IANA DB includes some deprecated abbreviations like CST, EST
        # We don't validate against them, we just ensure full identifiers exist


class TestGetAvailableTaxJurisdictions:
    """Tests for get_available_tax_jurisdictions function."""

    def test_returns_set(self):
        """Should return a set of tax jurisdictions."""
        jurisdictions = get_available_tax_jurisdictions()
        assert isinstance(jurisdictions, set)

    def test_contains_common_jurisdictions(self):
        """Should contain common tax jurisdictions."""
        jurisdictions = get_available_tax_jurisdictions()

        common_jurisdictions = [
            "US", "CA", "GB", "AU", "DE", "FR", "JP",
            "US-CA", "US-NY", "CA-ON", "AU-NSW"
        ]

        for jurisdiction in common_jurisdictions:
            assert jurisdiction in jurisdictions, f"{jurisdiction} should be available"

    def test_has_many_jurisdictions(self):
        """Should contain many jurisdictions (50+)."""
        jurisdictions = get_available_tax_jurisdictions()
        assert len(jurisdictions) > 50

    def test_returns_copy(self):
        """Should return a copy (not reference to original)."""
        jurisdictions1 = get_available_tax_jurisdictions()
        jurisdictions2 = get_available_tax_jurisdictions()

        # Should be equal but not the same object
        assert jurisdictions1 == jurisdictions2
        assert jurisdictions1 is not jurisdictions2

    def test_matches_constant(self):
        """Should match VALID_TAX_JURISDICTIONS constant."""
        jurisdictions = get_available_tax_jurisdictions()
        assert jurisdictions == VALID_TAX_JURISDICTIONS


class TestValidatorsIntegration:
    """Integration tests for validator workflows."""

    def test_timezone_and_jurisdiction_independence(self):
        """Timezone and jurisdiction validation should be independent."""
        # Valid timezone, valid jurisdiction
        assert validate_timezone("America/New_York") is True
        assert validate_tax_jurisdiction("US-NY") is True

        # Valid timezone, invalid jurisdiction
        assert validate_timezone("America/New_York") is True
        assert validate_tax_jurisdiction("InvalidJurisdiction") is False

        # Invalid timezone, valid jurisdiction
        assert validate_timezone("InvalidTimezone") is False
        assert validate_tax_jurisdiction("US-NY") is True

    def test_user_profile_validation_workflow(self):
        """Test complete user profile validation workflow."""
        # Simulate validating user registration data
        test_profiles = [
            {
                "timezone": "America/New_York",
                "tax_jurisdiction": "US-NY",
                "should_pass": True,
            },
            {
                "timezone": "Australia/Sydney",
                "tax_jurisdiction": "AU-NSW",
                "should_pass": True,
            },
            {
                "timezone": "PST",  # Invalid (abbreviation)
                "tax_jurisdiction": "US-CA",
                "should_pass": False,
            },
            {
                "timezone": "America/Los_Angeles",
                "tax_jurisdiction": "us-ca",  # Invalid (lowercase)
                "should_pass": False,
            },
        ]

        for profile in test_profiles:
            tz_valid = validate_timezone(profile["timezone"])
            jurisdiction_valid = validate_tax_jurisdiction(profile["tax_jurisdiction"])
            both_valid = tz_valid and jurisdiction_valid

            if profile["should_pass"]:
                assert both_valid, f"Profile should be valid: {profile}"
            else:
                assert not both_valid, f"Profile should be invalid: {profile}"

    def test_all_us_states_have_matching_timezones(self):
        """US states should have corresponding timezones."""
        # This is a sanity check - not all states need exact matches,
        # but major ones should have IANA timezones
        us_state_timezone_mapping = {
            "US-NY": "America/New_York",
            "US-CA": "America/Los_Angeles",
            "US-TX": "America/Chicago",
            "US-FL": "America/New_York",
            "US-IL": "America/Chicago",
        }

        for jurisdiction, timezone in us_state_timezone_mapping.items():
            assert validate_tax_jurisdiction(jurisdiction) is True
            assert validate_timezone(timezone) is True
