from __future__ import annotations

from collections.abc import Callable
import re
import typing
from typing import Any, TypeVar

import numpy as np
import pytest

import matplotlib as mpl
from matplotlib import _api


if typing.TYPE_CHECKING:
    from typing_extensions import Self

T = TypeVar('T')


@pytest.mark.parametrize('target,shape_repr,test_shape',
                         [((None, ), "(N,)", (1, 3)),
                          ((None, 3), "(N, 3)", (1,)),
                          ((None, 3), "(N, 3)", (1, 2)),
                          ((1, 5), "(1, 5)", (1, 9)),
                          ((None, 2, None), "(M, 2, N)", (1, 3, 1))
                          ])
def test_check_shape(target: tuple[int | None, ...],
                     shape_repr: str,
                     test_shape: tuple[int, ...]) -> None:
    error_pattern = "^" + re.escape(
        f"'aardvark' must be {len(target)}D with shape {shape_repr}, but your input "
        f"has shape {test_shape}")
    data = np.zeros(test_shape)
    with pytest.raises(ValueError, match=error_pattern):
        _api.check_shape(target, aardvark=data)


def test_classproperty_deprecation() -> None:
    class A:
        @_api.deprecated("0.0.0")
        @_api.classproperty
        def f(cls: Self) -> None:
            pass
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        A.f
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        a = A()
        a.f


def test_warn_deprecated():
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match=r'foo was deprecated in Matplotlib 3\.10 and will be '
                            r'removed in 3\.12\.'):
        _api.warn_deprecated('3.10', name='foo')
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match=r'The foo class was deprecated in Matplotlib 3\.10 and '
                            r'will be removed in 3\.12\.'):
        _api.warn_deprecated('3.10', name='foo', obj_type='class')
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match=r'foo was deprecated in Matplotlib 3\.10 and will be '
                            r'removed in 3\.12\. Use bar instead\.'):
        _api.warn_deprecated('3.10', name='foo', alternative='bar')
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match=r'foo was deprecated in Matplotlib 3\.10 and will be '
                            r'removed in 3\.12\. More information\.'):
        _api.warn_deprecated('3.10', name='foo', addendum='More information.')
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match=r'foo was deprecated in Matplotlib 3\.10 and will be '
                            r'removed in 4\.0\.'):
        _api.warn_deprecated('3.10', name='foo', removal='4.0')
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match=r'foo was deprecated in Matplotlib 3\.10\.'):
        _api.warn_deprecated('3.10', name='foo', removal=False)
    with pytest.warns(PendingDeprecationWarning,
                      match=r'foo will be deprecated in a future version'):
        _api.warn_deprecated('3.10', name='foo', pending=True)
    with pytest.raises(ValueError, match=r'cannot have a scheduled removal'):
        _api.warn_deprecated('3.10', name='foo', pending=True, removal='3.12')
    with pytest.warns(mpl.MatplotlibDeprecationWarning, match=r'Complete replacement'):
        _api.warn_deprecated('3.10', message='Complete replacement', name='foo',
                             alternative='bar', addendum='More information.',
                             obj_type='class', removal='4.0')


def test_deprecate_privatize_attribute() -> None:
    class C:
        def __init__(self) -> None: self._attr = 1
        def _meth(self, arg: T) -> T: return arg
        attr: int = _api.deprecate_privatize_attribute("0.0")
        meth: Callable = _api.deprecate_privatize_attribute("0.0")

    c = C()
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        assert c.attr == 1
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        c.attr = 2
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        assert c.attr == 2
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        assert c.meth(42) == 42


def test_delete_parameter() -> None:
    @_api.delete_parameter("3.0", "foo")
    def func1(foo: Any = None) -> None:
        pass

    @_api.delete_parameter("3.0", "foo")
    def func2(**kwargs: Any) -> None:
        pass

    for func in [func1, func2]:  # type: ignore[list-item]
        func()  # No warning.
        with pytest.warns(mpl.MatplotlibDeprecationWarning):
            func(foo="bar")

    def pyplot_wrapper(foo: Any = _api.deprecation._deprecated_parameter) -> None:
        func1(foo)

    pyplot_wrapper()  # No warning.
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        func(foo="bar")


def test_make_keyword_only() -> None:
    @_api.make_keyword_only("3.0", "arg")
    def func(pre: Any, arg: Any, post: Any = None) -> None:
        pass

    func(1, arg=2)  # Check that no warning is emitted.

    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        func(1, 2)
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        func(1, 2, 3)


def test_deprecation_alternative() -> None:
    alternative = "`.f1`, `f2`, `f3(x) <.f3>` or `f4(x)<f4>`"
    @_api.deprecated("1", alternative=alternative)
    def f() -> None:
        pass
    if f.__doc__ is None:
        pytest.skip('Documentation is disabled')
    assert alternative in f.__doc__


def test_empty_check_in_list() -> None:
    with pytest.raises(TypeError, match="No argument to check!"):
        _api.check_in_list(["a"])
