from .otBase import BaseTTXConverter


# https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6bsln.html
class table__b_s_l_n(BaseTTXConverter):
    """Baseline table

    The AAT ``bsln`` table is similar in purpose to the OpenType ``BASE``
    table; it stores per-script baselines to support automatic alignment
    of lines of text.

    See also https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6bsln.html
    """

    pass
