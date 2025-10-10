from fontTools.pens.basePen import BasePen


__all__ = ["WxPen"]


class WxPen(BasePen):
    def __init__(self, glyphSet, path=None):
        BasePen.__init__(self, glyphSet)
        if path is None:
            import wx

            path = wx.GraphicsRenderer.GetDefaultRenderer().CreatePath()
        self.path = path

    def _moveTo(self, p):
        self.path.MoveToPoint(*p)

    def _lineTo(self, p):
        self.path.AddLineToPoint(*p)

    def _curveToOne(self, p1, p2, p3):
        self.path.AddCurveToPoint(*p1 + p2 + p3)

    def _qCurveToOne(self, p1, p2):
        self.path.AddQuadCurveToPoint(*p1 + p2)

    def _closePath(self):
        self.path.CloseSubpath()
