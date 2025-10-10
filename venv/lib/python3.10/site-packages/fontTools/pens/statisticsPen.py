"""Pen calculating area, center of mass, variance and standard-deviation,
covariance and correlation, and slant, of glyph shapes."""

from math import sqrt, degrees, atan
from fontTools.pens.basePen import BasePen, OpenContourError
from fontTools.pens.momentsPen import MomentsPen

__all__ = ["StatisticsPen", "StatisticsControlPen"]


class StatisticsBase:
    def __init__(self):
        self._zero()

    def _zero(self):
        self.area = 0
        self.meanX = 0
        self.meanY = 0
        self.varianceX = 0
        self.varianceY = 0
        self.stddevX = 0
        self.stddevY = 0
        self.covariance = 0
        self.correlation = 0
        self.slant = 0

    def _update(self):
        # XXX The variance formulas should never produce a negative value,
        # but due to reasons I don't understand, both of our pens do.
        # So we take the absolute value here.
        self.varianceX = abs(self.varianceX)
        self.varianceY = abs(self.varianceY)

        self.stddevX = stddevX = sqrt(self.varianceX)
        self.stddevY = stddevY = sqrt(self.varianceY)

        # Correlation(X,Y) = Covariance(X,Y) / ( stddev(X) * stddev(Y) )
        # https://en.wikipedia.org/wiki/Pearson_product-moment_correlation_coefficient
        if stddevX * stddevY == 0:
            correlation = float("NaN")
        else:
            # XXX The above formula should never produce a value outside
            # the range [-1, 1], but due to reasons I don't understand,
            # (probably the same issue as above), it does. So we clamp.
            correlation = self.covariance / (stddevX * stddevY)
            correlation = max(-1, min(1, correlation))
        self.correlation = correlation if abs(correlation) > 1e-3 else 0

        slant = (
            self.covariance / self.varianceY if self.varianceY != 0 else float("NaN")
        )
        self.slant = slant if abs(slant) > 1e-3 else 0


class StatisticsPen(StatisticsBase, MomentsPen):
    """Pen calculating area, center of mass, variance and
    standard-deviation, covariance and correlation, and slant,
    of glyph shapes.

    Note that if the glyph shape is self-intersecting, the values
    are not correct (but well-defined). Moreover, area will be
    negative if contour directions are clockwise."""

    def __init__(self, glyphset=None):
        MomentsPen.__init__(self, glyphset=glyphset)
        StatisticsBase.__init__(self)

    def _closePath(self):
        MomentsPen._closePath(self)
        self._update()

    def _update(self):
        area = self.area
        if not area:
            self._zero()
            return

        # Center of mass
        # https://en.wikipedia.org/wiki/Center_of_mass#A_continuous_volume
        self.meanX = meanX = self.momentX / area
        self.meanY = meanY = self.momentY / area

        # Var(X) = E[X^2] - E[X]^2
        self.varianceX = self.momentXX / area - meanX * meanX
        self.varianceY = self.momentYY / area - meanY * meanY

        # Covariance(X,Y) = (E[X.Y] - E[X]E[Y])
        self.covariance = self.momentXY / area - meanX * meanY

        StatisticsBase._update(self)


class StatisticsControlPen(StatisticsBase, BasePen):
    """Pen calculating area, center of mass, variance and
    standard-deviation, covariance and correlation, and slant,
    of glyph shapes, using the control polygon only.

    Note that if the glyph shape is self-intersecting, the values
    are not correct (but well-defined). Moreover, area will be
    negative if contour directions are clockwise."""

    def __init__(self, glyphset=None):
        BasePen.__init__(self, glyphset)
        StatisticsBase.__init__(self)
        self._nodes = []

    def _moveTo(self, pt):
        self._nodes.append(complex(*pt))
        self._startPoint = pt

    def _lineTo(self, pt):
        self._nodes.append(complex(*pt))

    def _qCurveToOne(self, pt1, pt2):
        for pt in (pt1, pt2):
            self._nodes.append(complex(*pt))

    def _curveToOne(self, pt1, pt2, pt3):
        for pt in (pt1, pt2, pt3):
            self._nodes.append(complex(*pt))

    def _closePath(self):
        p0 = self._getCurrentPoint()
        if p0 != self._startPoint:
            self._lineTo(self._startPoint)
        self._update()

    def _endPath(self):
        p0 = self._getCurrentPoint()
        if p0 != self._startPoint:
            raise OpenContourError("Glyph statistics not defined on open contours.")
        self._update()

    def _update(self):
        nodes = self._nodes
        n = len(nodes)

        # Triangle formula
        self.area = (
            sum(
                (p0.real * p1.imag - p1.real * p0.imag)
                for p0, p1 in zip(nodes, nodes[1:] + nodes[:1])
            )
            / 2
        )

        # Center of mass
        # https://en.wikipedia.org/wiki/Center_of_mass#A_system_of_particles
        sumNodes = sum(nodes)
        self.meanX = meanX = sumNodes.real / n
        self.meanY = meanY = sumNodes.imag / n

        if n > 1:
            # Var(X) = (sum[X^2] - sum[X]^2 / n) / (n - 1)
            # https://www.statisticshowto.com/probability-and-statistics/descriptive-statistics/sample-variance/
            self.varianceX = varianceX = (
                sum(p.real * p.real for p in nodes)
                - (sumNodes.real * sumNodes.real) / n
            ) / (n - 1)
            self.varianceY = varianceY = (
                sum(p.imag * p.imag for p in nodes)
                - (sumNodes.imag * sumNodes.imag) / n
            ) / (n - 1)

            # Covariance(X,Y) = (sum[X.Y] - sum[X].sum[Y] / n) / (n - 1)
            self.covariance = covariance = (
                sum(p.real * p.imag for p in nodes)
                - (sumNodes.real * sumNodes.imag) / n
            ) / (n - 1)
        else:
            self.varianceX = varianceX = 0
            self.varianceY = varianceY = 0
            self.covariance = covariance = 0

        StatisticsBase._update(self)


def _test(glyphset, upem, glyphs, quiet=False, *, control=False):
    from fontTools.pens.transformPen import TransformPen
    from fontTools.misc.transform import Scale

    wght_sum = 0
    wght_sum_perceptual = 0
    wdth_sum = 0
    slnt_sum = 0
    slnt_sum_perceptual = 0
    for glyph_name in glyphs:
        glyph = glyphset[glyph_name]
        if control:
            pen = StatisticsControlPen(glyphset=glyphset)
        else:
            pen = StatisticsPen(glyphset=glyphset)
        transformer = TransformPen(pen, Scale(1.0 / upem))
        glyph.draw(transformer)

        area = abs(pen.area)
        width = glyph.width
        wght_sum += area
        wght_sum_perceptual += pen.area * width
        wdth_sum += width
        slnt_sum += pen.slant
        slnt_sum_perceptual += pen.slant * width

        if quiet:
            continue

        print()
        print("glyph:", glyph_name)

        for item in [
            "area",
            "momentX",
            "momentY",
            "momentXX",
            "momentYY",
            "momentXY",
            "meanX",
            "meanY",
            "varianceX",
            "varianceY",
            "stddevX",
            "stddevY",
            "covariance",
            "correlation",
            "slant",
        ]:
            print("%s: %g" % (item, getattr(pen, item)))

    if not quiet:
        print()
        print("font:")

    print("weight: %g" % (wght_sum * upem / wdth_sum))
    print("weight (perceptual): %g" % (wght_sum_perceptual / wdth_sum))
    print("width:  %g" % (wdth_sum / upem / len(glyphs)))
    slant = slnt_sum / len(glyphs)
    print("slant:  %g" % slant)
    print("slant angle:  %g" % -degrees(atan(slant)))
    slant_perceptual = slnt_sum_perceptual / wdth_sum
    print("slant (perceptual):  %g" % slant_perceptual)
    print("slant (perceptual) angle:  %g" % -degrees(atan(slant_perceptual)))


def main(args):
    """Report font glyph shape geometricsl statistics"""

    if args is None:
        import sys

        args = sys.argv[1:]

    import argparse

    parser = argparse.ArgumentParser(
        "fonttools pens.statisticsPen",
        description="Report font glyph shape geometricsl statistics",
    )
    parser.add_argument("font", metavar="font.ttf", help="Font file.")
    parser.add_argument("glyphs", metavar="glyph-name", help="Glyph names.", nargs="*")
    parser.add_argument(
        "-y",
        metavar="<number>",
        help="Face index into a collection to open. Zero based.",
    )
    parser.add_argument(
        "-c",
        "--control",
        action="store_true",
        help="Use the control-box pen instead of the Green therem.",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Only report font-wide statistics."
    )
    parser.add_argument(
        "--variations",
        metavar="AXIS=LOC",
        default="",
        help="List of space separated locations. A location consist in "
        "the name of a variation axis, followed by '=' and a number. E.g.: "
        "wght=700 wdth=80. The default is the location of the base master.",
    )

    options = parser.parse_args(args)

    glyphs = options.glyphs
    fontNumber = int(options.y) if options.y is not None else 0

    location = {}
    for tag_v in options.variations.split():
        fields = tag_v.split("=")
        tag = fields[0].strip()
        v = int(fields[1])
        location[tag] = v

    from fontTools.ttLib import TTFont

    font = TTFont(options.font, fontNumber=fontNumber)
    if not glyphs:
        glyphs = font.getGlyphOrder()
    _test(
        font.getGlyphSet(location=location),
        font["head"].unitsPerEm,
        glyphs,
        quiet=options.quiet,
        control=options.control,
    )


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])
