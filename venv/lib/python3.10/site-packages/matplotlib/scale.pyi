from matplotlib.axis import Axis
from matplotlib.transforms import Transform

from collections.abc import Callable, Iterable
from typing import Literal
from numpy.typing import ArrayLike

class ScaleBase:
    def __init__(self, axis: Axis | None) -> None: ...
    def get_transform(self) -> Transform: ...
    def set_default_locators_and_formatters(self, axis: Axis) -> None: ...
    def limit_range_for_scale(
        self, vmin: float, vmax: float, minpos: float
    ) -> tuple[float, float]: ...

class LinearScale(ScaleBase):
    name: str

class FuncTransform(Transform):
    input_dims: int
    output_dims: int
    def __init__(
        self,
        forward: Callable[[ArrayLike], ArrayLike],
        inverse: Callable[[ArrayLike], ArrayLike],
    ) -> None: ...
    def inverted(self) -> FuncTransform: ...

class FuncScale(ScaleBase):
    name: str
    def __init__(
        self,
        axis: Axis | None,
        functions: tuple[
            Callable[[ArrayLike], ArrayLike], Callable[[ArrayLike], ArrayLike]
        ],
    ) -> None: ...

class LogTransform(Transform):
    input_dims: int
    output_dims: int
    base: float
    def __init__(
        self, base: float, nonpositive: Literal["clip", "mask"] = ...
    ) -> None: ...
    def inverted(self) -> InvertedLogTransform: ...

class InvertedLogTransform(Transform):
    input_dims: int
    output_dims: int
    base: float
    def __init__(self, base: float) -> None: ...
    def inverted(self) -> LogTransform: ...

class LogScale(ScaleBase):
    name: str
    subs: Iterable[int] | None
    def __init__(
        self,
        axis: Axis | None,
        *,
        base: float = ...,
        subs: Iterable[int] | None = ...,
        nonpositive: Literal["clip", "mask"] = ...
    ) -> None: ...
    @property
    def base(self) -> float: ...
    def get_transform(self) -> Transform: ...

class FuncScaleLog(LogScale):
    def __init__(
        self,
        axis: Axis | None,
        functions: tuple[
            Callable[[ArrayLike], ArrayLike], Callable[[ArrayLike], ArrayLike]
        ],
        base: float = ...,
    ) -> None: ...
    @property
    def base(self) -> float: ...
    def get_transform(self) -> Transform: ...

class SymmetricalLogTransform(Transform):
    input_dims: int
    output_dims: int
    base: float
    linthresh: float
    linscale: float
    def __init__(self, base: float, linthresh: float, linscale: float) -> None: ...
    def inverted(self) -> InvertedSymmetricalLogTransform: ...

class InvertedSymmetricalLogTransform(Transform):
    input_dims: int
    output_dims: int
    base: float
    linthresh: float
    invlinthresh: float
    linscale: float
    def __init__(self, base: float, linthresh: float, linscale: float) -> None: ...
    def inverted(self) -> SymmetricalLogTransform: ...

class SymmetricalLogScale(ScaleBase):
    name: str
    subs: Iterable[int] | None
    def __init__(
        self,
        axis: Axis | None,
        *,
        base: float = ...,
        linthresh: float = ...,
        subs: Iterable[int] | None = ...,
        linscale: float = ...
    ) -> None: ...
    @property
    def base(self) -> float: ...
    @property
    def linthresh(self) -> float: ...
    @property
    def linscale(self) -> float: ...
    def get_transform(self) -> SymmetricalLogTransform: ...

class AsinhTransform(Transform):
    input_dims: int
    output_dims: int
    linear_width: float
    def __init__(self, linear_width: float) -> None: ...
    def inverted(self) -> InvertedAsinhTransform: ...

class InvertedAsinhTransform(Transform):
    input_dims: int
    output_dims: int
    linear_width: float
    def __init__(self, linear_width: float) -> None: ...
    def inverted(self) -> AsinhTransform: ...

class AsinhScale(ScaleBase):
    name: str
    auto_tick_multipliers: dict[int, tuple[int, ...]]
    def __init__(
        self,
        axis: Axis | None,
        *,
        linear_width: float = ...,
        base: float = ...,
        subs: Iterable[int] | Literal["auto"] | None = ...,
        **kwargs
    ) -> None: ...
    @property
    def linear_width(self) -> float: ...
    def get_transform(self) -> AsinhTransform: ...

class LogitTransform(Transform):
    input_dims: int
    output_dims: int
    def __init__(self, nonpositive: Literal["mask", "clip"] = ...) -> None: ...
    def inverted(self) -> LogisticTransform: ...

class LogisticTransform(Transform):
    input_dims: int
    output_dims: int
    def __init__(self, nonpositive: Literal["mask", "clip"] = ...) -> None: ...
    def inverted(self) -> LogitTransform: ...

class LogitScale(ScaleBase):
    name: str
    def __init__(
        self,
        axis: Axis | None,
        nonpositive: Literal["mask", "clip"] = ...,
        *,
        one_half: str = ...,
        use_overline: bool = ...
    ) -> None: ...
    def get_transform(self) -> LogitTransform: ...

def get_scale_names() -> list[str]: ...
def scale_factory(scale: str, axis: Axis, **kwargs) -> ScaleBase: ...
def register_scale(scale_class: type[ScaleBase]) -> None: ...
