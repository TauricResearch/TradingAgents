#
# The Python Imaging Library.
#
# QOI support for PIL
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import os
from typing import IO

from . import Image, ImageFile
from ._binary import i32be as i32
from ._binary import o8
from ._binary import o32be as o32


def _accept(prefix: bytes) -> bool:
    return prefix.startswith(b"qoif")


class QoiImageFile(ImageFile.ImageFile):
    format = "QOI"
    format_description = "Quite OK Image"

    def _open(self) -> None:
        if not _accept(self.fp.read(4)):
            msg = "not a QOI file"
            raise SyntaxError(msg)

        self._size = i32(self.fp.read(4)), i32(self.fp.read(4))

        channels = self.fp.read(1)[0]
        self._mode = "RGB" if channels == 3 else "RGBA"

        self.fp.seek(1, os.SEEK_CUR)  # colorspace
        self.tile = [ImageFile._Tile("qoi", (0, 0) + self._size, self.fp.tell())]


class QoiDecoder(ImageFile.PyDecoder):
    _pulls_fd = True
    _previous_pixel: bytes | bytearray | None = None
    _previously_seen_pixels: dict[int, bytes | bytearray] = {}

    def _add_to_previous_pixels(self, value: bytes | bytearray) -> None:
        self._previous_pixel = value

        r, g, b, a = value
        hash_value = (r * 3 + g * 5 + b * 7 + a * 11) % 64
        self._previously_seen_pixels[hash_value] = value

    def decode(self, buffer: bytes | Image.SupportsArrayInterface) -> tuple[int, int]:
        assert self.fd is not None

        self._previously_seen_pixels = {}
        self._previous_pixel = bytearray((0, 0, 0, 255))

        data = bytearray()
        bands = Image.getmodebands(self.mode)
        dest_length = self.state.xsize * self.state.ysize * bands
        while len(data) < dest_length:
            byte = self.fd.read(1)[0]
            value: bytes | bytearray
            if byte == 0b11111110 and self._previous_pixel:  # QOI_OP_RGB
                value = bytearray(self.fd.read(3)) + self._previous_pixel[3:]
            elif byte == 0b11111111:  # QOI_OP_RGBA
                value = self.fd.read(4)
            else:
                op = byte >> 6
                if op == 0:  # QOI_OP_INDEX
                    op_index = byte & 0b00111111
                    value = self._previously_seen_pixels.get(
                        op_index, bytearray((0, 0, 0, 0))
                    )
                elif op == 1 and self._previous_pixel:  # QOI_OP_DIFF
                    value = bytearray(
                        (
                            (self._previous_pixel[0] + ((byte & 0b00110000) >> 4) - 2)
                            % 256,
                            (self._previous_pixel[1] + ((byte & 0b00001100) >> 2) - 2)
                            % 256,
                            (self._previous_pixel[2] + (byte & 0b00000011) - 2) % 256,
                            self._previous_pixel[3],
                        )
                    )
                elif op == 2 and self._previous_pixel:  # QOI_OP_LUMA
                    second_byte = self.fd.read(1)[0]
                    diff_green = (byte & 0b00111111) - 32
                    diff_red = ((second_byte & 0b11110000) >> 4) - 8
                    diff_blue = (second_byte & 0b00001111) - 8

                    value = bytearray(
                        tuple(
                            (self._previous_pixel[i] + diff_green + diff) % 256
                            for i, diff in enumerate((diff_red, 0, diff_blue))
                        )
                    )
                    value += self._previous_pixel[3:]
                elif op == 3 and self._previous_pixel:  # QOI_OP_RUN
                    run_length = (byte & 0b00111111) + 1
                    value = self._previous_pixel
                    if bands == 3:
                        value = value[:3]
                    data += value * run_length
                    continue
            self._add_to_previous_pixels(value)

            if bands == 3:
                value = value[:3]
            data += value
        self.set_as_raw(data)
        return -1, 0


def _save(im: Image.Image, fp: IO[bytes], filename: str | bytes) -> None:
    if im.mode == "RGB":
        channels = 3
    elif im.mode == "RGBA":
        channels = 4
    else:
        msg = "Unsupported QOI image mode"
        raise ValueError(msg)

    colorspace = 0 if im.encoderinfo.get("colorspace") == "sRGB" else 1

    fp.write(b"qoif")
    fp.write(o32(im.size[0]))
    fp.write(o32(im.size[1]))
    fp.write(o8(channels))
    fp.write(o8(colorspace))

    ImageFile._save(im, fp, [ImageFile._Tile("qoi", (0, 0) + im.size)])


class QoiEncoder(ImageFile.PyEncoder):
    _pushes_fd = True
    _previous_pixel: tuple[int, int, int, int] | None = None
    _previously_seen_pixels: dict[int, tuple[int, int, int, int]] = {}
    _run = 0

    def _write_run(self) -> bytes:
        data = o8(0b11000000 | (self._run - 1))  # QOI_OP_RUN
        self._run = 0
        return data

    def _delta(self, left: int, right: int) -> int:
        result = (left - right) & 255
        if result >= 128:
            result -= 256
        return result

    def encode(self, bufsize: int) -> tuple[int, int, bytes]:
        assert self.im is not None

        self._previously_seen_pixels = {0: (0, 0, 0, 0)}
        self._previous_pixel = (0, 0, 0, 255)

        data = bytearray()
        w, h = self.im.size
        bands = Image.getmodebands(self.mode)

        for y in range(h):
            for x in range(w):
                pixel = self.im.getpixel((x, y))
                if bands == 3:
                    pixel = (*pixel, 255)

                if pixel == self._previous_pixel:
                    self._run += 1
                    if self._run == 62:
                        data += self._write_run()
                else:
                    if self._run:
                        data += self._write_run()

                    r, g, b, a = pixel
                    hash_value = (r * 3 + g * 5 + b * 7 + a * 11) % 64
                    if self._previously_seen_pixels.get(hash_value) == pixel:
                        data += o8(hash_value)  # QOI_OP_INDEX
                    elif self._previous_pixel:
                        self._previously_seen_pixels[hash_value] = pixel

                        prev_r, prev_g, prev_b, prev_a = self._previous_pixel
                        if prev_a == a:
                            delta_r = self._delta(r, prev_r)
                            delta_g = self._delta(g, prev_g)
                            delta_b = self._delta(b, prev_b)

                            if (
                                -2 <= delta_r < 2
                                and -2 <= delta_g < 2
                                and -2 <= delta_b < 2
                            ):
                                data += o8(
                                    0b01000000
                                    | (delta_r + 2) << 4
                                    | (delta_g + 2) << 2
                                    | (delta_b + 2)
                                )  # QOI_OP_DIFF
                            else:
                                delta_gr = self._delta(delta_r, delta_g)
                                delta_gb = self._delta(delta_b, delta_g)
                                if (
                                    -8 <= delta_gr < 8
                                    and -32 <= delta_g < 32
                                    and -8 <= delta_gb < 8
                                ):
                                    data += o8(
                                        0b10000000 | (delta_g + 32)
                                    )  # QOI_OP_LUMA
                                    data += o8((delta_gr + 8) << 4 | (delta_gb + 8))
                                else:
                                    data += o8(0b11111110)  # QOI_OP_RGB
                                    data += bytes(pixel[:3])
                        else:
                            data += o8(0b11111111)  # QOI_OP_RGBA
                            data += bytes(pixel)

                self._previous_pixel = pixel

        if self._run:
            data += self._write_run()
        data += bytes((0, 0, 0, 0, 0, 0, 0, 1))  # padding

        return len(data), 0, data


Image.register_open(QoiImageFile.format, QoiImageFile, _accept)
Image.register_decoder("qoi", QoiDecoder)
Image.register_extension(QoiImageFile.format, ".qoi")

Image.register_save(QoiImageFile.format, _save)
Image.register_encoder("qoi", QoiEncoder)
