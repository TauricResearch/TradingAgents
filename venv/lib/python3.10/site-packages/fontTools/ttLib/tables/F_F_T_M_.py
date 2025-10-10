from fontTools.misc import sstruct
from fontTools.misc.textTools import safeEval
from fontTools.misc.timeTools import timestampFromString, timestampToString
from . import DefaultTable

FFTMFormat = """
		>	# big endian
		version:        I
		FFTimeStamp:    Q
		sourceCreated:  Q
		sourceModified: Q
"""


class table_F_F_T_M_(DefaultTable.DefaultTable):
    """FontForge Time Stamp table

    The ``FFTM`` table is used by the free-software font editor
    FontForge to record timestamps for the creation and modification
    of font source (.sfd) files and a timestamp for FontForge's
    own source code.

    See also https://fontforge.org/docs/techref/non-standard.html
    """

    def decompile(self, data, ttFont):
        dummy, rest = sstruct.unpack2(FFTMFormat, data, self)

    def compile(self, ttFont):
        data = sstruct.pack(FFTMFormat, self)
        return data

    def toXML(self, writer, ttFont):
        writer.comment(
            "FontForge's timestamp, font source creation and modification dates"
        )
        writer.newline()
        formatstring, names, fixes = sstruct.getformat(FFTMFormat)
        for name in names:
            value = getattr(self, name)
            if name in ("FFTimeStamp", "sourceCreated", "sourceModified"):
                value = timestampToString(value)
            writer.simpletag(name, value=value)
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        value = attrs["value"]
        if name in ("FFTimeStamp", "sourceCreated", "sourceModified"):
            value = timestampFromString(value)
        else:
            value = safeEval(value)
        setattr(self, name, value)
