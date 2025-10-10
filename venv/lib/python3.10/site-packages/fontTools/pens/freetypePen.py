# -*- coding: utf-8 -*-

"""Pen to rasterize paths with FreeType."""

__all__ = ["FreeTypePen"]

import os
import ctypes
import platform
import subprocess
import collections
import math

import freetype
from freetype.raw import FT_Outline_Get_Bitmap, FT_Outline_Get_BBox, FT_Outline_Get_CBox
from freetype.ft_types import FT_Pos
from freetype.ft_structs import FT_Vector, FT_BBox, FT_Bitmap, FT_Outline
from freetype.ft_enums import (
    FT_OUTLINE_NONE,
    FT_OUTLINE_EVEN_ODD_FILL,
    FT_PIXEL_MODE_GRAY,
    FT_CURVE_TAG_ON,
    FT_CURVE_TAG_CONIC,
    FT_CURVE_TAG_CUBIC,
)
from freetype.ft_errors import FT_Exception

from fontTools.pens.basePen import BasePen, PenError
from fontTools.misc.roundTools import otRound
from fontTools.misc.transform import Transform

Contour = collections.namedtuple("Contour", ("points", "tags"))


class FreeTypePen(BasePen):
    """Pen to rasterize paths with FreeType. Requires `freetype-py` module.

    Constructs ``FT_Outline`` from the paths, and renders it within a bitmap
    buffer.

    For ``array()`` and ``show()``, `numpy` and `matplotlib` must be installed.
    For ``image()``, `Pillow` is required. Each module is lazily loaded when the
    corresponding method is called.

    Args:
        glyphSet: a dictionary of drawable glyph objects keyed by name
            used to resolve component references in composite glyphs.

    Examples:
        If `numpy` and `matplotlib` is available, the following code will
        show the glyph image of `fi` in a new window::

            from fontTools.ttLib import TTFont
            from fontTools.pens.freetypePen import FreeTypePen
            from fontTools.misc.transform import Offset
            pen = FreeTypePen(None)
            font = TTFont('SourceSansPro-Regular.otf')
            glyph = font.getGlyphSet()['fi']
            glyph.draw(pen)
            width, ascender, descender = glyph.width, font['OS/2'].usWinAscent, -font['OS/2'].usWinDescent
            height = ascender - descender
            pen.show(width=width, height=height, transform=Offset(0, -descender))

        Combining with `uharfbuzz`, you can typeset a chunk of glyphs in a pen::

            import uharfbuzz as hb
            from fontTools.pens.freetypePen import FreeTypePen
            from fontTools.pens.transformPen import TransformPen
            from fontTools.misc.transform import Offset

            en1, en2, ar, ja = 'Typesetting', 'Jeff', 'صف الحروف', 'たいぷせっと'
            for text, font_path, direction, typo_ascender, typo_descender, vhea_ascender, vhea_descender, contain, features in (
                (en1, 'NotoSans-Regular.ttf',       'ltr', 2189, -600, None, None, False, {"kern": True, "liga": True}),
                (en2, 'NotoSans-Regular.ttf',       'ltr', 2189, -600, None, None, True,  {"kern": True, "liga": True}),
                (ar,  'NotoSansArabic-Regular.ttf', 'rtl', 1374, -738, None, None, False, {"kern": True, "liga": True}),
                (ja,  'NotoSansJP-Regular.otf',     'ltr', 880,  -120, 500,  -500, False, {"palt": True, "kern": True}),
                (ja,  'NotoSansJP-Regular.otf',     'ttb', 880,  -120, 500,  -500, False, {"vert": True, "vpal": True, "vkrn": True})
            ):
                blob = hb.Blob.from_file_path(font_path)
                face = hb.Face(blob)
                font = hb.Font(face)
                buf = hb.Buffer()
                buf.direction = direction
                buf.add_str(text)
                buf.guess_segment_properties()
                hb.shape(font, buf, features)

                x, y = 0, 0
                pen = FreeTypePen(None)
                for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
                    gid = info.codepoint
                    transformed = TransformPen(pen, Offset(x + pos.x_offset, y + pos.y_offset))
                    font.draw_glyph_with_pen(gid, transformed)
                    x += pos.x_advance
                    y += pos.y_advance

                offset, width, height = None, None, None
                if direction in ('ltr', 'rtl'):
                    offset = (0, -typo_descender)
                    width  = x
                    height = typo_ascender - typo_descender
                else:
                    offset = (-vhea_descender, -y)
                    width  = vhea_ascender - vhea_descender
                    height = -y
                pen.show(width=width, height=height, transform=Offset(*offset), contain=contain)

        For Jupyter Notebook, the rendered image will be displayed in a cell if
        you replace ``show()`` with ``image()`` in the examples.
    """

    def __init__(self, glyphSet):
        BasePen.__init__(self, glyphSet)
        self.contours = []

    def outline(self, transform=None, evenOdd=False):
        """Converts the current contours to ``FT_Outline``.

        Args:
            transform: An optional 6-tuple containing an affine transformation,
                or a ``Transform`` object from the ``fontTools.misc.transform``
                module.
            evenOdd: Pass ``True`` for even-odd fill instead of non-zero.
        """
        transform = transform or Transform()
        if not hasattr(transform, "transformPoint"):
            transform = Transform(*transform)
        n_contours = len(self.contours)
        n_points = sum((len(contour.points) for contour in self.contours))
        points = []
        for contour in self.contours:
            for point in contour.points:
                point = transform.transformPoint(point)
                points.append(
                    FT_Vector(
                        FT_Pos(otRound(point[0] * 64)), FT_Pos(otRound(point[1] * 64))
                    )
                )
        tags = []
        for contour in self.contours:
            for tag in contour.tags:
                tags.append(tag)
        contours = []
        contours_sum = 0
        for contour in self.contours:
            contours_sum += len(contour.points)
            contours.append(contours_sum - 1)
        flags = FT_OUTLINE_EVEN_ODD_FILL if evenOdd else FT_OUTLINE_NONE
        return FT_Outline(
            (ctypes.c_short)(n_contours),
            (ctypes.c_short)(n_points),
            (FT_Vector * n_points)(*points),
            (ctypes.c_ubyte * n_points)(*tags),
            (ctypes.c_short * n_contours)(*contours),
            (ctypes.c_int)(flags),
        )

    def buffer(
        self, width=None, height=None, transform=None, contain=False, evenOdd=False
    ):
        """Renders the current contours within a bitmap buffer.

        Args:
            width: Image width of the bitmap in pixels. If omitted, it
                automatically fits to the bounding box of the contours.
            height: Image height of the bitmap in pixels. If omitted, it
                automatically fits to the bounding box of the contours.
            transform: An optional 6-tuple containing an affine transformation,
                or a ``Transform`` object from the ``fontTools.misc.transform``
                module. The bitmap size is not affected by this matrix.
            contain: If ``True``, the image size will be automatically expanded
                so that it fits to the bounding box of the paths. Useful for
                rendering glyphs with negative sidebearings without clipping.
            evenOdd: Pass ``True`` for even-odd fill instead of non-zero.

        Returns:
            A tuple of ``(buffer, size)``, where ``buffer`` is a ``bytes``
            object of the resulted bitmap and ``size`` is a 2-tuple of its
            dimension.

        Notes:
            The image size should always be given explicitly if you need to get
            a proper glyph image. When ``width`` and ``height`` are omitted, it
            forcifully fits to the bounding box and the side bearings get
            cropped. If you pass ``0`` to both ``width`` and ``height`` and set
            ``contain`` to ``True``, it expands to the bounding box while
            maintaining the origin of the contours, meaning that LSB will be
            maintained but RSB won’t. The difference between the two becomes
            more obvious when rotate or skew transformation is applied.

        Example:
            .. code-block:: pycon

                >>>
                >> pen = FreeTypePen(None)
                >> glyph.draw(pen)
                >> buf, size = pen.buffer(width=500, height=1000)
                >> type(buf), len(buf), size
                (<class 'bytes'>, 500000, (500, 1000))
        """
        transform = transform or Transform()
        if not hasattr(transform, "transformPoint"):
            transform = Transform(*transform)
        contain_x, contain_y = contain or width is None, contain or height is None
        if contain_x or contain_y:
            dx, dy = transform.dx, transform.dy
            bbox = self.bbox
            p1, p2, p3, p4 = (
                transform.transformPoint((bbox[0], bbox[1])),
                transform.transformPoint((bbox[2], bbox[1])),
                transform.transformPoint((bbox[0], bbox[3])),
                transform.transformPoint((bbox[2], bbox[3])),
            )
            px, py = (p1[0], p2[0], p3[0], p4[0]), (p1[1], p2[1], p3[1], p4[1])
            if contain_x:
                if width is None:
                    dx = dx - min(*px)
                    width = max(*px) - min(*px)
                else:
                    dx = dx - min(min(*px), 0.0)
                    width = max(width, max(*px) - min(min(*px), 0.0))
            if contain_y:
                if height is None:
                    dy = dy - min(*py)
                    height = max(*py) - min(*py)
                else:
                    dy = dy - min(min(*py), 0.0)
                    height = max(height, max(*py) - min(min(*py), 0.0))
            transform = Transform(*transform[:4], dx, dy)
        width, height = math.ceil(width), math.ceil(height)
        buf = ctypes.create_string_buffer(width * height)
        bitmap = FT_Bitmap(
            (ctypes.c_int)(height),
            (ctypes.c_int)(width),
            (ctypes.c_int)(width),
            (ctypes.POINTER(ctypes.c_ubyte))(buf),
            (ctypes.c_short)(256),
            (ctypes.c_ubyte)(FT_PIXEL_MODE_GRAY),
            (ctypes.c_char)(0),
            (ctypes.c_void_p)(None),
        )
        outline = self.outline(transform=transform, evenOdd=evenOdd)
        err = FT_Outline_Get_Bitmap(
            freetype.get_handle(), ctypes.byref(outline), ctypes.byref(bitmap)
        )
        if err != 0:
            raise FT_Exception(err)
        return buf.raw, (width, height)

    def array(
        self, width=None, height=None, transform=None, contain=False, evenOdd=False
    ):
        """Returns the rendered contours as a numpy array. Requires `numpy`.

        Args:
            width: Image width of the bitmap in pixels. If omitted, it
                automatically fits to the bounding box of the contours.
            height: Image height of the bitmap in pixels. If omitted, it
                automatically fits to the bounding box of the contours.
            transform: An optional 6-tuple containing an affine transformation,
                or a ``Transform`` object from the ``fontTools.misc.transform``
                module. The bitmap size is not affected by this matrix.
            contain: If ``True``, the image size will be automatically expanded
                so that it fits to the bounding box of the paths. Useful for
                rendering glyphs with negative sidebearings without clipping.
            evenOdd: Pass ``True`` for even-odd fill instead of non-zero.

        Returns:
            A ``numpy.ndarray`` object with a shape of ``(height, width)``.
            Each element takes a value in the range of ``[0.0, 1.0]``.

        Notes:
            The image size should always be given explicitly if you need to get
            a proper glyph image. When ``width`` and ``height`` are omitted, it
            forcifully fits to the bounding box and the side bearings get
            cropped. If you pass ``0`` to both ``width`` and ``height`` and set
            ``contain`` to ``True``, it expands to the bounding box while
            maintaining the origin of the contours, meaning that LSB will be
            maintained but RSB won’t. The difference between the two becomes
            more obvious when rotate or skew transformation is applied.

        Example:
            .. code-block:: pycon

                >>>
                >> pen = FreeTypePen(None)
                >> glyph.draw(pen)
                >> arr = pen.array(width=500, height=1000)
                >> type(a), a.shape
                (<class 'numpy.ndarray'>, (1000, 500))
        """

        import numpy as np

        buf, size = self.buffer(
            width=width,
            height=height,
            transform=transform,
            contain=contain,
            evenOdd=evenOdd,
        )
        return np.frombuffer(buf, "B").reshape((size[1], size[0])) / 255.0

    def show(
        self, width=None, height=None, transform=None, contain=False, evenOdd=False
    ):
        """Plots the rendered contours with `pyplot`. Requires `numpy` and
        `matplotlib`.

        Args:
            width: Image width of the bitmap in pixels. If omitted, it
                automatically fits to the bounding box of the contours.
            height: Image height of the bitmap in pixels. If omitted, it
                automatically fits to the bounding box of the contours.
            transform: An optional 6-tuple containing an affine transformation,
                or a ``Transform`` object from the ``fontTools.misc.transform``
                module. The bitmap size is not affected by this matrix.
            contain: If ``True``, the image size will be automatically expanded
                so that it fits to the bounding box of the paths. Useful for
                rendering glyphs with negative sidebearings without clipping.
            evenOdd: Pass ``True`` for even-odd fill instead of non-zero.

        Notes:
            The image size should always be given explicitly if you need to get
            a proper glyph image. When ``width`` and ``height`` are omitted, it
            forcifully fits to the bounding box and the side bearings get
            cropped. If you pass ``0`` to both ``width`` and ``height`` and set
            ``contain`` to ``True``, it expands to the bounding box while
            maintaining the origin of the contours, meaning that LSB will be
            maintained but RSB won’t. The difference between the two becomes
            more obvious when rotate or skew transformation is applied.

        Example:
            .. code-block:: pycon

                >>>
                >> pen = FreeTypePen(None)
                >> glyph.draw(pen)
                >> pen.show(width=500, height=1000)
        """
        from matplotlib import pyplot as plt

        a = self.array(
            width=width,
            height=height,
            transform=transform,
            contain=contain,
            evenOdd=evenOdd,
        )
        plt.imshow(a, cmap="gray_r", vmin=0, vmax=1)
        plt.show()

    def image(
        self, width=None, height=None, transform=None, contain=False, evenOdd=False
    ):
        """Returns the rendered contours as a PIL image. Requires `Pillow`.
        Can be used to display a glyph image in Jupyter Notebook.

        Args:
            width: Image width of the bitmap in pixels. If omitted, it
                automatically fits to the bounding box of the contours.
            height: Image height of the bitmap in pixels. If omitted, it
                automatically fits to the bounding box of the contours.
            transform: An optional 6-tuple containing an affine transformation,
                or a ``Transform`` object from the ``fontTools.misc.transform``
                module. The bitmap size is not affected by this matrix.
            contain: If ``True``, the image size will be automatically expanded
                so that it fits to the bounding box of the paths. Useful for
                rendering glyphs with negative sidebearings without clipping.
            evenOdd: Pass ``True`` for even-odd fill instead of non-zero.

        Returns:
            A ``PIL.image`` object. The image is filled in black with alpha
            channel obtained from the rendered bitmap.

        Notes:
            The image size should always be given explicitly if you need to get
            a proper glyph image. When ``width`` and ``height`` are omitted, it
            forcifully fits to the bounding box and the side bearings get
            cropped. If you pass ``0`` to both ``width`` and ``height`` and set
            ``contain`` to ``True``, it expands to the bounding box while
            maintaining the origin of the contours, meaning that LSB will be
            maintained but RSB won’t. The difference between the two becomes
            more obvious when rotate or skew transformation is applied.

        Example:
            .. code-block:: pycon

                >>>
                >> pen = FreeTypePen(None)
                >> glyph.draw(pen)
                >> img = pen.image(width=500, height=1000)
                >> type(img), img.size
                (<class 'PIL.Image.Image'>, (500, 1000))
        """
        from PIL import Image

        buf, size = self.buffer(
            width=width,
            height=height,
            transform=transform,
            contain=contain,
            evenOdd=evenOdd,
        )
        img = Image.new("L", size, 0)
        img.putalpha(Image.frombuffer("L", size, buf))
        return img

    @property
    def bbox(self):
        """Computes the exact bounding box of an outline.

        Returns:
            A tuple of ``(xMin, yMin, xMax, yMax)``.
        """
        bbox = FT_BBox()
        outline = self.outline()
        FT_Outline_Get_BBox(ctypes.byref(outline), ctypes.byref(bbox))
        return (bbox.xMin / 64.0, bbox.yMin / 64.0, bbox.xMax / 64.0, bbox.yMax / 64.0)

    @property
    def cbox(self):
        """Returns an outline's ‘control box’.

        Returns:
            A tuple of ``(xMin, yMin, xMax, yMax)``.
        """
        cbox = FT_BBox()
        outline = self.outline()
        FT_Outline_Get_CBox(ctypes.byref(outline), ctypes.byref(cbox))
        return (cbox.xMin / 64.0, cbox.yMin / 64.0, cbox.xMax / 64.0, cbox.yMax / 64.0)

    def _moveTo(self, pt):
        contour = Contour([], [])
        self.contours.append(contour)
        contour.points.append(pt)
        contour.tags.append(FT_CURVE_TAG_ON)

    def _lineTo(self, pt):
        if not (self.contours and len(self.contours[-1].points) > 0):
            raise PenError("Contour missing required initial moveTo")
        contour = self.contours[-1]
        contour.points.append(pt)
        contour.tags.append(FT_CURVE_TAG_ON)

    def _curveToOne(self, p1, p2, p3):
        if not (self.contours and len(self.contours[-1].points) > 0):
            raise PenError("Contour missing required initial moveTo")
        t1, t2, t3 = FT_CURVE_TAG_CUBIC, FT_CURVE_TAG_CUBIC, FT_CURVE_TAG_ON
        contour = self.contours[-1]
        for p, t in ((p1, t1), (p2, t2), (p3, t3)):
            contour.points.append(p)
            contour.tags.append(t)

    def _qCurveToOne(self, p1, p2):
        if not (self.contours and len(self.contours[-1].points) > 0):
            raise PenError("Contour missing required initial moveTo")
        t1, t2 = FT_CURVE_TAG_CONIC, FT_CURVE_TAG_ON
        contour = self.contours[-1]
        for p, t in ((p1, t1), (p2, t2)):
            contour.points.append(p)
            contour.tags.append(t)
