import platform
import re

import numpy as np

from numpy.testing import assert_array_equal
import pytest

from matplotlib import patches
from matplotlib.path import Path
from matplotlib.patches import Polygon
from matplotlib.testing.decorators import image_comparison
import matplotlib.pyplot as plt
from matplotlib import transforms
from matplotlib.backend_bases import MouseEvent


def test_empty_closed_path():
    path = Path(np.zeros((0, 2)), closed=True)
    assert path.vertices.shape == (0, 2)
    assert path.codes is None
    assert_array_equal(path.get_extents().extents,
                       transforms.Bbox.null().extents)


def test_readonly_path():
    path = Path.unit_circle()

    def modify_vertices():
        path.vertices = path.vertices * 2.0

    with pytest.raises(AttributeError):
        modify_vertices()


def test_path_exceptions():
    bad_verts1 = np.arange(12).reshape(4, 3)
    with pytest.raises(ValueError,
                       match=re.escape(f'has shape {bad_verts1.shape}')):
        Path(bad_verts1)

    bad_verts2 = np.arange(12).reshape(2, 3, 2)
    with pytest.raises(ValueError,
                       match=re.escape(f'has shape {bad_verts2.shape}')):
        Path(bad_verts2)

    good_verts = np.arange(12).reshape(6, 2)
    bad_codes = np.arange(2)
    msg = re.escape(f"Your vertices have shape {good_verts.shape} "
                    f"but your codes have shape {bad_codes.shape}")
    with pytest.raises(ValueError, match=msg):
        Path(good_verts, bad_codes)


def test_point_in_path():
    # Test #1787
    path = Path._create_closed([(0, 0), (0, 1), (1, 1), (1, 0)])
    points = [(0.5, 0.5), (1.5, 0.5)]
    ret = path.contains_points(points)
    assert ret.dtype == 'bool'
    np.testing.assert_equal(ret, [True, False])


@pytest.mark.parametrize(
    "other_path, inside, inverted_inside",
    [(Path([(0.25, 0.25), (0.25, 0.75), (0.75, 0.75), (0.75, 0.25), (0.25, 0.25)],
           closed=True), True, False),
     (Path([(-0.25, -0.25), (-0.25, 1.75), (1.75, 1.75), (1.75, -0.25), (-0.25, -0.25)],
           closed=True), False, True),
     (Path([(-0.25, -0.25), (-0.25, 1.75), (0.5, 0.5),
            (1.75, 1.75), (1.75, -0.25), (-0.25, -0.25)],
           closed=True), False, False),
     (Path([(0.25, 0.25), (0.25, 1.25), (1.25, 1.25), (1.25, 0.25), (0.25, 0.25)],
           closed=True), False, False),
     (Path([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)], closed=True), False, False),
     (Path([(2, 2), (2, 3), (3, 3), (3, 2), (2, 2)], closed=True), False, False)])
def test_contains_path(other_path, inside, inverted_inside):
    path = Path([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)], closed=True)
    assert path.contains_path(other_path) is inside
    assert other_path.contains_path(path) is inverted_inside


def test_contains_points_negative_radius():
    path = Path.unit_circle()

    points = [(0.0, 0.0), (1.25, 0.0), (0.9, 0.9)]
    result = path.contains_points(points, radius=-0.5)
    np.testing.assert_equal(result, [True, False, False])


_test_paths = [
    # interior extrema determine extents and degenerate derivative
    Path([[0, 0], [1, 0], [1, 1], [0, 1]],
           [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4]),
    # a quadratic curve
    Path([[0, 0], [0, 1], [1, 0]], [Path.MOVETO, Path.CURVE3, Path.CURVE3]),
    # a linear curve, degenerate vertically
    Path([[0, 1], [1, 1]], [Path.MOVETO, Path.LINETO]),
    # a point
    Path([[1, 2]], [Path.MOVETO]),
]


_test_path_extents = [(0., 0., 0.75, 1.), (0., 0., 1., 0.5), (0., 1., 1., 1.),
                      (1., 2., 1., 2.)]


@pytest.mark.parametrize('path, extents', zip(_test_paths, _test_path_extents))
def test_exact_extents(path, extents):
    # notice that if we just looked at the control points to get the bounding
    # box of each curve, we would get the wrong answers. For example, for
    # hard_curve = Path([[0, 0], [1, 0], [1, 1], [0, 1]],
    #                   [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4])
    # we would get that the extents area (0, 0, 1, 1). This code takes into
    # account the curved part of the path, which does not typically extend all
    # the way out to the control points.
    # Note that counterintuitively, path.get_extents() returns a Bbox, so we
    # have to get that Bbox's `.extents`.
    assert np.all(path.get_extents().extents == extents)


@pytest.mark.parametrize('ignored_code', [Path.CLOSEPOLY, Path.STOP])
def test_extents_with_ignored_codes(ignored_code):
    # Check that STOP and CLOSEPOLY points are ignored when calculating extents
    # of a path with only straight lines
    path = Path([[0, 0],
                 [1, 1],
                 [2, 2]], [Path.MOVETO, Path.MOVETO, ignored_code])
    assert np.all(path.get_extents().extents == (0., 0., 1., 1.))


def test_point_in_path_nan():
    box = np.array([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]])
    p = Path(box)
    test = np.array([[np.nan, 0.5]])
    contains = p.contains_points(test)
    assert len(contains) == 1
    assert not contains[0]


def test_nonlinear_containment():
    fig, ax = plt.subplots()
    ax.set(xscale="log", ylim=(0, 1))
    polygon = ax.axvspan(1, 10)
    assert polygon.get_path().contains_point(
        ax.transData.transform((5, .5)), polygon.get_transform())
    assert not polygon.get_path().contains_point(
        ax.transData.transform((.5, .5)), polygon.get_transform())
    assert not polygon.get_path().contains_point(
        ax.transData.transform((50, .5)), polygon.get_transform())


@image_comparison(['arrow_contains_point.png'], remove_text=True, style='mpl20',
                  tol=0 if platform.machine() == 'x86_64' else 0.027)
def test_arrow_contains_point():
    # fix bug (#8384)
    fig, ax = plt.subplots()
    ax.set_xlim((0, 2))
    ax.set_ylim((0, 2))

    # create an arrow with Curve style
    arrow = patches.FancyArrowPatch((0.5, 0.25), (1.5, 0.75),
                                    arrowstyle='->',
                                    mutation_scale=40)
    ax.add_patch(arrow)
    # create an arrow with Bracket style
    arrow1 = patches.FancyArrowPatch((0.5, 1), (1.5, 1.25),
                                     arrowstyle=']-[',
                                     mutation_scale=40)
    ax.add_patch(arrow1)
    # create an arrow with other arrow style
    arrow2 = patches.FancyArrowPatch((0.5, 1.5), (1.5, 1.75),
                                     arrowstyle='fancy',
                                     fill=False,
                                     mutation_scale=40)
    ax.add_patch(arrow2)
    patches_list = [arrow, arrow1, arrow2]

    # generate some points
    X, Y = np.meshgrid(np.arange(0, 2, 0.1),
                       np.arange(0, 2, 0.1))
    for k, (x, y) in enumerate(zip(X.ravel(), Y.ravel())):
        xdisp, ydisp = ax.transData.transform([x, y])
        event = MouseEvent('button_press_event', fig.canvas, xdisp, ydisp)
        for m, patch in enumerate(patches_list):
            # set the points to red only if the arrow contains the point
            inside, res = patch.contains(event)
            if inside:
                ax.scatter(x, y, s=5, c="r")


@image_comparison(['path_clipping.svg'], remove_text=True)
def test_path_clipping():
    fig = plt.figure(figsize=(6.0, 6.2))

    for i, xy in enumerate([
            [(200, 200), (200, 350), (400, 350), (400, 200)],
            [(200, 200), (200, 350), (400, 350), (400, 100)],
            [(200, 100), (200, 350), (400, 350), (400, 100)],
            [(200, 100), (200, 415), (400, 350), (400, 100)],
            [(200, 100), (200, 415), (400, 415), (400, 100)],
            [(200, 415), (400, 415), (400, 100), (200, 100)],
            [(400, 415), (400, 100), (200, 100), (200, 415)]]):
        ax = fig.add_subplot(4, 2, i+1)
        bbox = [0, 140, 640, 260]
        ax.set_xlim(bbox[0], bbox[0] + bbox[2])
        ax.set_ylim(bbox[1], bbox[1] + bbox[3])
        ax.add_patch(Polygon(
            xy, facecolor='none', edgecolor='red', closed=True))


@image_comparison(['semi_log_with_zero.png'], style='mpl20')
def test_log_transform_with_zero():
    x = np.arange(-10, 10)
    y = (1.0 - 1.0/(x**2+1))**20

    fig, ax = plt.subplots()
    ax.semilogy(x, y, "-o", lw=15, markeredgecolor='k')
    ax.set_ylim(1e-7, 1)
    ax.grid(True)


def test_make_compound_path_empty():
    # We should be able to make a compound path with no arguments.
    # This makes it easier to write generic path based code.
    empty = Path.make_compound_path()
    assert empty.vertices.shape == (0, 2)
    r2 = Path.make_compound_path(empty, empty)
    assert r2.vertices.shape == (0, 2)
    assert r2.codes.shape == (0,)
    r3 = Path.make_compound_path(Path([(0, 0)]), empty)
    assert r3.vertices.shape == (1, 2)
    assert r3.codes.shape == (1,)


def test_make_compound_path_stops():
    zero = [0, 0]
    paths = 3*[Path([zero, zero], [Path.MOVETO, Path.STOP])]
    compound_path = Path.make_compound_path(*paths)
    # the choice to not preserve the terminal STOP is arbitrary, but
    # documented, so we test that it is in fact respected here
    assert np.sum(compound_path.codes == Path.STOP) == 0


@image_comparison(['xkcd.png'], remove_text=True)
def test_xkcd():
    np.random.seed(0)

    x = np.linspace(0, 2 * np.pi, 100)
    y = np.sin(x)

    with plt.xkcd():
        fig, ax = plt.subplots()
        ax.plot(x, y)


@image_comparison(['xkcd_marker.png'], remove_text=True)
def test_xkcd_marker():
    np.random.seed(0)

    x = np.linspace(0, 5, 8)
    y1 = x
    y2 = 5 - x
    y3 = 2.5 * np.ones(8)

    with plt.xkcd():
        fig, ax = plt.subplots()
        ax.plot(x, y1, '+', ms=10)
        ax.plot(x, y2, 'o', ms=10)
        ax.plot(x, y3, '^', ms=10)


@image_comparison(['marker_paths.pdf'], remove_text=True)
def test_marker_paths_pdf():
    N = 7

    plt.errorbar(np.arange(N),
                 np.ones(N) + 4,
                 np.ones(N))
    plt.xlim(-1, N)
    plt.ylim(-1, 7)


@image_comparison(['nan_path'], style='default', remove_text=True,
                  extensions=['pdf', 'svg', 'eps', 'png'],
                  tol=0 if platform.machine() == 'x86_64' else 0.009)
def test_nan_isolated_points():

    y0 = [0, np.nan, 2, np.nan, 4, 5, 6]
    y1 = [np.nan, 7, np.nan, 9, 10, np.nan, 12]

    fig, ax = plt.subplots()

    ax.plot(y0, '-o')
    ax.plot(y1, '-o')


def test_path_no_doubled_point_in_to_polygon():
    hand = np.array(
        [[1.64516129, 1.16145833],
         [1.64516129, 1.59375],
         [1.35080645, 1.921875],
         [1.375, 2.18229167],
         [1.68548387, 1.9375],
         [1.60887097, 2.55208333],
         [1.68548387, 2.69791667],
         [1.76209677, 2.56770833],
         [1.83064516, 1.97395833],
         [1.89516129, 2.75],
         [1.9516129, 2.84895833],
         [2.01209677, 2.76041667],
         [1.99193548, 1.99479167],
         [2.11290323, 2.63020833],
         [2.2016129, 2.734375],
         [2.25403226, 2.60416667],
         [2.14919355, 1.953125],
         [2.30645161, 2.36979167],
         [2.39112903, 2.36979167],
         [2.41532258, 2.1875],
         [2.1733871, 1.703125],
         [2.07782258, 1.16666667]])

    (r0, c0, r1, c1) = (1.0, 1.5, 2.1, 2.5)

    poly = Path(np.vstack((hand[:, 1], hand[:, 0])).T, closed=True)
    clip_rect = transforms.Bbox([[r0, c0], [r1, c1]])
    poly_clipped = poly.clip_to_bbox(clip_rect).to_polygons()[0]

    assert np.all(poly_clipped[-2] != poly_clipped[-1])
    assert np.all(poly_clipped[-1] == poly_clipped[0])


def test_path_to_polygons():
    data = [[10, 10], [20, 20]]
    p = Path(data)

    assert_array_equal(p.to_polygons(width=40, height=40), [])
    assert_array_equal(p.to_polygons(width=40, height=40, closed_only=False),
                       [data])
    assert_array_equal(p.to_polygons(), [])
    assert_array_equal(p.to_polygons(closed_only=False), [data])

    data = [[10, 10], [20, 20], [30, 30]]
    closed_data = [[10, 10], [20, 20], [30, 30], [10, 10]]
    p = Path(data)

    assert_array_equal(p.to_polygons(width=40, height=40), [closed_data])
    assert_array_equal(p.to_polygons(width=40, height=40, closed_only=False),
                       [data])
    assert_array_equal(p.to_polygons(), [closed_data])
    assert_array_equal(p.to_polygons(closed_only=False), [data])


def test_path_deepcopy():
    # Should not raise any error
    verts = [[0, 0], [1, 1]]
    codes = [Path.MOVETO, Path.LINETO]
    path1 = Path(verts, readonly=True)
    path2 = Path(verts, codes, readonly=True)
    path1_copy = path1.deepcopy()
    path2_copy = path2.deepcopy()
    assert path1 is not path1_copy
    assert path1.vertices is not path1_copy.vertices
    assert_array_equal(path1.vertices, path1_copy.vertices)
    assert path1.readonly
    assert not path1_copy.readonly
    assert path2 is not path2_copy
    assert path2.vertices is not path2_copy.vertices
    assert_array_equal(path2.vertices, path2_copy.vertices)
    assert path2.codes is not path2_copy.codes
    assert_array_equal(path2.codes, path2_copy.codes)
    assert path2.readonly
    assert not path2_copy.readonly


def test_path_deepcopy_cycle():
    class PathWithCycle(Path):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.x = self

    p = PathWithCycle([[0, 0], [1, 1]], readonly=True)
    p_copy = p.deepcopy()
    assert p_copy is not p
    assert p.readonly
    assert not p_copy.readonly
    assert p_copy.x is p_copy

    class PathWithCycle2(Path):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.x = [self] * 2

    p2 = PathWithCycle2([[0, 0], [1, 1]], readonly=True)
    p2_copy = p2.deepcopy()
    assert p2_copy is not p2
    assert p2.readonly
    assert not p2_copy.readonly
    assert p2_copy.x[0] is p2_copy
    assert p2_copy.x[1] is p2_copy


def test_path_shallowcopy():
    # Should not raise any error
    verts = [[0, 0], [1, 1]]
    codes = [Path.MOVETO, Path.LINETO]
    path1 = Path(verts)
    path2 = Path(verts, codes)
    path1_copy = path1.copy()
    path2_copy = path2.copy()
    assert path1 is not path1_copy
    assert path1.vertices is path1_copy.vertices
    assert path2 is not path2_copy
    assert path2.vertices is path2_copy.vertices
    assert path2.codes is path2_copy.codes


@pytest.mark.parametrize('phi', np.concatenate([
    np.array([0, 15, 30, 45, 60, 75, 90, 105, 120, 135]) + delta
    for delta in [-1, 0, 1]]))
def test_path_intersect_path(phi):
    # test for the range of intersection angles
    eps_array = [1e-5, 1e-8, 1e-10, 1e-12]

    transform = transforms.Affine2D().rotate(np.deg2rad(phi))

    # a and b intersect at angle phi
    a = Path([(-2, 0), (2, 0)])
    b = transform.transform_path(a)
    assert a.intersects_path(b) and b.intersects_path(a)

    # a and b touch at angle phi at (0, 0)
    a = Path([(0, 0), (2, 0)])
    b = transform.transform_path(a)
    assert a.intersects_path(b) and b.intersects_path(a)

    # a and b are orthogonal and intersect at (0, 3)
    a = transform.transform_path(Path([(0, 1), (0, 3)]))
    b = transform.transform_path(Path([(1, 3), (0, 3)]))
    assert a.intersects_path(b) and b.intersects_path(a)

    # a and b are collinear and intersect at (0, 3)
    a = transform.transform_path(Path([(0, 1), (0, 3)]))
    b = transform.transform_path(Path([(0, 5), (0, 3)]))
    assert a.intersects_path(b) and b.intersects_path(a)

    # self-intersect
    assert a.intersects_path(a)

    # a contains b
    a = transform.transform_path(Path([(0, 0), (5, 5)]))
    b = transform.transform_path(Path([(1, 1), (3, 3)]))
    assert a.intersects_path(b) and b.intersects_path(a)

    # a and b are collinear but do not intersect
    a = transform.transform_path(Path([(0, 1), (0, 5)]))
    b = transform.transform_path(Path([(3, 0), (3, 3)]))
    assert not a.intersects_path(b) and not b.intersects_path(a)

    # a and b are on the same line but do not intersect
    a = transform.transform_path(Path([(0, 1), (0, 5)]))
    b = transform.transform_path(Path([(0, 6), (0, 7)]))
    assert not a.intersects_path(b) and not b.intersects_path(a)

    # Note: 1e-13 is the absolute tolerance error used for
    # `isclose` function from src/_path.h

    # a and b are parallel but do not touch
    for eps in eps_array:
        a = transform.transform_path(Path([(0, 1), (0, 5)]))
        b = transform.transform_path(Path([(0 + eps, 1), (0 + eps, 5)]))
        assert not a.intersects_path(b) and not b.intersects_path(a)

    # a and b are on the same line but do not intersect (really close)
    for eps in eps_array:
        a = transform.transform_path(Path([(0, 1), (0, 5)]))
        b = transform.transform_path(Path([(0, 5 + eps), (0, 7)]))
        assert not a.intersects_path(b) and not b.intersects_path(a)

    # a and b are on the same line and intersect (really close)
    for eps in eps_array:
        a = transform.transform_path(Path([(0, 1), (0, 5)]))
        b = transform.transform_path(Path([(0, 5 - eps), (0, 7)]))
        assert a.intersects_path(b) and b.intersects_path(a)

    # b is the same as a but with an extra point
    a = transform.transform_path(Path([(0, 1), (0, 5)]))
    b = transform.transform_path(Path([(0, 1), (0, 2), (0, 5)]))
    assert a.intersects_path(b) and b.intersects_path(a)

    # a and b are collinear but do not intersect
    a = transform.transform_path(Path([(1, -1), (0, -1)]))
    b = transform.transform_path(Path([(0, 1), (0.9, 1)]))
    assert not a.intersects_path(b) and not b.intersects_path(a)

    # a and b are collinear but do not intersect
    a = transform.transform_path(Path([(0., -5.), (1., -5.)]))
    b = transform.transform_path(Path([(1., 5.), (0., 5.)]))
    assert not a.intersects_path(b) and not b.intersects_path(a)


@pytest.mark.parametrize('offset', range(-720, 361, 45))
def test_full_arc(offset):
    low = offset
    high = 360 + offset

    path = Path.arc(low, high)
    mins = np.min(path.vertices, axis=0)
    maxs = np.max(path.vertices, axis=0)
    np.testing.assert_allclose(mins, -1)
    np.testing.assert_allclose(maxs, 1)


def test_disjoint_zero_length_segment():
    this_path = Path(
        np.array([
            [824.85064295, 2056.26489203],
            [861.69033931, 2041.00539016],
            [868.57864109, 2057.63522175],
            [831.73894473, 2072.89472361],
            [824.85064295, 2056.26489203]]),
        np.array([1, 2, 2, 2, 79], dtype=Path.code_type))

    outline_path = Path(
        np.array([
            [859.91051028, 2165.38461538],
            [859.06772495, 2149.30331334],
            [859.06772495, 2181.46591743],
            [859.91051028, 2165.38461538],
            [859.91051028, 2165.38461538]]),
        np.array([1, 2, 2, 2, 2],
                 dtype=Path.code_type))

    assert not outline_path.intersects_path(this_path)
    assert not this_path.intersects_path(outline_path)


def test_intersect_zero_length_segment():
    this_path = Path(
        np.array([
            [0, 0],
            [1, 1],
        ]))

    outline_path = Path(
        np.array([
            [1, 0],
            [.5, .5],
            [.5, .5],
            [0, 1],
        ]))

    assert outline_path.intersects_path(this_path)
    assert this_path.intersects_path(outline_path)


def test_cleanup_closepoly():
    # if the first connected component of a Path ends in a CLOSEPOLY, but that
    # component contains a NaN, then Path.cleaned should ignore not just the
    # control points but also the CLOSEPOLY, since it has nowhere valid to
    # point.
    paths = [
        Path([[np.nan, np.nan], [np.nan, np.nan]],
             [Path.MOVETO, Path.CLOSEPOLY]),
        # we trigger a different path in the C++ code if we don't pass any
        # codes explicitly, so we must also make sure that this works
        Path([[np.nan, np.nan], [np.nan, np.nan]]),
        # we should also make sure that this cleanup works if there's some
        # multi-vertex curves
        Path([[np.nan, np.nan], [np.nan, np.nan], [np.nan, np.nan],
              [np.nan, np.nan]],
             [Path.MOVETO, Path.CURVE3, Path.CURVE3, Path.CLOSEPOLY])
    ]
    for p in paths:
        cleaned = p.cleaned(remove_nans=True)
        assert len(cleaned) == 1
        assert cleaned.codes[0] == Path.STOP


def test_interpolated_moveto():
    # Initial path has two subpaths with two LINETOs each
    vertices = np.array([[0, 0],
                         [0, 1],
                         [1, 2],
                         [4, 4],
                         [4, 5],
                         [5, 5]])
    codes = [Path.MOVETO, Path.LINETO, Path.LINETO] * 2

    path = Path(vertices, codes)
    result = path.interpolated(3)

    # Result should have two subpaths with six LINETOs each
    expected_subpath_codes = [Path.MOVETO] + [Path.LINETO] * 6
    np.testing.assert_array_equal(result.codes, expected_subpath_codes * 2)


def test_interpolated_closepoly():
    codes = [Path.MOVETO] + [Path.LINETO]*2 + [Path.CLOSEPOLY]
    vertices = [(4, 3), (5, 4), (5, 3), (0, 0)]

    path = Path(vertices, codes)
    result = path.interpolated(2)

    expected_vertices = np.array([[4, 3],
                                  [4.5, 3.5],
                                  [5, 4],
                                  [5, 3.5],
                                  [5, 3],
                                  [4.5, 3],
                                  [4, 3]])
    expected_codes = [Path.MOVETO] + [Path.LINETO]*5 + [Path.CLOSEPOLY]

    np.testing.assert_allclose(result.vertices, expected_vertices)
    np.testing.assert_array_equal(result.codes, expected_codes)

    # Usually closepoly is the last vertex but does not have to be.
    codes += [Path.LINETO]
    vertices += [(2, 1)]

    path = Path(vertices, codes)
    result = path.interpolated(2)

    extra_expected_vertices = np.array([[3, 2],
                                        [2, 1]])
    expected_vertices = np.concatenate([expected_vertices, extra_expected_vertices])

    expected_codes += [Path.LINETO] * 2

    np.testing.assert_allclose(result.vertices, expected_vertices)
    np.testing.assert_array_equal(result.codes, expected_codes)


def test_interpolated_moveto_closepoly():
    # Initial path has two closed subpaths
    codes = ([Path.MOVETO] + [Path.LINETO]*2 + [Path.CLOSEPOLY]) * 2
    vertices = [(4, 3), (5, 4), (5, 3), (0, 0), (8, 6), (10, 8), (10, 6), (0, 0)]

    path = Path(vertices, codes)
    result = path.interpolated(2)

    expected_vertices1 = np.array([[4, 3],
                                   [4.5, 3.5],
                                   [5, 4],
                                   [5, 3.5],
                                   [5, 3],
                                   [4.5, 3],
                                   [4, 3]])
    expected_vertices = np.concatenate([expected_vertices1, expected_vertices1 * 2])
    expected_codes = ([Path.MOVETO] + [Path.LINETO]*5 + [Path.CLOSEPOLY]) * 2

    np.testing.assert_allclose(result.vertices, expected_vertices)
    np.testing.assert_array_equal(result.codes, expected_codes)


def test_interpolated_empty_path():
    path = Path(np.zeros((0, 2)))
    assert path.interpolated(42) is path
