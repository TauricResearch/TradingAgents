"""Compiles/decompiles SVG table.

https://docs.microsoft.com/en-us/typography/opentype/spec/svg

The XML format is:

.. code-block:: xml

	<SVG>
		<svgDoc endGlyphID="1" startGlyphID="1">
			<![CDATA[ <complete SVG doc> ]]
		</svgDoc>
	...
		<svgDoc endGlyphID="n" startGlyphID="m">
			<![CDATA[ <complete SVG doc> ]]
		</svgDoc>
	</SVG>
"""

from fontTools.misc.textTools import bytesjoin, safeEval, strjoin, tobytes, tostr
from fontTools.misc import sstruct
from . import DefaultTable
from collections.abc import Sequence
from dataclasses import dataclass, astuple
from io import BytesIO
import struct
import logging


log = logging.getLogger(__name__)


SVG_format_0 = """
	>   # big endian
	version:                  H
	offsetToSVGDocIndex:      L
	reserved:                 L
"""

SVG_format_0Size = sstruct.calcsize(SVG_format_0)

doc_index_entry_format_0 = """
	>   # big endian
	startGlyphID:             H
	endGlyphID:               H
	svgDocOffset:             L
	svgDocLength:             L
"""

doc_index_entry_format_0Size = sstruct.calcsize(doc_index_entry_format_0)


class table_S_V_G_(DefaultTable.DefaultTable):
    """Scalable Vector Graphics table

    The ``SVG`` table contains representations for glyphs in the SVG
    image format.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/stat
    """

    def decompile(self, data, ttFont):
        self.docList = []
        # Version 0 is the standardized version of the table; and current.
        # https://www.microsoft.com/typography/otspec/svg.htm
        sstruct.unpack(SVG_format_0, data[:SVG_format_0Size], self)
        if self.version != 0:
            log.warning(
                "Unknown SVG table version '%s'. Decompiling as version 0.",
                self.version,
            )
        # read in SVG Documents Index
        # data starts with the first entry of the entry list.
        pos = subTableStart = self.offsetToSVGDocIndex
        self.numEntries = struct.unpack(">H", data[pos : pos + 2])[0]
        pos += 2
        if self.numEntries > 0:
            data2 = data[pos:]
            entries = []
            for i in range(self.numEntries):
                record_data = data2[
                    i
                    * doc_index_entry_format_0Size : (i + 1)
                    * doc_index_entry_format_0Size
                ]
                docIndexEntry = sstruct.unpack(
                    doc_index_entry_format_0, record_data, DocumentIndexEntry()
                )
                entries.append(docIndexEntry)

            for entry in entries:
                start = entry.svgDocOffset + subTableStart
                end = start + entry.svgDocLength
                doc = data[start:end]
                compressed = False
                if doc.startswith(b"\x1f\x8b"):
                    import gzip

                    bytesIO = BytesIO(doc)
                    with gzip.GzipFile(None, "r", fileobj=bytesIO) as gunzipper:
                        doc = gunzipper.read()
                    del bytesIO
                    compressed = True
                doc = tostr(doc, "utf_8")
                self.docList.append(
                    SVGDocument(doc, entry.startGlyphID, entry.endGlyphID, compressed)
                )

    def compile(self, ttFont):
        version = 0
        offsetToSVGDocIndex = (
            SVG_format_0Size  # I start the SVGDocIndex right after the header.
        )
        # get SGVDoc info.
        docList = []
        entryList = []
        numEntries = len(self.docList)
        datum = struct.pack(">H", numEntries)
        entryList.append(datum)
        curOffset = len(datum) + doc_index_entry_format_0Size * numEntries
        seenDocs = {}
        allCompressed = getattr(self, "compressed", False)
        for i, doc in enumerate(self.docList):
            if isinstance(doc, (list, tuple)):
                doc = SVGDocument(*doc)
                self.docList[i] = doc
            docBytes = tobytes(doc.data, encoding="utf_8")
            if (allCompressed or doc.compressed) and not docBytes.startswith(
                b"\x1f\x8b"
            ):
                import gzip

                bytesIO = BytesIO()
                # mtime=0 strips the useless timestamp and makes gzip output reproducible;
                # equivalent to `gzip -n`
                with gzip.GzipFile(None, "w", fileobj=bytesIO, mtime=0) as gzipper:
                    gzipper.write(docBytes)
                gzipped = bytesIO.getvalue()
                if len(gzipped) < len(docBytes):
                    docBytes = gzipped
                del gzipped, bytesIO
            docLength = len(docBytes)
            if docBytes in seenDocs:
                docOffset = seenDocs[docBytes]
            else:
                docOffset = curOffset
                curOffset += docLength
                seenDocs[docBytes] = docOffset
                docList.append(docBytes)
            entry = struct.pack(
                ">HHLL", doc.startGlyphID, doc.endGlyphID, docOffset, docLength
            )
            entryList.append(entry)
        entryList.extend(docList)
        svgDocData = bytesjoin(entryList)

        reserved = 0
        header = struct.pack(">HLL", version, offsetToSVGDocIndex, reserved)
        data = [header, svgDocData]
        data = bytesjoin(data)
        return data

    def toXML(self, writer, ttFont):
        for i, doc in enumerate(self.docList):
            if isinstance(doc, (list, tuple)):
                doc = SVGDocument(*doc)
                self.docList[i] = doc
            attrs = {"startGlyphID": doc.startGlyphID, "endGlyphID": doc.endGlyphID}
            if doc.compressed:
                attrs["compressed"] = 1
            writer.begintag("svgDoc", **attrs)
            writer.newline()
            writer.writecdata(doc.data)
            writer.newline()
            writer.endtag("svgDoc")
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "svgDoc":
            if not hasattr(self, "docList"):
                self.docList = []
            doc = strjoin(content)
            doc = doc.strip()
            startGID = int(attrs["startGlyphID"])
            endGID = int(attrs["endGlyphID"])
            compressed = bool(safeEval(attrs.get("compressed", "0")))
            self.docList.append(SVGDocument(doc, startGID, endGID, compressed))
        else:
            log.warning("Unknown %s %s", name, content)


class DocumentIndexEntry(object):
    def __init__(self):
        self.startGlyphID = None  # USHORT
        self.endGlyphID = None  # USHORT
        self.svgDocOffset = None  # ULONG
        self.svgDocLength = None  # ULONG

    def __repr__(self):
        return (
            "startGlyphID: %s, endGlyphID: %s, svgDocOffset: %s, svgDocLength: %s"
            % (self.startGlyphID, self.endGlyphID, self.svgDocOffset, self.svgDocLength)
        )


@dataclass
class SVGDocument(Sequence):
    data: str
    startGlyphID: int
    endGlyphID: int
    compressed: bool = False

    # Previously, the SVG table's docList attribute contained a lists of 3 items:
    # [doc, startGlyphID, endGlyphID]; later, we added a `compressed` attribute.
    # For backward compatibility with code that depends of them being sequences of
    # fixed length=3, we subclass the Sequence abstract base class and pretend only
    # the first three items are present. 'compressed' is only accessible via named
    # attribute lookup like regular dataclasses: i.e. `doc.compressed`, not `doc[3]`
    def __getitem__(self, index):
        return astuple(self)[:3][index]

    def __len__(self):
        return 3
