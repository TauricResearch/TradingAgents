""" TSI{0,1,2,3,5} are private tables used by Microsoft Visual TrueType (VTT)
tool to store its hinting source data.

TSI1 contains the text of the glyph programs in the form of low-level assembly
code, as well as the 'extra' programs 'fpgm', 'ppgm' (i.e. 'prep'), and 'cvt'.

See also https://learn.microsoft.com/en-us/typography/tools/vtt/tsi-tables
"""

from . import DefaultTable
from fontTools.misc.loggingTools import LogMixin
from fontTools.misc.textTools import strjoin, tobytes, tostr


class table_T_S_I__1(LogMixin, DefaultTable.DefaultTable):
    extras = {0xFFFA: "ppgm", 0xFFFB: "cvt", 0xFFFC: "reserved", 0xFFFD: "fpgm"}

    indextable = "TSI0"

    def decompile(self, data, ttFont):
        totalLength = len(data)
        indextable = ttFont[self.indextable]
        for indices, isExtra in zip(
            (indextable.indices, indextable.extra_indices), (False, True)
        ):
            programs = {}
            for i, (glyphID, textLength, textOffset) in enumerate(indices):
                if isExtra:
                    name = self.extras[glyphID]
                else:
                    name = ttFont.getGlyphName(glyphID)
                if textOffset > totalLength:
                    self.log.warning("textOffset > totalLength; %r skipped" % name)
                    continue
                if textLength < 0x8000:
                    # If the length stored in the record is less than 32768, then use
                    # that as the length of the record.
                    pass
                elif textLength == 0x8000:
                    # If the length is 32768, compute the actual length as follows:
                    isLast = i == (len(indices) - 1)
                    if isLast:
                        if isExtra:
                            # For the last "extra" record (the very last record of the
                            # table), the length is the difference between the total
                            # length of the TSI1 table and the textOffset of the final
                            # record.
                            nextTextOffset = totalLength
                        else:
                            # For the last "normal" record (the last record just prior
                            # to the record containing the "magic number"), the length
                            # is the difference between the textOffset of the record
                            # following the "magic number" (0xFFFE) record (i.e. the
                            # first "extra" record), and the textOffset of the last
                            # "normal" record.
                            nextTextOffset = indextable.extra_indices[0][2]
                    else:
                        # For all other records with a length of 0x8000, the length is
                        # the difference between the textOffset of the record in
                        # question and the textOffset of the next record.
                        nextTextOffset = indices[i + 1][2]
                    assert nextTextOffset >= textOffset, "entries not sorted by offset"
                    if nextTextOffset > totalLength:
                        self.log.warning(
                            "nextTextOffset > totalLength; %r truncated" % name
                        )
                        nextTextOffset = totalLength
                    textLength = nextTextOffset - textOffset
                else:
                    from fontTools import ttLib

                    raise ttLib.TTLibError(
                        "%r textLength (%d) must not be > 32768" % (name, textLength)
                    )
                text = data[textOffset : textOffset + textLength]
                assert len(text) == textLength
                text = tostr(text, encoding="utf-8")
                if text:
                    programs[name] = text
            if isExtra:
                self.extraPrograms = programs
            else:
                self.glyphPrograms = programs

    def compile(self, ttFont):
        if not hasattr(self, "glyphPrograms"):
            self.glyphPrograms = {}
            self.extraPrograms = {}
        data = b""
        indextable = ttFont[self.indextable]
        glyphNames = ttFont.getGlyphOrder()

        indices = []
        for i, name in enumerate(glyphNames):
            if len(data) % 2:
                data = (
                    data + b"\015"
                )  # align on 2-byte boundaries, fill with return chars. Yum.
            if name in self.glyphPrograms:
                text = tobytes(self.glyphPrograms[name], encoding="utf-8")
            else:
                text = b""
            textLength = len(text)
            if textLength >= 0x8000:
                textLength = 0x8000
            indices.append((i, textLength, len(data)))
            data = data + text

        extra_indices = []
        for code, name in sorted(self.extras.items()):
            if len(data) % 2:
                data = (
                    data + b"\015"
                )  # align on 2-byte boundaries, fill with return chars.
            if name in self.extraPrograms:
                text = tobytes(self.extraPrograms[name], encoding="utf-8")
            else:
                text = b""
            textLength = len(text)
            if textLength >= 0x8000:
                textLength = 0x8000
            extra_indices.append((code, textLength, len(data)))
            data = data + text
        indextable.set(indices, extra_indices)
        return data

    def toXML(self, writer, ttFont):
        names = sorted(self.glyphPrograms.keys())
        writer.newline()
        for name in names:
            text = self.glyphPrograms[name]
            if not text:
                continue
            writer.begintag("glyphProgram", name=name)
            writer.newline()
            writer.write_noindent(text.replace("\r", "\n"))
            writer.newline()
            writer.endtag("glyphProgram")
            writer.newline()
            writer.newline()
        extra_names = sorted(self.extraPrograms.keys())
        for name in extra_names:
            text = self.extraPrograms[name]
            if not text:
                continue
            writer.begintag("extraProgram", name=name)
            writer.newline()
            writer.write_noindent(text.replace("\r", "\n"))
            writer.newline()
            writer.endtag("extraProgram")
            writer.newline()
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if not hasattr(self, "glyphPrograms"):
            self.glyphPrograms = {}
            self.extraPrograms = {}
        lines = strjoin(content).replace("\r", "\n").split("\n")
        text = "\r".join(lines[1:-1])
        if name == "glyphProgram":
            self.glyphPrograms[attrs["name"]] = text
        elif name == "extraProgram":
            self.extraPrograms[attrs["name"]] = text
