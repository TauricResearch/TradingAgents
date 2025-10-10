# Copyright 2013 Google, Inc. All Rights Reserved.
#
# Google Author(s): Behdad Esfahbod, Roozbeh Pournader

from fontTools.merge.unicode import is_Default_Ignorable
from fontTools.pens.recordingPen import DecomposingRecordingPen
import logging


log = logging.getLogger("fontTools.merge")


def computeMegaGlyphOrder(merger, glyphOrders):
    """Modifies passed-in glyphOrders to reflect new glyph names.
    Stores merger.glyphOrder."""
    megaOrder = {}
    for glyphOrder in glyphOrders:
        for i, glyphName in enumerate(glyphOrder):
            if glyphName in megaOrder:
                n = megaOrder[glyphName]
                while (glyphName + "." + repr(n)) in megaOrder:
                    n += 1
                megaOrder[glyphName] = n
                glyphName += "." + repr(n)
                glyphOrder[i] = glyphName
            megaOrder[glyphName] = 1
    merger.glyphOrder = megaOrder = list(megaOrder.keys())


def _glyphsAreSame(
    glyphSet1,
    glyphSet2,
    glyph1,
    glyph2,
    advanceTolerance=0.05,
    advanceToleranceEmpty=0.20,
):
    pen1 = DecomposingRecordingPen(glyphSet1)
    pen2 = DecomposingRecordingPen(glyphSet2)
    g1 = glyphSet1[glyph1]
    g2 = glyphSet2[glyph2]
    g1.draw(pen1)
    g2.draw(pen2)
    if pen1.value != pen2.value:
        return False
    # Allow more width tolerance for glyphs with no ink
    tolerance = advanceTolerance if pen1.value else advanceToleranceEmpty
    # TODO Warn if advances not the same but within tolerance.
    if abs(g1.width - g2.width) > g1.width * tolerance:
        return False
    if hasattr(g1, "height") and g1.height is not None:
        if abs(g1.height - g2.height) > g1.height * tolerance:
            return False
    return True


def computeMegaUvs(merger, uvsTables):
    """Returns merged UVS subtable (cmap format=14)."""
    uvsDict = {}
    cmap = merger.cmap
    for table in uvsTables:
        for variationSelector, uvsMapping in table.uvsDict.items():
            if variationSelector not in uvsDict:
                uvsDict[variationSelector] = {}
            for unicodeValue, glyphName in uvsMapping:
                if cmap.get(unicodeValue) == glyphName:
                    # this is a default variation
                    glyphName = None
                    # prefer previous glyph id if both fonts defined UVS
                if unicodeValue not in uvsDict[variationSelector]:
                    uvsDict[variationSelector][unicodeValue] = glyphName

    for variationSelector in uvsDict:
        uvsDict[variationSelector] = [*uvsDict[variationSelector].items()]

    return uvsDict


# Valid (format, platformID, platEncID) triplets for cmap subtables containing
# Unicode BMP-only and Unicode Full Repertoire semantics.
# Cf. OpenType spec for "Platform specific encodings":
# https://docs.microsoft.com/en-us/typography/opentype/spec/name
class _CmapUnicodePlatEncodings:
    BMP = {(4, 3, 1), (4, 0, 3), (4, 0, 4), (4, 0, 6)}
    FullRepertoire = {(12, 3, 10), (12, 0, 4), (12, 0, 6)}
    UVS = {(14, 0, 5)}


def computeMegaCmap(merger, cmapTables):
    """Sets merger.cmap and merger.uvsDict."""

    # TODO Handle format=14.
    # Only merge format 4 and 12 Unicode subtables, ignores all other subtables
    # If there is a format 12 table for a font, ignore the format 4 table of it
    chosenCmapTables = []
    chosenUvsTables = []
    for fontIdx, table in enumerate(cmapTables):
        format4 = None
        format12 = None
        format14 = None
        for subtable in table.tables:
            properties = (subtable.format, subtable.platformID, subtable.platEncID)
            if properties in _CmapUnicodePlatEncodings.BMP:
                format4 = subtable
            elif properties in _CmapUnicodePlatEncodings.FullRepertoire:
                format12 = subtable
            elif properties in _CmapUnicodePlatEncodings.UVS:
                format14 = subtable
            else:
                log.warning(
                    "Dropped cmap subtable from font '%s':\t"
                    "format %2s, platformID %2s, platEncID %2s",
                    fontIdx,
                    subtable.format,
                    subtable.platformID,
                    subtable.platEncID,
                )
        if format12 is not None:
            chosenCmapTables.append((format12, fontIdx))
        elif format4 is not None:
            chosenCmapTables.append((format4, fontIdx))

        if format14 is not None:
            chosenUvsTables.append(format14)

    # Build the unicode mapping
    merger.cmap = cmap = {}
    fontIndexForGlyph = {}
    glyphSets = [None for f in merger.fonts] if hasattr(merger, "fonts") else None

    for table, fontIdx in chosenCmapTables:
        # handle duplicates
        for uni, gid in table.cmap.items():
            oldgid = cmap.get(uni, None)
            if oldgid is None:
                cmap[uni] = gid
                fontIndexForGlyph[gid] = fontIdx
            elif is_Default_Ignorable(uni) or uni in (0x25CC,):  # U+25CC DOTTED CIRCLE
                continue
            elif oldgid != gid:
                # Char previously mapped to oldgid, now to gid.
                # Record, to fix up in GSUB 'locl' later.
                if merger.duplicateGlyphsPerFont[fontIdx].get(oldgid) is None:
                    if glyphSets is not None:
                        oldFontIdx = fontIndexForGlyph[oldgid]
                        for idx in (fontIdx, oldFontIdx):
                            if glyphSets[idx] is None:
                                glyphSets[idx] = merger.fonts[idx].getGlyphSet()
                        # if _glyphsAreSame(glyphSets[oldFontIdx], glyphSets[fontIdx], oldgid, gid):
                        # 	continue
                    merger.duplicateGlyphsPerFont[fontIdx][oldgid] = gid
                elif merger.duplicateGlyphsPerFont[fontIdx][oldgid] != gid:
                    # Char previously mapped to oldgid but oldgid is already remapped to a different
                    # gid, because of another Unicode character.
                    # TODO: Try harder to do something about these.
                    log.warning(
                        "Dropped mapping from codepoint %#06X to glyphId '%s'", uni, gid
                    )

    merger.uvsDict = computeMegaUvs(merger, chosenUvsTables)


def renameCFFCharStrings(merger, glyphOrder, cffTable):
    """Rename topDictIndex charStrings based on glyphOrder."""
    td = cffTable.cff.topDictIndex[0]

    charStrings = {}
    for i, v in enumerate(td.CharStrings.charStrings.values()):
        glyphName = glyphOrder[i]
        charStrings[glyphName] = v
    td.CharStrings.charStrings = charStrings

    td.charset = list(glyphOrder)
