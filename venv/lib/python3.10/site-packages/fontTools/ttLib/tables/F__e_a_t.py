from fontTools.misc import sstruct
from fontTools.misc.fixedTools import floatToFixedToStr
from fontTools.misc.textTools import safeEval
from . import DefaultTable
from . import grUtils
import struct

Feat_hdr_format = """
    >
    version:    16.16F
"""


class table_F__e_a_t(DefaultTable.DefaultTable):
    """Feature table

    The ``Feat`` table is used exclusively by the Graphite shaping engine
    to store features and possible settings specified in GDL. Graphite features
    determine what rules are applied to transform a glyph stream.

    Not to be confused with ``feat``, or the OpenType Layout tables
    ``GSUB``/``GPOS``.

    See also https://graphite.sil.org/graphite_techAbout#graphite-font-tables
    """

    def __init__(self, tag=None):
        DefaultTable.DefaultTable.__init__(self, tag)
        self.features = {}

    def decompile(self, data, ttFont):
        (_, data) = sstruct.unpack2(Feat_hdr_format, data, self)
        self.version = float(floatToFixedToStr(self.version, precisionBits=16))
        (numFeats,) = struct.unpack(">H", data[:2])
        data = data[8:]
        allfeats = []
        maxsetting = 0
        for i in range(numFeats):
            if self.version >= 2.0:
                (fid, nums, _, offset, flags, lid) = struct.unpack(
                    ">LHHLHH", data[16 * i : 16 * (i + 1)]
                )
                offset = int((offset - 12 - 16 * numFeats) / 4)
            else:
                (fid, nums, offset, flags, lid) = struct.unpack(
                    ">HHLHH", data[12 * i : 12 * (i + 1)]
                )
                offset = int((offset - 12 - 12 * numFeats) / 4)
            allfeats.append((fid, nums, offset, flags, lid))
            maxsetting = max(maxsetting, offset + nums)
        data = data[16 * numFeats :]
        allsettings = []
        for i in range(maxsetting):
            if len(data) >= 4 * (i + 1):
                (val, lid) = struct.unpack(">HH", data[4 * i : 4 * (i + 1)])
                allsettings.append((val, lid))
        for i, f in enumerate(allfeats):
            (fid, nums, offset, flags, lid) = f
            fobj = Feature()
            fobj.flags = flags
            fobj.label = lid
            self.features[grUtils.num2tag(fid)] = fobj
            fobj.settings = {}
            fobj.default = None
            fobj.index = i
            for i in range(offset, offset + nums):
                if i >= len(allsettings):
                    continue
                (vid, vlid) = allsettings[i]
                fobj.settings[vid] = vlid
                if fobj.default is None:
                    fobj.default = vid

    def compile(self, ttFont):
        fdat = b""
        vdat = b""
        offset = 0
        for f, v in sorted(self.features.items(), key=lambda x: x[1].index):
            fnum = grUtils.tag2num(f)
            if self.version >= 2.0:
                fdat += struct.pack(
                    ">LHHLHH",
                    grUtils.tag2num(f),
                    len(v.settings),
                    0,
                    offset * 4 + 12 + 16 * len(self.features),
                    v.flags,
                    v.label,
                )
            elif fnum > 65535:  # self healing for alphabetic ids
                self.version = 2.0
                return self.compile(ttFont)
            else:
                fdat += struct.pack(
                    ">HHLHH",
                    grUtils.tag2num(f),
                    len(v.settings),
                    offset * 4 + 12 + 12 * len(self.features),
                    v.flags,
                    v.label,
                )
            for s, l in sorted(
                v.settings.items(), key=lambda x: (-1, x[1]) if x[0] == v.default else x
            ):
                vdat += struct.pack(">HH", s, l)
            offset += len(v.settings)
        hdr = sstruct.pack(Feat_hdr_format, self)
        return hdr + struct.pack(">HHL", len(self.features), 0, 0) + fdat + vdat

    def toXML(self, writer, ttFont):
        writer.simpletag("version", version=self.version)
        writer.newline()
        for f, v in sorted(self.features.items(), key=lambda x: x[1].index):
            writer.begintag(
                "feature",
                fid=f,
                label=v.label,
                flags=v.flags,
                default=(v.default if v.default else 0),
            )
            writer.newline()
            for s, l in sorted(v.settings.items()):
                writer.simpletag("setting", value=s, label=l)
                writer.newline()
            writer.endtag("feature")
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "version":
            self.version = float(safeEval(attrs["version"]))
        elif name == "feature":
            fid = attrs["fid"]
            fobj = Feature()
            fobj.flags = int(safeEval(attrs["flags"]))
            fobj.label = int(safeEval(attrs["label"]))
            fobj.default = int(safeEval(attrs.get("default", "0")))
            fobj.index = len(self.features)
            self.features[fid] = fobj
            fobj.settings = {}
            for element in content:
                if not isinstance(element, tuple):
                    continue
                tag, a, c = element
                if tag == "setting":
                    fobj.settings[int(safeEval(a["value"]))] = int(safeEval(a["label"]))


class Feature(object):
    pass
