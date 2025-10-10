from fontTools.ttLib.ttFont import TTFont
from fontTools.ttLib.sfnt import readTTCHeader, writeTTCHeader
from io import BytesIO
import struct
import logging

log = logging.getLogger(__name__)


class TTCollection(object):
    """Object representing a TrueType Collection / OpenType Collection.
    The main API is self.fonts being a list of TTFont instances.

    If shareTables is True, then different fonts in the collection
    might point to the same table object if the data for the table was
    the same in the font file.  Note, however, that this might result
    in suprises and incorrect behavior if the different fonts involved
    have different GlyphOrder.  Use only if you know what you are doing.
    """

    def __init__(self, file=None, shareTables=False, **kwargs):
        fonts = self.fonts = []
        if file is None:
            return

        assert "fontNumber" not in kwargs, kwargs

        closeStream = False
        if not hasattr(file, "read"):
            file = open(file, "rb")
            closeStream = True

        tableCache = {} if shareTables else None

        header = readTTCHeader(file)
        for i in range(header.numFonts):
            font = TTFont(file, fontNumber=i, _tableCache=tableCache, **kwargs)
            fonts.append(font)

        # don't close file if lazy=True, as the TTFont hold a reference to the original
        # file; the file will be closed once the TTFonts are closed in the
        # TTCollection.close(). We still want to close the file if lazy is None or
        # False, because in that case the TTFont no longer need the original file
        # and we want to avoid 'ResourceWarning: unclosed file'.
        if not kwargs.get("lazy") and closeStream:
            file.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def close(self):
        for font in self.fonts:
            font.close()

    def save(self, file, shareTables=True):
        """Save the font to disk. Similarly to the constructor,
        the 'file' argument can be either a pathname or a writable
        file object.
        """
        if not hasattr(file, "write"):
            final = None
            file = open(file, "wb")
        else:
            # assume "file" is a writable file object
            # write to a temporary stream to allow saving to unseekable streams
            final = file
            file = BytesIO()

        tableCache = {} if shareTables else None

        offsets_offset = writeTTCHeader(file, len(self.fonts))
        offsets = []
        for font in self.fonts:
            offsets.append(file.tell())
            font._save(file, tableCache=tableCache)
            file.seek(0, 2)

        file.seek(offsets_offset)
        file.write(struct.pack(">%dL" % len(self.fonts), *offsets))

        if final:
            final.write(file.getvalue())
        file.close()

    def saveXML(self, fileOrPath, newlinestr="\n", writeVersion=True, **kwargs):
        from fontTools.misc import xmlWriter

        writer = xmlWriter.XMLWriter(fileOrPath, newlinestr=newlinestr)

        if writeVersion:
            from fontTools import version

            version = ".".join(version.split(".")[:2])
            writer.begintag("ttCollection", ttLibVersion=version)
        else:
            writer.begintag("ttCollection")
        writer.newline()
        writer.newline()

        for font in self.fonts:
            font._saveXML(writer, writeVersion=False, **kwargs)
            writer.newline()

        writer.endtag("ttCollection")
        writer.newline()

        writer.close()

    def __getitem__(self, item):
        return self.fonts[item]

    def __setitem__(self, item, value):
        self.fonts[item] = value

    def __delitem__(self, item):
        return self.fonts[item]

    def __len__(self):
        return len(self.fonts)

    def __iter__(self):
        return iter(self.fonts)
