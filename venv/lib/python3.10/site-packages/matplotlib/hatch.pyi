from matplotlib.path import Path

import numpy as np
from numpy.typing import ArrayLike

class HatchPatternBase: ...

class HorizontalHatch(HatchPatternBase):
    num_lines: int
    num_vertices: int
    def __init__(self, hatch: str, density: int) -> None: ...
    def set_vertices_and_codes(self, vertices: ArrayLike, codes: ArrayLike) -> None: ...

class VerticalHatch(HatchPatternBase):
    num_lines: int
    num_vertices: int
    def __init__(self, hatch: str, density: int) -> None: ...
    def set_vertices_and_codes(self, vertices: ArrayLike, codes: ArrayLike) -> None: ...

class NorthEastHatch(HatchPatternBase):
    num_lines: int
    num_vertices: int
    def __init__(self, hatch: str, density: int) -> None: ...
    def set_vertices_and_codes(self, vertices: ArrayLike, codes: ArrayLike) -> None: ...

class SouthEastHatch(HatchPatternBase):
    num_lines: int
    num_vertices: int
    def __init__(self, hatch: str, density: int) -> None: ...
    def set_vertices_and_codes(self, vertices: ArrayLike, codes: ArrayLike) -> None: ...

class Shapes(HatchPatternBase):
    filled: bool
    num_shapes: int
    num_vertices: int
    def __init__(self, hatch: str, density: int) -> None: ...
    def set_vertices_and_codes(self, vertices: ArrayLike, codes: ArrayLike) -> None: ...

class Circles(Shapes):
    shape_vertices: np.ndarray
    shape_codes: np.ndarray
    def __init__(self, hatch: str, density: int) -> None: ...

class SmallCircles(Circles):
    size: float
    num_rows: int
    def __init__(self, hatch: str, density: int) -> None: ...

class LargeCircles(Circles):
    size: float
    num_rows: int
    def __init__(self, hatch: str, density: int) -> None: ...

class SmallFilledCircles(Circles):
    size: float
    filled: bool
    num_rows: int
    def __init__(self, hatch: str, density: int) -> None: ...

class Stars(Shapes):
    size: float
    filled: bool
    num_rows: int
    shape_vertices: np.ndarray
    shape_codes: np.ndarray
    def __init__(self, hatch: str, density: int) -> None: ...

def get_path(hatchpattern: str, density: int = ...) -> Path: ...
