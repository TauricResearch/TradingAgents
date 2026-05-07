from datetime import datetime
import inspect

from tradingagents.dataflows.utils import get_next_weekday


def test_get_next_weekday_returns_datetime_for_string_weekday():
    result = get_next_weekday("2026-05-05")

    assert result == datetime(2026, 5, 5)
    assert isinstance(result, datetime)


def test_get_next_weekday_moves_string_weekend_to_monday():
    result = get_next_weekday("2026-05-09")

    assert result == datetime(2026, 5, 11)


def test_get_next_weekday_contract_is_annotated_as_datetime_return():
    signature = inspect.signature(get_next_weekday)

    assert signature.return_annotation is datetime
