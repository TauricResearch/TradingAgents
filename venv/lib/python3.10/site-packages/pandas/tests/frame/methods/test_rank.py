from datetime import (
    datetime,
    timedelta,
)

import numpy as np
import pytest

from pandas._libs.algos import (
    Infinity,
    NegInfinity,
)

from pandas import (
    DataFrame,
    Index,
    Series,
)
import pandas._testing as tm


class TestRank:
    s = Series([1, 3, 4, 2, np.nan, 2, 1, 5, np.nan, 3])
    df = DataFrame({"A": s, "B": s})

    results = {
        "average": np.array([1.5, 5.5, 7.0, 3.5, np.nan, 3.5, 1.5, 8.0, np.nan, 5.5]),
        "min": np.array([1, 5, 7, 3, np.nan, 3, 1, 8, np.nan, 5]),
        "max": np.array([2, 6, 7, 4, np.nan, 4, 2, 8, np.nan, 6]),
        "first": np.array([1, 5, 7, 3, np.nan, 4, 2, 8, np.nan, 6]),
        "dense": np.array([1, 3, 4, 2, np.nan, 2, 1, 5, np.nan, 3]),
    }

    @pytest.fixture(params=["average", "min", "max", "first", "dense"])
    def method(self, request):
        """
        Fixture for trying all rank methods
        """
        return request.param

    def test_rank(self, float_frame):
        sp_stats = pytest.importorskip("scipy.stats")

        float_frame.loc[::2, "A"] = np.nan
        float_frame.loc[::3, "B"] = np.nan
        float_frame.loc[::4, "C"] = np.nan
        float_frame.loc[::5, "D"] = np.nan

        ranks0 = float_frame.rank()
        ranks1 = float_frame.rank(1)
        mask = np.isnan(float_frame.values)

        fvals = float_frame.fillna(np.inf).values

        exp0 = np.apply_along_axis(sp_stats.rankdata, 0, fvals)
        exp0[mask] = np.nan

        exp1 = np.apply_along_axis(sp_stats.rankdata, 1, fvals)
        exp1[mask] = np.nan

        tm.assert_almost_equal(ranks0.values, exp0)
        tm.assert_almost_equal(ranks1.values, exp1)

        # integers
        df = DataFrame(
            np.random.default_rng(2).integers(0, 5, size=40).reshape((10, 4))
        )

        result = df.rank()
        exp = df.astype(float).rank()
        tm.assert_frame_equal(result, exp)

        result = df.rank(1)
        exp = df.astype(float).rank(1)
        tm.assert_frame_equal(result, exp)

    def test_rank2(self):
        df = DataFrame([[1, 3, 2], [1, 2, 3]])
        expected = DataFrame([[1.0, 3.0, 2.0], [1, 2, 3]]) / 3.0
        result = df.rank(1, pct=True)
        tm.assert_frame_equal(result, expected)

        df = DataFrame([[1, 3, 2], [1, 2, 3]])
        expected = df.rank(0) / 2.0
        result = df.rank(0, pct=True)
        tm.assert_frame_equal(result, expected)

        df = DataFrame([["b", "c", "a"], ["a", "c", "b"]])
        expected = DataFrame([[2.0, 3.0, 1.0], [1, 3, 2]])
        result = df.rank(1, numeric_only=False)
        tm.assert_frame_equal(result, expected)

        expected = DataFrame([[2.0, 1.5, 1.0], [1, 1.5, 2]])
        result = df.rank(0, numeric_only=False)
        tm.assert_frame_equal(result, expected)

        df = DataFrame([["b", np.nan, "a"], ["a", "c", "b"]])
        expected = DataFrame([[2.0, np.nan, 1.0], [1.0, 3.0, 2.0]])
        result = df.rank(1, numeric_only=False)
        tm.assert_frame_equal(result, expected)

        expected = DataFrame([[2.0, np.nan, 1.0], [1.0, 1.0, 2.0]])
        result = df.rank(0, numeric_only=False)
        tm.assert_frame_equal(result, expected)

        # f7u12, this does not work without extensive workaround
        data = [
            [datetime(2001, 1, 5), np.nan, datetime(2001, 1, 2)],
            [datetime(2000, 1, 2), datetime(2000, 1, 3), datetime(2000, 1, 1)],
        ]
        df = DataFrame(data)

        # check the rank
        expected = DataFrame([[2.0, np.nan, 1.0], [2.0, 3.0, 1.0]])
        result = df.rank(1, numeric_only=False, ascending=True)
        tm.assert_frame_equal(result, expected)

        expected = DataFrame([[1.0, np.nan, 2.0], [2.0, 1.0, 3.0]])
        result = df.rank(1, numeric_only=False, ascending=False)
        tm.assert_frame_equal(result, expected)

        df = DataFrame({"a": [1e-20, -5, 1e-20 + 1e-40, 10, 1e60, 1e80, 1e-30]})
        exp = DataFrame({"a": [3.5, 1.0, 3.5, 5.0, 6.0, 7.0, 2.0]})
        tm.assert_frame_equal(df.rank(), exp)

    def test_rank_does_not_mutate(self):
        # GH#18521
        # Check rank does not mutate DataFrame
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 3)), dtype="float64"
        )
        expected = df.copy()
        df.rank()
        result = df
        tm.assert_frame_equal(result, expected)

    def test_rank_mixed_frame(self, float_string_frame):
        float_string_frame["datetime"] = datetime.now()
        float_string_frame["timedelta"] = timedelta(days=1, seconds=1)

        float_string_frame.rank(numeric_only=False)
        with pytest.raises(TypeError, match="not supported between instances of"):
            float_string_frame.rank(axis=1)

    def test_rank_na_option(self, float_frame):
        sp_stats = pytest.importorskip("scipy.stats")

        float_frame.loc[::2, "A"] = np.nan
        float_frame.loc[::3, "B"] = np.nan
        float_frame.loc[::4, "C"] = np.nan
        float_frame.loc[::5, "D"] = np.nan

        # bottom
        ranks0 = float_frame.rank(na_option="bottom")
        ranks1 = float_frame.rank(1, na_option="bottom")

        fvals = float_frame.fillna(np.inf).values

        exp0 = np.apply_along_axis(sp_stats.rankdata, 0, fvals)
        exp1 = np.apply_along_axis(sp_stats.rankdata, 1, fvals)

        tm.assert_almost_equal(ranks0.values, exp0)
        tm.assert_almost_equal(ranks1.values, exp1)

        # top
        ranks0 = float_frame.rank(na_option="top")
        ranks1 = float_frame.rank(1, na_option="top")

        fval0 = float_frame.fillna((float_frame.min() - 1).to_dict()).values
        fval1 = float_frame.T
        fval1 = fval1.fillna((fval1.min() - 1).to_dict()).T
        fval1 = fval1.fillna(np.inf).values

        exp0 = np.apply_along_axis(sp_stats.rankdata, 0, fval0)
        exp1 = np.apply_along_axis(sp_stats.rankdata, 1, fval1)

        tm.assert_almost_equal(ranks0.values, exp0)
        tm.assert_almost_equal(ranks1.values, exp1)

        # descending

        # bottom
        ranks0 = float_frame.rank(na_option="top", ascending=False)
        ranks1 = float_frame.rank(1, na_option="top", ascending=False)

        fvals = float_frame.fillna(np.inf).values

        exp0 = np.apply_along_axis(sp_stats.rankdata, 0, -fvals)
        exp1 = np.apply_along_axis(sp_stats.rankdata, 1, -fvals)

        tm.assert_almost_equal(ranks0.values, exp0)
        tm.assert_almost_equal(ranks1.values, exp1)

        # descending

        # top
        ranks0 = float_frame.rank(na_option="bottom", ascending=False)
        ranks1 = float_frame.rank(1, na_option="bottom", ascending=False)

        fval0 = float_frame.fillna((float_frame.min() - 1).to_dict()).values
        fval1 = float_frame.T
        fval1 = fval1.fillna((fval1.min() - 1).to_dict()).T
        fval1 = fval1.fillna(np.inf).values

        exp0 = np.apply_along_axis(sp_stats.rankdata, 0, -fval0)
        exp1 = np.apply_along_axis(sp_stats.rankdata, 1, -fval1)

        tm.assert_numpy_array_equal(ranks0.values, exp0)
        tm.assert_numpy_array_equal(ranks1.values, exp1)

        # bad values throw error
        msg = "na_option must be one of 'keep', 'top', or 'bottom'"

        with pytest.raises(ValueError, match=msg):
            float_frame.rank(na_option="bad", ascending=False)

        # invalid type
        with pytest.raises(ValueError, match=msg):
            float_frame.rank(na_option=True, ascending=False)

    def test_rank_axis(self):
        # check if using axes' names gives the same result
        df = DataFrame([[2, 1], [4, 3]])
        tm.assert_frame_equal(df.rank(axis=0), df.rank(axis="index"))
        tm.assert_frame_equal(df.rank(axis=1), df.rank(axis="columns"))

    @pytest.mark.parametrize("ax", [0, 1])
    @pytest.mark.parametrize("m", ["average", "min", "max", "first", "dense"])
    def test_rank_methods_frame(self, ax, m):
        sp_stats = pytest.importorskip("scipy.stats")

        xs = np.random.default_rng(2).integers(0, 21, (100, 26))
        xs = (xs - 10.0) / 10.0
        cols = [chr(ord("z") - i) for i in range(xs.shape[1])]

        for vals in [xs, xs + 1e6, xs * 1e-6]:
            df = DataFrame(vals, columns=cols)

            result = df.rank(axis=ax, method=m)
            sprank = np.apply_along_axis(
                sp_stats.rankdata, ax, vals, m if m != "first" else "ordinal"
            )
            sprank = sprank.astype(np.float64)
            expected = DataFrame(sprank, columns=cols).astype("float64")
            tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("dtype", ["O", "f8", "i8"])
    def test_rank_descending(self, method, dtype):
        if "i" in dtype:
            df = self.df.dropna().astype(dtype)
        else:
            df = self.df.astype(dtype)

        res = df.rank(ascending=False)
        expected = (df.max() - df).rank()
        tm.assert_frame_equal(res, expected)

        expected = (df.max() - df).rank(method=method)

        if dtype != "O":
            res2 = df.rank(method=method, ascending=False, numeric_only=True)
            tm.assert_frame_equal(res2, expected)

        res3 = df.rank(method=method, ascending=False, numeric_only=False)
        tm.assert_frame_equal(res3, expected)

    @pytest.mark.parametrize("axis", [0, 1])
    @pytest.mark.parametrize("dtype", [None, object])
    def test_rank_2d_tie_methods(self, method, axis, dtype):
        df = self.df

        def _check2d(df, expected, method="average", axis=0):
            exp_df = DataFrame({"A": expected, "B": expected})

            if axis == 1:
                df = df.T
                exp_df = exp_df.T

            result = df.rank(method=method, axis=axis)
            tm.assert_frame_equal(result, exp_df)

        frame = df if dtype is None else df.astype(dtype)
        _check2d(frame, self.results[method], method=method, axis=axis)

    @pytest.mark.parametrize(
        "method,exp",
        [
            ("dense", [[1.0, 1.0, 1.0], [1.0, 0.5, 2.0 / 3], [1.0, 0.5, 1.0 / 3]]),
            (
                "min",
                [
                    [1.0 / 3, 1.0, 1.0],
                    [1.0 / 3, 1.0 / 3, 2.0 / 3],
                    [1.0 / 3, 1.0 / 3, 1.0 / 3],
                ],
            ),
            (
                "max",
                [[1.0, 1.0, 1.0], [1.0, 2.0 / 3, 2.0 / 3], [1.0, 2.0 / 3, 1.0 / 3]],
            ),
            (
                "average",
                [[2.0 / 3, 1.0, 1.0], [2.0 / 3, 0.5, 2.0 / 3], [2.0 / 3, 0.5, 1.0 / 3]],
            ),
            (
                "first",
                [
                    [1.0 / 3, 1.0, 1.0],
                    [2.0 / 3, 1.0 / 3, 2.0 / 3],
                    [3.0 / 3, 2.0 / 3, 1.0 / 3],
                ],
            ),
        ],
    )
    def test_rank_pct_true(self, method, exp):
        # see gh-15630.

        df = DataFrame([[2012, 66, 3], [2012, 65, 2], [2012, 65, 1]])
        result = df.rank(method=method, pct=True)

        expected = DataFrame(exp)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.single_cpu
    def test_pct_max_many_rows(self):
        # GH 18271
        df = DataFrame(
            {"A": np.arange(2**24 + 1), "B": np.arange(2**24 + 1, 0, -1)}
        )
        result = df.rank(pct=True).max()
        assert (result == 1).all()

    @pytest.mark.parametrize(
        "contents,dtype",
        [
            (
                [
                    -np.inf,
                    -50,
                    -1,
                    -1e-20,
                    -1e-25,
                    -1e-50,
                    0,
                    1e-40,
                    1e-20,
                    1e-10,
                    2,
                    40,
                    np.inf,
                ],
                "float64",
            ),
            (
                [
                    -np.inf,
                    -50,
                    -1,
                    -1e-20,
                    -1e-25,
                    -1e-45,
                    0,
                    1e-40,
                    1e-20,
                    1e-10,
                    2,
                    40,
                    np.inf,
                ],
                "float32",
            ),
            ([np.iinfo(np.uint8).min, 1, 2, 100, np.iinfo(np.uint8).max], "uint8"),
            (
                [
                    np.iinfo(np.int64).min,
                    -100,
                    0,
                    1,
                    9999,
                    100000,
                    1e10,
                    np.iinfo(np.int64).max,
                ],
                "int64",
            ),
            ([NegInfinity(), "1", "A", "BA", "Ba", "C", Infinity()], "object"),
            (
                [datetime(2001, 1, 1), datetime(2001, 1, 2), datetime(2001, 1, 5)],
                "datetime64",
            ),
        ],
    )
    def test_rank_inf_and_nan(self, contents, dtype, frame_or_series):
        dtype_na_map = {
            "float64": np.nan,
            "float32": np.nan,
            "object": None,
            "datetime64": np.datetime64("nat"),
        }
        # Insert nans at random positions if underlying dtype has missing
        # value. Then adjust the expected order by adding nans accordingly
        # This is for testing whether rank calculation is affected
        # when values are interwined with nan values.
        values = np.array(contents, dtype=dtype)
        exp_order = np.array(range(len(values)), dtype="float64") + 1.0
        if dtype in dtype_na_map:
            na_value = dtype_na_map[dtype]
            nan_indices = np.random.default_rng(2).choice(range(len(values)), 5)
            values = np.insert(values, nan_indices, na_value)
            exp_order = np.insert(exp_order, nan_indices, np.nan)

        # Shuffle the testing array and expected results in the same way
        random_order = np.random.default_rng(2).permutation(len(values))
        obj = frame_or_series(values[random_order])
        expected = frame_or_series(exp_order[random_order], dtype="float64")
        result = obj.rank()
        tm.assert_equal(result, expected)

    def test_df_series_inf_nan_consistency(self):
        # GH#32593
        index = [5, 4, 3, 2, 1, 6, 7, 8, 9, 10]
        col1 = [5, 4, 3, 5, 8, 5, 2, 1, 6, 6]
        col2 = [5, 4, np.nan, 5, 8, 5, np.inf, np.nan, 6, -np.inf]
        df = DataFrame(
            data={
                "col1": col1,
                "col2": col2,
            },
            index=index,
            dtype="f8",
        )
        df_result = df.rank()

        series_result = df.copy()
        series_result["col1"] = df["col1"].rank()
        series_result["col2"] = df["col2"].rank()

        tm.assert_frame_equal(df_result, series_result)

    def test_rank_both_inf(self):
        # GH#32593
        df = DataFrame({"a": [-np.inf, 0, np.inf]})
        expected = DataFrame({"a": [1.0, 2.0, 3.0]})
        result = df.rank()
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "na_option,ascending,expected",
        [
            ("top", True, [3.0, 1.0, 2.0]),
            ("top", False, [2.0, 1.0, 3.0]),
            ("bottom", True, [2.0, 3.0, 1.0]),
            ("bottom", False, [1.0, 3.0, 2.0]),
        ],
    )
    def test_rank_inf_nans_na_option(
        self, frame_or_series, method, na_option, ascending, expected
    ):
        obj = frame_or_series([np.inf, np.nan, -np.inf])
        result = obj.rank(method=method, na_option=na_option, ascending=ascending)
        expected = frame_or_series(expected)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize(
        "na_option,ascending,expected",
        [
            ("bottom", True, [1.0, 2.0, 4.0, 3.0]),
            ("bottom", False, [1.0, 2.0, 4.0, 3.0]),
            ("top", True, [2.0, 3.0, 1.0, 4.0]),
            ("top", False, [2.0, 3.0, 1.0, 4.0]),
        ],
    )
    def test_rank_object_first(self, frame_or_series, na_option, ascending, expected):
        obj = frame_or_series(["foo", "foo", None, "foo"])
        result = obj.rank(method="first", na_option=na_option, ascending=ascending)
        expected = frame_or_series(expected)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize(
        "data,expected",
        [
            (
                {"a": [1, 2, "a"], "b": [4, 5, 6]},
                DataFrame({"b": [1.0, 2.0, 3.0]}, columns=Index(["b"], dtype=object)),
            ),
            ({"a": [1, 2, "a"]}, DataFrame(index=range(3), columns=[])),
        ],
    )
    def test_rank_mixed_axis_zero(self, data, expected):
        df = DataFrame(data, columns=Index(list(data.keys()), dtype=object))
        with pytest.raises(TypeError, match="'<' not supported between instances of"):
            df.rank()
        result = df.rank(numeric_only=True)
        tm.assert_frame_equal(result, expected)

    def test_rank_string_dtype(self, string_dtype_no_object):
        # GH#55362
        obj = Series(["foo", "foo", None, "foo"], dtype=string_dtype_no_object)
        result = obj.rank(method="first")
        exp_dtype = (
            "Float64" if string_dtype_no_object == "string[pyarrow]" else "float64"
        )
        if string_dtype_no_object.storage == "python":
            # TODO nullable string[python] should also return nullable Int64
            exp_dtype = "float64"
        expected = Series([1, 2, None, 3], dtype=exp_dtype)
        tm.assert_series_equal(result, expected)
