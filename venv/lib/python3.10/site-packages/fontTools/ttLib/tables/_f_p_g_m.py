from . import DefaultTable
from . import ttProgram


class table__f_p_g_m(DefaultTable.DefaultTable):
    """Font Program table

    The ``fpgm`` table typically contains function defintions that are
    used by font instructions. This Font Program is similar to the Control
    Value Program that is stored in the ``prep`` table, but
    the ``fpgm`` table is only executed one time, when the font is first
    used.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/fpgm
    """

    def decompile(self, data, ttFont):
        program = ttProgram.Program()
        program.fromBytecode(data)
        self.program = program

    def compile(self, ttFont):
        if hasattr(self, "program"):
            return self.program.getBytecode()
        return b""

    def toXML(self, writer, ttFont):
        self.program.toXML(writer, ttFont)

    def fromXML(self, name, attrs, content, ttFont):
        program = ttProgram.Program()
        program.fromXML(name, attrs, content, ttFont)
        self.program = program

    def __bool__(self):
        """
        >>> fpgm = table__f_p_g_m()
        >>> bool(fpgm)
        False
        >>> p = ttProgram.Program()
        >>> fpgm.program = p
        >>> bool(fpgm)
        False
        >>> bc = bytearray([0])
        >>> p.fromBytecode(bc)
        >>> bool(fpgm)
        True
        >>> p.bytecode.pop()
        0
        >>> bool(fpgm)
        False
        """
        return hasattr(self, "program") and bool(self.program)

    __nonzero__ = __bool__


if __name__ == "__main__":
    import sys
    import doctest

    sys.exit(doctest.testmod().failed)
