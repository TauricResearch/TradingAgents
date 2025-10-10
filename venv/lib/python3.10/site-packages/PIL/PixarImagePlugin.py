#
# The Python Imaging Library.
# $Id$
#
# PIXAR raster support for PIL
#
# history:
#       97-01-29 fl     Created
#
# notes:
#       This is incomplete; it is based on a few samples created with
#       Photoshop 2.5 and 3.0, and a summary description provided by
#       Greg Coats <gcoats@labiris.er.usgs.gov>.  Hopefully, "L" and
#       "RGBA" support will be added in future versions.
#
# Copyright (c) Secret Labs AB 1997.
# Copyright (c) Fredrik Lundh 1997.
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

from . import Image, ImageFile
from ._binary import i16le as i16

#
# helpers


def _accept(prefix: bytes) -> bool:
    return prefix.startswith(b"\200\350\000\000")


##
# Image plugin for PIXAR raster images.


class PixarImageFile(ImageFile.ImageFile):
    format = "PIXAR"
    format_description = "PIXAR raster image"

    def _open(self) -> None:
        # assuming a 4-byte magic label
        assert self.fp is not None

        s = self.fp.read(4)
        if not _accept(s):
            msg = "not a PIXAR file"
            raise SyntaxError(msg)

        # read rest of header
        s = s + self.fp.read(508)

        self._size = i16(s, 418), i16(s, 416)

        # get channel/depth descriptions
        mode = i16(s, 424), i16(s, 426)

        if mode == (14, 2):
            self._mode = "RGB"
        # FIXME: to be continued...

        # create tile descriptor (assuming "dumped")
        self.tile = [ImageFile._Tile("raw", (0, 0) + self.size, 1024, self.mode)]


#
# --------------------------------------------------------------------

Image.register_open(PixarImageFile.format, PixarImageFile, _accept)

Image.register_extension(PixarImageFile.format, ".pxr")
