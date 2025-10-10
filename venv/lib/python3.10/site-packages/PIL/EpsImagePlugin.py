#
# The Python Imaging Library.
# $Id$
#
# EPS file handling
#
# History:
# 1995-09-01 fl   Created (0.1)
# 1996-05-18 fl   Don't choke on "atend" fields, Ghostscript interface (0.2)
# 1996-08-22 fl   Don't choke on floating point BoundingBox values
# 1996-08-23 fl   Handle files from Macintosh (0.3)
# 2001-02-17 fl   Use 're' instead of 'regex' (Python 2.1) (0.4)
# 2003-09-07 fl   Check gs.close status (from Federico Di Gregorio) (0.5)
# 2014-05-07 e    Handling of EPS with binary preview and fixed resolution
#                 resizing
#
# Copyright (c) 1997-2003 by Secret Labs AB.
# Copyright (c) 1995-2003 by Fredrik Lundh
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import tempfile
from typing import IO

from . import Image, ImageFile
from ._binary import i32le as i32

# --------------------------------------------------------------------


split = re.compile(r"^%%([^:]*):[ \t]*(.*)[ \t]*$")
field = re.compile(r"^%[%!\w]([^:]*)[ \t]*$")

gs_binary: str | bool | None = None
gs_windows_binary = None


def has_ghostscript() -> bool:
    global gs_binary, gs_windows_binary
    if gs_binary is None:
        if sys.platform.startswith("win"):
            if gs_windows_binary is None:
                import shutil

                for binary in ("gswin32c", "gswin64c", "gs"):
                    if shutil.which(binary) is not None:
                        gs_windows_binary = binary
                        break
                else:
                    gs_windows_binary = False
            gs_binary = gs_windows_binary
        else:
            try:
                subprocess.check_call(["gs", "--version"], stdout=subprocess.DEVNULL)
                gs_binary = "gs"
            except OSError:
                gs_binary = False
    return gs_binary is not False


def Ghostscript(
    tile: list[ImageFile._Tile],
    size: tuple[int, int],
    fp: IO[bytes],
    scale: int = 1,
    transparency: bool = False,
) -> Image.core.ImagingCore:
    """Render an image using Ghostscript"""
    global gs_binary
    if not has_ghostscript():
        msg = "Unable to locate Ghostscript on paths"
        raise OSError(msg)
    assert isinstance(gs_binary, str)

    # Unpack decoder tile
    args = tile[0].args
    assert isinstance(args, tuple)
    length, bbox = args

    # Hack to support hi-res rendering
    scale = int(scale) or 1
    width = size[0] * scale
    height = size[1] * scale
    # resolution is dependent on bbox and size
    res_x = 72.0 * width / (bbox[2] - bbox[0])
    res_y = 72.0 * height / (bbox[3] - bbox[1])

    out_fd, outfile = tempfile.mkstemp()
    os.close(out_fd)

    infile_temp = None
    if hasattr(fp, "name") and os.path.exists(fp.name):
        infile = fp.name
    else:
        in_fd, infile_temp = tempfile.mkstemp()
        os.close(in_fd)
        infile = infile_temp

        # Ignore length and offset!
        # Ghostscript can read it
        # Copy whole file to read in Ghostscript
        with open(infile_temp, "wb") as f:
            # fetch length of fp
            fp.seek(0, io.SEEK_END)
            fsize = fp.tell()
            # ensure start position
            # go back
            fp.seek(0)
            lengthfile = fsize
            while lengthfile > 0:
                s = fp.read(min(lengthfile, 100 * 1024))
                if not s:
                    break
                lengthfile -= len(s)
                f.write(s)

    if transparency:
        # "RGBA"
        device = "pngalpha"
    else:
        # "pnmraw" automatically chooses between
        # PBM ("1"), PGM ("L"), and PPM ("RGB").
        device = "pnmraw"

    # Build Ghostscript command
    command = [
        gs_binary,
        "-q",  # quiet mode
        f"-g{width:d}x{height:d}",  # set output geometry (pixels)
        f"-r{res_x:f}x{res_y:f}",  # set input DPI (dots per inch)
        "-dBATCH",  # exit after processing
        "-dNOPAUSE",  # don't pause between pages
        "-dSAFER",  # safe mode
        f"-sDEVICE={device}",
        f"-sOutputFile={outfile}",  # output file
        # adjust for image origin
        "-c",
        f"{-bbox[0]} {-bbox[1]} translate",
        "-f",
        infile,  # input file
        # showpage (see https://bugs.ghostscript.com/show_bug.cgi?id=698272)
        "-c",
        "showpage",
    ]

    # push data through Ghostscript
    try:
        startupinfo = None
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.check_call(command, startupinfo=startupinfo)
        with Image.open(outfile) as out_im:
            out_im.load()
            return out_im.im.copy()
    finally:
        try:
            os.unlink(outfile)
            if infile_temp:
                os.unlink(infile_temp)
        except OSError:
            pass


def _accept(prefix: bytes) -> bool:
    return prefix.startswith(b"%!PS") or (
        len(prefix) >= 4 and i32(prefix) == 0xC6D3D0C5
    )


##
# Image plugin for Encapsulated PostScript. This plugin supports only
# a few variants of this format.


class EpsImageFile(ImageFile.ImageFile):
    """EPS File Parser for the Python Imaging Library"""

    format = "EPS"
    format_description = "Encapsulated Postscript"

    mode_map = {1: "L", 2: "LAB", 3: "RGB", 4: "CMYK"}

    def _open(self) -> None:
        (length, offset) = self._find_offset(self.fp)

        # go to offset - start of "%!PS"
        self.fp.seek(offset)

        self._mode = "RGB"

        # When reading header comments, the first comment is used.
        # When reading trailer comments, the last comment is used.
        bounding_box: list[int] | None = None
        imagedata_size: tuple[int, int] | None = None

        byte_arr = bytearray(255)
        bytes_mv = memoryview(byte_arr)
        bytes_read = 0
        reading_header_comments = True
        reading_trailer_comments = False
        trailer_reached = False

        def check_required_header_comments() -> None:
            """
            The EPS specification requires that some headers exist.
            This should be checked when the header comments formally end,
            when image data starts, or when the file ends, whichever comes first.
            """
            if "PS-Adobe" not in self.info:
                msg = 'EPS header missing "%!PS-Adobe" comment'
                raise SyntaxError(msg)
            if "BoundingBox" not in self.info:
                msg = 'EPS header missing "%%BoundingBox" comment'
                raise SyntaxError(msg)

        def read_comment(s: str) -> bool:
            nonlocal bounding_box, reading_trailer_comments
            try:
                m = split.match(s)
            except re.error as e:
                msg = "not an EPS file"
                raise SyntaxError(msg) from e

            if not m:
                return False

            k, v = m.group(1, 2)
            self.info[k] = v
            if k == "BoundingBox":
                if v == "(atend)":
                    reading_trailer_comments = True
                elif not bounding_box or (trailer_reached and reading_trailer_comments):
                    try:
                        # Note: The DSC spec says that BoundingBox
                        # fields should be integers, but some drivers
                        # put floating point values there anyway.
                        bounding_box = [int(float(i)) for i in v.split()]
                    except Exception:
                        pass
            return True

        while True:
            byte = self.fp.read(1)
            if byte == b"":
                # if we didn't read a byte we must be at the end of the file
                if bytes_read == 0:
                    if reading_header_comments:
                        check_required_header_comments()
                    break
            elif byte in b"\r\n":
                # if we read a line ending character, ignore it and parse what
                # we have already read. if we haven't read any other characters,
                # continue reading
                if bytes_read == 0:
                    continue
            else:
                # ASCII/hexadecimal lines in an EPS file must not exceed
                # 255 characters, not including line ending characters
                if bytes_read >= 255:
                    # only enforce this for lines starting with a "%",
                    # otherwise assume it's binary data
                    if byte_arr[0] == ord("%"):
                        msg = "not an EPS file"
                        raise SyntaxError(msg)
                    else:
                        if reading_header_comments:
                            check_required_header_comments()
                            reading_header_comments = False
                        # reset bytes_read so we can keep reading
                        # data until the end of the line
                        bytes_read = 0
                byte_arr[bytes_read] = byte[0]
                bytes_read += 1
                continue

            if reading_header_comments:
                # Load EPS header

                # if this line doesn't start with a "%",
                # or does start with "%%EndComments",
                # then we've reached the end of the header/comments
                if byte_arr[0] != ord("%") or bytes_mv[:13] == b"%%EndComments":
                    check_required_header_comments()
                    reading_header_comments = False
                    continue

                s = str(bytes_mv[:bytes_read], "latin-1")
                if not read_comment(s):
                    m = field.match(s)
                    if m:
                        k = m.group(1)
                        if k.startswith("PS-Adobe"):
                            self.info["PS-Adobe"] = k[9:]
                        else:
                            self.info[k] = ""
                    elif s[0] == "%":
                        # handle non-DSC PostScript comments that some
                        # tools mistakenly put in the Comments section
                        pass
                    else:
                        msg = "bad EPS header"
                        raise OSError(msg)
            elif bytes_mv[:11] == b"%ImageData:":
                # Check for an "ImageData" descriptor
                # https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/#50577413_pgfId-1035096

                # If we've already read an "ImageData" descriptor,
                # don't read another one.
                if imagedata_size:
                    bytes_read = 0
                    continue

                # Values:
                # columns
                # rows
                # bit depth (1 or 8)
                # mode (1: L, 2: LAB, 3: RGB, 4: CMYK)
                # number of padding channels
                # block size (number of bytes per row per channel)
                # binary/ascii (1: binary, 2: ascii)
                # data start identifier (the image data follows after a single line
                #   consisting only of this quoted value)
                image_data_values = byte_arr[11:bytes_read].split(None, 7)
                columns, rows, bit_depth, mode_id = (
                    int(value) for value in image_data_values[:4]
                )

                if bit_depth == 1:
                    self._mode = "1"
                elif bit_depth == 8:
                    try:
                        self._mode = self.mode_map[mode_id]
                    except ValueError:
                        break
                else:
                    break

                # Parse the columns and rows after checking the bit depth and mode
                # in case the bit depth and/or mode are invalid.
                imagedata_size = columns, rows
            elif bytes_mv[:5] == b"%%EOF":
                break
            elif trailer_reached and reading_trailer_comments:
                # Load EPS trailer
                s = str(bytes_mv[:bytes_read], "latin-1")
                read_comment(s)
            elif bytes_mv[:9] == b"%%Trailer":
                trailer_reached = True
            bytes_read = 0

        # A "BoundingBox" is always required,
        # even if an "ImageData" descriptor size exists.
        if not bounding_box:
            msg = "cannot determine EPS bounding box"
            raise OSError(msg)

        # An "ImageData" size takes precedence over the "BoundingBox".
        self._size = imagedata_size or (
            bounding_box[2] - bounding_box[0],
            bounding_box[3] - bounding_box[1],
        )

        self.tile = [
            ImageFile._Tile("eps", (0, 0) + self.size, offset, (length, bounding_box))
        ]

    def _find_offset(self, fp: IO[bytes]) -> tuple[int, int]:
        s = fp.read(4)

        if s == b"%!PS":
            # for HEAD without binary preview
            fp.seek(0, io.SEEK_END)
            length = fp.tell()
            offset = 0
        elif i32(s) == 0xC6D3D0C5:
            # FIX for: Some EPS file not handled correctly / issue #302
            # EPS can contain binary data
            # or start directly with latin coding
            # more info see:
            # https://web.archive.org/web/20160528181353/http://partners.adobe.com/public/developer/en/ps/5002.EPSF_Spec.pdf
            s = fp.read(8)
            offset = i32(s)
            length = i32(s, 4)
        else:
            msg = "not an EPS file"
            raise SyntaxError(msg)

        return length, offset

    def load(
        self, scale: int = 1, transparency: bool = False
    ) -> Image.core.PixelAccess | None:
        # Load EPS via Ghostscript
        if self.tile:
            self.im = Ghostscript(self.tile, self.size, self.fp, scale, transparency)
            self._mode = self.im.mode
            self._size = self.im.size
            self.tile = []
        return Image.Image.load(self)

    def load_seek(self, pos: int) -> None:
        # we can't incrementally load, so force ImageFile.parser to
        # use our custom load method by defining this method.
        pass


# --------------------------------------------------------------------


def _save(im: Image.Image, fp: IO[bytes], filename: str | bytes, eps: int = 1) -> None:
    """EPS Writer for the Python Imaging Library."""

    # make sure image data is available
    im.load()

    # determine PostScript image mode
    if im.mode == "L":
        operator = (8, 1, b"image")
    elif im.mode == "RGB":
        operator = (8, 3, b"false 3 colorimage")
    elif im.mode == "CMYK":
        operator = (8, 4, b"false 4 colorimage")
    else:
        msg = "image mode is not supported"
        raise ValueError(msg)

    if eps:
        # write EPS header
        fp.write(b"%!PS-Adobe-3.0 EPSF-3.0\n")
        fp.write(b"%%Creator: PIL 0.1 EpsEncode\n")
        # fp.write("%%CreationDate: %s"...)
        fp.write(b"%%%%BoundingBox: 0 0 %d %d\n" % im.size)
        fp.write(b"%%Pages: 1\n")
        fp.write(b"%%EndComments\n")
        fp.write(b"%%Page: 1 1\n")
        fp.write(b"%%ImageData: %d %d " % im.size)
        fp.write(b'%d %d 0 1 1 "%s"\n' % operator)

    # image header
    fp.write(b"gsave\n")
    fp.write(b"10 dict begin\n")
    fp.write(b"/buf %d string def\n" % (im.size[0] * operator[1]))
    fp.write(b"%d %d scale\n" % im.size)
    fp.write(b"%d %d 8\n" % im.size)  # <= bits
    fp.write(b"[%d 0 0 -%d 0 %d]\n" % (im.size[0], im.size[1], im.size[1]))
    fp.write(b"{ currentfile buf readhexstring pop } bind\n")
    fp.write(operator[2] + b"\n")
    if hasattr(fp, "flush"):
        fp.flush()

    ImageFile._save(im, fp, [ImageFile._Tile("eps", (0, 0) + im.size)])

    fp.write(b"\n%%%%EndBinary\n")
    fp.write(b"grestore end\n")
    if hasattr(fp, "flush"):
        fp.flush()


# --------------------------------------------------------------------


Image.register_open(EpsImageFile.format, EpsImageFile, _accept)

Image.register_save(EpsImageFile.format, _save)

Image.register_extensions(EpsImageFile.format, [".ps", ".eps"])

Image.register_mime(EpsImageFile.format, "application/postscript")
