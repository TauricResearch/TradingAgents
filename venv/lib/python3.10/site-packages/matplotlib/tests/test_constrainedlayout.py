import gc
import platform

import numpy as np
import pytest

import matplotlib as mpl
from matplotlib.testing.decorators import image_comparison
import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
from matplotlib import gridspec, ticker


pytestmark = [
    pytest.mark.usefixtures('text_placeholders')
]


def example_plot(ax, fontsize=12, nodec=False):
    ax.plot([1, 2])
    ax.locator_params(nbins=3)
    if not nodec:
        ax.set_xlabel('x-label', fontsize=fontsize)
        ax.set_ylabel('y-label', fontsize=fontsize)
        ax.set_title('Title', fontsize=fontsize)
    else:
        ax.set_xticklabels([])
        ax.set_yticklabels([])


def example_pcolor(ax, fontsize=12):
    dx, dy = 0.6, 0.6
    y, x = np.mgrid[slice(-3, 3 + dy, dy),
                    slice(-3, 3 + dx, dx)]
    z = (1 - x / 2. + x ** 5 + y ** 3) * np.exp(-x ** 2 - y ** 2)
    pcm = ax.pcolormesh(x, y, z[:-1, :-1], cmap='RdBu_r', vmin=-1., vmax=1.,
                        rasterized=True)
    ax.set_xlabel('x-label', fontsize=fontsize)
    ax.set_ylabel('y-label', fontsize=fontsize)
    ax.set_title('Title', fontsize=fontsize)
    return pcm


@image_comparison(['constrained_layout1.png'], style='mpl20')
def test_constrained_layout1():
    """Test constrained_layout for a single subplot"""
    fig = plt.figure(layout="constrained")
    ax = fig.add_subplot()
    example_plot(ax, fontsize=24)


@image_comparison(['constrained_layout2.png'], style='mpl20')
def test_constrained_layout2():
    """Test constrained_layout for 2x2 subplots"""
    fig, axs = plt.subplots(2, 2, layout="constrained")
    for ax in axs.flat:
        example_plot(ax, fontsize=24)


@image_comparison(['constrained_layout3.png'], style='mpl20')
def test_constrained_layout3():
    """Test constrained_layout for colorbars with subplots"""

    fig, axs = plt.subplots(2, 2, layout="constrained")
    for nn, ax in enumerate(axs.flat):
        pcm = example_pcolor(ax, fontsize=24)
        if nn == 3:
            pad = 0.08
        else:
            pad = 0.02  # default
        fig.colorbar(pcm, ax=ax, pad=pad)


@image_comparison(['constrained_layout4.png'], style='mpl20')
def test_constrained_layout4():
    """Test constrained_layout for a single colorbar with subplots"""

    fig, axs = plt.subplots(2, 2, layout="constrained")
    for ax in axs.flat:
        pcm = example_pcolor(ax, fontsize=24)
    fig.colorbar(pcm, ax=axs, pad=0.01, shrink=0.6)


@image_comparison(['constrained_layout5.png'], style='mpl20')
def test_constrained_layout5():
    """
    Test constrained_layout for a single colorbar with subplots,
    colorbar bottom
    """

    fig, axs = plt.subplots(2, 2, layout="constrained")
    for ax in axs.flat:
        pcm = example_pcolor(ax, fontsize=24)
    fig.colorbar(pcm, ax=axs,
                 use_gridspec=False, pad=0.01, shrink=0.6,
                 location='bottom')


@image_comparison(['constrained_layout6.png'], style='mpl20')
def test_constrained_layout6():
    """Test constrained_layout for nested gridspecs"""
    fig = plt.figure(layout="constrained")
    gs = fig.add_gridspec(1, 2, figure=fig)
    gsl = gs[0].subgridspec(2, 2)
    gsr = gs[1].subgridspec(1, 2)
    axsl = []
    for gs in gsl:
        ax = fig.add_subplot(gs)
        axsl += [ax]
        example_plot(ax, fontsize=12)
    ax.set_xlabel('x-label\nMultiLine')
    axsr = []
    for gs in gsr:
        ax = fig.add_subplot(gs)
        axsr += [ax]
        pcm = example_pcolor(ax, fontsize=12)

    fig.colorbar(pcm, ax=axsr,
                 pad=0.01, shrink=0.99, location='bottom',
                 ticks=ticker.MaxNLocator(nbins=5))


def test_identical_subgridspec():

    fig = plt.figure(constrained_layout=True)

    GS = fig.add_gridspec(2, 1)

    GSA = GS[0].subgridspec(1, 3)
    GSB = GS[1].subgridspec(1, 3)

    axa = []
    axb = []
    for i in range(3):
        axa += [fig.add_subplot(GSA[i])]
        axb += [fig.add_subplot(GSB[i])]

    fig.draw_without_rendering()
    # check first row above second
    assert axa[0].get_position().y0 > axb[0].get_position().y1


def test_constrained_layout7():
    """Test for proper warning if fig not set in GridSpec"""
    with pytest.warns(
        UserWarning, match=('There are no gridspecs with layoutgrids. '
                            'Possibly did not call parent GridSpec with '
                            'the "figure" keyword')):
        fig = plt.figure(layout="constrained")
        gs = gridspec.GridSpec(1, 2)
        gsl = gridspec.GridSpecFromSubplotSpec(2, 2, gs[0])
        gsr = gridspec.GridSpecFromSubplotSpec(1, 2, gs[1])
        for gs in gsl:
            fig.add_subplot(gs)
        # need to trigger a draw to get warning
        fig.draw_without_rendering()


@image_comparison(['constrained_layout8.png'], style='mpl20')
def test_constrained_layout8():
    """Test for gridspecs that are not completely full"""

    fig = plt.figure(figsize=(10, 5), layout="constrained")
    gs = gridspec.GridSpec(3, 5, figure=fig)
    axs = []
    for j in [0, 1]:
        if j == 0:
            ilist = [1]
        else:
            ilist = [0, 4]
        for i in ilist:
            ax = fig.add_subplot(gs[j, i])
            axs += [ax]
            example_pcolor(ax, fontsize=9)
            if i > 0:
                ax.set_ylabel('')
            if j < 1:
                ax.set_xlabel('')
            ax.set_title('')
    ax = fig.add_subplot(gs[2, :])
    axs += [ax]
    pcm = example_pcolor(ax, fontsize=9)

    fig.colorbar(pcm, ax=axs, pad=0.01, shrink=0.6)


@image_comparison(['constrained_layout9.png'], style='mpl20')
def test_constrained_layout9():
    """Test for handling suptitle and for sharex and sharey"""

    fig, axs = plt.subplots(2, 2, layout="constrained",
                            sharex=False, sharey=False)
    for ax in axs.flat:
        pcm = example_pcolor(ax, fontsize=24)
        ax.set_xlabel('')
        ax.set_ylabel('')
    ax.set_aspect(2.)
    fig.colorbar(pcm, ax=axs, pad=0.01, shrink=0.6)
    fig.suptitle('Test Suptitle', fontsize=28)


@image_comparison(['constrained_layout10.png'], style='mpl20',
                  tol=0 if platform.machine() == 'x86_64' else 0.032)
def test_constrained_layout10():
    """Test for handling legend outside axis"""
    fig, axs = plt.subplots(2, 2, layout="constrained")
    for ax in axs.flat:
        ax.plot(np.arange(12), label='This is a label')
    ax.legend(loc='center left', bbox_to_anchor=(0.8, 0.5))


@image_comparison(['constrained_layout11.png'], style='mpl20')
def test_constrained_layout11():
    """Test for multiple nested gridspecs"""

    fig = plt.figure(layout="constrained", figsize=(13, 3))
    gs0 = gridspec.GridSpec(1, 2, figure=fig)
    gsl = gridspec.GridSpecFromSubplotSpec(1, 2, gs0[0])
    gsl0 = gridspec.GridSpecFromSubplotSpec(2, 2, gsl[1])
    ax = fig.add_subplot(gs0[1])
    example_plot(ax, fontsize=9)
    axs = []
    for gs in gsl0:
        ax = fig.add_subplot(gs)
        axs += [ax]
        pcm = example_pcolor(ax, fontsize=9)
    fig.colorbar(pcm, ax=axs, shrink=0.6, aspect=70.)
    ax = fig.add_subplot(gsl[0])
    example_plot(ax, fontsize=9)


@image_comparison(['constrained_layout11rat.png'], style='mpl20')
def test_constrained_layout11rat():
    """Test for multiple nested gridspecs with width_ratios"""

    fig = plt.figure(layout="constrained", figsize=(10, 3))
    gs0 = gridspec.GridSpec(1, 2, figure=fig, width_ratios=[6, 1])
    gsl = gridspec.GridSpecFromSubplotSpec(1, 2, gs0[0])
    gsl0 = gridspec.GridSpecFromSubplotSpec(2, 2, gsl[1], height_ratios=[2, 1])
    ax = fig.add_subplot(gs0[1])
    example_plot(ax, fontsize=9)
    axs = []
    for gs in gsl0:
        ax = fig.add_subplot(gs)
        axs += [ax]
        pcm = example_pcolor(ax, fontsize=9)
    fig.colorbar(pcm, ax=axs, shrink=0.6, aspect=70.)
    ax = fig.add_subplot(gsl[0])
    example_plot(ax, fontsize=9)


@image_comparison(['constrained_layout12.png'], style='mpl20')
def test_constrained_layout12():
    """Test that very unbalanced labeling still works."""
    fig = plt.figure(layout="constrained", figsize=(6, 8))

    gs0 = gridspec.GridSpec(6, 2, figure=fig)

    ax1 = fig.add_subplot(gs0[:3, 1])
    ax2 = fig.add_subplot(gs0[3:, 1])

    example_plot(ax1, fontsize=18)
    example_plot(ax2, fontsize=18)

    ax = fig.add_subplot(gs0[0:2, 0])
    example_plot(ax, nodec=True)
    ax = fig.add_subplot(gs0[2:4, 0])
    example_plot(ax, nodec=True)
    ax = fig.add_subplot(gs0[4:, 0])
    example_plot(ax, nodec=True)
    ax.set_xlabel('x-label')


@image_comparison(['constrained_layout13.png'], style='mpl20')
def test_constrained_layout13():
    """Test that padding works."""
    fig, axs = plt.subplots(2, 2, layout="constrained")
    for ax in axs.flat:
        pcm = example_pcolor(ax, fontsize=12)
        fig.colorbar(pcm, ax=ax, shrink=0.6, aspect=20., pad=0.02)
    with pytest.raises(TypeError):
        fig.get_layout_engine().set(wpad=1, hpad=2)
    fig.get_layout_engine().set(w_pad=24./72., h_pad=24./72.)


@image_comparison(['constrained_layout14.png'], style='mpl20')
def test_constrained_layout14():
    """Test that padding works."""
    fig, axs = plt.subplots(2, 2, layout="constrained")
    for ax in axs.flat:
        pcm = example_pcolor(ax, fontsize=12)
        fig.colorbar(pcm, ax=ax, shrink=0.6, aspect=20., pad=0.02)
    fig.get_layout_engine().set(
            w_pad=3./72., h_pad=3./72.,
            hspace=0.2, wspace=0.2)


@image_comparison(['constrained_layout15.png'], style='mpl20')
def test_constrained_layout15():
    """Test that rcparams work."""
    mpl.rcParams['figure.constrained_layout.use'] = True
    fig, axs = plt.subplots(2, 2)
    for ax in axs.flat:
        example_plot(ax, fontsize=12)


@image_comparison(['constrained_layout16.png'], style='mpl20')
def test_constrained_layout16():
    """Test ax.set_position."""
    fig, ax = plt.subplots(layout="constrained")
    example_plot(ax, fontsize=12)
    ax2 = fig.add_axes([0.2, 0.2, 0.4, 0.4])


@image_comparison(['constrained_layout17.png'], style='mpl20')
def test_constrained_layout17():
    """Test uneven gridspecs"""
    fig = plt.figure(layout="constrained")
    gs = gridspec.GridSpec(3, 3, figure=fig)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1:])
    ax3 = fig.add_subplot(gs[1:, 0:2])
    ax4 = fig.add_subplot(gs[1:, -1])

    example_plot(ax1)
    example_plot(ax2)
    example_plot(ax3)
    example_plot(ax4)


def test_constrained_layout18():
    """Test twinx"""
    fig, ax = plt.subplots(layout="constrained")
    ax2 = ax.twinx()
    example_plot(ax)
    example_plot(ax2, fontsize=24)
    fig.draw_without_rendering()
    assert all(ax.get_position().extents == ax2.get_position().extents)


def test_constrained_layout19():
    """Test twiny"""
    fig, ax = plt.subplots(layout="constrained")
    ax2 = ax.twiny()
    example_plot(ax)
    example_plot(ax2, fontsize=24)
    ax2.set_title('')
    ax.set_title('')
    fig.draw_without_rendering()
    assert all(ax.get_position().extents == ax2.get_position().extents)


def test_constrained_layout20():
    """Smoke test cl does not mess up added Axes"""
    gx = np.linspace(-5, 5, 4)
    img = np.hypot(gx, gx[:, None])

    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1])
    mesh = ax.pcolormesh(gx, gx, img[:-1, :-1])
    fig.colorbar(mesh)


def test_constrained_layout21():
    """#11035: repeated calls to suptitle should not alter the layout"""
    fig, ax = plt.subplots(layout="constrained")

    fig.suptitle("Suptitle0")
    fig.draw_without_rendering()
    extents0 = np.copy(ax.get_position().extents)

    fig.suptitle("Suptitle1")
    fig.draw_without_rendering()
    extents1 = np.copy(ax.get_position().extents)

    np.testing.assert_allclose(extents0, extents1)


def test_constrained_layout22():
    """#11035: suptitle should not be include in CL if manually positioned"""
    fig, ax = plt.subplots(layout="constrained")

    fig.draw_without_rendering()
    extents0 = np.copy(ax.get_position().extents)

    fig.suptitle("Suptitle", y=0.5)
    fig.draw_without_rendering()
    extents1 = np.copy(ax.get_position().extents)

    np.testing.assert_allclose(extents0, extents1)


def test_constrained_layout23():
    """
    Comment in #11035: suptitle used to cause an exception when
    reusing a figure w/ CL with ``clear=True``.
    """

    for i in range(2):
        fig = plt.figure(layout="constrained", clear=True, num="123")
        gs = fig.add_gridspec(1, 2)
        sub = gs[0].subgridspec(2, 2)
        fig.suptitle(f"Suptitle{i}")


@image_comparison(['test_colorbar_location.png'],
                  remove_text=True, style='mpl20')
def test_colorbar_location():
    """
    Test that colorbar handling is as expected for various complicated
    cases...
    """
    # Remove this line when this test image is regenerated.
    plt.rcParams['pcolormesh.snap'] = False

    fig, axs = plt.subplots(4, 5, layout="constrained")
    for ax in axs.flat:
        pcm = example_pcolor(ax)
        ax.set_xlabel('')
        ax.set_ylabel('')
    fig.colorbar(pcm, ax=axs[:, 1], shrink=0.4)
    fig.colorbar(pcm, ax=axs[-1, :2], shrink=0.5, location='bottom')
    fig.colorbar(pcm, ax=axs[0, 2:], shrink=0.5, location='bottom', pad=0.05)
    fig.colorbar(pcm, ax=axs[-2, 3:], shrink=0.5, location='top')
    fig.colorbar(pcm, ax=axs[0, 0], shrink=0.5, location='left')
    fig.colorbar(pcm, ax=axs[1:3, 2], shrink=0.5, location='right')


def test_hidden_axes():
    # test that if we make an Axes not visible that constrained_layout
    # still works.  Note the axes still takes space in the layout
    # (as does a gridspec slot that is empty)
    fig, axs = plt.subplots(2, 2, layout="constrained")
    axs[0, 1].set_visible(False)
    fig.draw_without_rendering()
    extents1 = np.copy(axs[0, 0].get_position().extents)

    np.testing.assert_allclose(
        extents1, [0.046918, 0.541204, 0.477409, 0.980555], rtol=1e-5)


def test_colorbar_align():
    for location in ['right', 'left', 'top', 'bottom']:
        fig, axs = plt.subplots(2, 2, layout="constrained")
        cbs = []
        for nn, ax in enumerate(axs.flat):
            ax.tick_params(direction='in')
            pc = example_pcolor(ax)
            cb = fig.colorbar(pc, ax=ax, location=location, shrink=0.6,
                              pad=0.04)
            cbs += [cb]
            cb.ax.tick_params(direction='in')
            if nn != 1:
                cb.ax.xaxis.set_ticks([])
                cb.ax.yaxis.set_ticks([])
                ax.set_xticklabels([])
                ax.set_yticklabels([])
        fig.get_layout_engine().set(w_pad=4 / 72, h_pad=4 / 72,
                                    hspace=0.1, wspace=0.1)

        fig.draw_without_rendering()
        if location in ['left', 'right']:
            np.testing.assert_allclose(cbs[0].ax.get_position().x0,
                                       cbs[2].ax.get_position().x0)
            np.testing.assert_allclose(cbs[1].ax.get_position().x0,
                                       cbs[3].ax.get_position().x0)
        else:
            np.testing.assert_allclose(cbs[0].ax.get_position().y0,
                                       cbs[1].ax.get_position().y0)
            np.testing.assert_allclose(cbs[2].ax.get_position().y0,
                                       cbs[3].ax.get_position().y0)


@image_comparison(['test_colorbars_no_overlapV.png'], style='mpl20')
def test_colorbars_no_overlapV():
    fig = plt.figure(figsize=(2, 4), layout="constrained")
    axs = fig.subplots(2, 1, sharex=True, sharey=True)
    for ax in axs:
        ax.yaxis.set_major_formatter(ticker.NullFormatter())
        ax.tick_params(axis='both', direction='in')
        im = ax.imshow([[1, 2], [3, 4]])
        fig.colorbar(im, ax=ax, orientation="vertical")
    fig.suptitle("foo")


@image_comparison(['test_colorbars_no_overlapH.png'], style='mpl20')
def test_colorbars_no_overlapH():
    fig = plt.figure(figsize=(4, 2), layout="constrained")
    fig.suptitle("foo")
    axs = fig.subplots(1, 2, sharex=True, sharey=True)
    for ax in axs:
        ax.yaxis.set_major_formatter(ticker.NullFormatter())
        ax.tick_params(axis='both', direction='in')
        im = ax.imshow([[1, 2], [3, 4]])
        fig.colorbar(im, ax=ax, orientation="horizontal")


def test_manually_set_position():
    fig, axs = plt.subplots(1, 2, layout="constrained")
    axs[0].set_position([0.2, 0.2, 0.3, 0.3])
    fig.draw_without_rendering()
    pp = axs[0].get_position()
    np.testing.assert_allclose(pp, [[0.2, 0.2], [0.5, 0.5]])

    fig, axs = plt.subplots(1, 2, layout="constrained")
    axs[0].set_position([0.2, 0.2, 0.3, 0.3])
    pc = axs[0].pcolormesh(np.random.rand(20, 20))
    fig.colorbar(pc, ax=axs[0])
    fig.draw_without_rendering()
    pp = axs[0].get_position()
    np.testing.assert_allclose(pp, [[0.2, 0.2], [0.44, 0.5]])


@image_comparison(['test_bboxtight.png'],
                  remove_text=True, style='mpl20',
                  savefig_kwarg={'bbox_inches': 'tight'})
def test_bboxtight():
    fig, ax = plt.subplots(layout="constrained")
    ax.set_aspect(1.)


@image_comparison(['test_bbox.png'],
                  remove_text=True, style='mpl20',
                  savefig_kwarg={'bbox_inches':
                                 mtransforms.Bbox([[0.5, 0], [2.5, 2]])})
def test_bbox():
    fig, ax = plt.subplots(layout="constrained")
    ax.set_aspect(1.)


def test_align_labels():
    """
    Tests for a bug in which constrained layout and align_ylabels on
    three unevenly sized subplots, one of whose y tick labels include
    negative numbers, drives the non-negative subplots' y labels off
    the edge of the plot
    """
    fig, (ax3, ax1, ax2) = plt.subplots(3, 1, layout="constrained",
                                        figsize=(6.4, 8),
                                        gridspec_kw={"height_ratios": (1, 1,
                                                                       0.7)})

    ax1.set_ylim(0, 1)
    ax1.set_ylabel("Label")

    ax2.set_ylim(-1.5, 1.5)
    ax2.set_ylabel("Label")

    ax3.set_ylim(0, 1)
    ax3.set_ylabel("Label")

    fig.align_ylabels(axs=(ax3, ax1, ax2))

    fig.draw_without_rendering()
    after_align = [ax1.yaxis.label.get_window_extent(),
                   ax2.yaxis.label.get_window_extent(),
                   ax3.yaxis.label.get_window_extent()]
    # ensure labels are approximately aligned
    np.testing.assert_allclose([after_align[0].x0, after_align[2].x0],
                               after_align[1].x0, rtol=0, atol=1e-05)
    # ensure labels do not go off the edge
    assert after_align[0].x0 >= 1


def test_suplabels():
    fig, ax = plt.subplots(layout="constrained")
    fig.draw_without_rendering()
    pos0 = ax.get_tightbbox(fig.canvas.get_renderer())
    fig.supxlabel('Boo')
    fig.supylabel('Booy')
    fig.draw_without_rendering()
    pos = ax.get_tightbbox(fig.canvas.get_renderer())
    assert pos.y0 > pos0.y0 + 10.0
    assert pos.x0 > pos0.x0 + 10.0

    fig, ax = plt.subplots(layout="constrained")
    fig.draw_without_rendering()
    pos0 = ax.get_tightbbox(fig.canvas.get_renderer())
    # check that specifying x (y) doesn't ruin the layout
    fig.supxlabel('Boo', x=0.5)
    fig.supylabel('Boo', y=0.5)
    fig.draw_without_rendering()
    pos = ax.get_tightbbox(fig.canvas.get_renderer())
    assert pos.y0 > pos0.y0 + 10.0
    assert pos.x0 > pos0.x0 + 10.0


def test_gridspec_addressing():
    fig = plt.figure()
    gs = fig.add_gridspec(3, 3)
    sp = fig.add_subplot(gs[0:, 1:])
    fig.draw_without_rendering()


def test_discouraged_api():
    fig, ax = plt.subplots(constrained_layout=True)
    fig.draw_without_rendering()

    with pytest.warns(PendingDeprecationWarning,
                      match="will be deprecated"):
        fig, ax = plt.subplots()
        fig.set_constrained_layout(True)
        fig.draw_without_rendering()

    with pytest.warns(PendingDeprecationWarning,
                      match="will be deprecated"):
        fig, ax = plt.subplots()
        fig.set_constrained_layout({'w_pad': 0.02, 'h_pad': 0.02})
        fig.draw_without_rendering()


def test_kwargs():
    fig, ax = plt.subplots(constrained_layout={'h_pad': 0.02})
    fig.draw_without_rendering()


def test_rect():
    fig, ax = plt.subplots(layout='constrained')
    fig.get_layout_engine().set(rect=[0, 0, 0.5, 0.5])
    fig.draw_without_rendering()
    ppos = ax.get_position()
    assert ppos.x1 < 0.5
    assert ppos.y1 < 0.5

    fig, ax = plt.subplots(layout='constrained')
    fig.get_layout_engine().set(rect=[0.2, 0.2, 0.3, 0.3])
    fig.draw_without_rendering()
    ppos = ax.get_position()
    assert ppos.x1 < 0.5
    assert ppos.y1 < 0.5
    assert ppos.x0 > 0.2
    assert ppos.y0 > 0.2


def test_compressed1():
    fig, axs = plt.subplots(3, 2, layout='compressed',
                            sharex=True, sharey=True)
    for ax in axs.flat:
        pc = ax.imshow(np.random.randn(20, 20))

    fig.colorbar(pc, ax=axs)
    fig.draw_without_rendering()

    pos = axs[0, 0].get_position()
    np.testing.assert_allclose(pos.x0, 0.2381, atol=1e-2)
    pos = axs[0, 1].get_position()
    np.testing.assert_allclose(pos.x1, 0.7024, atol=1e-3)

    # wider than tall
    fig, axs = plt.subplots(2, 3, layout='compressed',
                            sharex=True, sharey=True, figsize=(5, 4))
    for ax in axs.flat:
        pc = ax.imshow(np.random.randn(20, 20))

    fig.colorbar(pc, ax=axs)
    fig.draw_without_rendering()

    pos = axs[0, 0].get_position()
    np.testing.assert_allclose(pos.x0, 0.05653, atol=1e-3)
    np.testing.assert_allclose(pos.y1, 0.8603, atol=1e-2)
    pos = axs[1, 2].get_position()
    np.testing.assert_allclose(pos.x1, 0.8728, atol=1e-3)
    np.testing.assert_allclose(pos.y0, 0.1808, atol=1e-2)


def test_compressed_suptitle():
    fig, (ax0, ax1) = plt.subplots(
        nrows=2, figsize=(4, 10), layout="compressed",
        gridspec_kw={"height_ratios": (1 / 4, 3 / 4), "hspace": 0})

    ax0.axis("equal")
    ax0.set_box_aspect(1/3)

    ax1.axis("equal")
    ax1.set_box_aspect(1)

    title = fig.suptitle("Title")
    fig.draw_without_rendering()
    assert title.get_position()[1] == pytest.approx(0.7491, abs=1e-3)

    title = fig.suptitle("Title", y=0.98)
    fig.draw_without_rendering()
    assert title.get_position()[1] == 0.98

    title = fig.suptitle("Title", in_layout=False)
    fig.draw_without_rendering()
    assert title.get_position()[1] == 0.98


@pytest.mark.parametrize('arg, state', [
    (True, True),
    (False, False),
    ({}, True),
    ({'rect': None}, True)
])
def test_set_constrained_layout(arg, state):
    fig, ax = plt.subplots(constrained_layout=arg)
    assert fig.get_constrained_layout() is state


def test_constrained_toggle():
    fig, ax = plt.subplots()
    with pytest.warns(PendingDeprecationWarning):
        fig.set_constrained_layout(True)
        assert fig.get_constrained_layout()
        fig.set_constrained_layout(False)
        assert not fig.get_constrained_layout()
        fig.set_constrained_layout(True)
        assert fig.get_constrained_layout()


def test_layout_leak():
    # Make sure there aren't any cyclic references when using LayoutGrid
    # GH #25853
    fig = plt.figure(constrained_layout=True, figsize=(10, 10))
    fig.add_subplot()
    fig.draw_without_rendering()
    plt.close("all")
    del fig
    gc.collect()
    assert not any(isinstance(obj, mpl._layoutgrid.LayoutGrid)
                   for obj in gc.get_objects())


def test_submerged_subfig():
    """
    Test that the submerged margin logic does not get called multiple times
    on same axes if it is already in a subfigure
    """
    fig = plt.figure(figsize=(4, 5), layout='constrained')
    figures = fig.subfigures(3, 1)
    axs = []
    for f in figures.flatten():
        gs = f.add_gridspec(2, 2)
        for i in range(2):
            axs += [f.add_subplot(gs[i, 0])]
            axs[-1].plot()
        f.add_subplot(gs[:, 1]).plot()
    fig.draw_without_rendering()
    for ax in axs[1:]:
        assert np.allclose(ax.get_position().bounds[-1],
                           axs[0].get_position().bounds[-1], atol=1e-6)
