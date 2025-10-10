"""Shim module exporting the same ElementTree API for lxml and
xml.etree backends.

When lxml is installed, it is automatically preferred over the built-in
xml.etree module.
On Python 2.7, the cElementTree module is preferred over the pure-python
ElementTree module.

Besides exporting a unified interface, this also defines extra functions
or subclasses built-in ElementTree classes to add features that are
only availble in lxml, like OrderedDict for attributes, pretty_print and
iterwalk.
"""

from fontTools.misc.textTools import tostr


XML_DECLARATION = """<?xml version='1.0' encoding='%s'?>"""

__all__ = [
    # public symbols
    "Comment",
    "dump",
    "Element",
    "ElementTree",
    "fromstring",
    "fromstringlist",
    "iselement",
    "iterparse",
    "parse",
    "ParseError",
    "PI",
    "ProcessingInstruction",
    "QName",
    "SubElement",
    "tostring",
    "tostringlist",
    "TreeBuilder",
    "XML",
    "XMLParser",
    "register_namespace",
]

try:
    from lxml.etree import *

    _have_lxml = True
except ImportError:
    try:
        from xml.etree.cElementTree import *

        # the cElementTree version of XML function doesn't support
        # the optional 'parser' keyword argument
        from xml.etree.ElementTree import XML
    except ImportError:  # pragma: no cover
        from xml.etree.ElementTree import *
    _have_lxml = False

    _Attrib = dict

    if isinstance(Element, type):
        _Element = Element
    else:
        # in py27, cElementTree.Element cannot be subclassed, so
        # we need to import the pure-python class
        from xml.etree.ElementTree import Element as _Element

    class Element(_Element):
        """Element subclass that keeps the order of attributes."""

        def __init__(self, tag, attrib=_Attrib(), **extra):
            super(Element, self).__init__(tag)
            self.attrib = _Attrib()
            if attrib:
                self.attrib.update(attrib)
            if extra:
                self.attrib.update(extra)

    def SubElement(parent, tag, attrib=_Attrib(), **extra):
        """Must override SubElement as well otherwise _elementtree.SubElement
        fails if 'parent' is a subclass of Element object.
        """
        element = parent.__class__(tag, attrib, **extra)
        parent.append(element)
        return element

    def _iterwalk(element, events, tag):
        include = tag is None or element.tag == tag
        if include and "start" in events:
            yield ("start", element)
        for e in element:
            for item in _iterwalk(e, events, tag):
                yield item
        if include:
            yield ("end", element)

    def iterwalk(element_or_tree, events=("end",), tag=None):
        """A tree walker that generates events from an existing tree as
        if it was parsing XML data with iterparse().
        Drop-in replacement for lxml.etree.iterwalk.
        """
        if iselement(element_or_tree):
            element = element_or_tree
        else:
            element = element_or_tree.getroot()
        if tag == "*":
            tag = None
        for item in _iterwalk(element, events, tag):
            yield item

    _ElementTree = ElementTree

    class ElementTree(_ElementTree):
        """ElementTree subclass that adds 'pretty_print' and 'doctype'
        arguments to the 'write' method.
        Currently these are only supported for the default XML serialization
        'method', and not also for "html" or "text", for these are delegated
        to the base class.
        """

        def write(
            self,
            file_or_filename,
            encoding=None,
            xml_declaration=False,
            method=None,
            doctype=None,
            pretty_print=False,
        ):
            if method and method != "xml":
                # delegate to super-class
                super(ElementTree, self).write(
                    file_or_filename,
                    encoding=encoding,
                    xml_declaration=xml_declaration,
                    method=method,
                )
                return

            if encoding is not None and encoding.lower() == "unicode":
                if xml_declaration:
                    raise ValueError(
                        "Serialisation to unicode must not request an XML declaration"
                    )
                write_declaration = False
                encoding = "unicode"
            elif xml_declaration is None:
                # by default, write an XML declaration only for non-standard encodings
                write_declaration = encoding is not None and encoding.upper() not in (
                    "ASCII",
                    "UTF-8",
                    "UTF8",
                    "US-ASCII",
                )
            else:
                write_declaration = xml_declaration

            if encoding is None:
                encoding = "ASCII"

            if pretty_print:
                # NOTE this will modify the tree in-place
                _indent(self._root)

            with _get_writer(file_or_filename, encoding) as write:
                if write_declaration:
                    write(XML_DECLARATION % encoding.upper())
                    if pretty_print:
                        write("\n")
                if doctype:
                    write(_tounicode(doctype))
                    if pretty_print:
                        write("\n")

                qnames, namespaces = _namespaces(self._root)
                _serialize_xml(write, self._root, qnames, namespaces)

    import io

    def tostring(
        element,
        encoding=None,
        xml_declaration=None,
        method=None,
        doctype=None,
        pretty_print=False,
    ):
        """Custom 'tostring' function that uses our ElementTree subclass, with
        pretty_print support.
        """
        stream = io.StringIO() if encoding == "unicode" else io.BytesIO()
        ElementTree(element).write(
            stream,
            encoding=encoding,
            xml_declaration=xml_declaration,
            method=method,
            doctype=doctype,
            pretty_print=pretty_print,
        )
        return stream.getvalue()

    # serialization support

    import re

    # Valid XML strings can include any Unicode character, excluding control
    # characters, the surrogate blocks, FFFE, and FFFF:
    #   Char ::= #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
    # Here we reversed the pattern to match only the invalid characters.
    _invalid_xml_string = re.compile(
        "[\u0000-\u0008\u000B-\u000C\u000E-\u001F\uD800-\uDFFF\uFFFE-\uFFFF]"
    )

    def _tounicode(s):
        """Test if a string is valid user input and decode it to unicode string
        using ASCII encoding if it's a bytes string.
        Reject all bytes/unicode input that contains non-XML characters.
        Reject all bytes input that contains non-ASCII characters.
        """
        try:
            s = tostr(s, encoding="ascii", errors="strict")
        except UnicodeDecodeError:
            raise ValueError(
                "Bytes strings can only contain ASCII characters. "
                "Use unicode strings for non-ASCII characters."
            )
        except AttributeError:
            _raise_serialization_error(s)
        if s and _invalid_xml_string.search(s):
            raise ValueError(
                "All strings must be XML compatible: Unicode or ASCII, "
                "no NULL bytes or control characters"
            )
        return s

    import contextlib

    @contextlib.contextmanager
    def _get_writer(file_or_filename, encoding):
        # returns text write method and release all resources after using
        try:
            write = file_or_filename.write
        except AttributeError:
            # file_or_filename is a file name
            f = open(
                file_or_filename,
                "w",
                encoding="utf-8" if encoding == "unicode" else encoding,
                errors="xmlcharrefreplace",
            )
            with f:
                yield f.write
        else:
            # file_or_filename is a file-like object
            # encoding determines if it is a text or binary writer
            if encoding == "unicode":
                # use a text writer as is
                yield write
            else:
                # wrap a binary writer with TextIOWrapper
                detach_buffer = False
                if isinstance(file_or_filename, io.BufferedIOBase):
                    buf = file_or_filename
                elif isinstance(file_or_filename, io.RawIOBase):
                    buf = io.BufferedWriter(file_or_filename)
                    detach_buffer = True
                else:
                    # This is to handle passed objects that aren't in the
                    # IOBase hierarchy, but just have a write method
                    buf = io.BufferedIOBase()
                    buf.writable = lambda: True
                    buf.write = write
                    try:
                        # TextIOWrapper uses this methods to determine
                        # if BOM (for UTF-16, etc) should be added
                        buf.seekable = file_or_filename.seekable
                        buf.tell = file_or_filename.tell
                    except AttributeError:
                        pass
                wrapper = io.TextIOWrapper(
                    buf,
                    encoding=encoding,
                    errors="xmlcharrefreplace",
                    newline="\n",
                )
                try:
                    yield wrapper.write
                finally:
                    # Keep the original file open when the TextIOWrapper and
                    # the BufferedWriter are destroyed
                    wrapper.detach()
                    if detach_buffer:
                        buf.detach()

    from xml.etree.ElementTree import _namespace_map

    def _namespaces(elem):
        # identify namespaces used in this tree

        # maps qnames to *encoded* prefix:local names
        qnames = {None: None}

        # maps uri:s to prefixes
        namespaces = {}

        def add_qname(qname):
            # calculate serialized qname representation
            try:
                qname = _tounicode(qname)
                if qname[:1] == "{":
                    uri, tag = qname[1:].rsplit("}", 1)
                    prefix = namespaces.get(uri)
                    if prefix is None:
                        prefix = _namespace_map.get(uri)
                        if prefix is None:
                            prefix = "ns%d" % len(namespaces)
                        else:
                            prefix = _tounicode(prefix)
                        if prefix != "xml":
                            namespaces[uri] = prefix
                    if prefix:
                        qnames[qname] = "%s:%s" % (prefix, tag)
                    else:
                        qnames[qname] = tag  # default element
                else:
                    qnames[qname] = qname
            except TypeError:
                _raise_serialization_error(qname)

        # populate qname and namespaces table
        for elem in elem.iter():
            tag = elem.tag
            if isinstance(tag, QName):
                if tag.text not in qnames:
                    add_qname(tag.text)
            elif isinstance(tag, str):
                if tag not in qnames:
                    add_qname(tag)
            elif tag is not None and tag is not Comment and tag is not PI:
                _raise_serialization_error(tag)
            for key, value in elem.items():
                if isinstance(key, QName):
                    key = key.text
                if key not in qnames:
                    add_qname(key)
                if isinstance(value, QName) and value.text not in qnames:
                    add_qname(value.text)
            text = elem.text
            if isinstance(text, QName) and text.text not in qnames:
                add_qname(text.text)
        return qnames, namespaces

    def _serialize_xml(write, elem, qnames, namespaces, **kwargs):
        tag = elem.tag
        text = elem.text
        if tag is Comment:
            write("<!--%s-->" % _tounicode(text))
        elif tag is ProcessingInstruction:
            write("<?%s?>" % _tounicode(text))
        else:
            tag = qnames[_tounicode(tag) if tag is not None else None]
            if tag is None:
                if text:
                    write(_escape_cdata(text))
                for e in elem:
                    _serialize_xml(write, e, qnames, None)
            else:
                write("<" + tag)
                if namespaces:
                    for uri, prefix in sorted(
                        namespaces.items(), key=lambda x: x[1]
                    ):  # sort on prefix
                        if prefix:
                            prefix = ":" + prefix
                        write(' xmlns%s="%s"' % (prefix, _escape_attrib(uri)))
                attrs = elem.attrib
                if attrs:
                    # try to keep existing attrib order
                    if len(attrs) <= 1 or type(attrs) is _Attrib:
                        items = attrs.items()
                    else:
                        # if plain dict, use lexical order
                        items = sorted(attrs.items())
                    for k, v in items:
                        if isinstance(k, QName):
                            k = _tounicode(k.text)
                        else:
                            k = _tounicode(k)
                        if isinstance(v, QName):
                            v = qnames[_tounicode(v.text)]
                        else:
                            v = _escape_attrib(v)
                        write(' %s="%s"' % (qnames[k], v))
                if text is not None or len(elem):
                    write(">")
                    if text:
                        write(_escape_cdata(text))
                    for e in elem:
                        _serialize_xml(write, e, qnames, None)
                    write("</" + tag + ">")
                else:
                    write("/>")
        if elem.tail:
            write(_escape_cdata(elem.tail))

    def _raise_serialization_error(text):
        raise TypeError("cannot serialize %r (type %s)" % (text, type(text).__name__))

    def _escape_cdata(text):
        # escape character data
        try:
            text = _tounicode(text)
            # it's worth avoiding do-nothing calls for short strings
            if "&" in text:
                text = text.replace("&", "&amp;")
            if "<" in text:
                text = text.replace("<", "&lt;")
            if ">" in text:
                text = text.replace(">", "&gt;")
            return text
        except (TypeError, AttributeError):
            _raise_serialization_error(text)

    def _escape_attrib(text):
        # escape attribute value
        try:
            text = _tounicode(text)
            if "&" in text:
                text = text.replace("&", "&amp;")
            if "<" in text:
                text = text.replace("<", "&lt;")
            if ">" in text:
                text = text.replace(">", "&gt;")
            if '"' in text:
                text = text.replace('"', "&quot;")
            if "\n" in text:
                text = text.replace("\n", "&#10;")
            return text
        except (TypeError, AttributeError):
            _raise_serialization_error(text)

    def _indent(elem, level=0):
        # From http://effbot.org/zone/element-lib.htm#prettyprint
        i = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for elem in elem:
                _indent(elem, level + 1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i
