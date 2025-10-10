import sys
from fontTools.ttLib import OPTIMIZE_FONT_SPEED, TTLibError, TTLibFileIsCollectionError
from fontTools.ttLib.ttFont import *
from fontTools.ttLib.ttCollection import TTCollection


def main(args=None):
    """Open/save fonts with TTFont() or TTCollection()

      ./fonttools ttLib [-oFILE] [-yNUMBER] files...

    If multiple files are given on the command-line,
    they are each opened (as a font or collection),
    and added to the font list.

    If -o (output-file) argument is given, the font
    list is then saved to the output file, either as
    a single font, if there is only one font, or as
    a collection otherwise.

    If -y (font-number) argument is given, only the
    specified font from collections is opened.

    The above allow extracting a single font from a
    collection, or combining multiple fonts into a
    collection.

    If --lazy or --no-lazy are give, those are passed
    to the TTFont() or TTCollection() constructors.
    """
    from fontTools import configLogger

    if args is None:
        args = sys.argv[1:]

    import argparse

    parser = argparse.ArgumentParser(
        "fonttools ttLib",
        description="Open/save fonts with TTFont() or TTCollection()",
        epilog="""
		If multiple files are given on the command-line,
		they are each opened (as a font or collection),
		and added to the font list.

		The above, when combined with -o / --output,
		allows for extracting a single font from a
		collection, or combining multiple fonts into a
		collection.
		""",
    )
    parser.add_argument("font", metavar="font", nargs="*", help="Font file.")
    parser.add_argument(
        "-t", "--table", metavar="table", action="append", help="Tables to decompile."
    )
    parser.add_argument(
        "-o", "--output", metavar="FILE", default=None, help="Output file."
    )
    parser.add_argument(
        "-y", metavar="NUMBER", default=-1, help="Font number to load from collections."
    )
    parser.add_argument(
        "--lazy", action="store_true", default=None, help="Load fonts lazily."
    )
    parser.add_argument(
        "--no-lazy", dest="lazy", action="store_false", help="Load fonts immediately."
    )
    parser.add_argument(
        "--flavor",
        dest="flavor",
        default=None,
        help="Flavor of output font. 'woff' or 'woff2'.",
    )
    parser.add_argument(
        "--no-recalc-timestamp",
        dest="recalcTimestamp",
        action="store_false",
        help="Keep the original font 'modified' timestamp.",
    )
    parser.add_argument(
        "-b",
        dest="recalcBBoxes",
        action="store_false",
        help="Don't recalc glyph bounding boxes: use the values in the original font.",
    )
    parser.add_argument(
        "--optimize-font-speed",
        action="store_true",
        help=(
            "Enable optimizations that prioritize speed over file size. This "
            "mainly affects how glyf table and gvar / VARC tables are compiled."
        ),
    )
    options = parser.parse_args(args)

    fontNumber = int(options.y) if options.y is not None else None
    outFile = options.output
    lazy = options.lazy
    flavor = options.flavor
    tables = options.table
    recalcBBoxes = options.recalcBBoxes
    recalcTimestamp = options.recalcTimestamp
    optimizeFontSpeed = options.optimize_font_speed

    fonts = []
    for f in options.font:
        try:
            font = TTFont(
                f,
                recalcBBoxes=recalcBBoxes,
                recalcTimestamp=recalcTimestamp,
                fontNumber=fontNumber,
                lazy=lazy,
            )
            if optimizeFontSpeed:
                font.cfg[OPTIMIZE_FONT_SPEED] = optimizeFontSpeed
            fonts.append(font)
        except TTLibFileIsCollectionError:
            collection = TTCollection(f, lazy=lazy)
            fonts.extend(collection.fonts)

    if tables is None:
        if lazy is False:
            tables = ["*"]
        elif optimizeFontSpeed:
            tables = {"glyf", "gvar", "VARC"}.intersection(font.keys())
        else:
            tables = []
    for font in fonts:
        if "GlyphOrder" in tables:
            font.getGlyphOrder()
        for table in tables if "*" not in tables else font.keys():
            font[table]  # Decompiles

    if outFile is not None:
        if len(fonts) == 1:
            fonts[0].flavor = flavor
            fonts[0].save(outFile)
        else:
            if flavor is not None:
                raise TTLibError("Cannot set flavor for collections.")
            collection = TTCollection()
            collection.fonts = fonts
            collection.save(outFile)


if __name__ == "__main__":
    sys.exit(main())
