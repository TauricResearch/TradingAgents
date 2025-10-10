from __future__ import annotations

from fontTools.pens.basePen import AbstractPen, DecomposingPen
from fontTools.pens.pointPen import (
    AbstractPointPen,
    DecomposingPointPen,
    ReverseFlipped,
)
from fontTools.pens.recordingPen import RecordingPen


class _PassThruComponentsMixin(object):
    def addComponent(self, glyphName, transformation, **kwargs):
        self._outPen.addComponent(glyphName, transformation, **kwargs)


class FilterPen(_PassThruComponentsMixin, AbstractPen):
    """Base class for pens that apply some transformation to the coordinates
    they receive and pass them to another pen.

    You can override any of its methods. The default implementation does
    nothing, but passes the commands unmodified to the other pen.

    >>> from fontTools.pens.recordingPen import RecordingPen
    >>> rec = RecordingPen()
    >>> pen = FilterPen(rec)
    >>> v = iter(rec.value)

    >>> pen.moveTo((0, 0))
    >>> next(v)
    ('moveTo', ((0, 0),))

    >>> pen.lineTo((1, 1))
    >>> next(v)
    ('lineTo', ((1, 1),))

    >>> pen.curveTo((2, 2), (3, 3), (4, 4))
    >>> next(v)
    ('curveTo', ((2, 2), (3, 3), (4, 4)))

    >>> pen.qCurveTo((5, 5), (6, 6), (7, 7), (8, 8))
    >>> next(v)
    ('qCurveTo', ((5, 5), (6, 6), (7, 7), (8, 8)))

    >>> pen.closePath()
    >>> next(v)
    ('closePath', ())

    >>> pen.moveTo((9, 9))
    >>> next(v)
    ('moveTo', ((9, 9),))

    >>> pen.endPath()
    >>> next(v)
    ('endPath', ())

    >>> pen.addComponent('foo', (1, 0, 0, 1, 0, 0))
    >>> next(v)
    ('addComponent', ('foo', (1, 0, 0, 1, 0, 0)))
    """

    def __init__(self, outPen):
        self._outPen = outPen
        self.current_pt = None

    def moveTo(self, pt):
        self._outPen.moveTo(pt)
        self.current_pt = pt

    def lineTo(self, pt):
        self._outPen.lineTo(pt)
        self.current_pt = pt

    def curveTo(self, *points):
        self._outPen.curveTo(*points)
        self.current_pt = points[-1]

    def qCurveTo(self, *points):
        self._outPen.qCurveTo(*points)
        self.current_pt = points[-1]

    def closePath(self):
        self._outPen.closePath()
        self.current_pt = None

    def endPath(self):
        self._outPen.endPath()
        self.current_pt = None


class ContourFilterPen(_PassThruComponentsMixin, RecordingPen):
    """A "buffered" filter pen that accumulates contour data, passes
    it through a ``filterContour`` method when the contour is closed or ended,
    and finally draws the result with the output pen.

    Components are passed through unchanged.
    """

    def __init__(self, outPen):
        super(ContourFilterPen, self).__init__()
        self._outPen = outPen

    def closePath(self):
        super(ContourFilterPen, self).closePath()
        self._flushContour()

    def endPath(self):
        super(ContourFilterPen, self).endPath()
        self._flushContour()

    def _flushContour(self):
        result = self.filterContour(self.value)
        if result is not None:
            self.value = result
        self.replay(self._outPen)
        self.value = []

    def filterContour(self, contour):
        """Subclasses must override this to perform the filtering.

        The contour is a list of pen (operator, operands) tuples.
        Operators are strings corresponding to the AbstractPen methods:
        "moveTo", "lineTo", "curveTo", "qCurveTo", "closePath" and
        "endPath". The operands are the positional arguments that are
        passed to each method.

        If the method doesn't return a value (i.e. returns None), it's
        assumed that the argument was modified in-place.
        Otherwise, the return value is drawn with the output pen.
        """
        return  # or return contour


class FilterPointPen(_PassThruComponentsMixin, AbstractPointPen):
    """Baseclass for point pens that apply some transformation to the
    coordinates they receive and pass them to another point pen.

    You can override any of its methods. The default implementation does
    nothing, but passes the commands unmodified to the other pen.

    >>> from fontTools.pens.recordingPen import RecordingPointPen
    >>> rec = RecordingPointPen()
    >>> pen = FilterPointPen(rec)
    >>> v = iter(rec.value)
    >>> pen.beginPath(identifier="abc")
    >>> next(v)
    ('beginPath', (), {'identifier': 'abc'})
    >>> pen.addPoint((1, 2), "line", False)
    >>> next(v)
    ('addPoint', ((1, 2), 'line', False, None), {})
    >>> pen.addComponent("a", (2, 0, 0, 2, 10, -10), identifier="0001")
    >>> next(v)
    ('addComponent', ('a', (2, 0, 0, 2, 10, -10)), {'identifier': '0001'})
    >>> pen.endPath()
    >>> next(v)
    ('endPath', (), {})
    """

    def __init__(self, outPen):
        self._outPen = outPen

    def beginPath(self, identifier=None, **kwargs):
        kwargs = dict(kwargs)
        if identifier is not None:
            kwargs["identifier"] = identifier
        self._outPen.beginPath(**kwargs)

    def endPath(self):
        self._outPen.endPath()

    def addPoint(
        self,
        pt,
        segmentType=None,
        smooth=False,
        name=None,
        identifier=None,
        **kwargs,
    ):
        kwargs = dict(kwargs)
        if identifier is not None:
            kwargs["identifier"] = identifier
        self._outPen.addPoint(pt, segmentType, smooth, name, **kwargs)


class _DecomposingFilterMixinBase:
    """Base mixin class with common `addComponent` logic for decomposing filter pens."""

    def addComponent(self, baseGlyphName, transformation, **kwargs):
        # only decompose the component if it's included in the set
        if self.include is None or baseGlyphName in self.include:
            # if we're decomposing nested components, temporarily set include to None
            include_bak = self.include
            if self.decomposeNested and self.include:
                self.include = None
            try:
                super().addComponent(baseGlyphName, transformation, **kwargs)
            finally:
                if self.include != include_bak:
                    self.include = include_bak
        else:
            _PassThruComponentsMixin.addComponent(
                self, baseGlyphName, transformation, **kwargs
            )


class _DecomposingFilterPenMixin(_DecomposingFilterMixinBase):
    """Mixin class that decomposes components as regular contours for segment pens.

    Used by DecomposingFilterPen.

    Takes two required parameters, another segment pen 'outPen' to draw
    with, and a 'glyphSet' dict of drawable glyph objects to draw components from.

    The 'skipMissingComponents' and 'reverseFlipped' optional arguments work the
    same as in the DecomposingPen. reverseFlipped is bool only (True/False).

    In addition, the decomposing filter pens also take the following two options:

    'include' is an optional set of component base glyph names to consider for
    decomposition; the default include=None means decompose all components no matter
    the base glyph name).

    'decomposeNested' (bool) controls whether to recurse decomposition into nested
    components of components (this only matters when 'include' was also provided);
    if False, only decompose top-level components included in the set, but not
    also their children.
    """

    # raises MissingComponentError if base glyph is not found in glyphSet
    skipMissingComponents = False

    def __init__(
        self,
        outPen,
        glyphSet,
        skipMissingComponents=None,
        reverseFlipped: bool = False,
        include: set[str] | None = None,
        decomposeNested: bool = True,
        **kwargs,
    ):
        assert isinstance(
            reverseFlipped, bool
        ), f"Expected bool, got {type(reverseFlipped).__name__}"
        super().__init__(
            outPen=outPen,
            glyphSet=glyphSet,
            skipMissingComponents=skipMissingComponents,
            reverseFlipped=reverseFlipped,
            **kwargs,
        )
        self.include = include
        self.decomposeNested = decomposeNested


class _DecomposingFilterPointPenMixin(_DecomposingFilterMixinBase):
    """Mixin class that decomposes components as regular contours for point pens.

    Takes two required parameters, another point pen 'outPen' to draw
    with, and a 'glyphSet' dict of drawable glyph objects to draw components from.

    The 'skipMissingComponents' and 'reverseFlipped' optional arguments work the
    same as in the DecomposingPointPen. reverseFlipped accepts bool | ReverseFlipped
    (see DecomposingPointPen).

    In addition, the decomposing filter pens also take the following two options:

    'include' is an optional set of component base glyph names to consider for
    decomposition; the default include=None means decompose all components no matter
    the base glyph name).

    'decomposeNested' (bool) controls whether to recurse decomposition into nested
    components of components (this only matters when 'include' was also provided);
    if False, only decompose top-level components included in the set, but not
    also their children.
    """

    # raises MissingComponentError if base glyph is not found in glyphSet
    skipMissingComponents = False

    def __init__(
        self,
        outPen,
        glyphSet,
        skipMissingComponents=None,
        reverseFlipped: bool | ReverseFlipped = False,
        include: set[str] | None = None,
        decomposeNested: bool = True,
        **kwargs,
    ):
        super().__init__(
            outPen=outPen,
            glyphSet=glyphSet,
            skipMissingComponents=skipMissingComponents,
            reverseFlipped=reverseFlipped,
            **kwargs,
        )
        self.include = include
        self.decomposeNested = decomposeNested


class DecomposingFilterPen(_DecomposingFilterPenMixin, DecomposingPen, FilterPen):
    """Filter pen that draws components as regular contours."""

    pass


class DecomposingFilterPointPen(
    _DecomposingFilterPointPenMixin, DecomposingPointPen, FilterPointPen
):
    """Filter point pen that draws components as regular contours."""

    pass


class ContourFilterPointPen(_PassThruComponentsMixin, AbstractPointPen):
    """A "buffered" filter point pen that accumulates contour data, passes
    it through a ``filterContour`` method when the contour is closed or ended,
    and finally draws the result with the output point pen.

    Components are passed through unchanged.

    The ``filterContour`` method can modify the contour in-place (return None)
    or return a new contour to replace it.
    """

    def __init__(self, outPen):
        self._outPen = outPen
        self.currentContour = None
        self.currentContourKwargs = None

    def beginPath(self, identifier=None, **kwargs):
        if self.currentContour is not None:
            raise ValueError("Path already begun")
        kwargs = dict(kwargs)
        if identifier is not None:
            kwargs["identifier"] = identifier
        self.currentContour = []
        self.currentContourKwargs = kwargs

    def endPath(self):
        if self.currentContour is None:
            raise ValueError("Path not begun")
        self._flushContour()
        self.currentContour = None
        self.currentContourKwargs = None

    def _flushContour(self):
        """Flush the current contour to the output pen."""
        result = self.filterContour(self.currentContour)
        if result is not None:
            self.currentContour = result

        # Draw the filtered contour
        self._outPen.beginPath(**self.currentContourKwargs)
        for pt, segmentType, smooth, name, kwargs in self.currentContour:
            self._outPen.addPoint(pt, segmentType, smooth, name, **kwargs)
        self._outPen.endPath()

    def filterContour(self, contour):
        """Subclasses must override this to perform the filtering.

        The contour is a list of (pt, segmentType, smooth, name, kwargs) tuples.
        If the method doesn't return a value (i.e. returns None), it's
        assumed that the contour was modified in-place.
        Otherwise, the return value replaces the original contour.
        """
        return  # or return contour

    def addPoint(
        self,
        pt,
        segmentType=None,
        smooth=False,
        name=None,
        identifier=None,
        **kwargs,
    ):
        if self.currentContour is None:
            raise ValueError("Path not begun")
        kwargs = dict(kwargs)
        if identifier is not None:
            kwargs["identifier"] = identifier
        self.currentContour.append((pt, segmentType, smooth, name, kwargs))


class OnCurveFirstPointPen(ContourFilterPointPen):
    """Filter point pen that ensures closed contours start with an on-curve point.

    If a closed contour starts with an off-curve point (segmentType=None), it rotates
    the points list so that the first on-curve point (segmentType != None) becomes
    the start point. Open contours and contours already starting with on-curve points
    are passed through unchanged.

    >>> from fontTools.pens.recordingPen import RecordingPointPen
    >>> rec = RecordingPointPen()
    >>> pen = OnCurveFirstPointPen(rec)
    >>> # Closed contour starting with off-curve - will be rotated
    >>> pen.beginPath()
    >>> pen.addPoint((0, 0), None)  # off-curve
    >>> pen.addPoint((100, 100), "line")  # on-curve - will become start
    >>> pen.addPoint((200, 0), None)  # off-curve
    >>> pen.addPoint((300, 100), "curve")  # on-curve
    >>> pen.endPath()
    >>> # The contour should now start with (100, 100) "line"
    >>> rec.value[0]
    ('beginPath', (), {})
    >>> rec.value[1]
    ('addPoint', ((100, 100), 'line', False, None), {})
    >>> rec.value[2]
    ('addPoint', ((200, 0), None, False, None), {})
    >>> rec.value[3]
    ('addPoint', ((300, 100), 'curve', False, None), {})
    >>> rec.value[4]
    ('addPoint', ((0, 0), None, False, None), {})
    """

    def filterContour(self, contour):
        """Rotate closed contour to start with first on-curve point if needed."""
        if not contour:
            return

        # Check if it's a closed contour (no "move" segmentType)
        is_closed = contour[0][1] != "move"

        if is_closed and contour[0][1] is None:
            # Closed contour starting with off-curve - need to rotate
            # Find the first on-curve point
            for i, (pt, segmentType, smooth, name, kwargs) in enumerate(contour):
                if segmentType is not None:
                    # Rotate the points list so it starts with the first on-curve point
                    return contour[i:] + contour[:i]
