from fontTools.ttLib.tables import otTables as ot
from .table_builder import TableUnbuilder


def unbuildColrV1(layerList, baseGlyphList):
    layers = []
    if layerList:
        layers = layerList.Paint
    unbuilder = LayerListUnbuilder(layers)
    return {
        rec.BaseGlyph: unbuilder.unbuildPaint(rec.Paint)
        for rec in baseGlyphList.BaseGlyphPaintRecord
    }


def _flatten_layers(lst):
    for paint in lst:
        if paint["Format"] == ot.PaintFormat.PaintColrLayers:
            yield from _flatten_layers(paint["Layers"])
        else:
            yield paint


class LayerListUnbuilder:
    def __init__(self, layers):
        self.layers = layers

        callbacks = {
            (
                ot.Paint,
                ot.PaintFormat.PaintColrLayers,
            ): self._unbuildPaintColrLayers,
        }
        self.tableUnbuilder = TableUnbuilder(callbacks)

    def unbuildPaint(self, paint):
        assert isinstance(paint, ot.Paint)
        return self.tableUnbuilder.unbuild(paint)

    def _unbuildPaintColrLayers(self, source):
        assert source["Format"] == ot.PaintFormat.PaintColrLayers

        layers = list(
            _flatten_layers(
                [
                    self.unbuildPaint(childPaint)
                    for childPaint in self.layers[
                        source["FirstLayerIndex"] : source["FirstLayerIndex"]
                        + source["NumLayers"]
                    ]
                ]
            )
        )

        if len(layers) == 1:
            return layers[0]

        return {"Format": source["Format"], "Layers": layers}


if __name__ == "__main__":
    from pprint import pprint
    import sys
    from fontTools.ttLib import TTFont

    try:
        fontfile = sys.argv[1]
    except IndexError:
        sys.exit("usage: fonttools colorLib.unbuilder FONTFILE")

    font = TTFont(fontfile)
    colr = font["COLR"]
    if colr.version < 1:
        sys.exit(f"error: No COLR table version=1 found in {fontfile}")

    colorGlyphs = unbuildColrV1(
        colr.table.LayerList,
        colr.table.BaseGlyphList,
    )

    pprint(colorGlyphs)
