import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    Interval,
    MultiIndex,
    Series,
    StringDtype,
)
import pandas._testing as tm


@pytest.mark.parametrize(
    "other", [Index(["three", "one", "two"]), Index(["one"]), Index(["one", "three"])]
)
def test_join_level(idx, other, join_type):
    join_index, lidx, ridx = other.join(
        idx, how=join_type, level="second", return_indexers=True
    )

    exp_level = other.join(idx.levels[1], how=join_type)
    assert join_index.levels[0].equals(idx.levels[0])
    assert join_index.levels[1].equals(exp_level)

    # pare down levels
    mask = np.array([x[1] in exp_level for x in idx], dtype=bool)
    exp_values = idx.values[mask]
    tm.assert_numpy_array_equal(join_index.values, exp_values)

    if join_type in ("outer", "inner"):
        join_index2, ridx2, lidx2 = idx.join(
            other, how=join_type, level="second", return_indexers=True
        )

        assert join_index.equals(join_index2)
        tm.assert_numpy_array_equal(lidx, lidx2)
        tm.assert_numpy_array_equal(ridx, ridx2)
        tm.assert_numpy_array_equal(join_index2.values, exp_values)


def test_join_level_corner_case(idx):
    # some corner cases
    index = Index(["three", "one", "two"])
    result = index.join(idx, level="second")
    assert isinstance(result, MultiIndex)

    with pytest.raises(TypeError, match="Join.*MultiIndex.*ambiguous"):
        idx.join(idx, level=1)


def test_join_self(idx, join_type):
    result = idx.join(idx, how=join_type)
    expected = idx
    if join_type == "outer":
        expected = expected.sort_values()
    tm.assert_index_equal(result, expected)


def test_join_multi():
    # GH 10665
    midx = MultiIndex.from_product([np.arange(4), np.arange(4)], names=["a", "b"])
    idx = Index([1, 2, 5], name="b")

    # inner
    jidx, lidx, ridx = midx.join(idx, how="inner", return_indexers=True)
    exp_idx = MultiIndex.from_product([np.arange(4), [1, 2]], names=["a", "b"])
    exp_lidx = np.array([1, 2, 5, 6, 9, 10, 13, 14], dtype=np.intp)
    exp_ridx = np.array([0, 1, 0, 1, 0, 1, 0, 1], dtype=np.intp)
    tm.assert_index_equal(jidx, exp_idx)
    tm.assert_numpy_array_equal(lidx, exp_lidx)
    tm.assert_numpy_array_equal(ridx, exp_ridx)
    # flip
    jidx, ridx, lidx = idx.join(midx, how="inner", return_indexers=True)
    tm.assert_index_equal(jidx, exp_idx)
    tm.assert_numpy_array_equal(lidx, exp_lidx)
    tm.assert_numpy_array_equal(ridx, exp_ridx)

    # keep MultiIndex
    jidx, lidx, ridx = midx.join(idx, how="left", return_indexers=True)
    exp_ridx = np.array(
        [-1, 0, 1, -1, -1, 0, 1, -1, -1, 0, 1, -1, -1, 0, 1, -1], dtype=np.intp
    )
    tm.assert_index_equal(jidx, midx)
    assert lidx is None
    tm.assert_numpy_array_equal(ridx, exp_ridx)
    # flip
    jidx, ridx, lidx = idx.join(midx, how="right", return_indexers=True)
    tm.assert_index_equal(jidx, midx)
    assert lidx is None
    tm.assert_numpy_array_equal(ridx, exp_ridx)


def test_join_multi_wrong_order():
    # GH 25760
    # GH 28956

    midx1 = MultiIndex.from_product([[1, 2], [3, 4]], names=["a", "b"])
    midx2 = MultiIndex.from_product([[1, 2], [3, 4]], names=["b", "a"])

    join_idx, lidx, ridx = midx1.join(midx2, return_indexers=True)

    exp_ridx = np.array([-1, -1, -1, -1], dtype=np.intp)

    tm.assert_index_equal(midx1, join_idx)
    assert lidx is None
    tm.assert_numpy_array_equal(ridx, exp_ridx)


def test_join_multi_return_indexers():
    # GH 34074

    midx1 = MultiIndex.from_product([[1, 2], [3, 4], [5, 6]], names=["a", "b", "c"])
    midx2 = MultiIndex.from_product([[1, 2], [3, 4]], names=["a", "b"])

    result = midx1.join(midx2, return_indexers=False)
    tm.assert_index_equal(result, midx1)


def test_join_overlapping_interval_level():
    # GH 44096
    idx_1 = MultiIndex.from_tuples(
        [
            (1, Interval(0.0, 1.0)),
            (1, Interval(1.0, 2.0)),
            (1, Interval(2.0, 5.0)),
            (2, Interval(0.0, 1.0)),
            (2, Interval(1.0, 3.0)),  # interval limit is here at 3.0, not at 2.0
            (2, Interval(3.0, 5.0)),
        ],
        names=["num", "interval"],
    )

    idx_2 = MultiIndex.from_tuples(
        [
            (1, Interval(2.0, 5.0)),
            (1, Interval(0.0, 1.0)),
            (1, Interval(1.0, 2.0)),
            (2, Interval(3.0, 5.0)),
            (2, Interval(0.0, 1.0)),
            (2, Interval(1.0, 3.0)),
        ],
        names=["num", "interval"],
    )

    expected = MultiIndex.from_tuples(
        [
            (1, Interval(0.0, 1.0)),
            (1, Interval(1.0, 2.0)),
            (1, Interval(2.0, 5.0)),
            (2, Interval(0.0, 1.0)),
            (2, Interval(1.0, 3.0)),
            (2, Interval(3.0, 5.0)),
        ],
        names=["num", "interval"],
    )
    result = idx_1.join(idx_2, how="outer")

    tm.assert_index_equal(result, expected)


def test_join_midx_ea():
    # GH#49277
    midx = MultiIndex.from_arrays(
        [Series([1, 1, 3], dtype="Int64"), Series([1, 2, 3], dtype="Int64")],
        names=["a", "b"],
    )
    midx2 = MultiIndex.from_arrays(
        [Series([1], dtype="Int64"), Series([3], dtype="Int64")], names=["a", "c"]
    )
    result = midx.join(midx2, how="inner")
    expected = MultiIndex.from_arrays(
        [
            Series([1, 1], dtype="Int64"),
            Series([1, 2], dtype="Int64"),
            Series([3, 3], dtype="Int64"),
        ],
        names=["a", "b", "c"],
    )
    tm.assert_index_equal(result, expected)


def test_join_midx_string():
    # GH#49277
    midx = MultiIndex.from_arrays(
        [
            Series(["a", "a", "c"], dtype=StringDtype()),
            Series(["a", "b", "c"], dtype=StringDtype()),
        ],
        names=["a", "b"],
    )
    midx2 = MultiIndex.from_arrays(
        [Series(["a"], dtype=StringDtype()), Series(["c"], dtype=StringDtype())],
        names=["a", "c"],
    )
    result = midx.join(midx2, how="inner")
    expected = MultiIndex.from_arrays(
        [
            Series(["a", "a"], dtype=StringDtype()),
            Series(["a", "b"], dtype=StringDtype()),
            Series(["c", "c"], dtype=StringDtype()),
        ],
        names=["a", "b", "c"],
    )
    tm.assert_index_equal(result, expected)


def test_join_multi_with_nan():
    # GH29252
    df1 = DataFrame(
        data={"col1": [1.1, 1.2]},
        index=MultiIndex.from_product([["A"], [1.0, 2.0]], names=["id1", "id2"]),
    )
    df2 = DataFrame(
        data={"col2": [2.1, 2.2]},
        index=MultiIndex.from_product([["A"], [np.nan, 2.0]], names=["id1", "id2"]),
    )
    result = df1.join(df2)
    expected = DataFrame(
        data={"col1": [1.1, 1.2], "col2": [np.nan, 2.2]},
        index=MultiIndex.from_product([["A"], [1.0, 2.0]], names=["id1", "id2"]),
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("val", [0, 5])
def test_join_dtypes(any_numeric_ea_dtype, val):
    # GH#49830
    midx = MultiIndex.from_arrays([Series([1, 2], dtype=any_numeric_ea_dtype), [3, 4]])
    midx2 = MultiIndex.from_arrays(
        [Series([1, val, val], dtype=any_numeric_ea_dtype), [3, 4, 4]]
    )
    result = midx.join(midx2, how="outer")
    expected = MultiIndex.from_arrays(
        [Series([val, val, 1, 2], dtype=any_numeric_ea_dtype), [4, 4, 3, 4]]
    ).sort_values()
    tm.assert_index_equal(result, expected)


def test_join_dtypes_all_nan(any_numeric_ea_dtype):
    # GH#49830
    midx = MultiIndex.from_arrays(
        [Series([1, 2], dtype=any_numeric_ea_dtype), [np.nan, np.nan]]
    )
    midx2 = MultiIndex.from_arrays(
        [Series([1, 0, 0], dtype=any_numeric_ea_dtype), [np.nan, np.nan, np.nan]]
    )
    result = midx.join(midx2, how="outer")
    expected = MultiIndex.from_arrays(
        [
            Series([0, 0, 1, 2], dtype=any_numeric_ea_dtype),
            [np.nan, np.nan, np.nan, np.nan],
        ]
    )
    tm.assert_index_equal(result, expected)


def test_join_index_levels():
    # GH#53093
    midx = midx = MultiIndex.from_tuples([("a", "2019-02-01"), ("a", "2019-02-01")])
    midx2 = MultiIndex.from_tuples([("a", "2019-01-31")])
    result = midx.join(midx2, how="outer")
    expected = MultiIndex.from_tuples(
        [("a", "2019-01-31"), ("a", "2019-02-01"), ("a", "2019-02-01")]
    )
    tm.assert_index_equal(result.levels[1], expected.levels[1])
    tm.assert_index_equal(result, expected)
