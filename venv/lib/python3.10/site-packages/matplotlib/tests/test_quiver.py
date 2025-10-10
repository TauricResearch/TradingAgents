import platform
import sys

import numpy as np
import pytest

from matplotlib import pyplot as plt
from matplotlib.testing.decorators import image_comparison
from matplotlib.testing.decorators import check_figures_equal


def draw_quiver(ax, **kwargs):
    X, Y = np.meshgrid(np.arange(0, 2 * np.pi, 1),
                       np.arange(0, 2 * np.pi, 1))
    U = np.cos(X)
    V = np.sin(Y)

    Q = ax.quiver(U, V, **kwargs)
    return Q


@pytest.mark.skipif(platform.python_implementation() != 'CPython',
                    reason='Requires CPython')
def test_quiver_memory_leak():
    fig, ax = plt.subplots()

    Q = draw_quiver(ax)
    ttX = Q.X
    orig_refcount = sys.getrefcount(ttX)
    Q.remove()

    del Q

    assert sys.getrefcount(ttX) < orig_refcount


@pytest.mark.skipif(platform.python_implementation() != 'CPython',
                    reason='Requires CPython')
def test_quiver_key_memory_leak():
    fig, ax = plt.subplots()

    Q = draw_quiver(ax)

    qk = ax.quiverkey(Q, 0.5, 0.92, 2, r'$2 \frac{m}{s}$',
                      labelpos='W',
                      fontproperties={'weight': 'bold'})
    orig_refcount = sys.getrefcount(qk)
    qk.remove()
    assert sys.getrefcount(qk) < orig_refcount


def test_quiver_number_of_args():
    X = [1, 2]
    with pytest.raises(
            TypeError,
            match='takes from 2 to 5 positional arguments but 1 were given'):
        plt.quiver(X)
    with pytest.raises(
            TypeError,
            match='takes from 2 to 5 positional arguments but 6 were given'):
        plt.quiver(X, X, X, X, X, X)


def test_quiver_arg_sizes():
    X2 = [1, 2]
    X3 = [1, 2, 3]
    with pytest.raises(
            ValueError, match=('X and Y must be the same size, but '
                               'X.size is 2 and Y.size is 3.')):
        plt.quiver(X2, X3, X2, X2)
    with pytest.raises(
            ValueError, match=('Argument U has a size 3 which does not match '
                               '2, the number of arrow positions')):
        plt.quiver(X2, X2, X3, X2)
    with pytest.raises(
            ValueError, match=('Argument V has a size 3 which does not match '
                               '2, the number of arrow positions')):
        plt.quiver(X2, X2, X2, X3)
    with pytest.raises(
            ValueError, match=('Argument C has a size 3 which does not match '
                               '2, the number of arrow positions')):
        plt.quiver(X2, X2, X2, X2, X3)


def test_no_warnings():
    fig, ax = plt.subplots()
    X, Y = np.meshgrid(np.arange(15), np.arange(10))
    U = V = np.ones_like(X)
    phi = (np.random.rand(15, 10) - .5) * 150
    ax.quiver(X, Y, U, V, angles=phi)
    fig.canvas.draw()  # Check that no warning is emitted.


def test_zero_headlength():
    # Based on report by Doug McNeil:
    # https://discourse.matplotlib.org/t/quiver-warnings/16722
    fig, ax = plt.subplots()
    X, Y = np.meshgrid(np.arange(10), np.arange(10))
    U, V = np.cos(X), np.sin(Y)
    ax.quiver(U, V, headlength=0, headaxislength=0)
    fig.canvas.draw()  # Check that no warning is emitted.


@image_comparison(['quiver_animated_test_image.png'])
def test_quiver_animate():
    # Tests fix for #2616
    fig, ax = plt.subplots()
    Q = draw_quiver(ax, animated=True)
    ax.quiverkey(Q, 0.5, 0.92, 2, r'$2 \frac{m}{s}$',
                 labelpos='W', fontproperties={'weight': 'bold'})


@image_comparison(['quiver_with_key_test_image.png'])
def test_quiver_with_key():
    fig, ax = plt.subplots()
    ax.margins(0.1)
    Q = draw_quiver(ax)
    ax.quiverkey(Q, 0.5, 0.95, 2,
                 r'$2\, \mathrm{m}\, \mathrm{s}^{-1}$',
                 angle=-10,
                 coordinates='figure',
                 labelpos='W',
                 fontproperties={'weight': 'bold', 'size': 'large'})


@image_comparison(['quiver_single_test_image.png'], remove_text=True)
def test_quiver_single():
    fig, ax = plt.subplots()
    ax.margins(0.1)
    ax.quiver([1], [1], [2], [2])


def test_quiver_copy():
    fig, ax = plt.subplots()
    uv = dict(u=np.array([1.1]), v=np.array([2.0]))
    q0 = ax.quiver([1], [1], uv['u'], uv['v'])
    uv['v'][0] = 0
    assert q0.V[0] == 2.0


@image_comparison(['quiver_key_pivot.png'], remove_text=True)
def test_quiver_key_pivot():
    fig, ax = plt.subplots()

    u, v = np.mgrid[0:2*np.pi:10j, 0:2*np.pi:10j]

    q = ax.quiver(np.sin(u), np.cos(v))
    ax.set_xlim(-2, 11)
    ax.set_ylim(-2, 11)
    ax.quiverkey(q, 0.5, 1, 1, 'N', labelpos='N')
    ax.quiverkey(q, 1, 0.5, 1, 'E', labelpos='E')
    ax.quiverkey(q, 0.5, 0, 1, 'S', labelpos='S')
    ax.quiverkey(q, 0, 0.5, 1, 'W', labelpos='W')


@image_comparison(['quiver_key_xy.png'], remove_text=True)
def test_quiver_key_xy():
    # With scale_units='xy', ensure quiverkey still matches its quiver.
    # Note that the quiver and quiverkey lengths depend on the axes aspect
    # ratio, and that with angles='xy' their angles also depend on the axes
    # aspect ratio.
    X = np.arange(8)
    Y = np.zeros(8)
    angles = X * (np.pi / 4)
    uv = np.exp(1j * angles)
    U = uv.real
    V = uv.imag
    fig, axs = plt.subplots(2)
    for ax, angle_str in zip(axs, ('uv', 'xy')):
        ax.set_xlim(-1, 8)
        ax.set_ylim(-0.2, 0.2)
        q = ax.quiver(X, Y, U, V, pivot='middle',
                      units='xy', width=0.05,
                      scale=2, scale_units='xy',
                      angles=angle_str)
        for x, angle in zip((0.2, 0.5, 0.8), (0, 45, 90)):
            ax.quiverkey(q, X=x, Y=0.8, U=1, angle=angle, label='', color='b')


@image_comparison(['barbs_test_image.png'], remove_text=True)
def test_barbs():
    x = np.linspace(-5, 5, 5)
    X, Y = np.meshgrid(x, x)
    U, V = 12*X, 12*Y
    fig, ax = plt.subplots()
    ax.barbs(X, Y, U, V, np.hypot(U, V), fill_empty=True, rounding=False,
             sizes=dict(emptybarb=0.25, spacing=0.2, height=0.3),
             cmap='viridis')


@image_comparison(['barbs_pivot_test_image.png'], remove_text=True)
def test_barbs_pivot():
    x = np.linspace(-5, 5, 5)
    X, Y = np.meshgrid(x, x)
    U, V = 12*X, 12*Y
    fig, ax = plt.subplots()
    ax.barbs(X, Y, U, V, fill_empty=True, rounding=False, pivot=1.7,
             sizes=dict(emptybarb=0.25, spacing=0.2, height=0.3))
    ax.scatter(X, Y, s=49, c='black')


@image_comparison(['barbs_test_flip.png'], remove_text=True)
def test_barbs_flip():
    """Test barbs with an array for flip_barb."""
    x = np.linspace(-5, 5, 5)
    X, Y = np.meshgrid(x, x)
    U, V = 12*X, 12*Y
    fig, ax = plt.subplots()
    ax.barbs(X, Y, U, V, fill_empty=True, rounding=False, pivot=1.7,
             sizes=dict(emptybarb=0.25, spacing=0.2, height=0.3),
             flip_barb=Y < 0)


def test_barb_copy():
    fig, ax = plt.subplots()
    u = np.array([1.1])
    v = np.array([2.2])
    b0 = ax.barbs([1], [1], u, v)
    u[0] = 0
    assert b0.u[0] == 1.1
    v[0] = 0
    assert b0.v[0] == 2.2


def test_bad_masked_sizes():
    """Test error handling when given differing sized masked arrays."""
    x = np.arange(3)
    y = np.arange(3)
    u = np.ma.array(15. * np.ones((4,)))
    v = np.ma.array(15. * np.ones_like(u))
    u[1] = np.ma.masked
    v[1] = np.ma.masked
    fig, ax = plt.subplots()
    with pytest.raises(ValueError):
        ax.barbs(x, y, u, v)


def test_angles_and_scale():
    # angles array + scale_units kwarg
    fig, ax = plt.subplots()
    X, Y = np.meshgrid(np.arange(15), np.arange(10))
    U = V = np.ones_like(X)
    phi = (np.random.rand(15, 10) - .5) * 150
    ax.quiver(X, Y, U, V, angles=phi, scale_units='xy')


@image_comparison(['quiver_xy.png'], remove_text=True)
def test_quiver_xy():
    # simple arrow pointing from SW to NE
    fig, ax = plt.subplots(subplot_kw=dict(aspect='equal'))
    ax.quiver(0, 0, 1, 1, angles='xy', scale_units='xy', scale=1)
    ax.set_xlim(0, 1.1)
    ax.set_ylim(0, 1.1)
    ax.grid()


def test_quiverkey_angles():
    # Check that only a single arrow is plotted for a quiverkey when an array
    # of angles is given to the original quiver plot
    fig, ax = plt.subplots()

    X, Y = np.meshgrid(np.arange(2), np.arange(2))
    U = V = angles = np.ones_like(X)

    q = ax.quiver(X, Y, U, V, angles=angles)
    qk = ax.quiverkey(q, 1, 1, 2, 'Label')
    # The arrows are only created when the key is drawn
    fig.canvas.draw()
    assert len(qk.verts) == 1


def test_quiverkey_angles_xy_aitoff():
    # GH 26316 and GH 26748
    # Test that only one arrow will be plotted with non-cartesian
    # when angles='xy' and/or scale_units='xy'

    # only for test purpose
    # scale_units='xy' may not be a valid use case for non-cartesian
    kwargs_list = [
        {'angles': 'xy'},
        {'angles': 'xy', 'scale_units': 'xy'},
        {'scale_units': 'xy'}
    ]

    for kwargs_dict in kwargs_list:

        x = np.linspace(-np.pi, np.pi, 11)
        y = np.ones_like(x) * np.pi / 6
        vx = np.zeros_like(x)
        vy = np.ones_like(x)

        fig = plt.figure()
        ax = fig.add_subplot(projection='aitoff')
        q = ax.quiver(x, y, vx, vy, **kwargs_dict)
        qk = ax.quiverkey(q, 0, 0, 1, '1 units')

        fig.canvas.draw()
        assert len(qk.verts) == 1


def test_quiverkey_angles_scale_units_cartesian():
    # GH 26316
    # Test that only one arrow will be plotted with normal cartesian
    # when angles='xy' and/or scale_units='xy'

    kwargs_list = [
        {'angles': 'xy'},
        {'angles': 'xy', 'scale_units': 'xy'},
        {'scale_units': 'xy'}
    ]

    for kwargs_dict in kwargs_list:
        X = [0, -1, 0]
        Y = [0, -1, 0]
        U = [1, -1, 1]
        V = [1, -1, 0]

        fig, ax = plt.subplots()
        q = ax.quiver(X, Y, U, V, **kwargs_dict)
        ax.quiverkey(q, X=0.3, Y=1.1, U=1,
                     label='Quiver key, length = 1', labelpos='E')
        qk = ax.quiverkey(q, 0, 0, 1, '1 units')

        fig.canvas.draw()
        assert len(qk.verts) == 1


def test_quiver_setuvc_numbers():
    """Check that it is possible to set all arrow UVC to the same numbers"""

    fig, ax = plt.subplots()

    X, Y = np.meshgrid(np.arange(2), np.arange(2))
    U = V = np.ones_like(X)

    q = ax.quiver(X, Y, U, V)
    q.set_UVC(0, 1)


def draw_quiverkey_zorder_argument(fig, zorder=None):
    """Draw Quiver and QuiverKey using zorder argument"""
    x = np.arange(1, 6, 1)
    y = np.arange(1, 6, 1)
    X, Y = np.meshgrid(x, y)
    U, V = 2, 2

    ax = fig.subplots()
    q = ax.quiver(X, Y, U, V, pivot='middle')
    ax.set_xlim(0.5, 5.5)
    ax.set_ylim(0.5, 5.5)
    if zorder is None:
        ax.quiverkey(q, 4, 4, 25, coordinates='data',
                     label='U', color='blue')
        ax.quiverkey(q, 5.5, 2, 20, coordinates='data',
                     label='V', color='blue', angle=90)
    else:
        ax.quiverkey(q, 4, 4, 25, coordinates='data',
                     label='U', color='blue', zorder=zorder)
        ax.quiverkey(q, 5.5, 2, 20, coordinates='data',
                     label='V', color='blue', angle=90, zorder=zorder)


def draw_quiverkey_setzorder(fig, zorder=None):
    """Draw Quiver and QuiverKey using set_zorder"""
    x = np.arange(1, 6, 1)
    y = np.arange(1, 6, 1)
    X, Y = np.meshgrid(x, y)
    U, V = 2, 2

    ax = fig.subplots()
    q = ax.quiver(X, Y, U, V, pivot='middle')
    ax.set_xlim(0.5, 5.5)
    ax.set_ylim(0.5, 5.5)
    qk1 = ax.quiverkey(q, 4, 4, 25, coordinates='data',
                       label='U', color='blue')
    qk2 = ax.quiverkey(q, 5.5, 2, 20, coordinates='data',
                       label='V', color='blue', angle=90)
    if zorder is not None:
        qk1.set_zorder(zorder)
        qk2.set_zorder(zorder)


@pytest.mark.parametrize('zorder', [0, 2, 5, None])
@check_figures_equal(extensions=['png'])
def test_quiverkey_zorder(fig_test, fig_ref, zorder):
    draw_quiverkey_zorder_argument(fig_test, zorder=zorder)
    draw_quiverkey_setzorder(fig_ref, zorder=zorder)
