from .otBase import BaseTTXConverter


# https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6gcid.html
class table__g_c_i_d(BaseTTXConverter):
    """Glyph ID to CID table

    The AAT ``gcid`` table stores glyphID-to-CID mappings.

    See also https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6gcid.html
    """

    pass
