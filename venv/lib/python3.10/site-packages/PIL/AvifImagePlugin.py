from __future__ import annotations

import os
from io import BytesIO
from typing import IO

from . import ExifTags, Image, ImageFile

try:
    from . import _avif

    SUPPORTED = True
except ImportError:
    SUPPORTED = False

# Decoder options as module globals, until there is a way to pass parameters
# to Image.open (see https://github.com/python-pillow/Pillow/issues/569)
DECODE_CODEC_CHOICE = "auto"
DEFAULT_MAX_THREADS = 0


def get_codec_version(codec_name: str) -> str | None:
    versions = _avif.codec_versions()
    for version in versions.split(", "):
        if version.split(" [")[0] == codec_name:
            return version.split(":")[-1].split(" ")[0]
    return None


def _accept(prefix: bytes) -> bool | str:
    if prefix[4:8] != b"ftyp":
        return False
    major_brand = prefix[8:12]
    if major_brand in (
        # coding brands
        b"avif",
        b"avis",
        # We accept files with AVIF container brands; we can't yet know if
        # the ftyp box has the correct compatible brands, but if it doesn't
        # then the plugin will raise a SyntaxError which Pillow will catch
        # before moving on to the next plugin that accepts the file.
        #
        # Also, because this file might not actually be an AVIF file, we
        # don't raise an error if AVIF support isn't properly compiled.
        b"mif1",
        b"msf1",
    ):
        if not SUPPORTED:
            return (
                "image file could not be identified because AVIF support not installed"
            )
        return True
    return False


def _get_default_max_threads() -> int:
    if DEFAULT_MAX_THREADS:
        return DEFAULT_MAX_THREADS
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0))
    else:
        return os.cpu_count() or 1


class AvifImageFile(ImageFile.ImageFile):
    format = "AVIF"
    format_description = "AVIF image"
    __frame = -1

    def _open(self) -> None:
        if not SUPPORTED:
            msg = "image file could not be opened because AVIF support not installed"
            raise SyntaxError(msg)

        if DECODE_CODEC_CHOICE != "auto" and not _avif.decoder_codec_available(
            DECODE_CODEC_CHOICE
        ):
            msg = "Invalid opening codec"
            raise ValueError(msg)
        self._decoder = _avif.AvifDecoder(
            self.fp.read(),
            DECODE_CODEC_CHOICE,
            _get_default_max_threads(),
        )

        # Get info from decoder
        self._size, self.n_frames, self._mode, icc, exif, exif_orientation, xmp = (
            self._decoder.get_info()
        )
        self.is_animated = self.n_frames > 1

        if icc:
            self.info["icc_profile"] = icc
        if xmp:
            self.info["xmp"] = xmp

        if exif_orientation != 1 or exif:
            exif_data = Image.Exif()
            if exif:
                exif_data.load(exif)
                original_orientation = exif_data.get(ExifTags.Base.Orientation, 1)
            else:
                original_orientation = 1
            if exif_orientation != original_orientation:
                exif_data[ExifTags.Base.Orientation] = exif_orientation
                exif = exif_data.tobytes()
        if exif:
            self.info["exif"] = exif
        self.seek(0)

    def seek(self, frame: int) -> None:
        if not self._seek_check(frame):
            return

        # Set tile
        self.__frame = frame
        self.tile = [ImageFile._Tile("raw", (0, 0) + self.size, 0, self.mode)]

    def load(self) -> Image.core.PixelAccess | None:
        if self.tile:
            # We need to load the image data for this frame
            data, timescale, pts_in_timescales, duration_in_timescales = (
                self._decoder.get_frame(self.__frame)
            )
            self.info["timestamp"] = round(1000 * (pts_in_timescales / timescale))
            self.info["duration"] = round(1000 * (duration_in_timescales / timescale))

            if self.fp and self._exclusive_fp:
                self.fp.close()
            self.fp = BytesIO(data)

        return super().load()

    def load_seek(self, pos: int) -> None:
        pass

    def tell(self) -> int:
        return self.__frame


def _save_all(im: Image.Image, fp: IO[bytes], filename: str | bytes) -> None:
    _save(im, fp, filename, save_all=True)


def _save(
    im: Image.Image, fp: IO[bytes], filename: str | bytes, save_all: bool = False
) -> None:
    info = im.encoderinfo.copy()
    if save_all:
        append_images = list(info.get("append_images", []))
    else:
        append_images = []

    total = 0
    for ims in [im] + append_images:
        total += getattr(ims, "n_frames", 1)

    quality = info.get("quality", 75)
    if not isinstance(quality, int) or quality < 0 or quality > 100:
        msg = "Invalid quality setting"
        raise ValueError(msg)

    duration = info.get("duration", 0)
    subsampling = info.get("subsampling", "4:2:0")
    speed = info.get("speed", 6)
    max_threads = info.get("max_threads", _get_default_max_threads())
    codec = info.get("codec", "auto")
    if codec != "auto" and not _avif.encoder_codec_available(codec):
        msg = "Invalid saving codec"
        raise ValueError(msg)
    range_ = info.get("range", "full")
    tile_rows_log2 = info.get("tile_rows", 0)
    tile_cols_log2 = info.get("tile_cols", 0)
    alpha_premultiplied = bool(info.get("alpha_premultiplied", False))
    autotiling = bool(info.get("autotiling", tile_rows_log2 == tile_cols_log2 == 0))

    icc_profile = info.get("icc_profile", im.info.get("icc_profile"))
    exif_orientation = 1
    if exif := info.get("exif"):
        if isinstance(exif, Image.Exif):
            exif_data = exif
        else:
            exif_data = Image.Exif()
            exif_data.load(exif)
        if ExifTags.Base.Orientation in exif_data:
            exif_orientation = exif_data.pop(ExifTags.Base.Orientation)
            exif = exif_data.tobytes() if exif_data else b""
        elif isinstance(exif, Image.Exif):
            exif = exif_data.tobytes()

    xmp = info.get("xmp")

    if isinstance(xmp, str):
        xmp = xmp.encode("utf-8")

    advanced = info.get("advanced")
    if advanced is not None:
        if isinstance(advanced, dict):
            advanced = advanced.items()
        try:
            advanced = tuple(advanced)
        except TypeError:
            invalid = True
        else:
            invalid = any(not isinstance(v, tuple) or len(v) != 2 for v in advanced)
        if invalid:
            msg = (
                "advanced codec options must be a dict of key-value string "
                "pairs or a series of key-value two-tuples"
            )
            raise ValueError(msg)

    # Setup the AVIF encoder
    enc = _avif.AvifEncoder(
        im.size,
        subsampling,
        quality,
        speed,
        max_threads,
        codec,
        range_,
        tile_rows_log2,
        tile_cols_log2,
        alpha_premultiplied,
        autotiling,
        icc_profile or b"",
        exif or b"",
        exif_orientation,
        xmp or b"",
        advanced,
    )

    # Add each frame
    frame_idx = 0
    frame_duration = 0
    cur_idx = im.tell()
    is_single_frame = total == 1
    try:
        for ims in [im] + append_images:
            # Get number of frames in this image
            nfr = getattr(ims, "n_frames", 1)

            for idx in range(nfr):
                ims.seek(idx)

                # Make sure image mode is supported
                frame = ims
                rawmode = ims.mode
                if ims.mode not in {"RGB", "RGBA"}:
                    rawmode = "RGBA" if ims.has_transparency_data else "RGB"
                    frame = ims.convert(rawmode)

                # Update frame duration
                if isinstance(duration, (list, tuple)):
                    frame_duration = duration[frame_idx]
                else:
                    frame_duration = duration

                # Append the frame to the animation encoder
                enc.add(
                    frame.tobytes("raw", rawmode),
                    frame_duration,
                    frame.size,
                    rawmode,
                    is_single_frame,
                )

                # Update frame index
                frame_idx += 1

                if not save_all:
                    break

    finally:
        im.seek(cur_idx)

    # Get the final output from the encoder
    data = enc.finish()
    if data is None:
        msg = "cannot write file as AVIF (encoder returned None)"
        raise OSError(msg)

    fp.write(data)


Image.register_open(AvifImageFile.format, AvifImageFile, _accept)
if SUPPORTED:
    Image.register_save(AvifImageFile.format, _save)
    Image.register_save_all(AvifImageFile.format, _save_all)
    Image.register_extensions(AvifImageFile.format, [".avif", ".avifs"])
    Image.register_mime(AvifImageFile.format, "image/avif")
