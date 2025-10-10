from matplotlib.tri._triangulation import Triangulation
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from typing import overload
from numpy.typing import ArrayLike

@overload
def triplot(
    ax: Axes, triangulation: Triangulation, *args, **kwargs
) -> tuple[Line2D, Line2D]: ...
@overload
def triplot(
    ax: Axes, x: ArrayLike, y: ArrayLike, triangles: ArrayLike = ..., *args, **kwargs
) -> tuple[Line2D, Line2D]: ...
