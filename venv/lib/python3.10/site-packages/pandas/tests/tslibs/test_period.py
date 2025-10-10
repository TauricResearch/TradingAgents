import numpy as np
import pytest

from pandas._libs.tslibs import (
    iNaT,
    to_offset,
)
from pandas._libs.tslibs.period import (
    extract_ordinals,
    get_period_field_arr,
    period_asfreq,
    period_ordinal,
)

import pandas._testing as tm


def get_freq_code(freqstr: str) -> int:
    off = to_offset(freqstr, is_period=True)
    # error: "BaseOffset" has no attribute "_period_dtype_code"
    code = off._period_dtype_code  # type: ignore[attr-defined]
    return code


@pytest.mark.parametrize(
    "freq1,freq2,expected",
    [
        ("D", "h", 24),
        ("D", "min", 1440),
        ("D", "s", 86400),
        ("D", "ms", 86400000),
        ("D", "us", 86400000000),
        ("D", "ns", 86400000000000),
        ("h", "min", 60),
        ("h", "s", 3600),
        ("h", "ms", 3600000),
        ("h", "us", 3600000000),
        ("h", "ns", 3600000000000),
        ("min", "s", 60),
        ("min", "ms", 60000),
        ("min", "us", 60000000),
        ("min", "ns", 60000000000),
        ("s", "ms", 1000),
        ("s", "us", 1000000),
        ("s", "ns", 1000000000),
        ("ms", "us", 1000),
        ("ms", "ns", 1000000),
        ("us", "ns", 1000),
    ],
)
def test_intra_day_conversion_factors(freq1, freq2, expected):
    assert (
        period_asfreq(1, get_freq_code(freq1), get_freq_code(freq2), False) == expected
    )


@pytest.mark.parametrize(
    "freq,expected", [("Y", 0), ("M", 0), ("W", 1), ("D", 0), ("B", 0)]
)
def test_period_ordinal_start_values(freq, expected):
    # information for Jan. 1, 1970.
    assert period_ordinal(1970, 1, 1, 0, 0, 0, 0, 0, get_freq_code(freq)) == expected


@pytest.mark.parametrize(
    "dt,expected",
    [
        ((1970, 1, 4, 0, 0, 0, 0, 0), 1),
        ((1970, 1, 5, 0, 0, 0, 0, 0), 2),
        ((2013, 10, 6, 0, 0, 0, 0, 0), 2284),
        ((2013, 10, 7, 0, 0, 0, 0, 0), 2285),
    ],
)
def test_period_ordinal_week(dt, expected):
    args = dt + (get_freq_code("W"),)
    assert period_ordinal(*args) == expected


@pytest.mark.parametrize(
    "day,expected",
    [
        # Thursday (Oct. 3, 2013).
        (3, 11415),
        # Friday (Oct. 4, 2013).
        (4, 11416),
        # Saturday (Oct. 5, 2013).
        (5, 11417),
        # Sunday (Oct. 6, 2013).
        (6, 11417),
        # Monday (Oct. 7, 2013).
        (7, 11417),
        # Tuesday (Oct. 8, 2013).
        (8, 11418),
    ],
)
def test_period_ordinal_business_day(day, expected):
    # 5000 is PeriodDtypeCode for BusinessDay
    args = (2013, 10, day, 0, 0, 0, 0, 0, 5000)
    assert period_ordinal(*args) == expected


class TestExtractOrdinals:
    def test_extract_ordinals_raises(self):
        # with non-object, make sure we raise TypeError, not segfault
        arr = np.arange(5)
        freq = to_offset("D")
        with pytest.raises(TypeError, match="values must be object-dtype"):
            extract_ordinals(arr, freq)

    def test_extract_ordinals_2d(self):
        freq = to_offset("D")
        arr = np.empty(10, dtype=object)
        arr[:] = iNaT

        res = extract_ordinals(arr, freq)
        res2 = extract_ordinals(arr.reshape(5, 2), freq)
        tm.assert_numpy_array_equal(res, res2.reshape(-1))


def test_get_period_field_array_raises_on_out_of_range():
    msg = "Buffer dtype mismatch, expected 'const int64_t' but got 'double'"
    with pytest.raises(ValueError, match=msg):
        get_period_field_arr(-1, np.empty(1), 0)
