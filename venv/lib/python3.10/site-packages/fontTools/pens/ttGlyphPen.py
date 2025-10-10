from array import array
from typing import Any, Callable, Dict, Optional, Tuple
from fontTools.misc.fixedTools import MAX_F2DOT14, floatToFixedToFloat
from fontTools.misc.loggingTools import LogMixin
from fontTools.pens.pointPen import AbstractPointPen
from fontTools.misc.roundTools import otRound
from fontTools.pens.basePen import LoggingPen, PenError
from fontTools.pens.transformPen import TransformPen, TransformPointPen
from fontTools.ttLib.tables import ttProgram
from fontTools.ttLib.tables._g_l_y_f import flagOnCurve, flagCubic
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.ttLib.tables._g_l_y_f import GlyphComponent
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ttLib.tables._g_l_y_f import dropImpliedOnCurvePoints
import math


__all__ = ["TTGlyphPen", "TTGlyphPointPen"]


class _TTGlyphBasePen:
    def __init__(
        self,
        glyphSet: Optional[Dict[str, Any]],
        handleOverflowingTransforms: bool = True,
    ) -> None:
        """
        Construct a new pen.

        Args:
            glyphSet (Dict[str, Any]): A glyphset object, used to resolve components.
            handleOverflowingTransforms (bool): See below.

        If ``handleOverflowingTransforms`` is True, the components' transform values
        are checked that they don't overflow the limits of a F2Dot14 number:
        -2.0 <= v < +2.0. If any transform value exceeds these, the composite
        glyph is decomposed.

        An exception to this rule is done for values that are very close to +2.0
        (both for consistency with the -2.0 case, and for the relative frequency
        these occur in real fonts). When almost +2.0 values occur (and all other
        values are within the range -2.0 <= x <= +2.0), they are clamped to the
        maximum positive value that can still be encoded as an F2Dot14: i.e.
        1.99993896484375.

        If False, no check is done and all components are translated unmodified
        into the glyf table, followed by an inevitable ``struct.error`` once an
        attempt is made to compile them.

        If both contours and components are present in a glyph, the components
        are decomposed.
        """
        self.glyphSet = glyphSet
        self.handleOverflowingTransforms = handleOverflowingTransforms
        self.init()

    def _decompose(
        self,
        glyphName: str,
        transformation: Tuple[float, float, float, float, float, float],
    ):
        tpen = self.transformPen(self, transformation)
        getattr(self.glyphSet[glyphName], self.drawMethod)(tpen)

    def _isClosed(self):
        """
        Check if the current path is closed.
        """
        raise NotImplementedError

    def init(self) -> None:
        self.points = []
        self.endPts = []
        self.types = []
        self.components = []

    def addComponent(
        self,
        baseGlyphName: str,
        transformation: Tuple[float, float, float, float, float, float],
        identifier: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        Add a sub glyph.
        """
        self.components.append((baseGlyphName, transformation))

    def _buildComponents(self, componentFlags):
        if self.handleOverflowingTransforms:
            # we can't encode transform values > 2 or < -2 in F2Dot14,
            # so we must decompose the glyph if any transform exceeds these
            overflowing = any(
                s > 2 or s < -2
                for (glyphName, transformation) in self.components
                for s in transformation[:4]
            )
        components = []
        for glyphName, transformation in self.components:
            if glyphName not in self.glyphSet:
                self.log.warning(f"skipped non-existing component '{glyphName}'")
                continue
            if self.points or (self.handleOverflowingTransforms and overflowing):
                # can't have both coordinates and components, so decompose
                self._decompose(glyphName, transformation)
                continue

            component = GlyphComponent()
            component.glyphName = glyphName
            component.x, component.y = (otRound(v) for v in transformation[4:])
            # quantize floats to F2Dot14 so we get same values as when decompiled
            # from a binary glyf table
            transformation = tuple(
                floatToFixedToFloat(v, 14) for v in transformation[:4]
            )
            if transformation != (1, 0, 0, 1):
                if self.handleOverflowingTransforms and any(
                    MAX_F2DOT14 < s <= 2 for s in transformation
                ):
                    # clamp values ~= +2.0 so we can keep the component
                    transformation = tuple(
                        MAX_F2DOT14 if MAX_F2DOT14 < s <= 2 else s
                        for s in transformation
                    )
                component.transform = (transformation[:2], transformation[2:])
            component.flags = componentFlags
            components.append(component)
        return components

    def glyph(
        self,
        componentFlags: int = 0x04,
        dropImpliedOnCurves: bool = False,
        *,
        round: Callable[[float], int] = otRound,
    ) -> Glyph:
        """
        Returns a :py:class:`~._g_l_y_f.Glyph` object representing the glyph.

        Args:
            componentFlags: Flags to use for component glyphs. (default: 0x04)

            dropImpliedOnCurves: Whether to remove implied-oncurve points. (default: False)
        """
        if not self._isClosed():
            raise PenError("Didn't close last contour.")
        components = self._buildComponents(componentFlags)

        glyph = Glyph()
        glyph.coordinates = GlyphCoordinates(self.points)
        glyph.endPtsOfContours = self.endPts
        glyph.flags = array("B", self.types)
        self.init()

        if components:
            # If both components and contours were present, they have by now
            # been decomposed by _buildComponents.
            glyph.components = components
            glyph.numberOfContours = -1
        else:
            glyph.numberOfContours = len(glyph.endPtsOfContours)
            glyph.program = ttProgram.Program()
            glyph.program.fromBytecode(b"")
            if dropImpliedOnCurves:
                dropImpliedOnCurvePoints(glyph)
            glyph.coordinates.toInt(round=round)

        return glyph


class TTGlyphPen(_TTGlyphBasePen, LoggingPen):
    """
    Pen used for drawing to a TrueType glyph.

    This pen can be used to construct or modify glyphs in a TrueType format
    font. After using the pen to draw, use the ``.glyph()`` method to retrieve
    a :py:class:`~._g_l_y_f.Glyph` object representing the glyph.
    """

    drawMethod = "draw"
    transformPen = TransformPen

    def __init__(
        self,
        glyphSet: Optional[Dict[str, Any]] = None,
        handleOverflowingTransforms: bool = True,
        outputImpliedClosingLine: bool = False,
    ) -> None:
        super().__init__(glyphSet, handleOverflowingTransforms)
        self.outputImpliedClosingLine = outputImpliedClosingLine

    def _addPoint(self, pt: Tuple[float, float], tp: int) -> None:
        self.points.append(pt)
        self.types.append(tp)

    def _popPoint(self) -> None:
        self.points.pop()
        self.types.pop()

    def _isClosed(self) -> bool:
        return (not self.points) or (
            self.endPts and self.endPts[-1] == len(self.points) - 1
        )

    def lineTo(self, pt: Tuple[float, float]) -> None:
        self._addPoint(pt, flagOnCurve)

    def moveTo(self, pt: Tuple[float, float]) -> None:
        if not self._isClosed():
            raise PenError('"move"-type point must begin a new contour.')
        self._addPoint(pt, flagOnCurve)

    def curveTo(self, *points) -> None:
        assert len(points) % 2 == 1
        for pt in points[:-1]:
            self._addPoint(pt, flagCubic)

        # last point is None if there are no on-curve points
        if points[-1] is not None:
            self._addPoint(points[-1], 1)

    def qCurveTo(self, *points) -> None:
        assert len(points) >= 1
        for pt in points[:-1]:
            self._addPoint(pt, 0)

        # last point is None if there are no on-curve points
        if points[-1] is not None:
            self._addPoint(points[-1], 1)

    def closePath(self) -> None:
        endPt = len(self.points) - 1

        # ignore anchors (one-point paths)
        if endPt == 0 or (self.endPts and endPt == self.endPts[-1] + 1):
            self._popPoint()
            return

        if not self.outputImpliedClosingLine:
            # if first and last point on this path are the same, remove last
            startPt = 0
            if self.endPts:
                startPt = self.endPts[-1] + 1
            if self.points[startPt] == self.points[endPt]:
                self._popPoint()
                endPt -= 1

        self.endPts.append(endPt)

    def endPath(self) -> None:
        # TrueType contours are always "closed"
        self.closePath()


class TTGlyphPointPen(_TTGlyphBasePen, LogMixin, AbstractPointPen):
    """
    Point pen used for drawing to a TrueType glyph.

    This pen can be used to construct or modify glyphs in a TrueType format
    font. After using the pen to draw, use the ``.glyph()`` method to retrieve
    a :py:class:`~._g_l_y_f.Glyph` object representing the glyph.
    """

    drawMethod = "drawPoints"
    transformPen = TransformPointPen

    def init(self) -> None:
        super().init()
        self._currentContourStartIndex = None

    def _isClosed(self) -> bool:
        return self._currentContourStartIndex is None

    def beginPath(self, identifier: Optional[str] = None, **kwargs: Any) -> None:
        """
        Start a new sub path.
        """
        if not self._isClosed():
            raise PenError("Didn't close previous contour.")
        self._currentContourStartIndex = len(self.points)

    def endPath(self) -> None:
        """
        End the current sub path.
        """
        # TrueType contours are always "closed"
        if self._isClosed():
            raise PenError("Contour is already closed.")
        if self._currentContourStartIndex == len(self.points):
            # ignore empty contours
            self._currentContourStartIndex = None
            return

        contourStart = self.endPts[-1] + 1 if self.endPts else 0
        self.endPts.append(len(self.points) - 1)
        self._currentContourStartIndex = None

        # Resolve types for any cubic segments
        flags = self.types
        for i in range(contourStart, len(flags)):
            if flags[i] == "curve":
                j = i - 1
                if j < contourStart:
                    j = len(flags) - 1
                while flags[j] == 0:
                    flags[j] = flagCubic
                    j -= 1
                flags[i] = flagOnCurve

    def addPoint(
        self,
        pt: Tuple[float, float],
        segmentType: Optional[str] = None,
        smooth: bool = False,
        name: Optional[str] = None,
        identifier: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        Add a point to the current sub path.
        """
        if self._isClosed():
            raise PenError("Can't add a point to a closed contour.")
        if segmentType is None:
            self.types.append(0)
        elif segmentType in ("line", "move"):
            self.types.append(flagOnCurve)
        elif segmentType == "qcurve":
            self.types.append(flagOnCurve)
        elif segmentType == "curve":
            self.types.append("curve")
        else:
            raise AssertionError(segmentType)

        self.points.append(pt)
