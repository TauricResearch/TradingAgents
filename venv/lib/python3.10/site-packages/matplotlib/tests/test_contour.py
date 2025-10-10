import datetime
import platform
import re
from unittest import mock

import contourpy
import numpy as np
from numpy.testing import assert_array_almost_equal, assert_array_almost_equal_nulp
import matplotlib as mpl
from matplotlib import pyplot as plt, rc_context, ticker
from matplotlib.colors import LogNorm, same_color
import matplotlib.patches as mpatches
from matplotlib.testing.decorators import check_figures_equal, image_comparison
import pytest


def test_contour_shape_1d_valid():

    x = np.arange(10)
    y = np.arange(9)
    z = np.random.random((9, 10))

    fig, ax = plt.subplots()
    ax.contour(x, y, z)


def test_contour_shape_2d_valid():

    x = np.arange(10)
    y = np.arange(9)
    xg, yg = np.meshgrid(x, y)
    z = np.random.random((9, 10))

    fig, ax = plt.subplots()
    ax.contour(xg, yg, z)


@pytest.mark.parametrize("args, message", [
    ((np.arange(9), np.arange(9), np.empty((9, 10))),
     'Length of x (9) must match number of columns in z (10)'),
    ((np.arange(10), np.arange(10), np.empty((9, 10))),
     'Length of y (10) must match number of rows in z (9)'),
    ((np.empty((10, 10)), np.arange(10), np.empty((9, 10))),
     'Number of dimensions of x (2) and y (1) do not match'),
    ((np.arange(10), np.empty((10, 10)), np.empty((9, 10))),
     'Number of dimensions of x (1) and y (2) do not match'),
    ((np.empty((9, 9)), np.empty((9, 10)), np.empty((9, 10))),
     'Shapes of x (9, 9) and z (9, 10) do not match'),
    ((np.empty((9, 10)), np.empty((9, 9)), np.empty((9, 10))),
     'Shapes of y (9, 9) and z (9, 10) do not match'),
    ((np.empty((3, 3, 3)), np.empty((3, 3, 3)), np.empty((9, 10))),
     'Inputs x and y must be 1D or 2D, not 3D'),
    ((np.empty((3, 3, 3)), np.empty((3, 3, 3)), np.empty((3, 3, 3))),
     'Input z must be 2D, not 3D'),
    (([[0]],),  # github issue 8197
     'Input z must be at least a (2, 2) shaped array, but has shape (1, 1)'),
    (([0], [0], [[0]]),
     'Input z must be at least a (2, 2) shaped array, but has shape (1, 1)'),
])
def test_contour_shape_error(args, message):
    fig, ax = plt.subplots()
    with pytest.raises(TypeError, match=re.escape(message)):
        ax.contour(*args)


def test_contour_no_valid_levels():
    fig, ax = plt.subplots()
    # no warning for empty levels.
    ax.contour(np.random.rand(9, 9), levels=[])
    # no warning if levels is given and is not within the range of z.
    cs = ax.contour(np.arange(81).reshape((9, 9)), levels=[100])
    # ... and if fmt is given.
    ax.clabel(cs, fmt={100: '%1.2f'})
    # no warning if z is uniform.
    ax.contour(np.ones((9, 9)))


def test_contour_Nlevels():
    # A scalar levels arg or kwarg should trigger auto level generation.
    # https://github.com/matplotlib/matplotlib/issues/11913
    z = np.arange(12).reshape((3, 4))
    fig, ax = plt.subplots()
    cs1 = ax.contour(z, 5)
    assert len(cs1.levels) > 1
    cs2 = ax.contour(z, levels=5)
    assert (cs1.levels == cs2.levels).all()


@check_figures_equal(extensions=['png'])
def test_contour_set_paths(fig_test, fig_ref):
    cs_test = fig_test.subplots().contour([[0, 1], [1, 2]])
    cs_ref = fig_ref.subplots().contour([[1, 0], [2, 1]])

    cs_test.set_paths(cs_ref.get_paths())


@image_comparison(['contour_manual_labels'], remove_text=True, style='mpl20', tol=0.26)
def test_contour_manual_labels():
    x, y = np.meshgrid(np.arange(0, 10), np.arange(0, 10))
    z = np.max(np.dstack([abs(x), abs(y)]), 2)

    plt.figure(figsize=(6, 2), dpi=200)
    cs = plt.contour(x, y, z)

    pts = np.array([(1.0, 3.0), (1.0, 4.4), (1.0, 6.0)])
    plt.clabel(cs, manual=pts)
    pts = np.array([(2.0, 3.0), (2.0, 4.4), (2.0, 6.0)])
    plt.clabel(cs, manual=pts, fontsize='small', colors=('r', 'g'))


def test_contour_manual_moveto():
    x = np.linspace(-10, 10)
    y = np.linspace(-10, 10)

    X, Y = np.meshgrid(x, y)

    Z = X**2 * 1 / Y**2 - 1

    contours = plt.contour(X, Y, Z, levels=[0, 100])

    # This point lies on the `MOVETO` line for the 100 contour
    # but is actually closest to the 0 contour
    point = (1.3, 1)
    clabels = plt.clabel(contours, manual=[point])

    # Ensure that the 0 contour was chosen, not the 100 contour
    assert clabels[0].get_text() == "0"


@image_comparison(['contour_disconnected_segments'],
                  remove_text=True, style='mpl20', extensions=['png'])
def test_contour_label_with_disconnected_segments():
    x, y = np.mgrid[-1:1:21j, -1:1:21j]
    z = 1 / np.sqrt(0.01 + (x + 0.3) ** 2 + y ** 2)
    z += 1 / np.sqrt(0.01 + (x - 0.3) ** 2 + y ** 2)

    plt.figure()
    cs = plt.contour(x, y, z, levels=[7])
    cs.clabel(manual=[(0.2, 0.1)])


@image_comparison(['contour_manual_colors_and_levels.png'], remove_text=True,
                  tol=0 if platform.machine() == 'x86_64' else 0.018)
def test_given_colors_levels_and_extends():
    # Remove this line when this test image is regenerated.
    plt.rcParams['pcolormesh.snap'] = False

    _, axs = plt.subplots(2, 4)

    data = np.arange(12).reshape(3, 4)

    colors = ['red', 'yellow', 'pink', 'blue', 'black']
    levels = [2, 4, 8, 10]

    for i, ax in enumerate(axs.flat):
        filled = i % 2 == 0.
        extend = ['neither', 'min', 'max', 'both'][i // 2]

        if filled:
            # If filled, we have 3 colors with no extension,
            # 4 colors with one extension, and 5 colors with both extensions
            first_color = 1 if extend in ['max', 'neither'] else None
            last_color = -1 if extend in ['min', 'neither'] else None
            c = ax.contourf(data, colors=colors[first_color:last_color],
                            levels=levels, extend=extend)
        else:
            # If not filled, we have 4 levels and 4 colors
            c = ax.contour(data, colors=colors[:-1],
                           levels=levels, extend=extend)

        plt.colorbar(c, ax=ax)


@image_comparison(['contourf_hatch_colors'],
                  remove_text=True, style='mpl20', extensions=['png'])
def test_hatch_colors():
    fig, ax = plt.subplots()
    cf = ax.contourf([[0, 1], [1, 2]], hatches=['-', '/', '\\', '//'], cmap='gray')
    cf.set_edgecolors(["blue", "grey", "yellow", "red"])


@pytest.mark.parametrize('color, extend', [('darkred', 'neither'),
                                           ('darkred', 'both'),
                                           (('r', 0.5), 'neither'),
                                           ((0.1, 0.2, 0.5, 0.3), 'neither')])
def test_single_color_and_extend(color, extend):
    z = [[0, 1], [1, 2]]

    _, ax = plt.subplots()
    levels = [0.5, 0.75, 1, 1.25, 1.5]
    cs = ax.contour(z, levels=levels, colors=color, extend=extend)
    for c in cs.get_edgecolors():
        assert same_color(c, color)


@image_comparison(['contour_log_locator.svg'], style='mpl20', remove_text=False)
def test_log_locator_levels():

    fig, ax = plt.subplots()

    N = 100
    x = np.linspace(-3.0, 3.0, N)
    y = np.linspace(-2.0, 2.0, N)

    X, Y = np.meshgrid(x, y)

    Z1 = np.exp(-X**2 - Y**2)
    Z2 = np.exp(-(X * 10)**2 - (Y * 10)**2)
    data = Z1 + 50 * Z2

    c = ax.contourf(data, locator=ticker.LogLocator())
    assert_array_almost_equal(c.levels, np.power(10.0, np.arange(-6, 3)))
    cb = fig.colorbar(c, ax=ax)
    assert_array_almost_equal(cb.ax.get_yticks(), c.levels)


@image_comparison(['contour_datetime_axis.png'], style='mpl20')
def test_contour_datetime_axis():
    fig = plt.figure()
    fig.subplots_adjust(hspace=0.4, top=0.98, bottom=.15)
    base = datetime.datetime(2013, 1, 1)
    x = np.array([base + datetime.timedelta(days=d) for d in range(20)])
    y = np.arange(20)
    z1, z2 = np.meshgrid(np.arange(20), np.arange(20))
    z = z1 * z2
    plt.subplot(221)
    plt.contour(x, y, z)
    plt.subplot(222)
    plt.contourf(x, y, z)
    x = np.repeat(x[np.newaxis], 20, axis=0)
    y = np.repeat(y[:, np.newaxis], 20, axis=1)
    plt.subplot(223)
    plt.contour(x, y, z)
    plt.subplot(224)
    plt.contourf(x, y, z)
    for ax in fig.get_axes():
        for label in ax.get_xticklabels():
            label.set_ha('right')
            label.set_rotation(30)


@image_comparison(['contour_test_label_transforms.png'],
                  remove_text=True, style='mpl20', tol=1.1)
def test_labels():
    # Adapted from pylab_examples example code: contour_demo.py
    # see issues #2475, #2843, and #2818 for explanation
    delta = 0.025
    x = np.arange(-3.0, 3.0, delta)
    y = np.arange(-2.0, 2.0, delta)
    X, Y = np.meshgrid(x, y)
    Z1 = np.exp(-(X**2 + Y**2) / 2) / (2 * np.pi)
    Z2 = (np.exp(-(((X - 1) / 1.5)**2 + ((Y - 1) / 0.5)**2) / 2) /
          (2 * np.pi * 0.5 * 1.5))

    # difference of Gaussians
    Z = 10.0 * (Z2 - Z1)

    fig, ax = plt.subplots(1, 1)
    CS = ax.contour(X, Y, Z)
    disp_units = [(216, 177), (359, 290), (521, 406)]
    data_units = [(-2, .5), (0, -1.5), (2.8, 1)]

    CS.clabel()

    for x, y in data_units:
        CS.add_label_near(x, y, inline=True, transform=None)

    for x, y in disp_units:
        CS.add_label_near(x, y, inline=True, transform=False)


def test_label_contour_start():
    # Set up data and figure/axes that result in automatic labelling adding the
    # label to the start of a contour

    _, ax = plt.subplots(dpi=100)
    lats = lons = np.linspace(-np.pi / 2, np.pi / 2, 50)
    lons, lats = np.meshgrid(lons, lats)
    wave = 0.75 * (np.sin(2 * lats) ** 8) * np.cos(4 * lons)
    mean = 0.5 * np.cos(2 * lats) * ((np.sin(2 * lats)) ** 2 + 2)
    data = wave + mean

    cs = ax.contour(lons, lats, data)

    with mock.patch.object(
            cs, '_split_path_and_get_label_rotation',
            wraps=cs._split_path_and_get_label_rotation) as mocked_splitter:
        # Smoke test that we can add the labels
        cs.clabel(fontsize=9)

    # Verify at least one label was added to the start of a contour.  I.e. the
    # splitting method was called with idx=0 at least once.
    idxs = [cargs[0][1] for cargs in mocked_splitter.call_args_list]
    assert 0 in idxs


@image_comparison(['contour_corner_mask_False.png', 'contour_corner_mask_True.png'],
                  remove_text=True, tol=1.88)
def test_corner_mask():
    n = 60
    mask_level = 0.95
    noise_amp = 1.0
    np.random.seed([1])
    x, y = np.meshgrid(np.linspace(0, 2.0, n), np.linspace(0, 2.0, n))
    z = np.cos(7*x)*np.sin(8*y) + noise_amp*np.random.rand(n, n)
    mask = np.random.rand(n, n) >= mask_level
    z = np.ma.array(z, mask=mask)

    for corner_mask in [False, True]:
        plt.figure()
        plt.contourf(z, corner_mask=corner_mask)


def test_contourf_decreasing_levels():
    # github issue 5477.
    z = [[0.1, 0.3], [0.5, 0.7]]
    plt.figure()
    with pytest.raises(ValueError):
        plt.contourf(z, [1.0, 0.0])


def test_contourf_symmetric_locator():
    # github issue 7271
    z = np.arange(12).reshape((3, 4))
    locator = plt.MaxNLocator(nbins=4, symmetric=True)
    cs = plt.contourf(z, locator=locator)
    assert_array_almost_equal(cs.levels, np.linspace(-12, 12, 5))


def test_circular_contour_warning():
    # Check that almost circular contours don't throw a warning
    x, y = np.meshgrid(np.linspace(-2, 2, 4), np.linspace(-2, 2, 4))
    r = np.hypot(x, y)
    plt.figure()
    cs = plt.contour(x, y, r)
    plt.clabel(cs)


@pytest.mark.parametrize("use_clabeltext, contour_zorder, clabel_zorder",
                         [(True, 123, 1234), (False, 123, 1234),
                          (True, 123, None), (False, 123, None)])
def test_clabel_zorder(use_clabeltext, contour_zorder, clabel_zorder):
    x, y = np.meshgrid(np.arange(0, 10), np.arange(0, 10))
    z = np.max(np.dstack([abs(x), abs(y)]), 2)

    fig, (ax1, ax2) = plt.subplots(ncols=2)
    cs = ax1.contour(x, y, z, zorder=contour_zorder)
    cs_filled = ax2.contourf(x, y, z, zorder=contour_zorder)
    clabels1 = cs.clabel(zorder=clabel_zorder, use_clabeltext=use_clabeltext)
    clabels2 = cs_filled.clabel(zorder=clabel_zorder,
                                use_clabeltext=use_clabeltext)

    if clabel_zorder is None:
        expected_clabel_zorder = 2+contour_zorder
    else:
        expected_clabel_zorder = clabel_zorder

    for clabel in clabels1:
        assert clabel.get_zorder() == expected_clabel_zorder
    for clabel in clabels2:
        assert clabel.get_zorder() == expected_clabel_zorder


def test_clabel_with_large_spacing():
    # When the inline spacing is large relative to the contour, it may cause the
    # entire contour to be removed. In current implementation, one line segment is
    # retained between the identified points.
    # This behavior may be worth reconsidering, but check to be sure we do not produce
    # an invalid path, which results in an error at clabel call time.
    # see gh-27045 for more information
    x = y = np.arange(-3.0, 3.01, 0.05)
    X, Y = np.meshgrid(x, y)
    Z = np.exp(-X**2 - Y**2)

    fig, ax = plt.subplots()
    contourset = ax.contour(X, Y, Z, levels=[0.01, 0.2, .5, .8])
    ax.clabel(contourset, inline_spacing=100)


# tol because ticks happen to fall on pixel boundaries so small
# floating point changes in tick location flip which pixel gets
# the tick.
@image_comparison(['contour_log_extension.png'],
                  remove_text=True, style='mpl20',
                  tol=1.444)
def test_contourf_log_extension():
    # Remove this line when this test image is regenerated.
    plt.rcParams['pcolormesh.snap'] = False

    # Test that contourf with lognorm is extended correctly
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(10, 5))
    fig.subplots_adjust(left=0.05, right=0.95)

    # make data set with large range e.g. between 1e-8 and 1e10
    data_exp = np.linspace(-7.5, 9.5, 1200)
    data = np.power(10, data_exp).reshape(30, 40)
    # make manual levels e.g. between 1e-4 and 1e-6
    levels_exp = np.arange(-4., 7.)
    levels = np.power(10., levels_exp)

    # original data
    c1 = ax1.contourf(data,
                      norm=LogNorm(vmin=data.min(), vmax=data.max()))
    # just show data in levels
    c2 = ax2.contourf(data, levels=levels,
                      norm=LogNorm(vmin=levels.min(), vmax=levels.max()),
                      extend='neither')
    # extend data from levels
    c3 = ax3.contourf(data, levels=levels,
                      norm=LogNorm(vmin=levels.min(), vmax=levels.max()),
                      extend='both')
    cb = plt.colorbar(c1, ax=ax1)
    assert cb.ax.get_ylim() == (1e-8, 1e10)
    cb = plt.colorbar(c2, ax=ax2)
    assert_array_almost_equal_nulp(cb.ax.get_ylim(), np.array((1e-4, 1e6)))
    cb = plt.colorbar(c3, ax=ax3)


@image_comparison(['contour_addlines.png'], remove_text=True, style='mpl20',
                  tol=0.03 if platform.machine() == 'x86_64' else 0.15)
# tolerance is because image changed minutely when tick finding on
# colorbars was cleaned up...
def test_contour_addlines():
    # Remove this line when this test image is regenerated.
    plt.rcParams['pcolormesh.snap'] = False

    fig, ax = plt.subplots()
    np.random.seed(19680812)
    X = np.random.rand(10, 10)*10000
    pcm = ax.pcolormesh(X)
    # add 1000 to make colors visible...
    cont = ax.contour(X+1000)
    cb = fig.colorbar(pcm)
    cb.add_lines(cont)
    assert_array_almost_equal(cb.ax.get_ylim(), [114.3091, 9972.30735], 3)


@image_comparison(baseline_images=['contour_uneven'],
                  extensions=['png'], remove_text=True, style='mpl20')
def test_contour_uneven():
    # Remove this line when this test image is regenerated.
    plt.rcParams['pcolormesh.snap'] = False

    z = np.arange(24).reshape(4, 6)
    fig, axs = plt.subplots(1, 2)
    ax = axs[0]
    cs = ax.contourf(z, levels=[2, 4, 6, 10, 20])
    fig.colorbar(cs, ax=ax, spacing='proportional')
    ax = axs[1]
    cs = ax.contourf(z, levels=[2, 4, 6, 10, 20])
    fig.colorbar(cs, ax=ax, spacing='uniform')


@pytest.mark.parametrize(
    "rc_lines_linewidth, rc_contour_linewidth, call_linewidths, expected", [
        (1.23, None, None, 1.23),
        (1.23, 4.24, None, 4.24),
        (1.23, 4.24, 5.02, 5.02)
        ])
def test_contour_linewidth(
        rc_lines_linewidth, rc_contour_linewidth, call_linewidths, expected):

    with rc_context(rc={"lines.linewidth": rc_lines_linewidth,
                        "contour.linewidth": rc_contour_linewidth}):
        fig, ax = plt.subplots()
        X = np.arange(4*3).reshape(4, 3)
        cs = ax.contour(X, linewidths=call_linewidths)
        assert cs.get_linewidths()[0] == expected


@pytest.mark.backend("pdf")
def test_label_nonagg():
    # This should not crash even if the canvas doesn't have a get_renderer().
    plt.clabel(plt.contour([[1, 2], [3, 4]]))


@image_comparison(baseline_images=['contour_closed_line_loop'],
                  extensions=['png'], remove_text=True)
def test_contour_closed_line_loop():
    # github issue 19568.
    z = [[0, 0, 0], [0, 2, 0], [0, 0, 0], [2, 1, 2]]

    fig, ax = plt.subplots(figsize=(2, 2))
    ax.contour(z, [0.5], linewidths=[20], alpha=0.7)
    ax.set_xlim(-0.1, 2.1)
    ax.set_ylim(-0.1, 3.1)


def test_quadcontourset_reuse():
    # If QuadContourSet returned from one contour(f) call is passed as first
    # argument to another the underlying C++ contour generator will be reused.
    x, y = np.meshgrid([0.0, 1.0], [0.0, 1.0])
    z = x + y
    fig, ax = plt.subplots()
    qcs1 = ax.contourf(x, y, z)
    qcs2 = ax.contour(x, y, z)
    assert qcs2._contour_generator != qcs1._contour_generator
    qcs3 = ax.contour(qcs1, z)
    assert qcs3._contour_generator == qcs1._contour_generator


@image_comparison(baseline_images=['contour_manual'],
                  extensions=['png'], remove_text=True, tol=0.89)
def test_contour_manual():
    # Manually specifying contour lines/polygons to plot.
    from matplotlib.contour import ContourSet

    fig, ax = plt.subplots(figsize=(4, 4))
    cmap = 'viridis'

    # Segments only (no 'kind' codes).
    lines0 = [[[2, 0], [1, 2], [1, 3]]]  # Single line.
    lines1 = [[[3, 0], [3, 2]], [[3, 3], [3, 4]]]  # Two lines.
    filled01 = [[[0, 0], [0, 4], [1, 3], [1, 2], [2, 0]]]
    filled12 = [[[2, 0], [3, 0], [3, 2], [1, 3], [1, 2]],  # Two polygons.
                [[1, 4], [3, 4], [3, 3]]]
    ContourSet(ax, [0, 1, 2], [filled01, filled12], filled=True, cmap=cmap)
    ContourSet(ax, [1, 2], [lines0, lines1], linewidths=3, colors=['r', 'k'])

    # Segments and kind codes (1 = MOVETO, 2 = LINETO, 79 = CLOSEPOLY).
    segs = [[[4, 0], [7, 0], [7, 3], [4, 3], [4, 0],
             [5, 1], [5, 2], [6, 2], [6, 1], [5, 1]]]
    kinds = [[1, 2, 2, 2, 79, 1, 2, 2, 2, 79]]  # Polygon containing hole.
    ContourSet(ax, [2, 3], [segs], [kinds], filled=True, cmap=cmap)
    ContourSet(ax, [2], [segs], [kinds], colors='k', linewidths=3)


@image_comparison(baseline_images=['contour_line_start_on_corner_edge'],
                  extensions=['png'], remove_text=True)
def test_contour_line_start_on_corner_edge():
    fig, ax = plt.subplots(figsize=(6, 5))

    x, y = np.meshgrid([0, 1, 2, 3, 4], [0, 1, 2])
    z = 1.2 - (x - 2)**2 + (y - 1)**2
    mask = np.zeros_like(z, dtype=bool)
    mask[1, 1] = mask[1, 3] = True
    z = np.ma.array(z, mask=mask)

    filled = ax.contourf(x, y, z, corner_mask=True)
    cbar = fig.colorbar(filled)
    lines = ax.contour(x, y, z, corner_mask=True, colors='k')
    cbar.add_lines(lines)


def test_find_nearest_contour():
    xy = np.indices((15, 15))
    img = np.exp(-np.pi * (np.sum((xy - 5)**2, 0)/5.**2))
    cs = plt.contour(img, 10)

    nearest_contour = cs.find_nearest_contour(1, 1, pixel=False)
    expected_nearest = (1, 0, 33, 1.965966, 1.965966, 1.866183)
    assert_array_almost_equal(nearest_contour, expected_nearest)

    nearest_contour = cs.find_nearest_contour(8, 1, pixel=False)
    expected_nearest = (1, 0, 5, 7.550173, 1.587542, 0.547550)
    assert_array_almost_equal(nearest_contour, expected_nearest)

    nearest_contour = cs.find_nearest_contour(2, 5, pixel=False)
    expected_nearest = (3, 0, 21, 1.884384, 5.023335, 0.013911)
    assert_array_almost_equal(nearest_contour, expected_nearest)

    nearest_contour = cs.find_nearest_contour(2, 5, indices=(5, 7), pixel=False)
    expected_nearest = (5, 0, 16, 2.628202, 5.0, 0.394638)
    assert_array_almost_equal(nearest_contour, expected_nearest)


def test_find_nearest_contour_no_filled():
    xy = np.indices((15, 15))
    img = np.exp(-np.pi * (np.sum((xy - 5)**2, 0)/5.**2))
    cs = plt.contourf(img, 10)

    with pytest.raises(ValueError, match="Method does not support filled contours"):
        cs.find_nearest_contour(1, 1, pixel=False)

    with pytest.raises(ValueError, match="Method does not support filled contours"):
        cs.find_nearest_contour(1, 10, indices=(5, 7), pixel=False)

    with pytest.raises(ValueError, match="Method does not support filled contours"):
        cs.find_nearest_contour(2, 5, indices=(2, 7), pixel=True)


@mpl.style.context("default")
def test_contour_autolabel_beyond_powerlimits():
    ax = plt.figure().add_subplot()
    cs = plt.contour(np.geomspace(1e-6, 1e-4, 100).reshape(10, 10),
                     levels=[.25e-5, 1e-5, 4e-5])
    ax.clabel(cs)
    # Currently, the exponent is missing, but that may be fixed in the future.
    assert {text.get_text() for text in ax.texts} == {"0.25", "1.00", "4.00"}


def test_contourf_legend_elements():
    from matplotlib.patches import Rectangle
    x = np.arange(1, 10)
    y = x.reshape(-1, 1)
    h = x * y

    cs = plt.contourf(h, levels=[10, 30, 50],
                      colors=['#FFFF00', '#FF00FF', '#00FFFF'],
                      extend='both')
    cs.cmap.set_over('red')
    cs.cmap.set_under('blue')
    cs.changed()
    artists, labels = cs.legend_elements()
    assert labels == ['$x \\leq -1e+250s$',
                      '$10.0 < x \\leq 30.0$',
                      '$30.0 < x \\leq 50.0$',
                      '$x > 1e+250s$']
    expected_colors = ('blue', '#FFFF00', '#FF00FF', 'red')
    assert all(isinstance(a, Rectangle) for a in artists)
    assert all(same_color(a.get_facecolor(), c)
               for a, c in zip(artists, expected_colors))


def test_contour_legend_elements():
    x = np.arange(1, 10)
    y = x.reshape(-1, 1)
    h = x * y

    colors = ['blue', '#00FF00', 'red']
    cs = plt.contour(h, levels=[10, 30, 50],
                     colors=colors,
                     extend='both')
    artists, labels = cs.legend_elements()
    assert labels == ['$x = 10.0$', '$x = 30.0$', '$x = 50.0$']
    assert all(isinstance(a, mpl.lines.Line2D) for a in artists)
    assert all(same_color(a.get_color(), c)
               for a, c in zip(artists, colors))


@pytest.mark.parametrize(
    "algorithm, klass",
    [('mpl2005', contourpy.Mpl2005ContourGenerator),
     ('mpl2014', contourpy.Mpl2014ContourGenerator),
     ('serial', contourpy.SerialContourGenerator),
     ('threaded', contourpy.ThreadedContourGenerator),
     ('invalid', None)])
def test_algorithm_name(algorithm, klass):
    z = np.array([[1.0, 2.0], [3.0, 4.0]])
    if klass is not None:
        cs = plt.contourf(z, algorithm=algorithm)
        assert isinstance(cs._contour_generator, klass)
    else:
        with pytest.raises(ValueError):
            plt.contourf(z, algorithm=algorithm)


@pytest.mark.parametrize(
    "algorithm", ['mpl2005', 'mpl2014', 'serial', 'threaded'])
def test_algorithm_supports_corner_mask(algorithm):
    z = np.array([[1.0, 2.0], [3.0, 4.0]])

    # All algorithms support corner_mask=False
    plt.contourf(z, algorithm=algorithm, corner_mask=False)

    # Only some algorithms support corner_mask=True
    if algorithm != 'mpl2005':
        plt.contourf(z, algorithm=algorithm, corner_mask=True)
    else:
        with pytest.raises(ValueError):
            plt.contourf(z, algorithm=algorithm, corner_mask=True)


@image_comparison(baseline_images=['contour_all_algorithms'],
                  extensions=['png'], remove_text=True, tol=0.06)
def test_all_algorithms():
    algorithms = ['mpl2005', 'mpl2014', 'serial', 'threaded']

    rng = np.random.default_rng(2981)
    x, y = np.meshgrid(np.linspace(0.0, 1.0, 10), np.linspace(0.0, 1.0, 6))
    z = np.sin(15*x)*np.cos(10*y) + rng.normal(scale=0.5, size=(6, 10))
    mask = np.zeros_like(z, dtype=bool)
    mask[3, 7] = True
    z = np.ma.array(z, mask=mask)

    _, axs = plt.subplots(2, 2)
    for ax, algorithm in zip(axs.ravel(), algorithms):
        ax.contourf(x, y, z, algorithm=algorithm)
        ax.contour(x, y, z, algorithm=algorithm, colors='k')
        ax.set_title(algorithm)


def test_subfigure_clabel():
    # Smoke test for gh#23173
    delta = 0.025
    x = np.arange(-3.0, 3.0, delta)
    y = np.arange(-2.0, 2.0, delta)
    X, Y = np.meshgrid(x, y)
    Z1 = np.exp(-(X**2) - Y**2)
    Z2 = np.exp(-((X - 1) ** 2) - (Y - 1) ** 2)
    Z = (Z1 - Z2) * 2

    fig = plt.figure()
    figs = fig.subfigures(nrows=1, ncols=2)

    for f in figs:
        ax = f.subplots()
        CS = ax.contour(X, Y, Z)
        ax.clabel(CS, inline=True, fontsize=10)
        ax.set_title("Simplest default with labels")


@pytest.mark.parametrize(
    "style", ['solid', 'dashed', 'dashdot', 'dotted'])
def test_linestyles(style):
    delta = 0.025
    x = np.arange(-3.0, 3.0, delta)
    y = np.arange(-2.0, 2.0, delta)
    X, Y = np.meshgrid(x, y)
    Z1 = np.exp(-X**2 - Y**2)
    Z2 = np.exp(-(X - 1)**2 - (Y - 1)**2)
    Z = (Z1 - Z2) * 2

    # Positive contour defaults to solid
    fig1, ax1 = plt.subplots()
    CS1 = ax1.contour(X, Y, Z, 6, colors='k')
    ax1.clabel(CS1, fontsize=9, inline=True)
    ax1.set_title('Single color - positive contours solid (default)')
    assert CS1.linestyles is None  # default

    # Change linestyles using linestyles kwarg
    fig2, ax2 = plt.subplots()
    CS2 = ax2.contour(X, Y, Z, 6, colors='k', linestyles=style)
    ax2.clabel(CS2, fontsize=9, inline=True)
    ax2.set_title(f'Single color - positive contours {style}')
    assert CS2.linestyles == style

    # Ensure linestyles do not change when negative_linestyles is defined
    fig3, ax3 = plt.subplots()
    CS3 = ax3.contour(X, Y, Z, 6, colors='k', linestyles=style,
                      negative_linestyles='dashdot')
    ax3.clabel(CS3, fontsize=9, inline=True)
    ax3.set_title(f'Single color - positive contours {style}')
    assert CS3.linestyles == style


@pytest.mark.parametrize(
    "style", ['solid', 'dashed', 'dashdot', 'dotted'])
def test_negative_linestyles(style):
    delta = 0.025
    x = np.arange(-3.0, 3.0, delta)
    y = np.arange(-2.0, 2.0, delta)
    X, Y = np.meshgrid(x, y)
    Z1 = np.exp(-X**2 - Y**2)
    Z2 = np.exp(-(X - 1)**2 - (Y - 1)**2)
    Z = (Z1 - Z2) * 2

    # Negative contour defaults to dashed
    fig1, ax1 = plt.subplots()
    CS1 = ax1.contour(X, Y, Z, 6, colors='k')
    ax1.clabel(CS1, fontsize=9, inline=True)
    ax1.set_title('Single color - negative contours dashed (default)')
    assert CS1.negative_linestyles == 'dashed'  # default

    # Change negative_linestyles using rcParams
    plt.rcParams['contour.negative_linestyle'] = style
    fig2, ax2 = plt.subplots()
    CS2 = ax2.contour(X, Y, Z, 6, colors='k')
    ax2.clabel(CS2, fontsize=9, inline=True)
    ax2.set_title(f'Single color - negative contours {style}'
                   '(using rcParams)')
    assert CS2.negative_linestyles == style

    # Change negative_linestyles using negative_linestyles kwarg
    fig3, ax3 = plt.subplots()
    CS3 = ax3.contour(X, Y, Z, 6, colors='k', negative_linestyles=style)
    ax3.clabel(CS3, fontsize=9, inline=True)
    ax3.set_title(f'Single color - negative contours {style}')
    assert CS3.negative_linestyles == style

    # Ensure negative_linestyles do not change when linestyles is defined
    fig4, ax4 = plt.subplots()
    CS4 = ax4.contour(X, Y, Z, 6, colors='k', linestyles='dashdot',
                      negative_linestyles=style)
    ax4.clabel(CS4, fontsize=9, inline=True)
    ax4.set_title(f'Single color - negative contours {style}')
    assert CS4.negative_linestyles == style


def test_contour_remove():
    ax = plt.figure().add_subplot()
    orig_children = ax.get_children()
    cs = ax.contour(np.arange(16).reshape((4, 4)))
    cs.clabel()
    assert ax.get_children() != orig_children
    cs.remove()
    assert ax.get_children() == orig_children


def test_contour_no_args():
    fig, ax = plt.subplots()
    data = [[0, 1], [1, 0]]
    with pytest.raises(TypeError, match=r"contour\(\) takes from 1 to 4"):
        ax.contour(Z=data)


def test_contour_clip_path():
    fig, ax = plt.subplots()
    data = [[0, 1], [1, 0]]
    circle = mpatches.Circle([0.5, 0.5], 0.5, transform=ax.transAxes)
    cs = ax.contour(data, clip_path=circle)
    assert cs.get_clip_path() is not None


def test_bool_autolevel():
    x, y = np.random.rand(2, 9)
    z = (np.arange(9) % 2).reshape((3, 3)).astype(bool)
    m = [[False, False, False], [False, True, False], [False, False, False]]
    assert plt.contour(z.tolist()).levels.tolist() == [.5]
    assert plt.contour(z).levels.tolist() == [.5]
    assert plt.contour(np.ma.array(z, mask=m)).levels.tolist() == [.5]
    assert plt.contourf(z.tolist()).levels.tolist() == [0, .5, 1]
    assert plt.contourf(z).levels.tolist() == [0, .5, 1]
    assert plt.contourf(np.ma.array(z, mask=m)).levels.tolist() == [0, .5, 1]
    z = z.ravel()
    assert plt.tricontour(x, y, z.tolist()).levels.tolist() == [.5]
    assert plt.tricontour(x, y, z).levels.tolist() == [.5]
    assert plt.tricontourf(x, y, z.tolist()).levels.tolist() == [0, .5, 1]
    assert plt.tricontourf(x, y, z).levels.tolist() == [0, .5, 1]


def test_all_nan():
    x = np.array([[np.nan, np.nan], [np.nan, np.nan]])
    assert_array_almost_equal(plt.contour(x).levels,
                              [-1e-13, -7.5e-14, -5e-14, -2.4e-14, 0.0,
                                2.4e-14, 5e-14, 7.5e-14, 1e-13])


def test_allsegs_allkinds():
    x, y = np.meshgrid(np.arange(0, 10, 2), np.arange(0, 10, 2))
    z = np.sin(x) * np.cos(y)

    cs = plt.contour(x, y, z, levels=[0, 0.5])

    # Expect two levels, the first with 5 segments and the second with 4.
    for result in [cs.allsegs, cs.allkinds]:
        assert len(result) == 2
        assert len(result[0]) == 5
        assert len(result[1]) == 4
