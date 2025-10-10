from collections.abc import Callable, Sequence
from matplotlib.artist import Artist
from matplotlib.legend import Legend
from matplotlib.offsetbox import OffsetBox
from matplotlib.transforms import Transform

from typing import TypeVar

from numpy.typing import ArrayLike

def update_from_first_child(tgt: Artist, src: Artist) -> None: ...

class HandlerBase:
    def __init__(
        self,
        xpad: float = ...,
        ypad: float = ...,
        update_func: Callable[[Artist, Artist], None] | None = ...,
    ) -> None: ...
    def update_prop(
        self, legend_handle: Artist, orig_handle: Artist, legend: Legend
    ) -> None: ...
    def adjust_drawing_area(
        self,
        legend: Legend,
        orig_handle: Artist,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
    ) -> tuple[float, float, float, float]: ...
    def legend_artist(
        self, legend: Legend, orig_handle: Artist, fontsize: float, handlebox: OffsetBox
    ) -> Artist: ...
    def create_artists(
        self,
        legend: Legend,
        orig_handle: Artist,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
        trans: Transform,
    ) -> Sequence[Artist]: ...

class HandlerNpoints(HandlerBase):
    def __init__(
        self, marker_pad: float = ..., numpoints: int | None = ..., **kwargs
    ) -> None: ...
    def get_numpoints(self, legend: Legend) -> int | None: ...
    def get_xdata(
        self,
        legend: Legend,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
    ) -> tuple[ArrayLike, ArrayLike]: ...

class HandlerNpointsYoffsets(HandlerNpoints):
    def __init__(
        self,
        numpoints: int | None = ...,
        yoffsets: Sequence[float] | None = ...,
        **kwargs
    ) -> None: ...
    def get_ydata(
        self,
        legend: Legend,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
    ) -> ArrayLike: ...

class HandlerLine2DCompound(HandlerNpoints):
    def create_artists(
        self,
        legend: Legend,
        orig_handle: Artist,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
        trans: Transform,
    ) -> Sequence[Artist]: ...

class HandlerLine2D(HandlerNpoints):
    def create_artists(
        self,
        legend: Legend,
        orig_handle: Artist,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
        trans: Transform,
    ) -> Sequence[Artist]: ...

class HandlerPatch(HandlerBase):
    def __init__(self, patch_func: Callable | None = ..., **kwargs) -> None: ...
    def create_artists(
        self,
        legend: Legend,
        orig_handle: Artist,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
        trans: Transform,
    ) -> Sequence[Artist]: ...

class HandlerStepPatch(HandlerBase):
    def create_artists(
        self,
        legend: Legend,
        orig_handle: Artist,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
        trans: Transform,
    ) -> Sequence[Artist]: ...

class HandlerLineCollection(HandlerLine2D):
    def get_numpoints(self, legend: Legend) -> int: ...
    def create_artists(
        self,
        legend: Legend,
        orig_handle: Artist,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
        trans: Transform,
    ) -> Sequence[Artist]: ...

_T = TypeVar("_T", bound=Artist)

class HandlerRegularPolyCollection(HandlerNpointsYoffsets):
    def __init__(
        self,
        yoffsets: Sequence[float] | None = ...,
        sizes: Sequence[float] | None = ...,
        **kwargs
    ) -> None: ...
    def get_numpoints(self, legend: Legend) -> int: ...
    def get_sizes(
        self,
        legend: Legend,
        orig_handle: Artist,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
    ) -> Sequence[float]: ...
    def update_prop(
        self, legend_handle, orig_handle: Artist, legend: Legend
    ) -> None: ...
    def create_collection(
        self,
        orig_handle: _T,
        sizes: Sequence[float] | None,
        offsets: Sequence[float] | None,
        offset_transform: Transform,
    ) -> _T: ...
    def create_artists(
        self,
        legend: Legend,
        orig_handle: Artist,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
        trans: Transform,
    ) -> Sequence[Artist]: ...

class HandlerPathCollection(HandlerRegularPolyCollection):
    def create_collection(
        self,
        orig_handle: _T,
        sizes: Sequence[float] | None,
        offsets: Sequence[float] | None,
        offset_transform: Transform,
    ) -> _T: ...

class HandlerCircleCollection(HandlerRegularPolyCollection):
    def create_collection(
        self,
        orig_handle: _T,
        sizes: Sequence[float] | None,
        offsets: Sequence[float] | None,
        offset_transform: Transform,
    ) -> _T: ...

class HandlerErrorbar(HandlerLine2D):
    def __init__(
        self,
        xerr_size: float = ...,
        yerr_size: float | None = ...,
        marker_pad: float = ...,
        numpoints: int | None = ...,
        **kwargs
    ) -> None: ...
    def get_err_size(
        self,
        legend: Legend,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
    ) -> tuple[float, float]: ...
    def create_artists(
        self,
        legend: Legend,
        orig_handle: Artist,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
        trans: Transform,
    ) -> Sequence[Artist]: ...

class HandlerStem(HandlerNpointsYoffsets):
    def __init__(
        self,
        marker_pad: float = ...,
        numpoints: int | None = ...,
        bottom: float | None = ...,
        yoffsets: Sequence[float] | None = ...,
        **kwargs
    ) -> None: ...
    def get_ydata(
        self,
        legend: Legend,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
    ) -> ArrayLike: ...
    def create_artists(
        self,
        legend: Legend,
        orig_handle: Artist,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
        trans: Transform,
    ) -> Sequence[Artist]: ...

class HandlerTuple(HandlerBase):
    def __init__(
        self, ndivide: int | None = ..., pad: float | None = ..., **kwargs
    ) -> None: ...
    def create_artists(
        self,
        legend: Legend,
        orig_handle: Artist,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
        trans: Transform,
    ) -> Sequence[Artist]: ...

class HandlerPolyCollection(HandlerBase):
    def create_artists(
        self,
        legend: Legend,
        orig_handle: Artist,
        xdescent: float,
        ydescent: float,
        width: float,
        height: float,
        fontsize: float,
        trans: Transform,
    ) -> Sequence[Artist]: ...
