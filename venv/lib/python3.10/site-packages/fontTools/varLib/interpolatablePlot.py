from .interpolatableHelpers import *
from fontTools.ttLib import TTFont
from fontTools.ttLib.ttGlyphSet import LerpGlyphSet
from fontTools.pens.recordingPen import (
    RecordingPen,
    DecomposingRecordingPen,
    RecordingPointPen,
)
from fontTools.pens.boundsPen import ControlBoundsPen
from fontTools.pens.cairoPen import CairoPen
from fontTools.pens.pointPen import (
    SegmentToPointPen,
    PointToSegmentPen,
    ReverseContourPointPen,
)
from fontTools.varLib.interpolatableHelpers import (
    PerContourOrComponentPen,
    SimpleRecordingPointPen,
)
from itertools import cycle
from functools import wraps
from io import BytesIO
import cairo
import math
import os
import logging

log = logging.getLogger("fontTools.varLib.interpolatable")


class OverridingDict(dict):
    def __init__(self, parent_dict):
        self.parent_dict = parent_dict

    def __missing__(self, key):
        return self.parent_dict[key]


class InterpolatablePlot:
    width = 8.5 * 72
    height = 11 * 72
    pad = 0.1 * 72
    title_font_size = 24
    font_size = 16
    page_number = 1
    head_color = (0.3, 0.3, 0.3)
    label_color = (0.2, 0.2, 0.2)
    border_color = (0.9, 0.9, 0.9)
    border_width = 0.5
    fill_color = (0.8, 0.8, 0.8)
    stroke_color = (0.1, 0.1, 0.1)
    stroke_width = 1
    oncurve_node_color = (0, 0.8, 0, 0.7)
    oncurve_node_diameter = 6
    offcurve_node_color = (0, 0.5, 0, 0.7)
    offcurve_node_diameter = 4
    handle_color = (0, 0.5, 0, 0.7)
    handle_width = 0.5
    corrected_start_point_color = (0, 0.9, 0, 0.7)
    corrected_start_point_size = 7
    wrong_start_point_color = (1, 0, 0, 0.7)
    start_point_color = (0, 0, 1, 0.7)
    start_arrow_length = 9
    kink_point_size = 7
    kink_point_color = (1, 0, 1, 0.7)
    kink_circle_size = 15
    kink_circle_stroke_width = 1
    kink_circle_color = (1, 0, 1, 0.7)
    contour_colors = ((1, 0, 0), (0, 0, 1), (0, 1, 0), (1, 1, 0), (1, 0, 1), (0, 1, 1))
    contour_alpha = 0.5
    weight_issue_contour_color = (0, 0, 0, 0.4)
    no_issues_label = "Your font's good! Have a cupcake..."
    no_issues_label_color = (0, 0.5, 0)
    cupcake_color = (0.3, 0, 0.3)
    cupcake = r"""
                          ,@.
                        ,@.@@,.
                  ,@@,.@@@.  @.@@@,.
                ,@@. @@@.     @@. @@,.
        ,@@@.@,.@.              @.  @@@@,.@.@@,.
   ,@@.@.     @@.@@.            @,.    .@' @'  @@,
 ,@@. @.          .@@.@@@.  @@'                  @,
,@.  @@.                                          @,
@.     @,@@,.     ,                             .@@,
@,.       .@,@@,.         .@@,.  ,       .@@,  @, @,
@.                             .@. @ @@,.    ,      @
 @,.@@.     @,.      @@,.      @.           @,.    @'
  @@||@,.  @'@,.       @@,.  @@ @,.        @'@@,  @'
     \\@@@@'  @,.      @'@@@@'   @@,.   @@@' //@@@'
      |||||||| @@,.  @@' |||||||  |@@@|@||  ||
       \\\\\\\  ||@@@||  |||||||  |||||||  //
        |||||||  ||||||  ||||||   ||||||  ||
         \\\\\\  ||||||  ||||||  ||||||  //
          ||||||  |||||  |||||   |||||  ||
           \\\\\  |||||  |||||  |||||  //
            |||||  ||||  |||||  ||||  ||
             \\\\  ||||  ||||  ||||  //
              ||||||||||||||||||||||||
"""
    emoticon_color = (0, 0.3, 0.3)
    shrug = r"""\_(")_/"""
    underweight = r"""
 o
/|\
/ \
"""
    overweight = r"""
 o
/O\
/ \
"""
    yay = r""" \o/ """

    def __init__(self, out, glyphsets, names=None, **kwargs):
        self.out = out
        self.glyphsets = glyphsets
        self.names = names or [repr(g) for g in glyphsets]
        self.toc = {}

        for k, v in kwargs.items():
            if not hasattr(self, k):
                raise TypeError("Unknown keyword argument: %s" % k)
            setattr(self, k, v)

        self.panel_width = self.width / 2 - self.pad * 3
        self.panel_height = (
            self.height / 2 - self.pad * 6 - self.font_size * 2 - self.title_font_size
        )

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        pass

    def show_page(self):
        self.page_number += 1

    def add_title_page(
        self, files, *, show_tolerance=True, tolerance=None, kinkiness=None
    ):
        pad = self.pad
        width = self.width - 3 * self.pad
        height = self.height - 2 * self.pad
        x = y = pad

        self.draw_label(
            "Problem report for:",
            x=x,
            y=y,
            bold=True,
            width=width,
            font_size=self.title_font_size,
        )
        y += self.title_font_size

        import hashlib

        for file in files:
            base_file = os.path.basename(file)
            y += self.font_size + self.pad
            self.draw_label(base_file, x=x, y=y, bold=True, width=width)
            y += self.font_size + self.pad

            try:
                h = hashlib.sha1(open(file, "rb").read()).hexdigest()
                self.draw_label("sha1: %s" % h, x=x + pad, y=y, width=width)
                y += self.font_size
            except IsADirectoryError:
                pass

            if file.endswith(".ttf"):
                ttFont = TTFont(file)
                name = ttFont["name"] if "name" in ttFont else None
                if name:
                    for what, nameIDs in (
                        ("Family name", (21, 16, 1)),
                        ("Version", (5,)),
                    ):
                        n = name.getFirstDebugName(nameIDs)
                        if n is None:
                            continue
                        self.draw_label(
                            "%s: %s" % (what, n), x=x + pad, y=y, width=width
                        )
                        y += self.font_size + self.pad
            elif file.endswith((".glyphs", ".glyphspackage")):
                from glyphsLib import GSFont

                f = GSFont(file)
                for what, field in (
                    ("Family name", "familyName"),
                    ("VersionMajor", "versionMajor"),
                    ("VersionMinor", "_versionMinor"),
                ):
                    self.draw_label(
                        "%s: %s" % (what, getattr(f, field)),
                        x=x + pad,
                        y=y,
                        width=width,
                    )
                    y += self.font_size + self.pad

        self.draw_legend(
            show_tolerance=show_tolerance, tolerance=tolerance, kinkiness=kinkiness
        )
        self.show_page()

    def draw_legend(self, *, show_tolerance=True, tolerance=None, kinkiness=None):
        cr = cairo.Context(self.surface)

        x = self.pad
        y = self.height - self.pad - self.font_size * 2
        width = self.width - 2 * self.pad

        xx = x + self.pad * 2
        xxx = x + self.pad * 4

        if show_tolerance:
            self.draw_label(
                "Tolerance: badness; closer to zero the worse", x=xxx, y=y, width=width
            )
            y -= self.pad + self.font_size

        self.draw_label("Underweight contours", x=xxx, y=y, width=width)
        cr.rectangle(xx - self.pad * 0.7, y, 1.5 * self.pad, self.font_size)
        cr.set_source_rgb(*self.fill_color)
        cr.fill_preserve()
        if self.stroke_color:
            cr.set_source_rgb(*self.stroke_color)
            cr.set_line_width(self.stroke_width)
            cr.stroke_preserve()
        cr.set_source_rgba(*self.weight_issue_contour_color)
        cr.fill()
        y -= self.pad + self.font_size

        self.draw_label(
            "Colored contours: contours with the wrong order", x=xxx, y=y, width=width
        )
        cr.rectangle(xx - self.pad * 0.7, y, 1.5 * self.pad, self.font_size)
        if self.fill_color:
            cr.set_source_rgb(*self.fill_color)
            cr.fill_preserve()
        if self.stroke_color:
            cr.set_source_rgb(*self.stroke_color)
            cr.set_line_width(self.stroke_width)
            cr.stroke_preserve()
        cr.set_source_rgba(*self.contour_colors[0], self.contour_alpha)
        cr.fill()
        y -= self.pad + self.font_size

        self.draw_label("Kink artifact", x=xxx, y=y, width=width)
        self.draw_circle(
            cr,
            x=xx,
            y=y + self.font_size * 0.5,
            diameter=self.kink_circle_size,
            stroke_width=self.kink_circle_stroke_width,
            color=self.kink_circle_color,
        )
        y -= self.pad + self.font_size

        self.draw_label("Point causing kink in the contour", x=xxx, y=y, width=width)
        self.draw_dot(
            cr,
            x=xx,
            y=y + self.font_size * 0.5,
            diameter=self.kink_point_size,
            color=self.kink_point_color,
        )
        y -= self.pad + self.font_size

        self.draw_label("Suggested new contour start point", x=xxx, y=y, width=width)
        self.draw_dot(
            cr,
            x=xx,
            y=y + self.font_size * 0.5,
            diameter=self.corrected_start_point_size,
            color=self.corrected_start_point_color,
        )
        y -= self.pad + self.font_size

        self.draw_label(
            "Contour start point in contours with wrong direction",
            x=xxx,
            y=y,
            width=width,
        )
        self.draw_arrow(
            cr,
            x=xx - self.start_arrow_length * 0.3,
            y=y + self.font_size * 0.5,
            color=self.wrong_start_point_color,
        )
        y -= self.pad + self.font_size

        self.draw_label(
            "Contour start point when the first two points overlap",
            x=xxx,
            y=y,
            width=width,
        )
        self.draw_dot(
            cr,
            x=xx,
            y=y + self.font_size * 0.5,
            diameter=self.corrected_start_point_size,
            color=self.start_point_color,
        )
        y -= self.pad + self.font_size

        self.draw_label("Contour start point and direction", x=xxx, y=y, width=width)
        self.draw_arrow(
            cr,
            x=xx - self.start_arrow_length * 0.3,
            y=y + self.font_size * 0.5,
            color=self.start_point_color,
        )
        y -= self.pad + self.font_size

        self.draw_label("Legend:", x=x, y=y, width=width, bold=True)
        y -= self.pad + self.font_size

        if kinkiness is not None:
            self.draw_label(
                "Kink-reporting aggressiveness: %g" % kinkiness,
                x=xxx,
                y=y,
                width=width,
            )
            y -= self.pad + self.font_size

        if tolerance is not None:
            self.draw_label(
                "Error tolerance: %g" % tolerance,
                x=xxx,
                y=y,
                width=width,
            )
            y -= self.pad + self.font_size

        self.draw_label("Parameters:", x=x, y=y, width=width, bold=True)
        y -= self.pad + self.font_size

    def add_summary(self, problems):
        pad = self.pad
        width = self.width - 3 * self.pad
        height = self.height - 2 * self.pad
        x = y = pad

        self.draw_label(
            "Summary of problems",
            x=x,
            y=y,
            bold=True,
            width=width,
            font_size=self.title_font_size,
        )
        y += self.title_font_size

        glyphs_per_problem = defaultdict(set)
        for glyphname, problems in sorted(problems.items()):
            for problem in problems:
                glyphs_per_problem[problem["type"]].add(glyphname)

        if "nothing" in glyphs_per_problem:
            del glyphs_per_problem["nothing"]

        for problem_type in sorted(
            glyphs_per_problem, key=lambda x: InterpolatableProblem.severity[x]
        ):
            y += self.font_size
            self.draw_label(
                "%s: %d" % (problem_type, len(glyphs_per_problem[problem_type])),
                x=x,
                y=y,
                width=width,
                bold=True,
            )
            y += self.font_size

            for glyphname in sorted(glyphs_per_problem[problem_type]):
                if y + self.font_size > height:
                    self.show_page()
                    y = self.font_size + pad
                self.draw_label(glyphname, x=x + 2 * pad, y=y, width=width - 2 * pad)
                y += self.font_size

        self.show_page()

    def _add_listing(self, title, items):
        pad = self.pad
        width = self.width - 2 * self.pad
        height = self.height - 2 * self.pad
        x = y = pad

        self.draw_label(
            title, x=x, y=y, bold=True, width=width, font_size=self.title_font_size
        )
        y += self.title_font_size + self.pad

        last_glyphname = None
        for page_no, (glyphname, problems) in items:
            if glyphname == last_glyphname:
                continue
            last_glyphname = glyphname
            if y + self.font_size > height:
                self.show_page()
                y = self.font_size + pad
            self.draw_label(glyphname, x=x + 5 * pad, y=y, width=width - 2 * pad)
            self.draw_label(str(page_no), x=x, y=y, width=4 * pad, align=1)
            y += self.font_size

        self.show_page()

    def add_table_of_contents(self):
        self._add_listing("Table of contents", sorted(self.toc.items()))

    def add_index(self):
        self._add_listing("Index", sorted(self.toc.items(), key=lambda x: x[1][0]))

    def add_problems(self, problems, *, show_tolerance=True, show_page_number=True):
        for glyph, glyph_problems in problems.items():
            last_masters = None
            current_glyph_problems = []
            for p in glyph_problems:
                masters = (
                    p["master_idx"]
                    if "master_idx" in p
                    else (p["master_1_idx"], p["master_2_idx"])
                )
                if masters == last_masters:
                    current_glyph_problems.append(p)
                    continue
                # Flush
                if current_glyph_problems:
                    self.add_problem(
                        glyph,
                        current_glyph_problems,
                        show_tolerance=show_tolerance,
                        show_page_number=show_page_number,
                    )
                    self.show_page()
                    current_glyph_problems = []
                last_masters = masters
                current_glyph_problems.append(p)
            if current_glyph_problems:
                self.add_problem(
                    glyph,
                    current_glyph_problems,
                    show_tolerance=show_tolerance,
                    show_page_number=show_page_number,
                )
                self.show_page()

    def add_problem(
        self, glyphname, problems, *, show_tolerance=True, show_page_number=True
    ):
        if type(problems) not in (list, tuple):
            problems = [problems]

        self.toc[self.page_number] = (glyphname, problems)

        problem_type = problems[0]["type"]
        problem_types = set(problem["type"] for problem in problems)
        if not all(pt == problem_type for pt in problem_types):
            problem_type = ", ".join(sorted({problem["type"] for problem in problems}))

        log.info("Drawing %s: %s", glyphname, problem_type)

        master_keys = (
            ("master_idx",)
            if "master_idx" in problems[0]
            else ("master_1_idx", "master_2_idx")
        )
        master_indices = [problems[0][k] for k in master_keys]

        if problem_type == InterpolatableProblem.MISSING:
            sample_glyph = next(
                i for i, m in enumerate(self.glyphsets) if m[glyphname] is not None
            )
            master_indices.insert(0, sample_glyph)

        x = self.pad
        y = self.pad

        self.draw_label(
            "Glyph name: " + glyphname,
            x=x,
            y=y,
            color=self.head_color,
            align=0,
            bold=True,
            font_size=self.title_font_size,
        )
        tolerance = min(p.get("tolerance", 1) for p in problems)
        if tolerance < 1 and show_tolerance:
            self.draw_label(
                "tolerance: %.2f" % tolerance,
                x=x,
                y=y,
                width=self.width - 2 * self.pad,
                align=1,
                bold=True,
            )
        y += self.title_font_size + self.pad
        self.draw_label(
            "Problems: " + problem_type,
            x=x,
            y=y,
            width=self.width - 2 * self.pad,
            color=self.head_color,
            bold=True,
        )
        y += self.font_size + self.pad * 2

        scales = []
        for which, master_idx in enumerate(master_indices):
            glyphset = self.glyphsets[master_idx]
            name = self.names[master_idx]

            self.draw_label(
                name,
                x=x,
                y=y,
                color=self.label_color,
                width=self.panel_width,
                align=0.5,
            )
            y += self.font_size + self.pad

            if glyphset[glyphname] is not None:
                scales.append(
                    self.draw_glyph(glyphset, glyphname, problems, which, x=x, y=y)
                )
            else:
                self.draw_emoticon(self.shrug, x=x, y=y)
            y += self.panel_height + self.font_size + self.pad

        if any(
            pt
            in (
                InterpolatableProblem.NOTHING,
                InterpolatableProblem.WRONG_START_POINT,
                InterpolatableProblem.CONTOUR_ORDER,
                InterpolatableProblem.KINK,
                InterpolatableProblem.UNDERWEIGHT,
                InterpolatableProblem.OVERWEIGHT,
            )
            for pt in problem_types
        ):
            x = self.pad + self.panel_width + self.pad
            y = self.pad
            y += self.title_font_size + self.pad * 2
            y += self.font_size + self.pad

            glyphset1 = self.glyphsets[master_indices[0]]
            glyphset2 = self.glyphsets[master_indices[1]]

            # Draw the mid-way of the two masters

            self.draw_label(
                "midway interpolation",
                x=x,
                y=y,
                color=self.head_color,
                width=self.panel_width,
                align=0.5,
            )
            y += self.font_size + self.pad

            midway_glyphset = LerpGlyphSet(glyphset1, glyphset2)
            self.draw_glyph(
                midway_glyphset,
                glyphname,
                [{"type": "midway"}]
                + [
                    p
                    for p in problems
                    if p["type"]
                    in (
                        InterpolatableProblem.KINK,
                        InterpolatableProblem.UNDERWEIGHT,
                        InterpolatableProblem.OVERWEIGHT,
                    )
                ],
                None,
                x=x,
                y=y,
                scale=min(scales),
            )

            y += self.panel_height + self.font_size + self.pad

        if any(
            pt
            in (
                InterpolatableProblem.WRONG_START_POINT,
                InterpolatableProblem.CONTOUR_ORDER,
                InterpolatableProblem.KINK,
            )
            for pt in problem_types
        ):
            # Draw the proposed fix

            self.draw_label(
                "proposed fix",
                x=x,
                y=y,
                color=self.head_color,
                width=self.panel_width,
                align=0.5,
            )
            y += self.font_size + self.pad

            overriding1 = OverridingDict(glyphset1)
            overriding2 = OverridingDict(glyphset2)
            perContourPen1 = PerContourOrComponentPen(
                RecordingPen, glyphset=overriding1
            )
            perContourPen2 = PerContourOrComponentPen(
                RecordingPen, glyphset=overriding2
            )
            glyphset1[glyphname].draw(perContourPen1)
            glyphset2[glyphname].draw(perContourPen2)

            for problem in problems:
                if problem["type"] == InterpolatableProblem.CONTOUR_ORDER:
                    fixed_contours = [
                        perContourPen2.value[i] for i in problems[0]["value_2"]
                    ]
                    perContourPen2.value = fixed_contours

            for problem in problems:
                if problem["type"] == InterpolatableProblem.WRONG_START_POINT:
                    # Save the wrong contours
                    wrongContour1 = perContourPen1.value[problem["contour"]]
                    wrongContour2 = perContourPen2.value[problem["contour"]]

                    # Convert the wrong contours to point pens
                    points1 = RecordingPointPen()
                    converter = SegmentToPointPen(points1, False)
                    wrongContour1.replay(converter)
                    points2 = RecordingPointPen()
                    converter = SegmentToPointPen(points2, False)
                    wrongContour2.replay(converter)

                    proposed_start = problem["value_2"]

                    # See if we need reversing; fragile but worth a try
                    if problem["reversed"]:
                        new_points2 = RecordingPointPen()
                        reversedPen = ReverseContourPointPen(new_points2)
                        points2.replay(reversedPen)
                        points2 = new_points2
                        proposed_start = len(points2.value) - 2 - proposed_start

                    # Rotate points2 so that the first point is the same as in points1
                    beginPath = points2.value[:1]
                    endPath = points2.value[-1:]
                    pts = points2.value[1:-1]
                    pts = pts[proposed_start:] + pts[:proposed_start]
                    points2.value = beginPath + pts + endPath

                    # Convert the point pens back to segment pens
                    segment1 = RecordingPen()
                    converter = PointToSegmentPen(segment1, True)
                    points1.replay(converter)
                    segment2 = RecordingPen()
                    converter = PointToSegmentPen(segment2, True)
                    points2.replay(converter)

                    # Replace the wrong contours
                    wrongContour1.value = segment1.value
                    wrongContour2.value = segment2.value
                    perContourPen1.value[problem["contour"]] = wrongContour1
                    perContourPen2.value[problem["contour"]] = wrongContour2

            for problem in problems:
                # If we have a kink, try to fix it.
                if problem["type"] == InterpolatableProblem.KINK:
                    # Save the wrong contours
                    wrongContour1 = perContourPen1.value[problem["contour"]]
                    wrongContour2 = perContourPen2.value[problem["contour"]]

                    # Convert the wrong contours to point pens
                    points1 = RecordingPointPen()
                    converter = SegmentToPointPen(points1, False)
                    wrongContour1.replay(converter)
                    points2 = RecordingPointPen()
                    converter = SegmentToPointPen(points2, False)
                    wrongContour2.replay(converter)

                    i = problem["value"]

                    # Position points to be around the same ratio
                    # beginPath / endPath dance
                    j = i + 1
                    pt0 = points1.value[j][1][0]
                    pt1 = points2.value[j][1][0]
                    j_prev = (i - 1) % (len(points1.value) - 2) + 1
                    pt0_prev = points1.value[j_prev][1][0]
                    pt1_prev = points2.value[j_prev][1][0]
                    j_next = (i + 1) % (len(points1.value) - 2) + 1
                    pt0_next = points1.value[j_next][1][0]
                    pt1_next = points2.value[j_next][1][0]

                    pt0 = complex(*pt0)
                    pt1 = complex(*pt1)
                    pt0_prev = complex(*pt0_prev)
                    pt1_prev = complex(*pt1_prev)
                    pt0_next = complex(*pt0_next)
                    pt1_next = complex(*pt1_next)

                    # Find the ratio of the distance between the points
                    r0 = abs(pt0 - pt0_prev) / abs(pt0_next - pt0_prev)
                    r1 = abs(pt1 - pt1_prev) / abs(pt1_next - pt1_prev)
                    r_mid = (r0 + r1) / 2

                    pt0 = pt0_prev + r_mid * (pt0_next - pt0_prev)
                    pt1 = pt1_prev + r_mid * (pt1_next - pt1_prev)

                    points1.value[j] = (
                        points1.value[j][0],
                        (((pt0.real, pt0.imag),) + points1.value[j][1][1:]),
                        points1.value[j][2],
                    )
                    points2.value[j] = (
                        points2.value[j][0],
                        (((pt1.real, pt1.imag),) + points2.value[j][1][1:]),
                        points2.value[j][2],
                    )

                    # Convert the point pens back to segment pens
                    segment1 = RecordingPen()
                    converter = PointToSegmentPen(segment1, True)
                    points1.replay(converter)
                    segment2 = RecordingPen()
                    converter = PointToSegmentPen(segment2, True)
                    points2.replay(converter)

                    # Replace the wrong contours
                    wrongContour1.value = segment1.value
                    wrongContour2.value = segment2.value

            # Assemble
            fixed1 = RecordingPen()
            fixed2 = RecordingPen()
            for contour in perContourPen1.value:
                fixed1.value.extend(contour.value)
            for contour in perContourPen2.value:
                fixed2.value.extend(contour.value)
            fixed1.draw = fixed1.replay
            fixed2.draw = fixed2.replay

            overriding1[glyphname] = fixed1
            overriding2[glyphname] = fixed2

            try:
                midway_glyphset = LerpGlyphSet(overriding1, overriding2)
                self.draw_glyph(
                    midway_glyphset,
                    glyphname,
                    {"type": "fixed"},
                    None,
                    x=x,
                    y=y,
                    scale=min(scales),
                )
            except ValueError:
                self.draw_emoticon(self.shrug, x=x, y=y)
            y += self.panel_height + self.pad

        else:
            emoticon = self.shrug
            if InterpolatableProblem.UNDERWEIGHT in problem_types:
                emoticon = self.underweight
            elif InterpolatableProblem.OVERWEIGHT in problem_types:
                emoticon = self.overweight
            elif InterpolatableProblem.NOTHING in problem_types:
                emoticon = self.yay
            self.draw_emoticon(emoticon, x=x, y=y)

        if show_page_number:
            self.draw_label(
                str(self.page_number),
                x=0,
                y=self.height - self.font_size - self.pad,
                width=self.width,
                color=self.head_color,
                align=0.5,
            )

    def draw_label(
        self,
        label,
        *,
        x=0,
        y=0,
        color=(0, 0, 0),
        align=0,
        bold=False,
        width=None,
        height=None,
        font_size=None,
    ):
        if width is None:
            width = self.width
        if height is None:
            height = self.height
        if font_size is None:
            font_size = self.font_size
        cr = cairo.Context(self.surface)
        cr.select_font_face(
            "@cairo:",
            cairo.FONT_SLANT_NORMAL,
            cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL,
        )
        cr.set_font_size(font_size)
        font_extents = cr.font_extents()
        font_size = font_size * font_size / font_extents[2]
        cr.set_font_size(font_size)
        font_extents = cr.font_extents()

        cr.set_source_rgb(*color)

        extents = cr.text_extents(label)
        if extents.width > width:
            # Shrink
            font_size *= width / extents.width
            cr.set_font_size(font_size)
            font_extents = cr.font_extents()
            extents = cr.text_extents(label)

        # Center
        label_x = x + (width - extents.width) * align
        label_y = y + font_extents[0]
        cr.move_to(label_x, label_y)
        cr.show_text(label)

    def draw_glyph(self, glyphset, glyphname, problems, which, *, x=0, y=0, scale=None):
        if type(problems) not in (list, tuple):
            problems = [problems]

        midway = any(problem["type"] == "midway" for problem in problems)
        problem_type = problems[0]["type"]
        problem_types = set(problem["type"] for problem in problems)
        if not all(pt == problem_type for pt in problem_types):
            problem_type = "mixed"
        glyph = glyphset[glyphname]

        recording = RecordingPen()
        glyph.draw(recording)
        decomposedRecording = DecomposingRecordingPen(glyphset)
        glyph.draw(decomposedRecording)

        boundsPen = ControlBoundsPen(glyphset)
        decomposedRecording.replay(boundsPen)
        bounds = boundsPen.bounds
        if bounds is None:
            bounds = (0, 0, 0, 0)

        glyph_width = bounds[2] - bounds[0]
        glyph_height = bounds[3] - bounds[1]

        if glyph_width:
            if scale is None:
                scale = self.panel_width / glyph_width
            else:
                scale = min(scale, self.panel_height / glyph_height)
        if glyph_height:
            if scale is None:
                scale = self.panel_height / glyph_height
            else:
                scale = min(scale, self.panel_height / glyph_height)
        if scale is None:
            scale = 1

        cr = cairo.Context(self.surface)
        cr.translate(x, y)
        # Center
        cr.translate(
            (self.panel_width - glyph_width * scale) / 2,
            (self.panel_height - glyph_height * scale) / 2,
        )
        cr.scale(scale, -scale)
        cr.translate(-bounds[0], -bounds[3])

        if self.border_color:
            cr.set_source_rgb(*self.border_color)
            cr.rectangle(bounds[0], bounds[1], glyph_width, glyph_height)
            cr.set_line_width(self.border_width / scale)
            cr.stroke()

        if self.fill_color or self.stroke_color:
            pen = CairoPen(glyphset, cr)
            decomposedRecording.replay(pen)

            if self.fill_color and problem_type != InterpolatableProblem.OPEN_PATH:
                cr.set_source_rgb(*self.fill_color)
                cr.fill_preserve()

            if self.stroke_color:
                cr.set_source_rgb(*self.stroke_color)
                cr.set_line_width(self.stroke_width / scale)
                cr.stroke_preserve()

            cr.new_path()

        if (
            InterpolatableProblem.UNDERWEIGHT in problem_types
            or InterpolatableProblem.OVERWEIGHT in problem_types
        ):
            perContourPen = PerContourOrComponentPen(RecordingPen, glyphset=glyphset)
            recording.replay(perContourPen)
            for problem in problems:
                if problem["type"] in (
                    InterpolatableProblem.UNDERWEIGHT,
                    InterpolatableProblem.OVERWEIGHT,
                ):
                    contour = perContourPen.value[problem["contour"]]
                    contour.replay(CairoPen(glyphset, cr))
                    cr.set_source_rgba(*self.weight_issue_contour_color)
                    cr.fill()

        if any(
            t in problem_types
            for t in {
                InterpolatableProblem.NOTHING,
                InterpolatableProblem.NODE_COUNT,
                InterpolatableProblem.NODE_INCOMPATIBILITY,
            }
        ):
            cr.set_line_cap(cairo.LINE_CAP_ROUND)

            # Oncurve nodes
            for segment, args in decomposedRecording.value:
                if not args:
                    continue
                x, y = args[-1]
                cr.move_to(x, y)
                cr.line_to(x, y)
            cr.set_source_rgba(*self.oncurve_node_color)
            cr.set_line_width(self.oncurve_node_diameter / scale)
            cr.stroke()

            # Offcurve nodes
            for segment, args in decomposedRecording.value:
                if not args:
                    continue
                for x, y in args[:-1]:
                    cr.move_to(x, y)
                    cr.line_to(x, y)
            cr.set_source_rgba(*self.offcurve_node_color)
            cr.set_line_width(self.offcurve_node_diameter / scale)
            cr.stroke()

            # Handles
            for segment, args in decomposedRecording.value:
                if not args:
                    pass
                elif segment in ("moveTo", "lineTo"):
                    cr.move_to(*args[0])
                elif segment == "qCurveTo":
                    for x, y in args:
                        cr.line_to(x, y)
                    cr.new_sub_path()
                    cr.move_to(*args[-1])
                elif segment == "curveTo":
                    cr.line_to(*args[0])
                    cr.new_sub_path()
                    cr.move_to(*args[1])
                    cr.line_to(*args[2])
                    cr.new_sub_path()
                    cr.move_to(*args[-1])
                else:
                    continue

            cr.set_source_rgba(*self.handle_color)
            cr.set_line_width(self.handle_width / scale)
            cr.stroke()

        matching = None
        for problem in problems:
            if problem["type"] == InterpolatableProblem.CONTOUR_ORDER:
                matching = problem["value_2"]
                colors = cycle(self.contour_colors)
                perContourPen = PerContourOrComponentPen(
                    RecordingPen, glyphset=glyphset
                )
                recording.replay(perContourPen)
                for i, contour in enumerate(perContourPen.value):
                    if matching[i] == i:
                        continue
                    color = next(colors)
                    contour.replay(CairoPen(glyphset, cr))
                    cr.set_source_rgba(*color, self.contour_alpha)
                    cr.fill()

        for problem in problems:
            if problem["type"] in (
                InterpolatableProblem.NOTHING,
                InterpolatableProblem.WRONG_START_POINT,
            ):
                idx = problem.get("contour")

                # Draw suggested point
                if idx is not None and which == 1 and "value_2" in problem:
                    perContourPen = PerContourOrComponentPen(
                        RecordingPen, glyphset=glyphset
                    )
                    decomposedRecording.replay(perContourPen)
                    points = SimpleRecordingPointPen()
                    converter = SegmentToPointPen(points, False)
                    perContourPen.value[
                        idx if matching is None else matching[idx]
                    ].replay(converter)
                    targetPoint = points.value[problem["value_2"]][0]
                    cr.save()
                    cr.translate(*targetPoint)
                    cr.scale(1 / scale, 1 / scale)
                    self.draw_dot(
                        cr,
                        diameter=self.corrected_start_point_size,
                        color=self.corrected_start_point_color,
                    )
                    cr.restore()

                # Draw start-point arrow
                if which == 0 or not problem.get("reversed"):
                    color = self.start_point_color
                else:
                    color = self.wrong_start_point_color
                first_pt = None
                i = 0
                cr.save()
                for segment, args in decomposedRecording.value:
                    if segment == "moveTo":
                        first_pt = args[0]
                        continue
                    if first_pt is None:
                        continue
                    if segment == "closePath":
                        second_pt = first_pt
                    else:
                        second_pt = args[0]

                    if idx is None or i == idx:
                        cr.save()
                        first_pt = complex(*first_pt)
                        second_pt = complex(*second_pt)
                        length = abs(second_pt - first_pt)
                        cr.translate(first_pt.real, first_pt.imag)
                        if length:
                            # Draw arrowhead
                            cr.rotate(
                                math.atan2(
                                    second_pt.imag - first_pt.imag,
                                    second_pt.real - first_pt.real,
                                )
                            )
                            cr.scale(1 / scale, 1 / scale)
                            self.draw_arrow(cr, color=color)
                        else:
                            # Draw circle
                            cr.scale(1 / scale, 1 / scale)
                            self.draw_dot(
                                cr,
                                diameter=self.corrected_start_point_size,
                                color=color,
                            )
                        cr.restore()

                        if idx is not None:
                            break

                    first_pt = None
                    i += 1

                cr.restore()

            if problem["type"] == InterpolatableProblem.KINK:
                idx = problem.get("contour")
                perContourPen = PerContourOrComponentPen(
                    RecordingPen, glyphset=glyphset
                )
                decomposedRecording.replay(perContourPen)
                points = SimpleRecordingPointPen()
                converter = SegmentToPointPen(points, False)
                perContourPen.value[idx if matching is None else matching[idx]].replay(
                    converter
                )

                targetPoint = points.value[problem["value"]][0]
                cr.save()
                cr.translate(*targetPoint)
                cr.scale(1 / scale, 1 / scale)
                if midway:
                    self.draw_circle(
                        cr,
                        diameter=self.kink_circle_size,
                        stroke_width=self.kink_circle_stroke_width,
                        color=self.kink_circle_color,
                    )
                else:
                    self.draw_dot(
                        cr,
                        diameter=self.kink_point_size,
                        color=self.kink_point_color,
                    )
                cr.restore()

        return scale

    def draw_dot(self, cr, *, x=0, y=0, color=(0, 0, 0), diameter=10):
        cr.save()
        cr.set_line_width(diameter)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.move_to(x, y)
        cr.line_to(x, y)
        if len(color) == 3:
            color = color + (1,)
        cr.set_source_rgba(*color)
        cr.stroke()
        cr.restore()

    def draw_circle(
        self, cr, *, x=0, y=0, color=(0, 0, 0), diameter=10, stroke_width=1
    ):
        cr.save()
        cr.set_line_width(stroke_width)
        cr.set_line_cap(cairo.LINE_CAP_SQUARE)
        cr.arc(x, y, diameter / 2, 0, 2 * math.pi)
        if len(color) == 3:
            color = color + (1,)
        cr.set_source_rgba(*color)
        cr.stroke()
        cr.restore()

    def draw_arrow(self, cr, *, x=0, y=0, color=(0, 0, 0)):
        cr.save()
        if len(color) == 3:
            color = color + (1,)
        cr.set_source_rgba(*color)
        cr.translate(self.start_arrow_length + x, y)
        cr.move_to(0, 0)
        cr.line_to(
            -self.start_arrow_length,
            -self.start_arrow_length * 0.4,
        )
        cr.line_to(
            -self.start_arrow_length,
            self.start_arrow_length * 0.4,
        )
        cr.close_path()
        cr.fill()
        cr.restore()

    def draw_text(self, text, *, x=0, y=0, color=(0, 0, 0), width=None, height=None):
        if width is None:
            width = self.width
        if height is None:
            height = self.height

        text = text.splitlines()
        cr = cairo.Context(self.surface)
        cr.set_source_rgb(*color)
        cr.set_font_size(self.font_size)
        cr.select_font_face(
            "@cairo:monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL
        )
        text_width = 0
        text_height = 0
        font_extents = cr.font_extents()
        font_font_size = font_extents[2]
        font_ascent = font_extents[0]
        for line in text:
            extents = cr.text_extents(line)
            text_width = max(text_width, extents.x_advance)
            text_height += font_font_size
        if not text_width:
            return
        cr.translate(x, y)
        scale = min(width / text_width, height / text_height)
        # center
        cr.translate(
            (width - text_width * scale) / 2, (height - text_height * scale) / 2
        )
        cr.scale(scale, scale)

        cr.translate(0, font_ascent)
        for line in text:
            cr.move_to(0, 0)
            cr.show_text(line)
            cr.translate(0, font_font_size)

    def draw_cupcake(self):
        self.draw_label(
            self.no_issues_label,
            x=self.pad,
            y=self.pad,
            color=self.no_issues_label_color,
            width=self.width - 2 * self.pad,
            align=0.5,
            bold=True,
            font_size=self.title_font_size,
        )

        self.draw_text(
            self.cupcake,
            x=self.pad,
            y=self.pad + self.font_size,
            width=self.width - 2 * self.pad,
            height=self.height - 2 * self.pad - self.font_size,
            color=self.cupcake_color,
        )

    def draw_emoticon(self, emoticon, x=0, y=0):
        self.draw_text(
            emoticon,
            x=x,
            y=y,
            color=self.emoticon_color,
            width=self.panel_width,
            height=self.panel_height,
        )


class InterpolatablePostscriptLike(InterpolatablePlot):
    def __exit__(self, type, value, traceback):
        self.surface.finish()

    def show_page(self):
        super().show_page()
        self.surface.show_page()


class InterpolatablePS(InterpolatablePostscriptLike):
    def __enter__(self):
        self.surface = cairo.PSSurface(self.out, self.width, self.height)
        return self


class InterpolatablePDF(InterpolatablePostscriptLike):
    def __enter__(self):
        self.surface = cairo.PDFSurface(self.out, self.width, self.height)
        self.surface.set_metadata(
            cairo.PDF_METADATA_CREATOR, "fonttools varLib.interpolatable"
        )
        self.surface.set_metadata(cairo.PDF_METADATA_CREATE_DATE, "")
        return self


class InterpolatableSVG(InterpolatablePlot):
    def __enter__(self):
        self.sink = BytesIO()
        self.surface = cairo.SVGSurface(self.sink, self.width, self.height)
        return self

    def __exit__(self, type, value, traceback):
        if self.surface is not None:
            self.show_page()

    def show_page(self):
        super().show_page()
        self.surface.finish()
        self.out.append(self.sink.getvalue())
        self.sink = BytesIO()
        self.surface = cairo.SVGSurface(self.sink, self.width, self.height)
