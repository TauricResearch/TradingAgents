"""This module contains miscellaneous helpers.

It is not considered part of the public ufoLib API. It does, however,
define the :py:obj:`.deprecated` decorator that is used elsewhere in
the module.
"""

from __future__ import annotations

from typing import Optional, Type, TypeVar, Union, cast
from collections.abc import Callable
import enum
import functools
import warnings

F = TypeVar("F", bound=Callable[..., object])
FormatVersion = TypeVar("FormatVersion", bound="BaseFormatVersion")
FormatVersionInput = Optional[Union[int, tuple[int, int], FormatVersion]]

numberTypes = (int, float)


def deprecated(msg: str = "") -> Callable[[F], F]:
    """Decorator factory to mark functions as deprecated with given message.

    >>> @deprecated("Enough!")
    ... def some_function():
    ...    "I just print 'hello world'."
    ...    print("hello world")
    >>> some_function()
    hello world
    >>> some_function.__doc__ == "I just print 'hello world'."
    True
    """

    def deprecated_decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            warnings.warn(
                f"{func.__name__} function is a deprecated. {msg}",
                category=DeprecationWarning,
                stacklevel=2,
            )
            return func(*args, **kwargs)

        return cast(F, wrapper)

    return deprecated_decorator


def normalizeFormatVersion(
    value: FormatVersionInput, cls: Type[FormatVersion]
) -> FormatVersion:
    # Needed for type safety of UFOFormatVersion and GLIFFormatVersion input
    if value is None:
        return cls.default()
    if isinstance(value, cls):
        return value
    if isinstance(value, int):
        return cls((value, 0))
    if isinstance(value, tuple) and len(value) == 2:
        return cls(value)
    raise ValueError(f"Unsupported format version: {value!r}")


# Base class for UFOFormatVersion and GLIFFormatVersion
class BaseFormatVersion(tuple[int, int], enum.Enum):
    value: tuple[int, int]

    def __new__(cls: Type[FormatVersion], value: tuple[int, int]) -> BaseFormatVersion:
        return super().__new__(cls, value)

    @property
    def major(self) -> int:
        return self.value[0]

    @property
    def minor(self) -> int:
        return self.value[1]

    @classmethod
    def _missing_(cls, value: object) -> BaseFormatVersion:
        # allow to initialize a version enum from a single (major) integer
        if isinstance(value, int):
            return cls((value, 0))
        # or from None to obtain the current default version
        if value is None:
            return cls.default()
        raise ValueError(f"{value!r} is not a valid {cls.__name__}")

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}"

    @classmethod
    def default(cls: Type[FormatVersion]) -> FormatVersion:
        # get the latest defined version (i.e. the max of all versions)
        return max(cls.__members__.values())

    @classmethod
    def supported_versions(cls: Type[FormatVersion]) -> frozenset[FormatVersion]:
        return frozenset(cls.__members__.values())


if __name__ == "__main__":
    import doctest

    doctest.testmod()
