import collections.abc
import re
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Type,
    Union,
    IO,
)
import warnings
from io import BytesIO
from datetime import datetime
from base64 import b64encode, b64decode
from numbers import Integral
from types import SimpleNamespace
from functools import singledispatch

from fontTools.misc import etree

from fontTools.misc.textTools import tostr


# By default, we
#  - deserialize <data> elements as bytes and
#  - serialize bytes as <data> elements.
# Before, on Python 2, we
#  - deserialized <data> elements as plistlib.Data objects, in order to
#    distinguish them from the built-in str type (which is bytes on python2)
#  - serialized bytes as <string> elements (they must have only contained
#    ASCII characters in this case)
# You can pass use_builtin_types=[True|False] to the load/dump etc. functions
# to enforce a specific treatment.
# NOTE that unicode type always maps to <string> element, and plistlib.Data
# always maps to <data> element, regardless of use_builtin_types.
USE_BUILTIN_TYPES = True

XML_DECLARATION = b"""<?xml version='1.0' encoding='UTF-8'?>"""

PLIST_DOCTYPE = (
    b'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
    b'"http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
)


# Date should conform to a subset of ISO 8601:
# YYYY '-' MM '-' DD 'T' HH ':' MM ':' SS 'Z'
_date_parser = re.compile(
    r"(?P<year>\d\d\d\d)"
    r"(?:-(?P<month>\d\d)"
    r"(?:-(?P<day>\d\d)"
    r"(?:T(?P<hour>\d\d)"
    r"(?::(?P<minute>\d\d)"
    r"(?::(?P<second>\d\d))"
    r"?)?)?)?)?Z",
    re.ASCII,
)


def _date_from_string(s: str) -> datetime:
    order = ("year", "month", "day", "hour", "minute", "second")
    m = _date_parser.match(s)
    if m is None:
        raise ValueError(f"Expected ISO 8601 date string, but got '{s:r}'.")
    gd = m.groupdict()
    lst = []
    for key in order:
        val = gd[key]
        if val is None:
            break
        lst.append(int(val))
    # NOTE: mypy doesn't know that lst is 6 elements long.
    return datetime(*lst)  # type:ignore


def _date_to_string(d: datetime) -> str:
    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (
        d.year,
        d.month,
        d.day,
        d.hour,
        d.minute,
        d.second,
    )


class Data:
    """Represents binary data when ``use_builtin_types=False.``

    This class wraps binary data loaded from a plist file when the
    ``use_builtin_types`` argument to the loading function (:py:func:`fromtree`,
    :py:func:`load`, :py:func:`loads`) is false.

    The actual binary data is retrieved using the ``data`` attribute.
    """

    def __init__(self, data: bytes) -> None:
        if not isinstance(data, bytes):
            raise TypeError("Expected bytes, found %s" % type(data).__name__)
        self.data = data

    @classmethod
    def fromBase64(cls, data: Union[bytes, str]) -> "Data":
        return cls(b64decode(data))

    def asBase64(self, maxlinelength: int = 76, indent_level: int = 1) -> bytes:
        return _encode_base64(
            self.data, maxlinelength=maxlinelength, indent_level=indent_level
        )

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, self.__class__):
            return self.data == other.data
        elif isinstance(other, bytes):
            return self.data == other
        else:
            return NotImplemented

    def __repr__(self) -> str:
        return "%s(%s)" % (self.__class__.__name__, repr(self.data))


def _encode_base64(
    data: bytes, maxlinelength: Optional[int] = 76, indent_level: int = 1
) -> bytes:
    data = b64encode(data)
    if data and maxlinelength:
        # split into multiple lines right-justified to 'maxlinelength' chars
        indent = b"\n" + b"  " * indent_level
        max_length = max(16, maxlinelength - len(indent))
        chunks = []
        for i in range(0, len(data), max_length):
            chunks.append(indent)
            chunks.append(data[i : i + max_length])
        chunks.append(indent)
        data = b"".join(chunks)
    return data


# Mypy does not support recursive type aliases as of 0.782, Pylance does.
# https://github.com/python/mypy/issues/731
# https://devblogs.microsoft.com/python/pylance-introduces-five-new-features-that-enable-type-magic-for-python-developers/#1-support-for-recursive-type-aliases
PlistEncodable = Union[
    bool,
    bytes,
    Data,
    datetime,
    float,
    Integral,
    Mapping[str, Any],
    Sequence[Any],
    str,
]


class PlistTarget:
    """Event handler using the ElementTree Target API that can be
    passed to a XMLParser to produce property list objects from XML.
    It is based on the CPython plistlib module's _PlistParser class,
    but does not use the expat parser.

    >>> from fontTools.misc import etree
    >>> parser = etree.XMLParser(target=PlistTarget())
    >>> result = etree.XML(
    ...     "<dict>"
    ...     "    <key>something</key>"
    ...     "    <string>blah</string>"
    ...     "</dict>",
    ...     parser=parser)
    >>> result == {"something": "blah"}
    True

    Links:
    https://github.com/python/cpython/blob/main/Lib/plistlib.py
    http://lxml.de/parsing.html#the-target-parser-interface
    """

    def __init__(
        self,
        use_builtin_types: Optional[bool] = None,
        dict_type: Type[MutableMapping[str, Any]] = dict,
    ) -> None:
        self.stack: List[PlistEncodable] = []
        self.current_key: Optional[str] = None
        self.root: Optional[PlistEncodable] = None
        if use_builtin_types is None:
            self._use_builtin_types = USE_BUILTIN_TYPES
        else:
            if use_builtin_types is False:
                warnings.warn(
                    "Setting use_builtin_types to False is deprecated and will be "
                    "removed soon.",
                    DeprecationWarning,
                )
            self._use_builtin_types = use_builtin_types
        self._dict_type = dict_type

    def start(self, tag: str, attrib: Mapping[str, str]) -> None:
        self._data: List[str] = []
        handler = _TARGET_START_HANDLERS.get(tag)
        if handler is not None:
            handler(self)

    def end(self, tag: str) -> None:
        handler = _TARGET_END_HANDLERS.get(tag)
        if handler is not None:
            handler(self)

    def data(self, data: str) -> None:
        self._data.append(data)

    def close(self) -> PlistEncodable:
        if self.root is None:
            raise ValueError("No root set.")
        return self.root

    # helpers

    def add_object(self, value: PlistEncodable) -> None:
        if self.current_key is not None:
            stack_top = self.stack[-1]
            if not isinstance(stack_top, collections.abc.MutableMapping):
                raise ValueError("unexpected element: %r" % stack_top)
            stack_top[self.current_key] = value
            self.current_key = None
        elif not self.stack:
            # this is the root object
            self.root = value
        else:
            stack_top = self.stack[-1]
            if not isinstance(stack_top, list):
                raise ValueError("unexpected element: %r" % stack_top)
            stack_top.append(value)

    def get_data(self) -> str:
        data = "".join(self._data)
        self._data = []
        return data


# event handlers


def start_dict(self: PlistTarget) -> None:
    d = self._dict_type()
    self.add_object(d)
    self.stack.append(d)


def end_dict(self: PlistTarget) -> None:
    if self.current_key:
        raise ValueError("missing value for key '%s'" % self.current_key)
    self.stack.pop()


def end_key(self: PlistTarget) -> None:
    if self.current_key or not isinstance(self.stack[-1], collections.abc.Mapping):
        raise ValueError("unexpected key")
    self.current_key = self.get_data()


def start_array(self: PlistTarget) -> None:
    a: List[PlistEncodable] = []
    self.add_object(a)
    self.stack.append(a)


def end_array(self: PlistTarget) -> None:
    self.stack.pop()


def end_true(self: PlistTarget) -> None:
    self.add_object(True)


def end_false(self: PlistTarget) -> None:
    self.add_object(False)


def end_integer(self: PlistTarget) -> None:
    self.add_object(int(self.get_data()))


def end_real(self: PlistTarget) -> None:
    self.add_object(float(self.get_data()))


def end_string(self: PlistTarget) -> None:
    self.add_object(self.get_data())


def end_data(self: PlistTarget) -> None:
    if self._use_builtin_types:
        self.add_object(b64decode(self.get_data()))
    else:
        self.add_object(Data.fromBase64(self.get_data()))


def end_date(self: PlistTarget) -> None:
    self.add_object(_date_from_string(self.get_data()))


_TARGET_START_HANDLERS: Dict[str, Callable[[PlistTarget], None]] = {
    "dict": start_dict,
    "array": start_array,
}

_TARGET_END_HANDLERS: Dict[str, Callable[[PlistTarget], None]] = {
    "dict": end_dict,
    "array": end_array,
    "key": end_key,
    "true": end_true,
    "false": end_false,
    "integer": end_integer,
    "real": end_real,
    "string": end_string,
    "data": end_data,
    "date": end_date,
}


# functions to build element tree from plist data


def _string_element(value: str, ctx: SimpleNamespace) -> etree.Element:
    el = etree.Element("string")
    el.text = value
    return el


def _bool_element(value: bool, ctx: SimpleNamespace) -> etree.Element:
    if value:
        return etree.Element("true")
    return etree.Element("false")


def _integer_element(value: int, ctx: SimpleNamespace) -> etree.Element:
    if -1 << 63 <= value < 1 << 64:
        el = etree.Element("integer")
        el.text = "%d" % value
        return el
    raise OverflowError(value)


def _real_element(value: float, ctx: SimpleNamespace) -> etree.Element:
    el = etree.Element("real")
    el.text = repr(value)
    return el


def _dict_element(
    d: Mapping[str, PlistEncodable], ctx: SimpleNamespace
) -> etree.Element:
    el = etree.Element("dict")
    items = d.items()
    if ctx.sort_keys:
        items = sorted(items)  # type: ignore
    ctx.indent_level += 1
    for key, value in items:
        if not isinstance(key, str):
            if ctx.skipkeys:
                continue
            raise TypeError("keys must be strings")
        k = etree.SubElement(el, "key")
        k.text = tostr(key, "utf-8")
        el.append(_make_element(value, ctx))
    ctx.indent_level -= 1
    return el


def _array_element(
    array: Sequence[PlistEncodable], ctx: SimpleNamespace
) -> etree.Element:
    el = etree.Element("array")
    if len(array) == 0:
        return el
    ctx.indent_level += 1
    for value in array:
        el.append(_make_element(value, ctx))
    ctx.indent_level -= 1
    return el


def _date_element(date: datetime, ctx: SimpleNamespace) -> etree.Element:
    el = etree.Element("date")
    el.text = _date_to_string(date)
    return el


def _data_element(data: bytes, ctx: SimpleNamespace) -> etree.Element:
    el = etree.Element("data")
    # NOTE: mypy is confused about whether el.text should be str or bytes.
    el.text = _encode_base64(  # type: ignore
        data,
        maxlinelength=(76 if ctx.pretty_print else None),
        indent_level=ctx.indent_level,
    )
    return el


def _string_or_data_element(raw_bytes: bytes, ctx: SimpleNamespace) -> etree.Element:
    if ctx.use_builtin_types:
        return _data_element(raw_bytes, ctx)
    else:
        try:
            string = raw_bytes.decode(encoding="ascii", errors="strict")
        except UnicodeDecodeError:
            raise ValueError(
                "invalid non-ASCII bytes; use unicode string instead: %r" % raw_bytes
            )
        return _string_element(string, ctx)


# The following is probably not entirely correct. The signature should take `Any`
# and return `NoReturn`. At the time of this writing, neither mypy nor Pyright
# can deal with singledispatch properly and will apply the signature of the base
# function to all others. Being slightly dishonest makes it type-check and return
# usable typing information for the optimistic case.
@singledispatch
def _make_element(value: PlistEncodable, ctx: SimpleNamespace) -> etree.Element:
    raise TypeError("unsupported type: %s" % type(value))


_make_element.register(str)(_string_element)
_make_element.register(bool)(_bool_element)
_make_element.register(Integral)(_integer_element)
_make_element.register(float)(_real_element)
_make_element.register(collections.abc.Mapping)(_dict_element)
_make_element.register(list)(_array_element)
_make_element.register(tuple)(_array_element)
_make_element.register(datetime)(_date_element)
_make_element.register(bytes)(_string_or_data_element)
_make_element.register(bytearray)(_data_element)
_make_element.register(Data)(lambda v, ctx: _data_element(v.data, ctx))


# Public functions to create element tree from plist-compatible python
# data structures and viceversa, for use when (de)serializing GLIF xml.


def totree(
    value: PlistEncodable,
    sort_keys: bool = True,
    skipkeys: bool = False,
    use_builtin_types: Optional[bool] = None,
    pretty_print: bool = True,
    indent_level: int = 1,
) -> etree.Element:
    """Convert a value derived from a plist into an XML tree.

    Args:
        value: Any kind of value to be serialized to XML.
        sort_keys: Whether keys of dictionaries should be sorted.
        skipkeys (bool): Whether to silently skip non-string dictionary
            keys.
        use_builtin_types (bool): If true, byte strings will be
            encoded in Base-64 and wrapped in a ``data`` tag; if
            false, they will be either stored as ASCII strings or an
            exception raised if they cannot be decoded as such. Defaults
            to ``True`` if not present. Deprecated.
        pretty_print (bool): Whether to indent the output.
        indent_level (int): Level of indentation when serializing.

    Returns: an ``etree`` ``Element`` object.

    Raises:
        ``TypeError``
            if non-string dictionary keys are serialized
            and ``skipkeys`` is false.
        ``ValueError``
            if non-ASCII binary data is present
            and `use_builtin_types` is false.
    """
    if use_builtin_types is None:
        use_builtin_types = USE_BUILTIN_TYPES
    else:
        use_builtin_types = use_builtin_types
    context = SimpleNamespace(
        sort_keys=sort_keys,
        skipkeys=skipkeys,
        use_builtin_types=use_builtin_types,
        pretty_print=pretty_print,
        indent_level=indent_level,
    )
    return _make_element(value, context)


def fromtree(
    tree: etree.Element,
    use_builtin_types: Optional[bool] = None,
    dict_type: Type[MutableMapping[str, Any]] = dict,
) -> Any:
    """Convert an XML tree to a plist structure.

    Args:
        tree: An ``etree`` ``Element``.
        use_builtin_types: If True, binary data is deserialized to
            bytes strings. If False, it is wrapped in :py:class:`Data`
            objects. Defaults to True if not provided. Deprecated.
        dict_type: What type to use for dictionaries.

    Returns: An object (usually a dictionary).
    """
    target = PlistTarget(use_builtin_types=use_builtin_types, dict_type=dict_type)
    for action, element in etree.iterwalk(tree, events=("start", "end")):
        if action == "start":
            target.start(element.tag, element.attrib)
        elif action == "end":
            # if there are no children, parse the leaf's data
            if not len(element):
                # always pass str, not None
                target.data(element.text or "")
            target.end(element.tag)
    return target.close()


# python3 plistlib API


def load(
    fp: IO[bytes],
    use_builtin_types: Optional[bool] = None,
    dict_type: Type[MutableMapping[str, Any]] = dict,
) -> Any:
    """Load a plist file into an object.

    Args:
        fp: An opened file.
        use_builtin_types: If True, binary data is deserialized to
            bytes strings. If False, it is wrapped in :py:class:`Data`
            objects. Defaults to True if not provided. Deprecated.
        dict_type: What type to use for dictionaries.

    Returns:
        An object (usually a dictionary) representing the top level of
        the plist file.
    """

    if not hasattr(fp, "read"):
        raise AttributeError("'%s' object has no attribute 'read'" % type(fp).__name__)
    target = PlistTarget(use_builtin_types=use_builtin_types, dict_type=dict_type)
    parser = etree.XMLParser(target=target)
    result = etree.parse(fp, parser=parser)
    # lxml returns the target object directly, while ElementTree wraps
    # it as the root of an ElementTree object
    try:
        return result.getroot()
    except AttributeError:
        return result


def loads(
    value: bytes,
    use_builtin_types: Optional[bool] = None,
    dict_type: Type[MutableMapping[str, Any]] = dict,
) -> Any:
    """Load a plist file from a string into an object.

    Args:
        value: A bytes string containing a plist.
        use_builtin_types: If True, binary data is deserialized to
            bytes strings. If False, it is wrapped in :py:class:`Data`
            objects. Defaults to True if not provided. Deprecated.
        dict_type: What type to use for dictionaries.

    Returns:
        An object (usually a dictionary) representing the top level of
        the plist file.
    """

    fp = BytesIO(value)
    return load(fp, use_builtin_types=use_builtin_types, dict_type=dict_type)


def dump(
    value: PlistEncodable,
    fp: IO[bytes],
    sort_keys: bool = True,
    skipkeys: bool = False,
    use_builtin_types: Optional[bool] = None,
    pretty_print: bool = True,
) -> None:
    """Write a Python object to a plist file.

    Args:
        value: An object to write.
        fp: A file opened for writing.
        sort_keys (bool): Whether keys of dictionaries should be sorted.
        skipkeys (bool): Whether to silently skip non-string dictionary
            keys.
        use_builtin_types (bool): If true, byte strings will be
            encoded in Base-64 and wrapped in a ``data`` tag; if
            false, they will be either stored as ASCII strings or an
            exception raised if they cannot be represented. Defaults
        pretty_print (bool): Whether to indent the output.
        indent_level (int): Level of indentation when serializing.

    Raises:
        ``TypeError``
            if non-string dictionary keys are serialized
            and ``skipkeys`` is false.
        ``ValueError``
            if non-representable binary data is present
            and `use_builtin_types` is false.
    """

    if not hasattr(fp, "write"):
        raise AttributeError("'%s' object has no attribute 'write'" % type(fp).__name__)
    root = etree.Element("plist", version="1.0")
    el = totree(
        value,
        sort_keys=sort_keys,
        skipkeys=skipkeys,
        use_builtin_types=use_builtin_types,
        pretty_print=pretty_print,
    )
    root.append(el)
    tree = etree.ElementTree(root)
    # we write the doctype ourselves instead of using the 'doctype' argument
    # of 'write' method, becuse lxml will force adding a '\n' even when
    # pretty_print is False.
    if pretty_print:
        header = b"\n".join((XML_DECLARATION, PLIST_DOCTYPE, b""))
    else:
        header = XML_DECLARATION + PLIST_DOCTYPE
    fp.write(header)
    tree.write(  # type: ignore
        fp,
        encoding="utf-8",
        pretty_print=pretty_print,
        xml_declaration=False,
    )


def dumps(
    value: PlistEncodable,
    sort_keys: bool = True,
    skipkeys: bool = False,
    use_builtin_types: Optional[bool] = None,
    pretty_print: bool = True,
) -> bytes:
    """Write a Python object to a string in plist format.

    Args:
        value: An object to write.
        sort_keys (bool): Whether keys of dictionaries should be sorted.
        skipkeys (bool): Whether to silently skip non-string dictionary
            keys.
        use_builtin_types (bool): If true, byte strings will be
            encoded in Base-64 and wrapped in a ``data`` tag; if
            false, they will be either stored as strings or an
            exception raised if they cannot be represented. Defaults
        pretty_print (bool): Whether to indent the output.
        indent_level (int): Level of indentation when serializing.

    Returns:
        string: A plist representation of the Python object.

    Raises:
        ``TypeError``
            if non-string dictionary keys are serialized
            and ``skipkeys`` is false.
        ``ValueError``
            if non-representable binary data is present
            and `use_builtin_types` is false.
    """
    fp = BytesIO()
    dump(
        value,
        fp,
        sort_keys=sort_keys,
        skipkeys=skipkeys,
        use_builtin_types=use_builtin_types,
        pretty_print=pretty_print,
    )
    return fp.getvalue()
