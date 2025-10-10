from fontTools.ttLib.ttGlyphSet import LerpGlyphSet
from fontTools.pens.basePen import AbstractPen, BasePen, DecomposingPen
from fontTools.pens.pointPen import AbstractPointPen, SegmentToPointPen
from fontTools.pens.recordingPen import RecordingPen, DecomposingRecordingPen
from fontTools.misc.transform import Transform
from collections import defaultdict, deque
from math import sqrt, copysign, atan2, pi
from enum import Enum
import itertools

import logging

log = logging.getLogger("fontTools.varLib.interpolatable")


class InterpolatableProblem:
    NOTHING = "nothing"
    MISSING = "missing"
    OPEN_PATH = "open_path"
    PATH_COUNT = "path_count"
    NODE_COUNT = "node_count"
    NODE_INCOMPATIBILITY = "node_incompatibility"
    CONTOUR_ORDER = "contour_order"
    WRONG_START_POINT = "wrong_start_point"
    KINK = "kink"
    UNDERWEIGHT = "underweight"
    OVERWEIGHT = "overweight"

    severity = {
        MISSING: 1,
        OPEN_PATH: 2,
        PATH_COUNT: 3,
        NODE_COUNT: 4,
        NODE_INCOMPATIBILITY: 5,
        CONTOUR_ORDER: 6,
        WRONG_START_POINT: 7,
        KINK: 8,
        UNDERWEIGHT: 9,
        OVERWEIGHT: 10,
        NOTHING: 11,
    }


def sort_problems(problems):
    """Sort problems by severity, then by glyph name, then by problem message."""
    return dict(
        sorted(
            problems.items(),
            key=lambda _: -min(
                (
                    (InterpolatableProblem.severity[p["type"]] + p.get("tolerance", 0))
                    for p in _[1]
                ),
            ),
            reverse=True,
        )
    )


def rot_list(l, k):
    """Rotate list by k items forward.  Ie. item at position 0 will be
    at position k in returned list.  Negative k is allowed."""
    return l[-k:] + l[:-k]


class PerContourPen(BasePen):
    def __init__(self, Pen, glyphset=None):
        BasePen.__init__(self, glyphset)
        self._glyphset = glyphset
        self._Pen = Pen
        self._pen = None
        self.value = []

    def _moveTo(self, p0):
        self._newItem()
        self._pen.moveTo(p0)

    def _lineTo(self, p1):
        self._pen.lineTo(p1)

    def _qCurveToOne(self, p1, p2):
        self._pen.qCurveTo(p1, p2)

    def _curveToOne(self, p1, p2, p3):
        self._pen.curveTo(p1, p2, p3)

    def _closePath(self):
        self._pen.closePath()
        self._pen = None

    def _endPath(self):
        self._pen.endPath()
        self._pen = None

    def _newItem(self):
        self._pen = pen = self._Pen()
        self.value.append(pen)


class PerContourOrComponentPen(PerContourPen):
    def addComponent(self, glyphName, transformation):
        self._newItem()
        self.value[-1].addComponent(glyphName, transformation)


class SimpleRecordingPointPen(AbstractPointPen):
    def __init__(self):
        self.value = []

    def beginPath(self, identifier=None, **kwargs):
        pass

    def endPath(self) -> None:
        pass

    def addPoint(self, pt, segmentType=None):
        self.value.append((pt, False if segmentType is None else True))


def vdiff_hypot2(v0, v1):
    s = 0
    for x0, x1 in zip(v0, v1):
        d = x1 - x0
        s += d * d
    return s


def vdiff_hypot2_complex(v0, v1):
    s = 0
    for x0, x1 in zip(v0, v1):
        d = x1 - x0
        s += d.real * d.real + d.imag * d.imag
        # This does the same but seems to be slower:
        # s += (d * d.conjugate()).real
    return s


def matching_cost(G, matching):
    return sum(G[i][j] for i, j in enumerate(matching))


def min_cost_perfect_bipartite_matching_scipy(G):
    n = len(G)
    rows, cols = linear_sum_assignment(G)
    assert (rows == list(range(n))).all()
    # Convert numpy array and integer to Python types,
    # to ensure that this is JSON-serializable.
    cols = list(int(e) for e in cols)
    return list(cols), matching_cost(G, cols)


def min_cost_perfect_bipartite_matching_munkres(G):
    n = len(G)
    cols = [None] * n
    for row, col in Munkres().compute(G):
        cols[row] = col
    return cols, matching_cost(G, cols)


def min_cost_perfect_bipartite_matching_bruteforce(G):
    n = len(G)

    if n > 6:
        raise Exception("Install Python module 'munkres' or 'scipy >= 0.17.0'")

    # Otherwise just brute-force
    permutations = itertools.permutations(range(n))
    best = list(next(permutations))
    best_cost = matching_cost(G, best)
    for p in permutations:
        cost = matching_cost(G, p)
        if cost < best_cost:
            best, best_cost = list(p), cost
    return best, best_cost


# Prefer `scipy.optimize.linear_sum_assignment` for performance.
# `Munkres` is also supported as a fallback for minimalistic systems
# where installing SciPy is not feasible.
try:
    from scipy.optimize import linear_sum_assignment

    min_cost_perfect_bipartite_matching = min_cost_perfect_bipartite_matching_scipy
except ImportError:
    try:
        from munkres import Munkres

        min_cost_perfect_bipartite_matching = (
            min_cost_perfect_bipartite_matching_munkres
        )
    except ImportError:
        min_cost_perfect_bipartite_matching = (
            min_cost_perfect_bipartite_matching_bruteforce
        )


def contour_vector_from_stats(stats):
    # Don't change the order of items here.
    # It's okay to add to the end, but otherwise, other
    # code depends on it. Search for "covariance".
    size = sqrt(abs(stats.area))
    return (
        copysign((size), stats.area),
        stats.meanX,
        stats.meanY,
        stats.stddevX * 2,
        stats.stddevY * 2,
        stats.correlation * size,
    )


def matching_for_vectors(m0, m1):
    n = len(m0)

    identity_matching = list(range(n))

    costs = [[vdiff_hypot2(v0, v1) for v1 in m1] for v0 in m0]
    (
        matching,
        matching_cost,
    ) = min_cost_perfect_bipartite_matching(costs)
    identity_cost = sum(costs[i][i] for i in range(n))
    return matching, matching_cost, identity_cost


def points_characteristic_bits(points):
    bits = 0
    for pt, b in reversed(points):
        bits = (bits << 1) | b
    return bits


_NUM_ITEMS_PER_POINTS_COMPLEX_VECTOR = 4


def points_complex_vector(points):
    vector = []
    if not points:
        return vector
    points = [complex(*pt) for pt, _ in points]
    n = len(points)
    assert _NUM_ITEMS_PER_POINTS_COMPLEX_VECTOR == 4
    points.extend(points[: _NUM_ITEMS_PER_POINTS_COMPLEX_VECTOR - 1])
    while len(points) < _NUM_ITEMS_PER_POINTS_COMPLEX_VECTOR:
        points.extend(points[: _NUM_ITEMS_PER_POINTS_COMPLEX_VECTOR - 1])
    for i in range(n):
        # The weights are magic numbers.

        # The point itself
        p0 = points[i]
        vector.append(p0)

        # The vector to the next point
        p1 = points[i + 1]
        d0 = p1 - p0
        vector.append(d0 * 3)

        # The turn vector
        p2 = points[i + 2]
        d1 = p2 - p1
        vector.append(d1 - d0)

        # The angle to the next point, as a cross product;
        # Square root of, to match dimentionality of distance.
        cross = d0.real * d1.imag - d0.imag * d1.real
        cross = copysign(sqrt(abs(cross)), cross)
        vector.append(cross * 4)

    return vector


def add_isomorphisms(points, isomorphisms, reverse):
    reference_bits = points_characteristic_bits(points)
    n = len(points)

    # if points[0][0] == points[-1][0]:
    #   abort

    if reverse:
        points = points[::-1]
        bits = points_characteristic_bits(points)
    else:
        bits = reference_bits

    vector = points_complex_vector(points)

    assert len(vector) % n == 0
    mult = len(vector) // n
    mask = (1 << n) - 1

    for i in range(n):
        b = ((bits << (n - i)) & mask) | (bits >> i)
        if b == reference_bits:
            isomorphisms.append(
                (rot_list(vector, -i * mult), n - 1 - i if reverse else i, reverse)
            )


def find_parents_and_order(glyphsets, locations, *, discrete_axes=set()):
    parents = [None] + list(range(len(glyphsets) - 1))
    order = list(range(len(glyphsets)))
    if locations:
        # Order base master first
        bases = [
            i
            for i, l in enumerate(locations)
            if all(v == 0 for k, v in l.items() if k not in discrete_axes)
        ]
        if bases:
            logging.info("Found %s base masters: %s", len(bases), bases)
        else:
            logging.warning("No base master location found")

        # Form a minimum spanning tree of the locations
        try:
            from scipy.sparse.csgraph import minimum_spanning_tree

            graph = [[0] * len(locations) for _ in range(len(locations))]
            axes = set()
            for l in locations:
                axes.update(l.keys())
            axes = sorted(axes)
            vectors = [tuple(l.get(k, 0) for k in axes) for l in locations]
            for i, j in itertools.combinations(range(len(locations)), 2):
                i_discrete_location = {
                    k: v for k, v in zip(axes, vectors[i]) if k in discrete_axes
                }
                j_discrete_location = {
                    k: v for k, v in zip(axes, vectors[j]) if k in discrete_axes
                }
                if i_discrete_location != j_discrete_location:
                    continue
                graph[i][j] = vdiff_hypot2(vectors[i], vectors[j])

            tree = minimum_spanning_tree(graph, overwrite=True)
            rows, cols = tree.nonzero()
            graph = defaultdict(set)
            for row, col in zip(rows, cols):
                graph[row].add(col)
                graph[col].add(row)

            # Traverse graph from the base and assign parents
            parents = [None] * len(locations)
            order = []
            visited = set()
            queue = deque(bases)
            while queue:
                i = queue.popleft()
                visited.add(i)
                order.append(i)
                for j in sorted(graph[i]):
                    if j not in visited:
                        parents[j] = i
                        queue.append(j)
            assert len(order) == len(
                parents
            ), "Not all masters are reachable; report an issue"

        except ImportError:
            pass

        log.info("Parents: %s", parents)
        log.info("Order: %s", order)
    return parents, order


def transform_from_stats(stats, inverse=False):
    # https://cookierobotics.com/007/
    a = stats.varianceX
    b = stats.covariance
    c = stats.varianceY

    delta = (((a - c) * 0.5) ** 2 + b * b) ** 0.5
    lambda1 = (a + c) * 0.5 + delta  # Major eigenvalue
    lambda2 = (a + c) * 0.5 - delta  # Minor eigenvalue
    theta = atan2(lambda1 - a, b) if b != 0 else (pi * 0.5 if a < c else 0)
    trans = Transform()

    if lambda2 < 0:
        # XXX This is a hack.
        # The problem is that the covariance matrix is singular.
        # This happens when the contour is a line, or a circle.
        # In that case, the covariance matrix is not a good
        # representation of the contour.
        # We should probably detect this earlier and avoid
        # computing the covariance matrix in the first place.
        # But for now, we just avoid the division by zero.
        lambda2 = 0

    if inverse:
        trans = trans.translate(-stats.meanX, -stats.meanY)
        trans = trans.rotate(-theta)
        trans = trans.scale(1 / sqrt(lambda1), 1 / sqrt(lambda2))
    else:
        trans = trans.scale(sqrt(lambda1), sqrt(lambda2))
        trans = trans.rotate(theta)
        trans = trans.translate(stats.meanX, stats.meanY)

    return trans
