from textwrap import dedent

import pytest

from pandas.util._decorators import deprecate

import pandas._testing as tm


def new_func():
    """
    This is the summary. The deprecate directive goes next.

    This is the extended summary. The deprecate directive goes before this.
    """
    return "new_func called"


def new_func_no_docstring():
    return "new_func_no_docstring called"


def new_func_wrong_docstring():
    """Summary should be in the next line."""
    return "new_func_wrong_docstring called"


def new_func_with_deprecation():
    """
    This is the summary. The deprecate directive goes next.

    .. deprecated:: 1.0
        Use new_func instead.

    This is the extended summary. The deprecate directive goes before this.
    """


def test_deprecate_ok():
    depr_func = deprecate("depr_func", new_func, "1.0", msg="Use new_func instead.")

    with tm.assert_produces_warning(FutureWarning):
        result = depr_func()

    assert result == "new_func called"
    assert depr_func.__doc__ == dedent(new_func_with_deprecation.__doc__)


def test_deprecate_no_docstring():
    depr_func = deprecate(
        "depr_func", new_func_no_docstring, "1.0", msg="Use new_func instead."
    )
    with tm.assert_produces_warning(FutureWarning):
        result = depr_func()
    assert result == "new_func_no_docstring called"


def test_deprecate_wrong_docstring():
    msg = "deprecate needs a correctly formatted docstring"
    with pytest.raises(AssertionError, match=msg):
        deprecate(
            "depr_func", new_func_wrong_docstring, "1.0", msg="Use new_func instead."
        )
