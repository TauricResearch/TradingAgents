import logging

log = logging.getLogger("fontTools.varLib.avar")


def main(args=None):
    from fontTools.ttLib import TTFont
    from fontTools.misc.cliTools import makeOutputFileName
    from fontTools import configLogger
    import argparse
    import sys

    print(
        "WARNING: This script is deprecated. Use `fonttools varLib.avar.build` "
        "or `fonttools varLib.avar.unbuild` instead.\n",
        file=sys.stderr,
    )

    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(
        "fonttools varLib.avar",
        description="Add `avar` table from designspace file to variable font.",
    )
    parser.add_argument("font", metavar="varfont.ttf", help="Variable-font file.")
    parser.add_argument(
        "designspace",
        metavar="family.designspace",
        help="Designspace file.",
        nargs="?",
        default=None,
    )
    parser.add_argument(
        "-o",
        "--output-file",
        type=str,
        help="Output font file name.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Run more verbosely."
    )

    options = parser.parse_args(args)

    configLogger(level=("INFO" if options.verbose else "WARNING"))

    font = TTFont(options.font)

    if options.designspace is None:
        from .unbuild import unbuild

        unbuild(font)
        return 0

    from .build import build

    build(font, options.designspace)

    if options.output_file is None:
        outfile = makeOutputFileName(options.font, overWrite=True, suffix=".avar")
    else:
        outfile = options.output_file
    if outfile:
        log.info("Saving %s", outfile)
        font.save(outfile)


if __name__ == "__main__":
    import sys

    sys.exit(main())
