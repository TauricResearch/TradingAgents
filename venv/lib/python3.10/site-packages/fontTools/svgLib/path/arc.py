"""Convert SVG Path's elliptical arcs to Bezier curves.

The code is mostly adapted from Blink's SVGPathNormalizer::DecomposeArcToCubic
https://github.com/chromium/chromium/blob/93831f2/third_party/
blink/renderer/core/svg/svg_path_parser.cc#L169-L278
"""

from fontTools.misc.transform import Identity, Scale
from math import atan2, ceil, cos, fabs, isfinite, pi, radians, sin, sqrt, tan


TWO_PI = 2 * pi
PI_OVER_TWO = 0.5 * pi


def _map_point(matrix, pt):
    # apply Transform matrix to a point represented as a complex number
    r = matrix.transformPoint((pt.real, pt.imag))
    return r[0] + r[1] * 1j


class EllipticalArc(object):
    def __init__(self, current_point, rx, ry, rotation, large, sweep, target_point):
        self.current_point = current_point
        self.rx = rx
        self.ry = ry
        self.rotation = rotation
        self.large = large
        self.sweep = sweep
        self.target_point = target_point

        # SVG arc's rotation angle is expressed in degrees, whereas Transform.rotate
        # uses radians
        self.angle = radians(rotation)

        # these derived attributes are computed by the _parametrize method
        self.center_point = self.theta1 = self.theta2 = self.theta_arc = None

    def _parametrize(self):
        # convert from endopoint to center parametrization:
        # https://www.w3.org/TR/SVG/implnote.html#ArcConversionEndpointToCenter

        # If rx = 0 or ry = 0 then this arc is treated as a straight line segment (a
        # "lineto") joining the endpoints.
        # http://www.w3.org/TR/SVG/implnote.html#ArcOutOfRangeParameters
        rx = fabs(self.rx)
        ry = fabs(self.ry)
        if not (rx and ry):
            return False

        # If the current point and target point for the arc are identical, it should
        # be treated as a zero length path. This ensures continuity in animations.
        if self.target_point == self.current_point:
            return False

        mid_point_distance = (self.current_point - self.target_point) * 0.5

        point_transform = Identity.rotate(-self.angle)

        transformed_mid_point = _map_point(point_transform, mid_point_distance)
        square_rx = rx * rx
        square_ry = ry * ry
        square_x = transformed_mid_point.real * transformed_mid_point.real
        square_y = transformed_mid_point.imag * transformed_mid_point.imag

        # Check if the radii are big enough to draw the arc, scale radii if not.
        # http://www.w3.org/TR/SVG/implnote.html#ArcCorrectionOutOfRangeRadii
        radii_scale = square_x / square_rx + square_y / square_ry
        if radii_scale > 1:
            rx *= sqrt(radii_scale)
            ry *= sqrt(radii_scale)
            self.rx, self.ry = rx, ry

        point_transform = Scale(1 / rx, 1 / ry).rotate(-self.angle)

        point1 = _map_point(point_transform, self.current_point)
        point2 = _map_point(point_transform, self.target_point)
        delta = point2 - point1

        d = delta.real * delta.real + delta.imag * delta.imag
        scale_factor_squared = max(1 / d - 0.25, 0.0)

        scale_factor = sqrt(scale_factor_squared)
        if self.sweep == self.large:
            scale_factor = -scale_factor

        delta *= scale_factor
        center_point = (point1 + point2) * 0.5
        center_point += complex(-delta.imag, delta.real)
        point1 -= center_point
        point2 -= center_point

        theta1 = atan2(point1.imag, point1.real)
        theta2 = atan2(point2.imag, point2.real)

        theta_arc = theta2 - theta1
        if theta_arc < 0 and self.sweep:
            theta_arc += TWO_PI
        elif theta_arc > 0 and not self.sweep:
            theta_arc -= TWO_PI

        self.theta1 = theta1
        self.theta2 = theta1 + theta_arc
        self.theta_arc = theta_arc
        self.center_point = center_point

        return True

    def _decompose_to_cubic_curves(self):
        if self.center_point is None and not self._parametrize():
            return

        point_transform = Identity.rotate(self.angle).scale(self.rx, self.ry)

        # Some results of atan2 on some platform implementations are not exact
        # enough. So that we get more cubic curves than expected here. Adding 0.001f
        # reduces the count of sgements to the correct count.
        num_segments = int(ceil(fabs(self.theta_arc / (PI_OVER_TWO + 0.001))))
        for i in range(num_segments):
            start_theta = self.theta1 + i * self.theta_arc / num_segments
            end_theta = self.theta1 + (i + 1) * self.theta_arc / num_segments

            t = (4 / 3) * tan(0.25 * (end_theta - start_theta))
            if not isfinite(t):
                return

            sin_start_theta = sin(start_theta)
            cos_start_theta = cos(start_theta)
            sin_end_theta = sin(end_theta)
            cos_end_theta = cos(end_theta)

            point1 = complex(
                cos_start_theta - t * sin_start_theta,
                sin_start_theta + t * cos_start_theta,
            )
            point1 += self.center_point
            target_point = complex(cos_end_theta, sin_end_theta)
            target_point += self.center_point
            point2 = target_point
            point2 += complex(t * sin_end_theta, -t * cos_end_theta)

            point1 = _map_point(point_transform, point1)
            point2 = _map_point(point_transform, point2)
            target_point = _map_point(point_transform, target_point)

            yield point1, point2, target_point

    def draw(self, pen):
        for point1, point2, target_point in self._decompose_to_cubic_curves():
            pen.curveTo(
                (point1.real, point1.imag),
                (point2.real, point2.imag),
                (target_point.real, target_point.imag),
            )
