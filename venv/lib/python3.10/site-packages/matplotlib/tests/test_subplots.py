import itertools
import platform

import numpy as np
import pytest

import matplotlib as mpl
from matplotlib.axes import Axes, SubplotBase
import matplotlib.pyplot as plt
from matplotlib.testing.decorators import check_figures_equal, image_comparison


def check_shared(axs, x_shared, y_shared):
    """
    x_shared and y_shared are n x n boolean matrices; entry (i, j) indicates
    whether the x (or y) axes of subplots i and j should be shared.
    """
    for (i1, ax1), (i2, ax2), (i3, (name, shared)) in itertools.product(
            enumerate(axs),
            enumerate(axs),
            enumerate(zip("xy", [x_shared, y_shared]))):
        if i2 <= i1:
            continue
        assert axs[0]._shared_axes[name].joined(ax1, ax2) == shared[i1, i2], \
            "axes %i and %i incorrectly %ssharing %s axis" % (
                i1, i2, "not " if shared[i1, i2] else "", name)


def check_ticklabel_visible(axs, x_visible, y_visible):
    """Check that the x and y ticklabel visibility is as specified."""
    for i, (ax, vx, vy) in enumerate(zip(axs, x_visible, y_visible)):
        for l in ax.get_xticklabels() + [ax.xaxis.offsetText]:
            assert l.get_visible() == vx, \
                    f"Visibility of x axis #{i} is incorrectly {vx}"
        for l in ax.get_yticklabels() + [ax.yaxis.offsetText]:
            assert l.get_visible() == vy, \
                    f"Visibility of y axis #{i} is incorrectly {vy}"
        # axis label "visibility" is toggled by label_outer by resetting the
        # label to empty, but it can also be empty to start with.
        if not vx:
            assert ax.get_xlabel() == ""
        if not vy:
            assert ax.get_ylabel() == ""


def check_tick1_visible(axs, x_visible, y_visible):
    """
    Check that the x and y tick visibility is as specified.

    Note: This only checks the tick1line, i.e. bottom / left ticks.
    """
    for ax, visible, in zip(axs, x_visible):
        for tick in ax.xaxis.get_major_ticks():
            assert tick.tick1line.get_visible() == visible
    for ax, y_visible, in zip(axs, y_visible):
        for tick in ax.yaxis.get_major_ticks():
            assert tick.tick1line.get_visible() == visible


def test_shared():
    rdim = (4, 4, 2)
    share = {
            'all': np.ones(rdim[:2], dtype=bool),
            'none': np.zeros(rdim[:2], dtype=bool),
            'row': np.array([
                [False, True, False, False],
                [True, False, False, False],
                [False, False, False, True],
                [False, False, True, False]]),
            'col': np.array([
                [False, False, True, False],
                [False, False, False, True],
                [True, False, False, False],
                [False, True, False, False]]),
            }
    visible = {
            'x': {
                'all': [False, False, True, True],
                'col': [False, False, True, True],
                'row': [True] * 4,
                'none': [True] * 4,
                False: [True] * 4,
                True: [False, False, True, True],
                },
            'y': {
                'all': [True, False, True, False],
                'col': [True] * 4,
                'row': [True, False, True, False],
                'none': [True] * 4,
                False: [True] * 4,
                True: [True, False, True, False],
                },
            }
    share[False] = share['none']
    share[True] = share['all']

    # test default
    f, ((a1, a2), (a3, a4)) = plt.subplots(2, 2)
    axs = [a1, a2, a3, a4]
    check_shared(axs, share['none'], share['none'])
    plt.close(f)

    # test all option combinations
    ops = [False, True, 'all', 'none', 'row', 'col', 0, 1]
    for xo in ops:
        for yo in ops:
            f, ((a1, a2), (a3, a4)) = plt.subplots(2, 2, sharex=xo, sharey=yo)
            axs = [a1, a2, a3, a4]
            check_shared(axs, share[xo], share[yo])
            check_ticklabel_visible(axs, visible['x'][xo], visible['y'][yo])
            plt.close(f)


@pytest.mark.parametrize('remove_ticks', [True, False])
@pytest.mark.parametrize('layout_engine', ['none', 'tight', 'constrained'])
@pytest.mark.parametrize('with_colorbar', [True, False])
def test_label_outer(remove_ticks, layout_engine, with_colorbar):
    fig = plt.figure(layout=layout_engine)
    axs = fig.subplots(2, 2, sharex=True, sharey=True)
    for ax in axs.flat:
        ax.set(xlabel="foo", ylabel="bar")
        if with_colorbar:
            fig.colorbar(mpl.cm.ScalarMappable(), ax=ax)
        ax.label_outer(remove_inner_ticks=remove_ticks)
    check_ticklabel_visible(
        axs.flat, [False, False, True, True], [True, False, True, False])
    if remove_ticks:
        check_tick1_visible(
            axs.flat, [False, False, True, True], [True, False, True, False])
    else:
        check_tick1_visible(
            axs.flat, [True, True, True, True], [True, True, True, True])


def test_label_outer_span():
    fig = plt.figure()
    gs = fig.add_gridspec(3, 3)
    # +---+---+---+
    # |   1   |   |
    # +---+---+---+
    # |   |   | 3 |
    # + 2 +---+---+
    # |   | 4 |   |
    # +---+---+---+
    a1 = fig.add_subplot(gs[0, 0:2])
    a2 = fig.add_subplot(gs[1:3, 0])
    a3 = fig.add_subplot(gs[1, 2])
    a4 = fig.add_subplot(gs[2, 1])
    for ax in fig.axes:
        ax.label_outer()
    check_ticklabel_visible(
        fig.axes, [False, True, False, True], [True, True, False, False])


def test_label_outer_non_gridspec():
    ax = plt.axes((0, 0, 1, 1))
    ax.label_outer()  # Does nothing.
    check_ticklabel_visible([ax], [True], [True])


def test_shared_and_moved():
    # test if sharey is on, but then tick_left is called that labels don't
    # re-appear.  Seaborn does this just to be sure yaxis is on left...
    f, (a1, a2) = plt.subplots(1, 2, sharey=True)
    check_ticklabel_visible([a2], [True], [False])
    a2.yaxis.tick_left()
    check_ticklabel_visible([a2], [True], [False])

    f, (a1, a2) = plt.subplots(2, 1, sharex=True)
    check_ticklabel_visible([a1], [False], [True])
    a2.xaxis.tick_bottom()
    check_ticklabel_visible([a1], [False], [True])


def test_exceptions():
    # TODO should this test more options?
    with pytest.raises(ValueError):
        plt.subplots(2, 2, sharex='blah')
    with pytest.raises(ValueError):
        plt.subplots(2, 2, sharey='blah')


@image_comparison(['subplots_offset_text.png'],
                  tol=0 if platform.machine() == 'x86_64' else 0.028)
def test_subplots_offsettext():
    x = np.arange(0, 1e10, 1e9)
    y = np.arange(0, 100, 10)+1e4
    fig, axs = plt.subplots(2, 2, sharex='col', sharey='all')
    axs[0, 0].plot(x, x)
    axs[1, 0].plot(x, x)
    axs[0, 1].plot(y, x)
    axs[1, 1].plot(y, x)


@pytest.mark.parametrize("top", [True, False])
@pytest.mark.parametrize("bottom", [True, False])
@pytest.mark.parametrize("left", [True, False])
@pytest.mark.parametrize("right", [True, False])
def test_subplots_hide_ticklabels(top, bottom, left, right):
    # Ideally, we would also test offset-text visibility (and remove
    # test_subplots_offsettext), but currently, setting rcParams fails to move
    # the offset texts as well.
    with plt.rc_context({"xtick.labeltop": top, "xtick.labelbottom": bottom,
                         "ytick.labelleft": left, "ytick.labelright": right}):
        axs = plt.figure().subplots(3, 3, sharex=True, sharey=True)
    for (i, j), ax in np.ndenumerate(axs):
        xtop = ax.xaxis._major_tick_kw["label2On"]
        xbottom = ax.xaxis._major_tick_kw["label1On"]
        yleft = ax.yaxis._major_tick_kw["label1On"]
        yright = ax.yaxis._major_tick_kw["label2On"]
        assert xtop == (top and i == 0)
        assert xbottom == (bottom and i == 2)
        assert yleft == (left and j == 0)
        assert yright == (right and j == 2)


@pytest.mark.parametrize("xlabel_position", ["bottom", "top"])
@pytest.mark.parametrize("ylabel_position", ["left", "right"])
def test_subplots_hide_axislabels(xlabel_position, ylabel_position):
    axs = plt.figure().subplots(3, 3, sharex=True, sharey=True)
    for (i, j), ax in np.ndenumerate(axs):
        ax.set(xlabel="foo", ylabel="bar")
        ax.xaxis.set_label_position(xlabel_position)
        ax.yaxis.set_label_position(ylabel_position)
        ax.label_outer()
        assert bool(ax.get_xlabel()) == (
            xlabel_position == "bottom" and i == 2
            or xlabel_position == "top" and i == 0)
        assert bool(ax.get_ylabel()) == (
            ylabel_position == "left" and j == 0
            or ylabel_position == "right" and j == 2)


def test_get_gridspec():
    # ahem, pretty trivial, but...
    fig, ax = plt.subplots()
    assert ax.get_subplotspec().get_gridspec() == ax.get_gridspec()


def test_dont_mutate_kwargs():
    subplot_kw = {'sharex': 'all'}
    gridspec_kw = {'width_ratios': [1, 2]}
    fig, ax = plt.subplots(1, 2, subplot_kw=subplot_kw,
                           gridspec_kw=gridspec_kw)
    assert subplot_kw == {'sharex': 'all'}
    assert gridspec_kw == {'width_ratios': [1, 2]}


@pytest.mark.parametrize("width_ratios", [None, [1, 3, 2]])
@pytest.mark.parametrize("height_ratios", [None, [1, 2]])
@check_figures_equal(extensions=['png'])
def test_width_and_height_ratios(fig_test, fig_ref,
                                 height_ratios, width_ratios):
    fig_test.subplots(2, 3, height_ratios=height_ratios,
                      width_ratios=width_ratios)
    fig_ref.subplots(2, 3, gridspec_kw={
                     'height_ratios': height_ratios,
                     'width_ratios': width_ratios})


@pytest.mark.parametrize("width_ratios", [None, [1, 3, 2]])
@pytest.mark.parametrize("height_ratios", [None, [1, 2]])
@check_figures_equal(extensions=['png'])
def test_width_and_height_ratios_mosaic(fig_test, fig_ref,
                                        height_ratios, width_ratios):
    mosaic_spec = [['A', 'B', 'B'], ['A', 'C', 'D']]
    fig_test.subplot_mosaic(mosaic_spec, height_ratios=height_ratios,
                            width_ratios=width_ratios)
    fig_ref.subplot_mosaic(mosaic_spec, gridspec_kw={
                           'height_ratios': height_ratios,
                           'width_ratios': width_ratios})


@pytest.mark.parametrize('method,args', [
    ('subplots', (2, 3)),
    ('subplot_mosaic', ('abc;def', ))
    ]
)
def test_ratio_overlapping_kws(method, args):
    with pytest.raises(ValueError, match='height_ratios'):
        getattr(plt, method)(*args, height_ratios=[1, 2],
                             gridspec_kw={'height_ratios': [1, 2]})
    with pytest.raises(ValueError, match='width_ratios'):
        getattr(plt, method)(*args, width_ratios=[1, 2, 3],
                             gridspec_kw={'width_ratios': [1, 2, 3]})


def test_old_subplot_compat():
    fig = plt.figure()
    assert isinstance(fig.add_subplot(), SubplotBase)
    assert not isinstance(fig.add_axes(rect=[0, 0, 1, 1]), SubplotBase)
    with pytest.raises(TypeError):
        Axes(fig, [0, 0, 1, 1], rect=[0, 0, 1, 1])
