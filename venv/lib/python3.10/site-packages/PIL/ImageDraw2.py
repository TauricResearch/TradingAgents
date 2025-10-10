#
# The Python Imaging Library
# $Id$
#
# WCK-style drawing interface operations
#
# History:
# 2003-12-07 fl   created
# 2005-05-15 fl   updated; added to PIL as ImageDraw2
# 2005-05-15 fl   added text support
# 2005-05-20 fl   added arc/chord/pieslice support
#
# Copyright (c) 2003-2005 by Secret Labs AB
# Copyright (c) 2003-2005 by Fredrik Lundh
#
# See the README file for information on usage and redistribution.
#


"""
(Experimental) WCK-style drawing interface operations

.. seealso:: :py:mod:`PIL.ImageDraw`
"""
from __future__ import annotations

from typing import Any, AnyStr, BinaryIO

from . import Image, ImageColor, ImageDraw, ImageFont, ImagePath
from ._typing import Coords, StrOrBytesPath


class Pen:
    """Stores an outline color and width."""

    def __init__(self, color: str, width: int = 1, opacity: int = 255) -> None:
        self.color = ImageColor.getrgb(color)
        self.width = width


class Brush:
    """Stores a fill color"""

    def __init__(self, color: str, opacity: int = 255) -> None:
        self.color = ImageColor.getrgb(color)


class Font:
    """Stores a TrueType font and color"""

    def __init__(
        self, color: str, file: StrOrBytesPath | BinaryIO, size: float = 12
    ) -> None:
        # FIXME: add support for bitmap fonts
        self.color = ImageColor.getrgb(color)
        self.font = ImageFont.truetype(file, size)


class Draw:
    """
    (Experimental) WCK-style drawing interface
    """

    def __init__(
        self,
        image: Image.Image | str,
        size: tuple[int, int] | list[int] | None = None,
        color: float | tuple[float, ...] | str | None = None,
    ) -> None:
        if isinstance(image, str):
            if size is None:
                msg = "If image argument is mode string, size must be a list or tuple"
                raise ValueError(msg)
            image = Image.new(image, size, color)
        self.draw = ImageDraw.Draw(image)
        self.image = image
        self.transform: tuple[float, float, float, float, float, float] | None = None

    def flush(self) -> Image.Image:
        return self.image

    def render(
        self,
        op: str,
        xy: Coords,
        pen: Pen | Brush | None,
        brush: Brush | Pen | None = None,
        **kwargs: Any,
    ) -> None:
        # handle color arguments
        outline = fill = None
        width = 1
        if isinstance(pen, Pen):
            outline = pen.color
            width = pen.width
        elif isinstance(brush, Pen):
            outline = brush.color
            width = brush.width
        if isinstance(brush, Brush):
            fill = brush.color
        elif isinstance(pen, Brush):
            fill = pen.color
        # handle transformation
        if self.transform:
            path = ImagePath.Path(xy)
            path.transform(self.transform)
            xy = path
        # render the item
        if op in ("arc", "line"):
            kwargs.setdefault("fill", outline)
        else:
            kwargs.setdefault("fill", fill)
            kwargs.setdefault("outline", outline)
        if op == "line":
            kwargs.setdefault("width", width)
        getattr(self.draw, op)(xy, **kwargs)

    def settransform(self, offset: tuple[float, float]) -> None:
        """Sets a transformation offset."""
        (xoffset, yoffset) = offset
        self.transform = (1, 0, xoffset, 0, 1, yoffset)

    def arc(
        self,
        xy: Coords,
        pen: Pen | Brush | None,
        start: float,
        end: float,
        *options: Any,
    ) -> None:
        """
        Draws an arc (a portion of a circle outline) between the start and end
        angles, inside the given bounding box.

        .. seealso:: :py:meth:`PIL.ImageDraw.ImageDraw.arc`
        """
        self.render("arc", xy, pen, *options, start=start, end=end)

    def chord(
        self,
        xy: Coords,
        pen: Pen | Brush | None,
        start: float,
        end: float,
        *options: Any,
    ) -> None:
        """
        Same as :py:meth:`~PIL.ImageDraw2.Draw.arc`, but connects the end points
        with a straight line.

        .. seealso:: :py:meth:`PIL.ImageDraw.ImageDraw.chord`
        """
        self.render("chord", xy, pen, *options, start=start, end=end)

    def ellipse(self, xy: Coords, pen: Pen | Brush | None, *options: Any) -> None:
        """
        Draws an ellipse inside the given bounding box.

        .. seealso:: :py:meth:`PIL.ImageDraw.ImageDraw.ellipse`
        """
        self.render("ellipse", xy, pen, *options)

    def line(self, xy: Coords, pen: Pen | Brush | None, *options: Any) -> None:
        """
        Draws a line between the coordinates in the ``xy`` list.

        .. seealso:: :py:meth:`PIL.ImageDraw.ImageDraw.line`
        """
        self.render("line", xy, pen, *options)

    def pieslice(
        self,
        xy: Coords,
        pen: Pen | Brush | None,
        start: float,
        end: float,
        *options: Any,
    ) -> None:
        """
        Same as arc, but also draws straight lines between the end points and the
        center of the bounding box.

        .. seealso:: :py:meth:`PIL.ImageDraw.ImageDraw.pieslice`
        """
        self.render("pieslice", xy, pen, *options, start=start, end=end)

    def polygon(self, xy: Coords, pen: Pen | Brush | None, *options: Any) -> None:
        """
        Draws a polygon.

        The polygon outline consists of straight lines between the given
        coordinates, plus a straight line between the last and the first
        coordinate.


        .. seealso:: :py:meth:`PIL.ImageDraw.ImageDraw.polygon`
        """
        self.render("polygon", xy, pen, *options)

    def rectangle(self, xy: Coords, pen: Pen | Brush | None, *options: Any) -> None:
        """
        Draws a rectangle.

        .. seealso:: :py:meth:`PIL.ImageDraw.ImageDraw.rectangle`
        """
        self.render("rectangle", xy, pen, *options)

    def text(self, xy: tuple[float, float], text: AnyStr, font: Font) -> None:
        """
        Draws the string at the given position.

        .. seealso:: :py:meth:`PIL.ImageDraw.ImageDraw.text`
        """
        if self.transform:
            path = ImagePath.Path(xy)
            path.transform(self.transform)
            xy = path
        self.draw.text(xy, text, font=font.font, fill=font.color)

    def textbbox(
        self, xy: tuple[float, float], text: AnyStr, font: Font
    ) -> tuple[float, float, float, float]:
        """
        Returns bounding box (in pixels) of given text.

        :return: ``(left, top, right, bottom)`` bounding box

        .. seealso:: :py:meth:`PIL.ImageDraw.ImageDraw.textbbox`
        """
        if self.transform:
            path = ImagePath.Path(xy)
            path.transform(self.transform)
            xy = path
        return self.draw.textbbox(xy, text, font=font.font)

    def textlength(self, text: AnyStr, font: Font) -> float:
        """
        Returns length (in pixels) of given text.
        This is the amount by which following text should be offset.

        .. seealso:: :py:meth:`PIL.ImageDraw.ImageDraw.textlength`
        """
        return self.draw.textlength(text, font=font.font)
