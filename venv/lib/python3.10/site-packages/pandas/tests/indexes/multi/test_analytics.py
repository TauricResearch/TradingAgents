import numpy as np
import pytest

import pandas as pd
from pandas import (
    Index,
    MultiIndex,
    date_range,
    period_range,
)
import pandas._testing as tm


def test_infer_objects(idx):
    with pytest.raises(NotImplementedError, match="to_frame"):
        idx.infer_objects()


def test_shift(idx):
    # GH8083 test the base class for shift
    msg = (
        "This method is only implemented for DatetimeIndex, PeriodIndex and "
        "TimedeltaIndex; Got type MultiIndex"
    )
    with pytest.raises(NotImplementedError, match=msg):
        idx.shift(1)
    with pytest.raises(NotImplementedError, match=msg):
        idx.shift(1, 2)


def test_groupby(idx):
    groups = idx.groupby(np.array([1, 1, 1, 2, 2, 2]))
    labels = idx.tolist()
    exp = {1: labels[:3], 2: labels[3:]}
    tm.assert_dict_equal(groups, exp)

    # GH5620
    groups = idx.groupby(idx)
    exp = {key: [key] for key in idx}
    tm.assert_dict_equal(groups, exp)


def test_truncate_multiindex():
    # GH 34564 for MultiIndex level names check
    major_axis = Index(list(range(4)))
    minor_axis = Index(list(range(2)))

    major_codes = np.array([0, 0, 1, 2, 3, 3])
    minor_codes = np.array([0, 1, 0, 1, 0, 1])

    index = MultiIndex(
        levels=[major_axis, minor_axis],
        codes=[major_codes, minor_codes],
        names=["L1", "L2"],
    )

    result = index.truncate(before=1)
    assert "foo" not in result.levels[0]
    assert 1 in result.levels[0]
    assert index.names == result.names

    result = index.truncate(after=1)
    assert 2 not in result.levels[0]
    assert 1 in result.levels[0]
    assert index.names == result.names

    result = index.truncate(before=1, after=2)
    assert len(result.levels[0]) == 2
    assert index.names == result.names

    msg = "after < before"
    with pytest.raises(ValueError, match=msg):
        index.truncate(3, 1)


# TODO: reshape


def test_reorder_levels(idx):
    # this blows up
    with pytest.raises(IndexError, match="^Too many levels"):
        idx.reorder_levels([2, 1, 0])


def test_numpy_repeat():
    reps = 2
    numbers = [1, 2, 3]
    names = np.array(["foo", "bar"])

    m = MultiIndex.from_product([numbers, names], names=names)
    expected = MultiIndex.from_product([numbers, names.repeat(reps)], names=names)
    tm.assert_index_equal(np.repeat(m, reps), expected)

    msg = "the 'axis' parameter is not supported"
    with pytest.raises(ValueError, match=msg):
        np.repeat(m, reps, axis=1)


def test_append_mixed_dtypes():
    # GH 13660
    dti = date_range("2011-01-01", freq="ME", periods=3)
    dti_tz = date_range("2011-01-01", freq="ME", periods=3, tz="US/Eastern")
    pi = period_range("2011-01", freq="M", periods=3)

    mi = MultiIndex.from_arrays(
        [[1, 2, 3], [1.1, np.nan, 3.3], ["a", "b", "c"], dti, dti_tz, pi]
    )
    assert mi.nlevels == 6

    res = mi.append(mi)
    exp = MultiIndex.from_arrays(
        [
            [1, 2, 3, 1, 2, 3],
            [1.1, np.nan, 3.3, 1.1, np.nan, 3.3],
            ["a", "b", "c", "a", "b", "c"],
            dti.append(dti),
            dti_tz.append(dti_tz),
            pi.append(pi),
        ]
    )
    tm.assert_index_equal(res, exp)

    other = MultiIndex.from_arrays(
        [
            ["x", "y", "z"],
            ["x", "y", "z"],
            ["x", "y", "z"],
            ["x", "y", "z"],
            ["x", "y", "z"],
            ["x", "y", "z"],
        ]
    )

    res = mi.append(other)
    exp = MultiIndex.from_arrays(
        [
            [1, 2, 3, "x", "y", "z"],
            [1.1, np.nan, 3.3, "x", "y", "z"],
            ["a", "b", "c", "x", "y", "z"],
            dti.append(Index(["x", "y", "z"])),
            dti_tz.append(Index(["x", "y", "z"])),
            pi.append(Index(["x", "y", "z"])),
        ]
    )
    tm.assert_index_equal(res, exp)


def test_iter(idx):
    result = list(idx)
    expected = [
        ("foo", "one"),
        ("foo", "two"),
        ("bar", "one"),
        ("baz", "two"),
        ("qux", "one"),
        ("qux", "two"),
    ]
    assert result == expected


def test_sub(idx):
    first = idx

    # - now raises (previously was set op difference)
    msg = "cannot perform __sub__ with this index type: MultiIndex"
    with pytest.raises(TypeError, match=msg):
        first - idx[-3:]
    with pytest.raises(TypeError, match=msg):
        idx[-3:] - first
    with pytest.raises(TypeError, match=msg):
        idx[-3:] - first.tolist()
    msg = "cannot perform __rsub__ with this index type: MultiIndex"
    with pytest.raises(TypeError, match=msg):
        first.tolist() - idx[-3:]


def test_map(idx):
    # callable
    index = idx

    result = index.map(lambda x: x)
    tm.assert_index_equal(result, index)


@pytest.mark.parametrize(
    "mapper",
    [
        lambda values, idx: {i: e for e, i in zip(values, idx)},
        lambda values, idx: pd.Series(values, idx),
    ],
)
def test_map_dictlike(idx, mapper):
    identity = mapper(idx.values, idx)

    # we don't infer to uint64 dtype for a dict
    if idx.dtype == np.uint64 and isinstance(identity, dict):
        expected = idx.astype("int64")
    else:
        expected = idx

    result = idx.map(identity)
    tm.assert_index_equal(result, expected)

    # empty mappable
    expected = Index([np.nan] * len(idx))
    result = idx.map(mapper(expected, idx))
    tm.assert_index_equal(result, expected)


@pytest.mark.parametrize(
    "func",
    [
        np.exp,
        np.exp2,
        np.expm1,
        np.log,
        np.log2,
        np.log10,
        np.log1p,
        np.sqrt,
        np.sin,
        np.cos,
        np.tan,
        np.arcsin,
        np.arccos,
        np.arctan,
        np.sinh,
        np.cosh,
        np.tanh,
        np.arcsinh,
        np.arccosh,
        np.arctanh,
        np.deg2rad,
        np.rad2deg,
    ],
    ids=lambda func: func.__name__,
)
def test_numpy_ufuncs(idx, func):
    # test ufuncs of numpy. see:
    # https://numpy.org/doc/stable/reference/ufuncs.html

    expected_exception = TypeError
    msg = (
        "loop of ufunc does not support argument 0 of type tuple which "
        f"has no callable {func.__name__} method"
    )
    with pytest.raises(expected_exception, match=msg):
        func(idx)


@pytest.mark.parametrize(
    "func",
    [np.isfinite, np.isinf, np.isnan, np.signbit],
    ids=lambda func: func.__name__,
)
def test_numpy_type_funcs(idx, func):
    msg = (
        f"ufunc '{func.__name__}' not supported for the input types, and the inputs "
        "could not be safely coerced to any supported types according to "
        "the casting rule ''safe''"
    )
    with pytest.raises(TypeError, match=msg):
        func(idx)
