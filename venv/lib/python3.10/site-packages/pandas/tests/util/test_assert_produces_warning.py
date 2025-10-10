""""
Test module for testing ``pandas._testing.assert_produces_warning``.
"""
import warnings

import pytest

from pandas.errors import (
    DtypeWarning,
    PerformanceWarning,
)

import pandas._testing as tm


@pytest.fixture(
    params=[
        RuntimeWarning,
        ResourceWarning,
        UserWarning,
        FutureWarning,
        DeprecationWarning,
        PerformanceWarning,
        DtypeWarning,
    ],
)
def category(request):
    """
    Return unique warning.

    Useful for testing behavior of tm.assert_produces_warning with various categories.
    """
    return request.param


@pytest.fixture(
    params=[
        (RuntimeWarning, UserWarning),
        (UserWarning, FutureWarning),
        (FutureWarning, RuntimeWarning),
        (DeprecationWarning, PerformanceWarning),
        (PerformanceWarning, FutureWarning),
        (DtypeWarning, DeprecationWarning),
        (ResourceWarning, DeprecationWarning),
        (FutureWarning, DeprecationWarning),
    ],
    ids=lambda x: type(x).__name__,
)
def pair_different_warnings(request):
    """
    Return pair or different warnings.

    Useful for testing how several different warnings are handled
    in tm.assert_produces_warning.
    """
    return request.param


def f():
    warnings.warn("f1", FutureWarning)
    warnings.warn("f2", RuntimeWarning)


@pytest.mark.filterwarnings("ignore:f1:FutureWarning")
def test_assert_produces_warning_honors_filter():
    # Raise by default.
    msg = r"Caused unexpected warning\(s\)"
    with pytest.raises(AssertionError, match=msg):
        with tm.assert_produces_warning(RuntimeWarning):
            f()

    with tm.assert_produces_warning(RuntimeWarning, raise_on_extra_warnings=False):
        f()


@pytest.mark.parametrize(
    "message, match",
    [
        ("", None),
        ("", ""),
        ("Warning message", r".*"),
        ("Warning message", "War"),
        ("Warning message", r"[Ww]arning"),
        ("Warning message", "age"),
        ("Warning message", r"age$"),
        ("Message 12-234 with numbers", r"\d{2}-\d{3}"),
        ("Message 12-234 with numbers", r"^Mes.*\d{2}-\d{3}"),
        ("Message 12-234 with numbers", r"\d{2}-\d{3}\s\S+"),
        ("Message, which we do not match", None),
    ],
)
def test_catch_warning_category_and_match(category, message, match):
    with tm.assert_produces_warning(category, match=match):
        warnings.warn(message, category)


def test_fail_to_match_runtime_warning():
    category = RuntimeWarning
    match = "Did not see this warning"
    unmatched = (
        r"Did not see warning 'RuntimeWarning' matching 'Did not see this warning'. "
        r"The emitted warning messages are "
        r"\[RuntimeWarning\('This is not a match.'\), "
        r"RuntimeWarning\('Another unmatched warning.'\)\]"
    )
    with pytest.raises(AssertionError, match=unmatched):
        with tm.assert_produces_warning(category, match=match):
            warnings.warn("This is not a match.", category)
            warnings.warn("Another unmatched warning.", category)


def test_fail_to_match_future_warning():
    category = FutureWarning
    match = "Warning"
    unmatched = (
        r"Did not see warning 'FutureWarning' matching 'Warning'. "
        r"The emitted warning messages are "
        r"\[FutureWarning\('This is not a match.'\), "
        r"FutureWarning\('Another unmatched warning.'\)\]"
    )
    with pytest.raises(AssertionError, match=unmatched):
        with tm.assert_produces_warning(category, match=match):
            warnings.warn("This is not a match.", category)
            warnings.warn("Another unmatched warning.", category)


def test_fail_to_match_resource_warning():
    category = ResourceWarning
    match = r"\d+"
    unmatched = (
        r"Did not see warning 'ResourceWarning' matching '\\d\+'. "
        r"The emitted warning messages are "
        r"\[ResourceWarning\('This is not a match.'\), "
        r"ResourceWarning\('Another unmatched warning.'\)\]"
    )
    with pytest.raises(AssertionError, match=unmatched):
        with tm.assert_produces_warning(category, match=match):
            warnings.warn("This is not a match.", category)
            warnings.warn("Another unmatched warning.", category)


def test_fail_to_catch_actual_warning(pair_different_warnings):
    expected_category, actual_category = pair_different_warnings
    match = "Did not see expected warning of class"
    with pytest.raises(AssertionError, match=match):
        with tm.assert_produces_warning(expected_category):
            warnings.warn("warning message", actual_category)


def test_ignore_extra_warning(pair_different_warnings):
    expected_category, extra_category = pair_different_warnings
    with tm.assert_produces_warning(expected_category, raise_on_extra_warnings=False):
        warnings.warn("Expected warning", expected_category)
        warnings.warn("Unexpected warning OK", extra_category)


def test_raise_on_extra_warning(pair_different_warnings):
    expected_category, extra_category = pair_different_warnings
    match = r"Caused unexpected warning\(s\)"
    with pytest.raises(AssertionError, match=match):
        with tm.assert_produces_warning(expected_category):
            warnings.warn("Expected warning", expected_category)
            warnings.warn("Unexpected warning NOT OK", extra_category)


def test_same_category_different_messages_first_match():
    category = UserWarning
    with tm.assert_produces_warning(category, match=r"^Match this"):
        warnings.warn("Match this", category)
        warnings.warn("Do not match that", category)
        warnings.warn("Do not match that either", category)


def test_same_category_different_messages_last_match():
    category = DeprecationWarning
    with tm.assert_produces_warning(category, match=r"^Match this"):
        warnings.warn("Do not match that", category)
        warnings.warn("Do not match that either", category)
        warnings.warn("Match this", category)


def test_match_multiple_warnings():
    # https://github.com/pandas-dev/pandas/issues/47829
    category = (FutureWarning, UserWarning)
    with tm.assert_produces_warning(category, match=r"^Match this"):
        warnings.warn("Match this", FutureWarning)
        warnings.warn("Match this too", UserWarning)


def test_right_category_wrong_match_raises(pair_different_warnings):
    target_category, other_category = pair_different_warnings
    with pytest.raises(AssertionError, match="Did not see warning.*matching"):
        with tm.assert_produces_warning(target_category, match=r"^Match this"):
            warnings.warn("Do not match it", target_category)
            warnings.warn("Match this", other_category)


@pytest.mark.parametrize("false_or_none", [False, None])
class TestFalseOrNoneExpectedWarning:
    def test_raise_on_warning(self, false_or_none):
        msg = r"Caused unexpected warning\(s\)"
        with pytest.raises(AssertionError, match=msg):
            with tm.assert_produces_warning(false_or_none):
                f()

    def test_no_raise_without_warning(self, false_or_none):
        with tm.assert_produces_warning(false_or_none):
            pass

    def test_no_raise_with_false_raise_on_extra(self, false_or_none):
        with tm.assert_produces_warning(false_or_none, raise_on_extra_warnings=False):
            f()


def test_raises_during_exception():
    msg = "Did not see expected warning of class 'UserWarning'"
    with pytest.raises(AssertionError, match=msg):
        with tm.assert_produces_warning(UserWarning):
            raise ValueError

    with pytest.raises(AssertionError, match=msg):
        with tm.assert_produces_warning(UserWarning):
            warnings.warn("FutureWarning", FutureWarning)
            raise IndexError

    msg = "Caused unexpected warning"
    with pytest.raises(AssertionError, match=msg):
        with tm.assert_produces_warning(None):
            warnings.warn("FutureWarning", FutureWarning)
            raise SystemError


def test_passes_during_exception():
    with pytest.raises(SyntaxError, match="Error"):
        with tm.assert_produces_warning(None):
            raise SyntaxError("Error")

    with pytest.raises(ValueError, match="Error"):
        with tm.assert_produces_warning(FutureWarning, match="FutureWarning"):
            warnings.warn("FutureWarning", FutureWarning)
            raise ValueError("Error")
