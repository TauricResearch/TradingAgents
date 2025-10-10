# Copyright 2013 Google, Inc. All Rights Reserved.
#
# Google Author(s): Behdad Esfahbod, Roozbeh Pournader

from fontTools import ttLib, cffLib
from fontTools.misc.psCharStrings import T2WidthExtractor
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from fontTools.merge.base import add_method, mergeObjects
from fontTools.merge.cmap import computeMegaCmap
from fontTools.merge.util import *
import logging


log = logging.getLogger("fontTools.merge")


ttLib.getTableClass("maxp").mergeMap = {
    "*": max,
    "tableTag": equal,
    "tableVersion": equal,
    "numGlyphs": sum,
    "maxStorage": first,
    "maxFunctionDefs": first,
    "maxInstructionDefs": first,
    # TODO When we correctly merge hinting data, update these values:
    # maxFunctionDefs, maxInstructionDefs, maxSizeOfInstructions
}

headFlagsMergeBitMap = {
    "size": 16,
    "*": bitwise_or,
    1: bitwise_and,  # Baseline at y = 0
    2: bitwise_and,  # lsb at x = 0
    3: bitwise_and,  # Force ppem to integer values. FIXME?
    5: bitwise_and,  # Font is vertical
    6: lambda bit: 0,  # Always set to zero
    11: bitwise_and,  # Font data is 'lossless'
    13: bitwise_and,  # Optimized for ClearType
    14: bitwise_and,  # Last resort font. FIXME? equal or first may be better
    15: lambda bit: 0,  # Always set to zero
}

ttLib.getTableClass("head").mergeMap = {
    "tableTag": equal,
    "tableVersion": max,
    "fontRevision": max,
    "checkSumAdjustment": lambda lst: 0,  # We need *something* here
    "magicNumber": equal,
    "flags": mergeBits(headFlagsMergeBitMap),
    "unitsPerEm": equal,
    "created": current_time,
    "modified": current_time,
    "xMin": min,
    "yMin": min,
    "xMax": max,
    "yMax": max,
    "macStyle": first,
    "lowestRecPPEM": max,
    "fontDirectionHint": lambda lst: 2,
    "indexToLocFormat": first,
    "glyphDataFormat": equal,
}

ttLib.getTableClass("hhea").mergeMap = {
    "*": equal,
    "tableTag": equal,
    "tableVersion": max,
    "ascent": max,
    "descent": min,
    "lineGap": max,
    "advanceWidthMax": max,
    "minLeftSideBearing": min,
    "minRightSideBearing": min,
    "xMaxExtent": max,
    "caretSlopeRise": first,
    "caretSlopeRun": first,
    "caretOffset": first,
    "numberOfHMetrics": recalculate,
}

ttLib.getTableClass("vhea").mergeMap = {
    "*": equal,
    "tableTag": equal,
    "tableVersion": max,
    "ascent": max,
    "descent": min,
    "lineGap": max,
    "advanceHeightMax": max,
    "minTopSideBearing": min,
    "minBottomSideBearing": min,
    "yMaxExtent": max,
    "caretSlopeRise": first,
    "caretSlopeRun": first,
    "caretOffset": first,
    "numberOfVMetrics": recalculate,
}

os2FsTypeMergeBitMap = {
    "size": 16,
    "*": lambda bit: 0,
    1: bitwise_or,  # no embedding permitted
    2: bitwise_and,  # allow previewing and printing documents
    3: bitwise_and,  # allow editing documents
    8: bitwise_or,  # no subsetting permitted
    9: bitwise_or,  # no embedding of outlines permitted
}


def mergeOs2FsType(lst):
    lst = list(lst)
    if all(item == 0 for item in lst):
        return 0

    # Compute least restrictive logic for each fsType value
    for i in range(len(lst)):
        # unset bit 1 (no embedding permitted) if either bit 2 or 3 is set
        if lst[i] & 0x000C:
            lst[i] &= ~0x0002
        # set bit 2 (allow previewing) if bit 3 is set (allow editing)
        elif lst[i] & 0x0008:
            lst[i] |= 0x0004
        # set bits 2 and 3 if everything is allowed
        elif lst[i] == 0:
            lst[i] = 0x000C

    fsType = mergeBits(os2FsTypeMergeBitMap)(lst)
    # unset bits 2 and 3 if bit 1 is set (some font is "no embedding")
    if fsType & 0x0002:
        fsType &= ~0x000C
    return fsType


ttLib.getTableClass("OS/2").mergeMap = {
    "*": first,
    "tableTag": equal,
    "version": max,
    "xAvgCharWidth": first,  # Will be recalculated at the end on the merged font
    "fsType": mergeOs2FsType,  # Will be overwritten
    "panose": first,  # FIXME: should really be the first Latin font
    "ulUnicodeRange1": bitwise_or,
    "ulUnicodeRange2": bitwise_or,
    "ulUnicodeRange3": bitwise_or,
    "ulUnicodeRange4": bitwise_or,
    "fsFirstCharIndex": min,
    "fsLastCharIndex": max,
    "sTypoAscender": max,
    "sTypoDescender": min,
    "sTypoLineGap": max,
    "usWinAscent": max,
    "usWinDescent": max,
    # Version 1
    "ulCodePageRange1": onlyExisting(bitwise_or),
    "ulCodePageRange2": onlyExisting(bitwise_or),
    # Version 2, 3, 4
    "sxHeight": onlyExisting(max),
    "sCapHeight": onlyExisting(max),
    "usDefaultChar": onlyExisting(first),
    "usBreakChar": onlyExisting(first),
    "usMaxContext": onlyExisting(max),
    # version 5
    "usLowerOpticalPointSize": onlyExisting(min),
    "usUpperOpticalPointSize": onlyExisting(max),
}


@add_method(ttLib.getTableClass("OS/2"))
def merge(self, m, tables):
    DefaultTable.merge(self, m, tables)
    if self.version < 2:
        # bits 8 and 9 are reserved and should be set to zero
        self.fsType &= ~0x0300
    if self.version >= 3:
        # Only one of bits 1, 2, and 3 may be set. We already take
        # care of bit 1 implications in mergeOs2FsType. So unset
        # bit 2 if bit 3 is already set.
        if self.fsType & 0x0008:
            self.fsType &= ~0x0004
    return self


ttLib.getTableClass("post").mergeMap = {
    "*": first,
    "tableTag": equal,
    "formatType": max,
    "isFixedPitch": min,
    "minMemType42": max,
    "maxMemType42": lambda lst: 0,
    "minMemType1": max,
    "maxMemType1": lambda lst: 0,
    "mapping": onlyExisting(sumDicts),
    "extraNames": lambda lst: [],
}

ttLib.getTableClass("vmtx").mergeMap = ttLib.getTableClass("hmtx").mergeMap = {
    "tableTag": equal,
    "metrics": sumDicts,
}

ttLib.getTableClass("name").mergeMap = {
    "tableTag": equal,
    "names": first,  # FIXME? Does mixing name records make sense?
}

ttLib.getTableClass("loca").mergeMap = {
    "*": recalculate,
    "tableTag": equal,
}

ttLib.getTableClass("glyf").mergeMap = {
    "tableTag": equal,
    "glyphs": sumDicts,
    "glyphOrder": sumLists,
    "_reverseGlyphOrder": recalculate,
    "axisTags": equal,
}


@add_method(ttLib.getTableClass("glyf"))
def merge(self, m, tables):
    for i, table in enumerate(tables):
        for g in table.glyphs.values():
            if i:
                # Drop hints for all but first font, since
                # we don't map functions / CVT values.
                g.removeHinting()
            # Expand composite glyphs to load their
            # composite glyph names.
            if g.isComposite():
                g.expand(table)
    return DefaultTable.merge(self, m, tables)


ttLib.getTableClass("prep").mergeMap = lambda self, lst: first(lst)
ttLib.getTableClass("fpgm").mergeMap = lambda self, lst: first(lst)
ttLib.getTableClass("cvt ").mergeMap = lambda self, lst: first(lst)
ttLib.getTableClass("gasp").mergeMap = lambda self, lst: first(
    lst
)  # FIXME? Appears irreconcilable


@add_method(ttLib.getTableClass("CFF "))
def merge(self, m, tables):
    if any(hasattr(table.cff[0], "FDSelect") for table in tables):
        raise NotImplementedError("Merging CID-keyed CFF tables is not supported yet")

    for table in tables:
        table.cff.desubroutinize()

    newcff = tables[0]
    newfont = newcff.cff[0]
    private = newfont.Private
    newDefaultWidthX, newNominalWidthX = private.defaultWidthX, private.nominalWidthX
    storedNamesStrings = []
    glyphOrderStrings = []
    glyphOrder = set(newfont.getGlyphOrder())

    for name in newfont.strings.strings:
        if name not in glyphOrder:
            storedNamesStrings.append(name)
        else:
            glyphOrderStrings.append(name)

    chrset = list(newfont.charset)
    newcs = newfont.CharStrings
    log.debug("FONT 0 CharStrings: %d.", len(newcs))

    for i, table in enumerate(tables[1:], start=1):
        font = table.cff[0]
        defaultWidthX, nominalWidthX = (
            font.Private.defaultWidthX,
            font.Private.nominalWidthX,
        )
        widthsDiffer = (
            defaultWidthX != newDefaultWidthX or nominalWidthX != newNominalWidthX
        )
        font.Private = private
        fontGlyphOrder = set(font.getGlyphOrder())
        for name in font.strings.strings:
            if name in fontGlyphOrder:
                glyphOrderStrings.append(name)
        cs = font.CharStrings
        gs = table.cff.GlobalSubrs
        log.debug("Font %d CharStrings: %d.", i, len(cs))
        chrset.extend(font.charset)
        if newcs.charStringsAreIndexed:
            for i, name in enumerate(cs.charStrings, start=len(newcs)):
                newcs.charStrings[name] = i
                newcs.charStringsIndex.items.append(None)
        for name in cs.charStrings:
            if widthsDiffer:
                c = cs[name]
                defaultWidthXToken = object()
                extractor = T2WidthExtractor([], [], nominalWidthX, defaultWidthXToken)
                extractor.execute(c)
                width = extractor.width
                if width is not defaultWidthXToken:
                    # The following will be wrong if the width is added
                    # by a subroutine. Ouch!
                    c.program.pop(0)
                else:
                    width = defaultWidthX
                if width != newDefaultWidthX:
                    c.program.insert(0, width - newNominalWidthX)
            newcs[name] = cs[name]

    newfont.charset = chrset
    newfont.numGlyphs = len(chrset)
    newfont.strings.strings = glyphOrderStrings + storedNamesStrings

    return newcff


@add_method(ttLib.getTableClass("cmap"))
def merge(self, m, tables):
    if not hasattr(m, "cmap"):
        computeMegaCmap(m, tables)
    cmap = m.cmap

    cmapBmpOnly = {uni: gid for uni, gid in cmap.items() if uni <= 0xFFFF}
    self.tables = []
    module = ttLib.getTableModule("cmap")
    if len(cmapBmpOnly) != len(cmap):
        # format-12 required.
        cmapTable = module.cmap_classes[12](12)
        cmapTable.platformID = 3
        cmapTable.platEncID = 10
        cmapTable.language = 0
        cmapTable.cmap = cmap
        self.tables.append(cmapTable)
    # always create format-4
    cmapTable = module.cmap_classes[4](4)
    cmapTable.platformID = 3
    cmapTable.platEncID = 1
    cmapTable.language = 0
    cmapTable.cmap = cmapBmpOnly
    # ordered by platform then encoding
    self.tables.insert(0, cmapTable)

    uvsDict = m.uvsDict
    if uvsDict:
        # format-14
        uvsTable = module.cmap_classes[14](14)
        uvsTable.platformID = 0
        uvsTable.platEncID = 5
        uvsTable.language = 0
        uvsTable.cmap = {}
        uvsTable.uvsDict = uvsDict
        # ordered by platform then encoding
        self.tables.insert(0, uvsTable)
    self.tableVersion = 0
    self.numSubTables = len(self.tables)
    return self
