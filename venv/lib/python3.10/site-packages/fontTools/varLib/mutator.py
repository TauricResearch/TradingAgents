"""
Instantiate a variation font.  Run, eg:

.. code-block:: sh

    $ fonttools varLib.mutator ./NotoSansArabic-VF.ttf wght=140 wdth=85

.. warning::
   ``fontTools.varLib.mutator`` is deprecated in favor of :mod:`fontTools.varLib.instancer`
   which provides equivalent full instancing and also supports partial instancing.
   Please migrate CLI usage to ``fonttools varLib.instancer`` and API usage to
   :func:`fontTools.varLib.instancer.instantiateVariableFont`.
"""

from fontTools.misc.fixedTools import floatToFixedToFloat, floatToFixed
from fontTools.misc.loggingTools import deprecateFunction
from fontTools.misc.roundTools import otRound
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import ttProgram
from fontTools.ttLib.tables._g_l_y_f import (
    GlyphCoordinates,
    flagOverlapSimple,
    OVERLAP_COMPOUND,
)
from fontTools.varLib.models import (
    supportScalar,
    normalizeLocation,
    piecewiseLinearMap,
)
from fontTools.varLib.merger import MutatorMerger
from fontTools.varLib.varStore import VarStoreInstancer
from fontTools.varLib.mvar import MVAR_ENTRIES
from fontTools.varLib.iup import iup_delta
import fontTools.subset.cff
import os.path
import logging
from io import BytesIO


log = logging.getLogger("fontTools.varlib.mutator")

# map 'wdth' axis (1..200) to OS/2.usWidthClass (1..9), rounding to closest
OS2_WIDTH_CLASS_VALUES = {}
percents = [50.0, 62.5, 75.0, 87.5, 100.0, 112.5, 125.0, 150.0, 200.0]
for i, (prev, curr) in enumerate(zip(percents[:-1], percents[1:]), start=1):
    half = (prev + curr) / 2
    OS2_WIDTH_CLASS_VALUES[half] = i


def interpolate_cff2_PrivateDict(topDict, interpolateFromDeltas):
    pd_blend_lists = (
        "BlueValues",
        "OtherBlues",
        "FamilyBlues",
        "FamilyOtherBlues",
        "StemSnapH",
        "StemSnapV",
    )
    pd_blend_values = ("BlueScale", "BlueShift", "BlueFuzz", "StdHW", "StdVW")
    for fontDict in topDict.FDArray:
        pd = fontDict.Private
        vsindex = pd.vsindex if (hasattr(pd, "vsindex")) else 0
        for key, value in pd.rawDict.items():
            if (key in pd_blend_values) and isinstance(value, list):
                delta = interpolateFromDeltas(vsindex, value[1:])
                pd.rawDict[key] = otRound(value[0] + delta)
            elif (key in pd_blend_lists) and isinstance(value[0], list):
                """If any argument in a BlueValues list is a blend list,
                then they all are. The first value of each list is an
                absolute value. The delta tuples are calculated from
                relative master values, hence we need to append all the
                deltas to date to each successive absolute value."""
                delta = 0
                for i, val_list in enumerate(value):
                    delta += otRound(interpolateFromDeltas(vsindex, val_list[1:]))
                    value[i] = val_list[0] + delta


def interpolate_cff2_charstrings(topDict, interpolateFromDeltas, glyphOrder):
    charstrings = topDict.CharStrings
    for gname in glyphOrder:
        # Interpolate charstring
        # e.g replace blend op args with regular args,
        # and use and discard vsindex op.
        charstring = charstrings[gname]
        new_program = []
        vsindex = 0
        last_i = 0
        for i, token in enumerate(charstring.program):
            if token == "vsindex":
                vsindex = charstring.program[i - 1]
                if last_i != 0:
                    new_program.extend(charstring.program[last_i : i - 1])
                last_i = i + 1
            elif token == "blend":
                num_regions = charstring.getNumRegions(vsindex)
                numMasters = 1 + num_regions
                num_args = charstring.program[i - 1]
                # The program list starting at program[i] is now:
                # ..args for following operations
                # num_args values  from the default font
                # num_args tuples, each with numMasters-1 delta values
                # num_blend_args
                # 'blend'
                argi = i - (num_args * numMasters + 1)
                end_args = tuplei = argi + num_args
                while argi < end_args:
                    next_ti = tuplei + num_regions
                    deltas = charstring.program[tuplei:next_ti]
                    delta = interpolateFromDeltas(vsindex, deltas)
                    charstring.program[argi] += otRound(delta)
                    tuplei = next_ti
                    argi += 1
                new_program.extend(charstring.program[last_i:end_args])
                last_i = i + 1
        if last_i != 0:
            new_program.extend(charstring.program[last_i:])
            charstring.program = new_program


def interpolate_cff2_metrics(varfont, topDict, glyphOrder, loc):
    """Unlike TrueType glyphs, neither advance width nor bounding box
    info is stored in a CFF2 charstring. The width data exists only in
    the hmtx and HVAR tables. Since LSB data cannot be interpolated
    reliably from the master LSB values in the hmtx table, we traverse
    the charstring to determine the actual bound box."""

    charstrings = topDict.CharStrings
    boundsPen = BoundsPen(glyphOrder)
    hmtx = varfont["hmtx"]
    hvar_table = None
    if "HVAR" in varfont:
        hvar_table = varfont["HVAR"].table
        fvar = varfont["fvar"]
        varStoreInstancer = VarStoreInstancer(hvar_table.VarStore, fvar.axes, loc)

    for gid, gname in enumerate(glyphOrder):
        entry = list(hmtx[gname])
        # get width delta.
        if hvar_table:
            if hvar_table.AdvWidthMap:
                width_idx = hvar_table.AdvWidthMap.mapping[gname]
            else:
                width_idx = gid
            width_delta = otRound(varStoreInstancer[width_idx])
        else:
            width_delta = 0

        # get LSB.
        boundsPen.init()
        charstring = charstrings[gname]
        charstring.draw(boundsPen)
        if boundsPen.bounds is None:
            # Happens with non-marking glyphs
            lsb_delta = 0
        else:
            lsb = otRound(boundsPen.bounds[0])
            lsb_delta = entry[1] - lsb

        if lsb_delta or width_delta:
            if width_delta:
                entry[0] = max(0, entry[0] + width_delta)
            if lsb_delta:
                entry[1] = lsb
            hmtx[gname] = tuple(entry)


@deprecateFunction(
    "use fontTools.varLib.instancer.instantiateVariableFont instead "
    "for either full or partial instancing",
)
def instantiateVariableFont(varfont, location, inplace=False, overlap=True):
    """Generate a static instance from a variable TTFont and a dictionary
    defining the desired location along the variable font's axes.
    The location values must be specified as user-space coordinates, e.g.:

    .. code-block::

        {'wght': 400, 'wdth': 100}

    By default, a new TTFont object is returned. If ``inplace`` is True, the
    input varfont is modified and reduced to a static font.

    When the overlap parameter is defined as True,
    OVERLAP_SIMPLE and OVERLAP_COMPOUND bits are set to 1.  See
    https://docs.microsoft.com/en-us/typography/opentype/spec/glyf
    """
    if not inplace:
        # make a copy to leave input varfont unmodified
        stream = BytesIO()
        varfont.save(stream)
        stream.seek(0)
        varfont = TTFont(stream)

    fvar = varfont["fvar"]
    axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in fvar.axes}
    loc = normalizeLocation(location, axes)
    if "avar" in varfont:
        maps = varfont["avar"].segments
        loc = {k: piecewiseLinearMap(v, maps[k]) for k, v in loc.items()}
    # Quantize to F2Dot14, to avoid surprise interpolations.
    loc = {k: floatToFixedToFloat(v, 14) for k, v in loc.items()}
    # Location is normalized now
    log.info("Normalized location: %s", loc)

    if "gvar" in varfont:
        log.info("Mutating glyf/gvar tables")
        gvar = varfont["gvar"]
        glyf = varfont["glyf"]
        hMetrics = varfont["hmtx"].metrics
        vMetrics = getattr(varfont.get("vmtx"), "metrics", None)
        # get list of glyph names in gvar sorted by component depth
        glyphnames = sorted(
            gvar.variations.keys(),
            key=lambda name: (
                (
                    glyf[name].getCompositeMaxpValues(glyf).maxComponentDepth
                    if glyf[name].isComposite()
                    else 0
                ),
                name,
            ),
        )
        for glyphname in glyphnames:
            variations = gvar.variations[glyphname]
            coordinates, _ = glyf._getCoordinatesAndControls(
                glyphname, hMetrics, vMetrics
            )
            origCoords, endPts = None, None
            for var in variations:
                scalar = supportScalar(loc, var.axes)
                if not scalar:
                    continue
                delta = var.coordinates
                if None in delta:
                    if origCoords is None:
                        origCoords, g = glyf._getCoordinatesAndControls(
                            glyphname, hMetrics, vMetrics
                        )
                    delta = iup_delta(delta, origCoords, g.endPts)
                coordinates += GlyphCoordinates(delta) * scalar
            glyf._setCoordinates(glyphname, coordinates, hMetrics, vMetrics)
    else:
        glyf = None

    if "DSIG" in varfont:
        del varfont["DSIG"]

    if "cvar" in varfont:
        log.info("Mutating cvt/cvar tables")
        cvar = varfont["cvar"]
        cvt = varfont["cvt "]
        deltas = {}
        for var in cvar.variations:
            scalar = supportScalar(loc, var.axes)
            if not scalar:
                continue
            for i, c in enumerate(var.coordinates):
                if c is not None:
                    deltas[i] = deltas.get(i, 0) + scalar * c
        for i, delta in deltas.items():
            cvt[i] += otRound(delta)

    if "CFF2" in varfont:
        log.info("Mutating CFF2 table")
        glyphOrder = varfont.getGlyphOrder()
        CFF2 = varfont["CFF2"]
        topDict = CFF2.cff.topDictIndex[0]
        vsInstancer = VarStoreInstancer(topDict.VarStore.otVarStore, fvar.axes, loc)
        interpolateFromDeltas = vsInstancer.interpolateFromDeltas
        interpolate_cff2_PrivateDict(topDict, interpolateFromDeltas)
        CFF2.desubroutinize()
        interpolate_cff2_charstrings(topDict, interpolateFromDeltas, glyphOrder)
        interpolate_cff2_metrics(varfont, topDict, glyphOrder, loc)
        del topDict.rawDict["VarStore"]
        del topDict.VarStore

    if "MVAR" in varfont:
        log.info("Mutating MVAR table")
        mvar = varfont["MVAR"].table
        varStoreInstancer = VarStoreInstancer(mvar.VarStore, fvar.axes, loc)
        records = mvar.ValueRecord
        for rec in records:
            mvarTag = rec.ValueTag
            if mvarTag not in MVAR_ENTRIES:
                continue
            tableTag, itemName = MVAR_ENTRIES[mvarTag]
            delta = otRound(varStoreInstancer[rec.VarIdx])
            if not delta:
                continue
            setattr(
                varfont[tableTag],
                itemName,
                getattr(varfont[tableTag], itemName) + delta,
            )

    log.info("Mutating FeatureVariations")
    for tableTag in "GSUB", "GPOS":
        if not tableTag in varfont:
            continue
        table = varfont[tableTag].table
        if not getattr(table, "FeatureVariations", None):
            continue
        variations = table.FeatureVariations
        for record in variations.FeatureVariationRecord:
            applies = True
            for condition in record.ConditionSet.ConditionTable:
                if condition.Format == 1:
                    axisIdx = condition.AxisIndex
                    axisTag = fvar.axes[axisIdx].axisTag
                    Min = condition.FilterRangeMinValue
                    Max = condition.FilterRangeMaxValue
                    v = loc[axisTag]
                    if not (Min <= v <= Max):
                        applies = False
                else:
                    applies = False
                if not applies:
                    break

            if applies:
                assert record.FeatureTableSubstitution.Version == 0x00010000
                for rec in record.FeatureTableSubstitution.SubstitutionRecord:
                    table.FeatureList.FeatureRecord[rec.FeatureIndex].Feature = (
                        rec.Feature
                    )
                break
        del table.FeatureVariations

    if "GDEF" in varfont and varfont["GDEF"].table.Version >= 0x00010003:
        log.info("Mutating GDEF/GPOS/GSUB tables")
        gdef = varfont["GDEF"].table
        instancer = VarStoreInstancer(gdef.VarStore, fvar.axes, loc)

        merger = MutatorMerger(varfont, instancer)
        merger.mergeTables(varfont, [varfont], ["GDEF", "GPOS"])

        # Downgrade GDEF.
        del gdef.VarStore
        gdef.Version = 0x00010002
        if gdef.MarkGlyphSetsDef is None:
            del gdef.MarkGlyphSetsDef
            gdef.Version = 0x00010000

        if not (
            gdef.LigCaretList
            or gdef.MarkAttachClassDef
            or gdef.GlyphClassDef
            or gdef.AttachList
            or (gdef.Version >= 0x00010002 and gdef.MarkGlyphSetsDef)
        ):
            del varfont["GDEF"]

    addidef = False
    if glyf:
        for glyph in glyf.glyphs.values():
            if hasattr(glyph, "program"):
                instructions = glyph.program.getAssembly()
                # If GETVARIATION opcode is used in bytecode of any glyph add IDEF
                addidef = any(op.startswith("GETVARIATION") for op in instructions)
                if addidef:
                    break
        if overlap:
            for glyph_name in glyf.keys():
                glyph = glyf[glyph_name]
                # Set OVERLAP_COMPOUND bit for compound glyphs
                if glyph.isComposite():
                    glyph.components[0].flags |= OVERLAP_COMPOUND
                # Set OVERLAP_SIMPLE bit for simple glyphs
                elif glyph.numberOfContours > 0:
                    glyph.flags[0] |= flagOverlapSimple
    if addidef:
        log.info("Adding IDEF to fpgm table for GETVARIATION opcode")
        asm = []
        if "fpgm" in varfont:
            fpgm = varfont["fpgm"]
            asm = fpgm.program.getAssembly()
        else:
            fpgm = newTable("fpgm")
            fpgm.program = ttProgram.Program()
            varfont["fpgm"] = fpgm
        asm.append("PUSHB[000] 145")
        asm.append("IDEF[ ]")
        args = [str(len(loc))]
        for a in fvar.axes:
            args.append(str(floatToFixed(loc[a.axisTag], 14)))
        asm.append("NPUSHW[ ] " + " ".join(args))
        asm.append("ENDF[ ]")
        fpgm.program.fromAssembly(asm)

        # Change maxp attributes as IDEF is added
        if "maxp" in varfont:
            maxp = varfont["maxp"]
            setattr(
                maxp, "maxInstructionDefs", 1 + getattr(maxp, "maxInstructionDefs", 0)
            )
            setattr(
                maxp,
                "maxStackElements",
                max(len(loc), getattr(maxp, "maxStackElements", 0)),
            )

    if "name" in varfont:
        log.info("Pruning name table")
        exclude = {a.axisNameID for a in fvar.axes}
        for i in fvar.instances:
            exclude.add(i.subfamilyNameID)
            exclude.add(i.postscriptNameID)
        if "ltag" in varfont:
            # Drop the whole 'ltag' table if all its language tags are referenced by
            # name records to be pruned.
            # TODO: prune unused ltag tags and re-enumerate langIDs accordingly
            excludedUnicodeLangIDs = [
                n.langID
                for n in varfont["name"].names
                if n.nameID in exclude and n.platformID == 0 and n.langID != 0xFFFF
            ]
            if set(excludedUnicodeLangIDs) == set(range(len((varfont["ltag"].tags)))):
                del varfont["ltag"]
        varfont["name"].names[:] = [
            n
            for n in varfont["name"].names
            if n.nameID < 256 or n.nameID not in exclude
        ]

    if "wght" in location and "OS/2" in varfont:
        varfont["OS/2"].usWeightClass = otRound(max(1, min(location["wght"], 1000)))
    if "wdth" in location:
        wdth = location["wdth"]
        for percent, widthClass in sorted(OS2_WIDTH_CLASS_VALUES.items()):
            if wdth < percent:
                varfont["OS/2"].usWidthClass = widthClass
                break
        else:
            varfont["OS/2"].usWidthClass = 9
    if "slnt" in location and "post" in varfont:
        varfont["post"].italicAngle = max(-90, min(location["slnt"], 90))

    log.info("Removing variable tables")
    for tag in ("avar", "cvar", "fvar", "gvar", "HVAR", "MVAR", "VVAR", "STAT"):
        if tag in varfont:
            del varfont[tag]

    return varfont


def main(args=None):
    """Instantiate a variation font"""
    from fontTools import configLogger
    import argparse

    parser = argparse.ArgumentParser(
        "fonttools varLib.mutator", description="Instantiate a variable font"
    )
    parser.add_argument("input", metavar="INPUT.ttf", help="Input variable TTF file.")
    parser.add_argument(
        "locargs",
        metavar="AXIS=LOC",
        nargs="*",
        help="List of space separated locations. A location consist in "
        "the name of a variation axis, followed by '=' and a number. E.g.: "
        " wght=700 wdth=80. The default is the location of the base master.",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="OUTPUT.ttf",
        default=None,
        help="Output instance TTF file (default: INPUT-instance.ttf).",
    )
    parser.add_argument(
        "--no-recalc-timestamp",
        dest="recalc_timestamp",
        action="store_false",
        help="Don't set the output font's timestamp to the current time.",
    )
    logging_group = parser.add_mutually_exclusive_group(required=False)
    logging_group.add_argument(
        "-v", "--verbose", action="store_true", help="Run more verbosely."
    )
    logging_group.add_argument(
        "-q", "--quiet", action="store_true", help="Turn verbosity off."
    )
    parser.add_argument(
        "--no-overlap",
        dest="overlap",
        action="store_false",
        help="Don't set OVERLAP_SIMPLE/OVERLAP_COMPOUND glyf flags.",
    )
    options = parser.parse_args(args)

    varfilename = options.input
    outfile = (
        os.path.splitext(varfilename)[0] + "-instance.ttf"
        if not options.output
        else options.output
    )
    configLogger(
        level=("DEBUG" if options.verbose else "ERROR" if options.quiet else "INFO")
    )

    loc = {}
    for arg in options.locargs:
        try:
            tag, val = arg.split("=")
            assert len(tag) <= 4
            loc[tag.ljust(4)] = float(val)
        except (ValueError, AssertionError):
            parser.error("invalid location argument format: %r" % arg)
    log.info("Location: %s", loc)

    log.info("Loading variable font")
    varfont = TTFont(varfilename, recalcTimestamp=options.recalc_timestamp)

    instantiateVariableFont(varfont, loc, inplace=True, overlap=options.overlap)

    log.info("Saving instance font %s", outfile)
    varfont.save(outfile)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        sys.exit(main())
    import doctest

    sys.exit(doctest.testmod().failed)
