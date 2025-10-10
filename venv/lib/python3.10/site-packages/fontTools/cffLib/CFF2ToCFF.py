"""CFF2 to CFF converter."""

from fontTools.ttLib import TTFont, newTable
from fontTools.misc.cliTools import makeOutputFileName
from fontTools.misc.psCharStrings import T2StackUseExtractor
from fontTools.cffLib import (
    TopDictIndex,
    buildOrder,
    buildDefaults,
    topDictOperators,
    privateDictOperators,
    FDSelect,
)
from .transforms import desubroutinizeCharString
from .specializer import specializeProgram
from .width import optimizeWidths
from collections import defaultdict
import logging


__all__ = ["convertCFF2ToCFF", "main"]


log = logging.getLogger("fontTools.cffLib")


def _convertCFF2ToCFF(cff, otFont):
    """Converts this object from CFF2 format to CFF format. This conversion
    is done 'in-place'. The conversion cannot be reversed.

    The CFF2 font cannot be variable. (TODO Accept those and convert to the
    default instance?)

    This assumes a decompiled CFF2 table. (i.e. that the object has been
    filled via :meth:`decompile` and e.g. not loaded from XML.)"""

    cff.major = 1

    topDictData = TopDictIndex(None)
    for item in cff.topDictIndex:
        # Iterate over, such that all are decompiled
        item.cff2GetGlyphOrder = None
        topDictData.append(item)
    cff.topDictIndex = topDictData
    topDict = topDictData[0]

    if hasattr(topDict, "VarStore"):
        raise ValueError("Variable CFF2 font cannot be converted to CFF format.")

    opOrder = buildOrder(topDictOperators)
    topDict.order = opOrder
    for key in topDict.rawDict.keys():
        if key not in opOrder:
            del topDict.rawDict[key]
            if hasattr(topDict, key):
                delattr(topDict, key)

    charStrings = topDict.CharStrings

    fdArray = topDict.FDArray
    if not hasattr(topDict, "FDSelect"):
        # FDSelect is optional in CFF2, but required in CFF.
        fdSelect = topDict.FDSelect = FDSelect()
        fdSelect.gidArray = [0] * len(charStrings.charStrings)

    defaults = buildDefaults(privateDictOperators)
    order = buildOrder(privateDictOperators)
    for fd in fdArray:
        fd.setCFF2(False)
        privateDict = fd.Private
        privateDict.order = order
        for key in order:
            if key not in privateDict.rawDict and key in defaults:
                privateDict.rawDict[key] = defaults[key]
        for key in privateDict.rawDict.keys():
            if key not in order:
                del privateDict.rawDict[key]
                if hasattr(privateDict, key):
                    delattr(privateDict, key)

    # Add ending operators
    for cs in charStrings.values():
        cs.decompile()
        cs.program.append("endchar")
    for subrSets in [cff.GlobalSubrs] + [
        getattr(fd.Private, "Subrs", []) for fd in fdArray
    ]:
        for cs in subrSets:
            cs.program.append("return")

    # Add (optimal) width to CharStrings that need it.
    widths = defaultdict(list)
    metrics = otFont["hmtx"].metrics
    for glyphName in charStrings.keys():
        cs, fdIndex = charStrings.getItemAndSelector(glyphName)
        if fdIndex == None:
            fdIndex = 0
        widths[fdIndex].append(metrics[glyphName][0])
    for fdIndex, widthList in widths.items():
        bestDefault, bestNominal = optimizeWidths(widthList)
        private = fdArray[fdIndex].Private
        private.defaultWidthX = bestDefault
        private.nominalWidthX = bestNominal
    for glyphName in charStrings.keys():
        cs, fdIndex = charStrings.getItemAndSelector(glyphName)
        if fdIndex == None:
            fdIndex = 0
        private = fdArray[fdIndex].Private
        width = metrics[glyphName][0]
        if width != private.defaultWidthX:
            cs.program.insert(0, width - private.nominalWidthX)

    # Handle stack use since stack-depth is lower in CFF than in CFF2.
    for glyphName in charStrings.keys():
        cs, fdIndex = charStrings.getItemAndSelector(glyphName)
        if fdIndex is None:
            fdIndex = 0
        private = fdArray[fdIndex].Private
        extractor = T2StackUseExtractor(
            getattr(private, "Subrs", []), cff.GlobalSubrs, private=private
        )
        stackUse = extractor.execute(cs)
        if stackUse > 48:  # CFF stack depth is 48
            desubroutinizeCharString(cs)
            cs.program = specializeProgram(cs.program)

    # Unused subroutines are still in CFF2 (ie. lacking 'return' operator)
    # because they were not decompiled when we added the 'return'.
    # Moreover, some used subroutines may have become unused after the
    # stack-use fixup. So we remove all unused subroutines now.
    cff.remove_unused_subroutines()

    mapping = {
        name: ("cid" + str(n).zfill(5) if n else ".notdef")
        for n, name in enumerate(topDict.charset)
    }
    topDict.charset = [
        "cid" + str(n).zfill(5) if n else ".notdef" for n in range(len(topDict.charset))
    ]
    charStrings.charStrings = {
        mapping[name]: v for name, v in charStrings.charStrings.items()
    }

    topDict.ROS = ("Adobe", "Identity", 0)


def convertCFF2ToCFF(font, *, updatePostTable=True):
    if "CFF2" not in font:
        raise ValueError("Input font does not contain a CFF2 table.")
    cff = font["CFF2"].cff
    _convertCFF2ToCFF(cff, font)
    del font["CFF2"]
    table = font["CFF "] = newTable("CFF ")
    table.cff = cff

    if updatePostTable and "post" in font:
        # Only version supported for fonts with CFF table is 0x00030000 not 0x20000
        post = font["post"]
        if post.formatType == 2.0:
            post.formatType = 3.0


def main(args=None):
    """Convert CFF2 OTF font to CFF OTF font"""
    if args is None:
        import sys

        args = sys.argv[1:]

    import argparse

    parser = argparse.ArgumentParser(
        "fonttools cffLib.CFF2ToCFF",
        description="Convert a non-variable CFF2 font to CFF.",
    )
    parser.add_argument(
        "input", metavar="INPUT.ttf", help="Input OTF file with CFF table."
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="OUTPUT.ttf",
        default=None,
        help="Output instance OTF file (default: INPUT-CFF2.ttf).",
    )
    parser.add_argument(
        "--no-recalc-timestamp",
        dest="recalc_timestamp",
        action="store_false",
        help="Don't set the output font's timestamp to the current time.",
    )
    loggingGroup = parser.add_mutually_exclusive_group(required=False)
    loggingGroup.add_argument(
        "-v", "--verbose", action="store_true", help="Run more verbosely."
    )
    loggingGroup.add_argument(
        "-q", "--quiet", action="store_true", help="Turn verbosity off."
    )
    options = parser.parse_args(args)

    from fontTools import configLogger

    configLogger(
        level=("DEBUG" if options.verbose else "ERROR" if options.quiet else "INFO")
    )

    import os

    infile = options.input
    if not os.path.isfile(infile):
        parser.error("No such file '{}'".format(infile))

    outfile = (
        makeOutputFileName(infile, overWrite=True, suffix="-CFF")
        if not options.output
        else options.output
    )

    font = TTFont(infile, recalcTimestamp=options.recalc_timestamp, recalcBBoxes=False)

    convertCFF2ToCFF(font)

    log.info(
        "Saving %s",
        outfile,
    )
    font.save(outfile)


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
