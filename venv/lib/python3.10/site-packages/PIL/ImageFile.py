#
# The Python Imaging Library.
# $Id$
#
# base class for image file handlers
#
# history:
# 1995-09-09 fl   Created
# 1996-03-11 fl   Fixed load mechanism.
# 1996-04-15 fl   Added pcx/xbm decoders.
# 1996-04-30 fl   Added encoders.
# 1996-12-14 fl   Added load helpers
# 1997-01-11 fl   Use encode_to_file where possible
# 1997-08-27 fl   Flush output in _save
# 1998-03-05 fl   Use memory mapping for some modes
# 1999-02-04 fl   Use memory mapping also for "I;16" and "I;16B"
# 1999-05-31 fl   Added image parser
# 2000-10-12 fl   Set readonly flag on memory-mapped images
# 2002-03-20 fl   Use better messages for common decoder errors
# 2003-04-21 fl   Fall back on mmap/map_buffer if map is not available
# 2003-10-30 fl   Added StubImageFile class
# 2004-02-25 fl   Made incremental parser more robust
#
# Copyright (c) 1997-2004 by Secret Labs AB
# Copyright (c) 1995-2004 by Fredrik Lundh
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import abc
import io
import itertools
import logging
import os
import struct
from typing import IO, Any, NamedTuple, cast

from . import ExifTags, Image
from ._deprecate import deprecate
from ._util import DeferredError, is_path

TYPE_CHECKING = False
if TYPE_CHECKING:
    from ._typing import StrOrBytesPath

logger = logging.getLogger(__name__)

MAXBLOCK = 65536

SAFEBLOCK = 1024 * 1024

LOAD_TRUNCATED_IMAGES = False
"""Whether or not to load truncated image files. User code may change this."""

ERRORS = {
    -1: "image buffer overrun error",
    -2: "decoding error",
    -3: "unknown error",
    -8: "bad configuration",
    -9: "out of memory error",
}
"""
Dict of known error codes returned from :meth:`.PyDecoder.decode`,
:meth:`.PyEncoder.encode` :meth:`.PyEncoder.encode_to_pyfd` and
:meth:`.PyEncoder.encode_to_file`.
"""


#
# --------------------------------------------------------------------
# Helpers


def _get_oserror(error: int, *, encoder: bool) -> OSError:
    try:
        msg = Image.core.getcodecstatus(error)
    except AttributeError:
        msg = ERRORS.get(error)
    if not msg:
        msg = f"{'encoder' if encoder else 'decoder'} error {error}"
    msg += f" when {'writing' if encoder else 'reading'} image file"
    return OSError(msg)


def raise_oserror(error: int) -> OSError:
    deprecate(
        "raise_oserror",
        12,
        action="It is only useful for translating error codes returned by a codec's "
        "decode() method, which ImageFile already does automatically.",
    )
    raise _get_oserror(error, encoder=False)


def _tilesort(t: _Tile) -> int:
    # sort on offset
    return t[2]


class _Tile(NamedTuple):
    codec_name: str
    extents: tuple[int, int, int, int] | None
    offset: int = 0
    args: tuple[Any, ...] | str | None = None


#
# --------------------------------------------------------------------
# ImageFile base class


class ImageFile(Image.Image):
    """Base class for image file format handlers."""

    def __init__(
        self, fp: StrOrBytesPath | IO[bytes], filename: str | bytes | None = None
    ) -> None:
        super().__init__()

        self._min_frame = 0

        self.custom_mimetype: str | None = None

        self.tile: list[_Tile] = []
        """ A list of tile descriptors """

        self.readonly = 1  # until we know better

        self.decoderconfig: tuple[Any, ...] = ()
        self.decodermaxblock = MAXBLOCK

        if is_path(fp):
            # filename
            self.fp = open(fp, "rb")
            self.filename = os.fspath(fp)
            self._exclusive_fp = True
        else:
            # stream
            self.fp = cast(IO[bytes], fp)
            self.filename = filename if filename is not None else ""
            # can be overridden
            self._exclusive_fp = False

        try:
            try:
                self._open()
            except (
                IndexError,  # end of data
                TypeError,  # end of data (ord)
                KeyError,  # unsupported mode
                EOFError,  # got header but not the first frame
                struct.error,
            ) as v:
                raise SyntaxError(v) from v

            if not self.mode or self.size[0] <= 0 or self.size[1] <= 0:
                msg = "not identified by this driver"
                raise SyntaxError(msg)
        except BaseException:
            # close the file only if we have opened it this constructor
            if self._exclusive_fp:
                self.fp.close()
            raise

    def _open(self) -> None:
        pass

    def _close_fp(self):
        if getattr(self, "_fp", False) and not isinstance(self._fp, DeferredError):
            if self._fp != self.fp:
                self._fp.close()
            self._fp = DeferredError(ValueError("Operation on closed image"))
        if self.fp:
            self.fp.close()

    def close(self) -> None:
        """
        Closes the file pointer, if possible.

        This operation will destroy the image core and release its memory.
        The image data will be unusable afterward.

        This function is required to close images that have multiple frames or
        have not had their file read and closed by the
        :py:meth:`~PIL.Image.Image.load` method. See :ref:`file-handling` for
        more information.
        """
        try:
            self._close_fp()
            self.fp = None
        except Exception as msg:
            logger.debug("Error closing: %s", msg)

        super().close()

    def get_child_images(self) -> list[ImageFile]:
        child_images = []
        exif = self.getexif()
        ifds = []
        if ExifTags.Base.SubIFDs in exif:
            subifd_offsets = exif[ExifTags.Base.SubIFDs]
            if subifd_offsets:
                if not isinstance(subifd_offsets, tuple):
                    subifd_offsets = (subifd_offsets,)
                for subifd_offset in subifd_offsets:
                    ifds.append((exif._get_ifd_dict(subifd_offset), subifd_offset))
        ifd1 = exif.get_ifd(ExifTags.IFD.IFD1)
        if ifd1 and ifd1.get(ExifTags.Base.JpegIFOffset):
            assert exif._info is not None
            ifds.append((ifd1, exif._info.next))

        offset = None
        for ifd, ifd_offset in ifds:
            assert self.fp is not None
            current_offset = self.fp.tell()
            if offset is None:
                offset = current_offset

            fp = self.fp
            if ifd is not None:
                thumbnail_offset = ifd.get(ExifTags.Base.JpegIFOffset)
                if thumbnail_offset is not None:
                    thumbnail_offset += getattr(self, "_exif_offset", 0)
                    self.fp.seek(thumbnail_offset)

                    length = ifd.get(ExifTags.Base.JpegIFByteCount)
                    assert isinstance(length, int)
                    data = self.fp.read(length)
                    fp = io.BytesIO(data)

            with Image.open(fp) as im:
                from . import TiffImagePlugin

                if thumbnail_offset is None and isinstance(
                    im, TiffImagePlugin.TiffImageFile
                ):
                    im._frame_pos = [ifd_offset]
                    im._seek(0)
                im.load()
                child_images.append(im)

        if offset is not None:
            assert self.fp is not None
            self.fp.seek(offset)
        return child_images

    def get_format_mimetype(self) -> str | None:
        if self.custom_mimetype:
            return self.custom_mimetype
        if self.format is not None:
            return Image.MIME.get(self.format.upper())
        return None

    def __getstate__(self) -> list[Any]:
        return super().__getstate__() + [self.filename]

    def __setstate__(self, state: list[Any]) -> None:
        self.tile = []
        if len(state) > 5:
            self.filename = state[5]
        super().__setstate__(state)

    def verify(self) -> None:
        """Check file integrity"""

        # raise exception if something's wrong.  must be called
        # directly after open, and closes file when finished.
        if self._exclusive_fp:
            self.fp.close()
        self.fp = None

    def load(self) -> Image.core.PixelAccess | None:
        """Load image data based on tile list"""

        if not self.tile and self._im is None:
            msg = "cannot load this image"
            raise OSError(msg)

        pixel = Image.Image.load(self)
        if not self.tile:
            return pixel

        self.map: mmap.mmap | None = None
        use_mmap = self.filename and len(self.tile) == 1

        readonly = 0

        # look for read/seek overrides
        if hasattr(self, "load_read"):
            read = self.load_read
            # don't use mmap if there are custom read/seek functions
            use_mmap = False
        else:
            read = self.fp.read

        if hasattr(self, "load_seek"):
            seek = self.load_seek
            use_mmap = False
        else:
            seek = self.fp.seek

        if use_mmap:
            # try memory mapping
            decoder_name, extents, offset, args = self.tile[0]
            if isinstance(args, str):
                args = (args, 0, 1)
            if (
                decoder_name == "raw"
                and isinstance(args, tuple)
                and len(args) >= 3
                and args[0] == self.mode
                and args[0] in Image._MAPMODES
            ):
                try:
                    # use mmap, if possible
                    import mmap

                    with open(self.filename) as fp:
                        self.map = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
                    if offset + self.size[1] * args[1] > self.map.size():
                        msg = "buffer is not large enough"
                        raise OSError(msg)
                    self.im = Image.core.map_buffer(
                        self.map, self.size, decoder_name, offset, args
                    )
                    readonly = 1
                    # After trashing self.im,
                    # we might need to reload the palette data.
                    if self.palette:
                        self.palette.dirty = 1
                except (AttributeError, OSError, ImportError):
                    self.map = None

        self.load_prepare()
        err_code = -3  # initialize to unknown error
        if not self.map:
            # sort tiles in file order
            self.tile.sort(key=_tilesort)

            # FIXME: This is a hack to handle TIFF's JpegTables tag.
            prefix = getattr(self, "tile_prefix", b"")

            # Remove consecutive duplicates that only differ by their offset
            self.tile = [
                list(tiles)[-1]
                for _, tiles in itertools.groupby(
                    self.tile, lambda tile: (tile[0], tile[1], tile[3])
                )
            ]
            for i, (decoder_name, extents, offset, args) in enumerate(self.tile):
                seek(offset)
                decoder = Image._getdecoder(
                    self.mode, decoder_name, args, self.decoderconfig
                )
                try:
                    decoder.setimage(self.im, extents)
                    if decoder.pulls_fd:
                        decoder.setfd(self.fp)
                        err_code = decoder.decode(b"")[1]
                    else:
                        b = prefix
                        while True:
                            read_bytes = self.decodermaxblock
                            if i + 1 < len(self.tile):
                                next_offset = self.tile[i + 1].offset
                                if next_offset > offset:
                                    read_bytes = next_offset - offset
                            try:
                                s = read(read_bytes)
                            except (IndexError, struct.error) as e:
                                # truncated png/gif
                                if LOAD_TRUNCATED_IMAGES:
                                    break
                                else:
                                    msg = "image file is truncated"
                                    raise OSError(msg) from e

                            if not s:  # truncated jpeg
                                if LOAD_TRUNCATED_IMAGES:
                                    break
                                else:
                                    msg = (
                                        "image file is truncated "
                                        f"({len(b)} bytes not processed)"
                                    )
                                    raise OSError(msg)

                            b = b + s
                            n, err_code = decoder.decode(b)
                            if n < 0:
                                break
                            b = b[n:]
                finally:
                    # Need to cleanup here to prevent leaks
                    decoder.cleanup()

        self.tile = []
        self.readonly = readonly

        self.load_end()

        if self._exclusive_fp and self._close_exclusive_fp_after_loading:
            self.fp.close()
        self.fp = None

        if not self.map and not LOAD_TRUNCATED_IMAGES and err_code < 0:
            # still raised if decoder fails to return anything
            raise _get_oserror(err_code, encoder=False)

        return Image.Image.load(self)

    def load_prepare(self) -> None:
        # create image memory if necessary
        if self._im is None:
            self.im = Image.core.new(self.mode, self.size)
        # create palette (optional)
        if self.mode == "P":
            Image.Image.load(self)

    def load_end(self) -> None:
        # may be overridden
        pass

    # may be defined for contained formats
    # def load_seek(self, pos: int) -> None:
    #     pass

    # may be defined for blocked formats (e.g. PNG)
    # def load_read(self, read_bytes: int) -> bytes:
    #     pass

    def _seek_check(self, frame: int) -> bool:
        if (
            frame < self._min_frame
            # Only check upper limit on frames if additional seek operations
            # are not required to do so
            or (
                not (hasattr(self, "_n_frames") and self._n_frames is None)
                and frame >= getattr(self, "n_frames") + self._min_frame
            )
        ):
            msg = "attempt to seek outside sequence"
            raise EOFError(msg)

        return self.tell() != frame


class StubHandler(abc.ABC):
    def open(self, im: StubImageFile) -> None:
        pass

    @abc.abstractmethod
    def load(self, im: StubImageFile) -> Image.Image:
        pass


class StubImageFile(ImageFile, metaclass=abc.ABCMeta):
    """
    Base class for stub image loaders.

    A stub loader is an image loader that can identify files of a
    certain format, but relies on external code to load the file.
    """

    @abc.abstractmethod
    def _open(self) -> None:
        pass

    def load(self) -> Image.core.PixelAccess | None:
        loader = self._load()
        if loader is None:
            msg = f"cannot find loader for this {self.format} file"
            raise OSError(msg)
        image = loader.load(self)
        assert image is not None
        # become the other object (!)
        self.__class__ = image.__class__  # type: ignore[assignment]
        self.__dict__ = image.__dict__
        return image.load()

    @abc.abstractmethod
    def _load(self) -> StubHandler | None:
        """(Hook) Find actual image loader."""
        pass


class Parser:
    """
    Incremental image parser.  This class implements the standard
    feed/close consumer interface.
    """

    incremental = None
    image: Image.Image | None = None
    data: bytes | None = None
    decoder: Image.core.ImagingDecoder | PyDecoder | None = None
    offset = 0
    finished = 0

    def reset(self) -> None:
        """
        (Consumer) Reset the parser.  Note that you can only call this
        method immediately after you've created a parser; parser
        instances cannot be reused.
        """
        assert self.data is None, "cannot reuse parsers"

    def feed(self, data: bytes) -> None:
        """
        (Consumer) Feed data to the parser.

        :param data: A string buffer.
        :exception OSError: If the parser failed to parse the image file.
        """
        # collect data

        if self.finished:
            return

        if self.data is None:
            self.data = data
        else:
            self.data = self.data + data

        # parse what we have
        if self.decoder:
            if self.offset > 0:
                # skip header
                skip = min(len(self.data), self.offset)
                self.data = self.data[skip:]
                self.offset = self.offset - skip
                if self.offset > 0 or not self.data:
                    return

            n, e = self.decoder.decode(self.data)

            if n < 0:
                # end of stream
                self.data = None
                self.finished = 1
                if e < 0:
                    # decoding error
                    self.image = None
                    raise _get_oserror(e, encoder=False)
                else:
                    # end of image
                    return
            self.data = self.data[n:]

        elif self.image:
            # if we end up here with no decoder, this file cannot
            # be incrementally parsed.  wait until we've gotten all
            # available data
            pass

        else:
            # attempt to open this file
            try:
                with io.BytesIO(self.data) as fp:
                    im = Image.open(fp)
            except OSError:
                pass  # not enough data
            else:
                flag = hasattr(im, "load_seek") or hasattr(im, "load_read")
                if flag or len(im.tile) != 1:
                    # custom load code, or multiple tiles
                    self.decode = None
                else:
                    # initialize decoder
                    im.load_prepare()
                    d, e, o, a = im.tile[0]
                    im.tile = []
                    self.decoder = Image._getdecoder(im.mode, d, a, im.decoderconfig)
                    self.decoder.setimage(im.im, e)

                    # calculate decoder offset
                    self.offset = o
                    if self.offset <= len(self.data):
                        self.data = self.data[self.offset :]
                        self.offset = 0

                self.image = im

    def __enter__(self) -> Parser:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> Image.Image:
        """
        (Consumer) Close the stream.

        :returns: An image object.
        :exception OSError: If the parser failed to parse the image file either
                            because it cannot be identified or cannot be
                            decoded.
        """
        # finish decoding
        if self.decoder:
            # get rid of what's left in the buffers
            self.feed(b"")
            self.data = self.decoder = None
            if not self.finished:
                msg = "image was incomplete"
                raise OSError(msg)
        if not self.image:
            msg = "cannot parse this image"
            raise OSError(msg)
        if self.data:
            # incremental parsing not possible; reopen the file
            # not that we have all data
            with io.BytesIO(self.data) as fp:
                try:
                    self.image = Image.open(fp)
                finally:
                    self.image.load()
        return self.image


# --------------------------------------------------------------------


def _save(im: Image.Image, fp: IO[bytes], tile: list[_Tile], bufsize: int = 0) -> None:
    """Helper to save image based on tile list

    :param im: Image object.
    :param fp: File object.
    :param tile: Tile list.
    :param bufsize: Optional buffer size
    """

    im.load()
    if not hasattr(im, "encoderconfig"):
        im.encoderconfig = ()
    tile.sort(key=_tilesort)
    # FIXME: make MAXBLOCK a configuration parameter
    # It would be great if we could have the encoder specify what it needs
    # But, it would need at least the image size in most cases. RawEncode is
    # a tricky case.
    bufsize = max(MAXBLOCK, bufsize, im.size[0] * 4)  # see RawEncode.c
    try:
        fh = fp.fileno()
        fp.flush()
        _encode_tile(im, fp, tile, bufsize, fh)
    except (AttributeError, io.UnsupportedOperation) as exc:
        _encode_tile(im, fp, tile, bufsize, None, exc)
    if hasattr(fp, "flush"):
        fp.flush()


def _encode_tile(
    im: Image.Image,
    fp: IO[bytes],
    tile: list[_Tile],
    bufsize: int,
    fh: int | None,
    exc: BaseException | None = None,
) -> None:
    for encoder_name, extents, offset, args in tile:
        if offset > 0:
            fp.seek(offset)
        encoder = Image._getencoder(im.mode, encoder_name, args, im.encoderconfig)
        try:
            encoder.setimage(im.im, extents)
            if encoder.pushes_fd:
                encoder.setfd(fp)
                errcode = encoder.encode_to_pyfd()[1]
            else:
                if exc:
                    # compress to Python file-compatible object
                    while True:
                        errcode, data = encoder.encode(bufsize)[1:]
                        fp.write(data)
                        if errcode:
                            break
                else:
                    # slight speedup: compress to real file object
                    assert fh is not None
                    errcode = encoder.encode_to_file(fh, bufsize)
            if errcode < 0:
                raise _get_oserror(errcode, encoder=True) from exc
        finally:
            encoder.cleanup()


def _safe_read(fp: IO[bytes], size: int) -> bytes:
    """
    Reads large blocks in a safe way.  Unlike fp.read(n), this function
    doesn't trust the user.  If the requested size is larger than
    SAFEBLOCK, the file is read block by block.

    :param fp: File handle.  Must implement a <b>read</b> method.
    :param size: Number of bytes to read.
    :returns: A string containing <i>size</i> bytes of data.

    Raises an OSError if the file is truncated and the read cannot be completed

    """
    if size <= 0:
        return b""
    if size <= SAFEBLOCK:
        data = fp.read(size)
        if len(data) < size:
            msg = "Truncated File Read"
            raise OSError(msg)
        return data
    blocks: list[bytes] = []
    remaining_size = size
    while remaining_size > 0:
        block = fp.read(min(remaining_size, SAFEBLOCK))
        if not block:
            break
        blocks.append(block)
        remaining_size -= len(block)
    if sum(len(block) for block in blocks) < size:
        msg = "Truncated File Read"
        raise OSError(msg)
    return b"".join(blocks)


class PyCodecState:
    def __init__(self) -> None:
        self.xsize = 0
        self.ysize = 0
        self.xoff = 0
        self.yoff = 0

    def extents(self) -> tuple[int, int, int, int]:
        return self.xoff, self.yoff, self.xoff + self.xsize, self.yoff + self.ysize


class PyCodec:
    fd: IO[bytes] | None

    def __init__(self, mode: str, *args: Any) -> None:
        self.im: Image.core.ImagingCore | None = None
        self.state = PyCodecState()
        self.fd = None
        self.mode = mode
        self.init(args)

    def init(self, args: tuple[Any, ...]) -> None:
        """
        Override to perform codec specific initialization

        :param args: Tuple of arg items from the tile entry
        :returns: None
        """
        self.args = args

    def cleanup(self) -> None:
        """
        Override to perform codec specific cleanup

        :returns: None
        """
        pass

    def setfd(self, fd: IO[bytes]) -> None:
        """
        Called from ImageFile to set the Python file-like object

        :param fd: A Python file-like object
        :returns: None
        """
        self.fd = fd

    def setimage(
        self,
        im: Image.core.ImagingCore,
        extents: tuple[int, int, int, int] | None = None,
    ) -> None:
        """
        Called from ImageFile to set the core output image for the codec

        :param im: A core image object
        :param extents: a 4 tuple of (x0, y0, x1, y1) defining the rectangle
            for this tile
        :returns: None
        """

        # following c code
        self.im = im

        if extents:
            (x0, y0, x1, y1) = extents
        else:
            (x0, y0, x1, y1) = (0, 0, 0, 0)

        if x0 == 0 and x1 == 0:
            self.state.xsize, self.state.ysize = self.im.size
        else:
            self.state.xoff = x0
            self.state.yoff = y0
            self.state.xsize = x1 - x0
            self.state.ysize = y1 - y0

        if self.state.xsize <= 0 or self.state.ysize <= 0:
            msg = "Size cannot be negative"
            raise ValueError(msg)

        if (
            self.state.xsize + self.state.xoff > self.im.size[0]
            or self.state.ysize + self.state.yoff > self.im.size[1]
        ):
            msg = "Tile cannot extend outside image"
            raise ValueError(msg)


class PyDecoder(PyCodec):
    """
    Python implementation of a format decoder. Override this class and
    add the decoding logic in the :meth:`decode` method.

    See :ref:`Writing Your Own File Codec in Python<file-codecs-py>`
    """

    _pulls_fd = False

    @property
    def pulls_fd(self) -> bool:
        return self._pulls_fd

    def decode(self, buffer: bytes | Image.SupportsArrayInterface) -> tuple[int, int]:
        """
        Override to perform the decoding process.

        :param buffer: A bytes object with the data to be decoded.
        :returns: A tuple of ``(bytes consumed, errcode)``.
            If finished with decoding return -1 for the bytes consumed.
            Err codes are from :data:`.ImageFile.ERRORS`.
        """
        msg = "unavailable in base decoder"
        raise NotImplementedError(msg)

    def set_as_raw(
        self, data: bytes, rawmode: str | None = None, extra: tuple[Any, ...] = ()
    ) -> None:
        """
        Convenience method to set the internal image from a stream of raw data

        :param data: Bytes to be set
        :param rawmode: The rawmode to be used for the decoder.
            If not specified, it will default to the mode of the image
        :param extra: Extra arguments for the decoder.
        :returns: None
        """

        if not rawmode:
            rawmode = self.mode
        d = Image._getdecoder(self.mode, "raw", rawmode, extra)
        assert self.im is not None
        d.setimage(self.im, self.state.extents())
        s = d.decode(data)

        if s[0] >= 0:
            msg = "not enough image data"
            raise ValueError(msg)
        if s[1] != 0:
            msg = "cannot decode image data"
            raise ValueError(msg)


class PyEncoder(PyCodec):
    """
    Python implementation of a format encoder. Override this class and
    add the decoding logic in the :meth:`encode` method.

    See :ref:`Writing Your Own File Codec in Python<file-codecs-py>`
    """

    _pushes_fd = False

    @property
    def pushes_fd(self) -> bool:
        return self._pushes_fd

    def encode(self, bufsize: int) -> tuple[int, int, bytes]:
        """
        Override to perform the encoding process.

        :param bufsize: Buffer size.
        :returns: A tuple of ``(bytes encoded, errcode, bytes)``.
            If finished with encoding return 1 for the error code.
            Err codes are from :data:`.ImageFile.ERRORS`.
        """
        msg = "unavailable in base encoder"
        raise NotImplementedError(msg)

    def encode_to_pyfd(self) -> tuple[int, int]:
        """
        If ``pushes_fd`` is ``True``, then this method will be used,
        and ``encode()`` will only be called once.

        :returns: A tuple of ``(bytes consumed, errcode)``.
            Err codes are from :data:`.ImageFile.ERRORS`.
        """
        if not self.pushes_fd:
            return 0, -8  # bad configuration
        bytes_consumed, errcode, data = self.encode(0)
        if data:
            assert self.fd is not None
            self.fd.write(data)
        return bytes_consumed, errcode

    def encode_to_file(self, fh: int, bufsize: int) -> int:
        """
        :param fh: File handle.
        :param bufsize: Buffer size.

        :returns: If finished successfully, return 0.
            Otherwise, return an error code. Err codes are from
            :data:`.ImageFile.ERRORS`.
        """
        errcode = 0
        while errcode == 0:
            status, errcode, buf = self.encode(bufsize)
            if status > 0:
                os.write(fh, buf[status:])
        return errcode
