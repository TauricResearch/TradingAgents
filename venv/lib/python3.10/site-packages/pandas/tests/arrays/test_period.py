import numpy as np
import pytest

from pandas._libs.tslibs import iNaT
from pandas._libs.tslibs.period import IncompatibleFrequency

from pandas.core.dtypes.base import _registry as registry
from pandas.core.dtypes.dtypes import PeriodDtype

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays import PeriodArray

# ----------------------------------------------------------------------------
# Dtype


def test_registered():
    assert PeriodDtype in registry.dtypes
    result = registry.find("Period[D]")
    expected = PeriodDtype("D")
    assert result == expected


# ----------------------------------------------------------------------------
# period_array


def test_asi8():
    result = PeriodArray._from_sequence(["2000", "2001", None], dtype="period[D]").asi8
    expected = np.array([10957, 11323, iNaT])
    tm.assert_numpy_array_equal(result, expected)


def test_take_raises():
    arr = PeriodArray._from_sequence(["2000", "2001"], dtype="period[D]")
    with pytest.raises(IncompatibleFrequency, match="freq"):
        arr.take([0, -1], allow_fill=True, fill_value=pd.Period("2000", freq="W"))

    msg = "value should be a 'Period' or 'NaT'. Got 'str' instead"
    with pytest.raises(TypeError, match=msg):
        arr.take([0, -1], allow_fill=True, fill_value="foo")


def test_fillna_raises():
    arr = PeriodArray._from_sequence(["2000", "2001", "2002"], dtype="period[D]")
    with pytest.raises(ValueError, match="Length"):
        arr.fillna(arr[:2])


def test_fillna_copies():
    arr = PeriodArray._from_sequence(["2000", "2001", "2002"], dtype="period[D]")
    result = arr.fillna(pd.Period("2000", "D"))
    assert result is not arr


# ----------------------------------------------------------------------------
# setitem


@pytest.mark.parametrize(
    "key, value, expected",
    [
        ([0], pd.Period("2000", "D"), [10957, 1, 2]),
        ([0], None, [iNaT, 1, 2]),
        ([0], np.nan, [iNaT, 1, 2]),
        ([0, 1, 2], pd.Period("2000", "D"), [10957] * 3),
        (
            [0, 1, 2],
            [pd.Period("2000", "D"), pd.Period("2001", "D"), pd.Period("2002", "D")],
            [10957, 11323, 11688],
        ),
    ],
)
def test_setitem(key, value, expected):
    arr = PeriodArray(np.arange(3), dtype="period[D]")
    expected = PeriodArray(expected, dtype="period[D]")
    arr[key] = value
    tm.assert_period_array_equal(arr, expected)


def test_setitem_raises_incompatible_freq():
    arr = PeriodArray(np.arange(3), dtype="period[D]")
    with pytest.raises(IncompatibleFrequency, match="freq"):
        arr[0] = pd.Period("2000", freq="Y")

    other = PeriodArray._from_sequence(["2000", "2001"], dtype="period[Y]")
    with pytest.raises(IncompatibleFrequency, match="freq"):
        arr[[0, 1]] = other


def test_setitem_raises_length():
    arr = PeriodArray(np.arange(3), dtype="period[D]")
    with pytest.raises(ValueError, match="length"):
        arr[[0, 1]] = [pd.Period("2000", freq="D")]


def test_setitem_raises_type():
    arr = PeriodArray(np.arange(3), dtype="period[D]")
    with pytest.raises(TypeError, match="int"):
        arr[0] = 1


# ----------------------------------------------------------------------------
# Ops


def test_sub_period():
    arr = PeriodArray._from_sequence(["2000", "2001"], dtype="period[D]")
    other = pd.Period("2000", freq="M")
    with pytest.raises(IncompatibleFrequency, match="freq"):
        arr - other


def test_sub_period_overflow():
    # GH#47538
    dti = pd.date_range("1677-09-22", periods=2, freq="D")
    pi = dti.to_period("ns")

    per = pd.Period._from_ordinal(10**14, pi.freq)

    with pytest.raises(OverflowError, match="Overflow in int64 addition"):
        pi - per

    with pytest.raises(OverflowError, match="Overflow in int64 addition"):
        per - pi


# ----------------------------------------------------------------------------
# Methods


@pytest.mark.parametrize(
    "other",
    [
        pd.Period("2000", freq="h"),
        PeriodArray._from_sequence(["2000", "2001", "2000"], dtype="period[h]"),
    ],
)
def test_where_different_freq_raises(other):
    # GH#45768 The PeriodArray method raises, the Series method coerces
    ser = pd.Series(
        PeriodArray._from_sequence(["2000", "2001", "2002"], dtype="period[D]")
    )
    cond = np.array([True, False, True])

    with pytest.raises(IncompatibleFrequency, match="freq"):
        ser.array._where(cond, other)

    res = ser.where(cond, other)
    expected = ser.astype(object).where(cond, other)
    tm.assert_series_equal(res, expected)


# ----------------------------------------------------------------------------
# Printing


def test_repr_small():
    arr = PeriodArray._from_sequence(["2000", "2001"], dtype="period[D]")
    result = str(arr)
    expected = (
        "<PeriodArray>\n['2000-01-01', '2001-01-01']\nLength: 2, dtype: period[D]"
    )
    assert result == expected


def test_repr_large():
    arr = PeriodArray._from_sequence(["2000", "2001"] * 500, dtype="period[D]")
    result = str(arr)
    expected = (
        "<PeriodArray>\n"
        "['2000-01-01', '2001-01-01', '2000-01-01', '2001-01-01', "
        "'2000-01-01',\n"
        " '2001-01-01', '2000-01-01', '2001-01-01', '2000-01-01', "
        "'2001-01-01',\n"
        " ...\n"
        " '2000-01-01', '2001-01-01', '2000-01-01', '2001-01-01', "
        "'2000-01-01',\n"
        " '2001-01-01', '2000-01-01', '2001-01-01', '2000-01-01', "
        "'2001-01-01']\n"
        "Length: 1000, dtype: period[D]"
    )
    assert result == expected
