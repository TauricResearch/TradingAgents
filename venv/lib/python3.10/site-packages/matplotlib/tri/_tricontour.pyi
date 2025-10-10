from matplotlib.axes import Axes
from matplotlib.contour import ContourSet
from matplotlib.tri._triangulation import Triangulation

from numpy.typing import ArrayLike
from typing import overload

# TODO: more explicit args/kwargs (for all things in this module)?

class TriContourSet(ContourSet):
    def __init__(self, ax: Axes, *args, **kwargs) -> None: ...

@overload
def tricontour(
    ax: Axes,
    triangulation: Triangulation,
    z: ArrayLike,
    levels: int | ArrayLike = ...,
    **kwargs
) -> TriContourSet: ...
@overload
def tricontour(
    ax: Axes,
    x: ArrayLike,
    y: ArrayLike,
    z: ArrayLike,
    levels: int | ArrayLike = ...,
    *,
    triangles: ArrayLike = ...,
    mask: ArrayLike = ...,
    **kwargs
) -> TriContourSet: ...
@overload
def tricontourf(
    ax: Axes,
    triangulation: Triangulation,
    z: ArrayLike,
    levels: int | ArrayLike = ...,
    **kwargs
) -> TriContourSet: ...
@overload
def tricontourf(
    ax: Axes,
    x: ArrayLike,
    y: ArrayLike,
    z: ArrayLike,
    levels: int | ArrayLike = ...,
    *,
    triangles: ArrayLike = ...,
    mask: ArrayLike = ...,
    **kwargs
) -> TriContourSet: ...
