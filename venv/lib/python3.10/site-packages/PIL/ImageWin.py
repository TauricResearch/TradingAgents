#
# The Python Imaging Library.
# $Id$
#
# a Windows DIB display interface
#
# History:
# 1996-05-20 fl   Created
# 1996-09-20 fl   Fixed subregion exposure
# 1997-09-21 fl   Added draw primitive (for tzPrint)
# 2003-05-21 fl   Added experimental Window/ImageWindow classes
# 2003-09-05 fl   Added fromstring/tostring methods
#
# Copyright (c) Secret Labs AB 1997-2003.
# Copyright (c) Fredrik Lundh 1996-2003.
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

from . import Image


class HDC:
    """
    Wraps an HDC integer. The resulting object can be passed to the
    :py:meth:`~PIL.ImageWin.Dib.draw` and :py:meth:`~PIL.ImageWin.Dib.expose`
    methods.
    """

    def __init__(self, dc: int) -> None:
        self.dc = dc

    def __int__(self) -> int:
        return self.dc


class HWND:
    """
    Wraps an HWND integer. The resulting object can be passed to the
    :py:meth:`~PIL.ImageWin.Dib.draw` and :py:meth:`~PIL.ImageWin.Dib.expose`
    methods, instead of a DC.
    """

    def __init__(self, wnd: int) -> None:
        self.wnd = wnd

    def __int__(self) -> int:
        return self.wnd


class Dib:
    """
    A Windows bitmap with the given mode and size.  The mode can be one of "1",
    "L", "P", or "RGB".

    If the display requires a palette, this constructor creates a suitable
    palette and associates it with the image. For an "L" image, 128 graylevels
    are allocated. For an "RGB" image, a 6x6x6 colour cube is used, together
    with 20 graylevels.

    To make sure that palettes work properly under Windows, you must call the
    ``palette`` method upon certain events from Windows.

    :param image: Either a PIL image, or a mode string. If a mode string is
                  used, a size must also be given.  The mode can be one of "1",
                  "L", "P", or "RGB".
    :param size: If the first argument is a mode string, this
                 defines the size of the image.
    """

    def __init__(
        self, image: Image.Image | str, size: tuple[int, int] | None = None
    ) -> None:
        if isinstance(image, str):
            mode = image
            image = ""
            if size is None:
                msg = "If first argument is mode, size is required"
                raise ValueError(msg)
        else:
            mode = image.mode
            size = image.size
        if mode not in ["1", "L", "P", "RGB"]:
            mode = Image.getmodebase(mode)
        self.image = Image.core.display(mode, size)
        self.mode = mode
        self.size = size
        if image:
            assert not isinstance(image, str)
            self.paste(image)

    def expose(self, handle: int | HDC | HWND) -> None:
        """
        Copy the bitmap contents to a device context.

        :param handle: Device context (HDC), cast to a Python integer, or an
                       HDC or HWND instance.  In PythonWin, you can use
                       ``CDC.GetHandleAttrib()`` to get a suitable handle.
        """
        handle_int = int(handle)
        if isinstance(handle, HWND):
            dc = self.image.getdc(handle_int)
            try:
                self.image.expose(dc)
            finally:
                self.image.releasedc(handle_int, dc)
        else:
            self.image.expose(handle_int)

    def draw(
        self,
        handle: int | HDC | HWND,
        dst: tuple[int, int, int, int],
        src: tuple[int, int, int, int] | None = None,
    ) -> None:
        """
        Same as expose, but allows you to specify where to draw the image, and
        what part of it to draw.

        The destination and source areas are given as 4-tuple rectangles. If
        the source is omitted, the entire image is copied. If the source and
        the destination have different sizes, the image is resized as
        necessary.
        """
        if src is None:
            src = (0, 0) + self.size
        handle_int = int(handle)
        if isinstance(handle, HWND):
            dc = self.image.getdc(handle_int)
            try:
                self.image.draw(dc, dst, src)
            finally:
                self.image.releasedc(handle_int, dc)
        else:
            self.image.draw(handle_int, dst, src)

    def query_palette(self, handle: int | HDC | HWND) -> int:
        """
        Installs the palette associated with the image in the given device
        context.

        This method should be called upon **QUERYNEWPALETTE** and
        **PALETTECHANGED** events from Windows. If this method returns a
        non-zero value, one or more display palette entries were changed, and
        the image should be redrawn.

        :param handle: Device context (HDC), cast to a Python integer, or an
                       HDC or HWND instance.
        :return: The number of entries that were changed (if one or more entries,
                 this indicates that the image should be redrawn).
        """
        handle_int = int(handle)
        if isinstance(handle, HWND):
            handle = self.image.getdc(handle_int)
            try:
                result = self.image.query_palette(handle)
            finally:
                self.image.releasedc(handle, handle)
        else:
            result = self.image.query_palette(handle_int)
        return result

    def paste(
        self, im: Image.Image, box: tuple[int, int, int, int] | None = None
    ) -> None:
        """
        Paste a PIL image into the bitmap image.

        :param im: A PIL image.  The size must match the target region.
                   If the mode does not match, the image is converted to the
                   mode of the bitmap image.
        :param box: A 4-tuple defining the left, upper, right, and
                    lower pixel coordinate.  See :ref:`coordinate-system`. If
                    None is given instead of a tuple, all of the image is
                    assumed.
        """
        im.load()
        if self.mode != im.mode:
            im = im.convert(self.mode)
        if box:
            self.image.paste(im.im, box)
        else:
            self.image.paste(im.im)

    def frombytes(self, buffer: bytes) -> None:
        """
        Load display memory contents from byte data.

        :param buffer: A buffer containing display data (usually
                       data returned from :py:func:`~PIL.ImageWin.Dib.tobytes`)
        """
        self.image.frombytes(buffer)

    def tobytes(self) -> bytes:
        """
        Copy display memory contents to bytes object.

        :return: A bytes object containing display data.
        """
        return self.image.tobytes()


class Window:
    """Create a Window with the given title size."""

    def __init__(
        self, title: str = "PIL", width: int | None = None, height: int | None = None
    ) -> None:
        self.hwnd = Image.core.createwindow(
            title, self.__dispatcher, width or 0, height or 0
        )

    def __dispatcher(self, action: str, *args: int) -> None:
        getattr(self, f"ui_handle_{action}")(*args)

    def ui_handle_clear(self, dc: int, x0: int, y0: int, x1: int, y1: int) -> None:
        pass

    def ui_handle_damage(self, x0: int, y0: int, x1: int, y1: int) -> None:
        pass

    def ui_handle_destroy(self) -> None:
        pass

    def ui_handle_repair(self, dc: int, x0: int, y0: int, x1: int, y1: int) -> None:
        pass

    def ui_handle_resize(self, width: int, height: int) -> None:
        pass

    def mainloop(self) -> None:
        Image.core.eventloop()


class ImageWindow(Window):
    """Create an image window which displays the given image."""

    def __init__(self, image: Image.Image | Dib, title: str = "PIL") -> None:
        if not isinstance(image, Dib):
            image = Dib(image)
        self.image = image
        width, height = image.size
        super().__init__(title, width=width, height=height)

    def ui_handle_repair(self, dc: int, x0: int, y0: int, x1: int, y1: int) -> None:
        self.image.draw(dc, (x0, y0, x1, y1))
