#
# The Python Imaging Library.
# $Id$
#
# MPEG file handling
#
# History:
#       95-09-09 fl     Created
#
# Copyright (c) Secret Labs AB 1997.
# Copyright (c) Fredrik Lundh 1995.
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

from . import Image, ImageFile
from ._binary import i8
from ._typing import SupportsRead

#
# Bitstream parser


class BitStream:
    def __init__(self, fp: SupportsRead[bytes]) -> None:
        self.fp = fp
        self.bits = 0
        self.bitbuffer = 0

    def next(self) -> int:
        return i8(self.fp.read(1))

    def peek(self, bits: int) -> int:
        while self.bits < bits:
            self.bitbuffer = (self.bitbuffer << 8) + self.next()
            self.bits += 8
        return self.bitbuffer >> (self.bits - bits) & (1 << bits) - 1

    def skip(self, bits: int) -> None:
        while self.bits < bits:
            self.bitbuffer = (self.bitbuffer << 8) + i8(self.fp.read(1))
            self.bits += 8
        self.bits = self.bits - bits

    def read(self, bits: int) -> int:
        v = self.peek(bits)
        self.bits = self.bits - bits
        return v


def _accept(prefix: bytes) -> bool:
    return prefix.startswith(b"\x00\x00\x01\xb3")


##
# Image plugin for MPEG streams.  This plugin can identify a stream,
# but it cannot read it.


class MpegImageFile(ImageFile.ImageFile):
    format = "MPEG"
    format_description = "MPEG"

    def _open(self) -> None:
        assert self.fp is not None

        s = BitStream(self.fp)
        if s.read(32) != 0x1B3:
            msg = "not an MPEG file"
            raise SyntaxError(msg)

        self._mode = "RGB"
        self._size = s.read(12), s.read(12)


# --------------------------------------------------------------------
# Registry stuff

Image.register_open(MpegImageFile.format, MpegImageFile, _accept)

Image.register_extensions(MpegImageFile.format, [".mpg", ".mpeg"])

Image.register_mime(MpegImageFile.format, "video/mpeg")
