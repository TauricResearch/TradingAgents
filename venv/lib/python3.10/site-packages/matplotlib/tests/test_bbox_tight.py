from io import BytesIO
import platform

import numpy as np

from matplotlib.testing.decorators import image_comparison
import matplotlib.pyplot as plt
import matplotlib.path as mpath
import matplotlib.patches as mpatches
from matplotlib.ticker import FuncFormatter


@image_comparison(['bbox_inches_tight'], remove_text=True,
                  savefig_kwarg={'bbox_inches': 'tight'})
def test_bbox_inches_tight():
    #: Test that a figure saved using bbox_inches='tight' is clipped correctly
    data = [[66386, 174296, 75131, 577908, 32015],
            [58230, 381139, 78045, 99308, 160454],
            [89135, 80552, 152558, 497981, 603535],
            [78415, 81858, 150656, 193263, 69638],
            [139361, 331509, 343164, 781380, 52269]]

    col_labels = row_labels = [''] * 5

    rows = len(data)
    ind = np.arange(len(col_labels)) + 0.3  # the x locations for the groups
    cell_text = []
    width = 0.4  # the width of the bars
    yoff = np.zeros(len(col_labels))
    # the bottom values for stacked bar chart
    fig, ax = plt.subplots(1, 1)
    for row in range(rows):
        ax.bar(ind, data[row], width, bottom=yoff, align='edge', color='b')
        yoff = yoff + data[row]
        cell_text.append([''])
    plt.xticks([])
    plt.xlim(0, 5)
    plt.legend([''] * 5, loc=(1.2, 0.2))
    fig.legend([''] * 5, bbox_to_anchor=(0, 0.2), loc='lower left')
    # Add a table at the bottom of the axes
    cell_text.reverse()
    plt.table(cellText=cell_text, rowLabels=row_labels, colLabels=col_labels,
              loc='bottom')


@image_comparison(['bbox_inches_tight_suptile_legend'],
                  savefig_kwarg={'bbox_inches': 'tight'},
                  tol=0 if platform.machine() == 'x86_64' else 0.02)
def test_bbox_inches_tight_suptile_legend():
    plt.plot(np.arange(10), label='a straight line')
    plt.legend(bbox_to_anchor=(0.9, 1), loc='upper left')
    plt.title('Axis title')
    plt.suptitle('Figure title')

    # put an extra long y tick on to see that the bbox is accounted for
    def y_formatter(y, pos):
        if int(y) == 4:
            return 'The number 4'
        else:
            return str(y)
    plt.gca().yaxis.set_major_formatter(FuncFormatter(y_formatter))

    plt.xlabel('X axis')


@image_comparison(['bbox_inches_tight_suptile_non_default.png'],
                  savefig_kwarg={'bbox_inches': 'tight'},
                  tol=0.1)  # large tolerance because only testing clipping.
def test_bbox_inches_tight_suptitle_non_default():
    fig, ax = plt.subplots()
    fig.suptitle('Booo', x=0.5, y=1.1)


@image_comparison(['bbox_inches_tight_layout.png'], remove_text=True,
                  style='mpl20',
                  savefig_kwarg=dict(bbox_inches='tight', pad_inches='layout'))
def test_bbox_inches_tight_layout_constrained():
    fig, ax = plt.subplots(layout='constrained')
    fig.get_layout_engine().set(h_pad=0.5)
    ax.set_aspect('equal')


def test_bbox_inches_tight_layout_notconstrained(tmp_path):
    # pad_inches='layout' should be ignored when not using constrained/
    # compressed layout.  Smoke test that savefig doesn't error in this case.
    fig, ax = plt.subplots()
    fig.savefig(tmp_path / 'foo.png', bbox_inches='tight', pad_inches='layout')


@image_comparison(['bbox_inches_tight_clipping'],
                  remove_text=True, savefig_kwarg={'bbox_inches': 'tight'})
def test_bbox_inches_tight_clipping():
    # tests bbox clipping on scatter points, and path clipping on a patch
    # to generate an appropriately tight bbox
    plt.scatter(np.arange(10), np.arange(10))
    ax = plt.gca()
    ax.set_xlim(0, 5)
    ax.set_ylim(0, 5)

    # make a massive rectangle and clip it with a path
    patch = mpatches.Rectangle([-50, -50], 100, 100,
                               transform=ax.transData,
                               facecolor='blue', alpha=0.5)

    path = mpath.Path.unit_regular_star(5).deepcopy()
    path.vertices *= 0.25
    patch.set_clip_path(path, transform=ax.transAxes)
    plt.gcf().artists.append(patch)


@image_comparison(['bbox_inches_tight_raster'],
                  remove_text=True, savefig_kwarg={'bbox_inches': 'tight'})
def test_bbox_inches_tight_raster():
    """Test rasterization with tight_layout"""
    fig, ax = plt.subplots()
    ax.plot([1.0, 2.0], rasterized=True)


def test_only_on_non_finite_bbox():
    fig, ax = plt.subplots()
    ax.annotate("", xy=(0, float('nan')))
    ax.set_axis_off()
    # we only need to test that it does not error out on save
    fig.savefig(BytesIO(), bbox_inches='tight', format='png')


def test_tight_pcolorfast():
    fig, ax = plt.subplots()
    ax.pcolorfast(np.arange(4).reshape((2, 2)))
    ax.set(ylim=(0, .1))
    buf = BytesIO()
    fig.savefig(buf, bbox_inches="tight")
    buf.seek(0)
    height, width, _ = plt.imread(buf).shape
    # Previously, the bbox would include the area of the image clipped out by
    # the axes, resulting in a very tall image given the y limits of (0, 0.1).
    assert width > height


def test_noop_tight_bbox():
    from PIL import Image
    x_size, y_size = (10, 7)
    dpi = 100
    # make the figure just the right size up front
    fig = plt.figure(frameon=False, dpi=dpi, figsize=(x_size/dpi, y_size/dpi))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_axis_off()
    ax.xaxis.set_visible(False)
    ax.yaxis.set_visible(False)

    data = np.arange(x_size * y_size).reshape(y_size, x_size)
    ax.imshow(data, rasterized=True)

    # When a rasterized Artist is included, a mixed-mode renderer does
    # additional bbox adjustment. It should also be a no-op, and not affect the
    # next save.
    fig.savefig(BytesIO(), bbox_inches='tight', pad_inches=0, format='pdf')

    out = BytesIO()
    fig.savefig(out, bbox_inches='tight', pad_inches=0)
    out.seek(0)
    im = np.asarray(Image.open(out))
    assert (im[:, :, 3] == 255).all()
    assert not (im[:, :, :3] == 255).all()
    assert im.shape == (7, 10, 4)


@image_comparison(['bbox_inches_fixed_aspect'], extensions=['png'],
                  remove_text=True, savefig_kwarg={'bbox_inches': 'tight'})
def test_bbox_inches_fixed_aspect():
    with plt.rc_context({'figure.constrained_layout.use': True}):
        fig, ax = plt.subplots()
        ax.plot([0, 1])
        ax.set_xlim(0, 1)
        ax.set_aspect('equal')
