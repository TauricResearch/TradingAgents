# Copyright 2013 Google, Inc. All Rights Reserved.
#
# Google Author(s): Behdad Esfahbod, Roozbeh Pournader

from fontTools import ttLib
import fontTools.merge.base
from fontTools.merge.cmap import (
    computeMegaGlyphOrder,
    computeMegaCmap,
    renameCFFCharStrings,
)
from fontTools.merge.layout import layoutPreMerge, layoutPostMerge
from fontTools.merge.options import Options
import fontTools.merge.tables
from fontTools.misc.loggingTools import Timer
from functools import reduce
import sys
import logging


log = logging.getLogger("fontTools.merge")
timer = Timer(logger=logging.getLogger(__name__ + ".timer"), level=logging.INFO)


class Merger(object):
    """Font merger.

    This class merges multiple files into a single OpenType font, taking into
    account complexities such as OpenType layout (``GSUB``/``GPOS``) tables and
    cross-font metrics (for example ``hhea.ascent`` is set to the maximum value
    across all the fonts).

    If multiple glyphs map to the same Unicode value, and the glyphs are considered
    sufficiently different (that is, they differ in any of paths, widths, or
    height), then subsequent glyphs are renamed and a lookup in the ``locl``
    feature will be created to disambiguate them. For example, if the arguments
    are an Arabic font and a Latin font and both contain a set of parentheses,
    the Latin glyphs will be renamed to ``parenleft.1`` and ``parenright.1``,
    and a lookup will be inserted into the to ``locl`` feature (creating it if
    necessary) under the ``latn`` script to substitute ``parenleft`` with
    ``parenleft.1`` etc.

    Restrictions:

    - All fonts must have the same units per em.
    - If duplicate glyph disambiguation takes place as described above then the
      fonts must have a ``GSUB`` table.

    Attributes:
            options: Currently unused.
    """

    def __init__(self, options=None):
        if not options:
            options = Options()

        self.options = options

    def _openFonts(self, fontfiles):
        fonts = [ttLib.TTFont(fontfile) for fontfile in fontfiles]
        for font, fontfile in zip(fonts, fontfiles):
            font._merger__fontfile = fontfile
            font._merger__name = font["name"].getDebugName(4)
        return fonts

    def merge(self, fontfiles):
        """Merges fonts together.

        Args:
                fontfiles: A list of file names to be merged

        Returns:
                A :class:`fontTools.ttLib.TTFont` object. Call the ``save`` method on
                this to write it out to an OTF file.
        """
        #
        # Settle on a mega glyph order.
        #
        fonts = self._openFonts(fontfiles)
        glyphOrders = [list(font.getGlyphOrder()) for font in fonts]
        computeMegaGlyphOrder(self, glyphOrders)

        # Take first input file sfntVersion
        sfntVersion = fonts[0].sfntVersion

        # Reload fonts and set new glyph names on them.
        fonts = self._openFonts(fontfiles)
        for font, glyphOrder in zip(fonts, glyphOrders):
            font.setGlyphOrder(glyphOrder)
            if "CFF " in font:
                renameCFFCharStrings(self, glyphOrder, font["CFF "])

        cmaps = [font["cmap"] for font in fonts]
        self.duplicateGlyphsPerFont = [{} for _ in fonts]
        computeMegaCmap(self, cmaps)

        mega = ttLib.TTFont(sfntVersion=sfntVersion)
        mega.setGlyphOrder(self.glyphOrder)

        for font in fonts:
            self._preMerge(font)

        self.fonts = fonts

        allTags = reduce(set.union, (list(font.keys()) for font in fonts), set())
        allTags.remove("GlyphOrder")

        for tag in sorted(allTags):
            if tag in self.options.drop_tables:
                continue

            with timer("merge '%s'" % tag):
                tables = [font.get(tag, NotImplemented) for font in fonts]

                log.info("Merging '%s'.", tag)
                clazz = ttLib.getTableClass(tag)
                table = clazz(tag).merge(self, tables)
                # XXX Clean this up and use:  table = mergeObjects(tables)

                if table is not NotImplemented and table is not False:
                    mega[tag] = table
                    log.info("Merged '%s'.", tag)
                else:
                    log.info("Dropped '%s'.", tag)

        del self.duplicateGlyphsPerFont
        del self.fonts

        self._postMerge(mega)

        return mega

    def mergeObjects(self, returnTable, logic, tables):
        # Right now we don't use self at all.  Will use in the future
        # for options and logging.

        allKeys = set.union(
            set(),
            *(vars(table).keys() for table in tables if table is not NotImplemented),
        )
        for key in allKeys:
            log.info(" %s", key)
            try:
                mergeLogic = logic[key]
            except KeyError:
                try:
                    mergeLogic = logic["*"]
                except KeyError:
                    raise Exception(
                        "Don't know how to merge key %s of class %s"
                        % (key, returnTable.__class__.__name__)
                    )
            if mergeLogic is NotImplemented:
                continue
            value = mergeLogic(getattr(table, key, NotImplemented) for table in tables)
            if value is not NotImplemented:
                setattr(returnTable, key, value)

        return returnTable

    def _preMerge(self, font):
        layoutPreMerge(font)

    def _postMerge(self, font):
        layoutPostMerge(font)

        if "OS/2" in font:
            # https://github.com/fonttools/fonttools/issues/2538
            # TODO: Add an option to disable this?
            font["OS/2"].recalcAvgCharWidth(font)


__all__ = ["Options", "Merger", "main"]


@timer("make one with everything (TOTAL TIME)")
def main(args=None):
    """Merge multiple fonts into one"""
    from fontTools import configLogger

    if args is None:
        args = sys.argv[1:]

    options = Options()
    args = options.parse_opts(args)
    fontfiles = []
    if options.input_file:
        with open(options.input_file) as inputfile:
            fontfiles = [
                line.strip()
                for line in inputfile.readlines()
                if not line.lstrip().startswith("#")
            ]
    for g in args:
        fontfiles.append(g)

    if len(fontfiles) < 1:
        print(
            "usage: fonttools merge [font1 ... fontN] [--input-file=filelist.txt] [--output-file=merged.ttf] [--import-file=tables.ttx]",
            file=sys.stderr,
        )
        print(
            "                                   [--drop-tables=tags] [--verbose] [--timing]",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        print(" font1 ... fontN              Files to merge.", file=sys.stderr)
        print(
            " --input-file=<filename>      Read files to merge from a text file, each path new line. # Comment lines allowed.",
            file=sys.stderr,
        )
        print(
            " --output-file=<filename>     Specify output file name (default: merged.ttf).",
            file=sys.stderr,
        )
        print(
            " --import-file=<filename>     TTX file to import after merging. This can be used to set metadata.",
            file=sys.stderr,
        )
        print(
            " --drop-tables=<table tags>   Comma separated list of table tags to skip, case sensitive.",
            file=sys.stderr,
        )
        print(
            " --verbose                    Output progress information.",
            file=sys.stderr,
        )
        print(" --timing                     Output progress timing.", file=sys.stderr)
        return 1

    configLogger(level=logging.INFO if options.verbose else logging.WARNING)
    if options.timing:
        timer.logger.setLevel(logging.DEBUG)
    else:
        timer.logger.disabled = True

    merger = Merger(options=options)
    font = merger.merge(fontfiles)

    if options.import_file:
        font.importXML(options.import_file)

    with timer("compile and save font"):
        font.save(options.output_file)


if __name__ == "__main__":
    sys.exit(main())
