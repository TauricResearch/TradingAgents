import numpy as np
from numpy.testing import assert_array_equal, assert_allclose
import matplotlib.pyplot as plt
from matplotlib.testing.decorators import (image_comparison,
                                           remove_ticks_and_titles)
import matplotlib as mpl
import pytest
from pathlib import Path
from io import BytesIO
from PIL import Image
import base64


@image_comparison(["bivariate_cmap_shapes.png"])
def test_bivariate_cmap_shapes():
    x_0 = np.repeat(np.linspace(-0.1, 1.1, 10, dtype='float32')[None, :], 10, axis=0)
    x_1 = x_0.T

    fig, axes = plt.subplots(1, 4, figsize=(10, 2))

    # shape = 'square'
    cmap = mpl.bivar_colormaps['BiPeak']
    axes[0].imshow(cmap((x_0, x_1)), interpolation='nearest')

    # shape = 'circle'
    cmap = mpl.bivar_colormaps['BiCone']
    axes[1].imshow(cmap((x_0, x_1)), interpolation='nearest')

    # shape = 'ignore'
    cmap = mpl.bivar_colormaps['BiPeak']
    cmap = cmap.with_extremes(shape='ignore')
    axes[2].imshow(cmap((x_0, x_1)), interpolation='nearest')

    # shape = circleignore
    cmap = mpl.bivar_colormaps['BiCone']
    cmap = cmap.with_extremes(shape='circleignore')
    axes[3].imshow(cmap((x_0, x_1)), interpolation='nearest')
    remove_ticks_and_titles(fig)


def test_multivar_creation():
    # test creation of a custom multivariate colorbar
    blues = mpl.colormaps['Blues']
    cmap = mpl.colors.MultivarColormap((blues, 'Oranges'), 'sRGB_sub')
    y, x = np.mgrid[0:3, 0:3]/2
    im = cmap((y, x))
    res = np.array([[[0.96862745, 0.94509804, 0.92156863, 1],
                     [0.96004614, 0.53504037, 0.23277201, 1],
                     [0.46666667, 0.1372549, 0.01568627, 1]],
                    [[0.41708574, 0.64141484, 0.75980008, 1],
                     [0.40850442, 0.23135717, 0.07100346, 1],
                     [0, 0, 0, 1]],
                    [[0.03137255, 0.14901961, 0.34117647, 1],
                     [0.02279123, 0, 0, 1],
                     [0, 0, 0, 1]]])
    assert_allclose(im,  res, atol=0.01)

    with pytest.raises(ValueError, match="colormaps must be a list of"):
        cmap = mpl.colors.MultivarColormap((blues, [blues]), 'sRGB_sub')
    with pytest.raises(ValueError, match="A MultivarColormap must"):
        cmap = mpl.colors.MultivarColormap('blues', 'sRGB_sub')
    with pytest.raises(ValueError, match="A MultivarColormap must"):
        cmap = mpl.colors.MultivarColormap((blues), 'sRGB_sub')


@image_comparison(["multivar_alpha_mixing.png"])
def test_multivar_alpha_mixing():
    # test creation of a custom colormap using 'rainbow'
    # and a colormap that goes from alpha = 1 to alpha = 0
    rainbow = mpl.colormaps['rainbow']
    alpha = np.zeros((256, 4))
    alpha[:, 3] = np.linspace(1, 0, 256)
    alpha_cmap = mpl.colors.LinearSegmentedColormap.from_list('from_list', alpha)

    cmap = mpl.colors.MultivarColormap((rainbow, alpha_cmap), 'sRGB_add')
    y, x = np.mgrid[0:10, 0:10]/9
    im = cmap((y, x))

    fig, ax = plt.subplots()
    ax.imshow(im, interpolation='nearest')
    remove_ticks_and_titles(fig)


def test_multivar_cmap_call():
    cmap = mpl.multivar_colormaps['2VarAddA']
    assert_array_equal(cmap((0.0, 0.0)), (0, 0, 0, 1))
    assert_array_equal(cmap((1.0, 1.0)), (1, 1, 1, 1))
    assert_allclose(cmap((0.0, 0.0), alpha=0.1), (0, 0, 0, 0.1), atol=0.1)

    cmap = mpl.multivar_colormaps['2VarSubA']
    assert_array_equal(cmap((0.0, 0.0)), (1, 1, 1, 1))
    assert_allclose(cmap((1.0, 1.0)), (0, 0, 0, 1), atol=0.1)

    # check outside and bad
    cs = cmap([(0., 0., 0., 1.2, np.nan), (0., 1.2, np.nan, 0., 0., )])
    assert_allclose(cs, [[1., 1., 1., 1.],
                         [0.801, 0.426, 0.119, 1.],
                         [0., 0., 0., 0.],
                         [0.199, 0.574, 0.881, 1.],
                         [0., 0., 0., 0.]])

    assert_array_equal(cmap((0.0, 0.0), bytes=True), (255, 255, 255, 255))

    with pytest.raises(ValueError, match="alpha is array-like but its shape"):
        cs = cmap([(0, 5, 9), (0, 0, 0)], alpha=(0.5, 0.3))

    with pytest.raises(ValueError, match="For the selected colormap the data"):
        cs = cmap([(0, 5, 9), (0, 0, 0), (0, 0, 0)])

    with pytest.raises(ValueError, match="clip cannot be false"):
        cs = cmap([(0, 5, 9), (0, 0, 0)], bytes=True, clip=False)
    # Tests calling a multivariate colormap with integer values
    cmap = mpl.multivar_colormaps['2VarSubA']

    # call only integers
    cs = cmap([(0, 50, 100, 0, 0, 300), (0, 0, 0, 50, 100, 300)])
    res = np.array([[1, 1, 1, 1],
                     [0.85176471, 0.91029412, 0.96023529, 1],
                     [0.70452941, 0.82764706, 0.93358824, 1],
                     [0.94358824, 0.88505882, 0.83511765, 1],
                     [0.89729412, 0.77417647, 0.66823529, 1],
                     [0, 0, 0, 1]])
    assert_allclose(cs,  res, atol=0.01)

    # call only integers, wrong byte order
    swapped_dt = np.dtype(int).newbyteorder()
    cs = cmap([np.array([0, 50, 100, 0, 0, 300], dtype=swapped_dt),
               np.array([0, 0, 0, 50, 100, 300], dtype=swapped_dt)])
    assert_allclose(cs,  res, atol=0.01)

    # call mix floats integers
    # check calling with bytes = True
    cs = cmap([(0, 50, 100, 0, 0, 300), (0, 0, 0, 50, 100, 300)], bytes=True)
    res = np.array([[255, 255, 255, 255],
                     [217, 232, 244, 255],
                     [179, 211, 238, 255],
                     [240, 225, 212, 255],
                     [228, 197, 170, 255],
                     [0,   0,   0, 255]])
    assert_allclose(cs,  res, atol=0.01)

    cs = cmap([(0, 50, 100, 0, 0, 300), (0, 0, 0, 50, 100, 300)], alpha=0.5)
    res = np.array([[1, 1, 1, 0.5],
                     [0.85176471, 0.91029412, 0.96023529, 0.5],
                     [0.70452941, 0.82764706, 0.93358824, 0.5],
                     [0.94358824, 0.88505882, 0.83511765, 0.5],
                     [0.89729412, 0.77417647, 0.66823529, 0.5],
                     [0, 0, 0, 0.5]])
    assert_allclose(cs,  res, atol=0.01)
    # call with tuple
    assert_allclose(cmap((100, 120), bytes=True, alpha=0.5),
                    [149, 142, 136, 127], atol=0.01)

    # alpha and bytes
    cs = cmap([(0, 5, 9, 0, 0, 10), (0, 0, 0, 5, 11, 12)], bytes=True, alpha=0.5)
    res = np.array([[0, 0, 255, 127],
                    [141, 0, 255, 127],
                    [255, 0, 255, 127],
                    [0, 115, 255, 127],
                    [0, 255, 255, 127],
                    [255, 255, 255, 127]])

    # bad alpha shape
    with pytest.raises(ValueError, match="alpha is array-like but its shape"):
        cs = cmap([(0, 5, 9), (0, 0, 0)], bytes=True, alpha=(0.5, 0.3))

    cmap = cmap.with_extremes(bad=(1, 1, 1, 1))
    cs = cmap([(0., 1.1, np.nan), (0., 1.2, 1.)])
    res = np.array([[1., 1., 1., 1.],
                   [0., 0., 0., 1.],
                   [1., 1., 1., 1.]])
    assert_allclose(cs,  res, atol=0.01)

    # call outside with tuple
    assert_allclose(cmap((300, 300), bytes=True, alpha=0.5),
                    [0, 0, 0, 127], atol=0.01)
    with pytest.raises(ValueError,
                       match="For the selected colormap the data must have"):
        cs = cmap((0, 5, 9))

    # test over/under
    cmap = mpl.multivar_colormaps['2VarAddA']
    with pytest.raises(ValueError, match='i.e. be of length 2'):
        cmap.with_extremes(over=0)
    with pytest.raises(ValueError, match='i.e. be of length 2'):
        cmap.with_extremes(under=0)

    cmap = cmap.with_extremes(under=[(0, 0, 0, 0)]*2)
    assert_allclose((0, 0, 0, 0), cmap((-1., 0)), atol=1e-2)
    cmap = cmap.with_extremes(over=[(0, 0, 0, 0)]*2)
    assert_allclose((0, 0, 0, 0), cmap((2., 0)), atol=1e-2)


def test_multivar_bad_mode():
    cmap = mpl.multivar_colormaps['2VarSubA']
    with pytest.raises(ValueError, match="is not a valid value for"):
        cmap = mpl.colors.MultivarColormap(cmap[:], 'bad')


def test_multivar_resample():
    cmap = mpl.multivar_colormaps['3VarAddA']
    cmap_resampled = cmap.resampled((None, 10, 3))

    assert_allclose(cmap_resampled[1](0.25), (0.093, 0.116, 0.059, 1.0))
    assert_allclose(cmap_resampled((0, 0.25, 0)), (0.093, 0.116, 0.059, 1.0))
    assert_allclose(cmap_resampled((1, 0.25, 1)), (0.417271, 0.264624, 0.274976, 1.),
                                   atol=0.01)

    with pytest.raises(ValueError, match="lutshape must be of length"):
        cmap = cmap.resampled(4)


def test_bivar_cmap_call_tuple():
    cmap = mpl.bivar_colormaps['BiOrangeBlue']
    assert_allclose(cmap((1.0, 1.0)), (1, 1, 1, 1), atol=0.01)
    assert_allclose(cmap((0.0, 0.0)), (0, 0, 0, 1), atol=0.1)
    assert_allclose(cmap((0.0, 0.0), alpha=0.1), (0, 0, 0, 0.1), atol=0.1)


def test_bivar_cmap_call():
    """
    Tests calling a bivariate colormap with integer values
    """
    im = np.ones((10, 12, 4))
    im[:, :, 0] = np.linspace(0, 1, 10)[:, np.newaxis]
    im[:, :, 1] = np.linspace(0, 1, 12)[np.newaxis, :]
    cmap = mpl.colors.BivarColormapFromImage(im)

    # call only integers
    cs = cmap([(0, 5, 9, 0, 0, 10), (0, 0, 0, 5, 11, 12)])
    res = np.array([[0, 0, 1, 1],
                   [0.556, 0, 1, 1],
                   [1, 0, 1, 1],
                   [0, 0.454, 1, 1],
                   [0, 1, 1, 1],
                   [1, 1, 1, 1]])
    assert_allclose(cs,  res, atol=0.01)
    # call only integers, wrong byte order
    swapped_dt = np.dtype(int).newbyteorder()
    cs = cmap([np.array([0, 5, 9, 0, 0, 10], dtype=swapped_dt),
               np.array([0, 0, 0, 5, 11, 12], dtype=swapped_dt)])
    assert_allclose(cs,  res, atol=0.01)

    # call mix floats integers
    cmap = cmap.with_extremes(outside=(1, 0, 0, 0))
    cs = cmap([(0.5, 0), (0, 3)])
    res = np.array([[0.555, 0, 1, 1],
                    [0, 0.2727, 1, 1]])
    assert_allclose(cs,  res, atol=0.01)

    # check calling with bytes = True
    cs = cmap([(0, 5, 9, 0, 0, 10), (0, 0, 0, 5, 11, 12)], bytes=True)
    res = np.array([[0, 0, 255, 255],
                    [141, 0, 255, 255],
                    [255, 0, 255, 255],
                    [0, 115, 255, 255],
                    [0, 255, 255, 255],
                    [255, 255, 255, 255]])
    assert_allclose(cs,  res, atol=0.01)

    # test alpha
    cs = cmap([(0, 5, 9, 0, 0, 10), (0, 0, 0, 5, 11, 12)], alpha=0.5)
    res = np.array([[0, 0, 1, 0.5],
                    [0.556, 0, 1, 0.5],
                    [1, 0, 1, 0.5],
                    [0, 0.454, 1, 0.5],
                    [0, 1, 1, 0.5],
                    [1, 1, 1, 0.5]])
    assert_allclose(cs,  res, atol=0.01)
    # call with tuple
    assert_allclose(cmap((10, 12), bytes=True, alpha=0.5),
                    [255, 255, 255, 127], atol=0.01)

    # alpha and bytes
    cs = cmap([(0, 5, 9, 0, 0, 10), (0, 0, 0, 5, 11, 12)], bytes=True, alpha=0.5)
    res = np.array([[0, 0, 255, 127],
                    [141, 0, 255, 127],
                    [255, 0, 255, 127],
                    [0, 115, 255, 127],
                    [0, 255, 255, 127],
                    [255, 255, 255, 127]])

    # bad alpha shape
    with pytest.raises(ValueError, match="alpha is array-like but its shape"):
        cs = cmap([(0, 5, 9), (0, 0, 0)], bytes=True, alpha=(0.5, 0.3))

    # set shape to 'ignore'.
    # final point is outside colormap and should then receive
    # the 'outside' (in this case [1,0,0,0])
    # also test 'bad' (in this case [1,1,1,0])
    cmap = cmap.with_extremes(outside=(1, 0, 0, 0), bad=(1, 1, 1, 0), shape='ignore')
    cs = cmap([(0., 1.1, np.nan), (0., 1.2, 1.)])
    res = np.array([[0, 0, 1, 1],
                    [1, 0, 0, 0],
                    [1, 1, 1, 0]])
    assert_allclose(cs,  res, atol=0.01)
    # call outside with tuple
    assert_allclose(cmap((10, 12), bytes=True, alpha=0.5),
                    [255, 0, 0, 127], atol=0.01)
    # with integers
    cs = cmap([(0, 10), (0, 12)])
    res = np.array([[0, 0, 1, 1],
                    [1, 0, 0, 0]])
    assert_allclose(cs,  res, atol=0.01)

    with pytest.raises(ValueError,
                       match="For a `BivarColormap` the data must have"):
        cs = cmap((0, 5, 9))

    cmap = cmap.with_extremes(shape='circle')
    with pytest.raises(NotImplementedError,
                       match="only implemented for use with with floats"):
        cs = cmap([(0, 5, 9, 0, 0, 9), (0, 0, 0, 5, 11, 11)])

    # test origin
    cmap = mpl.bivar_colormaps['BiOrangeBlue'].with_extremes(origin=(0.5, 0.5))
    assert_allclose(cmap[0](0.5),
                    (0.50244140625, 0.5024222412109375, 0.50244140625, 1))
    assert_allclose(cmap[1](0.5),
                    (0.50244140625, 0.5024222412109375, 0.50244140625, 1))
    cmap = mpl.bivar_colormaps['BiOrangeBlue'].with_extremes(origin=(1, 1))
    assert_allclose(cmap[0](1.),
                    (0.99853515625, 0.9985467529296875, 0.99853515625, 1.0))
    assert_allclose(cmap[1](1.),
                    (0.99853515625, 0.9985467529296875, 0.99853515625, 1.0))
    with pytest.raises(KeyError,
                       match="only 0 or 1 are valid keys"):
        cs = cmap[2]


def test_bivar_getitem():
    """Test __getitem__  on BivarColormap"""
    xA = ([.0, .25, .5, .75, 1., -1, 2], [.5]*7)
    xB = ([.5]*7, [.0, .25, .5, .75, 1., -1, 2])

    cmaps = mpl.bivar_colormaps['BiPeak']
    assert_array_equal(cmaps(xA), cmaps[0](xA[0]))
    assert_array_equal(cmaps(xB), cmaps[1](xB[1]))

    cmaps = cmaps.with_extremes(shape='ignore')
    assert_array_equal(cmaps(xA), cmaps[0](xA[0]))
    assert_array_equal(cmaps(xB), cmaps[1](xB[1]))

    xA = ([.0, .25, .5, .75, 1., -1, 2], [.0]*7)
    xB = ([.0]*7, [.0, .25, .5, .75, 1., -1, 2])
    cmaps = mpl.bivar_colormaps['BiOrangeBlue']
    assert_array_equal(cmaps(xA), cmaps[0](xA[0]))
    assert_array_equal(cmaps(xB), cmaps[1](xB[1]))

    cmaps = cmaps.with_extremes(shape='ignore')
    assert_array_equal(cmaps(xA), cmaps[0](xA[0]))
    assert_array_equal(cmaps(xB), cmaps[1](xB[1]))


def test_bivar_cmap_bad_shape():
    """
    Tests calling a bivariate colormap with integer values
    """
    cmap = mpl.bivar_colormaps['BiCone']
    _ = cmap.lut
    with pytest.raises(ValueError,
                       match="is not a valid value for shape"):
        cmap.with_extremes(shape='bad_shape')

    with pytest.raises(ValueError,
                       match="is not a valid value for shape"):
        mpl.colors.BivarColormapFromImage(np.ones((3, 3, 4)),
                                          shape='bad_shape')


def test_bivar_cmap_bad_lut():
    """
    Tests calling a bivariate colormap with integer values
    """
    with pytest.raises(ValueError,
                       match="The lut must be an array of shape"):
        cmap = mpl.colors.BivarColormapFromImage(np.ones((3, 3, 5)))


def test_bivar_cmap_from_image():
    """
    This tests the creation and use of a bivariate colormap
    generated from an image
    """

    data_0 = np.arange(6).reshape((2, 3))/5
    data_1 = np.arange(6).reshape((3, 2)).T/5

    # bivariate colormap from array
    cim = np.ones((10, 12, 3))
    cim[:, :, 0] = np.arange(10)[:, np.newaxis]/10
    cim[:, :, 1] = np.arange(12)[np.newaxis, :]/12

    cmap = mpl.colors.BivarColormapFromImage(cim)
    im = cmap((data_0, data_1))
    res = np.array([[[0, 0, 1, 1],
                    [0.2, 0.33333333, 1, 1],
                    [0.4, 0.75, 1, 1]],
                   [[0.6, 0.16666667, 1, 1],
                    [0.8, 0.58333333, 1, 1],
                    [0.9, 0.91666667, 1, 1]]])
    assert_allclose(im,  res, atol=0.01)

    # input as unit8
    cim = np.ones((10, 12, 3))*255
    cim[:, :, 0] = np.arange(10)[:, np.newaxis]/10*255
    cim[:, :, 1] = np.arange(12)[np.newaxis, :]/12*255

    cmap = mpl.colors.BivarColormapFromImage(cim.astype(np.uint8))
    im = cmap((data_0, data_1))
    res = np.array([[[0, 0, 1, 1],
                    [0.2, 0.33333333, 1, 1],
                    [0.4, 0.75, 1, 1]],
                   [[0.6, 0.16666667, 1, 1],
                    [0.8, 0.58333333, 1, 1],
                    [0.9, 0.91666667, 1, 1]]])
    assert_allclose(im,  res, atol=0.01)

    # bivariate colormap from array
    png_path = Path(__file__).parent / "baseline_images/pngsuite/basn2c16.png"
    cim = Image.open(png_path)
    cim = np.asarray(cim.convert('RGBA'))

    cmap = mpl.colors.BivarColormapFromImage(cim)
    im = cmap((data_0, data_1), bytes=True)
    res = np.array([[[255, 255,   0, 255],
                     [156, 206,   0, 255],
                     [49, 156,  49, 255]],
                    [[206,  99,   0, 255],
                     [99,  49, 107, 255],
                     [0,   0, 255, 255]]])
    assert_allclose(im,  res, atol=0.01)


def test_bivar_resample():
    cmap = mpl.bivar_colormaps['BiOrangeBlue'].resampled((2, 2))
    assert_allclose(cmap((0.25, 0.25)), (0, 0, 0, 1), atol=1e-2)

    cmap = mpl.bivar_colormaps['BiOrangeBlue'].resampled((-2, 2))
    assert_allclose(cmap((0.25, 0.25)), (1., 0.5, 0., 1.), atol=1e-2)

    cmap = mpl.bivar_colormaps['BiOrangeBlue'].resampled((2, -2))
    assert_allclose(cmap((0.25, 0.25)), (0., 0.5, 1., 1.), atol=1e-2)

    cmap = mpl.bivar_colormaps['BiOrangeBlue'].resampled((-2, -2))
    assert_allclose(cmap((0.25, 0.25)), (1, 1, 1, 1), atol=1e-2)

    cmap = mpl.bivar_colormaps['BiOrangeBlue'].reversed()
    assert_allclose(cmap((0.25, 0.25)), (0.748535, 0.748547, 0.748535, 1.), atol=1e-2)
    cmap = mpl.bivar_colormaps['BiOrangeBlue'].transposed()
    assert_allclose(cmap((0.25, 0.25)), (0.252441, 0.252422, 0.252441, 1.), atol=1e-2)

    with pytest.raises(ValueError, match="lutshape must be of length"):
        cmap = cmap.resampled(4)


def test_bivariate_repr_png():
    cmap = mpl.bivar_colormaps['BiCone']
    png = cmap._repr_png_()
    assert len(png) > 0
    img = Image.open(BytesIO(png))
    assert img.width > 0
    assert img.height > 0
    assert 'Title' in img.text
    assert 'Description' in img.text
    assert 'Author' in img.text
    assert 'Software' in img.text


def test_bivariate_repr_html():
    cmap = mpl.bivar_colormaps['BiCone']
    html = cmap._repr_html_()
    assert len(html) > 0
    png = cmap._repr_png_()
    assert base64.b64encode(png).decode('ascii') in html
    assert cmap.name in html
    assert html.startswith('<div')
    assert html.endswith('</div>')


def test_multivariate_repr_png():
    cmap = mpl.multivar_colormaps['3VarAddA']
    png = cmap._repr_png_()
    assert len(png) > 0
    img = Image.open(BytesIO(png))
    assert img.width > 0
    assert img.height > 0
    assert 'Title' in img.text
    assert 'Description' in img.text
    assert 'Author' in img.text
    assert 'Software' in img.text


def test_multivariate_repr_html():
    cmap = mpl.multivar_colormaps['3VarAddA']
    html = cmap._repr_html_()
    assert len(html) > 0
    for c in cmap:
        png = c._repr_png_()
        assert base64.b64encode(png).decode('ascii') in html
    assert cmap.name in html
    assert html.startswith('<div')
    assert html.endswith('</div>')


def test_bivar_eq():
    """
    Tests equality between multivariate colormaps
    """
    cmap_0 = mpl.bivar_colormaps['BiPeak']

    cmap_1 = mpl.bivar_colormaps['BiPeak']
    assert (cmap_0 == cmap_1) is True

    cmap_1 = mpl.multivar_colormaps['2VarAddA']
    assert (cmap_0 == cmap_1) is False

    cmap_1 = mpl.bivar_colormaps['BiCone']
    assert (cmap_0 == cmap_1) is False

    cmap_1 = mpl.bivar_colormaps['BiPeak']
    cmap_1 = cmap_1.with_extremes(bad='k')
    assert (cmap_0 == cmap_1) is False

    cmap_1 = mpl.bivar_colormaps['BiPeak']
    cmap_1 = cmap_1.with_extremes(outside='k')
    assert (cmap_0 == cmap_1) is False

    cmap_1 = mpl.bivar_colormaps['BiPeak']
    cmap_1._init()
    cmap_1._lut *= 0.5
    assert (cmap_0 == cmap_1) is False

    cmap_1 = mpl.bivar_colormaps['BiPeak']
    cmap_1 = cmap_1.with_extremes(shape='ignore')
    assert (cmap_0 == cmap_1) is False


def test_multivar_eq():
    """
    Tests equality between multivariate colormaps
    """
    cmap_0 = mpl.multivar_colormaps['2VarAddA']

    cmap_1 = mpl.multivar_colormaps['2VarAddA']
    assert (cmap_0 == cmap_1) is True

    cmap_1 = mpl.bivar_colormaps['BiPeak']
    assert (cmap_0 == cmap_1) is False

    cmap_1 = mpl.colors.MultivarColormap([cmap_0[0]]*2,
                                         'sRGB_add')
    assert (cmap_0 == cmap_1) is False

    cmap_1 = mpl.multivar_colormaps['3VarAddA']
    assert (cmap_0 == cmap_1) is False

    cmap_1 = mpl.multivar_colormaps['2VarAddA']
    cmap_1 = cmap_1.with_extremes(bad='k')
    assert (cmap_0 == cmap_1) is False

    cmap_1 = mpl.multivar_colormaps['2VarAddA']
    cmap_1 = mpl.colors.MultivarColormap(cmap_1[:], 'sRGB_sub')
    assert (cmap_0 == cmap_1) is False
