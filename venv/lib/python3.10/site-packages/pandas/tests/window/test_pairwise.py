import numpy as np
import pytest

from pandas.compat import IS64

from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Series,
    date_range,
)
import pandas._testing as tm
from pandas.core.algorithms import safe_sort


@pytest.fixture(
    params=[
        DataFrame([[2, 4], [1, 2], [5, 2], [8, 1]], columns=[1, 0]),
        DataFrame([[2, 4], [1, 2], [5, 2], [8, 1]], columns=[1, 1]),
        DataFrame([[2, 4], [1, 2], [5, 2], [8, 1]], columns=["C", "C"]),
        DataFrame([[2, 4], [1, 2], [5, 2], [8, 1]], columns=[1.0, 0]),
        DataFrame([[2, 4], [1, 2], [5, 2], [8, 1]], columns=[0.0, 1]),
        DataFrame([[2, 4], [1, 2], [5, 2], [8, 1]], columns=["C", 1]),
        DataFrame([[2.0, 4.0], [1.0, 2.0], [5.0, 2.0], [8.0, 1.0]], columns=[1, 0.0]),
        DataFrame([[2, 4.0], [1, 2.0], [5, 2.0], [8, 1.0]], columns=[0, 1.0]),
        DataFrame([[2, 4], [1, 2], [5, 2], [8, 1.0]], columns=[1.0, "X"]),
    ]
)
def pairwise_frames(request):
    """Pairwise frames test_pairwise"""
    return request.param


@pytest.fixture
def pairwise_target_frame():
    """Pairwise target frame for test_pairwise"""
    return DataFrame([[2, 4], [1, 2], [5, 2], [8, 1]], columns=[0, 1])


@pytest.fixture
def pairwise_other_frame():
    """Pairwise other frame for test_pairwise"""
    return DataFrame(
        [[None, 1, 1], [None, 1, 2], [None, 3, 2], [None, 8, 1]],
        columns=["Y", "Z", "X"],
    )


def test_rolling_cov(series):
    A = series
    B = A + np.random.default_rng(2).standard_normal(len(A))

    result = A.rolling(window=50, min_periods=25).cov(B)
    tm.assert_almost_equal(result.iloc[-1], np.cov(A[-50:], B[-50:])[0, 1])


def test_rolling_corr(series):
    A = series
    B = A + np.random.default_rng(2).standard_normal(len(A))

    result = A.rolling(window=50, min_periods=25).corr(B)
    tm.assert_almost_equal(result.iloc[-1], np.corrcoef(A[-50:], B[-50:])[0, 1])


def test_rolling_corr_bias_correction():
    # test for correct bias correction
    a = Series(
        np.arange(20, dtype=np.float64), index=date_range("2020-01-01", periods=20)
    )
    b = a.copy()
    a[:5] = np.nan
    b[:10] = np.nan

    result = a.rolling(window=len(a), min_periods=1).corr(b)
    tm.assert_almost_equal(result.iloc[-1], a.corr(b))


@pytest.mark.parametrize("func", ["cov", "corr"])
def test_rolling_pairwise_cov_corr(func, frame):
    result = getattr(frame.rolling(window=10, min_periods=5), func)()
    result = result.loc[(slice(None), 1), 5]
    result.index = result.index.droplevel(1)
    expected = getattr(frame[1].rolling(window=10, min_periods=5), func)(frame[5])
    tm.assert_series_equal(result, expected, check_names=False)


@pytest.mark.parametrize("method", ["corr", "cov"])
def test_flex_binary_frame(method, frame):
    series = frame[1]

    res = getattr(series.rolling(window=10), method)(frame)
    res2 = getattr(frame.rolling(window=10), method)(series)
    exp = frame.apply(lambda x: getattr(series.rolling(window=10), method)(x))

    tm.assert_frame_equal(res, exp)
    tm.assert_frame_equal(res2, exp)

    frame2 = frame.copy()
    frame2 = DataFrame(
        np.random.default_rng(2).standard_normal(frame2.shape),
        index=frame2.index,
        columns=frame2.columns,
    )

    res3 = getattr(frame.rolling(window=10), method)(frame2)
    exp = DataFrame(
        {k: getattr(frame[k].rolling(window=10), method)(frame2[k]) for k in frame}
    )
    tm.assert_frame_equal(res3, exp)


@pytest.mark.parametrize("window", range(7))
def test_rolling_corr_with_zero_variance(window):
    # GH 18430
    s = Series(np.zeros(20))
    other = Series(np.arange(20))

    assert s.rolling(window=window).corr(other=other).isna().all()


def test_corr_sanity():
    # GH 3155
    df = DataFrame(
        np.array(
            [
                [0.87024726, 0.18505595],
                [0.64355431, 0.3091617],
                [0.92372966, 0.50552513],
                [0.00203756, 0.04520709],
                [0.84780328, 0.33394331],
                [0.78369152, 0.63919667],
            ]
        )
    )

    res = df[0].rolling(5, center=True).corr(df[1])
    assert all(np.abs(np.nan_to_num(x)) <= 1 for x in res)

    df = DataFrame(np.random.default_rng(2).random((30, 2)))
    res = df[0].rolling(5, center=True).corr(df[1])
    assert all(np.abs(np.nan_to_num(x)) <= 1 for x in res)


def test_rolling_cov_diff_length():
    # GH 7512
    s1 = Series([1, 2, 3], index=[0, 1, 2])
    s2 = Series([1, 3], index=[0, 2])
    result = s1.rolling(window=3, min_periods=2).cov(s2)
    expected = Series([None, None, 2.0])
    tm.assert_series_equal(result, expected)

    s2a = Series([1, None, 3], index=[0, 1, 2])
    result = s1.rolling(window=3, min_periods=2).cov(s2a)
    tm.assert_series_equal(result, expected)


def test_rolling_corr_diff_length():
    # GH 7512
    s1 = Series([1, 2, 3], index=[0, 1, 2])
    s2 = Series([1, 3], index=[0, 2])
    result = s1.rolling(window=3, min_periods=2).corr(s2)
    expected = Series([None, None, 1.0])
    tm.assert_series_equal(result, expected)

    s2a = Series([1, None, 3], index=[0, 1, 2])
    result = s1.rolling(window=3, min_periods=2).corr(s2a)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "f",
    [
        lambda x: (x.rolling(window=10, min_periods=5).cov(x, pairwise=True)),
        lambda x: (x.rolling(window=10, min_periods=5).corr(x, pairwise=True)),
    ],
)
def test_rolling_functions_window_non_shrinkage_binary(f):
    # corr/cov return a MI DataFrame
    df = DataFrame(
        [[1, 5], [3, 2], [3, 9], [-1, 0]],
        columns=Index(["A", "B"], name="foo"),
        index=Index(range(4), name="bar"),
    )
    df_expected = DataFrame(
        columns=Index(["A", "B"], name="foo"),
        index=MultiIndex.from_product([df.index, df.columns], names=["bar", "foo"]),
        dtype="float64",
    )
    df_result = f(df)
    tm.assert_frame_equal(df_result, df_expected)


@pytest.mark.parametrize(
    "f",
    [
        lambda x: (x.rolling(window=10, min_periods=5).cov(x, pairwise=True)),
        lambda x: (x.rolling(window=10, min_periods=5).corr(x, pairwise=True)),
    ],
)
def test_moment_functions_zero_length_pairwise(f):
    df1 = DataFrame()
    df2 = DataFrame(columns=Index(["a"], name="foo"), index=Index([], name="bar"))
    df2["a"] = df2["a"].astype("float64")

    df1_expected = DataFrame(index=MultiIndex.from_product([df1.index, df1.columns]))
    df2_expected = DataFrame(
        index=MultiIndex.from_product([df2.index, df2.columns], names=["bar", "foo"]),
        columns=Index(["a"], name="foo"),
        dtype="float64",
    )

    df1_result = f(df1)
    tm.assert_frame_equal(df1_result, df1_expected)

    df2_result = f(df2)
    tm.assert_frame_equal(df2_result, df2_expected)


class TestPairwise:
    # GH 7738
    @pytest.mark.parametrize("f", [lambda x: x.cov(), lambda x: x.corr()])
    def test_no_flex(self, pairwise_frames, pairwise_target_frame, f):
        # DataFrame methods (which do not call flex_binary_moment())

        result = f(pairwise_frames)
        tm.assert_index_equal(result.index, pairwise_frames.columns)
        tm.assert_index_equal(result.columns, pairwise_frames.columns)
        expected = f(pairwise_target_frame)
        # since we have sorted the results
        # we can only compare non-nans
        result = result.dropna().values
        expected = expected.dropna().values

        tm.assert_numpy_array_equal(result, expected, check_dtype=False)

    @pytest.mark.parametrize(
        "f",
        [
            lambda x: x.expanding().cov(pairwise=True),
            lambda x: x.expanding().corr(pairwise=True),
            lambda x: x.rolling(window=3).cov(pairwise=True),
            lambda x: x.rolling(window=3).corr(pairwise=True),
            lambda x: x.ewm(com=3).cov(pairwise=True),
            lambda x: x.ewm(com=3).corr(pairwise=True),
        ],
    )
    def test_pairwise_with_self(self, pairwise_frames, pairwise_target_frame, f):
        # DataFrame with itself, pairwise=True
        # note that we may construct the 1st level of the MI
        # in a non-monotonic way, so compare accordingly
        result = f(pairwise_frames)
        tm.assert_index_equal(
            result.index.levels[0], pairwise_frames.index, check_names=False
        )
        tm.assert_index_equal(
            safe_sort(result.index.levels[1]),
            safe_sort(pairwise_frames.columns.unique()),
        )
        tm.assert_index_equal(result.columns, pairwise_frames.columns)
        expected = f(pairwise_target_frame)
        # since we have sorted the results
        # we can only compare non-nans
        result = result.dropna().values
        expected = expected.dropna().values

        tm.assert_numpy_array_equal(result, expected, check_dtype=False)

    @pytest.mark.parametrize(
        "f",
        [
            lambda x: x.expanding().cov(pairwise=False),
            lambda x: x.expanding().corr(pairwise=False),
            lambda x: x.rolling(window=3).cov(pairwise=False),
            lambda x: x.rolling(window=3).corr(pairwise=False),
            lambda x: x.ewm(com=3).cov(pairwise=False),
            lambda x: x.ewm(com=3).corr(pairwise=False),
        ],
    )
    def test_no_pairwise_with_self(self, pairwise_frames, pairwise_target_frame, f):
        # DataFrame with itself, pairwise=False
        result = f(pairwise_frames)
        tm.assert_index_equal(result.index, pairwise_frames.index)
        tm.assert_index_equal(result.columns, pairwise_frames.columns)
        expected = f(pairwise_target_frame)
        # since we have sorted the results
        # we can only compare non-nans
        result = result.dropna().values
        expected = expected.dropna().values

        tm.assert_numpy_array_equal(result, expected, check_dtype=False)

    @pytest.mark.parametrize(
        "f",
        [
            lambda x, y: x.expanding().cov(y, pairwise=True),
            lambda x, y: x.expanding().corr(y, pairwise=True),
            lambda x, y: x.rolling(window=3).cov(y, pairwise=True),
            # TODO: We're missing a flag somewhere in meson
            pytest.param(
                lambda x, y: x.rolling(window=3).corr(y, pairwise=True),
                marks=pytest.mark.xfail(
                    not IS64, reason="Precision issues on 32 bit", strict=False
                ),
            ),
            lambda x, y: x.ewm(com=3).cov(y, pairwise=True),
            lambda x, y: x.ewm(com=3).corr(y, pairwise=True),
        ],
    )
    def test_pairwise_with_other(
        self, pairwise_frames, pairwise_target_frame, pairwise_other_frame, f
    ):
        # DataFrame with another DataFrame, pairwise=True
        result = f(pairwise_frames, pairwise_other_frame)
        tm.assert_index_equal(
            result.index.levels[0], pairwise_frames.index, check_names=False
        )
        tm.assert_index_equal(
            safe_sort(result.index.levels[1]),
            safe_sort(pairwise_other_frame.columns.unique()),
        )
        expected = f(pairwise_target_frame, pairwise_other_frame)
        # since we have sorted the results
        # we can only compare non-nans
        result = result.dropna().values
        expected = expected.dropna().values

        tm.assert_numpy_array_equal(result, expected, check_dtype=False)

    @pytest.mark.filterwarnings("ignore:RuntimeWarning")
    @pytest.mark.parametrize(
        "f",
        [
            lambda x, y: x.expanding().cov(y, pairwise=False),
            lambda x, y: x.expanding().corr(y, pairwise=False),
            lambda x, y: x.rolling(window=3).cov(y, pairwise=False),
            lambda x, y: x.rolling(window=3).corr(y, pairwise=False),
            lambda x, y: x.ewm(com=3).cov(y, pairwise=False),
            lambda x, y: x.ewm(com=3).corr(y, pairwise=False),
        ],
    )
    def test_no_pairwise_with_other(self, pairwise_frames, pairwise_other_frame, f):
        # DataFrame with another DataFrame, pairwise=False
        result = (
            f(pairwise_frames, pairwise_other_frame)
            if pairwise_frames.columns.is_unique
            else None
        )
        if result is not None:
            # we can have int and str columns
            expected_index = pairwise_frames.index.union(pairwise_other_frame.index)
            expected_columns = pairwise_frames.columns.union(
                pairwise_other_frame.columns
            )
            tm.assert_index_equal(result.index, expected_index)
            tm.assert_index_equal(result.columns, expected_columns)
        else:
            with pytest.raises(ValueError, match="'arg1' columns are not unique"):
                f(pairwise_frames, pairwise_other_frame)
            with pytest.raises(ValueError, match="'arg2' columns are not unique"):
                f(pairwise_other_frame, pairwise_frames)

    @pytest.mark.parametrize(
        "f",
        [
            lambda x, y: x.expanding().cov(y),
            lambda x, y: x.expanding().corr(y),
            lambda x, y: x.rolling(window=3).cov(y),
            lambda x, y: x.rolling(window=3).corr(y),
            lambda x, y: x.ewm(com=3).cov(y),
            lambda x, y: x.ewm(com=3).corr(y),
        ],
    )
    def test_pairwise_with_series(self, pairwise_frames, pairwise_target_frame, f):
        # DataFrame with a Series
        result = f(pairwise_frames, Series([1, 1, 3, 8]))
        tm.assert_index_equal(result.index, pairwise_frames.index)
        tm.assert_index_equal(result.columns, pairwise_frames.columns)
        expected = f(pairwise_target_frame, Series([1, 1, 3, 8]))
        # since we have sorted the results
        # we can only compare non-nans
        result = result.dropna().values
        expected = expected.dropna().values
        tm.assert_numpy_array_equal(result, expected, check_dtype=False)

        result = f(Series([1, 1, 3, 8]), pairwise_frames)
        tm.assert_index_equal(result.index, pairwise_frames.index)
        tm.assert_index_equal(result.columns, pairwise_frames.columns)
        expected = f(Series([1, 1, 3, 8]), pairwise_target_frame)
        # since we have sorted the results
        # we can only compare non-nans
        result = result.dropna().values
        expected = expected.dropna().values
        tm.assert_numpy_array_equal(result, expected, check_dtype=False)

    def test_corr_freq_memory_error(self):
        # GH 31789
        s = Series(range(5), index=date_range("2020", periods=5))
        result = s.rolling("12h").corr(s)
        expected = Series([np.nan] * 5, index=date_range("2020", periods=5))
        tm.assert_series_equal(result, expected)

    def test_cov_mulittindex(self):
        # GH 34440

        columns = MultiIndex.from_product([list("ab"), list("xy"), list("AB")])
        index = range(3)
        df = DataFrame(np.arange(24).reshape(3, 8), index=index, columns=columns)

        result = df.ewm(alpha=0.1).cov()

        index = MultiIndex.from_product([range(3), list("ab"), list("xy"), list("AB")])
        columns = MultiIndex.from_product([list("ab"), list("xy"), list("AB")])
        expected = DataFrame(
            np.vstack(
                (
                    np.full((8, 8), np.nan),
                    np.full((8, 8), 32.000000),
                    np.full((8, 8), 63.881919),
                )
            ),
            index=index,
            columns=columns,
        )

        tm.assert_frame_equal(result, expected)

    def test_multindex_columns_pairwise_func(self):
        # GH 21157
        columns = MultiIndex.from_arrays([["M", "N"], ["P", "Q"]], names=["a", "b"])
        df = DataFrame(np.ones((5, 2)), columns=columns)
        result = df.rolling(3).corr()
        expected = DataFrame(
            np.nan,
            index=MultiIndex.from_arrays(
                [
                    np.repeat(np.arange(5, dtype=np.int64), 2),
                    ["M", "N"] * 5,
                    ["P", "Q"] * 5,
                ],
                names=[None, "a", "b"],
            ),
            columns=columns,
        )
        tm.assert_frame_equal(result, expected)
