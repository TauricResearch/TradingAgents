from collections.abc import Generator
import contextlib

from matplotlib import RcParams
from matplotlib.typing import RcStyleType

USER_LIBRARY_PATHS: list[str] = ...
STYLE_EXTENSION: str = ...

def use(style: RcStyleType) -> None: ...
@contextlib.contextmanager
def context(
    style: RcStyleType, after_reset: bool = ...
) -> Generator[None, None, None]: ...

library: dict[str, RcParams]
available: list[str]

def reload_library() -> None: ...

__all__ = ['use', 'context', 'available', 'library', 'reload_library']
