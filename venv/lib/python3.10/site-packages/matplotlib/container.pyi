from matplotlib.artist import Artist
from matplotlib.lines import Line2D
from matplotlib.collections import LineCollection
from matplotlib.patches import Rectangle

from collections.abc import Callable
from typing import Any, Literal
from numpy.typing import ArrayLike

class Container(tuple):
    def __new__(cls, *args, **kwargs): ...
    def __init__(self, kl, label: Any | None = ...) -> None: ...
    def remove(self) -> None: ...
    def get_children(self) -> list[Artist]: ...
    def get_label(self) -> str | None: ...
    def set_label(self, s: Any) -> None: ...
    def add_callback(self, func: Callable[[Artist], Any]) -> int: ...
    def remove_callback(self, oid: int) -> None: ...
    def pchanged(self) -> None: ...

class BarContainer(Container):
    patches: list[Rectangle]
    errorbar: None | ErrorbarContainer
    datavalues: None | ArrayLike
    orientation: None | Literal["vertical", "horizontal"]
    def __init__(
        self,
        patches: list[Rectangle],
        errorbar: ErrorbarContainer | None = ...,
        *,
        datavalues: ArrayLike | None = ...,
        orientation: Literal["vertical", "horizontal"] | None = ...,
        **kwargs
    ) -> None: ...

class ErrorbarContainer(Container):
    lines: tuple[Line2D, tuple[Line2D, ...], tuple[LineCollection, ...]]
    has_xerr: bool
    has_yerr: bool
    def __init__(
        self,
        lines: tuple[Line2D, tuple[Line2D, ...], tuple[LineCollection, ...]],
        has_xerr: bool = ...,
        has_yerr: bool = ...,
        **kwargs
    ) -> None: ...

class StemContainer(Container):
    markerline: Line2D
    stemlines: LineCollection
    baseline: Line2D
    def __init__(
        self,
        markerline_stemlines_baseline: tuple[Line2D, LineCollection, Line2D],
        **kwargs
    ) -> None: ...
