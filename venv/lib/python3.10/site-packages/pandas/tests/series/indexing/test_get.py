import numpy as np
import pytest

import pandas as pd
from pandas import (
    DatetimeIndex,
    Index,
    Series,
    date_range,
)
import pandas._testing as tm


def test_get():
    # GH 6383
    s = Series(
        np.array(
            [
                43,
                48,
                60,
                48,
                50,
                51,
                50,
                45,
                57,
                48,
                56,
                45,
                51,
                39,
                55,
                43,
                54,
                52,
                51,
                54,
            ]
        )
    )

    result = s.get(25, 0)
    expected = 0
    assert result == expected

    s = Series(
        np.array(
            [
                43,
                48,
                60,
                48,
                50,
                51,
                50,
                45,
                57,
                48,
                56,
                45,
                51,
                39,
                55,
                43,
                54,
                52,
                51,
                54,
            ]
        ),
        index=Index(
            [
                25.0,
                36.0,
                49.0,
                64.0,
                81.0,
                100.0,
                121.0,
                144.0,
                169.0,
                196.0,
                1225.0,
                1296.0,
                1369.0,
                1444.0,
                1521.0,
                1600.0,
                1681.0,
                1764.0,
                1849.0,
                1936.0,
            ],
            dtype=np.float64,
        ),
    )

    result = s.get(25, 0)
    expected = 43
    assert result == expected

    # GH 7407
    # with a boolean accessor
    df = pd.DataFrame({"i": [0] * 3, "b": [False] * 3})
    vc = df.i.value_counts()
    result = vc.get(99, default="Missing")
    assert result == "Missing"

    vc = df.b.value_counts()
    result = vc.get(False, default="Missing")
    assert result == 3

    result = vc.get(True, default="Missing")
    assert result == "Missing"


def test_get_nan(float_numpy_dtype):
    # GH 8569
    s = Index(range(10), dtype=float_numpy_dtype).to_series()
    assert s.get(np.nan) is None
    assert s.get(np.nan, default="Missing") == "Missing"


def test_get_nan_multiple(float_numpy_dtype):
    # GH 8569
    # ensure that fixing "test_get_nan" above hasn't broken get
    # with multiple elements
    s = Index(range(10), dtype=float_numpy_dtype).to_series()

    idx = [2, 30]
    assert s.get(idx) is None

    idx = [2, np.nan]
    assert s.get(idx) is None

    # GH 17295 - all missing keys
    idx = [20, 30]
    assert s.get(idx) is None

    idx = [np.nan, np.nan]
    assert s.get(idx) is None


def test_get_with_default():
    # GH#7725
    d0 = ["a", "b", "c", "d"]
    d1 = np.arange(4, dtype="int64")

    for data, index in ((d0, d1), (d1, d0)):
        s = Series(data, index=index)
        for i, d in zip(index, data):
            assert s.get(i) == d
            assert s.get(i, d) == d
            assert s.get(i, "z") == d

            assert s.get("e", "z") == "z"
            assert s.get("e", "e") == "e"

            msg = "Series.__getitem__ treating keys as positions is deprecated"
            warn = None
            if index is d0:
                warn = FutureWarning
            with tm.assert_produces_warning(warn, match=msg):
                assert s.get(10, "z") == "z"
                assert s.get(10, 10) == 10


@pytest.mark.parametrize(
    "arr",
    [
        np.random.default_rng(2).standard_normal(10),
        DatetimeIndex(date_range("2020-01-01", periods=10), name="a").tz_localize(
            tz="US/Eastern"
        ),
    ],
)
def test_get_with_ea(arr):
    # GH#21260
    ser = Series(arr, index=[2 * i for i in range(len(arr))])
    assert ser.get(4) == ser.iloc[2]

    result = ser.get([4, 6])
    expected = ser.iloc[[2, 3]]
    tm.assert_series_equal(result, expected)

    result = ser.get(slice(2))
    expected = ser.iloc[[0, 1]]
    tm.assert_series_equal(result, expected)

    assert ser.get(-1) is None
    assert ser.get(ser.index.max() + 1) is None

    ser = Series(arr[:6], index=list("abcdef"))
    assert ser.get("c") == ser.iloc[2]

    result = ser.get(slice("b", "d"))
    expected = ser.iloc[[1, 2, 3]]
    tm.assert_series_equal(result, expected)

    result = ser.get("Z")
    assert result is None

    msg = "Series.__getitem__ treating keys as positions is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        assert ser.get(4) == ser.iloc[4]
    with tm.assert_produces_warning(FutureWarning, match=msg):
        assert ser.get(-1) == ser.iloc[-1]
    with tm.assert_produces_warning(FutureWarning, match=msg):
        assert ser.get(len(ser)) is None

    # GH#21257
    ser = Series(arr)
    ser2 = ser[::2]
    assert ser2.get(1) is None


def test_getitem_get(string_series, object_series):
    msg = "Series.__getitem__ treating keys as positions is deprecated"

    for obj in [string_series, object_series]:
        idx = obj.index[5]

        assert obj[idx] == obj.get(idx)
        assert obj[idx] == obj.iloc[5]

    with tm.assert_produces_warning(FutureWarning, match=msg):
        assert string_series.get(-1) == string_series.get(string_series.index[-1])
    assert string_series.iloc[5] == string_series.get(string_series.index[5])


def test_get_none():
    # GH#5652
    s1 = Series(dtype=object)
    s2 = Series(dtype=object, index=list("abc"))
    for s in [s1, s2]:
        result = s.get(None)
        assert result is None
