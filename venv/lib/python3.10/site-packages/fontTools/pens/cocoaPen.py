from fontTools.pens.basePen import BasePen


__all__ = ["CocoaPen"]


class CocoaPen(BasePen):
    def __init__(self, glyphSet, path=None):
        BasePen.__init__(self, glyphSet)
        if path is None:
            from AppKit import NSBezierPath

            path = NSBezierPath.bezierPath()
        self.path = path

    def _moveTo(self, p):
        self.path.moveToPoint_(p)

    def _lineTo(self, p):
        self.path.lineToPoint_(p)

    def _curveToOne(self, p1, p2, p3):
        self.path.curveToPoint_controlPoint1_controlPoint2_(p3, p1, p2)

    def _closePath(self):
        self.path.closePath()
