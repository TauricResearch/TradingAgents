from fontTools.misc.arrayTools import pairwise
from fontTools.pens.filterPen import ContourFilterPen


__all__ = ["reversedContour", "ReverseContourPen"]


class ReverseContourPen(ContourFilterPen):
    """Filter pen that passes outline data to another pen, but reversing
    the winding direction of all contours. Components are simply passed
    through unchanged.

    Closed contours are reversed in such a way that the first point remains
    the first point.
    """

    def __init__(self, outPen, outputImpliedClosingLine=False):
        super().__init__(outPen)
        self.outputImpliedClosingLine = outputImpliedClosingLine

    def filterContour(self, contour):
        return reversedContour(contour, self.outputImpliedClosingLine)


def reversedContour(contour, outputImpliedClosingLine=False):
    """Generator that takes a list of pen's (operator, operands) tuples,
    and yields them with the winding direction reversed.
    """
    if not contour:
        return  # nothing to do, stop iteration

    # valid contours must have at least a starting and ending command,
    # can't have one without the other
    assert len(contour) > 1, "invalid contour"

    # the type of the last command determines if the contour is closed
    contourType = contour.pop()[0]
    assert contourType in ("endPath", "closePath")
    closed = contourType == "closePath"

    firstType, firstPts = contour.pop(0)
    assert firstType in ("moveTo", "qCurveTo"), (
        "invalid initial segment type: %r" % firstType
    )
    firstOnCurve = firstPts[-1]
    if firstType == "qCurveTo":
        # special case for TrueType paths contaning only off-curve points
        assert firstOnCurve is None, "off-curve only paths must end with 'None'"
        assert not contour, "only one qCurveTo allowed per off-curve path"
        firstPts = (firstPts[0],) + tuple(reversed(firstPts[1:-1])) + (None,)

    if not contour:
        # contour contains only one segment, nothing to reverse
        if firstType == "moveTo":
            closed = False  # single-point paths can't be closed
        else:
            closed = True  # off-curve paths are closed by definition
        yield firstType, firstPts
    else:
        lastType, lastPts = contour[-1]
        lastOnCurve = lastPts[-1]
        if closed:
            # for closed paths, we keep the starting point
            yield firstType, firstPts
            if firstOnCurve != lastOnCurve:
                # emit an implied line between the last and first points
                yield "lineTo", (lastOnCurve,)
                contour[-1] = (lastType, tuple(lastPts[:-1]) + (firstOnCurve,))

            if len(contour) > 1:
                secondType, secondPts = contour[0]
            else:
                # contour has only two points, the second and last are the same
                secondType, secondPts = lastType, lastPts

            if not outputImpliedClosingLine:
                # if a lineTo follows the initial moveTo, after reversing it
                # will be implied by the closePath, so we don't emit one;
                # unless the lineTo and moveTo overlap, in which case we keep the
                # duplicate points
                if secondType == "lineTo" and firstPts != secondPts:
                    del contour[0]
                    if contour:
                        contour[-1] = (lastType, tuple(lastPts[:-1]) + secondPts)
        else:
            # for open paths, the last point will become the first
            yield firstType, (lastOnCurve,)
            contour[-1] = (lastType, tuple(lastPts[:-1]) + (firstOnCurve,))

        # we iterate over all segment pairs in reverse order, and yield
        # each one with the off-curve points reversed (if any), and
        # with the on-curve point of the following segment
        for (curType, curPts), (_, nextPts) in pairwise(contour, reverse=True):
            yield curType, tuple(reversed(curPts[:-1])) + (nextPts[-1],)

    yield "closePath" if closed else "endPath", ()
