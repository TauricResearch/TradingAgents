import pytest

from pandas.util._validators import (
    validate_bool_kwarg,
    validate_kwargs,
)


@pytest.fixture
def _fname():
    return "func"


def test_bad_kwarg(_fname):
    good_arg = "f"
    bad_arg = good_arg + "o"

    compat_args = {good_arg: "foo", bad_arg + "o": "bar"}
    kwargs = {good_arg: "foo", bad_arg: "bar"}

    msg = rf"{_fname}\(\) got an unexpected keyword argument '{bad_arg}'"

    with pytest.raises(TypeError, match=msg):
        validate_kwargs(_fname, kwargs, compat_args)


@pytest.mark.parametrize("i", range(1, 3))
def test_not_all_none(i, _fname):
    bad_arg = "foo"
    msg = (
        rf"the '{bad_arg}' parameter is not supported "
        rf"in the pandas implementation of {_fname}\(\)"
    )

    compat_args = {"foo": 1, "bar": "s", "baz": None}

    kwarg_keys = ("foo", "bar", "baz")
    kwarg_vals = (2, "s", None)

    kwargs = dict(zip(kwarg_keys[:i], kwarg_vals[:i]))

    with pytest.raises(ValueError, match=msg):
        validate_kwargs(_fname, kwargs, compat_args)


def test_validation(_fname):
    # No exceptions should be raised.
    compat_args = {"f": None, "b": 1, "ba": "s"}

    kwargs = {"f": None, "b": 1}
    validate_kwargs(_fname, kwargs, compat_args)


@pytest.mark.parametrize("name", ["inplace", "copy"])
@pytest.mark.parametrize("value", [1, "True", [1, 2, 3], 5.0])
def test_validate_bool_kwarg_fail(name, value):
    msg = (
        f'For argument "{name}" expected type bool, '
        f"received type {type(value).__name__}"
    )

    with pytest.raises(ValueError, match=msg):
        validate_bool_kwarg(value, name)


@pytest.mark.parametrize("name", ["inplace", "copy"])
@pytest.mark.parametrize("value", [True, False, None])
def test_validate_bool_kwarg(name, value):
    assert validate_bool_kwarg(value, name) == value
