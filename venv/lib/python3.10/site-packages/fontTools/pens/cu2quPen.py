# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import operator
from fontTools.cu2qu import curve_to_quadratic, curves_to_quadratic
from fontTools.pens.basePen import decomposeSuperBezierSegment
from fontTools.pens.filterPen import FilterPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.pointPen import BasePointToSegmentPen
from fontTools.pens.pointPen import ReverseContourPointPen


class Cu2QuPen(FilterPen):
    """A filter pen to convert cubic bezier curves to quadratic b-splines
    using the FontTools SegmentPen protocol.

    Args:

        other_pen: another SegmentPen used to draw the transformed outline.
        max_err: maximum approximation error in font units. For optimal results,
            if you know the UPEM of the font, we recommend setting this to a
            value equal, or close to UPEM / 1000.
        reverse_direction: flip the contours' direction but keep starting point.
        stats: a dictionary counting the point numbers of quadratic segments.
        all_quadratic: if True (default), only quadratic b-splines are generated.
            if False, quadratic curves or cubic curves are generated depending
            on which one is more economical.
    """

    def __init__(
        self,
        other_pen,
        max_err,
        reverse_direction=False,
        stats=None,
        all_quadratic=True,
    ):
        if reverse_direction:
            other_pen = ReverseContourPen(other_pen)
        super().__init__(other_pen)
        self.max_err = max_err
        self.stats = stats
        self.all_quadratic = all_quadratic

    def _convert_curve(self, pt1, pt2, pt3):
        curve = (self.current_pt, pt1, pt2, pt3)
        result = curve_to_quadratic(curve, self.max_err, self.all_quadratic)
        if self.stats is not None:
            n = str(len(result) - 2)
            self.stats[n] = self.stats.get(n, 0) + 1
        if self.all_quadratic:
            self.qCurveTo(*result[1:])
        else:
            if len(result) == 3:
                self.qCurveTo(*result[1:])
            else:
                assert len(result) == 4
                super().curveTo(*result[1:])

    def curveTo(self, *points):
        n = len(points)
        if n == 3:
            # this is the most common case, so we special-case it
            self._convert_curve(*points)
        elif n > 3:
            for segment in decomposeSuperBezierSegment(points):
                self._convert_curve(*segment)
        else:
            self.qCurveTo(*points)


class Cu2QuPointPen(BasePointToSegmentPen):
    """A filter pen to convert cubic bezier curves to quadratic b-splines
    using the FontTools PointPen protocol.

    Args:
        other_point_pen: another PointPen used to draw the transformed outline.
        max_err: maximum approximation error in font units. For optimal results,
            if you know the UPEM of the font, we recommend setting this to a
            value equal, or close to UPEM / 1000.
        reverse_direction: reverse the winding direction of all contours.
        stats: a dictionary counting the point numbers of quadratic segments.
        all_quadratic: if True (default), only quadratic b-splines are generated.
            if False, quadratic curves or cubic curves are generated depending
            on which one is more economical.
    """

    __points_required = {
        "move": (1, operator.eq),
        "line": (1, operator.eq),
        "qcurve": (2, operator.ge),
        "curve": (3, operator.eq),
    }

    def __init__(
        self,
        other_point_pen,
        max_err,
        reverse_direction=False,
        stats=None,
        all_quadratic=True,
    ):
        BasePointToSegmentPen.__init__(self)
        if reverse_direction:
            self.pen = ReverseContourPointPen(other_point_pen)
        else:
            self.pen = other_point_pen
        self.max_err = max_err
        self.stats = stats
        self.all_quadratic = all_quadratic

    def _flushContour(self, segments):
        assert len(segments) >= 1
        closed = segments[0][0] != "move"
        new_segments = []
        prev_points = segments[-1][1]
        prev_on_curve = prev_points[-1][0]
        for segment_type, points in segments:
            if segment_type == "curve":
                for sub_points in self._split_super_bezier_segments(points):
                    on_curve, smooth, name, kwargs = sub_points[-1]
                    bcp1, bcp2 = sub_points[0][0], sub_points[1][0]
                    cubic = [prev_on_curve, bcp1, bcp2, on_curve]
                    quad = curve_to_quadratic(cubic, self.max_err, self.all_quadratic)
                    if self.stats is not None:
                        n = str(len(quad) - 2)
                        self.stats[n] = self.stats.get(n, 0) + 1
                    new_points = [(pt, False, None, {}) for pt in quad[1:-1]]
                    new_points.append((on_curve, smooth, name, kwargs))
                    if self.all_quadratic or len(new_points) == 2:
                        new_segments.append(["qcurve", new_points])
                    else:
                        new_segments.append(["curve", new_points])
                    prev_on_curve = sub_points[-1][0]
            else:
                new_segments.append([segment_type, points])
                prev_on_curve = points[-1][0]
        if closed:
            # the BasePointToSegmentPen.endPath method that calls _flushContour
            # rotates the point list of closed contours so that they end with
            # the first on-curve point. We restore the original starting point.
            new_segments = new_segments[-1:] + new_segments[:-1]
        self._drawPoints(new_segments)

    def _split_super_bezier_segments(self, points):
        sub_segments = []
        # n is the number of control points
        n = len(points) - 1
        if n == 2:
            # a simple bezier curve segment
            sub_segments.append(points)
        elif n > 2:
            # a "super" bezier; decompose it
            on_curve, smooth, name, kwargs = points[-1]
            num_sub_segments = n - 1
            for i, sub_points in enumerate(
                decomposeSuperBezierSegment([pt for pt, _, _, _ in points])
            ):
                new_segment = []
                for point in sub_points[:-1]:
                    new_segment.append((point, False, None, {}))
                if i == (num_sub_segments - 1):
                    # the last on-curve keeps its original attributes
                    new_segment.append((on_curve, smooth, name, kwargs))
                else:
                    # on-curves of sub-segments are always "smooth"
                    new_segment.append((sub_points[-1], True, None, {}))
                sub_segments.append(new_segment)
        else:
            raise AssertionError("expected 2 control points, found: %d" % n)
        return sub_segments

    def _drawPoints(self, segments):
        pen = self.pen
        pen.beginPath()
        last_offcurves = []
        points_required = self.__points_required
        for i, (segment_type, points) in enumerate(segments):
            if segment_type in points_required:
                n, op = points_required[segment_type]
                assert op(len(points), n), (
                    f"illegal {segment_type!r} segment point count: "
                    f"expected {n}, got {len(points)}"
                )
                offcurves = points[:-1]
                if i == 0:
                    # any off-curve points preceding the first on-curve
                    # will be appended at the end of the contour
                    last_offcurves = offcurves
                else:
                    for pt, smooth, name, kwargs in offcurves:
                        pen.addPoint(pt, None, smooth, name, **kwargs)
                pt, smooth, name, kwargs = points[-1]
                if pt is None:
                    assert segment_type == "qcurve"
                    # special quadratic contour with no on-curve points:
                    # we need to skip the "None" point. See also the Pen
                    # protocol's qCurveTo() method and fontTools.pens.basePen
                    pass
                else:
                    pen.addPoint(pt, segment_type, smooth, name, **kwargs)
            else:
                raise AssertionError("unexpected segment type: %r" % segment_type)
        for pt, smooth, name, kwargs in last_offcurves:
            pen.addPoint(pt, None, smooth, name, **kwargs)
        pen.endPath()

    def addComponent(self, baseGlyphName, transformation):
        assert self.currentPath is None
        self.pen.addComponent(baseGlyphName, transformation)


class Cu2QuMultiPen:
    """A filter multi-pen to convert cubic bezier curves to quadratic b-splines
    in a interpolation-compatible manner, using the FontTools SegmentPen protocol.

    Args:

        other_pens: list of SegmentPens used to draw the transformed outlines.
        max_err: maximum approximation error in font units. For optimal results,
            if you know the UPEM of the font, we recommend setting this to a
            value equal, or close to UPEM / 1000.
        reverse_direction: flip the contours' direction but keep starting point.

    This pen does not follow the normal SegmentPen protocol. Instead, its
    moveTo/lineTo/qCurveTo/curveTo methods take a list of tuples that are
    arguments that would normally be passed to a SegmentPen, one item for
    each of the pens in other_pens.
    """

    # TODO Simplify like 3e8ebcdce592fe8a59ca4c3a294cc9724351e1ce
    # Remove start_pts and _add_moveTO

    def __init__(self, other_pens, max_err, reverse_direction=False):
        if reverse_direction:
            other_pens = [
                ReverseContourPen(pen, outputImpliedClosingLine=True)
                for pen in other_pens
            ]
        self.pens = other_pens
        self.max_err = max_err
        self.start_pts = None
        self.current_pts = None

    def _check_contour_is_open(self):
        if self.current_pts is None:
            raise AssertionError("moveTo is required")

    def _check_contour_is_closed(self):
        if self.current_pts is not None:
            raise AssertionError("closePath or endPath is required")

    def _add_moveTo(self):
        if self.start_pts is not None:
            for pt, pen in zip(self.start_pts, self.pens):
                pen.moveTo(*pt)
            self.start_pts = None

    def moveTo(self, pts):
        self._check_contour_is_closed()
        self.start_pts = self.current_pts = pts
        self._add_moveTo()

    def lineTo(self, pts):
        self._check_contour_is_open()
        self._add_moveTo()
        for pt, pen in zip(pts, self.pens):
            pen.lineTo(*pt)
        self.current_pts = pts

    def qCurveTo(self, pointsList):
        self._check_contour_is_open()
        if len(pointsList[0]) == 1:
            self.lineTo([(points[0],) for points in pointsList])
            return
        self._add_moveTo()
        current_pts = []
        for points, pen in zip(pointsList, self.pens):
            pen.qCurveTo(*points)
            current_pts.append((points[-1],))
        self.current_pts = current_pts

    def _curves_to_quadratic(self, pointsList):
        curves = []
        for current_pt, points in zip(self.current_pts, pointsList):
            curves.append(current_pt + points)
        quadratics = curves_to_quadratic(curves, [self.max_err] * len(curves))
        pointsList = []
        for quadratic in quadratics:
            pointsList.append(quadratic[1:])
        self.qCurveTo(pointsList)

    def curveTo(self, pointsList):
        self._check_contour_is_open()
        self._curves_to_quadratic(pointsList)

    def closePath(self):
        self._check_contour_is_open()
        if self.start_pts is None:
            for pen in self.pens:
                pen.closePath()
        self.current_pts = self.start_pts = None

    def endPath(self):
        self._check_contour_is_open()
        if self.start_pts is None:
            for pen in self.pens:
                pen.endPath()
        self.current_pts = self.start_pts = None

    def addComponent(self, glyphName, transformations):
        self._check_contour_is_closed()
        for trans, pen in zip(transformations, self.pens):
            pen.addComponent(glyphName, trans)
