"""
Implementation details for :mod:`.mathtext`.
"""

from __future__ import annotations

import abc
import copy
import enum
import functools
import logging
import os
import re
import types
import unicodedata
import string
import typing as T
from typing import NamedTuple

import numpy as np
from pyparsing import (
    Empty, Forward, Literal, Group, NotAny, OneOrMore, Optional,
    ParseBaseException, ParseException, ParseExpression, ParseFatalException,
    ParserElement, ParseResults, QuotedString, Regex, StringEnd, ZeroOrMore,
    pyparsing_common, nested_expr, one_of)

import matplotlib as mpl
from . import cbook
from ._mathtext_data import (
    latex_to_bakoma, stix_glyph_fixes, stix_virtual_fonts, tex2uni)
from .font_manager import FontProperties, findfont, get_font
from .ft2font import FT2Font, FT2Image, Kerning, LoadFlags


if T.TYPE_CHECKING:
    from collections.abc import Iterable
    from .ft2font import Glyph

ParserElement.enable_packrat()
_log = logging.getLogger("matplotlib.mathtext")


##############################################################################
# FONTS


def get_unicode_index(symbol: str) -> int:  # Publicly exported.
    r"""
    Return the integer index (from the Unicode table) of *symbol*.

    Parameters
    ----------
    symbol : str
        A single (Unicode) character, a TeX command (e.g. r'\pi') or a Type1
        symbol name (e.g. 'phi').
    """
    try:  # This will succeed if symbol is a single Unicode char
        return ord(symbol)
    except TypeError:
        pass
    try:  # Is symbol a TeX symbol (i.e. \alpha)
        return tex2uni[symbol.strip("\\")]
    except KeyError as err:
        raise ValueError(
            f"{symbol!r} is not a valid Unicode character or TeX/Type1 symbol"
            ) from err


class VectorParse(NamedTuple):
    """
    The namedtuple type returned by ``MathTextParser("path").parse(...)``.

    Attributes
    ----------
    width, height, depth : float
        The global metrics.
    glyphs : list
        The glyphs including their positions.
    rect : list
        The list of rectangles.
    """
    width: float
    height: float
    depth: float
    glyphs: list[tuple[FT2Font, float, int, float, float]]
    rects: list[tuple[float, float, float, float]]

VectorParse.__module__ = "matplotlib.mathtext"


class RasterParse(NamedTuple):
    """
    The namedtuple type returned by ``MathTextParser("agg").parse(...)``.

    Attributes
    ----------
    ox, oy : float
        The offsets are always zero.
    width, height, depth : float
        The global metrics.
    image : FT2Image
        A raster image.
    """
    ox: float
    oy: float
    width: float
    height: float
    depth: float
    image: FT2Image

RasterParse.__module__ = "matplotlib.mathtext"


class Output:
    r"""
    Result of `ship`\ping a box: lists of positioned glyphs and rectangles.

    This class is not exposed to end users, but converted to a `VectorParse` or
    a `RasterParse` by `.MathTextParser.parse`.
    """

    def __init__(self, box: Box):
        self.box = box
        self.glyphs: list[tuple[float, float, FontInfo]] = []  # (ox, oy, info)
        self.rects: list[tuple[float, float, float, float]] = []  # (x1, y1, x2, y2)

    def to_vector(self) -> VectorParse:
        w, h, d = map(
            np.ceil, [self.box.width, self.box.height, self.box.depth])
        gs = [(info.font, info.fontsize, info.num, ox, h - oy + info.offset)
              for ox, oy, info in self.glyphs]
        rs = [(x1, h - y2, x2 - x1, y2 - y1)
              for x1, y1, x2, y2 in self.rects]
        return VectorParse(w, h + d, d, gs, rs)

    def to_raster(self, *, antialiased: bool) -> RasterParse:
        # Metrics y's and mathtext y's are oriented in opposite directions,
        # hence the switch between ymin and ymax.
        xmin = min([*[ox + info.metrics.xmin for ox, oy, info in self.glyphs],
                    *[x1 for x1, y1, x2, y2 in self.rects], 0]) - 1
        ymin = min([*[oy - info.metrics.ymax for ox, oy, info in self.glyphs],
                    *[y1 for x1, y1, x2, y2 in self.rects], 0]) - 1
        xmax = max([*[ox + info.metrics.xmax for ox, oy, info in self.glyphs],
                    *[x2 for x1, y1, x2, y2 in self.rects], 0]) + 1
        ymax = max([*[oy - info.metrics.ymin for ox, oy, info in self.glyphs],
                    *[y2 for x1, y1, x2, y2 in self.rects], 0]) + 1
        w = xmax - xmin
        h = ymax - ymin - self.box.depth
        d = ymax - ymin - self.box.height
        image = FT2Image(int(np.ceil(w)), int(np.ceil(h + max(d, 0))))

        # Ideally, we could just use self.glyphs and self.rects here, shifting
        # their coordinates by (-xmin, -ymin), but this yields slightly
        # different results due to floating point slop; shipping twice is the
        # old approach and keeps baseline images backcompat.
        shifted = ship(self.box, (-xmin, -ymin))

        for ox, oy, info in shifted.glyphs:
            info.font.draw_glyph_to_bitmap(
                image, int(ox), int(oy - info.metrics.iceberg), info.glyph,
                antialiased=antialiased)
        for x1, y1, x2, y2 in shifted.rects:
            height = max(int(y2 - y1) - 1, 0)
            if height == 0:
                center = (y2 + y1) / 2
                y = int(center - (height + 1) / 2)
            else:
                y = int(y1)
            image.draw_rect_filled(int(x1), y, int(np.ceil(x2)), y + height)
        return RasterParse(0, 0, w, h + d, d, image)


class FontMetrics(NamedTuple):
    """
    Metrics of a font.

    Attributes
    ----------
    advance : float
        The advance distance (in points) of the glyph.
    height : float
        The height of the glyph in points.
    width : float
        The width of the glyph in points.
    xmin, xmax, ymin, ymax : float
        The ink rectangle of the glyph.
    iceberg : float
        The distance from the baseline to the top of the glyph. (This corresponds to
        TeX's definition of "height".)
    slanted : bool
        Whether the glyph should be considered as "slanted" (currently used for kerning
        sub/superscripts).
    """
    advance: float
    height: float
    width: float
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    iceberg: float
    slanted: bool


class FontInfo(NamedTuple):
    font: FT2Font
    fontsize: float
    postscript_name: str
    metrics: FontMetrics
    num: int
    glyph: Glyph
    offset: float


class Fonts(abc.ABC):
    """
    An abstract base class for a system of fonts to use for mathtext.

    The class must be able to take symbol keys and font file names and
    return the character metrics.  It also delegates to a backend class
    to do the actual drawing.
    """

    def __init__(self, default_font_prop: FontProperties, load_glyph_flags: LoadFlags):
        """
        Parameters
        ----------
        default_font_prop : `~.font_manager.FontProperties`
            The default non-math font, or the base font for Unicode (generic)
            font rendering.
        load_glyph_flags : `.ft2font.LoadFlags`
            Flags passed to the glyph loader (e.g. ``FT_Load_Glyph`` and
            ``FT_Load_Char`` for FreeType-based fonts).
        """
        self.default_font_prop = default_font_prop
        self.load_glyph_flags = load_glyph_flags

    def get_kern(self, font1: str, fontclass1: str, sym1: str, fontsize1: float,
                 font2: str, fontclass2: str, sym2: str, fontsize2: float,
                 dpi: float) -> float:
        """
        Get the kerning distance for font between *sym1* and *sym2*.

        See `~.Fonts.get_metrics` for a detailed description of the parameters.
        """
        return 0.

    def _get_font(self, font: str) -> FT2Font:
        raise NotImplementedError

    def _get_info(self, font: str, font_class: str, sym: str, fontsize: float,
                  dpi: float) -> FontInfo:
        raise NotImplementedError

    def get_metrics(self, font: str, font_class: str, sym: str, fontsize: float,
                    dpi: float) -> FontMetrics:
        r"""
        Parameters
        ----------
        font : str
            One of the TeX font names: "tt", "it", "rm", "cal", "sf", "bf",
            "default", "regular", "bb", "frak", "scr".  "default" and "regular"
            are synonyms and use the non-math font.
        font_class : str
            One of the TeX font names (as for *font*), but **not** "bb",
            "frak", or "scr".  This is used to combine two font classes.  The
            only supported combination currently is ``get_metrics("frak", "bf",
            ...)``.
        sym : str
            A symbol in raw TeX form, e.g., "1", "x", or "\sigma".
        fontsize : float
            Font size in points.
        dpi : float
            Rendering dots-per-inch.

        Returns
        -------
        FontMetrics
        """
        info = self._get_info(font, font_class, sym, fontsize, dpi)
        return info.metrics

    def render_glyph(self, output: Output, ox: float, oy: float, font: str,
                     font_class: str, sym: str, fontsize: float, dpi: float) -> None:
        """
        At position (*ox*, *oy*), draw the glyph specified by the remaining
        parameters (see `get_metrics` for their detailed description).
        """
        info = self._get_info(font, font_class, sym, fontsize, dpi)
        output.glyphs.append((ox, oy, info))

    def render_rect_filled(self, output: Output,
                           x1: float, y1: float, x2: float, y2: float) -> None:
        """
        Draw a filled rectangle from (*x1*, *y1*) to (*x2*, *y2*).
        """
        output.rects.append((x1, y1, x2, y2))

    def get_xheight(self, font: str, fontsize: float, dpi: float) -> float:
        """
        Get the xheight for the given *font* and *fontsize*.
        """
        raise NotImplementedError()

    def get_underline_thickness(self, font: str, fontsize: float, dpi: float) -> float:
        """
        Get the line thickness that matches the given font.  Used as a
        base unit for drawing lines such as in a fraction or radical.
        """
        raise NotImplementedError()

    def get_sized_alternatives_for_symbol(self, fontname: str,
                                          sym: str) -> list[tuple[str, str]]:
        """
        Override if your font provides multiple sizes of the same
        symbol.  Should return a list of symbols matching *sym* in
        various sizes.  The expression renderer will select the most
        appropriate size for a given situation from this list.
        """
        return [(fontname, sym)]


class TruetypeFonts(Fonts, metaclass=abc.ABCMeta):
    """
    A generic base class for all font setups that use Truetype fonts
    (through FT2Font).
    """

    def __init__(self, default_font_prop: FontProperties, load_glyph_flags: LoadFlags):
        super().__init__(default_font_prop, load_glyph_flags)
        # Per-instance cache.
        self._get_info = functools.cache(self._get_info)  # type: ignore[method-assign]
        self._fonts = {}
        self.fontmap: dict[str | int, str] = {}

        filename = findfont(self.default_font_prop)
        default_font = get_font(filename)
        self._fonts['default'] = default_font
        self._fonts['regular'] = default_font

    def _get_font(self, font: str | int) -> FT2Font:
        if font in self.fontmap:
            basename = self.fontmap[font]
        else:
            # NOTE: An int is only passed by subclasses which have placed int keys into
            # `self.fontmap`, so we must cast this to confirm it to typing.
            basename = T.cast(str, font)
        cached_font = self._fonts.get(basename)
        if cached_font is None and os.path.exists(basename):
            cached_font = get_font(basename)
            self._fonts[basename] = cached_font
            self._fonts[cached_font.postscript_name] = cached_font
            self._fonts[cached_font.postscript_name.lower()] = cached_font
        return T.cast(FT2Font, cached_font)  # FIXME: Not sure this is guaranteed.

    def _get_offset(self, font: FT2Font, glyph: Glyph, fontsize: float,
                    dpi: float) -> float:
        if font.postscript_name == 'Cmex10':
            return (glyph.height / 64 / 2) + (fontsize/3 * dpi/72)
        return 0.

    def _get_glyph(self, fontname: str, font_class: str,
                   sym: str) -> tuple[FT2Font, int, bool]:
        raise NotImplementedError

    # The return value of _get_info is cached per-instance.
    def _get_info(self, fontname: str, font_class: str, sym: str, fontsize: float,
                  dpi: float) -> FontInfo:
        font, num, slanted = self._get_glyph(fontname, font_class, sym)
        font.set_size(fontsize, dpi)
        glyph = font.load_char(num, flags=self.load_glyph_flags)

        xmin, ymin, xmax, ymax = (val / 64 for val in glyph.bbox)
        offset = self._get_offset(font, glyph, fontsize, dpi)
        metrics = FontMetrics(
            advance=glyph.linearHoriAdvance / 65536,
            height=glyph.height / 64,
            width=glyph.width / 64,
            xmin=xmin,
            xmax=xmax,
            ymin=ymin + offset,
            ymax=ymax + offset,
            # iceberg is the equivalent of TeX's "height"
            iceberg=glyph.horiBearingY / 64 + offset,
            slanted=slanted
        )

        return FontInfo(
            font=font,
            fontsize=fontsize,
            postscript_name=font.postscript_name,
            metrics=metrics,
            num=num,
            glyph=glyph,
            offset=offset
        )

    def get_xheight(self, fontname: str, fontsize: float, dpi: float) -> float:
        font = self._get_font(fontname)
        font.set_size(fontsize, dpi)
        pclt = font.get_sfnt_table('pclt')
        if pclt is None:
            # Some fonts don't store the xHeight, so we do a poor man's xHeight
            metrics = self.get_metrics(
                fontname, mpl.rcParams['mathtext.default'], 'x', fontsize, dpi)
            return metrics.iceberg
        xHeight = (pclt['xHeight'] / 64.0) * (fontsize / 12.0) * (dpi / 100.0)
        return xHeight

    def get_underline_thickness(self, font: str, fontsize: float, dpi: float) -> float:
        # This function used to grab underline thickness from the font
        # metrics, but that information is just too un-reliable, so it
        # is now hardcoded.
        return ((0.75 / 12.0) * fontsize * dpi) / 72.0

    def get_kern(self, font1: str, fontclass1: str, sym1: str, fontsize1: float,
                 font2: str, fontclass2: str, sym2: str, fontsize2: float,
                 dpi: float) -> float:
        if font1 == font2 and fontsize1 == fontsize2:
            info1 = self._get_info(font1, fontclass1, sym1, fontsize1, dpi)
            info2 = self._get_info(font2, fontclass2, sym2, fontsize2, dpi)
            font = info1.font
            return font.get_kerning(info1.num, info2.num, Kerning.DEFAULT) / 64
        return super().get_kern(font1, fontclass1, sym1, fontsize1,
                                font2, fontclass2, sym2, fontsize2, dpi)


class BakomaFonts(TruetypeFonts):
    """
    Use the Bakoma TrueType fonts for rendering.

    Symbols are strewn about a number of font files, each of which has
    its own proprietary 8-bit encoding.
    """
    _fontmap = {
        'cal': 'cmsy10',
        'rm':  'cmr10',
        'tt':  'cmtt10',
        'it':  'cmmi10',
        'bf':  'cmb10',
        'sf':  'cmss10',
        'ex':  'cmex10',
    }

    def __init__(self, default_font_prop: FontProperties, load_glyph_flags: LoadFlags):
        self._stix_fallback = StixFonts(default_font_prop, load_glyph_flags)

        super().__init__(default_font_prop, load_glyph_flags)
        for key, val in self._fontmap.items():
            fullpath = findfont(val)
            self.fontmap[key] = fullpath
            self.fontmap[val] = fullpath

    _slanted_symbols = set(r"\int \oint".split())

    def _get_glyph(self, fontname: str, font_class: str,
                   sym: str) -> tuple[FT2Font, int, bool]:
        font = None
        if fontname in self.fontmap and sym in latex_to_bakoma:
            basename, num = latex_to_bakoma[sym]
            slanted = (basename == "cmmi10") or sym in self._slanted_symbols
            font = self._get_font(basename)
        elif len(sym) == 1:
            slanted = (fontname == "it")
            font = self._get_font(fontname)
            if font is not None:
                num = ord(sym)
        if font is not None and font.get_char_index(num) != 0:
            return font, num, slanted
        else:
            return self._stix_fallback._get_glyph(fontname, font_class, sym)

    # The Bakoma fonts contain many pre-sized alternatives for the
    # delimiters.  The AutoSizedChar class will use these alternatives
    # and select the best (closest sized) glyph.
    _size_alternatives = {
        '(':           [('rm', '('), ('ex', '\xa1'), ('ex', '\xb3'),
                        ('ex', '\xb5'), ('ex', '\xc3')],
        ')':           [('rm', ')'), ('ex', '\xa2'), ('ex', '\xb4'),
                        ('ex', '\xb6'), ('ex', '\x21')],
        '{':           [('cal', '{'), ('ex', '\xa9'), ('ex', '\x6e'),
                        ('ex', '\xbd'), ('ex', '\x28')],
        '}':           [('cal', '}'), ('ex', '\xaa'), ('ex', '\x6f'),
                        ('ex', '\xbe'), ('ex', '\x29')],
        # The fourth size of '[' is mysteriously missing from the BaKoMa
        # font, so I've omitted it for both '[' and ']'
        '[':           [('rm', '['), ('ex', '\xa3'), ('ex', '\x68'),
                        ('ex', '\x22')],
        ']':           [('rm', ']'), ('ex', '\xa4'), ('ex', '\x69'),
                        ('ex', '\x23')],
        r'\lfloor':    [('ex', '\xa5'), ('ex', '\x6a'),
                        ('ex', '\xb9'), ('ex', '\x24')],
        r'\rfloor':    [('ex', '\xa6'), ('ex', '\x6b'),
                        ('ex', '\xba'), ('ex', '\x25')],
        r'\lceil':     [('ex', '\xa7'), ('ex', '\x6c'),
                        ('ex', '\xbb'), ('ex', '\x26')],
        r'\rceil':     [('ex', '\xa8'), ('ex', '\x6d'),
                        ('ex', '\xbc'), ('ex', '\x27')],
        r'\langle':    [('ex', '\xad'), ('ex', '\x44'),
                        ('ex', '\xbf'), ('ex', '\x2a')],
        r'\rangle':    [('ex', '\xae'), ('ex', '\x45'),
                        ('ex', '\xc0'), ('ex', '\x2b')],
        r'\__sqrt__':  [('ex', '\x70'), ('ex', '\x71'),
                        ('ex', '\x72'), ('ex', '\x73')],
        r'\backslash': [('ex', '\xb2'), ('ex', '\x2f'),
                        ('ex', '\xc2'), ('ex', '\x2d')],
        r'/':          [('rm', '/'), ('ex', '\xb1'), ('ex', '\x2e'),
                        ('ex', '\xcb'), ('ex', '\x2c')],
        r'\widehat':   [('rm', '\x5e'), ('ex', '\x62'), ('ex', '\x63'),
                        ('ex', '\x64')],
        r'\widetilde': [('rm', '\x7e'), ('ex', '\x65'), ('ex', '\x66'),
                        ('ex', '\x67')],
        r'<':          [('cal', 'h'), ('ex', 'D')],
        r'>':          [('cal', 'i'), ('ex', 'E')]
        }

    for alias, target in [(r'\leftparen', '('),
                          (r'\rightparen', ')'),
                          (r'\leftbrace', '{'),
                          (r'\rightbrace', '}'),
                          (r'\leftbracket', '['),
                          (r'\rightbracket', ']'),
                          (r'\{', '{'),
                          (r'\}', '}'),
                          (r'\[', '['),
                          (r'\]', ']')]:
        _size_alternatives[alias] = _size_alternatives[target]

    def get_sized_alternatives_for_symbol(self, fontname: str,
                                          sym: str) -> list[tuple[str, str]]:
        return self._size_alternatives.get(sym, [(fontname, sym)])


class UnicodeFonts(TruetypeFonts):
    """
    An abstract base class for handling Unicode fonts.

    While some reasonably complete Unicode fonts (such as DejaVu) may
    work in some situations, the only Unicode font I'm aware of with a
    complete set of math symbols is STIX.

    This class will "fallback" on the Bakoma fonts when a required
    symbol cannot be found in the font.
    """

    # Some glyphs are not present in the `cmr10` font, and must be brought in
    # from `cmsy10`. Map the Unicode indices of those glyphs to the indices at
    # which they are found in `cmsy10`.
    _cmr10_substitutions = {
        0x00D7: 0x00A3,  # Multiplication sign.
        0x2212: 0x00A1,  # Minus sign.
    }

    def __init__(self, default_font_prop: FontProperties, load_glyph_flags: LoadFlags):
        # This must come first so the backend's owner is set correctly
        fallback_rc = mpl.rcParams['mathtext.fallback']
        font_cls: type[TruetypeFonts] | None = {
            'stix': StixFonts,
            'stixsans': StixSansFonts,
            'cm': BakomaFonts
        }.get(fallback_rc)
        self._fallback_font = (font_cls(default_font_prop, load_glyph_flags)
                               if font_cls else None)

        super().__init__(default_font_prop, load_glyph_flags)
        for texfont in "cal rm tt it bf sf bfit".split():
            prop = mpl.rcParams['mathtext.' + texfont]
            font = findfont(prop)
            self.fontmap[texfont] = font
        prop = FontProperties('cmex10')
        font = findfont(prop)
        self.fontmap['ex'] = font

        # include STIX sized alternatives for glyphs if fallback is STIX
        if isinstance(self._fallback_font, StixFonts):
            stixsizedaltfonts = {
                 0: 'STIXGeneral',
                 1: 'STIXSizeOneSym',
                 2: 'STIXSizeTwoSym',
                 3: 'STIXSizeThreeSym',
                 4: 'STIXSizeFourSym',
                 5: 'STIXSizeFiveSym'}

            for size, name in stixsizedaltfonts.items():
                fullpath = findfont(name)
                self.fontmap[size] = fullpath
                self.fontmap[name] = fullpath

    _slanted_symbols = set(r"\int \oint".split())

    def _map_virtual_font(self, fontname: str, font_class: str,
                          uniindex: int) -> tuple[str, int]:
        return fontname, uniindex

    def _get_glyph(self, fontname: str, font_class: str,
                   sym: str) -> tuple[FT2Font, int, bool]:
        try:
            uniindex = get_unicode_index(sym)
            found_symbol = True
        except ValueError:
            uniindex = ord('?')
            found_symbol = False
            _log.warning("No TeX to Unicode mapping for %a.", sym)

        fontname, uniindex = self._map_virtual_font(
            fontname, font_class, uniindex)

        new_fontname = fontname

        # Only characters in the "Letter" class should be italicized in 'it'
        # mode.  Greek capital letters should be Roman.
        if found_symbol:
            if fontname == 'it' and uniindex < 0x10000:
                char = chr(uniindex)
                if (unicodedata.category(char)[0] != "L"
                        or unicodedata.name(char).startswith("GREEK CAPITAL")):
                    new_fontname = 'rm'

            slanted = (new_fontname == 'it') or sym in self._slanted_symbols
            found_symbol = False
            font = self._get_font(new_fontname)
            if font is not None:
                if (uniindex in self._cmr10_substitutions
                        and font.family_name == "cmr10"):
                    font = get_font(
                        cbook._get_data_path("fonts/ttf/cmsy10.ttf"))
                    uniindex = self._cmr10_substitutions[uniindex]
                glyphindex = font.get_char_index(uniindex)
                if glyphindex != 0:
                    found_symbol = True

        if not found_symbol:
            if self._fallback_font:
                if (fontname in ('it', 'regular')
                        and isinstance(self._fallback_font, StixFonts)):
                    fontname = 'rm'

                g = self._fallback_font._get_glyph(fontname, font_class, sym)
                family = g[0].family_name
                if family in list(BakomaFonts._fontmap.values()):
                    family = "Computer Modern"
                _log.info("Substituting symbol %s from %s", sym, family)
                return g

            else:
                if (fontname in ('it', 'regular')
                        and isinstance(self, StixFonts)):
                    return self._get_glyph('rm', font_class, sym)
                _log.warning("Font %r does not have a glyph for %a [U+%x], "
                             "substituting with a dummy symbol.",
                             new_fontname, sym, uniindex)
                font = self._get_font('rm')
                uniindex = 0xA4  # currency char, for lack of anything better
                slanted = False

        return font, uniindex, slanted

    def get_sized_alternatives_for_symbol(self, fontname: str,
                                          sym: str) -> list[tuple[str, str]]:
        if self._fallback_font:
            return self._fallback_font.get_sized_alternatives_for_symbol(
                fontname, sym)
        return [(fontname, sym)]


class DejaVuFonts(UnicodeFonts, metaclass=abc.ABCMeta):
    _fontmap: dict[str | int, str] = {}

    def __init__(self, default_font_prop: FontProperties, load_glyph_flags: LoadFlags):
        # This must come first so the backend's owner is set correctly
        if isinstance(self, DejaVuSerifFonts):
            self._fallback_font = StixFonts(default_font_prop, load_glyph_flags)
        else:
            self._fallback_font = StixSansFonts(default_font_prop, load_glyph_flags)
        self.bakoma = BakomaFonts(default_font_prop, load_glyph_flags)
        TruetypeFonts.__init__(self, default_font_prop, load_glyph_flags)
        # Include Stix sized alternatives for glyphs
        self._fontmap.update({
            1: 'STIXSizeOneSym',
            2: 'STIXSizeTwoSym',
            3: 'STIXSizeThreeSym',
            4: 'STIXSizeFourSym',
            5: 'STIXSizeFiveSym',
        })
        for key, name in self._fontmap.items():
            fullpath = findfont(name)
            self.fontmap[key] = fullpath
            self.fontmap[name] = fullpath

    def _get_glyph(self, fontname: str, font_class: str,
                   sym: str) -> tuple[FT2Font, int, bool]:
        # Override prime symbol to use Bakoma.
        if sym == r'\prime':
            return self.bakoma._get_glyph(fontname, font_class, sym)
        else:
            # check whether the glyph is available in the display font
            uniindex = get_unicode_index(sym)
            font = self._get_font('ex')
            if font is not None:
                glyphindex = font.get_char_index(uniindex)
                if glyphindex != 0:
                    return super()._get_glyph('ex', font_class, sym)
            # otherwise return regular glyph
            return super()._get_glyph(fontname, font_class, sym)


class DejaVuSerifFonts(DejaVuFonts):
    """
    A font handling class for the DejaVu Serif fonts

    If a glyph is not found it will fallback to Stix Serif
    """
    _fontmap = {
        'rm': 'DejaVu Serif',
        'it': 'DejaVu Serif:italic',
        'bf': 'DejaVu Serif:weight=bold',
        'bfit': 'DejaVu Serif:italic:bold',
        'sf': 'DejaVu Sans',
        'tt': 'DejaVu Sans Mono',
        'ex': 'DejaVu Serif Display',
        0:    'DejaVu Serif',
    }


class DejaVuSansFonts(DejaVuFonts):
    """
    A font handling class for the DejaVu Sans fonts

    If a glyph is not found it will fallback to Stix Sans
    """
    _fontmap = {
        'rm': 'DejaVu Sans',
        'it': 'DejaVu Sans:italic',
        'bf': 'DejaVu Sans:weight=bold',
        'bfit': 'DejaVu Sans:italic:bold',
        'sf': 'DejaVu Sans',
        'tt': 'DejaVu Sans Mono',
        'ex': 'DejaVu Sans Display',
        0:    'DejaVu Sans',
    }


class StixFonts(UnicodeFonts):
    """
    A font handling class for the STIX fonts.

    In addition to what UnicodeFonts provides, this class:

    - supports "virtual fonts" which are complete alpha numeric
      character sets with different font styles at special Unicode
      code points, such as "Blackboard".

    - handles sized alternative characters for the STIXSizeX fonts.
    """
    _fontmap: dict[str | int, str] = {
        'rm': 'STIXGeneral',
        'it': 'STIXGeneral:italic',
        'bf': 'STIXGeneral:weight=bold',
        'bfit': 'STIXGeneral:italic:bold',
        'nonunirm': 'STIXNonUnicode',
        'nonuniit': 'STIXNonUnicode:italic',
        'nonunibf': 'STIXNonUnicode:weight=bold',
        0: 'STIXGeneral',
        1: 'STIXSizeOneSym',
        2: 'STIXSizeTwoSym',
        3: 'STIXSizeThreeSym',
        4: 'STIXSizeFourSym',
        5: 'STIXSizeFiveSym',
    }
    _fallback_font = None
    _sans = False

    def __init__(self, default_font_prop: FontProperties, load_glyph_flags: LoadFlags):
        TruetypeFonts.__init__(self, default_font_prop, load_glyph_flags)
        for key, name in self._fontmap.items():
            fullpath = findfont(name)
            self.fontmap[key] = fullpath
            self.fontmap[name] = fullpath

    def _map_virtual_font(self, fontname: str, font_class: str,
                          uniindex: int) -> tuple[str, int]:
        # Handle these "fonts" that are actually embedded in
        # other fonts.
        font_mapping = stix_virtual_fonts.get(fontname)
        if (self._sans and font_mapping is None
                and fontname not in ('regular', 'default')):
            font_mapping = stix_virtual_fonts['sf']
            doing_sans_conversion = True
        else:
            doing_sans_conversion = False

        if isinstance(font_mapping, dict):
            try:
                mapping = font_mapping[font_class]
            except KeyError:
                mapping = font_mapping['rm']
        elif isinstance(font_mapping, list):
            mapping = font_mapping
        else:
            mapping = None

        if mapping is not None:
            # Binary search for the source glyph
            lo = 0
            hi = len(mapping)
            while lo < hi:
                mid = (lo+hi)//2
                range = mapping[mid]
                if uniindex < range[0]:
                    hi = mid
                elif uniindex <= range[1]:
                    break
                else:
                    lo = mid + 1

            if range[0] <= uniindex <= range[1]:
                uniindex = uniindex - range[0] + range[3]
                fontname = range[2]
            elif not doing_sans_conversion:
                # This will generate a dummy character
                uniindex = 0x1
                fontname = mpl.rcParams['mathtext.default']

        # Fix some incorrect glyphs.
        if fontname in ('rm', 'it'):
            uniindex = stix_glyph_fixes.get(uniindex, uniindex)

        # Handle private use area glyphs
        if fontname in ('it', 'rm', 'bf', 'bfit') and 0xe000 <= uniindex <= 0xf8ff:
            fontname = 'nonuni' + fontname

        return fontname, uniindex

    @functools.cache
    def get_sized_alternatives_for_symbol(  # type: ignore[override]
            self,
            fontname: str,
            sym: str) -> list[tuple[str, str]] | list[tuple[int, str]]:
        fixes = {
            '\\{': '{', '\\}': '}', '\\[': '[', '\\]': ']',
            '<': '\N{MATHEMATICAL LEFT ANGLE BRACKET}',
            '>': '\N{MATHEMATICAL RIGHT ANGLE BRACKET}',
        }
        sym = fixes.get(sym, sym)
        try:
            uniindex = get_unicode_index(sym)
        except ValueError:
            return [(fontname, sym)]
        alternatives = [(i, chr(uniindex)) for i in range(6)
                        if self._get_font(i).get_char_index(uniindex) != 0]
        # The largest size of the radical symbol in STIX has incorrect
        # metrics that cause it to be disconnected from the stem.
        if sym == r'\__sqrt__':
            alternatives = alternatives[:-1]
        return alternatives


class StixSansFonts(StixFonts):
    """
    A font handling class for the STIX fonts (that uses sans-serif
    characters by default).
    """
    _sans = True


##############################################################################
# TeX-LIKE BOX MODEL

# The following is based directly on the document 'woven' from the
# TeX82 source code.  This information is also available in printed
# form:
#
#    Knuth, Donald E.. 1986.  Computers and Typesetting, Volume B:
#    TeX: The Program.  Addison-Wesley Professional.
#
# The most relevant "chapters" are:
#    Data structures for boxes and their friends
#    Shipping pages out (ship())
#    Packaging (hpack() and vpack())
#    Data structures for math mode
#    Subroutines for math mode
#    Typesetting math formulas
#
# Many of the docstrings below refer to a numbered "node" in that
# book, e.g., node123
#
# Note that (as TeX) y increases downward, unlike many other parts of
# matplotlib.

# How much text shrinks when going to the next-smallest level.
SHRINK_FACTOR   = 0.7
# The number of different sizes of chars to use, beyond which they will not
# get any smaller
NUM_SIZE_LEVELS = 6


class FontConstantsBase:
    """
    A set of constants that controls how certain things, such as sub-
    and superscripts are laid out.  These are all metrics that can't
    be reliably retrieved from the font metrics in the font itself.
    """
    # Percentage of x-height of additional horiz. space after sub/superscripts
    script_space: T.ClassVar[float] = 0.05

    # Percentage of x-height that sub/superscripts drop below the baseline
    subdrop: T.ClassVar[float] = 0.4

    # Percentage of x-height that superscripts are raised from the baseline
    sup1: T.ClassVar[float] = 0.7

    # Percentage of x-height that subscripts drop below the baseline
    sub1: T.ClassVar[float] = 0.3

    # Percentage of x-height that subscripts drop below the baseline when a
    # superscript is present
    sub2: T.ClassVar[float] = 0.5

    # Percentage of x-height that sub/superscripts are offset relative to the
    # nucleus edge for non-slanted nuclei
    delta: T.ClassVar[float] = 0.025

    # Additional percentage of last character height above 2/3 of the
    # x-height that superscripts are offset relative to the subscript
    # for slanted nuclei
    delta_slanted: T.ClassVar[float] = 0.2

    # Percentage of x-height that superscripts and subscripts are offset for
    # integrals
    delta_integral: T.ClassVar[float] = 0.1


class ComputerModernFontConstants(FontConstantsBase):
    script_space = 0.075
    subdrop = 0.2
    sup1 = 0.45
    sub1 = 0.2
    sub2 = 0.3
    delta = 0.075
    delta_slanted = 0.3
    delta_integral = 0.3


class STIXFontConstants(FontConstantsBase):
    script_space = 0.1
    sup1 = 0.8
    sub2 = 0.6
    delta = 0.05
    delta_slanted = 0.3
    delta_integral = 0.3


class STIXSansFontConstants(FontConstantsBase):
    script_space = 0.05
    sup1 = 0.8
    delta_slanted = 0.6
    delta_integral = 0.3


class DejaVuSerifFontConstants(FontConstantsBase):
    pass


class DejaVuSansFontConstants(FontConstantsBase):
    pass


# Maps font family names to the FontConstantBase subclass to use
_font_constant_mapping = {
    'DejaVu Sans': DejaVuSansFontConstants,
    'DejaVu Sans Mono': DejaVuSansFontConstants,
    'DejaVu Serif': DejaVuSerifFontConstants,
    'cmb10': ComputerModernFontConstants,
    'cmex10': ComputerModernFontConstants,
    'cmmi10': ComputerModernFontConstants,
    'cmr10': ComputerModernFontConstants,
    'cmss10': ComputerModernFontConstants,
    'cmsy10': ComputerModernFontConstants,
    'cmtt10': ComputerModernFontConstants,
    'STIXGeneral': STIXFontConstants,
    'STIXNonUnicode': STIXFontConstants,
    'STIXSizeFiveSym': STIXFontConstants,
    'STIXSizeFourSym': STIXFontConstants,
    'STIXSizeThreeSym': STIXFontConstants,
    'STIXSizeTwoSym': STIXFontConstants,
    'STIXSizeOneSym': STIXFontConstants,
    # Map the fonts we used to ship, just for good measure
    'Bitstream Vera Sans': DejaVuSansFontConstants,
    'Bitstream Vera': DejaVuSansFontConstants,
    }


def _get_font_constant_set(state: ParserState) -> type[FontConstantsBase]:
    constants = _font_constant_mapping.get(
        state.fontset._get_font(state.font).family_name, FontConstantsBase)
    # STIX sans isn't really its own fonts, just different code points
    # in the STIX fonts, so we have to detect this one separately.
    if (constants is STIXFontConstants and
            isinstance(state.fontset, StixSansFonts)):
        return STIXSansFontConstants
    return constants


class Node:
    """A node in the TeX box model."""

    def __init__(self) -> None:
        self.size = 0

    def __repr__(self) -> str:
        return type(self).__name__

    def get_kerning(self, next: Node | None) -> float:
        return 0.0

    def shrink(self) -> None:
        """
        Shrinks one level smaller.  There are only three levels of
        sizes, after which things will no longer get smaller.
        """
        self.size += 1

    def render(self, output: Output, x: float, y: float) -> None:
        """Render this node."""


class Box(Node):
    """A node with a physical location."""

    def __init__(self, width: float, height: float, depth: float) -> None:
        super().__init__()
        self.width  = width
        self.height = height
        self.depth  = depth

    def shrink(self) -> None:
        super().shrink()
        if self.size < NUM_SIZE_LEVELS:
            self.width  *= SHRINK_FACTOR
            self.height *= SHRINK_FACTOR
            self.depth  *= SHRINK_FACTOR

    def render(self, output: Output,  # type: ignore[override]
               x1: float, y1: float, x2: float, y2: float) -> None:
        pass


class Vbox(Box):
    """A box with only height (zero width)."""

    def __init__(self, height: float, depth: float):
        super().__init__(0., height, depth)


class Hbox(Box):
    """A box with only width (zero height and depth)."""

    def __init__(self, width: float):
        super().__init__(width, 0., 0.)


class Char(Node):
    """
    A single character.

    Unlike TeX, the font information and metrics are stored with each `Char`
    to make it easier to lookup the font metrics when needed.  Note that TeX
    boxes have a width, height, and depth, unlike Type1 and TrueType which use
    a full bounding box and an advance in the x-direction.  The metrics must
    be converted to the TeX model, and the advance (if different from width)
    must be converted into a `Kern` node when the `Char` is added to its parent
    `Hlist`.
    """

    def __init__(self, c: str, state: ParserState):
        super().__init__()
        self.c = c
        self.fontset = state.fontset
        self.font = state.font
        self.font_class = state.font_class
        self.fontsize = state.fontsize
        self.dpi = state.dpi
        # The real width, height and depth will be set during the
        # pack phase, after we know the real fontsize
        self._update_metrics()

    def __repr__(self) -> str:
        return '`%s`' % self.c

    def _update_metrics(self) -> None:
        metrics = self._metrics = self.fontset.get_metrics(
            self.font, self.font_class, self.c, self.fontsize, self.dpi)
        if self.c == ' ':
            self.width = metrics.advance
        else:
            self.width = metrics.width
        self.height = metrics.iceberg
        self.depth = -(metrics.iceberg - metrics.height)

    def is_slanted(self) -> bool:
        return self._metrics.slanted

    def get_kerning(self, next: Node | None) -> float:
        """
        Return the amount of kerning between this and the given character.

        This method is called when characters are strung together into `Hlist`
        to create `Kern` nodes.
        """
        advance = self._metrics.advance - self.width
        kern = 0.
        if isinstance(next, Char):
            kern = self.fontset.get_kern(
                self.font, self.font_class, self.c, self.fontsize,
                next.font, next.font_class, next.c, next.fontsize,
                self.dpi)
        return advance + kern

    def render(self, output: Output, x: float, y: float) -> None:
        self.fontset.render_glyph(
            output, x, y,
            self.font, self.font_class, self.c, self.fontsize, self.dpi)

    def shrink(self) -> None:
        super().shrink()
        if self.size < NUM_SIZE_LEVELS:
            self.fontsize *= SHRINK_FACTOR
            self.width    *= SHRINK_FACTOR
            self.height   *= SHRINK_FACTOR
            self.depth    *= SHRINK_FACTOR


class Accent(Char):
    """
    The font metrics need to be dealt with differently for accents,
    since they are already offset correctly from the baseline in
    TrueType fonts.
    """
    def _update_metrics(self) -> None:
        metrics = self._metrics = self.fontset.get_metrics(
            self.font, self.font_class, self.c, self.fontsize, self.dpi)
        self.width = metrics.xmax - metrics.xmin
        self.height = metrics.ymax - metrics.ymin
        self.depth = 0

    def shrink(self) -> None:
        super().shrink()
        self._update_metrics()

    def render(self, output: Output, x: float, y: float) -> None:
        self.fontset.render_glyph(
            output, x - self._metrics.xmin, y + self._metrics.ymin,
            self.font, self.font_class, self.c, self.fontsize, self.dpi)


class List(Box):
    """A list of nodes (either horizontal or vertical)."""

    def __init__(self, elements: T.Sequence[Node]):
        super().__init__(0., 0., 0.)
        self.shift_amount = 0.   # An arbitrary offset
        self.children = [*elements]  # The child nodes of this list
        # The following parameters are set in the vpack and hpack functions
        self.glue_set     = 0.   # The glue setting of this list
        self.glue_sign    = 0    # 0: normal, -1: shrinking, 1: stretching
        self.glue_order   = 0    # The order of infinity (0 - 3) for the glue

    def __repr__(self) -> str:
        return '{}<w={:.02f} h={:.02f} d={:.02f} s={:.02f}>[{}]'.format(
            super().__repr__(),
            self.width, self.height,
            self.depth, self.shift_amount,
            ', '.join([repr(x) for x in self.children]))

    def _set_glue(self, x: float, sign: int, totals: list[float],
                  error_type: str) -> None:
        self.glue_order = o = next(
            # Highest order of glue used by the members of this list.
            (i for i in range(len(totals))[::-1] if totals[i] != 0), 0)
        self.glue_sign = sign
        if totals[o] != 0.:
            self.glue_set = x / totals[o]
        else:
            self.glue_sign = 0
            self.glue_ratio = 0.
        if o == 0:
            if len(self.children):
                _log.warning("%s %s: %r",
                             error_type, type(self).__name__, self)

    def shrink(self) -> None:
        for child in self.children:
            child.shrink()
        super().shrink()
        if self.size < NUM_SIZE_LEVELS:
            self.shift_amount *= SHRINK_FACTOR
            self.glue_set     *= SHRINK_FACTOR


class Hlist(List):
    """A horizontal list of boxes."""

    def __init__(self, elements: T.Sequence[Node], w: float = 0.0,
                 m: T.Literal['additional', 'exactly'] = 'additional',
                 do_kern: bool = True):
        super().__init__(elements)
        if do_kern:
            self.kern()
        self.hpack(w=w, m=m)

    def kern(self) -> None:
        """
        Insert `Kern` nodes between `Char` nodes to set kerning.

        The `Char` nodes themselves determine the amount of kerning they need
        (in `~Char.get_kerning`), and this function just creates the correct
        linked list.
        """
        new_children = []
        num_children = len(self.children)
        if num_children:
            for i in range(num_children):
                elem = self.children[i]
                if i < num_children - 1:
                    next = self.children[i + 1]
                else:
                    next = None

                new_children.append(elem)
                kerning_distance = elem.get_kerning(next)
                if kerning_distance != 0.:
                    kern = Kern(kerning_distance)
                    new_children.append(kern)
            self.children = new_children

    def hpack(self, w: float = 0.0,
              m: T.Literal['additional', 'exactly'] = 'additional') -> None:
        r"""
        Compute the dimensions of the resulting boxes, and adjust the glue if
        one of those dimensions is pre-specified.  The computed sizes normally
        enclose all of the material inside the new box; but some items may
        stick out if negative glue is used, if the box is overfull, or if a
        ``\vbox`` includes other boxes that have been shifted left.

        Parameters
        ----------
        w : float, default: 0
            A width.
        m : {'exactly', 'additional'}, default: 'additional'
            Whether to produce a box whose width is 'exactly' *w*; or a box
            with the natural width of the contents, plus *w* ('additional').

        Notes
        -----
        The defaults produce a box with the natural width of the contents.
        """
        # I don't know why these get reset in TeX.  Shift_amount is pretty
        # much useless if we do.
        # self.shift_amount = 0.
        h = 0.
        d = 0.
        x = 0.
        total_stretch = [0.] * 4
        total_shrink = [0.] * 4
        for p in self.children:
            if isinstance(p, Char):
                x += p.width
                h = max(h, p.height)
                d = max(d, p.depth)
            elif isinstance(p, Box):
                x += p.width
                if not np.isinf(p.height) and not np.isinf(p.depth):
                    s = getattr(p, 'shift_amount', 0.)
                    h = max(h, p.height - s)
                    d = max(d, p.depth + s)
            elif isinstance(p, Glue):
                glue_spec = p.glue_spec
                x += glue_spec.width
                total_stretch[glue_spec.stretch_order] += glue_spec.stretch
                total_shrink[glue_spec.shrink_order] += glue_spec.shrink
            elif isinstance(p, Kern):
                x += p.width
        self.height = h
        self.depth = d

        if m == 'additional':
            w += x
        self.width = w
        x = w - x

        if x == 0.:
            self.glue_sign = 0
            self.glue_order = 0
            self.glue_ratio = 0.
            return
        if x > 0.:
            self._set_glue(x, 1, total_stretch, "Overful")
        else:
            self._set_glue(x, -1, total_shrink, "Underful")


class Vlist(List):
    """A vertical list of boxes."""

    def __init__(self, elements: T.Sequence[Node], h: float = 0.0,
                 m: T.Literal['additional', 'exactly'] = 'additional'):
        super().__init__(elements)
        self.vpack(h=h, m=m)

    def vpack(self, h: float = 0.0,
              m: T.Literal['additional', 'exactly'] = 'additional',
              l: float = np.inf) -> None:
        """
        Compute the dimensions of the resulting boxes, and to adjust the glue
        if one of those dimensions is pre-specified.

        Parameters
        ----------
        h : float, default: 0
            A height.
        m : {'exactly', 'additional'}, default: 'additional'
            Whether to produce a box whose height is 'exactly' *h*; or a box
            with the natural height of the contents, plus *h* ('additional').
        l : float, default: np.inf
            The maximum height.

        Notes
        -----
        The defaults produce a box with the natural height of the contents.
        """
        # I don't know why these get reset in TeX.  Shift_amount is pretty
        # much useless if we do.
        # self.shift_amount = 0.
        w = 0.
        d = 0.
        x = 0.
        total_stretch = [0.] * 4
        total_shrink = [0.] * 4
        for p in self.children:
            if isinstance(p, Box):
                x += d + p.height
                d = p.depth
                if not np.isinf(p.width):
                    s = getattr(p, 'shift_amount', 0.)
                    w = max(w, p.width + s)
            elif isinstance(p, Glue):
                x += d
                d = 0.
                glue_spec = p.glue_spec
                x += glue_spec.width
                total_stretch[glue_spec.stretch_order] += glue_spec.stretch
                total_shrink[glue_spec.shrink_order] += glue_spec.shrink
            elif isinstance(p, Kern):
                x += d + p.width
                d = 0.
            elif isinstance(p, Char):
                raise RuntimeError(
                    "Internal mathtext error: Char node found in Vlist")

        self.width = w
        if d > l:
            x += d - l
            self.depth = l
        else:
            self.depth = d

        if m == 'additional':
            h += x
        self.height = h
        x = h - x

        if x == 0:
            self.glue_sign = 0
            self.glue_order = 0
            self.glue_ratio = 0.
            return

        if x > 0.:
            self._set_glue(x, 1, total_stretch, "Overful")
        else:
            self._set_glue(x, -1, total_shrink, "Underful")


class Rule(Box):
    """
    A solid black rectangle.

    It has *width*, *depth*, and *height* fields just as in an `Hlist`.
    However, if any of these dimensions is inf, the actual value will be
    determined by running the rule up to the boundary of the innermost
    enclosing box.  This is called a "running dimension".  The width is never
    running in an `Hlist`; the height and depth are never running in a `Vlist`.
    """

    def __init__(self, width: float, height: float, depth: float, state: ParserState):
        super().__init__(width, height, depth)
        self.fontset = state.fontset

    def render(self, output: Output,  # type: ignore[override]
               x: float, y: float, w: float, h: float) -> None:
        self.fontset.render_rect_filled(output, x, y, x + w, y + h)


class Hrule(Rule):
    """Convenience class to create a horizontal rule."""

    def __init__(self, state: ParserState, thickness: float | None = None):
        if thickness is None:
            thickness = state.get_current_underline_thickness()
        height = depth = thickness * 0.5
        super().__init__(np.inf, height, depth, state)


class Vrule(Rule):
    """Convenience class to create a vertical rule."""

    def __init__(self, state: ParserState):
        thickness = state.get_current_underline_thickness()
        super().__init__(thickness, np.inf, np.inf, state)


class _GlueSpec(NamedTuple):
    width: float
    stretch: float
    stretch_order: int
    shrink: float
    shrink_order: int


_GlueSpec._named = {  # type: ignore[attr-defined]
    'fil':         _GlueSpec(0., 1., 1, 0., 0),
    'fill':        _GlueSpec(0., 1., 2, 0., 0),
    'filll':       _GlueSpec(0., 1., 3, 0., 0),
    'neg_fil':     _GlueSpec(0., 0., 0, 1., 1),
    'neg_fill':    _GlueSpec(0., 0., 0, 1., 2),
    'neg_filll':   _GlueSpec(0., 0., 0, 1., 3),
    'empty':       _GlueSpec(0., 0., 0, 0., 0),
    'ss':          _GlueSpec(0., 1., 1, -1., 1),
}


class Glue(Node):
    """
    Most of the information in this object is stored in the underlying
    ``_GlueSpec`` class, which is shared between multiple glue objects.
    (This is a memory optimization which probably doesn't matter anymore, but
    it's easier to stick to what TeX does.)
    """

    def __init__(self,
                 glue_type: _GlueSpec | T.Literal["fil", "fill", "filll",
                                                  "neg_fil", "neg_fill", "neg_filll",
                                                  "empty", "ss"]):
        super().__init__()
        if isinstance(glue_type, str):
            glue_spec = _GlueSpec._named[glue_type]  # type: ignore[attr-defined]
        elif isinstance(glue_type, _GlueSpec):
            glue_spec = glue_type
        else:
            raise ValueError("glue_type must be a glue spec name or instance")
        self.glue_spec = glue_spec

    def shrink(self) -> None:
        super().shrink()
        if self.size < NUM_SIZE_LEVELS:
            g = self.glue_spec
            self.glue_spec = g._replace(width=g.width * SHRINK_FACTOR)


class HCentered(Hlist):
    """
    A convenience class to create an `Hlist` whose contents are
    centered within its enclosing box.
    """

    def __init__(self, elements: list[Node]):
        super().__init__([Glue('ss'), *elements, Glue('ss')], do_kern=False)


class VCentered(Vlist):
    """
    A convenience class to create a `Vlist` whose contents are
    centered within its enclosing box.
    """

    def __init__(self, elements: list[Node]):
        super().__init__([Glue('ss'), *elements, Glue('ss')])


class Kern(Node):
    """
    A `Kern` node has a width field to specify a (normally
    negative) amount of spacing. This spacing correction appears in
    horizontal lists between letters like A and V when the font
    designer said that it looks better to move them closer together or
    further apart. A kern node can also appear in a vertical list,
    when its *width* denotes additional spacing in the vertical
    direction.
    """

    height = 0
    depth = 0

    def __init__(self, width: float):
        super().__init__()
        self.width = width

    def __repr__(self) -> str:
        return "k%.02f" % self.width

    def shrink(self) -> None:
        super().shrink()
        if self.size < NUM_SIZE_LEVELS:
            self.width *= SHRINK_FACTOR


class AutoHeightChar(Hlist):
    """
    A character as close to the given height and depth as possible.

    When using a font with multiple height versions of some characters (such as
    the BaKoMa fonts), the correct glyph will be selected, otherwise this will
    always just return a scaled version of the glyph.
    """

    def __init__(self, c: str, height: float, depth: float, state: ParserState,
                 always: bool = False, factor: float | None = None):
        alternatives = state.fontset.get_sized_alternatives_for_symbol(
            state.font, c)

        xHeight = state.fontset.get_xheight(
            state.font, state.fontsize, state.dpi)

        state = state.copy()
        target_total = height + depth
        for fontname, sym in alternatives:
            state.font = fontname
            char = Char(sym, state)
            # Ensure that size 0 is chosen when the text is regular sized but
            # with descender glyphs by subtracting 0.2 * xHeight
            if char.height + char.depth >= target_total - 0.2 * xHeight:
                break

        shift = 0.0
        if state.font != 0 or len(alternatives) == 1:
            if factor is None:
                factor = target_total / (char.height + char.depth)
            state.fontsize *= factor
            char = Char(sym, state)

            shift = (depth - char.depth)

        super().__init__([char])
        self.shift_amount = shift


class AutoWidthChar(Hlist):
    """
    A character as close to the given width as possible.

    When using a font with multiple width versions of some characters (such as
    the BaKoMa fonts), the correct glyph will be selected, otherwise this will
    always just return a scaled version of the glyph.
    """

    def __init__(self, c: str, width: float, state: ParserState, always: bool = False,
                 char_class: type[Char] = Char):
        alternatives = state.fontset.get_sized_alternatives_for_symbol(
            state.font, c)

        state = state.copy()
        for fontname, sym in alternatives:
            state.font = fontname
            char = char_class(sym, state)
            if char.width >= width:
                break

        factor = width / char.width
        state.fontsize *= factor
        char = char_class(sym, state)

        super().__init__([char])
        self.width = char.width


def ship(box: Box, xy: tuple[float, float] = (0, 0)) -> Output:
    """
    Ship out *box* at offset *xy*, converting it to an `Output`.

    Since boxes can be inside of boxes inside of boxes, the main work of `ship`
    is done by two mutually recursive routines, `hlist_out` and `vlist_out`,
    which traverse the `Hlist` nodes and `Vlist` nodes inside of horizontal
    and vertical boxes.  The global variables used in TeX to store state as it
    processes have become local variables here.
    """
    ox, oy = xy
    cur_v = 0.
    cur_h = 0.
    off_h = ox
    off_v = oy + box.height
    output = Output(box)

    def clamp(value: float) -> float:
        return -1e9 if value < -1e9 else +1e9 if value > +1e9 else value

    def hlist_out(box: Hlist) -> None:
        nonlocal cur_v, cur_h, off_h, off_v

        cur_g = 0
        cur_glue = 0.
        glue_order = box.glue_order
        glue_sign = box.glue_sign
        base_line = cur_v
        left_edge = cur_h

        for p in box.children:
            if isinstance(p, Char):
                p.render(output, cur_h + off_h, cur_v + off_v)
                cur_h += p.width
            elif isinstance(p, Kern):
                cur_h += p.width
            elif isinstance(p, List):
                # node623
                if len(p.children) == 0:
                    cur_h += p.width
                else:
                    edge = cur_h
                    cur_v = base_line + p.shift_amount
                    if isinstance(p, Hlist):
                        hlist_out(p)
                    elif isinstance(p, Vlist):
                        # p.vpack(box.height + box.depth, 'exactly')
                        vlist_out(p)
                    else:
                        assert False, "unreachable code"
                    cur_h = edge + p.width
                    cur_v = base_line
            elif isinstance(p, Box):
                # node624
                rule_height = p.height
                rule_depth = p.depth
                rule_width = p.width
                if np.isinf(rule_height):
                    rule_height = box.height
                if np.isinf(rule_depth):
                    rule_depth = box.depth
                if rule_height > 0 and rule_width > 0:
                    cur_v = base_line + rule_depth
                    p.render(output,
                             cur_h + off_h, cur_v + off_v,
                             rule_width, rule_height)
                    cur_v = base_line
                cur_h += rule_width
            elif isinstance(p, Glue):
                # node625
                glue_spec = p.glue_spec
                rule_width = glue_spec.width - cur_g
                if glue_sign != 0:  # normal
                    if glue_sign == 1:  # stretching
                        if glue_spec.stretch_order == glue_order:
                            cur_glue += glue_spec.stretch
                            cur_g = round(clamp(box.glue_set * cur_glue))
                    elif glue_spec.shrink_order == glue_order:
                        cur_glue += glue_spec.shrink
                        cur_g = round(clamp(box.glue_set * cur_glue))
                rule_width += cur_g
                cur_h += rule_width

    def vlist_out(box: Vlist) -> None:
        nonlocal cur_v, cur_h, off_h, off_v

        cur_g = 0
        cur_glue = 0.
        glue_order = box.glue_order
        glue_sign = box.glue_sign
        left_edge = cur_h
        cur_v -= box.height
        top_edge = cur_v

        for p in box.children:
            if isinstance(p, Kern):
                cur_v += p.width
            elif isinstance(p, List):
                if len(p.children) == 0:
                    cur_v += p.height + p.depth
                else:
                    cur_v += p.height
                    cur_h = left_edge + p.shift_amount
                    save_v = cur_v
                    p.width = box.width
                    if isinstance(p, Hlist):
                        hlist_out(p)
                    elif isinstance(p, Vlist):
                        vlist_out(p)
                    else:
                        assert False, "unreachable code"
                    cur_v = save_v + p.depth
                    cur_h = left_edge
            elif isinstance(p, Box):
                rule_height = p.height
                rule_depth = p.depth
                rule_width = p.width
                if np.isinf(rule_width):
                    rule_width = box.width
                rule_height += rule_depth
                if rule_height > 0 and rule_depth > 0:
                    cur_v += rule_height
                    p.render(output,
                             cur_h + off_h, cur_v + off_v,
                             rule_width, rule_height)
            elif isinstance(p, Glue):
                glue_spec = p.glue_spec
                rule_height = glue_spec.width - cur_g
                if glue_sign != 0:  # normal
                    if glue_sign == 1:  # stretching
                        if glue_spec.stretch_order == glue_order:
                            cur_glue += glue_spec.stretch
                            cur_g = round(clamp(box.glue_set * cur_glue))
                    elif glue_spec.shrink_order == glue_order:  # shrinking
                        cur_glue += glue_spec.shrink
                        cur_g = round(clamp(box.glue_set * cur_glue))
                rule_height += cur_g
                cur_v += rule_height
            elif isinstance(p, Char):
                raise RuntimeError(
                    "Internal mathtext error: Char node found in vlist")

    assert isinstance(box, Hlist)
    hlist_out(box)
    return output


##############################################################################
# PARSER


def Error(msg: str) -> ParserElement:
    """Helper class to raise parser errors."""
    def raise_error(s: str, loc: int, toks: ParseResults) -> T.Any:
        raise ParseFatalException(s, loc, msg)

    return Empty().set_parse_action(raise_error)


class ParserState:
    """
    Parser state.

    States are pushed and popped from a stack as necessary, and the "current"
    state is always at the top of the stack.

    Upon entering and leaving a group { } or math/non-math, the stack is pushed
    and popped accordingly.
    """

    def __init__(self, fontset: Fonts, font: str, font_class: str, fontsize: float,
                 dpi: float):
        self.fontset = fontset
        self._font = font
        self.font_class = font_class
        self.fontsize = fontsize
        self.dpi = dpi

    def copy(self) -> ParserState:
        return copy.copy(self)

    @property
    def font(self) -> str:
        return self._font

    @font.setter
    def font(self, name: str) -> None:
        if name in ('rm', 'it', 'bf', 'bfit'):
            self.font_class = name
        self._font = name

    def get_current_underline_thickness(self) -> float:
        """Return the underline thickness for this state."""
        return self.fontset.get_underline_thickness(
            self.font, self.fontsize, self.dpi)


def cmd(expr: str, args: ParserElement) -> ParserElement:
    r"""
    Helper to define TeX commands.

    ``cmd("\cmd", args)`` is equivalent to
    ``"\cmd" - (args | Error("Expected \cmd{arg}{...}"))`` where the names in
    the error message are taken from element names in *args*.  If *expr*
    already includes arguments (e.g. "\cmd{arg}{...}"), then they are stripped
    when constructing the parse element, but kept (and *expr* is used as is) in
    the error message.
    """

    def names(elt: ParserElement) -> T.Generator[str, None, None]:
        if isinstance(elt, ParseExpression):
            for expr in elt.exprs:
                yield from names(expr)
        elif elt.resultsName:
            yield elt.resultsName

    csname = expr.split("{", 1)[0]
    err = (csname + "".join("{%s}" % name for name in names(args))
           if expr == csname else expr)
    return csname - (args | Error(f"Expected {err}"))


class Parser:
    """
    A pyparsing-based parser for strings containing math expressions.

    Raw text may also appear outside of pairs of ``$``.

    The grammar is based directly on that in TeX, though it cuts a few corners.
    """

    class _MathStyle(enum.Enum):
        DISPLAYSTYLE = 0
        TEXTSTYLE = 1
        SCRIPTSTYLE = 2
        SCRIPTSCRIPTSTYLE = 3

    _binary_operators = set(
      '+ * - \N{MINUS SIGN}'
      r'''
      \pm             \sqcap                   \rhd
      \mp             \sqcup                   \unlhd
      \times          \vee                     \unrhd
      \div            \wedge                   \oplus
      \ast            \setminus                \ominus
      \star           \wr                      \otimes
      \circ           \diamond                 \oslash
      \bullet         \bigtriangleup           \odot
      \cdot           \bigtriangledown         \bigcirc
      \cap            \triangleleft            \dagger
      \cup            \triangleright           \ddagger
      \uplus          \lhd                     \amalg
      \dotplus        \dotminus                \Cap
      \Cup            \barwedge                \boxdot
      \boxminus       \boxplus                 \boxtimes
      \curlyvee       \curlywedge              \divideontimes
      \doublebarwedge \leftthreetimes          \rightthreetimes
      \slash          \veebar                  \barvee
      \cupdot         \intercal                \amalg
      \circledcirc    \circleddash             \circledast
      \boxbar         \obar                    \merge
      \minuscolon     \dotsminusdots
      '''.split())

    _relation_symbols = set(r'''
      = < > :
      \leq          \geq          \equiv       \models
      \prec         \succ         \sim         \perp
      \preceq       \succeq       \simeq       \mid
      \ll           \gg           \asymp       \parallel
      \subset       \supset       \approx      \bowtie
      \subseteq     \supseteq     \cong        \Join
      \sqsubset     \sqsupset     \neq         \smile
      \sqsubseteq   \sqsupseteq   \doteq       \frown
      \in           \ni           \propto      \vdash
      \dashv        \dots         \doteqdot    \leqq
      \geqq         \lneqq        \gneqq       \lessgtr
      \leqslant     \geqslant     \eqgtr       \eqless
      \eqslantless  \eqslantgtr   \lesseqgtr   \backsim
      \backsimeq    \lesssim      \gtrsim      \precsim
      \precnsim     \gnsim        \lnsim       \succsim
      \succnsim     \nsim         \lesseqqgtr  \gtreqqless
      \gtreqless    \subseteqq    \supseteqq   \subsetneqq
      \supsetneqq   \lessapprox   \approxeq    \gtrapprox
      \precapprox   \succapprox   \precnapprox \succnapprox
      \npreccurlyeq \nsucccurlyeq \nsqsubseteq \nsqsupseteq
      \sqsubsetneq  \sqsupsetneq  \nlesssim    \ngtrsim
      \nlessgtr     \ngtrless     \lnapprox    \gnapprox
      \napprox      \approxeq     \approxident \lll
      \ggg          \nparallel    \Vdash       \Vvdash
      \nVdash       \nvdash       \vDash       \nvDash
      \nVDash       \oequal       \simneqq     \triangle
      \triangleq         \triangleeq         \triangleleft
      \triangleright     \ntriangleleft      \ntriangleright
      \trianglelefteq    \ntrianglelefteq    \trianglerighteq
      \ntrianglerighteq  \blacktriangleleft  \blacktriangleright
      \equalparallel     \measuredrightangle \varlrtriangle
      \Doteq        \Bumpeq       \Subset      \Supset
      \backepsilon  \because      \therefore   \bot
      \top          \bumpeq       \circeq      \coloneq
      \curlyeqprec  \curlyeqsucc  \eqcirc      \eqcolon
      \eqsim        \fallingdotseq \gtrdot     \gtrless
      \ltimes       \rtimes       \lessdot     \ne
      \ncong        \nequiv       \ngeq        \ngtr
      \nleq         \nless        \nmid        \notin
      \nprec        \nsubset      \nsubseteq   \nsucc
      \nsupset      \nsupseteq    \pitchfork   \preccurlyeq
      \risingdotseq \subsetneq    \succcurlyeq \supsetneq
      \varpropto    \vartriangleleft \scurel
      \vartriangleright \rightangle \equal     \backcong
      \eqdef        \wedgeq       \questeq     \between
      \veeeq        \disin        \varisins    \isins
      \isindot      \varisinobar  \isinobar    \isinvb
      \isinE        \nisd         \varnis      \nis
      \varniobar    \niobar       \bagmember   \ratio
      \Equiv        \stareq       \measeq      \arceq
      \rightassert  \rightModels  \smallin     \smallowns
      \notsmallowns \nsimeq'''.split())

    _arrow_symbols = set(r"""
     \leftarrow \longleftarrow \uparrow \Leftarrow \Longleftarrow
     \Uparrow \rightarrow \longrightarrow \downarrow \Rightarrow
     \Longrightarrow \Downarrow \leftrightarrow \updownarrow
     \longleftrightarrow \updownarrow \Leftrightarrow
     \Longleftrightarrow \Updownarrow \mapsto \longmapsto \nearrow
     \hookleftarrow \hookrightarrow \searrow \leftharpoonup
     \rightharpoonup \swarrow \leftharpoondown \rightharpoondown
     \nwarrow \rightleftharpoons \leadsto \dashrightarrow
     \dashleftarrow \leftleftarrows \leftrightarrows \Lleftarrow
     \Rrightarrow \twoheadleftarrow \leftarrowtail \looparrowleft
     \leftrightharpoons \curvearrowleft \circlearrowleft \Lsh
     \upuparrows \upharpoonleft \downharpoonleft \multimap
     \leftrightsquigarrow \rightrightarrows \rightleftarrows
     \rightrightarrows \rightleftarrows \twoheadrightarrow
     \rightarrowtail \looparrowright \rightleftharpoons
     \curvearrowright \circlearrowright \Rsh \downdownarrows
     \upharpoonright \downharpoonright \rightsquigarrow \nleftarrow
     \nrightarrow \nLeftarrow \nRightarrow \nleftrightarrow
     \nLeftrightarrow \to \Swarrow \Searrow \Nwarrow \Nearrow
     \leftsquigarrow \overleftarrow \overleftrightarrow \cwopencirclearrow
     \downzigzagarrow \cupleftarrow \rightzigzagarrow \twoheaddownarrow
     \updownarrowbar \twoheaduparrow \rightarrowbar \updownarrows
     \barleftarrow \mapsfrom \mapsdown \mapsup \Ldsh \Rdsh
     """.split())

    _spaced_symbols = _binary_operators | _relation_symbols | _arrow_symbols

    _punctuation_symbols = set(r', ; . ! \ldotp \cdotp'.split())

    _overunder_symbols = set(r'''
       \sum \prod \coprod \bigcap \bigcup \bigsqcup \bigvee
       \bigwedge \bigodot \bigotimes \bigoplus \biguplus
       '''.split())

    _overunder_functions = set("lim liminf limsup sup max min".split())

    _dropsub_symbols = set(r'\int \oint \iint \oiint \iiint \oiiint \iiiint'.split())

    _fontnames = set("rm cal it tt sf bf bfit "
                     "default bb frak scr regular".split())

    _function_names = set("""
      arccos csc ker min arcsin deg lg Pr arctan det lim sec arg dim
      liminf sin cos exp limsup sinh cosh gcd ln sup cot hom log tan
      coth inf max tanh""".split())

    _ambi_delims = set(r"""
      | \| / \backslash \uparrow \downarrow \updownarrow \Uparrow
      \Downarrow \Updownarrow . \vert \Vert""".split())
    _left_delims = set(r"""
      ( [ \{ < \lfloor \langle \lceil \lbrace \leftbrace \lbrack \leftparen \lgroup
      """.split())
    _right_delims = set(r"""
      ) ] \} > \rfloor \rangle \rceil \rbrace \rightbrace \rbrack \rightparen \rgroup
      """.split())
    _delims = _left_delims | _right_delims | _ambi_delims

    _small_greek = set([unicodedata.name(chr(i)).split()[-1].lower() for i in
                       range(ord('\N{GREEK SMALL LETTER ALPHA}'),
                             ord('\N{GREEK SMALL LETTER OMEGA}') + 1)])
    _latin_alphabets = set(string.ascii_letters)

    def __init__(self) -> None:
        p = types.SimpleNamespace()

        def set_names_and_parse_actions() -> None:
            for key, val in vars(p).items():
                if not key.startswith('_'):
                    # Set names on (almost) everything -- very useful for debugging
                    # token, placeable, and auto_delim are forward references which
                    # are left without names to ensure useful error messages
                    if key not in ("token", "placeable", "auto_delim"):
                        val.set_name(key)
                    # Set actions
                    if hasattr(self, key):
                        val.set_parse_action(getattr(self, key))

        # Root definitions.

        # In TeX parlance, a csname is a control sequence name (a "\foo").
        def csnames(group: str, names: Iterable[str]) -> Regex:
            ends_with_alpha = []
            ends_with_nonalpha = []
            for name in names:
                if name[-1].isalpha():
                    ends_with_alpha.append(name)
                else:
                    ends_with_nonalpha.append(name)
            return Regex(
                r"\\(?P<{group}>(?:{alpha})(?![A-Za-z]){additional}{nonalpha})".format(
                    group=group,
                    alpha="|".join(map(re.escape, ends_with_alpha)),
                    additional="|" if ends_with_nonalpha else "",
                    nonalpha="|".join(map(re.escape, ends_with_nonalpha)),
                )
            )

        p.float_literal  = Regex(r"[-+]?([0-9]+\.?[0-9]*|\.[0-9]+)")
        p.space          = one_of(self._space_widths)("space")

        p.style_literal  = one_of(
            [str(e.value) for e in self._MathStyle])("style_literal")

        p.symbol         = Regex(
            r"[a-zA-Z0-9 +\-*/<>=:,.;!\?&'@()\[\]|\U00000080-\U0001ffff]"
            r"|\\[%${}\[\]_|]"
            + r"|\\(?:{})(?![A-Za-z])".format(
                "|".join(map(re.escape, tex2uni)))
        )("sym").leave_whitespace()
        p.unknown_symbol = Regex(r"\\[A-Za-z]+")("name")

        p.font           = csnames("font", self._fontnames)
        p.start_group    = Optional(r"\math" + one_of(self._fontnames)("font")) + "{"
        p.end_group      = Literal("}")

        p.delim          = one_of(self._delims)

        # Mutually recursive definitions.  (Minimizing the number of Forward
        # elements is important for speed.)
        p.auto_delim       = Forward()
        p.placeable        = Forward()
        p.named_placeable  = Forward()
        p.required_group   = Forward()
        p.optional_group   = Forward()
        p.token            = Forward()

        # Workaround for placable being part of a cycle of definitions
        # calling `p.placeable("name")` results in a copy, so not guaranteed
        # to get the definition added after it is used.
        # ref https://github.com/matplotlib/matplotlib/issues/25204
        # xref https://github.com/pyparsing/pyparsing/issues/95
        p.named_placeable <<= p.placeable

        set_names_and_parse_actions()  # for mutually recursive definitions.

        p.optional_group <<= "{" + ZeroOrMore(p.token)("group") + "}"
        p.required_group <<= "{" + OneOrMore(p.token)("group") + "}"

        p.customspace = cmd(r"\hspace", "{" + p.float_literal("space") + "}")

        p.accent = (
            csnames("accent", [*self._accent_map, *self._wide_accents])
            - p.named_placeable("sym"))

        p.function = csnames("name", self._function_names)

        p.group = p.start_group + ZeroOrMore(p.token)("group") + p.end_group
        p.unclosed_group = (p.start_group + ZeroOrMore(p.token)("group") + StringEnd())

        p.frac  = cmd(r"\frac", p.required_group("num") + p.required_group("den"))
        p.dfrac = cmd(r"\dfrac", p.required_group("num") + p.required_group("den"))
        p.binom = cmd(r"\binom", p.required_group("num") + p.required_group("den"))

        p.genfrac = cmd(
            r"\genfrac",
            "{" + Optional(p.delim)("ldelim") + "}"
            + "{" + Optional(p.delim)("rdelim") + "}"
            + "{" + p.float_literal("rulesize") + "}"
            + "{" + Optional(p.style_literal)("style") + "}"
            + p.required_group("num")
            + p.required_group("den"))

        p.sqrt = cmd(
            r"\sqrt{value}",
            Optional("[" + OneOrMore(NotAny("]") + p.token)("root") + "]")
            + p.required_group("value"))

        p.overline = cmd(r"\overline", p.required_group("body"))

        p.overset  = cmd(
            r"\overset",
            p.optional_group("annotation") + p.optional_group("body"))
        p.underset = cmd(
            r"\underset",
            p.optional_group("annotation") + p.optional_group("body"))

        p.text = cmd(r"\text", QuotedString('{', '\\', end_quote_char="}"))

        p.substack = cmd(r"\substack",
                           nested_expr(opener="{", closer="}",
                                       content=Group(OneOrMore(p.token)) +
                                       ZeroOrMore(Literal("\\\\").suppress()))("parts"))

        p.subsuper = (
            (Optional(p.placeable)("nucleus")
             + OneOrMore(one_of(["_", "^"]) - p.placeable)("subsuper")
             + Regex("'*")("apostrophes"))
            | Regex("'+")("apostrophes")
            | (p.named_placeable("nucleus") + Regex("'*")("apostrophes"))
        )

        p.simple = p.space | p.customspace | p.font | p.subsuper

        p.token <<= (
            p.simple
            | p.auto_delim
            | p.unclosed_group
            | p.unknown_symbol  # Must be last
        )

        p.operatorname = cmd(r"\operatorname", "{" + ZeroOrMore(p.simple)("name") + "}")

        p.boldsymbol = cmd(
            r"\boldsymbol", "{" + ZeroOrMore(p.simple)("value") + "}")

        p.placeable     <<= (
            p.accent     # Must be before symbol as all accents are symbols
            | p.symbol   # Must be second to catch all named symbols and single
                         # chars not in a group
            | p.function
            | p.operatorname
            | p.group
            | p.frac
            | p.dfrac
            | p.binom
            | p.genfrac
            | p.overset
            | p.underset
            | p.sqrt
            | p.overline
            | p.text
            | p.boldsymbol
            | p.substack
        )

        mdelim = r"\middle" - (p.delim("mdelim") | Error("Expected a delimiter"))
        p.auto_delim    <<= (
            r"\left" - (p.delim("left") | Error("Expected a delimiter"))
            + ZeroOrMore(p.simple | p.auto_delim | mdelim)("mid")
            + r"\right" - (p.delim("right") | Error("Expected a delimiter"))
        )

        # Leaf definitions.
        p.math          = OneOrMore(p.token)
        p.math_string   = QuotedString('$', '\\', unquote_results=False)
        p.non_math      = Regex(r"(?:(?:\\[$])|[^$])*").leave_whitespace()
        p.main          = (
            p.non_math + ZeroOrMore(p.math_string + p.non_math) + StringEnd()
        )
        set_names_and_parse_actions()  # for leaf definitions.

        self._expression = p.main
        self._math_expression = p.math

        # To add space to nucleus operators after sub/superscripts
        self._in_subscript_or_superscript = False

    def parse(self, s: str, fonts_object: Fonts, fontsize: float, dpi: float) -> Hlist:
        """
        Parse expression *s* using the given *fonts_object* for
        output, at the given *fontsize* and *dpi*.

        Returns the parse tree of `Node` instances.
        """
        self._state_stack = [
            ParserState(fonts_object, 'default', 'rm', fontsize, dpi)]
        self._em_width_cache: dict[tuple[str, float, float], float] = {}
        try:
            result = self._expression.parse_string(s)
        except ParseBaseException as err:
            # explain becomes a plain method on pyparsing 3 (err.explain(0)).
            raise ValueError("\n" + ParseException.explain(err, 0)) from None
        self._state_stack = []
        self._in_subscript_or_superscript = False
        # prevent operator spacing from leaking into a new expression
        self._em_width_cache = {}
        ParserElement.reset_cache()
        return T.cast(Hlist, result[0])  # Known return type from main.

    def get_state(self) -> ParserState:
        """Get the current `State` of the parser."""
        return self._state_stack[-1]

    def pop_state(self) -> None:
        """Pop a `State` off of the stack."""
        self._state_stack.pop()

    def push_state(self) -> None:
        """Push a new `State` onto the stack, copying the current state."""
        self._state_stack.append(self.get_state().copy())

    def main(self, toks: ParseResults) -> list[Hlist]:
        return [Hlist(toks.as_list())]

    def math_string(self, toks: ParseResults) -> ParseResults:
        return self._math_expression.parse_string(toks[0][1:-1], parse_all=True)

    def math(self, toks: ParseResults) -> T.Any:
        hlist = Hlist(toks.as_list())
        self.pop_state()
        return [hlist]

    def non_math(self, toks: ParseResults) -> T.Any:
        s = toks[0].replace(r'\$', '$')
        symbols = [Char(c, self.get_state()) for c in s]
        hlist = Hlist(symbols)
        # We're going into math now, so set font to 'it'
        self.push_state()
        self.get_state().font = mpl.rcParams['mathtext.default']
        return [hlist]

    float_literal = staticmethod(pyparsing_common.convert_to_float)

    def text(self, toks: ParseResults) -> T.Any:
        self.push_state()
        state = self.get_state()
        state.font = 'rm'
        hlist = Hlist([Char(c, state) for c in toks[1]])
        self.pop_state()
        return [hlist]

    def _make_space(self, percentage: float) -> Kern:
        # In TeX, an em (the unit usually used to measure horizontal lengths)
        # is not the width of the character 'm'; it is the same in different
        # font styles (e.g. roman or italic). Mathtext, however, uses 'm' in
        # the italic style so that horizontal spaces don't depend on the
        # current font style.
        state = self.get_state()
        key = (state.font, state.fontsize, state.dpi)
        width = self._em_width_cache.get(key)
        if width is None:
            metrics = state.fontset.get_metrics(
                'it', mpl.rcParams['mathtext.default'], 'm',
                state.fontsize, state.dpi)
            width = metrics.advance
            self._em_width_cache[key] = width
        return Kern(width * percentage)

    _space_widths = {
        r'\,':         0.16667,   # 3/18 em = 3 mu
        r'\thinspace': 0.16667,   # 3/18 em = 3 mu
        r'\/':         0.16667,   # 3/18 em = 3 mu
        r'\>':         0.22222,   # 4/18 em = 4 mu
        r'\:':         0.22222,   # 4/18 em = 4 mu
        r'\;':         0.27778,   # 5/18 em = 5 mu
        r'\ ':         0.33333,   # 6/18 em = 6 mu
        r'~':          0.33333,   # 6/18 em = 6 mu, nonbreakable
        r'\enspace':   0.5,       # 9/18 em = 9 mu
        r'\quad':      1,         # 1 em = 18 mu
        r'\qquad':     2,         # 2 em = 36 mu
        r'\!':         -0.16667,  # -3/18 em = -3 mu
    }

    def space(self, toks: ParseResults) -> T.Any:
        num = self._space_widths[toks["space"]]
        box = self._make_space(num)
        return [box]

    def customspace(self, toks: ParseResults) -> T.Any:
        return [self._make_space(toks["space"])]

    def symbol(self, s: str, loc: int,
               toks: ParseResults | dict[str, str]) -> T.Any:
        c = toks["sym"]
        if c == "-":
            # "U+2212 minus sign is the preferred representation of the unary
            # and binary minus sign rather than the ASCII-derived U+002D
            # hyphen-minus, because minus sign is unambiguous and because it
            # is rendered with a more desirable length, usually longer than a
            # hyphen." (https://www.unicode.org/reports/tr25/)
            c = "\N{MINUS SIGN}"
        try:
            char = Char(c, self.get_state())
        except ValueError as err:
            raise ParseFatalException(s, loc,
                                      "Unknown symbol: %s" % c) from err

        if c in self._spaced_symbols:
            # iterate until we find previous character, needed for cases
            # such as $=-2$, ${ -2}$, $ -2$, or $   -2$.
            prev_char = next((c for c in s[:loc][::-1] if c != ' '), '')
            # Binary operators at start of string should not be spaced
            # Also, operators in sub- or superscripts should not be spaced
            if (self._in_subscript_or_superscript or (
                    c in self._binary_operators and (
                    len(s[:loc].split()) == 0 or prev_char in {
                        '{', *self._left_delims, *self._relation_symbols}))):
                return [char]
            else:
                return [Hlist([self._make_space(0.2),
                               char,
                               self._make_space(0.2)],
                              do_kern=True)]
        elif c in self._punctuation_symbols:
            prev_char = next((c for c in s[:loc][::-1] if c != ' '), '')
            next_char = next((c for c in s[loc + 1:] if c != ' '), '')

            # Do not space commas between brackets
            if c == ',':
                if prev_char == '{' and next_char == '}':
                    return [char]

            # Do not space dots as decimal separators
            if c == '.' and prev_char.isdigit() and next_char.isdigit():
                return [char]
            else:
                return [Hlist([char, self._make_space(0.2)], do_kern=True)]
        return [char]

    def unknown_symbol(self, s: str, loc: int, toks: ParseResults) -> T.Any:
        raise ParseFatalException(s, loc, f"Unknown symbol: {toks['name']}")

    _accent_map = {
        r'hat':            r'\circumflexaccent',
        r'breve':          r'\combiningbreve',
        r'bar':            r'\combiningoverline',
        r'grave':          r'\combininggraveaccent',
        r'acute':          r'\combiningacuteaccent',
        r'tilde':          r'\combiningtilde',
        r'dot':            r'\combiningdotabove',
        r'ddot':           r'\combiningdiaeresis',
        r'dddot':          r'\combiningthreedotsabove',
        r'ddddot':         r'\combiningfourdotsabove',
        r'vec':            r'\combiningrightarrowabove',
        r'"':              r'\combiningdiaeresis',
        r"`":              r'\combininggraveaccent',
        r"'":              r'\combiningacuteaccent',
        r'~':              r'\combiningtilde',
        r'.':              r'\combiningdotabove',
        r'^':              r'\circumflexaccent',
        r'overrightarrow': r'\rightarrow',
        r'overleftarrow':  r'\leftarrow',
        r'mathring':       r'\circ',
    }

    _wide_accents = set(r"widehat widetilde widebar".split())

    def accent(self, toks: ParseResults) -> T.Any:
        state = self.get_state()
        thickness = state.get_current_underline_thickness()
        accent = toks["accent"]
        sym = toks["sym"]
        accent_box: Node
        if accent in self._wide_accents:
            accent_box = AutoWidthChar(
                '\\' + accent, sym.width, state, char_class=Accent)
        else:
            accent_box = Accent(self._accent_map[accent], state)
        if accent == 'mathring':
            accent_box.shrink()
            accent_box.shrink()
        centered = HCentered([Hbox(sym.width / 4.0), accent_box])
        centered.hpack(sym.width, 'exactly')
        return Vlist([
                centered,
                Vbox(0., thickness * 2.0),
                Hlist([sym])
                ])

    def function(self, s: str, loc: int, toks: ParseResults) -> T.Any:
        hlist = self.operatorname(s, loc, toks)
        hlist.function_name = toks["name"]
        return hlist

    def operatorname(self, s: str, loc: int, toks: ParseResults) -> T.Any:
        self.push_state()
        state = self.get_state()
        state.font = 'rm'
        hlist_list: list[Node] = []
        # Change the font of Chars, but leave Kerns alone
        name = toks["name"]
        for c in name:
            if isinstance(c, Char):
                c.font = 'rm'
                c._update_metrics()
                hlist_list.append(c)
            elif isinstance(c, str):
                hlist_list.append(Char(c, state))
            else:
                hlist_list.append(c)
        next_char_loc = loc + len(name) + 1
        if isinstance(name, ParseResults):
            next_char_loc += len('operatorname{}')
        next_char = next((c for c in s[next_char_loc:] if c != ' '), '')
        delimiters = self._delims | {'^', '_'}
        if (next_char not in delimiters and
                name not in self._overunder_functions):
            # Add thin space except when followed by parenthesis, bracket, etc.
            hlist_list += [self._make_space(self._space_widths[r'\,'])]
        self.pop_state()
        # if followed by a super/subscript, set flag to true
        # This flag tells subsuper to add space after this operator
        if next_char in {'^', '_'}:
            self._in_subscript_or_superscript = True
        else:
            self._in_subscript_or_superscript = False

        return Hlist(hlist_list)

    def start_group(self, toks: ParseResults) -> T.Any:
        self.push_state()
        # Deal with LaTeX-style font tokens
        if toks.get("font"):
            self.get_state().font = toks.get("font")
        return []

    def group(self, toks: ParseResults) -> T.Any:
        grp = Hlist(toks.get("group", []))
        return [grp]

    def required_group(self, toks: ParseResults) -> T.Any:
        return Hlist(toks.get("group", []))

    optional_group = required_group

    def end_group(self) -> T.Any:
        self.pop_state()
        return []

    def unclosed_group(self, s: str, loc: int, toks: ParseResults) -> T.Any:
        raise ParseFatalException(s, len(s), "Expected '}'")

    def font(self, toks: ParseResults) -> T.Any:
        self.get_state().font = toks["font"]
        return []

    def is_overunder(self, nucleus: Node) -> bool:
        if isinstance(nucleus, Char):
            return nucleus.c in self._overunder_symbols
        elif isinstance(nucleus, Hlist) and hasattr(nucleus, 'function_name'):
            return nucleus.function_name in self._overunder_functions
        return False

    def is_dropsub(self, nucleus: Node) -> bool:
        if isinstance(nucleus, Char):
            return nucleus.c in self._dropsub_symbols
        return False

    def is_slanted(self, nucleus: Node) -> bool:
        if isinstance(nucleus, Char):
            return nucleus.is_slanted()
        return False

    def subsuper(self, s: str, loc: int, toks: ParseResults) -> T.Any:
        nucleus = toks.get("nucleus", Hbox(0))
        subsuper = toks.get("subsuper", [])
        napostrophes = len(toks.get("apostrophes", []))

        if not subsuper and not napostrophes:
            return nucleus

        sub = super = None
        while subsuper:
            op, arg, *subsuper = subsuper
            if op == '_':
                if sub is not None:
                    raise ParseFatalException("Double subscript")
                sub = arg
            else:
                if super is not None:
                    raise ParseFatalException("Double superscript")
                super = arg

        state = self.get_state()
        rule_thickness = state.fontset.get_underline_thickness(
            state.font, state.fontsize, state.dpi)
        xHeight = state.fontset.get_xheight(
            state.font, state.fontsize, state.dpi)

        if napostrophes:
            if super is None:
                super = Hlist([])
            for i in range(napostrophes):
                super.children.extend(self.symbol(s, loc, {"sym": "\\prime"}))
            # kern() and hpack() needed to get the metrics right after
            # extending
            super.kern()
            super.hpack()

        # Handle over/under symbols, such as sum or prod
        if self.is_overunder(nucleus):
            vlist = []
            shift = 0.
            width = nucleus.width
            if super is not None:
                super.shrink()
                width = max(width, super.width)
            if sub is not None:
                sub.shrink()
                width = max(width, sub.width)

            vgap = rule_thickness * 3.0
            if super is not None:
                hlist = HCentered([super])
                hlist.hpack(width, 'exactly')
                vlist.extend([hlist, Vbox(0, vgap)])
            hlist = HCentered([nucleus])
            hlist.hpack(width, 'exactly')
            vlist.append(hlist)
            if sub is not None:
                hlist = HCentered([sub])
                hlist.hpack(width, 'exactly')
                vlist.extend([Vbox(0, vgap), hlist])
                shift = hlist.height + vgap + nucleus.depth
            vlt = Vlist(vlist)
            vlt.shift_amount = shift
            result = Hlist([vlt])
            return [result]

        # We remove kerning on the last character for consistency (otherwise
        # it will compute kerning based on non-shrunk characters and may put
        # them too close together when superscripted)
        # We change the width of the last character to match the advance to
        # consider some fonts with weird metrics: e.g. stix's f has a width of
        # 7.75 and a kerning of -4.0 for an advance of 3.72, and we want to put
        # the superscript at the advance
        last_char = nucleus
        if isinstance(nucleus, Hlist):
            new_children = nucleus.children
            if len(new_children):
                # remove last kern
                if (isinstance(new_children[-1], Kern) and
                        isinstance(new_children[-2], Char)):
                    new_children = new_children[:-1]
                last_char = new_children[-1]
                if isinstance(last_char, Char):
                    last_char.width = last_char._metrics.advance
            # create new Hlist without kerning
            nucleus = Hlist(new_children, do_kern=False)
        else:
            if isinstance(nucleus, Char):
                last_char.width = last_char._metrics.advance
            nucleus = Hlist([nucleus])

        # Handle regular sub/superscripts
        constants = _get_font_constant_set(state)
        lc_height   = last_char.height
        lc_baseline = 0
        if self.is_dropsub(last_char):
            lc_baseline = last_char.depth

        # Compute kerning for sub and super
        superkern = constants.delta * xHeight
        subkern = constants.delta * xHeight
        if self.is_slanted(last_char):
            superkern += constants.delta * xHeight
            superkern += (constants.delta_slanted *
                          (lc_height - xHeight * 2. / 3.))
            if self.is_dropsub(last_char):
                subkern = (3 * constants.delta -
                           constants.delta_integral) * lc_height
                superkern = (3 * constants.delta +
                             constants.delta_integral) * lc_height
            else:
                subkern = 0

        x: List
        if super is None:
            # node757
            # Note: One of super or sub must be a Node if we're in this function, but
            # mypy can't know this, since it can't interpret pyparsing expressions,
            # hence the cast.
            x = Hlist([Kern(subkern), T.cast(Node, sub)])
            x.shrink()
            if self.is_dropsub(last_char):
                shift_down = lc_baseline + constants.subdrop * xHeight
            else:
                shift_down = constants.sub1 * xHeight
            x.shift_amount = shift_down
        else:
            x = Hlist([Kern(superkern), super])
            x.shrink()
            if self.is_dropsub(last_char):
                shift_up = lc_height - constants.subdrop * xHeight
            else:
                shift_up = constants.sup1 * xHeight
            if sub is None:
                x.shift_amount = -shift_up
            else:  # Both sub and superscript
                y = Hlist([Kern(subkern), sub])
                y.shrink()
                if self.is_dropsub(last_char):
                    shift_down = lc_baseline + constants.subdrop * xHeight
                else:
                    shift_down = constants.sub2 * xHeight
                # If sub and superscript collide, move super up
                clr = (2.0 * rule_thickness -
                       ((shift_up - x.depth) - (y.height - shift_down)))
                if clr > 0.:
                    shift_up += clr
                x = Vlist([
                    x,
                    Kern((shift_up - x.depth) - (y.height - shift_down)),
                    y])
                x.shift_amount = shift_down

        if not self.is_dropsub(last_char):
            x.width += constants.script_space * xHeight

        # Do we need to add a space after the nucleus?
        # To find out, check the flag set by operatorname
        spaced_nucleus: list[Node] = [nucleus, x]
        if self._in_subscript_or_superscript:
            spaced_nucleus += [self._make_space(self._space_widths[r'\,'])]
            self._in_subscript_or_superscript = False

        result = Hlist(spaced_nucleus)
        return [result]

    def _genfrac(self, ldelim: str, rdelim: str, rule: float | None, style: _MathStyle,
                 num: Hlist, den: Hlist) -> T.Any:
        state = self.get_state()
        thickness = state.get_current_underline_thickness()

        for _ in range(style.value):
            num.shrink()
            den.shrink()
        cnum = HCentered([num])
        cden = HCentered([den])
        width = max(num.width, den.width)
        cnum.hpack(width, 'exactly')
        cden.hpack(width, 'exactly')
        vlist = Vlist([cnum,                      # numerator
                       Vbox(0, thickness * 2.0),  # space
                       Hrule(state, rule),        # rule
                       Vbox(0, thickness * 2.0),  # space
                       cden                       # denominator
                       ])

        # Shift so the fraction line sits in the middle of the
        # equals sign
        metrics = state.fontset.get_metrics(
            state.font, mpl.rcParams['mathtext.default'],
            '=', state.fontsize, state.dpi)
        shift = (cden.height -
                 ((metrics.ymax + metrics.ymin) / 2 -
                  thickness * 3.0))
        vlist.shift_amount = shift

        result = [Hlist([vlist, Hbox(thickness * 2.)])]
        if ldelim or rdelim:
            if ldelim == '':
                ldelim = '.'
            if rdelim == '':
                rdelim = '.'
            return self._auto_sized_delimiter(ldelim,
                                              T.cast(list[Box | Char | str],
                                                     result),
                                              rdelim)
        return result

    def style_literal(self, toks: ParseResults) -> T.Any:
        return self._MathStyle(int(toks["style_literal"]))

    def genfrac(self, toks: ParseResults) -> T.Any:
        return self._genfrac(
            toks.get("ldelim", ""), toks.get("rdelim", ""),
            toks["rulesize"], toks.get("style", self._MathStyle.TEXTSTYLE),
            toks["num"], toks["den"])

    def frac(self, toks: ParseResults) -> T.Any:
        return self._genfrac(
            "", "", self.get_state().get_current_underline_thickness(),
            self._MathStyle.TEXTSTYLE, toks["num"], toks["den"])

    def dfrac(self, toks: ParseResults) -> T.Any:
        return self._genfrac(
            "", "", self.get_state().get_current_underline_thickness(),
            self._MathStyle.DISPLAYSTYLE, toks["num"], toks["den"])

    def binom(self, toks: ParseResults) -> T.Any:
        return self._genfrac(
            "(", ")", 0,
            self._MathStyle.TEXTSTYLE, toks["num"], toks["den"])

    def _genset(self, s: str, loc: int, toks: ParseResults) -> T.Any:
        annotation = toks["annotation"]
        body = toks["body"]
        thickness = self.get_state().get_current_underline_thickness()

        annotation.shrink()
        centered_annotation = HCentered([annotation])
        centered_body = HCentered([body])
        width = max(centered_annotation.width, centered_body.width)
        centered_annotation.hpack(width, 'exactly')
        centered_body.hpack(width, 'exactly')

        vgap = thickness * 3
        if s[loc + 1] == "u":  # \underset
            vlist = Vlist([
                centered_body,               # body
                Vbox(0, vgap),               # space
                centered_annotation          # annotation
            ])
            # Shift so the body sits in the same vertical position
            vlist.shift_amount = centered_body.depth + centered_annotation.height + vgap
        else:  # \overset
            vlist = Vlist([
                centered_annotation,         # annotation
                Vbox(0, vgap),               # space
                centered_body                # body
            ])

        # To add horizontal gap between symbols: wrap the Vlist into
        # an Hlist and extend it with an Hbox(0, horizontal_gap)
        return vlist

    overset = underset = _genset

    def sqrt(self, toks: ParseResults) -> T.Any:
        root = toks.get("root")
        body = toks["value"]
        state = self.get_state()
        thickness = state.get_current_underline_thickness()

        # Determine the height of the body, and add a little extra to
        # the height so it doesn't seem cramped
        height = body.height - body.shift_amount + thickness * 5.0
        depth = body.depth + body.shift_amount
        check = AutoHeightChar(r'\__sqrt__', height, depth, state, always=True)
        height = check.height - check.shift_amount
        depth = check.depth + check.shift_amount

        # Put a little extra space to the left and right of the body
        padded_body = Hlist([Hbox(2 * thickness), body, Hbox(2 * thickness)])
        rightside = Vlist([Hrule(state), Glue('fill'), padded_body])
        # Stretch the glue between the hrule and the body
        rightside.vpack(height + (state.fontsize * state.dpi) / (100.0 * 12.0),
                        'exactly', depth)

        # Add the root and shift it upward so it is above the tick.
        # The value of 0.6 is a hard-coded hack ;)
        if not root:
            root = Box(check.width * 0.5, 0., 0.)
        else:
            root = Hlist(root)
            root.shrink()
            root.shrink()

        root_vlist = Vlist([Hlist([root])])
        root_vlist.shift_amount = -height * 0.6

        hlist = Hlist([root_vlist,               # Root
                       # Negative kerning to put root over tick
                       Kern(-check.width * 0.5),
                       check,                    # Check
                       rightside])               # Body
        return [hlist]

    def overline(self, toks: ParseResults) -> T.Any:
        body = toks["body"]

        state = self.get_state()
        thickness = state.get_current_underline_thickness()

        height = body.height - body.shift_amount + thickness * 3.0
        depth = body.depth + body.shift_amount

        # Place overline above body
        rightside = Vlist([Hrule(state), Glue('fill'), Hlist([body])])

        # Stretch the glue between the hrule and the body
        rightside.vpack(height + (state.fontsize * state.dpi) / (100.0 * 12.0),
                        'exactly', depth)

        hlist = Hlist([rightside])
        return [hlist]

    def _auto_sized_delimiter(self, front: str,
                              middle: list[Box | Char | str],
                              back: str) -> T.Any:
        state = self.get_state()
        if len(middle):
            height = max([x.height for x in middle if not isinstance(x, str)])
            depth = max([x.depth for x in middle if not isinstance(x, str)])
            factor = None
            for idx, el in enumerate(middle):
                if el == r'\middle':
                    c = T.cast(str, middle[idx + 1])  # Should be one of p.delims.
                    if c != '.':
                        middle[idx + 1] = AutoHeightChar(
                                c, height, depth, state, factor=factor)
                    else:
                        middle.remove(c)
                    del middle[idx]
            # There should only be \middle and its delimiter as str, which have
            # just been removed.
            middle_part = T.cast(list[Box | Char], middle)
        else:
            height = 0
            depth = 0
            factor = 1.0
            middle_part = []

        parts: list[Node] = []
        # \left. and \right. aren't supposed to produce any symbols
        if front != '.':
            parts.append(
                AutoHeightChar(front, height, depth, state, factor=factor))
        parts.extend(middle_part)
        if back != '.':
            parts.append(
                AutoHeightChar(back, height, depth, state, factor=factor))
        hlist = Hlist(parts)
        return hlist

    def auto_delim(self, toks: ParseResults) -> T.Any:
        return self._auto_sized_delimiter(
            toks["left"],
            # if "mid" in toks ... can be removed when requiring pyparsing 3.
            toks["mid"].as_list() if "mid" in toks else [],
            toks["right"])

    def boldsymbol(self, toks: ParseResults) -> T.Any:
        self.push_state()
        state = self.get_state()
        hlist: list[Node] = []
        name = toks["value"]
        for c in name:
            if isinstance(c, Hlist):
                k = c.children[1]
                if isinstance(k, Char):
                    k.font = "bf"
                    k._update_metrics()
                hlist.append(c)
            elif isinstance(c, Char):
                c.font = "bf"
                if (c.c in self._latin_alphabets or
                   c.c[1:] in self._small_greek):
                    c.font = "bfit"
                    c._update_metrics()
                c._update_metrics()
                hlist.append(c)
            else:
                hlist.append(c)
        self.pop_state()

        return Hlist(hlist)

    def substack(self, toks: ParseResults) -> T.Any:
        parts = toks["parts"]
        state = self.get_state()
        thickness = state.get_current_underline_thickness()

        hlist = [Hlist(k) for k in parts[0]]
        max_width = max(map(lambda c: c.width, hlist))

        vlist = []
        for sub in hlist:
            cp = HCentered([sub])
            cp.hpack(max_width, 'exactly')
            vlist.append(cp)

        stack = [val
                 for pair in zip(vlist, [Vbox(0, thickness * 2)] * len(vlist))
                 for val in pair]
        del stack[-1]
        vlt = Vlist(stack)
        result = [Hlist([vlt])]
        return result
