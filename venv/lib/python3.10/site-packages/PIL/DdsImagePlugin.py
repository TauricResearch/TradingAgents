"""
A Pillow plugin for .dds files (S3TC-compressed aka DXTC)
Jerome Leclanche <jerome@leclan.ch>

Documentation:
https://web.archive.org/web/20170802060935/http://oss.sgi.com/projects/ogl-sample/registry/EXT/texture_compression_s3tc.txt

The contents of this file are hereby released in the public domain (CC0)
Full text of the CC0 license:
https://creativecommons.org/publicdomain/zero/1.0/
"""

from __future__ import annotations

import io
import struct
import sys
from enum import IntEnum, IntFlag
from typing import IO

from . import Image, ImageFile, ImagePalette
from ._binary import i32le as i32
from ._binary import o8
from ._binary import o32le as o32

# Magic ("DDS ")
DDS_MAGIC = 0x20534444


# DDS flags
class DDSD(IntFlag):
    CAPS = 0x1
    HEIGHT = 0x2
    WIDTH = 0x4
    PITCH = 0x8
    PIXELFORMAT = 0x1000
    MIPMAPCOUNT = 0x20000
    LINEARSIZE = 0x80000
    DEPTH = 0x800000


# DDS caps
class DDSCAPS(IntFlag):
    COMPLEX = 0x8
    TEXTURE = 0x1000
    MIPMAP = 0x400000


class DDSCAPS2(IntFlag):
    CUBEMAP = 0x200
    CUBEMAP_POSITIVEX = 0x400
    CUBEMAP_NEGATIVEX = 0x800
    CUBEMAP_POSITIVEY = 0x1000
    CUBEMAP_NEGATIVEY = 0x2000
    CUBEMAP_POSITIVEZ = 0x4000
    CUBEMAP_NEGATIVEZ = 0x8000
    VOLUME = 0x200000


# Pixel Format
class DDPF(IntFlag):
    ALPHAPIXELS = 0x1
    ALPHA = 0x2
    FOURCC = 0x4
    PALETTEINDEXED8 = 0x20
    RGB = 0x40
    LUMINANCE = 0x20000


# dxgiformat.h
class DXGI_FORMAT(IntEnum):
    UNKNOWN = 0
    R32G32B32A32_TYPELESS = 1
    R32G32B32A32_FLOAT = 2
    R32G32B32A32_UINT = 3
    R32G32B32A32_SINT = 4
    R32G32B32_TYPELESS = 5
    R32G32B32_FLOAT = 6
    R32G32B32_UINT = 7
    R32G32B32_SINT = 8
    R16G16B16A16_TYPELESS = 9
    R16G16B16A16_FLOAT = 10
    R16G16B16A16_UNORM = 11
    R16G16B16A16_UINT = 12
    R16G16B16A16_SNORM = 13
    R16G16B16A16_SINT = 14
    R32G32_TYPELESS = 15
    R32G32_FLOAT = 16
    R32G32_UINT = 17
    R32G32_SINT = 18
    R32G8X24_TYPELESS = 19
    D32_FLOAT_S8X24_UINT = 20
    R32_FLOAT_X8X24_TYPELESS = 21
    X32_TYPELESS_G8X24_UINT = 22
    R10G10B10A2_TYPELESS = 23
    R10G10B10A2_UNORM = 24
    R10G10B10A2_UINT = 25
    R11G11B10_FLOAT = 26
    R8G8B8A8_TYPELESS = 27
    R8G8B8A8_UNORM = 28
    R8G8B8A8_UNORM_SRGB = 29
    R8G8B8A8_UINT = 30
    R8G8B8A8_SNORM = 31
    R8G8B8A8_SINT = 32
    R16G16_TYPELESS = 33
    R16G16_FLOAT = 34
    R16G16_UNORM = 35
    R16G16_UINT = 36
    R16G16_SNORM = 37
    R16G16_SINT = 38
    R32_TYPELESS = 39
    D32_FLOAT = 40
    R32_FLOAT = 41
    R32_UINT = 42
    R32_SINT = 43
    R24G8_TYPELESS = 44
    D24_UNORM_S8_UINT = 45
    R24_UNORM_X8_TYPELESS = 46
    X24_TYPELESS_G8_UINT = 47
    R8G8_TYPELESS = 48
    R8G8_UNORM = 49
    R8G8_UINT = 50
    R8G8_SNORM = 51
    R8G8_SINT = 52
    R16_TYPELESS = 53
    R16_FLOAT = 54
    D16_UNORM = 55
    R16_UNORM = 56
    R16_UINT = 57
    R16_SNORM = 58
    R16_SINT = 59
    R8_TYPELESS = 60
    R8_UNORM = 61
    R8_UINT = 62
    R8_SNORM = 63
    R8_SINT = 64
    A8_UNORM = 65
    R1_UNORM = 66
    R9G9B9E5_SHAREDEXP = 67
    R8G8_B8G8_UNORM = 68
    G8R8_G8B8_UNORM = 69
    BC1_TYPELESS = 70
    BC1_UNORM = 71
    BC1_UNORM_SRGB = 72
    BC2_TYPELESS = 73
    BC2_UNORM = 74
    BC2_UNORM_SRGB = 75
    BC3_TYPELESS = 76
    BC3_UNORM = 77
    BC3_UNORM_SRGB = 78
    BC4_TYPELESS = 79
    BC4_UNORM = 80
    BC4_SNORM = 81
    BC5_TYPELESS = 82
    BC5_UNORM = 83
    BC5_SNORM = 84
    B5G6R5_UNORM = 85
    B5G5R5A1_UNORM = 86
    B8G8R8A8_UNORM = 87
    B8G8R8X8_UNORM = 88
    R10G10B10_XR_BIAS_A2_UNORM = 89
    B8G8R8A8_TYPELESS = 90
    B8G8R8A8_UNORM_SRGB = 91
    B8G8R8X8_TYPELESS = 92
    B8G8R8X8_UNORM_SRGB = 93
    BC6H_TYPELESS = 94
    BC6H_UF16 = 95
    BC6H_SF16 = 96
    BC7_TYPELESS = 97
    BC7_UNORM = 98
    BC7_UNORM_SRGB = 99
    AYUV = 100
    Y410 = 101
    Y416 = 102
    NV12 = 103
    P010 = 104
    P016 = 105
    OPAQUE_420 = 106
    YUY2 = 107
    Y210 = 108
    Y216 = 109
    NV11 = 110
    AI44 = 111
    IA44 = 112
    P8 = 113
    A8P8 = 114
    B4G4R4A4_UNORM = 115
    P208 = 130
    V208 = 131
    V408 = 132
    SAMPLER_FEEDBACK_MIN_MIP_OPAQUE = 189
    SAMPLER_FEEDBACK_MIP_REGION_USED_OPAQUE = 190


class D3DFMT(IntEnum):
    UNKNOWN = 0
    R8G8B8 = 20
    A8R8G8B8 = 21
    X8R8G8B8 = 22
    R5G6B5 = 23
    X1R5G5B5 = 24
    A1R5G5B5 = 25
    A4R4G4B4 = 26
    R3G3B2 = 27
    A8 = 28
    A8R3G3B2 = 29
    X4R4G4B4 = 30
    A2B10G10R10 = 31
    A8B8G8R8 = 32
    X8B8G8R8 = 33
    G16R16 = 34
    A2R10G10B10 = 35
    A16B16G16R16 = 36
    A8P8 = 40
    P8 = 41
    L8 = 50
    A8L8 = 51
    A4L4 = 52
    V8U8 = 60
    L6V5U5 = 61
    X8L8V8U8 = 62
    Q8W8V8U8 = 63
    V16U16 = 64
    A2W10V10U10 = 67
    D16_LOCKABLE = 70
    D32 = 71
    D15S1 = 73
    D24S8 = 75
    D24X8 = 77
    D24X4S4 = 79
    D16 = 80
    D32F_LOCKABLE = 82
    D24FS8 = 83
    D32_LOCKABLE = 84
    S8_LOCKABLE = 85
    L16 = 81
    VERTEXDATA = 100
    INDEX16 = 101
    INDEX32 = 102
    Q16W16V16U16 = 110
    R16F = 111
    G16R16F = 112
    A16B16G16R16F = 113
    R32F = 114
    G32R32F = 115
    A32B32G32R32F = 116
    CxV8U8 = 117
    A1 = 118
    A2B10G10R10_XR_BIAS = 119
    BINARYBUFFER = 199

    UYVY = i32(b"UYVY")
    R8G8_B8G8 = i32(b"RGBG")
    YUY2 = i32(b"YUY2")
    G8R8_G8B8 = i32(b"GRGB")
    DXT1 = i32(b"DXT1")
    DXT2 = i32(b"DXT2")
    DXT3 = i32(b"DXT3")
    DXT4 = i32(b"DXT4")
    DXT5 = i32(b"DXT5")
    DX10 = i32(b"DX10")
    BC4S = i32(b"BC4S")
    BC4U = i32(b"BC4U")
    BC5S = i32(b"BC5S")
    BC5U = i32(b"BC5U")
    ATI1 = i32(b"ATI1")
    ATI2 = i32(b"ATI2")
    MULTI2_ARGB8 = i32(b"MET1")


# Backward compatibility layer
module = sys.modules[__name__]
for item in DDSD:
    assert item.name is not None
    setattr(module, f"DDSD_{item.name}", item.value)
for item1 in DDSCAPS:
    assert item1.name is not None
    setattr(module, f"DDSCAPS_{item1.name}", item1.value)
for item2 in DDSCAPS2:
    assert item2.name is not None
    setattr(module, f"DDSCAPS2_{item2.name}", item2.value)
for item3 in DDPF:
    assert item3.name is not None
    setattr(module, f"DDPF_{item3.name}", item3.value)

DDS_FOURCC = DDPF.FOURCC
DDS_RGB = DDPF.RGB
DDS_RGBA = DDPF.RGB | DDPF.ALPHAPIXELS
DDS_LUMINANCE = DDPF.LUMINANCE
DDS_LUMINANCEA = DDPF.LUMINANCE | DDPF.ALPHAPIXELS
DDS_ALPHA = DDPF.ALPHA
DDS_PAL8 = DDPF.PALETTEINDEXED8

DDS_HEADER_FLAGS_TEXTURE = DDSD.CAPS | DDSD.HEIGHT | DDSD.WIDTH | DDSD.PIXELFORMAT
DDS_HEADER_FLAGS_MIPMAP = DDSD.MIPMAPCOUNT
DDS_HEADER_FLAGS_VOLUME = DDSD.DEPTH
DDS_HEADER_FLAGS_PITCH = DDSD.PITCH
DDS_HEADER_FLAGS_LINEARSIZE = DDSD.LINEARSIZE

DDS_HEIGHT = DDSD.HEIGHT
DDS_WIDTH = DDSD.WIDTH

DDS_SURFACE_FLAGS_TEXTURE = DDSCAPS.TEXTURE
DDS_SURFACE_FLAGS_MIPMAP = DDSCAPS.COMPLEX | DDSCAPS.MIPMAP
DDS_SURFACE_FLAGS_CUBEMAP = DDSCAPS.COMPLEX

DDS_CUBEMAP_POSITIVEX = DDSCAPS2.CUBEMAP | DDSCAPS2.CUBEMAP_POSITIVEX
DDS_CUBEMAP_NEGATIVEX = DDSCAPS2.CUBEMAP | DDSCAPS2.CUBEMAP_NEGATIVEX
DDS_CUBEMAP_POSITIVEY = DDSCAPS2.CUBEMAP | DDSCAPS2.CUBEMAP_POSITIVEY
DDS_CUBEMAP_NEGATIVEY = DDSCAPS2.CUBEMAP | DDSCAPS2.CUBEMAP_NEGATIVEY
DDS_CUBEMAP_POSITIVEZ = DDSCAPS2.CUBEMAP | DDSCAPS2.CUBEMAP_POSITIVEZ
DDS_CUBEMAP_NEGATIVEZ = DDSCAPS2.CUBEMAP | DDSCAPS2.CUBEMAP_NEGATIVEZ

DXT1_FOURCC = D3DFMT.DXT1
DXT3_FOURCC = D3DFMT.DXT3
DXT5_FOURCC = D3DFMT.DXT5

DXGI_FORMAT_R8G8B8A8_TYPELESS = DXGI_FORMAT.R8G8B8A8_TYPELESS
DXGI_FORMAT_R8G8B8A8_UNORM = DXGI_FORMAT.R8G8B8A8_UNORM
DXGI_FORMAT_R8G8B8A8_UNORM_SRGB = DXGI_FORMAT.R8G8B8A8_UNORM_SRGB
DXGI_FORMAT_BC5_TYPELESS = DXGI_FORMAT.BC5_TYPELESS
DXGI_FORMAT_BC5_UNORM = DXGI_FORMAT.BC5_UNORM
DXGI_FORMAT_BC5_SNORM = DXGI_FORMAT.BC5_SNORM
DXGI_FORMAT_BC6H_UF16 = DXGI_FORMAT.BC6H_UF16
DXGI_FORMAT_BC6H_SF16 = DXGI_FORMAT.BC6H_SF16
DXGI_FORMAT_BC7_TYPELESS = DXGI_FORMAT.BC7_TYPELESS
DXGI_FORMAT_BC7_UNORM = DXGI_FORMAT.BC7_UNORM
DXGI_FORMAT_BC7_UNORM_SRGB = DXGI_FORMAT.BC7_UNORM_SRGB


class DdsImageFile(ImageFile.ImageFile):
    format = "DDS"
    format_description = "DirectDraw Surface"

    def _open(self) -> None:
        if not _accept(self.fp.read(4)):
            msg = "not a DDS file"
            raise SyntaxError(msg)
        (header_size,) = struct.unpack("<I", self.fp.read(4))
        if header_size != 124:
            msg = f"Unsupported header size {repr(header_size)}"
            raise OSError(msg)
        header_bytes = self.fp.read(header_size - 4)
        if len(header_bytes) != 120:
            msg = f"Incomplete header: {len(header_bytes)} bytes"
            raise OSError(msg)
        header = io.BytesIO(header_bytes)

        flags, height, width = struct.unpack("<3I", header.read(12))
        self._size = (width, height)
        extents = (0, 0) + self.size

        pitch, depth, mipmaps = struct.unpack("<3I", header.read(12))
        struct.unpack("<11I", header.read(44))  # reserved

        # pixel format
        pfsize, pfflags, fourcc, bitcount = struct.unpack("<4I", header.read(16))
        n = 0
        rawmode = None
        if pfflags & DDPF.RGB:
            # Texture contains uncompressed RGB data
            if pfflags & DDPF.ALPHAPIXELS:
                self._mode = "RGBA"
                mask_count = 4
            else:
                self._mode = "RGB"
                mask_count = 3

            masks = struct.unpack(f"<{mask_count}I", header.read(mask_count * 4))
            self.tile = [ImageFile._Tile("dds_rgb", extents, 0, (bitcount, masks))]
            return
        elif pfflags & DDPF.LUMINANCE:
            if bitcount == 8:
                self._mode = "L"
            elif bitcount == 16 and pfflags & DDPF.ALPHAPIXELS:
                self._mode = "LA"
            else:
                msg = f"Unsupported bitcount {bitcount} for {pfflags}"
                raise OSError(msg)
        elif pfflags & DDPF.PALETTEINDEXED8:
            self._mode = "P"
            self.palette = ImagePalette.raw("RGBA", self.fp.read(1024))
            self.palette.mode = "RGBA"
        elif pfflags & DDPF.FOURCC:
            offset = header_size + 4
            if fourcc == D3DFMT.DXT1:
                self._mode = "RGBA"
                self.pixel_format = "DXT1"
                n = 1
            elif fourcc == D3DFMT.DXT3:
                self._mode = "RGBA"
                self.pixel_format = "DXT3"
                n = 2
            elif fourcc == D3DFMT.DXT5:
                self._mode = "RGBA"
                self.pixel_format = "DXT5"
                n = 3
            elif fourcc in (D3DFMT.BC4U, D3DFMT.ATI1):
                self._mode = "L"
                self.pixel_format = "BC4"
                n = 4
            elif fourcc == D3DFMT.BC5S:
                self._mode = "RGB"
                self.pixel_format = "BC5S"
                n = 5
            elif fourcc in (D3DFMT.BC5U, D3DFMT.ATI2):
                self._mode = "RGB"
                self.pixel_format = "BC5"
                n = 5
            elif fourcc == D3DFMT.DX10:
                offset += 20
                # ignoring flags which pertain to volume textures and cubemaps
                (dxgi_format,) = struct.unpack("<I", self.fp.read(4))
                self.fp.read(16)
                if dxgi_format in (
                    DXGI_FORMAT.BC1_UNORM,
                    DXGI_FORMAT.BC1_TYPELESS,
                ):
                    self._mode = "RGBA"
                    self.pixel_format = "BC1"
                    n = 1
                elif dxgi_format in (DXGI_FORMAT.BC2_TYPELESS, DXGI_FORMAT.BC2_UNORM):
                    self._mode = "RGBA"
                    self.pixel_format = "BC2"
                    n = 2
                elif dxgi_format in (DXGI_FORMAT.BC3_TYPELESS, DXGI_FORMAT.BC3_UNORM):
                    self._mode = "RGBA"
                    self.pixel_format = "BC3"
                    n = 3
                elif dxgi_format in (DXGI_FORMAT.BC4_TYPELESS, DXGI_FORMAT.BC4_UNORM):
                    self._mode = "L"
                    self.pixel_format = "BC4"
                    n = 4
                elif dxgi_format in (DXGI_FORMAT.BC5_TYPELESS, DXGI_FORMAT.BC5_UNORM):
                    self._mode = "RGB"
                    self.pixel_format = "BC5"
                    n = 5
                elif dxgi_format == DXGI_FORMAT.BC5_SNORM:
                    self._mode = "RGB"
                    self.pixel_format = "BC5S"
                    n = 5
                elif dxgi_format == DXGI_FORMAT.BC6H_UF16:
                    self._mode = "RGB"
                    self.pixel_format = "BC6H"
                    n = 6
                elif dxgi_format == DXGI_FORMAT.BC6H_SF16:
                    self._mode = "RGB"
                    self.pixel_format = "BC6HS"
                    n = 6
                elif dxgi_format in (
                    DXGI_FORMAT.BC7_TYPELESS,
                    DXGI_FORMAT.BC7_UNORM,
                    DXGI_FORMAT.BC7_UNORM_SRGB,
                ):
                    self._mode = "RGBA"
                    self.pixel_format = "BC7"
                    n = 7
                    if dxgi_format == DXGI_FORMAT.BC7_UNORM_SRGB:
                        self.info["gamma"] = 1 / 2.2
                elif dxgi_format in (
                    DXGI_FORMAT.R8G8B8A8_TYPELESS,
                    DXGI_FORMAT.R8G8B8A8_UNORM,
                    DXGI_FORMAT.R8G8B8A8_UNORM_SRGB,
                ):
                    self._mode = "RGBA"
                    if dxgi_format == DXGI_FORMAT.R8G8B8A8_UNORM_SRGB:
                        self.info["gamma"] = 1 / 2.2
                else:
                    msg = f"Unimplemented DXGI format {dxgi_format}"
                    raise NotImplementedError(msg)
            else:
                msg = f"Unimplemented pixel format {repr(fourcc)}"
                raise NotImplementedError(msg)
        else:
            msg = f"Unknown pixel format flags {pfflags}"
            raise NotImplementedError(msg)

        if n:
            self.tile = [
                ImageFile._Tile("bcn", extents, offset, (n, self.pixel_format))
            ]
        else:
            self.tile = [ImageFile._Tile("raw", extents, 0, rawmode or self.mode)]

    def load_seek(self, pos: int) -> None:
        pass


class DdsRgbDecoder(ImageFile.PyDecoder):
    _pulls_fd = True

    def decode(self, buffer: bytes | Image.SupportsArrayInterface) -> tuple[int, int]:
        assert self.fd is not None
        bitcount, masks = self.args

        # Some masks will be padded with zeros, e.g. R 0b11 G 0b1100
        # Calculate how many zeros each mask is padded with
        mask_offsets = []
        # And the maximum value of each channel without the padding
        mask_totals = []
        for mask in masks:
            offset = 0
            if mask != 0:
                while mask >> (offset + 1) << (offset + 1) == mask:
                    offset += 1
            mask_offsets.append(offset)
            mask_totals.append(mask >> offset)

        data = bytearray()
        bytecount = bitcount // 8
        dest_length = self.state.xsize * self.state.ysize * len(masks)
        while len(data) < dest_length:
            value = int.from_bytes(self.fd.read(bytecount), "little")
            for i, mask in enumerate(masks):
                masked_value = value & mask
                # Remove the zero padding, and scale it to 8 bits
                data += o8(
                    int(((masked_value >> mask_offsets[i]) / mask_totals[i]) * 255)
                )
        self.set_as_raw(data)
        return -1, 0


def _save(im: Image.Image, fp: IO[bytes], filename: str | bytes) -> None:
    if im.mode not in ("RGB", "RGBA", "L", "LA"):
        msg = f"cannot write mode {im.mode} as DDS"
        raise OSError(msg)

    flags = DDSD.CAPS | DDSD.HEIGHT | DDSD.WIDTH | DDSD.PIXELFORMAT
    bitcount = len(im.getbands()) * 8
    pixel_format = im.encoderinfo.get("pixel_format")
    args: tuple[int] | str
    if pixel_format:
        codec_name = "bcn"
        flags |= DDSD.LINEARSIZE
        pitch = (im.width + 3) * 4
        rgba_mask = [0, 0, 0, 0]
        pixel_flags = DDPF.FOURCC
        if pixel_format == "DXT1":
            fourcc = D3DFMT.DXT1
            args = (1,)
        elif pixel_format == "DXT3":
            fourcc = D3DFMT.DXT3
            args = (2,)
        elif pixel_format == "DXT5":
            fourcc = D3DFMT.DXT5
            args = (3,)
        else:
            fourcc = D3DFMT.DX10
            if pixel_format == "BC2":
                args = (2,)
                dxgi_format = DXGI_FORMAT.BC2_TYPELESS
            elif pixel_format == "BC3":
                args = (3,)
                dxgi_format = DXGI_FORMAT.BC3_TYPELESS
            elif pixel_format == "BC5":
                args = (5,)
                dxgi_format = DXGI_FORMAT.BC5_TYPELESS
                if im.mode != "RGB":
                    msg = "only RGB mode can be written as BC5"
                    raise OSError(msg)
            else:
                msg = f"cannot write pixel format {pixel_format}"
                raise OSError(msg)
    else:
        codec_name = "raw"
        flags |= DDSD.PITCH
        pitch = (im.width * bitcount + 7) // 8

        alpha = im.mode[-1] == "A"
        if im.mode[0] == "L":
            pixel_flags = DDPF.LUMINANCE
            args = im.mode
            if alpha:
                rgba_mask = [0x000000FF, 0x000000FF, 0x000000FF]
            else:
                rgba_mask = [0xFF000000, 0xFF000000, 0xFF000000]
        else:
            pixel_flags = DDPF.RGB
            args = im.mode[::-1]
            rgba_mask = [0x00FF0000, 0x0000FF00, 0x000000FF]

            if alpha:
                r, g, b, a = im.split()
                im = Image.merge("RGBA", (a, r, g, b))
        if alpha:
            pixel_flags |= DDPF.ALPHAPIXELS
        rgba_mask.append(0xFF000000 if alpha else 0)

        fourcc = D3DFMT.UNKNOWN
    fp.write(
        o32(DDS_MAGIC)
        + struct.pack(
            "<7I",
            124,  # header size
            flags,  # flags
            im.height,
            im.width,
            pitch,
            0,  # depth
            0,  # mipmaps
        )
        + struct.pack("11I", *((0,) * 11))  # reserved
        # pfsize, pfflags, fourcc, bitcount
        + struct.pack("<4I", 32, pixel_flags, fourcc, bitcount)
        + struct.pack("<4I", *rgba_mask)  # dwRGBABitMask
        + struct.pack("<5I", DDSCAPS.TEXTURE, 0, 0, 0, 0)
    )
    if fourcc == D3DFMT.DX10:
        fp.write(
            # dxgi_format, 2D resource, misc, array size, straight alpha
            struct.pack("<5I", dxgi_format, 3, 0, 0, 1)
        )
    ImageFile._save(im, fp, [ImageFile._Tile(codec_name, (0, 0) + im.size, 0, args)])


def _accept(prefix: bytes) -> bool:
    return prefix.startswith(b"DDS ")


Image.register_open(DdsImageFile.format, DdsImageFile, _accept)
Image.register_decoder("dds_rgb", DdsRgbDecoder)
Image.register_save(DdsImageFile.format, _save)
Image.register_extension(DdsImageFile.format, ".dds")
