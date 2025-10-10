#
# The Python Imaging Library
# $Id$
#
# FITS file handling
#
# Copyright (c) 1998-2003 by Fredrik Lundh
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import gzip
import math

from . import Image, ImageFile


def _accept(prefix: bytes) -> bool:
    return prefix.startswith(b"SIMPLE")


class FitsImageFile(ImageFile.ImageFile):
    format = "FITS"
    format_description = "FITS"

    def _open(self) -> None:
        assert self.fp is not None

        headers: dict[bytes, bytes] = {}
        header_in_progress = False
        decoder_name = ""
        while True:
            header = self.fp.read(80)
            if not header:
                msg = "Truncated FITS file"
                raise OSError(msg)
            keyword = header[:8].strip()
            if keyword in (b"SIMPLE", b"XTENSION"):
                header_in_progress = True
            elif headers and not header_in_progress:
                # This is now a data unit
                break
            elif keyword == b"END":
                # Seek to the end of the header unit
                self.fp.seek(math.ceil(self.fp.tell() / 2880) * 2880)
                if not decoder_name:
                    decoder_name, offset, args = self._parse_headers(headers)

                header_in_progress = False
                continue

            if decoder_name:
                # Keep going to read past the headers
                continue

            value = header[8:].split(b"/")[0].strip()
            if value.startswith(b"="):
                value = value[1:].strip()
            if not headers and (not _accept(keyword) or value != b"T"):
                msg = "Not a FITS file"
                raise SyntaxError(msg)
            headers[keyword] = value

        if not decoder_name:
            msg = "No image data"
            raise ValueError(msg)

        offset += self.fp.tell() - 80
        self.tile = [ImageFile._Tile(decoder_name, (0, 0) + self.size, offset, args)]

    def _get_size(
        self, headers: dict[bytes, bytes], prefix: bytes
    ) -> tuple[int, int] | None:
        naxis = int(headers[prefix + b"NAXIS"])
        if naxis == 0:
            return None

        if naxis == 1:
            return 1, int(headers[prefix + b"NAXIS1"])
        else:
            return int(headers[prefix + b"NAXIS1"]), int(headers[prefix + b"NAXIS2"])

    def _parse_headers(
        self, headers: dict[bytes, bytes]
    ) -> tuple[str, int, tuple[str | int, ...]]:
        prefix = b""
        decoder_name = "raw"
        offset = 0
        if (
            headers.get(b"XTENSION") == b"'BINTABLE'"
            and headers.get(b"ZIMAGE") == b"T"
            and headers[b"ZCMPTYPE"] == b"'GZIP_1  '"
        ):
            no_prefix_size = self._get_size(headers, prefix) or (0, 0)
            number_of_bits = int(headers[b"BITPIX"])
            offset = no_prefix_size[0] * no_prefix_size[1] * (number_of_bits // 8)

            prefix = b"Z"
            decoder_name = "fits_gzip"

        size = self._get_size(headers, prefix)
        if not size:
            return "", 0, ()

        self._size = size

        number_of_bits = int(headers[prefix + b"BITPIX"])
        if number_of_bits == 8:
            self._mode = "L"
        elif number_of_bits == 16:
            self._mode = "I;16"
        elif number_of_bits == 32:
            self._mode = "I"
        elif number_of_bits in (-32, -64):
            self._mode = "F"

        args: tuple[str | int, ...]
        if decoder_name == "raw":
            args = (self.mode, 0, -1)
        else:
            args = (number_of_bits,)
        return decoder_name, offset, args


class FitsGzipDecoder(ImageFile.PyDecoder):
    _pulls_fd = True

    def decode(self, buffer: bytes | Image.SupportsArrayInterface) -> tuple[int, int]:
        assert self.fd is not None
        value = gzip.decompress(self.fd.read())

        rows = []
        offset = 0
        number_of_bits = min(self.args[0] // 8, 4)
        for y in range(self.state.ysize):
            row = bytearray()
            for x in range(self.state.xsize):
                row += value[offset + (4 - number_of_bits) : offset + 4]
                offset += 4
            rows.append(row)
        self.set_as_raw(bytes([pixel for row in rows[::-1] for pixel in row]))
        return -1, 0


# --------------------------------------------------------------------
# Registry

Image.register_open(FitsImageFile.format, FitsImageFile, _accept)
Image.register_decoder("fits_gzip", FitsGzipDecoder)

Image.register_extensions(FitsImageFile.format, [".fit", ".fits"])
