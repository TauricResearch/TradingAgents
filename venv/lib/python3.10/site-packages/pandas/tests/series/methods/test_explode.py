import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm


def test_basic():
    s = pd.Series([[0, 1, 2], np.nan, [], (3, 4)], index=list("abcd"), name="foo")
    result = s.explode()
    expected = pd.Series(
        [0, 1, 2, np.nan, np.nan, 3, 4], index=list("aaabcdd"), dtype=object, name="foo"
    )
    tm.assert_series_equal(result, expected)


def test_mixed_type():
    s = pd.Series(
        [[0, 1, 2], np.nan, None, np.array([]), pd.Series(["a", "b"])], name="foo"
    )
    result = s.explode()
    expected = pd.Series(
        [0, 1, 2, np.nan, None, np.nan, "a", "b"],
        index=[0, 0, 0, 1, 2, 3, 4, 4],
        dtype=object,
        name="foo",
    )
    tm.assert_series_equal(result, expected)


def test_empty():
    s = pd.Series(dtype=object)
    result = s.explode()
    expected = s.copy()
    tm.assert_series_equal(result, expected)


def test_nested_lists():
    s = pd.Series([[[1, 2, 3]], [1, 2], 1])
    result = s.explode()
    expected = pd.Series([[1, 2, 3], 1, 2, 1], index=[0, 1, 1, 2])
    tm.assert_series_equal(result, expected)


def test_multi_index():
    s = pd.Series(
        [[0, 1, 2], np.nan, [], (3, 4)],
        name="foo",
        index=pd.MultiIndex.from_product([list("ab"), range(2)], names=["foo", "bar"]),
    )
    result = s.explode()
    index = pd.MultiIndex.from_tuples(
        [("a", 0), ("a", 0), ("a", 0), ("a", 1), ("b", 0), ("b", 1), ("b", 1)],
        names=["foo", "bar"],
    )
    expected = pd.Series(
        [0, 1, 2, np.nan, np.nan, 3, 4], index=index, dtype=object, name="foo"
    )
    tm.assert_series_equal(result, expected)


def test_large():
    s = pd.Series([range(256)]).explode()
    result = s.explode()
    tm.assert_series_equal(result, s)


def test_invert_array():
    df = pd.DataFrame({"a": pd.date_range("20190101", periods=3, tz="UTC")})

    listify = df.apply(lambda x: x.array, axis=1)
    result = listify.explode()
    tm.assert_series_equal(result, df["a"].rename())


@pytest.mark.parametrize(
    "s", [pd.Series([1, 2, 3]), pd.Series(pd.date_range("2019", periods=3, tz="UTC"))]
)
def test_non_object_dtype(s):
    result = s.explode()
    tm.assert_series_equal(result, s)


def test_typical_usecase():
    df = pd.DataFrame(
        [{"var1": "a,b,c", "var2": 1}, {"var1": "d,e,f", "var2": 2}],
        columns=["var1", "var2"],
    )
    exploded = df.var1.str.split(",").explode()
    result = df[["var2"]].join(exploded)
    expected = pd.DataFrame(
        {"var2": [1, 1, 1, 2, 2, 2], "var1": list("abcdef")},
        columns=["var2", "var1"],
        index=[0, 0, 0, 1, 1, 1],
    )
    tm.assert_frame_equal(result, expected)


def test_nested_EA():
    # a nested EA array
    s = pd.Series(
        [
            pd.date_range("20170101", periods=3, tz="UTC"),
            pd.date_range("20170104", periods=3, tz="UTC"),
        ]
    )
    result = s.explode()
    expected = pd.Series(
        pd.date_range("20170101", periods=6, tz="UTC"), index=[0, 0, 0, 1, 1, 1]
    )
    tm.assert_series_equal(result, expected)


def test_duplicate_index():
    # GH 28005
    s = pd.Series([[1, 2], [3, 4]], index=[0, 0])
    result = s.explode()
    expected = pd.Series([1, 2, 3, 4], index=[0, 0, 0, 0], dtype=object)
    tm.assert_series_equal(result, expected)


def test_ignore_index():
    # GH 34932
    s = pd.Series([[1, 2], [3, 4]])
    result = s.explode(ignore_index=True)
    expected = pd.Series([1, 2, 3, 4], index=[0, 1, 2, 3], dtype=object)
    tm.assert_series_equal(result, expected)


def test_explode_sets():
    # https://github.com/pandas-dev/pandas/issues/35614
    s = pd.Series([{"a", "b", "c"}], index=[1])
    result = s.explode().sort_values()
    expected = pd.Series(["a", "b", "c"], index=[1, 1, 1])
    tm.assert_series_equal(result, expected)


def test_explode_scalars_can_ignore_index():
    # https://github.com/pandas-dev/pandas/issues/40487
    s = pd.Series([1, 2, 3], index=["a", "b", "c"])
    result = s.explode(ignore_index=True)
    expected = pd.Series([1, 2, 3])
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("ignore_index", [True, False])
def test_explode_pyarrow_list_type(ignore_index):
    # GH 53602
    pa = pytest.importorskip("pyarrow")

    data = [
        [None, None],
        [1],
        [],
        [2, 3],
        None,
    ]
    ser = pd.Series(data, dtype=pd.ArrowDtype(pa.list_(pa.int64())))
    result = ser.explode(ignore_index=ignore_index)
    expected = pd.Series(
        data=[None, None, 1, None, 2, 3, None],
        index=None if ignore_index else [0, 0, 1, 2, 3, 3, 4],
        dtype=pd.ArrowDtype(pa.int64()),
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("ignore_index", [True, False])
def test_explode_pyarrow_non_list_type(ignore_index):
    pa = pytest.importorskip("pyarrow")
    data = [1, 2, 3]
    ser = pd.Series(data, dtype=pd.ArrowDtype(pa.int64()))
    result = ser.explode(ignore_index=ignore_index)
    expected = pd.Series([1, 2, 3], dtype="int64[pyarrow]", index=[0, 1, 2])
    tm.assert_series_equal(result, expected)


def test_str_dtype():
    # https://github.com/pandas-dev/pandas/pull/61623
    ser = pd.Series(["x", "y"], dtype="str")
    result = ser.explode()
    assert result is not ser
    tm.assert_series_equal(result, ser)
