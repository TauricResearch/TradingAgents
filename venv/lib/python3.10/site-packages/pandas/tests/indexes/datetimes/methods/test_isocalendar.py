from pandas import (
    DataFrame,
    DatetimeIndex,
    date_range,
)
import pandas._testing as tm


def test_isocalendar_returns_correct_values_close_to_new_year_with_tz():
    # GH#6538: Check that DatetimeIndex and its TimeStamp elements
    # return the same weekofyear accessor close to new year w/ tz
    dates = ["2013/12/29", "2013/12/30", "2013/12/31"]
    dates = DatetimeIndex(dates, tz="Europe/Brussels")
    result = dates.isocalendar()
    expected_data_frame = DataFrame(
        [[2013, 52, 7], [2014, 1, 1], [2014, 1, 2]],
        columns=["year", "week", "day"],
        index=dates,
        dtype="UInt32",
    )
    tm.assert_frame_equal(result, expected_data_frame)


def test_dti_timestamp_isocalendar_fields():
    idx = date_range("2020-01-01", periods=10)
    expected = tuple(idx.isocalendar().iloc[-1].to_list())
    result = idx[-1].isocalendar()
    assert result == expected
