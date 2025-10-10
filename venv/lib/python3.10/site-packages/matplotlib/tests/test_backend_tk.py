import functools
import importlib
import os
import platform
import subprocess
import sys

import pytest

from matplotlib import _c_internal_utils
from matplotlib.testing import subprocess_run_helper


_test_timeout = 60  # A reasonably safe value for slower architectures.


def _isolated_tk_test(success_count, func=None):
    """
    A decorator to run *func* in a subprocess and assert that it prints
    "success" *success_count* times and nothing on stderr.

    TkAgg tests seem to have interactions between tests, so isolate each test
    in a subprocess. See GH#18261
    """

    if func is None:
        return functools.partial(_isolated_tk_test, success_count)

    if "MPL_TEST_ESCAPE_HATCH" in os.environ:
        # set in subprocess_run_helper() below
        return func

    @pytest.mark.skipif(
        not importlib.util.find_spec('tkinter'),
        reason="missing tkinter"
    )
    @pytest.mark.skipif(
        sys.platform == "linux" and not _c_internal_utils.xdisplay_is_valid(),
        reason="$DISPLAY is unset"
    )
    @pytest.mark.xfail(  # https://github.com/actions/setup-python/issues/649
        ('TF_BUILD' in os.environ or 'GITHUB_ACTION' in os.environ) and
        sys.platform == 'darwin' and sys.version_info[:2] < (3, 11),
        reason='Tk version mismatch on Azure macOS CI'
    )
    @functools.wraps(func)
    def test_func():
        # even if the package exists, may not actually be importable this can
        # be the case on some CI systems.
        pytest.importorskip('tkinter')
        try:
            proc = subprocess_run_helper(
                func, timeout=_test_timeout, extra_env=dict(
                    MPLBACKEND="TkAgg", MPL_TEST_ESCAPE_HATCH="1"))
        except subprocess.TimeoutExpired:
            pytest.fail("Subprocess timed out")
        except subprocess.CalledProcessError as e:
            pytest.fail("Subprocess failed to test intended behavior\n"
                        + str(e.stderr))
        else:
            # macOS may actually emit irrelevant errors about Accelerated
            # OpenGL vs. software OpenGL, or some permission error on Azure, so
            # suppress them.
            # Asserting stderr first (and printing it on failure) should be
            # more helpful for debugging that printing a failed success count.
            ignored_lines = ["OpenGL", "CFMessagePort: bootstrap_register",
                             "/usr/include/servers/bootstrap_defs.h"]
            assert not [line for line in proc.stderr.splitlines()
                        if all(msg not in line for msg in ignored_lines)]
            assert proc.stdout.count("success") == success_count

    return test_func


@_isolated_tk_test(success_count=6)  # len(bad_boxes)
def test_blit():
    import matplotlib.pyplot as plt
    import numpy as np
    import matplotlib.backends.backend_tkagg  # noqa
    from matplotlib.backends import _backend_tk, _tkagg

    fig, ax = plt.subplots()
    photoimage = fig.canvas._tkphoto
    data = np.ones((4, 4, 4), dtype=np.uint8)
    # Test out of bounds blitting.
    bad_boxes = ((-1, 2, 0, 2),
                 (2, 0, 0, 2),
                 (1, 6, 0, 2),
                 (0, 2, -1, 2),
                 (0, 2, 2, 0),
                 (0, 2, 1, 6))
    for bad_box in bad_boxes:
        try:
            _tkagg.blit(
                photoimage.tk.interpaddr(), str(photoimage), data,
                _tkagg.TK_PHOTO_COMPOSITE_OVERLAY, (0, 1, 2, 3), bad_box)
        except ValueError:
            print("success")

    # Test blitting to a destroyed canvas.
    plt.close(fig)
    _backend_tk.blit(photoimage, data, (0, 1, 2, 3))


@_isolated_tk_test(success_count=1)
def test_figuremanager_preserves_host_mainloop():
    import tkinter
    import matplotlib.pyplot as plt
    success = []

    def do_plot():
        plt.figure()
        plt.plot([1, 2], [3, 5])
        plt.close()
        root.after(0, legitimate_quit)

    def legitimate_quit():
        root.quit()
        success.append(True)

    root = tkinter.Tk()
    root.after(0, do_plot)
    root.mainloop()

    if success:
        print("success")


@pytest.mark.skipif(platform.python_implementation() != 'CPython',
                    reason='PyPy does not support Tkinter threading: '
                           'https://foss.heptapod.net/pypy/pypy/-/issues/1929')
@pytest.mark.flaky(reruns=3)
@_isolated_tk_test(success_count=1)
def test_figuremanager_cleans_own_mainloop():
    import tkinter
    import time
    import matplotlib.pyplot as plt
    import threading
    from matplotlib.cbook import _get_running_interactive_framework

    root = tkinter.Tk()
    plt.plot([1, 2, 3], [1, 2, 5])

    def target():
        while not 'tk' == _get_running_interactive_framework():
            time.sleep(.01)
        plt.close()
        if show_finished_event.wait():
            print('success')

    show_finished_event = threading.Event()
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    plt.show(block=True)  # Testing if this function hangs.
    show_finished_event.set()
    thread.join()


@pytest.mark.flaky(reruns=3)
@_isolated_tk_test(success_count=0)
def test_never_update():
    import tkinter
    del tkinter.Misc.update
    del tkinter.Misc.update_idletasks

    import matplotlib.pyplot as plt
    fig = plt.figure()
    plt.show(block=False)

    plt.draw()  # Test FigureCanvasTkAgg.
    fig.canvas.toolbar.configure_subplots()  # Test NavigationToolbar2Tk.
    # Test FigureCanvasTk filter_destroy callback
    fig.canvas.get_tk_widget().after(100, plt.close, fig)

    # Check for update() or update_idletasks() in the event queue, functionally
    # equivalent to tkinter.Misc.update.
    plt.show(block=True)

    # Note that exceptions would be printed to stderr; _isolated_tk_test
    # checks them.


@_isolated_tk_test(success_count=2)
def test_missing_back_button():
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk

    class Toolbar(NavigationToolbar2Tk):
        # Only display the buttons we need.
        toolitems = [t for t in NavigationToolbar2Tk.toolitems if
                     t[0] in ('Home', 'Pan', 'Zoom')]

    fig = plt.figure()
    print("success")
    Toolbar(fig.canvas, fig.canvas.manager.window)  # This should not raise.
    print("success")


@_isolated_tk_test(success_count=2)
def test_save_figure_return():
    import matplotlib.pyplot as plt
    from unittest import mock
    fig = plt.figure()
    prop = "tkinter.filedialog.asksaveasfilename"
    with mock.patch(prop, return_value="foobar.png"):
        fname = fig.canvas.manager.toolbar.save_figure()
        os.remove("foobar.png")
        assert fname == "foobar.png"
        print("success")
    with mock.patch(prop, return_value=""):
        fname = fig.canvas.manager.toolbar.save_figure()
        assert fname is None
        print("success")


@_isolated_tk_test(success_count=1)
def test_canvas_focus():
    import tkinter as tk
    import matplotlib.pyplot as plt
    success = []

    def check_focus():
        tkcanvas = fig.canvas.get_tk_widget()
        # Give the plot window time to appear
        if not tkcanvas.winfo_viewable():
            tkcanvas.wait_visibility()
        # Make sure the canvas has the focus, so that it's able to receive
        # keyboard events.
        if tkcanvas.focus_lastfor() == tkcanvas:
            success.append(True)
        plt.close()
        root.destroy()

    root = tk.Tk()
    fig = plt.figure()
    plt.plot([1, 2, 3])
    root.after(0, plt.show)
    root.after(100, check_focus)
    root.mainloop()

    if success:
        print("success")


@_isolated_tk_test(success_count=2)
def test_embedding():
    import tkinter as tk
    from matplotlib.backends.backend_tkagg import (
        FigureCanvasTkAgg, NavigationToolbar2Tk)
    from matplotlib.backend_bases import key_press_handler
    from matplotlib.figure import Figure

    root = tk.Tk()

    def test_figure(master):
        fig = Figure()
        ax = fig.add_subplot()
        ax.plot([1, 2, 3])

        canvas = FigureCanvasTkAgg(fig, master=master)
        canvas.draw()
        canvas.mpl_connect("key_press_event", key_press_handler)
        canvas.get_tk_widget().pack(expand=True, fill="both")

        toolbar = NavigationToolbar2Tk(canvas, master, pack_toolbar=False)
        toolbar.pack(expand=True, fill="x")

        canvas.get_tk_widget().forget()
        toolbar.forget()

    test_figure(root)
    print("success")

    # Test with a dark button color. Doesn't actually check whether the icon
    # color becomes lighter, just that the code doesn't break.

    root.tk_setPalette(background="sky blue", selectColor="midnight blue",
                       foreground="white")
    test_figure(root)
    print("success")
