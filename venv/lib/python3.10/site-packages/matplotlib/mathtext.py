r"""
A module for parsing a subset of the TeX math syntax and rendering it to a
Matplotlib backend.

For a tutorial of its usage, see :ref:`mathtext`.  This
document is primarily concerned with implementation details.

The module uses pyparsing_ to parse the TeX expression.

.. _pyparsing: https://pypi.org/project/pyparsing/

The Bakoma distribution of the TeX Computer Modern fonts, and STIX
fonts are supported.  There is experimental support for using
arbitrary fonts, but results may vary without proper tweaking and
metrics for those fonts.
"""

import functools
import logging

import matplotlib as mpl
from matplotlib import _api, _mathtext
from matplotlib.ft2font import LoadFlags
from matplotlib.font_manager import FontProperties
from ._mathtext import (  # noqa: F401, reexported API
    RasterParse, VectorParse, get_unicode_index)

_log = logging.getLogger(__name__)


get_unicode_index.__module__ = __name__

##############################################################################
# MAIN


class MathTextParser:
    _parser = None
    _font_type_mapping = {
        'cm':          _mathtext.BakomaFonts,
        'dejavuserif': _mathtext.DejaVuSerifFonts,
        'dejavusans':  _mathtext.DejaVuSansFonts,
        'stix':        _mathtext.StixFonts,
        'stixsans':    _mathtext.StixSansFonts,
        'custom':      _mathtext.UnicodeFonts,
    }

    def __init__(self, output):
        """
        Create a MathTextParser for the given backend *output*.

        Parameters
        ----------
        output : {"path", "agg"}
            Whether to return a `VectorParse` ("path") or a
            `RasterParse` ("agg", or its synonym "macosx").
        """
        self._output_type = _api.check_getitem(
            {"path": "vector", "agg": "raster", "macosx": "raster"},
            output=output.lower())

    def parse(self, s, dpi=72, prop=None, *, antialiased=None):
        """
        Parse the given math expression *s* at the given *dpi*.  If *prop* is
        provided, it is a `.FontProperties` object specifying the "default"
        font to use in the math expression, used for all non-math text.

        The results are cached, so multiple calls to `parse`
        with the same expression should be fast.

        Depending on the *output* type, this returns either a `VectorParse` or
        a `RasterParse`.
        """
        # lru_cache can't decorate parse() directly because prop is
        # mutable, so we key the cache using an internal copy (see
        # Text._get_text_metrics_with_cache for a similar case); likewise,
        # we need to check the mutable state of the text.antialiased and
        # text.hinting rcParams.
        prop = prop.copy() if prop is not None else None
        antialiased = mpl._val_or_rc(antialiased, 'text.antialiased')
        from matplotlib.backends import backend_agg
        load_glyph_flags = {
            "vector": LoadFlags.NO_HINTING,
            "raster": backend_agg.get_hinting_flag(),
        }[self._output_type]
        return self._parse_cached(s, dpi, prop, antialiased, load_glyph_flags)

    @functools.lru_cache(50)
    def _parse_cached(self, s, dpi, prop, antialiased, load_glyph_flags):
        if prop is None:
            prop = FontProperties()
        fontset_class = _api.check_getitem(
            self._font_type_mapping, fontset=prop.get_math_fontfamily())
        fontset = fontset_class(prop, load_glyph_flags)
        fontsize = prop.get_size_in_points()

        if self._parser is None:  # Cache the parser globally.
            self.__class__._parser = _mathtext.Parser()

        box = self._parser.parse(s, fontset, fontsize, dpi)
        output = _mathtext.ship(box)
        if self._output_type == "vector":
            return output.to_vector()
        elif self._output_type == "raster":
            return output.to_raster(antialiased=antialiased)


def math_to_image(s, filename_or_obj, prop=None, dpi=None, format=None,
                  *, color=None):
    """
    Given a math expression, renders it in a closely-clipped bounding
    box to an image file.

    Parameters
    ----------
    s : str
        A math expression.  The math portion must be enclosed in dollar signs.
    filename_or_obj : str or path-like or file-like
        Where to write the image data.
    prop : `.FontProperties`, optional
        The size and style of the text.
    dpi : float, optional
        The output dpi.  If not set, the dpi is determined as for
        `.Figure.savefig`.
    format : str, optional
        The output format, e.g., 'svg', 'pdf', 'ps' or 'png'.  If not set, the
        format is determined as for `.Figure.savefig`.
    color : str, optional
        Foreground color, defaults to :rc:`text.color`.
    """
    from matplotlib import figure

    parser = MathTextParser('path')
    width, height, depth, _, _ = parser.parse(s, dpi=72, prop=prop)

    fig = figure.Figure(figsize=(width / 72.0, height / 72.0))
    fig.text(0, depth/height, s, fontproperties=prop, color=color)
    fig.savefig(filename_or_obj, dpi=dpi, format=format)

    return depth
