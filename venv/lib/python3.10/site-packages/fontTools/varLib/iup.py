try:
    import cython
except (AttributeError, ImportError):
    # if cython not installed, use mock module with no-op decorators and types
    from fontTools.misc import cython
COMPILED = cython.compiled

from typing import (
    Sequence,
    Tuple,
    Union,
)
from numbers import Integral, Real


_Point = Tuple[Real, Real]
_Delta = Tuple[Real, Real]
_PointSegment = Sequence[_Point]
_DeltaSegment = Sequence[_Delta]
_DeltaOrNone = Union[_Delta, None]
_DeltaOrNoneSegment = Sequence[_DeltaOrNone]
_Endpoints = Sequence[Integral]


MAX_LOOKBACK = 8


@cython.cfunc
@cython.locals(
    j=cython.int,
    n=cython.int,
    x1=cython.double,
    x2=cython.double,
    d1=cython.double,
    d2=cython.double,
    scale=cython.double,
    x=cython.double,
    d=cython.double,
)
def iup_segment(
    coords: _PointSegment, rc1: _Point, rd1: _Delta, rc2: _Point, rd2: _Delta
):  # -> _DeltaSegment:
    """Given two reference coordinates `rc1` & `rc2` and their respective
    delta vectors `rd1` & `rd2`, returns interpolated deltas for the set of
    coordinates `coords`."""

    # rc1 = reference coord 1
    # rd1 = reference delta 1
    out_arrays = [None, None]
    for j in 0, 1:
        out_arrays[j] = out = []
        x1, x2, d1, d2 = rc1[j], rc2[j], rd1[j], rd2[j]

        if x1 == x2:
            n = len(coords)
            if d1 == d2:
                out.extend([d1] * n)
            else:
                out.extend([0] * n)
            continue

        if x1 > x2:
            x1, x2 = x2, x1
            d1, d2 = d2, d1

        # x1 < x2
        scale = (d2 - d1) / (x2 - x1)
        for pair in coords:
            x = pair[j]

            if x <= x1:
                d = d1
            elif x >= x2:
                d = d2
            else:
                # Interpolate
                #
                # NOTE: we assign an explicit intermediate variable here in
                # order to disable a fused mul-add optimization. See:
                #
                # - https://godbolt.org/z/YsP4T3TqK,
                # - https://github.com/fonttools/fonttools/issues/3703
                nudge = (x - x1) * scale
                d = d1 + nudge

            out.append(d)

    return zip(*out_arrays)


def iup_contour(deltas: _DeltaOrNoneSegment, coords: _PointSegment) -> _DeltaSegment:
    """For the contour given in `coords`, interpolate any missing
    delta values in delta vector `deltas`.

    Returns fully filled-out delta vector."""

    assert len(deltas) == len(coords)
    if None not in deltas:
        return deltas

    n = len(deltas)
    # indices of points with explicit deltas
    indices = [i for i, v in enumerate(deltas) if v is not None]
    if not indices:
        # All deltas are None.  Return 0,0 for all.
        return [(0, 0)] * n

    out = []
    it = iter(indices)
    start = next(it)
    if start != 0:
        # Initial segment that wraps around
        i1, i2, ri1, ri2 = 0, start, start, indices[-1]
        out.extend(
            iup_segment(
                coords[i1:i2], coords[ri1], deltas[ri1], coords[ri2], deltas[ri2]
            )
        )
    out.append(deltas[start])
    for end in it:
        if end - start > 1:
            i1, i2, ri1, ri2 = start + 1, end, start, end
            out.extend(
                iup_segment(
                    coords[i1:i2], coords[ri1], deltas[ri1], coords[ri2], deltas[ri2]
                )
            )
        out.append(deltas[end])
        start = end
    if start != n - 1:
        # Final segment that wraps around
        i1, i2, ri1, ri2 = start + 1, n, start, indices[0]
        out.extend(
            iup_segment(
                coords[i1:i2], coords[ri1], deltas[ri1], coords[ri2], deltas[ri2]
            )
        )

    assert len(deltas) == len(out), (len(deltas), len(out))
    return out


def iup_delta(
    deltas: _DeltaOrNoneSegment, coords: _PointSegment, ends: _Endpoints
) -> _DeltaSegment:
    """For the outline given in `coords`, with contour endpoints given
    in sorted increasing order in `ends`, interpolate any missing
    delta values in delta vector `deltas`.

    Returns fully filled-out delta vector."""

    assert sorted(ends) == ends and len(coords) == (ends[-1] + 1 if ends else 0) + 4
    n = len(coords)
    ends = ends + [n - 4, n - 3, n - 2, n - 1]
    out = []
    start = 0
    for end in ends:
        end += 1
        contour = iup_contour(deltas[start:end], coords[start:end])
        out.extend(contour)
        start = end

    return out


# Optimizer


@cython.cfunc
@cython.inline
@cython.locals(
    i=cython.int,
    j=cython.int,
    # tolerance=cython.double, # https://github.com/fonttools/fonttools/issues/3282
    x=cython.double,
    y=cython.double,
    p=cython.double,
    q=cython.double,
)
@cython.returns(int)
def can_iup_in_between(
    deltas: _DeltaSegment,
    coords: _PointSegment,
    i: Integral,
    j: Integral,
    tolerance: Real,
):  # -> bool:
    """Return true if the deltas for points at `i` and `j` (`i < j`) can be
    successfully used to interpolate deltas for points in between them within
    provided error tolerance."""

    assert j - i >= 2
    interp = iup_segment(coords[i + 1 : j], coords[i], deltas[i], coords[j], deltas[j])
    deltas = deltas[i + 1 : j]

    return all(
        abs(complex(x - p, y - q)) <= tolerance
        for (x, y), (p, q) in zip(deltas, interp)
    )


@cython.locals(
    cj=cython.double,
    dj=cython.double,
    lcj=cython.double,
    ldj=cython.double,
    ncj=cython.double,
    ndj=cython.double,
    force=cython.int,
    forced=set,
)
def _iup_contour_bound_forced_set(
    deltas: _DeltaSegment, coords: _PointSegment, tolerance: Real = 0
) -> set:
    """The forced set is a conservative set of points on the contour that must be encoded
    explicitly (ie. cannot be interpolated).  Calculating this set allows for significantly
    speeding up the dynamic-programming, as well as resolve circularity in DP.

    The set is precise; that is, if an index is in the returned set, then there is no way
    that IUP can generate delta for that point, given `coords` and `deltas`.
    """
    assert len(deltas) == len(coords)

    n = len(deltas)
    forced = set()
    # Track "last" and "next" points on the contour as we sweep.
    for i in range(len(deltas) - 1, -1, -1):
        ld, lc = deltas[i - 1], coords[i - 1]
        d, c = deltas[i], coords[i]
        nd, nc = deltas[i - n + 1], coords[i - n + 1]

        for j in (0, 1):  # For X and for Y
            cj = c[j]
            dj = d[j]
            lcj = lc[j]
            ldj = ld[j]
            ncj = nc[j]
            ndj = nd[j]

            if lcj <= ncj:
                c1, c2 = lcj, ncj
                d1, d2 = ldj, ndj
            else:
                c1, c2 = ncj, lcj
                d1, d2 = ndj, ldj

            force = False

            # If the two coordinates are the same, then the interpolation
            # algorithm produces the same delta if both deltas are equal,
            # and zero if they differ.
            #
            # This test has to be before the next one.
            if c1 == c2:
                if abs(d1 - d2) > tolerance and abs(dj) > tolerance:
                    force = True

            # If coordinate for current point is between coordinate of adjacent
            # points on the two sides, but the delta for current point is NOT
            # between delta for those adjacent points (considering tolerance
            # allowance), then there is no way that current point can be IUP-ed.
            # Mark it forced.
            elif c1 <= cj <= c2:  # and c1 != c2
                if not (min(d1, d2) - tolerance <= dj <= max(d1, d2) + tolerance):
                    force = True

            # Otherwise, the delta should either match the closest, or have the
            # same sign as the interpolation of the two deltas.
            else:  # cj < c1 or c2 < cj
                if d1 != d2:
                    if cj < c1:
                        if (
                            abs(dj) > tolerance
                            and abs(dj - d1) > tolerance
                            and ((dj - tolerance < d1) != (d1 < d2))
                        ):
                            force = True
                    else:  # c2 < cj
                        if (
                            abs(dj) > tolerance
                            and abs(dj - d2) > tolerance
                            and ((d2 < dj + tolerance) != (d1 < d2))
                        ):
                            force = True

            if force:
                forced.add(i)
                break

    return forced


@cython.locals(
    i=cython.int,
    j=cython.int,
    best_cost=cython.double,
    best_j=cython.int,
    cost=cython.double,
    forced=set,
    tolerance=cython.double,
)
def _iup_contour_optimize_dp(
    deltas: _DeltaSegment,
    coords: _PointSegment,
    forced=set(),
    tolerance: Real = 0,
    lookback: Integral = None,
):
    """Straightforward Dynamic-Programming.  For each index i, find least-costly encoding of
    points 0 to i where i is explicitly encoded.  We find this by considering all previous
    explicit points j and check whether interpolation can fill points between j and i.

    Note that solution always encodes last point explicitly.  Higher-level is responsible
    for removing that restriction.

    As major speedup, we stop looking further whenever we see a "forced" point."""

    n = len(deltas)
    if lookback is None:
        lookback = n
    lookback = min(lookback, MAX_LOOKBACK)
    costs = {-1: 0}
    chain = {-1: None}
    for i in range(0, n):
        best_cost = costs[i - 1] + 1

        costs[i] = best_cost
        chain[i] = i - 1

        if i - 1 in forced:
            continue

        for j in range(i - 2, max(i - lookback, -2), -1):
            cost = costs[j] + 1

            if cost < best_cost and can_iup_in_between(deltas, coords, j, i, tolerance):
                costs[i] = best_cost = cost
                chain[i] = j

            if j in forced:
                break

    return chain, costs


def _rot_list(l: list, k: int):
    """Rotate list by k items forward.  Ie. item at position 0 will be
    at position k in returned list.  Negative k is allowed."""
    n = len(l)
    k %= n
    if not k:
        return l
    return l[n - k :] + l[: n - k]


def _rot_set(s: set, k: int, n: int):
    k %= n
    if not k:
        return s
    return {(v + k) % n for v in s}


def iup_contour_optimize(
    deltas: _DeltaSegment, coords: _PointSegment, tolerance: Real = 0.0
) -> _DeltaOrNoneSegment:
    """For contour with coordinates `coords`, optimize a set of delta
    values `deltas` within error `tolerance`.

    Returns delta vector that has most number of None items instead of
    the input delta.
    """

    n = len(deltas)

    # Get the easy cases out of the way:

    # If all are within tolerance distance of 0, encode nothing:
    if all(abs(complex(*p)) <= tolerance for p in deltas):
        return [None] * n

    # If there's exactly one point, return it:
    if n == 1:
        return deltas

    # If all deltas are exactly the same, return just one (the first one):
    d0 = deltas[0]
    if all(d0 == d for d in deltas):
        return [d0] + [None] * (n - 1)

    # Else, solve the general problem using Dynamic Programming.

    forced = _iup_contour_bound_forced_set(deltas, coords, tolerance)
    # The _iup_contour_optimize_dp() routine returns the optimal encoding
    # solution given the constraint that the last point is always encoded.
    # To remove this constraint, we use two different methods, depending on
    # whether forced set is non-empty or not:

    # Debugging: Make the next if always take the second branch and observe
    # if the font size changes (reduced); that would mean the forced-set
    # has members it should not have.
    if forced:
        # Forced set is non-empty: rotate the contour start point
        # such that the last point in the list is a forced point.
        k = (n - 1) - max(forced)
        assert k >= 0

        deltas = _rot_list(deltas, k)
        coords = _rot_list(coords, k)
        forced = _rot_set(forced, k, n)

        # Debugging: Pass a set() instead of forced variable to the next call
        # to exercise forced-set computation for under-counting.
        chain, costs = _iup_contour_optimize_dp(deltas, coords, forced, tolerance)

        # Assemble solution.
        solution = set()
        i = n - 1
        while i is not None:
            solution.add(i)
            i = chain[i]
        solution.remove(-1)

        # if not forced <= solution:
        # 	print("coord", coords)
        # 	print("deltas", deltas)
        # 	print("len", len(deltas))
        assert forced <= solution, (forced, solution)

        deltas = [deltas[i] if i in solution else None for i in range(n)]

        deltas = _rot_list(deltas, -k)
    else:
        # Repeat the contour an extra time, solve the new case, then look for solutions of the
        # circular n-length problem in the solution for new linear case.  I cannot prove that
        # this always produces the optimal solution...
        chain, costs = _iup_contour_optimize_dp(
            deltas + deltas, coords + coords, forced, tolerance, n
        )
        best_sol, best_cost = None, n + 1

        for start in range(n - 1, len(costs) - 1):
            # Assemble solution.
            solution = set()
            i = start
            while i > start - n:
                solution.add(i % n)
                i = chain[i]
            if i == start - n:
                cost = costs[start] - costs[start - n]
                if cost <= best_cost:
                    best_sol, best_cost = solution, cost

        # if not forced <= best_sol:
        # 	print("coord", coords)
        # 	print("deltas", deltas)
        # 	print("len", len(deltas))
        assert forced <= best_sol, (forced, best_sol)

        deltas = [deltas[i] if i in best_sol else None for i in range(n)]

    return deltas


def iup_delta_optimize(
    deltas: _DeltaSegment,
    coords: _PointSegment,
    ends: _Endpoints,
    tolerance: Real = 0.0,
) -> _DeltaOrNoneSegment:
    """For the outline given in `coords`, with contour endpoints given
    in sorted increasing order in `ends`, optimize a set of delta
    values `deltas` within error `tolerance`.

    Returns delta vector that has most number of None items instead of
    the input delta.
    """
    assert sorted(ends) == ends and len(coords) == (ends[-1] + 1 if ends else 0) + 4
    n = len(coords)
    ends = ends + [n - 4, n - 3, n - 2, n - 1]
    out = []
    start = 0
    for end in ends:
        contour = iup_contour_optimize(
            deltas[start : end + 1], coords[start : end + 1], tolerance
        )
        assert len(contour) == end - start + 1
        out.extend(contour)
        start = end + 1

    return out
