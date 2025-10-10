from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from typing import Any, Protocol, TypeVar, Union

TYPE_CHECKING = False
if TYPE_CHECKING:
    from numbers import _IntegralLike as IntegralLike

    try:
        import numpy.typing as npt

        NumpyArray = npt.NDArray[Any]  # requires numpy>=1.21
    except (ImportError, AttributeError):
        pass

if sys.version_info >= (3, 13):
    from types import CapsuleType
else:
    CapsuleType = object

if sys.version_info >= (3, 12):
    from collections.abc import Buffer
else:
    Buffer = Any

if sys.version_info >= (3, 10):
    from typing import TypeGuard
else:
    try:
        from typing_extensions import TypeGuard
    except ImportError:

        class TypeGuard:  # type: ignore[no-redef]
            def __class_getitem__(cls, item: Any) -> type[bool]:
                return bool


Coords = Union[Sequence[float], Sequence[Sequence[float]]]


_T_co = TypeVar("_T_co", covariant=True)


class SupportsRead(Protocol[_T_co]):
    def read(self, length: int = ..., /) -> _T_co: ...


StrOrBytesPath = Union[str, bytes, os.PathLike[str], os.PathLike[bytes]]


__all__ = ["Buffer", "IntegralLike", "StrOrBytesPath", "SupportsRead", "TypeGuard"]
