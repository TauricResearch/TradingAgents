import sys

import numpy as np

from . import _backend_tk
from .backend_cairo import cairo, FigureCanvasCairo
from ._backend_tk import _BackendTk, FigureCanvasTk


class FigureCanvasTkCairo(FigureCanvasCairo, FigureCanvasTk):
    def draw(self):
        width = int(self.figure.bbox.width)
        height = int(self.figure.bbox.height)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        self._renderer.set_context(cairo.Context(surface))
        self._renderer.dpi = self.figure.dpi
        self.figure.draw(self._renderer)
        buf = np.reshape(surface.get_data(), (height, width, 4))
        _backend_tk.blit(
            self._tkphoto, buf,
            (2, 1, 0, 3) if sys.byteorder == "little" else (1, 2, 3, 0))


@_BackendTk.export
class _BackendTkCairo(_BackendTk):
    FigureCanvas = FigureCanvasTkCairo
