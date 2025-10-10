#
# The Python Imaging Library
# $Id$
#
# BUFR stub adapter
#
# Copyright (c) 1996-2003 by Fredrik Lundh
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
    Install application-specific BUFR image handler.

    :param handler: Handler object.
    """
    global _handler
    _handler = handler


# --------------------------------------------------------------------
# Image adapter


def _accept(prefix: bytes) -> bool:
    return prefix.startswith((b"BUFR", b"ZCZC"))


class BufrStubImageFile(ImageFile.StubImageFile):
    format = "BUFR"
    format_description = "BUFR"

    def _open(self) -> None:
        if not _accept(self.fp.read(4)):
            msg = "Not a BUFR file"
            raise SyntaxError(msg)

        self.fp.seek(-4, os.SEEK_CUR)

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
        msg = "BUFR save handler not installed"
        raise OSError(msg)
    _handler.save(im, fp, filename)


# --------------------------------------------------------------------
# Registry

Image.register_open(BufrStubImageFile.format, BufrStubImageFile, _accept)
Image.register_save(BufrStubImageFile.format, _save)

Image.register_extension(BufrStubImageFile.format, ".bufr")
