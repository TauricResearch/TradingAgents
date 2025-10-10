from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeVar
from typing_extensions import ParamSpec

from matplotlib.figure import Figure
from matplotlib.typing import RcStyleType

_P = ParamSpec("_P")
_R = TypeVar("_R")

def remove_ticks_and_titles(figure: Figure) -> None: ...
def image_comparison(
    baseline_images: list[str] | None,
    extensions: list[str] | None = ...,
    tol: float = ...,
    freetype_version: tuple[str, str] | str | None = ...,
    remove_text: bool = ...,
    savefig_kwarg: dict[str, Any] | None = ...,
    style: RcStyleType = ...,
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]: ...
def check_figures_equal(
    *, extensions: Sequence[str] = ..., tol: float = ...
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]: ...
def _image_directories(func: Callable) -> tuple[Path, Path]: ...
