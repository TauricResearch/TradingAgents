"""
Test output reproducibility.
"""

import os
import sys

import pytest

import matplotlib as mpl
from matplotlib import pyplot as plt
from matplotlib.cbook import get_sample_data
from matplotlib.collections import PathCollection
from matplotlib.image import BboxImage
from matplotlib.offsetbox import AnchoredOffsetbox, AuxTransformBox
from matplotlib.patches import Circle, PathPatch
from matplotlib.path import Path
from matplotlib.testing import subprocess_run_for_testing
from matplotlib.testing._markers import needs_ghostscript, needs_usetex
import matplotlib.testing.compare
from matplotlib.text import TextPath
from matplotlib.transforms import IdentityTransform


def _save_figure(objects='mhip', fmt="pdf", usetex=False):
    mpl.use(fmt)
    mpl.rcParams.update({'svg.hashsalt': 'asdf', 'text.usetex': usetex})

    fig = plt.figure()

    if 'm' in objects:
        # use different markers...
        ax1 = fig.add_subplot(1, 6, 1)
        x = range(10)
        ax1.plot(x, [1] * 10, marker='D')
        ax1.plot(x, [2] * 10, marker='x')
        ax1.plot(x, [3] * 10, marker='^')
        ax1.plot(x, [4] * 10, marker='H')
        ax1.plot(x, [5] * 10, marker='v')

    if 'h' in objects:
        # also use different hatch patterns
        ax2 = fig.add_subplot(1, 6, 2)
        bars = (ax2.bar(range(1, 5), range(1, 5)) +
                ax2.bar(range(1, 5), [6] * 4, bottom=range(1, 5)))
        ax2.set_xticks([1.5, 2.5, 3.5, 4.5])

        patterns = ('-', '+', 'x', '\\', '*', 'o', 'O', '.')
        for bar, pattern in zip(bars, patterns):
            bar.set_hatch(pattern)

    if 'i' in objects:
        # also use different images
        A = [[1, 2, 3], [2, 3, 1], [3, 1, 2]]
        fig.add_subplot(1, 6, 3).imshow(A, interpolation='nearest')
        A = [[1, 3, 2], [1, 2, 3], [3, 1, 2]]
        fig.add_subplot(1, 6, 4).imshow(A, interpolation='bilinear')
        A = [[2, 3, 1], [1, 2, 3], [2, 1, 3]]
        fig.add_subplot(1, 6, 5).imshow(A, interpolation='bicubic')

    if 'p' in objects:

        # clipping support class, copied from demo_text_path.py gallery example
        class PathClippedImagePatch(PathPatch):
            """
            The given image is used to draw the face of the patch. Internally,
            it uses BboxImage whose clippath set to the path of the patch.

            FIXME : The result is currently dpi dependent.
            """

            def __init__(self, path, bbox_image, **kwargs):
                super().__init__(path, **kwargs)
                self.bbox_image = BboxImage(
                    self.get_window_extent, norm=None, origin=None)
                self.bbox_image.set_data(bbox_image)

            def set_facecolor(self, color):
                """Simply ignore facecolor."""
                super().set_facecolor("none")

            def draw(self, renderer=None):
                # the clip path must be updated every draw. any solution? -JJ
                self.bbox_image.set_clip_path(self._path, self.get_transform())
                self.bbox_image.draw(renderer)
                super().draw(renderer)

        # add a polar projection
        px = fig.add_subplot(projection="polar")
        pimg = px.imshow([[2]])
        pimg.set_clip_path(Circle((0, 1), radius=0.3333))

        # add a text-based clipping path (origin: demo_text_path.py)
        (ax1, ax2) = fig.subplots(2)
        arr = plt.imread(get_sample_data("grace_hopper.jpg"))
        text_path = TextPath((0, 0), "!?", size=150)
        p = PathClippedImagePatch(text_path, arr, ec="k")
        offsetbox = AuxTransformBox(IdentityTransform())
        offsetbox.add_artist(p)
        ao = AnchoredOffsetbox(loc='upper left', child=offsetbox, frameon=True,
                               borderpad=0.2)
        ax1.add_artist(ao)

        # add a 2x2 grid of path-clipped axes (origin: test_artist.py)
        exterior = Path.unit_rectangle().deepcopy()
        exterior.vertices *= 4
        exterior.vertices -= 2
        interior = Path.unit_circle().deepcopy()
        interior.vertices = interior.vertices[::-1]
        clip_path = Path.make_compound_path(exterior, interior)

        star = Path.unit_regular_star(6).deepcopy()
        star.vertices *= 2.6

        (row1, row2) = fig.subplots(2, 2, sharex=True, sharey=True)
        for row in (row1, row2):
            ax1, ax2 = row
            collection = PathCollection([star], lw=5, edgecolor='blue',
                                        facecolor='red', alpha=0.7, hatch='*')
            collection.set_clip_path(clip_path, ax1.transData)
            ax1.add_collection(collection)

            patch = PathPatch(star, lw=5, edgecolor='blue', facecolor='red',
                              alpha=0.7, hatch='*')
            patch.set_clip_path(clip_path, ax2.transData)
            ax2.add_patch(patch)

            ax1.set_xlim([-3, 3])
            ax1.set_ylim([-3, 3])

    x = range(5)
    ax = fig.add_subplot(1, 6, 6)
    ax.plot(x, x)
    ax.set_title('A string $1+2+\\sigma$')
    ax.set_xlabel('A string $1+2+\\sigma$')
    ax.set_ylabel('A string $1+2+\\sigma$')

    stdout = getattr(sys.stdout, 'buffer', sys.stdout)
    fig.savefig(stdout, format=fmt)


@pytest.mark.parametrize(
    "objects, fmt, usetex", [
        ("", "pdf", False),
        ("m", "pdf", False),
        ("h", "pdf", False),
        ("i", "pdf", False),
        ("mhip", "pdf", False),
        ("mhip", "ps", False),
        pytest.param(
            "mhip", "ps", True, marks=[needs_usetex, needs_ghostscript]),
        ("p", "svg", False),
        ("mhip", "svg", False),
        pytest.param("mhip", "svg", True, marks=needs_usetex),
    ]
)
def test_determinism_check(objects, fmt, usetex):
    """
    Output three times the same graphs and checks that the outputs are exactly
    the same.

    Parameters
    ----------
    objects : str
        Objects to be included in the test document: 'm' for markers, 'h' for
        hatch patterns, 'i' for images, and 'p' for paths.
    fmt : {"pdf", "ps", "svg"}
        Output format.
    """
    plots = [
        subprocess_run_for_testing(
            [sys.executable, "-R", "-c",
             f"from matplotlib.tests.test_determinism import _save_figure;"
             f"_save_figure({objects!r}, {fmt!r}, {usetex})"],
            env={**os.environ, "SOURCE_DATE_EPOCH": "946684800",
                 "MPLBACKEND": "Agg"},
            text=False, capture_output=True, check=True).stdout
        for _ in range(3)
    ]
    for p in plots[1:]:
        if fmt == "ps" and usetex:
            if p != plots[0]:
                pytest.skip("failed, maybe due to ghostscript timestamps")
        else:
            assert p == plots[0]


@pytest.mark.parametrize(
    "fmt, string", [
        ("pdf", b"/CreationDate (D:20000101000000Z)"),
        # SOURCE_DATE_EPOCH support is not tested with text.usetex,
        # because the produced timestamp comes from ghostscript:
        # %%CreationDate: D:20000101000000Z00\'00\', and this could change
        # with another ghostscript version.
        ("ps", b"%%CreationDate: Sat Jan 01 00:00:00 2000"),
    ]
)
def test_determinism_source_date_epoch(fmt, string):
    """
    Test SOURCE_DATE_EPOCH support. Output a document with the environment
    variable SOURCE_DATE_EPOCH set to 2000-01-01 00:00 UTC and check that the
    document contains the timestamp that corresponds to this date (given as an
    argument).

    Parameters
    ----------
    fmt : {"pdf", "ps", "svg"}
        Output format.
    string : bytes
        Timestamp string for 2000-01-01 00:00 UTC.
    """
    buf = subprocess_run_for_testing(
        [sys.executable, "-R", "-c",
         f"from matplotlib.tests.test_determinism import _save_figure; "
         f"_save_figure('', {fmt!r})"],
        env={**os.environ, "SOURCE_DATE_EPOCH": "946684800",
             "MPLBACKEND": "Agg"}, capture_output=True, text=False, check=True).stdout
    assert string in buf
