"""Property-based and unit tests for Alpha Vantage look-ahead bias date filter.

Feature: upstream-feature-adoption
Properties 4-5: Alpha Vantage Report Date Filter, None Passthrough
Validates: Requirements 2.1, 2.2, 2.3
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from tradingagents.dataflows.alpha_vantage_fundamentals import _filter_reports_by_date

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_DATE_STR = st.dates(
    min_value=__import__("datetime").date(2010, 1, 1),
    max_value=__import__("datetime").date(2026, 12, 31),
).map(lambda d: d.strftime("%Y-%m-%d"))


@st.composite
def alpha_vantage_response(draw):
    """Generate a dict mimicking Alpha Vantage report response."""
    n_annual = draw(st.integers(min_value=0, max_value=10))
    n_quarterly = draw(st.integers(min_value=0, max_value=20))

    annual_reports = [
        {"fiscalDateEnding": draw(_DATE_STR), "totalAssets": "1000000"} for _ in range(n_annual)
    ]
    quarterly_reports = [
        {"fiscalDateEnding": draw(_DATE_STR), "totalAssets": "500000"} for _ in range(n_quarterly)
    ]

    return {"annualReports": annual_reports, "quarterlyReports": quarterly_reports}


# ---------------------------------------------------------------------------
# Property 4: Alpha Vantage Report Date Filter
# All remaining reports have fiscalDateEnding <= curr_date
# ---------------------------------------------------------------------------


@given(response=alpha_vantage_response(), curr_date=_DATE_STR)
@settings(max_examples=100)
def test_property_4_all_reports_on_or_before_curr_date(response, curr_date):
    """Property 4: After filtering, every report has fiscalDateEnding <= curr_date."""
    result = _filter_reports_by_date(response, curr_date)
    for key in ("annualReports", "quarterlyReports"):
        if key in result:
            for report in result[key]:
                assert report["fiscalDateEnding"] <= curr_date


# ---------------------------------------------------------------------------
# Property 5: Alpha Vantage None Passthrough
# filter(result, None) returns identical dict
# ---------------------------------------------------------------------------


@given(response=alpha_vantage_response())
@settings(max_examples=100)
def test_property_5_none_passthrough(response):
    """Property 5: Passing None as curr_date returns the dict unchanged."""
    import copy

    original = copy.deepcopy(response)
    result = _filter_reports_by_date(response, None)
    assert result == original


# ---------------------------------------------------------------------------
# Unit tests: edge cases
# ---------------------------------------------------------------------------


def test_string_input_passthrough():
    """Error string input is returned unchanged."""
    error_str = "Error: API rate limit exceeded"
    result = _filter_reports_by_date(error_str, "2025-01-01")
    assert result == error_str


def test_all_reports_after_curr_date():
    """All reports after curr_date returns empty arrays."""
    response = {
        "annualReports": [
            {"fiscalDateEnding": "2026-12-31", "totalAssets": "1000"},
            {"fiscalDateEnding": "2025-12-31", "totalAssets": "900"},
        ],
        "quarterlyReports": [
            {"fiscalDateEnding": "2025-06-30", "totalAssets": "800"},
        ],
    }
    result = _filter_reports_by_date(response, "2024-01-01")
    assert result["annualReports"] == []
    assert result["quarterlyReports"] == []


def test_missing_report_keys():
    """Dict without report keys is returned unchanged."""
    response = {"Symbol": "AAPL", "Description": "Apple Inc."}
    result = _filter_reports_by_date(response, "2025-01-01")
    assert result == response


def test_partial_filtering():
    """Only reports after curr_date are removed."""
    response = {
        "annualReports": [
            {"fiscalDateEnding": "2024-12-31", "totalAssets": "1000"},
            {"fiscalDateEnding": "2025-12-31", "totalAssets": "1100"},
        ],
    }
    result = _filter_reports_by_date(response, "2025-06-01")
    assert len(result["annualReports"]) == 1
    assert result["annualReports"][0]["fiscalDateEnding"] == "2024-12-31"
