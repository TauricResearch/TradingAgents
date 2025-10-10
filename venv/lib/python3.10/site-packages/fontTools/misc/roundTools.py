"""
Various round-to-integer helpers.
"""

import math
import functools
import logging

log = logging.getLogger(__name__)

__all__ = [
    "noRound",
    "otRound",
    "maybeRound",
    "roundFunc",
    "nearestMultipleShortestRepr",
]


def noRound(value):
    return value


def otRound(value):
    """Round float value to nearest integer towards ``+Infinity``.

    The OpenType spec (in the section on `"normalization" of OpenType Font Variations <https://docs.microsoft.com/en-us/typography/opentype/spec/otvaroverview#coordinate-scales-and-normalization>`_)
    defines the required method for converting floating point values to
    fixed-point. In particular it specifies the following rounding strategy:

            for fractional values of 0.5 and higher, take the next higher integer;
            for other fractional values, truncate.

    This function rounds the floating-point value according to this strategy
    in preparation for conversion to fixed-point.

    Args:
            value (float): The input floating-point value.

    Returns
            float: The rounded value.
    """
    # See this thread for how we ended up with this implementation:
    # https://github.com/fonttools/fonttools/issues/1248#issuecomment-383198166
    return int(math.floor(value + 0.5))


def maybeRound(v, tolerance, round=otRound):
    rounded = round(v)
    return rounded if abs(rounded - v) <= tolerance else v


def roundFunc(tolerance, round=otRound):
    if tolerance < 0:
        raise ValueError("Rounding tolerance must be positive")

    if tolerance == 0:
        return noRound

    if tolerance >= 0.5:
        return round

    return functools.partial(maybeRound, tolerance=tolerance, round=round)


def nearestMultipleShortestRepr(value: float, factor: float) -> str:
    """Round to nearest multiple of factor and return shortest decimal representation.

    This chooses the float that is closer to a multiple of the given factor while
    having the shortest decimal representation (the least number of fractional decimal
    digits).

    For example, given the following:

    >>> nearestMultipleShortestRepr(-0.61883544921875, 1.0/(1<<14))
    '-0.61884'

    Useful when you need to serialize or print a fixed-point number (or multiples
    thereof, such as F2Dot14 fractions of 180 degrees in COLRv1 PaintRotate) in
    a human-readable form.

    Args:
        value (value): The value to be rounded and serialized.
        factor (float): The value which the result is a close multiple of.

    Returns:
        str: A compact string representation of the value.
    """
    if not value:
        return "0.0"

    value = otRound(value / factor) * factor
    eps = 0.5 * factor
    lo = value - eps
    hi = value + eps
    # If the range of valid choices spans an integer, return the integer.
    if int(lo) != int(hi):
        return str(float(round(value)))

    fmt = "%.8f"
    lo = fmt % lo
    hi = fmt % hi
    assert len(lo) == len(hi) and lo != hi
    for i in range(len(lo)):
        if lo[i] != hi[i]:
            break
    period = lo.find(".")
    assert period < i
    fmt = "%%.%df" % (i - period)
    return fmt % value
