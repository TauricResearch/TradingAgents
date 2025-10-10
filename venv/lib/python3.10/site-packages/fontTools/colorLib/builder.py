"""
colorLib.builder: Build COLR/CPAL tables from scratch

"""

import collections
import copy
import enum
from functools import partial
from math import ceil, log
from typing import (
    Any,
    Dict,
    Generator,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)
from fontTools.misc.arrayTools import intRect
from fontTools.misc.fixedTools import fixedToFloat
from fontTools.misc.treeTools import build_n_ary_tree
from fontTools.ttLib.tables import C_O_L_R_
from fontTools.ttLib.tables import C_P_A_L_
from fontTools.ttLib.tables import _n_a_m_e
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables.otTables import ExtendMode, CompositeMode
from .errors import ColorLibError
from .geometry import round_start_circle_stable_containment
from .table_builder import BuildCallback, TableBuilder


# TODO move type aliases to colorLib.types?
T = TypeVar("T")
_Kwargs = Mapping[str, Any]
_PaintInput = Union[int, _Kwargs, ot.Paint, Tuple[str, "_PaintInput"]]
_PaintInputList = Sequence[_PaintInput]
_ColorGlyphsDict = Dict[str, Union[_PaintInputList, _PaintInput]]
_ColorGlyphsV0Dict = Dict[str, Sequence[Tuple[str, int]]]
_ClipBoxInput = Union[
    Tuple[int, int, int, int, int],  # format 1, variable
    Tuple[int, int, int, int],  # format 0, non-variable
    ot.ClipBox,
]


MAX_PAINT_COLR_LAYER_COUNT = 255
_DEFAULT_ALPHA = 1.0
_MAX_REUSE_LEN = 32


def _beforeBuildPaintRadialGradient(paint, source):
    x0 = source["x0"]
    y0 = source["y0"]
    r0 = source["r0"]
    x1 = source["x1"]
    y1 = source["y1"]
    r1 = source["r1"]

    # TODO apparently no builder_test confirms this works (?)

    # avoid abrupt change after rounding when c0 is near c1's perimeter
    c = round_start_circle_stable_containment((x0, y0), r0, (x1, y1), r1)
    x0, y0 = c.centre
    r0 = c.radius

    # update source to ensure paint is built with corrected values
    source["x0"] = x0
    source["y0"] = y0
    source["r0"] = r0
    source["x1"] = x1
    source["y1"] = y1
    source["r1"] = r1

    return paint, source


def _defaultColorStop():
    colorStop = ot.ColorStop()
    colorStop.Alpha = _DEFAULT_ALPHA
    return colorStop


def _defaultVarColorStop():
    colorStop = ot.VarColorStop()
    colorStop.Alpha = _DEFAULT_ALPHA
    return colorStop


def _defaultColorLine():
    colorLine = ot.ColorLine()
    colorLine.Extend = ExtendMode.PAD
    return colorLine


def _defaultVarColorLine():
    colorLine = ot.VarColorLine()
    colorLine.Extend = ExtendMode.PAD
    return colorLine


def _defaultPaintSolid():
    paint = ot.Paint()
    paint.Alpha = _DEFAULT_ALPHA
    return paint


def _buildPaintCallbacks():
    return {
        (
            BuildCallback.BEFORE_BUILD,
            ot.Paint,
            ot.PaintFormat.PaintRadialGradient,
        ): _beforeBuildPaintRadialGradient,
        (
            BuildCallback.BEFORE_BUILD,
            ot.Paint,
            ot.PaintFormat.PaintVarRadialGradient,
        ): _beforeBuildPaintRadialGradient,
        (BuildCallback.CREATE_DEFAULT, ot.ColorStop): _defaultColorStop,
        (BuildCallback.CREATE_DEFAULT, ot.VarColorStop): _defaultVarColorStop,
        (BuildCallback.CREATE_DEFAULT, ot.ColorLine): _defaultColorLine,
        (BuildCallback.CREATE_DEFAULT, ot.VarColorLine): _defaultVarColorLine,
        (
            BuildCallback.CREATE_DEFAULT,
            ot.Paint,
            ot.PaintFormat.PaintSolid,
        ): _defaultPaintSolid,
        (
            BuildCallback.CREATE_DEFAULT,
            ot.Paint,
            ot.PaintFormat.PaintVarSolid,
        ): _defaultPaintSolid,
    }


def populateCOLRv0(
    table: ot.COLR,
    colorGlyphsV0: _ColorGlyphsV0Dict,
    glyphMap: Optional[Mapping[str, int]] = None,
):
    """Build v0 color layers and add to existing COLR table.

    Args:
        table: a raw ``otTables.COLR()`` object (not ttLib's ``table_C_O_L_R_``).
        colorGlyphsV0: map of base glyph names to lists of (layer glyph names,
            color palette index) tuples. Can be empty.
        glyphMap: a map from glyph names to glyph indices, as returned from
            ``TTFont.getReverseGlyphMap()``, to optionally sort base records by GID.
    """
    if glyphMap is not None:
        colorGlyphItems = sorted(
            colorGlyphsV0.items(), key=lambda item: glyphMap[item[0]]
        )
    else:
        colorGlyphItems = colorGlyphsV0.items()
    baseGlyphRecords = []
    layerRecords = []
    for baseGlyph, layers in colorGlyphItems:
        baseRec = ot.BaseGlyphRecord()
        baseRec.BaseGlyph = baseGlyph
        baseRec.FirstLayerIndex = len(layerRecords)
        baseRec.NumLayers = len(layers)
        baseGlyphRecords.append(baseRec)

        for layerGlyph, paletteIndex in layers:
            layerRec = ot.LayerRecord()
            layerRec.LayerGlyph = layerGlyph
            layerRec.PaletteIndex = paletteIndex
            layerRecords.append(layerRec)

    table.BaseGlyphRecordArray = table.LayerRecordArray = None
    if baseGlyphRecords:
        table.BaseGlyphRecordArray = ot.BaseGlyphRecordArray()
        table.BaseGlyphRecordArray.BaseGlyphRecord = baseGlyphRecords
    if layerRecords:
        table.LayerRecordArray = ot.LayerRecordArray()
        table.LayerRecordArray.LayerRecord = layerRecords
    table.BaseGlyphRecordCount = len(baseGlyphRecords)
    table.LayerRecordCount = len(layerRecords)


def buildCOLR(
    colorGlyphs: _ColorGlyphsDict,
    version: Optional[int] = None,
    *,
    glyphMap: Optional[Mapping[str, int]] = None,
    varStore: Optional[ot.VarStore] = None,
    varIndexMap: Optional[ot.DeltaSetIndexMap] = None,
    clipBoxes: Optional[Dict[str, _ClipBoxInput]] = None,
    allowLayerReuse: bool = True,
) -> C_O_L_R_.table_C_O_L_R_:
    """Build COLR table from color layers mapping.

    Args:

        colorGlyphs: map of base glyph name to, either list of (layer glyph name,
            color palette index) tuples for COLRv0; or a single ``Paint`` (dict) or
            list of ``Paint`` for COLRv1.
        version: the version of COLR table. If None, the version is determined
            by the presence of COLRv1 paints or variation data (varStore), which
            require version 1; otherwise, if all base glyphs use only simple color
            layers, version 0 is used.
        glyphMap: a map from glyph names to glyph indices, as returned from
            TTFont.getReverseGlyphMap(), to optionally sort base records by GID.
        varStore: Optional ItemVarationStore for deltas associated with v1 layer.
        varIndexMap: Optional DeltaSetIndexMap for deltas associated with v1 layer.
        clipBoxes: Optional map of base glyph name to clip box 4- or 5-tuples:
            (xMin, yMin, xMax, yMax) or (xMin, yMin, xMax, yMax, varIndexBase).

    Returns:
        A new COLR table.
    """
    self = C_O_L_R_.table_C_O_L_R_()

    if varStore is not None and version == 0:
        raise ValueError("Can't add VarStore to COLRv0")

    if version in (None, 0) and not varStore:
        # split color glyphs into v0 and v1 and encode separately
        colorGlyphsV0, colorGlyphsV1 = _split_color_glyphs_by_version(colorGlyphs)
        if version == 0 and colorGlyphsV1:
            raise ValueError("Can't encode COLRv1 glyphs in COLRv0")
    else:
        # unless explicitly requested for v1 or have variations, in which case
        # we encode all color glyph as v1
        colorGlyphsV0, colorGlyphsV1 = {}, colorGlyphs

    colr = ot.COLR()

    populateCOLRv0(colr, colorGlyphsV0, glyphMap)

    colr.LayerList, colr.BaseGlyphList = buildColrV1(
        colorGlyphsV1,
        glyphMap,
        allowLayerReuse=allowLayerReuse,
    )

    if version is None:
        version = 1 if (varStore or colorGlyphsV1) else 0
    elif version not in (0, 1):
        raise NotImplementedError(version)
    self.version = colr.Version = version

    if version == 0:
        self.ColorLayers = self._decompileColorLayersV0(colr)
    else:
        colr.ClipList = buildClipList(clipBoxes) if clipBoxes else None
        colr.VarIndexMap = varIndexMap
        colr.VarStore = varStore
        self.table = colr

    return self


def buildClipList(clipBoxes: Dict[str, _ClipBoxInput]) -> ot.ClipList:
    clipList = ot.ClipList()
    clipList.Format = 1
    clipList.clips = {name: buildClipBox(box) for name, box in clipBoxes.items()}
    return clipList


def buildClipBox(clipBox: _ClipBoxInput) -> ot.ClipBox:
    if isinstance(clipBox, ot.ClipBox):
        return clipBox
    n = len(clipBox)
    clip = ot.ClipBox()
    if n not in (4, 5):
        raise ValueError(f"Invalid ClipBox: expected 4 or 5 values, found {n}")
    clip.xMin, clip.yMin, clip.xMax, clip.yMax = intRect(clipBox[:4])
    clip.Format = int(n == 5) + 1
    if n == 5:
        clip.VarIndexBase = int(clipBox[4])
    return clip


class ColorPaletteType(enum.IntFlag):
    USABLE_WITH_LIGHT_BACKGROUND = 0x0001
    USABLE_WITH_DARK_BACKGROUND = 0x0002

    @classmethod
    def _missing_(cls, value):
        # enforce reserved bits
        if isinstance(value, int) and (value < 0 or value & 0xFFFC != 0):
            raise ValueError(f"{value} is not a valid {cls.__name__}")
        return super()._missing_(value)


# None, 'abc' or {'en': 'abc', 'de': 'xyz'}
_OptionalLocalizedString = Union[None, str, Dict[str, str]]


def buildPaletteLabels(
    labels: Iterable[_OptionalLocalizedString], nameTable: _n_a_m_e.table__n_a_m_e
) -> List[Optional[int]]:
    return [
        (
            nameTable.addMultilingualName(l, mac=False)
            if isinstance(l, dict)
            else (
                C_P_A_L_.table_C_P_A_L_.NO_NAME_ID
                if l is None
                else nameTable.addMultilingualName({"en": l}, mac=False)
            )
        )
        for l in labels
    ]


def buildCPAL(
    palettes: Sequence[Sequence[Tuple[float, float, float, float]]],
    paletteTypes: Optional[Sequence[ColorPaletteType]] = None,
    paletteLabels: Optional[Sequence[_OptionalLocalizedString]] = None,
    paletteEntryLabels: Optional[Sequence[_OptionalLocalizedString]] = None,
    nameTable: Optional[_n_a_m_e.table__n_a_m_e] = None,
) -> C_P_A_L_.table_C_P_A_L_:
    """Build CPAL table from list of color palettes.

    Args:
        palettes: list of lists of colors encoded as tuples of (R, G, B, A) floats
            in the range [0..1].
        paletteTypes: optional list of ColorPaletteType, one for each palette.
        paletteLabels: optional list of palette labels. Each lable can be either:
            None (no label), a string (for for default English labels), or a
            localized string (as a dict keyed with BCP47 language codes).
        paletteEntryLabels: optional list of palette entry labels, one for each
            palette entry (see paletteLabels).
        nameTable: optional name table where to store palette and palette entry
            labels. Required if either paletteLabels or paletteEntryLabels is set.

    Return:
        A new CPAL v0 or v1 table, if custom palette types or labels are specified.
    """
    if len({len(p) for p in palettes}) != 1:
        raise ColorLibError("color palettes have different lengths")

    if (paletteLabels or paletteEntryLabels) and not nameTable:
        raise TypeError(
            "nameTable is required if palette or palette entries have labels"
        )

    cpal = C_P_A_L_.table_C_P_A_L_()
    cpal.numPaletteEntries = len(palettes[0])

    cpal.palettes = []
    for i, palette in enumerate(palettes):
        colors = []
        for j, color in enumerate(palette):
            if not isinstance(color, tuple) or len(color) != 4:
                raise ColorLibError(
                    f"In palette[{i}][{j}]: expected (R, G, B, A) tuple, got {color!r}"
                )
            if any(v > 1 or v < 0 for v in color):
                raise ColorLibError(
                    f"palette[{i}][{j}] has invalid out-of-range [0..1] color: {color!r}"
                )
            # input colors are RGBA, CPAL encodes them as BGRA
            red, green, blue, alpha = color
            colors.append(
                C_P_A_L_.Color(*(round(v * 255) for v in (blue, green, red, alpha)))
            )
        cpal.palettes.append(colors)

    if any(v is not None for v in (paletteTypes, paletteLabels, paletteEntryLabels)):
        cpal.version = 1

        if paletteTypes is not None:
            if len(paletteTypes) != len(palettes):
                raise ColorLibError(
                    f"Expected {len(palettes)} paletteTypes, got {len(paletteTypes)}"
                )
            cpal.paletteTypes = [ColorPaletteType(t).value for t in paletteTypes]
        else:
            cpal.paletteTypes = [C_P_A_L_.table_C_P_A_L_.DEFAULT_PALETTE_TYPE] * len(
                palettes
            )

        if paletteLabels is not None:
            if len(paletteLabels) != len(palettes):
                raise ColorLibError(
                    f"Expected {len(palettes)} paletteLabels, got {len(paletteLabels)}"
                )
            cpal.paletteLabels = buildPaletteLabels(paletteLabels, nameTable)
        else:
            cpal.paletteLabels = [C_P_A_L_.table_C_P_A_L_.NO_NAME_ID] * len(palettes)

        if paletteEntryLabels is not None:
            if len(paletteEntryLabels) != cpal.numPaletteEntries:
                raise ColorLibError(
                    f"Expected {cpal.numPaletteEntries} paletteEntryLabels, "
                    f"got {len(paletteEntryLabels)}"
                )
            cpal.paletteEntryLabels = buildPaletteLabels(paletteEntryLabels, nameTable)
        else:
            cpal.paletteEntryLabels = [
                C_P_A_L_.table_C_P_A_L_.NO_NAME_ID
            ] * cpal.numPaletteEntries
    else:
        cpal.version = 0

    return cpal


# COLR v1 tables
# See draft proposal at: https://github.com/googlefonts/colr-gradients-spec


def _is_colrv0_layer(layer: Any) -> bool:
    # Consider as COLRv0 layer any sequence of length 2 (be it tuple or list) in which
    # the first element is a str (the layerGlyph) and the second element is an int
    # (CPAL paletteIndex).
    # https://github.com/googlefonts/ufo2ft/issues/426
    try:
        layerGlyph, paletteIndex = layer
    except (TypeError, ValueError):
        return False
    else:
        return isinstance(layerGlyph, str) and isinstance(paletteIndex, int)


def _split_color_glyphs_by_version(
    colorGlyphs: _ColorGlyphsDict,
) -> Tuple[_ColorGlyphsV0Dict, _ColorGlyphsDict]:
    colorGlyphsV0 = {}
    colorGlyphsV1 = {}
    for baseGlyph, layers in colorGlyphs.items():
        if all(_is_colrv0_layer(l) for l in layers):
            colorGlyphsV0[baseGlyph] = layers
        else:
            colorGlyphsV1[baseGlyph] = layers

    # sanity check
    assert set(colorGlyphs) == (set(colorGlyphsV0) | set(colorGlyphsV1))

    return colorGlyphsV0, colorGlyphsV1


def _reuse_ranges(num_layers: int) -> Generator[Tuple[int, int], None, None]:
    # TODO feels like something itertools might have already
    for lbound in range(num_layers):
        # Reuse of very large #s of layers is relatively unlikely
        # +2: we want sequences of at least 2
        # otData handles single-record duplication
        for ubound in range(
            lbound + 2, min(num_layers + 1, lbound + 2 + _MAX_REUSE_LEN)
        ):
            yield (lbound, ubound)


class LayerReuseCache:
    reusePool: Mapping[Tuple[Any, ...], int]
    tuples: Mapping[int, Tuple[Any, ...]]
    keepAlive: List[ot.Paint]  # we need id to remain valid

    def __init__(self):
        self.reusePool = {}
        self.tuples = {}
        self.keepAlive = []

    def _paint_tuple(self, paint: ot.Paint):
        # start simple, who even cares about cyclic graphs or interesting field types
        def _tuple_safe(value):
            if isinstance(value, enum.Enum):
                return value
            elif hasattr(value, "__dict__"):
                return tuple(
                    (k, _tuple_safe(v)) for k, v in sorted(value.__dict__.items())
                )
            elif isinstance(value, collections.abc.MutableSequence):
                return tuple(_tuple_safe(e) for e in value)
            return value

        # Cache the tuples for individual Paint instead of the whole sequence
        # because the seq could be a transient slice
        result = self.tuples.get(id(paint), None)
        if result is None:
            result = _tuple_safe(paint)
            self.tuples[id(paint)] = result
            self.keepAlive.append(paint)
        return result

    def _as_tuple(self, paints: Sequence[ot.Paint]) -> Tuple[Any, ...]:
        return tuple(self._paint_tuple(p) for p in paints)

    def try_reuse(self, layers: List[ot.Paint]) -> List[ot.Paint]:
        found_reuse = True
        while found_reuse:
            found_reuse = False

            ranges = sorted(
                _reuse_ranges(len(layers)),
                key=lambda t: (t[1] - t[0], t[1], t[0]),
                reverse=True,
            )
            for lbound, ubound in ranges:
                reuse_lbound = self.reusePool.get(
                    self._as_tuple(layers[lbound:ubound]), -1
                )
                if reuse_lbound == -1:
                    continue
                new_slice = ot.Paint()
                new_slice.Format = int(ot.PaintFormat.PaintColrLayers)
                new_slice.NumLayers = ubound - lbound
                new_slice.FirstLayerIndex = reuse_lbound
                layers = layers[:lbound] + [new_slice] + layers[ubound:]
                found_reuse = True
                break
        return layers

    def add(self, layers: List[ot.Paint], first_layer_index: int):
        for lbound, ubound in _reuse_ranges(len(layers)):
            self.reusePool[self._as_tuple(layers[lbound:ubound])] = (
                lbound + first_layer_index
            )


class LayerListBuilder:
    layers: List[ot.Paint]
    cache: LayerReuseCache
    allowLayerReuse: bool

    def __init__(self, *, allowLayerReuse=True):
        self.layers = []
        if allowLayerReuse:
            self.cache = LayerReuseCache()
        else:
            self.cache = None

        # We need to intercept construction of PaintColrLayers
        callbacks = _buildPaintCallbacks()
        callbacks[
            (
                BuildCallback.BEFORE_BUILD,
                ot.Paint,
                ot.PaintFormat.PaintColrLayers,
            )
        ] = self._beforeBuildPaintColrLayers
        self.tableBuilder = TableBuilder(callbacks)

    # COLR layers is unusual in that it modifies shared state
    # so we need a callback into an object
    def _beforeBuildPaintColrLayers(self, dest, source):
        # Sketchy gymnastics: a sequence input will have dropped it's layers
        # into NumLayers; get it back
        if isinstance(source.get("NumLayers", None), collections.abc.Sequence):
            layers = source["NumLayers"]
        else:
            layers = source["Layers"]

        # Convert maps seqs or whatever into typed objects
        layers = [self.buildPaint(l) for l in layers]

        # No reason to have a colr layers with just one entry
        if len(layers) == 1:
            return layers[0], {}

        if self.cache is not None:
            # Look for reuse, with preference to longer sequences
            # This may make the layer list smaller
            layers = self.cache.try_reuse(layers)

        # The layer list is now final; if it's too big we need to tree it
        is_tree = len(layers) > MAX_PAINT_COLR_LAYER_COUNT
        layers = build_n_ary_tree(layers, n=MAX_PAINT_COLR_LAYER_COUNT)

        # We now have a tree of sequences with Paint leaves.
        # Convert the sequences into PaintColrLayers.
        def listToColrLayers(layer):
            if isinstance(layer, collections.abc.Sequence):
                return self.buildPaint(
                    {
                        "Format": ot.PaintFormat.PaintColrLayers,
                        "Layers": [listToColrLayers(l) for l in layer],
                    }
                )
            return layer

        layers = [listToColrLayers(l) for l in layers]

        # No reason to have a colr layers with just one entry
        if len(layers) == 1:
            return layers[0], {}

        paint = ot.Paint()
        paint.Format = int(ot.PaintFormat.PaintColrLayers)
        paint.NumLayers = len(layers)
        paint.FirstLayerIndex = len(self.layers)
        self.layers.extend(layers)

        # Register our parts for reuse provided we aren't a tree
        # If we are a tree the leaves registered for reuse and that will suffice
        if self.cache is not None and not is_tree:
            self.cache.add(layers, paint.FirstLayerIndex)

        # we've fully built dest; empty source prevents generalized build from kicking in
        return paint, {}

    def buildPaint(self, paint: _PaintInput) -> ot.Paint:
        return self.tableBuilder.build(ot.Paint, paint)

    def build(self) -> Optional[ot.LayerList]:
        if not self.layers:
            return None
        layers = ot.LayerList()
        layers.LayerCount = len(self.layers)
        layers.Paint = self.layers
        return layers


def buildBaseGlyphPaintRecord(
    baseGlyph: str, layerBuilder: LayerListBuilder, paint: _PaintInput
) -> ot.BaseGlyphList:
    self = ot.BaseGlyphPaintRecord()
    self.BaseGlyph = baseGlyph
    self.Paint = layerBuilder.buildPaint(paint)
    return self


def _format_glyph_errors(errors: Mapping[str, Exception]) -> str:
    lines = []
    for baseGlyph, error in sorted(errors.items()):
        lines.append(f"    {baseGlyph} => {type(error).__name__}: {error}")
    return "\n".join(lines)


def buildColrV1(
    colorGlyphs: _ColorGlyphsDict,
    glyphMap: Optional[Mapping[str, int]] = None,
    *,
    allowLayerReuse: bool = True,
) -> Tuple[Optional[ot.LayerList], ot.BaseGlyphList]:
    if glyphMap is not None:
        colorGlyphItems = sorted(
            colorGlyphs.items(), key=lambda item: glyphMap[item[0]]
        )
    else:
        colorGlyphItems = colorGlyphs.items()

    errors = {}
    baseGlyphs = []
    layerBuilder = LayerListBuilder(allowLayerReuse=allowLayerReuse)
    for baseGlyph, paint in colorGlyphItems:
        try:
            baseGlyphs.append(buildBaseGlyphPaintRecord(baseGlyph, layerBuilder, paint))

        except (ColorLibError, OverflowError, ValueError, TypeError) as e:
            errors[baseGlyph] = e

    if errors:
        failed_glyphs = _format_glyph_errors(errors)
        exc = ColorLibError(f"Failed to build BaseGlyphList:\n{failed_glyphs}")
        exc.errors = errors
        raise exc from next(iter(errors.values()))

    layers = layerBuilder.build()
    glyphs = ot.BaseGlyphList()
    glyphs.BaseGlyphCount = len(baseGlyphs)
    glyphs.BaseGlyphPaintRecord = baseGlyphs
    return (layers, glyphs)
