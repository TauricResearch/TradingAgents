from .otBase import BaseTTXConverter


# https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6mort.html
class table__m_o_r_t(BaseTTXConverter):
    """The AAT ``mort`` table contains glyph transformations used for script shaping and
    for various other optional smart features.

    Note: ``mort`` has been deprecated in favor of the newer ``morx`` table.

    See also https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6mort.html
    """

    pass
