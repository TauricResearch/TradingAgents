import numpy as np
import pytest

from pandas import (
    DataFrame,
    MultiIndex,
    Series,
    concat,
    date_range,
)
import pandas._testing as tm
from pandas.api.indexers import (
    BaseIndexer,
    FixedForwardWindowIndexer,
)
from pandas.core.indexers.objects import (
    ExpandingIndexer,
    FixedWindowIndexer,
    VariableOffsetWindowIndexer,
)

from pandas.tseries.offsets import BusinessDay


def test_bad_get_window_bounds_signature():
    class BadIndexer(BaseIndexer):
        def get_window_bounds(self):
            return None

    indexer = BadIndexer()
    with pytest.raises(ValueError, match="BadIndexer does not implement"):
        Series(range(5)).rolling(indexer)


def test_expanding_indexer():
    s = Series(range(10))
    indexer = ExpandingIndexer()
    result = s.rolling(indexer).mean()
    expected = s.expanding().mean()
    tm.assert_series_equal(result, expected)


def test_indexer_constructor_arg():
    # Example found in computation.rst
    use_expanding = [True, False, True, False, True]
    df = DataFrame({"values": range(5)})

    class CustomIndexer(BaseIndexer):
        def get_window_bounds(self, num_values, min_periods, center, closed, step):
            start = np.empty(num_values, dtype=np.int64)
            end = np.empty(num_values, dtype=np.int64)
            for i in range(num_values):
                if self.use_expanding[i]:
                    start[i] = 0
                    end[i] = i + 1
                else:
                    start[i] = i
                    end[i] = i + self.window_size
            return start, end

    indexer = CustomIndexer(window_size=1, use_expanding=use_expanding)
    result = df.rolling(indexer).sum()
    expected = DataFrame({"values": [0.0, 1.0, 3.0, 3.0, 10.0]})
    tm.assert_frame_equal(result, expected)


def test_indexer_accepts_rolling_args():
    df = DataFrame({"values": range(5)})

    class CustomIndexer(BaseIndexer):
        def get_window_bounds(self, num_values, min_periods, center, closed, step):
            start = np.empty(num_values, dtype=np.int64)
            end = np.empty(num_values, dtype=np.int64)
            for i in range(num_values):
                if (
                    center
                    and min_periods == 1
                    and closed == "both"
                    and step == 1
                    and i == 2
                ):
                    start[i] = 0
                    end[i] = num_values
                else:
                    start[i] = i
                    end[i] = i + self.window_size
            return start, end

    indexer = CustomIndexer(window_size=1)
    result = df.rolling(
        indexer, center=True, min_periods=1, closed="both", step=1
    ).sum()
    expected = DataFrame({"values": [0.0, 1.0, 10.0, 3.0, 4.0]})
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "func,np_func,expected,np_kwargs",
    [
        ("count", len, [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 2.0, np.nan], {}),
        ("min", np.min, [0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 6.0, 7.0, 8.0, np.nan], {}),
        (
            "max",
            np.max,
            [2.0, 3.0, 4.0, 100.0, 100.0, 100.0, 8.0, 9.0, 9.0, np.nan],
            {},
        ),
        (
            "std",
            np.std,
            [
                1.0,
                1.0,
                1.0,
                55.71654452,
                54.85739087,
                53.9845657,
                1.0,
                1.0,
                0.70710678,
                np.nan,
            ],
            {"ddof": 1},
        ),
        (
            "var",
            np.var,
            [
                1.0,
                1.0,
                1.0,
                3104.333333,
                3009.333333,
                2914.333333,
                1.0,
                1.0,
                0.500000,
                np.nan,
            ],
            {"ddof": 1},
        ),
        (
            "median",
            np.median,
            [1.0, 2.0, 3.0, 4.0, 6.0, 7.0, 7.0, 8.0, 8.5, np.nan],
            {},
        ),
    ],
)
def test_rolling_forward_window(
    frame_or_series, func, np_func, expected, np_kwargs, step
):
    # GH 32865
    values = np.arange(10.0)
    values[5] = 100.0

    indexer = FixedForwardWindowIndexer(window_size=3)

    match = "Forward-looking windows can't have center=True"
    with pytest.raises(ValueError, match=match):
        rolling = frame_or_series(values).rolling(window=indexer, center=True)
        getattr(rolling, func)()

    match = "Forward-looking windows don't support setting the closed argument"
    with pytest.raises(ValueError, match=match):
        rolling = frame_or_series(values).rolling(window=indexer, closed="right")
        getattr(rolling, func)()

    rolling = frame_or_series(values).rolling(window=indexer, min_periods=2, step=step)
    result = getattr(rolling, func)()

    # Check that the function output matches the explicitly provided array
    expected = frame_or_series(expected)[::step]
    tm.assert_equal(result, expected)

    # Check that the rolling function output matches applying an alternative
    # function to the rolling window object
    expected2 = frame_or_series(rolling.apply(lambda x: np_func(x, **np_kwargs)))
    tm.assert_equal(result, expected2)

    # Check that the function output matches applying an alternative function
    # if min_periods isn't specified
    # GH 39604: After count-min_periods deprecation, apply(lambda x: len(x))
    # is equivalent to count after setting min_periods=0
    min_periods = 0 if func == "count" else None
    rolling3 = frame_or_series(values).rolling(window=indexer, min_periods=min_periods)
    result3 = getattr(rolling3, func)()
    expected3 = frame_or_series(rolling3.apply(lambda x: np_func(x, **np_kwargs)))
    tm.assert_equal(result3, expected3)


def test_rolling_forward_skewness(frame_or_series, step):
    values = np.arange(10.0)
    values[5] = 100.0

    indexer = FixedForwardWindowIndexer(window_size=5)
    rolling = frame_or_series(values).rolling(window=indexer, min_periods=3, step=step)
    result = rolling.skew()

    expected = frame_or_series(
        [
            0.0,
            2.232396,
            2.229508,
            2.228340,
            2.229091,
            2.231989,
            0.0,
            0.0,
            np.nan,
            np.nan,
        ]
    )[::step]
    tm.assert_equal(result, expected)


@pytest.mark.parametrize(
    "func,expected",
    [
        ("cov", [2.0, 2.0, 2.0, 97.0, 2.0, -93.0, 2.0, 2.0, np.nan, np.nan]),
        (
            "corr",
            [
                1.0,
                1.0,
                1.0,
                0.8704775290207161,
                0.018229084250926637,
                -0.861357304646493,
                1.0,
                1.0,
                np.nan,
                np.nan,
            ],
        ),
    ],
)
def test_rolling_forward_cov_corr(func, expected):
    values1 = np.arange(10).reshape(-1, 1)
    values2 = values1 * 2
    values1[5, 0] = 100
    values = np.concatenate([values1, values2], axis=1)

    indexer = FixedForwardWindowIndexer(window_size=3)
    rolling = DataFrame(values).rolling(window=indexer, min_periods=3)
    # We are interested in checking only pairwise covariance / correlation
    result = getattr(rolling, func)().loc[(slice(None), 1), 0]
    result = result.reset_index(drop=True)
    expected = Series(expected).reset_index(drop=True)
    expected.name = result.name
    tm.assert_equal(result, expected)


@pytest.mark.parametrize(
    "closed,expected_data",
    [
        ["right", [0.0, 1.0, 2.0, 3.0, 7.0, 12.0, 6.0, 7.0, 8.0, 9.0]],
        ["left", [0.0, 0.0, 1.0, 2.0, 5.0, 9.0, 5.0, 6.0, 7.0, 8.0]],
    ],
)
def test_non_fixed_variable_window_indexer(closed, expected_data):
    index = date_range("2020", periods=10)
    df = DataFrame(range(10), index=index)
    offset = BusinessDay(1)
    indexer = VariableOffsetWindowIndexer(index=index, offset=offset)
    result = df.rolling(indexer, closed=closed).sum()
    expected = DataFrame(expected_data, index=index)
    tm.assert_frame_equal(result, expected)


def test_variableoffsetwindowindexer_not_dti():
    # GH 54379
    with pytest.raises(ValueError, match="index must be a DatetimeIndex."):
        VariableOffsetWindowIndexer(index="foo", offset=BusinessDay(1))


def test_variableoffsetwindowindexer_not_offset():
    # GH 54379
    idx = date_range("2020", periods=10)
    with pytest.raises(ValueError, match="offset must be a DateOffset-like object."):
        VariableOffsetWindowIndexer(index=idx, offset="foo")


def test_fixed_forward_indexer_count(step):
    # GH: 35579
    df = DataFrame({"b": [None, None, None, 7]})
    indexer = FixedForwardWindowIndexer(window_size=2)
    result = df.rolling(window=indexer, min_periods=0, step=step).count()
    expected = DataFrame({"b": [0.0, 0.0, 1.0, 1.0]})[::step]
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    ("end_value", "values"), [(1, [0.0, 1, 1, 3, 2]), (-1, [0.0, 1, 0, 3, 1])]
)
@pytest.mark.parametrize(("func", "args"), [("median", []), ("quantile", [0.5])])
def test_indexer_quantile_sum(end_value, values, func, args):
    # GH 37153
    class CustomIndexer(BaseIndexer):
        def get_window_bounds(self, num_values, min_periods, center, closed, step):
            start = np.empty(num_values, dtype=np.int64)
            end = np.empty(num_values, dtype=np.int64)
            for i in range(num_values):
                if self.use_expanding[i]:
                    start[i] = 0
                    end[i] = max(i + end_value, 1)
                else:
                    start[i] = i
                    end[i] = i + self.window_size
            return start, end

    use_expanding = [True, False, True, False, True]
    df = DataFrame({"values": range(5)})

    indexer = CustomIndexer(window_size=1, use_expanding=use_expanding)
    result = getattr(df.rolling(indexer), func)(*args)
    expected = DataFrame({"values": values})
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "indexer_class", [FixedWindowIndexer, FixedForwardWindowIndexer, ExpandingIndexer]
)
@pytest.mark.parametrize("window_size", [1, 2, 12])
@pytest.mark.parametrize(
    "df_data",
    [
        {"a": [1, 1], "b": [0, 1]},
        {"a": [1, 2], "b": [0, 1]},
        {"a": [1] * 16, "b": [np.nan, 1, 2, np.nan] + list(range(4, 16))},
    ],
)
def test_indexers_are_reusable_after_groupby_rolling(
    indexer_class, window_size, df_data
):
    # GH 43267
    df = DataFrame(df_data)
    num_trials = 3
    indexer = indexer_class(window_size=window_size)
    original_window_size = indexer.window_size
    for i in range(num_trials):
        df.groupby("a")["b"].rolling(window=indexer, min_periods=1).mean()
        assert indexer.window_size == original_window_size


@pytest.mark.parametrize(
    "window_size, num_values, expected_start, expected_end",
    [
        (1, 1, [0], [1]),
        (1, 2, [0, 1], [1, 2]),
        (2, 1, [0], [1]),
        (2, 2, [0, 1], [2, 2]),
        (5, 12, range(12), list(range(5, 12)) + [12] * 5),
        (12, 5, range(5), [5] * 5),
        (0, 0, np.array([]), np.array([])),
        (1, 0, np.array([]), np.array([])),
        (0, 1, [0], [0]),
    ],
)
def test_fixed_forward_indexer_bounds(
    window_size, num_values, expected_start, expected_end, step
):
    # GH 43267
    indexer = FixedForwardWindowIndexer(window_size=window_size)
    start, end = indexer.get_window_bounds(num_values=num_values, step=step)

    tm.assert_numpy_array_equal(
        start, np.array(expected_start[::step]), check_dtype=False
    )
    tm.assert_numpy_array_equal(end, np.array(expected_end[::step]), check_dtype=False)
    assert len(start) == len(end)


@pytest.mark.parametrize(
    "df, window_size, expected",
    [
        (
            DataFrame({"b": [0, 1, 2], "a": [1, 2, 2]}),
            2,
            Series(
                [0, 1.5, 2.0],
                index=MultiIndex.from_arrays([[1, 2, 2], range(3)], names=["a", None]),
                name="b",
                dtype=np.float64,
            ),
        ),
        (
            DataFrame(
                {
                    "b": [np.nan, 1, 2, np.nan] + list(range(4, 18)),
                    "a": [1] * 7 + [2] * 11,
                    "c": range(18),
                }
            ),
            12,
            Series(
                [
                    3.6,
                    3.6,
                    4.25,
                    5.0,
                    5.0,
                    5.5,
                    6.0,
                    12.0,
                    12.5,
                    13.0,
                    13.5,
                    14.0,
                    14.5,
                    15.0,
                    15.5,
                    16.0,
                    16.5,
                    17.0,
                ],
                index=MultiIndex.from_arrays(
                    [[1] * 7 + [2] * 11, range(18)], names=["a", None]
                ),
                name="b",
                dtype=np.float64,
            ),
        ),
    ],
)
def test_rolling_groupby_with_fixed_forward_specific(df, window_size, expected):
    # GH 43267
    indexer = FixedForwardWindowIndexer(window_size=window_size)
    result = df.groupby("a")["b"].rolling(window=indexer, min_periods=1).mean()
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "group_keys",
    [
        (1,),
        (1, 2),
        (2, 1),
        (1, 1, 2),
        (1, 2, 1),
        (1, 1, 2, 2),
        (1, 2, 3, 2, 3),
        (1, 1, 2) * 4,
        (1, 2, 3) * 5,
    ],
)
@pytest.mark.parametrize("window_size", [1, 2, 3, 4, 5, 8, 20])
def test_rolling_groupby_with_fixed_forward_many(group_keys, window_size):
    # GH 43267
    df = DataFrame(
        {
            "a": np.array(list(group_keys)),
            "b": np.arange(len(group_keys), dtype=np.float64) + 17,
            "c": np.arange(len(group_keys), dtype=np.int64),
        }
    )

    indexer = FixedForwardWindowIndexer(window_size=window_size)
    result = df.groupby("a")["b"].rolling(window=indexer, min_periods=1).sum()
    result.index.names = ["a", "c"]

    groups = df.groupby("a")[["a", "b", "c"]]
    manual = concat(
        [
            g.assign(
                b=[
                    g["b"].iloc[i : i + window_size].sum(min_count=1)
                    for i in range(len(g))
                ]
            )
            for _, g in groups
        ]
    )
    manual = manual.set_index(["a", "c"])["b"]

    tm.assert_series_equal(result, manual)


def test_unequal_start_end_bounds():
    class CustomIndexer(BaseIndexer):
        def get_window_bounds(self, num_values, min_periods, center, closed, step):
            return np.array([1]), np.array([1, 2])

    indexer = CustomIndexer()
    roll = Series(1).rolling(indexer)
    match = "start"
    with pytest.raises(ValueError, match=match):
        roll.mean()

    with pytest.raises(ValueError, match=match):
        next(iter(roll))

    with pytest.raises(ValueError, match=match):
        roll.corr(pairwise=True)

    with pytest.raises(ValueError, match=match):
        roll.cov(pairwise=True)


def test_unequal_bounds_to_object():
    # GH 44470
    class CustomIndexer(BaseIndexer):
        def get_window_bounds(self, num_values, min_periods, center, closed, step):
            return np.array([1]), np.array([2])

    indexer = CustomIndexer()
    roll = Series([1, 1]).rolling(indexer)
    match = "start and end"
    with pytest.raises(ValueError, match=match):
        roll.mean()

    with pytest.raises(ValueError, match=match):
        next(iter(roll))

    with pytest.raises(ValueError, match=match):
        roll.corr(pairwise=True)

    with pytest.raises(ValueError, match=match):
        roll.cov(pairwise=True)
