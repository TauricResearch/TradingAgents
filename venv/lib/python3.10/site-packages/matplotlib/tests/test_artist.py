import io
from itertools import chain

import numpy as np

import pytest

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import matplotlib.path as mpath
import matplotlib.transforms as mtransforms
import matplotlib.collections as mcollections
import matplotlib.artist as martist
import matplotlib.backend_bases as mbackend_bases
import matplotlib as mpl
from matplotlib.testing.decorators import check_figures_equal, image_comparison


def test_patch_transform_of_none():
    # tests the behaviour of patches added to an Axes with various transform
    # specifications

    ax = plt.axes()
    ax.set_xlim(1, 3)
    ax.set_ylim(1, 3)

    # Draw an ellipse over data coord (2, 2) by specifying device coords.
    xy_data = (2, 2)
    xy_pix = ax.transData.transform(xy_data)

    # Not providing a transform of None puts the ellipse in data coordinates .
    e = mpatches.Ellipse(xy_data, width=1, height=1, fc='yellow', alpha=0.5)
    ax.add_patch(e)
    assert e._transform == ax.transData

    # Providing a transform of None puts the ellipse in device coordinates.
    e = mpatches.Ellipse(xy_pix, width=120, height=120, fc='coral',
                         transform=None, alpha=0.5)
    assert e.is_transform_set()
    ax.add_patch(e)
    assert isinstance(e._transform, mtransforms.IdentityTransform)

    # Providing an IdentityTransform puts the ellipse in device coordinates.
    e = mpatches.Ellipse(xy_pix, width=100, height=100,
                         transform=mtransforms.IdentityTransform(), alpha=0.5)
    ax.add_patch(e)
    assert isinstance(e._transform, mtransforms.IdentityTransform)

    # Not providing a transform, and then subsequently "get_transform" should
    # not mean that "is_transform_set".
    e = mpatches.Ellipse(xy_pix, width=120, height=120, fc='coral',
                         alpha=0.5)
    intermediate_transform = e.get_transform()
    assert not e.is_transform_set()
    ax.add_patch(e)
    assert e.get_transform() != intermediate_transform
    assert e.is_transform_set()
    assert e._transform == ax.transData


def test_collection_transform_of_none():
    # tests the behaviour of collections added to an Axes with various
    # transform specifications

    ax = plt.axes()
    ax.set_xlim(1, 3)
    ax.set_ylim(1, 3)

    # draw an ellipse over data coord (2, 2) by specifying device coords
    xy_data = (2, 2)
    xy_pix = ax.transData.transform(xy_data)

    # not providing a transform of None puts the ellipse in data coordinates
    e = mpatches.Ellipse(xy_data, width=1, height=1)
    c = mcollections.PatchCollection([e], facecolor='yellow', alpha=0.5)
    ax.add_collection(c)
    # the collection should be in data coordinates
    assert c.get_offset_transform() + c.get_transform() == ax.transData

    # providing a transform of None puts the ellipse in device coordinates
    e = mpatches.Ellipse(xy_pix, width=120, height=120)
    c = mcollections.PatchCollection([e], facecolor='coral',
                                     alpha=0.5)
    c.set_transform(None)
    ax.add_collection(c)
    assert isinstance(c.get_transform(), mtransforms.IdentityTransform)

    # providing an IdentityTransform puts the ellipse in device coordinates
    e = mpatches.Ellipse(xy_pix, width=100, height=100)
    c = mcollections.PatchCollection([e],
                                     transform=mtransforms.IdentityTransform(),
                                     alpha=0.5)
    ax.add_collection(c)
    assert isinstance(c.get_offset_transform(), mtransforms.IdentityTransform)


@image_comparison(["clip_path_clipping"], remove_text=True)
def test_clipping():
    exterior = mpath.Path.unit_rectangle().deepcopy()
    exterior.vertices *= 4
    exterior.vertices -= 2
    interior = mpath.Path.unit_circle().deepcopy()
    interior.vertices = interior.vertices[::-1]
    clip_path = mpath.Path.make_compound_path(exterior, interior)

    star = mpath.Path.unit_regular_star(6).deepcopy()
    star.vertices *= 2.6

    fig, (ax1, ax2) = plt.subplots(1, 2, sharex=True, sharey=True)

    col = mcollections.PathCollection([star], lw=5, edgecolor='blue',
                                      facecolor='red', alpha=0.7, hatch='*')
    col.set_clip_path(clip_path, ax1.transData)
    ax1.add_collection(col)

    patch = mpatches.PathPatch(star, lw=5, edgecolor='blue', facecolor='red',
                               alpha=0.7, hatch='*')
    patch.set_clip_path(clip_path, ax2.transData)
    ax2.add_patch(patch)

    ax1.set_xlim([-3, 3])
    ax1.set_ylim([-3, 3])


@check_figures_equal(extensions=['png'])
def test_clipping_zoom(fig_test, fig_ref):
    # This test places the Axes and sets its limits such that the clip path is
    # outside the figure entirely. This should not break the clip path.
    ax_test = fig_test.add_axes([0, 0, 1, 1])
    l, = ax_test.plot([-3, 3], [-3, 3])
    # Explicit Path instead of a Rectangle uses clip path processing, instead
    # of a clip box optimization.
    p = mpath.Path([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]])
    p = mpatches.PathPatch(p, transform=ax_test.transData)
    l.set_clip_path(p)

    ax_ref = fig_ref.add_axes([0, 0, 1, 1])
    ax_ref.plot([-3, 3], [-3, 3])

    ax_ref.set(xlim=(0.5, 0.75), ylim=(0.5, 0.75))
    ax_test.set(xlim=(0.5, 0.75), ylim=(0.5, 0.75))


def test_cull_markers():
    x = np.random.random(20000)
    y = np.random.random(20000)

    fig, ax = plt.subplots()
    ax.plot(x, y, 'k.')
    ax.set_xlim(2, 3)

    pdf = io.BytesIO()
    fig.savefig(pdf, format="pdf")
    assert len(pdf.getvalue()) < 8000

    svg = io.BytesIO()
    fig.savefig(svg, format="svg")
    assert len(svg.getvalue()) < 20000


@image_comparison(['hatching'], remove_text=True, style='default')
def test_hatching():
    fig, ax = plt.subplots(1, 1)

    # Default hatch color.
    rect1 = mpatches.Rectangle((0, 0), 3, 4, hatch='/')
    ax.add_patch(rect1)

    rect2 = mcollections.RegularPolyCollection(
        4, sizes=[16000], offsets=[(1.5, 6.5)], offset_transform=ax.transData,
        hatch='/')
    ax.add_collection(rect2)

    # Ensure edge color is not applied to hatching.
    rect3 = mpatches.Rectangle((4, 0), 3, 4, hatch='/', edgecolor='C1')
    ax.add_patch(rect3)

    rect4 = mcollections.RegularPolyCollection(
        4, sizes=[16000], offsets=[(5.5, 6.5)], offset_transform=ax.transData,
        hatch='/', edgecolor='C1')
    ax.add_collection(rect4)

    ax.set_xlim(0, 7)
    ax.set_ylim(0, 9)


def test_remove():
    fig, ax = plt.subplots()
    im = ax.imshow(np.arange(36).reshape(6, 6))
    ln, = ax.plot(range(5))

    assert fig.stale
    assert ax.stale

    fig.canvas.draw()
    assert not fig.stale
    assert not ax.stale
    assert not ln.stale

    assert im in ax._mouseover_set
    assert ln not in ax._mouseover_set
    assert im.axes is ax

    im.remove()
    ln.remove()

    for art in [im, ln]:
        assert art.axes is None
        assert art.get_figure() is None

    assert im not in ax._mouseover_set
    assert fig.stale
    assert ax.stale


@image_comparison(["default_edges.png"], remove_text=True, style='default')
def test_default_edges():
    # Remove this line when this test image is regenerated.
    plt.rcParams['text.kerning_factor'] = 6

    fig, [[ax1, ax2], [ax3, ax4]] = plt.subplots(2, 2)

    ax1.plot(np.arange(10), np.arange(10), 'x',
             np.arange(10) + 1, np.arange(10), 'o')
    ax2.bar(np.arange(10), np.arange(10), align='edge')
    ax3.text(0, 0, "BOX", size=24, bbox=dict(boxstyle='sawtooth'))
    ax3.set_xlim((-1, 1))
    ax3.set_ylim((-1, 1))
    pp1 = mpatches.PathPatch(
        mpath.Path([(0, 0), (1, 0), (1, 1), (0, 0)],
                   [mpath.Path.MOVETO, mpath.Path.CURVE3,
                    mpath.Path.CURVE3, mpath.Path.CLOSEPOLY]),
        fc="none", transform=ax4.transData)
    ax4.add_patch(pp1)


def test_properties():
    ln = mlines.Line2D([], [])
    ln.properties()  # Check that no warning is emitted.


def test_setp():
    # Check empty list
    plt.setp([])
    plt.setp([[]])

    # Check arbitrary iterables
    fig, ax = plt.subplots()
    lines1 = ax.plot(range(3))
    lines2 = ax.plot(range(3))
    martist.setp(chain(lines1, lines2), 'lw', 5)
    plt.setp(ax.spines.values(), color='green')

    # Check *file* argument
    sio = io.StringIO()
    plt.setp(lines1, 'zorder', file=sio)
    assert sio.getvalue() == '  zorder: float\n'


def test_None_zorder():
    fig, ax = plt.subplots()
    ln, = ax.plot(range(5), zorder=None)
    assert ln.get_zorder() == mlines.Line2D.zorder
    ln.set_zorder(123456)
    assert ln.get_zorder() == 123456
    ln.set_zorder(None)
    assert ln.get_zorder() == mlines.Line2D.zorder


@pytest.mark.parametrize('accept_clause, expected', [
    ('', 'unknown'),
    ("ACCEPTS: [ '-' | '--' | '-.' ]", "[ '-' | '--' | '-.' ]"),
    ('ACCEPTS: Some description.', 'Some description.'),
    ('.. ACCEPTS: Some description.', 'Some description.'),
    ('arg : int', 'int'),
    ('*arg : int', 'int'),
    ('arg : int\nACCEPTS: Something else.', 'Something else. '),
])
def test_artist_inspector_get_valid_values(accept_clause, expected):
    class TestArtist(martist.Artist):
        def set_f(self, arg):
            pass

    TestArtist.set_f.__doc__ = """
    Some text.

    %s
    """ % accept_clause
    valid_values = martist.ArtistInspector(TestArtist).get_valid_values('f')
    assert valid_values == expected


def test_artist_inspector_get_aliases():
    # test the correct format and type of get_aliases method
    ai = martist.ArtistInspector(mlines.Line2D)
    aliases = ai.get_aliases()
    assert aliases["linewidth"] == {"lw"}


def test_set_alpha():
    art = martist.Artist()
    with pytest.raises(TypeError, match='^alpha must be numeric or None'):
        art.set_alpha('string')
    with pytest.raises(TypeError, match='^alpha must be numeric or None'):
        art.set_alpha([1, 2, 3])
    with pytest.raises(ValueError, match="outside 0-1 range"):
        art.set_alpha(1.1)
    with pytest.raises(ValueError, match="outside 0-1 range"):
        art.set_alpha(np.nan)


def test_set_alpha_for_array():
    art = martist.Artist()
    with pytest.raises(TypeError, match='^alpha must be numeric or None'):
        art._set_alpha_for_array('string')
    with pytest.raises(ValueError, match="outside 0-1 range"):
        art._set_alpha_for_array(1.1)
    with pytest.raises(ValueError, match="outside 0-1 range"):
        art._set_alpha_for_array(np.nan)
    with pytest.raises(ValueError, match="alpha must be between 0 and 1"):
        art._set_alpha_for_array([0.5, 1.1])
    with pytest.raises(ValueError, match="alpha must be between 0 and 1"):
        art._set_alpha_for_array([0.5, np.nan])


def test_callbacks():
    def func(artist):
        func.counter += 1

    func.counter = 0

    art = martist.Artist()
    oid = art.add_callback(func)
    assert func.counter == 0
    art.pchanged()  # must call the callback
    assert func.counter == 1
    art.set_zorder(10)  # setting a property must also call the callback
    assert func.counter == 2
    art.remove_callback(oid)
    art.pchanged()  # must not call the callback anymore
    assert func.counter == 2


def test_set_signature():
    """Test autogenerated ``set()`` for Artist subclasses."""
    class MyArtist1(martist.Artist):
        def set_myparam1(self, val):
            pass

    assert hasattr(MyArtist1.set, '_autogenerated_signature')
    assert 'myparam1' in MyArtist1.set.__doc__

    class MyArtist2(MyArtist1):
        def set_myparam2(self, val):
            pass

    assert hasattr(MyArtist2.set, '_autogenerated_signature')
    assert 'myparam1' in MyArtist2.set.__doc__
    assert 'myparam2' in MyArtist2.set.__doc__


def test_set_is_overwritten():
    """set() defined in Artist subclasses should not be overwritten."""
    class MyArtist3(martist.Artist):

        def set(self, **kwargs):
            """Not overwritten."""

    assert not hasattr(MyArtist3.set, '_autogenerated_signature')
    assert MyArtist3.set.__doc__ == "Not overwritten."

    class MyArtist4(MyArtist3):
        pass

    assert MyArtist4.set is MyArtist3.set


def test_format_cursor_data_BoundaryNorm():
    """Test if cursor data is correct when using BoundaryNorm."""
    X = np.empty((3, 3))
    X[0, 0] = 0.9
    X[0, 1] = 0.99
    X[0, 2] = 0.999
    X[1, 0] = -1
    X[1, 1] = 0
    X[1, 2] = 1
    X[2, 0] = 0.09
    X[2, 1] = 0.009
    X[2, 2] = 0.0009

    # map range -1..1 to 0..256 in 0.1 steps
    fig, ax = plt.subplots()
    fig.suptitle("-1..1 to 0..256 in 0.1")
    norm = mcolors.BoundaryNorm(np.linspace(-1, 1, 20), 256)
    img = ax.imshow(X, cmap='RdBu_r', norm=norm)

    labels_list = [
        "[0.9]",
        "[1.]",
        "[1.]",
        "[-1.0]",
        "[0.0]",
        "[1.0]",
        "[0.09]",
        "[0.009]",
        "[0.0009]",
    ]
    for v, label in zip(X.flat, labels_list):
        # label = "[{:-#.{}g}]".format(v, cbook._g_sig_digits(v, 0.1))
        assert img.format_cursor_data(v) == label

    plt.close()

    # map range -1..1 to 0..256 in 0.01 steps
    fig, ax = plt.subplots()
    fig.suptitle("-1..1 to 0..256 in 0.01")
    cmap = mpl.colormaps['RdBu_r'].resampled(200)
    norm = mcolors.BoundaryNorm(np.linspace(-1, 1, 200), 200)
    img = ax.imshow(X, cmap=cmap, norm=norm)

    labels_list = [
        "[0.90]",
        "[0.99]",
        "[1.0]",
        "[-1.00]",
        "[0.00]",
        "[1.00]",
        "[0.09]",
        "[0.009]",
        "[0.0009]",
    ]
    for v, label in zip(X.flat, labels_list):
        # label = "[{:-#.{}g}]".format(v, cbook._g_sig_digits(v, 0.01))
        assert img.format_cursor_data(v) == label

    plt.close()

    # map range -1..1 to 0..256 in 0.01 steps
    fig, ax = plt.subplots()
    fig.suptitle("-1..1 to 0..256 in 0.001")
    cmap = mpl.colormaps['RdBu_r'].resampled(2000)
    norm = mcolors.BoundaryNorm(np.linspace(-1, 1, 2000), 2000)
    img = ax.imshow(X, cmap=cmap, norm=norm)

    labels_list = [
        "[0.900]",
        "[0.990]",
        "[0.999]",
        "[-1.000]",
        "[0.000]",
        "[1.000]",
        "[0.090]",
        "[0.009]",
        "[0.0009]",
    ]
    for v, label in zip(X.flat, labels_list):
        # label = "[{:-#.{}g}]".format(v, cbook._g_sig_digits(v, 0.001))
        assert img.format_cursor_data(v) == label

    plt.close()

    # different testing data set with
    # out of bounds values for 0..1 range
    X = np.empty((7, 1))
    X[0] = -1.0
    X[1] = 0.0
    X[2] = 0.1
    X[3] = 0.5
    X[4] = 0.9
    X[5] = 1.0
    X[6] = 2.0

    labels_list = [
        "[-1.0]",
        "[0.0]",
        "[0.1]",
        "[0.5]",
        "[0.9]",
        "[1.0]",
        "[2.0]",
    ]

    fig, ax = plt.subplots()
    fig.suptitle("noclip, neither")
    norm = mcolors.BoundaryNorm(
        np.linspace(0, 1, 4, endpoint=True), 256, clip=False, extend='neither')
    img = ax.imshow(X, cmap='RdBu_r', norm=norm)
    for v, label in zip(X.flat, labels_list):
        # label = "[{:-#.{}g}]".format(v, cbook._g_sig_digits(v, 0.33))
        assert img.format_cursor_data(v) == label

    plt.close()

    fig, ax = plt.subplots()
    fig.suptitle("noclip, min")
    norm = mcolors.BoundaryNorm(
        np.linspace(0, 1, 4, endpoint=True), 256, clip=False, extend='min')
    img = ax.imshow(X, cmap='RdBu_r', norm=norm)
    for v, label in zip(X.flat, labels_list):
        # label = "[{:-#.{}g}]".format(v, cbook._g_sig_digits(v, 0.33))
        assert img.format_cursor_data(v) == label

    plt.close()

    fig, ax = plt.subplots()
    fig.suptitle("noclip, max")
    norm = mcolors.BoundaryNorm(
        np.linspace(0, 1, 4, endpoint=True), 256, clip=False, extend='max')
    img = ax.imshow(X, cmap='RdBu_r', norm=norm)
    for v, label in zip(X.flat, labels_list):
        # label = "[{:-#.{}g}]".format(v, cbook._g_sig_digits(v, 0.33))
        assert img.format_cursor_data(v) == label

    plt.close()

    fig, ax = plt.subplots()
    fig.suptitle("noclip, both")
    norm = mcolors.BoundaryNorm(
        np.linspace(0, 1, 4, endpoint=True), 256, clip=False, extend='both')
    img = ax.imshow(X, cmap='RdBu_r', norm=norm)
    for v, label in zip(X.flat, labels_list):
        # label = "[{:-#.{}g}]".format(v, cbook._g_sig_digits(v, 0.33))
        assert img.format_cursor_data(v) == label

    plt.close()

    fig, ax = plt.subplots()
    fig.suptitle("clip, neither")
    norm = mcolors.BoundaryNorm(
        np.linspace(0, 1, 4, endpoint=True), 256, clip=True, extend='neither')
    img = ax.imshow(X, cmap='RdBu_r', norm=norm)
    for v, label in zip(X.flat, labels_list):
        # label = "[{:-#.{}g}]".format(v, cbook._g_sig_digits(v, 0.33))
        assert img.format_cursor_data(v) == label

    plt.close()


def test_auto_no_rasterize():
    class Gen1(martist.Artist):
        ...

    assert 'draw' in Gen1.__dict__
    assert Gen1.__dict__['draw'] is Gen1.draw

    class Gen2(Gen1):
        ...

    assert 'draw' not in Gen2.__dict__
    assert Gen2.draw is Gen1.draw


def test_draw_wraper_forward_input():
    class TestKlass(martist.Artist):
        def draw(self, renderer, extra):
            return extra

    art = TestKlass()
    renderer = mbackend_bases.RendererBase()

    assert 'aardvark' == art.draw(renderer, 'aardvark')
    assert 'aardvark' == art.draw(renderer, extra='aardvark')


def test_get_figure():
    fig = plt.figure()
    sfig1 = fig.subfigures()
    sfig2 = sfig1.subfigures()
    ax = sfig2.subplots()

    assert fig.get_figure(root=True) is fig
    assert fig.get_figure(root=False) is fig

    assert ax.get_figure() is sfig2
    assert ax.get_figure(root=False) is sfig2
    assert ax.get_figure(root=True) is fig

    # SubFigure.get_figure has separate implementation but should give consistent
    # results to other artists.
    assert sfig2.get_figure(root=False) is sfig1
    assert sfig2.get_figure(root=True) is fig
    # Currently different results by default.
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        assert sfig2.get_figure() is fig
    # No deprecation warning if root and parent figure are the same.
    assert sfig1.get_figure() is fig

    # An artist not yet attached to anything has no figure.
    ln = mlines.Line2D([], [])
    assert ln.get_figure(root=True) is None
    assert ln.get_figure(root=False) is None

    # figure attribute is root for (Sub)Figures but parent for other artists.
    assert ax.figure is sfig2
    assert fig.figure is fig
    assert sfig2.figure is fig
