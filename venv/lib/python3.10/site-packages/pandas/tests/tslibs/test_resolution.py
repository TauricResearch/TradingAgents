import numpy as np
import pytest
import pytz

from pandas._libs.tslibs import (
    Resolution,
    get_resolution,
)
from pandas._libs.tslibs.dtypes import NpyDatetimeUnit

import pandas._testing as tm


def test_get_resolution_nano():
    # don't return the fallback RESO_DAY
    arr = np.array([1], dtype=np.int64)
    res = get_resolution(arr)
    assert res == Resolution.RESO_NS


def test_get_resolution_non_nano_data():
    arr = np.array([1], dtype=np.int64)
    res = get_resolution(arr, None, NpyDatetimeUnit.NPY_FR_us.value)
    assert res == Resolution.RESO_US

    res = get_resolution(arr, pytz.UTC, NpyDatetimeUnit.NPY_FR_us.value)
    assert res == Resolution.RESO_US


@pytest.mark.parametrize(
    "freqstr,expected",
    [
        ("Y", "year"),
        ("Q", "quarter"),
        ("M", "month"),
        ("D", "day"),
        ("h", "hour"),
        ("min", "minute"),
        ("s", "second"),
        ("ms", "millisecond"),
        ("us", "microsecond"),
        ("ns", "nanosecond"),
    ],
)
def test_get_attrname_from_abbrev(freqstr, expected):
    reso = Resolution.get_reso_from_freqstr(freqstr)
    assert reso.attr_abbrev == freqstr
    assert reso.attrname == expected


@pytest.mark.parametrize("freq", ["A", "H", "T", "S", "L", "U", "N"])
def test_units_A_H_T_S_L_U_N_deprecated_from_attrname_to_abbrevs(freq):
    # GH#52536
    msg = f"'{freq}' is deprecated and will be removed in a future version."

    with tm.assert_produces_warning(FutureWarning, match=msg):
        Resolution.get_reso_from_freqstr(freq)
