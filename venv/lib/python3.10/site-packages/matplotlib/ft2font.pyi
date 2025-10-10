from enum import Enum, Flag
import sys
from typing import BinaryIO, Literal, TypedDict, final, overload, cast
from typing_extensions import Buffer  # < Py 3.12

import numpy as np
from numpy.typing import NDArray

__freetype_build_type__: str
__freetype_version__: str

class FaceFlags(Flag):
    SCALABLE = cast(int, ...)
    FIXED_SIZES = cast(int, ...)
    FIXED_WIDTH = cast(int, ...)
    SFNT = cast(int, ...)
    HORIZONTAL = cast(int, ...)
    VERTICAL = cast(int, ...)
    KERNING = cast(int, ...)
    FAST_GLYPHS = cast(int, ...)
    MULTIPLE_MASTERS = cast(int, ...)
    GLYPH_NAMES = cast(int, ...)
    EXTERNAL_STREAM = cast(int, ...)
    HINTER = cast(int, ...)
    CID_KEYED = cast(int, ...)
    TRICKY = cast(int, ...)
    COLOR = cast(int, ...)
    # VARIATION = cast(int, ...)  # FT 2.9
    # SVG = cast(int, ...)  # FT 2.12
    # SBIX = cast(int, ...)  # FT 2.12
    # SBIX_OVERLAY = cast(int, ...)  # FT 2.12

class Kerning(Enum):
    DEFAULT = cast(int, ...)
    UNFITTED = cast(int, ...)
    UNSCALED = cast(int, ...)

class LoadFlags(Flag):
    DEFAULT = cast(int, ...)
    NO_SCALE = cast(int, ...)
    NO_HINTING = cast(int, ...)
    RENDER = cast(int, ...)
    NO_BITMAP = cast(int, ...)
    VERTICAL_LAYOUT = cast(int, ...)
    FORCE_AUTOHINT = cast(int, ...)
    CROP_BITMAP = cast(int, ...)
    PEDANTIC = cast(int, ...)
    IGNORE_GLOBAL_ADVANCE_WIDTH = cast(int, ...)
    NO_RECURSE = cast(int, ...)
    IGNORE_TRANSFORM = cast(int, ...)
    MONOCHROME = cast(int, ...)
    LINEAR_DESIGN = cast(int, ...)
    NO_AUTOHINT = cast(int, ...)
    COLOR = cast(int, ...)
    COMPUTE_METRICS = cast(int, ...)  # FT 2.6.1
    # BITMAP_METRICS_ONLY = cast(int, ...)  # FT 2.7.1
    # NO_SVG = cast(int, ...)  # FT 2.13.1
    # The following should be unique, but the above can be OR'd together.
    TARGET_NORMAL = cast(int, ...)
    TARGET_LIGHT = cast(int, ...)
    TARGET_MONO = cast(int, ...)
    TARGET_LCD = cast(int, ...)
    TARGET_LCD_V = cast(int, ...)

class StyleFlags(Flag):
    NORMAL = cast(int, ...)
    ITALIC = cast(int, ...)
    BOLD = cast(int, ...)

class _SfntHeadDict(TypedDict):
    version: tuple[int, int]
    fontRevision: tuple[int, int]
    checkSumAdjustment: int
    magicNumber: int
    flags: int
    unitsPerEm: int
    created: tuple[int, int]
    modified: tuple[int, int]
    xMin: int
    yMin: int
    xMax: int
    yMax: int
    macStyle: int
    lowestRecPPEM: int
    fontDirectionHint: int
    indexToLocFormat: int
    glyphDataFormat: int

class _SfntMaxpDict(TypedDict):
    version: tuple[int, int]
    numGlyphs: int
    maxPoints: int
    maxContours: int
    maxComponentPoints: int
    maxComponentContours: int
    maxZones: int
    maxTwilightPoints: int
    maxStorage: int
    maxFunctionDefs: int
    maxInstructionDefs: int
    maxStackElements: int
    maxSizeOfInstructions: int
    maxComponentElements: int
    maxComponentDepth: int

class _SfntOs2Dict(TypedDict):
    version: int
    xAvgCharWidth: int
    usWeightClass: int
    usWidthClass: int
    fsType: int
    ySubscriptXSize: int
    ySubscriptYSize: int
    ySubscriptXOffset: int
    ySubscriptYOffset: int
    ySuperscriptXSize: int
    ySuperscriptYSize: int
    ySuperscriptXOffset: int
    ySuperscriptYOffset: int
    yStrikeoutSize: int
    yStrikeoutPosition: int
    sFamilyClass: int
    panose: bytes
    ulCharRange: tuple[int, int, int, int]
    achVendID: bytes
    fsSelection: int
    fsFirstCharIndex: int
    fsLastCharIndex: int

class _SfntHheaDict(TypedDict):
    version: tuple[int, int]
    ascent: int
    descent: int
    lineGap: int
    advanceWidthMax: int
    minLeftBearing: int
    minRightBearing: int
    xMaxExtent: int
    caretSlopeRise: int
    caretSlopeRun: int
    caretOffset: int
    metricDataFormat: int
    numOfLongHorMetrics: int

class _SfntVheaDict(TypedDict):
    version: tuple[int, int]
    vertTypoAscender: int
    vertTypoDescender: int
    vertTypoLineGap: int
    advanceHeightMax: int
    minTopSideBearing: int
    minBottomSizeBearing: int
    yMaxExtent: int
    caretSlopeRise: int
    caretSlopeRun: int
    caretOffset: int
    metricDataFormat: int
    numOfLongVerMetrics: int

class _SfntPostDict(TypedDict):
    format: tuple[int, int]
    italicAngle: tuple[int, int]
    underlinePosition: int
    underlineThickness: int
    isFixedPitch: int
    minMemType42: int
    maxMemType42: int
    minMemType1: int
    maxMemType1: int

class _SfntPcltDict(TypedDict):
    version: tuple[int, int]
    fontNumber: int
    pitch: int
    xHeight: int
    style: int
    typeFamily: int
    capHeight: int
    symbolSet: int
    typeFace: bytes
    characterComplement: bytes
    strokeWeight: int
    widthType: int
    serifStyle: int

@final
class FT2Font(Buffer):
    def __init__(
        self,
        filename: str | BinaryIO,
        hinting_factor: int = ...,
        *,
        _fallback_list: list[FT2Font] | None = ...,
        _kerning_factor: int = ...
    ) -> None: ...
    if sys.version_info[:2] >= (3, 12):
        def __buffer__(self, flags: int) -> memoryview: ...
    def _get_fontmap(self, string: str) -> dict[str, FT2Font]: ...
    def clear(self) -> None: ...
    def draw_glyph_to_bitmap(
        self, image: FT2Image, x: int, y: int, glyph: Glyph, antialiased: bool = ...
    ) -> None: ...
    def draw_glyphs_to_bitmap(self, antialiased: bool = ...) -> None: ...
    def get_bitmap_offset(self) -> tuple[int, int]: ...
    def get_char_index(self, codepoint: int) -> int: ...
    def get_charmap(self) -> dict[int, int]: ...
    def get_descent(self) -> int: ...
    def get_glyph_name(self, index: int) -> str: ...
    def get_image(self) -> NDArray[np.uint8]: ...
    def get_kerning(self, left: int, right: int, mode: Kerning) -> int: ...
    def get_name_index(self, name: str) -> int: ...
    def get_num_glyphs(self) -> int: ...
    def get_path(self) -> tuple[NDArray[np.float64], NDArray[np.int8]]: ...
    def get_ps_font_info(
        self,
    ) -> tuple[str, str, str, str, str, int, int, int, int]: ...
    def get_sfnt(self) -> dict[tuple[int, int, int, int], bytes]: ...
    @overload
    def get_sfnt_table(self, name: Literal["head"]) -> _SfntHeadDict | None: ...
    @overload
    def get_sfnt_table(self, name: Literal["maxp"]) -> _SfntMaxpDict | None: ...
    @overload
    def get_sfnt_table(self, name: Literal["OS/2"]) -> _SfntOs2Dict | None: ...
    @overload
    def get_sfnt_table(self, name: Literal["hhea"]) -> _SfntHheaDict | None: ...
    @overload
    def get_sfnt_table(self, name: Literal["vhea"]) -> _SfntVheaDict | None: ...
    @overload
    def get_sfnt_table(self, name: Literal["post"]) -> _SfntPostDict | None: ...
    @overload
    def get_sfnt_table(self, name: Literal["pclt"]) -> _SfntPcltDict | None: ...
    def get_width_height(self) -> tuple[int, int]: ...
    def load_char(self, charcode: int, flags: LoadFlags = ...) -> Glyph: ...
    def load_glyph(self, glyphindex: int, flags: LoadFlags = ...) -> Glyph: ...
    def select_charmap(self, i: int) -> None: ...
    def set_charmap(self, i: int) -> None: ...
    def set_size(self, ptsize: float, dpi: float) -> None: ...
    def set_text(
        self, string: str, angle: float = ..., flags: LoadFlags = ...
    ) -> NDArray[np.float64]: ...
    @property
    def ascender(self) -> int: ...
    @property
    def bbox(self) -> tuple[int, int, int, int]: ...
    @property
    def descender(self) -> int: ...
    @property
    def face_flags(self) -> FaceFlags: ...
    @property
    def family_name(self) -> str: ...
    @property
    def fname(self) -> str: ...
    @property
    def height(self) -> int: ...
    @property
    def max_advance_height(self) -> int: ...
    @property
    def max_advance_width(self) -> int: ...
    @property
    def num_charmaps(self) -> int: ...
    @property
    def num_faces(self) -> int: ...
    @property
    def num_fixed_sizes(self) -> int: ...
    @property
    def num_glyphs(self) -> int: ...
    @property
    def num_named_instances(self) -> int: ...
    @property
    def postscript_name(self) -> str: ...
    @property
    def scalable(self) -> bool: ...
    @property
    def style_flags(self) -> StyleFlags: ...
    @property
    def style_name(self) -> str: ...
    @property
    def underline_position(self) -> int: ...
    @property
    def underline_thickness(self) -> int: ...
    @property
    def units_per_EM(self) -> int: ...

@final
class FT2Image(Buffer):
    def __init__(self, width: int, height: int) -> None: ...
    def draw_rect_filled(self, x0: int, y0: int, x1: int, y1: int) -> None: ...
    if sys.version_info[:2] >= (3, 12):
        def __buffer__(self, flags: int) -> memoryview: ...

@final
class Glyph:
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def horiBearingX(self) -> int: ...
    @property
    def horiBearingY(self) -> int: ...
    @property
    def horiAdvance(self) -> int: ...
    @property
    def linearHoriAdvance(self) -> int: ...
    @property
    def vertBearingX(self) -> int: ...
    @property
    def vertBearingY(self) -> int: ...
    @property
    def vertAdvance(self) -> int: ...
    @property
    def bbox(self) -> tuple[int, int, int, int]: ...
