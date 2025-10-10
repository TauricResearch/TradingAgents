#
# The Python Imaging Library.
# $Id$
#
# MPO file handling
#
# See "Multi-Picture Format" (CIPA DC-007-Translation 2009, Standard of the
# Camera & Imaging Products Association)
#
# The multi-picture object combines multiple JPEG images (with a modified EXIF
# data format) into a single file. While it can theoretically be used much like
# a GIF animation, it is commonly used to represent 3D photographs and is (as
# of this writing) the most commonly used format by 3D cameras.
#
# History:
# 2014-03-13 Feneric   Created
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import os
import struct
from typing import IO, Any, cast

from . import (
    Image,
    ImageFile,
    ImageSequence,
    JpegImagePlugin,
    TiffImagePlugin,
)
from ._binary import o32le
from ._util import DeferredError


def _save(im: Image.Image, fp: IO[bytes], filename: str | bytes) -> None:
    JpegImagePlugin._save(im, fp, filename)


def _save_all(im: Image.Image, fp: IO[bytes], filename: str | bytes) -> None:
    append_images = im.encoderinfo.get("append_images", [])
    if not append_images and not getattr(im, "is_animated", False):
        _save(im, fp, filename)
        return

    mpf_offset = 28
    offsets: list[int] = []
    im_sequences = [im, *append_images]
    total = sum(getattr(seq, "n_frames", 1) for seq in im_sequences)
    for im_sequence in im_sequences:
        for im_frame in ImageSequence.Iterator(im_sequence):
            if not offsets:
                # APP2 marker
                ifd_length = 66 + 16 * total
                im_frame.encoderinfo["extra"] = (
                    b"\xff\xe2"
                    + struct.pack(">H", 6 + ifd_length)
                    + b"MPF\0"
                    + b" " * ifd_length
                )
                exif = im_frame.encoderinfo.get("exif")
                if isinstance(exif, Image.Exif):
                    exif = exif.tobytes()
                    im_frame.encoderinfo["exif"] = exif
                if exif:
                    mpf_offset += 4 + len(exif)

                JpegImagePlugin._save(im_frame, fp, filename)
                offsets.append(fp.tell())
            else:
                encoderinfo = im_frame._attach_default_encoderinfo(im)
                im_frame.save(fp, "JPEG")
                im_frame.encoderinfo = encoderinfo
                offsets.append(fp.tell() - offsets[-1])

    ifd = TiffImagePlugin.ImageFileDirectory_v2()
    ifd[0xB000] = b"0100"
    ifd[0xB001] = len(offsets)

    mpentries = b""
    data_offset = 0
    for i, size in enumerate(offsets):
        if i == 0:
            mptype = 0x030000  # Baseline MP Primary Image
        else:
            mptype = 0x000000  # Undefined
        mpentries += struct.pack("<LLLHH", mptype, size, data_offset, 0, 0)
        if i == 0:
            data_offset -= mpf_offset
        data_offset += size
    ifd[0xB002] = mpentries

    fp.seek(mpf_offset)
    fp.write(b"II\x2a\x00" + o32le(8) + ifd.tobytes(8))
    fp.seek(0, os.SEEK_END)


##
# Image plugin for MPO images.


class MpoImageFile(JpegImagePlugin.JpegImageFile):
    format = "MPO"
    format_description = "MPO (CIPA DC-007)"
    _close_exclusive_fp_after_loading = False

    def _open(self) -> None:
        self.fp.seek(0)  # prep the fp in order to pass the JPEG test
        JpegImagePlugin.JpegImageFile._open(self)
        self._after_jpeg_open()

    def _after_jpeg_open(self, mpheader: dict[int, Any] | None = None) -> None:
        self.mpinfo = mpheader if mpheader is not None else self._getmp()
        if self.mpinfo is None:
            msg = "Image appears to be a malformed MPO file"
            raise ValueError(msg)
        self.n_frames = self.mpinfo[0xB001]
        self.__mpoffsets = [
            mpent["DataOffset"] + self.info["mpoffset"] for mpent in self.mpinfo[0xB002]
        ]
        self.__mpoffsets[0] = 0
        # Note that the following assertion will only be invalid if something
        # gets broken within JpegImagePlugin.
        assert self.n_frames == len(self.__mpoffsets)
        del self.info["mpoffset"]  # no longer needed
        self.is_animated = self.n_frames > 1
        self._fp = self.fp  # FIXME: hack
        self._fp.seek(self.__mpoffsets[0])  # get ready to read first frame
        self.__frame = 0
        self.offset = 0
        # for now we can only handle reading and individual frame extraction
        self.readonly = 1

    def load_seek(self, pos: int) -> None:
        if isinstance(self._fp, DeferredError):
            raise self._fp.ex
        self._fp.seek(pos)

    def seek(self, frame: int) -> None:
        if not self._seek_check(frame):
            return
        if isinstance(self._fp, DeferredError):
            raise self._fp.ex
        self.fp = self._fp
        self.offset = self.__mpoffsets[frame]

        original_exif = self.info.get("exif")
        if "exif" in self.info:
            del self.info["exif"]

        self.fp.seek(self.offset + 2)  # skip SOI marker
        if not self.fp.read(2):
            msg = "No data found for frame"
            raise ValueError(msg)
        self.fp.seek(self.offset)
        JpegImagePlugin.JpegImageFile._open(self)
        if self.info.get("exif") != original_exif:
            self._reload_exif()

        self.tile = [
            ImageFile._Tile("jpeg", (0, 0) + self.size, self.offset, self.tile[0][-1])
        ]
        self.__frame = frame

    def tell(self) -> int:
        return self.__frame

    @staticmethod
    def adopt(
        jpeg_instance: JpegImagePlugin.JpegImageFile,
        mpheader: dict[int, Any] | None = None,
    ) -> MpoImageFile:
        """
        Transform the instance of JpegImageFile into
        an instance of MpoImageFile.
        After the call, the JpegImageFile is extended
        to be an MpoImageFile.

        This is essentially useful when opening a JPEG
        file that reveals itself as an MPO, to avoid
        double call to _open.
        """
        jpeg_instance.__class__ = MpoImageFile
        mpo_instance = cast(MpoImageFile, jpeg_instance)
        mpo_instance._after_jpeg_open(mpheader)
        return mpo_instance


# ---------------------------------------------------------------------
# Registry stuff

# Note that since MPO shares a factory with JPEG, we do not need to do a
# separate registration for it here.
# Image.register_open(MpoImageFile.format,
#                     JpegImagePlugin.jpeg_factory, _accept)
Image.register_save(MpoImageFile.format, _save)
Image.register_save_all(MpoImageFile.format, _save_all)

Image.register_extension(MpoImageFile.format, ".mpo")

Image.register_mime(MpoImageFile.format, "image/mpo")
