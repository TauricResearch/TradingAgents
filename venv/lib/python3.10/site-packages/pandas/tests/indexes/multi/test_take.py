import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm


def test_take(idx):
    indexer = [4, 3, 0, 2]
    result = idx.take(indexer)
    expected = idx[indexer]
    assert result.equals(expected)

    # GH 10791
    msg = "'MultiIndex' object has no attribute 'freq'"
    with pytest.raises(AttributeError, match=msg):
        idx.freq


def test_take_invalid_kwargs(idx):
    indices = [1, 2]

    msg = r"take\(\) got an unexpected keyword argument 'foo'"
    with pytest.raises(TypeError, match=msg):
        idx.take(indices, foo=2)

    msg = "the 'out' parameter is not supported"
    with pytest.raises(ValueError, match=msg):
        idx.take(indices, out=indices)

    msg = "the 'mode' parameter is not supported"
    with pytest.raises(ValueError, match=msg):
        idx.take(indices, mode="clip")


def test_take_fill_value():
    # GH 12631
    vals = [["A", "B"], [pd.Timestamp("2011-01-01"), pd.Timestamp("2011-01-02")]]
    idx = pd.MultiIndex.from_product(vals, names=["str", "dt"])

    result = idx.take(np.array([1, 0, -1]))
    exp_vals = [
        ("A", pd.Timestamp("2011-01-02")),
        ("A", pd.Timestamp("2011-01-01")),
        ("B", pd.Timestamp("2011-01-02")),
    ]
    expected = pd.MultiIndex.from_tuples(exp_vals, names=["str", "dt"])
    tm.assert_index_equal(result, expected)

    # fill_value
    result = idx.take(np.array([1, 0, -1]), fill_value=True)
    exp_vals = [
        ("A", pd.Timestamp("2011-01-02")),
        ("A", pd.Timestamp("2011-01-01")),
        (np.nan, pd.NaT),
    ]
    expected = pd.MultiIndex.from_tuples(exp_vals, names=["str", "dt"])
    tm.assert_index_equal(result, expected)

    # allow_fill=False
    result = idx.take(np.array([1, 0, -1]), allow_fill=False, fill_value=True)
    exp_vals = [
        ("A", pd.Timestamp("2011-01-02")),
        ("A", pd.Timestamp("2011-01-01")),
        ("B", pd.Timestamp("2011-01-02")),
    ]
    expected = pd.MultiIndex.from_tuples(exp_vals, names=["str", "dt"])
    tm.assert_index_equal(result, expected)

    msg = "When allow_fill=True and fill_value is not None, all indices must be >= -1"
    with pytest.raises(ValueError, match=msg):
        idx.take(np.array([1, 0, -2]), fill_value=True)
    with pytest.raises(ValueError, match=msg):
        idx.take(np.array([1, 0, -5]), fill_value=True)

    msg = "index -5 is out of bounds for( axis 0 with)? size 4"
    with pytest.raises(IndexError, match=msg):
        idx.take(np.array([1, -5]))
