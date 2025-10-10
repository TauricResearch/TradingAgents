"""DEPRECATED - This module is kept here only as a backward compatibility shim
for the old `ufoLib.plistlib` module, which was moved to :class:`fontTools.misc.plistlib`.
Please use the latter instead.
"""

from fontTools.misc.plistlib import dump, dumps, load, loads
from fontTools.misc.textTools import tobytes

# The following functions were part of the old py2-like ufoLib.plistlib API.
# They are kept only for backward compatiblity.
from fontTools.ufoLib.utils import deprecated


@deprecated("Use 'fontTools.misc.plistlib.load' instead")
def readPlist(path_or_file):
    did_open = False
    if isinstance(path_or_file, str):
        path_or_file = open(path_or_file, "rb")
        did_open = True
    try:
        return load(path_or_file, use_builtin_types=False)
    finally:
        if did_open:
            path_or_file.close()


@deprecated("Use 'fontTools.misc.plistlib.dump' instead")
def writePlist(value, path_or_file):
    did_open = False
    if isinstance(path_or_file, str):
        path_or_file = open(path_or_file, "wb")
        did_open = True
    try:
        dump(value, path_or_file, use_builtin_types=False)
    finally:
        if did_open:
            path_or_file.close()


@deprecated("Use 'fontTools.misc.plistlib.loads' instead")
def readPlistFromString(data):
    return loads(tobytes(data, encoding="utf-8"), use_builtin_types=False)


@deprecated("Use 'fontTools.misc.plistlib.dumps' instead")
def writePlistToString(value):
    return dumps(value, use_builtin_types=False)
