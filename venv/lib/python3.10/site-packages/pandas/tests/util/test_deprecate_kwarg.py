import pytest

from pandas.util._decorators import deprecate_kwarg

import pandas._testing as tm


@deprecate_kwarg("old", "new")
def _f1(new=False):
    return new


_f2_mappings = {"yes": True, "no": False}


@deprecate_kwarg("old", "new", _f2_mappings)
def _f2(new=False):
    return new


def _f3_mapping(x):
    return x + 1


@deprecate_kwarg("old", "new", _f3_mapping)
def _f3(new=0):
    return new


@pytest.mark.parametrize("key,klass", [("old", FutureWarning), ("new", None)])
def test_deprecate_kwarg(key, klass):
    x = 78

    with tm.assert_produces_warning(klass):
        assert _f1(**{key: x}) == x


@pytest.mark.parametrize("key", list(_f2_mappings.keys()))
def test_dict_deprecate_kwarg(key):
    with tm.assert_produces_warning(FutureWarning):
        assert _f2(old=key) == _f2_mappings[key]


@pytest.mark.parametrize("key", ["bogus", 12345, -1.23])
def test_missing_deprecate_kwarg(key):
    with tm.assert_produces_warning(FutureWarning):
        assert _f2(old=key) == key


@pytest.mark.parametrize("x", [1, -1.4, 0])
def test_callable_deprecate_kwarg(x):
    with tm.assert_produces_warning(FutureWarning):
        assert _f3(old=x) == _f3_mapping(x)


def test_callable_deprecate_kwarg_fail():
    msg = "((can only|cannot) concatenate)|(must be str)|(Can't convert)"

    with pytest.raises(TypeError, match=msg):
        _f3(old="hello")


def test_bad_deprecate_kwarg():
    msg = "mapping from old to new argument values must be dict or callable!"

    with pytest.raises(TypeError, match=msg):

        @deprecate_kwarg("old", "new", 0)
        def f4(new=None):
            return new


@deprecate_kwarg("old", None)
def _f4(old=True, unchanged=True):
    return old, unchanged


@pytest.mark.parametrize("key", ["old", "unchanged"])
def test_deprecate_keyword(key):
    x = 9

    if key == "old":
        klass = FutureWarning
        expected = (x, True)
    else:
        klass = None
        expected = (True, x)

    with tm.assert_produces_warning(klass):
        assert _f4(**{key: x}) == expected
