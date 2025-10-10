#
# The Python Imaging Library.
# $Id$
#
# transform wrappers
#
# History:
# 2002-04-08 fl   Created
#
# Copyright (c) 2002 by Secret Labs AB
# Copyright (c) 2002 by Fredrik Lundh
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from . import Image


class Transform(Image.ImageTransformHandler):
    """Base class for other transforms defined in :py:mod:`~PIL.ImageTransform`."""

    method: Image.Transform

    def __init__(self, data: Sequence[Any]) -> None:
        self.data = data

    def getdata(self) -> tuple[Image.Transform, Sequence[int]]:
        return self.method, self.data

    def transform(
        self,
        size: tuple[int, int],
        image: Image.Image,
        **options: Any,
    ) -> Image.Image:
        """Perform the transform. Called from :py:meth:`.Image.transform`."""
        # can be overridden
        method, data = self.getdata()
        return image.transform(size, method, data, **options)


class AffineTransform(Transform):
    """
    Define an affine image transform.

    This function takes a 6-tuple (a, b, c, d, e, f) which contain the first
    two rows from the inverse of an affine transform matrix. For each pixel
    (x, y) in the output image, the new value is taken from a position (a x +
    b y + c, d x + e y + f) in the input image, rounded to nearest pixel.

    This function can be used to scale, translate, rotate, and shear the
    original image.

    See :py:meth:`.Image.transform`

    :param matrix: A 6-tuple (a, b, c, d, e, f) containing the first two rows
        from the inverse of an affine transform matrix.
    """

    method = Image.Transform.AFFINE


class PerspectiveTransform(Transform):
    """
    Define a perspective image transform.

    This function takes an 8-tuple (a, b, c, d, e, f, g, h). For each pixel
    (x, y) in the output image, the new value is taken from a position
    ((a x + b y + c) / (g x + h y + 1), (d x + e y + f) / (g x + h y + 1)) in
    the input image, rounded to nearest pixel.

    This function can be used to scale, translate, rotate, and shear the
    original image.

    See :py:meth:`.Image.transform`

    :param matrix: An 8-tuple (a, b, c, d, e, f, g, h).
    """

    method = Image.Transform.PERSPECTIVE


class ExtentTransform(Transform):
    """
    Define a transform to extract a subregion from an image.

    Maps a rectangle (defined by two corners) from the image to a rectangle of
    the given size. The resulting image will contain data sampled from between
    the corners, such that (x0, y0) in the input image will end up at (0,0) in
    the output image, and (x1, y1) at size.

    This method can be used to crop, stretch, shrink, or mirror an arbitrary
    rectangle in the current image. It is slightly slower than crop, but about
    as fast as a corresponding resize operation.

    See :py:meth:`.Image.transform`

    :param bbox: A 4-tuple (x0, y0, x1, y1) which specifies two points in the
        input image's coordinate system. See :ref:`coordinate-system`.
    """

    method = Image.Transform.EXTENT


class QuadTransform(Transform):
    """
    Define a quad image transform.

    Maps a quadrilateral (a region defined by four corners) from the image to a
    rectangle of the given size.

    See :py:meth:`.Image.transform`

    :param xy: An 8-tuple (x0, y0, x1, y1, x2, y2, x3, y3) which contain the
        upper left, lower left, lower right, and upper right corner of the
        source quadrilateral.
    """

    method = Image.Transform.QUAD


class MeshTransform(Transform):
    """
    Define a mesh image transform.  A mesh transform consists of one or more
    individual quad transforms.

    See :py:meth:`.Image.transform`

    :param data: A list of (bbox, quad) tuples.
    """

    method = Image.Transform.MESH
