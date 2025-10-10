"""Reorder glyphs in a font."""

__author__ = "Rod Sheeter"

# See https://docs.google.com/document/d/1h9O-C_ndods87uY0QeIIcgAMiX2gDTpvO_IhMJsKAqs/
# for details.


from fontTools import ttLib
from fontTools.ttLib.tables import otBase
from fontTools.ttLib.tables import otTables as ot
from abc import ABC, abstractmethod
from dataclasses import dataclass
from collections import deque
from typing import (
    Optional,
    Any,
    Callable,
    Deque,
    Iterable,
    List,
    Tuple,
)


_COVERAGE_ATTR = "Coverage"  # tables that have one coverage use this name


def _sort_by_gid(
    get_glyph_id: Callable[[str], int],
    glyphs: List[str],
    parallel_list: Optional[List[Any]],
):
    if parallel_list:
        reordered = sorted(
            ((g, e) for g, e in zip(glyphs, parallel_list)),
            key=lambda t: get_glyph_id(t[0]),
        )
        sorted_glyphs, sorted_parallel_list = map(list, zip(*reordered))
        parallel_list[:] = sorted_parallel_list
    else:
        sorted_glyphs = sorted(glyphs, key=get_glyph_id)

    glyphs[:] = sorted_glyphs


def _get_dotted_attr(value: Any, dotted_attr: str) -> Any:
    attr_names = dotted_attr.split(".")
    assert attr_names

    while attr_names:
        attr_name = attr_names.pop(0)
        value = getattr(value, attr_name)
    return value


class ReorderRule(ABC):
    """A rule to reorder something in a font to match the fonts glyph order."""

    @abstractmethod
    def apply(self, font: ttLib.TTFont, value: otBase.BaseTable) -> None: ...


@dataclass(frozen=True)
class ReorderCoverage(ReorderRule):
    """Reorder a Coverage table, and optionally a list that is sorted parallel to it."""

    # A list that is parallel to Coverage
    parallel_list_attr: Optional[str] = None
    coverage_attr: str = _COVERAGE_ATTR

    def apply(self, font: ttLib.TTFont, value: otBase.BaseTable) -> None:
        coverage = _get_dotted_attr(value, self.coverage_attr)

        if type(coverage) is not list:
            # Normal path, process one coverage that might have a parallel list
            parallel_list = None
            if self.parallel_list_attr:
                parallel_list = _get_dotted_attr(value, self.parallel_list_attr)
                assert (
                    type(parallel_list) is list
                ), f"{self.parallel_list_attr} should be a list"
                assert len(parallel_list) == len(coverage.glyphs), "Nothing makes sense"

            _sort_by_gid(font.getGlyphID, coverage.glyphs, parallel_list)

        else:
            # A few tables have a list of coverage. No parallel list can exist.
            assert (
                not self.parallel_list_attr
            ), f"Can't have multiple coverage AND a parallel list; {self}"
            for coverage_entry in coverage:
                _sort_by_gid(font.getGlyphID, coverage_entry.glyphs, None)


@dataclass(frozen=True)
class ReorderList(ReorderRule):
    """Reorder the items within a list to match the updated glyph order.

    Useful when a list ordered by coverage itself contains something ordered by a gid.
    For example, the PairSet table of https://docs.microsoft.com/en-us/typography/opentype/spec/gpos#lookup-type-2-pair-adjustment-positioning-subtable.
    """

    list_attr: str
    key: str

    def apply(self, font: ttLib.TTFont, value: otBase.BaseTable) -> None:
        lst = _get_dotted_attr(value, self.list_attr)
        assert isinstance(lst, list), f"{self.list_attr} should be a list"
        lst.sort(key=lambda v: font.getGlyphID(getattr(v, self.key)))


# (Type, Optional Format) => List[ReorderRule]
# Encodes the relationships Cosimo identified
_REORDER_RULES = {
    # GPOS
    (ot.SinglePos, 1): [ReorderCoverage()],
    (ot.SinglePos, 2): [ReorderCoverage(parallel_list_attr="Value")],
    (ot.PairPos, 1): [ReorderCoverage(parallel_list_attr="PairSet")],
    (ot.PairSet, None): [ReorderList("PairValueRecord", key="SecondGlyph")],
    (ot.PairPos, 2): [ReorderCoverage()],
    (ot.CursivePos, 1): [ReorderCoverage(parallel_list_attr="EntryExitRecord")],
    (ot.MarkBasePos, 1): [
        ReorderCoverage(
            coverage_attr="MarkCoverage", parallel_list_attr="MarkArray.MarkRecord"
        ),
        ReorderCoverage(
            coverage_attr="BaseCoverage", parallel_list_attr="BaseArray.BaseRecord"
        ),
    ],
    (ot.MarkLigPos, 1): [
        ReorderCoverage(
            coverage_attr="MarkCoverage", parallel_list_attr="MarkArray.MarkRecord"
        ),
        ReorderCoverage(
            coverage_attr="LigatureCoverage",
            parallel_list_attr="LigatureArray.LigatureAttach",
        ),
    ],
    (ot.MarkMarkPos, 1): [
        ReorderCoverage(
            coverage_attr="Mark1Coverage", parallel_list_attr="Mark1Array.MarkRecord"
        ),
        ReorderCoverage(
            coverage_attr="Mark2Coverage", parallel_list_attr="Mark2Array.Mark2Record"
        ),
    ],
    (ot.ContextPos, 1): [ReorderCoverage(parallel_list_attr="PosRuleSet")],
    (ot.ContextPos, 2): [ReorderCoverage()],
    (ot.ContextPos, 3): [ReorderCoverage()],
    (ot.ChainContextPos, 1): [ReorderCoverage(parallel_list_attr="ChainPosRuleSet")],
    (ot.ChainContextPos, 2): [ReorderCoverage()],
    (ot.ChainContextPos, 3): [
        ReorderCoverage(coverage_attr="BacktrackCoverage"),
        ReorderCoverage(coverage_attr="InputCoverage"),
        ReorderCoverage(coverage_attr="LookAheadCoverage"),
    ],
    # GSUB
    (ot.ContextSubst, 1): [ReorderCoverage(parallel_list_attr="SubRuleSet")],
    (ot.ContextSubst, 2): [ReorderCoverage()],
    (ot.ContextSubst, 3): [ReorderCoverage()],
    (ot.ChainContextSubst, 1): [ReorderCoverage(parallel_list_attr="ChainSubRuleSet")],
    (ot.ChainContextSubst, 2): [ReorderCoverage()],
    (ot.ChainContextSubst, 3): [
        ReorderCoverage(coverage_attr="BacktrackCoverage"),
        ReorderCoverage(coverage_attr="InputCoverage"),
        ReorderCoverage(coverage_attr="LookAheadCoverage"),
    ],
    (ot.ReverseChainSingleSubst, 1): [
        ReorderCoverage(parallel_list_attr="Substitute"),
        ReorderCoverage(coverage_attr="BacktrackCoverage"),
        ReorderCoverage(coverage_attr="LookAheadCoverage"),
    ],
    # GDEF
    (ot.AttachList, None): [ReorderCoverage(parallel_list_attr="AttachPoint")],
    (ot.LigCaretList, None): [ReorderCoverage(parallel_list_attr="LigGlyph")],
    (ot.MarkGlyphSetsDef, None): [ReorderCoverage()],
    # MATH
    (ot.MathGlyphInfo, None): [ReorderCoverage(coverage_attr="ExtendedShapeCoverage")],
    (ot.MathItalicsCorrectionInfo, None): [
        ReorderCoverage(parallel_list_attr="ItalicsCorrection")
    ],
    (ot.MathTopAccentAttachment, None): [
        ReorderCoverage(
            coverage_attr="TopAccentCoverage", parallel_list_attr="TopAccentAttachment"
        )
    ],
    (ot.MathKernInfo, None): [
        ReorderCoverage(
            coverage_attr="MathKernCoverage", parallel_list_attr="MathKernInfoRecords"
        )
    ],
    (ot.MathVariants, None): [
        ReorderCoverage(
            coverage_attr="VertGlyphCoverage",
            parallel_list_attr="VertGlyphConstruction",
        ),
        ReorderCoverage(
            coverage_attr="HorizGlyphCoverage",
            parallel_list_attr="HorizGlyphConstruction",
        ),
    ],
}


# TODO Port to otTraverse

SubTablePath = Tuple[otBase.BaseTable.SubTableEntry, ...]


def _bfs_base_table(
    root: otBase.BaseTable, root_accessor: str
) -> Iterable[SubTablePath]:
    yield from _traverse_ot_data(
        root, root_accessor, lambda frontier, new: frontier.extend(new)
    )


# Given f(current frontier, new entries) add new entries to frontier
AddToFrontierFn = Callable[[Deque[SubTablePath], List[SubTablePath]], None]


def _traverse_ot_data(
    root: otBase.BaseTable, root_accessor: str, add_to_frontier_fn: AddToFrontierFn
) -> Iterable[SubTablePath]:
    # no visited because general otData is forward-offset only and thus cannot cycle

    frontier: Deque[SubTablePath] = deque()
    frontier.append((otBase.BaseTable.SubTableEntry(root_accessor, root),))
    while frontier:
        # path is (value, attr_name) tuples. attr_name is attr of parent to get value
        path = frontier.popleft()
        current = path[-1].value

        yield path

        new_entries = []
        for subtable_entry in current.iterSubTables():
            new_entries.append(path + (subtable_entry,))

        add_to_frontier_fn(frontier, new_entries)


def reorderGlyphs(font: ttLib.TTFont, new_glyph_order: List[str]):
    old_glyph_order = font.getGlyphOrder()
    if len(new_glyph_order) != len(old_glyph_order):
        raise ValueError(
            f"New glyph order contains {len(new_glyph_order)} glyphs, "
            f"but font has {len(old_glyph_order)} glyphs"
        )

    if set(old_glyph_order) != set(new_glyph_order):
        raise ValueError(
            "New glyph order does not contain the same set of glyphs as the font:\n"
            f"* only in new: {set(new_glyph_order) - set(old_glyph_order)}\n"
            f"* only in old: {set(old_glyph_order) - set(new_glyph_order)}"
        )

    # Changing the order of glyphs in a TTFont requires that all tables that use
    # glyph indexes have been fully.
    # Cf. https://github.com/fonttools/fonttools/issues/2060
    font.ensureDecompiled()
    not_loaded = sorted(t for t in font.keys() if not font.isLoaded(t))
    if not_loaded:
        raise ValueError(f"Everything should be loaded, following aren't: {not_loaded}")

    font.setGlyphOrder(new_glyph_order)

    coverage_containers = {"GDEF", "GPOS", "GSUB", "MATH"}
    for tag in coverage_containers:
        if tag in font.keys():
            for path in _bfs_base_table(font[tag].table, f'font["{tag}"]'):
                value = path[-1].value
                reorder_key = (type(value), getattr(value, "Format", None))
                for reorder in _REORDER_RULES.get(reorder_key, []):
                    reorder.apply(font, value)

    for tag in ["CFF ", "CFF2"]:
        if tag in font:
            cff_table = font[tag]
            charstrings = cff_table.cff.topDictIndex[0].CharStrings.charStrings
            cff_table.cff.topDictIndex[0].charset = new_glyph_order
            cff_table.cff.topDictIndex[0].CharStrings.charStrings = {
                k: charstrings.get(k) for k in new_glyph_order
            }
