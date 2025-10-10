#
# The Python Imaging Library.
# $Id$
#
# IPTC/NAA file handling
#
# history:
# 1995-10-01 fl   Created
# 1998-03-09 fl   Cleaned up and added to PIL
# 2002-06-18 fl   Added getiptcinfo helper
#
# Copyright (c) Secret Labs AB 1997-2002.
# Copyright (c) Fredrik Lundh 1995.
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from typing import cast

from . import Image, ImageFile
from ._binary import i16be as i16
from ._binary import i32be as i32
from ._deprecate import deprecate

COMPRESSION = {1: "raw", 5: "jpeg"}


def __getattr__(name: str) -> bytes:
    if name == "PAD":
        deprecate("IptcImagePlugin.PAD", 12)
        return b"\0\0\0\0"
    msg = f"module '{__name__}' has no attribute '{name}'"
    raise AttributeError(msg)


#
# Helpers


def _i(c: bytes) -> int:
    return i32((b"\0\0\0\0" + c)[-4:])


def _i8(c: int | bytes) -> int:
    return c if isinstance(c, int) else c[0]


def i(c: bytes) -> int:
    """.. deprecated:: 10.2.0"""
    deprecate("IptcImagePlugin.i", 12)
    return _i(c)


def dump(c: Sequence[int | bytes]) -> None:
    """.. deprecated:: 10.2.0"""
    deprecate("IptcImagePlugin.dump", 12)
    for i in c:
        print(f"{_i8(i):02x}", end=" ")
    print()


##
# Image plugin for IPTC/NAA datastreams.  To read IPTC/NAA fields
# from TIFF and JPEG files, use the <b>getiptcinfo</b> function.


class IptcImageFile(ImageFile.ImageFile):
    format = "IPTC"
    format_description = "IPTC/NAA"

    def getint(self, key: tuple[int, int]) -> int:
        return _i(self.info[key])

    def field(self) -> tuple[tuple[int, int] | None, int]:
        #
        # get a IPTC field header
        s = self.fp.read(5)
        if not s.strip(b"\x00"):
            return None, 0

        tag = s[1], s[2]

        # syntax
        if s[0] != 0x1C or tag[0] not in [1, 2, 3, 4, 5, 6, 7, 8, 9, 240]:
            msg = "invalid IPTC/NAA file"
            raise SyntaxError(msg)

        # field size
        size = s[3]
        if size > 132:
            msg = "illegal field length in IPTC/NAA file"
            raise OSError(msg)
        elif size == 128:
            size = 0
        elif size > 128:
            size = _i(self.fp.read(size - 128))
        else:
            size = i16(s, 3)

        return tag, size

    def _open(self) -> None:
        # load descriptive fields
        while True:
            offset = self.fp.tell()
            tag, size = self.field()
            if not tag or tag == (8, 10):
                break
            if size:
                tagdata = self.fp.read(size)
            else:
                tagdata = None
            if tag in self.info:
                if isinstance(self.info[tag], list):
                    self.info[tag].append(tagdata)
                else:
                    self.info[tag] = [self.info[tag], tagdata]
            else:
                self.info[tag] = tagdata

        # mode
        layers = self.info[(3, 60)][0]
        component = self.info[(3, 60)][1]
        if (3, 65) in self.info:
            id = self.info[(3, 65)][0] - 1
        else:
            id = 0
        if layers == 1 and not component:
            self._mode = "L"
        elif layers == 3 and component:
            self._mode = "RGB"[id]
        elif layers == 4 and component:
            self._mode = "CMYK"[id]

        # size
        self._size = self.getint((3, 20)), self.getint((3, 30))

        # compression
        try:
            compression = COMPRESSION[self.getint((3, 120))]
        except KeyError as e:
            msg = "Unknown IPTC image compression"
            raise OSError(msg) from e

        # tile
        if tag == (8, 10):
            self.tile = [
                ImageFile._Tile("iptc", (0, 0) + self.size, offset, compression)
            ]

    def load(self) -> Image.core.PixelAccess | None:
        if len(self.tile) != 1 or self.tile[0][0] != "iptc":
            return ImageFile.ImageFile.load(self)

        offset, compression = self.tile[0][2:]

        self.fp.seek(offset)

        # Copy image data to temporary file
        o = BytesIO()
        if compression == "raw":
            # To simplify access to the extracted file,
            # prepend a PPM header
            o.write(b"P5\n%d %d\n255\n" % self.size)
        while True:
            type, size = self.field()
            if type != (8, 10):
                break
            while size > 0:
                s = self.fp.read(min(size, 8192))
                if not s:
                    break
                o.write(s)
                size -= len(s)

        with Image.open(o) as _im:
            _im.load()
            self.im = _im.im
        self.tile = []
        return Image.Image.load(self)


Image.register_open(IptcImageFile.format, IptcImageFile)

Image.register_extension(IptcImageFile.format, ".iim")


def getiptcinfo(
    im: ImageFile.ImageFile,
) -> dict[tuple[int, int], bytes | list[bytes]] | None:
    """
    Get IPTC information from TIFF, JPEG, or IPTC file.

    :param im: An image containing IPTC data.
    :returns: A dictionary containing IPTC information, or None if
        no IPTC information block was found.
    """
    from . import JpegImagePlugin, TiffImagePlugin

    data = None

    info: dict[tuple[int, int], bytes | list[bytes]] = {}
    if isinstance(im, IptcImageFile):
        # return info dictionary right away
        for k, v in im.info.items():
            if isinstance(k, tuple):
                info[k] = v
        return info

    elif isinstance(im, JpegImagePlugin.JpegImageFile):
        # extract the IPTC/NAA resource
        photoshop = im.info.get("photoshop")
        if photoshop:
            data = photoshop.get(0x0404)

    elif isinstance(im, TiffImagePlugin.TiffImageFile):
        # get raw data from the IPTC/NAA tag (PhotoShop tags the data
        # as 4-byte integers, so we cannot use the get method...)
        try:
            data = im.tag_v2._tagdata[TiffImagePlugin.IPTC_NAA_CHUNK]
        except KeyError:
            pass

    if data is None:
        return None  # no properties

    # create an IptcImagePlugin object without initializing it
    class FakeImage:
        pass

    fake_im = FakeImage()
    fake_im.__class__ = IptcImageFile  # type: ignore[assignment]
    iptc_im = cast(IptcImageFile, fake_im)

    # parse the IPTC information chunk
    iptc_im.info = {}
    iptc_im.fp = BytesIO(data)

    try:
        iptc_im._open()
    except (IndexError, KeyError):
        pass  # expected failure

    for k, v in iptc_im.info.items():
        if isinstance(k, tuple):
            info[k] = v
    return info
