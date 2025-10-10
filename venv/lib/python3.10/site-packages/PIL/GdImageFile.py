#
# The Python Imaging Library.
# $Id$
#
# GD file handling
#
# History:
# 1996-04-12 fl   Created
#
# Copyright (c) 1997 by Secret Labs AB.
# Copyright (c) 1996 by Fredrik Lundh.
#
# See the README file for information on usage and redistribution.
#


"""
.. note::
    This format cannot be automatically recognized, so the
    class is not registered for use with :py:func:`PIL.Image.open()`.  To open a
    gd file, use the :py:func:`PIL.GdImageFile.open()` function instead.

.. warning::
    THE GD FORMAT IS NOT DESIGNED FOR DATA INTERCHANGE.  This
    implementation is provided for convenience and demonstrational
    purposes only.
"""
from __future__ import annotations

from typing import IO

from . import ImageFile, ImagePalette, UnidentifiedImageError
from ._binary import i16be as i16
from ._binary import i32be as i32
from ._typing import StrOrBytesPath


class GdImageFile(ImageFile.ImageFile):
    """
    Image plugin for the GD uncompressed format.  Note that this format
    is not supported by the standard :py:func:`PIL.Image.open()` function.  To use
    this plugin, you have to import the :py:mod:`PIL.GdImageFile` module and
    use the :py:func:`PIL.GdImageFile.open()` function.
    """

    format = "GD"
    format_description = "GD uncompressed images"

    def _open(self) -> None:
        # Header
        assert self.fp is not None

        s = self.fp.read(1037)

        if i16(s) not in [65534, 65535]:
            msg = "Not a valid GD 2.x .gd file"
            raise SyntaxError(msg)

        self._mode = "P"
        self._size = i16(s, 2), i16(s, 4)

        true_color = s[6]
        true_color_offset = 2 if true_color else 0

        # transparency index
        tindex = i32(s, 7 + true_color_offset)
        if tindex < 256:
            self.info["transparency"] = tindex

        self.palette = ImagePalette.raw(
            "RGBX", s[7 + true_color_offset + 6 : 7 + true_color_offset + 6 + 256 * 4]
        )

        self.tile = [
            ImageFile._Tile(
                "raw",
                (0, 0) + self.size,
                7 + true_color_offset + 6 + 256 * 4,
                "L",
            )
        ]


def open(fp: StrOrBytesPath | IO[bytes], mode: str = "r") -> GdImageFile:
    """
    Load texture from a GD image file.

    :param fp: GD file name, or an opened file handle.
    :param mode: Optional mode.  In this version, if the mode argument
        is given, it must be "r".
    :returns: An image instance.
    :raises OSError: If the image could not be read.
    """
    if mode != "r":
        msg = "bad mode"
        raise ValueError(msg)

    try:
        return GdImageFile(fp)
    except SyntaxError as e:
        msg = "cannot identify this image file"
        raise UnidentifiedImageError(msg) from e
