# cython: language_level=3
# distutils: define_macros=CYTHON_TRACE_NOGIL=1

# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

try:
    import cython
except (AttributeError, ImportError):
    # if cython not installed, use mock module with no-op decorators and types
    from fontTools.misc import cython
COMPILED = cython.compiled

import math

from .errors import Error as Cu2QuError, ApproxNotFoundError


__all__ = ["curve_to_quadratic", "curves_to_quadratic"]

MAX_N = 100

NAN = float("NaN")


@cython.cfunc
@cython.inline
@cython.returns(cython.double)
@cython.locals(v1=cython.complex, v2=cython.complex, result=cython.double)
def dot(v1, v2):
    """Return the dot product of two vectors.

    Args:
        v1 (complex): First vector.
        v2 (complex): Second vector.

    Returns:
        double: Dot product.
    """
    result = (v1 * v2.conjugate()).real
    # When vectors are perpendicular (i.e. dot product is 0), the above expression may
    # yield slightly different results when running in pure Python vs C/Cython,
    # both of which are correct within IEEE-754 floating-point precision.
    # It's probably due to the different order of operations and roundings in each
    # implementation. Because we are using the result in a denominator and catching
    # ZeroDivisionError (see `calc_intersect`), it's best to normalize the result here.
    if abs(result) < 1e-15:
        result = 0.0
    return result


@cython.cfunc
@cython.locals(z=cython.complex, den=cython.double)
@cython.locals(zr=cython.double, zi=cython.double)
def _complex_div_by_real(z, den):
    """Divide complex by real using Python's method (two separate divisions).

    This ensures bit-exact compatibility with Python's complex division,
    avoiding C's multiply-by-reciprocal optimization that can cause 1 ULP differences
    on some platforms/compilers (e.g. clang on macOS arm64).

    https://github.com/fonttools/fonttools/issues/3928
    """
    zr = z.real
    zi = z.imag
    return complex(zr / den, zi / den)


@cython.cfunc
@cython.inline
@cython.locals(a=cython.complex, b=cython.complex, c=cython.complex, d=cython.complex)
@cython.locals(
    _1=cython.complex, _2=cython.complex, _3=cython.complex, _4=cython.complex
)
def calc_cubic_points(a, b, c, d):
    _1 = d
    _2 = _complex_div_by_real(c, 3.0) + d
    _3 = _complex_div_by_real(b + c, 3.0) + _2
    _4 = a + d + c + b
    return _1, _2, _3, _4


@cython.cfunc
@cython.inline
@cython.locals(
    p0=cython.complex, p1=cython.complex, p2=cython.complex, p3=cython.complex
)
@cython.locals(a=cython.complex, b=cython.complex, c=cython.complex, d=cython.complex)
def calc_cubic_parameters(p0, p1, p2, p3):
    c = (p1 - p0) * 3.0
    b = (p2 - p1) * 3.0 - c
    d = p0
    a = p3 - d - c - b
    return a, b, c, d


@cython.cfunc
@cython.inline
@cython.locals(
    p0=cython.complex, p1=cython.complex, p2=cython.complex, p3=cython.complex
)
def split_cubic_into_n_iter(p0, p1, p2, p3, n):
    """Split a cubic Bezier into n equal parts.

    Splits the curve into `n` equal parts by curve time.
    (t=0..1/n, t=1/n..2/n, ...)

    Args:
        p0 (complex): Start point of curve.
        p1 (complex): First handle of curve.
        p2 (complex): Second handle of curve.
        p3 (complex): End point of curve.

    Returns:
        An iterator yielding the control points (four complex values) of the
        subcurves.
    """
    # Hand-coded special-cases
    if n == 2:
        return iter(split_cubic_into_two(p0, p1, p2, p3))
    if n == 3:
        return iter(split_cubic_into_three(p0, p1, p2, p3))
    if n == 4:
        a, b = split_cubic_into_two(p0, p1, p2, p3)
        return iter(
            split_cubic_into_two(a[0], a[1], a[2], a[3])
            + split_cubic_into_two(b[0], b[1], b[2], b[3])
        )
    if n == 6:
        a, b = split_cubic_into_two(p0, p1, p2, p3)
        return iter(
            split_cubic_into_three(a[0], a[1], a[2], a[3])
            + split_cubic_into_three(b[0], b[1], b[2], b[3])
        )

    return _split_cubic_into_n_gen(p0, p1, p2, p3, n)


@cython.locals(
    p0=cython.complex,
    p1=cython.complex,
    p2=cython.complex,
    p3=cython.complex,
    n=cython.int,
)
@cython.locals(a=cython.complex, b=cython.complex, c=cython.complex, d=cython.complex)
@cython.locals(
    dt=cython.double, delta_2=cython.double, delta_3=cython.double, i=cython.int
)
@cython.locals(
    a1=cython.complex, b1=cython.complex, c1=cython.complex, d1=cython.complex
)
def _split_cubic_into_n_gen(p0, p1, p2, p3, n):
    a, b, c, d = calc_cubic_parameters(p0, p1, p2, p3)
    dt = 1 / n
    delta_2 = dt * dt
    delta_3 = dt * delta_2
    for i in range(n):
        t1 = i * dt
        t1_2 = t1 * t1
        # calc new a, b, c and d
        a1 = a * delta_3
        b1 = (3 * a * t1 + b) * delta_2
        c1 = (2 * b * t1 + c + 3 * a * t1_2) * dt
        d1 = a * t1 * t1_2 + b * t1_2 + c * t1 + d
        yield calc_cubic_points(a1, b1, c1, d1)


@cython.cfunc
@cython.inline
@cython.locals(
    p0=cython.complex, p1=cython.complex, p2=cython.complex, p3=cython.complex
)
@cython.locals(mid=cython.complex, deriv3=cython.complex)
def split_cubic_into_two(p0, p1, p2, p3):
    """Split a cubic Bezier into two equal parts.

    Splits the curve into two equal parts at t = 0.5

    Args:
        p0 (complex): Start point of curve.
        p1 (complex): First handle of curve.
        p2 (complex): Second handle of curve.
        p3 (complex): End point of curve.

    Returns:
        tuple: Two cubic Beziers (each expressed as a tuple of four complex
        values).
    """
    mid = (p0 + 3 * (p1 + p2) + p3) * 0.125
    deriv3 = (p3 + p2 - p1 - p0) * 0.125
    return (
        (p0, (p0 + p1) * 0.5, mid - deriv3, mid),
        (mid, mid + deriv3, (p2 + p3) * 0.5, p3),
    )


@cython.cfunc
@cython.inline
@cython.locals(
    p0=cython.complex,
    p1=cython.complex,
    p2=cython.complex,
    p3=cython.complex,
)
@cython.locals(
    mid1=cython.complex,
    deriv1=cython.complex,
    mid2=cython.complex,
    deriv2=cython.complex,
)
def split_cubic_into_three(p0, p1, p2, p3):
    """Split a cubic Bezier into three equal parts.

    Splits the curve into three equal parts at t = 1/3 and t = 2/3

    Args:
        p0 (complex): Start point of curve.
        p1 (complex): First handle of curve.
        p2 (complex): Second handle of curve.
        p3 (complex): End point of curve.

    Returns:
        tuple: Three cubic Beziers (each expressed as a tuple of four complex
        values).
    """
    mid1 = (8 * p0 + 12 * p1 + 6 * p2 + p3) * (1 / 27)
    deriv1 = (p3 + 3 * p2 - 4 * p0) * (1 / 27)
    mid2 = (p0 + 6 * p1 + 12 * p2 + 8 * p3) * (1 / 27)
    deriv2 = (4 * p3 - 3 * p1 - p0) * (1 / 27)
    return (
        (p0, (2 * p0 + p1) / 3.0, mid1 - deriv1, mid1),
        (mid1, mid1 + deriv1, mid2 - deriv2, mid2),
        (mid2, mid2 + deriv2, (p2 + 2 * p3) / 3.0, p3),
    )


@cython.cfunc
@cython.inline
@cython.returns(cython.complex)
@cython.locals(
    t=cython.double,
    p0=cython.complex,
    p1=cython.complex,
    p2=cython.complex,
    p3=cython.complex,
)
@cython.locals(_p1=cython.complex, _p2=cython.complex)
def cubic_approx_control(t, p0, p1, p2, p3):
    """Approximate a cubic Bezier using a quadratic one.

    Args:
        t (double): Position of control point.
        p0 (complex): Start point of curve.
        p1 (complex): First handle of curve.
        p2 (complex): Second handle of curve.
        p3 (complex): End point of curve.

    Returns:
        complex: Location of candidate control point on quadratic curve.
    """
    _p1 = p0 + (p1 - p0) * 1.5
    _p2 = p3 + (p2 - p3) * 1.5
    return _p1 + (_p2 - _p1) * t


@cython.cfunc
@cython.inline
@cython.returns(cython.complex)
@cython.locals(a=cython.complex, b=cython.complex, c=cython.complex, d=cython.complex)
@cython.locals(ab=cython.complex, cd=cython.complex, p=cython.complex, h=cython.double)
def calc_intersect(a, b, c, d):
    """Calculate the intersection of two lines.

    Args:
        a (complex): Start point of first line.
        b (complex): End point of first line.
        c (complex): Start point of second line.
        d (complex): End point of second line.

    Returns:
        complex: Location of intersection if one present, ``complex(NaN,NaN)``
        if no intersection was found.
    """
    ab = b - a
    cd = d - c
    p = ab * 1j
    try:
        h = dot(p, a - c) / dot(p, cd)
    except ZeroDivisionError:
        # if 3 or 4 points are equal, we do have an intersection despite the zero-div:
        # return one of the off-curves so that the algorithm can attempt a one-curve
        # solution if it's within tolerance:
        # https://github.com/linebender/kurbo/pull/484
        if b == c and (a == b or c == d):
            return b
        return complex(NAN, NAN)
    return c + cd * h


@cython.cfunc
@cython.returns(cython.int)
@cython.locals(
    tolerance=cython.double,
    p0=cython.complex,
    p1=cython.complex,
    p2=cython.complex,
    p3=cython.complex,
)
@cython.locals(mid=cython.complex, deriv3=cython.complex)
def cubic_farthest_fit_inside(p0, p1, p2, p3, tolerance):
    """Check if a cubic Bezier lies within a given distance of the origin.

    "Origin" means *the* origin (0,0), not the start of the curve. Note that no
    checks are made on the start and end positions of the curve; this function
    only checks the inside of the curve.

    Args:
        p0 (complex): Start point of curve.
        p1 (complex): First handle of curve.
        p2 (complex): Second handle of curve.
        p3 (complex): End point of curve.
        tolerance (double): Distance from origin.

    Returns:
        bool: True if the cubic Bezier ``p`` entirely lies within a distance
        ``tolerance`` of the origin, False otherwise.
    """
    # First check p2 then p1, as p2 has higher error early on.
    if abs(p2) <= tolerance and abs(p1) <= tolerance:
        return True

    # Split.
    mid = (p0 + 3 * (p1 + p2) + p3) * 0.125
    if abs(mid) > tolerance:
        return False
    deriv3 = (p3 + p2 - p1 - p0) * 0.125
    return cubic_farthest_fit_inside(
        p0, (p0 + p1) * 0.5, mid - deriv3, mid, tolerance
    ) and cubic_farthest_fit_inside(mid, mid + deriv3, (p2 + p3) * 0.5, p3, tolerance)


@cython.cfunc
@cython.inline
@cython.locals(tolerance=cython.double)
@cython.locals(
    q1=cython.complex,
    c0=cython.complex,
    c1=cython.complex,
    c2=cython.complex,
    c3=cython.complex,
)
def cubic_approx_quadratic(cubic, tolerance):
    """Approximate a cubic Bezier with a single quadratic within a given tolerance.

    Args:
        cubic (sequence): Four complex numbers representing control points of
            the cubic Bezier curve.
        tolerance (double): Permitted deviation from the original curve.

    Returns:
        Three complex numbers representing control points of the quadratic
        curve if it fits within the given tolerance, or ``None`` if no suitable
        curve could be calculated.
    """

    q1 = calc_intersect(cubic[0], cubic[1], cubic[2], cubic[3])
    if math.isnan(q1.imag):
        return None
    c0 = cubic[0]
    c3 = cubic[3]
    c1 = c0 + (q1 - c0) * (2 / 3)
    c2 = c3 + (q1 - c3) * (2 / 3)
    if not cubic_farthest_fit_inside(0, c1 - cubic[1], c2 - cubic[2], 0, tolerance):
        return None
    return c0, q1, c3


@cython.cfunc
@cython.locals(n=cython.int, tolerance=cython.double)
@cython.locals(i=cython.int)
@cython.locals(all_quadratic=cython.int)
@cython.locals(
    c0=cython.complex, c1=cython.complex, c2=cython.complex, c3=cython.complex
)
@cython.locals(
    q0=cython.complex,
    q1=cython.complex,
    next_q1=cython.complex,
    q2=cython.complex,
    d1=cython.complex,
)
def cubic_approx_spline(cubic, n, tolerance, all_quadratic):
    """Approximate a cubic Bezier curve with a spline of n quadratics.

    Args:
        cubic (sequence): Four complex numbers representing control points of
            the cubic Bezier curve.
        n (int): Number of quadratic Bezier curves in the spline.
        tolerance (double): Permitted deviation from the original curve.

    Returns:
        A list of ``n+2`` complex numbers, representing control points of the
        quadratic spline if it fits within the given tolerance, or ``None`` if
        no suitable spline could be calculated.
    """

    if n == 1:
        return cubic_approx_quadratic(cubic, tolerance)
    if n == 2 and all_quadratic == False:
        return cubic

    cubics = split_cubic_into_n_iter(cubic[0], cubic[1], cubic[2], cubic[3], n)

    # calculate the spline of quadratics and check errors at the same time.
    next_cubic = next(cubics)
    next_q1 = cubic_approx_control(
        0, next_cubic[0], next_cubic[1], next_cubic[2], next_cubic[3]
    )
    q2 = cubic[0]
    d1 = 0j
    spline = [cubic[0], next_q1]
    for i in range(1, n + 1):
        # Current cubic to convert
        c0, c1, c2, c3 = next_cubic

        # Current quadratic approximation of current cubic
        q0 = q2
        q1 = next_q1
        if i < n:
            next_cubic = next(cubics)
            next_q1 = cubic_approx_control(
                i / (n - 1), next_cubic[0], next_cubic[1], next_cubic[2], next_cubic[3]
            )
            spline.append(next_q1)
            q2 = (q1 + next_q1) * 0.5
        else:
            q2 = c3

        # End-point deltas
        d0 = d1
        d1 = q2 - c3

        if abs(d1) > tolerance or not cubic_farthest_fit_inside(
            d0,
            q0 + (q1 - q0) * (2 / 3) - c1,
            q2 + (q1 - q2) * (2 / 3) - c2,
            d1,
            tolerance,
        ):
            return None
    spline.append(cubic[3])

    return spline


@cython.locals(max_err=cython.double)
@cython.locals(n=cython.int)
@cython.locals(all_quadratic=cython.int)
def curve_to_quadratic(curve, max_err, all_quadratic=True):
    """Approximate a cubic Bezier curve with a spline of n quadratics.

    Args:
        cubic (sequence): Four 2D tuples representing control points of
            the cubic Bezier curve.
        max_err (double): Permitted deviation from the original curve.
        all_quadratic (bool): If True (default) returned value is a
            quadratic spline. If False, it's either a single quadratic
            curve or a single cubic curve.

    Returns:
        If all_quadratic is True: A list of 2D tuples, representing
        control points of the quadratic spline if it fits within the
        given tolerance, or ``None`` if no suitable spline could be
        calculated.

        If all_quadratic is False: Either a quadratic curve (if length
        of output is 3), or a cubic curve (if length of output is 4).
    """

    curve = [complex(*p) for p in curve]

    for n in range(1, MAX_N + 1):
        spline = cubic_approx_spline(curve, n, max_err, all_quadratic)
        if spline is not None:
            # done. go home
            return [(s.real, s.imag) for s in spline]

    raise ApproxNotFoundError(curve)


@cython.locals(l=cython.int, last_i=cython.int, i=cython.int)
@cython.locals(all_quadratic=cython.int)
def curves_to_quadratic(curves, max_errors, all_quadratic=True):
    """Return quadratic Bezier splines approximating the input cubic Beziers.

    Args:
        curves: A sequence of *n* curves, each curve being a sequence of four
            2D tuples.
        max_errors: A sequence of *n* floats representing the maximum permissible
            deviation from each of the cubic Bezier curves.
        all_quadratic (bool): If True (default) returned values are a
            quadratic spline. If False, they are either a single quadratic
            curve or a single cubic curve.

    Example::

        >>> curves_to_quadratic( [
        ...   [ (50,50), (100,100), (150,100), (200,50) ],
        ...   [ (75,50), (120,100), (150,75),  (200,60) ]
        ... ], [1,1] )
        [[(50.0, 50.0), (75.0, 75.0), (125.0, 91.66666666666666), (175.0, 75.0), (200.0, 50.0)], [(75.0, 50.0), (97.5, 75.0), (135.41666666666666, 82.08333333333333), (175.0, 67.5), (200.0, 60.0)]]

    The returned splines have "implied oncurve points" suitable for use in
    TrueType ``glif`` outlines - i.e. in the first spline returned above,
    the first quadratic segment runs from (50,50) to
    ( (75 + 125)/2 , (120 + 91.666..)/2 ) = (100, 83.333...).

    Returns:
        If all_quadratic is True, a list of splines, each spline being a list
        of 2D tuples.

        If all_quadratic is False, a list of curves, each curve being a quadratic
        (length 3), or cubic (length 4).

    Raises:
        fontTools.cu2qu.Errors.ApproxNotFoundError: if no suitable approximation
        can be found for all curves with the given parameters.
    """

    curves = [[complex(*p) for p in curve] for curve in curves]
    assert len(max_errors) == len(curves)

    l = len(curves)
    splines = [None] * l
    last_i = i = 0
    n = 1
    while True:
        spline = cubic_approx_spline(curves[i], n, max_errors[i], all_quadratic)
        if spline is None:
            if n == MAX_N:
                break
            n += 1
            last_i = i
            continue
        splines[i] = spline
        i = (i + 1) % l
        if i == last_i:
            # done. go home
            return [[(s.real, s.imag) for s in spline] for spline in splines]

    raise ApproxNotFoundError(curves)
