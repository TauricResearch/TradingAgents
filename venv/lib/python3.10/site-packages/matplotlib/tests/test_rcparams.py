import copy
import os
import subprocess
import sys
from unittest import mock

from cycler import cycler, Cycler
from packaging.version import parse as parse_version
import pytest

import matplotlib as mpl
from matplotlib import _api, _c_internal_utils
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
from matplotlib.rcsetup import (
    validate_bool,
    validate_color,
    validate_colorlist,
    _validate_color_or_linecolor,
    validate_cycler,
    validate_float,
    validate_fontstretch,
    validate_fontweight,
    validate_hatch,
    validate_hist_bins,
    validate_int,
    validate_markevery,
    validate_stringlist,
    validate_sketch,
    _validate_linestyle,
    _listify_validator)
from matplotlib.testing import subprocess_run_for_testing


def test_rcparams(tmp_path):
    mpl.rc('text', usetex=False)
    mpl.rc('lines', linewidth=22)

    usetex = mpl.rcParams['text.usetex']
    linewidth = mpl.rcParams['lines.linewidth']

    rcpath = tmp_path / 'test_rcparams.rc'
    rcpath.write_text('lines.linewidth: 33', encoding='utf-8')

    # test context given dictionary
    with mpl.rc_context(rc={'text.usetex': not usetex}):
        assert mpl.rcParams['text.usetex'] == (not usetex)
    assert mpl.rcParams['text.usetex'] == usetex

    # test context given filename (mpl.rc sets linewidth to 33)
    with mpl.rc_context(fname=rcpath):
        assert mpl.rcParams['lines.linewidth'] == 33
    assert mpl.rcParams['lines.linewidth'] == linewidth

    # test context given filename and dictionary
    with mpl.rc_context(fname=rcpath, rc={'lines.linewidth': 44}):
        assert mpl.rcParams['lines.linewidth'] == 44
    assert mpl.rcParams['lines.linewidth'] == linewidth

    # test context as decorator (and test reusability, by calling func twice)
    @mpl.rc_context({'lines.linewidth': 44})
    def func():
        assert mpl.rcParams['lines.linewidth'] == 44

    func()
    func()

    # test rc_file
    mpl.rc_file(rcpath)
    assert mpl.rcParams['lines.linewidth'] == 33


def test_RcParams_class():
    rc = mpl.RcParams({'font.cursive': ['Apple Chancery',
                                        'Textile',
                                        'Zapf Chancery',
                                        'cursive'],
                       'font.family': 'sans-serif',
                       'font.weight': 'normal',
                       'font.size': 12})

    expected_repr = """
RcParams({'font.cursive': ['Apple Chancery',
                           'Textile',
                           'Zapf Chancery',
                           'cursive'],
          'font.family': ['sans-serif'],
          'font.size': 12.0,
          'font.weight': 'normal'})""".lstrip()

    assert expected_repr == repr(rc)

    expected_str = """
font.cursive: ['Apple Chancery', 'Textile', 'Zapf Chancery', 'cursive']
font.family: ['sans-serif']
font.size: 12.0
font.weight: normal""".lstrip()

    assert expected_str == str(rc)

    # test the find_all functionality
    assert ['font.cursive', 'font.size'] == sorted(rc.find_all('i[vz]'))
    assert ['font.family'] == list(rc.find_all('family'))


def test_rcparams_update():
    rc = mpl.RcParams({'figure.figsize': (3.5, 42)})
    bad_dict = {'figure.figsize': (3.5, 42, 1)}
    # make sure validation happens on input
    with pytest.raises(ValueError):
        rc.update(bad_dict)


def test_rcparams_init():
    with pytest.raises(ValueError):
        mpl.RcParams({'figure.figsize': (3.5, 42, 1)})


def test_nargs_cycler():
    from matplotlib.rcsetup import cycler as ccl
    with pytest.raises(TypeError, match='3 were given'):
        # cycler() takes 0-2 arguments.
        ccl(ccl(color=list('rgb')), 2, 3)


def test_Bug_2543():
    # Test that it possible to add all values to itself / deepcopy
    # https://github.com/matplotlib/matplotlib/issues/2543
    # We filter warnings at this stage since a number of them are raised
    # for deprecated rcparams as they should. We don't want these in the
    # printed in the test suite.
    with _api.suppress_matplotlib_deprecation_warning():
        with mpl.rc_context():
            _copy = mpl.rcParams.copy()
            for key in _copy:
                mpl.rcParams[key] = _copy[key]
        with mpl.rc_context():
            copy.deepcopy(mpl.rcParams)
    with pytest.raises(ValueError):
        validate_bool(None)
    with pytest.raises(ValueError):
        with mpl.rc_context():
            mpl.rcParams['svg.fonttype'] = True


legend_color_tests = [
    ('face', {'color': 'r'}, mcolors.to_rgba('r')),
    ('face', {'color': 'inherit', 'axes.facecolor': 'r'},
     mcolors.to_rgba('r')),
    ('face', {'color': 'g', 'axes.facecolor': 'r'}, mcolors.to_rgba('g')),
    ('edge', {'color': 'r'}, mcolors.to_rgba('r')),
    ('edge', {'color': 'inherit', 'axes.edgecolor': 'r'},
     mcolors.to_rgba('r')),
    ('edge', {'color': 'g', 'axes.facecolor': 'r'}, mcolors.to_rgba('g'))
]
legend_color_test_ids = [
    'same facecolor',
    'inherited facecolor',
    'different facecolor',
    'same edgecolor',
    'inherited edgecolor',
    'different facecolor',
]


@pytest.mark.parametrize('color_type, param_dict, target', legend_color_tests,
                         ids=legend_color_test_ids)
def test_legend_colors(color_type, param_dict, target):
    param_dict[f'legend.{color_type}color'] = param_dict.pop('color')
    get_func = f'get_{color_type}color'

    with mpl.rc_context(param_dict):
        _, ax = plt.subplots()
        ax.plot(range(3), label='test')
        leg = ax.legend()
        assert getattr(leg.legendPatch, get_func)() == target


def test_mfc_rcparams():
    mpl.rcParams['lines.markerfacecolor'] = 'r'
    ln = mpl.lines.Line2D([1, 2], [1, 2])
    assert ln.get_markerfacecolor() == 'r'


def test_mec_rcparams():
    mpl.rcParams['lines.markeredgecolor'] = 'r'
    ln = mpl.lines.Line2D([1, 2], [1, 2])
    assert ln.get_markeredgecolor() == 'r'


def test_axes_titlecolor_rcparams():
    mpl.rcParams['axes.titlecolor'] = 'r'
    _, ax = plt.subplots()
    title = ax.set_title("Title")
    assert title.get_color() == 'r'


def test_Issue_1713(tmp_path):
    rcpath = tmp_path / 'test_rcparams.rc'
    rcpath.write_text('timezone: UTC', encoding='utf-8')
    with mock.patch('locale.getpreferredencoding', return_value='UTF-32-BE'):
        rc = mpl.rc_params_from_file(rcpath, True, False)
    assert rc.get('timezone') == 'UTC'


def test_animation_frame_formats():
    # Animation frame_format should allow any of the following
    # if any of these are not allowed, an exception will be raised
    # test for gh issue #17908
    for fmt in ['png', 'jpeg', 'tiff', 'raw', 'rgba', 'ppm',
                'sgi', 'bmp', 'pbm', 'svg']:
        mpl.rcParams['animation.frame_format'] = fmt


def generate_validator_testcases(valid):
    validation_tests = (
        {'validator': validate_bool,
         'success': (*((_, True) for _ in
                       ('t', 'y', 'yes', 'on', 'true', '1', 1, True)),
                     *((_, False) for _ in
                       ('f', 'n', 'no', 'off', 'false', '0', 0, False))),
         'fail': ((_, ValueError)
                  for _ in ('aardvark', 2, -1, [], ))
         },
        {'validator': validate_stringlist,
         'success': (('', []),
                     ('a,b', ['a', 'b']),
                     ('aardvark', ['aardvark']),
                     ('aardvark, ', ['aardvark']),
                     ('aardvark, ,', ['aardvark']),
                     (['a', 'b'], ['a', 'b']),
                     (('a', 'b'), ['a', 'b']),
                     (iter(['a', 'b']), ['a', 'b']),
                     (np.array(['a', 'b']), ['a', 'b']),
                     ),
         'fail': ((set(), ValueError),
                  (1, ValueError),
                  )
         },
        {'validator': _listify_validator(validate_int, n=2),
         'success': ((_, [1, 2])
                     for _ in ('1, 2', [1.5, 2.5], [1, 2],
                               (1, 2), np.array((1, 2)))),
         'fail': ((_, ValueError)
                  for _ in ('aardvark', ('a', 1),
                            (1, 2, 3)
                            ))
         },
        {'validator': _listify_validator(validate_float, n=2),
         'success': ((_, [1.5, 2.5])
                     for _ in ('1.5, 2.5', [1.5, 2.5], [1.5, 2.5],
                               (1.5, 2.5), np.array((1.5, 2.5)))),
         'fail': ((_, ValueError)
                  for _ in ('aardvark', ('a', 1), (1, 2, 3), (None, ), None))
         },
        {'validator': validate_cycler,
         'success': (('cycler("color", "rgb")',
                      cycler("color", 'rgb')),
                     (cycler('linestyle', ['-', '--']),
                      cycler('linestyle', ['-', '--'])),
                     ("""(cycler("color", ["r", "g", "b"]) +
                          cycler("mew", [2, 3, 5]))""",
                      (cycler("color", 'rgb') +
                       cycler("markeredgewidth", [2, 3, 5]))),
                     ("cycler(c='rgb', lw=[1, 2, 3])",
                      cycler('color', 'rgb') + cycler('linewidth', [1, 2, 3])),
                     ("cycler('c', 'rgb') * cycler('linestyle', ['-', '--'])",
                      (cycler('color', 'rgb') *
                       cycler('linestyle', ['-', '--']))),
                     (cycler('ls', ['-', '--']),
                      cycler('linestyle', ['-', '--'])),
                     (cycler(mew=[2, 5]),
                      cycler('markeredgewidth', [2, 5])),
                     ),
         # This is *so* incredibly important: validate_cycler() eval's
         # an arbitrary string! I think I have it locked down enough,
         # and that is what this is testing.
         # TODO: Note that these tests are actually insufficient, as it may
         # be that they raised errors, but still did an action prior to
         # raising the exception. We should devise some additional tests
         # for that...
         'fail': ((4, ValueError),  # Gotta be a string or Cycler object
                  ('cycler("bleh, [])', ValueError),  # syntax error
                  ('Cycler("linewidth", [1, 2, 3])',
                   ValueError),  # only 'cycler()' function is allowed
                  # do not allow dunder in string literals
                  ("cycler('c', [j.__class__(j) for j in ['r', 'b']])",
                   ValueError),
                  ("cycler('c', [j. __class__(j) for j in ['r', 'b']])",
                   ValueError),
                  ("cycler('c', [j.\t__class__(j) for j in ['r', 'b']])",
                   ValueError),
                  ("cycler('c', [j.\u000c__class__(j) for j in ['r', 'b']])",
                   ValueError),
                  ("cycler('c', [j.__class__(j).lower() for j in ['r', 'b']])",
                   ValueError),
                  ('1 + 2', ValueError),  # doesn't produce a Cycler object
                  ('os.system("echo Gotcha")', ValueError),  # os not available
                  ('import os', ValueError),  # should not be able to import
                  ('def badjuju(a): return a; badjuju(cycler("color", "rgb"))',
                   ValueError),  # Should not be able to define anything
                  # even if it does return a cycler
                  ('cycler("waka", [1, 2, 3])', ValueError),  # not a property
                  ('cycler(c=[1, 2, 3])', ValueError),  # invalid values
                  ("cycler(lw=['a', 'b', 'c'])", ValueError),  # invalid values
                  (cycler('waka', [1, 3, 5]), ValueError),  # not a property
                  (cycler('color', ['C1', 'r', 'g']), ValueError)  # no CN
                  )
         },
        {'validator': validate_hatch,
         'success': (('--|', '--|'), ('\\oO', '\\oO'),
                     ('/+*/.x', '/+*/.x'), ('', '')),
         'fail': (('--_', ValueError),
                  (8, ValueError),
                  ('X', ValueError)),
         },
        {'validator': validate_colorlist,
         'success': (('r,g,b', ['r', 'g', 'b']),
                     (['r', 'g', 'b'], ['r', 'g', 'b']),
                     ('r, ,', ['r']),
                     (['', 'g', 'blue'], ['g', 'blue']),
                     ([np.array([1, 0, 0]), np.array([0, 1, 0])],
                     np.array([[1, 0, 0], [0, 1, 0]])),
                     (np.array([[1, 0, 0], [0, 1, 0]]),
                     np.array([[1, 0, 0], [0, 1, 0]])),
                     ),
         'fail': (('fish', ValueError),
                  ),
         },
        {'validator': validate_color,
         'success': (('None', 'none'),
                     ('none', 'none'),
                     ('AABBCC', '#AABBCC'),  # RGB hex code
                     ('AABBCC00', '#AABBCC00'),  # RGBA hex code
                     ('tab:blue', 'tab:blue'),  # named color
                     ('C12', 'C12'),  # color from cycle
                     ('(0, 1, 0)', (0.0, 1.0, 0.0)),  # RGB tuple
                     ((0, 1, 0), (0, 1, 0)),  # non-string version
                     ('(0, 1, 0, 1)', (0.0, 1.0, 0.0, 1.0)),  # RGBA tuple
                     ((0, 1, 0, 1), (0, 1, 0, 1)),  # non-string version
                     ),
         'fail': (('tab:veryblue', ValueError),  # invalid name
                  ('(0, 1)', ValueError),  # tuple with length < 3
                  ('(0, 1, 0, 1, 0)', ValueError),  # tuple with length > 4
                  ('(0, 1, none)', ValueError),  # cannot cast none to float
                  ('(0, 1, "0.5")', ValueError),  # last one not a float
                  ),
         },
        {'validator': _validate_color_or_linecolor,
         'success': (('linecolor', 'linecolor'),
                     ('markerfacecolor', 'markerfacecolor'),
                     ('mfc', 'markerfacecolor'),
                     ('markeredgecolor', 'markeredgecolor'),
                     ('mec', 'markeredgecolor')
                     ),
         'fail': (('line', ValueError),
                  ('marker', ValueError)
                  )
         },
        {'validator': validate_hist_bins,
         'success': (('auto', 'auto'),
                     ('fd', 'fd'),
                     ('10', 10),
                     ('1, 2, 3', [1, 2, 3]),
                     ([1, 2, 3], [1, 2, 3]),
                     (np.arange(15), np.arange(15))
                     ),
         'fail': (('aardvark', ValueError),
                  )
         },
        {'validator': validate_markevery,
         'success': ((None, None),
                     (1, 1),
                     (0.1, 0.1),
                     ((1, 1), (1, 1)),
                     ((0.1, 0.1), (0.1, 0.1)),
                     ([1, 2, 3], [1, 2, 3]),
                     (slice(2), slice(None, 2, None)),
                     (slice(1, 2, 3), slice(1, 2, 3))
                     ),
         'fail': (((1, 2, 3), TypeError),
                  ([1, 2, 0.3], TypeError),
                  (['a', 2, 3], TypeError),
                  ([1, 2, 'a'], TypeError),
                  ((0.1, 0.2, 0.3), TypeError),
                  ((0.1, 2, 3), TypeError),
                  ((1, 0.2, 0.3), TypeError),
                  ((1, 0.1), TypeError),
                  ((0.1, 1), TypeError),
                  (('abc'), TypeError),
                  ((1, 'a'), TypeError),
                  ((0.1, 'b'), TypeError),
                  (('a', 1), TypeError),
                  (('a', 0.1), TypeError),
                  ('abc', TypeError),
                  ('a', TypeError),
                  (object(), TypeError)
                  )
         },
        {'validator': _validate_linestyle,
         'success': (('-', '-'), ('solid', 'solid'),
                     ('--', '--'), ('dashed', 'dashed'),
                     ('-.', '-.'), ('dashdot', 'dashdot'),
                     (':', ':'), ('dotted', 'dotted'),
                     ('', ''), (' ', ' '),
                     ('None', 'none'), ('none', 'none'),
                     ('DoTtEd', 'dotted'),  # case-insensitive
                     ('1, 3', (0, (1, 3))),
                     ([1.23, 456], (0, [1.23, 456.0])),
                     ([1, 2, 3, 4], (0, [1.0, 2.0, 3.0, 4.0])),
                     ((0, [1, 2]), (0, [1, 2])),
                     ((-1, [1, 2]), (-1, [1, 2])),
                     ),
         'fail': (('aardvark', ValueError),  # not a valid string
                  (b'dotted', ValueError),
                  ('dotted'.encode('utf-16'), ValueError),
                  ([1, 2, 3], ValueError),  # sequence with odd length
                  (1.23, ValueError),  # not a sequence
                  (("a", [1, 2]), ValueError),  # wrong explicit offset
                  ((None, [1, 2]), ValueError),  # wrong explicit offset
                  ((1, [1, 2, 3]), ValueError),  # odd length sequence
                  (([1, 2], 1), ValueError),  # inverted offset/onoff
                  )
         },
    )

    for validator_dict in validation_tests:
        validator = validator_dict['validator']
        if valid:
            for arg, target in validator_dict['success']:
                yield validator, arg, target
        else:
            for arg, error_type in validator_dict['fail']:
                yield validator, arg, error_type


@pytest.mark.parametrize('validator, arg, target',
                         generate_validator_testcases(True))
def test_validator_valid(validator, arg, target):
    res = validator(arg)
    if isinstance(target, np.ndarray):
        np.testing.assert_equal(res, target)
    elif not isinstance(target, Cycler):
        assert res == target
    else:
        # Cyclers can't simply be asserted equal. They don't implement __eq__
        assert list(res) == list(target)


@pytest.mark.parametrize('validator, arg, exception_type',
                         generate_validator_testcases(False))
def test_validator_invalid(validator, arg, exception_type):
    with pytest.raises(exception_type):
        validator(arg)


@pytest.mark.parametrize('weight, parsed_weight', [
    ('bold', 'bold'),
    ('BOLD', ValueError),  # weight is case-sensitive
    (100, 100),
    ('100', 100),
    (np.array(100), 100),
    # fractional fontweights are not defined. This should actually raise a
    # ValueError, but historically did not.
    (20.6, 20),
    ('20.6', ValueError),
    ([100], ValueError),
])
def test_validate_fontweight(weight, parsed_weight):
    if parsed_weight is ValueError:
        with pytest.raises(ValueError):
            validate_fontweight(weight)
    else:
        assert validate_fontweight(weight) == parsed_weight


@pytest.mark.parametrize('stretch, parsed_stretch', [
    ('expanded', 'expanded'),
    ('EXPANDED', ValueError),  # stretch is case-sensitive
    (100, 100),
    ('100', 100),
    (np.array(100), 100),
    # fractional fontweights are not defined. This should actually raise a
    # ValueError, but historically did not.
    (20.6, 20),
    ('20.6', ValueError),
    ([100], ValueError),
])
def test_validate_fontstretch(stretch, parsed_stretch):
    if parsed_stretch is ValueError:
        with pytest.raises(ValueError):
            validate_fontstretch(stretch)
    else:
        assert validate_fontstretch(stretch) == parsed_stretch


def test_keymaps():
    key_list = [k for k in mpl.rcParams if 'keymap' in k]
    for k in key_list:
        assert isinstance(mpl.rcParams[k], list)


def test_no_backend_reset_rccontext():
    assert mpl.rcParams['backend'] != 'module://aardvark'
    with mpl.rc_context():
        mpl.rcParams['backend'] = 'module://aardvark'
    assert mpl.rcParams['backend'] == 'module://aardvark'


def test_rcparams_reset_after_fail():
    # There was previously a bug that meant that if rc_context failed and
    # raised an exception due to issues in the supplied rc parameters, the
    # global rc parameters were left in a modified state.
    with mpl.rc_context(rc={'text.usetex': False}):
        assert mpl.rcParams['text.usetex'] is False
        with pytest.raises(KeyError):
            with mpl.rc_context(rc={'text.usetex': True, 'test.blah': True}):
                pass
        assert mpl.rcParams['text.usetex'] is False


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_backend_fallback_headless_invalid_backend(tmp_path):
    env = {**os.environ,
           "DISPLAY": "", "WAYLAND_DISPLAY": "",
           "MPLBACKEND": "", "MPLCONFIGDIR": str(tmp_path)}
    # plotting should fail with the tkagg backend selected in a headless environment
    with pytest.raises(subprocess.CalledProcessError):
        subprocess_run_for_testing(
            [sys.executable, "-c",
             "import matplotlib;"
             "matplotlib.use('tkagg');"
             "import matplotlib.pyplot;"
             "matplotlib.pyplot.plot(42);"
             ],
            env=env, check=True, stderr=subprocess.DEVNULL)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_backend_fallback_headless_auto_backend(tmp_path):
    # specify a headless mpl environment, but request a graphical (tk) backend
    env = {**os.environ,
           "DISPLAY": "", "WAYLAND_DISPLAY": "",
           "MPLBACKEND": "TkAgg", "MPLCONFIGDIR": str(tmp_path)}

    # allow fallback to an available interactive backend explicitly in configuration
    rc_path = tmp_path / "matplotlibrc"
    rc_path.write_text("backend_fallback: true")

    # plotting should succeed, by falling back to use the generic agg backend
    backend = subprocess_run_for_testing(
        [sys.executable, "-c",
         "import matplotlib.pyplot;"
         "matplotlib.pyplot.plot(42);"
         "print(matplotlib.get_backend());"
         ],
        env=env, text=True, check=True, capture_output=True).stdout
    assert backend.strip().lower() == "agg"


@pytest.mark.skipif(
    sys.platform == "linux" and not _c_internal_utils.xdisplay_is_valid(),
    reason="headless")
def test_backend_fallback_headful(tmp_path):
    if parse_version(pytest.__version__) >= parse_version('8.2.0'):
        pytest_kwargs = dict(exc_type=ImportError)
    else:
        pytest_kwargs = {}

    pytest.importorskip("tkinter", **pytest_kwargs)
    env = {**os.environ, "MPLBACKEND": "", "MPLCONFIGDIR": str(tmp_path)}
    backend = subprocess_run_for_testing(
        [sys.executable, "-c",
         "import matplotlib as mpl; "
         "sentinel = mpl.rcsetup._auto_backend_sentinel; "
         # Check that access on another instance does not resolve the sentinel.
         "assert mpl.RcParams({'backend': sentinel})['backend'] == sentinel; "
         "assert mpl.rcParams._get('backend') == sentinel; "
         "assert mpl.get_backend(auto_select=False) is None; "
         "import matplotlib.pyplot; "
         "print(matplotlib.get_backend())"],
        env=env, text=True, check=True, capture_output=True).stdout
    # The actual backend will depend on what's installed, but at least tkagg is
    # present.
    assert backend.strip().lower() != "agg"


def test_deprecation(monkeypatch):
    monkeypatch.setitem(
        mpl._deprecated_map, "patch.linewidth",
        ("0.0", "axes.linewidth", lambda old: 2 * old, lambda new: new / 2))
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        assert mpl.rcParams["patch.linewidth"] \
            == mpl.rcParams["axes.linewidth"] / 2
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        mpl.rcParams["patch.linewidth"] = 1
    assert mpl.rcParams["axes.linewidth"] == 2

    monkeypatch.setitem(
        mpl._deprecated_ignore_map, "patch.edgecolor",
        ("0.0", "axes.edgecolor"))
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        assert mpl.rcParams["patch.edgecolor"] \
            == mpl.rcParams["axes.edgecolor"]
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        mpl.rcParams["patch.edgecolor"] = "#abcd"
    assert mpl.rcParams["axes.edgecolor"] != "#abcd"

    monkeypatch.setitem(
        mpl._deprecated_ignore_map, "patch.force_edgecolor",
        ("0.0", None))
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        assert mpl.rcParams["patch.force_edgecolor"] is None

    monkeypatch.setitem(
        mpl._deprecated_remain_as_none, "svg.hashsalt",
        ("0.0",))
    with pytest.warns(mpl.MatplotlibDeprecationWarning):
        mpl.rcParams["svg.hashsalt"] = "foobar"
    assert mpl.rcParams["svg.hashsalt"] == "foobar"  # Doesn't warn.
    mpl.rcParams["svg.hashsalt"] = None  # Doesn't warn.

    mpl.rcParams.update(mpl.rcParams.copy())  # Doesn't warn.
    # Note that the warning suppression actually arises from the
    # iteration over the updater rcParams being protected by
    # suppress_matplotlib_deprecation_warning, rather than any explicit check.


@pytest.mark.parametrize("value", [
    "best",
    1,
    "1",
    (0.9, .7),
    (-0.9, .7),
    "(0.9, .7)"
])
def test_rcparams_legend_loc(value):
    # rcParams['legend.loc'] should allow any of the following formats.
    # if any of these are not allowed, an exception will be raised
    # test for gh issue #22338
    mpl.rcParams["legend.loc"] = value


@pytest.mark.parametrize("value", [
    "best",
    1,
    (0.9, .7),
    (-0.9, .7),
])
def test_rcparams_legend_loc_from_file(tmp_path, value):
    # rcParams['legend.loc'] should be settable from matplotlibrc.
    # if any of these are not allowed, an exception will be raised.
    # test for gh issue #22338
    rc_path = tmp_path / "matplotlibrc"
    rc_path.write_text(f"legend.loc: {value}")

    with mpl.rc_context(fname=rc_path):
        assert mpl.rcParams["legend.loc"] == value


@pytest.mark.parametrize("value", [(1, 2, 3), '1, 2, 3', '(1, 2, 3)'])
def test_validate_sketch(value):
    mpl.rcParams["path.sketch"] = value
    assert mpl.rcParams["path.sketch"] == (1, 2, 3)
    assert validate_sketch(value) == (1, 2, 3)


@pytest.mark.parametrize("value", [1, '1', '1 2 3'])
def test_validate_sketch_error(value):
    with pytest.raises(ValueError, match="scale, length, randomness"):
        validate_sketch(value)
    with pytest.raises(ValueError, match="scale, length, randomness"):
        mpl.rcParams["path.sketch"] = value


@pytest.mark.parametrize("value", ['1, 2, 3', '(1,2,3)'])
def test_rcparams_path_sketch_from_file(tmp_path, value):
    rc_path = tmp_path / "matplotlibrc"
    rc_path.write_text(f"path.sketch: {value}")
    with mpl.rc_context(fname=rc_path):
        assert mpl.rcParams["path.sketch"] == (1, 2, 3)
