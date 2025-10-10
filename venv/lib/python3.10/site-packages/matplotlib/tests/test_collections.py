from datetime import datetime
import io
import itertools
import platform
import re
from types import SimpleNamespace

import numpy as np
from numpy.testing import assert_array_equal, assert_array_almost_equal
import pytest

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.collections as mcollections
import matplotlib.colors as mcolors
import matplotlib.path as mpath
import matplotlib.transforms as mtransforms
from matplotlib.collections import (Collection, LineCollection,
                                    EventCollection, PolyCollection)
from matplotlib.collections import FillBetweenPolyCollection
from matplotlib.testing.decorators import check_figures_equal, image_comparison


@pytest.fixture(params=["pcolormesh", "pcolor"])
def pcfunc(request):
    return request.param


def generate_EventCollection_plot():
    """Generate the initial collection and plot it."""
    positions = np.array([0., 1., 2., 3., 5., 8., 13., 21.])
    extra_positions = np.array([34., 55., 89.])
    orientation = 'horizontal'
    lineoffset = 1
    linelength = .5
    linewidth = 2
    color = [1, 0, 0, 1]
    linestyle = 'solid'
    antialiased = True

    coll = EventCollection(positions,
                           orientation=orientation,
                           lineoffset=lineoffset,
                           linelength=linelength,
                           linewidth=linewidth,
                           color=color,
                           linestyle=linestyle,
                           antialiased=antialiased
                           )

    fig, ax = plt.subplots()
    ax.add_collection(coll)
    ax.set_title('EventCollection: default')
    props = {'positions': positions,
             'extra_positions': extra_positions,
             'orientation': orientation,
             'lineoffset': lineoffset,
             'linelength': linelength,
             'linewidth': linewidth,
             'color': color,
             'linestyle': linestyle,
             'antialiased': antialiased
             }
    ax.set_xlim(-1, 22)
    ax.set_ylim(0, 2)
    return ax, coll, props


@image_comparison(['EventCollection_plot__default.png'])
def test__EventCollection__get_props():
    _, coll, props = generate_EventCollection_plot()
    # check that the default segments have the correct coordinates
    check_segments(coll,
                   props['positions'],
                   props['linelength'],
                   props['lineoffset'],
                   props['orientation'])
    # check that the default positions match the input positions
    np.testing.assert_array_equal(props['positions'], coll.get_positions())
    # check that the default orientation matches the input orientation
    assert props['orientation'] == coll.get_orientation()
    # check that the default orientation matches the input orientation
    assert coll.is_horizontal()
    # check that the default linelength matches the input linelength
    assert props['linelength'] == coll.get_linelength()
    # check that the default lineoffset matches the input lineoffset
    assert props['lineoffset'] == coll.get_lineoffset()
    # check that the default linestyle matches the input linestyle
    assert coll.get_linestyle() == [(0, None)]
    # check that the default color matches the input color
    for color in [coll.get_color(), *coll.get_colors()]:
        np.testing.assert_array_equal(color, props['color'])


@image_comparison(['EventCollection_plot__set_positions.png'])
def test__EventCollection__set_positions():
    splt, coll, props = generate_EventCollection_plot()
    new_positions = np.hstack([props['positions'], props['extra_positions']])
    coll.set_positions(new_positions)
    np.testing.assert_array_equal(new_positions, coll.get_positions())
    check_segments(coll, new_positions,
                   props['linelength'],
                   props['lineoffset'],
                   props['orientation'])
    splt.set_title('EventCollection: set_positions')
    splt.set_xlim(-1, 90)


@image_comparison(['EventCollection_plot__add_positions.png'])
def test__EventCollection__add_positions():
    splt, coll, props = generate_EventCollection_plot()
    new_positions = np.hstack([props['positions'],
                               props['extra_positions'][0]])
    coll.switch_orientation()  # Test adding in the vertical orientation, too.
    coll.add_positions(props['extra_positions'][0])
    coll.switch_orientation()
    np.testing.assert_array_equal(new_positions, coll.get_positions())
    check_segments(coll,
                   new_positions,
                   props['linelength'],
                   props['lineoffset'],
                   props['orientation'])
    splt.set_title('EventCollection: add_positions')
    splt.set_xlim(-1, 35)


@image_comparison(['EventCollection_plot__append_positions.png'])
def test__EventCollection__append_positions():
    splt, coll, props = generate_EventCollection_plot()
    new_positions = np.hstack([props['positions'],
                               props['extra_positions'][2]])
    coll.append_positions(props['extra_positions'][2])
    np.testing.assert_array_equal(new_positions, coll.get_positions())
    check_segments(coll,
                   new_positions,
                   props['linelength'],
                   props['lineoffset'],
                   props['orientation'])
    splt.set_title('EventCollection: append_positions')
    splt.set_xlim(-1, 90)


@image_comparison(['EventCollection_plot__extend_positions.png'])
def test__EventCollection__extend_positions():
    splt, coll, props = generate_EventCollection_plot()
    new_positions = np.hstack([props['positions'],
                               props['extra_positions'][1:]])
    coll.extend_positions(props['extra_positions'][1:])
    np.testing.assert_array_equal(new_positions, coll.get_positions())
    check_segments(coll,
                   new_positions,
                   props['linelength'],
                   props['lineoffset'],
                   props['orientation'])
    splt.set_title('EventCollection: extend_positions')
    splt.set_xlim(-1, 90)


@image_comparison(['EventCollection_plot__switch_orientation.png'])
def test__EventCollection__switch_orientation():
    splt, coll, props = generate_EventCollection_plot()
    new_orientation = 'vertical'
    coll.switch_orientation()
    assert new_orientation == coll.get_orientation()
    assert not coll.is_horizontal()
    new_positions = coll.get_positions()
    check_segments(coll,
                   new_positions,
                   props['linelength'],
                   props['lineoffset'], new_orientation)
    splt.set_title('EventCollection: switch_orientation')
    splt.set_ylim(-1, 22)
    splt.set_xlim(0, 2)


@image_comparison(['EventCollection_plot__switch_orientation__2x.png'])
def test__EventCollection__switch_orientation_2x():
    """
    Check that calling switch_orientation twice sets the orientation back to
    the default.
    """
    splt, coll, props = generate_EventCollection_plot()
    coll.switch_orientation()
    coll.switch_orientation()
    new_positions = coll.get_positions()
    assert props['orientation'] == coll.get_orientation()
    assert coll.is_horizontal()
    np.testing.assert_array_equal(props['positions'], new_positions)
    check_segments(coll,
                   new_positions,
                   props['linelength'],
                   props['lineoffset'],
                   props['orientation'])
    splt.set_title('EventCollection: switch_orientation 2x')


@image_comparison(['EventCollection_plot__set_orientation.png'])
def test__EventCollection__set_orientation():
    splt, coll, props = generate_EventCollection_plot()
    new_orientation = 'vertical'
    coll.set_orientation(new_orientation)
    assert new_orientation == coll.get_orientation()
    assert not coll.is_horizontal()
    check_segments(coll,
                   props['positions'],
                   props['linelength'],
                   props['lineoffset'],
                   new_orientation)
    splt.set_title('EventCollection: set_orientation')
    splt.set_ylim(-1, 22)
    splt.set_xlim(0, 2)


@image_comparison(['EventCollection_plot__set_linelength.png'])
def test__EventCollection__set_linelength():
    splt, coll, props = generate_EventCollection_plot()
    new_linelength = 15
    coll.set_linelength(new_linelength)
    assert new_linelength == coll.get_linelength()
    check_segments(coll,
                   props['positions'],
                   new_linelength,
                   props['lineoffset'],
                   props['orientation'])
    splt.set_title('EventCollection: set_linelength')
    splt.set_ylim(-20, 20)


@image_comparison(['EventCollection_plot__set_lineoffset.png'])
def test__EventCollection__set_lineoffset():
    splt, coll, props = generate_EventCollection_plot()
    new_lineoffset = -5.
    coll.set_lineoffset(new_lineoffset)
    assert new_lineoffset == coll.get_lineoffset()
    check_segments(coll,
                   props['positions'],
                   props['linelength'],
                   new_lineoffset,
                   props['orientation'])
    splt.set_title('EventCollection: set_lineoffset')
    splt.set_ylim(-6, -4)


@image_comparison([
    'EventCollection_plot__set_linestyle.png',
    'EventCollection_plot__set_linestyle.png',
    'EventCollection_plot__set_linewidth.png',
])
def test__EventCollection__set_prop():
    for prop, value, expected in [
            ('linestyle', 'dashed', [(0, (6.0, 6.0))]),
            ('linestyle', (0, (6., 6.)), [(0, (6.0, 6.0))]),
            ('linewidth', 5, 5),
    ]:
        splt, coll, _ = generate_EventCollection_plot()
        coll.set(**{prop: value})
        assert plt.getp(coll, prop) == expected
        splt.set_title(f'EventCollection: set_{prop}')


@image_comparison(['EventCollection_plot__set_color.png'])
def test__EventCollection__set_color():
    splt, coll, _ = generate_EventCollection_plot()
    new_color = np.array([0, 1, 1, 1])
    coll.set_color(new_color)
    for color in [coll.get_color(), *coll.get_colors()]:
        np.testing.assert_array_equal(color, new_color)
    splt.set_title('EventCollection: set_color')


def check_segments(coll, positions, linelength, lineoffset, orientation):
    """
    Test helper checking that all values in the segment are correct, given a
    particular set of inputs.
    """
    segments = coll.get_segments()
    if (orientation.lower() == 'horizontal'
            or orientation.lower() == 'none' or orientation is None):
        # if horizontal, the position in is in the y-axis
        pos1 = 1
        pos2 = 0
    elif orientation.lower() == 'vertical':
        # if vertical, the position in is in the x-axis
        pos1 = 0
        pos2 = 1
    else:
        raise ValueError("orientation must be 'horizontal' or 'vertical'")

    # test to make sure each segment is correct
    for i, segment in enumerate(segments):
        assert segment[0, pos1] == lineoffset + linelength / 2
        assert segment[1, pos1] == lineoffset - linelength / 2
        assert segment[0, pos2] == positions[i]
        assert segment[1, pos2] == positions[i]


def test_collection_norm_autoscale():
    # norm should be autoscaled when array is set, not deferred to draw time
    lines = np.arange(24).reshape((4, 3, 2))
    coll = mcollections.LineCollection(lines, array=np.arange(4))
    assert coll.norm(2) == 2 / 3
    # setting a new array shouldn't update the already scaled limits
    coll.set_array(np.arange(4) + 5)
    assert coll.norm(2) == 2 / 3


def test_null_collection_datalim():
    col = mcollections.PathCollection([])
    col_data_lim = col.get_datalim(mtransforms.IdentityTransform())
    assert_array_equal(col_data_lim.get_points(),
                       mtransforms.Bbox.null().get_points())


def test_no_offsets_datalim():
    # A collection with no offsets and a non transData
    # transform should return a null bbox
    ax = plt.axes()
    coll = mcollections.PathCollection([mpath.Path([(0, 0), (1, 0)])])
    ax.add_collection(coll)
    coll_data_lim = coll.get_datalim(mtransforms.IdentityTransform())
    assert_array_equal(coll_data_lim.get_points(),
                       mtransforms.Bbox.null().get_points())


def test_add_collection():
    # Test if data limits are unchanged by adding an empty collection.
    # GitHub issue #1490, pull #1497.
    plt.figure()
    ax = plt.axes()
    ax.scatter([0, 1], [0, 1])
    bounds = ax.dataLim.bounds
    ax.scatter([], [])
    assert ax.dataLim.bounds == bounds


@mpl.style.context('mpl20')
@check_figures_equal(extensions=['png'])
def test_collection_log_datalim(fig_test, fig_ref):
    # Data limits should respect the minimum x/y when using log scale.
    x_vals = [4.38462e-6, 5.54929e-6, 7.02332e-6, 8.88889e-6, 1.12500e-5,
              1.42383e-5, 1.80203e-5, 2.28070e-5, 2.88651e-5, 3.65324e-5,
              4.62363e-5, 5.85178e-5, 7.40616e-5, 9.37342e-5, 1.18632e-4]
    y_vals = [0.0, 0.1, 0.182, 0.332, 0.604, 1.1, 2.0, 3.64, 6.64, 12.1, 22.0,
              39.6, 71.3]

    x, y = np.meshgrid(x_vals, y_vals)
    x = x.flatten()
    y = y.flatten()

    ax_test = fig_test.subplots()
    ax_test.set_xscale('log')
    ax_test.set_yscale('log')
    ax_test.margins = 0
    ax_test.scatter(x, y)

    ax_ref = fig_ref.subplots()
    ax_ref.set_xscale('log')
    ax_ref.set_yscale('log')
    ax_ref.plot(x, y, marker="o", ls="")


def test_quiver_limits():
    ax = plt.axes()
    x, y = np.arange(8), np.arange(10)
    u = v = np.linspace(0, 10, 80).reshape(10, 8)
    q = plt.quiver(x, y, u, v)
    assert q.get_datalim(ax.transData).bounds == (0., 0., 7., 9.)

    plt.figure()
    ax = plt.axes()
    x = np.linspace(-5, 10, 20)
    y = np.linspace(-2, 4, 10)
    y, x = np.meshgrid(y, x)
    trans = mtransforms.Affine2D().translate(25, 32) + ax.transData
    plt.quiver(x, y, np.sin(x), np.cos(y), transform=trans)
    assert ax.dataLim.bounds == (20.0, 30.0, 15.0, 6.0)


def test_barb_limits():
    ax = plt.axes()
    x = np.linspace(-5, 10, 20)
    y = np.linspace(-2, 4, 10)
    y, x = np.meshgrid(y, x)
    trans = mtransforms.Affine2D().translate(25, 32) + ax.transData
    plt.barbs(x, y, np.sin(x), np.cos(y), transform=trans)
    # The calculated bounds are approximately the bounds of the original data,
    # this is because the entire path is taken into account when updating the
    # datalim.
    assert_array_almost_equal(ax.dataLim.bounds, (20, 30, 15, 6),
                              decimal=1)


@image_comparison(['EllipseCollection_test_image.png'], remove_text=True,
                  tol=0 if platform.machine() == 'x86_64' else 0.021)
def test_EllipseCollection():
    # Test basic functionality
    fig, ax = plt.subplots()
    x = np.arange(4)
    y = np.arange(3)
    X, Y = np.meshgrid(x, y)
    XY = np.vstack((X.ravel(), Y.ravel())).T

    ww = X / x[-1]
    hh = Y / y[-1]
    aa = np.ones_like(ww) * 20  # first axis is 20 degrees CCW from x axis

    ec = mcollections.EllipseCollection(
        ww, hh, aa, units='x', offsets=XY, offset_transform=ax.transData,
        facecolors='none')
    ax.add_collection(ec)
    ax.autoscale_view()


def test_EllipseCollection_setter_getter():
    # Test widths, heights and angle setter
    rng = np.random.default_rng(0)

    widths = (2, )
    heights = (3, )
    angles = (45, )
    offsets = rng.random((10, 2)) * 10

    fig, ax = plt.subplots()

    ec = mcollections.EllipseCollection(
        widths=widths,
        heights=heights,
        angles=angles,
        offsets=offsets,
        units='x',
        offset_transform=ax.transData,
        )

    assert_array_almost_equal(ec._widths, np.array(widths).ravel() * 0.5)
    assert_array_almost_equal(ec._heights, np.array(heights).ravel() * 0.5)
    assert_array_almost_equal(ec._angles, np.deg2rad(angles).ravel())

    assert_array_almost_equal(ec.get_widths(), widths)
    assert_array_almost_equal(ec.get_heights(), heights)
    assert_array_almost_equal(ec.get_angles(), angles)

    ax.add_collection(ec)
    ax.set_xlim(-2, 12)
    ax.set_ylim(-2, 12)

    new_widths = rng.random((10, 2)) * 2
    new_heights = rng.random((10, 2)) * 3
    new_angles = rng.random((10, 2)) * 180

    ec.set(widths=new_widths, heights=new_heights, angles=new_angles)

    assert_array_almost_equal(ec.get_widths(), new_widths.ravel())
    assert_array_almost_equal(ec.get_heights(), new_heights.ravel())
    assert_array_almost_equal(ec.get_angles(), new_angles.ravel())


@image_comparison(['polycollection_close.png'], remove_text=True, style='mpl20')
def test_polycollection_close():
    from mpl_toolkits.mplot3d import Axes3D  # type: ignore[import]
    plt.rcParams['axes3d.automargin'] = True

    vertsQuad = [
        [[0., 0.], [0., 1.], [1., 1.], [1., 0.]],
        [[0., 1.], [2., 3.], [2., 2.], [1., 1.]],
        [[2., 2.], [2., 3.], [4., 1.], [3., 1.]],
        [[3., 0.], [3., 1.], [4., 1.], [4., 0.]]]

    fig = plt.figure()
    ax = fig.add_axes(Axes3D(fig))

    colors = ['r', 'g', 'b', 'y', 'k']
    zpos = list(range(5))

    poly = mcollections.PolyCollection(
        vertsQuad * len(zpos), linewidth=0.25)
    poly.set_alpha(0.7)

    # need to have a z-value for *each* polygon = element!
    zs = []
    cs = []
    for z, c in zip(zpos, colors):
        zs.extend([z] * len(vertsQuad))
        cs.extend([c] * len(vertsQuad))

    poly.set_color(cs)

    ax.add_collection3d(poly, zs=zs, zdir='y')

    # axis limit settings:
    ax.set_xlim3d(0, 4)
    ax.set_zlim3d(0, 3)
    ax.set_ylim3d(0, 4)


@image_comparison(['regularpolycollection_rotate.png'], remove_text=True)
def test_regularpolycollection_rotate():
    xx, yy = np.mgrid[:10, :10]
    xy_points = np.transpose([xx.flatten(), yy.flatten()])
    rotations = np.linspace(0, 2*np.pi, len(xy_points))

    fig, ax = plt.subplots()
    for xy, alpha in zip(xy_points, rotations):
        col = mcollections.RegularPolyCollection(
            4, sizes=(100,), rotation=alpha,
            offsets=[xy], offset_transform=ax.transData)
        ax.add_collection(col, autolim=True)
    ax.autoscale_view()


@image_comparison(['regularpolycollection_scale.png'], remove_text=True)
def test_regularpolycollection_scale():
    # See issue #3860

    class SquareCollection(mcollections.RegularPolyCollection):
        def __init__(self, **kwargs):
            super().__init__(4, rotation=np.pi/4., **kwargs)

        def get_transform(self):
            """Return transform scaling circle areas to data space."""
            ax = self.axes

            pts2pixels = 72.0 / ax.get_figure(root=True).dpi

            scale_x = pts2pixels * ax.bbox.width / ax.viewLim.width
            scale_y = pts2pixels * ax.bbox.height / ax.viewLim.height
            return mtransforms.Affine2D().scale(scale_x, scale_y)

    fig, ax = plt.subplots()

    xy = [(0, 0)]
    # Unit square has a half-diagonal of `1/sqrt(2)`, so `pi * r**2` equals...
    circle_areas = [np.pi / 2]
    squares = SquareCollection(
        sizes=circle_areas, offsets=xy, offset_transform=ax.transData)
    ax.add_collection(squares, autolim=True)
    ax.axis([-1, 1, -1, 1])


def test_picking():
    fig, ax = plt.subplots()
    col = ax.scatter([0], [0], [1000], picker=True)
    fig.savefig(io.BytesIO(), dpi=fig.dpi)
    mouse_event = SimpleNamespace(x=325, y=240)
    found, indices = col.contains(mouse_event)
    assert found
    assert_array_equal(indices['ind'], [0])


def test_quadmesh_contains():
    x = np.arange(4)
    X = x[:, None] * x[None, :]

    fig, ax = plt.subplots()
    mesh = ax.pcolormesh(X)
    fig.draw_without_rendering()
    xdata, ydata = 0.5, 0.5
    x, y = mesh.get_transform().transform((xdata, ydata))
    mouse_event = SimpleNamespace(xdata=xdata, ydata=ydata, x=x, y=y)
    found, indices = mesh.contains(mouse_event)
    assert found
    assert_array_equal(indices['ind'], [0])

    xdata, ydata = 1.5, 1.5
    x, y = mesh.get_transform().transform((xdata, ydata))
    mouse_event = SimpleNamespace(xdata=xdata, ydata=ydata, x=x, y=y)
    found, indices = mesh.contains(mouse_event)
    assert found
    assert_array_equal(indices['ind'], [5])


def test_quadmesh_contains_concave():
    # Test a concave polygon, V-like shape
    x = [[0, -1], [1, 0]]
    y = [[0, 1], [1, -1]]
    fig, ax = plt.subplots()
    mesh = ax.pcolormesh(x, y, [[0]])
    fig.draw_without_rendering()
    # xdata, ydata, expected
    points = [(-0.5, 0.25, True),  # left wing
              (0, 0.25, False),  # between the two wings
              (0.5, 0.25, True),  # right wing
              (0, -0.25, True),  # main body
              ]
    for point in points:
        xdata, ydata, expected = point
        x, y = mesh.get_transform().transform((xdata, ydata))
        mouse_event = SimpleNamespace(xdata=xdata, ydata=ydata, x=x, y=y)
        found, indices = mesh.contains(mouse_event)
        assert found is expected


def test_quadmesh_cursor_data():
    x = np.arange(4)
    X = x[:, None] * x[None, :]

    fig, ax = plt.subplots()
    mesh = ax.pcolormesh(X)
    # Empty array data
    mesh._A = None
    fig.draw_without_rendering()
    xdata, ydata = 0.5, 0.5
    x, y = mesh.get_transform().transform((xdata, ydata))
    mouse_event = SimpleNamespace(xdata=xdata, ydata=ydata, x=x, y=y)
    # Empty collection should return None
    assert mesh.get_cursor_data(mouse_event) is None

    # Now test adding the array data, to make sure we do get a value
    mesh.set_array(np.ones(X.shape))
    assert_array_equal(mesh.get_cursor_data(mouse_event), [1])


def test_quadmesh_cursor_data_multiple_points():
    x = [1, 2, 1, 2]
    fig, ax = plt.subplots()
    mesh = ax.pcolormesh(x, x, np.ones((3, 3)))
    fig.draw_without_rendering()
    xdata, ydata = 1.5, 1.5
    x, y = mesh.get_transform().transform((xdata, ydata))
    mouse_event = SimpleNamespace(xdata=xdata, ydata=ydata, x=x, y=y)
    # All quads are covering the same square
    assert_array_equal(mesh.get_cursor_data(mouse_event), np.ones(9))


def test_linestyle_single_dashes():
    plt.scatter([0, 1, 2], [0, 1, 2], linestyle=(0., [2., 2.]))
    plt.draw()


@image_comparison(['size_in_xy.png'], remove_text=True)
def test_size_in_xy():
    fig, ax = plt.subplots()

    widths, heights, angles = (10, 10), 10, 0
    widths = 10, 10
    coords = [(10, 10), (15, 15)]
    e = mcollections.EllipseCollection(
        widths, heights, angles, units='xy',
        offsets=coords, offset_transform=ax.transData)

    ax.add_collection(e)

    ax.set_xlim(0, 30)
    ax.set_ylim(0, 30)


def test_pandas_indexing(pd):

    # Should not fail break when faced with a
    # non-zero indexed series
    index = [11, 12, 13]
    ec = fc = pd.Series(['red', 'blue', 'green'], index=index)
    lw = pd.Series([1, 2, 3], index=index)
    ls = pd.Series(['solid', 'dashed', 'dashdot'], index=index)
    aa = pd.Series([True, False, True], index=index)

    Collection(edgecolors=ec)
    Collection(facecolors=fc)
    Collection(linewidths=lw)
    Collection(linestyles=ls)
    Collection(antialiaseds=aa)


@mpl.style.context('default')
def test_lslw_bcast():
    col = mcollections.PathCollection([])
    col.set_linestyles(['-', '-'])
    col.set_linewidths([1, 2, 3])

    assert col.get_linestyles() == [(0, None)] * 6
    assert col.get_linewidths() == [1, 2, 3] * 2

    col.set_linestyles(['-', '-', '-'])
    assert col.get_linestyles() == [(0, None)] * 3
    assert (col.get_linewidths() == [1, 2, 3]).all()


def test_set_wrong_linestyle():
    c = Collection()
    with pytest.raises(ValueError, match="Do not know how to convert 'fuzzy'"):
        c.set_linestyle('fuzzy')


@mpl.style.context('default')
def test_capstyle():
    col = mcollections.PathCollection([])
    assert col.get_capstyle() is None
    col = mcollections.PathCollection([], capstyle='round')
    assert col.get_capstyle() == 'round'
    col.set_capstyle('butt')
    assert col.get_capstyle() == 'butt'


@mpl.style.context('default')
def test_joinstyle():
    col = mcollections.PathCollection([])
    assert col.get_joinstyle() is None
    col = mcollections.PathCollection([], joinstyle='round')
    assert col.get_joinstyle() == 'round'
    col.set_joinstyle('miter')
    assert col.get_joinstyle() == 'miter'


@image_comparison(['cap_and_joinstyle.png'])
def test_cap_and_joinstyle_image():
    fig, ax = plt.subplots()
    ax.set_xlim([-0.5, 1.5])
    ax.set_ylim([-0.5, 2.5])

    x = np.array([0.0, 1.0, 0.5])
    ys = np.array([[0.0], [0.5], [1.0]]) + np.array([[0.0, 0.0, 1.0]])

    segs = np.zeros((3, 3, 2))
    segs[:, :, 0] = x
    segs[:, :, 1] = ys
    line_segments = LineCollection(segs, linewidth=[10, 15, 20])
    line_segments.set_capstyle("round")
    line_segments.set_joinstyle("miter")

    ax.add_collection(line_segments)
    ax.set_title('Line collection with customized caps and joinstyle')


@image_comparison(['scatter_post_alpha.png'],
                  remove_text=True, style='default')
def test_scatter_post_alpha():
    fig, ax = plt.subplots()
    sc = ax.scatter(range(5), range(5), c=range(5))
    sc.set_alpha(.1)


def test_scatter_alpha_array():
    x = np.arange(5)
    alpha = x / 5
    # With colormapping.
    fig, (ax0, ax1) = plt.subplots(2)
    sc0 = ax0.scatter(x, x, c=x, alpha=alpha)
    sc1 = ax1.scatter(x, x, c=x)
    sc1.set_alpha(alpha)
    plt.draw()
    assert_array_equal(sc0.get_facecolors()[:, -1], alpha)
    assert_array_equal(sc1.get_facecolors()[:, -1], alpha)
    # Without colormapping.
    fig, (ax0, ax1) = plt.subplots(2)
    sc0 = ax0.scatter(x, x, color=['r', 'g', 'b', 'c', 'm'], alpha=alpha)
    sc1 = ax1.scatter(x, x, color='r', alpha=alpha)
    plt.draw()
    assert_array_equal(sc0.get_facecolors()[:, -1], alpha)
    assert_array_equal(sc1.get_facecolors()[:, -1], alpha)
    # Without colormapping, and set alpha afterward.
    fig, (ax0, ax1) = plt.subplots(2)
    sc0 = ax0.scatter(x, x, color=['r', 'g', 'b', 'c', 'm'])
    sc0.set_alpha(alpha)
    sc1 = ax1.scatter(x, x, color='r')
    sc1.set_alpha(alpha)
    plt.draw()
    assert_array_equal(sc0.get_facecolors()[:, -1], alpha)
    assert_array_equal(sc1.get_facecolors()[:, -1], alpha)


def test_pathcollection_legend_elements():
    np.random.seed(19680801)
    x, y = np.random.rand(2, 10)
    y = np.random.rand(10)
    c = np.random.randint(0, 5, size=10)
    s = np.random.randint(10, 300, size=10)

    fig, ax = plt.subplots()
    sc = ax.scatter(x, y, c=c, s=s, cmap="jet", marker="o", linewidths=0)

    h, l = sc.legend_elements(fmt="{x:g}")
    assert len(h) == 5
    assert l == ["0", "1", "2", "3", "4"]
    colors = np.array([line.get_color() for line in h])
    colors2 = sc.cmap(np.arange(5)/4)
    assert_array_equal(colors, colors2)
    l1 = ax.legend(h, l, loc=1)

    h2, lab2 = sc.legend_elements(num=9)
    assert len(h2) == 9
    l2 = ax.legend(h2, lab2, loc=2)

    h, l = sc.legend_elements(prop="sizes", alpha=0.5, color="red")
    assert all(line.get_alpha() == 0.5 for line in h)
    assert all(line.get_markerfacecolor() == "red" for line in h)
    l3 = ax.legend(h, l, loc=4)

    h, l = sc.legend_elements(prop="sizes", num=4, fmt="{x:.2f}",
                              func=lambda x: 2*x)
    actsizes = [line.get_markersize() for line in h]
    labeledsizes = np.sqrt(np.array(l, float) / 2)
    assert_array_almost_equal(actsizes, labeledsizes)
    l4 = ax.legend(h, l, loc=3)

    loc = mpl.ticker.MaxNLocator(nbins=9, min_n_ticks=9-1,
                                 steps=[1, 2, 2.5, 3, 5, 6, 8, 10])
    h5, lab5 = sc.legend_elements(num=loc)
    assert len(h2) == len(h5)

    levels = [-1, 0, 55.4, 260]
    h6, lab6 = sc.legend_elements(num=levels, prop="sizes", fmt="{x:g}")
    assert [float(l) for l in lab6] == levels[2:]

    for l in [l1, l2, l3, l4]:
        ax.add_artist(l)

    fig.canvas.draw()


def test_EventCollection_nosort():
    # Check that EventCollection doesn't modify input in place
    arr = np.array([3, 2, 1, 10])
    coll = EventCollection(arr)
    np.testing.assert_array_equal(arr, np.array([3, 2, 1, 10]))


def test_collection_set_verts_array():
    verts = np.arange(80, dtype=np.double).reshape(10, 4, 2)
    col_arr = PolyCollection(verts)
    col_list = PolyCollection(list(verts))
    assert len(col_arr._paths) == len(col_list._paths)
    for ap, lp in zip(col_arr._paths, col_list._paths):
        assert np.array_equal(ap._vertices, lp._vertices)
        assert np.array_equal(ap._codes, lp._codes)

    verts_tuple = np.empty(10, dtype=object)
    verts_tuple[:] = [tuple(tuple(y) for y in x) for x in verts]
    col_arr_tuple = PolyCollection(verts_tuple)
    assert len(col_arr._paths) == len(col_arr_tuple._paths)
    for ap, atp in zip(col_arr._paths, col_arr_tuple._paths):
        assert np.array_equal(ap._vertices, atp._vertices)
        assert np.array_equal(ap._codes, atp._codes)


@check_figures_equal(extensions=["png"])
@pytest.mark.parametrize("kwargs", [{}, {"step": "pre"}])
def test_fill_between_poly_collection_set_data(fig_test, fig_ref, kwargs):
    t = np.linspace(0, 16)
    f1 = np.sin(t)
    f2 = f1 + 0.2

    fig_ref.subplots().fill_between(t, f1, f2, **kwargs)

    coll = fig_test.subplots().fill_between(t, -1, 1.2, **kwargs)
    coll.set_data(t, f1, f2)


@pytest.mark.parametrize(("t_direction", "f1", "shape", "where", "msg"), [
    ("z", None, None, None, r"t_direction must be 'x' or 'y', got 'z'"),
    ("x", None, (-1, 1), None, r"'x' is not 1-dimensional"),
    ("x", None, None, [False] * 3, r"where size \(3\) does not match 'x' size \(\d+\)"),
    ("y", [1, 2], None, None, r"'y' has size \d+, but 'x1' has an unequal size of \d+"),
])
def test_fill_between_poly_collection_raise(t_direction, f1, shape, where, msg):
    t = np.linspace(0, 16)
    f1 = np.sin(t) if f1 is None else np.asarray(f1)
    f2 = f1 + 0.2
    if shape:
        t = t.reshape(*shape)
    with pytest.raises(ValueError, match=msg):
        FillBetweenPolyCollection(t_direction, t, f1, f2, where=where)


def test_collection_set_array():
    vals = [*range(10)]

    # Test set_array with list
    c = Collection()
    c.set_array(vals)

    # Test set_array with wrong dtype
    with pytest.raises(TypeError, match="^Image data of dtype"):
        c.set_array("wrong_input")

    # Test if array kwarg is copied
    vals[5] = 45
    assert np.not_equal(vals, c.get_array()).any()


def test_blended_collection_autolim():
    f, ax = plt.subplots()

    # sample data to give initial data limits
    ax.plot([2, 3, 4], [0.4, 0.6, 0.5])
    np.testing.assert_allclose((ax.dataLim.xmin, ax.dataLim.xmax), (2, 4))
    data_ymin, data_ymax = ax.dataLim.ymin, ax.dataLim.ymax

    # LineCollection with vertical lines spanning the Axes vertical, using transAxes
    x = [1, 2, 3, 4, 5]
    vertical_lines = [np.array([[xi, 0], [xi, 1]]) for xi in x]
    trans = mtransforms.blended_transform_factory(ax.transData, ax.transAxes)
    ax.add_collection(LineCollection(vertical_lines, transform=trans))

    # check that the x data limits are updated to include the LineCollection
    np.testing.assert_allclose((ax.dataLim.xmin, ax.dataLim.xmax), (1, 5))
    # check that the y data limits are not updated (because they are not transData)
    np.testing.assert_allclose((ax.dataLim.ymin, ax.dataLim.ymax),
                               (data_ymin, data_ymax))


def test_singleton_autolim():
    fig, ax = plt.subplots()
    ax.scatter(0, 0)
    np.testing.assert_allclose(ax.get_ylim(), [-0.06, 0.06])
    np.testing.assert_allclose(ax.get_xlim(), [-0.06, 0.06])


@pytest.mark.parametrize("transform, expected", [
    ("transData", (-0.5, 3.5)),
    ("transAxes", (2.8, 3.2)),
])
def test_autolim_with_zeros(transform, expected):
    # 1) Test that a scatter at (0, 0) data coordinates contributes to
    # autoscaling even though any(offsets) would be False in that situation.
    # 2) Test that specifying transAxes for the transform does not contribute
    # to the autoscaling.
    fig, ax = plt.subplots()
    ax.scatter(0, 0, transform=getattr(ax, transform))
    ax.scatter(3, 3)
    np.testing.assert_allclose(ax.get_ylim(), expected)
    np.testing.assert_allclose(ax.get_xlim(), expected)


def test_quadmesh_set_array_validation(pcfunc):
    x = np.arange(11)
    y = np.arange(8)
    z = np.random.random((7, 10))
    fig, ax = plt.subplots()
    coll = getattr(ax, pcfunc)(x, y, z)

    with pytest.raises(ValueError, match=re.escape(
            "For X (11) and Y (8) with flat shading, A should have shape "
            "(7, 10, 3) or (7, 10, 4) or (7, 10) or (70,), not (10, 7)")):
        coll.set_array(z.reshape(10, 7))

    z = np.arange(54).reshape((6, 9))
    with pytest.raises(ValueError, match=re.escape(
            "For X (11) and Y (8) with flat shading, A should have shape "
            "(7, 10, 3) or (7, 10, 4) or (7, 10) or (70,), not (6, 9)")):
        coll.set_array(z)
    with pytest.raises(ValueError, match=re.escape(
            "For X (11) and Y (8) with flat shading, A should have shape "
            "(7, 10, 3) or (7, 10, 4) or (7, 10) or (70,), not (54,)")):
        coll.set_array(z.ravel())

    # RGB(A) tests
    z = np.ones((9, 6, 3))  # RGB with wrong X/Y dims
    with pytest.raises(ValueError, match=re.escape(
            "For X (11) and Y (8) with flat shading, A should have shape "
            "(7, 10, 3) or (7, 10, 4) or (7, 10) or (70,), not (9, 6, 3)")):
        coll.set_array(z)

    z = np.ones((9, 6, 4))  # RGBA with wrong X/Y dims
    with pytest.raises(ValueError, match=re.escape(
            "For X (11) and Y (8) with flat shading, A should have shape "
            "(7, 10, 3) or (7, 10, 4) or (7, 10) or (70,), not (9, 6, 4)")):
        coll.set_array(z)

    z = np.ones((7, 10, 2))  # Right X/Y dims, bad 3rd dim
    with pytest.raises(ValueError, match=re.escape(
            "For X (11) and Y (8) with flat shading, A should have shape "
            "(7, 10, 3) or (7, 10, 4) or (7, 10) or (70,), not (7, 10, 2)")):
        coll.set_array(z)

    x = np.arange(10)
    y = np.arange(7)
    z = np.random.random((7, 10))
    fig, ax = plt.subplots()
    coll = ax.pcolormesh(x, y, z, shading='gouraud')


def test_polyquadmesh_masked_vertices_array():
    xx, yy = np.meshgrid([0, 1, 2], [0, 1, 2, 3])
    # 2 x 3 mesh data
    zz = (xx*yy)[:-1, :-1]
    quadmesh = plt.pcolormesh(xx, yy, zz)
    quadmesh.update_scalarmappable()
    quadmesh_fc = quadmesh.get_facecolor()[1:, :]
    # Mask the origin vertex in x
    xx = np.ma.masked_where((xx == 0) & (yy == 0), xx)
    polymesh = plt.pcolor(xx, yy, zz)
    polymesh.update_scalarmappable()
    # One cell should be left out
    assert len(polymesh.get_paths()) == 5
    # Poly version should have the same facecolors as the end of the quadmesh
    assert_array_equal(quadmesh_fc, polymesh.get_facecolor())

    # Mask the origin vertex in y
    yy = np.ma.masked_where((xx == 0) & (yy == 0), yy)
    polymesh = plt.pcolor(xx, yy, zz)
    polymesh.update_scalarmappable()
    # One cell should be left out
    assert len(polymesh.get_paths()) == 5
    # Poly version should have the same facecolors as the end of the quadmesh
    assert_array_equal(quadmesh_fc, polymesh.get_facecolor())

    # Mask the origin cell data
    zz = np.ma.masked_where((xx[:-1, :-1] == 0) & (yy[:-1, :-1] == 0), zz)
    polymesh = plt.pcolor(zz)
    polymesh.update_scalarmappable()
    # One cell should be left out
    assert len(polymesh.get_paths()) == 5
    # Poly version should have the same facecolors as the end of the quadmesh
    assert_array_equal(quadmesh_fc, polymesh.get_facecolor())

    # We should also be able to call set_array with a new mask and get
    # updated polys
    # Remove mask, should add all polys back
    zz = np.arange(6).reshape((3, 2))
    polymesh.set_array(zz)
    polymesh.update_scalarmappable()
    assert len(polymesh.get_paths()) == 6
    # Add mask should remove polys
    zz = np.ma.masked_less(zz, 2)
    polymesh.set_array(zz)
    polymesh.update_scalarmappable()
    assert len(polymesh.get_paths()) == 4


def test_quadmesh_get_coordinates(pcfunc):
    x = [0, 1, 2]
    y = [2, 4, 6]
    z = np.ones(shape=(2, 2))
    xx, yy = np.meshgrid(x, y)
    coll = getattr(plt, pcfunc)(xx, yy, z)

    # shape (3, 3, 2)
    coords = np.stack([xx.T, yy.T]).T
    assert_array_equal(coll.get_coordinates(), coords)


def test_quadmesh_set_array():
    x = np.arange(4)
    y = np.arange(4)
    z = np.arange(9).reshape((3, 3))
    fig, ax = plt.subplots()
    coll = ax.pcolormesh(x, y, np.ones(z.shape))
    # Test that the collection is able to update with a 2d array
    coll.set_array(z)
    fig.canvas.draw()
    assert np.array_equal(coll.get_array(), z)

    # Check that pre-flattened arrays work too
    coll.set_array(np.ones(9))
    fig.canvas.draw()
    assert np.array_equal(coll.get_array(), np.ones(9))

    z = np.arange(16).reshape((4, 4))
    fig, ax = plt.subplots()
    coll = ax.pcolormesh(x, y, np.ones(z.shape), shading='gouraud')
    # Test that the collection is able to update with a 2d array
    coll.set_array(z)
    fig.canvas.draw()
    assert np.array_equal(coll.get_array(), z)

    # Check that pre-flattened arrays work too
    coll.set_array(np.ones(16))
    fig.canvas.draw()
    assert np.array_equal(coll.get_array(), np.ones(16))


def test_quadmesh_vmin_vmax(pcfunc):
    # test when vmin/vmax on the norm changes, the quadmesh gets updated
    fig, ax = plt.subplots()
    cmap = mpl.colormaps['plasma']
    norm = mpl.colors.Normalize(vmin=0, vmax=1)
    coll = getattr(ax, pcfunc)([[1]], cmap=cmap, norm=norm)
    fig.canvas.draw()
    assert np.array_equal(coll.get_facecolors()[0, :], cmap(norm(1)))

    # Change the vmin/vmax of the norm so that the color is from
    # the bottom of the colormap now
    norm.vmin, norm.vmax = 1, 2
    fig.canvas.draw()
    assert np.array_equal(coll.get_facecolors()[0, :], cmap(norm(1)))


def test_quadmesh_alpha_array(pcfunc):
    x = np.arange(4)
    y = np.arange(4)
    z = np.arange(9).reshape((3, 3))
    alpha = z / z.max()
    alpha_flat = alpha.ravel()
    # Provide 2-D alpha:
    fig, (ax0, ax1) = plt.subplots(2)
    coll1 = getattr(ax0, pcfunc)(x, y, z, alpha=alpha)
    coll2 = getattr(ax0, pcfunc)(x, y, z)
    coll2.set_alpha(alpha)
    plt.draw()
    assert_array_equal(coll1.get_facecolors()[:, -1], alpha_flat)
    assert_array_equal(coll2.get_facecolors()[:, -1], alpha_flat)
    # Or provide 1-D alpha:
    fig, (ax0, ax1) = plt.subplots(2)
    coll1 = getattr(ax0, pcfunc)(x, y, z, alpha=alpha)
    coll2 = getattr(ax1, pcfunc)(x, y, z)
    coll2.set_alpha(alpha)
    plt.draw()
    assert_array_equal(coll1.get_facecolors()[:, -1], alpha_flat)
    assert_array_equal(coll2.get_facecolors()[:, -1], alpha_flat)


def test_alpha_validation(pcfunc):
    # Most of the relevant testing is in test_artist and test_colors.
    fig, ax = plt.subplots()
    pc = getattr(ax, pcfunc)(np.arange(12).reshape((3, 4)))
    with pytest.raises(ValueError, match="^Data array shape"):
        pc.set_alpha([0.5, 0.6])
        pc.update_scalarmappable()


def test_legend_inverse_size_label_relationship():
    """
    Ensure legend markers scale appropriately when label and size are
    inversely related.
    Here label = 5 / size
    """

    np.random.seed(19680801)
    X = np.random.random(50)
    Y = np.random.random(50)
    C = 1 - np.random.random(50)
    S = 5 / C

    legend_sizes = [0.2, 0.4, 0.6, 0.8]
    fig, ax = plt.subplots()
    sc = ax.scatter(X, Y, s=S)
    handles, labels = sc.legend_elements(
      prop='sizes', num=legend_sizes, func=lambda s: 5 / s
    )

    # Convert markersize scale to 's' scale
    handle_sizes = [x.get_markersize() for x in handles]
    handle_sizes = [5 / x**2 for x in handle_sizes]

    assert_array_almost_equal(handle_sizes, legend_sizes, decimal=1)


@mpl.style.context('default')
def test_color_logic(pcfunc):
    pcfunc = getattr(plt, pcfunc)
    z = np.arange(12).reshape(3, 4)
    # Explicitly set an edgecolor.
    pc = pcfunc(z, edgecolors='red', facecolors='none')
    pc.update_scalarmappable()  # This is called in draw().
    # Define 2 reference "colors" here for multiple use.
    face_default = mcolors.to_rgba_array(pc._get_default_facecolor())
    mapped = pc.get_cmap()(pc.norm(z.ravel()))
    # GitHub issue #1302:
    assert mcolors.same_color(pc.get_edgecolor(), 'red')
    # Check setting attributes after initialization:
    pc = pcfunc(z)
    pc.set_facecolor('none')
    pc.set_edgecolor('red')
    pc.update_scalarmappable()
    assert mcolors.same_color(pc.get_facecolor(), 'none')
    assert mcolors.same_color(pc.get_edgecolor(), [[1, 0, 0, 1]])
    pc.set_alpha(0.5)
    pc.update_scalarmappable()
    assert mcolors.same_color(pc.get_edgecolor(), [[1, 0, 0, 0.5]])
    pc.set_alpha(None)  # restore default alpha
    pc.update_scalarmappable()
    assert mcolors.same_color(pc.get_edgecolor(), [[1, 0, 0, 1]])
    # Reset edgecolor to default.
    pc.set_edgecolor(None)
    pc.update_scalarmappable()
    assert np.array_equal(pc.get_edgecolor(), mapped)
    pc.set_facecolor(None)  # restore default for facecolor
    pc.update_scalarmappable()
    assert np.array_equal(pc.get_facecolor(), mapped)
    assert mcolors.same_color(pc.get_edgecolor(), 'none')
    # Turn off colormapping entirely:
    pc.set_array(None)
    pc.update_scalarmappable()
    assert mcolors.same_color(pc.get_edgecolor(), 'none')
    assert mcolors.same_color(pc.get_facecolor(), face_default)  # not mapped
    # Turn it back on by restoring the array (must be 1D!):
    pc.set_array(z)
    pc.update_scalarmappable()
    assert np.array_equal(pc.get_facecolor(), mapped)
    assert mcolors.same_color(pc.get_edgecolor(), 'none')
    # Give color via tuple rather than string.
    pc = pcfunc(z, edgecolors=(1, 0, 0), facecolors=(0, 1, 0))
    pc.update_scalarmappable()
    assert np.array_equal(pc.get_facecolor(), mapped)
    assert mcolors.same_color(pc.get_edgecolor(), [[1, 0, 0, 1]])
    # Provide an RGB array; mapping overrides it.
    pc = pcfunc(z, edgecolors=(1, 0, 0), facecolors=np.ones((12, 3)))
    pc.update_scalarmappable()
    assert np.array_equal(pc.get_facecolor(), mapped)
    assert mcolors.same_color(pc.get_edgecolor(), [[1, 0, 0, 1]])
    # Turn off the mapping.
    pc.set_array(None)
    pc.update_scalarmappable()
    assert mcolors.same_color(pc.get_facecolor(), np.ones((12, 3)))
    assert mcolors.same_color(pc.get_edgecolor(), [[1, 0, 0, 1]])
    # And an RGBA array.
    pc = pcfunc(z, edgecolors=(1, 0, 0), facecolors=np.ones((12, 4)))
    pc.update_scalarmappable()
    assert np.array_equal(pc.get_facecolor(), mapped)
    assert mcolors.same_color(pc.get_edgecolor(), [[1, 0, 0, 1]])
    # Turn off the mapping.
    pc.set_array(None)
    pc.update_scalarmappable()
    assert mcolors.same_color(pc.get_facecolor(), np.ones((12, 4)))
    assert mcolors.same_color(pc.get_edgecolor(), [[1, 0, 0, 1]])


def test_LineCollection_args():
    lc = LineCollection(None, linewidth=2.2, edgecolor='r',
                        zorder=3, facecolors=[0, 1, 0, 1])
    assert lc.get_linewidth()[0] == 2.2
    assert mcolors.same_color(lc.get_edgecolor(), 'r')
    assert lc.get_zorder() == 3
    assert mcolors.same_color(lc.get_facecolor(), [[0, 1, 0, 1]])
    # To avoid breaking mplot3d, LineCollection internally sets the facecolor
    # kwarg if it has not been specified.  Hence we need the following test
    # for LineCollection._set_default().
    lc = LineCollection(None, facecolor=None)
    assert mcolors.same_color(lc.get_facecolor(), 'none')


def test_array_dimensions(pcfunc):
    # Make sure we can set the 1D, 2D, and 3D array shapes
    z = np.arange(12).reshape(3, 4)
    pc = getattr(plt, pcfunc)(z)
    # 1D
    pc.set_array(z.ravel())
    pc.update_scalarmappable()
    # 2D
    pc.set_array(z)
    pc.update_scalarmappable()
    # 3D RGB is OK as well
    z = np.arange(36, dtype=np.uint8).reshape(3, 4, 3)
    pc.set_array(z)
    pc.update_scalarmappable()


def test_get_segments():
    segments = np.tile(np.linspace(0, 1, 256), (2, 1)).T
    lc = LineCollection([segments])

    readback, = lc.get_segments()
    # these should comeback un-changed!
    assert np.all(segments == readback)


def test_set_offsets_late():
    identity = mtransforms.IdentityTransform()
    sizes = [2]

    null = mcollections.CircleCollection(sizes=sizes)

    init = mcollections.CircleCollection(sizes=sizes, offsets=(10, 10))

    late = mcollections.CircleCollection(sizes=sizes)
    late.set_offsets((10, 10))

    # Bbox.__eq__ doesn't compare bounds
    null_bounds = null.get_datalim(identity).bounds
    init_bounds = init.get_datalim(identity).bounds
    late_bounds = late.get_datalim(identity).bounds

    # offsets and transform are applied when set after initialization
    assert null_bounds != init_bounds
    assert init_bounds == late_bounds


def test_set_offset_transform():
    skew = mtransforms.Affine2D().skew(2, 2)
    init = mcollections.Collection(offset_transform=skew)

    late = mcollections.Collection()
    late.set_offset_transform(skew)

    assert skew == init.get_offset_transform() == late.get_offset_transform()


def test_set_offset_units():
    # passing the offsets in initially (i.e. via scatter)
    # should yield the same results as `set_offsets`
    x = np.linspace(0, 10, 5)
    y = np.sin(x)
    d = x * np.timedelta64(24, 'h') + np.datetime64('2021-11-29')

    sc = plt.scatter(d, y)
    off0 = sc.get_offsets()
    sc.set_offsets(list(zip(d, y)))
    np.testing.assert_allclose(off0, sc.get_offsets())

    # try the other way around
    fig, ax = plt.subplots()
    sc = ax.scatter(y, d)
    off0 = sc.get_offsets()
    sc.set_offsets(list(zip(y, d)))
    np.testing.assert_allclose(off0, sc.get_offsets())


@image_comparison(baseline_images=["test_check_masked_offsets"],
                  extensions=["png"], remove_text=True, style="mpl20")
def test_check_masked_offsets():
    # Check if masked data is respected by scatter
    # Ref: Issue #24545
    unmasked_x = [
        datetime(2022, 12, 15, 4, 49, 52),
        datetime(2022, 12, 15, 4, 49, 53),
        datetime(2022, 12, 15, 4, 49, 54),
        datetime(2022, 12, 15, 4, 49, 55),
        datetime(2022, 12, 15, 4, 49, 56),
    ]

    masked_y = np.ma.array([1, 2, 3, 4, 5], mask=[0, 1, 1, 0, 0])

    fig, ax = plt.subplots()
    ax.scatter(unmasked_x, masked_y)


@check_figures_equal(extensions=["png"])
def test_masked_set_offsets(fig_ref, fig_test):
    x = np.ma.array([1, 2, 3, 4, 5], mask=[0, 0, 1, 1, 0])
    y = np.arange(1, 6)

    ax_test = fig_test.add_subplot()
    scat = ax_test.scatter(x, y)
    scat.set_offsets(np.ma.column_stack([x, y]))
    ax_test.set_xticks([])
    ax_test.set_yticks([])

    ax_ref = fig_ref.add_subplot()
    ax_ref.scatter([1, 2, 5], [1, 2, 5])
    ax_ref.set_xticks([])
    ax_ref.set_yticks([])


def test_check_offsets_dtype():
    # Check that setting offsets doesn't change dtype
    x = np.ma.array([1, 2, 3, 4, 5], mask=[0, 0, 1, 1, 0])
    y = np.arange(1, 6)

    fig, ax = plt.subplots()
    scat = ax.scatter(x, y)
    masked_offsets = np.ma.column_stack([x, y])
    scat.set_offsets(masked_offsets)
    assert isinstance(scat.get_offsets(), type(masked_offsets))

    unmasked_offsets = np.column_stack([x, y])
    scat.set_offsets(unmasked_offsets)
    assert isinstance(scat.get_offsets(), type(unmasked_offsets))


@pytest.mark.parametrize('gapcolor', ['orange', ['r', 'k']])
@check_figures_equal(extensions=['png'])
def test_striped_lines(fig_test, fig_ref, gapcolor):
    ax_test = fig_test.add_subplot(111)
    ax_ref = fig_ref.add_subplot(111)

    for ax in [ax_test, ax_ref]:
        ax.set_xlim(0, 6)
        ax.set_ylim(0, 1)

    x = range(1, 6)
    linestyles = [':', '-', '--']

    ax_test.vlines(x, 0, 1, linewidth=20, linestyle=linestyles, gapcolor=gapcolor,
                   alpha=0.5)

    if isinstance(gapcolor, str):
        gapcolor = [gapcolor]

    for x, gcol, ls in zip(x, itertools.cycle(gapcolor),
                           itertools.cycle(linestyles)):
        ax_ref.axvline(x, 0, 1, linewidth=20, linestyle=ls, gapcolor=gcol, alpha=0.5)


@check_figures_equal(extensions=['png', 'pdf', 'svg', 'eps'])
def test_hatch_linewidth(fig_test, fig_ref):
    ax_test = fig_test.add_subplot()
    ax_ref = fig_ref.add_subplot()

    lw = 2.0

    polygons = [
        [(0.1, 0.1), (0.1, 0.4), (0.4, 0.4), (0.4, 0.1)],
        [(0.6, 0.6), (0.6, 0.9), (0.9, 0.9), (0.9, 0.6)],
    ]
    ref = PolyCollection(polygons, hatch="x")
    ref.set_hatch_linewidth(lw)

    with mpl.rc_context({"hatch.linewidth": lw}):
        test = PolyCollection(polygons, hatch="x")

    ax_ref.add_collection(ref)
    ax_test.add_collection(test)

    assert test.get_hatch_linewidth() == ref.get_hatch_linewidth() == lw
