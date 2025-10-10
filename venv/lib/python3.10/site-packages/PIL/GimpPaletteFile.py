#
# Python Imaging Library
# $Id$
#
# stuff to read GIMP palette files
#
# History:
# 1997-08-23 fl     Created
# 2004-09-07 fl     Support GIMP 2.0 palette files.
#
# Copyright (c) Secret Labs AB 1997-2004.  All rights reserved.
# Copyright (c) Fredrik Lundh 1997-2004.
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import re
from io import BytesIO
from typing import IO


class GimpPaletteFile:
    """File handler for GIMP's palette format."""

    rawmode = "RGB"

    def _read(self, fp: IO[bytes], limit: bool = True) -> None:
        if not fp.readline().startswith(b"GIMP Palette"):
            msg = "not a GIMP palette file"
            raise SyntaxError(msg)

        palette: list[int] = []
        i = 0
        while True:
            if limit and i == 256 + 3:
                break

            i += 1
            s = fp.readline()
            if not s:
                break

            # skip fields and comment lines
            if re.match(rb"\w+:|#", s):
                continue
            if limit and len(s) > 100:
                msg = "bad palette file"
                raise SyntaxError(msg)

            v = s.split(maxsplit=3)
            if len(v) < 3:
                msg = "bad palette entry"
                raise ValueError(msg)

            palette += (int(v[i]) for i in range(3))
            if limit and len(palette) == 768:
                break

        self.palette = bytes(palette)

    def __init__(self, fp: IO[bytes]) -> None:
        self._read(fp)

    @classmethod
    def frombytes(cls, data: bytes) -> GimpPaletteFile:
        self = cls.__new__(cls)
        self._read(BytesIO(data), False)
        return self

    def getpalette(self) -> tuple[bytes, str]:
        return self.palette, self.rawmode
