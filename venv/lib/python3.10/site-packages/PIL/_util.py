from __future__ import annotations

import os
from typing import Any, NoReturn

from ._typing import StrOrBytesPath, TypeGuard


def is_path(f: Any) -> TypeGuard[StrOrBytesPath]:
    return isinstance(f, (bytes, str, os.PathLike))


class DeferredError:
    def __init__(self, ex: BaseException):
        self.ex = ex

    def __getattr__(self, elt: str) -> NoReturn:
        raise self.ex

    @staticmethod
    def new(ex: BaseException) -> Any:
        """
        Creates an object that raises the wrapped exception ``ex`` when used,
        and casts it to :py:obj:`~typing.Any` type.
        """
        return DeferredError(ex)
