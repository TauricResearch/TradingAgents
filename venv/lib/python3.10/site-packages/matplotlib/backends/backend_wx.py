"""
A wxPython backend for matplotlib.

Originally contributed by Jeremy O'Donoghue (jeremy@o-donoghue.com) and John
Hunter (jdhunter@ace.bsd.uchicago.edu).

Copyright (C) Jeremy O'Donoghue & John Hunter, 2003-4.
"""

import functools
import logging
import math
import pathlib
import sys
import weakref

import numpy as np
import PIL.Image

import matplotlib as mpl
from matplotlib.backend_bases import (
    _Backend, FigureCanvasBase, FigureManagerBase,
    GraphicsContextBase, MouseButton, NavigationToolbar2, RendererBase,
    TimerBase, ToolContainerBase, cursors,
    CloseEvent, KeyEvent, LocationEvent, MouseEvent, ResizeEvent)

from matplotlib import _api, cbook, backend_tools, _c_internal_utils
from matplotlib._pylab_helpers import Gcf
from matplotlib.path import Path
from matplotlib.transforms import Affine2D

import wx
import wx.svg  # noqa: F401

_log = logging.getLogger(__name__)

# the True dots per inch on the screen; should be display dependent; see
# http://groups.google.com/d/msg/comp.lang.postscript/-/omHAc9FEuAsJ?hl=en
# for some info about screen dpi
PIXELS_PER_INCH = 75


# lru_cache holds a reference to the App and prevents it from being gc'ed.
@functools.lru_cache(1)
def _create_wxapp():
    wxapp = wx.App(False)
    wxapp.SetExitOnFrameDelete(True)
    cbook._setup_new_guiapp()
    # Set per-process DPI awareness. This is a NoOp except in MSW
    _c_internal_utils.Win32_SetProcessDpiAwareness_max()
    return wxapp


class TimerWx(TimerBase):
    """Subclass of `.TimerBase` using wx.Timer events."""

    def __init__(self, *args, **kwargs):
        self._timer = wx.Timer()
        self._timer.Notify = self._on_timer
        super().__init__(*args, **kwargs)

    def _timer_start(self):
        self._timer.Start(self._interval, self._single)

    def _timer_stop(self):
        self._timer.Stop()

    def _timer_set_interval(self):
        if self._timer.IsRunning():
            self._timer_start()  # Restart with new interval.


@_api.deprecated(
    "2.0", name="wx", obj_type="backend", removal="the future",
    alternative="wxagg",
    addendum="See the Matplotlib usage FAQ for more info on backends.")
class RendererWx(RendererBase):
    """
    The renderer handles all the drawing primitives using a graphics
    context instance that controls the colors/styles. It acts as the
    'renderer' instance used by many classes in the hierarchy.
    """
    # In wxPython, drawing is performed on a wxDC instance, which will
    # generally be mapped to the client area of the window displaying
    # the plot. Under wxPython, the wxDC instance has a wx.Pen which
    # describes the colour and weight of any lines drawn, and a wxBrush
    # which describes the fill colour of any closed polygon.

    # Font styles, families and weight.
    fontweights = {
        100: wx.FONTWEIGHT_LIGHT,
        200: wx.FONTWEIGHT_LIGHT,
        300: wx.FONTWEIGHT_LIGHT,
        400: wx.FONTWEIGHT_NORMAL,
        500: wx.FONTWEIGHT_NORMAL,
        600: wx.FONTWEIGHT_NORMAL,
        700: wx.FONTWEIGHT_BOLD,
        800: wx.FONTWEIGHT_BOLD,
        900: wx.FONTWEIGHT_BOLD,
        'ultralight': wx.FONTWEIGHT_LIGHT,
        'light': wx.FONTWEIGHT_LIGHT,
        'normal': wx.FONTWEIGHT_NORMAL,
        'medium': wx.FONTWEIGHT_NORMAL,
        'semibold': wx.FONTWEIGHT_NORMAL,
        'bold': wx.FONTWEIGHT_BOLD,
        'heavy': wx.FONTWEIGHT_BOLD,
        'ultrabold': wx.FONTWEIGHT_BOLD,
        'black': wx.FONTWEIGHT_BOLD,
    }
    fontangles = {
        'italic': wx.FONTSTYLE_ITALIC,
        'normal': wx.FONTSTYLE_NORMAL,
        'oblique': wx.FONTSTYLE_SLANT,
    }

    # wxPython allows for portable font styles, choosing them appropriately for
    # the target platform. Map some standard font names to the portable styles.
    # QUESTION: Is it wise to agree to standard fontnames across all backends?
    fontnames = {
        'Sans': wx.FONTFAMILY_SWISS,
        'Roman': wx.FONTFAMILY_ROMAN,
        'Script': wx.FONTFAMILY_SCRIPT,
        'Decorative': wx.FONTFAMILY_DECORATIVE,
        'Modern': wx.FONTFAMILY_MODERN,
        'Courier': wx.FONTFAMILY_MODERN,
        'courier': wx.FONTFAMILY_MODERN,
    }

    def __init__(self, bitmap, dpi):
        """Initialise a wxWindows renderer instance."""
        super().__init__()
        _log.debug("%s - __init__()", type(self))
        self.width = bitmap.GetWidth()
        self.height = bitmap.GetHeight()
        self.bitmap = bitmap
        self.fontd = {}
        self.dpi = dpi
        self.gc = None

    def flipy(self):
        # docstring inherited
        return True

    def get_text_width_height_descent(self, s, prop, ismath):
        # docstring inherited

        if ismath:
            s = cbook.strip_math(s)

        if self.gc is None:
            gc = self.new_gc()
        else:
            gc = self.gc
        gfx_ctx = gc.gfx_ctx
        font = self.get_wx_font(s, prop)
        gfx_ctx.SetFont(font, wx.BLACK)
        w, h, descent, leading = gfx_ctx.GetFullTextExtent(s)

        return w, h, descent

    def get_canvas_width_height(self):
        # docstring inherited
        return self.width, self.height

    def handle_clip_rectangle(self, gc):
        new_bounds = gc.get_clip_rectangle()
        if new_bounds is not None:
            new_bounds = new_bounds.bounds
        gfx_ctx = gc.gfx_ctx
        if gfx_ctx._lastcliprect != new_bounds:
            gfx_ctx._lastcliprect = new_bounds
            if new_bounds is None:
                gfx_ctx.ResetClip()
            else:
                gfx_ctx.Clip(new_bounds[0],
                             self.height - new_bounds[1] - new_bounds[3],
                             new_bounds[2], new_bounds[3])

    @staticmethod
    def convert_path(gfx_ctx, path, transform):
        wxpath = gfx_ctx.CreatePath()
        for points, code in path.iter_segments(transform):
            if code == Path.MOVETO:
                wxpath.MoveToPoint(*points)
            elif code == Path.LINETO:
                wxpath.AddLineToPoint(*points)
            elif code == Path.CURVE3:
                wxpath.AddQuadCurveToPoint(*points)
            elif code == Path.CURVE4:
                wxpath.AddCurveToPoint(*points)
            elif code == Path.CLOSEPOLY:
                wxpath.CloseSubpath()
        return wxpath

    def draw_path(self, gc, path, transform, rgbFace=None):
        # docstring inherited
        gc.select()
        self.handle_clip_rectangle(gc)
        gfx_ctx = gc.gfx_ctx
        transform = transform + \
            Affine2D().scale(1.0, -1.0).translate(0.0, self.height)
        wxpath = self.convert_path(gfx_ctx, path, transform)
        if rgbFace is not None:
            gfx_ctx.SetBrush(wx.Brush(gc.get_wxcolour(rgbFace)))
            gfx_ctx.DrawPath(wxpath)
        else:
            gfx_ctx.StrokePath(wxpath)
        gc.unselect()

    def draw_image(self, gc, x, y, im):
        bbox = gc.get_clip_rectangle()
        if bbox is not None:
            l, b, w, h = bbox.bounds
        else:
            l = 0
            b = 0
            w = self.width
            h = self.height
        rows, cols = im.shape[:2]
        bitmap = wx.Bitmap.FromBufferRGBA(cols, rows, im.tobytes())
        gc.select()
        gc.gfx_ctx.DrawBitmap(bitmap, int(l), int(self.height - b),
                              int(w), int(-h))
        gc.unselect()

    def draw_text(self, gc, x, y, s, prop, angle, ismath=False, mtext=None):
        # docstring inherited

        if ismath:
            s = cbook.strip_math(s)
        _log.debug("%s - draw_text()", type(self))
        gc.select()
        self.handle_clip_rectangle(gc)
        gfx_ctx = gc.gfx_ctx

        font = self.get_wx_font(s, prop)
        color = gc.get_wxcolour(gc.get_rgb())
        gfx_ctx.SetFont(font, color)

        w, h, d = self.get_text_width_height_descent(s, prop, ismath)
        x = int(x)
        y = int(y - h)

        if angle == 0.0:
            gfx_ctx.DrawText(s, x, y)
        else:
            rads = math.radians(angle)
            xo = h * math.sin(rads)
            yo = h * math.cos(rads)
            gfx_ctx.DrawRotatedText(s, x - xo, y - yo, rads)

        gc.unselect()

    def new_gc(self):
        # docstring inherited
        _log.debug("%s - new_gc()", type(self))
        self.gc = GraphicsContextWx(self.bitmap, self)
        self.gc.select()
        self.gc.unselect()
        return self.gc

    def get_wx_font(self, s, prop):
        """Return a wx font.  Cache font instances for efficiency."""
        _log.debug("%s - get_wx_font()", type(self))
        key = hash(prop)
        font = self.fontd.get(key)
        if font is not None:
            return font
        size = self.points_to_pixels(prop.get_size_in_points())
        # Font colour is determined by the active wx.Pen
        # TODO: It may be wise to cache font information
        self.fontd[key] = font = wx.Font(  # Cache the font and gc.
            pointSize=round(size),
            family=self.fontnames.get(prop.get_name(), wx.ROMAN),
            style=self.fontangles[prop.get_style()],
            weight=self.fontweights[prop.get_weight()])
        return font

    def points_to_pixels(self, points):
        # docstring inherited
        return points * (PIXELS_PER_INCH / 72.0 * self.dpi / 72.0)


class GraphicsContextWx(GraphicsContextBase):
    """
    The graphics context provides the color, line styles, etc.

    This class stores a reference to a wxMemoryDC, and a
    wxGraphicsContext that draws to it.  Creating a wxGraphicsContext
    seems to be fairly heavy, so these objects are cached based on the
    bitmap object that is passed in.

    The base GraphicsContext stores colors as an RGB tuple on the unit
    interval, e.g., (0.5, 0.0, 1.0).  wxPython uses an int interval, but
    since wxPython colour management is rather simple, I have not chosen
    to implement a separate colour manager class.
    """
    _capd = {'butt': wx.CAP_BUTT,
             'projecting': wx.CAP_PROJECTING,
             'round': wx.CAP_ROUND}

    _joind = {'bevel': wx.JOIN_BEVEL,
              'miter': wx.JOIN_MITER,
              'round': wx.JOIN_ROUND}

    _cache = weakref.WeakKeyDictionary()

    def __init__(self, bitmap, renderer):
        super().__init__()
        # assert self.Ok(), "wxMemoryDC not OK to use"
        _log.debug("%s - __init__(): %s", type(self), bitmap)

        dc, gfx_ctx = self._cache.get(bitmap, (None, None))
        if dc is None:
            dc = wx.MemoryDC(bitmap)
            gfx_ctx = wx.GraphicsContext.Create(dc)
            gfx_ctx._lastcliprect = None
            self._cache[bitmap] = dc, gfx_ctx

        self.bitmap = bitmap
        self.dc = dc
        self.gfx_ctx = gfx_ctx
        self._pen = wx.Pen('BLACK', 1, wx.SOLID)
        gfx_ctx.SetPen(self._pen)
        self.renderer = renderer

    def select(self):
        """Select the current bitmap into this wxDC instance."""
        if sys.platform == 'win32':
            self.dc.SelectObject(self.bitmap)
            self.IsSelected = True

    def unselect(self):
        """Select a Null bitmap into this wxDC instance."""
        if sys.platform == 'win32':
            self.dc.SelectObject(wx.NullBitmap)
            self.IsSelected = False

    def set_foreground(self, fg, isRGBA=None):
        # docstring inherited
        # Implementation note: wxPython has a separate concept of pen and
        # brush - the brush fills any outline trace left by the pen.
        # Here we set both to the same colour - if a figure is not to be
        # filled, the renderer will set the brush to be transparent
        # Same goes for text foreground...
        _log.debug("%s - set_foreground()", type(self))
        self.select()
        super().set_foreground(fg, isRGBA)

        self._pen.SetColour(self.get_wxcolour(self.get_rgb()))
        self.gfx_ctx.SetPen(self._pen)
        self.unselect()

    def set_linewidth(self, w):
        # docstring inherited
        w = float(w)
        _log.debug("%s - set_linewidth()", type(self))
        self.select()
        if 0 < w < 1:
            w = 1
        super().set_linewidth(w)
        lw = int(self.renderer.points_to_pixels(self._linewidth))
        if lw == 0:
            lw = 1
        self._pen.SetWidth(lw)
        self.gfx_ctx.SetPen(self._pen)
        self.unselect()

    def set_capstyle(self, cs):
        # docstring inherited
        _log.debug("%s - set_capstyle()", type(self))
        self.select()
        super().set_capstyle(cs)
        self._pen.SetCap(GraphicsContextWx._capd[self._capstyle])
        self.gfx_ctx.SetPen(self._pen)
        self.unselect()

    def set_joinstyle(self, js):
        # docstring inherited
        _log.debug("%s - set_joinstyle()", type(self))
        self.select()
        super().set_joinstyle(js)
        self._pen.SetJoin(GraphicsContextWx._joind[self._joinstyle])
        self.gfx_ctx.SetPen(self._pen)
        self.unselect()

    def get_wxcolour(self, color):
        """Convert an RGB(A) color to a wx.Colour."""
        _log.debug("%s - get_wx_color()", type(self))
        return wx.Colour(*[int(255 * x) for x in color])


class _FigureCanvasWxBase(FigureCanvasBase, wx.Panel):
    """
    The FigureCanvas contains the figure and does event handling.

    In the wxPython backend, it is derived from wxPanel, and (usually) lives
    inside a frame instantiated by a FigureManagerWx. The parent window
    probably implements a wx.Sizer to control the displayed control size - but
    we give a hint as to our preferred minimum size.
    """

    required_interactive_framework = "wx"
    _timer_cls = TimerWx
    manager_class = _api.classproperty(lambda cls: FigureManagerWx)

    keyvald = {
        wx.WXK_CONTROL: 'control',
        wx.WXK_SHIFT: 'shift',
        wx.WXK_ALT: 'alt',
        wx.WXK_CAPITAL: 'caps_lock',
        wx.WXK_LEFT: 'left',
        wx.WXK_UP: 'up',
        wx.WXK_RIGHT: 'right',
        wx.WXK_DOWN: 'down',
        wx.WXK_ESCAPE: 'escape',
        wx.WXK_F1: 'f1',
        wx.WXK_F2: 'f2',
        wx.WXK_F3: 'f3',
        wx.WXK_F4: 'f4',
        wx.WXK_F5: 'f5',
        wx.WXK_F6: 'f6',
        wx.WXK_F7: 'f7',
        wx.WXK_F8: 'f8',
        wx.WXK_F9: 'f9',
        wx.WXK_F10: 'f10',
        wx.WXK_F11: 'f11',
        wx.WXK_F12: 'f12',
        wx.WXK_SCROLL: 'scroll_lock',
        wx.WXK_PAUSE: 'break',
        wx.WXK_BACK: 'backspace',
        wx.WXK_RETURN: 'enter',
        wx.WXK_INSERT: 'insert',
        wx.WXK_DELETE: 'delete',
        wx.WXK_HOME: 'home',
        wx.WXK_END: 'end',
        wx.WXK_PAGEUP: 'pageup',
        wx.WXK_PAGEDOWN: 'pagedown',
        wx.WXK_NUMPAD0: '0',
        wx.WXK_NUMPAD1: '1',
        wx.WXK_NUMPAD2: '2',
        wx.WXK_NUMPAD3: '3',
        wx.WXK_NUMPAD4: '4',
        wx.WXK_NUMPAD5: '5',
        wx.WXK_NUMPAD6: '6',
        wx.WXK_NUMPAD7: '7',
        wx.WXK_NUMPAD8: '8',
        wx.WXK_NUMPAD9: '9',
        wx.WXK_NUMPAD_ADD: '+',
        wx.WXK_NUMPAD_SUBTRACT: '-',
        wx.WXK_NUMPAD_MULTIPLY: '*',
        wx.WXK_NUMPAD_DIVIDE: '/',
        wx.WXK_NUMPAD_DECIMAL: 'dec',
        wx.WXK_NUMPAD_ENTER: 'enter',
        wx.WXK_NUMPAD_UP: 'up',
        wx.WXK_NUMPAD_RIGHT: 'right',
        wx.WXK_NUMPAD_DOWN: 'down',
        wx.WXK_NUMPAD_LEFT: 'left',
        wx.WXK_NUMPAD_PAGEUP: 'pageup',
        wx.WXK_NUMPAD_PAGEDOWN: 'pagedown',
        wx.WXK_NUMPAD_HOME: 'home',
        wx.WXK_NUMPAD_END: 'end',
        wx.WXK_NUMPAD_INSERT: 'insert',
        wx.WXK_NUMPAD_DELETE: 'delete',
    }

    def __init__(self, parent, id, figure=None):
        """
        Initialize a FigureWx instance.

        - Initialize the FigureCanvasBase and wxPanel parents.
        - Set event handlers for resize, paint, and keyboard and mouse
          interaction.
        """

        FigureCanvasBase.__init__(self, figure)
        size = wx.Size(*map(math.ceil, self.figure.bbox.size))
        if wx.Platform != '__WXMSW__':
            size = parent.FromDIP(size)
        # Set preferred window size hint - helps the sizer, if one is connected
        wx.Panel.__init__(self, parent, id, size=size)
        self.bitmap = None
        self._isDrawn = False
        self._rubberband_rect = None
        self._rubberband_pen_black = wx.Pen('BLACK', 1, wx.PENSTYLE_SHORT_DASH)
        self._rubberband_pen_white = wx.Pen('WHITE', 1, wx.PENSTYLE_SOLID)

        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key_down)
        self.Bind(wx.EVT_KEY_UP, self._on_key_up)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_mouse_button)
        self.Bind(wx.EVT_LEFT_DCLICK, self._on_mouse_button)
        self.Bind(wx.EVT_LEFT_UP, self._on_mouse_button)
        self.Bind(wx.EVT_MIDDLE_DOWN, self._on_mouse_button)
        self.Bind(wx.EVT_MIDDLE_DCLICK, self._on_mouse_button)
        self.Bind(wx.EVT_MIDDLE_UP, self._on_mouse_button)
        self.Bind(wx.EVT_RIGHT_DOWN, self._on_mouse_button)
        self.Bind(wx.EVT_RIGHT_DCLICK, self._on_mouse_button)
        self.Bind(wx.EVT_RIGHT_UP, self._on_mouse_button)
        self.Bind(wx.EVT_MOUSE_AUX1_DOWN, self._on_mouse_button)
        self.Bind(wx.EVT_MOUSE_AUX1_UP, self._on_mouse_button)
        self.Bind(wx.EVT_MOUSE_AUX2_DOWN, self._on_mouse_button)
        self.Bind(wx.EVT_MOUSE_AUX2_UP, self._on_mouse_button)
        self.Bind(wx.EVT_MOUSE_AUX1_DCLICK, self._on_mouse_button)
        self.Bind(wx.EVT_MOUSE_AUX2_DCLICK, self._on_mouse_button)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_mouse_wheel)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)

        self.Bind(wx.EVT_MOUSE_CAPTURE_CHANGED, self._on_capture_lost)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self._on_capture_lost)

        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)  # Reduce flicker.
        self.SetBackgroundColour(wx.WHITE)

        if wx.Platform == '__WXMAC__':
            # Initial scaling. Other platforms handle this automatically
            dpiScale = self.GetDPIScaleFactor()
            self.SetInitialSize(self.GetSize()*(1/dpiScale))
            self._set_device_pixel_ratio(dpiScale)

    def Copy_to_Clipboard(self, event=None):
        """Copy bitmap of canvas to system clipboard."""
        bmp_obj = wx.BitmapDataObject()
        bmp_obj.SetBitmap(self.bitmap)

        if not wx.TheClipboard.IsOpened():
            open_success = wx.TheClipboard.Open()
            if open_success:
                wx.TheClipboard.SetData(bmp_obj)
                wx.TheClipboard.Flush()
                wx.TheClipboard.Close()

    def _update_device_pixel_ratio(self, *args, **kwargs):
        # We need to be careful in cases with mixed resolution displays if
        # device_pixel_ratio changes.
        if self._set_device_pixel_ratio(self.GetDPIScaleFactor()):
            self.draw()

    def draw_idle(self):
        # docstring inherited
        _log.debug("%s - draw_idle()", type(self))
        self._isDrawn = False  # Force redraw
        # Triggering a paint event is all that is needed to defer drawing
        # until later. The platform will send the event when it thinks it is
        # a good time (usually as soon as there are no other events pending).
        self.Refresh(eraseBackground=False)

    def flush_events(self):
        # docstring inherited
        wx.Yield()

    def start_event_loop(self, timeout=0):
        # docstring inherited
        if hasattr(self, '_event_loop'):
            raise RuntimeError("Event loop already running")
        timer = wx.Timer(self, id=wx.ID_ANY)
        if timeout > 0:
            timer.Start(int(timeout * 1000), oneShot=True)
            self.Bind(wx.EVT_TIMER, self.stop_event_loop, id=timer.GetId())
        # Event loop handler for start/stop event loop
        self._event_loop = wx.GUIEventLoop()
        self._event_loop.Run()
        timer.Stop()

    def stop_event_loop(self, event=None):
        # docstring inherited
        if hasattr(self, '_event_loop'):
            if self._event_loop.IsRunning():
                self._event_loop.Exit()
            del self._event_loop

    def _get_imagesave_wildcards(self):
        """Return the wildcard string for the filesave dialog."""
        default_filetype = self.get_default_filetype()
        filetypes = self.get_supported_filetypes_grouped()
        sorted_filetypes = sorted(filetypes.items())
        wildcards = []
        extensions = []
        filter_index = 0
        for i, (name, exts) in enumerate(sorted_filetypes):
            ext_list = ';'.join(['*.%s' % ext for ext in exts])
            extensions.append(exts[0])
            wildcard = f'{name} ({ext_list})|{ext_list}'
            if default_filetype in exts:
                filter_index = i
            wildcards.append(wildcard)
        wildcards = '|'.join(wildcards)
        return wildcards, extensions, filter_index

    def gui_repaint(self, drawDC=None):
        """
        Update the displayed image on the GUI canvas, using the supplied
        wx.PaintDC device context.
        """
        _log.debug("%s - gui_repaint()", type(self))
        # The "if self" check avoids a "wrapped C/C++ object has been deleted"
        # RuntimeError if doing things after window is closed.
        if not (self and self.IsShownOnScreen()):
            return
        if not drawDC:  # not called from OnPaint use a ClientDC
            drawDC = wx.ClientDC(self)
        # For 'WX' backend on Windows, the bitmap cannot be in use by another
        # DC (see GraphicsContextWx._cache).
        bmp = (self.bitmap.ConvertToImage().ConvertToBitmap()
               if wx.Platform == '__WXMSW__'
                  and isinstance(self.figure.canvas.get_renderer(), RendererWx)
               else self.bitmap)
        drawDC.DrawBitmap(bmp, 0, 0)
        if self._rubberband_rect is not None:
            # Some versions of wx+python don't support numpy.float64 here.
            x0, y0, x1, y1 = map(round, self._rubberband_rect)
            rect = [(x0, y0, x1, y0), (x1, y0, x1, y1),
                    (x0, y0, x0, y1), (x0, y1, x1, y1)]
            drawDC.DrawLineList(rect, self._rubberband_pen_white)
            drawDC.DrawLineList(rect, self._rubberband_pen_black)

    filetypes = {
        **FigureCanvasBase.filetypes,
        'bmp': 'Windows bitmap',
        'jpeg': 'JPEG',
        'jpg': 'JPEG',
        'pcx': 'PCX',
        'png': 'Portable Network Graphics',
        'tif': 'Tagged Image Format File',
        'tiff': 'Tagged Image Format File',
        'xpm': 'X pixmap',
    }

    def _on_paint(self, event):
        """Called when wxPaintEvt is generated."""
        _log.debug("%s - _on_paint()", type(self))
        drawDC = wx.PaintDC(self)
        if not self._isDrawn:
            self.draw(drawDC=drawDC)
        else:
            self.gui_repaint(drawDC=drawDC)
        drawDC.Destroy()

    def _on_size(self, event):
        """
        Called when wxEventSize is generated.

        In this application we attempt to resize to fit the window, so it
        is better to take the performance hit and redraw the whole window.
        """
        self._update_device_pixel_ratio()
        _log.debug("%s - _on_size()", type(self))
        sz = self.GetParent().GetSizer()
        if sz:
            si = sz.GetItem(self)
        if sz and si and not si.Proportion and not si.Flag & wx.EXPAND:
            # managed by a sizer, but with a fixed size
            size = self.GetMinSize()
        else:
            # variable size
            size = self.GetClientSize()
            # Do not allow size to become smaller than MinSize
            size.IncTo(self.GetMinSize())
        if getattr(self, "_width", None):
            if size == (self._width, self._height):
                # no change in size
                return
        self._width, self._height = size
        self._isDrawn = False

        if self._width <= 1 or self._height <= 1:
            return  # Empty figure

        # Create a new, correctly sized bitmap
        dpival = self.figure.dpi
        if not wx.Platform == '__WXMSW__':
            scale = self.GetDPIScaleFactor()
            dpival /= scale
        winch = self._width / dpival
        hinch = self._height / dpival
        self.figure.set_size_inches(winch, hinch, forward=False)

        # Rendering will happen on the associated paint event
        # so no need to do anything here except to make sure
        # the whole background is repainted.
        self.Refresh(eraseBackground=False)
        ResizeEvent("resize_event", self)._process()
        self.draw_idle()

    @staticmethod
    def _mpl_buttons():
        state = wx.GetMouseState()
        # NOTE: Alternatively, we could use event.LeftIsDown() / etc. but this
        # fails to report multiclick drags on macOS (other OSes have not been
        # verified).
        mod_table = [
            (MouseButton.LEFT, state.LeftIsDown()),
            (MouseButton.RIGHT, state.RightIsDown()),
            (MouseButton.MIDDLE, state.MiddleIsDown()),
            (MouseButton.BACK, state.Aux1IsDown()),
            (MouseButton.FORWARD, state.Aux2IsDown()),
        ]
        # State *after* press/release.
        return {button for button, flag in mod_table if flag}

    @staticmethod
    def _mpl_modifiers(event=None, *, exclude=None):
        mod_table = [
            ("ctrl", wx.MOD_CONTROL, wx.WXK_CONTROL),
            ("alt", wx.MOD_ALT, wx.WXK_ALT),
            ("shift", wx.MOD_SHIFT, wx.WXK_SHIFT),
        ]
        if event is not None:
            modifiers = event.GetModifiers()
            return [name for name, mod, key in mod_table
                    if modifiers & mod and exclude != key]
        else:
            return [name for name, mod, key in mod_table
                    if wx.GetKeyState(key)]

    def _get_key(self, event):
        keyval = event.KeyCode
        if keyval in self.keyvald:
            key = self.keyvald[keyval]
        elif keyval < 256:
            key = chr(keyval)
            # wx always returns an uppercase, so make it lowercase if the shift
            # key is not depressed (NOTE: this will not handle Caps Lock)
            if not event.ShiftDown():
                key = key.lower()
        else:
            return None
        mods = self._mpl_modifiers(event, exclude=keyval)
        if "shift" in mods and key.isupper():
            mods.remove("shift")
        return "+".join([*mods, key])

    def _mpl_coords(self, pos=None):
        """
        Convert a wx position, defaulting to the current cursor position, to
        Matplotlib coordinates.
        """
        if pos is None:
            pos = wx.GetMouseState()
            x, y = self.ScreenToClient(pos.X, pos.Y)
        else:
            x, y = pos.X, pos.Y
        # flip y so y=0 is bottom of canvas
        if not wx.Platform == '__WXMSW__':
            scale = self.GetDPIScaleFactor()
            return x*scale, self.figure.bbox.height - y*scale
        else:
            return x, self.figure.bbox.height - y

    def _on_key_down(self, event):
        """Capture key press."""
        KeyEvent("key_press_event", self,
                 self._get_key(event), *self._mpl_coords(),
                 guiEvent=event)._process()
        if self:
            event.Skip()

    def _on_key_up(self, event):
        """Release key."""
        KeyEvent("key_release_event", self,
                 self._get_key(event), *self._mpl_coords(),
                 guiEvent=event)._process()
        if self:
            event.Skip()

    def set_cursor(self, cursor):
        # docstring inherited
        cursor = wx.Cursor(_api.check_getitem({
            cursors.MOVE: wx.CURSOR_HAND,
            cursors.HAND: wx.CURSOR_HAND,
            cursors.POINTER: wx.CURSOR_ARROW,
            cursors.SELECT_REGION: wx.CURSOR_CROSS,
            cursors.WAIT: wx.CURSOR_WAIT,
            cursors.RESIZE_HORIZONTAL: wx.CURSOR_SIZEWE,
            cursors.RESIZE_VERTICAL: wx.CURSOR_SIZENS,
        }, cursor=cursor))
        self.SetCursor(cursor)
        self.Refresh()

    def _set_capture(self, capture=True):
        """Control wx mouse capture."""
        if self.HasCapture():
            self.ReleaseMouse()
        if capture:
            self.CaptureMouse()

    def _on_capture_lost(self, event):
        """Capture changed or lost"""
        self._set_capture(False)

    def _on_mouse_button(self, event):
        """Start measuring on an axis."""
        event.Skip()
        self._set_capture(event.ButtonDown() or event.ButtonDClick())
        x, y = self._mpl_coords(event)
        button_map = {
            wx.MOUSE_BTN_LEFT: MouseButton.LEFT,
            wx.MOUSE_BTN_MIDDLE: MouseButton.MIDDLE,
            wx.MOUSE_BTN_RIGHT: MouseButton.RIGHT,
            wx.MOUSE_BTN_AUX1: MouseButton.BACK,
            wx.MOUSE_BTN_AUX2: MouseButton.FORWARD,
        }
        button = event.GetButton()
        button = button_map.get(button, button)
        modifiers = self._mpl_modifiers(event)
        if event.ButtonDown():
            MouseEvent("button_press_event", self, x, y, button,
                       modifiers=modifiers, guiEvent=event)._process()
        elif event.ButtonDClick():
            MouseEvent("button_press_event", self, x, y, button, dblclick=True,
                       modifiers=modifiers, guiEvent=event)._process()
        elif event.ButtonUp():
            MouseEvent("button_release_event", self, x, y, button,
                       modifiers=modifiers, guiEvent=event)._process()

    def _on_mouse_wheel(self, event):
        """Translate mouse wheel events into matplotlib events"""
        x, y = self._mpl_coords(event)
        # Convert delta/rotation/rate into a floating point step size
        step = event.LinesPerAction * event.WheelRotation / event.WheelDelta
        # Done handling event
        event.Skip()
        # Mac gives two events for every wheel event; skip every second one.
        if wx.Platform == '__WXMAC__':
            if not hasattr(self, '_skipwheelevent'):
                self._skipwheelevent = True
            elif self._skipwheelevent:
                self._skipwheelevent = False
                return  # Return without processing event
            else:
                self._skipwheelevent = True
        MouseEvent("scroll_event", self, x, y, step=step,
                   modifiers=self._mpl_modifiers(event),
                   guiEvent=event)._process()

    def _on_motion(self, event):
        """Start measuring on an axis."""
        event.Skip()
        MouseEvent("motion_notify_event", self,
                   *self._mpl_coords(event),
                   buttons=self._mpl_buttons(),
                   modifiers=self._mpl_modifiers(event),
                   guiEvent=event)._process()

    def _on_enter(self, event):
        """Mouse has entered the window."""
        event.Skip()
        LocationEvent("figure_enter_event", self,
                      *self._mpl_coords(event),
                      modifiers=self._mpl_modifiers(),
                      guiEvent=event)._process()

    def _on_leave(self, event):
        """Mouse has left the window."""
        event.Skip()
        LocationEvent("figure_leave_event", self,
                      *self._mpl_coords(event),
                      modifiers=self._mpl_modifiers(),
                      guiEvent=event)._process()


class FigureCanvasWx(_FigureCanvasWxBase):
    # Rendering to a Wx canvas using the deprecated Wx renderer.

    def draw(self, drawDC=None):
        """
        Render the figure using RendererWx instance renderer, or using a
        previously defined renderer if none is specified.
        """
        _log.debug("%s - draw()", type(self))
        self.renderer = RendererWx(self.bitmap, self.figure.dpi)
        self.figure.draw(self.renderer)
        self._isDrawn = True
        self.gui_repaint(drawDC=drawDC)

    def _print_image(self, filetype, filename):
        bitmap = wx.Bitmap(math.ceil(self.figure.bbox.width),
                           math.ceil(self.figure.bbox.height))
        self.figure.draw(RendererWx(bitmap, self.figure.dpi))
        saved_obj = (bitmap.ConvertToImage()
                     if cbook.is_writable_file_like(filename)
                     else bitmap)
        if not saved_obj.SaveFile(filename, filetype):
            raise RuntimeError(f'Could not save figure to {filename}')
        # draw() is required here since bits of state about the last renderer
        # are strewn about the artist draw methods.  Do not remove the draw
        # without first verifying that these have been cleaned up.  The artist
        # contains() methods will fail otherwise.
        if self._isDrawn:
            self.draw()
        # The "if self" check avoids a "wrapped C/C++ object has been deleted"
        # RuntimeError if doing things after window is closed.
        if self:
            self.Refresh()

    print_bmp = functools.partialmethod(
        _print_image, wx.BITMAP_TYPE_BMP)
    print_jpeg = print_jpg = functools.partialmethod(
        _print_image, wx.BITMAP_TYPE_JPEG)
    print_pcx = functools.partialmethod(
        _print_image, wx.BITMAP_TYPE_PCX)
    print_png = functools.partialmethod(
        _print_image, wx.BITMAP_TYPE_PNG)
    print_tiff = print_tif = functools.partialmethod(
        _print_image, wx.BITMAP_TYPE_TIF)
    print_xpm = functools.partialmethod(
        _print_image, wx.BITMAP_TYPE_XPM)


class FigureFrameWx(wx.Frame):
    def __init__(self, num, fig, *, canvas_class):
        # On non-Windows platform, explicitly set the position - fix
        # positioning bug on some Linux platforms
        if wx.Platform == '__WXMSW__':
            pos = wx.DefaultPosition
        else:
            pos = wx.Point(20, 20)
        super().__init__(parent=None, id=-1, pos=pos)
        # Frame will be sized later by the Fit method
        _log.debug("%s - __init__()", type(self))
        _set_frame_icon(self)

        self.canvas = canvas_class(self, -1, fig)
        # Auto-attaches itself to self.canvas.manager
        manager = FigureManagerWx(self.canvas, num, self)

        toolbar = self.canvas.manager.toolbar
        if toolbar is not None:
            self.SetToolBar(toolbar)

        # On Windows, canvas sizing must occur after toolbar addition;
        # otherwise the toolbar further resizes the canvas.
        w, h = map(math.ceil, fig.bbox.size)
        self.canvas.SetInitialSize(self.FromDIP(wx.Size(w, h)))
        self.canvas.SetMinSize(self.FromDIP(wx.Size(2, 2)))
        self.canvas.SetFocus()

        self.Fit()

        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _on_close(self, event):
        _log.debug("%s - on_close()", type(self))
        CloseEvent("close_event", self.canvas)._process()
        self.canvas.stop_event_loop()
        # set FigureManagerWx.frame to None to prevent repeated attempts to
        # close this frame from FigureManagerWx.destroy()
        self.canvas.manager.frame = None
        # remove figure manager from Gcf.figs
        Gcf.destroy(self.canvas.manager)
        try:  # See issue 2941338.
            self.canvas.mpl_disconnect(self.canvas.toolbar._id_drag)
        except AttributeError:  # If there's no toolbar.
            pass
        # Carry on with close event propagation, frame & children destruction
        event.Skip()


class FigureManagerWx(FigureManagerBase):
    """
    Container/controller for the FigureCanvas and GUI frame.

    It is instantiated by Gcf whenever a new figure is created.  Gcf is
    responsible for managing multiple instances of FigureManagerWx.

    Attributes
    ----------
    canvas : `FigureCanvas`
        a FigureCanvasWx(wx.Panel) instance
    window : wxFrame
        a wxFrame instance - wxpython.org/Phoenix/docs/html/Frame.html
    """

    def __init__(self, canvas, num, frame):
        _log.debug("%s - __init__()", type(self))
        self.frame = self.window = frame
        super().__init__(canvas, num)

    @classmethod
    def create_with_canvas(cls, canvas_class, figure, num):
        # docstring inherited
        wxapp = wx.GetApp() or _create_wxapp()
        frame = FigureFrameWx(num, figure, canvas_class=canvas_class)
        manager = figure.canvas.manager
        if mpl.is_interactive():
            manager.frame.Show()
            figure.canvas.draw_idle()
        return manager

    @classmethod
    def start_main_loop(cls):
        if not wx.App.IsMainLoopRunning():
            wxapp = wx.GetApp()
            if wxapp is not None:
                wxapp.MainLoop()

    def show(self):
        # docstring inherited
        self.frame.Show()
        self.canvas.draw()
        if mpl.rcParams['figure.raise_window']:
            self.frame.Raise()

    def destroy(self, *args):
        # docstring inherited
        _log.debug("%s - destroy()", type(self))
        frame = self.frame
        if frame:  # Else, may have been already deleted, e.g. when closing.
            # As this can be called from non-GUI thread from plt.close use
            # wx.CallAfter to ensure thread safety.
            wx.CallAfter(frame.Close)

    def full_screen_toggle(self):
        # docstring inherited
        self.frame.ShowFullScreen(not self.frame.IsFullScreen())

    def get_window_title(self):
        # docstring inherited
        return self.window.GetTitle()

    def set_window_title(self, title):
        # docstring inherited
        self.window.SetTitle(title)

    def resize(self, width, height):
        # docstring inherited
        # Directly using SetClientSize doesn't handle the toolbar on Windows.
        self.window.SetSize(self.window.ClientToWindowSize(wx.Size(
            math.ceil(width), math.ceil(height))))


def _load_bitmap(filename):
    """
    Load a wx.Bitmap from a file in the "images" directory of the Matplotlib
    data.
    """
    return wx.Bitmap(str(cbook._get_data_path('images', filename)))


def _set_frame_icon(frame):
    bundle = wx.IconBundle()
    for image in ('matplotlib.png', 'matplotlib_large.png'):
        icon = wx.Icon(_load_bitmap(image))
        if not icon.IsOk():
            return
        bundle.AddIcon(icon)
    frame.SetIcons(bundle)


class NavigationToolbar2Wx(NavigationToolbar2, wx.ToolBar):
    def __init__(self, canvas, coordinates=True, *, style=wx.TB_BOTTOM):
        wx.ToolBar.__init__(self, canvas.GetParent(), -1, style=style)
        if wx.Platform == '__WXMAC__':
            self.SetToolBitmapSize(self.GetToolBitmapSize()*self.GetDPIScaleFactor())

        self.wx_ids = {}
        for text, tooltip_text, image_file, callback in self.toolitems:
            if text is None:
                self.AddSeparator()
                continue
            self.wx_ids[text] = (
                self.AddTool(
                    -1,
                    bitmap=self._icon(f"{image_file}.svg"),
                    bmpDisabled=wx.NullBitmap,
                    label=text, shortHelp=tooltip_text,
                    kind=(wx.ITEM_CHECK if text in ["Pan", "Zoom"]
                          else wx.ITEM_NORMAL))
                .Id)
            self.Bind(wx.EVT_TOOL, getattr(self, callback),
                      id=self.wx_ids[text])

        self._coordinates = coordinates
        if self._coordinates:
            self.AddStretchableSpace()
            self._label_text = wx.StaticText(self, style=wx.ALIGN_RIGHT)
            self.AddControl(self._label_text)

        self.Realize()

        NavigationToolbar2.__init__(self, canvas)

    @staticmethod
    def _icon(name):
        """
        Construct a `wx.Bitmap` suitable for use as icon from an image file
        *name*, including the extension and relative to Matplotlib's "images"
        data directory.
        """
        try:
            dark = wx.SystemSettings.GetAppearance().IsDark()
        except AttributeError:  # wxpython < 4.1
            # copied from wx's IsUsingDarkBackground / GetLuminance.
            bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
            fg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
            # See wx.Colour.GetLuminance.
            bg_lum = (.299 * bg.red + .587 * bg.green + .114 * bg.blue) / 255
            fg_lum = (.299 * fg.red + .587 * fg.green + .114 * fg.blue) / 255
            dark = fg_lum - bg_lum > .2

        path = cbook._get_data_path('images', name)
        if path.suffix == '.svg':
            svg = path.read_bytes()
            if dark:
                svg = svg.replace(b'fill:black;', b'fill:white;')
            toolbarIconSize = wx.ArtProvider().GetDIPSizeHint(wx.ART_TOOLBAR)
            return wx.BitmapBundle.FromSVG(svg, toolbarIconSize)
        else:
            pilimg = PIL.Image.open(path)
            # ensure RGBA as wx BitMap expects RGBA format
            image = np.array(pilimg.convert("RGBA"))
            if dark:
                fg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
                black_mask = (image[..., :3] == 0).all(axis=-1)
                image[black_mask, :3] = (fg.Red(), fg.Green(), fg.Blue())
            return wx.Bitmap.FromBufferRGBA(
                image.shape[1], image.shape[0], image.tobytes())

    def _update_buttons_checked(self):
        if "Pan" in self.wx_ids:
            self.ToggleTool(self.wx_ids["Pan"], self.mode.name == "PAN")
        if "Zoom" in self.wx_ids:
            self.ToggleTool(self.wx_ids["Zoom"], self.mode.name == "ZOOM")

    def zoom(self, *args):
        super().zoom(*args)
        self._update_buttons_checked()

    def pan(self, *args):
        super().pan(*args)
        self._update_buttons_checked()

    def save_figure(self, *args):
        # Fetch the required filename and file type.
        filetypes, exts, filter_index = self.canvas._get_imagesave_wildcards()
        default_file = self.canvas.get_default_filename()
        dialog = wx.FileDialog(
            self.canvas.GetParent(), "Save to file",
            mpl.rcParams["savefig.directory"], default_file, filetypes,
            wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        dialog.SetFilterIndex(filter_index)
        if dialog.ShowModal() == wx.ID_OK:
            path = pathlib.Path(dialog.GetPath())
            _log.debug('%s - Save file path: %s', type(self), path)
            fmt = exts[dialog.GetFilterIndex()]
            ext = path.suffix[1:]
            if ext in self.canvas.get_supported_filetypes() and fmt != ext:
                # looks like they forgot to set the image type drop
                # down, going with the extension.
                _log.warning('extension %s did not match the selected '
                             'image type %s; going with %s',
                             ext, fmt, ext)
                fmt = ext
            # Save dir for next time, unless empty str (which means use cwd).
            if mpl.rcParams["savefig.directory"]:
                mpl.rcParams["savefig.directory"] = str(path.parent)
            try:
                self.canvas.figure.savefig(path, format=fmt)
                return path
            except Exception as e:
                dialog = wx.MessageDialog(
                    parent=self.canvas.GetParent(), message=str(e),
                    caption='Matplotlib error')
                dialog.ShowModal()
                dialog.Destroy()

    def draw_rubberband(self, event, x0, y0, x1, y1):
        height = self.canvas.figure.bbox.height
        sf = 1 if wx.Platform == '__WXMSW__' else self.canvas.GetDPIScaleFactor()
        self.canvas._rubberband_rect = (x0/sf, (height - y0)/sf,
                                        x1/sf, (height - y1)/sf)
        self.canvas.Refresh()

    def remove_rubberband(self):
        self.canvas._rubberband_rect = None
        self.canvas.Refresh()

    def set_message(self, s):
        if self._coordinates:
            self._label_text.SetLabel(s)

    def set_history_buttons(self):
        can_backward = self._nav_stack._pos > 0
        can_forward = self._nav_stack._pos < len(self._nav_stack) - 1
        if 'Back' in self.wx_ids:
            self.EnableTool(self.wx_ids['Back'], can_backward)
        if 'Forward' in self.wx_ids:
            self.EnableTool(self.wx_ids['Forward'], can_forward)


# tools for matplotlib.backend_managers.ToolManager:

class ToolbarWx(ToolContainerBase, wx.ToolBar):
    _icon_extension = '.svg'

    def __init__(self, toolmanager, parent=None, style=wx.TB_BOTTOM):
        if parent is None:
            parent = toolmanager.canvas.GetParent()
        ToolContainerBase.__init__(self, toolmanager)
        wx.ToolBar.__init__(self, parent, -1, style=style)
        self._space = self.AddStretchableSpace()
        self._label_text = wx.StaticText(self, style=wx.ALIGN_RIGHT)
        self.AddControl(self._label_text)
        self._toolitems = {}
        self._groups = {}  # Mapping of groups to the separator after them.

    def _get_tool_pos(self, tool):
        """
        Find the position (index) of a wx.ToolBarToolBase in a ToolBar.

        ``ToolBar.GetToolPos`` is not useful because wx assigns the same Id to
        all Separators and StretchableSpaces.
        """
        pos, = (pos for pos in range(self.ToolsCount)
                if self.GetToolByPos(pos) == tool)
        return pos

    def add_toolitem(self, name, group, position, image_file, description,
                     toggle):
        # Find or create the separator that follows this group.
        if group not in self._groups:
            self._groups[group] = self.InsertSeparator(
                self._get_tool_pos(self._space))
        sep = self._groups[group]
        # List all separators.
        seps = [t for t in map(self.GetToolByPos, range(self.ToolsCount))
                if t.IsSeparator() and not t.IsStretchableSpace()]
        # Find where to insert the tool.
        if position >= 0:
            # Find the start of the group by looking for the separator
            # preceding this one; then move forward from it.
            start = (0 if sep == seps[0]
                     else self._get_tool_pos(seps[seps.index(sep) - 1]) + 1)
        else:
            # Move backwards from this separator.
            start = self._get_tool_pos(sep) + 1
        idx = start + position
        if image_file:
            bmp = NavigationToolbar2Wx._icon(image_file)
            kind = wx.ITEM_NORMAL if not toggle else wx.ITEM_CHECK
            tool = self.InsertTool(idx, -1, name, bmp, wx.NullBitmap, kind,
                                   description or "")
        else:
            size = (self.GetTextExtent(name)[0] + 10, -1)
            if toggle:
                control = wx.ToggleButton(self, -1, name, size=size)
            else:
                control = wx.Button(self, -1, name, size=size)
            tool = self.InsertControl(idx, control, label=name)
        self.Realize()

        def handler(event):
            self.trigger_tool(name)

        if image_file:
            self.Bind(wx.EVT_TOOL, handler, tool)
        else:
            control.Bind(wx.EVT_LEFT_DOWN, handler)

        self._toolitems.setdefault(name, [])
        self._toolitems[name].append((tool, handler))

    def toggle_toolitem(self, name, toggled):
        if name not in self._toolitems:
            return
        for tool, handler in self._toolitems[name]:
            if not tool.IsControl():
                self.ToggleTool(tool.Id, toggled)
            else:
                tool.GetControl().SetValue(toggled)
        self.Refresh()

    def remove_toolitem(self, name):
        for tool, handler in self._toolitems.pop(name, []):
            self.DeleteTool(tool.Id)

    def set_message(self, s):
        self._label_text.SetLabel(s)


@backend_tools._register_tool_class(_FigureCanvasWxBase)
class ConfigureSubplotsWx(backend_tools.ConfigureSubplotsBase):
    def trigger(self, *args):
        NavigationToolbar2Wx.configure_subplots(self)


@backend_tools._register_tool_class(_FigureCanvasWxBase)
class SaveFigureWx(backend_tools.SaveFigureBase):
    def trigger(self, *args):
        NavigationToolbar2Wx.save_figure(
            self._make_classic_style_pseudo_toolbar())


@backend_tools._register_tool_class(_FigureCanvasWxBase)
class RubberbandWx(backend_tools.RubberbandBase):
    def draw_rubberband(self, x0, y0, x1, y1):
        NavigationToolbar2Wx.draw_rubberband(
            self._make_classic_style_pseudo_toolbar(), None, x0, y0, x1, y1)

    def remove_rubberband(self):
        NavigationToolbar2Wx.remove_rubberband(
            self._make_classic_style_pseudo_toolbar())


class _HelpDialog(wx.Dialog):
    _instance = None  # a reference to an open dialog singleton
    headers = [("Action", "Shortcuts", "Description")]
    widths = [100, 140, 300]

    def __init__(self, parent, help_entries):
        super().__init__(parent, title="Help",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        sizer = wx.BoxSizer(wx.VERTICAL)
        grid_sizer = wx.FlexGridSizer(0, 3, 8, 6)
        # create and add the entries
        bold = self.GetFont().MakeBold()
        for r, row in enumerate(self.headers + help_entries):
            for (col, width) in zip(row, self.widths):
                label = wx.StaticText(self, label=col)
                if r == 0:
                    label.SetFont(bold)
                label.Wrap(width)
                grid_sizer.Add(label, 0, 0, 0)
        # finalize layout, create button
        sizer.Add(grid_sizer, 0, wx.ALL, 6)
        ok = wx.Button(self, wx.ID_OK)
        sizer.Add(ok, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 8)
        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()
        self.Bind(wx.EVT_CLOSE, self._on_close)
        ok.Bind(wx.EVT_BUTTON, self._on_close)

    def _on_close(self, event):
        _HelpDialog._instance = None  # remove global reference
        self.DestroyLater()
        event.Skip()

    @classmethod
    def show(cls, parent, help_entries):
        # if no dialog is shown, create one; otherwise just re-raise it
        if cls._instance:
            cls._instance.Raise()
            return
        cls._instance = cls(parent, help_entries)
        cls._instance.Show()


@backend_tools._register_tool_class(_FigureCanvasWxBase)
class HelpWx(backend_tools.ToolHelpBase):
    def trigger(self, *args):
        _HelpDialog.show(self.figure.canvas.GetTopLevelParent(),
                         self._get_help_entries())


@backend_tools._register_tool_class(_FigureCanvasWxBase)
class ToolCopyToClipboardWx(backend_tools.ToolCopyToClipboardBase):
    def trigger(self, *args, **kwargs):
        if not self.canvas._isDrawn:
            self.canvas.draw()
        if not self.canvas.bitmap.IsOk() or not wx.TheClipboard.Open():
            return
        try:
            wx.TheClipboard.SetData(wx.BitmapDataObject(self.canvas.bitmap))
        finally:
            wx.TheClipboard.Close()


FigureManagerWx._toolbar2_class = NavigationToolbar2Wx
FigureManagerWx._toolmanager_toolbar_class = ToolbarWx


@_Backend.export
class _BackendWx(_Backend):
    FigureCanvas = FigureCanvasWx
    FigureManager = FigureManagerWx
    mainloop = FigureManagerWx.start_main_loop
