#
# The Python Imaging Library.
# $Id$
#
# Windows Cursor support for PIL
#
# notes:
#       uses BmpImagePlugin.py to read the bitmap data.
#
# history:
#       96-05-27 fl     Created
#
# Copyright (c) Secret Labs AB 1997.
# Copyright (c) Fredrik Lundh 1996.
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

from . import BmpImagePlugin, Image, ImageFile
from ._binary import i16le as i16
from ._binary import i32le as i32

#
# --------------------------------------------------------------------


def _accept(prefix: bytes) -> bool:
    return prefix.startswith(b"\0\0\2\0")


##
# Image plugin for Windows Cursor files.


class CurImageFile(BmpImagePlugin.BmpImageFile):
    format = "CUR"
    format_description = "Windows Cursor"

    def _open(self) -> None:
        offset = self.fp.tell()

        # check magic
        s = self.fp.read(6)
        if not _accept(s):
            msg = "not a CUR file"
            raise SyntaxError(msg)

        # pick the largest cursor in the file
        m = b""
        for i in range(i16(s, 4)):
            s = self.fp.read(16)
            if not m:
                m = s
            elif s[0] > m[0] and s[1] > m[1]:
                m = s
        if not m:
            msg = "No cursors were found"
            raise TypeError(msg)

        # load as bitmap
        self._bitmap(i32(m, 12) + offset)

        # patch up the bitmap height
        self._size = self.size[0], self.size[1] // 2
        d, e, o, a = self.tile[0]
        self.tile[0] = ImageFile._Tile(d, (0, 0) + self.size, o, a)


#
# --------------------------------------------------------------------

Image.register_open(CurImageFile.format, CurImageFile, _accept)

Image.register_extension(CurImageFile.format, ".cur")
