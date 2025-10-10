import json
from textwrap import indent

from . import DefaultTable
from fontTools.misc.textTools import tostr


class table_D__e_b_g(DefaultTable.DefaultTable):
    def __init__(self, tag=None):
        DefaultTable.DefaultTable.__init__(self, tag)
        self.data = {}

    def decompile(self, data, ttFont):
        self.data = json.loads(data)

    def compile(self, ttFont):
        return json.dumps(self.data).encode("utf-8")

    def toXML(self, writer, ttFont):
        # make sure json indentation inside CDATA block matches XMLWriter's
        data = json.dumps(self.data, indent=len(writer.indentwhite))
        prefix = tostr(writer.indentwhite) * (writer.indentlevel + 1)
        # but don't indent the first json line so it's adjacent to `<![CDATA[{`
        cdata = indent(data, prefix, lambda ln: ln != "{\n")

        writer.begintag("json")
        writer.newline()
        writer.writecdata(cdata)
        writer.newline()
        writer.endtag("json")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "json":
            self.data = json.loads("".join(content))
