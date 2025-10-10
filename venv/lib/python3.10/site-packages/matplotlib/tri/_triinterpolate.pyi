from matplotlib.tri import Triangulation, TriFinder

from typing import Literal
import numpy as np
from numpy.typing import ArrayLike

class TriInterpolator:
    def __init__(
        self,
        triangulation: Triangulation,
        z: ArrayLike,
        trifinder: TriFinder | None = ...,
    ) -> None: ...
    # __call__ and gradient are not actually implemented by the ABC, but are specified as required
    def __call__(self, x: ArrayLike, y: ArrayLike) -> np.ma.MaskedArray: ...
    def gradient(
        self, x: ArrayLike, y: ArrayLike
    ) -> tuple[np.ma.MaskedArray, np.ma.MaskedArray]: ...

class LinearTriInterpolator(TriInterpolator): ...

class CubicTriInterpolator(TriInterpolator):
    def __init__(
        self,
        triangulation: Triangulation,
        z: ArrayLike,
        kind: Literal["min_E", "geom", "user"] = ...,
        trifinder: TriFinder | None = ...,
        dz: tuple[ArrayLike, ArrayLike] | None = ...,
    ) -> None: ...

__all__ = ('TriInterpolator', 'LinearTriInterpolator', 'CubicTriInterpolator')
