"""
Blizzard Mipmap Format (.blp)
Jerome Leclanche <jerome@leclan.ch>

The contents of this file are hereby released in the public domain (CC0)
Full text of the CC0 license:
  https://creativecommons.org/publicdomain/zero/1.0/

BLP1 files, used mostly in Warcraft III, are not fully supported.
All types of BLP2 files used in World of Warcraft are supported.

The BLP file structure consists of a header, up to 16 mipmaps of the
texture

Texture sizes must be powers of two, though the two dimensions do
not have to be equal; 512x256 is valid, but 512x200 is not.
The first mipmap (mipmap #0) is the full size image; each subsequent
mipmap halves both dimensions. The final mipmap should be 1x1.

BLP files come in many different flavours:
* JPEG-compressed (type == 0) - only supported for BLP1.
* RAW images (type == 1, encoding == 1). Each mipmap is stored as an
  array of 8-bit values, one per pixel, left to right, top to bottom.
  Each value is an index to the palette.
* DXT-compressed (type == 1, encoding == 2):
- DXT1 compression is used if alpha_encoding == 0.
  - An additional alpha bit is used if alpha_depth == 1.
  - DXT3 compression is used if alpha_encoding == 1.
  - DXT5 compression is used if alpha_encoding == 7.
"""

from __future__ import annotations

import abc
import os
import struct
from enum import IntEnum
from io import BytesIO
from typing import IO

from . import Image, ImageFile


class Format(IntEnum):
    JPEG = 0


class Encoding(IntEnum):
    UNCOMPRESSED = 1
    DXT = 2
    UNCOMPRESSED_RAW_BGRA = 3


class AlphaEncoding(IntEnum):
    DXT1 = 0
    DXT3 = 1
    DXT5 = 7


def unpack_565(i: int) -> tuple[int, int, int]:
    return ((i >> 11) & 0x1F) << 3, ((i >> 5) & 0x3F) << 2, (i & 0x1F) << 3


def decode_dxt1(
    data: bytes, alpha: bool = False
) -> tuple[bytearray, bytearray, bytearray, bytearray]:
    """
    input: one "row" of data (i.e. will produce 4*width pixels)
    """

    blocks = len(data) // 8  # number of blocks in row
    ret = (bytearray(), bytearray(), bytearray(), bytearray())

    for block_index in range(blocks):
        # Decode next 8-byte block.
        idx = block_index * 8
        color0, color1, bits = struct.unpack_from("<HHI", data, idx)

        r0, g0, b0 = unpack_565(color0)
        r1, g1, b1 = unpack_565(color1)

        # Decode this block into 4x4 pixels
        # Accumulate the results onto our 4 row accumulators
        for j in range(4):
            for i in range(4):
                # get next control op and generate a pixel

                control = bits & 3
                bits = bits >> 2

                a = 0xFF
                if control == 0:
                    r, g, b = r0, g0, b0
                elif control == 1:
                    r, g, b = r1, g1, b1
                elif control == 2:
                    if color0 > color1:
                        r = (2 * r0 + r1) // 3
                        g = (2 * g0 + g1) // 3
                        b = (2 * b0 + b1) // 3
                    else:
                        r = (r0 + r1) // 2
                        g = (g0 + g1) // 2
                        b = (b0 + b1) // 2
                elif control == 3:
                    if color0 > color1:
                        r = (2 * r1 + r0) // 3
                        g = (2 * g1 + g0) // 3
                        b = (2 * b1 + b0) // 3
                    else:
                        r, g, b, a = 0, 0, 0, 0

                if alpha:
                    ret[j].extend([r, g, b, a])
                else:
                    ret[j].extend([r, g, b])

    return ret


def decode_dxt3(data: bytes) -> tuple[bytearray, bytearray, bytearray, bytearray]:
    """
    input: one "row" of data (i.e. will produce 4*width pixels)
    """

    blocks = len(data) // 16  # number of blocks in row
    ret = (bytearray(), bytearray(), bytearray(), bytearray())

    for block_index in range(blocks):
        idx = block_index * 16
        block = data[idx : idx + 16]
        # Decode next 16-byte block.
        bits = struct.unpack_from("<8B", block)
        color0, color1 = struct.unpack_from("<HH", block, 8)

        (code,) = struct.unpack_from("<I", block, 12)

        r0, g0, b0 = unpack_565(color0)
        r1, g1, b1 = unpack_565(color1)

        for j in range(4):
            high = False  # Do we want the higher bits?
            for i in range(4):
                alphacode_index = (4 * j + i) // 2
                a = bits[alphacode_index]
                if high:
                    high = False
                    a >>= 4
                else:
                    high = True
                    a &= 0xF
                a *= 17  # We get a value between 0 and 15

                color_code = (code >> 2 * (4 * j + i)) & 0x03

                if color_code == 0:
                    r, g, b = r0, g0, b0
                elif color_code == 1:
                    r, g, b = r1, g1, b1
                elif color_code == 2:
                    r = (2 * r0 + r1) // 3
                    g = (2 * g0 + g1) // 3
                    b = (2 * b0 + b1) // 3
                elif color_code == 3:
                    r = (2 * r1 + r0) // 3
                    g = (2 * g1 + g0) // 3
                    b = (2 * b1 + b0) // 3

                ret[j].extend([r, g, b, a])

    return ret


def decode_dxt5(data: bytes) -> tuple[bytearray, bytearray, bytearray, bytearray]:
    """
    input: one "row" of data (i.e. will produce 4 * width pixels)
    """

    blocks = len(data) // 16  # number of blocks in row
    ret = (bytearray(), bytearray(), bytearray(), bytearray())

    for block_index in range(blocks):
        idx = block_index * 16
        block = data[idx : idx + 16]
        # Decode next 16-byte block.
        a0, a1 = struct.unpack_from("<BB", block)

        bits = struct.unpack_from("<6B", block, 2)
        alphacode1 = bits[2] | (bits[3] << 8) | (bits[4] << 16) | (bits[5] << 24)
        alphacode2 = bits[0] | (bits[1] << 8)

        color0, color1 = struct.unpack_from("<HH", block, 8)

        (code,) = struct.unpack_from("<I", block, 12)

        r0, g0, b0 = unpack_565(color0)
        r1, g1, b1 = unpack_565(color1)

        for j in range(4):
            for i in range(4):
                # get next control op and generate a pixel
                alphacode_index = 3 * (4 * j + i)

                if alphacode_index <= 12:
                    alphacode = (alphacode2 >> alphacode_index) & 0x07
                elif alphacode_index == 15:
                    alphacode = (alphacode2 >> 15) | ((alphacode1 << 1) & 0x06)
                else:  # alphacode_index >= 18 and alphacode_index <= 45
                    alphacode = (alphacode1 >> (alphacode_index - 16)) & 0x07

                if alphacode == 0:
                    a = a0
                elif alphacode == 1:
                    a = a1
                elif a0 > a1:
                    a = ((8 - alphacode) * a0 + (alphacode - 1) * a1) // 7
                elif alphacode == 6:
                    a = 0
                elif alphacode == 7:
                    a = 255
                else:
                    a = ((6 - alphacode) * a0 + (alphacode - 1) * a1) // 5

                color_code = (code >> 2 * (4 * j + i)) & 0x03

                if color_code == 0:
                    r, g, b = r0, g0, b0
                elif color_code == 1:
                    r, g, b = r1, g1, b1
                elif color_code == 2:
                    r = (2 * r0 + r1) // 3
                    g = (2 * g0 + g1) // 3
                    b = (2 * b0 + b1) // 3
                elif color_code == 3:
                    r = (2 * r1 + r0) // 3
                    g = (2 * g1 + g0) // 3
                    b = (2 * b1 + b0) // 3

                ret[j].extend([r, g, b, a])

    return ret


class BLPFormatError(NotImplementedError):
    pass


def _accept(prefix: bytes) -> bool:
    return prefix.startswith((b"BLP1", b"BLP2"))


class BlpImageFile(ImageFile.ImageFile):
    """
    Blizzard Mipmap Format
    """

    format = "BLP"
    format_description = "Blizzard Mipmap Format"

    def _open(self) -> None:
        self.magic = self.fp.read(4)
        if not _accept(self.magic):
            msg = f"Bad BLP magic {repr(self.magic)}"
            raise BLPFormatError(msg)

        compression = struct.unpack("<i", self.fp.read(4))[0]
        if self.magic == b"BLP1":
            alpha = struct.unpack("<I", self.fp.read(4))[0] != 0
        else:
            encoding = struct.unpack("<b", self.fp.read(1))[0]
            alpha = struct.unpack("<b", self.fp.read(1))[0] != 0
            alpha_encoding = struct.unpack("<b", self.fp.read(1))[0]
            self.fp.seek(1, os.SEEK_CUR)  # mips

        self._size = struct.unpack("<II", self.fp.read(8))

        args: tuple[int, int, bool] | tuple[int, int, bool, int]
        if self.magic == b"BLP1":
            encoding = struct.unpack("<i", self.fp.read(4))[0]
            self.fp.seek(4, os.SEEK_CUR)  # subtype

            args = (compression, encoding, alpha)
            offset = 28
        else:
            args = (compression, encoding, alpha, alpha_encoding)
            offset = 20

        decoder = self.magic.decode()

        self._mode = "RGBA" if alpha else "RGB"
        self.tile = [ImageFile._Tile(decoder, (0, 0) + self.size, offset, args)]


class _BLPBaseDecoder(abc.ABC, ImageFile.PyDecoder):
    _pulls_fd = True

    def decode(self, buffer: bytes | Image.SupportsArrayInterface) -> tuple[int, int]:
        try:
            self._read_header()
            self._load()
        except struct.error as e:
            msg = "Truncated BLP file"
            raise OSError(msg) from e
        return -1, 0

    @abc.abstractmethod
    def _load(self) -> None:
        pass

    def _read_header(self) -> None:
        self._offsets = struct.unpack("<16I", self._safe_read(16 * 4))
        self._lengths = struct.unpack("<16I", self._safe_read(16 * 4))

    def _safe_read(self, length: int) -> bytes:
        assert self.fd is not None
        return ImageFile._safe_read(self.fd, length)

    def _read_palette(self) -> list[tuple[int, int, int, int]]:
        ret = []
        for i in range(256):
            try:
                b, g, r, a = struct.unpack("<4B", self._safe_read(4))
            except struct.error:
                break
            ret.append((b, g, r, a))
        return ret

    def _read_bgra(
        self, palette: list[tuple[int, int, int, int]], alpha: bool
    ) -> bytearray:
        data = bytearray()
        _data = BytesIO(self._safe_read(self._lengths[0]))
        while True:
            try:
                (offset,) = struct.unpack("<B", _data.read(1))
            except struct.error:
                break
            b, g, r, a = palette[offset]
            d: tuple[int, ...] = (r, g, b)
            if alpha:
                d += (a,)
            data.extend(d)
        return data


class BLP1Decoder(_BLPBaseDecoder):
    def _load(self) -> None:
        self._compression, self._encoding, alpha = self.args

        if self._compression == Format.JPEG:
            self._decode_jpeg_stream()

        elif self._compression == 1:
            if self._encoding in (4, 5):
                palette = self._read_palette()
                data = self._read_bgra(palette, alpha)
                self.set_as_raw(data)
            else:
                msg = f"Unsupported BLP encoding {repr(self._encoding)}"
                raise BLPFormatError(msg)
        else:
            msg = f"Unsupported BLP compression {repr(self._encoding)}"
            raise BLPFormatError(msg)

    def _decode_jpeg_stream(self) -> None:
        from .JpegImagePlugin import JpegImageFile

        (jpeg_header_size,) = struct.unpack("<I", self._safe_read(4))
        jpeg_header = self._safe_read(jpeg_header_size)
        assert self.fd is not None
        self._safe_read(self._offsets[0] - self.fd.tell())  # What IS this?
        data = self._safe_read(self._lengths[0])
        data = jpeg_header + data
        image = JpegImageFile(BytesIO(data))
        Image._decompression_bomb_check(image.size)
        if image.mode == "CMYK":
            args = image.tile[0].args
            assert isinstance(args, tuple)
            image.tile = [image.tile[0]._replace(args=(args[0], "CMYK"))]
        self.set_as_raw(image.convert("RGB").tobytes(), "BGR")


class BLP2Decoder(_BLPBaseDecoder):
    def _load(self) -> None:
        self._compression, self._encoding, alpha, self._alpha_encoding = self.args

        palette = self._read_palette()

        assert self.fd is not None
        self.fd.seek(self._offsets[0])

        if self._compression == 1:
            # Uncompressed or DirectX compression

            if self._encoding == Encoding.UNCOMPRESSED:
                data = self._read_bgra(palette, alpha)

            elif self._encoding == Encoding.DXT:
                data = bytearray()
                if self._alpha_encoding == AlphaEncoding.DXT1:
                    linesize = (self.state.xsize + 3) // 4 * 8
                    for yb in range((self.state.ysize + 3) // 4):
                        for d in decode_dxt1(self._safe_read(linesize), alpha):
                            data += d

                elif self._alpha_encoding == AlphaEncoding.DXT3:
                    linesize = (self.state.xsize + 3) // 4 * 16
                    for yb in range((self.state.ysize + 3) // 4):
                        for d in decode_dxt3(self._safe_read(linesize)):
                            data += d

                elif self._alpha_encoding == AlphaEncoding.DXT5:
                    linesize = (self.state.xsize + 3) // 4 * 16
                    for yb in range((self.state.ysize + 3) // 4):
                        for d in decode_dxt5(self._safe_read(linesize)):
                            data += d
                else:
                    msg = f"Unsupported alpha encoding {repr(self._alpha_encoding)}"
                    raise BLPFormatError(msg)
            else:
                msg = f"Unknown BLP encoding {repr(self._encoding)}"
                raise BLPFormatError(msg)

        else:
            msg = f"Unknown BLP compression {repr(self._compression)}"
            raise BLPFormatError(msg)

        self.set_as_raw(data)


class BLPEncoder(ImageFile.PyEncoder):
    _pushes_fd = True

    def _write_palette(self) -> bytes:
        data = b""
        assert self.im is not None
        palette = self.im.getpalette("RGBA", "RGBA")
        for i in range(len(palette) // 4):
            r, g, b, a = palette[i * 4 : (i + 1) * 4]
            data += struct.pack("<4B", b, g, r, a)
        while len(data) < 256 * 4:
            data += b"\x00" * 4
        return data

    def encode(self, bufsize: int) -> tuple[int, int, bytes]:
        palette_data = self._write_palette()

        offset = 20 + 16 * 4 * 2 + len(palette_data)
        data = struct.pack("<16I", offset, *((0,) * 15))

        assert self.im is not None
        w, h = self.im.size
        data += struct.pack("<16I", w * h, *((0,) * 15))

        data += palette_data

        for y in range(h):
            for x in range(w):
                data += struct.pack("<B", self.im.getpixel((x, y)))

        return len(data), 0, data


def _save(im: Image.Image, fp: IO[bytes], filename: str | bytes) -> None:
    if im.mode != "P":
        msg = "Unsupported BLP image mode"
        raise ValueError(msg)

    magic = b"BLP1" if im.encoderinfo.get("blp_version") == "BLP1" else b"BLP2"
    fp.write(magic)

    assert im.palette is not None
    fp.write(struct.pack("<i", 1))  # Uncompressed or DirectX compression

    alpha_depth = 1 if im.palette.mode == "RGBA" else 0
    if magic == b"BLP1":
        fp.write(struct.pack("<L", alpha_depth))
    else:
        fp.write(struct.pack("<b", Encoding.UNCOMPRESSED))
        fp.write(struct.pack("<b", alpha_depth))
        fp.write(struct.pack("<b", 0))  # alpha encoding
        fp.write(struct.pack("<b", 0))  # mips
    fp.write(struct.pack("<II", *im.size))
    if magic == b"BLP1":
        fp.write(struct.pack("<i", 5))
        fp.write(struct.pack("<i", 0))

    ImageFile._save(im, fp, [ImageFile._Tile("BLP", (0, 0) + im.size, 0, im.mode)])


Image.register_open(BlpImageFile.format, BlpImageFile, _accept)
Image.register_extension(BlpImageFile.format, ".blp")
Image.register_decoder("BLP1", BLP1Decoder)
Image.register_decoder("BLP2", BLP2Decoder)

Image.register_save(BlpImageFile.format, _save)
Image.register_encoder("BLP", BLPEncoder)
