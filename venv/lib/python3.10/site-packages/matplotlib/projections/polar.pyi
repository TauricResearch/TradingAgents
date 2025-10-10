import matplotlib.axis as maxis
import matplotlib.ticker as mticker
import matplotlib.transforms as mtransforms
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.text import Text

import numpy as np
from numpy.typing import ArrayLike
from collections.abc import Sequence
from typing import Any, ClassVar, Literal, overload

class PolarTransform(mtransforms.Transform):
    input_dims: int
    output_dims: int
    def __init__(
        self,
        axis: PolarAxes | None = ...,
        use_rmin: bool = ...,
        *,
        apply_theta_transforms: bool = ...,
        scale_transform: mtransforms.Transform | None = ...,
    ) -> None: ...
    def inverted(self) -> InvertedPolarTransform: ...

class PolarAffine(mtransforms.Affine2DBase):
    def __init__(
        self, scale_transform: mtransforms.Transform, limits: mtransforms.BboxBase
    ) -> None: ...

class InvertedPolarTransform(mtransforms.Transform):
    input_dims: int
    output_dims: int
    def __init__(
        self,
        axis: PolarAxes | None = ...,
        use_rmin: bool = ...,
        *,
        apply_theta_transforms: bool = ...,
    ) -> None: ...
    def inverted(self) -> PolarTransform: ...

class ThetaFormatter(mticker.Formatter): ...

class _AxisWrapper:
    def __init__(self, axis: maxis.Axis) -> None: ...
    def get_view_interval(self) -> np.ndarray: ...
    def set_view_interval(self, vmin: float, vmax: float) -> None: ...
    def get_minpos(self) -> float: ...
    def get_data_interval(self) -> np.ndarray: ...
    def set_data_interval(self, vmin: float, vmax: float) -> None: ...
    def get_tick_space(self) -> int: ...

class ThetaLocator(mticker.Locator):
    base: mticker.Locator
    axis: _AxisWrapper | None
    def __init__(self, base: mticker.Locator) -> None: ...

class ThetaTick(maxis.XTick):
    def __init__(self, axes: PolarAxes, *args, **kwargs) -> None: ...

class ThetaAxis(maxis.XAxis):
    axis_name: str

class RadialLocator(mticker.Locator):
    base: mticker.Locator
    def __init__(self, base, axes: PolarAxes | None = ...) -> None: ...

class RadialTick(maxis.YTick): ...

class RadialAxis(maxis.YAxis):
    axis_name: str

class _WedgeBbox(mtransforms.Bbox):
    def __init__(
        self,
        center: tuple[float, float],
        viewLim: mtransforms.Bbox,
        originLim: mtransforms.Bbox,
        **kwargs,
    ) -> None: ...

class PolarAxes(Axes):

    PolarTransform: ClassVar[type] = PolarTransform
    PolarAffine: ClassVar[type] = PolarAffine
    InvertedPolarTransform: ClassVar[type] = InvertedPolarTransform
    ThetaFormatter: ClassVar[type] = ThetaFormatter
    RadialLocator: ClassVar[type] = RadialLocator
    ThetaLocator: ClassVar[type] = ThetaLocator

    name: str
    use_sticky_edges: bool
    def __init__(
        self,
        *args,
        theta_offset: float = ...,
        theta_direction: float = ...,
        rlabel_position: float = ...,
        **kwargs,
    ) -> None: ...
    def get_xaxis_transform(
        self, which: Literal["tick1", "tick2", "grid"] = ...
    ) -> mtransforms.Transform: ...
    def get_xaxis_text1_transform(
        self, pad: float
    ) -> tuple[
        mtransforms.Transform,
        Literal["center", "top", "bottom", "baseline", "center_baseline"],
        Literal["center", "left", "right"],
    ]: ...
    def get_xaxis_text2_transform(
        self, pad: float
    ) -> tuple[
        mtransforms.Transform,
        Literal["center", "top", "bottom", "baseline", "center_baseline"],
        Literal["center", "left", "right"],
    ]: ...
    def get_yaxis_transform(
        self, which: Literal["tick1", "tick2", "grid"] = ...
    ) -> mtransforms.Transform: ...
    def get_yaxis_text1_transform(
        self, pad: float
    ) -> tuple[
        mtransforms.Transform,
        Literal["center", "top", "bottom", "baseline", "center_baseline"],
        Literal["center", "left", "right"],
    ]: ...
    def get_yaxis_text2_transform(
        self, pad: float
    ) -> tuple[
        mtransforms.Transform,
        Literal["center", "top", "bottom", "baseline", "center_baseline"],
        Literal["center", "left", "right"],
    ]: ...
    def set_thetamax(self, thetamax: float) -> None: ...
    def get_thetamax(self) -> float: ...
    def set_thetamin(self, thetamin: float) -> None: ...
    def get_thetamin(self) -> float: ...
    @overload
    def set_thetalim(self, minval: float, maxval: float, /) -> tuple[float, float]: ...
    @overload
    def set_thetalim(self, *, thetamin: float, thetamax: float) -> tuple[float, float]: ...
    def set_theta_offset(self, offset: float) -> None: ...
    def get_theta_offset(self) -> float: ...
    def set_theta_zero_location(
        self,
        loc: Literal["N", "NW", "W", "SW", "S", "SE", "E", "NE"],
        offset: float = ...,
    ) -> None: ...
    def set_theta_direction(
        self,
        direction: Literal[-1, 1, "clockwise", "counterclockwise", "anticlockwise"],
    ) -> None: ...
    def get_theta_direction(self) -> Literal[-1, 1]: ...
    def set_rmax(self, rmax: float) -> None: ...
    def get_rmax(self) -> float: ...
    def set_rmin(self, rmin: float) -> None: ...
    def get_rmin(self) -> float: ...
    def set_rorigin(self, rorigin: float | None) -> None: ...
    def get_rorigin(self) -> float: ...
    def get_rsign(self) -> float: ...
    def set_rlim(
        self,
        bottom: float | tuple[float, float] | None = ...,
        top: float | None = ...,
        *,
        emit: bool = ...,
        auto: bool = ...,
        **kwargs,
    ) -> tuple[float, float]: ...
    def get_rlabel_position(self) -> float: ...
    def set_rlabel_position(self, value: float) -> None: ...
    def set_rscale(self, *args, **kwargs) -> None: ...
    def set_rticks(self, *args, **kwargs) -> None: ...
    def set_thetagrids(
        self,
        angles: ArrayLike,
        labels: Sequence[str | Text] | None = ...,
        fmt: str | None = ...,
        **kwargs,
    ) -> tuple[list[Line2D], list[Text]]: ...
    def set_rgrids(
        self,
        radii: ArrayLike,
        labels: Sequence[str | Text] | None = ...,
        angle: float | None = ...,
        fmt: str | None = ...,
        **kwargs,
    ) -> tuple[list[Line2D], list[Text]]: ...
    def format_coord(self, theta: float, r: float) -> str: ...
    def get_data_ratio(self) -> float: ...
    def can_zoom(self) -> bool: ...
    def can_pan(self) -> bool: ...
    def start_pan(self, x: float, y: float, button: int) -> None: ...
    def end_pan(self) -> None: ...
    def drag_pan(self, button: Any, key: Any, x: float, y: float) -> None: ...
