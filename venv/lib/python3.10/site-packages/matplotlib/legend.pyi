from matplotlib.axes import Axes
from matplotlib.artist import Artist
from matplotlib.backend_bases import MouseEvent
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.legend_handler import HandlerBase
from matplotlib.lines import Line2D
from matplotlib.offsetbox import (
    DraggableOffsetBox,
)
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle
from matplotlib.text import Text
from matplotlib.transforms import (
    BboxBase,
    Transform,
)


import pathlib
from collections.abc import Iterable
from typing import Any, Literal, overload
from .typing import ColorType

class DraggableLegend(DraggableOffsetBox):
    legend: Legend
    def __init__(
        self, legend: Legend, use_blit: bool = ..., update: Literal["loc", "bbox"] = ...
    ) -> None: ...
    def finalize_offset(self) -> None: ...

class Legend(Artist):
    codes: dict[str, int]
    zorder: float
    prop: FontProperties
    texts: list[Text]
    legend_handles: list[Artist | None]
    numpoints: int
    markerscale: float
    scatterpoints: int
    borderpad: float
    labelspacing: float
    handlelength: float
    handleheight: float
    handletextpad: float
    borderaxespad: float
    columnspacing: float
    shadow: bool
    isaxes: bool
    axes: Axes
    parent: Axes | Figure
    legendPatch: FancyBboxPatch
    def __init__(
        self,
        parent: Axes | Figure,
        handles: Iterable[Artist | tuple[Artist, ...]],
        labels: Iterable[str],
        *,
        loc: str | tuple[float, float] | int | None = ...,
        numpoints: int | None = ...,
        markerscale: float | None = ...,
        markerfirst: bool = ...,
        reverse: bool = ...,
        scatterpoints: int | None = ...,
        scatteryoffsets: Iterable[float] | None = ...,
        prop: FontProperties | dict[str, Any] | None = ...,
        fontsize: float | str | None = ...,
        labelcolor: ColorType
        | Iterable[ColorType]
        | Literal["linecolor", "markerfacecolor", "mfc", "markeredgecolor", "mec"]
        | None = ...,
        borderpad: float | None = ...,
        labelspacing: float | None = ...,
        handlelength: float | None = ...,
        handleheight: float | None = ...,
        handletextpad: float | None = ...,
        borderaxespad: float | None = ...,
        columnspacing: float | None = ...,
        ncols: int = ...,
        mode: Literal["expand"] | None = ...,
        fancybox: bool | None = ...,
        shadow: bool | dict[str, Any] | None = ...,
        title: str | None = ...,
        title_fontsize: float | None = ...,
        framealpha: float | None = ...,
        edgecolor: Literal["inherit"] | ColorType | None = ...,
        facecolor: Literal["inherit"] | ColorType | None = ...,
        bbox_to_anchor: BboxBase
        | tuple[float, float]
        | tuple[float, float, float, float]
        | None = ...,
        bbox_transform: Transform | None = ...,
        frameon: bool | None = ...,
        handler_map: dict[Artist | type, HandlerBase] | None = ...,
        title_fontproperties: FontProperties | dict[str, Any] | None = ...,
        alignment: Literal["center", "left", "right"] = ...,
        ncol: int = ...,
        draggable: bool = ...
    ) -> None: ...
    def contains(self, mouseevent: MouseEvent) -> tuple[bool, dict[Any, Any]]: ...
    def set_ncols(self, ncols: int) -> None: ...
    @classmethod
    def get_default_handler_map(cls) -> dict[type, HandlerBase]: ...
    @classmethod
    def set_default_handler_map(cls, handler_map: dict[type, HandlerBase]) -> None: ...
    @classmethod
    def update_default_handler_map(
        cls, handler_map: dict[type, HandlerBase]
    ) -> None: ...
    def get_legend_handler_map(self) -> dict[type, HandlerBase]: ...
    @staticmethod
    def get_legend_handler(
        legend_handler_map: dict[type, HandlerBase], orig_handle: Any
    ) -> HandlerBase | None: ...
    def get_children(self) -> list[Artist]: ...
    def get_frame(self) -> Rectangle: ...
    def get_lines(self) -> list[Line2D]: ...
    def get_patches(self) -> list[Patch]: ...
    def get_texts(self) -> list[Text]: ...
    def set_alignment(self, alignment: Literal["center", "left", "right"]) -> None: ...
    def get_alignment(self) -> Literal["center", "left", "right"]: ...
    def set_loc(self, loc: str | tuple[float, float] | int | None = ...) -> None: ...
    def set_title(
        self, title: str, prop: FontProperties | str | pathlib.Path | None = ...
    ) -> None: ...
    def get_title(self) -> Text: ...
    def get_frame_on(self) -> bool: ...
    def set_frame_on(self, b: bool) -> None: ...
    draw_frame = set_frame_on
    def get_bbox_to_anchor(self) -> BboxBase: ...
    def set_bbox_to_anchor(
        self,
        bbox: BboxBase
        | tuple[float, float]
        | tuple[float, float, float, float]
        | None,
        transform: Transform | None = ...
    ) -> None: ...
    @overload
    def set_draggable(
        self,
        state: Literal[True],
        use_blit: bool = ...,
        update: Literal["loc", "bbox"] = ...,
    ) -> DraggableLegend: ...
    @overload
    def set_draggable(
        self,
        state: Literal[False],
        use_blit: bool = ...,
        update: Literal["loc", "bbox"] = ...,
    ) -> None: ...
    def get_draggable(self) -> bool: ...
