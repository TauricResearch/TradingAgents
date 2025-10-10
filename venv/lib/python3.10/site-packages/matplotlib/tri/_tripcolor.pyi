from matplotlib.axes import Axes
from matplotlib.collections import PolyCollection, TriMesh
from matplotlib.colors import Normalize, Colormap
from matplotlib.tri._triangulation import Triangulation

from numpy.typing import ArrayLike

from typing import overload, Literal

@overload
def tripcolor(
    ax: Axes,
    triangulation: Triangulation,
    c: ArrayLike = ...,
    *,
    alpha: float = ...,
    norm: str | Normalize | None = ...,
    cmap: str | Colormap | None = ...,
    vmin: float | None = ...,
    vmax: float | None = ...,
    shading: Literal["flat"] = ...,
    facecolors: ArrayLike | None = ...,
    **kwargs
) -> PolyCollection: ...
@overload
def tripcolor(
    ax: Axes,
    x: ArrayLike,
    y: ArrayLike,
    c: ArrayLike = ...,
    *,
    alpha: float = ...,
    norm: str | Normalize | None = ...,
    cmap: str | Colormap | None = ...,
    vmin: float | None = ...,
    vmax: float | None = ...,
    shading: Literal["flat"] = ...,
    facecolors: ArrayLike | None = ...,
    **kwargs
) -> PolyCollection: ...
@overload
def tripcolor(
    ax: Axes,
    triangulation: Triangulation,
    c: ArrayLike = ...,
    *,
    alpha: float = ...,
    norm: str | Normalize | None = ...,
    cmap: str | Colormap | None = ...,
    vmin: float | None = ...,
    vmax: float | None = ...,
    shading: Literal["gouraud"],
    facecolors: ArrayLike | None = ...,
    **kwargs
) -> TriMesh: ...
@overload
def tripcolor(
    ax: Axes,
    x: ArrayLike,
    y: ArrayLike,
    c: ArrayLike = ...,
    *,
    alpha: float = ...,
    norm: str | Normalize | None = ...,
    cmap: str | Colormap | None = ...,
    vmin: float | None = ...,
    vmax: float | None = ...,
    shading: Literal["gouraud"],
    facecolors: ArrayLike | None = ...,
    **kwargs
) -> TriMesh: ...
