from fontTools import ttLib

superclass = ttLib.getTableClass("fpgm")


class table__p_r_e_p(superclass):
    """Control Value Program table

    The ``prep`` table contains TrueType instructions that can makee font-wide
    alterations to the Control Value Table. It may potentially be executed
    before any glyph is processed.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/prep
    """

    pass
