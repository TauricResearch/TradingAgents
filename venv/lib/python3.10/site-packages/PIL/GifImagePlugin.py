#
# The Python Imaging Library.
# $Id$
#
# GIF file handling
#
# History:
# 1995-09-01 fl   Created
# 1996-12-14 fl   Added interlace support
# 1996-12-30 fl   Added animation support
# 1997-01-05 fl   Added write support, fixed local colour map bug
# 1997-02-23 fl   Make sure to load raster data in getdata()
# 1997-07-05 fl   Support external decoder (0.4)
# 1998-07-09 fl   Handle all modes when saving (0.5)
# 1998-07-15 fl   Renamed offset attribute to avoid name clash
# 2001-04-16 fl   Added rewind support (seek to frame 0) (0.6)
# 2001-04-17 fl   Added palette optimization (0.7)
# 2002-06-06 fl   Added transparency support for save (0.8)
# 2004-02-24 fl   Disable interlacing for small images
#
# Copyright (c) 1997-2004 by Secret Labs AB
# Copyright (c) 1995-2004 by Fredrik Lundh
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import itertools
import math
import os
import subprocess
from enum import IntEnum
from functools import cached_property
from typing import IO, Any, Literal, NamedTuple, Union, cast

from . import (
    Image,
    ImageChops,
    ImageFile,
    ImageMath,
    ImageOps,
    ImagePalette,
    ImageSequence,
)
from ._binary import i16le as i16
from ._binary import o8
from ._binary import o16le as o16
from ._util import DeferredError

TYPE_CHECKING = False
if TYPE_CHECKING:
    from . import _imaging
    from ._typing import Buffer


class LoadingStrategy(IntEnum):
    """.. versionadded:: 9.1.0"""

    RGB_AFTER_FIRST = 0
    RGB_AFTER_DIFFERENT_PALETTE_ONLY = 1
    RGB_ALWAYS = 2


#: .. versionadded:: 9.1.0
LOADING_STRATEGY = LoadingStrategy.RGB_AFTER_FIRST

# --------------------------------------------------------------------
# Identify/read GIF files


def _accept(prefix: bytes) -> bool:
    return prefix.startswith((b"GIF87a", b"GIF89a"))


##
# Image plugin for GIF images.  This plugin supports both GIF87 and
# GIF89 images.


class GifImageFile(ImageFile.ImageFile):
    format = "GIF"
    format_description = "Compuserve GIF"
    _close_exclusive_fp_after_loading = False

    global_palette = None

    def data(self) -> bytes | None:
        s = self.fp.read(1)
        if s and s[0]:
            return self.fp.read(s[0])
        return None

    def _is_palette_needed(self, p: bytes) -> bool:
        for i in range(0, len(p), 3):
            if not (i // 3 == p[i] == p[i + 1] == p[i + 2]):
                return True
        return False

    def _open(self) -> None:
        # Screen
        s = self.fp.read(13)
        if not _accept(s):
            msg = "not a GIF file"
            raise SyntaxError(msg)

        self.info["version"] = s[:6]
        self._size = i16(s, 6), i16(s, 8)
        flags = s[10]
        bits = (flags & 7) + 1

        if flags & 128:
            # get global palette
            self.info["background"] = s[11]
            # check if palette contains colour indices
            p = self.fp.read(3 << bits)
            if self._is_palette_needed(p):
                p = ImagePalette.raw("RGB", p)
                self.global_palette = self.palette = p

        self._fp = self.fp  # FIXME: hack
        self.__rewind = self.fp.tell()
        self._n_frames: int | None = None
        self._seek(0)  # get ready to read first frame

    @property
    def n_frames(self) -> int:
        if self._n_frames is None:
            current = self.tell()
            try:
                while True:
                    self._seek(self.tell() + 1, False)
            except EOFError:
                self._n_frames = self.tell() + 1
            self.seek(current)
        return self._n_frames

    @cached_property
    def is_animated(self) -> bool:
        if self._n_frames is not None:
            return self._n_frames != 1

        current = self.tell()
        if current:
            return True

        try:
            self._seek(1, False)
            is_animated = True
        except EOFError:
            is_animated = False

        self.seek(current)
        return is_animated

    def seek(self, frame: int) -> None:
        if not self._seek_check(frame):
            return
        if frame < self.__frame:
            self._im = None
            self._seek(0)

        last_frame = self.__frame
        for f in range(self.__frame + 1, frame + 1):
            try:
                self._seek(f)
            except EOFError as e:
                self.seek(last_frame)
                msg = "no more images in GIF file"
                raise EOFError(msg) from e

    def _seek(self, frame: int, update_image: bool = True) -> None:
        if isinstance(self._fp, DeferredError):
            raise self._fp.ex
        if frame == 0:
            # rewind
            self.__offset = 0
            self.dispose: _imaging.ImagingCore | None = None
            self.__frame = -1
            self._fp.seek(self.__rewind)
            self.disposal_method = 0
            if "comment" in self.info:
                del self.info["comment"]
        else:
            # ensure that the previous frame was loaded
            if self.tile and update_image:
                self.load()

        if frame != self.__frame + 1:
            msg = f"cannot seek to frame {frame}"
            raise ValueError(msg)

        self.fp = self._fp
        if self.__offset:
            # backup to last frame
            self.fp.seek(self.__offset)
            while self.data():
                pass
            self.__offset = 0

        s = self.fp.read(1)
        if not s or s == b";":
            msg = "no more images in GIF file"
            raise EOFError(msg)

        palette: ImagePalette.ImagePalette | Literal[False] | None = None

        info: dict[str, Any] = {}
        frame_transparency = None
        interlace = None
        frame_dispose_extent = None
        while True:
            if not s:
                s = self.fp.read(1)
            if not s or s == b";":
                break

            elif s == b"!":
                #
                # extensions
                #
                s = self.fp.read(1)
                block = self.data()
                if s[0] == 249 and block is not None:
                    #
                    # graphic control extension
                    #
                    flags = block[0]
                    if flags & 1:
                        frame_transparency = block[3]
                    info["duration"] = i16(block, 1) * 10

                    # disposal method - find the value of bits 4 - 6
                    dispose_bits = 0b00011100 & flags
                    dispose_bits = dispose_bits >> 2
                    if dispose_bits:
                        # only set the dispose if it is not
                        # unspecified. I'm not sure if this is
                        # correct, but it seems to prevent the last
                        # frame from looking odd for some animations
                        self.disposal_method = dispose_bits
                elif s[0] == 254:
                    #
                    # comment extension
                    #
                    comment = b""

                    # Read this comment block
                    while block:
                        comment += block
                        block = self.data()

                    if "comment" in info:
                        # If multiple comment blocks in frame, separate with \n
                        info["comment"] += b"\n" + comment
                    else:
                        info["comment"] = comment
                    s = None
                    continue
                elif s[0] == 255 and frame == 0 and block is not None:
                    #
                    # application extension
                    #
                    info["extension"] = block, self.fp.tell()
                    if block.startswith(b"NETSCAPE2.0"):
                        block = self.data()
                        if block and len(block) >= 3 and block[0] == 1:
                            self.info["loop"] = i16(block, 1)
                while self.data():
                    pass

            elif s == b",":
                #
                # local image
                #
                s = self.fp.read(9)

                # extent
                x0, y0 = i16(s, 0), i16(s, 2)
                x1, y1 = x0 + i16(s, 4), y0 + i16(s, 6)
                if (x1 > self.size[0] or y1 > self.size[1]) and update_image:
                    self._size = max(x1, self.size[0]), max(y1, self.size[1])
                    Image._decompression_bomb_check(self._size)
                frame_dispose_extent = x0, y0, x1, y1
                flags = s[8]

                interlace = (flags & 64) != 0

                if flags & 128:
                    bits = (flags & 7) + 1
                    p = self.fp.read(3 << bits)
                    if self._is_palette_needed(p):
                        palette = ImagePalette.raw("RGB", p)
                    else:
                        palette = False

                # image data
                bits = self.fp.read(1)[0]
                self.__offset = self.fp.tell()
                break
            s = None

        if interlace is None:
            msg = "image not found in GIF frame"
            raise EOFError(msg)

        self.__frame = frame
        if not update_image:
            return

        self.tile = []

        if self.dispose:
            self.im.paste(self.dispose, self.dispose_extent)

        self._frame_palette = palette if palette is not None else self.global_palette
        self._frame_transparency = frame_transparency
        if frame == 0:
            if self._frame_palette:
                if LOADING_STRATEGY == LoadingStrategy.RGB_ALWAYS:
                    self._mode = "RGBA" if frame_transparency is not None else "RGB"
                else:
                    self._mode = "P"
            else:
                self._mode = "L"

            if palette:
                self.palette = palette
            elif self.global_palette:
                from copy import copy

                self.palette = copy(self.global_palette)
            else:
                self.palette = None
        else:
            if self.mode == "P":
                if (
                    LOADING_STRATEGY != LoadingStrategy.RGB_AFTER_DIFFERENT_PALETTE_ONLY
                    or palette
                ):
                    if "transparency" in self.info:
                        self.im.putpalettealpha(self.info["transparency"], 0)
                        self.im = self.im.convert("RGBA", Image.Dither.FLOYDSTEINBERG)
                        self._mode = "RGBA"
                        del self.info["transparency"]
                    else:
                        self._mode = "RGB"
                        self.im = self.im.convert("RGB", Image.Dither.FLOYDSTEINBERG)

        def _rgb(color: int) -> tuple[int, int, int]:
            if self._frame_palette:
                if color * 3 + 3 > len(self._frame_palette.palette):
                    color = 0
                return cast(
                    tuple[int, int, int],
                    tuple(self._frame_palette.palette[color * 3 : color * 3 + 3]),
                )
            else:
                return (color, color, color)

        self.dispose = None
        self.dispose_extent: tuple[int, int, int, int] | None = frame_dispose_extent
        if self.dispose_extent and self.disposal_method >= 2:
            try:
                if self.disposal_method == 2:
                    # replace with background colour

                    # only dispose the extent in this frame
                    x0, y0, x1, y1 = self.dispose_extent
                    dispose_size = (x1 - x0, y1 - y0)

                    Image._decompression_bomb_check(dispose_size)

                    # by convention, attempt to use transparency first
                    dispose_mode = "P"
                    color = self.info.get("transparency", frame_transparency)
                    if color is not None:
                        if self.mode in ("RGB", "RGBA"):
                            dispose_mode = "RGBA"
                            color = _rgb(color) + (0,)
                    else:
                        color = self.info.get("background", 0)
                        if self.mode in ("RGB", "RGBA"):
                            dispose_mode = "RGB"
                            color = _rgb(color)
                    self.dispose = Image.core.fill(dispose_mode, dispose_size, color)
                else:
                    # replace with previous contents
                    if self._im is not None:
                        # only dispose the extent in this frame
                        self.dispose = self._crop(self.im, self.dispose_extent)
                    elif frame_transparency is not None:
                        x0, y0, x1, y1 = self.dispose_extent
                        dispose_size = (x1 - x0, y1 - y0)

                        Image._decompression_bomb_check(dispose_size)
                        dispose_mode = "P"
                        color = frame_transparency
                        if self.mode in ("RGB", "RGBA"):
                            dispose_mode = "RGBA"
                            color = _rgb(frame_transparency) + (0,)
                        self.dispose = Image.core.fill(
                            dispose_mode, dispose_size, color
                        )
            except AttributeError:
                pass

        if interlace is not None:
            transparency = -1
            if frame_transparency is not None:
                if frame == 0:
                    if LOADING_STRATEGY != LoadingStrategy.RGB_ALWAYS:
                        self.info["transparency"] = frame_transparency
                elif self.mode not in ("RGB", "RGBA"):
                    transparency = frame_transparency
            self.tile = [
                ImageFile._Tile(
                    "gif",
                    (x0, y0, x1, y1),
                    self.__offset,
                    (bits, interlace, transparency),
                )
            ]

        if info.get("comment"):
            self.info["comment"] = info["comment"]
        for k in ["duration", "extension"]:
            if k in info:
                self.info[k] = info[k]
            elif k in self.info:
                del self.info[k]

    def load_prepare(self) -> None:
        temp_mode = "P" if self._frame_palette else "L"
        self._prev_im = None
        if self.__frame == 0:
            if self._frame_transparency is not None:
                self.im = Image.core.fill(
                    temp_mode, self.size, self._frame_transparency
                )
        elif self.mode in ("RGB", "RGBA"):
            self._prev_im = self.im
            if self._frame_palette:
                self.im = Image.core.fill("P", self.size, self._frame_transparency or 0)
                self.im.putpalette("RGB", *self._frame_palette.getdata())
            else:
                self._im = None
        if not self._prev_im and self._im is not None and self.size != self.im.size:
            expanded_im = Image.core.fill(self.im.mode, self.size)
            if self._frame_palette:
                expanded_im.putpalette("RGB", *self._frame_palette.getdata())
            expanded_im.paste(self.im, (0, 0) + self.im.size)

            self.im = expanded_im
        self._mode = temp_mode
        self._frame_palette = None

        super().load_prepare()

    def load_end(self) -> None:
        if self.__frame == 0:
            if self.mode == "P" and LOADING_STRATEGY == LoadingStrategy.RGB_ALWAYS:
                if self._frame_transparency is not None:
                    self.im.putpalettealpha(self._frame_transparency, 0)
                    self._mode = "RGBA"
                else:
                    self._mode = "RGB"
                self.im = self.im.convert(self.mode, Image.Dither.FLOYDSTEINBERG)
            return
        if not self._prev_im:
            return
        if self.size != self._prev_im.size:
            if self._frame_transparency is not None:
                expanded_im = Image.core.fill("RGBA", self.size)
            else:
                expanded_im = Image.core.fill("P", self.size)
                expanded_im.putpalette("RGB", "RGB", self.im.getpalette())
                expanded_im = expanded_im.convert("RGB")
            expanded_im.paste(self._prev_im, (0, 0) + self._prev_im.size)

            self._prev_im = expanded_im
            assert self._prev_im is not None
        if self._frame_transparency is not None:
            if self.mode == "L":
                frame_im = self.im.convert_transparent("LA", self._frame_transparency)
            else:
                self.im.putpalettealpha(self._frame_transparency, 0)
                frame_im = self.im.convert("RGBA")
        else:
            frame_im = self.im.convert("RGB")

        assert self.dispose_extent is not None
        frame_im = self._crop(frame_im, self.dispose_extent)

        self.im = self._prev_im
        self._mode = self.im.mode
        if frame_im.mode in ("LA", "RGBA"):
            self.im.paste(frame_im, self.dispose_extent, frame_im)
        else:
            self.im.paste(frame_im, self.dispose_extent)

    def tell(self) -> int:
        return self.__frame


# --------------------------------------------------------------------
# Write GIF files


RAWMODE = {"1": "L", "L": "L", "P": "P"}


def _normalize_mode(im: Image.Image) -> Image.Image:
    """
    Takes an image (or frame), returns an image in a mode that is appropriate
    for saving in a Gif.

    It may return the original image, or it may return an image converted to
    palette or 'L' mode.

    :param im: Image object
    :returns: Image object
    """
    if im.mode in RAWMODE:
        im.load()
        return im
    if Image.getmodebase(im.mode) == "RGB":
        im = im.convert("P", palette=Image.Palette.ADAPTIVE)
        assert im.palette is not None
        if im.palette.mode == "RGBA":
            for rgba in im.palette.colors:
                if rgba[3] == 0:
                    im.info["transparency"] = im.palette.colors[rgba]
                    break
        return im
    return im.convert("L")


_Palette = Union[bytes, bytearray, list[int], ImagePalette.ImagePalette]


def _normalize_palette(
    im: Image.Image, palette: _Palette | None, info: dict[str, Any]
) -> Image.Image:
    """
    Normalizes the palette for image.
      - Sets the palette to the incoming palette, if provided.
      - Ensures that there's a palette for L mode images
      - Optimizes the palette if necessary/desired.

    :param im: Image object
    :param palette: bytes object containing the source palette, or ....
    :param info: encoderinfo
    :returns: Image object
    """
    source_palette = None
    if palette:
        # a bytes palette
        if isinstance(palette, (bytes, bytearray, list)):
            source_palette = bytearray(palette[:768])
        if isinstance(palette, ImagePalette.ImagePalette):
            source_palette = bytearray(palette.palette)

    if im.mode == "P":
        if not source_palette:
            im_palette = im.getpalette(None)
            assert im_palette is not None
            source_palette = bytearray(im_palette)
    else:  # L-mode
        if not source_palette:
            source_palette = bytearray(i // 3 for i in range(768))
        im.palette = ImagePalette.ImagePalette("RGB", palette=source_palette)
    assert source_palette is not None

    if palette:
        used_palette_colors: list[int | None] = []
        assert im.palette is not None
        for i in range(0, len(source_palette), 3):
            source_color = tuple(source_palette[i : i + 3])
            index = im.palette.colors.get(source_color)
            if index in used_palette_colors:
                index = None
            used_palette_colors.append(index)
        for i, index in enumerate(used_palette_colors):
            if index is None:
                for j in range(len(used_palette_colors)):
                    if j not in used_palette_colors:
                        used_palette_colors[i] = j
                        break
        dest_map: list[int] = []
        for index in used_palette_colors:
            assert index is not None
            dest_map.append(index)
        im = im.remap_palette(dest_map)
    else:
        optimized_palette_colors = _get_optimize(im, info)
        if optimized_palette_colors is not None:
            im = im.remap_palette(optimized_palette_colors, source_palette)
            if "transparency" in info:
                try:
                    info["transparency"] = optimized_palette_colors.index(
                        info["transparency"]
                    )
                except ValueError:
                    del info["transparency"]
            return im

    assert im.palette is not None
    im.palette.palette = source_palette
    return im


def _write_single_frame(
    im: Image.Image,
    fp: IO[bytes],
    palette: _Palette | None,
) -> None:
    im_out = _normalize_mode(im)
    for k, v in im_out.info.items():
        if isinstance(k, str):
            im.encoderinfo.setdefault(k, v)
    im_out = _normalize_palette(im_out, palette, im.encoderinfo)

    for s in _get_global_header(im_out, im.encoderinfo):
        fp.write(s)

    # local image header
    flags = 0
    if get_interlace(im):
        flags = flags | 64
    _write_local_header(fp, im, (0, 0), flags)

    im_out.encoderconfig = (8, get_interlace(im))
    ImageFile._save(
        im_out, fp, [ImageFile._Tile("gif", (0, 0) + im.size, 0, RAWMODE[im_out.mode])]
    )

    fp.write(b"\0")  # end of image data


def _getbbox(
    base_im: Image.Image, im_frame: Image.Image
) -> tuple[Image.Image, tuple[int, int, int, int] | None]:
    palette_bytes = [
        bytes(im.palette.palette) if im.palette else b"" for im in (base_im, im_frame)
    ]
    if palette_bytes[0] != palette_bytes[1]:
        im_frame = im_frame.convert("RGBA")
        base_im = base_im.convert("RGBA")
    delta = ImageChops.subtract_modulo(im_frame, base_im)
    return delta, delta.getbbox(alpha_only=False)


class _Frame(NamedTuple):
    im: Image.Image
    bbox: tuple[int, int, int, int] | None
    encoderinfo: dict[str, Any]


def _write_multiple_frames(
    im: Image.Image, fp: IO[bytes], palette: _Palette | None
) -> bool:
    duration = im.encoderinfo.get("duration")
    disposal = im.encoderinfo.get("disposal", im.info.get("disposal"))

    im_frames: list[_Frame] = []
    previous_im: Image.Image | None = None
    frame_count = 0
    background_im = None
    for imSequence in itertools.chain([im], im.encoderinfo.get("append_images", [])):
        for im_frame in ImageSequence.Iterator(imSequence):
            # a copy is required here since seek can still mutate the image
            im_frame = _normalize_mode(im_frame.copy())
            if frame_count == 0:
                for k, v in im_frame.info.items():
                    if k == "transparency":
                        continue
                    if isinstance(k, str):
                        im.encoderinfo.setdefault(k, v)

            encoderinfo = im.encoderinfo.copy()
            if "transparency" in im_frame.info:
                encoderinfo.setdefault("transparency", im_frame.info["transparency"])
            im_frame = _normalize_palette(im_frame, palette, encoderinfo)
            if isinstance(duration, (list, tuple)):
                encoderinfo["duration"] = duration[frame_count]
            elif duration is None and "duration" in im_frame.info:
                encoderinfo["duration"] = im_frame.info["duration"]
            if isinstance(disposal, (list, tuple)):
                encoderinfo["disposal"] = disposal[frame_count]
            frame_count += 1

            diff_frame = None
            if im_frames and previous_im:
                # delta frame
                delta, bbox = _getbbox(previous_im, im_frame)
                if not bbox:
                    # This frame is identical to the previous frame
                    if encoderinfo.get("duration"):
                        im_frames[-1].encoderinfo["duration"] += encoderinfo["duration"]
                    continue
                if im_frames[-1].encoderinfo.get("disposal") == 2:
                    # To appear correctly in viewers using a convention,
                    # only consider transparency, and not background color
                    color = im.encoderinfo.get(
                        "transparency", im.info.get("transparency")
                    )
                    if color is not None:
                        if background_im is None:
                            background = _get_background(im_frame, color)
                            background_im = Image.new("P", im_frame.size, background)
                            first_palette = im_frames[0].im.palette
                            assert first_palette is not None
                            background_im.putpalette(first_palette, first_palette.mode)
                        bbox = _getbbox(background_im, im_frame)[1]
                    else:
                        bbox = (0, 0) + im_frame.size
                elif encoderinfo.get("optimize") and im_frame.mode != "1":
                    if "transparency" not in encoderinfo:
                        assert im_frame.palette is not None
                        try:
                            encoderinfo["transparency"] = (
                                im_frame.palette._new_color_index(im_frame)
                            )
                        except ValueError:
                            pass
                    if "transparency" in encoderinfo:
                        # When the delta is zero, fill the image with transparency
                        diff_frame = im_frame.copy()
                        fill = Image.new("P", delta.size, encoderinfo["transparency"])
                        if delta.mode == "RGBA":
                            r, g, b, a = delta.split()
                            mask = ImageMath.lambda_eval(
                                lambda args: args["convert"](
                                    args["max"](
                                        args["max"](
                                            args["max"](args["r"], args["g"]), args["b"]
                                        ),
                                        args["a"],
                                    )
                                    * 255,
                                    "1",
                                ),
                                r=r,
                                g=g,
                                b=b,
                                a=a,
                            )
                        else:
                            if delta.mode == "P":
                                # Convert to L without considering palette
                                delta_l = Image.new("L", delta.size)
                                delta_l.putdata(delta.getdata())
                                delta = delta_l
                            mask = ImageMath.lambda_eval(
                                lambda args: args["convert"](args["im"] * 255, "1"),
                                im=delta,
                            )
                        diff_frame.paste(fill, mask=ImageOps.invert(mask))
            else:
                bbox = None
            previous_im = im_frame
            im_frames.append(_Frame(diff_frame or im_frame, bbox, encoderinfo))

    if len(im_frames) == 1:
        if "duration" in im.encoderinfo:
            # Since multiple frames will not be written, use the combined duration
            im.encoderinfo["duration"] = im_frames[0].encoderinfo["duration"]
        return False

    for frame_data in im_frames:
        im_frame = frame_data.im
        if not frame_data.bbox:
            # global header
            for s in _get_global_header(im_frame, frame_data.encoderinfo):
                fp.write(s)
            offset = (0, 0)
        else:
            # compress difference
            if not palette:
                frame_data.encoderinfo["include_color_table"] = True

            if frame_data.bbox != (0, 0) + im_frame.size:
                im_frame = im_frame.crop(frame_data.bbox)
            offset = frame_data.bbox[:2]
        _write_frame_data(fp, im_frame, offset, frame_data.encoderinfo)
    return True


def _save_all(im: Image.Image, fp: IO[bytes], filename: str | bytes) -> None:
    _save(im, fp, filename, save_all=True)


def _save(
    im: Image.Image, fp: IO[bytes], filename: str | bytes, save_all: bool = False
) -> None:
    # header
    if "palette" in im.encoderinfo or "palette" in im.info:
        palette = im.encoderinfo.get("palette", im.info.get("palette"))
    else:
        palette = None
        im.encoderinfo.setdefault("optimize", True)

    if not save_all or not _write_multiple_frames(im, fp, palette):
        _write_single_frame(im, fp, palette)

    fp.write(b";")  # end of file

    if hasattr(fp, "flush"):
        fp.flush()


def get_interlace(im: Image.Image) -> int:
    interlace = im.encoderinfo.get("interlace", 1)

    # workaround for @PIL153
    if min(im.size) < 16:
        interlace = 0

    return interlace


def _write_local_header(
    fp: IO[bytes], im: Image.Image, offset: tuple[int, int], flags: int
) -> None:
    try:
        transparency = im.encoderinfo["transparency"]
    except KeyError:
        transparency = None

    if "duration" in im.encoderinfo:
        duration = int(im.encoderinfo["duration"] / 10)
    else:
        duration = 0

    disposal = int(im.encoderinfo.get("disposal", 0))

    if transparency is not None or duration != 0 or disposal:
        packed_flag = 1 if transparency is not None else 0
        packed_flag |= disposal << 2

        fp.write(
            b"!"
            + o8(249)  # extension intro
            + o8(4)  # length
            + o8(packed_flag)  # packed fields
            + o16(duration)  # duration
            + o8(transparency or 0)  # transparency index
            + o8(0)
        )

    include_color_table = im.encoderinfo.get("include_color_table")
    if include_color_table:
        palette_bytes = _get_palette_bytes(im)
        color_table_size = _get_color_table_size(palette_bytes)
        if color_table_size:
            flags = flags | 128  # local color table flag
            flags = flags | color_table_size

    fp.write(
        b","
        + o16(offset[0])  # offset
        + o16(offset[1])
        + o16(im.size[0])  # size
        + o16(im.size[1])
        + o8(flags)  # flags
    )
    if include_color_table and color_table_size:
        fp.write(_get_header_palette(palette_bytes))
    fp.write(o8(8))  # bits


def _save_netpbm(im: Image.Image, fp: IO[bytes], filename: str | bytes) -> None:
    # Unused by default.
    # To use, uncomment the register_save call at the end of the file.
    #
    # If you need real GIF compression and/or RGB quantization, you
    # can use the external NETPBM/PBMPLUS utilities.  See comments
    # below for information on how to enable this.
    tempfile = im._dump()

    try:
        with open(filename, "wb") as f:
            if im.mode != "RGB":
                subprocess.check_call(
                    ["ppmtogif", tempfile], stdout=f, stderr=subprocess.DEVNULL
                )
            else:
                # Pipe ppmquant output into ppmtogif
                # "ppmquant 256 %s | ppmtogif > %s" % (tempfile, filename)
                quant_cmd = ["ppmquant", "256", tempfile]
                togif_cmd = ["ppmtogif"]
                quant_proc = subprocess.Popen(
                    quant_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
                )
                togif_proc = subprocess.Popen(
                    togif_cmd,
                    stdin=quant_proc.stdout,
                    stdout=f,
                    stderr=subprocess.DEVNULL,
                )

                # Allow ppmquant to receive SIGPIPE if ppmtogif exits
                assert quant_proc.stdout is not None
                quant_proc.stdout.close()

                retcode = quant_proc.wait()
                if retcode:
                    raise subprocess.CalledProcessError(retcode, quant_cmd)

                retcode = togif_proc.wait()
                if retcode:
                    raise subprocess.CalledProcessError(retcode, togif_cmd)
    finally:
        try:
            os.unlink(tempfile)
        except OSError:
            pass


# Force optimization so that we can test performance against
# cases where it took lots of memory and time previously.
_FORCE_OPTIMIZE = False


def _get_optimize(im: Image.Image, info: dict[str, Any]) -> list[int] | None:
    """
    Palette optimization is a potentially expensive operation.

    This function determines if the palette should be optimized using
    some heuristics, then returns the list of palette entries in use.

    :param im: Image object
    :param info: encoderinfo
    :returns: list of indexes of palette entries in use, or None
    """
    if im.mode in ("P", "L") and info and info.get("optimize"):
        # Potentially expensive operation.

        # The palette saves 3 bytes per color not used, but palette
        # lengths are restricted to 3*(2**N) bytes. Max saving would
        # be 768 -> 6 bytes if we went all the way down to 2 colors.
        # * If we're over 128 colors, we can't save any space.
        # * If there aren't any holes, it's not worth collapsing.
        # * If we have a 'large' image, the palette is in the noise.

        # create the new palette if not every color is used
        optimise = _FORCE_OPTIMIZE or im.mode == "L"
        if optimise or im.width * im.height < 512 * 512:
            # check which colors are used
            used_palette_colors = []
            for i, count in enumerate(im.histogram()):
                if count:
                    used_palette_colors.append(i)

            if optimise or max(used_palette_colors) >= len(used_palette_colors):
                return used_palette_colors

            assert im.palette is not None
            num_palette_colors = len(im.palette.palette) // Image.getmodebands(
                im.palette.mode
            )
            current_palette_size = 1 << (num_palette_colors - 1).bit_length()
            if (
                # check that the palette would become smaller when saved
                len(used_palette_colors) <= current_palette_size // 2
                # check that the palette is not already the smallest possible size
                and current_palette_size > 2
            ):
                return used_palette_colors
    return None


def _get_color_table_size(palette_bytes: bytes) -> int:
    # calculate the palette size for the header
    if not palette_bytes:
        return 0
    elif len(palette_bytes) < 9:
        return 1
    else:
        return math.ceil(math.log(len(palette_bytes) // 3, 2)) - 1


def _get_header_palette(palette_bytes: bytes) -> bytes:
    """
    Returns the palette, null padded to the next power of 2 (*3) bytes
    suitable for direct inclusion in the GIF header

    :param palette_bytes: Unpadded palette bytes, in RGBRGB form
    :returns: Null padded palette
    """
    color_table_size = _get_color_table_size(palette_bytes)

    # add the missing amount of bytes
    # the palette has to be 2<<n in size
    actual_target_size_diff = (2 << color_table_size) - len(palette_bytes) // 3
    if actual_target_size_diff > 0:
        palette_bytes += o8(0) * 3 * actual_target_size_diff
    return palette_bytes


def _get_palette_bytes(im: Image.Image) -> bytes:
    """
    Gets the palette for inclusion in the gif header

    :param im: Image object
    :returns: Bytes, len<=768 suitable for inclusion in gif header
    """
    if not im.palette:
        return b""

    palette = bytes(im.palette.palette)
    if im.palette.mode == "RGBA":
        palette = b"".join(palette[i * 4 : i * 4 + 3] for i in range(len(palette) // 3))
    return palette


def _get_background(
    im: Image.Image,
    info_background: int | tuple[int, int, int] | tuple[int, int, int, int] | None,
) -> int:
    background = 0
    if info_background:
        if isinstance(info_background, tuple):
            # WebPImagePlugin stores an RGBA value in info["background"]
            # So it must be converted to the same format as GifImagePlugin's
            # info["background"] - a global color table index
            assert im.palette is not None
            try:
                background = im.palette.getcolor(info_background, im)
            except ValueError as e:
                if str(e) not in (
                    # If all 256 colors are in use,
                    # then there is no need for the background color
                    "cannot allocate more than 256 colors",
                    # Ignore non-opaque WebP background
                    "cannot add non-opaque RGBA color to RGB palette",
                ):
                    raise
        else:
            background = info_background
    return background


def _get_global_header(im: Image.Image, info: dict[str, Any]) -> list[bytes]:
    """Return a list of strings representing a GIF header"""

    # Header Block
    # https://www.matthewflickinger.com/lab/whatsinagif/bits_and_bytes.asp

    version = b"87a"
    if im.info.get("version") == b"89a" or (
        info
        and (
            "transparency" in info
            or info.get("loop") is not None
            or info.get("duration")
            or info.get("comment")
        )
    ):
        version = b"89a"

    background = _get_background(im, info.get("background"))

    palette_bytes = _get_palette_bytes(im)
    color_table_size = _get_color_table_size(palette_bytes)

    header = [
        b"GIF"  # signature
        + version  # version
        + o16(im.size[0])  # canvas width
        + o16(im.size[1]),  # canvas height
        # Logical Screen Descriptor
        # size of global color table + global color table flag
        o8(color_table_size + 128),  # packed fields
        # background + reserved/aspect
        o8(background) + o8(0),
        # Global Color Table
        _get_header_palette(palette_bytes),
    ]
    if info.get("loop") is not None:
        header.append(
            b"!"
            + o8(255)  # extension intro
            + o8(11)
            + b"NETSCAPE2.0"
            + o8(3)
            + o8(1)
            + o16(info["loop"])  # number of loops
            + o8(0)
        )
    if info.get("comment"):
        comment_block = b"!" + o8(254)  # extension intro

        comment = info["comment"]
        if isinstance(comment, str):
            comment = comment.encode()
        for i in range(0, len(comment), 255):
            subblock = comment[i : i + 255]
            comment_block += o8(len(subblock)) + subblock

        comment_block += o8(0)
        header.append(comment_block)
    return header


def _write_frame_data(
    fp: IO[bytes],
    im_frame: Image.Image,
    offset: tuple[int, int],
    params: dict[str, Any],
) -> None:
    try:
        im_frame.encoderinfo = params

        # local image header
        _write_local_header(fp, im_frame, offset, 0)

        ImageFile._save(
            im_frame,
            fp,
            [ImageFile._Tile("gif", (0, 0) + im_frame.size, 0, RAWMODE[im_frame.mode])],
        )

        fp.write(b"\0")  # end of image data
    finally:
        del im_frame.encoderinfo


# --------------------------------------------------------------------
# Legacy GIF utilities


def getheader(
    im: Image.Image, palette: _Palette | None = None, info: dict[str, Any] | None = None
) -> tuple[list[bytes], list[int] | None]:
    """
    Legacy Method to get Gif data from image.

    Warning:: May modify image data.

    :param im: Image object
    :param palette: bytes object containing the source palette, or ....
    :param info: encoderinfo
    :returns: tuple of(list of header items, optimized palette)

    """
    if info is None:
        info = {}

    used_palette_colors = _get_optimize(im, info)

    if "background" not in info and "background" in im.info:
        info["background"] = im.info["background"]

    im_mod = _normalize_palette(im, palette, info)
    im.palette = im_mod.palette
    im.im = im_mod.im
    header = _get_global_header(im, info)

    return header, used_palette_colors


def getdata(
    im: Image.Image, offset: tuple[int, int] = (0, 0), **params: Any
) -> list[bytes]:
    """
    Legacy Method

    Return a list of strings representing this image.
    The first string is a local image header, the rest contains
    encoded image data.

    To specify duration, add the time in milliseconds,
    e.g. ``getdata(im_frame, duration=1000)``

    :param im: Image object
    :param offset: Tuple of (x, y) pixels. Defaults to (0, 0)
    :param \\**params: e.g. duration or other encoder info parameters
    :returns: List of bytes containing GIF encoded frame data

    """
    from io import BytesIO

    class Collector(BytesIO):
        data = []

        def write(self, data: Buffer) -> int:
            self.data.append(data)
            return len(data)

    im.load()  # make sure raster data is available

    fp = Collector()

    _write_frame_data(fp, im, offset, params)

    return fp.data


# --------------------------------------------------------------------
# Registry

Image.register_open(GifImageFile.format, GifImageFile, _accept)
Image.register_save(GifImageFile.format, _save)
Image.register_save_all(GifImageFile.format, _save_all)
Image.register_extension(GifImageFile.format, ".gif")
Image.register_mime(GifImageFile.format, "image/gif")

#
# Uncomment the following line if you wish to use NETPBM/PBMPLUS
# instead of the built-in "uncompressed" GIF encoder

# Image.register_save(GifImageFile.format, _save_netpbm)
