from fontTools.pens.filterPen import FilterPen, FilterPointPen


__all__ = ["TransformPen", "TransformPointPen"]


class TransformPen(FilterPen):
    """Pen that transforms all coordinates using a Affine transformation,
    and passes them to another pen.
    """

    def __init__(self, outPen, transformation):
        """The 'outPen' argument is another pen object. It will receive the
        transformed coordinates. The 'transformation' argument can either
        be a six-tuple, or a fontTools.misc.transform.Transform object.
        """
        super(TransformPen, self).__init__(outPen)
        if not hasattr(transformation, "transformPoint"):
            from fontTools.misc.transform import Transform

            transformation = Transform(*transformation)
        self._transformation = transformation
        self._transformPoint = transformation.transformPoint
        self._stack = []

    def moveTo(self, pt):
        self._outPen.moveTo(self._transformPoint(pt))

    def lineTo(self, pt):
        self._outPen.lineTo(self._transformPoint(pt))

    def curveTo(self, *points):
        self._outPen.curveTo(*self._transformPoints(points))

    def qCurveTo(self, *points):
        if points[-1] is None:
            points = self._transformPoints(points[:-1]) + [None]
        else:
            points = self._transformPoints(points)
        self._outPen.qCurveTo(*points)

    def _transformPoints(self, points):
        transformPoint = self._transformPoint
        return [transformPoint(pt) for pt in points]

    def closePath(self):
        self._outPen.closePath()

    def endPath(self):
        self._outPen.endPath()

    def addComponent(self, glyphName, transformation):
        transformation = self._transformation.transform(transformation)
        self._outPen.addComponent(glyphName, transformation)


class TransformPointPen(FilterPointPen):
    """PointPen that transforms all coordinates using a Affine transformation,
    and passes them to another PointPen.

    For example::

        >>> from fontTools.pens.recordingPen import RecordingPointPen
        >>> rec = RecordingPointPen()
        >>> pen = TransformPointPen(rec, (2, 0, 0, 2, -10, 5))
        >>> v = iter(rec.value)
        >>> pen.beginPath(identifier="contour-0")
        >>> next(v)
        ('beginPath', (), {'identifier': 'contour-0'})

        >>> pen.addPoint((100, 100), "line")
        >>> next(v)
        ('addPoint', ((190, 205), 'line', False, None), {})

        >>> pen.endPath()
        >>> next(v)
        ('endPath', (), {})

        >>> pen.addComponent("a", (1, 0, 0, 1, -10, 5), identifier="component-0")
        >>> next(v)
        ('addComponent', ('a', <Transform [2 0 0 2 -30 15]>), {'identifier': 'component-0'})
    """

    def __init__(self, outPointPen, transformation):
        """The 'outPointPen' argument is another point pen object.
        It will receive the transformed coordinates.
        The 'transformation' argument can either be a six-tuple, or a
        fontTools.misc.transform.Transform object.
        """
        super().__init__(outPointPen)
        if not hasattr(transformation, "transformPoint"):
            from fontTools.misc.transform import Transform

            transformation = Transform(*transformation)
        self._transformation = transformation
        self._transformPoint = transformation.transformPoint

    def addPoint(self, pt, segmentType=None, smooth=False, name=None, **kwargs):
        self._outPen.addPoint(
            self._transformPoint(pt), segmentType, smooth, name, **kwargs
        )

    def addComponent(self, baseGlyphName, transformation, **kwargs):
        transformation = self._transformation.transform(transformation)
        self._outPen.addComponent(baseGlyphName, transformation, **kwargs)


if __name__ == "__main__":
    from fontTools.pens.basePen import _TestPen

    pen = TransformPen(_TestPen(None), (2, 0, 0.5, 2, -10, 0))
    pen.moveTo((0, 0))
    pen.lineTo((0, 100))
    pen.curveTo((50, 75), (60, 50), (50, 25), (0, 0))
    pen.closePath()
