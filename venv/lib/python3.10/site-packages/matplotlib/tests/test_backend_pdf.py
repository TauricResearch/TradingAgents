import datetime
import decimal
import io
import os
from pathlib import Path

import numpy as np
import pytest

import matplotlib as mpl
from matplotlib import (
    pyplot as plt, rcParams, font_manager as fm
)
from matplotlib.cbook import _get_data_path
from matplotlib.ft2font import FT2Font
from matplotlib.font_manager import findfont, FontProperties
from matplotlib.backends._backend_pdf_ps import get_glyphs_subset, font_as_file
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle
from matplotlib.testing.decorators import check_figures_equal, image_comparison
from matplotlib.testing._markers import needs_usetex


@image_comparison(['pdf_use14corefonts.pdf'])
def test_use14corefonts():
    rcParams['pdf.use14corefonts'] = True
    rcParams['font.family'] = 'sans-serif'
    rcParams['font.size'] = 8
    rcParams['font.sans-serif'] = ['Helvetica']
    rcParams['pdf.compression'] = 0

    text = '''A three-line text positioned just above a blue line
and containing some French characters and the euro symbol:
"Merci pépé pour les 10 €"'''

    fig, ax = plt.subplots()
    ax.set_title('Test PDF backend with option use14corefonts=True')
    ax.text(0.5, 0.5, text, horizontalalignment='center',
            verticalalignment='bottom',
            fontsize=14)
    ax.axhline(0.5, linewidth=0.5)


@pytest.mark.parametrize('fontname, fontfile', [
    ('DejaVu Sans', 'DejaVuSans.ttf'),
    ('WenQuanYi Zen Hei', 'wqy-zenhei.ttc'),
])
@pytest.mark.parametrize('fonttype', [3, 42])
def test_embed_fonts(fontname, fontfile, fonttype):
    if Path(findfont(FontProperties(family=[fontname]))).name != fontfile:
        pytest.skip(f'Font {fontname!r} may be missing')

    rcParams['pdf.fonttype'] = fonttype
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3])
    ax.set_title('Axes Title', font=fontname)
    fig.savefig(io.BytesIO(), format='pdf')


def test_multipage_pagecount():
    with PdfPages(io.BytesIO()) as pdf:
        assert pdf.get_pagecount() == 0
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3])
        fig.savefig(pdf, format="pdf")
        assert pdf.get_pagecount() == 1
        pdf.savefig()
        assert pdf.get_pagecount() == 2


def test_multipage_properfinalize():
    pdfio = io.BytesIO()
    with PdfPages(pdfio) as pdf:
        for i in range(10):
            fig, ax = plt.subplots()
            ax.set_title('This is a long title')
            fig.savefig(pdf, format="pdf")
    s = pdfio.getvalue()
    assert s.count(b'startxref') == 1
    assert len(s) < 40000


def test_multipage_keep_empty(tmp_path):
    # An empty pdf deletes itself afterwards.
    fn = tmp_path / "a.pdf"
    with PdfPages(fn) as pdf:
        pass
    assert not fn.exists()

    # Test pdf files with content, they should never be deleted.
    fn = tmp_path / "b.pdf"
    with PdfPages(fn) as pdf:
        pdf.savefig(plt.figure())
    assert fn.exists()


def test_composite_image():
    # Test that figures can be saved with and without combining multiple images
    # (on a single set of axes) into a single composite image.
    X, Y = np.meshgrid(np.arange(-5, 5, 1), np.arange(-5, 5, 1))
    Z = np.sin(Y ** 2)
    fig, ax = plt.subplots()
    ax.set_xlim(0, 3)
    ax.imshow(Z, extent=[0, 1, 0, 1])
    ax.imshow(Z[::-1], extent=[2, 3, 0, 1])
    plt.rcParams['image.composite_image'] = True
    with PdfPages(io.BytesIO()) as pdf:
        fig.savefig(pdf, format="pdf")
        assert len(pdf._file._images) == 1
    plt.rcParams['image.composite_image'] = False
    with PdfPages(io.BytesIO()) as pdf:
        fig.savefig(pdf, format="pdf")
        assert len(pdf._file._images) == 2


def test_indexed_image():
    # An image with low color count should compress to a palette-indexed format.
    pikepdf = pytest.importorskip('pikepdf')

    data = np.zeros((256, 1, 3), dtype=np.uint8)
    data[:, 0, 0] = np.arange(256)  # Maximum unique colours for an indexed image.

    rcParams['pdf.compression'] = True
    fig = plt.figure()
    fig.figimage(data, resize=True)
    buf = io.BytesIO()
    fig.savefig(buf, format='pdf', dpi='figure')

    with pikepdf.Pdf.open(buf) as pdf:
        page, = pdf.pages
        image, = page.images.values()
        pdf_image = pikepdf.PdfImage(image)
        assert pdf_image.indexed
        pil_image = pdf_image.as_pil_image()
        rgb = np.asarray(pil_image.convert('RGB'))

    np.testing.assert_array_equal(data, rgb)


def test_savefig_metadata(monkeypatch):
    pikepdf = pytest.importorskip('pikepdf')
    monkeypatch.setenv('SOURCE_DATE_EPOCH', '0')

    fig, ax = plt.subplots()
    ax.plot(range(5))

    md = {
        'Author': 'me',
        'Title': 'Multipage PDF',
        'Subject': 'Test page',
        'Keywords': 'test,pdf,multipage',
        'ModDate': datetime.datetime(
            1968, 8, 1, tzinfo=datetime.timezone(datetime.timedelta(0))),
        'Trapped': 'True'
    }
    buf = io.BytesIO()
    fig.savefig(buf, metadata=md, format='pdf')

    with pikepdf.Pdf.open(buf) as pdf:
        info = {k: str(v) for k, v in pdf.docinfo.items()}

    assert info == {
        '/Author': 'me',
        '/CreationDate': 'D:19700101000000Z',
        '/Creator': f'Matplotlib v{mpl.__version__}, https://matplotlib.org',
        '/Keywords': 'test,pdf,multipage',
        '/ModDate': 'D:19680801000000Z',
        '/Producer': f'Matplotlib pdf backend v{mpl.__version__}',
        '/Subject': 'Test page',
        '/Title': 'Multipage PDF',
        '/Trapped': '/True',
    }


def test_invalid_metadata():
    fig, ax = plt.subplots()

    with pytest.warns(UserWarning,
                      match="Unknown infodict keyword: 'foobar'."):
        fig.savefig(io.BytesIO(), format='pdf', metadata={'foobar': 'invalid'})

    with pytest.warns(UserWarning,
                      match='not an instance of datetime.datetime.'):
        fig.savefig(io.BytesIO(), format='pdf',
                    metadata={'ModDate': '1968-08-01'})

    with pytest.warns(UserWarning,
                      match='not one of {"True", "False", "Unknown"}'):
        fig.savefig(io.BytesIO(), format='pdf', metadata={'Trapped': 'foo'})

    with pytest.warns(UserWarning, match='not an instance of str.'):
        fig.savefig(io.BytesIO(), format='pdf', metadata={'Title': 1234})


def test_multipage_metadata(monkeypatch):
    pikepdf = pytest.importorskip('pikepdf')
    monkeypatch.setenv('SOURCE_DATE_EPOCH', '0')

    fig, ax = plt.subplots()
    ax.plot(range(5))

    md = {
        'Author': 'me',
        'Title': 'Multipage PDF',
        'Subject': 'Test page',
        'Keywords': 'test,pdf,multipage',
        'ModDate': datetime.datetime(
            1968, 8, 1, tzinfo=datetime.timezone(datetime.timedelta(0))),
        'Trapped': 'True'
    }
    buf = io.BytesIO()
    with PdfPages(buf, metadata=md) as pdf:
        pdf.savefig(fig)
        pdf.savefig(fig)

    with pikepdf.Pdf.open(buf) as pdf:
        info = {k: str(v) for k, v in pdf.docinfo.items()}

    assert info == {
        '/Author': 'me',
        '/CreationDate': 'D:19700101000000Z',
        '/Creator': f'Matplotlib v{mpl.__version__}, https://matplotlib.org',
        '/Keywords': 'test,pdf,multipage',
        '/ModDate': 'D:19680801000000Z',
        '/Producer': f'Matplotlib pdf backend v{mpl.__version__}',
        '/Subject': 'Test page',
        '/Title': 'Multipage PDF',
        '/Trapped': '/True',
    }


def test_text_urls():
    pikepdf = pytest.importorskip('pikepdf')

    test_url = 'https://test_text_urls.matplotlib.org/'

    fig = plt.figure(figsize=(2, 1))
    fig.text(0.1, 0.1, 'test plain 123', url=f'{test_url}plain')
    fig.text(0.1, 0.4, 'test mathtext $123$', url=f'{test_url}mathtext')

    with io.BytesIO() as fd:
        fig.savefig(fd, format='pdf')

        with pikepdf.Pdf.open(fd) as pdf:
            annots = pdf.pages[0].Annots

            # Iteration over Annots must occur within the context manager,
            # otherwise it may fail depending on the pdf structure.
            for y, fragment in [('0.1', 'plain'), ('0.4', 'mathtext')]:
                annot = next(
                    (a for a in annots if a.A.URI == f'{test_url}{fragment}'),
                    None)
                assert annot is not None
                assert getattr(annot, 'QuadPoints', None) is None
                # Positions in points (72 per inch.)
                assert annot.Rect[1] == decimal.Decimal(y) * 72


def test_text_rotated_urls():
    pikepdf = pytest.importorskip('pikepdf')

    test_url = 'https://test_text_urls.matplotlib.org/'

    fig = plt.figure(figsize=(1, 1))
    fig.text(0.1, 0.1, 'N', rotation=45, url=f'{test_url}')

    with io.BytesIO() as fd:
        fig.savefig(fd, format='pdf')

        with pikepdf.Pdf.open(fd) as pdf:
            annots = pdf.pages[0].Annots

            # Iteration over Annots must occur within the context manager,
            # otherwise it may fail depending on the pdf structure.
            annot = next(
                (a for a in annots if a.A.URI == f'{test_url}'),
                None)
            assert annot is not None
            assert getattr(annot, 'QuadPoints', None) is not None
            # Positions in points (72 per inch)
            assert annot.Rect[0] == \
               annot.QuadPoints[6] - decimal.Decimal('0.00001')


@needs_usetex
def test_text_urls_tex():
    pikepdf = pytest.importorskip('pikepdf')

    test_url = 'https://test_text_urls.matplotlib.org/'

    fig = plt.figure(figsize=(2, 1))
    fig.text(0.1, 0.7, 'test tex $123$', usetex=True, url=f'{test_url}tex')

    with io.BytesIO() as fd:
        fig.savefig(fd, format='pdf')

        with pikepdf.Pdf.open(fd) as pdf:
            annots = pdf.pages[0].Annots

            # Iteration over Annots must occur within the context manager,
            # otherwise it may fail depending on the pdf structure.
            annot = next(
                (a for a in annots if a.A.URI == f'{test_url}tex'),
                None)
            assert annot is not None
            # Positions in points (72 per inch.)
            assert annot.Rect[1] == decimal.Decimal('0.7') * 72


def test_pdfpages_fspath():
    with PdfPages(Path(os.devnull)) as pdf:
        pdf.savefig(plt.figure())


@image_comparison(['hatching_legend.pdf'])
def test_hatching_legend():
    """Test for correct hatching on patches in legend"""
    fig = plt.figure(figsize=(1, 2))

    a = Rectangle([0, 0], 0, 0, facecolor="green", hatch="XXXX")
    b = Rectangle([0, 0], 0, 0, facecolor="blue", hatch="XXXX")

    fig.legend([a, b, a, b], ["", "", "", ""])


@image_comparison(['grayscale_alpha.pdf'])
def test_grayscale_alpha():
    """Masking images with NaN did not work for grayscale images"""
    x, y = np.ogrid[-2:2:.1, -2:2:.1]
    dd = np.exp(-(x**2 + y**2))
    dd[dd < .1] = np.nan
    fig, ax = plt.subplots()
    ax.imshow(dd, interpolation='none', cmap='gray_r')
    ax.set_xticks([])
    ax.set_yticks([])


@mpl.style.context('default')
@check_figures_equal(extensions=["pdf", "eps"])
def test_pdf_eps_savefig_when_color_is_none(fig_test, fig_ref):
    ax_test = fig_test.add_subplot()
    ax_test.set_axis_off()
    ax_test.plot(np.sin(np.linspace(-5, 5, 100)), "v", c="none")
    ax_ref = fig_ref.add_subplot()
    ax_ref.set_axis_off()


@needs_usetex
def test_failing_latex():
    """Test failing latex subprocess call"""
    plt.xlabel("$22_2_2$", usetex=True)  # This fails with "Double subscript"
    with pytest.raises(RuntimeError):
        plt.savefig(io.BytesIO(), format="pdf")


def test_empty_rasterized():
    # Check that empty figures that are rasterised save to pdf files fine
    fig, ax = plt.subplots()
    ax.plot([], [], rasterized=True)
    fig.savefig(io.BytesIO(), format="pdf")


@image_comparison(['kerning.pdf'])
def test_kerning():
    fig = plt.figure()
    s = "AVAVAVAVAVAVAVAV€AAVV"
    fig.text(0, .25, s, size=5)
    fig.text(0, .75, s, size=20)


def test_glyphs_subset():
    fpath = str(_get_data_path("fonts/ttf/DejaVuSerif.ttf"))
    chars = "these should be subsetted! 1234567890"

    # non-subsetted FT2Font
    nosubfont = FT2Font(fpath)
    nosubfont.set_text(chars)

    # subsetted FT2Font
    with get_glyphs_subset(fpath, chars) as subset:
        subfont = FT2Font(font_as_file(subset))
    subfont.set_text(chars)

    nosubcmap = nosubfont.get_charmap()
    subcmap = subfont.get_charmap()

    # all unique chars must be available in subsetted font
    assert {*chars} == {chr(key) for key in subcmap}

    # subsetted font's charmap should have less entries
    assert len(subcmap) < len(nosubcmap)

    # since both objects are assigned same characters
    assert subfont.get_num_glyphs() == nosubfont.get_num_glyphs()


@image_comparison(["multi_font_type3.pdf"], tol=4.6)
def test_multi_font_type3():
    fp = fm.FontProperties(family=["WenQuanYi Zen Hei"])
    if Path(fm.findfont(fp)).name != "wqy-zenhei.ttc":
        pytest.skip("Font may be missing")

    plt.rc('font', family=['DejaVu Sans', 'WenQuanYi Zen Hei'], size=27)
    plt.rc('pdf', fonttype=3)

    fig = plt.figure()
    fig.text(0.15, 0.475, "There are 几个汉字 in between!")


@image_comparison(["multi_font_type42.pdf"], tol=2.2)
def test_multi_font_type42():
    fp = fm.FontProperties(family=["WenQuanYi Zen Hei"])
    if Path(fm.findfont(fp)).name != "wqy-zenhei.ttc":
        pytest.skip("Font may be missing")

    plt.rc('font', family=['DejaVu Sans', 'WenQuanYi Zen Hei'], size=27)
    plt.rc('pdf', fonttype=42)

    fig = plt.figure()
    fig.text(0.15, 0.475, "There are 几个汉字 in between!")


@pytest.mark.parametrize('family_name, file_name',
                         [("Noto Sans", "NotoSans-Regular.otf"),
                          ("FreeMono", "FreeMono.otf")])
def test_otf_font_smoke(family_name, file_name):
    # checks that there's no segfault
    fp = fm.FontProperties(family=[family_name])
    if Path(fm.findfont(fp)).name != file_name:
        pytest.skip(f"Font {family_name} may be missing")

    plt.rc('font', family=[family_name], size=27)

    fig = plt.figure()
    fig.text(0.15, 0.475, "Привет мир!")
    fig.savefig(io.BytesIO(), format="pdf")


@image_comparison(["truetype-conversion.pdf"])
# mpltest.ttf does not have "l"/"p" glyphs so we get a warning when trying to
# get the font extents.
def test_truetype_conversion(recwarn):
    mpl.rcParams['pdf.fonttype'] = 3
    fig, ax = plt.subplots()
    ax.text(0, 0, "ABCDE",
            font=Path(__file__).with_name("mpltest.ttf"), fontsize=80)
    ax.set_xticks([])
    ax.set_yticks([])
