from collections.abc import Callable
import subprocess
from typing import Any, IO, Literal, overload

def set_font_settings_for_testing() -> None: ...
def set_reproducibility_for_testing() -> None: ...
def setup() -> None: ...
@overload
def subprocess_run_for_testing(
    command: list[str],
    env: dict[str, str] | None = ...,
    timeout: float | None = ...,
    stdout: int | IO[Any] | None = ...,
    stderr: int | IO[Any] | None = ...,
    check: bool = ...,
    *,
    text: Literal[True],
    capture_output: bool = ...,
) -> subprocess.CompletedProcess[str]: ...
@overload
def subprocess_run_for_testing(
    command: list[str],
    env: dict[str, str] | None = ...,
    timeout: float | None = ...,
    stdout: int | IO[Any] | None = ...,
    stderr: int | IO[Any] | None = ...,
    check: bool = ...,
    text: Literal[False] = ...,
    capture_output: bool = ...,
) -> subprocess.CompletedProcess[bytes]: ...
@overload
def subprocess_run_for_testing(
    command: list[str],
    env: dict[str, str] | None = ...,
    timeout: float | None = ...,
    stdout: int | IO[Any] | None = ...,
    stderr: int | IO[Any] | None = ...,
    check: bool = ...,
    text: bool = ...,
    capture_output: bool = ...,
) -> subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]: ...
def subprocess_run_helper(
    func: Callable[[], None],
    *args: Any,
    timeout: float,
    extra_env: dict[str, str] | None = ...,
) -> subprocess.CompletedProcess[str]: ...
def _check_for_pgf(texsystem: str) -> bool: ...
def _has_tex_package(package: str) -> bool: ...
def ipython_in_subprocess(
    requested_backend_or_gui_framework: str,
    all_expected_backends: dict[tuple[int, int], str],
) -> None: ...
def is_ci_environment() -> bool: ...
