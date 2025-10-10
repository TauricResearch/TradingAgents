"""Calculate the area of a glyph."""

from fontTools.pens.basePen import BasePen


__all__ = ["AreaPen"]


class AreaPen(BasePen):
    def __init__(self, glyphset=None):
        BasePen.__init__(self, glyphset)
        self.value = 0

    def _moveTo(self, p0):
        self._p0 = self._startPoint = p0

    def _lineTo(self, p1):
        x0, y0 = self._p0
        x1, y1 = p1
        self.value -= (x1 - x0) * (y1 + y0) * 0.5
        self._p0 = p1

    def _qCurveToOne(self, p1, p2):
        # https://github.com/Pomax/bezierinfo/issues/44
        p0 = self._p0
        x0, y0 = p0[0], p0[1]
        x1, y1 = p1[0] - x0, p1[1] - y0
        x2, y2 = p2[0] - x0, p2[1] - y0
        self.value -= (x2 * y1 - x1 * y2) / 3
        self._lineTo(p2)
        self._p0 = p2

    def _curveToOne(self, p1, p2, p3):
        # https://github.com/Pomax/bezierinfo/issues/44
        p0 = self._p0
        x0, y0 = p0[0], p0[1]
        x1, y1 = p1[0] - x0, p1[1] - y0
        x2, y2 = p2[0] - x0, p2[1] - y0
        x3, y3 = p3[0] - x0, p3[1] - y0
        self.value -= (x1 * (-y2 - y3) + x2 * (y1 - 2 * y3) + x3 * (y1 + 2 * y2)) * 0.15
        self._lineTo(p3)
        self._p0 = p3

    def _closePath(self):
        self._lineTo(self._startPoint)
        del self._p0, self._startPoint

    def _endPath(self):
        if self._p0 != self._startPoint:
            # Area is not defined for open contours.
            raise NotImplementedError
        del self._p0, self._startPoint
