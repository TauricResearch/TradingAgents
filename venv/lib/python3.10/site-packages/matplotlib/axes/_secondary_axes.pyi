from matplotlib.axes._base import _AxesBase
from matplotlib.axis import Tick

from matplotlib.transforms import Transform

from collections.abc import Callable, Iterable
from typing import Literal
from numpy.typing import ArrayLike
from matplotlib.typing import ColorType

class SecondaryAxis(_AxesBase):
    def __init__(
        self,
        parent: _AxesBase,
        orientation: Literal["x", "y"],
        location: Literal["top", "bottom", "right", "left"] | float,
        functions: tuple[
            Callable[[ArrayLike], ArrayLike], Callable[[ArrayLike], ArrayLike]
        ]
        | Transform,
        transform: Transform | None = ...,
        **kwargs
    ) -> None: ...
    def set_alignment(
        self, align: Literal["top", "bottom", "right", "left"]
    ) -> None: ...
    def set_location(
        self,
        location: Literal["top", "bottom", "right", "left"] | float,
        transform: Transform | None = ...
    ) -> None: ...
    def set_ticks(
        self,
        ticks: ArrayLike,
        labels: Iterable[str] | None = ...,
        *,
        minor: bool = ...,
        **kwargs
    ) -> list[Tick]: ...
    def set_functions(
        self,
        functions: tuple[Callable[[ArrayLike], ArrayLike], Callable[[ArrayLike], ArrayLike]] | Transform,
    ) -> None: ...
    def set_aspect(self, *args, **kwargs) -> None: ...
    def set_color(self, color: ColorType) -> None: ...
