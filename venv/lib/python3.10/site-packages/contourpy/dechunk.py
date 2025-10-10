from __future__ import annotations

from typing import TYPE_CHECKING, cast

from contourpy._contourpy import FillType, LineType
from contourpy.array import (
    concat_codes_or_none,
    concat_offsets_or_none,
    concat_points_or_none,
    concat_points_or_none_with_nan,
)
from contourpy.enum_util import as_fill_type, as_line_type
from contourpy.typecheck import check_filled, check_lines

if TYPE_CHECKING:
    import contourpy._contourpy as cpy


def dechunk_filled(filled: cpy.FillReturn, fill_type: FillType | str) -> cpy.FillReturn:
    """Return the specified filled contours with chunked data moved into the first chunk.

    Filled contours that are not chunked (``FillType.OuterCode`` and ``FillType.OuterOffset``) and
    those that are but only contain a single chunk are returned unmodified. Individual polygons are
    unchanged, they are not geometrically combined.

    Args:
        filled (sequence of arrays): Filled contour data, such as returned by
            :meth:`.ContourGenerator.filled`.
        fill_type (FillType or str): Type of :meth:`~.ContourGenerator.filled` as enum or string
            equivalent.

    Return:
        Filled contours in a single chunk.

    .. versionadded:: 1.2.0
    """
    fill_type = as_fill_type(fill_type)

    if fill_type in (FillType.OuterCode, FillType.OuterOffset):
        # No-op if fill_type is not chunked.
        return filled

    check_filled(filled, fill_type)
    if len(filled[0]) < 2:
        # No-op if just one chunk.
        return filled

    if TYPE_CHECKING:
        filled = cast(cpy.FillReturn_Chunk, filled)
    points = concat_points_or_none(filled[0])

    if fill_type == FillType.ChunkCombinedCode:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_ChunkCombinedCode, filled)
        if points is None:
            ret1: cpy.FillReturn_ChunkCombinedCode = ([None], [None])
        else:
            ret1 = ([points], [concat_codes_or_none(filled[1])])
        return ret1
    elif fill_type == FillType.ChunkCombinedOffset:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_ChunkCombinedOffset, filled)
        if points is None:
            ret2: cpy.FillReturn_ChunkCombinedOffset = ([None], [None])
        else:
            ret2 = ([points], [concat_offsets_or_none(filled[1])])
        return ret2
    elif fill_type == FillType.ChunkCombinedCodeOffset:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_ChunkCombinedCodeOffset, filled)
        if points is None:
            ret3: cpy.FillReturn_ChunkCombinedCodeOffset = ([None], [None], [None])
        else:
            outer_offsets = concat_offsets_or_none(filled[2])
            ret3 = ([points], [concat_codes_or_none(filled[1])], [outer_offsets])
        return ret3
    elif fill_type == FillType.ChunkCombinedOffsetOffset:
        if TYPE_CHECKING:
            filled = cast(cpy.FillReturn_ChunkCombinedOffsetOffset, filled)
        if points is None:
            ret4: cpy.FillReturn_ChunkCombinedOffsetOffset = ([None], [None], [None])
        else:
            outer_offsets = concat_offsets_or_none(filled[2])
            ret4 = ([points], [concat_offsets_or_none(filled[1])], [outer_offsets])
        return ret4
    else:
        raise ValueError(f"Invalid FillType {fill_type}")


def dechunk_lines(lines: cpy.LineReturn, line_type: LineType | str) -> cpy.LineReturn:
    """Return the specified contour lines with chunked data moved into the first chunk.

    Contour lines that are not chunked (``LineType.Separate`` and ``LineType.SeparateCode``) and
    those that are but only contain a single chunk are returned unmodified. Individual lines are
    unchanged, they are not geometrically combined.

    Args:
        lines (sequence of arrays): Contour line data, such as returned by
            :meth:`.ContourGenerator.lines`.
        line_type (LineType or str): Type of :meth:`~.ContourGenerator.lines` as enum or string
            equivalent.

    Return:
        Contour lines in a single chunk.

    .. versionadded:: 1.2.0
    """
    line_type = as_line_type(line_type)

    if line_type in (LineType.Separate, LineType.SeparateCode):
        # No-op if line_type is not chunked.
        return lines

    check_lines(lines, line_type)
    if len(lines[0]) < 2:
        # No-op if just one chunk.
        return lines

    if TYPE_CHECKING:
        lines = cast(cpy.LineReturn_Chunk, lines)

    if line_type == LineType.ChunkCombinedCode:
        if TYPE_CHECKING:
            lines = cast(cpy.LineReturn_ChunkCombinedCode, lines)
        points = concat_points_or_none(lines[0])
        if points is None:
            ret1: cpy.LineReturn_ChunkCombinedCode = ([None], [None])
        else:
            ret1 = ([points], [concat_codes_or_none(lines[1])])
        return ret1
    elif line_type == LineType.ChunkCombinedOffset:
        if TYPE_CHECKING:
            lines = cast(cpy.LineReturn_ChunkCombinedOffset, lines)
        points = concat_points_or_none(lines[0])
        if points is None:
            ret2: cpy.LineReturn_ChunkCombinedOffset = ([None], [None])
        else:
            ret2 = ([points], [concat_offsets_or_none(lines[1])])
        return ret2
    elif line_type == LineType.ChunkCombinedNan:
        if TYPE_CHECKING:
            lines = cast(cpy.LineReturn_ChunkCombinedNan, lines)
        points = concat_points_or_none_with_nan(lines[0])
        ret3: cpy.LineReturn_ChunkCombinedNan = ([points],)
        return ret3
    else:
        raise ValueError(f"Invalid LineType {line_type}")


def dechunk_multi_filled(
    multi_filled: list[cpy.FillReturn],
    fill_type: FillType | str,
) -> list[cpy.FillReturn]:
    """Return multiple sets of filled contours with chunked data moved into the first chunks.

    Filled contours that are not chunked (``FillType.OuterCode`` and ``FillType.OuterOffset``) and
    those that are but only contain a single chunk are returned unmodified. Individual polygons are
    unchanged, they are not geometrically combined.

    Args:
        multi_filled (nested sequence of arrays): Filled contour data, such as returned by
            :meth:`.ContourGenerator.multi_filled`.
        fill_type (FillType or str): Type of :meth:`~.ContourGenerator.filled` as enum or string
            equivalent.

    Return:
        Multiple sets of filled contours in a single chunk.

    .. versionadded:: 1.3.0
    """
    fill_type = as_fill_type(fill_type)

    if fill_type in (FillType.OuterCode, FillType.OuterOffset):
        # No-op if fill_type is not chunked.
        return multi_filled

    return [dechunk_filled(filled, fill_type) for filled in multi_filled]


def dechunk_multi_lines(
    multi_lines: list[cpy.LineReturn],
    line_type: LineType | str,
) -> list[cpy.LineReturn]:
    """Return multiple sets of contour lines with all chunked data moved into the first chunks.

    Contour lines that are not chunked (``LineType.Separate`` and ``LineType.SeparateCode``) and
    those that are but only contain a single chunk are returned unmodified. Individual lines are
    unchanged, they are not geometrically combined.

    Args:
        multi_lines (nested sequence of arrays): Contour line data, such as returned by
            :meth:`.ContourGenerator.multi_lines`.
        line_type (LineType or str): Type of :meth:`~.ContourGenerator.lines` as enum or string
            equivalent.

    Return:
        Multiple sets of contour lines in a single chunk.

    .. versionadded:: 1.3.0
    """
    line_type = as_line_type(line_type)

    if line_type in (LineType.Separate, LineType.SeparateCode):
        # No-op if line_type is not chunked.
        return multi_lines

    return [dechunk_lines(lines, line_type) for lines in multi_lines]
