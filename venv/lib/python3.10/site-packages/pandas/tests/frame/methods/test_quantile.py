import numpy as np
import pytest

from pandas._config import using_string_dtype

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    Series,
    Timestamp,
)
import pandas._testing as tm


@pytest.fixture(
    params=[["linear", "single"], ["nearest", "table"]], ids=lambda x: "-".join(x)
)
def interp_method(request):
    """(interpolation, method) arguments for quantile"""
    return request.param


class TestDataFrameQuantile:
    @pytest.mark.parametrize(
        "df,expected",
        [
            [
                DataFrame(
                    {
                        0: Series(pd.arrays.SparseArray([1, 2])),
                        1: Series(pd.arrays.SparseArray([3, 4])),
                    }
                ),
                Series([1.5, 3.5], name=0.5),
            ],
            [
                DataFrame(Series([0.0, None, 1.0, 2.0], dtype="Sparse[float]")),
                Series([1.0], name=0.5),
            ],
        ],
    )
    def test_quantile_sparse(self, df, expected):
        # GH#17198
        # GH#24600
        result = df.quantile()
        expected = expected.astype("Sparse[float]")
        tm.assert_series_equal(result, expected)

    def test_quantile(
        self, datetime_frame, interp_method, using_array_manager, request
    ):
        interpolation, method = interp_method
        df = datetime_frame
        result = df.quantile(
            0.1, axis=0, numeric_only=True, interpolation=interpolation, method=method
        )
        expected = Series(
            [np.percentile(df[col], 10) for col in df.columns],
            index=df.columns,
            name=0.1,
        )
        if interpolation == "linear":
            # np.percentile values only comparable to linear interpolation
            tm.assert_series_equal(result, expected)
        else:
            tm.assert_index_equal(result.index, expected.index)
            request.applymarker(
                pytest.mark.xfail(
                    using_array_manager, reason="Name set incorrectly for arraymanager"
                )
            )
            assert result.name == expected.name

        result = df.quantile(
            0.9, axis=1, numeric_only=True, interpolation=interpolation, method=method
        )
        expected = Series(
            [np.percentile(df.loc[date], 90) for date in df.index],
            index=df.index,
            name=0.9,
        )
        if interpolation == "linear":
            # np.percentile values only comparable to linear interpolation
            tm.assert_series_equal(result, expected)
        else:
            tm.assert_index_equal(result.index, expected.index)
            request.applymarker(
                pytest.mark.xfail(
                    using_array_manager, reason="Name set incorrectly for arraymanager"
                )
            )
            assert result.name == expected.name

    def test_empty(self, interp_method):
        interpolation, method = interp_method
        q = DataFrame({"x": [], "y": []}).quantile(
            0.1, axis=0, numeric_only=True, interpolation=interpolation, method=method
        )
        assert np.isnan(q["x"]) and np.isnan(q["y"])

    def test_non_numeric_exclusion(self, interp_method, request, using_array_manager):
        interpolation, method = interp_method
        df = DataFrame({"col1": ["A", "A", "B", "B"], "col2": [1, 2, 3, 4]})
        rs = df.quantile(
            0.5, numeric_only=True, interpolation=interpolation, method=method
        )
        xp = df.median(numeric_only=True).rename(0.5)
        if interpolation == "nearest":
            xp = (xp + 0.5).astype(np.int64)
        if method == "table" and using_array_manager:
            request.applymarker(pytest.mark.xfail(reason="Axis name incorrectly set."))
        tm.assert_series_equal(rs, xp)

    def test_axis(self, interp_method, request, using_array_manager):
        # axis
        interpolation, method = interp_method
        df = DataFrame({"A": [1, 2, 3], "B": [2, 3, 4]}, index=[1, 2, 3])
        result = df.quantile(0.5, axis=1, interpolation=interpolation, method=method)
        expected = Series([1.5, 2.5, 3.5], index=[1, 2, 3], name=0.5)
        if interpolation == "nearest":
            expected = expected.astype(np.int64)
        if method == "table" and using_array_manager:
            request.applymarker(pytest.mark.xfail(reason="Axis name incorrectly set."))
        tm.assert_series_equal(result, expected)

        result = df.quantile(
            [0.5, 0.75], axis=1, interpolation=interpolation, method=method
        )
        expected = DataFrame(
            {1: [1.5, 1.75], 2: [2.5, 2.75], 3: [3.5, 3.75]}, index=[0.5, 0.75]
        )
        if interpolation == "nearest":
            expected.iloc[0, :] -= 0.5
            expected.iloc[1, :] += 0.25
            expected = expected.astype(np.int64)
        tm.assert_frame_equal(result, expected, check_index_type=True)

    def test_axis_numeric_only_true(self, interp_method, request, using_array_manager):
        # We may want to break API in the future to change this
        # so that we exclude non-numeric along the same axis
        # See GH #7312
        interpolation, method = interp_method
        df = DataFrame([[1, 2, 3], ["a", "b", 4]])
        result = df.quantile(
            0.5, axis=1, numeric_only=True, interpolation=interpolation, method=method
        )
        expected = Series([3.0, 4.0], index=[0, 1], name=0.5)
        if interpolation == "nearest":
            expected = expected.astype(np.int64)
        if method == "table" and using_array_manager:
            request.applymarker(pytest.mark.xfail(reason="Axis name incorrectly set."))
        tm.assert_series_equal(result, expected)

    def test_quantile_date_range(self, interp_method, request, using_array_manager):
        # GH 2460
        interpolation, method = interp_method
        dti = pd.date_range("2016-01-01", periods=3, tz="US/Pacific")
        ser = Series(dti)
        df = DataFrame(ser)

        result = df.quantile(
            numeric_only=False, interpolation=interpolation, method=method
        )
        expected = Series(
            ["2016-01-02 00:00:00"], name=0.5, dtype="datetime64[ns, US/Pacific]"
        )
        if method == "table" and using_array_manager:
            request.applymarker(pytest.mark.xfail(reason="Axis name incorrectly set."))

        tm.assert_series_equal(result, expected)

    def test_quantile_axis_mixed(self, interp_method, request, using_array_manager):
        # mixed on axis=1
        interpolation, method = interp_method
        df = DataFrame(
            {
                "A": [1, 2, 3],
                "B": [2.0, 3.0, 4.0],
                "C": pd.date_range("20130101", periods=3),
                "D": ["foo", "bar", "baz"],
            }
        )
        result = df.quantile(
            0.5, axis=1, numeric_only=True, interpolation=interpolation, method=method
        )
        expected = Series([1.5, 2.5, 3.5], name=0.5)
        if interpolation == "nearest":
            expected -= 0.5
        if method == "table" and using_array_manager:
            request.applymarker(pytest.mark.xfail(reason="Axis name incorrectly set."))
        tm.assert_series_equal(result, expected)

        # must raise
        msg = "'<' not supported between instances of 'Timestamp' and 'float'"
        with pytest.raises(TypeError, match=msg):
            df.quantile(0.5, axis=1, numeric_only=False)

    def test_quantile_axis_parameter(self, interp_method, request, using_array_manager):
        # GH 9543/9544
        interpolation, method = interp_method
        if method == "table" and using_array_manager:
            request.applymarker(pytest.mark.xfail(reason="Axis name incorrectly set."))
        df = DataFrame({"A": [1, 2, 3], "B": [2, 3, 4]}, index=[1, 2, 3])

        result = df.quantile(0.5, axis=0, interpolation=interpolation, method=method)

        expected = Series([2.0, 3.0], index=["A", "B"], name=0.5)
        if interpolation == "nearest":
            expected = expected.astype(np.int64)
        tm.assert_series_equal(result, expected)

        expected = df.quantile(
            0.5, axis="index", interpolation=interpolation, method=method
        )
        if interpolation == "nearest":
            expected = expected.astype(np.int64)
        tm.assert_series_equal(result, expected)

        result = df.quantile(0.5, axis=1, interpolation=interpolation, method=method)

        expected = Series([1.5, 2.5, 3.5], index=[1, 2, 3], name=0.5)
        if interpolation == "nearest":
            expected = expected.astype(np.int64)
        tm.assert_series_equal(result, expected)

        result = df.quantile(
            0.5, axis="columns", interpolation=interpolation, method=method
        )
        tm.assert_series_equal(result, expected)

        msg = "No axis named -1 for object type DataFrame"
        with pytest.raises(ValueError, match=msg):
            df.quantile(0.1, axis=-1, interpolation=interpolation, method=method)
        msg = "No axis named column for object type DataFrame"
        with pytest.raises(ValueError, match=msg):
            df.quantile(0.1, axis="column")

    def test_quantile_interpolation(self):
        # see gh-10174

        # interpolation method other than default linear
        df = DataFrame({"A": [1, 2, 3], "B": [2, 3, 4]}, index=[1, 2, 3])
        result = df.quantile(0.5, axis=1, interpolation="nearest")
        expected = Series([1, 2, 3], index=[1, 2, 3], name=0.5)
        tm.assert_series_equal(result, expected)

        # cross-check interpolation=nearest results in original dtype
        exp = np.percentile(
            np.array([[1, 2, 3], [2, 3, 4]]),
            0.5,
            axis=0,
            method="nearest",
        )
        expected = Series(exp, index=[1, 2, 3], name=0.5, dtype="int64")
        tm.assert_series_equal(result, expected)

        # float
        df = DataFrame({"A": [1.0, 2.0, 3.0], "B": [2.0, 3.0, 4.0]}, index=[1, 2, 3])
        result = df.quantile(0.5, axis=1, interpolation="nearest")
        expected = Series([1.0, 2.0, 3.0], index=[1, 2, 3], name=0.5)
        tm.assert_series_equal(result, expected)
        exp = np.percentile(
            np.array([[1.0, 2.0, 3.0], [2.0, 3.0, 4.0]]),
            0.5,
            axis=0,
            method="nearest",
        )
        expected = Series(exp, index=[1, 2, 3], name=0.5, dtype="float64")
        tm.assert_series_equal(result, expected)

        # axis
        result = df.quantile([0.5, 0.75], axis=1, interpolation="lower")
        expected = DataFrame(
            {1: [1.0, 1.0], 2: [2.0, 2.0], 3: [3.0, 3.0]}, index=[0.5, 0.75]
        )
        tm.assert_frame_equal(result, expected)

        # test degenerate case
        df = DataFrame({"x": [], "y": []})
        q = df.quantile(0.1, axis=0, interpolation="higher")
        assert np.isnan(q["x"]) and np.isnan(q["y"])

        # multi
        df = DataFrame([[1, 1, 1], [2, 2, 2], [3, 3, 3]], columns=["a", "b", "c"])
        result = df.quantile([0.25, 0.5], interpolation="midpoint")

        # https://github.com/numpy/numpy/issues/7163
        expected = DataFrame(
            [[1.5, 1.5, 1.5], [2.0, 2.0, 2.0]],
            index=[0.25, 0.5],
            columns=["a", "b", "c"],
        )
        tm.assert_frame_equal(result, expected)

    def test_quantile_interpolation_datetime(self, datetime_frame):
        # see gh-10174

        # interpolation = linear (default case)
        df = datetime_frame
        q = df.quantile(0.1, axis=0, numeric_only=True, interpolation="linear")
        assert q["A"] == np.percentile(df["A"], 10)

    def test_quantile_interpolation_int(self, int_frame):
        # see gh-10174

        df = int_frame
        # interpolation = linear (default case)
        q = df.quantile(0.1)
        assert q["A"] == np.percentile(df["A"], 10)

        # test with and without interpolation keyword
        q1 = df.quantile(0.1, axis=0, interpolation="linear")
        assert q1["A"] == np.percentile(df["A"], 10)
        tm.assert_series_equal(q, q1)

    def test_quantile_multi(self, interp_method, request, using_array_manager):
        interpolation, method = interp_method
        df = DataFrame([[1, 1, 1], [2, 2, 2], [3, 3, 3]], columns=["a", "b", "c"])
        result = df.quantile([0.25, 0.5], interpolation=interpolation, method=method)
        expected = DataFrame(
            [[1.5, 1.5, 1.5], [2.0, 2.0, 2.0]],
            index=[0.25, 0.5],
            columns=["a", "b", "c"],
        )
        if interpolation == "nearest":
            expected = expected.astype(np.int64)
        if method == "table" and using_array_manager:
            request.applymarker(pytest.mark.xfail(reason="Axis name incorrectly set."))
        tm.assert_frame_equal(result, expected)

    def test_quantile_multi_axis_1(self, interp_method, request, using_array_manager):
        interpolation, method = interp_method
        df = DataFrame([[1, 1, 1], [2, 2, 2], [3, 3, 3]], columns=["a", "b", "c"])
        result = df.quantile(
            [0.25, 0.5], axis=1, interpolation=interpolation, method=method
        )
        expected = DataFrame(
            [[1.0, 2.0, 3.0]] * 2, index=[0.25, 0.5], columns=[0, 1, 2]
        )
        if interpolation == "nearest":
            expected = expected.astype(np.int64)
        if method == "table" and using_array_manager:
            request.applymarker(pytest.mark.xfail(reason="Axis name incorrectly set."))
        tm.assert_frame_equal(result, expected)

    def test_quantile_multi_empty(self, interp_method):
        interpolation, method = interp_method
        result = DataFrame({"x": [], "y": []}).quantile(
            [0.1, 0.9], axis=0, interpolation=interpolation, method=method
        )
        expected = DataFrame(
            {"x": [np.nan, np.nan], "y": [np.nan, np.nan]}, index=[0.1, 0.9]
        )
        tm.assert_frame_equal(result, expected)

    def test_quantile_datetime(self, unit):
        dti = pd.to_datetime(["2010", "2011"]).as_unit(unit)
        df = DataFrame({"a": dti, "b": [0, 5]})

        # exclude datetime
        result = df.quantile(0.5, numeric_only=True)
        expected = Series([2.5], index=["b"], name=0.5)
        tm.assert_series_equal(result, expected)

        # datetime
        result = df.quantile(0.5, numeric_only=False)
        expected = Series(
            [Timestamp("2010-07-02 12:00:00"), 2.5], index=["a", "b"], name=0.5
        )
        tm.assert_series_equal(result, expected)

        # datetime w/ multi
        result = df.quantile([0.5], numeric_only=False)
        expected = DataFrame(
            {"a": Timestamp("2010-07-02 12:00:00").as_unit(unit), "b": 2.5},
            index=[0.5],
        )
        tm.assert_frame_equal(result, expected)

        # axis = 1
        df["c"] = pd.to_datetime(["2011", "2012"]).as_unit(unit)
        result = df[["a", "c"]].quantile(0.5, axis=1, numeric_only=False)
        expected = Series(
            [Timestamp("2010-07-02 12:00:00"), Timestamp("2011-07-02 12:00:00")],
            index=[0, 1],
            name=0.5,
            dtype=f"M8[{unit}]",
        )
        tm.assert_series_equal(result, expected)

        result = df[["a", "c"]].quantile([0.5], axis=1, numeric_only=False)
        expected = DataFrame(
            [[Timestamp("2010-07-02 12:00:00"), Timestamp("2011-07-02 12:00:00")]],
            index=[0.5],
            columns=[0, 1],
            dtype=f"M8[{unit}]",
        )
        tm.assert_frame_equal(result, expected)

        # empty when numeric_only=True
        result = df[["a", "c"]].quantile(0.5, numeric_only=True)
        expected = Series([], index=[], dtype=np.float64, name=0.5)
        tm.assert_series_equal(result, expected)

        result = df[["a", "c"]].quantile([0.5], numeric_only=True)
        expected = DataFrame(index=[0.5], columns=[])
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "dtype",
        [
            "datetime64[ns]",
            "datetime64[ns, US/Pacific]",
            "timedelta64[ns]",
            "Period[D]",
        ],
    )
    def test_quantile_dt64_empty(self, dtype, interp_method):
        # GH#41544
        interpolation, method = interp_method
        df = DataFrame(columns=["a", "b"], dtype=dtype)

        res = df.quantile(
            0.5, axis=1, numeric_only=False, interpolation=interpolation, method=method
        )
        expected = Series([], index=[], name=0.5, dtype=dtype)
        tm.assert_series_equal(res, expected)

        # no columns in result, so no dtype preservation
        res = df.quantile(
            [0.5],
            axis=1,
            numeric_only=False,
            interpolation=interpolation,
            method=method,
        )
        expected = DataFrame(index=[0.5], columns=[])
        tm.assert_frame_equal(res, expected)

    @pytest.mark.parametrize("invalid", [-1, 2, [0.5, -1], [0.5, 2]])
    def test_quantile_invalid(self, invalid, datetime_frame, interp_method):
        msg = "percentiles should all be in the interval \\[0, 1\\]"
        interpolation, method = interp_method
        with pytest.raises(ValueError, match=msg):
            datetime_frame.quantile(invalid, interpolation=interpolation, method=method)

    def test_quantile_box(self, interp_method, request, using_array_manager):
        interpolation, method = interp_method
        if method == "table" and using_array_manager:
            request.applymarker(pytest.mark.xfail(reason="Axis name incorrectly set."))
        df = DataFrame(
            {
                "A": [
                    Timestamp("2011-01-01"),
                    Timestamp("2011-01-02"),
                    Timestamp("2011-01-03"),
                ],
                "B": [
                    Timestamp("2011-01-01", tz="US/Eastern"),
                    Timestamp("2011-01-02", tz="US/Eastern"),
                    Timestamp("2011-01-03", tz="US/Eastern"),
                ],
                "C": [
                    pd.Timedelta("1 days"),
                    pd.Timedelta("2 days"),
                    pd.Timedelta("3 days"),
                ],
            }
        )

        res = df.quantile(
            0.5, numeric_only=False, interpolation=interpolation, method=method
        )

        exp = Series(
            [
                Timestamp("2011-01-02"),
                Timestamp("2011-01-02", tz="US/Eastern"),
                pd.Timedelta("2 days"),
            ],
            name=0.5,
            index=["A", "B", "C"],
        )
        tm.assert_series_equal(res, exp)

        res = df.quantile(
            [0.5], numeric_only=False, interpolation=interpolation, method=method
        )
        exp = DataFrame(
            [
                [
                    Timestamp("2011-01-02"),
                    Timestamp("2011-01-02", tz="US/Eastern"),
                    pd.Timedelta("2 days"),
                ]
            ],
            index=[0.5],
            columns=["A", "B", "C"],
        )
        tm.assert_frame_equal(res, exp)

    def test_quantile_box_nat(self):
        # DatetimeLikeBlock may be consolidated and contain NaT in different loc
        df = DataFrame(
            {
                "A": [
                    Timestamp("2011-01-01"),
                    pd.NaT,
                    Timestamp("2011-01-02"),
                    Timestamp("2011-01-03"),
                ],
                "a": [
                    Timestamp("2011-01-01"),
                    Timestamp("2011-01-02"),
                    pd.NaT,
                    Timestamp("2011-01-03"),
                ],
                "B": [
                    Timestamp("2011-01-01", tz="US/Eastern"),
                    pd.NaT,
                    Timestamp("2011-01-02", tz="US/Eastern"),
                    Timestamp("2011-01-03", tz="US/Eastern"),
                ],
                "b": [
                    Timestamp("2011-01-01", tz="US/Eastern"),
                    Timestamp("2011-01-02", tz="US/Eastern"),
                    pd.NaT,
                    Timestamp("2011-01-03", tz="US/Eastern"),
                ],
                "C": [
                    pd.Timedelta("1 days"),
                    pd.Timedelta("2 days"),
                    pd.Timedelta("3 days"),
                    pd.NaT,
                ],
                "c": [
                    pd.NaT,
                    pd.Timedelta("1 days"),
                    pd.Timedelta("2 days"),
                    pd.Timedelta("3 days"),
                ],
            },
            columns=list("AaBbCc"),
        )

        res = df.quantile(0.5, numeric_only=False)
        exp = Series(
            [
                Timestamp("2011-01-02"),
                Timestamp("2011-01-02"),
                Timestamp("2011-01-02", tz="US/Eastern"),
                Timestamp("2011-01-02", tz="US/Eastern"),
                pd.Timedelta("2 days"),
                pd.Timedelta("2 days"),
            ],
            name=0.5,
            index=list("AaBbCc"),
        )
        tm.assert_series_equal(res, exp)

        res = df.quantile([0.5], numeric_only=False)
        exp = DataFrame(
            [
                [
                    Timestamp("2011-01-02"),
                    Timestamp("2011-01-02"),
                    Timestamp("2011-01-02", tz="US/Eastern"),
                    Timestamp("2011-01-02", tz="US/Eastern"),
                    pd.Timedelta("2 days"),
                    pd.Timedelta("2 days"),
                ]
            ],
            index=[0.5],
            columns=list("AaBbCc"),
        )
        tm.assert_frame_equal(res, exp)

    def test_quantile_nan(self, interp_method, request, using_array_manager):
        interpolation, method = interp_method
        if method == "table" and using_array_manager:
            request.applymarker(pytest.mark.xfail(reason="Axis name incorrectly set."))
        # GH 14357 - float block where some cols have missing values
        df = DataFrame({"a": np.arange(1, 6.0), "b": np.arange(1, 6.0)})
        df.iloc[-1, 1] = np.nan

        res = df.quantile(0.5, interpolation=interpolation, method=method)
        exp = Series(
            [3.0, 2.5 if interpolation == "linear" else 3.0], index=["a", "b"], name=0.5
        )
        tm.assert_series_equal(res, exp)

        res = df.quantile([0.5, 0.75], interpolation=interpolation, method=method)
        exp = DataFrame(
            {
                "a": [3.0, 4.0],
                "b": [2.5, 3.25] if interpolation == "linear" else [3.0, 4.0],
            },
            index=[0.5, 0.75],
        )
        tm.assert_frame_equal(res, exp)

        res = df.quantile(0.5, axis=1, interpolation=interpolation, method=method)
        exp = Series(np.arange(1.0, 6.0), name=0.5)
        tm.assert_series_equal(res, exp)

        res = df.quantile(
            [0.5, 0.75], axis=1, interpolation=interpolation, method=method
        )
        exp = DataFrame([np.arange(1.0, 6.0)] * 2, index=[0.5, 0.75])
        if interpolation == "nearest":
            exp.iloc[1, -1] = np.nan
        tm.assert_frame_equal(res, exp)

        # full-nan column
        df["b"] = np.nan

        res = df.quantile(0.5, interpolation=interpolation, method=method)
        exp = Series([3.0, np.nan], index=["a", "b"], name=0.5)
        tm.assert_series_equal(res, exp)

        res = df.quantile([0.5, 0.75], interpolation=interpolation, method=method)
        exp = DataFrame({"a": [3.0, 4.0], "b": [np.nan, np.nan]}, index=[0.5, 0.75])
        tm.assert_frame_equal(res, exp)

    def test_quantile_nat(self, interp_method, request, using_array_manager, unit):
        interpolation, method = interp_method
        if method == "table" and using_array_manager:
            request.applymarker(pytest.mark.xfail(reason="Axis name incorrectly set."))
        # full NaT column
        df = DataFrame({"a": [pd.NaT, pd.NaT, pd.NaT]}, dtype=f"M8[{unit}]")

        res = df.quantile(
            0.5, numeric_only=False, interpolation=interpolation, method=method
        )
        exp = Series([pd.NaT], index=["a"], name=0.5, dtype=f"M8[{unit}]")
        tm.assert_series_equal(res, exp)

        res = df.quantile(
            [0.5], numeric_only=False, interpolation=interpolation, method=method
        )
        exp = DataFrame({"a": [pd.NaT]}, index=[0.5], dtype=f"M8[{unit}]")
        tm.assert_frame_equal(res, exp)

        # mixed non-null / full null column
        df = DataFrame(
            {
                "a": [
                    Timestamp("2012-01-01"),
                    Timestamp("2012-01-02"),
                    Timestamp("2012-01-03"),
                ],
                "b": [pd.NaT, pd.NaT, pd.NaT],
            },
            dtype=f"M8[{unit}]",
        )

        res = df.quantile(
            0.5, numeric_only=False, interpolation=interpolation, method=method
        )
        exp = Series(
            [Timestamp("2012-01-02"), pd.NaT],
            index=["a", "b"],
            name=0.5,
            dtype=f"M8[{unit}]",
        )
        tm.assert_series_equal(res, exp)

        res = df.quantile(
            [0.5], numeric_only=False, interpolation=interpolation, method=method
        )
        exp = DataFrame(
            [[Timestamp("2012-01-02"), pd.NaT]],
            index=[0.5],
            columns=["a", "b"],
            dtype=f"M8[{unit}]",
        )
        tm.assert_frame_equal(res, exp)

    def test_quantile_empty_no_rows_floats(self, interp_method):
        interpolation, method = interp_method

        df = DataFrame(columns=["a", "b"], dtype="float64")

        res = df.quantile(0.5, interpolation=interpolation, method=method)
        exp = Series([np.nan, np.nan], index=["a", "b"], name=0.5)
        tm.assert_series_equal(res, exp)

        res = df.quantile([0.5], interpolation=interpolation, method=method)
        exp = DataFrame([[np.nan, np.nan]], columns=["a", "b"], index=[0.5])
        tm.assert_frame_equal(res, exp)

        res = df.quantile(0.5, axis=1, interpolation=interpolation, method=method)
        exp = Series([], index=[], dtype="float64", name=0.5)
        tm.assert_series_equal(res, exp)

        res = df.quantile([0.5], axis=1, interpolation=interpolation, method=method)
        exp = DataFrame(columns=[], index=[0.5])
        tm.assert_frame_equal(res, exp)

    def test_quantile_empty_no_rows_ints(self, interp_method):
        interpolation, method = interp_method
        df = DataFrame(columns=["a", "b"], dtype="int64")

        res = df.quantile(0.5, interpolation=interpolation, method=method)
        exp = Series([np.nan, np.nan], index=["a", "b"], name=0.5)
        tm.assert_series_equal(res, exp)

    def test_quantile_empty_no_rows_dt64(self, interp_method):
        interpolation, method = interp_method
        # datetimes
        df = DataFrame(columns=["a", "b"], dtype="datetime64[ns]")

        res = df.quantile(
            0.5, numeric_only=False, interpolation=interpolation, method=method
        )
        exp = Series(
            [pd.NaT, pd.NaT], index=["a", "b"], dtype="datetime64[ns]", name=0.5
        )
        tm.assert_series_equal(res, exp)

        # Mixed dt64/dt64tz
        df["a"] = df["a"].dt.tz_localize("US/Central")
        res = df.quantile(
            0.5, numeric_only=False, interpolation=interpolation, method=method
        )
        exp = exp.astype(object)
        if interpolation == "nearest":
            # GH#18463 TODO: would we prefer NaTs here?
            msg = "The 'downcast' keyword in fillna is deprecated"
            with tm.assert_produces_warning(FutureWarning, match=msg):
                exp = exp.fillna(np.nan, downcast=False)
        tm.assert_series_equal(res, exp)

        # both dt64tz
        df["b"] = df["b"].dt.tz_localize("US/Central")
        res = df.quantile(
            0.5, numeric_only=False, interpolation=interpolation, method=method
        )
        exp = exp.astype(df["b"].dtype)
        tm.assert_series_equal(res, exp)

    def test_quantile_empty_no_columns(self, interp_method):
        # GH#23925 _get_numeric_data may drop all columns
        interpolation, method = interp_method
        df = DataFrame(pd.date_range("1/1/18", periods=5))
        df.columns.name = "captain tightpants"
        result = df.quantile(
            0.5, numeric_only=True, interpolation=interpolation, method=method
        )
        expected = Series([], index=[], name=0.5, dtype=np.float64)
        expected.index.name = "captain tightpants"
        tm.assert_series_equal(result, expected)

        result = df.quantile(
            [0.5], numeric_only=True, interpolation=interpolation, method=method
        )
        expected = DataFrame([], index=[0.5], columns=[])
        expected.columns.name = "captain tightpants"
        tm.assert_frame_equal(result, expected)

    def test_quantile_item_cache(
        self, using_array_manager, interp_method, using_copy_on_write
    ):
        # previous behavior incorrect retained an invalid _item_cache entry
        interpolation, method = interp_method
        df = DataFrame(
            np.random.default_rng(2).standard_normal((4, 3)), columns=["A", "B", "C"]
        )
        df["D"] = df["A"] * 2
        ser = df["A"]
        if not using_array_manager:
            assert len(df._mgr.blocks) == 2

        df.quantile(numeric_only=False, interpolation=interpolation, method=method)

        if using_copy_on_write:
            ser.iloc[0] = 99
            assert df.iloc[0, 0] == df["A"][0]
            assert df.iloc[0, 0] != 99
        else:
            ser.values[0] = 99
            assert df.iloc[0, 0] == df["A"][0]
            assert df.iloc[0, 0] == 99

    def test_invalid_method(self):
        with pytest.raises(ValueError, match="Invalid method: foo"):
            DataFrame(range(1)).quantile(0.5, method="foo")

    def test_table_invalid_interpolation(self):
        with pytest.raises(ValueError, match="Invalid interpolation: foo"):
            DataFrame(range(1)).quantile(0.5, method="table", interpolation="foo")


class TestQuantileExtensionDtype:
    # TODO: tests for axis=1?
    # TODO: empty case?

    @pytest.fixture(
        params=[
            pytest.param(
                pd.IntervalIndex.from_breaks(range(10)),
                marks=pytest.mark.xfail(reason="raises when trying to add Intervals"),
            ),
            pd.period_range("2016-01-01", periods=9, freq="D"),
            pd.date_range("2016-01-01", periods=9, tz="US/Pacific"),
            pd.timedelta_range("1 Day", periods=9),
            pd.array(np.arange(9), dtype="Int64"),
            pd.array(np.arange(9), dtype="Float64"),
        ],
        ids=lambda x: str(x.dtype),
    )
    def index(self, request):
        # NB: not actually an Index object
        idx = request.param
        idx.name = "A"
        return idx

    @pytest.fixture
    def obj(self, index, frame_or_series):
        # bc index is not always an Index (yet), we need to re-patch .name
        obj = frame_or_series(index).copy()

        if frame_or_series is Series:
            obj.name = "A"
        else:
            obj.columns = ["A"]
        return obj

    def compute_quantile(self, obj, qs):
        if isinstance(obj, Series):
            result = obj.quantile(qs)
        else:
            result = obj.quantile(qs, numeric_only=False)
        return result

    def test_quantile_ea(self, request, obj, index):
        # result should be invariant to shuffling
        indexer = np.arange(len(index), dtype=np.intp)
        np.random.default_rng(2).shuffle(indexer)
        obj = obj.iloc[indexer]

        qs = [0.5, 0, 1]
        result = self.compute_quantile(obj, qs)

        exp_dtype = index.dtype
        if index.dtype == "Int64":
            # match non-nullable casting behavior
            exp_dtype = "Float64"

        # expected here assumes len(index) == 9
        expected = Series(
            [index[4], index[0], index[-1]], dtype=exp_dtype, index=qs, name="A"
        )
        expected = type(obj)(expected)

        tm.assert_equal(result, expected)

    def test_quantile_ea_with_na(self, obj, index):
        obj.iloc[0] = index._na_value
        obj.iloc[-1] = index._na_value

        # result should be invariant to shuffling
        indexer = np.arange(len(index), dtype=np.intp)
        np.random.default_rng(2).shuffle(indexer)
        obj = obj.iloc[indexer]

        qs = [0.5, 0, 1]
        result = self.compute_quantile(obj, qs)

        # expected here assumes len(index) == 9
        expected = Series(
            [index[4], index[1], index[-2]], dtype=index.dtype, index=qs, name="A"
        )
        expected = type(obj)(expected)
        tm.assert_equal(result, expected)

    def test_quantile_ea_all_na(self, request, obj, index):
        obj.iloc[:] = index._na_value
        # Check dtypes were preserved; this was once a problem see GH#39763
        assert np.all(obj.dtypes == index.dtype)

        # result should be invariant to shuffling
        indexer = np.arange(len(index), dtype=np.intp)
        np.random.default_rng(2).shuffle(indexer)
        obj = obj.iloc[indexer]

        qs = [0.5, 0, 1]
        result = self.compute_quantile(obj, qs)

        expected = index.take([-1, -1, -1], allow_fill=True, fill_value=index._na_value)
        expected = Series(expected, index=qs, name="A")
        expected = type(obj)(expected)
        tm.assert_equal(result, expected)

    def test_quantile_ea_scalar(self, request, obj, index):
        # scalar qs

        # result should be invariant to shuffling
        indexer = np.arange(len(index), dtype=np.intp)
        np.random.default_rng(2).shuffle(indexer)
        obj = obj.iloc[indexer]

        qs = 0.5
        result = self.compute_quantile(obj, qs)

        exp_dtype = index.dtype
        if index.dtype == "Int64":
            exp_dtype = "Float64"

        expected = Series({"A": index[4]}, dtype=exp_dtype, name=0.5)
        if isinstance(obj, Series):
            expected = expected["A"]
            assert result == expected
        else:
            tm.assert_series_equal(result, expected)

    @pytest.mark.xfail(using_string_dtype(), reason="TODO(infer_string)", strict=False)
    @pytest.mark.parametrize(
        "dtype, expected_data, expected_index, axis",
        [
            ["float64", [], [], 1],
            ["int64", [], [], 1],
            ["float64", [np.nan, np.nan], ["a", "b"], 0],
            ["int64", [np.nan, np.nan], ["a", "b"], 0],
        ],
    )
    def test_empty_numeric(self, dtype, expected_data, expected_index, axis):
        # GH 14564
        df = DataFrame(columns=["a", "b"], dtype=dtype)
        result = df.quantile(0.5, axis=axis)
        expected = Series(
            expected_data, name=0.5, index=Index(expected_index), dtype="float64"
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.xfail(using_string_dtype(), reason="TODO(infer_string)", strict=False)
    @pytest.mark.parametrize(
        "dtype, expected_data, expected_index, axis, expected_dtype",
        [
            ["datetime64[ns]", [], [], 1, "datetime64[ns]"],
            ["datetime64[ns]", [pd.NaT, pd.NaT], ["a", "b"], 0, "datetime64[ns]"],
        ],
    )
    def test_empty_datelike(
        self, dtype, expected_data, expected_index, axis, expected_dtype
    ):
        # GH 14564
        df = DataFrame(columns=["a", "b"], dtype=dtype)
        result = df.quantile(0.5, axis=axis, numeric_only=False)
        expected = Series(
            expected_data, name=0.5, index=Index(expected_index), dtype=expected_dtype
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.xfail(using_string_dtype(), reason="TODO(infer_string)", strict=False)
    @pytest.mark.parametrize(
        "expected_data, expected_index, axis",
        [
            [[np.nan, np.nan], range(2), 1],
            [[], [], 0],
        ],
    )
    def test_datelike_numeric_only(self, expected_data, expected_index, axis):
        # GH 14564
        df = DataFrame(
            {
                "a": pd.to_datetime(["2010", "2011"]),
                "b": [0, 5],
                "c": pd.to_datetime(["2011", "2012"]),
            }
        )
        result = df[["a", "c"]].quantile(0.5, axis=axis, numeric_only=True)
        expected = Series(
            expected_data, name=0.5, index=Index(expected_index), dtype=np.float64
        )
        tm.assert_series_equal(result, expected)
