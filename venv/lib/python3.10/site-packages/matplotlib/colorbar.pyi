import matplotlib.spines as mspines
from matplotlib import cm, collections, colors, contour, colorizer
from matplotlib.axes import Axes
from matplotlib.axis import Axis
from matplotlib.backend_bases import RendererBase
from matplotlib.patches import Patch
from matplotlib.ticker import Locator, Formatter
from matplotlib.transforms import Bbox

import numpy as np
from numpy.typing import ArrayLike
from collections.abc import Sequence
from typing import Any, Literal, overload
from .typing import ColorType

class _ColorbarSpine(mspines.Spines):
    def __init__(self, axes: Axes): ...
    def get_window_extent(self, renderer: RendererBase | None = ...) -> Bbox:...
    def set_xy(self, xy: ArrayLike) -> None: ...
    def draw(self, renderer: RendererBase | None) -> None:...


class Colorbar:
    n_rasterize: int
    mappable: cm.ScalarMappable | colorizer.ColorizingArtist
    ax: Axes
    alpha: float | None
    cmap: colors.Colormap
    norm: colors.Normalize
    values: Sequence[float] | None
    boundaries: Sequence[float] | None
    extend: Literal["neither", "both", "min", "max"]
    spacing: Literal["uniform", "proportional"]
    orientation: Literal["vertical", "horizontal"]
    drawedges: bool
    extendfrac: Literal["auto"] | float | Sequence[float] | None
    extendrect: bool
    solids: None | collections.QuadMesh
    solids_patches: list[Patch]
    lines: list[collections.LineCollection]
    outline: _ColorbarSpine
    dividers: collections.LineCollection
    ticklocation: Literal["left", "right", "top", "bottom"]
    def __init__(
        self,
        ax: Axes,
        mappable: cm.ScalarMappable | colorizer.ColorizingArtist | None = ...,
        *,
        cmap: str | colors.Colormap | None = ...,
        norm: colors.Normalize | None = ...,
        alpha: float | None = ...,
        values: Sequence[float] | None = ...,
        boundaries: Sequence[float] | None = ...,
        orientation: Literal["vertical", "horizontal"] | None = ...,
        ticklocation: Literal["auto", "left", "right", "top", "bottom"] = ...,
        extend: Literal["neither", "both", "min", "max"] | None = ...,
        spacing: Literal["uniform", "proportional"] = ...,
        ticks: Sequence[float] | Locator | None = ...,
        format: str | Formatter | None = ...,
        drawedges: bool = ...,
        extendfrac: Literal["auto"] | float | Sequence[float] | None = ...,
        extendrect: bool = ...,
        label: str = ...,
        location: Literal["left", "right", "top", "bottom"] | None = ...
    ) -> None: ...
    @property
    def long_axis(self) -> Axis: ...
    @property
    def locator(self) -> Locator: ...
    @locator.setter
    def locator(self, loc: Locator) -> None: ...
    @property
    def minorlocator(self) -> Locator: ...
    @minorlocator.setter
    def minorlocator(self, loc: Locator) -> None: ...
    @property
    def formatter(self) -> Formatter: ...
    @formatter.setter
    def formatter(self, fmt: Formatter) -> None: ...
    @property
    def minorformatter(self) -> Formatter: ...
    @minorformatter.setter
    def minorformatter(self, fmt: Formatter) -> None: ...
    def update_normal(self, mappable: cm.ScalarMappable | None = ...) -> None: ...
    @overload
    def add_lines(self, CS: contour.ContourSet, erase: bool = ...) -> None: ...
    @overload
    def add_lines(
        self,
        levels: ArrayLike,
        colors: ColorType | Sequence[ColorType],
        linewidths: float | ArrayLike,
        erase: bool = ...,
    ) -> None: ...
    def update_ticks(self) -> None: ...
    def set_ticks(
        self,
        ticks: Sequence[float] | Locator,
        *,
        labels: Sequence[str] | None = ...,
        minor: bool = ...,
        **kwargs
    ) -> None: ...
    def get_ticks(self, minor: bool = ...) -> np.ndarray: ...
    def set_ticklabels(
        self,
        ticklabels: Sequence[str],
        *,
        minor: bool = ...,
        **kwargs
    ) -> None: ...
    def minorticks_on(self) -> None: ...
    def minorticks_off(self) -> None: ...
    def set_label(self, label: str, *, loc: str | None = ..., **kwargs) -> None: ...
    def set_alpha(self, alpha: float | np.ndarray) -> None: ...
    def remove(self) -> None: ...
    def drag_pan(self, button: Any, key: Any, x: float, y: float) -> None: ...

ColorbarBase = Colorbar

def make_axes(
    parents: Axes | list[Axes] | np.ndarray,
    location: Literal["left", "right", "top", "bottom"] | None = ...,
    orientation: Literal["vertical", "horizontal"] | None = ...,
    fraction: float = ...,
    shrink: float = ...,
    aspect: float = ...,
    **kwargs
) -> tuple[Axes, dict[str, Any]]: ...
def make_axes_gridspec(
    parent: Axes,
    *,
    location: Literal["left", "right", "top", "bottom"] | None = ...,
    orientation: Literal["vertical", "horizontal"] | None = ...,
    fraction: float = ...,
    shrink: float = ...,
    aspect: float = ...,
    **kwargs
) -> tuple[Axes, dict[str, Any]]: ...
