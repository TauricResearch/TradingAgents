from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import numpy as np

from contourpy import FillType, LineType
from contourpy.enum_util import as_fill_type, as_line_type
from contourpy.types import MOVETO, code_dtype, offset_dtype, point_dtype

if TYPE_CHECKING:
    import contourpy._contourpy as cpy


# Minimalist array-checking functions that check dtype, ndims and shape only.
# They do not walk the arrays to check the contents for performance reasons.
def check_code_array(codes: Any) -> None:
    if not isinstance(codes, np.ndarray):
        raise TypeError(f"Expected numpy array not {type(codes)}")
    if codes.dtype != code_dtype:
        raise ValueError(f"Expected numpy array of dtype {code_dtype} not {codes.dtype}")
    if not (codes.ndim == 1 and len(codes) > 1):
        raise ValueError(f"Expected numpy array of shape (?,) not {codes.shape}")
    if codes[0] != MOVETO:
        raise ValueError(f"First element of code array must be {MOVETO}, not {codes[0]}")


def check_offset_array(offsets: Any) -> None:
    if not isinstance(offsets, np.ndarray):
        raise TypeError(f"Expected numpy array not {type(offsets)}")
    if offsets.dtype != offset_dtype:
        raise ValueError(f"Expected numpy array of dtype {offset_dtype} not {offsets.dtype}")
    if not (offsets.ndim == 1 and len(offsets) > 1):
        raise ValueError(f"Expected numpy array of shape (?,) not {offsets.shape}")
    if offsets[0] != 0:
        raise ValueError(f"First element of offset array must be 0, not {offsets[0]}")


def check_point_array(points: Any) -> None:
    if not isinstance(points, np.ndarray):
        raise TypeError(f"Expected numpy array not {type(points)}")
    if points.dtype != point_dtype:
        raise ValueError(f"Expected numpy array of dtype {point_dtype} not {points.dtype}")
    if not (points.ndim == 2 and points.shape[1] ==2 and points.shape[0] > 1):
        raise ValueError(f"Expected numpy array of shape (?, 2) not {points.shape}")


def _check_tuple_of_lists_with_same_length(
    maybe_tuple: Any,
    tuple_length: int,
    allow_empty_lists: bool = True,
) -> None:
    if not isinstance(maybe_tuple, tuple):
        raise TypeError(f"Expected tuple not {type(maybe_tuple)}")
    if len(maybe_tuple) != tuple_length:
        raise ValueError(f"Expected tuple of length {tuple_length} not {len(maybe_tuple)}")
    for maybe_list in maybe_tuple:
        if not isinstance(maybe_list, list):
            msg = f"Expected tuple to contain {tuple_length} lists but found a {type(maybe_list)}"
            raise TypeError(msg)
    lengths = [len(item) for item in maybe_tuple]
    if len(set(lengths)) != 1:
        msg = f"Expected {tuple_length} lists with same length but lengths are {lengths}"
        raise ValueError(msg)
    if not allow_empty_lists and lengths[0] == 0:
        raise ValueError(f"Expected {tuple_length} non-empty lists")


def check_filled(filled: cpy.FillReturn, fill_type: FillType | str) -> None:
    fill_type = as_fill_type(fill_type)

    if fill_type == FillType.OuterCode:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_OuterCode, filled)
        _check_tuple_of_lists_with_same_length(filled, 2)
        for i, (points, codes) in enumerate(zip(*filled)):
            check_point_array(points)
            check_code_array(codes)
            if len(points) != len(codes):
                raise ValueError(f"Points and codes have different lengths in polygon {i}")
    elif fill_type == FillType.OuterOffset:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_OuterOffset, filled)
        _check_tuple_of_lists_with_same_length(filled, 2)
        for i, (points, offsets) in enumerate(zip(*filled)):
            check_point_array(points)
            check_offset_array(offsets)
            if offsets[-1] != len(points):
                raise ValueError(f"Inconsistent points and offsets in polygon {i}")
    elif fill_type == FillType.ChunkCombinedCode:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_ChunkCombinedCode, filled)
        _check_tuple_of_lists_with_same_length(filled, 2, allow_empty_lists=False)
        for chunk, (points_or_none, codes_or_none) in enumerate(zip(*filled)):
            if points_or_none is not None and codes_or_none is not None:
                check_point_array(points_or_none)
                check_code_array(codes_or_none)
                if len(points_or_none) != len(codes_or_none):
                    raise ValueError(f"Points and codes have different lengths in chunk {chunk}")
            elif not (points_or_none is None and codes_or_none is None):
                raise ValueError(f"Inconsistent Nones in chunk {chunk}")
    elif fill_type == FillType.ChunkCombinedOffset:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_ChunkCombinedOffset, filled)
        _check_tuple_of_lists_with_same_length(filled, 2, allow_empty_lists=False)
        for chunk, (points_or_none, offsets_or_none) in enumerate(zip(*filled)):
            if points_or_none is not None and offsets_or_none is not None:
                check_point_array(points_or_none)
                check_offset_array(offsets_or_none)
                if offsets_or_none[-1] != len(points_or_none):
                    raise ValueError(f"Inconsistent points and offsets in chunk {chunk}")
            elif not (points_or_none is None and offsets_or_none is None):
                raise ValueError(f"Inconsistent Nones in chunk {chunk}")
    elif fill_type == FillType.ChunkCombinedCodeOffset:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_ChunkCombinedCodeOffset, filled)
        _check_tuple_of_lists_with_same_length(filled, 3, allow_empty_lists=False)
        for i, (points_or_none, codes_or_none, outer_offsets_or_none) in enumerate(zip(*filled)):
            if (points_or_none is not None and codes_or_none is not None and
                    outer_offsets_or_none is not None):
                check_point_array(points_or_none)
                check_code_array(codes_or_none)
                check_offset_array(outer_offsets_or_none)
                if len(codes_or_none) != len(points_or_none):
                    raise ValueError(f"Points and codes have different lengths in chunk {i}")
                if outer_offsets_or_none[-1] != len(codes_or_none):
                    raise ValueError(f"Inconsistent codes and outer_offsets in chunk {i}")
            elif not (points_or_none is None and codes_or_none is None and
                      outer_offsets_or_none is None):
                raise ValueError(f"Inconsistent Nones in chunk {i}")
    elif fill_type == FillType.ChunkCombinedOffsetOffset:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_ChunkCombinedOffsetOffset, filled)
        _check_tuple_of_lists_with_same_length(filled, 3, allow_empty_lists=False)
        for i, (points_or_none, offsets_or_none, outer_offsets_or_none) in enumerate(zip(*filled)):
            if (points_or_none is not None and offsets_or_none is not None and
                    outer_offsets_or_none is not None):
                check_point_array(points_or_none)
                check_offset_array(offsets_or_none)
                check_offset_array(outer_offsets_or_none)
                if offsets_or_none[-1] != len(points_or_none):
                    raise ValueError(f"Inconsistent points and offsets in chunk {i}")
                if outer_offsets_or_none[-1] != len(offsets_or_none) - 1:
                    raise ValueError(f"Inconsistent offsets and outer_offsets in chunk {i}")
            elif not (points_or_none is None and offsets_or_none is None and
                      outer_offsets_or_none is None):
                raise ValueError(f"Inconsistent Nones in chunk {i}")
    else:
        raise ValueError(f"Invalid FillType {fill_type}")


def check_lines(lines: cpy.LineReturn, line_type: LineType | str) -> None:
    line_type = as_line_type(line_type)

    if line_type == LineType.Separate:
        if TYPE_CHECKING:
            lines = cast(cpy.LineReturn_Separate, lines)
        if not isinstance(lines, list):
            raise TypeError(f"Expected list not {type(lines)}")
        for points in lines:
            check_point_array(points)
    elif line_type == LineType.SeparateCode:
        if TYPE_CHECKING:
            lines = cast(cpy.LineReturn_SeparateCode, lines)
        _check_tuple_of_lists_with_same_length(lines, 2)
        for i, (points, codes) in enumerate(zip(*lines)):
            check_point_array(points)
            check_code_array(codes)
            if len(points) != len(codes):
                raise ValueError(f"Points and codes have different lengths in line {i}")
    elif line_type == LineType.ChunkCombinedCode:
        if TYPE_CHECKING:
            lines = cast(cpy.LineReturn_ChunkCombinedCode, lines)
        _check_tuple_of_lists_with_same_length(lines, 2, allow_empty_lists=False)
        for chunk, (points_or_none, codes_or_none) in enumerate(zip(*lines)):
            if points_or_none is not None and codes_or_none is not None:
                check_point_array(points_or_none)
                check_code_array(codes_or_none)
                if len(points_or_none) != len(codes_or_none):
                    raise ValueError(f"Points and codes have different lengths in chunk {chunk}")
            elif not (points_or_none is None and codes_or_none is None):
                raise ValueError(f"Inconsistent Nones in chunk {chunk}")
    elif line_type == LineType.ChunkCombinedOffset:
        if TYPE_CHECKING:
            lines = cast(cpy.LineReturn_ChunkCombinedOffset, lines)
        _check_tuple_of_lists_with_same_length(lines, 2, allow_empty_lists=False)
        for chunk, (points_or_none, offsets_or_none) in enumerate(zip(*lines)):
            if points_or_none is not None and offsets_or_none is not None:
                check_point_array(points_or_none)
                check_offset_array(offsets_or_none)
                if offsets_or_none[-1] != len(points_or_none):
                    raise ValueError(f"Inconsistent points and offsets in chunk {chunk}")
            elif not (points_or_none is None and offsets_or_none is None):
                raise ValueError(f"Inconsistent Nones in chunk {chunk}")
    elif line_type == LineType.ChunkCombinedNan:
        if TYPE_CHECKING:
            lines = cast(cpy.LineReturn_ChunkCombinedNan, lines)
        _check_tuple_of_lists_with_same_length(lines, 1, allow_empty_lists=False)
        for _chunk, points_or_none in enumerate(lines[0]):
            if points_or_none is not None:
                check_point_array(points_or_none)
    else:
        raise ValueError(f"Invalid LineType {line_type}")
