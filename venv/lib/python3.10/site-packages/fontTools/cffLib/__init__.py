"""cffLib: read/write Adobe CFF fonts

OpenType fonts with PostScript outlines embed a completely independent
font file in Adobe's *Compact Font Format*. So dealing with OpenType fonts
requires also dealing with CFF. This module allows you to read and write
fonts written in the CFF format.

In 2016, OpenType 1.8 introduced the `CFF2 <https://docs.microsoft.com/en-us/typography/opentype/spec/cff2>`_
format which, along with other changes, extended the CFF format to deal with
the demands of variable fonts. This module parses both original CFF and CFF2.

"""

from fontTools.misc import sstruct
from fontTools.misc import psCharStrings
from fontTools.misc.arrayTools import unionRect, intRect
from fontTools.misc.textTools import (
    bytechr,
    byteord,
    bytesjoin,
    tobytes,
    tostr,
    safeEval,
)
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.otBase import OTTableWriter
from fontTools.ttLib.tables.otBase import OTTableReader
from fontTools.ttLib.tables import otTables as ot
from io import BytesIO
import struct
import logging
import re

# mute cffLib debug messages when running ttx in verbose mode
DEBUG = logging.DEBUG - 1
log = logging.getLogger(__name__)

cffHeaderFormat = """
	major:   B
	minor:   B
	hdrSize: B
"""

maxStackLimit = 513
# maxstack operator has been deprecated. max stack is now always 513.


class CFFFontSet(object):
    """A CFF font "file" can contain more than one font, although this is
    extremely rare (and not allowed within OpenType fonts).

    This class is the entry point for parsing a CFF table. To actually
    manipulate the data inside the CFF font, you will want to access the
    ``CFFFontSet``'s :class:`TopDict` object. To do this, a ``CFFFontSet``
    object can either be treated as a dictionary (with appropriate
    ``keys()`` and ``values()`` methods) mapping font names to :class:`TopDict`
    objects, or as a list.

    .. code:: python

            from fontTools import ttLib
            tt = ttLib.TTFont("Tests/cffLib/data/LinLibertine_RBI.otf")
            tt["CFF "].cff
            # <fontTools.cffLib.CFFFontSet object at 0x101e24c90>
            tt["CFF "].cff[0] # Here's your actual font data
            # <fontTools.cffLib.TopDict object at 0x1020f1fd0>

    """

    def decompile(self, file, otFont, isCFF2=None):
        """Parse a binary CFF file into an internal representation. ``file``
        should be a file handle object. ``otFont`` is the top-level
        :py:class:`fontTools.ttLib.ttFont.TTFont` object containing this CFF file.

        If ``isCFF2`` is passed and set to ``True`` or ``False``, then the
        library makes an assertion that the CFF header is of the appropriate
        version.
        """

        self.otFont = otFont
        sstruct.unpack(cffHeaderFormat, file.read(3), self)
        if isCFF2 is not None:
            # called from ttLib: assert 'major' as read from file matches the
            # expected version
            expected_major = 2 if isCFF2 else 1
            if self.major != expected_major:
                raise ValueError(
                    "Invalid CFF 'major' version: expected %d, found %d"
                    % (expected_major, self.major)
                )
        else:
            # use 'major' version from file to determine if isCFF2
            assert self.major in (1, 2), "Unknown CFF format"
            isCFF2 = self.major == 2
        if not isCFF2:
            self.offSize = struct.unpack("B", file.read(1))[0]
            file.seek(self.hdrSize)
            self.fontNames = list(tostr(s) for s in Index(file, isCFF2=isCFF2))
            self.topDictIndex = TopDictIndex(file, isCFF2=isCFF2)
            self.strings = IndexedStrings(file)
        else:  # isCFF2
            self.topDictSize = struct.unpack(">H", file.read(2))[0]
            file.seek(self.hdrSize)
            self.fontNames = ["CFF2Font"]
            cff2GetGlyphOrder = otFont.getGlyphOrder
            # in CFF2, offsetSize is the size of the TopDict data.
            self.topDictIndex = TopDictIndex(
                file, cff2GetGlyphOrder, self.topDictSize, isCFF2=isCFF2
            )
            self.strings = None
        self.GlobalSubrs = GlobalSubrsIndex(file, isCFF2=isCFF2)
        self.topDictIndex.strings = self.strings
        self.topDictIndex.GlobalSubrs = self.GlobalSubrs

    def __len__(self):
        return len(self.fontNames)

    def keys(self):
        return list(self.fontNames)

    def values(self):
        return self.topDictIndex

    def __getitem__(self, nameOrIndex):
        """Return TopDict instance identified by name (str) or index (int
        or any object that implements `__index__`).
        """
        if hasattr(nameOrIndex, "__index__"):
            index = nameOrIndex.__index__()
        elif isinstance(nameOrIndex, str):
            name = nameOrIndex
            try:
                index = self.fontNames.index(name)
            except ValueError:
                raise KeyError(nameOrIndex)
        else:
            raise TypeError(nameOrIndex)
        return self.topDictIndex[index]

    def compile(self, file, otFont, isCFF2=None):
        """Write the object back into binary representation onto the given file.
        ``file`` should be a file handle object. ``otFont`` is the top-level
        :py:class:`fontTools.ttLib.ttFont.TTFont` object containing this CFF file.

        If ``isCFF2`` is passed and set to ``True`` or ``False``, then the
        library makes an assertion that the CFF header is of the appropriate
        version.
        """
        self.otFont = otFont
        if isCFF2 is not None:
            # called from ttLib: assert 'major' value matches expected version
            expected_major = 2 if isCFF2 else 1
            if self.major != expected_major:
                raise ValueError(
                    "Invalid CFF 'major' version: expected %d, found %d"
                    % (expected_major, self.major)
                )
        else:
            # use current 'major' value to determine output format
            assert self.major in (1, 2), "Unknown CFF format"
            isCFF2 = self.major == 2

        if otFont.recalcBBoxes and not isCFF2:
            for topDict in self.topDictIndex:
                topDict.recalcFontBBox()

        if not isCFF2:
            strings = IndexedStrings()
        else:
            strings = None
        writer = CFFWriter(isCFF2)
        topCompiler = self.topDictIndex.getCompiler(strings, self, isCFF2=isCFF2)
        if isCFF2:
            self.hdrSize = 5
            writer.add(sstruct.pack(cffHeaderFormat, self))
            # Note: topDictSize will most likely change in CFFWriter.toFile().
            self.topDictSize = topCompiler.getDataLength()
            writer.add(struct.pack(">H", self.topDictSize))
        else:
            self.hdrSize = 4
            self.offSize = 4  # will most likely change in CFFWriter.toFile().
            writer.add(sstruct.pack(cffHeaderFormat, self))
            writer.add(struct.pack("B", self.offSize))
        if not isCFF2:
            fontNames = Index()
            for name in self.fontNames:
                fontNames.append(name)
            writer.add(fontNames.getCompiler(strings, self, isCFF2=isCFF2))
        writer.add(topCompiler)
        if not isCFF2:
            writer.add(strings.getCompiler())
        writer.add(self.GlobalSubrs.getCompiler(strings, self, isCFF2=isCFF2))

        for topDict in self.topDictIndex:
            if not hasattr(topDict, "charset") or topDict.charset is None:
                charset = otFont.getGlyphOrder()
                topDict.charset = charset
        children = topCompiler.getChildren(strings)
        for child in children:
            writer.add(child)

        writer.toFile(file)

    def toXML(self, xmlWriter):
        """Write the object into XML representation onto the given
        :class:`fontTools.misc.xmlWriter.XMLWriter`.

        .. code:: python

                writer = xmlWriter.XMLWriter(sys.stdout)
                tt["CFF "].cff.toXML(writer)

        """

        xmlWriter.simpletag("major", value=self.major)
        xmlWriter.newline()
        xmlWriter.simpletag("minor", value=self.minor)
        xmlWriter.newline()
        for fontName in self.fontNames:
            xmlWriter.begintag("CFFFont", name=tostr(fontName))
            xmlWriter.newline()
            font = self[fontName]
            font.toXML(xmlWriter)
            xmlWriter.endtag("CFFFont")
            xmlWriter.newline()
        xmlWriter.newline()
        xmlWriter.begintag("GlobalSubrs")
        xmlWriter.newline()
        self.GlobalSubrs.toXML(xmlWriter)
        xmlWriter.endtag("GlobalSubrs")
        xmlWriter.newline()

    def fromXML(self, name, attrs, content, otFont=None):
        """Reads data from the XML element into the ``CFFFontSet`` object."""
        self.otFont = otFont

        # set defaults. These will be replaced if there are entries for them
        # in the XML file.
        if not hasattr(self, "major"):
            self.major = 1
        if not hasattr(self, "minor"):
            self.minor = 0

        if name == "CFFFont":
            if self.major == 1:
                if not hasattr(self, "offSize"):
                    # this will be recalculated when the cff is compiled.
                    self.offSize = 4
                if not hasattr(self, "hdrSize"):
                    self.hdrSize = 4
                if not hasattr(self, "GlobalSubrs"):
                    self.GlobalSubrs = GlobalSubrsIndex()
                if not hasattr(self, "fontNames"):
                    self.fontNames = []
                    self.topDictIndex = TopDictIndex()
                fontName = attrs["name"]
                self.fontNames.append(fontName)
                topDict = TopDict(GlobalSubrs=self.GlobalSubrs)
                topDict.charset = None  # gets filled in later
            elif self.major == 2:
                if not hasattr(self, "hdrSize"):
                    self.hdrSize = 5
                if not hasattr(self, "GlobalSubrs"):
                    self.GlobalSubrs = GlobalSubrsIndex()
                if not hasattr(self, "fontNames"):
                    self.fontNames = ["CFF2Font"]
                cff2GetGlyphOrder = self.otFont.getGlyphOrder
                topDict = TopDict(
                    GlobalSubrs=self.GlobalSubrs, cff2GetGlyphOrder=cff2GetGlyphOrder
                )
                self.topDictIndex = TopDictIndex(None, cff2GetGlyphOrder)
            self.topDictIndex.append(topDict)
            for element in content:
                if isinstance(element, str):
                    continue
                name, attrs, content = element
                topDict.fromXML(name, attrs, content)

            if hasattr(topDict, "VarStore") and topDict.FDArray[0].vstore is None:
                fdArray = topDict.FDArray
                for fontDict in fdArray:
                    if hasattr(fontDict, "Private"):
                        fontDict.Private.vstore = topDict.VarStore

        elif name == "GlobalSubrs":
            subrCharStringClass = psCharStrings.T2CharString
            if not hasattr(self, "GlobalSubrs"):
                self.GlobalSubrs = GlobalSubrsIndex()
            for element in content:
                if isinstance(element, str):
                    continue
                name, attrs, content = element
                subr = subrCharStringClass()
                subr.fromXML(name, attrs, content)
                self.GlobalSubrs.append(subr)
        elif name == "major":
            self.major = int(attrs["value"])
        elif name == "minor":
            self.minor = int(attrs["value"])

    def convertCFFToCFF2(self, otFont):
        from .CFFToCFF2 import _convertCFFToCFF2

        _convertCFFToCFF2(self, otFont)

    def convertCFF2ToCFF(self, otFont):
        from .CFF2ToCFF import _convertCFF2ToCFF

        _convertCFF2ToCFF(self, otFont)

    def desubroutinize(self):
        from .transforms import desubroutinize

        desubroutinize(self)

    def remove_hints(self):
        from .transforms import remove_hints

        remove_hints(self)

    def remove_unused_subroutines(self):
        from .transforms import remove_unused_subroutines

        remove_unused_subroutines(self)


class CFFWriter(object):
    """Helper class for serializing CFF data to binary. Used by
    :meth:`CFFFontSet.compile`."""

    def __init__(self, isCFF2):
        self.data = []
        self.isCFF2 = isCFF2

    def add(self, table):
        self.data.append(table)

    def toFile(self, file):
        lastPosList = None
        count = 1
        while True:
            log.log(DEBUG, "CFFWriter.toFile() iteration: %d", count)
            count = count + 1
            pos = 0
            posList = [pos]
            for item in self.data:
                if hasattr(item, "getDataLength"):
                    endPos = pos + item.getDataLength()
                    if isinstance(item, TopDictIndexCompiler) and item.isCFF2:
                        self.topDictSize = item.getDataLength()
                else:
                    endPos = pos + len(item)
                if hasattr(item, "setPos"):
                    item.setPos(pos, endPos)
                pos = endPos
                posList.append(pos)
            if posList == lastPosList:
                break
            lastPosList = posList
        log.log(DEBUG, "CFFWriter.toFile() writing to file.")
        begin = file.tell()
        if self.isCFF2:
            self.data[1] = struct.pack(">H", self.topDictSize)
        else:
            self.offSize = calcOffSize(lastPosList[-1])
            self.data[1] = struct.pack("B", self.offSize)
        posList = [0]
        for item in self.data:
            if hasattr(item, "toFile"):
                item.toFile(file)
            else:
                file.write(item)
            posList.append(file.tell() - begin)
        assert posList == lastPosList


def calcOffSize(largestOffset):
    if largestOffset < 0x100:
        offSize = 1
    elif largestOffset < 0x10000:
        offSize = 2
    elif largestOffset < 0x1000000:
        offSize = 3
    else:
        offSize = 4
    return offSize


class IndexCompiler(object):
    """Base class for writing CFF `INDEX data <https://docs.microsoft.com/en-us/typography/opentype/spec/cff2#5-index-data>`_
    to binary."""

    def __init__(self, items, strings, parent, isCFF2=None):
        if isCFF2 is None and hasattr(parent, "isCFF2"):
            isCFF2 = parent.isCFF2
            assert isCFF2 is not None
        self.isCFF2 = isCFF2
        self.items = self.getItems(items, strings)
        self.parent = parent

    def getItems(self, items, strings):
        return items

    def getOffsets(self):
        # An empty INDEX contains only the count field.
        if self.items:
            pos = 1
            offsets = [pos]
            for item in self.items:
                if hasattr(item, "getDataLength"):
                    pos = pos + item.getDataLength()
                else:
                    pos = pos + len(item)
                offsets.append(pos)
        else:
            offsets = []
        return offsets

    def getDataLength(self):
        if self.isCFF2:
            countSize = 4
        else:
            countSize = 2

        if self.items:
            lastOffset = self.getOffsets()[-1]
            offSize = calcOffSize(lastOffset)
            dataLength = (
                countSize
                + 1  # count
                + (len(self.items) + 1) * offSize  # offSize
                + lastOffset  # the offsets
                - 1  # size of object data
            )
        else:
            # count. For empty INDEX tables, this is the only entry.
            dataLength = countSize

        return dataLength

    def toFile(self, file):
        offsets = self.getOffsets()
        if self.isCFF2:
            writeCard32(file, len(self.items))
        else:
            writeCard16(file, len(self.items))
        # An empty INDEX contains only the count field.
        if self.items:
            offSize = calcOffSize(offsets[-1])
            writeCard8(file, offSize)
            offSize = -offSize
            pack = struct.pack
            for offset in offsets:
                binOffset = pack(">l", offset)[offSize:]
                assert len(binOffset) == -offSize
                file.write(binOffset)
            for item in self.items:
                if hasattr(item, "toFile"):
                    item.toFile(file)
                else:
                    data = tobytes(item, encoding="latin1")
                    file.write(data)


class IndexedStringsCompiler(IndexCompiler):
    def getItems(self, items, strings):
        return items.strings


class TopDictIndexCompiler(IndexCompiler):
    """Helper class for writing the TopDict to binary."""

    def getItems(self, items, strings):
        out = []
        for item in items:
            out.append(item.getCompiler(strings, self))
        return out

    def getChildren(self, strings):
        children = []
        for topDict in self.items:
            children.extend(topDict.getChildren(strings))
        return children

    def getOffsets(self):
        if self.isCFF2:
            offsets = [0, self.items[0].getDataLength()]
            return offsets
        else:
            return super(TopDictIndexCompiler, self).getOffsets()

    def getDataLength(self):
        if self.isCFF2:
            dataLength = self.items[0].getDataLength()
            return dataLength
        else:
            return super(TopDictIndexCompiler, self).getDataLength()

    def toFile(self, file):
        if self.isCFF2:
            self.items[0].toFile(file)
        else:
            super(TopDictIndexCompiler, self).toFile(file)


class FDArrayIndexCompiler(IndexCompiler):
    """Helper class for writing the
    `Font DICT INDEX <https://docs.microsoft.com/en-us/typography/opentype/spec/cff2#10-font-dict-index-font-dicts-and-fdselect>`_
    to binary."""

    def getItems(self, items, strings):
        out = []
        for item in items:
            out.append(item.getCompiler(strings, self))
        return out

    def getChildren(self, strings):
        children = []
        for fontDict in self.items:
            children.extend(fontDict.getChildren(strings))
        return children

    def toFile(self, file):
        offsets = self.getOffsets()
        if self.isCFF2:
            writeCard32(file, len(self.items))
        else:
            writeCard16(file, len(self.items))
        offSize = calcOffSize(offsets[-1])
        writeCard8(file, offSize)
        offSize = -offSize
        pack = struct.pack
        for offset in offsets:
            binOffset = pack(">l", offset)[offSize:]
            assert len(binOffset) == -offSize
            file.write(binOffset)
        for item in self.items:
            if hasattr(item, "toFile"):
                item.toFile(file)
            else:
                file.write(item)

    def setPos(self, pos, endPos):
        self.parent.rawDict["FDArray"] = pos


class GlobalSubrsCompiler(IndexCompiler):
    """Helper class for writing the `global subroutine INDEX <https://docs.microsoft.com/en-us/typography/opentype/spec/cff2#9-local-and-global-subr-indexes>`_
    to binary."""

    def getItems(self, items, strings):
        out = []
        for cs in items:
            cs.compile(self.isCFF2)
            out.append(cs.bytecode)
        return out


class SubrsCompiler(GlobalSubrsCompiler):
    """Helper class for writing the `local subroutine INDEX <https://docs.microsoft.com/en-us/typography/opentype/spec/cff2#9-local-and-global-subr-indexes>`_
    to binary."""

    def setPos(self, pos, endPos):
        offset = pos - self.parent.pos
        self.parent.rawDict["Subrs"] = offset


class CharStringsCompiler(GlobalSubrsCompiler):
    """Helper class for writing the `CharStrings INDEX <https://docs.microsoft.com/en-us/typography/opentype/spec/cff2#9-local-and-global-subr-indexes>`_
    to binary."""

    def getItems(self, items, strings):
        out = []
        for cs in items:
            cs.compile(self.isCFF2)
            out.append(cs.bytecode)
        return out

    def setPos(self, pos, endPos):
        self.parent.rawDict["CharStrings"] = pos


class Index(object):
    """This class represents what the CFF spec calls an INDEX (an array of
    variable-sized objects). `Index` items can be addressed and set using
    Python list indexing."""

    compilerClass = IndexCompiler

    def __init__(self, file=None, isCFF2=None):
        self.items = []
        self.offsets = offsets = []
        name = self.__class__.__name__
        if file is None:
            return
        self._isCFF2 = isCFF2
        log.log(DEBUG, "loading %s at %s", name, file.tell())
        self.file = file
        if isCFF2:
            count = readCard32(file)
        else:
            count = readCard16(file)
        if count == 0:
            return
        self.items = [None] * count
        offSize = readCard8(file)
        log.log(DEBUG, "    index count: %s offSize: %s", count, offSize)
        assert offSize <= 4, "offSize too large: %s" % offSize
        pad = b"\0" * (4 - offSize)
        for index in range(count + 1):
            chunk = file.read(offSize)
            chunk = pad + chunk
            (offset,) = struct.unpack(">L", chunk)
            offsets.append(int(offset))
        self.offsetBase = file.tell() - 1
        file.seek(self.offsetBase + offsets[-1])  # pretend we've read the whole lot
        log.log(DEBUG, "    end of %s at %s", name, file.tell())

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        item = self.items[index]
        if item is not None:
            return item
        offset = self.offsets[index] + self.offsetBase
        size = self.offsets[index + 1] - self.offsets[index]
        file = self.file
        file.seek(offset)
        data = file.read(size)
        assert len(data) == size
        item = self.produceItem(index, data, file, offset)
        self.items[index] = item
        return item

    def __setitem__(self, index, item):
        self.items[index] = item

    def produceItem(self, index, data, file, offset):
        return data

    def append(self, item):
        """Add an item to an INDEX."""
        self.items.append(item)

    def getCompiler(self, strings, parent, isCFF2=None):
        return self.compilerClass(self, strings, parent, isCFF2=isCFF2)

    def clear(self):
        """Empty the INDEX."""
        del self.items[:]


class GlobalSubrsIndex(Index):
    """This index contains all the global subroutines in the font. A global
    subroutine is a set of ``CharString`` data which is accessible to any
    glyph in the font, and are used to store repeated instructions - for
    example, components may be encoded as global subroutines, but so could
    hinting instructions.

    Remember that when interpreting a ``callgsubr`` instruction (or indeed
    a ``callsubr`` instruction) that you will need to add the "subroutine
    number bias" to number given:

    .. code:: python

            tt = ttLib.TTFont("Almendra-Bold.otf")
            u = tt["CFF "].cff[0].CharStrings["udieresis"]
            u.decompile()

            u.toXML(XMLWriter(sys.stdout))
            # <some stuff>
            # -64 callgsubr <-- Subroutine which implements the dieresis mark
            # <other stuff>

            tt["CFF "].cff[0].GlobalSubrs[-64] # <-- WRONG
            # <T2CharString (bytecode) at 103451d10>

            tt["CFF "].cff[0].GlobalSubrs[-64 + 107] # <-- RIGHT
            # <T2CharString (source) at 103451390>

    ("The bias applied depends on the number of subrs (gsubrs). If the number of
    subrs (gsubrs) is less than 1240, the bias is 107. Otherwise if it is less
    than 33900, it is 1131; otherwise it is 32768.",
    `Subroutine Operators <https://docs.microsoft.com/en-us/typography/opentype/otspec180/cff2charstr#section4.4>`)
    """

    compilerClass = GlobalSubrsCompiler
    subrClass = psCharStrings.T2CharString
    charStringClass = psCharStrings.T2CharString

    def __init__(
        self,
        file=None,
        globalSubrs=None,
        private=None,
        fdSelect=None,
        fdArray=None,
        isCFF2=None,
    ):
        super(GlobalSubrsIndex, self).__init__(file, isCFF2=isCFF2)
        self.globalSubrs = globalSubrs
        self.private = private
        if fdSelect:
            self.fdSelect = fdSelect
        if fdArray:
            self.fdArray = fdArray

    def produceItem(self, index, data, file, offset):
        if self.private is not None:
            private = self.private
        elif hasattr(self, "fdArray") and self.fdArray is not None:
            if hasattr(self, "fdSelect") and self.fdSelect is not None:
                fdIndex = self.fdSelect[index]
            else:
                fdIndex = 0
            private = self.fdArray[fdIndex].Private
        else:
            private = None
        return self.subrClass(data, private=private, globalSubrs=self.globalSubrs)

    def toXML(self, xmlWriter):
        """Write the subroutines index into XML representation onto the given
        :class:`fontTools.misc.xmlWriter.XMLWriter`.

        .. code:: python

                writer = xmlWriter.XMLWriter(sys.stdout)
                tt["CFF "].cff[0].GlobalSubrs.toXML(writer)

        """
        xmlWriter.comment(
            "The 'index' attribute is only for humans; " "it is ignored when parsed."
        )
        xmlWriter.newline()
        for i in range(len(self)):
            subr = self[i]
            if subr.needsDecompilation():
                xmlWriter.begintag("CharString", index=i, raw=1)
            else:
                xmlWriter.begintag("CharString", index=i)
            xmlWriter.newline()
            subr.toXML(xmlWriter)
            xmlWriter.endtag("CharString")
            xmlWriter.newline()

    def fromXML(self, name, attrs, content):
        if name != "CharString":
            return
        subr = self.subrClass()
        subr.fromXML(name, attrs, content)
        self.append(subr)

    def getItemAndSelector(self, index):
        sel = None
        if hasattr(self, "fdSelect"):
            sel = self.fdSelect[index]
        return self[index], sel


class SubrsIndex(GlobalSubrsIndex):
    """This index contains a glyph's local subroutines. A local subroutine is a
    private set of ``CharString`` data which is accessible only to the glyph to
    which the index is attached."""

    compilerClass = SubrsCompiler


class TopDictIndex(Index):
    """This index represents the array of ``TopDict`` structures in the font
    (again, usually only one entry is present). Hence the following calls are
    equivalent:

    .. code:: python

            tt["CFF "].cff[0]
            # <fontTools.cffLib.TopDict object at 0x102ed6e50>
            tt["CFF "].cff.topDictIndex[0]
            # <fontTools.cffLib.TopDict object at 0x102ed6e50>

    """

    compilerClass = TopDictIndexCompiler

    def __init__(self, file=None, cff2GetGlyphOrder=None, topSize=0, isCFF2=None):
        self.cff2GetGlyphOrder = cff2GetGlyphOrder
        if file is not None and isCFF2:
            self._isCFF2 = isCFF2
            self.items = []
            name = self.__class__.__name__
            log.log(DEBUG, "loading %s at %s", name, file.tell())
            self.file = file
            count = 1
            self.items = [None] * count
            self.offsets = [0, topSize]
            self.offsetBase = file.tell()
            # pretend we've read the whole lot
            file.seek(self.offsetBase + topSize)
            log.log(DEBUG, "    end of %s at %s", name, file.tell())
        else:
            super(TopDictIndex, self).__init__(file, isCFF2=isCFF2)

    def produceItem(self, index, data, file, offset):
        top = TopDict(
            self.strings,
            file,
            offset,
            self.GlobalSubrs,
            self.cff2GetGlyphOrder,
            isCFF2=self._isCFF2,
        )
        top.decompile(data)
        return top

    def toXML(self, xmlWriter):
        for i in range(len(self)):
            xmlWriter.begintag("FontDict", index=i)
            xmlWriter.newline()
            self[i].toXML(xmlWriter)
            xmlWriter.endtag("FontDict")
            xmlWriter.newline()


class FDArrayIndex(Index):
    compilerClass = FDArrayIndexCompiler

    def toXML(self, xmlWriter):
        for i in range(len(self)):
            xmlWriter.begintag("FontDict", index=i)
            xmlWriter.newline()
            self[i].toXML(xmlWriter)
            xmlWriter.endtag("FontDict")
            xmlWriter.newline()

    def produceItem(self, index, data, file, offset):
        fontDict = FontDict(
            self.strings,
            file,
            offset,
            self.GlobalSubrs,
            isCFF2=self._isCFF2,
            vstore=self.vstore,
        )
        fontDict.decompile(data)
        return fontDict

    def fromXML(self, name, attrs, content):
        if name != "FontDict":
            return
        fontDict = FontDict()
        for element in content:
            if isinstance(element, str):
                continue
            name, attrs, content = element
            fontDict.fromXML(name, attrs, content)
        self.append(fontDict)


class VarStoreData(object):
    def __init__(self, file=None, otVarStore=None):
        self.file = file
        self.data = None
        self.otVarStore = otVarStore
        self.font = TTFont()  # dummy font for the decompile function.

    def decompile(self):
        if self.file:
            # read data in from file. Assume position is correct.
            length = readCard16(self.file)
            # https://github.com/fonttools/fonttools/issues/3673
            if length == 65535:
                self.data = self.file.read()
            else:
                self.data = self.file.read(length)
            globalState = {}
            reader = OTTableReader(self.data, globalState)
            self.otVarStore = ot.VarStore()
            self.otVarStore.decompile(reader, self.font)
            self.data = None
        return self

    def compile(self):
        writer = OTTableWriter()
        self.otVarStore.compile(writer, self.font)
        # Note that this omits the initial Card16 length from the CFF2
        # VarStore data block
        self.data = writer.getAllData()

    def writeXML(self, xmlWriter, name):
        self.otVarStore.toXML(xmlWriter, self.font)

    def xmlRead(self, name, attrs, content, parent):
        self.otVarStore = ot.VarStore()
        for element in content:
            if isinstance(element, tuple):
                name, attrs, content = element
                self.otVarStore.fromXML(name, attrs, content, self.font)
            else:
                pass
        return None

    def __len__(self):
        return len(self.data)

    def getNumRegions(self, vsIndex):
        if vsIndex is None:
            vsIndex = 0
        varData = self.otVarStore.VarData[vsIndex]
        numRegions = varData.VarRegionCount
        return numRegions


class FDSelect(object):
    def __init__(self, file=None, numGlyphs=None, format=None):
        if file:
            # read data in from file
            self.format = readCard8(file)
            if self.format == 0:
                from array import array

                self.gidArray = array("B", file.read(numGlyphs)).tolist()
            elif self.format == 3:
                gidArray = [None] * numGlyphs
                nRanges = readCard16(file)
                fd = None
                prev = None
                for i in range(nRanges):
                    first = readCard16(file)
                    if prev is not None:
                        for glyphID in range(prev, first):
                            gidArray[glyphID] = fd
                    prev = first
                    fd = readCard8(file)
                if prev is not None:
                    first = readCard16(file)
                    for glyphID in range(prev, first):
                        gidArray[glyphID] = fd
                self.gidArray = gidArray
            elif self.format == 4:
                gidArray = [None] * numGlyphs
                nRanges = readCard32(file)
                fd = None
                prev = None
                for i in range(nRanges):
                    first = readCard32(file)
                    if prev is not None:
                        for glyphID in range(prev, first):
                            gidArray[glyphID] = fd
                    prev = first
                    fd = readCard16(file)
                if prev is not None:
                    first = readCard32(file)
                    for glyphID in range(prev, first):
                        gidArray[glyphID] = fd
                self.gidArray = gidArray
            else:
                assert False, "unsupported FDSelect format: %s" % format
        else:
            # reading from XML. Make empty gidArray, and leave format as passed in.
            # format is None will result in the smallest representation being used.
            self.format = format
            self.gidArray = []

    def __len__(self):
        return len(self.gidArray)

    def __getitem__(self, index):
        return self.gidArray[index]

    def __setitem__(self, index, fdSelectValue):
        self.gidArray[index] = fdSelectValue

    def append(self, fdSelectValue):
        self.gidArray.append(fdSelectValue)


class CharStrings(object):
    """The ``CharStrings`` in the font represent the instructions for drawing
    each glyph. This object presents a dictionary interface to the font's
    CharStrings, indexed by glyph name:

    .. code:: python

            tt["CFF "].cff[0].CharStrings["a"]
            # <T2CharString (bytecode) at 103451e90>

    See :class:`fontTools.misc.psCharStrings.T1CharString` and
    :class:`fontTools.misc.psCharStrings.T2CharString` for how to decompile,
    compile and interpret the glyph drawing instructions in the returned objects.

    """

    def __init__(
        self,
        file,
        charset,
        globalSubrs,
        private,
        fdSelect,
        fdArray,
        isCFF2=None,
        varStore=None,
    ):
        self.globalSubrs = globalSubrs
        self.varStore = varStore
        if file is not None:
            self.charStringsIndex = SubrsIndex(
                file, globalSubrs, private, fdSelect, fdArray, isCFF2=isCFF2
            )
            self.charStrings = charStrings = {}
            for i in range(len(charset)):
                charStrings[charset[i]] = i
            # read from OTF file: charStrings.values() are indices into
            # charStringsIndex.
            self.charStringsAreIndexed = 1
        else:
            self.charStrings = {}
            # read from ttx file: charStrings.values() are actual charstrings
            self.charStringsAreIndexed = 0
            self.private = private
            if fdSelect is not None:
                self.fdSelect = fdSelect
            if fdArray is not None:
                self.fdArray = fdArray

    def keys(self):
        return list(self.charStrings.keys())

    def values(self):
        if self.charStringsAreIndexed:
            return self.charStringsIndex
        else:
            return list(self.charStrings.values())

    def has_key(self, name):
        return name in self.charStrings

    __contains__ = has_key

    def __len__(self):
        return len(self.charStrings)

    def __getitem__(self, name):
        charString = self.charStrings[name]
        if self.charStringsAreIndexed:
            charString = self.charStringsIndex[charString]
        return charString

    def __setitem__(self, name, charString):
        if self.charStringsAreIndexed:
            index = self.charStrings[name]
            self.charStringsIndex[index] = charString
        else:
            self.charStrings[name] = charString

    def getItemAndSelector(self, name):
        if self.charStringsAreIndexed:
            index = self.charStrings[name]
            return self.charStringsIndex.getItemAndSelector(index)
        else:
            if hasattr(self, "fdArray"):
                if hasattr(self, "fdSelect"):
                    sel = self.charStrings[name].fdSelectIndex
                else:
                    sel = 0
            else:
                sel = None
            return self.charStrings[name], sel

    def toXML(self, xmlWriter):
        names = sorted(self.keys())
        for name in names:
            charStr, fdSelectIndex = self.getItemAndSelector(name)
            if charStr.needsDecompilation():
                raw = [("raw", 1)]
            else:
                raw = []
            if fdSelectIndex is None:
                xmlWriter.begintag("CharString", [("name", name)] + raw)
            else:
                xmlWriter.begintag(
                    "CharString",
                    [("name", name), ("fdSelectIndex", fdSelectIndex)] + raw,
                )
            xmlWriter.newline()
            charStr.toXML(xmlWriter)
            xmlWriter.endtag("CharString")
            xmlWriter.newline()

    def fromXML(self, name, attrs, content):
        for element in content:
            if isinstance(element, str):
                continue
            name, attrs, content = element
            if name != "CharString":
                continue
            fdID = -1
            if hasattr(self, "fdArray"):
                try:
                    fdID = safeEval(attrs["fdSelectIndex"])
                except KeyError:
                    fdID = 0
                private = self.fdArray[fdID].Private
            else:
                private = self.private

            glyphName = attrs["name"]
            charStringClass = psCharStrings.T2CharString
            charString = charStringClass(private=private, globalSubrs=self.globalSubrs)
            charString.fromXML(name, attrs, content)
            if fdID >= 0:
                charString.fdSelectIndex = fdID
            self[glyphName] = charString


def readCard8(file):
    return byteord(file.read(1))


def readCard16(file):
    (value,) = struct.unpack(">H", file.read(2))
    return value


def readCard32(file):
    (value,) = struct.unpack(">L", file.read(4))
    return value


def writeCard8(file, value):
    file.write(bytechr(value))


def writeCard16(file, value):
    file.write(struct.pack(">H", value))


def writeCard32(file, value):
    file.write(struct.pack(">L", value))


def packCard8(value):
    return bytechr(value)


def packCard16(value):
    return struct.pack(">H", value)


def packCard32(value):
    return struct.pack(">L", value)


def buildOperatorDict(table):
    d = {}
    for op, name, arg, default, conv in table:
        d[op] = (name, arg)
    return d


def buildOpcodeDict(table):
    d = {}
    for op, name, arg, default, conv in table:
        if isinstance(op, tuple):
            op = bytechr(op[0]) + bytechr(op[1])
        else:
            op = bytechr(op)
        d[name] = (op, arg)
    return d


def buildOrder(table):
    l = []
    for op, name, arg, default, conv in table:
        l.append(name)
    return l


def buildDefaults(table):
    d = {}
    for op, name, arg, default, conv in table:
        if default is not None:
            d[name] = default
    return d


def buildConverters(table):
    d = {}
    for op, name, arg, default, conv in table:
        d[name] = conv
    return d


class SimpleConverter(object):
    def read(self, parent, value):
        if not hasattr(parent, "file"):
            return self._read(parent, value)
        file = parent.file
        pos = file.tell()
        try:
            return self._read(parent, value)
        finally:
            file.seek(pos)

    def _read(self, parent, value):
        return value

    def write(self, parent, value):
        return value

    def xmlWrite(self, xmlWriter, name, value):
        xmlWriter.simpletag(name, value=value)
        xmlWriter.newline()

    def xmlRead(self, name, attrs, content, parent):
        return attrs["value"]


class ASCIIConverter(SimpleConverter):
    def _read(self, parent, value):
        return tostr(value, encoding="ascii")

    def write(self, parent, value):
        return tobytes(value, encoding="ascii")

    def xmlWrite(self, xmlWriter, name, value):
        xmlWriter.simpletag(name, value=tostr(value, encoding="ascii"))
        xmlWriter.newline()

    def xmlRead(self, name, attrs, content, parent):
        return tobytes(attrs["value"], encoding=("ascii"))


class Latin1Converter(SimpleConverter):
    def _read(self, parent, value):
        return tostr(value, encoding="latin1")

    def write(self, parent, value):
        return tobytes(value, encoding="latin1")

    def xmlWrite(self, xmlWriter, name, value):
        value = tostr(value, encoding="latin1")
        if name in ["Notice", "Copyright"]:
            value = re.sub(r"[\r\n]\s+", " ", value)
        xmlWriter.simpletag(name, value=value)
        xmlWriter.newline()

    def xmlRead(self, name, attrs, content, parent):
        return tobytes(attrs["value"], encoding=("latin1"))


def parseNum(s):
    try:
        value = int(s)
    except:
        value = float(s)
    return value


def parseBlendList(s):
    valueList = []
    for element in s:
        if isinstance(element, str):
            continue
        name, attrs, content = element
        blendList = attrs["value"].split()
        blendList = [eval(val) for val in blendList]
        valueList.append(blendList)
    if len(valueList) == 1:
        valueList = valueList[0]
    return valueList


class NumberConverter(SimpleConverter):
    def xmlWrite(self, xmlWriter, name, value):
        if isinstance(value, list):
            xmlWriter.begintag(name)
            xmlWriter.newline()
            xmlWriter.indent()
            blendValue = " ".join([str(val) for val in value])
            xmlWriter.simpletag(kBlendDictOpName, value=blendValue)
            xmlWriter.newline()
            xmlWriter.dedent()
            xmlWriter.endtag(name)
            xmlWriter.newline()
        else:
            xmlWriter.simpletag(name, value=value)
            xmlWriter.newline()

    def xmlRead(self, name, attrs, content, parent):
        valueString = attrs.get("value", None)
        if valueString is None:
            value = parseBlendList(content)
        else:
            value = parseNum(attrs["value"])
        return value


class ArrayConverter(SimpleConverter):
    def xmlWrite(self, xmlWriter, name, value):
        if value and isinstance(value[0], list):
            xmlWriter.begintag(name)
            xmlWriter.newline()
            xmlWriter.indent()
            for valueList in value:
                blendValue = " ".join([str(val) for val in valueList])
                xmlWriter.simpletag(kBlendDictOpName, value=blendValue)
                xmlWriter.newline()
            xmlWriter.dedent()
            xmlWriter.endtag(name)
            xmlWriter.newline()
        else:
            value = " ".join([str(val) for val in value])
            xmlWriter.simpletag(name, value=value)
            xmlWriter.newline()

    def xmlRead(self, name, attrs, content, parent):
        valueString = attrs.get("value", None)
        if valueString is None:
            valueList = parseBlendList(content)
        else:
            values = valueString.split()
            valueList = [parseNum(value) for value in values]
        return valueList


class TableConverter(SimpleConverter):
    def xmlWrite(self, xmlWriter, name, value):
        xmlWriter.begintag(name)
        xmlWriter.newline()
        value.toXML(xmlWriter)
        xmlWriter.endtag(name)
        xmlWriter.newline()

    def xmlRead(self, name, attrs, content, parent):
        ob = self.getClass()()
        for element in content:
            if isinstance(element, str):
                continue
            name, attrs, content = element
            ob.fromXML(name, attrs, content)
        return ob


class PrivateDictConverter(TableConverter):
    def getClass(self):
        return PrivateDict

    def _read(self, parent, value):
        size, offset = value
        file = parent.file
        isCFF2 = parent._isCFF2
        try:
            vstore = parent.vstore
        except AttributeError:
            vstore = None
        priv = PrivateDict(parent.strings, file, offset, isCFF2=isCFF2, vstore=vstore)
        file.seek(offset)
        data = file.read(size)
        assert len(data) == size
        priv.decompile(data)
        return priv

    def write(self, parent, value):
        return (0, 0)  # dummy value


class SubrsConverter(TableConverter):
    def getClass(self):
        return SubrsIndex

    def _read(self, parent, value):
        file = parent.file
        isCFF2 = parent._isCFF2
        file.seek(parent.offset + value)  # Offset(self)
        return SubrsIndex(file, isCFF2=isCFF2)

    def write(self, parent, value):
        return 0  # dummy value


class CharStringsConverter(TableConverter):
    def _read(self, parent, value):
        file = parent.file
        isCFF2 = parent._isCFF2
        charset = parent.charset
        varStore = getattr(parent, "VarStore", None)
        globalSubrs = parent.GlobalSubrs
        if hasattr(parent, "FDArray"):
            fdArray = parent.FDArray
            if hasattr(parent, "FDSelect"):
                fdSelect = parent.FDSelect
            else:
                fdSelect = None
            private = None
        else:
            fdSelect, fdArray = None, None
            private = parent.Private
        file.seek(value)  # Offset(0)
        charStrings = CharStrings(
            file,
            charset,
            globalSubrs,
            private,
            fdSelect,
            fdArray,
            isCFF2=isCFF2,
            varStore=varStore,
        )
        return charStrings

    def write(self, parent, value):
        return 0  # dummy value

    def xmlRead(self, name, attrs, content, parent):
        if hasattr(parent, "FDArray"):
            # if it is a CID-keyed font, then the private Dict is extracted from the
            # parent.FDArray
            fdArray = parent.FDArray
            if hasattr(parent, "FDSelect"):
                fdSelect = parent.FDSelect
            else:
                fdSelect = None
            private = None
        else:
            # if it is a name-keyed font, then the private dict is in the top dict,
            # and
            # there is no fdArray.
            private, fdSelect, fdArray = parent.Private, None, None
        charStrings = CharStrings(
            None,
            None,
            parent.GlobalSubrs,
            private,
            fdSelect,
            fdArray,
            varStore=getattr(parent, "VarStore", None),
        )
        charStrings.fromXML(name, attrs, content)
        return charStrings


class CharsetConverter(SimpleConverter):
    def _read(self, parent, value):
        isCID = hasattr(parent, "ROS")
        if value > 2:
            numGlyphs = parent.numGlyphs
            file = parent.file
            file.seek(value)
            log.log(DEBUG, "loading charset at %s", value)
            format = readCard8(file)
            if format == 0:
                charset = parseCharset0(numGlyphs, file, parent.strings, isCID)
            elif format == 1 or format == 2:
                charset = parseCharset(numGlyphs, file, parent.strings, isCID, format)
            else:
                raise NotImplementedError
            assert len(charset) == numGlyphs
            log.log(DEBUG, "    charset end at %s", file.tell())
            # make sure glyph names are unique
            allNames = {}
            newCharset = []
            for glyphName in charset:
                if glyphName in allNames:
                    # make up a new glyphName that's unique
                    n = allNames[glyphName]
                    names = set(allNames) | set(charset)
                    while (glyphName + "." + str(n)) in names:
                        n += 1
                    allNames[glyphName] = n + 1
                    glyphName = glyphName + "." + str(n)
                allNames[glyphName] = 1
                newCharset.append(glyphName)
            charset = newCharset
        else:  # offset == 0 -> no charset data.
            if isCID or "CharStrings" not in parent.rawDict:
                # We get here only when processing fontDicts from the FDArray of
                # CFF-CID fonts. Only the real topDict references the charset.
                assert value == 0
                charset = None
            elif value == 0:
                charset = cffISOAdobeStrings
            elif value == 1:
                charset = cffIExpertStrings
            elif value == 2:
                charset = cffExpertSubsetStrings
        if charset and (len(charset) != parent.numGlyphs):
            charset = charset[: parent.numGlyphs]
        return charset

    def write(self, parent, value):
        return 0  # dummy value

    def xmlWrite(self, xmlWriter, name, value):
        # XXX only write charset when not in OT/TTX context, where we
        # dump charset as a separate "GlyphOrder" table.
        # # xmlWriter.simpletag("charset")
        xmlWriter.comment("charset is dumped separately as the 'GlyphOrder' element")
        xmlWriter.newline()

    def xmlRead(self, name, attrs, content, parent):
        pass


class CharsetCompiler(object):
    def __init__(self, strings, charset, parent):
        assert charset[0] == ".notdef"
        isCID = hasattr(parent.dictObj, "ROS")
        data0 = packCharset0(charset, isCID, strings)
        data = packCharset(charset, isCID, strings)
        if len(data) < len(data0):
            self.data = data
        else:
            self.data = data0
        self.parent = parent

    def setPos(self, pos, endPos):
        self.parent.rawDict["charset"] = pos

    def getDataLength(self):
        return len(self.data)

    def toFile(self, file):
        file.write(self.data)


def getStdCharSet(charset):
    # check to see if we can use a predefined charset value.
    predefinedCharSetVal = None
    predefinedCharSets = [
        (cffISOAdobeStringCount, cffISOAdobeStrings, 0),
        (cffExpertStringCount, cffIExpertStrings, 1),
        (cffExpertSubsetStringCount, cffExpertSubsetStrings, 2),
    ]
    lcs = len(charset)
    for cnt, pcs, csv in predefinedCharSets:
        if predefinedCharSetVal is not None:
            break
        if lcs > cnt:
            continue
        predefinedCharSetVal = csv
        for i in range(lcs):
            if charset[i] != pcs[i]:
                predefinedCharSetVal = None
                break
    return predefinedCharSetVal


def getCIDfromName(name, strings):
    return int(name[3:])


def getSIDfromName(name, strings):
    return strings.getSID(name)


def packCharset0(charset, isCID, strings):
    fmt = 0
    data = [packCard8(fmt)]
    if isCID:
        getNameID = getCIDfromName
    else:
        getNameID = getSIDfromName

    for name in charset[1:]:
        data.append(packCard16(getNameID(name, strings)))
    return bytesjoin(data)


def packCharset(charset, isCID, strings):
    fmt = 1
    ranges = []
    first = None
    end = 0
    if isCID:
        getNameID = getCIDfromName
    else:
        getNameID = getSIDfromName

    for name in charset[1:]:
        SID = getNameID(name, strings)
        if first is None:
            first = SID
        elif end + 1 != SID:
            nLeft = end - first
            if nLeft > 255:
                fmt = 2
            ranges.append((first, nLeft))
            first = SID
        end = SID
    if end:
        nLeft = end - first
        if nLeft > 255:
            fmt = 2
        ranges.append((first, nLeft))

    data = [packCard8(fmt)]
    if fmt == 1:
        nLeftFunc = packCard8
    else:
        nLeftFunc = packCard16
    for first, nLeft in ranges:
        data.append(packCard16(first) + nLeftFunc(nLeft))
    return bytesjoin(data)


def parseCharset0(numGlyphs, file, strings, isCID):
    charset = [".notdef"]
    if isCID:
        for i in range(numGlyphs - 1):
            CID = readCard16(file)
            charset.append("cid" + str(CID).zfill(5))
    else:
        for i in range(numGlyphs - 1):
            SID = readCard16(file)
            charset.append(strings[SID])
    return charset


def parseCharset(numGlyphs, file, strings, isCID, fmt):
    charset = [".notdef"]
    count = 1
    if fmt == 1:
        nLeftFunc = readCard8
    else:
        nLeftFunc = readCard16
    while count < numGlyphs:
        first = readCard16(file)
        nLeft = nLeftFunc(file)
        if isCID:
            for CID in range(first, first + nLeft + 1):
                charset.append("cid" + str(CID).zfill(5))
        else:
            for SID in range(first, first + nLeft + 1):
                charset.append(strings[SID])
        count = count + nLeft + 1
    return charset


class EncodingCompiler(object):
    def __init__(self, strings, encoding, parent):
        assert not isinstance(encoding, str)
        data0 = packEncoding0(parent.dictObj.charset, encoding, parent.strings)
        data1 = packEncoding1(parent.dictObj.charset, encoding, parent.strings)
        if len(data0) < len(data1):
            self.data = data0
        else:
            self.data = data1
        self.parent = parent

    def setPos(self, pos, endPos):
        self.parent.rawDict["Encoding"] = pos

    def getDataLength(self):
        return len(self.data)

    def toFile(self, file):
        file.write(self.data)


class EncodingConverter(SimpleConverter):
    def _read(self, parent, value):
        if value == 0:
            return "StandardEncoding"
        elif value == 1:
            return "ExpertEncoding"
        # custom encoding at offset `value`
        assert value > 1
        file = parent.file
        file.seek(value)
        log.log(DEBUG, "loading Encoding at %s", value)
        fmt = readCard8(file)
        haveSupplement = bool(fmt & 0x80)
        fmt = fmt & 0x7F

        if fmt == 0:
            encoding = parseEncoding0(parent.charset, file)
        elif fmt == 1:
            encoding = parseEncoding1(parent.charset, file)
        else:
            raise ValueError(f"Unknown Encoding format: {fmt}")

        if haveSupplement:
            parseEncodingSupplement(file, encoding, parent.strings)

        return encoding

    def write(self, parent, value):
        if value == "StandardEncoding":
            return 0
        elif value == "ExpertEncoding":
            return 1
        return 0  # dummy value

    def xmlWrite(self, xmlWriter, name, value):
        if value in ("StandardEncoding", "ExpertEncoding"):
            xmlWriter.simpletag(name, name=value)
            xmlWriter.newline()
            return
        xmlWriter.begintag(name)
        xmlWriter.newline()
        for code in range(len(value)):
            glyphName = value[code]
            if glyphName != ".notdef":
                xmlWriter.simpletag("map", code=hex(code), name=glyphName)
                xmlWriter.newline()
        xmlWriter.endtag(name)
        xmlWriter.newline()

    def xmlRead(self, name, attrs, content, parent):
        if "name" in attrs:
            return attrs["name"]
        encoding = [".notdef"] * 256
        for element in content:
            if isinstance(element, str):
                continue
            name, attrs, content = element
            code = safeEval(attrs["code"])
            glyphName = attrs["name"]
            encoding[code] = glyphName
        return encoding


def readSID(file):
    """Read a String ID (SID) — 2-byte unsigned integer."""
    data = file.read(2)
    if len(data) != 2:
        raise EOFError("Unexpected end of file while reading SID")
    return struct.unpack(">H", data)[0]  # big-endian uint16


def parseEncodingSupplement(file, encoding, strings):
    """
    Parse the CFF Encoding supplement data:
      - nSups: number of supplementary mappings
      - each mapping: (code, SID) pair
    and apply them to the `encoding` list in place.
    """
    nSups = readCard8(file)
    for _ in range(nSups):
        code = readCard8(file)
        sid = readSID(file)
        name = strings[sid]
        encoding[code] = name


def parseEncoding0(charset, file):
    """
    Format 0: simple list of codes.
    After reading the base table, optionally parse the supplement.
    """
    nCodes = readCard8(file)
    encoding = [".notdef"] * 256
    for glyphID in range(1, nCodes + 1):
        code = readCard8(file)
        if code != 0:
            encoding[code] = charset[glyphID]

    return encoding


def parseEncoding1(charset, file):
    """
    Format 1: range-based encoding.
    After reading the base ranges, optionally parse the supplement.
    """
    nRanges = readCard8(file)
    encoding = [".notdef"] * 256
    glyphID = 1
    for _ in range(nRanges):
        code = readCard8(file)
        nLeft = readCard8(file)
        for _ in range(nLeft + 1):
            encoding[code] = charset[glyphID]
            code += 1
            glyphID += 1

    return encoding


def packEncoding0(charset, encoding, strings):
    fmt = 0
    m = {}
    for code in range(len(encoding)):
        name = encoding[code]
        if name != ".notdef":
            m[name] = code
    codes = []
    for name in charset[1:]:
        code = m.get(name)
        codes.append(code)

    while codes and codes[-1] is None:
        codes.pop()

    data = [packCard8(fmt), packCard8(len(codes))]
    for code in codes:
        if code is None:
            code = 0
        data.append(packCard8(code))
    return bytesjoin(data)


def packEncoding1(charset, encoding, strings):
    fmt = 1
    m = {}
    for code in range(len(encoding)):
        name = encoding[code]
        if name != ".notdef":
            m[name] = code
    ranges = []
    first = None
    end = 0
    for name in charset[1:]:
        code = m.get(name, -1)
        if first is None:
            first = code
        elif end + 1 != code:
            nLeft = end - first
            ranges.append((first, nLeft))
            first = code
        end = code
    nLeft = end - first
    ranges.append((first, nLeft))

    # remove unencoded glyphs at the end.
    while ranges and ranges[-1][0] == -1:
        ranges.pop()

    data = [packCard8(fmt), packCard8(len(ranges))]
    for first, nLeft in ranges:
        if first == -1:  # unencoded
            first = 0
        data.append(packCard8(first) + packCard8(nLeft))
    return bytesjoin(data)


class FDArrayConverter(TableConverter):
    def _read(self, parent, value):
        try:
            vstore = parent.VarStore
        except AttributeError:
            vstore = None
        file = parent.file
        isCFF2 = parent._isCFF2
        file.seek(value)
        fdArray = FDArrayIndex(file, isCFF2=isCFF2)
        fdArray.vstore = vstore
        fdArray.strings = parent.strings
        fdArray.GlobalSubrs = parent.GlobalSubrs
        return fdArray

    def write(self, parent, value):
        return 0  # dummy value

    def xmlRead(self, name, attrs, content, parent):
        fdArray = FDArrayIndex()
        for element in content:
            if isinstance(element, str):
                continue
            name, attrs, content = element
            fdArray.fromXML(name, attrs, content)
        return fdArray


class FDSelectConverter(SimpleConverter):
    def _read(self, parent, value):
        file = parent.file
        file.seek(value)
        fdSelect = FDSelect(file, parent.numGlyphs)
        return fdSelect

    def write(self, parent, value):
        return 0  # dummy value

    # The FDSelect glyph data is written out to XML in the charstring keys,
    # so we write out only the format selector
    def xmlWrite(self, xmlWriter, name, value):
        xmlWriter.simpletag(name, [("format", value.format)])
        xmlWriter.newline()

    def xmlRead(self, name, attrs, content, parent):
        fmt = safeEval(attrs["format"])
        file = None
        numGlyphs = None
        fdSelect = FDSelect(file, numGlyphs, fmt)
        return fdSelect


class VarStoreConverter(SimpleConverter):
    def _read(self, parent, value):
        file = parent.file
        file.seek(value)
        varStore = VarStoreData(file)
        varStore.decompile()
        return varStore

    def write(self, parent, value):
        return 0  # dummy value

    def xmlWrite(self, xmlWriter, name, value):
        value.writeXML(xmlWriter, name)

    def xmlRead(self, name, attrs, content, parent):
        varStore = VarStoreData()
        varStore.xmlRead(name, attrs, content, parent)
        return varStore


def packFDSelect0(fdSelectArray):
    fmt = 0
    data = [packCard8(fmt)]
    for index in fdSelectArray:
        data.append(packCard8(index))
    return bytesjoin(data)


def packFDSelect3(fdSelectArray):
    fmt = 3
    fdRanges = []
    lenArray = len(fdSelectArray)
    lastFDIndex = -1
    for i in range(lenArray):
        fdIndex = fdSelectArray[i]
        if lastFDIndex != fdIndex:
            fdRanges.append([i, fdIndex])
            lastFDIndex = fdIndex
    sentinelGID = i + 1

    data = [packCard8(fmt)]
    data.append(packCard16(len(fdRanges)))
    for fdRange in fdRanges:
        data.append(packCard16(fdRange[0]))
        data.append(packCard8(fdRange[1]))
    data.append(packCard16(sentinelGID))
    return bytesjoin(data)


def packFDSelect4(fdSelectArray):
    fmt = 4
    fdRanges = []
    lenArray = len(fdSelectArray)
    lastFDIndex = -1
    for i in range(lenArray):
        fdIndex = fdSelectArray[i]
        if lastFDIndex != fdIndex:
            fdRanges.append([i, fdIndex])
            lastFDIndex = fdIndex
    sentinelGID = i + 1

    data = [packCard8(fmt)]
    data.append(packCard32(len(fdRanges)))
    for fdRange in fdRanges:
        data.append(packCard32(fdRange[0]))
        data.append(packCard16(fdRange[1]))
    data.append(packCard32(sentinelGID))
    return bytesjoin(data)


class FDSelectCompiler(object):
    def __init__(self, fdSelect, parent):
        fmt = fdSelect.format
        fdSelectArray = fdSelect.gidArray
        if fmt == 0:
            self.data = packFDSelect0(fdSelectArray)
        elif fmt == 3:
            self.data = packFDSelect3(fdSelectArray)
        elif fmt == 4:
            self.data = packFDSelect4(fdSelectArray)
        else:
            # choose smaller of the two formats
            data0 = packFDSelect0(fdSelectArray)
            data3 = packFDSelect3(fdSelectArray)
            if len(data0) < len(data3):
                self.data = data0
                fdSelect.format = 0
            else:
                self.data = data3
                fdSelect.format = 3

        self.parent = parent

    def setPos(self, pos, endPos):
        self.parent.rawDict["FDSelect"] = pos

    def getDataLength(self):
        return len(self.data)

    def toFile(self, file):
        file.write(self.data)


class VarStoreCompiler(object):
    def __init__(self, varStoreData, parent):
        self.parent = parent
        if not varStoreData.data:
            varStoreData.compile()
        varStoreDataLen = min(0xFFFF, len(varStoreData.data))
        data = [packCard16(varStoreDataLen), varStoreData.data]
        self.data = bytesjoin(data)

    def setPos(self, pos, endPos):
        self.parent.rawDict["VarStore"] = pos

    def getDataLength(self):
        return len(self.data)

    def toFile(self, file):
        file.write(self.data)


class ROSConverter(SimpleConverter):
    def xmlWrite(self, xmlWriter, name, value):
        registry, order, supplement = value
        xmlWriter.simpletag(
            name,
            [
                ("Registry", tostr(registry)),
                ("Order", tostr(order)),
                ("Supplement", supplement),
            ],
        )
        xmlWriter.newline()

    def xmlRead(self, name, attrs, content, parent):
        return (attrs["Registry"], attrs["Order"], safeEval(attrs["Supplement"]))


topDictOperators = [
    # 	opcode		name			argument type	default	converter
    (25, "maxstack", "number", None, None),
    ((12, 30), "ROS", ("SID", "SID", "number"), None, ROSConverter()),
    ((12, 20), "SyntheticBase", "number", None, None),
    (0, "version", "SID", None, None),
    (1, "Notice", "SID", None, Latin1Converter()),
    ((12, 0), "Copyright", "SID", None, Latin1Converter()),
    (2, "FullName", "SID", None, Latin1Converter()),
    ((12, 38), "FontName", "SID", None, Latin1Converter()),
    (3, "FamilyName", "SID", None, Latin1Converter()),
    (4, "Weight", "SID", None, None),
    ((12, 1), "isFixedPitch", "number", 0, None),
    ((12, 2), "ItalicAngle", "number", 0, None),
    ((12, 3), "UnderlinePosition", "number", -100, None),
    ((12, 4), "UnderlineThickness", "number", 50, None),
    ((12, 5), "PaintType", "number", 0, None),
    ((12, 6), "CharstringType", "number", 2, None),
    ((12, 7), "FontMatrix", "array", [0.001, 0, 0, 0.001, 0, 0], None),
    (13, "UniqueID", "number", None, None),
    (5, "FontBBox", "array", [0, 0, 0, 0], None),
    ((12, 8), "StrokeWidth", "number", 0, None),
    (14, "XUID", "array", None, None),
    ((12, 21), "PostScript", "SID", None, None),
    ((12, 22), "BaseFontName", "SID", None, None),
    ((12, 23), "BaseFontBlend", "delta", None, None),
    ((12, 31), "CIDFontVersion", "number", 0, None),
    ((12, 32), "CIDFontRevision", "number", 0, None),
    ((12, 33), "CIDFontType", "number", 0, None),
    ((12, 34), "CIDCount", "number", 8720, None),
    (15, "charset", "number", None, CharsetConverter()),
    ((12, 35), "UIDBase", "number", None, None),
    (16, "Encoding", "number", 0, EncodingConverter()),
    (18, "Private", ("number", "number"), None, PrivateDictConverter()),
    ((12, 37), "FDSelect", "number", None, FDSelectConverter()),
    ((12, 36), "FDArray", "number", None, FDArrayConverter()),
    (17, "CharStrings", "number", None, CharStringsConverter()),
    (24, "VarStore", "number", None, VarStoreConverter()),
]

topDictOperators2 = [
    # 	opcode		name			argument type	default	converter
    (25, "maxstack", "number", None, None),
    ((12, 7), "FontMatrix", "array", [0.001, 0, 0, 0.001, 0, 0], None),
    ((12, 37), "FDSelect", "number", None, FDSelectConverter()),
    ((12, 36), "FDArray", "number", None, FDArrayConverter()),
    (17, "CharStrings", "number", None, CharStringsConverter()),
    (24, "VarStore", "number", None, VarStoreConverter()),
]

# Note! FDSelect and FDArray must both preceed CharStrings in the output XML build order,
# in order for the font to compile back from xml.

kBlendDictOpName = "blend"
blendOp = 23

privateDictOperators = [
    # 	opcode		name			argument type	default	converter
    (22, "vsindex", "number", None, None),
    (
        blendOp,
        kBlendDictOpName,
        "blendList",
        None,
        None,
    ),  # This is for reading to/from XML: it not written to CFF.
    (6, "BlueValues", "delta", None, None),
    (7, "OtherBlues", "delta", None, None),
    (8, "FamilyBlues", "delta", None, None),
    (9, "FamilyOtherBlues", "delta", None, None),
    ((12, 9), "BlueScale", "number", 0.039625, None),
    ((12, 10), "BlueShift", "number", 7, None),
    ((12, 11), "BlueFuzz", "number", 1, None),
    (10, "StdHW", "number", None, None),
    (11, "StdVW", "number", None, None),
    ((12, 12), "StemSnapH", "delta", None, None),
    ((12, 13), "StemSnapV", "delta", None, None),
    ((12, 14), "ForceBold", "number", 0, None),
    ((12, 15), "ForceBoldThreshold", "number", None, None),  # deprecated
    ((12, 16), "lenIV", "number", None, None),  # deprecated
    ((12, 17), "LanguageGroup", "number", 0, None),
    ((12, 18), "ExpansionFactor", "number", 0.06, None),
    ((12, 19), "initialRandomSeed", "number", 0, None),
    (20, "defaultWidthX", "number", 0, None),
    (21, "nominalWidthX", "number", 0, None),
    (19, "Subrs", "number", None, SubrsConverter()),
]

privateDictOperators2 = [
    # 	opcode		name			argument type	default	converter
    (22, "vsindex", "number", None, None),
    (
        blendOp,
        kBlendDictOpName,
        "blendList",
        None,
        None,
    ),  # This is for reading to/from XML: it not written to CFF.
    (6, "BlueValues", "delta", None, None),
    (7, "OtherBlues", "delta", None, None),
    (8, "FamilyBlues", "delta", None, None),
    (9, "FamilyOtherBlues", "delta", None, None),
    ((12, 9), "BlueScale", "number", 0.039625, None),
    ((12, 10), "BlueShift", "number", 7, None),
    ((12, 11), "BlueFuzz", "number", 1, None),
    (10, "StdHW", "number", None, None),
    (11, "StdVW", "number", None, None),
    ((12, 12), "StemSnapH", "delta", None, None),
    ((12, 13), "StemSnapV", "delta", None, None),
    ((12, 17), "LanguageGroup", "number", 0, None),
    ((12, 18), "ExpansionFactor", "number", 0.06, None),
    (19, "Subrs", "number", None, SubrsConverter()),
]


def addConverters(table):
    for i in range(len(table)):
        op, name, arg, default, conv = table[i]
        if conv is not None:
            continue
        if arg in ("delta", "array"):
            conv = ArrayConverter()
        elif arg == "number":
            conv = NumberConverter()
        elif arg == "SID":
            conv = ASCIIConverter()
        elif arg == "blendList":
            conv = None
        else:
            assert False
        table[i] = op, name, arg, default, conv


addConverters(privateDictOperators)
addConverters(topDictOperators)


class TopDictDecompiler(psCharStrings.DictDecompiler):
    operators = buildOperatorDict(topDictOperators)


class PrivateDictDecompiler(psCharStrings.DictDecompiler):
    operators = buildOperatorDict(privateDictOperators)


class DictCompiler(object):
    maxBlendStack = 0

    def __init__(self, dictObj, strings, parent, isCFF2=None):
        if strings:
            assert isinstance(strings, IndexedStrings)
        if isCFF2 is None and hasattr(parent, "isCFF2"):
            isCFF2 = parent.isCFF2
            assert isCFF2 is not None
        self.isCFF2 = isCFF2
        self.dictObj = dictObj
        self.strings = strings
        self.parent = parent
        rawDict = {}
        for name in dictObj.order:
            value = getattr(dictObj, name, None)
            if value is None:
                continue
            conv = dictObj.converters[name]
            value = conv.write(dictObj, value)
            if value == dictObj.defaults.get(name):
                continue
            rawDict[name] = value
        self.rawDict = rawDict

    def setPos(self, pos, endPos):
        pass

    def getDataLength(self):
        return len(self.compile("getDataLength"))

    def compile(self, reason):
        log.log(DEBUG, "-- compiling %s for %s", self.__class__.__name__, reason)
        rawDict = self.rawDict
        data = []
        for name in self.dictObj.order:
            value = rawDict.get(name)
            if value is None:
                continue
            op, argType = self.opcodes[name]
            if isinstance(argType, tuple):
                l = len(argType)
                assert len(value) == l, "value doesn't match arg type"
                for i in range(l):
                    arg = argType[i]
                    v = value[i]
                    arghandler = getattr(self, "arg_" + arg)
                    data.append(arghandler(v))
            else:
                arghandler = getattr(self, "arg_" + argType)
                data.append(arghandler(value))
            data.append(op)
        data = bytesjoin(data)
        return data

    def toFile(self, file):
        data = self.compile("toFile")
        file.write(data)

    def arg_number(self, num):
        if isinstance(num, list):
            data = [encodeNumber(val) for val in num]
            data.append(encodeNumber(1))
            data.append(bytechr(blendOp))
            datum = bytesjoin(data)
        else:
            datum = encodeNumber(num)
        return datum

    def arg_SID(self, s):
        return psCharStrings.encodeIntCFF(self.strings.getSID(s))

    def arg_array(self, value):
        data = []
        for num in value:
            data.append(self.arg_number(num))
        return bytesjoin(data)

    def arg_delta(self, value):
        if not value:
            return b""
        val0 = value[0]
        if isinstance(val0, list):
            data = self.arg_delta_blend(value)
        else:
            out = []
            last = 0
            for v in value:
                out.append(v - last)
                last = v
            data = []
            for num in out:
                data.append(encodeNumber(num))
        return bytesjoin(data)

    def arg_delta_blend(self, value):
        """A delta list with blend lists has to be *all* blend lists.

        The value is a list is arranged as follows::

                [
                        [V0, d0..dn]
                        [V1, d0..dn]
                        ...
                        [Vm, d0..dn]
                ]

        ``V`` is the absolute coordinate value from the default font, and ``d0-dn``
        are the delta values from the *n* regions. Each ``V`` is an absolute
        coordinate from the default font.

        We want to return a list::

                [
                        [v0, v1..vm]
                        [d0..dn]
                        ...
                        [d0..dn]
                        numBlends
                        blendOp
                ]

        where each ``v`` is relative to the previous default font value.
        """
        numMasters = len(value[0])
        numBlends = len(value)
        numStack = (numBlends * numMasters) + 1
        if numStack > self.maxBlendStack:
            # Figure out the max number of value we can blend
            # and divide this list up into chunks of that size.

            numBlendValues = int((self.maxBlendStack - 1) / numMasters)
            out = []
            while True:
                numVal = min(len(value), numBlendValues)
                if numVal == 0:
                    break
                valList = value[0:numVal]
                out1 = self.arg_delta_blend(valList)
                out.extend(out1)
                value = value[numVal:]
        else:
            firstList = [0] * numBlends
            deltaList = [None] * numBlends
            i = 0
            prevVal = 0
            while i < numBlends:
                # For PrivateDict BlueValues, the default font
                # values are absolute, not relative.
                # Must convert these back to relative coordinates
                # before writing to CFF2.
                defaultValue = value[i][0]
                firstList[i] = defaultValue - prevVal
                prevVal = defaultValue
                deltaList[i] = value[i][1:]
                i += 1

            relValueList = firstList
            for blendList in deltaList:
                relValueList.extend(blendList)
            out = [encodeNumber(val) for val in relValueList]
            out.append(encodeNumber(numBlends))
            out.append(bytechr(blendOp))
        return out


def encodeNumber(num):
    if isinstance(num, float):
        return psCharStrings.encodeFloat(num)
    else:
        return psCharStrings.encodeIntCFF(num)


class TopDictCompiler(DictCompiler):
    opcodes = buildOpcodeDict(topDictOperators)

    def getChildren(self, strings):
        isCFF2 = self.isCFF2
        children = []
        if self.dictObj.cff2GetGlyphOrder is None:
            if hasattr(self.dictObj, "charset") and self.dictObj.charset:
                if hasattr(self.dictObj, "ROS"):  # aka isCID
                    charsetCode = None
                else:
                    charsetCode = getStdCharSet(self.dictObj.charset)
                if charsetCode is None:
                    children.append(
                        CharsetCompiler(strings, self.dictObj.charset, self)
                    )
                else:
                    self.rawDict["charset"] = charsetCode
            if hasattr(self.dictObj, "Encoding") and self.dictObj.Encoding:
                encoding = self.dictObj.Encoding
                if not isinstance(encoding, str):
                    children.append(EncodingCompiler(strings, encoding, self))
        else:
            if hasattr(self.dictObj, "VarStore"):
                varStoreData = self.dictObj.VarStore
                varStoreComp = VarStoreCompiler(varStoreData, self)
                children.append(varStoreComp)
        if hasattr(self.dictObj, "FDSelect"):
            # I have not yet supported merging a ttx CFF-CID font, as there are
            # interesting issues about merging the FDArrays. Here I assume that
            # either the font was read from XML, and the FDSelect indices are all
            # in the charstring data, or the FDSelect array is already fully defined.
            fdSelect = self.dictObj.FDSelect
            # probably read in from XML; assume fdIndex in CharString data
            if len(fdSelect) == 0:
                charStrings = self.dictObj.CharStrings
                for name in self.dictObj.charset:
                    fdSelect.append(charStrings[name].fdSelectIndex)
            fdSelectComp = FDSelectCompiler(fdSelect, self)
            children.append(fdSelectComp)
        if hasattr(self.dictObj, "CharStrings"):
            items = []
            charStrings = self.dictObj.CharStrings
            for name in self.dictObj.charset:
                items.append(charStrings[name])
            charStringsComp = CharStringsCompiler(items, strings, self, isCFF2=isCFF2)
            children.append(charStringsComp)
        if hasattr(self.dictObj, "FDArray"):
            # I have not yet supported merging a ttx CFF-CID font, as there are
            # interesting issues about merging the FDArrays. Here I assume that the
            # FDArray info is correct and complete.
            fdArrayIndexComp = self.dictObj.FDArray.getCompiler(strings, self)
            children.append(fdArrayIndexComp)
            children.extend(fdArrayIndexComp.getChildren(strings))
        if hasattr(self.dictObj, "Private"):
            privComp = self.dictObj.Private.getCompiler(strings, self)
            children.append(privComp)
            children.extend(privComp.getChildren(strings))
        return children


class FontDictCompiler(DictCompiler):
    opcodes = buildOpcodeDict(topDictOperators)

    def __init__(self, dictObj, strings, parent, isCFF2=None):
        super(FontDictCompiler, self).__init__(dictObj, strings, parent, isCFF2=isCFF2)
        #
        # We now take some effort to detect if there were any key/value pairs
        # supplied that were ignored in the FontDict context, and issue a warning
        # for those cases.
        #
        ignoredNames = []
        dictObj = self.dictObj
        for name in sorted(set(dictObj.converters) - set(dictObj.order)):
            if name in dictObj.rawDict:
                # The font was directly read from binary. In this
                # case, we want to report *all* "useless" key/value
                # pairs that are in the font, not just the ones that
                # are different from the default.
                ignoredNames.append(name)
            else:
                # The font was probably read from a TTX file. We only
                # warn about keys whos value is not the default. The
                # ones that have the default value will not be written
                # to binary anyway.
                default = dictObj.defaults.get(name)
                if default is not None:
                    conv = dictObj.converters[name]
                    default = conv.read(dictObj, default)
                if getattr(dictObj, name, None) != default:
                    ignoredNames.append(name)
        if ignoredNames:
            log.warning(
                "Some CFF FDArray/FontDict keys were ignored upon compile: "
                + " ".join(sorted(ignoredNames))
            )

    def getChildren(self, strings):
        children = []
        if hasattr(self.dictObj, "Private"):
            privComp = self.dictObj.Private.getCompiler(strings, self)
            children.append(privComp)
            children.extend(privComp.getChildren(strings))
        return children


class PrivateDictCompiler(DictCompiler):
    maxBlendStack = maxStackLimit
    opcodes = buildOpcodeDict(privateDictOperators)

    def setPos(self, pos, endPos):
        size = endPos - pos
        self.parent.rawDict["Private"] = size, pos
        self.pos = pos

    def getChildren(self, strings):
        children = []
        if hasattr(self.dictObj, "Subrs"):
            children.append(self.dictObj.Subrs.getCompiler(strings, self))
        return children


class BaseDict(object):
    def __init__(self, strings=None, file=None, offset=None, isCFF2=None):
        assert (isCFF2 is None) == (file is None)
        self.rawDict = {}
        self.skipNames = []
        self.strings = strings
        if file is None:
            return
        self._isCFF2 = isCFF2
        self.file = file
        if offset is not None:
            log.log(DEBUG, "loading %s at %s", self.__class__.__name__, offset)
            self.offset = offset

    def decompile(self, data):
        log.log(DEBUG, "    length %s is %d", self.__class__.__name__, len(data))
        dec = self.decompilerClass(self.strings, self)
        dec.decompile(data)
        self.rawDict = dec.getDict()
        self.postDecompile()

    def postDecompile(self):
        pass

    def getCompiler(self, strings, parent, isCFF2=None):
        return self.compilerClass(self, strings, parent, isCFF2=isCFF2)

    def __getattr__(self, name):
        if name[:2] == name[-2:] == "__":
            # to make deepcopy() and pickle.load() work, we need to signal with
            # AttributeError that dunder methods like '__deepcopy__' or '__getstate__'
            # aren't implemented. For more details, see:
            # https://github.com/fonttools/fonttools/pull/1488
            raise AttributeError(name)
        value = self.rawDict.get(name, None)
        if value is None:
            value = self.defaults.get(name)
        if value is None:
            raise AttributeError(name)
        conv = self.converters[name]
        value = conv.read(self, value)
        setattr(self, name, value)
        return value

    def toXML(self, xmlWriter):
        for name in self.order:
            if name in self.skipNames:
                continue
            value = getattr(self, name, None)
            # XXX For "charset" we never skip calling xmlWrite even if the
            # value is None, so we always write the following XML comment:
            #
            # <!-- charset is dumped separately as the 'GlyphOrder' element -->
            #
            # Charset is None when 'CFF ' table is imported from XML into an
            # empty TTFont(). By writing this comment all the time, we obtain
            # the same XML output whether roundtripping XML-to-XML or
            # dumping binary-to-XML
            if value is None and name != "charset":
                continue
            conv = self.converters[name]
            conv.xmlWrite(xmlWriter, name, value)
        ignoredNames = set(self.rawDict) - set(self.order)
        if ignoredNames:
            xmlWriter.comment(
                "some keys were ignored: %s" % " ".join(sorted(ignoredNames))
            )
            xmlWriter.newline()

    def fromXML(self, name, attrs, content):
        conv = self.converters[name]
        value = conv.xmlRead(name, attrs, content, self)
        setattr(self, name, value)


class TopDict(BaseDict):
    """The ``TopDict`` represents the top-level dictionary holding font
    information. CFF2 tables contain a restricted set of top-level entries
    as described `here <https://docs.microsoft.com/en-us/typography/opentype/spec/cff2#7-top-dict-data>`_,
    but CFF tables may contain a wider range of information. This information
    can be accessed through attributes or through the dictionary returned
    through the ``rawDict`` property:

    .. code:: python

            font = tt["CFF "].cff[0]
            font.FamilyName
            # 'Linux Libertine O'
            font.rawDict["FamilyName"]
            # 'Linux Libertine O'

    More information is available in the CFF file's private dictionary, accessed
    via the ``Private`` property:

    .. code:: python

            tt["CFF "].cff[0].Private.BlueValues
            # [-15, 0, 515, 515, 666, 666]

    """

    defaults = buildDefaults(topDictOperators)
    converters = buildConverters(topDictOperators)
    compilerClass = TopDictCompiler
    order = buildOrder(topDictOperators)
    decompilerClass = TopDictDecompiler

    def __init__(
        self,
        strings=None,
        file=None,
        offset=None,
        GlobalSubrs=None,
        cff2GetGlyphOrder=None,
        isCFF2=None,
    ):
        super(TopDict, self).__init__(strings, file, offset, isCFF2=isCFF2)
        self.cff2GetGlyphOrder = cff2GetGlyphOrder
        self.GlobalSubrs = GlobalSubrs
        if isCFF2:
            self.defaults = buildDefaults(topDictOperators2)
            self.charset = cff2GetGlyphOrder()
            self.order = buildOrder(topDictOperators2)
        else:
            self.defaults = buildDefaults(topDictOperators)
            self.order = buildOrder(topDictOperators)

    def getGlyphOrder(self):
        """Returns a list of glyph names in the CFF font."""
        return self.charset

    def postDecompile(self):
        offset = self.rawDict.get("CharStrings")
        if offset is None:
            return
        # get the number of glyphs beforehand.
        self.file.seek(offset)
        if self._isCFF2:
            self.numGlyphs = readCard32(self.file)
        else:
            self.numGlyphs = readCard16(self.file)

    def toXML(self, xmlWriter):
        if hasattr(self, "CharStrings"):
            self.decompileAllCharStrings()
        if hasattr(self, "ROS"):
            self.skipNames = ["Encoding"]
        if not hasattr(self, "ROS") or not hasattr(self, "CharStrings"):
            # these values have default values, but I only want them to show up
            # in CID fonts.
            self.skipNames = [
                "CIDFontVersion",
                "CIDFontRevision",
                "CIDFontType",
                "CIDCount",
            ]
        BaseDict.toXML(self, xmlWriter)

    def decompileAllCharStrings(self):
        # Make sure that all the Private Dicts have been instantiated.
        for i, charString in enumerate(self.CharStrings.values()):
            try:
                charString.decompile()
            except:
                log.error("Error in charstring %s", i)
                raise

    def recalcFontBBox(self):
        fontBBox = None
        for charString in self.CharStrings.values():
            bounds = charString.calcBounds(self.CharStrings)
            if bounds is not None:
                if fontBBox is not None:
                    fontBBox = unionRect(fontBBox, bounds)
                else:
                    fontBBox = bounds

        if fontBBox is None:
            self.FontBBox = self.defaults["FontBBox"][:]
        else:
            self.FontBBox = list(intRect(fontBBox))


class FontDict(BaseDict):
    #
    # Since fonttools used to pass a lot of fields that are not relevant in the FDArray
    # FontDict, there are 'ttx' files in the wild that contain all these. These got in
    # the ttx files because fonttools writes explicit values for all the TopDict default
    # values. These are not actually illegal in the context of an FDArray FontDict - you
    # can legally, per spec, put any arbitrary key/value pair in a FontDict - but are
    # useless since current major company CFF interpreters ignore anything but the set
    # listed in this file. So, we just silently skip them. An exception is Weight: this
    # is not used by any interpreter, but some foundries have asked that this be
    # supported in FDArray FontDicts just to preserve information about the design when
    # the font is being inspected.
    #
    # On top of that, there are fonts out there that contain such useless FontDict values.
    #
    # By subclassing TopDict, we *allow* all key/values from TopDict, both when reading
    # from binary or when reading from XML, but by overriding `order` with a limited
    # list of names, we ensure that only the useful names ever get exported to XML and
    # ever get compiled into the binary font.
    #
    # We override compilerClass so we can warn about "useless" key/value pairs, either
    # from the original binary font or from TTX input.
    #
    # See:
    # - https://github.com/fonttools/fonttools/issues/740
    # - https://github.com/fonttools/fonttools/issues/601
    # - https://github.com/adobe-type-tools/afdko/issues/137
    #
    defaults = {}
    converters = buildConverters(topDictOperators)
    compilerClass = FontDictCompiler
    orderCFF = ["FontName", "FontMatrix", "Weight", "Private"]
    orderCFF2 = ["Private"]
    decompilerClass = TopDictDecompiler

    def __init__(
        self,
        strings=None,
        file=None,
        offset=None,
        GlobalSubrs=None,
        isCFF2=None,
        vstore=None,
    ):
        super(FontDict, self).__init__(strings, file, offset, isCFF2=isCFF2)
        self.vstore = vstore
        self.setCFF2(isCFF2)

    def setCFF2(self, isCFF2):
        # isCFF2 may be None.
        if isCFF2:
            self.order = self.orderCFF2
            self._isCFF2 = True
        else:
            self.order = self.orderCFF
            self._isCFF2 = False


class PrivateDict(BaseDict):
    defaults = buildDefaults(privateDictOperators)
    converters = buildConverters(privateDictOperators)
    order = buildOrder(privateDictOperators)
    decompilerClass = PrivateDictDecompiler
    compilerClass = PrivateDictCompiler

    def __init__(self, strings=None, file=None, offset=None, isCFF2=None, vstore=None):
        super(PrivateDict, self).__init__(strings, file, offset, isCFF2=isCFF2)
        self.vstore = vstore
        if isCFF2:
            self.defaults = buildDefaults(privateDictOperators2)
            self.order = buildOrder(privateDictOperators2)
            # Provide dummy values. This avoids needing to provide
            # an isCFF2 state in a lot of places.
            self.nominalWidthX = self.defaultWidthX = None
            self._isCFF2 = True
        else:
            self.defaults = buildDefaults(privateDictOperators)
            self.order = buildOrder(privateDictOperators)
            self._isCFF2 = False

    @property
    def in_cff2(self):
        return self._isCFF2

    def getNumRegions(self, vi=None):  # called from misc/psCharStrings.py
        # if getNumRegions is being called, we can assume that VarStore exists.
        if vi is None:
            if hasattr(self, "vsindex"):
                vi = self.vsindex
            else:
                vi = 0
        numRegions = self.vstore.getNumRegions(vi)
        return numRegions


class IndexedStrings(object):
    """SID -> string mapping."""

    def __init__(self, file=None):
        if file is None:
            strings = []
        else:
            strings = [tostr(s, encoding="latin1") for s in Index(file, isCFF2=False)]
        self.strings = strings

    def getCompiler(self):
        return IndexedStringsCompiler(self, None, self, isCFF2=False)

    def __len__(self):
        return len(self.strings)

    def __getitem__(self, SID):
        if SID < cffStandardStringCount:
            return cffStandardStrings[SID]
        else:
            return self.strings[SID - cffStandardStringCount]

    def getSID(self, s):
        if not hasattr(self, "stringMapping"):
            self.buildStringMapping()
        s = tostr(s, encoding="latin1")
        if s in cffStandardStringMapping:
            SID = cffStandardStringMapping[s]
        elif s in self.stringMapping:
            SID = self.stringMapping[s]
        else:
            SID = len(self.strings) + cffStandardStringCount
            self.strings.append(s)
            self.stringMapping[s] = SID
        return SID

    def getStrings(self):
        return self.strings

    def buildStringMapping(self):
        self.stringMapping = {}
        for index in range(len(self.strings)):
            self.stringMapping[self.strings[index]] = index + cffStandardStringCount


# The 391 Standard Strings as used in the CFF format.
# from Adobe Technical None #5176, version 1.0, 18 March 1998

cffStandardStrings = [
    ".notdef",
    "space",
    "exclam",
    "quotedbl",
    "numbersign",
    "dollar",
    "percent",
    "ampersand",
    "quoteright",
    "parenleft",
    "parenright",
    "asterisk",
    "plus",
    "comma",
    "hyphen",
    "period",
    "slash",
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "colon",
    "semicolon",
    "less",
    "equal",
    "greater",
    "question",
    "at",
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "H",
    "I",
    "J",
    "K",
    "L",
    "M",
    "N",
    "O",
    "P",
    "Q",
    "R",
    "S",
    "T",
    "U",
    "V",
    "W",
    "X",
    "Y",
    "Z",
    "bracketleft",
    "backslash",
    "bracketright",
    "asciicircum",
    "underscore",
    "quoteleft",
    "a",
    "b",
    "c",
    "d",
    "e",
    "f",
    "g",
    "h",
    "i",
    "j",
    "k",
    "l",
    "m",
    "n",
    "o",
    "p",
    "q",
    "r",
    "s",
    "t",
    "u",
    "v",
    "w",
    "x",
    "y",
    "z",
    "braceleft",
    "bar",
    "braceright",
    "asciitilde",
    "exclamdown",
    "cent",
    "sterling",
    "fraction",
    "yen",
    "florin",
    "section",
    "currency",
    "quotesingle",
    "quotedblleft",
    "guillemotleft",
    "guilsinglleft",
    "guilsinglright",
    "fi",
    "fl",
    "endash",
    "dagger",
    "daggerdbl",
    "periodcentered",
    "paragraph",
    "bullet",
    "quotesinglbase",
    "quotedblbase",
    "quotedblright",
    "guillemotright",
    "ellipsis",
    "perthousand",
    "questiondown",
    "grave",
    "acute",
    "circumflex",
    "tilde",
    "macron",
    "breve",
    "dotaccent",
    "dieresis",
    "ring",
    "cedilla",
    "hungarumlaut",
    "ogonek",
    "caron",
    "emdash",
    "AE",
    "ordfeminine",
    "Lslash",
    "Oslash",
    "OE",
    "ordmasculine",
    "ae",
    "dotlessi",
    "lslash",
    "oslash",
    "oe",
    "germandbls",
    "onesuperior",
    "logicalnot",
    "mu",
    "trademark",
    "Eth",
    "onehalf",
    "plusminus",
    "Thorn",
    "onequarter",
    "divide",
    "brokenbar",
    "degree",
    "thorn",
    "threequarters",
    "twosuperior",
    "registered",
    "minus",
    "eth",
    "multiply",
    "threesuperior",
    "copyright",
    "Aacute",
    "Acircumflex",
    "Adieresis",
    "Agrave",
    "Aring",
    "Atilde",
    "Ccedilla",
    "Eacute",
    "Ecircumflex",
    "Edieresis",
    "Egrave",
    "Iacute",
    "Icircumflex",
    "Idieresis",
    "Igrave",
    "Ntilde",
    "Oacute",
    "Ocircumflex",
    "Odieresis",
    "Ograve",
    "Otilde",
    "Scaron",
    "Uacute",
    "Ucircumflex",
    "Udieresis",
    "Ugrave",
    "Yacute",
    "Ydieresis",
    "Zcaron",
    "aacute",
    "acircumflex",
    "adieresis",
    "agrave",
    "aring",
    "atilde",
    "ccedilla",
    "eacute",
    "ecircumflex",
    "edieresis",
    "egrave",
    "iacute",
    "icircumflex",
    "idieresis",
    "igrave",
    "ntilde",
    "oacute",
    "ocircumflex",
    "odieresis",
    "ograve",
    "otilde",
    "scaron",
    "uacute",
    "ucircumflex",
    "udieresis",
    "ugrave",
    "yacute",
    "ydieresis",
    "zcaron",
    "exclamsmall",
    "Hungarumlautsmall",
    "dollaroldstyle",
    "dollarsuperior",
    "ampersandsmall",
    "Acutesmall",
    "parenleftsuperior",
    "parenrightsuperior",
    "twodotenleader",
    "onedotenleader",
    "zerooldstyle",
    "oneoldstyle",
    "twooldstyle",
    "threeoldstyle",
    "fouroldstyle",
    "fiveoldstyle",
    "sixoldstyle",
    "sevenoldstyle",
    "eightoldstyle",
    "nineoldstyle",
    "commasuperior",
    "threequartersemdash",
    "periodsuperior",
    "questionsmall",
    "asuperior",
    "bsuperior",
    "centsuperior",
    "dsuperior",
    "esuperior",
    "isuperior",
    "lsuperior",
    "msuperior",
    "nsuperior",
    "osuperior",
    "rsuperior",
    "ssuperior",
    "tsuperior",
    "ff",
    "ffi",
    "ffl",
    "parenleftinferior",
    "parenrightinferior",
    "Circumflexsmall",
    "hyphensuperior",
    "Gravesmall",
    "Asmall",
    "Bsmall",
    "Csmall",
    "Dsmall",
    "Esmall",
    "Fsmall",
    "Gsmall",
    "Hsmall",
    "Ismall",
    "Jsmall",
    "Ksmall",
    "Lsmall",
    "Msmall",
    "Nsmall",
    "Osmall",
    "Psmall",
    "Qsmall",
    "Rsmall",
    "Ssmall",
    "Tsmall",
    "Usmall",
    "Vsmall",
    "Wsmall",
    "Xsmall",
    "Ysmall",
    "Zsmall",
    "colonmonetary",
    "onefitted",
    "rupiah",
    "Tildesmall",
    "exclamdownsmall",
    "centoldstyle",
    "Lslashsmall",
    "Scaronsmall",
    "Zcaronsmall",
    "Dieresissmall",
    "Brevesmall",
    "Caronsmall",
    "Dotaccentsmall",
    "Macronsmall",
    "figuredash",
    "hypheninferior",
    "Ogoneksmall",
    "Ringsmall",
    "Cedillasmall",
    "questiondownsmall",
    "oneeighth",
    "threeeighths",
    "fiveeighths",
    "seveneighths",
    "onethird",
    "twothirds",
    "zerosuperior",
    "foursuperior",
    "fivesuperior",
    "sixsuperior",
    "sevensuperior",
    "eightsuperior",
    "ninesuperior",
    "zeroinferior",
    "oneinferior",
    "twoinferior",
    "threeinferior",
    "fourinferior",
    "fiveinferior",
    "sixinferior",
    "seveninferior",
    "eightinferior",
    "nineinferior",
    "centinferior",
    "dollarinferior",
    "periodinferior",
    "commainferior",
    "Agravesmall",
    "Aacutesmall",
    "Acircumflexsmall",
    "Atildesmall",
    "Adieresissmall",
    "Aringsmall",
    "AEsmall",
    "Ccedillasmall",
    "Egravesmall",
    "Eacutesmall",
    "Ecircumflexsmall",
    "Edieresissmall",
    "Igravesmall",
    "Iacutesmall",
    "Icircumflexsmall",
    "Idieresissmall",
    "Ethsmall",
    "Ntildesmall",
    "Ogravesmall",
    "Oacutesmall",
    "Ocircumflexsmall",
    "Otildesmall",
    "Odieresissmall",
    "OEsmall",
    "Oslashsmall",
    "Ugravesmall",
    "Uacutesmall",
    "Ucircumflexsmall",
    "Udieresissmall",
    "Yacutesmall",
    "Thornsmall",
    "Ydieresissmall",
    "001.000",
    "001.001",
    "001.002",
    "001.003",
    "Black",
    "Bold",
    "Book",
    "Light",
    "Medium",
    "Regular",
    "Roman",
    "Semibold",
]

cffStandardStringCount = 391
assert len(cffStandardStrings) == cffStandardStringCount
# build reverse mapping
cffStandardStringMapping = {}
for _i in range(cffStandardStringCount):
    cffStandardStringMapping[cffStandardStrings[_i]] = _i

cffISOAdobeStrings = [
    ".notdef",
    "space",
    "exclam",
    "quotedbl",
    "numbersign",
    "dollar",
    "percent",
    "ampersand",
    "quoteright",
    "parenleft",
    "parenright",
    "asterisk",
    "plus",
    "comma",
    "hyphen",
    "period",
    "slash",
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "colon",
    "semicolon",
    "less",
    "equal",
    "greater",
    "question",
    "at",
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "H",
    "I",
    "J",
    "K",
    "L",
    "M",
    "N",
    "O",
    "P",
    "Q",
    "R",
    "S",
    "T",
    "U",
    "V",
    "W",
    "X",
    "Y",
    "Z",
    "bracketleft",
    "backslash",
    "bracketright",
    "asciicircum",
    "underscore",
    "quoteleft",
    "a",
    "b",
    "c",
    "d",
    "e",
    "f",
    "g",
    "h",
    "i",
    "j",
    "k",
    "l",
    "m",
    "n",
    "o",
    "p",
    "q",
    "r",
    "s",
    "t",
    "u",
    "v",
    "w",
    "x",
    "y",
    "z",
    "braceleft",
    "bar",
    "braceright",
    "asciitilde",
    "exclamdown",
    "cent",
    "sterling",
    "fraction",
    "yen",
    "florin",
    "section",
    "currency",
    "quotesingle",
    "quotedblleft",
    "guillemotleft",
    "guilsinglleft",
    "guilsinglright",
    "fi",
    "fl",
    "endash",
    "dagger",
    "daggerdbl",
    "periodcentered",
    "paragraph",
    "bullet",
    "quotesinglbase",
    "quotedblbase",
    "quotedblright",
    "guillemotright",
    "ellipsis",
    "perthousand",
    "questiondown",
    "grave",
    "acute",
    "circumflex",
    "tilde",
    "macron",
    "breve",
    "dotaccent",
    "dieresis",
    "ring",
    "cedilla",
    "hungarumlaut",
    "ogonek",
    "caron",
    "emdash",
    "AE",
    "ordfeminine",
    "Lslash",
    "Oslash",
    "OE",
    "ordmasculine",
    "ae",
    "dotlessi",
    "lslash",
    "oslash",
    "oe",
    "germandbls",
    "onesuperior",
    "logicalnot",
    "mu",
    "trademark",
    "Eth",
    "onehalf",
    "plusminus",
    "Thorn",
    "onequarter",
    "divide",
    "brokenbar",
    "degree",
    "thorn",
    "threequarters",
    "twosuperior",
    "registered",
    "minus",
    "eth",
    "multiply",
    "threesuperior",
    "copyright",
    "Aacute",
    "Acircumflex",
    "Adieresis",
    "Agrave",
    "Aring",
    "Atilde",
    "Ccedilla",
    "Eacute",
    "Ecircumflex",
    "Edieresis",
    "Egrave",
    "Iacute",
    "Icircumflex",
    "Idieresis",
    "Igrave",
    "Ntilde",
    "Oacute",
    "Ocircumflex",
    "Odieresis",
    "Ograve",
    "Otilde",
    "Scaron",
    "Uacute",
    "Ucircumflex",
    "Udieresis",
    "Ugrave",
    "Yacute",
    "Ydieresis",
    "Zcaron",
    "aacute",
    "acircumflex",
    "adieresis",
    "agrave",
    "aring",
    "atilde",
    "ccedilla",
    "eacute",
    "ecircumflex",
    "edieresis",
    "egrave",
    "iacute",
    "icircumflex",
    "idieresis",
    "igrave",
    "ntilde",
    "oacute",
    "ocircumflex",
    "odieresis",
    "ograve",
    "otilde",
    "scaron",
    "uacute",
    "ucircumflex",
    "udieresis",
    "ugrave",
    "yacute",
    "ydieresis",
    "zcaron",
]

cffISOAdobeStringCount = 229
assert len(cffISOAdobeStrings) == cffISOAdobeStringCount

cffIExpertStrings = [
    ".notdef",
    "space",
    "exclamsmall",
    "Hungarumlautsmall",
    "dollaroldstyle",
    "dollarsuperior",
    "ampersandsmall",
    "Acutesmall",
    "parenleftsuperior",
    "parenrightsuperior",
    "twodotenleader",
    "onedotenleader",
    "comma",
    "hyphen",
    "period",
    "fraction",
    "zerooldstyle",
    "oneoldstyle",
    "twooldstyle",
    "threeoldstyle",
    "fouroldstyle",
    "fiveoldstyle",
    "sixoldstyle",
    "sevenoldstyle",
    "eightoldstyle",
    "nineoldstyle",
    "colon",
    "semicolon",
    "commasuperior",
    "threequartersemdash",
    "periodsuperior",
    "questionsmall",
    "asuperior",
    "bsuperior",
    "centsuperior",
    "dsuperior",
    "esuperior",
    "isuperior",
    "lsuperior",
    "msuperior",
    "nsuperior",
    "osuperior",
    "rsuperior",
    "ssuperior",
    "tsuperior",
    "ff",
    "fi",
    "fl",
    "ffi",
    "ffl",
    "parenleftinferior",
    "parenrightinferior",
    "Circumflexsmall",
    "hyphensuperior",
    "Gravesmall",
    "Asmall",
    "Bsmall",
    "Csmall",
    "Dsmall",
    "Esmall",
    "Fsmall",
    "Gsmall",
    "Hsmall",
    "Ismall",
    "Jsmall",
    "Ksmall",
    "Lsmall",
    "Msmall",
    "Nsmall",
    "Osmall",
    "Psmall",
    "Qsmall",
    "Rsmall",
    "Ssmall",
    "Tsmall",
    "Usmall",
    "Vsmall",
    "Wsmall",
    "Xsmall",
    "Ysmall",
    "Zsmall",
    "colonmonetary",
    "onefitted",
    "rupiah",
    "Tildesmall",
    "exclamdownsmall",
    "centoldstyle",
    "Lslashsmall",
    "Scaronsmall",
    "Zcaronsmall",
    "Dieresissmall",
    "Brevesmall",
    "Caronsmall",
    "Dotaccentsmall",
    "Macronsmall",
    "figuredash",
    "hypheninferior",
    "Ogoneksmall",
    "Ringsmall",
    "Cedillasmall",
    "onequarter",
    "onehalf",
    "threequarters",
    "questiondownsmall",
    "oneeighth",
    "threeeighths",
    "fiveeighths",
    "seveneighths",
    "onethird",
    "twothirds",
    "zerosuperior",
    "onesuperior",
    "twosuperior",
    "threesuperior",
    "foursuperior",
    "fivesuperior",
    "sixsuperior",
    "sevensuperior",
    "eightsuperior",
    "ninesuperior",
    "zeroinferior",
    "oneinferior",
    "twoinferior",
    "threeinferior",
    "fourinferior",
    "fiveinferior",
    "sixinferior",
    "seveninferior",
    "eightinferior",
    "nineinferior",
    "centinferior",
    "dollarinferior",
    "periodinferior",
    "commainferior",
    "Agravesmall",
    "Aacutesmall",
    "Acircumflexsmall",
    "Atildesmall",
    "Adieresissmall",
    "Aringsmall",
    "AEsmall",
    "Ccedillasmall",
    "Egravesmall",
    "Eacutesmall",
    "Ecircumflexsmall",
    "Edieresissmall",
    "Igravesmall",
    "Iacutesmall",
    "Icircumflexsmall",
    "Idieresissmall",
    "Ethsmall",
    "Ntildesmall",
    "Ogravesmall",
    "Oacutesmall",
    "Ocircumflexsmall",
    "Otildesmall",
    "Odieresissmall",
    "OEsmall",
    "Oslashsmall",
    "Ugravesmall",
    "Uacutesmall",
    "Ucircumflexsmall",
    "Udieresissmall",
    "Yacutesmall",
    "Thornsmall",
    "Ydieresissmall",
]

cffExpertStringCount = 166
assert len(cffIExpertStrings) == cffExpertStringCount

cffExpertSubsetStrings = [
    ".notdef",
    "space",
    "dollaroldstyle",
    "dollarsuperior",
    "parenleftsuperior",
    "parenrightsuperior",
    "twodotenleader",
    "onedotenleader",
    "comma",
    "hyphen",
    "period",
    "fraction",
    "zerooldstyle",
    "oneoldstyle",
    "twooldstyle",
    "threeoldstyle",
    "fouroldstyle",
    "fiveoldstyle",
    "sixoldstyle",
    "sevenoldstyle",
    "eightoldstyle",
    "nineoldstyle",
    "colon",
    "semicolon",
    "commasuperior",
    "threequartersemdash",
    "periodsuperior",
    "asuperior",
    "bsuperior",
    "centsuperior",
    "dsuperior",
    "esuperior",
    "isuperior",
    "lsuperior",
    "msuperior",
    "nsuperior",
    "osuperior",
    "rsuperior",
    "ssuperior",
    "tsuperior",
    "ff",
    "fi",
    "fl",
    "ffi",
    "ffl",
    "parenleftinferior",
    "parenrightinferior",
    "hyphensuperior",
    "colonmonetary",
    "onefitted",
    "rupiah",
    "centoldstyle",
    "figuredash",
    "hypheninferior",
    "onequarter",
    "onehalf",
    "threequarters",
    "oneeighth",
    "threeeighths",
    "fiveeighths",
    "seveneighths",
    "onethird",
    "twothirds",
    "zerosuperior",
    "onesuperior",
    "twosuperior",
    "threesuperior",
    "foursuperior",
    "fivesuperior",
    "sixsuperior",
    "sevensuperior",
    "eightsuperior",
    "ninesuperior",
    "zeroinferior",
    "oneinferior",
    "twoinferior",
    "threeinferior",
    "fourinferior",
    "fiveinferior",
    "sixinferior",
    "seveninferior",
    "eightinferior",
    "nineinferior",
    "centinferior",
    "dollarinferior",
    "periodinferior",
    "commainferior",
]

cffExpertSubsetStringCount = 87
assert len(cffExpertSubsetStrings) == cffExpertSubsetStringCount
