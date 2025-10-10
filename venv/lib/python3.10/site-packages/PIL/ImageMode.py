#
# The Python Imaging Library.
# $Id$
#
# standard mode descriptors
#
# History:
# 2006-03-20 fl   Added
#
# Copyright (c) 2006 by Secret Labs AB.
# Copyright (c) 2006 by Fredrik Lundh.
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import sys
from functools import lru_cache
from typing import NamedTuple

from ._deprecate import deprecate


class ModeDescriptor(NamedTuple):
    """Wrapper for mode strings."""

    mode: str
    bands: tuple[str, ...]
    basemode: str
    basetype: str
    typestr: str

    def __str__(self) -> str:
        return self.mode


@lru_cache
def getmode(mode: str) -> ModeDescriptor:
    """Gets a mode descriptor for the given mode."""
    endian = "<" if sys.byteorder == "little" else ">"

    modes = {
        # core modes
        # Bits need to be extended to bytes
        "1": ("L", "L", ("1",), "|b1"),
        "L": ("L", "L", ("L",), "|u1"),
        "I": ("L", "I", ("I",), f"{endian}i4"),
        "F": ("L", "F", ("F",), f"{endian}f4"),
        "P": ("P", "L", ("P",), "|u1"),
        "RGB": ("RGB", "L", ("R", "G", "B"), "|u1"),
        "RGBX": ("RGB", "L", ("R", "G", "B", "X"), "|u1"),
        "RGBA": ("RGB", "L", ("R", "G", "B", "A"), "|u1"),
        "CMYK": ("RGB", "L", ("C", "M", "Y", "K"), "|u1"),
        "YCbCr": ("RGB", "L", ("Y", "Cb", "Cr"), "|u1"),
        # UNDONE - unsigned |u1i1i1
        "LAB": ("RGB", "L", ("L", "A", "B"), "|u1"),
        "HSV": ("RGB", "L", ("H", "S", "V"), "|u1"),
        # extra experimental modes
        "RGBa": ("RGB", "L", ("R", "G", "B", "a"), "|u1"),
        "BGR;15": ("RGB", "L", ("B", "G", "R"), "|u1"),
        "BGR;16": ("RGB", "L", ("B", "G", "R"), "|u1"),
        "BGR;24": ("RGB", "L", ("B", "G", "R"), "|u1"),
        "LA": ("L", "L", ("L", "A"), "|u1"),
        "La": ("L", "L", ("L", "a"), "|u1"),
        "PA": ("RGB", "L", ("P", "A"), "|u1"),
    }
    if mode in modes:
        if mode in ("BGR;15", "BGR;16", "BGR;24"):
            deprecate(mode, 12)
        base_mode, base_type, bands, type_str = modes[mode]
        return ModeDescriptor(mode, bands, base_mode, base_type, type_str)

    mapping_modes = {
        # I;16 == I;16L, and I;32 == I;32L
        "I;16": "<u2",
        "I;16S": "<i2",
        "I;16L": "<u2",
        "I;16LS": "<i2",
        "I;16B": ">u2",
        "I;16BS": ">i2",
        "I;16N": f"{endian}u2",
        "I;16NS": f"{endian}i2",
        "I;32": "<u4",
        "I;32B": ">u4",
        "I;32L": "<u4",
        "I;32S": "<i4",
        "I;32BS": ">i4",
        "I;32LS": "<i4",
    }

    type_str = mapping_modes[mode]
    return ModeDescriptor(mode, ("I",), "L", "L", type_str)
