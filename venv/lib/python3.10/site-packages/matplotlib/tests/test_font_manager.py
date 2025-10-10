from io import BytesIO, StringIO
import gc
import multiprocessing
import os
from pathlib import Path
from PIL import Image
import shutil
import sys
import warnings

import numpy as np
import pytest

import matplotlib as mpl
from matplotlib.font_manager import (
    findfont, findSystemFonts, FontEntry, FontProperties, fontManager,
    json_dump, json_load, get_font, is_opentype_cff_font,
    MSUserFontDirectories, _get_fontconfig_fonts, ttfFontProperty)
from matplotlib import cbook, ft2font, pyplot as plt, rc_context, figure as mfigure
from matplotlib.testing import subprocess_run_helper, subprocess_run_for_testing


has_fclist = shutil.which('fc-list') is not None


def test_font_priority():
    with rc_context(rc={
            'font.sans-serif':
            ['cmmi10', 'Bitstream Vera Sans']}):
        fontfile = findfont(FontProperties(family=["sans-serif"]))
    assert Path(fontfile).name == 'cmmi10.ttf'

    # Smoketest get_charmap, which isn't used internally anymore
    font = get_font(fontfile)
    cmap = font.get_charmap()
    assert len(cmap) == 131
    assert cmap[8729] == 30


def test_score_weight():
    assert 0 == fontManager.score_weight("regular", "regular")
    assert 0 == fontManager.score_weight("bold", "bold")
    assert (0 < fontManager.score_weight(400, 400) <
            fontManager.score_weight("normal", "bold"))
    assert (0 < fontManager.score_weight("normal", "regular") <
            fontManager.score_weight("normal", "bold"))
    assert (fontManager.score_weight("normal", "regular") ==
            fontManager.score_weight(400, 400))


def test_json_serialization(tmp_path):
    # Can't open a NamedTemporaryFile twice on Windows, so use a temporary
    # directory instead.
    json_dump(fontManager, tmp_path / "fontlist.json")
    copy = json_load(tmp_path / "fontlist.json")
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', 'findfont: Font family.*not found')
        for prop in ({'family': 'STIXGeneral'},
                     {'family': 'Bitstream Vera Sans', 'weight': 700},
                     {'family': 'no such font family'}):
            fp = FontProperties(**prop)
            assert (fontManager.findfont(fp, rebuild_if_missing=False) ==
                    copy.findfont(fp, rebuild_if_missing=False))


def test_otf():
    fname = '/usr/share/fonts/opentype/freefont/FreeMono.otf'
    if Path(fname).exists():
        assert is_opentype_cff_font(fname)
    for f in fontManager.ttflist:
        if 'otf' in f.fname:
            with open(f.fname, 'rb') as fd:
                res = fd.read(4) == b'OTTO'
            assert res == is_opentype_cff_font(f.fname)


@pytest.mark.skipif(sys.platform == "win32" or not has_fclist,
                    reason='no fontconfig installed')
def test_get_fontconfig_fonts():
    assert len(_get_fontconfig_fonts()) > 1


@pytest.mark.parametrize('factor', [2, 4, 6, 8])
def test_hinting_factor(factor):
    font = findfont(FontProperties(family=["sans-serif"]))

    font1 = get_font(font, hinting_factor=1)
    font1.clear()
    font1.set_size(12, 100)
    font1.set_text('abc')
    expected = font1.get_width_height()

    hinted_font = get_font(font, hinting_factor=factor)
    hinted_font.clear()
    hinted_font.set_size(12, 100)
    hinted_font.set_text('abc')
    # Check that hinting only changes text layout by a small (10%) amount.
    np.testing.assert_allclose(hinted_font.get_width_height(), expected,
                               rtol=0.1)


def test_utf16m_sfnt():
    try:
        # seguisbi = Microsoft Segoe UI Semibold
        entry = next(entry for entry in fontManager.ttflist
                     if Path(entry.fname).name == "seguisbi.ttf")
    except StopIteration:
        pytest.skip("Couldn't find seguisbi.ttf font to test against.")
    else:
        # Check that we successfully read "semibold" from the font's sfnt table
        # and set its weight accordingly.
        assert entry.weight == 600


def test_find_ttc():
    fp = FontProperties(family=["WenQuanYi Zen Hei"])
    if Path(findfont(fp)).name != "wqy-zenhei.ttc":
        pytest.skip("Font wqy-zenhei.ttc may be missing")
    fig, ax = plt.subplots()
    ax.text(.5, .5, "\N{KANGXI RADICAL DRAGON}", fontproperties=fp)
    for fmt in ["raw", "svg", "pdf", "ps"]:
        fig.savefig(BytesIO(), format=fmt)


def test_find_noto():
    fp = FontProperties(family=["Noto Sans CJK SC", "Noto Sans CJK JP"])
    name = Path(findfont(fp)).name
    if name not in ("NotoSansCJKsc-Regular.otf", "NotoSansCJK-Regular.ttc"):
        pytest.skip(f"Noto Sans CJK SC font may be missing (found {name})")

    fig, ax = plt.subplots()
    ax.text(0.5, 0.5, 'Hello, 你好', fontproperties=fp)
    for fmt in ["raw", "svg", "pdf", "ps"]:
        fig.savefig(BytesIO(), format=fmt)


def test_find_invalid(tmp_path):

    with pytest.raises(FileNotFoundError):
        get_font(tmp_path / 'non-existent-font-name.ttf')

    with pytest.raises(FileNotFoundError):
        get_font(str(tmp_path / 'non-existent-font-name.ttf'))

    with pytest.raises(FileNotFoundError):
        get_font(bytes(tmp_path / 'non-existent-font-name.ttf'))

    # Not really public, but get_font doesn't expose non-filename constructor.
    from matplotlib.ft2font import FT2Font
    with pytest.raises(TypeError, match='font file or a binary-mode file'):
        FT2Font(StringIO())  # type: ignore[arg-type]


@pytest.mark.skipif(sys.platform != 'linux' or not has_fclist,
                    reason='only Linux with fontconfig installed')
def test_user_fonts_linux(tmpdir, monkeypatch):
    font_test_file = 'mpltest.ttf'

    # Precondition: the test font should not be available
    fonts = findSystemFonts()
    if any(font_test_file in font for font in fonts):
        pytest.skip(f'{font_test_file} already exists in system fonts')

    # Prepare a temporary user font directory
    user_fonts_dir = tmpdir.join('fonts')
    user_fonts_dir.ensure(dir=True)
    shutil.copyfile(Path(__file__).parent / font_test_file,
                    user_fonts_dir.join(font_test_file))

    with monkeypatch.context() as m:
        m.setenv('XDG_DATA_HOME', str(tmpdir))
        _get_fontconfig_fonts.cache_clear()
        # Now, the font should be available
        fonts = findSystemFonts()
        assert any(font_test_file in font for font in fonts)

    # Make sure the temporary directory is no longer cached.
    _get_fontconfig_fonts.cache_clear()


def test_addfont_as_path():
    """Smoke test that addfont() accepts pathlib.Path."""
    font_test_file = 'mpltest.ttf'
    path = Path(__file__).parent / font_test_file
    try:
        fontManager.addfont(path)
        added, = (font for font in fontManager.ttflist
                  if font.fname.endswith(font_test_file))
        fontManager.ttflist.remove(added)
    finally:
        to_remove = [font for font in fontManager.ttflist
                     if font.fname.endswith(font_test_file)]
        for font in to_remove:
            fontManager.ttflist.remove(font)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows only')
def test_user_fonts_win32():
    if not (os.environ.get('APPVEYOR') or os.environ.get('TF_BUILD')):
        pytest.xfail("This test should only run on CI (appveyor or azure) "
                     "as the developer's font directory should remain "
                     "unchanged.")
    pytest.xfail("We need to update the registry for this test to work")
    font_test_file = 'mpltest.ttf'

    # Precondition: the test font should not be available
    fonts = findSystemFonts()
    if any(font_test_file in font for font in fonts):
        pytest.skip(f'{font_test_file} already exists in system fonts')

    user_fonts_dir = MSUserFontDirectories[0]

    # Make sure that the user font directory exists (this is probably not the
    # case on Windows versions < 1809)
    os.makedirs(user_fonts_dir)

    # Copy the test font to the user font directory
    shutil.copy(Path(__file__).parent / font_test_file, user_fonts_dir)

    # Now, the font should be available
    fonts = findSystemFonts()
    assert any(font_test_file in font for font in fonts)


def _model_handler(_):
    fig, ax = plt.subplots()
    fig.savefig(BytesIO(), format="pdf")
    plt.close()


@pytest.mark.skipif(not hasattr(os, "register_at_fork"),
                    reason="Cannot register at_fork handlers")
def test_fork():
    _model_handler(0)  # Make sure the font cache is filled.
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(processes=2) as pool:
        pool.map(_model_handler, range(2))


def test_missing_family(caplog):
    plt.rcParams["font.sans-serif"] = ["this-font-does-not-exist"]
    with caplog.at_level("WARNING"):
        findfont("sans")
    assert [rec.getMessage() for rec in caplog.records] == [
        "findfont: Font family ['sans'] not found. "
        "Falling back to DejaVu Sans.",
        "findfont: Generic family 'sans' not found because none of the "
        "following families were found: this-font-does-not-exist",
    ]


def _test_threading():
    import threading
    from matplotlib.ft2font import LoadFlags
    import matplotlib.font_manager as fm

    def loud_excepthook(args):
        raise RuntimeError("error in thread!")

    threading.excepthook = loud_excepthook

    N = 10
    b = threading.Barrier(N)

    def bad_idea(n):
        b.wait(timeout=5)
        for j in range(100):
            font = fm.get_font(fm.findfont("DejaVu Sans"))
            font.set_text(str(n), 0.0, flags=LoadFlags.NO_HINTING)

    threads = [
        threading.Thread(target=bad_idea, name=f"bad_thread_{j}", args=(j,))
        for j in range(N)
    ]

    for t in threads:
        t.start()

    for t in threads:
        t.join(timeout=9)
        if t.is_alive():
            raise RuntimeError("thread failed to join")


def test_fontcache_thread_safe():
    pytest.importorskip('threading')

    subprocess_run_helper(_test_threading, timeout=10)


def test_lockfilefailure(tmp_path):
    # The logic here:
    # 1. get a temp directory from pytest
    # 2. import matplotlib which makes sure it exists
    # 3. get the cache dir (where we check it is writable)
    # 4. make it not writable
    # 5. try to write into it via font manager
    proc = subprocess_run_for_testing(
        [
            sys.executable,
            "-c",
            "import matplotlib;"
            "import os;"
            "p = matplotlib.get_cachedir();"
            "os.chmod(p, 0o555);"
            "import matplotlib.font_manager;"
        ],
        env={**os.environ, 'MPLCONFIGDIR': str(tmp_path)},
        check=True
    )


def test_fontentry_dataclass():
    fontent = FontEntry(name='font-name')

    png = fontent._repr_png_()
    img = Image.open(BytesIO(png))
    assert img.width > 0
    assert img.height > 0

    html = fontent._repr_html_()
    assert html.startswith("<img src=\"data:image/png;base64")


def test_fontentry_dataclass_invalid_path():
    with pytest.raises(FileNotFoundError):
        fontent = FontEntry(fname='/random', name='font-name')
        fontent._repr_html_()


@pytest.mark.skipif(sys.platform == 'win32', reason='Linux or OS only')
def test_get_font_names():
    paths_mpl = [cbook._get_data_path('fonts', subdir) for subdir in ['ttf']]
    fonts_mpl = findSystemFonts(paths_mpl, fontext='ttf')
    fonts_system = findSystemFonts(fontext='ttf')
    ttf_fonts = []
    for path in fonts_mpl + fonts_system:
        try:
            font = ft2font.FT2Font(path)
            prop = ttfFontProperty(font)
            ttf_fonts.append(prop.name)
        except Exception:
            pass
    available_fonts = sorted(list(set(ttf_fonts)))
    mpl_font_names = sorted(fontManager.get_font_names())
    assert set(available_fonts) == set(mpl_font_names)
    assert len(available_fonts) == len(mpl_font_names)
    assert available_fonts == mpl_font_names


def test_donot_cache_tracebacks():

    class SomeObject:
        pass

    def inner():
        x = SomeObject()
        fig = mfigure.Figure()
        ax = fig.subplots()
        fig.text(.5, .5, 'aardvark', family='doesnotexist')
        with BytesIO() as out:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore')
                fig.savefig(out, format='raw')

    inner()

    for obj in gc.get_objects():
        if isinstance(obj, SomeObject):
            pytest.fail("object from inner stack still alive")


def test_fontproperties_init_deprecation():
    """
    Test the deprecated API of FontProperties.__init__.

    The deprecation does not change behavior, it only adds a deprecation warning
    via a decorator. Therefore, the purpose of this test is limited to check
    which calls do and do not issue deprecation warnings. Behavior is still
    tested via the existing regular tests.
    """
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        # multiple positional arguments
        FontProperties("Times", "italic")

    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        # Mixed positional and keyword arguments
        FontProperties("Times", size=10)

    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        # passing a family list positionally
        FontProperties(["Times"])

    # still accepted:
    FontProperties(family="Times", style="italic")
    FontProperties(family="Times")
    FontProperties("Times")  # works as pattern and family
    FontProperties("serif-24:style=oblique:weight=bold")  # pattern

    # also still accepted:
    # passing as pattern via family kwarg was not covered by the docs but
    # historically worked. This is left unchanged for now.
    # AFAICT, we cannot detect this: We can determine whether a string
    # works as pattern, but that doesn't help, because there are strings
    # that are both pattern and family. We would need to identify, whether
    # a string is *not* a valid family.
    # Since this case is not covered by docs, I've refrained from jumping
    # extra hoops to detect this possible API misuse.
    FontProperties(family="serif-24:style=oblique:weight=bold")
