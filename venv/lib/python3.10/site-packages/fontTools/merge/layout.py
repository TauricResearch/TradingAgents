# Copyright 2013 Google, Inc. All Rights Reserved.
#
# Google Author(s): Behdad Esfahbod, Roozbeh Pournader

from fontTools import ttLib
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from fontTools.ttLib.tables import otTables
from fontTools.merge.base import add_method, mergeObjects
from fontTools.merge.util import *
import logging


log = logging.getLogger("fontTools.merge")


def mergeLookupLists(lst):
    # TODO Do smarter merge.
    return sumLists(lst)


def mergeFeatures(lst):
    assert lst
    self = otTables.Feature()
    self.FeatureParams = None
    self.LookupListIndex = mergeLookupLists(
        [l.LookupListIndex for l in lst if l.LookupListIndex]
    )
    self.LookupCount = len(self.LookupListIndex)
    return self


def mergeFeatureLists(lst):
    d = {}
    for l in lst:
        for f in l:
            tag = f.FeatureTag
            if tag not in d:
                d[tag] = []
            d[tag].append(f.Feature)
    ret = []
    for tag in sorted(d.keys()):
        rec = otTables.FeatureRecord()
        rec.FeatureTag = tag
        rec.Feature = mergeFeatures(d[tag])
        ret.append(rec)
    return ret


def mergeLangSyses(lst):
    assert lst

    # TODO Support merging ReqFeatureIndex
    assert all(l.ReqFeatureIndex == 0xFFFF for l in lst)

    self = otTables.LangSys()
    self.LookupOrder = None
    self.ReqFeatureIndex = 0xFFFF
    self.FeatureIndex = mergeFeatureLists(
        [l.FeatureIndex for l in lst if l.FeatureIndex]
    )
    self.FeatureCount = len(self.FeatureIndex)
    return self


def mergeScripts(lst):
    assert lst

    if len(lst) == 1:
        return lst[0]
    langSyses = {}
    for sr in lst:
        for lsr in sr.LangSysRecord:
            if lsr.LangSysTag not in langSyses:
                langSyses[lsr.LangSysTag] = []
            langSyses[lsr.LangSysTag].append(lsr.LangSys)
    lsrecords = []
    for tag, langSys_list in sorted(langSyses.items()):
        lsr = otTables.LangSysRecord()
        lsr.LangSys = mergeLangSyses(langSys_list)
        lsr.LangSysTag = tag
        lsrecords.append(lsr)

    self = otTables.Script()
    self.LangSysRecord = lsrecords
    self.LangSysCount = len(lsrecords)
    dfltLangSyses = [s.DefaultLangSys for s in lst if s.DefaultLangSys]
    if dfltLangSyses:
        self.DefaultLangSys = mergeLangSyses(dfltLangSyses)
    else:
        self.DefaultLangSys = None
    return self


def mergeScriptRecords(lst):
    d = {}
    for l in lst:
        for s in l:
            tag = s.ScriptTag
            if tag not in d:
                d[tag] = []
            d[tag].append(s.Script)
    ret = []
    for tag in sorted(d.keys()):
        rec = otTables.ScriptRecord()
        rec.ScriptTag = tag
        rec.Script = mergeScripts(d[tag])
        ret.append(rec)
    return ret


otTables.ScriptList.mergeMap = {
    "ScriptCount": lambda lst: None,  # TODO
    "ScriptRecord": mergeScriptRecords,
}
otTables.BaseScriptList.mergeMap = {
    "BaseScriptCount": lambda lst: None,  # TODO
    # TODO: Merge duplicate entries
    "BaseScriptRecord": lambda lst: sorted(
        sumLists(lst), key=lambda s: s.BaseScriptTag
    ),
}

otTables.FeatureList.mergeMap = {
    "FeatureCount": sum,
    "FeatureRecord": lambda lst: sorted(sumLists(lst), key=lambda s: s.FeatureTag),
}

otTables.LookupList.mergeMap = {
    "LookupCount": sum,
    "Lookup": sumLists,
}

otTables.Coverage.mergeMap = {
    "Format": min,
    "glyphs": sumLists,
}

otTables.ClassDef.mergeMap = {
    "Format": min,
    "classDefs": sumDicts,
}

otTables.LigCaretList.mergeMap = {
    "Coverage": mergeObjects,
    "LigGlyphCount": sum,
    "LigGlyph": sumLists,
}

otTables.AttachList.mergeMap = {
    "Coverage": mergeObjects,
    "GlyphCount": sum,
    "AttachPoint": sumLists,
}

# XXX Renumber MarkFilterSets of lookups
otTables.MarkGlyphSetsDef.mergeMap = {
    "MarkSetTableFormat": equal,
    "MarkSetCount": sum,
    "Coverage": sumLists,
}

otTables.Axis.mergeMap = {
    "*": mergeObjects,
}

# XXX Fix BASE table merging
otTables.BaseTagList.mergeMap = {
    "BaseTagCount": sum,
    "BaselineTag": sumLists,
}

otTables.GDEF.mergeMap = otTables.GSUB.mergeMap = otTables.GPOS.mergeMap = (
    otTables.BASE.mergeMap
) = otTables.JSTF.mergeMap = otTables.MATH.mergeMap = {
    "*": mergeObjects,
    "Version": max,
}

ttLib.getTableClass("GDEF").mergeMap = ttLib.getTableClass("GSUB").mergeMap = (
    ttLib.getTableClass("GPOS").mergeMap
) = ttLib.getTableClass("BASE").mergeMap = ttLib.getTableClass(
    "JSTF"
).mergeMap = ttLib.getTableClass(
    "MATH"
).mergeMap = {
    "tableTag": onlyExisting(equal),  # XXX clean me up
    "table": mergeObjects,
}


@add_method(ttLib.getTableClass("GSUB"))
def merge(self, m, tables):
    assert len(tables) == len(m.duplicateGlyphsPerFont)
    for i, (table, dups) in enumerate(zip(tables, m.duplicateGlyphsPerFont)):
        if not dups:
            continue
        if table is None or table is NotImplemented:
            log.warning(
                "Have non-identical duplicates to resolve for '%s' but no GSUB. Are duplicates intended?: %s",
                m.fonts[i]._merger__name,
                dups,
            )
            continue

        synthFeature = None
        synthLookup = None
        for script in table.table.ScriptList.ScriptRecord:
            if script.ScriptTag == "DFLT":
                continue  # XXX
            for langsys in [script.Script.DefaultLangSys] + [
                l.LangSys for l in script.Script.LangSysRecord
            ]:
                if langsys is None:
                    continue  # XXX Create!
                feature = [v for v in langsys.FeatureIndex if v.FeatureTag == "locl"]
                assert len(feature) <= 1
                if feature:
                    feature = feature[0]
                else:
                    if not synthFeature:
                        synthFeature = otTables.FeatureRecord()
                        synthFeature.FeatureTag = "locl"
                        f = synthFeature.Feature = otTables.Feature()
                        f.FeatureParams = None
                        f.LookupCount = 0
                        f.LookupListIndex = []
                        table.table.FeatureList.FeatureRecord.append(synthFeature)
                        table.table.FeatureList.FeatureCount += 1
                    feature = synthFeature
                    langsys.FeatureIndex.append(feature)
                    langsys.FeatureIndex.sort(key=lambda v: v.FeatureTag)

                if not synthLookup:
                    subtable = otTables.SingleSubst()
                    subtable.mapping = dups
                    synthLookup = otTables.Lookup()
                    synthLookup.LookupFlag = 0
                    synthLookup.LookupType = 1
                    synthLookup.SubTableCount = 1
                    synthLookup.SubTable = [subtable]
                    if table.table.LookupList is None:
                        # mtiLib uses None as default value for LookupList,
                        # while feaLib points to an empty array with count 0
                        # TODO: make them do the same
                        table.table.LookupList = otTables.LookupList()
                        table.table.LookupList.Lookup = []
                        table.table.LookupList.LookupCount = 0
                    table.table.LookupList.Lookup.append(synthLookup)
                    table.table.LookupList.LookupCount += 1

                if feature.Feature.LookupListIndex[:1] != [synthLookup]:
                    feature.Feature.LookupListIndex[:0] = [synthLookup]
                    feature.Feature.LookupCount += 1

    DefaultTable.merge(self, m, tables)
    return self


@add_method(
    otTables.SingleSubst,
    otTables.MultipleSubst,
    otTables.AlternateSubst,
    otTables.LigatureSubst,
    otTables.ReverseChainSingleSubst,
    otTables.SinglePos,
    otTables.PairPos,
    otTables.CursivePos,
    otTables.MarkBasePos,
    otTables.MarkLigPos,
    otTables.MarkMarkPos,
)
def mapLookups(self, lookupMap):
    pass


# Copied and trimmed down from subset.py
@add_method(
    otTables.ContextSubst,
    otTables.ChainContextSubst,
    otTables.ContextPos,
    otTables.ChainContextPos,
)
def __merge_classify_context(self):
    class ContextHelper(object):
        def __init__(self, klass, Format):
            if klass.__name__.endswith("Subst"):
                Typ = "Sub"
                Type = "Subst"
            else:
                Typ = "Pos"
                Type = "Pos"
            if klass.__name__.startswith("Chain"):
                Chain = "Chain"
            else:
                Chain = ""
            ChainTyp = Chain + Typ

            self.Typ = Typ
            self.Type = Type
            self.Chain = Chain
            self.ChainTyp = ChainTyp

            self.LookupRecord = Type + "LookupRecord"

            if Format == 1:
                self.Rule = ChainTyp + "Rule"
                self.RuleSet = ChainTyp + "RuleSet"
            elif Format == 2:
                self.Rule = ChainTyp + "ClassRule"
                self.RuleSet = ChainTyp + "ClassSet"

    if self.Format not in [1, 2, 3]:
        return None  # Don't shoot the messenger; let it go
    if not hasattr(self.__class__, "_merge__ContextHelpers"):
        self.__class__._merge__ContextHelpers = {}
    if self.Format not in self.__class__._merge__ContextHelpers:
        helper = ContextHelper(self.__class__, self.Format)
        self.__class__._merge__ContextHelpers[self.Format] = helper
    return self.__class__._merge__ContextHelpers[self.Format]


@add_method(
    otTables.ContextSubst,
    otTables.ChainContextSubst,
    otTables.ContextPos,
    otTables.ChainContextPos,
)
def mapLookups(self, lookupMap):
    c = self.__merge_classify_context()

    if self.Format in [1, 2]:
        for rs in getattr(self, c.RuleSet):
            if not rs:
                continue
            for r in getattr(rs, c.Rule):
                if not r:
                    continue
                for ll in getattr(r, c.LookupRecord):
                    if not ll:
                        continue
                    ll.LookupListIndex = lookupMap[ll.LookupListIndex]
    elif self.Format == 3:
        for ll in getattr(self, c.LookupRecord):
            if not ll:
                continue
            ll.LookupListIndex = lookupMap[ll.LookupListIndex]
    else:
        assert 0, "unknown format: %s" % self.Format


@add_method(otTables.ExtensionSubst, otTables.ExtensionPos)
def mapLookups(self, lookupMap):
    if self.Format == 1:
        self.ExtSubTable.mapLookups(lookupMap)
    else:
        assert 0, "unknown format: %s" % self.Format


@add_method(otTables.Lookup)
def mapLookups(self, lookupMap):
    for st in self.SubTable:
        if not st:
            continue
        st.mapLookups(lookupMap)


@add_method(otTables.LookupList)
def mapLookups(self, lookupMap):
    for l in self.Lookup:
        if not l:
            continue
        l.mapLookups(lookupMap)


@add_method(otTables.Lookup)
def mapMarkFilteringSets(self, markFilteringSetMap):
    if self.LookupFlag & 0x0010:
        self.MarkFilteringSet = markFilteringSetMap[self.MarkFilteringSet]


@add_method(otTables.LookupList)
def mapMarkFilteringSets(self, markFilteringSetMap):
    for l in self.Lookup:
        if not l:
            continue
        l.mapMarkFilteringSets(markFilteringSetMap)


@add_method(otTables.Feature)
def mapLookups(self, lookupMap):
    self.LookupListIndex = [lookupMap[i] for i in self.LookupListIndex]


@add_method(otTables.FeatureList)
def mapLookups(self, lookupMap):
    for f in self.FeatureRecord:
        if not f or not f.Feature:
            continue
        f.Feature.mapLookups(lookupMap)


@add_method(otTables.DefaultLangSys, otTables.LangSys)
def mapFeatures(self, featureMap):
    self.FeatureIndex = [featureMap[i] for i in self.FeatureIndex]
    if self.ReqFeatureIndex != 65535:
        self.ReqFeatureIndex = featureMap[self.ReqFeatureIndex]


@add_method(otTables.Script)
def mapFeatures(self, featureMap):
    if self.DefaultLangSys:
        self.DefaultLangSys.mapFeatures(featureMap)
    for l in self.LangSysRecord:
        if not l or not l.LangSys:
            continue
        l.LangSys.mapFeatures(featureMap)


@add_method(otTables.ScriptList)
def mapFeatures(self, featureMap):
    for s in self.ScriptRecord:
        if not s or not s.Script:
            continue
        s.Script.mapFeatures(featureMap)


def layoutPreMerge(font):
    # Map indices to references

    GDEF = font.get("GDEF")
    GSUB = font.get("GSUB")
    GPOS = font.get("GPOS")

    for t in [GSUB, GPOS]:
        if not t:
            continue

        if t.table.LookupList:
            lookupMap = {i: v for i, v in enumerate(t.table.LookupList.Lookup)}
            t.table.LookupList.mapLookups(lookupMap)
            t.table.FeatureList.mapLookups(lookupMap)

            if (
                GDEF
                and GDEF.table.Version >= 0x00010002
                and GDEF.table.MarkGlyphSetsDef
            ):
                markFilteringSetMap = {
                    i: v for i, v in enumerate(GDEF.table.MarkGlyphSetsDef.Coverage)
                }
                t.table.LookupList.mapMarkFilteringSets(markFilteringSetMap)

        if t.table.FeatureList and t.table.ScriptList:
            featureMap = {i: v for i, v in enumerate(t.table.FeatureList.FeatureRecord)}
            t.table.ScriptList.mapFeatures(featureMap)

    # TODO FeatureParams nameIDs


def layoutPostMerge(font):
    # Map references back to indices

    GDEF = font.get("GDEF")
    GSUB = font.get("GSUB")
    GPOS = font.get("GPOS")

    for t in [GSUB, GPOS]:
        if not t:
            continue

        if t.table.FeatureList and t.table.ScriptList:
            # Collect unregistered (new) features.
            featureMap = GregariousIdentityDict(t.table.FeatureList.FeatureRecord)
            t.table.ScriptList.mapFeatures(featureMap)

            # Record used features.
            featureMap = AttendanceRecordingIdentityDict(
                t.table.FeatureList.FeatureRecord
            )
            t.table.ScriptList.mapFeatures(featureMap)
            usedIndices = featureMap.s

            # Remove unused features
            t.table.FeatureList.FeatureRecord = [
                f
                for i, f in enumerate(t.table.FeatureList.FeatureRecord)
                if i in usedIndices
            ]

            # Map back to indices.
            featureMap = NonhashableDict(t.table.FeatureList.FeatureRecord)
            t.table.ScriptList.mapFeatures(featureMap)

            t.table.FeatureList.FeatureCount = len(t.table.FeatureList.FeatureRecord)

        if t.table.LookupList:
            # Collect unregistered (new) lookups.
            lookupMap = GregariousIdentityDict(t.table.LookupList.Lookup)
            t.table.FeatureList.mapLookups(lookupMap)
            t.table.LookupList.mapLookups(lookupMap)

            # Record used lookups.
            lookupMap = AttendanceRecordingIdentityDict(t.table.LookupList.Lookup)
            t.table.FeatureList.mapLookups(lookupMap)
            t.table.LookupList.mapLookups(lookupMap)
            usedIndices = lookupMap.s

            # Remove unused lookups
            t.table.LookupList.Lookup = [
                l for i, l in enumerate(t.table.LookupList.Lookup) if i in usedIndices
            ]

            # Map back to indices.
            lookupMap = NonhashableDict(t.table.LookupList.Lookup)
            t.table.FeatureList.mapLookups(lookupMap)
            t.table.LookupList.mapLookups(lookupMap)

            t.table.LookupList.LookupCount = len(t.table.LookupList.Lookup)

            if GDEF and GDEF.table.Version >= 0x00010002:
                markFilteringSetMap = NonhashableDict(
                    GDEF.table.MarkGlyphSetsDef.Coverage
                )
                t.table.LookupList.mapMarkFilteringSets(markFilteringSetMap)

    # TODO FeatureParams nameIDs
