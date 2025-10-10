import matplotlib.artist as martist
import matplotlib.collections as mcollections
from matplotlib.axes import Axes
from matplotlib.figure import Figure, SubFigure
from matplotlib.text import Text
from matplotlib.transforms import Transform, Bbox


import numpy as np
from numpy.typing import ArrayLike
from collections.abc import Sequence
from typing import Any, Literal, overload
from matplotlib.typing import ColorType

class QuiverKey(martist.Artist):
    halign: dict[Literal["N", "S", "E", "W"], Literal["left", "center", "right"]]
    valign: dict[Literal["N", "S", "E", "W"], Literal["top", "center", "bottom"]]
    pivot: dict[Literal["N", "S", "E", "W"], Literal["middle", "tip", "tail"]]
    Q: Quiver
    X: float
    Y: float
    U: float
    angle: float
    coord: Literal["axes", "figure", "data", "inches"]
    color: ColorType | None
    label: str
    labelpos: Literal["N", "S", "E", "W"]
    labelcolor: ColorType | None
    fontproperties: dict[str, Any]
    kw: dict[str, Any]
    text: Text
    zorder: float
    def __init__(
        self,
        Q: Quiver,
        X: float,
        Y: float,
        U: float,
        label: str,
        *,
        angle: float = ...,
        coordinates: Literal["axes", "figure", "data", "inches"] = ...,
        color: ColorType | None = ...,
        labelsep: float = ...,
        labelpos: Literal["N", "S", "E", "W"] = ...,
        labelcolor: ColorType | None = ...,
        fontproperties: dict[str, Any] | None = ...,
        zorder: float | None = ...,
        **kwargs
    ) -> None: ...
    @property
    def labelsep(self) -> float: ...
    def set_figure(self, fig: Figure | SubFigure) -> None: ...

class Quiver(mcollections.PolyCollection):
    X: ArrayLike
    Y: ArrayLike
    XY: ArrayLike
    U: ArrayLike
    V: ArrayLike
    Umask: ArrayLike
    N: int
    scale: float | None
    headwidth: float
    headlength: float
    headaxislength: float
    minshaft: float
    minlength: float
    units: Literal["width", "height", "dots", "inches", "x", "y", "xy"]
    scale_units: Literal["width", "height", "dots", "inches", "x", "y", "xy"] | None
    angles: Literal["uv", "xy"] | ArrayLike
    width: float | None
    pivot: Literal["tail", "middle", "tip"]
    transform: Transform
    polykw: dict[str, Any]

    @overload
    def __init__(
        self,
        ax: Axes,
        U: ArrayLike,
        V: ArrayLike,
        C: ArrayLike = ...,
        *,
        scale: float | None = ...,
        headwidth: float = ...,
        headlength: float = ...,
        headaxislength: float = ...,
        minshaft: float = ...,
        minlength: float = ...,
        units: Literal["width", "height", "dots", "inches", "x", "y", "xy"] = ...,
        scale_units: Literal["width", "height", "dots", "inches", "x", "y", "xy"]
        | None = ...,
        angles: Literal["uv", "xy"] | ArrayLike = ...,
        width: float | None = ...,
        color: ColorType | Sequence[ColorType] = ...,
        pivot: Literal["tail", "mid", "middle", "tip"] = ...,
        **kwargs
    ) -> None: ...
    @overload
    def __init__(
        self,
        ax: Axes,
        X: ArrayLike,
        Y: ArrayLike,
        U: ArrayLike,
        V: ArrayLike,
        C: ArrayLike = ...,
        *,
        scale: float | None = ...,
        headwidth: float = ...,
        headlength: float = ...,
        headaxislength: float = ...,
        minshaft: float = ...,
        minlength: float = ...,
        units: Literal["width", "height", "dots", "inches", "x", "y", "xy"] = ...,
        scale_units: Literal["width", "height", "dots", "inches", "x", "y", "xy"]
        | None = ...,
        angles: Literal["uv", "xy"] | ArrayLike = ...,
        width: float | None = ...,
        color: ColorType | Sequence[ColorType] = ...,
        pivot: Literal["tail", "mid", "middle", "tip"] = ...,
        **kwargs
    ) -> None: ...
    def get_datalim(self, transData: Transform) -> Bbox: ...
    def set_UVC(
        self, U: ArrayLike, V: ArrayLike, C: ArrayLike | None = ...
    ) -> None: ...

class Barbs(mcollections.PolyCollection):
    sizes: dict[str, float]
    fill_empty: bool
    barb_increments: dict[str, float]
    rounding: bool
    flip: np.ndarray
    x: ArrayLike
    y: ArrayLike
    u: ArrayLike
    v: ArrayLike

    @overload
    def __init__(
        self,
        ax: Axes,
        U: ArrayLike,
        V: ArrayLike,
        C: ArrayLike = ...,
        *,
        pivot: str = ...,
        length: int = ...,
        barbcolor: ColorType | Sequence[ColorType] | None = ...,
        flagcolor: ColorType | Sequence[ColorType] | None = ...,
        sizes: dict[str, float] | None = ...,
        fill_empty: bool = ...,
        barb_increments: dict[str, float] | None = ...,
        rounding: bool = ...,
        flip_barb: bool | ArrayLike = ...,
        **kwargs
    ) -> None: ...
    @overload
    def __init__(
        self,
        ax: Axes,
        X: ArrayLike,
        Y: ArrayLike,
        U: ArrayLike,
        V: ArrayLike,
        C: ArrayLike = ...,
        *,
        pivot: str = ...,
        length: int = ...,
        barbcolor: ColorType | Sequence[ColorType] | None = ...,
        flagcolor: ColorType | Sequence[ColorType] | None = ...,
        sizes: dict[str, float] | None = ...,
        fill_empty: bool = ...,
        barb_increments: dict[str, float] | None = ...,
        rounding: bool = ...,
        flip_barb: bool | ArrayLike = ...,
        **kwargs
    ) -> None: ...
    def set_UVC(
        self, U: ArrayLike, V: ArrayLike, C: ArrayLike | None = ...
    ) -> None: ...
    def set_offsets(self, xy: ArrayLike) -> None: ...
