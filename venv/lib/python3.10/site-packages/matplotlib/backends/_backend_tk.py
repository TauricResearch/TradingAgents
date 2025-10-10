import uuid
import weakref
from contextlib import contextmanager
import logging
import math
import os.path
import pathlib
import sys
import tkinter as tk
import tkinter.filedialog
import tkinter.font
import tkinter.messagebox
from tkinter.simpledialog import SimpleDialog

import numpy as np
from PIL import Image, ImageTk

import matplotlib as mpl
from matplotlib import _api, backend_tools, cbook, _c_internal_utils
from matplotlib.backend_bases import (
    _Backend, FigureCanvasBase, FigureManagerBase, NavigationToolbar2,
    TimerBase, ToolContainerBase, cursors, _Mode, MouseButton,
    CloseEvent, KeyEvent, LocationEvent, MouseEvent, ResizeEvent)
from matplotlib._pylab_helpers import Gcf

try:
    from . import _tkagg
    from ._tkagg import TK_PHOTO_COMPOSITE_OVERLAY, TK_PHOTO_COMPOSITE_SET
except ImportError as e:
    # catch incompatibility of python-build-standalone with Tk
    cause1 = getattr(e, '__cause__', None)
    cause2 = getattr(cause1, '__cause__', None)
    if (isinstance(cause1, ImportError) and
            isinstance(cause2, AttributeError) and
            "'_tkinter' has no attribute '__file__'" in str(cause2)):

        is_uv_python = "/uv/python" in (os.path.realpath(sys.executable))
        if is_uv_python:
            raise ImportError(
                "Failed to import tkagg backend. You appear to be using an outdated "
                "version of uv's managed Python distribution which is not compatible "
                "with Tk. Please upgrade to the latest uv version, then update "
                "Python with: `uv python upgrade --reinstall`"
                ) from e
        else:
            raise ImportError(
                "Failed to import tkagg backend. This is likely caused by using a "
                "Python executable based on python-build-standalone, which is not "
                "compatible with Tk. Recent versions of python-build-standalone "
                "should be compatible with Tk. Please update your python version "
                "or select another backend."
                ) from e
    else:
        raise


_log = logging.getLogger(__name__)
cursord = {
    cursors.MOVE: "fleur",
    cursors.HAND: "hand2",
    cursors.POINTER: "arrow",
    cursors.SELECT_REGION: "crosshair",
    cursors.WAIT: "watch",
    cursors.RESIZE_HORIZONTAL: "sb_h_double_arrow",
    cursors.RESIZE_VERTICAL: "sb_v_double_arrow",
}


@contextmanager
def _restore_foreground_window_at_end():
    foreground = _c_internal_utils.Win32_GetForegroundWindow()
    try:
        yield
    finally:
        if foreground and mpl.rcParams['tk.window_focus']:
            _c_internal_utils.Win32_SetForegroundWindow(foreground)


_blit_args = {}
# Initialize to a non-empty string that is not a Tcl command
_blit_tcl_name = "mpl_blit_" + uuid.uuid4().hex


def _blit(argsid):
    """
    Thin wrapper to blit called via tkapp.call.

    *argsid* is a unique string identifier to fetch the correct arguments from
    the ``_blit_args`` dict, since arguments cannot be passed directly.
    """
    photoimage, data, offsets, bbox, comp_rule = _blit_args.pop(argsid)
    if not photoimage.tk.call("info", "commands", photoimage):
        return
    _tkagg.blit(photoimage.tk.interpaddr(), str(photoimage), data, comp_rule, offsets,
                bbox)


def blit(photoimage, aggimage, offsets, bbox=None):
    """
    Blit *aggimage* to *photoimage*.

    *offsets* is a tuple describing how to fill the ``offset`` field of the
    ``Tk_PhotoImageBlock`` struct: it should be (0, 1, 2, 3) for RGBA8888 data,
    (2, 1, 0, 3) for little-endian ARBG32 (i.e. GBRA8888) data and (1, 2, 3, 0)
    for big-endian ARGB32 (i.e. ARGB8888) data.

    If *bbox* is passed, it defines the region that gets blitted. That region
    will be composed with the previous data according to the alpha channel.
    Blitting will be clipped to pixels inside the canvas, including silently
    doing nothing if the *bbox* region is entirely outside the canvas.

    Tcl events must be dispatched to trigger a blit from a non-Tcl thread.
    """
    data = np.asarray(aggimage)
    height, width = data.shape[:2]
    if bbox is not None:
        (x1, y1), (x2, y2) = bbox.__array__()
        x1 = max(math.floor(x1), 0)
        x2 = min(math.ceil(x2), width)
        y1 = max(math.floor(y1), 0)
        y2 = min(math.ceil(y2), height)
        if (x1 > x2) or (y1 > y2):
            return
        bboxptr = (x1, x2, y1, y2)
        comp_rule = TK_PHOTO_COMPOSITE_OVERLAY
    else:
        bboxptr = (0, width, 0, height)
        comp_rule = TK_PHOTO_COMPOSITE_SET

    # NOTE: _tkagg.blit is thread unsafe and will crash the process if called
    # from a thread (GH#13293). Instead of blanking and blitting here,
    # use tkapp.call to post a cross-thread event if this function is called
    # from a non-Tcl thread.

    # tkapp.call coerces all arguments to strings, so to avoid string parsing
    # within _blit, pack up the arguments into a global data structure.
    args = photoimage, data, offsets, bboxptr, comp_rule
    # Need a unique key to avoid thread races.
    # Again, make the key a string to avoid string parsing in _blit.
    argsid = str(id(args))
    _blit_args[argsid] = args

    try:
        photoimage.tk.call(_blit_tcl_name, argsid)
    except tk.TclError as e:
        if "invalid command name" not in str(e):
            raise
        photoimage.tk.createcommand(_blit_tcl_name, _blit)
        photoimage.tk.call(_blit_tcl_name, argsid)


class TimerTk(TimerBase):
    """Subclass of `backend_bases.TimerBase` using Tk timer events."""

    def __init__(self, parent, *args, **kwargs):
        self._timer = None
        super().__init__(*args, **kwargs)
        self.parent = parent

    def _timer_start(self):
        self._timer_stop()
        self._timer = self.parent.after(self._interval, self._on_timer)

    def _timer_stop(self):
        if self._timer is not None:
            self.parent.after_cancel(self._timer)
        self._timer = None

    def _on_timer(self):
        super()._on_timer()
        # Tk after() is only a single shot, so we need to add code here to
        # reset the timer if we're not operating in single shot mode.  However,
        # if _timer is None, this means that _timer_stop has been called; so
        # don't recreate the timer in that case.
        if not self._single and self._timer:
            if self._interval > 0:
                self._timer = self.parent.after(self._interval, self._on_timer)
            else:
                # Edge case: Tcl after 0 *prepends* events to the queue
                # so a 0 interval does not allow any other events to run.
                # This incantation is cancellable and runs as fast as possible
                # while also allowing events and drawing every frame. GH#18236
                self._timer = self.parent.after_idle(
                    lambda: self.parent.after(self._interval, self._on_timer)
                )
        else:
            self._timer = None


class FigureCanvasTk(FigureCanvasBase):
    required_interactive_framework = "tk"
    manager_class = _api.classproperty(lambda cls: FigureManagerTk)

    def __init__(self, figure=None, master=None):
        super().__init__(figure)
        self._idle_draw_id = None
        self._event_loop_id = None
        w, h = self.get_width_height(physical=True)
        self._tkcanvas = tk.Canvas(
            master=master, background="white",
            width=w, height=h, borderwidth=0, highlightthickness=0)
        self._tkphoto = tk.PhotoImage(
            master=self._tkcanvas, width=w, height=h)
        self._tkcanvas_image_region = self._tkcanvas.create_image(
            w//2, h//2, image=self._tkphoto)
        self._tkcanvas.bind("<Configure>", self.resize)
        self._tkcanvas.bind("<Map>", self._update_device_pixel_ratio)
        self._tkcanvas.bind("<Key>", self.key_press)
        self._tkcanvas.bind("<Motion>", self.motion_notify_event)
        self._tkcanvas.bind("<Enter>", self.enter_notify_event)
        self._tkcanvas.bind("<Leave>", self.leave_notify_event)
        self._tkcanvas.bind("<KeyRelease>", self.key_release)
        for name in ["<Button-1>", "<Button-2>", "<Button-3>"]:
            self._tkcanvas.bind(name, self.button_press_event)
        for name in [
                "<Double-Button-1>", "<Double-Button-2>", "<Double-Button-3>"]:
            self._tkcanvas.bind(name, self.button_dblclick_event)
        for name in [
                "<ButtonRelease-1>", "<ButtonRelease-2>", "<ButtonRelease-3>"]:
            self._tkcanvas.bind(name, self.button_release_event)

        # Mouse wheel on Linux generates button 4/5 events
        for name in "<Button-4>", "<Button-5>":
            self._tkcanvas.bind(name, self.scroll_event)
        # Mouse wheel for windows goes to the window with the focus.
        # Since the canvas won't usually have the focus, bind the
        # event to the window containing the canvas instead.
        # See https://wiki.tcl-lang.org/3893 (mousewheel) for details
        root = self._tkcanvas.winfo_toplevel()

        # Prevent long-lived references via tkinter callback structure GH-24820
        weakself = weakref.ref(self)
        weakroot = weakref.ref(root)

        def scroll_event_windows(event):
            self = weakself()
            if self is None:
                root = weakroot()
                if root is not None:
                    root.unbind("<MouseWheel>", scroll_event_windows_id)
                return
            return self.scroll_event_windows(event)
        scroll_event_windows_id = root.bind("<MouseWheel>", scroll_event_windows, "+")

        # Can't get destroy events by binding to _tkcanvas. Therefore, bind
        # to the window and filter.
        def filter_destroy(event):
            self = weakself()
            if self is None:
                root = weakroot()
                if root is not None:
                    root.unbind("<Destroy>", filter_destroy_id)
                return
            if event.widget is self._tkcanvas:
                CloseEvent("close_event", self)._process()
        filter_destroy_id = root.bind("<Destroy>", filter_destroy, "+")

        self._tkcanvas.focus_set()

        self._rubberband_rect_black = None
        self._rubberband_rect_white = None

    def _update_device_pixel_ratio(self, event=None):
        ratio = None
        if sys.platform == 'win32':
            # Tk gives scaling with respect to 72 DPI, but Windows screens are
            # scaled vs 96 dpi, and pixel ratio settings are given in whole
            # percentages, so round to 2 digits.
            ratio = round(self._tkcanvas.tk.call('tk', 'scaling') / (96 / 72), 2)
        elif sys.platform == "linux":
            ratio = self._tkcanvas.winfo_fpixels('1i') / 96
        if ratio is not None and self._set_device_pixel_ratio(ratio):
            # The easiest way to resize the canvas is to resize the canvas
            # widget itself, since we implement all the logic for resizing the
            # canvas backing store on that event.
            w, h = self.get_width_height(physical=True)
            self._tkcanvas.configure(width=w, height=h)

    def resize(self, event):
        width, height = event.width, event.height

        # compute desired figure size in inches
        dpival = self.figure.dpi
        winch = width / dpival
        hinch = height / dpival
        self.figure.set_size_inches(winch, hinch, forward=False)

        self._tkcanvas.delete(self._tkcanvas_image_region)
        self._tkphoto.configure(width=int(width), height=int(height))
        self._tkcanvas_image_region = self._tkcanvas.create_image(
            int(width / 2), int(height / 2), image=self._tkphoto)
        ResizeEvent("resize_event", self)._process()
        self.draw_idle()

    def draw_idle(self):
        # docstring inherited
        if self._idle_draw_id:
            return

        def idle_draw(*args):
            try:
                self.draw()
            finally:
                self._idle_draw_id = None

        self._idle_draw_id = self._tkcanvas.after_idle(idle_draw)

    def get_tk_widget(self):
        """
        Return the Tk widget used to implement FigureCanvasTkAgg.

        Although the initial implementation uses a Tk canvas,  this routine
        is intended to hide that fact.
        """
        return self._tkcanvas

    def _event_mpl_coords(self, event):
        # calling canvasx/canvasy allows taking scrollbars into account (i.e.
        # the top of the widget may have been scrolled out of view).
        return (self._tkcanvas.canvasx(event.x),
                # flipy so y=0 is bottom of canvas
                self.figure.bbox.height - self._tkcanvas.canvasy(event.y))

    def motion_notify_event(self, event):
        MouseEvent("motion_notify_event", self,
                   *self._event_mpl_coords(event),
                   buttons=self._mpl_buttons(event),
                   modifiers=self._mpl_modifiers(event),
                   guiEvent=event)._process()

    def enter_notify_event(self, event):
        LocationEvent("figure_enter_event", self,
                      *self._event_mpl_coords(event),
                      modifiers=self._mpl_modifiers(event),
                      guiEvent=event)._process()

    def leave_notify_event(self, event):
        LocationEvent("figure_leave_event", self,
                      *self._event_mpl_coords(event),
                      modifiers=self._mpl_modifiers(event),
                      guiEvent=event)._process()

    def button_press_event(self, event, dblclick=False):
        # set focus to the canvas so that it can receive keyboard events
        self._tkcanvas.focus_set()

        num = getattr(event, 'num', None)
        if sys.platform == 'darwin':  # 2 and 3 are reversed.
            num = {2: 3, 3: 2}.get(num, num)
        MouseEvent("button_press_event", self,
                   *self._event_mpl_coords(event), num, dblclick=dblclick,
                   modifiers=self._mpl_modifiers(event),
                   guiEvent=event)._process()

    def button_dblclick_event(self, event):
        self.button_press_event(event, dblclick=True)

    def button_release_event(self, event):
        num = getattr(event, 'num', None)
        if sys.platform == 'darwin':  # 2 and 3 are reversed.
            num = {2: 3, 3: 2}.get(num, num)
        MouseEvent("button_release_event", self,
                   *self._event_mpl_coords(event), num,
                   modifiers=self._mpl_modifiers(event),
                   guiEvent=event)._process()

    def scroll_event(self, event):
        num = getattr(event, 'num', None)
        step = 1 if num == 4 else -1 if num == 5 else 0
        MouseEvent("scroll_event", self,
                   *self._event_mpl_coords(event), step=step,
                   modifiers=self._mpl_modifiers(event),
                   guiEvent=event)._process()

    def scroll_event_windows(self, event):
        """MouseWheel event processor"""
        # need to find the window that contains the mouse
        w = event.widget.winfo_containing(event.x_root, event.y_root)
        if w != self._tkcanvas:
            return
        x = self._tkcanvas.canvasx(event.x_root - w.winfo_rootx())
        y = (self.figure.bbox.height
             - self._tkcanvas.canvasy(event.y_root - w.winfo_rooty()))
        step = event.delta / 120
        MouseEvent("scroll_event", self,
                   x, y, step=step, modifiers=self._mpl_modifiers(event),
                   guiEvent=event)._process()

    @staticmethod
    def _mpl_buttons(event):  # See _mpl_modifiers.
        # NOTE: This fails to report multiclicks on macOS; only one button is
        # reported (multiclicks work correctly on Linux & Windows).
        modifiers = [
            # macOS appears to swap right and middle (look for "Swap buttons
            # 2/3" in tk/macosx/tkMacOSXMouseEvent.c).
            (MouseButton.LEFT, 1 << 8),
            (MouseButton.RIGHT, 1 << 9),
            (MouseButton.MIDDLE, 1 << 10),
            (MouseButton.BACK, 1 << 11),
            (MouseButton.FORWARD, 1 << 12),
        ] if sys.platform == "darwin" else [
            (MouseButton.LEFT, 1 << 8),
            (MouseButton.MIDDLE, 1 << 9),
            (MouseButton.RIGHT, 1 << 10),
            (MouseButton.BACK, 1 << 11),
            (MouseButton.FORWARD, 1 << 12),
        ]
        # State *before* press/release.
        return [name for name, mask in modifiers if event.state & mask]

    @staticmethod
    def _mpl_modifiers(event, *, exclude=None):
        # Add modifier keys to the key string. Bit values are inferred from
        # the implementation of tkinter.Event.__repr__ (1, 2, 4, 8, ... =
        # Shift, Lock, Control, Mod1, ..., Mod5, Button1, ..., Button5)
        # In general, the modifier key is excluded from the modifier flag,
        # however this is not the case on "darwin", so double check that
        # we aren't adding repeat modifier flags to a modifier key.
        modifiers = [
            ("ctrl", 1 << 2, "control"),
            ("alt", 1 << 17, "alt"),
            ("shift", 1 << 0, "shift"),
        ] if sys.platform == "win32" else [
            ("ctrl", 1 << 2, "control"),
            ("alt", 1 << 4, "alt"),
            ("shift", 1 << 0, "shift"),
            ("cmd", 1 << 3, "cmd"),
        ] if sys.platform == "darwin" else [
            ("ctrl", 1 << 2, "control"),
            ("alt", 1 << 3, "alt"),
            ("shift", 1 << 0, "shift"),
            ("super", 1 << 6, "super"),
        ]
        return [name for name, mask, key in modifiers
                if event.state & mask and exclude != key]

    def _get_key(self, event):
        unikey = event.char
        key = cbook._unikey_or_keysym_to_mplkey(unikey, event.keysym)
        if key is not None:
            mods = self._mpl_modifiers(event, exclude=key)
            # shift is not added to the keys as this is already accounted for.
            if "shift" in mods and unikey:
                mods.remove("shift")
            return "+".join([*mods, key])

    def key_press(self, event):
        KeyEvent("key_press_event", self,
                 self._get_key(event), *self._event_mpl_coords(event),
                 guiEvent=event)._process()

    def key_release(self, event):
        KeyEvent("key_release_event", self,
                 self._get_key(event), *self._event_mpl_coords(event),
                 guiEvent=event)._process()

    def new_timer(self, *args, **kwargs):
        # docstring inherited
        return TimerTk(self._tkcanvas, *args, **kwargs)

    def flush_events(self):
        # docstring inherited
        self._tkcanvas.update()

    def start_event_loop(self, timeout=0):
        # docstring inherited
        if timeout > 0:
            milliseconds = int(1000 * timeout)
            if milliseconds > 0:
                self._event_loop_id = self._tkcanvas.after(
                    milliseconds, self.stop_event_loop)
            else:
                self._event_loop_id = self._tkcanvas.after_idle(
                    self.stop_event_loop)
        self._tkcanvas.mainloop()

    def stop_event_loop(self):
        # docstring inherited
        if self._event_loop_id:
            self._tkcanvas.after_cancel(self._event_loop_id)
            self._event_loop_id = None
        self._tkcanvas.quit()

    def set_cursor(self, cursor):
        try:
            self._tkcanvas.configure(cursor=cursord[cursor])
        except tkinter.TclError:
            pass


class FigureManagerTk(FigureManagerBase):
    """
    Attributes
    ----------
    canvas : `FigureCanvas`
        The FigureCanvas instance
    num : int or str
        The Figure number
    toolbar : tk.Toolbar
        The tk.Toolbar
    window : tk.Window
        The tk.Window
    """

    _owns_mainloop = False

    def __init__(self, canvas, num, window):
        self.window = window
        super().__init__(canvas, num)
        self.window.withdraw()
        # packing toolbar first, because if space is getting low, last packed
        # widget is getting shrunk first (-> the canvas)
        self.canvas._tkcanvas.pack(side=tk.TOP, fill=tk.BOTH, expand=1)

        # If the window has per-monitor DPI awareness, then setup a Tk variable
        # to store the DPI, which will be updated by the C code, and the trace
        # will handle it on the Python side.
        window_frame = int(window.wm_frame(), 16)
        self._window_dpi = tk.IntVar(master=window, value=96,
                                     name=f'window_dpi{window_frame}')
        self._window_dpi_cbname = ''
        if _tkagg.enable_dpi_awareness(window_frame, window.tk.interpaddr()):
            self._window_dpi_cbname = self._window_dpi.trace_add(
                'write', self._update_window_dpi)

        self._shown = False

    @classmethod
    def create_with_canvas(cls, canvas_class, figure, num):
        # docstring inherited
        with _restore_foreground_window_at_end():
            if cbook._get_running_interactive_framework() is None:
                cbook._setup_new_guiapp()
                _c_internal_utils.Win32_SetProcessDpiAwareness_max()
            window = tk.Tk(className="matplotlib")
            window.withdraw()

            # Put a Matplotlib icon on the window rather than the default tk
            # icon. See https://www.tcl.tk/man/tcl/TkCmd/wm.html#M50
            #
            # `ImageTk` can be replaced with `tk` whenever the minimum
            # supported Tk version is increased to 8.6, as Tk 8.6+ natively
            # supports PNG images.
            icon_fname = str(cbook._get_data_path(
                'images/matplotlib.png'))
            icon_img = ImageTk.PhotoImage(file=icon_fname, master=window)

            icon_fname_large = str(cbook._get_data_path(
                'images/matplotlib_large.png'))
            icon_img_large = ImageTk.PhotoImage(
                file=icon_fname_large, master=window)

            window.iconphoto(False, icon_img_large, icon_img)

            canvas = canvas_class(figure, master=window)
            manager = cls(canvas, num, window)
            if mpl.is_interactive():
                manager.show()
                canvas.draw_idle()
            return manager

    @classmethod
    def start_main_loop(cls):
        managers = Gcf.get_all_fig_managers()
        if managers:
            first_manager = managers[0]
            manager_class = type(first_manager)
            if manager_class._owns_mainloop:
                return
            manager_class._owns_mainloop = True
            try:
                first_manager.window.mainloop()
            finally:
                manager_class._owns_mainloop = False

    def _update_window_dpi(self, *args):
        newdpi = self._window_dpi.get()
        self.window.call('tk', 'scaling', newdpi / 72)
        if self.toolbar and hasattr(self.toolbar, '_rescale'):
            self.toolbar._rescale()
        self.canvas._update_device_pixel_ratio()

    def resize(self, width, height):
        max_size = 1_400_000  # the measured max on xorg 1.20.8 was 1_409_023

        if (width > max_size or height > max_size) and sys.platform == 'linux':
            raise ValueError(
                'You have requested to resize the '
                f'Tk window to ({width}, {height}), one of which '
                f'is bigger than {max_size}.  At larger sizes xorg will '
                'either exit with an error on newer versions (~1.20) or '
                'cause corruption on older version (~1.19).  We '
                'do not expect a window over a million pixel wide or tall '
                'to be intended behavior.')
        self.canvas._tkcanvas.configure(width=width, height=height)

    def show(self):
        with _restore_foreground_window_at_end():
            if not self._shown:
                def destroy(*args):
                    Gcf.destroy(self)
                self.window.protocol("WM_DELETE_WINDOW", destroy)
                self.window.deiconify()
                self.canvas._tkcanvas.focus_set()
            else:
                self.canvas.draw_idle()
            if mpl.rcParams['figure.raise_window']:
                self.canvas.manager.window.attributes('-topmost', 1)
                self.canvas.manager.window.attributes('-topmost', 0)
            self._shown = True

    def destroy(self, *args):
        if self.canvas._idle_draw_id:
            self.canvas._tkcanvas.after_cancel(self.canvas._idle_draw_id)
        if self.canvas._event_loop_id:
            self.canvas._tkcanvas.after_cancel(self.canvas._event_loop_id)
        if self._window_dpi_cbname:
            self._window_dpi.trace_remove('write', self._window_dpi_cbname)

        # NOTE: events need to be flushed before issuing destroy (GH #9956),
        # however, self.window.update() can break user code. An async callback
        # is the safest way to achieve a complete draining of the event queue,
        # but it leaks if no tk event loop is running. Therefore we explicitly
        # check for an event loop and choose our best guess.
        def delayed_destroy():
            self.window.destroy()

            if self._owns_mainloop and not Gcf.get_num_fig_managers():
                self.window.quit()

        if cbook._get_running_interactive_framework() == "tk":
            # "after idle after 0" avoids Tcl error/race (GH #19940)
            self.window.after_idle(self.window.after, 0, delayed_destroy)
        else:
            self.window.update()
            delayed_destroy()

    def get_window_title(self):
        return self.window.wm_title()

    def set_window_title(self, title):
        self.window.wm_title(title)

    def full_screen_toggle(self):
        is_fullscreen = bool(self.window.attributes('-fullscreen'))
        self.window.attributes('-fullscreen', not is_fullscreen)


class NavigationToolbar2Tk(NavigationToolbar2, tk.Frame):
    def __init__(self, canvas, window=None, *, pack_toolbar=True):
        """
        Parameters
        ----------
        canvas : `FigureCanvas`
            The figure canvas on which to operate.
        window : tk.Window
            The tk.Window which owns this toolbar.
        pack_toolbar : bool, default: True
            If True, add the toolbar to the parent's pack manager's packing
            list during initialization with ``side="bottom"`` and ``fill="x"``.
            If you want to use the toolbar with a different layout manager, use
            ``pack_toolbar=False``.
        """

        if window is None:
            window = canvas.get_tk_widget().master
        tk.Frame.__init__(self, master=window, borderwidth=2,
                          width=int(canvas.figure.bbox.width), height=50)

        self._buttons = {}
        for text, tooltip_text, image_file, callback in self.toolitems:
            if text is None:
                # Add a spacer; return value is unused.
                self._Spacer()
            else:
                self._buttons[text] = button = self._Button(
                    text,
                    str(cbook._get_data_path(f"images/{image_file}.png")),
                    toggle=callback in ["zoom", "pan"],
                    command=getattr(self, callback),
                )
                if tooltip_text is not None:
                    add_tooltip(button, tooltip_text)

        self._label_font = tkinter.font.Font(root=window, size=10)

        # This filler item ensures the toolbar is always at least two text
        # lines high. Otherwise the canvas gets redrawn as the mouse hovers
        # over images because those use two-line messages which resize the
        # toolbar.
        label = tk.Label(master=self, font=self._label_font,
                         text='\N{NO-BREAK SPACE}\n\N{NO-BREAK SPACE}')
        label.pack(side=tk.RIGHT)

        self.message = tk.StringVar(master=self)
        self._message_label = tk.Label(master=self, font=self._label_font,
                                       textvariable=self.message,
                                       justify=tk.RIGHT)
        self._message_label.pack(side=tk.RIGHT)

        NavigationToolbar2.__init__(self, canvas)
        if pack_toolbar:
            self.pack(side=tk.BOTTOM, fill=tk.X)

    def _rescale(self):
        """
        Scale all children of the toolbar to current DPI setting.

        Before this is called, the Tk scaling setting will have been updated to
        match the new DPI. Tk widgets do not update for changes to scaling, but
        all measurements made after the change will match the new scaling. Thus
        this function re-applies all the same sizes in points, which Tk will
        scale correctly to pixels.
        """
        for widget in self.winfo_children():
            if isinstance(widget, (tk.Button, tk.Checkbutton)):
                if hasattr(widget, '_image_file'):
                    # Explicit class because ToolbarTk calls _rescale.
                    NavigationToolbar2Tk._set_image_for_button(self, widget)
                else:
                    # Text-only button is handled by the font setting instead.
                    pass
            elif isinstance(widget, tk.Frame):
                widget.configure(height='18p')
                widget.pack_configure(padx='3p')
            elif isinstance(widget, tk.Label):
                pass  # Text is handled by the font setting instead.
            else:
                _log.warning('Unknown child class %s', widget.winfo_class)
        self._label_font.configure(size=10)

    def _update_buttons_checked(self):
        # sync button checkstates to match active mode
        for text, mode in [('Zoom', _Mode.ZOOM), ('Pan', _Mode.PAN)]:
            if text in self._buttons:
                if self.mode == mode:
                    self._buttons[text].select()  # NOT .invoke()
                else:
                    self._buttons[text].deselect()

    def pan(self, *args):
        super().pan(*args)
        self._update_buttons_checked()

    def zoom(self, *args):
        super().zoom(*args)
        self._update_buttons_checked()

    def set_message(self, s):
        self.message.set(s)

    def draw_rubberband(self, event, x0, y0, x1, y1):
        # Block copied from remove_rubberband for backend_tools convenience.
        if self.canvas._rubberband_rect_white:
            self.canvas._tkcanvas.delete(self.canvas._rubberband_rect_white)
        if self.canvas._rubberband_rect_black:
            self.canvas._tkcanvas.delete(self.canvas._rubberband_rect_black)
        height = self.canvas.figure.bbox.height
        y0 = height - y0
        y1 = height - y1
        self.canvas._rubberband_rect_black = (
            self.canvas._tkcanvas.create_rectangle(
                x0, y0, x1, y1))
        self.canvas._rubberband_rect_white = (
            self.canvas._tkcanvas.create_rectangle(
                x0, y0, x1, y1, outline='white', dash=(3, 3)))

    def remove_rubberband(self):
        if self.canvas._rubberband_rect_white:
            self.canvas._tkcanvas.delete(self.canvas._rubberband_rect_white)
            self.canvas._rubberband_rect_white = None
        if self.canvas._rubberband_rect_black:
            self.canvas._tkcanvas.delete(self.canvas._rubberband_rect_black)
            self.canvas._rubberband_rect_black = None

    def _set_image_for_button(self, button):
        """
        Set the image for a button based on its pixel size.

        The pixel size is determined by the DPI scaling of the window.
        """
        if button._image_file is None:
            return

        # Allow _image_file to be relative to Matplotlib's "images" data
        # directory.
        path_regular = cbook._get_data_path('images', button._image_file)
        path_large = path_regular.with_name(
            path_regular.name.replace('.png', '_large.png'))
        size = button.winfo_pixels('18p')

        # Nested functions because ToolbarTk calls  _Button.
        def _get_color(color_name):
            # `winfo_rgb` returns an (r, g, b) tuple in the range 0-65535
            return button.winfo_rgb(button.cget(color_name))

        def _is_dark(color):
            if isinstance(color, str):
                color = _get_color(color)
            return max(color) < 65535 / 2

        def _recolor_icon(image, color):
            image_data = np.asarray(image).copy()
            black_mask = (image_data[..., :3] == 0).all(axis=-1)
            image_data[black_mask, :3] = color
            return Image.fromarray(image_data)

        # Use the high-resolution (48x48 px) icon if it exists and is needed
        with Image.open(path_large if (size > 24 and path_large.exists())
                        else path_regular) as im:
            # assure a RGBA image as foreground color is RGB
            im = im.convert("RGBA")
            image = ImageTk.PhotoImage(im.resize((size, size)), master=self)
            button._ntimage = image

            # create a version of the icon with the button's text color
            foreground = (255 / 65535) * np.array(
                button.winfo_rgb(button.cget("foreground")))
            im_alt = _recolor_icon(im, foreground)
            image_alt = ImageTk.PhotoImage(
                im_alt.resize((size, size)), master=self)
            button._ntimage_alt = image_alt

        if _is_dark("background"):
            # For Checkbuttons, we need to set `image` and `selectimage` at
            # the same time. Otherwise, when updating the `image` option
            # (such as when changing DPI), if the old `selectimage` has
            # just been overwritten, Tk will throw an error.
            image_kwargs = {"image": image_alt}
        else:
            image_kwargs = {"image": image}
        # Checkbuttons may switch the background to `selectcolor` in the
        # checked state, so check separately which image it needs to use in
        # that state to still ensure enough contrast with the background.
        if (
            isinstance(button, tk.Checkbutton)
            and button.cget("selectcolor") != ""
        ):
            if self._windowingsystem != "x11":
                selectcolor = "selectcolor"
            else:
                # On X11, selectcolor isn't used directly for indicator-less
                # buttons. See `::tk::CheckEnter` in the Tk button.tcl source
                # code for details.
                r1, g1, b1 = _get_color("selectcolor")
                r2, g2, b2 = _get_color("activebackground")
                selectcolor = ((r1+r2)/2, (g1+g2)/2, (b1+b2)/2)
            if _is_dark(selectcolor):
                image_kwargs["selectimage"] = image_alt
            else:
                image_kwargs["selectimage"] = image

        button.configure(**image_kwargs, height='18p', width='18p')

    def _Button(self, text, image_file, toggle, command):
        if not toggle:
            b = tk.Button(
                master=self, text=text, command=command,
                relief="flat", overrelief="groove", borderwidth=1,
            )
        else:
            # There is a bug in tkinter included in some python 3.6 versions
            # that without this variable, produces a "visual" toggling of
            # other near checkbuttons
            # https://bugs.python.org/issue29402
            # https://bugs.python.org/issue25684
            var = tk.IntVar(master=self)
            b = tk.Checkbutton(
                master=self, text=text, command=command, indicatoron=False,
                variable=var, offrelief="flat", overrelief="groove",
                borderwidth=1
            )
            b.var = var
        b._image_file = image_file
        if image_file is not None:
            # Explicit class because ToolbarTk calls _Button.
            NavigationToolbar2Tk._set_image_for_button(self, b)
        else:
            b.configure(font=self._label_font)
        b.pack(side=tk.LEFT)
        return b

    def _Spacer(self):
        # Buttons are also 18pt high.
        s = tk.Frame(master=self, height='18p', relief=tk.RIDGE, bg='DarkGray')
        s.pack(side=tk.LEFT, padx='3p')
        return s

    def save_figure(self, *args):
        filetypes = self.canvas.get_supported_filetypes_grouped()
        tk_filetypes = [
            (name, " ".join(f"*.{ext}" for ext in exts))
            for name, exts in sorted(filetypes.items())
        ]

        default_extension = self.canvas.get_default_filetype()
        default_filetype = self.canvas.get_supported_filetypes()[default_extension]
        filetype_variable = tk.StringVar(self.canvas.get_tk_widget(), default_filetype)

        # adding a default extension seems to break the
        # asksaveasfilename dialog when you choose various save types
        # from the dropdown.  Passing in the empty string seems to
        # work - JDH!
        # defaultextension = self.canvas.get_default_filetype()
        defaultextension = ''
        initialdir = os.path.expanduser(mpl.rcParams['savefig.directory'])
        # get_default_filename() contains the default extension. On some platforms,
        # choosing a different extension from the dropdown does not overwrite it,
        # so we need to remove it to make the dropdown functional.
        initialfile = pathlib.Path(self.canvas.get_default_filename()).stem
        fname = tkinter.filedialog.asksaveasfilename(
            master=self.canvas.get_tk_widget().master,
            title='Save the figure',
            filetypes=tk_filetypes,
            defaultextension=defaultextension,
            initialdir=initialdir,
            initialfile=initialfile,
            typevariable=filetype_variable
            )

        if fname in ["", ()]:
            return None
        # Save dir for next time, unless empty str (i.e., use cwd).
        if initialdir != "":
            mpl.rcParams['savefig.directory'] = (
                os.path.dirname(str(fname)))

        # If the filename contains an extension, let savefig() infer the file
        # format from that. If it does not, use the selected dropdown option.
        if pathlib.Path(fname).suffix[1:] != "":
            extension = None
        else:
            extension = filetypes[filetype_variable.get()][0]

        try:
            self.canvas.figure.savefig(fname, format=extension)
            return fname
        except Exception as e:
            tkinter.messagebox.showerror("Error saving file", str(e))

    def set_history_buttons(self):
        state_map = {True: tk.NORMAL, False: tk.DISABLED}
        can_back = self._nav_stack._pos > 0
        can_forward = self._nav_stack._pos < len(self._nav_stack) - 1
        if "Back" in self._buttons:
            self._buttons['Back']['state'] = state_map[can_back]
        if "Forward" in self._buttons:
            self._buttons['Forward']['state'] = state_map[can_forward]


def add_tooltip(widget, text):
    tipwindow = None

    def showtip(event):
        """Display text in tooltip window."""
        nonlocal tipwindow
        if tipwindow or not text:
            return
        x, y, _, _ = widget.bbox("insert")
        x = x + widget.winfo_rootx() + widget.winfo_width()
        y = y + widget.winfo_rooty()
        tipwindow = tk.Toplevel(widget)
        tipwindow.overrideredirect(1)
        tipwindow.geometry(f"+{x}+{y}")
        try:  # For Mac OS
            tipwindow.tk.call("::tk::unsupported::MacWindowStyle",
                              "style", tipwindow._w,
                              "help", "noActivates")
        except tk.TclError:
            pass
        label = tk.Label(tipwindow, text=text, justify=tk.LEFT,
                         relief=tk.SOLID, borderwidth=1)
        label.pack(ipadx=1)

    def hidetip(event):
        nonlocal tipwindow
        if tipwindow:
            tipwindow.destroy()
        tipwindow = None

    widget.bind("<Enter>", showtip)
    widget.bind("<Leave>", hidetip)


@backend_tools._register_tool_class(FigureCanvasTk)
class RubberbandTk(backend_tools.RubberbandBase):
    def draw_rubberband(self, x0, y0, x1, y1):
        NavigationToolbar2Tk.draw_rubberband(
            self._make_classic_style_pseudo_toolbar(), None, x0, y0, x1, y1)

    def remove_rubberband(self):
        NavigationToolbar2Tk.remove_rubberband(
            self._make_classic_style_pseudo_toolbar())


class ToolbarTk(ToolContainerBase, tk.Frame):
    def __init__(self, toolmanager, window=None):
        ToolContainerBase.__init__(self, toolmanager)
        if window is None:
            window = self.toolmanager.canvas.get_tk_widget().master
        xmin, xmax = self.toolmanager.canvas.figure.bbox.intervalx
        height, width = 50, xmax - xmin
        tk.Frame.__init__(self, master=window,
                          width=int(width), height=int(height),
                          borderwidth=2)
        self._label_font = tkinter.font.Font(size=10)
        # This filler item ensures the toolbar is always at least two text
        # lines high. Otherwise the canvas gets redrawn as the mouse hovers
        # over images because those use two-line messages which resize the
        # toolbar.
        label = tk.Label(master=self, font=self._label_font,
                         text='\N{NO-BREAK SPACE}\n\N{NO-BREAK SPACE}')
        label.pack(side=tk.RIGHT)
        self._message = tk.StringVar(master=self)
        self._message_label = tk.Label(master=self, font=self._label_font,
                                       textvariable=self._message)
        self._message_label.pack(side=tk.RIGHT)
        self._toolitems = {}
        self.pack(side=tk.TOP, fill=tk.X)
        self._groups = {}

    def _rescale(self):
        return NavigationToolbar2Tk._rescale(self)

    def add_toolitem(
            self, name, group, position, image_file, description, toggle):
        frame = self._get_groupframe(group)
        buttons = frame.pack_slaves()
        if position >= len(buttons) or position < 0:
            before = None
        else:
            before = buttons[position]
        button = NavigationToolbar2Tk._Button(frame, name, image_file, toggle,
                                              lambda: self._button_click(name))
        button.pack_configure(before=before)
        if description is not None:
            add_tooltip(button, description)
        self._toolitems.setdefault(name, [])
        self._toolitems[name].append(button)

    def _get_groupframe(self, group):
        if group not in self._groups:
            if self._groups:
                self._add_separator()
            frame = tk.Frame(master=self, borderwidth=0)
            frame.pack(side=tk.LEFT, fill=tk.Y)
            frame._label_font = self._label_font
            self._groups[group] = frame
        return self._groups[group]

    def _add_separator(self):
        return NavigationToolbar2Tk._Spacer(self)

    def _button_click(self, name):
        self.trigger_tool(name)

    def toggle_toolitem(self, name, toggled):
        if name not in self._toolitems:
            return
        for toolitem in self._toolitems[name]:
            if toggled:
                toolitem.select()
            else:
                toolitem.deselect()

    def remove_toolitem(self, name):
        for toolitem in self._toolitems.pop(name, []):
            toolitem.pack_forget()

    def set_message(self, s):
        self._message.set(s)


@backend_tools._register_tool_class(FigureCanvasTk)
class SaveFigureTk(backend_tools.SaveFigureBase):
    def trigger(self, *args):
        NavigationToolbar2Tk.save_figure(
            self._make_classic_style_pseudo_toolbar())


@backend_tools._register_tool_class(FigureCanvasTk)
class ConfigureSubplotsTk(backend_tools.ConfigureSubplotsBase):
    def trigger(self, *args):
        NavigationToolbar2Tk.configure_subplots(self)


@backend_tools._register_tool_class(FigureCanvasTk)
class HelpTk(backend_tools.ToolHelpBase):
    def trigger(self, *args):
        dialog = SimpleDialog(
            self.figure.canvas._tkcanvas, self._get_help_text(), ["OK"])
        dialog.done = lambda num: dialog.frame.master.withdraw()


Toolbar = ToolbarTk
FigureManagerTk._toolbar2_class = NavigationToolbar2Tk
FigureManagerTk._toolmanager_toolbar_class = ToolbarTk


@_Backend.export
class _BackendTk(_Backend):
    backend_version = tk.TkVersion
    FigureCanvas = FigureCanvasTk
    FigureManager = FigureManagerTk
    mainloop = FigureManagerTk.start_main_loop
