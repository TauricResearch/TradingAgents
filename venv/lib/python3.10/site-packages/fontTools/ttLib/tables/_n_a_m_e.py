# -*- coding: utf-8 -*-
from __future__ import annotations

from fontTools.misc import sstruct
from fontTools.misc.textTools import (
    bytechr,
    byteord,
    bytesjoin,
    strjoin,
    tobytes,
    tostr,
    safeEval,
)
from fontTools.misc.encodingTools import getEncoding
from fontTools.ttLib import newTable
from fontTools.ttLib.ttVisitor import TTVisitor
from fontTools import ttLib
import fontTools.ttLib.tables.otTables as otTables
from fontTools.ttLib.tables import C_P_A_L_
from . import DefaultTable
import struct
import logging


log = logging.getLogger(__name__)

nameRecordFormat = """
		>	# big endian
		platformID:	H
		platEncID:	H
		langID:		H
		nameID:		H
		length:		H
		offset:		H
"""

nameRecordSize = sstruct.calcsize(nameRecordFormat)


class table__n_a_m_e(DefaultTable.DefaultTable):
    """Naming table

    The ``name`` table is used to store a variety of strings that can be
    associated with user-facing font information. Records in the ``name``
    table can be tagged with language tags to support multilingual naming
    and can support platform-specific character-encoding variants.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/name
    """

    dependencies = ["ltag"]

    def __init__(self, tag=None):
        super().__init__(tag)
        self.names = []

    def decompile(self, data, ttFont):
        format, n, stringOffset = struct.unpack(b">HHH", data[:6])
        expectedStringOffset = 6 + n * nameRecordSize
        if stringOffset != expectedStringOffset:
            log.error(
                "'name' table stringOffset incorrect. Expected: %s; Actual: %s",
                expectedStringOffset,
                stringOffset,
            )
        stringData = data[stringOffset:]
        data = data[6:]
        self.names: list[NameRecord] = []
        for i in range(n):
            if len(data) < 12:
                log.error("skipping malformed name record #%d", i)
                continue
            name, data = sstruct.unpack2(nameRecordFormat, data, NameRecord())
            name.string = stringData[name.offset : name.offset + name.length]
            if name.offset + name.length > len(stringData):
                log.error("skipping malformed name record #%d", i)
                continue
            assert len(name.string) == name.length
            # if (name.platEncID, name.platformID) in ((0, 0), (1, 3)):
            # 	if len(name.string) % 2:
            # 		print "2-byte string doesn't have even length!"
            # 		print name.__dict__
            del name.offset, name.length
            self.names.append(name)

    def compile(self, ttFont):
        names = self.names
        names.sort()  # sort according to the spec; see NameRecord.__lt__()
        stringData = b""
        format = 0
        n = len(names)
        stringOffset = 6 + n * sstruct.calcsize(nameRecordFormat)
        data = struct.pack(b">HHH", format, n, stringOffset)
        lastoffset = 0
        done = {}  # remember the data so we can reuse the "pointers"
        for name in names:
            string = name.toBytes()
            if string in done:
                name.offset, name.length = done[string]
            else:
                name.offset, name.length = done[string] = len(stringData), len(string)
                stringData = bytesjoin([stringData, string])
            data = data + sstruct.pack(nameRecordFormat, name)
        return data + stringData

    def toXML(self, writer, ttFont):
        for name in self.names:
            name.toXML(writer, ttFont)

    def fromXML(self, name, attrs, content, ttFont):
        if name != "namerecord":
            return  # ignore unknown tags
        name = NameRecord()
        self.names.append(name)
        name.fromXML(name, attrs, content, ttFont)

    def getName(
        self, nameID: int, platformID: int, platEncID: int, langID: int | None = None
    ) -> "NameRecord | None":
        for namerecord in self.names:
            if (
                namerecord.nameID == nameID
                and namerecord.platformID == platformID
                and namerecord.platEncID == platEncID
            ):
                if langID is None or namerecord.langID == langID:
                    return namerecord
        return None  # not found

    def getDebugName(self, nameID: int) -> str | None:
        englishName: str | None = None
        someName: str | None = None
        for name in self.names:
            if name.nameID != nameID:
                continue
            try:
                unistr = name.toUnicode()
            except UnicodeDecodeError:
                continue

            someName = unistr
            if (name.platformID, name.langID) in ((1, 0), (3, 0x409)):
                englishName = unistr
                break
        if englishName:
            return englishName
        elif someName:
            return someName
        else:
            return None

    def getFirstDebugName(self, nameIDs):
        for nameID in nameIDs:
            name = self.getDebugName(nameID)
            if name is not None:
                return name
        return None

    def getBestFamilyName(self):
        # 21 = WWS Family Name
        # 16 = Typographic Family Name
        # 1 = Family Name
        return self.getFirstDebugName((21, 16, 1))

    def getBestSubFamilyName(self):
        # 22 = WWS SubFamily Name
        # 17 = Typographic SubFamily Name
        # 2 = SubFamily Name
        return self.getFirstDebugName((22, 17, 2))

    def getBestFullName(self):
        # 4 = Full Name
        # 6 = PostScript Name
        for nameIDs in ((21, 22), (16, 17), (1, 2), (4,), (6,)):
            if len(nameIDs) == 2:
                name_fam = self.getDebugName(nameIDs[0])
                name_subfam = self.getDebugName(nameIDs[1])
                if None in [name_fam, name_subfam]:
                    continue  # if any is None, skip
                name = f"{name_fam} {name_subfam}"
                if name_subfam.lower() == "regular":
                    name = f"{name_fam}"
                return name
            else:
                name = self.getDebugName(nameIDs[0])
                if name is not None:
                    return name
        return None

    def setName(self, string, nameID, platformID, platEncID, langID):
        """Set the 'string' for the name record identified by 'nameID', 'platformID',
        'platEncID' and 'langID'. If a record with that nameID doesn't exist, create it
        and append to the name table.

        'string' can be of type `str` (`unicode` in PY2) or `bytes`. In the latter case,
        it is assumed to be already encoded with the correct plaform-specific encoding
        identified by the (platformID, platEncID, langID) triplet. A warning is issued
        to prevent unexpected results.
        """
        if not isinstance(string, str):
            if isinstance(string, bytes):
                log.warning(
                    "name string is bytes, ensure it's correctly encoded: %r", string
                )
            else:
                raise TypeError(
                    "expected unicode or bytes, found %s: %r"
                    % (type(string).__name__, string)
                )
        namerecord = self.getName(nameID, platformID, platEncID, langID)
        if namerecord:
            namerecord.string = string
        else:
            self.names.append(makeName(string, nameID, platformID, platEncID, langID))

    def removeNames(self, nameID=None, platformID=None, platEncID=None, langID=None):
        """Remove any name records identified by the given combination of 'nameID',
        'platformID', 'platEncID' and 'langID'.
        """
        args = {
            argName: argValue
            for argName, argValue in (
                ("nameID", nameID),
                ("platformID", platformID),
                ("platEncID", platEncID),
                ("langID", langID),
            )
            if argValue is not None
        }
        if not args:
            # no arguments, nothing to do
            return
        self.names = [
            rec
            for rec in self.names
            if any(
                argValue != getattr(rec, argName) for argName, argValue in args.items()
            )
        ]

    @staticmethod
    def removeUnusedNames(ttFont):
        """Remove any name records which are not in NameID range 0-255 and not utilized
        within the font itself."""
        visitor = NameRecordVisitor()
        visitor.visit(ttFont)
        toDelete = set()
        for record in ttFont["name"].names:
            # Name IDs 26 to 255, inclusive, are reserved for future standard names.
            # https://learn.microsoft.com/en-us/typography/opentype/spec/name#name-ids
            if record.nameID < 256:
                continue
            if record.nameID not in visitor.seen:
                toDelete.add(record.nameID)

        for nameID in toDelete:
            ttFont["name"].removeNames(nameID)
        return toDelete

    def _findUnusedNameID(self, minNameID=256):
        """Finds an unused name id.

        The nameID is assigned in the range between 'minNameID' and 32767 (inclusive),
        following the last nameID in the name table.
        """
        names = self.names
        nameID = 1 + max([n.nameID for n in names] + [minNameID - 1])
        if nameID > 32767:
            raise ValueError("nameID must be less than 32768")
        return nameID

    def findMultilingualName(
        self, names, windows=True, mac=True, minNameID=0, ttFont=None
    ):
        """Return the name ID of an existing multilingual name that
        matches the 'names' dictionary, or None if not found.

        'names' is a dictionary with the name in multiple languages,
        such as {'en': 'Pale', 'de': 'Blaß', 'de-CH': 'Blass'}.
        The keys can be arbitrary IETF BCP 47 language codes;
        the values are Unicode strings.

        If 'windows' is True, the returned name ID is guaranteed
        exist for all requested languages for platformID=3 and
        platEncID=1.
        If 'mac' is True, the returned name ID is guaranteed to exist
        for all requested languages for platformID=1 and platEncID=0.

        The returned name ID will not be less than the 'minNameID'
        argument.
        """
        # Gather the set of requested
        #   (string, platformID, platEncID, langID)
        # tuples
        reqNameSet = set()
        for lang, name in sorted(names.items()):
            if windows:
                windowsName = _makeWindowsName(name, None, lang)
                if windowsName is not None:
                    reqNameSet.add(
                        (
                            windowsName.string,
                            windowsName.platformID,
                            windowsName.platEncID,
                            windowsName.langID,
                        )
                    )
            if mac:
                macName = _makeMacName(name, None, lang, ttFont)
                if macName is not None:
                    reqNameSet.add(
                        (
                            macName.string,
                            macName.platformID,
                            macName.platEncID,
                            macName.langID,
                        )
                    )

        # Collect matching name IDs
        matchingNames = dict()
        for name in self.names:
            try:
                key = (name.toUnicode(), name.platformID, name.platEncID, name.langID)
            except UnicodeDecodeError:
                continue
            if key in reqNameSet and name.nameID >= minNameID:
                nameSet = matchingNames.setdefault(name.nameID, set())
                nameSet.add(key)

        # Return the first name ID that defines all requested strings
        for nameID, nameSet in sorted(matchingNames.items()):
            if nameSet == reqNameSet:
                return nameID

        return None  # not found

    def addMultilingualName(
        self, names, ttFont=None, nameID=None, windows=True, mac=True, minNameID=0
    ):
        """Add a multilingual name, returning its name ID

        'names' is a dictionary with the name in multiple languages,
        such as {'en': 'Pale', 'de': 'Blaß', 'de-CH': 'Blass'}.
        The keys can be arbitrary IETF BCP 47 language codes;
        the values are Unicode strings.

        'ttFont' is the TTFont to which the names are added, or None.
        If present, the font's 'ltag' table can get populated
        to store exotic language codes, which allows encoding
        names that otherwise cannot get encoded at all.

        'nameID' is the name ID to be used, or None to let the library
        find an existing set of name records that match, or pick an
        unused name ID.

        If 'windows' is True, a platformID=3 name record will be added.
        If 'mac' is True, a platformID=1 name record will be added.

        If the 'nameID' argument is None, the created nameID will not
        be less than the 'minNameID' argument.
        """
        if nameID is None:
            # Reuse nameID if possible
            nameID = self.findMultilingualName(
                names, windows=windows, mac=mac, minNameID=minNameID, ttFont=ttFont
            )
            if nameID is not None:
                return nameID
            nameID = self._findUnusedNameID()
        # TODO: Should minimize BCP 47 language codes.
        # https://github.com/fonttools/fonttools/issues/930
        for lang, name in sorted(names.items()):
            if windows:
                windowsName = _makeWindowsName(name, nameID, lang)
                if windowsName is not None:
                    self.names.append(windowsName)
                else:
                    # We cannot not make a Windows name: make sure we add a
                    # Mac name as a fallback. This can happen for exotic
                    # BCP47 language tags that have no Windows language code.
                    mac = True
            if mac:
                macName = _makeMacName(name, nameID, lang, ttFont)
                if macName is not None:
                    self.names.append(macName)
        return nameID

    def addName(self, string, platforms=((1, 0, 0), (3, 1, 0x409)), minNameID=255):
        """Add a new name record containing 'string' for each (platformID, platEncID,
        langID) tuple specified in the 'platforms' list.

        The nameID is assigned in the range between 'minNameID'+1 and 32767 (inclusive),
        following the last nameID in the name table.
        If no 'platforms' are specified, two English name records are added, one for the
        Macintosh (platformID=0), and one for the Windows platform (3).

        The 'string' must be a Unicode string, so it can be encoded with different,
        platform-specific encodings.

        Return the new nameID.
        """
        assert (
            len(platforms) > 0
        ), "'platforms' must contain at least one (platformID, platEncID, langID) tuple"
        if not isinstance(string, str):
            raise TypeError(
                "expected str, found %s: %r" % (type(string).__name__, string)
            )
        nameID = self._findUnusedNameID(minNameID + 1)
        for platformID, platEncID, langID in platforms:
            self.names.append(makeName(string, nameID, platformID, platEncID, langID))
        return nameID


def makeName(string, nameID, platformID, platEncID, langID):
    name = NameRecord()
    name.string, name.nameID, name.platformID, name.platEncID, name.langID = (
        string,
        nameID,
        platformID,
        platEncID,
        langID,
    )
    return name


def _makeWindowsName(name, nameID, language):
    """Create a NameRecord for the Microsoft Windows platform

    'language' is an arbitrary IETF BCP 47 language identifier such
    as 'en', 'de-CH', 'de-AT-1901', or 'fa-Latn'. If Microsoft Windows
    does not support the desired language, the result will be None.
    Future versions of fonttools might return a NameRecord for the
    OpenType 'name' table format 1, but this is not implemented yet.
    """
    langID = _WINDOWS_LANGUAGE_CODES.get(language.lower())
    if langID is not None:
        return makeName(name, nameID, 3, 1, langID)
    else:
        log.warning(
            "cannot add Windows name in language %s "
            "because fonttools does not yet support "
            "name table format 1" % language
        )
        return None


def _makeMacName(name, nameID, language, font=None):
    """Create a NameRecord for Apple platforms

    'language' is an arbitrary IETF BCP 47 language identifier such
    as 'en', 'de-CH', 'de-AT-1901', or 'fa-Latn'. When possible, we
    create a Macintosh NameRecord that is understood by old applications
    (platform ID 1 and an old-style Macintosh language enum). If this
    is not possible, we create a Unicode NameRecord (platform ID 0)
    whose language points to the font’s 'ltag' table. The latter
    can encode any string in any language, but legacy applications
    might not recognize the format (in which case they will ignore
    those names).

    'font' should be the TTFont for which you want to create a name.
    If 'font' is None, we only return NameRecords for legacy Macintosh;
    in that case, the result will be None for names that need to
    be encoded with an 'ltag' table.

    See the section “The language identifier” in Apple’s specification:
    https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6name.html
    """
    macLang = _MAC_LANGUAGE_CODES.get(language.lower())
    macScript = _MAC_LANGUAGE_TO_SCRIPT.get(macLang)
    if macLang is not None and macScript is not None:
        encoding = getEncoding(1, macScript, macLang, default="ascii")
        # Check if we can actually encode this name. If we can't,
        # for example because we have no support for the legacy
        # encoding, or because the name string contains Unicode
        # characters that the legacy encoding cannot represent,
        # we fall back to encoding the name in Unicode and put
        # the language tag into the ltag table.
        try:
            _ = tobytes(name, encoding, errors="strict")
            return makeName(name, nameID, 1, macScript, macLang)
        except UnicodeEncodeError:
            pass
    if font is not None:
        ltag = font.tables.get("ltag")
        if ltag is None:
            ltag = font["ltag"] = newTable("ltag")
        # 0 = Unicode; 4 = “Unicode 2.0 or later semantics (non-BMP characters allowed)”
        # “The preferred platform-specific code for Unicode would be 3 or 4.”
        # https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6name.html
        return makeName(name, nameID, 0, 4, ltag.addTag(language))
    else:
        log.warning(
            "cannot store language %s into 'ltag' table "
            "without having access to the TTFont object" % language
        )
        return None


class NameRecord(object):
    def getEncoding(self, default="ascii"):
        """Returns the Python encoding name for this name entry based on its platformID,
        platEncID, and langID.  If encoding for these values is not known, by default
        'ascii' is returned.  That can be overriden by passing a value to the default
        argument.
        """
        return getEncoding(self.platformID, self.platEncID, self.langID, default)

    def encodingIsUnicodeCompatible(self):
        return self.getEncoding(None) in ["utf_16_be", "ucs2be", "ascii", "latin1"]

    def __str__(self):
        return self.toStr(errors="backslashreplace")

    def isUnicode(self):
        return self.platformID == 0 or (
            self.platformID == 3 and self.platEncID in [0, 1, 10]
        )

    def toUnicode(self, errors: str = "strict") -> str:
        """
        If self.string is a Unicode string, return it; otherwise try decoding the
        bytes in self.string to a Unicode string using the encoding of this
        entry as returned by self.getEncoding(); Note that  self.getEncoding()
        returns 'ascii' if the encoding is unknown to the library.

        Certain heuristics are performed to recover data from bytes that are
        ill-formed in the chosen encoding, or that otherwise look misencoded
        (mostly around bad UTF-16BE encoded bytes, or bytes that look like UTF-16BE
        but marked otherwise).  If the bytes are ill-formed and the heuristics fail,
        the error is handled according to the errors parameter to this function, which is
        passed to the underlying decode() function; by default it throws a
        UnicodeDecodeError exception.

        Note: The mentioned heuristics mean that roundtripping a font to XML and back
        to binary might recover some misencoded data whereas just loading the font
        and saving it back will not change them.
        """

        def isascii(b: int) -> bool:
            return (b >= 0x20 and b <= 0x7E) or b in [0x09, 0x0A, 0x0D]

        encoding = self.getEncoding()
        string = self.string

        if (
            isinstance(string, bytes)
            and encoding == "utf_16_be"
            and len(string) % 2 == 1
        ):
            # Recover badly encoded UTF-16 strings that have an odd number of bytes:
            # - If the last byte is zero, drop it.  Otherwise,
            # - If all the odd bytes are zero and all the even bytes are ASCII,
            #   prepend one zero byte.  Otherwise,
            # - If first byte is zero and all other bytes are ASCII, insert zero
            #   bytes between consecutive ASCII bytes.
            #
            # (Yes, I've seen all of these in the wild... sigh)
            if byteord(string[-1]) == 0:
                string = string[:-1]
            elif all(
                byteord(b) == 0 if i % 2 else isascii(byteord(b))
                for i, b in enumerate(string)
            ):
                string = b"\0" + string
            elif byteord(string[0]) == 0 and all(
                isascii(byteord(b)) for b in string[1:]
            ):
                string = bytesjoin(b"\0" + bytechr(byteord(b)) for b in string[1:])

        string = tostr(string, encoding=encoding, errors=errors)

        # If decoded strings still looks like UTF-16BE, it suggests a double-encoding.
        # Fix it up.
        if all(
            ord(c) == 0 if i % 2 == 0 else isascii(ord(c)) for i, c in enumerate(string)
        ):
            # If string claims to be Mac encoding, but looks like UTF-16BE with ASCII text,
            # narrow it down.
            string = "".join(c for c in string[1::2])

        return string

    def toBytes(self, errors="strict"):
        """If self.string is a bytes object, return it; otherwise try encoding
        the Unicode string in self.string to bytes using the encoding of this
        entry as returned by self.getEncoding(); Note that self.getEncoding()
        returns 'ascii' if the encoding is unknown to the library.

        If the Unicode string cannot be encoded to bytes in the chosen encoding,
        the error is handled according to the errors parameter to this function,
        which is passed to the underlying encode() function; by default it throws a
        UnicodeEncodeError exception.
        """
        return tobytes(self.string, encoding=self.getEncoding(), errors=errors)

    toStr = toUnicode

    def toXML(self, writer, ttFont):
        try:
            unistr = self.toUnicode()
        except UnicodeDecodeError:
            unistr = None
        attrs = [
            ("nameID", self.nameID),
            ("platformID", self.platformID),
            ("platEncID", self.platEncID),
            ("langID", hex(self.langID)),
        ]

        if unistr is None or not self.encodingIsUnicodeCompatible():
            attrs.append(("unicode", unistr is not None))

        writer.begintag("namerecord", attrs)
        writer.newline()
        if unistr is not None:
            writer.write(unistr)
        else:
            writer.write8bit(self.string)
        writer.newline()
        writer.endtag("namerecord")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        self.nameID = safeEval(attrs["nameID"])
        self.platformID = safeEval(attrs["platformID"])
        self.platEncID = safeEval(attrs["platEncID"])
        self.langID = safeEval(attrs["langID"])
        s = strjoin(content).strip()
        encoding = self.getEncoding()
        if self.encodingIsUnicodeCompatible() or safeEval(
            attrs.get("unicode", "False")
        ):
            self.string = s.encode(encoding)
        else:
            # This is the inverse of write8bit...
            self.string = s.encode("latin1")

    def __lt__(self, other):
        if type(self) != type(other):
            return NotImplemented

        try:
            selfTuple = (
                self.platformID,
                self.platEncID,
                self.langID,
                self.nameID,
            )
            otherTuple = (
                other.platformID,
                other.platEncID,
                other.langID,
                other.nameID,
            )
        except AttributeError:
            # This can only happen for
            # 1) an object that is not a NameRecord, or
            # 2) an unlikely incomplete NameRecord object which has not been
            #    fully populated
            return NotImplemented

        try:
            # Include the actual NameRecord string in the comparison tuples
            selfTuple = selfTuple + (self.toBytes(),)
            otherTuple = otherTuple + (other.toBytes(),)
        except UnicodeEncodeError as e:
            # toBytes caused an encoding error in either of the two, so content
            # to sorting based on IDs only
            log.error("NameRecord sorting failed to encode: %s" % e)

        # Implemented so that list.sort() sorts according to the spec by using
        # the order of the tuple items and their comparison
        return selfTuple < otherTuple

    def __repr__(self):
        return "<NameRecord NameID=%d; PlatformID=%d; LanguageID=%d>" % (
            self.nameID,
            self.platformID,
            self.langID,
        )


# Windows language ID → IETF BCP-47 language tag
#
# While Microsoft indicates a region/country for all its language
# IDs, we follow Unicode practice by omitting “most likely subtags”
# as per Unicode CLDR. For example, English is simply “en” and not
# “en-Latn” because according to Unicode, the default script
# for English is Latin.
#
# http://www.unicode.org/cldr/charts/latest/supplemental/likely_subtags.html
# http://www.iana.org/assignments/language-subtag-registry/language-subtag-registry
_WINDOWS_LANGUAGES = {
    0x0436: "af",
    0x041C: "sq",
    0x0484: "gsw",
    0x045E: "am",
    0x1401: "ar-DZ",
    0x3C01: "ar-BH",
    0x0C01: "ar",
    0x0801: "ar-IQ",
    0x2C01: "ar-JO",
    0x3401: "ar-KW",
    0x3001: "ar-LB",
    0x1001: "ar-LY",
    0x1801: "ary",
    0x2001: "ar-OM",
    0x4001: "ar-QA",
    0x0401: "ar-SA",
    0x2801: "ar-SY",
    0x1C01: "aeb",
    0x3801: "ar-AE",
    0x2401: "ar-YE",
    0x042B: "hy",
    0x044D: "as",
    0x082C: "az-Cyrl",
    0x042C: "az",
    0x046D: "ba",
    0x042D: "eu",
    0x0423: "be",
    0x0845: "bn",
    0x0445: "bn-IN",
    0x201A: "bs-Cyrl",
    0x141A: "bs",
    0x047E: "br",
    0x0402: "bg",
    0x0403: "ca",
    0x0C04: "zh-HK",
    0x1404: "zh-MO",
    0x0804: "zh",
    0x1004: "zh-SG",
    0x0404: "zh-TW",
    0x0483: "co",
    0x041A: "hr",
    0x101A: "hr-BA",
    0x0405: "cs",
    0x0406: "da",
    0x048C: "prs",
    0x0465: "dv",
    0x0813: "nl-BE",
    0x0413: "nl",
    0x0C09: "en-AU",
    0x2809: "en-BZ",
    0x1009: "en-CA",
    0x2409: "en-029",
    0x4009: "en-IN",
    0x1809: "en-IE",
    0x2009: "en-JM",
    0x4409: "en-MY",
    0x1409: "en-NZ",
    0x3409: "en-PH",
    0x4809: "en-SG",
    0x1C09: "en-ZA",
    0x2C09: "en-TT",
    0x0809: "en-GB",
    0x0409: "en",
    0x3009: "en-ZW",
    0x0425: "et",
    0x0438: "fo",
    0x0464: "fil",
    0x040B: "fi",
    0x080C: "fr-BE",
    0x0C0C: "fr-CA",
    0x040C: "fr",
    0x140C: "fr-LU",
    0x180C: "fr-MC",
    0x100C: "fr-CH",
    0x0462: "fy",
    0x0456: "gl",
    0x0437: "ka",
    0x0C07: "de-AT",
    0x0407: "de",
    0x1407: "de-LI",
    0x1007: "de-LU",
    0x0807: "de-CH",
    0x0408: "el",
    0x046F: "kl",
    0x0447: "gu",
    0x0468: "ha",
    0x040D: "he",
    0x0439: "hi",
    0x040E: "hu",
    0x040F: "is",
    0x0470: "ig",
    0x0421: "id",
    0x045D: "iu",
    0x085D: "iu-Latn",
    0x083C: "ga",
    0x0434: "xh",
    0x0435: "zu",
    0x0410: "it",
    0x0810: "it-CH",
    0x0411: "ja",
    0x044B: "kn",
    0x043F: "kk",
    0x0453: "km",
    0x0486: "quc",
    0x0487: "rw",
    0x0441: "sw",
    0x0457: "kok",
    0x0412: "ko",
    0x0440: "ky",
    0x0454: "lo",
    0x0426: "lv",
    0x0427: "lt",
    0x082E: "dsb",
    0x046E: "lb",
    0x042F: "mk",
    0x083E: "ms-BN",
    0x043E: "ms",
    0x044C: "ml",
    0x043A: "mt",
    0x0481: "mi",
    0x047A: "arn",
    0x044E: "mr",
    0x047C: "moh",
    0x0450: "mn",
    0x0850: "mn-CN",
    0x0461: "ne",
    0x0414: "nb",
    0x0814: "nn",
    0x0482: "oc",
    0x0448: "or",
    0x0463: "ps",
    0x0415: "pl",
    0x0416: "pt",
    0x0816: "pt-PT",
    0x0446: "pa",
    0x046B: "qu-BO",
    0x086B: "qu-EC",
    0x0C6B: "qu",
    0x0418: "ro",
    0x0417: "rm",
    0x0419: "ru",
    0x243B: "smn",
    0x103B: "smj-NO",
    0x143B: "smj",
    0x0C3B: "se-FI",
    0x043B: "se",
    0x083B: "se-SE",
    0x203B: "sms",
    0x183B: "sma-NO",
    0x1C3B: "sms",
    0x044F: "sa",
    0x1C1A: "sr-Cyrl-BA",
    0x0C1A: "sr",
    0x181A: "sr-Latn-BA",
    0x081A: "sr-Latn",
    0x046C: "nso",
    0x0432: "tn",
    0x045B: "si",
    0x041B: "sk",
    0x0424: "sl",
    0x2C0A: "es-AR",
    0x400A: "es-BO",
    0x340A: "es-CL",
    0x240A: "es-CO",
    0x140A: "es-CR",
    0x1C0A: "es-DO",
    0x300A: "es-EC",
    0x440A: "es-SV",
    0x100A: "es-GT",
    0x480A: "es-HN",
    0x080A: "es-MX",
    0x4C0A: "es-NI",
    0x180A: "es-PA",
    0x3C0A: "es-PY",
    0x280A: "es-PE",
    0x500A: "es-PR",
    # Microsoft has defined two different language codes for
    # “Spanish with modern sorting” and “Spanish with traditional
    # sorting”. This makes sense for collation APIs, and it would be
    # possible to express this in BCP 47 language tags via Unicode
    # extensions (eg., “es-u-co-trad” is “Spanish with traditional
    # sorting”). However, for storing names in fonts, this distinction
    # does not make sense, so we use “es” in both cases.
    0x0C0A: "es",
    0x040A: "es",
    0x540A: "es-US",
    0x380A: "es-UY",
    0x200A: "es-VE",
    0x081D: "sv-FI",
    0x041D: "sv",
    0x045A: "syr",
    0x0428: "tg",
    0x085F: "tzm",
    0x0449: "ta",
    0x0444: "tt",
    0x044A: "te",
    0x041E: "th",
    0x0451: "bo",
    0x041F: "tr",
    0x0442: "tk",
    0x0480: "ug",
    0x0422: "uk",
    0x042E: "hsb",
    0x0420: "ur",
    0x0843: "uz-Cyrl",
    0x0443: "uz",
    0x042A: "vi",
    0x0452: "cy",
    0x0488: "wo",
    0x0485: "sah",
    0x0478: "ii",
    0x046A: "yo",
}


_MAC_LANGUAGES = {
    0: "en",
    1: "fr",
    2: "de",
    3: "it",
    4: "nl",
    5: "sv",
    6: "es",
    7: "da",
    8: "pt",
    9: "no",
    10: "he",
    11: "ja",
    12: "ar",
    13: "fi",
    14: "el",
    15: "is",
    16: "mt",
    17: "tr",
    18: "hr",
    19: "zh-Hant",
    20: "ur",
    21: "hi",
    22: "th",
    23: "ko",
    24: "lt",
    25: "pl",
    26: "hu",
    27: "es",
    28: "lv",
    29: "se",
    30: "fo",
    31: "fa",
    32: "ru",
    33: "zh",
    34: "nl-BE",
    35: "ga",
    36: "sq",
    37: "ro",
    38: "cz",
    39: "sk",
    40: "sl",
    41: "yi",
    42: "sr",
    43: "mk",
    44: "bg",
    45: "uk",
    46: "be",
    47: "uz",
    48: "kk",
    49: "az-Cyrl",
    50: "az-Arab",
    51: "hy",
    52: "ka",
    53: "mo",
    54: "ky",
    55: "tg",
    56: "tk",
    57: "mn-CN",
    58: "mn",
    59: "ps",
    60: "ks",
    61: "ku",
    62: "sd",
    63: "bo",
    64: "ne",
    65: "sa",
    66: "mr",
    67: "bn",
    68: "as",
    69: "gu",
    70: "pa",
    71: "or",
    72: "ml",
    73: "kn",
    74: "ta",
    75: "te",
    76: "si",
    77: "my",
    78: "km",
    79: "lo",
    80: "vi",
    81: "id",
    82: "tl",
    83: "ms",
    84: "ms-Arab",
    85: "am",
    86: "ti",
    87: "om",
    88: "so",
    89: "sw",
    90: "rw",
    91: "rn",
    92: "ny",
    93: "mg",
    94: "eo",
    128: "cy",
    129: "eu",
    130: "ca",
    131: "la",
    132: "qu",
    133: "gn",
    134: "ay",
    135: "tt",
    136: "ug",
    137: "dz",
    138: "jv",
    139: "su",
    140: "gl",
    141: "af",
    142: "br",
    143: "iu",
    144: "gd",
    145: "gv",
    146: "ga",
    147: "to",
    148: "el-polyton",
    149: "kl",
    150: "az",
    151: "nn",
}


_WINDOWS_LANGUAGE_CODES = {
    lang.lower(): code for code, lang in _WINDOWS_LANGUAGES.items()
}
_MAC_LANGUAGE_CODES = {lang.lower(): code for code, lang in _MAC_LANGUAGES.items()}


# MacOS language ID → MacOS script ID
#
# Note that the script ID is not sufficient to determine what encoding
# to use in TrueType files. For some languages, MacOS used a modification
# of a mainstream script. For example, an Icelandic name would be stored
# with smRoman in the TrueType naming table, but the actual encoding
# is a special Icelandic version of the normal Macintosh Roman encoding.
# As another example, Inuktitut uses an 8-bit encoding for Canadian Aboriginal
# Syllables but MacOS had run out of available script codes, so this was
# done as a (pretty radical) “modification” of Ethiopic.
#
# http://unicode.org/Public/MAPPINGS/VENDORS/APPLE/Readme.txt
_MAC_LANGUAGE_TO_SCRIPT = {
    0: 0,  # langEnglish → smRoman
    1: 0,  # langFrench → smRoman
    2: 0,  # langGerman → smRoman
    3: 0,  # langItalian → smRoman
    4: 0,  # langDutch → smRoman
    5: 0,  # langSwedish → smRoman
    6: 0,  # langSpanish → smRoman
    7: 0,  # langDanish → smRoman
    8: 0,  # langPortuguese → smRoman
    9: 0,  # langNorwegian → smRoman
    10: 5,  # langHebrew → smHebrew
    11: 1,  # langJapanese → smJapanese
    12: 4,  # langArabic → smArabic
    13: 0,  # langFinnish → smRoman
    14: 6,  # langGreek → smGreek
    15: 0,  # langIcelandic → smRoman (modified)
    16: 0,  # langMaltese → smRoman
    17: 0,  # langTurkish → smRoman (modified)
    18: 0,  # langCroatian → smRoman (modified)
    19: 2,  # langTradChinese → smTradChinese
    20: 4,  # langUrdu → smArabic
    21: 9,  # langHindi → smDevanagari
    22: 21,  # langThai → smThai
    23: 3,  # langKorean → smKorean
    24: 29,  # langLithuanian → smCentralEuroRoman
    25: 29,  # langPolish → smCentralEuroRoman
    26: 29,  # langHungarian → smCentralEuroRoman
    27: 29,  # langEstonian → smCentralEuroRoman
    28: 29,  # langLatvian → smCentralEuroRoman
    29: 0,  # langSami → smRoman
    30: 0,  # langFaroese → smRoman (modified)
    31: 4,  # langFarsi → smArabic (modified)
    32: 7,  # langRussian → smCyrillic
    33: 25,  # langSimpChinese → smSimpChinese
    34: 0,  # langFlemish → smRoman
    35: 0,  # langIrishGaelic → smRoman (modified)
    36: 0,  # langAlbanian → smRoman
    37: 0,  # langRomanian → smRoman (modified)
    38: 29,  # langCzech → smCentralEuroRoman
    39: 29,  # langSlovak → smCentralEuroRoman
    40: 0,  # langSlovenian → smRoman (modified)
    41: 5,  # langYiddish → smHebrew
    42: 7,  # langSerbian → smCyrillic
    43: 7,  # langMacedonian → smCyrillic
    44: 7,  # langBulgarian → smCyrillic
    45: 7,  # langUkrainian → smCyrillic (modified)
    46: 7,  # langByelorussian → smCyrillic
    47: 7,  # langUzbek → smCyrillic
    48: 7,  # langKazakh → smCyrillic
    49: 7,  # langAzerbaijani → smCyrillic
    50: 4,  # langAzerbaijanAr → smArabic
    51: 24,  # langArmenian → smArmenian
    52: 23,  # langGeorgian → smGeorgian
    53: 7,  # langMoldavian → smCyrillic
    54: 7,  # langKirghiz → smCyrillic
    55: 7,  # langTajiki → smCyrillic
    56: 7,  # langTurkmen → smCyrillic
    57: 27,  # langMongolian → smMongolian
    58: 7,  # langMongolianCyr → smCyrillic
    59: 4,  # langPashto → smArabic
    60: 4,  # langKurdish → smArabic
    61: 4,  # langKashmiri → smArabic
    62: 4,  # langSindhi → smArabic
    63: 26,  # langTibetan → smTibetan
    64: 9,  # langNepali → smDevanagari
    65: 9,  # langSanskrit → smDevanagari
    66: 9,  # langMarathi → smDevanagari
    67: 13,  # langBengali → smBengali
    68: 13,  # langAssamese → smBengali
    69: 11,  # langGujarati → smGujarati
    70: 10,  # langPunjabi → smGurmukhi
    71: 12,  # langOriya → smOriya
    72: 17,  # langMalayalam → smMalayalam
    73: 16,  # langKannada → smKannada
    74: 14,  # langTamil → smTamil
    75: 15,  # langTelugu → smTelugu
    76: 18,  # langSinhalese → smSinhalese
    77: 19,  # langBurmese → smBurmese
    78: 20,  # langKhmer → smKhmer
    79: 22,  # langLao → smLao
    80: 30,  # langVietnamese → smVietnamese
    81: 0,  # langIndonesian → smRoman
    82: 0,  # langTagalog → smRoman
    83: 0,  # langMalayRoman → smRoman
    84: 4,  # langMalayArabic → smArabic
    85: 28,  # langAmharic → smEthiopic
    86: 28,  # langTigrinya → smEthiopic
    87: 28,  # langOromo → smEthiopic
    88: 0,  # langSomali → smRoman
    89: 0,  # langSwahili → smRoman
    90: 0,  # langKinyarwanda → smRoman
    91: 0,  # langRundi → smRoman
    92: 0,  # langNyanja → smRoman
    93: 0,  # langMalagasy → smRoman
    94: 0,  # langEsperanto → smRoman
    128: 0,  # langWelsh → smRoman (modified)
    129: 0,  # langBasque → smRoman
    130: 0,  # langCatalan → smRoman
    131: 0,  # langLatin → smRoman
    132: 0,  # langQuechua → smRoman
    133: 0,  # langGuarani → smRoman
    134: 0,  # langAymara → smRoman
    135: 7,  # langTatar → smCyrillic
    136: 4,  # langUighur → smArabic
    137: 26,  # langDzongkha → smTibetan
    138: 0,  # langJavaneseRom → smRoman
    139: 0,  # langSundaneseRom → smRoman
    140: 0,  # langGalician → smRoman
    141: 0,  # langAfrikaans → smRoman
    142: 0,  # langBreton → smRoman (modified)
    143: 28,  # langInuktitut → smEthiopic (modified)
    144: 0,  # langScottishGaelic → smRoman (modified)
    145: 0,  # langManxGaelic → smRoman (modified)
    146: 0,  # langIrishGaelicScript → smRoman (modified)
    147: 0,  # langTongan → smRoman
    148: 6,  # langGreekAncient → smRoman
    149: 0,  # langGreenlandic → smRoman
    150: 0,  # langAzerbaijanRoman → smRoman
    151: 0,  # langNynorsk → smRoman
}


class NameRecordVisitor(TTVisitor):
    # Font tables that have NameIDs we need to collect.
    TABLES = ("GSUB", "GPOS", "fvar", "CPAL", "STAT")

    def __init__(self):
        self.seen = set()


@NameRecordVisitor.register_attrs(
    (
        (otTables.FeatureParamsSize, ("SubfamilyNameID",)),
        (otTables.FeatureParamsStylisticSet, ("UINameID",)),
        (otTables.STAT, ("ElidedFallbackNameID",)),
        (otTables.AxisRecord, ("AxisNameID",)),
        (otTables.AxisValue, ("ValueNameID",)),
        (otTables.FeatureName, ("FeatureNameID",)),
        (otTables.Setting, ("SettingNameID",)),
    )
)
def visit(visitor, obj, attr, value):
    visitor.seen.add(value)


@NameRecordVisitor.register(otTables.FeatureParamsCharacterVariants)
def visit(visitor, obj):
    for attr in ("FeatUILabelNameID", "FeatUITooltipTextNameID", "SampleTextNameID"):
        value = getattr(obj, attr)
        visitor.seen.add(value)
    # also include the sequence of UI strings for individual variants, if any
    if obj.FirstParamUILabelNameID == 0 or obj.NumNamedParameters == 0:
        return
    visitor.seen.update(
        range(
            obj.FirstParamUILabelNameID,
            obj.FirstParamUILabelNameID + obj.NumNamedParameters,
        )
    )


@NameRecordVisitor.register(ttLib.getTableClass("fvar"))
def visit(visitor, obj):
    for inst in obj.instances:
        if inst.postscriptNameID != 0xFFFF:
            visitor.seen.add(inst.postscriptNameID)
        visitor.seen.add(inst.subfamilyNameID)

    for axis in obj.axes:
        visitor.seen.add(axis.axisNameID)


@NameRecordVisitor.register(ttLib.getTableClass("CPAL"))
def visit(visitor, obj):
    if obj.version == 1:
        visitor.seen.update(obj.paletteLabels)
        visitor.seen.update(obj.paletteEntryLabels)


@NameRecordVisitor.register(ttLib.TTFont)
def visit(visitor, font, *args, **kwargs):
    if hasattr(visitor, "font"):
        return False

    visitor.font = font
    for tag in visitor.TABLES:
        if tag in font:
            visitor.visit(font[tag], *args, **kwargs)
    del visitor.font
    return False
