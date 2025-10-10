import functools
import importlib
import importlib.util
import inspect
import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

from PIL import Image

import pytest

import matplotlib as mpl
from matplotlib import _c_internal_utils
from matplotlib.backend_tools import ToolToggleBase
from matplotlib.testing import subprocess_run_helper as _run_helper, is_ci_environment


class _WaitForStringPopen(subprocess.Popen):
    """
    A Popen that passes flags that allow triggering KeyboardInterrupt.
    """

    def __init__(self, *args, **kwargs):
        if sys.platform == 'win32':
            kwargs['creationflags'] = subprocess.CREATE_NEW_CONSOLE
        super().__init__(
            *args, **kwargs,
            # Force Agg so that each test can switch to its desired backend.
            env={**os.environ, "MPLBACKEND": "Agg", "SOURCE_DATE_EPOCH": "0"},
            stdout=subprocess.PIPE, universal_newlines=True)

    def wait_for(self, terminator):
        """Read until the terminator is reached."""
        buf = ''
        while True:
            c = self.stdout.read(1)
            if not c:
                raise RuntimeError(
                    f'Subprocess died before emitting expected {terminator!r}')
            buf += c
            if buf.endswith(terminator):
                return


# Minimal smoke-testing of the backends for which the dependencies are
# PyPI-installable on CI.  They are not available for all tested Python
# versions so we don't fail on missing backends.

@functools.lru_cache
def _get_available_interactive_backends():
    _is_linux_and_display_invalid = (sys.platform == "linux" and
                                     not _c_internal_utils.display_is_valid())
    _is_linux_and_xdisplay_invalid = (sys.platform == "linux" and
                                      not _c_internal_utils.xdisplay_is_valid())
    envs = []
    for deps, env in [
            *[([qt_api],
               {"MPLBACKEND": "qtagg", "QT_API": qt_api})
              for qt_api in ["PyQt6", "PySide6", "PyQt5", "PySide2"]],
            *[([qt_api, "cairocffi"],
               {"MPLBACKEND": "qtcairo", "QT_API": qt_api})
              for qt_api in ["PyQt6", "PySide6", "PyQt5", "PySide2"]],
            *[(["cairo", "gi"], {"MPLBACKEND": f"gtk{version}{renderer}"})
              for version in [3, 4] for renderer in ["agg", "cairo"]],
            (["tkinter"], {"MPLBACKEND": "tkagg"}),
            (["wx"], {"MPLBACKEND": "wx"}),
            (["wx"], {"MPLBACKEND": "wxagg"}),
            (["matplotlib.backends._macosx"], {"MPLBACKEND": "macosx"}),
    ]:
        reason = None
        missing = [dep for dep in deps if not importlib.util.find_spec(dep)]
        if missing:
            reason = "{} cannot be imported".format(", ".join(missing))
        elif _is_linux_and_xdisplay_invalid and (
                env["MPLBACKEND"] == "tkagg"
                # Remove when https://github.com/wxWidgets/Phoenix/pull/2638 is out.
                or env["MPLBACKEND"].startswith("wx")):
            reason = "$DISPLAY is unset"
        elif _is_linux_and_display_invalid:
            reason = "$DISPLAY and $WAYLAND_DISPLAY are unset"
        elif env["MPLBACKEND"] == 'macosx' and os.environ.get('TF_BUILD'):
            reason = "macosx backend fails on Azure"
        elif env["MPLBACKEND"].startswith('gtk'):
            try:
                import gi  # type: ignore[import]
            except ImportError:
                # Though we check that `gi` exists above, it is possible that its
                # C-level dependencies are not available, and then it still raises an
                # `ImportError`, so guard against that.
                available_gtk_versions = []
            else:
                gi_repo = gi.Repository.get_default()
                available_gtk_versions = gi_repo.enumerate_versions('Gtk')
            version = env["MPLBACKEND"][3]
            if f'{version}.0' not in available_gtk_versions:
                reason = "no usable GTK bindings"
        marks = []
        if reason:
            marks.append(pytest.mark.skip(reason=f"Skipping {env} because {reason}"))
        elif env["MPLBACKEND"].startswith('wx') and sys.platform == 'darwin':
            # ignore on macosx because that's currently broken (github #16849)
            marks.append(pytest.mark.xfail(reason='github #16849'))
        elif (env['MPLBACKEND'] == 'tkagg' and
              ('TF_BUILD' in os.environ or 'GITHUB_ACTION' in os.environ) and
              sys.platform == 'darwin' and
              sys.version_info[:2] < (3, 11)
              ):
            marks.append(  # https://github.com/actions/setup-python/issues/649
                pytest.mark.xfail(reason='Tk version mismatch on Azure macOS CI'))
        envs.append(({**env, 'BACKEND_DEPS': ','.join(deps)}, marks))
    return envs


def _get_testable_interactive_backends():
    # We re-create this because some of the callers below might modify the markers.
    return [pytest.param({**env}, marks=[*marks],
                         id='-'.join(f'{k}={v}' for k, v in env.items()))
            for env, marks in _get_available_interactive_backends()]


# Reasonable safe values for slower CI/Remote and local architectures.
_test_timeout = 120 if is_ci_environment() else 20


def _test_toolbar_button_la_mode_icon(fig):
    # test a toolbar button icon using an image in LA mode (GH issue 25174)
    # create an icon in LA mode
    with tempfile.TemporaryDirectory() as tempdir:
        img = Image.new("LA", (26, 26))
        tmp_img_path = os.path.join(tempdir, "test_la_icon.png")
        img.save(tmp_img_path)

        class CustomTool(ToolToggleBase):
            image = tmp_img_path
            description = ""  # gtk3 backend does not allow None

        toolmanager = fig.canvas.manager.toolmanager
        toolbar = fig.canvas.manager.toolbar
        toolmanager.add_tool("test", CustomTool)
        toolbar.add_tool("test", "group")


# The source of this function gets extracted and run in another process, so it
# must be fully self-contained.
# Using a timer not only allows testing of timers (on other backends), but is
# also necessary on gtk3 and wx, where directly processing a KeyEvent() for "q"
# from draw_event causes breakage as the canvas widget gets deleted too early.
def _test_interactive_impl():
    import importlib.util
    import io
    import json
    import sys

    import pytest

    import matplotlib as mpl
    from matplotlib import pyplot as plt
    from matplotlib.backend_bases import KeyEvent
    mpl.rcParams.update({
        "webagg.open_in_browser": False,
        "webagg.port_retries": 1,
    })

    mpl.rcParams.update(json.loads(sys.argv[1]))
    backend = plt.rcParams["backend"].lower()

    if backend.endswith("agg") and not backend.startswith(("gtk", "web")):
        # Force interactive framework setup.
        fig = plt.figure()
        plt.close(fig)

        # Check that we cannot switch to a backend using another interactive
        # framework, but can switch to a backend using cairo instead of agg,
        # or a non-interactive backend.  In the first case, we use tkagg as
        # the "other" interactive backend as it is (essentially) guaranteed
        # to be present.  Moreover, don't test switching away from gtk3 (as
        # Gtk.main_level() is not set up at this point yet) and webagg (which
        # uses no interactive framework).

        if backend != "tkagg":
            with pytest.raises(ImportError):
                mpl.use("tkagg", force=True)

        def check_alt_backend(alt_backend):
            mpl.use(alt_backend, force=True)
            fig = plt.figure()
            assert (type(fig.canvas).__module__ ==
                    f"matplotlib.backends.backend_{alt_backend}")
            plt.close("all")

        if importlib.util.find_spec("cairocffi"):
            check_alt_backend(backend[:-3] + "cairo")
        check_alt_backend("svg")
    mpl.use(backend, force=True)

    fig, ax = plt.subplots()
    assert type(fig.canvas).__module__ == f"matplotlib.backends.backend_{backend}"

    assert fig.canvas.manager.get_window_title() == "Figure 1"

    if mpl.rcParams["toolbar"] == "toolmanager":
        # test toolbar button icon LA mode see GH issue 25174
        _test_toolbar_button_la_mode_icon(fig)

    ax.plot([0, 1], [2, 3])
    if fig.canvas.toolbar:  # i.e toolbar2.
        fig.canvas.toolbar.draw_rubberband(None, 1., 1, 2., 2)

    timer = fig.canvas.new_timer(1.)  # Test that floats are cast to int.
    timer.add_callback(KeyEvent("key_press_event", fig.canvas, "q")._process)
    # Trigger quitting upon draw.
    fig.canvas.mpl_connect("draw_event", lambda event: timer.start())
    fig.canvas.mpl_connect("close_event", print)

    result = io.BytesIO()
    fig.savefig(result, format='png')

    plt.show()

    # Ensure that the window is really closed.
    plt.pause(0.5)

    # Test that saving works after interactive window is closed, but the figure
    # is not deleted.
    result_after = io.BytesIO()
    fig.savefig(result_after, format='png')

    assert result.getvalue() == result_after.getvalue()


@pytest.mark.parametrize("env", _get_testable_interactive_backends())
@pytest.mark.parametrize("toolbar", ["toolbar2", "toolmanager"])
@pytest.mark.flaky(reruns=3)
def test_interactive_backend(env, toolbar):
    if env["MPLBACKEND"] == "macosx":
        if toolbar == "toolmanager":
            pytest.skip("toolmanager is not implemented for macosx.")
    if env["MPLBACKEND"] == "wx":
        pytest.skip("wx backend is deprecated; tests failed on appveyor")
    if env["MPLBACKEND"] == "wxagg" and toolbar == "toolmanager":
        pytest.skip("Temporarily deactivated: show() changes figure height "
                    "and thus fails the test")
    try:
        proc = _run_helper(
            _test_interactive_impl,
            json.dumps({"toolbar": toolbar}),
            timeout=_test_timeout,
            extra_env=env,
        )
    except subprocess.CalledProcessError as err:
        pytest.fail(
            "Subprocess failed to test intended behavior\n"
            + str(err.stderr))
    assert proc.stdout.count("CloseEvent") == 1


def _test_thread_impl():
    from concurrent.futures import ThreadPoolExecutor

    import matplotlib as mpl
    from matplotlib import pyplot as plt

    mpl.rcParams.update({
        "webagg.open_in_browser": False,
        "webagg.port_retries": 1,
    })

    # Test artist creation and drawing does not crash from thread
    # No other guarantees!
    fig, ax = plt.subplots()
    # plt.pause needed vs plt.show(block=False) at least on toolbar2-tkagg
    plt.pause(0.5)

    future = ThreadPoolExecutor().submit(ax.plot, [1, 3, 6])
    future.result()  # Joins the thread; rethrows any exception.

    fig.canvas.mpl_connect("close_event", print)
    future = ThreadPoolExecutor().submit(fig.canvas.draw)
    plt.pause(0.5)  # flush_events fails here on at least Tkagg (bpo-41176)
    future.result()  # Joins the thread; rethrows any exception.
    plt.close()  # backend is responsible for flushing any events here
    if plt.rcParams["backend"].lower().startswith("wx"):
        # TODO: debug why WX needs this only on py >= 3.8
        fig.canvas.flush_events()


_thread_safe_backends = _get_testable_interactive_backends()
# Known unsafe backends. Remove the xfails if they start to pass!
for param in _thread_safe_backends:
    backend = param.values[0]["MPLBACKEND"]
    if "cairo" in backend:
        # Cairo backends save a cairo_t on the graphics context, and sharing
        # these is not threadsafe.
        param.marks.append(
            pytest.mark.xfail(raises=subprocess.CalledProcessError))
    elif backend == "wx":
        param.marks.append(
            pytest.mark.xfail(raises=subprocess.CalledProcessError))
    elif backend == "macosx":
        from packaging.version import parse
        mac_ver = platform.mac_ver()[0]
        # Note, macOS Big Sur is both 11 and 10.16, depending on SDK that
        # Python was compiled against.
        if mac_ver and parse(mac_ver) < parse('10.16'):
            param.marks.append(
                pytest.mark.xfail(raises=subprocess.TimeoutExpired,
                                  strict=True))
    elif param.values[0].get("QT_API") == "PySide2":
        param.marks.append(
            pytest.mark.xfail(raises=subprocess.CalledProcessError))
    elif backend == "tkagg" and platform.python_implementation() != 'CPython':
        param.marks.append(
            pytest.mark.xfail(
                reason='PyPy does not support Tkinter threading: '
                       'https://foss.heptapod.net/pypy/pypy/-/issues/1929',
                strict=True))
    elif (backend == 'tkagg' and
          ('TF_BUILD' in os.environ or 'GITHUB_ACTION' in os.environ) and
          sys.platform == 'darwin' and sys.version_info[:2] < (3, 11)):
        param.marks.append(  # https://github.com/actions/setup-python/issues/649
            pytest.mark.xfail('Tk version mismatch on Azure macOS CI'))


@pytest.mark.parametrize("env", _thread_safe_backends)
@pytest.mark.flaky(reruns=3)
def test_interactive_thread_safety(env):
    proc = _run_helper(_test_thread_impl, timeout=_test_timeout, extra_env=env)
    assert proc.stdout.count("CloseEvent") == 1


def _impl_test_lazy_auto_backend_selection():
    import matplotlib
    import matplotlib.pyplot as plt
    # just importing pyplot should not be enough to trigger resolution
    bk = matplotlib.rcParams._get('backend')
    assert not isinstance(bk, str)
    assert plt._backend_mod is None
    # but actually plotting should
    plt.plot(5)
    assert plt._backend_mod is not None
    bk = matplotlib.rcParams._get('backend')
    assert isinstance(bk, str)


def test_lazy_auto_backend_selection():
    _run_helper(_impl_test_lazy_auto_backend_selection,
                timeout=_test_timeout)


def _implqt5agg():
    import matplotlib.backends.backend_qt5agg  # noqa
    import sys

    assert 'PyQt6' not in sys.modules
    assert 'pyside6' not in sys.modules
    assert 'PyQt5' in sys.modules or 'pyside2' in sys.modules


def _implcairo():
    import matplotlib.backends.backend_qt5cairo  # noqa
    import sys

    assert 'PyQt6' not in sys.modules
    assert 'pyside6' not in sys.modules
    assert 'PyQt5' in sys.modules or 'pyside2' in sys.modules


def _implcore():
    import matplotlib.backends.backend_qt5  # noqa
    import sys

    assert 'PyQt6' not in sys.modules
    assert 'pyside6' not in sys.modules
    assert 'PyQt5' in sys.modules or 'pyside2' in sys.modules


def test_qt5backends_uses_qt5():
    qt5_bindings = [
        dep for dep in ['PyQt5', 'pyside2']
        if importlib.util.find_spec(dep) is not None
    ]
    qt6_bindings = [
        dep for dep in ['PyQt6', 'pyside6']
        if importlib.util.find_spec(dep) is not None
    ]
    if len(qt5_bindings) == 0 or len(qt6_bindings) == 0:
        pytest.skip('need both QT6 and QT5 bindings')
    _run_helper(_implqt5agg, timeout=_test_timeout)
    if importlib.util.find_spec('pycairo') is not None:
        _run_helper(_implcairo, timeout=_test_timeout)
    _run_helper(_implcore, timeout=_test_timeout)


def _impl_missing():
    import sys
    # Simulate uninstalled
    sys.modules["PyQt6"] = None
    sys.modules["PyQt5"] = None
    sys.modules["PySide2"] = None
    sys.modules["PySide6"] = None

    import matplotlib.pyplot as plt
    with pytest.raises(ImportError, match="Failed to import any of the following Qt"):
        plt.switch_backend("qtagg")
    # Specifically ensure that Pyside6/Pyqt6 are not in the error message for qt5agg
    with pytest.raises(ImportError, match="^(?:(?!(PySide6|PyQt6)).)*$"):
        plt.switch_backend("qt5agg")


def test_qt_missing():
    _run_helper(_impl_missing, timeout=_test_timeout)


def _impl_test_cross_Qt_imports():
    import importlib
    import sys
    import warnings

    _, host_binding, mpl_binding = sys.argv
    # import the mpl binding.  This will force us to use that binding
    importlib.import_module(f'{mpl_binding}.QtCore')
    mpl_binding_qwidgets = importlib.import_module(f'{mpl_binding}.QtWidgets')
    import matplotlib.backends.backend_qt
    host_qwidgets = importlib.import_module(f'{host_binding}.QtWidgets')

    host_app = host_qwidgets.QApplication(["mpl testing"])
    warnings.filterwarnings("error", message=r".*Mixing Qt major.*",
                            category=UserWarning)
    matplotlib.backends.backend_qt._create_qApp()


def qt5_and_qt6_pairs():
    qt5_bindings = [
        dep for dep in ['PyQt5', 'PySide2']
        if importlib.util.find_spec(dep) is not None
    ]
    qt6_bindings = [
        dep for dep in ['PyQt6', 'PySide6']
        if importlib.util.find_spec(dep) is not None
    ]
    if len(qt5_bindings) == 0 or len(qt6_bindings) == 0:
        yield pytest.param(None, None,
                           marks=[pytest.mark.skip('need both QT6 and QT5 bindings')])
        return

    for qt5 in qt5_bindings:
        for qt6 in qt6_bindings:
            yield from ([qt5, qt6], [qt6, qt5])


@pytest.mark.skipif(
    sys.platform == "linux" and not _c_internal_utils.display_is_valid(),
    reason="$DISPLAY and $WAYLAND_DISPLAY are unset")
@pytest.mark.parametrize('host, mpl', [*qt5_and_qt6_pairs()])
def test_cross_Qt_imports(host, mpl):
    try:
        proc = _run_helper(_impl_test_cross_Qt_imports, host, mpl,
                           timeout=_test_timeout)
    except subprocess.CalledProcessError as ex:
        # We do try to warn the user they are doing something that we do not
        # expect to work, so we're going to ignore if the subprocess crashes or
        # is killed, and just check that the warning is printed.
        stderr = ex.stderr
    else:
        stderr = proc.stderr
    assert "Mixing Qt major versions may not work as expected." in stderr


@pytest.mark.skipif('TF_BUILD' in os.environ,
                    reason="this test fails an azure for unknown reasons")
@pytest.mark.skipif(sys.platform == "win32", reason="Cannot send SIGINT on Windows.")
def test_webagg():
    pytest.importorskip("tornado")
    proc = subprocess.Popen(
        [sys.executable, "-c",
         inspect.getsource(_test_interactive_impl)
         + "\n_test_interactive_impl()", "{}"],
        env={**os.environ, "MPLBACKEND": "webagg", "SOURCE_DATE_EPOCH": "0"})
    url = f'http://{mpl.rcParams["webagg.address"]}:{mpl.rcParams["webagg.port"]}'
    timeout = time.perf_counter() + _test_timeout
    try:
        while True:
            try:
                retcode = proc.poll()
                # check that the subprocess for the server is not dead
                assert retcode is None
                conn = urllib.request.urlopen(url)
                break
            except urllib.error.URLError:
                if time.perf_counter() > timeout:
                    pytest.fail("Failed to connect to the webagg server.")
                else:
                    continue
        conn.close()
        proc.send_signal(signal.SIGINT)
        assert proc.wait(timeout=_test_timeout) == 0
    finally:
        if proc.poll() is None:
            proc.kill()


def _lazy_headless():
    import os
    import sys

    backend, deps = sys.argv[1:]
    deps = deps.split(',')

    # make it look headless
    os.environ.pop('DISPLAY', None)
    os.environ.pop('WAYLAND_DISPLAY', None)
    for dep in deps:
        assert dep not in sys.modules

    # we should fast-track to Agg
    import matplotlib.pyplot as plt
    assert plt.get_backend() == 'agg'
    for dep in deps:
        assert dep not in sys.modules

    # make sure we really have dependencies installed
    for dep in deps:
        importlib.import_module(dep)
        assert dep in sys.modules

    # try to switch and make sure we fail with ImportError
    try:
        plt.switch_backend(backend)
    except ImportError:
        pass
    else:
        sys.exit(1)


@pytest.mark.skipif(sys.platform != "linux", reason="this a linux-only test")
@pytest.mark.parametrize("env", _get_testable_interactive_backends())
def test_lazy_linux_headless(env):
    proc = _run_helper(
        _lazy_headless,
        env.pop('MPLBACKEND'), env.pop("BACKEND_DEPS"),
        timeout=_test_timeout,
        extra_env={**env, 'DISPLAY': '', 'WAYLAND_DISPLAY': ''}
    )


def _test_number_of_draws_script():
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()

    # animated=True tells matplotlib to only draw the artist when we
    # explicitly request it
    ln, = ax.plot([0, 1], [1, 2], animated=True)

    # make sure the window is raised, but the script keeps going
    plt.show(block=False)
    plt.pause(0.3)
    # Connect to draw_event to count the occurrences
    fig.canvas.mpl_connect('draw_event', print)

    # get copy of entire figure (everything inside fig.bbox)
    # sans animated artist
    bg = fig.canvas.copy_from_bbox(fig.bbox)
    # draw the animated artist, this uses a cached renderer
    ax.draw_artist(ln)
    # show the result to the screen
    fig.canvas.blit(fig.bbox)

    for j in range(10):
        # reset the background back in the canvas state, screen unchanged
        fig.canvas.restore_region(bg)
        # Create a **new** artist here, this is poor usage of blitting
        # but good for testing to make sure that this doesn't create
        # excessive draws
        ln, = ax.plot([0, 1], [1, 2])
        # render the artist, updating the canvas state, but not the screen
        ax.draw_artist(ln)
        # copy the image to the GUI state, but screen might not changed yet
        fig.canvas.blit(fig.bbox)
        # flush any pending GUI events, re-painting the screen if needed
        fig.canvas.flush_events()

    # Let the event loop process everything before leaving
    plt.pause(0.1)


_blit_backends = _get_testable_interactive_backends()
for param in _blit_backends:
    backend = param.values[0]["MPLBACKEND"]
    if backend == "gtk3cairo":
        # copy_from_bbox only works when rendering to an ImageSurface
        param.marks.append(
            pytest.mark.skip("gtk3cairo does not support blitting"))
    elif backend == "gtk4cairo":
        # copy_from_bbox only works when rendering to an ImageSurface
        param.marks.append(
            pytest.mark.skip("gtk4cairo does not support blitting"))
    elif backend == "wx":
        param.marks.append(
            pytest.mark.skip("wx does not support blitting"))
    elif (backend == 'tkagg' and
          ('TF_BUILD' in os.environ or 'GITHUB_ACTION' in os.environ) and
          sys.platform == 'darwin' and
          sys.version_info[:2] < (3, 11)
          ):
        param.marks.append(  # https://github.com/actions/setup-python/issues/649
            pytest.mark.xfail('Tk version mismatch on Azure macOS CI')
        )


@pytest.mark.parametrize("env", _blit_backends)
# subprocesses can struggle to get the display, so rerun a few times
@pytest.mark.flaky(reruns=4)
def test_blitting_events(env):
    proc = _run_helper(
        _test_number_of_draws_script, timeout=_test_timeout, extra_env=env)
    # Count the number of draw_events we got. We could count some initial
    # canvas draws (which vary in number by backend), but the critical
    # check here is that it isn't 10 draws, which would be called if
    # blitting is not properly implemented
    ndraws = proc.stdout.count("DrawEvent")
    assert 0 < ndraws < 5


def _impl_test_interactive_timers():
    # A timer with <1 millisecond gets converted to int and therefore 0
    # milliseconds, which the mac framework interprets as singleshot.
    # We only want singleshot if we specify that ourselves, otherwise we want
    # a repeating timer
    from unittest.mock import Mock
    import matplotlib.pyplot as plt
    pause_time = 0.5
    fig = plt.figure()
    plt.pause(pause_time)
    timer = fig.canvas.new_timer(0.1)
    mock = Mock()
    timer.add_callback(mock)
    timer.start()
    plt.pause(pause_time)
    timer.stop()
    assert mock.call_count > 1

    # Now turn it into a single shot timer and verify only one gets triggered
    mock.call_count = 0
    timer.single_shot = True
    timer.start()
    plt.pause(pause_time)
    assert mock.call_count == 1

    # Make sure we can start the timer a second time
    timer.start()
    plt.pause(pause_time)
    assert mock.call_count == 2
    plt.close("all")


@pytest.mark.parametrize("env", _get_testable_interactive_backends())
def test_interactive_timers(env):
    if env["MPLBACKEND"] == "gtk3cairo" and os.getenv("CI"):
        pytest.skip("gtk3cairo timers do not work in remote CI")
    if env["MPLBACKEND"] == "wx":
        pytest.skip("wx backend is deprecated; tests failed on appveyor")
    _run_helper(_impl_test_interactive_timers,
                timeout=_test_timeout, extra_env=env)


def _test_sigint_impl(backend, target_name, kwargs):
    import sys
    import matplotlib.pyplot as plt
    import os
    import threading

    plt.switch_backend(backend)

    def interrupter():
        if sys.platform == 'win32':
            import win32api
            win32api.GenerateConsoleCtrlEvent(0, 0)
        else:
            import signal
            os.kill(os.getpid(), signal.SIGINT)

    target = getattr(plt, target_name)
    timer = threading.Timer(1, interrupter)
    fig = plt.figure()
    fig.canvas.mpl_connect(
        'draw_event',
        lambda *args: print('DRAW', flush=True)
    )
    fig.canvas.mpl_connect(
        'draw_event',
        lambda *args: timer.start()
    )
    try:
        target(**kwargs)
    except KeyboardInterrupt:
        print('SUCCESS', flush=True)


@pytest.mark.parametrize("env", _get_testable_interactive_backends())
@pytest.mark.parametrize("target, kwargs", [
    ('show', {'block': True}),
    ('pause', {'interval': 10})
])
def test_sigint(env, target, kwargs):
    backend = env.get("MPLBACKEND")
    if not backend.startswith(("qt", "macosx")):
        pytest.skip("SIGINT currently only tested on qt and macosx")
    proc = _WaitForStringPopen(
        [sys.executable, "-c",
         inspect.getsource(_test_sigint_impl) +
         f"\n_test_sigint_impl({backend!r}, {target!r}, {kwargs!r})"])
    try:
        proc.wait_for('DRAW')
        stdout, _ = proc.communicate(timeout=_test_timeout)
    except Exception:
        proc.kill()
        stdout, _ = proc.communicate()
        raise
    assert 'SUCCESS' in stdout


def _test_other_signal_before_sigint_impl(backend, target_name, kwargs):
    import signal
    import matplotlib.pyplot as plt

    plt.switch_backend(backend)

    target = getattr(plt, target_name)

    fig = plt.figure()
    fig.canvas.mpl_connect('draw_event', lambda *args: print('DRAW', flush=True))

    timer = fig.canvas.new_timer(interval=1)
    timer.single_shot = True
    timer.add_callback(print, 'SIGUSR1', flush=True)

    def custom_signal_handler(signum, frame):
        timer.start()
    signal.signal(signal.SIGUSR1, custom_signal_handler)

    try:
        target(**kwargs)
    except KeyboardInterrupt:
        print('SUCCESS', flush=True)


@pytest.mark.skipif(sys.platform == 'win32',
                    reason='No other signal available to send on Windows')
@pytest.mark.parametrize("env", _get_testable_interactive_backends())
@pytest.mark.parametrize("target, kwargs", [
    ('show', {'block': True}),
    ('pause', {'interval': 10})
])
def test_other_signal_before_sigint(env, target, kwargs, request):
    backend = env.get("MPLBACKEND")
    if not backend.startswith(("qt", "macosx")):
        pytest.skip("SIGINT currently only tested on qt and macosx")
    if backend == "macosx":
        request.node.add_marker(pytest.mark.xfail(reason="macosx backend is buggy"))
    if sys.platform == "darwin" and target == "show":
        # We've not previously had these toolkits installed on CI, and so were never
        # aware that this was crashing. However, we've had little luck reproducing it
        # locally, so mark it xfail for now. For more information, see
        # https://github.com/matplotlib/matplotlib/issues/27984
        request.node.add_marker(
            pytest.mark.xfail(reason="Qt backend is buggy on macOS"))
    proc = _WaitForStringPopen(
        [sys.executable, "-c",
         inspect.getsource(_test_other_signal_before_sigint_impl) +
         "\n_test_other_signal_before_sigint_impl("
            f"{backend!r}, {target!r}, {kwargs!r})"])
    try:
        proc.wait_for('DRAW')
        os.kill(proc.pid, signal.SIGUSR1)
        proc.wait_for('SIGUSR1')
        os.kill(proc.pid, signal.SIGINT)
        stdout, _ = proc.communicate(timeout=_test_timeout)
    except Exception:
        proc.kill()
        stdout, _ = proc.communicate()
        raise
    print(stdout)
    assert 'SUCCESS' in stdout
