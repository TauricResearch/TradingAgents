from fontTools.misc.textTools import strjoin, tobytes, tostr
from . import DefaultTable


class asciiTable(DefaultTable.DefaultTable):
    def toXML(self, writer, ttFont):
        data = tostr(self.data)
        # removing null bytes. XXX needed??
        data = data.split("\0")
        data = strjoin(data)
        writer.begintag("source")
        writer.newline()
        writer.write_noindent(data)
        writer.newline()
        writer.endtag("source")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        lines = strjoin(content).split("\n")
        self.data = tobytes("\n".join(lines[1:-1]))
