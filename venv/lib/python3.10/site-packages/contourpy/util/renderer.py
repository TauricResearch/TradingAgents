from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import io

    from numpy.typing import ArrayLike

    from contourpy._contourpy import CoordinateArray, FillReturn, FillType, LineReturn, LineType


class Renderer(ABC):
    """Abstract base class for renderers."""

    def _grid_as_2d(self, x: ArrayLike, y: ArrayLike) -> tuple[CoordinateArray, CoordinateArray]:
        x = np.asarray(x)
        y = np.asarray(y)
        if x.ndim == 1:
            x, y = np.meshgrid(x, y)
        return x, y

    @abstractmethod
    def filled(
        self,
        filled: FillReturn,
        fill_type: FillType | str,
        ax: Any = 0,
        color: str = "C0",
        alpha: float = 0.7,
    ) -> None:
        pass

    @abstractmethod
    def grid(
        self,
        x: ArrayLike,
        y: ArrayLike,
        ax: Any = 0,
        color: str = "black",
        alpha: float = 0.1,
        point_color: str | None = None,
        quad_as_tri_alpha: float = 0,
    ) -> None:
        pass

    @abstractmethod
    def lines(
        self,
        lines: LineReturn,
        line_type: LineType | str,
        ax: Any = 0,
        color: str = "C0",
        alpha: float = 1.0,
        linewidth: float = 1,
    ) -> None:
        pass

    @abstractmethod
    def mask(
        self,
        x: ArrayLike,
        y: ArrayLike,
        z: ArrayLike | np.ma.MaskedArray[Any, Any],
        ax: Any = 0,
        color: str = "black",
    ) -> None:
        pass

    def multi_filled(
        self,
        multi_filled: list[FillReturn],
        fill_type: FillType | str,
        ax: Any = 0,
        color: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Plot multiple sets of filled contours on a single axes.

        Args:
            multi_filled (list of filled contour arrays): Multiple filled contour sets as returned
                by :meth:`.ContourGenerator.multi_filled`.
            fill_type (FillType or str): Type of filled data as returned by
                :attr:`~.ContourGenerator.fill_type`, or string equivalent.
            ax (int or Renderer-specific axes or figure object, optional): Which axes to plot on,
                default ``0``.
            color (str or None, optional): If a string color then this same color is used for all
                filled contours. If ``None``, the default, then the filled contour sets use colors
                from the ``tab10`` colormap in order, wrapping around to the beginning if more than
                10 sets of filled contours are rendered.
            kwargs: All other keyword argument are passed on to
                :meth:`.Renderer.filled` unchanged.

        .. versionadded:: 1.3.0
        """
        if color is not None:
            kwargs["color"] = color
        for i, filled in enumerate(multi_filled):
            if color is None:
                kwargs["color"] = f"C{i % 10}"
            self.filled(filled, fill_type, ax, **kwargs)

    def multi_lines(
        self,
        multi_lines: list[LineReturn],
        line_type: LineType | str,
        ax: Any = 0,
        color: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Plot multiple sets of contour lines on a single axes.

        Args:
            multi_lines (list of contour line arrays): Multiple contour line sets as returned by
                :meth:`.ContourGenerator.multi_lines`.
            line_type (LineType or str): Type of line data as returned by
                :attr:`~.ContourGenerator.line_type`, or string equivalent.
            ax (int or Renderer-specific axes or figure object, optional): Which axes to plot on,
                default ``0``.
            color (str or None, optional): If a string color then this same color is used for all
                lines. If ``None``, the default, then the line sets use colors from the ``tab10``
                colormap in order, wrapping around to the beginning if more than 10 sets of lines
                are rendered.
            kwargs: All other keyword argument are passed on to
                :meth:`Renderer.lines` unchanged.

        .. versionadded:: 1.3.0
        """
        if color is not None:
            kwargs["color"] = color
        for i, lines in enumerate(multi_lines):
            if color is None:
                kwargs["color"] = f"C{i % 10}"
            self.lines(lines, line_type, ax, **kwargs)

    @abstractmethod
    def save(self, filename: str, transparent: bool = False) -> None:
        pass

    @abstractmethod
    def save_to_buffer(self) -> io.BytesIO:
        pass

    @abstractmethod
    def show(self) -> None:
        pass

    @abstractmethod
    def title(self, title: str, ax: Any = 0, color: str | None = None) -> None:
        pass

    @abstractmethod
    def z_values(
        self,
        x: ArrayLike,
        y: ArrayLike,
        z: ArrayLike,
        ax: Any = 0,
        color: str = "green",
        fmt: str = ".1f",
        quad_as_tri: bool = False,
    ) -> None:
        pass
