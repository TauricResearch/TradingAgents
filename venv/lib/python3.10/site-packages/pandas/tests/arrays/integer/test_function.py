import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays import FloatingArray


@pytest.mark.parametrize("ufunc", [np.abs, np.sign])
# np.sign emits a warning with nans, <https://github.com/numpy/numpy/issues/15127>
@pytest.mark.filterwarnings("ignore:invalid value encountered in sign:RuntimeWarning")
def test_ufuncs_single_int(ufunc):
    a = pd.array([1, 2, -3, np.nan])
    result = ufunc(a)
    expected = pd.array(ufunc(a.astype(float)), dtype="Int64")
    tm.assert_extension_array_equal(result, expected)

    s = pd.Series(a)
    result = ufunc(s)
    expected = pd.Series(pd.array(ufunc(a.astype(float)), dtype="Int64"))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("ufunc", [np.log, np.exp, np.sin, np.cos, np.sqrt])
def test_ufuncs_single_float(ufunc):
    a = pd.array([1, 2, -3, np.nan])
    with np.errstate(invalid="ignore"):
        result = ufunc(a)
        expected = FloatingArray(ufunc(a.astype(float)), mask=a._mask)
    tm.assert_extension_array_equal(result, expected)

    s = pd.Series(a)
    with np.errstate(invalid="ignore"):
        result = ufunc(s)
    expected = pd.Series(expected)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("ufunc", [np.add, np.subtract])
def test_ufuncs_binary_int(ufunc):
    # two IntegerArrays
    a = pd.array([1, 2, -3, np.nan])
    result = ufunc(a, a)
    expected = pd.array(ufunc(a.astype(float), a.astype(float)), dtype="Int64")
    tm.assert_extension_array_equal(result, expected)

    # IntegerArray with numpy array
    arr = np.array([1, 2, 3, 4])
    result = ufunc(a, arr)
    expected = pd.array(ufunc(a.astype(float), arr), dtype="Int64")
    tm.assert_extension_array_equal(result, expected)

    result = ufunc(arr, a)
    expected = pd.array(ufunc(arr, a.astype(float)), dtype="Int64")
    tm.assert_extension_array_equal(result, expected)

    # IntegerArray with scalar
    result = ufunc(a, 1)
    expected = pd.array(ufunc(a.astype(float), 1), dtype="Int64")
    tm.assert_extension_array_equal(result, expected)

    result = ufunc(1, a)
    expected = pd.array(ufunc(1, a.astype(float)), dtype="Int64")
    tm.assert_extension_array_equal(result, expected)


def test_ufunc_binary_output():
    a = pd.array([1, 2, np.nan])
    result = np.modf(a)
    expected = np.modf(a.to_numpy(na_value=np.nan, dtype="float"))
    expected = (pd.array(expected[0]), pd.array(expected[1]))

    assert isinstance(result, tuple)
    assert len(result) == 2

    for x, y in zip(result, expected):
        tm.assert_extension_array_equal(x, y)


@pytest.mark.parametrize("values", [[0, 1], [0, None]])
def test_ufunc_reduce_raises(values):
    arr = pd.array(values)

    res = np.add.reduce(arr)
    expected = arr.sum(skipna=False)
    tm.assert_almost_equal(res, expected)


@pytest.mark.parametrize(
    "pandasmethname, kwargs",
    [
        ("var", {"ddof": 0}),
        ("var", {"ddof": 1}),
        ("std", {"ddof": 0}),
        ("std", {"ddof": 1}),
        ("kurtosis", {}),
        ("skew", {}),
        ("sem", {}),
    ],
)
def test_stat_method(pandasmethname, kwargs):
    s = pd.Series(data=[1, 2, 3, 4, 5, 6, np.nan, np.nan], dtype="Int64")
    pandasmeth = getattr(s, pandasmethname)
    result = pandasmeth(**kwargs)
    s2 = pd.Series(data=[1, 2, 3, 4, 5, 6], dtype="Int64")
    pandasmeth = getattr(s2, pandasmethname)
    expected = pandasmeth(**kwargs)
    assert expected == result


def test_value_counts_na():
    arr = pd.array([1, 2, 1, pd.NA], dtype="Int64")
    result = arr.value_counts(dropna=False)
    ex_index = pd.Index([1, 2, pd.NA], dtype="Int64")
    assert ex_index.dtype == "Int64"
    expected = pd.Series([2, 1, 1], index=ex_index, dtype="Int64", name="count")
    tm.assert_series_equal(result, expected)

    result = arr.value_counts(dropna=True)
    expected = pd.Series([2, 1], index=arr[:2], dtype="Int64", name="count")
    assert expected.index.dtype == arr.dtype
    tm.assert_series_equal(result, expected)


def test_value_counts_empty():
    # https://github.com/pandas-dev/pandas/issues/33317
    ser = pd.Series([], dtype="Int64")
    result = ser.value_counts()
    idx = pd.Index([], dtype=ser.dtype)
    assert idx.dtype == ser.dtype
    expected = pd.Series([], index=idx, dtype="Int64", name="count")
    tm.assert_series_equal(result, expected)


def test_value_counts_with_normalize():
    # GH 33172
    ser = pd.Series([1, 2, 1, pd.NA], dtype="Int64")
    result = ser.value_counts(normalize=True)
    expected = pd.Series([2, 1], index=ser[:2], dtype="Float64", name="proportion") / 3
    assert expected.index.dtype == ser.dtype
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("skipna", [True, False])
@pytest.mark.parametrize("min_count", [0, 4])
def test_integer_array_sum(skipna, min_count, any_int_ea_dtype):
    dtype = any_int_ea_dtype
    arr = pd.array([1, 2, 3, None], dtype=dtype)
    result = arr.sum(skipna=skipna, min_count=min_count)
    if skipna and min_count == 0:
        assert result == 6
    else:
        assert result is pd.NA


@pytest.mark.parametrize("skipna", [True, False])
@pytest.mark.parametrize("method", ["min", "max"])
def test_integer_array_min_max(skipna, method, any_int_ea_dtype):
    dtype = any_int_ea_dtype
    arr = pd.array([0, 1, None], dtype=dtype)
    func = getattr(arr, method)
    result = func(skipna=skipna)
    if skipna:
        assert result == (0 if method == "min" else 1)
    else:
        assert result is pd.NA


@pytest.mark.parametrize("skipna", [True, False])
@pytest.mark.parametrize("min_count", [0, 9])
def test_integer_array_prod(skipna, min_count, any_int_ea_dtype):
    dtype = any_int_ea_dtype
    arr = pd.array([1, 2, None], dtype=dtype)
    result = arr.prod(skipna=skipna, min_count=min_count)
    if skipna and min_count == 0:
        assert result == 2
    else:
        assert result is pd.NA


@pytest.mark.parametrize(
    "values, expected", [([1, 2, 3], 6), ([1, 2, 3, None], 6), ([None], 0)]
)
def test_integer_array_numpy_sum(values, expected):
    arr = pd.array(values, dtype="Int64")
    result = np.sum(arr)
    assert result == expected


@pytest.mark.parametrize("op", ["sum", "prod", "min", "max"])
def test_dataframe_reductions(op):
    # https://github.com/pandas-dev/pandas/pull/32867
    # ensure the integers are not cast to float during reductions
    df = pd.DataFrame({"a": pd.array([1, 2], dtype="Int64")})
    result = df.max()
    assert isinstance(result["a"], np.int64)


# TODO(jreback) - these need testing / are broken

# shift

# set_index (destroys type)
