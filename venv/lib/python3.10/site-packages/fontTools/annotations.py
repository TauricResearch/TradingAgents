from __future__ import annotations
from typing import TYPE_CHECKING, Iterable, Optional, TypeVar, Union
from collections.abc import Callable, Sequence
from fontTools.misc.filesystem._base import FS
from os import PathLike
from xml.etree.ElementTree import Element as ElementTreeElement

if TYPE_CHECKING:
    from fontTools.ufoLib import UFOFormatVersion
    from fontTools.ufoLib.glifLib import GLIFFormatVersion
    from lxml.etree import _Element as LxmlElement


T = TypeVar("T")  # Generic type
K = TypeVar("K")  # Generic dict key type
V = TypeVar("V")  # Generic dict value type

GlyphNameToFileNameFunc = Optional[Callable[[str, set[str]], str]]
ElementType = Union[ElementTreeElement, "LxmlElement"]
FormatVersion = Union[int, tuple[int, int]]
FormatVersions = Optional[Iterable[FormatVersion]]
GLIFFormatVersionInput = Optional[Union[int, tuple[int, int], "GLIFFormatVersion"]]
UFOFormatVersionInput = Optional[Union[int, tuple[int, int], "UFOFormatVersion"]]
IntFloat = Union[int, float]
KerningPair = tuple[str, str]
KerningDict = dict[KerningPair, IntFloat]
KerningGroups = dict[str, Sequence[str]]
KerningNested = dict[str, dict[str, IntFloat]]
PathStr = Union[str, PathLike[str]]
PathOrFS = Union[PathStr, FS]
