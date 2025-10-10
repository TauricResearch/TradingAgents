from contextlib import nullcontext

from .backend_cairo import FigureCanvasCairo
from .backend_gtk3 import GLib, Gtk, FigureCanvasGTK3, _BackendGTK3


class FigureCanvasGTK3Cairo(FigureCanvasCairo, FigureCanvasGTK3):
    def on_draw_event(self, widget, ctx):
        if self._idle_draw_id:
            GLib.source_remove(self._idle_draw_id)
            self._idle_draw_id = 0
            self.draw()

        with (self.toolbar._wait_cursor_for_draw_cm() if self.toolbar
              else nullcontext()):
            allocation = self.get_allocation()
            # Render the background before scaling, as the allocated size here is in
            # logical pixels.
            Gtk.render_background(
                self.get_style_context(), ctx,
                0, 0, allocation.width, allocation.height)
            scale = self.device_pixel_ratio
            # Scale physical drawing to logical size.
            ctx.scale(1 / scale, 1 / scale)
            self._renderer.set_context(ctx)
            # Set renderer to physical size so it renders in full resolution.
            self._renderer.width = allocation.width * scale
            self._renderer.height = allocation.height * scale
            self._renderer.dpi = self.figure.dpi
            self.figure.draw(self._renderer)


@_BackendGTK3.export
class _BackendGTK3Cairo(_BackendGTK3):
    FigureCanvas = FigureCanvasGTK3Cairo
