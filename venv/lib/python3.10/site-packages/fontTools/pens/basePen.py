"""fontTools.pens.basePen.py -- Tools and base classes to build pen objects.

The Pen Protocol

A Pen is a kind of object that standardizes the way how to "draw" outlines:
it is a middle man between an outline and a drawing. In other words:
it is an abstraction for drawing outlines, making sure that outline objects
don't need to know the details about how and where they're being drawn, and
that drawings don't need to know the details of how outlines are stored.

The most basic pattern is this::

	outline.draw(pen)  # 'outline' draws itself onto 'pen'

Pens can be used to render outlines to the screen, but also to construct
new outlines. Eg. an outline object can be both a drawable object (it has a
draw() method) as well as a pen itself: you *build* an outline using pen
methods.

The AbstractPen class defines the Pen protocol. It implements almost
nothing (only no-op closePath() and endPath() methods), but is useful
for documentation purposes. Subclassing it basically tells the reader:
"this class implements the Pen protocol.". An examples of an AbstractPen
subclass is :py:class:`fontTools.pens.transformPen.TransformPen`.

The BasePen class is a base implementation useful for pens that actually
draw (for example a pen renders outlines using a native graphics engine).
BasePen contains a lot of base functionality, making it very easy to build
a pen that fully conforms to the pen protocol. Note that if you subclass
BasePen, you *don't* override moveTo(), lineTo(), etc., but _moveTo(),
_lineTo(), etc. See the BasePen doc string for details. Examples of
BasePen subclasses are fontTools.pens.boundsPen.BoundsPen and
fontTools.pens.cocoaPen.CocoaPen.

Coordinates are usually expressed as (x, y) tuples, but generally any
sequence of length 2 will do.
"""

from typing import Tuple, Dict

from fontTools.misc.loggingTools import LogMixin
from fontTools.misc.transform import DecomposedTransform, Identity

__all__ = [
    "AbstractPen",
    "NullPen",
    "BasePen",
    "PenError",
    "decomposeSuperBezierSegment",
    "decomposeQuadraticSegment",
]


class PenError(Exception):
    """Represents an error during penning."""


class OpenContourError(PenError):
    pass


class AbstractPen:
    def moveTo(self, pt: Tuple[float, float]) -> None:
        """Begin a new sub path, set the current point to 'pt'. You must
        end each sub path with a call to pen.closePath() or pen.endPath().
        """
        raise NotImplementedError

    def lineTo(self, pt: Tuple[float, float]) -> None:
        """Draw a straight line from the current point to 'pt'."""
        raise NotImplementedError

    def curveTo(self, *points: Tuple[float, float]) -> None:
        """Draw a cubic bezier with an arbitrary number of control points.

        The last point specified is on-curve, all others are off-curve
        (control) points. If the number of control points is > 2, the
        segment is split into multiple bezier segments. This works
        like this:

        Let n be the number of control points (which is the number of
        arguments to this call minus 1). If n==2, a plain vanilla cubic
        bezier is drawn. If n==1, we fall back to a quadratic segment and
        if n==0 we draw a straight line. It gets interesting when n>2:
        n-1 PostScript-style cubic segments will be drawn as if it were
        one curve. See decomposeSuperBezierSegment().

        The conversion algorithm used for n>2 is inspired by NURB
        splines, and is conceptually equivalent to the TrueType "implied
        points" principle. See also decomposeQuadraticSegment().
        """
        raise NotImplementedError

    def qCurveTo(self, *points: Tuple[float, float]) -> None:
        """Draw a whole string of quadratic curve segments.

        The last point specified is on-curve, all others are off-curve
        points.

        This method implements TrueType-style curves, breaking up curves
        using 'implied points': between each two consequtive off-curve points,
        there is one implied point exactly in the middle between them. See
        also decomposeQuadraticSegment().

        The last argument (normally the on-curve point) may be None.
        This is to support contours that have NO on-curve points (a rarely
        seen feature of TrueType outlines).
        """
        raise NotImplementedError

    def closePath(self) -> None:
        """Close the current sub path. You must call either pen.closePath()
        or pen.endPath() after each sub path.
        """
        pass

    def endPath(self) -> None:
        """End the current sub path, but don't close it. You must call
        either pen.closePath() or pen.endPath() after each sub path.
        """
        pass

    def addComponent(
        self,
        glyphName: str,
        transformation: Tuple[float, float, float, float, float, float],
    ) -> None:
        """Add a sub glyph. The 'transformation' argument must be a 6-tuple
        containing an affine transformation, or a Transform object from the
        fontTools.misc.transform module. More precisely: it should be a
        sequence containing 6 numbers.
        """
        raise NotImplementedError

    def addVarComponent(
        self,
        glyphName: str,
        transformation: DecomposedTransform,
        location: Dict[str, float],
    ) -> None:
        """Add a VarComponent sub glyph. The 'transformation' argument
        must be a DecomposedTransform from the fontTools.misc.transform module,
        and the 'location' argument must be a dictionary mapping axis tags
        to their locations.
        """
        # GlyphSet decomposes for us
        raise AttributeError


class NullPen(AbstractPen):
    """A pen that does nothing."""

    def moveTo(self, pt):
        pass

    def lineTo(self, pt):
        pass

    def curveTo(self, *points):
        pass

    def qCurveTo(self, *points):
        pass

    def closePath(self):
        pass

    def endPath(self):
        pass

    def addComponent(self, glyphName, transformation):
        pass

    def addVarComponent(self, glyphName, transformation, location):
        pass


class LoggingPen(LogMixin, AbstractPen):
    """A pen with a ``log`` property (see fontTools.misc.loggingTools.LogMixin)"""

    pass


class MissingComponentError(KeyError):
    """Indicates a component pointing to a non-existent glyph in the glyphset."""


class DecomposingPen(LoggingPen):
    """Implements a 'addComponent' method that decomposes components
    (i.e. draws them onto self as simple contours).
    It can also be used as a mixin class (e.g. see ContourRecordingPen).

    You must override moveTo, lineTo, curveTo and qCurveTo. You may
    additionally override closePath, endPath and addComponent.

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
        reverseFlipped=False,
        **kwargs,
    ):
        """Takes a 'glyphSet' argument (dict), in which the glyphs that are referenced
        as components are looked up by their name.

        If the optional 'reverseFlipped' argument is True, components whose transformation
        matrix has a negative determinant will be decomposed with a reversed path direction
        to compensate for the flip.

        The optional 'skipMissingComponents' argument can be set to True/False to
        override the homonymous class attribute for a given pen instance.
        """
        super(DecomposingPen, self).__init__(*args, **kwargs)
        self.glyphSet = glyphSet
        self.skipMissingComponents = (
            self.__class__.skipMissingComponents
            if skipMissingComponents is None
            else skipMissingComponents
        )
        self.reverseFlipped = reverseFlipped

    def addComponent(self, glyphName, transformation):
        """Transform the points of the base glyph and draw it onto self."""
        from fontTools.pens.transformPen import TransformPen

        try:
            glyph = self.glyphSet[glyphName]
        except KeyError:
            if not self.skipMissingComponents:
                raise MissingComponentError(glyphName)
            self.log.warning("glyph '%s' is missing from glyphSet; skipped" % glyphName)
        else:
            pen = self
            if transformation != Identity:
                pen = TransformPen(pen, transformation)
            if self.reverseFlipped:
                # if the transformation has a negative determinant, it will
                # reverse the contour direction of the component
                a, b, c, d = transformation[:4]
                det = a * d - b * c
                if det < 0:
                    from fontTools.pens.reverseContourPen import ReverseContourPen

                    pen = ReverseContourPen(pen)
            glyph.draw(pen)

    def addVarComponent(self, glyphName, transformation, location):
        # GlyphSet decomposes for us
        raise AttributeError


class BasePen(DecomposingPen):
    """Base class for drawing pens. You must override _moveTo, _lineTo and
    _curveToOne. You may additionally override _closePath, _endPath,
    addComponent, addVarComponent, and/or _qCurveToOne. You should not
    override any other methods.
    """

    def __init__(self, glyphSet=None):
        super(BasePen, self).__init__(glyphSet)
        self.__currentPoint = None

    # must override

    def _moveTo(self, pt):
        raise NotImplementedError

    def _lineTo(self, pt):
        raise NotImplementedError

    def _curveToOne(self, pt1, pt2, pt3):
        raise NotImplementedError

    # may override

    def _closePath(self):
        pass

    def _endPath(self):
        pass

    def _qCurveToOne(self, pt1, pt2):
        """This method implements the basic quadratic curve type. The
        default implementation delegates the work to the cubic curve
        function. Optionally override with a native implementation.
        """
        pt0x, pt0y = self.__currentPoint
        pt1x, pt1y = pt1
        pt2x, pt2y = pt2
        mid1x = pt0x + 0.66666666666666667 * (pt1x - pt0x)
        mid1y = pt0y + 0.66666666666666667 * (pt1y - pt0y)
        mid2x = pt2x + 0.66666666666666667 * (pt1x - pt2x)
        mid2y = pt2y + 0.66666666666666667 * (pt1y - pt2y)
        self._curveToOne((mid1x, mid1y), (mid2x, mid2y), pt2)

    # don't override

    def _getCurrentPoint(self):
        """Return the current point. This is not part of the public
        interface, yet is useful for subclasses.
        """
        return self.__currentPoint

    def closePath(self):
        self._closePath()
        self.__currentPoint = None

    def endPath(self):
        self._endPath()
        self.__currentPoint = None

    def moveTo(self, pt):
        self._moveTo(pt)
        self.__currentPoint = pt

    def lineTo(self, pt):
        self._lineTo(pt)
        self.__currentPoint = pt

    def curveTo(self, *points):
        n = len(points) - 1  # 'n' is the number of control points
        assert n >= 0
        if n == 2:
            # The common case, we have exactly two BCP's, so this is a standard
            # cubic bezier. Even though decomposeSuperBezierSegment() handles
            # this case just fine, we special-case it anyway since it's so
            # common.
            self._curveToOne(*points)
            self.__currentPoint = points[-1]
        elif n > 2:
            # n is the number of control points; split curve into n-1 cubic
            # bezier segments. The algorithm used here is inspired by NURB
            # splines and the TrueType "implied point" principle, and ensures
            # the smoothest possible connection between two curve segments,
            # with no disruption in the curvature. It is practical since it
            # allows one to construct multiple bezier segments with a much
            # smaller amount of points.
            _curveToOne = self._curveToOne
            for pt1, pt2, pt3 in decomposeSuperBezierSegment(points):
                _curveToOne(pt1, pt2, pt3)
                self.__currentPoint = pt3
        elif n == 1:
            self.qCurveTo(*points)
        elif n == 0:
            self.lineTo(points[0])
        else:
            raise AssertionError("can't get there from here")

    def qCurveTo(self, *points):
        n = len(points) - 1  # 'n' is the number of control points
        assert n >= 0
        if points[-1] is None:
            # Special case for TrueType quadratics: it is possible to
            # define a contour with NO on-curve points. BasePen supports
            # this by allowing the final argument (the expected on-curve
            # point) to be None. We simulate the feature by making the implied
            # on-curve point between the last and the first off-curve points
            # explicit.
            x, y = points[-2]  # last off-curve point
            nx, ny = points[0]  # first off-curve point
            impliedStartPoint = (0.5 * (x + nx), 0.5 * (y + ny))
            self.__currentPoint = impliedStartPoint
            self._moveTo(impliedStartPoint)
            points = points[:-1] + (impliedStartPoint,)
        if n > 0:
            # Split the string of points into discrete quadratic curve
            # segments. Between any two consecutive off-curve points
            # there's an implied on-curve point exactly in the middle.
            # This is where the segment splits.
            _qCurveToOne = self._qCurveToOne
            for pt1, pt2 in decomposeQuadraticSegment(points):
                _qCurveToOne(pt1, pt2)
                self.__currentPoint = pt2
        else:
            self.lineTo(points[0])


def decomposeSuperBezierSegment(points):
    """Split the SuperBezier described by 'points' into a list of regular
    bezier segments. The 'points' argument must be a sequence with length
    3 or greater, containing (x, y) coordinates. The last point is the
    destination on-curve point, the rest of the points are off-curve points.
    The start point should not be supplied.

    This function returns a list of (pt1, pt2, pt3) tuples, which each
    specify a regular curveto-style bezier segment.
    """
    n = len(points) - 1
    assert n > 1
    bezierSegments = []
    pt1, pt2, pt3 = points[0], None, None
    for i in range(2, n + 1):
        # calculate points in between control points.
        nDivisions = min(i, 3, n - i + 2)
        for j in range(1, nDivisions):
            factor = j / nDivisions
            temp1 = points[i - 1]
            temp2 = points[i - 2]
            temp = (
                temp2[0] + factor * (temp1[0] - temp2[0]),
                temp2[1] + factor * (temp1[1] - temp2[1]),
            )
            if pt2 is None:
                pt2 = temp
            else:
                pt3 = (0.5 * (pt2[0] + temp[0]), 0.5 * (pt2[1] + temp[1]))
                bezierSegments.append((pt1, pt2, pt3))
                pt1, pt2, pt3 = temp, None, None
    bezierSegments.append((pt1, points[-2], points[-1]))
    return bezierSegments


def decomposeQuadraticSegment(points):
    """Split the quadratic curve segment described by 'points' into a list
    of "atomic" quadratic segments. The 'points' argument must be a sequence
    with length 2 or greater, containing (x, y) coordinates. The last point
    is the destination on-curve point, the rest of the points are off-curve
    points. The start point should not be supplied.

    This function returns a list of (pt1, pt2) tuples, which each specify a
    plain quadratic bezier segment.
    """
    n = len(points) - 1
    assert n > 0
    quadSegments = []
    for i in range(n - 1):
        x, y = points[i]
        nx, ny = points[i + 1]
        impliedPt = (0.5 * (x + nx), 0.5 * (y + ny))
        quadSegments.append((points[i], impliedPt))
    quadSegments.append((points[-2], points[-1]))
    return quadSegments


class _TestPen(BasePen):
    """Test class that prints PostScript to stdout."""

    def _moveTo(self, pt):
        print("%s %s moveto" % (pt[0], pt[1]))

    def _lineTo(self, pt):
        print("%s %s lineto" % (pt[0], pt[1]))

    def _curveToOne(self, bcp1, bcp2, pt):
        print(
            "%s %s %s %s %s %s curveto"
            % (bcp1[0], bcp1[1], bcp2[0], bcp2[1], pt[0], pt[1])
        )

    def _closePath(self):
        print("closepath")


if __name__ == "__main__":
    pen = _TestPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((0, 100))
    pen.curveTo((50, 75), (60, 50), (50, 25), (0, 0))
    pen.closePath()

    pen = _TestPen(None)
    # testing the "no on-curve point" scenario
    pen.qCurveTo((0, 0), (0, 100), (100, 100), (100, 0), None)
    pen.closePath()
