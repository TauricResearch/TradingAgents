from matplotlib.axes import Axes
from matplotlib.colors import Normalize, Colormap
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.patches import ArrowStyle
from matplotlib.transforms import Transform

from typing import Literal
from numpy.typing import ArrayLike
from .typing import ColorType

def streamplot(
    axes: Axes,
    x: ArrayLike,
    y: ArrayLike,
    u: ArrayLike,
    v: ArrayLike,
    density: float | tuple[float, float] = ...,
    linewidth: float | ArrayLike | None = ...,
    color: ColorType | ArrayLike | None = ...,
    cmap: str | Colormap | None = ...,
    norm: str | Normalize | None = ...,
    arrowsize: float = ...,
    arrowstyle: str | ArrowStyle = ...,
    minlength: float = ...,
    transform: Transform | None = ...,
    zorder: float | None = ...,
    start_points: ArrayLike | None = ...,
    maxlength: float = ...,
    integration_direction: Literal["forward", "backward", "both"] = ...,
    broken_streamlines: bool = ...,
) -> StreamplotSet: ...

class StreamplotSet:
    lines: LineCollection
    arrows: PatchCollection
    def __init__(self, lines: LineCollection, arrows: PatchCollection) -> None: ...

class DomainMap:
    grid: Grid
    mask: StreamMask
    x_grid2mask: float
    y_grid2mask: float
    x_mask2grid: float
    y_mask2grid: float
    x_data2grid: float
    y_data2grid: float
    def __init__(self, grid: Grid, mask: StreamMask) -> None: ...
    def grid2mask(self, xi: float, yi: float) -> tuple[int, int]: ...
    def mask2grid(self, xm: float, ym: float) -> tuple[float, float]: ...
    def data2grid(self, xd: float, yd: float) -> tuple[float, float]: ...
    def grid2data(self, xg: float, yg: float) -> tuple[float, float]: ...
    def start_trajectory(
        self, xg: float, yg: float, broken_streamlines: bool = ...
    ) -> None: ...
    def reset_start_point(self, xg: float, yg: float) -> None: ...
    def update_trajectory(self, xg, yg, broken_streamlines: bool = ...) -> None: ...
    def undo_trajectory(self) -> None: ...

class Grid:
    nx: int
    ny: int
    dx: float
    dy: float
    x_origin: float
    y_origin: float
    width: float
    height: float
    def __init__(self, x: ArrayLike, y: ArrayLike) -> None: ...
    @property
    def shape(self) -> tuple[int, int]: ...
    def within_grid(self, xi: float, yi: float) -> bool: ...

class StreamMask:
    nx: int
    ny: int
    shape: tuple[int, int]
    def __init__(self, density: float | tuple[float, float]) -> None: ...
    def __getitem__(self, args): ...

class InvalidIndexError(Exception): ...
class TerminateTrajectory(Exception): ...
class OutOfBounds(IndexError): ...

__all__ = ['streamplot']
