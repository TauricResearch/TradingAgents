"""
Test suite for FRED API Data Retrieval Functions (fred.py).

This module tests:
1. get_interest_rates() - Federal funds rate retrieval
2. get_treasury_rates() - Treasury yield retrieval
3. get_money_supply() - M2 money supply retrieval
4. get_gdp() - GDP data retrieval
5. get_inflation() - CPI/inflation data retrieval
6. get_unemployment() - Unemployment rate retrieval
7. get_fred_series() - Generic FRED series retrieval

Test Coverage:
- Unit tests for each data function
- Default parameters and custom parameters
- Date range filtering
- Different series IDs and maturities
- Error handling (returns error strings, not exceptions)
- Cache integration
- Empty data scenarios
"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date

pytestmark = pytest.mark.unit


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_fred_request():
    """Mock _make_fred_request function."""
    with patch('tradingagents.dataflows.fred._make_fred_request') as mock_request:
        yield mock_request


@pytest.fixture
def sample_interest_rate_df():
    """Create sample interest rate DataFrame."""
    return pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=5, freq='D'),
        'value': [5.33, 5.35, 5.37, 5.39, 5.40],
    })


@pytest.fixture
def sample_treasury_rate_df():
    """Create sample treasury rate DataFrame."""
    return pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=5, freq='D'),
        'value': [4.25, 4.27, 4.29, 4.31, 4.33],
    })


@pytest.fixture
def sample_money_supply_df():
    """Create sample M2 money supply DataFrame (billions)."""
    return pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=5, freq='ME'),
        'value': [21000.0, 21050.0, 21100.0, 21150.0, 21200.0],
    })


@pytest.fixture
def sample_gdp_df():
    """Create sample GDP DataFrame (billions)."""
    return pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=4, freq='QE'),
        'value': [27000.0, 27200.0, 27400.0, 27600.0],
    })


@pytest.fixture
def sample_cpi_df():
    """Create sample CPI DataFrame."""
    return pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=5, freq='ME'),
        'value': [308.0, 309.0, 310.0, 311.0, 312.0],
    })


@pytest.fixture
def sample_unemployment_df():
    """Create sample unemployment rate DataFrame."""
    return pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=5, freq='ME'),
        'value': [3.7, 3.8, 3.9, 4.0, 4.1],
    })


# ============================================================================
# Test get_interest_rates()
# ============================================================================

class TestGetInterestRates:
    """Test federal funds rate retrieval."""

    def test_get_interest_rates_success_default(self, mock_fred_request, sample_interest_rate_df):
        """Test successful retrieval with default parameters (FEDFUNDS)."""
        from tradingagents.dataflows.fred import get_interest_rates

        mock_fred_request.return_value = sample_interest_rate_df

        result = get_interest_rates()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        assert 'date' in result.columns
        assert 'value' in result.columns
        mock_fred_request.assert_called_once_with('FEDFUNDS', start_date=None, end_date=None)

    def test_get_interest_rates_with_date_range(self, mock_fred_request, sample_interest_rate_df):
        """Test retrieval with custom date range."""
        from tradingagents.dataflows.fred import get_interest_rates

        mock_fred_request.return_value = sample_interest_rate_df

        result = get_interest_rates(start_date='2024-01-01', end_date='2024-12-31')

        mock_fred_request.assert_called_once_with('FEDFUNDS', start_date='2024-01-01', end_date='2024-12-31')

    def test_get_interest_rates_custom_series(self, mock_fred_request, sample_interest_rate_df):
        """Test retrieval with custom series ID."""
        from tradingagents.dataflows.fred import get_interest_rates

        mock_fred_request.return_value = sample_interest_rate_df

        result = get_interest_rates(series_id='DFF')

        mock_fred_request.assert_called_once_with('DFF', start_date=None, end_date=None)

    def test_get_interest_rates_returns_error_string_on_failure(self, mock_fred_request):
        """Test that errors return error string, not exception."""
        from tradingagents.dataflows.fred import get_interest_rates
        from tradingagents.dataflows.fred_common import FredRateLimitError

        mock_fred_request.side_effect = FredRateLimitError("Rate limit exceeded")

        result = get_interest_rates()

        assert isinstance(result, str)
        assert "error" in result.lower() or "failed" in result.lower()
        assert "rate limit" in result.lower()

    def test_get_interest_rates_empty_dataframe(self, mock_fred_request):
        """Test handling of empty DataFrame response."""
        from tradingagents.dataflows.fred import get_interest_rates

        mock_fred_request.return_value = pd.DataFrame()

        result = get_interest_rates()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_get_interest_rates_datetime_objects(self, mock_fred_request, sample_interest_rate_df):
        """Test retrieval with datetime objects instead of strings."""
        from tradingagents.dataflows.fred import get_interest_rates

        mock_fred_request.return_value = sample_interest_rate_df

        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)

        result = get_interest_rates(start_date=start, end_date=end)

        # Should convert to string format
        assert mock_fred_request.called


# ============================================================================
# Test get_treasury_rates()
# ============================================================================

class TestGetTreasuryRates:
    """Test treasury yield retrieval."""

    def test_get_treasury_rates_default_10y(self, mock_fred_request, sample_treasury_rate_df):
        """Test successful retrieval of 10-year treasury (default)."""
        from tradingagents.dataflows.fred import get_treasury_rates

        mock_fred_request.return_value = sample_treasury_rate_df

        result = get_treasury_rates()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        mock_fred_request.assert_called_once_with('DGS10', start_date=None, end_date=None)

    def test_get_treasury_rates_2y(self, mock_fred_request, sample_treasury_rate_df):
        """Test retrieval of 2-year treasury."""
        from tradingagents.dataflows.fred import get_treasury_rates

        mock_fred_request.return_value = sample_treasury_rate_df

        result = get_treasury_rates(maturity='2Y')

        mock_fred_request.assert_called_once_with('DGS2', start_date=None, end_date=None)

    def test_get_treasury_rates_5y(self, mock_fred_request, sample_treasury_rate_df):
        """Test retrieval of 5-year treasury."""
        from tradingagents.dataflows.fred import get_treasury_rates

        mock_fred_request.return_value = sample_treasury_rate_df

        result = get_treasury_rates(maturity='5Y')

        mock_fred_request.assert_called_once_with('DGS5', start_date=None, end_date=None)

    def test_get_treasury_rates_30y(self, mock_fred_request, sample_treasury_rate_df):
        """Test retrieval of 30-year treasury."""
        from tradingagents.dataflows.fred import get_treasury_rates

        mock_fred_request.return_value = sample_treasury_rate_df

        result = get_treasury_rates(maturity='30Y')

        mock_fred_request.assert_called_once_with('DGS30', start_date=None, end_date=None)

    def test_get_treasury_rates_invalid_maturity(self, mock_fred_request):
        """Test invalid maturity returns error string."""
        from tradingagents.dataflows.fred import get_treasury_rates

        result = get_treasury_rates(maturity='15Y')

        assert isinstance(result, str)
        assert "error" in result.lower() or "invalid" in result.lower()

    def test_get_treasury_rates_with_date_range(self, mock_fred_request, sample_treasury_rate_df):
        """Test retrieval with date range."""
        from tradingagents.dataflows.fred import get_treasury_rates

        mock_fred_request.return_value = sample_treasury_rate_df

        result = get_treasury_rates(maturity='10Y', start_date='2024-01-01', end_date='2024-12-31')

        mock_fred_request.assert_called_once_with('DGS10', start_date='2024-01-01', end_date='2024-12-31')

    def test_get_treasury_rates_returns_error_string_on_failure(self, mock_fred_request):
        """Test that errors return error string."""
        from tradingagents.dataflows.fred import get_treasury_rates
        from tradingagents.dataflows.fred_common import FredInvalidSeriesError

        mock_fred_request.side_effect = FredInvalidSeriesError("Invalid series")

        result = get_treasury_rates()

        assert isinstance(result, str)
        assert "error" in result.lower()


# ============================================================================
# Test get_money_supply()
# ============================================================================

class TestGetMoneySupply:
    """Test money supply (M2) retrieval."""

    def test_get_money_supply_default_m2(self, mock_fred_request, sample_money_supply_df):
        """Test successful M2 money supply retrieval (default)."""
        from tradingagents.dataflows.fred import get_money_supply

        mock_fred_request.return_value = sample_money_supply_df

        result = get_money_supply()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        mock_fred_request.assert_called_once_with('M2SL', start_date=None, end_date=None)

    def test_get_money_supply_m1(self, mock_fred_request, sample_money_supply_df):
        """Test M1 money supply retrieval."""
        from tradingagents.dataflows.fred import get_money_supply

        mock_fred_request.return_value = sample_money_supply_df

        result = get_money_supply(measure='M1')

        mock_fred_request.assert_called_once_with('M1SL', start_date=None, end_date=None)

    def test_get_money_supply_with_date_range(self, mock_fred_request, sample_money_supply_df):
        """Test money supply with date range."""
        from tradingagents.dataflows.fred import get_money_supply

        mock_fred_request.return_value = sample_money_supply_df

        result = get_money_supply(start_date='2020-01-01', end_date='2024-12-31')

        mock_fred_request.assert_called_once_with('M2SL', start_date='2020-01-01', end_date='2024-12-31')

    def test_get_money_supply_invalid_measure(self, mock_fred_request):
        """Test invalid measure returns error string."""
        from tradingagents.dataflows.fred import get_money_supply

        result = get_money_supply(measure='M5')

        assert isinstance(result, str)
        assert "error" in result.lower() or "invalid" in result.lower()

    def test_get_money_supply_returns_error_string_on_failure(self, mock_fred_request):
        """Test that errors return error string."""
        from tradingagents.dataflows.fred import get_money_supply

        mock_fred_request.side_effect = Exception("Network error")

        result = get_money_supply()

        assert isinstance(result, str)
        assert "error" in result.lower()


# ============================================================================
# Test get_gdp()
# ============================================================================

class TestGetGDP:
    """Test GDP data retrieval."""

    def test_get_gdp_default_quarterly(self, mock_fred_request, sample_gdp_df):
        """Test successful quarterly GDP retrieval (default)."""
        from tradingagents.dataflows.fred import get_gdp

        mock_fred_request.return_value = sample_gdp_df

        result = get_gdp()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 4
        mock_fred_request.assert_called_once_with('GDP', start_date=None, end_date=None)

    def test_get_gdp_annual(self, mock_fred_request, sample_gdp_df):
        """Test annual GDP retrieval."""
        from tradingagents.dataflows.fred import get_gdp

        mock_fred_request.return_value = sample_gdp_df

        result = get_gdp(frequency='annual')

        mock_fred_request.assert_called_once_with('GDPA', start_date=None, end_date=None)

    def test_get_gdp_real(self, mock_fred_request, sample_gdp_df):
        """Test real GDP retrieval."""
        from tradingagents.dataflows.fred import get_gdp

        mock_fred_request.return_value = sample_gdp_df

        result = get_gdp(frequency='real')

        mock_fred_request.assert_called_once_with('GDPC1', start_date=None, end_date=None)

    def test_get_gdp_with_date_range(self, mock_fred_request, sample_gdp_df):
        """Test GDP with date range."""
        from tradingagents.dataflows.fred import get_gdp

        mock_fred_request.return_value = sample_gdp_df

        result = get_gdp(start_date='2020-01-01', end_date='2024-12-31')

        mock_fred_request.assert_called_once_with('GDP', start_date='2020-01-01', end_date='2024-12-31')

    def test_get_gdp_invalid_frequency(self, mock_fred_request):
        """Test invalid frequency returns error string."""
        from tradingagents.dataflows.fred import get_gdp

        result = get_gdp(frequency='weekly')

        assert isinstance(result, str)
        assert "error" in result.lower() or "invalid" in result.lower()

    def test_get_gdp_returns_error_string_on_failure(self, mock_fred_request):
        """Test that errors return error string."""
        from tradingagents.dataflows.fred import get_gdp

        mock_fred_request.side_effect = Exception("API error")

        result = get_gdp()

        assert isinstance(result, str)
        assert "error" in result.lower()


# ============================================================================
# Test get_inflation()
# ============================================================================

class TestGetInflation:
    """Test inflation/CPI data retrieval."""

    def test_get_inflation_default_cpi(self, mock_fred_request, sample_cpi_df):
        """Test successful CPI retrieval (default)."""
        from tradingagents.dataflows.fred import get_inflation

        mock_fred_request.return_value = sample_cpi_df

        result = get_inflation()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        mock_fred_request.assert_called_once_with('CPIAUCSL', start_date=None, end_date=None)

    def test_get_inflation_core_cpi(self, mock_fred_request, sample_cpi_df):
        """Test core CPI retrieval (excluding food and energy)."""
        from tradingagents.dataflows.fred import get_inflation

        mock_fred_request.return_value = sample_cpi_df

        result = get_inflation(measure='CORE')

        mock_fred_request.assert_called_once_with('CPILFESL', start_date=None, end_date=None)

    def test_get_inflation_pce(self, mock_fred_request, sample_cpi_df):
        """Test PCE price index retrieval."""
        from tradingagents.dataflows.fred import get_inflation

        mock_fred_request.return_value = sample_cpi_df

        result = get_inflation(measure='PCE')

        mock_fred_request.assert_called_once_with('PCEPI', start_date=None, end_date=None)

    def test_get_inflation_with_date_range(self, mock_fred_request, sample_cpi_df):
        """Test inflation with date range."""
        from tradingagents.dataflows.fred import get_inflation

        mock_fred_request.return_value = sample_cpi_df

        result = get_inflation(start_date='2020-01-01', end_date='2024-12-31')

        mock_fred_request.assert_called_once_with('CPIAUCSL', start_date='2020-01-01', end_date='2024-12-31')

    def test_get_inflation_invalid_measure(self, mock_fred_request):
        """Test invalid measure returns error string."""
        from tradingagents.dataflows.fred import get_inflation

        result = get_inflation(measure='INVALID')

        assert isinstance(result, str)
        assert "error" in result.lower() or "invalid" in result.lower()

    def test_get_inflation_returns_error_string_on_failure(self, mock_fred_request):
        """Test that errors return error string."""
        from tradingagents.dataflows.fred import get_inflation

        mock_fred_request.side_effect = Exception("API error")

        result = get_inflation()

        assert isinstance(result, str)
        assert "error" in result.lower()


# ============================================================================
# Test get_unemployment()
# ============================================================================

class TestGetUnemployment:
    """Test unemployment rate retrieval."""

    def test_get_unemployment_default_unrate(self, mock_fred_request, sample_unemployment_df):
        """Test successful unemployment rate retrieval (default)."""
        from tradingagents.dataflows.fred import get_unemployment

        mock_fred_request.return_value = sample_unemployment_df

        result = get_unemployment()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        mock_fred_request.assert_called_once_with('UNRATE', start_date=None, end_date=None)

    def test_get_unemployment_custom_series(self, mock_fred_request, sample_unemployment_df):
        """Test unemployment with custom series ID."""
        from tradingagents.dataflows.fred import get_unemployment

        mock_fred_request.return_value = sample_unemployment_df

        result = get_unemployment(series_id='U6RATE')

        mock_fred_request.assert_called_once_with('U6RATE', start_date=None, end_date=None)

    def test_get_unemployment_with_date_range(self, mock_fred_request, sample_unemployment_df):
        """Test unemployment with date range."""
        from tradingagents.dataflows.fred import get_unemployment

        mock_fred_request.return_value = sample_unemployment_df

        result = get_unemployment(start_date='2020-01-01', end_date='2024-12-31')

        mock_fred_request.assert_called_once_with('UNRATE', start_date='2020-01-01', end_date='2024-12-31')

    def test_get_unemployment_returns_error_string_on_failure(self, mock_fred_request):
        """Test that errors return error string."""
        from tradingagents.dataflows.fred import get_unemployment

        mock_fred_request.side_effect = Exception("API error")

        result = get_unemployment()

        assert isinstance(result, str)
        assert "error" in result.lower()


# ============================================================================
# Test get_fred_series() - Generic Function
# ============================================================================

class TestGetFredSeries:
    """Test generic FRED series retrieval."""

    def test_get_fred_series_success(self, mock_fred_request, sample_interest_rate_df):
        """Test successful generic series retrieval."""
        from tradingagents.dataflows.fred import get_fred_series

        mock_fred_request.return_value = sample_interest_rate_df

        result = get_fred_series('FEDFUNDS')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        mock_fred_request.assert_called_once_with('FEDFUNDS', start_date=None, end_date=None)

    def test_get_fred_series_with_date_range(self, mock_fred_request, sample_interest_rate_df):
        """Test generic series with date range."""
        from tradingagents.dataflows.fred import get_fred_series

        mock_fred_request.return_value = sample_interest_rate_df

        result = get_fred_series('FEDFUNDS', start_date='2024-01-01', end_date='2024-12-31')

        mock_fred_request.assert_called_once_with('FEDFUNDS', start_date='2024-01-01', end_date='2024-12-31')

    def test_get_fred_series_custom_series_id(self, mock_fred_request, sample_interest_rate_df):
        """Test generic series with any custom series ID."""
        from tradingagents.dataflows.fred import get_fred_series

        mock_fred_request.return_value = sample_interest_rate_df

        result = get_fred_series('SP500')

        mock_fred_request.assert_called_once_with('SP500', start_date=None, end_date=None)

    def test_get_fred_series_returns_error_string_on_failure(self, mock_fred_request):
        """Test that errors return error string."""
        from tradingagents.dataflows.fred import get_fred_series

        mock_fred_request.side_effect = Exception("API error")

        result = get_fred_series('INVALID')

        assert isinstance(result, str)
        assert "error" in result.lower()

    def test_get_fred_series_invalid_series_id(self, mock_fred_request):
        """Test generic series with invalid series ID."""
        from tradingagents.dataflows.fred import get_fred_series
        from tradingagents.dataflows.fred_common import FredInvalidSeriesError

        mock_fred_request.side_effect = FredInvalidSeriesError("Series not found", series_id='INVALID')

        result = get_fred_series('INVALID')

        assert isinstance(result, str)
        assert "error" in result.lower()
        assert "INVALID" in result or "series" in result.lower()


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Test edge cases across all functions."""

    def test_all_functions_handle_none_dates(self, mock_fred_request, sample_interest_rate_df):
        """Test that all functions handle None dates properly."""
        from tradingagents.dataflows.fred import (
            get_interest_rates, get_treasury_rates, get_money_supply,
            get_gdp, get_inflation, get_unemployment, get_fred_series
        )

        mock_fred_request.return_value = sample_interest_rate_df

        # Should all succeed with None dates
        functions = [
            lambda: get_interest_rates(start_date=None, end_date=None),
            lambda: get_treasury_rates(start_date=None, end_date=None),
            lambda: get_money_supply(start_date=None, end_date=None),
            lambda: get_gdp(start_date=None, end_date=None),
            lambda: get_inflation(start_date=None, end_date=None),
            lambda: get_unemployment(start_date=None, end_date=None),
            lambda: get_fred_series('TEST', start_date=None, end_date=None),
        ]

        for func in functions:
            result = func()
            assert isinstance(result, pd.DataFrame)

    def test_all_functions_return_strings_on_error(self, mock_fred_request):
        """Test that all functions return error strings, not exceptions."""
        from tradingagents.dataflows.fred import (
            get_interest_rates, get_treasury_rates, get_money_supply,
            get_gdp, get_inflation, get_unemployment, get_fred_series
        )

        mock_fred_request.side_effect = Exception("Test error")

        functions = [
            get_interest_rates,
            get_treasury_rates,
            get_money_supply,
            get_gdp,
            get_inflation,
            get_unemployment,
            lambda: get_fred_series('TEST'),
        ]

        for func in functions:
            result = func()
            assert isinstance(result, str), f"{func.__name__} should return string on error"
            assert "error" in result.lower() or "failed" in result.lower()

    def test_empty_series_id_handled(self, mock_fred_request):
        """Test handling of empty series ID."""
        from tradingagents.dataflows.fred import get_fred_series

        result = get_fred_series('')

        assert isinstance(result, str)
        assert "error" in result.lower()
