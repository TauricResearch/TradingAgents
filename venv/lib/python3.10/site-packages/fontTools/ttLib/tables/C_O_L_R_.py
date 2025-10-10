# Copyright 2013 Google, Inc. All Rights Reserved.
#
# Google Author(s): Behdad Esfahbod

from fontTools.misc.textTools import safeEval
from . import DefaultTable


class table_C_O_L_R_(DefaultTable.DefaultTable):
    """Color table

    The ``COLR`` table defines color presentation of outline glyphs. It must
    be used in concert with the ``CPAL`` table, which contains the color
    descriptors used.

    This table is structured so that you can treat it like a dictionary keyed by glyph name.

    ``ttFont['COLR'][<glyphName>]`` will return the color layers for any glyph.

    ``ttFont['COLR'][<glyphName>] = <value>`` will set the color layers for any glyph.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/colr
    """

    @staticmethod
    def _decompileColorLayersV0(table):
        if not table.LayerRecordArray:
            return {}
        colorLayerLists = {}
        layerRecords = table.LayerRecordArray.LayerRecord
        numLayerRecords = len(layerRecords)
        for baseRec in table.BaseGlyphRecordArray.BaseGlyphRecord:
            baseGlyph = baseRec.BaseGlyph
            firstLayerIndex = baseRec.FirstLayerIndex
            numLayers = baseRec.NumLayers
            assert firstLayerIndex + numLayers <= numLayerRecords
            layers = []
            for i in range(firstLayerIndex, firstLayerIndex + numLayers):
                layerRec = layerRecords[i]
                layers.append(LayerRecord(layerRec.LayerGlyph, layerRec.PaletteIndex))
            colorLayerLists[baseGlyph] = layers
        return colorLayerLists

    def _toOTTable(self, ttFont):
        from . import otTables
        from fontTools.colorLib.builder import populateCOLRv0

        tableClass = getattr(otTables, self.tableTag)
        table = tableClass()
        table.Version = self.version

        populateCOLRv0(
            table,
            {
                baseGlyph: [(layer.name, layer.colorID) for layer in layers]
                for baseGlyph, layers in self.ColorLayers.items()
            },
            glyphMap=ttFont.getReverseGlyphMap(rebuild=True),
        )
        return table

    def decompile(self, data, ttFont):
        from .otBase import OTTableReader
        from . import otTables

        # We use otData to decompile, but we adapt the decompiled otTables to the
        # existing COLR v0 API for backward compatibility.
        reader = OTTableReader(data, tableTag=self.tableTag)
        tableClass = getattr(otTables, self.tableTag)
        table = tableClass()
        table.decompile(reader, ttFont)

        self.version = table.Version
        if self.version == 0:
            self.ColorLayers = self._decompileColorLayersV0(table)
        else:
            # for new versions, keep the raw otTables around
            self.table = table

    def compile(self, ttFont):
        from .otBase import OTTableWriter

        if hasattr(self, "table"):
            table = self.table
        else:
            table = self._toOTTable(ttFont)

        writer = OTTableWriter(tableTag=self.tableTag)
        table.compile(writer, ttFont)
        return writer.getAllData()

    def toXML(self, writer, ttFont):
        if hasattr(self, "table"):
            self.table.toXML2(writer, ttFont)
        else:
            writer.simpletag("version", value=self.version)
            writer.newline()
            for baseGlyph in sorted(self.ColorLayers.keys(), key=ttFont.getGlyphID):
                writer.begintag("ColorGlyph", name=baseGlyph)
                writer.newline()
                for layer in self.ColorLayers[baseGlyph]:
                    layer.toXML(writer, ttFont)
                writer.endtag("ColorGlyph")
                writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "version":  # old COLR v0 API
            setattr(self, name, safeEval(attrs["value"]))
        elif name == "ColorGlyph":
            if not hasattr(self, "ColorLayers"):
                self.ColorLayers = {}
            glyphName = attrs["name"]
            for element in content:
                if isinstance(element, str):
                    continue
            layers = []
            for element in content:
                if isinstance(element, str):
                    continue
                layer = LayerRecord()
                layer.fromXML(element[0], element[1], element[2], ttFont)
                layers.append(layer)
            self.ColorLayers[glyphName] = layers
        else:  # new COLR v1 API
            from . import otTables

            if not hasattr(self, "table"):
                tableClass = getattr(otTables, self.tableTag)
                self.table = tableClass()
            self.table.fromXML(name, attrs, content, ttFont)
            self.table.populateDefaults()
            self.version = self.table.Version

    def __getitem__(self, glyphName):
        if not isinstance(glyphName, str):
            raise TypeError(f"expected str, found {type(glyphName).__name__}")
        return self.ColorLayers[glyphName]

    def __setitem__(self, glyphName, value):
        if not isinstance(glyphName, str):
            raise TypeError(f"expected str, found {type(glyphName).__name__}")
        if value is not None:
            self.ColorLayers[glyphName] = value
        elif glyphName in self.ColorLayers:
            del self.ColorLayers[glyphName]

    def __delitem__(self, glyphName):
        del self.ColorLayers[glyphName]


class LayerRecord(object):
    def __init__(self, name=None, colorID=None):
        self.name = name
        self.colorID = colorID

    def toXML(self, writer, ttFont):
        writer.simpletag("layer", name=self.name, colorID=self.colorID)
        writer.newline()

    def fromXML(self, eltname, attrs, content, ttFont):
        for name, value in attrs.items():
            if name == "name":
                setattr(self, name, value)
            else:
                setattr(self, name, safeEval(value))
