import numpy as np
import pytest

from pandas.compat import WARNING_CHECK_DISABLED
import pandas.util._test_decorators as td

from pandas import (
    CategoricalDtype,
    DataFrame,
    NaT,
    Series,
    Timestamp,
)
import pandas._testing as tm


class TestUpdate:
    def test_update(self, using_copy_on_write):
        s = Series([1.5, np.nan, 3.0, 4.0, np.nan])
        s2 = Series([np.nan, 3.5, np.nan, 5.0])
        s.update(s2)

        expected = Series([1.5, 3.5, 3.0, 5.0, np.nan])
        tm.assert_series_equal(s, expected)

        # GH 3217
        df = DataFrame([{"a": 1}, {"a": 3, "b": 2}])
        df["c"] = np.nan
        # Cast to object to avoid upcast when setting "foo"
        df["c"] = df["c"].astype(object)
        df_orig = df.copy()

        if using_copy_on_write:
            with tm.raises_chained_assignment_error():
                df["c"].update(Series(["foo"], index=[0]))
            expected = df_orig
        else:
            with tm.assert_produces_warning(
                FutureWarning if not WARNING_CHECK_DISABLED else None,
                match="inplace method",
            ):
                df["c"].update(Series(["foo"], index=[0]))
            expected = DataFrame(
                [[1, np.nan, "foo"], [3, 2.0, np.nan]], columns=["a", "b", "c"]
            )
            expected["c"] = expected["c"].astype(object)
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize(
        "other, dtype, expected, warn",
        [
            # other is int
            ([61, 63], "int32", Series([10, 61, 12], dtype="int32"), None),
            ([61, 63], "int64", Series([10, 61, 12]), None),
            ([61, 63], float, Series([10.0, 61.0, 12.0]), None),
            ([61, 63], object, Series([10, 61, 12], dtype=object), None),
            # other is float, but can be cast to int
            ([61.0, 63.0], "int32", Series([10, 61, 12], dtype="int32"), None),
            ([61.0, 63.0], "int64", Series([10, 61, 12]), None),
            ([61.0, 63.0], float, Series([10.0, 61.0, 12.0]), None),
            ([61.0, 63.0], object, Series([10, 61.0, 12], dtype=object), None),
            # others is float, cannot be cast to int
            ([61.1, 63.1], "int32", Series([10.0, 61.1, 12.0]), FutureWarning),
            ([61.1, 63.1], "int64", Series([10.0, 61.1, 12.0]), FutureWarning),
            ([61.1, 63.1], float, Series([10.0, 61.1, 12.0]), None),
            ([61.1, 63.1], object, Series([10, 61.1, 12], dtype=object), None),
            # other is object, cannot be cast
            ([(61,), (63,)], "int32", Series([10, (61,), 12]), FutureWarning),
            ([(61,), (63,)], "int64", Series([10, (61,), 12]), FutureWarning),
            ([(61,), (63,)], float, Series([10.0, (61,), 12.0]), FutureWarning),
            ([(61,), (63,)], object, Series([10, (61,), 12]), None),
        ],
    )
    def test_update_dtypes(self, other, dtype, expected, warn):
        ser = Series([10, 11, 12], dtype=dtype)
        other = Series(other, index=[1, 3])
        with tm.assert_produces_warning(warn, match="item of incompatible dtype"):
            ser.update(other)

        tm.assert_series_equal(ser, expected)

    @pytest.mark.parametrize(
        "series, other, expected",
        [
            # update by key
            (
                Series({"a": 1, "b": 2, "c": 3, "d": 4}),
                {"b": 5, "c": np.nan},
                Series({"a": 1, "b": 5, "c": 3, "d": 4}),
            ),
            # update by position
            (Series([1, 2, 3, 4]), [np.nan, 5, 1], Series([1, 5, 1, 4])),
        ],
    )
    def test_update_from_non_series(self, series, other, expected):
        # GH 33215
        series.update(other)
        tm.assert_series_equal(series, expected)

    @pytest.mark.parametrize(
        "data, other, expected, dtype",
        [
            (["a", None], [None, "b"], ["a", "b"], "string[python]"),
            pytest.param(
                ["a", None],
                [None, "b"],
                ["a", "b"],
                "string[pyarrow]",
                marks=td.skip_if_no("pyarrow"),
            ),
            ([1, None], [None, 2], [1, 2], "Int64"),
            ([True, None], [None, False], [True, False], "boolean"),
            (
                ["a", None],
                [None, "b"],
                ["a", "b"],
                CategoricalDtype(categories=["a", "b"]),
            ),
            (
                [Timestamp(year=2020, month=1, day=1, tz="Europe/London"), NaT],
                [NaT, Timestamp(year=2020, month=1, day=1, tz="Europe/London")],
                [Timestamp(year=2020, month=1, day=1, tz="Europe/London")] * 2,
                "datetime64[ns, Europe/London]",
            ),
        ],
    )
    def test_update_extension_array_series(self, data, other, expected, dtype):
        result = Series(data, dtype=dtype)
        other = Series(other, dtype=dtype)
        expected = Series(expected, dtype=dtype)

        result.update(other)
        tm.assert_series_equal(result, expected)

    def test_update_with_categorical_type(self):
        # GH 25744
        dtype = CategoricalDtype(["a", "b", "c", "d"])
        s1 = Series(["a", "b", "c"], index=[1, 2, 3], dtype=dtype)
        s2 = Series(["b", "a"], index=[1, 2], dtype=dtype)
        s1.update(s2)
        result = s1
        expected = Series(["b", "a", "c"], index=[1, 2, 3], dtype=dtype)
        tm.assert_series_equal(result, expected)
