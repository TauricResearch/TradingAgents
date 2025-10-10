#
# The Python Imaging Library.
# $Id$
#
# a Tk display interface
#
# History:
# 96-04-08 fl   Created
# 96-09-06 fl   Added getimage method
# 96-11-01 fl   Rewritten, removed image attribute and crop method
# 97-05-09 fl   Use PyImagingPaste method instead of image type
# 97-05-12 fl   Minor tweaks to match the IFUNC95 interface
# 97-05-17 fl   Support the "pilbitmap" booster patch
# 97-06-05 fl   Added file= and data= argument to image constructors
# 98-03-09 fl   Added width and height methods to Image classes
# 98-07-02 fl   Use default mode for "P" images without palette attribute
# 98-07-02 fl   Explicitly destroy Tkinter image objects
# 99-07-24 fl   Support multiple Tk interpreters (from Greg Couch)
# 99-07-26 fl   Automatically hook into Tkinter (if possible)
# 99-08-15 fl   Hook uses _imagingtk instead of _imaging
#
# Copyright (c) 1997-1999 by Secret Labs AB
# Copyright (c) 1996-1997 by Fredrik Lundh
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import tkinter
from io import BytesIO
from typing import Any

from . import Image, ImageFile

TYPE_CHECKING = False
if TYPE_CHECKING:
    from ._typing import CapsuleType

# --------------------------------------------------------------------
# Check for Tkinter interface hooks


def _get_image_from_kw(kw: dict[str, Any]) -> ImageFile.ImageFile | None:
    source = None
    if "file" in kw:
        source = kw.pop("file")
    elif "data" in kw:
        source = BytesIO(kw.pop("data"))
    if not source:
        return None
    return Image.open(source)


def _pyimagingtkcall(
    command: str, photo: PhotoImage | tkinter.PhotoImage, ptr: CapsuleType
) -> None:
    tk = photo.tk
    try:
        tk.call(command, photo, repr(ptr))
    except tkinter.TclError:
        # activate Tkinter hook
        # may raise an error if it cannot attach to Tkinter
        from . import _imagingtk

        _imagingtk.tkinit(tk.interpaddr())
        tk.call(command, photo, repr(ptr))


# --------------------------------------------------------------------
# PhotoImage


class PhotoImage:
    """
    A Tkinter-compatible photo image.  This can be used
    everywhere Tkinter expects an image object.  If the image is an RGBA
    image, pixels having alpha 0 are treated as transparent.

    The constructor takes either a PIL image, or a mode and a size.
    Alternatively, you can use the ``file`` or ``data`` options to initialize
    the photo image object.

    :param image: Either a PIL image, or a mode string.  If a mode string is
                  used, a size must also be given.
    :param size: If the first argument is a mode string, this defines the size
                 of the image.
    :keyword file: A filename to load the image from (using
                   ``Image.open(file)``).
    :keyword data: An 8-bit string containing image data (as loaded from an
                   image file).
    """

    def __init__(
        self,
        image: Image.Image | str | None = None,
        size: tuple[int, int] | None = None,
        **kw: Any,
    ) -> None:
        # Tk compatibility: file or data
        if image is None:
            image = _get_image_from_kw(kw)

        if image is None:
            msg = "Image is required"
            raise ValueError(msg)
        elif isinstance(image, str):
            mode = image
            image = None

            if size is None:
                msg = "If first argument is mode, size is required"
                raise ValueError(msg)
        else:
            # got an image instead of a mode
            mode = image.mode
            if mode == "P":
                # palette mapped data
                image.apply_transparency()
                image.load()
                mode = image.palette.mode if image.palette else "RGB"
            size = image.size
            kw["width"], kw["height"] = size

        if mode not in ["1", "L", "RGB", "RGBA"]:
            mode = Image.getmodebase(mode)

        self.__mode = mode
        self.__size = size
        self.__photo = tkinter.PhotoImage(**kw)
        self.tk = self.__photo.tk
        if image:
            self.paste(image)

    def __del__(self) -> None:
        try:
            name = self.__photo.name
        except AttributeError:
            return
        self.__photo.name = None
        try:
            self.__photo.tk.call("image", "delete", name)
        except Exception:
            pass  # ignore internal errors

    def __str__(self) -> str:
        """
        Get the Tkinter photo image identifier.  This method is automatically
        called by Tkinter whenever a PhotoImage object is passed to a Tkinter
        method.

        :return: A Tkinter photo image identifier (a string).
        """
        return str(self.__photo)

    def width(self) -> int:
        """
        Get the width of the image.

        :return: The width, in pixels.
        """
        return self.__size[0]

    def height(self) -> int:
        """
        Get the height of the image.

        :return: The height, in pixels.
        """
        return self.__size[1]

    def paste(self, im: Image.Image) -> None:
        """
        Paste a PIL image into the photo image.  Note that this can
        be very slow if the photo image is displayed.

        :param im: A PIL image. The size must match the target region.  If the
                   mode does not match, the image is converted to the mode of
                   the bitmap image.
        """
        # convert to blittable
        ptr = im.getim()
        image = im.im
        if not image.isblock() or im.mode != self.__mode:
            block = Image.core.new_block(self.__mode, im.size)
            image.convert2(block, image)  # convert directly between buffers
            ptr = block.ptr

        _pyimagingtkcall("PyImagingPhoto", self.__photo, ptr)


# --------------------------------------------------------------------
# BitmapImage


class BitmapImage:
    """
    A Tkinter-compatible bitmap image.  This can be used everywhere Tkinter
    expects an image object.

    The given image must have mode "1".  Pixels having value 0 are treated as
    transparent.  Options, if any, are passed on to Tkinter.  The most commonly
    used option is ``foreground``, which is used to specify the color for the
    non-transparent parts.  See the Tkinter documentation for information on
    how to specify colours.

    :param image: A PIL image.
    """

    def __init__(self, image: Image.Image | None = None, **kw: Any) -> None:
        # Tk compatibility: file or data
        if image is None:
            image = _get_image_from_kw(kw)

        if image is None:
            msg = "Image is required"
            raise ValueError(msg)
        self.__mode = image.mode
        self.__size = image.size

        self.__photo = tkinter.BitmapImage(data=image.tobitmap(), **kw)

    def __del__(self) -> None:
        try:
            name = self.__photo.name
        except AttributeError:
            return
        self.__photo.name = None
        try:
            self.__photo.tk.call("image", "delete", name)
        except Exception:
            pass  # ignore internal errors

    def width(self) -> int:
        """
        Get the width of the image.

        :return: The width, in pixels.
        """
        return self.__size[0]

    def height(self) -> int:
        """
        Get the height of the image.

        :return: The height, in pixels.
        """
        return self.__size[1]

    def __str__(self) -> str:
        """
        Get the Tkinter bitmap image identifier.  This method is automatically
        called by Tkinter whenever a BitmapImage object is passed to a Tkinter
        method.

        :return: A Tkinter bitmap image identifier (a string).
        """
        return str(self.__photo)


def getimage(photo: PhotoImage) -> Image.Image:
    """Copies the contents of a PhotoImage to a PIL image memory."""
    im = Image.new("RGBA", (photo.width(), photo.height()))

    _pyimagingtkcall("PyImagingPhotoGet", photo, im.getim())

    return im
