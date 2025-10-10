import pytest

from pandas.util._validators import validate_args


@pytest.fixture
def _fname():
    return "func"


def test_bad_min_fname_arg_count(_fname):
    msg = "'max_fname_arg_count' must be non-negative"

    with pytest.raises(ValueError, match=msg):
        validate_args(_fname, (None,), -1, "foo")


def test_bad_arg_length_max_value_single(_fname):
    args = (None, None)
    compat_args = ("foo",)

    min_fname_arg_count = 0
    max_length = len(compat_args) + min_fname_arg_count
    actual_length = len(args) + min_fname_arg_count
    msg = (
        rf"{_fname}\(\) takes at most {max_length} "
        rf"argument \({actual_length} given\)"
    )

    with pytest.raises(TypeError, match=msg):
        validate_args(_fname, args, min_fname_arg_count, compat_args)


def test_bad_arg_length_max_value_multiple(_fname):
    args = (None, None)
    compat_args = {"foo": None}

    min_fname_arg_count = 2
    max_length = len(compat_args) + min_fname_arg_count
    actual_length = len(args) + min_fname_arg_count
    msg = (
        rf"{_fname}\(\) takes at most {max_length} "
        rf"arguments \({actual_length} given\)"
    )

    with pytest.raises(TypeError, match=msg):
        validate_args(_fname, args, min_fname_arg_count, compat_args)


@pytest.mark.parametrize("i", range(1, 3))
def test_not_all_defaults(i, _fname):
    bad_arg = "foo"
    msg = (
        f"the '{bad_arg}' parameter is not supported "
        rf"in the pandas implementation of {_fname}\(\)"
    )

    compat_args = {"foo": 2, "bar": -1, "baz": 3}
    arg_vals = (1, -1, 3)

    with pytest.raises(ValueError, match=msg):
        validate_args(_fname, arg_vals[:i], 2, compat_args)


def test_validation(_fname):
    # No exceptions should be raised.
    validate_args(_fname, (None,), 2, {"out": None})

    compat_args = {"axis": 1, "out": None}
    validate_args(_fname, (1, None), 2, compat_args)
