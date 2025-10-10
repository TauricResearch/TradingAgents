from pathlib import Path
import io
import os
from enum import Enum
from collections.abc import Generator

from typing import NamedTuple
from typing_extensions import Self  # < Py 3.11

class _dvistate(Enum):
    pre = ...
    outer = ...
    inpage = ...
    post_post = ...
    finale = ...

class Page(NamedTuple):
    text: list[Text]
    boxes: list[Box]
    height: int
    width: int
    descent: int

class Box(NamedTuple):
    x: int
    y: int
    height: int
    width: int

class Text(NamedTuple):
    x: int
    y: int
    font: DviFont
    glyph: int
    width: int
    @property
    def font_path(self) -> Path: ...
    @property
    def font_size(self) -> float: ...
    @property
    def font_effects(self) -> dict[str, float]: ...
    @property
    def glyph_name_or_index(self) -> int | str: ...

class Dvi:
    file: io.BufferedReader
    dpi: float | None
    fonts: dict[int, DviFont]
    state: _dvistate
    def __init__(self, filename: str | os.PathLike, dpi: float | None) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, etype, evalue, etrace) -> None: ...
    def __iter__(self) -> Generator[Page, None, None]: ...
    def close(self) -> None: ...

class DviFont:
    texname: bytes
    size: float
    widths: list[int]
    def __init__(
        self, scale: float, tfm: Tfm, texname: bytes, vf: Vf | None
    ) -> None: ...
    def __eq__(self, other: object) -> bool: ...
    def __ne__(self, other: object) -> bool: ...

class Vf(Dvi):
    def __init__(self, filename: str | os.PathLike) -> None: ...
    def __getitem__(self, code: int) -> Page: ...

class Tfm:
    checksum: int
    design_size: int
    width: dict[int, int]
    height: dict[int, int]
    depth: dict[int, int]
    def __init__(self, filename: str | os.PathLike) -> None: ...

class PsFont(NamedTuple):
    texname: bytes
    psname: bytes
    effects: dict[str, float]
    encoding: None | bytes
    filename: str

class PsfontsMap:
    def __new__(cls, filename: str | os.PathLike) -> Self: ...
    def __getitem__(self, texname: bytes) -> PsFont: ...

def find_tex_file(filename: str | os.PathLike) -> str: ...
