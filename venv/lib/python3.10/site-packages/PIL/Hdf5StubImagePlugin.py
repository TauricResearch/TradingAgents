#
# The Python Imaging Library
# $Id$
#
# HDF5 stub adapter
#
# Copyright (c) 2000-2003 by Fredrik Lundh
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import os
from typing import IO

from . import Image, ImageFile

_handler = None


def register_handler(handler: ImageFile.StubHandler | None) -> None:
    """
    Install application-specific HDF5 image handler.

    :param handler: Handler object.
    """
    global _handler
    _handler = handler


# --------------------------------------------------------------------
# Image adapter


def _accept(prefix: bytes) -> bool:
    return prefix.startswith(b"\x89HDF\r\n\x1a\n")


class HDF5StubImageFile(ImageFile.StubImageFile):
    format = "HDF5"
    format_description = "HDF5"

    def _open(self) -> None:
        if not _accept(self.fp.read(8)):
            msg = "Not an HDF file"
            raise SyntaxError(msg)

        self.fp.seek(-8, os.SEEK_CUR)

        # make something up
        self._mode = "F"
        self._size = 1, 1

        loader = self._load()
        if loader:
            loader.open(self)

    def _load(self) -> ImageFile.StubHandler | None:
        return _handler


def _save(im: Image.Image, fp: IO[bytes], filename: str | bytes) -> None:
    if _handler is None or not hasattr(_handler, "save"):
        msg = "HDF5 save handler not installed"
        raise OSError(msg)
    _handler.save(im, fp, filename)


# --------------------------------------------------------------------
# Registry

Image.register_open(HDF5StubImageFile.format, HDF5StubImageFile, _accept)
Image.register_save(HDF5StubImageFile.format, _save)

Image.register_extensions(HDF5StubImageFile.format, [".h5", ".hdf"])
