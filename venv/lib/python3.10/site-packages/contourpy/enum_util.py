from __future__ import annotations

from contourpy._contourpy import FillType, LineType, ZInterp


def as_fill_type(fill_type: FillType | str) -> FillType:
    """Coerce a FillType or string value to a FillType.

    Args:
        fill_type (FillType or str): Value to convert.

    Return:
        FillType: Converted value.
    """
    if isinstance(fill_type, str):
        try:
            return FillType.__members__[fill_type]
        except KeyError as e:
            raise ValueError(f"'{fill_type}' is not a valid FillType") from e
    else:
        return fill_type


def as_line_type(line_type: LineType | str) -> LineType:
    """Coerce a LineType or string value to a LineType.

    Args:
        line_type (LineType or str): Value to convert.

    Return:
        LineType: Converted value.
    """
    if isinstance(line_type, str):
        try:
            return LineType.__members__[line_type]
        except KeyError as e:
            raise ValueError(f"'{line_type}' is not a valid LineType") from e
    else:
        return line_type


def as_z_interp(z_interp: ZInterp | str) -> ZInterp:
    """Coerce a ZInterp or string value to a ZInterp.

    Args:
        z_interp (ZInterp or str): Value to convert.

    Return:
        ZInterp: Converted value.
    """
    if isinstance(z_interp, str):
        try:
            return ZInterp.__members__[z_interp]
        except KeyError as e:
            raise ValueError(f"'{z_interp}' is not a valid ZInterp") from e
    else:
        return z_interp
