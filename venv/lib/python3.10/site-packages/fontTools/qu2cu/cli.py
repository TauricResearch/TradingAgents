import os
import argparse
import logging
from fontTools.misc.cliTools import makeOutputFileName
from fontTools.ttLib import TTFont
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
import fontTools


logger = logging.getLogger("fontTools.qu2cu")


def _font_to_cubic(input_path, output_path=None, **kwargs):
    font = TTFont(input_path)
    logger.info("Converting curves for %s", input_path)

    stats = {} if kwargs["dump_stats"] else None
    qu2cu_kwargs = {
        "stats": stats,
        "max_err": kwargs["max_err_em"] * font["head"].unitsPerEm,
        "all_cubic": kwargs["all_cubic"],
    }

    assert "gvar" not in font, "Cannot convert variable font"
    glyphSet = font.getGlyphSet()
    glyphOrder = font.getGlyphOrder()
    glyf = font["glyf"]
    for glyphName in glyphOrder:
        glyph = glyphSet[glyphName]
        ttpen = TTGlyphPen(glyphSet)
        pen = Qu2CuPen(ttpen, **qu2cu_kwargs)
        glyph.draw(pen)
        glyf[glyphName] = ttpen.glyph(dropImpliedOnCurves=True)

    font["head"].glyphDataFormat = 1

    if kwargs["dump_stats"]:
        logger.info("Stats: %s", stats)

    logger.info("Saving %s", output_path)
    font.save(output_path)


def _main(args=None):
    """Convert an OpenType font from quadratic to cubic curves"""
    parser = argparse.ArgumentParser(prog="qu2cu")
    parser.add_argument("--version", action="version", version=fontTools.__version__)
    parser.add_argument(
        "infiles",
        nargs="+",
        metavar="INPUT",
        help="one or more input TTF source file(s).",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument(
        "-e",
        "--conversion-error",
        type=float,
        metavar="ERROR",
        default=0.001,
        help="maxiumum approximation error measured in EM (default: 0.001)",
    )
    parser.add_argument(
        "-c",
        "--all-cubic",
        default=False,
        action="store_true",
        help="whether to only use cubic curves",
    )

    output_parser = parser.add_mutually_exclusive_group()
    output_parser.add_argument(
        "-o",
        "--output-file",
        default=None,
        metavar="OUTPUT",
        help=("output filename for the converted TTF."),
    )
    output_parser.add_argument(
        "-d",
        "--output-dir",
        default=None,
        metavar="DIRECTORY",
        help="output directory where to save converted TTFs",
    )

    options = parser.parse_args(args)

    if not options.verbose:
        level = "WARNING"
    elif options.verbose == 1:
        level = "INFO"
    else:
        level = "DEBUG"
    logging.basicConfig(level=level)

    if len(options.infiles) > 1 and options.output_file:
        parser.error("-o/--output-file can't be used with multile inputs")

    if options.output_dir:
        output_dir = options.output_dir
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)
        elif not os.path.isdir(output_dir):
            parser.error("'%s' is not a directory" % output_dir)
        output_paths = [
            os.path.join(output_dir, os.path.basename(p)) for p in options.infiles
        ]
    elif options.output_file:
        output_paths = [options.output_file]
    else:
        output_paths = [
            makeOutputFileName(p, overWrite=True, suffix=".cubic")
            for p in options.infiles
        ]

    kwargs = dict(
        dump_stats=options.verbose > 0,
        max_err_em=options.conversion_error,
        all_cubic=options.all_cubic,
    )

    for input_path, output_path in zip(options.infiles, output_paths):
        _font_to_cubic(input_path, output_path, **kwargs)
