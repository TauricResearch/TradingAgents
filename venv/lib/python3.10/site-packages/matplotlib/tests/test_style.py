from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

import numpy as np
import pytest

import matplotlib as mpl
from matplotlib import pyplot as plt, style
from matplotlib.style.core import USER_LIBRARY_PATHS, STYLE_EXTENSION


PARAM = 'image.cmap'
VALUE = 'pink'
DUMMY_SETTINGS = {PARAM: VALUE}


@contextmanager
def temp_style(style_name, settings=None):
    """Context manager to create a style sheet in a temporary directory."""
    if not settings:
        settings = DUMMY_SETTINGS
    temp_file = f'{style_name}.{STYLE_EXTENSION}'
    try:
        with TemporaryDirectory() as tmpdir:
            # Write style settings to file in the tmpdir.
            Path(tmpdir, temp_file).write_text(
                "\n".join(f"{k}: {v}" for k, v in settings.items()),
                encoding="utf-8")
            # Add tmpdir to style path and reload so we can access this style.
            USER_LIBRARY_PATHS.append(tmpdir)
            style.reload_library()
            yield
    finally:
        style.reload_library()


def test_invalid_rc_warning_includes_filename(caplog):
    SETTINGS = {'foo': 'bar'}
    basename = 'basename'
    with temp_style(basename, SETTINGS):
        # style.reload_library() in temp_style() triggers the warning
        pass
    assert (len(caplog.records) == 1
            and basename in caplog.records[0].getMessage())


def test_available():
    with temp_style('_test_', DUMMY_SETTINGS):
        assert '_test_' in style.available


def test_use():
    mpl.rcParams[PARAM] = 'gray'
    with temp_style('test', DUMMY_SETTINGS):
        with style.context('test'):
            assert mpl.rcParams[PARAM] == VALUE


def test_use_url(tmp_path):
    path = tmp_path / 'file'
    path.write_text('axes.facecolor: adeade', encoding='utf-8')
    with temp_style('test', DUMMY_SETTINGS):
        url = ('file:'
               + ('///' if sys.platform == 'win32' else '')
               + path.resolve().as_posix())
        with style.context(url):
            assert mpl.rcParams['axes.facecolor'] == "#adeade"


def test_single_path(tmp_path):
    mpl.rcParams[PARAM] = 'gray'
    path = tmp_path / f'text.{STYLE_EXTENSION}'
    path.write_text(f'{PARAM} : {VALUE}', encoding='utf-8')
    with style.context(path):
        assert mpl.rcParams[PARAM] == VALUE
    assert mpl.rcParams[PARAM] == 'gray'


def test_context():
    mpl.rcParams[PARAM] = 'gray'
    with temp_style('test', DUMMY_SETTINGS):
        with style.context('test'):
            assert mpl.rcParams[PARAM] == VALUE
    # Check that this value is reset after the exiting the context.
    assert mpl.rcParams[PARAM] == 'gray'


def test_context_with_dict():
    original_value = 'gray'
    other_value = 'blue'
    mpl.rcParams[PARAM] = original_value
    with style.context({PARAM: other_value}):
        assert mpl.rcParams[PARAM] == other_value
    assert mpl.rcParams[PARAM] == original_value


def test_context_with_dict_after_namedstyle():
    # Test dict after style name where dict modifies the same parameter.
    original_value = 'gray'
    other_value = 'blue'
    mpl.rcParams[PARAM] = original_value
    with temp_style('test', DUMMY_SETTINGS):
        with style.context(['test', {PARAM: other_value}]):
            assert mpl.rcParams[PARAM] == other_value
    assert mpl.rcParams[PARAM] == original_value


def test_context_with_dict_before_namedstyle():
    # Test dict before style name where dict modifies the same parameter.
    original_value = 'gray'
    other_value = 'blue'
    mpl.rcParams[PARAM] = original_value
    with temp_style('test', DUMMY_SETTINGS):
        with style.context([{PARAM: other_value}, 'test']):
            assert mpl.rcParams[PARAM] == VALUE
    assert mpl.rcParams[PARAM] == original_value


def test_context_with_union_of_dict_and_namedstyle():
    # Test dict after style name where dict modifies the a different parameter.
    original_value = 'gray'
    other_param = 'text.usetex'
    other_value = True
    d = {other_param: other_value}
    mpl.rcParams[PARAM] = original_value
    mpl.rcParams[other_param] = (not other_value)
    with temp_style('test', DUMMY_SETTINGS):
        with style.context(['test', d]):
            assert mpl.rcParams[PARAM] == VALUE
            assert mpl.rcParams[other_param] == other_value
    assert mpl.rcParams[PARAM] == original_value
    assert mpl.rcParams[other_param] == (not other_value)


def test_context_with_badparam():
    original_value = 'gray'
    other_value = 'blue'
    with style.context({PARAM: other_value}):
        assert mpl.rcParams[PARAM] == other_value
        x = style.context({PARAM: original_value, 'badparam': None})
        with pytest.raises(KeyError):
            with x:
                pass
        assert mpl.rcParams[PARAM] == other_value


@pytest.mark.parametrize('equiv_styles',
                         [('mpl20', 'default'),
                          ('mpl15', 'classic')],
                         ids=['mpl20', 'mpl15'])
def test_alias(equiv_styles):
    rc_dicts = []
    for sty in equiv_styles:
        with style.context(sty):
            rc_dicts.append(mpl.rcParams.copy())

    rc_base = rc_dicts[0]
    for nm, rc in zip(equiv_styles[1:], rc_dicts[1:]):
        assert rc_base == rc


def test_xkcd_no_cm():
    assert mpl.rcParams["path.sketch"] is None
    plt.xkcd()
    assert mpl.rcParams["path.sketch"] == (1, 100, 2)
    np.testing.break_cycles()
    assert mpl.rcParams["path.sketch"] == (1, 100, 2)


def test_xkcd_cm():
    assert mpl.rcParams["path.sketch"] is None
    with plt.xkcd():
        assert mpl.rcParams["path.sketch"] == (1, 100, 2)
    assert mpl.rcParams["path.sketch"] is None


def test_up_to_date_blacklist():
    assert mpl.style.core.STYLE_BLACKLIST <= {*mpl.rcsetup._validators}


def test_style_from_module(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(tmp_path)
    monkeypatch.chdir(tmp_path)
    pkg_path = tmp_path / "mpl_test_style_pkg"
    pkg_path.mkdir()
    (pkg_path / "test_style.mplstyle").write_text(
        "lines.linewidth: 42", encoding="utf-8")
    pkg_path.with_suffix(".mplstyle").write_text(
        "lines.linewidth: 84", encoding="utf-8")
    mpl.style.use("mpl_test_style_pkg.test_style")
    assert mpl.rcParams["lines.linewidth"] == 42
    mpl.style.use("mpl_test_style_pkg.mplstyle")
    assert mpl.rcParams["lines.linewidth"] == 84
    mpl.style.use("./mpl_test_style_pkg.mplstyle")
    assert mpl.rcParams["lines.linewidth"] == 84
