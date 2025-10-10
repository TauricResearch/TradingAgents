import platform

import numpy as np

import matplotlib as mpl
from matplotlib.colors import same_color
from matplotlib.testing.decorators import image_comparison
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import art3d


@image_comparison(['legend_plot.png'], remove_text=True, style='mpl20')
def test_legend_plot():
    fig, ax = plt.subplots(subplot_kw=dict(projection='3d'))
    x = np.arange(10)
    ax.plot(x, 5 - x, 'o', zdir='y', label='z=1')
    ax.plot(x, x - 5, 'o', zdir='y', label='z=-1')
    ax.legend()


@image_comparison(['legend_bar.png'], remove_text=True, style='mpl20')
def test_legend_bar():
    fig, ax = plt.subplots(subplot_kw=dict(projection='3d'))
    x = np.arange(10)
    b1 = ax.bar(x, x, zdir='y', align='edge', color='m')
    b2 = ax.bar(x, x[::-1], zdir='x', align='edge', color='g')
    ax.legend([b1[0], b2[0]], ['up', 'down'])


@image_comparison(['fancy.png'], remove_text=True, style='mpl20',
                  tol=0 if platform.machine() == 'x86_64' else 0.011)
def test_fancy():
    fig, ax = plt.subplots(subplot_kw=dict(projection='3d'))
    ax.plot(np.arange(10), np.full(10, 5), np.full(10, 5), 'o--', label='line')
    ax.scatter(np.arange(10), np.arange(10, 0, -1), label='scatter')
    ax.errorbar(np.full(10, 5), np.arange(10), np.full(10, 10),
                xerr=0.5, zerr=0.5, label='errorbar')
    ax.legend(loc='lower left', ncols=2, title='My legend', numpoints=1)


def test_linecollection_scaled_dashes():
    lines1 = [[(0, .5), (.5, 1)], [(.3, .6), (.2, .2)]]
    lines2 = [[[0.7, .2], [.8, .4]], [[.5, .7], [.6, .1]]]
    lines3 = [[[0.6, .2], [.8, .4]], [[.5, .7], [.1, .1]]]
    lc1 = art3d.Line3DCollection(lines1, linestyles="--", lw=3)
    lc2 = art3d.Line3DCollection(lines2, linestyles="-.")
    lc3 = art3d.Line3DCollection(lines3, linestyles=":", lw=.5)

    fig, ax = plt.subplots(subplot_kw=dict(projection='3d'))
    ax.add_collection(lc1)
    ax.add_collection(lc2)
    ax.add_collection(lc3)

    leg = ax.legend([lc1, lc2, lc3], ['line1', 'line2', 'line 3'])
    h1, h2, h3 = leg.legend_handles

    for oh, lh in zip((lc1, lc2, lc3), (h1, h2, h3)):
        assert oh.get_linestyles()[0] == lh._dash_pattern


def test_handlerline3d():
    # Test marker consistency for monolithic Line3D legend handler.
    fig, ax = plt.subplots(subplot_kw=dict(projection='3d'))
    ax.scatter([0, 1], [0, 1], marker="v")
    handles = [art3d.Line3D([0], [0], [0], marker="v")]
    leg = ax.legend(handles, ["Aardvark"], numpoints=1)
    assert handles[0].get_marker() == leg.legend_handles[0].get_marker()


def test_contour_legend_elements():
    x, y = np.mgrid[1:10, 1:10]
    h = x * y
    colors = ['blue', '#00FF00', 'red']

    fig, ax = plt.subplots(subplot_kw=dict(projection='3d'))
    cs = ax.contour(x, y, h, levels=[10, 30, 50], colors=colors, extend='both')

    artists, labels = cs.legend_elements()
    assert labels == ['$x = 10.0$', '$x = 30.0$', '$x = 50.0$']
    assert all(isinstance(a, mpl.lines.Line2D) for a in artists)
    assert all(same_color(a.get_color(), c)
               for a, c in zip(artists, colors))


def test_contourf_legend_elements():
    x, y = np.mgrid[1:10, 1:10]
    h = x * y

    fig, ax = plt.subplots(subplot_kw=dict(projection='3d'))
    cs = ax.contourf(x, y, h, levels=[10, 30, 50],
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
    assert all(isinstance(a, mpl.patches.Rectangle) for a in artists)
    assert all(same_color(a.get_facecolor(), c)
               for a, c in zip(artists, expected_colors))


def test_legend_Poly3dCollection():

    verts = np.asarray([[0, 0, 0], [0, 1, 1], [1, 0, 1]])
    mesh = art3d.Poly3DCollection([verts], label="surface")

    fig, ax = plt.subplots(subplot_kw={"projection": "3d"})
    mesh.set_edgecolor('k')
    handle = ax.add_collection3d(mesh)
    leg = ax.legend()
    assert (leg.legend_handles[0].get_facecolor()
            == handle.get_facecolor()).all()
