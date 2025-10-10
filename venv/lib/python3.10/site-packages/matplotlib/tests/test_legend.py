import collections
import io
import itertools
import platform
import time
from unittest import mock
import warnings

import numpy as np
from numpy.testing import assert_allclose
import pytest

from matplotlib.testing.decorators import check_figures_equal, image_comparison
from matplotlib.testing._markers import needs_usetex
import matplotlib.pyplot as plt
import matplotlib as mpl
import matplotlib.patches as mpatches
import matplotlib.transforms as mtransforms
import matplotlib.collections as mcollections
import matplotlib.lines as mlines
from matplotlib.legend_handler import HandlerTuple
import matplotlib.legend as mlegend
from matplotlib import rc_context
from matplotlib.font_manager import FontProperties


def test_legend_ordereddict():
    # smoketest that ordereddict inputs work...

    X = np.random.randn(10)
    Y = np.random.randn(10)
    labels = ['a'] * 5 + ['b'] * 5
    colors = ['r'] * 5 + ['g'] * 5

    fig, ax = plt.subplots()
    for x, y, label, color in zip(X, Y, labels, colors):
        ax.scatter(x, y, label=label, c=color)

    handles, labels = ax.get_legend_handles_labels()
    legend = collections.OrderedDict(zip(labels, handles))
    ax.legend(legend.values(), legend.keys(),
              loc='center left', bbox_to_anchor=(1, .5))


def test_legend_generator():
    # smoketest that generator inputs work
    fig, ax = plt.subplots()
    ax.plot([0, 1])
    ax.plot([0, 2])

    handles = (line for line in ax.get_lines())
    labels = (label for label in ['spam', 'eggs'])

    ax.legend(handles, labels, loc='upper left')


@image_comparison(['legend_auto1.png'], remove_text=True)
def test_legend_auto1():
    """Test automatic legend placement"""
    fig, ax = plt.subplots()
    x = np.arange(100)
    ax.plot(x, 50 - x, 'o', label='y=1')
    ax.plot(x, x - 50, 'o', label='y=-1')
    ax.legend(loc='best')


@image_comparison(['legend_auto2.png'], remove_text=True)
def test_legend_auto2():
    """Test automatic legend placement"""
    fig, ax = plt.subplots()
    x = np.arange(100)
    b1 = ax.bar(x, x, align='edge', color='m')
    b2 = ax.bar(x, x[::-1], align='edge', color='g')
    ax.legend([b1[0], b2[0]], ['up', 'down'], loc='best')


@image_comparison(['legend_auto3.png'])
def test_legend_auto3():
    """Test automatic legend placement"""
    fig, ax = plt.subplots()
    x = [0.9, 0.1, 0.1, 0.9, 0.9, 0.5]
    y = [0.95, 0.95, 0.05, 0.05, 0.5, 0.5]
    ax.plot(x, y, 'o-', label='line')
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.legend(loc='best')


def test_legend_auto4():
    """
    Check that the legend location with automatic placement is the same,
    whatever the histogram type is. Related to issue #9580.
    """
    # NB: barstacked is pointless with a single dataset.
    fig, axs = plt.subplots(ncols=3, figsize=(6.4, 2.4))
    leg_bboxes = []
    for ax, ht in zip(axs.flat, ('bar', 'step', 'stepfilled')):
        ax.set_title(ht)
        # A high bar on the left but an even higher one on the right.
        ax.hist([0] + 5*[9], bins=range(10), label="Legend", histtype=ht)
        leg = ax.legend(loc="best")
        fig.canvas.draw()
        leg_bboxes.append(
            leg.get_window_extent().transformed(ax.transAxes.inverted()))

    # The histogram type "bar" is assumed to be the correct reference.
    assert_allclose(leg_bboxes[1].bounds, leg_bboxes[0].bounds)
    assert_allclose(leg_bboxes[2].bounds, leg_bboxes[0].bounds)


def test_legend_auto5():
    """
    Check that the automatic placement handle a rather complex
    case with non rectangular patch. Related to issue #9580.
    """
    fig, axs = plt.subplots(ncols=2, figsize=(9.6, 4.8))

    leg_bboxes = []
    for ax, loc in zip(axs.flat, ("center", "best")):
        # An Ellipse patch at the top, a U-shaped Polygon patch at the
        # bottom and a ring-like Wedge patch: the correct placement of
        # the legend should be in the center.
        for _patch in [
                mpatches.Ellipse(
                    xy=(0.5, 0.9), width=0.8, height=0.2, fc="C1"),
                mpatches.Polygon(np.array([
                    [0, 1], [0, 0], [1, 0], [1, 1], [0.9, 1.0], [0.9, 0.1],
                    [0.1, 0.1], [0.1, 1.0], [0.1, 1.0]]), fc="C1"),
                mpatches.Wedge((0.5, 0.5), 0.5, 0, 360, width=0.05, fc="C0")
                ]:
            ax.add_patch(_patch)

        ax.plot([0.1, 0.9], [0.9, 0.9], label="A segment")  # sthg to label

        leg = ax.legend(loc=loc)
        fig.canvas.draw()
        leg_bboxes.append(
            leg.get_window_extent().transformed(ax.transAxes.inverted()))

    assert_allclose(leg_bboxes[1].bounds, leg_bboxes[0].bounds)


@image_comparison(['legend_various_labels.png'], remove_text=True)
def test_various_labels():
    # tests all sorts of label types
    fig = plt.figure()
    ax = fig.add_subplot(121)
    ax.plot(np.arange(4), 'o', label=1)
    ax.plot(np.linspace(4, 4.1), 'o', label='Développés')
    ax.plot(np.arange(4, 1, -1), 'o', label='__nolegend__')
    ax.legend(numpoints=1, loc='best')


@image_comparison(['legend_labels_first.png'], remove_text=True,
                  tol=0 if platform.machine() == 'x86_64' else 0.013)
def test_labels_first():
    # test labels to left of markers
    fig, ax = plt.subplots()
    ax.plot(np.arange(10), '-o', label=1)
    ax.plot(np.ones(10)*5, ':x', label="x")
    ax.plot(np.arange(20, 10, -1), 'd', label="diamond")
    ax.legend(loc='best', markerfirst=False)


@image_comparison(['legend_multiple_keys.png'], remove_text=True,
                  tol=0 if platform.machine() == 'x86_64' else 0.013)
def test_multiple_keys():
    # test legend entries with multiple keys
    fig, ax = plt.subplots()
    p1, = ax.plot([1, 2, 3], '-o')
    p2, = ax.plot([2, 3, 4], '-x')
    p3, = ax.plot([3, 4, 5], '-d')
    ax.legend([(p1, p2), (p2, p1), p3], ['two keys', 'pad=0', 'one key'],
              numpoints=1,
              handler_map={(p1, p2): HandlerTuple(ndivide=None),
                           (p2, p1): HandlerTuple(ndivide=None, pad=0)})


@image_comparison(['rgba_alpha.png'], remove_text=True,
                  tol=0 if platform.machine() == 'x86_64' else 0.03)
def test_alpha_rgba():
    fig, ax = plt.subplots()
    ax.plot(range(10), lw=5)
    leg = plt.legend(['Longlabel that will go away'], loc='center')
    leg.legendPatch.set_facecolor([1, 0, 0, 0.5])


@image_comparison(['rcparam_alpha.png'], remove_text=True,
                  tol=0 if platform.machine() == 'x86_64' else 0.03)
def test_alpha_rcparam():
    fig, ax = plt.subplots()
    ax.plot(range(10), lw=5)
    with mpl.rc_context(rc={'legend.framealpha': .75}):
        leg = plt.legend(['Longlabel that will go away'], loc='center')
        # this alpha is going to be over-ridden by the rcparam with
        # sets the alpha of the patch to be non-None which causes the alpha
        # value of the face color to be discarded.  This behavior may not be
        # ideal, but it is what it is and we should keep track of it changing
        leg.legendPatch.set_facecolor([1, 0, 0, 0.5])


@image_comparison(['fancy.png'], remove_text=True, tol=0.05)
def test_fancy():
    # Tolerance caused by changing default shadow "shade" from 0.3 to 1 - 0.7 =
    # 0.30000000000000004
    # using subplot triggers some offsetbox functionality untested elsewhere
    plt.subplot(121)
    plt.plot([5] * 10, 'o--', label='XX')
    plt.scatter(np.arange(10), np.arange(10, 0, -1), label='XX\nXX')
    plt.errorbar(np.arange(10), np.arange(10), xerr=0.5,
                 yerr=0.5, label='XX')
    plt.legend(loc="center left", bbox_to_anchor=[1.0, 0.5],
               ncols=2, shadow=True, title="My legend", numpoints=1)


@image_comparison(['framealpha'], remove_text=True,
                  tol=0 if platform.machine() == 'x86_64' else 0.024)
def test_framealpha():
    x = np.linspace(1, 100, 100)
    y = x
    plt.plot(x, y, label='mylabel', lw=10)
    plt.legend(framealpha=0.5)


@image_comparison(['scatter_rc3.png', 'scatter_rc1.png'], remove_text=True)
def test_rc():
    # using subplot triggers some offsetbox functionality untested elsewhere
    plt.figure()
    ax = plt.subplot(121)
    ax.scatter(np.arange(10), np.arange(10, 0, -1), label='three')
    ax.legend(loc="center left", bbox_to_anchor=[1.0, 0.5],
              title="My legend")

    mpl.rcParams['legend.scatterpoints'] = 1
    plt.figure()
    ax = plt.subplot(121)
    ax.scatter(np.arange(10), np.arange(10, 0, -1), label='one')
    ax.legend(loc="center left", bbox_to_anchor=[1.0, 0.5],
              title="My legend")


@image_comparison(['legend_expand.png'], remove_text=True)
def test_legend_expand():
    """Test expand mode"""
    legend_modes = [None, "expand"]
    fig, axs = plt.subplots(len(legend_modes), 1)
    x = np.arange(100)
    for ax, mode in zip(axs, legend_modes):
        ax.plot(x, 50 - x, 'o', label='y=1')
        l1 = ax.legend(loc='upper left', mode=mode)
        ax.add_artist(l1)
        ax.plot(x, x - 50, 'o', label='y=-1')
        l2 = ax.legend(loc='right', mode=mode)
        ax.add_artist(l2)
        ax.legend(loc='lower left', mode=mode, ncols=2)


@image_comparison(['hatching'], remove_text=True, style='default')
def test_hatching():
    # Remove legend texts when this image is regenerated.
    # Remove this line when this test image is regenerated.
    plt.rcParams['text.kerning_factor'] = 6

    fig, ax = plt.subplots()

    # Patches
    patch = plt.Rectangle((0, 0), 0.3, 0.3, hatch='xx',
                          label='Patch\ndefault color\nfilled')
    ax.add_patch(patch)
    patch = plt.Rectangle((0.33, 0), 0.3, 0.3, hatch='||', edgecolor='C1',
                          label='Patch\nexplicit color\nfilled')
    ax.add_patch(patch)
    patch = plt.Rectangle((0, 0.4), 0.3, 0.3, hatch='xx', fill=False,
                          label='Patch\ndefault color\nunfilled')
    ax.add_patch(patch)
    patch = plt.Rectangle((0.33, 0.4), 0.3, 0.3, hatch='||', fill=False,
                          edgecolor='C1',
                          label='Patch\nexplicit color\nunfilled')
    ax.add_patch(patch)

    # Paths
    ax.fill_between([0, .15, .3], [.8, .8, .8], [.9, 1.0, .9],
                    hatch='+', label='Path\ndefault color')
    ax.fill_between([.33, .48, .63], [.8, .8, .8], [.9, 1.0, .9],
                    hatch='+', edgecolor='C2', label='Path\nexplicit color')

    ax.set_xlim(-0.01, 1.1)
    ax.set_ylim(-0.01, 1.1)
    ax.legend(handlelength=4, handleheight=4)


def test_legend_remove():
    fig, ax = plt.subplots()
    lines = ax.plot(range(10))
    leg = fig.legend(lines, "test")
    leg.remove()
    assert fig.legends == []
    leg = ax.legend("test")
    leg.remove()
    assert ax.get_legend() is None


def test_reverse_legend_handles_and_labels():
    """Check that the legend handles and labels are reversed."""
    fig, ax = plt.subplots()
    x = 1
    y = 1
    labels = ["First label", "Second label", "Third label"]
    markers = ['.', ',', 'o']

    ax.plot(x, y, markers[0], label=labels[0])
    ax.plot(x, y, markers[1], label=labels[1])
    ax.plot(x, y, markers[2], label=labels[2])
    leg = ax.legend(reverse=True)
    actual_labels = [t.get_text() for t in leg.get_texts()]
    actual_markers = [h.get_marker() for h in leg.legend_handles]
    assert actual_labels == list(reversed(labels))
    assert actual_markers == list(reversed(markers))


@check_figures_equal(extensions=["png"])
def test_reverse_legend_display(fig_test, fig_ref):
    """Check that the rendered legend entries are reversed"""
    ax = fig_test.subplots()
    ax.plot([1], 'ro', label="first")
    ax.plot([2], 'bx', label="second")
    ax.legend(reverse=True)

    ax = fig_ref.subplots()
    ax.plot([2], 'bx', label="second")
    ax.plot([1], 'ro', label="first")
    ax.legend()


class TestLegendFunction:
    # Tests the legend function on the Axes and pyplot.
    def test_legend_no_args(self):
        lines = plt.plot(range(10), label='hello world')
        with mock.patch('matplotlib.legend.Legend') as Legend:
            plt.legend()
        Legend.assert_called_with(plt.gca(), lines, ['hello world'])

    def test_legend_positional_handles_labels(self):
        lines = plt.plot(range(10))
        with mock.patch('matplotlib.legend.Legend') as Legend:
            plt.legend(lines, ['hello world'])
        Legend.assert_called_with(plt.gca(), lines, ['hello world'])

    def test_legend_positional_handles_only(self):
        lines = plt.plot(range(10))
        with pytest.raises(TypeError, match='but found an Artist'):
            # a single arg is interpreted as labels
            # it's a common error to just pass handles
            plt.legend(lines)

    def test_legend_positional_labels_only(self):
        lines = plt.plot(range(10), label='hello world')
        with mock.patch('matplotlib.legend.Legend') as Legend:
            plt.legend(['foobar'])
        Legend.assert_called_with(plt.gca(), lines, ['foobar'])

    def test_legend_three_args(self):
        lines = plt.plot(range(10), label='hello world')
        with mock.patch('matplotlib.legend.Legend') as Legend:
            plt.legend(lines, ['foobar'], loc='right')
        Legend.assert_called_with(plt.gca(), lines, ['foobar'], loc='right')

    def test_legend_handler_map(self):
        lines = plt.plot(range(10), label='hello world')
        with mock.patch('matplotlib.legend.'
                        '_get_legend_handles_labels') as handles_labels:
            handles_labels.return_value = lines, ['hello world']
            plt.legend(handler_map={'1': 2})
        handles_labels.assert_called_with([plt.gca()], {'1': 2})

    def test_legend_kwargs_handles_only(self):
        fig, ax = plt.subplots()
        x = np.linspace(0, 1, 11)
        ln1, = ax.plot(x, x, label='x')
        ln2, = ax.plot(x, 2*x, label='2x')
        ln3, = ax.plot(x, 3*x, label='3x')
        with mock.patch('matplotlib.legend.Legend') as Legend:
            ax.legend(handles=[ln3, ln2])  # reversed and not ln1
        Legend.assert_called_with(ax, [ln3, ln2], ['3x', '2x'])

    def test_legend_kwargs_labels_only(self):
        fig, ax = plt.subplots()
        x = np.linspace(0, 1, 11)
        ln1, = ax.plot(x, x)
        ln2, = ax.plot(x, 2*x)
        with mock.patch('matplotlib.legend.Legend') as Legend:
            ax.legend(labels=['x', '2x'])
        Legend.assert_called_with(ax, [ln1, ln2], ['x', '2x'])

    def test_legend_kwargs_handles_labels(self):
        fig, ax = plt.subplots()
        th = np.linspace(0, 2*np.pi, 1024)
        lns, = ax.plot(th, np.sin(th), label='sin')
        lnc, = ax.plot(th, np.cos(th), label='cos')
        with mock.patch('matplotlib.legend.Legend') as Legend:
            # labels of lns, lnc are overwritten with explicit ('a', 'b')
            ax.legend(labels=('a', 'b'), handles=(lnc, lns))
        Legend.assert_called_with(ax, (lnc, lns), ('a', 'b'))

    def test_warn_mixed_args_and_kwargs(self):
        fig, ax = plt.subplots()
        th = np.linspace(0, 2*np.pi, 1024)
        lns, = ax.plot(th, np.sin(th), label='sin')
        lnc, = ax.plot(th, np.cos(th), label='cos')
        with pytest.warns(DeprecationWarning) as record:
            ax.legend((lnc, lns), labels=('a', 'b'))
        assert len(record) == 1
        assert str(record[0].message).startswith(
            "You have mixed positional and keyword arguments, some input may "
            "be discarded.")

    def test_parasite(self):
        from mpl_toolkits.axes_grid1 import host_subplot  # type: ignore[import]

        host = host_subplot(111)
        par = host.twinx()

        p1, = host.plot([0, 1, 2], [0, 1, 2], label="Density")
        p2, = par.plot([0, 1, 2], [0, 3, 2], label="Temperature")

        with mock.patch('matplotlib.legend.Legend') as Legend:
            plt.legend()
        Legend.assert_called_with(host, [p1, p2], ['Density', 'Temperature'])


class TestLegendFigureFunction:
    # Tests the legend function for figure
    def test_legend_handle_label(self):
        fig, ax = plt.subplots()
        lines = ax.plot(range(10))
        with mock.patch('matplotlib.legend.Legend') as Legend:
            fig.legend(lines, ['hello world'])
        Legend.assert_called_with(fig, lines, ['hello world'],
                                  bbox_transform=fig.transFigure)

    def test_legend_no_args(self):
        fig, ax = plt.subplots()
        lines = ax.plot(range(10), label='hello world')
        with mock.patch('matplotlib.legend.Legend') as Legend:
            fig.legend()
        Legend.assert_called_with(fig, lines, ['hello world'],
                                  bbox_transform=fig.transFigure)

    def test_legend_label_arg(self):
        fig, ax = plt.subplots()
        lines = ax.plot(range(10))
        with mock.patch('matplotlib.legend.Legend') as Legend:
            fig.legend(['foobar'])
        Legend.assert_called_with(fig, lines, ['foobar'],
                                  bbox_transform=fig.transFigure)

    def test_legend_label_three_args(self):
        fig, ax = plt.subplots()
        lines = ax.plot(range(10))
        with pytest.raises(TypeError, match="0-2"):
            fig.legend(lines, ['foobar'], 'right')
        with pytest.raises(TypeError, match="0-2"):
            fig.legend(lines, ['foobar'], 'right', loc='left')

    def test_legend_kw_args(self):
        fig, axs = plt.subplots(1, 2)
        lines = axs[0].plot(range(10))
        lines2 = axs[1].plot(np.arange(10) * 2.)
        with mock.patch('matplotlib.legend.Legend') as Legend:
            fig.legend(loc='right', labels=('a', 'b'), handles=(lines, lines2))
        Legend.assert_called_with(
            fig, (lines, lines2), ('a', 'b'), loc='right',
            bbox_transform=fig.transFigure)

    def test_warn_args_kwargs(self):
        fig, axs = plt.subplots(1, 2)
        lines = axs[0].plot(range(10))
        lines2 = axs[1].plot(np.arange(10) * 2.)
        with pytest.warns(DeprecationWarning) as record:
            fig.legend((lines, lines2), labels=('a', 'b'))
        assert len(record) == 1
        assert str(record[0].message).startswith(
            "You have mixed positional and keyword arguments, some input may "
            "be discarded.")


def test_figure_legend_outside():
    todos = ['upper ' + pos for pos in ['left', 'center', 'right']]
    todos += ['lower ' + pos for pos in ['left', 'center', 'right']]
    todos += ['left ' + pos for pos in ['lower', 'center', 'upper']]
    todos += ['right ' + pos for pos in ['lower', 'center', 'upper']]

    upperext = [20.347556,  27.722556, 790.583, 545.499]
    lowerext = [20.347556,  71.056556, 790.583, 588.833]
    leftext = [151.681556, 27.722556, 790.583, 588.833]
    rightext = [20.347556,  27.722556, 659.249, 588.833]
    axbb = [upperext, upperext, upperext,
            lowerext, lowerext, lowerext,
            leftext, leftext, leftext,
            rightext, rightext, rightext]

    legbb = [[10., 555., 133., 590.],     # upper left
             [338.5, 555., 461.5, 590.],  # upper center
             [667, 555., 790.,  590.],    # upper right
             [10., 10., 133.,  45.],      # lower left
             [338.5, 10., 461.5,  45.],   # lower center
             [667., 10., 790.,  45.],     # lower right
             [10., 10., 133., 45.],       # left lower
             [10., 282.5, 133., 317.5],   # left center
             [10., 555., 133., 590.],     # left upper
             [667, 10., 790., 45.],       # right lower
             [667., 282.5, 790., 317.5],  # right center
             [667., 555., 790., 590.]]    # right upper

    for nn, todo in enumerate(todos):
        print(todo)
        fig, axs = plt.subplots(constrained_layout=True, dpi=100)
        axs.plot(range(10), label='Boo1')
        leg = fig.legend(loc='outside ' + todo)
        fig.draw_without_rendering()

        assert_allclose(axs.get_window_extent().extents,
                        axbb[nn])
        assert_allclose(leg.get_window_extent().extents,
                        legbb[nn])


@image_comparison(['legend_stackplot.png'],
                  tol=0 if platform.machine() == 'x86_64' else 0.031)
def test_legend_stackplot():
    """Test legend for PolyCollection using stackplot."""
    # related to #1341, #1943, and PR #3303
    fig, ax = plt.subplots()
    x = np.linspace(0, 10, 10)
    y1 = 1.0 * x
    y2 = 2.0 * x + 1
    y3 = 3.0 * x + 2
    ax.stackplot(x, y1, y2, y3, labels=['y1', 'y2', 'y3'])
    ax.set_xlim((0, 10))
    ax.set_ylim((0, 70))
    ax.legend(loc='best')


def test_cross_figure_patch_legend():
    fig, ax = plt.subplots()
    fig2, ax2 = plt.subplots()

    brs = ax.bar(range(3), range(3))
    fig2.legend(brs, 'foo')


def test_nanscatter():
    fig, ax = plt.subplots()

    h = ax.scatter([np.nan], [np.nan], marker="o",
                   facecolor="r", edgecolor="r", s=3)

    ax.legend([h], ["scatter"])

    fig, ax = plt.subplots()
    for color in ['red', 'green', 'blue']:
        n = 750
        x, y = np.random.rand(2, n)
        scale = 200.0 * np.random.rand(n)
        ax.scatter(x, y, c=color, s=scale, label=color,
                   alpha=0.3, edgecolors='none')

    ax.legend()
    ax.grid(True)


def test_legend_repeatcheckok():
    fig, ax = plt.subplots()
    ax.scatter(0.0, 1.0, color='k', marker='o', label='test')
    ax.scatter(0.5, 0.0, color='r', marker='v', label='test')
    ax.legend()
    hand, lab = mlegend._get_legend_handles_labels([ax])
    assert len(lab) == 2
    fig, ax = plt.subplots()
    ax.scatter(0.0, 1.0, color='k', marker='o', label='test')
    ax.scatter(0.5, 0.0, color='k', marker='v', label='test')
    ax.legend()
    hand, lab = mlegend._get_legend_handles_labels([ax])
    assert len(lab) == 2


@image_comparison(['not_covering_scatter.png'])
def test_not_covering_scatter():
    colors = ['b', 'g', 'r']

    for n in range(3):
        plt.scatter([n], [n], color=colors[n])

    plt.legend(['foo', 'foo', 'foo'], loc='best')
    plt.gca().set_xlim(-0.5, 2.2)
    plt.gca().set_ylim(-0.5, 2.2)


@image_comparison(['not_covering_scatter_transform.png'])
def test_not_covering_scatter_transform():
    # Offsets point to top left, the default auto position
    offset = mtransforms.Affine2D().translate(-20, 20)
    x = np.linspace(0, 30, 1000)
    plt.plot(x, x)

    plt.scatter([20], [10], transform=offset + plt.gca().transData)

    plt.legend(['foo', 'bar'], loc='best')


def test_linecollection_scaled_dashes():
    lines1 = [[(0, .5), (.5, 1)], [(.3, .6), (.2, .2)]]
    lines2 = [[[0.7, .2], [.8, .4]], [[.5, .7], [.6, .1]]]
    lines3 = [[[0.6, .2], [.8, .4]], [[.5, .7], [.1, .1]]]
    lc1 = mcollections.LineCollection(lines1, linestyles="--", lw=3)
    lc2 = mcollections.LineCollection(lines2, linestyles="-.")
    lc3 = mcollections.LineCollection(lines3, linestyles=":", lw=.5)

    fig, ax = plt.subplots()
    ax.add_collection(lc1)
    ax.add_collection(lc2)
    ax.add_collection(lc3)

    leg = ax.legend([lc1, lc2, lc3], ["line1", "line2", 'line 3'])
    h1, h2, h3 = leg.legend_handles

    for oh, lh in zip((lc1, lc2, lc3), (h1, h2, h3)):
        assert oh.get_linestyles()[0] == lh._dash_pattern


def test_handler_numpoints():
    """Test legend handler with numpoints <= 1."""
    # related to #6921 and PR #8478
    fig, ax = plt.subplots()
    ax.plot(range(5), label='test')
    ax.legend(numpoints=0.5)


def test_text_nohandler_warning():
    """Test that Text artists with labels raise a warning"""
    fig, ax = plt.subplots()
    ax.plot([0], label="mock data")
    ax.text(x=0, y=0, s="text", label="label")
    with pytest.warns(UserWarning) as record:
        ax.legend()
    assert len(record) == 1

    # this should _not_ warn:
    f, ax = plt.subplots()
    ax.pcolormesh(np.random.uniform(0, 1, (10, 10)))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ax.get_legend_handles_labels()


def test_empty_bar_chart_with_legend():
    """Test legend when bar chart is empty with a label."""
    # related to issue #13003. Calling plt.legend() should not
    # raise an IndexError.
    plt.bar([], [], label='test')
    plt.legend()


@image_comparison(['shadow_argument_types.png'], remove_text=True, style='mpl20',
                  tol=0 if platform.machine() == 'x86_64' else 0.028)
def test_shadow_argument_types():
    # Test that different arguments for shadow work as expected
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], label='test')

    # Test various shadow configurations
    # as well as different ways of specifying colors
    legs = (ax.legend(loc='upper left', shadow=True),    # True
            ax.legend(loc='upper right', shadow=False),  # False
            ax.legend(loc='center left',                 # string
                      shadow={'color': 'red', 'alpha': 0.1}),
            ax.legend(loc='center right',                # tuple
                      shadow={'color': (0.1, 0.2, 0.5), 'oy': -5}),
            ax.legend(loc='lower left',                   # tab
                      shadow={'color': 'tab:cyan', 'ox': 10})
            )
    for l in legs:
        ax.add_artist(l)
    ax.legend(loc='lower right')  # default


def test_shadow_invalid_argument():
    # Test if invalid argument to legend shadow
    # (i.e. not [color|bool]) raises ValueError
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], label='test')
    with pytest.raises(ValueError, match="dict or bool"):
        ax.legend(loc="upper left", shadow="aardvark")  # Bad argument


def test_shadow_framealpha():
    # Test if framealpha is activated when shadow is True
    # and framealpha is not explicitly passed'''
    fig, ax = plt.subplots()
    ax.plot(range(100), label="test")
    leg = ax.legend(shadow=True, facecolor='w')
    assert leg.get_frame().get_alpha() == 1


def test_legend_title_empty():
    # test that if we don't set the legend title, that
    # it comes back as an empty string, and that it is not
    # visible:
    fig, ax = plt.subplots()
    ax.plot(range(10), label="mock data")
    leg = ax.legend()
    assert leg.get_title().get_text() == ""
    assert not leg.get_title().get_visible()


def test_legend_proper_window_extent():
    # test that legend returns the expected extent under various dpi...
    fig, ax = plt.subplots(dpi=100)
    ax.plot(range(10), label='Aardvark')
    leg = ax.legend()
    x01 = leg.get_window_extent(fig.canvas.get_renderer()).x0

    fig, ax = plt.subplots(dpi=200)
    ax.plot(range(10), label='Aardvark')
    leg = ax.legend()
    x02 = leg.get_window_extent(fig.canvas.get_renderer()).x0
    assert pytest.approx(x01*2, 0.1) == x02


def test_window_extent_cached_renderer():
    fig, ax = plt.subplots(dpi=100)
    ax.plot(range(10), label='Aardvark')
    leg = ax.legend()
    leg2 = fig.legend()
    fig.canvas.draw()
    # check that get_window_extent will use the cached renderer
    leg.get_window_extent()
    leg2.get_window_extent()


def test_legend_title_fontprop_fontsize():
    # test the title_fontsize kwarg
    plt.plot(range(10), label="mock data")
    with pytest.raises(ValueError):
        plt.legend(title='Aardvark', title_fontsize=22,
                   title_fontproperties={'family': 'serif', 'size': 22})

    leg = plt.legend(title='Aardvark', title_fontproperties=FontProperties(
                                       family='serif', size=22))
    assert leg.get_title().get_size() == 22

    fig, axes = plt.subplots(2, 3, figsize=(10, 6))
    axes = axes.flat
    axes[0].plot(range(10), label="mock data")
    leg0 = axes[0].legend(title='Aardvark', title_fontsize=22)
    assert leg0.get_title().get_fontsize() == 22
    axes[1].plot(range(10), label="mock data")
    leg1 = axes[1].legend(title='Aardvark',
                          title_fontproperties={'family': 'serif', 'size': 22})
    assert leg1.get_title().get_fontsize() == 22
    axes[2].plot(range(10), label="mock data")
    mpl.rcParams['legend.title_fontsize'] = None
    leg2 = axes[2].legend(title='Aardvark',
                          title_fontproperties={'family': 'serif'})
    assert leg2.get_title().get_fontsize() == mpl.rcParams['font.size']
    axes[3].plot(range(10), label="mock data")
    leg3 = axes[3].legend(title='Aardvark')
    assert leg3.get_title().get_fontsize() == mpl.rcParams['font.size']
    axes[4].plot(range(10), label="mock data")
    mpl.rcParams['legend.title_fontsize'] = 20
    leg4 = axes[4].legend(title='Aardvark',
                          title_fontproperties={'family': 'serif'})
    assert leg4.get_title().get_fontsize() == 20
    axes[5].plot(range(10), label="mock data")
    leg5 = axes[5].legend(title='Aardvark')
    assert leg5.get_title().get_fontsize() == 20


@pytest.mark.parametrize('alignment', ('center', 'left', 'right'))
def test_legend_alignment(alignment):
    fig, ax = plt.subplots()
    ax.plot(range(10), label='test')
    leg = ax.legend(title="Aardvark", alignment=alignment)
    assert leg.get_children()[0].align == alignment
    assert leg.get_alignment() == alignment


@pytest.mark.parametrize('loc', ('center', 'best',))
def test_ax_legend_set_loc(loc):
    fig, ax = plt.subplots()
    ax.plot(range(10), label='test')
    leg = ax.legend()
    leg.set_loc(loc)
    assert leg._get_loc() == mlegend.Legend.codes[loc]


@pytest.mark.parametrize('loc', ('outside right', 'right',))
def test_fig_legend_set_loc(loc):
    fig, ax = plt.subplots()
    ax.plot(range(10), label='test')
    leg = fig.legend()
    leg.set_loc(loc)

    loc = loc.split()[1] if loc.startswith("outside") else loc
    assert leg._get_loc() == mlegend.Legend.codes[loc]


@pytest.mark.parametrize('alignment', ('center', 'left', 'right'))
def test_legend_set_alignment(alignment):
    fig, ax = plt.subplots()
    ax.plot(range(10), label='test')
    leg = ax.legend()
    leg.set_alignment(alignment)
    assert leg.get_children()[0].align == alignment
    assert leg.get_alignment() == alignment


@pytest.mark.parametrize('color', ('red', 'none', (.5, .5, .5)))
def test_legend_labelcolor_single(color):
    # test labelcolor for a single color
    fig, ax = plt.subplots()
    ax.plot(np.arange(10), np.arange(10)*1, label='#1')
    ax.plot(np.arange(10), np.arange(10)*2, label='#2')
    ax.plot(np.arange(10), np.arange(10)*3, label='#3')

    leg = ax.legend(labelcolor=color)
    for text in leg.get_texts():
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_labelcolor_list():
    # test labelcolor for a list of colors
    fig, ax = plt.subplots()
    ax.plot(np.arange(10), np.arange(10)*1, label='#1')
    ax.plot(np.arange(10), np.arange(10)*2, label='#2')
    ax.plot(np.arange(10), np.arange(10)*3, label='#3')

    leg = ax.legend(labelcolor=['r', 'g', 'b'])
    for text, color in zip(leg.get_texts(), ['r', 'g', 'b']):
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_labelcolor_linecolor():
    # test the labelcolor for labelcolor='linecolor'
    fig, ax = plt.subplots()
    ax.plot(np.arange(10), np.arange(10)*1, label='#1', color='r')
    ax.plot(np.arange(10), np.arange(10)*2, label='#2', color='g')
    ax.plot(np.arange(10), np.arange(10)*3, label='#3', color='b')

    leg = ax.legend(labelcolor='linecolor')
    for text, color in zip(leg.get_texts(), ['r', 'g', 'b']):
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_pathcollection_labelcolor_linecolor():
    # test the labelcolor for labelcolor='linecolor' on PathCollection
    fig, ax = plt.subplots()
    ax.scatter(np.arange(10), np.arange(10)*1, label='#1', c='r')
    ax.scatter(np.arange(10), np.arange(10)*2, label='#2', c='g')
    ax.scatter(np.arange(10), np.arange(10)*3, label='#3', c='b')

    leg = ax.legend(labelcolor='linecolor')
    for text, color in zip(leg.get_texts(), ['r', 'g', 'b']):
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_pathcollection_labelcolor_linecolor_iterable():
    # test the labelcolor for labelcolor='linecolor' on PathCollection
    # with iterable colors
    fig, ax = plt.subplots()
    colors = np.array(['r', 'g', 'b', 'c', 'm'] * 2)
    ax.scatter(np.arange(10), np.arange(10), label='#1', c=colors)

    leg = ax.legend(labelcolor='linecolor')
    text, = leg.get_texts()
    assert mpl.colors.same_color(text.get_color(), 'black')


def test_legend_pathcollection_labelcolor_linecolor_cmap():
    # test the labelcolor for labelcolor='linecolor' on PathCollection
    # with a colormap
    fig, ax = plt.subplots()
    ax.scatter(np.arange(10), np.arange(10), c=np.arange(10), label='#1')

    leg = ax.legend(labelcolor='linecolor')
    text, = leg.get_texts()
    assert mpl.colors.same_color(text.get_color(), 'black')


def test_legend_labelcolor_markeredgecolor():
    # test the labelcolor for labelcolor='markeredgecolor'
    fig, ax = plt.subplots()
    ax.plot(np.arange(10), np.arange(10)*1, label='#1', markeredgecolor='r')
    ax.plot(np.arange(10), np.arange(10)*2, label='#2', markeredgecolor='g')
    ax.plot(np.arange(10), np.arange(10)*3, label='#3', markeredgecolor='b')

    leg = ax.legend(labelcolor='markeredgecolor')
    for text, color in zip(leg.get_texts(), ['r', 'g', 'b']):
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_pathcollection_labelcolor_markeredgecolor():
    # test the labelcolor for labelcolor='markeredgecolor' on PathCollection
    fig, ax = plt.subplots()
    ax.scatter(np.arange(10), np.arange(10)*1, label='#1', edgecolor='r')
    ax.scatter(np.arange(10), np.arange(10)*2, label='#2', edgecolor='g')
    ax.scatter(np.arange(10), np.arange(10)*3, label='#3', edgecolor='b')

    leg = ax.legend(labelcolor='markeredgecolor')
    for text, color in zip(leg.get_texts(), ['r', 'g', 'b']):
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_pathcollection_labelcolor_markeredgecolor_iterable():
    # test the labelcolor for labelcolor='markeredgecolor' on PathCollection
    # with iterable colors
    fig, ax = plt.subplots()
    colors = np.array(['r', 'g', 'b', 'c', 'm'] * 2)
    ax.scatter(np.arange(10), np.arange(10), label='#1', edgecolor=colors)

    leg = ax.legend(labelcolor='markeredgecolor')
    for text, color in zip(leg.get_texts(), ['k']):
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_pathcollection_labelcolor_markeredgecolor_cmap():
    # test the labelcolor for labelcolor='markeredgecolor' on PathCollection
    # with a colormap
    fig, ax = plt.subplots()
    edgecolors = mpl.cm.viridis(np.random.rand(10))
    ax.scatter(
        np.arange(10),
        np.arange(10),
        label='#1',
        c=np.arange(10),
        edgecolor=edgecolors,
        cmap="Reds"
    )

    leg = ax.legend(labelcolor='markeredgecolor')
    for text, color in zip(leg.get_texts(), ['k']):
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_labelcolor_markerfacecolor():
    # test the labelcolor for labelcolor='markerfacecolor'
    fig, ax = plt.subplots()
    ax.plot(np.arange(10), np.arange(10)*1, label='#1', markerfacecolor='r')
    ax.plot(np.arange(10), np.arange(10)*2, label='#2', markerfacecolor='g')
    ax.plot(np.arange(10), np.arange(10)*3, label='#3', markerfacecolor='b')

    leg = ax.legend(labelcolor='markerfacecolor')
    for text, color in zip(leg.get_texts(), ['r', 'g', 'b']):
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_pathcollection_labelcolor_markerfacecolor():
    # test the labelcolor for labelcolor='markerfacecolor' on PathCollection
    fig, ax = plt.subplots()
    ax.scatter(np.arange(10), np.arange(10)*1, label='#1', facecolor='r')
    ax.scatter(np.arange(10), np.arange(10)*2, label='#2', facecolor='g')
    ax.scatter(np.arange(10), np.arange(10)*3, label='#3', facecolor='b')

    leg = ax.legend(labelcolor='markerfacecolor')
    for text, color in zip(leg.get_texts(), ['r', 'g', 'b']):
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_pathcollection_labelcolor_markerfacecolor_iterable():
    # test the labelcolor for labelcolor='markerfacecolor' on PathCollection
    # with iterable colors
    fig, ax = plt.subplots()
    colors = np.array(['r', 'g', 'b', 'c', 'm'] * 2)
    ax.scatter(np.arange(10), np.arange(10), label='#1', facecolor=colors)

    leg = ax.legend(labelcolor='markerfacecolor')
    for text, color in zip(leg.get_texts(), ['k']):
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_pathcollection_labelcolor_markfacecolor_cmap():
    # test the labelcolor for labelcolor='markerfacecolor' on PathCollection
    # with colormaps
    fig, ax = plt.subplots()
    colors = mpl.cm.viridis(np.random.rand(10))
    ax.scatter(
        np.arange(10),
        np.arange(10),
        label='#1',
        c=colors
    )

    leg = ax.legend(labelcolor='markerfacecolor')
    for text, color in zip(leg.get_texts(), ['k']):
        assert mpl.colors.same_color(text.get_color(), color)


@pytest.mark.parametrize('color', ('red', 'none', (.5, .5, .5)))
def test_legend_labelcolor_rcparam_single(color):
    # test the rcParams legend.labelcolor for a single color
    fig, ax = plt.subplots()
    ax.plot(np.arange(10), np.arange(10)*1, label='#1')
    ax.plot(np.arange(10), np.arange(10)*2, label='#2')
    ax.plot(np.arange(10), np.arange(10)*3, label='#3')

    mpl.rcParams['legend.labelcolor'] = color
    leg = ax.legend()
    for text in leg.get_texts():
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_labelcolor_rcparam_linecolor():
    # test the rcParams legend.labelcolor for a linecolor
    fig, ax = plt.subplots()
    ax.plot(np.arange(10), np.arange(10)*1, label='#1', color='r')
    ax.plot(np.arange(10), np.arange(10)*2, label='#2', color='g')
    ax.plot(np.arange(10), np.arange(10)*3, label='#3', color='b')

    mpl.rcParams['legend.labelcolor'] = 'linecolor'
    leg = ax.legend()
    for text, color in zip(leg.get_texts(), ['r', 'g', 'b']):
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_labelcolor_rcparam_markeredgecolor():
    # test the labelcolor for labelcolor='markeredgecolor'
    fig, ax = plt.subplots()
    ax.plot(np.arange(10), np.arange(10)*1, label='#1', markeredgecolor='r')
    ax.plot(np.arange(10), np.arange(10)*2, label='#2', markeredgecolor='g')
    ax.plot(np.arange(10), np.arange(10)*3, label='#3', markeredgecolor='b')

    mpl.rcParams['legend.labelcolor'] = 'markeredgecolor'
    leg = ax.legend()
    for text, color in zip(leg.get_texts(), ['r', 'g', 'b']):
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_labelcolor_rcparam_markeredgecolor_short():
    # test the labelcolor for labelcolor='markeredgecolor'
    fig, ax = plt.subplots()
    ax.plot(np.arange(10), np.arange(10)*1, label='#1', markeredgecolor='r')
    ax.plot(np.arange(10), np.arange(10)*2, label='#2', markeredgecolor='g')
    ax.plot(np.arange(10), np.arange(10)*3, label='#3', markeredgecolor='b')

    mpl.rcParams['legend.labelcolor'] = 'mec'
    leg = ax.legend()
    for text, color in zip(leg.get_texts(), ['r', 'g', 'b']):
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_labelcolor_rcparam_markerfacecolor():
    # test the labelcolor for labelcolor='markeredgecolor'
    fig, ax = plt.subplots()
    ax.plot(np.arange(10), np.arange(10)*1, label='#1', markerfacecolor='r')
    ax.plot(np.arange(10), np.arange(10)*2, label='#2', markerfacecolor='g')
    ax.plot(np.arange(10), np.arange(10)*3, label='#3', markerfacecolor='b')

    mpl.rcParams['legend.labelcolor'] = 'markerfacecolor'
    leg = ax.legend()
    for text, color in zip(leg.get_texts(), ['r', 'g', 'b']):
        assert mpl.colors.same_color(text.get_color(), color)


def test_legend_labelcolor_rcparam_markerfacecolor_short():
    # test the labelcolor for labelcolor='markeredgecolor'
    fig, ax = plt.subplots()
    ax.plot(np.arange(10), np.arange(10)*1, label='#1', markerfacecolor='r')
    ax.plot(np.arange(10), np.arange(10)*2, label='#2', markerfacecolor='g')
    ax.plot(np.arange(10), np.arange(10)*3, label='#3', markerfacecolor='b')

    mpl.rcParams['legend.labelcolor'] = 'mfc'
    leg = ax.legend()
    for text, color in zip(leg.get_texts(), ['r', 'g', 'b']):
        assert mpl.colors.same_color(text.get_color(), color)


@pytest.mark.filterwarnings("ignore:No artists with labels found to put in legend")
def test_get_set_draggable():
    legend = plt.legend()
    assert not legend.get_draggable()
    legend.set_draggable(True)
    assert legend.get_draggable()
    legend.set_draggable(False)
    assert not legend.get_draggable()


@pytest.mark.parametrize('draggable', (True, False))
def test_legend_draggable(draggable):
    fig, ax = plt.subplots()
    ax.plot(range(10), label='shabnams')
    leg = ax.legend(draggable=draggable)
    assert leg.get_draggable() is draggable


def test_alpha_handles():
    x, n, hh = plt.hist([1, 2, 3], alpha=0.25, label='data', color='red')
    legend = plt.legend()
    for lh in legend.legend_handles:
        lh.set_alpha(1.0)
    assert lh.get_facecolor()[:-1] == hh[1].get_facecolor()[:-1]
    assert lh.get_edgecolor()[:-1] == hh[1].get_edgecolor()[:-1]


@needs_usetex
def test_usetex_no_warn(caplog):
    mpl.rcParams['font.family'] = 'serif'
    mpl.rcParams['font.serif'] = 'Computer Modern'
    mpl.rcParams['text.usetex'] = True

    fig, ax = plt.subplots()
    ax.plot(0, 0, label='input')
    ax.legend(title="My legend")

    fig.canvas.draw()
    assert "Font family ['serif'] not found." not in caplog.text


def test_warn_big_data_best_loc(monkeypatch):
    # Force _find_best_position to think it took a long time.
    counter = itertools.count(0, step=1.5)
    monkeypatch.setattr(time, 'perf_counter', lambda: next(counter))

    fig, ax = plt.subplots()
    fig.canvas.draw()  # So that we can call draw_artist later.

    # Place line across all possible legend locations.
    x = [0.9, 0.1, 0.1, 0.9, 0.9, 0.5]
    y = [0.95, 0.95, 0.05, 0.05, 0.5, 0.5]
    ax.plot(x, y, 'o-', label='line')

    with rc_context({'legend.loc': 'best'}):
        legend = ax.legend()
    with pytest.warns(UserWarning,
                      match='Creating legend with loc="best" can be slow with large '
                      'amounts of data.') as records:
        fig.draw_artist(legend)  # Don't bother drawing the lines -- it's slow.
    # The _find_best_position method of Legend is called twice, duplicating
    # the warning message.
    assert len(records) == 2


def test_no_warn_big_data_when_loc_specified(monkeypatch):
    # Force _find_best_position to think it took a long time.
    counter = itertools.count(0, step=1.5)
    monkeypatch.setattr(time, 'perf_counter', lambda: next(counter))

    fig, ax = plt.subplots()
    fig.canvas.draw()

    # Place line across all possible legend locations.
    x = [0.9, 0.1, 0.1, 0.9, 0.9, 0.5]
    y = [0.95, 0.95, 0.05, 0.05, 0.5, 0.5]
    ax.plot(x, y, 'o-', label='line')

    legend = ax.legend('best')
    fig.draw_artist(legend)  # Check that no warning is emitted.


@pytest.mark.parametrize('label_array', [['low', 'high'],
                                         ('low', 'high'),
                                         np.array(['low', 'high'])])
def test_plot_multiple_input_multiple_label(label_array):
    # test ax.plot() with multidimensional input
    # and multiple labels
    x = [1, 2, 3]
    y = [[1, 2],
         [2, 5],
         [4, 9]]

    fig, ax = plt.subplots()
    ax.plot(x, y, label=label_array)
    leg = ax.legend()
    legend_texts = [entry.get_text() for entry in leg.get_texts()]
    assert legend_texts == ['low', 'high']


@pytest.mark.parametrize('label', ['one', 1, int])
def test_plot_multiple_input_single_label(label):
    # test ax.plot() with multidimensional input
    # and single label
    x = [1, 2, 3]
    y = [[1, 2],
         [2, 5],
         [4, 9]]

    fig, ax = plt.subplots()
    ax.plot(x, y, label=label)
    leg = ax.legend()
    legend_texts = [entry.get_text() for entry in leg.get_texts()]
    assert legend_texts == [str(label)] * 2


@pytest.mark.parametrize('label_array', [['low', 'high'],
                                         ('low', 'high'),
                                         np.array(['low', 'high'])])
def test_plot_single_input_multiple_label(label_array):
    # test ax.plot() with 1D array like input
    # and iterable label
    x = [1, 2, 3]
    y = [2, 5, 6]
    fig, ax = plt.subplots()
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match='Passing label as a length 2 sequence'):
        ax.plot(x, y, label=label_array)
    leg = ax.legend()
    assert len(leg.get_texts()) == 1
    assert leg.get_texts()[0].get_text() == str(label_array)


def test_plot_single_input_list_label():
    fig, ax = plt.subplots()
    line, = ax.plot([[0], [1]], label=['A'])
    assert line.get_label() == 'A'


def test_plot_multiple_label_incorrect_length_exception():
    # check that exception is raised if multiple labels
    # are given, but number of on labels != number of lines
    with pytest.raises(ValueError):
        x = [1, 2, 3]
        y = [[1, 2],
             [2, 5],
             [4, 9]]
        label = ['high', 'low', 'medium']
        fig, ax = plt.subplots()
        ax.plot(x, y, label=label)


def test_legend_face_edgecolor():
    # Smoke test for PolyCollection legend handler with 'face' edgecolor.
    fig, ax = plt.subplots()
    ax.fill_between([0, 1, 2], [1, 2, 3], [2, 3, 4],
                    facecolor='r', edgecolor='face', label='Fill')
    ax.legend()


def test_legend_text_axes():
    fig, ax = plt.subplots()
    ax.plot([1, 2], [3, 4], label='line')
    leg = ax.legend()

    assert leg.axes is ax
    assert leg.get_texts()[0].axes is ax


def test_handlerline2d():
    # Test marker consistency for monolithic Line2D legend handler (#11357).
    fig, ax = plt.subplots()
    ax.scatter([0, 1], [0, 1], marker="v")
    handles = [mlines.Line2D([0], [0], marker="v")]
    leg = ax.legend(handles, ["Aardvark"], numpoints=1)
    assert handles[0].get_marker() == leg.legend_handles[0].get_marker()


def test_subfigure_legend():
    # Test that legend can be added to subfigure (#20723)
    subfig = plt.figure().subfigures()
    ax = subfig.subplots()
    ax.plot([0, 1], [0, 1], label="line")
    leg = subfig.legend()
    assert leg.get_figure(root=False) is subfig


def test_setting_alpha_keeps_polycollection_color():
    pc = plt.fill_between([0, 1], [2, 3], color='#123456', label='label')
    patch = plt.legend().get_patches()[0]
    patch.set_alpha(0.5)
    assert patch.get_facecolor()[:3] == tuple(pc.get_facecolor()[0][:3])
    assert patch.get_edgecolor()[:3] == tuple(pc.get_edgecolor()[0][:3])


def test_legend_markers_from_line2d():
    # Test that markers can be copied for legend lines (#17960)
    _markers = ['.', '*', 'v']
    fig, ax = plt.subplots()
    lines = [mlines.Line2D([0], [0], ls='None', marker=mark)
             for mark in _markers]
    labels = ["foo", "bar", "xyzzy"]
    markers = [line.get_marker() for line in lines]
    legend = ax.legend(lines, labels)

    new_markers = [line.get_marker() for line in legend.get_lines()]
    new_labels = [text.get_text() for text in legend.get_texts()]

    assert markers == new_markers == _markers
    assert labels == new_labels


@check_figures_equal(extensions=['png'])
def test_ncol_ncols(fig_test, fig_ref):
    # Test that both ncol and ncols work
    strings = ["a", "b", "c", "d", "e", "f"]
    ncols = 3
    fig_test.legend(strings, ncol=ncols)
    fig_ref.legend(strings, ncols=ncols)


def test_loc_invalid_tuple_exception():
    # check that exception is raised if the loc arg
    # of legend is not a 2-tuple of numbers
    fig, ax = plt.subplots()
    with pytest.raises(ValueError, match=('loc must be string, coordinate '
                       'tuple, or an integer 0-10, not \\(1.1,\\)')):
        ax.legend(loc=(1.1, ), labels=["mock data"])

    with pytest.raises(ValueError, match=('loc must be string, coordinate '
                       'tuple, or an integer 0-10, not \\(0.481, 0.4227, 0.4523\\)')):
        ax.legend(loc=(0.481, 0.4227, 0.4523), labels=["mock data"])

    with pytest.raises(ValueError, match=('loc must be string, coordinate '
                       'tuple, or an integer 0-10, not \\(0.481, \'go blue\'\\)')):
        ax.legend(loc=(0.481, "go blue"), labels=["mock data"])


def test_loc_valid_tuple():
    fig, ax = plt.subplots()
    ax.legend(loc=(0.481, 0.442), labels=["mock data"])
    ax.legend(loc=(1, 2), labels=["mock data"])


def test_loc_valid_list():
    fig, ax = plt.subplots()
    ax.legend(loc=[0.481, 0.442], labels=["mock data"])
    ax.legend(loc=[1, 2], labels=["mock data"])


def test_loc_invalid_list_exception():
    fig, ax = plt.subplots()
    with pytest.raises(ValueError, match=('loc must be string, coordinate '
                       'tuple, or an integer 0-10, not \\[1.1, 2.2, 3.3\\]')):
        ax.legend(loc=[1.1, 2.2, 3.3], labels=["mock data"])


def test_loc_invalid_type():
    fig, ax = plt.subplots()
    with pytest.raises(ValueError, match=("loc must be string, coordinate "
                       "tuple, or an integer 0-10, not {'not': True}")):
        ax.legend(loc={'not': True}, labels=["mock data"])


def test_loc_validation_numeric_value():
    fig, ax = plt.subplots()
    ax.legend(loc=0, labels=["mock data"])
    ax.legend(loc=1, labels=["mock data"])
    ax.legend(loc=5, labels=["mock data"])
    ax.legend(loc=10, labels=["mock data"])
    with pytest.raises(ValueError, match=('loc must be string, coordinate '
                       'tuple, or an integer 0-10, not 11')):
        ax.legend(loc=11, labels=["mock data"])

    with pytest.raises(ValueError, match=('loc must be string, coordinate '
                       'tuple, or an integer 0-10, not -1')):
        ax.legend(loc=-1, labels=["mock data"])


def test_loc_validation_string_value():
    fig, ax = plt.subplots()
    labels = ["mock data"]
    ax.legend(loc='best', labels=labels)
    ax.legend(loc='upper right', labels=labels)
    ax.legend(loc='best', labels=labels)
    ax.legend(loc='upper right', labels=labels)
    ax.legend(loc='upper left', labels=labels)
    ax.legend(loc='lower left', labels=labels)
    ax.legend(loc='lower right', labels=labels)
    ax.legend(loc='right', labels=labels)
    ax.legend(loc='center left', labels=labels)
    ax.legend(loc='center right', labels=labels)
    ax.legend(loc='lower center', labels=labels)
    ax.legend(loc='upper center', labels=labels)
    with pytest.raises(ValueError, match="'wrong' is not a valid value for"):
        ax.legend(loc='wrong', labels=labels)


def test_legend_handle_label_mismatch():
    pl1, = plt.plot(range(10))
    pl2, = plt.plot(range(10))
    with pytest.warns(UserWarning, match="number of handles and labels"):
        legend = plt.legend(handles=[pl1, pl2], labels=["pl1", "pl2", "pl3"])
        assert len(legend.legend_handles) == 2
        assert len(legend.get_texts()) == 2


def test_legend_handle_label_mismatch_no_len():
    pl1, = plt.plot(range(10))
    pl2, = plt.plot(range(10))
    legend = plt.legend(handles=iter([pl1, pl2]),
                        labels=iter(["pl1", "pl2", "pl3"]))
    assert len(legend.legend_handles) == 2
    assert len(legend.get_texts()) == 2


def test_legend_nolabels_warning():
    plt.plot([1, 2, 3])
    with pytest.raises(UserWarning, match="No artists with labels found"):
        plt.legend()


@pytest.mark.filterwarnings("ignore:No artists with labels found to put in legend")
def test_legend_nolabels_draw():
    plt.plot([1, 2, 3])
    plt.legend()
    assert plt.gca().get_legend() is not None


def test_legend_loc_polycollection():
    # Test that the legend is placed in the correct
    # position for 'best' for polycollection
    x = [3, 4, 5]
    y1 = [1, 1, 1]
    y2 = [5, 5, 5]
    leg_bboxes = []
    fig, axs = plt.subplots(ncols=2, figsize=(10, 5))
    for ax, loc in zip(axs.flat, ('best', 'lower left')):
        ax.fill_between(x, y1, y2, color='gray', alpha=0.5, label='Shaded Area')
        ax.set_xlim(0, 6)
        ax.set_ylim(-1, 5)
        leg = ax.legend(loc=loc)
        fig.canvas.draw()
        leg_bboxes.append(
            leg.get_window_extent().transformed(ax.transAxes.inverted()))
    assert_allclose(leg_bboxes[1].bounds, leg_bboxes[0].bounds)


def test_legend_text():
    # Test that legend is place in the correct
    # position for 'best' when there is text in figure
    fig, axs = plt.subplots(ncols=2, figsize=(10, 5))
    leg_bboxes = []
    for ax, loc in zip(axs.flat, ('best', 'lower left')):
        x = [1, 2]
        y = [2, 1]
        ax.plot(x, y, label='plot name')
        ax.text(1.5, 2, 'some text blahblah', verticalalignment='top')
        leg = ax.legend(loc=loc)
        fig.canvas.draw()
        leg_bboxes.append(
            leg.get_window_extent().transformed(ax.transAxes.inverted()))
    assert_allclose(leg_bboxes[1].bounds, leg_bboxes[0].bounds)


def test_legend_annotate():
    fig, ax = plt.subplots()

    ax.plot([1, 2, 3], label="Line")
    ax.annotate("a", xy=(1, 1))
    ax.legend(loc=0)

    with mock.patch.object(
            fig, '_get_renderer', wraps=fig._get_renderer) as mocked_get_renderer:
        fig.savefig(io.BytesIO())

    # Finding the legend position should not require _get_renderer to be called
    mocked_get_renderer.assert_not_called()


def test_boxplot_legend_labels():
    # Test that legend entries are generated when passing `label`.
    np.random.seed(19680801)
    data = np.random.random((10, 4))
    fig, axs = plt.subplots(nrows=1, ncols=4)
    legend_labels = ['box A', 'box B', 'box C', 'box D']

    # Testing legend labels and patch passed to legend.
    bp1 = axs[0].boxplot(data, patch_artist=True, label=legend_labels)
    assert [v.get_label() for v in bp1['boxes']] == legend_labels
    handles, labels = axs[0].get_legend_handles_labels()
    assert labels == legend_labels
    assert all(isinstance(h, mpl.patches.PathPatch) for h in handles)

    # Testing legend without `box`.
    bp2 = axs[1].boxplot(data, label=legend_labels, showbox=False)
    # Without a box, The legend entries should be passed from the medians.
    assert [v.get_label() for v in bp2['medians']] == legend_labels
    handles, labels = axs[1].get_legend_handles_labels()
    assert labels == legend_labels
    assert all(isinstance(h, mpl.lines.Line2D) for h in handles)

    # Testing legend with number of labels different from number of boxes.
    with pytest.raises(ValueError, match='values must have same the length'):
        bp3 = axs[2].boxplot(data, label=legend_labels[:-1])

    # Test that for a string label, only the first box gets a label.
    bp4 = axs[3].boxplot(data, label='box A')
    assert bp4['medians'][0].get_label() == 'box A'
    assert all(x.get_label().startswith("_") for x in bp4['medians'][1:])
