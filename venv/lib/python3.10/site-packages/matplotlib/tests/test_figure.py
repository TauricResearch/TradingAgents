import copy
from datetime import datetime
import io
import pickle
import platform
from threading import Timer
from types import SimpleNamespace
import warnings

import numpy as np
import pytest
from PIL import Image

import matplotlib as mpl
from matplotlib import gridspec
from matplotlib.testing.decorators import image_comparison, check_figures_equal
from matplotlib.axes import Axes
from matplotlib.backend_bases import KeyEvent, MouseEvent
from matplotlib.figure import Figure, FigureBase
from matplotlib.layout_engine import (ConstrainedLayoutEngine,
                                      TightLayoutEngine,
                                      PlaceHolderLayoutEngine)
from matplotlib.ticker import AutoMinorLocator, FixedFormatter, ScalarFormatter
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


@image_comparison(['figure_align_labels'], extensions=['png', 'svg'],
                  tol=0 if platform.machine() == 'x86_64' else 0.01)
def test_align_labels():
    fig = plt.figure(layout='tight')
    gs = gridspec.GridSpec(3, 3)

    ax = fig.add_subplot(gs[0, :2])
    ax.plot(np.arange(0, 1e6, 1000))
    ax.set_ylabel('Ylabel0 0')
    ax = fig.add_subplot(gs[0, -1])
    ax.plot(np.arange(0, 1e4, 100))

    for i in range(3):
        ax = fig.add_subplot(gs[1, i])
        ax.set_ylabel('YLabel1 %d' % i)
        ax.set_xlabel('XLabel1 %d' % i)
        if i in [0, 2]:
            ax.xaxis.set_label_position("top")
            ax.xaxis.tick_top()
        if i == 0:
            for tick in ax.get_xticklabels():
                tick.set_rotation(90)
        if i == 2:
            ax.yaxis.set_label_position("right")
            ax.yaxis.tick_right()

    for i in range(3):
        ax = fig.add_subplot(gs[2, i])
        ax.set_xlabel(f'XLabel2 {i}')
        ax.set_ylabel(f'YLabel2 {i}')

        if i == 2:
            ax.plot(np.arange(0, 1e4, 10))
            ax.yaxis.set_label_position("right")
            ax.yaxis.tick_right()
            for tick in ax.get_xticklabels():
                tick.set_rotation(90)

    fig.align_labels()


@image_comparison(['figure_align_titles_tight.png',
                   'figure_align_titles_constrained.png'],
                  tol=0 if platform.machine() == 'x86_64' else 0.022,
                  style='mpl20')
def test_align_titles():
    for layout in ['tight', 'constrained']:
        fig, axs = plt.subplots(1, 2, layout=layout, width_ratios=[2, 1])

        ax = axs[0]
        ax.plot(np.arange(0, 1e6, 1000))
        ax.set_title('Title0 left', loc='left')
        ax.set_title('Title0 center', loc='center')
        ax.set_title('Title0 right', loc='right')

        ax = axs[1]
        ax.plot(np.arange(0, 1e4, 100))
        ax.set_title('Title1')
        ax.set_xlabel('Xlabel0')
        ax.xaxis.set_label_position("top")
        ax.xaxis.tick_top()
        for tick in ax.get_xticklabels():
            tick.set_rotation(90)

        fig.align_titles()


def test_align_labels_stray_axes():
    fig, axs = plt.subplots(2, 2)
    for nn, ax in enumerate(axs.flat):
        ax.set_xlabel('Boo')
        ax.set_xlabel('Who')
        ax.plot(np.arange(4)**nn, np.arange(4)**nn)
    fig.align_ylabels()
    fig.align_xlabels()
    fig.draw_without_rendering()
    xn = np.zeros(4)
    yn = np.zeros(4)
    for nn, ax in enumerate(axs.flat):
        yn[nn] = ax.xaxis.label.get_position()[1]
        xn[nn] = ax.yaxis.label.get_position()[0]
    np.testing.assert_allclose(xn[:2], xn[2:])
    np.testing.assert_allclose(yn[::2], yn[1::2])

    fig, axs = plt.subplots(2, 2, constrained_layout=True)
    for nn, ax in enumerate(axs.flat):
        ax.set_xlabel('Boo')
        ax.set_xlabel('Who')
        pc = ax.pcolormesh(np.random.randn(10, 10))
    fig.colorbar(pc, ax=ax)
    fig.align_ylabels()
    fig.align_xlabels()
    fig.draw_without_rendering()
    xn = np.zeros(4)
    yn = np.zeros(4)
    for nn, ax in enumerate(axs.flat):
        yn[nn] = ax.xaxis.label.get_position()[1]
        xn[nn] = ax.yaxis.label.get_position()[0]
    np.testing.assert_allclose(xn[:2], xn[2:])
    np.testing.assert_allclose(yn[::2], yn[1::2])


def test_figure_label():
    # pyplot figure creation, selection, and closing with label/number/instance
    plt.close('all')
    fig_today = plt.figure('today')
    plt.figure(3)
    plt.figure('tomorrow')
    plt.figure()
    plt.figure(0)
    plt.figure(1)
    plt.figure(3)
    assert plt.get_fignums() == [0, 1, 3, 4, 5]
    assert plt.get_figlabels() == ['', 'today', '', 'tomorrow', '']
    plt.close(10)
    plt.close()
    plt.close(5)
    plt.close('tomorrow')
    assert plt.get_fignums() == [0, 1]
    assert plt.get_figlabels() == ['', 'today']
    plt.figure(fig_today)
    assert plt.gcf() == fig_today
    with pytest.raises(ValueError):
        plt.figure(Figure())


def test_figure_label_replaced():
    plt.close('all')
    fig = plt.figure(1)
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match="Changing 'Figure.number' is deprecated"):
        fig.number = 2
    assert fig.number == 2


def test_figure_no_label():
    # standalone figures do not have a figure attribute
    fig = Figure()
    with pytest.raises(AttributeError):
        fig.number
    # but one can set one
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match="Changing 'Figure.number' is deprecated"):
        fig.number = 5
    assert fig.number == 5
    # even though it's not known by pyplot
    assert not plt.fignum_exists(fig.number)


def test_fignum_exists():
    # pyplot figure creation, selection and closing with fignum_exists
    plt.figure('one')
    plt.figure(2)
    plt.figure('three')
    plt.figure()
    assert plt.fignum_exists('one')
    assert plt.fignum_exists(2)
    assert plt.fignum_exists('three')
    assert plt.fignum_exists(4)
    plt.close('one')
    plt.close(4)
    assert not plt.fignum_exists('one')
    assert not plt.fignum_exists(4)


def test_clf_keyword():
    # test if existing figure is cleared with figure() and subplots()
    text1 = 'A fancy plot'
    text2 = 'Really fancy!'

    fig0 = plt.figure(num=1)
    fig0.suptitle(text1)
    assert [t.get_text() for t in fig0.texts] == [text1]

    fig1 = plt.figure(num=1, clear=False)
    fig1.text(0.5, 0.5, text2)
    assert fig0 is fig1
    assert [t.get_text() for t in fig1.texts] == [text1, text2]

    fig2, ax2 = plt.subplots(2, 1, num=1, clear=True)
    assert fig0 is fig2
    assert [t.get_text() for t in fig2.texts] == []


@image_comparison(['figure_today.png'],
                  tol=0 if platform.machine() == 'x86_64' else 0.015)
def test_figure():
    # named figure support
    fig = plt.figure('today')
    ax = fig.add_subplot()
    ax.set_title(fig.get_label())
    ax.plot(np.arange(5))
    # plot red line in a different figure.
    plt.figure('tomorrow')
    plt.plot([0, 1], [1, 0], 'r')
    # Return to the original; make sure the red line is not there.
    plt.figure('today')
    plt.close('tomorrow')


@image_comparison(['figure_legend.png'])
def test_figure_legend():
    fig, axs = plt.subplots(2)
    axs[0].plot([0, 1], [1, 0], label='x', color='g')
    axs[0].plot([0, 1], [0, 1], label='y', color='r')
    axs[0].plot([0, 1], [0.5, 0.5], label='y', color='k')

    axs[1].plot([0, 1], [1, 0], label='_y', color='r')
    axs[1].plot([0, 1], [0, 1], label='z', color='b')
    fig.legend()


def test_gca():
    fig = plt.figure()

    # test that gca() picks up Axes created via add_axes()
    ax0 = fig.add_axes([0, 0, 1, 1])
    assert fig.gca() is ax0

    # test that gca() picks up Axes created via add_subplot()
    ax1 = fig.add_subplot(111)
    assert fig.gca() is ax1

    # add_axes on an existing Axes should not change stored order, but will
    # make it current.
    fig.add_axes(ax0)
    assert fig.axes == [ax0, ax1]
    assert fig.gca() is ax0

    # sca() should not change stored order of Axes, which is order added.
    fig.sca(ax0)
    assert fig.axes == [ax0, ax1]

    # add_subplot on an existing Axes should not change stored order, but will
    # make it current.
    fig.add_subplot(ax1)
    assert fig.axes == [ax0, ax1]
    assert fig.gca() is ax1


def test_add_subplot_subclass():
    fig = plt.figure()
    fig.add_subplot(axes_class=Axes)
    with pytest.raises(ValueError):
        fig.add_subplot(axes_class=Axes, projection="3d")
    with pytest.raises(ValueError):
        fig.add_subplot(axes_class=Axes, polar=True)
    with pytest.raises(ValueError):
        fig.add_subplot(projection="3d", polar=True)
    with pytest.raises(TypeError):
        fig.add_subplot(projection=42)


def test_add_subplot_invalid():
    fig = plt.figure()
    with pytest.raises(ValueError,
                       match='Number of columns must be a positive integer'):
        fig.add_subplot(2, 0, 1)
    with pytest.raises(ValueError,
                       match='Number of rows must be a positive integer'):
        fig.add_subplot(0, 2, 1)
    with pytest.raises(ValueError, match='num must be an integer with '
                                         '1 <= num <= 4'):
        fig.add_subplot(2, 2, 0)
    with pytest.raises(ValueError, match='num must be an integer with '
                                         '1 <= num <= 4'):
        fig.add_subplot(2, 2, 5)
    with pytest.raises(ValueError, match='num must be an integer with '
                                         '1 <= num <= 4'):
        fig.add_subplot(2, 2, 0.5)

    with pytest.raises(ValueError, match='must be a three-digit integer'):
        fig.add_subplot(42)
    with pytest.raises(ValueError, match='must be a three-digit integer'):
        fig.add_subplot(1000)

    with pytest.raises(TypeError, match='takes 1 or 3 positional arguments '
                                        'but 2 were given'):
        fig.add_subplot(2, 2)
    with pytest.raises(TypeError, match='takes 1 or 3 positional arguments '
                                        'but 4 were given'):
        fig.add_subplot(1, 2, 3, 4)
    with pytest.raises(ValueError,
                       match="Number of rows must be a positive integer, "
                             "not '2'"):
        fig.add_subplot('2', 2, 1)
    with pytest.raises(ValueError,
                       match='Number of columns must be a positive integer, '
                             'not 2.0'):
        fig.add_subplot(2, 2.0, 1)
    _, ax = plt.subplots()
    with pytest.raises(ValueError,
                       match='The Axes must have been created in the '
                             'present figure'):
        fig.add_subplot(ax)


@image_comparison(['figure_suptitle.png'])
def test_suptitle():
    fig, _ = plt.subplots()
    fig.suptitle('hello', color='r')
    fig.suptitle('title', color='g', rotation=30)


def test_suptitle_fontproperties():
    fig, ax = plt.subplots()
    fps = mpl.font_manager.FontProperties(size='large', weight='bold')
    txt = fig.suptitle('fontprops title', fontproperties=fps)
    assert txt.get_fontsize() == fps.get_size_in_points()
    assert txt.get_weight() == fps.get_weight()


def test_suptitle_subfigures():
    fig = plt.figure(figsize=(4, 3))
    sf1, sf2 = fig.subfigures(1, 2)
    sf2.set_facecolor('white')
    sf1.subplots()
    sf2.subplots()
    fig.suptitle("This is a visible suptitle.")

    # verify the first subfigure facecolor is the default transparent
    assert sf1.get_facecolor() == (0.0, 0.0, 0.0, 0.0)
    # verify the second subfigure facecolor is white
    assert sf2.get_facecolor() == (1.0, 1.0, 1.0, 1.0)


def test_get_suptitle_supxlabel_supylabel():
    fig, ax = plt.subplots()
    assert fig.get_suptitle() == ""
    assert fig.get_supxlabel() == ""
    assert fig.get_supylabel() == ""
    fig.suptitle('suptitle')
    assert fig.get_suptitle() == 'suptitle'
    fig.supxlabel('supxlabel')
    assert fig.get_supxlabel() == 'supxlabel'
    fig.supylabel('supylabel')
    assert fig.get_supylabel() == 'supylabel'


@image_comparison(['alpha_background'],
                  # only test png and svg. The PDF output appears correct,
                  # but Ghostscript does not preserve the background color.
                  extensions=['png', 'svg'],
                  savefig_kwarg={'facecolor': (0, 1, 0.4),
                                 'edgecolor': 'none'})
def test_alpha():
    # We want an image which has a background color and an alpha of 0.4.
    fig = plt.figure(figsize=[2, 1])
    fig.set_facecolor((0, 1, 0.4))
    fig.patch.set_alpha(0.4)
    fig.patches.append(mpl.patches.CirclePolygon(
        [20, 20], radius=15, alpha=0.6, facecolor='red'))


def test_too_many_figures():
    with pytest.warns(RuntimeWarning):
        for i in range(mpl.rcParams['figure.max_open_warning'] + 1):
            plt.figure()


def test_iterability_axes_argument():

    # This is a regression test for matplotlib/matplotlib#3196. If one of the
    # arguments returned by _as_mpl_axes defines __getitem__ but is not
    # iterable, this would raise an exception. This is because we check
    # whether the arguments are iterable, and if so we try and convert them
    # to a tuple. However, the ``iterable`` function returns True if
    # __getitem__ is present, but some classes can define __getitem__ without
    # being iterable. The tuple conversion is now done in a try...except in
    # case it fails.

    class MyAxes(Axes):
        def __init__(self, *args, myclass=None, **kwargs):
            Axes.__init__(self, *args, **kwargs)

    class MyClass:

        def __getitem__(self, item):
            if item != 'a':
                raise ValueError("item should be a")

        def _as_mpl_axes(self):
            return MyAxes, {'myclass': self}

    fig = plt.figure()
    fig.add_subplot(1, 1, 1, projection=MyClass())
    plt.close(fig)


def test_set_fig_size():
    fig = plt.figure()

    # check figwidth
    fig.set_figwidth(5)
    assert fig.get_figwidth() == 5

    # check figheight
    fig.set_figheight(1)
    assert fig.get_figheight() == 1

    # check using set_size_inches
    fig.set_size_inches(2, 4)
    assert fig.get_figwidth() == 2
    assert fig.get_figheight() == 4

    # check using tuple to first argument
    fig.set_size_inches((1, 3))
    assert fig.get_figwidth() == 1
    assert fig.get_figheight() == 3


def test_axes_remove():
    fig, axs = plt.subplots(2, 2)
    axs[-1, -1].remove()
    for ax in axs.ravel()[:-1]:
        assert ax in fig.axes
    assert axs[-1, -1] not in fig.axes
    assert len(fig.axes) == 3


def test_figaspect():
    w, h = plt.figaspect(np.float64(2) / np.float64(1))
    assert h / w == 2
    w, h = plt.figaspect(2)
    assert h / w == 2
    w, h = plt.figaspect(np.zeros((1, 2)))
    assert h / w == 0.5
    w, h = plt.figaspect(np.zeros((2, 2)))
    assert h / w == 1


@pytest.mark.parametrize('which', ['both', 'major', 'minor'])
def test_autofmt_xdate(which):
    date = ['3 Jan 2013', '4 Jan 2013', '5 Jan 2013', '6 Jan 2013',
            '7 Jan 2013', '8 Jan 2013', '9 Jan 2013', '10 Jan 2013',
            '11 Jan 2013', '12 Jan 2013', '13 Jan 2013', '14 Jan 2013']

    time = ['16:44:00', '16:45:00', '16:46:00', '16:47:00', '16:48:00',
            '16:49:00', '16:51:00', '16:52:00', '16:53:00', '16:55:00',
            '16:56:00', '16:57:00']

    angle = 60
    minors = [1, 2, 3, 4, 5, 6, 7]

    x = mdates.datestr2num(date)
    y = mdates.datestr2num(time)

    fig, ax = plt.subplots()

    ax.plot(x, y)
    ax.yaxis_date()
    ax.xaxis_date()

    ax.xaxis.set_minor_locator(AutoMinorLocator(2))
    with warnings.catch_warnings():
        warnings.filterwarnings(
            'ignore',
            'FixedFormatter should only be used together with FixedLocator')
        ax.xaxis.set_minor_formatter(FixedFormatter(minors))

    fig.autofmt_xdate(0.2, angle, 'right', which)

    if which in ('both', 'major'):
        for label in fig.axes[0].get_xticklabels(False, 'major'):
            assert int(label.get_rotation()) == angle

    if which in ('both', 'minor'):
        for label in fig.axes[0].get_xticklabels(True, 'minor'):
            assert int(label.get_rotation()) == angle


def test_autofmt_xdate_colorbar_constrained():
    # check works with a colorbar.
    # with constrained layout, colorbars do not have a gridspec,
    # but autofmt_xdate checks if all axes have a gridspec before being
    # applied.
    fig, ax = plt.subplots(layout="constrained")
    im = ax.imshow([[1, 4, 6], [2, 3, 5]])
    plt.colorbar(im)
    fig.autofmt_xdate()
    fig.draw_without_rendering()
    label = ax.get_xticklabels(which='major')[1]
    assert label.get_rotation() == 30.0


@mpl.style.context('default')
def test_change_dpi():
    fig = plt.figure(figsize=(4, 4))
    fig.draw_without_rendering()
    assert fig.canvas.renderer.height == 400
    assert fig.canvas.renderer.width == 400
    fig.dpi = 50
    fig.draw_without_rendering()
    assert fig.canvas.renderer.height == 200
    assert fig.canvas.renderer.width == 200


@pytest.mark.parametrize('width, height', [
    (1, np.nan),
    (-1, 1),
    (np.inf, 1)
])
def test_invalid_figure_size(width, height):
    with pytest.raises(ValueError):
        plt.figure(figsize=(width, height))

    fig = plt.figure()
    with pytest.raises(ValueError):
        fig.set_size_inches(width, height)


def test_invalid_figure_add_axes():
    fig = plt.figure()
    with pytest.raises(TypeError,
                       match="missing 1 required positional argument: 'rect'"):
        fig.add_axes()

    with pytest.raises(ValueError):
        fig.add_axes((.1, .1, .5, np.nan))

    with pytest.raises(TypeError, match="multiple values for argument 'rect'"):
        fig.add_axes([0, 0, 1, 1], rect=[0, 0, 1, 1])

    fig2, ax = plt.subplots()
    with pytest.raises(ValueError,
                       match="The Axes must have been created in the present "
                             "figure"):
        fig.add_axes(ax)

    fig2.delaxes(ax)
    with pytest.raises(TypeError, match=r"add_axes\(\) takes 1 positional arguments"):
        fig2.add_axes(ax, "extra positional argument")

    with pytest.raises(TypeError, match=r"add_axes\(\) takes 1 positional arguments"):
        fig.add_axes([0, 0, 1, 1], "extra positional argument")


def test_subplots_shareax_loglabels():
    fig, axs = plt.subplots(2, 2, sharex=True, sharey=True, squeeze=False)
    for ax in axs.flat:
        ax.plot([10, 20, 30], [10, 20, 30])

    ax.set_yscale("log")
    ax.set_xscale("log")

    for ax in axs[0, :]:
        assert 0 == len(ax.xaxis.get_ticklabels(which='both'))

    for ax in axs[1, :]:
        assert 0 < len(ax.xaxis.get_ticklabels(which='both'))

    for ax in axs[:, 1]:
        assert 0 == len(ax.yaxis.get_ticklabels(which='both'))

    for ax in axs[:, 0]:
        assert 0 < len(ax.yaxis.get_ticklabels(which='both'))


def test_savefig():
    fig = plt.figure()
    msg = r"savefig\(\) takes 2 positional arguments but 3 were given"
    with pytest.raises(TypeError, match=msg):
        fig.savefig("fname1.png", "fname2.png")


def test_savefig_warns():
    fig = plt.figure()
    for format in ['png', 'pdf', 'svg', 'tif', 'jpg']:
        with pytest.raises(TypeError):
            fig.savefig(io.BytesIO(), format=format, non_existent_kwarg=True)


def test_savefig_backend():
    fig = plt.figure()
    # Intentionally use an invalid module name.
    with pytest.raises(ModuleNotFoundError, match="No module named '@absent'"):
        fig.savefig("test", backend="module://@absent")
    with pytest.raises(ValueError,
                       match="The 'pdf' backend does not support png output"):
        fig.savefig("test.png", backend="pdf")


@pytest.mark.parametrize('backend', [
    pytest.param('Agg', marks=[pytest.mark.backend('Agg')]),
    pytest.param('Cairo', marks=[pytest.mark.backend('Cairo')]),
])
def test_savefig_pixel_ratio(backend):
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3])
    with io.BytesIO() as buf:
        fig.savefig(buf, format='png')
        ratio1 = Image.open(buf)
        ratio1.load()

    fig, ax = plt.subplots()
    ax.plot([1, 2, 3])
    fig.canvas._set_device_pixel_ratio(2)
    with io.BytesIO() as buf:
        fig.savefig(buf, format='png')
        ratio2 = Image.open(buf)
        ratio2.load()

    assert ratio1 == ratio2


def test_savefig_preserve_layout_engine():
    fig = plt.figure(layout='compressed')
    fig.savefig(io.BytesIO(), bbox_inches='tight')

    assert fig.get_layout_engine()._compress


def test_savefig_locate_colorbar():
    fig, ax = plt.subplots()
    pc = ax.pcolormesh(np.random.randn(2, 2))
    cbar = fig.colorbar(pc, aspect=40)
    fig.savefig(io.BytesIO(), bbox_inches=mpl.transforms.Bbox([[0, 0], [4, 4]]))

    # Check that an aspect ratio has been applied.
    assert (cbar.ax.get_position(original=True).bounds !=
            cbar.ax.get_position(original=False).bounds)


@mpl.rc_context({"savefig.transparent": True})
@check_figures_equal(extensions=["png"])
def test_savefig_transparent(fig_test, fig_ref):
    # create two transparent subfigures with corresponding transparent inset
    # axes. the entire background of the image should be transparent.
    gs1 = fig_test.add_gridspec(3, 3, left=0.05, wspace=0.05)
    f1 = fig_test.add_subfigure(gs1[:, :])
    f2 = f1.add_subfigure(gs1[0, 0])

    ax12 = f2.add_subplot(gs1[:, :])

    ax1 = f1.add_subplot(gs1[:-1, :])
    iax1 = ax1.inset_axes([.1, .2, .3, .4])
    iax2 = iax1.inset_axes([.1, .2, .3, .4])

    ax2 = fig_test.add_subplot(gs1[-1, :-1])
    ax3 = fig_test.add_subplot(gs1[-1, -1])

    for ax in [ax12, ax1, iax1, iax2, ax2, ax3]:
        ax.set(xticks=[], yticks=[])
        ax.spines[:].set_visible(False)


def test_figure_repr():
    fig = plt.figure(figsize=(10, 20), dpi=10)
    assert repr(fig) == "<Figure size 100x200 with 0 Axes>"


def test_valid_layouts():
    fig = Figure(layout=None)
    assert not fig.get_tight_layout()
    assert not fig.get_constrained_layout()

    fig = Figure(layout='tight')
    assert fig.get_tight_layout()
    assert not fig.get_constrained_layout()

    fig = Figure(layout='constrained')
    assert not fig.get_tight_layout()
    assert fig.get_constrained_layout()


def test_invalid_layouts():
    fig, ax = plt.subplots(layout="constrained")
    with pytest.warns(UserWarning):
        # this should warn,
        fig.subplots_adjust(top=0.8)
    assert isinstance(fig.get_layout_engine(), ConstrainedLayoutEngine)

    # Using layout + (tight|constrained)_layout warns, but the former takes
    # precedence.
    wst = "The Figure parameters 'layout' and 'tight_layout'"
    with pytest.warns(UserWarning, match=wst):
        fig = Figure(layout='tight', tight_layout=False)
    assert isinstance(fig.get_layout_engine(), TightLayoutEngine)
    wst = "The Figure parameters 'layout' and 'constrained_layout'"
    with pytest.warns(UserWarning, match=wst):
        fig = Figure(layout='constrained', constrained_layout=False)
    assert not isinstance(fig.get_layout_engine(), TightLayoutEngine)
    assert isinstance(fig.get_layout_engine(), ConstrainedLayoutEngine)

    with pytest.raises(ValueError,
                       match="Invalid value for 'layout'"):
        Figure(layout='foobar')

    # test that layouts can be swapped if no colorbar:
    fig, ax = plt.subplots(layout="constrained")
    fig.set_layout_engine("tight")
    assert isinstance(fig.get_layout_engine(), TightLayoutEngine)
    fig.set_layout_engine("constrained")
    assert isinstance(fig.get_layout_engine(), ConstrainedLayoutEngine)

    # test that layouts cannot be swapped if there is a colorbar:
    fig, ax = plt.subplots(layout="constrained")
    pc = ax.pcolormesh(np.random.randn(2, 2))
    fig.colorbar(pc)
    with pytest.raises(RuntimeError, match='Colorbar layout of new layout'):
        fig.set_layout_engine("tight")
    fig.set_layout_engine("none")
    with pytest.raises(RuntimeError, match='Colorbar layout of new layout'):
        fig.set_layout_engine("tight")

    fig, ax = plt.subplots(layout="tight")
    pc = ax.pcolormesh(np.random.randn(2, 2))
    fig.colorbar(pc)
    with pytest.raises(RuntimeError, match='Colorbar layout of new layout'):
        fig.set_layout_engine("constrained")
    fig.set_layout_engine("none")
    assert isinstance(fig.get_layout_engine(), PlaceHolderLayoutEngine)

    with pytest.raises(RuntimeError, match='Colorbar layout of new layout'):
        fig.set_layout_engine("constrained")


@check_figures_equal(extensions=["png"])
def test_tightlayout_autolayout_deconflict(fig_test, fig_ref):
    for fig, autolayout in zip([fig_ref, fig_test], [False, True]):
        with mpl.rc_context({'figure.autolayout': autolayout}):
            axes = fig.subplots(ncols=2)
            fig.tight_layout(w_pad=10)
        assert isinstance(fig.get_layout_engine(), PlaceHolderLayoutEngine)


@pytest.mark.parametrize('layout', ['constrained', 'compressed'])
def test_layout_change_warning(layout):
    """
    Raise a warning when a previously assigned layout changes to tight using
    plt.tight_layout().
    """
    fig, ax = plt.subplots(layout=layout)
    with pytest.warns(UserWarning, match='The figure layout has changed to'):
        plt.tight_layout()


def test_repeated_tightlayout():
    fig = Figure()
    fig.tight_layout()
    # subsequent calls should not warn
    fig.tight_layout()
    fig.tight_layout()


@check_figures_equal(extensions=["png", "pdf"])
def test_add_artist(fig_test, fig_ref):
    fig_test.dpi = 100
    fig_ref.dpi = 100

    fig_test.subplots()
    l1 = plt.Line2D([.2, .7], [.7, .7], gid='l1')
    l2 = plt.Line2D([.2, .7], [.8, .8], gid='l2')
    r1 = plt.Circle((20, 20), 100, transform=None, gid='C1')
    r2 = plt.Circle((.7, .5), .05, gid='C2')
    r3 = plt.Circle((4.5, .8), .55, transform=fig_test.dpi_scale_trans,
                    facecolor='crimson', gid='C3')
    for a in [l1, l2, r1, r2, r3]:
        fig_test.add_artist(a)
    l2.remove()

    ax2 = fig_ref.subplots()
    l1 = plt.Line2D([.2, .7], [.7, .7], transform=fig_ref.transFigure,
                    gid='l1', zorder=21)
    r1 = plt.Circle((20, 20), 100, transform=None, clip_on=False, zorder=20,
                    gid='C1')
    r2 = plt.Circle((.7, .5), .05, transform=fig_ref.transFigure, gid='C2',
                    zorder=20)
    r3 = plt.Circle((4.5, .8), .55, transform=fig_ref.dpi_scale_trans,
                    facecolor='crimson', clip_on=False, zorder=20, gid='C3')
    for a in [l1, r1, r2, r3]:
        ax2.add_artist(a)


@pytest.mark.parametrize("fmt", ["png", "pdf", "ps", "eps", "svg"])
def test_fspath(fmt, tmp_path):
    out = tmp_path / f"test.{fmt}"
    plt.savefig(out)
    with out.open("rb") as file:
        # All the supported formats include the format name (case-insensitive)
        # in the first 100 bytes.
        assert fmt.encode("ascii") in file.read(100).lower()


def test_tightbbox():
    fig, ax = plt.subplots()
    ax.set_xlim(0, 1)
    t = ax.text(1., 0.5, 'This dangles over end')
    renderer = fig.canvas.get_renderer()
    x1Nom0 = 9.035  # inches
    assert abs(t.get_tightbbox(renderer).x1 - x1Nom0 * fig.dpi) < 2
    assert abs(ax.get_tightbbox(renderer).x1 - x1Nom0 * fig.dpi) < 2
    assert abs(fig.get_tightbbox(renderer).x1 - x1Nom0) < 0.05
    assert abs(fig.get_tightbbox(renderer).x0 - 0.679) < 0.05
    # now exclude t from the tight bbox so now the bbox is quite a bit
    # smaller
    t.set_in_layout(False)
    x1Nom = 7.333
    assert abs(ax.get_tightbbox(renderer).x1 - x1Nom * fig.dpi) < 2
    assert abs(fig.get_tightbbox(renderer).x1 - x1Nom) < 0.05

    t.set_in_layout(True)
    x1Nom = 7.333
    assert abs(ax.get_tightbbox(renderer).x1 - x1Nom0 * fig.dpi) < 2
    # test bbox_extra_artists method...
    assert abs(ax.get_tightbbox(renderer, bbox_extra_artists=[]).x1
               - x1Nom * fig.dpi) < 2


def test_axes_removal():
    # Check that units can set the formatter after an Axes removal
    fig, axs = plt.subplots(1, 2, sharex=True)
    axs[1].remove()
    axs[0].plot([datetime(2000, 1, 1), datetime(2000, 2, 1)], [0, 1])
    assert isinstance(axs[0].xaxis.get_major_formatter(),
                      mdates.AutoDateFormatter)

    # Check that manually setting the formatter, then removing Axes keeps
    # the set formatter.
    fig, axs = plt.subplots(1, 2, sharex=True)
    axs[1].xaxis.set_major_formatter(ScalarFormatter())
    axs[1].remove()
    axs[0].plot([datetime(2000, 1, 1), datetime(2000, 2, 1)], [0, 1])
    assert isinstance(axs[0].xaxis.get_major_formatter(),
                      ScalarFormatter)


def test_removed_axis():
    # Simple smoke test to make sure removing a shared axis works
    fig, axs = plt.subplots(2, sharex=True)
    axs[0].remove()
    fig.canvas.draw()


@pytest.mark.parametrize('clear_meth', ['clear', 'clf'])
def test_figure_clear(clear_meth):
    # we test the following figure clearing scenarios:
    fig = plt.figure()

    # a) an empty figure
    fig.clear()
    assert fig.axes == []

    # b) a figure with a single unnested axes
    ax = fig.add_subplot(111)
    getattr(fig, clear_meth)()
    assert fig.axes == []

    # c) a figure multiple unnested axes
    axes = [fig.add_subplot(2, 1, i+1) for i in range(2)]
    getattr(fig, clear_meth)()
    assert fig.axes == []

    # d) a figure with a subfigure
    gs = fig.add_gridspec(ncols=2, nrows=1)
    subfig = fig.add_subfigure(gs[0])
    subaxes = subfig.add_subplot(111)
    getattr(fig, clear_meth)()
    assert subfig not in fig.subfigs
    assert fig.axes == []

    # e) a figure with a subfigure and a subplot
    subfig = fig.add_subfigure(gs[0])
    subaxes = subfig.add_subplot(111)
    mainaxes = fig.add_subplot(gs[1])

    # e.1) removing just the axes leaves the subplot
    mainaxes.remove()
    assert fig.axes == [subaxes]

    # e.2) removing just the subaxes leaves the subplot
    # and subfigure
    mainaxes = fig.add_subplot(gs[1])
    subaxes.remove()
    assert fig.axes == [mainaxes]
    assert subfig in fig.subfigs

    # e.3) clearing the subfigure leaves the subplot
    subaxes = subfig.add_subplot(111)
    assert mainaxes in fig.axes
    assert subaxes in fig.axes
    getattr(subfig, clear_meth)()
    assert subfig in fig.subfigs
    assert subaxes not in subfig.axes
    assert subaxes not in fig.axes
    assert mainaxes in fig.axes

    # e.4) clearing the whole thing
    subaxes = subfig.add_subplot(111)
    getattr(fig, clear_meth)()
    assert fig.axes == []
    assert fig.subfigs == []

    # f) multiple subfigures
    subfigs = [fig.add_subfigure(gs[i]) for i in [0, 1]]
    subaxes = [sfig.add_subplot(111) for sfig in subfigs]
    assert all(ax in fig.axes for ax in subaxes)
    assert all(sfig in fig.subfigs for sfig in subfigs)

    # f.1) clearing only one subfigure
    getattr(subfigs[0], clear_meth)()
    assert subaxes[0] not in fig.axes
    assert subaxes[1] in fig.axes
    assert subfigs[1] in fig.subfigs

    # f.2) clearing the whole thing
    getattr(subfigs[1], clear_meth)()
    subfigs = [fig.add_subfigure(gs[i]) for i in [0, 1]]
    subaxes = [sfig.add_subplot(111) for sfig in subfigs]
    assert all(ax in fig.axes for ax in subaxes)
    assert all(sfig in fig.subfigs for sfig in subfigs)
    getattr(fig, clear_meth)()
    assert fig.subfigs == []
    assert fig.axes == []


def test_clf_not_redefined():
    for klass in FigureBase.__subclasses__():
        # check that subclasses do not get redefined in our Figure subclasses
        assert 'clf' not in klass.__dict__


@mpl.style.context('mpl20')
def test_picking_does_not_stale():
    fig, ax = plt.subplots()
    ax.scatter([0], [0], [1000], picker=True)
    fig.canvas.draw()
    assert not fig.stale

    mouse_event = SimpleNamespace(x=ax.bbox.x0 + ax.bbox.width / 2,
                                  y=ax.bbox.y0 + ax.bbox.height / 2,
                                  inaxes=ax, guiEvent=None)
    fig.pick(mouse_event)
    assert not fig.stale


def test_add_subplot_twotuple():
    fig = plt.figure()
    ax1 = fig.add_subplot(3, 2, (3, 5))
    assert ax1.get_subplotspec().rowspan == range(1, 3)
    assert ax1.get_subplotspec().colspan == range(0, 1)
    ax2 = fig.add_subplot(3, 2, (4, 6))
    assert ax2.get_subplotspec().rowspan == range(1, 3)
    assert ax2.get_subplotspec().colspan == range(1, 2)
    ax3 = fig.add_subplot(3, 2, (3, 6))
    assert ax3.get_subplotspec().rowspan == range(1, 3)
    assert ax3.get_subplotspec().colspan == range(0, 2)
    ax4 = fig.add_subplot(3, 2, (4, 5))
    assert ax4.get_subplotspec().rowspan == range(1, 3)
    assert ax4.get_subplotspec().colspan == range(0, 2)
    with pytest.raises(IndexError):
        fig.add_subplot(3, 2, (6, 3))


@image_comparison(['tightbbox_box_aspect.svg'], style='mpl20',
                  savefig_kwarg={'bbox_inches': 'tight',
                                 'facecolor': 'teal'},
                  remove_text=True)
def test_tightbbox_box_aspect():
    fig = plt.figure()
    gs = fig.add_gridspec(1, 2)
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1], projection='3d')
    ax1.set_box_aspect(.5)
    ax2.set_box_aspect((2, 1, 1))


@check_figures_equal(extensions=["svg", "pdf", "eps", "png"])
def test_animated_with_canvas_change(fig_test, fig_ref):
    ax_ref = fig_ref.subplots()
    ax_ref.plot(range(5))

    ax_test = fig_test.subplots()
    ax_test.plot(range(5), animated=True)


class TestSubplotMosaic:
    @check_figures_equal(extensions=["png"])
    @pytest.mark.parametrize(
        "x", [
            [["A", "A", "B"], ["C", "D", "B"]],
            [[1, 1, 2], [3, 4, 2]],
            (("A", "A", "B"), ("C", "D", "B")),
            ((1, 1, 2), (3, 4, 2))
        ]
    )
    def test_basic(self, fig_test, fig_ref, x):
        grid_axes = fig_test.subplot_mosaic(x)

        for k, ax in grid_axes.items():
            ax.set_title(k)

        labels = sorted(np.unique(x))

        assert len(labels) == len(grid_axes)

        gs = fig_ref.add_gridspec(2, 3)
        axA = fig_ref.add_subplot(gs[:1, :2])
        axA.set_title(labels[0])

        axB = fig_ref.add_subplot(gs[:, 2])
        axB.set_title(labels[1])

        axC = fig_ref.add_subplot(gs[1, 0])
        axC.set_title(labels[2])

        axD = fig_ref.add_subplot(gs[1, 1])
        axD.set_title(labels[3])

    @check_figures_equal(extensions=["png"])
    def test_all_nested(self, fig_test, fig_ref):
        x = [["A", "B"], ["C", "D"]]
        y = [["E", "F"], ["G", "H"]]

        fig_ref.set_layout_engine("constrained")
        fig_test.set_layout_engine("constrained")

        grid_axes = fig_test.subplot_mosaic([[x, y]])
        for ax in grid_axes.values():
            ax.set_title(ax.get_label())

        gs = fig_ref.add_gridspec(1, 2)
        gs_left = gs[0, 0].subgridspec(2, 2)
        for j, r in enumerate(x):
            for k, label in enumerate(r):
                fig_ref.add_subplot(gs_left[j, k]).set_title(label)

        gs_right = gs[0, 1].subgridspec(2, 2)
        for j, r in enumerate(y):
            for k, label in enumerate(r):
                fig_ref.add_subplot(gs_right[j, k]).set_title(label)

    @check_figures_equal(extensions=["png"])
    def test_nested(self, fig_test, fig_ref):

        fig_ref.set_layout_engine("constrained")
        fig_test.set_layout_engine("constrained")

        x = [["A", "B"], ["C", "D"]]

        y = [["F"], [x]]

        grid_axes = fig_test.subplot_mosaic(y)

        for k, ax in grid_axes.items():
            ax.set_title(k)

        gs = fig_ref.add_gridspec(2, 1)

        gs_n = gs[1, 0].subgridspec(2, 2)

        axA = fig_ref.add_subplot(gs_n[0, 0])
        axA.set_title("A")

        axB = fig_ref.add_subplot(gs_n[0, 1])
        axB.set_title("B")

        axC = fig_ref.add_subplot(gs_n[1, 0])
        axC.set_title("C")

        axD = fig_ref.add_subplot(gs_n[1, 1])
        axD.set_title("D")

        axF = fig_ref.add_subplot(gs[0, 0])
        axF.set_title("F")

    @check_figures_equal(extensions=["png"])
    def test_nested_tuple(self, fig_test, fig_ref):
        x = [["A", "B", "B"], ["C", "C", "D"]]
        xt = (("A", "B", "B"), ("C", "C", "D"))

        fig_ref.subplot_mosaic([["F"], [x]])
        fig_test.subplot_mosaic([["F"], [xt]])

    def test_nested_width_ratios(self):
        x = [["A", [["B"],
                    ["C"]]]]
        width_ratios = [2, 1]

        fig, axd = plt.subplot_mosaic(x, width_ratios=width_ratios)

        assert axd["A"].get_gridspec().get_width_ratios() == width_ratios
        assert axd["B"].get_gridspec().get_width_ratios() != width_ratios

    def test_nested_height_ratios(self):
        x = [["A", [["B"],
                    ["C"]]], ["D", "D"]]
        height_ratios = [1, 2]

        fig, axd = plt.subplot_mosaic(x, height_ratios=height_ratios)

        assert axd["D"].get_gridspec().get_height_ratios() == height_ratios
        assert axd["B"].get_gridspec().get_height_ratios() != height_ratios

    @check_figures_equal(extensions=["png"])
    @pytest.mark.parametrize(
        "x, empty_sentinel",
        [
            ([["A", None], [None, "B"]], None),
            ([["A", "."], [".", "B"]], "SKIP"),
            ([["A", 0], [0, "B"]], 0),
            ([[1, None], [None, 2]], None),
            ([[1, "."], [".", 2]], "SKIP"),
            ([[1, 0], [0, 2]], 0),
        ],
    )
    def test_empty(self, fig_test, fig_ref, x, empty_sentinel):
        if empty_sentinel != "SKIP":
            kwargs = {"empty_sentinel": empty_sentinel}
        else:
            kwargs = {}
        grid_axes = fig_test.subplot_mosaic(x, **kwargs)

        for k, ax in grid_axes.items():
            ax.set_title(k)

        labels = sorted(
            {name for row in x for name in row} - {empty_sentinel, "."}
        )

        assert len(labels) == len(grid_axes)

        gs = fig_ref.add_gridspec(2, 2)
        axA = fig_ref.add_subplot(gs[0, 0])
        axA.set_title(labels[0])

        axB = fig_ref.add_subplot(gs[1, 1])
        axB.set_title(labels[1])

    def test_fail_list_of_str(self):
        with pytest.raises(ValueError, match='must be 2D'):
            plt.subplot_mosaic(['foo', 'bar'])
        with pytest.raises(ValueError, match='must be 2D'):
            plt.subplot_mosaic(['foo'])
        with pytest.raises(ValueError, match='must be 2D'):
            plt.subplot_mosaic([['foo', ('bar',)]])
        with pytest.raises(ValueError, match='must be 2D'):
            plt.subplot_mosaic([['a', 'b'], [('a', 'b'), 'c']])

    @check_figures_equal(extensions=["png"])
    @pytest.mark.parametrize("subplot_kw", [{}, {"projection": "polar"}, None])
    def test_subplot_kw(self, fig_test, fig_ref, subplot_kw):
        x = [[1, 2]]
        grid_axes = fig_test.subplot_mosaic(x, subplot_kw=subplot_kw)
        subplot_kw = subplot_kw or {}

        gs = fig_ref.add_gridspec(1, 2)
        axA = fig_ref.add_subplot(gs[0, 0], **subplot_kw)

        axB = fig_ref.add_subplot(gs[0, 1], **subplot_kw)

    @check_figures_equal(extensions=["png"])
    @pytest.mark.parametrize("multi_value", ['BC', tuple('BC')])
    def test_per_subplot_kw(self, fig_test, fig_ref, multi_value):
        x = 'AB;CD'
        grid_axes = fig_test.subplot_mosaic(
            x,
            subplot_kw={'facecolor': 'red'},
            per_subplot_kw={
                'D': {'facecolor': 'blue'},
                multi_value: {'facecolor': 'green'},
            }
        )

        gs = fig_ref.add_gridspec(2, 2)
        for color, spec in zip(['red', 'green', 'green', 'blue'], gs):
            fig_ref.add_subplot(spec, facecolor=color)

    def test_string_parser(self):
        normalize = Figure._normalize_grid_string

        assert normalize('ABC') == [['A', 'B', 'C']]
        assert normalize('AB;CC') == [['A', 'B'], ['C', 'C']]
        assert normalize('AB;CC;DE') == [['A', 'B'], ['C', 'C'], ['D', 'E']]
        assert normalize("""
                         ABC
                         """) == [['A', 'B', 'C']]
        assert normalize("""
                         AB
                         CC
                         """) == [['A', 'B'], ['C', 'C']]
        assert normalize("""
                         AB
                         CC
                         DE
                         """) == [['A', 'B'], ['C', 'C'], ['D', 'E']]

    def test_per_subplot_kw_expander(self):
        normalize = Figure._norm_per_subplot_kw
        assert normalize({"A": {}, "B": {}}) == {"A": {}, "B": {}}
        assert normalize({("A", "B"): {}}) == {"A": {}, "B": {}}
        with pytest.raises(
                ValueError, match=f'The key {"B"!r} appears multiple times'
        ):
            normalize({("A", "B"): {}, "B": {}})
        with pytest.raises(
                ValueError, match=f'The key {"B"!r} appears multiple times'
        ):
            normalize({"B": {}, ("A", "B"): {}})

    def test_extra_per_subplot_kw(self):
        with pytest.raises(
                ValueError, match=f'The keys {set("B")!r} are in'
        ):
            Figure().subplot_mosaic("A", per_subplot_kw={"B": {}})

    @check_figures_equal(extensions=["png"])
    @pytest.mark.parametrize("str_pattern",
                             ["AAA\nBBB", "\nAAA\nBBB\n", "ABC\nDEF"]
                             )
    def test_single_str_input(self, fig_test, fig_ref, str_pattern):
        grid_axes = fig_test.subplot_mosaic(str_pattern)

        grid_axes = fig_ref.subplot_mosaic(
            [list(ln) for ln in str_pattern.strip().split("\n")]
        )

    @pytest.mark.parametrize(
        "x,match",
        [
            (
                [["A", "."], [".", "A"]],
                (
                    "(?m)we found that the label .A. specifies a "
                    + "non-rectangular or non-contiguous area."
                ),
            ),
            (
                [["A", "B"], [None, [["A", "B"], ["C", "D"]]]],
                "There are duplicate keys .* between the outer layout",
            ),
            ("AAA\nc\nBBB", "All of the rows must be the same length"),
            (
                [["A", [["B", "C"], ["D"]]], ["E", "E"]],
                "All of the rows must be the same length",
            ),
        ],
    )
    def test_fail(self, x, match):
        fig = plt.figure()
        with pytest.raises(ValueError, match=match):
            fig.subplot_mosaic(x)

    @check_figures_equal(extensions=["png"])
    def test_hashable_keys(self, fig_test, fig_ref):
        fig_test.subplot_mosaic([[object(), object()]])
        fig_ref.subplot_mosaic([["A", "B"]])

    @pytest.mark.parametrize('str_pattern',
                             ['abc', 'cab', 'bca', 'cba', 'acb', 'bac'])
    def test_user_order(self, str_pattern):
        fig = plt.figure()
        ax_dict = fig.subplot_mosaic(str_pattern)
        assert list(str_pattern) == list(ax_dict)
        assert list(fig.axes) == list(ax_dict.values())

    def test_nested_user_order(self):
        layout = [
            ["A", [["B", "C"],
                   ["D", "E"]]],
            ["F", "G"],
            [".", [["H", [["I"],
                          ["."]]]]]
        ]

        fig = plt.figure()
        ax_dict = fig.subplot_mosaic(layout)
        assert list(ax_dict) == list("ABCDEFGHI")
        assert list(fig.axes) == list(ax_dict.values())

    def test_share_all(self):
        layout = [
            ["A", [["B", "C"],
                   ["D", "E"]]],
            ["F", "G"],
            [".", [["H", [["I"],
                          ["."]]]]]
        ]
        fig = plt.figure()
        ax_dict = fig.subplot_mosaic(layout, sharex=True, sharey=True)
        ax_dict["A"].set(xscale="log", yscale="logit")
        assert all(ax.get_xscale() == "log" and ax.get_yscale() == "logit"
                   for ax in ax_dict.values())


def test_reused_gridspec():
    """Test that these all use the same gridspec"""
    fig = plt.figure()
    ax1 = fig.add_subplot(3, 2, (3, 5))
    ax2 = fig.add_subplot(3, 2, 4)
    ax3 = plt.subplot2grid((3, 2), (2, 1), colspan=2, fig=fig)

    gs1 = ax1.get_subplotspec().get_gridspec()
    gs2 = ax2.get_subplotspec().get_gridspec()
    gs3 = ax3.get_subplotspec().get_gridspec()

    assert gs1 == gs2
    assert gs1 == gs3


@image_comparison(['test_subfigure.png'], style='mpl20',
                  savefig_kwarg={'facecolor': 'teal'})
def test_subfigure():
    np.random.seed(19680801)
    fig = plt.figure(layout='constrained')
    sub = fig.subfigures(1, 2)

    axs = sub[0].subplots(2, 2)
    for ax in axs.flat:
        pc = ax.pcolormesh(np.random.randn(30, 30), vmin=-2, vmax=2)
    sub[0].colorbar(pc, ax=axs)
    sub[0].suptitle('Left Side')
    sub[0].set_facecolor('white')

    axs = sub[1].subplots(1, 3)
    for ax in axs.flat:
        pc = ax.pcolormesh(np.random.randn(30, 30), vmin=-2, vmax=2)
    sub[1].colorbar(pc, ax=axs, location='bottom')
    sub[1].suptitle('Right Side')
    sub[1].set_facecolor('white')

    fig.suptitle('Figure suptitle', fontsize='xx-large')

    # below tests for the draw zorder of subfigures.
    leg = fig.legend(handles=[plt.Line2D([0], [0], label='Line{}'.format(i))
                     for i in range(5)], loc='center')
    sub[0].set_zorder(leg.get_zorder() - 1)
    sub[1].set_zorder(leg.get_zorder() + 1)


def test_subfigure_tightbbox():
    # test that we can get the tightbbox with a subfigure...
    fig = plt.figure(layout='constrained')
    sub = fig.subfigures(1, 2)

    np.testing.assert_allclose(
            fig.get_tightbbox(fig.canvas.get_renderer()).width,
            8.0)


def test_subfigure_dpi():
    fig = plt.figure(dpi=100)
    sub_fig = fig.subfigures()
    assert sub_fig.get_dpi() == fig.get_dpi()

    sub_fig.set_dpi(200)
    assert sub_fig.get_dpi() == 200
    assert fig.get_dpi() == 200


@image_comparison(['test_subfigure_ss.png'], style='mpl20',
                  savefig_kwarg={'facecolor': 'teal'}, tol=0.02)
def test_subfigure_ss():
    # test assigning the subfigure via subplotspec
    np.random.seed(19680801)
    fig = plt.figure(layout='constrained')
    gs = fig.add_gridspec(1, 2)

    sub = fig.add_subfigure(gs[0], facecolor='pink')

    axs = sub.subplots(2, 2)
    for ax in axs.flat:
        pc = ax.pcolormesh(np.random.randn(30, 30), vmin=-2, vmax=2)
    sub.colorbar(pc, ax=axs)
    sub.suptitle('Left Side')

    ax = fig.add_subplot(gs[1])
    ax.plot(np.arange(20))
    ax.set_title('Axes')

    fig.suptitle('Figure suptitle', fontsize='xx-large')


@image_comparison(['test_subfigure_double.png'], style='mpl20',
                  savefig_kwarg={'facecolor': 'teal'})
def test_subfigure_double():
    # test assigning the subfigure via subplotspec
    np.random.seed(19680801)

    fig = plt.figure(layout='constrained', figsize=(10, 8))

    fig.suptitle('fig')

    subfigs = fig.subfigures(1, 2, wspace=0.07)

    subfigs[0].set_facecolor('coral')
    subfigs[0].suptitle('subfigs[0]')

    subfigs[1].set_facecolor('coral')
    subfigs[1].suptitle('subfigs[1]')

    subfigsnest = subfigs[0].subfigures(2, 1, height_ratios=[1, 1.4])
    subfigsnest[0].suptitle('subfigsnest[0]')
    subfigsnest[0].set_facecolor('r')
    axsnest0 = subfigsnest[0].subplots(1, 2, sharey=True)
    for ax in axsnest0:
        fontsize = 12
        pc = ax.pcolormesh(np.random.randn(30, 30), vmin=-2.5, vmax=2.5)
        ax.set_xlabel('x-label', fontsize=fontsize)
        ax.set_ylabel('y-label', fontsize=fontsize)
        ax.set_title('Title', fontsize=fontsize)
    subfigsnest[0].colorbar(pc, ax=axsnest0)

    subfigsnest[1].suptitle('subfigsnest[1]')
    subfigsnest[1].set_facecolor('g')
    axsnest1 = subfigsnest[1].subplots(3, 1, sharex=True)
    for nn, ax in enumerate(axsnest1):
        ax.set_ylabel(f'ylabel{nn}')
    subfigsnest[1].supxlabel('supxlabel')
    subfigsnest[1].supylabel('supylabel')

    axsRight = subfigs[1].subplots(2, 2)


def test_subfigure_spanning():
    # test that subfigures get laid out properly...
    fig = plt.figure(constrained_layout=True)
    gs = fig.add_gridspec(3, 3)
    sub_figs = [
        fig.add_subfigure(gs[0, 0]),
        fig.add_subfigure(gs[0:2, 1]),
        fig.add_subfigure(gs[2, 1:3]),
        fig.add_subfigure(gs[0:, 1:])
    ]

    w = 640
    h = 480
    np.testing.assert_allclose(sub_figs[0].bbox.min, [0., h * 2/3])
    np.testing.assert_allclose(sub_figs[0].bbox.max, [w / 3, h])

    np.testing.assert_allclose(sub_figs[1].bbox.min, [w / 3, h / 3])
    np.testing.assert_allclose(sub_figs[1].bbox.max, [w * 2/3, h])

    np.testing.assert_allclose(sub_figs[2].bbox.min, [w / 3, 0])
    np.testing.assert_allclose(sub_figs[2].bbox.max, [w, h / 3])

    # check here that slicing actually works.  Last sub_fig
    # with open slices failed, but only on draw...
    for i in range(4):
        sub_figs[i].add_subplot()
    fig.draw_without_rendering()


@mpl.style.context('mpl20')
def test_subfigure_ticks():
    # This tests a tick-spacing error that only seems applicable
    # when the subfigures are saved to file.  It is very hard to replicate
    fig = plt.figure(constrained_layout=True, figsize=(10, 3))
    # create left/right subfigs nested in bottom subfig
    (subfig_bl, subfig_br) = fig.subfigures(1, 2, wspace=0.01,
                                            width_ratios=[7, 2])

    # put ax1-ax3 in gridspec of bottom-left subfig
    gs = subfig_bl.add_gridspec(nrows=1, ncols=14)

    ax1 = subfig_bl.add_subplot(gs[0, :1])
    ax1.scatter(x=[-56.46881504821776, 24.179891162109396], y=[1500, 3600])

    ax2 = subfig_bl.add_subplot(gs[0, 1:3], sharey=ax1)
    ax2.scatter(x=[-126.5357270050049, 94.68456736755368], y=[1500, 3600])
    ax3 = subfig_bl.add_subplot(gs[0, 3:14], sharey=ax1)

    fig.dpi = 120
    fig.draw_without_rendering()
    ticks120 = ax2.get_xticks()
    fig.dpi = 300
    fig.draw_without_rendering()
    ticks300 = ax2.get_xticks()
    np.testing.assert_allclose(ticks120, ticks300)


@image_comparison(['test_subfigure_scatter_size.png'], style='mpl20',
                   remove_text=True)
def test_subfigure_scatter_size():
    # markers in the left- and right-most subplots should be the same
    fig = plt.figure()
    gs = fig.add_gridspec(1, 2)
    ax0 = fig.add_subplot(gs[1])
    ax0.scatter([1, 2, 3], [1, 2, 3], s=30, marker='s')
    ax0.scatter([3, 4, 5], [1, 2, 3], s=[20, 30, 40], marker='s')

    sfig = fig.add_subfigure(gs[0])
    axs = sfig.subplots(1, 2)
    for ax in [ax0, axs[0]]:
        ax.scatter([1, 2, 3], [1, 2, 3], s=30, marker='s', color='r')
        ax.scatter([3, 4, 5], [1, 2, 3], s=[20, 30, 40], marker='s', color='g')


def test_subfigure_pdf():
    fig = plt.figure(layout='constrained')
    sub_fig = fig.subfigures()
    ax = sub_fig.add_subplot(111)
    b = ax.bar(1, 1)
    ax.bar_label(b)
    buffer = io.BytesIO()
    fig.savefig(buffer, format='pdf')


def test_subfigures_wspace_hspace():
    sub_figs = plt.figure().subfigures(2, 3, hspace=0.5, wspace=1/6.)

    w = 640
    h = 480

    np.testing.assert_allclose(sub_figs[0, 0].bbox.min, [0., h * 0.6])
    np.testing.assert_allclose(sub_figs[0, 0].bbox.max, [w * 0.3, h])

    np.testing.assert_allclose(sub_figs[0, 1].bbox.min, [w * 0.35, h * 0.6])
    np.testing.assert_allclose(sub_figs[0, 1].bbox.max, [w * 0.65, h])

    np.testing.assert_allclose(sub_figs[0, 2].bbox.min, [w * 0.7, h * 0.6])
    np.testing.assert_allclose(sub_figs[0, 2].bbox.max, [w, h])

    np.testing.assert_allclose(sub_figs[1, 0].bbox.min, [0, 0])
    np.testing.assert_allclose(sub_figs[1, 0].bbox.max, [w * 0.3, h * 0.4])

    np.testing.assert_allclose(sub_figs[1, 1].bbox.min, [w * 0.35, 0])
    np.testing.assert_allclose(sub_figs[1, 1].bbox.max, [w * 0.65, h * 0.4])

    np.testing.assert_allclose(sub_figs[1, 2].bbox.min, [w * 0.7, 0])
    np.testing.assert_allclose(sub_figs[1, 2].bbox.max, [w, h * 0.4])


def test_subfigure_remove():
    fig = plt.figure()
    sfs = fig.subfigures(2, 2)
    sfs[1, 1].remove()
    assert len(fig.subfigs) == 3


def test_add_subplot_kwargs():
    # fig.add_subplot() always creates new axes, even if axes kwargs differ.
    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1)
    ax1 = fig.add_subplot(1, 1, 1)
    assert ax is not None
    assert ax1 is not ax
    plt.close()

    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1, projection='polar')
    ax1 = fig.add_subplot(1, 1, 1, projection='polar')
    assert ax is not None
    assert ax1 is not ax
    plt.close()

    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1, projection='polar')
    ax1 = fig.add_subplot(1, 1, 1)
    assert ax is not None
    assert ax1.name == 'rectilinear'
    assert ax1 is not ax
    plt.close()


def test_add_axes_kwargs():
    # fig.add_axes() always creates new axes, even if axes kwargs differ.
    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1])
    ax1 = fig.add_axes([0, 0, 1, 1])
    assert ax is not None
    assert ax1 is not ax
    plt.close()

    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1], projection='polar')
    ax1 = fig.add_axes([0, 0, 1, 1], projection='polar')
    assert ax is not None
    assert ax1 is not ax
    plt.close()

    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1], projection='polar')
    ax1 = fig.add_axes([0, 0, 1, 1])
    assert ax is not None
    assert ax1.name == 'rectilinear'
    assert ax1 is not ax
    plt.close()


def test_ginput(recwarn):  # recwarn undoes warn filters at exit.
    warnings.filterwarnings("ignore", "cannot show the figure")
    fig, ax = plt.subplots()
    trans = ax.transData.transform

    def single_press():
        MouseEvent("button_press_event", fig.canvas, *trans((.1, .2)), 1)._process()

    Timer(.1, single_press).start()
    assert fig.ginput() == [(.1, .2)]

    def multi_presses():
        MouseEvent("button_press_event", fig.canvas, *trans((.1, .2)), 1)._process()
        KeyEvent("key_press_event", fig.canvas, "backspace")._process()
        MouseEvent("button_press_event", fig.canvas, *trans((.3, .4)), 1)._process()
        MouseEvent("button_press_event", fig.canvas, *trans((.5, .6)), 1)._process()
        MouseEvent("button_press_event", fig.canvas, *trans((0, 0)), 2)._process()

    Timer(.1, multi_presses).start()
    np.testing.assert_allclose(fig.ginput(3), [(.3, .4), (.5, .6)])


def test_waitforbuttonpress(recwarn):  # recwarn undoes warn filters at exit.
    warnings.filterwarnings("ignore", "cannot show the figure")
    fig = plt.figure()
    assert fig.waitforbuttonpress(timeout=.1) is None
    Timer(.1, KeyEvent("key_press_event", fig.canvas, "z")._process).start()
    assert fig.waitforbuttonpress() is True
    Timer(.1, MouseEvent("button_press_event", fig.canvas, 0, 0, 1)._process).start()
    assert fig.waitforbuttonpress() is False


def test_kwargs_pass():
    fig = Figure(label='whole Figure')
    sub_fig = fig.subfigures(1, 1, label='sub figure')

    assert fig.get_label() == 'whole Figure'
    assert sub_fig.get_label() == 'sub figure'


@check_figures_equal(extensions=["png"])
def test_rcparams(fig_test, fig_ref):
    fig_ref.supxlabel("xlabel", weight='bold', size=15)
    fig_ref.supylabel("ylabel", weight='bold', size=15)
    fig_ref.suptitle("Title", weight='light', size=20)
    with mpl.rc_context({'figure.labelweight': 'bold',
                         'figure.labelsize': 15,
                         'figure.titleweight': 'light',
                         'figure.titlesize': 20}):
        fig_test.supxlabel("xlabel")
        fig_test.supylabel("ylabel")
        fig_test.suptitle("Title")


def test_deepcopy():
    fig1, ax = plt.subplots()
    ax.plot([0, 1], [2, 3])
    ax.set_yscale('log')

    fig2 = copy.deepcopy(fig1)

    # Make sure it is a new object
    assert fig2.axes[0] is not ax
    # And that the axis scale got propagated
    assert fig2.axes[0].get_yscale() == 'log'
    # Update the deepcopy and check the original isn't modified
    fig2.axes[0].set_yscale('linear')
    assert ax.get_yscale() == 'log'

    # And test the limits of the axes don't get propagated
    ax.set_xlim(1e-1, 1e2)
    # Draw these to make sure limits are updated
    fig1.draw_without_rendering()
    fig2.draw_without_rendering()

    assert ax.get_xlim() == (1e-1, 1e2)
    assert fig2.axes[0].get_xlim() == (0, 1)


def test_unpickle_with_device_pixel_ratio():
    fig = Figure(dpi=42)
    fig.canvas._set_device_pixel_ratio(7)
    assert fig.dpi == 42*7
    fig2 = pickle.loads(pickle.dumps(fig))
    assert fig2.dpi == 42


def test_gridspec_no_mutate_input():
    gs = {'left': .1}
    gs_orig = dict(gs)
    plt.subplots(1, 2, width_ratios=[1, 2], gridspec_kw=gs)
    assert gs == gs_orig
    plt.subplot_mosaic('AB', width_ratios=[1, 2], gridspec_kw=gs)


@pytest.mark.parametrize('fmt', ['eps', 'pdf', 'png', 'ps', 'svg', 'svgz'])
def test_savefig_metadata(fmt):
    Figure().savefig(io.BytesIO(), format=fmt, metadata={})


@pytest.mark.parametrize('fmt', ['jpeg', 'jpg', 'tif', 'tiff', 'webp', "raw", "rgba"])
def test_savefig_metadata_error(fmt):
    with pytest.raises(ValueError, match="metadata not supported"):
        Figure().savefig(io.BytesIO(), format=fmt, metadata={})


def test_get_constrained_layout_pads():
    params = {'w_pad': 0.01, 'h_pad': 0.02, 'wspace': 0.03, 'hspace': 0.04}
    expected = tuple([*params.values()])
    fig = plt.figure(layout=mpl.layout_engine.ConstrainedLayoutEngine(**params))
    with pytest.warns(PendingDeprecationWarning, match="will be deprecated"):
        assert fig.get_constrained_layout_pads() == expected


def test_not_visible_figure():
    fig = Figure()

    buf = io.StringIO()
    fig.savefig(buf, format='svg')
    buf.seek(0)
    assert '<g ' in buf.read()

    fig.set_visible(False)
    buf = io.StringIO()
    fig.savefig(buf, format='svg')
    buf.seek(0)
    assert '<g ' not in buf.read()


def test_warn_colorbar_mismatch():
    fig1, ax1 = plt.subplots()
    fig2, (ax2_1, ax2_2) = plt.subplots(2)
    im = ax1.imshow([[1, 2], [3, 4]])

    fig1.colorbar(im)  # should not warn
    with pytest.warns(UserWarning, match="different Figure"):
        fig2.colorbar(im)
    # warn mismatch even when the host figure is not inferred
    with pytest.warns(UserWarning, match="different Figure"):
        fig2.colorbar(im, ax=ax1)
    with pytest.warns(UserWarning, match="different Figure"):
        fig2.colorbar(im, ax=ax2_1)
    with pytest.warns(UserWarning, match="different Figure"):
        fig2.colorbar(im, cax=ax2_2)

    # edge case: only compare top level artist in case of subfigure
    fig3 = plt.figure()
    fig4 = plt.figure()
    subfig3_1 = fig3.subfigures()
    subfig3_2 = fig3.subfigures()
    subfig4_1 = fig4.subfigures()
    ax3_1 = subfig3_1.subplots()
    ax3_2 = subfig3_1.subplots()
    ax4_1 = subfig4_1.subplots()
    im3_1 = ax3_1.imshow([[1, 2], [3, 4]])
    im3_2 = ax3_2.imshow([[1, 2], [3, 4]])
    im4_1 = ax4_1.imshow([[1, 2], [3, 4]])

    fig3.colorbar(im3_1)   # should not warn
    subfig3_1.colorbar(im3_1)   # should not warn
    subfig3_1.colorbar(im3_2)   # should not warn
    with pytest.warns(UserWarning, match="different Figure"):
        subfig3_1.colorbar(im4_1)


def test_set_figure():
    fig = plt.figure()
    sfig1 = fig.subfigures()
    sfig2 = sfig1.subfigures()

    for f in fig, sfig1, sfig2:
        with pytest.warns(mpl.MatplotlibDeprecationWarning):
            f.set_figure(fig)

    with pytest.raises(ValueError, match="cannot be changed"):
        sfig2.set_figure(sfig1)

    with pytest.raises(ValueError, match="cannot be changed"):
        sfig1.set_figure(plt.figure())


def test_subfigure_row_order():
    # Test that subfigures are drawn in row-major order.
    fig = plt.figure()
    sf_arr = fig.subfigures(4, 3)
    for a, b in zip(sf_arr.ravel(), fig.subfigs):
        assert a is b


def test_subfigure_stale_propagation():
    fig = plt.figure()

    fig.draw_without_rendering()
    assert not fig.stale

    sfig1 = fig.subfigures()
    assert fig.stale

    fig.draw_without_rendering()
    assert not fig.stale
    assert not sfig1.stale

    sfig2 = sfig1.subfigures()
    assert fig.stale
    assert sfig1.stale

    fig.draw_without_rendering()
    assert not fig.stale
    assert not sfig1.stale
    assert not sfig2.stale

    sfig2.stale = True
    assert sfig1.stale
    assert fig.stale
