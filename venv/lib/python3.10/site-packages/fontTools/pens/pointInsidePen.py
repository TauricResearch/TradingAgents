"""fontTools.pens.pointInsidePen -- Pen implementing "point inside" testing
for shapes.
"""

from fontTools.pens.basePen import BasePen
from fontTools.misc.bezierTools import solveQuadratic, solveCubic


__all__ = ["PointInsidePen"]


class PointInsidePen(BasePen):
    """This pen implements "point inside" testing: to test whether
    a given point lies inside the shape (black) or outside (white).
    Instances of this class can be recycled, as long as the
    setTestPoint() method is used to set the new point to test.

    :Example:
        .. code-block::

            pen = PointInsidePen(glyphSet, (100, 200))
            outline.draw(pen)
            isInside = pen.getResult()

    Both the even-odd algorithm and the non-zero-winding-rule
    algorithm are implemented. The latter is the default, specify
    True for the evenOdd argument of __init__ or setTestPoint
    to use the even-odd algorithm.
    """

    # This class implements the classical "shoot a ray from the test point
    # to infinity and count how many times it intersects the outline" (as well
    # as the non-zero variant, where the counter is incremented if the outline
    # intersects the ray in one direction and decremented if it intersects in
    # the other direction).
    # I found an amazingly clear explanation of the subtleties involved in
    # implementing this correctly for polygons here:
    #   http://graphics.cs.ucdavis.edu/~okreylos/TAship/Spring2000/PointInPolygon.html
    # I extended the principles outlined on that page to curves.

    def __init__(self, glyphSet, testPoint, evenOdd=False):
        BasePen.__init__(self, glyphSet)
        self.setTestPoint(testPoint, evenOdd)

    def setTestPoint(self, testPoint, evenOdd=False):
        """Set the point to test. Call this _before_ the outline gets drawn."""
        self.testPoint = testPoint
        self.evenOdd = evenOdd
        self.firstPoint = None
        self.intersectionCount = 0

    def getWinding(self):
        if self.firstPoint is not None:
            # always make sure the sub paths are closed; the algorithm only works
            # for closed paths.
            self.closePath()
        return self.intersectionCount

    def getResult(self):
        """After the shape has been drawn, getResult() returns True if the test
        point lies within the (black) shape, and False if it doesn't.
        """
        winding = self.getWinding()
        if self.evenOdd:
            result = winding % 2
        else:  # non-zero
            result = self.intersectionCount != 0
        return not not result

    def _addIntersection(self, goingUp):
        if self.evenOdd or goingUp:
            self.intersectionCount += 1
        else:
            self.intersectionCount -= 1

    def _moveTo(self, point):
        if self.firstPoint is not None:
            # always make sure the sub paths are closed; the algorithm only works
            # for closed paths.
            self.closePath()
        self.firstPoint = point

    def _lineTo(self, point):
        x, y = self.testPoint
        x1, y1 = self._getCurrentPoint()
        x2, y2 = point

        if x1 < x and x2 < x:
            return
        if y1 < y and y2 < y:
            return
        if y1 >= y and y2 >= y:
            return

        dx = x2 - x1
        dy = y2 - y1
        t = (y - y1) / dy
        ix = dx * t + x1
        if ix < x:
            return
        self._addIntersection(y2 > y1)

    def _curveToOne(self, bcp1, bcp2, point):
        x, y = self.testPoint
        x1, y1 = self._getCurrentPoint()
        x2, y2 = bcp1
        x3, y3 = bcp2
        x4, y4 = point

        if x1 < x and x2 < x and x3 < x and x4 < x:
            return
        if y1 < y and y2 < y and y3 < y and y4 < y:
            return
        if y1 >= y and y2 >= y and y3 >= y and y4 >= y:
            return

        dy = y1
        cy = (y2 - dy) * 3.0
        by = (y3 - y2) * 3.0 - cy
        ay = y4 - dy - cy - by
        solutions = sorted(solveCubic(ay, by, cy, dy - y))
        solutions = [t for t in solutions if -0.0 <= t <= 1.0]
        if not solutions:
            return

        dx = x1
        cx = (x2 - dx) * 3.0
        bx = (x3 - x2) * 3.0 - cx
        ax = x4 - dx - cx - bx

        above = y1 >= y
        lastT = None
        for t in solutions:
            if t == lastT:
                continue
            lastT = t
            t2 = t * t
            t3 = t2 * t

            direction = 3 * ay * t2 + 2 * by * t + cy
            incomingGoingUp = outgoingGoingUp = direction > 0.0
            if direction == 0.0:
                direction = 6 * ay * t + 2 * by
                outgoingGoingUp = direction > 0.0
                incomingGoingUp = not outgoingGoingUp
                if direction == 0.0:
                    direction = ay
                    incomingGoingUp = outgoingGoingUp = direction > 0.0

            xt = ax * t3 + bx * t2 + cx * t + dx
            if xt < x:
                continue

            if t in (0.0, -0.0):
                if not outgoingGoingUp:
                    self._addIntersection(outgoingGoingUp)
            elif t == 1.0:
                if incomingGoingUp:
                    self._addIntersection(incomingGoingUp)
            else:
                if incomingGoingUp == outgoingGoingUp:
                    self._addIntersection(outgoingGoingUp)
                # else:
                #   we're not really intersecting, merely touching

    def _qCurveToOne_unfinished(self, bcp, point):
        # XXX need to finish this, for now doing it through a cubic
        # (BasePen implements _qCurveTo in terms of a cubic) will
        # have to do.
        x, y = self.testPoint
        x1, y1 = self._getCurrentPoint()
        x2, y2 = bcp
        x3, y3 = point
        c = y1
        b = (y2 - c) * 2.0
        a = y3 - c - b
        solutions = sorted(solveQuadratic(a, b, c - y))
        solutions = [
            t for t in solutions if ZERO_MINUS_EPSILON <= t <= ONE_PLUS_EPSILON
        ]
        if not solutions:
            return
        # XXX

    def _closePath(self):
        if self._getCurrentPoint() != self.firstPoint:
            self.lineTo(self.firstPoint)
        self.firstPoint = None

    def _endPath(self):
        """Insideness is not defined for open contours."""
        raise NotImplementedError
