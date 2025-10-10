"""Displays Agg images in the browser, with interactivity."""
# The WebAgg backend is divided into two modules:
#
# - `backend_webagg_core.py` contains code necessary to embed a WebAgg
#   plot inside of a web application, and communicate in an abstract
#   way over a web socket.
#
# - `backend_webagg.py` contains a concrete implementation of a basic
#   application, implemented with asyncio.

import asyncio
import datetime
from io import BytesIO, StringIO
import json
import logging
import os
from pathlib import Path

import numpy as np
from PIL import Image

from matplotlib import _api, backend_bases, backend_tools
from matplotlib.backends import backend_agg
from matplotlib.backend_bases import (
    _Backend, MouseButton, KeyEvent, LocationEvent, MouseEvent, ResizeEvent)

_log = logging.getLogger(__name__)

_SPECIAL_KEYS_LUT = {'Alt': 'alt',
                     'AltGraph': 'alt',
                     'CapsLock': 'caps_lock',
                     'Control': 'control',
                     'Meta': 'meta',
                     'NumLock': 'num_lock',
                     'ScrollLock': 'scroll_lock',
                     'Shift': 'shift',
                     'Super': 'super',
                     'Enter': 'enter',
                     'Tab': 'tab',
                     'ArrowDown': 'down',
                     'ArrowLeft': 'left',
                     'ArrowRight': 'right',
                     'ArrowUp': 'up',
                     'End': 'end',
                     'Home': 'home',
                     'PageDown': 'pagedown',
                     'PageUp': 'pageup',
                     'Backspace': 'backspace',
                     'Delete': 'delete',
                     'Insert': 'insert',
                     'Escape': 'escape',
                     'Pause': 'pause',
                     'Select': 'select',
                     'Dead': 'dead',
                     'F1': 'f1',
                     'F2': 'f2',
                     'F3': 'f3',
                     'F4': 'f4',
                     'F5': 'f5',
                     'F6': 'f6',
                     'F7': 'f7',
                     'F8': 'f8',
                     'F9': 'f9',
                     'F10': 'f10',
                     'F11': 'f11',
                     'F12': 'f12'}


def _handle_key(key):
    """Handle key values"""
    value = key[key.index('k') + 1:]
    if 'shift+' in key:
        if len(value) == 1:
            key = key.replace('shift+', '')
    if value in _SPECIAL_KEYS_LUT:
        value = _SPECIAL_KEYS_LUT[value]
    key = key[:key.index('k')] + value
    return key


class TimerTornado(backend_bases.TimerBase):
    def __init__(self, *args, **kwargs):
        self._timer = None
        super().__init__(*args, **kwargs)

    def _timer_start(self):
        import tornado

        self._timer_stop()
        if self._single:
            ioloop = tornado.ioloop.IOLoop.instance()
            self._timer = ioloop.add_timeout(
                datetime.timedelta(milliseconds=self.interval),
                self._on_timer)
        else:
            self._timer = tornado.ioloop.PeriodicCallback(
                self._on_timer,
                max(self.interval, 1e-6))
            self._timer.start()

    def _timer_stop(self):
        import tornado

        if self._timer is None:
            return
        elif self._single:
            ioloop = tornado.ioloop.IOLoop.instance()
            ioloop.remove_timeout(self._timer)
        else:
            self._timer.stop()
        self._timer = None

    def _timer_set_interval(self):
        # Only stop and restart it if the timer has already been started
        if self._timer is not None:
            self._timer_stop()
            self._timer_start()


class TimerAsyncio(backend_bases.TimerBase):
    def __init__(self, *args, **kwargs):
        self._task = None
        super().__init__(*args, **kwargs)

    async def _timer_task(self, interval):
        while True:
            try:
                await asyncio.sleep(interval)
                self._on_timer()

                if self._single:
                    break
            except asyncio.CancelledError:
                break

    def _timer_start(self):
        self._timer_stop()

        self._task = asyncio.ensure_future(
            self._timer_task(max(self.interval / 1_000., 1e-6))
        )

    def _timer_stop(self):
        if self._task is not None:
            self._task.cancel()
        self._task = None

    def _timer_set_interval(self):
        # Only stop and restart it if the timer has already been started
        if self._task is not None:
            self._timer_stop()
            self._timer_start()


class FigureCanvasWebAggCore(backend_agg.FigureCanvasAgg):
    manager_class = _api.classproperty(lambda cls: FigureManagerWebAgg)
    _timer_cls = TimerAsyncio
    # Webagg and friends having the right methods, but still
    # having bugs in practice.  Do not advertise that it works until
    # we can debug this.
    supports_blit = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set to True when the renderer contains data that is newer
        # than the PNG buffer.
        self._png_is_old = True
        # Set to True by the `refresh` message so that the next frame
        # sent to the clients will be a full frame.
        self._force_full = True
        # The last buffer, for diff mode.
        self._last_buff = np.empty((0, 0))
        # Store the current image mode so that at any point, clients can
        # request the information. This should be changed by calling
        # self.set_image_mode(mode) so that the notification can be given
        # to the connected clients.
        self._current_image_mode = 'full'
        # Track mouse events to fill in the x, y position of key events.
        self._last_mouse_xy = (None, None)

    def show(self):
        # show the figure window
        from matplotlib.pyplot import show
        show()

    def draw(self):
        self._png_is_old = True
        try:
            super().draw()
        finally:
            self.manager.refresh_all()  # Swap the frames.

    def blit(self, bbox=None):
        self._png_is_old = True
        self.manager.refresh_all()

    def draw_idle(self):
        self.send_event("draw")

    def set_cursor(self, cursor):
        # docstring inherited
        cursor = _api.check_getitem({
            backend_tools.Cursors.HAND: 'pointer',
            backend_tools.Cursors.POINTER: 'default',
            backend_tools.Cursors.SELECT_REGION: 'crosshair',
            backend_tools.Cursors.MOVE: 'move',
            backend_tools.Cursors.WAIT: 'wait',
            backend_tools.Cursors.RESIZE_HORIZONTAL: 'ew-resize',
            backend_tools.Cursors.RESIZE_VERTICAL: 'ns-resize',
        }, cursor=cursor)
        self.send_event('cursor', cursor=cursor)

    def set_image_mode(self, mode):
        """
        Set the image mode for any subsequent images which will be sent
        to the clients. The modes may currently be either 'full' or 'diff'.

        Note: diff images may not contain transparency, therefore upon
        draw this mode may be changed if the resulting image has any
        transparent component.
        """
        _api.check_in_list(['full', 'diff'], mode=mode)
        if self._current_image_mode != mode:
            self._current_image_mode = mode
            self.handle_send_image_mode(None)

    def get_diff_image(self):
        if self._png_is_old:
            renderer = self.get_renderer()

            pixels = np.asarray(renderer.buffer_rgba())
            # The buffer is created as type uint32 so that entire
            # pixels can be compared in one numpy call, rather than
            # needing to compare each plane separately.
            buff = pixels.view(np.uint32).squeeze(2)

            if (self._force_full
                    # If the buffer has changed size we need to do a full draw.
                    or buff.shape != self._last_buff.shape
                    # If any pixels have transparency, we need to force a full
                    # draw as we cannot overlay new on top of old.
                    or (pixels[:, :, 3] != 255).any()):
                self.set_image_mode('full')
                output = buff
            else:
                self.set_image_mode('diff')
                diff = buff != self._last_buff
                output = np.where(diff, buff, 0)

            # Store the current buffer so we can compute the next diff.
            self._last_buff = buff.copy()
            self._force_full = False
            self._png_is_old = False

            data = output.view(dtype=np.uint8).reshape((*output.shape, 4))
            with BytesIO() as png:
                Image.fromarray(data).save(png, format="png")
                return png.getvalue()

    def handle_event(self, event):
        e_type = event['type']
        handler = getattr(self, f'handle_{e_type}',
                          self.handle_unknown_event)
        return handler(event)

    def handle_unknown_event(self, event):
        _log.warning('Unhandled message type %s. %s', event["type"], event)

    def handle_ack(self, event):
        # Network latency tends to decrease if traffic is flowing
        # in both directions.  Therefore, the browser sends back
        # an "ack" message after each image frame is received.
        # This could also be used as a simple sanity check in the
        # future, but for now the performance increase is enough
        # to justify it, even if the server does nothing with it.
        pass

    def handle_draw(self, event):
        self.draw()

    def _handle_mouse(self, event):
        x = event['x']
        y = event['y']
        y = self.get_renderer().height - y
        self._last_mouse_xy = x, y
        e_type = event['type']
        button = event['button'] + 1  # JS numbers off by 1 compared to mpl.
        buttons = {  # JS ordering different compared to mpl.
            button for button, mask in [
                (MouseButton.LEFT, 1),
                (MouseButton.RIGHT, 2),
                (MouseButton.MIDDLE, 4),
                (MouseButton.BACK, 8),
                (MouseButton.FORWARD, 16),
            ] if event['buttons'] & mask  # State *after* press/release.
        }
        modifiers = event['modifiers']
        guiEvent = event.get('guiEvent')
        if e_type in ['button_press', 'button_release']:
            MouseEvent(e_type + '_event', self, x, y, button,
                       modifiers=modifiers, guiEvent=guiEvent)._process()
        elif e_type == 'dblclick':
            MouseEvent('button_press_event', self, x, y, button, dblclick=True,
                       modifiers=modifiers, guiEvent=guiEvent)._process()
        elif e_type == 'scroll':
            MouseEvent('scroll_event', self, x, y, step=event['step'],
                       modifiers=modifiers, guiEvent=guiEvent)._process()
        elif e_type == 'motion_notify':
            MouseEvent(e_type + '_event', self, x, y,
                       buttons=buttons, modifiers=modifiers, guiEvent=guiEvent,
                       )._process()
        elif e_type in ['figure_enter', 'figure_leave']:
            LocationEvent(e_type + '_event', self, x, y,
                          modifiers=modifiers, guiEvent=guiEvent)._process()

    handle_button_press = handle_button_release = handle_dblclick = \
        handle_figure_enter = handle_figure_leave = handle_motion_notify = \
        handle_scroll = _handle_mouse

    def _handle_key(self, event):
        KeyEvent(event['type'] + '_event', self,
                 _handle_key(event['key']), *self._last_mouse_xy,
                 guiEvent=event.get('guiEvent'))._process()
    handle_key_press = handle_key_release = _handle_key

    def handle_toolbar_button(self, event):
        # TODO: Be more suspicious of the input
        getattr(self.toolbar, event['name'])()

    def handle_refresh(self, event):
        figure_label = self.figure.get_label()
        if not figure_label:
            figure_label = f"Figure {self.manager.num}"
        self.send_event('figure_label', label=figure_label)
        self._force_full = True
        if self.toolbar:
            # Normal toolbar init would refresh this, but it happens before the
            # browser canvas is set up.
            self.toolbar.set_history_buttons()
        self.draw_idle()

    def handle_resize(self, event):
        x = int(event.get('width', 800)) * self.device_pixel_ratio
        y = int(event.get('height', 800)) * self.device_pixel_ratio
        fig = self.figure
        # An attempt at approximating the figure size in pixels.
        fig.set_size_inches(x / fig.dpi, y / fig.dpi, forward=False)
        # Acknowledge the resize, and force the viewer to update the
        # canvas size to the figure's new size (which is hopefully
        # identical or within a pixel or so).
        self._png_is_old = True
        self.manager.resize(*fig.bbox.size, forward=False)
        ResizeEvent('resize_event', self)._process()
        self.draw_idle()

    def handle_send_image_mode(self, event):
        # The client requests notification of what the current image mode is.
        self.send_event('image_mode', mode=self._current_image_mode)

    def handle_set_device_pixel_ratio(self, event):
        self._handle_set_device_pixel_ratio(event.get('device_pixel_ratio', 1))

    def handle_set_dpi_ratio(self, event):
        # This handler is for backwards-compatibility with older ipympl.
        self._handle_set_device_pixel_ratio(event.get('dpi_ratio', 1))

    def _handle_set_device_pixel_ratio(self, device_pixel_ratio):
        if self._set_device_pixel_ratio(device_pixel_ratio):
            self._force_full = True
            self.draw_idle()

    def send_event(self, event_type, **kwargs):
        if self.manager:
            self.manager._send_event(event_type, **kwargs)


_ALLOWED_TOOL_ITEMS = {
    'home',
    'back',
    'forward',
    'pan',
    'zoom',
    'download',
    None,
}


class NavigationToolbar2WebAgg(backend_bases.NavigationToolbar2):

    # Use the standard toolbar items + download button
    toolitems = [
        (text, tooltip_text, image_file, name_of_method)
        for text, tooltip_text, image_file, name_of_method
        in (*backend_bases.NavigationToolbar2.toolitems,
            ('Download', 'Download plot', 'filesave', 'download'))
        if name_of_method in _ALLOWED_TOOL_ITEMS
    ]

    def __init__(self, canvas):
        self.message = ''
        super().__init__(canvas)

    def set_message(self, message):
        if message != self.message:
            self.canvas.send_event("message", message=message)
        self.message = message

    def draw_rubberband(self, event, x0, y0, x1, y1):
        self.canvas.send_event("rubberband", x0=x0, y0=y0, x1=x1, y1=y1)

    def remove_rubberband(self):
        self.canvas.send_event("rubberband", x0=-1, y0=-1, x1=-1, y1=-1)

    def save_figure(self, *args):
        """Save the current figure."""
        self.canvas.send_event('save')
        return self.UNKNOWN_SAVED_STATUS

    def pan(self):
        super().pan()
        self.canvas.send_event('navigate_mode', mode=self.mode.name)

    def zoom(self):
        super().zoom()
        self.canvas.send_event('navigate_mode', mode=self.mode.name)

    def set_history_buttons(self):
        can_backward = self._nav_stack._pos > 0
        can_forward = self._nav_stack._pos < len(self._nav_stack) - 1
        self.canvas.send_event('history_buttons',
                               Back=can_backward, Forward=can_forward)


class FigureManagerWebAgg(backend_bases.FigureManagerBase):
    # This must be None to not break ipympl
    _toolbar2_class = None
    ToolbarCls = NavigationToolbar2WebAgg
    _window_title = "Matplotlib"

    def __init__(self, canvas, num):
        self.web_sockets = set()
        super().__init__(canvas, num)

    def show(self):
        pass

    def resize(self, w, h, forward=True):
        self._send_event(
            'resize',
            size=(w / self.canvas.device_pixel_ratio,
                  h / self.canvas.device_pixel_ratio),
            forward=forward)

    def set_window_title(self, title):
        self._send_event('figure_label', label=title)
        self._window_title = title

    def get_window_title(self):
        return self._window_title

    # The following methods are specific to FigureManagerWebAgg

    def add_web_socket(self, web_socket):
        assert hasattr(web_socket, 'send_binary')
        assert hasattr(web_socket, 'send_json')
        self.web_sockets.add(web_socket)
        self.resize(*self.canvas.figure.bbox.size)
        self._send_event('refresh')

    def remove_web_socket(self, web_socket):
        self.web_sockets.remove(web_socket)

    def handle_json(self, content):
        self.canvas.handle_event(content)

    def refresh_all(self):
        if self.web_sockets:
            diff = self.canvas.get_diff_image()
            if diff is not None:
                for s in self.web_sockets:
                    s.send_binary(diff)

    @classmethod
    def get_javascript(cls, stream=None):
        if stream is None:
            output = StringIO()
        else:
            output = stream

        output.write((Path(__file__).parent / "web_backend/js/mpl.js")
                     .read_text(encoding="utf-8"))

        toolitems = []
        for name, tooltip, image, method in cls.ToolbarCls.toolitems:
            if name is None:
                toolitems.append(['', '', '', ''])
            else:
                toolitems.append([name, tooltip, image, method])
        output.write(f"mpl.toolbar_items = {json.dumps(toolitems)};\n\n")

        extensions = []
        for filetype, ext in sorted(FigureCanvasWebAggCore.
                                    get_supported_filetypes_grouped().
                                    items()):
            extensions.append(ext[0])
        output.write(f"mpl.extensions = {json.dumps(extensions)};\n\n")

        output.write("mpl.default_extension = {};".format(
            json.dumps(FigureCanvasWebAggCore.get_default_filetype())))

        if stream is None:
            return output.getvalue()

    @classmethod
    def get_static_file_path(cls):
        return os.path.join(os.path.dirname(__file__), 'web_backend')

    def _send_event(self, event_type, **kwargs):
        payload = {'type': event_type, **kwargs}
        for s in self.web_sockets:
            s.send_json(payload)


@_Backend.export
class _BackendWebAggCoreAgg(_Backend):
    FigureCanvas = FigureCanvasWebAggCore
    FigureManager = FigureManagerWebAgg
