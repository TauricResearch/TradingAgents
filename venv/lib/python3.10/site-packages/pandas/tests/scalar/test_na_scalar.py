from datetime import (
    date,
    time,
    timedelta,
)
import pickle

import numpy as np
import pytest

from pandas._libs.missing import NA

from pandas.core.dtypes.common import is_scalar

import pandas as pd
import pandas._testing as tm


def test_singleton():
    assert NA is NA
    new_NA = type(NA)()
    assert new_NA is NA


def test_repr():
    assert repr(NA) == "<NA>"
    assert str(NA) == "<NA>"


def test_format():
    # GH-34740
    assert format(NA) == "<NA>"
    assert format(NA, ">10") == "      <NA>"
    assert format(NA, "xxx") == "<NA>"  # NA is flexible, accept any format spec

    assert f"{NA}" == "<NA>"
    assert f"{NA:>10}" == "      <NA>"
    assert f"{NA:xxx}" == "<NA>"


def test_truthiness():
    msg = "boolean value of NA is ambiguous"

    with pytest.raises(TypeError, match=msg):
        bool(NA)

    with pytest.raises(TypeError, match=msg):
        not NA


def test_hashable():
    assert hash(NA) == hash(NA)
    d = {NA: "test"}
    assert d[NA] == "test"


@pytest.mark.parametrize(
    "other", [NA, 1, 1.0, "a", b"a", np.int64(1), np.nan], ids=repr
)
def test_arithmetic_ops(all_arithmetic_functions, other):
    op = all_arithmetic_functions

    if op.__name__ in ("pow", "rpow", "rmod") and isinstance(other, (str, bytes)):
        pytest.skip(reason=f"{op.__name__} with NA and {other} not defined.")
    if op.__name__ in ("divmod", "rdivmod"):
        assert op(NA, other) is (NA, NA)
    else:
        if op.__name__ == "rpow":
            # avoid special case
            other += 1
        assert op(NA, other) is NA


@pytest.mark.parametrize(
    "other",
    [
        NA,
        1,
        1.0,
        "a",
        b"a",
        np.int64(1),
        np.nan,
        np.bool_(True),
        time(0),
        date(1, 2, 3),
        timedelta(1),
        pd.NaT,
    ],
)
def test_comparison_ops(comparison_op, other):
    assert comparison_op(NA, other) is NA
    assert comparison_op(other, NA) is NA


@pytest.mark.parametrize(
    "value",
    [
        0,
        0.0,
        -0,
        -0.0,
        False,
        np.bool_(False),
        np.int_(0),
        np.float64(0),
        np.int_(-0),
        np.float64(-0),
    ],
)
@pytest.mark.parametrize("asarray", [True, False])
def test_pow_special(value, asarray):
    if asarray:
        value = np.array([value])
    result = NA**value

    if asarray:
        result = result[0]
    else:
        # this assertion isn't possible for ndarray.
        assert isinstance(result, type(value))
    assert result == 1


@pytest.mark.parametrize(
    "value", [1, 1.0, True, np.bool_(True), np.int_(1), np.float64(1)]
)
@pytest.mark.parametrize("asarray", [True, False])
def test_rpow_special(value, asarray):
    if asarray:
        value = np.array([value])
    result = value**NA

    if asarray:
        result = result[0]
    elif not isinstance(value, (np.float64, np.bool_, np.int_)):
        # this assertion isn't possible with asarray=True
        assert isinstance(result, type(value))

    assert result == value


@pytest.mark.parametrize("value", [-1, -1.0, np.int_(-1), np.float64(-1)])
@pytest.mark.parametrize("asarray", [True, False])
def test_rpow_minus_one(value, asarray):
    if asarray:
        value = np.array([value])
    result = value**NA

    if asarray:
        result = result[0]

    assert pd.isna(result)


def test_unary_ops():
    assert +NA is NA
    assert -NA is NA
    assert abs(NA) is NA
    assert ~NA is NA


def test_logical_and():
    assert NA & True is NA
    assert True & NA is NA
    assert NA & False is False
    assert False & NA is False
    assert NA & NA is NA

    msg = "unsupported operand type"
    with pytest.raises(TypeError, match=msg):
        NA & 5


def test_logical_or():
    assert NA | True is True
    assert True | NA is True
    assert NA | False is NA
    assert False | NA is NA
    assert NA | NA is NA

    msg = "unsupported operand type"
    with pytest.raises(TypeError, match=msg):
        NA | 5


def test_logical_xor():
    assert NA ^ True is NA
    assert True ^ NA is NA
    assert NA ^ False is NA
    assert False ^ NA is NA
    assert NA ^ NA is NA

    msg = "unsupported operand type"
    with pytest.raises(TypeError, match=msg):
        NA ^ 5


def test_logical_not():
    assert ~NA is NA


@pytest.mark.parametrize("shape", [(3,), (3, 3), (1, 2, 3)])
def test_arithmetic_ndarray(shape, all_arithmetic_functions):
    op = all_arithmetic_functions
    a = np.zeros(shape)
    if op.__name__ == "pow":
        a += 5
    result = op(NA, a)
    expected = np.full(a.shape, NA, dtype=object)
    tm.assert_numpy_array_equal(result, expected)


def test_is_scalar():
    assert is_scalar(NA) is True


def test_isna():
    assert pd.isna(NA) is True
    assert pd.notna(NA) is False


def test_series_isna():
    s = pd.Series([1, NA], dtype=object)
    expected = pd.Series([False, True])
    tm.assert_series_equal(s.isna(), expected)


def test_ufunc():
    assert np.log(NA) is NA
    assert np.add(NA, 1) is NA
    result = np.divmod(NA, 1)
    assert result[0] is NA and result[1] is NA

    result = np.frexp(NA)
    assert result[0] is NA and result[1] is NA


def test_ufunc_raises():
    msg = "ufunc method 'at'"
    with pytest.raises(ValueError, match=msg):
        np.log.at(NA, 0)


def test_binary_input_not_dunder():
    a = np.array([1, 2, 3])
    expected = np.array([NA, NA, NA], dtype=object)
    result = np.logaddexp(a, NA)
    tm.assert_numpy_array_equal(result, expected)

    result = np.logaddexp(NA, a)
    tm.assert_numpy_array_equal(result, expected)

    # all NA, multiple inputs
    assert np.logaddexp(NA, NA) is NA

    result = np.modf(NA, NA)
    assert len(result) == 2
    assert all(x is NA for x in result)


def test_divmod_ufunc():
    # binary in, binary out.
    a = np.array([1, 2, 3])
    expected = np.array([NA, NA, NA], dtype=object)

    result = np.divmod(a, NA)
    assert isinstance(result, tuple)
    for arr in result:
        tm.assert_numpy_array_equal(arr, expected)
        tm.assert_numpy_array_equal(arr, expected)

    result = np.divmod(NA, a)
    for arr in result:
        tm.assert_numpy_array_equal(arr, expected)
        tm.assert_numpy_array_equal(arr, expected)


def test_integer_hash_collision_dict():
    # GH 30013
    result = {NA: "foo", hash(NA): "bar"}

    assert result[NA] == "foo"
    assert result[hash(NA)] == "bar"


def test_integer_hash_collision_set():
    # GH 30013
    result = {NA, hash(NA)}

    assert len(result) == 2
    assert NA in result
    assert hash(NA) in result


def test_pickle_roundtrip():
    # https://github.com/pandas-dev/pandas/issues/31847
    result = pickle.loads(pickle.dumps(NA))
    assert result is NA


def test_pickle_roundtrip_pandas():
    result = tm.round_trip_pickle(NA)
    assert result is NA


@pytest.mark.parametrize(
    "values, dtype", [([1, 2, NA], "Int64"), (["A", "B", NA], "string")]
)
@pytest.mark.parametrize("as_frame", [True, False])
def test_pickle_roundtrip_containers(as_frame, values, dtype):
    s = pd.Series(pd.array(values, dtype=dtype))
    if as_frame:
        s = s.to_frame(name="A")
    result = tm.round_trip_pickle(s)
    tm.assert_equal(result, s)
