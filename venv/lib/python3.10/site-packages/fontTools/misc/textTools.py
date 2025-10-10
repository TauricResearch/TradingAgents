"""fontTools.misc.textTools.py -- miscellaneous routines."""

from __future__ import annotations

import ast
import string


# alias kept for backward compatibility
safeEval = ast.literal_eval


class Tag(str):
    @staticmethod
    def transcode(blob):
        if isinstance(blob, bytes):
            blob = blob.decode("latin-1")
        return blob

    def __new__(self, content):
        return str.__new__(self, self.transcode(content))

    def __ne__(self, other):
        return not self.__eq__(other)

    def __eq__(self, other):
        return str.__eq__(self, self.transcode(other))

    def __hash__(self):
        return str.__hash__(self)

    def tobytes(self):
        return self.encode("latin-1")


def readHex(content):
    """Convert a list of hex strings to binary data."""
    return deHexStr(strjoin(chunk for chunk in content if isinstance(chunk, str)))


def deHexStr(hexdata):
    """Convert a hex string to binary data."""
    hexdata = strjoin(hexdata.split())
    if len(hexdata) % 2:
        hexdata = hexdata + "0"
    data = []
    for i in range(0, len(hexdata), 2):
        data.append(bytechr(int(hexdata[i : i + 2], 16)))
    return bytesjoin(data)


def hexStr(data):
    """Convert binary data to a hex string."""
    h = string.hexdigits
    r = ""
    for c in data:
        i = byteord(c)
        r = r + h[(i >> 4) & 0xF] + h[i & 0xF]
    return r


def num2binary(l, bits=32):
    items = []
    binary = ""
    for i in range(bits):
        if l & 0x1:
            binary = "1" + binary
        else:
            binary = "0" + binary
        l = l >> 1
        if not ((i + 1) % 8):
            items.append(binary)
            binary = ""
    if binary:
        items.append(binary)
    items.reverse()
    assert l in (0, -1), "number doesn't fit in number of bits"
    return " ".join(items)


def binary2num(bin):
    bin = strjoin(bin.split())
    l = 0
    for digit in bin:
        l = l << 1
        if digit != "0":
            l = l | 0x1
    return l


def caselessSort(alist):
    """Return a sorted copy of a list. If there are only strings
    in the list, it will not consider case.
    """

    try:
        return sorted(alist, key=lambda a: (a.lower(), a))
    except TypeError:
        return sorted(alist)


def pad(data, size):
    r"""Pad byte string 'data' with null bytes until its length is a
    multiple of 'size'.

    >>> len(pad(b'abcd', 4))
    4
    >>> len(pad(b'abcde', 2))
    6
    >>> len(pad(b'abcde', 4))
    8
    >>> pad(b'abcdef', 4) == b'abcdef\x00\x00'
    True
    """
    data = tobytes(data)
    if size > 1:
        remainder = len(data) % size
        if remainder:
            data += b"\0" * (size - remainder)
    return data


def tostr(s: str | bytes, encoding: str = "ascii", errors: str = "strict") -> str:
    if not isinstance(s, str):
        return s.decode(encoding, errors)
    else:
        return s


def tobytes(s: str | bytes, encoding: str = "ascii", errors: str = "strict") -> bytes:
    if isinstance(s, str):
        return s.encode(encoding, errors)
    else:
        return bytes(s)


def bytechr(n):
    return bytes([n])


def byteord(c):
    return c if isinstance(c, int) else ord(c)


def strjoin(iterable, joiner=""):
    return tostr(joiner).join(iterable)


def bytesjoin(iterable, joiner=b""):
    return tobytes(joiner).join(tobytes(item) for item in iterable)


if __name__ == "__main__":
    import doctest, sys

    sys.exit(doctest.testmod().failed)
