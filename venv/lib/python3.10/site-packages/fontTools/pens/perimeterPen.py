# -*- coding: utf-8 -*-
"""Calculate the perimeter of a glyph."""

from fontTools.pens.basePen import BasePen
from fontTools.misc.bezierTools import (
    approximateQuadraticArcLengthC,
    calcQuadraticArcLengthC,
    approximateCubicArcLengthC,
    calcCubicArcLengthC,
)
import math


__all__ = ["PerimeterPen"]


def _distance(p0, p1):
    return math.hypot(p0[0] - p1[0], p0[1] - p1[1])


class PerimeterPen(BasePen):
    def __init__(self, glyphset=None, tolerance=0.005):
        BasePen.__init__(self, glyphset)
        self.value = 0
        self.tolerance = tolerance

        # Choose which algorithm to use for quadratic and for cubic.
        # Quadrature is faster but has fixed error characteristic with no strong
        # error bound.  The cutoff points are derived empirically.
        self._addCubic = (
            self._addCubicQuadrature if tolerance >= 0.0015 else self._addCubicRecursive
        )
        self._addQuadratic = (
            self._addQuadraticQuadrature
            if tolerance >= 0.00075
            else self._addQuadraticExact
        )

    def _moveTo(self, p0):
        self.__startPoint = p0

    def _closePath(self):
        p0 = self._getCurrentPoint()
        if p0 != self.__startPoint:
            self._lineTo(self.__startPoint)

    def _lineTo(self, p1):
        p0 = self._getCurrentPoint()
        self.value += _distance(p0, p1)

    def _addQuadraticExact(self, c0, c1, c2):
        self.value += calcQuadraticArcLengthC(c0, c1, c2)

    def _addQuadraticQuadrature(self, c0, c1, c2):
        self.value += approximateQuadraticArcLengthC(c0, c1, c2)

    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        self._addQuadratic(complex(*p0), complex(*p1), complex(*p2))

    def _addCubicRecursive(self, c0, c1, c2, c3):
        self.value += calcCubicArcLengthC(c0, c1, c2, c3, self.tolerance)

    def _addCubicQuadrature(self, c0, c1, c2, c3):
        self.value += approximateCubicArcLengthC(c0, c1, c2, c3)

    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        self._addCubic(complex(*p0), complex(*p1), complex(*p2), complex(*p3))
