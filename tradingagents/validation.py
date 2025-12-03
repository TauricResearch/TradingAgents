import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional, Union

logger = logging.getLogger(__name__)

TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}(-[A-Z]{1,2})?$")

TICKER_SPECIAL_PATTERN = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$")

MIN_VALID_DATE = date(1970, 1, 1)
MAX_FUTURE_DAYS = 365


class ValidationError(Exception):
    pass


class TickerValidationError(ValidationError):
    pass


class DateValidationError(ValidationError):
    pass


def validate_ticker(
    ticker: str,
    allow_empty: bool = False,
    check_format_only: bool = True,
) -> str:
    if ticker is None:
        if allow_empty:
            return ""
        raise TickerValidationError("Ticker cannot be None")

    if not isinstance(ticker, str):
        raise TickerValidationError(
            f"Ticker must be a string, got {type(ticker).__name__}"
        )

    ticker = ticker.strip().upper()

    if not ticker:
        if allow_empty:
            return ""
        raise TickerValidationError("Ticker cannot be empty")

    if len(ticker) > 10:
        raise TickerValidationError(
            f"Ticker '{ticker}' is too long (max 10 characters)"
        )

    if not TICKER_PATTERN.match(ticker) and not TICKER_SPECIAL_PATTERN.match(ticker):
        raise TickerValidationError(
            f"Invalid ticker format '{ticker}'. Must be 1-5 uppercase letters, "
            "optionally followed by a class indicator (e.g., BRK-B, BRK.A)"
        )

    return ticker


def validate_tickers(
    tickers: list[str],
    allow_empty_list: bool = False,
    check_format_only: bool = True,
) -> list[str]:
    if tickers is None:
        if allow_empty_list:
            return []
        raise TickerValidationError("Tickers list cannot be None")

    if not isinstance(tickers, (list, tuple)):
        raise TickerValidationError(
            f"Tickers must be a list, got {type(tickers).__name__}"
        )

    if not tickers:
        if allow_empty_list:
            return []
        raise TickerValidationError("Tickers list cannot be empty")

    validated = []
    errors = []

    for i, ticker in enumerate(tickers):
        try:
            validated.append(
                validate_ticker(ticker, check_format_only=check_format_only)
            )
        except TickerValidationError as e:
            errors.append(f"Index {i}: {e}")

    if errors:
        raise TickerValidationError(f"Invalid tickers: {'; '.join(errors)}")

    return validated


def parse_date(
    date_input: str | date | datetime | None,
    date_format: str = "%Y-%m-%d",
) -> date | None:
    if date_input is None:
        return None

    if isinstance(date_input, datetime):
        return date_input.date()

    if isinstance(date_input, date):
        return date_input

    if not isinstance(date_input, str):
        raise DateValidationError(
            f"Date must be string, date, or datetime, got {type(date_input).__name__}"
        )

    date_input = date_input.strip()

    if not date_input:
        return None

    formats_to_try = [
        date_format,
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y%m%d",
    ]

    for fmt in formats_to_try:
        try:
            return datetime.strptime(date_input, fmt).date()
        except ValueError:
            continue

    raise DateValidationError(
        f"Could not parse date '{date_input}'. Expected format: {date_format} "
        f"(e.g., {datetime.now().strftime(date_format)})"
    )


def validate_date(
    date_input: str | date | datetime | None,
    date_format: str = "%Y-%m-%d",
    allow_none: bool = False,
    min_date: date | None = None,
    max_date: date | None = None,
    allow_future: bool = True,
    allow_weekend: bool = True,
) -> date | None:
    if date_input is None:
        if allow_none:
            return None
        raise DateValidationError("Date cannot be None")

    parsed = parse_date(date_input, date_format)

    if parsed is None:
        if allow_none:
            return None
        raise DateValidationError("Date cannot be empty")

    effective_min = min_date or MIN_VALID_DATE
    if parsed < effective_min:
        raise DateValidationError(
            f"Date {parsed} is before minimum allowed date {effective_min}"
        )

    today = date.today()

    if not allow_future and parsed > today:
        raise DateValidationError(
            f"Date {parsed} is in the future. Future dates are not allowed."
        )

    effective_max = max_date or (today + timedelta(days=MAX_FUTURE_DAYS))
    if parsed > effective_max:
        raise DateValidationError(
            f"Date {parsed} is after maximum allowed date {effective_max}"
        )

    if not allow_weekend and parsed.weekday() >= 5:
        day_name = "Saturday" if parsed.weekday() == 5 else "Sunday"
        raise DateValidationError(
            f"Date {parsed} falls on a {day_name}. Weekend dates are not allowed."
        )

    return parsed


def validate_date_range(
    start_date: str | date | datetime,
    end_date: str | date | datetime,
    date_format: str = "%Y-%m-%d",
    min_date: date | None = None,
    max_date: date | None = None,
    allow_future: bool = True,
    max_range_days: int | None = None,
) -> tuple[date, date]:
    start = validate_date(
        start_date,
        date_format=date_format,
        allow_none=False,
        min_date=min_date,
        max_date=max_date,
        allow_future=allow_future,
    )

    end = validate_date(
        end_date,
        date_format=date_format,
        allow_none=False,
        min_date=min_date,
        max_date=max_date,
        allow_future=allow_future,
    )

    if end < start:
        raise DateValidationError(
            f"End date ({end}) must be on or after start date ({start})"
        )

    if end == start:
        raise DateValidationError(
            f"End date ({end}) must be after start date ({start})"
        )

    if max_range_days is not None:
        range_days = (end - start).days
        if range_days > max_range_days:
            raise DateValidationError(
                f"Date range of {range_days} days exceeds maximum of {max_range_days} days"
            )

    return start, end


def format_date(
    date_input: str | date | datetime,
    output_format: str = "%Y-%m-%d",
    input_format: str = "%Y-%m-%d",
) -> str:
    parsed = parse_date(date_input, input_format)
    if parsed is None:
        raise DateValidationError("Cannot format None date")
    return parsed.strftime(output_format)


def is_valid_ticker(ticker: str) -> bool:
    try:
        validate_ticker(ticker)
        return True
    except TickerValidationError:
        return False


def is_valid_date(
    date_input: str | date | datetime,
    date_format: str = "%Y-%m-%d",
) -> bool:
    try:
        validate_date(date_input, date_format=date_format)
        return True
    except DateValidationError:
        return False


def is_trading_day(check_date: str | date | datetime) -> bool:
    parsed = parse_date(check_date)
    if parsed is None:
        return False
    return parsed.weekday() < 5


def get_previous_trading_day(from_date: str | date | datetime | None = None) -> date:
    if from_date is None:
        check = date.today()
    else:
        check = parse_date(from_date)
        if check is None:
            check = date.today()

    while check.weekday() >= 5:
        check = check - timedelta(days=1)

    return check


def get_next_trading_day(from_date: str | date | datetime | None = None) -> date:
    if from_date is None:
        check = date.today()
    else:
        check = parse_date(from_date)
        if check is None:
            check = date.today()

    while check.weekday() >= 5:
        check = check + timedelta(days=1)

    return check
