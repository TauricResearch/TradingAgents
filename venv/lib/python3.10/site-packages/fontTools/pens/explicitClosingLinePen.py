from fontTools.pens.filterPen import ContourFilterPen


class ExplicitClosingLinePen(ContourFilterPen):
    """A filter pen that adds an explicit lineTo to the first point of each closed
    contour if the end point of the last segment is not already the same as the first point.
    Otherwise, it passes the contour through unchanged.

    >>> from pprint import pprint
    >>> from fontTools.pens.recordingPen import RecordingPen
    >>> rec = RecordingPen()
    >>> pen = ExplicitClosingLinePen(rec)
    >>> pen.moveTo((0, 0))
    >>> pen.lineTo((100, 0))
    >>> pen.lineTo((100, 100))
    >>> pen.closePath()
    >>> pprint(rec.value)
    [('moveTo', ((0, 0),)),
     ('lineTo', ((100, 0),)),
     ('lineTo', ((100, 100),)),
     ('lineTo', ((0, 0),)),
     ('closePath', ())]
    >>> rec = RecordingPen()
    >>> pen = ExplicitClosingLinePen(rec)
    >>> pen.moveTo((0, 0))
    >>> pen.lineTo((100, 0))
    >>> pen.lineTo((100, 100))
    >>> pen.lineTo((0, 0))
    >>> pen.closePath()
    >>> pprint(rec.value)
    [('moveTo', ((0, 0),)),
     ('lineTo', ((100, 0),)),
     ('lineTo', ((100, 100),)),
     ('lineTo', ((0, 0),)),
     ('closePath', ())]
    >>> rec = RecordingPen()
    >>> pen = ExplicitClosingLinePen(rec)
    >>> pen.moveTo((0, 0))
    >>> pen.curveTo((100, 0), (0, 100), (100, 100))
    >>> pen.closePath()
    >>> pprint(rec.value)
    [('moveTo', ((0, 0),)),
     ('curveTo', ((100, 0), (0, 100), (100, 100))),
     ('lineTo', ((0, 0),)),
     ('closePath', ())]
    >>> rec = RecordingPen()
    >>> pen = ExplicitClosingLinePen(rec)
    >>> pen.moveTo((0, 0))
    >>> pen.curveTo((100, 0), (0, 100), (100, 100))
    >>> pen.lineTo((0, 0))
    >>> pen.closePath()
    >>> pprint(rec.value)
    [('moveTo', ((0, 0),)),
     ('curveTo', ((100, 0), (0, 100), (100, 100))),
     ('lineTo', ((0, 0),)),
     ('closePath', ())]
    >>> rec = RecordingPen()
    >>> pen = ExplicitClosingLinePen(rec)
    >>> pen.moveTo((0, 0))
    >>> pen.curveTo((100, 0), (0, 100), (0, 0))
    >>> pen.closePath()
    >>> pprint(rec.value)
    [('moveTo', ((0, 0),)),
     ('curveTo', ((100, 0), (0, 100), (0, 0))),
     ('closePath', ())]
    >>> rec = RecordingPen()
    >>> pen = ExplicitClosingLinePen(rec)
    >>> pen.moveTo((0, 0))
    >>> pen.closePath()
    >>> pprint(rec.value)
    [('moveTo', ((0, 0),)), ('closePath', ())]
    >>> rec = RecordingPen()
    >>> pen = ExplicitClosingLinePen(rec)
    >>> pen.closePath()
    >>> pprint(rec.value)
    [('closePath', ())]
    >>> rec = RecordingPen()
    >>> pen = ExplicitClosingLinePen(rec)
    >>> pen.moveTo((0, 0))
    >>> pen.lineTo((100, 0))
    >>> pen.lineTo((100, 100))
    >>> pen.endPath()
    >>> pprint(rec.value)
    [('moveTo', ((0, 0),)),
     ('lineTo', ((100, 0),)),
     ('lineTo', ((100, 100),)),
     ('endPath', ())]
    """

    def filterContour(self, contour):
        if (
            not contour
            or contour[0][0] != "moveTo"
            or contour[-1][0] != "closePath"
            or len(contour) < 3
        ):
            return
        movePt = contour[0][1][0]
        lastSeg = contour[-2][1]
        if lastSeg and movePt != lastSeg[-1]:
            contour[-1:] = [("lineTo", (movePt,)), ("closePath", ())]
