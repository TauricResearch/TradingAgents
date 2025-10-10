#
# The Python Imaging Library.
# $Id$
#
# XPM File handling
#
# History:
# 1996-12-29 fl   Created
# 2001-02-17 fl   Use 're' instead of 'regex' (Python 2.1) (0.7)
#
# Copyright (c) Secret Labs AB 1997-2001.
# Copyright (c) Fredrik Lundh 1996-2001.
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import re

from . import Image, ImageFile, ImagePalette
from ._binary import o8

# XPM header
xpm_head = re.compile(b'"([0-9]*) ([0-9]*) ([0-9]*) ([0-9]*)')


def _accept(prefix: bytes) -> bool:
    return prefix.startswith(b"/* XPM */")


##
# Image plugin for X11 pixel maps.


class XpmImageFile(ImageFile.ImageFile):
    format = "XPM"
    format_description = "X11 Pixel Map"

    def _open(self) -> None:
        assert self.fp is not None
        if not _accept(self.fp.read(9)):
            msg = "not an XPM file"
            raise SyntaxError(msg)

        # skip forward to next string
        while True:
            line = self.fp.readline()
            if not line:
                msg = "broken XPM file"
                raise SyntaxError(msg)
            m = xpm_head.match(line)
            if m:
                break

        self._size = int(m.group(1)), int(m.group(2))

        palette_length = int(m.group(3))
        bpp = int(m.group(4))

        #
        # load palette description

        palette = {}

        for _ in range(palette_length):
            line = self.fp.readline().rstrip()

            c = line[1 : bpp + 1]
            s = line[bpp + 1 : -2].split()

            for i in range(0, len(s), 2):
                if s[i] == b"c":
                    # process colour key
                    rgb = s[i + 1]
                    if rgb == b"None":
                        self.info["transparency"] = c
                    elif rgb.startswith(b"#"):
                        rgb_int = int(rgb[1:], 16)
                        palette[c] = (
                            o8((rgb_int >> 16) & 255)
                            + o8((rgb_int >> 8) & 255)
                            + o8(rgb_int & 255)
                        )
                    else:
                        # unknown colour
                        msg = "cannot read this XPM file"
                        raise ValueError(msg)
                    break

            else:
                # missing colour key
                msg = "cannot read this XPM file"
                raise ValueError(msg)

        args: tuple[int, dict[bytes, bytes] | tuple[bytes, ...]]
        if palette_length > 256:
            self._mode = "RGB"
            args = (bpp, palette)
        else:
            self._mode = "P"
            self.palette = ImagePalette.raw("RGB", b"".join(palette.values()))
            args = (bpp, tuple(palette.keys()))

        self.tile = [ImageFile._Tile("xpm", (0, 0) + self.size, self.fp.tell(), args)]

    def load_read(self, read_bytes: int) -> bytes:
        #
        # load all image data in one chunk

        xsize, ysize = self.size

        assert self.fp is not None
        s = [self.fp.readline()[1 : xsize + 1].ljust(xsize) for i in range(ysize)]

        return b"".join(s)


class XpmDecoder(ImageFile.PyDecoder):
    _pulls_fd = True

    def decode(self, buffer: bytes | Image.SupportsArrayInterface) -> tuple[int, int]:
        assert self.fd is not None

        data = bytearray()
        bpp, palette = self.args
        dest_length = self.state.xsize * self.state.ysize
        if self.mode == "RGB":
            dest_length *= 3
        pixel_header = False
        while len(data) < dest_length:
            line = self.fd.readline()
            if not line:
                break
            if line.rstrip() == b"/* pixels */" and not pixel_header:
                pixel_header = True
                continue
            line = b'"'.join(line.split(b'"')[1:-1])
            for i in range(0, len(line), bpp):
                key = line[i : i + bpp]
                if self.mode == "RGB":
                    data += palette[key]
                else:
                    data += o8(palette.index(key))
        self.set_as_raw(bytes(data))
        return -1, 0


#
# Registry


Image.register_open(XpmImageFile.format, XpmImageFile, _accept)
Image.register_decoder("xpm", XpmDecoder)

Image.register_extension(XpmImageFile.format, ".xpm")

Image.register_mime(XpmImageFile.format, "image/xpm")
