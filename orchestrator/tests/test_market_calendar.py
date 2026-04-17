import json
from datetime import date

from orchestrator.market_calendar import get_market_holidays, is_non_trading_day, update_market_holidays


def test_is_non_trading_day_marks_a_share_holiday():
    assert is_non_trading_day('600519.SS', date(2024, 10, 2)) is True


def test_is_non_trading_day_marks_nyse_holiday():
    assert is_non_trading_day('AAPL', date(2024, 3, 29)) is True


def test_is_non_trading_day_leaves_regular_weekday_open():
    assert is_non_trading_day('AAPL', date(2024, 3, 28)) is False


def test_update_market_holidays_creates_maintainable_future_year_entry(tmp_path):
    data_path = tmp_path / "market_holidays.json"
    data_path.write_text(json.dumps({"a_share": {}}))

    update_market_holidays(
        market="a_share",
        year=2027,
        holiday_dates=["2027-02-10", "2027-02-11"],
        data_path=data_path,
    )

    assert get_market_holidays("a_share", 2027, data_path=data_path) == {
        date(2027, 2, 10),
        date(2027, 2, 11),
    }
    assert is_non_trading_day("600519.SS", date(2027, 2, 10)) is False
    assert is_non_trading_day("600519.SS", date(2027, 2, 10), data_path=data_path) is True
