from contextlib import nullcontext

from .backend_cairo import FigureCanvasCairo
from .backend_gtk4 import GLib, Gtk, FigureCanvasGTK4, _BackendGTK4


class FigureCanvasGTK4Cairo(FigureCanvasCairo, FigureCanvasGTK4):
    def _set_device_pixel_ratio(self, ratio):
        # Cairo in GTK4 always uses logical pixels, so we don't need to do anything for
        # changes to the device pixel ratio.
        return False

    def on_draw_event(self, widget, ctx):
        if self._idle_draw_id:
            GLib.source_remove(self._idle_draw_id)
            self._idle_draw_id = 0
            self.draw()

        with (self.toolbar._wait_cursor_for_draw_cm() if self.toolbar
              else nullcontext()):
            self._renderer.set_context(ctx)
            allocation = self.get_allocation()
            Gtk.render_background(
                self.get_style_context(), ctx,
                allocation.x, allocation.y,
                allocation.width, allocation.height)
            self.figure.draw(self._renderer)


@_BackendGTK4.export
class _BackendGTK4Cairo(_BackendGTK4):
    FigureCanvas = FigureCanvasGTK4Cairo
