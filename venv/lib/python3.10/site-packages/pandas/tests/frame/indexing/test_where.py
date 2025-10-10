from datetime import datetime

from hypothesis import given
import numpy as np
import pytest

from pandas.core.dtypes.common import is_scalar

import pandas as pd
from pandas import (
    DataFrame,
    DatetimeIndex,
    Index,
    Series,
    StringDtype,
    Timestamp,
    date_range,
    isna,
)
import pandas._testing as tm
from pandas._testing._hypothesis import OPTIONAL_ONE_OF_ALL


@pytest.fixture(params=["default", "float_string", "mixed_float", "mixed_int"])
def where_frame(request, float_string_frame, mixed_float_frame, mixed_int_frame):
    if request.param == "default":
        return DataFrame(
            np.random.default_rng(2).standard_normal((5, 3)), columns=["A", "B", "C"]
        )
    if request.param == "float_string":
        return float_string_frame
    if request.param == "mixed_float":
        return mixed_float_frame
    if request.param == "mixed_int":
        return mixed_int_frame


def _safe_add(df):
    # only add to the numeric items
    def is_ok(s):
        return (
            issubclass(s.dtype.type, (np.integer, np.floating)) and s.dtype != "uint8"
        )

    return DataFrame(dict((c, s + 1) if is_ok(s) else (c, s) for c, s in df.items()))


class TestDataFrameIndexingWhere:
    def test_where_get(self, where_frame, float_string_frame):
        def _check_get(df, cond, check_dtypes=True):
            other1 = _safe_add(df)
            rs = df.where(cond, other1)
            rs2 = df.where(cond.values, other1)
            for k, v in rs.items():
                exp = Series(np.where(cond[k], df[k], other1[k]), index=v.index)
                tm.assert_series_equal(v, exp, check_names=False)
            tm.assert_frame_equal(rs, rs2)

            # dtypes
            if check_dtypes:
                assert (rs.dtypes == df.dtypes).all()

        # check getting
        df = where_frame
        if df is float_string_frame:
            msg = (
                "'>' not supported between instances of 'str' and 'int'"
                "|Invalid comparison"
            )
            with pytest.raises(TypeError, match=msg):
                df > 0
            return
        cond = df > 0
        _check_get(df, cond)

    def test_where_upcasting(self):
        # upcasting case (GH # 2794)
        df = DataFrame(
            {
                c: Series([1] * 3, dtype=c)
                for c in ["float32", "float64", "int32", "int64"]
            }
        )
        df.iloc[1, :] = 0
        result = df.dtypes
        expected = Series(
            [
                np.dtype("float32"),
                np.dtype("float64"),
                np.dtype("int32"),
                np.dtype("int64"),
            ],
            index=["float32", "float64", "int32", "int64"],
        )

        # when we don't preserve boolean casts
        #
        # expected = Series({ 'float32' : 1, 'float64' : 3 })

        tm.assert_series_equal(result, expected)

    @pytest.mark.filterwarnings("ignore:Downcasting object dtype arrays:FutureWarning")
    def test_where_alignment(self, where_frame, float_string_frame):
        # aligning
        def _check_align(df, cond, other, check_dtypes=True):
            rs = df.where(cond, other)
            for i, k in enumerate(rs.columns):
                result = rs[k]
                d = df[k].values
                c = cond[k].reindex(df[k].index).fillna(False).values

                if is_scalar(other):
                    o = other
                elif isinstance(other, np.ndarray):
                    o = Series(other[:, i], index=result.index).values
                else:
                    o = other[k].values

                new_values = d if c.all() else np.where(c, d, o)
                expected = Series(new_values, index=result.index, name=k)

                # since we can't always have the correct numpy dtype
                # as numpy doesn't know how to downcast, don't check
                tm.assert_series_equal(result, expected, check_dtype=False)

            # dtypes
            # can't check dtype when other is an ndarray

            if check_dtypes and not isinstance(other, np.ndarray):
                assert (rs.dtypes == df.dtypes).all()

        df = where_frame
        if df is float_string_frame:
            msg = (
                "'>' not supported between instances of 'str' and 'int'"
                "|Invalid comparison"
            )
            with pytest.raises(TypeError, match=msg):
                df > 0
            return

        # other is a frame
        cond = (df > 0)[1:]
        _check_align(df, cond, _safe_add(df))

        # check other is ndarray
        cond = df > 0
        _check_align(df, cond, (_safe_add(df).values))

        # integers are upcast, so don't check the dtypes
        cond = df > 0
        check_dtypes = all(not issubclass(s.type, np.integer) for s in df.dtypes)
        _check_align(df, cond, np.nan, check_dtypes=check_dtypes)

    # Ignore deprecation warning in Python 3.12 for inverting a bool
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_where_invalid(self):
        # invalid conditions
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 3)), columns=["A", "B", "C"]
        )
        cond = df > 0

        err1 = (df + 1).values[0:2, :]
        msg = "other must be the same shape as self when an ndarray"
        with pytest.raises(ValueError, match=msg):
            df.where(cond, err1)

        err2 = cond.iloc[:2, :].values
        other1 = _safe_add(df)
        msg = "Array conditional must be same shape as self"
        with pytest.raises(ValueError, match=msg):
            df.where(err2, other1)

        with pytest.raises(ValueError, match=msg):
            df.mask(True)
        with pytest.raises(ValueError, match=msg):
            df.mask(0)

    @pytest.mark.filterwarnings("ignore:Downcasting object dtype arrays:FutureWarning")
    def test_where_set(self, where_frame, float_string_frame, mixed_int_frame):
        # where inplace

        def _check_set(df, cond, check_dtypes=True):
            dfi = df.copy()
            econd = cond.reindex_like(df).fillna(True).infer_objects(copy=False)
            expected = dfi.mask(~econd)

            return_value = dfi.where(cond, np.nan, inplace=True)
            assert return_value is None
            tm.assert_frame_equal(dfi, expected)

            # dtypes (and confirm upcasts)x
            if check_dtypes:
                for k, v in df.dtypes.items():
                    if issubclass(v.type, np.integer) and not cond[k].all():
                        v = np.dtype("float64")
                    assert dfi[k].dtype == v

        df = where_frame
        if df is float_string_frame:
            msg = (
                "'>' not supported between instances of 'str' and 'int'"
                "|Invalid comparison"
            )
            with pytest.raises(TypeError, match=msg):
                df > 0
            return
        if df is mixed_int_frame:
            df = df.astype("float64")

        cond = df > 0
        _check_set(df, cond)

        cond = df >= 0
        _check_set(df, cond)

        # aligning
        cond = (df >= 0)[1:]
        _check_set(df, cond)

    def test_where_series_slicing(self):
        # GH 10218
        # test DataFrame.where with Series slicing
        df = DataFrame({"a": range(3), "b": range(4, 7)})
        result = df.where(df["a"] == 1)
        expected = df[df["a"] == 1].reindex(df.index)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("klass", [list, tuple, np.array])
    def test_where_array_like(self, klass):
        # see gh-15414
        df = DataFrame({"a": [1, 2, 3]})
        cond = [[False], [True], [True]]
        expected = DataFrame({"a": [np.nan, 2, 3]})

        result = df.where(klass(cond))
        tm.assert_frame_equal(result, expected)

        df["b"] = 2
        expected["b"] = [2, np.nan, 2]
        cond = [[False, True], [True, False], [True, True]]

        result = df.where(klass(cond))
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "cond",
        [
            [[1], [0], [1]],
            Series([[2], [5], [7]]),
            DataFrame({"a": [2, 5, 7]}),
            [["True"], ["False"], ["True"]],
            [[Timestamp("2017-01-01")], [pd.NaT], [Timestamp("2017-01-02")]],
        ],
    )
    def test_where_invalid_input_single(self, cond):
        # see gh-15414: only boolean arrays accepted
        df = DataFrame({"a": [1, 2, 3]})
        msg = "Boolean array expected for the condition"

        with pytest.raises(ValueError, match=msg):
            df.where(cond)

    @pytest.mark.parametrize(
        "cond",
        [
            [[0, 1], [1, 0], [1, 1]],
            Series([[0, 2], [5, 0], [4, 7]]),
            [["False", "True"], ["True", "False"], ["True", "True"]],
            DataFrame({"a": [2, 5, 7], "b": [4, 8, 9]}),
            [
                [pd.NaT, Timestamp("2017-01-01")],
                [Timestamp("2017-01-02"), pd.NaT],
                [Timestamp("2017-01-03"), Timestamp("2017-01-03")],
            ],
        ],
    )
    def test_where_invalid_input_multiple(self, cond):
        # see gh-15414: only boolean arrays accepted
        df = DataFrame({"a": [1, 2, 3], "b": [2, 2, 2]})
        msg = "Boolean array expected for the condition"

        with pytest.raises(ValueError, match=msg):
            df.where(cond)

    def test_where_dataframe_col_match(self):
        df = DataFrame([[1, 2, 3], [4, 5, 6]])
        cond = DataFrame([[True, False, True], [False, False, True]])

        result = df.where(cond)
        expected = DataFrame([[1.0, np.nan, 3], [np.nan, np.nan, 6]])
        tm.assert_frame_equal(result, expected)

        # this *does* align, though has no matching columns
        cond.columns = ["a", "b", "c"]
        result = df.where(cond)
        expected = DataFrame(np.nan, index=df.index, columns=df.columns)
        tm.assert_frame_equal(result, expected)

    def test_where_ndframe_align(self):
        msg = "Array conditional must be same shape as self"
        df = DataFrame([[1, 2, 3], [4, 5, 6]])

        cond = [True]
        with pytest.raises(ValueError, match=msg):
            df.where(cond)

        expected = DataFrame([[1, 2, 3], [np.nan, np.nan, np.nan]])

        out = df.where(Series(cond))
        tm.assert_frame_equal(out, expected)

        cond = np.array([False, True, False, True])
        with pytest.raises(ValueError, match=msg):
            df.where(cond)

        expected = DataFrame([[np.nan, np.nan, np.nan], [4, 5, 6]])

        out = df.where(Series(cond))
        tm.assert_frame_equal(out, expected)

    def test_where_bug(self):
        # see gh-2793
        df = DataFrame(
            {"a": [1.0, 2.0, 3.0, 4.0], "b": [4.0, 3.0, 2.0, 1.0]}, dtype="float64"
        )
        expected = DataFrame(
            {"a": [np.nan, np.nan, 3.0, 4.0], "b": [4.0, 3.0, np.nan, np.nan]},
            dtype="float64",
        )
        result = df.where(df > 2, np.nan)
        tm.assert_frame_equal(result, expected)

        result = df.copy()
        return_value = result.where(result > 2, np.nan, inplace=True)
        assert return_value is None
        tm.assert_frame_equal(result, expected)

    def test_where_bug_mixed(self, any_signed_int_numpy_dtype):
        # see gh-2793
        df = DataFrame(
            {
                "a": np.array([1, 2, 3, 4], dtype=any_signed_int_numpy_dtype),
                "b": np.array([4.0, 3.0, 2.0, 1.0], dtype="float64"),
            }
        )

        expected = DataFrame(
            {"a": [-1, -1, 3, 4], "b": [4.0, 3.0, -1, -1]},
        ).astype({"a": any_signed_int_numpy_dtype, "b": "float64"})

        result = df.where(df > 2, -1)
        tm.assert_frame_equal(result, expected)

        result = df.copy()
        return_value = result.where(result > 2, -1, inplace=True)
        assert return_value is None
        tm.assert_frame_equal(result, expected)

    def test_where_bug_transposition(self):
        # see gh-7506
        a = DataFrame({0: [1, 2], 1: [3, 4], 2: [5, 6]})
        b = DataFrame({0: [np.nan, 8], 1: [9, np.nan], 2: [np.nan, np.nan]})
        do_not_replace = b.isna() | (a > b)

        expected = a.copy()
        expected[~do_not_replace] = b

        msg = "Downcasting behavior in Series and DataFrame methods 'where'"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = a.where(do_not_replace, b)
        tm.assert_frame_equal(result, expected)

        a = DataFrame({0: [4, 6], 1: [1, 0]})
        b = DataFrame({0: [np.nan, 3], 1: [3, np.nan]})
        do_not_replace = b.isna() | (a > b)

        expected = a.copy()
        expected[~do_not_replace] = b

        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = a.where(do_not_replace, b)
        tm.assert_frame_equal(result, expected)

    def test_where_datetime(self):
        # GH 3311
        df = DataFrame(
            {
                "A": date_range("20130102", periods=5),
                "B": date_range("20130104", periods=5),
                "C": np.random.default_rng(2).standard_normal(5),
            }
        )

        stamp = datetime(2013, 1, 3)
        msg = "'>' not supported between instances of 'float' and 'datetime.datetime'"
        with pytest.raises(TypeError, match=msg):
            df > stamp

        result = df[df.iloc[:, :-1] > stamp]

        expected = df.copy()
        expected.loc[[0, 1], "A"] = np.nan

        expected.loc[:, "C"] = np.nan
        tm.assert_frame_equal(result, expected)

    def test_where_none(self):
        # GH 4667
        # setting with None changes dtype
        df = DataFrame({"series": Series(range(10))}).astype(float)
        df[df > 7] = None
        expected = DataFrame(
            {"series": Series([0, 1, 2, 3, 4, 5, 6, 7, np.nan, np.nan])}
        )
        tm.assert_frame_equal(df, expected)

        # GH 7656
        df = DataFrame(
            [
                {"A": 1, "B": np.nan, "C": "Test"},
                {"A": np.nan, "B": "Test", "C": np.nan},
            ]
        )

        orig = df.copy()

        mask = ~isna(df)
        df.where(mask, None, inplace=True)
        expected = DataFrame(
            {
                "A": [1.0, np.nan],
                "B": [None, "Test"],
                "C": ["Test", None],
            }
        )
        tm.assert_frame_equal(df, expected)

        df = orig.copy()
        df[~mask] = None
        tm.assert_frame_equal(df, expected)

    def test_where_empty_df_and_empty_cond_having_non_bool_dtypes(self):
        # see gh-21947
        df = DataFrame(columns=["a"])
        cond = df
        assert (cond.dtypes == object).all()

        result = df.where(cond)
        tm.assert_frame_equal(result, df)

    def test_where_align(self):
        def create():
            df = DataFrame(np.random.default_rng(2).standard_normal((10, 3)))
            df.iloc[3:5, 0] = np.nan
            df.iloc[4:6, 1] = np.nan
            df.iloc[5:8, 2] = np.nan
            return df

        # series
        df = create()
        expected = df.fillna(df.mean())
        result = df.where(pd.notna(df), df.mean(), axis="columns")
        tm.assert_frame_equal(result, expected)

        return_value = df.where(pd.notna(df), df.mean(), inplace=True, axis="columns")
        assert return_value is None
        tm.assert_frame_equal(df, expected)

        df = create().fillna(0)
        expected = df.apply(lambda x, y: x.where(x > 0, y), y=df[0])
        result = df.where(df > 0, df[0], axis="index")
        tm.assert_frame_equal(result, expected)
        result = df.where(df > 0, df[0], axis="rows")
        tm.assert_frame_equal(result, expected)

        # frame
        df = create()
        expected = df.fillna(1)
        result = df.where(
            pd.notna(df), DataFrame(1, index=df.index, columns=df.columns)
        )
        tm.assert_frame_equal(result, expected)

    def test_where_complex(self):
        # GH 6345
        expected = DataFrame([[1 + 1j, 2], [np.nan, 4 + 1j]], columns=["a", "b"])
        df = DataFrame([[1 + 1j, 2], [5 + 1j, 4 + 1j]], columns=["a", "b"])
        df[df.abs() >= 5] = np.nan
        tm.assert_frame_equal(df, expected)

    def test_where_axis(self):
        # GH 9736
        df = DataFrame(np.random.default_rng(2).standard_normal((2, 2)))
        mask = DataFrame([[False, False], [False, False]])
        ser = Series([0, 1])

        expected = DataFrame([[0, 0], [1, 1]], dtype="float64")
        result = df.where(mask, ser, axis="index")
        tm.assert_frame_equal(result, expected)

        result = df.copy()
        return_value = result.where(mask, ser, axis="index", inplace=True)
        assert return_value is None
        tm.assert_frame_equal(result, expected)

        expected = DataFrame([[0, 1], [0, 1]], dtype="float64")
        result = df.where(mask, ser, axis="columns")
        tm.assert_frame_equal(result, expected)

        result = df.copy()
        return_value = result.where(mask, ser, axis="columns", inplace=True)
        assert return_value is None
        tm.assert_frame_equal(result, expected)

    def test_where_axis_with_upcast(self):
        # Upcast needed
        df = DataFrame([[1, 2], [3, 4]], dtype="int64")
        mask = DataFrame([[False, False], [False, False]])
        ser = Series([0, np.nan])

        expected = DataFrame([[0, 0], [np.nan, np.nan]], dtype="float64")
        result = df.where(mask, ser, axis="index")
        tm.assert_frame_equal(result, expected)

        result = df.copy()
        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            return_value = result.where(mask, ser, axis="index", inplace=True)
        assert return_value is None
        tm.assert_frame_equal(result, expected)

        expected = DataFrame([[0, np.nan], [0, np.nan]])
        result = df.where(mask, ser, axis="columns")
        tm.assert_frame_equal(result, expected)

        expected = DataFrame(
            {
                0: np.array([0, 0], dtype="int64"),
                1: np.array([np.nan, np.nan], dtype="float64"),
            }
        )
        result = df.copy()
        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            return_value = result.where(mask, ser, axis="columns", inplace=True)
        assert return_value is None
        tm.assert_frame_equal(result, expected)

    def test_where_axis_multiple_dtypes(self):
        # Multiple dtypes (=> multiple Blocks)
        df = pd.concat(
            [
                DataFrame(np.random.default_rng(2).standard_normal((10, 2))),
                DataFrame(
                    np.random.default_rng(2).integers(0, 10, size=(10, 2)),
                    dtype="int64",
                ),
            ],
            ignore_index=True,
            axis=1,
        )
        mask = DataFrame(False, columns=df.columns, index=df.index)
        s1 = Series(1, index=df.columns)
        s2 = Series(2, index=df.index)

        result = df.where(mask, s1, axis="columns")
        expected = DataFrame(1.0, columns=df.columns, index=df.index)
        expected[2] = expected[2].astype("int64")
        expected[3] = expected[3].astype("int64")
        tm.assert_frame_equal(result, expected)

        result = df.copy()
        return_value = result.where(mask, s1, axis="columns", inplace=True)
        assert return_value is None
        tm.assert_frame_equal(result, expected)

        result = df.where(mask, s2, axis="index")
        expected = DataFrame(2.0, columns=df.columns, index=df.index)
        expected[2] = expected[2].astype("int64")
        expected[3] = expected[3].astype("int64")
        tm.assert_frame_equal(result, expected)

        result = df.copy()
        return_value = result.where(mask, s2, axis="index", inplace=True)
        assert return_value is None
        tm.assert_frame_equal(result, expected)

        # DataFrame vs DataFrame
        d1 = df.copy().drop(1, axis=0)
        # Explicit cast to avoid implicit cast when setting value to np.nan
        expected = df.copy().astype("float")
        expected.loc[1, :] = np.nan

        result = df.where(mask, d1)
        tm.assert_frame_equal(result, expected)
        result = df.where(mask, d1, axis="index")
        tm.assert_frame_equal(result, expected)
        result = df.copy()
        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            return_value = result.where(mask, d1, inplace=True)
        assert return_value is None
        tm.assert_frame_equal(result, expected)
        result = df.copy()
        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            return_value = result.where(mask, d1, inplace=True, axis="index")
        assert return_value is None
        tm.assert_frame_equal(result, expected)

        d2 = df.copy().drop(1, axis=1)
        expected = df.copy()
        expected.loc[:, 1] = np.nan

        result = df.where(mask, d2)
        tm.assert_frame_equal(result, expected)
        result = df.where(mask, d2, axis="columns")
        tm.assert_frame_equal(result, expected)
        result = df.copy()
        return_value = result.where(mask, d2, inplace=True)
        assert return_value is None
        tm.assert_frame_equal(result, expected)
        result = df.copy()
        return_value = result.where(mask, d2, inplace=True, axis="columns")
        assert return_value is None
        tm.assert_frame_equal(result, expected)

    def test_where_callable(self):
        # GH 12533
        df = DataFrame([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        result = df.where(lambda x: x > 4, lambda x: x + 1)
        exp = DataFrame([[2, 3, 4], [5, 5, 6], [7, 8, 9]])
        tm.assert_frame_equal(result, exp)
        tm.assert_frame_equal(result, df.where(df > 4, df + 1))

        # return ndarray and scalar
        result = df.where(lambda x: (x % 2 == 0).values, lambda x: 99)
        exp = DataFrame([[99, 2, 99], [4, 99, 6], [99, 8, 99]])
        tm.assert_frame_equal(result, exp)
        tm.assert_frame_equal(result, df.where(df % 2 == 0, 99))

        # chain
        result = (df + 2).where(lambda x: x > 8, lambda x: x + 10)
        exp = DataFrame([[13, 14, 15], [16, 17, 18], [9, 10, 11]])
        tm.assert_frame_equal(result, exp)
        tm.assert_frame_equal(result, (df + 2).where((df + 2) > 8, (df + 2) + 10))

    def test_where_tz_values(self, tz_naive_fixture, frame_or_series):
        obj1 = DataFrame(
            DatetimeIndex(["20150101", "20150102", "20150103"], tz=tz_naive_fixture),
            columns=["date"],
        )
        obj2 = DataFrame(
            DatetimeIndex(["20150103", "20150104", "20150105"], tz=tz_naive_fixture),
            columns=["date"],
        )
        mask = DataFrame([True, True, False], columns=["date"])
        exp = DataFrame(
            DatetimeIndex(["20150101", "20150102", "20150105"], tz=tz_naive_fixture),
            columns=["date"],
        )
        if frame_or_series is Series:
            obj1 = obj1["date"]
            obj2 = obj2["date"]
            mask = mask["date"]
            exp = exp["date"]

        result = obj1.where(mask, obj2)
        tm.assert_equal(exp, result)

    def test_df_where_change_dtype(self):
        # GH#16979
        df = DataFrame(np.arange(2 * 3).reshape(2, 3), columns=list("ABC"))
        mask = np.array([[True, False, False], [False, False, True]])

        result = df.where(mask)
        expected = DataFrame(
            [[0, np.nan, np.nan], [np.nan, np.nan, 5]], columns=list("ABC")
        )

        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("kwargs", [{}, {"other": None}])
    def test_df_where_with_category(self, kwargs):
        # GH#16979
        data = np.arange(2 * 3, dtype=np.int64).reshape(2, 3)
        df = DataFrame(data, columns=list("ABC"))
        mask = np.array([[True, False, False], [False, False, True]])

        # change type to category
        df.A = df.A.astype("category")
        df.B = df.B.astype("category")
        df.C = df.C.astype("category")

        result = df.where(mask, **kwargs)
        A = pd.Categorical([0, np.nan], categories=[0, 3])
        B = pd.Categorical([np.nan, np.nan], categories=[1, 4])
        C = pd.Categorical([np.nan, 5], categories=[2, 5])
        expected = DataFrame({"A": A, "B": B, "C": C})

        tm.assert_frame_equal(result, expected)

        # Check Series.where while we're here
        result = df.A.where(mask[:, 0], **kwargs)
        expected = Series(A, name="A")

        tm.assert_series_equal(result, expected)

    def test_where_categorical_filtering(self):
        # GH#22609 Verify filtering operations on DataFrames with categorical Series
        df = DataFrame(data=[[0, 0], [1, 1]], columns=["a", "b"])
        df["b"] = df["b"].astype("category")

        result = df.where(df["a"] > 0)
        # Explicitly cast to 'float' to avoid implicit cast when setting np.nan
        expected = df.copy().astype({"a": "float"})
        expected.loc[0, :] = np.nan

        tm.assert_equal(result, expected)

    def test_where_ea_other(self):
        # GH#38729/GH#38742
        df = DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
        arr = pd.array([7, pd.NA, 9])
        ser = Series(arr)
        mask = np.ones(df.shape, dtype=bool)
        mask[1, :] = False

        # TODO: ideally we would get Int64 instead of object
        result = df.where(mask, ser, axis=0)
        expected = DataFrame({"A": [1, np.nan, 3], "B": [4, np.nan, 6]})
        tm.assert_frame_equal(result, expected)

        ser2 = Series(arr[:2], index=["A", "B"])
        expected = DataFrame({"A": [1, 7, 3], "B": [4, np.nan, 6]})
        result = df.where(mask, ser2, axis=1)
        tm.assert_frame_equal(result, expected)

    def test_where_interval_noop(self):
        # GH#44181
        df = DataFrame([pd.Interval(0, 0)])
        res = df.where(df.notna())
        tm.assert_frame_equal(res, df)

        ser = df[0]
        res = ser.where(ser.notna())
        tm.assert_series_equal(res, ser)

    def test_where_interval_fullop_downcast(self, frame_or_series):
        # GH#45768
        obj = frame_or_series([pd.Interval(0, 0)] * 2)
        other = frame_or_series([1.0, 2.0])

        msg = "Downcasting behavior in Series and DataFrame methods 'where'"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = obj.where(~obj.notna(), other)

        # since all entries are being changed, we will downcast result
        #  from object to ints (not floats)
        tm.assert_equal(res, other.astype(np.int64))

        # unlike where, Block.putmask does not downcast
        with tm.assert_produces_warning(
            FutureWarning, match="Setting an item of incompatible dtype"
        ):
            obj.mask(obj.notna(), other, inplace=True)
        tm.assert_equal(obj, other.astype(object))

    @pytest.mark.parametrize(
        "dtype",
        [
            "timedelta64[ns]",
            "datetime64[ns]",
            "datetime64[ns, Asia/Tokyo]",
            "Period[D]",
        ],
    )
    def test_where_datetimelike_noop(self, dtype):
        # GH#45135, analogue to GH#44181 for Period don't raise on no-op
        # For td64/dt64/dt64tz we already don't raise, but also are
        #  checking that we don't unnecessarily upcast to object.
        with tm.assert_produces_warning(FutureWarning, match="is deprecated"):
            ser = Series(np.arange(3) * 10**9, dtype=np.int64).view(dtype)
        df = ser.to_frame()
        mask = np.array([False, False, False])

        res = ser.where(~mask, "foo")
        tm.assert_series_equal(res, ser)

        mask2 = mask.reshape(-1, 1)
        res2 = df.where(~mask2, "foo")
        tm.assert_frame_equal(res2, df)

        res3 = ser.mask(mask, "foo")
        tm.assert_series_equal(res3, ser)

        res4 = df.mask(mask2, "foo")
        tm.assert_frame_equal(res4, df)

        # opposite case where we are replacing *all* values -> we downcast
        #  from object dtype # GH#45768
        msg = "Downcasting behavior in Series and DataFrame methods 'where'"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res5 = df.where(mask2, 4)
        expected = DataFrame(4, index=df.index, columns=df.columns)
        tm.assert_frame_equal(res5, expected)

        # unlike where, Block.putmask does not downcast
        with tm.assert_produces_warning(
            FutureWarning, match="Setting an item of incompatible dtype"
        ):
            df.mask(~mask2, 4, inplace=True)
        tm.assert_frame_equal(df, expected.astype(object))


def test_where_int_downcasting_deprecated():
    # GH#44597
    arr = np.arange(6).astype(np.int16).reshape(3, 2)
    df = DataFrame(arr)

    mask = np.zeros(arr.shape, dtype=bool)
    mask[:, 0] = True

    res = df.where(mask, 2**17)

    expected = DataFrame({0: arr[:, 0], 1: np.array([2**17] * 3, dtype=np.int32)})
    tm.assert_frame_equal(res, expected)


def test_where_copies_with_noop(frame_or_series):
    # GH-39595
    result = frame_or_series([1, 2, 3, 4])
    expected = result.copy()
    col = result[0] if frame_or_series is DataFrame else result

    where_res = result.where(col < 5)
    where_res *= 2

    tm.assert_equal(result, expected)

    where_res = result.where(col > 5, [1, 2, 3, 4])
    where_res *= 2

    tm.assert_equal(result, expected)


def test_where_string_dtype(frame_or_series):
    # GH40824
    obj = frame_or_series(
        ["a", "b", "c", "d"], index=["id1", "id2", "id3", "id4"], dtype=StringDtype()
    )
    filtered_obj = frame_or_series(
        ["b", "c"], index=["id2", "id3"], dtype=StringDtype()
    )
    filter_ser = Series([False, True, True, False])

    result = obj.where(filter_ser, filtered_obj)
    expected = frame_or_series(
        [pd.NA, "b", "c", pd.NA],
        index=["id1", "id2", "id3", "id4"],
        dtype=StringDtype(),
    )
    tm.assert_equal(result, expected)

    result = obj.mask(~filter_ser, filtered_obj)
    tm.assert_equal(result, expected)

    obj.mask(~filter_ser, filtered_obj, inplace=True)
    tm.assert_equal(result, expected)


def test_where_bool_comparison():
    # GH 10336
    df_mask = DataFrame(
        {"AAA": [True] * 4, "BBB": [False] * 4, "CCC": [True, False, True, False]}
    )
    result = df_mask.where(df_mask == False)  # noqa: E712
    expected = DataFrame(
        {
            "AAA": np.array([np.nan] * 4, dtype=object),
            "BBB": [False] * 4,
            "CCC": [np.nan, False, np.nan, False],
        }
    )
    tm.assert_frame_equal(result, expected)


def test_where_none_nan_coerce():
    # GH 15613
    expected = DataFrame(
        {
            "A": [Timestamp("20130101"), pd.NaT, Timestamp("20130103")],
            "B": [1, 2, np.nan],
        }
    )
    result = expected.where(expected.notnull(), None)
    tm.assert_frame_equal(result, expected)


def test_where_duplicate_axes_mixed_dtypes():
    # GH 25399, verify manually masking is not affected anymore by dtype of column for
    # duplicate axes.
    result = DataFrame(data=[[0, np.nan]], columns=Index(["A", "A"]))
    index, columns = result.axes
    mask = DataFrame(data=[[True, True]], columns=columns, index=index)
    a = result.astype(object).where(mask)
    b = result.astype("f8").where(mask)
    c = result.T.where(mask.T).T
    d = result.where(mask)  # used to fail with "cannot reindex from a duplicate axis"
    tm.assert_frame_equal(a.astype("f8"), b.astype("f8"))
    tm.assert_frame_equal(b.astype("f8"), c.astype("f8"))
    tm.assert_frame_equal(c.astype("f8"), d.astype("f8"))


def test_where_columns_casting():
    # GH 42295

    df = DataFrame({"a": [1.0, 2.0], "b": [3, np.nan]})
    expected = df.copy()
    result = df.where(pd.notnull(df), None)
    # make sure dtypes don't change
    tm.assert_frame_equal(expected, result)


@pytest.mark.parametrize("as_cat", [True, False])
def test_where_period_invalid_na(frame_or_series, as_cat, request):
    # GH#44697
    idx = pd.period_range("2016-01-01", periods=3, freq="D")
    if as_cat:
        idx = idx.astype("category")
    obj = frame_or_series(idx)

    # NA value that we should *not* cast to Period dtype
    tdnat = pd.NaT.to_numpy("m8[ns]")

    mask = np.array([True, True, False], ndmin=obj.ndim).T

    if as_cat:
        msg = (
            r"Cannot setitem on a Categorical with a new category \(NaT\), "
            "set the categories first"
        )
    else:
        msg = "value should be a 'Period'"

    if as_cat:
        with pytest.raises(TypeError, match=msg):
            obj.where(mask, tdnat)

        with pytest.raises(TypeError, match=msg):
            obj.mask(mask, tdnat)

        with pytest.raises(TypeError, match=msg):
            obj.mask(mask, tdnat, inplace=True)

    else:
        # With PeriodDtype, ser[i] = tdnat coerces instead of raising,
        #  so for consistency, ser[mask] = tdnat must as well
        expected = obj.astype(object).where(mask, tdnat)
        result = obj.where(mask, tdnat)
        tm.assert_equal(result, expected)

        expected = obj.astype(object).mask(mask, tdnat)
        result = obj.mask(mask, tdnat)
        tm.assert_equal(result, expected)

        with tm.assert_produces_warning(
            FutureWarning, match="Setting an item of incompatible dtype"
        ):
            obj.mask(mask, tdnat, inplace=True)
        tm.assert_equal(obj, expected)


def test_where_nullable_invalid_na(frame_or_series, any_numeric_ea_dtype):
    # GH#44697
    arr = pd.array([1, 2, 3], dtype=any_numeric_ea_dtype)
    obj = frame_or_series(arr)

    mask = np.array([True, True, False], ndmin=obj.ndim).T

    msg = r"Invalid value '.*' for dtype '(U?Int|Float)\d{1,2}'"

    for null in tm.NP_NAT_OBJECTS + [pd.NaT]:
        # NaT is an NA value that we should *not* cast to pd.NA dtype
        with pytest.raises(TypeError, match=msg):
            obj.where(mask, null)

        with pytest.raises(TypeError, match=msg):
            obj.mask(mask, null)


@given(data=OPTIONAL_ONE_OF_ALL)
def test_where_inplace_casting(data):
    # GH 22051
    df = DataFrame({"a": data})
    df_copy = df.where(pd.notnull(df), None).copy()
    df.where(pd.notnull(df), None, inplace=True)
    tm.assert_equal(df, df_copy)


def test_where_downcast_to_td64():
    ser = Series([1, 2, 3])

    mask = np.array([False, False, False])

    td = pd.Timedelta(days=1)

    msg = "Downcasting behavior in Series and DataFrame methods 'where'"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        res = ser.where(mask, td)
    expected = Series([td, td, td], dtype="m8[ns]")
    tm.assert_series_equal(res, expected)

    with pd.option_context("future.no_silent_downcasting", True):
        with tm.assert_produces_warning(None, match=msg):
            res2 = ser.where(mask, td)
    expected2 = expected.astype(object)
    tm.assert_series_equal(res2, expected2)


def _check_where_equivalences(df, mask, other, expected):
    # similar to tests.series.indexing.test_setitem.SetitemCastingEquivalences
    #  but with DataFrame in mind and less fleshed-out
    res = df.where(mask, other)
    tm.assert_frame_equal(res, expected)

    res = df.mask(~mask, other)
    tm.assert_frame_equal(res, expected)

    # Note: frame.mask(~mask, other, inplace=True) takes some more work bc
    #  Block.putmask does *not* downcast.  The change to 'expected' here
    #  is specific to the cases in test_where_dt64_2d.
    df = df.copy()
    df.mask(~mask, other, inplace=True)
    if not mask.all():
        # with mask.all(), Block.putmask is a no-op, so does not downcast
        expected = expected.copy()
        expected["A"] = expected["A"].astype(object)
    tm.assert_frame_equal(df, expected)


def test_where_dt64_2d():
    dti = date_range("2016-01-01", periods=6)
    dta = dti._data.reshape(3, 2)
    other = dta - dta[0, 0]

    df = DataFrame(dta, columns=["A", "B"])

    mask = np.asarray(df.isna()).copy()
    mask[:, 1] = True

    # setting all of one column, none of the other
    expected = DataFrame({"A": other[:, 0], "B": dta[:, 1]})
    with tm.assert_produces_warning(
        FutureWarning, match="Setting an item of incompatible dtype"
    ):
        _check_where_equivalences(df, mask, other, expected)

    # setting part of one column, none of the other
    mask[1, 0] = True
    expected = DataFrame(
        {
            "A": np.array([other[0, 0], dta[1, 0], other[2, 0]], dtype=object),
            "B": dta[:, 1],
        }
    )
    with tm.assert_produces_warning(
        FutureWarning, match="Setting an item of incompatible dtype"
    ):
        _check_where_equivalences(df, mask, other, expected)

    # setting nothing in either column
    mask[:] = True
    expected = df
    _check_where_equivalences(df, mask, other, expected)


def test_where_producing_ea_cond_for_np_dtype():
    # GH#44014
    df = DataFrame({"a": Series([1, pd.NA, 2], dtype="Int64"), "b": [1, 2, 3]})
    result = df.where(lambda x: x.apply(lambda y: y > 1, axis=1))
    expected = DataFrame(
        {"a": Series([pd.NA, pd.NA, 2], dtype="Int64"), "b": [np.nan, 2, 3]}
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "replacement", [0.001, True, "snake", None, datetime(2022, 5, 4)]
)
def test_where_int_overflow(replacement):
    # GH 31687
    df = DataFrame([[1.0, 2e25, "nine"], [np.nan, 0.1, None]])
    result = df.where(pd.notnull(df), replacement)
    expected = DataFrame([[1.0, 2e25, "nine"], [replacement, 0.1, replacement]])

    tm.assert_frame_equal(result, expected)


def test_where_inplace_no_other():
    # GH#51685
    df = DataFrame({"a": [1.0, 2.0], "b": ["x", "y"]})
    cond = DataFrame({"a": [True, False], "b": [False, True]})
    df.where(cond, inplace=True)
    expected = DataFrame({"a": [1, np.nan], "b": [np.nan, "y"]})
    tm.assert_frame_equal(df, expected)
