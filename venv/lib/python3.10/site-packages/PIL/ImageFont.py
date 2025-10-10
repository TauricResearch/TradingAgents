#
# The Python Imaging Library.
# $Id$
#
# PIL raster font management
#
# History:
# 1996-08-07 fl   created (experimental)
# 1997-08-25 fl   minor adjustments to handle fonts from pilfont 0.3
# 1999-02-06 fl   rewrote most font management stuff in C
# 1999-03-17 fl   take pth files into account in load_path (from Richard Jones)
# 2001-02-17 fl   added freetype support
# 2001-05-09 fl   added TransposedFont wrapper class
# 2002-03-04 fl   make sure we have a "L" or "1" font
# 2002-12-04 fl   skip non-directory entries in the system path
# 2003-04-29 fl   add embedded default font
# 2003-09-27 fl   added support for truetype charmap encodings
#
# Todo:
# Adapt to PILFONT2 format (16-bit fonts, compressed, single file)
#
# Copyright (c) 1997-2003 by Secret Labs AB
# Copyright (c) 1996-2003 by Fredrik Lundh
#
# See the README file for information on usage and redistribution.
#

from __future__ import annotations

import base64
import os
import sys
import warnings
from enum import IntEnum
from io import BytesIO
from types import ModuleType
from typing import IO, Any, BinaryIO, TypedDict, cast

from . import Image, features
from ._typing import StrOrBytesPath
from ._util import DeferredError, is_path

TYPE_CHECKING = False
if TYPE_CHECKING:
    from . import ImageFile
    from ._imaging import ImagingFont
    from ._imagingft import Font


class Axis(TypedDict):
    minimum: int | None
    default: int | None
    maximum: int | None
    name: bytes | None


class Layout(IntEnum):
    BASIC = 0
    RAQM = 1


MAX_STRING_LENGTH = 1_000_000


core: ModuleType | DeferredError
try:
    from . import _imagingft as core
except ImportError as ex:
    core = DeferredError.new(ex)


def _string_length_check(text: str | bytes | bytearray) -> None:
    if MAX_STRING_LENGTH is not None and len(text) > MAX_STRING_LENGTH:
        msg = "too many characters in string"
        raise ValueError(msg)


# FIXME: add support for pilfont2 format (see FontFile.py)

# --------------------------------------------------------------------
# Font metrics format:
#       "PILfont" LF
#       fontdescriptor LF
#       (optional) key=value... LF
#       "DATA" LF
#       binary data: 256*10*2 bytes (dx, dy, dstbox, srcbox)
#
# To place a character, cut out srcbox and paste at dstbox,
# relative to the character position.  Then move the character
# position according to dx, dy.
# --------------------------------------------------------------------


class ImageFont:
    """PIL font wrapper"""

    font: ImagingFont

    def _load_pilfont(self, filename: str) -> None:
        with open(filename, "rb") as fp:
            image: ImageFile.ImageFile | None = None
            root = os.path.splitext(filename)[0]

            for ext in (".png", ".gif", ".pbm"):
                if image:
                    image.close()
                try:
                    fullname = root + ext
                    image = Image.open(fullname)
                except Exception:
                    pass
                else:
                    if image and image.mode in ("1", "L"):
                        break
            else:
                if image:
                    image.close()

                msg = f"cannot find glyph data file {root}.{{gif|pbm|png}}"
                raise OSError(msg)

            self.file = fullname

            self._load_pilfont_data(fp, image)
            image.close()

    def _load_pilfont_data(self, file: IO[bytes], image: Image.Image) -> None:
        # read PILfont header
        if file.readline() != b"PILfont\n":
            msg = "Not a PILfont file"
            raise SyntaxError(msg)
        file.readline().split(b";")
        self.info = []  # FIXME: should be a dictionary
        while True:
            s = file.readline()
            if not s or s == b"DATA\n":
                break
            self.info.append(s)

        # read PILfont metrics
        data = file.read(256 * 20)

        # check image
        if image.mode not in ("1", "L"):
            msg = "invalid font image mode"
            raise TypeError(msg)

        image.load()

        self.font = Image.core.font(image.im, data)

    def getmask(
        self, text: str | bytes, mode: str = "", *args: Any, **kwargs: Any
    ) -> Image.core.ImagingCore:
        """
        Create a bitmap for the text.

        If the font uses antialiasing, the bitmap should have mode ``L`` and use a
        maximum value of 255. Otherwise, it should have mode ``1``.

        :param text: Text to render.
        :param mode: Used by some graphics drivers to indicate what mode the
                     driver prefers; if empty, the renderer may return either
                     mode. Note that the mode is always a string, to simplify
                     C-level implementations.

                     .. versionadded:: 1.1.5

        :return: An internal PIL storage memory instance as defined by the
                 :py:mod:`PIL.Image.core` interface module.
        """
        _string_length_check(text)
        Image._decompression_bomb_check(self.font.getsize(text))
        return self.font.getmask(text, mode)

    def getbbox(
        self, text: str | bytes | bytearray, *args: Any, **kwargs: Any
    ) -> tuple[int, int, int, int]:
        """
        Returns bounding box (in pixels) of given text.

        .. versionadded:: 9.2.0

        :param text: Text to render.

        :return: ``(left, top, right, bottom)`` bounding box
        """
        _string_length_check(text)
        width, height = self.font.getsize(text)
        return 0, 0, width, height

    def getlength(
        self, text: str | bytes | bytearray, *args: Any, **kwargs: Any
    ) -> int:
        """
        Returns length (in pixels) of given text.
        This is the amount by which following text should be offset.

        .. versionadded:: 9.2.0
        """
        _string_length_check(text)
        width, height = self.font.getsize(text)
        return width


##
# Wrapper for FreeType fonts.  Application code should use the
# <b>truetype</b> factory function to create font objects.


class FreeTypeFont:
    """FreeType font wrapper (requires _imagingft service)"""

    font: Font
    font_bytes: bytes

    def __init__(
        self,
        font: StrOrBytesPath | BinaryIO,
        size: float = 10,
        index: int = 0,
        encoding: str = "",
        layout_engine: Layout | None = None,
    ) -> None:
        # FIXME: use service provider instead

        if isinstance(core, DeferredError):
            raise core.ex

        if size <= 0:
            msg = f"font size must be greater than 0, not {size}"
            raise ValueError(msg)

        self.path = font
        self.size = size
        self.index = index
        self.encoding = encoding

        try:
            from packaging.version import parse as parse_version
        except ImportError:
            pass
        else:
            if freetype_version := features.version_module("freetype2"):
                if parse_version(freetype_version) < parse_version("2.9.1"):
                    warnings.warn(
                        "Support for FreeType 2.9.0 is deprecated and will be removed "
                        "in Pillow 12 (2025-10-15). Please upgrade to FreeType 2.9.1 "
                        "or newer, preferably FreeType 2.10.4 which fixes "
                        "CVE-2020-15999.",
                        DeprecationWarning,
                    )

        if layout_engine not in (Layout.BASIC, Layout.RAQM):
            layout_engine = Layout.BASIC
            if core.HAVE_RAQM:
                layout_engine = Layout.RAQM
        elif layout_engine == Layout.RAQM and not core.HAVE_RAQM:
            warnings.warn(
                "Raqm layout was requested, but Raqm is not available. "
                "Falling back to basic layout."
            )
            layout_engine = Layout.BASIC

        self.layout_engine = layout_engine

        def load_from_bytes(f: IO[bytes]) -> None:
            self.font_bytes = f.read()
            self.font = core.getfont(
                "", size, index, encoding, self.font_bytes, layout_engine
            )

        if is_path(font):
            font = os.fspath(font)
            if sys.platform == "win32":
                font_bytes_path = font if isinstance(font, bytes) else font.encode()
                try:
                    font_bytes_path.decode("ascii")
                except UnicodeDecodeError:
                    # FreeType cannot load fonts with non-ASCII characters on Windows
                    # So load it into memory first
                    with open(font, "rb") as f:
                        load_from_bytes(f)
                    return
            self.font = core.getfont(
                font, size, index, encoding, layout_engine=layout_engine
            )
        else:
            load_from_bytes(cast(IO[bytes], font))

    def __getstate__(self) -> list[Any]:
        return [self.path, self.size, self.index, self.encoding, self.layout_engine]

    def __setstate__(self, state: list[Any]) -> None:
        path, size, index, encoding, layout_engine = state
        FreeTypeFont.__init__(self, path, size, index, encoding, layout_engine)

    def getname(self) -> tuple[str | None, str | None]:
        """
        :return: A tuple of the font family (e.g. Helvetica) and the font style
            (e.g. Bold)
        """
        return self.font.family, self.font.style

    def getmetrics(self) -> tuple[int, int]:
        """
        :return: A tuple of the font ascent (the distance from the baseline to
            the highest outline point) and descent (the distance from the
            baseline to the lowest outline point, a negative value)
        """
        return self.font.ascent, self.font.descent

    def getlength(
        self,
        text: str | bytes,
        mode: str = "",
        direction: str | None = None,
        features: list[str] | None = None,
        language: str | None = None,
    ) -> float:
        """
        Returns length (in pixels with 1/64 precision) of given text when rendered
        in font with provided direction, features, and language.

        This is the amount by which following text should be offset.
        Text bounding box may extend past the length in some fonts,
        e.g. when using italics or accents.

        The result is returned as a float; it is a whole number if using basic layout.

        Note that the sum of two lengths may not equal the length of a concatenated
        string due to kerning. If you need to adjust for kerning, include the following
        character and subtract its length.

        For example, instead of ::

          hello = font.getlength("Hello")
          world = font.getlength("World")
          hello_world = hello + world  # not adjusted for kerning
          assert hello_world == font.getlength("HelloWorld")  # may fail

        use ::

          hello = font.getlength("HelloW") - font.getlength("W")  # adjusted for kerning
          world = font.getlength("World")
          hello_world = hello + world  # adjusted for kerning
          assert hello_world == font.getlength("HelloWorld")  # True

        or disable kerning with (requires libraqm) ::

          hello = draw.textlength("Hello", font, features=["-kern"])
          world = draw.textlength("World", font, features=["-kern"])
          hello_world = hello + world  # kerning is disabled, no need to adjust
          assert hello_world == draw.textlength("HelloWorld", font, features=["-kern"])

        .. versionadded:: 8.0.0

        :param text: Text to measure.
        :param mode: Used by some graphics drivers to indicate what mode the
                     driver prefers; if empty, the renderer may return either
                     mode. Note that the mode is always a string, to simplify
                     C-level implementations.

        :param direction: Direction of the text. It can be 'rtl' (right to
                          left), 'ltr' (left to right) or 'ttb' (top to bottom).
                          Requires libraqm.

        :param features: A list of OpenType font features to be used during text
                         layout. This is usually used to turn on optional
                         font features that are not enabled by default,
                         for example 'dlig' or 'ss01', but can be also
                         used to turn off default font features for
                         example '-liga' to disable ligatures or '-kern'
                         to disable kerning.  To get all supported
                         features, see
                         https://learn.microsoft.com/en-us/typography/opentype/spec/featurelist
                         Requires libraqm.

        :param language: Language of the text. Different languages may use
                         different glyph shapes or ligatures. This parameter tells
                         the font which language the text is in, and to apply the
                         correct substitutions as appropriate, if available.
                         It should be a `BCP 47 language code
                         <https://www.w3.org/International/articles/language-tags/>`_
                         Requires libraqm.

        :return: Either width for horizontal text, or height for vertical text.
        """
        _string_length_check(text)
        return self.font.getlength(text, mode, direction, features, language) / 64

    def getbbox(
        self,
        text: str | bytes,
        mode: str = "",
        direction: str | None = None,
        features: list[str] | None = None,
        language: str | None = None,
        stroke_width: float = 0,
        anchor: str | None = None,
    ) -> tuple[float, float, float, float]:
        """
        Returns bounding box (in pixels) of given text relative to given anchor
        when rendered in font with provided direction, features, and language.

        Use :py:meth:`getlength()` to get the offset of following text with
        1/64 pixel precision. The bounding box includes extra margins for
        some fonts, e.g. italics or accents.

        .. versionadded:: 8.0.0

        :param text: Text to render.
        :param mode: Used by some graphics drivers to indicate what mode the
                     driver prefers; if empty, the renderer may return either
                     mode. Note that the mode is always a string, to simplify
                     C-level implementations.

        :param direction: Direction of the text. It can be 'rtl' (right to
                          left), 'ltr' (left to right) or 'ttb' (top to bottom).
                          Requires libraqm.

        :param features: A list of OpenType font features to be used during text
                         layout. This is usually used to turn on optional
                         font features that are not enabled by default,
                         for example 'dlig' or 'ss01', but can be also
                         used to turn off default font features for
                         example '-liga' to disable ligatures or '-kern'
                         to disable kerning.  To get all supported
                         features, see
                         https://learn.microsoft.com/en-us/typography/opentype/spec/featurelist
                         Requires libraqm.

        :param language: Language of the text. Different languages may use
                         different glyph shapes or ligatures. This parameter tells
                         the font which language the text is in, and to apply the
                         correct substitutions as appropriate, if available.
                         It should be a `BCP 47 language code
                         <https://www.w3.org/International/articles/language-tags/>`_
                         Requires libraqm.

        :param stroke_width: The width of the text stroke.

        :param anchor:  The text anchor alignment. Determines the relative location of
                        the anchor to the text. The default alignment is top left,
                        specifically ``la`` for horizontal text and ``lt`` for
                        vertical text. See :ref:`text-anchors` for details.

        :return: ``(left, top, right, bottom)`` bounding box
        """
        _string_length_check(text)
        size, offset = self.font.getsize(
            text, mode, direction, features, language, anchor
        )
        left, top = offset[0] - stroke_width, offset[1] - stroke_width
        width, height = size[0] + 2 * stroke_width, size[1] + 2 * stroke_width
        return left, top, left + width, top + height

    def getmask(
        self,
        text: str | bytes,
        mode: str = "",
        direction: str | None = None,
        features: list[str] | None = None,
        language: str | None = None,
        stroke_width: float = 0,
        anchor: str | None = None,
        ink: int = 0,
        start: tuple[float, float] | None = None,
    ) -> Image.core.ImagingCore:
        """
        Create a bitmap for the text.

        If the font uses antialiasing, the bitmap should have mode ``L`` and use a
        maximum value of 255. If the font has embedded color data, the bitmap
        should have mode ``RGBA``. Otherwise, it should have mode ``1``.

        :param text: Text to render.
        :param mode: Used by some graphics drivers to indicate what mode the
                     driver prefers; if empty, the renderer may return either
                     mode. Note that the mode is always a string, to simplify
                     C-level implementations.

                     .. versionadded:: 1.1.5

        :param direction: Direction of the text. It can be 'rtl' (right to
                          left), 'ltr' (left to right) or 'ttb' (top to bottom).
                          Requires libraqm.

                          .. versionadded:: 4.2.0

        :param features: A list of OpenType font features to be used during text
                         layout. This is usually used to turn on optional
                         font features that are not enabled by default,
                         for example 'dlig' or 'ss01', but can be also
                         used to turn off default font features for
                         example '-liga' to disable ligatures or '-kern'
                         to disable kerning.  To get all supported
                         features, see
                         https://learn.microsoft.com/en-us/typography/opentype/spec/featurelist
                         Requires libraqm.

                         .. versionadded:: 4.2.0

        :param language: Language of the text. Different languages may use
                         different glyph shapes or ligatures. This parameter tells
                         the font which language the text is in, and to apply the
                         correct substitutions as appropriate, if available.
                         It should be a `BCP 47 language code
                         <https://www.w3.org/International/articles/language-tags/>`_
                         Requires libraqm.

                         .. versionadded:: 6.0.0

        :param stroke_width: The width of the text stroke.

                         .. versionadded:: 6.2.0

        :param anchor:  The text anchor alignment. Determines the relative location of
                        the anchor to the text. The default alignment is top left,
                        specifically ``la`` for horizontal text and ``lt`` for
                        vertical text. See :ref:`text-anchors` for details.

                         .. versionadded:: 8.0.0

        :param ink: Foreground ink for rendering in RGBA mode.

                         .. versionadded:: 8.0.0

        :param start: Tuple of horizontal and vertical offset, as text may render
                      differently when starting at fractional coordinates.

                         .. versionadded:: 9.4.0

        :return: An internal PIL storage memory instance as defined by the
                 :py:mod:`PIL.Image.core` interface module.
        """
        return self.getmask2(
            text,
            mode,
            direction=direction,
            features=features,
            language=language,
            stroke_width=stroke_width,
            anchor=anchor,
            ink=ink,
            start=start,
        )[0]

    def getmask2(
        self,
        text: str | bytes,
        mode: str = "",
        direction: str | None = None,
        features: list[str] | None = None,
        language: str | None = None,
        stroke_width: float = 0,
        anchor: str | None = None,
        ink: int = 0,
        start: tuple[float, float] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> tuple[Image.core.ImagingCore, tuple[int, int]]:
        """
        Create a bitmap for the text.

        If the font uses antialiasing, the bitmap should have mode ``L`` and use a
        maximum value of 255. If the font has embedded color data, the bitmap
        should have mode ``RGBA``. Otherwise, it should have mode ``1``.

        :param text: Text to render.
        :param mode: Used by some graphics drivers to indicate what mode the
                     driver prefers; if empty, the renderer may return either
                     mode. Note that the mode is always a string, to simplify
                     C-level implementations.

                     .. versionadded:: 1.1.5

        :param direction: Direction of the text. It can be 'rtl' (right to
                          left), 'ltr' (left to right) or 'ttb' (top to bottom).
                          Requires libraqm.

                          .. versionadded:: 4.2.0

        :param features: A list of OpenType font features to be used during text
                         layout. This is usually used to turn on optional
                         font features that are not enabled by default,
                         for example 'dlig' or 'ss01', but can be also
                         used to turn off default font features for
                         example '-liga' to disable ligatures or '-kern'
                         to disable kerning.  To get all supported
                         features, see
                         https://learn.microsoft.com/en-us/typography/opentype/spec/featurelist
                         Requires libraqm.

                         .. versionadded:: 4.2.0

        :param language: Language of the text. Different languages may use
                         different glyph shapes or ligatures. This parameter tells
                         the font which language the text is in, and to apply the
                         correct substitutions as appropriate, if available.
                         It should be a `BCP 47 language code
                         <https://www.w3.org/International/articles/language-tags/>`_
                         Requires libraqm.

                         .. versionadded:: 6.0.0

        :param stroke_width: The width of the text stroke.

                         .. versionadded:: 6.2.0

        :param anchor:  The text anchor alignment. Determines the relative location of
                        the anchor to the text. The default alignment is top left,
                        specifically ``la`` for horizontal text and ``lt`` for
                        vertical text. See :ref:`text-anchors` for details.

                         .. versionadded:: 8.0.0

        :param ink: Foreground ink for rendering in RGBA mode.

                         .. versionadded:: 8.0.0

        :param start: Tuple of horizontal and vertical offset, as text may render
                      differently when starting at fractional coordinates.

                         .. versionadded:: 9.4.0

        :return: A tuple of an internal PIL storage memory instance as defined by the
                 :py:mod:`PIL.Image.core` interface module, and the text offset, the
                 gap between the starting coordinate and the first marking
        """
        _string_length_check(text)
        if start is None:
            start = (0, 0)

        def fill(width: int, height: int) -> Image.core.ImagingCore:
            size = (width, height)
            Image._decompression_bomb_check(size)
            return Image.core.fill("RGBA" if mode == "RGBA" else "L", size)

        return self.font.render(
            text,
            fill,
            mode,
            direction,
            features,
            language,
            stroke_width,
            kwargs.get("stroke_filled", False),
            anchor,
            ink,
            start,
        )

    def font_variant(
        self,
        font: StrOrBytesPath | BinaryIO | None = None,
        size: float | None = None,
        index: int | None = None,
        encoding: str | None = None,
        layout_engine: Layout | None = None,
    ) -> FreeTypeFont:
        """
        Create a copy of this FreeTypeFont object,
        using any specified arguments to override the settings.

        Parameters are identical to the parameters used to initialize this
        object.

        :return: A FreeTypeFont object.
        """
        if font is None:
            try:
                font = BytesIO(self.font_bytes)
            except AttributeError:
                font = self.path
        return FreeTypeFont(
            font=font,
            size=self.size if size is None else size,
            index=self.index if index is None else index,
            encoding=self.encoding if encoding is None else encoding,
            layout_engine=layout_engine or self.layout_engine,
        )

    def get_variation_names(self) -> list[bytes]:
        """
        :returns: A list of the named styles in a variation font.
        :exception OSError: If the font is not a variation font.
        """
        try:
            names = self.font.getvarnames()
        except AttributeError as e:
            msg = "FreeType 2.9.1 or greater is required"
            raise NotImplementedError(msg) from e
        return [name.replace(b"\x00", b"") for name in names]

    def set_variation_by_name(self, name: str | bytes) -> None:
        """
        :param name: The name of the style.
        :exception OSError: If the font is not a variation font.
        """
        names = self.get_variation_names()
        if not isinstance(name, bytes):
            name = name.encode()
        index = names.index(name) + 1

        if index == getattr(self, "_last_variation_index", None):
            # When the same name is set twice in a row,
            # there is an 'unknown freetype error'
            # https://savannah.nongnu.org/bugs/?56186
            return
        self._last_variation_index = index

        self.font.setvarname(index)

    def get_variation_axes(self) -> list[Axis]:
        """
        :returns: A list of the axes in a variation font.
        :exception OSError: If the font is not a variation font.
        """
        try:
            axes = self.font.getvaraxes()
        except AttributeError as e:
            msg = "FreeType 2.9.1 or greater is required"
            raise NotImplementedError(msg) from e
        for axis in axes:
            if axis["name"]:
                axis["name"] = axis["name"].replace(b"\x00", b"")
        return axes

    def set_variation_by_axes(self, axes: list[float]) -> None:
        """
        :param axes: A list of values for each axis.
        :exception OSError: If the font is not a variation font.
        """
        try:
            self.font.setvaraxes(axes)
        except AttributeError as e:
            msg = "FreeType 2.9.1 or greater is required"
            raise NotImplementedError(msg) from e


class TransposedFont:
    """Wrapper for writing rotated or mirrored text"""

    def __init__(
        self, font: ImageFont | FreeTypeFont, orientation: Image.Transpose | None = None
    ):
        """
        Wrapper that creates a transposed font from any existing font
        object.

        :param font: A font object.
        :param orientation: An optional orientation.  If given, this should
            be one of Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.FLIP_TOP_BOTTOM,
            Image.Transpose.ROTATE_90, Image.Transpose.ROTATE_180, or
            Image.Transpose.ROTATE_270.
        """
        self.font = font
        self.orientation = orientation  # any 'transpose' argument, or None

    def getmask(
        self, text: str | bytes, mode: str = "", *args: Any, **kwargs: Any
    ) -> Image.core.ImagingCore:
        im = self.font.getmask(text, mode, *args, **kwargs)
        if self.orientation is not None:
            return im.transpose(self.orientation)
        return im

    def getbbox(
        self, text: str | bytes, *args: Any, **kwargs: Any
    ) -> tuple[int, int, float, float]:
        # TransposedFont doesn't support getmask2, move top-left point to (0, 0)
        # this has no effect on ImageFont and simulates anchor="lt" for FreeTypeFont
        left, top, right, bottom = self.font.getbbox(text, *args, **kwargs)
        width = right - left
        height = bottom - top
        if self.orientation in (Image.Transpose.ROTATE_90, Image.Transpose.ROTATE_270):
            return 0, 0, height, width
        return 0, 0, width, height

    def getlength(self, text: str | bytes, *args: Any, **kwargs: Any) -> float:
        if self.orientation in (Image.Transpose.ROTATE_90, Image.Transpose.ROTATE_270):
            msg = "text length is undefined for text rotated by 90 or 270 degrees"
            raise ValueError(msg)
        return self.font.getlength(text, *args, **kwargs)


def load(filename: str) -> ImageFont:
    """
    Load a font file. This function loads a font object from the given
    bitmap font file, and returns the corresponding font object. For loading TrueType
    or OpenType fonts instead, see :py:func:`~PIL.ImageFont.truetype`.

    :param filename: Name of font file.
    :return: A font object.
    :exception OSError: If the file could not be read.
    """
    f = ImageFont()
    f._load_pilfont(filename)
    return f


def truetype(
    font: StrOrBytesPath | BinaryIO,
    size: float = 10,
    index: int = 0,
    encoding: str = "",
    layout_engine: Layout | None = None,
) -> FreeTypeFont:
    """
    Load a TrueType or OpenType font from a file or file-like object,
    and create a font object. This function loads a font object from the given
    file or file-like object, and creates a font object for a font of the given
    size. For loading bitmap fonts instead, see :py:func:`~PIL.ImageFont.load`
    and :py:func:`~PIL.ImageFont.load_path`.

    Pillow uses FreeType to open font files. On Windows, be aware that FreeType
    will keep the file open as long as the FreeTypeFont object exists. Windows
    limits the number of files that can be open in C at once to 512, so if many
    fonts are opened simultaneously and that limit is approached, an
    ``OSError`` may be thrown, reporting that FreeType "cannot open resource".
    A workaround would be to copy the file(s) into memory, and open that instead.

    This function requires the _imagingft service.

    :param font: A filename or file-like object containing a TrueType font.
                 If the file is not found in this filename, the loader may also
                 search in other directories, such as:

                 * The :file:`fonts/` directory on Windows,
                 * :file:`/Library/Fonts/`, :file:`/System/Library/Fonts/`
                   and :file:`~/Library/Fonts/` on macOS.
                 * :file:`~/.local/share/fonts`, :file:`/usr/local/share/fonts`,
                   and :file:`/usr/share/fonts` on Linux; or those specified by
                   the ``XDG_DATA_HOME`` and ``XDG_DATA_DIRS`` environment variables
                   for user-installed and system-wide fonts, respectively.

    :param size: The requested size, in pixels.
    :param index: Which font face to load (default is first available face).
    :param encoding: Which font encoding to use (default is Unicode). Possible
                     encodings include (see the FreeType documentation for more
                     information):

                     * "unic" (Unicode)
                     * "symb" (Microsoft Symbol)
                     * "ADOB" (Adobe Standard)
                     * "ADBE" (Adobe Expert)
                     * "ADBC" (Adobe Custom)
                     * "armn" (Apple Roman)
                     * "sjis" (Shift JIS)
                     * "gb  " (PRC)
                     * "big5"
                     * "wans" (Extended Wansung)
                     * "joha" (Johab)
                     * "lat1" (Latin-1)

                     This specifies the character set to use. It does not alter the
                     encoding of any text provided in subsequent operations.
    :param layout_engine: Which layout engine to use, if available:
                     :attr:`.ImageFont.Layout.BASIC` or :attr:`.ImageFont.Layout.RAQM`.
                     If it is available, Raqm layout will be used by default.
                     Otherwise, basic layout will be used.

                     Raqm layout is recommended for all non-English text. If Raqm layout
                     is not required, basic layout will have better performance.

                     You can check support for Raqm layout using
                     :py:func:`PIL.features.check_feature` with ``feature="raqm"``.

                     .. versionadded:: 4.2.0
    :return: A font object.
    :exception OSError: If the file could not be read.
    :exception ValueError: If the font size is not greater than zero.
    """

    def freetype(font: StrOrBytesPath | BinaryIO) -> FreeTypeFont:
        return FreeTypeFont(font, size, index, encoding, layout_engine)

    try:
        return freetype(font)
    except OSError:
        if not is_path(font):
            raise
        ttf_filename = os.path.basename(font)

        dirs = []
        if sys.platform == "win32":
            # check the windows font repository
            # NOTE: must use uppercase WINDIR, to work around bugs in
            # 1.5.2's os.environ.get()
            windir = os.environ.get("WINDIR")
            if windir:
                dirs.append(os.path.join(windir, "fonts"))
        elif sys.platform in ("linux", "linux2"):
            data_home = os.environ.get("XDG_DATA_HOME")
            if not data_home:
                # The freedesktop spec defines the following default directory for
                # when XDG_DATA_HOME is unset or empty. This user-level directory
                # takes precedence over system-level directories.
                data_home = os.path.expanduser("~/.local/share")
            xdg_dirs = [data_home]

            data_dirs = os.environ.get("XDG_DATA_DIRS")
            if not data_dirs:
                # Similarly, defaults are defined for the system-level directories
                data_dirs = "/usr/local/share:/usr/share"
            xdg_dirs += data_dirs.split(":")

            dirs += [os.path.join(xdg_dir, "fonts") for xdg_dir in xdg_dirs]
        elif sys.platform == "darwin":
            dirs += [
                "/Library/Fonts",
                "/System/Library/Fonts",
                os.path.expanduser("~/Library/Fonts"),
            ]

        ext = os.path.splitext(ttf_filename)[1]
        first_font_with_a_different_extension = None
        for directory in dirs:
            for walkroot, walkdir, walkfilenames in os.walk(directory):
                for walkfilename in walkfilenames:
                    if ext and walkfilename == ttf_filename:
                        return freetype(os.path.join(walkroot, walkfilename))
                    elif not ext and os.path.splitext(walkfilename)[0] == ttf_filename:
                        fontpath = os.path.join(walkroot, walkfilename)
                        if os.path.splitext(fontpath)[1] == ".ttf":
                            return freetype(fontpath)
                        if not ext and first_font_with_a_different_extension is None:
                            first_font_with_a_different_extension = fontpath
        if first_font_with_a_different_extension:
            return freetype(first_font_with_a_different_extension)
        raise


def load_path(filename: str | bytes) -> ImageFont:
    """
    Load font file. Same as :py:func:`~PIL.ImageFont.load`, but searches for a
    bitmap font along the Python path.

    :param filename: Name of font file.
    :return: A font object.
    :exception OSError: If the file could not be read.
    """
    if not isinstance(filename, str):
        filename = filename.decode("utf-8")
    for directory in sys.path:
        try:
            return load(os.path.join(directory, filename))
        except OSError:
            pass
    msg = f'cannot find font file "{filename}" in sys.path'
    if os.path.exists(filename):
        msg += f', did you mean ImageFont.load("{filename}") instead?'

    raise OSError(msg)


def load_default_imagefont() -> ImageFont:
    f = ImageFont()
    f._load_pilfont_data(
        # courB08
        BytesIO(
            base64.b64decode(
                b"""
UElMZm9udAo7Ozs7OzsxMDsKREFUQQoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAYAAAAA//8AAQAAAAAAAAABAAEA
BgAAAAH/+gADAAAAAQAAAAMABgAGAAAAAf/6AAT//QADAAAABgADAAYAAAAA//kABQABAAYAAAAL
AAgABgAAAAD/+AAFAAEACwAAABAACQAGAAAAAP/5AAUAAAAQAAAAFQAHAAYAAP////oABQAAABUA
AAAbAAYABgAAAAH/+QAE//wAGwAAAB4AAwAGAAAAAf/5AAQAAQAeAAAAIQAIAAYAAAAB//kABAAB
ACEAAAAkAAgABgAAAAD/+QAE//0AJAAAACgABAAGAAAAAP/6AAX//wAoAAAALQAFAAYAAAAB//8A
BAACAC0AAAAwAAMABgAAAAD//AAF//0AMAAAADUAAQAGAAAAAf//AAMAAAA1AAAANwABAAYAAAAB
//kABQABADcAAAA7AAgABgAAAAD/+QAFAAAAOwAAAEAABwAGAAAAAP/5AAYAAABAAAAARgAHAAYA
AAAA//kABQAAAEYAAABLAAcABgAAAAD/+QAFAAAASwAAAFAABwAGAAAAAP/5AAYAAABQAAAAVgAH
AAYAAAAA//kABQAAAFYAAABbAAcABgAAAAD/+QAFAAAAWwAAAGAABwAGAAAAAP/5AAUAAABgAAAA
ZQAHAAYAAAAA//kABQAAAGUAAABqAAcABgAAAAD/+QAFAAAAagAAAG8ABwAGAAAAAf/8AAMAAABv
AAAAcQAEAAYAAAAA//wAAwACAHEAAAB0AAYABgAAAAD/+gAE//8AdAAAAHgABQAGAAAAAP/7AAT/
/gB4AAAAfAADAAYAAAAB//oABf//AHwAAACAAAUABgAAAAD/+gAFAAAAgAAAAIUABgAGAAAAAP/5
AAYAAQCFAAAAiwAIAAYAAP////oABgAAAIsAAACSAAYABgAA////+gAFAAAAkgAAAJgABgAGAAAA
AP/6AAUAAACYAAAAnQAGAAYAAP////oABQAAAJ0AAACjAAYABgAA////+gAFAAAAowAAAKkABgAG
AAD////6AAUAAACpAAAArwAGAAYAAAAA//oABQAAAK8AAAC0AAYABgAA////+gAGAAAAtAAAALsA
BgAGAAAAAP/6AAQAAAC7AAAAvwAGAAYAAP////oABQAAAL8AAADFAAYABgAA////+gAGAAAAxQAA
AMwABgAGAAD////6AAUAAADMAAAA0gAGAAYAAP////oABQAAANIAAADYAAYABgAA////+gAGAAAA
2AAAAN8ABgAGAAAAAP/6AAUAAADfAAAA5AAGAAYAAP////oABQAAAOQAAADqAAYABgAAAAD/+gAF
AAEA6gAAAO8ABwAGAAD////6AAYAAADvAAAA9gAGAAYAAAAA//oABQAAAPYAAAD7AAYABgAA////
+gAFAAAA+wAAAQEABgAGAAD////6AAYAAAEBAAABCAAGAAYAAP////oABgAAAQgAAAEPAAYABgAA
////+gAGAAABDwAAARYABgAGAAAAAP/6AAYAAAEWAAABHAAGAAYAAP////oABgAAARwAAAEjAAYA
BgAAAAD/+gAFAAABIwAAASgABgAGAAAAAf/5AAQAAQEoAAABKwAIAAYAAAAA//kABAABASsAAAEv
AAgABgAAAAH/+QAEAAEBLwAAATIACAAGAAAAAP/5AAX//AEyAAABNwADAAYAAAAAAAEABgACATcA
AAE9AAEABgAAAAH/+QAE//wBPQAAAUAAAwAGAAAAAP/7AAYAAAFAAAABRgAFAAYAAP////kABQAA
AUYAAAFMAAcABgAAAAD/+wAFAAABTAAAAVEABQAGAAAAAP/5AAYAAAFRAAABVwAHAAYAAAAA//sA
BQAAAVcAAAFcAAUABgAAAAD/+QAFAAABXAAAAWEABwAGAAAAAP/7AAYAAgFhAAABZwAHAAYAAP//
//kABQAAAWcAAAFtAAcABgAAAAD/+QAGAAABbQAAAXMABwAGAAAAAP/5AAQAAgFzAAABdwAJAAYA
AP////kABgAAAXcAAAF+AAcABgAAAAD/+QAGAAABfgAAAYQABwAGAAD////7AAUAAAGEAAABigAF
AAYAAP////sABQAAAYoAAAGQAAUABgAAAAD/+wAFAAABkAAAAZUABQAGAAD////7AAUAAgGVAAAB
mwAHAAYAAAAA//sABgACAZsAAAGhAAcABgAAAAD/+wAGAAABoQAAAacABQAGAAAAAP/7AAYAAAGn
AAABrQAFAAYAAAAA//kABgAAAa0AAAGzAAcABgAA////+wAGAAABswAAAboABQAGAAD////7AAUA
AAG6AAABwAAFAAYAAP////sABgAAAcAAAAHHAAUABgAAAAD/+wAGAAABxwAAAc0ABQAGAAD////7
AAYAAgHNAAAB1AAHAAYAAAAA//sABQAAAdQAAAHZAAUABgAAAAH/+QAFAAEB2QAAAd0ACAAGAAAA
Av/6AAMAAQHdAAAB3gAHAAYAAAAA//kABAABAd4AAAHiAAgABgAAAAD/+wAF//0B4gAAAecAAgAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAYAAAAB
//sAAwACAecAAAHpAAcABgAAAAD/+QAFAAEB6QAAAe4ACAAGAAAAAP/5AAYAAAHuAAAB9AAHAAYA
AAAA//oABf//AfQAAAH5AAUABgAAAAD/+QAGAAAB+QAAAf8ABwAGAAAAAv/5AAMAAgH/AAACAAAJ
AAYAAAAA//kABQABAgAAAAIFAAgABgAAAAH/+gAE//sCBQAAAggAAQAGAAAAAP/5AAYAAAIIAAAC
DgAHAAYAAAAB//kABf/+Ag4AAAISAAUABgAA////+wAGAAACEgAAAhkABQAGAAAAAP/7AAX//gIZ
AAACHgADAAYAAAAA//wABf/9Ah4AAAIjAAEABgAAAAD/+QAHAAACIwAAAioABwAGAAAAAP/6AAT/
+wIqAAACLgABAAYAAAAA//kABP/8Ai4AAAIyAAMABgAAAAD/+gAFAAACMgAAAjcABgAGAAAAAf/5
AAT//QI3AAACOgAEAAYAAAAB//kABP/9AjoAAAI9AAQABgAAAAL/+QAE//sCPQAAAj8AAgAGAAD/
///7AAYAAgI/AAACRgAHAAYAAAAA//kABgABAkYAAAJMAAgABgAAAAH//AAD//0CTAAAAk4AAQAG
AAAAAf//AAQAAgJOAAACUQADAAYAAAAB//kABP/9AlEAAAJUAAQABgAAAAH/+QAF//4CVAAAAlgA
BQAGAAD////7AAYAAAJYAAACXwAFAAYAAP////kABgAAAl8AAAJmAAcABgAA////+QAGAAACZgAA
Am0ABwAGAAD////5AAYAAAJtAAACdAAHAAYAAAAA//sABQACAnQAAAJ5AAcABgAA////9wAGAAAC
eQAAAoAACQAGAAD////3AAYAAAKAAAAChwAJAAYAAP////cABgAAAocAAAKOAAkABgAA////9wAG
AAACjgAAApUACQAGAAD////4AAYAAAKVAAACnAAIAAYAAP////cABgAAApwAAAKjAAkABgAA////
+gAGAAACowAAAqoABgAGAAAAAP/6AAUAAgKqAAACrwAIAAYAAP////cABQAAAq8AAAK1AAkABgAA
////9wAFAAACtQAAArsACQAGAAD////3AAUAAAK7AAACwQAJAAYAAP////gABQAAAsEAAALHAAgA
BgAAAAD/9wAEAAACxwAAAssACQAGAAAAAP/3AAQAAALLAAACzwAJAAYAAAAA//cABAAAAs8AAALT
AAkABgAAAAD/+AAEAAAC0wAAAtcACAAGAAD////6AAUAAALXAAAC3QAGAAYAAP////cABgAAAt0A
AALkAAkABgAAAAD/9wAFAAAC5AAAAukACQAGAAAAAP/3AAUAAALpAAAC7gAJAAYAAAAA//cABQAA
Au4AAALzAAkABgAAAAD/9wAFAAAC8wAAAvgACQAGAAAAAP/4AAUAAAL4AAAC/QAIAAYAAAAA//oA
Bf//Av0AAAMCAAUABgAA////+gAGAAADAgAAAwkABgAGAAD////3AAYAAAMJAAADEAAJAAYAAP//
//cABgAAAxAAAAMXAAkABgAA////9wAGAAADFwAAAx4ACQAGAAD////4AAYAAAAAAAoABwASAAYA
AP////cABgAAAAcACgAOABMABgAA////+gAFAAAADgAKABQAEAAGAAD////6AAYAAAAUAAoAGwAQ
AAYAAAAA//gABgAAABsACgAhABIABgAAAAD/+AAGAAAAIQAKACcAEgAGAAAAAP/4AAYAAAAnAAoA
LQASAAYAAAAA//gABgAAAC0ACgAzABIABgAAAAD/+QAGAAAAMwAKADkAEQAGAAAAAP/3AAYAAAA5
AAoAPwATAAYAAP////sABQAAAD8ACgBFAA8ABgAAAAD/+wAFAAIARQAKAEoAEQAGAAAAAP/4AAUA
AABKAAoATwASAAYAAAAA//gABQAAAE8ACgBUABIABgAAAAD/+AAFAAAAVAAKAFkAEgAGAAAAAP/5
AAUAAABZAAoAXgARAAYAAAAA//gABgAAAF4ACgBkABIABgAAAAD/+AAGAAAAZAAKAGoAEgAGAAAA
AP/4AAYAAABqAAoAcAASAAYAAAAA//kABgAAAHAACgB2ABEABgAAAAD/+AAFAAAAdgAKAHsAEgAG
AAD////4AAYAAAB7AAoAggASAAYAAAAA//gABQAAAIIACgCHABIABgAAAAD/+AAFAAAAhwAKAIwA
EgAGAAAAAP/4AAUAAACMAAoAkQASAAYAAAAA//gABQAAAJEACgCWABIABgAAAAD/+QAFAAAAlgAK
AJsAEQAGAAAAAP/6AAX//wCbAAoAoAAPAAYAAAAA//oABQABAKAACgClABEABgAA////+AAGAAAA
pQAKAKwAEgAGAAD////4AAYAAACsAAoAswASAAYAAP////gABgAAALMACgC6ABIABgAA////+QAG
AAAAugAKAMEAEQAGAAD////4AAYAAgDBAAoAyAAUAAYAAP////kABQACAMgACgDOABMABgAA////
+QAGAAIAzgAKANUAEw==
"""
            )
        ),
        Image.open(
            BytesIO(
                base64.b64decode(
                    b"""
iVBORw0KGgoAAAANSUhEUgAAAx4AAAAUAQAAAAArMtZoAAAEwElEQVR4nABlAJr/AHVE4czCI/4u
Mc4b7vuds/xzjz5/3/7u/n9vMe7vnfH/9++vPn/xyf5zhxzjt8GHw8+2d83u8x27199/nxuQ6Od9
M43/5z2I+9n9ZtmDBwMQECDRQw/eQIQohJXxpBCNVE6QCCAAAAD//wBlAJr/AgALyj1t/wINwq0g
LeNZUworuN1cjTPIzrTX6ofHWeo3v336qPzfEwRmBnHTtf95/fglZK5N0PDgfRTslpGBvz7LFc4F
IUXBWQGjQ5MGCx34EDFPwXiY4YbYxavpnhHFrk14CDAAAAD//wBlAJr/AgKqRooH2gAgPeggvUAA
Bu2WfgPoAwzRAABAAAAAAACQgLz/3Uv4Gv+gX7BJgDeeGP6AAAD1NMDzKHD7ANWr3loYbxsAD791
NAADfcoIDyP44K/jv4Y63/Z+t98Ovt+ub4T48LAAAAD//wBlAJr/AuplMlADJAAAAGuAphWpqhMx
in0A/fRvAYBABPgBwBUgABBQ/sYAyv9g0bCHgOLoGAAAAAAAREAAwI7nr0ArYpow7aX8//9LaP/9
SjdavWA8ePHeBIKB//81/83ndznOaXx379wAAAD//wBlAJr/AqDxW+D3AABAAbUh/QMnbQag/gAY
AYDAAACgtgD/gOqAAAB5IA/8AAAk+n9w0AAA8AAAmFRJuPo27ciC0cD5oeW4E7KA/wD3ECMAn2tt
y8PgwH8AfAxFzC0JzeAMtratAsC/ffwAAAD//wBlAJr/BGKAyCAA4AAAAvgeYTAwHd1kmQF5chkG
ABoMIHcL5xVpTfQbUqzlAAAErwAQBgAAEOClA5D9il08AEh/tUzdCBsXkbgACED+woQg8Si9VeqY
lODCn7lmF6NhnAEYgAAA/NMIAAAAAAD//2JgjLZgVGBg5Pv/Tvpc8hwGBjYGJADjHDrAwPzAjv/H
/Wf3PzCwtzcwHmBgYGcwbZz8wHaCAQMDOwMDQ8MCBgYOC3W7mp+f0w+wHOYxO3OG+e376hsMZjk3
AAAAAP//YmCMY2A4wMAIN5e5gQETPD6AZisDAwMDgzSDAAPjByiHcQMDAwMDg1nOze1lByRu5/47
c4859311AYNZzg0AAAAA//9iYGDBYihOIIMuwIjGL39/fwffA8b//xv/P2BPtzzHwCBjUQAAAAD/
/yLFBrIBAAAA//9i1HhcwdhizX7u8NZNzyLbvT97bfrMf/QHI8evOwcSqGUJAAAA//9iYBB81iSw
pEE170Qrg5MIYydHqwdDQRMrAwcVrQAAAAD//2J4x7j9AAMDn8Q/BgYLBoaiAwwMjPdvMDBYM1Tv
oJodAAAAAP//Yqo/83+dxePWlxl3npsel9lvLfPcqlE9725C+acfVLMEAAAA//9i+s9gwCoaaGMR
evta/58PTEWzr21hufPjA8N+qlnBwAAAAAD//2JiWLci5v1+HmFXDqcnULE/MxgYGBj+f6CaJQAA
AAD//2Ji2FrkY3iYpYC5qDeGgeEMAwPDvwQBBoYvcTwOVLMEAAAA//9isDBgkP///0EOg9z35v//
Gc/eeW7BwPj5+QGZhANUswMAAAD//2JgqGBgYGBgqEMXlvhMPUsAAAAA//8iYDd1AAAAAP//AwDR
w7IkEbzhVQAAAABJRU5ErkJggg==
"""
                )
            )
        ),
    )
    return f


def load_default(size: float | None = None) -> FreeTypeFont | ImageFont:
    """If FreeType support is available, load a version of Aileron Regular,
    https://dotcolon.net/fonts/aileron, with a more limited character set.

    Otherwise, load a "better than nothing" font.

    .. versionadded:: 1.1.4

    :param size: The font size of Aileron Regular.

        .. versionadded:: 10.1.0

    :return: A font object.
    """
    if isinstance(core, ModuleType) or size is not None:
        return truetype(
            BytesIO(
                base64.b64decode(
                    b"""
AAEAAAAPAIAAAwBwRkZUTYwDlUAAADFoAAAAHEdERUYAqADnAAAo8AAAACRHUE9ThhmITwAAKfgAA
AduR1NVQnHxefoAACkUAAAA4k9TLzJovoHLAAABeAAAAGBjbWFw5lFQMQAAA6gAAAGqZ2FzcP//AA
MAACjoAAAACGdseWYmRXoPAAAGQAAAHfhoZWFkE18ayQAAAPwAAAA2aGhlYQboArEAAAE0AAAAJGh
tdHjjERZ8AAAB2AAAAdBsb2NhuOexrgAABVQAAADqbWF4cAC7AEYAAAFYAAAAIG5hbWUr+h5lAAAk
OAAAA6Jwb3N0D3oPTQAAJ9wAAAEKAAEAAAABGhxJDqIhXw889QALA+gAAAAA0Bqf2QAAAADhCh2h/
2r/LgOxAyAAAAAIAAIAAAAAAAAAAQAAA8r/GgAAA7j/av9qA7EAAQAAAAAAAAAAAAAAAAAAAHQAAQ
AAAHQAQwAFAAAAAAACAAAAAQABAAAAQAAAAAAAAAADAfoBkAAFAAgCigJYAAAASwKKAlgAAAFeADI
BPgAAAAAFAAAAAAAAAAAAAAcAAAAAAAAAAAAAAABVS1dOAEAAIPsCAwL/GgDIA8oA5iAAAJMAAAAA
AhICsgAAACAAAwH0AAAAAAAAAU0AAADYAAAA8gA5AVMAVgJEAEYCRAA1AuQAKQKOAEAAsAArATsAZ
AE7AB4CMABVAkQAUADc/+EBEgAgANwAJQEv//sCRAApAkQAggJEADwCRAAtAkQAIQJEADkCRAArAk
QAMgJEACwCRAAxANwAJQDc/+ECRABnAkQAUAJEAEQB8wAjA1QANgJ/AB0CcwBkArsALwLFAGQCSwB
kAjcAZALGAC8C2gBkAQgAZAIgADcCYQBkAj8AZANiAGQCzgBkAuEALwJWAGQC3QAvAmsAZAJJADQC
ZAAiAqoAXgJuACADuAAaAnEAGQJFABMCTwAuATMAYgEv//sBJwAiAkQAUAH0ADIBLAApAhMAJAJjA
EoCEQAeAmcAHgIlAB4BIgAVAmcAHgJRAEoA7gA+AOn/8wIKAEoA9wBGA1cASgJRAEoCSgAeAmMASg
JnAB4BSgBKAcsAGAE5ABQCUABCAgIAAQMRAAEB4v/6AgEAAQHOABQBLwBAAPoAYAEvACECRABNA0Y
AJAItAHgBKgAcAkQAUAEsAHQAygAgAi0AOQD3ADYA9wAWAaEANgGhABYCbAAlAYMAeAGDADkA6/9q
AhsAFAIKABUB/QAVAAAAAwAAAAMAAAAcAAEAAAAAAKQAAwABAAAAHAAEAIgAAAAeABAAAwAOAH4Aq
QCrALEAtAC3ALsgGSAdICYgOiBEISL7Av//AAAAIACpAKsAsAC0ALcAuyAYIBwgJiA5IEQhIvsB//
//4/+5/7j/tP+y/7D/reBR4E/gR+A14CzfTwVxAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAEGAAABAAAAAAAAAAECAAAAAgAAAAAAAAAAAAAAAAAAAAEAAAMEBQYHCAkKCwwNDg8QERIT
FBUWFxgZGhscHR4fICEiIyQlJicoKSorLC0uLzAxMjM0NTY3ODk6Ozw9Pj9AQUJDREVGR0hJSktMT
U5PUFFSU1RVVldYWVpbXF1eX2BhAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGQAAA
AAAAAAYnFmAAAAAABlAAAAAAAAAAAAAAAAAAAAAAAAAAAAY2htAAAAAAAAAABrbGlqAAAAAHAAbm9
ycwBnAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAmACYAJgAmAD4AUgCCAMoBCgFO
AVwBcgGIAaYBvAHKAdYB6AH2AgwCIAJKAogCpgLWAw4DIgNkA5wDugPUA+gD/AQQBEYEogS8BPoFJ
gVSBWoFgAWwBcoF1gX6BhQGJAZMBmgGiga0BuIHGgdUB2YHkAeiB8AH3AfyCAoIHAgqCDoITghcCG
oIogjSCPoJKglYCXwJwgnqCgIKKApACl4Klgq8CtwLDAs8C1YLjAuyC9oL7gwMDCYMSAxgDKAMrAz
qDQoNTA1mDYQNoA2uDcAN2g3oDfYODA4iDkoOXA5sDnoOnA7EDvwAAAAFAAAAAAH0ArwAAwAGAAkA
DAAPAAAxESERAxMhExcRASELARETAfT6qv6syKr+jgFUqsiqArz9RAGLAP/+1P8B/v3VAP8BLP4CA
P8AAgA5//IAuQKyAAMACwAANyMDMwIyFhQGIiY0oE4MZk84JCQ4JLQB/v3AJDgkJDgAAgBWAeUBPA
LfAAMABwAAEyMnMxcjJzOmRgpagkYKWgHl+vr6AAAAAAIARgAAAf4CsgAbAB8AAAEHMxUjByM3Iwc
jNyM1MzcjNTM3MwczNzMHMxUrAQczAZgdZXEvOi9bLzovWmYdZXEvOi9bLzovWp9bHlsBn4w429vb
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
EQQ/BCQvEjQCFQZWFSEWQv40AcxCDiUblhP9uSEAAAAAAAAWAQ4AAQAAAAAAAAATACgAAQAAAAAAA
QAHAEwAAQAAAAAAAgAHAGQAAQAAAAAAAwAaAKIAAQAAAAAABAAHAM0AAQAAAAAABQA8AU8AAQAAAA
AABgAPAawAAQAAAAAACAALAdQAAQAAAAAACQALAfgAAQAAAAAACwAXAjQAAQAAAAAADAAXAnwAAwA
BBAkAAAAmAAAAAwABBAkAAQAOADwAAwABBAkAAgAOAFQAAwABBAkAAwA0AGwAAwABBAkABAAOAL0A
AwABBAkABQB4ANUAAwABBAkABgAeAYwAAwABBAkACAAWAbwAAwABBAkACQAWAeAAAwABBAkACwAuA
gQAAwABBAkADAAuAkwATgBvACAAUgBpAGcAaAB0AHMAIABSAGUAcwBlAHIAdgBlAGQALgAATm8gUm
lnaHRzIFJlc2VydmVkLgAAQQBpAGwAZQByAG8AbgAAQWlsZXJvbgAAUgBlAGcAdQBsAGEAcgAAUmV
ndWxhcgAAMQAuADEAMAAyADsAVQBLAFcATgA7AEEAaQBsAGUAcgBvAG4ALQBSAGUAZwB1AGwAYQBy
AAAxLjEwMjtVS1dOO0FpbGVyb24tUmVndWxhcgAAQQBpAGwAZQByAG8AbgAAQWlsZXJvbgAAVgBlA
HIAcwBpAG8AbgAgADEALgAxADAAMgA7AFAAUwAgADAAMAAxAC4AMQAwADIAOwBoAG8AdABjAG8Abg
B2ACAAMQAuADAALgA3ADAAOwBtAGEAawBlAG8AdABmAC4AbABpAGIAMgAuADUALgA1ADgAMwAyADk
AAFZlcnNpb24gMS4xMDI7UFMgMDAxLjEwMjtob3Rjb252IDEuMC43MDttYWtlb3RmLmxpYjIuNS41
ODMyOQAAQQBpAGwAZQByAG8AbgAtAFIAZQBnAHUAbABhAHIAAEFpbGVyb24tUmVndWxhcgAAUwBvA
HIAYQAgAFMAYQBnAGEAbgBvAABTb3JhIFNhZ2FubwAAUwBvAHIAYQAgAFMAYQBnAGEAbgBvAABTb3
JhIFNhZ2FubwAAaAB0AHQAcAA6AC8ALwB3AHcAdwAuAGQAbwB0AGMAbwBsAG8AbgAuAG4AZQB0AAB
odHRwOi8vd3d3LmRvdGNvbG9uLm5ldAAAaAB0AHQAcAA6AC8ALwB3AHcAdwAuAGQAbwB0AGMAbwBs
AG8AbgAuAG4AZQB0AABodHRwOi8vd3d3LmRvdGNvbG9uLm5ldAAAAAACAAAAAAAA/4MAMgAAAAAAA
AAAAAAAAAAAAAAAAAAAAHQAAAABAAIAAwAEAAUABgAHAAgACQAKAAsADAANAA4ADwAQABEAEgATAB
QAFQAWABcAGAAZABoAGwAcAB0AHgAfACAAIQAiACMAJAAlACYAJwAoACkAKgArACwALQAuAC8AMAA
xADIAMwA0ADUANgA3ADgAOQA6ADsAPAA9AD4APwBAAEEAQgBDAEQARQBGAEcASABJAEoASwBMAE0A
TgBPAFAAUQBSAFMAVABVAFYAVwBYAFkAWgBbAFwAXQBeAF8AYABhAIsAqQCDAJMAjQDDAKoAtgC3A
LQAtQCrAL4AvwC8AIwAwADBAAAAAAAB//8AAgABAAAADAAAABwAAAACAAIAAwBxAAEAcgBzAAIABA
AAAAIAAAABAAAACgBMAGYAAkRGTFQADmxhdG4AGgAEAAAAAP//AAEAAAAWAANDQVQgAB5NT0wgABZ
ST00gABYAAP//AAEAAAAA//8AAgAAAAEAAmxpZ2EADmxvY2wAFAAAAAEAAQAAAAEAAAACAAYAEAAG
AAAAAgASADQABAAAAAEATAADAAAAAgAQABYAAQAcAAAAAQABAE8AAQABAGcAAQABAE8AAwAAAAIAE
AAWAAEAHAAAAAEAAQAvAAEAAQBnAAEAAQAvAAEAGgABAAgAAgAGAAwAcwACAE8AcgACAEwAAQABAE
kAAAABAAAACgBGAGAAAkRGTFQADmxhdG4AHAAEAAAAAP//AAIAAAABABYAA0NBVCAAFk1PTCAAFlJ
PTSAAFgAA//8AAgAAAAEAAmNwc3AADmtlcm4AFAAAAAEAAAAAAAEAAQACAAYADgABAAAAAQASAAIA
AAACAB4ANgABAAoABQAFAAoAAgABACQAPQAAAAEAEgAEAAAAAQAMAAEAOP/nAAEAAQAkAAIGigAEA
AAFJAXKABoAGQAA//gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAD/sv+4/+z/7v/MAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAD/xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/9T/6AAAAAD/8QAA
ABD/vQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/7gAAAAAAAAAAAAAAAAAA//MAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABIAAAAAAAAAAP/5AAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/gAAD/4AAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//L/9AAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAA/+gAAAAAAAkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/zAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/mAAAAAAAAAAAAAAAAAAD
/4gAA//AAAAAA//YAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/+AAAAAAAAP/OAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/zv/qAAAAAP/0AAAACAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/ZAAD/egAA/1kAAAAA/5D/rgAAAAAAAAAAAA
AAAAAAAAAAAAAAAAD/9AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAD/8AAA/7b/8P+wAAD/8P/E/98AAAAA/8P/+P/0//oAAAAAAAAAAAAA//gA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/+AAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/w//C/9MAAP/SAAD/9wAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAD/yAAA/+kAAAAA//QAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/9wAAAAD//QAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAP/2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAP/cAAAAAAAAAAAAAAAA/7YAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAP/8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/6AAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAkAFAAEAAAAAQACwAAABcA
BgAAAAAAAAAIAA4AAAAAAAsAEgAAAAAAAAATABkAAwANAAAAAQAJAAAAAAAAAAAAAAAAAAAAGAAAA
AAABwAAAAAAAAAAAAAAFQAFAAAAAAAYABgAAAAUAAAACgAAAAwAAgAPABEAFgAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFAAEAEQBdAAYAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAcAAAAAAAAABwAAAAAACAAAAAAAAAAAAAcAAAAHAAAAEwAJ
ABUADgAPAAAACwAQAAAAAAAAAAAAAAAAAAUAGAACAAIAAgAAAAIAGAAXAAAAGAAAABYAFgACABYAA
gAWAAAAEQADAAoAFAAMAA0ABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAASAAAAEgAGAAEAHgAkAC
YAJwApACoALQAuAC8AMgAzADcAOAA5ADoAPAA9AEUASABOAE8AUgBTAFUAVwBZAFoAWwBcAF0AcwA
AAAAAAQAAAADa3tfFAAAAANAan9kAAAAA4QodoQ==
"""
                )
            ),
            10 if size is None else size,
            layout_engine=Layout.BASIC,
        )
    return load_default_imagefont()
