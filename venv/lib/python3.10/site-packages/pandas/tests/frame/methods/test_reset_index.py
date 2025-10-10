from datetime import datetime
from itertools import product

import numpy as np
import pytest

from pandas.core.dtypes.common import (
    is_float_dtype,
    is_integer_dtype,
)

import pandas as pd
from pandas import (
    Categorical,
    CategoricalIndex,
    DataFrame,
    Index,
    Interval,
    IntervalIndex,
    MultiIndex,
    RangeIndex,
    Series,
    Timestamp,
    cut,
    date_range,
)
import pandas._testing as tm


@pytest.fixture()
def multiindex_df():
    levels = [["A", ""], ["B", "b"]]
    return DataFrame([[0, 2], [1, 3]], columns=MultiIndex.from_tuples(levels))


class TestResetIndex:
    def test_reset_index_empty_rangeindex(self):
        # GH#45230
        df = DataFrame(
            columns=["brand"], dtype=np.int64, index=RangeIndex(0, 0, 1, name="foo")
        )

        df2 = df.set_index([df.index, "brand"])

        result = df2.reset_index([1], drop=True)
        tm.assert_frame_equal(result, df[[]], check_index_type=True)

    def test_set_reset(self):
        idx = Index([2**63, 2**63 + 5, 2**63 + 10], name="foo")

        # set/reset
        df = DataFrame({"A": [0, 1, 2]}, index=idx)
        result = df.reset_index()
        assert result["foo"].dtype == np.dtype("uint64")

        df = result.set_index("foo")
        tm.assert_index_equal(df.index, idx)

    def test_set_index_reset_index_dt64tz(self):
        idx = Index(date_range("20130101", periods=3, tz="US/Eastern"), name="foo")

        # set/reset
        df = DataFrame({"A": [0, 1, 2]}, index=idx)
        result = df.reset_index()
        assert result["foo"].dtype == "datetime64[ns, US/Eastern]"

        df = result.set_index("foo")
        tm.assert_index_equal(df.index, idx)

    def test_reset_index_tz(self, tz_aware_fixture):
        # GH 3950
        # reset_index with single level
        tz = tz_aware_fixture
        idx = date_range("1/1/2011", periods=5, freq="D", tz=tz, name="idx")
        df = DataFrame({"a": range(5), "b": ["A", "B", "C", "D", "E"]}, index=idx)

        expected = DataFrame(
            {
                "idx": idx,
                "a": range(5),
                "b": ["A", "B", "C", "D", "E"],
            },
            columns=["idx", "a", "b"],
        )
        result = df.reset_index()
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("tz", ["US/Eastern", "dateutil/US/Eastern"])
    def test_frame_reset_index_tzaware_index(self, tz):
        dr = date_range("2012-06-02", periods=10, tz=tz)
        df = DataFrame(np.random.default_rng(2).standard_normal(len(dr)), dr)
        roundtripped = df.reset_index().set_index("index")
        xp = df.index.tz
        rs = roundtripped.index.tz
        assert xp == rs

    def test_reset_index_with_intervals(self):
        idx = IntervalIndex.from_breaks(np.arange(11), name="x")
        original = DataFrame({"x": idx, "y": np.arange(10)})[["x", "y"]]

        result = original.set_index("x")
        expected = DataFrame({"y": np.arange(10)}, index=idx)
        tm.assert_frame_equal(result, expected)

        result2 = result.reset_index()
        tm.assert_frame_equal(result2, original)

    def test_reset_index(self, float_frame):
        stacked = float_frame.stack(future_stack=True)[::2]
        stacked = DataFrame({"foo": stacked, "bar": stacked})

        names = ["first", "second"]
        stacked.index.names = names
        deleveled = stacked.reset_index()
        for i, (lev, level_codes) in enumerate(
            zip(stacked.index.levels, stacked.index.codes)
        ):
            values = lev.take(level_codes)
            name = names[i]
            tm.assert_index_equal(values, Index(deleveled[name]))

        stacked.index.names = [None, None]
        deleveled2 = stacked.reset_index()
        tm.assert_series_equal(
            deleveled["first"], deleveled2["level_0"], check_names=False
        )
        tm.assert_series_equal(
            deleveled["second"], deleveled2["level_1"], check_names=False
        )

        # default name assigned
        rdf = float_frame.reset_index()
        exp = Series(float_frame.index.values, name="index")
        tm.assert_series_equal(rdf["index"], exp)

        # default name assigned, corner case
        df = float_frame.copy()
        df["index"] = "foo"
        rdf = df.reset_index()
        exp = Series(float_frame.index.values, name="level_0")
        tm.assert_series_equal(rdf["level_0"], exp)

        # but this is ok
        float_frame.index.name = "index"
        deleveled = float_frame.reset_index()
        tm.assert_series_equal(deleveled["index"], Series(float_frame.index))
        tm.assert_index_equal(deleveled.index, Index(range(len(deleveled))), exact=True)

        # preserve column names
        float_frame.columns.name = "columns"
        reset = float_frame.reset_index()
        assert reset.columns.name == "columns"

        # only remove certain columns
        df = float_frame.reset_index().set_index(["index", "A", "B"])
        rs = df.reset_index(["A", "B"])

        tm.assert_frame_equal(rs, float_frame)

        rs = df.reset_index(["index", "A", "B"])
        tm.assert_frame_equal(rs, float_frame.reset_index())

        rs = df.reset_index(["index", "A", "B"])
        tm.assert_frame_equal(rs, float_frame.reset_index())

        rs = df.reset_index("A")
        xp = float_frame.reset_index().set_index(["index", "B"])
        tm.assert_frame_equal(rs, xp)

        # test resetting in place
        df = float_frame.copy()
        reset = float_frame.reset_index()
        return_value = df.reset_index(inplace=True)
        assert return_value is None
        tm.assert_frame_equal(df, reset)

        df = float_frame.reset_index().set_index(["index", "A", "B"])
        rs = df.reset_index("A", drop=True)
        xp = float_frame.copy()
        del xp["A"]
        xp = xp.set_index(["B"], append=True)
        tm.assert_frame_equal(rs, xp)

    def test_reset_index_name(self):
        df = DataFrame(
            [[1, 2, 3, 4], [5, 6, 7, 8]],
            columns=["A", "B", "C", "D"],
            index=Index(range(2), name="x"),
        )
        assert df.reset_index().index.name is None
        assert df.reset_index(drop=True).index.name is None
        return_value = df.reset_index(inplace=True)
        assert return_value is None
        assert df.index.name is None

    @pytest.mark.parametrize("levels", [["A", "B"], [0, 1]])
    def test_reset_index_level(self, levels):
        df = DataFrame([[1, 2, 3, 4], [5, 6, 7, 8]], columns=["A", "B", "C", "D"])

        # With MultiIndex
        result = df.set_index(["A", "B"]).reset_index(level=levels[0])
        tm.assert_frame_equal(result, df.set_index("B"))

        result = df.set_index(["A", "B"]).reset_index(level=levels[:1])
        tm.assert_frame_equal(result, df.set_index("B"))

        result = df.set_index(["A", "B"]).reset_index(level=levels)
        tm.assert_frame_equal(result, df)

        result = df.set_index(["A", "B"]).reset_index(level=levels, drop=True)
        tm.assert_frame_equal(result, df[["C", "D"]])

        # With single-level Index (GH 16263)
        result = df.set_index("A").reset_index(level=levels[0])
        tm.assert_frame_equal(result, df)

        result = df.set_index("A").reset_index(level=levels[:1])
        tm.assert_frame_equal(result, df)

        result = df.set_index(["A"]).reset_index(level=levels[0], drop=True)
        tm.assert_frame_equal(result, df[["B", "C", "D"]])

    @pytest.mark.parametrize("idx_lev", [["A", "B"], ["A"]])
    def test_reset_index_level_missing(self, idx_lev):
        # Missing levels - for both MultiIndex and single-level Index:
        df = DataFrame([[1, 2, 3, 4], [5, 6, 7, 8]], columns=["A", "B", "C", "D"])

        with pytest.raises(KeyError, match=r"(L|l)evel \(?E\)?"):
            df.set_index(idx_lev).reset_index(level=["A", "E"])
        with pytest.raises(IndexError, match="Too many levels"):
            df.set_index(idx_lev).reset_index(level=[0, 1, 2])

    def test_reset_index_right_dtype(self):
        time = np.arange(0.0, 10, np.sqrt(2) / 2)
        s1 = Series(
            (9.81 * time**2) / 2, index=Index(time, name="time"), name="speed"
        )
        df = DataFrame(s1)

        reset = s1.reset_index()
        assert reset["time"].dtype == np.float64

        reset = df.reset_index()
        assert reset["time"].dtype == np.float64

    def test_reset_index_multiindex_col(self):
        vals = np.random.default_rng(2).standard_normal((3, 3)).astype(object)
        idx = ["x", "y", "z"]
        full = np.hstack(([[x] for x in idx], vals))
        df = DataFrame(
            vals,
            Index(idx, name="a"),
            columns=[["b", "b", "c"], ["mean", "median", "mean"]],
        )
        rs = df.reset_index()
        xp = DataFrame(
            full, columns=[["a", "b", "b", "c"], ["", "mean", "median", "mean"]]
        )
        tm.assert_frame_equal(rs, xp)

        rs = df.reset_index(col_fill=None)
        xp = DataFrame(
            full, columns=[["a", "b", "b", "c"], ["a", "mean", "median", "mean"]]
        )
        tm.assert_frame_equal(rs, xp)

        rs = df.reset_index(col_level=1, col_fill="blah")
        xp = DataFrame(
            full, columns=[["blah", "b", "b", "c"], ["a", "mean", "median", "mean"]]
        )
        tm.assert_frame_equal(rs, xp)

        df = DataFrame(
            vals,
            MultiIndex.from_arrays([[0, 1, 2], ["x", "y", "z"]], names=["d", "a"]),
            columns=[["b", "b", "c"], ["mean", "median", "mean"]],
        )
        rs = df.reset_index("a")
        xp = DataFrame(
            full,
            Index([0, 1, 2], name="d"),
            columns=[["a", "b", "b", "c"], ["", "mean", "median", "mean"]],
        )
        tm.assert_frame_equal(rs, xp)

        rs = df.reset_index("a", col_fill=None)
        xp = DataFrame(
            full,
            Index(range(3), name="d"),
            columns=[["a", "b", "b", "c"], ["a", "mean", "median", "mean"]],
        )
        tm.assert_frame_equal(rs, xp)

        rs = df.reset_index("a", col_fill="blah", col_level=1)
        xp = DataFrame(
            full,
            Index(range(3), name="d"),
            columns=[["blah", "b", "b", "c"], ["a", "mean", "median", "mean"]],
        )
        tm.assert_frame_equal(rs, xp)

    def test_reset_index_multiindex_nan(self):
        # GH#6322, testing reset_index on MultiIndexes
        # when we have a nan or all nan
        df = DataFrame(
            {
                "A": ["a", "b", "c"],
                "B": [0, 1, np.nan],
                "C": np.random.default_rng(2).random(3),
            }
        )
        rs = df.set_index(["A", "B"]).reset_index()
        tm.assert_frame_equal(rs, df)

        df = DataFrame(
            {
                "A": [np.nan, "b", "c"],
                "B": [0, 1, 2],
                "C": np.random.default_rng(2).random(3),
            }
        )
        rs = df.set_index(["A", "B"]).reset_index()
        tm.assert_frame_equal(rs, df)

        df = DataFrame({"A": ["a", "b", "c"], "B": [0, 1, 2], "C": [np.nan, 1.1, 2.2]})
        rs = df.set_index(["A", "B"]).reset_index()
        tm.assert_frame_equal(rs, df)

        df = DataFrame(
            {
                "A": ["a", "b", "c"],
                "B": [np.nan, np.nan, np.nan],
                "C": np.random.default_rng(2).random(3),
            }
        )
        rs = df.set_index(["A", "B"]).reset_index()
        tm.assert_frame_equal(rs, df)

    @pytest.mark.parametrize(
        "name",
        [
            None,
            "foo",
            2,
            3.0,
            pd.Timedelta(6),
            Timestamp("2012-12-30", tz="UTC"),
            "2012-12-31",
        ],
    )
    def test_reset_index_with_datetimeindex_cols(self, name):
        # GH#5818
        df = DataFrame(
            [[1, 2], [3, 4]],
            columns=date_range("1/1/2013", "1/2/2013"),
            index=["A", "B"],
        )
        df.index.name = name

        result = df.reset_index()

        item = name if name is not None else "index"
        columns = Index([item, datetime(2013, 1, 1), datetime(2013, 1, 2)])
        if isinstance(item, str) and item == "2012-12-31":
            columns = columns.astype("datetime64[ns]")
        else:
            assert columns.dtype == object

        expected = DataFrame(
            [["A", 1, 2], ["B", 3, 4]],
            columns=columns,
        )
        tm.assert_frame_equal(result, expected)

    def test_reset_index_range(self):
        # GH#12071
        df = DataFrame([[0, 0], [1, 1]], columns=["A", "B"], index=RangeIndex(stop=2))
        result = df.reset_index()
        assert isinstance(result.index, RangeIndex)
        expected = DataFrame(
            [[0, 0, 0], [1, 1, 1]],
            columns=["index", "A", "B"],
            index=RangeIndex(stop=2),
        )
        tm.assert_frame_equal(result, expected)

    def test_reset_index_multiindex_columns(self, multiindex_df):
        result = multiindex_df[["B"]].rename_axis("A").reset_index()
        tm.assert_frame_equal(result, multiindex_df)

        # GH#16120: already existing column
        msg = r"cannot insert \('A', ''\), already exists"
        with pytest.raises(ValueError, match=msg):
            multiindex_df.rename_axis("A").reset_index()

        # GH#16164: multiindex (tuple) full key
        result = multiindex_df.set_index([("A", "")]).reset_index()
        tm.assert_frame_equal(result, multiindex_df)

        # with additional (unnamed) index level
        idx_col = DataFrame(
            [[0], [1]], columns=MultiIndex.from_tuples([("level_0", "")])
        )
        expected = pd.concat([idx_col, multiindex_df[[("B", "b"), ("A", "")]]], axis=1)
        result = multiindex_df.set_index([("B", "b")], append=True).reset_index()
        tm.assert_frame_equal(result, expected)

        # with index name which is a too long tuple...
        msg = "Item must have length equal to number of levels."
        with pytest.raises(ValueError, match=msg):
            multiindex_df.rename_axis([("C", "c", "i")]).reset_index()

        # or too short...
        levels = [["A", "a", ""], ["B", "b", "i"]]
        df2 = DataFrame([[0, 2], [1, 3]], columns=MultiIndex.from_tuples(levels))
        idx_col = DataFrame(
            [[0], [1]], columns=MultiIndex.from_tuples([("C", "c", "ii")])
        )
        expected = pd.concat([idx_col, df2], axis=1)
        result = df2.rename_axis([("C", "c")]).reset_index(col_fill="ii")
        tm.assert_frame_equal(result, expected)

        # ... which is incompatible with col_fill=None
        with pytest.raises(
            ValueError,
            match=(
                "col_fill=None is incompatible with "
                r"incomplete column name \('C', 'c'\)"
            ),
        ):
            df2.rename_axis([("C", "c")]).reset_index(col_fill=None)

        # with col_level != 0
        result = df2.rename_axis([("c", "ii")]).reset_index(col_level=1, col_fill="C")
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("flag", [False, True])
    @pytest.mark.parametrize("allow_duplicates", [False, True])
    def test_reset_index_duplicate_columns_allow(
        self, multiindex_df, flag, allow_duplicates
    ):
        # GH#44755 reset_index with duplicate column labels
        df = multiindex_df.rename_axis("A")
        df = df.set_flags(allows_duplicate_labels=flag)

        if flag and allow_duplicates:
            result = df.reset_index(allow_duplicates=allow_duplicates)
            levels = [["A", ""], ["A", ""], ["B", "b"]]
            expected = DataFrame(
                [[0, 0, 2], [1, 1, 3]], columns=MultiIndex.from_tuples(levels)
            )
            tm.assert_frame_equal(result, expected)
        else:
            if not flag and allow_duplicates:
                msg = (
                    "Cannot specify 'allow_duplicates=True' when "
                    "'self.flags.allows_duplicate_labels' is False"
                )
            else:
                msg = r"cannot insert \('A', ''\), already exists"
            with pytest.raises(ValueError, match=msg):
                df.reset_index(allow_duplicates=allow_duplicates)

    @pytest.mark.parametrize("flag", [False, True])
    def test_reset_index_duplicate_columns_default(self, multiindex_df, flag):
        df = multiindex_df.rename_axis("A")
        df = df.set_flags(allows_duplicate_labels=flag)

        msg = r"cannot insert \('A', ''\), already exists"
        with pytest.raises(ValueError, match=msg):
            df.reset_index()

    @pytest.mark.parametrize("allow_duplicates", ["bad value"])
    def test_reset_index_allow_duplicates_check(self, multiindex_df, allow_duplicates):
        with pytest.raises(ValueError, match="expected type bool"):
            multiindex_df.reset_index(allow_duplicates=allow_duplicates)

    def test_reset_index_datetime(self, tz_naive_fixture):
        # GH#3950
        tz = tz_naive_fixture
        idx1 = date_range("1/1/2011", periods=5, freq="D", tz=tz, name="idx1")
        idx2 = Index(range(5), name="idx2", dtype="int64")
        idx = MultiIndex.from_arrays([idx1, idx2])
        df = DataFrame(
            {"a": np.arange(5, dtype="int64"), "b": ["A", "B", "C", "D", "E"]},
            index=idx,
        )

        expected = DataFrame(
            {
                "idx1": idx1,
                "idx2": np.arange(5, dtype="int64"),
                "a": np.arange(5, dtype="int64"),
                "b": ["A", "B", "C", "D", "E"],
            },
            columns=["idx1", "idx2", "a", "b"],
        )

        tm.assert_frame_equal(df.reset_index(), expected)

    def test_reset_index_datetime2(self, tz_naive_fixture):
        tz = tz_naive_fixture
        idx1 = date_range("1/1/2011", periods=5, freq="D", tz=tz, name="idx1")
        idx2 = Index(range(5), name="idx2", dtype="int64")
        idx3 = date_range(
            "1/1/2012", periods=5, freq="MS", tz="Europe/Paris", name="idx3"
        )
        idx = MultiIndex.from_arrays([idx1, idx2, idx3])
        df = DataFrame(
            {"a": np.arange(5, dtype="int64"), "b": ["A", "B", "C", "D", "E"]},
            index=idx,
        )

        expected = DataFrame(
            {
                "idx1": idx1,
                "idx2": np.arange(5, dtype="int64"),
                "idx3": idx3,
                "a": np.arange(5, dtype="int64"),
                "b": ["A", "B", "C", "D", "E"],
            },
            columns=["idx1", "idx2", "idx3", "a", "b"],
        )
        result = df.reset_index()
        tm.assert_frame_equal(result, expected)

    def test_reset_index_datetime3(self, tz_naive_fixture):
        # GH#7793
        tz = tz_naive_fixture
        dti = date_range("20130101", periods=3, tz=tz)
        idx = MultiIndex.from_product([["a", "b"], dti])
        df = DataFrame(
            np.arange(6, dtype="int64").reshape(6, 1), columns=["a"], index=idx
        )

        expected = DataFrame(
            {
                "level_0": "a a a b b b".split(),
                "level_1": dti.append(dti),
                "a": np.arange(6, dtype="int64"),
            },
            columns=["level_0", "level_1", "a"],
        )
        result = df.reset_index()
        tm.assert_frame_equal(result, expected)

    def test_reset_index_period(self):
        # GH#7746
        idx = MultiIndex.from_product(
            [pd.period_range("20130101", periods=3, freq="M"), list("abc")],
            names=["month", "feature"],
        )

        df = DataFrame(
            np.arange(9, dtype="int64").reshape(-1, 1), index=idx, columns=["a"]
        )
        expected = DataFrame(
            {
                "month": (
                    [pd.Period("2013-01", freq="M")] * 3
                    + [pd.Period("2013-02", freq="M")] * 3
                    + [pd.Period("2013-03", freq="M")] * 3
                ),
                "feature": ["a", "b", "c"] * 3,
                "a": np.arange(9, dtype="int64"),
            },
            columns=["month", "feature", "a"],
        )
        result = df.reset_index()
        tm.assert_frame_equal(result, expected)

    def test_reset_index_delevel_infer_dtype(self):
        tuples = list(product(["foo", "bar"], [10, 20], [1.0, 1.1]))
        index = MultiIndex.from_tuples(tuples, names=["prm0", "prm1", "prm2"])
        df = DataFrame(
            np.random.default_rng(2).standard_normal((8, 3)),
            columns=["A", "B", "C"],
            index=index,
        )
        deleveled = df.reset_index()
        assert is_integer_dtype(deleveled["prm1"])
        assert is_float_dtype(deleveled["prm2"])

    def test_reset_index_with_drop(
        self, multiindex_year_month_day_dataframe_random_data
    ):
        ymd = multiindex_year_month_day_dataframe_random_data

        deleveled = ymd.reset_index(drop=True)
        assert len(deleveled.columns) == len(ymd.columns)
        assert deleveled.index.name == ymd.index.name

    @pytest.mark.parametrize(
        "ix_data, exp_data",
        [
            (
                [(pd.NaT, 1), (pd.NaT, 2)],
                {"a": [pd.NaT, pd.NaT], "b": [1, 2], "x": [11, 12]},
            ),
            (
                [(pd.NaT, 1), (Timestamp("2020-01-01"), 2)],
                {"a": [pd.NaT, Timestamp("2020-01-01")], "b": [1, 2], "x": [11, 12]},
            ),
            (
                [(pd.NaT, 1), (pd.Timedelta(123, "d"), 2)],
                {"a": [pd.NaT, pd.Timedelta(123, "d")], "b": [1, 2], "x": [11, 12]},
            ),
        ],
    )
    def test_reset_index_nat_multiindex(self, ix_data, exp_data):
        # GH#36541: that reset_index() does not raise ValueError
        ix = MultiIndex.from_tuples(ix_data, names=["a", "b"])
        result = DataFrame({"x": [11, 12]}, index=ix)
        result = result.reset_index()

        expected = DataFrame(exp_data)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "codes", ([[0, 0, 1, 1], [0, 1, 0, 1]], [[0, 0, -1, 1], [0, 1, 0, 1]])
    )
    def test_rest_index_multiindex_categorical_with_missing_values(self, codes):
        # GH#24206

        index = MultiIndex(
            [CategoricalIndex(["A", "B"]), CategoricalIndex(["a", "b"])], codes
        )
        data = {"col": range(len(index))}
        df = DataFrame(data=data, index=index)

        expected = DataFrame(
            {
                "level_0": Categorical.from_codes(codes[0], categories=["A", "B"]),
                "level_1": Categorical.from_codes(codes[1], categories=["a", "b"]),
                "col": range(4),
            }
        )

        res = df.reset_index()
        tm.assert_frame_equal(res, expected)

        # roundtrip
        res = expected.set_index(["level_0", "level_1"]).reset_index()
        tm.assert_frame_equal(res, expected)


@pytest.mark.parametrize(
    "array, dtype",
    [
        (["a", "b"], object),
        (
            pd.period_range("12-1-2000", periods=2, freq="Q-DEC"),
            pd.PeriodDtype(freq="Q-DEC"),
        ),
    ],
)
def test_reset_index_dtypes_on_empty_frame_with_multiindex(
    array, dtype, using_infer_string
):
    # GH 19602 - Preserve dtype on empty DataFrame with MultiIndex
    idx = MultiIndex.from_product([[0, 1], [0.5, 1.0], array])
    result = DataFrame(index=idx)[:0].reset_index().dtypes
    if using_infer_string and dtype == object:
        dtype = pd.StringDtype(na_value=np.nan)
    expected = Series({"level_0": np.int64, "level_1": np.float64, "level_2": dtype})
    tm.assert_series_equal(result, expected)


def test_reset_index_empty_frame_with_datetime64_multiindex():
    # https://github.com/pandas-dev/pandas/issues/35606
    dti = pd.DatetimeIndex(["2020-07-20 00:00:00"], dtype="M8[ns]")
    idx = MultiIndex.from_product([dti, [3, 4]], names=["a", "b"])[:0]
    df = DataFrame(index=idx, columns=["c", "d"])
    result = df.reset_index()
    expected = DataFrame(
        columns=list("abcd"), index=RangeIndex(start=0, stop=0, step=1)
    )
    expected["a"] = expected["a"].astype("datetime64[ns]")
    expected["b"] = expected["b"].astype("int64")
    tm.assert_frame_equal(result, expected)


def test_reset_index_empty_frame_with_datetime64_multiindex_from_groupby(
    using_infer_string,
):
    # https://github.com/pandas-dev/pandas/issues/35657
    dti = pd.DatetimeIndex(["2020-01-01"], dtype="M8[ns]")
    df = DataFrame({"c1": [10.0], "c2": ["a"], "c3": dti})
    df = df.head(0).groupby(["c2", "c3"])[["c1"]].sum()
    result = df.reset_index()
    expected = DataFrame(
        columns=["c2", "c3", "c1"], index=RangeIndex(start=0, stop=0, step=1)
    )
    expected["c3"] = expected["c3"].astype("datetime64[ns]")
    expected["c1"] = expected["c1"].astype("float64")
    if using_infer_string:
        expected["c2"] = expected["c2"].astype("str")
    tm.assert_frame_equal(result, expected)


def test_reset_index_multiindex_nat():
    # GH 11479
    idx = range(3)
    tstamp = date_range("2015-07-01", freq="D", periods=3)
    df = DataFrame({"id": idx, "tstamp": tstamp, "a": list("abc")})
    df.loc[2, "tstamp"] = pd.NaT
    result = df.set_index(["id", "tstamp"]).reset_index("id")
    exp_dti = pd.DatetimeIndex(
        ["2015-07-01", "2015-07-02", "NaT"], dtype="M8[ns]", name="tstamp"
    )
    expected = DataFrame(
        {"id": range(3), "a": list("abc")},
        index=exp_dti,
    )
    tm.assert_frame_equal(result, expected)


def test_reset_index_interval_columns_object_cast():
    # GH 19136
    df = DataFrame(
        np.eye(2), index=Index([1, 2], name="Year"), columns=cut([1, 2], [0, 1, 2])
    )
    result = df.reset_index()
    expected = DataFrame(
        [[1, 1.0, 0.0], [2, 0.0, 1.0]],
        columns=Index(["Year", Interval(0, 1), Interval(1, 2)]),
    )
    tm.assert_frame_equal(result, expected)


def test_reset_index_rename(float_frame):
    # GH 6878
    result = float_frame.reset_index(names="new_name")
    expected = Series(float_frame.index.values, name="new_name")
    tm.assert_series_equal(result["new_name"], expected)

    result = float_frame.reset_index(names=123)
    expected = Series(float_frame.index.values, name=123)
    tm.assert_series_equal(result[123], expected)


def test_reset_index_rename_multiindex(float_frame):
    # GH 6878
    stacked_df = float_frame.stack(future_stack=True)[::2]
    stacked_df = DataFrame({"foo": stacked_df, "bar": stacked_df})

    names = ["first", "second"]
    stacked_df.index.names = names

    result = stacked_df.reset_index()
    expected = stacked_df.reset_index(names=["new_first", "new_second"])
    tm.assert_series_equal(result["first"], expected["new_first"], check_names=False)
    tm.assert_series_equal(result["second"], expected["new_second"], check_names=False)


def test_errorreset_index_rename(float_frame):
    # GH 6878
    stacked_df = float_frame.stack(future_stack=True)[::2]
    stacked_df = DataFrame({"first": stacked_df, "second": stacked_df})

    with pytest.raises(
        ValueError, match="Index names must be str or 1-dimensional list"
    ):
        stacked_df.reset_index(names={"first": "new_first", "second": "new_second"})

    with pytest.raises(IndexError, match="list index out of range"):
        stacked_df.reset_index(names=["new_first"])


def test_reset_index_false_index_name():
    result_series = Series(data=range(5, 10), index=range(5))
    result_series.index.name = False
    result_series.reset_index()
    expected_series = Series(range(5, 10), RangeIndex(range(5), name=False))
    tm.assert_series_equal(result_series, expected_series)

    # GH 38147
    result_frame = DataFrame(data=range(5, 10), index=range(5))
    result_frame.index.name = False
    result_frame.reset_index()
    expected_frame = DataFrame(range(5, 10), RangeIndex(range(5), name=False))
    tm.assert_frame_equal(result_frame, expected_frame)


@pytest.mark.parametrize("columns", [None, Index([])])
def test_reset_index_with_empty_frame(columns):
    # Currently empty DataFrame has RangeIndex or object dtype Index, but when
    # resetting the index we still want to end up with the default string dtype
    # https://github.com/pandas-dev/pandas/issues/60338

    index = Index([], name="foo")
    df = DataFrame(index=index, columns=columns)
    result = df.reset_index()
    expected = DataFrame(columns=["foo"])
    tm.assert_frame_equal(result, expected)

    index = Index([1, 2, 3], name="foo")
    df = DataFrame(index=index, columns=columns)
    result = df.reset_index()
    expected = DataFrame({"foo": [1, 2, 3]})
    tm.assert_frame_equal(result, expected)

    index = MultiIndex.from_tuples([], names=["foo", "bar"])
    df = DataFrame(index=index, columns=columns)
    result = df.reset_index()
    expected = DataFrame(columns=["foo", "bar"])
    tm.assert_frame_equal(result, expected)

    index = MultiIndex.from_tuples([(1, 2), (2, 3)], names=["foo", "bar"])
    df = DataFrame(index=index, columns=columns)
    result = df.reset_index()
    expected = DataFrame({"foo": [1, 2], "bar": [2, 3]})
    tm.assert_frame_equal(result, expected)
