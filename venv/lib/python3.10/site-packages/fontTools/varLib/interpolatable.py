"""
Tool to find wrong contour order between different masters, and
other interpolatability (or lack thereof) issues.

Call as:
$ fonttools varLib.interpolatable font1 font2 ...
"""

from .interpolatableHelpers import *
from .interpolatableTestContourOrder import test_contour_order
from .interpolatableTestStartingPoint import test_starting_point
from fontTools.pens.recordingPen import (
    RecordingPen,
    DecomposingRecordingPen,
    lerpRecordings,
)
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.statisticsPen import StatisticsPen, StatisticsControlPen
from fontTools.pens.momentsPen import OpenContourError
from fontTools.varLib.models import piecewiseLinearMap, normalizeLocation
from fontTools.misc.fixedTools import floatToFixedToStr
from fontTools.misc.transform import Transform
from collections import defaultdict
from types import SimpleNamespace
from functools import wraps
from pprint import pformat
from math import sqrt, atan2, pi
import logging
import os

log = logging.getLogger("fontTools.varLib.interpolatable")

DEFAULT_TOLERANCE = 0.95
DEFAULT_KINKINESS = 0.5
DEFAULT_KINKINESS_LENGTH = 0.002  # ratio of UPEM
DEFAULT_UPEM = 1000


class Glyph:
    ITEMS = (
        "recordings",
        "greenStats",
        "controlStats",
        "greenVectors",
        "controlVectors",
        "nodeTypes",
        "isomorphisms",
        "points",
        "openContours",
    )

    def __init__(self, glyphname, glyphset):
        self.name = glyphname
        for item in self.ITEMS:
            setattr(self, item, [])
        self._populate(glyphset)

    def _fill_in(self, ix):
        for item in self.ITEMS:
            if len(getattr(self, item)) == ix:
                getattr(self, item).append(None)

    def _populate(self, glyphset):
        glyph = glyphset[self.name]
        self.doesnt_exist = glyph is None
        if self.doesnt_exist:
            return

        perContourPen = PerContourOrComponentPen(RecordingPen, glyphset=glyphset)
        try:
            glyph.draw(perContourPen, outputImpliedClosingLine=True)
        except TypeError:
            glyph.draw(perContourPen)
        self.recordings = perContourPen.value
        del perContourPen

        for ix, contour in enumerate(self.recordings):
            nodeTypes = [op for op, arg in contour.value]
            self.nodeTypes.append(nodeTypes)

            greenStats = StatisticsPen(glyphset=glyphset)
            controlStats = StatisticsControlPen(glyphset=glyphset)
            try:
                contour.replay(greenStats)
                contour.replay(controlStats)
                self.openContours.append(False)
            except OpenContourError as e:
                self.openContours.append(True)
                self._fill_in(ix)
                continue
            self.greenStats.append(greenStats)
            self.controlStats.append(controlStats)
            self.greenVectors.append(contour_vector_from_stats(greenStats))
            self.controlVectors.append(contour_vector_from_stats(controlStats))

            # Check starting point
            if nodeTypes[0] == "addComponent":
                self._fill_in(ix)
                continue

            assert nodeTypes[0] == "moveTo"
            assert nodeTypes[-1] in ("closePath", "endPath")
            points = SimpleRecordingPointPen()
            converter = SegmentToPointPen(points, False)
            contour.replay(converter)
            # points.value is a list of pt,bool where bool is true if on-curve and false if off-curve;
            # now check all rotations and mirror-rotations of the contour and build list of isomorphic
            # possible starting points.
            self.points.append(points.value)

            isomorphisms = []
            self.isomorphisms.append(isomorphisms)

            # Add rotations
            add_isomorphisms(points.value, isomorphisms, False)
            # Add mirrored rotations
            add_isomorphisms(points.value, isomorphisms, True)

    def draw(self, pen, countor_idx=None):
        if countor_idx is None:
            for contour in self.recordings:
                contour.draw(pen)
        else:
            self.recordings[countor_idx].draw(pen)


def test_gen(
    glyphsets,
    glyphs=None,
    names=None,
    ignore_missing=False,
    *,
    locations=None,
    tolerance=DEFAULT_TOLERANCE,
    kinkiness=DEFAULT_KINKINESS,
    upem=DEFAULT_UPEM,
    show_all=False,
    discrete_axes=[],
):
    if tolerance >= 10:
        tolerance *= 0.01
    assert 0 <= tolerance <= 1
    if kinkiness >= 10:
        kinkiness *= 0.01
    assert 0 <= kinkiness

    names = names or [repr(g) for g in glyphsets]

    if glyphs is None:
        # `glyphs = glyphsets[0].keys()` is faster, certainly, but doesn't allow for sparse TTFs/OTFs given out of order
        # ... risks the sparse master being the first one, and only processing a subset of the glyphs
        glyphs = {g for glyphset in glyphsets for g in glyphset.keys()}

    parents, order = find_parents_and_order(
        glyphsets, locations, discrete_axes=discrete_axes
    )

    def grand_parent(i, glyphname):
        if i is None:
            return None
        i = parents[i]
        if i is None:
            return None
        while parents[i] is not None and glyphsets[i][glyphname] is None:
            i = parents[i]
        return i

    for glyph_name in glyphs:
        log.info("Testing glyph %s", glyph_name)
        allGlyphs = [Glyph(glyph_name, glyphset) for glyphset in glyphsets]
        if len([1 for glyph in allGlyphs if glyph is not None]) <= 1:
            continue
        for master_idx, (glyph, glyphset, name) in enumerate(
            zip(allGlyphs, glyphsets, names)
        ):
            if glyph.doesnt_exist:
                if not ignore_missing:
                    yield (
                        glyph_name,
                        {
                            "type": InterpolatableProblem.MISSING,
                            "master": name,
                            "master_idx": master_idx,
                        },
                    )
                continue

            has_open = False
            for ix, open in enumerate(glyph.openContours):
                if not open:
                    continue
                has_open = True
                yield (
                    glyph_name,
                    {
                        "type": InterpolatableProblem.OPEN_PATH,
                        "master": name,
                        "master_idx": master_idx,
                        "contour": ix,
                    },
                )
            if has_open:
                continue

        matchings = [None] * len(glyphsets)

        for m1idx in order:
            glyph1 = allGlyphs[m1idx]
            if glyph1 is None or not glyph1.nodeTypes:
                continue
            m0idx = grand_parent(m1idx, glyph_name)
            if m0idx is None:
                continue
            glyph0 = allGlyphs[m0idx]
            if glyph0 is None or not glyph0.nodeTypes:
                continue

            #
            # Basic compatibility checks
            #

            m1 = glyph0.nodeTypes
            m0 = glyph1.nodeTypes
            if len(m0) != len(m1):
                yield (
                    glyph_name,
                    {
                        "type": InterpolatableProblem.PATH_COUNT,
                        "master_1": names[m0idx],
                        "master_2": names[m1idx],
                        "master_1_idx": m0idx,
                        "master_2_idx": m1idx,
                        "value_1": len(m0),
                        "value_2": len(m1),
                    },
                )
                continue

            if m0 != m1:
                for pathIx, (nodes1, nodes2) in enumerate(zip(m0, m1)):
                    if nodes1 == nodes2:
                        continue
                    if len(nodes1) != len(nodes2):
                        yield (
                            glyph_name,
                            {
                                "type": InterpolatableProblem.NODE_COUNT,
                                "path": pathIx,
                                "master_1": names[m0idx],
                                "master_2": names[m1idx],
                                "master_1_idx": m0idx,
                                "master_2_idx": m1idx,
                                "value_1": len(nodes1),
                                "value_2": len(nodes2),
                            },
                        )
                        continue
                    for nodeIx, (n1, n2) in enumerate(zip(nodes1, nodes2)):
                        if n1 != n2:
                            yield (
                                glyph_name,
                                {
                                    "type": InterpolatableProblem.NODE_INCOMPATIBILITY,
                                    "path": pathIx,
                                    "node": nodeIx,
                                    "master_1": names[m0idx],
                                    "master_2": names[m1idx],
                                    "master_1_idx": m0idx,
                                    "master_2_idx": m1idx,
                                    "value_1": n1,
                                    "value_2": n2,
                                },
                            )
                            continue

            #
            # InterpolatableProblem.CONTOUR_ORDER check
            #

            this_tolerance, matching = test_contour_order(glyph0, glyph1)
            if this_tolerance < tolerance:
                yield (
                    glyph_name,
                    {
                        "type": InterpolatableProblem.CONTOUR_ORDER,
                        "master_1": names[m0idx],
                        "master_2": names[m1idx],
                        "master_1_idx": m0idx,
                        "master_2_idx": m1idx,
                        "value_1": list(range(len(matching))),
                        "value_2": matching,
                        "tolerance": this_tolerance,
                    },
                )
                matchings[m1idx] = matching

            #
            # wrong-start-point / weight check
            #

            m0Isomorphisms = glyph0.isomorphisms
            m1Isomorphisms = glyph1.isomorphisms
            m0Vectors = glyph0.greenVectors
            m1Vectors = glyph1.greenVectors
            recording0 = glyph0.recordings
            recording1 = glyph1.recordings

            # If contour-order is wrong, adjust it
            matching = matchings[m1idx]
            if (
                matching is not None and m1Isomorphisms
            ):  # m1 is empty for composite glyphs
                m1Isomorphisms = [m1Isomorphisms[i] for i in matching]
                m1Vectors = [m1Vectors[i] for i in matching]
                recording1 = [recording1[i] for i in matching]

            midRecording = []
            for c0, c1 in zip(recording0, recording1):
                try:
                    r = RecordingPen()
                    r.value = list(lerpRecordings(c0.value, c1.value))
                    midRecording.append(r)
                except ValueError:
                    # Mismatch because of the reordering above
                    midRecording.append(None)

            for ix, (contour0, contour1) in enumerate(
                zip(m0Isomorphisms, m1Isomorphisms)
            ):
                if (
                    contour0 is None
                    or contour1 is None
                    or len(contour0) == 0
                    or len(contour0) != len(contour1)
                ):
                    # We already reported this; or nothing to do; or not compatible
                    # after reordering above.
                    continue

                this_tolerance, proposed_point, reverse = test_starting_point(
                    glyph0, glyph1, ix, tolerance, matching
                )

                if this_tolerance < tolerance:
                    yield (
                        glyph_name,
                        {
                            "type": InterpolatableProblem.WRONG_START_POINT,
                            "contour": ix,
                            "master_1": names[m0idx],
                            "master_2": names[m1idx],
                            "master_1_idx": m0idx,
                            "master_2_idx": m1idx,
                            "value_1": 0,
                            "value_2": proposed_point,
                            "reversed": reverse,
                            "tolerance": this_tolerance,
                        },
                    )

                # Weight check.
                #
                # If contour could be mid-interpolated, and the two
                # contours have the same area sign, proceeed.
                #
                # The sign difference can happen if it's a weirdo
                # self-intersecting contour; ignore it.
                contour = midRecording[ix]

                if contour and (m0Vectors[ix][0] < 0) == (m1Vectors[ix][0] < 0):
                    midStats = StatisticsPen(glyphset=None)
                    contour.replay(midStats)

                    midVector = contour_vector_from_stats(midStats)

                    m0Vec = m0Vectors[ix]
                    m1Vec = m1Vectors[ix]
                    size0 = m0Vec[0] * m0Vec[0]
                    size1 = m1Vec[0] * m1Vec[0]
                    midSize = midVector[0] * midVector[0]

                    for overweight, problem_type in enumerate(
                        (
                            InterpolatableProblem.UNDERWEIGHT,
                            InterpolatableProblem.OVERWEIGHT,
                        )
                    ):
                        if overweight:
                            expectedSize = max(size0, size1)
                            continue
                        else:
                            expectedSize = sqrt(size0 * size1)

                        log.debug(
                            "%s: actual size %g; threshold size %g, master sizes: %g, %g",
                            problem_type,
                            midSize,
                            expectedSize,
                            size0,
                            size1,
                        )

                        if (
                            not overweight and expectedSize * tolerance > midSize + 1e-5
                        ) or (overweight and 1e-5 + expectedSize / tolerance < midSize):
                            try:
                                if overweight:
                                    this_tolerance = expectedSize / midSize
                                else:
                                    this_tolerance = midSize / expectedSize
                            except ZeroDivisionError:
                                this_tolerance = 0
                            log.debug("tolerance %g", this_tolerance)
                            yield (
                                glyph_name,
                                {
                                    "type": problem_type,
                                    "contour": ix,
                                    "master_1": names[m0idx],
                                    "master_2": names[m1idx],
                                    "master_1_idx": m0idx,
                                    "master_2_idx": m1idx,
                                    "tolerance": this_tolerance,
                                },
                            )

            #
            # "kink" detector
            #
            m0 = glyph0.points
            m1 = glyph1.points

            # If contour-order is wrong, adjust it
            if matchings[m1idx] is not None and m1:  # m1 is empty for composite glyphs
                m1 = [m1[i] for i in matchings[m1idx]]

            t = 0.1  # ~sin(radian(6)) for tolerance 0.95
            deviation_threshold = (
                upem * DEFAULT_KINKINESS_LENGTH * DEFAULT_KINKINESS / kinkiness
            )

            for ix, (contour0, contour1) in enumerate(zip(m0, m1)):
                if (
                    contour0 is None
                    or contour1 is None
                    or len(contour0) == 0
                    or len(contour0) != len(contour1)
                ):
                    # We already reported this; or nothing to do; or not compatible
                    # after reordering above.
                    continue

                # Walk the contour, keeping track of three consecutive points, with
                # middle one being an on-curve. If the three are co-linear then
                # check for kinky-ness.
                for i in range(len(contour0)):
                    pt0 = contour0[i]
                    pt1 = contour1[i]
                    if not pt0[1] or not pt1[1]:
                        # Skip off-curves
                        continue
                    pt0_prev = contour0[i - 1]
                    pt1_prev = contour1[i - 1]
                    pt0_next = contour0[(i + 1) % len(contour0)]
                    pt1_next = contour1[(i + 1) % len(contour1)]

                    if pt0_prev[1] and pt1_prev[1]:
                        # At least one off-curve is required
                        continue
                    if pt0_prev[1] and pt1_prev[1]:
                        # At least one off-curve is required
                        continue

                    pt0 = complex(*pt0[0])
                    pt1 = complex(*pt1[0])
                    pt0_prev = complex(*pt0_prev[0])
                    pt1_prev = complex(*pt1_prev[0])
                    pt0_next = complex(*pt0_next[0])
                    pt1_next = complex(*pt1_next[0])

                    # We have three consecutive points. Check whether
                    # they are colinear.
                    d0_prev = pt0 - pt0_prev
                    d0_next = pt0_next - pt0
                    d1_prev = pt1 - pt1_prev
                    d1_next = pt1_next - pt1

                    sin0 = d0_prev.real * d0_next.imag - d0_prev.imag * d0_next.real
                    sin1 = d1_prev.real * d1_next.imag - d1_prev.imag * d1_next.real
                    try:
                        sin0 /= abs(d0_prev) * abs(d0_next)
                        sin1 /= abs(d1_prev) * abs(d1_next)
                    except ZeroDivisionError:
                        continue

                    if abs(sin0) > t or abs(sin1) > t:
                        # Not colinear / not smooth.
                        continue

                    # Check the mid-point is actually, well, in the middle.
                    dot0 = d0_prev.real * d0_next.real + d0_prev.imag * d0_next.imag
                    dot1 = d1_prev.real * d1_next.real + d1_prev.imag * d1_next.imag
                    if dot0 < 0 or dot1 < 0:
                        # Sharp corner.
                        continue

                    # Fine, if handle ratios are similar...
                    r0 = abs(d0_prev) / (abs(d0_prev) + abs(d0_next))
                    r1 = abs(d1_prev) / (abs(d1_prev) + abs(d1_next))
                    r_diff = abs(r0 - r1)
                    if abs(r_diff) < t:
                        # Smooth enough.
                        continue

                    mid = (pt0 + pt1) / 2
                    mid_prev = (pt0_prev + pt1_prev) / 2
                    mid_next = (pt0_next + pt1_next) / 2

                    mid_d0 = mid - mid_prev
                    mid_d1 = mid_next - mid

                    sin_mid = mid_d0.real * mid_d1.imag - mid_d0.imag * mid_d1.real
                    try:
                        sin_mid /= abs(mid_d0) * abs(mid_d1)
                    except ZeroDivisionError:
                        continue

                    # ...or if the angles are similar.
                    if abs(sin_mid) * (tolerance * kinkiness) <= t:
                        # Smooth enough.
                        continue

                    # How visible is the kink?

                    cross = sin_mid * abs(mid_d0) * abs(mid_d1)
                    arc_len = abs(mid_d0 + mid_d1)
                    deviation = abs(cross / arc_len)
                    if deviation < deviation_threshold:
                        continue
                    deviation_ratio = deviation / arc_len
                    if deviation_ratio > t:
                        continue

                    this_tolerance = t / (abs(sin_mid) * kinkiness)

                    log.debug(
                        "kink: deviation %g; deviation_ratio %g; sin_mid %g; r_diff %g",
                        deviation,
                        deviation_ratio,
                        sin_mid,
                        r_diff,
                    )
                    log.debug("tolerance %g", this_tolerance)
                    yield (
                        glyph_name,
                        {
                            "type": InterpolatableProblem.KINK,
                            "contour": ix,
                            "master_1": names[m0idx],
                            "master_2": names[m1idx],
                            "master_1_idx": m0idx,
                            "master_2_idx": m1idx,
                            "value": i,
                            "tolerance": this_tolerance,
                        },
                    )

            #
            # --show-all
            #

            if show_all:
                yield (
                    glyph_name,
                    {
                        "type": InterpolatableProblem.NOTHING,
                        "master_1": names[m0idx],
                        "master_2": names[m1idx],
                        "master_1_idx": m0idx,
                        "master_2_idx": m1idx,
                    },
                )


@wraps(test_gen)
def test(*args, **kwargs):
    problems = defaultdict(list)
    for glyphname, problem in test_gen(*args, **kwargs):
        problems[glyphname].append(problem)
    return problems


def recursivelyAddGlyph(glyphname, glyphset, ttGlyphSet, glyf):
    if glyphname in glyphset:
        return
    glyphset[glyphname] = ttGlyphSet[glyphname]

    for component in getattr(glyf[glyphname], "components", []):
        recursivelyAddGlyph(component.glyphName, glyphset, ttGlyphSet, glyf)


def ensure_parent_dir(path):
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    return path


def main(args=None):
    """Test for interpolatability issues between fonts"""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        "fonttools varLib.interpolatable",
        description=main.__doc__,
    )
    parser.add_argument(
        "--glyphs",
        action="store",
        help="Space-separate name of glyphs to check",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Show all glyph pairs, even if no problems are found",
    )
    parser.add_argument(
        "--tolerance",
        action="store",
        type=float,
        help="Error tolerance. Between 0 and 1. Default %s" % DEFAULT_TOLERANCE,
    )
    parser.add_argument(
        "--kinkiness",
        action="store",
        type=float,
        help="How aggressively report kinks. Default %s" % DEFAULT_KINKINESS,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report in JSON format",
    )
    parser.add_argument(
        "--pdf",
        action="store",
        help="Output report in PDF format",
    )
    parser.add_argument(
        "--ps",
        action="store",
        help="Output report in PostScript format",
    )
    parser.add_argument(
        "--html",
        action="store",
        help="Output report in HTML format",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only exit with code 1 or 0, no output",
    )
    parser.add_argument(
        "--output",
        action="store",
        help="Output file for the problem report; Default: stdout",
    )
    parser.add_argument(
        "--ignore-missing",
        action="store_true",
        help="Will not report glyphs missing from sparse masters as errors",
    )
    parser.add_argument(
        "inputs",
        metavar="FILE",
        type=str,
        nargs="+",
        help="Input a single variable font / DesignSpace / Glyphs file, or multiple TTF/UFO files",
    )
    parser.add_argument(
        "--name",
        metavar="NAME",
        type=str,
        action="append",
        help="Name of the master to use in the report. If not provided, all are used.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Run verbosely.")
    parser.add_argument("--debug", action="store_true", help="Run with debug output.")

    args = parser.parse_args(args)

    from fontTools import configLogger

    configLogger(level=("INFO" if args.verbose else "WARNING"))
    if args.debug:
        configLogger(level="DEBUG")

    glyphs = args.glyphs.split() if args.glyphs else None

    from os.path import basename

    fonts = []
    names = []
    locations = []
    discrete_axes = set()
    upem = DEFAULT_UPEM

    original_args_inputs = tuple(args.inputs)

    if len(args.inputs) == 1:
        designspace = None
        if args.inputs[0].endswith(".designspace"):
            from fontTools.designspaceLib import DesignSpaceDocument

            designspace = DesignSpaceDocument.fromfile(args.inputs[0])
            args.inputs = [master.path for master in designspace.sources]
            locations = [master.location for master in designspace.sources]
            discrete_axes = {
                a.name for a in designspace.axes if not hasattr(a, "minimum")
            }
            axis_triples = {
                a.name: (a.minimum, a.default, a.maximum)
                for a in designspace.axes
                if a.name not in discrete_axes
            }
            axis_mappings = {a.name: a.map for a in designspace.axes}
            axis_triples = {
                k: tuple(piecewiseLinearMap(v, dict(axis_mappings[k])) for v in vv)
                for k, vv in axis_triples.items()
            }

        elif args.inputs[0].endswith((".glyphs", ".glyphspackage")):
            from glyphsLib import GSFont, to_designspace

            gsfont = GSFont(args.inputs[0])
            upem = gsfont.upm
            designspace = to_designspace(gsfont)
            fonts = [source.font for source in designspace.sources]
            names = ["%s-%s" % (f.info.familyName, f.info.styleName) for f in fonts]
            args.inputs = []
            locations = [master.location for master in designspace.sources]
            axis_triples = {
                a.name: (a.minimum, a.default, a.maximum) for a in designspace.axes
            }
            axis_mappings = {a.name: a.map for a in designspace.axes}
            axis_triples = {
                k: tuple(piecewiseLinearMap(v, dict(axis_mappings[k])) for v in vv)
                for k, vv in axis_triples.items()
            }

        elif args.inputs[0].endswith(".ttf") or args.inputs[0].endswith(".otf"):
            from fontTools.ttLib import TTFont

            # Is variable font?

            font = TTFont(args.inputs[0])
            upem = font["head"].unitsPerEm

            fvar = font["fvar"]
            axisMapping = {}
            for axis in fvar.axes:
                axisMapping[axis.axisTag] = {
                    -1: axis.minValue,
                    0: axis.defaultValue,
                    1: axis.maxValue,
                }
            normalized = False
            if "avar" in font:
                avar = font["avar"]
                if getattr(avar.table, "VarStore", None):
                    axisMapping = {tag: {-1: -1, 0: 0, 1: 1} for tag in axisMapping}
                    normalized = True
                else:
                    for axisTag, segments in avar.segments.items():
                        fvarMapping = axisMapping[axisTag].copy()
                        for location, value in segments.items():
                            axisMapping[axisTag][value] = piecewiseLinearMap(
                                location, fvarMapping
                            )

            # Gather all glyphs at their "master" locations
            ttGlyphSets = {}
            glyphsets = defaultdict(dict)

            if "gvar" in font:
                gvar = font["gvar"]
                glyf = font["glyf"]

                if glyphs is None:
                    glyphs = sorted(gvar.variations.keys())
                for glyphname in glyphs:
                    for var in gvar.variations[glyphname]:
                        locDict = {}
                        loc = []
                        for tag, val in sorted(var.axes.items()):
                            locDict[tag] = val[1]
                            loc.append((tag, val[1]))

                        locTuple = tuple(loc)
                        if locTuple not in ttGlyphSets:
                            ttGlyphSets[locTuple] = font.getGlyphSet(
                                location=locDict, normalized=True, recalcBounds=False
                            )

                        recursivelyAddGlyph(
                            glyphname, glyphsets[locTuple], ttGlyphSets[locTuple], glyf
                        )

            elif "CFF2" in font:
                fvarAxes = font["fvar"].axes
                cff2 = font["CFF2"].cff.topDictIndex[0]
                charstrings = cff2.CharStrings

                if glyphs is None:
                    glyphs = sorted(charstrings.keys())
                for glyphname in glyphs:
                    cs = charstrings[glyphname]
                    private = cs.private

                    # Extract vsindex for the glyph
                    vsindices = {getattr(private, "vsindex", 0)}
                    vsindex = getattr(private, "vsindex", 0)
                    last_op = 0
                    # The spec says vsindex can only appear once and must be the first
                    # operator in the charstring, but we support multiple.
                    # https://github.com/harfbuzz/boring-expansion-spec/issues/158
                    for op in enumerate(cs.program):
                        if op == "blend":
                            vsindices.add(vsindex)
                        elif op == "vsindex":
                            assert isinstance(last_op, int)
                            vsindex = last_op
                        last_op = op

                    if not hasattr(private, "vstore"):
                        continue

                    varStore = private.vstore.otVarStore
                    for vsindex in vsindices:
                        varData = varStore.VarData[vsindex]
                        for regionIndex in varData.VarRegionIndex:
                            region = varStore.VarRegionList.Region[regionIndex]

                            locDict = {}
                            loc = []
                            for axisIndex, axis in enumerate(region.VarRegionAxis):
                                tag = fvarAxes[axisIndex].axisTag
                                val = axis.PeakCoord
                                locDict[tag] = val
                                loc.append((tag, val))

                            locTuple = tuple(loc)
                            if locTuple not in ttGlyphSets:
                                ttGlyphSets[locTuple] = font.getGlyphSet(
                                    location=locDict,
                                    normalized=True,
                                    recalcBounds=False,
                                )

                            glyphset = glyphsets[locTuple]
                            glyphset[glyphname] = ttGlyphSets[locTuple][glyphname]

            names = ["''"]
            fonts = [font.getGlyphSet()]
            locations = [{}]
            axis_triples = {a: (-1, 0, +1) for a in sorted(axisMapping.keys())}
            for locTuple in sorted(glyphsets.keys(), key=lambda v: (len(v), v)):
                name = (
                    "'"
                    + " ".join(
                        "%s=%s"
                        % (
                            k,
                            floatToFixedToStr(
                                piecewiseLinearMap(v, axisMapping[k]), 14
                            ),
                        )
                        for k, v in locTuple
                    )
                    + "'"
                )
                if normalized:
                    name += " (normalized)"
                names.append(name)
                fonts.append(glyphsets[locTuple])
                locations.append(dict(locTuple))

            args.ignore_missing = True
            args.inputs = []

    if not locations:
        locations = [{} for _ in fonts]

    for filename in args.inputs:
        if filename.endswith(".ufo"):
            from fontTools.ufoLib import UFOReader

            font = UFOReader(filename)
            info = SimpleNamespace()
            font.readInfo(info)
            upem = info.unitsPerEm
            fonts.append(font)
        else:
            from fontTools.ttLib import TTFont

            font = TTFont(filename)
            upem = font["head"].unitsPerEm
            fonts.append(font)

        names.append(basename(filename).rsplit(".", 1)[0])

    if len(fonts) < 2:
        log.warning("Font file does not seem to be variable. Nothing to check.")
        return

    glyphsets = []
    for font in fonts:
        if hasattr(font, "getGlyphSet"):
            glyphset = font.getGlyphSet()
        else:
            glyphset = font
        glyphsets.append({k: glyphset[k] for k in glyphset.keys()})

    if args.name:
        accepted_names = set(args.name)
        glyphsets = [
            glyphset
            for name, glyphset in zip(names, glyphsets)
            if name in accepted_names
        ]
        locations = [
            location
            for name, location in zip(names, locations)
            if name in accepted_names
        ]
        names = [name for name in names if name in accepted_names]

    if not glyphs:
        glyphs = sorted(set([gn for glyphset in glyphsets for gn in glyphset.keys()]))

    glyphsSet = set(glyphs)
    for glyphset in glyphsets:
        glyphSetGlyphNames = set(glyphset.keys())
        diff = glyphsSet - glyphSetGlyphNames
        if diff:
            for gn in diff:
                glyphset[gn] = None

    # Normalize locations
    locations = [
        {
            **normalizeLocation(loc, axis_triples),
            **{k: v for k, v in loc.items() if k in discrete_axes},
        }
        for loc in locations
    ]
    tolerance = args.tolerance or DEFAULT_TOLERANCE
    kinkiness = args.kinkiness if args.kinkiness is not None else DEFAULT_KINKINESS

    try:
        log.info("Running on %d glyphsets", len(glyphsets))
        log.info("Locations: %s", pformat(locations))
        problems_gen = test_gen(
            glyphsets,
            glyphs=glyphs,
            names=names,
            locations=locations,
            upem=upem,
            ignore_missing=args.ignore_missing,
            tolerance=tolerance,
            kinkiness=kinkiness,
            show_all=args.show_all,
            discrete_axes=discrete_axes,
        )
        problems = defaultdict(list)

        f = (
            sys.stdout
            if args.output is None
            else open(ensure_parent_dir(args.output), "w")
        )

        if not args.quiet:
            if args.json:
                import json

                for glyphname, problem in problems_gen:
                    problems[glyphname].append(problem)

                print(json.dumps(problems), file=f)
            else:
                last_glyphname = None
                for glyphname, p in problems_gen:
                    problems[glyphname].append(p)

                    if glyphname != last_glyphname:
                        print(f"Glyph {glyphname} was not compatible:", file=f)
                        last_glyphname = glyphname
                        last_master_idxs = None

                    master_idxs = (
                        (p["master_idx"],)
                        if "master_idx" in p
                        else (p["master_1_idx"], p["master_2_idx"])
                    )
                    if master_idxs != last_master_idxs:
                        master_names = (
                            (p["master"],)
                            if "master" in p
                            else (p["master_1"], p["master_2"])
                        )
                        print(f"  Masters: %s:" % ", ".join(master_names), file=f)
                        last_master_idxs = master_idxs

                    if p["type"] == InterpolatableProblem.MISSING:
                        print(
                            "    Glyph was missing in master %s" % p["master"], file=f
                        )
                    elif p["type"] == InterpolatableProblem.OPEN_PATH:
                        print(
                            "    Glyph has an open path in master %s" % p["master"],
                            file=f,
                        )
                    elif p["type"] == InterpolatableProblem.PATH_COUNT:
                        print(
                            "    Path count differs: %i in %s, %i in %s"
                            % (
                                p["value_1"],
                                p["master_1"],
                                p["value_2"],
                                p["master_2"],
                            ),
                            file=f,
                        )
                    elif p["type"] == InterpolatableProblem.NODE_COUNT:
                        print(
                            "    Node count differs in path %i: %i in %s, %i in %s"
                            % (
                                p["path"],
                                p["value_1"],
                                p["master_1"],
                                p["value_2"],
                                p["master_2"],
                            ),
                            file=f,
                        )
                    elif p["type"] == InterpolatableProblem.NODE_INCOMPATIBILITY:
                        print(
                            "    Node %o incompatible in path %i: %s in %s, %s in %s"
                            % (
                                p["node"],
                                p["path"],
                                p["value_1"],
                                p["master_1"],
                                p["value_2"],
                                p["master_2"],
                            ),
                            file=f,
                        )
                    elif p["type"] == InterpolatableProblem.CONTOUR_ORDER:
                        print(
                            "    Contour order differs: %s in %s, %s in %s"
                            % (
                                p["value_1"],
                                p["master_1"],
                                p["value_2"],
                                p["master_2"],
                            ),
                            file=f,
                        )
                    elif p["type"] == InterpolatableProblem.WRONG_START_POINT:
                        print(
                            "    Contour %d start point differs: %s in %s, %s in %s; reversed: %s"
                            % (
                                p["contour"],
                                p["value_1"],
                                p["master_1"],
                                p["value_2"],
                                p["master_2"],
                                p["reversed"],
                            ),
                            file=f,
                        )
                    elif p["type"] == InterpolatableProblem.UNDERWEIGHT:
                        print(
                            "    Contour %d interpolation is underweight: %s, %s"
                            % (
                                p["contour"],
                                p["master_1"],
                                p["master_2"],
                            ),
                            file=f,
                        )
                    elif p["type"] == InterpolatableProblem.OVERWEIGHT:
                        print(
                            "    Contour %d interpolation is overweight: %s, %s"
                            % (
                                p["contour"],
                                p["master_1"],
                                p["master_2"],
                            ),
                            file=f,
                        )
                    elif p["type"] == InterpolatableProblem.KINK:
                        print(
                            "    Contour %d has a kink at %s: %s, %s"
                            % (
                                p["contour"],
                                p["value"],
                                p["master_1"],
                                p["master_2"],
                            ),
                            file=f,
                        )
                    elif p["type"] == InterpolatableProblem.NOTHING:
                        print(
                            "    Showing %s and %s"
                            % (
                                p["master_1"],
                                p["master_2"],
                            ),
                            file=f,
                        )
        else:
            for glyphname, problem in problems_gen:
                problems[glyphname].append(problem)

        problems = sort_problems(problems)

        for p in "ps", "pdf":
            arg = getattr(args, p)
            if arg is None:
                continue
            log.info("Writing %s to %s", p.upper(), arg)
            from .interpolatablePlot import InterpolatablePS, InterpolatablePDF

            PlotterClass = InterpolatablePS if p == "ps" else InterpolatablePDF

            with PlotterClass(
                ensure_parent_dir(arg), glyphsets=glyphsets, names=names
            ) as doc:
                doc.add_title_page(
                    original_args_inputs, tolerance=tolerance, kinkiness=kinkiness
                )
                if problems:
                    doc.add_summary(problems)
                doc.add_problems(problems)
                if not problems and not args.quiet:
                    doc.draw_cupcake()
                if problems:
                    doc.add_index()
                    doc.add_table_of_contents()

        if args.html:
            log.info("Writing HTML to %s", args.html)
            from .interpolatablePlot import InterpolatableSVG

            svgs = []
            glyph_starts = {}
            with InterpolatableSVG(svgs, glyphsets=glyphsets, names=names) as svg:
                svg.add_title_page(
                    original_args_inputs,
                    show_tolerance=False,
                    tolerance=tolerance,
                    kinkiness=kinkiness,
                )
                for glyph, glyph_problems in problems.items():
                    glyph_starts[len(svgs)] = glyph
                    svg.add_problems(
                        {glyph: glyph_problems},
                        show_tolerance=False,
                        show_page_number=False,
                    )
                if not problems and not args.quiet:
                    svg.draw_cupcake()

            import base64

            with open(ensure_parent_dir(args.html), "wb") as f:
                f.write(b"<!DOCTYPE html>\n")
                f.write(
                    b'<html><body align="center" style="font-family: sans-serif; text-color: #222">\n'
                )
                f.write(b"<title>fonttools varLib.interpolatable report</title>\n")
                for i, svg in enumerate(svgs):
                    if i in glyph_starts:
                        f.write(f"<h1>Glyph {glyph_starts[i]}</h1>\n".encode("utf-8"))
                    f.write("<img src='data:image/svg+xml;base64,".encode("utf-8"))
                    f.write(base64.b64encode(svg))
                    f.write(b"' />\n")
                    f.write(b"<hr>\n")
                f.write(b"</body></html>\n")

    except Exception as e:
        e.args += original_args_inputs
        log.error(e)
        raise

    if problems:
        return problems


if __name__ == "__main__":
    import sys

    problems = main()
    sys.exit(int(bool(problems)))
