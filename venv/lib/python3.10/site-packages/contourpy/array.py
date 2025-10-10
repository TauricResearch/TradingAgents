from __future__ import annotations

from itertools import chain, pairwise
from typing import TYPE_CHECKING

import numpy as np

from contourpy.typecheck import check_code_array, check_offset_array, check_point_array
from contourpy.types import CLOSEPOLY, LINETO, MOVETO, code_dtype, offset_dtype, point_dtype

if TYPE_CHECKING:
    import contourpy._contourpy as cpy


def codes_from_offsets(offsets: cpy.OffsetArray) -> cpy.CodeArray:
    """Determine codes from offsets, assuming they all correspond to closed polygons.
    """
    check_offset_array(offsets)

    n = offsets[-1]
    codes = np.full(n, LINETO, dtype=code_dtype)
    codes[offsets[:-1]] = MOVETO
    codes[offsets[1:] - 1] = CLOSEPOLY
    return codes


def codes_from_offsets_and_points(
    offsets: cpy.OffsetArray,
    points: cpy.PointArray,
) -> cpy.CodeArray:
    """Determine codes from offsets and points, using the equality of the start and end points of
    each line to determine if lines are closed or not.
    """
    check_offset_array(offsets)
    check_point_array(points)

    codes = np.full(len(points), LINETO, dtype=code_dtype)
    codes[offsets[:-1]] = MOVETO

    end_offsets = offsets[1:] - 1
    closed = np.all(points[offsets[:-1]] == points[end_offsets], axis=1)
    codes[end_offsets[closed]] = CLOSEPOLY

    return codes


def codes_from_points(points: cpy.PointArray) -> cpy.CodeArray:
    """Determine codes for a single line, using the equality of the start and end points to
    determine if the line is closed or not.
    """
    check_point_array(points)

    n = len(points)
    codes = np.full(n, LINETO, dtype=code_dtype)
    codes[0] = MOVETO
    if np.all(points[0] == points[-1]):
        codes[-1] = CLOSEPOLY
    return codes


def concat_codes(list_of_codes: list[cpy.CodeArray]) -> cpy.CodeArray:
    """Concatenate a list of codes arrays into a single code array.
    """
    if not list_of_codes:
        raise ValueError("Empty list passed to concat_codes")

    return np.concatenate(list_of_codes, dtype=code_dtype)


def concat_codes_or_none(list_of_codes_or_none: list[cpy.CodeArray | None]) -> cpy.CodeArray | None:
    """Concatenate a list of codes arrays or None into a single code array or None.
    """
    list_of_codes = [codes for codes in list_of_codes_or_none if codes is not None]
    if list_of_codes:
        return concat_codes(list_of_codes)
    else:
        return None


def concat_offsets(list_of_offsets: list[cpy.OffsetArray]) -> cpy.OffsetArray:
    """Concatenate a list of offsets arrays into a single offset array.
    """
    if not list_of_offsets:
        raise ValueError("Empty list passed to concat_offsets")

    n = len(list_of_offsets)
    cumulative = np.cumsum([offsets[-1] for offsets in list_of_offsets], dtype=offset_dtype)
    ret: cpy.OffsetArray = np.concatenate(
        (list_of_offsets[0], *(list_of_offsets[i+1][1:] + cumulative[i] for i in range(n-1))),
        dtype=offset_dtype,
    )
    return ret


def concat_offsets_or_none(
    list_of_offsets_or_none: list[cpy.OffsetArray | None],
) -> cpy.OffsetArray | None:
    """Concatenate a list of offsets arrays or None into a single offset array or None.
    """
    list_of_offsets = [offsets for offsets in list_of_offsets_or_none if offsets is not None]
    if list_of_offsets:
        return concat_offsets(list_of_offsets)
    else:
        return None


def concat_points(list_of_points: list[cpy.PointArray]) -> cpy.PointArray:
    """Concatenate a list of point arrays into a single point array.
    """
    if not list_of_points:
        raise ValueError("Empty list passed to concat_points")

    return np.concatenate(list_of_points, dtype=point_dtype)


def concat_points_or_none(
    list_of_points_or_none: list[cpy.PointArray | None],
) -> cpy.PointArray | None:
    """Concatenate a list of point arrays or None into a single point array or None.
    """
    list_of_points = [points for points in list_of_points_or_none if points is not None]
    if list_of_points:
        return concat_points(list_of_points)
    else:
        return None


def concat_points_or_none_with_nan(
    list_of_points_or_none: list[cpy.PointArray | None],
) -> cpy.PointArray | None:
    """Concatenate a list of points or None into a single point array or None, with NaNs used to
    separate each line.
    """
    list_of_points = [points for points in list_of_points_or_none if points is not None]
    if list_of_points:
        return concat_points_with_nan(list_of_points)
    else:
        return None


def concat_points_with_nan(list_of_points: list[cpy.PointArray]) -> cpy.PointArray:
    """Concatenate a list of points into a single point array with NaNs used to separate each line.
    """
    if not list_of_points:
        raise ValueError("Empty list passed to concat_points_with_nan")

    if len(list_of_points) == 1:
        return list_of_points[0]
    else:
        nan_spacer = np.full((1, 2), np.nan, dtype=point_dtype)
        list_of_points = [list_of_points[0],
                          *list(chain(*((nan_spacer, x) for x in list_of_points[1:])))]
        return concat_points(list_of_points)


def insert_nan_at_offsets(points: cpy.PointArray, offsets: cpy.OffsetArray) -> cpy.PointArray:
    """Insert NaNs into a point array at locations specified by an offset array.
    """
    check_point_array(points)
    check_offset_array(offsets)

    if len(offsets) <= 2:
        return points
    else:
        nan_spacer = np.array([np.nan, np.nan], dtype=point_dtype)
        # Convert offsets to int64 to avoid numpy error when mixing signed and unsigned ints.
        return np.insert(points, offsets[1:-1].astype(np.int64), nan_spacer, axis=0)


def offsets_from_codes(codes: cpy.CodeArray) -> cpy.OffsetArray:
    """Determine offsets from codes using locations of MOVETO codes.
    """
    check_code_array(codes)

    return np.append(np.nonzero(codes == MOVETO)[0], len(codes)).astype(offset_dtype)


def offsets_from_lengths(list_of_points: list[cpy.PointArray]) -> cpy.OffsetArray:
    """Determine offsets from lengths of point arrays.
    """
    if not list_of_points:
        raise ValueError("Empty list passed to offsets_from_lengths")

    return np.cumsum([0] + [len(line) for line in list_of_points], dtype=offset_dtype)


def outer_offsets_from_list_of_codes(list_of_codes: list[cpy.CodeArray]) -> cpy.OffsetArray:
    """Determine outer offsets from codes using locations of MOVETO codes.
    """
    if not list_of_codes:
        raise ValueError("Empty list passed to outer_offsets_from_list_of_codes")

    return np.cumsum([0] + [np.count_nonzero(codes == MOVETO) for codes in list_of_codes],
                     dtype=offset_dtype)


def outer_offsets_from_list_of_offsets(list_of_offsets: list[cpy.OffsetArray]) -> cpy.OffsetArray:
    """Determine outer offsets from a list of offsets.
    """
    if not list_of_offsets:
        raise ValueError("Empty list passed to outer_offsets_from_list_of_offsets")

    return np.cumsum([0] + [len(offsets)-1 for offsets in list_of_offsets], dtype=offset_dtype)


def remove_nan(points: cpy.PointArray) -> tuple[cpy.PointArray, cpy.OffsetArray]:
    """Remove NaN from a points array, also return the offsets corresponding to the NaN removed.
    """
    check_point_array(points)

    nan_offsets = np.nonzero(np.isnan(points[:, 0]))[0]
    if len(nan_offsets) == 0:
        return points, np.array([0, len(points)], dtype=offset_dtype)
    else:
        points = np.delete(points, nan_offsets, axis=0)
        nan_offsets -= np.arange(len(nan_offsets))
        offsets: cpy.OffsetArray = np.empty(len(nan_offsets)+2, dtype=offset_dtype)
        offsets[0] = 0
        offsets[1:-1] = nan_offsets
        offsets[-1] = len(points)
        return points, offsets


def split_codes_by_offsets(codes: cpy.CodeArray, offsets: cpy.OffsetArray) -> list[cpy.CodeArray]:
    """Split a code array at locations specified by an offset array into a list of code arrays.
    """
    check_code_array(codes)
    check_offset_array(offsets)

    if len(offsets) > 2:
        return np.split(codes, offsets[1:-1])
    else:
        return [codes]


def split_points_by_offsets(
    points: cpy.PointArray,
    offsets: cpy.OffsetArray,
) -> list[cpy.PointArray]:
    """Split a point array at locations specified by an offset array into a list of point arrays.
    """
    check_point_array(points)
    check_offset_array(offsets)

    if len(offsets) > 2:
        return np.split(points, offsets[1:-1])
    else:
        return [points]


def split_points_at_nan(points: cpy.PointArray) -> list[cpy.PointArray]:
    """Split a points array at NaNs into a list of point arrays.
    """
    check_point_array(points)

    nan_offsets = np.nonzero(np.isnan(points[:, 0]))[0]
    if len(nan_offsets) == 0:
        return [points]
    else:
        nan_offsets = np.concatenate(([-1], nan_offsets, [len(points)]))
        return [points[s+1:e] for s, e in pairwise(nan_offsets)]
