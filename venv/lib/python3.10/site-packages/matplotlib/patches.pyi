from . import artist
from .axes import Axes
from .backend_bases import RendererBase, MouseEvent
from .path import Path
from .transforms import Transform, Bbox

from typing import Any, Literal, overload

import numpy as np
from numpy.typing import ArrayLike
from .typing import ColorType, LineStyleType, CapStyleType, JoinStyleType

class Patch(artist.Artist):
    zorder: float
    def __init__(
        self,
        *,
        edgecolor: ColorType | None = ...,
        facecolor: ColorType | None = ...,
        color: ColorType | None = ...,
        linewidth: float | None = ...,
        linestyle: LineStyleType | None = ...,
        antialiased: bool | None = ...,
        hatch: str | None = ...,
        fill: bool = ...,
        capstyle: CapStyleType | None = ...,
        joinstyle: JoinStyleType | None = ...,
        **kwargs,
    ) -> None: ...
    def get_verts(self) -> ArrayLike: ...
    def contains(self, mouseevent: MouseEvent, radius: float | None = None) -> tuple[bool, dict[Any, Any]]: ...
    def contains_point(
        self, point: tuple[float, float], radius: float | None = ...
    ) -> bool: ...
    def contains_points(
        self, points: ArrayLike, radius: float | None = ...
    ) -> np.ndarray: ...
    def get_extents(self) -> Bbox: ...
    def get_transform(self) -> Transform: ...
    def get_data_transform(self) -> Transform: ...
    def get_patch_transform(self) -> Transform: ...
    def get_antialiased(self) -> bool: ...
    def get_edgecolor(self) -> ColorType: ...
    def get_facecolor(self) -> ColorType: ...
    def get_linewidth(self) -> float: ...
    def get_linestyle(self) -> LineStyleType: ...
    def set_antialiased(self, aa: bool | None) -> None: ...
    def set_edgecolor(self, color: ColorType | None) -> None: ...
    def set_facecolor(self, color: ColorType | None) -> None: ...
    def set_color(self, c: ColorType | None) -> None: ...
    def set_alpha(self, alpha: float | None) -> None: ...
    def set_linewidth(self, w: float | None) -> None: ...
    def set_linestyle(self, ls: LineStyleType | None) -> None: ...
    def set_fill(self, b: bool) -> None: ...
    def get_fill(self) -> bool: ...
    fill = property(get_fill, set_fill)
    def set_capstyle(self, s: CapStyleType) -> None: ...
    def get_capstyle(self) -> Literal["butt", "projecting", "round"]: ...
    def set_joinstyle(self, s: JoinStyleType) -> None: ...
    def get_joinstyle(self) -> Literal["miter", "round", "bevel"]: ...
    def set_hatch(self, hatch: str) -> None: ...
    def set_hatch_linewidth(self, lw: float) -> None: ...
    def get_hatch_linewidth(self) -> float: ...
    def get_hatch(self) -> str: ...
    def get_path(self) -> Path: ...

class Shadow(Patch):
    patch: Patch
    def __init__(self, patch: Patch, ox: float, oy: float, *, shade: float = ..., **kwargs) -> None: ...

class Rectangle(Patch):
    angle: float
    def __init__(
        self,
        xy: tuple[float, float],
        width: float,
        height: float,
        *,
        angle: float = ...,
        rotation_point: Literal["xy", "center"] | tuple[float, float] = ...,
        **kwargs,
    ) -> None: ...
    @property
    def rotation_point(self) -> Literal["xy", "center"] | tuple[float, float]: ...
    @rotation_point.setter
    def rotation_point(
        self, value: Literal["xy", "center"] | tuple[float, float]
    ) -> None: ...
    def get_x(self) -> float: ...
    def get_y(self) -> float: ...
    def get_xy(self) -> tuple[float, float]: ...
    def get_corners(self) -> np.ndarray: ...
    def get_center(self) -> np.ndarray: ...
    def get_width(self) -> float: ...
    def get_height(self) -> float: ...
    def get_angle(self) -> float: ...
    def set_x(self, x: float) -> None: ...
    def set_y(self, y: float) -> None: ...
    def set_angle(self, angle: float) -> None: ...
    def set_xy(self, xy: tuple[float, float]) -> None: ...
    def set_width(self, w: float) -> None: ...
    def set_height(self, h: float) -> None: ...
    @overload
    def set_bounds(self, args: tuple[float, float, float, float], /) -> None: ...
    @overload
    def set_bounds(
        self, left: float, bottom: float, width: float, height: float, /
    ) -> None: ...
    def get_bbox(self) -> Bbox: ...
    xy = property(get_xy, set_xy)

class RegularPolygon(Patch):
    xy: tuple[float, float]
    numvertices: int
    orientation: float
    radius: float
    def __init__(
        self,
        xy: tuple[float, float],
        numVertices: int,
        *,
        radius: float = ...,
        orientation: float = ...,
        **kwargs,
    ) -> None: ...

class PathPatch(Patch):
    def __init__(self, path: Path, **kwargs) -> None: ...
    def set_path(self, path: Path) -> None: ...

class StepPatch(PathPatch):
    orientation: Literal["vertical", "horizontal"]
    def __init__(
        self,
        values: ArrayLike,
        edges: ArrayLike,
        *,
        orientation: Literal["vertical", "horizontal"] = ...,
        baseline: float = ...,
        **kwargs,
    ) -> None: ...

    # NamedTuple StairData, defined in body of method
    def get_data(self) -> tuple[np.ndarray, np.ndarray, float]: ...
    def set_data(
        self,
        values: ArrayLike | None = ...,
        edges: ArrayLike | None = ...,
        baseline: float | None = ...,
    ) -> None: ...

class Polygon(Patch):
    def __init__(self, xy: ArrayLike, *, closed: bool = ..., **kwargs) -> None: ...
    def get_closed(self) -> bool: ...
    def set_closed(self, closed: bool) -> None: ...
    def get_xy(self) -> np.ndarray: ...
    def set_xy(self, xy: ArrayLike) -> None: ...
    xy = property(get_xy, set_xy)

class Wedge(Patch):
    center: tuple[float, float]
    r: float
    theta1: float
    theta2: float
    width: float | None
    def __init__(
        self,
        center: tuple[float, float],
        r: float,
        theta1: float,
        theta2: float,
        *,
        width: float | None = ...,
        **kwargs,
    ) -> None: ...
    def set_center(self, center: tuple[float, float]) -> None: ...
    def set_radius(self, radius: float) -> None: ...
    def set_theta1(self, theta1: float) -> None: ...
    def set_theta2(self, theta2: float) -> None: ...
    def set_width(self, width: float | None) -> None: ...

class Arrow(Patch):
    def __init__(
        self, x: float, y: float, dx: float, dy: float, *, width: float = ..., **kwargs
    ) -> None: ...
    def set_data(
        self,
        x: float | None = ...,
        y: float | None = ...,
        dx: float | None = ...,
        dy: float | None = ...,
        width: float | None = ...,
    ) -> None: ...
class FancyArrow(Polygon):
    def __init__(
        self,
        x: float,
        y: float,
        dx: float,
        dy: float,
        *,
        width: float = ...,
        length_includes_head: bool = ...,
        head_width: float | None = ...,
        head_length: float | None = ...,
        shape: Literal["full", "left", "right"] = ...,
        overhang: float = ...,
        head_starts_at_zero: bool = ...,
        **kwargs,
    ) -> None: ...
    def set_data(
        self,
        *,
        x: float | None = ...,
        y: float | None = ...,
        dx: float | None = ...,
        dy: float | None = ...,
        width: float | None = ...,
        head_width: float | None = ...,
        head_length: float | None = ...,
    ) -> None: ...

class CirclePolygon(RegularPolygon):
    def __init__(
        self,
        xy: tuple[float, float],
        radius: float = ...,
        *,
        resolution: int = ...,
        **kwargs,
    ) -> None: ...

class Ellipse(Patch):
    def __init__(
        self,
        xy: tuple[float, float],
        width: float,
        height: float,
        *,
        angle: float = ...,
        **kwargs,
    ) -> None: ...
    def set_center(self, xy: tuple[float, float]) -> None: ...
    def get_center(self) -> float: ...
    center = property(get_center, set_center)

    def set_width(self, width: float) -> None: ...
    def get_width(self) -> float: ...
    width = property(get_width, set_width)

    def set_height(self, height: float) -> None: ...
    def get_height(self) -> float: ...
    height = property(get_height, set_height)

    def set_angle(self, angle: float) -> None: ...
    def get_angle(self) -> float: ...
    angle = property(get_angle, set_angle)

    def get_corners(self) -> np.ndarray: ...

    def get_vertices(self) -> list[tuple[float, float]]: ...
    def get_co_vertices(self) -> list[tuple[float, float]]: ...


class Annulus(Patch):
    a: float
    b: float
    def __init__(
        self,
        xy: tuple[float, float],
        r: float | tuple[float, float],
        width: float,
        angle: float = ...,
        **kwargs,
    ) -> None: ...
    def set_center(self, xy: tuple[float, float]) -> None: ...
    def get_center(self) -> tuple[float, float]: ...
    center = property(get_center, set_center)

    def set_width(self, width: float) -> None: ...
    def get_width(self) -> float: ...
    width = property(get_width, set_width)

    def set_angle(self, angle: float) -> None: ...
    def get_angle(self) -> float: ...
    angle = property(get_angle, set_angle)

    def set_semimajor(self, a: float) -> None: ...
    def set_semiminor(self, b: float) -> None: ...
    def set_radii(self, r: float | tuple[float, float]) -> None: ...
    def get_radii(self) -> tuple[float, float]: ...
    radii = property(get_radii, set_radii)

class Circle(Ellipse):
    def __init__(
        self, xy: tuple[float, float], radius: float = ..., **kwargs
    ) -> None: ...
    def set_radius(self, radius: float) -> None: ...
    def get_radius(self) -> float: ...
    radius = property(get_radius, set_radius)

class Arc(Ellipse):
    theta1: float
    theta2: float
    def __init__(
        self,
        xy: tuple[float, float],
        width: float,
        height: float,
        *,
        angle: float = ...,
        theta1: float = ...,
        theta2: float = ...,
        **kwargs,
    ) -> None: ...

def bbox_artist(
    artist: artist.Artist,
    renderer: RendererBase,
    props: dict[str, Any] | None = ...,
    fill: bool = ...,
) -> None: ...
def draw_bbox(
    bbox: Bbox,
    renderer: RendererBase,
    color: ColorType = ...,
    trans: Transform | None = ...,
) -> None: ...

class _Style:
    def __new__(cls, stylename, **kwargs): ...
    @classmethod
    def get_styles(cls) -> dict[str, type]: ...
    @classmethod
    def pprint_styles(cls) -> str: ...
    @classmethod
    def register(cls, name: str, style: type) -> None: ...

class BoxStyle(_Style):
    class Square(BoxStyle):
        pad: float
        def __init__(self, pad: float = ...) -> None: ...
        def __call__(
            self,
            x0: float,
            y0: float,
            width: float,
            height: float,
            mutation_size: float,
        ) -> Path: ...

    class Circle(BoxStyle):
        pad: float
        def __init__(self, pad: float = ...) -> None: ...
        def __call__(
            self,
            x0: float,
            y0: float,
            width: float,
            height: float,
            mutation_size: float,
        ) -> Path: ...

    class Ellipse(BoxStyle):
        pad: float
        def __init__(self, pad: float = ...) -> None: ...
        def __call__(
            self,
            x0: float,
            y0: float,
            width: float,
            height: float,
            mutation_size: float,
        ) -> Path: ...

    class LArrow(BoxStyle):
        pad: float
        def __init__(self, pad: float = ...) -> None: ...
        def __call__(
            self,
            x0: float,
            y0: float,
            width: float,
            height: float,
            mutation_size: float,
        ) -> Path: ...

    class RArrow(LArrow):
        def __call__(
            self,
            x0: float,
            y0: float,
            width: float,
            height: float,
            mutation_size: float,
        ) -> Path: ...

    class DArrow(BoxStyle):
        pad: float
        def __init__(self, pad: float = ...) -> None: ...
        def __call__(
            self,
            x0: float,
            y0: float,
            width: float,
            height: float,
            mutation_size: float,
        ) -> Path: ...

    class Round(BoxStyle):
        pad: float
        rounding_size: float | None
        def __init__(
            self, pad: float = ..., rounding_size: float | None = ...
        ) -> None: ...
        def __call__(
            self,
            x0: float,
            y0: float,
            width: float,
            height: float,
            mutation_size: float,
        ) -> Path: ...

    class Round4(BoxStyle):
        pad: float
        rounding_size: float | None
        def __init__(
            self, pad: float = ..., rounding_size: float | None = ...
        ) -> None: ...
        def __call__(
            self,
            x0: float,
            y0: float,
            width: float,
            height: float,
            mutation_size: float,
        ) -> Path: ...

    class Sawtooth(BoxStyle):
        pad: float
        tooth_size: float | None
        def __init__(
            self, pad: float = ..., tooth_size: float | None = ...
        ) -> None: ...
        def __call__(
            self,
            x0: float,
            y0: float,
            width: float,
            height: float,
            mutation_size: float,
        ) -> Path: ...

    class Roundtooth(Sawtooth):
        def __call__(
            self,
            x0: float,
            y0: float,
            width: float,
            height: float,
            mutation_size: float,
        ) -> Path: ...

class ConnectionStyle(_Style):
    class _Base(ConnectionStyle):
        def __call__(
            self,
            posA: tuple[float, float],
            posB: tuple[float, float],
            shrinkA: float = ...,
            shrinkB: float = ...,
            patchA: Patch | None = ...,
            patchB: Patch | None = ...,
        ) -> Path: ...

    class Arc3(_Base):
        rad: float
        def __init__(self, rad: float = ...) -> None: ...
        def connect(
            self, posA: tuple[float, float], posB: tuple[float, float]
        ) -> Path: ...

    class Angle3(_Base):
        angleA: float
        angleB: float
        def __init__(self, angleA: float = ..., angleB: float = ...) -> None: ...
        def connect(
            self, posA: tuple[float, float], posB: tuple[float, float]
        ) -> Path: ...

    class Angle(_Base):
        angleA: float
        angleB: float
        rad: float
        def __init__(
            self, angleA: float = ..., angleB: float = ..., rad: float = ...
        ) -> None: ...
        def connect(
            self, posA: tuple[float, float], posB: tuple[float, float]
        ) -> Path: ...

    class Arc(_Base):
        angleA: float
        angleB: float
        armA: float | None
        armB: float | None
        rad: float
        def __init__(
            self,
            angleA: float = ...,
            angleB: float = ...,
            armA: float | None = ...,
            armB: float | None = ...,
            rad: float = ...,
        ) -> None: ...
        def connect(
            self, posA: tuple[float, float], posB: tuple[float, float]
        ) -> Path: ...

    class Bar(_Base):
        armA: float
        armB: float
        fraction: float
        angle: float | None
        def __init__(
            self,
            armA: float = ...,
            armB: float = ...,
            fraction: float = ...,
            angle: float | None = ...,
        ) -> None: ...
        def connect(
            self, posA: tuple[float, float], posB: tuple[float, float]
        ) -> Path: ...

class ArrowStyle(_Style):
    class _Base(ArrowStyle):
        @staticmethod
        def ensure_quadratic_bezier(path: Path) -> list[float]: ...
        def transmute(
            self, path: Path, mutation_size: float, linewidth: float
        ) -> tuple[Path, bool]: ...
        def __call__(
            self,
            path: Path,
            mutation_size: float,
            linewidth: float,
            aspect_ratio: float = ...,
        ) -> tuple[Path, bool]: ...

    class _Curve(_Base):
        arrow: str
        fillbegin: bool
        fillend: bool
        def __init__(
            self,
            head_length: float = ...,
            head_width: float = ...,
            widthA: float = ...,
            widthB: float = ...,
            lengthA: float = ...,
            lengthB: float = ...,
            angleA: float | None = ...,
            angleB: float | None = ...,
            scaleA: float | None = ...,
            scaleB: float | None = ...,
        ) -> None: ...

    class Curve(_Curve):
        def __init__(self) -> None: ...

    class CurveA(_Curve):
        arrow: str

    class CurveB(_Curve):
        arrow: str

    class CurveAB(_Curve):
        arrow: str

    class CurveFilledA(_Curve):
        arrow: str

    class CurveFilledB(_Curve):
        arrow: str

    class CurveFilledAB(_Curve):
        arrow: str

    class BracketA(_Curve):
        arrow: str
        def __init__(
            self, widthA: float = ..., lengthA: float = ..., angleA: float = ...
        ) -> None: ...

    class BracketB(_Curve):
        arrow: str
        def __init__(
            self, widthB: float = ..., lengthB: float = ..., angleB: float = ...
        ) -> None: ...

    class BracketAB(_Curve):
        arrow: str
        def __init__(
            self,
            widthA: float = ...,
            lengthA: float = ...,
            angleA: float = ...,
            widthB: float = ...,
            lengthB: float = ...,
            angleB: float = ...,
        ) -> None: ...

    class BarAB(_Curve):
        arrow: str
        def __init__(
            self,
            widthA: float = ...,
            angleA: float = ...,
            widthB: float = ...,
            angleB: float = ...,
        ) -> None: ...

    class BracketCurve(_Curve):
        arrow: str
        def __init__(
            self, widthA: float = ..., lengthA: float = ..., angleA: float | None = ...
        ) -> None: ...

    class CurveBracket(_Curve):
        arrow: str
        def __init__(
            self, widthB: float = ..., lengthB: float = ..., angleB: float | None = ...
        ) -> None: ...

    class Simple(_Base):
        def __init__(
            self,
            head_length: float = ...,
            head_width: float = ...,
            tail_width: float = ...,
        ) -> None: ...

    class Fancy(_Base):
        def __init__(
            self,
            head_length: float = ...,
            head_width: float = ...,
            tail_width: float = ...,
        ) -> None: ...

    class Wedge(_Base):
        tail_width: float
        shrink_factor: float
        def __init__(
            self, tail_width: float = ..., shrink_factor: float = ...
        ) -> None: ...

class FancyBboxPatch(Patch):
    def __init__(
        self,
        xy: tuple[float, float],
        width: float,
        height: float,
        boxstyle: str | BoxStyle = ...,
        *,
        mutation_scale: float = ...,
        mutation_aspect: float = ...,
        **kwargs,
    ) -> None: ...
    def set_boxstyle(self, boxstyle: str | BoxStyle | None = ..., **kwargs) -> None: ...
    def get_boxstyle(self) -> BoxStyle: ...
    def set_mutation_scale(self, scale: float) -> None: ...
    def get_mutation_scale(self) -> float: ...
    def set_mutation_aspect(self, aspect: float) -> None: ...
    def get_mutation_aspect(self) -> float: ...
    def get_x(self) -> float: ...
    def get_y(self) -> float: ...
    def get_width(self) -> float: ...
    def get_height(self) -> float: ...
    def set_x(self, x: float) -> None: ...
    def set_y(self, y: float) -> None: ...
    def set_width(self, w: float) -> None: ...
    def set_height(self, h: float) -> None: ...
    @overload
    def set_bounds(self, args: tuple[float, float, float, float], /) -> None: ...
    @overload
    def set_bounds(
        self, left: float, bottom: float, width: float, height: float, /
    ) -> None: ...
    def get_bbox(self) -> Bbox: ...

class FancyArrowPatch(Patch):
    patchA: Patch
    patchB: Patch
    shrinkA: float
    shrinkB: float
    def __init__(
        self,
        posA: tuple[float, float] | None = ...,
        posB: tuple[float, float] | None = ...,
        *,
        path: Path | None = ...,
        arrowstyle: str | ArrowStyle = ...,
        connectionstyle: str | ConnectionStyle = ...,
        patchA: Patch | None = ...,
        patchB: Patch | None = ...,
        shrinkA: float = ...,
        shrinkB: float = ...,
        mutation_scale: float = ...,
        mutation_aspect: float | None = ...,
        **kwargs,
    ) -> None: ...
    def set_positions(
        self, posA: tuple[float, float], posB: tuple[float, float]
    ) -> None: ...
    def set_patchA(self, patchA: Patch) -> None: ...
    def set_patchB(self, patchB: Patch) -> None: ...
    def set_connectionstyle(self, connectionstyle: str | ConnectionStyle | None = ..., **kwargs) -> None: ...
    def get_connectionstyle(self) -> ConnectionStyle: ...
    def set_arrowstyle(self, arrowstyle: str | ArrowStyle | None = ..., **kwargs) -> None: ...
    def get_arrowstyle(self) -> ArrowStyle: ...
    def set_mutation_scale(self, scale: float) -> None: ...
    def get_mutation_scale(self) -> float: ...
    def set_mutation_aspect(self, aspect: float | None) -> None: ...
    def get_mutation_aspect(self) -> float: ...

class ConnectionPatch(FancyArrowPatch):
    xy1: tuple[float, float]
    xy2: tuple[float, float]
    coords1: str | Transform
    coords2: str | Transform | None
    axesA: Axes | None
    axesB: Axes | None
    def __init__(
        self,
        xyA: tuple[float, float],
        xyB: tuple[float, float],
        coordsA: str | Transform,
        coordsB: str | Transform | None = ...,
        *,
        axesA: Axes | None = ...,
        axesB: Axes | None = ...,
        arrowstyle: str | ArrowStyle = ...,
        connectionstyle: str | ConnectionStyle = ...,
        patchA: Patch | None = ...,
        patchB: Patch | None = ...,
        shrinkA: float = ...,
        shrinkB: float = ...,
        mutation_scale: float = ...,
        mutation_aspect: float | None = ...,
        clip_on: bool = ...,
        **kwargs,
    ) -> None: ...
    def set_annotation_clip(self, b: bool | None) -> None: ...
    def get_annotation_clip(self) -> bool | None: ...
