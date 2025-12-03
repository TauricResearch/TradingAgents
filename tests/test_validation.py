import pytest
from datetime import date, datetime, timedelta

from tradingagents.validation import (
    ValidationError,
    TickerValidationError,
    DateValidationError,
    validate_ticker,
    validate_tickers,
    parse_date,
    validate_date,
    validate_date_range,
    format_date,
    is_valid_ticker,
    is_valid_date,
    is_trading_day,
    get_previous_trading_day,
    get_next_trading_day,
)


class TestValidateTicker:
    def test_valid_simple_ticker(self):
        assert validate_ticker("AAPL") == "AAPL"
        assert validate_ticker("A") == "A"
        assert validate_ticker("GOOGL") == "GOOGL"

    def test_valid_ticker_lowercase_converted(self):
        assert validate_ticker("aapl") == "AAPL"
        assert validate_ticker("Msft") == "MSFT"

    def test_valid_ticker_with_whitespace(self):
        assert validate_ticker("  AAPL  ") == "AAPL"
        assert validate_ticker("\tTSLA\n") == "TSLA"

    def test_valid_ticker_with_class_indicator(self):
        assert validate_ticker("BRK-B") == "BRK-B"
        assert validate_ticker("BRK-A") == "BRK-A"
        assert validate_ticker("BRK.B") == "BRK.B"

    def test_invalid_ticker_none(self):
        with pytest.raises(TickerValidationError, match="cannot be None"):
            validate_ticker(None)

    def test_invalid_ticker_none_allowed(self):
        assert validate_ticker(None, allow_empty=True) == ""

    def test_invalid_ticker_empty(self):
        with pytest.raises(TickerValidationError, match="cannot be empty"):
            validate_ticker("")

    def test_invalid_ticker_empty_allowed(self):
        assert validate_ticker("", allow_empty=True) == ""

    def test_invalid_ticker_wrong_type(self):
        with pytest.raises(TickerValidationError, match="must be a string"):
            validate_ticker(123)

    def test_invalid_ticker_too_long(self):
        with pytest.raises(TickerValidationError, match="too long"):
            validate_ticker("VERYLONGTICKER")

    def test_invalid_ticker_format(self):
        with pytest.raises(TickerValidationError, match="Invalid ticker format"):
            validate_ticker("AAPL123")

        with pytest.raises(TickerValidationError, match="Invalid ticker format"):
            validate_ticker("AA-PL-B")

        with pytest.raises(TickerValidationError, match="Invalid ticker format"):
            validate_ticker("A@PL")


class TestValidateTickers:
    def test_valid_tickers_list(self):
        result = validate_tickers(["AAPL", "MSFT", "GOOGL"])
        assert result == ["AAPL", "MSFT", "GOOGL"]

    def test_valid_tickers_lowercase_converted(self):
        result = validate_tickers(["aapl", "msft"])
        assert result == ["AAPL", "MSFT"]

    def test_valid_tickers_tuple(self):
        result = validate_tickers(("AAPL", "MSFT"))
        assert result == ["AAPL", "MSFT"]

    def test_invalid_tickers_none(self):
        with pytest.raises(TickerValidationError, match="cannot be None"):
            validate_tickers(None)

    def test_invalid_tickers_none_allowed(self):
        assert validate_tickers(None, allow_empty_list=True) == []

    def test_invalid_tickers_empty_list(self):
        with pytest.raises(TickerValidationError, match="cannot be empty"):
            validate_tickers([])

    def test_invalid_tickers_empty_list_allowed(self):
        assert validate_tickers([], allow_empty_list=True) == []

    def test_invalid_tickers_wrong_type(self):
        with pytest.raises(TickerValidationError, match="must be a list"):
            validate_tickers("AAPL")

    def test_invalid_tickers_contains_invalid(self):
        with pytest.raises(TickerValidationError, match="Invalid tickers"):
            validate_tickers(["AAPL", "INVALID123", "MSFT"])


class TestParseDate:
    def test_parse_date_string_default_format(self):
        result = parse_date("2024-01-15")
        assert result == date(2024, 1, 15)

    def test_parse_date_string_various_formats(self):
        assert parse_date("2024/01/15") == date(2024, 1, 15)
        assert parse_date("01/15/2024") == date(2024, 1, 15)
        assert parse_date("20240115") == date(2024, 1, 15)

    def test_parse_date_from_date(self):
        d = date(2024, 1, 15)
        assert parse_date(d) == d

    def test_parse_date_from_datetime(self):
        dt = datetime(2024, 1, 15, 10, 30)
        assert parse_date(dt) == date(2024, 1, 15)

    def test_parse_date_none(self):
        assert parse_date(None) is None

    def test_parse_date_empty_string(self):
        assert parse_date("") is None
        assert parse_date("   ") is None

    def test_parse_date_invalid_format(self):
        with pytest.raises(DateValidationError, match="Could not parse date"):
            parse_date("not-a-date")

    def test_parse_date_invalid_type(self):
        with pytest.raises(DateValidationError, match="must be string"):
            parse_date(123)


class TestValidateDate:
    def test_validate_date_valid(self):
        result = validate_date("2024-01-15")
        assert result == date(2024, 1, 15)

    def test_validate_date_none_not_allowed(self):
        with pytest.raises(DateValidationError, match="cannot be None"):
            validate_date(None)

    def test_validate_date_none_allowed(self):
        assert validate_date(None, allow_none=True) is None

    def test_validate_date_before_min(self):
        with pytest.raises(DateValidationError, match="before minimum"):
            validate_date("1960-01-01")

    def test_validate_date_custom_min(self):
        with pytest.raises(DateValidationError, match="before minimum"):
            validate_date("2020-01-01", min_date=date(2021, 1, 1))

    def test_validate_date_future_not_allowed(self):
        future = date.today() + timedelta(days=30)
        with pytest.raises(DateValidationError, match="in the future"):
            validate_date(future.strftime("%Y-%m-%d"), allow_future=False)

    def test_validate_date_future_allowed(self):
        future = date.today() + timedelta(days=30)
        result = validate_date(future.strftime("%Y-%m-%d"), allow_future=True)
        assert result == future

    def test_validate_date_after_max(self):
        far_future = date.today() + timedelta(days=500)
        with pytest.raises(DateValidationError, match="after maximum"):
            validate_date(far_future.strftime("%Y-%m-%d"))

    def test_validate_date_weekend_not_allowed(self):
        saturday = date(2024, 1, 6)
        with pytest.raises(DateValidationError, match="Saturday"):
            validate_date(saturday, allow_weekend=False)

        sunday = date(2024, 1, 7)
        with pytest.raises(DateValidationError, match="Sunday"):
            validate_date(sunday, allow_weekend=False)

    def test_validate_date_weekend_allowed(self):
        saturday = date(2024, 1, 6)
        result = validate_date(saturday, allow_weekend=True)
        assert result == saturday


class TestValidateDateRange:
    def test_validate_date_range_valid(self):
        start, end = validate_date_range("2024-01-01", "2024-01-31")
        assert start == date(2024, 1, 1)
        assert end == date(2024, 1, 31)

    def test_validate_date_range_end_before_start(self):
        with pytest.raises(DateValidationError, match="must be on or after"):
            validate_date_range("2024-01-31", "2024-01-01")

    def test_validate_date_range_same_day(self):
        with pytest.raises(DateValidationError, match="must be after"):
            validate_date_range("2024-01-15", "2024-01-15")

    def test_validate_date_range_max_range(self):
        with pytest.raises(DateValidationError, match="exceeds maximum"):
            validate_date_range("2020-01-01", "2024-01-01", max_range_days=365)


class TestFormatDate:
    def test_format_date_default(self):
        result = format_date(date(2024, 1, 15))
        assert result == "2024-01-15"

    def test_format_date_custom_format(self):
        result = format_date(date(2024, 1, 15), output_format="%m/%d/%Y")
        assert result == "01/15/2024"

    def test_format_date_from_string(self):
        result = format_date("2024-01-15", output_format="%Y%m%d")
        assert result == "20240115"

    def test_format_date_none(self):
        with pytest.raises(DateValidationError, match="Cannot format None"):
            format_date(None)


class TestHelperFunctions:
    def test_is_valid_ticker(self):
        assert is_valid_ticker("AAPL") is True
        assert is_valid_ticker("INVALID123") is False
        assert is_valid_ticker("") is False

    def test_is_valid_date(self):
        assert is_valid_date("2024-01-15") is True
        assert is_valid_date("not-a-date") is False
        assert is_valid_date(date(2024, 1, 15)) is True

    def test_is_trading_day(self):
        assert is_trading_day(date(2024, 1, 15)) is True
        assert is_trading_day(date(2024, 1, 13)) is False
        assert is_trading_day("2024-01-15") is True

    def test_get_previous_trading_day_from_monday(self):
        monday = date(2024, 1, 15)
        result = get_previous_trading_day(monday)
        assert result == monday

    def test_get_previous_trading_day_from_saturday(self):
        saturday = date(2024, 1, 13)
        result = get_previous_trading_day(saturday)
        assert result == date(2024, 1, 12)

    def test_get_previous_trading_day_from_sunday(self):
        sunday = date(2024, 1, 14)
        result = get_previous_trading_day(sunday)
        assert result == date(2024, 1, 12)

    def test_get_next_trading_day_from_friday(self):
        friday = date(2024, 1, 12)
        result = get_next_trading_day(friday)
        assert result == friday

    def test_get_next_trading_day_from_saturday(self):
        saturday = date(2024, 1, 13)
        result = get_next_trading_day(saturday)
        assert result == date(2024, 1, 15)

    def test_get_next_trading_day_from_sunday(self):
        sunday = date(2024, 1, 14)
        result = get_next_trading_day(sunday)
        assert result == date(2024, 1, 15)
