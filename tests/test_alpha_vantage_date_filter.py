"""Tests for _filter_reports_by_date in alpha_vantage_fundamentals.

Feature: upstream-feature-adoption, Properties 4-5: Alpha Vantage Report Date Filter
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tradingagents.dataflows.alpha_vantage_fundamentals import _filter_reports_by_date

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate valid YYYY-MM-DD date strings
_date_strategy = st.dates().map(lambda d: d.isoformat())

# Generate a single report entry with a valid fiscalDateEnding
_report_entry = st.fixed_dictionaries(
    {"fiscalDateEnding": _date_strategy, "totalAssets": st.integers(min_value=0)}
)

# Generate a dict resembling an Alpha Vantage response
_av_response = st.fixed_dictionaries(
    {
        "annualReports": st.lists(_report_entry, min_size=0, max_size=10),
        "quarterlyReports": st.lists(_report_entry, min_size=0, max_size=10),
    }
)


# ---------------------------------------------------------------------------
# Property 4: Alpha Vantage Report Date Filter Correctness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(result=_av_response, curr_date=_date_strategy)
def test_prop4_all_remaining_reports_on_or_before_curr_date(result, curr_date):
    """After filtering, every remaining report has fiscalDateEnding <= curr_date."""
    # Feature: upstream-feature-adoption, Property 4: Alpha Vantage Report Date Filter
    result_copy = copy.deepcopy(result)
    filtered = _filter_reports_by_date(result_copy, curr_date)

    for key in ("annualReports", "quarterlyReports"):
        for report in filtered.get(key, []):
            assert report["fiscalDateEnding"] <= curr_date


# ---------------------------------------------------------------------------
# Property 5: Alpha Vantage None Passthrough
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(result=_av_response)
def test_prop5_none_passthrough_returns_identical(result):
    """filter(result, None) returns a dict identical to the input."""
    # Feature: upstream-feature-adoption, Property 5: Alpha Vantage None Passthrough
    result_copy = copy.deepcopy(result)
    filtered = _filter_reports_by_date(result_copy, None)
    assert filtered == result


# ---------------------------------------------------------------------------
# Unit: Invalid curr_date raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "invalid_date",
    [
        "2025-99-99",  # Invalid month/day
        "2025-13-01",  # Month > 12
        "2025-02-30",  # Feb 30 doesn't exist
        "not-a-date",
        "",
        "2025/01/01",  # Wrong separator
        "20250101",  # No separators (not YYYY-MM-DD)
    ],
)
def test_invalid_curr_date_raises_valueerror(invalid_date):
    """Invalid calendar dates raise ValueError, not silently pass."""
    result = {"annualReports": [{"fiscalDateEnding": "2025-01-01"}]}
    with pytest.raises(ValueError, match="curr_date must be"):
        _filter_reports_by_date(result, invalid_date)


# ---------------------------------------------------------------------------
# Unit: Error string passthrough
# ---------------------------------------------------------------------------


def test_error_string_passthrough():
    """When result is a string (API error), it passes through unchanged."""
    error_msg = "Error: API rate limit exceeded"
    assert _filter_reports_by_date(error_msg, "2025-01-01") == error_msg


def test_error_string_passthrough_none_date():
    """String result with None curr_date passes through."""
    error_msg = "Error: Invalid API key"
    assert _filter_reports_by_date(error_msg, None) == error_msg


# ---------------------------------------------------------------------------
# Unit: All reports after curr_date returns empty arrays
# ---------------------------------------------------------------------------


def test_all_reports_after_curr_date():
    """When all reports are after curr_date, arrays are empty."""
    result = {
        "annualReports": [
            {"fiscalDateEnding": "2026-12-31"},
            {"fiscalDateEnding": "2025-12-31"},
        ],
        "quarterlyReports": [
            {"fiscalDateEnding": "2025-06-30"},
            {"fiscalDateEnding": "2025-03-31"},
        ],
    }
    filtered = _filter_reports_by_date(result, "2024-01-01")
    assert filtered["annualReports"] == []
    assert filtered["quarterlyReports"] == []


# ---------------------------------------------------------------------------
# Unit: Missing report keys in dict
# ---------------------------------------------------------------------------


def test_missing_report_keys():
    """Dict without annualReports/quarterlyReports keys is returned unchanged."""
    result = {"symbol": "AAPL", "someOtherKey": "value"}
    filtered = _filter_reports_by_date(result, "2025-06-01")
    assert filtered == {"symbol": "AAPL", "someOtherKey": "value"}


def test_partial_report_keys():
    """Dict with only one report key filters that key correctly."""
    result = {
        "annualReports": [
            {"fiscalDateEnding": "2024-12-31"},
            {"fiscalDateEnding": "2025-12-31"},
        ],
    }
    filtered = _filter_reports_by_date(result, "2025-01-01")
    assert filtered["annualReports"] == [{"fiscalDateEnding": "2024-12-31"}]
    assert "quarterlyReports" not in filtered


# ---------------------------------------------------------------------------
# Unit: curr_date after all data (no-op filter)
# ---------------------------------------------------------------------------


def test_curr_date_after_all_data():
    """When curr_date is after all reports, all reports are retained."""
    result = {
        "annualReports": [
            {"fiscalDateEnding": "2023-12-31"},
            {"fiscalDateEnding": "2022-12-31"},
        ],
        "quarterlyReports": [
            {"fiscalDateEnding": "2024-03-31"},
        ],
    }
    filtered = _filter_reports_by_date(result, "2030-12-31")
    assert len(filtered["annualReports"]) == 2
    assert len(filtered["quarterlyReports"]) == 1
