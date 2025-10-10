# Copyright 2013 Google, Inc. All Rights Reserved.
#
# Google Author(s): Behdad Esfahbod

from __future__ import annotations

from fontTools import config
from fontTools.misc.roundTools import otRound
from fontTools import ttLib
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.otBase import USE_HARFBUZZ_REPACKER
from fontTools.otlLib.maxContextCalc import maxCtxFont
from fontTools.pens.basePen import NullPen
from fontTools.misc.loggingTools import Timer
from fontTools.misc.cliTools import makeOutputFileName
from fontTools.subset.util import _add_method, _uniq_sort
from fontTools.subset.cff import *
from fontTools.subset.svg import *
from fontTools.varLib import varStore, multiVarStore  # For monkey-patching
from fontTools.ttLib.tables._n_a_m_e import NameRecordVisitor, makeName
from fontTools.unicodedata import mirrored
import sys
import struct
import array
import logging
from collections import Counter, defaultdict
from functools import reduce
from types import MethodType

__usage__ = "fonttools subset font-file [glyph...] [--option=value]..."

__doc__ = (
    """\
fonttools subset -- OpenType font subsetter and optimizer

fonttools subset is an OpenType font subsetter and optimizer, based on
fontTools. It accepts any TT- or CFF-flavored OpenType (.otf or .ttf)
or WOFF (.woff) font file. The subsetted glyph set is based on the
specified glyphs or characters, and specified OpenType layout features.

The tool also performs some size-reducing optimizations, aimed for using
subset fonts as webfonts.  Individual optimizations can be enabled or
disabled, and are enabled by default when they are safe.

Usage: """
    + __usage__
    + """

At least one glyph or one of --gids, --gids-file, --glyphs, --glyphs-file,
--text, --text-file, --unicodes, or --unicodes-file, must be specified.

Args:

font-file
  The input font file.
glyph
  Specify one or more glyph identifiers to include in the subset. Must be
  PS glyph names, or the special string '*' to keep the entire glyph set.

Initial glyph set specification
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

These options populate the initial glyph set. Same option can appear
multiple times, and the results are accummulated.

--gids=<NNN>[,<NNN>...]
  Specify comma/whitespace-separated list of glyph IDs or ranges as decimal
  numbers.  For example, --gids=10-12,14 adds glyphs with numbers 10, 11,
  12, and 14.

--gids-file=<path>
  Like --gids but reads from a file. Anything after a '#' on any line is
  ignored as comments.

--glyphs=<glyphname>[,<glyphname>...]
  Specify comma/whitespace-separated PS glyph names to add to the subset.
  Note that only PS glyph names are accepted, not gidNNN, U+XXXX, etc
  that are accepted on the command line.  The special string '*' will keep
  the entire glyph set.

--glyphs-file=<path>
  Like --glyphs but reads from a file. Anything after a '#' on any line
  is ignored as comments.

--text=<text>
  Specify characters to include in the subset, as UTF-8 string.

--text-file=<path>
  Like --text but reads from a file. Newline character are not added to
  the subset.

--unicodes=<XXXX>[,<XXXX>...]
  Specify comma/whitespace-separated list of Unicode codepoints or
  ranges as hex numbers, optionally prefixed with 'U+', 'u', etc.
  For example, --unicodes=41-5a,61-7a adds ASCII letters, so does
  the more verbose --unicodes=U+0041-005A,U+0061-007A.
  The special strings '*' will choose all Unicode characters mapped
  by the font.

--unicodes-file=<path>
  Like --unicodes, but reads from a file. Anything after a '#' on any
  line in the file is ignored as comments.

--ignore-missing-glyphs
  Do not fail if some requested glyphs or gids are not available in
  the font.

--no-ignore-missing-glyphs
  Stop and fail if some requested glyphs or gids are not available
  in the font. [default]

--ignore-missing-unicodes [default]
  Do not fail if some requested Unicode characters (including those
  indirectly specified using --text or --text-file) are not available
  in the font.

--no-ignore-missing-unicodes
  Stop and fail if some requested Unicode characters are not available
  in the font.
  Note the default discrepancy between ignoring missing glyphs versus
  unicodes.  This is for historical reasons and in the future
  --no-ignore-missing-unicodes might become default.

Other options
^^^^^^^^^^^^^

For the other options listed below, to see the current value of the option,
pass a value of '?' to it, with or without a '='. In some environments,
you might need to escape the question mark, like this: '--glyph-names\\?'.

Examples::

    $ fonttools subset --glyph-names?
    Current setting for 'glyph-names' is: False
    $ fonttools subset --name-IDs=?
    Current setting for 'name-IDs' is: [0, 1, 2, 3, 4, 5, 6]
    $ fonttools subset --hinting? --no-hinting --hinting?
    Current setting for 'hinting' is: True
    Current setting for 'hinting' is: False

Output options
^^^^^^^^^^^^^^

--output-file=<path>
  The output font file. If not specified, the subsetted font
  will be saved in as font-file.subset.

--flavor=<type>
  Specify flavor of output font file. May be 'woff' or 'woff2'.
  Note that WOFF2 requires the Brotli Python extension, available
  at https://github.com/google/brotli

--with-zopfli
  Use the Google Zopfli algorithm to compress WOFF. The output is 3-8 %
  smaller than pure zlib, but the compression speed is much slower.
  The Zopfli Python bindings are available at:
  https://pypi.python.org/pypi/zopfli

--harfbuzz-repacker
  By default, we serialize GPOS/GSUB using the HarfBuzz Repacker when
  uharfbuzz can be imported and is successful, otherwise fall back to
  the pure-python serializer. Set the option to force using the HarfBuzz
  Repacker (raises an error if uharfbuzz can't be found or fails).

--no-harfbuzz-repacker
  Always use the pure-python serializer even if uharfbuzz is available.

Glyph set expansion
^^^^^^^^^^^^^^^^^^^

These options control how additional glyphs are added to the subset.

--retain-gids
  Retain glyph indices; just empty glyphs not needed in-place.

--notdef-glyph
  Add the '.notdef' glyph to the subset (ie, keep it). [default]

--no-notdef-glyph
  Drop the '.notdef' glyph unless specified in the glyph set. This
  saves a few bytes, but is not possible for Postscript-flavored
  fonts, as those require '.notdef'. For TrueType-flavored fonts,
  this works fine as long as no unsupported glyphs are requested
  from the font.

--notdef-outline
  Keep the outline of '.notdef' glyph. The '.notdef' glyph outline is
  used when glyphs not supported by the font are to be shown. It is not
  needed otherwise.

--no-notdef-outline
  When including a '.notdef' glyph, remove its outline. This saves
  a few bytes. [default]

--recommended-glyphs
  Add glyphs 0, 1, 2, and 3 to the subset, as recommended for
  TrueType-flavored fonts: '.notdef', 'NULL' or '.null', 'CR', 'space'.
  Some legacy software might require this, but no modern system does.

--no-recommended-glyphs
  Do not add glyphs 0, 1, 2, and 3 to the subset, unless specified in
  glyph set. [default]

--no-layout-closure
  Do not expand glyph set to add glyphs produced by OpenType layout
  features.  Instead, OpenType layout features will be subset to only
  rules that are relevant to the otherwise-specified glyph set.

--layout-features[+|-]=<feature>[,<feature>...]
  Specify (=), add to (+=) or exclude from (-=) the comma-separated
  set of OpenType layout feature tags that will be preserved.
  Glyph variants used by the preserved features are added to the
  specified subset glyph set. By default, 'calt', 'ccmp', 'clig', 'curs',
  'dnom', 'frac', 'kern', 'liga', 'locl', 'mark', 'mkmk', 'numr', 'rclt',
  'rlig', 'rvrn', and all features required for script shaping are
  preserved. To see the full list, try '--layout-features=?'.
  Use '*' to keep all features.
  Multiple --layout-features options can be provided if necessary.
  Examples:

    --layout-features+=onum,pnum,ss01
        * Keep the default set of features and 'onum', 'pnum', 'ss01'.
    --layout-features-='mark','mkmk'
        * Keep the default set of features but drop 'mark' and 'mkmk'.
    --layout-features='kern'
        * Only keep the 'kern' feature, drop all others.
    --layout-features=''
        * Drop all features.
    --layout-features='*'
        * Keep all features.
    --layout-features+=aalt --layout-features-=vrt2
        * Keep default set of features plus 'aalt', but drop 'vrt2'.

--layout-scripts[+|-]=<script>[,<script>...]
  Specify (=), add to (+=) or exclude from (-=) the comma-separated
  set of OpenType layout script tags that will be preserved. LangSys tags
  can be appended to script tag, separated by '.', for example:
  'arab.dflt,arab.URD,latn.TRK'. By default all scripts are retained ('*').

Hinting options
^^^^^^^^^^^^^^^

--hinting
  Keep hinting [default]

--no-hinting
  Drop glyph-specific hinting and font-wide hinting tables, as well
  as remove hinting-related bits and pieces from other tables (eg. GPOS).
  See --hinting-tables for list of tables that are dropped by default.
  Instructions and hints are stripped from 'glyf' and 'CFF ' tables
  respectively. This produces (sometimes up to 30%) smaller fonts that
  are suitable for extremely high-resolution systems, like high-end
  mobile devices and retina displays.

Optimization options
^^^^^^^^^^^^^^^^^^^^

--desubroutinize
  Remove CFF use of subroutinizes.  Subroutinization is a way to make CFF
  fonts smaller.  For small subsets however, desubroutinizing might make
  the font smaller.  It has even been reported that desubroutinized CFF
  fonts compress better (produce smaller output) WOFF and WOFF2 fonts.
  Also see note under --no-hinting.

--no-desubroutinize [default]
  Leave CFF subroutinizes as is, only throw away unused subroutinizes.

Font table options
^^^^^^^^^^^^^^^^^^

--drop-tables[+|-]=<table>[,<table>...]
  Specify (=), add to (+=) or exclude from (-=) the comma-separated
  set of tables that will be be dropped.
  By default, the following tables are dropped:
  'JSTF', 'DSIG', 'EBDT', 'EBLC', 'EBSC', 'PCLT', 'LTSH'
  and Graphite tables: 'Feat', 'Glat', 'Gloc', 'Silf', 'Sill'.
  The tool will attempt to subset the remaining tables.

  Examples:

  --drop-tables-=BASE
      * Drop the default set of tables but keep 'BASE'.

  --drop-tables+=GSUB
      * Drop the default set of tables and 'GSUB'.

  --drop-tables=DSIG
      * Only drop the 'DSIG' table, keep all others.

  --drop-tables=
      * Keep all tables.

--no-subset-tables+=<table>[,<table>...]
  Add to the set of tables that will not be subsetted.
  By default, the following tables are included in this list, as
  they do not need subsetting (ignore the fact that 'loca' is listed
  here): 'gasp', 'head', 'hhea', 'maxp', 'vhea', 'OS/2', 'loca', 'name',
  'cvt ', 'fpgm', 'prep', 'VMDX', 'DSIG', 'CPAL', 'MVAR', 'cvar', 'STAT'.
  By default, tables that the tool does not know how to subset and are not
  specified here will be dropped from the font, unless --passthrough-tables
  option is passed.

  Example:

   --no-subset-tables+=FFTM
      * Keep 'FFTM' table in the font by preventing subsetting.

--passthrough-tables
  Do not drop tables that the tool does not know how to subset.

--no-passthrough-tables
  Tables that the tool does not know how to subset and are not specified
  in --no-subset-tables will be dropped from the font. [default]

--hinting-tables[-]=<table>[,<table>...]
  Specify (=), add to (+=) or exclude from (-=) the list of font-wide
  hinting tables that will be dropped if --no-hinting is specified.

  Examples:

  --hinting-tables-=VDMX
      * Drop font-wide hinting tables except 'VDMX'.
  --hinting-tables=
      * Keep all font-wide hinting tables (but strip hints from glyphs).

--legacy-kern
  Keep TrueType 'kern' table even when OpenType 'GPOS' is available.

--no-legacy-kern
  Drop TrueType 'kern' table if OpenType 'GPOS' is available. [default]

Font naming options
^^^^^^^^^^^^^^^^^^^

These options control what is retained in the 'name' table. For numerical
codes, see: http://www.microsoft.com/typography/otspec/name.htm

--name-IDs[+|-]=<nameID>[,<nameID>...]
  Specify (=), add to (+=) or exclude from (-=) the set of 'name' table
  entry nameIDs that will be preserved. By default, only nameIDs between 0
  and 6 are preserved, the rest are dropped. Use '*' to keep all entries.

  Examples:

  --name-IDs+=7,8,9
      * Also keep Trademark, Manufacturer and Designer name entries.
  --name-IDs=
      * Drop all 'name' table entries.
  --name-IDs=*
      * keep all 'name' table entries

--name-legacy
  Keep legacy (non-Unicode) 'name' table entries (0.x, 1.x etc.).
  XXX Note: This might be needed for some fonts that have no Unicode name
  entires for English. See: https://github.com/fonttools/fonttools/issues/146

--no-name-legacy
  Drop legacy (non-Unicode) 'name' table entries [default]

--name-languages[+|-]=<langID>[,<langID>]
  Specify (=), add to (+=) or exclude from (-=) the set of 'name' table
  langIDs that will be preserved. By default only records with langID
  0x0409 (English) are preserved. Use '*' to keep all langIDs.

--obfuscate-names
  Make the font unusable as a system font by replacing name IDs 1, 2, 3, 4,
  and 6 with dummy strings (it is still fully functional as webfont).

Glyph naming and encoding options
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

--glyph-names
  Keep PS glyph names in TT-flavored fonts. In general glyph names are
  not needed for correct use of the font. However, some PDF generators
  and PDF viewers might rely on glyph names to extract Unicode text
  from PDF documents.
--no-glyph-names
  Drop PS glyph names in TT-flavored fonts, by using 'post' table
  version 3.0. [default]
--legacy-cmap
  Keep the legacy 'cmap' subtables (0.x, 1.x, 4.x etc.).
--no-legacy-cmap
  Drop the legacy 'cmap' subtables. [default]
--symbol-cmap
  Keep the 3.0 symbol 'cmap'.
--no-symbol-cmap
  Drop the 3.0 symbol 'cmap'. [default]

Other font-specific options
^^^^^^^^^^^^^^^^^^^^^^^^^^^

--recalc-bounds
    Recalculate font bounding boxes.
--no-recalc-bounds
    Keep original font bounding boxes. This is faster and still safe
    for all practical purposes. [default]
--recalc-timestamp
    Set font 'modified' timestamp to current time.
--no-recalc-timestamp
    Do not modify font 'modified' timestamp. [default]
--canonical-order
    Order tables as recommended in the OpenType standard. This is not
    required by the standard, nor by any known implementation.
--no-canonical-order
    Keep original order of font tables. This is faster. [default]
--prune-unicode-ranges
    Update the 'OS/2 ulUnicodeRange*' bits after subsetting. The Unicode
    ranges defined in the OpenType specification v1.7 are intersected with
    the Unicode codepoints specified in the font's Unicode 'cmap' subtables:
    when no overlap is found, the bit will be switched off. However, it will
    *not* be switched on if an intersection is found.  [default]
--no-prune-unicode-ranges
    Don't change the 'OS/2 ulUnicodeRange*' bits.
--prune-codepage-ranges
    Update the 'OS/2 ulCodePageRange*' bits after subsetting.  [default]
--no-prune-codepage-ranges
    Don't change the 'OS/2 ulCodePageRange*' bits.
--recalc-average-width
    Update the 'OS/2 xAvgCharWidth' field after subsetting.
--no-recalc-average-width
    Don't change the 'OS/2 xAvgCharWidth' field. [default]
--recalc-max-context
    Update the 'OS/2 usMaxContext' field after subsetting.
--no-recalc-max-context
    Don't change the 'OS/2 usMaxContext' field. [default]
--font-number=<number>
    Select font number for TrueType Collection (.ttc/.otc), starting from 0.
--pretty-svg
    When subsetting SVG table, use lxml pretty_print=True option to indent
    the XML output (only recommended for debugging purposes).

Application options
^^^^^^^^^^^^^^^^^^^

--verbose
    Display verbose information of the subsetting process.
--timing
    Display detailed timing information of the subsetting process.
--xml
    Display the TTX XML representation of subsetted font.

Example
^^^^^^^

Produce a subset containing the characters ' !"#$%' without performing
size-reducing optimizations::

  $ fonttools subset font.ttf --unicodes="U+0020-0025" \\
    --layout-features=* --glyph-names --symbol-cmap --legacy-cmap \\
    --notdef-glyph --notdef-outline --recommended-glyphs \\
    --name-IDs=* --name-legacy --name-languages=*
"""
)


log = logging.getLogger("fontTools.subset")


def _log_glyphs(self, glyphs, font=None):
    self.info("Glyph names: %s", sorted(glyphs))
    if font:
        reverseGlyphMap = font.getReverseGlyphMap()
        self.info("Glyph IDs:   %s", sorted(reverseGlyphMap[g] for g in glyphs))


# bind "glyphs" function to 'log' object
log.glyphs = MethodType(_log_glyphs, log)

# I use a different timing channel so I can configure it separately from the
# main module's logger
timer = Timer(logger=logging.getLogger("fontTools.subset.timer"))


def _dict_subset(d, glyphs):
    return {g: d[g] for g in glyphs}


def _list_subset(l, indices):
    count = len(l)
    return [l[i] for i in indices if i < count]


@_add_method(otTables.Coverage)
def intersect(self, glyphs):
    """Returns ascending list of matching coverage values."""
    return [i for i, g in enumerate(self.glyphs) if g in glyphs]


@_add_method(otTables.Coverage)
def intersect_glyphs(self, glyphs):
    """Returns set of intersecting glyphs."""
    return set(g for g in self.glyphs if g in glyphs)


@_add_method(otTables.Coverage)
def subset(self, glyphs):
    """Returns ascending list of remaining coverage values."""
    indices = self.intersect(glyphs)
    self.glyphs = [g for g in self.glyphs if g in glyphs]
    return indices


@_add_method(otTables.Coverage)
def remap(self, coverage_map):
    """Remaps coverage."""
    self.glyphs = [self.glyphs[i] for i in coverage_map]


@_add_method(otTables.ClassDef)
def intersect(self, glyphs):
    """Returns ascending list of matching class values."""
    return _uniq_sort(
        ([0] if any(g not in self.classDefs for g in glyphs) else [])
        + [v for g, v in self.classDefs.items() if g in glyphs]
    )


@_add_method(otTables.ClassDef)
def intersect_class(self, glyphs, klass):
    """Returns set of glyphs matching class."""
    if klass == 0:
        return set(g for g in glyphs if g not in self.classDefs)
    return set(g for g, v in self.classDefs.items() if v == klass and g in glyphs)


@_add_method(otTables.ClassDef)
def subset(self, glyphs, remap=False, useClass0=True):
    """Returns ascending list of remaining classes."""
    self.classDefs = {g: v for g, v in self.classDefs.items() if g in glyphs}
    # Note: while class 0 has the special meaning of "not matched",
    # if no glyph will ever /not match/, we can optimize class 0 out too.
    # Only do this if allowed.
    indices = _uniq_sort(
        (
            [0]
            if ((not useClass0) or any(g not in self.classDefs for g in glyphs))
            else []
        )
        + list(self.classDefs.values())
    )
    if remap:
        self.remap(indices)
    return indices


@_add_method(otTables.ClassDef)
def remap(self, class_map):
    """Remaps classes."""
    self.classDefs = {g: class_map.index(v) for g, v in self.classDefs.items()}


@_add_method(otTables.SingleSubst)
def closure_glyphs(self, s, cur_glyphs):
    s.glyphs.update(v for g, v in self.mapping.items() if g in cur_glyphs)


@_add_method(otTables.SingleSubst)
def subset_glyphs(self, s):
    self.mapping = {
        g: v for g, v in self.mapping.items() if g in s.glyphs and v in s.glyphs
    }
    return bool(self.mapping)


@_add_method(otTables.MultipleSubst)
def closure_glyphs(self, s, cur_glyphs):
    for glyph, subst in self.mapping.items():
        if glyph in cur_glyphs:
            s.glyphs.update(subst)


@_add_method(otTables.MultipleSubst)
def subset_glyphs(self, s):
    self.mapping = {
        g: v
        for g, v in self.mapping.items()
        if g in s.glyphs and all(sub in s.glyphs for sub in v)
    }
    return bool(self.mapping)


@_add_method(otTables.AlternateSubst)
def closure_glyphs(self, s, cur_glyphs):
    s.glyphs.update(*(vlist for g, vlist in self.alternates.items() if g in cur_glyphs))


@_add_method(otTables.AlternateSubst)
def subset_glyphs(self, s):
    self.alternates = {
        g: [v for v in vlist if v in s.glyphs]
        for g, vlist in self.alternates.items()
        if g in s.glyphs and any(v in s.glyphs for v in vlist)
    }
    return bool(self.alternates)


@_add_method(otTables.LigatureSubst)
def closure_glyphs(self, s, cur_glyphs):
    s.glyphs.update(
        *(
            [seq.LigGlyph for seq in seqs if all(c in s.glyphs for c in seq.Component)]
            for g, seqs in self.ligatures.items()
            if g in cur_glyphs
        )
    )


@_add_method(otTables.LigatureSubst)
def subset_glyphs(self, s):
    self.ligatures = {g: v for g, v in self.ligatures.items() if g in s.glyphs}
    self.ligatures = {
        g: [
            seq
            for seq in seqs
            if seq.LigGlyph in s.glyphs and all(c in s.glyphs for c in seq.Component)
        ]
        for g, seqs in self.ligatures.items()
    }
    self.ligatures = {g: v for g, v in self.ligatures.items() if v}
    return bool(self.ligatures)


@_add_method(otTables.ReverseChainSingleSubst)
def closure_glyphs(self, s, cur_glyphs):
    if self.Format == 1:
        indices = self.Coverage.intersect(cur_glyphs)
        if not indices or not all(
            c.intersect(s.glyphs)
            for c in self.LookAheadCoverage + self.BacktrackCoverage
        ):
            return
        s.glyphs.update(self.Substitute[i] for i in indices)
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.ReverseChainSingleSubst)
def subset_glyphs(self, s):
    if self.Format == 1:
        indices = self.Coverage.subset(s.glyphs)
        self.Substitute = _list_subset(self.Substitute, indices)
        # Now drop rules generating glyphs we don't want
        indices = [i for i, sub in enumerate(self.Substitute) if sub in s.glyphs]
        self.Substitute = _list_subset(self.Substitute, indices)
        self.Coverage.remap(indices)
        self.GlyphCount = len(self.Substitute)
        return bool(
            self.GlyphCount
            and all(
                c.subset(s.glyphs)
                for c in self.LookAheadCoverage + self.BacktrackCoverage
            )
        )
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.Device)
def is_hinting(self):
    return self.DeltaFormat in (1, 2, 3)


@_add_method(otTables.ValueRecord)
def prune_hints(self):
    for name in ["XPlaDevice", "YPlaDevice", "XAdvDevice", "YAdvDevice"]:
        v = getattr(self, name, None)
        if v is not None and v.is_hinting():
            delattr(self, name)


@_add_method(otTables.SinglePos)
def subset_glyphs(self, s):
    if self.Format == 1:
        return len(self.Coverage.subset(s.glyphs))
    elif self.Format == 2:
        indices = self.Coverage.subset(s.glyphs)
        values = self.Value
        count = len(values)
        self.Value = [values[i] for i in indices if i < count]
        self.ValueCount = len(self.Value)
        return bool(self.ValueCount)
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.SinglePos)
def prune_post_subset(self, font, options):
    if self.Value is None:
        assert self.ValueFormat == 0
        return True

    # Shrink ValueFormat
    if self.Format == 1:
        if not options.hinting:
            self.Value.prune_hints()
        self.ValueFormat = self.Value.getEffectiveFormat()
    elif self.Format == 2:
        if None in self.Value:
            assert self.ValueFormat == 0
            assert all(v is None for v in self.Value)
        else:
            if not options.hinting:
                for v in self.Value:
                    v.prune_hints()
            self.ValueFormat = reduce(
                int.__or__, [v.getEffectiveFormat() for v in self.Value], 0
            )

    # Downgrade to Format 1 if all ValueRecords are the same
    if self.Format == 2 and all(v == self.Value[0] for v in self.Value):
        self.Format = 1
        self.Value = self.Value[0] if self.ValueFormat != 0 else None
        del self.ValueCount

    return True


@_add_method(otTables.PairPos)
def subset_glyphs(self, s):
    if self.Format == 1:
        indices = self.Coverage.subset(s.glyphs)
        pairs = self.PairSet
        count = len(pairs)
        self.PairSet = [pairs[i] for i in indices if i < count]
        for p in self.PairSet:
            p.PairValueRecord = [
                r for r in p.PairValueRecord if r.SecondGlyph in s.glyphs
            ]
            p.PairValueCount = len(p.PairValueRecord)
        # Remove empty pairsets
        indices = [i for i, p in enumerate(self.PairSet) if p.PairValueCount]
        self.Coverage.remap(indices)
        self.PairSet = _list_subset(self.PairSet, indices)
        self.PairSetCount = len(self.PairSet)
        return bool(self.PairSetCount)
    elif self.Format == 2:
        class1_map = [
            c
            for c in self.ClassDef1.subset(
                s.glyphs.intersection(self.Coverage.glyphs), remap=True
            )
            if c < self.Class1Count
        ]
        class2_map = [
            c
            for c in self.ClassDef2.subset(s.glyphs, remap=True, useClass0=False)
            if c < self.Class2Count
        ]
        self.Class1Record = [self.Class1Record[i] for i in class1_map]
        for c in self.Class1Record:
            c.Class2Record = [c.Class2Record[i] for i in class2_map]
        self.Class1Count = len(class1_map)
        self.Class2Count = len(class2_map)
        # If only Class2 0 left, no need to keep anything.
        return bool(
            self.Class1Count
            and (self.Class2Count > 1)
            and self.Coverage.subset(s.glyphs)
        )
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.PairPos)
def prune_post_subset(self, font, options):
    if not options.hinting:
        attr1, attr2 = {
            1: ("PairSet", "PairValueRecord"),
            2: ("Class1Record", "Class2Record"),
        }[self.Format]

        self.ValueFormat1 = self.ValueFormat2 = 0
        for row in getattr(self, attr1):
            for r in getattr(row, attr2):
                if r.Value1:
                    r.Value1.prune_hints()
                    self.ValueFormat1 |= r.Value1.getEffectiveFormat()
                if r.Value2:
                    r.Value2.prune_hints()
                    self.ValueFormat2 |= r.Value2.getEffectiveFormat()

    return bool(self.ValueFormat1 | self.ValueFormat2)


@_add_method(otTables.CursivePos)
def subset_glyphs(self, s):
    if self.Format == 1:
        indices = self.Coverage.subset(s.glyphs)
        records = self.EntryExitRecord
        count = len(records)
        self.EntryExitRecord = [records[i] for i in indices if i < count]
        self.EntryExitCount = len(self.EntryExitRecord)
        return bool(self.EntryExitCount)
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.Anchor)
def prune_hints(self):
    if self.Format == 2:
        self.Format = 1
    elif self.Format == 3:
        for name in ("XDeviceTable", "YDeviceTable"):
            v = getattr(self, name, None)
            if v is not None and v.is_hinting():
                setattr(self, name, None)
        if self.XDeviceTable is None and self.YDeviceTable is None:
            self.Format = 1


@_add_method(otTables.CursivePos)
def prune_post_subset(self, font, options):
    if not options.hinting:
        for rec in self.EntryExitRecord:
            if rec.EntryAnchor:
                rec.EntryAnchor.prune_hints()
            if rec.ExitAnchor:
                rec.ExitAnchor.prune_hints()
    return True


@_add_method(otTables.MarkBasePos)
def subset_glyphs(self, s):
    if self.Format == 1:
        mark_indices = self.MarkCoverage.subset(s.glyphs)
        self.MarkArray.MarkRecord = _list_subset(
            self.MarkArray.MarkRecord, mark_indices
        )
        self.MarkArray.MarkCount = len(self.MarkArray.MarkRecord)
        class_indices = _uniq_sort(v.Class for v in self.MarkArray.MarkRecord)

        intersect_base_indices = self.BaseCoverage.intersect(s.glyphs)
        base_records = self.BaseArray.BaseRecord
        num_base_records = len(base_records)
        base_indices = [
            i
            for i in intersect_base_indices
            if i < num_base_records
            and any(base_records[i].BaseAnchor[j] is not None for j in class_indices)
        ]
        if not base_indices:
            return False

        self.BaseCoverage.remap(base_indices)
        self.BaseArray.BaseRecord = _list_subset(
            self.BaseArray.BaseRecord, base_indices
        )
        self.BaseArray.BaseCount = len(self.BaseArray.BaseRecord)
        # Prune empty classes
        self.ClassCount = len(class_indices)
        for m in self.MarkArray.MarkRecord:
            m.Class = class_indices.index(m.Class)
        for b in self.BaseArray.BaseRecord:
            b.BaseAnchor = _list_subset(b.BaseAnchor, class_indices)
        return bool(
            self.ClassCount and self.MarkArray.MarkCount and self.BaseArray.BaseCount
        )
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.MarkBasePos)
def prune_post_subset(self, font, options):
    if not options.hinting:
        for m in self.MarkArray.MarkRecord:
            if m.MarkAnchor:
                m.MarkAnchor.prune_hints()
        for b in self.BaseArray.BaseRecord:
            for a in b.BaseAnchor:
                if a:
                    a.prune_hints()
    return True


@_add_method(otTables.MarkLigPos)
def subset_glyphs(self, s):
    if self.Format == 1:
        mark_indices = self.MarkCoverage.subset(s.glyphs)
        self.MarkArray.MarkRecord = _list_subset(
            self.MarkArray.MarkRecord, mark_indices
        )
        self.MarkArray.MarkCount = len(self.MarkArray.MarkRecord)
        class_indices = _uniq_sort(v.Class for v in self.MarkArray.MarkRecord)

        intersect_ligature_indices = self.LigatureCoverage.intersect(s.glyphs)
        ligature_array = self.LigatureArray.LigatureAttach
        num_ligatures = self.LigatureArray.LigatureCount

        ligature_indices = [
            i
            for i in intersect_ligature_indices
            if i < num_ligatures
            and any(
                any(component.LigatureAnchor[j] is not None for j in class_indices)
                for component in ligature_array[i].ComponentRecord
            )
        ]

        if not ligature_indices:
            return False

        self.LigatureCoverage.remap(ligature_indices)
        self.LigatureArray.LigatureAttach = _list_subset(
            self.LigatureArray.LigatureAttach, ligature_indices
        )
        self.LigatureArray.LigatureCount = len(self.LigatureArray.LigatureAttach)
        # Prune empty classes
        self.ClassCount = len(class_indices)
        for m in self.MarkArray.MarkRecord:
            m.Class = class_indices.index(m.Class)
        for l in self.LigatureArray.LigatureAttach:
            if l is None:
                continue
            for c in l.ComponentRecord:
                c.LigatureAnchor = _list_subset(c.LigatureAnchor, class_indices)
        return bool(
            self.ClassCount
            and self.MarkArray.MarkCount
            and self.LigatureArray.LigatureCount
        )
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.MarkLigPos)
def prune_post_subset(self, font, options):
    if not options.hinting:
        for m in self.MarkArray.MarkRecord:
            if m.MarkAnchor:
                m.MarkAnchor.prune_hints()
        for l in self.LigatureArray.LigatureAttach:
            if l is None:
                continue
            for c in l.ComponentRecord:
                for a in c.LigatureAnchor:
                    if a:
                        a.prune_hints()
    return True


@_add_method(otTables.MarkMarkPos)
def subset_glyphs(self, s):
    if self.Format == 1:
        mark1_indices = self.Mark1Coverage.subset(s.glyphs)
        self.Mark1Array.MarkRecord = _list_subset(
            self.Mark1Array.MarkRecord, mark1_indices
        )
        self.Mark1Array.MarkCount = len(self.Mark1Array.MarkRecord)
        class_indices = _uniq_sort(v.Class for v in self.Mark1Array.MarkRecord)

        intersect_mark2_indices = self.Mark2Coverage.intersect(s.glyphs)
        mark2_records = self.Mark2Array.Mark2Record
        num_mark2_records = len(mark2_records)
        mark2_indices = [
            i
            for i in intersect_mark2_indices
            if i < num_mark2_records
            and any(mark2_records[i].Mark2Anchor[j] is not None for j in class_indices)
        ]
        if not mark2_indices:
            return False

        self.Mark2Coverage.remap(mark2_indices)
        self.Mark2Array.Mark2Record = _list_subset(
            self.Mark2Array.Mark2Record, mark2_indices
        )
        self.Mark2Array.MarkCount = len(self.Mark2Array.Mark2Record)
        # Prune empty classes
        self.ClassCount = len(class_indices)
        for m in self.Mark1Array.MarkRecord:
            m.Class = class_indices.index(m.Class)
        for b in self.Mark2Array.Mark2Record:
            b.Mark2Anchor = _list_subset(b.Mark2Anchor, class_indices)
        return bool(
            self.ClassCount and self.Mark1Array.MarkCount and self.Mark2Array.MarkCount
        )
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.MarkMarkPos)
def prune_post_subset(self, font, options):
    if not options.hinting:
        for m in self.Mark1Array.MarkRecord:
            if m.MarkAnchor:
                m.MarkAnchor.prune_hints()
        for b in self.Mark2Array.Mark2Record:
            for m in b.Mark2Anchor:
                if m:
                    m.prune_hints()
    return True


@_add_method(
    otTables.SingleSubst,
    otTables.MultipleSubst,
    otTables.AlternateSubst,
    otTables.LigatureSubst,
    otTables.ReverseChainSingleSubst,
    otTables.SinglePos,
    otTables.PairPos,
    otTables.CursivePos,
    otTables.MarkBasePos,
    otTables.MarkLigPos,
    otTables.MarkMarkPos,
)
def subset_lookups(self, lookup_indices):
    pass


@_add_method(
    otTables.SingleSubst,
    otTables.MultipleSubst,
    otTables.AlternateSubst,
    otTables.LigatureSubst,
    otTables.ReverseChainSingleSubst,
    otTables.SinglePos,
    otTables.PairPos,
    otTables.CursivePos,
    otTables.MarkBasePos,
    otTables.MarkLigPos,
    otTables.MarkMarkPos,
)
def collect_lookups(self):
    return []


@_add_method(
    otTables.SingleSubst,
    otTables.MultipleSubst,
    otTables.AlternateSubst,
    otTables.LigatureSubst,
    otTables.ReverseChainSingleSubst,
    otTables.ContextSubst,
    otTables.ChainContextSubst,
    otTables.ContextPos,
    otTables.ChainContextPos,
)
def prune_post_subset(self, font, options):
    return True


@_add_method(
    otTables.SingleSubst, otTables.AlternateSubst, otTables.ReverseChainSingleSubst
)
def may_have_non_1to1(self):
    return False


@_add_method(
    otTables.MultipleSubst,
    otTables.LigatureSubst,
    otTables.ContextSubst,
    otTables.ChainContextSubst,
)
def may_have_non_1to1(self):
    return True


@_add_method(
    otTables.ContextSubst,
    otTables.ChainContextSubst,
    otTables.ContextPos,
    otTables.ChainContextPos,
)
def __subset_classify_context(self):
    class ContextHelper(object):
        def __init__(self, klass, Format):
            if klass.__name__.endswith("Subst"):
                Typ = "Sub"
                Type = "Subst"
            else:
                Typ = "Pos"
                Type = "Pos"
            if klass.__name__.startswith("Chain"):
                Chain = "Chain"
                InputIdx = 1
                DataLen = 3
            else:
                Chain = ""
                InputIdx = 0
                DataLen = 1
            ChainTyp = Chain + Typ

            self.Typ = Typ
            self.Type = Type
            self.Chain = Chain
            self.ChainTyp = ChainTyp
            self.InputIdx = InputIdx
            self.DataLen = DataLen

            self.LookupRecord = Type + "LookupRecord"

            if Format == 1:
                Coverage = lambda r: r.Coverage
                ChainCoverage = lambda r: r.Coverage
                ContextData = lambda r: (None,)
                ChainContextData = lambda r: (None, None, None)
                SetContextData = None
                SetChainContextData = None
                RuleData = lambda r: (r.Input,)
                ChainRuleData = lambda r: (r.Backtrack, r.Input, r.LookAhead)

                def SetRuleData(r, d):
                    (r.Input,) = d
                    (r.GlyphCount,) = (len(x) + 1 for x in d)

                def ChainSetRuleData(r, d):
                    (r.Backtrack, r.Input, r.LookAhead) = d
                    (
                        r.BacktrackGlyphCount,
                        r.InputGlyphCount,
                        r.LookAheadGlyphCount,
                    ) = (len(d[0]), len(d[1]) + 1, len(d[2]))

            elif Format == 2:
                Coverage = lambda r: r.Coverage
                ChainCoverage = lambda r: r.Coverage
                ContextData = lambda r: (r.ClassDef,)
                ChainContextData = lambda r: (
                    r.BacktrackClassDef,
                    r.InputClassDef,
                    r.LookAheadClassDef,
                )

                def SetContextData(r, d):
                    (r.ClassDef,) = d

                def SetChainContextData(r, d):
                    (r.BacktrackClassDef, r.InputClassDef, r.LookAheadClassDef) = d

                RuleData = lambda r: (r.Class,)
                ChainRuleData = lambda r: (r.Backtrack, r.Input, r.LookAhead)

                def SetRuleData(r, d):
                    (r.Class,) = d
                    (r.GlyphCount,) = (len(x) + 1 for x in d)

                def ChainSetRuleData(r, d):
                    (r.Backtrack, r.Input, r.LookAhead) = d
                    (
                        r.BacktrackGlyphCount,
                        r.InputGlyphCount,
                        r.LookAheadGlyphCount,
                    ) = (len(d[0]), len(d[1]) + 1, len(d[2]))

            elif Format == 3:
                Coverage = lambda r: r.Coverage[0]
                ChainCoverage = lambda r: r.InputCoverage[0]
                ContextData = None
                ChainContextData = None
                SetContextData = None
                SetChainContextData = None
                RuleData = lambda r: r.Coverage
                ChainRuleData = lambda r: (
                    r.BacktrackCoverage + r.InputCoverage + r.LookAheadCoverage
                )

                def SetRuleData(r, d):
                    (r.Coverage,) = d
                    (r.GlyphCount,) = (len(x) for x in d)

                def ChainSetRuleData(r, d):
                    (r.BacktrackCoverage, r.InputCoverage, r.LookAheadCoverage) = d
                    (
                        r.BacktrackGlyphCount,
                        r.InputGlyphCount,
                        r.LookAheadGlyphCount,
                    ) = (len(x) for x in d)

            else:
                assert 0, "unknown format: %s" % Format

            if Chain:
                self.Coverage = ChainCoverage
                self.ContextData = ChainContextData
                self.SetContextData = SetChainContextData
                self.RuleData = ChainRuleData
                self.SetRuleData = ChainSetRuleData
            else:
                self.Coverage = Coverage
                self.ContextData = ContextData
                self.SetContextData = SetContextData
                self.RuleData = RuleData
                self.SetRuleData = SetRuleData

            if Format == 1:
                self.Rule = ChainTyp + "Rule"
                self.RuleCount = ChainTyp + "RuleCount"
                self.RuleSet = ChainTyp + "RuleSet"
                self.RuleSetCount = ChainTyp + "RuleSetCount"
                self.Intersect = lambda glyphs, c, r: [r] if r in glyphs else []
            elif Format == 2:
                self.Rule = ChainTyp + "ClassRule"
                self.RuleCount = ChainTyp + "ClassRuleCount"
                self.RuleSet = ChainTyp + "ClassSet"
                self.RuleSetCount = ChainTyp + "ClassSetCount"
                self.Intersect = lambda glyphs, c, r: (
                    c.intersect_class(glyphs, r)
                    if c
                    else (set(glyphs) if r == 0 else set())
                )

                self.ClassDef = "InputClassDef" if Chain else "ClassDef"
                self.ClassDefIndex = 1 if Chain else 0
                self.Input = "Input" if Chain else "Class"
            elif Format == 3:
                self.Input = "InputCoverage" if Chain else "Coverage"

    if self.Format not in [1, 2, 3]:
        return None  # Don't shoot the messenger; let it go
    if not hasattr(self.__class__, "_subset__ContextHelpers"):
        self.__class__._subset__ContextHelpers = {}
    if self.Format not in self.__class__._subset__ContextHelpers:
        helper = ContextHelper(self.__class__, self.Format)
        self.__class__._subset__ContextHelpers[self.Format] = helper
    return self.__class__._subset__ContextHelpers[self.Format]


@_add_method(otTables.ContextSubst, otTables.ChainContextSubst)
def closure_glyphs(self, s, cur_glyphs):
    c = self.__subset_classify_context()

    indices = c.Coverage(self).intersect(cur_glyphs)
    if not indices:
        return []
    cur_glyphs = c.Coverage(self).intersect_glyphs(cur_glyphs)

    if self.Format == 1:
        ContextData = c.ContextData(self)
        rss = getattr(self, c.RuleSet)
        rssCount = getattr(self, c.RuleSetCount)
        for i in indices:
            if i >= rssCount or not rss[i]:
                continue
            for r in getattr(rss[i], c.Rule):
                if not r:
                    continue
                if not all(
                    all(c.Intersect(s.glyphs, cd, k) for k in klist)
                    for cd, klist in zip(ContextData, c.RuleData(r))
                ):
                    continue
                chaos = set()
                for ll in getattr(r, c.LookupRecord):
                    if not ll:
                        continue
                    seqi = ll.SequenceIndex
                    if seqi in chaos:
                        # TODO Can we improve this?
                        pos_glyphs = None
                    else:
                        if seqi == 0:
                            pos_glyphs = frozenset([c.Coverage(self).glyphs[i]])
                        else:
                            pos_glyphs = frozenset([r.Input[seqi - 1]])
                    lookup = s.table.LookupList.Lookup[ll.LookupListIndex]
                    chaos.add(seqi)
                    if lookup.may_have_non_1to1():
                        chaos.update(range(seqi, len(r.Input) + 2))
                    lookup.closure_glyphs(s, cur_glyphs=pos_glyphs)
    elif self.Format == 2:
        ClassDef = getattr(self, c.ClassDef)
        indices = ClassDef.intersect(cur_glyphs)
        ContextData = c.ContextData(self)
        rss = getattr(self, c.RuleSet)
        rssCount = getattr(self, c.RuleSetCount)
        for i in indices:
            if i >= rssCount or not rss[i]:
                continue
            for r in getattr(rss[i], c.Rule):
                if not r:
                    continue
                if not all(
                    all(c.Intersect(s.glyphs, cd, k) for k in klist)
                    for cd, klist in zip(ContextData, c.RuleData(r))
                ):
                    continue
                chaos = set()
                for ll in getattr(r, c.LookupRecord):
                    if not ll:
                        continue
                    seqi = ll.SequenceIndex
                    if seqi in chaos:
                        # TODO Can we improve this?
                        pos_glyphs = None
                    else:
                        if seqi == 0:
                            pos_glyphs = frozenset(
                                ClassDef.intersect_class(cur_glyphs, i)
                            )
                        else:
                            pos_glyphs = frozenset(
                                ClassDef.intersect_class(
                                    s.glyphs, getattr(r, c.Input)[seqi - 1]
                                )
                            )
                    lookup = s.table.LookupList.Lookup[ll.LookupListIndex]
                    chaos.add(seqi)
                    if lookup.may_have_non_1to1():
                        chaos.update(range(seqi, len(getattr(r, c.Input)) + 2))
                    lookup.closure_glyphs(s, cur_glyphs=pos_glyphs)
    elif self.Format == 3:
        if not all(x is not None and x.intersect(s.glyphs) for x in c.RuleData(self)):
            return []
        r = self
        input_coverages = getattr(r, c.Input)
        chaos = set()
        for ll in getattr(r, c.LookupRecord):
            if not ll:
                continue
            seqi = ll.SequenceIndex
            if seqi in chaos:
                # TODO Can we improve this?
                pos_glyphs = None
            else:
                if seqi == 0:
                    pos_glyphs = frozenset(cur_glyphs)
                else:
                    pos_glyphs = frozenset(
                        input_coverages[seqi].intersect_glyphs(s.glyphs)
                    )
            lookup = s.table.LookupList.Lookup[ll.LookupListIndex]
            chaos.add(seqi)
            if lookup.may_have_non_1to1():
                chaos.update(range(seqi, len(input_coverages) + 1))
            lookup.closure_glyphs(s, cur_glyphs=pos_glyphs)
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(
    otTables.ContextSubst,
    otTables.ContextPos,
    otTables.ChainContextSubst,
    otTables.ChainContextPos,
)
def subset_glyphs(self, s):
    c = self.__subset_classify_context()

    if self.Format == 1:
        indices = self.Coverage.subset(s.glyphs)
        rss = getattr(self, c.RuleSet)
        rssCount = getattr(self, c.RuleSetCount)
        rss = [rss[i] for i in indices if i < rssCount]
        for rs in rss:
            if not rs:
                continue
            ss = getattr(rs, c.Rule)
            ss = [
                r
                for r in ss
                if r
                and all(all(g in s.glyphs for g in glist) for glist in c.RuleData(r))
            ]
            setattr(rs, c.Rule, ss)
            setattr(rs, c.RuleCount, len(ss))
        # Prune empty rulesets
        indices = [i for i, rs in enumerate(rss) if rs and getattr(rs, c.Rule)]
        self.Coverage.remap(indices)
        rss = _list_subset(rss, indices)
        setattr(self, c.RuleSet, rss)
        setattr(self, c.RuleSetCount, len(rss))
        return bool(rss)
    elif self.Format == 2:
        if not self.Coverage.subset(s.glyphs):
            return False
        ContextData = c.ContextData(self)
        klass_maps = [
            x.subset(s.glyphs, remap=True) if x else None for x in ContextData
        ]

        # Keep rulesets for class numbers that survived.
        indices = klass_maps[c.ClassDefIndex]
        rss = getattr(self, c.RuleSet)
        rssCount = getattr(self, c.RuleSetCount)
        rss = [rss[i] for i in indices if i < rssCount]
        del rssCount
        # Delete, but not renumber, unreachable rulesets.
        indices = getattr(self, c.ClassDef).intersect(self.Coverage.glyphs)
        rss = [rss if i in indices else None for i, rss in enumerate(rss)]

        for rs in rss:
            if not rs:
                continue
            ss = getattr(rs, c.Rule)
            ss = [
                r
                for r in ss
                if r
                and all(
                    all(k in klass_map for k in klist)
                    for klass_map, klist in zip(klass_maps, c.RuleData(r))
                )
            ]
            setattr(rs, c.Rule, ss)
            setattr(rs, c.RuleCount, len(ss))

            # Remap rule classes
            for r in ss:
                c.SetRuleData(
                    r,
                    [
                        [klass_map.index(k) for k in klist]
                        for klass_map, klist in zip(klass_maps, c.RuleData(r))
                    ],
                )

        # Prune empty rulesets
        rss = [rs if rs and getattr(rs, c.Rule) else None for rs in rss]
        while rss and rss[-1] is None:
            del rss[-1]
        setattr(self, c.RuleSet, rss)
        setattr(self, c.RuleSetCount, len(rss))

        # TODO: We can do a second round of remapping class values based
        # on classes that are actually used in at least one rule.	Right
        # now we subset classes to c.glyphs only.	Or better, rewrite
        # the above to do that.

        return bool(rss)
    elif self.Format == 3:
        return all(x is not None and x.subset(s.glyphs) for x in c.RuleData(self))
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(
    otTables.ContextSubst,
    otTables.ChainContextSubst,
    otTables.ContextPos,
    otTables.ChainContextPos,
)
def subset_lookups(self, lookup_indices):
    c = self.__subset_classify_context()

    if self.Format in [1, 2]:
        for rs in getattr(self, c.RuleSet):
            if not rs:
                continue
            for r in getattr(rs, c.Rule):
                if not r:
                    continue
                setattr(
                    r,
                    c.LookupRecord,
                    [
                        ll
                        for ll in getattr(r, c.LookupRecord)
                        if ll and ll.LookupListIndex in lookup_indices
                    ],
                )
                for ll in getattr(r, c.LookupRecord):
                    if not ll:
                        continue
                    ll.LookupListIndex = lookup_indices.index(ll.LookupListIndex)
    elif self.Format == 3:
        setattr(
            self,
            c.LookupRecord,
            [
                ll
                for ll in getattr(self, c.LookupRecord)
                if ll and ll.LookupListIndex in lookup_indices
            ],
        )
        for ll in getattr(self, c.LookupRecord):
            if not ll:
                continue
            ll.LookupListIndex = lookup_indices.index(ll.LookupListIndex)
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(
    otTables.ContextSubst,
    otTables.ChainContextSubst,
    otTables.ContextPos,
    otTables.ChainContextPos,
)
def collect_lookups(self):
    c = self.__subset_classify_context()

    if self.Format in [1, 2]:
        return [
            ll.LookupListIndex
            for rs in getattr(self, c.RuleSet)
            if rs
            for r in getattr(rs, c.Rule)
            if r
            for ll in getattr(r, c.LookupRecord)
            if ll
        ]
    elif self.Format == 3:
        return [ll.LookupListIndex for ll in getattr(self, c.LookupRecord) if ll]
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.ExtensionSubst)
def closure_glyphs(self, s, cur_glyphs):
    if self.Format == 1:
        self.ExtSubTable.closure_glyphs(s, cur_glyphs)
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.ExtensionSubst)
def may_have_non_1to1(self):
    if self.Format == 1:
        return self.ExtSubTable.may_have_non_1to1()
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.ExtensionSubst, otTables.ExtensionPos)
def subset_glyphs(self, s):
    if self.Format == 1:
        return self.ExtSubTable.subset_glyphs(s)
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.ExtensionSubst, otTables.ExtensionPos)
def prune_post_subset(self, font, options):
    if self.Format == 1:
        return self.ExtSubTable.prune_post_subset(font, options)
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.ExtensionSubst, otTables.ExtensionPos)
def subset_lookups(self, lookup_indices):
    if self.Format == 1:
        return self.ExtSubTable.subset_lookups(lookup_indices)
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.ExtensionSubst, otTables.ExtensionPos)
def collect_lookups(self):
    if self.Format == 1:
        return self.ExtSubTable.collect_lookups()
    else:
        assert 0, "unknown format: %s" % self.Format


@_add_method(otTables.Lookup)
def closure_glyphs(self, s, cur_glyphs=None):
    if cur_glyphs is None:
        cur_glyphs = frozenset(s.glyphs)

    # Memoize
    key = id(self)
    doneLookups = s._doneLookups
    count, covered = doneLookups.get(key, (0, None))
    if count != len(s.glyphs):
        count, covered = doneLookups[key] = (len(s.glyphs), set())
    if cur_glyphs.issubset(covered):
        return
    covered.update(cur_glyphs)

    for st in self.SubTable:
        if not st:
            continue
        st.closure_glyphs(s, cur_glyphs)


@_add_method(otTables.Lookup)
def subset_glyphs(self, s):
    self.SubTable = [st for st in self.SubTable if st and st.subset_glyphs(s)]
    self.SubTableCount = len(self.SubTable)
    if hasattr(self, "MarkFilteringSet") and self.MarkFilteringSet is not None:
        if self.MarkFilteringSet not in s.used_mark_sets:
            self.MarkFilteringSet = None
            self.LookupFlag &= ~0x10
            self.LookupFlag |= 0x8
        else:
            self.MarkFilteringSet = s.used_mark_sets.index(self.MarkFilteringSet)
    return bool(self.SubTableCount)


@_add_method(otTables.Lookup)
def prune_post_subset(self, font, options):
    ret = False
    for st in self.SubTable:
        if not st:
            continue
        if st.prune_post_subset(font, options):
            ret = True
    return ret


@_add_method(otTables.Lookup)
def subset_lookups(self, lookup_indices):
    for s in self.SubTable:
        s.subset_lookups(lookup_indices)


@_add_method(otTables.Lookup)
def collect_lookups(self):
    return sum((st.collect_lookups() for st in self.SubTable if st), [])


@_add_method(otTables.Lookup)
def may_have_non_1to1(self):
    return any(st.may_have_non_1to1() for st in self.SubTable if st)


@_add_method(otTables.LookupList)
def subset_glyphs(self, s):
    """Returns the indices of nonempty lookups."""
    return [i for i, l in enumerate(self.Lookup) if l and l.subset_glyphs(s)]


@_add_method(otTables.LookupList)
def prune_post_subset(self, font, options):
    ret = False
    for l in self.Lookup:
        if not l:
            continue
        if l.prune_post_subset(font, options):
            ret = True
    return ret


@_add_method(otTables.LookupList)
def subset_lookups(self, lookup_indices):
    self.ensureDecompiled()
    self.Lookup = [self.Lookup[i] for i in lookup_indices if i < self.LookupCount]
    self.LookupCount = len(self.Lookup)
    for l in self.Lookup:
        l.subset_lookups(lookup_indices)


@_add_method(otTables.LookupList)
def neuter_lookups(self, lookup_indices):
    """Sets lookups not in lookup_indices to None."""
    self.ensureDecompiled()
    self.Lookup = [
        l if i in lookup_indices else None for i, l in enumerate(self.Lookup)
    ]


@_add_method(otTables.LookupList)
def closure_lookups(self, lookup_indices):
    """Returns sorted index of all lookups reachable from lookup_indices."""
    lookup_indices = _uniq_sort(lookup_indices)
    recurse = lookup_indices
    while True:
        recurse_lookups = sum(
            (self.Lookup[i].collect_lookups() for i in recurse if i < self.LookupCount),
            [],
        )
        recurse_lookups = [
            l
            for l in recurse_lookups
            if l not in lookup_indices and l < self.LookupCount
        ]
        if not recurse_lookups:
            return _uniq_sort(lookup_indices)
        recurse_lookups = _uniq_sort(recurse_lookups)
        lookup_indices.extend(recurse_lookups)
        recurse = recurse_lookups


@_add_method(otTables.Feature)
def subset_lookups(self, lookup_indices):
    """ "Returns True if feature is non-empty afterwards."""
    self.LookupListIndex = [l for l in self.LookupListIndex if l in lookup_indices]
    # Now map them.
    self.LookupListIndex = [lookup_indices.index(l) for l in self.LookupListIndex]
    self.LookupCount = len(self.LookupListIndex)
    # keep 'size' feature even if it contains no lookups; but drop any other
    # empty feature (e.g. FeatureParams for stylistic set names)
    # https://github.com/fonttools/fonttools/issues/2324
    return self.LookupCount or isinstance(
        self.FeatureParams, otTables.FeatureParamsSize
    )


@_add_method(otTables.FeatureList)
def subset_lookups(self, lookup_indices):
    """Returns the indices of nonempty features."""
    # Note: Never ever drop feature 'pref', even if it's empty.
    # HarfBuzz chooses shaper for Khmer based on presence of this
    # feature.	See thread at:
    # http://lists.freedesktop.org/archives/harfbuzz/2012-November/002660.html
    return [
        i
        for i, f in enumerate(self.FeatureRecord)
        if (f.Feature.subset_lookups(lookup_indices) or f.FeatureTag == "pref")
    ]


@_add_method(otTables.FeatureList)
def collect_lookups(self, feature_indices):
    return sum(
        (
            self.FeatureRecord[i].Feature.LookupListIndex
            for i in feature_indices
            if i < self.FeatureCount
        ),
        [],
    )


@_add_method(otTables.FeatureList)
def subset_features(self, feature_indices):
    self.ensureDecompiled()
    self.FeatureRecord = _list_subset(self.FeatureRecord, feature_indices)
    self.FeatureCount = len(self.FeatureRecord)
    return bool(self.FeatureCount)


@_add_method(otTables.FeatureTableSubstitution)
def subset_lookups(self, lookup_indices):
    """Returns the indices of nonempty features."""
    return [
        r.FeatureIndex
        for r in self.SubstitutionRecord
        if r.Feature.subset_lookups(lookup_indices)
    ]


@_add_method(otTables.FeatureVariations)
def subset_lookups(self, lookup_indices):
    """Returns the indices of nonempty features."""
    return sum(
        (
            f.FeatureTableSubstitution.subset_lookups(lookup_indices)
            for f in self.FeatureVariationRecord
        ),
        [],
    )


@_add_method(otTables.FeatureVariations)
def collect_lookups(self, feature_indices):
    return sum(
        (
            r.Feature.LookupListIndex
            for vr in self.FeatureVariationRecord
            for r in vr.FeatureTableSubstitution.SubstitutionRecord
            if r.FeatureIndex in feature_indices
        ),
        [],
    )


@_add_method(otTables.FeatureTableSubstitution)
def subset_features(self, feature_indices):
    self.ensureDecompiled()
    self.SubstitutionRecord = [
        r for r in self.SubstitutionRecord if r.FeatureIndex in feature_indices
    ]
    # remap feature indices
    for r in self.SubstitutionRecord:
        r.FeatureIndex = feature_indices.index(r.FeatureIndex)
    self.SubstitutionCount = len(self.SubstitutionRecord)
    return bool(self.SubstitutionCount)


@_add_method(otTables.FeatureTableSubstitution)
def prune_features(self, feature_index_map):
    self.ensureDecompiled()
    self.SubstitutionRecord = [
        r for r in self.SubstitutionRecord if r.FeatureIndex in feature_index_map.keys()
    ]
    # remap feature indices
    for r in self.SubstitutionRecord:
        r.FeatureIndex = feature_index_map[r.FeatureIndex]
    self.SubstitutionCount = len(self.SubstitutionRecord)
    return bool(self.SubstitutionCount)


@_add_method(otTables.FeatureVariations)
def subset_features(self, feature_indices):
    self.ensureDecompiled()
    for r in self.FeatureVariationRecord:
        r.FeatureTableSubstitution.subset_features(feature_indices)
    # Prune empty records at the end only
    # https://github.com/fonttools/fonttools/issues/1881
    while (
        self.FeatureVariationRecord
        and not self.FeatureVariationRecord[
            -1
        ].FeatureTableSubstitution.SubstitutionCount
    ):
        self.FeatureVariationRecord.pop()
    self.FeatureVariationCount = len(self.FeatureVariationRecord)
    return bool(self.FeatureVariationCount)


@_add_method(otTables.FeatureVariations)
def prune_features(self, feature_index_map):
    self.ensureDecompiled()
    for r in self.FeatureVariationRecord:
        r.FeatureTableSubstitution.prune_features(feature_index_map)
    # Prune empty records at the end only
    # https://github.com/fonttools/fonttools/issues/1881
    while (
        self.FeatureVariationRecord
        and not self.FeatureVariationRecord[
            -1
        ].FeatureTableSubstitution.SubstitutionCount
    ):
        self.FeatureVariationRecord.pop()
    self.FeatureVariationCount = len(self.FeatureVariationRecord)
    return bool(self.FeatureVariationCount)


@_add_method(otTables.DefaultLangSys, otTables.LangSys)
def subset_features(self, feature_indices):
    if self.ReqFeatureIndex in feature_indices:
        self.ReqFeatureIndex = feature_indices.index(self.ReqFeatureIndex)
    else:
        self.ReqFeatureIndex = 65535
    self.FeatureIndex = [f for f in self.FeatureIndex if f in feature_indices]
    # Now map them.
    self.FeatureIndex = [
        feature_indices.index(f) for f in self.FeatureIndex if f in feature_indices
    ]
    self.FeatureCount = len(self.FeatureIndex)
    return bool(self.FeatureCount or self.ReqFeatureIndex != 65535)


@_add_method(otTables.DefaultLangSys, otTables.LangSys)
def prune_features(self, feature_index_map):
    self.ReqFeatureIndex = feature_index_map.get(self.ReqFeatureIndex, 65535)
    self.FeatureIndex = [
        feature_index_map[f] for f in self.FeatureIndex if f in feature_index_map.keys()
    ]
    self.FeatureCount = len(self.FeatureIndex)
    return bool(self.FeatureCount or self.ReqFeatureIndex != 65535)


@_add_method(otTables.DefaultLangSys, otTables.LangSys)
def collect_features(self):
    feature_indices = self.FeatureIndex[:]
    if self.ReqFeatureIndex != 65535:
        feature_indices.append(self.ReqFeatureIndex)
    return _uniq_sort(feature_indices)


@_add_method(otTables.Script)
def subset_features(self, feature_indices, keepEmptyDefaultLangSys=False):
    if (
        self.DefaultLangSys
        and not self.DefaultLangSys.subset_features(feature_indices)
        and not keepEmptyDefaultLangSys
    ):
        self.DefaultLangSys = None
    self.LangSysRecord = [
        l for l in self.LangSysRecord if l.LangSys.subset_features(feature_indices)
    ]
    self.LangSysCount = len(self.LangSysRecord)
    return bool(self.LangSysCount or self.DefaultLangSys)


@_add_method(otTables.Script)
def prune_features(self, feature_index_map, keepEmptyDefaultLangSys=False):
    if (
        self.DefaultLangSys
        and not self.DefaultLangSys.prune_features(feature_index_map)
        and not keepEmptyDefaultLangSys
    ):
        self.DefaultLangSys = None
    self.LangSysRecord = [
        l for l in self.LangSysRecord if l.LangSys.prune_features(feature_index_map)
    ]
    self.LangSysCount = len(self.LangSysRecord)
    return bool(self.LangSysCount or self.DefaultLangSys)


@_add_method(otTables.Script)
def collect_features(self):
    feature_indices = [l.LangSys.collect_features() for l in self.LangSysRecord]
    if self.DefaultLangSys:
        feature_indices.append(self.DefaultLangSys.collect_features())
    return _uniq_sort(sum(feature_indices, []))


@_add_method(otTables.ScriptList)
def subset_features(self, feature_indices, retain_empty):
    # https://bugzilla.mozilla.org/show_bug.cgi?id=1331737#c32
    self.ScriptRecord = [
        s
        for s in self.ScriptRecord
        if s.Script.subset_features(feature_indices, s.ScriptTag == "DFLT")
        or retain_empty
    ]
    self.ScriptCount = len(self.ScriptRecord)
    return bool(self.ScriptCount)


@_add_method(otTables.ScriptList)
def prune_features(self, feature_index_map, retain_empty):
    # https://bugzilla.mozilla.org/show_bug.cgi?id=1331737#c32
    self.ScriptRecord = [
        s
        for s in self.ScriptRecord
        if s.Script.prune_features(feature_index_map, s.ScriptTag == "DFLT")
        or retain_empty
    ]
    self.ScriptCount = len(self.ScriptRecord)
    return bool(self.ScriptCount)


@_add_method(otTables.ScriptList)
def collect_features(self):
    return _uniq_sort(sum((s.Script.collect_features() for s in self.ScriptRecord), []))


# CBLC will inherit it
@_add_method(ttLib.getTableClass("EBLC"))
def subset_glyphs(self, s):
    for strike in self.strikes:
        for indexSubTable in strike.indexSubTables:
            indexSubTable.names = [n for n in indexSubTable.names if n in s.glyphs]
        strike.indexSubTables = [i for i in strike.indexSubTables if i.names]
    self.strikes = [s for s in self.strikes if s.indexSubTables]

    return True


# CBDT will inherit it
@_add_method(ttLib.getTableClass("EBDT"))
def subset_glyphs(self, s):
    strikeData = [
        {g: strike[g] for g in s.glyphs if g in strike} for strike in self.strikeData
    ]
    # Prune empty strikes
    # https://github.com/fonttools/fonttools/issues/1633
    self.strikeData = [strike for strike in strikeData if strike]
    return True


@_add_method(ttLib.getTableClass("sbix"))
def subset_glyphs(self, s):
    for strike in self.strikes.values():
        strike.glyphs = {g: strike.glyphs[g] for g in s.glyphs if g in strike.glyphs}

    return True


@_add_method(ttLib.getTableClass("GSUB"))
def closure_glyphs(self, s):
    s.table = self.table
    if self.table.ScriptList:
        feature_indices = self.table.ScriptList.collect_features()
    else:
        feature_indices = []
    if self.table.FeatureList:
        lookup_indices = self.table.FeatureList.collect_lookups(feature_indices)
    else:
        lookup_indices = []
    if getattr(self.table, "FeatureVariations", None):
        lookup_indices += self.table.FeatureVariations.collect_lookups(feature_indices)
    lookup_indices = _uniq_sort(lookup_indices)
    if self.table.LookupList:
        s._doneLookups = {}
        while True:
            orig_glyphs = frozenset(s.glyphs)
            for i in lookup_indices:
                if i >= self.table.LookupList.LookupCount:
                    continue
                if not self.table.LookupList.Lookup[i]:
                    continue
                self.table.LookupList.Lookup[i].closure_glyphs(s)
            if orig_glyphs == s.glyphs:
                break
        del s._doneLookups
    del s.table


@_add_method(ttLib.getTableClass("GSUB"), ttLib.getTableClass("GPOS"))
def subset_glyphs(self, s):
    s.glyphs = s.glyphs_gsubed
    if self.table.LookupList:
        lookup_indices = self.table.LookupList.subset_glyphs(s)
    else:
        lookup_indices = []
    self.subset_lookups(lookup_indices)
    return True


@_add_method(ttLib.getTableClass("GSUB"), ttLib.getTableClass("GPOS"))
def retain_empty_scripts(self):
    # https://github.com/fonttools/fonttools/issues/518
    # https://bugzilla.mozilla.org/show_bug.cgi?id=1080739#c15
    return self.__class__ == ttLib.getTableClass("GSUB")


@_add_method(ttLib.getTableClass("GSUB"), ttLib.getTableClass("GPOS"))
def subset_lookups(self, lookup_indices):
    """Retains specified lookups, then removes empty features, language
    systems, and scripts."""
    if self.table.LookupList:
        self.table.LookupList.subset_lookups(lookup_indices)
    if self.table.FeatureList:
        feature_indices = self.table.FeatureList.subset_lookups(lookup_indices)
    else:
        feature_indices = []
    if getattr(self.table, "FeatureVariations", None):
        feature_indices += self.table.FeatureVariations.subset_lookups(lookup_indices)
    feature_indices = _uniq_sort(feature_indices)
    if self.table.FeatureList:
        self.table.FeatureList.subset_features(feature_indices)
    if getattr(self.table, "FeatureVariations", None):
        self.table.FeatureVariations.subset_features(feature_indices)
    if self.table.ScriptList:
        self.table.ScriptList.subset_features(
            feature_indices, self.retain_empty_scripts()
        )


@_add_method(ttLib.getTableClass("GSUB"), ttLib.getTableClass("GPOS"))
def neuter_lookups(self, lookup_indices):
    """Sets lookups not in lookup_indices to None."""
    if self.table.LookupList:
        self.table.LookupList.neuter_lookups(lookup_indices)


@_add_method(ttLib.getTableClass("GSUB"), ttLib.getTableClass("GPOS"))
def prune_lookups(self, remap=True):
    """Remove (default) or neuter unreferenced lookups"""
    if self.table.ScriptList:
        feature_indices = self.table.ScriptList.collect_features()
    else:
        feature_indices = []
    if self.table.FeatureList:
        lookup_indices = self.table.FeatureList.collect_lookups(feature_indices)
    else:
        lookup_indices = []
    if getattr(self.table, "FeatureVariations", None):
        lookup_indices += self.table.FeatureVariations.collect_lookups(feature_indices)
    lookup_indices = _uniq_sort(lookup_indices)
    if self.table.LookupList:
        lookup_indices = self.table.LookupList.closure_lookups(lookup_indices)
    else:
        lookup_indices = []
    if remap:
        self.subset_lookups(lookup_indices)
    else:
        self.neuter_lookups(lookup_indices)


@_add_method(ttLib.getTableClass("GSUB"), ttLib.getTableClass("GPOS"))
def subset_feature_tags(self, feature_tags):
    if self.table.FeatureList:
        feature_indices = [
            i
            for i, f in enumerate(self.table.FeatureList.FeatureRecord)
            if f.FeatureTag in feature_tags
        ]
        self.table.FeatureList.subset_features(feature_indices)
        if getattr(self.table, "FeatureVariations", None):
            self.table.FeatureVariations.subset_features(feature_indices)
    else:
        feature_indices = []
    if self.table.ScriptList:
        self.table.ScriptList.subset_features(
            feature_indices, self.retain_empty_scripts()
        )


@_add_method(ttLib.getTableClass("GSUB"), ttLib.getTableClass("GPOS"))
def subset_script_tags(self, tags):
    langsys = {}
    script_tags = set()
    for tag in tags:
        script_tag, lang_tag = tag.split(".") if "." in tag else (tag, "*")
        script_tags.add(script_tag.ljust(4))
        langsys.setdefault(script_tag, set()).add(lang_tag.ljust(4))

    if self.table.ScriptList:
        self.table.ScriptList.ScriptRecord = [
            s for s in self.table.ScriptList.ScriptRecord if s.ScriptTag in script_tags
        ]
        self.table.ScriptList.ScriptCount = len(self.table.ScriptList.ScriptRecord)

        for record in self.table.ScriptList.ScriptRecord:
            if record.ScriptTag in langsys and "*   " not in langsys[record.ScriptTag]:
                record.Script.LangSysRecord = [
                    l
                    for l in record.Script.LangSysRecord
                    if l.LangSysTag in langsys[record.ScriptTag]
                ]
                record.Script.LangSysCount = len(record.Script.LangSysRecord)
                if "dflt" not in langsys[record.ScriptTag]:
                    record.Script.DefaultLangSys = None


@_add_method(ttLib.getTableClass("GSUB"), ttLib.getTableClass("GPOS"))
def prune_features(self):
    """Remove unreferenced and duplicate features in FeatureList
    Remove unreferenced features and remap duplicate feature indices in ScriptList and FeatureVariations
    """
    if self.table.ScriptList:
        feature_indices = self.table.ScriptList.collect_features()
    else:
        feature_indices = []
    (feature_indices, feature_index_map) = self.remap_duplicate_features(
        feature_indices
    )

    if self.table.FeatureList:
        self.table.FeatureList.subset_features(feature_indices)
    if getattr(self.table, "FeatureVariations", None):
        self.table.FeatureVariations.prune_features(feature_index_map)
    if self.table.ScriptList:
        self.table.ScriptList.prune_features(
            feature_index_map, self.retain_empty_scripts()
        )


@_add_method(ttLib.getTableClass("GSUB"), ttLib.getTableClass("GPOS"))
def remap_duplicate_features(self, feature_indices):
    """Return retained feature indices(without duplicates) and remapped feature indices"""
    features = self.table.FeatureList.FeatureRecord

    unique_features = {}
    duplicate_features = {}
    for i in feature_indices:
        f = features[i]
        tag = f.FeatureTag

        same_tag_features = unique_features.get(tag)
        if same_tag_features is None:
            unique_features[tag] = set([i])
            duplicate_features[i] = i
            continue

        found = False
        for other_i in same_tag_features:
            if features[other_i] == f:
                found = True
                duplicate_features[i] = other_i
                break

        if not found:
            same_tag_features.add(i)
            duplicate_features[i] = i

    ## remap retained feature indices
    feature_map = {}
    new_idx = 0

    for i in feature_indices:
        unique_i = duplicate_features.get(i, i)
        v = feature_map.get(unique_i)
        if v is None:
            feature_map[i] = new_idx
            new_idx += 1
        else:
            feature_map[i] = v

    retained_feature_indices = _uniq_sort(
        sum((list(s) for s in unique_features.values()), [])
    )
    return (retained_feature_indices, feature_map)


@_add_method(ttLib.getTableClass("GSUB"), ttLib.getTableClass("GPOS"))
def prune_pre_subset(self, font, options):
    # Drop undesired features
    if "*" not in options.layout_scripts:
        self.subset_script_tags(options.layout_scripts)
    if "*" not in options.layout_features:
        self.subset_feature_tags(options.layout_features)
    # Neuter unreferenced lookups
    self.prune_lookups(remap=False)
    return True


@_add_method(ttLib.getTableClass("GSUB"), ttLib.getTableClass("GPOS"))
def remove_redundant_langsys(self):
    table = self.table
    if not table.ScriptList or not table.FeatureList:
        return

    features = table.FeatureList.FeatureRecord

    for s in table.ScriptList.ScriptRecord:
        d = s.Script.DefaultLangSys
        if not d:
            continue
        for lr in s.Script.LangSysRecord[:]:
            l = lr.LangSys
            # Compare d and l
            if len(d.FeatureIndex) != len(l.FeatureIndex):
                continue
            if (d.ReqFeatureIndex == 65535) != (l.ReqFeatureIndex == 65535):
                continue

            if d.ReqFeatureIndex != 65535:
                if features[d.ReqFeatureIndex] != features[l.ReqFeatureIndex]:
                    continue

            for i in range(len(d.FeatureIndex)):
                if features[d.FeatureIndex[i]] != features[l.FeatureIndex[i]]:
                    break
            else:
                # LangSys and default are equal; delete LangSys
                s.Script.LangSysRecord.remove(lr)


@_add_method(ttLib.getTableClass("GSUB"), ttLib.getTableClass("GPOS"))
def prune_post_subset(self, font, options):
    table = self.table

    self.prune_lookups()  # XXX Is this actually needed?!

    if table.LookupList:
        table.LookupList.prune_post_subset(font, options)
        # XXX Next two lines disabled because OTS is stupid and
        # doesn't like NULL offsets here.
        # if not table.LookupList.Lookup:
        # 	table.LookupList = None

    if not table.LookupList:
        table.FeatureList = None

    if table.FeatureList:
        self.remove_redundant_langsys()
        # Remove unreferenced features
        self.prune_features()

    # XXX Next two lines disabled because OTS is stupid and
    # doesn't like NULL offsets here.
    # if table.FeatureList and not table.FeatureList.FeatureRecord:
    # 	table.FeatureList = None

    # Never drop scripts themselves as them just being available
    # holds semantic significance.
    # XXX Next two lines disabled because OTS is stupid and
    # doesn't like NULL offsets here.
    # if table.ScriptList and not table.ScriptList.ScriptRecord:
    # 	table.ScriptList = None

    if hasattr(table, "FeatureVariations"):
        # drop FeatureVariations if there are no features to substitute
        if table.FeatureVariations and not (
            table.FeatureList and table.FeatureVariations.FeatureVariationRecord
        ):
            table.FeatureVariations = None

        # downgrade table version if there are no FeatureVariations
        if not table.FeatureVariations and table.Version == 0x00010001:
            table.Version = 0x00010000

    return True


@_add_method(ttLib.getTableClass("GDEF"))
def subset_glyphs(self, s):
    glyphs = s.glyphs_gsubed
    table = self.table
    if table.LigCaretList:
        indices = table.LigCaretList.Coverage.subset(glyphs)
        table.LigCaretList.LigGlyph = _list_subset(table.LigCaretList.LigGlyph, indices)
        table.LigCaretList.LigGlyphCount = len(table.LigCaretList.LigGlyph)
    if table.MarkAttachClassDef:
        table.MarkAttachClassDef.classDefs = {
            g: v for g, v in table.MarkAttachClassDef.classDefs.items() if g in glyphs
        }
    if table.GlyphClassDef:
        table.GlyphClassDef.classDefs = {
            g: v for g, v in table.GlyphClassDef.classDefs.items() if g in glyphs
        }
    if table.AttachList:
        indices = table.AttachList.Coverage.subset(glyphs)
        GlyphCount = table.AttachList.GlyphCount
        table.AttachList.AttachPoint = [
            table.AttachList.AttachPoint[i] for i in indices if i < GlyphCount
        ]
        table.AttachList.GlyphCount = len(table.AttachList.AttachPoint)
    if hasattr(table, "MarkGlyphSetsDef") and table.MarkGlyphSetsDef:
        markGlyphSets = table.MarkGlyphSetsDef
        for coverage in markGlyphSets.Coverage:
            if coverage:
                coverage.subset(glyphs)

        s.used_mark_sets = [i for i, c in enumerate(markGlyphSets.Coverage) if c.glyphs]
        markGlyphSets.Coverage = [c for c in markGlyphSets.Coverage if c.glyphs]

    return True


def _pruneGDEF(font):
    if "GDEF" not in font:
        return
    gdef = font["GDEF"]
    table = gdef.table
    if not hasattr(table, "VarStore"):
        return

    store = table.VarStore

    usedVarIdxes = set()

    # Collect.
    table.collect_device_varidxes(usedVarIdxes)
    if "GPOS" in font:
        font["GPOS"].table.collect_device_varidxes(usedVarIdxes)

    # Subset.
    varidx_map = store.subset_varidxes(usedVarIdxes)

    # Map.
    table.remap_device_varidxes(varidx_map)
    if "GPOS" in font:
        font["GPOS"].table.remap_device_varidxes(varidx_map)


@_add_method(ttLib.getTableClass("GDEF"))
def prune_post_subset(self, font, options):
    table = self.table
    # XXX check these against OTS
    if table.LigCaretList and not table.LigCaretList.LigGlyphCount:
        table.LigCaretList = None
    if table.MarkAttachClassDef and not table.MarkAttachClassDef.classDefs:
        table.MarkAttachClassDef = None
    if table.GlyphClassDef and not table.GlyphClassDef.classDefs:
        table.GlyphClassDef = None
    if table.AttachList and not table.AttachList.GlyphCount:
        table.AttachList = None
    if hasattr(table, "VarStore"):
        _pruneGDEF(font)
        if table.VarStore.VarDataCount == 0:
            if table.Version == 0x00010003:
                table.Version = 0x00010002
    if (
        not hasattr(table, "MarkGlyphSetsDef")
        or not table.MarkGlyphSetsDef
        or not table.MarkGlyphSetsDef.Coverage
    ):
        table.MarkGlyphSetsDef = None
        if table.Version == 0x00010002:
            table.Version = 0x00010000
    return bool(
        table.LigCaretList
        or table.MarkAttachClassDef
        or table.GlyphClassDef
        or table.AttachList
        or (table.Version >= 0x00010002 and table.MarkGlyphSetsDef)
        or (table.Version >= 0x00010003 and table.VarStore)
    )


@_add_method(ttLib.getTableClass("kern"))
def prune_pre_subset(self, font, options):
    # Prune unknown kern table types
    self.kernTables = [t for t in self.kernTables if hasattr(t, "kernTable")]
    return bool(self.kernTables)


@_add_method(ttLib.getTableClass("kern"))
def subset_glyphs(self, s):
    glyphs = s.glyphs_gsubed
    for t in self.kernTables:
        t.kernTable = {
            (a, b): v
            for (a, b), v in t.kernTable.items()
            if a in glyphs and b in glyphs
        }
    self.kernTables = [t for t in self.kernTables if t.kernTable]
    return bool(self.kernTables)


@_add_method(ttLib.getTableClass("vmtx"))
def subset_glyphs(self, s):
    self.metrics = _dict_subset(self.metrics, s.glyphs)
    for g in s.glyphs_emptied:
        self.metrics[g] = (0, 0)
    return bool(self.metrics)


@_add_method(ttLib.getTableClass("hmtx"))
def subset_glyphs(self, s):
    self.metrics = _dict_subset(self.metrics, s.glyphs)
    for g in s.glyphs_emptied:
        self.metrics[g] = (0, 0)
    return True  # Required table


@_add_method(ttLib.getTableClass("hdmx"))
def subset_glyphs(self, s):
    self.hdmx = {sz: _dict_subset(l, s.glyphs) for sz, l in self.hdmx.items()}
    for sz in self.hdmx:
        for g in s.glyphs_emptied:
            self.hdmx[sz][g] = 0
    return bool(self.hdmx)


@_add_method(ttLib.getTableClass("ankr"))
def subset_glyphs(self, s):
    table = self.table.AnchorPoints
    assert table.Format == 0, "unknown 'ankr' format %s" % table.Format
    table.Anchors = {
        glyph: table.Anchors[glyph] for glyph in s.glyphs if glyph in table.Anchors
    }
    return len(table.Anchors) > 0


@_add_method(ttLib.getTableClass("bsln"))
def closure_glyphs(self, s):
    table = self.table.Baseline
    if table.Format in (2, 3):
        s.glyphs.add(table.StandardGlyph)


@_add_method(ttLib.getTableClass("bsln"))
def subset_glyphs(self, s):
    table = self.table.Baseline
    if table.Format in (1, 3):
        baselines = {
            glyph: table.BaselineValues.get(glyph, table.DefaultBaseline)
            for glyph in s.glyphs
        }
        if len(baselines) > 0:
            mostCommon, _cnt = Counter(baselines.values()).most_common(1)[0]
            table.DefaultBaseline = mostCommon
            baselines = {glyph: b for glyph, b in baselines.items() if b != mostCommon}
        if len(baselines) > 0:
            table.BaselineValues = baselines
        else:
            table.Format = {1: 0, 3: 2}[table.Format]
            del table.BaselineValues
    return True


@_add_method(ttLib.getTableClass("lcar"))
def subset_glyphs(self, s):
    table = self.table.LigatureCarets
    if table.Format in (0, 1):
        table.Carets = {
            glyph: table.Carets[glyph] for glyph in s.glyphs if glyph in table.Carets
        }
        return len(table.Carets) > 0
    else:
        assert False, "unknown 'lcar' format %s" % table.Format


@_add_method(ttLib.getTableClass("gvar"))
def prune_pre_subset(self, font, options):
    if options.notdef_glyph and not options.notdef_outline:
        self.variations[font.glyphOrder[0]] = []
    return True


@_add_method(ttLib.getTableClass("gvar"))
def subset_glyphs(self, s):
    self.variations = _dict_subset(self.variations, s.glyphs)
    self.glyphCount = len(self.variations)
    return bool(self.variations)


def _remap_index_map(s, varidx_map, table_map):
    map_ = {k: varidx_map[v] for k, v in table_map.mapping.items()}
    # Emptied glyphs are remapped to:
    # if GID <= last retained GID, 0/0: delta set for 0/0 is expected to exist & zeros compress well
    # if GID > last retained GID, major/minor of the last retained glyph: will be optimized out by table compiler
    last_idx = varidx_map[table_map.mapping[s.last_retained_glyph]]
    for g, i in s.reverseEmptiedGlyphMap.items():
        map_[g] = last_idx if i > s.last_retained_order else 0
    return map_


@_add_method(ttLib.getTableClass("HVAR"))
def subset_glyphs(self, s):
    table = self.table

    used = set()
    advIdxes_ = set()
    retainAdvMap = False

    if table.AdvWidthMap:
        table.AdvWidthMap.mapping = _dict_subset(table.AdvWidthMap.mapping, s.glyphs)
        used.update(table.AdvWidthMap.mapping.values())
    else:
        used.update(s.reverseOrigGlyphMap.values())
        advIdxes_ = used.copy()
        retainAdvMap = s.options.retain_gids

    if table.LsbMap:
        table.LsbMap.mapping = _dict_subset(table.LsbMap.mapping, s.glyphs)
        used.update(table.LsbMap.mapping.values())
    if table.RsbMap:
        table.RsbMap.mapping = _dict_subset(table.RsbMap.mapping, s.glyphs)
        used.update(table.RsbMap.mapping.values())

    varidx_map = table.VarStore.subset_varidxes(
        used, retainFirstMap=retainAdvMap, advIdxes=advIdxes_
    )

    if table.AdvWidthMap:
        table.AdvWidthMap.mapping = _remap_index_map(s, varidx_map, table.AdvWidthMap)
    if table.LsbMap:
        table.LsbMap.mapping = _remap_index_map(s, varidx_map, table.LsbMap)
    if table.RsbMap:
        table.RsbMap.mapping = _remap_index_map(s, varidx_map, table.RsbMap)

    # TODO Return emptiness...
    return True


@_add_method(ttLib.getTableClass("VVAR"))
def subset_glyphs(self, s):
    table = self.table

    used = set()
    advIdxes_ = set()
    retainAdvMap = False

    if table.AdvHeightMap:
        table.AdvHeightMap.mapping = _dict_subset(table.AdvHeightMap.mapping, s.glyphs)
        used.update(table.AdvHeightMap.mapping.values())
    else:
        used.update(s.reverseOrigGlyphMap.values())
        advIdxes_ = used.copy()
        retainAdvMap = s.options.retain_gids

    if table.TsbMap:
        table.TsbMap.mapping = _dict_subset(table.TsbMap.mapping, s.glyphs)
        used.update(table.TsbMap.mapping.values())
    if table.BsbMap:
        table.BsbMap.mapping = _dict_subset(table.BsbMap.mapping, s.glyphs)
        used.update(table.BsbMap.mapping.values())
    if table.VOrgMap:
        table.VOrgMap.mapping = _dict_subset(table.VOrgMap.mapping, s.glyphs)
        used.update(table.VOrgMap.mapping.values())

    varidx_map = table.VarStore.subset_varidxes(
        used, retainFirstMap=retainAdvMap, advIdxes=advIdxes_
    )

    if table.AdvHeightMap:
        table.AdvHeightMap.mapping = _remap_index_map(s, varidx_map, table.AdvHeightMap)
    if table.TsbMap:
        table.TsbMap.mapping = _remap_index_map(s, varidx_map, table.TsbMap)
    if table.BsbMap:
        table.BsbMap.mapping = _remap_index_map(s, varidx_map, table.BsbMap)
    if table.VOrgMap:
        table.VOrgMap.mapping = _remap_index_map(s, varidx_map, table.VOrgMap)

    # TODO Return emptiness...
    return True


@_add_method(ttLib.getTableClass("VORG"))
def subset_glyphs(self, s):
    self.VOriginRecords = {
        g: v for g, v in self.VOriginRecords.items() if g in s.glyphs
    }
    self.numVertOriginYMetrics = len(self.VOriginRecords)
    return True  # Never drop; has default metrics


@_add_method(ttLib.getTableClass("opbd"))
def subset_glyphs(self, s):
    table = self.table.OpticalBounds
    if table.Format == 0:
        table.OpticalBoundsDeltas = {
            glyph: table.OpticalBoundsDeltas[glyph]
            for glyph in s.glyphs
            if glyph in table.OpticalBoundsDeltas
        }
        return len(table.OpticalBoundsDeltas) > 0
    elif table.Format == 1:
        table.OpticalBoundsPoints = {
            glyph: table.OpticalBoundsPoints[glyph]
            for glyph in s.glyphs
            if glyph in table.OpticalBoundsPoints
        }
        return len(table.OpticalBoundsPoints) > 0
    else:
        assert False, "unknown 'opbd' format %s" % table.Format


@_add_method(ttLib.getTableClass("post"))
def prune_pre_subset(self, font, options):
    if not options.glyph_names:
        self.formatType = 3.0
    return True  # Required table


@_add_method(ttLib.getTableClass("post"))
def subset_glyphs(self, s):
    self.extraNames = []  # This seems to do it
    return True  # Required table


@_add_method(ttLib.getTableClass("prop"))
def subset_glyphs(self, s):
    prop = self.table.GlyphProperties
    if prop.Format == 0:
        return prop.DefaultProperties != 0
    elif prop.Format == 1:
        prop.Properties = {
            g: prop.Properties.get(g, prop.DefaultProperties) for g in s.glyphs
        }
        mostCommon, _cnt = Counter(prop.Properties.values()).most_common(1)[0]
        prop.DefaultProperties = mostCommon
        prop.Properties = {
            g: prop for g, prop in prop.Properties.items() if prop != mostCommon
        }
        if len(prop.Properties) == 0:
            del prop.Properties
            prop.Format = 0
            return prop.DefaultProperties != 0
        return True
    else:
        assert False, "unknown 'prop' format %s" % prop.Format


def _paint_glyph_names(paint, colr):
    result = set()

    def callback(paint):
        if paint.Format in {
            otTables.PaintFormat.PaintGlyph,
            otTables.PaintFormat.PaintColrGlyph,
        }:
            result.add(paint.Glyph)

    paint.traverse(colr, callback)
    return result


@_add_method(ttLib.getTableClass("COLR"))
def closure_glyphs(self, s):
    if self.version > 0:
        # on decompiling COLRv1, we only keep around the raw otTables
        # but for subsetting we need dicts with fully decompiled layers;
        # we store them temporarily in the C_O_L_R_ instance and delete
        # them after we have finished subsetting.
        self.ColorLayers = self._decompileColorLayersV0(self.table)
        self.ColorLayersV1 = {
            rec.BaseGlyph: rec.Paint
            for rec in self.table.BaseGlyphList.BaseGlyphPaintRecord
        }

    decompose = s.glyphs
    while decompose:
        layers = set()
        for g in decompose:
            for layer in self.ColorLayers.get(g, []):
                layers.add(layer.name)

            if self.version > 0:
                paint = self.ColorLayersV1.get(g)
                if paint is not None:
                    layers.update(_paint_glyph_names(paint, self.table))

        layers -= s.glyphs
        s.glyphs.update(layers)
        decompose = layers


@_add_method(ttLib.getTableClass("COLR"))
def subset_glyphs(self, s):
    from fontTools.colorLib.unbuilder import unbuildColrV1
    from fontTools.colorLib.builder import buildColrV1, populateCOLRv0

    # only include glyphs after COLR closure, which in turn comes after cmap and GSUB
    # closure, but importantly before glyf/CFF closures. COLR layers can refer to
    # composite glyphs, and that's ok, since glyf/CFF closures happen after COLR closure
    # and take care of those. If we also included glyphs resulting from glyf/CFF closures
    # when deciding which COLR base glyphs to retain, then we may end up with a situation
    # whereby a COLR base glyph is kept, not because directly requested (cmap)
    # or substituted (GSUB) or referenced by another COLRv1 PaintColrGlyph, but because
    # it corresponds to (has same GID as) a non-COLR glyph that happens to be used as a
    # component in glyf or CFF table. Best case scenario we retain more glyphs than
    # required; worst case we retain incomplete COLR records that try to reference
    # glyphs that are no longer in the final subset font.
    # https://github.com/fonttools/fonttools/issues/2461
    s.glyphs = s.glyphs_colred

    self.ColorLayers = {
        g: self.ColorLayers[g] for g in s.glyphs if g in self.ColorLayers
    }
    if self.version == 0:
        return bool(self.ColorLayers)

    colorGlyphsV1 = unbuildColrV1(self.table.LayerList, self.table.BaseGlyphList)
    self.table.LayerList, self.table.BaseGlyphList = buildColrV1(
        {g: colorGlyphsV1[g] for g in colorGlyphsV1 if g in s.glyphs}
    )
    del self.ColorLayersV1

    if self.table.ClipList is not None:
        clips = self.table.ClipList.clips
        self.table.ClipList.clips = {g: clips[g] for g in clips if g in s.glyphs}

    layersV0 = self.ColorLayers
    if not self.table.BaseGlyphList.BaseGlyphPaintRecord:
        # no more COLRv1 glyphs: downgrade to version 0
        self.version = 0
        del self.table
        return bool(layersV0)

    populateCOLRv0(
        self.table,
        {g: [(layer.name, layer.colorID) for layer in layersV0[g]] for g in layersV0},
    )
    del self.ColorLayers

    # TODO: also prune ununsed varIndices in COLR.VarStore
    return True


@_add_method(ttLib.getTableClass("CPAL"))
def prune_post_subset(self, font, options):
    # Keep whole "CPAL" if "SVG " is present as it may be referenced by the latter
    # via 'var(--color{palette_entry_index}, ...)' CSS color variables.
    # For now we just assume this is the case by the mere presence of "SVG " table,
    # for parsing SVG to collect all the used indices is too much work...
    # TODO(anthrotype): Do The Right Thing (TM).
    if "SVG " in font:
        return True

    colr = font.get("COLR")
    if not colr:  # drop CPAL if COLR was subsetted to empty
        return False

    colors_by_index = defaultdict(list)

    def collect_colors_by_index(paint):
        if hasattr(paint, "PaletteIndex"):  # either solid colors...
            colors_by_index[paint.PaletteIndex].append(paint)
        elif hasattr(paint, "ColorLine"):  # ... or gradient color stops
            for stop in paint.ColorLine.ColorStop:
                colors_by_index[stop.PaletteIndex].append(stop)

    if colr.version == 0:
        for layers in colr.ColorLayers.values():
            for layer in layers:
                colors_by_index[layer.colorID].append(layer)
    else:
        if colr.table.LayerRecordArray:
            for layer in colr.table.LayerRecordArray.LayerRecord:
                colors_by_index[layer.PaletteIndex].append(layer)
        for record in colr.table.BaseGlyphList.BaseGlyphPaintRecord:
            record.Paint.traverse(colr.table, collect_colors_by_index)

    # don't remap palette entry index 0xFFFF, this is always the foreground color
    # https://github.com/fonttools/fonttools/issues/2257
    retained_palette_indices = set(colors_by_index.keys()) - {0xFFFF}
    for palette in self.palettes:
        palette[:] = [c for i, c in enumerate(palette) if i in retained_palette_indices]
        assert len(palette) == len(retained_palette_indices)

    for new_index, old_index in enumerate(sorted(retained_palette_indices)):
        for record in colors_by_index[old_index]:
            if hasattr(record, "colorID"):  # v0
                record.colorID = new_index
            elif hasattr(record, "PaletteIndex"):  # v1
                record.PaletteIndex = new_index
            else:
                raise AssertionError(record)

    self.numPaletteEntries = len(self.palettes[0])

    if self.version == 1:
        kept_labels = []
        for i, label in enumerate(self.paletteEntryLabels):
            if i in retained_palette_indices:
                kept_labels.append(label)
        self.paletteEntryLabels = kept_labels
    return bool(self.numPaletteEntries)


@_add_method(otTables.MathGlyphConstruction)
def closure_glyphs(self, glyphs):
    variants = set()
    for v in self.MathGlyphVariantRecord:
        variants.add(v.VariantGlyph)
    if self.GlyphAssembly:
        for p in self.GlyphAssembly.PartRecords:
            variants.add(p.glyph)
    return variants


@_add_method(otTables.MathVariants)
def closure_glyphs(self, s):
    glyphs = frozenset(s.glyphs)
    variants = set()

    if self.VertGlyphCoverage:
        indices = self.VertGlyphCoverage.intersect(glyphs)
        for i in indices:
            variants.update(self.VertGlyphConstruction[i].closure_glyphs(glyphs))

    if self.HorizGlyphCoverage:
        indices = self.HorizGlyphCoverage.intersect(glyphs)
        for i in indices:
            variants.update(self.HorizGlyphConstruction[i].closure_glyphs(glyphs))

    s.glyphs.update(variants)


@_add_method(ttLib.getTableClass("VARC"))
def subset_glyphs(self, s):
    indices = self.table.Coverage.subset(s.glyphs)
    self.table.VarCompositeGlyphs.VarCompositeGlyph = _list_subset(
        self.table.VarCompositeGlyphs.VarCompositeGlyph, indices
    )
    return bool(self.table.VarCompositeGlyphs.VarCompositeGlyph)


@_add_method(ttLib.getTableClass("VARC"))
def closure_glyphs(self, s):
    if self.table.VarCompositeGlyphs is None:
        return

    glyphMap = {glyphName: i for i, glyphName in enumerate(self.table.Coverage.glyphs)}
    glyphRecords = self.table.VarCompositeGlyphs.VarCompositeGlyph

    glyphs = s.glyphs
    covered = set()
    new = set(glyphs)
    while new:
        oldNew = new
        new = set()
        for glyphName in oldNew:
            if glyphName in covered:
                continue
            idx = glyphMap.get(glyphName)
            if idx is None:
                continue
            glyph = glyphRecords[idx]
            for comp in glyph.components:
                name = comp.glyphName
                glyphs.add(name)
                if name not in covered:
                    new.add(name)


@_add_method(ttLib.getTableClass("VARC"))
def prune_post_subset(self, font, options):
    table = self.table

    store = table.MultiVarStore
    if store is not None:
        usedVarIdxes = set()
        table.collect_varidxes(usedVarIdxes)
        varidx_map = store.subset_varidxes(usedVarIdxes)
        table.remap_varidxes(varidx_map)

    axisIndicesList = table.AxisIndicesList.Item
    if axisIndicesList is not None:
        usedIndices = set()
        for glyph in table.VarCompositeGlyphs.VarCompositeGlyph:
            for comp in glyph.components:
                if comp.axisIndicesIndex is not None:
                    usedIndices.add(comp.axisIndicesIndex)
        usedIndices = sorted(usedIndices)
        table.AxisIndicesList.Item = _list_subset(axisIndicesList, usedIndices)
        mapping = {old: new for new, old in enumerate(usedIndices)}
        for glyph in table.VarCompositeGlyphs.VarCompositeGlyph:
            for comp in glyph.components:
                if comp.axisIndicesIndex is not None:
                    comp.axisIndicesIndex = mapping[comp.axisIndicesIndex]

    conditionList = table.ConditionList
    if conditionList is not None:
        conditionTables = conditionList.ConditionTable
        usedIndices = set()
        for glyph in table.VarCompositeGlyphs.VarCompositeGlyph:
            for comp in glyph.components:
                if comp.conditionIndex is not None:
                    usedIndices.add(comp.conditionIndex)
        usedIndices = sorted(usedIndices)
        conditionList.ConditionTable = _list_subset(conditionTables, usedIndices)
        mapping = {old: new for new, old in enumerate(usedIndices)}
        for glyph in table.VarCompositeGlyphs.VarCompositeGlyph:
            for comp in glyph.components:
                if comp.conditionIndex is not None:
                    comp.conditionIndex = mapping[comp.conditionIndex]

    return True


@_add_method(ttLib.getTableClass("MATH"))
def closure_glyphs(self, s):
    if self.table.MathVariants:
        self.table.MathVariants.closure_glyphs(s)


@_add_method(otTables.MathItalicsCorrectionInfo)
def subset_glyphs(self, s):
    indices = self.Coverage.subset(s.glyphs)
    self.ItalicsCorrection = _list_subset(self.ItalicsCorrection, indices)
    self.ItalicsCorrectionCount = len(self.ItalicsCorrection)
    return bool(self.ItalicsCorrectionCount)


@_add_method(otTables.MathTopAccentAttachment)
def subset_glyphs(self, s):
    indices = self.TopAccentCoverage.subset(s.glyphs)
    self.TopAccentAttachment = _list_subset(self.TopAccentAttachment, indices)
    self.TopAccentAttachmentCount = len(self.TopAccentAttachment)
    return bool(self.TopAccentAttachmentCount)


@_add_method(otTables.MathKernInfo)
def subset_glyphs(self, s):
    indices = self.MathKernCoverage.subset(s.glyphs)
    self.MathKernInfoRecords = _list_subset(self.MathKernInfoRecords, indices)
    self.MathKernCount = len(self.MathKernInfoRecords)
    return bool(self.MathKernCount)


@_add_method(otTables.MathGlyphInfo)
def subset_glyphs(self, s):
    if self.MathItalicsCorrectionInfo:
        self.MathItalicsCorrectionInfo.subset_glyphs(s)
    if self.MathTopAccentAttachment:
        self.MathTopAccentAttachment.subset_glyphs(s)
    if self.MathKernInfo:
        self.MathKernInfo.subset_glyphs(s)
    if self.ExtendedShapeCoverage:
        self.ExtendedShapeCoverage.subset(s.glyphs)
    return True


@_add_method(otTables.MathVariants)
def subset_glyphs(self, s):
    if self.VertGlyphCoverage:
        indices = self.VertGlyphCoverage.subset(s.glyphs)
        self.VertGlyphConstruction = _list_subset(self.VertGlyphConstruction, indices)
        self.VertGlyphCount = len(self.VertGlyphConstruction)

    if self.HorizGlyphCoverage:
        indices = self.HorizGlyphCoverage.subset(s.glyphs)
        self.HorizGlyphConstruction = _list_subset(self.HorizGlyphConstruction, indices)
        self.HorizGlyphCount = len(self.HorizGlyphConstruction)

    return True


@_add_method(ttLib.getTableClass("MATH"))
def subset_glyphs(self, s):
    s.glyphs = s.glyphs_mathed
    if self.table.MathGlyphInfo:
        self.table.MathGlyphInfo.subset_glyphs(s)
    if self.table.MathVariants:
        self.table.MathVariants.subset_glyphs(s)
    return True


@_add_method(ttLib.getTableModule("glyf").Glyph)
def remapComponentsFast(self, glyphidmap):
    if not self.data or struct.unpack(">h", self.data[:2])[0] >= 0:
        return  # Not composite
    data = self.data = bytearray(self.data)
    i = 10
    more = 1
    while more:
        flags = (data[i] << 8) | data[i + 1]
        glyphID = (data[i + 2] << 8) | data[i + 3]
        # Remap
        glyphID = glyphidmap[glyphID]
        data[i + 2] = glyphID >> 8
        data[i + 3] = glyphID & 0xFF
        i += 4
        flags = int(flags)

        if flags & 0x0001:
            i += 4  # ARG_1_AND_2_ARE_WORDS
        else:
            i += 2
        if flags & 0x0008:
            i += 2  # WE_HAVE_A_SCALE
        elif flags & 0x0040:
            i += 4  # WE_HAVE_AN_X_AND_Y_SCALE
        elif flags & 0x0080:
            i += 8  # WE_HAVE_A_TWO_BY_TWO
        more = flags & 0x0020  # MORE_COMPONENTS


@_add_method(ttLib.getTableClass("glyf"))
def closure_glyphs(self, s):
    glyphSet = self.glyphs
    decompose = s.glyphs
    while decompose:
        components = set()
        for g in decompose:
            if g not in glyphSet:
                continue
            gl = glyphSet[g]
            for c in gl.getComponentNames(self):
                components.add(c)
        components -= s.glyphs
        s.glyphs.update(components)
        decompose = components


@_add_method(ttLib.getTableClass("glyf"))
def prune_pre_subset(self, font, options):
    if options.notdef_glyph and not options.notdef_outline:
        g = self[self.glyphOrder[0]]
        # Yay, easy!
        g.__dict__.clear()
        g.data = b""
    return True


@_add_method(ttLib.getTableClass("glyf"))
def subset_glyphs(self, s):
    self.glyphs = _dict_subset(self.glyphs, s.glyphs)
    if not s.options.retain_gids:
        indices = [i for i, g in enumerate(self.glyphOrder) if g in s.glyphs]
        glyphmap = {o: n for n, o in enumerate(indices)}
        for v in self.glyphs.values():
            if hasattr(v, "data"):
                v.remapComponentsFast(glyphmap)
    Glyph = ttLib.getTableModule("glyf").Glyph
    for g in s.glyphs_emptied:
        self.glyphs[g] = Glyph()
        self.glyphs[g].data = b""
    self.glyphOrder = [
        g for g in self.glyphOrder if g in s.glyphs or g in s.glyphs_emptied
    ]
    # Don't drop empty 'glyf' tables, otherwise 'loca' doesn't get subset.
    return True


@_add_method(ttLib.getTableClass("glyf"))
def prune_post_subset(self, font, options):
    remove_hinting = not options.hinting
    for v in self.glyphs.values():
        v.trim(remove_hinting=remove_hinting)
    return True


@_add_method(ttLib.getTableClass("cmap"))
def closure_glyphs(self, s):
    tables = [t for t in self.tables if t.isUnicode()]

    # Closure unicodes, which for now is pulling in bidi mirrored variants
    if s.options.bidi_closure:
        additional_unicodes = set()
        for u in s.unicodes_requested:
            mirror_u = mirrored(u)
            if mirror_u is not None:
                additional_unicodes.add(mirror_u)
        s.unicodes_requested.update(additional_unicodes)

    # Close glyphs
    for table in tables:
        if table.format == 14:
            for varSelector, cmap in table.uvsDict.items():
                if varSelector not in s.unicodes_requested:
                    continue
                glyphs = {g for u, g in cmap if u in s.unicodes_requested}
                if None in glyphs:
                    glyphs.remove(None)
                s.glyphs.update(glyphs)
        else:
            cmap = table.cmap
            intersection = s.unicodes_requested.intersection(cmap.keys())
            s.glyphs.update(cmap[u] for u in intersection)

    # Calculate unicodes_missing
    s.unicodes_missing = s.unicodes_requested.copy()
    for table in tables:
        s.unicodes_missing.difference_update(table.cmap)


@_add_method(ttLib.getTableClass("cmap"))
def prune_pre_subset(self, font, options):
    if not options.legacy_cmap:
        # Drop non-Unicode / non-Symbol cmaps
        self.tables = [t for t in self.tables if t.isUnicode() or t.isSymbol()]
    if not options.symbol_cmap:
        self.tables = [t for t in self.tables if not t.isSymbol()]
    # TODO(behdad) Only keep one subtable?
    # For now, drop format=0 which can't be subset_glyphs easily?
    self.tables = [t for t in self.tables if t.format != 0]
    self.numSubTables = len(self.tables)
    return True  # Required table


@_add_method(ttLib.getTableClass("cmap"))
def subset_glyphs(self, s):
    s.glyphs = None  # We use s.glyphs_requested and s.unicodes_requested only

    tables_format12_bmp = []
    table_plat0_enc3 = {}  # Unicode platform, Unicode BMP only, keyed by language
    table_plat3_enc1 = {}  # Windows platform, Unicode BMP, keyed by language

    for t in self.tables:
        if t.platformID == 0 and t.platEncID == 3:
            table_plat0_enc3[t.language] = t
        if t.platformID == 3 and t.platEncID == 1:
            table_plat3_enc1[t.language] = t

        if t.format == 14:
            # TODO(behdad) We drop all the default-UVS mappings
            # for glyphs_requested.  So it's the caller's responsibility to make
            # sure those are included.
            t.uvsDict = {
                v: [
                    (u, g)
                    for u, g in l
                    if g in s.glyphs_requested or u in s.unicodes_requested
                ]
                for v, l in t.uvsDict.items()
                if v in s.unicodes_requested
            }
            t.uvsDict = {v: l for v, l in t.uvsDict.items() if l}
        elif t.isUnicode():
            t.cmap = {
                u: g
                for u, g in t.cmap.items()
                if g in s.glyphs_requested or u in s.unicodes_requested
            }
            # Collect format 12 tables that hold only basic multilingual plane
            # codepoints.
            if t.format == 12 and t.cmap and max(t.cmap.keys()) < 0x10000:
                tables_format12_bmp.append(t)
        else:
            t.cmap = {u: g for u, g in t.cmap.items() if g in s.glyphs_requested}

    # Fomat 12 tables are redundant if they contain just the same BMP codepoints
    # their little BMP-only encoding siblings contain.
    for t in tables_format12_bmp:
        if (
            t.platformID == 0  # Unicode platform
            and t.platEncID == 4  # Unicode full repertoire
            and t.language in table_plat0_enc3  # Have a BMP-only sibling?
            and table_plat0_enc3[t.language].cmap == t.cmap
        ):
            t.cmap.clear()
        elif (
            t.platformID == 3  # Windows platform
            and t.platEncID == 10  # Unicode full repertoire
            and t.language in table_plat3_enc1  # Have a BMP-only sibling?
            and table_plat3_enc1[t.language].cmap == t.cmap
        ):
            t.cmap.clear()

    self.tables = [t for t in self.tables if (t.cmap if t.format != 14 else t.uvsDict)]
    self.numSubTables = len(self.tables)
    # TODO(behdad) Convert formats when needed.
    # In particular, if we have a format=12 without non-BMP
    # characters, convert it to format=4 if there's not one.
    return True  # Required table


@_add_method(ttLib.getTableClass("DSIG"))
def prune_pre_subset(self, font, options):
    # Drop all signatures since they will be invalid
    self.usNumSigs = 0
    self.signatureRecords = []
    return True


@_add_method(ttLib.getTableClass("maxp"))
def prune_pre_subset(self, font, options):
    if not options.hinting:
        if self.tableVersion == 0x00010000:
            self.maxZones = 1
            self.maxTwilightPoints = 0
            self.maxStorage = 0
            self.maxFunctionDefs = 0
            self.maxInstructionDefs = 0
            self.maxStackElements = 0
            self.maxSizeOfInstructions = 0
    return True


NAME_IDS_TO_OBFUSCATE = {1, 2, 3, 4, 6, 16, 17, 18}


@_add_method(ttLib.getTableClass("name"))
def prune_post_subset(self, font, options):
    visitor = NameRecordVisitor()
    visitor.visit(font)
    nameIDs = set(options.name_IDs) | visitor.seen
    if "*" in options.name_IDs:
        nameIDs |= {n.nameID for n in self.names if n.nameID < 256}
    self.names = [n for n in self.names if n.nameID in nameIDs]
    if not options.name_legacy:
        # TODO(behdad) Sometimes (eg Apple Color Emoji) there's only a macroman
        # entry for Latin and no Unicode names.
        self.names = [n for n in self.names if n.isUnicode()]
    # TODO(behdad) Option to keep only one platform's
    if "*" not in options.name_languages:
        # TODO(behdad) This is Windows-platform specific!
        self.names = [n for n in self.names if n.langID in options.name_languages]
    if options.obfuscate_names:
        namerecs = []
        # Preserve names to be scrambled or dropped elsewhere so that other
        # parts of the font don't break.
        needRemapping = visitor.seen.intersection(NAME_IDS_TO_OBFUSCATE)
        if needRemapping:
            _remap_select_name_ids(font, needRemapping)
        for n in self.names:
            if n.nameID in [1, 4]:
                n.string = ".\x7f".encode("utf_16_be") if n.isUnicode() else ".\x7f"
            elif n.nameID in [2, 6]:
                n.string = "\x7f".encode("utf_16_be") if n.isUnicode() else "\x7f"
            elif n.nameID == 3:
                n.string = ""
            elif n.nameID in [16, 17, 18]:
                continue
            namerecs.append(n)
        self.names = namerecs
    return True  # Required table


def _remap_select_name_ids(font: ttLib.TTFont, needRemapping: set[int]) -> None:
    """Remap a set of IDs so that the originals can be safely scrambled or
    dropped.

    For each name record whose name id is in the `needRemapping` set, make a copy
    and allocate a new unused name id in the font-specific range (> 255).

    Finally update references to these in the `fvar` and `STAT` tables.
    """

    if "fvar" not in font and "STAT" not in font:
        return

    name = font["name"]

    # 1. Assign new IDs for names to be preserved.
    existingIds = {record.nameID for record in name.names}
    remapping = {}
    nextId = name._findUnusedNameID() - 1  # Should skip gaps in name IDs.
    for nameId in needRemapping:
        nextId += 1  # We should have complete freedom until 32767.
        assert nextId not in existingIds, "_findUnusedNameID did not skip gaps"
        if nextId > 32767:
            raise ValueError("Ran out of name IDs while trying to remap existing ones.")
        remapping[nameId] = nextId

    # 2. Copy records to use the new ID. We can't rewrite them in place, because
    #    that could make IDs 1 to 6 "disappear" from code that follows. Some
    #    tools that produce EOT fonts expect them to exist, even when they're
    #    scrambled. See https://github.com/fonttools/fonttools/issues/165.
    copiedRecords = []
    for record in name.names:
        if record.nameID not in needRemapping:
            continue
        recordCopy = makeName(
            record.string,
            remapping[record.nameID],
            record.platformID,
            record.platEncID,
            record.langID,
        )
        copiedRecords.append(recordCopy)
    name.names.extend(copiedRecords)

    # 3. Rewrite the corresponding IDs in other tables. For now, care only about
    #    STAT and fvar. If more tables need to be changed, consider adapting
    #    NameRecordVisitor to rewrite IDs wherever it finds them.
    fvar = font.get("fvar")
    if fvar is not None:
        for axis in fvar.axes:
            axis.axisNameID = remapping.get(axis.axisNameID, axis.axisNameID)
        for instance in fvar.instances:
            nameID = instance.subfamilyNameID
            instance.subfamilyNameID = remapping.get(nameID, nameID)
            nameID = instance.postscriptNameID
            instance.postscriptNameID = remapping.get(nameID, nameID)

    stat = font.get("STAT")
    if stat is None:
        return
    elidedNameID = stat.table.ElidedFallbackNameID
    stat.table.ElidedFallbackNameID = remapping.get(elidedNameID, elidedNameID)
    if stat.table.DesignAxisRecord:
        for axis in stat.table.DesignAxisRecord.Axis:
            axis.AxisNameID = remapping.get(axis.AxisNameID, axis.AxisNameID)
    if stat.table.AxisValueArray:
        for value in stat.table.AxisValueArray.AxisValue:
            value.ValueNameID = remapping.get(value.ValueNameID, value.ValueNameID)


@_add_method(ttLib.getTableClass("head"))
def prune_post_subset(self, font, options):
    # Force re-compiling head table, to update any recalculated values.
    return True


# TODO(behdad) OS/2 ulCodePageRange?
# TODO(behdad) Drop AAT tables.
# TODO(behdad) Drop unneeded GSUB/GPOS Script/LangSys entries.
# TODO(behdad) Drop empty GSUB/GPOS, and GDEF if no GSUB/GPOS left
# TODO(behdad) Drop GDEF subitems if unused by lookups
# TODO(behdad) Avoid recursing too much (in GSUB/GPOS and in CFF)
# TODO(behdad) Text direction considerations.
# TODO(behdad) Text script / language considerations.
# TODO(behdad) Optionally drop 'kern' table if GPOS available
# TODO(behdad) Implement --unicode='*' to choose all cmap'ed
# TODO(behdad) Drop old-spec Indic scripts


class Options(object):
    class OptionError(Exception):
        pass

    class UnknownOptionError(OptionError):
        pass

    # spaces in tag names (e.g. "SVG ", "cvt ") are stripped by the argument parser
    _drop_tables_default = [
        "JSTF",
        "DSIG",
        "EBDT",
        "EBLC",
        "EBSC",
        "PCLT",
        "LTSH",
    ]
    _drop_tables_default += ["Feat", "Glat", "Gloc", "Silf", "Sill"]  # Graphite
    _no_subset_tables_default = [
        "avar",
        "BASE",
        "fvar",
        "gasp",
        "head",
        "hhea",
        "maxp",
        "vhea",
        "OS/2",
        "loca",
        "name",
        "cvt",
        "fpgm",
        "prep",
        "VDMX",
        "DSIG",
        "CPAL",
        "MVAR",
        "cvar",
        "STAT",
    ]
    _hinting_tables_default = ["cvt", "cvar", "fpgm", "prep", "hdmx", "VDMX"]

    # Based on HarfBuzz shapers
    _layout_features_groups = {
        # Default shaper
        "common": ["rvrn", "ccmp", "liga", "locl", "mark", "mkmk", "rlig"],
        "fractions": ["frac", "numr", "dnom"],
        "horizontal": ["calt", "clig", "curs", "kern", "rclt"],
        "vertical": ["valt", "vert", "vkrn", "vpal", "vrt2"],
        "ltr": ["ltra", "ltrm"],
        "rtl": ["rtla", "rtlm"],
        "rand": ["rand"],
        "justify": ["jalt"],
        "private": ["Harf", "HARF", "Buzz", "BUZZ"],
        "east_asian_spacing": ["chws", "vchw", "halt", "vhal"],
        # Complex shapers
        "arabic": [
            "init",
            "medi",
            "fina",
            "isol",
            "med2",
            "fin2",
            "fin3",
            "cswh",
            "mset",
            "stch",
        ],
        "hangul": ["ljmo", "vjmo", "tjmo"],
        "tibetan": ["abvs", "blws", "abvm", "blwm"],
        "indic": [
            "nukt",
            "akhn",
            "rphf",
            "rkrf",
            "pref",
            "blwf",
            "half",
            "abvf",
            "pstf",
            "cfar",
            "vatu",
            "cjct",
            "init",
            "pres",
            "abvs",
            "blws",
            "psts",
            "haln",
            "dist",
            "abvm",
            "blwm",
        ],
    }
    _layout_features_default = _uniq_sort(
        sum(iter(_layout_features_groups.values()), [])
    )

    def __init__(self, **kwargs):
        self.drop_tables = self._drop_tables_default[:]
        self.no_subset_tables = self._no_subset_tables_default[:]
        self.passthrough_tables = False  # keep/drop tables we can't subset
        self.hinting_tables = self._hinting_tables_default[:]
        self.legacy_kern = False  # drop 'kern' table if GPOS available
        self.layout_closure = True
        self.layout_features = self._layout_features_default[:]
        self.layout_scripts = ["*"]
        self.ignore_missing_glyphs = False
        self.ignore_missing_unicodes = True
        self.hinting = True
        self.glyph_names = False
        self.legacy_cmap = False
        self.symbol_cmap = False
        self.name_IDs = [
            0,
            1,
            2,
            3,
            4,
            5,
            6,
        ]  # https://github.com/fonttools/fonttools/issues/1170#issuecomment-364631225
        self.name_legacy = False
        self.name_languages = [0x0409]  # English
        self.obfuscate_names = False  # to make webfont unusable as a system font
        self.retain_gids = False
        self.notdef_glyph = True  # gid0 for TrueType / .notdef for CFF
        self.notdef_outline = False  # No need for notdef to have an outline really
        self.recommended_glyphs = False  # gid1, gid2, gid3 for TrueType
        self.recalc_bounds = False  # Recalculate font bounding boxes
        self.recalc_timestamp = False  # Recalculate font modified timestamp
        self.prune_unicode_ranges = True  # Clear unused 'ulUnicodeRange' bits
        self.prune_codepage_ranges = True  # Clear unused 'ulCodePageRange' bits
        self.recalc_average_width = False  # update 'xAvgCharWidth'
        self.recalc_max_context = False  # update 'usMaxContext'
        self.canonical_order = None  # Order tables as recommended
        self.flavor = None  # May be 'woff' or 'woff2'
        self.with_zopfli = False  # use zopfli instead of zlib for WOFF 1.0
        self.desubroutinize = False  # Desubroutinize CFF CharStrings
        self.harfbuzz_repacker = USE_HARFBUZZ_REPACKER.default
        self.verbose = False
        self.timing = False
        self.xml = False
        self.font_number = -1
        self.pretty_svg = False
        self.lazy = True
        self.bidi_closure = True

        self.set(**kwargs)

    def set(self, **kwargs):
        for k, v in kwargs.items():
            if not hasattr(self, k):
                raise self.UnknownOptionError("Unknown option '%s'" % k)
            setattr(self, k, v)

    def parse_opts(self, argv, ignore_unknown=[]):
        posargs = []
        passthru_options = []
        for a in argv:
            orig_a = a
            if not a.startswith("--"):
                posargs.append(a)
                continue
            a = a[2:]
            i = a.find("=")
            op = "="
            if i == -1:
                if a.startswith("no-"):
                    k = a[3:]
                    if k == "canonical-order":
                        # reorderTables=None is faster than False (the latter
                        # still reorders to "keep" the original table order)
                        v = None
                    else:
                        v = False
                else:
                    k = a
                    v = True
                if k.endswith("?"):
                    k = k[:-1]
                    v = "?"
            else:
                k = a[:i]
                if k[-1] in "-+":
                    op = k[-1] + "="  # Op is '-=' or '+=' now.
                    k = k[:-1]
                v = a[i + 1 :]
            ok = k
            k = k.replace("-", "_")
            if not hasattr(self, k):
                if ignore_unknown is True or ok in ignore_unknown:
                    passthru_options.append(orig_a)
                    continue
                else:
                    raise self.UnknownOptionError("Unknown option '%s'" % a)

            ov = getattr(self, k)
            if v == "?":
                print("Current setting for '%s' is: %s" % (ok, ov))
                continue
            if isinstance(ov, bool):
                v = bool(v)
            elif isinstance(ov, int):
                v = int(v)
            elif isinstance(ov, str):
                v = str(v)  # redundant
            elif isinstance(ov, list):
                if isinstance(v, bool):
                    raise self.OptionError(
                        "Option '%s' requires values to be specified using '='" % a
                    )
                vv = v.replace(",", " ").split()
                if vv == [""]:
                    vv = []
                vv = [int(x, 0) if len(x) and x[0] in "0123456789" else x for x in vv]
                if op == "=":
                    v = vv
                elif op == "+=":
                    v = ov
                    v.extend(vv)
                elif op == "-=":
                    v = ov
                    for x in vv:
                        if x in v:
                            v.remove(x)
                else:
                    assert False

            setattr(self, k, v)

        return posargs + passthru_options


class Subsetter(object):
    class SubsettingError(Exception):
        pass

    class MissingGlyphsSubsettingError(SubsettingError):
        pass

    class MissingUnicodesSubsettingError(SubsettingError):
        pass

    def __init__(self, options=None):
        if not options:
            options = Options()

        self.options = options
        self.unicodes_requested = set()
        self.glyph_names_requested = set()
        self.glyph_ids_requested = set()

    def populate(self, glyphs=[], gids=[], unicodes=[], text=""):
        self.unicodes_requested.update(unicodes)
        if isinstance(text, bytes):
            text = text.decode("utf_8")
        text_utf32 = text.encode("utf-32-be")
        nchars = len(text_utf32) // 4
        for u in struct.unpack(">%dL" % nchars, text_utf32):
            self.unicodes_requested.add(u)
        self.glyph_names_requested.update(glyphs)
        self.glyph_ids_requested.update(gids)

    def _prune_pre_subset(self, font):
        for tag in self._sort_tables(font):
            if (
                tag.strip() in self.options.drop_tables
                or (
                    tag.strip() in self.options.hinting_tables
                    and not self.options.hinting
                )
                or (tag == "kern" and (not self.options.legacy_kern and "GPOS" in font))
            ):
                log.info("%s dropped", tag)
                del font[tag]
                continue

            clazz = ttLib.getTableClass(tag)

            if hasattr(clazz, "prune_pre_subset"):
                with timer("load '%s'" % tag):
                    table = font[tag]
                with timer("prune '%s'" % tag):
                    retain = table.prune_pre_subset(font, self.options)
                if not retain:
                    log.info("%s pruned to empty; dropped", tag)
                    del font[tag]
                    continue
                else:
                    log.info("%s pruned", tag)

    def _closure_glyphs(self, font):
        realGlyphs = set(font.getGlyphOrder())
        self.orig_glyph_order = glyph_order = font.getGlyphOrder()

        self.glyphs_requested = set()
        self.glyphs_requested.update(self.glyph_names_requested)
        self.glyphs_requested.update(
            glyph_order[i] for i in self.glyph_ids_requested if i < len(glyph_order)
        )

        self.glyphs_missing = set()
        self.glyphs_missing.update(self.glyphs_requested.difference(realGlyphs))
        self.glyphs_missing.update(
            i for i in self.glyph_ids_requested if i >= len(glyph_order)
        )
        if self.glyphs_missing:
            log.info("Missing requested glyphs: %s", self.glyphs_missing)
            if not self.options.ignore_missing_glyphs:
                raise self.MissingGlyphsSubsettingError(self.glyphs_missing)

        self.glyphs = self.glyphs_requested.copy()

        self.unicodes_missing = set()
        if "cmap" in font:
            with timer("close glyph list over 'cmap'"):
                font["cmap"].closure_glyphs(self)
                self.glyphs.intersection_update(realGlyphs)
        self.glyphs_cmaped = frozenset(self.glyphs)
        if self.unicodes_missing:
            missing = ["U+%04X" % u for u in self.unicodes_missing]
            log.info("Missing glyphs for requested Unicodes: %s", missing)
            if not self.options.ignore_missing_unicodes:
                raise self.MissingUnicodesSubsettingError(missing)
            del missing

        if self.options.notdef_glyph:
            if "glyf" in font:
                self.glyphs.add(font.getGlyphName(0))
                log.info("Added gid0 to subset")
            else:
                self.glyphs.add(".notdef")
                log.info("Added .notdef to subset")
        if self.options.recommended_glyphs:
            if "glyf" in font:
                for i in range(min(4, len(font.getGlyphOrder()))):
                    self.glyphs.add(font.getGlyphName(i))
                log.info("Added first four glyphs to subset")

        if "MATH" in font:
            with timer("close glyph list over 'MATH'"):
                log.info(
                    "Closing glyph list over 'MATH': %d glyphs before", len(self.glyphs)
                )
                log.glyphs(self.glyphs, font=font)
                font["MATH"].closure_glyphs(self)
                self.glyphs.intersection_update(realGlyphs)
                log.info(
                    "Closed glyph list over 'MATH': %d glyphs after", len(self.glyphs)
                )
                log.glyphs(self.glyphs, font=font)
        self.glyphs_mathed = frozenset(self.glyphs)

        if self.options.layout_closure and "GSUB" in font:
            with timer("close glyph list over 'GSUB'"):
                log.info(
                    "Closing glyph list over 'GSUB': %d glyphs before", len(self.glyphs)
                )
                log.glyphs(self.glyphs, font=font)
                font["GSUB"].closure_glyphs(self)
                self.glyphs.intersection_update(realGlyphs)
                log.info(
                    "Closed glyph list over 'GSUB': %d glyphs after", len(self.glyphs)
                )
                log.glyphs(self.glyphs, font=font)
        self.glyphs_gsubed = frozenset(self.glyphs)

        for table in ("COLR", "bsln"):
            if table in font:
                with timer("close glyph list over '%s'" % table):
                    log.info(
                        "Closing glyph list over '%s': %d glyphs before",
                        table,
                        len(self.glyphs),
                    )
                    log.glyphs(self.glyphs, font=font)
                    font[table].closure_glyphs(self)
                    self.glyphs.intersection_update(realGlyphs)
                    log.info(
                        "Closed glyph list over '%s': %d glyphs after",
                        table,
                        len(self.glyphs),
                    )
                    log.glyphs(self.glyphs, font=font)
            setattr(self, f"glyphs_{table.lower()}ed", frozenset(self.glyphs))

        if "VARC" in font:
            with timer("close glyph list over 'VARC'"):
                log.info(
                    "Closing glyph list over 'VARC': %d glyphs before", len(self.glyphs)
                )
                log.glyphs(self.glyphs, font=font)
                font["VARC"].closure_glyphs(self)
                self.glyphs.intersection_update(realGlyphs)
                log.info(
                    "Closed glyph list over 'VARC': %d glyphs after", len(self.glyphs)
                )
                log.glyphs(self.glyphs, font=font)
        self.glyphs_glyfed = frozenset(self.glyphs)

        if "glyf" in font:
            with timer("close glyph list over 'glyf'"):
                log.info(
                    "Closing glyph list over 'glyf': %d glyphs before", len(self.glyphs)
                )
                log.glyphs(self.glyphs, font=font)
                font["glyf"].closure_glyphs(self)
                self.glyphs.intersection_update(realGlyphs)
                log.info(
                    "Closed glyph list over 'glyf': %d glyphs after", len(self.glyphs)
                )
                log.glyphs(self.glyphs, font=font)
        self.glyphs_glyfed = frozenset(self.glyphs)

        if "CFF " in font:
            with timer("close glyph list over 'CFF '"):
                log.info(
                    "Closing glyph list over 'CFF ': %d glyphs before", len(self.glyphs)
                )
                log.glyphs(self.glyphs, font=font)
                font["CFF "].closure_glyphs(self)
                self.glyphs.intersection_update(realGlyphs)
                log.info(
                    "Closed glyph list over 'CFF ': %d glyphs after", len(self.glyphs)
                )
                log.glyphs(self.glyphs, font=font)
        self.glyphs_cffed = frozenset(self.glyphs)

        self.glyphs_retained = frozenset(self.glyphs)

        order = font.getReverseGlyphMap()
        self.reverseOrigGlyphMap = {g: order[g] for g in self.glyphs_retained}

        self.last_retained_order = max(self.reverseOrigGlyphMap.values())
        self.last_retained_glyph = font.getGlyphOrder()[self.last_retained_order]

        self.glyphs_emptied = frozenset()
        if self.options.retain_gids:
            self.glyphs_emptied = {
                g
                for g in realGlyphs - self.glyphs_retained
                if order[g] <= self.last_retained_order
            }

        self.reverseEmptiedGlyphMap = {g: order[g] for g in self.glyphs_emptied}

        if not self.options.retain_gids:
            new_glyph_order = [g for g in glyph_order if g in self.glyphs_retained]
        else:
            new_glyph_order = [
                g for g in glyph_order if font.getGlyphID(g) <= self.last_retained_order
            ]
        # We'll call font.setGlyphOrder() at the end of _subset_glyphs when all
        # tables have been subsetted. Below, we use the new glyph order to get
        # a map from old to new glyph indices, which can be useful when
        # subsetting individual tables (e.g. SVG) that refer to GIDs.
        self.new_glyph_order = new_glyph_order
        self.glyph_index_map = {
            order[new_glyph_order[i]]: i for i in range(len(new_glyph_order))
        }

        log.info("Retaining %d glyphs", len(self.glyphs_retained))

        del self.glyphs

    def _subset_glyphs(self, font):
        self.used_mark_sets = []
        for tag in self._sort_tables(font):
            clazz = ttLib.getTableClass(tag)

            if tag.strip() in self.options.no_subset_tables:
                log.info("%s subsetting not needed", tag)
            elif hasattr(clazz, "subset_glyphs"):
                with timer("subset '%s'" % tag):
                    table = font[tag]
                    self.glyphs = self.glyphs_retained
                    retain = table.subset_glyphs(self)
                    del self.glyphs
                if not retain:
                    log.info("%s subsetted to empty; dropped", tag)
                    del font[tag]
                else:
                    log.info("%s subsetted", tag)
            elif self.options.passthrough_tables:
                log.info("%s NOT subset; don't know how to subset", tag)
            else:
                log.warning("%s NOT subset; don't know how to subset; dropped", tag)
                del font[tag]

        with timer("subset GlyphOrder"):
            font.setGlyphOrder(self.new_glyph_order)

    def _prune_post_subset(self, font):
        tableTags = font.keys()
        # Prune the name table last because when we're pruning the name table,
        # we visit each table in the font to see what name table records are
        # still in use.
        if "name" in tableTags:
            tableTags.remove("name")
            tableTags.append("name")
        for tag in tableTags:
            if tag == "GlyphOrder":
                continue
            if tag == "OS/2":
                if self.options.prune_unicode_ranges:
                    old_uniranges = font[tag].getUnicodeRanges()
                    new_uniranges = font[tag].recalcUnicodeRanges(font, pruneOnly=True)
                    if old_uniranges != new_uniranges:
                        log.info(
                            "%s Unicode ranges pruned: %s", tag, sorted(new_uniranges)
                        )
                if self.options.prune_codepage_ranges and font[tag].version >= 1:
                    # codepage range fields were added with OS/2 format 1
                    # https://learn.microsoft.com/en-us/typography/opentype/spec/os2#version-1
                    old_codepages = font[tag].getCodePageRanges()
                    new_codepages = font[tag].recalcCodePageRanges(font, pruneOnly=True)
                    if old_codepages != new_codepages:
                        log.info(
                            "%s CodePage ranges pruned: %s",
                            tag,
                            sorted(new_codepages),
                        )
                if self.options.recalc_average_width:
                    old_avg_width = font[tag].xAvgCharWidth
                    new_avg_width = font[tag].recalcAvgCharWidth(font)
                    if old_avg_width != new_avg_width:
                        log.info("%s xAvgCharWidth updated: %d", tag, new_avg_width)
                if self.options.recalc_max_context:
                    max_context = maxCtxFont(font)
                    if max_context != font[tag].usMaxContext:
                        font[tag].usMaxContext = max_context
                        log.info("%s usMaxContext updated: %d", tag, max_context)
            clazz = ttLib.getTableClass(tag)
            if hasattr(clazz, "prune_post_subset"):
                with timer("prune '%s'" % tag):
                    table = font[tag]
                    retain = table.prune_post_subset(font, self.options)
                if not retain:
                    log.info("%s pruned to empty; dropped", tag)
                    del font[tag]
                else:
                    log.info("%s pruned", tag)

    def _sort_tables(self, font):
        tagOrder = ["GDEF", "GPOS", "GSUB", "fvar", "avar", "gvar", "name", "glyf"]
        tagOrder = {t: i + 1 for i, t in enumerate(tagOrder)}
        tags = sorted(font.keys(), key=lambda tag: tagOrder.get(tag, 0))
        return [t for t in tags if t != "GlyphOrder"]

    def subset(self, font):
        self._prune_pre_subset(font)
        self._closure_glyphs(font)
        self._subset_glyphs(font)
        self._prune_post_subset(font)


@timer("load font")
def load_font(fontFile, options, checkChecksums=0, dontLoadGlyphNames=False, lazy=True):
    font = ttLib.TTFont(
        fontFile,
        checkChecksums=checkChecksums,
        recalcBBoxes=options.recalc_bounds,
        recalcTimestamp=options.recalc_timestamp,
        lazy=lazy,
        fontNumber=options.font_number,
    )

    # Hack:
    #
    # If we don't need glyph names, change 'post' class to not try to
    # load them.	It avoid lots of headache with broken fonts as well
    # as loading time.
    #
    # Ideally ttLib should provide a way to ask it to skip loading
    # glyph names.	But it currently doesn't provide such a thing.
    #
    if dontLoadGlyphNames:
        post = ttLib.getTableClass("post")
        saved = post.decode_format_2_0
        post.decode_format_2_0 = post.decode_format_3_0
        f = font["post"]
        if f.formatType == 2.0:
            f.formatType = 3.0
        post.decode_format_2_0 = saved

    return font


@timer("compile and save font")
def save_font(font, outfile, options):
    if options.with_zopfli and options.flavor == "woff":
        from fontTools.ttLib import sfnt

        sfnt.USE_ZOPFLI = True
    font.flavor = options.flavor
    font.cfg[USE_HARFBUZZ_REPACKER] = options.harfbuzz_repacker
    font.save(outfile, reorderTables=options.canonical_order)


def parse_unicodes(s):
    import re

    s = re.sub(r"0[xX]", " ", s)
    s = re.sub(r"[<+>,;&#\\xXuU\n	]", " ", s)
    l = []
    for item in s.split():
        fields = item.split("-")
        if len(fields) == 1:
            l.append(int(item, 16))
        else:
            start, end = fields
            l.extend(range(int(start, 16), int(end, 16) + 1))
    return l


def parse_gids(s):
    l = []
    for item in s.replace(",", " ").split():
        fields = item.split("-")
        if len(fields) == 1:
            l.append(int(fields[0]))
        else:
            l.extend(range(int(fields[0]), int(fields[1]) + 1))
    return l


def parse_glyphs(s):
    return s.replace(",", " ").split()


def usage():
    print("usage:", __usage__, file=sys.stderr)
    print("Try fonttools subset --help for more information.\n", file=sys.stderr)


@timer("make one with everything (TOTAL TIME)")
def main(args=None):
    """OpenType font subsetter and optimizer"""
    from os.path import splitext
    from fontTools import configLogger

    if args is None:
        args = sys.argv[1:]

    if "--help" in args:
        print(__doc__)
        return 0

    options = Options()
    try:
        args = options.parse_opts(
            args,
            ignore_unknown=[
                "gids",
                "gids-file",
                "glyphs",
                "glyphs-file",
                "text",
                "text-file",
                "unicodes",
                "unicodes-file",
                "output-file",
            ],
        )
    except options.OptionError as e:
        usage()
        print("ERROR:", e, file=sys.stderr)
        return 2

    if len(args) < 2:
        usage()
        return 1

    configLogger(level=logging.INFO if options.verbose else logging.WARNING)
    if options.timing:
        timer.logger.setLevel(logging.DEBUG)
    else:
        timer.logger.disabled = True

    fontfile = args[0]
    args = args[1:]

    subsetter = Subsetter(options=options)
    outfile = None
    glyphs = []
    gids = []
    unicodes = []
    wildcard_glyphs = False
    wildcard_unicodes = False
    text = ""
    for g in args:
        if g == "*":
            wildcard_glyphs = True
            continue
        if g.startswith("--output-file="):
            outfile = g[14:]
            continue
        if g.startswith("--text="):
            text += g[7:]
            continue
        if g.startswith("--text-file="):
            with open(g[12:], encoding="utf-8-sig") as f:
                text += f.read().replace("\n", "")
            continue
        if g.startswith("--unicodes="):
            if g[11:] == "*":
                wildcard_unicodes = True
            else:
                unicodes.extend(parse_unicodes(g[11:]))
            continue
        if g.startswith("--unicodes-file="):
            with open(g[16:]) as f:
                for line in f.readlines():
                    unicodes.extend(parse_unicodes(line.split("#")[0]))
            continue
        if g.startswith("--gids="):
            gids.extend(parse_gids(g[7:]))
            continue
        if g.startswith("--gids-file="):
            with open(g[12:]) as f:
                for line in f.readlines():
                    gids.extend(parse_gids(line.split("#")[0]))
            continue
        if g.startswith("--glyphs="):
            if g[9:] == "*":
                wildcard_glyphs = True
            else:
                glyphs.extend(parse_glyphs(g[9:]))
            continue
        if g.startswith("--glyphs-file="):
            with open(g[14:]) as f:
                for line in f.readlines():
                    glyphs.extend(parse_glyphs(line.split("#")[0]))
            continue
        glyphs.append(g)

    dontLoadGlyphNames = not options.glyph_names and not glyphs
    lazy = options.lazy
    font = load_font(
        fontfile, options, dontLoadGlyphNames=dontLoadGlyphNames, lazy=lazy
    )

    if outfile is None:
        ext = "." + options.flavor.lower() if options.flavor is not None else None
        outfile = makeOutputFileName(
            fontfile, extension=ext, overWrite=True, suffix=".subset"
        )

    with timer("compile glyph list"):
        if wildcard_glyphs:
            glyphs.extend(font.getGlyphOrder())
        if wildcard_unicodes:
            for t in font["cmap"].tables:
                if t.isUnicode():
                    unicodes.extend(t.cmap.keys())
                    if t.format == 14:
                        unicodes.extend(t.uvsDict.keys())
        assert "" not in glyphs

    log.info("Text: '%s'" % text)
    log.info("Unicodes: %s", unicodes)
    log.info("Glyphs: %s", glyphs)
    log.info("Gids: %s", gids)

    subsetter.populate(glyphs=glyphs, gids=gids, unicodes=unicodes, text=text)
    subsetter.subset(font)

    save_font(font, outfile, options)

    if options.verbose:
        import os

        log.info("Input font:% 7d bytes: %s" % (os.path.getsize(fontfile), fontfile))
        log.info("Subset font:% 7d bytes: %s" % (os.path.getsize(outfile), outfile))

    if options.xml:
        font.saveXML(sys.stdout)

    font.close()


__all__ = [
    "Options",
    "Subsetter",
    "load_font",
    "save_font",
    "parse_gids",
    "parse_glyphs",
    "parse_unicodes",
    "main",
]
