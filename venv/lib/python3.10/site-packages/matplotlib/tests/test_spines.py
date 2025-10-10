import numpy as np
import pytest

import matplotlib.pyplot as plt
from matplotlib.spines import Spines
from matplotlib.testing.decorators import check_figures_equal, image_comparison


def test_spine_class():
    """Test Spines and SpinesProxy in isolation."""
    class SpineMock:
        def __init__(self):
            self.val = None

        def set(self, **kwargs):
            vars(self).update(kwargs)

        def set_val(self, val):
            self.val = val

    spines_dict = {
        'left': SpineMock(),
        'right': SpineMock(),
        'top': SpineMock(),
        'bottom': SpineMock(),
    }
    spines = Spines(**spines_dict)

    assert spines['left'] is spines_dict['left']
    assert spines.left is spines_dict['left']

    spines[['left', 'right']].set_val('x')
    assert spines.left.val == 'x'
    assert spines.right.val == 'x'
    assert spines.top.val is None
    assert spines.bottom.val is None

    spines[:].set_val('y')
    assert all(spine.val == 'y' for spine in spines.values())

    spines[:].set(foo='bar')
    assert all(spine.foo == 'bar' for spine in spines.values())

    with pytest.raises(AttributeError, match='foo'):
        spines.foo
    with pytest.raises(KeyError, match='foo'):
        spines['foo']
    with pytest.raises(KeyError, match='foo, bar'):
        spines[['left', 'foo', 'right', 'bar']]
    with pytest.raises(ValueError, match='single list'):
        spines['left', 'right']
    with pytest.raises(ValueError, match='Spines does not support slicing'):
        spines['left':'right']
    with pytest.raises(ValueError, match='Spines does not support slicing'):
        spines['top':]


@image_comparison(['spines_axes_positions.png'])
def test_spines_axes_positions():
    # SF bug 2852168
    fig = plt.figure()
    x = np.linspace(0, 2*np.pi, 100)
    y = 2*np.sin(x)
    ax = fig.add_subplot(1, 1, 1)
    ax.set_title('centered spines')
    ax.plot(x, y)
    ax.spines.right.set_position(('axes', 0.1))
    ax.yaxis.set_ticks_position('right')
    ax.spines.top.set_position(('axes', 0.25))
    ax.xaxis.set_ticks_position('top')
    ax.spines.left.set_color('none')
    ax.spines.bottom.set_color('none')


@image_comparison(['spines_data_positions.png'])
def test_spines_data_positions():
    fig, ax = plt.subplots()
    ax.spines.left.set_position(('data', -1.5))
    ax.spines.top.set_position(('data', 0.5))
    ax.spines.right.set_position(('data', -0.5))
    ax.spines.bottom.set_position('zero')
    ax.set_xlim([-2, 2])
    ax.set_ylim([-2, 2])


@check_figures_equal(extensions=["png"])
def test_spine_nonlinear_data_positions(fig_test, fig_ref):
    plt.style.use("default")

    ax = fig_test.add_subplot()
    ax.set(xscale="log", xlim=(.1, 1))
    # Use position="data" to visually swap the left and right spines, using
    # linewidth to distinguish them.  The calls to tick_params removes labels
    # (for image comparison purposes) and harmonizes tick positions with the
    # reference).
    ax.spines.left.set_position(("data", 1))
    ax.spines.left.set_linewidth(2)
    ax.spines.right.set_position(("data", .1))
    ax.tick_params(axis="y", labelleft=False, direction="in")

    ax = fig_ref.add_subplot()
    ax.set(xscale="log", xlim=(.1, 1))
    ax.spines.right.set_linewidth(2)
    ax.tick_params(axis="y", labelleft=False, left=False, right=True)


@image_comparison(['spines_capstyle.png'])
def test_spines_capstyle():
    # issue 2542
    plt.rc('axes', linewidth=20)
    fig, ax = plt.subplots()
    ax.set_xticks([])
    ax.set_yticks([])


def test_label_without_ticks():
    fig, ax = plt.subplots()
    plt.subplots_adjust(left=0.3, bottom=0.3)
    ax.plot(np.arange(10))
    ax.yaxis.set_ticks_position('left')
    ax.spines.left.set_position(('outward', 30))
    ax.spines.right.set_visible(False)
    ax.set_ylabel('y label')
    ax.xaxis.set_ticks_position('bottom')
    ax.spines.bottom.set_position(('outward', 30))
    ax.spines.top.set_visible(False)
    ax.set_xlabel('x label')
    ax.xaxis.set_ticks([])
    ax.yaxis.set_ticks([])
    plt.draw()

    spine = ax.spines.left
    spinebbox = spine.get_transform().transform_path(
        spine.get_path()).get_extents()
    assert ax.yaxis.label.get_position()[0] < spinebbox.xmin, \
        "Y-Axis label not left of the spine"

    spine = ax.spines.bottom
    spinebbox = spine.get_transform().transform_path(
        spine.get_path()).get_extents()
    assert ax.xaxis.label.get_position()[1] < spinebbox.ymin, \
        "X-Axis label not below the spine"


@image_comparison(['black_axes.png'])
def test_spines_black_axes():
    # GitHub #18804
    plt.rcParams["savefig.pad_inches"] = 0
    plt.rcParams["savefig.bbox"] = 'tight'
    fig = plt.figure(0, figsize=(4, 4))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xticklabels([])
    ax.set_yticklabels([])
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_facecolor((0, 0, 0))


def test_arc_spine_inner_no_axis():
    # Backcompat: smoke test that inner arc spine does not need a registered
    # axis in order to be drawn
    fig = plt.figure()
    ax = fig.add_subplot(projection="polar")
    inner_spine = ax.spines["inner"]
    inner_spine.register_axis(None)
    assert ax.spines["inner"].axis is None

    fig.draw_without_rendering()
