import pytest
import platform
import matplotlib.pyplot as plt
from matplotlib.testing.decorators import image_comparison
import matplotlib.patches as mpatches


def draw_arrow(ax, t, r):
    ax.annotate('', xy=(0.5, 0.5 + r), xytext=(0.5, 0.5), size=30,
                arrowprops=dict(arrowstyle=t,
                                fc="b", ec='k'))


@image_comparison(['fancyarrow_test_image.png'],
                  tol=0 if platform.machine() == 'x86_64' else 0.012)
def test_fancyarrow():
    # Added 0 to test division by zero error described in issue 3930
    r = [0.4, 0.3, 0.2, 0.1, 0]
    t = ["fancy", "simple", mpatches.ArrowStyle.Fancy()]

    fig, axs = plt.subplots(len(t), len(r), squeeze=False,
                            figsize=(8, 4.5), subplot_kw=dict(aspect=1))

    for i_r, r1 in enumerate(r):
        for i_t, t1 in enumerate(t):
            ax = axs[i_t, i_r]
            draw_arrow(ax, t1, r1)
            ax.tick_params(labelleft=False, labelbottom=False)


@image_comparison(['boxarrow_test_image.png'])
def test_boxarrow():

    styles = mpatches.BoxStyle.get_styles()

    n = len(styles)
    spacing = 1.2

    figheight = (n * spacing + .5)
    fig = plt.figure(figsize=(4 / 1.5, figheight / 1.5))

    fontsize = 0.3 * 72

    for i, stylename in enumerate(sorted(styles)):
        fig.text(0.5, ((n - i) * spacing - 0.5)/figheight, stylename,
                 ha="center",
                 size=fontsize,
                 transform=fig.transFigure,
                 bbox=dict(boxstyle=stylename, fc="w", ec="k"))


def __prepare_fancyarrow_dpi_cor_test():
    """
    Convenience function that prepares and returns a FancyArrowPatch. It aims
    at being used to test that the size of the arrow head does not depend on
    the DPI value of the exported picture.

    NB: this function *is not* a test in itself!
    """
    fig2 = plt.figure("fancyarrow_dpi_cor_test", figsize=(4, 3), dpi=50)
    ax = fig2.add_subplot()
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1])
    ax.add_patch(mpatches.FancyArrowPatch(posA=(0.3, 0.4), posB=(0.8, 0.6),
                                          lw=3, arrowstyle='->',
                                          mutation_scale=100))
    return fig2


@image_comparison(['fancyarrow_dpi_cor_100dpi.png'], remove_text=True,
                  tol=0 if platform.machine() == 'x86_64' else 0.02,
                  savefig_kwarg=dict(dpi=100))
def test_fancyarrow_dpi_cor_100dpi():
    """
    Check the export of a FancyArrowPatch @ 100 DPI. FancyArrowPatch is
    instantiated through a dedicated function because another similar test
    checks a similar export but with a different DPI value.

    Remark: test only a rasterized format.
    """

    __prepare_fancyarrow_dpi_cor_test()


@image_comparison(['fancyarrow_dpi_cor_200dpi.png'], remove_text=True,
                  tol=0 if platform.machine() == 'x86_64' else 0.02,
                  savefig_kwarg=dict(dpi=200))
def test_fancyarrow_dpi_cor_200dpi():
    """
    As test_fancyarrow_dpi_cor_100dpi, but exports @ 200 DPI. The relative size
    of the arrow head should be the same.
    """

    __prepare_fancyarrow_dpi_cor_test()


@image_comparison(['fancyarrow_dash.png'], remove_text=True, style='default')
def test_fancyarrow_dash():
    fig, ax = plt.subplots()
    e = mpatches.FancyArrowPatch((0, 0), (0.5, 0.5),
                                 arrowstyle='-|>',
                                 connectionstyle='angle3,angleA=0,angleB=90',
                                 mutation_scale=10.0,
                                 linewidth=2,
                                 linestyle='dashed',
                                 color='k')
    e2 = mpatches.FancyArrowPatch((0, 0), (0.5, 0.5),
                                  arrowstyle='-|>',
                                  connectionstyle='angle3',
                                  mutation_scale=10.0,
                                  linewidth=2,
                                  linestyle='dotted',
                                  color='k')
    ax.add_patch(e)
    ax.add_patch(e2)


@image_comparison(['arrow_styles.png'], style='mpl20', remove_text=True,
                  tol=0 if platform.machine() == 'x86_64' else 0.02)
def test_arrow_styles():
    styles = mpatches.ArrowStyle.get_styles()

    n = len(styles)
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(0, 1)
    ax.set_ylim(-1, n)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

    for i, stylename in enumerate(sorted(styles)):
        patch = mpatches.FancyArrowPatch((0.1 + (i % 2)*0.05, i),
                                         (0.45 + (i % 2)*0.05, i),
                                         arrowstyle=stylename,
                                         mutation_scale=25)
        ax.add_patch(patch)

    for i, stylename in enumerate([']-[', ']-', '-[', '|-|']):
        style = stylename
        if stylename[0] != '-':
            style += ',angleA=ANGLE'
        if stylename[-1] != '-':
            style += ',angleB=ANGLE'

        for j, angle in enumerate([-30, 60]):
            arrowstyle = style.replace('ANGLE', str(angle))
            patch = mpatches.FancyArrowPatch((0.55, 2*i + j), (0.9, 2*i + j),
                                             arrowstyle=arrowstyle,
                                             mutation_scale=25)
            ax.add_patch(patch)


@image_comparison(['connection_styles.png'], style='mpl20', remove_text=True,
                  tol=0 if platform.machine() == 'x86_64' else 0.013)
def test_connection_styles():
    styles = mpatches.ConnectionStyle.get_styles()

    n = len(styles)
    fig, ax = plt.subplots(figsize=(6, 10))
    ax.set_xlim(0, 1)
    ax.set_ylim(-1, n)

    for i, stylename in enumerate(sorted(styles)):
        patch = mpatches.FancyArrowPatch((0.1, i), (0.8, i + 0.5),
                                         arrowstyle="->",
                                         connectionstyle=stylename,
                                         mutation_scale=25)
        ax.add_patch(patch)


def test_invalid_intersection():
    conn_style_1 = mpatches.ConnectionStyle.Angle3(angleA=20, angleB=200)
    p1 = mpatches.FancyArrowPatch((.2, .2), (.5, .5),
                                  connectionstyle=conn_style_1)
    with pytest.raises(ValueError):
        plt.gca().add_patch(p1)

    conn_style_2 = mpatches.ConnectionStyle.Angle3(angleA=20, angleB=199.9)
    p2 = mpatches.FancyArrowPatch((.2, .2), (.5, .5),
                                  connectionstyle=conn_style_2)
    plt.gca().add_patch(p2)
