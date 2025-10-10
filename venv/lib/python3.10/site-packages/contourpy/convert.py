from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING, cast

import numpy as np

from contourpy._contourpy import FillType, LineType
import contourpy.array as arr
from contourpy.enum_util import as_fill_type, as_line_type
from contourpy.typecheck import check_filled, check_lines
from contourpy.types import MOVETO, offset_dtype

if TYPE_CHECKING:
    import contourpy._contourpy as cpy


def _convert_filled_from_OuterCode(
    filled: cpy.FillReturn_OuterCode,
    fill_type_to: FillType,
) -> cpy.FillReturn:
    if fill_type_to == FillType.OuterCode:
        return filled
    elif fill_type_to == FillType.OuterOffset:
        return (filled[0], [arr.offsets_from_codes(codes) for codes in filled[1]])

    if len(filled[0]) > 0:
        points = arr.concat_points(filled[0])
        codes = arr.concat_codes(filled[1])
    else:
        points = None
        codes = None

    if fill_type_to == FillType.ChunkCombinedCode:
        return ([points], [codes])
    elif fill_type_to == FillType.ChunkCombinedOffset:
        return ([points], [None if codes is None else arr.offsets_from_codes(codes)])
    elif fill_type_to == FillType.ChunkCombinedCodeOffset:
        outer_offsets = None if points is None else arr.offsets_from_lengths(filled[0])
        ret1: cpy.FillReturn_ChunkCombinedCodeOffset = ([points], [codes], [outer_offsets])
        return ret1
    elif fill_type_to == FillType.ChunkCombinedOffsetOffset:
        if codes is None:
            ret2: cpy.FillReturn_ChunkCombinedOffsetOffset = ([None], [None], [None])
        else:
            offsets = arr.offsets_from_codes(codes)
            outer_offsets = arr.outer_offsets_from_list_of_codes(filled[1])
            ret2 = ([points], [offsets], [outer_offsets])
        return ret2
    else:
        raise ValueError(f"Invalid FillType {fill_type_to}")


def _convert_filled_from_OuterOffset(
    filled: cpy.FillReturn_OuterOffset,
    fill_type_to: FillType,
) -> cpy.FillReturn:
    if fill_type_to == FillType.OuterCode:
        separate_codes = [arr.codes_from_offsets(offsets) for offsets in filled[1]]
        return (filled[0], separate_codes)
    elif fill_type_to == FillType.OuterOffset:
        return filled

    if len(filled[0]) > 0:
        points = arr.concat_points(filled[0])
        offsets = arr.concat_offsets(filled[1])
    else:
        points = None
        offsets = None

    if fill_type_to == FillType.ChunkCombinedCode:
        return ([points], [None if offsets is None else arr.codes_from_offsets(offsets)])
    elif fill_type_to == FillType.ChunkCombinedOffset:
        return ([points], [offsets])
    elif fill_type_to == FillType.ChunkCombinedCodeOffset:
        if offsets is None:
            ret1: cpy.FillReturn_ChunkCombinedCodeOffset = ([None], [None], [None])
        else:
            codes = arr.codes_from_offsets(offsets)
            outer_offsets = arr.offsets_from_lengths(filled[0])
            ret1 = ([points], [codes], [outer_offsets])
        return ret1
    elif fill_type_to == FillType.ChunkCombinedOffsetOffset:
        if points is None:
            ret2: cpy.FillReturn_ChunkCombinedOffsetOffset = ([None], [None], [None])
        else:
            outer_offsets = arr.outer_offsets_from_list_of_offsets(filled[1])
            ret2 = ([points], [offsets], [outer_offsets])
        return ret2
    else:
        raise ValueError(f"Invalid FillType {fill_type_to}")


def _convert_filled_from_ChunkCombinedCode(
    filled: cpy.FillReturn_ChunkCombinedCode,
    fill_type_to: FillType,
) -> cpy.FillReturn:
    if fill_type_to == FillType.ChunkCombinedCode:
        return filled
    elif fill_type_to == FillType.ChunkCombinedOffset:
        codes = [None if codes is None else arr.offsets_from_codes(codes) for codes in filled[1]]
        return (filled[0], codes)
    else:
        raise ValueError(
            f"Conversion from {FillType.ChunkCombinedCode} to {fill_type_to} not supported")


def _convert_filled_from_ChunkCombinedOffset(
    filled: cpy.FillReturn_ChunkCombinedOffset,
    fill_type_to: FillType,
) -> cpy.FillReturn:
    if fill_type_to == FillType.ChunkCombinedCode:
        chunk_codes: list[cpy.CodeArray | None] = []
        for points, offsets in zip(*filled):
            if points is None:
                chunk_codes.append(None)
            else:
                if TYPE_CHECKING:
                    assert offsets is not None
                chunk_codes.append(arr.codes_from_offsets_and_points(offsets, points))
        return (filled[0], chunk_codes)
    elif fill_type_to == FillType.ChunkCombinedOffset:
        return filled
    else:
        raise ValueError(
            f"Conversion from {FillType.ChunkCombinedOffset} to {fill_type_to} not supported")


def _convert_filled_from_ChunkCombinedCodeOffset(
    filled: cpy.FillReturn_ChunkCombinedCodeOffset,
    fill_type_to: FillType,
) -> cpy.FillReturn:
    if fill_type_to == FillType.OuterCode:
        separate_points = []
        separate_codes = []
        for points, codes, outer_offsets in zip(*filled):
            if points is not None:
                if TYPE_CHECKING:
                    assert codes is not None
                    assert outer_offsets is not None
                separate_points += arr.split_points_by_offsets(points, outer_offsets)
                separate_codes += arr.split_codes_by_offsets(codes, outer_offsets)
        return (separate_points, separate_codes)
    elif fill_type_to == FillType.OuterOffset:
        separate_points = []
        separate_offsets = []
        for points, codes, outer_offsets in zip(*filled):
            if points is not None:
                if TYPE_CHECKING:
                    assert codes is not None
                    assert outer_offsets is not None
                separate_points += arr.split_points_by_offsets(points, outer_offsets)
                separate_codes = arr.split_codes_by_offsets(codes, outer_offsets)
                separate_offsets += [arr.offsets_from_codes(codes) for codes in separate_codes]
        return (separate_points, separate_offsets)
    elif fill_type_to == FillType.ChunkCombinedCode:
        ret1: cpy.FillReturn_ChunkCombinedCode = (filled[0], filled[1])
        return ret1
    elif fill_type_to == FillType.ChunkCombinedOffset:
        all_offsets = [None if codes is None else arr.offsets_from_codes(codes)
                       for codes in filled[1]]
        ret2: cpy.FillReturn_ChunkCombinedOffset = (filled[0], all_offsets)
        return ret2
    elif fill_type_to == FillType.ChunkCombinedCodeOffset:
        return filled
    elif fill_type_to == FillType.ChunkCombinedOffsetOffset:
        chunk_offsets: list[cpy.OffsetArray | None] = []
        chunk_outer_offsets: list[cpy.OffsetArray | None] = []
        for codes, outer_offsets in zip(*filled[1:]):
            if codes is None:
                chunk_offsets.append(None)
                chunk_outer_offsets.append(None)
            else:
                if TYPE_CHECKING:
                    assert outer_offsets is not None
                offsets = arr.offsets_from_codes(codes)
                outer_offsets = np.array([np.nonzero(offsets == oo)[0][0] for oo in outer_offsets],
                                         dtype=offset_dtype)
                chunk_offsets.append(offsets)
                chunk_outer_offsets.append(outer_offsets)
        ret3: cpy.FillReturn_ChunkCombinedOffsetOffset = (
            filled[0], chunk_offsets, chunk_outer_offsets,
        )
        return ret3
    else:
        raise ValueError(f"Invalid FillType {fill_type_to}")


def _convert_filled_from_ChunkCombinedOffsetOffset(
    filled: cpy.FillReturn_ChunkCombinedOffsetOffset,
    fill_type_to: FillType,
) -> cpy.FillReturn:
    if fill_type_to == FillType.OuterCode:
        separate_points = []
        separate_codes = []
        for points, offsets, outer_offsets in zip(*filled):
            if points is not None:
                if TYPE_CHECKING:
                    assert offsets is not None
                    assert outer_offsets is not None
                codes = arr.codes_from_offsets_and_points(offsets, points)
                outer_offsets = offsets[outer_offsets]
                separate_points += arr.split_points_by_offsets(points, outer_offsets)
                separate_codes += arr.split_codes_by_offsets(codes, outer_offsets)
        return (separate_points, separate_codes)
    elif fill_type_to == FillType.OuterOffset:
        separate_points = []
        separate_offsets = []
        for points, offsets, outer_offsets in zip(*filled):
            if points is not None:
                if TYPE_CHECKING:
                    assert offsets is not None
                    assert outer_offsets is not None
                if len(outer_offsets) > 2:
                    separate_offsets += [offsets[s:e+1] - offsets[s] for s, e in
                                         pairwise(outer_offsets)]
                else:
                    separate_offsets.append(offsets)
                separate_points += arr.split_points_by_offsets(points, offsets[outer_offsets])
        return (separate_points, separate_offsets)
    elif fill_type_to == FillType.ChunkCombinedCode:
        chunk_codes: list[cpy.CodeArray | None] = []
        for points, offsets, outer_offsets in zip(*filled):
            if points is None:
                chunk_codes.append(None)
            else:
                if TYPE_CHECKING:
                    assert offsets is not None
                    assert outer_offsets is not None
                chunk_codes.append(arr.codes_from_offsets_and_points(offsets, points))
        ret1: cpy.FillReturn_ChunkCombinedCode = (filled[0], chunk_codes)
        return ret1
    elif fill_type_to == FillType.ChunkCombinedOffset:
        return (filled[0], filled[1])
    elif fill_type_to == FillType.ChunkCombinedCodeOffset:
        chunk_codes = []
        chunk_outer_offsets: list[cpy.OffsetArray | None] = []
        for points, offsets, outer_offsets in zip(*filled):
            if points is None:
                chunk_codes.append(None)
                chunk_outer_offsets.append(None)
            else:
                if TYPE_CHECKING:
                    assert offsets is not None
                    assert outer_offsets is not None
                chunk_codes.append(arr.codes_from_offsets_and_points(offsets, points))
                chunk_outer_offsets.append(offsets[outer_offsets])
        ret2: cpy.FillReturn_ChunkCombinedCodeOffset = (filled[0], chunk_codes, chunk_outer_offsets)
        return ret2
    elif fill_type_to == FillType.ChunkCombinedOffsetOffset:
        return filled
    else:
        raise ValueError(f"Invalid FillType {fill_type_to}")


def convert_filled(
    filled: cpy.FillReturn,
    fill_type_from: FillType | str,
    fill_type_to:  FillType | str,
) -> cpy.FillReturn:
    """Convert filled contours from one :class:`~.FillType` to another.

    Args:
        filled (sequence of arrays): Filled contour polygons to convert, such as those returned by
            :meth:`.ContourGenerator.filled`.
        fill_type_from (FillType or str): :class:`~.FillType` to convert from as enum or
            string equivalent.
        fill_type_to (FillType or str): :class:`~.FillType` to convert to as enum or string
            equivalent.

    Return:
        Converted filled contour polygons.

    When converting non-chunked fill types (``FillType.OuterCode`` or ``FillType.OuterOffset``) to
    chunked ones, all polygons are placed in the first chunk. When converting in the other
    direction, all chunk information is discarded. Converting a fill type that is not aware of the
    relationship between outer boundaries and contained holes (``FillType.ChunkCombinedCode`` or
    ``FillType.ChunkCombinedOffset``) to one that is will raise a ``ValueError``.

    .. versionadded:: 1.2.0
    """
    fill_type_from = as_fill_type(fill_type_from)
    fill_type_to = as_fill_type(fill_type_to)

    check_filled(filled, fill_type_from)

    if fill_type_from == FillType.OuterCode:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_OuterCode, filled)
        return _convert_filled_from_OuterCode(filled, fill_type_to)
    elif fill_type_from == FillType.OuterOffset:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_OuterOffset, filled)
        return _convert_filled_from_OuterOffset(filled, fill_type_to)
    elif fill_type_from == FillType.ChunkCombinedCode:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_ChunkCombinedCode, filled)
        return _convert_filled_from_ChunkCombinedCode(filled, fill_type_to)
    elif fill_type_from == FillType.ChunkCombinedOffset:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_ChunkCombinedOffset, filled)
        return _convert_filled_from_ChunkCombinedOffset(filled, fill_type_to)
    elif fill_type_from == FillType.ChunkCombinedCodeOffset:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_ChunkCombinedCodeOffset, filled)
        return _convert_filled_from_ChunkCombinedCodeOffset(filled, fill_type_to)
    elif fill_type_from == FillType.ChunkCombinedOffsetOffset:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_ChunkCombinedOffsetOffset, filled)
        return _convert_filled_from_ChunkCombinedOffsetOffset(filled, fill_type_to)
    else:
        raise ValueError(f"Invalid FillType {fill_type_from}")


def _convert_lines_from_Separate(
    lines: cpy.LineReturn_Separate,
    line_type_to: LineType,
) -> cpy.LineReturn:
    if line_type_to == LineType.Separate:
        return lines
    elif line_type_to == LineType.SeparateCode:
        separate_codes = [arr.codes_from_points(line) for line in lines]
        return (lines, separate_codes)
    elif line_type_to == LineType.ChunkCombinedCode:
        if not lines:
            ret1: cpy.LineReturn_ChunkCombinedCode = ([None], [None])
        else:
            points = arr.concat_points(lines)
            offsets = arr.offsets_from_lengths(lines)
            codes = arr.codes_from_offsets_and_points(offsets, points)
            ret1 = ([points], [codes])
        return ret1
    elif line_type_to == LineType.ChunkCombinedOffset:
        if not lines:
            ret2: cpy.LineReturn_ChunkCombinedOffset = ([None], [None])
        else:
            ret2 = ([arr.concat_points(lines)], [arr.offsets_from_lengths(lines)])
        return ret2
    elif line_type_to == LineType.ChunkCombinedNan:
        if not lines:
            ret3: cpy.LineReturn_ChunkCombinedNan = ([None],)
        else:
            ret3 = ([arr.concat_points_with_nan(lines)],)
        return ret3
    else:
        raise ValueError(f"Invalid LineType {line_type_to}")


def _convert_lines_from_SeparateCode(
    lines: cpy.LineReturn_SeparateCode,
    line_type_to: LineType,
) -> cpy.LineReturn:
    if line_type_to == LineType.Separate:
        # Drop codes.
        return lines[0]
    elif line_type_to == LineType.SeparateCode:
        return lines
    elif line_type_to == LineType.ChunkCombinedCode:
        if not lines[0]:
            ret1: cpy.LineReturn_ChunkCombinedCode = ([None], [None])
        else:
            ret1 = ([arr.concat_points(lines[0])], [arr.concat_codes(lines[1])])
        return ret1
    elif line_type_to == LineType.ChunkCombinedOffset:
        if not lines[0]:
            ret2: cpy.LineReturn_ChunkCombinedOffset = ([None], [None])
        else:
            ret2 = ([arr.concat_points(lines[0])], [arr.offsets_from_lengths(lines[0])])
        return ret2
    elif line_type_to == LineType.ChunkCombinedNan:
        if not lines[0]:
            ret3: cpy.LineReturn_ChunkCombinedNan = ([None],)
        else:
            ret3 = ([arr.concat_points_with_nan(lines[0])],)
        return ret3
    else:
        raise ValueError(f"Invalid LineType {line_type_to}")


def _convert_lines_from_ChunkCombinedCode(
    lines: cpy.LineReturn_ChunkCombinedCode,
    line_type_to: LineType,
) -> cpy.LineReturn:
    if line_type_to in (LineType.Separate, LineType.SeparateCode):
        separate_lines = []
        for points, codes in zip(*lines):
            if points is not None:
                if TYPE_CHECKING:
                    assert codes is not None
                split_at = np.nonzero(codes == MOVETO)[0]
                if len(split_at) > 1:
                    separate_lines += np.split(points, split_at[1:])
                else:
                    separate_lines.append(points)
        if line_type_to == LineType.Separate:
            return separate_lines
        else:
            separate_codes = [arr.codes_from_points(line) for line in separate_lines]
            return (separate_lines, separate_codes)
    elif line_type_to == LineType.ChunkCombinedCode:
        return lines
    elif line_type_to == LineType.ChunkCombinedOffset:
        chunk_offsets = [None if codes is None else arr.offsets_from_codes(codes)
                         for codes in lines[1]]
        return (lines[0], chunk_offsets)
    elif line_type_to == LineType.ChunkCombinedNan:
        points_nan: list[cpy.PointArray | None] = []
        for points, codes in zip(*lines):
            if points is None:
                points_nan.append(None)
            else:
                if TYPE_CHECKING:
                    assert codes is not None
                offsets = arr.offsets_from_codes(codes)
                points_nan.append(arr.insert_nan_at_offsets(points, offsets))
        return (points_nan,)
    else:
        raise ValueError(f"Invalid LineType {line_type_to}")


def _convert_lines_from_ChunkCombinedOffset(
    lines: cpy.LineReturn_ChunkCombinedOffset,
    line_type_to: LineType,
) -> cpy.LineReturn:
    if line_type_to in (LineType.Separate, LineType.SeparateCode):
        separate_lines = []
        for points, offsets in zip(*lines):
            if points is not None:
                if TYPE_CHECKING:
                    assert offsets is not None
                separate_lines += arr.split_points_by_offsets(points, offsets)
        if line_type_to == LineType.Separate:
            return separate_lines
        else:
            separate_codes = [arr.codes_from_points(line) for line in separate_lines]
            return (separate_lines, separate_codes)
    elif line_type_to == LineType.ChunkCombinedCode:
        chunk_codes: list[cpy.CodeArray | None] = []
        for points, offsets in zip(*lines):
            if points is None:
                chunk_codes.append(None)
            else:
                if TYPE_CHECKING:
                    assert offsets is not None
                chunk_codes.append(arr.codes_from_offsets_and_points(offsets, points))
        return (lines[0], chunk_codes)
    elif line_type_to == LineType.ChunkCombinedOffset:
        return lines
    elif line_type_to == LineType.ChunkCombinedNan:
        points_nan: list[cpy.PointArray | None] = []
        for points, offsets in zip(*lines):
            if points is None:
                points_nan.append(None)
            else:
                if TYPE_CHECKING:
                    assert offsets is not None
                points_nan.append(arr.insert_nan_at_offsets(points, offsets))
        return (points_nan,)
    else:
        raise ValueError(f"Invalid LineType {line_type_to}")


def _convert_lines_from_ChunkCombinedNan(
    lines: cpy.LineReturn_ChunkCombinedNan,
    line_type_to: LineType,
) -> cpy.LineReturn:
    if line_type_to in (LineType.Separate, LineType.SeparateCode):
        separate_lines = []
        for points in lines[0]:
            if points is not None:
                separate_lines += arr.split_points_at_nan(points)
        if line_type_to == LineType.Separate:
            return separate_lines
        else:
            separate_codes = [arr.codes_from_points(points) for points in separate_lines]
            return (separate_lines, separate_codes)
    elif line_type_to == LineType.ChunkCombinedCode:
        chunk_points: list[cpy.PointArray | None] = []
        chunk_codes: list[cpy.CodeArray | None] = []
        for points in lines[0]:
            if points is None:
                chunk_points.append(None)
                chunk_codes.append(None)
            else:
                points, offsets = arr.remove_nan(points)
                chunk_points.append(points)
                chunk_codes.append(arr.codes_from_offsets_and_points(offsets, points))
        return (chunk_points, chunk_codes)
    elif line_type_to == LineType.ChunkCombinedOffset:
        chunk_points = []
        chunk_offsets: list[cpy.OffsetArray | None] = []
        for points in lines[0]:
            if points is None:
                chunk_points.append(None)
                chunk_offsets.append(None)
            else:
                points, offsets = arr.remove_nan(points)
                chunk_points.append(points)
                chunk_offsets.append(offsets)
        return (chunk_points, chunk_offsets)
    elif line_type_to == LineType.ChunkCombinedNan:
        return lines
    else:
        raise ValueError(f"Invalid LineType {line_type_to}")


def convert_lines(
    lines: cpy.LineReturn,
    line_type_from: LineType | str,
    line_type_to:  LineType | str,
) -> cpy.LineReturn:
    """Convert contour lines from one :class:`~.LineType` to another.

    Args:
        lines (sequence of arrays): Contour lines to convert, such as those returned by
            :meth:`.ContourGenerator.lines`.
        line_type_from (LineType or str): :class:`~.LineType` to convert from as enum or
            string equivalent.
        line_type_to (LineType or str): :class:`~.LineType` to convert to as enum or string
            equivalent.

    Return:
        Converted contour lines.

    When converting non-chunked line types (``LineType.Separate`` or ``LineType.SeparateCode``) to
    chunked ones (``LineType.ChunkCombinedCode``, ``LineType.ChunkCombinedOffset`` or
    ``LineType.ChunkCombinedNan``), all lines are placed in the first chunk. When converting in the
    other direction, all chunk information is discarded.

    .. versionadded:: 1.2.0
    """
    line_type_from = as_line_type(line_type_from)
    line_type_to = as_line_type(line_type_to)

    check_lines(lines, line_type_from)

    if line_type_from == LineType.Separate:
        if TYPE_CHECKING:
            lines = cast(cpy.LineReturn_Separate, lines)
        return _convert_lines_from_Separate(lines, line_type_to)
    elif line_type_from == LineType.SeparateCode:
        if TYPE_CHECKING:
            lines = cast(cpy.LineReturn_SeparateCode, lines)
        return _convert_lines_from_SeparateCode(lines, line_type_to)
    elif line_type_from == LineType.ChunkCombinedCode:
        if TYPE_CHECKING:
            lines = cast(cpy.LineReturn_ChunkCombinedCode, lines)
        return _convert_lines_from_ChunkCombinedCode(lines, line_type_to)
    elif line_type_from == LineType.ChunkCombinedOffset:
        if TYPE_CHECKING:
            lines = cast(cpy.LineReturn_ChunkCombinedOffset, lines)
        return _convert_lines_from_ChunkCombinedOffset(lines, line_type_to)
    elif line_type_from == LineType.ChunkCombinedNan:
        if TYPE_CHECKING:
            lines = cast(cpy.LineReturn_ChunkCombinedNan, lines)
        return _convert_lines_from_ChunkCombinedNan(lines, line_type_to)
    else:
        raise ValueError(f"Invalid LineType {line_type_from}")


def convert_multi_filled(
    multi_filled: list[cpy.FillReturn],
    fill_type_from: FillType | str,
    fill_type_to:  FillType | str,
) -> list[cpy.FillReturn]:
    """Convert multiple sets of filled contours from one :class:`~.FillType` to another.

    Args:
        multi_filled (nested sequence of arrays): Filled contour polygons to convert, such as those
            returned by :meth:`.ContourGenerator.multi_filled`.
        fill_type_from (FillType or str): :class:`~.FillType` to convert from as enum or
            string equivalent.
        fill_type_to (FillType or str): :class:`~.FillType` to convert to as enum or string
            equivalent.

    Return:
        Converted sets filled contour polygons.

    When converting non-chunked fill types (``FillType.OuterCode`` or ``FillType.OuterOffset``) to
    chunked ones, all polygons are placed in the first chunk. When converting in the other
    direction, all chunk information is discarded. Converting a fill type that is not aware of the
    relationship between outer boundaries and contained holes (``FillType.ChunkCombinedCode`` or
    ``FillType.ChunkCombinedOffset``) to one that is will raise a ``ValueError``.

    .. versionadded:: 1.3.0
    """
    fill_type_from = as_fill_type(fill_type_from)
    fill_type_to = as_fill_type(fill_type_to)

    return [convert_filled(filled, fill_type_from, fill_type_to) for filled in multi_filled]


def convert_multi_lines(
    multi_lines: list[cpy.LineReturn],
    line_type_from: LineType | str,
    line_type_to:  LineType | str,
) -> list[cpy.LineReturn]:
    """Convert multiple sets of contour lines from one :class:`~.LineType` to another.

    Args:
        multi_lines (nested sequence of arrays): Contour lines to convert, such as those returned by
            :meth:`.ContourGenerator.multi_lines`.
        line_type_from (LineType or str): :class:`~.LineType` to convert from as enum or
            string equivalent.
        line_type_to (LineType or str): :class:`~.LineType` to convert to as enum or string
            equivalent.

    Return:
        Converted set of contour lines.

    When converting non-chunked line types (``LineType.Separate`` or ``LineType.SeparateCode``) to
    chunked ones (``LineType.ChunkCombinedCode``, ``LineType.ChunkCombinedOffset`` or
    ``LineType.ChunkCombinedNan``), all lines are placed in the first chunk. When converting in the
    other direction, all chunk information is discarded.

    .. versionadded:: 1.3.0
    """
    line_type_from = as_line_type(line_type_from)
    line_type_to = as_line_type(line_type_to)

    return [convert_lines(lines, line_type_from, line_type_to) for lines in multi_lines]
