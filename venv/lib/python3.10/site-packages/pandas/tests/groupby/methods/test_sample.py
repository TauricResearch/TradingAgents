import pytest

from pandas import (
    DataFrame,
    Index,
    Series,
)
import pandas._testing as tm


@pytest.mark.parametrize("n, frac", [(2, None), (None, 0.2)])
def test_groupby_sample_balanced_groups_shape(n, frac):
    values = [1] * 10 + [2] * 10
    df = DataFrame({"a": values, "b": values})

    result = df.groupby("a").sample(n=n, frac=frac)
    values = [1] * 2 + [2] * 2
    expected = DataFrame({"a": values, "b": values}, index=result.index)
    tm.assert_frame_equal(result, expected)

    result = df.groupby("a")["b"].sample(n=n, frac=frac)
    expected = Series(values, name="b", index=result.index)
    tm.assert_series_equal(result, expected)


def test_groupby_sample_unbalanced_groups_shape():
    values = [1] * 10 + [2] * 20
    df = DataFrame({"a": values, "b": values})

    result = df.groupby("a").sample(n=5)
    values = [1] * 5 + [2] * 5
    expected = DataFrame({"a": values, "b": values}, index=result.index)
    tm.assert_frame_equal(result, expected)

    result = df.groupby("a")["b"].sample(n=5)
    expected = Series(values, name="b", index=result.index)
    tm.assert_series_equal(result, expected)


def test_groupby_sample_index_value_spans_groups():
    values = [1] * 3 + [2] * 3
    df = DataFrame({"a": values, "b": values}, index=[1, 2, 2, 2, 2, 2])

    result = df.groupby("a").sample(n=2)
    values = [1] * 2 + [2] * 2
    expected = DataFrame({"a": values, "b": values}, index=result.index)
    tm.assert_frame_equal(result, expected)

    result = df.groupby("a")["b"].sample(n=2)
    expected = Series(values, name="b", index=result.index)
    tm.assert_series_equal(result, expected)


def test_groupby_sample_n_and_frac_raises():
    df = DataFrame({"a": [1, 2], "b": [1, 2]})
    msg = "Please enter a value for `frac` OR `n`, not both"

    with pytest.raises(ValueError, match=msg):
        df.groupby("a").sample(n=1, frac=1.0)

    with pytest.raises(ValueError, match=msg):
        df.groupby("a")["b"].sample(n=1, frac=1.0)


def test_groupby_sample_frac_gt_one_without_replacement_raises():
    df = DataFrame({"a": [1, 2], "b": [1, 2]})
    msg = "Replace has to be set to `True` when upsampling the population `frac` > 1."

    with pytest.raises(ValueError, match=msg):
        df.groupby("a").sample(frac=1.5, replace=False)

    with pytest.raises(ValueError, match=msg):
        df.groupby("a")["b"].sample(frac=1.5, replace=False)


@pytest.mark.parametrize("n", [-1, 1.5])
def test_groupby_sample_invalid_n_raises(n):
    df = DataFrame({"a": [1, 2], "b": [1, 2]})

    if n < 0:
        msg = "A negative number of rows requested. Please provide `n` >= 0."
    else:
        msg = "Only integers accepted as `n` values"

    with pytest.raises(ValueError, match=msg):
        df.groupby("a").sample(n=n)

    with pytest.raises(ValueError, match=msg):
        df.groupby("a")["b"].sample(n=n)


def test_groupby_sample_oversample():
    values = [1] * 10 + [2] * 10
    df = DataFrame({"a": values, "b": values})

    result = df.groupby("a").sample(frac=2.0, replace=True)
    values = [1] * 20 + [2] * 20
    expected = DataFrame({"a": values, "b": values}, index=result.index)
    tm.assert_frame_equal(result, expected)

    result = df.groupby("a")["b"].sample(frac=2.0, replace=True)
    expected = Series(values, name="b", index=result.index)
    tm.assert_series_equal(result, expected)


def test_groupby_sample_without_n_or_frac():
    values = [1] * 10 + [2] * 10
    df = DataFrame({"a": values, "b": values})

    result = df.groupby("a").sample(n=None, frac=None)
    expected = DataFrame({"a": [1, 2], "b": [1, 2]}, index=result.index)
    tm.assert_frame_equal(result, expected)

    result = df.groupby("a")["b"].sample(n=None, frac=None)
    expected = Series([1, 2], name="b", index=result.index)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "index, expected_index",
    [(["w", "x", "y", "z"], ["w", "w", "y", "y"]), ([3, 4, 5, 6], [3, 3, 5, 5])],
)
def test_groupby_sample_with_weights(index, expected_index):
    # GH 39927 - tests for integer index needed
    values = [1] * 2 + [2] * 2
    df = DataFrame({"a": values, "b": values}, index=Index(index))

    result = df.groupby("a").sample(n=2, replace=True, weights=[1, 0, 1, 0])
    expected = DataFrame({"a": values, "b": values}, index=Index(expected_index))
    tm.assert_frame_equal(result, expected)

    result = df.groupby("a")["b"].sample(n=2, replace=True, weights=[1, 0, 1, 0])
    expected = Series(values, name="b", index=Index(expected_index))
    tm.assert_series_equal(result, expected)


def test_groupby_sample_with_selections():
    # GH 39928
    values = [1] * 10 + [2] * 10
    df = DataFrame({"a": values, "b": values, "c": values})

    result = df.groupby("a")[["b", "c"]].sample(n=None, frac=None)
    expected = DataFrame({"b": [1, 2], "c": [1, 2]}, index=result.index)
    tm.assert_frame_equal(result, expected)


def test_groupby_sample_with_empty_inputs():
    # GH48459
    df = DataFrame({"a": [], "b": []})
    groupby_df = df.groupby("a")

    result = groupby_df.sample()
    expected = df
    tm.assert_frame_equal(result, expected)
