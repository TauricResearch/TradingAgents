from fontTools.misc.roundTools import noRound
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables.otBase import OTTableWriter
from fontTools.varLib import HVAR_FIELDS, VVAR_FIELDS, _add_VHVAR
from fontTools.varLib import builder, models, varStore
from fontTools.misc.fixedTools import fixedToFloat as fi2fl
from fontTools.misc.cliTools import makeOutputFileName
from functools import partial
import logging

log = logging.getLogger("fontTools.varLib.avar")


def _get_advance_metrics(font, axisTags, tableFields):
    # There's two ways we can go from here:
    # 1. For each glyph, at each master peak, compute the value of the
    #    advance width at that peak.  Then pass these all to a VariationModel
    #    builder to compute back the deltas.
    # 2. For each master peak, pull out the deltas of the advance width directly,
    #    and feed these to the VarStoreBuilder, forgoing the remodeling step.
    # We'll go with the second option, as it's simpler, faster, and more direct.
    gvar = font["gvar"]
    vhAdvanceDeltasAndSupports = {}
    glyphOrder = font.getGlyphOrder()
    phantomIndex = tableFields.phantomIndex
    for glyphName in glyphOrder:
        supports = []
        deltas = []
        variations = gvar.variations.get(glyphName, [])

        for tv in variations:
            supports.append(tv.axes)
            phantoms = tv.coordinates[-4:]
            phantoms = phantoms[phantomIndex * 2 : phantomIndex * 2 + 2]
            assert len(phantoms) == 2
            phantoms[0] = phantoms[0][phantomIndex] if phantoms[0] is not None else 0
            phantoms[1] = phantoms[1][phantomIndex] if phantoms[1] is not None else 0
            deltas.append(phantoms[1] - phantoms[0])

        vhAdvanceDeltasAndSupports[glyphName] = (deltas, supports)

    vOrigDeltasAndSupports = None  # TODO

    return vhAdvanceDeltasAndSupports, vOrigDeltasAndSupports


def add_HVAR(font):
    if "HVAR" in font:
        del font["HVAR"]
    axisTags = [axis.axisTag for axis in font["fvar"].axes]
    getAdvanceMetrics = partial(_get_advance_metrics, font, axisTags, HVAR_FIELDS)
    _add_VHVAR(font, axisTags, HVAR_FIELDS, getAdvanceMetrics)


def add_VVAR(font):
    if "VVAR" in font:
        del font["VVAR"]
    getAdvanceMetrics = partial(_get_advance_metrics, font, axisTags, VVAR_FIELDS)
    axisTags = [axis.axisTag for axis in font["fvar"].axes]
    _add_VHVAR(font, axisTags, VVAR_FIELDS, getAdvanceMetrics)


def main(args=None):
    """Add `HVAR` table to variable font."""

    if args is None:
        import sys

        args = sys.argv[1:]

    from fontTools import configLogger
    from fontTools.designspaceLib import DesignSpaceDocument
    import argparse

    parser = argparse.ArgumentParser(
        "fonttools varLib.hvar",
        description="Add `HVAR` table from to variable font.",
    )
    parser.add_argument("font", metavar="varfont.ttf", help="Variable-font file.")
    parser.add_argument(
        "-o",
        "--output-file",
        type=str,
        help="Output font file name.",
    )

    options = parser.parse_args(args)

    configLogger(level="WARNING")

    font = TTFont(options.font)
    if not "fvar" in font:
        log.error("Not a variable font.")
        return 1

    add_HVAR(font)
    if "vmtx" in font:
        add_VVAR(font)

    if options.output_file is None:
        outfile = makeOutputFileName(options.font, overWrite=True, suffix=".hvar")
    else:
        outfile = options.output_file
    if outfile:
        log.info("Saving %s", outfile)
        font.save(outfile)


if __name__ == "__main__":
    import sys

    sys.exit(main())
