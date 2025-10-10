import logging
import os
from collections import defaultdict, namedtuple
from dataclasses import dataclass
from functools import cached_property, reduce
from itertools import chain
from math import log2
from typing import DefaultDict, Dict, Iterable, List, Sequence, Tuple

from fontTools.config import OPTIONS
from fontTools.misc.intTools import bit_count, bit_indices
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otBase, otTables

log = logging.getLogger(__name__)

COMPRESSION_LEVEL = OPTIONS[f"{__name__}:COMPRESSION_LEVEL"]

# Kept because ufo2ft depends on it, to be removed once ufo2ft uses the config instead
# https://github.com/fonttools/fonttools/issues/2592
GPOS_COMPACT_MODE_ENV_KEY = "FONTTOOLS_GPOS_COMPACT_MODE"
GPOS_COMPACT_MODE_DEFAULT = str(COMPRESSION_LEVEL.default)


def _compression_level_from_env() -> int:
    env_level = GPOS_COMPACT_MODE_DEFAULT
    if GPOS_COMPACT_MODE_ENV_KEY in os.environ:
        import warnings

        warnings.warn(
            f"'{GPOS_COMPACT_MODE_ENV_KEY}' environment variable is deprecated. "
            "Please set the 'fontTools.otlLib.optimize.gpos:COMPRESSION_LEVEL' option "
            "in TTFont.cfg.",
            DeprecationWarning,
        )

        env_level = os.environ[GPOS_COMPACT_MODE_ENV_KEY]
    if len(env_level) == 1 and env_level in "0123456789":
        return int(env_level)
    raise ValueError(f"Bad {GPOS_COMPACT_MODE_ENV_KEY}={env_level}")


def compact(font: TTFont, level: int) -> TTFont:
    # Ideal plan:
    #  1. Find lookups of Lookup Type 2: Pair Adjustment Positioning Subtable
    #     https://docs.microsoft.com/en-us/typography/opentype/spec/gpos#lookup-type-2-pair-adjustment-positioning-subtable
    #  2. Extract glyph-glyph kerning and class-kerning from all present subtables
    #  3. Regroup into different subtable arrangements
    #  4. Put back into the lookup
    #
    # Actual implementation:
    #  2. Only class kerning is optimized currently
    #  3. If the input kerning is already in several subtables, the subtables
    #     are not grouped together first; instead each subtable is treated
    #     independently, so currently this step is:
    #     Split existing subtables into more smaller subtables
    gpos = font.get("GPOS")

    # If the font does not contain a GPOS table, there is nothing to do.
    if gpos is None:
        return font

    for lookup in gpos.table.LookupList.Lookup:
        if lookup.LookupType == 2:
            compact_lookup(font, level, lookup)
        elif lookup.LookupType == 9 and lookup.SubTable[0].ExtensionLookupType == 2:
            compact_ext_lookup(font, level, lookup)

    return font


def compact_lookup(font: TTFont, level: int, lookup: otTables.Lookup) -> None:
    new_subtables = compact_pair_pos(font, level, lookup.SubTable)
    lookup.SubTable = new_subtables
    lookup.SubTableCount = len(new_subtables)


def compact_ext_lookup(font: TTFont, level: int, lookup: otTables.Lookup) -> None:
    new_subtables = compact_pair_pos(
        font, level, [ext_subtable.ExtSubTable for ext_subtable in lookup.SubTable]
    )
    new_ext_subtables = []
    for subtable in new_subtables:
        ext_subtable = otTables.ExtensionPos()
        ext_subtable.Format = 1
        ext_subtable.ExtSubTable = subtable
        new_ext_subtables.append(ext_subtable)
    lookup.SubTable = new_ext_subtables
    lookup.SubTableCount = len(new_ext_subtables)


def compact_pair_pos(
    font: TTFont, level: int, subtables: Sequence[otTables.PairPos]
) -> Sequence[otTables.PairPos]:
    new_subtables = []
    for subtable in subtables:
        if subtable.Format == 1:
            # Not doing anything to Format 1 (yet?)
            new_subtables.append(subtable)
        elif subtable.Format == 2:
            new_subtables.extend(compact_class_pairs(font, level, subtable))
    return new_subtables


def compact_class_pairs(
    font: TTFont, level: int, subtable: otTables.PairPos
) -> List[otTables.PairPos]:
    from fontTools.otlLib.builder import buildPairPosClassesSubtable

    subtables = []
    classes1: DefaultDict[int, List[str]] = defaultdict(list)
    for g in subtable.Coverage.glyphs:
        classes1[subtable.ClassDef1.classDefs.get(g, 0)].append(g)
    classes2: DefaultDict[int, List[str]] = defaultdict(list)
    for g, i in subtable.ClassDef2.classDefs.items():
        classes2[i].append(g)
    all_pairs = {}
    for i, class1 in enumerate(subtable.Class1Record):
        for j, class2 in enumerate(class1.Class2Record):
            if is_really_zero(class2):
                continue
            all_pairs[(tuple(sorted(classes1[i])), tuple(sorted(classes2[j])))] = (
                getattr(class2, "Value1", None),
                getattr(class2, "Value2", None),
            )
    grouped_pairs = cluster_pairs_by_class2_coverage_custom_cost(font, all_pairs, level)
    for pairs in grouped_pairs:
        subtables.append(buildPairPosClassesSubtable(pairs, font.getReverseGlyphMap()))
    return subtables


def is_really_zero(class2: otTables.Class2Record) -> bool:
    v1 = getattr(class2, "Value1", None)
    v2 = getattr(class2, "Value2", None)
    return (v1 is None or v1.getEffectiveFormat() == 0) and (
        v2 is None or v2.getEffectiveFormat() == 0
    )


Pairs = Dict[
    Tuple[Tuple[str, ...], Tuple[str, ...]],
    Tuple[otBase.ValueRecord, otBase.ValueRecord],
]


# Adapted from https://github.com/fonttools/fonttools/blob/f64f0b42f2d1163b2d85194e0979def539f5dca3/Lib/fontTools/ttLib/tables/otTables.py#L935-L958
def _getClassRanges(glyphIDs: Iterable[int]):
    glyphIDs = sorted(glyphIDs)
    last = glyphIDs[0]
    ranges = [[last]]
    for glyphID in glyphIDs[1:]:
        if glyphID != last + 1:
            ranges[-1].append(last)
            ranges.append([glyphID])
        last = glyphID
    ranges[-1].append(last)
    return ranges, glyphIDs[0], glyphIDs[-1]


# Adapted from https://github.com/fonttools/fonttools/blob/f64f0b42f2d1163b2d85194e0979def539f5dca3/Lib/fontTools/ttLib/tables/otTables.py#L960-L989
def _classDef_bytes(
    class_data: List[Tuple[List[Tuple[int, int]], int, int]],
    class_ids: List[int],
    coverage=False,
):
    if not class_ids:
        return 0
    first_ranges, min_glyph_id, max_glyph_id = class_data[class_ids[0]]
    range_count = len(first_ranges)
    for i in class_ids[1:]:
        data = class_data[i]
        range_count += len(data[0])
        min_glyph_id = min(min_glyph_id, data[1])
        max_glyph_id = max(max_glyph_id, data[2])
    glyphCount = max_glyph_id - min_glyph_id + 1
    # https://docs.microsoft.com/en-us/typography/opentype/spec/chapter2#class-definition-table-format-1
    format1_bytes = 6 + glyphCount * 2
    # https://docs.microsoft.com/en-us/typography/opentype/spec/chapter2#class-definition-table-format-2
    format2_bytes = 4 + range_count * 6
    return min(format1_bytes, format2_bytes)


ClusteringContext = namedtuple(
    "ClusteringContext",
    [
        "lines",
        "all_class1",
        "all_class1_data",
        "all_class2_data",
        "valueFormat1_bytes",
        "valueFormat2_bytes",
    ],
)


@dataclass
class Cluster:
    ctx: ClusteringContext
    indices_bitmask: int

    @cached_property
    def indices(self):
        return bit_indices(self.indices_bitmask)

    @cached_property
    def column_indices(self):
        # Indices of columns that have a 1 in at least 1 line
        #   => binary OR all the lines
        bitmask = reduce(int.__or__, (self.ctx.lines[i] for i in self.indices))
        return bit_indices(bitmask)

    @property
    def width(self):
        # Add 1 because Class2=0 cannot be used but needs to be encoded.
        return len(self.column_indices) + 1

    @cached_property
    def cost(self):
        return (
            # 2 bytes to store the offset to this subtable in the Lookup table above
            2
            # Contents of the subtable
            # From: https://docs.microsoft.com/en-us/typography/opentype/spec/gpos#pair-adjustment-positioning-format-2-class-pair-adjustment
            # uint16	posFormat	Format identifier: format = 2
            + 2
            # Offset16	coverageOffset	Offset to Coverage table, from beginning of PairPos subtable.
            + 2
            + self.coverage_bytes
            # uint16	valueFormat1	ValueRecord definition — for the first glyph of the pair (may be zero).
            + 2
            # uint16	valueFormat2	ValueRecord definition — for the second glyph of the pair (may be zero).
            + 2
            # Offset16	classDef1Offset	Offset to ClassDef table, from beginning of PairPos subtable — for the first glyph of the pair.
            + 2
            + self.classDef1_bytes
            # Offset16	classDef2Offset	Offset to ClassDef table, from beginning of PairPos subtable — for the second glyph of the pair.
            + 2
            + self.classDef2_bytes
            # uint16	class1Count	Number of classes in classDef1 table — includes Class 0.
            + 2
            # uint16	class2Count	Number of classes in classDef2 table — includes Class 0.
            + 2
            # Class1Record	class1Records[class1Count]	Array of Class1 records, ordered by classes in classDef1.
            + (self.ctx.valueFormat1_bytes + self.ctx.valueFormat2_bytes)
            * len(self.indices)
            * self.width
        )

    @property
    def coverage_bytes(self):
        format1_bytes = (
            # From https://docs.microsoft.com/en-us/typography/opentype/spec/chapter2#coverage-format-1
            # uint16	coverageFormat	Format identifier — format = 1
            # uint16	glyphCount	Number of glyphs in the glyph array
            4
            # uint16	glyphArray[glyphCount]	Array of glyph IDs — in numerical order
            + sum(len(self.ctx.all_class1[i]) for i in self.indices) * 2
        )
        ranges = sorted(
            chain.from_iterable(self.ctx.all_class1_data[i][0] for i in self.indices)
        )
        merged_range_count = 0
        last = None
        for start, end in ranges:
            if last is not None and start != last + 1:
                merged_range_count += 1
            last = end
        format2_bytes = (
            # From https://docs.microsoft.com/en-us/typography/opentype/spec/chapter2#coverage-format-2
            # uint16	coverageFormat	Format identifier — format = 2
            # uint16	rangeCount	Number of RangeRecords
            4
            # RangeRecord	rangeRecords[rangeCount]	Array of glyph ranges — ordered by startGlyphID.
            # uint16	startGlyphID	First glyph ID in the range
            # uint16	endGlyphID	Last glyph ID in the range
            # uint16	startCoverageIndex	Coverage Index of first glyph ID in range
            + merged_range_count * 6
        )
        return min(format1_bytes, format2_bytes)

    @property
    def classDef1_bytes(self):
        # We can skip encoding one of the Class1 definitions, and use
        # Class1=0 to represent it instead, because Class1 is gated by the
        # Coverage definition. Use Class1=0 for the highest byte savings.
        # Going through all options takes too long, pick the biggest class
        # = what happens in otlLib.builder.ClassDefBuilder.classes()
        biggest_index = max(self.indices, key=lambda i: len(self.ctx.all_class1[i]))
        return _classDef_bytes(
            self.ctx.all_class1_data, [i for i in self.indices if i != biggest_index]
        )

    @property
    def classDef2_bytes(self):
        # All Class2 need to be encoded because we can't use Class2=0
        return _classDef_bytes(self.ctx.all_class2_data, self.column_indices)


def cluster_pairs_by_class2_coverage_custom_cost(
    font: TTFont,
    pairs: Pairs,
    compression: int = 5,
) -> List[Pairs]:
    if not pairs:
        # The subtable was actually empty?
        return [pairs]

    # Sorted for reproducibility/determinism
    all_class1 = sorted(set(pair[0] for pair in pairs))
    all_class2 = sorted(set(pair[1] for pair in pairs))

    # Use Python's big ints for binary vectors representing each line
    lines = [
        sum(
            1 << i if (class1, class2) in pairs else 0
            for i, class2 in enumerate(all_class2)
        )
        for class1 in all_class1
    ]

    # Map glyph names to ids and work with ints throughout for ClassDef formats
    name_to_id = font.getReverseGlyphMap()
    # Each entry in the arrays below is (range_count, min_glyph_id, max_glyph_id)
    all_class1_data = [
        _getClassRanges(name_to_id[name] for name in cls) for cls in all_class1
    ]
    all_class2_data = [
        _getClassRanges(name_to_id[name] for name in cls) for cls in all_class2
    ]

    format1 = 0
    format2 = 0
    for pair, value in pairs.items():
        format1 |= value[0].getEffectiveFormat() if value[0] else 0
        format2 |= value[1].getEffectiveFormat() if value[1] else 0
    valueFormat1_bytes = bit_count(format1) * 2
    valueFormat2_bytes = bit_count(format2) * 2

    ctx = ClusteringContext(
        lines,
        all_class1,
        all_class1_data,
        all_class2_data,
        valueFormat1_bytes,
        valueFormat2_bytes,
    )

    cluster_cache: Dict[int, Cluster] = {}

    def make_cluster(indices: int) -> Cluster:
        cluster = cluster_cache.get(indices, None)
        if cluster is not None:
            return cluster
        cluster = Cluster(ctx, indices)
        cluster_cache[indices] = cluster
        return cluster

    def merge(cluster: Cluster, other: Cluster) -> Cluster:
        return make_cluster(cluster.indices_bitmask | other.indices_bitmask)

    # Agglomerative clustering by hand, checking the cost gain of the new
    # cluster against the previously separate clusters
    # Start with 1 cluster per line
    # cluster = set of lines = new subtable
    clusters = [make_cluster(1 << i) for i in range(len(lines))]

    # Cost of 1 cluster with everything
    # `(1 << len) - 1` gives a bitmask full of 1's of length `len`
    cost_before_splitting = make_cluster((1 << len(lines)) - 1).cost
    log.debug(f"        len(clusters) = {len(clusters)}")

    while len(clusters) > 1:
        lowest_cost_change = None
        best_cluster_index = None
        best_other_index = None
        best_merged = None
        for i, cluster in enumerate(clusters):
            for j, other in enumerate(clusters[i + 1 :]):
                merged = merge(cluster, other)
                cost_change = merged.cost - cluster.cost - other.cost
                if lowest_cost_change is None or cost_change < lowest_cost_change:
                    lowest_cost_change = cost_change
                    best_cluster_index = i
                    best_other_index = i + 1 + j
                    best_merged = merged
        assert lowest_cost_change is not None
        assert best_cluster_index is not None
        assert best_other_index is not None
        assert best_merged is not None

        # If the best merge we found is still taking down the file size, then
        # there's no question: we must do it, because it's beneficial in both
        # ways (lower file size and lower number of subtables).  However, if the
        # best merge we found is not reducing file size anymore, then we need to
        # look at the other stop criteria = the compression factor.
        if lowest_cost_change > 0:
            # Stop critera: check whether we should keep merging.
            # Compute size reduction brought by splitting
            cost_after_splitting = sum(c.cost for c in clusters)
            # size_reduction so that after = before * (1 - size_reduction)
            # E.g. before = 1000, after = 800, 1 - 800/1000 = 0.2
            size_reduction = 1 - cost_after_splitting / cost_before_splitting

            # Force more merging by taking into account the compression number.
            # Target behaviour: compression number = 1 to 9, default 5 like gzip
            #   - 1 = accept to add 1 subtable to reduce size by 50%
            #   - 5 = accept to add 5 subtables to reduce size by 50%
            # See https://github.com/harfbuzz/packtab/blob/master/Lib/packTab/__init__.py#L690-L691
            # Given the size reduction we have achieved so far, compute how many
            # new subtables are acceptable.
            max_new_subtables = -log2(1 - size_reduction) * compression
            log.debug(
                f"            len(clusters) = {len(clusters):3d}    size_reduction={size_reduction:5.2f}    max_new_subtables={max_new_subtables}",
            )
            if compression == 9:
                # Override level 9 to mean: create any number of subtables
                max_new_subtables = len(clusters)

            # If we have managed to take the number of new subtables below the
            # threshold, then we can stop.
            if len(clusters) <= max_new_subtables + 1:
                break

        # No reason to stop yet, do the merge and move on to the next.
        del clusters[best_other_index]
        clusters[best_cluster_index] = best_merged

    # All clusters are final; turn bitmasks back into the "Pairs" format
    pairs_by_class1: Dict[Tuple[str, ...], Pairs] = defaultdict(dict)
    for pair, values in pairs.items():
        pairs_by_class1[pair[0]][pair] = values
    pairs_groups: List[Pairs] = []
    for cluster in clusters:
        pairs_group: Pairs = dict()
        for i in cluster.indices:
            class1 = all_class1[i]
            pairs_group.update(pairs_by_class1[class1])
        pairs_groups.append(pairs_group)
    return pairs_groups
