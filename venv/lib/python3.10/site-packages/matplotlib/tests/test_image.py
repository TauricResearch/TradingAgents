from contextlib import ExitStack
from copy import copy
import functools
import io
import os
from pathlib import Path
import platform
import sys
import urllib.request

import numpy as np
from numpy.testing import assert_array_equal
from PIL import Image

import matplotlib as mpl
from matplotlib import (
    colors, image as mimage, patches, pyplot as plt, style, rcParams)
from matplotlib.image import (AxesImage, BboxImage, FigureImage,
                              NonUniformImage, PcolorImage)
from matplotlib.testing.decorators import check_figures_equal, image_comparison
from matplotlib.transforms import Bbox, Affine2D, TransformedBbox
import matplotlib.ticker as mticker

import pytest


@image_comparison(['interp_alpha.png'], remove_text=True)
def test_alpha_interp():
    """Test the interpolation of the alpha channel on RGBA images"""
    fig, (axl, axr) = plt.subplots(1, 2)
    # full green image
    img = np.zeros((5, 5, 4))
    img[..., 1] = np.ones((5, 5))
    # transparent under main diagonal
    img[..., 3] = np.tril(np.ones((5, 5), dtype=np.uint8))
    axl.imshow(img, interpolation="none")
    axr.imshow(img, interpolation="bilinear")


@image_comparison(['interp_nearest_vs_none'],
                  extensions=['pdf', 'svg'], remove_text=True)
def test_interp_nearest_vs_none():
    """Test the effect of "nearest" and "none" interpolation"""
    # Setting dpi to something really small makes the difference very
    # visible. This works fine with pdf, since the dpi setting doesn't
    # affect anything but images, but the agg output becomes unusably
    # small.
    rcParams['savefig.dpi'] = 3
    X = np.array([[[218, 165, 32], [122, 103, 238]],
                  [[127, 255, 0], [255, 99, 71]]], dtype=np.uint8)
    fig, (ax1, ax2) = plt.subplots(1, 2)
    ax1.imshow(X, interpolation='none')
    ax1.set_title('interpolation none')
    ax2.imshow(X, interpolation='nearest')
    ax2.set_title('interpolation nearest')


@pytest.mark.parametrize('suppressComposite', [False, True])
@image_comparison(['figimage'], extensions=['png', 'pdf'])
def test_figimage(suppressComposite):
    fig = plt.figure(figsize=(2, 2), dpi=100)
    fig.suppressComposite = suppressComposite
    x, y = np.ix_(np.arange(100) / 100.0, np.arange(100) / 100)
    z = np.sin(x**2 + y**2 - x*y)
    c = np.sin(20*x**2 + 50*y**2)
    img = z + c/5

    fig.figimage(img, xo=0, yo=0, origin='lower')
    fig.figimage(img[::-1, :], xo=0, yo=100, origin='lower')
    fig.figimage(img[:, ::-1], xo=100, yo=0, origin='lower')
    fig.figimage(img[::-1, ::-1], xo=100, yo=100, origin='lower')


def test_image_python_io():
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3])
    buffer = io.BytesIO()
    fig.savefig(buffer)
    buffer.seek(0)
    plt.imread(buffer)


@pytest.mark.parametrize(
    "img_size, fig_size, interpolation",
    [(5, 2, "hanning"),  # data larger than figure.
     (5, 5, "nearest"),  # exact resample.
     (5, 10, "nearest"),  # double sample.
     (3, 2.9, "hanning"),  # <3 upsample.
     (3, 9.1, "nearest"),  # >3 upsample.
     ])
@check_figures_equal(extensions=['png'])
def test_imshow_antialiased(fig_test, fig_ref,
                            img_size, fig_size, interpolation):
    np.random.seed(19680801)
    dpi = plt.rcParams["savefig.dpi"]
    A = np.random.rand(int(dpi * img_size), int(dpi * img_size))
    for fig in [fig_test, fig_ref]:
        fig.set_size_inches(fig_size, fig_size)
    ax = fig_test.subplots()
    ax.set_position([0, 0, 1, 1])
    ax.imshow(A, interpolation='auto')
    ax = fig_ref.subplots()
    ax.set_position([0, 0, 1, 1])
    ax.imshow(A, interpolation=interpolation)


@check_figures_equal(extensions=['png'])
def test_imshow_zoom(fig_test, fig_ref):
    # should be less than 3 upsample, so should be nearest...
    np.random.seed(19680801)
    dpi = plt.rcParams["savefig.dpi"]
    A = np.random.rand(int(dpi * 3), int(dpi * 3))
    for fig in [fig_test, fig_ref]:
        fig.set_size_inches(2.9, 2.9)
    ax = fig_test.subplots()
    ax.imshow(A, interpolation='auto')
    ax.set_xlim([10, 20])
    ax.set_ylim([10, 20])
    ax = fig_ref.subplots()
    ax.imshow(A, interpolation='nearest')
    ax.set_xlim([10, 20])
    ax.set_ylim([10, 20])


@check_figures_equal(extensions=['png'])
def test_imshow_pil(fig_test, fig_ref):
    style.use("default")
    png_path = Path(__file__).parent / "baseline_images/pngsuite/basn3p04.png"
    tiff_path = Path(__file__).parent / "baseline_images/test_image/uint16.tif"
    axs = fig_test.subplots(2)
    axs[0].imshow(Image.open(png_path))
    axs[1].imshow(Image.open(tiff_path))
    axs = fig_ref.subplots(2)
    axs[0].imshow(plt.imread(png_path))
    axs[1].imshow(plt.imread(tiff_path))


def test_imread_pil_uint16():
    img = plt.imread(os.path.join(os.path.dirname(__file__),
                     'baseline_images', 'test_image', 'uint16.tif'))
    assert img.dtype == np.uint16
    assert np.sum(img) == 134184960


def test_imread_fspath():
    img = plt.imread(
        Path(__file__).parent / 'baseline_images/test_image/uint16.tif')
    assert img.dtype == np.uint16
    assert np.sum(img) == 134184960


@pytest.mark.parametrize("fmt", ["png", "jpg", "jpeg", "tiff"])
def test_imsave(fmt):
    has_alpha = fmt not in ["jpg", "jpeg"]

    # The goal here is that the user can specify an output logical DPI
    # for the image, but this will not actually add any extra pixels
    # to the image, it will merely be used for metadata purposes.

    # So we do the traditional case (dpi == 1), and the new case (dpi
    # == 100) and read the resulting PNG files back in and make sure
    # the data is 100% identical.
    np.random.seed(1)
    # The height of 1856 pixels was selected because going through creating an
    # actual dpi=100 figure to save the image to a Pillow-provided format would
    # cause a rounding error resulting in a final image of shape 1855.
    data = np.random.rand(1856, 2)

    buff_dpi1 = io.BytesIO()
    plt.imsave(buff_dpi1, data, format=fmt, dpi=1)

    buff_dpi100 = io.BytesIO()
    plt.imsave(buff_dpi100, data, format=fmt, dpi=100)

    buff_dpi1.seek(0)
    arr_dpi1 = plt.imread(buff_dpi1, format=fmt)

    buff_dpi100.seek(0)
    arr_dpi100 = plt.imread(buff_dpi100, format=fmt)

    assert arr_dpi1.shape == (1856, 2, 3 + has_alpha)
    assert arr_dpi100.shape == (1856, 2, 3 + has_alpha)

    assert_array_equal(arr_dpi1, arr_dpi100)


def test_imsave_python_sequences():
    # Tests saving an image with data passed using Python sequence types
    # such as lists or tuples.

    # RGB image: 3 rows × 2 columns, with float values in [0.0, 1.0]
    img_data = [
        [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [(0.0, 0.0, 1.0), (1.0, 1.0, 0.0)],
        [(0.0, 1.0, 1.0), (1.0, 0.0, 1.0)],
    ]

    buff = io.BytesIO()
    plt.imsave(buff, img_data, format="png")
    buff.seek(0)
    read_img = plt.imread(buff)

    assert_array_equal(
        np.array(img_data),
        read_img[:, :, :3]  # Drop alpha if present
    )


@pytest.mark.parametrize("origin", ["upper", "lower"])
def test_imsave_rgba_origin(origin):
    # test that imsave always passes c-contiguous arrays down to pillow
    buf = io.BytesIO()
    result = np.zeros((10, 10, 4), dtype='uint8')
    mimage.imsave(buf, arr=result, format="png", origin=origin)


@pytest.mark.parametrize("fmt", ["png", "pdf", "ps", "eps", "svg"])
def test_imsave_fspath(fmt):
    plt.imsave(Path(os.devnull), np.array([[0, 1]]), format=fmt)


def test_imsave_color_alpha():
    # Test that imsave accept arrays with ndim=3 where the third dimension is
    # color and alpha without raising any exceptions, and that the data is
    # acceptably preserved through a save/read roundtrip.
    np.random.seed(1)

    for origin in ['lower', 'upper']:
        data = np.random.rand(16, 16, 4)
        buff = io.BytesIO()
        plt.imsave(buff, data, origin=origin, format="png")

        buff.seek(0)
        arr_buf = plt.imread(buff)

        # Recreate the float -> uint8 conversion of the data
        # We can only expect to be the same with 8 bits of precision,
        # since that's what the PNG file used.
        data = (255*data).astype('uint8')
        if origin == 'lower':
            data = data[::-1]
        arr_buf = (255*arr_buf).astype('uint8')

        assert_array_equal(data, arr_buf)


def test_imsave_pil_kwargs_png():
    from PIL.PngImagePlugin import PngInfo
    buf = io.BytesIO()
    pnginfo = PngInfo()
    pnginfo.add_text("Software", "test")
    plt.imsave(buf, [[0, 1], [2, 3]],
               format="png", pil_kwargs={"pnginfo": pnginfo})
    im = Image.open(buf)
    assert im.info["Software"] == "test"


def test_imsave_pil_kwargs_tiff():
    from PIL.TiffTags import TAGS_V2 as TAGS
    buf = io.BytesIO()
    pil_kwargs = {"description": "test image"}
    plt.imsave(buf, [[0, 1], [2, 3]], format="tiff", pil_kwargs=pil_kwargs)
    assert len(pil_kwargs) == 1
    im = Image.open(buf)
    tags = {TAGS[k].name: v for k, v in im.tag_v2.items()}
    assert tags["ImageDescription"] == "test image"


@image_comparison(['image_alpha'], remove_text=True)
def test_image_alpha():
    np.random.seed(0)
    Z = np.random.rand(6, 6)

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3)
    ax1.imshow(Z, alpha=1.0, interpolation='none')
    ax2.imshow(Z, alpha=0.5, interpolation='none')
    ax3.imshow(Z, alpha=0.5, interpolation='nearest')


@mpl.style.context('mpl20')
@check_figures_equal(extensions=['png'])
def test_imshow_alpha(fig_test, fig_ref):
    np.random.seed(19680801)

    rgbf = np.random.rand(6, 6, 3)
    rgbu = np.uint8(rgbf * 255)
    ((ax0, ax1), (ax2, ax3)) = fig_test.subplots(2, 2)
    ax0.imshow(rgbf, alpha=0.5)
    ax1.imshow(rgbf, alpha=0.75)
    ax2.imshow(rgbu, alpha=0.5)
    ax3.imshow(rgbu, alpha=0.75)

    rgbaf = np.concatenate((rgbf, np.ones((6, 6, 1))), axis=2)
    rgbau = np.concatenate((rgbu, np.full((6, 6, 1), 255, np.uint8)), axis=2)
    ((ax0, ax1), (ax2, ax3)) = fig_ref.subplots(2, 2)
    rgbaf[:, :, 3] = 0.5
    ax0.imshow(rgbaf)
    rgbaf[:, :, 3] = 0.75
    ax1.imshow(rgbaf)
    rgbau[:, :, 3] = 127
    ax2.imshow(rgbau)
    rgbau[:, :, 3] = 191
    ax3.imshow(rgbau)


def test_cursor_data():
    from matplotlib.backend_bases import MouseEvent

    fig, ax = plt.subplots()
    im = ax.imshow(np.arange(100).reshape(10, 10), origin='upper')

    x, y = 4, 4
    xdisp, ydisp = ax.transData.transform([x, y])

    event = MouseEvent('motion_notify_event', fig.canvas, xdisp, ydisp)
    assert im.get_cursor_data(event) == 44

    # Now try for a point outside the image
    # Tests issue #4957
    x, y = 10.1, 4
    xdisp, ydisp = ax.transData.transform([x, y])

    event = MouseEvent('motion_notify_event', fig.canvas, xdisp, ydisp)
    assert im.get_cursor_data(event) is None

    # Hmm, something is wrong here... I get 0, not None...
    # But, this works further down in the tests with extents flipped
    # x, y = 0.1, -0.1
    # xdisp, ydisp = ax.transData.transform([x, y])
    # event = MouseEvent('motion_notify_event', fig.canvas, xdisp, ydisp)
    # z = im.get_cursor_data(event)
    # assert z is None, "Did not get None, got %d" % z

    ax.clear()
    # Now try with the extents flipped.
    im = ax.imshow(np.arange(100).reshape(10, 10), origin='lower')

    x, y = 4, 4
    xdisp, ydisp = ax.transData.transform([x, y])

    event = MouseEvent('motion_notify_event', fig.canvas, xdisp, ydisp)
    assert im.get_cursor_data(event) == 44

    fig, ax = plt.subplots()
    im = ax.imshow(np.arange(100).reshape(10, 10), extent=[0, 0.5, 0, 0.5])

    x, y = 0.25, 0.25
    xdisp, ydisp = ax.transData.transform([x, y])

    event = MouseEvent('motion_notify_event', fig.canvas, xdisp, ydisp)
    assert im.get_cursor_data(event) == 55

    # Now try for a point outside the image
    # Tests issue #4957
    x, y = 0.75, 0.25
    xdisp, ydisp = ax.transData.transform([x, y])

    event = MouseEvent('motion_notify_event', fig.canvas, xdisp, ydisp)
    assert im.get_cursor_data(event) is None

    x, y = 0.01, -0.01
    xdisp, ydisp = ax.transData.transform([x, y])

    event = MouseEvent('motion_notify_event', fig.canvas, xdisp, ydisp)
    assert im.get_cursor_data(event) is None

    # Now try with additional transform applied to the image artist
    trans = Affine2D().scale(2).rotate(0.5)
    im = ax.imshow(np.arange(100).reshape(10, 10),
                   transform=trans + ax.transData)
    x, y = 3, 10
    xdisp, ydisp = ax.transData.transform([x, y])
    event = MouseEvent('motion_notify_event', fig.canvas, xdisp, ydisp)
    assert im.get_cursor_data(event) == 44


@pytest.mark.parametrize("xy, data", [
    # x/y coords chosen to be 0.5 above boundaries so they lie within image pixels
    [[0.5, 0.5], 0 + 0],
    [[0.5, 1.5], 0 + 1],
    [[4.5, 0.5], 16 + 0],
    [[8.5, 0.5], 16 + 0],
    [[9.5, 2.5], 81 + 4],
    [[-1, 0.5], None],
    [[0.5, -1], None],
    ]
)
def test_cursor_data_nonuniform(xy, data):
    from matplotlib.backend_bases import MouseEvent

    # Non-linear set of x-values
    x = np.array([0, 1, 4, 9, 16])
    y = np.array([0, 1, 2, 3, 4])
    z = x[np.newaxis, :]**2 + y[:, np.newaxis]**2

    fig, ax = plt.subplots()
    im = NonUniformImage(ax, extent=(x.min(), x.max(), y.min(), y.max()))
    im.set_data(x, y, z)
    ax.add_image(im)
    # Set lower min lim so we can test cursor outside image
    ax.set_xlim(x.min() - 2, x.max())
    ax.set_ylim(y.min() - 2, y.max())

    xdisp, ydisp = ax.transData.transform(xy)
    event = MouseEvent('motion_notify_event', fig.canvas, xdisp, ydisp)
    assert im.get_cursor_data(event) == data, (im.get_cursor_data(event), data)


@pytest.mark.parametrize(
    "data, text", [
        ([[10001, 10000]], "[10001.000]"),
        ([[.123, .987]], "[0.123]"),
        ([[np.nan, 1, 2]], "[]"),
        ([[1, 1+1e-15]], "[1.0000000000000000]"),
        ([[-1, -1]], "[-1.0]"),
        ([[0, 0]], "[0.00]"),
    ])
def test_format_cursor_data(data, text):
    from matplotlib.backend_bases import MouseEvent

    fig, ax = plt.subplots()
    im = ax.imshow(data)

    xdisp, ydisp = ax.transData.transform([0, 0])
    event = MouseEvent('motion_notify_event', fig.canvas, xdisp, ydisp)
    assert im.format_cursor_data(im.get_cursor_data(event)) == text


@image_comparison(['image_clip'], style='mpl20')
def test_image_clip():
    d = [[1, 2], [3, 4]]

    fig, ax = plt.subplots()
    im = ax.imshow(d)
    patch = patches.Circle((0, 0), radius=1, transform=ax.transData)
    im.set_clip_path(patch)


@image_comparison(['image_cliprect'], style='mpl20')
def test_image_cliprect():
    fig, ax = plt.subplots()
    d = [[1, 2], [3, 4]]

    im = ax.imshow(d, extent=(0, 5, 0, 5))

    rect = patches.Rectangle(
        xy=(1, 1), width=2, height=2, transform=im.axes.transData)
    im.set_clip_path(rect)


@check_figures_equal(extensions=['png'])
def test_imshow_10_10_1(fig_test, fig_ref):
    # 10x10x1 should be the same as 10x10
    arr = np.arange(100).reshape((10, 10, 1))
    ax = fig_ref.subplots()
    ax.imshow(arr[:, :, 0], interpolation="bilinear", extent=(1, 2, 1, 2))
    ax.set_xlim(0, 3)
    ax.set_ylim(0, 3)

    ax = fig_test.subplots()
    ax.imshow(arr, interpolation="bilinear", extent=(1, 2, 1, 2))
    ax.set_xlim(0, 3)
    ax.set_ylim(0, 3)


def test_imshow_10_10_2():
    fig, ax = plt.subplots()
    arr = np.arange(200).reshape((10, 10, 2))
    with pytest.raises(TypeError):
        ax.imshow(arr)


def test_imshow_10_10_5():
    fig, ax = plt.subplots()
    arr = np.arange(500).reshape((10, 10, 5))
    with pytest.raises(TypeError):
        ax.imshow(arr)


@image_comparison(['no_interpolation_origin'], remove_text=True)
def test_no_interpolation_origin():
    fig, axs = plt.subplots(2)
    axs[0].imshow(np.arange(100).reshape((2, 50)), origin="lower",
                  interpolation='none')
    axs[1].imshow(np.arange(100).reshape((2, 50)), interpolation='none')


@image_comparison(['image_shift'], remove_text=True, extensions=['pdf', 'svg'])
def test_image_shift():
    imgData = [[1 / x + 1 / y for x in range(1, 100)] for y in range(1, 100)]
    tMin = 734717.945208
    tMax = 734717.946366

    fig, ax = plt.subplots()
    ax.imshow(imgData, norm=colors.LogNorm(), interpolation='none',
              extent=(tMin, tMax, 1, 100))
    ax.set_aspect('auto')


def test_image_edges():
    fig = plt.figure(figsize=[1, 1])
    ax = fig.add_axes([0, 0, 1, 1], frameon=False)

    data = np.tile(np.arange(12), 15).reshape(20, 9)

    im = ax.imshow(data, origin='upper', extent=[-10, 10, -10, 10],
                   interpolation='none', cmap='gray')

    x = y = 2
    ax.set_xlim([-x, x])
    ax.set_ylim([-y, y])

    ax.set_xticks([])
    ax.set_yticks([])

    buf = io.BytesIO()
    fig.savefig(buf, facecolor=(0, 1, 0))

    buf.seek(0)

    im = plt.imread(buf)
    r, g, b, a = sum(im[:, 0])
    r, g, b, a = sum(im[:, -1])

    assert g != 100, 'Expected a non-green edge - but sadly, it was.'


@image_comparison(['image_composite_background'],
                  remove_text=True, style='mpl20')
def test_image_composite_background():
    fig, ax = plt.subplots()
    arr = np.arange(12).reshape(4, 3)
    ax.imshow(arr, extent=[0, 2, 15, 0])
    ax.imshow(arr, extent=[4, 6, 15, 0])
    ax.set_facecolor((1, 0, 0, 0.5))
    ax.set_xlim([0, 12])


@image_comparison(['image_composite_alpha'], remove_text=True)
def test_image_composite_alpha():
    """
    Tests that the alpha value is recognized and correctly applied in the
    process of compositing images together.
    """
    fig, ax = plt.subplots()
    arr = np.zeros((11, 21, 4))
    arr[:, :, 0] = 1
    arr[:, :, 3] = np.concatenate(
        (np.arange(0, 1.1, 0.1), np.arange(0, 1, 0.1)[::-1]))
    arr2 = np.zeros((21, 11, 4))
    arr2[:, :, 0] = 1
    arr2[:, :, 1] = 1
    arr2[:, :, 3] = np.concatenate(
        (np.arange(0, 1.1, 0.1), np.arange(0, 1, 0.1)[::-1]))[:, np.newaxis]
    ax.imshow(arr, extent=[1, 2, 5, 0], alpha=0.3)
    ax.imshow(arr, extent=[2, 3, 5, 0], alpha=0.6)
    ax.imshow(arr, extent=[3, 4, 5, 0])
    ax.imshow(arr2, extent=[0, 5, 1, 2])
    ax.imshow(arr2, extent=[0, 5, 2, 3], alpha=0.6)
    ax.imshow(arr2, extent=[0, 5, 3, 4], alpha=0.3)
    ax.set_facecolor((0, 0.5, 0, 1))
    ax.set_xlim([0, 5])
    ax.set_ylim([5, 0])


@check_figures_equal(extensions=["pdf"])
def test_clip_path_disables_compositing(fig_test, fig_ref):
    t = np.arange(9).reshape((3, 3))
    for fig in [fig_test, fig_ref]:
        ax = fig.add_subplot()
        ax.imshow(t, clip_path=(mpl.path.Path([(0, 0), (0, 1), (1, 0)]),
                                ax.transData))
        ax.imshow(t, clip_path=(mpl.path.Path([(1, 1), (1, 2), (2, 1)]),
                                ax.transData))
    fig_ref.suppressComposite = True


@image_comparison(['rasterize_10dpi'],
                  extensions=['pdf', 'svg'], remove_text=True, style='mpl20')
def test_rasterize_dpi():
    # This test should check rasterized rendering with high output resolution.
    # It plots a rasterized line and a normal image with imshow.  So it will
    # catch when images end up in the wrong place in case of non-standard dpi
    # setting.  Instead of high-res rasterization I use low-res.  Therefore
    # the fact that the resolution is non-standard is easily checked by
    # image_comparison.
    img = np.asarray([[1, 2], [3, 4]])

    fig, axs = plt.subplots(1, 3, figsize=(3, 1))

    axs[0].imshow(img)

    axs[1].plot([0, 1], [0, 1], linewidth=20., rasterized=True)
    axs[1].set(xlim=(0, 1), ylim=(-1, 2))

    axs[2].plot([0, 1], [0, 1], linewidth=20.)
    axs[2].set(xlim=(0, 1), ylim=(-1, 2))

    # Low-dpi PDF rasterization errors prevent proper image comparison tests.
    # Hide detailed structures like the axes spines.
    for ax in axs:
        ax.set_xticks([])
        ax.set_yticks([])
        ax.spines[:].set_visible(False)

    rcParams['savefig.dpi'] = 10


@image_comparison(['bbox_image_inverted'], remove_text=True, style='mpl20')
def test_bbox_image_inverted():
    # This is just used to produce an image to feed to BboxImage
    image = np.arange(100).reshape((10, 10))

    fig, ax = plt.subplots()
    bbox_im = BboxImage(
        TransformedBbox(Bbox([[100, 100], [0, 0]]), ax.transData),
        interpolation='nearest')
    bbox_im.set_data(image)
    bbox_im.set_clip_on(False)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.add_artist(bbox_im)

    image = np.identity(10)

    bbox_im = BboxImage(TransformedBbox(Bbox([[0.1, 0.2], [0.3, 0.25]]),
                                        ax.get_figure().transFigure),
                        interpolation='nearest')
    bbox_im.set_data(image)
    bbox_im.set_clip_on(False)
    ax.add_artist(bbox_im)


def test_get_window_extent_for_AxisImage():
    # Create a figure of known size (1000x1000 pixels), place an image
    # object at a given location and check that get_window_extent()
    # returns the correct bounding box values (in pixels).

    im = np.array([[0.25, 0.75, 1.0, 0.75], [0.1, 0.65, 0.5, 0.4],
                   [0.6, 0.3, 0.0, 0.2], [0.7, 0.9, 0.4, 0.6]])
    fig, ax = plt.subplots(figsize=(10, 10), dpi=100)
    ax.set_position([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    im_obj = ax.imshow(
        im, extent=[0.4, 0.7, 0.2, 0.9], interpolation='nearest')

    fig.canvas.draw()
    renderer = fig.canvas.renderer
    im_bbox = im_obj.get_window_extent(renderer)

    assert_array_equal(im_bbox.get_points(), [[400, 200], [700, 900]])

    fig, ax = plt.subplots(figsize=(10, 10), dpi=100)
    ax.set_position([0, 0, 1, 1])
    ax.set_xlim(1, 2)
    ax.set_ylim(0, 1)
    im_obj = ax.imshow(
        im, extent=[0.4, 0.7, 0.2, 0.9], interpolation='nearest',
        transform=ax.transAxes)

    fig.canvas.draw()
    renderer = fig.canvas.renderer
    im_bbox = im_obj.get_window_extent(renderer)

    assert_array_equal(im_bbox.get_points(), [[400, 200], [700, 900]])


@image_comparison(['zoom_and_clip_upper_origin.png'],
                  remove_text=True, style='mpl20')
def test_zoom_and_clip_upper_origin():
    image = np.arange(100)
    image = image.reshape((10, 10))

    fig, ax = plt.subplots()
    ax.imshow(image)
    ax.set_ylim(2.0, -0.5)
    ax.set_xlim(-0.5, 2.0)


def test_nonuniformimage_setcmap():
    ax = plt.gca()
    im = NonUniformImage(ax)
    im.set_cmap('Blues')


def test_nonuniformimage_setnorm():
    ax = plt.gca()
    im = NonUniformImage(ax)
    im.set_norm(plt.Normalize())


def test_jpeg_2d():
    # smoke test that mode-L pillow images work.
    imd = np.ones((10, 10), dtype='uint8')
    for i in range(10):
        imd[i, :] = np.linspace(0.0, 1.0, 10) * 255
    im = Image.new('L', (10, 10))
    im.putdata(imd.flatten())
    fig, ax = plt.subplots()
    ax.imshow(im)


def test_jpeg_alpha():
    plt.figure(figsize=(1, 1), dpi=300)
    # Create an image that is all black, with a gradient from 0-1 in
    # the alpha channel from left to right.
    im = np.zeros((300, 300, 4), dtype=float)
    im[..., 3] = np.linspace(0.0, 1.0, 300)

    plt.figimage(im)

    buff = io.BytesIO()
    plt.savefig(buff, facecolor="red", format='jpg', dpi=300)

    buff.seek(0)
    image = Image.open(buff)

    # If this fails, there will be only one color (all black). If this
    # is working, we should have all 256 shades of grey represented.
    num_colors = len(image.getcolors(256))
    assert 175 <= num_colors <= 230
    # The fully transparent part should be red.
    corner_pixel = image.getpixel((0, 0))
    assert corner_pixel == (254, 0, 0)


def test_axesimage_setdata():
    ax = plt.gca()
    im = AxesImage(ax)
    z = np.arange(12, dtype=float).reshape((4, 3))
    im.set_data(z)
    z[0, 0] = 9.9
    assert im._A[0, 0] == 0, 'value changed'


def test_figureimage_setdata():
    fig = plt.gcf()
    im = FigureImage(fig)
    z = np.arange(12, dtype=float).reshape((4, 3))
    im.set_data(z)
    z[0, 0] = 9.9
    assert im._A[0, 0] == 0, 'value changed'


@pytest.mark.parametrize(
    "image_cls,x,y,a", [
        (NonUniformImage,
         np.arange(3.), np.arange(4.), np.arange(12.).reshape((4, 3))),
        (PcolorImage,
         np.arange(3.), np.arange(4.), np.arange(6.).reshape((3, 2))),
    ])
def test_setdata_xya(image_cls, x, y, a):
    ax = plt.gca()
    im = image_cls(ax)
    im.set_data(x, y, a)
    x[0] = y[0] = a[0, 0] = 9.9
    assert im._A[0, 0] == im._Ax[0] == im._Ay[0] == 0, 'value changed'
    im.set_data(x, y, a.reshape((*a.shape, -1)))  # Just a smoketest.


def test_minimized_rasterized():
    # This ensures that the rasterized content in the colorbars is
    # only as thick as the colorbar, and doesn't extend to other parts
    # of the image.  See #5814.  While the original bug exists only
    # in Postscript, the best way to detect it is to generate SVG
    # and then parse the output to make sure the two colorbar images
    # are the same size.
    from xml.etree import ElementTree

    np.random.seed(0)
    data = np.random.rand(10, 10)

    fig, ax = plt.subplots(1, 2)
    p1 = ax[0].pcolormesh(data)
    p2 = ax[1].pcolormesh(data)

    plt.colorbar(p1, ax=ax[0])
    plt.colorbar(p2, ax=ax[1])

    buff = io.BytesIO()
    plt.savefig(buff, format='svg')

    buff = io.BytesIO(buff.getvalue())
    tree = ElementTree.parse(buff)
    width = None
    for image in tree.iter('image'):
        if width is None:
            width = image['width']
        else:
            if image['width'] != width:
                assert False


def test_load_from_url():
    path = Path(__file__).parent / "baseline_images/pngsuite/basn3p04.png"
    url = ('file:'
           + ('///' if sys.platform == 'win32' else '')
           + path.resolve().as_posix())
    with pytest.raises(ValueError, match="Please open the URL"):
        plt.imread(url)
    with urllib.request.urlopen(url) as file:
        plt.imread(file)


@image_comparison(['log_scale_image'], remove_text=True)
def test_log_scale_image():
    Z = np.zeros((10, 10))
    Z[::2] = 1

    fig, ax = plt.subplots()
    ax.imshow(Z, extent=[1, 100, 1, 100], cmap='viridis', vmax=1, vmin=-1,
              aspect='auto')
    ax.set(yscale='log')


@image_comparison(['rotate_image'], remove_text=True)
def test_rotate_image():
    delta = 0.25
    x = y = np.arange(-3.0, 3.0, delta)
    X, Y = np.meshgrid(x, y)
    Z1 = np.exp(-(X**2 + Y**2) / 2) / (2 * np.pi)
    Z2 = (np.exp(-(((X - 1) / 1.5)**2 + ((Y - 1) / 0.5)**2) / 2) /
          (2 * np.pi * 0.5 * 1.5))
    Z = Z2 - Z1  # difference of Gaussians

    fig, ax1 = plt.subplots(1, 1)
    im1 = ax1.imshow(Z, interpolation='none', cmap='viridis',
                     origin='lower',
                     extent=[-2, 4, -3, 2], clip_on=True)

    trans_data2 = Affine2D().rotate_deg(30) + ax1.transData
    im1.set_transform(trans_data2)

    # display intended extent of the image
    x1, x2, y1, y2 = im1.get_extent()

    ax1.plot([x1, x2, x2, x1, x1], [y1, y1, y2, y2, y1], "r--", lw=3,
             transform=trans_data2)

    ax1.set_xlim(2, 5)
    ax1.set_ylim(0, 4)


def test_image_preserve_size():
    buff = io.BytesIO()

    im = np.zeros((481, 321))
    plt.imsave(buff, im, format="png")

    buff.seek(0)
    img = plt.imread(buff)

    assert img.shape[:2] == im.shape


def test_image_preserve_size2():
    n = 7
    data = np.identity(n, float)

    fig = plt.figure(figsize=(n, n), frameon=False)
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set_axis_off()
    ax.imshow(data, interpolation='nearest', origin='lower', aspect='auto')
    buff = io.BytesIO()
    fig.savefig(buff, dpi=1)

    buff.seek(0)
    img = plt.imread(buff)

    assert img.shape == (7, 7, 4)

    assert_array_equal(np.asarray(img[:, :, 0], bool),
                       np.identity(n, bool)[::-1])


@image_comparison(['mask_image_over_under.png'], remove_text=True, tol=1.0)
def test_mask_image_over_under():

    delta = 0.025
    x = y = np.arange(-3.0, 3.0, delta)
    X, Y = np.meshgrid(x, y)
    Z1 = np.exp(-(X**2 + Y**2) / 2) / (2 * np.pi)
    Z2 = (np.exp(-(((X - 1) / 1.5)**2 + ((Y - 1) / 0.5)**2) / 2) /
          (2 * np.pi * 0.5 * 1.5))
    Z = 10*(Z2 - Z1)  # difference of Gaussians

    palette = plt.cm.gray.with_extremes(over='r', under='g', bad='b')
    Zm = np.ma.masked_where(Z > 1.2, Z)
    fig, (ax1, ax2) = plt.subplots(1, 2)
    im = ax1.imshow(Zm, interpolation='bilinear',
                    cmap=palette,
                    norm=colors.Normalize(vmin=-1.0, vmax=1.0, clip=False),
                    origin='lower', extent=[-3, 3, -3, 3])
    ax1.set_title('Green=low, Red=high, Blue=bad')
    fig.colorbar(im, extend='both', orientation='horizontal',
                 ax=ax1, aspect=10)

    im = ax2.imshow(Zm, interpolation='nearest',
                    cmap=palette,
                    norm=colors.BoundaryNorm([-1, -0.5, -0.2, 0, 0.2, 0.5, 1],
                                             ncolors=256, clip=False),
                    origin='lower', extent=[-3, 3, -3, 3])
    ax2.set_title('With BoundaryNorm')
    fig.colorbar(im, extend='both', spacing='proportional',
                 orientation='horizontal', ax=ax2, aspect=10)


@image_comparison(['mask_image'], remove_text=True)
def test_mask_image():
    # Test mask image two ways: Using nans and using a masked array.

    fig, (ax1, ax2) = plt.subplots(1, 2)

    A = np.ones((5, 5))
    A[1:2, 1:2] = np.nan

    ax1.imshow(A, interpolation='nearest')

    A = np.zeros((5, 5), dtype=bool)
    A[1:2, 1:2] = True
    A = np.ma.masked_array(np.ones((5, 5), dtype=np.uint16), A)

    ax2.imshow(A, interpolation='nearest')


def test_mask_image_all():
    # Test behavior with an image that is entirely masked does not warn
    data = np.full((2, 2), np.nan)
    fig, ax = plt.subplots()
    ax.imshow(data)
    fig.canvas.draw_idle()  # would emit a warning


@image_comparison(['imshow_endianess.png'], remove_text=True)
def test_imshow_endianess():
    x = np.arange(10)
    X, Y = np.meshgrid(x, x)
    Z = np.hypot(X - 5, Y - 5)

    fig, (ax1, ax2) = plt.subplots(1, 2)

    kwargs = dict(origin="lower", interpolation='nearest', cmap='viridis')

    ax1.imshow(Z.astype('<f8'), **kwargs)
    ax2.imshow(Z.astype('>f8'), **kwargs)


@image_comparison(['imshow_masked_interpolation'],
                  tol=0 if platform.machine() == 'x86_64' else 0.01,
                  remove_text=True, style='mpl20')
def test_imshow_masked_interpolation():

    cmap = mpl.colormaps['viridis'].with_extremes(over='r', under='b', bad='k')

    N = 20
    n = colors.Normalize(vmin=0, vmax=N*N-1)

    data = np.arange(N*N, dtype=float).reshape(N, N)

    data[5, 5] = -1
    # This will cause crazy ringing for the higher-order
    # interpolations
    data[15, 5] = 1e5

    # data[3, 3] = np.nan

    data[15, 15] = np.inf

    mask = np.zeros_like(data).astype('bool')
    mask[5, 15] = True

    data = np.ma.masked_array(data, mask)

    fig, ax_grid = plt.subplots(3, 6)
    interps = sorted(mimage._interpd_)
    interps.remove('auto')
    interps.remove('antialiased')

    for interp, ax in zip(interps, ax_grid.ravel()):
        ax.set_title(interp)
        ax.imshow(data, norm=n, cmap=cmap, interpolation=interp)
        ax.axis('off')


def test_imshow_no_warn_invalid():
    plt.imshow([[1, 2], [3, np.nan]])  # Check that no warning is emitted.


@pytest.mark.parametrize(
    'dtype', [np.dtype(s) for s in 'u2 u4 i2 i4 i8 f4 f8'.split()])
def test_imshow_clips_rgb_to_valid_range(dtype):
    arr = np.arange(300, dtype=dtype).reshape((10, 10, 3))
    if dtype.kind != 'u':
        arr -= 10
    too_low = arr < 0
    too_high = arr > 255
    if dtype.kind == 'f':
        arr = arr / 255
    _, ax = plt.subplots()
    out = ax.imshow(arr).get_array()
    assert (out[too_low] == 0).all()
    if dtype.kind == 'f':
        assert (out[too_high] == 1).all()
        assert out.dtype.kind == 'f'
    else:
        assert (out[too_high] == 255).all()
        assert out.dtype == np.uint8


@image_comparison(['imshow_flatfield.png'], remove_text=True, style='mpl20')
def test_imshow_flatfield():
    fig, ax = plt.subplots()
    im = ax.imshow(np.ones((5, 5)), interpolation='nearest')
    im.set_clim(.5, 1.5)


@image_comparison(['imshow_bignumbers.png'], remove_text=True, style='mpl20')
def test_imshow_bignumbers():
    rcParams['image.interpolation'] = 'nearest'
    # putting a big number in an array of integers shouldn't
    # ruin the dynamic range of the resolved bits.
    fig, ax = plt.subplots()
    img = np.array([[1, 2, 1e12], [3, 1, 4]], dtype=np.uint64)
    pc = ax.imshow(img)
    pc.set_clim(0, 5)


@image_comparison(['imshow_bignumbers_real.png'],
                  remove_text=True, style='mpl20')
def test_imshow_bignumbers_real():
    rcParams['image.interpolation'] = 'nearest'
    # putting a big number in an array of integers shouldn't
    # ruin the dynamic range of the resolved bits.
    fig, ax = plt.subplots()
    img = np.array([[2., 1., 1.e22], [4., 1., 3.]])
    pc = ax.imshow(img)
    pc.set_clim(0, 5)


@pytest.mark.parametrize(
    "make_norm",
    [colors.Normalize,
     colors.LogNorm,
     lambda: colors.SymLogNorm(1),
     lambda: colors.PowerNorm(1)])
def test_empty_imshow(make_norm):
    fig, ax = plt.subplots()
    with pytest.warns(UserWarning,
                      match="Attempting to set identical low and high xlims"):
        im = ax.imshow([[]], norm=make_norm())
    im.set_extent([-5, 5, -5, 5])
    fig.canvas.draw()

    with pytest.raises(RuntimeError):
        im.make_image(fig.canvas.get_renderer())


def test_imshow_float16():
    fig, ax = plt.subplots()
    ax.imshow(np.zeros((3, 3), dtype=np.float16))
    # Ensure that drawing doesn't cause crash.
    fig.canvas.draw()


def test_imshow_float128():
    fig, ax = plt.subplots()
    ax.imshow(np.zeros((3, 3), dtype=np.longdouble))
    with (ExitStack() if np.can_cast(np.longdouble, np.float64, "equiv")
          else pytest.warns(UserWarning)):
        # Ensure that drawing doesn't cause crash.
        fig.canvas.draw()


def test_imshow_bool():
    fig, ax = plt.subplots()
    ax.imshow(np.array([[True, False], [False, True]], dtype=bool))


def test_full_invalid():
    fig, ax = plt.subplots()
    ax.imshow(np.full((10, 10), np.nan))

    fig.canvas.draw()


@pytest.mark.parametrize("fmt,counted",
                         [("ps", b" colorimage"), ("svg", b"<image")])
@pytest.mark.parametrize("composite_image,count", [(True, 1), (False, 2)])
def test_composite(fmt, counted, composite_image, count):
    # Test that figures can be saved with and without combining multiple images
    # (on a single set of axes) into a single composite image.
    X, Y = np.meshgrid(np.arange(-5, 5, 1), np.arange(-5, 5, 1))
    Z = np.sin(Y ** 2)

    fig, ax = plt.subplots()
    ax.set_xlim(0, 3)
    ax.imshow(Z, extent=[0, 1, 0, 1])
    ax.imshow(Z[::-1], extent=[2, 3, 0, 1])
    plt.rcParams['image.composite_image'] = composite_image
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt)
    assert buf.getvalue().count(counted) == count


def test_relim():
    fig, ax = plt.subplots()
    ax.imshow([[0]], extent=(0, 1, 0, 1))
    ax.relim()
    ax.autoscale()
    assert ax.get_xlim() == ax.get_ylim() == (0, 1)


def test_unclipped():
    fig, ax = plt.subplots()
    ax.set_axis_off()
    im = ax.imshow([[0, 0], [0, 0]], aspect="auto", extent=(-10, 10, -10, 10),
                   cmap='gray', clip_on=False)
    ax.set(xlim=(0, 1), ylim=(0, 1))
    fig.canvas.draw()
    # The unclipped image should fill the *entire* figure and be black.
    # Ignore alpha for this comparison.
    assert (np.array(fig.canvas.buffer_rgba())[..., :3] == 0).all()


def test_respects_bbox():
    fig, axs = plt.subplots(2)
    for ax in axs:
        ax.set_axis_off()
    im = axs[1].imshow([[0, 1], [2, 3]], aspect="auto", extent=(0, 1, 0, 1))
    im.set_clip_path(None)
    # Make the image invisible in axs[1], but visible in axs[0] if we pan
    # axs[1] up.
    im.set_clip_box(axs[0].bbox)
    buf_before = io.BytesIO()
    fig.savefig(buf_before, format="rgba")
    assert {*buf_before.getvalue()} == {0xff}  # All white.
    axs[1].set(ylim=(-1, 0))
    buf_after = io.BytesIO()
    fig.savefig(buf_after, format="rgba")
    assert buf_before.getvalue() != buf_after.getvalue()  # Not all white.


def test_image_cursor_formatting():
    fig, ax = plt.subplots()
    # Create a dummy image to be able to call format_cursor_data
    im = ax.imshow(np.zeros((4, 4)))

    data = np.ma.masked_array([0], mask=[True])
    assert im.format_cursor_data(data) == '[]'

    data = np.ma.masked_array([0], mask=[False])
    assert im.format_cursor_data(data) == '[0]'

    data = np.nan
    assert im.format_cursor_data(data) == '[nan]'


@check_figures_equal()
def test_image_array_alpha(fig_test, fig_ref):
    """Per-pixel alpha channel test."""
    x = np.linspace(0, 1)
    xx, yy = np.meshgrid(x, x)

    zz = np.exp(- 3 * ((xx - 0.5) ** 2) + (yy - 0.7 ** 2))
    alpha = zz / zz.max()

    cmap = mpl.colormaps['viridis']
    ax = fig_test.add_subplot()
    ax.imshow(zz, alpha=alpha, cmap=cmap, interpolation='nearest')

    ax = fig_ref.add_subplot()
    rgba = cmap(colors.Normalize()(zz))
    rgba[..., -1] = alpha
    ax.imshow(rgba, interpolation='nearest')


def test_image_array_alpha_validation():
    with pytest.raises(TypeError, match="alpha must be a float, two-d"):
        plt.imshow(np.zeros((2, 2)), alpha=[1, 1])


@mpl.style.context('mpl20')
def test_exact_vmin():
    cmap = copy(mpl.colormaps["autumn_r"])
    cmap.set_under(color="lightgrey")

    # make the image exactly 190 pixels wide
    fig = plt.figure(figsize=(1.9, 0.1), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])

    data = np.array(
        [[-1, -1, -1, 0, 0, 0, 0, 43, 79, 95, 66, 1, -1, -1, -1, 0, 0, 0, 34]],
        dtype=float,
    )

    im = ax.imshow(data, aspect="auto", cmap=cmap, vmin=0, vmax=100)
    ax.axis("off")
    fig.canvas.draw()

    # get the RGBA slice from the image
    from_image = im.make_image(fig.canvas.renderer)[0][0]
    # expand the input to be 190 long and run through norm / cmap
    direct_computation = (
        im.cmap(im.norm((data * ([[1]] * 10)).T.ravel())) * 255
    ).astype(int)

    # check than the RBGA values are the same
    assert np.all(from_image == direct_computation)


@image_comparison(['image_placement'], extensions=['svg', 'pdf'],
                  remove_text=True, style='mpl20')
def test_image_placement():
    """
    The red box should line up exactly with the outside of the image.
    """
    fig, ax = plt.subplots()
    ax.plot([0, 0, 1, 1, 0], [0, 1, 1, 0, 0], color='r', lw=0.1)
    np.random.seed(19680801)
    ax.imshow(np.random.randn(16, 16), cmap='Blues', extent=(0, 1, 0, 1),
              interpolation='none', vmin=-1, vmax=1)
    ax.set_xlim(-0.1, 1+0.1)
    ax.set_ylim(-0.1, 1+0.1)


# A basic ndarray subclass that implements a quantity
# It does not implement an entire unit system or all quantity math.
# There is just enough implemented to test handling of ndarray
# subclasses.
class QuantityND(np.ndarray):
    def __new__(cls, input_array, units):
        obj = np.asarray(input_array).view(cls)
        obj.units = units
        return obj

    def __array_finalize__(self, obj):
        self.units = getattr(obj, "units", None)

    def __getitem__(self, item):
        units = getattr(self, "units", None)
        ret = super().__getitem__(item)
        if isinstance(ret, QuantityND) or units is not None:
            ret = QuantityND(ret, units)
        return ret

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        func = getattr(ufunc, method)
        if "out" in kwargs:
            return NotImplemented
        if len(inputs) == 1:
            i0 = inputs[0]
            unit = getattr(i0, "units", "dimensionless")
            out_arr = func(np.asarray(i0), **kwargs)
        elif len(inputs) == 2:
            i0 = inputs[0]
            i1 = inputs[1]
            u0 = getattr(i0, "units", "dimensionless")
            u1 = getattr(i1, "units", "dimensionless")
            u0 = u1 if u0 is None else u0
            u1 = u0 if u1 is None else u1
            if ufunc in [np.add, np.subtract]:
                if u0 != u1:
                    raise ValueError
                unit = u0
            elif ufunc == np.multiply:
                unit = f"{u0}*{u1}"
            elif ufunc == np.divide:
                unit = f"{u0}/({u1})"
            elif ufunc in (np.greater, np.greater_equal,
                           np.equal, np.not_equal,
                           np.less, np.less_equal):
                # Comparisons produce unitless booleans for output
                unit = None
            else:
                return NotImplemented
            out_arr = func(i0.view(np.ndarray), i1.view(np.ndarray), **kwargs)
        else:
            return NotImplemented
        if unit is None:
            out_arr = np.array(out_arr)
        else:
            out_arr = QuantityND(out_arr, unit)
        return out_arr

    @property
    def v(self):
        return self.view(np.ndarray)


def test_quantitynd():
    q = QuantityND([1, 2], "m")
    q0, q1 = q[:]
    assert np.all(q.v == np.asarray([1, 2]))
    assert q.units == "m"
    assert np.all((q0 + q1).v == np.asarray([3]))
    assert (q0 * q1).units == "m*m"
    assert (q1 / q0).units == "m/(m)"
    with pytest.raises(ValueError):
        q0 + QuantityND(1, "s")


def test_imshow_quantitynd():
    # generate a dummy ndarray subclass
    arr = QuantityND(np.ones((2, 2)), "m")
    fig, ax = plt.subplots()
    ax.imshow(arr)
    # executing the draw should not raise an exception
    fig.canvas.draw()


@check_figures_equal(extensions=['png'])
def test_norm_change(fig_test, fig_ref):
    # LogNorm should not mask anything invalid permanently.
    data = np.full((5, 5), 1, dtype=np.float64)
    data[0:2, :] = -1

    masked_data = np.ma.array(data, mask=False)
    masked_data.mask[0:2, 0:2] = True

    cmap = mpl.colormaps['viridis'].with_extremes(under='w')

    ax = fig_test.subplots()
    im = ax.imshow(data, norm=colors.LogNorm(vmin=0.5, vmax=1),
                   extent=(0, 5, 0, 5), interpolation='nearest', cmap=cmap)
    im.set_norm(colors.Normalize(vmin=-2, vmax=2))
    im = ax.imshow(masked_data, norm=colors.LogNorm(vmin=0.5, vmax=1),
                   extent=(5, 10, 5, 10), interpolation='nearest', cmap=cmap)
    im.set_norm(colors.Normalize(vmin=-2, vmax=2))
    ax.set(xlim=(0, 10), ylim=(0, 10))

    ax = fig_ref.subplots()
    ax.imshow(data, norm=colors.Normalize(vmin=-2, vmax=2),
              extent=(0, 5, 0, 5), interpolation='nearest', cmap=cmap)
    ax.imshow(masked_data, norm=colors.Normalize(vmin=-2, vmax=2),
              extent=(5, 10, 5, 10), interpolation='nearest', cmap=cmap)
    ax.set(xlim=(0, 10), ylim=(0, 10))


@pytest.mark.parametrize('x', [-1, 1])
@check_figures_equal(extensions=['png'])
def test_huge_range_log(fig_test, fig_ref, x):
    # parametrize over bad lognorm -1 values and large range 1 -> 1e20
    data = np.full((5, 5), x, dtype=np.float64)
    data[0:2, :] = 1E20

    ax = fig_test.subplots()
    ax.imshow(data, norm=colors.LogNorm(vmin=1, vmax=data.max()),
              interpolation='nearest', cmap='viridis')

    data = np.full((5, 5), x, dtype=np.float64)
    data[0:2, :] = 1000

    ax = fig_ref.subplots()
    cmap = mpl.colormaps['viridis'].with_extremes(under='w')
    ax.imshow(data, norm=colors.Normalize(vmin=1, vmax=data.max()),
              interpolation='nearest', cmap=cmap)


@check_figures_equal(extensions=['png'])
def test_spy_box(fig_test, fig_ref):
    # setting up reference and test
    ax_test = fig_test.subplots(1, 3)
    ax_ref = fig_ref.subplots(1, 3)

    plot_data = (
        [[1, 1], [1, 1]],
        [[0, 0], [0, 0]],
        [[0, 1], [1, 0]],
    )
    plot_titles = ["ones", "zeros", "mixed"]

    for i, (z, title) in enumerate(zip(plot_data, plot_titles)):
        ax_test[i].set_title(title)
        ax_test[i].spy(z)
        ax_ref[i].set_title(title)
        ax_ref[i].imshow(z, interpolation='nearest',
                            aspect='equal', origin='upper', cmap='Greys',
                            vmin=0, vmax=1)
        ax_ref[i].set_xlim(-0.5, 1.5)
        ax_ref[i].set_ylim(1.5, -0.5)
        ax_ref[i].xaxis.tick_top()
        ax_ref[i].title.set_y(1.05)
        ax_ref[i].xaxis.set_ticks_position('both')
        ax_ref[i].xaxis.set_major_locator(
            mticker.MaxNLocator(nbins=9, steps=[1, 2, 5, 10], integer=True)
        )
        ax_ref[i].yaxis.set_major_locator(
            mticker.MaxNLocator(nbins=9, steps=[1, 2, 5, 10], integer=True)
        )


@image_comparison(["nonuniform_and_pcolor.png"], style="mpl20")
def test_nonuniform_and_pcolor():
    axs = plt.figure(figsize=(3, 3)).subplots(3, sharex=True, sharey=True)
    for ax, interpolation in zip(axs, ["nearest", "bilinear"]):
        im = NonUniformImage(ax, interpolation=interpolation)
        im.set_data(np.arange(3) ** 2, np.arange(3) ** 2,
                    np.arange(9).reshape((3, 3)))
        ax.add_image(im)
    axs[2].pcolorfast(  # PcolorImage
        np.arange(4) ** 2, np.arange(4) ** 2, np.arange(9).reshape((3, 3)))
    for ax in axs:
        ax.set_axis_off()
        # NonUniformImage "leaks" out of extents, not PColorImage.
        ax.set(xlim=(0, 10))


@image_comparison(["nonuniform_logscale.png"], style="mpl20")
def test_nonuniform_logscale():
    _, axs = plt.subplots(ncols=3, nrows=1)

    for i in range(3):
        ax = axs[i]
        im = NonUniformImage(ax)
        im.set_data(np.arange(1, 4) ** 2, np.arange(1, 4) ** 2,
                    np.arange(9).reshape((3, 3)))
        ax.set_xlim(1, 16)
        ax.set_ylim(1, 16)
        ax.set_box_aspect(1)
        if i == 1:
            ax.set_xscale("log", base=2)
            ax.set_yscale("log", base=2)
        if i == 2:
            ax.set_xscale("log", base=4)
            ax.set_yscale("log", base=4)
        ax.add_image(im)


@image_comparison(['rgba_antialias.png'], style='mpl20', remove_text=True, tol=0.02)
def test_rgba_antialias():
    fig, axs = plt.subplots(2, 2, figsize=(3.5, 3.5), sharex=False,
                            sharey=False, constrained_layout=True)
    N = 250
    aa = np.ones((N, N))
    aa[::2, :] = -1

    x = np.arange(N) / N - 0.5
    y = np.arange(N) / N - 0.5

    X, Y = np.meshgrid(x, y)
    R = np.sqrt(X**2 + Y**2)
    f0 = 10
    k = 75
    # aliased concentric circles
    a = np.sin(np.pi * 2 * (f0 * R + k * R**2 / 2))

    # stripes on lhs
    a[:int(N/2), :][R[:int(N/2), :] < 0.4] = -1
    a[:int(N/2), :][R[:int(N/2), :] < 0.3] = 1
    aa[:, int(N/2):] = a[:, int(N/2):]

    # set some over/unders and NaNs
    aa[20:50, 20:50] = np.nan
    aa[70:90, 70:90] = 1e6
    aa[70:90, 20:30] = -1e6
    aa[70:90, 195:215] = 1e6
    aa[20:30, 195:215] = -1e6

    cmap = copy(plt.cm.RdBu_r)
    cmap.set_over('yellow')
    cmap.set_under('cyan')

    axs = axs.flatten()
    # zoom in
    axs[0].imshow(aa, interpolation='nearest', cmap=cmap, vmin=-1.2, vmax=1.2)
    axs[0].set_xlim([N/2-25, N/2+25])
    axs[0].set_ylim([N/2+50, N/2-10])

    # no anti-alias
    axs[1].imshow(aa, interpolation='nearest', cmap=cmap, vmin=-1.2, vmax=1.2)

    # data antialias: Note no purples, and white in circle.  Note
    # that alternating red and blue stripes become white.
    axs[2].imshow(aa, interpolation='auto', interpolation_stage='data',
                  cmap=cmap, vmin=-1.2, vmax=1.2)

    # rgba antialias: Note purples at boundary with circle.  Note that
    # alternating red and blue stripes become purple
    axs[3].imshow(aa, interpolation='auto', interpolation_stage='rgba',
                  cmap=cmap, vmin=-1.2, vmax=1.2)


@check_figures_equal(extensions=('png', ))
def test_upsample_interpolation_stage(fig_test, fig_ref):
    """
    Show that interpolation_stage='auto' gives the same as 'data'
    for upsampling.
    """
    # Fixing random state for reproducibility.  This non-standard seed
    # gives red splotches for 'rgba'.
    np.random.seed(19680801+9)

    grid = np.random.rand(4, 4)
    ax = fig_ref.subplots()
    ax.imshow(grid, interpolation='bilinear', cmap='viridis',
              interpolation_stage='data')

    ax = fig_test.subplots()
    ax.imshow(grid, interpolation='bilinear', cmap='viridis',
              interpolation_stage='auto')


@check_figures_equal(extensions=('png', ))
def test_downsample_interpolation_stage(fig_test, fig_ref):
    """
    Show that interpolation_stage='auto' gives the same as 'rgba'
    for downsampling.
    """
    # Fixing random state for reproducibility
    np.random.seed(19680801)

    grid = np.random.rand(4000, 4000)
    ax = fig_ref.subplots()
    ax.imshow(grid, interpolation='auto', cmap='viridis',
              interpolation_stage='rgba')

    ax = fig_test.subplots()
    ax.imshow(grid, interpolation='auto', cmap='viridis',
              interpolation_stage='auto')


def test_rc_interpolation_stage():
    for val in ["data", "rgba"]:
        with mpl.rc_context({"image.interpolation_stage": val}):
            assert plt.imshow([[1, 2]]).get_interpolation_stage() == val
    for val in ["DATA", "foo", None]:
        with pytest.raises(ValueError):
            mpl.rcParams["image.interpolation_stage"] = val


# We check for the warning with a draw() in the test, but we also need to
# filter the warning as it is emitted by the figure test decorator
@pytest.mark.filterwarnings(r'ignore:Data with more than .* '
                            'cannot be accurately displayed')
@pytest.mark.parametrize('origin', ['upper', 'lower'])
@pytest.mark.parametrize(
    'dim, size, msg', [['row', 2**23, r'2\*\*23 columns'],
                       ['col', 2**24, r'2\*\*24 rows']])
@check_figures_equal(extensions=('png', ))
def test_large_image(fig_test, fig_ref, dim, size, msg, origin):
    # Check that Matplotlib downsamples images that are too big for AGG
    # See issue #19276. Currently the fix only works for png output but not
    # pdf or svg output.
    ax_test = fig_test.subplots()
    ax_ref = fig_ref.subplots()

    array = np.zeros((1, size + 2))
    array[:, array.size // 2:] = 1
    if dim == 'col':
        array = array.T
    im = ax_test.imshow(array, vmin=0, vmax=1,
                        aspect='auto', extent=(0, 1, 0, 1),
                        interpolation='none',
                        origin=origin)

    with pytest.warns(UserWarning,
                      match=f'Data with more than {msg} cannot be '
                      'accurately displayed.'):
        fig_test.canvas.draw()

    array = np.zeros((1, 2))
    array[:, 1] = 1
    if dim == 'col':
        array = array.T
    im = ax_ref.imshow(array, vmin=0, vmax=1, aspect='auto',
                       extent=(0, 1, 0, 1),
                       interpolation='none',
                       origin=origin)


@check_figures_equal(extensions=["png"])
def test_str_norms(fig_test, fig_ref):
    t = np.random.rand(10, 10) * .8 + .1  # between 0 and 1
    axts = fig_test.subplots(1, 5)
    axts[0].imshow(t, norm="log")
    axts[1].imshow(t, norm="log", vmin=.2)
    axts[2].imshow(t, norm="symlog")
    axts[3].imshow(t, norm="symlog", vmin=.3, vmax=.7)
    axts[4].imshow(t, norm="logit", vmin=.3, vmax=.7)
    axrs = fig_ref.subplots(1, 5)
    axrs[0].imshow(t, norm=colors.LogNorm())
    axrs[1].imshow(t, norm=colors.LogNorm(vmin=.2))
    # same linthresh as SymmetricalLogScale's default.
    axrs[2].imshow(t, norm=colors.SymLogNorm(linthresh=2))
    axrs[3].imshow(t, norm=colors.SymLogNorm(linthresh=2, vmin=.3, vmax=.7))
    axrs[4].imshow(t, norm="logit", clim=(.3, .7))

    assert type(axts[0].images[0].norm) is colors.LogNorm  # Exactly that class
    with pytest.raises(ValueError):
        axts[0].imshow(t, norm="foobar")


def test__resample_valid_output():
    resample = functools.partial(mpl._image.resample, transform=Affine2D())
    with pytest.raises(TypeError, match="incompatible function arguments"):
        resample(np.zeros((9, 9)), None)
    with pytest.raises(ValueError, match="different dimensionalities"):
        resample(np.zeros((9, 9)), np.zeros((9, 9, 4)))
    with pytest.raises(ValueError, match="different dimensionalities"):
        resample(np.zeros((9, 9, 4)), np.zeros((9, 9)))
    with pytest.raises(ValueError, match="3D input array must be RGBA"):
        resample(np.zeros((9, 9, 3)), np.zeros((9, 9, 4)))
    with pytest.raises(ValueError, match="3D output array must be RGBA"):
        resample(np.zeros((9, 9, 4)), np.zeros((9, 9, 3)))
    with pytest.raises(ValueError, match="mismatched types"):
        resample(np.zeros((9, 9), np.uint8), np.zeros((9, 9)))
    with pytest.raises(ValueError, match="must be C-contiguous"):
        resample(np.zeros((9, 9)), np.zeros((9, 9)).T)

    out = np.zeros((9, 9))
    out.flags.writeable = False
    with pytest.raises(ValueError, match="Output array must be writeable"):
        resample(np.zeros((9, 9)), out)


def test_axesimage_get_shape():
    # generate dummy image to test get_shape method
    ax = plt.gca()
    im = AxesImage(ax)
    with pytest.raises(RuntimeError, match="You must first set the image array"):
        im.get_shape()
    z = np.arange(12, dtype=float).reshape((4, 3))
    im.set_data(z)
    assert im.get_shape() == (4, 3)
    assert im.get_size() == im.get_shape()


def test_non_transdata_image_does_not_touch_aspect():
    ax = plt.figure().add_subplot()
    im = np.arange(4).reshape((2, 2))
    ax.imshow(im, transform=ax.transAxes)
    assert ax.get_aspect() == "auto"
    ax.imshow(im, transform=Affine2D().scale(2) + ax.transData)
    assert ax.get_aspect() == 1
    ax.imshow(im, transform=ax.transAxes, aspect=2)
    assert ax.get_aspect() == 2


@image_comparison(
    ['downsampling.png'], style='mpl20', remove_text=True, tol=0.09)
def test_downsampling():
    N = 450
    x = np.arange(N) / N - 0.5
    y = np.arange(N) / N - 0.5
    aa = np.ones((N, N))
    aa[::2, :] = -1

    X, Y = np.meshgrid(x, y)
    R = np.sqrt(X**2 + Y**2)
    f0 = 5
    k = 100
    a = np.sin(np.pi * 2 * (f0 * R + k * R**2 / 2))
    # make the left hand side of this
    a[:int(N / 2), :][R[:int(N / 2), :] < 0.4] = -1
    a[:int(N / 2), :][R[:int(N / 2), :] < 0.3] = 1
    aa[:, int(N / 3):] = a[:, int(N / 3):]
    a = aa

    fig, axs = plt.subplots(2, 3, figsize=(7, 6), layout='compressed')
    axs[0, 0].imshow(a, interpolation='nearest', interpolation_stage='rgba',
                     cmap='RdBu_r')
    axs[0, 0].set_xlim(125, 175)
    axs[0, 0].set_ylim(250, 200)
    axs[0, 0].set_title('Zoom')

    for ax, interp, space in zip(axs.flat[1:], ['nearest', 'nearest', 'hanning',
                                                'hanning', 'auto'],
                                 ['data', 'rgba', 'data', 'rgba', 'auto']):
        ax.imshow(a, interpolation=interp, interpolation_stage=space,
                  cmap='RdBu_r')
        ax.set_title(f"interpolation='{interp}'\nspace='{space}'")


@image_comparison(
    ['downsampling_speckle.png'], style='mpl20', remove_text=True, tol=0.09)
def test_downsampling_speckle():
    fig, axs = plt.subplots(1, 2, figsize=(5, 2.7), sharex=True, sharey=True,
                            layout="compressed")
    axs = axs.flatten()
    img = ((np.arange(1024).reshape(-1, 1) * np.ones(720)) // 50).T

    cm = plt.get_cmap("viridis")
    cm.set_over("m")
    norm = colors.LogNorm(vmin=3, vmax=11)

    # old default cannot be tested because it creates over/under speckles
    # in the following that are machine dependent.

    axs[0].set_title("interpolation='auto', stage='rgba'")
    axs[0].imshow(np.triu(img), cmap=cm, norm=norm, interpolation_stage='rgba')

    # Should be same as previous
    axs[1].set_title("interpolation='auto', stage='auto'")
    axs[1].imshow(np.triu(img), cmap=cm, norm=norm)


@image_comparison(
    ['upsampling.png'], style='mpl20', remove_text=True)
def test_upsampling():

    np.random.seed(19680801+9)  # need this seed to get yellow next to blue
    a = np.random.rand(4, 4)

    fig, axs = plt.subplots(1, 3, figsize=(6.5, 3), layout='compressed')
    im = axs[0].imshow(a, cmap='viridis')
    axs[0].set_title(
        "interpolation='auto'\nstage='antialaised'\n(default for upsampling)")

    # probably what people want:
    axs[1].imshow(a, cmap='viridis', interpolation='sinc')
    axs[1].set_title(
        "interpolation='sinc'\nstage='auto'\n(default for upsampling)")

    # probably not what people want:
    axs[2].imshow(a, cmap='viridis', interpolation='sinc', interpolation_stage='rgba')
    axs[2].set_title("interpolation='sinc'\nstage='rgba'")
    fig.colorbar(im, ax=axs, shrink=0.7, extend='both')


@pytest.mark.parametrize(
    'dtype',
    ('float64', 'float32', 'int16', 'uint16', 'int8', 'uint8'),
)
@pytest.mark.parametrize('ndim', (2, 3))
def test_resample_dtypes(dtype, ndim):
    # Issue 28448, incorrect dtype comparisons in C++ image_resample can raise
    # ValueError: arrays must be of dtype byte, short, float32 or float64
    rng = np.random.default_rng(4181)
    shape = (2, 2) if ndim == 2 else (2, 2, 3)
    data = rng.uniform(size=shape).astype(np.dtype(dtype, copy=True))
    fig, ax = plt.subplots()
    axes_image = ax.imshow(data)
    # Before fix the following raises ValueError for some dtypes.
    axes_image.make_image(None)[0]


@pytest.mark.parametrize('intp_stage', ('data', 'rgba'))
@check_figures_equal()
def test_interpolation_stage_rgba_respects_alpha_param(fig_test, fig_ref, intp_stage):
    axs_tst = fig_test.subplots(2, 3)
    axs_ref = fig_ref.subplots(2, 3)
    ny, nx = 3, 3
    scalar_alpha = 0.5
    array_alpha = np.random.rand(ny, nx)

    # When the image does not have an alpha channel, alpha should be specified
    # by the user or default to 1.0
    im_rgb = np.random.rand(ny, nx, 3)
    im_concat_default_a = np.ones((ny, nx, 1))  # alpha defaults to 1.0
    im_rgba = np.concatenate(  # combine rgb channels with array alpha
        (im_rgb, array_alpha.reshape((ny, nx, 1))), axis=-1
    )
    axs_tst[0][0].imshow(im_rgb)
    axs_ref[0][0].imshow(np.concatenate((im_rgb, im_concat_default_a), axis=-1))
    axs_tst[0][1].imshow(im_rgb, interpolation_stage=intp_stage, alpha=scalar_alpha)
    axs_ref[0][1].imshow(
        np.concatenate(  # combine rgb channels with broadcasted scalar alpha
            (im_rgb, scalar_alpha * im_concat_default_a), axis=-1
        ), interpolation_stage=intp_stage
    )
    axs_tst[0][2].imshow(im_rgb, interpolation_stage=intp_stage, alpha=array_alpha)
    axs_ref[0][2].imshow(im_rgba, interpolation_stage=intp_stage)

    # When the image already has an alpha channel, multiply it by the
    # scalar alpha param, or replace it by the array alpha param
    axs_tst[1][0].imshow(im_rgba)
    axs_ref[1][0].imshow(im_rgb, alpha=array_alpha)
    axs_tst[1][1].imshow(im_rgba, interpolation_stage=intp_stage, alpha=scalar_alpha)
    axs_ref[1][1].imshow(
        np.concatenate(  # combine rgb channels with scaled array alpha
            (im_rgb, scalar_alpha * array_alpha.reshape((ny, nx, 1))), axis=-1
        ), interpolation_stage=intp_stage
    )
    new_array_alpha = np.random.rand(ny, nx)
    axs_tst[1][2].imshow(im_rgba, interpolation_stage=intp_stage, alpha=new_array_alpha)
    axs_ref[1][2].imshow(
        np.concatenate(  # combine rgb channels with new array alpha
            (im_rgb, new_array_alpha.reshape((ny, nx, 1))), axis=-1
        ), interpolation_stage=intp_stage
    )
