__all__ = [
    "__bibtex__",
    "__version__",
    "__version_info__",
    "set_loglevel",
    "ExecutableNotFoundError",
    "get_configdir",
    "get_cachedir",
    "get_data_path",
    "matplotlib_fname",
    "MatplotlibDeprecationWarning",
    "RcParams",
    "rc_params",
    "rc_params_from_file",
    "rcParamsDefault",
    "rcParams",
    "rcParamsOrig",
    "defaultParams",
    "rc",
    "rcdefaults",
    "rc_file_defaults",
    "rc_file",
    "rc_context",
    "use",
    "get_backend",
    "interactive",
    "is_interactive",
    "colormaps",
    "color_sequences",
]

import os
from pathlib import Path

from collections.abc import Callable, Generator
import contextlib
from packaging.version import Version

from matplotlib._api import MatplotlibDeprecationWarning
from typing import Any, Literal, NamedTuple, overload

class _VersionInfo(NamedTuple):
    major: int
    minor: int
    micro: int
    releaselevel: str
    serial: int

__bibtex__: str
__version__: str
__version_info__: _VersionInfo

def set_loglevel(level: str) -> None: ...

class _ExecInfo(NamedTuple):
    executable: str
    raw_version: str
    version: Version

class ExecutableNotFoundError(FileNotFoundError): ...

def _get_executable_info(name: str) -> _ExecInfo: ...
def get_configdir() -> str: ...
def get_cachedir() -> str: ...
def get_data_path() -> str: ...
def matplotlib_fname() -> str: ...

class RcParams(dict[str, Any]):
    validate: dict[str, Callable]
    def __init__(self, *args, **kwargs) -> None: ...
    def _set(self, key: str, val: Any) -> None: ...
    def _get(self, key: str) -> Any: ...

    def _update_raw(self, other_params: dict | RcParams) -> None: ...

    def _ensure_has_backend(self) -> None: ...
    def __setitem__(self, key: str, val: Any) -> None: ...
    def __getitem__(self, key: str) -> Any: ...
    def __iter__(self) -> Generator[str, None, None]: ...
    def __len__(self) -> int: ...
    def find_all(self, pattern: str) -> RcParams: ...
    def copy(self) -> RcParams: ...

def rc_params(fail_on_error: bool = ...) -> RcParams: ...
def rc_params_from_file(
    fname: str | Path | os.PathLike,
    fail_on_error: bool = ...,
    use_default_template: bool = ...,
) -> RcParams: ...

rcParamsDefault: RcParams
rcParams: RcParams
rcParamsOrig: RcParams
defaultParams: dict[str, Any]

def rc(group: str, **kwargs) -> None: ...
def rcdefaults() -> None: ...
def rc_file_defaults() -> None: ...
def rc_file(
    fname: str | Path | os.PathLike, *, use_default_template: bool = ...
) -> None: ...
@contextlib.contextmanager
def rc_context(
    rc: dict[str, Any] | None = ..., fname: str | Path | os.PathLike | None = ...
) -> Generator[None, None, None]: ...
def use(backend: str, *, force: bool = ...) -> None: ...
@overload
def get_backend(*, auto_select: Literal[True] = True) -> str: ...
@overload
def get_backend(*, auto_select: Literal[False]) -> str | None: ...
def interactive(b: bool) -> None: ...
def is_interactive() -> bool: ...

def _preprocess_data(
    func: Callable | None = ...,
    *,
    replace_names: list[str] | None = ...,
    label_namer: str | None = ...
) -> Callable: ...

from matplotlib.cm import _colormaps as colormaps  # noqa: E402
from matplotlib.cm import _multivar_colormaps as multivar_colormaps  # noqa: E402
from matplotlib.cm import _bivar_colormaps as bivar_colormaps  # noqa: E402
from matplotlib.colors import _color_sequences as color_sequences  # noqa: E402
