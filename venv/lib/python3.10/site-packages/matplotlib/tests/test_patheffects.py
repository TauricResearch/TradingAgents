import platform

import numpy as np

from matplotlib.testing.decorators import image_comparison
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from matplotlib.path import Path
import matplotlib.patches as patches
from matplotlib.backend_bases import RendererBase
from matplotlib.patheffects import PathEffectRenderer


@image_comparison(['patheffect1'], remove_text=True)
def test_patheffect1():
    ax1 = plt.subplot()
    ax1.imshow([[1, 2], [2, 3]])
    txt = ax1.annotate("test", (1., 1.), (0., 0),
                       arrowprops=dict(arrowstyle="->",
                                       connectionstyle="angle3", lw=2),
                       size=20, ha="center",
                       path_effects=[path_effects.withStroke(linewidth=3,
                                                             foreground="w")])
    txt.arrow_patch.set_path_effects([path_effects.Stroke(linewidth=5,
                                                          foreground="w"),
                                      path_effects.Normal()])

    pe = [path_effects.withStroke(linewidth=3, foreground="w")]
    ax1.grid(True, linestyle="-", path_effects=pe)


@image_comparison(['patheffect2'], remove_text=True, style='mpl20',
                  tol=0 if platform.machine() == 'x86_64' else 0.06)
def test_patheffect2():

    ax2 = plt.subplot()
    arr = np.arange(25).reshape((5, 5))
    ax2.imshow(arr, interpolation='nearest')
    cntr = ax2.contour(arr, colors="k")
    cntr.set(path_effects=[path_effects.withStroke(linewidth=3, foreground="w")])

    clbls = ax2.clabel(cntr, fmt="%2.0f", use_clabeltext=True)
    plt.setp(clbls,
             path_effects=[path_effects.withStroke(linewidth=3,
                                                   foreground="w")])


@image_comparison(['patheffect3'],
                  tol=0 if platform.machine() == 'x86_64' else 0.019)
def test_patheffect3():
    p1, = plt.plot([1, 3, 5, 4, 3], 'o-b', lw=4)
    p1.set_path_effects([path_effects.SimpleLineShadow(),
                         path_effects.Normal()])
    plt.title(
        r'testing$^{123}$',
        path_effects=[path_effects.withStroke(linewidth=1, foreground="r")])
    leg = plt.legend([p1], [r'Line 1$^2$'], fancybox=True, loc='upper left')
    leg.legendPatch.set_path_effects([path_effects.withSimplePatchShadow()])

    text = plt.text(2, 3, 'Drop test', color='white',
                    bbox={'boxstyle': 'circle,pad=0.1', 'color': 'red'})
    pe = [path_effects.Stroke(linewidth=3.75, foreground='k'),
          path_effects.withSimplePatchShadow((6, -3), shadow_rgbFace='blue')]
    text.set_path_effects(pe)
    text.get_bbox_patch().set_path_effects(pe)

    pe = [path_effects.PathPatchEffect(offset=(4, -4), hatch='xxxx',
                                       facecolor='gray'),
          path_effects.PathPatchEffect(edgecolor='white', facecolor='black',
                                       lw=1.1)]

    t = plt.gcf().text(0.02, 0.1, 'Hatch shadow', fontsize=75, weight=1000,
                       va='center')
    t.set_path_effects(pe)


@image_comparison(['stroked_text.png'])
def test_patheffects_stroked_text():
    text_chunks = [
        'A B C D E F G H I J K L',
        'M N O P Q R S T U V W',
        'X Y Z a b c d e f g h i j',
        'k l m n o p q r s t u v',
        'w x y z 0123456789',
        r"!@#$%^&*()-=_+[]\;'",
        ',./{}|:"<>?'
    ]
    font_size = 50

    ax = plt.axes((0, 0, 1, 1))
    for i, chunk in enumerate(text_chunks):
        text = ax.text(x=0.01, y=(0.9 - i * 0.13), s=chunk,
                       fontdict={'ha': 'left', 'va': 'center',
                                 'size': font_size, 'color': 'white'})

        text.set_path_effects([path_effects.Stroke(linewidth=font_size / 10,
                                                   foreground='black'),
                               path_effects.Normal()])

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')


def test_PathEffect_points_to_pixels():
    fig = plt.figure(dpi=150)
    p1, = plt.plot(range(10))
    p1.set_path_effects([path_effects.SimpleLineShadow(),
                         path_effects.Normal()])
    renderer = fig.canvas.get_renderer()
    pe_renderer = path_effects.PathEffectRenderer(
        p1.get_path_effects(), renderer)
    # Confirm that using a path effects renderer maintains point sizes
    # appropriately. Otherwise rendered font would be the wrong size.
    assert renderer.points_to_pixels(15) == pe_renderer.points_to_pixels(15)


def test_SimplePatchShadow_offset():
    pe = path_effects.SimplePatchShadow(offset=(4, 5))
    assert pe._offset == (4, 5)


@image_comparison(['collection'], tol=0.03, style='mpl20')
def test_collection():
    x, y = np.meshgrid(np.linspace(0, 10, 150), np.linspace(-5, 5, 100))
    data = np.sin(x) + np.cos(y)
    cs = plt.contour(data)
    cs.set(path_effects=[
        path_effects.PathPatchEffect(edgecolor='black', facecolor='none', linewidth=12),
        path_effects.Stroke(linewidth=5)])
    for text in plt.clabel(cs, colors='white'):
        text.set_path_effects([path_effects.withStroke(foreground='k',
                                                       linewidth=3)])
        text.set_bbox({'boxstyle': 'sawtooth', 'facecolor': 'none',
                       'edgecolor': 'blue'})


@image_comparison(['tickedstroke'], remove_text=True, extensions=['png'],
                  tol=0.22)  # Increased tolerance due to fixed clipping.
def test_tickedstroke():
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(12, 4))
    path = Path.unit_circle()
    patch = patches.PathPatch(path, facecolor='none', lw=2, path_effects=[
        path_effects.withTickedStroke(angle=-90, spacing=10,
                                      length=1)])

    ax1.add_patch(patch)
    ax1.axis('equal')
    ax1.set_xlim(-2, 2)
    ax1.set_ylim(-2, 2)

    ax2.plot([0, 1], [0, 1], label=' ',
             path_effects=[path_effects.withTickedStroke(spacing=7,
                                                         angle=135)])
    nx = 101
    x = np.linspace(0.0, 1.0, nx)
    y = 0.3 * np.sin(x * 8) + 0.4
    ax2.plot(x, y, label=' ', path_effects=[path_effects.withTickedStroke()])

    ax2.legend()

    nx = 101
    ny = 105

    # Set up survey vectors
    xvec = np.linspace(0.001, 4.0, nx)
    yvec = np.linspace(0.001, 4.0, ny)

    # Set up survey matrices.  Design disk loading and gear ratio.
    x1, x2 = np.meshgrid(xvec, yvec)

    # Evaluate some stuff to plot
    g1 = -(3 * x1 + x2 - 5.5)
    g2 = -(x1 + 2 * x2 - 4)
    g3 = .8 + x1 ** -3 - x2

    cg1 = ax3.contour(x1, x2, g1, [0], colors=('k',))
    cg1.set(path_effects=[path_effects.withTickedStroke(angle=135)])

    cg2 = ax3.contour(x1, x2, g2, [0], colors=('r',))
    cg2.set(path_effects=[path_effects.withTickedStroke(angle=60, length=2)])

    cg3 = ax3.contour(x1, x2, g3, [0], colors=('b',))
    cg3.set(path_effects=[path_effects.withTickedStroke(spacing=7)])

    ax3.set_xlim(0, 4)
    ax3.set_ylim(0, 4)


@image_comparison(['spaces_and_newlines.png'], remove_text=True)
def test_patheffects_spaces_and_newlines():
    ax = plt.subplot()
    s1 = "         "
    s2 = "\nNewline also causes problems"
    text1 = ax.text(0.5, 0.75, s1, ha='center', va='center', size=20,
                    bbox={'color': 'salmon'})
    text2 = ax.text(0.5, 0.25, s2, ha='center', va='center', size=20,
                    bbox={'color': 'thistle'})
    text1.set_path_effects([path_effects.Normal()])
    text2.set_path_effects([path_effects.Normal()])


def test_patheffects_overridden_methods_open_close_group():
    class CustomRenderer(RendererBase):
        def __init__(self):
            super().__init__()

        def open_group(self, s, gid=None):
            return "open_group overridden"

        def close_group(self, s):
            return "close_group overridden"

    renderer = PathEffectRenderer([path_effects.Normal()], CustomRenderer())

    assert renderer.open_group('s') == "open_group overridden"
    assert renderer.close_group('s') == "close_group overridden"
