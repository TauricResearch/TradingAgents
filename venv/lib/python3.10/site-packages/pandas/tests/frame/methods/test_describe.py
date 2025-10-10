import numpy as np
import pytest

import pandas as pd
from pandas import (
    Categorical,
    DataFrame,
    Series,
    Timestamp,
    date_range,
)
import pandas._testing as tm


class TestDataFrameDescribe:
    def test_describe_bool_in_mixed_frame(self):
        df = DataFrame(
            {
                "string_data": ["a", "b", "c", "d", "e"],
                "bool_data": [True, True, False, False, False],
                "int_data": [10, 20, 30, 40, 50],
            }
        )

        # Integer data are included in .describe() output,
        # Boolean and string data are not.
        result = df.describe()
        expected = DataFrame(
            {"int_data": [5, 30, df.int_data.std(), 10, 20, 30, 40, 50]},
            index=["count", "mean", "std", "min", "25%", "50%", "75%", "max"],
        )
        tm.assert_frame_equal(result, expected)

        # Top value is a boolean value that is False
        result = df.describe(include=["bool"])

        expected = DataFrame(
            {"bool_data": [5, 2, False, 3]}, index=["count", "unique", "top", "freq"]
        )
        tm.assert_frame_equal(result, expected)

    def test_describe_empty_object(self):
        # GH#27183
        df = DataFrame({"A": [None, None]}, dtype=object)
        result = df.describe()
        expected = DataFrame(
            {"A": [0, 0, np.nan, np.nan]},
            dtype=object,
            index=["count", "unique", "top", "freq"],
        )
        tm.assert_frame_equal(result, expected)

        result = df.iloc[:0].describe()
        tm.assert_frame_equal(result, expected)

    def test_describe_bool_frame(self):
        # GH#13891
        df = DataFrame(
            {
                "bool_data_1": [False, False, True, True],
                "bool_data_2": [False, True, True, True],
            }
        )
        result = df.describe()
        expected = DataFrame(
            {"bool_data_1": [4, 2, False, 2], "bool_data_2": [4, 2, True, 3]},
            index=["count", "unique", "top", "freq"],
        )
        tm.assert_frame_equal(result, expected)

        df = DataFrame(
            {
                "bool_data": [False, False, True, True, False],
                "int_data": [0, 1, 2, 3, 4],
            }
        )
        result = df.describe()
        expected = DataFrame(
            {"int_data": [5, 2, df.int_data.std(), 0, 1, 2, 3, 4]},
            index=["count", "mean", "std", "min", "25%", "50%", "75%", "max"],
        )
        tm.assert_frame_equal(result, expected)

        df = DataFrame(
            {"bool_data": [False, False, True, True], "str_data": ["a", "b", "c", "a"]}
        )
        result = df.describe()
        expected = DataFrame(
            {"bool_data": [4, 2, False, 2], "str_data": [4, 3, "a", 2]},
            index=["count", "unique", "top", "freq"],
        )
        tm.assert_frame_equal(result, expected)

    def test_describe_categorical(self):
        df = DataFrame({"value": np.random.default_rng(2).integers(0, 10000, 100)})
        labels = [f"{i} - {i + 499}" for i in range(0, 10000, 500)]
        cat_labels = Categorical(labels, labels)

        df = df.sort_values(by=["value"], ascending=True)
        df["value_group"] = pd.cut(
            df.value, range(0, 10500, 500), right=False, labels=cat_labels
        )
        cat = df

        # Categoricals should not show up together with numerical columns
        result = cat.describe()
        assert len(result.columns) == 1

        # In a frame, describe() for the cat should be the same as for string
        # arrays (count, unique, top, freq)

        cat = Categorical(
            ["a", "b", "b", "b"], categories=["a", "b", "c"], ordered=True
        )
        s = Series(cat)
        result = s.describe()
        expected = Series([4, 2, "b", 3], index=["count", "unique", "top", "freq"])
        tm.assert_series_equal(result, expected)

        cat = Series(Categorical(["a", "b", "c", "c"]))
        df3 = DataFrame({"cat": cat, "s": ["a", "b", "c", "c"]})
        result = df3.describe()
        tm.assert_numpy_array_equal(result["cat"].values, result["s"].values)

    def test_describe_empty_categorical_column(self):
        # GH#26397
        # Ensure the index of an empty categorical DataFrame column
        # also contains (count, unique, top, freq)
        df = DataFrame({"empty_col": Categorical([])})
        result = df.describe()
        expected = DataFrame(
            {"empty_col": [0, 0, np.nan, np.nan]},
            index=["count", "unique", "top", "freq"],
            dtype="object",
        )
        tm.assert_frame_equal(result, expected)
        # ensure NaN, not None
        assert np.isnan(result.iloc[2, 0])
        assert np.isnan(result.iloc[3, 0])

    def test_describe_categorical_columns(self):
        # GH#11558
        columns = pd.CategoricalIndex(["int1", "int2", "obj"], ordered=True, name="XXX")
        df = DataFrame(
            {
                "int1": [10, 20, 30, 40, 50],
                "int2": [10, 20, 30, 40, 50],
                "obj": ["A", 0, None, "X", 1],
            },
            columns=columns,
        )
        result = df.describe()

        exp_columns = pd.CategoricalIndex(
            ["int1", "int2"],
            categories=["int1", "int2", "obj"],
            ordered=True,
            name="XXX",
        )
        expected = DataFrame(
            {
                "int1": [5, 30, df.int1.std(), 10, 20, 30, 40, 50],
                "int2": [5, 30, df.int2.std(), 10, 20, 30, 40, 50],
            },
            index=["count", "mean", "std", "min", "25%", "50%", "75%", "max"],
            columns=exp_columns,
        )

        tm.assert_frame_equal(result, expected)
        tm.assert_categorical_equal(result.columns.values, expected.columns.values)

    def test_describe_datetime_columns(self):
        columns = pd.DatetimeIndex(
            ["2011-01-01", "2011-02-01", "2011-03-01"],
            freq="MS",
            tz="US/Eastern",
            name="XXX",
        )
        df = DataFrame(
            {
                0: [10, 20, 30, 40, 50],
                1: [10, 20, 30, 40, 50],
                2: ["A", 0, None, "X", 1],
            }
        )
        df.columns = columns
        result = df.describe()

        exp_columns = pd.DatetimeIndex(
            ["2011-01-01", "2011-02-01"], freq="MS", tz="US/Eastern", name="XXX"
        )
        expected = DataFrame(
            {
                0: [5, 30, df.iloc[:, 0].std(), 10, 20, 30, 40, 50],
                1: [5, 30, df.iloc[:, 1].std(), 10, 20, 30, 40, 50],
            },
            index=["count", "mean", "std", "min", "25%", "50%", "75%", "max"],
        )
        expected.columns = exp_columns
        tm.assert_frame_equal(result, expected)
        assert result.columns.freq == "MS"
        assert result.columns.tz == expected.columns.tz

    def test_describe_timedelta_values(self):
        # GH#6145
        t1 = pd.timedelta_range("1 days", freq="D", periods=5)
        t2 = pd.timedelta_range("1 hours", freq="h", periods=5)
        df = DataFrame({"t1": t1, "t2": t2})

        expected = DataFrame(
            {
                "t1": [
                    5,
                    pd.Timedelta("3 days"),
                    df.iloc[:, 0].std(),
                    pd.Timedelta("1 days"),
                    pd.Timedelta("2 days"),
                    pd.Timedelta("3 days"),
                    pd.Timedelta("4 days"),
                    pd.Timedelta("5 days"),
                ],
                "t2": [
                    5,
                    pd.Timedelta("3 hours"),
                    df.iloc[:, 1].std(),
                    pd.Timedelta("1 hours"),
                    pd.Timedelta("2 hours"),
                    pd.Timedelta("3 hours"),
                    pd.Timedelta("4 hours"),
                    pd.Timedelta("5 hours"),
                ],
            },
            index=["count", "mean", "std", "min", "25%", "50%", "75%", "max"],
        )

        result = df.describe()
        tm.assert_frame_equal(result, expected)

        exp_repr = (
            "                              t1                         t2\n"
            "count                          5                          5\n"
            "mean             3 days 00:00:00            0 days 03:00:00\n"
            "std    1 days 13:56:50.394919273  0 days 01:34:52.099788303\n"
            "min              1 days 00:00:00            0 days 01:00:00\n"
            "25%              2 days 00:00:00            0 days 02:00:00\n"
            "50%              3 days 00:00:00            0 days 03:00:00\n"
            "75%              4 days 00:00:00            0 days 04:00:00\n"
            "max              5 days 00:00:00            0 days 05:00:00"
        )
        assert repr(result) == exp_repr

    def test_describe_tz_values(self, tz_naive_fixture):
        # GH#21332
        tz = tz_naive_fixture
        s1 = Series(range(5))
        start = Timestamp(2018, 1, 1)
        end = Timestamp(2018, 1, 5)
        s2 = Series(date_range(start, end, tz=tz))
        df = DataFrame({"s1": s1, "s2": s2})

        expected = DataFrame(
            {
                "s1": [5, 2, 0, 1, 2, 3, 4, 1.581139],
                "s2": [
                    5,
                    Timestamp(2018, 1, 3).tz_localize(tz),
                    start.tz_localize(tz),
                    s2[1],
                    s2[2],
                    s2[3],
                    end.tz_localize(tz),
                    np.nan,
                ],
            },
            index=["count", "mean", "min", "25%", "50%", "75%", "max", "std"],
        )
        result = df.describe(include="all")
        tm.assert_frame_equal(result, expected)

    def test_datetime_is_numeric_includes_datetime(self):
        df = DataFrame({"a": date_range("2012", periods=3), "b": [1, 2, 3]})
        result = df.describe()
        expected = DataFrame(
            {
                "a": [
                    3,
                    Timestamp("2012-01-02"),
                    Timestamp("2012-01-01"),
                    Timestamp("2012-01-01T12:00:00"),
                    Timestamp("2012-01-02"),
                    Timestamp("2012-01-02T12:00:00"),
                    Timestamp("2012-01-03"),
                    np.nan,
                ],
                "b": [3, 2, 1, 1.5, 2, 2.5, 3, 1],
            },
            index=["count", "mean", "min", "25%", "50%", "75%", "max", "std"],
        )
        tm.assert_frame_equal(result, expected)

    def test_describe_tz_values2(self):
        tz = "CET"
        s1 = Series(range(5))
        start = Timestamp(2018, 1, 1)
        end = Timestamp(2018, 1, 5)
        s2 = Series(date_range(start, end, tz=tz))
        df = DataFrame({"s1": s1, "s2": s2})

        s1_ = s1.describe()
        s2_ = s2.describe()
        idx = [
            "count",
            "mean",
            "min",
            "25%",
            "50%",
            "75%",
            "max",
            "std",
        ]
        expected = pd.concat([s1_, s2_], axis=1, keys=["s1", "s2"]).reindex(
            idx, copy=False
        )

        result = df.describe(include="all")
        tm.assert_frame_equal(result, expected)

    def test_describe_percentiles_integer_idx(self):
        # GH#26660
        df = DataFrame({"x": [1]})
        pct = np.linspace(0, 1, 10 + 1)
        result = df.describe(percentiles=pct)

        expected = DataFrame(
            {"x": [1.0, 1.0, np.nan, 1.0, *(1.0 for _ in pct), 1.0]},
            index=[
                "count",
                "mean",
                "std",
                "min",
                "0%",
                "10%",
                "20%",
                "30%",
                "40%",
                "50%",
                "60%",
                "70%",
                "80%",
                "90%",
                "100%",
                "max",
            ],
        )
        tm.assert_frame_equal(result, expected)

    def test_describe_does_not_raise_error_for_dictlike_elements(self):
        # GH#32409
        df = DataFrame([{"test": {"a": "1"}}, {"test": {"a": "2"}}])
        expected = DataFrame(
            {"test": [2, 2, {"a": "1"}, 1]}, index=["count", "unique", "top", "freq"]
        )
        result = df.describe()
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("exclude", ["x", "y", ["x", "y"], ["x", "z"]])
    def test_describe_when_include_all_exclude_not_allowed(self, exclude):
        """
        When include is 'all', then setting exclude != None is not allowed.
        """
        df = DataFrame({"x": [1], "y": [2], "z": [3]})
        msg = "exclude must be None when include is 'all'"
        with pytest.raises(ValueError, match=msg):
            df.describe(include="all", exclude=exclude)

    def test_describe_with_duplicate_columns(self):
        df = DataFrame(
            [[1, 1, 1], [2, 2, 2], [3, 3, 3]],
            columns=["bar", "a", "a"],
            dtype="float64",
        )
        result = df.describe()
        ser = df.iloc[:, 0].describe()
        expected = pd.concat([ser, ser, ser], keys=df.columns, axis=1)
        tm.assert_frame_equal(result, expected)

    def test_ea_with_na(self, any_numeric_ea_dtype):
        # GH#48778

        df = DataFrame({"a": [1, pd.NA, pd.NA], "b": pd.NA}, dtype=any_numeric_ea_dtype)
        result = df.describe()
        expected = DataFrame(
            {"a": [1.0, 1.0, pd.NA] + [1.0] * 5, "b": [0.0] + [pd.NA] * 7},
            index=["count", "mean", "std", "min", "25%", "50%", "75%", "max"],
            dtype="Float64",
        )
        tm.assert_frame_equal(result, expected)

    def test_describe_exclude_pa_dtype(self):
        # GH#52570
        pa = pytest.importorskip("pyarrow")
        df = DataFrame(
            {
                "a": Series([1, 2, 3], dtype=pd.ArrowDtype(pa.int8())),
                "b": Series([1, 2, 3], dtype=pd.ArrowDtype(pa.int16())),
                "c": Series([1, 2, 3], dtype=pd.ArrowDtype(pa.int32())),
            }
        )
        result = df.describe(
            include=pd.ArrowDtype(pa.int8()), exclude=pd.ArrowDtype(pa.int32())
        )
        expected = DataFrame(
            {"a": [3, 2, 1, 1, 1.5, 2, 2.5, 3]},
            index=["count", "mean", "std", "min", "25%", "50%", "75%", "max"],
            dtype=pd.ArrowDtype(pa.float64()),
        )
        tm.assert_frame_equal(result, expected)
