from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING, cast

import matplotlib.path as mpath
import numpy as np

from contourpy import FillType, LineType
from contourpy.array import codes_from_offsets

if TYPE_CHECKING:
    from contourpy._contourpy import FillReturn, LineReturn, LineReturn_Separate


def filled_to_mpl_paths(filled: FillReturn, fill_type: FillType) -> list[mpath.Path]:
    if fill_type in (FillType.OuterCode, FillType.ChunkCombinedCode):
        paths = [mpath.Path(points, codes) for points, codes in zip(*filled) if points is not None]
    elif fill_type in (FillType.OuterOffset, FillType.ChunkCombinedOffset):
        paths = [mpath.Path(points, codes_from_offsets(offsets))
                 for points, offsets in zip(*filled) if points is not None]
    elif fill_type == FillType.ChunkCombinedCodeOffset:
        paths = []
        for points, codes, outer_offsets in zip(*filled):
            if points is None:
                continue
            points = np.split(points, outer_offsets[1:-1])
            codes = np.split(codes, outer_offsets[1:-1])
            paths += [mpath.Path(p, c) for p, c in zip(points, codes)]
    elif fill_type == FillType.ChunkCombinedOffsetOffset:
        paths = []
        for points, offsets, outer_offsets in zip(*filled):
            if points is None:
                continue
            for i in range(len(outer_offsets)-1):
                offs = offsets[outer_offsets[i]:outer_offsets[i+1]+1]
                pts = points[offs[0]:offs[-1]]
                paths += [mpath.Path(pts, codes_from_offsets(offs - offs[0]))]
    else:
        raise RuntimeError(f"Conversion of FillType {fill_type} to MPL Paths is not implemented")
    return paths


def lines_to_mpl_paths(lines: LineReturn, line_type: LineType) -> list[mpath.Path]:
    if line_type == LineType.Separate:
        if TYPE_CHECKING:
            lines = cast(LineReturn_Separate, lines)
        paths = []
        for line in lines:
            # Drawing as Paths so that they can be closed correctly.
            closed = line[0, 0] == line[-1, 0] and line[0, 1] == line[-1, 1]
            paths.append(mpath.Path(line, closed=closed))
    elif line_type in (LineType.SeparateCode, LineType.ChunkCombinedCode):
        paths = [mpath.Path(points, codes) for points, codes in zip(*lines) if points is not None]
    elif line_type == LineType.ChunkCombinedOffset:
        paths = []
        for points, offsets in zip(*lines):
            if points is None:
                continue
            for i in range(len(offsets)-1):
                line = points[offsets[i]:offsets[i+1]]
                closed = line[0, 0] == line[-1, 0] and line[0, 1] == line[-1, 1]
                paths.append(mpath.Path(line, closed=closed))
    elif line_type == LineType.ChunkCombinedNan:
        paths = []
        for points in lines[0]:
            if points is None:
                continue
            nan_offsets = np.nonzero(np.isnan(points[:, 0]))[0]
            nan_offsets = np.concatenate([[-1], nan_offsets, [len(points)]])
            for s, e in pairwise(nan_offsets):
                line = points[s+1:e]
                closed = line[0, 0] == line[-1, 0] and line[0, 1] == line[-1, 1]
                paths.append(mpath.Path(line, closed=closed))
    else:
        raise RuntimeError(f"Conversion of LineType {line_type} to MPL Paths is not implemented")
    return paths
