from argparse import RawTextHelpFormatter
from fontTools.otlLib.optimize.gpos import COMPRESSION_LEVEL, compact
from fontTools.ttLib import TTFont


def main(args=None):
    """Optimize the layout tables of an existing font"""
    from argparse import ArgumentParser

    from fontTools import configLogger

    parser = ArgumentParser(
        prog="otlLib.optimize",
        description=main.__doc__,
        formatter_class=RawTextHelpFormatter,
    )
    parser.add_argument("font")
    parser.add_argument(
        "-o", metavar="OUTPUTFILE", dest="outfile", default=None, help="output file"
    )
    parser.add_argument(
        "--gpos-compression-level",
        help=COMPRESSION_LEVEL.help,
        default=COMPRESSION_LEVEL.default,
        choices=list(range(10)),
        type=int,
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

    font = TTFont(options.font)
    compact(font, options.gpos_compression_level)
    font.save(options.outfile or options.font)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        sys.exit(main())
    import doctest

    sys.exit(doctest.testmod().failed)
