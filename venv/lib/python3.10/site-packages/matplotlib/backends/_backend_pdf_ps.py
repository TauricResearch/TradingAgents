"""
Common functionality between the PDF and PS backends.
"""

from io import BytesIO
import functools
import logging

from fontTools import subset

import matplotlib as mpl
from .. import font_manager, ft2font
from .._afm import AFM
from ..backend_bases import RendererBase


@functools.lru_cache(50)
def _cached_get_afm_from_fname(fname):
    with open(fname, "rb") as fh:
        return AFM(fh)


def get_glyphs_subset(fontfile, characters):
    """
    Subset a TTF font

    Reads the named fontfile and restricts the font to the characters.

    Parameters
    ----------
    fontfile : str
        Path to the font file
    characters : str
        Continuous set of characters to include in subset

    Returns
    -------
    fontTools.ttLib.ttFont.TTFont
        An open font object representing the subset, which needs to
        be closed by the caller.
    """

    options = subset.Options(glyph_names=True, recommended_glyphs=True)

    # Prevent subsetting extra tables.
    options.drop_tables += [
        'FFTM',  # FontForge Timestamp.
        'PfEd',  # FontForge personal table.
        'BDF',  # X11 BDF header.
        'meta',  # Metadata stores design/supported languages (meaningless for subsets).
        'MERG',  # Merge Table.
        'TSIV',  # Microsoft Visual TrueType extension.
        'Zapf',  # Information about the individual glyphs in the font.
        'bdat',  # The bitmap data table.
        'bloc',  # The bitmap location table.
        'cidg',  # CID to Glyph ID table (Apple Advanced Typography).
        'fdsc',  # The font descriptors table.
        'feat',  # Feature name table (Apple Advanced Typography).
        'fmtx',  # The Font Metrics Table.
        'fond',  # Data-fork font information (Apple Advanced Typography).
        'just',  # The justification table (Apple Advanced Typography).
        'kerx',  # An extended kerning table (Apple Advanced Typography).
        'ltag',  # Language Tag.
        'morx',  # Extended Glyph Metamorphosis Table.
        'trak',  # Tracking table.
        'xref',  # The cross-reference table (some Apple font tooling information).
    ]
    # if fontfile is a ttc, specify font number
    if fontfile.endswith(".ttc"):
        options.font_number = 0

    font = subset.load_font(fontfile, options)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text=characters)
    subsetter.subset(font)
    return font


def font_as_file(font):
    """
    Convert a TTFont object into a file-like object.

    Parameters
    ----------
    font : fontTools.ttLib.ttFont.TTFont
        A font object

    Returns
    -------
    BytesIO
        A file object with the font saved into it
    """
    fh = BytesIO()
    font.save(fh, reorderTables=False)
    return fh


class CharacterTracker:
    """
    Helper for font subsetting by the pdf and ps backends.

    Maintains a mapping of font paths to the set of character codepoints that
    are being used from that font.
    """

    def __init__(self):
        self.used = {}

    def track(self, font, s):
        """Record that string *s* is being typeset using font *font*."""
        char_to_font = font._get_fontmap(s)
        for _c, _f in char_to_font.items():
            self.used.setdefault(_f.fname, set()).add(ord(_c))

    def track_glyph(self, font, glyph):
        """Record that codepoint *glyph* is being typeset using font *font*."""
        self.used.setdefault(font.fname, set()).add(glyph)


class RendererPDFPSBase(RendererBase):
    # The following attributes must be defined by the subclasses:
    # - _afm_font_dir
    # - _use_afm_rc_name

    def __init__(self, width, height):
        super().__init__()
        self.width = width
        self.height = height

    def flipy(self):
        # docstring inherited
        return False  # y increases from bottom to top.

    def option_scale_image(self):
        # docstring inherited
        return True  # PDF and PS support arbitrary image scaling.

    def option_image_nocomposite(self):
        # docstring inherited
        # Decide whether to composite image based on rcParam value.
        return not mpl.rcParams["image.composite_image"]

    def get_canvas_width_height(self):
        # docstring inherited
        return self.width * 72.0, self.height * 72.0

    def get_text_width_height_descent(self, s, prop, ismath):
        # docstring inherited
        if ismath == "TeX":
            return super().get_text_width_height_descent(s, prop, ismath)
        elif ismath:
            parse = self._text2path.mathtext_parser.parse(s, 72, prop)
            return parse.width, parse.height, parse.depth
        elif mpl.rcParams[self._use_afm_rc_name]:
            font = self._get_font_afm(prop)
            l, b, w, h, d = font.get_str_bbox_and_descent(s)
            scale = prop.get_size_in_points() / 1000
            w *= scale
            h *= scale
            d *= scale
            return w, h, d
        else:
            font = self._get_font_ttf(prop)
            font.set_text(s, 0.0, flags=ft2font.LoadFlags.NO_HINTING)
            w, h = font.get_width_height()
            d = font.get_descent()
            scale = 1 / 64
            w *= scale
            h *= scale
            d *= scale
            return w, h, d

    def _get_font_afm(self, prop):
        fname = font_manager.findfont(
            prop, fontext="afm", directory=self._afm_font_dir)
        return _cached_get_afm_from_fname(fname)

    def _get_font_ttf(self, prop):
        fnames = font_manager.fontManager._find_fonts_by_props(prop)
        try:
            font = font_manager.get_font(fnames)
            font.clear()
            font.set_size(prop.get_size_in_points(), 72)
            return font
        except RuntimeError:
            logging.getLogger(__name__).warning(
                "The PostScript/PDF backend does not currently "
                "support the selected font (%s).", fnames)
            raise
