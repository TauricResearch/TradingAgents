"""
Module for dealing with 'gvar'-style font variations, also known as run-time
interpolation.

The ideas here are very similar to MutatorMath.  There is even code to read
MutatorMath .designspace files in the varLib.designspace module.

For now, if you run this file on a designspace file, it tries to find
ttf-interpolatable files for the masters and build a variable-font from
them.  Such ttf-interpolatable and designspace files can be generated from
a Glyphs source, eg., using noto-source as an example:

    .. code-block:: sh

        $ fontmake -o ttf-interpolatable -g NotoSansArabic-MM.glyphs

Then you can make a variable-font this way:

    .. code-block:: sh

        $ fonttools varLib master_ufo/NotoSansArabic.designspace

API *will* change in near future.
"""

from typing import List
from fontTools.misc.vector import Vector
from fontTools.misc.roundTools import noRound, otRound
from fontTools.misc.fixedTools import floatToFixed as fl2fi
from fontTools.misc.textTools import Tag, tostr
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._f_v_a_r import Axis, NamedInstance
from fontTools.ttLib.tables._g_l_y_f import (
    GlyphCoordinates,
    dropImpliedOnCurvePoints,
    USE_MY_METRICS,
)
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables.otBase import OTTableWriter
from fontTools.varLib import builder, models, varStore
from fontTools.varLib.merger import VariationMerger, COLRVariationMerger
from fontTools.varLib.mvar import MVAR_ENTRIES
from fontTools.varLib.iup import iup_delta_optimize
from fontTools.varLib.featureVars import addFeatureVariations
from fontTools.designspaceLib import DesignSpaceDocument, InstanceDescriptor
from fontTools.designspaceLib.split import splitInterpolable, splitVariableFonts
from fontTools.varLib.stat import buildVFStatTable
from fontTools.colorLib.builder import buildColrV1
from fontTools.colorLib.unbuilder import unbuildColrV1
from functools import partial
from collections import OrderedDict, defaultdict, namedtuple
import os.path
import logging
from copy import deepcopy
from pprint import pformat
from re import fullmatch
from .errors import VarLibError, VarLibValidationError

log = logging.getLogger("fontTools.varLib")

# This is a lib key for the designspace document. The value should be
# a comma-separated list of OpenType feature tag(s), to be used as the
# FeatureVariations feature.
# If present, the DesignSpace <rules processing="..."> flag is ignored.
FEAVAR_FEATURETAG_LIB_KEY = "com.github.fonttools.varLib.featureVarsFeatureTag"

#
# Creation routines
#


def _add_fvar(font, axes, instances: List[InstanceDescriptor]):
    """
    Add 'fvar' table to font.

    axes is an ordered dictionary of DesignspaceAxis objects.

    instances is list of dictionary objects with 'location', 'stylename',
    and possibly 'postscriptfontname' entries.
    """

    assert axes
    assert isinstance(axes, OrderedDict)

    log.info("Generating fvar")

    fvar = newTable("fvar")
    nameTable = font["name"]

    # if there are not currently any mac names don't add them here, that's inconsistent
    # https://github.com/fonttools/fonttools/issues/683
    macNames = any(nr.platformID == 1 for nr in getattr(nameTable, "names", ()))

    # we have all the best ways to express mac names
    platforms = ((3, 1, 0x409),)
    if macNames:
        platforms = ((1, 0, 0),) + platforms

    for a in axes.values():
        axis = Axis()
        axis.axisTag = Tag(a.tag)
        # TODO Skip axes that have no variation.
        axis.minValue, axis.defaultValue, axis.maxValue = (
            a.minimum,
            a.default,
            a.maximum,
        )
        axis.axisNameID = nameTable.addMultilingualName(
            a.labelNames, font, minNameID=256, mac=macNames
        )
        axis.flags = int(a.hidden)
        fvar.axes.append(axis)

    default_coordinates = {axis.axisTag: axis.defaultValue for axis in fvar.axes}

    for instance in instances:
        # Filter out discrete axis locations
        coordinates = {
            name: value for name, value in instance.location.items() if name in axes
        }

        if "en" not in instance.localisedStyleName:
            if not instance.styleName:
                raise VarLibValidationError(
                    f"Instance at location '{coordinates}' must have a default English "
                    "style name ('stylename' attribute on the instance element or a "
                    "stylename element with an 'xml:lang=\"en\"' attribute)."
                )
            localisedStyleName = dict(instance.localisedStyleName)
            localisedStyleName["en"] = tostr(instance.styleName)
        else:
            localisedStyleName = instance.localisedStyleName

        psname = instance.postScriptFontName

        inst = NamedInstance()
        inst.coordinates = {
            axes[k].tag: axes[k].map_backward(v) for k, v in coordinates.items()
        }

        subfamilyNameID = nameTable.findMultilingualName(
            localisedStyleName, windows=True, mac=macNames
        )
        if subfamilyNameID in {2, 17} and inst.coordinates == default_coordinates:
            # Instances can only reuse an existing name ID 2 or 17 if they are at the
            # default location across all axes, see:
            # https://github.com/fonttools/fonttools/issues/3825.
            inst.subfamilyNameID = subfamilyNameID
        else:
            inst.subfamilyNameID = nameTable.addMultilingualName(
                localisedStyleName, windows=True, mac=macNames, minNameID=256
            )

        if psname is not None:
            psname = tostr(psname)
            inst.postscriptNameID = nameTable.addName(psname, platforms=platforms)
        fvar.instances.append(inst)

    assert "fvar" not in font
    font["fvar"] = fvar

    return fvar


def _add_avar(font, axes, mappings, axisTags):
    """
    Add 'avar' table to font.

    axes is an ordered dictionary of AxisDescriptor objects.
    """

    assert axes
    assert isinstance(axes, OrderedDict)

    log.info("Generating avar")

    avar = newTable("avar")

    interesting = False
    vals_triples = {}
    for axis in axes.values():
        # Currently, some rasterizers require that the default value maps
        # (-1 to -1, 0 to 0, and 1 to 1) be present for all the segment
        # maps, even when the default normalization mapping for the axis
        # was not modified.
        # https://github.com/googlei18n/fontmake/issues/295
        # https://github.com/fonttools/fonttools/issues/1011
        # TODO(anthrotype) revert this (and 19c4b37) when issue is fixed
        curve = avar.segments[axis.tag] = {-1.0: -1.0, 0.0: 0.0, 1.0: 1.0}

        keys_triple = (axis.minimum, axis.default, axis.maximum)
        vals_triple = tuple(axis.map_forward(v) for v in keys_triple)
        vals_triples[axis.tag] = vals_triple

        if not axis.map:
            continue

        items = sorted(axis.map)
        keys = [item[0] for item in items]
        vals = [item[1] for item in items]

        # Current avar requirements.  We don't have to enforce
        # these on the designer and can deduce some ourselves,
        # but for now just enforce them.
        if axis.minimum != min(keys):
            raise VarLibValidationError(
                f"Axis '{axis.name}': there must be a mapping for the axis minimum "
                f"value {axis.minimum} and it must be the lowest input mapping value."
            )
        if axis.maximum != max(keys):
            raise VarLibValidationError(
                f"Axis '{axis.name}': there must be a mapping for the axis maximum "
                f"value {axis.maximum} and it must be the highest input mapping value."
            )
        if axis.default not in keys:
            raise VarLibValidationError(
                f"Axis '{axis.name}': there must be a mapping for the axis default "
                f"value {axis.default}."
            )
        # No duplicate input values (output values can be >= their preceeding value).
        if len(set(keys)) != len(keys):
            raise VarLibValidationError(
                f"Axis '{axis.name}': All axis mapping input='...' values must be "
                "unique, but we found duplicates."
            )
        # Ascending values
        if sorted(vals) != vals:
            raise VarLibValidationError(
                f"Axis '{axis.name}': mapping output values must be in ascending order."
            )

        keys = [models.normalizeValue(v, keys_triple) for v in keys]
        vals = [models.normalizeValue(v, vals_triple) for v in vals]

        if all(k == v for k, v in zip(keys, vals)):
            continue
        interesting = True

        curve.update(zip(keys, vals))

        assert 0.0 in curve and curve[0.0] == 0.0
        assert -1.0 not in curve or curve[-1.0] == -1.0
        assert +1.0 not in curve or curve[+1.0] == +1.0
        # curve.update({-1.0: -1.0, 0.0: 0.0, 1.0: 1.0})

    if mappings:
        interesting = True

        inputLocations = [
            {
                axes[name].tag: models.normalizeValue(v, vals_triples[axes[name].tag])
                for name, v in mapping.inputLocation.items()
            }
            for mapping in mappings
        ]
        outputLocations = [
            {
                axes[name].tag: models.normalizeValue(v, vals_triples[axes[name].tag])
                for name, v in mapping.outputLocation.items()
            }
            for mapping in mappings
        ]
        assert len(inputLocations) == len(outputLocations)

        # If base-master is missing, insert it at zero location.
        if not any(all(v == 0 for k, v in loc.items()) for loc in inputLocations):
            inputLocations.insert(0, {})
            outputLocations.insert(0, {})

        model = models.VariationModel(inputLocations, axisTags)
        storeBuilder = varStore.OnlineVarStoreBuilder(axisTags)
        storeBuilder.setModel(model)
        varIdxes = {}
        for tag in axisTags:
            masterValues = []
            for vo, vi in zip(outputLocations, inputLocations):
                if tag not in vo:
                    masterValues.append(0)
                    continue
                v = vo[tag] - vi.get(tag, 0)
                masterValues.append(fl2fi(v, 14))
            varIdxes[tag] = storeBuilder.storeMasters(masterValues)[1]

        store = storeBuilder.finish()
        optimized = store.optimize()
        varIdxes = {axis: optimized[value] for axis, value in varIdxes.items()}

        varIdxMap = builder.buildDeltaSetIndexMap(varIdxes[t] for t in axisTags)

        avar.majorVersion = 2
        avar.table = ot.avar()
        avar.table.VarIdxMap = varIdxMap
        avar.table.VarStore = store

    assert "avar" not in font
    if not interesting:
        log.info("No need for avar")
        avar = None
    else:
        font["avar"] = avar

    return avar


def _add_stat(font):
    # Note: this function only gets called by old code that calls `build()`
    # directly. Newer code that wants to benefit from STAT data from the
    # designspace should call `build_many()`

    if "STAT" in font:
        return

    from ..otlLib.builder import buildStatTable

    fvarTable = font["fvar"]
    axes = [dict(tag=a.axisTag, name=a.axisNameID) for a in fvarTable.axes]
    buildStatTable(font, axes)


_MasterData = namedtuple("_MasterData", ["glyf", "hMetrics", "vMetrics"])


def _add_gvar(font, masterModel, master_ttfs, tolerance=0.5, optimize=True):
    if tolerance < 0:
        raise ValueError("`tolerance` must be a positive number.")

    log.info("Generating gvar")
    assert "gvar" not in font
    gvar = font["gvar"] = newTable("gvar")
    glyf = font["glyf"]
    defaultMasterIndex = masterModel.reverseMapping[0]

    master_datas = [
        _MasterData(
            m["glyf"], m["hmtx"].metrics, getattr(m.get("vmtx"), "metrics", None)
        )
        for m in master_ttfs
    ]

    for glyph in font.getGlyphOrder():
        log.debug("building gvar for glyph '%s'", glyph)

        allData = [
            m.glyf._getCoordinatesAndControls(glyph, m.hMetrics, m.vMetrics)
            for m in master_datas
        ]

        if allData[defaultMasterIndex][1].numberOfContours != 0:
            # If the default master is not empty, interpret empty non-default masters
            # as missing glyphs from a sparse master
            allData = [
                d if d is not None and d[1].numberOfContours != 0 else None
                for d in allData
            ]

        model, allData = masterModel.getSubModel(allData)

        allCoords = [d[0] for d in allData]
        allControls = [d[1] for d in allData]
        control = allControls[0]
        if not models.allEqual(allControls):
            log.warning("glyph %s has incompatible masters; skipping" % glyph)
            continue
        del allControls

        # Update gvar
        gvar.variations[glyph] = []
        deltas = model.getDeltas(
            allCoords, round=partial(GlyphCoordinates.__round__, round=round)
        )
        supports = model.supports
        assert len(deltas) == len(supports)

        # Prepare for IUP optimization
        origCoords = deltas[0]
        endPts = control.endPts

        for i, (delta, support) in enumerate(zip(deltas[1:], supports[1:])):
            if all(v == 0 for v in delta.array):
                continue
            var = TupleVariation(support, delta)
            if optimize:
                delta_opt = iup_delta_optimize(
                    delta, origCoords, endPts, tolerance=tolerance
                )

                if None in delta_opt:
                    # Use "optimized" version only if smaller...
                    var_opt = TupleVariation(support, delta_opt)

                    axis_tags = sorted(
                        support.keys()
                    )  # Shouldn't matter that this is different from fvar...?
                    tupleData, auxData = var.compile(axis_tags)
                    unoptimized_len = len(tupleData) + len(auxData)
                    tupleData, auxData = var_opt.compile(axis_tags)
                    optimized_len = len(tupleData) + len(auxData)

                    if optimized_len < unoptimized_len:
                        var = var_opt

            gvar.variations[glyph].append(var)


def _remove_TTHinting(font):
    for tag in ("cvar", "cvt ", "fpgm", "prep"):
        if tag in font:
            del font[tag]
    maxp = font["maxp"]
    for attr in (
        "maxTwilightPoints",
        "maxStorage",
        "maxFunctionDefs",
        "maxInstructionDefs",
        "maxStackElements",
        "maxSizeOfInstructions",
    ):
        setattr(maxp, attr, 0)
    maxp.maxZones = 1
    font["glyf"].removeHinting()
    # TODO: Modify gasp table to deactivate gridfitting for all ranges?


def _merge_TTHinting(font, masterModel, master_ttfs):
    log.info("Merging TT hinting")
    assert "cvar" not in font

    # Check that the existing hinting is compatible

    # fpgm and prep table

    for tag in ("fpgm", "prep"):
        all_pgms = [m[tag].program for m in master_ttfs if tag in m]
        if not all_pgms:
            continue
        font_pgm = getattr(font.get(tag), "program", None)
        if any(pgm != font_pgm for pgm in all_pgms):
            log.warning(
                "Masters have incompatible %s tables, hinting is discarded." % tag
            )
            _remove_TTHinting(font)
            return

    # glyf table

    font_glyf = font["glyf"]
    master_glyfs = [m["glyf"] for m in master_ttfs]
    for name, glyph in font_glyf.glyphs.items():
        all_pgms = [getattr(glyf.get(name), "program", None) for glyf in master_glyfs]
        if not any(all_pgms):
            continue
        glyph.expand(font_glyf)
        font_pgm = getattr(glyph, "program", None)
        if any(pgm != font_pgm for pgm in all_pgms if pgm):
            log.warning(
                "Masters have incompatible glyph programs in glyph '%s', hinting is discarded."
                % name
            )
            # TODO Only drop hinting from this glyph.
            _remove_TTHinting(font)
            return

    # cvt table

    all_cvs = [Vector(m["cvt "].values) if "cvt " in m else None for m in master_ttfs]

    nonNone_cvs = models.nonNone(all_cvs)
    if not nonNone_cvs:
        # There is no cvt table to make a cvar table from, we're done here.
        return

    if not models.allEqual(len(c) for c in nonNone_cvs):
        log.warning("Masters have incompatible cvt tables, hinting is discarded.")
        _remove_TTHinting(font)
        return

    variations = []
    deltas, supports = masterModel.getDeltasAndSupports(
        all_cvs, round=round
    )  # builtin round calls into Vector.__round__, which uses builtin round as we like
    for i, (delta, support) in enumerate(zip(deltas[1:], supports[1:])):
        if all(v == 0 for v in delta):
            continue
        var = TupleVariation(support, delta)
        variations.append(var)

    # We can build the cvar table now.
    if variations:
        cvar = font["cvar"] = newTable("cvar")
        cvar.version = 1
        cvar.variations = variations


def _has_inconsistent_use_my_metrics_flag(
    master_glyf, glyph_name, flagged_components, expected_num_components
) -> bool:
    master_glyph = master_glyf.get(glyph_name)
    # 'sparse' glyph master doesn't contribute. Besides when components don't match
    # the VF build is going to fail anyway, so be lenient here.
    if (
        master_glyph is not None
        and master_glyph.isComposite()
        and len(master_glyph.components) == expected_num_components
    ):
        for i, base_glyph in flagged_components:
            comp = master_glyph.components[i]
            if comp.glyphName != base_glyph:
                break
            if not (comp.flags & USE_MY_METRICS):
                return True
    return False


def _unset_inconsistent_use_my_metrics_flags(vf, master_fonts):
    """Clear USE_MY_METRICS on composite components if inconsistent across masters.

    If a composite glyph's component has USE_MY_METRICS set differently among
    the masters, the flag is removed from the variable font's glyf table so that
    advance widths are not determined by that single component's phantom points.
    """
    glyf = vf["glyf"]
    master_glyfs = [m["glyf"] for m in master_fonts if "glyf" in m]
    if not master_glyfs:
        # Should not happen: at least the base master (as copied into vf) has glyf
        return

    for glyph_name in glyf.keys():
        glyph = glyf[glyph_name]
        if not glyph.isComposite():
            continue

        # collect indices of component(s) that carry the USE_MY_METRICS flag.
        # This is supposed to be 1 component per composite, but you never know.
        flagged_components = [
            (i, comp.glyphName)
            for i, comp in enumerate(glyph.components)
            if (comp.flags & USE_MY_METRICS)
        ]
        if not flagged_components:
            # Nothing to fix
            continue

        # Verify that for all master glyf tables that contribute this glyph, the
        # corresponding component (same glyphName and index) also carries USE_MY_METRICS
        # and unset the flag if not.
        expected_num_components = len(glyph.components)
        if any(
            _has_inconsistent_use_my_metrics_flag(
                master_glyf, glyph_name, flagged_components, expected_num_components
            )
            for master_glyf in master_glyfs
        ):
            comp_names = [name for _, name in flagged_components]
            log.info(
                "Composite glyph '%s' has inconsistent USE_MY_METRICS flags across "
                "masters; clearing the flag on component%s %s",
                glyph_name,
                "s" if len(comp_names) > 1 else "",
                comp_names if len(comp_names) > 1 else comp_names[0],
            )
            for i, _ in flagged_components:
                glyph.components[i].flags &= ~USE_MY_METRICS


_MetricsFields = namedtuple(
    "_MetricsFields",
    [
        "tableTag",
        "metricsTag",
        "sb1",
        "sb2",
        "advMapping",
        "vOrigMapping",
        "phantomIndex",
    ],
)

HVAR_FIELDS = _MetricsFields(
    tableTag="HVAR",
    metricsTag="hmtx",
    sb1="LsbMap",
    sb2="RsbMap",
    advMapping="AdvWidthMap",
    vOrigMapping=None,
    phantomIndex=0,
)

VVAR_FIELDS = _MetricsFields(
    tableTag="VVAR",
    metricsTag="vmtx",
    sb1="TsbMap",
    sb2="BsbMap",
    advMapping="AdvHeightMap",
    vOrigMapping="VOrgMap",
    phantomIndex=1,
)


def _add_HVAR(font, masterModel, master_ttfs, axisTags):
    getAdvanceMetrics = partial(
        _get_advance_metrics, font, masterModel, master_ttfs, axisTags, HVAR_FIELDS
    )
    _add_VHVAR(font, axisTags, HVAR_FIELDS, getAdvanceMetrics)


def _add_VVAR(font, masterModel, master_ttfs, axisTags):
    getAdvanceMetrics = partial(
        _get_advance_metrics, font, masterModel, master_ttfs, axisTags, VVAR_FIELDS
    )
    _add_VHVAR(font, axisTags, VVAR_FIELDS, getAdvanceMetrics)


def _add_VHVAR(font, axisTags, tableFields, getAdvanceMetrics):
    tableTag = tableFields.tableTag
    assert tableTag not in font
    glyphOrder = font.getGlyphOrder()
    log.info("Generating " + tableTag)
    VHVAR = newTable(tableTag)
    tableClass = getattr(ot, tableTag)
    vhvar = VHVAR.table = tableClass()
    vhvar.Version = 0x00010000

    vhAdvanceDeltasAndSupports, vOrigDeltasAndSupports = getAdvanceMetrics()

    if vOrigDeltasAndSupports:
        singleModel = False
    else:
        singleModel = models.allEqual(
            id(v[1]) for v in vhAdvanceDeltasAndSupports.values()
        )

    directStore = None
    if singleModel:
        # Build direct mapping
        supports = next(iter(vhAdvanceDeltasAndSupports.values()))[1][1:]
        varTupleList = builder.buildVarRegionList(supports, axisTags)
        varTupleIndexes = list(range(len(supports)))
        varData = builder.buildVarData(varTupleIndexes, [], optimize=False)
        for glyphName in glyphOrder:
            varData.addItem(vhAdvanceDeltasAndSupports[glyphName][0], round=noRound)
        varData.optimize()
        directStore = builder.buildVarStore(varTupleList, [varData])
        # remove unused regions from VarRegionList
        directStore.prune_regions()

    # Build optimized indirect mapping
    storeBuilder = varStore.OnlineVarStoreBuilder(axisTags)
    advMapping = {}
    for glyphName in glyphOrder:
        deltas, supports = vhAdvanceDeltasAndSupports[glyphName]
        storeBuilder.setSupports(supports)
        advMapping[glyphName] = storeBuilder.storeDeltas(deltas, round=noRound)

    if vOrigDeltasAndSupports:
        vOrigMap = {}
        for glyphName in glyphOrder:
            deltas, supports = vOrigDeltasAndSupports[glyphName]
            storeBuilder.setSupports(supports)
            vOrigMap[glyphName] = storeBuilder.storeDeltas(deltas, round=noRound)

    indirectStore = storeBuilder.finish()
    mapping2 = indirectStore.optimize(use_NO_VARIATION_INDEX=False)
    advMapping = [mapping2[advMapping[g]] for g in glyphOrder]
    advanceMapping = builder.buildVarIdxMap(advMapping, glyphOrder)

    if vOrigDeltasAndSupports:
        vOrigMap = [mapping2[vOrigMap[g]] for g in glyphOrder]

    useDirect = False
    vOrigMapping = None
    if directStore:
        # Compile both, see which is more compact

        writer = OTTableWriter()
        directStore.compile(writer, font)
        directSize = len(writer.getAllData())

        writer = OTTableWriter()
        indirectStore.compile(writer, font)
        advanceMapping.compile(writer, font)
        indirectSize = len(writer.getAllData())

        useDirect = directSize < indirectSize

    if useDirect:
        metricsStore = directStore
        advanceMapping = None
    else:
        metricsStore = indirectStore
        if vOrigDeltasAndSupports:
            vOrigMapping = builder.buildVarIdxMap(vOrigMap, glyphOrder)

    vhvar.VarStore = metricsStore
    setattr(vhvar, tableFields.advMapping, advanceMapping)
    if vOrigMapping is not None:
        setattr(vhvar, tableFields.vOrigMapping, vOrigMapping)
    setattr(vhvar, tableFields.sb1, None)
    setattr(vhvar, tableFields.sb2, None)

    font[tableTag] = VHVAR
    return


def _get_advance_metrics(font, masterModel, master_ttfs, axisTags, tableFields):
    tableTag = tableFields.tableTag
    glyphOrder = font.getGlyphOrder()

    # Build list of source font advance widths for each glyph
    metricsTag = tableFields.metricsTag
    advMetricses = [m[metricsTag].metrics for m in master_ttfs]

    # Build list of source font vertical origin coords for each glyph
    if tableTag == "VVAR" and "VORG" in master_ttfs[0]:
        vOrigMetricses = [m["VORG"].VOriginRecords for m in master_ttfs]
        defaultYOrigs = [m["VORG"].defaultVertOriginY for m in master_ttfs]
        vOrigMetricses = list(zip(vOrigMetricses, defaultYOrigs))
    else:
        vOrigMetricses = None

    vhAdvanceDeltasAndSupports = {}
    vOrigDeltasAndSupports = {}
    # HACK: we treat width 65535 as a sentinel value to signal that a glyph
    # from a non-default master should not participate in computing {H,V}VAR,
    # as if it were missing. Allows to variate other glyph-related data independently
    # from glyph metrics
    sparse_advance = 0xFFFF
    for glyph in glyphOrder:
        vhAdvances = [
            (
                metrics[glyph][0]
                if glyph in metrics and metrics[glyph][0] != sparse_advance
                else None
            )
            for metrics in advMetricses
        ]
        vhAdvanceDeltasAndSupports[glyph] = masterModel.getDeltasAndSupports(
            vhAdvances, round=round
        )

    if vOrigMetricses:
        for glyph in glyphOrder:
            # We need to supply a vOrigs tuple with non-None default values
            # for each glyph. vOrigMetricses contains values only for those
            # glyphs which have a non-default vOrig.
            vOrigs = [
                metrics[glyph] if glyph in metrics else defaultVOrig
                for metrics, defaultVOrig in vOrigMetricses
            ]
            vOrigDeltasAndSupports[glyph] = masterModel.getDeltasAndSupports(
                vOrigs, round=round
            )

    return vhAdvanceDeltasAndSupports, vOrigDeltasAndSupports


def _add_MVAR(font, masterModel, master_ttfs, axisTags):
    log.info("Generating MVAR")

    store_builder = varStore.OnlineVarStoreBuilder(axisTags)

    records = []
    lastTableTag = None
    fontTable = None
    tables = None
    # HACK: we need to special-case post.underlineThickness and .underlinePosition
    # and unilaterally/arbitrarily define a sentinel value to distinguish the case
    # when a post table is present in a given master simply because that's where
    # the glyph names in TrueType must be stored, but the underline values are not
    # meant to be used for building MVAR's deltas. The value of -0x8000 (-36768)
    # the minimum FWord (int16) value, was chosen for its unlikelyhood to appear
    # in real-world underline position/thickness values.
    specialTags = {"unds": -0x8000, "undo": -0x8000}

    for tag, (tableTag, itemName) in sorted(MVAR_ENTRIES.items(), key=lambda kv: kv[1]):
        # For each tag, fetch the associated table from all fonts (or not when we are
        # still looking at a tag from the same tables) and set up the variation model
        # for them.
        if tableTag != lastTableTag:
            tables = fontTable = None
            if tableTag in font:
                fontTable = font[tableTag]
                tables = []
                for master in master_ttfs:
                    if tableTag not in master or (
                        tag in specialTags
                        and getattr(master[tableTag], itemName) == specialTags[tag]
                    ):
                        tables.append(None)
                    else:
                        tables.append(master[tableTag])
                model, tables = masterModel.getSubModel(tables)
                store_builder.setModel(model)
            lastTableTag = tableTag

        if tables is None:  # Tag not applicable to the master font.
            continue

        # TODO support gasp entries

        master_values = [getattr(table, itemName) for table in tables]
        if models.allEqual(master_values):
            base, varIdx = master_values[0], None
        else:
            base, varIdx = store_builder.storeMasters(master_values)
        setattr(fontTable, itemName, base)

        if varIdx is None:
            continue
        log.info("	%s: %s.%s	%s", tag, tableTag, itemName, master_values)
        rec = ot.MetricsValueRecord()
        rec.ValueTag = tag
        rec.VarIdx = varIdx
        records.append(rec)

    assert "MVAR" not in font
    if records:
        store = store_builder.finish()
        # Optimize
        mapping = store.optimize()
        for rec in records:
            rec.VarIdx = mapping[rec.VarIdx]

        MVAR = font["MVAR"] = newTable("MVAR")
        mvar = MVAR.table = ot.MVAR()
        mvar.Version = 0x00010000
        mvar.Reserved = 0
        mvar.VarStore = store
        # XXX these should not be hard-coded but computed automatically
        mvar.ValueRecordSize = 8
        mvar.ValueRecordCount = len(records)
        mvar.ValueRecord = sorted(records, key=lambda r: r.ValueTag)


def _add_BASE(font, masterModel, master_ttfs, axisTags):
    log.info("Generating BASE")

    merger = VariationMerger(masterModel, axisTags, font)
    merger.mergeTables(font, master_ttfs, ["BASE"])
    store = merger.store_builder.finish()

    if not store:
        return
    base = font["BASE"].table
    assert base.Version == 0x00010000
    base.Version = 0x00010001
    base.VarStore = store


def _merge_OTL(font, model, master_fonts, axisTags):
    otl_tags = ["GSUB", "GDEF", "GPOS"]
    if not any(tag in font for tag in otl_tags):
        return

    log.info("Merging OpenType Layout tables")
    merger = VariationMerger(model, axisTags, font)

    merger.mergeTables(font, master_fonts, otl_tags)
    store = merger.store_builder.finish()
    if not store:
        return
    try:
        GDEF = font["GDEF"].table
        assert GDEF.Version <= 0x00010002
    except KeyError:
        font["GDEF"] = newTable("GDEF")
        GDEFTable = font["GDEF"] = newTable("GDEF")
        GDEF = GDEFTable.table = ot.GDEF()
        GDEF.GlyphClassDef = None
        GDEF.AttachList = None
        GDEF.LigCaretList = None
        GDEF.MarkAttachClassDef = None
        GDEF.MarkGlyphSetsDef = None

    GDEF.Version = 0x00010003
    GDEF.VarStore = store

    # Optimize
    varidx_map = store.optimize()
    GDEF.remap_device_varidxes(varidx_map)
    if "GPOS" in font:
        font["GPOS"].table.remap_device_varidxes(varidx_map)


def _add_GSUB_feature_variations(
    font, axes, internal_axis_supports, rules, featureTags
):
    def normalize(name, value):
        return models.normalizeLocation({name: value}, internal_axis_supports)[name]

    log.info("Generating GSUB FeatureVariations")

    axis_tags = {name: axis.tag for name, axis in axes.items()}

    conditional_subs = []
    for rule in rules:
        region = []
        for conditions in rule.conditionSets:
            space = {}
            for condition in conditions:
                axis_name = condition["name"]
                if condition["minimum"] is not None:
                    minimum = normalize(axis_name, condition["minimum"])
                else:
                    minimum = -1.0
                if condition["maximum"] is not None:
                    maximum = normalize(axis_name, condition["maximum"])
                else:
                    maximum = 1.0
                tag = axis_tags[axis_name]
                space[tag] = (minimum, maximum)
            region.append(space)

        subs = {k: v for k, v in rule.subs}

        conditional_subs.append((region, subs))

    addFeatureVariations(font, conditional_subs, featureTags)


_DesignSpaceData = namedtuple(
    "_DesignSpaceData",
    [
        "axes",
        "axisMappings",
        "internal_axis_supports",
        "base_idx",
        "normalized_master_locs",
        "masters",
        "instances",
        "rules",
        "rulesProcessingLast",
        "lib",
    ],
)


def _add_CFF2(varFont, model, master_fonts):
    from .cff import merge_region_fonts

    glyphOrder = varFont.getGlyphOrder()
    if "CFF2" not in varFont:
        from fontTools.cffLib.CFFToCFF2 import convertCFFToCFF2

        convertCFFToCFF2(varFont)

    ordered_fonts_list = model.reorderMasters(master_fonts, model.reverseMapping)
    # re-ordering the master list simplifies building the CFF2 data item lists.
    merge_region_fonts(varFont, model, ordered_fonts_list, glyphOrder)


def _add_COLR(font, model, master_fonts, axisTags, colr_layer_reuse=True):
    merger = COLRVariationMerger(
        model, axisTags, font, allowLayerReuse=colr_layer_reuse
    )
    merger.mergeTables(font, master_fonts)
    store = merger.store_builder.finish()

    colr = font["COLR"].table
    if store:
        mapping = store.optimize()
        colr.VarStore = store
        varIdxes = [mapping[v] for v in merger.varIdxes]
        colr.VarIndexMap = builder.buildDeltaSetIndexMap(varIdxes)


def load_designspace(designspace, log_enabled=True, *, require_sources=True):
    # TODO: remove this and always assume 'designspace' is a DesignSpaceDocument,
    # never a file path, as that's already handled by caller
    if hasattr(designspace, "sources"):  # Assume a DesignspaceDocument
        ds = designspace
    else:  # Assume a file path
        ds = DesignSpaceDocument.fromfile(designspace)

    masters = ds.sources
    if require_sources and not masters:
        raise VarLibValidationError("Designspace must have at least one source.")
    instances = ds.instances

    # TODO: Use fontTools.designspaceLib.tagForAxisName instead.
    standard_axis_map = OrderedDict(
        [
            ("weight", ("wght", {"en": "Weight"})),
            ("width", ("wdth", {"en": "Width"})),
            ("slant", ("slnt", {"en": "Slant"})),
            ("optical", ("opsz", {"en": "Optical Size"})),
            ("italic", ("ital", {"en": "Italic"})),
        ]
    )

    # Setup axes
    if not ds.axes:
        raise VarLibValidationError(f"Designspace must have at least one axis.")

    axes = OrderedDict()
    for axis_index, axis in enumerate(ds.axes):
        axis_name = axis.name
        if not axis_name:
            if not axis.tag:
                raise VarLibValidationError(f"Axis at index {axis_index} needs a tag.")
            axis_name = axis.name = axis.tag

        if axis_name in standard_axis_map:
            if axis.tag is None:
                axis.tag = standard_axis_map[axis_name][0]
            if not axis.labelNames:
                axis.labelNames.update(standard_axis_map[axis_name][1])
        else:
            if not axis.tag:
                raise VarLibValidationError(f"Axis at index {axis_index} needs a tag.")
            if not axis.labelNames:
                axis.labelNames["en"] = tostr(axis_name)

        axes[axis_name] = axis
    if log_enabled:
        log.info("Axes:\n%s", pformat([axis.asdict() for axis in axes.values()]))

    axisMappings = ds.axisMappings
    if axisMappings and log_enabled:
        log.info("Mappings:\n%s", pformat(axisMappings))

    # Check all master and instance locations are valid and fill in defaults
    for obj in masters + instances:
        obj_name = obj.name or obj.styleName or ""
        loc = obj.getFullDesignLocation(ds)
        obj.designLocation = loc
        if loc is None:
            raise VarLibValidationError(
                f"Source or instance '{obj_name}' has no location."
            )
        for axis_name in loc.keys():
            if axis_name not in axes:
                raise VarLibValidationError(
                    f"Location axis '{axis_name}' unknown for '{obj_name}'."
                )
        for axis_name, axis in axes.items():
            v = axis.map_backward(loc[axis_name])
            if not (axis.minimum <= v <= axis.maximum):
                raise VarLibValidationError(
                    f"Source or instance '{obj_name}' has out-of-range location "
                    f"for axis '{axis_name}': is mapped to {v} but must be in "
                    f"mapped range [{axis.minimum}..{axis.maximum}] (NOTE: all "
                    "values are in user-space)."
                )

    # Normalize master locations

    internal_master_locs = [o.getFullDesignLocation(ds) for o in masters]
    if log_enabled:
        log.info("Internal master locations:\n%s", pformat(internal_master_locs))

    # TODO This mapping should ideally be moved closer to logic in _add_fvar/avar
    internal_axis_supports = {}
    for axis in axes.values():
        triple = (axis.minimum, axis.default, axis.maximum)
        internal_axis_supports[axis.name] = [axis.map_forward(v) for v in triple]
    if log_enabled:
        log.info("Internal axis supports:\n%s", pformat(internal_axis_supports))

    normalized_master_locs = [
        models.normalizeLocation(m, internal_axis_supports)
        for m in internal_master_locs
    ]
    if log_enabled:
        log.info("Normalized master locations:\n%s", pformat(normalized_master_locs))

    # Find base master
    base_idx = None
    for i, m in enumerate(normalized_master_locs):
        if all(v == 0 for v in m.values()):
            if base_idx is not None:
                raise VarLibValidationError(
                    "More than one base master found in Designspace."
                )
            base_idx = i
    if require_sources and base_idx is None:
        raise VarLibValidationError(
            "Base master not found; no master at default location?"
        )
    if log_enabled:
        log.info("Index of base master: %s", base_idx)

    return _DesignSpaceData(
        axes,
        axisMappings,
        internal_axis_supports,
        base_idx,
        normalized_master_locs,
        masters,
        instances,
        ds.rules,
        ds.rulesProcessingLast,
        ds.lib,
    )


# https://docs.microsoft.com/en-us/typography/opentype/spec/os2#uswidthclass
WDTH_VALUE_TO_OS2_WIDTH_CLASS = {
    50: 1,
    62.5: 2,
    75: 3,
    87.5: 4,
    100: 5,
    112.5: 6,
    125: 7,
    150: 8,
    200: 9,
}


def set_default_weight_width_slant(font, location):
    if "OS/2" in font:
        if "wght" in location:
            weight_class = otRound(max(1, min(location["wght"], 1000)))
            if font["OS/2"].usWeightClass != weight_class:
                log.info("Setting OS/2.usWeightClass = %s", weight_class)
                font["OS/2"].usWeightClass = weight_class

        if "wdth" in location:
            # map 'wdth' axis (50..200) to OS/2.usWidthClass (1..9), rounding to closest
            widthValue = min(max(location["wdth"], 50), 200)
            widthClass = otRound(
                models.piecewiseLinearMap(widthValue, WDTH_VALUE_TO_OS2_WIDTH_CLASS)
            )
            if font["OS/2"].usWidthClass != widthClass:
                log.info("Setting OS/2.usWidthClass = %s", widthClass)
                font["OS/2"].usWidthClass = widthClass

    if "slnt" in location and "post" in font:
        italicAngle = max(-90, min(location["slnt"], 90))
        if font["post"].italicAngle != italicAngle:
            log.info("Setting post.italicAngle = %s", italicAngle)
            font["post"].italicAngle = italicAngle


def drop_implied_oncurve_points(*masters: TTFont) -> int:
    """Drop impliable on-curve points from all the simple glyphs in masters.

    In TrueType glyf outlines, on-curve points can be implied when they are located
    exactly at the midpoint of the line connecting two consecutive off-curve points.

    The input masters' glyf tables are assumed to contain same-named glyphs that are
    interpolatable. Oncurve points are only dropped if they can be implied for all
    the masters. The fonts are modified in-place.

    Args:
        masters: The TTFont(s) to modify

    Returns:
        The total number of points that were dropped if any.

    Reference:
    https://developer.apple.com/fonts/TrueType-Reference-Manual/RM01/Chap1.html
    """

    count = 0
    glyph_masters = defaultdict(list)
    # multiple DS source may point to the same TTFont object and we want to
    # avoid processing the same glyph twice as they are modified in-place
    for font in {id(m): m for m in masters}.values():
        glyf = font["glyf"]
        for glyphName in glyf.keys():
            glyph_masters[glyphName].append(glyf[glyphName])
    count = 0
    for glyphName, glyphs in glyph_masters.items():
        try:
            dropped = dropImpliedOnCurvePoints(*glyphs)
        except ValueError as e:
            # we don't fail for incompatible glyphs in _add_gvar so we shouldn't here
            log.warning("Failed to drop implied oncurves for %r: %s", glyphName, e)
        else:
            count += len(dropped)
    return count


def build_many(
    designspace: DesignSpaceDocument,
    master_finder=lambda s: s,
    exclude=[],
    optimize=True,
    skip_vf=lambda vf_name: False,
    colr_layer_reuse=True,
    drop_implied_oncurves=False,
):
    """
    Build variable fonts from a designspace file, version 5 which can define
    several VFs, or version 4 which has implicitly one VF covering the whole doc.

    If master_finder is set, it should be a callable that takes master
    filename as found in designspace file and map it to master font
    binary as to be opened (eg. .ttf or .otf).

    skip_vf can be used to skip building some of the variable fonts defined in
    the input designspace. It's a predicate that takes as argument the name
    of the variable font and returns `bool`.

    Always returns a Dict[str, TTFont] keyed by VariableFontDescriptor.name
    """
    res = {}
    # varLib.build (used further below) by default only builds an incomplete 'STAT'
    # with an empty AxisValueArray--unless the VF inherited 'STAT' from its base master.
    # Designspace version 5 can also be used to define 'STAT' labels or customize
    # axes ordering, etc. To avoid overwriting a pre-existing 'STAT' or redoing the
    # same work twice, here we check if designspace contains any 'STAT' info before
    # proceeding to call buildVFStatTable for each VF.
    # https://github.com/fonttools/fonttools/pull/3024
    # https://github.com/fonttools/fonttools/issues/3045
    doBuildStatFromDSv5 = (
        "STAT" not in exclude
        and designspace.formatTuple >= (5, 0)
        and (
            any(a.axisLabels or a.axisOrdering is not None for a in designspace.axes)
            or designspace.locationLabels
        )
    )
    for _location, subDoc in splitInterpolable(designspace):
        for name, vfDoc in splitVariableFonts(subDoc):
            if skip_vf(name):
                log.debug(f"Skipping variable TTF font: {name}")
                continue
            vf = build(
                vfDoc,
                master_finder,
                exclude=exclude,
                optimize=optimize,
                colr_layer_reuse=colr_layer_reuse,
                drop_implied_oncurves=drop_implied_oncurves,
            )[0]
            if doBuildStatFromDSv5:
                buildVFStatTable(vf, designspace, name)
            res[name] = vf
    return res


def build(
    designspace,
    master_finder=lambda s: s,
    exclude=[],
    optimize=True,
    colr_layer_reuse=True,
    drop_implied_oncurves=False,
):
    """
    Build variation font from a designspace file.

    If master_finder is set, it should be a callable that takes master
    filename as found in designspace file and map it to master font
    binary as to be opened (eg. .ttf or .otf).
    """
    if hasattr(designspace, "sources"):  # Assume a DesignspaceDocument
        pass
    else:  # Assume a file path
        designspace = DesignSpaceDocument.fromfile(designspace)

    ds = load_designspace(designspace)
    log.info("Building variable font")

    log.info("Loading master fonts")
    master_fonts = load_masters(designspace, master_finder)

    # TODO: 'master_ttfs' is unused except for return value, remove later
    master_ttfs = []
    for master in master_fonts:
        try:
            master_ttfs.append(master.reader.file.name)
        except AttributeError:
            master_ttfs.append(None)  # in-memory fonts have no path

    if drop_implied_oncurves and "glyf" in master_fonts[ds.base_idx]:
        drop_count = drop_implied_oncurve_points(*master_fonts)
        log.info(
            "Dropped %s on-curve points from simple glyphs in the 'glyf' table",
            drop_count,
        )

    # Copy the base master to work from it
    vf = deepcopy(master_fonts[ds.base_idx])

    if "DSIG" in vf:
        del vf["DSIG"]

    # Clear USE_MY_METRICS composite flags if set inconsistently across masters.
    if "glyf" in vf:
        _unset_inconsistent_use_my_metrics_flags(vf, master_fonts)

    # TODO append masters as named-instances as well; needs .designspace change.
    fvar = _add_fvar(vf, ds.axes, ds.instances)
    if "STAT" not in exclude:
        _add_stat(vf)

    # Map from axis names to axis tags...
    normalized_master_locs = [
        {ds.axes[k].tag: v for k, v in loc.items()} for loc in ds.normalized_master_locs
    ]
    # From here on, we use fvar axes only
    axisTags = [axis.axisTag for axis in fvar.axes]

    # Assume single-model for now.
    model = models.VariationModel(normalized_master_locs, axisOrder=axisTags)
    assert 0 == model.mapping[ds.base_idx]

    log.info("Building variations tables")
    if "avar" not in exclude:
        _add_avar(vf, ds.axes, ds.axisMappings, axisTags)
    if "BASE" not in exclude and "BASE" in vf:
        _add_BASE(vf, model, master_fonts, axisTags)
    if "MVAR" not in exclude:
        _add_MVAR(vf, model, master_fonts, axisTags)
    if "HVAR" not in exclude:
        _add_HVAR(vf, model, master_fonts, axisTags)
    if "VVAR" not in exclude and "vmtx" in vf:
        _add_VVAR(vf, model, master_fonts, axisTags)
    if "GDEF" not in exclude or "GPOS" not in exclude:
        _merge_OTL(vf, model, master_fonts, axisTags)
    if "gvar" not in exclude and "glyf" in vf:
        _add_gvar(vf, model, master_fonts, optimize=optimize)
    if "cvar" not in exclude and "glyf" in vf:
        _merge_TTHinting(vf, model, master_fonts)
    if "GSUB" not in exclude and ds.rules:
        featureTags = _feature_variations_tags(ds)
        _add_GSUB_feature_variations(
            vf, ds.axes, ds.internal_axis_supports, ds.rules, featureTags
        )
    if "CFF2" not in exclude and ("CFF " in vf or "CFF2" in vf):
        _add_CFF2(vf, model, master_fonts)
        if "post" in vf:
            # set 'post' to format 2 to keep the glyph names dropped from CFF2
            post = vf["post"]
            if post.formatType != 2.0:
                post.formatType = 2.0
                post.extraNames = []
                post.mapping = {}
    if "COLR" not in exclude and "COLR" in vf and vf["COLR"].version > 0:
        _add_COLR(vf, model, master_fonts, axisTags, colr_layer_reuse)

    set_default_weight_width_slant(
        vf, location={axis.axisTag: axis.defaultValue for axis in vf["fvar"].axes}
    )

    for tag in exclude:
        if tag in vf:
            del vf[tag]

    # TODO: Only return vf for 4.0+, the rest is unused.
    return vf, model, master_ttfs


def _open_font(path, master_finder=lambda s: s):
    # load TTFont masters from given 'path': this can be either a .TTX or an
    # OpenType binary font; or if neither of these, try use the 'master_finder'
    # callable to resolve the path to a valid .TTX or OpenType font binary.
    from fontTools.ttx import guessFileType

    master_path = os.path.normpath(path)
    tp = guessFileType(master_path)
    if tp is None:
        # not an OpenType binary/ttx, fall back to the master finder.
        master_path = master_finder(master_path)
        tp = guessFileType(master_path)
    if tp in ("TTX", "OTX"):
        font = TTFont()
        font.importXML(master_path)
    elif tp in ("TTF", "OTF", "WOFF", "WOFF2"):
        font = TTFont(master_path)
    else:
        raise VarLibValidationError("Invalid master path: %r" % master_path)
    return font


def load_masters(designspace, master_finder=lambda s: s):
    """Ensure that all SourceDescriptor.font attributes have an appropriate TTFont
    object loaded, or else open TTFont objects from the SourceDescriptor.path
    attributes.

    The paths can point to either an OpenType font, a TTX file, or a UFO. In the
    latter case, use the provided master_finder callable to map from UFO paths to
    the respective master font binaries (e.g. .ttf, .otf or .ttx).

    Return list of master TTFont objects in the same order they are listed in the
    DesignSpaceDocument.
    """
    for master in designspace.sources:
        # If a SourceDescriptor has a layer name, demand that the compiled TTFont
        # be supplied by the caller. This spares us from modifying MasterFinder.
        if master.layerName and master.font is None:
            raise VarLibValidationError(
                f"Designspace source '{master.name or '<Unknown>'}' specified a "
                "layer name but lacks the required TTFont object in the 'font' "
                "attribute."
            )

    return designspace.loadSourceFonts(_open_font, master_finder=master_finder)


class MasterFinder(object):
    def __init__(self, template):
        self.template = template

    def __call__(self, src_path):
        fullname = os.path.abspath(src_path)
        dirname, basename = os.path.split(fullname)
        stem, ext = os.path.splitext(basename)
        path = self.template.format(
            fullname=fullname,
            dirname=dirname,
            basename=basename,
            stem=stem,
            ext=ext,
        )
        return os.path.normpath(path)


def _feature_variations_tags(ds):
    raw_tags = ds.lib.get(
        FEAVAR_FEATURETAG_LIB_KEY,
        "rclt" if ds.rulesProcessingLast else "rvrn",
    )
    return sorted({t.strip() for t in raw_tags.split(",")})


def addGSUBFeatureVariations(vf, designspace, featureTags=(), *, log_enabled=False):
    """Add GSUB FeatureVariations table to variable font, based on DesignSpace rules.

    Args:
        vf: A TTFont object representing the variable font.
        designspace: A DesignSpaceDocument object.
        featureTags: Optional feature tag(s) to use for the FeatureVariations records.
            If unset, the key 'com.github.fonttools.varLib.featureVarsFeatureTag' is
            looked up in the DS <lib> and used; otherwise the default is 'rclt' if
            the <rules processing="last"> attribute is set, else 'rvrn'.
            See <https://fonttools.readthedocs.io/en/latest/designspaceLib/xml.html#rules-element>
        log_enabled: If True, log info about DS axes and sources. Default is False, as
            the same info may have already been logged as part of varLib.build.
    """
    ds = load_designspace(designspace, log_enabled=log_enabled)
    if not ds.rules:
        return
    if not featureTags:
        featureTags = _feature_variations_tags(ds)
    _add_GSUB_feature_variations(
        vf, ds.axes, ds.internal_axis_supports, ds.rules, featureTags
    )


def main(args=None):
    """Build variable fonts from a designspace file and masters"""
    from argparse import ArgumentParser
    from fontTools import configLogger

    parser = ArgumentParser(prog="varLib", description=main.__doc__)
    parser.add_argument("designspace")
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "-o", metavar="OUTPUTFILE", dest="outfile", default=None, help="output file"
    )
    output_group.add_argument(
        "-d",
        "--output-dir",
        metavar="OUTPUTDIR",
        default=None,
        help="output dir (default: same as input designspace file)",
    )
    parser.add_argument(
        "-x",
        metavar="TAG",
        dest="exclude",
        action="append",
        default=[],
        help="exclude table",
    )
    parser.add_argument(
        "--disable-iup",
        dest="optimize",
        action="store_false",
        help="do not perform IUP optimization",
    )
    parser.add_argument(
        "--no-colr-layer-reuse",
        dest="colr_layer_reuse",
        action="store_false",
        help="do not rebuild variable COLR table to optimize COLR layer reuse",
    )
    parser.add_argument(
        "--drop-implied-oncurves",
        action="store_true",
        help=(
            "drop on-curve points that can be implied when exactly in the middle of "
            "two off-curve points (only applies to TrueType fonts)"
        ),
    )
    parser.add_argument(
        "--master-finder",
        default="master_ttf_interpolatable/{stem}.ttf",
        help=(
            "templated string used for finding binary font "
            "files given the source file names defined in the "
            "designspace document. The following special strings "
            "are defined: {fullname} is the absolute source file "
            "name; {basename} is the file name without its "
            "directory; {stem} is the basename without the file "
            "extension; {ext} is the source file extension; "
            "{dirname} is the directory of the absolute file "
            'name. The default value is "%(default)s".'
        ),
    )
    parser.add_argument(
        "--variable-fonts",
        default=".*",
        metavar="VF_NAME",
        help=(
            "Filter the list of variable fonts produced from the input "
            "Designspace v5 file. By default all listed variable fonts are "
            "generated. To generate a specific variable font (or variable fonts) "
            'that match a given "name" attribute, you can pass as argument '
            "the full name or a regular expression. E.g.: --variable-fonts "
            '"MyFontVF_WeightOnly"; or --variable-fonts "MyFontVFItalic_.*".'
        ),
    )
    logging_group = parser.add_mutually_exclusive_group(required=False)
    logging_group.add_argument(
        "-v", "--verbose", action="store_true", help="Run more verbosely."
    )
    logging_group.add_argument(
        "-q", "--quiet", action="store_true", help="Turn verbosity off."
    )
    options = parser.parse_args(args)

    configLogger(
        level=("DEBUG" if options.verbose else "ERROR" if options.quiet else "INFO")
    )

    designspace_filename = options.designspace
    designspace = DesignSpaceDocument.fromfile(designspace_filename)

    vf_descriptors = designspace.getVariableFonts()
    if not vf_descriptors:
        parser.error(f"No variable fonts in given designspace {designspace.path!r}")

    vfs_to_build = []
    for vf in vf_descriptors:
        # Skip variable fonts that do not match the user's inclusion regex if given.
        if not fullmatch(options.variable_fonts, vf.name):
            continue
        vfs_to_build.append(vf)

    if not vfs_to_build:
        parser.error(f"No variable fonts matching {options.variable_fonts!r}")

    if options.outfile is not None and len(vfs_to_build) > 1:
        parser.error(
            "can't specify -o because there are multiple VFs to build; "
            "use --output-dir, or select a single VF with --variable-fonts"
        )

    output_dir = options.output_dir
    if output_dir is None:
        output_dir = os.path.dirname(designspace_filename)

    vf_name_to_output_path = {}
    if len(vfs_to_build) == 1 and options.outfile is not None:
        vf_name_to_output_path[vfs_to_build[0].name] = options.outfile
    else:
        for vf in vfs_to_build:
            filename = vf.filename if vf.filename is not None else vf.name + ".{ext}"
            vf_name_to_output_path[vf.name] = os.path.join(output_dir, filename)

    finder = MasterFinder(options.master_finder)

    vfs = build_many(
        designspace,
        finder,
        exclude=options.exclude,
        optimize=options.optimize,
        colr_layer_reuse=options.colr_layer_reuse,
        drop_implied_oncurves=options.drop_implied_oncurves,
    )

    for vf_name, vf in vfs.items():
        ext = "otf" if vf.sfntVersion == "OTTO" else "ttf"
        output_path = vf_name_to_output_path[vf_name].format(ext=ext)
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        log.info("Saving variation font %s", output_path)
        vf.save(output_path)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        sys.exit(main())
    import doctest

    sys.exit(doctest.testmod().failed)
