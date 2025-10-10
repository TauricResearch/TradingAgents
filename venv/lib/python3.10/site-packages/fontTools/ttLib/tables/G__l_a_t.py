from fontTools.misc import sstruct
from fontTools.misc.fixedTools import floatToFixedToStr
from fontTools.misc.textTools import safeEval

# from itertools import *
from functools import partial
from . import DefaultTable
from . import grUtils
import struct


Glat_format_0 = """
    >        # big endian
    version: 16.16F
"""

Glat_format_3 = """
    >
    version: 16.16F
    compression:L    # compression scheme or reserved 
"""

Glat_format_1_entry = """
    >
    attNum:     B    # Attribute number of first attribute
    num:        B    # Number of attributes in this run
"""
Glat_format_23_entry = """
    >
    attNum:     H    # Attribute number of first attribute
    num:        H    # Number of attributes in this run
"""

Glat_format_3_octabox_metrics = """
    >
    subboxBitmap:   H    # Which subboxes exist on 4x4 grid
    diagNegMin:     B    # Defines minimum negatively-sloped diagonal (si)
    diagNegMax:     B    # Defines maximum negatively-sloped diagonal (sa)
    diagPosMin:     B    # Defines minimum positively-sloped diagonal (di)
    diagPosMax:     B    # Defines maximum positively-sloped diagonal (da)
"""

Glat_format_3_subbox_entry = """
    >
    left:           B    # xi
    right:          B    # xa
    bottom:         B    # yi
    top:            B    # ya
    diagNegMin:     B    # Defines minimum negatively-sloped diagonal (si)
    diagNegMax:     B    # Defines maximum negatively-sloped diagonal (sa)
    diagPosMin:     B    # Defines minimum positively-sloped diagonal (di)
    diagPosMax:     B    # Defines maximum positively-sloped diagonal (da)
"""


class _Object:
    pass


class _Dict(dict):
    pass


class table_G__l_a_t(DefaultTable.DefaultTable):
    """Graphite Glyph Attributes table

    See also https://graphite.sil.org/graphite_techAbout#graphite-font-tables
    """

    def __init__(self, tag=None):
        DefaultTable.DefaultTable.__init__(self, tag)
        self.scheme = 0

    def decompile(self, data, ttFont):
        sstruct.unpack2(Glat_format_0, data, self)
        self.version = float(floatToFixedToStr(self.version, precisionBits=16))
        if self.version <= 1.9:
            decoder = partial(self.decompileAttributes12, fmt=Glat_format_1_entry)
        elif self.version <= 2.9:
            decoder = partial(self.decompileAttributes12, fmt=Glat_format_23_entry)
        elif self.version >= 3.0:
            (data, self.scheme) = grUtils.decompress(data)
            sstruct.unpack2(Glat_format_3, data, self)
            self.hasOctaboxes = (self.compression & 1) == 1
            decoder = self.decompileAttributes3

        gloc = ttFont["Gloc"]
        self.attributes = {}
        count = 0
        for s, e in zip(gloc, gloc[1:]):
            self.attributes[ttFont.getGlyphName(count)] = decoder(data[s:e])
            count += 1

    def decompileAttributes12(self, data, fmt):
        attributes = _Dict()
        while len(data) > 3:
            e, data = sstruct.unpack2(fmt, data, _Object())
            keys = range(e.attNum, e.attNum + e.num)
            if len(data) >= 2 * e.num:
                vals = struct.unpack_from((">%dh" % e.num), data)
                attributes.update(zip(keys, vals))
                data = data[2 * e.num :]
        return attributes

    def decompileAttributes3(self, data):
        if self.hasOctaboxes:
            o, data = sstruct.unpack2(Glat_format_3_octabox_metrics, data, _Object())
            numsub = bin(o.subboxBitmap).count("1")
            o.subboxes = []
            for b in range(numsub):
                if len(data) >= 8:
                    subbox, data = sstruct.unpack2(
                        Glat_format_3_subbox_entry, data, _Object()
                    )
                    o.subboxes.append(subbox)
        attrs = self.decompileAttributes12(data, Glat_format_23_entry)
        if self.hasOctaboxes:
            attrs.octabox = o
        return attrs

    def compile(self, ttFont):
        data = sstruct.pack(Glat_format_0, self)
        if self.version <= 1.9:
            encoder = partial(self.compileAttributes12, fmt=Glat_format_1_entry)
        elif self.version <= 2.9:
            encoder = partial(self.compileAttributes12, fmt=Glat_format_1_entry)
        elif self.version >= 3.0:
            self.compression = (self.scheme << 27) + (1 if self.hasOctaboxes else 0)
            data = sstruct.pack(Glat_format_3, self)
            encoder = self.compileAttributes3

        glocs = []
        for n in range(len(self.attributes)):
            glocs.append(len(data))
            data += encoder(self.attributes[ttFont.getGlyphName(n)])
        glocs.append(len(data))
        ttFont["Gloc"].set(glocs)

        if self.version >= 3.0:
            data = grUtils.compress(self.scheme, data)
        return data

    def compileAttributes12(self, attrs, fmt):
        data = b""
        for e in grUtils.entries(attrs):
            data += sstruct.pack(fmt, {"attNum": e[0], "num": e[1]}) + struct.pack(
                (">%dh" % len(e[2])), *e[2]
            )
        return data

    def compileAttributes3(self, attrs):
        if self.hasOctaboxes:
            o = attrs.octabox
            data = sstruct.pack(Glat_format_3_octabox_metrics, o)
            numsub = bin(o.subboxBitmap).count("1")
            for b in range(numsub):
                data += sstruct.pack(Glat_format_3_subbox_entry, o.subboxes[b])
        else:
            data = ""
        return data + self.compileAttributes12(attrs, Glat_format_23_entry)

    def toXML(self, writer, ttFont):
        writer.simpletag("version", version=self.version, compressionScheme=self.scheme)
        writer.newline()
        for n, a in sorted(
            self.attributes.items(), key=lambda x: ttFont.getGlyphID(x[0])
        ):
            writer.begintag("glyph", name=n)
            writer.newline()
            if hasattr(a, "octabox"):
                o = a.octabox
                formatstring, names, fixes = sstruct.getformat(
                    Glat_format_3_octabox_metrics
                )
                vals = {}
                for k in names:
                    if k == "subboxBitmap":
                        continue
                    vals[k] = "{:.3f}%".format(getattr(o, k) * 100.0 / 255)
                vals["bitmap"] = "{:0X}".format(o.subboxBitmap)
                writer.begintag("octaboxes", **vals)
                writer.newline()
                formatstring, names, fixes = sstruct.getformat(
                    Glat_format_3_subbox_entry
                )
                for s in o.subboxes:
                    vals = {}
                    for k in names:
                        vals[k] = "{:.3f}%".format(getattr(s, k) * 100.0 / 255)
                    writer.simpletag("octabox", **vals)
                    writer.newline()
                writer.endtag("octaboxes")
                writer.newline()
            for k, v in sorted(a.items()):
                writer.simpletag("attribute", index=k, value=v)
                writer.newline()
            writer.endtag("glyph")
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "version":
            self.version = float(safeEval(attrs["version"]))
            self.scheme = int(safeEval(attrs["compressionScheme"]))
        if name != "glyph":
            return
        if not hasattr(self, "attributes"):
            self.attributes = {}
        gname = attrs["name"]
        attributes = _Dict()
        for element in content:
            if not isinstance(element, tuple):
                continue
            tag, attrs, subcontent = element
            if tag == "attribute":
                k = int(safeEval(attrs["index"]))
                v = int(safeEval(attrs["value"]))
                attributes[k] = v
            elif tag == "octaboxes":
                self.hasOctaboxes = True
                o = _Object()
                o.subboxBitmap = int(attrs["bitmap"], 16)
                o.subboxes = []
                del attrs["bitmap"]
                for k, v in attrs.items():
                    setattr(o, k, int(float(v[:-1]) * 255.0 / 100.0 + 0.5))
                for element in subcontent:
                    if not isinstance(element, tuple):
                        continue
                    (tag, attrs, subcontent) = element
                    so = _Object()
                    for k, v in attrs.items():
                        setattr(so, k, int(float(v[:-1]) * 255.0 / 100.0 + 0.5))
                    o.subboxes.append(so)
                attributes.octabox = o
        self.attributes[gname] = attributes
