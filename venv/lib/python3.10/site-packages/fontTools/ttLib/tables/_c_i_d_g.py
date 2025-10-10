# coding: utf-8
from .otBase import BaseTTXConverter


class table__c_i_d_g(BaseTTXConverter):
    """CID to Glyph ID table

    The AAT ``cidg`` table has almost the same structure as ``gidc``,
    just mapping CIDs to GlyphIDs instead of the reverse direction.

    It is useful for fonts that may be used by a PDF renderer in lieu of
    a font reference with a known glyph collection but no subsetted
    glyphs.  For instance, a PDF can say “please use a font conforming
    to Adobe-Japan-1”; the ``cidg`` mapping is necessary if the font is,
    say, a TrueType font.  ``gidc`` is lossy for this purpose and is
    obsoleted by ``cidg``.

    For example, the first font in ``/System/Library/Fonts/PingFang.ttc``
    (which Apple ships pre-installed on MacOS 10.12.6) has a ``cidg`` table.

    See also https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6gcid.html
    """

    pass
