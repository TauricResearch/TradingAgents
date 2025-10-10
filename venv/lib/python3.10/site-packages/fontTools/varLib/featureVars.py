"""Module to build FeatureVariation tables:
https://docs.microsoft.com/en-us/typography/opentype/spec/chapter2#featurevariations-table

NOTE: The API is experimental and subject to change.
"""

from fontTools.misc.dictTools import hashdict
from fontTools.misc.intTools import bit_count
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.ttVisitor import TTVisitor
from fontTools.otlLib.builder import buildLookup, buildSingleSubstSubtable
from collections import OrderedDict

from .errors import VarLibError, VarLibValidationError


def addFeatureVariations(font, conditionalSubstitutions, featureTag="rvrn"):
    """Add conditional substitutions to a Variable Font.

    The `conditionalSubstitutions` argument is a list of (Region, Substitutions)
    tuples.

    A Region is a list of Boxes. A Box is a dict mapping axisTags to
    (minValue, maxValue) tuples. Irrelevant axes may be omitted and they are
    interpretted as extending to end of axis in each direction.  A Box represents
    an orthogonal 'rectangular' subset of an N-dimensional design space.
    A Region represents a more complex subset of an N-dimensional design space,
    ie. the union of all the Boxes in the Region.
    For efficiency, Boxes within a Region should ideally not overlap, but
    functionality is not compromised if they do.

    The minimum and maximum values are expressed in normalized coordinates.

    A Substitution is a dict mapping source glyph names to substitute glyph names.

    Example:

    # >>> f = TTFont(srcPath)
    # >>> condSubst = [
    # ...     # A list of (Region, Substitution) tuples.
    # ...     ([{"wdth": (0.5, 1.0)}], {"cent": "cent.rvrn"}),
    # ...     ([{"wght": (0.5, 1.0)}], {"dollar": "dollar.rvrn"}),
    # ... ]
    # >>> addFeatureVariations(f, condSubst)
    # >>> f.save(dstPath)

    The `featureTag` parameter takes either a str or a iterable of str (the single str
    is kept for backwards compatibility), and defines which feature(s) will be
    associated with the feature variations.
    Note, if this is "rvrn", then the substitution lookup will be inserted at the
    beginning of the lookup list so that it is processed before others, otherwise
    for any other feature tags it will be appended last.
    """

    # process first when "rvrn" is the only listed tag
    featureTags = [featureTag] if isinstance(featureTag, str) else sorted(featureTag)
    processLast = "rvrn" not in featureTags or len(featureTags) > 1

    _checkSubstitutionGlyphsExist(
        glyphNames=set(font.getGlyphOrder()),
        substitutions=conditionalSubstitutions,
    )

    substitutions = overlayFeatureVariations(conditionalSubstitutions)

    # turn substitution dicts into tuples of tuples, so they are hashable
    conditionalSubstitutions, allSubstitutions = makeSubstitutionsHashable(
        substitutions
    )
    if "GSUB" not in font:
        font["GSUB"] = buildGSUB()
    else:
        existingTags = _existingVariableFeatures(font["GSUB"].table).intersection(
            featureTags
        )
        if existingTags:
            raise VarLibError(
                f"FeatureVariations already exist for feature tag(s): {existingTags}"
            )

    # setup lookups
    lookupMap = buildSubstitutionLookups(
        font["GSUB"].table, allSubstitutions, processLast
    )

    # addFeatureVariationsRaw takes a list of
    #  ( {condition}, [ lookup indices ] )
    # so rearrange our lookups to match
    conditionsAndLookups = []
    for conditionSet, substitutions in conditionalSubstitutions:
        conditionsAndLookups.append(
            (conditionSet, [lookupMap[s] for s in substitutions])
        )

    addFeatureVariationsRaw(font, font["GSUB"].table, conditionsAndLookups, featureTags)

    # Update OS/2.usMaxContext in case the font didn't have features before, but
    # does now, if the OS/2 table exists. The table may be required, but
    # fontTools needs to be able to deal with non-standard fonts. Since feature
    # variations are always 1:1 mappings, we can set the value to at least 1
    # instead of recomputing it with `otlLib.maxContextCalc.maxCtxFont()`.
    if (os2 := font.get("OS/2")) is not None:
        os2.usMaxContext = max(1, os2.usMaxContext)


def _existingVariableFeatures(table):
    existingFeatureVarsTags = set()
    if hasattr(table, "FeatureVariations") and table.FeatureVariations is not None:
        features = table.FeatureList.FeatureRecord
        for fvr in table.FeatureVariations.FeatureVariationRecord:
            for ftsr in fvr.FeatureTableSubstitution.SubstitutionRecord:
                existingFeatureVarsTags.add(features[ftsr.FeatureIndex].FeatureTag)
    return existingFeatureVarsTags


def _checkSubstitutionGlyphsExist(glyphNames, substitutions):
    referencedGlyphNames = set()
    for _, substitution in substitutions:
        referencedGlyphNames |= substitution.keys()
        referencedGlyphNames |= set(substitution.values())
    missing = referencedGlyphNames - glyphNames
    if missing:
        raise VarLibValidationError(
            "Missing glyphs are referenced in conditional substitution rules:"
            f" {', '.join(missing)}"
        )


def overlayFeatureVariations(conditionalSubstitutions):
    """Compute overlaps between all conditional substitutions.

    The `conditionalSubstitutions` argument is a list of (Region, Substitutions)
    tuples.

    A Region is a list of Boxes. A Box is a dict mapping axisTags to
    (minValue, maxValue) tuples. Irrelevant axes may be omitted and they are
    interpretted as extending to end of axis in each direction.  A Box represents
    an orthogonal 'rectangular' subset of an N-dimensional design space.
    A Region represents a more complex subset of an N-dimensional design space,
    ie. the union of all the Boxes in the Region.
    For efficiency, Boxes within a Region should ideally not overlap, but
    functionality is not compromised if they do.

    The minimum and maximum values are expressed in normalized coordinates.

    A Substitution is a dict mapping source glyph names to substitute glyph names.

    Returns data is in similar but different format.  Overlaps of distinct
    substitution Boxes (*not* Regions) are explicitly listed as distinct rules,
    and rules with the same Box merged.  The more specific rules appear earlier
    in the resulting list.  Moreover, instead of just a dictionary of substitutions,
    a list of dictionaries is returned for substitutions corresponding to each
    unique space, with each dictionary being identical to one of the input
    substitution dictionaries.  These dictionaries are not merged to allow data
    sharing when they are converted into font tables.

    Example::

        >>> condSubst = [
        ...     # A list of (Region, Substitution) tuples.
        ...     ([{"wght": (0.5, 1.0)}], {"dollar": "dollar.rvrn"}),
        ...     ([{"wght": (0.5, 1.0)}], {"dollar": "dollar.rvrn"}),
        ...     ([{"wdth": (0.5, 1.0)}], {"cent": "cent.rvrn"}),
        ...     ([{"wght": (0.5, 1.0), "wdth": (-1, 1.0)}], {"dollar": "dollar.rvrn"}),
        ... ]
        >>> from pprint import pprint
        >>> pprint(overlayFeatureVariations(condSubst))
        [({'wdth': (0.5, 1.0), 'wght': (0.5, 1.0)},
          [{'dollar': 'dollar.rvrn'}, {'cent': 'cent.rvrn'}]),
         ({'wdth': (0.5, 1.0)}, [{'cent': 'cent.rvrn'}]),
         ({'wght': (0.5, 1.0)}, [{'dollar': 'dollar.rvrn'}])]

    """

    # Merge same-substitutions rules, as this creates fewer number oflookups.
    merged = OrderedDict()
    for value, key in conditionalSubstitutions:
        key = hashdict(key)
        if key in merged:
            merged[key].extend(value)
        else:
            merged[key] = value
    conditionalSubstitutions = [(v, dict(k)) for k, v in merged.items()]
    del merged

    # Merge same-region rules, as this is cheaper.
    # Also convert boxes to hashdict()
    #
    # Reversing is such that earlier entries win in case of conflicting substitution
    # rules for the same region.
    merged = OrderedDict()
    for key, value in reversed(conditionalSubstitutions):
        key = tuple(
            sorted(
                (hashdict(cleanupBox(k)) for k in key),
                key=lambda d: tuple(sorted(d.items())),
            )
        )
        if key in merged:
            merged[key].update(value)
        else:
            merged[key] = dict(value)
    conditionalSubstitutions = list(reversed(merged.items()))
    del merged

    # Overlay
    #
    # Rank is the bit-set of the index of all contributing layers.
    initMapInit = ((hashdict(), 0),)  # Initializer representing the entire space
    boxMap = OrderedDict(initMapInit)  # Map from Box to Rank
    for i, (currRegion, _) in enumerate(conditionalSubstitutions):
        newMap = OrderedDict(initMapInit)
        currRank = 1 << i
        for box, rank in boxMap.items():
            for currBox in currRegion:
                intersection, remainder = overlayBox(currBox, box)
                if intersection is not None:
                    intersection = hashdict(intersection)
                    newMap[intersection] = newMap.get(intersection, 0) | rank | currRank
                if remainder is not None:
                    remainder = hashdict(remainder)
                    newMap[remainder] = newMap.get(remainder, 0) | rank
        boxMap = newMap

    # Generate output
    items = []
    for box, rank in sorted(
        boxMap.items(), key=(lambda BoxAndRank: -bit_count(BoxAndRank[1]))
    ):
        # Skip any box that doesn't have any substitution.
        if rank == 0:
            continue
        substsList = []
        i = 0
        while rank:
            if rank & 1:
                substsList.append(conditionalSubstitutions[i][1])
            rank >>= 1
            i += 1
        items.append((dict(box), substsList))
    return items


#
# Terminology:
#
# A 'Box' is a dict representing an orthogonal "rectangular" bit of N-dimensional space.
# The keys in the dict are axis tags, the values are (minValue, maxValue) tuples.
# Missing dimensions (keys) are substituted by the default min and max values
# from the corresponding axes.
#


def overlayBox(top, bot):
    """Overlays ``top`` box on top of ``bot`` box.

    Returns two items:

    * Box for intersection of ``top`` and ``bot``, or None if they don't intersect.
    * Box for remainder of ``bot``.  Remainder box might not be exact (since the
      remainder might not be a simple box), but is inclusive of the exact
      remainder.
    """

    # Intersection
    intersection = {}
    intersection.update(top)
    intersection.update(bot)
    for axisTag in set(top) & set(bot):
        min1, max1 = top[axisTag]
        min2, max2 = bot[axisTag]
        minimum = max(min1, min2)
        maximum = min(max1, max2)
        if not minimum < maximum:
            return None, bot  # Do not intersect
        intersection[axisTag] = minimum, maximum

    # Remainder
    #
    # Remainder is empty if bot's each axis range lies within that of intersection.
    #
    # Remainder is shrank if bot's each, except for exactly one, axis range lies
    # within that of intersection, and that one axis, it extrudes out of the
    # intersection only on one side.
    #
    # Bot is returned in full as remainder otherwise, as true remainder is not
    # representable as a single box.

    remainder = dict(bot)
    extruding = False
    fullyInside = True
    for axisTag in top:
        if axisTag in bot:
            continue
        extruding = True
        fullyInside = False
        break
    for axisTag in bot:
        if axisTag not in top:
            continue  # Axis range lies fully within
        min1, max1 = intersection[axisTag]
        min2, max2 = bot[axisTag]
        if min1 <= min2 and max2 <= max1:
            continue  # Axis range lies fully within

        # Bot's range doesn't fully lie within that of top's for this axis.
        # We know they intersect, so it cannot lie fully without either; so they
        # overlap.

        # If we have had an overlapping axis before, remainder is not
        # representable as a box, so return full bottom and go home.
        if extruding:
            return intersection, bot
        extruding = True
        fullyInside = False

        # Otherwise, cut remainder on this axis and continue.
        if min1 <= min2:
            # Right side survives.
            minimum = max(max1, min2)
            maximum = max2
        elif max2 <= max1:
            # Left side survives.
            minimum = min2
            maximum = min(min1, max2)
        else:
            # Remainder leaks out from both sides.  Can't cut either.
            return intersection, bot

        remainder[axisTag] = minimum, maximum

    if fullyInside:
        # bot is fully within intersection.  Remainder is empty.
        return intersection, None

    return intersection, remainder


def cleanupBox(box):
    """Return a sparse copy of `box`, without redundant (default) values.

    >>> cleanupBox({})
    {}
    >>> cleanupBox({'wdth': (0.0, 1.0)})
    {'wdth': (0.0, 1.0)}
    >>> cleanupBox({'wdth': (-1.0, 1.0)})
    {}

    """
    return {tag: limit for tag, limit in box.items() if limit != (-1.0, 1.0)}


#
# Low level implementation
#


def addFeatureVariationsRaw(font, table, conditionalSubstitutions, featureTag="rvrn"):
    """Low level implementation of addFeatureVariations that directly
    models the possibilities of the FeatureVariations table."""

    featureTags = [featureTag] if isinstance(featureTag, str) else sorted(featureTag)
    processLast = "rvrn" not in featureTags or len(featureTags) > 1

    #
    # if a <featureTag> feature is not present:
    #     make empty <featureTag> feature
    #     sort features, get <featureTag> feature index
    #     add <featureTag> feature to all scripts
    # if a <featureTag> feature is present:
    #     reuse <featureTag> feature index
    # make lookups
    # add feature variations
    #
    if table.Version < 0x00010001:
        table.Version = 0x00010001  # allow table.FeatureVariations

    varFeatureIndices = set()

    existingTags = {
        feature.FeatureTag
        for feature in table.FeatureList.FeatureRecord
        if feature.FeatureTag in featureTags
    }

    newTags = set(featureTags) - existingTags
    if newTags:
        varFeatures = []
        for featureTag in sorted(newTags):
            varFeature = buildFeatureRecord(featureTag, [])
            table.FeatureList.FeatureRecord.append(varFeature)
            varFeatures.append(varFeature)
        table.FeatureList.FeatureCount = len(table.FeatureList.FeatureRecord)

        sortFeatureList(table)

        for varFeature in varFeatures:
            varFeatureIndex = table.FeatureList.FeatureRecord.index(varFeature)

            for scriptRecord in table.ScriptList.ScriptRecord:
                if scriptRecord.Script.DefaultLangSys is None:
                    # We need to have a default LangSys to attach variations to.
                    langSys = ot.LangSys()
                    langSys.LookupOrder = None
                    langSys.ReqFeatureIndex = 0xFFFF
                    langSys.FeatureIndex = []
                    langSys.FeatureCount = 0
                    scriptRecord.Script.DefaultLangSys = langSys
                langSystems = [lsr.LangSys for lsr in scriptRecord.Script.LangSysRecord]
                for langSys in [scriptRecord.Script.DefaultLangSys] + langSystems:
                    langSys.FeatureIndex.append(varFeatureIndex)
                    langSys.FeatureCount = len(langSys.FeatureIndex)
            varFeatureIndices.add(varFeatureIndex)

    if existingTags:
        # indices may have changed if we inserted new features and sorted feature list
        # so we must do this after the above
        varFeatureIndices.update(
            index
            for index, feature in enumerate(table.FeatureList.FeatureRecord)
            if feature.FeatureTag in existingTags
        )

    axisIndices = {
        axis.axisTag: axisIndex for axisIndex, axis in enumerate(font["fvar"].axes)
    }

    hasFeatureVariations = (
        hasattr(table, "FeatureVariations") and table.FeatureVariations is not None
    )

    featureVariationRecords = []
    for conditionSet, lookupIndices in conditionalSubstitutions:
        conditionTable = []
        for axisTag, (minValue, maxValue) in sorted(conditionSet.items()):
            if minValue > maxValue:
                raise VarLibValidationError(
                    "A condition set has a minimum value above the maximum value."
                )
            ct = buildConditionTable(axisIndices[axisTag], minValue, maxValue)
            conditionTable.append(ct)
        records = []
        for varFeatureIndex in sorted(varFeatureIndices):
            existingLookupIndices = table.FeatureList.FeatureRecord[
                varFeatureIndex
            ].Feature.LookupListIndex
            combinedLookupIndices = (
                existingLookupIndices + lookupIndices
                if processLast
                else lookupIndices + existingLookupIndices
            )

            records.append(
                buildFeatureTableSubstitutionRecord(
                    varFeatureIndex, combinedLookupIndices
                )
            )
        if hasFeatureVariations and (
            fvr := findFeatureVariationRecord(table.FeatureVariations, conditionTable)
        ):
            fvr.FeatureTableSubstitution.SubstitutionRecord.extend(records)
            fvr.FeatureTableSubstitution.SubstitutionCount = len(
                fvr.FeatureTableSubstitution.SubstitutionRecord
            )
        else:
            featureVariationRecords.append(
                buildFeatureVariationRecord(conditionTable, records)
            )

    if hasFeatureVariations:
        if table.FeatureVariations.Version != 0x00010000:
            raise VarLibError(
                "Unsupported FeatureVariations table version: "
                f"0x{table.FeatureVariations.Version:08x} (expected 0x00010000)."
            )
        table.FeatureVariations.FeatureVariationRecord.extend(featureVariationRecords)
        table.FeatureVariations.FeatureVariationCount = len(
            table.FeatureVariations.FeatureVariationRecord
        )
    else:
        table.FeatureVariations = buildFeatureVariations(featureVariationRecords)


#
# Building GSUB/FeatureVariations internals
#


def buildGSUB():
    """Build a GSUB table from scratch."""
    fontTable = newTable("GSUB")
    gsub = fontTable.table = ot.GSUB()
    gsub.Version = 0x00010001  # allow gsub.FeatureVariations

    gsub.ScriptList = ot.ScriptList()
    gsub.ScriptList.ScriptRecord = []
    gsub.FeatureList = ot.FeatureList()
    gsub.FeatureList.FeatureRecord = []
    gsub.LookupList = ot.LookupList()
    gsub.LookupList.Lookup = []

    srec = ot.ScriptRecord()
    srec.ScriptTag = "DFLT"
    srec.Script = ot.Script()
    srec.Script.DefaultLangSys = None
    srec.Script.LangSysRecord = []
    srec.Script.LangSysCount = 0

    langrec = ot.LangSysRecord()
    langrec.LangSys = ot.LangSys()
    langrec.LangSys.ReqFeatureIndex = 0xFFFF
    langrec.LangSys.FeatureIndex = []
    srec.Script.DefaultLangSys = langrec.LangSys

    gsub.ScriptList.ScriptRecord.append(srec)
    gsub.ScriptList.ScriptCount = 1
    gsub.FeatureVariations = None

    return fontTable


def makeSubstitutionsHashable(conditionalSubstitutions):
    """Turn all the substitution dictionaries in sorted tuples of tuples so
    they are hashable, to detect duplicates so we don't write out redundant
    data."""
    allSubstitutions = set()
    condSubst = []
    for conditionSet, substitutionMaps in conditionalSubstitutions:
        substitutions = []
        for substitutionMap in substitutionMaps:
            subst = tuple(sorted(substitutionMap.items()))
            substitutions.append(subst)
            allSubstitutions.add(subst)
        condSubst.append((conditionSet, substitutions))
    return condSubst, sorted(allSubstitutions)


class ShifterVisitor(TTVisitor):
    def __init__(self, shift):
        self.shift = shift


@ShifterVisitor.register_attr(ot.Feature, "LookupListIndex")  # GSUB/GPOS
def visit(visitor, obj, attr, value):
    shift = visitor.shift
    value = [l + shift for l in value]
    setattr(obj, attr, value)


@ShifterVisitor.register_attr(
    (ot.SubstLookupRecord, ot.PosLookupRecord), "LookupListIndex"
)
def visit(visitor, obj, attr, value):
    setattr(obj, attr, visitor.shift + value)


def buildSubstitutionLookups(gsub, allSubstitutions, processLast=False):
    """Build the lookups for the glyph substitutions, return a dict mapping
    the substitution to lookup indices."""

    # Insert lookups at the beginning of the lookup vector
    # https://github.com/googlefonts/fontmake/issues/950

    firstIndex = len(gsub.LookupList.Lookup) if processLast else 0
    lookupMap = {}
    for i, substitutionMap in enumerate(allSubstitutions):
        lookupMap[substitutionMap] = firstIndex + i

    if not processLast:
        # Shift all lookup indices in gsub by len(allSubstitutions)
        shift = len(allSubstitutions)
        visitor = ShifterVisitor(shift)
        visitor.visit(gsub.FeatureList.FeatureRecord)
        visitor.visit(gsub.LookupList.Lookup)

    for i, subst in enumerate(allSubstitutions):
        substMap = dict(subst)
        lookup = buildLookup([buildSingleSubstSubtable(substMap)])
        if processLast:
            gsub.LookupList.Lookup.append(lookup)
        else:
            gsub.LookupList.Lookup.insert(i, lookup)
        assert gsub.LookupList.Lookup[lookupMap[subst]] is lookup
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
    return lookupMap


def buildFeatureVariations(featureVariationRecords):
    """Build the FeatureVariations subtable."""
    fv = ot.FeatureVariations()
    fv.Version = 0x00010000
    fv.FeatureVariationRecord = featureVariationRecords
    fv.FeatureVariationCount = len(featureVariationRecords)
    return fv


def buildFeatureRecord(featureTag, lookupListIndices):
    """Build a FeatureRecord."""
    fr = ot.FeatureRecord()
    fr.FeatureTag = featureTag
    fr.Feature = ot.Feature()
    fr.Feature.LookupListIndex = lookupListIndices
    fr.Feature.populateDefaults()
    return fr


def buildFeatureVariationRecord(conditionTable, substitutionRecords):
    """Build a FeatureVariationRecord."""
    fvr = ot.FeatureVariationRecord()
    if len(conditionTable) != 0:
        fvr.ConditionSet = ot.ConditionSet()
        fvr.ConditionSet.ConditionTable = conditionTable
        fvr.ConditionSet.ConditionCount = len(conditionTable)
    else:
        fvr.ConditionSet = None
    fvr.FeatureTableSubstitution = ot.FeatureTableSubstitution()
    fvr.FeatureTableSubstitution.Version = 0x00010000
    fvr.FeatureTableSubstitution.SubstitutionRecord = substitutionRecords
    fvr.FeatureTableSubstitution.SubstitutionCount = len(substitutionRecords)
    return fvr


def buildFeatureTableSubstitutionRecord(featureIndex, lookupListIndices):
    """Build a FeatureTableSubstitutionRecord."""
    ftsr = ot.FeatureTableSubstitutionRecord()
    ftsr.FeatureIndex = featureIndex
    ftsr.Feature = ot.Feature()
    ftsr.Feature.LookupListIndex = lookupListIndices
    ftsr.Feature.LookupCount = len(lookupListIndices)
    return ftsr


def buildConditionTable(axisIndex, filterRangeMinValue, filterRangeMaxValue):
    """Build a ConditionTable."""
    ct = ot.ConditionTable()
    ct.Format = 1
    ct.AxisIndex = axisIndex
    ct.FilterRangeMinValue = filterRangeMinValue
    ct.FilterRangeMaxValue = filterRangeMaxValue
    return ct


def findFeatureVariationRecord(featureVariations, conditionTable):
    """Find a FeatureVariationRecord that has the same conditionTable."""
    if featureVariations.Version != 0x00010000:
        raise VarLibError(
            "Unsupported FeatureVariations table version: "
            f"0x{featureVariations.Version:08x} (expected 0x00010000)."
        )

    for fvr in featureVariations.FeatureVariationRecord:
        if conditionTable == fvr.ConditionSet.ConditionTable:
            return fvr

    return None


def sortFeatureList(table):
    """Sort the feature list by feature tag, and remap the feature indices
    elsewhere. This is needed after the feature list has been modified.
    """
    # decorate, sort, undecorate, because we need to make an index remapping table
    tagIndexFea = [
        (fea.FeatureTag, index, fea)
        for index, fea in enumerate(table.FeatureList.FeatureRecord)
    ]
    tagIndexFea.sort()
    table.FeatureList.FeatureRecord = [fea for tag, index, fea in tagIndexFea]
    featureRemap = dict(
        zip([index for tag, index, fea in tagIndexFea], range(len(tagIndexFea)))
    )

    # Remap the feature indices
    remapFeatures(table, featureRemap)


def remapFeatures(table, featureRemap):
    """Go through the scripts list, and remap feature indices."""
    for scriptIndex, script in enumerate(table.ScriptList.ScriptRecord):
        defaultLangSys = script.Script.DefaultLangSys
        if defaultLangSys is not None:
            _remapLangSys(defaultLangSys, featureRemap)
        for langSysRecordIndex, langSysRec in enumerate(script.Script.LangSysRecord):
            langSys = langSysRec.LangSys
            _remapLangSys(langSys, featureRemap)

    if hasattr(table, "FeatureVariations") and table.FeatureVariations is not None:
        for fvr in table.FeatureVariations.FeatureVariationRecord:
            for ftsr in fvr.FeatureTableSubstitution.SubstitutionRecord:
                ftsr.FeatureIndex = featureRemap[ftsr.FeatureIndex]


def _remapLangSys(langSys, featureRemap):
    if langSys.ReqFeatureIndex != 0xFFFF:
        langSys.ReqFeatureIndex = featureRemap[langSys.ReqFeatureIndex]
    langSys.FeatureIndex = [featureRemap[index] for index in langSys.FeatureIndex]


if __name__ == "__main__":
    import doctest, sys

    sys.exit(doctest.testmod().failed)
