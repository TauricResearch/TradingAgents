"""sstruct.py -- SuperStruct

Higher level layer on top of the struct module, enabling to
bind names to struct elements. The interface is similar to
struct, except the objects passed and returned are not tuples
(or argument lists), but dictionaries or instances.

Just like struct, we use fmt strings to describe a data
structure, except we use one line per element. Lines are
separated by newlines or semi-colons. Each line contains
either one of the special struct characters ('@', '=', '<',
'>' or '!') or a 'name:formatchar' combo (eg. 'myFloat:f').
Repetitions, like the struct module offers them are not useful
in this context, except for fixed length strings  (eg. 'myInt:5h'
is not allowed but 'myString:5s' is). The 'x' fmt character
(pad byte) is treated as 'special', since it is by definition
anonymous. Extra whitespace is allowed everywhere.

The sstruct module offers one feature that the "normal" struct
module doesn't: support for fixed point numbers. These are spelled
as "n.mF", where n is the number of bits before the point, and m
the number of bits after the point. Fixed point numbers get
converted to floats.

pack(fmt, object):
	'object' is either a dictionary or an instance (or actually
	anything that has a __dict__ attribute). If it is a dictionary,
	its keys are used for names. If it is an instance, it's
	attributes are used to grab struct elements from. Returns
	a string containing the data.

unpack(fmt, data, object=None)
	If 'object' is omitted (or None), a new dictionary will be
	returned. If 'object' is a dictionary, it will be used to add
	struct elements to. If it is an instance (or in fact anything
	that has a __dict__ attribute), an attribute will be added for
	each struct element. In the latter two cases, 'object' itself
	is returned.

unpack2(fmt, data, object=None)
	Convenience function. Same as unpack, except data may be longer
	than needed. The returned value is a tuple: (object, leftoverdata).

calcsize(fmt)
	like struct.calcsize(), but uses our own fmt strings:
	it returns the size of the data in bytes.
"""

from fontTools.misc.fixedTools import fixedToFloat as fi2fl, floatToFixed as fl2fi
from fontTools.misc.textTools import tobytes, tostr
import struct
import re

__version__ = "1.2"
__copyright__ = "Copyright 1998, Just van Rossum <just@letterror.com>"


class Error(Exception):
    pass


def pack(fmt, obj):
    formatstring, names, fixes = getformat(fmt, keep_pad_byte=True)
    elements = []
    if not isinstance(obj, dict):
        obj = obj.__dict__
    for name in names.keys():
        value = obj[name]
        if name in fixes:
            # fixed point conversion
            value = fl2fi(value, fixes[name])
        elif isinstance(value, str):
            value = tobytes(value)
        elements.append(value)
        # Check it fits
        try:
            struct.pack(names[name], value)
        except Exception as e:
            raise ValueError(
                "Value %s does not fit in format %s for %s" % (value, names[name], name)
            ) from e
    data = struct.pack(*(formatstring,) + tuple(elements))
    return data


def unpack(fmt, data, obj=None):
    if obj is None:
        obj = {}
    data = tobytes(data)
    formatstring, names, fixes = getformat(fmt)
    if isinstance(obj, dict):
        d = obj
    else:
        d = obj.__dict__
    elements = struct.unpack(formatstring, data)
    for i, name in enumerate(names.keys()):
        value = elements[i]
        if name in fixes:
            # fixed point conversion
            value = fi2fl(value, fixes[name])
        elif isinstance(value, bytes):
            try:
                value = tostr(value)
            except UnicodeDecodeError:
                pass
        d[name] = value
    return obj


def unpack2(fmt, data, obj=None):
    length = calcsize(fmt)
    return unpack(fmt, data[:length], obj), data[length:]


def calcsize(fmt):
    formatstring, names, fixes = getformat(fmt)
    return struct.calcsize(formatstring)


# matches "name:formatchar" (whitespace is allowed)
_elementRE = re.compile(
    r"\s*"  # whitespace
    r"([A-Za-z_][A-Za-z_0-9]*)"  # name (python identifier)
    r"\s*:\s*"  # whitespace : whitespace
    r"([xcbB?hHiIlLqQfd]|"  # formatchar...
    r"[0-9]+[ps]|"  # ...formatchar...
    r"([0-9]+)\.([0-9]+)(F))"  # ...formatchar
    r"\s*"  # whitespace
    r"(#.*)?$"  # [comment] + end of string
)

# matches the special struct fmt chars and 'x' (pad byte)
_extraRE = re.compile(r"\s*([x@=<>!])\s*(#.*)?$")

# matches an "empty" string, possibly containing whitespace and/or a comment
_emptyRE = re.compile(r"\s*(#.*)?$")

_fixedpointmappings = {8: "b", 16: "h", 32: "l"}

_formatcache = {}


def getformat(fmt, keep_pad_byte=False):
    fmt = tostr(fmt, encoding="ascii")
    try:
        formatstring, names, fixes = _formatcache[fmt]
    except KeyError:
        lines = re.split("[\n;]", fmt)
        formatstring = ""
        names = {}
        fixes = {}
        for line in lines:
            if _emptyRE.match(line):
                continue
            m = _extraRE.match(line)
            if m:
                formatchar = m.group(1)
                if formatchar != "x" and formatstring:
                    raise Error("a special fmt char must be first")
            else:
                m = _elementRE.match(line)
                if not m:
                    raise Error("syntax error in fmt: '%s'" % line)
                name = m.group(1)
                formatchar = m.group(2)
                if keep_pad_byte or formatchar != "x":
                    names[name] = formatchar
                if m.group(3):
                    # fixed point
                    before = int(m.group(3))
                    after = int(m.group(4))
                    bits = before + after
                    if bits not in [8, 16, 32]:
                        raise Error("fixed point must be 8, 16 or 32 bits long")
                    formatchar = _fixedpointmappings[bits]
                    names[name] = formatchar
                    assert m.group(5) == "F"
                    fixes[name] = after
            formatstring += formatchar
        _formatcache[fmt] = formatstring, names, fixes
    return formatstring, names, fixes


def _test():
    fmt = """
		# comments are allowed
		>  # big endian (see documentation for struct)
		# empty lines are allowed:

		ashort: h
		along: l
		abyte: b	# a byte
		achar: c
		astr: 5s
		afloat: f; adouble: d	# multiple "statements" are allowed
		afixed: 16.16F
		abool: ?
		apad: x
	"""

    print("size:", calcsize(fmt))

    class foo(object):
        pass

    i = foo()

    i.ashort = 0x7FFF
    i.along = 0x7FFFFFFF
    i.abyte = 0x7F
    i.achar = "a"
    i.astr = "12345"
    i.afloat = 0.5
    i.adouble = 0.5
    i.afixed = 1.5
    i.abool = True

    data = pack(fmt, i)
    print("data:", repr(data))
    print(unpack(fmt, data))
    i2 = foo()
    unpack(fmt, data, i2)
    print(vars(i2))


if __name__ == "__main__":
    _test()
