from collections.abc import Callable
import contextlib
from typing import Any, Literal, ParamSpec, TypedDict, TypeVar, overload
from typing_extensions import (
    Unpack,  # < Py 3.11
)

_P = ParamSpec("_P")
_R = TypeVar("_R")
_T = TypeVar("_T")

class MatplotlibDeprecationWarning(DeprecationWarning): ...

class DeprecationKwargs(TypedDict, total=False):
    message: str
    alternative: str
    pending: bool
    obj_type: str
    addendum: str
    removal: str | Literal[False]

class NamedDeprecationKwargs(DeprecationKwargs, total=False):
    name: str

def warn_deprecated(since: str, **kwargs: Unpack[NamedDeprecationKwargs]) -> None: ...
def deprecated(
    since: str, **kwargs: Unpack[NamedDeprecationKwargs]
) -> Callable[[_T], _T]: ...

class deprecate_privatize_attribute(Any):
    def __init__(self, since: str, **kwargs: Unpack[NamedDeprecationKwargs]): ...
    def __set_name__(self, owner: type[object], name: str) -> None: ...

DECORATORS: dict[Callable, Callable] = ...

@overload
def rename_parameter(
    since: str, old: str, new: str, func: None = ...
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]: ...
@overload
def rename_parameter(
    since: str, old: str, new: str, func: Callable[_P, _R]
) -> Callable[_P, _R]: ...

class _deprecated_parameter_class: ...

_deprecated_parameter: _deprecated_parameter_class

@overload
def delete_parameter(
    since: str, name: str, func: None = ..., **kwargs: Unpack[DeprecationKwargs]
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]: ...
@overload
def delete_parameter(
    since: str, name: str, func: Callable[_P, _R], **kwargs: Unpack[DeprecationKwargs]
) -> Callable[_P, _R]: ...
@overload
def make_keyword_only(
    since: str, name: str, func: None = ...
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]: ...
@overload
def make_keyword_only(
    since: str, name: str, func: Callable[_P, _R]
) -> Callable[_P, _R]: ...
def deprecate_method_override(
    method: Callable[_P, _R],
    obj: object | type,
    *,
    allow_empty: bool = ...,
    since: str,
    **kwargs: Unpack[NamedDeprecationKwargs]
) -> Callable[_P, _R]: ...
def suppress_matplotlib_deprecation_warning() -> (
    contextlib.AbstractContextManager[None]
): ...
