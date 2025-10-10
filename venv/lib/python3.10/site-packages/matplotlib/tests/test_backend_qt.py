import copy
import importlib
import os
import signal
import sys

from datetime import date, datetime
from unittest import mock

import pytest

import matplotlib
from matplotlib import pyplot as plt
from matplotlib._pylab_helpers import Gcf
from matplotlib import _c_internal_utils

try:
    from matplotlib.backends.qt_compat import QtGui  # type: ignore[attr-defined]  # noqa: E501, F401
    from matplotlib.backends.qt_compat import QtWidgets  # type: ignore[attr-defined]
    from matplotlib.backends.qt_editor import _formlayout
except ImportError:
    pytestmark = pytest.mark.skip('No usable Qt bindings')


_test_timeout = 60  # A reasonably safe value for slower architectures.


@pytest.fixture
def qt_core(request):
    from matplotlib.backends.qt_compat import QtCore
    return QtCore


@pytest.mark.backend('QtAgg', skip_on_importerror=True)
def test_fig_close():

    # save the state of Gcf.figs
    init_figs = copy.copy(Gcf.figs)

    # make a figure using pyplot interface
    fig = plt.figure()

    # simulate user clicking the close button by reaching in
    # and calling close on the underlying Qt object
    fig.canvas.manager.window.close()

    # assert that we have removed the reference to the FigureManager
    # that got added by plt.figure()
    assert init_figs == Gcf.figs


@pytest.mark.parametrize(
    "qt_key, qt_mods, answer",
    [
        ("Key_A", ["ShiftModifier"], "A"),
        ("Key_A", [], "a"),
        ("Key_A", ["ControlModifier"], ("ctrl+a")),
        (
            "Key_Aacute",
            ["ShiftModifier"],
            "\N{LATIN CAPITAL LETTER A WITH ACUTE}",
        ),
        ("Key_Aacute", [], "\N{LATIN SMALL LETTER A WITH ACUTE}"),
        ("Key_Control", ["AltModifier"], ("alt+control")),
        ("Key_Alt", ["ControlModifier"], "ctrl+alt"),
        (
            "Key_Aacute",
            ["ControlModifier", "AltModifier", "MetaModifier"],
            ("ctrl+alt+meta+\N{LATIN SMALL LETTER A WITH ACUTE}"),
        ),
        # We do not currently map the media keys, this may change in the
        # future.  This means the callback will never fire
        ("Key_Play", [], None),
        ("Key_Backspace", [], "backspace"),
        (
            "Key_Backspace",
            ["ControlModifier"],
            "ctrl+backspace",
        ),
    ],
    ids=[
        'shift',
        'lower',
        'control',
        'unicode_upper',
        'unicode_lower',
        'alt_control',
        'control_alt',
        'modifier_order',
        'non_unicode_key',
        'backspace',
        'backspace_mod',
    ]
)
@pytest.mark.parametrize('backend', [
    # Note: the value is irrelevant; the important part is the marker.
    pytest.param(
        'Qt5Agg',
        marks=pytest.mark.backend('Qt5Agg', skip_on_importerror=True)),
    pytest.param(
        'QtAgg',
        marks=pytest.mark.backend('QtAgg', skip_on_importerror=True)),
])
def test_correct_key(backend, qt_core, qt_key, qt_mods, answer, monkeypatch):
    """
    Make a figure.
    Send a key_press_event event (using non-public, qtX backend specific api).
    Catch the event.
    Assert sent and caught keys are the same.
    """
    from matplotlib.backends.qt_compat import _to_int, QtCore

    if sys.platform == "darwin" and answer is not None:
        answer = answer.replace("ctrl", "cmd")
        answer = answer.replace("control", "cmd")
        answer = answer.replace("meta", "ctrl")
    result = None
    qt_mod = QtCore.Qt.KeyboardModifier.NoModifier
    for mod in qt_mods:
        qt_mod |= getattr(QtCore.Qt.KeyboardModifier, mod)

    class _Event:
        def isAutoRepeat(self): return False
        def key(self): return _to_int(getattr(QtCore.Qt.Key, qt_key))

    monkeypatch.setattr(QtWidgets.QApplication, "keyboardModifiers",
                        lambda self: qt_mod)

    def on_key_press(event):
        nonlocal result
        result = event.key

    qt_canvas = plt.figure().canvas
    qt_canvas.mpl_connect('key_press_event', on_key_press)
    qt_canvas.keyPressEvent(_Event())
    assert result == answer


@pytest.mark.backend('QtAgg', skip_on_importerror=True)
def test_device_pixel_ratio_change(qt_core):
    """
    Make sure that if the pixel ratio changes, the figure dpi changes but the
    widget remains the same logical size.
    """

    prop = 'matplotlib.backends.backend_qt.FigureCanvasQT.devicePixelRatioF'
    with mock.patch(prop) as p:
        p.return_value = 3

        fig = plt.figure(figsize=(5, 2), dpi=120)
        qt_canvas = fig.canvas
        qt_canvas.show()

        def set_device_pixel_ratio(ratio):
            p.return_value = ratio

            window = qt_canvas.window().windowHandle()
            current_version = tuple(
                int(x) for x in qt_core.qVersion().split('.', 2)[:2])
            if current_version >= (6, 6):
                qt_core.QCoreApplication.sendEvent(
                    window,
                    qt_core.QEvent(qt_core.QEvent.Type.DevicePixelRatioChange))
            else:
                # The value here doesn't matter, as we can't mock the C++ QScreen
                # object, but can override the functional wrapper around it.
                # Emitting this event is simply to trigger the DPI change handler
                # in Matplotlib in the same manner that it would occur normally.
                window.screen().logicalDotsPerInchChanged.emit(96)

            qt_canvas.draw()
            qt_canvas.flush_events()

            # Make sure the mocking worked
            assert qt_canvas.device_pixel_ratio == ratio

        qt_canvas.manager.show()
        qt_canvas.draw()
        qt_canvas.flush_events()
        size = qt_canvas.size()

        options = [
            (None, 360, 1800, 720),  # Use ratio at startup time.
            (3, 360, 1800, 720),  # Change to same ratio.
            (2, 240, 1200, 480),  # Change to different ratio.
            (1.5, 180, 900, 360),  # Fractional ratio.
        ]
        for ratio, dpi, width, height in options:
            if ratio is not None:
                set_device_pixel_ratio(ratio)

            # The DPI and the renderer width/height change
            assert fig.dpi == dpi
            assert qt_canvas.renderer.width == width
            assert qt_canvas.renderer.height == height

            # The actual widget size and figure logical size don't change.
            assert size.width() == 600
            assert size.height() == 240
            assert qt_canvas.get_width_height() == (600, 240)
            assert (fig.get_size_inches() == (5, 2)).all()


@pytest.mark.backend('QtAgg', skip_on_importerror=True)
def test_subplottool():
    fig, ax = plt.subplots()
    with mock.patch("matplotlib.backends.qt_compat._exec", lambda obj: None):
        fig.canvas.manager.toolbar.configure_subplots()


@pytest.mark.backend('QtAgg', skip_on_importerror=True)
def test_figureoptions():
    fig, ax = plt.subplots()
    ax.plot([1, 2])
    ax.imshow([[1]])
    ax.scatter(range(3), range(3), c=range(3))
    with mock.patch("matplotlib.backends.qt_compat._exec", lambda obj: None):
        fig.canvas.manager.toolbar.edit_parameters()


@pytest.mark.backend('QtAgg', skip_on_importerror=True)
def test_save_figure_return(tmp_path):
    fig, ax = plt.subplots()
    ax.imshow([[1]])
    expected = tmp_path / "foobar.png"
    prop = "matplotlib.backends.qt_compat.QtWidgets.QFileDialog.getSaveFileName"
    with mock.patch(prop, return_value=(str(expected), None)):
        fname = fig.canvas.manager.toolbar.save_figure()
        assert fname == str(expected)
        assert expected.exists()
    with mock.patch(prop, return_value=(None, None)):
        fname = fig.canvas.manager.toolbar.save_figure()
        assert fname is None


@pytest.mark.backend('QtAgg', skip_on_importerror=True)
def test_figureoptions_with_datetime_axes():
    fig, ax = plt.subplots()
    xydata = [
        datetime(year=2021, month=1, day=1),
        datetime(year=2021, month=2, day=1)
    ]
    ax.plot(xydata, xydata)
    with mock.patch("matplotlib.backends.qt_compat._exec", lambda obj: None):
        fig.canvas.manager.toolbar.edit_parameters()


@pytest.mark.backend('QtAgg', skip_on_importerror=True)
def test_double_resize():
    # Check that resizing a figure twice keeps the same window size
    fig, ax = plt.subplots()
    fig.canvas.draw()
    window = fig.canvas.manager.window

    w, h = 3, 2
    fig.set_size_inches(w, h)
    assert fig.canvas.width() == w * matplotlib.rcParams['figure.dpi']
    assert fig.canvas.height() == h * matplotlib.rcParams['figure.dpi']

    old_width = window.width()
    old_height = window.height()

    fig.set_size_inches(w, h)
    assert window.width() == old_width
    assert window.height() == old_height


@pytest.mark.backend('QtAgg', skip_on_importerror=True)
def test_canvas_reinit():
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

    called = False

    def crashing_callback(fig, stale):
        nonlocal called
        fig.canvas.draw_idle()
        called = True

    fig, ax = plt.subplots()
    fig.stale_callback = crashing_callback
    # this should not raise
    canvas = FigureCanvasQTAgg(fig)
    fig.stale = True
    assert called


@pytest.mark.backend('Qt5Agg', skip_on_importerror=True)
def test_form_widget_get_with_datetime_and_date_fields():
    from matplotlib.backends.backend_qt import _create_qApp
    _create_qApp()

    form = [
        ("Datetime field", datetime(year=2021, month=3, day=11)),
        ("Date field", date(year=2021, month=3, day=11))
    ]
    widget = _formlayout.FormWidget(form)
    widget.setup()
    values = widget.get()
    assert values == [
        datetime(year=2021, month=3, day=11),
        date(year=2021, month=3, day=11)
    ]


def _get_testable_qt_backends():
    envs = []
    for deps, env in [
            ([qt_api], {"MPLBACKEND": "qtagg", "QT_API": qt_api})
            for qt_api in ["PyQt6", "PySide6", "PyQt5", "PySide2"]
    ]:
        reason = None
        missing = [dep for dep in deps if not importlib.util.find_spec(dep)]
        if (sys.platform == "linux" and
                not _c_internal_utils.display_is_valid()):
            reason = "$DISPLAY and $WAYLAND_DISPLAY are unset"
        elif missing:
            reason = "{} cannot be imported".format(", ".join(missing))
        elif env["MPLBACKEND"] == 'macosx' and os.environ.get('TF_BUILD'):
            reason = "macosx backend fails on Azure"
        marks = []
        if reason:
            marks.append(pytest.mark.skip(
                reason=f"Skipping {env} because {reason}"))
        envs.append(pytest.param(env, marks=marks, id=str(env)))
    return envs


@pytest.mark.backend('QtAgg', skip_on_importerror=True)
def test_fig_sigint_override(qt_core):
    from matplotlib.backends.backend_qt5 import _BackendQT5
    # Create a figure
    plt.figure()

    # Variable to access the handler from the inside of the event loop
    event_loop_handler = None

    # Callback to fire during event loop: save SIGINT handler, then exit
    def fire_signal_and_quit():
        # Save event loop signal
        nonlocal event_loop_handler
        event_loop_handler = signal.getsignal(signal.SIGINT)

        # Request event loop exit
        qt_core.QCoreApplication.exit()

    # Timer to exit event loop
    qt_core.QTimer.singleShot(0, fire_signal_and_quit)

    # Save original SIGINT handler
    original_handler = signal.getsignal(signal.SIGINT)

    # Use our own SIGINT handler to be 100% sure this is working
    def custom_handler(signum, frame):
        pass

    signal.signal(signal.SIGINT, custom_handler)

    try:
        # mainloop() sets SIGINT, starts Qt event loop (which triggers timer
        # and exits) and then mainloop() resets SIGINT
        matplotlib.backends.backend_qt._BackendQT.mainloop()

        # Assert: signal handler during loop execution is changed
        # (can't test equality with func)
        assert event_loop_handler != custom_handler

        # Assert: current signal handler is the same as the one we set before
        assert signal.getsignal(signal.SIGINT) == custom_handler

        # Repeat again to test that SIG_DFL and SIG_IGN will not be overridden
        for custom_handler in (signal.SIG_DFL, signal.SIG_IGN):
            qt_core.QTimer.singleShot(0, fire_signal_and_quit)
            signal.signal(signal.SIGINT, custom_handler)

            _BackendQT5.mainloop()

            assert event_loop_handler == custom_handler
            assert signal.getsignal(signal.SIGINT) == custom_handler

    finally:
        # Reset SIGINT handler to what it was before the test
        signal.signal(signal.SIGINT, original_handler)


@pytest.mark.backend('QtAgg', skip_on_importerror=True)
def test_ipython():
    from matplotlib.testing import ipython_in_subprocess
    ipython_in_subprocess("qt", {(8, 24): "qtagg", (8, 15): "QtAgg", (7, 0): "Qt5Agg"})
