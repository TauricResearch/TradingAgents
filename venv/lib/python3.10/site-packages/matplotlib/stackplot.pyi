from matplotlib.axes import Axes
from matplotlib.collections import PolyCollection

from collections.abc import Iterable
from typing import Literal
from numpy.typing import ArrayLike
from matplotlib.typing import ColorType

def stackplot(
    axes: Axes,
    x: ArrayLike,
    *args: ArrayLike,
    labels: Iterable[str] = ...,
    colors: Iterable[ColorType] | None = ...,
    hatch: Iterable[str] | str | None = ...,
    baseline: Literal["zero", "sym", "wiggle", "weighted_wiggle"] = ...,
    **kwargs
) -> list[PolyCollection]: ...

__all__ = ['stackplot']
