__all__ = ["FontBuilder"]

"""
This module is *experimental*, meaning it still may evolve and change.

The `FontBuilder` class is a convenient helper to construct working TTF or
OTF fonts from scratch.

Note that the various setup methods cannot be called in arbitrary order,
due to various interdependencies between OpenType tables. Here is an order
that works:

    fb = FontBuilder(...)
    fb.setupGlyphOrder(...)
    fb.setupCharacterMap(...)
    fb.setupGlyf(...) --or-- fb.setupCFF(...)
    fb.setupHorizontalMetrics(...)
    fb.setupHorizontalHeader()
    fb.setupNameTable(...)
    fb.setupOS2()
    fb.addOpenTypeFeatures(...)
    fb.setupPost()
    fb.save(...)

Here is how to build a minimal TTF:

```python
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


def drawTestGlyph(pen):
    pen.moveTo((100, 100))
    pen.lineTo((100, 1000))
    pen.qCurveTo((200, 900), (400, 900), (500, 1000))
    pen.lineTo((500, 100))
    pen.closePath()


fb = FontBuilder(1024, isTTF=True)
fb.setupGlyphOrder([".notdef", ".null", "space", "A", "a"])
fb.setupCharacterMap({32: "space", 65: "A", 97: "a"})
advanceWidths = {".notdef": 600, "space": 500, "A": 600, "a": 600, ".null": 0}

familyName = "HelloTestFont"
styleName = "TotallyNormal"
version = "0.1"

nameStrings = dict(
    familyName=dict(en=familyName, nl="HalloTestFont"),
    styleName=dict(en=styleName, nl="TotaalNormaal"),
    uniqueFontIdentifier="fontBuilder: " + familyName + "." + styleName,
    fullName=familyName + "-" + styleName,
    psName=familyName + "-" + styleName,
    version="Version " + version,
)

pen = TTGlyphPen(None)
drawTestGlyph(pen)
glyph = pen.glyph()
glyphs = {".notdef": glyph, "space": glyph, "A": glyph, "a": glyph, ".null": glyph}
fb.setupGlyf(glyphs)
metrics = {}
glyphTable = fb.font["glyf"]
for gn, advanceWidth in advanceWidths.items():
    metrics[gn] = (advanceWidth, glyphTable[gn].xMin)
fb.setupHorizontalMetrics(metrics)
fb.setupHorizontalHeader(ascent=824, descent=-200)
fb.setupNameTable(nameStrings)
fb.setupOS2(sTypoAscender=824, usWinAscent=824, usWinDescent=200)
fb.setupPost()
fb.save("test.ttf")
```

And here's how to build a minimal OTF:

```python
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen


def drawTestGlyph(pen):
    pen.moveTo((100, 100))
    pen.lineTo((100, 1000))
    pen.curveTo((200, 900), (400, 900), (500, 1000))
    pen.lineTo((500, 100))
    pen.closePath()


fb = FontBuilder(1024, isTTF=False)
fb.setupGlyphOrder([".notdef", ".null", "space", "A", "a"])
fb.setupCharacterMap({32: "space", 65: "A", 97: "a"})
advanceWidths = {".notdef": 600, "space": 500, "A": 600, "a": 600, ".null": 0}

familyName = "HelloTestFont"
styleName = "TotallyNormal"
version = "0.1"

nameStrings = dict(
    familyName=dict(en=familyName, nl="HalloTestFont"),
    styleName=dict(en=styleName, nl="TotaalNormaal"),
    uniqueFontIdentifier="fontBuilder: " + familyName + "." + styleName,
    fullName=familyName + "-" + styleName,
    psName=familyName + "-" + styleName,
    version="Version " + version,
)

pen = T2CharStringPen(600, None)
drawTestGlyph(pen)
charString = pen.getCharString()
charStrings = {
    ".notdef": charString,
    "space": charString,
    "A": charString,
    "a": charString,
    ".null": charString,
}
fb.setupCFF(nameStrings["psName"], {"FullName": nameStrings["psName"]}, charStrings, {})
lsb = {gn: cs.calcBounds(None)[0] for gn, cs in charStrings.items()}
metrics = {}
for gn, advanceWidth in advanceWidths.items():
    metrics[gn] = (advanceWidth, lsb[gn])
fb.setupHorizontalMetrics(metrics)
fb.setupHorizontalHeader(ascent=824, descent=200)
fb.setupNameTable(nameStrings)
fb.setupOS2(sTypoAscender=824, usWinAscent=824, usWinDescent=200)
fb.setupPost()
fb.save("test.otf")
```
"""

from .ttLib import TTFont, newTable
from .ttLib.tables._c_m_a_p import cmap_classes
from .ttLib.tables._g_l_y_f import flagCubic
from .ttLib.tables.O_S_2f_2 import Panose
from .misc.timeTools import timestampNow
import struct
from collections import OrderedDict


_headDefaults = dict(
    tableVersion=1.0,
    fontRevision=1.0,
    checkSumAdjustment=0,
    magicNumber=0x5F0F3CF5,
    flags=0x0003,
    unitsPerEm=1000,
    created=0,
    modified=0,
    xMin=0,
    yMin=0,
    xMax=0,
    yMax=0,
    macStyle=0,
    lowestRecPPEM=3,
    fontDirectionHint=2,
    indexToLocFormat=0,
    glyphDataFormat=0,
)

_maxpDefaultsTTF = dict(
    tableVersion=0x00010000,
    numGlyphs=0,
    maxPoints=0,
    maxContours=0,
    maxCompositePoints=0,
    maxCompositeContours=0,
    maxZones=2,
    maxTwilightPoints=0,
    maxStorage=0,
    maxFunctionDefs=0,
    maxInstructionDefs=0,
    maxStackElements=0,
    maxSizeOfInstructions=0,
    maxComponentElements=0,
    maxComponentDepth=0,
)
_maxpDefaultsOTF = dict(
    tableVersion=0x00005000,
    numGlyphs=0,
)

_postDefaults = dict(
    formatType=3.0,
    italicAngle=0,
    underlinePosition=0,
    underlineThickness=0,
    isFixedPitch=0,
    minMemType42=0,
    maxMemType42=0,
    minMemType1=0,
    maxMemType1=0,
)

_hheaDefaults = dict(
    tableVersion=0x00010000,
    ascent=0,
    descent=0,
    lineGap=0,
    advanceWidthMax=0,
    minLeftSideBearing=0,
    minRightSideBearing=0,
    xMaxExtent=0,
    caretSlopeRise=1,
    caretSlopeRun=0,
    caretOffset=0,
    reserved0=0,
    reserved1=0,
    reserved2=0,
    reserved3=0,
    metricDataFormat=0,
    numberOfHMetrics=0,
)

_vheaDefaults = dict(
    tableVersion=0x00010000,
    ascent=0,
    descent=0,
    lineGap=0,
    advanceHeightMax=0,
    minTopSideBearing=0,
    minBottomSideBearing=0,
    yMaxExtent=0,
    caretSlopeRise=0,
    caretSlopeRun=0,
    reserved0=0,
    reserved1=0,
    reserved2=0,
    reserved3=0,
    reserved4=0,
    metricDataFormat=0,
    numberOfVMetrics=0,
)

_nameIDs = dict(
    copyright=0,
    familyName=1,
    styleName=2,
    uniqueFontIdentifier=3,
    fullName=4,
    version=5,
    psName=6,
    trademark=7,
    manufacturer=8,
    designer=9,
    description=10,
    vendorURL=11,
    designerURL=12,
    licenseDescription=13,
    licenseInfoURL=14,
    # reserved = 15,
    typographicFamily=16,
    typographicSubfamily=17,
    compatibleFullName=18,
    sampleText=19,
    postScriptCIDFindfontName=20,
    wwsFamilyName=21,
    wwsSubfamilyName=22,
    lightBackgroundPalette=23,
    darkBackgroundPalette=24,
    variationsPostScriptNamePrefix=25,
)

# to insert in setupNameTable doc string:
# print("\n".join(("%s (nameID %s)" % (k, v)) for k, v in sorted(_nameIDs.items(), key=lambda x: x[1])))

_panoseDefaults = Panose()

_OS2Defaults = dict(
    version=3,
    xAvgCharWidth=0,
    usWeightClass=400,
    usWidthClass=5,
    fsType=0x0004,  # default: Preview & Print embedding
    ySubscriptXSize=0,
    ySubscriptYSize=0,
    ySubscriptXOffset=0,
    ySubscriptYOffset=0,
    ySuperscriptXSize=0,
    ySuperscriptYSize=0,
    ySuperscriptXOffset=0,
    ySuperscriptYOffset=0,
    yStrikeoutSize=0,
    yStrikeoutPosition=0,
    sFamilyClass=0,
    panose=_panoseDefaults,
    ulUnicodeRange1=0,
    ulUnicodeRange2=0,
    ulUnicodeRange3=0,
    ulUnicodeRange4=0,
    achVendID="????",
    fsSelection=0,
    usFirstCharIndex=0,
    usLastCharIndex=0,
    sTypoAscender=0,
    sTypoDescender=0,
    sTypoLineGap=0,
    usWinAscent=0,
    usWinDescent=0,
    ulCodePageRange1=0,
    ulCodePageRange2=0,
    sxHeight=0,
    sCapHeight=0,
    usDefaultChar=0,  # .notdef
    usBreakChar=32,  # space
    usMaxContext=0,
    usLowerOpticalPointSize=0,
    usUpperOpticalPointSize=0,
)


class FontBuilder(object):
    def __init__(self, unitsPerEm=None, font=None, isTTF=True, glyphDataFormat=0):
        """Initialize a FontBuilder instance.

        If the `font` argument is not given, a new `TTFont` will be
        constructed, and `unitsPerEm` must be given. If `isTTF` is True,
        the font will be a glyf-based TTF; if `isTTF` is False it will be
        a CFF-based OTF.

        The `glyphDataFormat` argument corresponds to the `head` table field
        that defines the format of the TrueType `glyf` table (default=0).
        TrueType glyphs historically can only contain quadratic splines and static
        components, but there's a proposal to add support for cubic Bezier curves as well
        as variable composites/components at
        https://github.com/harfbuzz/boring-expansion-spec/blob/main/glyf1.md
        You can experiment with the new features by setting `glyphDataFormat` to 1.
        A ValueError is raised if `glyphDataFormat` is left at 0 but glyphs are added
        that contain cubic splines or varcomposites. This is to prevent accidentally
        creating fonts that are incompatible with existing TrueType implementations.

        If `font` is given, it must be a `TTFont` instance and `unitsPerEm`
        must _not_ be given. The `isTTF` and `glyphDataFormat` arguments will be ignored.
        """
        if font is None:
            self.font = TTFont(recalcTimestamp=False)
            self.isTTF = isTTF
            now = timestampNow()
            assert unitsPerEm is not None
            self.setupHead(
                unitsPerEm=unitsPerEm,
                created=now,
                modified=now,
                glyphDataFormat=glyphDataFormat,
            )
            self.setupMaxp()
        else:
            assert unitsPerEm is None
            self.font = font
            self.isTTF = "glyf" in font

    def save(self, file):
        """Save the font. The 'file' argument can be either a pathname or a
        writable file object.
        """
        self.font.save(file)

    def _initTableWithValues(self, tableTag, defaults, values):
        table = self.font[tableTag] = newTable(tableTag)
        for k, v in defaults.items():
            setattr(table, k, v)
        for k, v in values.items():
            setattr(table, k, v)
        return table

    def _updateTableWithValues(self, tableTag, values):
        table = self.font[tableTag]
        for k, v in values.items():
            setattr(table, k, v)

    def setupHead(self, **values):
        """Create a new `head` table and initialize it with default values,
        which can be overridden by keyword arguments.
        """
        self._initTableWithValues("head", _headDefaults, values)

    def updateHead(self, **values):
        """Update the head table with the fields and values passed as
        keyword arguments.
        """
        self._updateTableWithValues("head", values)

    def setupGlyphOrder(self, glyphOrder):
        """Set the glyph order for the font."""
        self.font.setGlyphOrder(glyphOrder)

    def setupCharacterMap(self, cmapping, uvs=None, allowFallback=False):
        """Build the `cmap` table for the font. The `cmapping` argument should
        be a dict mapping unicode code points as integers to glyph names.

        The `uvs` argument, when passed, must be a list of tuples, describing
        Unicode Variation Sequences. These tuples have three elements:
            (unicodeValue, variationSelector, glyphName)
        `unicodeValue` and `variationSelector` are integer code points.
        `glyphName` may be None, to indicate this is the default variation.
        Text processors will then use the cmap to find the glyph name.
        Each Unicode Variation Sequence should be an officially supported
        sequence, but this is not policed.
        """
        subTables = []
        highestUnicode = max(cmapping) if cmapping else 0
        if highestUnicode > 0xFFFF:
            cmapping_3_1 = dict((k, v) for k, v in cmapping.items() if k < 0x10000)
            subTable_3_10 = buildCmapSubTable(cmapping, 12, 3, 10)
            subTables.append(subTable_3_10)
        else:
            cmapping_3_1 = cmapping
        format = 4
        subTable_3_1 = buildCmapSubTable(cmapping_3_1, format, 3, 1)
        try:
            subTable_3_1.compile(self.font)
        except struct.error:
            # format 4 overflowed, fall back to format 12
            if not allowFallback:
                raise ValueError(
                    "cmap format 4 subtable overflowed; sort glyph order by unicode to fix."
                )
            format = 12
            subTable_3_1 = buildCmapSubTable(cmapping_3_1, format, 3, 1)
        subTables.append(subTable_3_1)
        subTable_0_3 = buildCmapSubTable(cmapping_3_1, format, 0, 3)
        subTables.append(subTable_0_3)

        if uvs is not None:
            uvsDict = {}
            for unicodeValue, variationSelector, glyphName in uvs:
                if cmapping.get(unicodeValue) == glyphName:
                    # this is a default variation
                    glyphName = None
                if variationSelector not in uvsDict:
                    uvsDict[variationSelector] = []
                uvsDict[variationSelector].append((unicodeValue, glyphName))
            uvsSubTable = buildCmapSubTable({}, 14, 0, 5)
            uvsSubTable.uvsDict = uvsDict
            subTables.append(uvsSubTable)

        self.font["cmap"] = newTable("cmap")
        self.font["cmap"].tableVersion = 0
        self.font["cmap"].tables = subTables

    def setupNameTable(self, nameStrings, windows=True, mac=True):
        """Create the `name` table for the font. The `nameStrings` argument must
        be a dict, mapping nameIDs or descriptive names for the nameIDs to name
        record values. A value is either a string, or a dict, mapping language codes
        to strings, to allow localized name table entries.

        By default, both Windows (platformID=3) and Macintosh (platformID=1) name
        records are added, unless any of `windows` or `mac` arguments is False.

        The following descriptive names are available for nameIDs:

            copyright (nameID 0)
            familyName (nameID 1)
            styleName (nameID 2)
            uniqueFontIdentifier (nameID 3)
            fullName (nameID 4)
            version (nameID 5)
            psName (nameID 6)
            trademark (nameID 7)
            manufacturer (nameID 8)
            designer (nameID 9)
            description (nameID 10)
            vendorURL (nameID 11)
            designerURL (nameID 12)
            licenseDescription (nameID 13)
            licenseInfoURL (nameID 14)
            typographicFamily (nameID 16)
            typographicSubfamily (nameID 17)
            compatibleFullName (nameID 18)
            sampleText (nameID 19)
            postScriptCIDFindfontName (nameID 20)
            wwsFamilyName (nameID 21)
            wwsSubfamilyName (nameID 22)
            lightBackgroundPalette (nameID 23)
            darkBackgroundPalette (nameID 24)
            variationsPostScriptNamePrefix (nameID 25)
        """
        nameTable = self.font["name"] = newTable("name")
        nameTable.names = []

        for nameName, nameValue in nameStrings.items():
            if isinstance(nameName, int):
                nameID = nameName
            else:
                nameID = _nameIDs[nameName]
            if isinstance(nameValue, str):
                nameValue = dict(en=nameValue)
            nameTable.addMultilingualName(
                nameValue, ttFont=self.font, nameID=nameID, windows=windows, mac=mac
            )

    def setupOS2(self, **values):
        """Create a new `OS/2` table and initialize it with default values,
        which can be overridden by keyword arguments.
        """
        self._initTableWithValues("OS/2", _OS2Defaults, values)
        if "xAvgCharWidth" not in values:
            assert (
                "hmtx" in self.font
            ), "the 'hmtx' table must be setup before the 'OS/2' table"
            self.font["OS/2"].recalcAvgCharWidth(self.font)
        if not (
            "ulUnicodeRange1" in values
            or "ulUnicodeRange2" in values
            or "ulUnicodeRange3" in values
            or "ulUnicodeRange3" in values
        ):
            assert (
                "cmap" in self.font
            ), "the 'cmap' table must be setup before the 'OS/2' table"
            self.font["OS/2"].recalcUnicodeRanges(self.font)

    def setupCFF(self, psName, fontInfo, charStringsDict, privateDict):
        from .cffLib import (
            CFFFontSet,
            TopDictIndex,
            TopDict,
            CharStrings,
            GlobalSubrsIndex,
            PrivateDict,
        )

        assert not self.isTTF
        self.font.sfntVersion = "OTTO"
        fontSet = CFFFontSet()
        fontSet.major = 1
        fontSet.minor = 0
        fontSet.otFont = self.font
        fontSet.fontNames = [psName]
        fontSet.topDictIndex = TopDictIndex()

        globalSubrs = GlobalSubrsIndex()
        fontSet.GlobalSubrs = globalSubrs
        private = PrivateDict()
        for key, value in privateDict.items():
            setattr(private, key, value)
        fdSelect = None
        fdArray = None

        topDict = TopDict()
        topDict.charset = self.font.getGlyphOrder()
        topDict.Private = private
        topDict.GlobalSubrs = fontSet.GlobalSubrs
        for key, value in fontInfo.items():
            setattr(topDict, key, value)
        if "FontMatrix" not in fontInfo:
            scale = 1 / self.font["head"].unitsPerEm
            topDict.FontMatrix = [scale, 0, 0, scale, 0, 0]

        charStrings = CharStrings(
            None, topDict.charset, globalSubrs, private, fdSelect, fdArray
        )
        for glyphName, charString in charStringsDict.items():
            charString.private = private
            charString.globalSubrs = globalSubrs
            charStrings[glyphName] = charString
        topDict.CharStrings = charStrings

        fontSet.topDictIndex.append(topDict)

        self.font["CFF "] = newTable("CFF ")
        self.font["CFF "].cff = fontSet

    def setupCFF2(self, charStringsDict, fdArrayList=None, regions=None):
        from .cffLib import (
            CFFFontSet,
            TopDictIndex,
            TopDict,
            CharStrings,
            GlobalSubrsIndex,
            PrivateDict,
            FDArrayIndex,
            FontDict,
        )

        assert not self.isTTF
        self.font.sfntVersion = "OTTO"
        fontSet = CFFFontSet()
        fontSet.major = 2
        fontSet.minor = 0

        cff2GetGlyphOrder = self.font.getGlyphOrder
        fontSet.topDictIndex = TopDictIndex(None, cff2GetGlyphOrder, None)

        globalSubrs = GlobalSubrsIndex()
        fontSet.GlobalSubrs = globalSubrs

        if fdArrayList is None:
            fdArrayList = [{}]
        fdSelect = None
        fdArray = FDArrayIndex()
        fdArray.strings = None
        fdArray.GlobalSubrs = globalSubrs
        for privateDict in fdArrayList:
            fontDict = FontDict()
            fontDict.setCFF2(True)
            private = PrivateDict()
            for key, value in privateDict.items():
                setattr(private, key, value)
            fontDict.Private = private
            fdArray.append(fontDict)

        topDict = TopDict()
        topDict.cff2GetGlyphOrder = cff2GetGlyphOrder
        topDict.FDArray = fdArray
        scale = 1 / self.font["head"].unitsPerEm
        topDict.FontMatrix = [scale, 0, 0, scale, 0, 0]

        private = fdArray[0].Private
        charStrings = CharStrings(None, None, globalSubrs, private, fdSelect, fdArray)
        for glyphName, charString in charStringsDict.items():
            charString.private = private
            charString.globalSubrs = globalSubrs
            charStrings[glyphName] = charString
        topDict.CharStrings = charStrings

        fontSet.topDictIndex.append(topDict)

        self.font["CFF2"] = newTable("CFF2")
        self.font["CFF2"].cff = fontSet

        if regions:
            self.setupCFF2Regions(regions)

    def setupCFF2Regions(self, regions):
        from .varLib.builder import buildVarRegionList, buildVarData, buildVarStore
        from .cffLib import VarStoreData

        assert "fvar" in self.font, "fvar must to be set up first"
        assert "CFF2" in self.font, "CFF2 must to be set up first"
        axisTags = [a.axisTag for a in self.font["fvar"].axes]
        varRegionList = buildVarRegionList(regions, axisTags)
        varData = buildVarData(list(range(len(regions))), None, optimize=False)
        varStore = buildVarStore(varRegionList, [varData])
        vstore = VarStoreData(otVarStore=varStore)
        topDict = self.font["CFF2"].cff.topDictIndex[0]
        topDict.VarStore = vstore
        for fontDict in topDict.FDArray:
            fontDict.Private.vstore = vstore

    def setupGlyf(self, glyphs, calcGlyphBounds=True, validateGlyphFormat=True):
        """Create the `glyf` table from a dict, that maps glyph names
        to `fontTools.ttLib.tables._g_l_y_f.Glyph` objects, for example
        as made by `fontTools.pens.ttGlyphPen.TTGlyphPen`.

        If `calcGlyphBounds` is True, the bounds of all glyphs will be
        calculated. Only pass False if your glyph objects already have
        their bounding box values set.

        If `validateGlyphFormat` is True, raise ValueError if any of the glyphs contains
        cubic curves or is a variable composite but head.glyphDataFormat=0.
        Set it to False to skip the check if you know in advance all the glyphs are
        compatible with the specified glyphDataFormat.
        """
        assert self.isTTF

        if validateGlyphFormat and self.font["head"].glyphDataFormat == 0:
            for name, g in glyphs.items():
                if g.numberOfContours > 0 and any(f & flagCubic for f in g.flags):
                    raise ValueError(
                        f"Glyph {name!r} has cubic Bezier outlines, but glyphDataFormat=0; "
                        "either convert to quadratics with cu2qu or set glyphDataFormat=1."
                    )

        self.font["loca"] = newTable("loca")
        self.font["glyf"] = newTable("glyf")
        self.font["glyf"].glyphs = glyphs
        if hasattr(self.font, "glyphOrder"):
            self.font["glyf"].glyphOrder = self.font.glyphOrder
        if calcGlyphBounds:
            self.calcGlyphBounds()

    def setupFvar(self, axes, instances):
        """Adds an font variations table to the font.

        Args:
            axes (list): See below.
            instances (list): See below.

        ``axes`` should be a list of axes, with each axis either supplied as
        a py:class:`.designspaceLib.AxisDescriptor` object, or a tuple in the
        format ```tupletag, minValue, defaultValue, maxValue, name``.
        The ``name`` is either a string, or a dict, mapping language codes
        to strings, to allow localized name table entries.

        ```instances`` should be a list of instances, with each instance either
        supplied as a py:class:`.designspaceLib.InstanceDescriptor` object, or a
        dict with keys ``location`` (mapping of axis tags to float values),
        ``stylename`` and (optionally) ``postscriptfontname``.
        The ``stylename`` is either a string, or a dict, mapping language codes
        to strings, to allow localized name table entries.
        """

        addFvar(self.font, axes, instances)

    def setupAvar(self, axes, mappings=None):
        """Adds an axis variations table to the font.

        Args:
            axes (list): A list of py:class:`.designspaceLib.AxisDescriptor` objects.
        """
        from .varLib import _add_avar

        if "fvar" not in self.font:
            raise KeyError("'fvar' table is missing; can't add 'avar'.")

        axisTags = [axis.axisTag for axis in self.font["fvar"].axes]
        axes = OrderedDict(enumerate(axes))  # Only values are used
        _add_avar(self.font, axes, mappings, axisTags)

    def setupGvar(self, variations):
        gvar = self.font["gvar"] = newTable("gvar")
        gvar.version = 1
        gvar.reserved = 0
        gvar.variations = variations

    def setupGVAR(self, variations):
        gvar = self.font["GVAR"] = newTable("GVAR")
        gvar.version = 1
        gvar.reserved = 0
        gvar.variations = variations

    def calcGlyphBounds(self):
        """Calculate the bounding boxes of all glyphs in the `glyf` table.
        This is usually not called explicitly by client code.
        """
        glyphTable = self.font["glyf"]
        for glyph in glyphTable.glyphs.values():
            glyph.recalcBounds(glyphTable)

    def setupHorizontalMetrics(self, metrics):
        """Create a new `hmtx` table, for horizontal metrics.

        The `metrics` argument must be a dict, mapping glyph names to
        `(width, leftSidebearing)` tuples.
        """
        self.setupMetrics("hmtx", metrics)

    def setupVerticalMetrics(self, metrics):
        """Create a new `vmtx` table, for horizontal metrics.

        The `metrics` argument must be a dict, mapping glyph names to
        `(height, topSidebearing)` tuples.
        """
        self.setupMetrics("vmtx", metrics)

    def setupMetrics(self, tableTag, metrics):
        """See `setupHorizontalMetrics()` and `setupVerticalMetrics()`."""
        assert tableTag in ("hmtx", "vmtx")
        mtxTable = self.font[tableTag] = newTable(tableTag)
        roundedMetrics = {}
        for gn in metrics:
            w, lsb = metrics[gn]
            roundedMetrics[gn] = int(round(w)), int(round(lsb))
        mtxTable.metrics = roundedMetrics

    def setupHorizontalHeader(self, **values):
        """Create a new `hhea` table initialize it with default values,
        which can be overridden by keyword arguments.
        """
        self._initTableWithValues("hhea", _hheaDefaults, values)

    def setupVerticalHeader(self, **values):
        """Create a new `vhea` table initialize it with default values,
        which can be overridden by keyword arguments.
        """
        self._initTableWithValues("vhea", _vheaDefaults, values)

    def setupVerticalOrigins(self, verticalOrigins, defaultVerticalOrigin=None):
        """Create a new `VORG` table. The `verticalOrigins` argument must be
        a dict, mapping glyph names to vertical origin values.

        The `defaultVerticalOrigin` argument should be the most common vertical
        origin value. If omitted, this value will be derived from the actual
        values in the `verticalOrigins` argument.
        """
        if defaultVerticalOrigin is None:
            # find the most frequent vorg value
            bag = {}
            for gn in verticalOrigins:
                vorg = verticalOrigins[gn]
                if vorg not in bag:
                    bag[vorg] = 1
                else:
                    bag[vorg] += 1
            defaultVerticalOrigin = sorted(
                bag, key=lambda vorg: bag[vorg], reverse=True
            )[0]
        self._initTableWithValues(
            "VORG",
            {},
            dict(VOriginRecords={}, defaultVertOriginY=defaultVerticalOrigin),
        )
        vorgTable = self.font["VORG"]
        vorgTable.majorVersion = 1
        vorgTable.minorVersion = 0
        for gn in verticalOrigins:
            vorgTable[gn] = verticalOrigins[gn]

    def setupPost(self, keepGlyphNames=True, **values):
        """Create a new `post` table and initialize it with default values,
        which can be overridden by keyword arguments.
        """
        isCFF2 = "CFF2" in self.font
        postTable = self._initTableWithValues("post", _postDefaults, values)
        if (self.isTTF or isCFF2) and keepGlyphNames:
            postTable.formatType = 2.0
            postTable.extraNames = []
            postTable.mapping = {}
        else:
            postTable.formatType = 3.0

    def setupMaxp(self):
        """Create a new `maxp` table. This is called implicitly by FontBuilder
        itself and is usually not called by client code.
        """
        if self.isTTF:
            defaults = _maxpDefaultsTTF
        else:
            defaults = _maxpDefaultsOTF
        self._initTableWithValues("maxp", defaults, {})

    def setupDummyDSIG(self):
        """This adds an empty DSIG table to the font to make some MS applications
        happy. This does not properly sign the font.
        """
        values = dict(
            ulVersion=1,
            usFlag=0,
            usNumSigs=0,
            signatureRecords=[],
        )
        self._initTableWithValues("DSIG", {}, values)

    def addOpenTypeFeatures(self, features, filename=None, tables=None, debug=False):
        """Add OpenType features to the font from a string containing
        Feature File syntax.

        The `filename` argument is used in error messages and to determine
        where to look for "include" files.

        The optional `tables` argument can be a list of OTL tables tags to
        build, allowing the caller to only build selected OTL tables. See
        `fontTools.feaLib` for details.

        The optional `debug` argument controls whether to add source debugging
        information to the font in the `Debg` table.
        """
        from .feaLib.builder import addOpenTypeFeaturesFromString

        addOpenTypeFeaturesFromString(
            self.font, features, filename=filename, tables=tables, debug=debug
        )

    def addFeatureVariations(self, conditionalSubstitutions, featureTag="rvrn"):
        """Add conditional substitutions to a Variable Font.

        See `fontTools.varLib.featureVars.addFeatureVariations`.
        """
        from .varLib import featureVars

        if "fvar" not in self.font:
            raise KeyError("'fvar' table is missing; can't add FeatureVariations.")

        featureVars.addFeatureVariations(
            self.font, conditionalSubstitutions, featureTag=featureTag
        )

    def setupCOLR(
        self,
        colorLayers,
        version=None,
        varStore=None,
        varIndexMap=None,
        clipBoxes=None,
        allowLayerReuse=True,
    ):
        """Build new COLR table using color layers dictionary.

        Cf. `fontTools.colorLib.builder.buildCOLR`.
        """
        from fontTools.colorLib.builder import buildCOLR

        glyphMap = self.font.getReverseGlyphMap()
        self.font["COLR"] = buildCOLR(
            colorLayers,
            version=version,
            glyphMap=glyphMap,
            varStore=varStore,
            varIndexMap=varIndexMap,
            clipBoxes=clipBoxes,
            allowLayerReuse=allowLayerReuse,
        )

    def setupCPAL(
        self,
        palettes,
        paletteTypes=None,
        paletteLabels=None,
        paletteEntryLabels=None,
    ):
        """Build new CPAL table using list of palettes.

        Optionally build CPAL v1 table using paletteTypes, paletteLabels and
        paletteEntryLabels.

        Cf. `fontTools.colorLib.builder.buildCPAL`.
        """
        from fontTools.colorLib.builder import buildCPAL

        self.font["CPAL"] = buildCPAL(
            palettes,
            paletteTypes=paletteTypes,
            paletteLabels=paletteLabels,
            paletteEntryLabels=paletteEntryLabels,
            nameTable=self.font.get("name"),
        )

    def setupStat(self, axes, locations=None, elidedFallbackName=2):
        """Build a new 'STAT' table.

        See `fontTools.otlLib.builder.buildStatTable` for details about
        the arguments.
        """
        from .otlLib.builder import buildStatTable

        assert "name" in self.font, "name must to be set up first"

        buildStatTable(
            self.font,
            axes,
            locations,
            elidedFallbackName,
            macNames=any(nr.platformID == 1 for nr in self.font["name"].names),
        )


def buildCmapSubTable(cmapping, format, platformID, platEncID):
    subTable = cmap_classes[format](format)
    subTable.cmap = cmapping
    subTable.platformID = platformID
    subTable.platEncID = platEncID
    subTable.language = 0
    return subTable


def addFvar(font, axes, instances):
    from .ttLib.tables._f_v_a_r import Axis, NamedInstance

    assert axes

    fvar = newTable("fvar")
    nameTable = font["name"]

    # if there are not currently any mac names don't add them here, that's inconsistent
    # https://github.com/fonttools/fonttools/issues/683
    macNames = any(nr.platformID == 1 for nr in getattr(nameTable, "names", ()))

    # we have all the best ways to express mac names
    platforms = ((3, 1, 0x409),)
    if macNames:
        platforms = ((1, 0, 0),) + platforms

    for axis_def in axes:
        axis = Axis()

        if isinstance(axis_def, tuple):
            (
                axis.axisTag,
                axis.minValue,
                axis.defaultValue,
                axis.maxValue,
                name,
            ) = axis_def
        else:
            (axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue, name) = (
                axis_def.tag,
                axis_def.minimum,
                axis_def.default,
                axis_def.maximum,
                axis_def.name,
            )
            if axis_def.hidden:
                axis.flags = 0x0001  # HIDDEN_AXIS

        if isinstance(name, str):
            name = dict(en=name)

        axis.axisNameID = nameTable.addMultilingualName(name, ttFont=font, mac=macNames)
        fvar.axes.append(axis)

    for instance in instances:
        if isinstance(instance, dict):
            coordinates = instance["location"]
            name = instance["stylename"]
            psname = instance.get("postscriptfontname")
        else:
            coordinates = instance.location
            name = instance.localisedStyleName or instance.styleName
            psname = instance.postScriptFontName

        if isinstance(name, str):
            name = dict(en=name)

        inst = NamedInstance()
        inst.subfamilyNameID = nameTable.addMultilingualName(
            name, ttFont=font, mac=macNames
        )
        if psname is not None:
            inst.postscriptNameID = nameTable.addName(psname, platforms=platforms)
        inst.coordinates = coordinates
        fvar.instances.append(inst)

    font["fvar"] = fvar
