"""Python 2/3 compat layer leftovers."""

import decimal as _decimal
import math as _math
import warnings
from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO
from io import StringIO as UnicodeIO
from types import SimpleNamespace

from .textTools import Tag, bytechr, byteord, bytesjoin, strjoin, tobytes, tostr

warnings.warn(
    "The py23 module has been deprecated and will be removed in a future release. "
    "Please update your code.",
    DeprecationWarning,
)

__all__ = [
    "basestring",
    "bytechr",
    "byteord",
    "BytesIO",
    "bytesjoin",
    "open",
    "Py23Error",
    "range",
    "RecursionError",
    "round",
    "SimpleNamespace",
    "StringIO",
    "strjoin",
    "Tag",
    "tobytes",
    "tostr",
    "tounicode",
    "unichr",
    "unicode",
    "UnicodeIO",
    "xrange",
    "zip",
]


class Py23Error(NotImplementedError):
    pass


RecursionError = RecursionError
StringIO = UnicodeIO

basestring = str
isclose = _math.isclose
isfinite = _math.isfinite
open = open
range = range
round = round3 = round
unichr = chr
unicode = str
zip = zip

tounicode = tostr


def xrange(*args, **kwargs):
    raise Py23Error("'xrange' is not defined. Use 'range' instead.")


def round2(number, ndigits=None):
    """
    Implementation of Python 2 built-in round() function.
    Rounds a number to a given precision in decimal digits (default
    0 digits). The result is a floating point number. Values are rounded
    to the closest multiple of 10 to the power minus ndigits; if two
    multiples are equally close, rounding is done away from 0.
    ndigits may be negative.
    See Python 2 documentation:
    https://docs.python.org/2/library/functions.html?highlight=round#round
    """
    if ndigits is None:
        ndigits = 0

    if ndigits < 0:
        exponent = 10 ** (-ndigits)
        quotient, remainder = divmod(number, exponent)
        if remainder >= exponent // 2 and number >= 0:
            quotient += 1
        return float(quotient * exponent)
    else:
        exponent = _decimal.Decimal("10") ** (-ndigits)

        d = _decimal.Decimal.from_float(number).quantize(
            exponent, rounding=_decimal.ROUND_HALF_UP
        )

        return float(d)
