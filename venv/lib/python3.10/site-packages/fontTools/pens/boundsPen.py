from fontTools.misc.arrayTools import updateBounds, pointInRect, unionRect
from fontTools.misc.bezierTools import calcCubicBounds, calcQuadraticBounds
from fontTools.pens.basePen import BasePen


__all__ = ["BoundsPen", "ControlBoundsPen"]


class ControlBoundsPen(BasePen):
    """Pen to calculate the "control bounds" of a shape. This is the
    bounding box of all control points, so may be larger than the
    actual bounding box if there are curves that don't have points
    on their extremes.

    When the shape has been drawn, the bounds are available as the
    ``bounds`` attribute of the pen object. It's a 4-tuple::

            (xMin, yMin, xMax, yMax).

    If ``ignoreSinglePoints`` is True, single points are ignored.
    """

    def __init__(self, glyphSet, ignoreSinglePoints=False):
        BasePen.__init__(self, glyphSet)
        self.ignoreSinglePoints = ignoreSinglePoints
        self.init()

    def init(self):
        self.bounds = None
        self._start = None

    def _moveTo(self, pt):
        self._start = pt
        if not self.ignoreSinglePoints:
            self._addMoveTo()

    def _addMoveTo(self):
        if self._start is None:
            return
        bounds = self.bounds
        if bounds:
            self.bounds = updateBounds(bounds, self._start)
        else:
            x, y = self._start
            self.bounds = (x, y, x, y)
        self._start = None

    def _lineTo(self, pt):
        self._addMoveTo()
        self.bounds = updateBounds(self.bounds, pt)

    def _curveToOne(self, bcp1, bcp2, pt):
        self._addMoveTo()
        bounds = self.bounds
        bounds = updateBounds(bounds, bcp1)
        bounds = updateBounds(bounds, bcp2)
        bounds = updateBounds(bounds, pt)
        self.bounds = bounds

    def _qCurveToOne(self, bcp, pt):
        self._addMoveTo()
        bounds = self.bounds
        bounds = updateBounds(bounds, bcp)
        bounds = updateBounds(bounds, pt)
        self.bounds = bounds


class BoundsPen(ControlBoundsPen):
    """Pen to calculate the bounds of a shape. It calculates the
    correct bounds even when the shape contains curves that don't
    have points on their extremes. This is somewhat slower to compute
    than the "control bounds".

    When the shape has been drawn, the bounds are available as the
    ``bounds`` attribute of the pen object. It's a 4-tuple::

            (xMin, yMin, xMax, yMax)
    """

    def _curveToOne(self, bcp1, bcp2, pt):
        self._addMoveTo()
        bounds = self.bounds
        bounds = updateBounds(bounds, pt)
        if not pointInRect(bcp1, bounds) or not pointInRect(bcp2, bounds):
            bounds = unionRect(
                bounds, calcCubicBounds(self._getCurrentPoint(), bcp1, bcp2, pt)
            )
        self.bounds = bounds

    def _qCurveToOne(self, bcp, pt):
        self._addMoveTo()
        bounds = self.bounds
        bounds = updateBounds(bounds, pt)
        if not pointInRect(bcp, bounds):
            bounds = unionRect(
                bounds, calcQuadraticBounds(self._getCurrentPoint(), bcp, pt)
            )
        self.bounds = bounds
