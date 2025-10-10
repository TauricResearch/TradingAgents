import numpy as np
import pytest

from pandas.errors import DataError

from pandas.core.dtypes.common import pandas_dtype

from pandas import (
    NA,
    DataFrame,
    Series,
)
import pandas._testing as tm

# gh-12373 : rolling functions error on float32 data
# make sure rolling functions works for different dtypes
#
# further note that we are only checking rolling for fully dtype
# compliance (though both expanding and ewm inherit)


def get_dtype(dtype, coerce_int=None):
    if coerce_int is False and "int" in dtype:
        return None
    return pandas_dtype(dtype)


@pytest.fixture(
    params=[
        "object",
        "category",
        "int8",
        "int16",
        "int32",
        "int64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "float16",
        "float32",
        "float64",
        "m8[ns]",
        "M8[ns]",
        "datetime64[ns, UTC]",
    ]
)
def dtypes(request):
    """Dtypes for window tests"""
    return request.param


@pytest.mark.parametrize(
    "method, data, expected_data, coerce_int, min_periods",
    [
        ("count", np.arange(5), [1, 2, 2, 2, 2], True, 0),
        ("count", np.arange(10, 0, -2), [1, 2, 2, 2, 2], True, 0),
        ("count", [0, 1, 2, np.nan, 4], [1, 2, 2, 1, 1], False, 0),
        ("max", np.arange(5), [np.nan, 1, 2, 3, 4], True, None),
        ("max", np.arange(10, 0, -2), [np.nan, 10, 8, 6, 4], True, None),
        ("max", [0, 1, 2, np.nan, 4], [np.nan, 1, 2, np.nan, np.nan], False, None),
        ("min", np.arange(5), [np.nan, 0, 1, 2, 3], True, None),
        ("min", np.arange(10, 0, -2), [np.nan, 8, 6, 4, 2], True, None),
        ("min", [0, 1, 2, np.nan, 4], [np.nan, 0, 1, np.nan, np.nan], False, None),
        ("sum", np.arange(5), [np.nan, 1, 3, 5, 7], True, None),
        ("sum", np.arange(10, 0, -2), [np.nan, 18, 14, 10, 6], True, None),
        ("sum", [0, 1, 2, np.nan, 4], [np.nan, 1, 3, np.nan, np.nan], False, None),
        ("mean", np.arange(5), [np.nan, 0.5, 1.5, 2.5, 3.5], True, None),
        ("mean", np.arange(10, 0, -2), [np.nan, 9, 7, 5, 3], True, None),
        ("mean", [0, 1, 2, np.nan, 4], [np.nan, 0.5, 1.5, np.nan, np.nan], False, None),
        ("std", np.arange(5), [np.nan] + [np.sqrt(0.5)] * 4, True, None),
        ("std", np.arange(10, 0, -2), [np.nan] + [np.sqrt(2)] * 4, True, None),
        (
            "std",
            [0, 1, 2, np.nan, 4],
            [np.nan] + [np.sqrt(0.5)] * 2 + [np.nan] * 2,
            False,
            None,
        ),
        ("var", np.arange(5), [np.nan, 0.5, 0.5, 0.5, 0.5], True, None),
        ("var", np.arange(10, 0, -2), [np.nan, 2, 2, 2, 2], True, None),
        ("var", [0, 1, 2, np.nan, 4], [np.nan, 0.5, 0.5, np.nan, np.nan], False, None),
        ("median", np.arange(5), [np.nan, 0.5, 1.5, 2.5, 3.5], True, None),
        ("median", np.arange(10, 0, -2), [np.nan, 9, 7, 5, 3], True, None),
        (
            "median",
            [0, 1, 2, np.nan, 4],
            [np.nan, 0.5, 1.5, np.nan, np.nan],
            False,
            None,
        ),
    ],
)
def test_series_dtypes(
    method, data, expected_data, coerce_int, dtypes, min_periods, step
):
    ser = Series(data, dtype=get_dtype(dtypes, coerce_int=coerce_int))
    rolled = ser.rolling(2, min_periods=min_periods, step=step)

    if dtypes in ("m8[ns]", "M8[ns]", "datetime64[ns, UTC]") and method != "count":
        msg = "No numeric types to aggregate"
        with pytest.raises(DataError, match=msg):
            getattr(rolled, method)()
    else:
        result = getattr(rolled, method)()
        expected = Series(expected_data, dtype="float64")[::step]
        tm.assert_almost_equal(result, expected)


def test_series_nullable_int(any_signed_int_ea_dtype, step):
    # GH 43016
    ser = Series([0, 1, NA], dtype=any_signed_int_ea_dtype)
    result = ser.rolling(2, step=step).mean()
    expected = Series([np.nan, 0.5, np.nan])[::step]
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "method, expected_data, min_periods",
    [
        ("count", {0: Series([1, 2, 2, 2, 2]), 1: Series([1, 2, 2, 2, 2])}, 0),
        (
            "max",
            {0: Series([np.nan, 2, 4, 6, 8]), 1: Series([np.nan, 3, 5, 7, 9])},
            None,
        ),
        (
            "min",
            {0: Series([np.nan, 0, 2, 4, 6]), 1: Series([np.nan, 1, 3, 5, 7])},
            None,
        ),
        (
            "sum",
            {0: Series([np.nan, 2, 6, 10, 14]), 1: Series([np.nan, 4, 8, 12, 16])},
            None,
        ),
        (
            "mean",
            {0: Series([np.nan, 1, 3, 5, 7]), 1: Series([np.nan, 2, 4, 6, 8])},
            None,
        ),
        (
            "std",
            {
                0: Series([np.nan] + [np.sqrt(2)] * 4),
                1: Series([np.nan] + [np.sqrt(2)] * 4),
            },
            None,
        ),
        (
            "var",
            {0: Series([np.nan, 2, 2, 2, 2]), 1: Series([np.nan, 2, 2, 2, 2])},
            None,
        ),
        (
            "median",
            {0: Series([np.nan, 1, 3, 5, 7]), 1: Series([np.nan, 2, 4, 6, 8])},
            None,
        ),
    ],
)
def test_dataframe_dtypes(method, expected_data, dtypes, min_periods, step):
    df = DataFrame(np.arange(10).reshape((5, 2)), dtype=get_dtype(dtypes))
    rolled = df.rolling(2, min_periods=min_periods, step=step)

    if dtypes in ("m8[ns]", "M8[ns]", "datetime64[ns, UTC]") and method != "count":
        msg = "Cannot aggregate non-numeric type"
        with pytest.raises(DataError, match=msg):
            getattr(rolled, method)()
    else:
        result = getattr(rolled, method)()
        expected = DataFrame(expected_data, dtype="float64")[::step]
        tm.assert_frame_equal(result, expected)
