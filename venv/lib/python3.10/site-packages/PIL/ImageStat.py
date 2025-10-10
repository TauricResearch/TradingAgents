#
# The Python Imaging Library.
# $Id$
#
# global image statistics
#
# History:
# 1996-04-05 fl   Created
# 1997-05-21 fl   Added mask; added rms, var, stddev attributes
# 1997-08-05 fl   Added median
# 1998-07-05 hk   Fixed integer overflow error
#
# Notes:
# This class shows how to implement delayed evaluation of attributes.
# To get a certain value, simply access the corresponding attribute.
# The __getattr__ dispatcher takes care of the rest.
#
# Copyright (c) Secret Labs AB 1997.
# Copyright (c) Fredrik Lundh 1996-97.
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import math
from functools import cached_property

from . import Image


class Stat:
    def __init__(
        self, image_or_list: Image.Image | list[int], mask: Image.Image | None = None
    ) -> None:
        """
        Calculate statistics for the given image. If a mask is included,
        only the regions covered by that mask are included in the
        statistics. You can also pass in a previously calculated histogram.

        :param image: A PIL image, or a precalculated histogram.

            .. note::

                For a PIL image, calculations rely on the
                :py:meth:`~PIL.Image.Image.histogram` method. The pixel counts are
                grouped into 256 bins, even if the image has more than 8 bits per
                channel. So ``I`` and ``F`` mode images have a maximum ``mean``,
                ``median`` and ``rms`` of 255, and cannot have an ``extrema`` maximum
                of more than 255.

        :param mask: An optional mask.
        """
        if isinstance(image_or_list, Image.Image):
            self.h = image_or_list.histogram(mask)
        elif isinstance(image_or_list, list):
            self.h = image_or_list
        else:
            msg = "first argument must be image or list"  # type: ignore[unreachable]
            raise TypeError(msg)
        self.bands = list(range(len(self.h) // 256))

    @cached_property
    def extrema(self) -> list[tuple[int, int]]:
        """
        Min/max values for each band in the image.

        .. note::
            This relies on the :py:meth:`~PIL.Image.Image.histogram` method, and
            simply returns the low and high bins used. This is correct for
            images with 8 bits per channel, but fails for other modes such as
            ``I`` or ``F``. Instead, use :py:meth:`~PIL.Image.Image.getextrema` to
            return per-band extrema for the image. This is more correct and
            efficient because, for non-8-bit modes, the histogram method uses
            :py:meth:`~PIL.Image.Image.getextrema` to determine the bins used.
        """

        def minmax(histogram: list[int]) -> tuple[int, int]:
            res_min, res_max = 255, 0
            for i in range(256):
                if histogram[i]:
                    res_min = i
                    break
            for i in range(255, -1, -1):
                if histogram[i]:
                    res_max = i
                    break
            return res_min, res_max

        return [minmax(self.h[i:]) for i in range(0, len(self.h), 256)]

    @cached_property
    def count(self) -> list[int]:
        """Total number of pixels for each band in the image."""
        return [sum(self.h[i : i + 256]) for i in range(0, len(self.h), 256)]

    @cached_property
    def sum(self) -> list[float]:
        """Sum of all pixels for each band in the image."""

        v = []
        for i in range(0, len(self.h), 256):
            layer_sum = 0.0
            for j in range(256):
                layer_sum += j * self.h[i + j]
            v.append(layer_sum)
        return v

    @cached_property
    def sum2(self) -> list[float]:
        """Squared sum of all pixels for each band in the image."""

        v = []
        for i in range(0, len(self.h), 256):
            sum2 = 0.0
            for j in range(256):
                sum2 += (j**2) * float(self.h[i + j])
            v.append(sum2)
        return v

    @cached_property
    def mean(self) -> list[float]:
        """Average (arithmetic mean) pixel level for each band in the image."""
        return [self.sum[i] / self.count[i] for i in self.bands]

    @cached_property
    def median(self) -> list[int]:
        """Median pixel level for each band in the image."""

        v = []
        for i in self.bands:
            s = 0
            half = self.count[i] // 2
            b = i * 256
            for j in range(256):
                s = s + self.h[b + j]
                if s > half:
                    break
            v.append(j)
        return v

    @cached_property
    def rms(self) -> list[float]:
        """RMS (root-mean-square) for each band in the image."""
        return [math.sqrt(self.sum2[i] / self.count[i]) for i in self.bands]

    @cached_property
    def var(self) -> list[float]:
        """Variance for each band in the image."""
        return [
            (self.sum2[i] - (self.sum[i] ** 2.0) / self.count[i]) / self.count[i]
            for i in self.bands
        ]

    @cached_property
    def stddev(self) -> list[float]:
        """Standard deviation for each band in the image."""
        return [math.sqrt(self.var[i]) for i in self.bands]


Global = Stat  # compatibility
