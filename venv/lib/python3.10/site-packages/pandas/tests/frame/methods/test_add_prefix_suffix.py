import pytest

from pandas import Index
import pandas._testing as tm


def test_add_prefix_suffix(float_frame):
    with_prefix = float_frame.add_prefix("foo#")
    expected = Index([f"foo#{c}" for c in float_frame.columns])
    tm.assert_index_equal(with_prefix.columns, expected)

    with_suffix = float_frame.add_suffix("#foo")
    expected = Index([f"{c}#foo" for c in float_frame.columns])
    tm.assert_index_equal(with_suffix.columns, expected)

    with_pct_prefix = float_frame.add_prefix("%")
    expected = Index([f"%{c}" for c in float_frame.columns])
    tm.assert_index_equal(with_pct_prefix.columns, expected)

    with_pct_suffix = float_frame.add_suffix("%")
    expected = Index([f"{c}%" for c in float_frame.columns])
    tm.assert_index_equal(with_pct_suffix.columns, expected)


def test_add_prefix_suffix_axis(float_frame):
    # GH 47819
    with_prefix = float_frame.add_prefix("foo#", axis=0)
    expected = Index([f"foo#{c}" for c in float_frame.index])
    tm.assert_index_equal(with_prefix.index, expected)

    with_prefix = float_frame.add_prefix("foo#", axis=1)
    expected = Index([f"foo#{c}" for c in float_frame.columns])
    tm.assert_index_equal(with_prefix.columns, expected)

    with_pct_suffix = float_frame.add_suffix("#foo", axis=0)
    expected = Index([f"{c}#foo" for c in float_frame.index])
    tm.assert_index_equal(with_pct_suffix.index, expected)

    with_pct_suffix = float_frame.add_suffix("#foo", axis=1)
    expected = Index([f"{c}#foo" for c in float_frame.columns])
    tm.assert_index_equal(with_pct_suffix.columns, expected)


def test_add_prefix_suffix_invalid_axis(float_frame):
    with pytest.raises(ValueError, match="No axis named 2 for object type DataFrame"):
        float_frame.add_prefix("foo#", axis=2)

    with pytest.raises(ValueError, match="No axis named 2 for object type DataFrame"):
        float_frame.add_suffix("foo#", axis=2)
