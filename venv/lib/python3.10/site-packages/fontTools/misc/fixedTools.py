"""
The `OpenType specification <https://docs.microsoft.com/en-us/typography/opentype/spec/otff#data-types>`_
defines two fixed-point data types:

``Fixed``
	A 32-bit signed fixed-point number with a 16 bit twos-complement
	magnitude component and 16 fractional bits.
``F2DOT14``
	A 16-bit signed fixed-point number with a 2 bit twos-complement
	magnitude component and 14 fractional bits.

To support reading and writing data with these data types, this module provides
functions for converting between fixed-point, float and string representations.

.. data:: MAX_F2DOT14

	The maximum value that can still fit in an F2Dot14. (1.99993896484375)
"""

from .roundTools import otRound, nearestMultipleShortestRepr
import logging

log = logging.getLogger(__name__)

__all__ = [
    "MAX_F2DOT14",
    "fixedToFloat",
    "floatToFixed",
    "floatToFixedToFloat",
    "floatToFixedToStr",
    "fixedToStr",
    "strToFixed",
    "strToFixedToFloat",
    "ensureVersionIsLong",
    "versionToFixed",
]


MAX_F2DOT14 = 0x7FFF / (1 << 14)


def fixedToFloat(value, precisionBits):
    """Converts a fixed-point number to a float given the number of
    precision bits.

    Args:
            value (int): Number in fixed-point format.
            precisionBits (int): Number of precision bits.

    Returns:
            Floating point value.

    Examples::

            >>> import math
            >>> f = fixedToFloat(-10139, precisionBits=14)
            >>> math.isclose(f, -0.61883544921875)
            True
    """
    return value / (1 << precisionBits)


def floatToFixed(value, precisionBits):
    """Converts a float to a fixed-point number given the number of
    precision bits.

    Args:
            value (float): Floating point value.
            precisionBits (int): Number of precision bits.

    Returns:
            int: Fixed-point representation.

    Examples::

            >>> floatToFixed(-0.61883544921875, precisionBits=14)
            -10139
            >>> floatToFixed(-0.61884, precisionBits=14)
            -10139
    """
    return otRound(value * (1 << precisionBits))


def floatToFixedToFloat(value, precisionBits):
    """Converts a float to a fixed-point number and back again.

    By converting the float to fixed, rounding it, and converting it back
    to float again, this returns a floating point values which is exactly
    representable in fixed-point format.

    Note: this **is** equivalent to ``fixedToFloat(floatToFixed(value))``.

    Args:
            value (float): The input floating point value.
            precisionBits (int): Number of precision bits.

    Returns:
            float: The transformed and rounded value.

    Examples::
            >>> import math
            >>> f1 = -0.61884
            >>> f2 = floatToFixedToFloat(-0.61884, precisionBits=14)
            >>> f1 != f2
            True
            >>> math.isclose(f2, -0.61883544921875)
            True
    """
    scale = 1 << precisionBits
    return otRound(value * scale) / scale


def fixedToStr(value, precisionBits):
    """Converts a fixed-point number to a string representing a decimal float.

    This chooses the float that has the shortest decimal representation (the least
    number of fractional decimal digits).

    For example, to convert a fixed-point number in a 2.14 format, use
    ``precisionBits=14``::

            >>> fixedToStr(-10139, precisionBits=14)
            '-0.61884'

    This is pretty slow compared to the simple division used in ``fixedToFloat``.
    Use sporadically when you need to serialize or print the fixed-point number in
    a human-readable form.
    It uses nearestMultipleShortestRepr under the hood.

    Args:
            value (int): The fixed-point value to convert.
            precisionBits (int): Number of precision bits, *up to a maximum of 16*.

    Returns:
            str: A string representation of the value.
    """
    scale = 1 << precisionBits
    return nearestMultipleShortestRepr(value / scale, factor=1.0 / scale)


def strToFixed(string, precisionBits):
    """Converts a string representing a decimal float to a fixed-point number.

    Args:
            string (str): A string representing a decimal float.
            precisionBits (int): Number of precision bits, *up to a maximum of 16*.

    Returns:
            int: Fixed-point representation.

    Examples::

            >>> ## to convert a float string to a 2.14 fixed-point number:
            >>> strToFixed('-0.61884', precisionBits=14)
            -10139
    """
    value = float(string)
    return otRound(value * (1 << precisionBits))


def strToFixedToFloat(string, precisionBits):
    """Convert a string to a decimal float with fixed-point rounding.

    This first converts string to a float, then turns it into a fixed-point
    number with ``precisionBits`` fractional binary digits, then back to a
    float again.

    This is simply a shorthand for fixedToFloat(floatToFixed(float(s))).

    Args:
            string (str): A string representing a decimal float.
            precisionBits (int): Number of precision bits.

    Returns:
            float: The transformed and rounded value.

    Examples::

            >>> import math
            >>> s = '-0.61884'
            >>> bits = 14
            >>> f = strToFixedToFloat(s, precisionBits=bits)
            >>> math.isclose(f, -0.61883544921875)
            True
            >>> f == fixedToFloat(floatToFixed(float(s), precisionBits=bits), precisionBits=bits)
            True
    """
    value = float(string)
    scale = 1 << precisionBits
    return otRound(value * scale) / scale


def floatToFixedToStr(value, precisionBits):
    """Convert float to string with fixed-point rounding.

    This uses the shortest decimal representation (ie. the least
    number of fractional decimal digits) to represent the equivalent
    fixed-point number with ``precisionBits`` fractional binary digits.
    It uses nearestMultipleShortestRepr under the hood.

    >>> floatToFixedToStr(-0.61883544921875, precisionBits=14)
    '-0.61884'

    Args:
            value (float): The float value to convert.
            precisionBits (int): Number of precision bits, *up to a maximum of 16*.

    Returns:
            str: A string representation of the value.

    """
    scale = 1 << precisionBits
    return nearestMultipleShortestRepr(value, factor=1.0 / scale)


def ensureVersionIsLong(value):
    """Ensure a table version is an unsigned long.

    OpenType table version numbers are expressed as a single unsigned long
    comprising of an unsigned short major version and unsigned short minor
    version. This function detects if the value to be used as a version number
    looks too small (i.e. is less than ``0x10000``), and converts it to
    fixed-point using :func:`floatToFixed` if so.

    Args:
            value (Number): a candidate table version number.

    Returns:
            int: A table version number, possibly corrected to fixed-point.
    """
    if value < 0x10000:
        newValue = floatToFixed(value, 16)
        log.warning(
            "Table version value is a float: %.4f; " "fix to use hex instead: 0x%08x",
            value,
            newValue,
        )
        value = newValue
    return value


def versionToFixed(value):
    """Ensure a table version number is fixed-point.

    Args:
            value (str): a candidate table version number.

    Returns:
            int: A table version number, possibly corrected to fixed-point.
    """
    value = int(value, 0) if value.startswith("0") else float(value)
    value = ensureVersionIsLong(value)
    return value
