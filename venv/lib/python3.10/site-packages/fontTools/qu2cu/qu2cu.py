# cython: language_level=3
# distutils: define_macros=CYTHON_TRACE_NOGIL=1

# Copyright 2023 Google Inc. All Rights Reserved.
# Copyright 2023 Behdad Esfahbod. All Rights Reserved.
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

from fontTools.misc.bezierTools import splitCubicAtTC
from collections import namedtuple
import math
from typing import (
    List,
    Tuple,
    Union,
)


__all__ = ["quadratic_to_curves"]


# Copied from cu2qu
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


@cython.locals(
    p0=cython.complex,
    p1=cython.complex,
    p2=cython.complex,
    p1_2_3=cython.complex,
)
def elevate_quadratic(p0, p1, p2):
    """Given a quadratic bezier curve, return its degree-elevated cubic."""

    # https://pomax.github.io/bezierinfo/#reordering
    p1_2_3 = p1 * (2 / 3)
    return (
        p0,
        (p0 * (1 / 3) + p1_2_3),
        (p2 * (1 / 3) + p1_2_3),
        p2,
    )


@cython.cfunc
@cython.locals(
    start=cython.int,
    n=cython.int,
    k=cython.int,
    prod_ratio=cython.double,
    sum_ratio=cython.double,
    ratio=cython.double,
    t=cython.double,
    p0=cython.complex,
    p1=cython.complex,
    p2=cython.complex,
    p3=cython.complex,
)
def merge_curves(curves, start, n):
    """Give a cubic-Bezier spline, reconstruct one cubic-Bezier
    that has the same endpoints and tangents and approxmates
    the spline."""

    # Reconstruct the t values of the cut segments
    prod_ratio = 1.0
    sum_ratio = 1.0
    ts = [1]
    for k in range(1, n):
        ck = curves[start + k]
        c_before = curves[start + k - 1]

        # |t_(k+1) - t_k| / |t_k - t_(k - 1)| = ratio
        assert ck[0] == c_before[3]
        ratio = abs(ck[1] - ck[0]) / abs(c_before[3] - c_before[2])

        prod_ratio *= ratio
        sum_ratio += prod_ratio
        ts.append(sum_ratio)

    # (t(n) - t(n - 1)) / (t_(1) - t(0)) = prod_ratio

    ts = [t / sum_ratio for t in ts[:-1]]

    p0 = curves[start][0]
    p1 = curves[start][1]
    p2 = curves[start + n - 1][2]
    p3 = curves[start + n - 1][3]

    # Build the curve by scaling the control-points.
    p1 = p0 + (p1 - p0) / (ts[0] if ts else 1)
    p2 = p3 + (p2 - p3) / ((1 - ts[-1]) if ts else 1)

    curve = (p0, p1, p2, p3)

    return curve, ts


@cython.locals(
    count=cython.int,
    num_offcurves=cython.int,
    i=cython.int,
    off1=cython.complex,
    off2=cython.complex,
    on=cython.complex,
)
def add_implicit_on_curves(p):
    q = list(p)
    count = 0
    num_offcurves = len(p) - 2
    for i in range(1, num_offcurves):
        off1 = p[i]
        off2 = p[i + 1]
        on = off1 + (off2 - off1) * 0.5
        q.insert(i + 1 + count, on)
        count += 1
    return q


Point = Union[Tuple[float, float], complex]


@cython.locals(
    cost=cython.int,
    is_complex=cython.int,
)
def quadratic_to_curves(
    quads: List[List[Point]],
    max_err: float = 0.5,
    all_cubic: bool = False,
) -> List[Tuple[Point, ...]]:
    """Converts a connecting list of quadratic splines to a list of quadratic
    and cubic curves.

    A quadratic spline is specified as a list of points.  Either each point is
    a 2-tuple of X,Y coordinates, or each point is a complex number with
    real/imaginary components representing X,Y coordinates.

    The first and last points are on-curve points and the rest are off-curve
    points, with an implied on-curve point in the middle between every two
    consequtive off-curve points.

    Returns:
        The output is a list of tuples of points. Points are represented
        in the same format as the input, either as 2-tuples or complex numbers.

        Each tuple is either of length three, for a quadratic curve, or four,
        for a cubic curve.  Each curve's last point is the same as the next
        curve's first point.

    Args:
        quads: quadratic splines

        max_err: absolute error tolerance; defaults to 0.5

        all_cubic: if True, only cubic curves are generated; defaults to False
    """
    is_complex = type(quads[0][0]) is complex
    if not is_complex:
        quads = [[complex(x, y) for (x, y) in p] for p in quads]

    q = [quads[0][0]]
    costs = [1]
    cost = 1
    for p in quads:
        assert q[-1] == p[0]
        for i in range(len(p) - 2):
            cost += 1
            costs.append(cost)
            costs.append(cost)
        qq = add_implicit_on_curves(p)[1:]
        costs.pop()
        q.extend(qq)
        cost += 1
        costs.append(cost)

    curves = spline_to_curves(q, costs, max_err, all_cubic)

    if not is_complex:
        curves = [tuple((c.real, c.imag) for c in curve) for curve in curves]
    return curves


Solution = namedtuple("Solution", ["num_points", "error", "start_index", "is_cubic"])


@cython.locals(
    i=cython.int,
    j=cython.int,
    k=cython.int,
    start=cython.int,
    i_sol_count=cython.int,
    j_sol_count=cython.int,
    this_sol_count=cython.int,
    tolerance=cython.double,
    err=cython.double,
    error=cython.double,
    i_sol_error=cython.double,
    j_sol_error=cython.double,
    all_cubic=cython.int,
    is_cubic=cython.int,
    count=cython.int,
    p0=cython.complex,
    p1=cython.complex,
    p2=cython.complex,
    p3=cython.complex,
    v=cython.complex,
    u=cython.complex,
)
def spline_to_curves(q, costs, tolerance=0.5, all_cubic=False):
    """
    q: quadratic spline with alternating on-curve / off-curve points.

    costs: cumulative list of encoding cost of q in terms of number of
      points that need to be encoded.  Implied on-curve points do not
      contribute to the cost. If all points need to be encoded, then
      costs will be range(1, len(q)+1).
    """

    assert len(q) >= 3, "quadratic spline requires at least 3 points"

    # Elevate quadratic segments to cubic
    elevated_quadratics = [
        elevate_quadratic(*q[i : i + 3]) for i in range(0, len(q) - 2, 2)
    ]

    # Find sharp corners; they have to be oncurves for sure.
    forced = set()
    for i in range(1, len(elevated_quadratics)):
        p0 = elevated_quadratics[i - 1][2]
        p1 = elevated_quadratics[i][0]
        p2 = elevated_quadratics[i][1]
        if abs(p1 - p0) + abs(p2 - p1) > tolerance + abs(p2 - p0):
            forced.add(i)

    # Dynamic-Programming to find the solution with fewest number of
    # cubic curves, and within those the one with smallest error.
    sols = [Solution(0, 0, 0, False)]
    impossible = Solution(len(elevated_quadratics) * 3 + 1, 0, 1, False)
    start = 0
    for i in range(1, len(elevated_quadratics) + 1):
        best_sol = impossible
        for j in range(start, i):
            j_sol_count, j_sol_error = sols[j].num_points, sols[j].error

            if not all_cubic:
                # Solution with quadratics between j:i
                this_count = costs[2 * i - 1] - costs[2 * j] + 1
                i_sol_count = j_sol_count + this_count
                i_sol_error = j_sol_error
                i_sol = Solution(i_sol_count, i_sol_error, i - j, False)
                if i_sol < best_sol:
                    best_sol = i_sol

                if this_count <= 3:
                    # Can't get any better than this in the path below
                    continue

            # Fit elevated_quadratics[j:i] into one cubic
            try:
                curve, ts = merge_curves(elevated_quadratics, j, i - j)
            except ZeroDivisionError:
                continue

            # Now reconstruct the segments from the fitted curve
            reconstructed_iter = splitCubicAtTC(*curve, *ts)
            reconstructed = []

            # Knot errors
            error = 0
            for k, reconst in enumerate(reconstructed_iter):
                orig = elevated_quadratics[j + k]
                err = abs(reconst[3] - orig[3])
                error = max(error, err)
                if error > tolerance:
                    break
                reconstructed.append(reconst)
            if error > tolerance:
                # Not feasible
                continue

            # Interior errors
            for k, reconst in enumerate(reconstructed):
                orig = elevated_quadratics[j + k]
                p0, p1, p2, p3 = tuple(v - u for v, u in zip(reconst, orig))

                if not cubic_farthest_fit_inside(p0, p1, p2, p3, tolerance):
                    error = tolerance + 1
                    break
            if error > tolerance:
                # Not feasible
                continue

            # Save best solution
            i_sol_count = j_sol_count + 3
            i_sol_error = max(j_sol_error, error)
            i_sol = Solution(i_sol_count, i_sol_error, i - j, True)
            if i_sol < best_sol:
                best_sol = i_sol

            if i_sol_count == 3:
                # Can't get any better than this
                break

        sols.append(best_sol)
        if i in forced:
            start = i

    # Reconstruct solution
    splits = []
    cubic = []
    i = len(sols) - 1
    while i:
        count, is_cubic = sols[i].start_index, sols[i].is_cubic
        splits.append(i)
        cubic.append(is_cubic)
        i -= count
    curves = []
    j = 0
    for i, is_cubic in reversed(list(zip(splits, cubic))):
        if is_cubic:
            curves.append(merge_curves(elevated_quadratics, j, i - j)[0])
        else:
            for k in range(j, i):
                curves.append(q[k * 2 : k * 2 + 3])
        j = i

    return curves


def main():
    from fontTools.cu2qu.benchmark import generate_curve
    from fontTools.cu2qu import curve_to_quadratic

    tolerance = 0.05
    reconstruct_tolerance = tolerance * 1
    curve = generate_curve()
    quadratics = curve_to_quadratic(curve, tolerance)
    print(
        "cu2qu tolerance %g. qu2cu tolerance %g." % (tolerance, reconstruct_tolerance)
    )
    print("One random cubic turned into %d quadratics." % len(quadratics))
    curves = quadratic_to_curves([quadratics], reconstruct_tolerance)
    print("Those quadratics turned back into %d cubics. " % len(curves))
    print("Original curve:", curve)
    print("Reconstructed curve(s):", curves)


if __name__ == "__main__":
    main()
