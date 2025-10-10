from datetime import datetime

import numpy as np
import pytest

from pandas.errors import SettingWithCopyWarning
import pandas.util._test_decorators as td

from pandas.core.dtypes.base import _registry as ea_registry
from pandas.core.dtypes.common import is_object_dtype
from pandas.core.dtypes.dtypes import (
    CategoricalDtype,
    DatetimeTZDtype,
    IntervalDtype,
    PeriodDtype,
)

import pandas as pd
from pandas import (
    Categorical,
    DataFrame,
    DatetimeIndex,
    Index,
    Interval,
    IntervalIndex,
    MultiIndex,
    NaT,
    Period,
    PeriodIndex,
    Series,
    Timestamp,
    cut,
    date_range,
    notna,
    period_range,
)
import pandas._testing as tm
from pandas.core.arrays import SparseArray

from pandas.tseries.offsets import BDay


class TestDataFrameSetItem:
    def test_setitem_str_subclass(self):
        # GH#37366
        class mystring(str):
            pass

        data = ["2020-10-22 01:21:00+00:00"]
        index = DatetimeIndex(data)
        df = DataFrame({"a": [1]}, index=index)
        df["b"] = 2
        df[mystring("c")] = 3
        expected = DataFrame({"a": [1], "b": [2], mystring("c"): [3]}, index=index)
        tm.assert_equal(df, expected)

    @pytest.mark.parametrize(
        "dtype", ["int32", "int64", "uint32", "uint64", "float32", "float64"]
    )
    def test_setitem_dtype(self, dtype, float_frame):
        # Use integers since casting negative floats to uints is undefined
        arr = np.random.default_rng(2).integers(1, 10, len(float_frame))

        float_frame[dtype] = np.array(arr, dtype=dtype)
        assert float_frame[dtype].dtype.name == dtype

    def test_setitem_list_not_dataframe(self, float_frame):
        data = np.random.default_rng(2).standard_normal((len(float_frame), 2))
        float_frame[["A", "B"]] = data
        tm.assert_almost_equal(float_frame[["A", "B"]].values, data)

    def test_setitem_error_msmgs(self):
        # GH 7432
        df = DataFrame(
            {"bar": [1, 2, 3], "baz": ["d", "e", "f"]},
            index=Index(["a", "b", "c"], name="foo"),
        )
        ser = Series(
            ["g", "h", "i", "j"],
            index=Index(["a", "b", "c", "a"], name="foo"),
            name="fiz",
        )
        msg = "cannot reindex on an axis with duplicate labels"
        with pytest.raises(ValueError, match=msg):
            df["newcol"] = ser

        # GH 4107, more descriptive error message
        df = DataFrame(
            np.random.default_rng(2).integers(0, 2, (4, 4)),
            columns=["a", "b", "c", "d"],
        )

        msg = "Cannot set a DataFrame with multiple columns to the single column gr"
        with pytest.raises(ValueError, match=msg):
            df["gr"] = df.groupby(["b", "c"]).count()

        # GH 55956, specific message for zero columns
        msg = "Cannot set a DataFrame without columns to the column gr"
        with pytest.raises(ValueError, match=msg):
            df["gr"] = DataFrame()

    def test_setitem_benchmark(self):
        # from the vb_suite/frame_methods/frame_insert_columns
        N = 10
        K = 5
        df = DataFrame(index=range(N))
        new_col = np.random.default_rng(2).standard_normal(N)
        for i in range(K):
            df[i] = new_col
        expected = DataFrame(np.repeat(new_col, K).reshape(N, K), index=range(N))
        tm.assert_frame_equal(df, expected)

    def test_setitem_different_dtype(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 3)),
            index=np.arange(5),
            columns=["c", "b", "a"],
        )
        df.insert(0, "foo", df["a"])
        df.insert(2, "bar", df["c"])

        # diff dtype

        # new item
        df["x"] = df["a"].astype("float32")
        result = df.dtypes
        expected = Series(
            [np.dtype("float64")] * 5 + [np.dtype("float32")],
            index=["foo", "c", "bar", "b", "a", "x"],
        )
        tm.assert_series_equal(result, expected)

        # replacing current (in different block)
        df["a"] = df["a"].astype("float32")
        result = df.dtypes
        expected = Series(
            [np.dtype("float64")] * 4 + [np.dtype("float32")] * 2,
            index=["foo", "c", "bar", "b", "a", "x"],
        )
        tm.assert_series_equal(result, expected)

        df["y"] = df["a"].astype("int32")
        result = df.dtypes
        expected = Series(
            [np.dtype("float64")] * 4 + [np.dtype("float32")] * 2 + [np.dtype("int32")],
            index=["foo", "c", "bar", "b", "a", "x", "y"],
        )
        tm.assert_series_equal(result, expected)

    def test_setitem_overwrite_index(self):
        # GH 13522 - assign the index as a column and then overwrite the values
        # -> should not affect the index
        df = DataFrame(index=["A", "B", "C"])
        df["X"] = df.index
        df["X"] = ["x", "y", "z"]
        exp = DataFrame(
            data={"X": ["x", "y", "z"]}, index=["A", "B", "C"], columns=["X"]
        )
        tm.assert_frame_equal(df, exp)

    def test_setitem_empty_columns(self):
        # Starting from an empty DataFrame and setting a column should result
        # in a default string dtype for the columns' Index
        # https://github.com/pandas-dev/pandas/issues/60338

        df = DataFrame()
        df["foo"] = [1, 2, 3]
        expected = DataFrame({"foo": [1, 2, 3]})
        tm.assert_frame_equal(df, expected)

        df = DataFrame(columns=Index([]))
        df["foo"] = [1, 2, 3]
        expected = DataFrame({"foo": [1, 2, 3]})
        tm.assert_frame_equal(df, expected)

    def test_setitem_dt64_index_empty_columns(self):
        rng = date_range("1/1/2000 00:00:00", "1/1/2000 1:59:50", freq="10s")
        df = DataFrame(index=np.arange(len(rng)))

        df["A"] = rng
        assert df["A"].dtype == np.dtype("M8[ns]")

    def test_setitem_timestamp_empty_columns(self):
        # GH#19843
        df = DataFrame(index=range(3))
        df["now"] = Timestamp("20130101", tz="UTC").as_unit("ns")

        expected = DataFrame(
            [[Timestamp("20130101", tz="UTC")]] * 3, index=range(3), columns=["now"]
        )
        tm.assert_frame_equal(df, expected)

    def test_setitem_wrong_length_categorical_dtype_raises(self):
        # GH#29523
        cat = Categorical.from_codes([0, 1, 1, 0, 1, 2], ["a", "b", "c"])
        df = DataFrame(range(10), columns=["bar"])

        msg = (
            rf"Length of values \({len(cat)}\) "
            rf"does not match length of index \({len(df)}\)"
        )
        with pytest.raises(ValueError, match=msg):
            df["foo"] = cat

    def test_setitem_with_sparse_value(self):
        # GH#8131
        df = DataFrame({"c_1": ["a", "b", "c"], "n_1": [1.0, 2.0, 3.0]})
        sp_array = SparseArray([0, 0, 1])
        df["new_column"] = sp_array

        expected = Series(sp_array, name="new_column")
        tm.assert_series_equal(df["new_column"], expected)

    def test_setitem_with_unaligned_sparse_value(self):
        df = DataFrame({"c_1": ["a", "b", "c"], "n_1": [1.0, 2.0, 3.0]})
        sp_series = Series(SparseArray([0, 0, 1]), index=[2, 1, 0])

        df["new_column"] = sp_series
        expected = Series(SparseArray([1, 0, 0]), name="new_column")
        tm.assert_series_equal(df["new_column"], expected)

    def test_setitem_period_preserves_dtype(self):
        # GH: 26861
        data = [Period("2003-12", "D")]
        result = DataFrame([])
        result["a"] = data

        expected = DataFrame({"a": data}, columns=["a"])

        tm.assert_frame_equal(result, expected)

    def test_setitem_dict_preserves_dtypes(self):
        # https://github.com/pandas-dev/pandas/issues/34573
        expected = DataFrame(
            {
                "a": Series([0, 1, 2], dtype="int64"),
                "b": Series([1, 2, 3], dtype=float),
                "c": Series([1, 2, 3], dtype=float),
                "d": Series([1, 2, 3], dtype="uint32"),
            }
        )
        df = DataFrame(
            {
                "a": Series([], dtype="int64"),
                "b": Series([], dtype=float),
                "c": Series([], dtype=float),
                "d": Series([], dtype="uint32"),
            }
        )
        for idx, b in enumerate([1, 2, 3]):
            df.loc[df.shape[0]] = {
                "a": int(idx),
                "b": float(b),
                "c": float(b),
                "d": np.uint32(b),
            }
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize(
        "obj,dtype",
        [
            (Period("2020-01"), PeriodDtype("M")),
            (Interval(left=0, right=5), IntervalDtype("int64", "right")),
            (
                Timestamp("2011-01-01", tz="US/Eastern"),
                DatetimeTZDtype(unit="s", tz="US/Eastern"),
            ),
        ],
    )
    def test_setitem_extension_types(self, obj, dtype):
        # GH: 34832
        expected = DataFrame({"idx": [1, 2, 3], "obj": Series([obj] * 3, dtype=dtype)})

        df = DataFrame({"idx": [1, 2, 3]})
        df["obj"] = obj

        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize(
        "ea_name",
        [
            dtype.name
            for dtype in ea_registry.dtypes
            # property would require instantiation
            if not isinstance(dtype.name, property)
        ]
        + ["datetime64[ns, UTC]", "period[D]"],
    )
    def test_setitem_with_ea_name(self, ea_name):
        # GH 38386
        result = DataFrame([0])
        result[ea_name] = [1]
        expected = DataFrame({0: [0], ea_name: [1]})
        tm.assert_frame_equal(result, expected)

    def test_setitem_dt64_ndarray_with_NaT_and_diff_time_units(self):
        # GH#7492
        data_ns = np.array([1, "nat"], dtype="datetime64[ns]")
        result = Series(data_ns).to_frame()
        result["new"] = data_ns
        expected = DataFrame({0: [1, None], "new": [1, None]}, dtype="datetime64[ns]")
        tm.assert_frame_equal(result, expected)

        # OutOfBoundsDatetime error shouldn't occur; as of 2.0 we preserve "M8[s]"
        data_s = np.array([1, "nat"], dtype="datetime64[s]")
        result["new"] = data_s
        tm.assert_series_equal(result[0], expected[0])
        tm.assert_numpy_array_equal(result["new"].to_numpy(), data_s)

    @pytest.mark.parametrize("unit", ["h", "m", "s", "ms", "D", "M", "Y"])
    def test_frame_setitem_datetime64_col_other_units(self, unit):
        # Check that non-nano dt64 values get cast to dt64 on setitem
        #  into a not-yet-existing column
        n = 100

        dtype = np.dtype(f"M8[{unit}]")
        vals = np.arange(n, dtype=np.int64).view(dtype)
        if unit in ["s", "ms"]:
            # supported unit
            ex_vals = vals
        else:
            # we get the nearest supported units, i.e. "s"
            ex_vals = vals.astype("datetime64[s]")

        df = DataFrame({"ints": np.arange(n)}, index=np.arange(n))
        df[unit] = vals

        assert df[unit].dtype == ex_vals.dtype
        assert (df[unit].values == ex_vals).all()

    @pytest.mark.parametrize("unit", ["h", "m", "s", "ms", "D", "M", "Y"])
    def test_frame_setitem_existing_datetime64_col_other_units(self, unit):
        # Check that non-nano dt64 values get cast to dt64 on setitem
        #  into an already-existing dt64 column
        n = 100

        dtype = np.dtype(f"M8[{unit}]")
        vals = np.arange(n, dtype=np.int64).view(dtype)
        ex_vals = vals.astype("datetime64[ns]")

        df = DataFrame({"ints": np.arange(n)}, index=np.arange(n))
        df["dates"] = np.arange(n, dtype=np.int64).view("M8[ns]")

        # We overwrite existing dt64 column with new, non-nano dt64 vals
        df["dates"] = vals
        assert (df["dates"].values == ex_vals).all()

    def test_setitem_dt64tz(self, timezone_frame, using_copy_on_write):
        df = timezone_frame
        idx = df["B"].rename("foo")

        # setitem
        df["C"] = idx
        tm.assert_series_equal(df["C"], Series(idx, name="C"))

        df["D"] = "foo"
        df["D"] = idx
        tm.assert_series_equal(df["D"], Series(idx, name="D"))
        del df["D"]

        # assert that A & C are not sharing the same base (e.g. they
        # are copies)
        # Note: This does not hold with Copy on Write (because of lazy copying)
        v1 = df._mgr.arrays[1]
        v2 = df._mgr.arrays[2]
        tm.assert_extension_array_equal(v1, v2)
        v1base = v1._ndarray.base
        v2base = v2._ndarray.base
        if not using_copy_on_write:
            assert v1base is None or (id(v1base) != id(v2base))
        else:
            assert id(v1base) == id(v2base)

        # with nan
        df2 = df.copy()
        df2.iloc[1, 1] = NaT
        df2.iloc[1, 2] = NaT
        result = df2["B"]
        tm.assert_series_equal(notna(result), Series([True, False, True], name="B"))
        tm.assert_series_equal(df2.dtypes, df.dtypes)

    def test_setitem_periodindex(self):
        rng = period_range("1/1/2000", periods=5, name="index")
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)), index=rng)

        df["Index"] = rng
        rs = Index(df["Index"])
        tm.assert_index_equal(rs, rng, check_names=False)
        assert rs.name == "Index"
        assert rng.name == "index"

        rs = df.reset_index().set_index("index")
        assert isinstance(rs.index, PeriodIndex)
        tm.assert_index_equal(rs.index, rng)

    def test_setitem_complete_column_with_array(self):
        # GH#37954
        df = DataFrame({"a": ["one", "two", "three"], "b": [1, 2, 3]})
        arr = np.array([[1, 1], [3, 1], [5, 1]])
        df[["c", "d"]] = arr
        expected = DataFrame(
            {
                "a": ["one", "two", "three"],
                "b": [1, 2, 3],
                "c": [1, 3, 5],
                "d": [1, 1, 1],
            }
        )
        expected["c"] = expected["c"].astype(arr.dtype)
        expected["d"] = expected["d"].astype(arr.dtype)
        assert expected["c"].dtype == arr.dtype
        assert expected["d"].dtype == arr.dtype
        tm.assert_frame_equal(df, expected)

    def test_setitem_period_d_dtype(self):
        # GH 39763
        rng = period_range("2016-01-01", periods=9, freq="D", name="A")
        result = DataFrame(rng)
        expected = DataFrame(
            {"A": ["NaT", "NaT", "NaT", "NaT", "NaT", "NaT", "NaT", "NaT", "NaT"]},
            dtype="period[D]",
        )
        result.iloc[:] = rng._na_value
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("dtype", ["f8", "i8", "u8"])
    def test_setitem_bool_with_numeric_index(self, dtype):
        # GH#36319
        cols = Index([1, 2, 3], dtype=dtype)
        df = DataFrame(np.random.default_rng(2).standard_normal((3, 3)), columns=cols)

        df[False] = ["a", "b", "c"]

        expected_cols = Index([1, 2, 3, False], dtype=object)
        if dtype == "f8":
            expected_cols = Index([1.0, 2.0, 3.0, False], dtype=object)

        tm.assert_index_equal(df.columns, expected_cols)

    @pytest.mark.parametrize("indexer", ["B", ["B"]])
    def test_setitem_frame_length_0_str_key(self, indexer):
        # GH#38831
        df = DataFrame(columns=["A", "B"])
        other = DataFrame({"B": [1, 2]})
        df[indexer] = other
        expected = DataFrame({"A": [np.nan] * 2, "B": [1, 2]})
        expected["A"] = expected["A"].astype("object")
        tm.assert_frame_equal(df, expected)

    def test_setitem_frame_duplicate_columns(self):
        # GH#15695
        cols = ["A", "B", "C"] * 2
        df = DataFrame(index=range(3), columns=cols)
        df.loc[0, "A"] = (0, 3)
        df.loc[:, "B"] = (1, 4)
        df["C"] = (2, 5)
        expected = DataFrame(
            [
                [0, 1, 2, 3, 4, 5],
                [np.nan, 1, 2, np.nan, 4, 5],
                [np.nan, 1, 2, np.nan, 4, 5],
            ],
            dtype="object",
        )

        # set these with unique columns to be extra-unambiguous
        expected[2] = expected[2].astype(np.int64)
        expected[5] = expected[5].astype(np.int64)
        expected.columns = cols

        tm.assert_frame_equal(df, expected)

    def test_setitem_frame_duplicate_columns_size_mismatch(self):
        # GH#39510
        cols = ["A", "B", "C"] * 2
        df = DataFrame(index=range(3), columns=cols)
        with pytest.raises(ValueError, match="Columns must be same length as key"):
            df[["A"]] = (0, 3, 5)

        df2 = df.iloc[:, :3]  # unique columns
        with pytest.raises(ValueError, match="Columns must be same length as key"):
            df2[["A"]] = (0, 3, 5)

    @pytest.mark.parametrize("cols", [["a", "b", "c"], ["a", "a", "a"]])
    def test_setitem_df_wrong_column_number(self, cols):
        # GH#38604
        df = DataFrame([[1, 2, 3]], columns=cols)
        rhs = DataFrame([[10, 11]], columns=["d", "e"])
        msg = "Columns must be same length as key"
        with pytest.raises(ValueError, match=msg):
            df["a"] = rhs

    def test_setitem_listlike_indexer_duplicate_columns(self):
        # GH#38604
        df = DataFrame([[1, 2, 3]], columns=["a", "b", "b"])
        rhs = DataFrame([[10, 11, 12]], columns=["a", "b", "b"])
        df[["a", "b"]] = rhs
        expected = DataFrame([[10, 11, 12]], columns=["a", "b", "b"])
        tm.assert_frame_equal(df, expected)

        df[["c", "b"]] = rhs
        expected = DataFrame([[10, 11, 12, 10]], columns=["a", "b", "b", "c"])
        tm.assert_frame_equal(df, expected)

    def test_setitem_listlike_indexer_duplicate_columns_not_equal_length(self):
        # GH#39403
        df = DataFrame([[1, 2, 3]], columns=["a", "b", "b"])
        rhs = DataFrame([[10, 11]], columns=["a", "b"])
        msg = "Columns must be same length as key"
        with pytest.raises(ValueError, match=msg):
            df[["a", "b"]] = rhs

    def test_setitem_intervals(self):
        df = DataFrame({"A": range(10)})
        ser = cut(df["A"], 5)
        assert isinstance(ser.cat.categories, IntervalIndex)

        # B & D end up as Categoricals
        # the remainder are converted to in-line objects
        # containing an IntervalIndex.values
        df["B"] = ser
        df["C"] = np.array(ser)
        df["D"] = ser.values
        df["E"] = np.array(ser.values)
        df["F"] = ser.astype(object)

        assert isinstance(df["B"].dtype, CategoricalDtype)
        assert isinstance(df["B"].cat.categories.dtype, IntervalDtype)
        assert isinstance(df["D"].dtype, CategoricalDtype)
        assert isinstance(df["D"].cat.categories.dtype, IntervalDtype)

        # These go through the Series constructor and so get inferred back
        #  to IntervalDtype
        assert isinstance(df["C"].dtype, IntervalDtype)
        assert isinstance(df["E"].dtype, IntervalDtype)

        # But the Series constructor doesn't do inference on Series objects,
        #  so setting df["F"] doesn't get cast back to IntervalDtype
        assert is_object_dtype(df["F"])

        # they compare equal as Index
        # when converted to numpy objects
        c = lambda x: Index(np.array(x))
        tm.assert_index_equal(c(df.B), c(df.B))
        tm.assert_index_equal(c(df.B), c(df.C), check_names=False)
        tm.assert_index_equal(c(df.B), c(df.D), check_names=False)
        tm.assert_index_equal(c(df.C), c(df.D), check_names=False)

        # B & D are the same Series
        tm.assert_series_equal(df["B"], df["B"])
        tm.assert_series_equal(df["B"], df["D"], check_names=False)

        # C & E are the same Series
        tm.assert_series_equal(df["C"], df["C"])
        tm.assert_series_equal(df["C"], df["E"], check_names=False)

    def test_setitem_categorical(self):
        # GH#35369
        df = DataFrame({"h": Series(list("mn")).astype("category")})
        df.h = df.h.cat.reorder_categories(["n", "m"])
        expected = DataFrame(
            {"h": Categorical(["m", "n"]).reorder_categories(["n", "m"])}
        )
        tm.assert_frame_equal(df, expected)

    def test_setitem_with_empty_listlike(self):
        # GH#17101
        index = Index([], name="idx")
        result = DataFrame(columns=["A"], index=index)
        result["A"] = []
        expected = DataFrame(columns=["A"], index=index)
        tm.assert_index_equal(result.index, expected.index)

    @pytest.mark.parametrize(
        "cols, values, expected",
        [
            (["C", "D", "D", "a"], [1, 2, 3, 4], 4),  # with duplicates
            (["D", "C", "D", "a"], [1, 2, 3, 4], 4),  # mixed order
            (["C", "B", "B", "a"], [1, 2, 3, 4], 4),  # other duplicate cols
            (["C", "B", "a"], [1, 2, 3], 3),  # no duplicates
            (["B", "C", "a"], [3, 2, 1], 1),  # alphabetical order
            (["C", "a", "B"], [3, 2, 1], 2),  # in the middle
        ],
    )
    def test_setitem_same_column(self, cols, values, expected):
        # GH#23239
        df = DataFrame([values], columns=cols)
        df["a"] = df["a"]
        result = df["a"].values[0]
        assert result == expected

    def test_setitem_multi_index(self):
        # GH#7655, test that assigning to a sub-frame of a frame
        # with multi-index columns aligns both rows and columns
        it = ["jim", "joe", "jolie"], ["first", "last"], ["left", "center", "right"]

        cols = MultiIndex.from_product(it)
        index = date_range("20141006", periods=20)
        vals = np.random.default_rng(2).integers(1, 1000, (len(index), len(cols)))
        df = DataFrame(vals, columns=cols, index=index)

        i, j = df.index.values.copy(), it[-1][:]

        np.random.default_rng(2).shuffle(i)
        df["jim"] = df["jolie"].loc[i, ::-1]
        tm.assert_frame_equal(df["jim"], df["jolie"])

        np.random.default_rng(2).shuffle(j)
        df[("joe", "first")] = df[("jolie", "last")].loc[i, j]
        tm.assert_frame_equal(df[("joe", "first")], df[("jolie", "last")])

        np.random.default_rng(2).shuffle(j)
        df[("joe", "last")] = df[("jolie", "first")].loc[i, j]
        tm.assert_frame_equal(df[("joe", "last")], df[("jolie", "first")])

    @pytest.mark.parametrize(
        "columns,box,expected",
        [
            (
                ["A", "B", "C", "D"],
                7,
                DataFrame(
                    [[7, 7, 7, 7], [7, 7, 7, 7], [7, 7, 7, 7]],
                    columns=["A", "B", "C", "D"],
                ),
            ),
            (
                ["C", "D"],
                [7, 8],
                DataFrame(
                    [[1, 2, 7, 8], [3, 4, 7, 8], [5, 6, 7, 8]],
                    columns=["A", "B", "C", "D"],
                ),
            ),
            (
                ["A", "B", "C"],
                np.array([7, 8, 9], dtype=np.int64),
                DataFrame([[7, 8, 9], [7, 8, 9], [7, 8, 9]], columns=["A", "B", "C"]),
            ),
            (
                ["B", "C", "D"],
                [[7, 8, 9], [10, 11, 12], [13, 14, 15]],
                DataFrame(
                    [[1, 7, 8, 9], [3, 10, 11, 12], [5, 13, 14, 15]],
                    columns=["A", "B", "C", "D"],
                ),
            ),
            (
                ["C", "A", "D"],
                np.array([[7, 8, 9], [10, 11, 12], [13, 14, 15]], dtype=np.int64),
                DataFrame(
                    [[8, 2, 7, 9], [11, 4, 10, 12], [14, 6, 13, 15]],
                    columns=["A", "B", "C", "D"],
                ),
            ),
            (
                ["A", "C"],
                DataFrame([[7, 8], [9, 10], [11, 12]], columns=["A", "C"]),
                DataFrame(
                    [[7, 2, 8], [9, 4, 10], [11, 6, 12]], columns=["A", "B", "C"]
                ),
            ),
        ],
    )
    def test_setitem_list_missing_columns(self, columns, box, expected):
        # GH#29334
        df = DataFrame([[1, 2], [3, 4], [5, 6]], columns=["A", "B"])
        df[columns] = box
        tm.assert_frame_equal(df, expected)

    def test_setitem_list_of_tuples(self, float_frame):
        tuples = list(zip(float_frame["A"], float_frame["B"]))
        float_frame["tuples"] = tuples

        result = float_frame["tuples"]
        expected = Series(tuples, index=float_frame.index, name="tuples")
        tm.assert_series_equal(result, expected)

    def test_setitem_iloc_generator(self):
        # GH#39614
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        indexer = (x for x in [1, 2])
        df.iloc[indexer] = 1
        expected = DataFrame({"a": [1, 1, 1], "b": [4, 1, 1]})
        tm.assert_frame_equal(df, expected)

    def test_setitem_iloc_two_dimensional_generator(self):
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        indexer = (x for x in [1, 2])
        df.iloc[indexer, 1] = 1
        expected = DataFrame({"a": [1, 2, 3], "b": [4, 1, 1]})
        tm.assert_frame_equal(df, expected)

    def test_setitem_dtypes_bytes_type_to_object(self):
        # GH 20734
        index = Series(name="id", dtype="S24")
        df = DataFrame(index=index, columns=Index([], dtype="str"))
        df["a"] = Series(name="a", index=index, dtype=np.uint32)
        df["b"] = Series(name="b", index=index, dtype="S64")
        df["c"] = Series(name="c", index=index, dtype="S64")
        df["d"] = Series(name="d", index=index, dtype=np.uint8)
        result = df.dtypes
        expected = Series([np.uint32, object, object, np.uint8], index=list("abcd"))
        tm.assert_series_equal(result, expected)

    def test_boolean_mask_nullable_int64(self):
        # GH 28928
        result = DataFrame({"a": [3, 4], "b": [5, 6]}).astype(
            {"a": "int64", "b": "Int64"}
        )
        mask = Series(False, index=result.index)
        result.loc[mask, "a"] = result["a"]
        result.loc[mask, "b"] = result["b"]
        expected = DataFrame({"a": [3, 4], "b": [5, 6]}).astype(
            {"a": "int64", "b": "Int64"}
        )
        tm.assert_frame_equal(result, expected)

    def test_setitem_ea_dtype_rhs_series(self):
        # GH#47425
        df = DataFrame({"a": [1, 2]})
        df["a"] = Series([1, 2], dtype="Int64")
        expected = DataFrame({"a": [1, 2]}, dtype="Int64")
        tm.assert_frame_equal(df, expected)

    # TODO(ArrayManager) set column with 2d column array, see #44788
    @td.skip_array_manager_not_yet_implemented
    def test_setitem_npmatrix_2d(self):
        # GH#42376
        # for use-case df["x"] = sparse.random((10, 10)).mean(axis=1)
        expected = DataFrame(
            {"np-array": np.ones(10), "np-matrix": np.ones(10)}, index=np.arange(10)
        )

        a = np.ones((10, 1))
        df = DataFrame(index=np.arange(10), columns=Index([], dtype="str"))
        df["np-array"] = a

        # Instantiation of `np.matrix` gives PendingDeprecationWarning
        with tm.assert_produces_warning(PendingDeprecationWarning):
            df["np-matrix"] = np.matrix(a)

        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize("vals", [{}, {"d": "a"}])
    def test_setitem_aligning_dict_with_index(self, vals):
        # GH#47216
        df = DataFrame({"a": [1, 2], "b": [3, 4], **vals})
        df.loc[:, "a"] = {1: 100, 0: 200}
        df.loc[:, "c"] = {0: 5, 1: 6}
        df.loc[:, "e"] = {1: 5}
        expected = DataFrame(
            {"a": [200, 100], "b": [3, 4], **vals, "c": [5, 6], "e": [np.nan, 5]}
        )
        tm.assert_frame_equal(df, expected)

    def test_setitem_rhs_dataframe(self):
        # GH#47578
        df = DataFrame({"a": [1, 2]})
        df["a"] = DataFrame({"a": [10, 11]}, index=[1, 2])
        expected = DataFrame({"a": [np.nan, 10]})
        tm.assert_frame_equal(df, expected)

        df = DataFrame({"a": [1, 2]})
        df.isetitem(0, DataFrame({"a": [10, 11]}, index=[1, 2]))
        tm.assert_frame_equal(df, expected)

    def test_setitem_frame_overwrite_with_ea_dtype(self, any_numeric_ea_dtype):
        # GH#46896
        df = DataFrame(columns=["a", "b"], data=[[1, 2], [3, 4]])
        df["a"] = DataFrame({"a": [10, 11]}, dtype=any_numeric_ea_dtype)
        expected = DataFrame(
            {
                "a": Series([10, 11], dtype=any_numeric_ea_dtype),
                "b": [2, 4],
            }
        )
        tm.assert_frame_equal(df, expected)

    def test_setitem_string_option_object_index(self):
        # GH#55638
        pytest.importorskip("pyarrow")
        df = DataFrame({"a": [1, 2]})
        with pd.option_context("future.infer_string", True):
            df["b"] = Index(["a", "b"], dtype=object)
        expected = DataFrame({"a": [1, 2], "b": Series(["a", "b"], dtype=object)})
        tm.assert_frame_equal(df, expected)

    def test_setitem_frame_midx_columns(self):
        # GH#49121
        df = DataFrame({("a", "b"): [10]})
        expected = df.copy()
        col_name = ("a", "b")
        df[col_name] = df[[col_name]]
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_ea_dtype(self):
        # GH#55604
        df = DataFrame({"a": np.array([10], dtype="i8")})
        df.loc[:, "a"] = Series([11], dtype="Int64")
        expected = DataFrame({"a": np.array([11], dtype="i8")})
        tm.assert_frame_equal(df, expected)

        df = DataFrame({"a": np.array([10], dtype="i8")})
        df.iloc[:, 0] = Series([11], dtype="Int64")
        tm.assert_frame_equal(df, expected)

    def test_setitem_object_inferring(self):
        # GH#56102
        idx = Index([Timestamp("2019-12-31")], dtype=object)
        df = DataFrame({"a": [1]})
        with tm.assert_produces_warning(FutureWarning, match="infer"):
            df.loc[:, "b"] = idx
        with tm.assert_produces_warning(FutureWarning, match="infer"):
            df["c"] = idx

        expected = DataFrame(
            {
                "a": [1],
                "b": Series([Timestamp("2019-12-31")], dtype="datetime64[ns]"),
                "c": Series([Timestamp("2019-12-31")], dtype="datetime64[ns]"),
            }
        )
        tm.assert_frame_equal(df, expected)


class TestSetitemTZAwareValues:
    @pytest.fixture
    def idx(self):
        naive = DatetimeIndex(["2013-1-1 13:00", "2013-1-2 14:00"], name="B")
        idx = naive.tz_localize("US/Pacific")
        return idx

    @pytest.fixture
    def expected(self, idx):
        expected = Series(np.array(idx.tolist(), dtype="object"), name="B")
        assert expected.dtype == idx.dtype
        return expected

    def test_setitem_dt64series(self, idx, expected):
        # convert to utc
        df = DataFrame(np.random.default_rng(2).standard_normal((2, 1)), columns=["A"])
        df["B"] = idx
        df["B"] = idx.to_series(index=[0, 1]).dt.tz_convert(None)

        result = df["B"]
        comp = Series(idx.tz_convert("UTC").tz_localize(None), name="B")
        tm.assert_series_equal(result, comp)

    def test_setitem_datetimeindex(self, idx, expected):
        # setting a DataFrame column with a tzaware DTI retains the dtype
        df = DataFrame(np.random.default_rng(2).standard_normal((2, 1)), columns=["A"])

        # assign to frame
        df["B"] = idx
        result = df["B"]
        tm.assert_series_equal(result, expected)

    def test_setitem_object_array_of_tzaware_datetimes(self, idx, expected):
        # setting a DataFrame column with a tzaware DTI retains the dtype
        df = DataFrame(np.random.default_rng(2).standard_normal((2, 1)), columns=["A"])

        # object array of datetimes with a tz
        df["B"] = idx.to_pydatetime()
        result = df["B"]
        tm.assert_series_equal(result, expected)


class TestDataFrameSetItemWithExpansion:
    def test_setitem_listlike_views(self, using_copy_on_write, warn_copy_on_write):
        # GH#38148
        df = DataFrame({"a": [1, 2, 3], "b": [4, 4, 6]})

        # get one column as a view of df
        ser = df["a"]

        # add columns with list-like indexer
        df[["c", "d"]] = np.array([[0.1, 0.2], [0.3, 0.4], [0.4, 0.5]])

        # edit in place the first column to check view semantics
        with tm.assert_cow_warning(warn_copy_on_write):
            df.iloc[0, 0] = 100

        if using_copy_on_write:
            expected = Series([1, 2, 3], name="a")
        else:
            expected = Series([100, 2, 3], name="a")
        tm.assert_series_equal(ser, expected)

    def test_setitem_string_column_numpy_dtype_raising(self):
        # GH#39010
        df = DataFrame([[1, 2], [3, 4]])
        df["0 - Name"] = [5, 6]
        expected = DataFrame([[1, 2, 5], [3, 4, 6]], columns=[0, 1, "0 - Name"])
        tm.assert_frame_equal(df, expected)

    def test_setitem_empty_df_duplicate_columns(self, using_copy_on_write):
        # GH#38521
        df = DataFrame(columns=["a", "b", "b"], dtype="float64")
        df.loc[:, "a"] = list(range(2))
        expected = DataFrame(
            [[0, np.nan, np.nan], [1, np.nan, np.nan]], columns=["a", "b", "b"]
        )
        tm.assert_frame_equal(df, expected)

    def test_setitem_with_expansion_categorical_dtype(self):
        # assignment
        df = DataFrame(
            {
                "value": np.array(
                    np.random.default_rng(2).integers(0, 10000, 100), dtype="int32"
                )
            }
        )
        labels = Categorical([f"{i} - {i + 499}" for i in range(0, 10000, 500)])

        df = df.sort_values(by=["value"], ascending=True)
        ser = cut(df.value, range(0, 10500, 500), right=False, labels=labels)
        cat = ser.values

        # setting with a Categorical
        df["D"] = cat
        result = df.dtypes
        expected = Series(
            [np.dtype("int32"), CategoricalDtype(categories=labels, ordered=False)],
            index=["value", "D"],
        )
        tm.assert_series_equal(result, expected)

        # setting with a Series
        df["E"] = ser
        result = df.dtypes
        expected = Series(
            [
                np.dtype("int32"),
                CategoricalDtype(categories=labels, ordered=False),
                CategoricalDtype(categories=labels, ordered=False),
            ],
            index=["value", "D", "E"],
        )
        tm.assert_series_equal(result, expected)

        result1 = df["D"]
        result2 = df["E"]
        tm.assert_categorical_equal(result1._mgr.array, cat)

        # sorting
        ser.name = "E"
        tm.assert_series_equal(result2.sort_index(), ser.sort_index())

    def test_setitem_scalars_no_index(self):
        # GH#16823 / GH#17894
        df = DataFrame()
        df["foo"] = 1
        expected = DataFrame(columns=["foo"]).astype(np.int64)
        tm.assert_frame_equal(df, expected)

    def test_setitem_newcol_tuple_key(self, float_frame):
        assert (
            "A",
            "B",
        ) not in float_frame.columns
        float_frame["A", "B"] = float_frame["A"]
        assert ("A", "B") in float_frame.columns

        result = float_frame["A", "B"]
        expected = float_frame["A"]
        tm.assert_series_equal(result, expected, check_names=False)

    def test_frame_setitem_newcol_timestamp(self):
        # GH#2155
        columns = date_range(start="1/1/2012", end="2/1/2012", freq=BDay())
        data = DataFrame(columns=columns, index=range(10))
        t = datetime(2012, 11, 1)
        ts = Timestamp(t)
        data[ts] = np.nan  # works, mostly a smoke-test
        assert np.isnan(data[ts]).all()

    def test_frame_setitem_rangeindex_into_new_col(self):
        # GH#47128
        df = DataFrame({"a": ["a", "b"]})
        df["b"] = df.index
        df.loc[[False, True], "b"] = 100
        result = df.loc[[1], :]
        expected = DataFrame({"a": ["b"], "b": [100]}, index=[1])
        tm.assert_frame_equal(result, expected)

    def test_setitem_frame_keep_ea_dtype(self, any_numeric_ea_dtype):
        # GH#46896
        df = DataFrame(columns=["a", "b"], data=[[1, 2], [3, 4]])
        df["c"] = DataFrame({"a": [10, 11]}, dtype=any_numeric_ea_dtype)
        expected = DataFrame(
            {
                "a": [1, 3],
                "b": [2, 4],
                "c": Series([10, 11], dtype=any_numeric_ea_dtype),
            }
        )
        tm.assert_frame_equal(df, expected)

    def test_loc_expansion_with_timedelta_type(self):
        result = DataFrame(columns=list("abc"))
        result.loc[0] = {
            "a": pd.to_timedelta(5, unit="s"),
            "b": pd.to_timedelta(72, unit="s"),
            "c": "23",
        }
        expected = DataFrame(
            [[pd.Timedelta("0 days 00:00:05"), pd.Timedelta("0 days 00:01:12"), "23"]],
            index=Index([0]),
            columns=(["a", "b", "c"]),
        )
        tm.assert_frame_equal(result, expected)


class TestDataFrameSetItemSlicing:
    def test_setitem_slice_position(self):
        # GH#31469
        df = DataFrame(np.zeros((100, 1)))
        df[-4:] = 1
        arr = np.zeros((100, 1))
        arr[-4:] = 1
        expected = DataFrame(arr)
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize("indexer", [tm.setitem, tm.iloc])
    @pytest.mark.parametrize("box", [Series, np.array, list, pd.array])
    @pytest.mark.parametrize("n", [1, 2, 3])
    def test_setitem_slice_indexer_broadcasting_rhs(self, n, box, indexer):
        # GH#40440
        df = DataFrame([[1, 3, 5]] + [[2, 4, 6]] * n, columns=["a", "b", "c"])
        indexer(df)[1:] = box([10, 11, 12])
        expected = DataFrame([[1, 3, 5]] + [[10, 11, 12]] * n, columns=["a", "b", "c"])
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize("box", [Series, np.array, list, pd.array])
    @pytest.mark.parametrize("n", [1, 2, 3])
    def test_setitem_list_indexer_broadcasting_rhs(self, n, box):
        # GH#40440
        df = DataFrame([[1, 3, 5]] + [[2, 4, 6]] * n, columns=["a", "b", "c"])
        df.iloc[list(range(1, n + 1))] = box([10, 11, 12])
        expected = DataFrame([[1, 3, 5]] + [[10, 11, 12]] * n, columns=["a", "b", "c"])
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize("indexer", [tm.setitem, tm.iloc])
    @pytest.mark.parametrize("box", [Series, np.array, list, pd.array])
    @pytest.mark.parametrize("n", [1, 2, 3])
    def test_setitem_slice_broadcasting_rhs_mixed_dtypes(self, n, box, indexer):
        # GH#40440
        df = DataFrame(
            [[1, 3, 5], ["x", "y", "z"]] + [[2, 4, 6]] * n, columns=["a", "b", "c"]
        )
        indexer(df)[1:] = box([10, 11, 12])
        expected = DataFrame(
            [[1, 3, 5]] + [[10, 11, 12]] * (n + 1),
            columns=["a", "b", "c"],
            dtype="object",
        )
        tm.assert_frame_equal(df, expected)


class TestDataFrameSetItemCallable:
    def test_setitem_callable(self):
        # GH#12533
        df = DataFrame({"A": [1, 2, 3, 4], "B": [5, 6, 7, 8]})
        df[lambda x: "A"] = [11, 12, 13, 14]

        exp = DataFrame({"A": [11, 12, 13, 14], "B": [5, 6, 7, 8]})
        tm.assert_frame_equal(df, exp)

    def test_setitem_other_callable(self):
        # GH#13299
        def inc(x):
            return x + 1

        # Set dtype object straight away to avoid upcast when setting inc below
        df = DataFrame([[-1, 1], [1, -1]], dtype=object)
        df[df > 0] = inc

        expected = DataFrame([[-1, inc], [inc, -1]])
        tm.assert_frame_equal(df, expected)


class TestDataFrameSetItemBooleanMask:
    @td.skip_array_manager_invalid_test  # TODO(ArrayManager) rewrite not using .values
    @pytest.mark.parametrize(
        "mask_type",
        [lambda df: df > np.abs(df) / 2, lambda df: (df > np.abs(df) / 2).values],
        ids=["dataframe", "array"],
    )
    def test_setitem_boolean_mask(self, mask_type, float_frame):
        # Test for issue #18582
        df = float_frame.copy()
        mask = mask_type(df)

        # index with boolean mask
        result = df.copy()
        result[mask] = np.nan

        expected = df.values.copy()
        expected[np.array(mask)] = np.nan
        expected = DataFrame(expected, index=df.index, columns=df.columns)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.xfail(reason="Currently empty indexers are treated as all False")
    @pytest.mark.parametrize("box", [list, np.array, Series])
    def test_setitem_loc_empty_indexer_raises_with_non_empty_value(self, box):
        # GH#37672
        df = DataFrame({"a": ["a"], "b": [1], "c": [1]})
        if box == Series:
            indexer = box([], dtype="object")
        else:
            indexer = box([])
        msg = "Must have equal len keys and value when setting with an iterable"
        with pytest.raises(ValueError, match=msg):
            df.loc[indexer, ["b"]] = [1]

    @pytest.mark.parametrize("box", [list, np.array, Series])
    def test_setitem_loc_only_false_indexer_dtype_changed(self, box):
        # GH#37550
        # Dtype is only changed when value to set is a Series and indexer is
        # empty/bool all False
        df = DataFrame({"a": ["a"], "b": [1], "c": [1]})
        indexer = box([False])
        df.loc[indexer, ["b"]] = 10 - df["c"]
        expected = DataFrame({"a": ["a"], "b": [1], "c": [1]})
        tm.assert_frame_equal(df, expected)

        df.loc[indexer, ["b"]] = 9
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize("indexer", [tm.setitem, tm.loc])
    def test_setitem_boolean_mask_aligning(self, indexer):
        # GH#39931
        df = DataFrame({"a": [1, 4, 2, 3], "b": [5, 6, 7, 8]})
        expected = df.copy()
        mask = df["a"] >= 3
        indexer(df)[mask] = indexer(df)[mask].sort_values("a")
        tm.assert_frame_equal(df, expected)

    def test_setitem_mask_categorical(self):
        # assign multiple rows (mixed values) (-> array) -> exp_multi_row
        # changed multiple rows
        cats2 = Categorical(["a", "a", "b", "b", "a", "a", "a"], categories=["a", "b"])
        idx2 = Index(["h", "i", "j", "k", "l", "m", "n"])
        values2 = [1, 1, 2, 2, 1, 1, 1]
        exp_multi_row = DataFrame({"cats": cats2, "values": values2}, index=idx2)

        catsf = Categorical(
            ["a", "a", "c", "c", "a", "a", "a"], categories=["a", "b", "c"]
        )
        idxf = Index(["h", "i", "j", "k", "l", "m", "n"])
        valuesf = [1, 1, 3, 3, 1, 1, 1]
        df = DataFrame({"cats": catsf, "values": valuesf}, index=idxf)

        exp_fancy = exp_multi_row.copy()
        exp_fancy["cats"] = exp_fancy["cats"].cat.set_categories(["a", "b", "c"])

        mask = df["cats"] == "c"
        df[mask] = ["b", 2]
        # category c is kept in .categories
        tm.assert_frame_equal(df, exp_fancy)

    @pytest.mark.parametrize("dtype", ["float", "int64"])
    @pytest.mark.parametrize("kwargs", [{}, {"index": [1]}, {"columns": ["A"]}])
    def test_setitem_empty_frame_with_boolean(self, dtype, kwargs):
        # see GH#10126
        kwargs["dtype"] = dtype
        df = DataFrame(**kwargs)

        df2 = df.copy()
        df[df > df2] = 47
        tm.assert_frame_equal(df, df2)

    def test_setitem_boolean_indexing(self):
        idx = list(range(3))
        cols = ["A", "B", "C"]
        df1 = DataFrame(
            index=idx,
            columns=cols,
            data=np.array(
                [[0.0, 0.5, 1.0], [1.5, 2.0, 2.5], [3.0, 3.5, 4.0]], dtype=float
            ),
        )
        df2 = DataFrame(index=idx, columns=cols, data=np.ones((len(idx), len(cols))))

        expected = DataFrame(
            index=idx,
            columns=cols,
            data=np.array([[0.0, 0.5, 1.0], [1.5, 2.0, -1], [-1, -1, -1]], dtype=float),
        )

        df1[df1 > 2.0 * df2] = -1
        tm.assert_frame_equal(df1, expected)
        with pytest.raises(ValueError, match="Item wrong length"):
            df1[df1.index[:-1] > 2] = -1

    def test_loc_setitem_all_false_boolean_two_blocks(self):
        # GH#40885
        df = DataFrame({"a": [1, 2], "b": [3, 4], "c": "a"})
        expected = df.copy()
        indexer = Series([False, False], name="c")
        df.loc[indexer, ["b"]] = DataFrame({"b": [5, 6]}, index=[0, 1])
        tm.assert_frame_equal(df, expected)

    def test_setitem_ea_boolean_mask(self):
        # GH#47125
        df = DataFrame([[-1, 2], [3, -4]])
        expected = DataFrame([[0, 2], [3, 0]])
        boolean_indexer = DataFrame(
            {
                0: Series([True, False], dtype="boolean"),
                1: Series([pd.NA, True], dtype="boolean"),
            }
        )
        df[boolean_indexer] = 0
        tm.assert_frame_equal(df, expected)


class TestDataFrameSetitemCopyViewSemantics:
    def test_setitem_always_copy(self, float_frame):
        assert "E" not in float_frame.columns
        s = float_frame["A"].copy()
        float_frame["E"] = s

        float_frame.iloc[5:10, float_frame.columns.get_loc("E")] = np.nan
        assert notna(s[5:10]).all()

    @pytest.mark.parametrize("consolidate", [True, False])
    def test_setitem_partial_column_inplace(
        self, consolidate, using_array_manager, using_copy_on_write
    ):
        # This setting should be in-place, regardless of whether frame is
        #  single-block or multi-block
        # GH#304 this used to be incorrectly not-inplace, in which case
        #  we needed to ensure _item_cache was cleared.

        df = DataFrame(
            {"x": [1.1, 2.1, 3.1, 4.1], "y": [5.1, 6.1, 7.1, 8.1]}, index=[0, 1, 2, 3]
        )
        df.insert(2, "z", np.nan)
        if not using_array_manager:
            if consolidate:
                df._consolidate_inplace()
                assert len(df._mgr.blocks) == 1
            else:
                assert len(df._mgr.blocks) == 2

        zvals = df["z"]._values

        df.loc[2:, "z"] = 42

        expected = Series([np.nan, np.nan, 42, 42], index=df.index, name="z")
        tm.assert_series_equal(df["z"], expected)

        # check setting occurred in-place
        if not using_copy_on_write:
            tm.assert_numpy_array_equal(zvals, expected.values)
            assert np.shares_memory(zvals, df["z"]._values)

    def test_setitem_duplicate_columns_not_inplace(self):
        # GH#39510
        cols = ["A", "B"] * 2
        df = DataFrame(0.0, index=[0], columns=cols)
        df_copy = df.copy()
        df_view = df[:]
        df["B"] = (2, 5)

        expected = DataFrame([[0.0, 2, 0.0, 5]], columns=cols)
        tm.assert_frame_equal(df_view, df_copy)
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize(
        "value", [1, np.array([[1], [1]], dtype="int64"), [[1], [1]]]
    )
    def test_setitem_same_dtype_not_inplace(self, value, using_array_manager):
        # GH#39510
        cols = ["A", "B"]
        df = DataFrame(0, index=[0, 1], columns=cols)
        df_copy = df.copy()
        df_view = df[:]
        df[["B"]] = value

        expected = DataFrame([[0, 1], [0, 1]], columns=cols)
        tm.assert_frame_equal(df, expected)
        tm.assert_frame_equal(df_view, df_copy)

    @pytest.mark.parametrize("value", [1.0, np.array([[1.0], [1.0]]), [[1.0], [1.0]]])
    def test_setitem_listlike_key_scalar_value_not_inplace(self, value):
        # GH#39510
        cols = ["A", "B"]
        df = DataFrame(0, index=[0, 1], columns=cols)
        df_copy = df.copy()
        df_view = df[:]
        df[["B"]] = value

        expected = DataFrame([[0, 1.0], [0, 1.0]], columns=cols)
        tm.assert_frame_equal(df_view, df_copy)
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize(
        "indexer",
        [
            "a",
            ["a"],
            pytest.param(
                [True, False],
                marks=pytest.mark.xfail(
                    reason="Boolean indexer incorrectly setting inplace",
                    strict=False,  # passing on some builds, no obvious pattern
                ),
            ),
        ],
    )
    @pytest.mark.parametrize(
        "value, set_value",
        [
            (1, 5),
            (1.0, 5.0),
            (Timestamp("2020-12-31"), Timestamp("2021-12-31")),
            ("a", "b"),
        ],
    )
    def test_setitem_not_operating_inplace(self, value, set_value, indexer):
        # GH#43406
        df = DataFrame({"a": value}, index=[0, 1])
        expected = df.copy()
        view = df[:]
        df[indexer] = set_value
        tm.assert_frame_equal(view, expected)

    @td.skip_array_manager_invalid_test
    def test_setitem_column_update_inplace(
        self, using_copy_on_write, warn_copy_on_write
    ):
        # https://github.com/pandas-dev/pandas/issues/47172

        labels = [f"c{i}" for i in range(10)]
        df = DataFrame({col: np.zeros(len(labels)) for col in labels}, index=labels)
        values = df._mgr.blocks[0].values

        with tm.raises_chained_assignment_error():
            for label in df.columns:
                df[label][label] = 1
        if not using_copy_on_write:
            # diagonal values all updated
            assert np.all(values[np.arange(10), np.arange(10)] == 1)
        else:
            # original dataframe not updated
            assert np.all(values[np.arange(10), np.arange(10)] == 0)

    def test_setitem_column_frame_as_category(self):
        # GH31581
        df = DataFrame([1, 2, 3])
        df["col1"] = DataFrame([1, 2, 3], dtype="category")
        df["col2"] = Series([1, 2, 3], dtype="category")

        expected_types = Series(
            ["int64", "category", "category"], index=[0, "col1", "col2"], dtype=object
        )
        tm.assert_series_equal(df.dtypes, expected_types)

    @pytest.mark.parametrize("dtype", ["int64", "Int64"])
    def test_setitem_iloc_with_numpy_array(self, dtype):
        # GH-33828
        df = DataFrame({"a": np.ones(3)}, dtype=dtype)
        df.iloc[np.array([0]), np.array([0])] = np.array([[2]])

        expected = DataFrame({"a": [2, 1, 1]}, dtype=dtype)
        tm.assert_frame_equal(df, expected)

    def test_setitem_frame_dup_cols_dtype(self):
        # GH#53143
        df = DataFrame([[1, 2, 3, 4], [4, 5, 6, 7]], columns=["a", "b", "a", "c"])
        rhs = DataFrame([[0, 1.5], [2, 2.5]], columns=["a", "a"])
        df["a"] = rhs
        expected = DataFrame(
            [[0, 2, 1.5, 4], [2, 5, 2.5, 7]], columns=["a", "b", "a", "c"]
        )
        tm.assert_frame_equal(df, expected)

        df = DataFrame([[1, 2, 3], [4, 5, 6]], columns=["a", "a", "b"])
        rhs = DataFrame([[0, 1.5], [2, 2.5]], columns=["a", "a"])
        df["a"] = rhs
        expected = DataFrame([[0, 1.5, 3], [2, 2.5, 6]], columns=["a", "a", "b"])
        tm.assert_frame_equal(df, expected)

    def test_frame_setitem_empty_dataframe(self):
        # GH#28871
        dti = DatetimeIndex(["2000-01-01"], dtype="M8[ns]", name="date")
        df = DataFrame({"date": dti}).set_index("date")
        df = df[0:0].copy()

        df["3010"] = None
        df["2010"] = None

        expected = DataFrame(
            [],
            columns=["3010", "2010"],
            index=dti[:0],
        )
        tm.assert_frame_equal(df, expected)

    def test_iloc_setitem_view_2dblock(self, using_copy_on_write, warn_copy_on_write):
        # https://github.com/pandas-dev/pandas/issues/60309
        df_parent = DataFrame(
            {
                "A": [1, 4, 1, 5],
                "B": [2, 5, 2, 6],
                "C": [3, 6, 1, 7],
                "D": [8, 9, 10, 11],
            }
        )
        df_orig = df_parent.copy()
        df = df_parent[["B", "C"]]

        # Perform the iloc operation
        if using_copy_on_write:
            df.iloc[[1, 3], :] = [[2, 2], [2, 2]]

            # Check that original DataFrame is unchanged
            tm.assert_frame_equal(df_parent, df_orig)
        elif warn_copy_on_write:
            # TODO(COW): should this warn?
            # with tm.assert_cow_warning(warn_copy_on_write):
            df.iloc[[1, 3], :] = [[2, 2], [2, 2]]
        else:
            with pd.option_context("chained_assignment", "warn"):
                with tm.assert_produces_warning(SettingWithCopyWarning):
                    df.iloc[[1, 3], :] = [[2, 2], [2, 2]]

        # Check that df is modified correctly
        expected = DataFrame({"B": [2, 2, 2, 2], "C": [3, 2, 1, 2]}, index=df.index)
        tm.assert_frame_equal(df, expected)

        # with setting to subset of columns
        df = df_parent[["B", "C", "D"]]
        if using_copy_on_write or warn_copy_on_write:
            df.iloc[[1, 3], 0:3:2] = [[2, 2], [2, 2]]
            tm.assert_frame_equal(df_parent, df_orig)
        else:
            with pd.option_context("chained_assignment", "warn"):
                with tm.assert_produces_warning(SettingWithCopyWarning):
                    df.iloc[[1, 3], 0:3:2] = [[2, 2], [2, 2]]

        expected = DataFrame(
            {"B": [2, 2, 2, 2], "C": [3, 6, 1, 7], "D": [8, 2, 10, 2]}, index=df.index
        )
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize(
        "indexer, value",
        [
            (([0, 2], slice(None)), [[2, 2, 2, 2], [2, 2, 2, 2]]),
            ((slice(None), slice(None)), 2),
            ((0, [1, 3]), [2, 2]),
            (([0], 1), [2]),
            (([0], np.int64(1)), [2]),
            ((slice(None), np.int64(1)), [2, 2, 2]),
            ((slice(None, 2), np.int64(1)), [2, 2]),
            (
                (np.array([False, True, False]), np.array([False, True, False, True])),
                [2, 2],
            ),
        ],
    )
    def test_setitem_2dblock_with_ref(
        self, indexer, value, using_copy_on_write, warn_copy_on_write
    ):
        # https://github.com/pandas-dev/pandas/issues/60309
        arr = np.arange(12).reshape(3, 4)

        df_parent = DataFrame(arr.copy(), columns=list("ABCD"))
        # the test is specifically for the case where the df is backed by a single
        # block (taking the non-split path)
        assert df_parent._mgr.is_single_block
        df_orig = df_parent.copy()
        df = df_parent[:]

        with tm.assert_cow_warning(warn_copy_on_write):
            df.iloc[indexer] = value

        # Check that original DataFrame is unchanged
        if using_copy_on_write:
            tm.assert_frame_equal(df_parent, df_orig)

        # Check that df is modified correctly
        arr[indexer] = value
        expected = DataFrame(arr, columns=list("ABCD"))
        tm.assert_frame_equal(df, expected)


def test_full_setter_loc_incompatible_dtype():
    # https://github.com/pandas-dev/pandas/issues/55791
    df = DataFrame({"a": [1, 2]})
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        df.loc[:, "a"] = True
    expected = DataFrame({"a": [True, True]})
    tm.assert_frame_equal(df, expected)

    df = DataFrame({"a": [1, 2]})
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        df.loc[:, "a"] = {0: 3.5, 1: 4.5}
    expected = DataFrame({"a": [3.5, 4.5]})
    tm.assert_frame_equal(df, expected)

    df = DataFrame({"a": [1, 2]})
    df.loc[:, "a"] = {0: 3, 1: 4}
    expected = DataFrame({"a": [3, 4]})
    tm.assert_frame_equal(df, expected)


def test_setitem_partial_row_multiple_columns():
    # https://github.com/pandas-dev/pandas/issues/56503
    df = DataFrame({"A": [1, 2, 3], "B": [4.0, 5, 6]})
    # should not warn
    df.loc[df.index <= 1, ["F", "G"]] = (1, "abc")
    expected = DataFrame(
        {
            "A": [1, 2, 3],
            "B": [4.0, 5, 6],
            "F": [1.0, 1, float("nan")],
            "G": ["abc", "abc", float("nan")],
        }
    )
    tm.assert_frame_equal(df, expected)
