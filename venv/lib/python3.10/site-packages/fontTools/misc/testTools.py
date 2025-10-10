"""Helpers for writing unit tests."""

from collections.abc import Iterable
from io import BytesIO
import os
import re
import shutil
import sys
import tempfile
from unittest import TestCase as _TestCase
from fontTools.config import Config
from fontTools.misc.textTools import tobytes
from fontTools.misc.xmlWriter import XMLWriter


def parseXML(xmlSnippet):
    """Parses a snippet of XML.

    Input can be either a single string (unicode or UTF-8 bytes), or a
    a sequence of strings.

    The result is in the same format that would be returned by
    XMLReader, but the parser imposes no constraints on the root
    element so it can be called on small snippets of TTX files.
    """
    # To support snippets with multiple elements, we add a fake root.
    reader = TestXMLReader_()
    xml = b"<root>"
    if isinstance(xmlSnippet, bytes):
        xml += xmlSnippet
    elif isinstance(xmlSnippet, str):
        xml += tobytes(xmlSnippet, "utf-8")
    elif isinstance(xmlSnippet, Iterable):
        xml += b"".join(tobytes(s, "utf-8") for s in xmlSnippet)
    else:
        raise TypeError(
            "expected string or sequence of strings; found %r"
            % type(xmlSnippet).__name__
        )
    xml += b"</root>"
    reader.parser.Parse(xml, 1)
    return reader.root[2]


def parseXmlInto(font, parseInto, xmlSnippet):
    parsed_xml = [e for e in parseXML(xmlSnippet.strip()) if not isinstance(e, str)]
    for name, attrs, content in parsed_xml:
        parseInto.fromXML(name, attrs, content, font)
    if hasattr(parseInto, "populateDefaults"):
        parseInto.populateDefaults()
    return parseInto


class FakeFont:
    def __init__(self, glyphs):
        self.glyphOrder_ = glyphs
        self.reverseGlyphOrderDict_ = {g: i for i, g in enumerate(glyphs)}
        self.lazy = False
        self.tables = {}
        self.cfg = Config()

    def __contains__(self, tag):
        return tag in self.tables

    def __getitem__(self, tag):
        return self.tables[tag]

    def __setitem__(self, tag, table):
        self.tables[tag] = table

    def get(self, tag, default=None):
        return self.tables.get(tag, default)

    def getGlyphID(self, name):
        return self.reverseGlyphOrderDict_[name]

    def getGlyphIDMany(self, lst):
        return [self.getGlyphID(gid) for gid in lst]

    def getGlyphName(self, glyphID):
        if glyphID < len(self.glyphOrder_):
            return self.glyphOrder_[glyphID]
        else:
            return "glyph%.5d" % glyphID

    def getGlyphNameMany(self, lst):
        return [self.getGlyphName(gid) for gid in lst]

    def getGlyphOrder(self):
        return self.glyphOrder_

    def getReverseGlyphMap(self):
        return self.reverseGlyphOrderDict_

    def getGlyphNames(self):
        return sorted(self.getGlyphOrder())


class TestXMLReader_(object):
    def __init__(self):
        from xml.parsers.expat import ParserCreate

        self.parser = ParserCreate()
        self.parser.StartElementHandler = self.startElement_
        self.parser.EndElementHandler = self.endElement_
        self.parser.CharacterDataHandler = self.addCharacterData_
        self.root = None
        self.stack = []

    def startElement_(self, name, attrs):
        element = (name, attrs, [])
        if self.stack:
            self.stack[-1][2].append(element)
        else:
            self.root = element
        self.stack.append(element)

    def endElement_(self, name):
        self.stack.pop()

    def addCharacterData_(self, data):
        self.stack[-1][2].append(data)


def makeXMLWriter(newlinestr="\n"):
    # don't write OS-specific new lines
    writer = XMLWriter(BytesIO(), newlinestr=newlinestr)
    # erase XML declaration
    writer.file.seek(0)
    writer.file.truncate()
    return writer


def getXML(func, ttFont=None):
    """Call the passed toXML function and return the written content as a
    list of lines (unicode strings).
    Result is stripped of XML declaration and OS-specific newline characters.
    """
    writer = makeXMLWriter()
    func(writer, ttFont)
    xml = writer.file.getvalue().decode("utf-8")
    # toXML methods must always end with a writer.newline()
    assert xml.endswith("\n")
    return xml.splitlines()


def stripVariableItemsFromTTX(
    string: str,
    ttLibVersion: bool = True,
    checkSumAdjustment: bool = True,
    modified: bool = True,
    created: bool = True,
    sfntVersion: bool = False,  # opt-in only
) -> str:
    """Strip stuff like ttLibVersion, checksums, timestamps, etc. from TTX dumps."""
    # ttlib changes with the fontTools version
    if ttLibVersion:
        string = re.sub(' ttLibVersion="[^"]+"', "", string)
    # sometimes (e.g. some subsetter tests) we don't care whether it's OTF or TTF
    if sfntVersion:
        string = re.sub(' sfntVersion="[^"]+"', "", string)
    # head table checksum and creation and mod date changes with each save.
    if checkSumAdjustment:
        string = re.sub('<checkSumAdjustment value="[^"]+"/>', "", string)
    if modified:
        string = re.sub('<modified value="[^"]+"/>', "", string)
    if created:
        string = re.sub('<created value="[^"]+"/>', "", string)
    return string


class MockFont(object):
    """A font-like object that automatically adds any looked up glyphname
    to its glyphOrder."""

    def __init__(self):
        self._glyphOrder = [".notdef"]

        class AllocatingDict(dict):
            def __missing__(reverseDict, key):
                self._glyphOrder.append(key)
                gid = len(reverseDict)
                reverseDict[key] = gid
                return gid

        self._reverseGlyphOrder = AllocatingDict({".notdef": 0})
        self.lazy = False

    def getGlyphID(self, glyph):
        gid = self._reverseGlyphOrder[glyph]
        return gid

    def getReverseGlyphMap(self):
        return self._reverseGlyphOrder

    def getGlyphName(self, gid):
        return self._glyphOrder[gid]

    def getGlyphOrder(self):
        return self._glyphOrder


class TestCase(_TestCase):
    def __init__(self, methodName):
        _TestCase.__init__(self, methodName)
        # Python 3 renamed assertRaisesRegexp to assertRaisesRegex,
        # and fires deprecation warnings if a program uses the old name.
        if not hasattr(self, "assertRaisesRegex"):
            self.assertRaisesRegex = self.assertRaisesRegexp


class DataFilesHandler(TestCase):
    def setUp(self):
        self.tempdir = None
        self.num_tempfiles = 0

    def tearDown(self):
        if self.tempdir:
            shutil.rmtree(self.tempdir)

    def getpath(self, testfile):
        folder = os.path.dirname(sys.modules[self.__module__].__file__)
        return os.path.join(folder, "data", testfile)

    def temp_dir(self):
        if not self.tempdir:
            self.tempdir = tempfile.mkdtemp()

    def temp_font(self, font_path, file_name):
        self.temp_dir()
        temppath = os.path.join(self.tempdir, file_name)
        shutil.copy2(font_path, temppath)
        return temppath
