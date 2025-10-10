import numpy as np

from .. import cbook
from . import backend_agg, backend_gtk4
from .backend_gtk4 import GLib, Gtk, _BackendGTK4

import cairo  # Presence of cairo is already checked by _backend_gtk.


class FigureCanvasGTK4Agg(backend_agg.FigureCanvasAgg,
                          backend_gtk4.FigureCanvasGTK4):

    def on_draw_event(self, widget, ctx):
        if self._idle_draw_id:
            GLib.source_remove(self._idle_draw_id)
            self._idle_draw_id = 0
            self.draw()

        scale = self.device_pixel_ratio
        allocation = self.get_allocation()

        Gtk.render_background(
            self.get_style_context(), ctx,
            allocation.x, allocation.y,
            allocation.width, allocation.height)

        buf = cbook._unmultiplied_rgba8888_to_premultiplied_argb32(
            np.asarray(self.get_renderer().buffer_rgba()))
        height, width, _ = buf.shape
        image = cairo.ImageSurface.create_for_data(
            buf.ravel().data, cairo.FORMAT_ARGB32, width, height)
        image.set_device_scale(scale, scale)
        ctx.set_source_surface(image, 0, 0)
        ctx.paint()

        return False


@_BackendGTK4.export
class _BackendGTK4Agg(_BackendGTK4):
    FigureCanvas = FigureCanvasGTK4Agg
