#
# The Python Imaging Library.
# $Id$
#
# PCD file handling
#
# History:
#       96-05-10 fl     Created
#       96-05-27 fl     Added draft mode (128x192, 256x384)
#
# Copyright (c) Secret Labs AB 1997.
# Copyright (c) Fredrik Lundh 1996.
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

from . import Image, ImageFile

##
# Image plugin for PhotoCD images.  This plugin only reads the 768x512
# image from the file; higher resolutions are encoded in a proprietary
# encoding.


class PcdImageFile(ImageFile.ImageFile):
    format = "PCD"
    format_description = "Kodak PhotoCD"

    def _open(self) -> None:
        # rough
        assert self.fp is not None

        self.fp.seek(2048)
        s = self.fp.read(2048)

        if not s.startswith(b"PCD_"):
            msg = "not a PCD file"
            raise SyntaxError(msg)

        orientation = s[1538] & 3
        self.tile_post_rotate = None
        if orientation == 1:
            self.tile_post_rotate = 90
        elif orientation == 3:
            self.tile_post_rotate = -90

        self._mode = "RGB"
        self._size = 768, 512  # FIXME: not correct for rotated images!
        self.tile = [ImageFile._Tile("pcd", (0, 0) + self.size, 96 * 2048)]

    def load_end(self) -> None:
        if self.tile_post_rotate:
            # Handle rotated PCDs
            self.im = self.im.rotate(self.tile_post_rotate)
            self._size = self.im.size


#
# registry

Image.register_open(PcdImageFile.format, PcdImageFile)

Image.register_extension(PcdImageFile.format, ".pcd")
