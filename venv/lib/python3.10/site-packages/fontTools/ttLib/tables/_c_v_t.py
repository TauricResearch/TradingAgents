from fontTools.misc.textTools import safeEval
from . import DefaultTable
import sys
import array


class table__c_v_t(DefaultTable.DefaultTable):
    """Control Value Table

    The Control Value Table holds a list of values that can be referenced
    by TrueType font instructions.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/cvt
    """

    def decompile(self, data, ttFont):
        values = array.array("h")
        values.frombytes(data)
        if sys.byteorder != "big":
            values.byteswap()
        self.values = values

    def compile(self, ttFont):
        if not hasattr(self, "values"):
            return b""
        values = self.values[:]
        if sys.byteorder != "big":
            values.byteswap()
        return values.tobytes()

    def toXML(self, writer, ttFont):
        for i, value in enumerate(self.values):
            writer.simpletag("cv", value=value, index=i)
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if not hasattr(self, "values"):
            self.values = array.array("h")
        if name == "cv":
            index = safeEval(attrs["index"])
            value = safeEval(attrs["value"])
            for i in range(1 + index - len(self.values)):
                self.values.append(0)
            self.values[index] = value

    def __len__(self):
        return len(self.values)

    def __getitem__(self, index):
        return self.values[index]

    def __setitem__(self, index, value):
        self.values[index] = value

    def __delitem__(self, index):
        del self.values[index]
