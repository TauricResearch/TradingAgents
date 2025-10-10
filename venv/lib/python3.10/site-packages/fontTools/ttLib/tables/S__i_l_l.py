from fontTools.misc import sstruct
from fontTools.misc.fixedTools import floatToFixedToStr
from fontTools.misc.textTools import safeEval
from . import DefaultTable
from . import grUtils
import struct

Sill_hdr = """
    >
    version:    16.16F
"""


class table_S__i_l_l(DefaultTable.DefaultTable):
    """Graphite Languages table

    See also https://graphite.sil.org/graphite_techAbout#graphite-font-tables
    """

    def __init__(self, tag=None):
        DefaultTable.DefaultTable.__init__(self, tag)
        self.langs = {}

    def decompile(self, data, ttFont):
        (_, data) = sstruct.unpack2(Sill_hdr, data, self)
        self.version = float(floatToFixedToStr(self.version, precisionBits=16))
        (numLangs,) = struct.unpack(">H", data[:2])
        data = data[8:]
        maxsetting = 0
        langinfo = []
        for i in range(numLangs):
            (langcode, numsettings, offset) = struct.unpack(
                ">4sHH", data[i * 8 : (i + 1) * 8]
            )
            offset = int(offset / 8) - (numLangs + 1)
            langcode = langcode.replace(b"\000", b"")
            langinfo.append((langcode.decode("utf-8"), numsettings, offset))
            maxsetting = max(maxsetting, offset + numsettings)
        data = data[numLangs * 8 :]
        finfo = []
        for i in range(maxsetting):
            (fid, val, _) = struct.unpack(">LHH", data[i * 8 : (i + 1) * 8])
            finfo.append((fid, val))
        self.langs = {}
        for c, n, o in langinfo:
            self.langs[c] = []
            for i in range(o, o + n):
                self.langs[c].append(finfo[i])

    def compile(self, ttFont):
        ldat = b""
        fdat = b""
        offset = len(self.langs)
        for c, inf in sorted(self.langs.items()):
            ldat += struct.pack(">4sHH", c.encode("utf8"), len(inf), 8 * offset + 20)
            for fid, val in inf:
                fdat += struct.pack(">LHH", fid, val, 0)
            offset += len(inf)
        ldat += struct.pack(">LHH", 0x80808080, 0, 8 * offset + 20)
        return (
            sstruct.pack(Sill_hdr, self)
            + grUtils.bininfo(len(self.langs))
            + ldat
            + fdat
        )

    def toXML(self, writer, ttFont):
        writer.simpletag("version", version=self.version)
        writer.newline()
        for c, inf in sorted(self.langs.items()):
            writer.begintag("lang", name=c)
            writer.newline()
            for fid, val in inf:
                writer.simpletag("feature", fid=grUtils.num2tag(fid), val=val)
                writer.newline()
            writer.endtag("lang")
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "version":
            self.version = float(safeEval(attrs["version"]))
        elif name == "lang":
            c = attrs["name"]
            self.langs[c] = []
            for element in content:
                if not isinstance(element, tuple):
                    continue
                tag, a, subcontent = element
                if tag == "feature":
                    self.langs[c].append(
                        (grUtils.tag2num(a["fid"]), int(safeEval(a["val"])))
                    )
