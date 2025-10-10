from typing import Any, Literal, overload

from numpy.typing import ArrayLike
import numpy as np

from matplotlib.axes import Axes
from matplotlib.backend_bases import RendererBase
from matplotlib.figure import Figure
from matplotlib.transforms import Bbox

class GridSpecBase:
    def __init__(
        self,
        nrows: int,
        ncols: int,
        height_ratios: ArrayLike | None = ...,
        width_ratios: ArrayLike | None = ...,
    ) -> None: ...
    @property
    def nrows(self) -> int: ...
    @property
    def ncols(self) -> int: ...
    def get_geometry(self) -> tuple[int, int]: ...
    def get_subplot_params(self, figure: Figure | None = ...) -> SubplotParams: ...
    def new_subplotspec(
        self, loc: tuple[int, int], rowspan: int = ..., colspan: int = ...
    ) -> SubplotSpec: ...
    def set_width_ratios(self, width_ratios: ArrayLike | None) -> None: ...
    def get_width_ratios(self) -> ArrayLike: ...
    def set_height_ratios(self, height_ratios: ArrayLike | None) -> None: ...
    def get_height_ratios(self) -> ArrayLike: ...
    def get_grid_positions(
        self, fig: Figure
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]: ...
    @staticmethod
    def _check_gridspec_exists(figure: Figure, nrows: int, ncols: int) -> GridSpec: ...
    def __getitem__(
        self, key: tuple[int | slice, int | slice] | slice | int
    ) -> SubplotSpec: ...
    @overload
    def subplots(
        self,
        *,
        sharex: bool | Literal["all", "row", "col", "none"] = ...,
        sharey: bool | Literal["all", "row", "col", "none"] = ...,
        squeeze: Literal[False],
        subplot_kw: dict[str, Any] | None = ...
    ) -> np.ndarray: ...
    @overload
    def subplots(
        self,
        *,
        sharex: bool | Literal["all", "row", "col", "none"] = ...,
        sharey: bool | Literal["all", "row", "col", "none"] = ...,
        squeeze: Literal[True] = ...,
        subplot_kw: dict[str, Any] | None = ...
    ) -> np.ndarray | Axes: ...

class GridSpec(GridSpecBase):
    left: float | None
    bottom: float | None
    right: float | None
    top: float | None
    wspace: float | None
    hspace: float | None
    figure: Figure | None
    def __init__(
        self,
        nrows: int,
        ncols: int,
        figure: Figure | None = ...,
        left: float | None = ...,
        bottom: float | None = ...,
        right: float | None = ...,
        top: float | None = ...,
        wspace: float | None = ...,
        hspace: float | None = ...,
        width_ratios: ArrayLike | None = ...,
        height_ratios: ArrayLike | None = ...,
    ) -> None: ...
    def update(self, **kwargs: float | None) -> None: ...
    def locally_modified_subplot_params(self) -> list[str]: ...
    def tight_layout(
        self,
        figure: Figure,
        renderer: RendererBase | None = ...,
        pad: float = ...,
        h_pad: float | None = ...,
        w_pad: float | None = ...,
        rect: tuple[float, float, float, float] | None = ...,
    ) -> None: ...

class GridSpecFromSubplotSpec(GridSpecBase):
    figure: Figure | None
    def __init__(
        self,
        nrows: int,
        ncols: int,
        subplot_spec: SubplotSpec,
        wspace: float | None = ...,
        hspace: float | None = ...,
        height_ratios: ArrayLike | None = ...,
        width_ratios: ArrayLike | None = ...,
    ) -> None: ...
    def get_topmost_subplotspec(self) -> SubplotSpec: ...

class SubplotSpec:
    num1: int
    def __init__(
        self, gridspec: GridSpecBase, num1: int, num2: int | None = ...
    ) -> None: ...
    @staticmethod
    def _from_subplot_args(figure, args): ...
    @property
    def num2(self) -> int: ...
    @num2.setter
    def num2(self, value: int) -> None: ...
    def get_gridspec(self) -> GridSpecBase: ...
    def get_geometry(self) -> tuple[int, int, int, int]: ...
    @property
    def rowspan(self) -> range: ...
    @property
    def colspan(self) -> range: ...
    def is_first_row(self) -> bool: ...
    def is_last_row(self) -> bool: ...
    def is_first_col(self) -> bool: ...
    def is_last_col(self) -> bool: ...
    def get_position(self, figure: Figure) -> Bbox: ...
    def get_topmost_subplotspec(self) -> SubplotSpec: ...
    def __eq__(self, other: object) -> bool: ...
    def __hash__(self) -> int: ...
    def subgridspec(
        self, nrows: int, ncols: int, **kwargs
    ) -> GridSpecFromSubplotSpec: ...

class SubplotParams:
    def __init__(
        self,
        left: float | None = ...,
        bottom: float | None = ...,
        right: float | None = ...,
        top: float | None = ...,
        wspace: float | None = ...,
        hspace: float | None = ...,
    ) -> None: ...
    left: float
    right: float
    bottom: float
    top: float
    wspace: float
    hspace: float
    def update(
        self,
        left: float | None = ...,
        bottom: float | None = ...,
        right: float | None = ...,
        top: float | None = ...,
        wspace: float | None = ...,
        hspace: float | None = ...,
    ) -> None: ...
