import pytest

from pandas import (
    DatetimeIndex,
    date_range,
)
import pandas._testing as tm


@pytest.mark.parametrize("tz", [None, "Asia/Shanghai", "Europe/Berlin"])
@pytest.mark.parametrize("name", [None, "my_dti"])
@pytest.mark.parametrize("unit", ["ns", "us", "ms", "s"])
def test_dti_snap(name, tz, unit):
    dti = DatetimeIndex(
        [
            "1/1/2002",
            "1/2/2002",
            "1/3/2002",
            "1/4/2002",
            "1/5/2002",
            "1/6/2002",
            "1/7/2002",
        ],
        name=name,
        tz=tz,
        freq="D",
    )
    dti = dti.as_unit(unit)

    result = dti.snap(freq="W-MON")
    expected = date_range("12/31/2001", "1/7/2002", name=name, tz=tz, freq="w-mon")
    expected = expected.repeat([3, 4])
    expected = expected.as_unit(unit)
    tm.assert_index_equal(result, expected)
    assert result.tz == expected.tz
    assert result.freq is None
    assert expected.freq is None

    result = dti.snap(freq="B")

    expected = date_range("1/1/2002", "1/7/2002", name=name, tz=tz, freq="b")
    expected = expected.repeat([1, 1, 1, 2, 2])
    expected = expected.as_unit(unit)
    tm.assert_index_equal(result, expected)
    assert result.tz == expected.tz
    assert result.freq is None
    assert expected.freq is None
