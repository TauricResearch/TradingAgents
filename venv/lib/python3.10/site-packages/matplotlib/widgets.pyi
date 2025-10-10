from .artist import Artist
from .axes import Axes
from .backend_bases import FigureCanvasBase, Event, MouseEvent, MouseButton
from .collections import LineCollection
from .figure import Figure
from .lines import Line2D
from .patches import Polygon, Rectangle
from .text import Text

import PIL.Image

from collections.abc import Callable, Collection, Iterable, Sequence
from typing import Any, Literal
from numpy.typing import ArrayLike
from .typing import ColorType
import numpy as np

class LockDraw:
    def __init__(self) -> None: ...
    def __call__(self, o: Any) -> None: ...
    def release(self, o: Any) -> None: ...
    def available(self, o: Any) -> bool: ...
    def isowner(self, o: Any) -> bool: ...
    def locked(self) -> bool: ...

class Widget:
    drawon: bool
    eventson: bool
    active: bool
    def set_active(self, active: bool) -> None: ...
    def get_active(self) -> None: ...
    def ignore(self, event) -> bool: ...

class AxesWidget(Widget):
    ax: Axes
    def __init__(self, ax: Axes) -> None: ...
    @property
    def canvas(self) -> FigureCanvasBase | None: ...
    def connect_event(self, event: Event, callback: Callable) -> None: ...
    def disconnect_events(self) -> None: ...

class Button(AxesWidget):
    label: Text
    color: ColorType
    hovercolor: ColorType
    def __init__(
        self,
        ax: Axes,
        label: str,
        image: ArrayLike | PIL.Image.Image | None = ...,
        color: ColorType = ...,
        hovercolor: ColorType = ...,
        *,
        useblit: bool = ...
    ) -> None: ...
    def on_clicked(self, func: Callable[[Event], Any]) -> int: ...
    def disconnect(self, cid: int) -> None: ...

class SliderBase(AxesWidget):
    orientation: Literal["horizontal", "vertical"]
    closedmin: bool
    closedmax: bool
    valmin: float
    valmax: float
    valstep: float | ArrayLike | None
    drag_active: bool
    valfmt: str
    def __init__(
        self,
        ax: Axes,
        orientation: Literal["horizontal", "vertical"],
        closedmin: bool,
        closedmax: bool,
        valmin: float,
        valmax: float,
        valfmt: str,
        dragging: Slider | None,
        valstep: float | ArrayLike | None,
    ) -> None: ...
    def disconnect(self, cid: int) -> None: ...
    def reset(self) -> None: ...

class Slider(SliderBase):
    slidermin: Slider | None
    slidermax: Slider | None
    val: float
    valinit: float
    track: Rectangle
    poly: Polygon
    hline: Line2D
    vline: Line2D
    label: Text
    valtext: Text
    def __init__(
        self,
        ax: Axes,
        label: str,
        valmin: float,
        valmax: float,
        *,
        valinit: float = ...,
        valfmt: str | None = ...,
        closedmin: bool = ...,
        closedmax: bool = ...,
        slidermin: Slider | None = ...,
        slidermax: Slider | None = ...,
        dragging: bool = ...,
        valstep: float | ArrayLike | None = ...,
        orientation: Literal["horizontal", "vertical"] = ...,
        initcolor: ColorType = ...,
        track_color: ColorType = ...,
        handle_style: dict[str, Any] | None = ...,
        **kwargs
    ) -> None: ...
    def set_val(self, val: float) -> None: ...
    def on_changed(self, func: Callable[[float], Any]) -> int: ...

class RangeSlider(SliderBase):
    val: tuple[float, float]
    valinit: tuple[float, float]
    track: Rectangle
    poly: Polygon
    label: Text
    valtext: Text
    def __init__(
        self,
        ax: Axes,
        label: str,
        valmin: float,
        valmax: float,
        *,
        valinit: tuple[float, float] | None = ...,
        valfmt: str | None = ...,
        closedmin: bool = ...,
        closedmax: bool = ...,
        dragging: bool = ...,
        valstep: float | ArrayLike | None = ...,
        orientation: Literal["horizontal", "vertical"] = ...,
        track_color: ColorType = ...,
        handle_style: dict[str, Any] | None = ...,
        **kwargs
    ) -> None: ...
    def set_min(self, min: float) -> None: ...
    def set_max(self, max: float) -> None: ...
    def set_val(self, val: ArrayLike) -> None: ...
    def on_changed(self, func: Callable[[tuple[float, float]], Any]) -> int: ...

class CheckButtons(AxesWidget):
    labels: list[Text]
    def __init__(
        self,
        ax: Axes,
        labels: Sequence[str],
        actives: Iterable[bool] | None = ...,
        *,
        useblit: bool = ...,
        label_props: dict[str, Sequence[Any]] | None = ...,
        frame_props: dict[str, Any] | None = ...,
        check_props: dict[str, Any] | None = ...,
    ) -> None: ...
    def set_label_props(self, props: dict[str, Sequence[Any]]) -> None: ...
    def set_frame_props(self, props: dict[str, Any]) -> None: ...
    def set_check_props(self, props: dict[str, Any]) -> None: ...
    def set_active(self, index: int, state: bool | None = ...) -> None: ...  # type: ignore[override]
    def clear(self) -> None: ...
    def get_status(self) -> list[bool]: ...
    def get_checked_labels(self) -> list[str]: ...
    def on_clicked(self, func: Callable[[str | None], Any]) -> int: ...
    def disconnect(self, cid: int) -> None: ...

class TextBox(AxesWidget):
    label: Text
    text_disp: Text
    cursor_index: int
    cursor: LineCollection
    color: ColorType
    hovercolor: ColorType
    capturekeystrokes: bool
    def __init__(
        self,
        ax: Axes,
        label: str,
        initial: str = ...,
        *,
        color: ColorType = ...,
        hovercolor: ColorType = ...,
        label_pad: float = ...,
        textalignment: Literal["left", "center", "right"] = ...,
    ) -> None: ...
    @property
    def text(self) -> str: ...
    def set_val(self, val: str) -> None: ...
    def begin_typing(self) -> None: ...
    def stop_typing(self) -> None: ...
    def on_text_change(self, func: Callable[[str], Any]) -> int: ...
    def on_submit(self, func: Callable[[str], Any]) -> int: ...
    def disconnect(self, cid: int) -> None: ...

class RadioButtons(AxesWidget):
    activecolor: ColorType
    value_selected: str
    labels: list[Text]
    def __init__(
        self,
        ax: Axes,
        labels: Iterable[str],
        active: int = ...,
        activecolor: ColorType | None = ...,
        *,
        useblit: bool = ...,
        label_props: dict[str, Sequence[Any]] | None = ...,
        radio_props: dict[str, Any] | None = ...,
    ) -> None: ...
    def set_label_props(self, props: dict[str, Sequence[Any]]) -> None: ...
    def set_radio_props(self, props: dict[str, Any]) -> None: ...
    def set_active(self, index: int) -> None: ...
    def clear(self) -> None: ...
    def on_clicked(self, func: Callable[[str | None], Any]) -> int: ...
    def disconnect(self, cid: int) -> None: ...

class SubplotTool(Widget):
    figure: Figure
    targetfig: Figure
    buttonreset: Button
    def __init__(self, targetfig: Figure, toolfig: Figure) -> None: ...

class Cursor(AxesWidget):
    visible: bool
    horizOn: bool
    vertOn: bool
    useblit: bool
    lineh: Line2D
    linev: Line2D
    background: Any
    needclear: bool
    def __init__(
        self,
        ax: Axes,
        *,
        horizOn: bool = ...,
        vertOn: bool = ...,
        useblit: bool = ...,
        **lineprops
    ) -> None: ...
    def clear(self, event: Event) -> None: ...
    def onmove(self, event: Event) -> None: ...

class MultiCursor(Widget):
    axes: Sequence[Axes]
    horizOn: bool
    vertOn: bool
    visible: bool
    useblit: bool
    vlines: list[Line2D]
    hlines: list[Line2D]
    def __init__(
        self,
        canvas: Any,
        axes: Sequence[Axes],
        *,
        useblit: bool = ...,
        horizOn: bool = ...,
        vertOn: bool = ...,
        **lineprops
    ) -> None: ...
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def clear(self, event: Event) -> None: ...
    def onmove(self, event: Event) -> None: ...

class _SelectorWidget(AxesWidget):
    onselect: Callable[[float, float], Any]
    useblit: bool
    background: Any
    validButtons: list[MouseButton]
    def __init__(
        self,
        ax: Axes,
        onselect: Callable[[float, float], Any] | None = ...,
        useblit: bool = ...,
        button: MouseButton | Collection[MouseButton] | None = ...,
        state_modifier_keys: dict[str, str] | None = ...,
        use_data_coordinates: bool = ...,
    ) -> None: ...
    def update_background(self, event: Event) -> None: ...
    def connect_default_events(self) -> None: ...
    def ignore(self, event: Event) -> bool: ...
    def update(self) -> None: ...
    def press(self, event: Event) -> bool: ...
    def release(self, event: Event) -> bool: ...
    def onmove(self, event: Event) -> bool: ...
    def on_scroll(self, event: Event) -> None: ...
    def on_key_press(self, event: Event) -> None: ...
    def on_key_release(self, event: Event) -> None: ...
    def set_visible(self, visible: bool) -> None: ...
    def get_visible(self) -> bool: ...
    def clear(self) -> None: ...
    @property
    def artists(self) -> tuple[Artist]: ...
    def set_props(self, **props) -> None: ...
    def set_handle_props(self, **handle_props) -> None: ...
    def add_state(self, state: str) -> None: ...
    def remove_state(self, state: str) -> None: ...

class SpanSelector(_SelectorWidget):
    snap_values: ArrayLike | None
    onmove_callback: Callable[[float, float], Any]
    minspan: float
    grab_range: float
    drag_from_anywhere: bool
    ignore_event_outside: bool
    def __init__(
        self,
        ax: Axes,
        onselect: Callable[[float, float], Any],
        direction: Literal["horizontal", "vertical"],
        *,
        minspan: float = ...,
        useblit: bool = ...,
        props: dict[str, Any] | None = ...,
        onmove_callback: Callable[[float, float], Any] | None = ...,
        interactive: bool = ...,
        button: MouseButton | Collection[MouseButton] | None = ...,
        handle_props: dict[str, Any] | None = ...,
        grab_range: float = ...,
        state_modifier_keys: dict[str, str] | None = ...,
        drag_from_anywhere: bool = ...,
        ignore_event_outside: bool = ...,
        snap_values: ArrayLike | None = ...,
    ) -> None: ...
    def new_axes(
        self,
        ax: Axes,
        *,
        _props: dict[str, Any] | None = ...,
        _init: bool = ...,
    ) -> None: ...
    def connect_default_events(self) -> None: ...
    @property
    def direction(self) -> Literal["horizontal", "vertical"]: ...
    @direction.setter
    def direction(self, direction: Literal["horizontal", "vertical"]) -> None: ...
    @property
    def extents(self) -> tuple[float, float]: ...
    @extents.setter
    def extents(self, extents: tuple[float, float]) -> None: ...

class ToolLineHandles:
    ax: Axes
    def __init__(
        self,
        ax: Axes,
        positions: ArrayLike,
        direction: Literal["horizontal", "vertical"],
        *,
        line_props: dict[str, Any] | None = ...,
        useblit: bool = ...,
    ) -> None: ...
    @property
    def artists(self) -> tuple[Line2D]: ...
    @property
    def positions(self) -> list[float]: ...
    @property
    def direction(self) -> Literal["horizontal", "vertical"]: ...
    def set_data(self, positions: ArrayLike) -> None: ...
    def set_visible(self, value: bool) -> None: ...
    def set_animated(self, value: bool) -> None: ...
    def remove(self) -> None: ...
    def closest(self, x: float, y: float) -> tuple[int, float]: ...

class ToolHandles:
    ax: Axes
    def __init__(
        self,
        ax: Axes,
        x: ArrayLike,
        y: ArrayLike,
        *,
        marker: str = ...,
        marker_props: dict[str, Any] | None = ...,
        useblit: bool = ...,
    ) -> None: ...
    @property
    def x(self) -> ArrayLike: ...
    @property
    def y(self) -> ArrayLike: ...
    @property
    def artists(self) -> tuple[Line2D]: ...
    def set_data(self, pts: ArrayLike, y: ArrayLike | None = ...) -> None: ...
    def set_visible(self, val: bool) -> None: ...
    def set_animated(self, val: bool) -> None: ...
    def closest(self, x: float, y: float) -> tuple[int, float]: ...

class RectangleSelector(_SelectorWidget):
    drag_from_anywhere: bool
    ignore_event_outside: bool
    minspanx: float
    minspany: float
    spancoords: Literal["data", "pixels"]
    grab_range: float
    def __init__(
        self,
        ax: Axes,
        onselect: Callable[[MouseEvent, MouseEvent], Any] | None = ...,
        *,
        minspanx: float = ...,
        minspany: float = ...,
        useblit: bool = ...,
        props: dict[str, Any] | None = ...,
        spancoords: Literal["data", "pixels"] = ...,
        button: MouseButton | Collection[MouseButton] | None = ...,
        grab_range: float = ...,
        handle_props: dict[str, Any] | None = ...,
        interactive: bool = ...,
        state_modifier_keys: dict[str, str] | None = ...,
        drag_from_anywhere: bool = ...,
        ignore_event_outside: bool = ...,
        use_data_coordinates: bool = ...,
    ) -> None: ...
    @property
    def corners(self) -> tuple[np.ndarray, np.ndarray]: ...
    @property
    def edge_centers(self) -> tuple[np.ndarray, np.ndarray]: ...
    @property
    def center(self) -> tuple[float, float]: ...
    @property
    def extents(self) -> tuple[float, float, float, float]: ...
    @extents.setter
    def extents(self, extents: tuple[float, float, float, float]) -> None: ...
    @property
    def rotation(self) -> float: ...
    @rotation.setter
    def rotation(self, value: float) -> None: ...
    @property
    def geometry(self) -> np.ndarray: ...

class EllipseSelector(RectangleSelector): ...

class LassoSelector(_SelectorWidget):
    verts: None | list[tuple[float, float]]
    def __init__(
        self,
        ax: Axes,
        onselect: Callable[[list[tuple[float, float]]], Any] | None = ...,
        *,
        useblit: bool = ...,
        props: dict[str, Any] | None = ...,
        button: MouseButton | Collection[MouseButton] | None = ...,
    ) -> None: ...

class PolygonSelector(_SelectorWidget):
    grab_range: float
    def __init__(
        self,
        ax: Axes,
        onselect: Callable[[ArrayLike, ArrayLike], Any] | None = ...,
        *,
        useblit: bool = ...,
        props: dict[str, Any] | None = ...,
        handle_props: dict[str, Any] | None = ...,
        grab_range: float = ...,
        draw_bounding_box: bool = ...,
        box_handle_props: dict[str, Any] | None = ...,
        box_props: dict[str, Any] | None = ...
    ) -> None: ...
    def onmove(self, event: Event) -> bool: ...
    @property
    def verts(self) -> list[tuple[float, float]]: ...
    @verts.setter
    def verts(self, xys: Sequence[tuple[float, float]]) -> None: ...

class Lasso(AxesWidget):
    useblit: bool
    background: Any
    verts: list[tuple[float, float]] | None
    line: Line2D
    callback: Callable[[list[tuple[float, float]]], Any]
    def __init__(
        self,
        ax: Axes,
        xy: tuple[float, float],
        callback: Callable[[list[tuple[float, float]]], Any],
        *,
        useblit: bool = ...,
        props: dict[str, Any] | None = ...,
    ) -> None: ...
    def onrelease(self, event: Event) -> None: ...
    def onmove(self, event: Event) -> None: ...
