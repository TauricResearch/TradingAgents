from fontTools.misc.textTools import bytesjoin, safeEval, readHex
from fontTools.misc.encodingTools import getEncoding
from fontTools.ttLib import getSearchRange
from fontTools.unicode import Unicode
from . import DefaultTable
import sys
import struct
import array
import logging


log = logging.getLogger(__name__)


def _make_map(font, chars, gids):
    assert len(chars) == len(gids)
    glyphNames = font.getGlyphNameMany(gids)
    cmap = {}
    for char, gid, name in zip(chars, gids, glyphNames):
        if gid == 0:
            continue
        cmap[char] = name
    return cmap


class table__c_m_a_p(DefaultTable.DefaultTable):
    """Character to Glyph Index Mapping Table

    This class represents the `cmap <https://docs.microsoft.com/en-us/typography/opentype/spec/cmap>`_
    table, which maps between input characters (in Unicode or other system encodings)
    and glyphs within the font. The ``cmap`` table contains one or more subtables
    which determine the mapping of of characters to glyphs across different platforms
    and encoding systems.

    ``table__c_m_a_p`` objects expose an accessor ``.tables`` which provides access
    to the subtables, although it is normally easier to retrieve individual subtables
    through the utility methods described below. To add new subtables to a font,
    first determine the subtable format (if in doubt use format 4 for glyphs within
    the BMP, format 12 for glyphs outside the BMP, and format 14 for Unicode Variation
    Sequences) construct subtable objects with ``CmapSubtable.newSubtable(format)``,
    and append them to the ``.tables`` list.

    Within a subtable, the mapping of characters to glyphs is provided by the ``.cmap``
    attribute.

    Example::

            cmap4_0_3 = CmapSubtable.newSubtable(4)
            cmap4_0_3.platformID = 0
            cmap4_0_3.platEncID = 3
            cmap4_0_3.language = 0
            cmap4_0_3.cmap = { 0xC1: "Aacute" }

            cmap = newTable("cmap")
            cmap.tableVersion = 0
            cmap.tables = [cmap4_0_3]

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/cmap
    """

    def getcmap(self, platformID, platEncID):
        """Returns the first subtable which matches the given platform and encoding.

        Args:
                platformID (int): The platform ID. Use 0 for Unicode, 1 for Macintosh
                        (deprecated for new fonts), 2 for ISO (deprecated) and 3 for Windows.
                encodingID (int): Encoding ID. Interpretation depends on the platform ID.
                        See the OpenType specification for details.

        Returns:
                An object which is a subclass of :py:class:`CmapSubtable` if a matching
                subtable is found within the font, or ``None`` otherwise.
        """

        for subtable in self.tables:
            if subtable.platformID == platformID and subtable.platEncID == platEncID:
                return subtable
        return None  # not found

    def getBestCmap(
        self,
        cmapPreferences=(
            (3, 10),
            (0, 6),
            (0, 4),
            (3, 1),
            (0, 3),
            (0, 2),
            (0, 1),
            (0, 0),
        ),
    ):
        """Returns the 'best' Unicode cmap dictionary available in the font
        or ``None``, if no Unicode cmap subtable is available.

        By default it will search for the following (platformID, platEncID)
        pairs in order::

                        (3, 10), # Windows Unicode full repertoire
                        (0, 6),  # Unicode full repertoire (format 13 subtable)
                        (0, 4),  # Unicode 2.0 full repertoire
                        (3, 1),  # Windows Unicode BMP
                        (0, 3),  # Unicode 2.0 BMP
                        (0, 2),  # Unicode ISO/IEC 10646
                        (0, 1),  # Unicode 1.1
                        (0, 0)   # Unicode 1.0

        This particular order matches what HarfBuzz uses to choose what
        subtable to use by default. This order prefers the largest-repertoire
        subtable, and among those, prefers the Windows-platform over the
        Unicode-platform as the former has wider support.

        This order can be customized via the ``cmapPreferences`` argument.
        """
        for platformID, platEncID in cmapPreferences:
            cmapSubtable = self.getcmap(platformID, platEncID)
            if cmapSubtable is not None:
                return cmapSubtable.cmap
        return None  # None of the requested cmap subtables were found

    def buildReversed(self):
        """Builds a reverse mapping dictionary

        Iterates over all Unicode cmap tables and returns a dictionary mapping
        glyphs to sets of codepoints, such as::

                {
                        'one': {0x31}
                        'A': {0x41,0x391}
                }

        The values are sets of Unicode codepoints because
        some fonts map different codepoints to the same glyph.
        For example, ``U+0041 LATIN CAPITAL LETTER A`` and ``U+0391
        GREEK CAPITAL LETTER ALPHA`` are sometimes the same glyph.
        """
        result = {}
        for subtable in self.tables:
            if subtable.isUnicode():
                for codepoint, name in subtable.cmap.items():
                    result.setdefault(name, set()).add(codepoint)
        return result

    def buildReversedMin(self):
        result = {}
        for subtable in self.tables:
            if subtable.isUnicode():
                for codepoint, name in subtable.cmap.items():
                    if name in result:
                        result[name] = min(result[name], codepoint)
                    else:
                        result[name] = codepoint
        return result

    def decompile(self, data, ttFont):
        tableVersion, numSubTables = struct.unpack(">HH", data[:4])
        self.tableVersion = int(tableVersion)
        self.tables = tables = []
        seenOffsets = {}
        for i in range(numSubTables):
            platformID, platEncID, offset = struct.unpack(
                ">HHl", data[4 + i * 8 : 4 + (i + 1) * 8]
            )
            platformID, platEncID = int(platformID), int(platEncID)
            format, length = struct.unpack(">HH", data[offset : offset + 4])
            if format in [8, 10, 12, 13]:
                format, reserved, length = struct.unpack(
                    ">HHL", data[offset : offset + 8]
                )
            elif format in [14]:
                format, length = struct.unpack(">HL", data[offset : offset + 6])

            if not length:
                log.error(
                    "cmap subtable is reported as having zero length: platformID %s, "
                    "platEncID %s, format %s offset %s. Skipping table.",
                    platformID,
                    platEncID,
                    format,
                    offset,
                )
                continue
            table = CmapSubtable.newSubtable(format)
            table.platformID = platformID
            table.platEncID = platEncID
            # Note that by default we decompile only the subtable header info;
            # any other data gets decompiled only when an attribute of the
            # subtable is referenced.
            table.decompileHeader(data[offset : offset + int(length)], ttFont)
            if offset in seenOffsets:
                table.data = None  # Mark as decompiled
                table.cmap = tables[seenOffsets[offset]].cmap
            else:
                seenOffsets[offset] = i
            tables.append(table)
        if ttFont.lazy is False:  # Be lazy for None and True
            self.ensureDecompiled()

    def ensureDecompiled(self, recurse=False):
        # The recurse argument is unused, but part of the signature of
        # ensureDecompiled across the library.
        for st in self.tables:
            st.ensureDecompiled()

    def compile(self, ttFont):
        self.tables.sort()  # sort according to the spec; see CmapSubtable.__lt__()
        numSubTables = len(self.tables)
        totalOffset = 4 + 8 * numSubTables
        data = struct.pack(">HH", self.tableVersion, numSubTables)
        tableData = b""
        seen = (
            {}
        )  # Some tables are the same object reference. Don't compile them twice.
        done = (
            {}
        )  # Some tables are different objects, but compile to the same data chunk
        for table in self.tables:
            offset = seen.get(id(table.cmap))
            if offset is None:
                chunk = table.compile(ttFont)
                offset = done.get(chunk)
                if offset is None:
                    offset = seen[id(table.cmap)] = done[chunk] = totalOffset + len(
                        tableData
                    )
                    tableData = tableData + chunk
            data = data + struct.pack(">HHl", table.platformID, table.platEncID, offset)
        return data + tableData

    def toXML(self, writer, ttFont):
        writer.simpletag("tableVersion", version=self.tableVersion)
        writer.newline()
        for table in self.tables:
            table.toXML(writer, ttFont)

    def fromXML(self, name, attrs, content, ttFont):
        if name == "tableVersion":
            self.tableVersion = safeEval(attrs["version"])
            return
        if name[:12] != "cmap_format_":
            return
        if not hasattr(self, "tables"):
            self.tables = []
        format = safeEval(name[12:])
        table = CmapSubtable.newSubtable(format)
        table.platformID = safeEval(attrs["platformID"])
        table.platEncID = safeEval(attrs["platEncID"])
        table.fromXML(name, attrs, content, ttFont)
        self.tables.append(table)


class CmapSubtable(object):
    """Base class for all cmap subtable formats.

    Subclasses which handle the individual subtable formats are named
    ``cmap_format_0``, ``cmap_format_2`` etc. Use :py:meth:`getSubtableClass`
    to retrieve the concrete subclass, or :py:meth:`newSubtable` to get a
    new subtable object for a given format.

    The object exposes a ``.cmap`` attribute, which contains a dictionary mapping
    character codepoints to glyph names.
    """

    @staticmethod
    def getSubtableClass(format):
        """Return the subtable class for a format."""
        return cmap_classes.get(format, cmap_format_unknown)

    @staticmethod
    def newSubtable(format):
        """Return a new instance of a subtable for the given format
        ."""
        subtableClass = CmapSubtable.getSubtableClass(format)
        return subtableClass(format)

    def __init__(self, format):
        self.format = format
        self.data = None
        self.ttFont = None
        self.platformID = None  #: The platform ID of this subtable
        self.platEncID = None  #: The encoding ID of this subtable (interpretation depends on ``platformID``)
        self.language = (
            None  #: The language ID of this subtable (Macintosh platform only)
        )

    def ensureDecompiled(self, recurse=False):
        # The recurse argument is unused, but part of the signature of
        # ensureDecompiled across the library.
        if self.data is None:
            return
        self.decompile(None, None)  # use saved data.
        self.data = None  # Once this table has been decompiled, make sure we don't
        # just return the original data. Also avoids recursion when
        # called with an attribute that the cmap subtable doesn't have.

    def __getattr__(self, attr):
        # allow lazy decompilation of subtables.
        if attr[:2] == "__":  # don't handle requests for member functions like '__lt__'
            raise AttributeError(attr)
        if self.data is None:
            raise AttributeError(attr)
        self.ensureDecompiled()
        return getattr(self, attr)

    def decompileHeader(self, data, ttFont):
        format, length, language = struct.unpack(">HHH", data[:6])
        assert (
            len(data) == length
        ), "corrupt cmap table format %d (data length: %d, header length: %d)" % (
            format,
            len(data),
            length,
        )
        self.format = int(format)
        self.length = int(length)
        self.language = int(language)
        self.data = data[6:]
        self.ttFont = ttFont

    def toXML(self, writer, ttFont):
        writer.begintag(
            self.__class__.__name__,
            [
                ("platformID", self.platformID),
                ("platEncID", self.platEncID),
                ("language", self.language),
            ],
        )
        writer.newline()
        codes = sorted(self.cmap.items())
        self._writeCodes(codes, writer)
        writer.endtag(self.__class__.__name__)
        writer.newline()

    def getEncoding(self, default=None):
        """Returns the Python encoding name for this cmap subtable based on its platformID,
        platEncID, and language.  If encoding for these values is not known, by default
        ``None`` is returned.  That can be overridden by passing a value to the ``default``
        argument.

        Note that if you want to choose a "preferred" cmap subtable, most of the time
        ``self.isUnicode()`` is what you want as that one only returns true for the modern,
        commonly used, Unicode-compatible triplets, not the legacy ones.
        """
        return getEncoding(self.platformID, self.platEncID, self.language, default)

    def isUnicode(self):
        """Returns true if the characters are interpreted as Unicode codepoints."""
        return self.platformID == 0 or (
            self.platformID == 3 and self.platEncID in [0, 1, 10]
        )

    def isSymbol(self):
        """Returns true if the subtable is for the Symbol encoding (3,0)"""
        return self.platformID == 3 and self.platEncID == 0

    def _writeCodes(self, codes, writer):
        isUnicode = self.isUnicode()
        for code, name in codes:
            writer.simpletag("map", code=hex(code), name=name)
            if isUnicode:
                writer.comment(Unicode[code])
            writer.newline()

    def __lt__(self, other):
        if not isinstance(other, CmapSubtable):
            return NotImplemented

        # implemented so that list.sort() sorts according to the spec.
        selfTuple = (
            getattr(self, "platformID", None),
            getattr(self, "platEncID", None),
            getattr(self, "language", None),
            self.__dict__,
        )
        otherTuple = (
            getattr(other, "platformID", None),
            getattr(other, "platEncID", None),
            getattr(other, "language", None),
            other.__dict__,
        )
        return selfTuple < otherTuple


class cmap_format_0(CmapSubtable):
    def decompile(self, data, ttFont):
        # we usually get here indirectly from the subtable __getattr__ function, in which case both args must be None.
        # If not, someone is calling the subtable decompile() directly, and must provide both args.
        if data is not None and ttFont is not None:
            self.decompileHeader(data, ttFont)
        else:
            assert (
                data is None and ttFont is None
            ), "Need both data and ttFont arguments"
        data = (
            self.data
        )  # decompileHeader assigns the data after the header to self.data
        assert 262 == self.length, "Format 0 cmap subtable not 262 bytes"
        gids = array.array("B")
        gids.frombytes(self.data)
        charCodes = range(len(gids))
        self.cmap = _make_map(self.ttFont, charCodes, gids)

    def compile(self, ttFont):
        if self.data:
            return struct.pack(">HHH", 0, 262, self.language) + self.data

        cmap = self.cmap
        assert set(cmap.keys()).issubset(range(256))
        getGlyphID = ttFont.getGlyphID
        valueList = [getGlyphID(cmap[i]) if i in cmap else 0 for i in range(256)]

        gids = array.array("B", valueList)
        data = struct.pack(">HHH", 0, 262, self.language) + gids.tobytes()
        assert len(data) == 262
        return data

    def fromXML(self, name, attrs, content, ttFont):
        self.language = safeEval(attrs["language"])
        if not hasattr(self, "cmap"):
            self.cmap = {}
        cmap = self.cmap
        for element in content:
            if not isinstance(element, tuple):
                continue
            name, attrs, content = element
            if name != "map":
                continue
            cmap[safeEval(attrs["code"])] = attrs["name"]


subHeaderFormat = ">HHhH"


class SubHeader(object):
    def __init__(self):
        self.firstCode = None
        self.entryCount = None
        self.idDelta = None
        self.idRangeOffset = None
        self.glyphIndexArray = []


class cmap_format_2(CmapSubtable):
    def setIDDelta(self, subHeader):
        subHeader.idDelta = 0
        # find the minGI which is not zero.
        minGI = subHeader.glyphIndexArray[0]
        for gid in subHeader.glyphIndexArray:
            if (gid != 0) and (gid < minGI):
                minGI = gid
        # The lowest gid in glyphIndexArray, after subtracting idDelta, must be 1.
        # idDelta is a short, and must be between -32K and 32K. minGI can be between 1 and 64K.
        # We would like to pick an idDelta such that the first glyphArray GID is 1,
        # so that we are more likely to be able to combine glypharray GID subranges.
        # This means that we have a problem when minGI is > 32K
        # Since the final gi is reconstructed from the glyphArray GID by:
        #    (short)finalGID = (gid + idDelta) % 0x10000),
        # we can get from a glypharray GID of 1 to a final GID of 65K by subtracting 2, and casting the
        # negative number to an unsigned short.

        if minGI > 1:
            if minGI > 0x7FFF:
                subHeader.idDelta = -(0x10000 - minGI) - 1
            else:
                subHeader.idDelta = minGI - 1
            idDelta = subHeader.idDelta
            for i in range(subHeader.entryCount):
                gid = subHeader.glyphIndexArray[i]
                if gid > 0:
                    subHeader.glyphIndexArray[i] = gid - idDelta

    def decompile(self, data, ttFont):
        # we usually get here indirectly from the subtable __getattr__ function, in which case both args must be None.
        # If not, someone is calling the subtable decompile() directly, and must provide both args.
        if data is not None and ttFont is not None:
            self.decompileHeader(data, ttFont)
        else:
            assert (
                data is None and ttFont is None
            ), "Need both data and ttFont arguments"

        data = (
            self.data
        )  # decompileHeader assigns the data after the header to self.data
        subHeaderKeys = []
        maxSubHeaderindex = 0
        # get the key array, and determine the number of subHeaders.
        allKeys = array.array("H")
        allKeys.frombytes(data[:512])
        data = data[512:]
        if sys.byteorder != "big":
            allKeys.byteswap()
        subHeaderKeys = [key // 8 for key in allKeys]
        maxSubHeaderindex = max(subHeaderKeys)

        # Load subHeaders
        subHeaderList = []
        pos = 0
        for i in range(maxSubHeaderindex + 1):
            subHeader = SubHeader()
            (
                subHeader.firstCode,
                subHeader.entryCount,
                subHeader.idDelta,
                subHeader.idRangeOffset,
            ) = struct.unpack(subHeaderFormat, data[pos : pos + 8])
            pos += 8
            giDataPos = pos + subHeader.idRangeOffset - 2
            giList = array.array("H")
            giList.frombytes(data[giDataPos : giDataPos + subHeader.entryCount * 2])
            if sys.byteorder != "big":
                giList.byteswap()
            subHeader.glyphIndexArray = giList
            subHeaderList.append(subHeader)
        # How this gets processed.
        # Charcodes may be one or two bytes.
        # The first byte of a charcode is mapped through the subHeaderKeys, to select
        # a subHeader. For any subheader but 0, the next byte is then mapped through the
        # selected subheader. If subheader Index 0 is selected, then the byte itself is
        # mapped through the subheader, and there is no second byte.
        # Then assume that the subsequent byte is the first byte of the next charcode,and repeat.
        #
        # Each subheader references a range in the glyphIndexArray whose length is entryCount.
        # The range in glyphIndexArray referenced by a sunheader may overlap with the range in glyphIndexArray
        # referenced by another subheader.
        # The only subheader that will be referenced by more than one first-byte value is the subheader
        # that maps the entire range of glyphID values to glyphIndex 0, e.g notdef:
        # 	 {firstChar 0, EntryCount 0,idDelta 0,idRangeOffset xx}
        # A byte being mapped though a subheader is treated as in index into a mapping of array index to font glyphIndex.
        # A subheader specifies a subrange within (0...256) by the
        # firstChar and EntryCount values. If the byte value is outside the subrange, then the glyphIndex is zero
        # (e.g. glyph not in font).
        # If the byte index is in the subrange, then an offset index is calculated as (byteIndex - firstChar).
        # The index to glyphIndex mapping is a subrange of the glyphIndexArray. You find the start of the subrange by
        # counting idRangeOffset bytes from the idRangeOffset word. The first value in this subrange is the
        # glyphIndex for the index firstChar. The offset index should then be used in this array to get the glyphIndex.
        # Example for Logocut-Medium
        # first byte of charcode = 129; selects subheader 1.
        # subheader 1 = {firstChar 64, EntryCount 108,idDelta 42,idRangeOffset 0252}
        # second byte of charCode = 66
        # the index offset = 66-64 = 2.
        # The subrange of the glyphIndexArray starting at 0x0252 bytes from the idRangeOffset word is:
        # [glyphIndexArray index], [subrange array index] = glyphIndex
        # [256], [0]=1 	from charcode [129, 64]
        # [257], [1]=2  	from charcode [129, 65]
        # [258], [2]=3  	from charcode [129, 66]
        # [259], [3]=4  	from charcode [129, 67]
        # So, the glyphIndex = 3 from the array. Then if idDelta is not zero and the glyph ID is not zero,
        # add it to the glyphID to get the final glyphIndex
        # value. In this case the final glyph index = 3+ 42 -> 45 for the final glyphIndex. Whew!

        self.data = b""
        cmap = {}
        notdefGI = 0
        for firstByte in range(256):
            subHeadindex = subHeaderKeys[firstByte]
            subHeader = subHeaderList[subHeadindex]
            if subHeadindex == 0:
                if (firstByte < subHeader.firstCode) or (
                    firstByte >= subHeader.firstCode + subHeader.entryCount
                ):
                    continue  # gi is notdef.
                else:
                    charCode = firstByte
                    offsetIndex = firstByte - subHeader.firstCode
                    gi = subHeader.glyphIndexArray[offsetIndex]
                    if gi != 0:
                        gi = (gi + subHeader.idDelta) % 0x10000
                    else:
                        continue  # gi is notdef.
                cmap[charCode] = gi
            else:
                if subHeader.entryCount:
                    charCodeOffset = firstByte * 256 + subHeader.firstCode
                    for offsetIndex in range(subHeader.entryCount):
                        charCode = charCodeOffset + offsetIndex
                        gi = subHeader.glyphIndexArray[offsetIndex]
                        if gi != 0:
                            gi = (gi + subHeader.idDelta) % 0x10000
                        else:
                            continue
                        cmap[charCode] = gi
                # If not subHeader.entryCount, then all char codes with this first byte are
                # mapped to .notdef. We can skip this subtable, and leave the glyphs un-encoded, which is the
                # same as mapping it to .notdef.

        gids = list(cmap.values())
        charCodes = list(cmap.keys())
        self.cmap = _make_map(self.ttFont, charCodes, gids)

    def compile(self, ttFont):
        if self.data:
            return (
                struct.pack(">HHH", self.format, self.length, self.language) + self.data
            )
        kEmptyTwoCharCodeRange = -1
        notdefGI = 0

        items = sorted(self.cmap.items())
        charCodes = [item[0] for item in items]
        names = [item[1] for item in items]
        nameMap = ttFont.getReverseGlyphMap()
        try:
            gids = [nameMap[name] for name in names]
        except KeyError:
            nameMap = ttFont.getReverseGlyphMap(rebuild=True)
            try:
                gids = [nameMap[name] for name in names]
            except KeyError:
                # allow virtual GIDs in format 2 tables
                gids = []
                for name in names:
                    try:
                        gid = nameMap[name]
                    except KeyError:
                        try:
                            if name[:3] == "gid":
                                gid = int(name[3:])
                            else:
                                gid = ttFont.getGlyphID(name)
                        except:
                            raise KeyError(name)

                    gids.append(gid)

        # Process the (char code to gid) item list in char code order.
        # By definition, all one byte char codes map to subheader 0.
        # For all the two byte char codes, we assume that the first byte maps maps to the empty subhead (with an entry count of 0,
        # which defines all char codes in its range to map to notdef) unless proven otherwise.
        # Note that since the char code items are processed in char code order, all the char codes with the
        # same first byte are in sequential order.

        subHeaderKeys = [
            kEmptyTwoCharCodeRange for x in range(256)
        ]  # list of indices into subHeaderList.
        subHeaderList = []

        # We force this subheader entry 0 to exist in the subHeaderList in the case where some one comes up
        # with a cmap where all the one byte char codes map to notdef,
        # with the result that the subhead 0 would not get created just by processing the item list.
        charCode = charCodes[0]
        if charCode > 255:
            subHeader = SubHeader()
            subHeader.firstCode = 0
            subHeader.entryCount = 0
            subHeader.idDelta = 0
            subHeader.idRangeOffset = 0
            subHeaderList.append(subHeader)

        lastFirstByte = -1
        items = zip(charCodes, gids)
        for charCode, gid in items:
            if gid == 0:
                continue
            firstbyte = charCode >> 8
            secondByte = charCode & 0x00FF

            if (
                firstbyte != lastFirstByte
            ):  # Need to update the current subhead, and start a new one.
                if lastFirstByte > -1:
                    # fix GI's and iDelta of current subheader.
                    self.setIDDelta(subHeader)

                    # If it was sunheader 0 for one-byte charCodes, then we need to set the subHeaderKeys value to zero
                    # for the indices matching the char codes.
                    if lastFirstByte == 0:
                        for index in range(subHeader.entryCount):
                            charCode = subHeader.firstCode + index
                            subHeaderKeys[charCode] = 0

                    assert subHeader.entryCount == len(
                        subHeader.glyphIndexArray
                    ), "Error - subhead entry count does not match len of glyphID subrange."
                # init new subheader
                subHeader = SubHeader()
                subHeader.firstCode = secondByte
                subHeader.entryCount = 1
                subHeader.glyphIndexArray.append(gid)
                subHeaderList.append(subHeader)
                subHeaderKeys[firstbyte] = len(subHeaderList) - 1
                lastFirstByte = firstbyte
            else:
                # need to fill in with notdefs all the code points between the last charCode and the current charCode.
                codeDiff = secondByte - (subHeader.firstCode + subHeader.entryCount)
                for i in range(codeDiff):
                    subHeader.glyphIndexArray.append(notdefGI)
                subHeader.glyphIndexArray.append(gid)
                subHeader.entryCount = subHeader.entryCount + codeDiff + 1

        # fix GI's and iDelta of last subheader that we we added to the subheader array.
        self.setIDDelta(subHeader)

        # Now we add a final subheader for the subHeaderKeys which maps to empty two byte charcode ranges.
        subHeader = SubHeader()
        subHeader.firstCode = 0
        subHeader.entryCount = 0
        subHeader.idDelta = 0
        subHeader.idRangeOffset = 2
        subHeaderList.append(subHeader)
        emptySubheadIndex = len(subHeaderList) - 1
        for index in range(256):
            if subHeaderKeys[index] == kEmptyTwoCharCodeRange:
                subHeaderKeys[index] = emptySubheadIndex
        # Since this is the last subheader, the GlyphIndex Array starts two bytes after the start of the
        # idRangeOffset word of this subHeader. We can safely point to the first entry in the GlyphIndexArray,
        # since the first subrange of the GlyphIndexArray is for subHeader 0, which always starts with
        # charcode 0 and GID 0.

        idRangeOffset = (
            len(subHeaderList) - 1
        ) * 8 + 2  # offset to beginning of glyphIDArray from first subheader idRangeOffset.
        subheadRangeLen = (
            len(subHeaderList) - 1
        )  # skip last special empty-set subheader; we've already hardocodes its idRangeOffset to 2.
        for index in range(subheadRangeLen):
            subHeader = subHeaderList[index]
            subHeader.idRangeOffset = 0
            for j in range(index):
                prevSubhead = subHeaderList[j]
                if (
                    prevSubhead.glyphIndexArray == subHeader.glyphIndexArray
                ):  # use the glyphIndexArray subarray
                    subHeader.idRangeOffset = (
                        prevSubhead.idRangeOffset - (index - j) * 8
                    )
                    subHeader.glyphIndexArray = []
                    break
            if subHeader.idRangeOffset == 0:  # didn't find one.
                subHeader.idRangeOffset = idRangeOffset
                idRangeOffset = (
                    idRangeOffset - 8
                ) + subHeader.entryCount * 2  # one less subheader, one more subArray.
            else:
                idRangeOffset = idRangeOffset - 8  # one less subheader

        # Now we can write out the data!
        length = (
            6 + 512 + 8 * len(subHeaderList)
        )  # header, 256 subHeaderKeys, and subheader array.
        for subhead in subHeaderList[:-1]:
            length = (
                length + len(subhead.glyphIndexArray) * 2
            )  # We can't use subhead.entryCount, as some of the subhead may share subArrays.
        dataList = [struct.pack(">HHH", 2, length, self.language)]
        for index in subHeaderKeys:
            dataList.append(struct.pack(">H", index * 8))
        for subhead in subHeaderList:
            dataList.append(
                struct.pack(
                    subHeaderFormat,
                    subhead.firstCode,
                    subhead.entryCount,
                    subhead.idDelta,
                    subhead.idRangeOffset,
                )
            )
        for subhead in subHeaderList[:-1]:
            for gi in subhead.glyphIndexArray:
                dataList.append(struct.pack(">H", gi))
        data = bytesjoin(dataList)
        assert len(data) == length, (
            "Error: cmap format 2 is not same length as calculated! actual: "
            + str(len(data))
            + " calc : "
            + str(length)
        )
        return data

    def fromXML(self, name, attrs, content, ttFont):
        self.language = safeEval(attrs["language"])
        if not hasattr(self, "cmap"):
            self.cmap = {}
        cmap = self.cmap

        for element in content:
            if not isinstance(element, tuple):
                continue
            name, attrs, content = element
            if name != "map":
                continue
            cmap[safeEval(attrs["code"])] = attrs["name"]


cmap_format_4_format = ">7H"

# uint16  endCode[segCount]          # Ending character code for each segment, last = 0xFFFF.
# uint16  reservedPad                # This value should be zero
# uint16  startCode[segCount]        # Starting character code for each segment
# uint16  idDelta[segCount]          # Delta for all character codes in segment
# uint16  idRangeOffset[segCount]    # Offset in bytes to glyph indexArray, or 0
# uint16  glyphIndexArray[variable]  # Glyph index array


def splitRange(startCode, endCode, cmap):
    # Try to split a range of character codes into subranges with consecutive
    # glyph IDs in such a way that the cmap4 subtable can be stored "most"
    # efficiently. I can't prove I've got the optimal solution, but it seems
    # to do well with the fonts I tested: none became bigger, many became smaller.
    if startCode == endCode:
        return [], [endCode]

    lastID = cmap[startCode]
    lastCode = startCode
    inOrder = None
    orderedBegin = None
    subRanges = []

    # Gather subranges in which the glyph IDs are consecutive.
    for code in range(startCode + 1, endCode + 1):
        glyphID = cmap[code]

        if glyphID - 1 == lastID:
            if inOrder is None or not inOrder:
                inOrder = 1
                orderedBegin = lastCode
        else:
            if inOrder:
                inOrder = 0
                subRanges.append((orderedBegin, lastCode))
                orderedBegin = None

        lastID = glyphID
        lastCode = code

    if inOrder:
        subRanges.append((orderedBegin, lastCode))
    assert lastCode == endCode

    # Now filter out those new subranges that would only make the data bigger.
    # A new segment cost 8 bytes, not using a new segment costs 2 bytes per
    # character.
    newRanges = []
    for b, e in subRanges:
        if b == startCode and e == endCode:
            break  # the whole range, we're fine
        if b == startCode or e == endCode:
            threshold = 4  # split costs one more segment
        else:
            threshold = 8  # split costs two more segments
        if (e - b + 1) > threshold:
            newRanges.append((b, e))
    subRanges = newRanges

    if not subRanges:
        return [], [endCode]

    if subRanges[0][0] != startCode:
        subRanges.insert(0, (startCode, subRanges[0][0] - 1))
    if subRanges[-1][1] != endCode:
        subRanges.append((subRanges[-1][1] + 1, endCode))

    # Fill the "holes" in the segments list -- those are the segments in which
    # the glyph IDs are _not_ consecutive.
    i = 1
    while i < len(subRanges):
        if subRanges[i - 1][1] + 1 != subRanges[i][0]:
            subRanges.insert(i, (subRanges[i - 1][1] + 1, subRanges[i][0] - 1))
            i = i + 1
        i = i + 1

    # Transform the ranges into startCode/endCode lists.
    start = []
    end = []
    for b, e in subRanges:
        start.append(b)
        end.append(e)
    start.pop(0)

    assert len(start) + 1 == len(end)
    return start, end


class cmap_format_4(CmapSubtable):
    def decompile(self, data, ttFont):
        # we usually get here indirectly from the subtable __getattr__ function, in which case both args must be None.
        # If not, someone is calling the subtable decompile() directly, and must provide both args.
        if data is not None and ttFont is not None:
            self.decompileHeader(data, ttFont)
        else:
            assert (
                data is None and ttFont is None
            ), "Need both data and ttFont arguments"

        data = (
            self.data
        )  # decompileHeader assigns the data after the header to self.data
        (segCountX2, searchRange, entrySelector, rangeShift) = struct.unpack(
            ">4H", data[:8]
        )
        data = data[8:]
        segCount = segCountX2 // 2

        allCodes = array.array("H")
        allCodes.frombytes(data)
        self.data = data = None

        if sys.byteorder != "big":
            allCodes.byteswap()

        # divide the data
        endCode = allCodes[:segCount]
        allCodes = allCodes[segCount + 1 :]  # the +1 is skipping the reservedPad field
        startCode = allCodes[:segCount]
        allCodes = allCodes[segCount:]
        idDelta = allCodes[:segCount]
        allCodes = allCodes[segCount:]
        idRangeOffset = allCodes[:segCount]
        glyphIndexArray = allCodes[segCount:]
        lenGIArray = len(glyphIndexArray)

        # build 2-byte character mapping
        charCodes = []
        gids = []
        for i in range(len(startCode) - 1):  # don't do 0xffff!
            start = startCode[i]
            delta = idDelta[i]
            rangeOffset = idRangeOffset[i]
            partial = rangeOffset // 2 - start + i - len(idRangeOffset)

            rangeCharCodes = list(range(startCode[i], endCode[i] + 1))
            charCodes.extend(rangeCharCodes)
            if rangeOffset == 0:
                gids.extend(
                    [(charCode + delta) & 0xFFFF for charCode in rangeCharCodes]
                )
            else:
                for charCode in rangeCharCodes:
                    index = charCode + partial
                    assert index < lenGIArray, (
                        "In format 4 cmap, range (%d), the calculated index (%d) into the glyph index array is not less than the length of the array (%d) !"
                        % (i, index, lenGIArray)
                    )
                    if glyphIndexArray[index] != 0:  # if not missing glyph
                        glyphID = glyphIndexArray[index] + delta
                    else:
                        glyphID = 0  # missing glyph
                    gids.append(glyphID & 0xFFFF)

        self.cmap = _make_map(self.ttFont, charCodes, gids)

    def compile(self, ttFont):
        if self.data:
            return (
                struct.pack(">HHH", self.format, self.length, self.language) + self.data
            )

        charCodes = list(self.cmap.keys())
        if not charCodes:
            startCode = [0xFFFF]
            endCode = [0xFFFF]
        else:
            charCodes.sort()
            names = [self.cmap[code] for code in charCodes]
            nameMap = ttFont.getReverseGlyphMap()
            try:
                gids = [nameMap[name] for name in names]
            except KeyError:
                nameMap = ttFont.getReverseGlyphMap(rebuild=True)
                try:
                    gids = [nameMap[name] for name in names]
                except KeyError:
                    # allow virtual GIDs in format 4 tables
                    gids = []
                    for name in names:
                        try:
                            gid = nameMap[name]
                        except KeyError:
                            try:
                                if name[:3] == "gid":
                                    gid = int(name[3:])
                                else:
                                    gid = ttFont.getGlyphID(name)
                            except:
                                raise KeyError(name)

                        gids.append(gid)
            cmap = {}  # code:glyphID mapping
            for code, gid in zip(charCodes, gids):
                cmap[code] = gid

            # Build startCode and endCode lists.
            # Split the char codes in ranges of consecutive char codes, then split
            # each range in more ranges of consecutive/not consecutive glyph IDs.
            # See splitRange().
            lastCode = charCodes[0]
            endCode = []
            startCode = [lastCode]
            for charCode in charCodes[
                1:
            ]:  # skip the first code, it's the first start code
                if charCode == lastCode + 1:
                    lastCode = charCode
                    continue
                start, end = splitRange(startCode[-1], lastCode, cmap)
                startCode.extend(start)
                endCode.extend(end)
                startCode.append(charCode)
                lastCode = charCode
            start, end = splitRange(startCode[-1], lastCode, cmap)
            startCode.extend(start)
            endCode.extend(end)
            startCode.append(0xFFFF)
            endCode.append(0xFFFF)

        # build up rest of cruft
        idDelta = []
        idRangeOffset = []
        glyphIndexArray = []
        for i in range(len(endCode) - 1):  # skip the closing codes (0xffff)
            indices = []
            for charCode in range(startCode[i], endCode[i] + 1):
                indices.append(cmap[charCode])
            if indices == list(range(indices[0], indices[0] + len(indices))):
                idDelta.append((indices[0] - startCode[i]) % 0x10000)
                idRangeOffset.append(0)
            else:
                idDelta.append(0)
                idRangeOffset.append(2 * (len(endCode) + len(glyphIndexArray) - i))
                glyphIndexArray.extend(indices)
        idDelta.append(1)  # 0xffff + 1 == (tadaa!) 0. So this end code maps to .notdef
        idRangeOffset.append(0)

        # Insane.
        segCount = len(endCode)
        segCountX2 = segCount * 2
        searchRange, entrySelector, rangeShift = getSearchRange(segCount, 2)

        charCodeArray = array.array("H", endCode + [0] + startCode)
        idDeltaArray = array.array("H", idDelta)
        restArray = array.array("H", idRangeOffset + glyphIndexArray)
        if sys.byteorder != "big":
            charCodeArray.byteswap()
        if sys.byteorder != "big":
            idDeltaArray.byteswap()
        if sys.byteorder != "big":
            restArray.byteswap()
        data = charCodeArray.tobytes() + idDeltaArray.tobytes() + restArray.tobytes()

        length = struct.calcsize(cmap_format_4_format) + len(data)
        header = struct.pack(
            cmap_format_4_format,
            self.format,
            length,
            self.language,
            segCountX2,
            searchRange,
            entrySelector,
            rangeShift,
        )
        return header + data

    def fromXML(self, name, attrs, content, ttFont):
        self.language = safeEval(attrs["language"])
        if not hasattr(self, "cmap"):
            self.cmap = {}
        cmap = self.cmap

        for element in content:
            if not isinstance(element, tuple):
                continue
            nameMap, attrsMap, dummyContent = element
            if nameMap != "map":
                assert 0, "Unrecognized keyword in cmap subtable"
            cmap[safeEval(attrsMap["code"])] = attrsMap["name"]


class cmap_format_6(CmapSubtable):
    def decompile(self, data, ttFont):
        # we usually get here indirectly from the subtable __getattr__ function, in which case both args must be None.
        # If not, someone is calling the subtable decompile() directly, and must provide both args.
        if data is not None and ttFont is not None:
            self.decompileHeader(data, ttFont)
        else:
            assert (
                data is None and ttFont is None
            ), "Need both data and ttFont arguments"

        data = (
            self.data
        )  # decompileHeader assigns the data after the header to self.data
        firstCode, entryCount = struct.unpack(">HH", data[:4])
        firstCode = int(firstCode)
        data = data[4:]
        # assert len(data) == 2 * entryCount  # XXX not true in Apple's Helvetica!!!
        gids = array.array("H")
        gids.frombytes(data[: 2 * int(entryCount)])
        if sys.byteorder != "big":
            gids.byteswap()
        self.data = data = None

        charCodes = list(range(firstCode, firstCode + len(gids)))
        self.cmap = _make_map(self.ttFont, charCodes, gids)

    def compile(self, ttFont):
        if self.data:
            return (
                struct.pack(">HHH", self.format, self.length, self.language) + self.data
            )
        cmap = self.cmap
        codes = sorted(cmap.keys())
        if codes:  # yes, there are empty cmap tables.
            codes = list(range(codes[0], codes[-1] + 1))
            firstCode = codes[0]
            valueList = [
                ttFont.getGlyphID(cmap[code]) if code in cmap else 0 for code in codes
            ]
            gids = array.array("H", valueList)
            if sys.byteorder != "big":
                gids.byteswap()
            data = gids.tobytes()
        else:
            data = b""
            firstCode = 0
        header = struct.pack(
            ">HHHHH", 6, len(data) + 10, self.language, firstCode, len(codes)
        )
        return header + data

    def fromXML(self, name, attrs, content, ttFont):
        self.language = safeEval(attrs["language"])
        if not hasattr(self, "cmap"):
            self.cmap = {}
        cmap = self.cmap

        for element in content:
            if not isinstance(element, tuple):
                continue
            name, attrs, content = element
            if name != "map":
                continue
            cmap[safeEval(attrs["code"])] = attrs["name"]


class cmap_format_12_or_13(CmapSubtable):
    def __init__(self, format):
        self.format = format
        self.reserved = 0
        self.data = None
        self.ttFont = None

    def decompileHeader(self, data, ttFont):
        format, reserved, length, language, nGroups = struct.unpack(">HHLLL", data[:16])
        assert (
            len(data) == (16 + nGroups * 12) == (length)
        ), "corrupt cmap table format %d (data length: %d, header length: %d)" % (
            self.format,
            len(data),
            length,
        )
        self.format = format
        self.reserved = reserved
        self.length = length
        self.language = language
        self.nGroups = nGroups
        self.data = data[16:]
        self.ttFont = ttFont

    def decompile(self, data, ttFont):
        # we usually get here indirectly from the subtable __getattr__ function, in which case both args must be None.
        # If not, someone is calling the subtable decompile() directly, and must provide both args.
        if data is not None and ttFont is not None:
            self.decompileHeader(data, ttFont)
        else:
            assert (
                data is None and ttFont is None
            ), "Need both data and ttFont arguments"

        data = (
            self.data
        )  # decompileHeader assigns the data after the header to self.data
        charCodes = []
        gids = []
        pos = 0
        groups = array.array("I", data[: self.nGroups * 12])
        if sys.byteorder != "big":
            groups.byteswap()
        for i in range(self.nGroups):
            startCharCode = groups[i * 3]
            endCharCode = groups[i * 3 + 1]
            glyphID = groups[i * 3 + 2]
            lenGroup = 1 + endCharCode - startCharCode
            charCodes.extend(range(startCharCode, endCharCode + 1))
            gids.extend(self._computeGIDs(glyphID, lenGroup))
        self.data = data = None
        self.cmap = _make_map(self.ttFont, charCodes, gids)

    def compile(self, ttFont):
        if self.data:
            return (
                struct.pack(
                    ">HHLLL",
                    self.format,
                    self.reserved,
                    self.length,
                    self.language,
                    self.nGroups,
                )
                + self.data
            )
        charCodes = list(self.cmap.keys())
        names = list(self.cmap.values())
        nameMap = ttFont.getReverseGlyphMap()
        try:
            gids = [nameMap[name] for name in names]
        except KeyError:
            nameMap = ttFont.getReverseGlyphMap(rebuild=True)
            try:
                gids = [nameMap[name] for name in names]
            except KeyError:
                # allow virtual GIDs in format 12 tables
                gids = []
                for name in names:
                    try:
                        gid = nameMap[name]
                    except KeyError:
                        try:
                            if name[:3] == "gid":
                                gid = int(name[3:])
                            else:
                                gid = ttFont.getGlyphID(name)
                        except:
                            raise KeyError(name)

                    gids.append(gid)

        cmap = {}  # code:glyphID mapping
        for code, gid in zip(charCodes, gids):
            cmap[code] = gid

        charCodes.sort()
        index = 0
        startCharCode = charCodes[0]
        startGlyphID = cmap[startCharCode]
        lastGlyphID = startGlyphID - self._format_step
        lastCharCode = startCharCode - 1
        nGroups = 0
        dataList = []
        maxIndex = len(charCodes)
        for index in range(maxIndex):
            charCode = charCodes[index]
            glyphID = cmap[charCode]
            if not self._IsInSameRun(glyphID, lastGlyphID, charCode, lastCharCode):
                dataList.append(
                    struct.pack(">LLL", startCharCode, lastCharCode, startGlyphID)
                )
                startCharCode = charCode
                startGlyphID = glyphID
                nGroups = nGroups + 1
            lastGlyphID = glyphID
            lastCharCode = charCode
        dataList.append(struct.pack(">LLL", startCharCode, lastCharCode, startGlyphID))
        nGroups = nGroups + 1
        data = bytesjoin(dataList)
        lengthSubtable = len(data) + 16
        assert len(data) == (nGroups * 12) == (lengthSubtable - 16)
        return (
            struct.pack(
                ">HHLLL",
                self.format,
                self.reserved,
                lengthSubtable,
                self.language,
                nGroups,
            )
            + data
        )

    def toXML(self, writer, ttFont):
        writer.begintag(
            self.__class__.__name__,
            [
                ("platformID", self.platformID),
                ("platEncID", self.platEncID),
                ("format", self.format),
                ("reserved", self.reserved),
                ("length", self.length),
                ("language", self.language),
                ("nGroups", self.nGroups),
            ],
        )
        writer.newline()
        codes = sorted(self.cmap.items())
        self._writeCodes(codes, writer)
        writer.endtag(self.__class__.__name__)
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        self.format = safeEval(attrs["format"])
        self.reserved = safeEval(attrs["reserved"])
        self.length = safeEval(attrs["length"])
        self.language = safeEval(attrs["language"])
        self.nGroups = safeEval(attrs["nGroups"])
        if not hasattr(self, "cmap"):
            self.cmap = {}
        cmap = self.cmap

        for element in content:
            if not isinstance(element, tuple):
                continue
            name, attrs, content = element
            if name != "map":
                continue
            cmap[safeEval(attrs["code"])] = attrs["name"]


class cmap_format_12(cmap_format_12_or_13):
    _format_step = 1

    def __init__(self, format=12):
        cmap_format_12_or_13.__init__(self, format)

    def _computeGIDs(self, startingGlyph, numberOfGlyphs):
        return range(startingGlyph, startingGlyph + numberOfGlyphs)

    def _IsInSameRun(self, glyphID, lastGlyphID, charCode, lastCharCode):
        return (glyphID == 1 + lastGlyphID) and (charCode == 1 + lastCharCode)


class cmap_format_13(cmap_format_12_or_13):
    _format_step = 0

    def __init__(self, format=13):
        cmap_format_12_or_13.__init__(self, format)

    def _computeGIDs(self, startingGlyph, numberOfGlyphs):
        return [startingGlyph] * numberOfGlyphs

    def _IsInSameRun(self, glyphID, lastGlyphID, charCode, lastCharCode):
        return (glyphID == lastGlyphID) and (charCode == 1 + lastCharCode)


def cvtToUVS(threeByteString):
    data = b"\0" + threeByteString
    (val,) = struct.unpack(">L", data)
    return val


def cvtFromUVS(val):
    assert 0 <= val < 0x1000000
    fourByteString = struct.pack(">L", val)
    return fourByteString[1:]


class cmap_format_14(CmapSubtable):
    def decompileHeader(self, data, ttFont):
        format, length, numVarSelectorRecords = struct.unpack(">HLL", data[:10])
        self.data = data[10:]
        self.length = length
        self.numVarSelectorRecords = numVarSelectorRecords
        self.ttFont = ttFont
        self.language = 0xFF  # has no language.

    def decompile(self, data, ttFont):
        if data is not None and ttFont is not None:
            self.decompileHeader(data, ttFont)
        else:
            assert (
                data is None and ttFont is None
            ), "Need both data and ttFont arguments"
        data = self.data

        self.cmap = (
            {}
        )  # so that clients that expect this to exist in a cmap table won't fail.
        uvsDict = {}
        recOffset = 0
        for n in range(self.numVarSelectorRecords):
            uvs, defOVSOffset, nonDefUVSOffset = struct.unpack(
                ">3sLL", data[recOffset : recOffset + 11]
            )
            recOffset += 11
            varUVS = cvtToUVS(uvs)
            if defOVSOffset:
                startOffset = defOVSOffset - 10
                (numValues,) = struct.unpack(">L", data[startOffset : startOffset + 4])
                startOffset += 4
                for r in range(numValues):
                    uv, addtlCnt = struct.unpack(
                        ">3sB", data[startOffset : startOffset + 4]
                    )
                    startOffset += 4
                    firstBaseUV = cvtToUVS(uv)
                    cnt = addtlCnt + 1
                    baseUVList = list(range(firstBaseUV, firstBaseUV + cnt))
                    glyphList = [None] * cnt
                    localUVList = zip(baseUVList, glyphList)
                    try:
                        uvsDict[varUVS].extend(localUVList)
                    except KeyError:
                        uvsDict[varUVS] = list(localUVList)

            if nonDefUVSOffset:
                startOffset = nonDefUVSOffset - 10
                (numRecs,) = struct.unpack(">L", data[startOffset : startOffset + 4])
                startOffset += 4
                localUVList = []
                for r in range(numRecs):
                    uv, gid = struct.unpack(">3sH", data[startOffset : startOffset + 5])
                    startOffset += 5
                    uv = cvtToUVS(uv)
                    glyphName = self.ttFont.getGlyphName(gid)
                    localUVList.append((uv, glyphName))
                try:
                    uvsDict[varUVS].extend(localUVList)
                except KeyError:
                    uvsDict[varUVS] = localUVList

        self.uvsDict = uvsDict

    def toXML(self, writer, ttFont):
        writer.begintag(
            self.__class__.__name__,
            [
                ("platformID", self.platformID),
                ("platEncID", self.platEncID),
            ],
        )
        writer.newline()
        uvsDict = self.uvsDict
        uvsList = sorted(uvsDict.keys())
        for uvs in uvsList:
            uvList = uvsDict[uvs]
            uvList.sort(key=lambda item: (item[1] is not None, item[0], item[1]))
            for uv, gname in uvList:
                attrs = [("uv", hex(uv)), ("uvs", hex(uvs))]
                if gname is not None:
                    attrs.append(("name", gname))
                writer.simpletag("map", attrs)
                writer.newline()
        writer.endtag(self.__class__.__name__)
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        self.language = 0xFF  # provide a value so that CmapSubtable.__lt__() won't fail
        if not hasattr(self, "cmap"):
            self.cmap = (
                {}
            )  # so that clients that expect this to exist in a cmap table won't fail.
        if not hasattr(self, "uvsDict"):
            self.uvsDict = {}
            uvsDict = self.uvsDict

        # For backwards compatibility reasons we accept "None" as an indicator
        # for "default mapping", unless the font actually has a glyph named
        # "None".
        _hasGlyphNamedNone = None

        for element in content:
            if not isinstance(element, tuple):
                continue
            name, attrs, content = element
            if name != "map":
                continue
            uvs = safeEval(attrs["uvs"])
            uv = safeEval(attrs["uv"])
            gname = attrs.get("name")
            if gname == "None":
                if _hasGlyphNamedNone is None:
                    _hasGlyphNamedNone = "None" in ttFont.getGlyphOrder()
                if not _hasGlyphNamedNone:
                    gname = None
            try:
                uvsDict[uvs].append((uv, gname))
            except KeyError:
                uvsDict[uvs] = [(uv, gname)]

    def compile(self, ttFont):
        if self.data:
            return (
                struct.pack(
                    ">HLL", self.format, self.length, self.numVarSelectorRecords
                )
                + self.data
            )

        uvsDict = self.uvsDict
        uvsList = sorted(uvsDict.keys())
        self.numVarSelectorRecords = len(uvsList)
        offset = (
            10 + self.numVarSelectorRecords * 11
        )  # current value is end of VarSelectorRecords block.
        data = []
        varSelectorRecords = []
        for uvs in uvsList:
            entryList = uvsDict[uvs]

            defList = [entry for entry in entryList if entry[1] is None]
            if defList:
                defList = [entry[0] for entry in defList]
                defOVSOffset = offset
                defList.sort()

                lastUV = defList[0]
                cnt = -1
                defRecs = []
                for defEntry in defList:
                    cnt += 1
                    if (lastUV + cnt) != defEntry:
                        rec = struct.pack(">3sB", cvtFromUVS(lastUV), cnt - 1)
                        lastUV = defEntry
                        defRecs.append(rec)
                        cnt = 0

                rec = struct.pack(">3sB", cvtFromUVS(lastUV), cnt)
                defRecs.append(rec)

                numDefRecs = len(defRecs)
                data.append(struct.pack(">L", numDefRecs))
                data.extend(defRecs)
                offset += 4 + numDefRecs * 4
            else:
                defOVSOffset = 0

            ndefList = [entry for entry in entryList if entry[1] is not None]
            if ndefList:
                nonDefUVSOffset = offset
                ndefList.sort()
                numNonDefRecs = len(ndefList)
                data.append(struct.pack(">L", numNonDefRecs))
                offset += 4 + numNonDefRecs * 5

                for uv, gname in ndefList:
                    gid = ttFont.getGlyphID(gname)
                    ndrec = struct.pack(">3sH", cvtFromUVS(uv), gid)
                    data.append(ndrec)
            else:
                nonDefUVSOffset = 0

            vrec = struct.pack(">3sLL", cvtFromUVS(uvs), defOVSOffset, nonDefUVSOffset)
            varSelectorRecords.append(vrec)

        data = bytesjoin(varSelectorRecords) + bytesjoin(data)
        self.length = 10 + len(data)
        headerdata = struct.pack(
            ">HLL", self.format, self.length, self.numVarSelectorRecords
        )

        return headerdata + data


class cmap_format_unknown(CmapSubtable):
    def toXML(self, writer, ttFont):
        cmapName = self.__class__.__name__[:12] + str(self.format)
        writer.begintag(
            cmapName,
            [
                ("platformID", self.platformID),
                ("platEncID", self.platEncID),
            ],
        )
        writer.newline()
        writer.dumphex(self.data)
        writer.endtag(cmapName)
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        self.data = readHex(content)
        self.cmap = {}

    def decompileHeader(self, data, ttFont):
        self.language = 0  # dummy value
        self.data = data

    def decompile(self, data, ttFont):
        # we usually get here indirectly from the subtable __getattr__ function, in which case both args must be None.
        # If not, someone is calling the subtable decompile() directly, and must provide both args.
        if data is not None and ttFont is not None:
            self.decompileHeader(data, ttFont)
        else:
            assert (
                data is None and ttFont is None
            ), "Need both data and ttFont arguments"

    def compile(self, ttFont):
        if self.data:
            return self.data
        else:
            return None


cmap_classes = {
    0: cmap_format_0,
    2: cmap_format_2,
    4: cmap_format_4,
    6: cmap_format_6,
    12: cmap_format_12,
    13: cmap_format_13,
    14: cmap_format_14,
}
