#
# The Python Imaging Library.
# $Id$
#
# a simple Qt image interface.
#
# history:
# 2006-06-03 fl: created
# 2006-06-04 fl: inherit from QImage instead of wrapping it
# 2006-06-05 fl: removed toimage helper; move string support to ImageQt
# 2013-11-13 fl: add support for Qt5 (aurelien.ballier@cyclonit.com)
#
# Copyright (c) 2006 by Secret Labs AB
# Copyright (c) 2006 by Fredrik Lundh
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import sys
from io import BytesIO
from typing import Any, Callable, Union

from . import Image
from ._util import is_path

TYPE_CHECKING = False
if TYPE_CHECKING:
    import PyQt6
    import PySide6

    from . import ImageFile

    QBuffer: type
    QByteArray = Union[PyQt6.QtCore.QByteArray, PySide6.QtCore.QByteArray]
    QIODevice = Union[PyQt6.QtCore.QIODevice, PySide6.QtCore.QIODevice]
    QImage = Union[PyQt6.QtGui.QImage, PySide6.QtGui.QImage]
    QPixmap = Union[PyQt6.QtGui.QPixmap, PySide6.QtGui.QPixmap]

qt_version: str | None
qt_versions = [
    ["6", "PyQt6"],
    ["side6", "PySide6"],
]

# If a version has already been imported, attempt it first
qt_versions.sort(key=lambda version: version[1] in sys.modules, reverse=True)
for version, qt_module in qt_versions:
    try:
        qRgba: Callable[[int, int, int, int], int]
        if qt_module == "PyQt6":
            from PyQt6.QtCore import QBuffer, QIODevice
            from PyQt6.QtGui import QImage, QPixmap, qRgba
        elif qt_module == "PySide6":
            from PySide6.QtCore import QBuffer, QIODevice
            from PySide6.QtGui import QImage, QPixmap, qRgba
    except (ImportError, RuntimeError):
        continue
    qt_is_installed = True
    qt_version = version
    break
else:
    qt_is_installed = False
    qt_version = None


def rgb(r: int, g: int, b: int, a: int = 255) -> int:
    """(Internal) Turns an RGB color into a Qt compatible color integer."""
    # use qRgb to pack the colors, and then turn the resulting long
    # into a negative integer with the same bitpattern.
    return qRgba(r, g, b, a) & 0xFFFFFFFF


def fromqimage(im: QImage | QPixmap) -> ImageFile.ImageFile:
    """
    :param im: QImage or PIL ImageQt object
    """
    buffer = QBuffer()
    qt_openmode: object
    if qt_version == "6":
        try:
            qt_openmode = getattr(QIODevice, "OpenModeFlag")
        except AttributeError:
            qt_openmode = getattr(QIODevice, "OpenMode")
    else:
        qt_openmode = QIODevice
    buffer.open(getattr(qt_openmode, "ReadWrite"))
    # preserve alpha channel with png
    # otherwise ppm is more friendly with Image.open
    if im.hasAlphaChannel():
        im.save(buffer, "png")
    else:
        im.save(buffer, "ppm")

    b = BytesIO()
    b.write(buffer.data())
    buffer.close()
    b.seek(0)

    return Image.open(b)


def fromqpixmap(im: QPixmap) -> ImageFile.ImageFile:
    return fromqimage(im)


def align8to32(bytes: bytes, width: int, mode: str) -> bytes:
    """
    converts each scanline of data from 8 bit to 32 bit aligned
    """

    bits_per_pixel = {"1": 1, "L": 8, "P": 8, "I;16": 16}[mode]

    # calculate bytes per line and the extra padding if needed
    bits_per_line = bits_per_pixel * width
    full_bytes_per_line, remaining_bits_per_line = divmod(bits_per_line, 8)
    bytes_per_line = full_bytes_per_line + (1 if remaining_bits_per_line else 0)

    extra_padding = -bytes_per_line % 4

    # already 32 bit aligned by luck
    if not extra_padding:
        return bytes

    new_data = [
        bytes[i * bytes_per_line : (i + 1) * bytes_per_line] + b"\x00" * extra_padding
        for i in range(len(bytes) // bytes_per_line)
    ]

    return b"".join(new_data)


def _toqclass_helper(im: Image.Image | str | QByteArray) -> dict[str, Any]:
    data = None
    colortable = None
    exclusive_fp = False

    # handle filename, if given instead of image name
    if hasattr(im, "toUtf8"):
        # FIXME - is this really the best way to do this?
        im = str(im.toUtf8(), "utf-8")
    if is_path(im):
        im = Image.open(im)
        exclusive_fp = True
    assert isinstance(im, Image.Image)

    qt_format = getattr(QImage, "Format") if qt_version == "6" else QImage
    if im.mode == "1":
        format = getattr(qt_format, "Format_Mono")
    elif im.mode == "L":
        format = getattr(qt_format, "Format_Indexed8")
        colortable = [rgb(i, i, i) for i in range(256)]
    elif im.mode == "P":
        format = getattr(qt_format, "Format_Indexed8")
        palette = im.getpalette()
        assert palette is not None
        colortable = [rgb(*palette[i : i + 3]) for i in range(0, len(palette), 3)]
    elif im.mode == "RGB":
        # Populate the 4th channel with 255
        im = im.convert("RGBA")

        data = im.tobytes("raw", "BGRA")
        format = getattr(qt_format, "Format_RGB32")
    elif im.mode == "RGBA":
        data = im.tobytes("raw", "BGRA")
        format = getattr(qt_format, "Format_ARGB32")
    elif im.mode == "I;16":
        im = im.point(lambda i: i * 256)

        format = getattr(qt_format, "Format_Grayscale16")
    else:
        if exclusive_fp:
            im.close()
        msg = f"unsupported image mode {repr(im.mode)}"
        raise ValueError(msg)

    size = im.size
    __data = data or align8to32(im.tobytes(), size[0], im.mode)
    if exclusive_fp:
        im.close()
    return {"data": __data, "size": size, "format": format, "colortable": colortable}


if qt_is_installed:

    class ImageQt(QImage):  # type: ignore[misc]
        def __init__(self, im: Image.Image | str | QByteArray) -> None:
            """
            An PIL image wrapper for Qt.  This is a subclass of PyQt's QImage
            class.

            :param im: A PIL Image object, or a file name (given either as
                Python string or a PyQt string object).
            """
            im_data = _toqclass_helper(im)
            # must keep a reference, or Qt will crash!
            # All QImage constructors that take data operate on an existing
            # buffer, so this buffer has to hang on for the life of the image.
            # Fixes https://github.com/python-pillow/Pillow/issues/1370
            self.__data = im_data["data"]
            super().__init__(
                self.__data,
                im_data["size"][0],
                im_data["size"][1],
                im_data["format"],
            )
            if im_data["colortable"]:
                self.setColorTable(im_data["colortable"])


def toqimage(im: Image.Image | str | QByteArray) -> ImageQt:
    return ImageQt(im)


def toqpixmap(im: Image.Image | str | QByteArray) -> QPixmap:
    qimage = toqimage(im)
    pixmap = getattr(QPixmap, "fromImage")(qimage)
    if qt_version == "6":
        pixmap.detach()
    return pixmap
