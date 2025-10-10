import matplotlib.artist as martist
from matplotlib.backend_bases import RendererBase, Event, FigureCanvasBase
from matplotlib.colors import Colormap, Normalize
import matplotlib.text as mtext
from matplotlib.figure import Figure, SubFigure
from matplotlib.font_manager import FontProperties
from matplotlib.image import BboxImage
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.transforms import Bbox, BboxBase, Transform
from matplotlib.typing import CoordsType

import numpy as np
from numpy.typing import ArrayLike
from collections.abc import Callable, Sequence
from typing import Any, Literal, overload

DEBUG: bool

def _get_packed_offsets(
    widths: Sequence[float],
    total: float | None,
    sep: float | None,
    mode: Literal["fixed", "expand", "equal"] = ...,
) -> tuple[float, np.ndarray]: ...

class OffsetBox(martist.Artist):
    width: float | None
    height: float | None
    def __init__(self, *args, **kwargs) -> None: ...
    def set_figure(self, fig: Figure | SubFigure) -> None: ...
    def set_offset(
        self,
        xy: tuple[float, float]
        | Callable[[float, float, float, float, RendererBase], tuple[float, float]],
    ) -> None: ...

    @overload
    def get_offset(self, bbox: Bbox, renderer: RendererBase) -> tuple[float, float]: ...
    @overload
    def get_offset(
        self,
        width: float,
        height: float,
        xdescent: float,
        ydescent: float,
        renderer: RendererBase
    ) -> tuple[float, float]: ...

    def set_width(self, width: float) -> None: ...
    def set_height(self, height: float) -> None: ...
    def get_visible_children(self) -> list[martist.Artist]: ...
    def get_children(self) -> list[martist.Artist]: ...
    def get_bbox(self, renderer: RendererBase) -> Bbox: ...
    def get_window_extent(self, renderer: RendererBase | None = ...) -> Bbox: ...

class PackerBase(OffsetBox):
    height: float | None
    width: float | None
    sep: float | None
    pad: float | None
    mode: Literal["fixed", "expand", "equal"]
    align: Literal["top", "bottom", "left", "right", "center", "baseline"]
    def __init__(
        self,
        pad: float | None = ...,
        sep: float | None = ...,
        width: float | None = ...,
        height: float | None = ...,
        align: Literal["top", "bottom", "left", "right", "center", "baseline"] = ...,
        mode: Literal["fixed", "expand", "equal"] = ...,
        children: list[martist.Artist] | None = ...,
    ) -> None: ...

class VPacker(PackerBase): ...
class HPacker(PackerBase): ...

class PaddedBox(OffsetBox):
    pad: float | None
    patch: FancyBboxPatch
    def __init__(
        self,
        child: martist.Artist,
        pad: float | None = ...,
        *,
        draw_frame: bool = ...,
        patch_attrs: dict[str, Any] | None = ...,
    ) -> None: ...
    def update_frame(self, bbox: Bbox, fontsize: float | None = ...) -> None: ...
    def draw_frame(self, renderer: RendererBase) -> None: ...

class DrawingArea(OffsetBox):
    width: float
    height: float
    xdescent: float
    ydescent: float
    offset_transform: Transform
    dpi_transform: Transform
    def __init__(
        self,
        width: float,
        height: float,
        xdescent: float = ...,
        ydescent: float = ...,
        clip: bool = ...,
    ) -> None: ...
    @property
    def clip_children(self) -> bool: ...
    @clip_children.setter
    def clip_children(self, val: bool) -> None: ...
    def get_transform(self) -> Transform: ...

    # does not accept all options of superclass
    def set_offset(self, xy: tuple[float, float]) -> None: ...  # type: ignore[override]
    def get_offset(self) -> tuple[float, float]: ...  # type: ignore[override]
    def add_artist(self, a: martist.Artist) -> None: ...

class TextArea(OffsetBox):
    offset_transform: Transform
    def __init__(
        self,
        s: str,
        *,
        textprops: dict[str, Any] | None = ...,
        multilinebaseline: bool = ...,
    ) -> None: ...
    def set_text(self, s: str) -> None: ...
    def get_text(self) -> str: ...
    def set_multilinebaseline(self, t: bool) -> None: ...
    def get_multilinebaseline(self) -> bool: ...

    # does not accept all options of superclass
    def set_offset(self, xy: tuple[float, float]) -> None: ...  # type: ignore[override]
    def get_offset(self) -> tuple[float, float]: ...  # type: ignore[override]

class AuxTransformBox(OffsetBox):
    aux_transform: Transform
    offset_transform: Transform
    ref_offset_transform: Transform
    def __init__(self, aux_transform: Transform) -> None: ...
    def add_artist(self, a: martist.Artist) -> None: ...
    def get_transform(self) -> Transform: ...

    # does not accept all options of superclass
    def set_offset(self, xy: tuple[float, float]) -> None: ...  # type: ignore[override]
    def get_offset(self) -> tuple[float, float]: ...  # type: ignore[override]

class AnchoredOffsetbox(OffsetBox):
    zorder: float
    codes: dict[str, int]
    loc: int
    borderpad: float
    pad: float
    prop: FontProperties
    patch: FancyBboxPatch
    def __init__(
        self,
        loc: str,
        *,
        pad: float = ...,
        borderpad: float = ...,
        child: OffsetBox | None = ...,
        prop: FontProperties | None = ...,
        frameon: bool = ...,
        bbox_to_anchor: BboxBase
        | tuple[float, float]
        | tuple[float, float, float, float]
        | None = ...,
        bbox_transform: Transform | None = ...,
        **kwargs
    ) -> None: ...
    def set_child(self, child: OffsetBox | None) -> None: ...
    def get_child(self) -> OffsetBox | None: ...
    def get_children(self) -> list[martist.Artist]: ...
    def get_bbox_to_anchor(self) -> Bbox: ...
    def set_bbox_to_anchor(
        self, bbox: BboxBase, transform: Transform | None = ...
    ) -> None: ...
    def update_frame(self, bbox: Bbox, fontsize: float | None = ...) -> None: ...

class AnchoredText(AnchoredOffsetbox):
    txt: TextArea
    def __init__(
        self,
        s: str,
        loc: str,
        *,
        pad: float = ...,
        borderpad: float = ...,
        prop: dict[str, Any] | None = ...,
        **kwargs
    ) -> None: ...

class OffsetImage(OffsetBox):
    image: BboxImage
    def __init__(
        self,
        arr: ArrayLike,
        *,
        zoom: float = ...,
        cmap: Colormap | str | None = ...,
        norm: Normalize | str | None = ...,
        interpolation: str | None = ...,
        origin: Literal["upper", "lower"] | None = ...,
        filternorm: bool = ...,
        filterrad: float = ...,
        resample: bool = ...,
        dpi_cor: bool = ...,
        **kwargs
    ) -> None: ...
    stale: bool
    def set_data(self, arr: ArrayLike | None) -> None: ...
    def get_data(self) -> ArrayLike | None: ...
    def set_zoom(self, zoom: float) -> None: ...
    def get_zoom(self) -> float: ...
    def get_children(self) -> list[martist.Artist]: ...
    def get_offset(self) -> tuple[float, float]: ...  # type: ignore[override]

class AnnotationBbox(martist.Artist, mtext._AnnotationBase):
    zorder: float
    offsetbox: OffsetBox
    arrowprops: dict[str, Any] | None
    xybox: tuple[float, float]
    boxcoords: CoordsType
    arrow_patch: FancyArrowPatch | None
    patch: FancyBboxPatch
    prop: FontProperties
    def __init__(
        self,
        offsetbox: OffsetBox,
        xy: tuple[float, float],
        xybox: tuple[float, float] | None = ...,
        xycoords: CoordsType = ...,
        boxcoords: CoordsType | None = ...,
        *,
        frameon: bool = ...,
        pad: float = ...,
        annotation_clip: bool | None = ...,
        box_alignment: tuple[float, float] = ...,
        bboxprops: dict[str, Any] | None = ...,
        arrowprops: dict[str, Any] | None = ...,
        fontsize: float | str | None = ...,
        **kwargs
    ) -> None: ...
    @property
    def xyann(self) -> tuple[float, float]: ...
    @xyann.setter
    def xyann(self, xyann: tuple[float, float]) -> None: ...
    @property
    def anncoords(
        self,
    ) -> CoordsType: ...
    @anncoords.setter
    def anncoords(
        self,
        coords: CoordsType,
    ) -> None: ...
    def get_children(self) -> list[martist.Artist]: ...
    def set_figure(self, fig: Figure | SubFigure) -> None: ...
    def set_fontsize(self, s: str | float | None = ...) -> None: ...
    def get_fontsize(self) -> float: ...
    def get_tightbbox(self, renderer: RendererBase | None = ...) -> Bbox: ...
    def update_positions(self, renderer: RendererBase) -> None: ...

class DraggableBase:
    ref_artist: martist.Artist
    got_artist: bool
    mouse_x: int
    mouse_y: int
    background: Any

    @property
    def canvas(self) -> FigureCanvasBase: ...
    @property
    def cids(self) -> list[int]: ...

    def __init__(self, ref_artist: martist.Artist, use_blit: bool = ...) -> None: ...
    def on_motion(self, evt: Event) -> None: ...
    def on_pick(self, evt: Event) -> None: ...
    def on_release(self, event: Event) -> None: ...
    def disconnect(self) -> None: ...
    def save_offset(self) -> None: ...
    def update_offset(self, dx: float, dy: float) -> None: ...
    def finalize_offset(self) -> None: ...

class DraggableOffsetBox(DraggableBase):
    offsetbox: OffsetBox
    def __init__(
        self, ref_artist: martist.Artist, offsetbox: OffsetBox, use_blit: bool = ...
    ) -> None: ...
    def save_offset(self) -> None: ...
    def update_offset(self, dx: float, dy: float) -> None: ...
    def get_loc_in_canvas(self) -> tuple[float, float]: ...

class DraggableAnnotation(DraggableBase):
    annotation: mtext.Annotation
    def __init__(self, annotation: mtext.Annotation, use_blit: bool = ...) -> None: ...
    def save_offset(self) -> None: ...
    def update_offset(self, dx: float, dy: float) -> None: ...
