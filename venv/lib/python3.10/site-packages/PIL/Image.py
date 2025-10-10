#
# The Python Imaging Library.
# $Id$
#
# the Image class wrapper
#
# partial release history:
# 1995-09-09 fl   Created
# 1996-03-11 fl   PIL release 0.0 (proof of concept)
# 1996-04-30 fl   PIL release 0.1b1
# 1999-07-28 fl   PIL release 1.0 final
# 2000-06-07 fl   PIL release 1.1
# 2000-10-20 fl   PIL release 1.1.1
# 2001-05-07 fl   PIL release 1.1.2
# 2002-03-15 fl   PIL release 1.1.3
# 2003-05-10 fl   PIL release 1.1.4
# 2005-03-28 fl   PIL release 1.1.5
# 2006-12-02 fl   PIL release 1.1.6
# 2009-11-15 fl   PIL release 1.1.7
#
# Copyright (c) 1997-2009 by Secret Labs AB.  All rights reserved.
# Copyright (c) 1995-2009 by Fredrik Lundh.
#
# See the README file for information on usage and redistribution.
#

from __future__ import annotations

import abc
import atexit
import builtins
import io
import logging
import math
import os
import re
import struct
import sys
import tempfile
import warnings
from collections.abc import Callable, Iterator, MutableMapping, Sequence
from enum import IntEnum
from types import ModuleType
from typing import IO, Any, Literal, Protocol, cast

# VERSION was removed in Pillow 6.0.0.
# PILLOW_VERSION was removed in Pillow 9.0.0.
# Use __version__ instead.
from . import (
    ExifTags,
    ImageMode,
    TiffTags,
    UnidentifiedImageError,
    __version__,
    _plugins,
)
from ._binary import i32le, o32be, o32le
from ._deprecate import deprecate
from ._util import DeferredError, is_path

ElementTree: ModuleType | None
try:
    from defusedxml import ElementTree
except ImportError:
    ElementTree = None

logger = logging.getLogger(__name__)


class DecompressionBombWarning(RuntimeWarning):
    pass


class DecompressionBombError(Exception):
    pass


WARN_POSSIBLE_FORMATS: bool = False

# Limit to around a quarter gigabyte for a 24-bit (3 bpp) image
MAX_IMAGE_PIXELS: int | None = int(1024 * 1024 * 1024 // 4 // 3)


try:
    # If the _imaging C module is not present, Pillow will not load.
    # Note that other modules should not refer to _imaging directly;
    # import Image and use the Image.core variable instead.
    # Also note that Image.core is not a publicly documented interface,
    # and should be considered private and subject to change.
    from . import _imaging as core

    if __version__ != getattr(core, "PILLOW_VERSION", None):
        msg = (
            "The _imaging extension was built for another version of Pillow or PIL:\n"
            f"Core version: {getattr(core, 'PILLOW_VERSION', None)}\n"
            f"Pillow version: {__version__}"
        )
        raise ImportError(msg)

except ImportError as v:
    core = DeferredError.new(ImportError("The _imaging C module is not installed."))
    # Explanations for ways that we know we might have an import error
    if str(v).startswith("Module use of python"):
        # The _imaging C module is present, but not compiled for
        # the right version (windows only).  Print a warning, if
        # possible.
        warnings.warn(
            "The _imaging extension was built for another version of Python.",
            RuntimeWarning,
        )
    elif str(v).startswith("The _imaging extension"):
        warnings.warn(str(v), RuntimeWarning)
    # Fail here anyway. Don't let people run with a mostly broken Pillow.
    # see docs/porting.rst
    raise


def isImageType(t: Any) -> TypeGuard[Image]:
    """
    Checks if an object is an image object.

    .. warning::

       This function is for internal use only.

    :param t: object to check if it's an image
    :returns: True if the object is an image
    """
    deprecate("Image.isImageType(im)", 12, "isinstance(im, Image.Image)")
    return hasattr(t, "im")


#
# Constants


# transpose
class Transpose(IntEnum):
    FLIP_LEFT_RIGHT = 0
    FLIP_TOP_BOTTOM = 1
    ROTATE_90 = 2
    ROTATE_180 = 3
    ROTATE_270 = 4
    TRANSPOSE = 5
    TRANSVERSE = 6


# transforms (also defined in Imaging.h)
class Transform(IntEnum):
    AFFINE = 0
    EXTENT = 1
    PERSPECTIVE = 2
    QUAD = 3
    MESH = 4


# resampling filters (also defined in Imaging.h)
class Resampling(IntEnum):
    NEAREST = 0
    BOX = 4
    BILINEAR = 2
    HAMMING = 5
    BICUBIC = 3
    LANCZOS = 1


_filters_support = {
    Resampling.BOX: 0.5,
    Resampling.BILINEAR: 1.0,
    Resampling.HAMMING: 1.0,
    Resampling.BICUBIC: 2.0,
    Resampling.LANCZOS: 3.0,
}


# dithers
class Dither(IntEnum):
    NONE = 0
    ORDERED = 1  # Not yet implemented
    RASTERIZE = 2  # Not yet implemented
    FLOYDSTEINBERG = 3  # default


# palettes/quantizers
class Palette(IntEnum):
    WEB = 0
    ADAPTIVE = 1


class Quantize(IntEnum):
    MEDIANCUT = 0
    MAXCOVERAGE = 1
    FASTOCTREE = 2
    LIBIMAGEQUANT = 3


module = sys.modules[__name__]
for enum in (Transpose, Transform, Resampling, Dither, Palette, Quantize):
    for item in enum:
        setattr(module, item.name, item.value)


if hasattr(core, "DEFAULT_STRATEGY"):
    DEFAULT_STRATEGY = core.DEFAULT_STRATEGY
    FILTERED = core.FILTERED
    HUFFMAN_ONLY = core.HUFFMAN_ONLY
    RLE = core.RLE
    FIXED = core.FIXED


# --------------------------------------------------------------------
# Registries

TYPE_CHECKING = False
if TYPE_CHECKING:
    import mmap
    from xml.etree.ElementTree import Element

    from IPython.lib.pretty import PrettyPrinter

    from . import ImageFile, ImageFilter, ImagePalette, ImageQt, TiffImagePlugin
    from ._typing import CapsuleType, NumpyArray, StrOrBytesPath, TypeGuard
ID: list[str] = []
OPEN: dict[
    str,
    tuple[
        Callable[[IO[bytes], str | bytes], ImageFile.ImageFile],
        Callable[[bytes], bool | str] | None,
    ],
] = {}
MIME: dict[str, str] = {}
SAVE: dict[str, Callable[[Image, IO[bytes], str | bytes], None]] = {}
SAVE_ALL: dict[str, Callable[[Image, IO[bytes], str | bytes], None]] = {}
EXTENSION: dict[str, str] = {}
DECODERS: dict[str, type[ImageFile.PyDecoder]] = {}
ENCODERS: dict[str, type[ImageFile.PyEncoder]] = {}

# --------------------------------------------------------------------
# Modes

_ENDIAN = "<" if sys.byteorder == "little" else ">"


def _conv_type_shape(im: Image) -> tuple[tuple[int, ...], str]:
    m = ImageMode.getmode(im.mode)
    shape: tuple[int, ...] = (im.height, im.width)
    extra = len(m.bands)
    if extra != 1:
        shape += (extra,)
    return shape, m.typestr


MODES = [
    "1",
    "CMYK",
    "F",
    "HSV",
    "I",
    "I;16",
    "I;16B",
    "I;16L",
    "I;16N",
    "L",
    "LA",
    "La",
    "LAB",
    "P",
    "PA",
    "RGB",
    "RGBA",
    "RGBa",
    "RGBX",
    "YCbCr",
]

# raw modes that may be memory mapped.  NOTE: if you change this, you
# may have to modify the stride calculation in map.c too!
_MAPMODES = ("L", "P", "RGBX", "RGBA", "CMYK", "I;16", "I;16L", "I;16B")


def getmodebase(mode: str) -> str:
    """
    Gets the "base" mode for given mode.  This function returns "L" for
    images that contain grayscale data, and "RGB" for images that
    contain color data.

    :param mode: Input mode.
    :returns: "L" or "RGB".
    :exception KeyError: If the input mode was not a standard mode.
    """
    return ImageMode.getmode(mode).basemode


def getmodetype(mode: str) -> str:
    """
    Gets the storage type mode.  Given a mode, this function returns a
    single-layer mode suitable for storing individual bands.

    :param mode: Input mode.
    :returns: "L", "I", or "F".
    :exception KeyError: If the input mode was not a standard mode.
    """
    return ImageMode.getmode(mode).basetype


def getmodebandnames(mode: str) -> tuple[str, ...]:
    """
    Gets a list of individual band names.  Given a mode, this function returns
    a tuple containing the names of individual bands (use
    :py:method:`~PIL.Image.getmodetype` to get the mode used to store each
    individual band.

    :param mode: Input mode.
    :returns: A tuple containing band names.  The length of the tuple
        gives the number of bands in an image of the given mode.
    :exception KeyError: If the input mode was not a standard mode.
    """
    return ImageMode.getmode(mode).bands


def getmodebands(mode: str) -> int:
    """
    Gets the number of individual bands for this mode.

    :param mode: Input mode.
    :returns: The number of bands in this mode.
    :exception KeyError: If the input mode was not a standard mode.
    """
    return len(ImageMode.getmode(mode).bands)


# --------------------------------------------------------------------
# Helpers

_initialized = 0


def preinit() -> None:
    """
    Explicitly loads BMP, GIF, JPEG, PPM and PPM file format drivers.

    It is called when opening or saving images.
    """

    global _initialized
    if _initialized >= 1:
        return

    try:
        from . import BmpImagePlugin

        assert BmpImagePlugin
    except ImportError:
        pass
    try:
        from . import GifImagePlugin

        assert GifImagePlugin
    except ImportError:
        pass
    try:
        from . import JpegImagePlugin

        assert JpegImagePlugin
    except ImportError:
        pass
    try:
        from . import PpmImagePlugin

        assert PpmImagePlugin
    except ImportError:
        pass
    try:
        from . import PngImagePlugin

        assert PngImagePlugin
    except ImportError:
        pass

    _initialized = 1


def init() -> bool:
    """
    Explicitly initializes the Python Imaging Library. This function
    loads all available file format drivers.

    It is called when opening or saving images if :py:meth:`~preinit()` is
    insufficient, and by :py:meth:`~PIL.features.pilinfo`.
    """

    global _initialized
    if _initialized >= 2:
        return False

    parent_name = __name__.rpartition(".")[0]
    for plugin in _plugins:
        try:
            logger.debug("Importing %s", plugin)
            __import__(f"{parent_name}.{plugin}", globals(), locals(), [])
        except ImportError as e:
            logger.debug("Image: failed to import %s: %s", plugin, e)

    if OPEN or SAVE:
        _initialized = 2
        return True
    return False


# --------------------------------------------------------------------
# Codec factories (used by tobytes/frombytes and ImageFile.load)


def _getdecoder(
    mode: str, decoder_name: str, args: Any, extra: tuple[Any, ...] = ()
) -> core.ImagingDecoder | ImageFile.PyDecoder:
    # tweak arguments
    if args is None:
        args = ()
    elif not isinstance(args, tuple):
        args = (args,)

    try:
        decoder = DECODERS[decoder_name]
    except KeyError:
        pass
    else:
        return decoder(mode, *args + extra)

    try:
        # get decoder
        decoder = getattr(core, f"{decoder_name}_decoder")
    except AttributeError as e:
        msg = f"decoder {decoder_name} not available"
        raise OSError(msg) from e
    return decoder(mode, *args + extra)


def _getencoder(
    mode: str, encoder_name: str, args: Any, extra: tuple[Any, ...] = ()
) -> core.ImagingEncoder | ImageFile.PyEncoder:
    # tweak arguments
    if args is None:
        args = ()
    elif not isinstance(args, tuple):
        args = (args,)

    try:
        encoder = ENCODERS[encoder_name]
    except KeyError:
        pass
    else:
        return encoder(mode, *args + extra)

    try:
        # get encoder
        encoder = getattr(core, f"{encoder_name}_encoder")
    except AttributeError as e:
        msg = f"encoder {encoder_name} not available"
        raise OSError(msg) from e
    return encoder(mode, *args + extra)


# --------------------------------------------------------------------
# Simple expression analyzer


class ImagePointTransform:
    """
    Used with :py:meth:`~PIL.Image.Image.point` for single band images with more than
    8 bits, this represents an affine transformation, where the value is multiplied by
    ``scale`` and ``offset`` is added.
    """

    def __init__(self, scale: float, offset: float) -> None:
        self.scale = scale
        self.offset = offset

    def __neg__(self) -> ImagePointTransform:
        return ImagePointTransform(-self.scale, -self.offset)

    def __add__(self, other: ImagePointTransform | float) -> ImagePointTransform:
        if isinstance(other, ImagePointTransform):
            return ImagePointTransform(
                self.scale + other.scale, self.offset + other.offset
            )
        return ImagePointTransform(self.scale, self.offset + other)

    __radd__ = __add__

    def __sub__(self, other: ImagePointTransform | float) -> ImagePointTransform:
        return self + -other

    def __rsub__(self, other: ImagePointTransform | float) -> ImagePointTransform:
        return other + -self

    def __mul__(self, other: ImagePointTransform | float) -> ImagePointTransform:
        if isinstance(other, ImagePointTransform):
            return NotImplemented
        return ImagePointTransform(self.scale * other, self.offset * other)

    __rmul__ = __mul__

    def __truediv__(self, other: ImagePointTransform | float) -> ImagePointTransform:
        if isinstance(other, ImagePointTransform):
            return NotImplemented
        return ImagePointTransform(self.scale / other, self.offset / other)


def _getscaleoffset(
    expr: Callable[[ImagePointTransform], ImagePointTransform | float],
) -> tuple[float, float]:
    a = expr(ImagePointTransform(1, 0))
    return (a.scale, a.offset) if isinstance(a, ImagePointTransform) else (0, a)


# --------------------------------------------------------------------
# Implementation wrapper


class SupportsGetData(Protocol):
    def getdata(
        self,
    ) -> tuple[Transform, Sequence[int]]: ...


class Image:
    """
    This class represents an image object.  To create
    :py:class:`~PIL.Image.Image` objects, use the appropriate factory
    functions.  There's hardly ever any reason to call the Image constructor
    directly.

    * :py:func:`~PIL.Image.open`
    * :py:func:`~PIL.Image.new`
    * :py:func:`~PIL.Image.frombytes`
    """

    format: str | None = None
    format_description: str | None = None
    _close_exclusive_fp_after_loading = True

    def __init__(self) -> None:
        # FIXME: take "new" parameters / other image?
        self._im: core.ImagingCore | DeferredError | None = None
        self._mode = ""
        self._size = (0, 0)
        self.palette: ImagePalette.ImagePalette | None = None
        self.info: dict[str | tuple[int, int], Any] = {}
        self.readonly = 0
        self._exif: Exif | None = None

    @property
    def im(self) -> core.ImagingCore:
        if isinstance(self._im, DeferredError):
            raise self._im.ex
        assert self._im is not None
        return self._im

    @im.setter
    def im(self, im: core.ImagingCore) -> None:
        self._im = im

    @property
    def width(self) -> int:
        return self.size[0]

    @property
    def height(self) -> int:
        return self.size[1]

    @property
    def size(self) -> tuple[int, int]:
        return self._size

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def readonly(self) -> int:
        return (self._im and self._im.readonly) or self._readonly

    @readonly.setter
    def readonly(self, readonly: int) -> None:
        self._readonly = readonly

    def _new(self, im: core.ImagingCore) -> Image:
        new = Image()
        new.im = im
        new._mode = im.mode
        new._size = im.size
        if im.mode in ("P", "PA"):
            if self.palette:
                new.palette = self.palette.copy()
            else:
                from . import ImagePalette

                new.palette = ImagePalette.ImagePalette()
        new.info = self.info.copy()
        return new

    # Context manager support
    def __enter__(self):
        return self

    def __exit__(self, *args):
        from . import ImageFile

        if isinstance(self, ImageFile.ImageFile):
            if getattr(self, "_exclusive_fp", False):
                self._close_fp()
            self.fp = None

    def close(self) -> None:
        """
        This operation will destroy the image core and release its memory.
        The image data will be unusable afterward.

        This function is required to close images that have multiple frames or
        have not had their file read and closed by the
        :py:meth:`~PIL.Image.Image.load` method. See :ref:`file-handling` for
        more information.
        """
        if getattr(self, "map", None):
            if sys.platform == "win32" and hasattr(sys, "pypy_version_info"):
                self.map.close()
            self.map: mmap.mmap | None = None

        # Instead of simply setting to None, we're setting up a
        # deferred error that will better explain that the core image
        # object is gone.
        self._im = DeferredError(ValueError("Operation on closed image"))

    def _copy(self) -> None:
        self.load()
        self.im = self.im.copy()
        self.readonly = 0

    def _ensure_mutable(self) -> None:
        if self.readonly:
            self._copy()
        else:
            self.load()

    def _dump(
        self, file: str | None = None, format: str | None = None, **options: Any
    ) -> str:
        suffix = ""
        if format:
            suffix = f".{format}"

        if not file:
            f, filename = tempfile.mkstemp(suffix)
            os.close(f)
        else:
            filename = file
            if not filename.endswith(suffix):
                filename = filename + suffix

        self.load()

        if not format or format == "PPM":
            self.im.save_ppm(filename)
        else:
            self.save(filename, format, **options)

        return filename

    def __eq__(self, other: object) -> bool:
        if self.__class__ is not other.__class__:
            return False
        assert isinstance(other, Image)
        return (
            self.mode == other.mode
            and self.size == other.size
            and self.info == other.info
            and self.getpalette() == other.getpalette()
            and self.tobytes() == other.tobytes()
        )

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__module__}.{self.__class__.__name__} "
            f"image mode={self.mode} size={self.size[0]}x{self.size[1]} "
            f"at 0x{id(self):X}>"
        )

    def _repr_pretty_(self, p: PrettyPrinter, cycle: bool) -> None:
        """IPython plain text display support"""

        # Same as __repr__ but without unpredictable id(self),
        # to keep Jupyter notebook `text/plain` output stable.
        p.text(
            f"<{self.__class__.__module__}.{self.__class__.__name__} "
            f"image mode={self.mode} size={self.size[0]}x{self.size[1]}>"
        )

    def _repr_image(self, image_format: str, **kwargs: Any) -> bytes | None:
        """Helper function for iPython display hook.

        :param image_format: Image format.
        :returns: image as bytes, saved into the given format.
        """
        b = io.BytesIO()
        try:
            self.save(b, image_format, **kwargs)
        except Exception:
            return None
        return b.getvalue()

    def _repr_png_(self) -> bytes | None:
        """iPython display hook support for PNG format.

        :returns: PNG version of the image as bytes
        """
        return self._repr_image("PNG", compress_level=1)

    def _repr_jpeg_(self) -> bytes | None:
        """iPython display hook support for JPEG format.

        :returns: JPEG version of the image as bytes
        """
        return self._repr_image("JPEG")

    @property
    def __array_interface__(self) -> dict[str, str | bytes | int | tuple[int, ...]]:
        # numpy array interface support
        new: dict[str, str | bytes | int | tuple[int, ...]] = {"version": 3}
        if self.mode == "1":
            # Binary images need to be extended from bits to bytes
            # See: https://github.com/python-pillow/Pillow/issues/350
            new["data"] = self.tobytes("raw", "L")
        else:
            new["data"] = self.tobytes()
        new["shape"], new["typestr"] = _conv_type_shape(self)
        return new

    def __arrow_c_schema__(self) -> object:
        self.load()
        return self.im.__arrow_c_schema__()

    def __arrow_c_array__(
        self, requested_schema: object | None = None
    ) -> tuple[object, object]:
        self.load()
        return (self.im.__arrow_c_schema__(), self.im.__arrow_c_array__())

    def __getstate__(self) -> list[Any]:
        im_data = self.tobytes()  # load image first
        return [self.info, self.mode, self.size, self.getpalette(), im_data]

    def __setstate__(self, state: list[Any]) -> None:
        Image.__init__(self)
        info, mode, size, palette, data = state[:5]
        self.info = info
        self._mode = mode
        self._size = size
        self.im = core.new(mode, size)
        if mode in ("L", "LA", "P", "PA") and palette:
            self.putpalette(palette)
        self.frombytes(data)

    def tobytes(self, encoder_name: str = "raw", *args: Any) -> bytes:
        """
        Return image as a bytes object.

        .. warning::

            This method returns raw image data derived from Pillow's internal
            storage. For compressed image data (e.g. PNG, JPEG) use
            :meth:`~.save`, with a BytesIO parameter for in-memory data.

        :param encoder_name: What encoder to use.

                             The default is to use the standard "raw" encoder.
                             To see how this packs pixel data into the returned
                             bytes, see :file:`libImaging/Pack.c`.

                             A list of C encoders can be seen under codecs
                             section of the function array in
                             :file:`_imaging.c`. Python encoders are registered
                             within the relevant plugins.
        :param args: Extra arguments to the encoder.
        :returns: A :py:class:`bytes` object.
        """

        encoder_args: Any = args
        if len(encoder_args) == 1 and isinstance(encoder_args[0], tuple):
            # may pass tuple instead of argument list
            encoder_args = encoder_args[0]

        if encoder_name == "raw" and encoder_args == ():
            encoder_args = self.mode

        self.load()

        if self.width == 0 or self.height == 0:
            return b""

        # unpack data
        e = _getencoder(self.mode, encoder_name, encoder_args)
        e.setimage(self.im)

        from . import ImageFile

        bufsize = max(ImageFile.MAXBLOCK, self.size[0] * 4)  # see RawEncode.c

        output = []
        while True:
            bytes_consumed, errcode, data = e.encode(bufsize)
            output.append(data)
            if errcode:
                break
        if errcode < 0:
            msg = f"encoder error {errcode} in tobytes"
            raise RuntimeError(msg)

        return b"".join(output)

    def tobitmap(self, name: str = "image") -> bytes:
        """
        Returns the image converted to an X11 bitmap.

        .. note:: This method only works for mode "1" images.

        :param name: The name prefix to use for the bitmap variables.
        :returns: A string containing an X11 bitmap.
        :raises ValueError: If the mode is not "1"
        """

        self.load()
        if self.mode != "1":
            msg = "not a bitmap"
            raise ValueError(msg)
        data = self.tobytes("xbm")
        return b"".join(
            [
                f"#define {name}_width {self.size[0]}\n".encode("ascii"),
                f"#define {name}_height {self.size[1]}\n".encode("ascii"),
                f"static char {name}_bits[] = {{\n".encode("ascii"),
                data,
                b"};",
            ]
        )

    def frombytes(
        self,
        data: bytes | bytearray | SupportsArrayInterface,
        decoder_name: str = "raw",
        *args: Any,
    ) -> None:
        """
        Loads this image with pixel data from a bytes object.

        This method is similar to the :py:func:`~PIL.Image.frombytes` function,
        but loads data into this image instead of creating a new image object.
        """

        if self.width == 0 or self.height == 0:
            return

        decoder_args: Any = args
        if len(decoder_args) == 1 and isinstance(decoder_args[0], tuple):
            # may pass tuple instead of argument list
            decoder_args = decoder_args[0]

        # default format
        if decoder_name == "raw" and decoder_args == ():
            decoder_args = self.mode

        # unpack data
        d = _getdecoder(self.mode, decoder_name, decoder_args)
        d.setimage(self.im)
        s = d.decode(data)

        if s[0] >= 0:
            msg = "not enough image data"
            raise ValueError(msg)
        if s[1] != 0:
            msg = "cannot decode image data"
            raise ValueError(msg)

    def load(self) -> core.PixelAccess | None:
        """
        Allocates storage for the image and loads the pixel data.  In
        normal cases, you don't need to call this method, since the
        Image class automatically loads an opened image when it is
        accessed for the first time.

        If the file associated with the image was opened by Pillow, then this
        method will close it. The exception to this is if the image has
        multiple frames, in which case the file will be left open for seek
        operations. See :ref:`file-handling` for more information.

        :returns: An image access object.
        :rtype: :py:class:`.PixelAccess`
        """
        if self._im is not None and self.palette and self.palette.dirty:
            # realize palette
            mode, arr = self.palette.getdata()
            self.im.putpalette(self.palette.mode, mode, arr)
            self.palette.dirty = 0
            self.palette.rawmode = None
            if "transparency" in self.info and mode in ("LA", "PA"):
                if isinstance(self.info["transparency"], int):
                    self.im.putpalettealpha(self.info["transparency"], 0)
                else:
                    self.im.putpalettealphas(self.info["transparency"])
                self.palette.mode = "RGBA"
            else:
                self.palette.palette = self.im.getpalette(
                    self.palette.mode, self.palette.mode
                )

        if self._im is not None:
            return self.im.pixel_access(self.readonly)
        return None

    def verify(self) -> None:
        """
        Verifies the contents of a file. For data read from a file, this
        method attempts to determine if the file is broken, without
        actually decoding the image data.  If this method finds any
        problems, it raises suitable exceptions.  If you need to load
        the image after using this method, you must reopen the image
        file.
        """
        pass

    def convert(
        self,
        mode: str | None = None,
        matrix: tuple[float, ...] | None = None,
        dither: Dither | None = None,
        palette: Palette = Palette.WEB,
        colors: int = 256,
    ) -> Image:
        """
        Returns a converted copy of this image. For the "P" mode, this
        method translates pixels through the palette.  If mode is
        omitted, a mode is chosen so that all information in the image
        and the palette can be represented without a palette.

        This supports all possible conversions between "L", "RGB" and "CMYK". The
        ``matrix`` argument only supports "L" and "RGB".

        When translating a color image to grayscale (mode "L"),
        the library uses the ITU-R 601-2 luma transform::

            L = R * 299/1000 + G * 587/1000 + B * 114/1000

        The default method of converting a grayscale ("L") or "RGB"
        image into a bilevel (mode "1") image uses Floyd-Steinberg
        dither to approximate the original image luminosity levels. If
        dither is ``None``, all values larger than 127 are set to 255 (white),
        all other values to 0 (black). To use other thresholds, use the
        :py:meth:`~PIL.Image.Image.point` method.

        When converting from "RGBA" to "P" without a ``matrix`` argument,
        this passes the operation to :py:meth:`~PIL.Image.Image.quantize`,
        and ``dither`` and ``palette`` are ignored.

        When converting from "PA", if an "RGBA" palette is present, the alpha
        channel from the image will be used instead of the values from the palette.

        :param mode: The requested mode. See: :ref:`concept-modes`.
        :param matrix: An optional conversion matrix.  If given, this
           should be 4- or 12-tuple containing floating point values.
        :param dither: Dithering method, used when converting from
           mode "RGB" to "P" or from "RGB" or "L" to "1".
           Available methods are :data:`Dither.NONE` or :data:`Dither.FLOYDSTEINBERG`
           (default). Note that this is not used when ``matrix`` is supplied.
        :param palette: Palette to use when converting from mode "RGB"
           to "P".  Available palettes are :data:`Palette.WEB` or
           :data:`Palette.ADAPTIVE`.
        :param colors: Number of colors to use for the :data:`Palette.ADAPTIVE`
           palette. Defaults to 256.
        :rtype: :py:class:`~PIL.Image.Image`
        :returns: An :py:class:`~PIL.Image.Image` object.
        """

        if mode in ("BGR;15", "BGR;16", "BGR;24"):
            deprecate(mode, 12)

        self.load()

        has_transparency = "transparency" in self.info
        if not mode and self.mode == "P":
            # determine default mode
            if self.palette:
                mode = self.palette.mode
            else:
                mode = "RGB"
            if mode == "RGB" and has_transparency:
                mode = "RGBA"
        if not mode or (mode == self.mode and not matrix):
            return self.copy()

        if matrix:
            # matrix conversion
            if mode not in ("L", "RGB"):
                msg = "illegal conversion"
                raise ValueError(msg)
            im = self.im.convert_matrix(mode, matrix)
            new_im = self._new(im)
            if has_transparency and self.im.bands == 3:
                transparency = new_im.info["transparency"]

                def convert_transparency(
                    m: tuple[float, ...], v: tuple[int, int, int]
                ) -> int:
                    value = m[0] * v[0] + m[1] * v[1] + m[2] * v[2] + m[3] * 0.5
                    return max(0, min(255, int(value)))

                if mode == "L":
                    transparency = convert_transparency(matrix, transparency)
                elif len(mode) == 3:
                    transparency = tuple(
                        convert_transparency(matrix[i * 4 : i * 4 + 4], transparency)
                        for i in range(len(transparency))
                    )
                new_im.info["transparency"] = transparency
            return new_im

        if mode == "P" and self.mode == "RGBA":
            return self.quantize(colors)

        trns = None
        delete_trns = False
        # transparency handling
        if has_transparency:
            if (self.mode in ("1", "L", "I", "I;16") and mode in ("LA", "RGBA")) or (
                self.mode == "RGB" and mode in ("La", "LA", "RGBa", "RGBA")
            ):
                # Use transparent conversion to promote from transparent
                # color to an alpha channel.
                new_im = self._new(
                    self.im.convert_transparent(mode, self.info["transparency"])
                )
                del new_im.info["transparency"]
                return new_im
            elif self.mode in ("L", "RGB", "P") and mode in ("L", "RGB", "P"):
                t = self.info["transparency"]
                if isinstance(t, bytes):
                    # Dragons. This can't be represented by a single color
                    warnings.warn(
                        "Palette images with Transparency expressed in bytes should be "
                        "converted to RGBA images"
                    )
                    delete_trns = True
                else:
                    # get the new transparency color.
                    # use existing conversions
                    trns_im = new(self.mode, (1, 1))
                    if self.mode == "P":
                        assert self.palette is not None
                        trns_im.putpalette(self.palette, self.palette.mode)
                        if isinstance(t, tuple):
                            err = "Couldn't allocate a palette color for transparency"
                            assert trns_im.palette is not None
                            try:
                                t = trns_im.palette.getcolor(t, self)
                            except ValueError as e:
                                if str(e) == "cannot allocate more than 256 colors":
                                    # If all 256 colors are in use,
                                    # then there is no need for transparency
                                    t = None
                                else:
                                    raise ValueError(err) from e
                    if t is None:
                        trns = None
                    else:
                        trns_im.putpixel((0, 0), t)

                        if mode in ("L", "RGB"):
                            trns_im = trns_im.convert(mode)
                        else:
                            # can't just retrieve the palette number, got to do it
                            # after quantization.
                            trns_im = trns_im.convert("RGB")
                        trns = trns_im.getpixel((0, 0))

            elif self.mode == "P" and mode in ("LA", "PA", "RGBA"):
                t = self.info["transparency"]
                delete_trns = True

                if isinstance(t, bytes):
                    self.im.putpalettealphas(t)
                elif isinstance(t, int):
                    self.im.putpalettealpha(t, 0)
                else:
                    msg = "Transparency for P mode should be bytes or int"
                    raise ValueError(msg)

        if mode == "P" and palette == Palette.ADAPTIVE:
            im = self.im.quantize(colors)
            new_im = self._new(im)
            from . import ImagePalette

            new_im.palette = ImagePalette.ImagePalette(
                "RGB", new_im.im.getpalette("RGB")
            )
            if delete_trns:
                # This could possibly happen if we requantize to fewer colors.
                # The transparency would be totally off in that case.
                del new_im.info["transparency"]
            if trns is not None:
                try:
                    new_im.info["transparency"] = new_im.palette.getcolor(
                        cast(tuple[int, ...], trns),  # trns was converted to RGB
                        new_im,
                    )
                except Exception:
                    # if we can't make a transparent color, don't leave the old
                    # transparency hanging around to mess us up.
                    del new_im.info["transparency"]
                    warnings.warn("Couldn't allocate palette entry for transparency")
            return new_im

        if "LAB" in (self.mode, mode):
            im = self
            if mode == "LAB":
                if im.mode not in ("RGB", "RGBA", "RGBX"):
                    im = im.convert("RGBA")
                other_mode = im.mode
            else:
                other_mode = mode
            if other_mode in ("RGB", "RGBA", "RGBX"):
                from . import ImageCms

                srgb = ImageCms.createProfile("sRGB")
                lab = ImageCms.createProfile("LAB")
                profiles = [lab, srgb] if im.mode == "LAB" else [srgb, lab]
                transform = ImageCms.buildTransform(
                    profiles[0], profiles[1], im.mode, mode
                )
                return transform.apply(im)

        # colorspace conversion
        if dither is None:
            dither = Dither.FLOYDSTEINBERG

        try:
            im = self.im.convert(mode, dither)
        except ValueError:
            try:
                # normalize source image and try again
                modebase = getmodebase(self.mode)
                if modebase == self.mode:
                    raise
                im = self.im.convert(modebase)
                im = im.convert(mode, dither)
            except KeyError as e:
                msg = "illegal conversion"
                raise ValueError(msg) from e

        new_im = self._new(im)
        if mode == "P" and palette != Palette.ADAPTIVE:
            from . import ImagePalette

            new_im.palette = ImagePalette.ImagePalette("RGB", im.getpalette("RGB"))
        if delete_trns:
            # crash fail if we leave a bytes transparency in an rgb/l mode.
            del new_im.info["transparency"]
        if trns is not None:
            if new_im.mode == "P" and new_im.palette:
                try:
                    new_im.info["transparency"] = new_im.palette.getcolor(
                        cast(tuple[int, ...], trns), new_im  # trns was converted to RGB
                    )
                except ValueError as e:
                    del new_im.info["transparency"]
                    if str(e) != "cannot allocate more than 256 colors":
                        # If all 256 colors are in use,
                        # then there is no need for transparency
                        warnings.warn(
                            "Couldn't allocate palette entry for transparency"
                        )
            else:
                new_im.info["transparency"] = trns
        return new_im

    def quantize(
        self,
        colors: int = 256,
        method: int | None = None,
        kmeans: int = 0,
        palette: Image | None = None,
        dither: Dither = Dither.FLOYDSTEINBERG,
    ) -> Image:
        """
        Convert the image to 'P' mode with the specified number
        of colors.

        :param colors: The desired number of colors, <= 256
        :param method: :data:`Quantize.MEDIANCUT` (median cut),
                       :data:`Quantize.MAXCOVERAGE` (maximum coverage),
                       :data:`Quantize.FASTOCTREE` (fast octree),
                       :data:`Quantize.LIBIMAGEQUANT` (libimagequant; check support
                       using :py:func:`PIL.features.check_feature` with
                       ``feature="libimagequant"``).

                       By default, :data:`Quantize.MEDIANCUT` will be used.

                       The exception to this is RGBA images. :data:`Quantize.MEDIANCUT`
                       and :data:`Quantize.MAXCOVERAGE` do not support RGBA images, so
                       :data:`Quantize.FASTOCTREE` is used by default instead.
        :param kmeans: Integer greater than or equal to zero.
        :param palette: Quantize to the palette of given
                        :py:class:`PIL.Image.Image`.
        :param dither: Dithering method, used when converting from
           mode "RGB" to "P" or from "RGB" or "L" to "1".
           Available methods are :data:`Dither.NONE` or :data:`Dither.FLOYDSTEINBERG`
           (default).
        :returns: A new image
        """

        self.load()

        if method is None:
            # defaults:
            method = Quantize.MEDIANCUT
            if self.mode == "RGBA":
                method = Quantize.FASTOCTREE

        if self.mode == "RGBA" and method not in (
            Quantize.FASTOCTREE,
            Quantize.LIBIMAGEQUANT,
        ):
            # Caller specified an invalid mode.
            msg = (
                "Fast Octree (method == 2) and libimagequant (method == 3) "
                "are the only valid methods for quantizing RGBA images"
            )
            raise ValueError(msg)

        if palette:
            # use palette from reference image
            palette.load()
            if palette.mode != "P":
                msg = "bad mode for palette image"
                raise ValueError(msg)
            if self.mode not in {"RGB", "L"}:
                msg = "only RGB or L mode images can be quantized to a palette"
                raise ValueError(msg)
            im = self.im.convert("P", dither, palette.im)
            new_im = self._new(im)
            assert palette.palette is not None
            new_im.palette = palette.palette.copy()
            return new_im

        if kmeans < 0:
            msg = "kmeans must not be negative"
            raise ValueError(msg)

        im = self._new(self.im.quantize(colors, method, kmeans))

        from . import ImagePalette

        mode = im.im.getpalettemode()
        palette_data = im.im.getpalette(mode, mode)[: colors * len(mode)]
        im.palette = ImagePalette.ImagePalette(mode, palette_data)

        return im

    def copy(self) -> Image:
        """
        Copies this image. Use this method if you wish to paste things
        into an image, but still retain the original.

        :rtype: :py:class:`~PIL.Image.Image`
        :returns: An :py:class:`~PIL.Image.Image` object.
        """
        self.load()
        return self._new(self.im.copy())

    __copy__ = copy

    def crop(self, box: tuple[float, float, float, float] | None = None) -> Image:
        """
        Returns a rectangular region from this image. The box is a
        4-tuple defining the left, upper, right, and lower pixel
        coordinate. See :ref:`coordinate-system`.

        Note: Prior to Pillow 3.4.0, this was a lazy operation.

        :param box: The crop rectangle, as a (left, upper, right, lower)-tuple.
        :rtype: :py:class:`~PIL.Image.Image`
        :returns: An :py:class:`~PIL.Image.Image` object.
        """

        if box is None:
            return self.copy()

        if box[2] < box[0]:
            msg = "Coordinate 'right' is less than 'left'"
            raise ValueError(msg)
        elif box[3] < box[1]:
            msg = "Coordinate 'lower' is less than 'upper'"
            raise ValueError(msg)

        self.load()
        return self._new(self._crop(self.im, box))

    def _crop(
        self, im: core.ImagingCore, box: tuple[float, float, float, float]
    ) -> core.ImagingCore:
        """
        Returns a rectangular region from the core image object im.

        This is equivalent to calling im.crop((x0, y0, x1, y1)), but
        includes additional sanity checks.

        :param im: a core image object
        :param box: The crop rectangle, as a (left, upper, right, lower)-tuple.
        :returns: A core image object.
        """

        x0, y0, x1, y1 = map(int, map(round, box))

        absolute_values = (abs(x1 - x0), abs(y1 - y0))

        _decompression_bomb_check(absolute_values)

        return im.crop((x0, y0, x1, y1))

    def draft(
        self, mode: str | None, size: tuple[int, int] | None
    ) -> tuple[str, tuple[int, int, float, float]] | None:
        """
        Configures the image file loader so it returns a version of the
        image that as closely as possible matches the given mode and
        size. For example, you can use this method to convert a color
        JPEG to grayscale while loading it.

        If any changes are made, returns a tuple with the chosen ``mode`` and
        ``box`` with coordinates of the original image within the altered one.

        Note that this method modifies the :py:class:`~PIL.Image.Image` object
        in place. If the image has already been loaded, this method has no
        effect.

        Note: This method is not implemented for most images. It is
        currently implemented only for JPEG and MPO images.

        :param mode: The requested mode.
        :param size: The requested size in pixels, as a 2-tuple:
           (width, height).
        """
        pass

    def _expand(self, xmargin: int, ymargin: int | None = None) -> Image:
        if ymargin is None:
            ymargin = xmargin
        self.load()
        return self._new(self.im.expand(xmargin, ymargin))

    def filter(self, filter: ImageFilter.Filter | type[ImageFilter.Filter]) -> Image:
        """
        Filters this image using the given filter.  For a list of
        available filters, see the :py:mod:`~PIL.ImageFilter` module.

        :param filter: Filter kernel.
        :returns: An :py:class:`~PIL.Image.Image` object."""

        from . import ImageFilter

        self.load()

        if callable(filter):
            filter = filter()
        if not hasattr(filter, "filter"):
            msg = "filter argument should be ImageFilter.Filter instance or class"
            raise TypeError(msg)

        multiband = isinstance(filter, ImageFilter.MultibandFilter)
        if self.im.bands == 1 or multiband:
            return self._new(filter.filter(self.im))

        ims = [
            self._new(filter.filter(self.im.getband(c))) for c in range(self.im.bands)
        ]
        return merge(self.mode, ims)

    def getbands(self) -> tuple[str, ...]:
        """
        Returns a tuple containing the name of each band in this image.
        For example, ``getbands`` on an RGB image returns ("R", "G", "B").

        :returns: A tuple containing band names.
        :rtype: tuple
        """
        return ImageMode.getmode(self.mode).bands

    def getbbox(self, *, alpha_only: bool = True) -> tuple[int, int, int, int] | None:
        """
        Calculates the bounding box of the non-zero regions in the
        image.

        :param alpha_only: Optional flag, defaulting to ``True``.
           If ``True`` and the image has an alpha channel, trim transparent pixels.
           Otherwise, trim pixels when all channels are zero.
           Keyword-only argument.
        :returns: The bounding box is returned as a 4-tuple defining the
           left, upper, right, and lower pixel coordinate. See
           :ref:`coordinate-system`. If the image is completely empty, this
           method returns None.

        """

        self.load()
        return self.im.getbbox(alpha_only)

    def getcolors(
        self, maxcolors: int = 256
    ) -> list[tuple[int, tuple[int, ...]]] | list[tuple[int, float]] | None:
        """
        Returns a list of colors used in this image.

        The colors will be in the image's mode. For example, an RGB image will
        return a tuple of (red, green, blue) color values, and a P image will
        return the index of the color in the palette.

        :param maxcolors: Maximum number of colors.  If this number is
           exceeded, this method returns None.  The default limit is
           256 colors.
        :returns: An unsorted list of (count, pixel) values.
        """

        self.load()
        if self.mode in ("1", "L", "P"):
            h = self.im.histogram()
            out: list[tuple[int, float]] = [(h[i], i) for i in range(256) if h[i]]
            if len(out) > maxcolors:
                return None
            return out
        return self.im.getcolors(maxcolors)

    def getdata(self, band: int | None = None) -> core.ImagingCore:
        """
        Returns the contents of this image as a sequence object
        containing pixel values.  The sequence object is flattened, so
        that values for line one follow directly after the values of
        line zero, and so on.

        Note that the sequence object returned by this method is an
        internal PIL data type, which only supports certain sequence
        operations.  To convert it to an ordinary sequence (e.g. for
        printing), use ``list(im.getdata())``.

        :param band: What band to return.  The default is to return
           all bands.  To return a single band, pass in the index
           value (e.g. 0 to get the "R" band from an "RGB" image).
        :returns: A sequence-like object.
        """

        self.load()
        if band is not None:
            return self.im.getband(band)
        return self.im  # could be abused

    def getextrema(self) -> tuple[float, float] | tuple[tuple[int, int], ...]:
        """
        Gets the minimum and maximum pixel values for each band in
        the image.

        :returns: For a single-band image, a 2-tuple containing the
           minimum and maximum pixel value.  For a multi-band image,
           a tuple containing one 2-tuple for each band.
        """

        self.load()
        if self.im.bands > 1:
            return tuple(self.im.getband(i).getextrema() for i in range(self.im.bands))
        return self.im.getextrema()

    def getxmp(self) -> dict[str, Any]:
        """
        Returns a dictionary containing the XMP tags.
        Requires defusedxml to be installed.

        :returns: XMP tags in a dictionary.
        """

        def get_name(tag: str) -> str:
            return re.sub("^{[^}]+}", "", tag)

        def get_value(element: Element) -> str | dict[str, Any] | None:
            value: dict[str, Any] = {get_name(k): v for k, v in element.attrib.items()}
            children = list(element)
            if children:
                for child in children:
                    name = get_name(child.tag)
                    child_value = get_value(child)
                    if name in value:
                        if not isinstance(value[name], list):
                            value[name] = [value[name]]
                        value[name].append(child_value)
                    else:
                        value[name] = child_value
            elif value:
                if element.text:
                    value["text"] = element.text
            else:
                return element.text
            return value

        if ElementTree is None:
            warnings.warn("XMP data cannot be read without defusedxml dependency")
            return {}
        if "xmp" not in self.info:
            return {}
        root = ElementTree.fromstring(self.info["xmp"].rstrip(b"\x00 "))
        return {get_name(root.tag): get_value(root)}

    def getexif(self) -> Exif:
        """
        Gets EXIF data from the image.

        :returns: an :py:class:`~PIL.Image.Exif` object.
        """
        if self._exif is None:
            self._exif = Exif()
        elif self._exif._loaded:
            return self._exif
        self._exif._loaded = True

        exif_info = self.info.get("exif")
        if exif_info is None:
            if "Raw profile type exif" in self.info:
                exif_info = bytes.fromhex(
                    "".join(self.info["Raw profile type exif"].split("\n")[3:])
                )
            elif hasattr(self, "tag_v2"):
                self._exif.bigtiff = self.tag_v2._bigtiff
                self._exif.endian = self.tag_v2._endian
                self._exif.load_from_fp(self.fp, self.tag_v2._offset)
        if exif_info is not None:
            self._exif.load(exif_info)

        # XMP tags
        if ExifTags.Base.Orientation not in self._exif:
            xmp_tags = self.info.get("XML:com.adobe.xmp")
            pattern: str | bytes = r'tiff:Orientation(="|>)([0-9])'
            if not xmp_tags and (xmp_tags := self.info.get("xmp")):
                pattern = rb'tiff:Orientation(="|>)([0-9])'
            if xmp_tags:
                match = re.search(pattern, xmp_tags)
                if match:
                    self._exif[ExifTags.Base.Orientation] = int(match[2])

        return self._exif

    def _reload_exif(self) -> None:
        if self._exif is None or not self._exif._loaded:
            return
        self._exif._loaded = False
        self.getexif()

    def get_child_images(self) -> list[ImageFile.ImageFile]:
        from . import ImageFile

        deprecate("Image.Image.get_child_images", 13)
        return ImageFile.ImageFile.get_child_images(self)  # type: ignore[arg-type]

    def getim(self) -> CapsuleType:
        """
        Returns a capsule that points to the internal image memory.

        :returns: A capsule object.
        """

        self.load()
        return self.im.ptr

    def getpalette(self, rawmode: str | None = "RGB") -> list[int] | None:
        """
        Returns the image palette as a list.

        :param rawmode: The mode in which to return the palette. ``None`` will
           return the palette in its current mode.

           .. versionadded:: 9.1.0

        :returns: A list of color values [r, g, b, ...], or None if the
           image has no palette.
        """

        self.load()
        try:
            mode = self.im.getpalettemode()
        except ValueError:
            return None  # no palette
        if rawmode is None:
            rawmode = mode
        return list(self.im.getpalette(mode, rawmode))

    @property
    def has_transparency_data(self) -> bool:
        """
        Determine if an image has transparency data, whether in the form of an
        alpha channel, a palette with an alpha channel, or a "transparency" key
        in the info dictionary.

        Note the image might still appear solid, if all of the values shown
        within are opaque.

        :returns: A boolean.
        """
        if (
            self.mode in ("LA", "La", "PA", "RGBA", "RGBa")
            or "transparency" in self.info
        ):
            return True
        if self.mode == "P":
            assert self.palette is not None
            return self.palette.mode.endswith("A")
        return False

    def apply_transparency(self) -> None:
        """
        If a P mode image has a "transparency" key in the info dictionary,
        remove the key and instead apply the transparency to the palette.
        Otherwise, the image is unchanged.
        """
        if self.mode != "P" or "transparency" not in self.info:
            return

        from . import ImagePalette

        palette = self.getpalette("RGBA")
        assert palette is not None
        transparency = self.info["transparency"]
        if isinstance(transparency, bytes):
            for i, alpha in enumerate(transparency):
                palette[i * 4 + 3] = alpha
        else:
            palette[transparency * 4 + 3] = 0
        self.palette = ImagePalette.ImagePalette("RGBA", bytes(palette))
        self.palette.dirty = 1

        del self.info["transparency"]

    def getpixel(
        self, xy: tuple[int, int] | list[int]
    ) -> float | tuple[int, ...] | None:
        """
        Returns the pixel value at a given position.

        :param xy: The coordinate, given as (x, y). See
           :ref:`coordinate-system`.
        :returns: The pixel value.  If the image is a multi-layer image,
           this method returns a tuple.
        """

        self.load()
        return self.im.getpixel(tuple(xy))

    def getprojection(self) -> tuple[list[int], list[int]]:
        """
        Get projection to x and y axes

        :returns: Two sequences, indicating where there are non-zero
            pixels along the X-axis and the Y-axis, respectively.
        """

        self.load()
        x, y = self.im.getprojection()
        return list(x), list(y)

    def histogram(
        self, mask: Image | None = None, extrema: tuple[float, float] | None = None
    ) -> list[int]:
        """
        Returns a histogram for the image. The histogram is returned as a
        list of pixel counts, one for each pixel value in the source
        image. Counts are grouped into 256 bins for each band, even if
        the image has more than 8 bits per band. If the image has more
        than one band, the histograms for all bands are concatenated (for
        example, the histogram for an "RGB" image contains 768 values).

        A bilevel image (mode "1") is treated as a grayscale ("L") image
        by this method.

        If a mask is provided, the method returns a histogram for those
        parts of the image where the mask image is non-zero. The mask
        image must have the same size as the image, and be either a
        bi-level image (mode "1") or a grayscale image ("L").

        :param mask: An optional mask.
        :param extrema: An optional tuple of manually-specified extrema.
        :returns: A list containing pixel counts.
        """
        self.load()
        if mask:
            mask.load()
            return self.im.histogram((0, 0), mask.im)
        if self.mode in ("I", "F"):
            return self.im.histogram(
                extrema if extrema is not None else self.getextrema()
            )
        return self.im.histogram()

    def entropy(
        self, mask: Image | None = None, extrema: tuple[float, float] | None = None
    ) -> float:
        """
        Calculates and returns the entropy for the image.

        A bilevel image (mode "1") is treated as a grayscale ("L")
        image by this method.

        If a mask is provided, the method employs the histogram for
        those parts of the image where the mask image is non-zero.
        The mask image must have the same size as the image, and be
        either a bi-level image (mode "1") or a grayscale image ("L").

        :param mask: An optional mask.
        :param extrema: An optional tuple of manually-specified extrema.
        :returns: A float value representing the image entropy
        """
        self.load()
        if mask:
            mask.load()
            return self.im.entropy((0, 0), mask.im)
        if self.mode in ("I", "F"):
            return self.im.entropy(
                extrema if extrema is not None else self.getextrema()
            )
        return self.im.entropy()

    def paste(
        self,
        im: Image | str | float | tuple[float, ...],
        box: Image | tuple[int, int, int, int] | tuple[int, int] | None = None,
        mask: Image | None = None,
    ) -> None:
        """
        Pastes another image into this image. The box argument is either
        a 2-tuple giving the upper left corner, a 4-tuple defining the
        left, upper, right, and lower pixel coordinate, or None (same as
        (0, 0)). See :ref:`coordinate-system`. If a 4-tuple is given, the size
        of the pasted image must match the size of the region.

        If the modes don't match, the pasted image is converted to the mode of
        this image (see the :py:meth:`~PIL.Image.Image.convert` method for
        details).

        Instead of an image, the source can be a integer or tuple
        containing pixel values.  The method then fills the region
        with the given color.  When creating RGB images, you can
        also use color strings as supported by the ImageColor module.

        If a mask is given, this method updates only the regions
        indicated by the mask. You can use either "1", "L", "LA", "RGBA"
        or "RGBa" images (if present, the alpha band is used as mask).
        Where the mask is 255, the given image is copied as is.  Where
        the mask is 0, the current value is preserved.  Intermediate
        values will mix the two images together, including their alpha
        channels if they have them.

        See :py:meth:`~PIL.Image.Image.alpha_composite` if you want to
        combine images with respect to their alpha channels.

        :param im: Source image or pixel value (integer, float or tuple).
        :param box: An optional 4-tuple giving the region to paste into.
           If a 2-tuple is used instead, it's treated as the upper left
           corner.  If omitted or None, the source is pasted into the
           upper left corner.

           If an image is given as the second argument and there is no
           third, the box defaults to (0, 0), and the second argument
           is interpreted as a mask image.
        :param mask: An optional mask image.
        """

        if isinstance(box, Image):
            if mask is not None:
                msg = "If using second argument as mask, third argument must be None"
                raise ValueError(msg)
            # abbreviated paste(im, mask) syntax
            mask = box
            box = None

        if box is None:
            box = (0, 0)

        if len(box) == 2:
            # upper left corner given; get size from image or mask
            if isinstance(im, Image):
                size = im.size
            elif isinstance(mask, Image):
                size = mask.size
            else:
                # FIXME: use self.size here?
                msg = "cannot determine region size; use 4-item box"
                raise ValueError(msg)
            box += (box[0] + size[0], box[1] + size[1])

        source: core.ImagingCore | str | float | tuple[float, ...]
        if isinstance(im, str):
            from . import ImageColor

            source = ImageColor.getcolor(im, self.mode)
        elif isinstance(im, Image):
            im.load()
            if self.mode != im.mode:
                if self.mode != "RGB" or im.mode not in ("LA", "RGBA", "RGBa"):
                    # should use an adapter for this!
                    im = im.convert(self.mode)
            source = im.im
        else:
            source = im

        self._ensure_mutable()

        if mask:
            mask.load()
            self.im.paste(source, box, mask.im)
        else:
            self.im.paste(source, box)

    def alpha_composite(
        self, im: Image, dest: Sequence[int] = (0, 0), source: Sequence[int] = (0, 0)
    ) -> None:
        """'In-place' analog of Image.alpha_composite. Composites an image
        onto this image.

        :param im: image to composite over this one
        :param dest: Optional 2 tuple (left, top) specifying the upper
          left corner in this (destination) image.
        :param source: Optional 2 (left, top) tuple for the upper left
          corner in the overlay source image, or 4 tuple (left, top, right,
          bottom) for the bounds of the source rectangle

        Performance Note: Not currently implemented in-place in the core layer.
        """

        if not isinstance(source, (list, tuple)):
            msg = "Source must be a list or tuple"
            raise ValueError(msg)
        if not isinstance(dest, (list, tuple)):
            msg = "Destination must be a list or tuple"
            raise ValueError(msg)

        if len(source) == 4:
            overlay_crop_box = tuple(source)
        elif len(source) == 2:
            overlay_crop_box = tuple(source) + im.size
        else:
            msg = "Source must be a sequence of length 2 or 4"
            raise ValueError(msg)

        if not len(dest) == 2:
            msg = "Destination must be a sequence of length 2"
            raise ValueError(msg)
        if min(source) < 0:
            msg = "Source must be non-negative"
            raise ValueError(msg)

        # over image, crop if it's not the whole image.
        if overlay_crop_box == (0, 0) + im.size:
            overlay = im
        else:
            overlay = im.crop(overlay_crop_box)

        # target for the paste
        box = tuple(dest) + (dest[0] + overlay.width, dest[1] + overlay.height)

        # destination image. don't copy if we're using the whole image.
        if box == (0, 0) + self.size:
            background = self
        else:
            background = self.crop(box)

        result = alpha_composite(background, overlay)
        self.paste(result, box)

    def point(
        self,
        lut: (
            Sequence[float]
            | NumpyArray
            | Callable[[int], float]
            | Callable[[ImagePointTransform], ImagePointTransform | float]
            | ImagePointHandler
        ),
        mode: str | None = None,
    ) -> Image:
        """
        Maps this image through a lookup table or function.

        :param lut: A lookup table, containing 256 (or 65536 if
           self.mode=="I" and mode == "L") values per band in the
           image.  A function can be used instead, it should take a
           single argument. The function is called once for each
           possible pixel value, and the resulting table is applied to
           all bands of the image.

           It may also be an :py:class:`~PIL.Image.ImagePointHandler`
           object::

               class Example(Image.ImagePointHandler):
                 def point(self, im: Image) -> Image:
                   # Return result
        :param mode: Output mode (default is same as input). This can only be used if
           the source image has mode "L" or "P", and the output has mode "1" or the
           source image mode is "I" and the output mode is "L".
        :returns: An :py:class:`~PIL.Image.Image` object.
        """

        self.load()

        if isinstance(lut, ImagePointHandler):
            return lut.point(self)

        if callable(lut):
            # if it isn't a list, it should be a function
            if self.mode in ("I", "I;16", "F"):
                # check if the function can be used with point_transform
                # UNDONE wiredfool -- I think this prevents us from ever doing
                # a gamma function point transform on > 8bit images.
                scale, offset = _getscaleoffset(lut)  # type: ignore[arg-type]
                return self._new(self.im.point_transform(scale, offset))
            # for other modes, convert the function to a table
            flatLut = [lut(i) for i in range(256)] * self.im.bands  # type: ignore[arg-type]
        else:
            flatLut = lut

        if self.mode == "F":
            # FIXME: _imaging returns a confusing error message for this case
            msg = "point operation not supported for this mode"
            raise ValueError(msg)

        if mode != "F":
            flatLut = [round(i) for i in flatLut]
        return self._new(self.im.point(flatLut, mode))

    def putalpha(self, alpha: Image | int) -> None:
        """
        Adds or replaces the alpha layer in this image.  If the image
        does not have an alpha layer, it's converted to "LA" or "RGBA".
        The new layer must be either "L" or "1".

        :param alpha: The new alpha layer.  This can either be an "L" or "1"
           image having the same size as this image, or an integer.
        """

        self._ensure_mutable()

        if self.mode not in ("LA", "PA", "RGBA"):
            # attempt to promote self to a matching alpha mode
            try:
                mode = getmodebase(self.mode) + "A"
                try:
                    self.im.setmode(mode)
                except (AttributeError, ValueError) as e:
                    # do things the hard way
                    im = self.im.convert(mode)
                    if im.mode not in ("LA", "PA", "RGBA"):
                        msg = "alpha channel could not be added"
                        raise ValueError(msg) from e  # sanity check
                    self.im = im
                self._mode = self.im.mode
            except KeyError as e:
                msg = "illegal image mode"
                raise ValueError(msg) from e

        if self.mode in ("LA", "PA"):
            band = 1
        else:
            band = 3

        if isinstance(alpha, Image):
            # alpha layer
            if alpha.mode not in ("1", "L"):
                msg = "illegal image mode"
                raise ValueError(msg)
            alpha.load()
            if alpha.mode == "1":
                alpha = alpha.convert("L")
        else:
            # constant alpha
            try:
                self.im.fillband(band, alpha)
            except (AttributeError, ValueError):
                # do things the hard way
                alpha = new("L", self.size, alpha)
            else:
                return

        self.im.putband(alpha.im, band)

    def putdata(
        self,
        data: Sequence[float] | Sequence[Sequence[int]] | core.ImagingCore | NumpyArray,
        scale: float = 1.0,
        offset: float = 0.0,
    ) -> None:
        """
        Copies pixel data from a flattened sequence object into the image. The
        values should start at the upper left corner (0, 0), continue to the
        end of the line, followed directly by the first value of the second
        line, and so on. Data will be read until either the image or the
        sequence ends. The scale and offset values are used to adjust the
        sequence values: **pixel = value*scale + offset**.

        :param data: A flattened sequence object.
        :param scale: An optional scale value.  The default is 1.0.
        :param offset: An optional offset value.  The default is 0.0.
        """

        self._ensure_mutable()

        self.im.putdata(data, scale, offset)

    def putpalette(
        self,
        data: ImagePalette.ImagePalette | bytes | Sequence[int],
        rawmode: str = "RGB",
    ) -> None:
        """
        Attaches a palette to this image.  The image must be a "P", "PA", "L"
        or "LA" image.

        The palette sequence must contain at most 256 colors, made up of one
        integer value for each channel in the raw mode.
        For example, if the raw mode is "RGB", then it can contain at most 768
        values, made up of red, green and blue values for the corresponding pixel
        index in the 256 colors.
        If the raw mode is "RGBA", then it can contain at most 1024 values,
        containing red, green, blue and alpha values.

        Alternatively, an 8-bit string may be used instead of an integer sequence.

        :param data: A palette sequence (either a list or a string).
        :param rawmode: The raw mode of the palette. Either "RGB", "RGBA", or a mode
           that can be transformed to "RGB" or "RGBA" (e.g. "R", "BGR;15", "RGBA;L").
        """
        from . import ImagePalette

        if self.mode not in ("L", "LA", "P", "PA"):
            msg = "illegal image mode"
            raise ValueError(msg)
        if isinstance(data, ImagePalette.ImagePalette):
            if data.rawmode is not None:
                palette = ImagePalette.raw(data.rawmode, data.palette)
            else:
                palette = ImagePalette.ImagePalette(palette=data.palette)
                palette.dirty = 1
        else:
            if not isinstance(data, bytes):
                data = bytes(data)
            palette = ImagePalette.raw(rawmode, data)
        self._mode = "PA" if "A" in self.mode else "P"
        self.palette = palette
        self.palette.mode = "RGBA" if "A" in rawmode else "RGB"
        self.load()  # install new palette

    def putpixel(
        self, xy: tuple[int, int], value: float | tuple[int, ...] | list[int]
    ) -> None:
        """
        Modifies the pixel at the given position. The color is given as
        a single numerical value for single-band images, and a tuple for
        multi-band images. In addition to this, RGB and RGBA tuples are
        accepted for P and PA images.

        Note that this method is relatively slow.  For more extensive changes,
        use :py:meth:`~PIL.Image.Image.paste` or the :py:mod:`~PIL.ImageDraw`
        module instead.

        See:

        * :py:meth:`~PIL.Image.Image.paste`
        * :py:meth:`~PIL.Image.Image.putdata`
        * :py:mod:`~PIL.ImageDraw`

        :param xy: The pixel coordinate, given as (x, y). See
           :ref:`coordinate-system`.
        :param value: The pixel value.
        """

        if self.readonly:
            self._copy()
        self.load()

        if (
            self.mode in ("P", "PA")
            and isinstance(value, (list, tuple))
            and len(value) in [3, 4]
        ):
            # RGB or RGBA value for a P or PA image
            if self.mode == "PA":
                alpha = value[3] if len(value) == 4 else 255
                value = value[:3]
            assert self.palette is not None
            palette_index = self.palette.getcolor(tuple(value), self)
            value = (palette_index, alpha) if self.mode == "PA" else palette_index
        return self.im.putpixel(xy, value)

    def remap_palette(
        self, dest_map: list[int], source_palette: bytes | bytearray | None = None
    ) -> Image:
        """
        Rewrites the image to reorder the palette.

        :param dest_map: A list of indexes into the original palette.
           e.g. ``[1,0]`` would swap a two item palette, and ``list(range(256))``
           is the identity transform.
        :param source_palette: Bytes or None.
        :returns:  An :py:class:`~PIL.Image.Image` object.

        """
        from . import ImagePalette

        if self.mode not in ("L", "P"):
            msg = "illegal image mode"
            raise ValueError(msg)

        bands = 3
        palette_mode = "RGB"
        if source_palette is None:
            if self.mode == "P":
                self.load()
                palette_mode = self.im.getpalettemode()
                if palette_mode == "RGBA":
                    bands = 4
                source_palette = self.im.getpalette(palette_mode, palette_mode)
            else:  # L-mode
                source_palette = bytearray(i // 3 for i in range(768))
        elif len(source_palette) > 768:
            bands = 4
            palette_mode = "RGBA"

        palette_bytes = b""
        new_positions = [0] * 256

        # pick only the used colors from the palette
        for i, oldPosition in enumerate(dest_map):
            palette_bytes += source_palette[
                oldPosition * bands : oldPosition * bands + bands
            ]
            new_positions[oldPosition] = i

        # replace the palette color id of all pixel with the new id

        # Palette images are [0..255], mapped through a 1 or 3
        # byte/color map.  We need to remap the whole image
        # from palette 1 to palette 2. New_positions is
        # an array of indexes into palette 1.  Palette 2 is
        # palette 1 with any holes removed.

        # We're going to leverage the convert mechanism to use the
        # C code to remap the image from palette 1 to palette 2,
        # by forcing the source image into 'L' mode and adding a
        # mapping 'L' mode palette, then converting back to 'L'
        # sans palette thus converting the image bytes, then
        # assigning the optimized RGB palette.

        # perf reference, 9500x4000 gif, w/~135 colors
        # 14 sec prepatch, 1 sec postpatch with optimization forced.

        mapping_palette = bytearray(new_positions)

        m_im = self.copy()
        m_im._mode = "P"

        m_im.palette = ImagePalette.ImagePalette(
            palette_mode, palette=mapping_palette * bands
        )
        # possibly set palette dirty, then
        # m_im.putpalette(mapping_palette, 'L')  # converts to 'P'
        # or just force it.
        # UNDONE -- this is part of the general issue with palettes
        m_im.im.putpalette(palette_mode, palette_mode + ";L", m_im.palette.tobytes())

        m_im = m_im.convert("L")

        m_im.putpalette(palette_bytes, palette_mode)
        m_im.palette = ImagePalette.ImagePalette(palette_mode, palette=palette_bytes)

        if "transparency" in self.info:
            try:
                m_im.info["transparency"] = dest_map.index(self.info["transparency"])
            except ValueError:
                if "transparency" in m_im.info:
                    del m_im.info["transparency"]

        return m_im

    def _get_safe_box(
        self,
        size: tuple[int, int],
        resample: Resampling,
        box: tuple[float, float, float, float],
    ) -> tuple[int, int, int, int]:
        """Expands the box so it includes adjacent pixels
        that may be used by resampling with the given resampling filter.
        """
        filter_support = _filters_support[resample] - 0.5
        scale_x = (box[2] - box[0]) / size[0]
        scale_y = (box[3] - box[1]) / size[1]
        support_x = filter_support * scale_x
        support_y = filter_support * scale_y

        return (
            max(0, int(box[0] - support_x)),
            max(0, int(box[1] - support_y)),
            min(self.size[0], math.ceil(box[2] + support_x)),
            min(self.size[1], math.ceil(box[3] + support_y)),
        )

    def resize(
        self,
        size: tuple[int, int] | list[int] | NumpyArray,
        resample: int | None = None,
        box: tuple[float, float, float, float] | None = None,
        reducing_gap: float | None = None,
    ) -> Image:
        """
        Returns a resized copy of this image.

        :param size: The requested size in pixels, as a tuple or array:
           (width, height).
        :param resample: An optional resampling filter.  This can be
           one of :py:data:`Resampling.NEAREST`, :py:data:`Resampling.BOX`,
           :py:data:`Resampling.BILINEAR`, :py:data:`Resampling.HAMMING`,
           :py:data:`Resampling.BICUBIC` or :py:data:`Resampling.LANCZOS`.
           If the image has mode "1" or "P", it is always set to
           :py:data:`Resampling.NEAREST`. If the image mode is "BGR;15",
           "BGR;16" or "BGR;24", then the default filter is
           :py:data:`Resampling.NEAREST`. Otherwise, the default filter is
           :py:data:`Resampling.BICUBIC`. See: :ref:`concept-filters`.
        :param box: An optional 4-tuple of floats providing
           the source image region to be scaled.
           The values must be within (0, 0, width, height) rectangle.
           If omitted or None, the entire source is used.
        :param reducing_gap: Apply optimization by resizing the image
           in two steps. First, reducing the image by integer times
           using :py:meth:`~PIL.Image.Image.reduce`.
           Second, resizing using regular resampling. The last step
           changes size no less than by ``reducing_gap`` times.
           ``reducing_gap`` may be None (no first step is performed)
           or should be greater than 1.0. The bigger ``reducing_gap``,
           the closer the result to the fair resampling.
           The smaller ``reducing_gap``, the faster resizing.
           With ``reducing_gap`` greater or equal to 3.0, the result is
           indistinguishable from fair resampling in most cases.
           The default value is None (no optimization).
        :returns: An :py:class:`~PIL.Image.Image` object.
        """

        if resample is None:
            bgr = self.mode.startswith("BGR;")
            resample = Resampling.NEAREST if bgr else Resampling.BICUBIC
        elif resample not in (
            Resampling.NEAREST,
            Resampling.BILINEAR,
            Resampling.BICUBIC,
            Resampling.LANCZOS,
            Resampling.BOX,
            Resampling.HAMMING,
        ):
            msg = f"Unknown resampling filter ({resample})."

            filters = [
                f"{filter[1]} ({filter[0]})"
                for filter in (
                    (Resampling.NEAREST, "Image.Resampling.NEAREST"),
                    (Resampling.LANCZOS, "Image.Resampling.LANCZOS"),
                    (Resampling.BILINEAR, "Image.Resampling.BILINEAR"),
                    (Resampling.BICUBIC, "Image.Resampling.BICUBIC"),
                    (Resampling.BOX, "Image.Resampling.BOX"),
                    (Resampling.HAMMING, "Image.Resampling.HAMMING"),
                )
            ]
            msg += f" Use {', '.join(filters[:-1])} or {filters[-1]}"
            raise ValueError(msg)

        if reducing_gap is not None and reducing_gap < 1.0:
            msg = "reducing_gap must be 1.0 or greater"
            raise ValueError(msg)

        if box is None:
            box = (0, 0) + self.size

        size = tuple(size)
        if self.size == size and box == (0, 0) + self.size:
            return self.copy()

        if self.mode in ("1", "P"):
            resample = Resampling.NEAREST

        if self.mode in ["LA", "RGBA"] and resample != Resampling.NEAREST:
            im = self.convert({"LA": "La", "RGBA": "RGBa"}[self.mode])
            im = im.resize(size, resample, box)
            return im.convert(self.mode)

        self.load()

        if reducing_gap is not None and resample != Resampling.NEAREST:
            factor_x = int((box[2] - box[0]) / size[0] / reducing_gap) or 1
            factor_y = int((box[3] - box[1]) / size[1] / reducing_gap) or 1
            if factor_x > 1 or factor_y > 1:
                reduce_box = self._get_safe_box(size, cast(Resampling, resample), box)
                factor = (factor_x, factor_y)
                self = (
                    self.reduce(factor, box=reduce_box)
                    if callable(self.reduce)
                    else Image.reduce(self, factor, box=reduce_box)
                )
                box = (
                    (box[0] - reduce_box[0]) / factor_x,
                    (box[1] - reduce_box[1]) / factor_y,
                    (box[2] - reduce_box[0]) / factor_x,
                    (box[3] - reduce_box[1]) / factor_y,
                )

        return self._new(self.im.resize(size, resample, box))

    def reduce(
        self,
        factor: int | tuple[int, int],
        box: tuple[int, int, int, int] | None = None,
    ) -> Image:
        """
        Returns a copy of the image reduced ``factor`` times.
        If the size of the image is not dividable by ``factor``,
        the resulting size will be rounded up.

        :param factor: A greater than 0 integer or tuple of two integers
           for width and height separately.
        :param box: An optional 4-tuple of ints providing
           the source image region to be reduced.
           The values must be within ``(0, 0, width, height)`` rectangle.
           If omitted or ``None``, the entire source is used.
        """
        if not isinstance(factor, (list, tuple)):
            factor = (factor, factor)

        if box is None:
            box = (0, 0) + self.size

        if factor == (1, 1) and box == (0, 0) + self.size:
            return self.copy()

        if self.mode in ["LA", "RGBA"]:
            im = self.convert({"LA": "La", "RGBA": "RGBa"}[self.mode])
            im = im.reduce(factor, box)
            return im.convert(self.mode)

        self.load()

        return self._new(self.im.reduce(factor, box))

    def rotate(
        self,
        angle: float,
        resample: Resampling = Resampling.NEAREST,
        expand: int | bool = False,
        center: tuple[float, float] | None = None,
        translate: tuple[int, int] | None = None,
        fillcolor: float | tuple[float, ...] | str | None = None,
    ) -> Image:
        """
        Returns a rotated copy of this image.  This method returns a
        copy of this image, rotated the given number of degrees counter
        clockwise around its centre.

        :param angle: In degrees counter clockwise.
        :param resample: An optional resampling filter.  This can be
           one of :py:data:`Resampling.NEAREST` (use nearest neighbour),
           :py:data:`Resampling.BILINEAR` (linear interpolation in a 2x2
           environment), or :py:data:`Resampling.BICUBIC` (cubic spline
           interpolation in a 4x4 environment). If omitted, or if the image has
           mode "1" or "P", it is set to :py:data:`Resampling.NEAREST`.
           See :ref:`concept-filters`.
        :param expand: Optional expansion flag.  If true, expands the output
           image to make it large enough to hold the entire rotated image.
           If false or omitted, make the output image the same size as the
           input image.  Note that the expand flag assumes rotation around
           the center and no translation.
        :param center: Optional center of rotation (a 2-tuple).  Origin is
           the upper left corner.  Default is the center of the image.
        :param translate: An optional post-rotate translation (a 2-tuple).
        :param fillcolor: An optional color for area outside the rotated image.
        :returns: An :py:class:`~PIL.Image.Image` object.
        """

        angle = angle % 360.0

        # Fast paths regardless of filter, as long as we're not
        # translating or changing the center.
        if not (center or translate):
            if angle == 0:
                return self.copy()
            if angle == 180:
                return self.transpose(Transpose.ROTATE_180)
            if angle in (90, 270) and (expand or self.width == self.height):
                return self.transpose(
                    Transpose.ROTATE_90 if angle == 90 else Transpose.ROTATE_270
                )

        # Calculate the affine matrix.  Note that this is the reverse
        # transformation (from destination image to source) because we
        # want to interpolate the (discrete) destination pixel from
        # the local area around the (floating) source pixel.

        # The matrix we actually want (note that it operates from the right):
        # (1, 0, tx)   (1, 0, cx)   ( cos a, sin a, 0)   (1, 0, -cx)
        # (0, 1, ty) * (0, 1, cy) * (-sin a, cos a, 0) * (0, 1, -cy)
        # (0, 0,  1)   (0, 0,  1)   (     0,     0, 1)   (0, 0,   1)

        # The reverse matrix is thus:
        # (1, 0, cx)   ( cos -a, sin -a, 0)   (1, 0, -cx)   (1, 0, -tx)
        # (0, 1, cy) * (-sin -a, cos -a, 0) * (0, 1, -cy) * (0, 1, -ty)
        # (0, 0,  1)   (      0,      0, 1)   (0, 0,   1)   (0, 0,   1)

        # In any case, the final translation may be updated at the end to
        # compensate for the expand flag.

        w, h = self.size

        if translate is None:
            post_trans = (0, 0)
        else:
            post_trans = translate
        if center is None:
            center = (w / 2, h / 2)

        angle = -math.radians(angle)
        matrix = [
            round(math.cos(angle), 15),
            round(math.sin(angle), 15),
            0.0,
            round(-math.sin(angle), 15),
            round(math.cos(angle), 15),
            0.0,
        ]

        def transform(x: float, y: float, matrix: list[float]) -> tuple[float, float]:
            (a, b, c, d, e, f) = matrix
            return a * x + b * y + c, d * x + e * y + f

        matrix[2], matrix[5] = transform(
            -center[0] - post_trans[0], -center[1] - post_trans[1], matrix
        )
        matrix[2] += center[0]
        matrix[5] += center[1]

        if expand:
            # calculate output size
            xx = []
            yy = []
            for x, y in ((0, 0), (w, 0), (w, h), (0, h)):
                transformed_x, transformed_y = transform(x, y, matrix)
                xx.append(transformed_x)
                yy.append(transformed_y)
            nw = math.ceil(max(xx)) - math.floor(min(xx))
            nh = math.ceil(max(yy)) - math.floor(min(yy))

            # We multiply a translation matrix from the right.  Because of its
            # special form, this is the same as taking the image of the
            # translation vector as new translation vector.
            matrix[2], matrix[5] = transform(-(nw - w) / 2.0, -(nh - h) / 2.0, matrix)
            w, h = nw, nh

        return self.transform(
            (w, h), Transform.AFFINE, matrix, resample, fillcolor=fillcolor
        )

    def save(
        self, fp: StrOrBytesPath | IO[bytes], format: str | None = None, **params: Any
    ) -> None:
        """
        Saves this image under the given filename.  If no format is
        specified, the format to use is determined from the filename
        extension, if possible.

        Keyword options can be used to provide additional instructions
        to the writer. If a writer doesn't recognise an option, it is
        silently ignored. The available options are described in the
        :doc:`image format documentation
        <../handbook/image-file-formats>` for each writer.

        You can use a file object instead of a filename. In this case,
        you must always specify the format. The file object must
        implement the ``seek``, ``tell``, and ``write``
        methods, and be opened in binary mode.

        :param fp: A filename (string), os.PathLike object or file object.
        :param format: Optional format override.  If omitted, the
           format to use is determined from the filename extension.
           If a file object was used instead of a filename, this
           parameter should always be used.
        :param params: Extra parameters to the image writer. These can also be
           set on the image itself through ``encoderinfo``. This is useful when
           saving multiple images::

             # Saving XMP data to a single image
             from PIL import Image
             red = Image.new("RGB", (1, 1), "#f00")
             red.save("out.mpo", xmp=b"test")

             # Saving XMP data to the second frame of an image
             from PIL import Image
             black = Image.new("RGB", (1, 1))
             red = Image.new("RGB", (1, 1), "#f00")
             red.encoderinfo = {"xmp": b"test"}
             black.save("out.mpo", save_all=True, append_images=[red])
        :returns: None
        :exception ValueError: If the output format could not be determined
           from the file name.  Use the format option to solve this.
        :exception OSError: If the file could not be written.  The file
           may have been created, and may contain partial data.
        """

        filename: str | bytes = ""
        open_fp = False
        if is_path(fp):
            filename = os.fspath(fp)
            open_fp = True
        elif fp == sys.stdout:
            try:
                fp = sys.stdout.buffer
            except AttributeError:
                pass
        if not filename and hasattr(fp, "name") and is_path(fp.name):
            # only set the name for metadata purposes
            filename = os.fspath(fp.name)

        preinit()

        filename_ext = os.path.splitext(filename)[1].lower()
        ext = filename_ext.decode() if isinstance(filename_ext, bytes) else filename_ext

        if not format:
            if ext not in EXTENSION:
                init()
            try:
                format = EXTENSION[ext]
            except KeyError as e:
                msg = f"unknown file extension: {ext}"
                raise ValueError(msg) from e

        from . import ImageFile

        # may mutate self!
        if isinstance(self, ImageFile.ImageFile) and os.path.abspath(
            filename
        ) == os.path.abspath(self.filename):
            self._ensure_mutable()
        else:
            self.load()

        save_all = params.pop("save_all", None)
        self._default_encoderinfo = params
        encoderinfo = getattr(self, "encoderinfo", {})
        self._attach_default_encoderinfo(self)
        self.encoderconfig: tuple[Any, ...] = ()

        if format.upper() not in SAVE:
            init()
        if save_all or (
            save_all is None
            and params.get("append_images")
            and format.upper() in SAVE_ALL
        ):
            save_handler = SAVE_ALL[format.upper()]
        else:
            save_handler = SAVE[format.upper()]

        created = False
        if open_fp:
            created = not os.path.exists(filename)
            if params.get("append", False):
                # Open also for reading ("+"), because TIFF save_all
                # writer needs to go back and edit the written data.
                fp = builtins.open(filename, "r+b")
            else:
                fp = builtins.open(filename, "w+b")
        else:
            fp = cast(IO[bytes], fp)

        try:
            save_handler(self, fp, filename)
        except Exception:
            if open_fp:
                fp.close()
            if created:
                try:
                    os.remove(filename)
                except PermissionError:
                    pass
            raise
        finally:
            self.encoderinfo = encoderinfo
        if open_fp:
            fp.close()

    def _attach_default_encoderinfo(self, im: Image) -> dict[str, Any]:
        encoderinfo = getattr(self, "encoderinfo", {})
        self.encoderinfo = {**im._default_encoderinfo, **encoderinfo}
        return encoderinfo

    def seek(self, frame: int) -> None:
        """
        Seeks to the given frame in this sequence file. If you seek
        beyond the end of the sequence, the method raises an
        ``EOFError`` exception. When a sequence file is opened, the
        library automatically seeks to frame 0.

        See :py:meth:`~PIL.Image.Image.tell`.

        If defined, :attr:`~PIL.Image.Image.n_frames` refers to the
        number of available frames.

        :param frame: Frame number, starting at 0.
        :exception EOFError: If the call attempts to seek beyond the end
            of the sequence.
        """

        # overridden by file handlers
        if frame != 0:
            msg = "no more images in file"
            raise EOFError(msg)

    def show(self, title: str | None = None) -> None:
        """
        Displays this image. This method is mainly intended for debugging purposes.

        This method calls :py:func:`PIL.ImageShow.show` internally. You can use
        :py:func:`PIL.ImageShow.register` to override its default behaviour.

        The image is first saved to a temporary file. By default, it will be in
        PNG format.

        On Unix, the image is then opened using the **xdg-open**, **display**,
        **gm**, **eog** or **xv** utility, depending on which one can be found.

        On macOS, the image is opened with the native Preview application.

        On Windows, the image is opened with the standard PNG display utility.

        :param title: Optional title to use for the image window, where possible.
        """

        _show(self, title=title)

    def split(self) -> tuple[Image, ...]:
        """
        Split this image into individual bands. This method returns a
        tuple of individual image bands from an image. For example,
        splitting an "RGB" image creates three new images each
        containing a copy of one of the original bands (red, green,
        blue).

        If you need only one band, :py:meth:`~PIL.Image.Image.getchannel`
        method can be more convenient and faster.

        :returns: A tuple containing bands.
        """

        self.load()
        if self.im.bands == 1:
            return (self.copy(),)
        return tuple(map(self._new, self.im.split()))

    def getchannel(self, channel: int | str) -> Image:
        """
        Returns an image containing a single channel of the source image.

        :param channel: What channel to return. Could be index
          (0 for "R" channel of "RGB") or channel name
          ("A" for alpha channel of "RGBA").
        :returns: An image in "L" mode.

        .. versionadded:: 4.3.0
        """
        self.load()

        if isinstance(channel, str):
            try:
                channel = self.getbands().index(channel)
            except ValueError as e:
                msg = f'The image has no channel "{channel}"'
                raise ValueError(msg) from e

        return self._new(self.im.getband(channel))

    def tell(self) -> int:
        """
        Returns the current frame number. See :py:meth:`~PIL.Image.Image.seek`.

        If defined, :attr:`~PIL.Image.Image.n_frames` refers to the
        number of available frames.

        :returns: Frame number, starting with 0.
        """
        return 0

    def thumbnail(
        self,
        size: tuple[float, float],
        resample: Resampling = Resampling.BICUBIC,
        reducing_gap: float | None = 2.0,
    ) -> None:
        """
        Make this image into a thumbnail.  This method modifies the
        image to contain a thumbnail version of itself, no larger than
        the given size.  This method calculates an appropriate thumbnail
        size to preserve the aspect of the image, calls the
        :py:meth:`~PIL.Image.Image.draft` method to configure the file reader
        (where applicable), and finally resizes the image.

        Note that this function modifies the :py:class:`~PIL.Image.Image`
        object in place.  If you need to use the full resolution image as well,
        apply this method to a :py:meth:`~PIL.Image.Image.copy` of the original
        image.

        :param size: The requested size in pixels, as a 2-tuple:
           (width, height).
        :param resample: Optional resampling filter.  This can be one
           of :py:data:`Resampling.NEAREST`, :py:data:`Resampling.BOX`,
           :py:data:`Resampling.BILINEAR`, :py:data:`Resampling.HAMMING`,
           :py:data:`Resampling.BICUBIC` or :py:data:`Resampling.LANCZOS`.
           If omitted, it defaults to :py:data:`Resampling.BICUBIC`.
           (was :py:data:`Resampling.NEAREST` prior to version 2.5.0).
           See: :ref:`concept-filters`.
        :param reducing_gap: Apply optimization by resizing the image
           in two steps. First, reducing the image by integer times
           using :py:meth:`~PIL.Image.Image.reduce` or
           :py:meth:`~PIL.Image.Image.draft` for JPEG images.
           Second, resizing using regular resampling. The last step
           changes size no less than by ``reducing_gap`` times.
           ``reducing_gap`` may be None (no first step is performed)
           or should be greater than 1.0. The bigger ``reducing_gap``,
           the closer the result to the fair resampling.
           The smaller ``reducing_gap``, the faster resizing.
           With ``reducing_gap`` greater or equal to 3.0, the result is
           indistinguishable from fair resampling in most cases.
           The default value is 2.0 (very close to fair resampling
           while still being faster in many cases).
        :returns: None
        """

        provided_size = tuple(map(math.floor, size))

        def preserve_aspect_ratio() -> tuple[int, int] | None:
            def round_aspect(number: float, key: Callable[[int], float]) -> int:
                return max(min(math.floor(number), math.ceil(number), key=key), 1)

            x, y = provided_size
            if x >= self.width and y >= self.height:
                return None

            aspect = self.width / self.height
            if x / y >= aspect:
                x = round_aspect(y * aspect, key=lambda n: abs(aspect - n / y))
            else:
                y = round_aspect(
                    x / aspect, key=lambda n: 0 if n == 0 else abs(aspect - x / n)
                )
            return x, y

        preserved_size = preserve_aspect_ratio()
        if preserved_size is None:
            return
        final_size = preserved_size

        box = None
        if reducing_gap is not None:
            res = self.draft(
                None, (int(size[0] * reducing_gap), int(size[1] * reducing_gap))
            )
            if res is not None:
                box = res[1]

        if self.size != final_size:
            im = self.resize(final_size, resample, box=box, reducing_gap=reducing_gap)

            self.im = im.im
            self._size = final_size
            self._mode = self.im.mode

        self.readonly = 0

    # FIXME: the different transform methods need further explanation
    # instead of bloating the method docs, add a separate chapter.
    def transform(
        self,
        size: tuple[int, int],
        method: Transform | ImageTransformHandler | SupportsGetData,
        data: Sequence[Any] | None = None,
        resample: int = Resampling.NEAREST,
        fill: int = 1,
        fillcolor: float | tuple[float, ...] | str | None = None,
    ) -> Image:
        """
        Transforms this image.  This method creates a new image with the
        given size, and the same mode as the original, and copies data
        to the new image using the given transform.

        :param size: The output size in pixels, as a 2-tuple:
           (width, height).
        :param method: The transformation method.  This is one of
          :py:data:`Transform.EXTENT` (cut out a rectangular subregion),
          :py:data:`Transform.AFFINE` (affine transform),
          :py:data:`Transform.PERSPECTIVE` (perspective transform),
          :py:data:`Transform.QUAD` (map a quadrilateral to a rectangle), or
          :py:data:`Transform.MESH` (map a number of source quadrilaterals
          in one operation).

          It may also be an :py:class:`~PIL.Image.ImageTransformHandler`
          object::

            class Example(Image.ImageTransformHandler):
                def transform(self, size, data, resample, fill=1):
                    # Return result

          Implementations of :py:class:`~PIL.Image.ImageTransformHandler`
          for some of the :py:class:`Transform` methods are provided
          in :py:mod:`~PIL.ImageTransform`.

          It may also be an object with a ``method.getdata`` method
          that returns a tuple supplying new ``method`` and ``data`` values::

            class Example:
                def getdata(self):
                    method = Image.Transform.EXTENT
                    data = (0, 0, 100, 100)
                    return method, data
        :param data: Extra data to the transformation method.
        :param resample: Optional resampling filter.  It can be one of
           :py:data:`Resampling.NEAREST` (use nearest neighbour),
           :py:data:`Resampling.BILINEAR` (linear interpolation in a 2x2
           environment), or :py:data:`Resampling.BICUBIC` (cubic spline
           interpolation in a 4x4 environment). If omitted, or if the image
           has mode "1" or "P", it is set to :py:data:`Resampling.NEAREST`.
           See: :ref:`concept-filters`.
        :param fill: If ``method`` is an
          :py:class:`~PIL.Image.ImageTransformHandler` object, this is one of
          the arguments passed to it. Otherwise, it is unused.
        :param fillcolor: Optional fill color for the area outside the
           transform in the output image.
        :returns: An :py:class:`~PIL.Image.Image` object.
        """

        if self.mode in ("LA", "RGBA") and resample != Resampling.NEAREST:
            return (
                self.convert({"LA": "La", "RGBA": "RGBa"}[self.mode])
                .transform(size, method, data, resample, fill, fillcolor)
                .convert(self.mode)
            )

        if isinstance(method, ImageTransformHandler):
            return method.transform(size, self, resample=resample, fill=fill)

        if hasattr(method, "getdata"):
            # compatibility w. old-style transform objects
            method, data = method.getdata()

        if data is None:
            msg = "missing method data"
            raise ValueError(msg)

        im = new(self.mode, size, fillcolor)
        if self.mode == "P" and self.palette:
            im.palette = self.palette.copy()
        im.info = self.info.copy()
        if method == Transform.MESH:
            # list of quads
            for box, quad in data:
                im.__transformer(
                    box, self, Transform.QUAD, quad, resample, fillcolor is None
                )
        else:
            im.__transformer(
                (0, 0) + size, self, method, data, resample, fillcolor is None
            )

        return im

    def __transformer(
        self,
        box: tuple[int, int, int, int],
        image: Image,
        method: Transform,
        data: Sequence[float],
        resample: int = Resampling.NEAREST,
        fill: bool = True,
    ) -> None:
        w = box[2] - box[0]
        h = box[3] - box[1]

        if method == Transform.AFFINE:
            data = data[:6]

        elif method == Transform.EXTENT:
            # convert extent to an affine transform
            x0, y0, x1, y1 = data
            xs = (x1 - x0) / w
            ys = (y1 - y0) / h
            method = Transform.AFFINE
            data = (xs, 0, x0, 0, ys, y0)

        elif method == Transform.PERSPECTIVE:
            data = data[:8]

        elif method == Transform.QUAD:
            # quadrilateral warp.  data specifies the four corners
            # given as NW, SW, SE, and NE.
            nw = data[:2]
            sw = data[2:4]
            se = data[4:6]
            ne = data[6:8]
            x0, y0 = nw
            As = 1.0 / w
            At = 1.0 / h
            data = (
                x0,
                (ne[0] - x0) * As,
                (sw[0] - x0) * At,
                (se[0] - sw[0] - ne[0] + x0) * As * At,
                y0,
                (ne[1] - y0) * As,
                (sw[1] - y0) * At,
                (se[1] - sw[1] - ne[1] + y0) * As * At,
            )

        else:
            msg = "unknown transformation method"
            raise ValueError(msg)

        if resample not in (
            Resampling.NEAREST,
            Resampling.BILINEAR,
            Resampling.BICUBIC,
        ):
            if resample in (Resampling.BOX, Resampling.HAMMING, Resampling.LANCZOS):
                unusable: dict[int, str] = {
                    Resampling.BOX: "Image.Resampling.BOX",
                    Resampling.HAMMING: "Image.Resampling.HAMMING",
                    Resampling.LANCZOS: "Image.Resampling.LANCZOS",
                }
                msg = unusable[resample] + f" ({resample}) cannot be used."
            else:
                msg = f"Unknown resampling filter ({resample})."

            filters = [
                f"{filter[1]} ({filter[0]})"
                for filter in (
                    (Resampling.NEAREST, "Image.Resampling.NEAREST"),
                    (Resampling.BILINEAR, "Image.Resampling.BILINEAR"),
                    (Resampling.BICUBIC, "Image.Resampling.BICUBIC"),
                )
            ]
            msg += f" Use {', '.join(filters[:-1])} or {filters[-1]}"
            raise ValueError(msg)

        image.load()

        self.load()

        if image.mode in ("1", "P"):
            resample = Resampling.NEAREST

        self.im.transform(box, image.im, method, data, resample, fill)

    def transpose(self, method: Transpose) -> Image:
        """
        Transpose image (flip or rotate in 90 degree steps)

        :param method: One of :py:data:`Transpose.FLIP_LEFT_RIGHT`,
          :py:data:`Transpose.FLIP_TOP_BOTTOM`, :py:data:`Transpose.ROTATE_90`,
          :py:data:`Transpose.ROTATE_180`, :py:data:`Transpose.ROTATE_270`,
          :py:data:`Transpose.TRANSPOSE` or :py:data:`Transpose.TRANSVERSE`.
        :returns: Returns a flipped or rotated copy of this image.
        """

        self.load()
        return self._new(self.im.transpose(method))

    def effect_spread(self, distance: int) -> Image:
        """
        Randomly spread pixels in an image.

        :param distance: Distance to spread pixels.
        """
        self.load()
        return self._new(self.im.effect_spread(distance))

    def toqimage(self) -> ImageQt.ImageQt:
        """Returns a QImage copy of this image"""
        from . import ImageQt

        if not ImageQt.qt_is_installed:
            msg = "Qt bindings are not installed"
            raise ImportError(msg)
        return ImageQt.toqimage(self)

    def toqpixmap(self) -> ImageQt.QPixmap:
        """Returns a QPixmap copy of this image"""
        from . import ImageQt

        if not ImageQt.qt_is_installed:
            msg = "Qt bindings are not installed"
            raise ImportError(msg)
        return ImageQt.toqpixmap(self)


# --------------------------------------------------------------------
# Abstract handlers.


class ImagePointHandler(abc.ABC):
    """
    Used as a mixin by point transforms
    (for use with :py:meth:`~PIL.Image.Image.point`)
    """

    @abc.abstractmethod
    def point(self, im: Image) -> Image:
        pass


class ImageTransformHandler(abc.ABC):
    """
    Used as a mixin by geometry transforms
    (for use with :py:meth:`~PIL.Image.Image.transform`)
    """

    @abc.abstractmethod
    def transform(
        self,
        size: tuple[int, int],
        image: Image,
        **options: Any,
    ) -> Image:
        pass


# --------------------------------------------------------------------
# Factories


def _check_size(size: Any) -> None:
    """
    Common check to enforce type and sanity check on size tuples

    :param size: Should be a 2 tuple of (width, height)
    :returns: None, or raises a ValueError
    """

    if not isinstance(size, (list, tuple)):
        msg = "Size must be a list or tuple"
        raise ValueError(msg)
    if len(size) != 2:
        msg = "Size must be a sequence of length 2"
        raise ValueError(msg)
    if size[0] < 0 or size[1] < 0:
        msg = "Width and height must be >= 0"
        raise ValueError(msg)


def new(
    mode: str,
    size: tuple[int, int] | list[int],
    color: float | tuple[float, ...] | str | None = 0,
) -> Image:
    """
    Creates a new image with the given mode and size.

    :param mode: The mode to use for the new image. See:
       :ref:`concept-modes`.
    :param size: A 2-tuple, containing (width, height) in pixels.
    :param color: What color to use for the image.  Default is black.
       If given, this should be a single integer or floating point value
       for single-band modes, and a tuple for multi-band modes (one value
       per band).  When creating RGB or HSV images, you can also use color
       strings as supported by the ImageColor module.  If the color is
       None, the image is not initialised.
    :returns: An :py:class:`~PIL.Image.Image` object.
    """

    if mode in ("BGR;15", "BGR;16", "BGR;24"):
        deprecate(mode, 12)

    _check_size(size)

    if color is None:
        # don't initialize
        return Image()._new(core.new(mode, size))

    if isinstance(color, str):
        # css3-style specifier

        from . import ImageColor

        color = ImageColor.getcolor(color, mode)

    im = Image()
    if (
        mode == "P"
        and isinstance(color, (list, tuple))
        and all(isinstance(i, int) for i in color)
    ):
        color_ints: tuple[int, ...] = cast(tuple[int, ...], tuple(color))
        if len(color_ints) == 3 or len(color_ints) == 4:
            # RGB or RGBA value for a P image
            from . import ImagePalette

            im.palette = ImagePalette.ImagePalette()
            color = im.palette.getcolor(color_ints)
    return im._new(core.fill(mode, size, color))


def frombytes(
    mode: str,
    size: tuple[int, int],
    data: bytes | bytearray | SupportsArrayInterface,
    decoder_name: str = "raw",
    *args: Any,
) -> Image:
    """
    Creates a copy of an image memory from pixel data in a buffer.

    In its simplest form, this function takes three arguments
    (mode, size, and unpacked pixel data).

    You can also use any pixel decoder supported by PIL. For more
    information on available decoders, see the section
    :ref:`Writing Your Own File Codec <file-codecs>`.

    Note that this function decodes pixel data only, not entire images.
    If you have an entire image in a string, wrap it in a
    :py:class:`~io.BytesIO` object, and use :py:func:`~PIL.Image.open` to load
    it.

    :param mode: The image mode. See: :ref:`concept-modes`.
    :param size: The image size.
    :param data: A byte buffer containing raw data for the given mode.
    :param decoder_name: What decoder to use.
    :param args: Additional parameters for the given decoder.
    :returns: An :py:class:`~PIL.Image.Image` object.
    """

    _check_size(size)

    im = new(mode, size)
    if im.width != 0 and im.height != 0:
        decoder_args: Any = args
        if len(decoder_args) == 1 and isinstance(decoder_args[0], tuple):
            # may pass tuple instead of argument list
            decoder_args = decoder_args[0]

        if decoder_name == "raw" and decoder_args == ():
            decoder_args = mode

        im.frombytes(data, decoder_name, decoder_args)
    return im


def frombuffer(
    mode: str,
    size: tuple[int, int],
    data: bytes | SupportsArrayInterface,
    decoder_name: str = "raw",
    *args: Any,
) -> Image:
    """
    Creates an image memory referencing pixel data in a byte buffer.

    This function is similar to :py:func:`~PIL.Image.frombytes`, but uses data
    in the byte buffer, where possible.  This means that changes to the
    original buffer object are reflected in this image).  Not all modes can
    share memory; supported modes include "L", "RGBX", "RGBA", and "CMYK".

    Note that this function decodes pixel data only, not entire images.
    If you have an entire image file in a string, wrap it in a
    :py:class:`~io.BytesIO` object, and use :py:func:`~PIL.Image.open` to load it.

    The default parameters used for the "raw" decoder differs from that used for
    :py:func:`~PIL.Image.frombytes`. This is a bug, and will probably be fixed in a
    future release. The current release issues a warning if you do this; to disable
    the warning, you should provide the full set of parameters. See below for details.

    :param mode: The image mode. See: :ref:`concept-modes`.
    :param size: The image size.
    :param data: A bytes or other buffer object containing raw
        data for the given mode.
    :param decoder_name: What decoder to use.
    :param args: Additional parameters for the given decoder.  For the
        default encoder ("raw"), it's recommended that you provide the
        full set of parameters::

            frombuffer(mode, size, data, "raw", mode, 0, 1)

    :returns: An :py:class:`~PIL.Image.Image` object.

    .. versionadded:: 1.1.4
    """

    _check_size(size)

    # may pass tuple instead of argument list
    if len(args) == 1 and isinstance(args[0], tuple):
        args = args[0]

    if decoder_name == "raw":
        if args == ():
            args = mode, 0, 1
        if args[0] in _MAPMODES:
            im = new(mode, (0, 0))
            im = im._new(core.map_buffer(data, size, decoder_name, 0, args))
            if mode == "P":
                from . import ImagePalette

                im.palette = ImagePalette.ImagePalette("RGB", im.im.getpalette("RGB"))
            im.readonly = 1
            return im

    return frombytes(mode, size, data, decoder_name, args)


class SupportsArrayInterface(Protocol):
    """
    An object that has an ``__array_interface__`` dictionary.
    """

    @property
    def __array_interface__(self) -> dict[str, Any]:
        raise NotImplementedError()


class SupportsArrowArrayInterface(Protocol):
    """
    An object that has an ``__arrow_c_array__`` method corresponding to the arrow c
    data interface.
    """

    def __arrow_c_array__(
        self, requested_schema: "PyCapsule" = None  # type: ignore[name-defined]  # noqa: F821, UP037
    ) -> tuple["PyCapsule", "PyCapsule"]:  # type: ignore[name-defined]  # noqa: F821, UP037
        raise NotImplementedError()


def fromarray(obj: SupportsArrayInterface, mode: str | None = None) -> Image:
    """
    Creates an image memory from an object exporting the array interface
    (using the buffer protocol)::

      from PIL import Image
      import numpy as np
      a = np.zeros((5, 5))
      im = Image.fromarray(a)

    If ``obj`` is not contiguous, then the ``tobytes`` method is called
    and :py:func:`~PIL.Image.frombuffer` is used.

    In the case of NumPy, be aware that Pillow modes do not always correspond
    to NumPy dtypes. Pillow modes only offer 1-bit pixels, 8-bit pixels,
    32-bit signed integer pixels, and 32-bit floating point pixels.

    Pillow images can also be converted to arrays::

      from PIL import Image
      import numpy as np
      im = Image.open("hopper.jpg")
      a = np.asarray(im)

    When converting Pillow images to arrays however, only pixel values are
    transferred. This means that P and PA mode images will lose their palette.

    :param obj: Object with array interface
    :param mode: Optional mode to use when reading ``obj``. Will be determined from
      type if ``None``. Deprecated.

      This will not be used to convert the data after reading, but will be used to
      change how the data is read::

        from PIL import Image
        import numpy as np
        a = np.full((1, 1), 300)
        im = Image.fromarray(a, mode="L")
        im.getpixel((0, 0))  # 44
        im = Image.fromarray(a, mode="RGB")
        im.getpixel((0, 0))  # (44, 1, 0)

      See: :ref:`concept-modes` for general information about modes.
    :returns: An image object.

    .. versionadded:: 1.1.6
    """
    arr = obj.__array_interface__
    shape = arr["shape"]
    ndim = len(shape)
    strides = arr.get("strides", None)
    if mode is None:
        try:
            typekey = (1, 1) + shape[2:], arr["typestr"]
        except KeyError as e:
            msg = "Cannot handle this data type"
            raise TypeError(msg) from e
        try:
            mode, rawmode = _fromarray_typemap[typekey]
        except KeyError as e:
            typekey_shape, typestr = typekey
            msg = f"Cannot handle this data type: {typekey_shape}, {typestr}"
            raise TypeError(msg) from e
    else:
        deprecate("'mode' parameter", 13)
        rawmode = mode
    if mode in ["1", "L", "I", "P", "F"]:
        ndmax = 2
    elif mode == "RGB":
        ndmax = 3
    else:
        ndmax = 4
    if ndim > ndmax:
        msg = f"Too many dimensions: {ndim} > {ndmax}."
        raise ValueError(msg)

    size = 1 if ndim == 1 else shape[1], shape[0]
    if strides is not None:
        if hasattr(obj, "tobytes"):
            obj = obj.tobytes()
        elif hasattr(obj, "tostring"):
            obj = obj.tostring()
        else:
            msg = "'strides' requires either tobytes() or tostring()"
            raise ValueError(msg)

    return frombuffer(mode, size, obj, "raw", rawmode, 0, 1)


def fromarrow(
    obj: SupportsArrowArrayInterface, mode: str, size: tuple[int, int]
) -> Image:
    """Creates an image with zero-copy shared memory from an object exporting
    the arrow_c_array interface protocol::

      from PIL import Image
      import pyarrow as pa
      arr = pa.array([0]*(5*5*4), type=pa.uint8())
      im = Image.fromarrow(arr, 'RGBA', (5, 5))

    If the data representation of the ``obj`` is not compatible with
    Pillow internal storage, a ValueError is raised.

    Pillow images can also be converted to Arrow objects::

      from PIL import Image
      import pyarrow as pa
      im = Image.open('hopper.jpg')
      arr = pa.array(im)

    As with array support, when converting Pillow images to arrays,
    only pixel values are transferred. This means that P and PA mode
    images will lose their palette.

    :param obj: Object with an arrow_c_array interface
    :param mode: Image mode.
    :param size: Image size. This must match the storage of the arrow object.
    :returns: An Image object

    Note that according to the Arrow spec, both the producer and the
    consumer should consider the exported array to be immutable, as
    unsynchronized updates will potentially cause inconsistent data.

    See: :ref:`arrow-support` for more detailed information

    .. versionadded:: 11.2.1

    """
    if not hasattr(obj, "__arrow_c_array__"):
        msg = "arrow_c_array interface not found"
        raise ValueError(msg)

    (schema_capsule, array_capsule) = obj.__arrow_c_array__()
    _im = core.new_arrow(mode, size, schema_capsule, array_capsule)
    if _im:
        return Image()._new(_im)

    msg = "new_arrow returned None without an exception"
    raise ValueError(msg)


def fromqimage(im: ImageQt.QImage) -> ImageFile.ImageFile:
    """Creates an image instance from a QImage image"""
    from . import ImageQt

    if not ImageQt.qt_is_installed:
        msg = "Qt bindings are not installed"
        raise ImportError(msg)
    return ImageQt.fromqimage(im)


def fromqpixmap(im: ImageQt.QPixmap) -> ImageFile.ImageFile:
    """Creates an image instance from a QPixmap image"""
    from . import ImageQt

    if not ImageQt.qt_is_installed:
        msg = "Qt bindings are not installed"
        raise ImportError(msg)
    return ImageQt.fromqpixmap(im)


_fromarray_typemap = {
    # (shape, typestr) => mode, rawmode
    # first two members of shape are set to one
    ((1, 1), "|b1"): ("1", "1;8"),
    ((1, 1), "|u1"): ("L", "L"),
    ((1, 1), "|i1"): ("I", "I;8"),
    ((1, 1), "<u2"): ("I", "I;16"),
    ((1, 1), ">u2"): ("I", "I;16B"),
    ((1, 1), "<i2"): ("I", "I;16S"),
    ((1, 1), ">i2"): ("I", "I;16BS"),
    ((1, 1), "<u4"): ("I", "I;32"),
    ((1, 1), ">u4"): ("I", "I;32B"),
    ((1, 1), "<i4"): ("I", "I;32S"),
    ((1, 1), ">i4"): ("I", "I;32BS"),
    ((1, 1), "<f4"): ("F", "F;32F"),
    ((1, 1), ">f4"): ("F", "F;32BF"),
    ((1, 1), "<f8"): ("F", "F;64F"),
    ((1, 1), ">f8"): ("F", "F;64BF"),
    ((1, 1, 2), "|u1"): ("LA", "LA"),
    ((1, 1, 3), "|u1"): ("RGB", "RGB"),
    ((1, 1, 4), "|u1"): ("RGBA", "RGBA"),
    # shortcuts:
    ((1, 1), f"{_ENDIAN}i4"): ("I", "I"),
    ((1, 1), f"{_ENDIAN}f4"): ("F", "F"),
}


def _decompression_bomb_check(size: tuple[int, int]) -> None:
    if MAX_IMAGE_PIXELS is None:
        return

    pixels = max(1, size[0]) * max(1, size[1])

    if pixels > 2 * MAX_IMAGE_PIXELS:
        msg = (
            f"Image size ({pixels} pixels) exceeds limit of {2 * MAX_IMAGE_PIXELS} "
            "pixels, could be decompression bomb DOS attack."
        )
        raise DecompressionBombError(msg)

    if pixels > MAX_IMAGE_PIXELS:
        warnings.warn(
            f"Image size ({pixels} pixels) exceeds limit of {MAX_IMAGE_PIXELS} pixels, "
            "could be decompression bomb DOS attack.",
            DecompressionBombWarning,
        )


def open(
    fp: StrOrBytesPath | IO[bytes],
    mode: Literal["r"] = "r",
    formats: list[str] | tuple[str, ...] | None = None,
) -> ImageFile.ImageFile:
    """
    Opens and identifies the given image file.

    This is a lazy operation; this function identifies the file, but
    the file remains open and the actual image data is not read from
    the file until you try to process the data (or call the
    :py:meth:`~PIL.Image.Image.load` method).  See
    :py:func:`~PIL.Image.new`. See :ref:`file-handling`.

    :param fp: A filename (string), os.PathLike object or a file object.
       The file object must implement ``file.read``,
       ``file.seek``, and ``file.tell`` methods,
       and be opened in binary mode. The file object will also seek to zero
       before reading.
    :param mode: The mode.  If given, this argument must be "r".
    :param formats: A list or tuple of formats to attempt to load the file in.
       This can be used to restrict the set of formats checked.
       Pass ``None`` to try all supported formats. You can print the set of
       available formats by running ``python3 -m PIL`` or using
       the :py:func:`PIL.features.pilinfo` function.
    :returns: An :py:class:`~PIL.Image.Image` object.
    :exception FileNotFoundError: If the file cannot be found.
    :exception PIL.UnidentifiedImageError: If the image cannot be opened and
       identified.
    :exception ValueError: If the ``mode`` is not "r", or if a ``StringIO``
       instance is used for ``fp``.
    :exception TypeError: If ``formats`` is not ``None``, a list or a tuple.
    """

    if mode != "r":
        msg = f"bad mode {repr(mode)}"  # type: ignore[unreachable]
        raise ValueError(msg)
    elif isinstance(fp, io.StringIO):
        msg = (  # type: ignore[unreachable]
            "StringIO cannot be used to open an image. "
            "Binary data must be used instead."
        )
        raise ValueError(msg)

    if formats is None:
        formats = ID
    elif not isinstance(formats, (list, tuple)):
        msg = "formats must be a list or tuple"  # type: ignore[unreachable]
        raise TypeError(msg)

    exclusive_fp = False
    filename: str | bytes = ""
    if is_path(fp):
        filename = os.fspath(fp)
        fp = builtins.open(filename, "rb")
        exclusive_fp = True
    else:
        fp = cast(IO[bytes], fp)

    try:
        fp.seek(0)
    except (AttributeError, io.UnsupportedOperation):
        fp = io.BytesIO(fp.read())
        exclusive_fp = True

    prefix = fp.read(16)

    preinit()

    warning_messages: list[str] = []

    def _open_core(
        fp: IO[bytes],
        filename: str | bytes,
        prefix: bytes,
        formats: list[str] | tuple[str, ...],
    ) -> ImageFile.ImageFile | None:
        for i in formats:
            i = i.upper()
            if i not in OPEN:
                init()
            try:
                factory, accept = OPEN[i]
                result = not accept or accept(prefix)
                if isinstance(result, str):
                    warning_messages.append(result)
                elif result:
                    fp.seek(0)
                    im = factory(fp, filename)
                    _decompression_bomb_check(im.size)
                    return im
            except (SyntaxError, IndexError, TypeError, struct.error) as e:
                if WARN_POSSIBLE_FORMATS:
                    warning_messages.append(i + " opening failed. " + str(e))
            except BaseException:
                if exclusive_fp:
                    fp.close()
                raise
        return None

    im = _open_core(fp, filename, prefix, formats)

    if im is None and formats is ID:
        checked_formats = ID.copy()
        if init():
            im = _open_core(
                fp,
                filename,
                prefix,
                tuple(format for format in formats if format not in checked_formats),
            )

    if im:
        im._exclusive_fp = exclusive_fp
        return im

    if exclusive_fp:
        fp.close()
    for message in warning_messages:
        warnings.warn(message)
    msg = "cannot identify image file %r" % (filename if filename else fp)
    raise UnidentifiedImageError(msg)


#
# Image processing.


def alpha_composite(im1: Image, im2: Image) -> Image:
    """
    Alpha composite im2 over im1.

    :param im1: The first image. Must have mode RGBA.
    :param im2: The second image.  Must have mode RGBA, and the same size as
       the first image.
    :returns: An :py:class:`~PIL.Image.Image` object.
    """

    im1.load()
    im2.load()
    return im1._new(core.alpha_composite(im1.im, im2.im))


def blend(im1: Image, im2: Image, alpha: float) -> Image:
    """
    Creates a new image by interpolating between two input images, using
    a constant alpha::

        out = image1 * (1.0 - alpha) + image2 * alpha

    :param im1: The first image.
    :param im2: The second image.  Must have the same mode and size as
       the first image.
    :param alpha: The interpolation alpha factor.  If alpha is 0.0, a
       copy of the first image is returned. If alpha is 1.0, a copy of
       the second image is returned. There are no restrictions on the
       alpha value. If necessary, the result is clipped to fit into
       the allowed output range.
    :returns: An :py:class:`~PIL.Image.Image` object.
    """

    im1.load()
    im2.load()
    return im1._new(core.blend(im1.im, im2.im, alpha))


def composite(image1: Image, image2: Image, mask: Image) -> Image:
    """
    Create composite image by blending images using a transparency mask.

    :param image1: The first image.
    :param image2: The second image.  Must have the same mode and
       size as the first image.
    :param mask: A mask image.  This image can have mode
       "1", "L", or "RGBA", and must have the same size as the
       other two images.
    """

    image = image2.copy()
    image.paste(image1, None, mask)
    return image


def eval(image: Image, *args: Callable[[int], float]) -> Image:
    """
    Applies the function (which should take one argument) to each pixel
    in the given image. If the image has more than one band, the same
    function is applied to each band. Note that the function is
    evaluated once for each possible pixel value, so you cannot use
    random components or other generators.

    :param image: The input image.
    :param function: A function object, taking one integer argument.
    :returns: An :py:class:`~PIL.Image.Image` object.
    """

    return image.point(args[0])


def merge(mode: str, bands: Sequence[Image]) -> Image:
    """
    Merge a set of single band images into a new multiband image.

    :param mode: The mode to use for the output image. See:
        :ref:`concept-modes`.
    :param bands: A sequence containing one single-band image for
        each band in the output image.  All bands must have the
        same size.
    :returns: An :py:class:`~PIL.Image.Image` object.
    """

    if getmodebands(mode) != len(bands) or "*" in mode:
        msg = "wrong number of bands"
        raise ValueError(msg)
    for band in bands[1:]:
        if band.mode != getmodetype(mode):
            msg = "mode mismatch"
            raise ValueError(msg)
        if band.size != bands[0].size:
            msg = "size mismatch"
            raise ValueError(msg)
    for band in bands:
        band.load()
    return bands[0]._new(core.merge(mode, *[b.im for b in bands]))


# --------------------------------------------------------------------
# Plugin registry


def register_open(
    id: str,
    factory: (
        Callable[[IO[bytes], str | bytes], ImageFile.ImageFile]
        | type[ImageFile.ImageFile]
    ),
    accept: Callable[[bytes], bool | str] | None = None,
) -> None:
    """
    Register an image file plugin.  This function should not be used
    in application code.

    :param id: An image format identifier.
    :param factory: An image file factory method.
    :param accept: An optional function that can be used to quickly
       reject images having another format.
    """
    id = id.upper()
    if id not in ID:
        ID.append(id)
    OPEN[id] = factory, accept


def register_mime(id: str, mimetype: str) -> None:
    """
    Registers an image MIME type by populating ``Image.MIME``. This function
    should not be used in application code.

    ``Image.MIME`` provides a mapping from image format identifiers to mime
    formats, but :py:meth:`~PIL.ImageFile.ImageFile.get_format_mimetype` can
    provide a different result for specific images.

    :param id: An image format identifier.
    :param mimetype: The image MIME type for this format.
    """
    MIME[id.upper()] = mimetype


def register_save(
    id: str, driver: Callable[[Image, IO[bytes], str | bytes], None]
) -> None:
    """
    Registers an image save function.  This function should not be
    used in application code.

    :param id: An image format identifier.
    :param driver: A function to save images in this format.
    """
    SAVE[id.upper()] = driver


def register_save_all(
    id: str, driver: Callable[[Image, IO[bytes], str | bytes], None]
) -> None:
    """
    Registers an image function to save all the frames
    of a multiframe format.  This function should not be
    used in application code.

    :param id: An image format identifier.
    :param driver: A function to save images in this format.
    """
    SAVE_ALL[id.upper()] = driver


def register_extension(id: str, extension: str) -> None:
    """
    Registers an image extension.  This function should not be
    used in application code.

    :param id: An image format identifier.
    :param extension: An extension used for this format.
    """
    EXTENSION[extension.lower()] = id.upper()


def register_extensions(id: str, extensions: list[str]) -> None:
    """
    Registers image extensions.  This function should not be
    used in application code.

    :param id: An image format identifier.
    :param extensions: A list of extensions used for this format.
    """
    for extension in extensions:
        register_extension(id, extension)


def registered_extensions() -> dict[str, str]:
    """
    Returns a dictionary containing all file extensions belonging
    to registered plugins
    """
    init()
    return EXTENSION


def register_decoder(name: str, decoder: type[ImageFile.PyDecoder]) -> None:
    """
    Registers an image decoder.  This function should not be
    used in application code.

    :param name: The name of the decoder
    :param decoder: An ImageFile.PyDecoder object

    .. versionadded:: 4.1.0
    """
    DECODERS[name] = decoder


def register_encoder(name: str, encoder: type[ImageFile.PyEncoder]) -> None:
    """
    Registers an image encoder.  This function should not be
    used in application code.

    :param name: The name of the encoder
    :param encoder: An ImageFile.PyEncoder object

    .. versionadded:: 4.1.0
    """
    ENCODERS[name] = encoder


# --------------------------------------------------------------------
# Simple display support.


def _show(image: Image, **options: Any) -> None:
    from . import ImageShow

    ImageShow.show(image, **options)


# --------------------------------------------------------------------
# Effects


def effect_mandelbrot(
    size: tuple[int, int], extent: tuple[float, float, float, float], quality: int
) -> Image:
    """
    Generate a Mandelbrot set covering the given extent.

    :param size: The requested size in pixels, as a 2-tuple:
       (width, height).
    :param extent: The extent to cover, as a 4-tuple:
       (x0, y0, x1, y1).
    :param quality: Quality.
    """
    return Image()._new(core.effect_mandelbrot(size, extent, quality))


def effect_noise(size: tuple[int, int], sigma: float) -> Image:
    """
    Generate Gaussian noise centered around 128.

    :param size: The requested size in pixels, as a 2-tuple:
       (width, height).
    :param sigma: Standard deviation of noise.
    """
    return Image()._new(core.effect_noise(size, sigma))


def linear_gradient(mode: str) -> Image:
    """
    Generate 256x256 linear gradient from black to white, top to bottom.

    :param mode: Input mode.
    """
    return Image()._new(core.linear_gradient(mode))


def radial_gradient(mode: str) -> Image:
    """
    Generate 256x256 radial gradient from black to white, centre to edge.

    :param mode: Input mode.
    """
    return Image()._new(core.radial_gradient(mode))


# --------------------------------------------------------------------
# Resources


def _apply_env_variables(env: dict[str, str] | None = None) -> None:
    env_dict = env if env is not None else os.environ

    for var_name, setter in [
        ("PILLOW_ALIGNMENT", core.set_alignment),
        ("PILLOW_BLOCK_SIZE", core.set_block_size),
        ("PILLOW_BLOCKS_MAX", core.set_blocks_max),
    ]:
        if var_name not in env_dict:
            continue

        var = env_dict[var_name].lower()

        units = 1
        for postfix, mul in [("k", 1024), ("m", 1024 * 1024)]:
            if var.endswith(postfix):
                units = mul
                var = var[: -len(postfix)]

        try:
            var_int = int(var) * units
        except ValueError:
            warnings.warn(f"{var_name} is not int")
            continue

        try:
            setter(var_int)
        except ValueError as e:
            warnings.warn(f"{var_name}: {e}")


_apply_env_variables()
atexit.register(core.clear_cache)


if TYPE_CHECKING:
    _ExifBase = MutableMapping[int, Any]
else:
    _ExifBase = MutableMapping


class Exif(_ExifBase):
    """
    This class provides read and write access to EXIF image data::

      from PIL import Image
      im = Image.open("exif.png")
      exif = im.getexif()  # Returns an instance of this class

    Information can be read and written, iterated over or deleted::

      print(exif[274])  # 1
      exif[274] = 2
      for k, v in exif.items():
        print("Tag", k, "Value", v)  # Tag 274 Value 2
      del exif[274]

    To access information beyond IFD0, :py:meth:`~PIL.Image.Exif.get_ifd`
    returns a dictionary::

      from PIL import ExifTags
      im = Image.open("exif_gps.jpg")
      exif = im.getexif()
      gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
      print(gps_ifd)

    Other IFDs include ``ExifTags.IFD.Exif``, ``ExifTags.IFD.MakerNote``,
    ``ExifTags.IFD.Interop`` and ``ExifTags.IFD.IFD1``.

    :py:mod:`~PIL.ExifTags` also has enum classes to provide names for data::

      print(exif[ExifTags.Base.Software])  # PIL
      print(gps_ifd[ExifTags.GPS.GPSDateStamp])  # 1999:99:99 99:99:99
    """

    endian: str | None = None
    bigtiff = False
    _loaded = False

    def __init__(self) -> None:
        self._data: dict[int, Any] = {}
        self._hidden_data: dict[int, Any] = {}
        self._ifds: dict[int, dict[int, Any]] = {}
        self._info: TiffImagePlugin.ImageFileDirectory_v2 | None = None
        self._loaded_exif: bytes | None = None

    def _fixup(self, value: Any) -> Any:
        try:
            if len(value) == 1 and isinstance(value, tuple):
                return value[0]
        except Exception:
            pass
        return value

    def _fixup_dict(self, src_dict: dict[int, Any]) -> dict[int, Any]:
        # Helper function
        # returns a dict with any single item tuples/lists as individual values
        return {k: self._fixup(v) for k, v in src_dict.items()}

    def _get_ifd_dict(
        self, offset: int, group: int | None = None
    ) -> dict[int, Any] | None:
        try:
            # an offset pointer to the location of the nested embedded IFD.
            # It should be a long, but may be corrupted.
            self.fp.seek(offset)
        except (KeyError, TypeError):
            return None
        else:
            from . import TiffImagePlugin

            info = TiffImagePlugin.ImageFileDirectory_v2(self.head, group=group)
            info.load(self.fp)
            return self._fixup_dict(dict(info))

    def _get_head(self) -> bytes:
        version = b"\x2b" if self.bigtiff else b"\x2a"
        if self.endian == "<":
            head = b"II" + version + b"\x00" + o32le(8)
        else:
            head = b"MM\x00" + version + o32be(8)
        if self.bigtiff:
            head += o32le(8) if self.endian == "<" else o32be(8)
            head += b"\x00\x00\x00\x00"
        return head

    def load(self, data: bytes) -> None:
        # Extract EXIF information.  This is highly experimental,
        # and is likely to be replaced with something better in a future
        # version.

        # The EXIF record consists of a TIFF file embedded in a JPEG
        # application marker (!).
        if data == self._loaded_exif:
            return
        self._loaded_exif = data
        self._data.clear()
        self._hidden_data.clear()
        self._ifds.clear()
        while data and data.startswith(b"Exif\x00\x00"):
            data = data[6:]
        if not data:
            self._info = None
            return

        self.fp: IO[bytes] = io.BytesIO(data)
        self.head = self.fp.read(8)
        # process dictionary
        from . import TiffImagePlugin

        self._info = TiffImagePlugin.ImageFileDirectory_v2(self.head)
        self.endian = self._info._endian
        self.fp.seek(self._info.next)
        self._info.load(self.fp)

    def load_from_fp(self, fp: IO[bytes], offset: int | None = None) -> None:
        self._loaded_exif = None
        self._data.clear()
        self._hidden_data.clear()
        self._ifds.clear()

        # process dictionary
        from . import TiffImagePlugin

        self.fp = fp
        if offset is not None:
            self.head = self._get_head()
        else:
            self.head = self.fp.read(8)
        self._info = TiffImagePlugin.ImageFileDirectory_v2(self.head)
        if self.endian is None:
            self.endian = self._info._endian
        if offset is None:
            offset = self._info.next
        self.fp.tell()
        self.fp.seek(offset)
        self._info.load(self.fp)

    def _get_merged_dict(self) -> dict[int, Any]:
        merged_dict = dict(self)

        # get EXIF extension
        if ExifTags.IFD.Exif in self:
            ifd = self._get_ifd_dict(self[ExifTags.IFD.Exif], ExifTags.IFD.Exif)
            if ifd:
                merged_dict.update(ifd)

        # GPS
        if ExifTags.IFD.GPSInfo in self:
            merged_dict[ExifTags.IFD.GPSInfo] = self._get_ifd_dict(
                self[ExifTags.IFD.GPSInfo], ExifTags.IFD.GPSInfo
            )

        return merged_dict

    def tobytes(self, offset: int = 8) -> bytes:
        from . import TiffImagePlugin

        head = self._get_head()
        ifd = TiffImagePlugin.ImageFileDirectory_v2(ifh=head)
        for tag, ifd_dict in self._ifds.items():
            if tag not in self:
                ifd[tag] = ifd_dict
        for tag, value in self.items():
            if tag in [
                ExifTags.IFD.Exif,
                ExifTags.IFD.GPSInfo,
            ] and not isinstance(value, dict):
                value = self.get_ifd(tag)
                if (
                    tag == ExifTags.IFD.Exif
                    and ExifTags.IFD.Interop in value
                    and not isinstance(value[ExifTags.IFD.Interop], dict)
                ):
                    value = value.copy()
                    value[ExifTags.IFD.Interop] = self.get_ifd(ExifTags.IFD.Interop)
            ifd[tag] = value
        return b"Exif\x00\x00" + head + ifd.tobytes(offset)

    def get_ifd(self, tag: int) -> dict[int, Any]:
        if tag not in self._ifds:
            if tag == ExifTags.IFD.IFD1:
                if self._info is not None and self._info.next != 0:
                    ifd = self._get_ifd_dict(self._info.next)
                    if ifd is not None:
                        self._ifds[tag] = ifd
            elif tag in [ExifTags.IFD.Exif, ExifTags.IFD.GPSInfo]:
                offset = self._hidden_data.get(tag, self.get(tag))
                if offset is not None:
                    ifd = self._get_ifd_dict(offset, tag)
                    if ifd is not None:
                        self._ifds[tag] = ifd
            elif tag in [ExifTags.IFD.Interop, ExifTags.IFD.MakerNote]:
                if ExifTags.IFD.Exif not in self._ifds:
                    self.get_ifd(ExifTags.IFD.Exif)
                tag_data = self._ifds[ExifTags.IFD.Exif][tag]
                if tag == ExifTags.IFD.MakerNote:
                    from .TiffImagePlugin import ImageFileDirectory_v2

                    if tag_data.startswith(b"FUJIFILM"):
                        ifd_offset = i32le(tag_data, 8)
                        ifd_data = tag_data[ifd_offset:]

                        makernote = {}
                        for i in range(struct.unpack("<H", ifd_data[:2])[0]):
                            ifd_tag, typ, count, data = struct.unpack(
                                "<HHL4s", ifd_data[i * 12 + 2 : (i + 1) * 12 + 2]
                            )
                            try:
                                (
                                    unit_size,
                                    handler,
                                ) = ImageFileDirectory_v2._load_dispatch[typ]
                            except KeyError:
                                continue
                            size = count * unit_size
                            if size > 4:
                                (offset,) = struct.unpack("<L", data)
                                data = ifd_data[offset - 12 : offset + size - 12]
                            else:
                                data = data[:size]

                            if len(data) != size:
                                warnings.warn(
                                    "Possibly corrupt EXIF MakerNote data.  "
                                    f"Expecting to read {size} bytes but only got "
                                    f"{len(data)}. Skipping tag {ifd_tag}"
                                )
                                continue

                            if not data:
                                continue

                            makernote[ifd_tag] = handler(
                                ImageFileDirectory_v2(), data, False
                            )
                        self._ifds[tag] = dict(self._fixup_dict(makernote))
                    elif self.get(0x010F) == "Nintendo":
                        makernote = {}
                        for i in range(struct.unpack(">H", tag_data[:2])[0]):
                            ifd_tag, typ, count, data = struct.unpack(
                                ">HHL4s", tag_data[i * 12 + 2 : (i + 1) * 12 + 2]
                            )
                            if ifd_tag == 0x1101:
                                # CameraInfo
                                (offset,) = struct.unpack(">L", data)
                                self.fp.seek(offset)

                                camerainfo: dict[str, int | bytes] = {
                                    "ModelID": self.fp.read(4)
                                }

                                self.fp.read(4)
                                # Seconds since 2000
                                camerainfo["TimeStamp"] = i32le(self.fp.read(12))

                                self.fp.read(4)
                                camerainfo["InternalSerialNumber"] = self.fp.read(4)

                                self.fp.read(12)
                                parallax = self.fp.read(4)
                                handler = ImageFileDirectory_v2._load_dispatch[
                                    TiffTags.FLOAT
                                ][1]
                                camerainfo["Parallax"] = handler(
                                    ImageFileDirectory_v2(), parallax, False
                                )[0]

                                self.fp.read(4)
                                camerainfo["Category"] = self.fp.read(2)

                                makernote = {0x1101: camerainfo}
                        self._ifds[tag] = makernote
                else:
                    # Interop
                    ifd = self._get_ifd_dict(tag_data, tag)
                    if ifd is not None:
                        self._ifds[tag] = ifd
        ifd = self._ifds.setdefault(tag, {})
        if tag == ExifTags.IFD.Exif and self._hidden_data:
            ifd = {
                k: v
                for (k, v) in ifd.items()
                if k not in (ExifTags.IFD.Interop, ExifTags.IFD.MakerNote)
            }
        return ifd

    def hide_offsets(self) -> None:
        for tag in (ExifTags.IFD.Exif, ExifTags.IFD.GPSInfo):
            if tag in self:
                self._hidden_data[tag] = self[tag]
                del self[tag]

    def __str__(self) -> str:
        if self._info is not None:
            # Load all keys into self._data
            for tag in self._info:
                self[tag]

        return str(self._data)

    def __len__(self) -> int:
        keys = set(self._data)
        if self._info is not None:
            keys.update(self._info)
        return len(keys)

    def __getitem__(self, tag: int) -> Any:
        if self._info is not None and tag not in self._data and tag in self._info:
            self._data[tag] = self._fixup(self._info[tag])
            del self._info[tag]
        return self._data[tag]

    def __contains__(self, tag: object) -> bool:
        return tag in self._data or (self._info is not None and tag in self._info)

    def __setitem__(self, tag: int, value: Any) -> None:
        if self._info is not None and tag in self._info:
            del self._info[tag]
        self._data[tag] = value

    def __delitem__(self, tag: int) -> None:
        if self._info is not None and tag in self._info:
            del self._info[tag]
        else:
            del self._data[tag]

    def __iter__(self) -> Iterator[int]:
        keys = set(self._data)
        if self._info is not None:
            keys.update(self._info)
        return iter(keys)
