from fontTools.pens.basePen import BasePen

from Quartz.CoreGraphics import CGPathCreateMutable, CGPathMoveToPoint
from Quartz.CoreGraphics import CGPathAddLineToPoint, CGPathAddCurveToPoint
from Quartz.CoreGraphics import CGPathAddQuadCurveToPoint, CGPathCloseSubpath


__all__ = ["QuartzPen"]


class QuartzPen(BasePen):
    """A pen that creates a CGPath

    Parameters
    - path: an optional CGPath to add to
    - xform: an optional CGAffineTransform to apply to the path
    """

    def __init__(self, glyphSet, path=None, xform=None):
        BasePen.__init__(self, glyphSet)
        if path is None:
            path = CGPathCreateMutable()
        self.path = path
        self.xform = xform

    def _moveTo(self, pt):
        x, y = pt
        CGPathMoveToPoint(self.path, self.xform, x, y)

    def _lineTo(self, pt):
        x, y = pt
        CGPathAddLineToPoint(self.path, self.xform, x, y)

    def _curveToOne(self, p1, p2, p3):
        (x1, y1), (x2, y2), (x3, y3) = p1, p2, p3
        CGPathAddCurveToPoint(self.path, self.xform, x1, y1, x2, y2, x3, y3)

    def _qCurveToOne(self, p1, p2):
        (x1, y1), (x2, y2) = p1, p2
        CGPathAddQuadCurveToPoint(self.path, self.xform, x1, y1, x2, y2)

    def _closePath(self):
        CGPathCloseSubpath(self.path)
