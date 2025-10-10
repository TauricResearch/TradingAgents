from datetime import datetime

import numpy as np
import pytest
import pytz

import pandas as pd
from pandas import (
    Index,
    MultiIndex,
)
import pandas._testing as tm


def test_insert(idx):
    # key contained in all levels
    new_index = idx.insert(0, ("bar", "two"))
    assert new_index.equal_levels(idx)
    assert new_index[0] == ("bar", "two")

    # key not contained in all levels
    new_index = idx.insert(0, ("abc", "three"))

    exp0 = Index(list(idx.levels[0]) + ["abc"], name="first")
    tm.assert_index_equal(new_index.levels[0], exp0)
    assert new_index.names == ["first", "second"]

    exp1 = Index(list(idx.levels[1]) + ["three"], name="second")
    tm.assert_index_equal(new_index.levels[1], exp1)
    assert new_index[0] == ("abc", "three")

    # key wrong length
    msg = "Item must have length equal to number of levels"
    with pytest.raises(ValueError, match=msg):
        idx.insert(0, ("foo2",))

    left = pd.DataFrame([["a", "b", 0], ["b", "d", 1]], columns=["1st", "2nd", "3rd"])
    left.set_index(["1st", "2nd"], inplace=True)
    ts = left["3rd"].copy(deep=True)

    left.loc[("b", "x"), "3rd"] = 2
    left.loc[("b", "a"), "3rd"] = -1
    left.loc[("b", "b"), "3rd"] = 3
    left.loc[("a", "x"), "3rd"] = 4
    left.loc[("a", "w"), "3rd"] = 5
    left.loc[("a", "a"), "3rd"] = 6

    ts.loc[("b", "x")] = 2
    ts.loc["b", "a"] = -1
    ts.loc[("b", "b")] = 3
    ts.loc["a", "x"] = 4
    ts.loc[("a", "w")] = 5
    ts.loc["a", "a"] = 6

    right = pd.DataFrame(
        [
            ["a", "b", 0],
            ["b", "d", 1],
            ["b", "x", 2],
            ["b", "a", -1],
            ["b", "b", 3],
            ["a", "x", 4],
            ["a", "w", 5],
            ["a", "a", 6],
        ],
        columns=["1st", "2nd", "3rd"],
    )
    right.set_index(["1st", "2nd"], inplace=True)
    # FIXME data types changes to float because
    # of intermediate nan insertion;
    tm.assert_frame_equal(left, right, check_dtype=False)
    tm.assert_series_equal(ts, right["3rd"])


def test_insert2():
    # GH9250
    idx = (
        [("test1", i) for i in range(5)]
        + [("test2", i) for i in range(6)]
        + [("test", 17), ("test", 18)]
    )

    left = pd.Series(np.linspace(0, 10, 11), MultiIndex.from_tuples(idx[:-2]))

    left.loc[("test", 17)] = 11
    left.loc[("test", 18)] = 12

    right = pd.Series(np.linspace(0, 12, 13), MultiIndex.from_tuples(idx))

    tm.assert_series_equal(left, right)


def test_append(idx):
    result = idx[:3].append(idx[3:])
    assert result.equals(idx)

    foos = [idx[:1], idx[1:3], idx[3:]]
    result = foos[0].append(foos[1:])
    assert result.equals(idx)

    # empty
    result = idx.append([])
    assert result.equals(idx)


def test_append_index():
    idx1 = Index([1.1, 1.2, 1.3])
    idx2 = pd.date_range("2011-01-01", freq="D", periods=3, tz="Asia/Tokyo")
    idx3 = Index(["A", "B", "C"])

    midx_lv2 = MultiIndex.from_arrays([idx1, idx2])
    midx_lv3 = MultiIndex.from_arrays([idx1, idx2, idx3])

    result = idx1.append(midx_lv2)

    # see gh-7112
    tz = pytz.timezone("Asia/Tokyo")
    expected_tuples = [
        (1.1, tz.localize(datetime(2011, 1, 1))),
        (1.2, tz.localize(datetime(2011, 1, 2))),
        (1.3, tz.localize(datetime(2011, 1, 3))),
    ]
    expected = Index([1.1, 1.2, 1.3] + expected_tuples)
    tm.assert_index_equal(result, expected)

    result = midx_lv2.append(idx1)
    expected = Index(expected_tuples + [1.1, 1.2, 1.3])
    tm.assert_index_equal(result, expected)

    result = midx_lv2.append(midx_lv2)
    expected = MultiIndex.from_arrays([idx1.append(idx1), idx2.append(idx2)])
    tm.assert_index_equal(result, expected)

    result = midx_lv2.append(midx_lv3)
    tm.assert_index_equal(result, expected)

    result = midx_lv3.append(midx_lv2)
    expected = Index._simple_new(
        np.array(
            [
                (1.1, tz.localize(datetime(2011, 1, 1)), "A"),
                (1.2, tz.localize(datetime(2011, 1, 2)), "B"),
                (1.3, tz.localize(datetime(2011, 1, 3)), "C"),
            ]
            + expected_tuples,
            dtype=object,
        ),
        None,
    )
    tm.assert_index_equal(result, expected)


@pytest.mark.parametrize("name, exp", [("b", "b"), ("c", None)])
def test_append_names_match(name, exp):
    # GH#48288
    midx = MultiIndex.from_arrays([[1, 2], [3, 4]], names=["a", "b"])
    midx2 = MultiIndex.from_arrays([[3], [5]], names=["a", name])
    result = midx.append(midx2)
    expected = MultiIndex.from_arrays([[1, 2, 3], [3, 4, 5]], names=["a", exp])
    tm.assert_index_equal(result, expected)


def test_append_names_dont_match():
    # GH#48288
    midx = MultiIndex.from_arrays([[1, 2], [3, 4]], names=["a", "b"])
    midx2 = MultiIndex.from_arrays([[3], [5]], names=["x", "y"])
    result = midx.append(midx2)
    expected = MultiIndex.from_arrays([[1, 2, 3], [3, 4, 5]], names=None)
    tm.assert_index_equal(result, expected)


def test_append_overlapping_interval_levels():
    # GH 54934
    ivl1 = pd.IntervalIndex.from_breaks([0.0, 1.0, 2.0])
    ivl2 = pd.IntervalIndex.from_breaks([0.5, 1.5, 2.5])
    mi1 = MultiIndex.from_product([ivl1, ivl1])
    mi2 = MultiIndex.from_product([ivl2, ivl2])
    result = mi1.append(mi2)
    expected = MultiIndex.from_tuples(
        [
            (pd.Interval(0.0, 1.0), pd.Interval(0.0, 1.0)),
            (pd.Interval(0.0, 1.0), pd.Interval(1.0, 2.0)),
            (pd.Interval(1.0, 2.0), pd.Interval(0.0, 1.0)),
            (pd.Interval(1.0, 2.0), pd.Interval(1.0, 2.0)),
            (pd.Interval(0.5, 1.5), pd.Interval(0.5, 1.5)),
            (pd.Interval(0.5, 1.5), pd.Interval(1.5, 2.5)),
            (pd.Interval(1.5, 2.5), pd.Interval(0.5, 1.5)),
            (pd.Interval(1.5, 2.5), pd.Interval(1.5, 2.5)),
        ]
    )
    tm.assert_index_equal(result, expected)


def test_repeat():
    reps = 2
    numbers = [1, 2, 3]
    names = np.array(["foo", "bar"])

    m = MultiIndex.from_product([numbers, names], names=names)
    expected = MultiIndex.from_product([numbers, names.repeat(reps)], names=names)
    tm.assert_index_equal(m.repeat(reps), expected)


def test_insert_base(idx):
    result = idx[1:4]

    # test 0th element
    assert idx[0:4].equals(result.insert(0, idx[0]))


def test_delete_base(idx):
    expected = idx[1:]
    result = idx.delete(0)
    assert result.equals(expected)
    assert result.name == expected.name

    expected = idx[:-1]
    result = idx.delete(-1)
    assert result.equals(expected)
    assert result.name == expected.name

    msg = "index 6 is out of bounds for axis 0 with size 6"
    with pytest.raises(IndexError, match=msg):
        idx.delete(len(idx))
