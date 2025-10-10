from typing import Any, Callable

from . import ImageFont, _imaging

class Font:
    @property
    def family(self) -> str | None: ...
    @property
    def style(self) -> str | None: ...
    @property
    def ascent(self) -> int: ...
    @property
    def descent(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def x_ppem(self) -> int: ...
    @property
    def y_ppem(self) -> int: ...
    @property
    def glyphs(self) -> int: ...
    def render(
        self,
        string: str | bytes,
        fill: Callable[[int, int], _imaging.ImagingCore],
        mode: str,
        dir: str | None,
        features: list[str] | None,
        lang: str | None,
        stroke_width: float,
        stroke_filled: bool,
        anchor: str | None,
        foreground_ink_long: int,
        start: tuple[float, float],
        /,
    ) -> tuple[_imaging.ImagingCore, tuple[int, int]]: ...
    def getsize(
        self,
        string: str | bytes | bytearray,
        mode: str,
        dir: str | None,
        features: list[str] | None,
        lang: str | None,
        anchor: str | None,
        /,
    ) -> tuple[tuple[int, int], tuple[int, int]]: ...
    def getlength(
        self,
        string: str | bytes,
        mode: str,
        dir: str | None,
        features: list[str] | None,
        lang: str | None,
        /,
    ) -> float: ...
    def getvarnames(self) -> list[bytes]: ...
    def getvaraxes(self) -> list[ImageFont.Axis]: ...
    def setvarname(self, instance_index: int, /) -> None: ...
    def setvaraxes(self, axes: list[float], /) -> None: ...

def getfont(
    filename: str | bytes,
    size: float,
    index: int,
    encoding: str,
    font_bytes: bytes,
    layout_engine: int,
) -> Font: ...
def __getattr__(name: str) -> Any: ...
