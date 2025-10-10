"""
Render to qt from agg.
"""

import ctypes

from matplotlib.transforms import Bbox

from .qt_compat import QT_API, QtCore, QtGui
from .backend_agg import FigureCanvasAgg
from .backend_qt import _BackendQT, FigureCanvasQT
from .backend_qt import (  # noqa: F401 # pylint: disable=W0611
    FigureManagerQT, NavigationToolbar2QT)


class FigureCanvasQTAgg(FigureCanvasAgg, FigureCanvasQT):

    def paintEvent(self, event):
        """
        Copy the image from the Agg canvas to the qt.drawable.

        In Qt, all drawing should be done inside of here when a widget is
        shown onscreen.
        """
        self._draw_idle()  # Only does something if a draw is pending.

        # If the canvas does not have a renderer, then give up and wait for
        # FigureCanvasAgg.draw(self) to be called.
        if not hasattr(self, 'renderer'):
            return

        painter = QtGui.QPainter(self)
        try:
            # See documentation of QRect: bottom() and right() are off
            # by 1, so use left() + width() and top() + height().
            rect = event.rect()
            # scale rect dimensions using the screen dpi ratio to get
            # correct values for the Figure coordinates (rather than
            # QT5's coords)
            width = rect.width() * self.device_pixel_ratio
            height = rect.height() * self.device_pixel_ratio
            left, top = self.mouseEventCoords(rect.topLeft())
            # shift the "top" by the height of the image to get the
            # correct corner for our coordinate system
            bottom = top - height
            # same with the right side of the image
            right = left + width
            # create a buffer using the image bounding box
            bbox = Bbox([[left, bottom], [right, top]])
            buf = memoryview(self.copy_from_bbox(bbox))

            if QT_API == "PyQt6":
                from PyQt6 import sip
                ptr = int(sip.voidptr(buf))
            else:
                ptr = buf

            painter.eraseRect(rect)  # clear the widget canvas
            qimage = QtGui.QImage(ptr, buf.shape[1], buf.shape[0],
                                  QtGui.QImage.Format.Format_RGBA8888)
            qimage.setDevicePixelRatio(self.device_pixel_ratio)
            # set origin using original QT coordinates
            origin = QtCore.QPoint(rect.left(), rect.top())
            painter.drawImage(origin, qimage)
            # Adjust the buf reference count to work around a memory
            # leak bug in QImage under PySide.
            if QT_API == "PySide2" and QtCore.__version_info__ < (5, 12):
                ctypes.c_long.from_address(id(buf)).value = 1

            self._draw_rect_callback(painter)
        finally:
            painter.end()

    def print_figure(self, *args, **kwargs):
        super().print_figure(*args, **kwargs)
        # In some cases, Qt will itself trigger a paint event after closing the file
        # save dialog. When that happens, we need to be sure that the internal canvas is
        # re-drawn. However, if the user is using an automatically-chosen Qt backend but
        # saving with a different backend (such as pgf), we do not want to trigger a
        # full draw in Qt, so just set the flag for next time.
        self._draw_pending = True


@_BackendQT.export
class _BackendQTAgg(_BackendQT):
    FigureCanvas = FigureCanvasQTAgg
