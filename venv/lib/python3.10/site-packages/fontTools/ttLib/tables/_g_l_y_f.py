"""_g_l_y_f.py -- Converter classes for the 'glyf' table."""

from collections import namedtuple
from fontTools.misc import sstruct
from fontTools import ttLib
from fontTools import version
from fontTools.misc.transform import DecomposedTransform
from fontTools.misc.textTools import tostr, safeEval, pad
from fontTools.misc.arrayTools import updateBounds, pointInRect
from fontTools.misc.bezierTools import calcQuadraticBounds
from fontTools.misc.fixedTools import (
    fixedToFloat as fi2fl,
    floatToFixed as fl2fi,
    floatToFixedToStr as fl2str,
    strToFixedToFloat as str2fl,
)
from fontTools.misc.roundTools import noRound, otRound
from fontTools.misc.vector import Vector
from numbers import Number
from . import DefaultTable
from . import ttProgram
import sys
import struct
import array
import logging
import math
import os
from fontTools.misc import xmlWriter
from fontTools.misc.filenames import userNameToFileName
from fontTools.misc.loggingTools import deprecateFunction
from enum import IntFlag
from functools import partial
from types import SimpleNamespace
from typing import Set

log = logging.getLogger(__name__)

# We compute the version the same as is computed in ttlib/__init__
# so that we can write 'ttLibVersion' attribute of the glyf TTX files
# when glyf is written to separate files.
version = ".".join(version.split(".")[:2])

#
# The Apple and MS rasterizers behave differently for
# scaled composite components: one does scale first and then translate
# and the other does it vice versa. MS defined some flags to indicate
# the difference, but it seems nobody actually _sets_ those flags.
#
# Funny thing: Apple seems to _only_ do their thing in the
# WE_HAVE_A_SCALE (eg. Chicago) case, and not when it's WE_HAVE_AN_X_AND_Y_SCALE
# (eg. Charcoal)...
#
SCALE_COMPONENT_OFFSET_DEFAULT = 0  # 0 == MS, 1 == Apple


class table__g_l_y_f(DefaultTable.DefaultTable):
    """Glyph Data table

    This class represents the `glyf <https://docs.microsoft.com/en-us/typography/opentype/spec/glyf>`_
    table, which contains outlines for glyphs in TrueType format. In many cases,
    it is easier to access and manipulate glyph outlines through the ``GlyphSet``
    object returned from :py:meth:`fontTools.ttLib.ttFont.getGlyphSet`::

                    >> from fontTools.pens.boundsPen import BoundsPen
                    >> glyphset = font.getGlyphSet()
                    >> bp = BoundsPen(glyphset)
                    >> glyphset["A"].draw(bp)
                    >> bp.bounds
                    (19, 0, 633, 716)

    However, this class can be used for low-level access to the ``glyf`` table data.
    Objects of this class support dictionary-like access, mapping glyph names to
    :py:class:`Glyph` objects::

                    >> glyf = font["glyf"]
                    >> len(glyf["Aacute"].components)
                    2

    Note that when adding glyphs to the font via low-level access to the ``glyf``
    table, the new glyphs must also be added to the ``hmtx``/``vmtx`` table::

                    >> font["glyf"]["divisionslash"] = Glyph()
                    >> font["hmtx"]["divisionslash"] = (640, 0)

    """

    dependencies = ["fvar"]

    # this attribute controls the amount of padding applied to glyph data upon compile.
    # Glyph lenghts are aligned to multiples of the specified value.
    # Allowed values are (0, 1, 2, 4). '0' means no padding; '1' (default) also means
    # no padding, except for when padding would allow to use short loca offsets.
    padding = 1

    def decompile(self, data, ttFont):
        self.axisTags = (
            [axis.axisTag for axis in ttFont["fvar"].axes] if "fvar" in ttFont else []
        )
        loca = ttFont["loca"]
        pos = int(loca[0])
        nextPos = 0
        noname = 0
        self.glyphs = {}
        self.glyphOrder = glyphOrder = ttFont.getGlyphOrder()
        self._reverseGlyphOrder = {}
        for i in range(0, len(loca) - 1):
            try:
                glyphName = glyphOrder[i]
            except IndexError:
                noname = noname + 1
                glyphName = "ttxautoglyph%s" % i
            nextPos = int(loca[i + 1])
            glyphdata = data[pos:nextPos]
            if len(glyphdata) != (nextPos - pos):
                raise ttLib.TTLibError("not enough 'glyf' table data")
            glyph = Glyph(glyphdata)
            self.glyphs[glyphName] = glyph
            pos = nextPos
        if len(data) - nextPos >= 4:
            log.warning(
                "too much 'glyf' table data: expected %d, received %d bytes",
                nextPos,
                len(data),
            )
        if noname:
            log.warning("%s glyphs have no name", noname)
        if ttFont.lazy is False:  # Be lazy for None and True
            self.ensureDecompiled()

    def ensureDecompiled(self, recurse=False):
        # The recurse argument is unused, but part of the signature of
        # ensureDecompiled across the library.
        for glyph in self.glyphs.values():
            glyph.expand(self)

    def compile(self, ttFont):
        optimizeSpeed = ttFont.cfg[ttLib.OPTIMIZE_FONT_SPEED]

        self.axisTags = (
            [axis.axisTag for axis in ttFont["fvar"].axes] if "fvar" in ttFont else []
        )
        if not hasattr(self, "glyphOrder"):
            self.glyphOrder = ttFont.getGlyphOrder()
        padding = self.padding
        assert padding in (0, 1, 2, 4)
        locations = []
        currentLocation = 0
        dataList = []
        recalcBBoxes = ttFont.recalcBBoxes
        boundsDone = set()
        for glyphName in self.glyphOrder:
            glyph = self.glyphs[glyphName]
            glyphData = glyph.compile(
                self,
                recalcBBoxes,
                boundsDone=boundsDone,
                optimizeSize=not optimizeSpeed,
            )
            if padding > 1:
                glyphData = pad(glyphData, size=padding)
            locations.append(currentLocation)
            currentLocation = currentLocation + len(glyphData)
            dataList.append(glyphData)
        locations.append(currentLocation)

        if padding == 1 and currentLocation < 0x20000:
            # See if we can pad any odd-lengthed glyphs to allow loca
            # table to use the short offsets.
            indices = [
                i for i, glyphData in enumerate(dataList) if len(glyphData) % 2 == 1
            ]
            if indices and currentLocation + len(indices) < 0x20000:
                # It fits.  Do it.
                for i in indices:
                    dataList[i] += b"\0"
                currentLocation = 0
                for i, glyphData in enumerate(dataList):
                    locations[i] = currentLocation
                    currentLocation += len(glyphData)
                locations[len(dataList)] = currentLocation

        data = b"".join(dataList)
        if "loca" in ttFont:
            ttFont["loca"].set(locations)
        if "maxp" in ttFont:
            ttFont["maxp"].numGlyphs = len(self.glyphs)
        if not data:
            # As a special case when all glyph in the font are empty, add a zero byte
            # to the table, so that OTS doesn’t reject it, and to make the table work
            # on Windows as well.
            # See https://github.com/khaledhosny/ots/issues/52
            data = b"\0"
        return data

    def toXML(self, writer, ttFont, splitGlyphs=False):
        notice = (
            "The xMin, yMin, xMax and yMax values\n"
            "will be recalculated by the compiler."
        )
        glyphNames = ttFont.getGlyphNames()
        if not splitGlyphs:
            writer.newline()
            writer.comment(notice)
            writer.newline()
            writer.newline()
        numGlyphs = len(glyphNames)
        if splitGlyphs:
            path, ext = os.path.splitext(writer.file.name)
            existingGlyphFiles = set()
        for glyphName in glyphNames:
            glyph = self.get(glyphName)
            if glyph is None:
                log.warning("glyph '%s' does not exist in glyf table", glyphName)
                continue
            if glyph.numberOfContours:
                if splitGlyphs:
                    glyphPath = userNameToFileName(
                        tostr(glyphName, "utf-8"),
                        existingGlyphFiles,
                        prefix=path + ".",
                        suffix=ext,
                    )
                    existingGlyphFiles.add(glyphPath.lower())
                    glyphWriter = xmlWriter.XMLWriter(
                        glyphPath,
                        idlefunc=writer.idlefunc,
                        newlinestr=writer.newlinestr,
                    )
                    glyphWriter.begintag("ttFont", ttLibVersion=version)
                    glyphWriter.newline()
                    glyphWriter.begintag("glyf")
                    glyphWriter.newline()
                    glyphWriter.comment(notice)
                    glyphWriter.newline()
                    writer.simpletag("TTGlyph", src=os.path.basename(glyphPath))
                else:
                    glyphWriter = writer
                glyphWriter.begintag(
                    "TTGlyph",
                    [
                        ("name", glyphName),
                        ("xMin", glyph.xMin),
                        ("yMin", glyph.yMin),
                        ("xMax", glyph.xMax),
                        ("yMax", glyph.yMax),
                    ],
                )
                glyphWriter.newline()
                glyph.toXML(glyphWriter, ttFont)
                glyphWriter.endtag("TTGlyph")
                glyphWriter.newline()
                if splitGlyphs:
                    glyphWriter.endtag("glyf")
                    glyphWriter.newline()
                    glyphWriter.endtag("ttFont")
                    glyphWriter.newline()
                    glyphWriter.close()
            else:
                writer.simpletag("TTGlyph", name=glyphName)
                writer.comment("contains no outline data")
                if not splitGlyphs:
                    writer.newline()
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name != "TTGlyph":
            return
        if not hasattr(self, "glyphs"):
            self.glyphs = {}
        if not hasattr(self, "glyphOrder"):
            self.glyphOrder = ttFont.getGlyphOrder()
        glyphName = attrs["name"]
        log.debug("unpacking glyph '%s'", glyphName)
        glyph = Glyph()
        for attr in ["xMin", "yMin", "xMax", "yMax"]:
            setattr(glyph, attr, safeEval(attrs.get(attr, "0")))
        self.glyphs[glyphName] = glyph
        for element in content:
            if not isinstance(element, tuple):
                continue
            name, attrs, content = element
            glyph.fromXML(name, attrs, content, ttFont)
        if not ttFont.recalcBBoxes:
            glyph.compact(self, 0)

    def setGlyphOrder(self, glyphOrder):
        """Sets the glyph order

        Args:
                glyphOrder ([str]): List of glyph names in order.
        """
        self.glyphOrder = glyphOrder
        self._reverseGlyphOrder = {}

    def getGlyphName(self, glyphID):
        """Returns the name for the glyph with the given ID.

        Raises a ``KeyError`` if the glyph name is not found in the font.
        """
        return self.glyphOrder[glyphID]

    def _buildReverseGlyphOrderDict(self):
        self._reverseGlyphOrder = d = {}
        for glyphID, glyphName in enumerate(self.glyphOrder):
            d[glyphName] = glyphID

    def getGlyphID(self, glyphName):
        """Returns the ID of the glyph with the given name.

        Raises a ``ValueError`` if the glyph is not found in the font.
        """
        glyphOrder = self.glyphOrder
        id = getattr(self, "_reverseGlyphOrder", {}).get(glyphName)
        if id is None or id >= len(glyphOrder) or glyphOrder[id] != glyphName:
            self._buildReverseGlyphOrderDict()
            id = self._reverseGlyphOrder.get(glyphName)
        if id is None:
            raise ValueError(glyphName)
        return id

    def removeHinting(self):
        """Removes TrueType hints from all glyphs in the glyphset.

        See :py:meth:`Glyph.removeHinting`.
        """
        for glyph in self.glyphs.values():
            glyph.removeHinting()

    def keys(self):
        return self.glyphs.keys()

    def has_key(self, glyphName):
        return glyphName in self.glyphs

    __contains__ = has_key

    def get(self, glyphName, default=None):
        glyph = self.glyphs.get(glyphName, default)
        if glyph is not None:
            glyph.expand(self)
        return glyph

    def __getitem__(self, glyphName):
        glyph = self.glyphs[glyphName]
        glyph.expand(self)
        return glyph

    def __setitem__(self, glyphName, glyph):
        self.glyphs[glyphName] = glyph
        if glyphName not in self.glyphOrder:
            self.glyphOrder.append(glyphName)

    def __delitem__(self, glyphName):
        del self.glyphs[glyphName]
        self.glyphOrder.remove(glyphName)

    def __len__(self):
        assert len(self.glyphOrder) == len(self.glyphs)
        return len(self.glyphs)

    def _getPhantomPoints(self, glyphName, hMetrics, vMetrics=None):
        """Compute the four "phantom points" for the given glyph from its bounding box
        and the horizontal and vertical advance widths and sidebearings stored in the
        ttFont's "hmtx" and "vmtx" tables.

        'hMetrics' should be ttFont['hmtx'].metrics.

        'vMetrics' should be ttFont['vmtx'].metrics if there is "vmtx" or None otherwise.
        If there is no vMetrics passed in, vertical phantom points are set to the zero coordinate.

        https://docs.microsoft.com/en-us/typography/opentype/spec/tt_instructing_glyphs#phantoms
        """
        glyph = self[glyphName]
        if not hasattr(glyph, "xMin"):
            glyph.recalcBounds(self)

        horizontalAdvanceWidth, leftSideBearing = hMetrics[glyphName]
        leftSideX = glyph.xMin - leftSideBearing
        rightSideX = leftSideX + horizontalAdvanceWidth

        if vMetrics:
            verticalAdvanceWidth, topSideBearing = vMetrics[glyphName]
            topSideY = topSideBearing + glyph.yMax
            bottomSideY = topSideY - verticalAdvanceWidth
        else:
            bottomSideY = topSideY = 0

        return [
            (leftSideX, 0),
            (rightSideX, 0),
            (0, topSideY),
            (0, bottomSideY),
        ]

    def _getCoordinatesAndControls(
        self, glyphName, hMetrics, vMetrics=None, *, round=otRound
    ):
        """Return glyph coordinates and controls as expected by "gvar" table.

        The coordinates includes four "phantom points" for the glyph metrics,
        as mandated by the "gvar" spec.

        The glyph controls is a namedtuple with the following attributes:
                - numberOfContours: -1 for composite glyphs.
                - endPts: list of indices of end points for each contour in simple
                glyphs, or component indices in composite glyphs (used for IUP
                optimization).
                - flags: array of contour point flags for simple glyphs (None for
                composite glyphs).
                - components: list of base glyph names (str) for each component in
                composite glyphs (None for simple glyphs).

        The "hMetrics" and vMetrics are used to compute the "phantom points" (see
        the "_getPhantomPoints" method).

        Return None if the requested glyphName is not present.
        """
        glyph = self.get(glyphName)
        if glyph is None:
            return None
        if glyph.isComposite():
            coords = GlyphCoordinates(
                [(getattr(c, "x", 0), getattr(c, "y", 0)) for c in glyph.components]
            )
            controls = _GlyphControls(
                numberOfContours=glyph.numberOfContours,
                endPts=list(range(len(glyph.components))),
                flags=None,
                components=[
                    (c.glyphName, getattr(c, "transform", None))
                    for c in glyph.components
                ],
            )
        else:
            coords, endPts, flags = glyph.getCoordinates(self)
            coords = coords.copy()
            controls = _GlyphControls(
                numberOfContours=glyph.numberOfContours,
                endPts=endPts,
                flags=flags,
                components=None,
            )
        # Add phantom points for (left, right, top, bottom) positions.
        phantomPoints = self._getPhantomPoints(glyphName, hMetrics, vMetrics)
        coords.extend(phantomPoints)
        coords.toInt(round=round)
        return coords, controls

    def _setCoordinates(self, glyphName, coord, hMetrics, vMetrics=None):
        """Set coordinates and metrics for the given glyph.

        "coord" is an array of GlyphCoordinates which must include the "phantom
        points" as the last four coordinates.

        Both the horizontal/vertical advances and left/top sidebearings in "hmtx"
        and "vmtx" tables (if any) are updated from four phantom points and
        the glyph's bounding boxes.

        The "hMetrics" and vMetrics are used to propagate "phantom points"
        into "hmtx" and "vmtx" tables if desired.  (see the "_getPhantomPoints"
        method).
        """
        glyph = self[glyphName]

        # Handle phantom points for (left, right, top, bottom) positions.
        assert len(coord) >= 4
        leftSideX = coord[-4][0]
        rightSideX = coord[-3][0]
        topSideY = coord[-2][1]
        bottomSideY = coord[-1][1]

        coord = coord[:-4]

        if glyph.isComposite():
            assert len(coord) == len(glyph.components)
            for p, comp in zip(coord, glyph.components):
                if hasattr(comp, "x"):
                    comp.x, comp.y = p
        elif glyph.numberOfContours == 0:
            assert len(coord) == 0
        else:
            assert len(coord) == len(glyph.coordinates)
            glyph.coordinates = GlyphCoordinates(coord)

        glyph.recalcBounds(self, boundsDone=set())

        horizontalAdvanceWidth = otRound(rightSideX - leftSideX)
        if horizontalAdvanceWidth < 0:
            # unlikely, but it can happen, see:
            # https://github.com/fonttools/fonttools/pull/1198
            horizontalAdvanceWidth = 0
        leftSideBearing = otRound(glyph.xMin - leftSideX)
        hMetrics[glyphName] = horizontalAdvanceWidth, leftSideBearing

        if vMetrics is not None:
            verticalAdvanceWidth = otRound(topSideY - bottomSideY)
            if verticalAdvanceWidth < 0:  # unlikely but do the same as horizontal
                verticalAdvanceWidth = 0
            topSideBearing = otRound(topSideY - glyph.yMax)
            vMetrics[glyphName] = verticalAdvanceWidth, topSideBearing

    # Deprecated

    def _synthesizeVMetrics(self, glyphName, ttFont, defaultVerticalOrigin):
        """This method is wrong and deprecated.
        For rationale see:
        https://github.com/fonttools/fonttools/pull/2266/files#r613569473
        """
        vMetrics = getattr(ttFont.get("vmtx"), "metrics", None)
        if vMetrics is None:
            verticalAdvanceWidth = ttFont["head"].unitsPerEm
            topSideY = getattr(ttFont.get("hhea"), "ascent", None)
            if topSideY is None:
                if defaultVerticalOrigin is not None:
                    topSideY = defaultVerticalOrigin
                else:
                    topSideY = verticalAdvanceWidth
            glyph = self[glyphName]
            glyph.recalcBounds(self)
            topSideBearing = otRound(topSideY - glyph.yMax)
            vMetrics = {glyphName: (verticalAdvanceWidth, topSideBearing)}
        return vMetrics

    @deprecateFunction("use '_getPhantomPoints' instead", category=DeprecationWarning)
    def getPhantomPoints(self, glyphName, ttFont, defaultVerticalOrigin=None):
        """Old public name for self._getPhantomPoints().
        See: https://github.com/fonttools/fonttools/pull/2266"""
        hMetrics = ttFont["hmtx"].metrics
        vMetrics = self._synthesizeVMetrics(glyphName, ttFont, defaultVerticalOrigin)
        return self._getPhantomPoints(glyphName, hMetrics, vMetrics)

    @deprecateFunction(
        "use '_getCoordinatesAndControls' instead", category=DeprecationWarning
    )
    def getCoordinatesAndControls(self, glyphName, ttFont, defaultVerticalOrigin=None):
        """Old public name for self._getCoordinatesAndControls().
        See: https://github.com/fonttools/fonttools/pull/2266"""
        hMetrics = ttFont["hmtx"].metrics
        vMetrics = self._synthesizeVMetrics(glyphName, ttFont, defaultVerticalOrigin)
        return self._getCoordinatesAndControls(glyphName, hMetrics, vMetrics)

    @deprecateFunction("use '_setCoordinates' instead", category=DeprecationWarning)
    def setCoordinates(self, glyphName, ttFont):
        """Old public name for self._setCoordinates().
        See: https://github.com/fonttools/fonttools/pull/2266"""
        hMetrics = ttFont["hmtx"].metrics
        vMetrics = getattr(ttFont.get("vmtx"), "metrics", None)
        self._setCoordinates(glyphName, hMetrics, vMetrics)


_GlyphControls = namedtuple(
    "_GlyphControls", "numberOfContours endPts flags components"
)


glyphHeaderFormat = """
		>	# big endian
		numberOfContours:	h
		xMin:				h
		yMin:				h
		xMax:				h
		yMax:				h
"""

# flags
flagOnCurve = 0x01
flagXShort = 0x02
flagYShort = 0x04
flagRepeat = 0x08
flagXsame = 0x10
flagYsame = 0x20
flagOverlapSimple = 0x40
flagCubic = 0x80

# These flags are kept for XML output after decompiling the coordinates
keepFlags = flagOnCurve + flagOverlapSimple + flagCubic

_flagSignBytes = {
    0: 2,
    flagXsame: 0,
    flagXShort | flagXsame: +1,
    flagXShort: -1,
    flagYsame: 0,
    flagYShort | flagYsame: +1,
    flagYShort: -1,
}


def flagBest(x, y, onCurve):
    """For a given x,y delta pair, returns the flag that packs this pair
    most efficiently, as well as the number of byte cost of such flag."""

    flag = flagOnCurve if onCurve else 0
    cost = 0
    # do x
    if x == 0:
        flag = flag | flagXsame
    elif -255 <= x <= 255:
        flag = flag | flagXShort
        if x > 0:
            flag = flag | flagXsame
        cost += 1
    else:
        cost += 2
    # do y
    if y == 0:
        flag = flag | flagYsame
    elif -255 <= y <= 255:
        flag = flag | flagYShort
        if y > 0:
            flag = flag | flagYsame
        cost += 1
    else:
        cost += 2
    return flag, cost


def flagFits(newFlag, oldFlag, mask):
    newBytes = _flagSignBytes[newFlag & mask]
    oldBytes = _flagSignBytes[oldFlag & mask]
    return newBytes == oldBytes or abs(newBytes) > abs(oldBytes)


def flagSupports(newFlag, oldFlag):
    return (
        (oldFlag & flagOnCurve) == (newFlag & flagOnCurve)
        and flagFits(newFlag, oldFlag, flagXsame | flagXShort)
        and flagFits(newFlag, oldFlag, flagYsame | flagYShort)
    )


def flagEncodeCoord(flag, mask, coord, coordBytes):
    byteCount = _flagSignBytes[flag & mask]
    if byteCount == 1:
        coordBytes.append(coord)
    elif byteCount == -1:
        coordBytes.append(-coord)
    elif byteCount == 2:
        coordBytes.extend(struct.pack(">h", coord))


def flagEncodeCoords(flag, x, y, xBytes, yBytes):
    flagEncodeCoord(flag, flagXsame | flagXShort, x, xBytes)
    flagEncodeCoord(flag, flagYsame | flagYShort, y, yBytes)


ARG_1_AND_2_ARE_WORDS = 0x0001  # if set args are words otherwise they are bytes
ARGS_ARE_XY_VALUES = 0x0002  # if set args are xy values, otherwise they are points
ROUND_XY_TO_GRID = 0x0004  # for the xy values if above is true
WE_HAVE_A_SCALE = 0x0008  # Sx = Sy, otherwise scale == 1.0
NON_OVERLAPPING = 0x0010  # set to same value for all components (obsolete!)
MORE_COMPONENTS = 0x0020  # indicates at least one more glyph after this one
WE_HAVE_AN_X_AND_Y_SCALE = 0x0040  # Sx, Sy
WE_HAVE_A_TWO_BY_TWO = 0x0080  # t00, t01, t10, t11
WE_HAVE_INSTRUCTIONS = 0x0100  # instructions follow
USE_MY_METRICS = 0x0200  # apply these metrics to parent glyph
OVERLAP_COMPOUND = 0x0400  # used by Apple in GX fonts
SCALED_COMPONENT_OFFSET = 0x0800  # composite designed to have the component offset scaled (designed for Apple)
UNSCALED_COMPONENT_OFFSET = 0x1000  # composite designed not to have the component offset scaled (designed for MS)


CompositeMaxpValues = namedtuple(
    "CompositeMaxpValues", ["nPoints", "nContours", "maxComponentDepth"]
)


class Glyph(object):
    """This class represents an individual TrueType glyph.

    TrueType glyph objects come in two flavours: simple and composite. Simple
    glyph objects contain contours, represented via the ``.coordinates``,
    ``.flags``, ``.numberOfContours``, and ``.endPtsOfContours`` attributes;
    composite glyphs contain components, available through the ``.components``
    attributes.

    Because the ``.coordinates`` attribute (and other simple glyph attributes mentioned
    above) is only set on simple glyphs and the ``.components`` attribute is only
    set on composite glyphs, it is necessary to use the :py:meth:`isComposite`
    method to test whether a glyph is simple or composite before attempting to
    access its data.

    For a composite glyph, the components can also be accessed via array-like access::

            >> assert(font["glyf"]["Aacute"].isComposite())
            >> font["glyf"]["Aacute"][0]
            <fontTools.ttLib.tables._g_l_y_f.GlyphComponent at 0x1027b2ee0>

    """

    def __init__(self, data=b""):
        if not data:
            # empty char
            self.numberOfContours = 0
            return
        self.data = data

    def compact(self, glyfTable, recalcBBoxes=True):
        data = self.compile(glyfTable, recalcBBoxes)
        self.__dict__.clear()
        self.data = data

    def expand(self, glyfTable):
        if not hasattr(self, "data"):
            # already unpacked
            return
        if not self.data:
            # empty char
            del self.data
            self.numberOfContours = 0
            return
        dummy, data = sstruct.unpack2(glyphHeaderFormat, self.data, self)
        del self.data
        # Some fonts (eg. Neirizi.ttf) have a 0 for numberOfContours in
        # some glyphs; decompileCoordinates assumes that there's at least
        # one, so short-circuit here.
        if self.numberOfContours == 0:
            return
        if self.isComposite():
            self.decompileComponents(data, glyfTable)
        else:
            self.decompileCoordinates(data)

    def compile(
        self, glyfTable, recalcBBoxes=True, *, boundsDone=None, optimizeSize=True
    ):
        if hasattr(self, "data"):
            if recalcBBoxes:
                # must unpack glyph in order to recalculate bounding box
                self.expand(glyfTable)
            else:
                return self.data
        if self.numberOfContours == 0:
            return b""

        if recalcBBoxes:
            self.recalcBounds(glyfTable, boundsDone=boundsDone)

        data = sstruct.pack(glyphHeaderFormat, self)
        if self.isComposite():
            data = data + self.compileComponents(glyfTable)
        else:
            data = data + self.compileCoordinates(optimizeSize=optimizeSize)
        return data

    def toXML(self, writer, ttFont):
        if self.isComposite():
            for compo in self.components:
                compo.toXML(writer, ttFont)
            haveInstructions = hasattr(self, "program")
        else:
            last = 0
            for i in range(self.numberOfContours):
                writer.begintag("contour")
                writer.newline()
                for j in range(last, self.endPtsOfContours[i] + 1):
                    attrs = [
                        ("x", self.coordinates[j][0]),
                        ("y", self.coordinates[j][1]),
                        ("on", self.flags[j] & flagOnCurve),
                    ]
                    if self.flags[j] & flagOverlapSimple:
                        # Apple's rasterizer uses flagOverlapSimple in the first contour/first pt to flag glyphs that contain overlapping contours
                        attrs.append(("overlap", 1))
                    if self.flags[j] & flagCubic:
                        attrs.append(("cubic", 1))
                    writer.simpletag("pt", attrs)
                    writer.newline()
                last = self.endPtsOfContours[i] + 1
                writer.endtag("contour")
                writer.newline()
            haveInstructions = self.numberOfContours > 0
        if haveInstructions:
            if self.program:
                writer.begintag("instructions")
                writer.newline()
                self.program.toXML(writer, ttFont)
                writer.endtag("instructions")
            else:
                writer.simpletag("instructions")
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "contour":
            if self.numberOfContours < 0:
                raise ttLib.TTLibError("can't mix composites and contours in glyph")
            self.numberOfContours = self.numberOfContours + 1
            coordinates = GlyphCoordinates()
            flags = bytearray()
            for element in content:
                if not isinstance(element, tuple):
                    continue
                name, attrs, content = element
                if name != "pt":
                    continue  # ignore anything but "pt"
                coordinates.append((safeEval(attrs["x"]), safeEval(attrs["y"])))
                flag = bool(safeEval(attrs["on"]))
                if "overlap" in attrs and bool(safeEval(attrs["overlap"])):
                    flag |= flagOverlapSimple
                if "cubic" in attrs and bool(safeEval(attrs["cubic"])):
                    flag |= flagCubic
                flags.append(flag)
            if not hasattr(self, "coordinates"):
                self.coordinates = coordinates
                self.flags = flags
                self.endPtsOfContours = [len(coordinates) - 1]
            else:
                self.coordinates.extend(coordinates)
                self.flags.extend(flags)
                self.endPtsOfContours.append(len(self.coordinates) - 1)
        elif name == "component":
            if self.numberOfContours > 0:
                raise ttLib.TTLibError("can't mix composites and contours in glyph")
            self.numberOfContours = -1
            if not hasattr(self, "components"):
                self.components = []
            component = GlyphComponent()
            self.components.append(component)
            component.fromXML(name, attrs, content, ttFont)
        elif name == "instructions":
            self.program = ttProgram.Program()
            for element in content:
                if not isinstance(element, tuple):
                    continue
                name, attrs, content = element
                self.program.fromXML(name, attrs, content, ttFont)

    def getCompositeMaxpValues(self, glyfTable, maxComponentDepth=1):
        assert self.isComposite()
        nContours = 0
        nPoints = 0
        initialMaxComponentDepth = maxComponentDepth
        for compo in self.components:
            baseGlyph = glyfTable[compo.glyphName]
            if baseGlyph.numberOfContours == 0:
                continue
            elif baseGlyph.numberOfContours > 0:
                nP, nC = baseGlyph.getMaxpValues()
            else:
                nP, nC, componentDepth = baseGlyph.getCompositeMaxpValues(
                    glyfTable, initialMaxComponentDepth + 1
                )
                maxComponentDepth = max(maxComponentDepth, componentDepth)
            nPoints = nPoints + nP
            nContours = nContours + nC
        return CompositeMaxpValues(nPoints, nContours, maxComponentDepth)

    def getMaxpValues(self):
        assert self.numberOfContours > 0
        return len(self.coordinates), len(self.endPtsOfContours)

    def decompileComponents(self, data, glyfTable):
        self.components = []
        more = 1
        haveInstructions = 0
        while more:
            component = GlyphComponent()
            more, haveInstr, data = component.decompile(data, glyfTable)
            haveInstructions = haveInstructions | haveInstr
            self.components.append(component)
        if haveInstructions:
            (numInstructions,) = struct.unpack(">h", data[:2])
            data = data[2:]
            self.program = ttProgram.Program()
            self.program.fromBytecode(data[:numInstructions])
            data = data[numInstructions:]
            if len(data) >= 4:
                log.warning(
                    "too much glyph data at the end of composite glyph: %d excess bytes",
                    len(data),
                )

    def decompileCoordinates(self, data):
        endPtsOfContours = array.array("H")
        endPtsOfContours.frombytes(data[: 2 * self.numberOfContours])
        if sys.byteorder != "big":
            endPtsOfContours.byteswap()
        self.endPtsOfContours = endPtsOfContours.tolist()

        pos = 2 * self.numberOfContours
        (instructionLength,) = struct.unpack(">h", data[pos : pos + 2])
        self.program = ttProgram.Program()
        self.program.fromBytecode(data[pos + 2 : pos + 2 + instructionLength])
        pos += 2 + instructionLength
        nCoordinates = self.endPtsOfContours[-1] + 1
        flags, xCoordinates, yCoordinates = self.decompileCoordinatesRaw(
            nCoordinates, data, pos
        )

        # fill in repetitions and apply signs
        self.coordinates = coordinates = GlyphCoordinates.zeros(nCoordinates)
        xIndex = 0
        yIndex = 0
        for i in range(nCoordinates):
            flag = flags[i]
            # x coordinate
            if flag & flagXShort:
                if flag & flagXsame:
                    x = xCoordinates[xIndex]
                else:
                    x = -xCoordinates[xIndex]
                xIndex = xIndex + 1
            elif flag & flagXsame:
                x = 0
            else:
                x = xCoordinates[xIndex]
                xIndex = xIndex + 1
            # y coordinate
            if flag & flagYShort:
                if flag & flagYsame:
                    y = yCoordinates[yIndex]
                else:
                    y = -yCoordinates[yIndex]
                yIndex = yIndex + 1
            elif flag & flagYsame:
                y = 0
            else:
                y = yCoordinates[yIndex]
                yIndex = yIndex + 1
            coordinates[i] = (x, y)
        assert xIndex == len(xCoordinates)
        assert yIndex == len(yCoordinates)
        coordinates.relativeToAbsolute()
        # discard all flags except "keepFlags"
        for i in range(len(flags)):
            flags[i] &= keepFlags
        self.flags = flags

    def decompileCoordinatesRaw(self, nCoordinates, data, pos=0):
        # unpack flags and prepare unpacking of coordinates
        flags = bytearray(nCoordinates)
        # Warning: deep Python trickery going on. We use the struct module to unpack
        # the coordinates. We build a format string based on the flags, so we can
        # unpack the coordinates in one struct.unpack() call.
        xFormat = ">"  # big endian
        yFormat = ">"  # big endian
        j = 0
        while True:
            flag = data[pos]
            pos += 1
            repeat = 1
            if flag & flagRepeat:
                repeat = data[pos] + 1
                pos += 1
            for k in range(repeat):
                if flag & flagXShort:
                    xFormat = xFormat + "B"
                elif not (flag & flagXsame):
                    xFormat = xFormat + "h"
                if flag & flagYShort:
                    yFormat = yFormat + "B"
                elif not (flag & flagYsame):
                    yFormat = yFormat + "h"
                flags[j] = flag
                j = j + 1
            if j >= nCoordinates:
                break
        assert j == nCoordinates, "bad glyph flags"
        # unpack raw coordinates, krrrrrr-tching!
        xDataLen = struct.calcsize(xFormat)
        yDataLen = struct.calcsize(yFormat)
        if len(data) - pos - (xDataLen + yDataLen) >= 4:
            log.warning(
                "too much glyph data: %d excess bytes",
                len(data) - pos - (xDataLen + yDataLen),
            )
        xCoordinates = struct.unpack(xFormat, data[pos : pos + xDataLen])
        yCoordinates = struct.unpack(
            yFormat, data[pos + xDataLen : pos + xDataLen + yDataLen]
        )
        return flags, xCoordinates, yCoordinates

    def compileComponents(self, glyfTable):
        data = b""
        lastcomponent = len(self.components) - 1
        more = 1
        haveInstructions = 0
        for i, compo in enumerate(self.components):
            if i == lastcomponent:
                haveInstructions = hasattr(self, "program")
                more = 0
            data = data + compo.compile(more, haveInstructions, glyfTable)
        if haveInstructions:
            instructions = self.program.getBytecode()
            data = data + struct.pack(">h", len(instructions)) + instructions
        return data

    def compileCoordinates(self, *, optimizeSize=True):
        assert len(self.coordinates) == len(self.flags)
        data = []
        endPtsOfContours = array.array("H", self.endPtsOfContours)
        if sys.byteorder != "big":
            endPtsOfContours.byteswap()
        data.append(endPtsOfContours.tobytes())
        instructions = self.program.getBytecode()
        data.append(struct.pack(">h", len(instructions)))
        data.append(instructions)

        deltas = self.coordinates.copy()
        deltas.toInt()
        deltas.absoluteToRelative()

        if optimizeSize:
            # TODO(behdad): Add a configuration option for this?
            deltas = self.compileDeltasGreedy(self.flags, deltas)
            # deltas = self.compileDeltasOptimal(self.flags, deltas)
        else:
            deltas = self.compileDeltasForSpeed(self.flags, deltas)

        data.extend(deltas)
        return b"".join(data)

    def compileDeltasGreedy(self, flags, deltas):
        # Implements greedy algorithm for packing coordinate deltas:
        # uses shortest representation one coordinate at a time.
        compressedFlags = bytearray()
        compressedXs = bytearray()
        compressedYs = bytearray()
        lastflag = None
        repeat = 0
        for flag, (x, y) in zip(flags, deltas):
            # Oh, the horrors of TrueType
            # do x
            if x == 0:
                flag = flag | flagXsame
            elif -255 <= x <= 255:
                flag = flag | flagXShort
                if x > 0:
                    flag = flag | flagXsame
                else:
                    x = -x
                compressedXs.append(x)
            else:
                compressedXs.extend(struct.pack(">h", x))
            # do y
            if y == 0:
                flag = flag | flagYsame
            elif -255 <= y <= 255:
                flag = flag | flagYShort
                if y > 0:
                    flag = flag | flagYsame
                else:
                    y = -y
                compressedYs.append(y)
            else:
                compressedYs.extend(struct.pack(">h", y))
            # handle repeating flags
            if flag == lastflag and repeat != 255:
                repeat = repeat + 1
                if repeat == 1:
                    compressedFlags.append(flag)
                else:
                    compressedFlags[-2] = flag | flagRepeat
                    compressedFlags[-1] = repeat
            else:
                repeat = 0
                compressedFlags.append(flag)
            lastflag = flag
        return (compressedFlags, compressedXs, compressedYs)

    def compileDeltasOptimal(self, flags, deltas):
        # Implements optimal, dynaic-programming, algorithm for packing coordinate
        # deltas.  The savings are negligible :(.
        candidates = []
        bestTuple = None
        bestCost = 0
        repeat = 0
        for flag, (x, y) in zip(flags, deltas):
            # Oh, the horrors of TrueType
            flag, coordBytes = flagBest(x, y, flag)
            bestCost += 1 + coordBytes
            newCandidates = [
                (bestCost, bestTuple, flag, coordBytes),
                (bestCost + 1, bestTuple, (flag | flagRepeat), coordBytes),
            ]
            for lastCost, lastTuple, lastFlag, coordBytes in candidates:
                if (
                    lastCost + coordBytes <= bestCost + 1
                    and (lastFlag & flagRepeat)
                    and (lastFlag < 0xFF00)
                    and flagSupports(lastFlag, flag)
                ):
                    if (lastFlag & 0xFF) == (
                        flag | flagRepeat
                    ) and lastCost == bestCost + 1:
                        continue
                    newCandidates.append(
                        (lastCost + coordBytes, lastTuple, lastFlag + 256, coordBytes)
                    )
            candidates = newCandidates
            bestTuple = min(candidates, key=lambda t: t[0])
            bestCost = bestTuple[0]

        flags = []
        while bestTuple:
            cost, bestTuple, flag, coordBytes = bestTuple
            flags.append(flag)
        flags.reverse()

        compressedFlags = bytearray()
        compressedXs = bytearray()
        compressedYs = bytearray()
        coords = iter(deltas)
        ff = []
        for flag in flags:
            repeatCount, flag = flag >> 8, flag & 0xFF
            compressedFlags.append(flag)
            if flag & flagRepeat:
                assert repeatCount > 0
                compressedFlags.append(repeatCount)
            else:
                assert repeatCount == 0
            for i in range(1 + repeatCount):
                x, y = next(coords)
                flagEncodeCoords(flag, x, y, compressedXs, compressedYs)
                ff.append(flag)
        try:
            next(coords)
            raise Exception("internal error")
        except StopIteration:
            pass

        return (compressedFlags, compressedXs, compressedYs)

    def compileDeltasForSpeed(self, flags, deltas):
        # uses widest representation needed, for all deltas.
        compressedFlags = bytearray()
        compressedXs = bytearray()
        compressedYs = bytearray()

        # Compute the necessary width for each axis
        xs = [d[0] for d in deltas]
        ys = [d[1] for d in deltas]
        minX, minY, maxX, maxY = min(xs), min(ys), max(xs), max(ys)
        xZero = minX == 0 and maxX == 0
        yZero = minY == 0 and maxY == 0
        xShort = -255 <= minX <= maxX <= 255
        yShort = -255 <= minY <= maxY <= 255

        lastflag = None
        repeat = 0
        for flag, (x, y) in zip(flags, deltas):
            # Oh, the horrors of TrueType
            # do x
            if xZero:
                flag = flag | flagXsame
            elif xShort:
                flag = flag | flagXShort
                if x > 0:
                    flag = flag | flagXsame
                else:
                    x = -x
                compressedXs.append(x)
            else:
                compressedXs.extend(struct.pack(">h", x))
            # do y
            if yZero:
                flag = flag | flagYsame
            elif yShort:
                flag = flag | flagYShort
                if y > 0:
                    flag = flag | flagYsame
                else:
                    y = -y
                compressedYs.append(y)
            else:
                compressedYs.extend(struct.pack(">h", y))
            # handle repeating flags
            if flag == lastflag and repeat != 255:
                repeat = repeat + 1
                if repeat == 1:
                    compressedFlags.append(flag)
                else:
                    compressedFlags[-2] = flag | flagRepeat
                    compressedFlags[-1] = repeat
            else:
                repeat = 0
                compressedFlags.append(flag)
            lastflag = flag
        return (compressedFlags, compressedXs, compressedYs)

    def recalcBounds(self, glyfTable, *, boundsDone=None):
        """Recalculates the bounds of the glyph.

        Each glyph object stores its bounding box in the
        ``xMin``/``yMin``/``xMax``/``yMax`` attributes. These bounds must be
        recomputed when the ``coordinates`` change. The ``table__g_l_y_f`` bounds
        must be provided to resolve component bounds.
        """
        if self.isComposite() and self.tryRecalcBoundsComposite(
            glyfTable, boundsDone=boundsDone
        ):
            return
        try:
            coords, endPts, flags = self.getCoordinates(glyfTable, round=otRound)
            self.xMin, self.yMin, self.xMax, self.yMax = coords.calcIntBounds()
        except NotImplementedError:
            pass

    def tryRecalcBoundsComposite(self, glyfTable, *, boundsDone=None):
        """Try recalculating the bounds of a composite glyph that has
        certain constrained properties. Namely, none of the components
        have a transform other than an integer translate, and none
        uses the anchor points.

        Each glyph object stores its bounding box in the
        ``xMin``/``yMin``/``xMax``/``yMax`` attributes. These bounds must be
        recomputed when the ``coordinates`` change. The ``table__g_l_y_f`` bounds
        must be provided to resolve component bounds.

        Return True if bounds were calculated, False otherwise.
        """
        for compo in self.components:
            if not compo._hasOnlyIntegerTranslate():
                return False

        # All components are untransformed and have an integer x/y translate
        bounds = None
        for compo in self.components:
            glyphName = compo.glyphName
            g = glyfTable[glyphName]

            if boundsDone is None or glyphName not in boundsDone:
                g.recalcBounds(glyfTable, boundsDone=boundsDone)
                if boundsDone is not None:
                    boundsDone.add(glyphName)
            # empty components shouldn't update the bounds of the parent glyph
            if g.yMin == g.yMax and g.xMin == g.xMax:
                continue

            x, y = compo.x, compo.y
            bounds = updateBounds(bounds, (g.xMin + x, g.yMin + y))
            bounds = updateBounds(bounds, (g.xMax + x, g.yMax + y))

        if bounds is None:
            bounds = (0, 0, 0, 0)
        self.xMin, self.yMin, self.xMax, self.yMax = bounds
        return True

    def isComposite(self):
        """Test whether a glyph has components"""
        if hasattr(self, "data"):
            return struct.unpack(">h", self.data[:2])[0] == -1 if self.data else False
        else:
            return self.numberOfContours == -1

    def getCoordinates(self, glyfTable, *, round=noRound):
        """Return the coordinates, end points and flags

        This method returns three values: A :py:class:`GlyphCoordinates` object,
        a list of the indexes of the final points of each contour (allowing you
        to split up the coordinates list into contours) and a list of flags.

        On simple glyphs, this method returns information from the glyph's own
        contours; on composite glyphs, it "flattens" all components recursively
        to return a list of coordinates representing all the components involved
        in the glyph.

        To interpret the flags for each point, see the "Simple Glyph Flags"
        section of the `glyf table specification <https://docs.microsoft.com/en-us/typography/opentype/spec/glyf#simple-glyph-description>`.
        """

        if self.numberOfContours > 0:
            return self.coordinates, self.endPtsOfContours, self.flags
        elif self.isComposite():
            # it's a composite
            allCoords = GlyphCoordinates()
            allFlags = bytearray()
            allEndPts = []
            for compo in self.components:
                g = glyfTable[compo.glyphName]
                try:
                    coordinates, endPts, flags = g.getCoordinates(
                        glyfTable, round=round
                    )
                except RecursionError:
                    raise ttLib.TTLibError(
                        "glyph '%s' contains a recursive component reference"
                        % compo.glyphName
                    )
                coordinates = GlyphCoordinates(coordinates)
                # if asked to round e.g. while computing bboxes, it's important we
                # do it immediately before a component transform is applied to a
                # simple glyph's coordinates in case these might still contain floats;
                # however, if the referenced component glyph is another composite, we
                # must not round here but only at the end, after all the nested
                # transforms have been applied, or else rounding errors will compound.
                if round is not noRound and g.numberOfContours > 0:
                    coordinates.toInt(round=round)
                if hasattr(compo, "firstPt"):
                    # component uses two reference points: we apply the transform _before_
                    # computing the offset between the points
                    if hasattr(compo, "transform"):
                        coordinates.transform(compo.transform)
                    x1, y1 = allCoords[compo.firstPt]
                    x2, y2 = coordinates[compo.secondPt]
                    move = x1 - x2, y1 - y2
                    coordinates.translate(move)
                else:
                    # component uses XY offsets
                    move = compo.x, compo.y
                    if not hasattr(compo, "transform"):
                        coordinates.translate(move)
                    else:
                        apple_way = compo.flags & SCALED_COMPONENT_OFFSET
                        ms_way = compo.flags & UNSCALED_COMPONENT_OFFSET
                        assert not (apple_way and ms_way)
                        if not (apple_way or ms_way):
                            scale_component_offset = (
                                SCALE_COMPONENT_OFFSET_DEFAULT  # see top of this file
                            )
                        else:
                            scale_component_offset = apple_way
                        if scale_component_offset:
                            # the Apple way: first move, then scale (ie. scale the component offset)
                            coordinates.translate(move)
                            coordinates.transform(compo.transform)
                        else:
                            # the MS way: first scale, then move
                            coordinates.transform(compo.transform)
                            coordinates.translate(move)
                offset = len(allCoords)
                allEndPts.extend(e + offset for e in endPts)
                allCoords.extend(coordinates)
                allFlags.extend(flags)
            return allCoords, allEndPts, allFlags
        else:
            return GlyphCoordinates(), [], bytearray()

    def getComponentNames(self, glyfTable):
        """Returns a list of names of component glyphs used in this glyph

        This method can be used on simple glyphs (in which case it returns an
        empty list) or composite glyphs.
        """
        if not hasattr(self, "data"):
            if self.isComposite():
                return [c.glyphName for c in self.components]
            else:
                return []

        # Extract components without expanding glyph

        if not self.data or struct.unpack(">h", self.data[:2])[0] >= 0:
            return []  # Not composite

        data = self.data
        i = 10
        components = []
        more = 1
        while more:
            flags, glyphID = struct.unpack(">HH", data[i : i + 4])
            i += 4
            flags = int(flags)
            components.append(glyfTable.getGlyphName(int(glyphID)))

            if flags & ARG_1_AND_2_ARE_WORDS:
                i += 4
            else:
                i += 2
            if flags & WE_HAVE_A_SCALE:
                i += 2
            elif flags & WE_HAVE_AN_X_AND_Y_SCALE:
                i += 4
            elif flags & WE_HAVE_A_TWO_BY_TWO:
                i += 8
            more = flags & MORE_COMPONENTS

        return components

    def trim(self, remove_hinting=False):
        """Remove padding and, if requested, hinting, from a glyph.
        This works on both expanded and compacted glyphs, without
        expanding it."""
        if not hasattr(self, "data"):
            if remove_hinting:
                if self.isComposite():
                    if hasattr(self, "program"):
                        del self.program
                else:
                    self.program = ttProgram.Program()
                    self.program.fromBytecode([])
            # No padding to trim.
            return
        if not self.data:
            return
        numContours = struct.unpack(">h", self.data[:2])[0]
        data = bytearray(self.data)
        i = 10
        if numContours >= 0:
            i += 2 * numContours  # endPtsOfContours
            nCoordinates = ((data[i - 2] << 8) | data[i - 1]) + 1
            instructionLen = (data[i] << 8) | data[i + 1]
            if remove_hinting:
                # Zero instruction length
                data[i] = data[i + 1] = 0
                i += 2
                if instructionLen:
                    # Splice it out
                    data = data[:i] + data[i + instructionLen :]
                instructionLen = 0
            else:
                i += 2 + instructionLen

            coordBytes = 0
            j = 0
            while True:
                flag = data[i]
                i = i + 1
                repeat = 1
                if flag & flagRepeat:
                    repeat = data[i] + 1
                    i = i + 1
                xBytes = yBytes = 0
                if flag & flagXShort:
                    xBytes = 1
                elif not (flag & flagXsame):
                    xBytes = 2
                if flag & flagYShort:
                    yBytes = 1
                elif not (flag & flagYsame):
                    yBytes = 2
                coordBytes += (xBytes + yBytes) * repeat
                j += repeat
                if j >= nCoordinates:
                    break
            assert j == nCoordinates, "bad glyph flags"
            i += coordBytes
            # Remove padding
            data = data[:i]
        elif self.isComposite():
            more = 1
            we_have_instructions = False
            while more:
                flags = (data[i] << 8) | data[i + 1]
                if remove_hinting:
                    flags &= ~WE_HAVE_INSTRUCTIONS
                if flags & WE_HAVE_INSTRUCTIONS:
                    we_have_instructions = True
                data[i + 0] = flags >> 8
                data[i + 1] = flags & 0xFF
                i += 4
                flags = int(flags)

                if flags & ARG_1_AND_2_ARE_WORDS:
                    i += 4
                else:
                    i += 2
                if flags & WE_HAVE_A_SCALE:
                    i += 2
                elif flags & WE_HAVE_AN_X_AND_Y_SCALE:
                    i += 4
                elif flags & WE_HAVE_A_TWO_BY_TWO:
                    i += 8
                more = flags & MORE_COMPONENTS
            if we_have_instructions:
                instructionLen = (data[i] << 8) | data[i + 1]
                i += 2 + instructionLen
            # Remove padding
            data = data[:i]

        self.data = data

    def removeHinting(self):
        """Removes TrueType hinting instructions from the glyph."""
        self.trim(remove_hinting=True)

    def draw(self, pen, glyfTable, offset=0):
        """Draws the glyph using the supplied pen object.

        Arguments:
                pen: An object conforming to the pen protocol.
                glyfTable: A :py:class:`table__g_l_y_f` object, to resolve components.
                offset (int): A horizontal offset. If provided, all coordinates are
                        translated by this offset.
        """

        if self.isComposite():
            for component in self.components:
                glyphName, transform = component.getComponentInfo()
                pen.addComponent(glyphName, transform)
            return

        self.expand(glyfTable)
        coordinates, endPts, flags = self.getCoordinates(glyfTable)
        if offset:
            coordinates = coordinates.copy()
            coordinates.translate((offset, 0))
        start = 0
        maybeInt = lambda v: int(v) if v == int(v) else v
        for end in endPts:
            end = end + 1
            contour = coordinates[start:end]
            cFlags = [flagOnCurve & f for f in flags[start:end]]
            cuFlags = [flagCubic & f for f in flags[start:end]]
            start = end
            if 1 not in cFlags:
                assert all(cuFlags) or not any(cuFlags)
                cubic = all(cuFlags)
                if cubic:
                    count = len(contour)
                    assert count % 2 == 0, "Odd number of cubic off-curves undefined"
                    l = contour[-1]
                    f = contour[0]
                    p0 = (maybeInt((l[0] + f[0]) * 0.5), maybeInt((l[1] + f[1]) * 0.5))
                    pen.moveTo(p0)
                    for i in range(0, count, 2):
                        p1 = contour[i]
                        p2 = contour[i + 1]
                        p4 = contour[i + 2 if i + 2 < count else 0]
                        p3 = (
                            maybeInt((p2[0] + p4[0]) * 0.5),
                            maybeInt((p2[1] + p4[1]) * 0.5),
                        )
                        pen.curveTo(p1, p2, p3)
                else:
                    # There is not a single on-curve point on the curve,
                    # use pen.qCurveTo's special case by specifying None
                    # as the on-curve point.
                    contour.append(None)
                    pen.qCurveTo(*contour)
            else:
                # Shuffle the points so that the contour is guaranteed
                # to *end* in an on-curve point, which we'll use for
                # the moveTo.
                firstOnCurve = cFlags.index(1) + 1
                contour = contour[firstOnCurve:] + contour[:firstOnCurve]
                cFlags = cFlags[firstOnCurve:] + cFlags[:firstOnCurve]
                cuFlags = cuFlags[firstOnCurve:] + cuFlags[:firstOnCurve]
                pen.moveTo(contour[-1])
                while contour:
                    nextOnCurve = cFlags.index(1) + 1
                    if nextOnCurve == 1:
                        # Skip a final lineTo(), as it is implied by
                        # pen.closePath()
                        if len(contour) > 1:
                            pen.lineTo(contour[0])
                    else:
                        cubicFlags = [f for f in cuFlags[: nextOnCurve - 1]]
                        assert all(cubicFlags) or not any(cubicFlags)
                        cubic = any(cubicFlags)
                        if cubic:
                            assert all(
                                cubicFlags
                            ), "Mixed cubic and quadratic segment undefined"

                            count = nextOnCurve
                            assert (
                                count >= 3
                            ), "At least two cubic off-curve points required"
                            assert (
                                count - 1
                            ) % 2 == 0, "Odd number of cubic off-curves undefined"
                            for i in range(0, count - 3, 2):
                                p1 = contour[i]
                                p2 = contour[i + 1]
                                p4 = contour[i + 2]
                                p3 = (
                                    maybeInt((p2[0] + p4[0]) * 0.5),
                                    maybeInt((p2[1] + p4[1]) * 0.5),
                                )
                                lastOnCurve = p3
                                pen.curveTo(p1, p2, p3)
                            pen.curveTo(*contour[count - 3 : count])
                        else:
                            pen.qCurveTo(*contour[:nextOnCurve])
                    contour = contour[nextOnCurve:]
                    cFlags = cFlags[nextOnCurve:]
                    cuFlags = cuFlags[nextOnCurve:]
            pen.closePath()

    def drawPoints(self, pen, glyfTable, offset=0):
        """Draw the glyph using the supplied pointPen. As opposed to Glyph.draw(),
        this will not change the point indices.
        """

        if self.isComposite():
            for component in self.components:
                glyphName, transform = component.getComponentInfo()
                pen.addComponent(glyphName, transform)
            return

        coordinates, endPts, flags = self.getCoordinates(glyfTable)
        if offset:
            coordinates = coordinates.copy()
            coordinates.translate((offset, 0))
        start = 0
        for end in endPts:
            end = end + 1
            contour = coordinates[start:end]
            cFlags = flags[start:end]
            start = end
            pen.beginPath()
            # Start with the appropriate segment type based on the final segment

            if cFlags[-1] & flagOnCurve:
                segmentType = "line"
            elif cFlags[-1] & flagCubic:
                segmentType = "curve"
            else:
                segmentType = "qcurve"
            for i, pt in enumerate(contour):
                if cFlags[i] & flagOnCurve:
                    pen.addPoint(pt, segmentType=segmentType)
                    segmentType = "line"
                else:
                    pen.addPoint(pt)
                    segmentType = "curve" if cFlags[i] & flagCubic else "qcurve"
            pen.endPath()

    def __eq__(self, other):
        if type(self) != type(other):
            return NotImplemented
        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        result = self.__eq__(other)
        return result if result is NotImplemented else not result


# Vector.__round__ uses the built-in (Banker's) `round` but we want
# to use otRound below
_roundv = partial(Vector.__round__, round=otRound)


def _is_mid_point(p0: tuple, p1: tuple, p2: tuple) -> bool:
    # True if p1 is in the middle of p0 and p2, either before or after rounding
    p0 = Vector(p0)
    p1 = Vector(p1)
    p2 = Vector(p2)
    return ((p0 + p2) * 0.5).isclose(p1) or _roundv(p0) + _roundv(p2) == _roundv(p1) * 2


def dropImpliedOnCurvePoints(*interpolatable_glyphs: Glyph) -> Set[int]:
    """Drop impliable on-curve points from the (simple) glyph or glyphs.

    In TrueType glyf outlines, on-curve points can be implied when they are located at
    the midpoint of the line connecting two consecutive off-curve points.

    If more than one glyphs are passed, these are assumed to be interpolatable masters
    of the same glyph impliable, and thus only the on-curve points that are impliable
    for all of them will actually be implied.
    Composite glyphs or empty glyphs are skipped, only simple glyphs with 1 or more
    contours are considered.
    The input glyph(s) is/are modified in-place.

    Args:
        interpolatable_glyphs: The glyph or glyphs to modify in-place.

    Returns:
        The set of point indices that were dropped if any.

    Raises:
        ValueError if simple glyphs are not in fact interpolatable because they have
        different point flags or number of contours.

    Reference:
    https://developer.apple.com/fonts/TrueType-Reference-Manual/RM01/Chap1.html
    """
    staticAttributes = SimpleNamespace(
        numberOfContours=None, flags=None, endPtsOfContours=None
    )
    drop = None
    simple_glyphs = []
    for i, glyph in enumerate(interpolatable_glyphs):
        if glyph.numberOfContours < 1:
            # ignore composite or empty glyphs
            continue

        for attr in staticAttributes.__dict__:
            expected = getattr(staticAttributes, attr)
            found = getattr(glyph, attr)
            if expected is None:
                setattr(staticAttributes, attr, found)
            elif expected != found:
                raise ValueError(
                    f"Incompatible {attr} for glyph at master index {i}: "
                    f"expected {expected}, found {found}"
                )

        may_drop = set()
        start = 0
        coords = glyph.coordinates
        flags = staticAttributes.flags
        endPtsOfContours = staticAttributes.endPtsOfContours
        for last in endPtsOfContours:
            for i in range(start, last + 1):
                if not (flags[i] & flagOnCurve):
                    continue
                prv = i - 1 if i > start else last
                nxt = i + 1 if i < last else start
                if (flags[prv] & flagOnCurve) or flags[prv] != flags[nxt]:
                    continue
                # we may drop the ith on-curve if halfway between previous/next off-curves
                if not _is_mid_point(coords[prv], coords[i], coords[nxt]):
                    continue

                may_drop.add(i)
            start = last + 1
        # we only want to drop if ALL interpolatable glyphs have the same implied oncurves
        if drop is None:
            drop = may_drop
        else:
            drop.intersection_update(may_drop)

        simple_glyphs.append(glyph)

    if drop:
        # Do the actual dropping
        flags = staticAttributes.flags
        assert flags is not None
        newFlags = array.array(
            "B", (flags[i] for i in range(len(flags)) if i not in drop)
        )

        endPts = staticAttributes.endPtsOfContours
        assert endPts is not None
        newEndPts = []
        i = 0
        delta = 0
        for d in sorted(drop):
            while d > endPts[i]:
                newEndPts.append(endPts[i] - delta)
                i += 1
            delta += 1
        while i < len(endPts):
            newEndPts.append(endPts[i] - delta)
            i += 1

        for glyph in simple_glyphs:
            coords = glyph.coordinates
            glyph.coordinates = GlyphCoordinates(
                coords[i] for i in range(len(coords)) if i not in drop
            )
            glyph.flags = newFlags
            glyph.endPtsOfContours = newEndPts

    return drop if drop is not None else set()


class GlyphComponent(object):
    """Represents a component within a composite glyph.

    The component is represented internally with four attributes: ``glyphName``,
    ``x``, ``y`` and ``transform``. If there is no "two-by-two" matrix (i.e
    no scaling, reflection, or rotation; only translation), the ``transform``
    attribute is not present.
    """

    # The above documentation is not *completely* true, but is *true enough* because
    # the rare firstPt/lastPt attributes are not totally supported and nobody seems to
    # mind - see below.

    def __init__(self):
        pass

    def getComponentInfo(self):
        """Return information about the component

        This method returns a tuple of two values: the glyph name of the component's
        base glyph, and a transformation matrix. As opposed to accessing the attributes
        directly, ``getComponentInfo`` always returns a six-element tuple of the
        component's transformation matrix, even when the two-by-two ``.transform``
        matrix is not present.
        """
        # XXX Ignoring self.firstPt & self.lastpt for now: I need to implement
        # something equivalent in fontTools.objects.glyph (I'd rather not
        # convert it to an absolute offset, since it is valuable information).
        # This method will now raise "AttributeError: x" on glyphs that use
        # this TT feature.
        if hasattr(self, "transform"):
            [[xx, xy], [yx, yy]] = self.transform
            trans = (xx, xy, yx, yy, self.x, self.y)
        else:
            trans = (1, 0, 0, 1, self.x, self.y)
        return self.glyphName, trans

    def decompile(self, data, glyfTable):
        flags, glyphID = struct.unpack(">HH", data[:4])
        self.flags = int(flags)
        glyphID = int(glyphID)
        self.glyphName = glyfTable.getGlyphName(int(glyphID))
        data = data[4:]

        if self.flags & ARG_1_AND_2_ARE_WORDS:
            if self.flags & ARGS_ARE_XY_VALUES:
                self.x, self.y = struct.unpack(">hh", data[:4])
            else:
                x, y = struct.unpack(">HH", data[:4])
                self.firstPt, self.secondPt = int(x), int(y)
            data = data[4:]
        else:
            if self.flags & ARGS_ARE_XY_VALUES:
                self.x, self.y = struct.unpack(">bb", data[:2])
            else:
                x, y = struct.unpack(">BB", data[:2])
                self.firstPt, self.secondPt = int(x), int(y)
            data = data[2:]

        if self.flags & WE_HAVE_A_SCALE:
            (scale,) = struct.unpack(">h", data[:2])
            self.transform = [
                [fi2fl(scale, 14), 0],
                [0, fi2fl(scale, 14)],
            ]  # fixed 2.14
            data = data[2:]
        elif self.flags & WE_HAVE_AN_X_AND_Y_SCALE:
            xscale, yscale = struct.unpack(">hh", data[:4])
            self.transform = [
                [fi2fl(xscale, 14), 0],
                [0, fi2fl(yscale, 14)],
            ]  # fixed 2.14
            data = data[4:]
        elif self.flags & WE_HAVE_A_TWO_BY_TWO:
            (xscale, scale01, scale10, yscale) = struct.unpack(">hhhh", data[:8])
            self.transform = [
                [fi2fl(xscale, 14), fi2fl(scale01, 14)],
                [fi2fl(scale10, 14), fi2fl(yscale, 14)],
            ]  # fixed 2.14
            data = data[8:]
        more = self.flags & MORE_COMPONENTS
        haveInstructions = self.flags & WE_HAVE_INSTRUCTIONS
        self.flags = self.flags & (
            ROUND_XY_TO_GRID
            | USE_MY_METRICS
            | SCALED_COMPONENT_OFFSET
            | UNSCALED_COMPONENT_OFFSET
            | NON_OVERLAPPING
            | OVERLAP_COMPOUND
        )
        return more, haveInstructions, data

    def compile(self, more, haveInstructions, glyfTable):
        data = b""

        # reset all flags we will calculate ourselves
        flags = self.flags & (
            ROUND_XY_TO_GRID
            | USE_MY_METRICS
            | SCALED_COMPONENT_OFFSET
            | UNSCALED_COMPONENT_OFFSET
            | NON_OVERLAPPING
            | OVERLAP_COMPOUND
        )
        if more:
            flags = flags | MORE_COMPONENTS
        if haveInstructions:
            flags = flags | WE_HAVE_INSTRUCTIONS

        if hasattr(self, "firstPt"):
            if (0 <= self.firstPt <= 255) and (0 <= self.secondPt <= 255):
                data = data + struct.pack(">BB", self.firstPt, self.secondPt)
            else:
                data = data + struct.pack(">HH", self.firstPt, self.secondPt)
                flags = flags | ARG_1_AND_2_ARE_WORDS
        else:
            x = otRound(self.x)
            y = otRound(self.y)
            flags = flags | ARGS_ARE_XY_VALUES
            if (-128 <= x <= 127) and (-128 <= y <= 127):
                data = data + struct.pack(">bb", x, y)
            else:
                data = data + struct.pack(">hh", x, y)
                flags = flags | ARG_1_AND_2_ARE_WORDS

        if hasattr(self, "transform"):
            transform = [[fl2fi(x, 14) for x in row] for row in self.transform]
            if transform[0][1] or transform[1][0]:
                flags = flags | WE_HAVE_A_TWO_BY_TWO
                data = data + struct.pack(
                    ">hhhh",
                    transform[0][0],
                    transform[0][1],
                    transform[1][0],
                    transform[1][1],
                )
            elif transform[0][0] != transform[1][1]:
                flags = flags | WE_HAVE_AN_X_AND_Y_SCALE
                data = data + struct.pack(">hh", transform[0][0], transform[1][1])
            else:
                flags = flags | WE_HAVE_A_SCALE
                data = data + struct.pack(">h", transform[0][0])

        glyphID = glyfTable.getGlyphID(self.glyphName)
        return struct.pack(">HH", flags, glyphID) + data

    def toXML(self, writer, ttFont):
        attrs = [("glyphName", self.glyphName)]
        if not hasattr(self, "firstPt"):
            attrs = attrs + [("x", self.x), ("y", self.y)]
        else:
            attrs = attrs + [("firstPt", self.firstPt), ("secondPt", self.secondPt)]

        if hasattr(self, "transform"):
            transform = self.transform
            if transform[0][1] or transform[1][0]:
                attrs = attrs + [
                    ("scalex", fl2str(transform[0][0], 14)),
                    ("scale01", fl2str(transform[0][1], 14)),
                    ("scale10", fl2str(transform[1][0], 14)),
                    ("scaley", fl2str(transform[1][1], 14)),
                ]
            elif transform[0][0] != transform[1][1]:
                attrs = attrs + [
                    ("scalex", fl2str(transform[0][0], 14)),
                    ("scaley", fl2str(transform[1][1], 14)),
                ]
            else:
                attrs = attrs + [("scale", fl2str(transform[0][0], 14))]
        attrs = attrs + [("flags", hex(self.flags))]
        writer.simpletag("component", attrs)
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        self.glyphName = attrs["glyphName"]
        if "firstPt" in attrs:
            self.firstPt = safeEval(attrs["firstPt"])
            self.secondPt = safeEval(attrs["secondPt"])
        else:
            self.x = safeEval(attrs["x"])
            self.y = safeEval(attrs["y"])
        if "scale01" in attrs:
            scalex = str2fl(attrs["scalex"], 14)
            scale01 = str2fl(attrs["scale01"], 14)
            scale10 = str2fl(attrs["scale10"], 14)
            scaley = str2fl(attrs["scaley"], 14)
            self.transform = [[scalex, scale01], [scale10, scaley]]
        elif "scalex" in attrs:
            scalex = str2fl(attrs["scalex"], 14)
            scaley = str2fl(attrs["scaley"], 14)
            self.transform = [[scalex, 0], [0, scaley]]
        elif "scale" in attrs:
            scale = str2fl(attrs["scale"], 14)
            self.transform = [[scale, 0], [0, scale]]
        self.flags = safeEval(attrs["flags"])

    def __eq__(self, other):
        if type(self) != type(other):
            return NotImplemented
        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    def _hasOnlyIntegerTranslate(self):
        """Return True if it's a 'simple' component.

        That is, it has no anchor points and no transform other than integer translate.
        """
        return (
            not hasattr(self, "firstPt")
            and not hasattr(self, "transform")
            and float(self.x).is_integer()
            and float(self.y).is_integer()
        )


class GlyphCoordinates(object):
    """A list of glyph coordinates.

    Unlike an ordinary list, this is a numpy-like matrix object which supports
    matrix addition, scalar multiplication and other operations described below.
    """

    def __init__(self, iterable=[]):
        self._a = array.array("d")
        self.extend(iterable)

    @property
    def array(self):
        """Returns the underlying array of coordinates"""
        return self._a

    @staticmethod
    def zeros(count):
        """Creates a new ``GlyphCoordinates`` object with all coordinates set to (0,0)"""
        g = GlyphCoordinates()
        g._a.frombytes(bytes(count * 2 * g._a.itemsize))
        return g

    def copy(self):
        """Creates a new ``GlyphCoordinates`` object which is a copy of the current one."""
        c = GlyphCoordinates()
        c._a.extend(self._a)
        return c

    def __len__(self):
        """Returns the number of coordinates in the array."""
        return len(self._a) // 2

    def __getitem__(self, k):
        """Returns a two element tuple (x,y)"""
        a = self._a
        if isinstance(k, slice):
            indices = range(*k.indices(len(self)))
            # Instead of calling ourselves recursively, duplicate code; faster
            ret = []
            for k in indices:
                x = a[2 * k]
                y = a[2 * k + 1]
                ret.append(
                    (int(x) if x.is_integer() else x, int(y) if y.is_integer() else y)
                )
            return ret
        x = a[2 * k]
        y = a[2 * k + 1]
        return (int(x) if x.is_integer() else x, int(y) if y.is_integer() else y)

    def __setitem__(self, k, v):
        """Sets a point's coordinates to a two element tuple (x,y)"""
        if isinstance(k, slice):
            indices = range(*k.indices(len(self)))
            # XXX This only works if len(v) == len(indices)
            for j, i in enumerate(indices):
                self[i] = v[j]
            return
        self._a[2 * k], self._a[2 * k + 1] = v

    def __delitem__(self, i):
        """Removes a point from the list"""
        i = (2 * i) % len(self._a)
        del self._a[i]
        del self._a[i]

    def __repr__(self):
        return "GlyphCoordinates([" + ",".join(str(c) for c in self) + "])"

    def append(self, p):
        self._a.extend(tuple(p))

    def extend(self, iterable):
        for p in iterable:
            self._a.extend(p)

    def toInt(self, *, round=otRound):
        if round is noRound:
            return
        a = self._a
        for i, value in enumerate(a):
            a[i] = round(value)

    def calcBounds(self):
        a = self._a
        if not a:
            return 0, 0, 0, 0
        xs = a[0::2]
        ys = a[1::2]
        return min(xs), min(ys), max(xs), max(ys)

    def calcIntBounds(self, round=otRound):
        return tuple(round(v) for v in self.calcBounds())

    def relativeToAbsolute(self):
        a = self._a
        x, y = 0, 0
        for i in range(0, len(a), 2):
            a[i] = x = a[i] + x
            a[i + 1] = y = a[i + 1] + y

    def absoluteToRelative(self):
        a = self._a
        x, y = 0, 0
        for i in range(0, len(a), 2):
            nx = a[i]
            ny = a[i + 1]
            a[i] = nx - x
            a[i + 1] = ny - y
            x = nx
            y = ny

    def translate(self, p):
        """
        >>> GlyphCoordinates([(1,2)]).translate((.5,0))
        """
        x, y = p
        if x == 0 and y == 0:
            return
        a = self._a
        for i in range(0, len(a), 2):
            a[i] += x
            a[i + 1] += y

    def scale(self, p):
        """
        >>> GlyphCoordinates([(1,2)]).scale((.5,0))
        """
        x, y = p
        if x == 1 and y == 1:
            return
        a = self._a
        for i in range(0, len(a), 2):
            a[i] *= x
            a[i + 1] *= y

    def transform(self, t):
        """
        >>> GlyphCoordinates([(1,2)]).transform(((.5,0),(.2,.5)))
        """
        a = self._a
        for i in range(0, len(a), 2):
            x = a[i]
            y = a[i + 1]
            px = x * t[0][0] + y * t[1][0]
            py = x * t[0][1] + y * t[1][1]
            a[i] = px
            a[i + 1] = py

    def __eq__(self, other):
        """
        >>> g = GlyphCoordinates([(1,2)])
        >>> g2 = GlyphCoordinates([(1.0,2)])
        >>> g3 = GlyphCoordinates([(1.5,2)])
        >>> g == g2
        True
        >>> g == g3
        False
        >>> g2 == g3
        False
        """
        if type(self) != type(other):
            return NotImplemented
        return self._a == other._a

    def __ne__(self, other):
        """
        >>> g = GlyphCoordinates([(1,2)])
        >>> g2 = GlyphCoordinates([(1.0,2)])
        >>> g3 = GlyphCoordinates([(1.5,2)])
        >>> g != g2
        False
        >>> g != g3
        True
        >>> g2 != g3
        True
        """
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    # Math operations

    def __pos__(self):
        """
        >>> g = GlyphCoordinates([(1,2)])
        >>> g
        GlyphCoordinates([(1, 2)])
        >>> g2 = +g
        >>> g2
        GlyphCoordinates([(1, 2)])
        >>> g2.translate((1,0))
        >>> g2
        GlyphCoordinates([(2, 2)])
        >>> g
        GlyphCoordinates([(1, 2)])
        """
        return self.copy()

    def __neg__(self):
        """
        >>> g = GlyphCoordinates([(1,2)])
        >>> g
        GlyphCoordinates([(1, 2)])
        >>> g2 = -g
        >>> g2
        GlyphCoordinates([(-1, -2)])
        >>> g
        GlyphCoordinates([(1, 2)])
        """
        r = self.copy()
        a = r._a
        for i, value in enumerate(a):
            a[i] = -value
        return r

    def __round__(self, *, round=otRound):
        r = self.copy()
        r.toInt(round=round)
        return r

    def __add__(self, other):
        return self.copy().__iadd__(other)

    def __sub__(self, other):
        return self.copy().__isub__(other)

    def __mul__(self, other):
        return self.copy().__imul__(other)

    def __truediv__(self, other):
        return self.copy().__itruediv__(other)

    __radd__ = __add__
    __rmul__ = __mul__

    def __rsub__(self, other):
        return other + (-self)

    def __iadd__(self, other):
        """
        >>> g = GlyphCoordinates([(1,2)])
        >>> g += (.5,0)
        >>> g
        GlyphCoordinates([(1.5, 2)])
        >>> g2 = GlyphCoordinates([(3,4)])
        >>> g += g2
        >>> g
        GlyphCoordinates([(4.5, 6)])
        """
        if isinstance(other, tuple):
            assert len(other) == 2
            self.translate(other)
            return self
        if isinstance(other, GlyphCoordinates):
            other = other._a
            a = self._a
            assert len(a) == len(other)
            for i, value in enumerate(other):
                a[i] += value
            return self
        return NotImplemented

    def __isub__(self, other):
        """
        >>> g = GlyphCoordinates([(1,2)])
        >>> g -= (.5,0)
        >>> g
        GlyphCoordinates([(0.5, 2)])
        >>> g2 = GlyphCoordinates([(3,4)])
        >>> g -= g2
        >>> g
        GlyphCoordinates([(-2.5, -2)])
        """
        if isinstance(other, tuple):
            assert len(other) == 2
            self.translate((-other[0], -other[1]))
            return self
        if isinstance(other, GlyphCoordinates):
            other = other._a
            a = self._a
            assert len(a) == len(other)
            for i, value in enumerate(other):
                a[i] -= value
            return self
        return NotImplemented

    def __imul__(self, other):
        """
        >>> g = GlyphCoordinates([(1,2)])
        >>> g *= (2,.5)
        >>> g *= 2
        >>> g
        GlyphCoordinates([(4, 2)])
        >>> g = GlyphCoordinates([(1,2)])
        >>> g *= 2
        >>> g
        GlyphCoordinates([(2, 4)])
        """
        if isinstance(other, tuple):
            assert len(other) == 2
            self.scale(other)
            return self
        if isinstance(other, Number):
            if other == 1:
                return self
            a = self._a
            for i in range(len(a)):
                a[i] *= other
            return self
        return NotImplemented

    def __itruediv__(self, other):
        """
        >>> g = GlyphCoordinates([(1,3)])
        >>> g /= (.5,1.5)
        >>> g /= 2
        >>> g
        GlyphCoordinates([(1, 1)])
        """
        if isinstance(other, Number):
            other = (other, other)
        if isinstance(other, tuple):
            if other == (1, 1):
                return self
            assert len(other) == 2
            self.scale((1.0 / other[0], 1.0 / other[1]))
            return self
        return NotImplemented

    def __bool__(self):
        """
        >>> g = GlyphCoordinates([])
        >>> bool(g)
        False
        >>> g = GlyphCoordinates([(0,0), (0.,0)])
        >>> bool(g)
        True
        >>> g = GlyphCoordinates([(0,0), (1,0)])
        >>> bool(g)
        True
        >>> g = GlyphCoordinates([(0,.5), (0,0)])
        >>> bool(g)
        True
        """
        return bool(self._a)

    __nonzero__ = __bool__


if __name__ == "__main__":
    import doctest, sys

    sys.exit(doctest.testmod().failed)
