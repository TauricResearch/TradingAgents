from __future__ import annotations

import re
from functools import lru_cache
from itertools import chain, count
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple

try:
    from lxml import etree
except ImportError:
    # lxml is required for subsetting SVG, but we prefer to delay the import error
    # until subset_glyphs() is called (i.e. if font to subset has an 'SVG ' table)
    etree = None

from fontTools import ttLib
from fontTools.subset.util import _add_method
from fontTools.ttLib.tables.S_V_G_ import SVGDocument


__all__ = ["subset_glyphs"]


GID_RE = re.compile(r"^glyph(\d+)$")

NAMESPACES = {
    "svg": "http://www.w3.org/2000/svg",
    "xlink": "http://www.w3.org/1999/xlink",
}
XLINK_HREF = f'{{{NAMESPACES["xlink"]}}}href'


# TODO(antrotype): Replace with functools.cache once we are 3.9+
@lru_cache(maxsize=None)
def xpath(path):
    # compile XPath upfront, caching result to reuse on multiple elements
    return etree.XPath(path, namespaces=NAMESPACES)


def group_elements_by_id(tree: etree.Element) -> Dict[str, etree.Element]:
    # select all svg elements with 'id' attribute no matter where they are
    # including the root element itself:
    # https://github.com/fonttools/fonttools/issues/2548
    return {el.attrib["id"]: el for el in xpath("//svg:*[@id]")(tree)}


def parse_css_declarations(style_attr: str) -> Dict[str, str]:
    # https://developer.mozilla.org/en-US/docs/Web/SVG/Attribute/style
    # https://developer.mozilla.org/en-US/docs/Web/CSS/Syntax#css_declarations
    result = {}
    for declaration in style_attr.split(";"):
        if declaration.count(":") == 1:
            property_name, value = declaration.split(":")
            property_name = property_name.strip()
            result[property_name] = value.strip()
        elif declaration.strip():
            raise ValueError(f"Invalid CSS declaration syntax: {declaration}")
    return result


def iter_referenced_ids(tree: etree.Element) -> Iterator[str]:
    # Yield all the ids that can be reached via references from this element tree.
    # We currently support xlink:href (as used by <use> and gradient templates),
    # and local url(#...) links found in fill or clip-path attributes
    # TODO(anthrotype): Check we aren't missing other supported kinds of reference
    find_svg_elements_with_references = xpath(
        ".//svg:*[ "
        "starts-with(@xlink:href, '#') "
        "or starts-with(@fill, 'url(#') "
        "or starts-with(@clip-path, 'url(#') "
        "or contains(@style, ':url(#') "
        "]",
    )
    for el in chain([tree], find_svg_elements_with_references(tree)):
        ref_id = href_local_target(el)
        if ref_id is not None:
            yield ref_id

        attrs = el.attrib
        if "style" in attrs:
            attrs = {**dict(attrs), **parse_css_declarations(el.attrib["style"])}
        for attr in ("fill", "clip-path"):
            if attr in attrs:
                value = attrs[attr]
                if value.startswith("url(#") and value.endswith(")"):
                    ref_id = value[5:-1]
                    assert ref_id
                    yield ref_id


def closure_element_ids(
    elements: Dict[str, etree.Element], element_ids: Set[str]
) -> None:
    # Expand the initial subset of element ids to include ids that can be reached
    # via references from the initial set.
    unvisited = element_ids
    while unvisited:
        referenced: Set[str] = set()
        for el_id in unvisited:
            if el_id not in elements:
                # ignore dangling reference; not our job to validate svg
                continue
            referenced.update(iter_referenced_ids(elements[el_id]))
        referenced -= element_ids
        element_ids.update(referenced)
        unvisited = referenced


def subset_elements(el: etree.Element, retained_ids: Set[str]) -> bool:
    # Keep elements if their id is in the subset, or any of their children's id is.
    # Drop elements whose id is not in the subset, and either have no children,
    # or all their children are being dropped.
    if el.attrib.get("id") in retained_ids:
        # if id is in the set, don't recurse; keep whole subtree
        return True
    # recursively subset all the children; we use a list comprehension instead
    # of a parentheses-less generator expression because we don't want any() to
    # short-circuit, as our function has a side effect of dropping empty elements.
    if any([subset_elements(e, retained_ids) for e in el]):
        return True
    assert len(el) == 0
    parent = el.getparent()
    if parent is not None:
        parent.remove(el)
    return False


def remap_glyph_ids(
    svg: etree.Element, glyph_index_map: Dict[int, int]
) -> Dict[str, str]:
    # Given {old_gid: new_gid} map, rename all elements containing id="glyph{gid}"
    # special attributes
    elements = group_elements_by_id(svg)
    id_map = {}
    for el_id, el in elements.items():
        m = GID_RE.match(el_id)
        if not m:
            continue
        old_index = int(m.group(1))
        new_index = glyph_index_map.get(old_index)
        if new_index is not None:
            if old_index == new_index:
                continue
            new_id = f"glyph{new_index}"
        else:
            # If the old index is missing, the element correspond to a glyph that was
            # excluded from the font's subset.
            # We rename it to avoid clashes with the new GIDs or other element ids.
            new_id = f".{el_id}"
            n = count(1)
            while new_id in elements:
                new_id = f"{new_id}.{next(n)}"

        id_map[el_id] = new_id
        el.attrib["id"] = new_id

    return id_map


def href_local_target(el: etree.Element) -> Optional[str]:
    if XLINK_HREF in el.attrib:
        href = el.attrib[XLINK_HREF]
        if href.startswith("#") and len(href) > 1:
            return href[1:]  # drop the leading #
    return None


def update_glyph_href_links(svg: etree.Element, id_map: Dict[str, str]) -> None:
    # update all xlink:href="#glyph..." attributes to point to the new glyph ids
    for el in xpath(".//svg:*[starts-with(@xlink:href, '#glyph')]")(svg):
        old_id = href_local_target(el)
        assert old_id is not None
        if old_id in id_map:
            new_id = id_map[old_id]
            el.attrib[XLINK_HREF] = f"#{new_id}"


def ranges(ints: Iterable[int]) -> Iterator[Tuple[int, int]]:
    # Yield sorted, non-overlapping (min, max) ranges of consecutive integers
    sorted_ints = iter(sorted(set(ints)))
    try:
        start = end = next(sorted_ints)
    except StopIteration:
        return
    for v in sorted_ints:
        if v - 1 == end:
            end = v
        else:
            yield (start, end)
            start = end = v
    yield (start, end)


@_add_method(ttLib.getTableClass("SVG "))
def subset_glyphs(self, s) -> bool:
    if etree is None:
        raise ImportError("No module named 'lxml', required to subset SVG")

    # glyph names (before subsetting)
    glyph_order: List[str] = s.orig_glyph_order
    # map from glyph names to original glyph indices
    rev_orig_glyph_map: Dict[str, int] = s.reverseOrigGlyphMap
    # map from original to new glyph indices (after subsetting)
    glyph_index_map: Dict[int, int] = s.glyph_index_map

    new_docs: List[SVGDocument] = []
    for doc in self.docList:
        glyphs = {
            glyph_order[i] for i in range(doc.startGlyphID, doc.endGlyphID + 1)
        }.intersection(s.glyphs)
        if not glyphs:
            # no intersection: we can drop the whole record
            continue

        svg = etree.fromstring(
            # encode because fromstring dislikes xml encoding decl if input is str.
            # SVG xml encoding must be utf-8 as per OT spec.
            doc.data.encode("utf-8"),
            parser=etree.XMLParser(
                # Disable libxml2 security restrictions to support very deep trees.
                # Without this we would get an error like this:
                # `lxml.etree.XMLSyntaxError: internal error: Huge input lookup`
                # when parsing big fonts e.g. noto-emoji-picosvg.ttf.
                huge_tree=True,
                # ignore blank text as it's not meaningful in OT-SVG; it also prevents
                # dangling tail text after removing an element when pretty_print=True
                remove_blank_text=True,
                # don't replace entities; we don't expect any in OT-SVG and they may
                # be abused for XXE attacks
                resolve_entities=False,
            ),
        )

        elements = group_elements_by_id(svg)
        gids = {rev_orig_glyph_map[g] for g in glyphs}
        element_ids = {f"glyph{i}" for i in gids}
        closure_element_ids(elements, element_ids)

        if not subset_elements(svg, element_ids):
            continue

        if not s.options.retain_gids:
            id_map = remap_glyph_ids(svg, glyph_index_map)
            update_glyph_href_links(svg, id_map)

        new_doc = etree.tostring(svg, pretty_print=s.options.pretty_svg).decode("utf-8")

        new_gids = (glyph_index_map[i] for i in gids)
        for start, end in ranges(new_gids):
            new_docs.append(SVGDocument(new_doc, start, end, doc.compressed))

    self.docList = new_docs

    return bool(self.docList)
