# -*- coding: utf-8 -*-
"""fontTools.misc.bezierTools.py -- tools for working with Bezier path segments.
"""

from fontTools.misc.arrayTools import calcBounds, sectRect, rectArea
from fontTools.misc.transform import Identity
import math
from collections import namedtuple

try:
    import cython
except (AttributeError, ImportError):
    # if cython not installed, use mock module with no-op decorators and types
    from fontTools.misc import cython
COMPILED = cython.compiled


EPSILON = 1e-9


Intersection = namedtuple("Intersection", ["pt", "t1", "t2"])


__all__ = [
    "approximateCubicArcLength",
    "approximateCubicArcLengthC",
    "approximateQuadraticArcLength",
    "approximateQuadraticArcLengthC",
    "calcCubicArcLength",
    "calcCubicArcLengthC",
    "calcQuadraticArcLength",
    "calcQuadraticArcLengthC",
    "calcCubicBounds",
    "calcQuadraticBounds",
    "splitLine",
    "splitQuadratic",
    "splitCubic",
    "splitQuadraticAtT",
    "splitCubicAtT",
    "splitCubicAtTC",
    "splitCubicIntoTwoAtTC",
    "solveQuadratic",
    "solveCubic",
    "quadraticPointAtT",
    "cubicPointAtT",
    "cubicPointAtTC",
    "linePointAtT",
    "segmentPointAtT",
    "lineLineIntersections",
    "curveLineIntersections",
    "curveCurveIntersections",
    "segmentSegmentIntersections",
]


def calcCubicArcLength(pt1, pt2, pt3, pt4, tolerance=0.005):
    """Calculates the arc length for a cubic Bezier segment.

    Whereas :func:`approximateCubicArcLength` approximates the length, this
    function calculates it by "measuring", recursively dividing the curve
    until the divided segments are shorter than ``tolerance``.

    Args:
        pt1,pt2,pt3,pt4: Control points of the Bezier as 2D tuples.
        tolerance: Controls the precision of the calcuation.

    Returns:
        Arc length value.
    """
    return calcCubicArcLengthC(
        complex(*pt1), complex(*pt2), complex(*pt3), complex(*pt4), tolerance
    )


def _split_cubic_into_two(p0, p1, p2, p3):
    mid = (p0 + 3 * (p1 + p2) + p3) * 0.125
    deriv3 = (p3 + p2 - p1 - p0) * 0.125
    return (
        (p0, (p0 + p1) * 0.5, mid - deriv3, mid),
        (mid, mid + deriv3, (p2 + p3) * 0.5, p3),
    )


@cython.returns(cython.double)
@cython.locals(
    p0=cython.complex,
    p1=cython.complex,
    p2=cython.complex,
    p3=cython.complex,
)
@cython.locals(mult=cython.double, arch=cython.double, box=cython.double)
def _calcCubicArcLengthCRecurse(mult, p0, p1, p2, p3):
    arch = abs(p0 - p3)
    box = abs(p0 - p1) + abs(p1 - p2) + abs(p2 - p3)
    if arch * mult + EPSILON >= box:
        return (arch + box) * 0.5
    else:
        one, two = _split_cubic_into_two(p0, p1, p2, p3)
        return _calcCubicArcLengthCRecurse(mult, *one) + _calcCubicArcLengthCRecurse(
            mult, *two
        )


@cython.returns(cython.double)
@cython.locals(
    pt1=cython.complex,
    pt2=cython.complex,
    pt3=cython.complex,
    pt4=cython.complex,
)
@cython.locals(
    tolerance=cython.double,
    mult=cython.double,
)
def calcCubicArcLengthC(pt1, pt2, pt3, pt4, tolerance=0.005):
    """Calculates the arc length for a cubic Bezier segment.

    Args:
        pt1,pt2,pt3,pt4: Control points of the Bezier as complex numbers.
        tolerance: Controls the precision of the calcuation.

    Returns:
        Arc length value.
    """
    mult = 1.0 + 1.5 * tolerance  # The 1.5 is a empirical hack; no math
    return _calcCubicArcLengthCRecurse(mult, pt1, pt2, pt3, pt4)


epsilonDigits = 6
epsilon = 1e-10


@cython.cfunc
@cython.inline
@cython.returns(cython.double)
@cython.locals(v1=cython.complex, v2=cython.complex)
def _dot(v1, v2):
    return (v1 * v2.conjugate()).real


@cython.cfunc
@cython.inline
@cython.returns(cython.double)
@cython.locals(x=cython.double)
def _intSecAtan(x):
    # In : sympy.integrate(sp.sec(sp.atan(x)))
    # Out: x*sqrt(x**2 + 1)/2 + asinh(x)/2
    return x * math.sqrt(x**2 + 1) / 2 + math.asinh(x) / 2


def calcQuadraticArcLength(pt1, pt2, pt3):
    """Calculates the arc length for a quadratic Bezier segment.

    Args:
        pt1: Start point of the Bezier as 2D tuple.
        pt2: Handle point of the Bezier as 2D tuple.
        pt3: End point of the Bezier as 2D tuple.

    Returns:
        Arc length value.

    Example::

        >>> calcQuadraticArcLength((0, 0), (0, 0), (0, 0)) # empty segment
        0.0
        >>> calcQuadraticArcLength((0, 0), (50, 0), (80, 0)) # collinear points
        80.0
        >>> calcQuadraticArcLength((0, 0), (0, 50), (0, 80)) # collinear points vertical
        80.0
        >>> calcQuadraticArcLength((0, 0), (50, 20), (100, 40)) # collinear points
        107.70329614269008
        >>> calcQuadraticArcLength((0, 0), (0, 100), (100, 0))
        154.02976155645263
        >>> calcQuadraticArcLength((0, 0), (0, 50), (100, 0))
        120.21581243984076
        >>> calcQuadraticArcLength((0, 0), (50, -10), (80, 50))
        102.53273816445825
        >>> calcQuadraticArcLength((0, 0), (40, 0), (-40, 0)) # collinear points, control point outside
        66.66666666666667
        >>> calcQuadraticArcLength((0, 0), (40, 0), (0, 0)) # collinear points, looping back
        40.0
    """
    return calcQuadraticArcLengthC(complex(*pt1), complex(*pt2), complex(*pt3))


@cython.returns(cython.double)
@cython.locals(
    pt1=cython.complex,
    pt2=cython.complex,
    pt3=cython.complex,
    d0=cython.complex,
    d1=cython.complex,
    d=cython.complex,
    n=cython.complex,
)
@cython.locals(
    scale=cython.double,
    origDist=cython.double,
    a=cython.double,
    b=cython.double,
    x0=cython.double,
    x1=cython.double,
    Len=cython.double,
)
def calcQuadraticArcLengthC(pt1, pt2, pt3):
    """Calculates the arc length for a quadratic Bezier segment.

    Args:
        pt1: Start point of the Bezier as a complex number.
        pt2: Handle point of the Bezier as a complex number.
        pt3: End point of the Bezier as a complex number.

    Returns:
        Arc length value.
    """
    # Analytical solution to the length of a quadratic bezier.
    # Documentation: https://github.com/fonttools/fonttools/issues/3055
    d0 = pt2 - pt1
    d1 = pt3 - pt2
    d = d1 - d0
    n = d * 1j
    scale = abs(n)
    if scale == 0.0:
        return abs(pt3 - pt1)
    origDist = _dot(n, d0)
    if abs(origDist) < epsilon:
        if _dot(d0, d1) >= 0:
            return abs(pt3 - pt1)
        a, b = abs(d0), abs(d1)
        return (a * a + b * b) / (a + b)
    x0 = _dot(d, d0) / origDist
    x1 = _dot(d, d1) / origDist
    Len = abs(2 * (_intSecAtan(x1) - _intSecAtan(x0)) * origDist / (scale * (x1 - x0)))
    return Len


def approximateQuadraticArcLength(pt1, pt2, pt3):
    """Calculates the arc length for a quadratic Bezier segment.

    Uses Gauss-Legendre quadrature for a branch-free approximation.
    See :func:`calcQuadraticArcLength` for a slower but more accurate result.

    Args:
        pt1: Start point of the Bezier as 2D tuple.
        pt2: Handle point of the Bezier as 2D tuple.
        pt3: End point of the Bezier as 2D tuple.

    Returns:
        Approximate arc length value.
    """
    return approximateQuadraticArcLengthC(complex(*pt1), complex(*pt2), complex(*pt3))


@cython.returns(cython.double)
@cython.locals(
    pt1=cython.complex,
    pt2=cython.complex,
    pt3=cython.complex,
)
@cython.locals(
    v0=cython.double,
    v1=cython.double,
    v2=cython.double,
)
def approximateQuadraticArcLengthC(pt1, pt2, pt3):
    """Calculates the arc length for a quadratic Bezier segment.

    Uses Gauss-Legendre quadrature for a branch-free approximation.
    See :func:`calcQuadraticArcLength` for a slower but more accurate result.

    Args:
        pt1: Start point of the Bezier as a complex number.
        pt2: Handle point of the Bezier as a complex number.
        pt3: End point of the Bezier as a complex number.

    Returns:
        Approximate arc length value.
    """
    # This, essentially, approximates the length-of-derivative function
    # to be integrated with the best-matching fifth-degree polynomial
    # approximation of it.
    #
    # https://en.wikipedia.org/wiki/Gaussian_quadrature#Gauss.E2.80.93Legendre_quadrature

    # abs(BezierCurveC[2].diff(t).subs({t:T})) for T in sorted(.5, .5±sqrt(3/5)/2),
    # weighted 5/18, 8/18, 5/18 respectively.
    v0 = abs(
        -0.492943519233745 * pt1 + 0.430331482911935 * pt2 + 0.0626120363218102 * pt3
    )
    v1 = abs(pt3 - pt1) * 0.4444444444444444
    v2 = abs(
        -0.0626120363218102 * pt1 - 0.430331482911935 * pt2 + 0.492943519233745 * pt3
    )

    return v0 + v1 + v2


def calcQuadraticBounds(pt1, pt2, pt3):
    """Calculates the bounding rectangle for a quadratic Bezier segment.

    Args:
        pt1: Start point of the Bezier as a 2D tuple.
        pt2: Handle point of the Bezier as a 2D tuple.
        pt3: End point of the Bezier as a 2D tuple.

    Returns:
        A four-item tuple representing the bounding rectangle ``(xMin, yMin, xMax, yMax)``.

    Example::

        >>> calcQuadraticBounds((0, 0), (50, 100), (100, 0))
        (0, 0, 100, 50.0)
        >>> calcQuadraticBounds((0, 0), (100, 0), (100, 100))
        (0.0, 0.0, 100, 100)
    """
    (ax, ay), (bx, by), (cx, cy) = calcQuadraticParameters(pt1, pt2, pt3)
    ax2 = ax * 2.0
    ay2 = ay * 2.0
    roots = []
    if ax2 != 0:
        roots.append(-bx / ax2)
    if ay2 != 0:
        roots.append(-by / ay2)
    points = [
        (ax * t * t + bx * t + cx, ay * t * t + by * t + cy)
        for t in roots
        if 0 <= t < 1
    ] + [pt1, pt3]
    return calcBounds(points)


def approximateCubicArcLength(pt1, pt2, pt3, pt4):
    """Approximates the arc length for a cubic Bezier segment.

    Uses Gauss-Lobatto quadrature with n=5 points to approximate arc length.
    See :func:`calcCubicArcLength` for a slower but more accurate result.

    Args:
        pt1,pt2,pt3,pt4: Control points of the Bezier as 2D tuples.

    Returns:
        Arc length value.

    Example::

        >>> approximateCubicArcLength((0, 0), (25, 100), (75, 100), (100, 0))
        190.04332968932817
        >>> approximateCubicArcLength((0, 0), (50, 0), (100, 50), (100, 100))
        154.8852074945903
        >>> approximateCubicArcLength((0, 0), (50, 0), (100, 0), (150, 0)) # line; exact result should be 150.
        149.99999999999991
        >>> approximateCubicArcLength((0, 0), (50, 0), (100, 0), (-50, 0)) # cusp; exact result should be 150.
        136.9267662156362
        >>> approximateCubicArcLength((0, 0), (50, 0), (100, -50), (-50, 0)) # cusp
        154.80848416537057
    """
    return approximateCubicArcLengthC(
        complex(*pt1), complex(*pt2), complex(*pt3), complex(*pt4)
    )


@cython.returns(cython.double)
@cython.locals(
    pt1=cython.complex,
    pt2=cython.complex,
    pt3=cython.complex,
    pt4=cython.complex,
)
@cython.locals(
    v0=cython.double,
    v1=cython.double,
    v2=cython.double,
    v3=cython.double,
    v4=cython.double,
)
def approximateCubicArcLengthC(pt1, pt2, pt3, pt4):
    """Approximates the arc length for a cubic Bezier segment.

    Args:
        pt1,pt2,pt3,pt4: Control points of the Bezier as complex numbers.

    Returns:
        Arc length value.
    """
    # This, essentially, approximates the length-of-derivative function
    # to be integrated with the best-matching seventh-degree polynomial
    # approximation of it.
    #
    # https://en.wikipedia.org/wiki/Gaussian_quadrature#Gauss.E2.80.93Lobatto_rules

    # abs(BezierCurveC[3].diff(t).subs({t:T})) for T in sorted(0, .5±(3/7)**.5/2, .5, 1),
    # weighted 1/20, 49/180, 32/90, 49/180, 1/20 respectively.
    v0 = abs(pt2 - pt1) * 0.15
    v1 = abs(
        -0.558983582205757 * pt1
        + 0.325650248872424 * pt2
        + 0.208983582205757 * pt3
        + 0.024349751127576 * pt4
    )
    v2 = abs(pt4 - pt1 + pt3 - pt2) * 0.26666666666666666
    v3 = abs(
        -0.024349751127576 * pt1
        - 0.208983582205757 * pt2
        - 0.325650248872424 * pt3
        + 0.558983582205757 * pt4
    )
    v4 = abs(pt4 - pt3) * 0.15

    return v0 + v1 + v2 + v3 + v4


def calcCubicBounds(pt1, pt2, pt3, pt4):
    """Calculates the bounding rectangle for a quadratic Bezier segment.

    Args:
        pt1,pt2,pt3,pt4: Control points of the Bezier as 2D tuples.

    Returns:
        A four-item tuple representing the bounding rectangle ``(xMin, yMin, xMax, yMax)``.

    Example::

        >>> calcCubicBounds((0, 0), (25, 100), (75, 100), (100, 0))
        (0, 0, 100, 75.0)
        >>> calcCubicBounds((0, 0), (50, 0), (100, 50), (100, 100))
        (0.0, 0.0, 100, 100)
        >>> print("%f %f %f %f" % calcCubicBounds((50, 0), (0, 100), (100, 100), (50, 0)))
        35.566243 0.000000 64.433757 75.000000
    """
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = calcCubicParameters(pt1, pt2, pt3, pt4)
    # calc first derivative
    ax3 = ax * 3.0
    ay3 = ay * 3.0
    bx2 = bx * 2.0
    by2 = by * 2.0
    xRoots = [t for t in solveQuadratic(ax3, bx2, cx) if 0 <= t < 1]
    yRoots = [t for t in solveQuadratic(ay3, by2, cy) if 0 <= t < 1]
    roots = xRoots + yRoots

    points = [
        (
            ax * t * t * t + bx * t * t + cx * t + dx,
            ay * t * t * t + by * t * t + cy * t + dy,
        )
        for t in roots
    ] + [pt1, pt4]
    return calcBounds(points)


def splitLine(pt1, pt2, where, isHorizontal):
    """Split a line at a given coordinate.

    Args:
        pt1: Start point of line as 2D tuple.
        pt2: End point of line as 2D tuple.
        where: Position at which to split the line.
        isHorizontal: Direction of the ray splitting the line. If true,
            ``where`` is interpreted as a Y coordinate; if false, then
            ``where`` is interpreted as an X coordinate.

    Returns:
        A list of two line segments (each line segment being two 2D tuples)
        if the line was successfully split, or a list containing the original
        line.

    Example::

        >>> printSegments(splitLine((0, 0), (100, 100), 50, True))
        ((0, 0), (50, 50))
        ((50, 50), (100, 100))
        >>> printSegments(splitLine((0, 0), (100, 100), 100, True))
        ((0, 0), (100, 100))
        >>> printSegments(splitLine((0, 0), (100, 100), 0, True))
        ((0, 0), (0, 0))
        ((0, 0), (100, 100))
        >>> printSegments(splitLine((0, 0), (100, 100), 0, False))
        ((0, 0), (0, 0))
        ((0, 0), (100, 100))
        >>> printSegments(splitLine((100, 0), (0, 0), 50, False))
        ((100, 0), (50, 0))
        ((50, 0), (0, 0))
        >>> printSegments(splitLine((0, 100), (0, 0), 50, True))
        ((0, 100), (0, 50))
        ((0, 50), (0, 0))
    """
    pt1x, pt1y = pt1
    pt2x, pt2y = pt2

    ax = pt2x - pt1x
    ay = pt2y - pt1y

    bx = pt1x
    by = pt1y

    a = (ax, ay)[isHorizontal]

    if a == 0:
        return [(pt1, pt2)]
    t = (where - (bx, by)[isHorizontal]) / a
    if 0 <= t < 1:
        midPt = ax * t + bx, ay * t + by
        return [(pt1, midPt), (midPt, pt2)]
    else:
        return [(pt1, pt2)]


def splitQuadratic(pt1, pt2, pt3, where, isHorizontal):
    """Split a quadratic Bezier curve at a given coordinate.

    Args:
        pt1,pt2,pt3: Control points of the Bezier as 2D tuples.
        where: Position at which to split the curve.
        isHorizontal: Direction of the ray splitting the curve. If true,
            ``where`` is interpreted as a Y coordinate; if false, then
            ``where`` is interpreted as an X coordinate.

    Returns:
        A list of two curve segments (each curve segment being three 2D tuples)
        if the curve was successfully split, or a list containing the original
        curve.

    Example::

        >>> printSegments(splitQuadratic((0, 0), (50, 100), (100, 0), 150, False))
        ((0, 0), (50, 100), (100, 0))
        >>> printSegments(splitQuadratic((0, 0), (50, 100), (100, 0), 50, False))
        ((0, 0), (25, 50), (50, 50))
        ((50, 50), (75, 50), (100, 0))
        >>> printSegments(splitQuadratic((0, 0), (50, 100), (100, 0), 25, False))
        ((0, 0), (12.5, 25), (25, 37.5))
        ((25, 37.5), (62.5, 75), (100, 0))
        >>> printSegments(splitQuadratic((0, 0), (50, 100), (100, 0), 25, True))
        ((0, 0), (7.32233, 14.6447), (14.6447, 25))
        ((14.6447, 25), (50, 75), (85.3553, 25))
        ((85.3553, 25), (92.6777, 14.6447), (100, -7.10543e-15))
        >>> # XXX I'm not at all sure if the following behavior is desirable:
        >>> printSegments(splitQuadratic((0, 0), (50, 100), (100, 0), 50, True))
        ((0, 0), (25, 50), (50, 50))
        ((50, 50), (50, 50), (50, 50))
        ((50, 50), (75, 50), (100, 0))
    """
    a, b, c = calcQuadraticParameters(pt1, pt2, pt3)
    solutions = solveQuadratic(
        a[isHorizontal], b[isHorizontal], c[isHorizontal] - where
    )
    solutions = sorted(t for t in solutions if 0 <= t < 1)
    if not solutions:
        return [(pt1, pt2, pt3)]
    return _splitQuadraticAtT(a, b, c, *solutions)


def splitCubic(pt1, pt2, pt3, pt4, where, isHorizontal):
    """Split a cubic Bezier curve at a given coordinate.

    Args:
        pt1,pt2,pt3,pt4: Control points of the Bezier as 2D tuples.
        where: Position at which to split the curve.
        isHorizontal: Direction of the ray splitting the curve. If true,
            ``where`` is interpreted as a Y coordinate; if false, then
            ``where`` is interpreted as an X coordinate.

    Returns:
        A list of two curve segments (each curve segment being four 2D tuples)
        if the curve was successfully split, or a list containing the original
        curve.

    Example::

        >>> printSegments(splitCubic((0, 0), (25, 100), (75, 100), (100, 0), 150, False))
        ((0, 0), (25, 100), (75, 100), (100, 0))
        >>> printSegments(splitCubic((0, 0), (25, 100), (75, 100), (100, 0), 50, False))
        ((0, 0), (12.5, 50), (31.25, 75), (50, 75))
        ((50, 75), (68.75, 75), (87.5, 50), (100, 0))
        >>> printSegments(splitCubic((0, 0), (25, 100), (75, 100), (100, 0), 25, True))
        ((0, 0), (2.29379, 9.17517), (4.79804, 17.5085), (7.47414, 25))
        ((7.47414, 25), (31.2886, 91.6667), (68.7114, 91.6667), (92.5259, 25))
        ((92.5259, 25), (95.202, 17.5085), (97.7062, 9.17517), (100, 1.77636e-15))
    """
    a, b, c, d = calcCubicParameters(pt1, pt2, pt3, pt4)
    solutions = solveCubic(
        a[isHorizontal], b[isHorizontal], c[isHorizontal], d[isHorizontal] - where
    )
    solutions = sorted(t for t in solutions if 0 <= t < 1)
    if not solutions:
        return [(pt1, pt2, pt3, pt4)]
    return _splitCubicAtT(a, b, c, d, *solutions)


def splitQuadraticAtT(pt1, pt2, pt3, *ts):
    """Split a quadratic Bezier curve at one or more values of t.

    Args:
        pt1,pt2,pt3: Control points of the Bezier as 2D tuples.
        *ts: Positions at which to split the curve.

    Returns:
        A list of curve segments (each curve segment being three 2D tuples).

    Examples::

        >>> printSegments(splitQuadraticAtT((0, 0), (50, 100), (100, 0), 0.5))
        ((0, 0), (25, 50), (50, 50))
        ((50, 50), (75, 50), (100, 0))
        >>> printSegments(splitQuadraticAtT((0, 0), (50, 100), (100, 0), 0.5, 0.75))
        ((0, 0), (25, 50), (50, 50))
        ((50, 50), (62.5, 50), (75, 37.5))
        ((75, 37.5), (87.5, 25), (100, 0))
    """
    a, b, c = calcQuadraticParameters(pt1, pt2, pt3)
    return _splitQuadraticAtT(a, b, c, *ts)


def splitCubicAtT(pt1, pt2, pt3, pt4, *ts):
    """Split a cubic Bezier curve at one or more values of t.

    Args:
        pt1,pt2,pt3,pt4: Control points of the Bezier as 2D tuples.
        *ts: Positions at which to split the curve.

    Returns:
        A list of curve segments (each curve segment being four 2D tuples).

    Examples::

        >>> printSegments(splitCubicAtT((0, 0), (25, 100), (75, 100), (100, 0), 0.5))
        ((0, 0), (12.5, 50), (31.25, 75), (50, 75))
        ((50, 75), (68.75, 75), (87.5, 50), (100, 0))
        >>> printSegments(splitCubicAtT((0, 0), (25, 100), (75, 100), (100, 0), 0.5, 0.75))
        ((0, 0), (12.5, 50), (31.25, 75), (50, 75))
        ((50, 75), (59.375, 75), (68.75, 68.75), (77.3438, 56.25))
        ((77.3438, 56.25), (85.9375, 43.75), (93.75, 25), (100, 0))
    """
    a, b, c, d = calcCubicParameters(pt1, pt2, pt3, pt4)
    split = _splitCubicAtT(a, b, c, d, *ts)

    # the split impl can introduce floating point errors; we know the first
    # segment should always start at pt1 and the last segment should end at pt4,
    # so we set those values directly before returning.
    split[0] = (pt1, *split[0][1:])
    split[-1] = (*split[-1][:-1], pt4)
    return split


@cython.locals(
    pt1=cython.complex,
    pt2=cython.complex,
    pt3=cython.complex,
    pt4=cython.complex,
    a=cython.complex,
    b=cython.complex,
    c=cython.complex,
    d=cython.complex,
)
def splitCubicAtTC(pt1, pt2, pt3, pt4, *ts):
    """Split a cubic Bezier curve at one or more values of t.

    Args:
        pt1,pt2,pt3,pt4: Control points of the Bezier as complex numbers..
        *ts: Positions at which to split the curve.

    Yields:
        Curve segments (each curve segment being four complex numbers).
    """
    a, b, c, d = calcCubicParametersC(pt1, pt2, pt3, pt4)
    yield from _splitCubicAtTC(a, b, c, d, *ts)


@cython.returns(cython.complex)
@cython.locals(
    t=cython.double,
    pt1=cython.complex,
    pt2=cython.complex,
    pt3=cython.complex,
    pt4=cython.complex,
    pointAtT=cython.complex,
    off1=cython.complex,
    off2=cython.complex,
)
@cython.locals(
    t2=cython.double, _1_t=cython.double, _1_t_2=cython.double, _2_t_1_t=cython.double
)
def splitCubicIntoTwoAtTC(pt1, pt2, pt3, pt4, t):
    """Split a cubic Bezier curve at t.

    Args:
        pt1,pt2,pt3,pt4: Control points of the Bezier as complex numbers.
        t: Position at which to split the curve.

    Returns:
        A tuple of two curve segments (each curve segment being four complex numbers).
    """
    t2 = t * t
    _1_t = 1 - t
    _1_t_2 = _1_t * _1_t
    _2_t_1_t = 2 * t * _1_t
    pointAtT = (
        _1_t_2 * _1_t * pt1 + 3 * (_1_t_2 * t * pt2 + _1_t * t2 * pt3) + t2 * t * pt4
    )
    off1 = _1_t_2 * pt1 + _2_t_1_t * pt2 + t2 * pt3
    off2 = _1_t_2 * pt2 + _2_t_1_t * pt3 + t2 * pt4

    pt2 = pt1 + (pt2 - pt1) * t
    pt3 = pt4 + (pt3 - pt4) * _1_t

    return ((pt1, pt2, off1, pointAtT), (pointAtT, off2, pt3, pt4))


def _splitQuadraticAtT(a, b, c, *ts):
    ts = list(ts)
    segments = []
    ts.insert(0, 0.0)
    ts.append(1.0)
    ax, ay = a
    bx, by = b
    cx, cy = c
    for i in range(len(ts) - 1):
        t1 = ts[i]
        t2 = ts[i + 1]
        delta = t2 - t1
        # calc new a, b and c
        delta_2 = delta * delta
        a1x = ax * delta_2
        a1y = ay * delta_2
        b1x = (2 * ax * t1 + bx) * delta
        b1y = (2 * ay * t1 + by) * delta
        t1_2 = t1 * t1
        c1x = ax * t1_2 + bx * t1 + cx
        c1y = ay * t1_2 + by * t1 + cy

        pt1, pt2, pt3 = calcQuadraticPoints((a1x, a1y), (b1x, b1y), (c1x, c1y))
        segments.append((pt1, pt2, pt3))
    return segments


def _splitCubicAtT(a, b, c, d, *ts):
    ts = list(ts)
    ts.insert(0, 0.0)
    ts.append(1.0)
    segments = []
    ax, ay = a
    bx, by = b
    cx, cy = c
    dx, dy = d
    for i in range(len(ts) - 1):
        t1 = ts[i]
        t2 = ts[i + 1]
        delta = t2 - t1

        delta_2 = delta * delta
        delta_3 = delta * delta_2
        t1_2 = t1 * t1
        t1_3 = t1 * t1_2

        # calc new a, b, c and d
        a1x = ax * delta_3
        a1y = ay * delta_3
        b1x = (3 * ax * t1 + bx) * delta_2
        b1y = (3 * ay * t1 + by) * delta_2
        c1x = (2 * bx * t1 + cx + 3 * ax * t1_2) * delta
        c1y = (2 * by * t1 + cy + 3 * ay * t1_2) * delta
        d1x = ax * t1_3 + bx * t1_2 + cx * t1 + dx
        d1y = ay * t1_3 + by * t1_2 + cy * t1 + dy
        pt1, pt2, pt3, pt4 = calcCubicPoints(
            (a1x, a1y), (b1x, b1y), (c1x, c1y), (d1x, d1y)
        )
        segments.append((pt1, pt2, pt3, pt4))
    return segments


@cython.locals(
    a=cython.complex,
    b=cython.complex,
    c=cython.complex,
    d=cython.complex,
    t1=cython.double,
    t2=cython.double,
    delta=cython.double,
    delta_2=cython.double,
    delta_3=cython.double,
    a1=cython.complex,
    b1=cython.complex,
    c1=cython.complex,
    d1=cython.complex,
)
def _splitCubicAtTC(a, b, c, d, *ts):
    ts = list(ts)
    ts.insert(0, 0.0)
    ts.append(1.0)
    for i in range(len(ts) - 1):
        t1 = ts[i]
        t2 = ts[i + 1]
        delta = t2 - t1

        delta_2 = delta * delta
        delta_3 = delta * delta_2
        t1_2 = t1 * t1
        t1_3 = t1 * t1_2

        # calc new a, b, c and d
        a1 = a * delta_3
        b1 = (3 * a * t1 + b) * delta_2
        c1 = (2 * b * t1 + c + 3 * a * t1_2) * delta
        d1 = a * t1_3 + b * t1_2 + c * t1 + d
        pt1, pt2, pt3, pt4 = calcCubicPointsC(a1, b1, c1, d1)
        yield (pt1, pt2, pt3, pt4)


#
# Equation solvers.
#

from math import sqrt, acos, cos, pi


def solveQuadratic(a, b, c, sqrt=sqrt):
    """Solve a quadratic equation.

    Solves *a*x*x + b*x + c = 0* where a, b and c are real.

    Args:
        a: coefficient of *x²*
        b: coefficient of *x*
        c: constant term

    Returns:
        A list of roots. Note that the returned list is neither guaranteed to
        be sorted nor to contain unique values!
    """
    if abs(a) < epsilon:
        if abs(b) < epsilon:
            # We have a non-equation; therefore, we have no valid solution
            roots = []
        else:
            # We have a linear equation with 1 root.
            roots = [-c / b]
    else:
        # We have a true quadratic equation.  Apply the quadratic formula to find two roots.
        DD = b * b - 4.0 * a * c
        if DD >= 0.0:
            rDD = sqrt(DD)
            roots = [(-b + rDD) / 2.0 / a, (-b - rDD) / 2.0 / a]
        else:
            # complex roots, ignore
            roots = []
    return roots


def solveCubic(a, b, c, d):
    """Solve a cubic equation.

    Solves *a*x*x*x + b*x*x + c*x + d = 0* where a, b, c and d are real.

    Args:
        a: coefficient of *x³*
        b: coefficient of *x²*
        c: coefficient of *x*
        d: constant term

    Returns:
        A list of roots. Note that the returned list is neither guaranteed to
        be sorted nor to contain unique values!

    Examples::

        >>> solveCubic(1, 1, -6, 0)
        [-3.0, -0.0, 2.0]
        >>> solveCubic(-10.0, -9.0, 48.0, -29.0)
        [-2.9, 1.0, 1.0]
        >>> solveCubic(-9.875, -9.0, 47.625, -28.75)
        [-2.911392, 1.0, 1.0]
        >>> solveCubic(1.0, -4.5, 6.75, -3.375)
        [1.5, 1.5, 1.5]
        >>> solveCubic(-12.0, 18.0, -9.0, 1.50023651123)
        [0.5, 0.5, 0.5]
        >>> solveCubic(
        ...     9.0, 0.0, 0.0, -7.62939453125e-05
        ... ) == [-0.0, -0.0, -0.0]
        True
    """
    #
    # adapted from:
    #   CUBIC.C - Solve a cubic polynomial
    #   public domain by Ross Cottrell
    # found at: http://www.strangecreations.com/library/snippets/Cubic.C
    #
    if abs(a) < epsilon:
        # don't just test for zero; for very small values of 'a' solveCubic()
        # returns unreliable results, so we fall back to quad.
        return solveQuadratic(b, c, d)
    a = float(a)
    a1 = b / a
    a2 = c / a
    a3 = d / a

    Q = (a1 * a1 - 3.0 * a2) / 9.0
    R = (2.0 * a1 * a1 * a1 - 9.0 * a1 * a2 + 27.0 * a3) / 54.0

    R2 = R * R
    Q3 = Q * Q * Q
    R2 = 0 if R2 < epsilon else R2
    Q3 = 0 if abs(Q3) < epsilon else Q3

    R2_Q3 = R2 - Q3

    if R2 == 0.0 and Q3 == 0.0:
        x = round(-a1 / 3.0, epsilonDigits)
        return [x, x, x]
    elif R2_Q3 <= epsilon * 0.5:
        # The epsilon * .5 above ensures that Q3 is not zero.
        theta = acos(max(min(R / sqrt(Q3), 1.0), -1.0))
        rQ2 = -2.0 * sqrt(Q)
        a1_3 = a1 / 3.0
        x0 = rQ2 * cos(theta / 3.0) - a1_3
        x1 = rQ2 * cos((theta + 2.0 * pi) / 3.0) - a1_3
        x2 = rQ2 * cos((theta + 4.0 * pi) / 3.0) - a1_3
        x0, x1, x2 = sorted([x0, x1, x2])
        # Merge roots that are close-enough
        if x1 - x0 < epsilon and x2 - x1 < epsilon:
            x0 = x1 = x2 = round((x0 + x1 + x2) / 3.0, epsilonDigits)
        elif x1 - x0 < epsilon:
            x0 = x1 = round((x0 + x1) / 2.0, epsilonDigits)
            x2 = round(x2, epsilonDigits)
        elif x2 - x1 < epsilon:
            x0 = round(x0, epsilonDigits)
            x1 = x2 = round((x1 + x2) / 2.0, epsilonDigits)
        else:
            x0 = round(x0, epsilonDigits)
            x1 = round(x1, epsilonDigits)
            x2 = round(x2, epsilonDigits)
        return [x0, x1, x2]
    else:
        x = pow(sqrt(R2_Q3) + abs(R), 1 / 3.0)
        x = x + Q / x
        if R >= 0.0:
            x = -x
        x = round(x - a1 / 3.0, epsilonDigits)
        return [x]


#
# Conversion routines for points to parameters and vice versa
#


def calcQuadraticParameters(pt1, pt2, pt3):
    x2, y2 = pt2
    x3, y3 = pt3
    cx, cy = pt1
    bx = (x2 - cx) * 2.0
    by = (y2 - cy) * 2.0
    ax = x3 - cx - bx
    ay = y3 - cy - by
    return (ax, ay), (bx, by), (cx, cy)


def calcCubicParameters(pt1, pt2, pt3, pt4):
    x2, y2 = pt2
    x3, y3 = pt3
    x4, y4 = pt4
    dx, dy = pt1
    cx = (x2 - dx) * 3.0
    cy = (y2 - dy) * 3.0
    bx = (x3 - x2) * 3.0 - cx
    by = (y3 - y2) * 3.0 - cy
    ax = x4 - dx - cx - bx
    ay = y4 - dy - cy - by
    return (ax, ay), (bx, by), (cx, cy), (dx, dy)


@cython.cfunc
@cython.inline
@cython.locals(
    pt1=cython.complex,
    pt2=cython.complex,
    pt3=cython.complex,
    pt4=cython.complex,
    a=cython.complex,
    b=cython.complex,
    c=cython.complex,
)
def calcCubicParametersC(pt1, pt2, pt3, pt4):
    c = (pt2 - pt1) * 3.0
    b = (pt3 - pt2) * 3.0 - c
    a = pt4 - pt1 - c - b
    return (a, b, c, pt1)


def calcQuadraticPoints(a, b, c):
    ax, ay = a
    bx, by = b
    cx, cy = c
    x1 = cx
    y1 = cy
    x2 = (bx * 0.5) + cx
    y2 = (by * 0.5) + cy
    x3 = ax + bx + cx
    y3 = ay + by + cy
    return (x1, y1), (x2, y2), (x3, y3)


def calcCubicPoints(a, b, c, d):
    ax, ay = a
    bx, by = b
    cx, cy = c
    dx, dy = d
    x1 = dx
    y1 = dy
    x2 = (cx / 3.0) + dx
    y2 = (cy / 3.0) + dy
    x3 = (bx + cx) / 3.0 + x2
    y3 = (by + cy) / 3.0 + y2
    x4 = ax + dx + cx + bx
    y4 = ay + dy + cy + by
    return (x1, y1), (x2, y2), (x3, y3), (x4, y4)


@cython.cfunc
@cython.inline
@cython.locals(
    a=cython.complex,
    b=cython.complex,
    c=cython.complex,
    d=cython.complex,
    p2=cython.complex,
    p3=cython.complex,
    p4=cython.complex,
)
def calcCubicPointsC(a, b, c, d):
    p2 = c * (1 / 3) + d
    p3 = (b + c) * (1 / 3) + p2
    p4 = a + b + c + d
    return (d, p2, p3, p4)


#
# Point at time
#


def linePointAtT(pt1, pt2, t):
    """Finds the point at time `t` on a line.

    Args:
        pt1, pt2: Coordinates of the line as 2D tuples.
        t: The time along the line.

    Returns:
        A 2D tuple with the coordinates of the point.
    """
    return ((pt1[0] * (1 - t) + pt2[0] * t), (pt1[1] * (1 - t) + pt2[1] * t))


def quadraticPointAtT(pt1, pt2, pt3, t):
    """Finds the point at time `t` on a quadratic curve.

    Args:
        pt1, pt2, pt3: Coordinates of the curve as 2D tuples.
        t: The time along the curve.

    Returns:
        A 2D tuple with the coordinates of the point.
    """
    x = (1 - t) * (1 - t) * pt1[0] + 2 * (1 - t) * t * pt2[0] + t * t * pt3[0]
    y = (1 - t) * (1 - t) * pt1[1] + 2 * (1 - t) * t * pt2[1] + t * t * pt3[1]
    return (x, y)


def cubicPointAtT(pt1, pt2, pt3, pt4, t):
    """Finds the point at time `t` on a cubic curve.

    Args:
        pt1, pt2, pt3, pt4: Coordinates of the curve as 2D tuples.
        t: The time along the curve.

    Returns:
        A 2D tuple with the coordinates of the point.
    """
    t2 = t * t
    _1_t = 1 - t
    _1_t_2 = _1_t * _1_t
    x = (
        _1_t_2 * _1_t * pt1[0]
        + 3 * (_1_t_2 * t * pt2[0] + _1_t * t2 * pt3[0])
        + t2 * t * pt4[0]
    )
    y = (
        _1_t_2 * _1_t * pt1[1]
        + 3 * (_1_t_2 * t * pt2[1] + _1_t * t2 * pt3[1])
        + t2 * t * pt4[1]
    )
    return (x, y)


@cython.returns(cython.complex)
@cython.locals(
    t=cython.double,
    pt1=cython.complex,
    pt2=cython.complex,
    pt3=cython.complex,
    pt4=cython.complex,
)
@cython.locals(t2=cython.double, _1_t=cython.double, _1_t_2=cython.double)
def cubicPointAtTC(pt1, pt2, pt3, pt4, t):
    """Finds the point at time `t` on a cubic curve.

    Args:
        pt1, pt2, pt3, pt4: Coordinates of the curve as complex numbers.
        t: The time along the curve.

    Returns:
        A complex number with the coordinates of the point.
    """
    t2 = t * t
    _1_t = 1 - t
    _1_t_2 = _1_t * _1_t
    return _1_t_2 * _1_t * pt1 + 3 * (_1_t_2 * t * pt2 + _1_t * t2 * pt3) + t2 * t * pt4


def segmentPointAtT(seg, t):
    if len(seg) == 2:
        return linePointAtT(*seg, t)
    elif len(seg) == 3:
        return quadraticPointAtT(*seg, t)
    elif len(seg) == 4:
        return cubicPointAtT(*seg, t)
    raise ValueError("Unknown curve degree")


#
# Intersection finders
#


def _line_t_of_pt(s, e, pt):
    sx, sy = s
    ex, ey = e
    px, py = pt
    if abs(sx - ex) < epsilon and abs(sy - ey) < epsilon:
        # Line is a point!
        return -1
    # Use the largest
    if abs(sx - ex) > abs(sy - ey):
        return (px - sx) / (ex - sx)
    else:
        return (py - sy) / (ey - sy)


def _both_points_are_on_same_side_of_origin(a, b, origin):
    xDiff = (a[0] - origin[0]) * (b[0] - origin[0])
    yDiff = (a[1] - origin[1]) * (b[1] - origin[1])
    return not (xDiff <= 0.0 and yDiff <= 0.0)


def lineLineIntersections(s1, e1, s2, e2):
    """Finds intersections between two line segments.

    Args:
        s1, e1: Coordinates of the first line as 2D tuples.
        s2, e2: Coordinates of the second line as 2D tuples.

    Returns:
        A list of ``Intersection`` objects, each object having ``pt``, ``t1``
        and ``t2`` attributes containing the intersection point, time on first
        segment and time on second segment respectively.

    Examples::

        >>> a = lineLineIntersections( (310,389), (453, 222), (289, 251), (447, 367))
        >>> len(a)
        1
        >>> intersection = a[0]
        >>> intersection.pt
        (374.44882952482897, 313.73458370177315)
        >>> (intersection.t1, intersection.t2)
        (0.45069111555824465, 0.5408153767394238)
    """
    s1x, s1y = s1
    e1x, e1y = e1
    s2x, s2y = s2
    e2x, e2y = e2
    if (
        math.isclose(s2x, e2x) and math.isclose(s1x, e1x) and not math.isclose(s1x, s2x)
    ):  # Parallel vertical
        return []
    if (
        math.isclose(s2y, e2y) and math.isclose(s1y, e1y) and not math.isclose(s1y, s2y)
    ):  # Parallel horizontal
        return []
    if math.isclose(s2x, e2x) and math.isclose(s2y, e2y):  # Line segment is tiny
        return []
    if math.isclose(s1x, e1x) and math.isclose(s1y, e1y):  # Line segment is tiny
        return []
    if math.isclose(e1x, s1x):
        x = s1x
        slope34 = (e2y - s2y) / (e2x - s2x)
        y = slope34 * (x - s2x) + s2y
        pt = (x, y)
        return [
            Intersection(
                pt=pt, t1=_line_t_of_pt(s1, e1, pt), t2=_line_t_of_pt(s2, e2, pt)
            )
        ]
    if math.isclose(s2x, e2x):
        x = s2x
        slope12 = (e1y - s1y) / (e1x - s1x)
        y = slope12 * (x - s1x) + s1y
        pt = (x, y)
        return [
            Intersection(
                pt=pt, t1=_line_t_of_pt(s1, e1, pt), t2=_line_t_of_pt(s2, e2, pt)
            )
        ]

    slope12 = (e1y - s1y) / (e1x - s1x)
    slope34 = (e2y - s2y) / (e2x - s2x)
    if math.isclose(slope12, slope34):
        return []
    x = (slope12 * s1x - s1y - slope34 * s2x + s2y) / (slope12 - slope34)
    y = slope12 * (x - s1x) + s1y
    pt = (x, y)
    if _both_points_are_on_same_side_of_origin(
        pt, e1, s1
    ) and _both_points_are_on_same_side_of_origin(pt, s2, e2):
        return [
            Intersection(
                pt=pt, t1=_line_t_of_pt(s1, e1, pt), t2=_line_t_of_pt(s2, e2, pt)
            )
        ]
    return []


def _alignment_transformation(segment):
    # Returns a transformation which aligns a segment horizontally at the
    # origin. Apply this transformation to curves and root-find to find
    # intersections with the segment.
    start = segment[0]
    end = segment[-1]
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    return Identity.rotate(-angle).translate(-start[0], -start[1])


def _curve_line_intersections_t(curve, line):
    aligned_curve = _alignment_transformation(line).transformPoints(curve)
    if len(curve) == 3:
        a, b, c = calcQuadraticParameters(*aligned_curve)
        intersections = solveQuadratic(a[1], b[1], c[1])
    elif len(curve) == 4:
        a, b, c, d = calcCubicParameters(*aligned_curve)
        intersections = solveCubic(a[1], b[1], c[1], d[1])
    else:
        raise ValueError("Unknown curve degree")
    return sorted(i for i in intersections if 0.0 <= i <= 1)


def curveLineIntersections(curve, line):
    """Finds intersections between a curve and a line.

    Args:
        curve: List of coordinates of the curve segment as 2D tuples.
        line: List of coordinates of the line segment as 2D tuples.

    Returns:
        A list of ``Intersection`` objects, each object having ``pt``, ``t1``
        and ``t2`` attributes containing the intersection point, time on first
        segment and time on second segment respectively.

    Examples::
        >>> curve = [ (100, 240), (30, 60), (210, 230), (160, 30) ]
        >>> line  = [ (25, 260), (230, 20) ]
        >>> intersections = curveLineIntersections(curve, line)
        >>> len(intersections)
        3
        >>> intersections[0].pt
        (84.9000930760723, 189.87306176459828)
    """
    if len(curve) == 3:
        pointFinder = quadraticPointAtT
    elif len(curve) == 4:
        pointFinder = cubicPointAtT
    else:
        raise ValueError("Unknown curve degree")
    intersections = []
    for t in _curve_line_intersections_t(curve, line):
        pt = pointFinder(*curve, t)
        # Back-project the point onto the line, to avoid problems with
        # numerical accuracy in the case of vertical and horizontal lines
        line_t = _line_t_of_pt(*line, pt)
        pt = linePointAtT(*line, line_t)
        intersections.append(Intersection(pt=pt, t1=t, t2=line_t))
    return intersections


def _curve_bounds(c):
    if len(c) == 3:
        return calcQuadraticBounds(*c)
    elif len(c) == 4:
        return calcCubicBounds(*c)
    raise ValueError("Unknown curve degree")


def _split_segment_at_t(c, t):
    if len(c) == 2:
        s, e = c
        midpoint = linePointAtT(s, e, t)
        return [(s, midpoint), (midpoint, e)]
    if len(c) == 3:
        return splitQuadraticAtT(*c, t)
    elif len(c) == 4:
        return splitCubicAtT(*c, t)
    raise ValueError("Unknown curve degree")


def _curve_curve_intersections_t(
    curve1, curve2, precision=1e-3, range1=None, range2=None
):
    bounds1 = _curve_bounds(curve1)
    bounds2 = _curve_bounds(curve2)

    if not range1:
        range1 = (0.0, 1.0)
    if not range2:
        range2 = (0.0, 1.0)

    # If bounds don't intersect, go home
    intersects, _ = sectRect(bounds1, bounds2)
    if not intersects:
        return []

    def midpoint(r):
        return 0.5 * (r[0] + r[1])

    # If they do overlap but they're tiny, approximate
    if rectArea(bounds1) < precision and rectArea(bounds2) < precision:
        return [(midpoint(range1), midpoint(range2))]

    c11, c12 = _split_segment_at_t(curve1, 0.5)
    c11_range = (range1[0], midpoint(range1))
    c12_range = (midpoint(range1), range1[1])

    c21, c22 = _split_segment_at_t(curve2, 0.5)
    c21_range = (range2[0], midpoint(range2))
    c22_range = (midpoint(range2), range2[1])

    found = []
    found.extend(
        _curve_curve_intersections_t(
            c11, c21, precision, range1=c11_range, range2=c21_range
        )
    )
    found.extend(
        _curve_curve_intersections_t(
            c12, c21, precision, range1=c12_range, range2=c21_range
        )
    )
    found.extend(
        _curve_curve_intersections_t(
            c11, c22, precision, range1=c11_range, range2=c22_range
        )
    )
    found.extend(
        _curve_curve_intersections_t(
            c12, c22, precision, range1=c12_range, range2=c22_range
        )
    )

    unique_key = lambda ts: (int(ts[0] / precision), int(ts[1] / precision))
    seen = set()
    unique_values = []

    for ts in found:
        key = unique_key(ts)
        if key in seen:
            continue
        seen.add(key)
        unique_values.append(ts)

    return unique_values


def _is_linelike(segment):
    maybeline = _alignment_transformation(segment).transformPoints(segment)
    return all(math.isclose(p[1], 0.0) for p in maybeline)


def curveCurveIntersections(curve1, curve2):
    """Finds intersections between a curve and a curve.

    Args:
        curve1: List of coordinates of the first curve segment as 2D tuples.
        curve2: List of coordinates of the second curve segment as 2D tuples.

    Returns:
        A list of ``Intersection`` objects, each object having ``pt``, ``t1``
        and ``t2`` attributes containing the intersection point, time on first
        segment and time on second segment respectively.

    Examples::
        >>> curve1 = [ (10,100), (90,30), (40,140), (220,220) ]
        >>> curve2 = [ (5,150), (180,20), (80,250), (210,190) ]
        >>> intersections = curveCurveIntersections(curve1, curve2)
        >>> len(intersections)
        3
        >>> intersections[0].pt
        (81.7831487395506, 109.88904552375288)
    """
    if _is_linelike(curve1):
        line1 = curve1[0], curve1[-1]
        if _is_linelike(curve2):
            line2 = curve2[0], curve2[-1]
            return lineLineIntersections(*line1, *line2)
        else:
            return curveLineIntersections(curve2, line1)
    elif _is_linelike(curve2):
        line2 = curve2[0], curve2[-1]
        return curveLineIntersections(curve1, line2)

    intersection_ts = _curve_curve_intersections_t(curve1, curve2)
    return [
        Intersection(pt=segmentPointAtT(curve1, ts[0]), t1=ts[0], t2=ts[1])
        for ts in intersection_ts
    ]


def segmentSegmentIntersections(seg1, seg2):
    """Finds intersections between two segments.

    Args:
        seg1: List of coordinates of the first segment as 2D tuples.
        seg2: List of coordinates of the second segment as 2D tuples.

    Returns:
        A list of ``Intersection`` objects, each object having ``pt``, ``t1``
        and ``t2`` attributes containing the intersection point, time on first
        segment and time on second segment respectively.

    Examples::
        >>> curve1 = [ (10,100), (90,30), (40,140), (220,220) ]
        >>> curve2 = [ (5,150), (180,20), (80,250), (210,190) ]
        >>> intersections = segmentSegmentIntersections(curve1, curve2)
        >>> len(intersections)
        3
        >>> intersections[0].pt
        (81.7831487395506, 109.88904552375288)
        >>> curve3 = [ (100, 240), (30, 60), (210, 230), (160, 30) ]
        >>> line  = [ (25, 260), (230, 20) ]
        >>> intersections = segmentSegmentIntersections(curve3, line)
        >>> len(intersections)
        3
        >>> intersections[0].pt
        (84.9000930760723, 189.87306176459828)

    """
    # Arrange by degree
    swapped = False
    if len(seg2) > len(seg1):
        seg2, seg1 = seg1, seg2
        swapped = True
    if len(seg1) > 2:
        if len(seg2) > 2:
            intersections = curveCurveIntersections(seg1, seg2)
        else:
            intersections = curveLineIntersections(seg1, seg2)
    elif len(seg1) == 2 and len(seg2) == 2:
        intersections = lineLineIntersections(*seg1, *seg2)
    else:
        raise ValueError("Couldn't work out which intersection function to use")
    if not swapped:
        return intersections
    return [Intersection(pt=i.pt, t1=i.t2, t2=i.t1) for i in intersections]


def _segmentrepr(obj):
    """
    >>> _segmentrepr([1, [2, 3], [], [[2, [3, 4], [0.1, 2.2]]]])
    '(1, (2, 3), (), ((2, (3, 4), (0.1, 2.2))))'
    """
    try:
        it = iter(obj)
    except TypeError:
        return "%g" % obj
    else:
        return "(%s)" % ", ".join(_segmentrepr(x) for x in it)


def printSegments(segments):
    """Helper for the doctests, displaying each segment in a list of
    segments on a single line as a tuple.
    """
    for segment in segments:
        print(_segmentrepr(segment))


if __name__ == "__main__":
    import sys
    import doctest

    sys.exit(doctest.testmod().failed)
