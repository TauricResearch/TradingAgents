#
# The Python Imaging Library.
# $Id$
#
# image palette object
#
# History:
# 1996-03-11 fl   Rewritten.
# 1997-01-03 fl   Up and running.
# 1997-08-23 fl   Added load hack
# 2001-04-16 fl   Fixed randint shadow bug in random()
#
# Copyright (c) 1997-2001 by Secret Labs AB
# Copyright (c) 1996-1997 by Fredrik Lundh
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import array
from collections.abc import Sequence
from typing import IO

from . import GimpGradientFile, GimpPaletteFile, ImageColor, PaletteFile

TYPE_CHECKING = False
if TYPE_CHECKING:
    from . import Image


class ImagePalette:
    """
    Color palette for palette mapped images

    :param mode: The mode to use for the palette. See:
        :ref:`concept-modes`. Defaults to "RGB"
    :param palette: An optional palette. If given, it must be a bytearray,
        an array or a list of ints between 0-255. The list must consist of
        all channels for one color followed by the next color (e.g. RGBRGBRGB).
        Defaults to an empty palette.
    """

    def __init__(
        self,
        mode: str = "RGB",
        palette: Sequence[int] | bytes | bytearray | None = None,
    ) -> None:
        self.mode = mode
        self.rawmode: str | None = None  # if set, palette contains raw data
        self.palette = palette or bytearray()
        self.dirty: int | None = None

    @property
    def palette(self) -> Sequence[int] | bytes | bytearray:
        return self._palette

    @palette.setter
    def palette(self, palette: Sequence[int] | bytes | bytearray) -> None:
        self._colors: dict[tuple[int, ...], int] | None = None
        self._palette = palette

    @property
    def colors(self) -> dict[tuple[int, ...], int]:
        if self._colors is None:
            mode_len = len(self.mode)
            self._colors = {}
            for i in range(0, len(self.palette), mode_len):
                color = tuple(self.palette[i : i + mode_len])
                if color in self._colors:
                    continue
                self._colors[color] = i // mode_len
        return self._colors

    @colors.setter
    def colors(self, colors: dict[tuple[int, ...], int]) -> None:
        self._colors = colors

    def copy(self) -> ImagePalette:
        new = ImagePalette()

        new.mode = self.mode
        new.rawmode = self.rawmode
        if self.palette is not None:
            new.palette = self.palette[:]
        new.dirty = self.dirty

        return new

    def getdata(self) -> tuple[str, Sequence[int] | bytes | bytearray]:
        """
        Get palette contents in format suitable for the low-level
        ``im.putpalette`` primitive.

        .. warning:: This method is experimental.
        """
        if self.rawmode:
            return self.rawmode, self.palette
        return self.mode, self.tobytes()

    def tobytes(self) -> bytes:
        """Convert palette to bytes.

        .. warning:: This method is experimental.
        """
        if self.rawmode:
            msg = "palette contains raw palette data"
            raise ValueError(msg)
        if isinstance(self.palette, bytes):
            return self.palette
        arr = array.array("B", self.palette)
        return arr.tobytes()

    # Declare tostring as an alias for tobytes
    tostring = tobytes

    def _new_color_index(
        self, image: Image.Image | None = None, e: Exception | None = None
    ) -> int:
        if not isinstance(self.palette, bytearray):
            self._palette = bytearray(self.palette)
        index = len(self.palette) // 3
        special_colors: tuple[int | tuple[int, ...] | None, ...] = ()
        if image:
            special_colors = (
                image.info.get("background"),
                image.info.get("transparency"),
            )
            while index in special_colors:
                index += 1
        if index >= 256:
            if image:
                # Search for an unused index
                for i, count in reversed(list(enumerate(image.histogram()))):
                    if count == 0 and i not in special_colors:
                        index = i
                        break
            if index >= 256:
                msg = "cannot allocate more than 256 colors"
                raise ValueError(msg) from e
        return index

    def getcolor(
        self,
        color: tuple[int, ...],
        image: Image.Image | None = None,
    ) -> int:
        """Given an rgb tuple, allocate palette entry.

        .. warning:: This method is experimental.
        """
        if self.rawmode:
            msg = "palette contains raw palette data"
            raise ValueError(msg)
        if isinstance(color, tuple):
            if self.mode == "RGB":
                if len(color) == 4:
                    if color[3] != 255:
                        msg = "cannot add non-opaque RGBA color to RGB palette"
                        raise ValueError(msg)
                    color = color[:3]
            elif self.mode == "RGBA":
                if len(color) == 3:
                    color += (255,)
            try:
                return self.colors[color]
            except KeyError as e:
                # allocate new color slot
                index = self._new_color_index(image, e)
                assert isinstance(self._palette, bytearray)
                self.colors[color] = index
                if index * 3 < len(self.palette):
                    self._palette = (
                        self._palette[: index * 3]
                        + bytes(color)
                        + self._palette[index * 3 + 3 :]
                    )
                else:
                    self._palette += bytes(color)
                self.dirty = 1
                return index
        else:
            msg = f"unknown color specifier: {repr(color)}"  # type: ignore[unreachable]
            raise ValueError(msg)

    def save(self, fp: str | IO[str]) -> None:
        """Save palette to text file.

        .. warning:: This method is experimental.
        """
        if self.rawmode:
            msg = "palette contains raw palette data"
            raise ValueError(msg)
        if isinstance(fp, str):
            fp = open(fp, "w")
        fp.write("# Palette\n")
        fp.write(f"# Mode: {self.mode}\n")
        for i in range(256):
            fp.write(f"{i}")
            for j in range(i * len(self.mode), (i + 1) * len(self.mode)):
                try:
                    fp.write(f" {self.palette[j]}")
                except IndexError:
                    fp.write(" 0")
            fp.write("\n")
        fp.close()


# --------------------------------------------------------------------
# Internal


def raw(rawmode: str, data: Sequence[int] | bytes | bytearray) -> ImagePalette:
    palette = ImagePalette()
    palette.rawmode = rawmode
    palette.palette = data
    palette.dirty = 1
    return palette


# --------------------------------------------------------------------
# Factories


def make_linear_lut(black: int, white: float) -> list[int]:
    if black == 0:
        return [int(white * i // 255) for i in range(256)]

    msg = "unavailable when black is non-zero"
    raise NotImplementedError(msg)  # FIXME


def make_gamma_lut(exp: float) -> list[int]:
    return [int(((i / 255.0) ** exp) * 255.0 + 0.5) for i in range(256)]


def negative(mode: str = "RGB") -> ImagePalette:
    palette = list(range(256 * len(mode)))
    palette.reverse()
    return ImagePalette(mode, [i // len(mode) for i in palette])


def random(mode: str = "RGB") -> ImagePalette:
    from random import randint

    palette = [randint(0, 255) for _ in range(256 * len(mode))]
    return ImagePalette(mode, palette)


def sepia(white: str = "#fff0c0") -> ImagePalette:
    bands = [make_linear_lut(0, band) for band in ImageColor.getrgb(white)]
    return ImagePalette("RGB", [bands[i % 3][i // 3] for i in range(256 * 3)])


def wedge(mode: str = "RGB") -> ImagePalette:
    palette = list(range(256 * len(mode)))
    return ImagePalette(mode, [i // len(mode) for i in palette])


def load(filename: str) -> tuple[bytes, str]:
    # FIXME: supports GIMP gradients only

    with open(filename, "rb") as fp:
        paletteHandlers: list[
            type[
                GimpPaletteFile.GimpPaletteFile
                | GimpGradientFile.GimpGradientFile
                | PaletteFile.PaletteFile
            ]
        ] = [
            GimpPaletteFile.GimpPaletteFile,
            GimpGradientFile.GimpGradientFile,
            PaletteFile.PaletteFile,
        ]
        for paletteHandler in paletteHandlers:
            try:
                fp.seek(0)
                lut = paletteHandler(fp).getpalette()
                if lut:
                    break
            except (SyntaxError, ValueError):
                pass
        else:
            msg = "cannot load palette"
            raise OSError(msg)

    return lut  # data, rawmode
