"""
=========
PointPens
=========

Where **SegmentPens** have an intuitive approach to drawing
(if you're familiar with postscript anyway), the **PointPen**
is geared towards accessing all the data in the contours of
the glyph. A PointPen has a very simple interface, it just
steps through all the points in a call from glyph.drawPoints().
This allows the caller to provide more data for each point.
For instance, whether or not a point is smooth, and its name.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from fontTools.misc.enumTools import StrEnum
from fontTools.misc.loggingTools import LogMixin
from fontTools.misc.transform import DecomposedTransform, Identity
from fontTools.pens.basePen import AbstractPen, MissingComponentError, PenError

__all__ = [
    "AbstractPointPen",
    "BasePointToSegmentPen",
    "PointToSegmentPen",
    "SegmentToPointPen",
    "GuessSmoothPointPen",
    "ReverseContourPointPen",
    "ReverseFlipped",
]

# Some type aliases to make it easier below
Point = Tuple[float, float]
PointName = Optional[str]
# [(pt, smooth, name, kwargs)]
SegmentPointList = List[Tuple[Optional[Point], bool, PointName, Any]]
SegmentType = Optional[str]
SegmentList = List[Tuple[SegmentType, SegmentPointList]]


class ReverseFlipped(StrEnum):
    """How to handle flipped components during decomposition.

    NO: Don't reverse flipped components
    KEEP_START: Reverse flipped components, keeping original starting point
    ON_CURVE_FIRST: Reverse flipped components, ensuring first point is on-curve
    """

    NO = "no"
    KEEP_START = "keep_start"
    ON_CURVE_FIRST = "on_curve_first"


class AbstractPointPen:
    """Baseclass for all PointPens."""

    def beginPath(self, identifier: Optional[str] = None, **kwargs: Any) -> None:
        """Start a new sub path."""
        raise NotImplementedError

    def endPath(self) -> None:
        """End the current sub path."""
        raise NotImplementedError

    def addPoint(
        self,
        pt: Tuple[float, float],
        segmentType: Optional[str] = None,
        smooth: bool = False,
        name: Optional[str] = None,
        identifier: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Add a point to the current sub path."""
        raise NotImplementedError

    def addComponent(
        self,
        baseGlyphName: str,
        transformation: Tuple[float, float, float, float, float, float],
        identifier: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Add a sub glyph."""
        raise NotImplementedError

    def addVarComponent(
        self,
        glyphName: str,
        transformation: DecomposedTransform,
        location: Dict[str, float],
        identifier: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Add a VarComponent sub glyph. The 'transformation' argument
        must be a DecomposedTransform from the fontTools.misc.transform module,
        and the 'location' argument must be a dictionary mapping axis tags
        to their locations.
        """
        # ttGlyphSet decomposes for us
        raise AttributeError


class BasePointToSegmentPen(AbstractPointPen):
    """
    Base class for retrieving the outline in a segment-oriented
    way. The PointPen protocol is simple yet also a little tricky,
    so when you need an outline presented as segments but you have
    as points, do use this base implementation as it properly takes
    care of all the edge cases.
    """

    def __init__(self) -> None:
        self.currentPath = None

    def beginPath(self, identifier=None, **kwargs):
        if self.currentPath is not None:
            raise PenError("Path already begun.")
        self.currentPath = []

    def _flushContour(self, segments: SegmentList) -> None:
        """Override this method.

        It will be called for each non-empty sub path with a list
        of segments: the 'segments' argument.

        The segments list contains tuples of length 2:
                (segmentType, points)

        segmentType is one of "move", "line", "curve" or "qcurve".
        "move" may only occur as the first segment, and it signifies
        an OPEN path. A CLOSED path does NOT start with a "move", in
        fact it will not contain a "move" at ALL.

        The 'points' field in the 2-tuple is a list of point info
        tuples. The list has 1 or more items, a point tuple has
        four items:
                (point, smooth, name, kwargs)
        'point' is an (x, y) coordinate pair.

        For a closed path, the initial moveTo point is defined as
        the last point of the last segment.

        The 'points' list of "move" and "line" segments always contains
        exactly one point tuple.
        """
        raise NotImplementedError

    def endPath(self) -> None:
        if self.currentPath is None:
            raise PenError("Path not begun.")
        points = self.currentPath
        self.currentPath = None
        if not points:
            return
        if len(points) == 1:
            # Not much more we can do than output a single move segment.
            pt, segmentType, smooth, name, kwargs = points[0]
            segments: SegmentList = [("move", [(pt, smooth, name, kwargs)])]
            self._flushContour(segments)
            return
        segments = []
        if points[0][1] == "move":
            # It's an open contour, insert a "move" segment for the first
            # point and remove that first point from the point list.
            pt, segmentType, smooth, name, kwargs = points[0]
            segments.append(("move", [(pt, smooth, name, kwargs)]))
            points.pop(0)
        else:
            # It's a closed contour. Locate the first on-curve point, and
            # rotate the point list so that it _ends_ with an on-curve
            # point.
            firstOnCurve = None
            for i in range(len(points)):
                segmentType = points[i][1]
                if segmentType is not None:
                    firstOnCurve = i
                    break
            if firstOnCurve is None:
                # Special case for quadratics: a contour with no on-curve
                # points. Add a "None" point. (See also the Pen protocol's
                # qCurveTo() method and fontTools.pens.basePen.py.)
                points.append((None, "qcurve", None, None, None))
            else:
                points = points[firstOnCurve + 1 :] + points[: firstOnCurve + 1]

        currentSegment: SegmentPointList = []
        for pt, segmentType, smooth, name, kwargs in points:
            currentSegment.append((pt, smooth, name, kwargs))
            if segmentType is None:
                continue
            segments.append((segmentType, currentSegment))
            currentSegment = []

        self._flushContour(segments)

    def addPoint(
        self, pt, segmentType=None, smooth=False, name=None, identifier=None, **kwargs
    ):
        if self.currentPath is None:
            raise PenError("Path not begun")
        self.currentPath.append((pt, segmentType, smooth, name, kwargs))


class PointToSegmentPen(BasePointToSegmentPen):
    """
    Adapter class that converts the PointPen protocol to the
    (Segment)Pen protocol.

    NOTE: The segment pen does not support and will drop point names, identifiers
    and kwargs.
    """

    def __init__(self, segmentPen, outputImpliedClosingLine: bool = False) -> None:
        BasePointToSegmentPen.__init__(self)
        self.pen = segmentPen
        self.outputImpliedClosingLine = outputImpliedClosingLine

    def _flushContour(self, segments):
        if not segments:
            raise PenError("Must have at least one segment.")
        pen = self.pen
        if segments[0][0] == "move":
            # It's an open path.
            closed = False
            points = segments[0][1]
            if len(points) != 1:
                raise PenError(f"Illegal move segment point count: {len(points)}")
            movePt, _, _, _ = points[0]
            del segments[0]
        else:
            # It's a closed path, do a moveTo to the last
            # point of the last segment.
            closed = True
            segmentType, points = segments[-1]
            movePt, _, _, _ = points[-1]
        if movePt is None:
            # quad special case: a contour with no on-curve points contains
            # one "qcurve" segment that ends with a point that's None. We
            # must not output a moveTo() in that case.
            pass
        else:
            pen.moveTo(movePt)
        outputImpliedClosingLine = self.outputImpliedClosingLine
        nSegments = len(segments)
        lastPt = movePt
        for i in range(nSegments):
            segmentType, points = segments[i]
            points = [pt for pt, _, _, _ in points]
            if segmentType == "line":
                if len(points) != 1:
                    raise PenError(f"Illegal line segment point count: {len(points)}")
                pt = points[0]
                # For closed contours, a 'lineTo' is always implied from the last oncurve
                # point to the starting point, thus we can omit it when the last and
                # starting point don't overlap.
                # However, when the last oncurve point is a "line" segment and has same
                # coordinates as the starting point of a closed contour, we need to output
                # the closing 'lineTo' explicitly (regardless of the value of the
                # 'outputImpliedClosingLine' option) in order to disambiguate this case from
                # the implied closing 'lineTo', otherwise the duplicate point would be lost.
                # See https://github.com/googlefonts/fontmake/issues/572.
                if (
                    i + 1 != nSegments
                    or outputImpliedClosingLine
                    or not closed
                    or pt == lastPt
                ):
                    pen.lineTo(pt)
                    lastPt = pt
            elif segmentType == "curve":
                pen.curveTo(*points)
                lastPt = points[-1]
            elif segmentType == "qcurve":
                pen.qCurveTo(*points)
                lastPt = points[-1]
            else:
                raise PenError(f"Illegal segmentType: {segmentType}")
        if closed:
            pen.closePath()
        else:
            pen.endPath()

    def addComponent(self, glyphName, transform, identifier=None, **kwargs):
        del identifier  # unused
        del kwargs  # unused
        self.pen.addComponent(glyphName, transform)


class SegmentToPointPen(AbstractPen):
    """
    Adapter class that converts the (Segment)Pen protocol to the
    PointPen protocol.
    """

    def __init__(self, pointPen, guessSmooth=True) -> None:
        if guessSmooth:
            self.pen = GuessSmoothPointPen(pointPen)
        else:
            self.pen = pointPen
        self.contour: Optional[List[Tuple[Point, SegmentType]]] = None

    def _flushContour(self) -> None:
        pen = self.pen
        pen.beginPath()
        for pt, segmentType in self.contour:
            pen.addPoint(pt, segmentType=segmentType)
        pen.endPath()

    def moveTo(self, pt):
        self.contour = []
        self.contour.append((pt, "move"))

    def lineTo(self, pt):
        if self.contour is None:
            raise PenError("Contour missing required initial moveTo")
        self.contour.append((pt, "line"))

    def curveTo(self, *pts):
        if not pts:
            raise TypeError("Must pass in at least one point")
        if self.contour is None:
            raise PenError("Contour missing required initial moveTo")
        for pt in pts[:-1]:
            self.contour.append((pt, None))
        self.contour.append((pts[-1], "curve"))

    def qCurveTo(self, *pts):
        if not pts:
            raise TypeError("Must pass in at least one point")
        if pts[-1] is None:
            self.contour = []
        else:
            if self.contour is None:
                raise PenError("Contour missing required initial moveTo")
        for pt in pts[:-1]:
            self.contour.append((pt, None))
        if pts[-1] is not None:
            self.contour.append((pts[-1], "qcurve"))

    def closePath(self):
        if self.contour is None:
            raise PenError("Contour missing required initial moveTo")
        if len(self.contour) > 1 and self.contour[0][0] == self.contour[-1][0]:
            self.contour[0] = self.contour[-1]
            del self.contour[-1]
        else:
            # There's an implied line at the end, replace "move" with "line"
            # for the first point
            pt, tp = self.contour[0]
            if tp == "move":
                self.contour[0] = pt, "line"
        self._flushContour()
        self.contour = None

    def endPath(self):
        if self.contour is None:
            raise PenError("Contour missing required initial moveTo")
        self._flushContour()
        self.contour = None

    def addComponent(self, glyphName, transform):
        if self.contour is not None:
            raise PenError("Components must be added before or after contours")
        self.pen.addComponent(glyphName, transform)


class GuessSmoothPointPen(AbstractPointPen):
    """
    Filtering PointPen that tries to determine whether an on-curve point
    should be "smooth", ie. that it's a "tangent" point or a "curve" point.
    """

    def __init__(self, outPen, error=0.05):
        self._outPen = outPen
        self._error = error
        self._points = None

    def _flushContour(self):
        if self._points is None:
            raise PenError("Path not begun")
        points = self._points
        nPoints = len(points)
        if not nPoints:
            return
        if points[0][1] == "move":
            # Open path.
            indices = range(1, nPoints - 1)
        elif nPoints > 1:
            # Closed path. To avoid having to mod the contour index, we
            # simply abuse Python's negative index feature, and start at -1
            indices = range(-1, nPoints - 1)
        else:
            # closed path containing 1 point (!), ignore.
            indices = []
        for i in indices:
            pt, segmentType, _, name, kwargs = points[i]
            if segmentType is None:
                continue
            prev = i - 1
            next = i + 1
            if points[prev][1] is not None and points[next][1] is not None:
                continue
            # At least one of our neighbors is an off-curve point
            pt = points[i][0]
            prevPt = points[prev][0]
            nextPt = points[next][0]
            if pt != prevPt and pt != nextPt:
                dx1, dy1 = pt[0] - prevPt[0], pt[1] - prevPt[1]
                dx2, dy2 = nextPt[0] - pt[0], nextPt[1] - pt[1]
                a1 = math.atan2(dy1, dx1)
                a2 = math.atan2(dy2, dx2)
                if abs(a1 - a2) < self._error:
                    points[i] = pt, segmentType, True, name, kwargs

        for pt, segmentType, smooth, name, kwargs in points:
            self._outPen.addPoint(pt, segmentType, smooth, name, **kwargs)

    def beginPath(self, identifier=None, **kwargs):
        if self._points is not None:
            raise PenError("Path already begun")
        self._points = []
        if identifier is not None:
            kwargs["identifier"] = identifier
        self._outPen.beginPath(**kwargs)

    def endPath(self):
        self._flushContour()
        self._outPen.endPath()
        self._points = None

    def addPoint(
        self, pt, segmentType=None, smooth=False, name=None, identifier=None, **kwargs
    ):
        if self._points is None:
            raise PenError("Path not begun")
        if identifier is not None:
            kwargs["identifier"] = identifier
        self._points.append((pt, segmentType, False, name, kwargs))

    def addComponent(self, glyphName, transformation, identifier=None, **kwargs):
        if self._points is not None:
            raise PenError("Components must be added before or after contours")
        if identifier is not None:
            kwargs["identifier"] = identifier
        self._outPen.addComponent(glyphName, transformation, **kwargs)

    def addVarComponent(
        self, glyphName, transformation, location, identifier=None, **kwargs
    ):
        if self._points is not None:
            raise PenError("VarComponents must be added before or after contours")
        if identifier is not None:
            kwargs["identifier"] = identifier
        self._outPen.addVarComponent(glyphName, transformation, location, **kwargs)


class ReverseContourPointPen(AbstractPointPen):
    """
    This is a PointPen that passes outline data to another PointPen, but
    reversing the winding direction of all contours. Components are simply
    passed through unchanged.

    Closed contours are reversed in such a way that the first point remains
    the first point.
    """

    def __init__(self, outputPointPen):
        self.pen = outputPointPen
        # a place to store the points for the current sub path
        self.currentContour = None

    def _flushContour(self):
        pen = self.pen
        contour = self.currentContour
        if not contour:
            pen.beginPath(identifier=self.currentContourIdentifier)
            pen.endPath()
            return

        closed = contour[0][1] != "move"
        if not closed:
            lastSegmentType = "move"
        else:
            # Remove the first point and insert it at the end. When
            # the list of points gets reversed, this point will then
            # again be at the start. In other words, the following
            # will hold:
            #   for N in range(len(originalContour)):
            #       originalContour[N] == reversedContour[-N]
            contour.append(contour.pop(0))
            # Find the first on-curve point.
            firstOnCurve = None
            for i in range(len(contour)):
                if contour[i][1] is not None:
                    firstOnCurve = i
                    break
            if firstOnCurve is None:
                # There are no on-curve points, be basically have to
                # do nothing but contour.reverse().
                lastSegmentType = None
            else:
                lastSegmentType = contour[firstOnCurve][1]

        contour.reverse()
        if not closed:
            # Open paths must start with a move, so we simply dump
            # all off-curve points leading up to the first on-curve.
            while contour[0][1] is None:
                contour.pop(0)
        pen.beginPath(identifier=self.currentContourIdentifier)
        for pt, nextSegmentType, smooth, name, kwargs in contour:
            if nextSegmentType is not None:
                segmentType = lastSegmentType
                lastSegmentType = nextSegmentType
            else:
                segmentType = None
            pen.addPoint(
                pt, segmentType=segmentType, smooth=smooth, name=name, **kwargs
            )
        pen.endPath()

    def beginPath(self, identifier=None, **kwargs):
        if self.currentContour is not None:
            raise PenError("Path already begun")
        self.currentContour = []
        self.currentContourIdentifier = identifier
        self.onCurve = []

    def endPath(self):
        if self.currentContour is None:
            raise PenError("Path not begun")
        self._flushContour()
        self.currentContour = None

    def addPoint(
        self, pt, segmentType=None, smooth=False, name=None, identifier=None, **kwargs
    ):
        if self.currentContour is None:
            raise PenError("Path not begun")
        if identifier is not None:
            kwargs["identifier"] = identifier
        self.currentContour.append((pt, segmentType, smooth, name, kwargs))

    def addComponent(self, glyphName, transform, identifier=None, **kwargs):
        if self.currentContour is not None:
            raise PenError("Components must be added before or after contours")
        self.pen.addComponent(glyphName, transform, identifier=identifier, **kwargs)


class DecomposingPointPen(LogMixin, AbstractPointPen):
    """Implements a 'addComponent' method that decomposes components
    (i.e. draws them onto self as simple contours).
    It can also be used as a mixin class (e.g. see DecomposingRecordingPointPen).

    You must override beginPath, addPoint, endPath. You may
    additionally override addVarComponent and addComponent.

    By default a warning message is logged when a base glyph is missing;
    set the class variable ``skipMissingComponents`` to False if you want
    all instances of a sub-class to raise a :class:`MissingComponentError`
    exception by default.
    """

    skipMissingComponents = True
    # alias error for convenience
    MissingComponentError = MissingComponentError

    def __init__(
        self,
        glyphSet,
        *args,
        skipMissingComponents=None,
        reverseFlipped: bool | ReverseFlipped = False,
        **kwargs,
    ):
        """Takes a 'glyphSet' argument (dict), in which the glyphs that are referenced
        as components are looked up by their name.

        If the optional 'reverseFlipped' argument is True or a ReverseFlipped enum value,
        components whose transformation matrix has a negative determinant will be decomposed
        with a reversed path direction to compensate for the flip.

        The reverseFlipped parameter can be:
        - False or ReverseFlipped.NO: Don't reverse flipped components
        - True or ReverseFlipped.KEEP_START: Reverse, keeping original starting point
        - ReverseFlipped.ON_CURVE_FIRST: Reverse, ensuring first point is on-curve

        The optional 'skipMissingComponents' argument can be set to True/False to
        override the homonymous class attribute for a given pen instance.
        """
        super().__init__(*args, **kwargs)
        self.glyphSet = glyphSet
        self.skipMissingComponents = (
            self.__class__.skipMissingComponents
            if skipMissingComponents is None
            else skipMissingComponents
        )
        # Handle backward compatibility and validate string inputs
        if reverseFlipped is False:
            self.reverseFlipped = ReverseFlipped.NO
        elif reverseFlipped is True:
            self.reverseFlipped = ReverseFlipped.KEEP_START
        else:
            self.reverseFlipped = ReverseFlipped(reverseFlipped)

    def addComponent(self, baseGlyphName, transformation, identifier=None, **kwargs):
        """Transform the points of the base glyph and draw it onto self.

        The `identifier` parameter and any extra kwargs are ignored.
        """
        from fontTools.pens.transformPen import TransformPointPen

        try:
            glyph = self.glyphSet[baseGlyphName]
        except KeyError:
            if not self.skipMissingComponents:
                raise MissingComponentError(baseGlyphName)
            self.log.warning(
                "glyph '%s' is missing from glyphSet; skipped" % baseGlyphName
            )
        else:
            pen = self
            if transformation != Identity:
                pen = TransformPointPen(pen, transformation)
            if self.reverseFlipped != ReverseFlipped.NO:
                # if the transformation has a negative determinant, it will
                # reverse the contour direction of the component
                a, b, c, d = transformation[:4]
                if a * d - b * c < 0:
                    pen = ReverseContourPointPen(pen)

                    if self.reverseFlipped == ReverseFlipped.ON_CURVE_FIRST:
                        from fontTools.pens.filterPen import OnCurveFirstPointPen

                        # Ensure the starting point is an on-curve.
                        # Wrap last so this filter runs first during drawPoints
                        pen = OnCurveFirstPointPen(pen)

            glyph.drawPoints(pen)
