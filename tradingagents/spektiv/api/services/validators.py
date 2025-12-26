"""Validators for user profile fields.

This module provides validation functions for:
- Timezones (IANA timezone database)
- Tax jurisdictions (country codes and state/province codes)

All validators return True/False and are designed to be used
in Pydantic models and database constraints.
"""

from typing import Set
from zoneinfo import ZoneInfo, available_timezones


# Valid tax jurisdictions (ISO 3166-1 alpha-2 country codes + state/province)
# Format: "CC" for country-level, "CC-SS" for state/province-level
# This is a comprehensive list covering major jurisdictions
VALID_TAX_JURISDICTIONS: Set[str] = {
    # Country-level codes (ISO 3166-1 alpha-2)
    "US",  # United States
    "CA",  # Canada
    "GB",  # United Kingdom
    "AU",  # Australia
    "DE",  # Germany
    "FR",  # France
    "IT",  # Italy
    "ES",  # Spain
    "NL",  # Netherlands
    "BE",  # Belgium
    "CH",  # Switzerland
    "AT",  # Austria
    "SE",  # Sweden
    "NO",  # Norway
    "DK",  # Denmark
    "FI",  # Finland
    "IE",  # Ireland
    "PT",  # Portugal
    "GR",  # Greece
    "PL",  # Poland
    "CZ",  # Czech Republic
    "HU",  # Hungary
    "RO",  # Romania
    "JP",  # Japan
    "CN",  # China
    "KR",  # South Korea
    "IN",  # India
    "SG",  # Singapore
    "HK",  # Hong Kong
    "NZ",  # New Zealand
    "MX",  # Mexico
    "BR",  # Brazil
    "AR",  # Argentina
    "CL",  # Chile
    "ZA",  # South Africa
    "AE",  # United Arab Emirates
    "SA",  # Saudi Arabia
    "IL",  # Israel
    "TR",  # Turkey
    "RU",  # Russia
    "UA",  # Ukraine
    "TH",  # Thailand
    "MY",  # Malaysia
    "ID",  # Indonesia
    "PH",  # Philippines
    "VN",  # Vietnam
    "TW",  # Taiwan

    # United States - State level
    "US-AL",  # Alabama
    "US-AK",  # Alaska
    "US-AZ",  # Arizona
    "US-AR",  # Arkansas
    "US-CA",  # California
    "US-CO",  # Colorado
    "US-CT",  # Connecticut
    "US-DE",  # Delaware
    "US-FL",  # Florida
    "US-GA",  # Georgia
    "US-HI",  # Hawaii
    "US-ID",  # Idaho
    "US-IL",  # Illinois
    "US-IN",  # Indiana
    "US-IA",  # Iowa
    "US-KS",  # Kansas
    "US-KY",  # Kentucky
    "US-LA",  # Louisiana
    "US-ME",  # Maine
    "US-MD",  # Maryland
    "US-MA",  # Massachusetts
    "US-MI",  # Michigan
    "US-MN",  # Minnesota
    "US-MS",  # Mississippi
    "US-MO",  # Missouri
    "US-MT",  # Montana
    "US-NE",  # Nebraska
    "US-NV",  # Nevada
    "US-NH",  # New Hampshire
    "US-NJ",  # New Jersey
    "US-NM",  # New Mexico
    "US-NY",  # New York
    "US-NC",  # North Carolina
    "US-ND",  # North Dakota
    "US-OH",  # Ohio
    "US-OK",  # Oklahoma
    "US-OR",  # Oregon
    "US-PA",  # Pennsylvania
    "US-RI",  # Rhode Island
    "US-SC",  # South Carolina
    "US-SD",  # South Dakota
    "US-TN",  # Tennessee
    "US-TX",  # Texas
    "US-UT",  # Utah
    "US-VT",  # Vermont
    "US-VA",  # Virginia
    "US-WA",  # Washington
    "US-WV",  # West Virginia
    "US-WI",  # Wisconsin
    "US-WY",  # Wyoming
    "US-DC",  # District of Columbia

    # Canada - Province/Territory level
    "CA-AB",  # Alberta
    "CA-BC",  # British Columbia
    "CA-MB",  # Manitoba
    "CA-NB",  # New Brunswick
    "CA-NL",  # Newfoundland and Labrador
    "CA-NS",  # Nova Scotia
    "CA-NT",  # Northwest Territories
    "CA-NU",  # Nunavut
    "CA-ON",  # Ontario
    "CA-PE",  # Prince Edward Island
    "CA-QC",  # Quebec
    "CA-SK",  # Saskatchewan
    "CA-YT",  # Yukon

    # Australia - State/Territory level
    "AU-NSW",  # New South Wales
    "AU-VIC",  # Victoria
    "AU-QLD",  # Queensland
    "AU-SA",   # South Australia
    "AU-WA",   # Western Australia
    "AU-TAS",  # Tasmania
    "AU-NT",   # Northern Territory
    "AU-ACT",  # Australian Capital Territory
}


def validate_timezone(timezone: str) -> bool:
    """
    Validate timezone against IANA timezone database.

    Checks if the provided timezone string is a valid IANA timezone
    identifier. Uses Python's zoneinfo module which is based on the
    IANA timezone database (tzdata).

    Args:
        timezone: Timezone identifier (e.g., "America/New_York", "UTC")

    Returns:
        bool: True if valid IANA timezone, False otherwise

    Valid Examples:
        - "UTC"
        - "GMT"
        - "America/New_York"
        - "Europe/London"
        - "Asia/Tokyo"
        - "Australia/Sydney"

    Invalid Examples:
        - "PST" (abbreviation, not IANA identifier)
        - "EST" (abbreviation)
        - "New York" (wrong format)
        - "america/new_york" (wrong case)

    Example:
        >>> validate_timezone("America/New_York")
        True
        >>> validate_timezone("UTC")
        True
        >>> validate_timezone("PST")
        False
        >>> validate_timezone("Invalid/Zone")
        False

    Note:
        - Case-sensitive (must match IANA database exactly)
        - Use available_timezones() to get full list of valid zones
        - Rejects timezone abbreviations (PST, EST, etc.)
    """
    if not timezone or not isinstance(timezone, str):
        return False

    # Check if timezone exists in IANA database
    # This is more efficient than trying to create a ZoneInfo object
    return timezone in available_timezones()


def validate_tax_jurisdiction(jurisdiction: str) -> bool:
    """
    Validate tax jurisdiction code.

    Checks if the provided jurisdiction is in the list of valid
    tax jurisdictions. Supports both country-level and state/province-level
    jurisdictions.

    Format:
        - Country level: "CC" (2-letter ISO 3166-1 alpha-2)
        - State/Province level: "CC-SS" (country-state with hyphen)

    Args:
        jurisdiction: Tax jurisdiction code

    Returns:
        bool: True if valid jurisdiction, False otherwise

    Valid Examples:
        - "US" (United States)
        - "CA" (Canada)
        - "GB" (United Kingdom)
        - "US-CA" (California, USA)
        - "US-NY" (New York, USA)
        - "CA-ON" (Ontario, Canada)
        - "AU-NSW" (New South Wales, Australia)

    Invalid Examples:
        - "us" (lowercase)
        - "USA" (3 letters)
        - "US_CA" (underscore instead of hyphen)
        - "US/CA" (slash instead of hyphen)
        - "XX" (non-existent country)

    Example:
        >>> validate_tax_jurisdiction("US")
        True
        >>> validate_tax_jurisdiction("US-CA")
        True
        >>> validate_tax_jurisdiction("us")
        False
        >>> validate_tax_jurisdiction("XX-YY")
        False

    Note:
        - Case-sensitive (must be uppercase)
        - Hyphen separator for state/province codes
        - List is comprehensive but not exhaustive
        - Add new jurisdictions to VALID_TAX_JURISDICTIONS set as needed
    """
    if not jurisdiction or not isinstance(jurisdiction, str):
        return False

    return jurisdiction in VALID_TAX_JURISDICTIONS


def get_available_timezones() -> Set[str]:
    """
    Get set of all available IANA timezones.

    Returns the complete set of valid timezone identifiers from
    the IANA timezone database.

    Returns:
        Set[str]: Set of valid timezone identifiers

    Example:
        >>> timezones = get_available_timezones()
        >>> "America/New_York" in timezones
        True
        >>> len(timezones) > 500  # Hundreds of valid timezones
        True

    Note:
        - This is a cached call (zoneinfo caches available_timezones)
        - Use for populating dropdowns or validation lists
        - Contains all IANA timezone database entries
    """
    return available_timezones()


def get_available_tax_jurisdictions() -> Set[str]:
    """
    Get set of all available tax jurisdictions.

    Returns the complete set of valid tax jurisdiction codes.

    Returns:
        Set[str]: Set of valid tax jurisdiction codes

    Example:
        >>> jurisdictions = get_available_tax_jurisdictions()
        >>> "US" in jurisdictions
        True
        >>> "US-CA" in jurisdictions
        True
        >>> len(jurisdictions) > 50  # Many jurisdictions supported
        True

    Note:
        - Returns a copy to prevent external modification
        - Use for populating dropdowns or validation lists
        - Includes both country and state/province level codes
    """
    return VALID_TAX_JURISDICTIONS.copy()
