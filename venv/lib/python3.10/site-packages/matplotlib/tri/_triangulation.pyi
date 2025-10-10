from matplotlib import _tri
from matplotlib.tri._trifinder import TriFinder

import numpy as np
from numpy.typing import ArrayLike
from typing import Any

class Triangulation:
    x: np.ndarray
    y: np.ndarray
    mask: np.ndarray | None
    is_delaunay: bool
    triangles: np.ndarray
    def __init__(
        self,
        x: ArrayLike,
        y: ArrayLike,
        triangles: ArrayLike | None = ...,
        mask: ArrayLike | None = ...,
    ) -> None: ...
    def calculate_plane_coefficients(self, z: ArrayLike) -> np.ndarray: ...
    @property
    def edges(self) -> np.ndarray: ...
    def get_cpp_triangulation(self) -> _tri.Triangulation: ...
    def get_masked_triangles(self) -> np.ndarray: ...
    @staticmethod
    def get_from_args_and_kwargs(
        *args, **kwargs
    ) -> tuple[Triangulation, tuple[Any, ...], dict[str, Any]]: ...
    def get_trifinder(self) -> TriFinder: ...
    @property
    def neighbors(self) -> np.ndarray: ...
    def set_mask(self, mask: None | ArrayLike) -> None: ...
