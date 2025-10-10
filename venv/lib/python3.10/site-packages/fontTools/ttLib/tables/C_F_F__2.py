from io import BytesIO
from fontTools.ttLib.tables.C_F_F_ import table_C_F_F_


class table_C_F_F__2(table_C_F_F_):
    """Compact Font Format version 2 table

    The ``CFF2`` table contains glyph data for a CFF2-flavored OpenType
    font.

    .. note::
       ``CFF2`` is the successor to ``CFF``, and eliminates much of
       the redundancy incurred by embedding CFF version 1 in an OpenType
       font.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/cff2
    """

    def decompile(self, data, otFont):
        self.cff.decompile(BytesIO(data), otFont, isCFF2=True)
        assert len(self.cff) == 1, "can't deal with multi-font CFF tables."

    def compile(self, otFont):
        f = BytesIO()
        self.cff.compile(f, otFont, isCFF2=True)
        return f.getvalue()
