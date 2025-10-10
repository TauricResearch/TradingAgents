import functools
import itertools
import platform
import sys

import pytest

from mpl_toolkits.mplot3d import Axes3D, axes3d, proj3d, art3d
from mpl_toolkits.mplot3d.axes3d import _Quaternion as Quaternion
import matplotlib as mpl
from matplotlib.backend_bases import (MouseButton, MouseEvent,
                                      NavigationToolbar2)
from matplotlib import cm
from matplotlib import colors as mcolors, patches as mpatch
from matplotlib.testing.decorators import image_comparison, check_figures_equal
from matplotlib.testing.widgets import mock_event
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.patches import Circle, PathPatch
from matplotlib.path import Path
from matplotlib.text import Text

import matplotlib.pyplot as plt
import numpy as np


mpl3d_image_comparison = functools.partial(
    image_comparison, remove_text=True, style='default')


def plot_cuboid(ax, scale):
    # plot a rectangular cuboid with side lengths given by scale (x, y, z)
    r = [0, 1]
    pts = itertools.combinations(np.array(list(itertools.product(r, r, r))), 2)
    for start, end in pts:
        if np.sum(np.abs(start - end)) == r[1] - r[0]:
            ax.plot3D(*zip(start*np.array(scale), end*np.array(scale)))


@check_figures_equal(extensions=["png"])
def test_invisible_axes(fig_test, fig_ref):
    ax = fig_test.subplots(subplot_kw=dict(projection='3d'))
    ax.set_visible(False)


@mpl3d_image_comparison(['grid_off.png'], style='mpl20')
def test_grid_off():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.grid(False)


@mpl3d_image_comparison(['invisible_ticks_axis.png'], style='mpl20')
def test_invisible_ticks_axis():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_zticks([])
    for axis in [ax.xaxis, ax.yaxis, ax.zaxis]:
        axis.line.set_visible(False)


@mpl3d_image_comparison(['axis_positions.png'], remove_text=False, style='mpl20')
def test_axis_positions():
    positions = ['upper', 'lower', 'both', 'none']
    fig, axs = plt.subplots(2, 2, subplot_kw={'projection': '3d'})
    for ax, pos in zip(axs.flatten(), positions):
        for axis in ax.xaxis, ax.yaxis, ax.zaxis:
            axis.set_label_position(pos)
            axis.set_ticks_position(pos)
        title = f'{pos}'
        ax.set(xlabel='x', ylabel='y', zlabel='z', title=title)


@mpl3d_image_comparison(['aspects.png'], remove_text=False, style='mpl20')
def test_aspects():
    aspects = ('auto', 'equal', 'equalxy', 'equalyz', 'equalxz', 'equal')
    _, axs = plt.subplots(2, 3, subplot_kw={'projection': '3d'})

    for ax in axs.flatten()[0:-1]:
        plot_cuboid(ax, scale=[1, 1, 5])
    # plot a cube as well to cover github #25443
    plot_cuboid(axs[1][2], scale=[1, 1, 1])

    for i, ax in enumerate(axs.flatten()):
        ax.set_title(aspects[i])
        ax.set_box_aspect((3, 4, 5))
        ax.set_aspect(aspects[i], adjustable='datalim')
    axs[1][2].set_title('equal (cube)')


@mpl3d_image_comparison(['aspects_adjust_box.png'],
                        remove_text=False, style='mpl20')
def test_aspects_adjust_box():
    aspects = ('auto', 'equal', 'equalxy', 'equalyz', 'equalxz')
    fig, axs = plt.subplots(1, len(aspects), subplot_kw={'projection': '3d'},
                            figsize=(11, 3))

    for i, ax in enumerate(axs):
        plot_cuboid(ax, scale=[4, 3, 5])
        ax.set_title(aspects[i])
        ax.set_aspect(aspects[i], adjustable='box')


def test_axes3d_repr():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.set_label('label')
    ax.set_title('title')
    ax.set_xlabel('x')
    ax.set_ylabel('y')
    ax.set_zlabel('z')
    assert repr(ax) == (
        "<Axes3D: label='label', "
        "title={'center': 'title'}, xlabel='x', ylabel='y', zlabel='z'>")


@mpl3d_image_comparison(['axes3d_primary_views.png'], style='mpl20',
                        tol=0.05 if sys.platform == "darwin" else 0)
def test_axes3d_primary_views():
    # (elev, azim, roll)
    views = [(90, -90, 0),  # XY
             (0, -90, 0),   # XZ
             (0, 0, 0),     # YZ
             (-90, 90, 0),  # -XY
             (0, 90, 0),    # -XZ
             (0, 180, 0)]   # -YZ
    # When viewing primary planes, draw the two visible axes so they intersect
    # at their low values
    fig, axs = plt.subplots(2, 3, subplot_kw={'projection': '3d'})
    for i, ax in enumerate(axs.flat):
        ax.set_xlabel('x')
        ax.set_ylabel('y')
        ax.set_zlabel('z')
        ax.set_proj_type('ortho')
        ax.view_init(elev=views[i][0], azim=views[i][1], roll=views[i][2])
    plt.tight_layout()


@mpl3d_image_comparison(['bar3d.png'], style='mpl20')
def test_bar3d():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    for c, z in zip(['r', 'g', 'b', 'y'], [30, 20, 10, 0]):
        xs = np.arange(20)
        ys = np.arange(20)
        cs = [c] * len(xs)
        cs[0] = 'c'
        ax.bar(xs, ys, zs=z, zdir='y', align='edge', color=cs, alpha=0.8)


def test_bar3d_colors():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    for c in ['red', 'green', 'blue', 'yellow']:
        xs = np.arange(len(c))
        ys = np.zeros_like(xs)
        zs = np.zeros_like(ys)
        # Color names with same length as xs/ys/zs should not be split into
        # individual letters.
        ax.bar3d(xs, ys, zs, 1, 1, 1, color=c)


@mpl3d_image_comparison(['bar3d_shaded.png'], style='mpl20')
def test_bar3d_shaded():
    x = np.arange(4)
    y = np.arange(5)
    x2d, y2d = np.meshgrid(x, y)
    x2d, y2d = x2d.ravel(), y2d.ravel()
    z = x2d + y2d + 1  # Avoid triggering bug with zero-depth boxes.

    views = [(30, -60, 0), (30, 30, 30), (-30, 30, -90), (300, -30, 0)]
    fig = plt.figure(figsize=plt.figaspect(1 / len(views)))
    axs = fig.subplots(
        1, len(views),
        subplot_kw=dict(projection='3d')
    )
    for ax, (elev, azim, roll) in zip(axs, views):
        ax.bar3d(x2d, y2d, x2d * 0, 1, 1, z, shade=True)
        ax.view_init(elev=elev, azim=azim, roll=roll)
    fig.canvas.draw()


@mpl3d_image_comparison(['bar3d_notshaded.png'], style='mpl20')
def test_bar3d_notshaded():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    x = np.arange(4)
    y = np.arange(5)
    x2d, y2d = np.meshgrid(x, y)
    x2d, y2d = x2d.ravel(), y2d.ravel()
    z = x2d + y2d
    ax.bar3d(x2d, y2d, x2d * 0, 1, 1, z, shade=False)
    fig.canvas.draw()


def test_bar3d_lightsource():
    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1, projection="3d")

    ls = mcolors.LightSource(azdeg=0, altdeg=90)

    length, width = 3, 4
    area = length * width

    x, y = np.meshgrid(np.arange(length), np.arange(width))
    x = x.ravel()
    y = y.ravel()
    dz = x + y

    color = [cm.coolwarm(i/area) for i in range(area)]

    collection = ax.bar3d(x=x, y=y, z=0,
                          dx=1, dy=1, dz=dz,
                          color=color, shade=True, lightsource=ls)

    # Testing that the custom 90° lightsource produces different shading on
    # the top facecolors compared to the default, and that those colors are
    # precisely (within floating point rounding errors of 4 ULP) the colors
    # from the colormap, due to the illumination parallel to the z-axis.
    np.testing.assert_array_max_ulp(color, collection._facecolor3d[1::6], 4)


@mpl3d_image_comparison(['contour3d.png'], style='mpl20',
                        tol=0 if platform.machine() == 'x86_64' else 0.002)
def test_contour3d():
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    X, Y, Z = axes3d.get_test_data(0.05)
    ax.contour(X, Y, Z, zdir='z', offset=-100, cmap=cm.coolwarm)
    ax.contour(X, Y, Z, zdir='x', offset=-40, cmap=cm.coolwarm)
    ax.contour(X, Y, Z, zdir='y', offset=40, cmap=cm.coolwarm)
    ax.axis(xmin=-40, xmax=40, ymin=-40, ymax=40, zmin=-100, zmax=100)


@mpl3d_image_comparison(['contour3d_extend3d.png'], style='mpl20')
def test_contour3d_extend3d():
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    X, Y, Z = axes3d.get_test_data(0.05)
    ax.contour(X, Y, Z, zdir='z', offset=-100, cmap=cm.coolwarm, extend3d=True)
    ax.set_xlim(-30, 30)
    ax.set_ylim(-20, 40)
    ax.set_zlim(-80, 80)


@mpl3d_image_comparison(['contourf3d.png'], style='mpl20')
def test_contourf3d():
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    X, Y, Z = axes3d.get_test_data(0.05)
    ax.contourf(X, Y, Z, zdir='z', offset=-100, cmap=cm.coolwarm)
    ax.contourf(X, Y, Z, zdir='x', offset=-40, cmap=cm.coolwarm)
    ax.contourf(X, Y, Z, zdir='y', offset=40, cmap=cm.coolwarm)
    ax.set_xlim(-40, 40)
    ax.set_ylim(-40, 40)
    ax.set_zlim(-100, 100)


@mpl3d_image_comparison(['contourf3d_fill.png'], style='mpl20')
def test_contourf3d_fill():
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    X, Y = np.meshgrid(np.arange(-2, 2, 0.25), np.arange(-2, 2, 0.25))
    Z = X.clip(0, 0)
    # This produces holes in the z=0 surface that causes rendering errors if
    # the Poly3DCollection is not aware of path code information (issue #4784)
    Z[::5, ::5] = 0.1
    ax.contourf(X, Y, Z, offset=0, levels=[-0.1, 0], cmap=cm.coolwarm)
    ax.set_xlim(-2, 2)
    ax.set_ylim(-2, 2)
    ax.set_zlim(-1, 1)


@pytest.mark.parametrize('extend, levels', [['both', [2, 4, 6]],
                                            ['min', [2, 4, 6, 8]],
                                            ['max', [0, 2, 4, 6]]])
@check_figures_equal(extensions=["png"])
def test_contourf3d_extend(fig_test, fig_ref, extend, levels):
    X, Y = np.meshgrid(np.arange(-2, 2, 0.25), np.arange(-2, 2, 0.25))
    # Z is in the range [0, 8]
    Z = X**2 + Y**2

    # Manually set the over/under colors to be the end of the colormap
    cmap = mpl.colormaps['viridis'].copy()
    cmap.set_under(cmap(0))
    cmap.set_over(cmap(255))
    # Set vmin/max to be the min/max values plotted on the reference image
    kwargs = {'vmin': 1, 'vmax': 7, 'cmap': cmap}

    ax_ref = fig_ref.add_subplot(projection='3d')
    ax_ref.contourf(X, Y, Z, levels=[0, 2, 4, 6, 8], **kwargs)

    ax_test = fig_test.add_subplot(projection='3d')
    ax_test.contourf(X, Y, Z, levels, extend=extend, **kwargs)

    for ax in [ax_ref, ax_test]:
        ax.set_xlim(-2, 2)
        ax.set_ylim(-2, 2)
        ax.set_zlim(-10, 10)


@mpl3d_image_comparison(['tricontour.png'], tol=0.02, style='mpl20')
def test_tricontour():
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    fig = plt.figure()

    np.random.seed(19680801)
    x = np.random.rand(1000) - 0.5
    y = np.random.rand(1000) - 0.5
    z = -(x**2 + y**2)

    ax = fig.add_subplot(1, 2, 1, projection='3d')
    ax.tricontour(x, y, z)
    ax = fig.add_subplot(1, 2, 2, projection='3d')
    ax.tricontourf(x, y, z)


def test_contour3d_1d_input():
    # Check that 1D sequences of different length for {x, y} doesn't error
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    nx, ny = 30, 20
    x = np.linspace(-10, 10, nx)
    y = np.linspace(-10, 10, ny)
    z = np.random.randint(0, 2, [ny, nx])
    ax.contour(x, y, z, [0.5])


@mpl3d_image_comparison(['lines3d.png'], style='mpl20')
def test_lines3d():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    theta = np.linspace(-4 * np.pi, 4 * np.pi, 100)
    z = np.linspace(-2, 2, 100)
    r = z ** 2 + 1
    x = r * np.sin(theta)
    y = r * np.cos(theta)
    ax.plot(x, y, z)


@check_figures_equal(extensions=["png"])
def test_plot_scalar(fig_test, fig_ref):
    ax1 = fig_test.add_subplot(projection='3d')
    ax1.plot([1], [1], "o")
    ax2 = fig_ref.add_subplot(projection='3d')
    ax2.plot(1, 1, "o")


def test_invalid_line_data():
    with pytest.raises(RuntimeError, match='x must be'):
        art3d.Line3D(0, [], [])
    with pytest.raises(RuntimeError, match='y must be'):
        art3d.Line3D([], 0, [])
    with pytest.raises(RuntimeError, match='z must be'):
        art3d.Line3D([], [], 0)

    line = art3d.Line3D([], [], [])
    with pytest.raises(RuntimeError, match='x must be'):
        line.set_data_3d(0, [], [])
    with pytest.raises(RuntimeError, match='y must be'):
        line.set_data_3d([], 0, [])
    with pytest.raises(RuntimeError, match='z must be'):
        line.set_data_3d([], [], 0)


@mpl3d_image_comparison(['mixedsubplot.png'], style='mpl20')
def test_mixedsubplots():
    def f(t):
        return np.cos(2*np.pi*t) * np.exp(-t)

    t1 = np.arange(0.0, 5.0, 0.1)
    t2 = np.arange(0.0, 5.0, 0.02)

    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    fig = plt.figure(figsize=plt.figaspect(2.))
    ax = fig.add_subplot(2, 1, 1)
    ax.plot(t1, f(t1), 'bo', t2, f(t2), 'k--', markerfacecolor='green')
    ax.grid(True)

    ax = fig.add_subplot(2, 1, 2, projection='3d')
    X, Y = np.meshgrid(np.arange(-5, 5, 0.25), np.arange(-5, 5, 0.25))
    R = np.hypot(X, Y)
    Z = np.sin(R)

    ax.plot_surface(X, Y, Z, rcount=40, ccount=40,
                    linewidth=0, antialiased=False)

    ax.set_zlim3d(-1, 1)


@check_figures_equal(extensions=['png'])
def test_tight_layout_text(fig_test, fig_ref):
    # text is currently ignored in tight layout. So the order of text() and
    # tight_layout() calls should not influence the result.
    ax1 = fig_test.add_subplot(projection='3d')
    ax1.text(.5, .5, .5, s='some string')
    fig_test.tight_layout()

    ax2 = fig_ref.add_subplot(projection='3d')
    fig_ref.tight_layout()
    ax2.text(.5, .5, .5, s='some string')


@mpl3d_image_comparison(['scatter3d.png'], style='mpl20')
def test_scatter3d():
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.scatter(np.arange(10), np.arange(10), np.arange(10),
               c='r', marker='o')
    x = y = z = np.arange(10, 20)
    ax.scatter(x, y, z, c='b', marker='^')
    z[-1] = 0  # Check that scatter() copies the data.
    # Ensure empty scatters do not break.
    ax.scatter([], [], [], c='r', marker='X')


@mpl3d_image_comparison(['scatter3d_color.png'], style='mpl20')
def test_scatter3d_color():
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    # Check that 'none' color works; these two should overlay to produce the
    # same as setting just `color`.
    ax.scatter(np.arange(10), np.arange(10), np.arange(10),
               facecolor='r', edgecolor='none', marker='o')
    ax.scatter(np.arange(10), np.arange(10), np.arange(10),
               facecolor='none', edgecolor='r', marker='o')

    ax.scatter(np.arange(10, 20), np.arange(10, 20), np.arange(10, 20),
               color='b', marker='s')


@mpl3d_image_comparison(['scatter3d_linewidth.png'], style='mpl20')
def test_scatter3d_linewidth():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    # Check that array-like linewidth can be set
    ax.scatter(np.arange(10), np.arange(10), np.arange(10),
               marker='o', linewidth=np.arange(10))


@check_figures_equal(extensions=['png'])
def test_scatter3d_linewidth_modification(fig_ref, fig_test):
    # Changing Path3DCollection linewidths with array-like post-creation
    # should work correctly.
    ax_test = fig_test.add_subplot(projection='3d')
    c = ax_test.scatter(np.arange(10), np.arange(10), np.arange(10),
                        marker='o')
    c.set_linewidths(np.arange(10))

    ax_ref = fig_ref.add_subplot(projection='3d')
    ax_ref.scatter(np.arange(10), np.arange(10), np.arange(10), marker='o',
                   linewidths=np.arange(10))


@check_figures_equal(extensions=['png'])
def test_scatter3d_modification(fig_ref, fig_test):
    # Changing Path3DCollection properties post-creation should work correctly.
    ax_test = fig_test.add_subplot(projection='3d')
    c = ax_test.scatter(np.arange(10), np.arange(10), np.arange(10),
                        marker='o')
    c.set_facecolor('C1')
    c.set_edgecolor('C2')
    c.set_alpha([0.3, 0.7] * 5)
    assert c.get_depthshade()
    c.set_depthshade(False)
    assert not c.get_depthshade()
    c.set_sizes(np.full(10, 75))
    c.set_linewidths(3)

    ax_ref = fig_ref.add_subplot(projection='3d')
    ax_ref.scatter(np.arange(10), np.arange(10), np.arange(10), marker='o',
                   facecolor='C1', edgecolor='C2', alpha=[0.3, 0.7] * 5,
                   depthshade=False, s=75, linewidths=3)


@pytest.mark.parametrize('depthshade', [True, False])
@check_figures_equal(extensions=['png'])
def test_scatter3d_sorting(fig_ref, fig_test, depthshade):
    """Test that marker properties are correctly sorted."""

    y, x = np.mgrid[:10, :10]
    z = np.arange(x.size).reshape(x.shape)

    sizes = np.full(z.shape, 25)
    sizes[0::2, 0::2] = 100
    sizes[1::2, 1::2] = 100

    facecolors = np.full(z.shape, 'C0')
    facecolors[:5, :5] = 'C1'
    facecolors[6:, :4] = 'C2'
    facecolors[6:, 6:] = 'C3'

    edgecolors = np.full(z.shape, 'C4')
    edgecolors[1:5, 1:5] = 'C5'
    edgecolors[5:9, 1:5] = 'C6'
    edgecolors[5:9, 5:9] = 'C7'

    linewidths = np.full(z.shape, 2)
    linewidths[0::2, 0::2] = 5
    linewidths[1::2, 1::2] = 5

    x, y, z, sizes, facecolors, edgecolors, linewidths = (
        a.flatten()
        for a in [x, y, z, sizes, facecolors, edgecolors, linewidths]
    )

    ax_ref = fig_ref.add_subplot(projection='3d')
    sets = (np.unique(a) for a in [sizes, facecolors, edgecolors, linewidths])
    for s, fc, ec, lw in itertools.product(*sets):
        subset = (
            (sizes != s) |
            (facecolors != fc) |
            (edgecolors != ec) |
            (linewidths != lw)
        )
        subset = np.ma.masked_array(z, subset, dtype=float)

        # When depth shading is disabled, the colors are passed through as
        # single-item lists; this triggers single path optimization. The
        # following reshaping is a hack to disable that, since the optimization
        # would not occur for the full scatter which has multiple colors.
        fc = np.repeat(fc, sum(~subset.mask))

        ax_ref.scatter(x, y, subset, s=s, fc=fc, ec=ec, lw=lw, alpha=1,
                       depthshade=depthshade)

    ax_test = fig_test.add_subplot(projection='3d')
    ax_test.scatter(x, y, z, s=sizes, fc=facecolors, ec=edgecolors,
                    lw=linewidths, alpha=1, depthshade=depthshade)


@pytest.mark.parametrize('azim', [-50, 130])  # yellow first, blue first
@check_figures_equal(extensions=['png'])
def test_marker_draw_order_data_reversed(fig_test, fig_ref, azim):
    """
    Test that the draw order does not depend on the data point order.

    For the given viewing angle at azim=-50, the yellow marker should be in
    front. For azim=130, the blue marker should be in front.
    """
    x = [-1, 1]
    y = [1, -1]
    z = [0, 0]
    color = ['b', 'y']
    ax = fig_test.add_subplot(projection='3d')
    ax.scatter(x, y, z, s=3500, c=color)
    ax.view_init(elev=0, azim=azim, roll=0)
    ax = fig_ref.add_subplot(projection='3d')
    ax.scatter(x[::-1], y[::-1], z[::-1], s=3500, c=color[::-1])
    ax.view_init(elev=0, azim=azim, roll=0)


@check_figures_equal(extensions=['png'])
def test_marker_draw_order_view_rotated(fig_test, fig_ref):
    """
    Test that the draw order changes with the direction.

    If we rotate *azim* by 180 degrees and exchange the colors, the plot
    plot should look the same again.
    """
    azim = 130
    x = [-1, 1]
    y = [1, -1]
    z = [0, 0]
    color = ['b', 'y']
    ax = fig_test.add_subplot(projection='3d')
    # axis are not exactly invariant under 180 degree rotation -> deactivate
    ax.set_axis_off()
    ax.scatter(x, y, z, s=3500, c=color)
    ax.view_init(elev=0, azim=azim, roll=0)
    ax = fig_ref.add_subplot(projection='3d')
    ax.set_axis_off()
    ax.scatter(x, y, z, s=3500, c=color[::-1])  # color reversed
    ax.view_init(elev=0, azim=azim - 180, roll=0)  # view rotated by 180 deg


@mpl3d_image_comparison(['plot_3d_from_2d.png'], tol=0.019, style='mpl20')
def test_plot_3d_from_2d():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    xs = np.arange(0, 5)
    ys = np.arange(5, 10)
    ax.plot(xs, ys, zs=0, zdir='x')
    ax.plot(xs, ys, zs=0, zdir='y')


@mpl3d_image_comparison(['fill_between_quad.png'], style='mpl20')
def test_fill_between_quad():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    theta = np.linspace(0, 2*np.pi, 50)

    x1 = np.cos(theta)
    y1 = np.sin(theta)
    z1 = 0.1 * np.sin(6 * theta)

    x2 = 0.6 * np.cos(theta)
    y2 = 0.6 * np.sin(theta)
    z2 = 2

    where = (theta < np.pi/2) | (theta > 3*np.pi/2)

    # Since none of x1 == x2, y1 == y2, or z1 == z2 is True, the fill_between
    # mode will map to 'quad'
    ax.fill_between(x1, y1, z1, x2, y2, z2,
                    where=where, mode='auto', alpha=0.5, edgecolor='k')


@mpl3d_image_comparison(['fill_between_polygon.png'], style='mpl20')
def test_fill_between_polygon():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    theta = np.linspace(0, 2*np.pi, 50)

    x1 = x2 = theta
    y1 = y2 = 0
    z1 = np.cos(theta)
    z2 = z1 + 1

    where = (theta < np.pi/2) | (theta > 3*np.pi/2)

    # Since x1 == x2 and y1 == y2, the fill_between mode will be 'polygon'
    ax.fill_between(x1, y1, z1, x2, y2, z2,
                    where=where, mode='auto', edgecolor='k')


@mpl3d_image_comparison(['surface3d.png'], style='mpl20')
def test_surface3d():
    # Remove this line when this test image is regenerated.
    plt.rcParams['pcolormesh.snap'] = False

    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    X = np.arange(-5, 5, 0.25)
    Y = np.arange(-5, 5, 0.25)
    X, Y = np.meshgrid(X, Y)
    R = np.hypot(X, Y)
    Z = np.sin(R)
    surf = ax.plot_surface(X, Y, Z, rcount=40, ccount=40, cmap=cm.coolwarm,
                           lw=0, antialiased=False)
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    ax.set_zlim(-1.01, 1.01)
    fig.colorbar(surf, shrink=0.5, aspect=5)


@image_comparison(['surface3d_label_offset_tick_position.png'], style='mpl20')
def test_surface3d_label_offset_tick_position():
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    ax = plt.figure().add_subplot(projection="3d")

    x, y = np.mgrid[0:6 * np.pi:0.25, 0:4 * np.pi:0.25]
    z = np.sqrt(np.abs(np.cos(x) + np.cos(y)))

    ax.plot_surface(x * 1e5, y * 1e6, z * 1e8, cmap='autumn', cstride=2, rstride=2)
    ax.set_xlabel("X label")
    ax.set_ylabel("Y label")
    ax.set_zlabel("Z label")


@mpl3d_image_comparison(['surface3d_shaded.png'], style='mpl20')
def test_surface3d_shaded():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    X = np.arange(-5, 5, 0.25)
    Y = np.arange(-5, 5, 0.25)
    X, Y = np.meshgrid(X, Y)
    R = np.sqrt(X ** 2 + Y ** 2)
    Z = np.sin(R)
    ax.plot_surface(X, Y, Z, rstride=5, cstride=5,
                    color=[0.25, 1, 0.25], lw=1, antialiased=False)
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    ax.set_zlim(-1.01, 1.01)


@mpl3d_image_comparison(['surface3d_masked.png'], style='mpl20')
def test_surface3d_masked():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    y = [1, 2, 3, 4, 5, 6, 7, 8]

    x, y = np.meshgrid(x, y)
    matrix = np.array(
        [
            [-1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [-1, 1, 2, 3, 4, 4, 4, 3, 2, 1, 1],
            [-1, -1., 4, 5, 6, 8, 6, 5, 4, 3, -1.],
            [-1, -1., 7, 8, 11, 12, 11, 8, 7, -1., -1.],
            [-1, -1., 8, 9, 10, 16, 10, 9, 10, 7, -1.],
            [-1, -1., -1., 12, 16, 20, 16, 12, 11, -1., -1.],
            [-1, -1., -1., -1., 22, 24, 22, 20, 18, -1., -1.],
            [-1, -1., -1., -1., -1., 28, 26, 25, -1., -1., -1.],
        ]
    )
    z = np.ma.masked_less(matrix, 0)
    norm = mcolors.Normalize(vmax=z.max(), vmin=z.min())
    colors = mpl.colormaps["plasma"](norm(z))
    ax.plot_surface(x, y, z, facecolors=colors)
    ax.view_init(30, -80, 0)


@check_figures_equal(extensions=["png"])
def test_plot_scatter_masks(fig_test, fig_ref):
    x = np.linspace(0, 10, 100)
    y = np.linspace(0, 10, 100)
    z = np.sin(x) * np.cos(y)
    mask = z > 0

    z_masked = np.ma.array(z, mask=mask)
    ax_test = fig_test.add_subplot(projection='3d')
    ax_test.scatter(x, y, z_masked)
    ax_test.plot(x, y, z_masked)

    x[mask] = y[mask] = z[mask] = np.nan
    ax_ref = fig_ref.add_subplot(projection='3d')
    ax_ref.scatter(x, y, z)
    ax_ref.plot(x, y, z)


@check_figures_equal(extensions=["png"])
def test_plot_surface_None_arg(fig_test, fig_ref):
    x, y = np.meshgrid(np.arange(5), np.arange(5))
    z = x + y
    ax_test = fig_test.add_subplot(projection='3d')
    ax_test.plot_surface(x, y, z, facecolors=None)
    ax_ref = fig_ref.add_subplot(projection='3d')
    ax_ref.plot_surface(x, y, z)


@mpl3d_image_comparison(['surface3d_masked_strides.png'], style='mpl20')
def test_surface3d_masked_strides():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    x, y = np.mgrid[-6:6.1:1, -6:6.1:1]
    z = np.ma.masked_less(x * y, 2)

    ax.plot_surface(x, y, z, rstride=4, cstride=4)
    ax.view_init(60, -45, 0)


@mpl3d_image_comparison(['text3d.png'], remove_text=False, style='mpl20')
def test_text3d():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    zdirs = (None, 'x', 'y', 'z', (1, 1, 0), (1, 1, 1))
    xs = (2, 6, 4, 9, 7, 2)
    ys = (6, 4, 8, 7, 2, 2)
    zs = (4, 2, 5, 6, 1, 7)

    for zdir, x, y, z in zip(zdirs, xs, ys, zs):
        label = '(%d, %d, %d), dir=%s' % (x, y, z, zdir)
        ax.text(x, y, z, label, zdir)

    ax.text(1, 1, 1, "red", color='red')
    ax.text2D(0.05, 0.95, "2D Text", transform=ax.transAxes)
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    ax.set_xlim3d(0, 10)
    ax.set_ylim3d(0, 10)
    ax.set_zlim3d(0, 10)
    ax.set_xlabel('X axis')
    ax.set_ylabel('Y axis')
    ax.set_zlabel('Z axis')


@check_figures_equal(extensions=['png'])
def test_text3d_modification(fig_ref, fig_test):
    # Modifying the Text position after the fact should work the same as
    # setting it directly.
    zdirs = (None, 'x', 'y', 'z', (1, 1, 0), (1, 1, 1))
    xs = (2, 6, 4, 9, 7, 2)
    ys = (6, 4, 8, 7, 2, 2)
    zs = (4, 2, 5, 6, 1, 7)

    ax_test = fig_test.add_subplot(projection='3d')
    ax_test.set_xlim3d(0, 10)
    ax_test.set_ylim3d(0, 10)
    ax_test.set_zlim3d(0, 10)
    for zdir, x, y, z in zip(zdirs, xs, ys, zs):
        t = ax_test.text(0, 0, 0, f'({x}, {y}, {z}), dir={zdir}')
        t.set_position_3d((x, y, z), zdir=zdir)

    ax_ref = fig_ref.add_subplot(projection='3d')
    ax_ref.set_xlim3d(0, 10)
    ax_ref.set_ylim3d(0, 10)
    ax_ref.set_zlim3d(0, 10)
    for zdir, x, y, z in zip(zdirs, xs, ys, zs):
        ax_ref.text(x, y, z, f'({x}, {y}, {z}), dir={zdir}', zdir=zdir)


@mpl3d_image_comparison(['trisurf3d.png'], tol=0.061, style='mpl20')
def test_trisurf3d():
    n_angles = 36
    n_radii = 8
    radii = np.linspace(0.125, 1.0, n_radii)
    angles = np.linspace(0, 2*np.pi, n_angles, endpoint=False)
    angles = np.repeat(angles[..., np.newaxis], n_radii, axis=1)
    angles[:, 1::2] += np.pi/n_angles

    x = np.append(0, (radii*np.cos(angles)).flatten())
    y = np.append(0, (radii*np.sin(angles)).flatten())
    z = np.sin(-x*y)

    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.plot_trisurf(x, y, z, cmap=cm.jet, linewidth=0.2)


@mpl3d_image_comparison(['trisurf3d_shaded.png'], tol=0.03, style='mpl20')
def test_trisurf3d_shaded():
    n_angles = 36
    n_radii = 8
    radii = np.linspace(0.125, 1.0, n_radii)
    angles = np.linspace(0, 2*np.pi, n_angles, endpoint=False)
    angles = np.repeat(angles[..., np.newaxis], n_radii, axis=1)
    angles[:, 1::2] += np.pi/n_angles

    x = np.append(0, (radii*np.cos(angles)).flatten())
    y = np.append(0, (radii*np.sin(angles)).flatten())
    z = np.sin(-x*y)

    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.plot_trisurf(x, y, z, color=[1, 0.5, 0], linewidth=0.2)


@mpl3d_image_comparison(['wireframe3d.png'], style='mpl20')
def test_wireframe3d():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    X, Y, Z = axes3d.get_test_data(0.05)
    ax.plot_wireframe(X, Y, Z, rcount=13, ccount=13)


@mpl3d_image_comparison(['wireframe3dzerocstride.png'], style='mpl20')
def test_wireframe3dzerocstride():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    X, Y, Z = axes3d.get_test_data(0.05)
    ax.plot_wireframe(X, Y, Z, rcount=13, ccount=0)


@mpl3d_image_comparison(['wireframe3dzerorstride.png'], style='mpl20')
def test_wireframe3dzerorstride():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    X, Y, Z = axes3d.get_test_data(0.05)
    ax.plot_wireframe(X, Y, Z, rstride=0, cstride=10)


def test_wireframe3dzerostrideraises():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    X, Y, Z = axes3d.get_test_data(0.05)
    with pytest.raises(ValueError):
        ax.plot_wireframe(X, Y, Z, rstride=0, cstride=0)


def test_mixedsamplesraises():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    X, Y, Z = axes3d.get_test_data(0.05)
    with pytest.raises(ValueError):
        ax.plot_wireframe(X, Y, Z, rstride=10, ccount=50)
    with pytest.raises(ValueError):
        ax.plot_surface(X, Y, Z, cstride=50, rcount=10)


# remove tolerance when regenerating the test image
@mpl3d_image_comparison(['quiver3d.png'], style='mpl20', tol=0.003)
def test_quiver3d():
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    pivots = ['tip', 'middle', 'tail']
    colors = ['tab:blue', 'tab:orange', 'tab:green']
    for i, (pivot, color) in enumerate(zip(pivots, colors)):
        x, y, z = np.meshgrid([-0.5, 0.5], [-0.5, 0.5], [-0.5, 0.5])
        u = -x
        v = -y
        w = -z
        # Offset each set in z direction
        z += 2 * i
        ax.quiver(x, y, z, u, v, w, length=1, pivot=pivot, color=color)
        ax.scatter(x, y, z, color=color)

    ax.set_xlim(-3, 3)
    ax.set_ylim(-3, 3)
    ax.set_zlim(-1, 5)


@check_figures_equal(extensions=["png"])
def test_quiver3d_empty(fig_test, fig_ref):
    fig_ref.add_subplot(projection='3d')
    x = y = z = u = v = w = []
    ax = fig_test.add_subplot(projection='3d')
    ax.quiver(x, y, z, u, v, w, length=0.1, pivot='tip', normalize=True)


@mpl3d_image_comparison(['quiver3d_masked.png'], style='mpl20')
def test_quiver3d_masked():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    # Using mgrid here instead of ogrid because masked_where doesn't
    # seem to like broadcasting very much...
    x, y, z = np.mgrid[-1:0.8:10j, -1:0.8:10j, -1:0.6:3j]

    u = np.sin(np.pi * x) * np.cos(np.pi * y) * np.cos(np.pi * z)
    v = -np.cos(np.pi * x) * np.sin(np.pi * y) * np.cos(np.pi * z)
    w = (2/3)**0.5 * np.cos(np.pi * x) * np.cos(np.pi * y) * np.sin(np.pi * z)
    u = np.ma.masked_where((-0.4 < x) & (x < 0.1), u, copy=False)
    v = np.ma.masked_where((0.1 < y) & (y < 0.7), v, copy=False)

    ax.quiver(x, y, z, u, v, w, length=0.1, pivot='tip', normalize=True)


@mpl3d_image_comparison(['quiver3d_colorcoded.png'], style='mpl20')
def test_quiver3d_colorcoded():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    x = y = dx = dz = np.zeros(10)
    z = dy = np.arange(10.)

    color = plt.cm.Reds(dy/dy.max())
    ax.quiver(x, y, z, dx, dy, dz, colors=color)
    ax.set_ylim(0, 10)


def test_patch_modification():
    fig = plt.figure()
    ax = fig.add_subplot(projection="3d")
    circle = Circle((0, 0))
    ax.add_patch(circle)
    art3d.patch_2d_to_3d(circle)
    circle.set_facecolor((1.0, 0.0, 0.0, 1))

    assert mcolors.same_color(circle.get_facecolor(), (1, 0, 0, 1))
    fig.canvas.draw()
    assert mcolors.same_color(circle.get_facecolor(), (1, 0, 0, 1))


@check_figures_equal(extensions=['png'])
def test_patch_collection_modification(fig_test, fig_ref):
    # Test that modifying Patch3DCollection properties after creation works.
    patch1 = Circle((0, 0), 0.05)
    patch2 = Circle((0.1, 0.1), 0.03)
    facecolors = np.array([[0., 0.5, 0., 1.], [0.5, 0., 0., 0.5]])
    c = art3d.Patch3DCollection([patch1, patch2], linewidths=3)

    ax_test = fig_test.add_subplot(projection='3d')
    ax_test.add_collection3d(c)
    c.set_edgecolor('C2')
    c.set_facecolor(facecolors)
    c.set_alpha(0.7)
    assert c.get_depthshade()
    c.set_depthshade(False)
    assert not c.get_depthshade()

    patch1 = Circle((0, 0), 0.05)
    patch2 = Circle((0.1, 0.1), 0.03)
    facecolors = np.array([[0., 0.5, 0., 1.], [0.5, 0., 0., 0.5]])
    c = art3d.Patch3DCollection([patch1, patch2], linewidths=3,
                                edgecolor='C2', facecolor=facecolors,
                                alpha=0.7, depthshade=False)

    ax_ref = fig_ref.add_subplot(projection='3d')
    ax_ref.add_collection3d(c)


def test_poly3dcollection_verts_validation():
    poly = [[0, 0, 1], [0, 1, 1], [0, 1, 0], [0, 0, 0]]
    with pytest.raises(ValueError, match=r'list of \(N, 3\) array-like'):
        art3d.Poly3DCollection(poly)  # should be Poly3DCollection([poly])

    poly = np.array(poly, dtype=float)
    with pytest.raises(ValueError, match=r'list of \(N, 3\) array-like'):
        art3d.Poly3DCollection(poly)  # should be Poly3DCollection([poly])


@mpl3d_image_comparison(['poly3dcollection_closed.png'], style='mpl20')
def test_poly3dcollection_closed():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    poly1 = np.array([[0, 0, 1], [0, 1, 1], [0, 0, 0]], float)
    poly2 = np.array([[0, 1, 1], [1, 1, 1], [1, 1, 0]], float)
    c1 = art3d.Poly3DCollection([poly1], linewidths=3, edgecolor='k',
                                facecolor=(0.5, 0.5, 1, 0.5), closed=True)
    c2 = art3d.Poly3DCollection([poly2], linewidths=3, edgecolor='k',
                                facecolor=(1, 0.5, 0.5, 0.5), closed=False)
    ax.add_collection3d(c1, autolim=False)
    ax.add_collection3d(c2, autolim=False)


def test_poly_collection_2d_to_3d_empty():
    poly = PolyCollection([])
    art3d.poly_collection_2d_to_3d(poly)
    assert isinstance(poly, art3d.Poly3DCollection)
    assert poly.get_paths() == []

    fig, ax = plt.subplots(subplot_kw=dict(projection='3d'))
    ax.add_artist(poly)
    minz = poly.do_3d_projection()
    assert np.isnan(minz)

    # Ensure drawing actually works.
    fig.canvas.draw()


@mpl3d_image_comparison(['poly3dcollection_alpha.png'], style='mpl20')
def test_poly3dcollection_alpha():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    poly1 = np.array([[0, 0, 1], [0, 1, 1], [0, 0, 0]], float)
    poly2 = np.array([[0, 1, 1], [1, 1, 1], [1, 1, 0]], float)
    c1 = art3d.Poly3DCollection([poly1], linewidths=3, edgecolor='k',
                                facecolor=(0.5, 0.5, 1), closed=True)
    c1.set_alpha(0.5)
    c2 = art3d.Poly3DCollection([poly2], linewidths=3, closed=False)
    # Post-creation modification should work.
    c2.set_facecolor((1, 0.5, 0.5))
    c2.set_edgecolor('k')
    c2.set_alpha(0.5)
    ax.add_collection3d(c1, autolim=False)
    ax.add_collection3d(c2, autolim=False)


@mpl3d_image_comparison(['add_collection3d_zs_array.png'], style='mpl20')
def test_add_collection3d_zs_array():
    theta = np.linspace(-4 * np.pi, 4 * np.pi, 100)
    z = np.linspace(-2, 2, 100)
    r = z**2 + 1
    x = r * np.sin(theta)
    y = r * np.cos(theta)

    points = np.column_stack([x, y, z]).reshape(-1, 1, 3)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)

    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    norm = plt.Normalize(0, 2*np.pi)
    # 2D LineCollection from x & y values
    lc = LineCollection(segments[:, :, :2], cmap='twilight', norm=norm)
    lc.set_array(np.mod(theta, 2*np.pi))
    # Add 2D collection at z values to ax
    line = ax.add_collection3d(lc, zs=segments[:, :, 2])

    assert line is not None

    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    ax.set_xlim(-5, 5)
    ax.set_ylim(-4, 6)
    ax.set_zlim(-2, 2)


@mpl3d_image_comparison(['add_collection3d_zs_scalar.png'], style='mpl20')
def test_add_collection3d_zs_scalar():
    theta = np.linspace(0, 2 * np.pi, 100)
    z = 1
    r = z**2 + 1
    x = r * np.sin(theta)
    y = r * np.cos(theta)

    points = np.column_stack([x, y]).reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)

    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    norm = plt.Normalize(0, 2*np.pi)
    lc = LineCollection(segments, cmap='twilight', norm=norm)
    lc.set_array(theta)
    line = ax.add_collection3d(lc, zs=z)

    assert line is not None

    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    ax.set_xlim(-5, 5)
    ax.set_ylim(-4, 6)
    ax.set_zlim(0, 2)


def test_line3dCollection_autoscaling():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    lines = [[(0, 0, 0), (1, 4, 2)],
             [(1, 1, 3), (2, 0, 2)],
             [(1, 0, 4), (1, 4, 5)]]

    lc = art3d.Line3DCollection(lines)
    ax.add_collection3d(lc)
    assert np.allclose(ax.get_xlim3d(), (-0.041666666666666664, 2.0416666666666665))
    assert np.allclose(ax.get_ylim3d(), (-0.08333333333333333, 4.083333333333333))
    assert np.allclose(ax.get_zlim3d(), (-0.10416666666666666, 5.104166666666667))


def test_poly3dCollection_autoscaling():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    poly = np.array([[0, 0, 0], [1, 1, 3], [1, 0, 4]])
    col = art3d.Poly3DCollection([poly])
    ax.add_collection3d(col)
    assert np.allclose(ax.get_xlim3d(), (-0.020833333333333332, 1.0208333333333333))
    assert np.allclose(ax.get_ylim3d(), (-0.020833333333333332, 1.0208333333333333))
    assert np.allclose(ax.get_zlim3d(), (-0.0833333333333333, 4.083333333333333))


@mpl3d_image_comparison(['axes3d_labelpad.png'],
                        remove_text=False, style='mpl20')
def test_axes3d_labelpad():
    fig = plt.figure()
    ax = fig.add_axes(Axes3D(fig))
    # labelpad respects rcParams
    assert ax.xaxis.labelpad == mpl.rcParams['axes.labelpad']
    # labelpad can be set in set_label
    ax.set_xlabel('X LABEL', labelpad=10)
    assert ax.xaxis.labelpad == 10
    ax.set_ylabel('Y LABEL')
    ax.set_zlabel('Z LABEL', labelpad=20)
    assert ax.zaxis.labelpad == 20
    assert ax.get_zlabel() == 'Z LABEL'
    # or manually
    ax.yaxis.labelpad = 20
    ax.zaxis.labelpad = -40

    # Tick labels also respect tick.pad (also from rcParams)
    for i, tick in enumerate(ax.yaxis.get_major_ticks()):
        tick.set_pad(tick.get_pad() + 5 - i * 5)


@mpl3d_image_comparison(['axes3d_cla.png'], remove_text=False, style='mpl20')
def test_axes3d_cla():
    # fixed in pull request 4553
    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1, projection='3d')
    ax.set_axis_off()
    ax.cla()  # make sure the axis displayed is 3D (not 2D)


@mpl3d_image_comparison(['axes3d_rotated.png'],
                        remove_text=False, style='mpl20')
def test_axes3d_rotated():
    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1, projection='3d')
    ax.view_init(90, 45, 0)  # look down, rotated. Should be square


def test_plotsurface_1d_raises():
    x = np.linspace(0.5, 10, num=100)
    y = np.linspace(0.5, 10, num=100)
    X, Y = np.meshgrid(x, y)
    z = np.random.randn(100)

    fig = plt.figure(figsize=(14, 6))
    ax = fig.add_subplot(1, 2, 1, projection='3d')
    with pytest.raises(ValueError):
        ax.plot_surface(X, Y, z)


def _test_proj_make_M():
    # eye point
    E = np.array([1000, -1000, 2000])
    R = np.array([100, 100, 100])
    V = np.array([0, 0, 1])
    roll = 0
    u, v, w = proj3d._view_axes(E, R, V, roll)
    viewM = proj3d._view_transformation_uvw(u, v, w, E)
    perspM = proj3d._persp_transformation(100, -100, 1)
    M = np.dot(perspM, viewM)
    return M


def test_proj_transform():
    M = _test_proj_make_M()
    invM = np.linalg.inv(M)

    xs = np.array([0, 1, 1, 0, 0, 0, 1, 1, 0, 0]) * 300.0
    ys = np.array([0, 0, 1, 1, 0, 0, 0, 1, 1, 0]) * 300.0
    zs = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1]) * 300.0

    txs, tys, tzs = proj3d.proj_transform(xs, ys, zs, M)
    ixs, iys, izs = proj3d.inv_transform(txs, tys, tzs, invM)

    np.testing.assert_almost_equal(ixs, xs)
    np.testing.assert_almost_equal(iys, ys)
    np.testing.assert_almost_equal(izs, zs)


def _test_proj_draw_axes(M, s=1, *args, **kwargs):
    xs = [0, s, 0, 0]
    ys = [0, 0, s, 0]
    zs = [0, 0, 0, s]
    txs, tys, tzs = proj3d.proj_transform(xs, ys, zs, M)
    o, ax, ay, az = zip(txs, tys)
    lines = [(o, ax), (o, ay), (o, az)]

    fig, ax = plt.subplots(*args, **kwargs)
    linec = LineCollection(lines)
    ax.add_collection(linec)
    for x, y, t in zip(txs, tys, ['o', 'x', 'y', 'z']):
        ax.text(x, y, t)

    return fig, ax


@mpl3d_image_comparison(['proj3d_axes_cube.png'], style='mpl20')
def test_proj_axes_cube():
    M = _test_proj_make_M()

    ts = '0 1 2 3 0 4 5 6 7 4'.split()
    xs = np.array([0, 1, 1, 0, 0, 0, 1, 1, 0, 0]) * 300.0
    ys = np.array([0, 0, 1, 1, 0, 0, 0, 1, 1, 0]) * 300.0
    zs = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1]) * 300.0

    txs, tys, tzs = proj3d.proj_transform(xs, ys, zs, M)

    fig, ax = _test_proj_draw_axes(M, s=400)

    ax.scatter(txs, tys, c=tzs)
    ax.plot(txs, tys, c='r')
    for x, y, t in zip(txs, tys, ts):
        ax.text(x, y, t)

    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    ax.set_xlim(-0.2, 0.2)
    ax.set_ylim(-0.2, 0.2)


@mpl3d_image_comparison(['proj3d_axes_cube_ortho.png'], style='mpl20')
def test_proj_axes_cube_ortho():
    E = np.array([200, 100, 100])
    R = np.array([0, 0, 0])
    V = np.array([0, 0, 1])
    roll = 0
    u, v, w = proj3d._view_axes(E, R, V, roll)
    viewM = proj3d._view_transformation_uvw(u, v, w, E)
    orthoM = proj3d._ortho_transformation(-1, 1)
    M = np.dot(orthoM, viewM)

    ts = '0 1 2 3 0 4 5 6 7 4'.split()
    xs = np.array([0, 1, 1, 0, 0, 0, 1, 1, 0, 0]) * 100
    ys = np.array([0, 0, 1, 1, 0, 0, 0, 1, 1, 0]) * 100
    zs = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1]) * 100

    txs, tys, tzs = proj3d.proj_transform(xs, ys, zs, M)

    fig, ax = _test_proj_draw_axes(M, s=150)

    ax.scatter(txs, tys, s=300-tzs)
    ax.plot(txs, tys, c='r')
    for x, y, t in zip(txs, tys, ts):
        ax.text(x, y, t)

    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    ax.set_xlim(-200, 200)
    ax.set_ylim(-200, 200)


def test_world():
    xmin, xmax = 100, 120
    ymin, ymax = -100, 100
    zmin, zmax = 0.1, 0.2
    M = proj3d.world_transformation(xmin, xmax, ymin, ymax, zmin, zmax)
    np.testing.assert_allclose(M,
                               [[5e-2, 0, 0, -5],
                                [0, 5e-3, 0, 5e-1],
                                [0, 0, 1e1, -1],
                                [0, 0, 0, 1]])


def test_autoscale():
    fig, ax = plt.subplots(subplot_kw={"projection": "3d"})
    assert ax.get_zscale() == 'linear'
    ax._view_margin = 0
    ax.margins(x=0, y=.1, z=.2)
    ax.plot([0, 1], [0, 1], [0, 1])
    assert ax.get_w_lims() == (0, 1, -.1, 1.1, -.2, 1.2)
    ax.autoscale(False)
    ax.set_autoscalez_on(True)
    ax.plot([0, 2], [0, 2], [0, 2])
    assert ax.get_w_lims() == (0, 1, -.1, 1.1, -.4, 2.4)
    ax.autoscale(axis='x')
    ax.plot([0, 2], [0, 2], [0, 2])
    assert ax.get_w_lims() == (0, 2, -.1, 1.1, -.4, 2.4)


@pytest.mark.parametrize('axis', ('x', 'y', 'z'))
@pytest.mark.parametrize('auto', (True, False, None))
def test_unautoscale(axis, auto):
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    x = np.arange(100)
    y = np.linspace(-0.1, 0.1, 100)
    ax.scatter(x, y)

    get_autoscale_on = getattr(ax, f'get_autoscale{axis}_on')
    set_lim = getattr(ax, f'set_{axis}lim')
    get_lim = getattr(ax, f'get_{axis}lim')

    post_auto = get_autoscale_on() if auto is None else auto

    set_lim((-0.5, 0.5), auto=auto)
    assert post_auto == get_autoscale_on()
    fig.canvas.draw()
    np.testing.assert_array_equal(get_lim(), (-0.5, 0.5))


@check_figures_equal(extensions=["png"])
def test_culling(fig_test, fig_ref):
    xmins = (-100, -50)
    for fig, xmin in zip((fig_test, fig_ref), xmins):
        ax = fig.add_subplot(projection='3d')
        n = abs(xmin) + 1
        xs = np.linspace(0, xmin, n)
        ys = np.ones(n)
        zs = np.zeros(n)
        ax.plot(xs, ys, zs, 'k')

        ax.set(xlim=(-5, 5), ylim=(-5, 5), zlim=(-5, 5))
        ax.view_init(5, 180, 0)


def test_axes3d_focal_length_checks():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    with pytest.raises(ValueError):
        ax.set_proj_type('persp', focal_length=0)
    with pytest.raises(ValueError):
        ax.set_proj_type('ortho', focal_length=1)


@mpl3d_image_comparison(['axes3d_focal_length.png'],
                        remove_text=False, style='mpl20')
def test_axes3d_focal_length():
    fig, axs = plt.subplots(1, 2, subplot_kw={'projection': '3d'})
    axs[0].set_proj_type('persp', focal_length=np.inf)
    axs[1].set_proj_type('persp', focal_length=0.15)


@mpl3d_image_comparison(['axes3d_ortho.png'], remove_text=False, style='mpl20')
def test_axes3d_ortho():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.set_proj_type('ortho')


@mpl3d_image_comparison(['axes3d_isometric.png'], style='mpl20')
def test_axes3d_isometric():
    from itertools import combinations, product
    fig, ax = plt.subplots(subplot_kw=dict(
        projection='3d',
        proj_type='ortho',
        box_aspect=(4, 4, 4)
    ))
    r = (-1, 1)  # stackoverflow.com/a/11156353
    for s, e in combinations(np.array(list(product(r, r, r))), 2):
        if abs(s - e).sum() == r[1] - r[0]:
            ax.plot3D(*zip(s, e), c='k')
    ax.view_init(elev=np.degrees(np.arctan(1. / np.sqrt(2))), azim=-45, roll=0)
    ax.grid(True)


@check_figures_equal(extensions=["png"])
def test_axlim_clip(fig_test, fig_ref):
    # With axlim clipping
    ax = fig_test.add_subplot(projection="3d")
    x = np.linspace(0, 1, 11)
    y = np.linspace(0, 1, 11)
    X, Y = np.meshgrid(x, y)
    Z = X + Y
    ax.plot_surface(X, Y, Z, facecolor='C1', edgecolors=None,
                    rcount=50, ccount=50, axlim_clip=True)
    # This ax.plot is to cover the extra surface edge which is not clipped out
    ax.plot([0.5, 0.5], [0, 1], [0.5, 1.5],
            color='k', linewidth=3, zorder=5, axlim_clip=True)
    ax.scatter(X.ravel(), Y.ravel(), Z.ravel() + 1, axlim_clip=True)
    ax.quiver(X.ravel(), Y.ravel(), Z.ravel() + 2,
              0*X.ravel(), 0*Y.ravel(), 0*Z.ravel() + 1,
              arrow_length_ratio=0, axlim_clip=True)
    ax.plot(X[0], Y[0], Z[0] + 3, color='C2', axlim_clip=True)
    ax.text(1.1, 0.5, 4, 'test', axlim_clip=True)  # won't be visible
    ax.set(xlim=(0, 0.5), ylim=(0, 1), zlim=(0, 5))

    # With manual clipping
    ax = fig_ref.add_subplot(projection="3d")
    idx = (X <= 0.5)
    X = X[idx].reshape(11, 6)
    Y = Y[idx].reshape(11, 6)
    Z = Z[idx].reshape(11, 6)
    ax.plot_surface(X, Y, Z, facecolor='C1', edgecolors=None,
                    rcount=50, ccount=50, axlim_clip=False)
    ax.plot([0.5, 0.5], [0, 1], [0.5, 1.5],
            color='k', linewidth=3, zorder=5, axlim_clip=False)
    ax.scatter(X.ravel(), Y.ravel(), Z.ravel() + 1, axlim_clip=False)
    ax.quiver(X.ravel(), Y.ravel(), Z.ravel() + 2,
              0*X.ravel(), 0*Y.ravel(), 0*Z.ravel() + 1,
              arrow_length_ratio=0, axlim_clip=False)
    ax.plot(X[0], Y[0], Z[0] + 3, color='C2', axlim_clip=False)
    ax.set(xlim=(0, 0.5), ylim=(0, 1), zlim=(0, 5))


@pytest.mark.parametrize('value', [np.inf, np.nan])
@pytest.mark.parametrize(('setter', 'side'), [
    ('set_xlim3d', 'left'),
    ('set_xlim3d', 'right'),
    ('set_ylim3d', 'bottom'),
    ('set_ylim3d', 'top'),
    ('set_zlim3d', 'bottom'),
    ('set_zlim3d', 'top'),
])
def test_invalid_axes_limits(setter, side, value):
    limit = {side: value}
    fig = plt.figure()
    obj = fig.add_subplot(projection='3d')
    with pytest.raises(ValueError):
        getattr(obj, setter)(**limit)


class TestVoxels:
    @mpl3d_image_comparison(['voxels-simple.png'], style='mpl20')
    def test_simple(self):
        fig, ax = plt.subplots(subplot_kw={"projection": "3d"})

        x, y, z = np.indices((5, 4, 3))
        voxels = (x == y) | (y == z)
        ax.voxels(voxels)

    @mpl3d_image_comparison(['voxels-edge-style.png'], style='mpl20')
    def test_edge_style(self):
        fig, ax = plt.subplots(subplot_kw={"projection": "3d"})

        x, y, z = np.indices((5, 5, 4))
        voxels = ((x - 2)**2 + (y - 2)**2 + (z-1.5)**2) < 2.2**2
        v = ax.voxels(voxels, linewidths=3, edgecolor='C1')

        # change the edge color of one voxel
        v[max(v.keys())].set_edgecolor('C2')

    @mpl3d_image_comparison(['voxels-named-colors.png'], style='mpl20')
    def test_named_colors(self):
        """Test with colors set to a 3D object array of strings."""
        fig, ax = plt.subplots(subplot_kw={"projection": "3d"})

        x, y, z = np.indices((10, 10, 10))
        voxels = (x == y) | (y == z)
        voxels = voxels & ~(x * y * z < 1)
        colors = np.full((10, 10, 10), 'C0', dtype=np.object_)
        colors[(x < 5) & (y < 5)] = '0.25'
        colors[(x + z) < 10] = 'cyan'
        ax.voxels(voxels, facecolors=colors)

    @mpl3d_image_comparison(['voxels-rgb-data.png'], style='mpl20')
    def test_rgb_data(self):
        """Test with colors set to a 4d float array of rgb data."""
        fig, ax = plt.subplots(subplot_kw={"projection": "3d"})

        x, y, z = np.indices((10, 10, 10))
        voxels = (x == y) | (y == z)
        colors = np.zeros((10, 10, 10, 3))
        colors[..., 0] = x / 9
        colors[..., 1] = y / 9
        colors[..., 2] = z / 9
        ax.voxels(voxels, facecolors=colors)

    @mpl3d_image_comparison(['voxels-alpha.png'], style='mpl20')
    def test_alpha(self):
        fig, ax = plt.subplots(subplot_kw={"projection": "3d"})

        x, y, z = np.indices((10, 10, 10))
        v1 = x == y
        v2 = np.abs(x - y) < 2
        voxels = v1 | v2
        colors = np.zeros((10, 10, 10, 4))
        colors[v2] = [1, 0, 0, 0.5]
        colors[v1] = [0, 1, 0, 0.5]
        v = ax.voxels(voxels, facecolors=colors)

        assert type(v) is dict
        for coord, poly in v.items():
            assert voxels[coord], "faces returned for absent voxel"
            assert isinstance(poly, art3d.Poly3DCollection)

    @mpl3d_image_comparison(['voxels-xyz.png'],
                            tol=0.01, remove_text=False, style='mpl20')
    def test_xyz(self):
        fig, ax = plt.subplots(subplot_kw={"projection": "3d"})

        def midpoints(x):
            sl = ()
            for i in range(x.ndim):
                x = (x[sl + np.index_exp[:-1]] +
                     x[sl + np.index_exp[1:]]) / 2.0
                sl += np.index_exp[:]
            return x

        # prepare some coordinates, and attach rgb values to each
        r, g, b = np.indices((17, 17, 17)) / 16.0
        rc = midpoints(r)
        gc = midpoints(g)
        bc = midpoints(b)

        # define a sphere about [0.5, 0.5, 0.5]
        sphere = (rc - 0.5)**2 + (gc - 0.5)**2 + (bc - 0.5)**2 < 0.5**2

        # combine the color components
        colors = np.zeros(sphere.shape + (3,))
        colors[..., 0] = rc
        colors[..., 1] = gc
        colors[..., 2] = bc

        # and plot everything
        ax.voxels(r, g, b, sphere,
                  facecolors=colors,
                  edgecolors=np.clip(2*colors - 0.5, 0, 1),  # brighter
                  linewidth=0.5)

    def test_calling_conventions(self):
        x, y, z = np.indices((3, 4, 5))
        filled = np.ones((2, 3, 4))

        fig, ax = plt.subplots(subplot_kw={"projection": "3d"})

        # all the valid calling conventions
        for kw in (dict(), dict(edgecolor='k')):
            ax.voxels(filled, **kw)
            ax.voxels(filled=filled, **kw)
            ax.voxels(x, y, z, filled, **kw)
            ax.voxels(x, y, z, filled=filled, **kw)

        # duplicate argument
        with pytest.raises(TypeError, match='voxels'):
            ax.voxels(x, y, z, filled, filled=filled)
        # missing arguments
        with pytest.raises(TypeError, match='voxels'):
            ax.voxels(x, y)
        # x, y, z are positional only - this passes them on as attributes of
        # Poly3DCollection
        with pytest.raises(AttributeError, match="keyword argument 'x'") as exec_info:
            ax.voxels(filled=filled, x=x, y=y, z=z)
        assert exec_info.value.name == 'x'


def test_line3d_set_get_data_3d():
    x, y, z = [0, 1], [2, 3], [4, 5]
    x2, y2, z2 = [6, 7], [8, 9], [10, 11]
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    lines = ax.plot(x, y, z)
    line = lines[0]
    np.testing.assert_array_equal((x, y, z), line.get_data_3d())
    line.set_data_3d(x2, y2, z2)
    np.testing.assert_array_equal((x2, y2, z2), line.get_data_3d())
    line.set_xdata(x)
    line.set_ydata(y)
    line.set_3d_properties(zs=z, zdir='z')
    np.testing.assert_array_equal((x, y, z), line.get_data_3d())
    line.set_3d_properties(zs=0, zdir='z')
    np.testing.assert_array_equal((x, y, np.zeros_like(z)), line.get_data_3d())


@check_figures_equal(extensions=["png"])
def test_inverted(fig_test, fig_ref):
    # Plot then invert.
    ax = fig_test.add_subplot(projection="3d")
    ax.plot([1, 1, 10, 10], [1, 10, 10, 10], [1, 1, 1, 10])
    ax.invert_yaxis()
    # Invert then plot.
    ax = fig_ref.add_subplot(projection="3d")
    ax.invert_yaxis()
    ax.plot([1, 1, 10, 10], [1, 10, 10, 10], [1, 1, 1, 10])


def test_inverted_cla():
    # GitHub PR #5450. Setting autoscale should reset
    # axes to be non-inverted.
    fig, ax = plt.subplots(subplot_kw={"projection": "3d"})
    # 1. test that a new axis is not inverted per default
    assert not ax.xaxis_inverted()
    assert not ax.yaxis_inverted()
    assert not ax.zaxis_inverted()
    ax.set_xlim(1, 0)
    ax.set_ylim(1, 0)
    ax.set_zlim(1, 0)
    assert ax.xaxis_inverted()
    assert ax.yaxis_inverted()
    assert ax.zaxis_inverted()
    ax.cla()
    assert not ax.xaxis_inverted()
    assert not ax.yaxis_inverted()
    assert not ax.zaxis_inverted()


def test_ax3d_tickcolour():
    fig = plt.figure()
    ax = Axes3D(fig)

    ax.tick_params(axis='x', colors='red')
    ax.tick_params(axis='y', colors='red')
    ax.tick_params(axis='z', colors='red')
    fig.canvas.draw()

    for tick in ax.xaxis.get_major_ticks():
        assert tick.tick1line._color == 'red'
    for tick in ax.yaxis.get_major_ticks():
        assert tick.tick1line._color == 'red'
    for tick in ax.zaxis.get_major_ticks():
        assert tick.tick1line._color == 'red'


@check_figures_equal(extensions=["png"])
def test_ticklabel_format(fig_test, fig_ref):
    axs = fig_test.subplots(4, 5, subplot_kw={"projection": "3d"})
    for ax in axs.flat:
        ax.set_xlim(1e7, 1e7 + 10)
    for row, name in zip(axs, ["x", "y", "z", "both"]):
        row[0].ticklabel_format(
            axis=name, style="plain")
        row[1].ticklabel_format(
            axis=name, scilimits=(-2, 2))
        row[2].ticklabel_format(
            axis=name, useOffset=not mpl.rcParams["axes.formatter.useoffset"])
        row[3].ticklabel_format(
            axis=name, useLocale=not mpl.rcParams["axes.formatter.use_locale"])
        row[4].ticklabel_format(
            axis=name,
            useMathText=not mpl.rcParams["axes.formatter.use_mathtext"])

    def get_formatters(ax, names):
        return [getattr(ax, name).get_major_formatter() for name in names]

    axs = fig_ref.subplots(4, 5, subplot_kw={"projection": "3d"})
    for ax in axs.flat:
        ax.set_xlim(1e7, 1e7 + 10)
    for row, names in zip(
            axs, [["xaxis"], ["yaxis"], ["zaxis"], ["xaxis", "yaxis", "zaxis"]]
    ):
        for fmt in get_formatters(row[0], names):
            fmt.set_scientific(False)
        for fmt in get_formatters(row[1], names):
            fmt.set_powerlimits((-2, 2))
        for fmt in get_formatters(row[2], names):
            fmt.set_useOffset(not mpl.rcParams["axes.formatter.useoffset"])
        for fmt in get_formatters(row[3], names):
            fmt.set_useLocale(not mpl.rcParams["axes.formatter.use_locale"])
        for fmt in get_formatters(row[4], names):
            fmt.set_useMathText(
                not mpl.rcParams["axes.formatter.use_mathtext"])


@check_figures_equal(extensions=["png"])
def test_quiver3D_smoke(fig_test, fig_ref):
    pivot = "middle"
    # Make the grid
    x, y, z = np.meshgrid(
        np.arange(-0.8, 1, 0.2),
        np.arange(-0.8, 1, 0.2),
        np.arange(-0.8, 1, 0.8)
    )
    u = v = w = np.ones_like(x)

    for fig, length in zip((fig_ref, fig_test), (1, 1.0)):
        ax = fig.add_subplot(projection="3d")
        ax.quiver(x, y, z, u, v, w, length=length, pivot=pivot)


@image_comparison(["minor_ticks.png"], style="mpl20")
def test_minor_ticks():
    ax = plt.figure().add_subplot(projection="3d")
    ax.set_xticks([0.25], minor=True)
    ax.set_xticklabels(["quarter"], minor=True)
    ax.set_yticks([0.33], minor=True)
    ax.set_yticklabels(["third"], minor=True)
    ax.set_zticks([0.50], minor=True)
    ax.set_zticklabels(["half"], minor=True)


# remove tolerance when regenerating the test image
@mpl3d_image_comparison(['errorbar3d_errorevery.png'], style='mpl20', tol=0.003)
def test_errorbar3d_errorevery():
    """Tests errorevery functionality for 3D errorbars."""
    t = np.arange(0, 2*np.pi+.1, 0.01)
    x, y, z = np.sin(t), np.cos(3*t), np.sin(5*t)

    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    estep = 15
    i = np.arange(t.size)
    zuplims = (i % estep == 0) & (i // estep % 3 == 0)
    zlolims = (i % estep == 0) & (i // estep % 3 == 2)

    ax.errorbar(x, y, z, 0.2, zuplims=zuplims, zlolims=zlolims,
                errorevery=estep)


@mpl3d_image_comparison(['errorbar3d.png'], style='mpl20',
                        tol=0 if platform.machine() == 'x86_64' else 0.02)
def test_errorbar3d():
    """Tests limits, color styling, and legend for 3D errorbars."""
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    d = [1, 2, 3, 4, 5]
    e = [.5, .5, .5, .5, .5]
    ax.errorbar(x=d, y=d, z=d, xerr=e, yerr=e, zerr=e, capsize=3,
                zuplims=[False, True, False, True, True],
                zlolims=[True, False, False, True, False],
                yuplims=True,
                ecolor='purple', label='Error lines')
    ax.legend()


@image_comparison(['stem3d.png'], style='mpl20', tol=0.009)
def test_stem3d():
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    fig, axs = plt.subplots(2, 3, figsize=(8, 6),
                            constrained_layout=True,
                            subplot_kw={'projection': '3d'})

    theta = np.linspace(0, 2*np.pi)
    x = np.cos(theta - np.pi/2)
    y = np.sin(theta - np.pi/2)
    z = theta

    for ax, zdir in zip(axs[0], ['x', 'y', 'z']):
        ax.stem(x, y, z, orientation=zdir)
        ax.set_title(f'orientation={zdir}')

    x = np.linspace(-np.pi/2, np.pi/2, 20)
    y = np.ones_like(x)
    z = np.cos(x)

    for ax, zdir in zip(axs[1], ['x', 'y', 'z']):
        markerline, stemlines, baseline = ax.stem(
            x, y, z,
            linefmt='C4-.', markerfmt='C1D', basefmt='C2',
            orientation=zdir)
        ax.set_title(f'orientation={zdir}')
        markerline.set(markerfacecolor='none', markeredgewidth=2)
        baseline.set_linewidth(3)


@image_comparison(["equal_box_aspect.png"], style="mpl20")
def test_equal_box_aspect():
    from itertools import product, combinations

    fig = plt.figure()
    ax = fig.add_subplot(projection="3d")

    # Make data
    u = np.linspace(0, 2 * np.pi, 100)
    v = np.linspace(0, np.pi, 100)
    x = np.outer(np.cos(u), np.sin(v))
    y = np.outer(np.sin(u), np.sin(v))
    z = np.outer(np.ones_like(u), np.cos(v))

    # Plot the surface
    ax.plot_surface(x, y, z)

    # draw cube
    r = [-1, 1]
    for s, e in combinations(np.array(list(product(r, r, r))), 2):
        if np.sum(np.abs(s - e)) == r[1] - r[0]:
            ax.plot3D(*zip(s, e), color="b")

    # Make axes limits
    xyzlim = np.column_stack(
        [ax.get_xlim3d(), ax.get_ylim3d(), ax.get_zlim3d()]
    )
    XYZlim = [min(xyzlim[0]), max(xyzlim[1])]
    ax.set_xlim3d(XYZlim)
    ax.set_ylim3d(XYZlim)
    ax.set_zlim3d(XYZlim)
    ax.axis('off')
    ax.set_box_aspect((1, 1, 1))

    with pytest.raises(ValueError, match="Argument zoom ="):
        ax.set_box_aspect((1, 1, 1), zoom=-1)


def test_colorbar_pos():
    num_plots = 2
    fig, axs = plt.subplots(1, num_plots, figsize=(4, 5),
                            constrained_layout=True,
                            subplot_kw={'projection': '3d'})
    for ax in axs:
        p_tri = ax.plot_trisurf(np.random.randn(5), np.random.randn(5),
                                np.random.randn(5))

    cbar = plt.colorbar(p_tri, ax=axs, orientation='horizontal')

    fig.canvas.draw()
    # check that actually on the bottom
    assert cbar.ax.get_position().extents[1] < 0.2


def test_inverted_zaxis():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.set_zlim(0, 1)
    assert not ax.zaxis_inverted()
    assert ax.get_zlim() == (0, 1)
    assert ax.get_zbound() == (0, 1)

    # Change bound
    ax.set_zbound((0, 2))
    assert not ax.zaxis_inverted()
    assert ax.get_zlim() == (0, 2)
    assert ax.get_zbound() == (0, 2)

    # Change invert
    ax.invert_zaxis()
    assert ax.zaxis_inverted()
    assert ax.get_zlim() == (2, 0)
    assert ax.get_zbound() == (0, 2)

    # Set upper bound
    ax.set_zbound(upper=1)
    assert ax.zaxis_inverted()
    assert ax.get_zlim() == (1, 0)
    assert ax.get_zbound() == (0, 1)

    # Set lower bound
    ax.set_zbound(lower=2)
    assert ax.zaxis_inverted()
    assert ax.get_zlim() == (2, 1)
    assert ax.get_zbound() == (1, 2)


def test_set_zlim():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    assert np.allclose(ax.get_zlim(), (-1/48, 49/48))
    ax.set_zlim(zmax=2)
    assert np.allclose(ax.get_zlim(), (-1/48, 2))
    ax.set_zlim(zmin=1)
    assert ax.get_zlim() == (1, 2)

    with pytest.raises(
            TypeError, match="Cannot pass both 'lower' and 'min'"):
        ax.set_zlim(bottom=0, zmin=1)
    with pytest.raises(
            TypeError, match="Cannot pass both 'upper' and 'max'"):
        ax.set_zlim(top=0, zmax=1)


@check_figures_equal(extensions=["png"])
def test_shared_view(fig_test, fig_ref):
    elev, azim, roll = 5, 20, 30
    ax1 = fig_test.add_subplot(131, projection="3d")
    ax2 = fig_test.add_subplot(132, projection="3d", shareview=ax1)
    ax3 = fig_test.add_subplot(133, projection="3d")
    ax3.shareview(ax1)
    ax2.view_init(elev=elev, azim=azim, roll=roll, share=True)

    for subplot_num in (131, 132, 133):
        ax = fig_ref.add_subplot(subplot_num, projection="3d")
        ax.view_init(elev=elev, azim=azim, roll=roll)


def test_shared_axes_retick():
    fig = plt.figure()
    ax1 = fig.add_subplot(211, projection="3d")
    ax2 = fig.add_subplot(212, projection="3d", sharez=ax1)
    ax1.plot([0, 1], [0, 1], [0, 2])
    ax2.plot([0, 1], [0, 1], [0, 2])
    ax1.set_zticks([-0.5, 0, 2, 2.5])
    # check that setting ticks on a shared axis is synchronized
    assert ax1.get_zlim() == (-0.5, 2.5)
    assert ax2.get_zlim() == (-0.5, 2.5)


def test_quaternion():
    # 1:
    q1 = Quaternion(1, [0, 0, 0])
    assert q1.scalar == 1
    assert (q1.vector == [0, 0, 0]).all
    # __neg__:
    assert (-q1).scalar == -1
    assert ((-q1).vector == [0, 0, 0]).all
    # i, j, k:
    qi = Quaternion(0, [1, 0, 0])
    assert qi.scalar == 0
    assert (qi.vector == [1, 0, 0]).all
    qj = Quaternion(0, [0, 1, 0])
    assert qj.scalar == 0
    assert (qj.vector == [0, 1, 0]).all
    qk = Quaternion(0, [0, 0, 1])
    assert qk.scalar == 0
    assert (qk.vector == [0, 0, 1]).all
    # i^2 = j^2 = k^2 = -1:
    assert qi*qi == -q1
    assert qj*qj == -q1
    assert qk*qk == -q1
    # identity:
    assert q1*qi == qi
    assert q1*qj == qj
    assert q1*qk == qk
    # i*j=k, j*k=i, k*i=j:
    assert qi*qj == qk
    assert qj*qk == qi
    assert qk*qi == qj
    assert qj*qi == -qk
    assert qk*qj == -qi
    assert qi*qk == -qj
    # __mul__:
    assert (Quaternion(2, [3, 4, 5]) * Quaternion(6, [7, 8, 9])
            == Quaternion(-86, [28, 48, 44]))
    # conjugate():
    for q in [q1, qi, qj, qk]:
        assert q.conjugate().scalar == q.scalar
        assert (q.conjugate().vector == -q.vector).all
        assert q.conjugate().conjugate() == q
        assert ((q*q.conjugate()).vector == 0).all
    # norm:
    q0 = Quaternion(0, [0, 0, 0])
    assert q0.norm == 0
    assert q1.norm == 1
    assert qi.norm == 1
    assert qj.norm == 1
    assert qk.norm == 1
    for q in [q0, q1, qi, qj, qk]:
        assert q.norm == (q*q.conjugate()).scalar
    # normalize():
    for q in [
        Quaternion(2, [0, 0, 0]),
        Quaternion(0, [3, 0, 0]),
        Quaternion(0, [0, 4, 0]),
        Quaternion(0, [0, 0, 5]),
        Quaternion(6, [7, 8, 9])
    ]:
        assert q.normalize().norm == 1
    # reciprocal():
    for q in [q1, qi, qj, qk]:
        assert q*q.reciprocal() == q1
        assert q.reciprocal()*q == q1
    # rotate():
    assert (qi.rotate([1, 2, 3]) == np.array([1, -2, -3])).all
    # rotate_from_to():
    for r1, r2, q in [
        ([1, 0, 0], [0, 1, 0], Quaternion(np.sqrt(1/2), [0, 0, np.sqrt(1/2)])),
        ([1, 0, 0], [0, 0, 1], Quaternion(np.sqrt(1/2), [0, -np.sqrt(1/2), 0])),
        ([1, 0, 0], [1, 0, 0], Quaternion(1, [0, 0, 0]))
    ]:
        assert Quaternion.rotate_from_to(r1, r2) == q
    # rotate_from_to(), special case:
    for r1 in [[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]]:
        r1 = np.array(r1)
        with pytest.warns(UserWarning):
            q = Quaternion.rotate_from_to(r1, -r1)
        assert np.isclose(q.norm, 1)
        assert np.dot(q.vector, r1) == 0
    # from_cardan_angles(), as_cardan_angles():
    for elev, azim, roll in [(0, 0, 0),
                             (90, 0, 0), (0, 90, 0), (0, 0, 90),
                             (0, 30, 30), (30, 0, 30), (30, 30, 0),
                             (47, 11, -24)]:
        for mag in [1, 2]:
            q = Quaternion.from_cardan_angles(
                np.deg2rad(elev), np.deg2rad(azim), np.deg2rad(roll))
            assert np.isclose(q.norm, 1)
            q = Quaternion(mag * q.scalar, mag * q.vector)
            np.testing.assert_allclose(np.rad2deg(Quaternion.as_cardan_angles(q)),
                                       (elev, azim, roll), atol=1e-6)


@pytest.mark.parametrize('style',
                         ('azel', 'trackball', 'sphere', 'arcball'))
def test_rotate(style):
    """Test rotating using the left mouse button."""
    if style == 'azel':
        s = 0.5
    else:
        s = mpl.rcParams['axes3d.trackballsize'] / 2
    s *= 0.5
    mpl.rcParams['axes3d.trackballborder'] = 0
    with mpl.rc_context({'axes3d.mouserotationstyle': style}):
        for roll, dx, dy in [
                [0, 1, 0],
                [30, 1, 0],
                [0, 0, 1],
                [30, 0, 1],
                [0, 0.5, np.sqrt(3)/2],
                [30, 0.5, np.sqrt(3)/2],
                [0, 2, 0]]:
            fig = plt.figure()
            ax = fig.add_subplot(1, 1, 1, projection='3d')
            ax.view_init(0, 0, roll)
            ax.figure.canvas.draw()

            # drag mouse to change orientation
            ax._button_press(
                mock_event(ax, button=MouseButton.LEFT, xdata=0, ydata=0))
            ax._on_move(
                mock_event(ax, button=MouseButton.LEFT,
                           xdata=s*dx*ax._pseudo_w, ydata=s*dy*ax._pseudo_h))
            ax.figure.canvas.draw()

            c = np.sqrt(3)/2
            expectations = {
                ('azel', 0, 1, 0): (0,  -45, 0),
                ('azel', 0, 0, 1): (-45, 0, 0),
                ('azel', 0, 0.5, c): (-38.971143, -22.5, 0),
                ('azel', 0, 2, 0): (0, -90, 0),
                ('azel', 30, 1, 0): (22.5, -38.971143, 30),
                ('azel', 30, 0, 1): (-38.971143, -22.5, 30),
                ('azel', 30, 0.5, c): (-22.5, -38.971143, 30),

                ('trackball', 0, 1, 0): (0, -28.64789, 0),
                ('trackball', 0, 0, 1): (-28.64789, 0, 0),
                ('trackball', 0, 0.5, c): (-24.531578, -15.277726, 3.340403),
                ('trackball', 0, 2, 0): (0, -180/np.pi, 0),
                ('trackball', 30, 1, 0): (13.869588, -25.319385, 26.87008),
                ('trackball', 30, 0, 1): (-24.531578, -15.277726, 33.340403),
                ('trackball', 30, 0.5, c): (-13.869588, -25.319385, 33.129920),

                ('sphere', 0, 1, 0): (0, -30, 0),
                ('sphere', 0, 0, 1): (-30, 0, 0),
                ('sphere', 0, 0.5, c): (-25.658906, -16.102114, 3.690068),
                ('sphere', 0, 2, 0): (0, -90, 0),
                ('sphere', 30, 1, 0): (14.477512, -26.565051, 26.565051),
                ('sphere', 30, 0, 1): (-25.658906, -16.102114, 33.690068),
                ('sphere', 30, 0.5, c): (-14.477512, -26.565051, 33.434949),

                ('arcball', 0, 1, 0): (0, -60, 0),
                ('arcball', 0, 0, 1): (-60, 0, 0),
                ('arcball', 0, 0.5, c): (-48.590378, -40.893395, 19.106605),
                ('arcball', 0, 2, 0): (0, 180, 0),
                ('arcball', 30, 1, 0): (25.658906, -56.309932, 16.102114),
                ('arcball', 30, 0, 1): (-48.590378, -40.893395, 49.106605),
                ('arcball', 30, 0.5, c): (-25.658906, -56.309932, 43.897886)}
            new_elev, new_azim, new_roll = expectations[(style, roll, dx, dy)]
            np.testing.assert_allclose((ax.elev, ax.azim, ax.roll),
                                       (new_elev, new_azim, new_roll), atol=1e-6)


def test_pan():
    """Test mouse panning using the middle mouse button."""

    def convert_lim(dmin, dmax):
        """Convert min/max limits to center and range."""
        center = (dmin + dmax) / 2
        range_ = dmax - dmin
        return center, range_

    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.scatter(0, 0, 0)
    fig.canvas.draw()

    x_center0, x_range0 = convert_lim(*ax.get_xlim3d())
    y_center0, y_range0 = convert_lim(*ax.get_ylim3d())
    z_center0, z_range0 = convert_lim(*ax.get_zlim3d())

    # move mouse diagonally to pan along all axis.
    ax._button_press(
        mock_event(ax, button=MouseButton.MIDDLE, xdata=0, ydata=0))
    ax._on_move(
        mock_event(ax, button=MouseButton.MIDDLE, xdata=1, ydata=1))

    x_center, x_range = convert_lim(*ax.get_xlim3d())
    y_center, y_range = convert_lim(*ax.get_ylim3d())
    z_center, z_range = convert_lim(*ax.get_zlim3d())

    # Ranges have not changed
    assert x_range == pytest.approx(x_range0)
    assert y_range == pytest.approx(y_range0)
    assert z_range == pytest.approx(z_range0)

    # But center positions have
    assert x_center != pytest.approx(x_center0)
    assert y_center != pytest.approx(y_center0)
    assert z_center != pytest.approx(z_center0)


@pytest.mark.parametrize("tool,button,key,expected",
                         [("zoom", MouseButton.LEFT, None,  # zoom in
                          ((0.00, 0.06), (0.01, 0.07), (0.02, 0.08))),
                          ("zoom", MouseButton.LEFT, 'x',  # zoom in
                          ((-0.01, 0.10), (-0.03, 0.08), (-0.06, 0.06))),
                          ("zoom", MouseButton.LEFT, 'y',  # zoom in
                          ((-0.07, 0.05), (-0.04, 0.08), (0.00, 0.12))),
                          ("zoom", MouseButton.RIGHT, None,  # zoom out
                          ((-0.09, 0.15), (-0.08, 0.17), (-0.07, 0.18))),
                          ("pan", MouseButton.LEFT, None,
                          ((-0.70, -0.58), (-1.04, -0.91), (-1.27, -1.15))),
                          ("pan", MouseButton.LEFT, 'x',
                          ((-0.97, -0.84), (-0.58, -0.46), (-0.06, 0.06))),
                          ("pan", MouseButton.LEFT, 'y',
                          ((0.20, 0.32), (-0.51, -0.39), (-1.27, -1.15)))])
def test_toolbar_zoom_pan(tool, button, key, expected):
    # NOTE: The expected zoom values are rough ballparks of moving in the view
    #       to make sure we are getting the right direction of motion.
    #       The specific values can and should change if the zoom movement
    #       scaling factor gets updated.
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.scatter(0, 0, 0)
    fig.canvas.draw()
    xlim0, ylim0, zlim0 = ax.get_xlim3d(), ax.get_ylim3d(), ax.get_zlim3d()

    # Mouse from (0, 0) to (1, 1)
    d0 = (0, 0)
    d1 = (1, 1)
    # Convert to screen coordinates ("s").  Events are defined only with pixel
    # precision, so round the pixel values, and below, check against the
    # corresponding xdata/ydata, which are close but not equal to d0/d1.
    s0 = ax.transData.transform(d0).astype(int)
    s1 = ax.transData.transform(d1).astype(int)

    # Set up the mouse movements
    start_event = MouseEvent(
        "button_press_event", fig.canvas, *s0, button, key=key)
    stop_event = MouseEvent(
        "button_release_event", fig.canvas, *s1, button, key=key)

    tb = NavigationToolbar2(fig.canvas)
    if tool == "zoom":
        tb.zoom()
        tb.press_zoom(start_event)
        tb.drag_zoom(stop_event)
        tb.release_zoom(stop_event)
    else:
        tb.pan()
        tb.press_pan(start_event)
        tb.drag_pan(stop_event)
        tb.release_pan(stop_event)

    # Should be close, but won't be exact due to screen integer resolution
    xlim, ylim, zlim = expected
    assert ax.get_xlim3d() == pytest.approx(xlim, abs=0.01)
    assert ax.get_ylim3d() == pytest.approx(ylim, abs=0.01)
    assert ax.get_zlim3d() == pytest.approx(zlim, abs=0.01)

    # Ensure that back, forward, and home buttons work
    tb.back()
    assert ax.get_xlim3d() == pytest.approx(xlim0)
    assert ax.get_ylim3d() == pytest.approx(ylim0)
    assert ax.get_zlim3d() == pytest.approx(zlim0)

    tb.forward()
    assert ax.get_xlim3d() == pytest.approx(xlim, abs=0.01)
    assert ax.get_ylim3d() == pytest.approx(ylim, abs=0.01)
    assert ax.get_zlim3d() == pytest.approx(zlim, abs=0.01)

    tb.home()
    assert ax.get_xlim3d() == pytest.approx(xlim0)
    assert ax.get_ylim3d() == pytest.approx(ylim0)
    assert ax.get_zlim3d() == pytest.approx(zlim0)


@mpl.style.context('default')
@check_figures_equal(extensions=["png"])
def test_scalarmap_update(fig_test, fig_ref):

    x, y, z = np.array(list(itertools.product(*[np.arange(0, 5, 1),
                                                np.arange(0, 5, 1),
                                                np.arange(0, 5, 1)]))).T
    c = x + y

    # test
    ax_test = fig_test.add_subplot(111, projection='3d')
    sc_test = ax_test.scatter(x, y, z, c=c, s=40, cmap='viridis')
    # force a draw
    fig_test.canvas.draw()
    # mark it as "stale"
    sc_test.changed()

    # ref
    ax_ref = fig_ref.add_subplot(111, projection='3d')
    sc_ref = ax_ref.scatter(x, y, z, c=c, s=40, cmap='viridis')


def test_subfigure_simple():
    # smoketest that subfigures can work...
    fig = plt.figure()
    sf = fig.subfigures(1, 2)
    ax = sf[0].add_subplot(1, 1, 1, projection='3d')
    ax = sf[1].add_subplot(1, 1, 1, projection='3d', label='other')


# Update style when regenerating the test image
@image_comparison(baseline_images=['computed_zorder'], remove_text=True,
                  extensions=['png'], style=('mpl20'))
def test_computed_zorder():
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    fig = plt.figure()
    ax1 = fig.add_subplot(221, projection='3d')
    ax2 = fig.add_subplot(222, projection='3d')
    ax2.computed_zorder = False

    # create a horizontal plane
    corners = ((0, 0, 0), (0, 5, 0), (5, 5, 0), (5, 0, 0))
    for ax in (ax1, ax2):
        tri = art3d.Poly3DCollection([corners],
                                     facecolors='white',
                                     edgecolors='black',
                                     zorder=1)
        ax.add_collection3d(tri)

        # plot a vector
        ax.plot((2, 2), (2, 2), (0, 4), c='red', zorder=2)

        # plot some points
        ax.scatter((3, 3), (1, 3), (1, 3), c='red', zorder=10)

        ax.set_xlim((0, 5.0))
        ax.set_ylim((0, 5.0))
        ax.set_zlim((0, 2.5))

    ax3 = fig.add_subplot(223, projection='3d')
    ax4 = fig.add_subplot(224, projection='3d')
    ax4.computed_zorder = False

    dim = 10
    X, Y = np.meshgrid((-dim, dim), (-dim, dim))
    Z = np.zeros((2, 2))

    angle = 0.5
    X2, Y2 = np.meshgrid((-dim, dim), (0, dim))
    Z2 = Y2 * angle
    X3, Y3 = np.meshgrid((-dim, dim), (-dim, 0))
    Z3 = Y3 * angle

    r = 7
    M = 1000
    th = np.linspace(0, 2 * np.pi, M)
    x, y, z = r * np.cos(th),  r * np.sin(th), angle * r * np.sin(th)
    for ax in (ax3, ax4):
        ax.plot_surface(X2, Y3, Z3,
                        color='blue',
                        alpha=0.5,
                        linewidth=0,
                        zorder=-1)
        ax.plot(x[y < 0], y[y < 0], z[y < 0],
                lw=5,
                linestyle='--',
                color='green',
                zorder=0)

        ax.plot_surface(X, Y, Z,
                        color='red',
                        alpha=0.5,
                        linewidth=0,
                        zorder=1)

        ax.plot(r * np.sin(th), r * np.cos(th), np.zeros(M),
                lw=5,
                linestyle='--',
                color='black',
                zorder=2)

        ax.plot_surface(X2, Y2, Z2,
                        color='blue',
                        alpha=0.5,
                        linewidth=0,
                        zorder=3)

        ax.plot(x[y > 0], y[y > 0], z[y > 0], lw=5,
                linestyle='--',
                color='green',
                zorder=4)
        ax.view_init(elev=20, azim=-20, roll=0)
        ax.axis('off')


def test_format_coord():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    x = np.arange(10)
    ax.plot(x, np.sin(x))
    xv = 0.1
    yv = 0.1
    fig.canvas.draw()
    assert ax.format_coord(xv, yv) == 'x=10.5227, y pane=1.0417, z=0.1444'

    # Modify parameters
    ax.view_init(roll=30, vertical_axis="y")
    fig.canvas.draw()
    assert ax.format_coord(xv, yv) == 'x pane=9.1875, y=0.9761, z=0.1291'

    # Reset parameters
    ax.view_init()
    fig.canvas.draw()
    assert ax.format_coord(xv, yv) == 'x=10.5227, y pane=1.0417, z=0.1444'

    # Check orthographic projection
    ax.set_proj_type('ortho')
    fig.canvas.draw()
    assert ax.format_coord(xv, yv) == 'x=10.8869, y pane=1.0417, z=0.1528'

    # Check non-default perspective projection
    ax.set_proj_type('persp', focal_length=0.1)
    fig.canvas.draw()
    assert ax.format_coord(xv, yv) == 'x=9.0620, y pane=1.0417, z=0.1110'


def test_get_axis_position():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    x = np.arange(10)
    ax.plot(x, np.sin(x))
    fig.canvas.draw()
    assert ax.get_axis_position() == (False, True, False)


def test_margins():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.margins(0.2)
    assert ax.margins() == (0.2, 0.2, 0.2)
    ax.margins(0.1, 0.2, 0.3)
    assert ax.margins() == (0.1, 0.2, 0.3)
    ax.margins(x=0)
    assert ax.margins() == (0, 0.2, 0.3)
    ax.margins(y=0.1)
    assert ax.margins() == (0, 0.1, 0.3)
    ax.margins(z=0)
    assert ax.margins() == (0, 0.1, 0)


def test_margin_getters():
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.margins(0.1, 0.2, 0.3)
    assert ax.get_xmargin() == 0.1
    assert ax.get_ymargin() == 0.2
    assert ax.get_zmargin() == 0.3


@pytest.mark.parametrize('err, args, kwargs, match', (
        (ValueError, (-1,), {}, r'margin must be greater than -0\.5'),
        (ValueError, (1, -1, 1), {}, r'margin must be greater than -0\.5'),
        (ValueError, (1, 1, -1), {}, r'margin must be greater than -0\.5'),
        (ValueError, tuple(), {'x': -1}, r'margin must be greater than -0\.5'),
        (ValueError, tuple(), {'y': -1}, r'margin must be greater than -0\.5'),
        (ValueError, tuple(), {'z': -1}, r'margin must be greater than -0\.5'),
        (TypeError, (1, ), {'x': 1},
         'Cannot pass both positional and keyword'),
        (TypeError, (1, ), {'x': 1, 'y': 1, 'z': 1},
         'Cannot pass both positional and keyword'),
        (TypeError, (1, ), {'x': 1, 'y': 1},
         'Cannot pass both positional and keyword'),
        (TypeError, (1, 1), {}, 'Must pass a single positional argument for'),
))
def test_margins_errors(err, args, kwargs, match):
    with pytest.raises(err, match=match):
        fig = plt.figure()
        ax = fig.add_subplot(projection='3d')
        ax.margins(*args, **kwargs)


@check_figures_equal(extensions=["png"])
def test_text_3d(fig_test, fig_ref):
    ax = fig_ref.add_subplot(projection="3d")
    txt = Text(0.5, 0.5, r'Foo bar $\int$')
    art3d.text_2d_to_3d(txt, z=1)
    ax.add_artist(txt)
    assert txt.get_position_3d() == (0.5, 0.5, 1)

    ax = fig_test.add_subplot(projection="3d")
    t3d = art3d.Text3D(0.5, 0.5, 1, r'Foo bar $\int$')
    ax.add_artist(t3d)
    assert t3d.get_position_3d() == (0.5, 0.5, 1)


def test_draw_single_lines_from_Nx1():
    # Smoke test for GH#23459
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.plot([[0], [1]], [[0], [1]], [[0], [1]])


@check_figures_equal(extensions=["png"])
def test_pathpatch_3d(fig_test, fig_ref):
    ax = fig_ref.add_subplot(projection="3d")
    path = Path.unit_rectangle()
    patch = PathPatch(path)
    art3d.pathpatch_2d_to_3d(patch, z=(0, 0.5, 0.7, 1, 0), zdir='y')
    ax.add_artist(patch)

    ax = fig_test.add_subplot(projection="3d")
    pp3d = art3d.PathPatch3D(path, zs=(0, 0.5, 0.7, 1, 0), zdir='y')
    ax.add_artist(pp3d)


@image_comparison(baseline_images=['scatter_spiral.png'],
                  remove_text=True,
                  style='mpl20')
def test_scatter_spiral():
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    th = np.linspace(0, 2 * np.pi * 6, 256)
    sc = ax.scatter(np.sin(th), np.cos(th), th, s=(1 + th * 5), c=th ** 2)

    # force at least 1 draw!
    fig.canvas.draw()


def test_Poly3DCollection_get_path():
    # Smoke test to see that get_path does not raise
    # See GH#27361
    fig, ax = plt.subplots(subplot_kw={"projection": "3d"})
    p = Circle((0, 0), 1.0)
    ax.add_patch(p)
    art3d.pathpatch_2d_to_3d(p)
    p.get_path()


def test_Poly3DCollection_get_facecolor():
    # Smoke test to see that get_facecolor does not raise
    # See GH#4067
    y, x = np.ogrid[1:10:100j, 1:10:100j]
    z2 = np.cos(x) ** 3 - np.sin(y) ** 2
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    r = ax.plot_surface(x, y, z2, cmap='hot')
    r.get_facecolor()


def test_Poly3DCollection_get_edgecolor():
    # Smoke test to see that get_edgecolor does not raise
    # See GH#4067
    y, x = np.ogrid[1:10:100j, 1:10:100j]
    z2 = np.cos(x) ** 3 - np.sin(y) ** 2
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    r = ax.plot_surface(x, y, z2, cmap='hot')
    r.get_edgecolor()


@pytest.mark.parametrize(
    "vertical_axis, proj_expected, axis_lines_expected, tickdirs_expected",
    [
        (
            "z",
            [
                [0.0, 1.142857, 0.0, -0.571429],
                [0.0, 0.0, 0.857143, -0.428571],
                [0.0, 0.0, 0.0, -10.0],
                [-1.142857, 0.0, 0.0, 10.571429],
            ],
            [
                ([0.05617978, 0.06329114], [-0.04213483, -0.04746835]),
                ([-0.06329114, 0.06329114], [-0.04746835, -0.04746835]),
                ([-0.06329114, -0.06329114], [-0.04746835, 0.04746835]),
            ],
            [1, 0, 0],
        ),
        (
            "y",
            [
                [1.142857, 0.0, 0.0, -0.571429],
                [0.0, 0.857143, 0.0, -0.428571],
                [0.0, 0.0, 0.0, -10.0],
                [0.0, 0.0, -1.142857, 10.571429],
            ],
            [
                ([-0.06329114, 0.06329114], [0.04746835, 0.04746835]),
                ([0.06329114, 0.06329114], [-0.04746835, 0.04746835]),
                ([-0.05617978, -0.06329114], [0.04213483, 0.04746835]),
            ],
            [2, 2, 0],
        ),
        (
            "x",
            [
                [0.0, 0.0, 1.142857, -0.571429],
                [0.857143, 0.0, 0.0, -0.428571],
                [0.0, 0.0, 0.0, -10.0],
                [0.0, -1.142857, 0.0, 10.571429],
            ],
            [
                ([-0.06329114, -0.06329114], [0.04746835, -0.04746835]),
                ([0.06329114, 0.05617978], [0.04746835, 0.04213483]),
                ([0.06329114, -0.06329114], [0.04746835, 0.04746835]),
            ],
            [1, 2, 1],
        ),
    ],
)
def test_view_init_vertical_axis(
    vertical_axis, proj_expected, axis_lines_expected, tickdirs_expected
):
    """
    Test the actual projection, axis lines and ticks matches expected values.

    Parameters
    ----------
    vertical_axis : str
        Axis to align vertically.
    proj_expected : ndarray
        Expected values from ax.get_proj().
    axis_lines_expected : tuple of arrays
        Edgepoints of the axis line. Expected values retrieved according
        to ``ax.get_[xyz]axis().line.get_data()``.
    tickdirs_expected : list of int
        indexes indicating which axis to create a tick line along.
    """
    rtol = 2e-06
    ax = plt.subplot(1, 1, 1, projection="3d")
    ax.view_init(elev=0, azim=0, roll=0, vertical_axis=vertical_axis)
    ax.get_figure().canvas.draw()

    # Assert the projection matrix:
    proj_actual = ax.get_proj()
    np.testing.assert_allclose(proj_expected, proj_actual, rtol=rtol)

    for i, axis in enumerate([ax.get_xaxis(), ax.get_yaxis(), ax.get_zaxis()]):
        # Assert black lines are correctly aligned:
        axis_line_expected = axis_lines_expected[i]
        axis_line_actual = axis.line.get_data()
        np.testing.assert_allclose(axis_line_expected, axis_line_actual,
                                   rtol=rtol)

        # Assert ticks are correctly aligned:
        tickdir_expected = tickdirs_expected[i]
        tickdir_actual = axis._get_tickdir('default')
        np.testing.assert_array_equal(tickdir_expected, tickdir_actual)


@pytest.mark.parametrize("vertical_axis", ["x", "y", "z"])
def test_on_move_vertical_axis(vertical_axis: str) -> None:
    """
    Test vertical axis is respected when rotating the plot interactively.
    """
    ax = plt.subplot(1, 1, 1, projection="3d")
    ax.view_init(elev=0, azim=0, roll=0, vertical_axis=vertical_axis)
    ax.get_figure().canvas.draw()

    proj_before = ax.get_proj()
    event_click = mock_event(ax, button=MouseButton.LEFT, xdata=0, ydata=1)
    ax._button_press(event_click)

    event_move = mock_event(ax, button=MouseButton.LEFT, xdata=0.5, ydata=0.8)
    ax._on_move(event_move)

    assert ax._axis_names.index(vertical_axis) == ax._vertical_axis

    # Make sure plot has actually moved:
    proj_after = ax.get_proj()
    np.testing.assert_raises(
        AssertionError, np.testing.assert_allclose, proj_before, proj_after
    )


@pytest.mark.parametrize(
    "vertical_axis, aspect_expected",
    [
        ("x", [1.190476, 0.892857, 1.190476]),
        ("y", [0.892857, 1.190476, 1.190476]),
        ("z", [1.190476, 1.190476, 0.892857]),
    ],
)
def test_set_box_aspect_vertical_axis(vertical_axis, aspect_expected):
    ax = plt.subplot(1, 1, 1, projection="3d")
    ax.view_init(elev=0, azim=0, roll=0, vertical_axis=vertical_axis)
    ax.get_figure().canvas.draw()

    ax.set_box_aspect(None)

    np.testing.assert_allclose(aspect_expected, ax._box_aspect, rtol=1e-6)


@image_comparison(baseline_images=['arc_pathpatch.png'],
                  remove_text=True,
                  style='mpl20')
def test_arc_pathpatch():
    ax = plt.subplot(1, 1, 1, projection="3d")
    a = mpatch.Arc((0.5, 0.5), width=0.5, height=0.9,
                   angle=20, theta1=10, theta2=130)
    ax.add_patch(a)
    art3d.pathpatch_2d_to_3d(a, z=0, zdir='z')


@image_comparison(baseline_images=['panecolor_rcparams.png'],
                  remove_text=True,
                  style='mpl20')
def test_panecolor_rcparams():
    with plt.rc_context({'axes3d.xaxis.panecolor': 'r',
                         'axes3d.yaxis.panecolor': 'g',
                         'axes3d.zaxis.panecolor': 'b'}):
        fig = plt.figure(figsize=(1, 1))
        fig.add_subplot(projection='3d')


@check_figures_equal(extensions=["png"])
def test_mutating_input_arrays_y_and_z(fig_test, fig_ref):
    """
    Test to see if the `z` axis does not get mutated
    after a call to `Axes3D.plot`

    test cases came from GH#8990
    """
    ax1 = fig_test.add_subplot(111, projection='3d')
    x = [1, 2, 3]
    y = [0.0, 0.0, 0.0]
    z = [0.0, 0.0, 0.0]
    ax1.plot(x, y, z, 'o-')

    # mutate y,z to get a nontrivial line
    y[:] = [1, 2, 3]
    z[:] = [1, 2, 3]

    # draw the same plot without mutating x and y
    ax2 = fig_ref.add_subplot(111, projection='3d')
    x = [1, 2, 3]
    y = [0.0, 0.0, 0.0]
    z = [0.0, 0.0, 0.0]
    ax2.plot(x, y, z, 'o-')


def test_scatter_masked_color():
    """
    Test color parameter usage with non-finite coordinate arrays.

    GH#26236
    """

    x = [np.nan, 1, 2,  1]
    y = [0, np.inf, 2,  1]
    z = [0, 1, -np.inf, 1]
    colors = [
        [0.0, 0.0, 0.0, 1],
        [0.0, 0.0, 0.0, 1],
        [0.0, 0.0, 0.0, 1],
        [0.0, 0.0, 0.0, 1]
    ]

    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    path3d = ax.scatter(x, y, z, color=colors)

    # Assert sizes' equality
    assert len(path3d.get_offsets()) ==\
           len(super(type(path3d), path3d).get_facecolors())


@mpl3d_image_comparison(['surface3d_zsort_inf.png'], style='mpl20')
def test_surface3d_zsort_inf():
    plt.rcParams['axes3d.automargin'] = True  # Remove when image is regenerated
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')

    x, y = np.mgrid[-2:2:0.1, -2:2:0.1]
    z = np.sin(x)**2 + np.cos(y)**2
    z[x.shape[0] // 2:, x.shape[1] // 2:] = np.inf

    ax.plot_surface(x, y, z, cmap='jet')
    ax.view_init(elev=45, azim=145)


def test_Poly3DCollection_init_value_error():
    # smoke test to ensure the input check works
    # GH#26420
    with pytest.raises(ValueError,
                       match='You must provide facecolors, edgecolors, '
                        'or both for shade to work.'):
        poly = np.array([[0, 0, 1], [0, 1, 1], [0, 0, 0]], float)
        c = art3d.Poly3DCollection([poly], shade=True)


def test_ndarray_color_kwargs_value_error():
    # smoke test
    # ensures ndarray can be passed to color in kwargs for 3d projection plot
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.scatter(1, 0, 0, color=np.array([0, 0, 0, 1]))
    fig.canvas.draw()
