from __future__ import annotations

from typing import TYPE_CHECKING, cast

from contourpy import FillType, LineType
from contourpy.array import offsets_from_codes
from contourpy.convert import convert_lines
from contourpy.dechunk import dechunk_lines

if TYPE_CHECKING:
    from contourpy._contourpy import (
        CoordinateArray,
        FillReturn,
        LineReturn,
        LineReturn_ChunkCombinedNan,
    )


def filled_to_bokeh(
    filled: FillReturn,
    fill_type: FillType,
) -> tuple[list[list[CoordinateArray]], list[list[CoordinateArray]]]:
    xs: list[list[CoordinateArray]] = []
    ys: list[list[CoordinateArray]] = []
    if fill_type in (FillType.OuterOffset, FillType.ChunkCombinedOffset,
                     FillType.OuterCode, FillType.ChunkCombinedCode):
        have_codes = fill_type in (FillType.OuterCode, FillType.ChunkCombinedCode)

        for points, offsets in zip(*filled):
            if points is None:
                continue
            if have_codes:
                offsets = offsets_from_codes(offsets)
            xs.append([])  # New outer with zero or more holes.
            ys.append([])
            for i in range(len(offsets)-1):
                xys = points[offsets[i]:offsets[i+1]]
                xs[-1].append(xys[:, 0])
                ys[-1].append(xys[:, 1])
    elif fill_type in (FillType.ChunkCombinedCodeOffset, FillType.ChunkCombinedOffsetOffset):
        for points, codes_or_offsets, outer_offsets in zip(*filled):
            if points is None:
                continue
            for j in range(len(outer_offsets)-1):
                if fill_type == FillType.ChunkCombinedCodeOffset:
                    codes = codes_or_offsets[outer_offsets[j]:outer_offsets[j+1]]
                    offsets = offsets_from_codes(codes) + outer_offsets[j]
                else:
                    offsets = codes_or_offsets[outer_offsets[j]:outer_offsets[j+1]+1]
                xs.append([])  # New outer with zero or more holes.
                ys.append([])
                for k in range(len(offsets)-1):
                    xys = points[offsets[k]:offsets[k+1]]
                    xs[-1].append(xys[:, 0])
                    ys[-1].append(xys[:, 1])
    else:
        raise RuntimeError(f"Conversion of FillType {fill_type} to Bokeh is not implemented")

    return xs, ys


def lines_to_bokeh(
    lines: LineReturn,
    line_type: LineType,
) -> tuple[CoordinateArray | None, CoordinateArray | None]:
    lines = convert_lines(lines, line_type, LineType.ChunkCombinedNan)
    lines = dechunk_lines(lines, LineType.ChunkCombinedNan)
    if TYPE_CHECKING:
        lines = cast(LineReturn_ChunkCombinedNan, lines)
    points = lines[0][0]
    if points is None:
        return None, None
    else:
        return points[:, 0], points[:, 1]
