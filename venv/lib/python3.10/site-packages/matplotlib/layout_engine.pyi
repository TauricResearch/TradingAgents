from matplotlib.figure import Figure

from typing import Any

class LayoutEngine:
    def __init__(self, **kwargs: Any) -> None: ...
    def set(self) -> None: ...
    @property
    def colorbar_gridspec(self) -> bool: ...
    @property
    def adjust_compatible(self) -> bool: ...
    def get(self) -> dict[str, Any]: ...
    def execute(self, fig: Figure) -> None: ...

class PlaceHolderLayoutEngine(LayoutEngine):
    def __init__(
        self, adjust_compatible: bool, colorbar_gridspec: bool, **kwargs: Any
    ) -> None: ...
    def execute(self, fig: Figure) -> None: ...

class TightLayoutEngine(LayoutEngine):
    def __init__(
        self,
        *,
        pad: float = ...,
        h_pad: float | None = ...,
        w_pad: float | None = ...,
        rect: tuple[float, float, float, float] = ...,
        **kwargs: Any
    ) -> None: ...
    def execute(self, fig: Figure) -> None: ...
    def set(
        self,
        *,
        pad: float | None = ...,
        w_pad: float | None = ...,
        h_pad: float | None = ...,
        rect: tuple[float, float, float, float] | None = ...
    ) -> None: ...

class ConstrainedLayoutEngine(LayoutEngine):
    def __init__(
        self,
        *,
        h_pad: float | None = ...,
        w_pad: float | None = ...,
        hspace: float | None = ...,
        wspace: float | None = ...,
        rect: tuple[float, float, float, float] = ...,
        compress: bool = ...,
        **kwargs: Any
    ) -> None: ...
    def execute(self, fig: Figure) -> Any: ...
    def set(
        self,
        *,
        h_pad: float | None = ...,
        w_pad: float | None = ...,
        hspace: float | None = ...,
        wspace: float | None = ...,
        rect: tuple[float, float, float, float] | None = ...
    ) -> None: ...
