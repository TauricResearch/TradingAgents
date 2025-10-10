from fontTools.misc import sstruct
from fontTools.misc.fixedTools import floatToFixedToStr
from fontTools.misc.textTools import byteord, safeEval

# from itertools import *
from . import DefaultTable
from . import grUtils
from array import array
from functools import reduce
import struct, re, sys

Silf_hdr_format = """
    >
    version:            16.16F
"""

Silf_hdr_format_3 = """
    >
    version:            16.16F
    compilerVersion:    L
    numSilf:            H
                        x
                        x
"""

Silf_part1_format_v3 = """
    >
    ruleVersion:        16.16F
    passOffset:         H
    pseudosOffset:      H
"""

Silf_part1_format = """
    >
    maxGlyphID:         H
    extraAscent:        h
    extraDescent:       h
    numPasses:          B
    iSubst:             B
    iPos:               B
    iJust:              B
    iBidi:              B
    flags:              B
    maxPreContext:      B
    maxPostContext:     B
    attrPseudo:         B
    attrBreakWeight:    B
    attrDirectionality: B
    attrMirroring:      B
    attrSkipPasses:     B
    numJLevels:         B
"""

Silf_justify_format = """
    >
    attrStretch:        B
    attrShrink:         B
    attrStep:           B
    attrWeight:         B
    runto:              B
                        x
                        x
                        x
"""

Silf_part2_format = """
    >
    numLigComp:         H
    numUserDefn:        B
    maxCompPerLig:      B
    direction:          B
    attCollisions:      B
                        x
                        x
                        x
    numCritFeatures:    B
"""

Silf_pseudomap_format = """
    >
    unicode:            L
    nPseudo:            H
"""

Silf_pseudomap_format_h = """
    >
    unicode:            H
    nPseudo:            H
"""

Silf_classmap_format = """
    >
    numClass:           H
    numLinear:          H
"""

Silf_lookupclass_format = """
    >
    numIDs:             H
    searchRange:        H
    entrySelector:      H
    rangeShift:         H
"""

Silf_lookuppair_format = """
    >
    glyphId:            H
    index:              H
"""

Silf_pass_format = """
    >
    flags:              B
    maxRuleLoop:        B
    maxRuleContext:     B
    maxBackup:          B
    numRules:           H
    fsmOffset:          H
    pcCode:             L
    rcCode:             L
    aCode:              L
    oDebug:             L
    numRows:            H
    numTransitional:    H
    numSuccess:         H
    numColumns:         H
"""

aCode_info = (
    ("NOP", 0),
    ("PUSH_BYTE", "b"),
    ("PUSH_BYTE_U", "B"),
    ("PUSH_SHORT", ">h"),
    ("PUSH_SHORT_U", ">H"),
    ("PUSH_LONG", ">L"),
    ("ADD", 0),
    ("SUB", 0),
    ("MUL", 0),
    ("DIV", 0),
    ("MIN", 0),
    ("MAX", 0),
    ("NEG", 0),
    ("TRUNC8", 0),
    ("TRUNC16", 0),
    ("COND", 0),
    ("AND", 0),  # x10
    ("OR", 0),
    ("NOT", 0),
    ("EQUAL", 0),
    ("NOT_EQ", 0),
    ("LESS", 0),
    ("GTR", 0),
    ("LESS_EQ", 0),
    ("GTR_EQ", 0),
    ("NEXT", 0),
    ("NEXT_N", "b"),
    ("COPY_NEXT", 0),
    ("PUT_GLYPH_8BIT_OBS", "B"),
    ("PUT_SUBS_8BIT_OBS", "bBB"),
    ("PUT_COPY", "b"),
    ("INSERT", 0),
    ("DELETE", 0),  # x20
    ("ASSOC", -1),
    ("CNTXT_ITEM", "bB"),
    ("ATTR_SET", "B"),
    ("ATTR_ADD", "B"),
    ("ATTR_SUB", "B"),
    ("ATTR_SET_SLOT", "B"),
    ("IATTR_SET_SLOT", "BB"),
    ("PUSH_SLOT_ATTR", "Bb"),
    ("PUSH_GLYPH_ATTR_OBS", "Bb"),
    ("PUSH_GLYPH_METRIC", "Bbb"),
    ("PUSH_FEAT", "Bb"),
    ("PUSH_ATT_TO_GATTR_OBS", "Bb"),
    ("PUSH_ATT_TO_GLYPH_METRIC", "Bbb"),
    ("PUSH_ISLOT_ATTR", "Bbb"),
    ("PUSH_IGLYPH_ATTR", "Bbb"),
    ("POP_RET", 0),  # x30
    ("RET_ZERO", 0),
    ("RET_TRUE", 0),
    ("IATTR_SET", "BB"),
    ("IATTR_ADD", "BB"),
    ("IATTR_SUB", "BB"),
    ("PUSH_PROC_STATE", "B"),
    ("PUSH_VERSION", 0),
    ("PUT_SUBS", ">bHH"),
    ("PUT_SUBS2", 0),
    ("PUT_SUBS3", 0),
    ("PUT_GLYPH", ">H"),
    ("PUSH_GLYPH_ATTR", ">Hb"),
    ("PUSH_ATT_TO_GLYPH_ATTR", ">Hb"),
    ("BITOR", 0),
    ("BITAND", 0),
    ("BITNOT", 0),  # x40
    ("BITSET", ">HH"),
    ("SET_FEAT", "Bb"),
)
aCode_map = dict([(x[0], (i, x[1])) for i, x in enumerate(aCode_info)])


def disassemble(aCode):
    codelen = len(aCode)
    pc = 0
    res = []
    while pc < codelen:
        opcode = byteord(aCode[pc : pc + 1])
        if opcode > len(aCode_info):
            instr = aCode_info[0]
        else:
            instr = aCode_info[opcode]
        pc += 1
        if instr[1] != 0 and pc >= codelen:
            return res
        if instr[1] == -1:
            count = byteord(aCode[pc])
            fmt = "%dB" % count
            pc += 1
        elif instr[1] == 0:
            fmt = ""
        else:
            fmt = instr[1]
        if fmt == "":
            res.append(instr[0])
            continue
        parms = struct.unpack_from(fmt, aCode[pc:])
        res.append(instr[0] + "(" + ", ".join(map(str, parms)) + ")")
        pc += struct.calcsize(fmt)
    return res


instre = re.compile(r"^\s*([^(]+)\s*(?:\(([^)]+)\))?")


def assemble(instrs):
    res = b""
    for inst in instrs:
        m = instre.match(inst)
        if not m or not m.group(1) in aCode_map:
            continue
        opcode, parmfmt = aCode_map[m.group(1)]
        res += struct.pack("B", opcode)
        if m.group(2):
            if parmfmt == 0:
                continue
            parms = [int(x) for x in re.split(r",\s*", m.group(2))]
            if parmfmt == -1:
                l = len(parms)
                res += struct.pack(("%dB" % (l + 1)), l, *parms)
            else:
                res += struct.pack(parmfmt, *parms)
    return res


def writecode(tag, writer, instrs):
    writer.begintag(tag)
    writer.newline()
    for l in disassemble(instrs):
        writer.write(l)
        writer.newline()
    writer.endtag(tag)
    writer.newline()


def readcode(content):
    res = []
    for e in content_string(content).split("\n"):
        e = e.strip()
        if not len(e):
            continue
        res.append(e)
    return assemble(res)


attrs_info = (
    "flags",
    "extraAscent",
    "extraDescent",
    "maxGlyphID",
    "numLigComp",
    "numUserDefn",
    "maxCompPerLig",
    "direction",
    "lbGID",
)
attrs_passindexes = ("iSubst", "iPos", "iJust", "iBidi")
attrs_contexts = ("maxPreContext", "maxPostContext")
attrs_attributes = (
    "attrPseudo",
    "attrBreakWeight",
    "attrDirectionality",
    "attrMirroring",
    "attrSkipPasses",
    "attCollisions",
)
pass_attrs_info = (
    "flags",
    "maxRuleLoop",
    "maxRuleContext",
    "maxBackup",
    "minRulePreContext",
    "maxRulePreContext",
    "collisionThreshold",
)
pass_attrs_fsm = ("numRows", "numTransitional", "numSuccess", "numColumns")


def writesimple(tag, self, writer, *attrkeys):
    attrs = dict([(k, getattr(self, k)) for k in attrkeys])
    writer.simpletag(tag, **attrs)
    writer.newline()


def getSimple(self, attrs, *attr_list):
    for k in attr_list:
        if k in attrs:
            setattr(self, k, int(safeEval(attrs[k])))


def content_string(contents):
    res = ""
    for element in contents:
        if isinstance(element, tuple):
            continue
        res += element
    return res.strip()


def wrapline(writer, dat, length=80):
    currline = ""
    for d in dat:
        if len(currline) > length:
            writer.write(currline[:-1])
            writer.newline()
            currline = ""
        currline += d + " "
    if len(currline):
        writer.write(currline[:-1])
        writer.newline()


class _Object:
    pass


class table_S__i_l_f(DefaultTable.DefaultTable):
    """Graphite Rules table

    See also https://graphite.sil.org/graphite_techAbout#graphite-font-tables
    """

    def __init__(self, tag=None):
        DefaultTable.DefaultTable.__init__(self, tag)
        self.silfs = []

    def decompile(self, data, ttFont):
        sstruct.unpack2(Silf_hdr_format, data, self)
        self.version = float(floatToFixedToStr(self.version, precisionBits=16))
        if self.version >= 5.0:
            (data, self.scheme) = grUtils.decompress(data)
            sstruct.unpack2(Silf_hdr_format_3, data, self)
            base = sstruct.calcsize(Silf_hdr_format_3)
        elif self.version < 3.0:
            self.numSilf = struct.unpack(">H", data[4:6])
            self.scheme = 0
            self.compilerVersion = 0
            base = 8
        else:
            self.scheme = 0
            sstruct.unpack2(Silf_hdr_format_3, data, self)
            base = sstruct.calcsize(Silf_hdr_format_3)

        silfoffsets = struct.unpack_from((">%dL" % self.numSilf), data[base:])
        for offset in silfoffsets:
            s = Silf()
            self.silfs.append(s)
            s.decompile(data[offset:], ttFont, self.version)

    def compile(self, ttFont):
        self.numSilf = len(self.silfs)
        if self.version < 3.0:
            hdr = sstruct.pack(Silf_hdr_format, self)
            hdr += struct.pack(">HH", self.numSilf, 0)
        else:
            hdr = sstruct.pack(Silf_hdr_format_3, self)
        offset = len(hdr) + 4 * self.numSilf
        data = b""
        for s in self.silfs:
            hdr += struct.pack(">L", offset)
            subdata = s.compile(ttFont, self.version)
            offset += len(subdata)
            data += subdata
        if self.version >= 5.0:
            return grUtils.compress(self.scheme, hdr + data)
        return hdr + data

    def toXML(self, writer, ttFont):
        writer.comment("Attributes starting with _ are informative only")
        writer.newline()
        writer.simpletag(
            "version",
            version=self.version,
            compilerVersion=self.compilerVersion,
            compressionScheme=self.scheme,
        )
        writer.newline()
        for s in self.silfs:
            writer.begintag("silf")
            writer.newline()
            s.toXML(writer, ttFont, self.version)
            writer.endtag("silf")
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "version":
            self.scheme = int(safeEval(attrs["compressionScheme"]))
            self.version = float(safeEval(attrs["version"]))
            self.compilerVersion = int(safeEval(attrs["compilerVersion"]))
            return
        if name == "silf":
            s = Silf()
            self.silfs.append(s)
            for element in content:
                if not isinstance(element, tuple):
                    continue
                tag, attrs, subcontent = element
                s.fromXML(tag, attrs, subcontent, ttFont, self.version)


class Silf(object):
    """A particular Silf subtable"""

    def __init__(self):
        self.passes = []
        self.scriptTags = []
        self.critFeatures = []
        self.jLevels = []
        self.pMap = {}

    def decompile(self, data, ttFont, version=2.0):
        if version >= 3.0:
            _, data = sstruct.unpack2(Silf_part1_format_v3, data, self)
            self.ruleVersion = float(
                floatToFixedToStr(self.ruleVersion, precisionBits=16)
            )
        _, data = sstruct.unpack2(Silf_part1_format, data, self)
        for jlevel in range(self.numJLevels):
            j, data = sstruct.unpack2(Silf_justify_format, data, _Object())
            self.jLevels.append(j)
        _, data = sstruct.unpack2(Silf_part2_format, data, self)
        if self.numCritFeatures:
            self.critFeatures = struct.unpack_from(
                (">%dH" % self.numCritFeatures), data
            )
        data = data[self.numCritFeatures * 2 + 1 :]
        (numScriptTag,) = struct.unpack_from("B", data)
        if numScriptTag:
            self.scriptTags = [
                struct.unpack("4s", data[x : x + 4])[0].decode("ascii")
                for x in range(1, 1 + 4 * numScriptTag, 4)
            ]
        data = data[1 + 4 * numScriptTag :]
        (self.lbGID,) = struct.unpack(">H", data[:2])
        if self.numPasses:
            self.oPasses = struct.unpack(
                (">%dL" % (self.numPasses + 1)), data[2 : 6 + 4 * self.numPasses]
            )
        data = data[6 + 4 * self.numPasses :]
        (numPseudo,) = struct.unpack(">H", data[:2])
        for i in range(numPseudo):
            if version >= 3.0:
                pseudo = sstruct.unpack(
                    Silf_pseudomap_format, data[8 + 6 * i : 14 + 6 * i], _Object()
                )
            else:
                pseudo = sstruct.unpack(
                    Silf_pseudomap_format_h, data[8 + 4 * i : 12 + 4 * i], _Object()
                )
            self.pMap[pseudo.unicode] = ttFont.getGlyphName(pseudo.nPseudo)
        data = data[8 + 6 * numPseudo :]
        currpos = (
            sstruct.calcsize(Silf_part1_format)
            + sstruct.calcsize(Silf_justify_format) * self.numJLevels
            + sstruct.calcsize(Silf_part2_format)
            + 2 * self.numCritFeatures
            + 1
            + 1
            + 4 * numScriptTag
            + 6
            + 4 * self.numPasses
            + 8
            + 6 * numPseudo
        )
        if version >= 3.0:
            currpos += sstruct.calcsize(Silf_part1_format_v3)
        self.classes = Classes()
        self.classes.decompile(data, ttFont, version)
        for i in range(self.numPasses):
            p = Pass()
            self.passes.append(p)
            p.decompile(
                data[self.oPasses[i] - currpos : self.oPasses[i + 1] - currpos],
                ttFont,
                version,
            )

    def compile(self, ttFont, version=2.0):
        self.numPasses = len(self.passes)
        self.numJLevels = len(self.jLevels)
        self.numCritFeatures = len(self.critFeatures)
        numPseudo = len(self.pMap)
        data = b""
        if version >= 3.0:
            hdroffset = sstruct.calcsize(Silf_part1_format_v3)
        else:
            hdroffset = 0
        data += sstruct.pack(Silf_part1_format, self)
        for j in self.jLevels:
            data += sstruct.pack(Silf_justify_format, j)
        data += sstruct.pack(Silf_part2_format, self)
        if self.numCritFeatures:
            data += struct.pack((">%dH" % self.numCritFeaturs), *self.critFeatures)
        data += struct.pack("BB", 0, len(self.scriptTags))
        if len(self.scriptTags):
            tdata = [struct.pack("4s", x.encode("ascii")) for x in self.scriptTags]
            data += b"".join(tdata)
        data += struct.pack(">H", self.lbGID)
        self.passOffset = len(data)

        data1 = grUtils.bininfo(numPseudo, 6)
        currpos = hdroffset + len(data) + 4 * (self.numPasses + 1)
        self.pseudosOffset = currpos + len(data1)
        for u, p in sorted(self.pMap.items()):
            data1 += struct.pack(
                (">LH" if version >= 3.0 else ">HH"), u, ttFont.getGlyphID(p)
            )
        data1 += self.classes.compile(ttFont, version)
        currpos += len(data1)
        data2 = b""
        datao = b""
        for i, p in enumerate(self.passes):
            base = currpos + len(data2)
            datao += struct.pack(">L", base)
            data2 += p.compile(ttFont, base, version)
        datao += struct.pack(">L", currpos + len(data2))

        if version >= 3.0:
            data3 = sstruct.pack(Silf_part1_format_v3, self)
        else:
            data3 = b""
        return data3 + data + datao + data1 + data2

    def toXML(self, writer, ttFont, version=2.0):
        if version >= 3.0:
            writer.simpletag("version", ruleVersion=self.ruleVersion)
            writer.newline()
        writesimple("info", self, writer, *attrs_info)
        writesimple("passindexes", self, writer, *attrs_passindexes)
        writesimple("contexts", self, writer, *attrs_contexts)
        writesimple("attributes", self, writer, *attrs_attributes)
        if len(self.jLevels):
            writer.begintag("justifications")
            writer.newline()
            jformat, jnames, jfixes = sstruct.getformat(Silf_justify_format)
            for i, j in enumerate(self.jLevels):
                attrs = dict([(k, getattr(j, k)) for k in jnames])
                writer.simpletag("justify", **attrs)
                writer.newline()
            writer.endtag("justifications")
            writer.newline()
        if len(self.critFeatures):
            writer.begintag("critFeatures")
            writer.newline()
            writer.write(" ".join(map(str, self.critFeatures)))
            writer.newline()
            writer.endtag("critFeatures")
            writer.newline()
        if len(self.scriptTags):
            writer.begintag("scriptTags")
            writer.newline()
            writer.write(" ".join(self.scriptTags))
            writer.newline()
            writer.endtag("scriptTags")
            writer.newline()
        if self.pMap:
            writer.begintag("pseudoMap")
            writer.newline()
            for k, v in sorted(self.pMap.items()):
                writer.simpletag("pseudo", unicode=hex(k), pseudo=v)
                writer.newline()
            writer.endtag("pseudoMap")
            writer.newline()
        self.classes.toXML(writer, ttFont, version)
        if len(self.passes):
            writer.begintag("passes")
            writer.newline()
            for i, p in enumerate(self.passes):
                writer.begintag("pass", _index=i)
                writer.newline()
                p.toXML(writer, ttFont, version)
                writer.endtag("pass")
                writer.newline()
            writer.endtag("passes")
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont, version=2.0):
        if name == "version":
            self.ruleVersion = float(safeEval(attrs.get("ruleVersion", "0")))
        if name == "info":
            getSimple(self, attrs, *attrs_info)
        elif name == "passindexes":
            getSimple(self, attrs, *attrs_passindexes)
        elif name == "contexts":
            getSimple(self, attrs, *attrs_contexts)
        elif name == "attributes":
            getSimple(self, attrs, *attrs_attributes)
        elif name == "justifications":
            for element in content:
                if not isinstance(element, tuple):
                    continue
                (tag, attrs, subcontent) = element
                if tag == "justify":
                    j = _Object()
                    for k, v in attrs.items():
                        setattr(j, k, int(v))
                    self.jLevels.append(j)
        elif name == "critFeatures":
            self.critFeatures = []
            element = content_string(content)
            self.critFeatures.extend(map(int, element.split()))
        elif name == "scriptTags":
            self.scriptTags = []
            element = content_string(content)
            for n in element.split():
                self.scriptTags.append(n)
        elif name == "pseudoMap":
            self.pMap = {}
            for element in content:
                if not isinstance(element, tuple):
                    continue
                (tag, attrs, subcontent) = element
                if tag == "pseudo":
                    k = int(attrs["unicode"], 16)
                    v = attrs["pseudo"]
                self.pMap[k] = v
        elif name == "classes":
            self.classes = Classes()
            for element in content:
                if not isinstance(element, tuple):
                    continue
                tag, attrs, subcontent = element
                self.classes.fromXML(tag, attrs, subcontent, ttFont, version)
        elif name == "passes":
            for element in content:
                if not isinstance(element, tuple):
                    continue
                tag, attrs, subcontent = element
                if tag == "pass":
                    p = Pass()
                    for e in subcontent:
                        if not isinstance(e, tuple):
                            continue
                        p.fromXML(e[0], e[1], e[2], ttFont, version)
                    self.passes.append(p)


class Classes(object):
    def __init__(self):
        self.linear = []
        self.nonLinear = []

    def decompile(self, data, ttFont, version=2.0):
        sstruct.unpack2(Silf_classmap_format, data, self)
        if version >= 4.0:
            oClasses = struct.unpack(
                (">%dL" % (self.numClass + 1)), data[4 : 8 + 4 * self.numClass]
            )
        else:
            oClasses = struct.unpack(
                (">%dH" % (self.numClass + 1)), data[4 : 6 + 2 * self.numClass]
            )
        for s, e in zip(oClasses[: self.numLinear], oClasses[1 : self.numLinear + 1]):
            self.linear.append(
                ttFont.getGlyphName(x)
                for x in struct.unpack((">%dH" % ((e - s) / 2)), data[s:e])
            )
        for s, e in zip(
            oClasses[self.numLinear : self.numClass],
            oClasses[self.numLinear + 1 : self.numClass + 1],
        ):
            nonLinids = [
                struct.unpack(">HH", data[x : x + 4]) for x in range(s + 8, e, 4)
            ]
            nonLin = dict([(ttFont.getGlyphName(x[0]), x[1]) for x in nonLinids])
            self.nonLinear.append(nonLin)

    def compile(self, ttFont, version=2.0):
        data = b""
        oClasses = []
        if version >= 4.0:
            offset = 8 + 4 * (len(self.linear) + len(self.nonLinear))
        else:
            offset = 6 + 2 * (len(self.linear) + len(self.nonLinear))
        for l in self.linear:
            oClasses.append(len(data) + offset)
            gs = [ttFont.getGlyphID(x) for x in l]
            data += struct.pack((">%dH" % len(l)), *gs)
        for l in self.nonLinear:
            oClasses.append(len(data) + offset)
            gs = [(ttFont.getGlyphID(x[0]), x[1]) for x in l.items()]
            data += grUtils.bininfo(len(gs))
            data += b"".join([struct.pack(">HH", *x) for x in sorted(gs)])
        oClasses.append(len(data) + offset)
        self.numClass = len(oClasses) - 1
        self.numLinear = len(self.linear)
        return (
            sstruct.pack(Silf_classmap_format, self)
            + struct.pack(
                ((">%dL" if version >= 4.0 else ">%dH") % len(oClasses)), *oClasses
            )
            + data
        )

    def toXML(self, writer, ttFont, version=2.0):
        writer.begintag("classes")
        writer.newline()
        writer.begintag("linearClasses")
        writer.newline()
        for i, l in enumerate(self.linear):
            writer.begintag("linear", _index=i)
            writer.newline()
            wrapline(writer, l)
            writer.endtag("linear")
            writer.newline()
        writer.endtag("linearClasses")
        writer.newline()
        writer.begintag("nonLinearClasses")
        writer.newline()
        for i, l in enumerate(self.nonLinear):
            writer.begintag("nonLinear", _index=i + self.numLinear)
            writer.newline()
            for inp, ind in l.items():
                writer.simpletag("map", glyph=inp, index=ind)
                writer.newline()
            writer.endtag("nonLinear")
            writer.newline()
        writer.endtag("nonLinearClasses")
        writer.newline()
        writer.endtag("classes")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont, version=2.0):
        if name == "linearClasses":
            for element in content:
                if not isinstance(element, tuple):
                    continue
                tag, attrs, subcontent = element
                if tag == "linear":
                    l = content_string(subcontent).split()
                    self.linear.append(l)
        elif name == "nonLinearClasses":
            for element in content:
                if not isinstance(element, tuple):
                    continue
                tag, attrs, subcontent = element
                if tag == "nonLinear":
                    l = {}
                    for e in subcontent:
                        if not isinstance(e, tuple):
                            continue
                        tag, attrs, subsubcontent = e
                        if tag == "map":
                            l[attrs["glyph"]] = int(safeEval(attrs["index"]))
                    self.nonLinear.append(l)


class Pass(object):
    def __init__(self):
        self.colMap = {}
        self.rules = []
        self.rulePreContexts = []
        self.ruleSortKeys = []
        self.ruleConstraints = []
        self.passConstraints = b""
        self.actions = []
        self.stateTrans = []
        self.startStates = []

    def decompile(self, data, ttFont, version=2.0):
        _, data = sstruct.unpack2(Silf_pass_format, data, self)
        (numRange, _, _, _) = struct.unpack(">4H", data[:8])
        data = data[8:]
        for i in range(numRange):
            (first, last, col) = struct.unpack(">3H", data[6 * i : 6 * i + 6])
            for g in range(first, last + 1):
                self.colMap[ttFont.getGlyphName(g)] = col
        data = data[6 * numRange :]
        oRuleMap = struct.unpack_from((">%dH" % (self.numSuccess + 1)), data)
        data = data[2 + 2 * self.numSuccess :]
        rules = struct.unpack_from((">%dH" % oRuleMap[-1]), data)
        self.rules = [rules[s:e] for (s, e) in zip(oRuleMap, oRuleMap[1:])]
        data = data[2 * oRuleMap[-1] :]
        (self.minRulePreContext, self.maxRulePreContext) = struct.unpack("BB", data[:2])
        numStartStates = self.maxRulePreContext - self.minRulePreContext + 1
        self.startStates = struct.unpack(
            (">%dH" % numStartStates), data[2 : 2 + numStartStates * 2]
        )
        data = data[2 + numStartStates * 2 :]
        self.ruleSortKeys = struct.unpack(
            (">%dH" % self.numRules), data[: 2 * self.numRules]
        )
        data = data[2 * self.numRules :]
        self.rulePreContexts = struct.unpack(
            ("%dB" % self.numRules), data[: self.numRules]
        )
        data = data[self.numRules :]
        (self.collisionThreshold, pConstraint) = struct.unpack(">BH", data[:3])
        oConstraints = list(
            struct.unpack(
                (">%dH" % (self.numRules + 1)), data[3 : 5 + self.numRules * 2]
            )
        )
        data = data[5 + self.numRules * 2 :]
        oActions = list(
            struct.unpack((">%dH" % (self.numRules + 1)), data[: 2 + self.numRules * 2])
        )
        data = data[2 * self.numRules + 2 :]
        for i in range(self.numTransitional):
            a = array(
                "H", data[i * self.numColumns * 2 : (i + 1) * self.numColumns * 2]
            )
            if sys.byteorder != "big":
                a.byteswap()
            self.stateTrans.append(a)
        data = data[self.numTransitional * self.numColumns * 2 + 1 :]
        self.passConstraints = data[:pConstraint]
        data = data[pConstraint:]
        for i in range(len(oConstraints) - 2, -1, -1):
            if oConstraints[i] == 0:
                oConstraints[i] = oConstraints[i + 1]
        self.ruleConstraints = [
            (data[s:e] if (e - s > 1) else b"")
            for (s, e) in zip(oConstraints, oConstraints[1:])
        ]
        data = data[oConstraints[-1] :]
        self.actions = [
            (data[s:e] if (e - s > 1) else "") for (s, e) in zip(oActions, oActions[1:])
        ]
        data = data[oActions[-1] :]
        # not using debug

    def compile(self, ttFont, base, version=2.0):
        # build it all up backwards
        oActions = reduce(
            lambda a, x: (a[0] + len(x), a[1] + [a[0]]), self.actions + [b""], (0, [])
        )[1]
        oConstraints = reduce(
            lambda a, x: (a[0] + len(x), a[1] + [a[0]]),
            self.ruleConstraints + [b""],
            (1, []),
        )[1]
        constraintCode = b"\000" + b"".join(self.ruleConstraints)
        transes = []
        for t in self.stateTrans:
            if sys.byteorder != "big":
                t.byteswap()
            transes.append(t.tobytes())
            if sys.byteorder != "big":
                t.byteswap()
        if not len(transes):
            self.startStates = [0]
        oRuleMap = reduce(
            lambda a, x: (a[0] + len(x), a[1] + [a[0]]), self.rules + [[]], (0, [])
        )[1]
        passRanges = []
        gidcolmap = dict([(ttFont.getGlyphID(x[0]), x[1]) for x in self.colMap.items()])
        for e in grUtils.entries(gidcolmap, sameval=True):
            if e[1]:
                passRanges.append((e[0], e[0] + e[1] - 1, e[2][0]))
        self.numRules = len(self.actions)
        self.fsmOffset = (
            sstruct.calcsize(Silf_pass_format)
            + 8
            + len(passRanges) * 6
            + len(oRuleMap) * 2
            + 2 * oRuleMap[-1]
            + 2
            + 2 * len(self.startStates)
            + 3 * self.numRules
            + 3
            + 4 * self.numRules
            + 4
        )
        self.pcCode = (
            self.fsmOffset + 2 * self.numTransitional * self.numColumns + 1 + base
        )
        self.rcCode = self.pcCode + len(self.passConstraints)
        self.aCode = self.rcCode + len(constraintCode)
        self.oDebug = 0
        # now generate output
        data = sstruct.pack(Silf_pass_format, self)
        data += grUtils.bininfo(len(passRanges), 6)
        data += b"".join(struct.pack(">3H", *p) for p in passRanges)
        data += struct.pack((">%dH" % len(oRuleMap)), *oRuleMap)
        flatrules = reduce(lambda a, x: a + x, self.rules, [])
        data += struct.pack((">%dH" % oRuleMap[-1]), *flatrules)
        data += struct.pack("BB", self.minRulePreContext, self.maxRulePreContext)
        data += struct.pack((">%dH" % len(self.startStates)), *self.startStates)
        data += struct.pack((">%dH" % self.numRules), *self.ruleSortKeys)
        data += struct.pack(("%dB" % self.numRules), *self.rulePreContexts)
        data += struct.pack(">BH", self.collisionThreshold, len(self.passConstraints))
        data += struct.pack((">%dH" % (self.numRules + 1)), *oConstraints)
        data += struct.pack((">%dH" % (self.numRules + 1)), *oActions)
        return (
            data
            + b"".join(transes)
            + struct.pack("B", 0)
            + self.passConstraints
            + constraintCode
            + b"".join(self.actions)
        )

    def toXML(self, writer, ttFont, version=2.0):
        writesimple("info", self, writer, *pass_attrs_info)
        writesimple("fsminfo", self, writer, *pass_attrs_fsm)
        writer.begintag("colmap")
        writer.newline()
        wrapline(
            writer,
            [
                "{}={}".format(*x)
                for x in sorted(
                    self.colMap.items(), key=lambda x: ttFont.getGlyphID(x[0])
                )
            ],
        )
        writer.endtag("colmap")
        writer.newline()
        writer.begintag("staterulemap")
        writer.newline()
        for i, r in enumerate(self.rules):
            writer.simpletag(
                "state",
                number=self.numRows - self.numSuccess + i,
                rules=" ".join(map(str, r)),
            )
            writer.newline()
        writer.endtag("staterulemap")
        writer.newline()
        writer.begintag("rules")
        writer.newline()
        for i, action in enumerate(self.actions):
            writer.begintag(
                "rule",
                index=i,
                precontext=self.rulePreContexts[i],
                sortkey=self.ruleSortKeys[i],
            )
            writer.newline()
            if len(self.ruleConstraints[i]):
                writecode("constraint", writer, self.ruleConstraints[i])
            writecode("action", writer, action)
            writer.endtag("rule")
            writer.newline()
        writer.endtag("rules")
        writer.newline()
        if len(self.passConstraints):
            writecode("passConstraint", writer, self.passConstraints)
        if len(self.stateTrans):
            writer.begintag("fsm")
            writer.newline()
            writer.begintag("starts")
            writer.write(" ".join(map(str, self.startStates)))
            writer.endtag("starts")
            writer.newline()
            for i, s in enumerate(self.stateTrans):
                writer.begintag("row", _i=i)
                # no newlines here
                writer.write(" ".join(map(str, s)))
                writer.endtag("row")
                writer.newline()
            writer.endtag("fsm")
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont, version=2.0):
        if name == "info":
            getSimple(self, attrs, *pass_attrs_info)
        elif name == "fsminfo":
            getSimple(self, attrs, *pass_attrs_fsm)
        elif name == "colmap":
            e = content_string(content)
            for w in e.split():
                x = w.split("=")
                if len(x) != 2 or x[0] == "" or x[1] == "":
                    continue
                self.colMap[x[0]] = int(x[1])
        elif name == "staterulemap":
            for e in content:
                if not isinstance(e, tuple):
                    continue
                tag, a, c = e
                if tag == "state":
                    self.rules.append([int(x) for x in a["rules"].split(" ")])
        elif name == "rules":
            for element in content:
                if not isinstance(element, tuple):
                    continue
                tag, a, c = element
                if tag != "rule":
                    continue
                self.rulePreContexts.append(int(a["precontext"]))
                self.ruleSortKeys.append(int(a["sortkey"]))
                con = b""
                act = b""
                for e in c:
                    if not isinstance(e, tuple):
                        continue
                    tag, a, subc = e
                    if tag == "constraint":
                        con = readcode(subc)
                    elif tag == "action":
                        act = readcode(subc)
                self.actions.append(act)
                self.ruleConstraints.append(con)
        elif name == "passConstraint":
            self.passConstraints = readcode(content)
        elif name == "fsm":
            for element in content:
                if not isinstance(element, tuple):
                    continue
                tag, a, c = element
                if tag == "row":
                    s = array("H")
                    e = content_string(c)
                    s.extend(map(int, e.split()))
                    self.stateTrans.append(s)
                elif tag == "starts":
                    s = []
                    e = content_string(c)
                    s.extend(map(int, e.split()))
                    self.startStates = s
