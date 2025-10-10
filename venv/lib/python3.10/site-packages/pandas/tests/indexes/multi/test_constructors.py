from datetime import (
    date,
    datetime,
)
import itertools

import numpy as np
import pytest

from pandas.core.dtypes.cast import construct_1d_object_array_from_listlike

import pandas as pd
from pandas import (
    Index,
    MultiIndex,
    Series,
    Timestamp,
    date_range,
)
import pandas._testing as tm


def test_constructor_single_level():
    result = MultiIndex(
        levels=[["foo", "bar", "baz", "qux"]], codes=[[0, 1, 2, 3]], names=["first"]
    )
    assert isinstance(result, MultiIndex)
    expected = Index(["foo", "bar", "baz", "qux"], name="first")
    tm.assert_index_equal(result.levels[0], expected)
    assert result.names == ["first"]


def test_constructor_no_levels():
    msg = "non-zero number of levels/codes"
    with pytest.raises(ValueError, match=msg):
        MultiIndex(levels=[], codes=[])

    msg = "Must pass both levels and codes"
    with pytest.raises(TypeError, match=msg):
        MultiIndex(levels=[])
    with pytest.raises(TypeError, match=msg):
        MultiIndex(codes=[])


def test_constructor_nonhashable_names():
    # GH 20527
    levels = [[1, 2], ["one", "two"]]
    codes = [[0, 0, 1, 1], [0, 1, 0, 1]]
    names = (["foo"], ["bar"])
    msg = r"MultiIndex\.name must be a hashable type"
    with pytest.raises(TypeError, match=msg):
        MultiIndex(levels=levels, codes=codes, names=names)

    # With .rename()
    mi = MultiIndex(
        levels=[[1, 2], ["one", "two"]],
        codes=[[0, 0, 1, 1], [0, 1, 0, 1]],
        names=("foo", "bar"),
    )
    renamed = [["fooo"], ["barr"]]
    with pytest.raises(TypeError, match=msg):
        mi.rename(names=renamed)

    # With .set_names()
    with pytest.raises(TypeError, match=msg):
        mi.set_names(names=renamed)


def test_constructor_mismatched_codes_levels(idx):
    codes = [np.array([1]), np.array([2]), np.array([3])]
    levels = ["a"]

    msg = "Length of levels and codes must be the same"
    with pytest.raises(ValueError, match=msg):
        MultiIndex(levels=levels, codes=codes)

    length_error = (
        r"On level 0, code max \(3\) >= length of level \(1\)\. "
        "NOTE: this index is in an inconsistent state"
    )
    label_error = r"Unequal code lengths: \[4, 2\]"
    code_value_error = r"On level 0, code value \(-2\) < -1"

    # important to check that it's looking at the right thing.
    with pytest.raises(ValueError, match=length_error):
        MultiIndex(levels=[["a"], ["b"]], codes=[[0, 1, 2, 3], [0, 3, 4, 1]])

    with pytest.raises(ValueError, match=label_error):
        MultiIndex(levels=[["a"], ["b"]], codes=[[0, 0, 0, 0], [0, 0]])

    # external API
    with pytest.raises(ValueError, match=length_error):
        idx.copy().set_levels([["a"], ["b"]])

    with pytest.raises(ValueError, match=label_error):
        idx.copy().set_codes([[0, 0, 0, 0], [0, 0]])

    # test set_codes with verify_integrity=False
    # the setting should not raise any value error
    idx.copy().set_codes(codes=[[0, 0, 0, 0], [0, 0]], verify_integrity=False)

    # code value smaller than -1
    with pytest.raises(ValueError, match=code_value_error):
        MultiIndex(levels=[["a"], ["b"]], codes=[[0, -2], [0, 0]])


def test_na_levels():
    # GH26408
    # test if codes are re-assigned value -1 for levels
    # with missing values (NaN, NaT, None)
    result = MultiIndex(
        levels=[[np.nan, None, pd.NaT, 128, 2]], codes=[[0, -1, 1, 2, 3, 4]]
    )
    expected = MultiIndex(
        levels=[[np.nan, None, pd.NaT, 128, 2]], codes=[[-1, -1, -1, -1, 3, 4]]
    )
    tm.assert_index_equal(result, expected)

    result = MultiIndex(
        levels=[[np.nan, "s", pd.NaT, 128, None]], codes=[[0, -1, 1, 2, 3, 4]]
    )
    expected = MultiIndex(
        levels=[[np.nan, "s", pd.NaT, 128, None]], codes=[[-1, -1, 1, -1, 3, -1]]
    )
    tm.assert_index_equal(result, expected)

    # verify set_levels and set_codes
    result = MultiIndex(
        levels=[[1, 2, 3, 4, 5]], codes=[[0, -1, 1, 2, 3, 4]]
    ).set_levels([[np.nan, "s", pd.NaT, 128, None]])
    tm.assert_index_equal(result, expected)

    result = MultiIndex(
        levels=[[np.nan, "s", pd.NaT, 128, None]], codes=[[1, 2, 2, 2, 2, 2]]
    ).set_codes([[0, -1, 1, 2, 3, 4]])
    tm.assert_index_equal(result, expected)


def test_copy_in_constructor():
    levels = np.array(["a", "b", "c"])
    codes = np.array([1, 1, 2, 0, 0, 1, 1])
    val = codes[0]
    mi = MultiIndex(levels=[levels, levels], codes=[codes, codes], copy=True)
    assert mi.codes[0][0] == val
    codes[0] = 15
    assert mi.codes[0][0] == val
    val = levels[0]
    levels[0] = "PANDA"
    assert mi.levels[0][0] == val


# ----------------------------------------------------------------------------
# from_arrays
# ----------------------------------------------------------------------------
def test_from_arrays(idx):
    arrays = [
        np.asarray(lev).take(level_codes)
        for lev, level_codes in zip(idx.levels, idx.codes)
    ]

    # list of arrays as input
    result = MultiIndex.from_arrays(arrays, names=idx.names)
    tm.assert_index_equal(result, idx)

    # infer correctly
    result = MultiIndex.from_arrays([[pd.NaT, Timestamp("20130101")], ["a", "b"]])
    assert result.levels[0].equals(Index([Timestamp("20130101")]))
    assert result.levels[1].equals(Index(["a", "b"]))


def test_from_arrays_iterator(idx):
    # GH 18434
    arrays = [
        np.asarray(lev).take(level_codes)
        for lev, level_codes in zip(idx.levels, idx.codes)
    ]

    # iterator as input
    result = MultiIndex.from_arrays(iter(arrays), names=idx.names)
    tm.assert_index_equal(result, idx)

    # invalid iterator input
    msg = "Input must be a list / sequence of array-likes."
    with pytest.raises(TypeError, match=msg):
        MultiIndex.from_arrays(0)


def test_from_arrays_tuples(idx):
    arrays = tuple(
        tuple(np.asarray(lev).take(level_codes))
        for lev, level_codes in zip(idx.levels, idx.codes)
    )

    # tuple of tuples as input
    result = MultiIndex.from_arrays(arrays, names=idx.names)
    tm.assert_index_equal(result, idx)


@pytest.mark.parametrize(
    ("idx1", "idx2"),
    [
        (
            pd.period_range("2011-01-01", freq="D", periods=3),
            pd.period_range("2015-01-01", freq="h", periods=3),
        ),
        (
            date_range("2015-01-01 10:00", freq="D", periods=3, tz="US/Eastern"),
            date_range("2015-01-01 10:00", freq="h", periods=3, tz="Asia/Tokyo"),
        ),
        (
            pd.timedelta_range("1 days", freq="D", periods=3),
            pd.timedelta_range("2 hours", freq="h", periods=3),
        ),
    ],
)
def test_from_arrays_index_series_period_datetimetz_and_timedelta(idx1, idx2):
    result = MultiIndex.from_arrays([idx1, idx2])
    tm.assert_index_equal(result.get_level_values(0), idx1)
    tm.assert_index_equal(result.get_level_values(1), idx2)

    result2 = MultiIndex.from_arrays([Series(idx1), Series(idx2)])
    tm.assert_index_equal(result2.get_level_values(0), idx1)
    tm.assert_index_equal(result2.get_level_values(1), idx2)

    tm.assert_index_equal(result, result2)


def test_from_arrays_index_datetimelike_mixed():
    idx1 = date_range("2015-01-01 10:00", freq="D", periods=3, tz="US/Eastern")
    idx2 = date_range("2015-01-01 10:00", freq="h", periods=3)
    idx3 = pd.timedelta_range("1 days", freq="D", periods=3)
    idx4 = pd.period_range("2011-01-01", freq="D", periods=3)

    result = MultiIndex.from_arrays([idx1, idx2, idx3, idx4])
    tm.assert_index_equal(result.get_level_values(0), idx1)
    tm.assert_index_equal(result.get_level_values(1), idx2)
    tm.assert_index_equal(result.get_level_values(2), idx3)
    tm.assert_index_equal(result.get_level_values(3), idx4)

    result2 = MultiIndex.from_arrays(
        [Series(idx1), Series(idx2), Series(idx3), Series(idx4)]
    )
    tm.assert_index_equal(result2.get_level_values(0), idx1)
    tm.assert_index_equal(result2.get_level_values(1), idx2)
    tm.assert_index_equal(result2.get_level_values(2), idx3)
    tm.assert_index_equal(result2.get_level_values(3), idx4)

    tm.assert_index_equal(result, result2)


def test_from_arrays_index_series_categorical():
    # GH13743
    idx1 = pd.CategoricalIndex(list("abcaab"), categories=list("bac"), ordered=False)
    idx2 = pd.CategoricalIndex(list("abcaab"), categories=list("bac"), ordered=True)

    result = MultiIndex.from_arrays([idx1, idx2])
    tm.assert_index_equal(result.get_level_values(0), idx1)
    tm.assert_index_equal(result.get_level_values(1), idx2)

    result2 = MultiIndex.from_arrays([Series(idx1), Series(idx2)])
    tm.assert_index_equal(result2.get_level_values(0), idx1)
    tm.assert_index_equal(result2.get_level_values(1), idx2)

    result3 = MultiIndex.from_arrays([idx1.values, idx2.values])
    tm.assert_index_equal(result3.get_level_values(0), idx1)
    tm.assert_index_equal(result3.get_level_values(1), idx2)


def test_from_arrays_empty():
    # 0 levels
    msg = "Must pass non-zero number of levels/codes"
    with pytest.raises(ValueError, match=msg):
        MultiIndex.from_arrays(arrays=[])

    # 1 level
    result = MultiIndex.from_arrays(arrays=[[]], names=["A"])
    assert isinstance(result, MultiIndex)
    expected = Index([], name="A")
    tm.assert_index_equal(result.levels[0], expected)
    assert result.names == ["A"]

    # N levels
    for N in [2, 3]:
        arrays = [[]] * N
        names = list("ABC")[:N]
        result = MultiIndex.from_arrays(arrays=arrays, names=names)
        expected = MultiIndex(levels=[[]] * N, codes=[[]] * N, names=names)
        tm.assert_index_equal(result, expected)


@pytest.mark.parametrize(
    "invalid_sequence_of_arrays",
    [
        1,
        [1],
        [1, 2],
        [[1], 2],
        [1, [2]],
        "a",
        ["a"],
        ["a", "b"],
        [["a"], "b"],
        (1,),
        (1, 2),
        ([1], 2),
        (1, [2]),
        "a",
        ("a",),
        ("a", "b"),
        (["a"], "b"),
        [(1,), 2],
        [1, (2,)],
        [("a",), "b"],
        ((1,), 2),
        (1, (2,)),
        (("a",), "b"),
    ],
)
def test_from_arrays_invalid_input(invalid_sequence_of_arrays):
    msg = "Input must be a list / sequence of array-likes"
    with pytest.raises(TypeError, match=msg):
        MultiIndex.from_arrays(arrays=invalid_sequence_of_arrays)


@pytest.mark.parametrize(
    "idx1, idx2", [([1, 2, 3], ["a", "b"]), ([], ["a", "b"]), ([1, 2, 3], [])]
)
def test_from_arrays_different_lengths(idx1, idx2):
    # see gh-13599
    msg = "^all arrays must be same length$"
    with pytest.raises(ValueError, match=msg):
        MultiIndex.from_arrays([idx1, idx2])


def test_from_arrays_respects_none_names():
    # GH27292
    a = Series([1, 2, 3], name="foo")
    b = Series(["a", "b", "c"], name="bar")

    result = MultiIndex.from_arrays([a, b], names=None)
    expected = MultiIndex(
        levels=[[1, 2, 3], ["a", "b", "c"]], codes=[[0, 1, 2], [0, 1, 2]], names=None
    )

    tm.assert_index_equal(result, expected)


# ----------------------------------------------------------------------------
# from_tuples
# ----------------------------------------------------------------------------
def test_from_tuples():
    msg = "Cannot infer number of levels from empty list"
    with pytest.raises(TypeError, match=msg):
        MultiIndex.from_tuples([])

    expected = MultiIndex(
        levels=[[1, 3], [2, 4]], codes=[[0, 1], [0, 1]], names=["a", "b"]
    )

    # input tuples
    result = MultiIndex.from_tuples(((1, 2), (3, 4)), names=["a", "b"])
    tm.assert_index_equal(result, expected)


def test_from_tuples_iterator():
    # GH 18434
    # input iterator for tuples
    expected = MultiIndex(
        levels=[[1, 3], [2, 4]], codes=[[0, 1], [0, 1]], names=["a", "b"]
    )

    result = MultiIndex.from_tuples(zip([1, 3], [2, 4]), names=["a", "b"])
    tm.assert_index_equal(result, expected)

    # input non-iterables
    msg = "Input must be a list / sequence of tuple-likes."
    with pytest.raises(TypeError, match=msg):
        MultiIndex.from_tuples(0)


def test_from_tuples_empty():
    # GH 16777
    result = MultiIndex.from_tuples([], names=["a", "b"])
    expected = MultiIndex.from_arrays(arrays=[[], []], names=["a", "b"])
    tm.assert_index_equal(result, expected)


def test_from_tuples_index_values(idx):
    result = MultiIndex.from_tuples(idx)
    assert (result.values == idx.values).all()


def test_tuples_with_name_string():
    # GH 15110 and GH 14848

    li = [(0, 0, 1), (0, 1, 0), (1, 0, 0)]
    msg = "Names should be list-like for a MultiIndex"
    with pytest.raises(ValueError, match=msg):
        Index(li, name="abc")
    with pytest.raises(ValueError, match=msg):
        Index(li, name="a")


def test_from_tuples_with_tuple_label():
    # GH 15457
    expected = pd.DataFrame(
        [[2, 1, 2], [4, (1, 2), 3]], columns=["a", "b", "c"]
    ).set_index(["a", "b"])
    idx = MultiIndex.from_tuples([(2, 1), (4, (1, 2))], names=("a", "b"))
    result = pd.DataFrame([2, 3], columns=["c"], index=idx)
    tm.assert_frame_equal(expected, result)


# ----------------------------------------------------------------------------
# from_product
# ----------------------------------------------------------------------------
def test_from_product_empty_zero_levels():
    # 0 levels
    msg = "Must pass non-zero number of levels/codes"
    with pytest.raises(ValueError, match=msg):
        MultiIndex.from_product([])


def test_from_product_empty_one_level():
    result = MultiIndex.from_product([[]], names=["A"])
    expected = Index([], name="A")
    tm.assert_index_equal(result.levels[0], expected)
    assert result.names == ["A"]


@pytest.mark.parametrize(
    "first, second", [([], []), (["foo", "bar", "baz"], []), ([], ["a", "b", "c"])]
)
def test_from_product_empty_two_levels(first, second):
    names = ["A", "B"]
    result = MultiIndex.from_product([first, second], names=names)
    expected = MultiIndex(levels=[first, second], codes=[[], []], names=names)
    tm.assert_index_equal(result, expected)


@pytest.mark.parametrize("N", list(range(4)))
def test_from_product_empty_three_levels(N):
    # GH12258
    names = ["A", "B", "C"]
    lvl2 = list(range(N))
    result = MultiIndex.from_product([[], lvl2, []], names=names)
    expected = MultiIndex(levels=[[], lvl2, []], codes=[[], [], []], names=names)
    tm.assert_index_equal(result, expected)


@pytest.mark.parametrize(
    "invalid_input", [1, [1], [1, 2], [[1], 2], "a", ["a"], ["a", "b"], [["a"], "b"]]
)
def test_from_product_invalid_input(invalid_input):
    msg = r"Input must be a list / sequence of iterables|Input must be list-like"
    with pytest.raises(TypeError, match=msg):
        MultiIndex.from_product(iterables=invalid_input)


def test_from_product_datetimeindex():
    dt_index = date_range("2000-01-01", periods=2)
    mi = MultiIndex.from_product([[1, 2], dt_index])
    etalon = construct_1d_object_array_from_listlike(
        [
            (1, Timestamp("2000-01-01")),
            (1, Timestamp("2000-01-02")),
            (2, Timestamp("2000-01-01")),
            (2, Timestamp("2000-01-02")),
        ]
    )
    tm.assert_numpy_array_equal(mi.values, etalon)


def test_from_product_rangeindex():
    # RangeIndex is preserved by factorize, so preserved in levels
    rng = Index(range(5))
    other = ["a", "b"]
    mi = MultiIndex.from_product([rng, other])
    tm.assert_index_equal(mi._levels[0], rng, exact=True)


@pytest.mark.parametrize("ordered", [False, True])
@pytest.mark.parametrize("f", [lambda x: x, lambda x: Series(x), lambda x: x.values])
def test_from_product_index_series_categorical(ordered, f):
    # GH13743
    first = ["foo", "bar"]

    idx = pd.CategoricalIndex(list("abcaab"), categories=list("bac"), ordered=ordered)
    expected = pd.CategoricalIndex(
        list("abcaab") + list("abcaab"), categories=list("bac"), ordered=ordered
    )

    result = MultiIndex.from_product([first, f(idx)])
    tm.assert_index_equal(result.get_level_values(1), expected)


def test_from_product():
    first = ["foo", "bar", "buz"]
    second = ["a", "b", "c"]
    names = ["first", "second"]
    result = MultiIndex.from_product([first, second], names=names)

    tuples = [
        ("foo", "a"),
        ("foo", "b"),
        ("foo", "c"),
        ("bar", "a"),
        ("bar", "b"),
        ("bar", "c"),
        ("buz", "a"),
        ("buz", "b"),
        ("buz", "c"),
    ]
    expected = MultiIndex.from_tuples(tuples, names=names)

    tm.assert_index_equal(result, expected)


def test_from_product_iterator():
    # GH 18434
    first = ["foo", "bar", "buz"]
    second = ["a", "b", "c"]
    names = ["first", "second"]
    tuples = [
        ("foo", "a"),
        ("foo", "b"),
        ("foo", "c"),
        ("bar", "a"),
        ("bar", "b"),
        ("bar", "c"),
        ("buz", "a"),
        ("buz", "b"),
        ("buz", "c"),
    ]
    expected = MultiIndex.from_tuples(tuples, names=names)

    # iterator as input
    result = MultiIndex.from_product(iter([first, second]), names=names)
    tm.assert_index_equal(result, expected)

    # Invalid non-iterable input
    msg = "Input must be a list / sequence of iterables."
    with pytest.raises(TypeError, match=msg):
        MultiIndex.from_product(0)


@pytest.mark.parametrize(
    "a, b, expected_names",
    [
        (
            Series([1, 2, 3], name="foo"),
            Series(["a", "b"], name="bar"),
            ["foo", "bar"],
        ),
        (Series([1, 2, 3], name="foo"), ["a", "b"], ["foo", None]),
        ([1, 2, 3], ["a", "b"], None),
    ],
)
def test_from_product_infer_names(a, b, expected_names):
    # GH27292
    result = MultiIndex.from_product([a, b])
    expected = MultiIndex(
        levels=[[1, 2, 3], ["a", "b"]],
        codes=[[0, 0, 1, 1, 2, 2], [0, 1, 0, 1, 0, 1]],
        names=expected_names,
    )
    tm.assert_index_equal(result, expected)


def test_from_product_respects_none_names():
    # GH27292
    a = Series([1, 2, 3], name="foo")
    b = Series(["a", "b"], name="bar")

    result = MultiIndex.from_product([a, b], names=None)
    expected = MultiIndex(
        levels=[[1, 2, 3], ["a", "b"]],
        codes=[[0, 0, 1, 1, 2, 2], [0, 1, 0, 1, 0, 1]],
        names=None,
    )
    tm.assert_index_equal(result, expected)


def test_from_product_readonly():
    # GH#15286 passing read-only array to from_product
    a = np.array(range(3))
    b = ["a", "b"]
    expected = MultiIndex.from_product([a, b])

    a.setflags(write=False)
    result = MultiIndex.from_product([a, b])
    tm.assert_index_equal(result, expected)


def test_create_index_existing_name(idx):
    # GH11193, when an existing index is passed, and a new name is not
    # specified, the new index should inherit the previous object name
    index = idx
    index.names = ["foo", "bar"]
    result = Index(index)
    expected = Index(
        Index(
            [
                ("foo", "one"),
                ("foo", "two"),
                ("bar", "one"),
                ("baz", "two"),
                ("qux", "one"),
                ("qux", "two"),
            ],
            dtype="object",
        )
    )
    tm.assert_index_equal(result, expected)

    result = Index(index, name="A")
    expected = Index(
        Index(
            [
                ("foo", "one"),
                ("foo", "two"),
                ("bar", "one"),
                ("baz", "two"),
                ("qux", "one"),
                ("qux", "two"),
            ],
            dtype="object",
        ),
        name="A",
    )
    tm.assert_index_equal(result, expected)


# ----------------------------------------------------------------------------
# from_frame
# ----------------------------------------------------------------------------
def test_from_frame():
    # GH 22420
    df = pd.DataFrame(
        [["a", "a"], ["a", "b"], ["b", "a"], ["b", "b"]], columns=["L1", "L2"]
    )
    expected = MultiIndex.from_tuples(
        [("a", "a"), ("a", "b"), ("b", "a"), ("b", "b")], names=["L1", "L2"]
    )
    result = MultiIndex.from_frame(df)
    tm.assert_index_equal(expected, result)


def test_from_frame_missing_values_multiIndex():
    # GH 39984
    pa = pytest.importorskip("pyarrow")

    df = pd.DataFrame(
        {
            "a": Series([1, 2, None], dtype="Int64"),
            "b": pd.Float64Dtype().__from_arrow__(pa.array([0.2, np.nan, None])),
        }
    )
    multi_indexed = MultiIndex.from_frame(df)
    expected = MultiIndex.from_arrays(
        [
            Series([1, 2, None]).astype("Int64"),
            pd.Float64Dtype().__from_arrow__(pa.array([0.2, np.nan, None])),
        ],
        names=["a", "b"],
    )
    tm.assert_index_equal(multi_indexed, expected)


@pytest.mark.parametrize(
    "non_frame",
    [
        Series([1, 2, 3, 4]),
        [1, 2, 3, 4],
        [[1, 2], [3, 4], [5, 6]],
        Index([1, 2, 3, 4]),
        np.array([[1, 2], [3, 4], [5, 6]]),
        27,
    ],
)
def test_from_frame_error(non_frame):
    # GH 22420
    with pytest.raises(TypeError, match="Input must be a DataFrame"):
        MultiIndex.from_frame(non_frame)


def test_from_frame_dtype_fidelity():
    # GH 22420
    df = pd.DataFrame(
        {
            "dates": date_range("19910905", periods=6, tz="US/Eastern"),
            "a": [1, 1, 1, 2, 2, 2],
            "b": pd.Categorical(["a", "a", "b", "b", "c", "c"], ordered=True),
            "c": ["x", "x", "y", "z", "x", "y"],
        }
    )
    original_dtypes = df.dtypes.to_dict()

    expected_mi = MultiIndex.from_arrays(
        [
            date_range("19910905", periods=6, tz="US/Eastern"),
            [1, 1, 1, 2, 2, 2],
            pd.Categorical(["a", "a", "b", "b", "c", "c"], ordered=True),
            ["x", "x", "y", "z", "x", "y"],
        ],
        names=["dates", "a", "b", "c"],
    )
    mi = MultiIndex.from_frame(df)
    mi_dtypes = {name: mi.levels[i].dtype for i, name in enumerate(mi.names)}

    tm.assert_index_equal(expected_mi, mi)
    assert original_dtypes == mi_dtypes


@pytest.mark.parametrize(
    "names_in,names_out", [(None, [("L1", "x"), ("L2", "y")]), (["x", "y"], ["x", "y"])]
)
def test_from_frame_valid_names(names_in, names_out):
    # GH 22420
    df = pd.DataFrame(
        [["a", "a"], ["a", "b"], ["b", "a"], ["b", "b"]],
        columns=MultiIndex.from_tuples([("L1", "x"), ("L2", "y")]),
    )
    mi = MultiIndex.from_frame(df, names=names_in)
    assert mi.names == names_out


@pytest.mark.parametrize(
    "names,expected_error_msg",
    [
        ("bad_input", "Names should be list-like for a MultiIndex"),
        (["a", "b", "c"], "Length of names must match number of levels in MultiIndex"),
    ],
)
def test_from_frame_invalid_names(names, expected_error_msg):
    # GH 22420
    df = pd.DataFrame(
        [["a", "a"], ["a", "b"], ["b", "a"], ["b", "b"]],
        columns=MultiIndex.from_tuples([("L1", "x"), ("L2", "y")]),
    )
    with pytest.raises(ValueError, match=expected_error_msg):
        MultiIndex.from_frame(df, names=names)


def test_index_equal_empty_iterable():
    # #16844
    a = MultiIndex(levels=[[], []], codes=[[], []], names=["a", "b"])
    b = MultiIndex.from_arrays(arrays=[[], []], names=["a", "b"])
    tm.assert_index_equal(a, b)


def test_raise_invalid_sortorder():
    # Test that the MultiIndex constructor raise when a incorrect sortorder is given
    # GH#28518

    levels = [[0, 1], [0, 1, 2]]

    # Correct sortorder
    MultiIndex(
        levels=levels, codes=[[0, 0, 0, 1, 1, 1], [0, 1, 2, 0, 1, 2]], sortorder=2
    )

    with pytest.raises(ValueError, match=r".* sortorder 2 with lexsort_depth 1.*"):
        MultiIndex(
            levels=levels, codes=[[0, 0, 0, 1, 1, 1], [0, 1, 2, 0, 2, 1]], sortorder=2
        )

    with pytest.raises(ValueError, match=r".* sortorder 1 with lexsort_depth 0.*"):
        MultiIndex(
            levels=levels, codes=[[0, 0, 1, 0, 1, 1], [0, 1, 0, 2, 2, 1]], sortorder=1
        )


def test_datetimeindex():
    idx1 = pd.DatetimeIndex(
        ["2013-04-01 9:00", "2013-04-02 9:00", "2013-04-03 9:00"] * 2, tz="Asia/Tokyo"
    )
    idx2 = date_range("2010/01/01", periods=6, freq="ME", tz="US/Eastern")
    idx = MultiIndex.from_arrays([idx1, idx2])

    expected1 = pd.DatetimeIndex(
        ["2013-04-01 9:00", "2013-04-02 9:00", "2013-04-03 9:00"], tz="Asia/Tokyo"
    )

    tm.assert_index_equal(idx.levels[0], expected1)
    tm.assert_index_equal(idx.levels[1], idx2)

    # from datetime combos
    # GH 7888
    date1 = np.datetime64("today")
    date2 = datetime.today()
    date3 = Timestamp.today()

    for d1, d2 in itertools.product([date1, date2, date3], [date1, date2, date3]):
        index = MultiIndex.from_product([[d1], [d2]])
        assert isinstance(index.levels[0], pd.DatetimeIndex)
        assert isinstance(index.levels[1], pd.DatetimeIndex)

    # but NOT date objects, matching Index behavior
    date4 = date.today()
    index = MultiIndex.from_product([[date4], [date2]])
    assert not isinstance(index.levels[0], pd.DatetimeIndex)
    assert isinstance(index.levels[1], pd.DatetimeIndex)


def test_constructor_with_tz():
    index = pd.DatetimeIndex(
        ["2013/01/01 09:00", "2013/01/02 09:00"], name="dt1", tz="US/Pacific"
    )
    columns = pd.DatetimeIndex(
        ["2014/01/01 09:00", "2014/01/02 09:00"], name="dt2", tz="Asia/Tokyo"
    )

    result = MultiIndex.from_arrays([index, columns])

    assert result.names == ["dt1", "dt2"]
    tm.assert_index_equal(result.levels[0], index)
    tm.assert_index_equal(result.levels[1], columns)

    result = MultiIndex.from_arrays([Series(index), Series(columns)])

    assert result.names == ["dt1", "dt2"]
    tm.assert_index_equal(result.levels[0], index)
    tm.assert_index_equal(result.levels[1], columns)


def test_multiindex_inference_consistency():
    # check that inference behavior matches the base class

    v = date.today()

    arr = [v, v]

    idx = Index(arr)
    assert idx.dtype == object

    mi = MultiIndex.from_arrays([arr])
    lev = mi.levels[0]
    assert lev.dtype == object

    mi = MultiIndex.from_product([arr])
    lev = mi.levels[0]
    assert lev.dtype == object

    mi = MultiIndex.from_tuples([(x,) for x in arr])
    lev = mi.levels[0]
    assert lev.dtype == object


def test_dtype_representation(using_infer_string):
    # GH#46900
    pmidx = MultiIndex.from_arrays([[1], ["a"]], names=[("a", "b"), ("c", "d")])
    result = pmidx.dtypes
    exp = "object" if not using_infer_string else pd.StringDtype(na_value=np.nan)
    expected = Series(
        ["int64", exp],
        index=MultiIndex.from_tuples([("a", "b"), ("c", "d")]),
        dtype=object,
    )
    tm.assert_series_equal(result, expected)
