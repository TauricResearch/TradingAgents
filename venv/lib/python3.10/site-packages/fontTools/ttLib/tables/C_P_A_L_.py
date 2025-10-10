# Copyright 2013 Google, Inc. All Rights Reserved.
#
# Google Author(s): Behdad Esfahbod

from fontTools.misc.textTools import bytesjoin, safeEval
from . import DefaultTable
import array
from collections import namedtuple
import struct
import sys


class table_C_P_A_L_(DefaultTable.DefaultTable):
    """Color Palette table

    The ``CPAL`` table contains a set of one or more color palettes. The color
    records in each palette can be referenced by the ``COLR`` table to specify
    the colors used in a color glyph.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/cpal
    """

    NO_NAME_ID = 0xFFFF
    DEFAULT_PALETTE_TYPE = 0

    def __init__(self, tag=None):
        DefaultTable.DefaultTable.__init__(self, tag)
        self.palettes = []
        self.paletteTypes = []
        self.paletteLabels = []
        self.paletteEntryLabels = []

    def decompile(self, data, ttFont):
        (
            self.version,
            self.numPaletteEntries,
            numPalettes,
            numColorRecords,
            goffsetFirstColorRecord,
        ) = struct.unpack(">HHHHL", data[:12])
        assert (
            self.version <= 1
        ), "Version of CPAL table is higher than I know how to handle"
        self.palettes = []
        pos = 12
        for i in range(numPalettes):
            startIndex = struct.unpack(">H", data[pos : pos + 2])[0]
            assert startIndex + self.numPaletteEntries <= numColorRecords
            pos += 2
            palette = []
            ppos = goffsetFirstColorRecord + startIndex * 4
            for j in range(self.numPaletteEntries):
                palette.append(Color(*struct.unpack(">BBBB", data[ppos : ppos + 4])))
                ppos += 4
            self.palettes.append(palette)
        if self.version == 0:
            offsetToPaletteTypeArray = 0
            offsetToPaletteLabelArray = 0
            offsetToPaletteEntryLabelArray = 0
        else:
            pos = 12 + numPalettes * 2
            (
                offsetToPaletteTypeArray,
                offsetToPaletteLabelArray,
                offsetToPaletteEntryLabelArray,
            ) = struct.unpack(">LLL", data[pos : pos + 12])
        self.paletteTypes = self._decompileUInt32Array(
            data,
            offsetToPaletteTypeArray,
            numPalettes,
            default=self.DEFAULT_PALETTE_TYPE,
        )
        self.paletteLabels = self._decompileUInt16Array(
            data, offsetToPaletteLabelArray, numPalettes, default=self.NO_NAME_ID
        )
        self.paletteEntryLabels = self._decompileUInt16Array(
            data,
            offsetToPaletteEntryLabelArray,
            self.numPaletteEntries,
            default=self.NO_NAME_ID,
        )

    def _decompileUInt16Array(self, data, offset, numElements, default=0):
        if offset == 0:
            return [default] * numElements
        result = array.array("H", data[offset : offset + 2 * numElements])
        if sys.byteorder != "big":
            result.byteswap()
        assert len(result) == numElements, result
        return result.tolist()

    def _decompileUInt32Array(self, data, offset, numElements, default=0):
        if offset == 0:
            return [default] * numElements
        result = array.array("I", data[offset : offset + 4 * numElements])
        if sys.byteorder != "big":
            result.byteswap()
        assert len(result) == numElements, result
        return result.tolist()

    def compile(self, ttFont):
        colorRecordIndices, colorRecords = self._compileColorRecords()
        paletteTypes = self._compilePaletteTypes()
        paletteLabels = self._compilePaletteLabels()
        paletteEntryLabels = self._compilePaletteEntryLabels()
        numColorRecords = len(colorRecords) // 4
        offsetToFirstColorRecord = 12 + len(colorRecordIndices)
        if self.version >= 1:
            offsetToFirstColorRecord += 12
        header = struct.pack(
            ">HHHHL",
            self.version,
            self.numPaletteEntries,
            len(self.palettes),
            numColorRecords,
            offsetToFirstColorRecord,
        )
        if self.version == 0:
            dataList = [header, colorRecordIndices, colorRecords]
        else:
            pos = offsetToFirstColorRecord + len(colorRecords)
            if len(paletteTypes) == 0:
                offsetToPaletteTypeArray = 0
            else:
                offsetToPaletteTypeArray = pos
                pos += len(paletteTypes)
            if len(paletteLabels) == 0:
                offsetToPaletteLabelArray = 0
            else:
                offsetToPaletteLabelArray = pos
                pos += len(paletteLabels)
            if len(paletteEntryLabels) == 0:
                offsetToPaletteEntryLabelArray = 0
            else:
                offsetToPaletteEntryLabelArray = pos
                pos += len(paletteLabels)
            header1 = struct.pack(
                ">LLL",
                offsetToPaletteTypeArray,
                offsetToPaletteLabelArray,
                offsetToPaletteEntryLabelArray,
            )
            dataList = [
                header,
                colorRecordIndices,
                header1,
                colorRecords,
                paletteTypes,
                paletteLabels,
                paletteEntryLabels,
            ]
        return bytesjoin(dataList)

    def _compilePalette(self, palette):
        assert len(palette) == self.numPaletteEntries
        pack = lambda c: struct.pack(">BBBB", c.blue, c.green, c.red, c.alpha)
        return bytesjoin([pack(color) for color in palette])

    def _compileColorRecords(self):
        colorRecords, colorRecordIndices, pool = [], [], {}
        for palette in self.palettes:
            packedPalette = self._compilePalette(palette)
            if packedPalette in pool:
                index = pool[packedPalette]
            else:
                index = len(colorRecords)
                colorRecords.append(packedPalette)
                pool[packedPalette] = index
            colorRecordIndices.append(struct.pack(">H", index * self.numPaletteEntries))
        return bytesjoin(colorRecordIndices), bytesjoin(colorRecords)

    def _compilePaletteTypes(self):
        if self.version == 0 or not any(self.paletteTypes):
            return b""
        assert len(self.paletteTypes) == len(self.palettes)
        result = bytesjoin([struct.pack(">I", ptype) for ptype in self.paletteTypes])
        assert len(result) == 4 * len(self.palettes)
        return result

    def _compilePaletteLabels(self):
        if self.version == 0 or all(l == self.NO_NAME_ID for l in self.paletteLabels):
            return b""
        assert len(self.paletteLabels) == len(self.palettes)
        result = bytesjoin([struct.pack(">H", label) for label in self.paletteLabels])
        assert len(result) == 2 * len(self.palettes)
        return result

    def _compilePaletteEntryLabels(self):
        if self.version == 0 or all(
            l == self.NO_NAME_ID for l in self.paletteEntryLabels
        ):
            return b""
        assert len(self.paletteEntryLabels) == self.numPaletteEntries
        result = bytesjoin(
            [struct.pack(">H", label) for label in self.paletteEntryLabels]
        )
        assert len(result) == 2 * self.numPaletteEntries
        return result

    def toXML(self, writer, ttFont):
        numPalettes = len(self.palettes)
        paletteLabels = {i: nameID for (i, nameID) in enumerate(self.paletteLabels)}
        paletteTypes = {i: typ for (i, typ) in enumerate(self.paletteTypes)}
        writer.simpletag("version", value=self.version)
        writer.newline()
        writer.simpletag("numPaletteEntries", value=self.numPaletteEntries)
        writer.newline()
        for index, palette in enumerate(self.palettes):
            attrs = {"index": index}
            paletteType = paletteTypes.get(index, self.DEFAULT_PALETTE_TYPE)
            paletteLabel = paletteLabels.get(index, self.NO_NAME_ID)
            if self.version > 0 and paletteLabel != self.NO_NAME_ID:
                attrs["label"] = paletteLabel
            if self.version > 0 and paletteType != self.DEFAULT_PALETTE_TYPE:
                attrs["type"] = paletteType
            writer.begintag("palette", **attrs)
            writer.newline()
            if (
                self.version > 0
                and paletteLabel != self.NO_NAME_ID
                and ttFont
                and "name" in ttFont
            ):
                name = ttFont["name"].getDebugName(paletteLabel)
                if name is not None:
                    writer.comment(name)
                    writer.newline()
            assert len(palette) == self.numPaletteEntries
            for cindex, color in enumerate(palette):
                color.toXML(writer, ttFont, cindex)
            writer.endtag("palette")
            writer.newline()
        if self.version > 0 and not all(
            l == self.NO_NAME_ID for l in self.paletteEntryLabels
        ):
            writer.begintag("paletteEntryLabels")
            writer.newline()
            for index, label in enumerate(self.paletteEntryLabels):
                if label != self.NO_NAME_ID:
                    writer.simpletag("label", index=index, value=label)
                    if self.version > 0 and label and ttFont and "name" in ttFont:
                        name = ttFont["name"].getDebugName(label)
                        if name is not None:
                            writer.comment(name)
                    writer.newline()
            writer.endtag("paletteEntryLabels")
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "palette":
            self.paletteLabels.append(int(attrs.get("label", self.NO_NAME_ID)))
            self.paletteTypes.append(int(attrs.get("type", self.DEFAULT_PALETTE_TYPE)))
            palette = []
            for element in content:
                if isinstance(element, str):
                    continue
                attrs = element[1]
                color = Color.fromHex(attrs["value"])
                palette.append(color)
            self.palettes.append(palette)
        elif name == "paletteEntryLabels":
            colorLabels = {}
            for element in content:
                if isinstance(element, str):
                    continue
                elementName, elementAttr, _ = element
                if elementName == "label":
                    labelIndex = safeEval(elementAttr["index"])
                    nameID = safeEval(elementAttr["value"])
                    colorLabels[labelIndex] = nameID
            self.paletteEntryLabels = [
                colorLabels.get(i, self.NO_NAME_ID)
                for i in range(self.numPaletteEntries)
            ]
        elif "value" in attrs:
            value = safeEval(attrs["value"])
            setattr(self, name, value)
            if name == "numPaletteEntries":
                self.paletteEntryLabels = [self.NO_NAME_ID] * self.numPaletteEntries


class Color(namedtuple("Color", "blue green red alpha")):
    def hex(self):
        return "#%02X%02X%02X%02X" % (self.red, self.green, self.blue, self.alpha)

    def __repr__(self):
        return self.hex()

    def toXML(self, writer, ttFont, index=None):
        writer.simpletag("color", value=self.hex(), index=index)
        writer.newline()

    @classmethod
    def fromHex(cls, value):
        if value[0] == "#":
            value = value[1:]
        red = int(value[0:2], 16)
        green = int(value[2:4], 16)
        blue = int(value[4:6], 16)
        alpha = int(value[6:8], 16) if len(value) >= 8 else 0xFF
        return cls(red=red, green=green, blue=blue, alpha=alpha)

    @classmethod
    def fromRGBA(cls, red, green, blue, alpha):
        return cls(red=red, green=green, blue=blue, alpha=alpha)
