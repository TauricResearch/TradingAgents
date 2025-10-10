import argparse
import logging
import sys
from io import StringIO
from pathlib import Path

from fontTools import configLogger
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.feaLib.error import FeatureLibError
from fontTools.feaLib.lexer import Lexer
from fontTools.misc.cliTools import makeOutputFileName
from fontTools.ttLib import TTFont, TTLibError
from fontTools.voltLib.parser import Parser
from fontTools.voltLib.voltToFea import TABLES, VoltToFea

log = logging.getLogger("fontTools.feaLib")

SUPPORTED_TABLES = TABLES + ["cmap"]


def invalid_fea_glyph_name(name):
    """Check if the glyph name is valid according to FEA syntax."""
    if name[0] not in Lexer.CHAR_NAME_START_:
        return True
    if any(c not in Lexer.CHAR_NAME_CONTINUATION_ for c in name[1:]):
        return True
    return False


def sanitize_glyph_name(name):
    """Sanitize the glyph name to ensure it is valid according to FEA syntax."""
    sanitized = ""
    for i, c in enumerate(name):
        if i == 0 and c not in Lexer.CHAR_NAME_START_:
            sanitized += "a" + c
        elif c not in Lexer.CHAR_NAME_CONTINUATION_:
            sanitized += "_"
        else:
            sanitized += c

    return sanitized


def main(args=None):
    """Build tables from a MS VOLT project into an OTF font"""
    parser = argparse.ArgumentParser(
        description="Use fontTools to compile MS VOLT projects."
    )
    parser.add_argument(
        "input",
        metavar="INPUT",
        help="Path to the input font/VTP file to process",
        type=Path,
    )
    parser.add_argument(
        "-f",
        "--font",
        metavar="INPUT_FONT",
        help="Path to the input font (if INPUT is a VTP file)",
        type=Path,
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        metavar="OUTPUT",
        help="Path to the output font.",
        type=Path,
    )
    parser.add_argument(
        "-t",
        "--tables",
        metavar="TABLE_TAG",
        choices=SUPPORTED_TABLES,
        nargs="+",
        help="Specify the table(s) to be built.",
    )
    parser.add_argument(
        "-F",
        "--debug-feature-file",
        help="Write the generated feature file to disk.",
        action="store_true",
    )
    parser.add_argument(
        "--ship",
        help="Remove source VOLT tables from output font.",
        action="store_true",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Increase the logger verbosity. Multiple -v options are allowed.",
        action="count",
        default=0,
    )
    parser.add_argument(
        "-T",
        "--traceback",
        help="show traceback for exceptions.",
        action="store_true",
    )
    options = parser.parse_args(args)

    levels = ["WARNING", "INFO", "DEBUG"]
    configLogger(level=levels[min(len(levels) - 1, options.verbose)])

    output_font = options.output or Path(
        makeOutputFileName(options.font or options.input)
    )
    log.info(f"Compiling MS VOLT to '{output_font}'")

    file_or_path = options.input
    font = None

    # If the input is a font file, extract the VOLT data from the "TSIV" table
    try:
        font = TTFont(file_or_path)
        if "TSIV" in font:
            file_or_path = StringIO(font["TSIV"].data.decode("utf-8"))
        else:
            log.error('"TSIV" table is missing')
            return 1
    except TTLibError:
        pass

    # If input is not a font file, the font must be provided
    if font is None:
        if not options.font:
            log.error("Please provide an input font")
            return 1
        font = TTFont(options.font)

    # FEA syntax does not allow some glyph names that VOLT accepts, so if we
    # found such glyph name we will temporarily rename such glyphs.
    glyphOrder = font.getGlyphOrder()
    tempGlyphOrder = None
    if any(invalid_fea_glyph_name(n) for n in glyphOrder):
        tempGlyphOrder = []
        for n in glyphOrder:
            if invalid_fea_glyph_name(n):
                n = sanitize_glyph_name(n)
                existing = set(tempGlyphOrder) | set(glyphOrder)
                while n in existing:
                    n = "a" + n
            tempGlyphOrder.append(n)
        font.setGlyphOrder(tempGlyphOrder)

    doc = Parser(file_or_path).parse()

    log.info("Converting VTP data to FEA")
    converter = VoltToFea(doc, font)
    try:
        fea = converter.convert(options.tables, ignore_unsupported_settings=True)
    except NotImplementedError as e:
        if options.traceback:
            raise
        location = getattr(e.args[0], "location", None)
        message = f'"{e}" is not supported'
        if location:
            path, line, column = location
            log.error(f"{path}:{line}:{column}: {message}")
        else:
            log.error(message)
        return 1

    fea_filename = options.input
    if options.debug_feature_file:
        fea_filename = output_font.with_suffix(".fea")
        log.info(f"Writing FEA to '{fea_filename}'")
        with open(fea_filename, "w") as fp:
            fp.write(fea)

    log.info("Compiling FEA to OpenType tables")
    try:
        addOpenTypeFeaturesFromString(
            font,
            fea,
            filename=fea_filename,
            tables=options.tables,
        )
    except FeatureLibError as e:
        if options.traceback:
            raise
        log.error(e)
        return 1

    if options.ship:
        for tag in ["TSIV", "TSIS", "TSIP", "TSID"]:
            if tag in font:
                del font[tag]

    # Restore original glyph names.
    if tempGlyphOrder:
        import io

        f = io.BytesIO()
        font.save(f)
        font = TTFont(f)
        font.setGlyphOrder(glyphOrder)
        font["post"].extraNames = []

    font.save(output_font)


if __name__ == "__main__":
    sys.exit(main())
