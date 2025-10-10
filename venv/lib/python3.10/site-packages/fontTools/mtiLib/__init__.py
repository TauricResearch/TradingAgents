# FontDame-to-FontTools for OpenType Layout tables
#
# Source language spec is available at:
# http://monotype.github.io/OpenType_Table_Source/otl_source.html
# https://github.com/Monotype/OpenType_Table_Source/

from fontTools import ttLib
from fontTools.ttLib.tables._c_m_a_p import cmap_classes
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables.otBase import ValueRecord, valueRecordFormatDict
from fontTools.otlLib import builder as otl
from contextlib import contextmanager
from fontTools.ttLib import newTable
from fontTools.feaLib.lookupDebugInfo import LOOKUP_DEBUG_ENV_VAR, LOOKUP_DEBUG_INFO_KEY
from operator import setitem
import os
import logging


class MtiLibError(Exception):
    pass


class ReferenceNotFoundError(MtiLibError):
    pass


class FeatureNotFoundError(ReferenceNotFoundError):
    pass


class LookupNotFoundError(ReferenceNotFoundError):
    pass


log = logging.getLogger("fontTools.mtiLib")


def makeGlyph(s):
    if s[:2] in ["U ", "u "]:
        return ttLib.TTFont._makeGlyphName(int(s[2:], 16))
    elif s[:2] == "# ":
        return "glyph%.5d" % int(s[2:])
    assert s.find(" ") < 0, "Space found in glyph name: %s" % s
    assert s, "Glyph name is empty"
    return s


def makeGlyphs(l):
    return [makeGlyph(g) for g in l]


def mapLookup(sym, mapping):
    # Lookups are addressed by name.  So resolved them using a map if available.
    # Fallback to parsing as lookup index if a map isn't provided.
    if mapping is not None:
        try:
            idx = mapping[sym]
        except KeyError:
            raise LookupNotFoundError(sym)
    else:
        idx = int(sym)
    return idx


def mapFeature(sym, mapping):
    # Features are referenced by index according the spec.  So, if symbol is an
    # integer, use it directly.  Otherwise look up in the map if provided.
    try:
        idx = int(sym)
    except ValueError:
        try:
            idx = mapping[sym]
        except KeyError:
            raise FeatureNotFoundError(sym)
    return idx


def setReference(mapper, mapping, sym, setter, collection, key):
    try:
        mapped = mapper(sym, mapping)
    except ReferenceNotFoundError as e:
        try:
            if mapping is not None:
                mapping.addDeferredMapping(
                    lambda ref: setter(collection, key, ref), sym, e
                )
                return
        except AttributeError:
            pass
        raise
    setter(collection, key, mapped)


class DeferredMapping(dict):
    def __init__(self):
        self._deferredMappings = []

    def addDeferredMapping(self, setter, sym, e):
        log.debug("Adding deferred mapping for symbol '%s' %s", sym, type(e).__name__)
        self._deferredMappings.append((setter, sym, e))

    def applyDeferredMappings(self):
        for setter, sym, e in self._deferredMappings:
            log.debug(
                "Applying deferred mapping for symbol '%s' %s", sym, type(e).__name__
            )
            try:
                mapped = self[sym]
            except KeyError:
                raise e
            setter(mapped)
            log.debug("Set to %s", mapped)
        self._deferredMappings = []


def parseScriptList(lines, featureMap=None):
    self = ot.ScriptList()
    records = []
    with lines.between("script table"):
        for line in lines:
            while len(line) < 4:
                line.append("")
            scriptTag, langSysTag, defaultFeature, features = line
            log.debug("Adding script %s language-system %s", scriptTag, langSysTag)

            langSys = ot.LangSys()
            langSys.LookupOrder = None
            if defaultFeature:
                setReference(
                    mapFeature,
                    featureMap,
                    defaultFeature,
                    setattr,
                    langSys,
                    "ReqFeatureIndex",
                )
            else:
                langSys.ReqFeatureIndex = 0xFFFF
            syms = stripSplitComma(features)
            langSys.FeatureIndex = theList = [3] * len(syms)
            for i, sym in enumerate(syms):
                setReference(mapFeature, featureMap, sym, setitem, theList, i)
            langSys.FeatureCount = len(langSys.FeatureIndex)

            script = [s for s in records if s.ScriptTag == scriptTag]
            if script:
                script = script[0].Script
            else:
                scriptRec = ot.ScriptRecord()
                scriptRec.ScriptTag = scriptTag + " " * (4 - len(scriptTag))
                scriptRec.Script = ot.Script()
                records.append(scriptRec)
                script = scriptRec.Script
                script.DefaultLangSys = None
                script.LangSysRecord = []
                script.LangSysCount = 0

            if langSysTag == "default":
                script.DefaultLangSys = langSys
            else:
                langSysRec = ot.LangSysRecord()
                langSysRec.LangSysTag = langSysTag + " " * (4 - len(langSysTag))
                langSysRec.LangSys = langSys
                script.LangSysRecord.append(langSysRec)
                script.LangSysCount = len(script.LangSysRecord)

    for script in records:
        script.Script.LangSysRecord = sorted(
            script.Script.LangSysRecord, key=lambda rec: rec.LangSysTag
        )
    self.ScriptRecord = sorted(records, key=lambda rec: rec.ScriptTag)
    self.ScriptCount = len(self.ScriptRecord)
    return self


def parseFeatureList(lines, lookupMap=None, featureMap=None):
    self = ot.FeatureList()
    self.FeatureRecord = []
    with lines.between("feature table"):
        for line in lines:
            name, featureTag, lookups = line
            if featureMap is not None:
                assert name not in featureMap, "Duplicate feature name: %s" % name
                featureMap[name] = len(self.FeatureRecord)
            # If feature name is integer, make sure it matches its index.
            try:
                assert int(name) == len(self.FeatureRecord), "%d %d" % (
                    name,
                    len(self.FeatureRecord),
                )
            except ValueError:
                pass
            featureRec = ot.FeatureRecord()
            featureRec.FeatureTag = featureTag
            featureRec.Feature = ot.Feature()
            self.FeatureRecord.append(featureRec)
            feature = featureRec.Feature
            feature.FeatureParams = None
            syms = stripSplitComma(lookups)
            feature.LookupListIndex = theList = [None] * len(syms)
            for i, sym in enumerate(syms):
                setReference(mapLookup, lookupMap, sym, setitem, theList, i)
            feature.LookupCount = len(feature.LookupListIndex)

    self.FeatureCount = len(self.FeatureRecord)
    return self


def parseLookupFlags(lines):
    flags = 0
    filterset = None
    allFlags = [
        "righttoleft",
        "ignorebaseglyphs",
        "ignoreligatures",
        "ignoremarks",
        "markattachmenttype",
        "markfiltertype",
    ]
    while lines.peeks()[0].lower() in allFlags:
        line = next(lines)
        flag = {
            "righttoleft": 0x0001,
            "ignorebaseglyphs": 0x0002,
            "ignoreligatures": 0x0004,
            "ignoremarks": 0x0008,
        }.get(line[0].lower())
        if flag:
            assert line[1].lower() in ["yes", "no"], line[1]
            if line[1].lower() == "yes":
                flags |= flag
            continue
        if line[0].lower() == "markattachmenttype":
            flags |= int(line[1]) << 8
            continue
        if line[0].lower() == "markfiltertype":
            flags |= 0x10
            filterset = int(line[1])
    return flags, filterset


def parseSingleSubst(lines, font, _lookupMap=None):
    mapping = {}
    for line in lines:
        assert len(line) == 2, line
        line = makeGlyphs(line)
        mapping[line[0]] = line[1]
    return otl.buildSingleSubstSubtable(mapping)


def parseMultiple(lines, font, _lookupMap=None):
    mapping = {}
    for line in lines:
        line = makeGlyphs(line)
        mapping[line[0]] = line[1:]
    return otl.buildMultipleSubstSubtable(mapping)


def parseAlternate(lines, font, _lookupMap=None):
    mapping = {}
    for line in lines:
        line = makeGlyphs(line)
        mapping[line[0]] = line[1:]
    return otl.buildAlternateSubstSubtable(mapping)


def parseLigature(lines, font, _lookupMap=None):
    mapping = {}
    for line in lines:
        assert len(line) >= 2, line
        line = makeGlyphs(line)
        mapping[tuple(line[1:])] = line[0]
    return otl.buildLigatureSubstSubtable(mapping)


def parseSinglePos(lines, font, _lookupMap=None):
    values = {}
    for line in lines:
        assert len(line) == 3, line
        w = line[0].title().replace(" ", "")
        assert w in valueRecordFormatDict
        g = makeGlyph(line[1])
        v = int(line[2])
        if g not in values:
            values[g] = ValueRecord()
        assert not hasattr(values[g], w), (g, w)
        setattr(values[g], w, v)
    return otl.buildSinglePosSubtable(values, font.getReverseGlyphMap())


def parsePair(lines, font, _lookupMap=None):
    self = ot.PairPos()
    self.ValueFormat1 = self.ValueFormat2 = 0
    typ = lines.peeks()[0].split()[0].lower()
    if typ in ("left", "right"):
        self.Format = 1
        values = {}
        for line in lines:
            assert len(line) == 4, line
            side = line[0].split()[0].lower()
            assert side in ("left", "right"), side
            what = line[0][len(side) :].title().replace(" ", "")
            mask = valueRecordFormatDict[what][0]
            glyph1, glyph2 = makeGlyphs(line[1:3])
            value = int(line[3])
            if not glyph1 in values:
                values[glyph1] = {}
            if not glyph2 in values[glyph1]:
                values[glyph1][glyph2] = (ValueRecord(), ValueRecord())
            rec2 = values[glyph1][glyph2]
            if side == "left":
                self.ValueFormat1 |= mask
                vr = rec2[0]
            else:
                self.ValueFormat2 |= mask
                vr = rec2[1]
            assert not hasattr(vr, what), (vr, what)
            setattr(vr, what, value)
        self.Coverage = makeCoverage(set(values.keys()), font)
        self.PairSet = []
        for glyph1 in self.Coverage.glyphs:
            values1 = values[glyph1]
            pairset = ot.PairSet()
            records = pairset.PairValueRecord = []
            for glyph2 in sorted(values1.keys(), key=font.getGlyphID):
                values2 = values1[glyph2]
                pair = ot.PairValueRecord()
                pair.SecondGlyph = glyph2
                pair.Value1 = values2[0]
                pair.Value2 = values2[1] if self.ValueFormat2 else None
                records.append(pair)
            pairset.PairValueCount = len(pairset.PairValueRecord)
            self.PairSet.append(pairset)
        self.PairSetCount = len(self.PairSet)
    elif typ.endswith("class"):
        self.Format = 2
        classDefs = [None, None]
        while lines.peeks()[0].endswith("class definition begin"):
            typ = lines.peek()[0][: -len("class definition begin")].lower()
            idx, klass = {
                "first": (0, ot.ClassDef1),
                "second": (1, ot.ClassDef2),
            }[typ]
            assert classDefs[idx] is None
            classDefs[idx] = parseClassDef(lines, font, klass=klass)
        self.ClassDef1, self.ClassDef2 = classDefs
        self.Class1Count, self.Class2Count = (
            1 + max(c.classDefs.values()) for c in classDefs
        )
        self.Class1Record = [ot.Class1Record() for i in range(self.Class1Count)]
        for rec1 in self.Class1Record:
            rec1.Class2Record = [ot.Class2Record() for j in range(self.Class2Count)]
            for rec2 in rec1.Class2Record:
                rec2.Value1 = ValueRecord()
                rec2.Value2 = ValueRecord()
        for line in lines:
            assert len(line) == 4, line
            side = line[0].split()[0].lower()
            assert side in ("left", "right"), side
            what = line[0][len(side) :].title().replace(" ", "")
            mask = valueRecordFormatDict[what][0]
            class1, class2, value = (int(x) for x in line[1:4])
            rec2 = self.Class1Record[class1].Class2Record[class2]
            if side == "left":
                self.ValueFormat1 |= mask
                vr = rec2.Value1
            else:
                self.ValueFormat2 |= mask
                vr = rec2.Value2
            assert not hasattr(vr, what), (vr, what)
            setattr(vr, what, value)
        for rec1 in self.Class1Record:
            for rec2 in rec1.Class2Record:
                rec2.Value1 = ValueRecord(self.ValueFormat1, rec2.Value1)
                rec2.Value2 = (
                    ValueRecord(self.ValueFormat2, rec2.Value2)
                    if self.ValueFormat2
                    else None
                )

        self.Coverage = makeCoverage(set(self.ClassDef1.classDefs.keys()), font)
    else:
        assert 0, typ
    return self


def parseKernset(lines, font, _lookupMap=None):
    typ = lines.peeks()[0].split()[0].lower()
    if typ in ("left", "right"):
        with lines.until(
            ("firstclass definition begin", "secondclass definition begin")
        ):
            return parsePair(lines, font)
    return parsePair(lines, font)


def makeAnchor(data, klass=ot.Anchor):
    assert len(data) <= 2
    anchor = klass()
    anchor.Format = 1
    anchor.XCoordinate, anchor.YCoordinate = intSplitComma(data[0])
    if len(data) > 1 and data[1] != "":
        anchor.Format = 2
        anchor.AnchorPoint = int(data[1])
    return anchor


def parseCursive(lines, font, _lookupMap=None):
    records = {}
    for line in lines:
        assert len(line) in [3, 4], line
        idx, klass = {
            "entry": (0, ot.EntryAnchor),
            "exit": (1, ot.ExitAnchor),
        }[line[0]]
        glyph = makeGlyph(line[1])
        if glyph not in records:
            records[glyph] = [None, None]
        assert records[glyph][idx] is None, (glyph, idx)
        records[glyph][idx] = makeAnchor(line[2:], klass)
    return otl.buildCursivePosSubtable(records, font.getReverseGlyphMap())


def makeMarkRecords(data, coverage, c):
    records = []
    for glyph in coverage.glyphs:
        klass, anchor = data[glyph]
        record = c.MarkRecordClass()
        record.Class = klass
        setattr(record, c.MarkAnchor, anchor)
        records.append(record)
    return records


def makeBaseRecords(data, coverage, c, classCount):
    records = []
    idx = {}
    for glyph in coverage.glyphs:
        idx[glyph] = len(records)
        record = c.BaseRecordClass()
        anchors = [None] * classCount
        setattr(record, c.BaseAnchor, anchors)
        records.append(record)
    for (glyph, klass), anchor in data.items():
        record = records[idx[glyph]]
        anchors = getattr(record, c.BaseAnchor)
        assert anchors[klass] is None, (glyph, klass)
        anchors[klass] = anchor
    return records


def makeLigatureRecords(data, coverage, c, classCount):
    records = [None] * len(coverage.glyphs)
    idx = {g: i for i, g in enumerate(coverage.glyphs)}

    for (glyph, klass, compIdx, compCount), anchor in data.items():
        record = records[idx[glyph]]
        if record is None:
            record = records[idx[glyph]] = ot.LigatureAttach()
            record.ComponentCount = compCount
            record.ComponentRecord = [ot.ComponentRecord() for i in range(compCount)]
            for compRec in record.ComponentRecord:
                compRec.LigatureAnchor = [None] * classCount
        assert record.ComponentCount == compCount, (
            glyph,
            record.ComponentCount,
            compCount,
        )

        anchors = record.ComponentRecord[compIdx - 1].LigatureAnchor
        assert anchors[klass] is None, (glyph, compIdx, klass)
        anchors[klass] = anchor
    return records


def parseMarkToSomething(lines, font, c):
    self = c.Type()
    self.Format = 1
    markData = {}
    baseData = {}
    Data = {
        "mark": (markData, c.MarkAnchorClass),
        "base": (baseData, c.BaseAnchorClass),
        "ligature": (baseData, c.BaseAnchorClass),
    }
    maxKlass = 0
    for line in lines:
        typ = line[0]
        assert typ in ("mark", "base", "ligature")
        glyph = makeGlyph(line[1])
        data, anchorClass = Data[typ]
        extraItems = 2 if typ == "ligature" else 0
        extras = tuple(int(i) for i in line[2 : 2 + extraItems])
        klass = int(line[2 + extraItems])
        anchor = makeAnchor(line[3 + extraItems :], anchorClass)
        if typ == "mark":
            key, value = glyph, (klass, anchor)
        else:
            key, value = ((glyph, klass) + extras), anchor
        assert key not in data, key
        data[key] = value
        maxKlass = max(maxKlass, klass)

    # Mark
    markCoverage = makeCoverage(set(markData.keys()), font, c.MarkCoverageClass)
    markArray = c.MarkArrayClass()
    markRecords = makeMarkRecords(markData, markCoverage, c)
    setattr(markArray, c.MarkRecord, markRecords)
    setattr(markArray, c.MarkCount, len(markRecords))
    setattr(self, c.MarkCoverage, markCoverage)
    setattr(self, c.MarkArray, markArray)
    self.ClassCount = maxKlass + 1

    # Base
    self.classCount = 0 if not baseData else 1 + max(k[1] for k, v in baseData.items())
    baseCoverage = makeCoverage(
        set([k[0] for k in baseData.keys()]), font, c.BaseCoverageClass
    )
    baseArray = c.BaseArrayClass()
    if c.Base == "Ligature":
        baseRecords = makeLigatureRecords(baseData, baseCoverage, c, self.classCount)
    else:
        baseRecords = makeBaseRecords(baseData, baseCoverage, c, self.classCount)
    setattr(baseArray, c.BaseRecord, baseRecords)
    setattr(baseArray, c.BaseCount, len(baseRecords))
    setattr(self, c.BaseCoverage, baseCoverage)
    setattr(self, c.BaseArray, baseArray)

    return self


class MarkHelper(object):
    def __init__(self):
        for Which in ("Mark", "Base"):
            for What in ("Coverage", "Array", "Count", "Record", "Anchor"):
                key = Which + What
                if Which == "Mark" and What in ("Count", "Record", "Anchor"):
                    value = key
                else:
                    value = getattr(self, Which) + What
                if value == "LigatureRecord":
                    value = "LigatureAttach"
                setattr(self, key, value)
                if What != "Count":
                    klass = getattr(ot, value)
                    setattr(self, key + "Class", klass)


class MarkToBaseHelper(MarkHelper):
    Mark = "Mark"
    Base = "Base"
    Type = ot.MarkBasePos


class MarkToMarkHelper(MarkHelper):
    Mark = "Mark1"
    Base = "Mark2"
    Type = ot.MarkMarkPos


class MarkToLigatureHelper(MarkHelper):
    Mark = "Mark"
    Base = "Ligature"
    Type = ot.MarkLigPos


def parseMarkToBase(lines, font, _lookupMap=None):
    return parseMarkToSomething(lines, font, MarkToBaseHelper())


def parseMarkToMark(lines, font, _lookupMap=None):
    return parseMarkToSomething(lines, font, MarkToMarkHelper())


def parseMarkToLigature(lines, font, _lookupMap=None):
    return parseMarkToSomething(lines, font, MarkToLigatureHelper())


def stripSplitComma(line):
    return [s.strip() for s in line.split(",")] if line else []


def intSplitComma(line):
    return [int(i) for i in line.split(",")] if line else []


# Copied from fontTools.subset
class ContextHelper(object):
    def __init__(self, klassName, Format):
        if klassName.endswith("Subst"):
            Typ = "Sub"
            Type = "Subst"
        else:
            Typ = "Pos"
            Type = "Pos"
        if klassName.startswith("Chain"):
            Chain = "Chain"
            InputIdx = 1
            DataLen = 3
        else:
            Chain = ""
            InputIdx = 0
            DataLen = 1
        ChainTyp = Chain + Typ

        self.Typ = Typ
        self.Type = Type
        self.Chain = Chain
        self.ChainTyp = ChainTyp
        self.InputIdx = InputIdx
        self.DataLen = DataLen

        self.LookupRecord = Type + "LookupRecord"

        if Format == 1:
            Coverage = lambda r: r.Coverage
            ChainCoverage = lambda r: r.Coverage
            ContextData = lambda r: (None,)
            ChainContextData = lambda r: (None, None, None)
            SetContextData = None
            SetChainContextData = None
            RuleData = lambda r: (r.Input,)
            ChainRuleData = lambda r: (r.Backtrack, r.Input, r.LookAhead)

            def SetRuleData(r, d):
                (r.Input,) = d
                (r.GlyphCount,) = (len(x) + 1 for x in d)

            def ChainSetRuleData(r, d):
                (r.Backtrack, r.Input, r.LookAhead) = d
                (
                    r.BacktrackGlyphCount,
                    r.InputGlyphCount,
                    r.LookAheadGlyphCount,
                ) = (len(d[0]), len(d[1]) + 1, len(d[2]))

        elif Format == 2:
            Coverage = lambda r: r.Coverage
            ChainCoverage = lambda r: r.Coverage
            ContextData = lambda r: (r.ClassDef,)
            ChainContextData = lambda r: (
                r.BacktrackClassDef,
                r.InputClassDef,
                r.LookAheadClassDef,
            )

            def SetContextData(r, d):
                (r.ClassDef,) = d

            def SetChainContextData(r, d):
                (r.BacktrackClassDef, r.InputClassDef, r.LookAheadClassDef) = d

            RuleData = lambda r: (r.Class,)
            ChainRuleData = lambda r: (r.Backtrack, r.Input, r.LookAhead)

            def SetRuleData(r, d):
                (r.Class,) = d
                (r.GlyphCount,) = (len(x) + 1 for x in d)

            def ChainSetRuleData(r, d):
                (r.Backtrack, r.Input, r.LookAhead) = d
                (
                    r.BacktrackGlyphCount,
                    r.InputGlyphCount,
                    r.LookAheadGlyphCount,
                ) = (len(d[0]), len(d[1]) + 1, len(d[2]))

        elif Format == 3:
            Coverage = lambda r: r.Coverage[0]
            ChainCoverage = lambda r: r.InputCoverage[0]
            ContextData = None
            ChainContextData = None
            SetContextData = None
            SetChainContextData = None
            RuleData = lambda r: r.Coverage
            ChainRuleData = lambda r: (
                r.BacktrackCoverage + r.InputCoverage + r.LookAheadCoverage
            )

            def SetRuleData(r, d):
                (r.Coverage,) = d
                (r.GlyphCount,) = (len(x) for x in d)

            def ChainSetRuleData(r, d):
                (r.BacktrackCoverage, r.InputCoverage, r.LookAheadCoverage) = d
                (
                    r.BacktrackGlyphCount,
                    r.InputGlyphCount,
                    r.LookAheadGlyphCount,
                ) = (len(x) for x in d)

        else:
            assert 0, "unknown format: %s" % Format

        if Chain:
            self.Coverage = ChainCoverage
            self.ContextData = ChainContextData
            self.SetContextData = SetChainContextData
            self.RuleData = ChainRuleData
            self.SetRuleData = ChainSetRuleData
        else:
            self.Coverage = Coverage
            self.ContextData = ContextData
            self.SetContextData = SetContextData
            self.RuleData = RuleData
            self.SetRuleData = SetRuleData

        if Format == 1:
            self.Rule = ChainTyp + "Rule"
            self.RuleCount = ChainTyp + "RuleCount"
            self.RuleSet = ChainTyp + "RuleSet"
            self.RuleSetCount = ChainTyp + "RuleSetCount"
            self.Intersect = lambda glyphs, c, r: [r] if r in glyphs else []
        elif Format == 2:
            self.Rule = ChainTyp + "ClassRule"
            self.RuleCount = ChainTyp + "ClassRuleCount"
            self.RuleSet = ChainTyp + "ClassSet"
            self.RuleSetCount = ChainTyp + "ClassSetCount"
            self.Intersect = lambda glyphs, c, r: (
                c.intersect_class(glyphs, r)
                if c
                else (set(glyphs) if r == 0 else set())
            )

            self.ClassDef = "InputClassDef" if Chain else "ClassDef"
            self.ClassDefIndex = 1 if Chain else 0
            self.Input = "Input" if Chain else "Class"


def parseLookupRecords(items, klassName, lookupMap=None):
    klass = getattr(ot, klassName)
    lst = []
    for item in items:
        rec = klass()
        item = stripSplitComma(item)
        assert len(item) == 2, item
        idx = int(item[0])
        assert idx > 0, idx
        rec.SequenceIndex = idx - 1
        setReference(mapLookup, lookupMap, item[1], setattr, rec, "LookupListIndex")
        lst.append(rec)
    return lst


def makeClassDef(classDefs, font, klass=ot.Coverage):
    if not classDefs:
        return None
    self = klass()
    self.classDefs = dict(classDefs)
    return self


def parseClassDef(lines, font, klass=ot.ClassDef):
    classDefs = {}
    with lines.between("class definition"):
        for line in lines:
            glyph = makeGlyph(line[0])
            assert glyph not in classDefs, glyph
            classDefs[glyph] = int(line[1])
    return makeClassDef(classDefs, font, klass)


def makeCoverage(glyphs, font, klass=ot.Coverage):
    if not glyphs:
        return None
    if isinstance(glyphs, set):
        glyphs = sorted(glyphs)
    coverage = klass()
    coverage.glyphs = sorted(set(glyphs), key=font.getGlyphID)
    return coverage


def parseCoverage(lines, font, klass=ot.Coverage):
    glyphs = []
    with lines.between("coverage definition"):
        for line in lines:
            glyphs.append(makeGlyph(line[0]))
    return makeCoverage(glyphs, font, klass)


def bucketizeRules(self, c, rules, bucketKeys):
    buckets = {}
    for seq, recs in rules:
        buckets.setdefault(seq[c.InputIdx][0], []).append(
            (tuple(s[1 if i == c.InputIdx else 0 :] for i, s in enumerate(seq)), recs)
        )

    rulesets = []
    for firstGlyph in bucketKeys:
        if firstGlyph not in buckets:
            rulesets.append(None)
            continue
        thisRules = []
        for seq, recs in buckets[firstGlyph]:
            rule = getattr(ot, c.Rule)()
            c.SetRuleData(rule, seq)
            setattr(rule, c.Type + "Count", len(recs))
            setattr(rule, c.LookupRecord, recs)
            thisRules.append(rule)

        ruleset = getattr(ot, c.RuleSet)()
        setattr(ruleset, c.Rule, thisRules)
        setattr(ruleset, c.RuleCount, len(thisRules))
        rulesets.append(ruleset)

    setattr(self, c.RuleSet, rulesets)
    setattr(self, c.RuleSetCount, len(rulesets))


def parseContext(lines, font, Type, lookupMap=None):
    self = getattr(ot, Type)()
    typ = lines.peeks()[0].split()[0].lower()
    if typ == "glyph":
        self.Format = 1
        log.debug("Parsing %s format %s", Type, self.Format)
        c = ContextHelper(Type, self.Format)
        rules = []
        for line in lines:
            assert line[0].lower() == "glyph", line[0]
            while len(line) < 1 + c.DataLen:
                line.append("")
            seq = tuple(makeGlyphs(stripSplitComma(i)) for i in line[1 : 1 + c.DataLen])
            recs = parseLookupRecords(line[1 + c.DataLen :], c.LookupRecord, lookupMap)
            rules.append((seq, recs))

        firstGlyphs = set(seq[c.InputIdx][0] for seq, recs in rules)
        self.Coverage = makeCoverage(firstGlyphs, font)
        bucketizeRules(self, c, rules, self.Coverage.glyphs)
    elif typ.endswith("class"):
        self.Format = 2
        log.debug("Parsing %s format %s", Type, self.Format)
        c = ContextHelper(Type, self.Format)
        classDefs = [None] * c.DataLen
        while lines.peeks()[0].endswith("class definition begin"):
            typ = lines.peek()[0][: -len("class definition begin")].lower()
            idx, klass = {
                1: {
                    "": (0, ot.ClassDef),
                },
                3: {
                    "backtrack": (0, ot.BacktrackClassDef),
                    "": (1, ot.InputClassDef),
                    "lookahead": (2, ot.LookAheadClassDef),
                },
            }[c.DataLen][typ]
            assert classDefs[idx] is None, idx
            classDefs[idx] = parseClassDef(lines, font, klass=klass)
        c.SetContextData(self, classDefs)
        rules = []
        for line in lines:
            assert line[0].lower().startswith("class"), line[0]
            while len(line) < 1 + c.DataLen:
                line.append("")
            seq = tuple(intSplitComma(i) for i in line[1 : 1 + c.DataLen])
            recs = parseLookupRecords(line[1 + c.DataLen :], c.LookupRecord, lookupMap)
            rules.append((seq, recs))
        firstClasses = set(seq[c.InputIdx][0] for seq, recs in rules)
        firstGlyphs = set(
            g for g, c in classDefs[c.InputIdx].classDefs.items() if c in firstClasses
        )
        self.Coverage = makeCoverage(firstGlyphs, font)
        bucketizeRules(self, c, rules, range(max(firstClasses) + 1))
    elif typ.endswith("coverage"):
        self.Format = 3
        log.debug("Parsing %s format %s", Type, self.Format)
        c = ContextHelper(Type, self.Format)
        coverages = tuple([] for i in range(c.DataLen))
        while lines.peeks()[0].endswith("coverage definition begin"):
            typ = lines.peek()[0][: -len("coverage definition begin")].lower()
            idx, klass = {
                1: {
                    "": (0, ot.Coverage),
                },
                3: {
                    "backtrack": (0, ot.BacktrackCoverage),
                    "input": (1, ot.InputCoverage),
                    "lookahead": (2, ot.LookAheadCoverage),
                },
            }[c.DataLen][typ]
            coverages[idx].append(parseCoverage(lines, font, klass=klass))
        c.SetRuleData(self, coverages)
        lines = list(lines)
        assert len(lines) == 1
        line = lines[0]
        assert line[0].lower() == "coverage", line[0]
        recs = parseLookupRecords(line[1:], c.LookupRecord, lookupMap)
        setattr(self, c.Type + "Count", len(recs))
        setattr(self, c.LookupRecord, recs)
    else:
        assert 0, typ
    return self


def parseContextSubst(lines, font, lookupMap=None):
    return parseContext(lines, font, "ContextSubst", lookupMap=lookupMap)


def parseContextPos(lines, font, lookupMap=None):
    return parseContext(lines, font, "ContextPos", lookupMap=lookupMap)


def parseChainedSubst(lines, font, lookupMap=None):
    return parseContext(lines, font, "ChainContextSubst", lookupMap=lookupMap)


def parseChainedPos(lines, font, lookupMap=None):
    return parseContext(lines, font, "ChainContextPos", lookupMap=lookupMap)


def parseReverseChainedSubst(lines, font, _lookupMap=None):
    self = ot.ReverseChainSingleSubst()
    self.Format = 1
    coverages = ([], [])
    while lines.peeks()[0].endswith("coverage definition begin"):
        typ = lines.peek()[0][: -len("coverage definition begin")].lower()
        idx, klass = {
            "backtrack": (0, ot.BacktrackCoverage),
            "lookahead": (1, ot.LookAheadCoverage),
        }[typ]
        coverages[idx].append(parseCoverage(lines, font, klass=klass))
    self.BacktrackCoverage = coverages[0]
    self.BacktrackGlyphCount = len(self.BacktrackCoverage)
    self.LookAheadCoverage = coverages[1]
    self.LookAheadGlyphCount = len(self.LookAheadCoverage)
    mapping = {}
    for line in lines:
        assert len(line) == 2, line
        line = makeGlyphs(line)
        mapping[line[0]] = line[1]
    self.Coverage = makeCoverage(set(mapping.keys()), font)
    self.Substitute = [mapping[k] for k in self.Coverage.glyphs]
    self.GlyphCount = len(self.Substitute)
    return self


def parseLookup(lines, tableTag, font, lookupMap=None):
    line = lines.expect("lookup")
    _, name, typ = line
    log.debug("Parsing lookup type %s %s", typ, name)
    lookup = ot.Lookup()
    lookup.LookupFlag, filterset = parseLookupFlags(lines)
    if filterset is not None:
        lookup.MarkFilteringSet = filterset
    lookup.LookupType, parseLookupSubTable = {
        "GSUB": {
            "single": (1, parseSingleSubst),
            "multiple": (2, parseMultiple),
            "alternate": (3, parseAlternate),
            "ligature": (4, parseLigature),
            "context": (5, parseContextSubst),
            "chained": (6, parseChainedSubst),
            "reversechained": (8, parseReverseChainedSubst),
        },
        "GPOS": {
            "single": (1, parseSinglePos),
            "pair": (2, parsePair),
            "kernset": (2, parseKernset),
            "cursive": (3, parseCursive),
            "mark to base": (4, parseMarkToBase),
            "mark to ligature": (5, parseMarkToLigature),
            "mark to mark": (6, parseMarkToMark),
            "context": (7, parseContextPos),
            "chained": (8, parseChainedPos),
        },
    }[tableTag][typ]

    with lines.until("lookup end"):
        subtables = []

        while lines.peek():
            with lines.until(("% subtable", "subtable end")):
                while lines.peek():
                    subtable = parseLookupSubTable(lines, font, lookupMap)
                    assert lookup.LookupType == subtable.LookupType
                    subtables.append(subtable)
            if lines.peeks()[0] in ("% subtable", "subtable end"):
                next(lines)
    lines.expect("lookup end")

    lookup.SubTable = subtables
    lookup.SubTableCount = len(lookup.SubTable)
    if lookup.SubTableCount == 0:
        # Remove this return when following is fixed:
        # https://github.com/fonttools/fonttools/issues/789
        return None
    return lookup


def parseGSUBGPOS(lines, font, tableTag):
    container = ttLib.getTableClass(tableTag)()
    lookupMap = DeferredMapping()
    featureMap = DeferredMapping()
    assert tableTag in ("GSUB", "GPOS")
    log.debug("Parsing %s", tableTag)
    self = getattr(ot, tableTag)()
    self.Version = 0x00010000
    fields = {
        "script table begin": (
            "ScriptList",
            lambda lines: parseScriptList(lines, featureMap),
        ),
        "feature table begin": (
            "FeatureList",
            lambda lines: parseFeatureList(lines, lookupMap, featureMap),
        ),
        "lookup": ("LookupList", None),
    }
    for attr, parser in fields.values():
        setattr(self, attr, None)
    while lines.peek() is not None:
        typ = lines.peek()[0].lower()
        if typ not in fields:
            log.debug("Skipping %s", lines.peek())
            next(lines)
            continue
        attr, parser = fields[typ]
        if typ == "lookup":
            if self.LookupList is None:
                self.LookupList = ot.LookupList()
                self.LookupList.Lookup = []
            _, name, _ = lines.peek()
            lookup = parseLookup(lines, tableTag, font, lookupMap)
            if lookupMap is not None:
                assert name not in lookupMap, "Duplicate lookup name: %s" % name
                lookupMap[name] = len(self.LookupList.Lookup)
            else:
                assert int(name) == len(self.LookupList.Lookup), "%d %d" % (
                    name,
                    len(self.Lookup),
                )
            self.LookupList.Lookup.append(lookup)
        else:
            assert getattr(self, attr) is None, attr
            setattr(self, attr, parser(lines))
    if self.LookupList:
        self.LookupList.LookupCount = len(self.LookupList.Lookup)
    if lookupMap is not None:
        lookupMap.applyDeferredMappings()
        if os.environ.get(LOOKUP_DEBUG_ENV_VAR):
            if "Debg" not in font:
                font["Debg"] = newTable("Debg")
                font["Debg"].data = {}
            debug = (
                font["Debg"]
                .data.setdefault(LOOKUP_DEBUG_INFO_KEY, {})
                .setdefault(tableTag, {})
            )
            for name, lookup in lookupMap.items():
                debug[str(lookup)] = ["", name, ""]

        featureMap.applyDeferredMappings()
    container.table = self
    return container


def parseGSUB(lines, font):
    return parseGSUBGPOS(lines, font, "GSUB")


def parseGPOS(lines, font):
    return parseGSUBGPOS(lines, font, "GPOS")


def parseAttachList(lines, font):
    points = {}
    with lines.between("attachment list"):
        for line in lines:
            glyph = makeGlyph(line[0])
            assert glyph not in points, glyph
            points[glyph] = [int(i) for i in line[1:]]
    return otl.buildAttachList(points, font.getReverseGlyphMap())


def parseCaretList(lines, font):
    carets = {}
    with lines.between("carets"):
        for line in lines:
            glyph = makeGlyph(line[0])
            assert glyph not in carets, glyph
            num = int(line[1])
            thisCarets = [int(i) for i in line[2:]]
            assert num == len(thisCarets), line
            carets[glyph] = thisCarets
    return otl.buildLigCaretList(carets, {}, font.getReverseGlyphMap())


def makeMarkFilteringSets(sets, font):
    self = ot.MarkGlyphSetsDef()
    self.MarkSetTableFormat = 1
    self.MarkSetCount = 1 + max(sets.keys())
    self.Coverage = [None] * self.MarkSetCount
    for k, v in sorted(sets.items()):
        self.Coverage[k] = makeCoverage(set(v), font)
    return self


def parseMarkFilteringSets(lines, font):
    sets = {}
    with lines.between("set definition"):
        for line in lines:
            assert len(line) == 2, line
            glyph = makeGlyph(line[0])
            # TODO accept set names
            st = int(line[1])
            if st not in sets:
                sets[st] = []
            sets[st].append(glyph)
    return makeMarkFilteringSets(sets, font)


def parseGDEF(lines, font):
    container = ttLib.getTableClass("GDEF")()
    log.debug("Parsing GDEF")
    self = ot.GDEF()
    fields = {
        "class definition begin": (
            "GlyphClassDef",
            lambda lines, font: parseClassDef(lines, font, klass=ot.GlyphClassDef),
        ),
        "attachment list begin": ("AttachList", parseAttachList),
        "carets begin": ("LigCaretList", parseCaretList),
        "mark attachment class definition begin": (
            "MarkAttachClassDef",
            lambda lines, font: parseClassDef(lines, font, klass=ot.MarkAttachClassDef),
        ),
        "markfilter set definition begin": ("MarkGlyphSetsDef", parseMarkFilteringSets),
    }
    for attr, parser in fields.values():
        setattr(self, attr, None)
    while lines.peek() is not None:
        typ = lines.peek()[0].lower()
        if typ not in fields:
            log.debug("Skipping %s", typ)
            next(lines)
            continue
        attr, parser = fields[typ]
        assert getattr(self, attr) is None, attr
        setattr(self, attr, parser(lines, font))
    self.Version = 0x00010000 if self.MarkGlyphSetsDef is None else 0x00010002
    container.table = self
    return container


def parseCmap(lines, font):
    container = ttLib.getTableClass("cmap")()
    log.debug("Parsing cmap")
    tables = []
    while lines.peek() is not None:
        lines.expect("cmap subtable %d" % len(tables))
        platId, encId, fmt, lang = [
            parseCmapId(lines, field)
            for field in ("platformID", "encodingID", "format", "language")
        ]
        table = cmap_classes[fmt](fmt)
        table.platformID = platId
        table.platEncID = encId
        table.language = lang
        table.cmap = {}
        line = next(lines)
        while line[0] != "end subtable":
            table.cmap[int(line[0], 16)] = line[1]
            line = next(lines)
        tables.append(table)
    container.tableVersion = 0
    container.tables = tables
    return container


def parseCmapId(lines, field):
    line = next(lines)
    assert field == line[0]
    return int(line[1])


def parseTable(lines, font, tableTag=None):
    log.debug("Parsing table")
    line = lines.peeks()
    tag = None
    if line[0].split()[0] == "FontDame":
        tag = line[0].split()[1]
    elif " ".join(line[0].split()[:3]) == "Font Chef Table":
        tag = line[0].split()[3]
    if tag is not None:
        next(lines)
        tag = tag.ljust(4)
        if tableTag is None:
            tableTag = tag
        else:
            assert tableTag == tag, (tableTag, tag)

    assert (
        tableTag is not None
    ), "Don't know what table to parse and data doesn't specify"

    return {
        "GSUB": parseGSUB,
        "GPOS": parseGPOS,
        "GDEF": parseGDEF,
        "cmap": parseCmap,
    }[tableTag](lines, font)


class Tokenizer(object):
    def __init__(self, f):
        # TODO BytesIO / StringIO as needed?  also, figure out whether we work on bytes or unicode
        lines = iter(f)
        try:
            self.filename = f.name
        except:
            self.filename = None
        self.lines = iter(lines)
        self.line = ""
        self.lineno = 0
        self.stoppers = []
        self.buffer = None

    def __iter__(self):
        return self

    def _next_line(self):
        self.lineno += 1
        line = self.line = next(self.lines)
        line = [s.strip() for s in line.split("\t")]
        if len(line) == 1 and not line[0]:
            del line[0]
        if line and not line[-1]:
            log.warning("trailing tab found on line %d: %s" % (self.lineno, self.line))
            while line and not line[-1]:
                del line[-1]
        return line

    def _next_nonempty(self):
        while True:
            line = self._next_line()
            # Skip comments and empty lines
            if line and line[0] and (line[0][0] != "%" or line[0] == "% subtable"):
                return line

    def _next_buffered(self):
        if self.buffer:
            ret = self.buffer
            self.buffer = None
            return ret
        else:
            return self._next_nonempty()

    def __next__(self):
        line = self._next_buffered()
        if line[0].lower() in self.stoppers:
            self.buffer = line
            raise StopIteration
        return line

    def next(self):
        return self.__next__()

    def peek(self):
        if not self.buffer:
            try:
                self.buffer = self._next_nonempty()
            except StopIteration:
                return None
        if self.buffer[0].lower() in self.stoppers:
            return None
        return self.buffer

    def peeks(self):
        ret = self.peek()
        return ret if ret is not None else ("",)

    @contextmanager
    def between(self, tag):
        start = tag + " begin"
        end = tag + " end"
        self.expectendswith(start)
        self.stoppers.append(end)
        yield
        del self.stoppers[-1]
        self.expect(tag + " end")

    @contextmanager
    def until(self, tags):
        if type(tags) is not tuple:
            tags = (tags,)
        self.stoppers.extend(tags)
        yield
        del self.stoppers[-len(tags) :]

    def expect(self, s):
        line = next(self)
        tag = line[0].lower()
        assert tag == s, "Expected '%s', got '%s'" % (s, tag)
        return line

    def expectendswith(self, s):
        line = next(self)
        tag = line[0].lower()
        assert tag.endswith(s), "Expected '*%s', got '%s'" % (s, tag)
        return line


def build(f, font, tableTag=None):
    """Convert a Monotype font layout file to an OpenType layout object

    A font object must be passed, but this may be a "dummy" font; it is only
    used for sorting glyph sets when making coverage tables and to hold the
    OpenType layout table while it is being built.

    Args:
            f: A file object.
            font (TTFont): A font object.
            tableTag (string): If provided, asserts that the file contains data for the
                    given OpenType table.

    Returns:
            An object representing the table. (e.g. ``table_G_S_U_B_``)
    """
    lines = Tokenizer(f)
    return parseTable(lines, font, tableTag=tableTag)


def main(args=None, font=None):
    """Convert a FontDame OTL file to TTX XML

    Writes XML output to stdout.

    Args:
            args: Command line arguments (``--font``, ``--table``, input files).
    """
    import sys
    from fontTools import configLogger
    from fontTools.misc.testTools import MockFont

    if args is None:
        args = sys.argv[1:]

    # configure the library logger (for >= WARNING)
    configLogger()
    # comment this out to enable debug messages from mtiLib's logger
    # log.setLevel(logging.DEBUG)

    import argparse

    parser = argparse.ArgumentParser(
        "fonttools mtiLib",
        description=main.__doc__,
    )

    parser.add_argument(
        "--font",
        "-f",
        metavar="FILE",
        dest="font",
        help="Input TTF files (used for glyph classes and sorting coverage tables)",
    )
    parser.add_argument(
        "--table",
        "-t",
        metavar="TABLE",
        dest="tableTag",
        help="Table to fill (sniffed from input file if not provided)",
    )
    parser.add_argument(
        "inputs", metavar="FILE", type=str, nargs="+", help="Input FontDame .txt files"
    )

    args = parser.parse_args(args)

    if font is None:
        if args.font:
            font = ttLib.TTFont(args.font)
        else:
            font = MockFont()

    for f in args.inputs:
        log.debug("Processing %s", f)
        with open(f, "rt", encoding="utf-8-sig") as f:
            table = build(f, font, tableTag=args.tableTag)
        blob = table.compile(font)  # Make sure it compiles
        decompiled = table.__class__()
        decompiled.decompile(blob, font)  # Make sure it decompiles!

        # continue
        from fontTools.misc import xmlWriter

        tag = table.tableTag
        writer = xmlWriter.XMLWriter(sys.stdout)
        writer.begintag(tag)
        writer.newline()
        # table.toXML(writer, font)
        decompiled.toXML(writer, font)
        writer.endtag(tag)
        writer.newline()


if __name__ == "__main__":
    import sys

    sys.exit(main())
