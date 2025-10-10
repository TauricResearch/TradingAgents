from .otBase import BaseTTXConverter


# https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6morx.html
class table__m_o_r_x(BaseTTXConverter):
    """The AAT ``morx`` table contains glyph transformations used for script shaping and
    for various other optional smart features, akin to ``GSUB`` and ``GPOS`` features
    in OpenType Layout.

    Note: ``morx`` is a replacement for the now deprecated ``mort`` table.

    See also https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6morx.html
    """

    pass
