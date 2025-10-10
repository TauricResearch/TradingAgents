from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

from bokeh.io import export_png, export_svg, show
from bokeh.io.export import get_screenshot_as_png
from bokeh.layouts import gridplot
from bokeh.models.annotations.labels import Label
from bokeh.palettes import Category10
from bokeh.plotting import figure
import numpy as np

from contourpy.enum_util import as_fill_type, as_line_type
from contourpy.util.bokeh_util import filled_to_bokeh, lines_to_bokeh
from contourpy.util.renderer import Renderer

if TYPE_CHECKING:
    from bokeh.core.enums import OutputBackendType
    from bokeh.models import GridPlot
    from bokeh.palettes import Palette
    from numpy.typing import ArrayLike
    from selenium.webdriver.remote.webdriver import WebDriver

    from contourpy import FillType, LineType
    from contourpy._contourpy import FillReturn, LineReturn


class BokehRenderer(Renderer):
    """Utility renderer using Bokeh to render a grid of plots over the same (x, y) range.

    Args:
        nrows (int, optional): Number of rows of plots, default ``1``.
        ncols (int, optional): Number of columns of plots, default ``1``.
        figsize (tuple(float, float), optional): Figure size in inches (assuming 100 dpi), default
            ``(9, 9)``.
        show_frame (bool, optional): Whether to show frame and axes ticks, default ``True``.
        want_svg (bool, optional): Whether output is required in SVG format or not, default
            ``False``.

    Warning:
        :class:`~.BokehRenderer`, unlike :class:`~.MplRenderer`, needs to be told in advance if
        output to SVG format will be required later, otherwise it will assume PNG output.
    """
    _figures: list[figure]
    _layout: GridPlot
    _palette: Palette
    _want_svg: bool

    def __init__(
        self,
        nrows: int = 1,
        ncols: int = 1,
        figsize: tuple[float, float] = (9, 9),
        show_frame: bool = True,
        want_svg: bool = False,
    ) -> None:
        self._want_svg = want_svg
        self._palette = Category10[10]

        total_size = 100*np.asarray(figsize, dtype=int)  # Assuming 100 dpi.

        nfigures = nrows*ncols
        self._figures = []
        backend: OutputBackendType = "svg" if self._want_svg else "canvas"
        for _ in range(nfigures):
            fig = figure(output_backend=backend)
            fig.xgrid.visible = False  # type: ignore[attr-defined]
            fig.ygrid.visible = False  # type: ignore[attr-defined]
            self._figures.append(fig)
            if not show_frame:
                fig.outline_line_color = None
                fig.axis.visible = False  # type: ignore[attr-defined]

        self._layout = gridplot(
            self._figures, ncols=ncols, toolbar_location=None,  # type: ignore[arg-type]
            width=total_size[0] // ncols, height=total_size[1] // nrows)

    def _convert_color(self, color: str) -> str:
        if isinstance(color, str) and color[0] == "C":
            index = int(color[1:])
            color = self._palette[index]
        return color

    def _get_figure(self, ax: figure | int) -> figure:
        if isinstance(ax, int):
            ax = self._figures[ax]
        return ax

    def filled(
        self,
        filled: FillReturn,
        fill_type: FillType | str,
        ax: figure | int = 0,
        color: str = "C0",
        alpha: float = 0.7,
    ) -> None:
        """Plot filled contours on a single plot.

        Args:
            filled (sequence of arrays): Filled contour data as returned by
                :meth:`~.ContourGenerator.filled`.
            fill_type (FillType or str): Type of :meth:`~.ContourGenerator.filled` data as returned
                by :attr:`~.ContourGenerator.fill_type`, or a string equivalent.
            ax (int or Bokeh Figure, optional): Which plot to use, default ``0``.
            color (str, optional): Color to plot with. May be a string color or the letter ``"C"``
                followed by an integer in the range ``"C0"`` to ``"C9"`` to use a color from the
                ``Category10`` palette. Default ``"C0"``.
            alpha (float, optional): Opacity to plot with, default ``0.7``.
        """
        fill_type = as_fill_type(fill_type)
        fig = self._get_figure(ax)
        color = self._convert_color(color)
        xs, ys = filled_to_bokeh(filled, fill_type)
        if len(xs) > 0:
            fig.multi_polygons(xs=[xs], ys=[ys], color=color, fill_alpha=alpha, line_width=0)  # type: ignore[arg-type]

    def grid(
        self,
        x: ArrayLike,
        y: ArrayLike,
        ax: figure | int = 0,
        color: str = "black",
        alpha: float = 0.1,
        point_color: str | None = None,
        quad_as_tri_alpha: float = 0,
    ) -> None:
        """Plot quad grid lines on a single plot.

        Args:
            x (array-like of shape (ny, nx) or (nx,)): The x-coordinates of the grid points.
            y (array-like of shape (ny, nx) or (ny,)): The y-coordinates of the grid points.
            ax (int or Bokeh Figure, optional): Which plot to use, default ``0``.
            color (str, optional): Color to plot grid lines, default ``"black"``.
            alpha (float, optional): Opacity to plot lines with, default ``0.1``.
            point_color (str, optional): Color to plot grid points or ``None`` if grid points
                should not be plotted, default ``None``.
            quad_as_tri_alpha (float, optional): Opacity to plot ``quad_as_tri`` grid, default
                ``0``.

        Colors may be a string color or the letter ``"C"`` followed by an integer in the range
        ``"C0"`` to ``"C9"`` to use a color from the ``Category10`` palette.

        Warning:
            ``quad_as_tri_alpha > 0`` plots all quads as though they are unmasked.
        """
        fig = self._get_figure(ax)
        x, y = self._grid_as_2d(x, y)
        xs = list(x) + list(x.T)
        ys = list(y) + list(y.T)
        kwargs = {"line_color": color, "alpha": alpha}
        fig.multi_line(xs, ys, **kwargs)
        if quad_as_tri_alpha > 0:
            # Assumes no quad mask.
            xmid = (0.25*(x[:-1, :-1] + x[1:, :-1] + x[:-1, 1:] + x[1:, 1:])).ravel()
            ymid = (0.25*(y[:-1, :-1] + y[1:, :-1] + y[:-1, 1:] + y[1:, 1:])).ravel()
            fig.multi_line(
                list(np.stack((x[:-1, :-1].ravel(), xmid, x[1:, 1:].ravel()), axis=1)),
                list(np.stack((y[:-1, :-1].ravel(), ymid, y[1:, 1:].ravel()), axis=1)),
                **kwargs)
            fig.multi_line(
                list(np.stack((x[:-1, 1:].ravel(), xmid, x[1:, :-1].ravel()), axis=1)),
                list(np.stack((y[:-1, 1:].ravel(), ymid, y[1:, :-1].ravel()), axis=1)),
                **kwargs)
        if point_color is not None:
            fig.scatter(
                x=x.ravel(), y=y.ravel(), fill_color=color, line_color=None, alpha=alpha,
                marker="circle", size=8)

    def lines(
        self,
        lines: LineReturn,
        line_type: LineType | str,
        ax: figure | int = 0,
        color: str = "C0",
        alpha: float = 1.0,
        linewidth: float = 1,
    ) -> None:
        """Plot contour lines on a single plot.

        Args:
            lines (sequence of arrays): Contour line data as returned by
                :meth:`~.ContourGenerator.lines`.
            line_type (LineType or str): Type of :meth:`~.ContourGenerator.lines` data as returned
                by :attr:`~.ContourGenerator.line_type`, or a string equivalent.
            ax (int or Bokeh Figure, optional): Which plot to use, default ``0``.
            color (str, optional): Color to plot lines. May be a string color or the letter ``"C"``
                followed by an integer in the range ``"C0"`` to ``"C9"`` to use a color from the
                ``Category10`` palette. Default ``"C0"``.
            alpha (float, optional): Opacity to plot lines with, default ``1.0``.
            linewidth (float, optional): Width of lines, default ``1``.

        Note:
            Assumes all lines are open line strips not closed line loops.
        """
        line_type = as_line_type(line_type)
        fig = self._get_figure(ax)
        color = self._convert_color(color)
        xs, ys = lines_to_bokeh(lines, line_type)
        if xs is not None:
            assert ys is not None
            fig.line(xs, ys, line_color=color, line_alpha=alpha, line_width=linewidth)

    def mask(
        self,
        x: ArrayLike,
        y: ArrayLike,
        z: ArrayLike | np.ma.MaskedArray[Any, Any],
        ax: figure | int = 0,
        color: str = "black",
    ) -> None:
        """Plot masked out grid points as circles on a single plot.

        Args:
            x (array-like of shape (ny, nx) or (nx,)): The x-coordinates of the grid points.
            y (array-like of shape (ny, nx) or (ny,)): The y-coordinates of the grid points.
            z (masked array of shape (ny, nx): z-values.
            ax (int or Bokeh Figure, optional): Which plot to use, default ``0``.
            color (str, optional): Circle color, default ``"black"``.
        """
        mask = np.ma.getmask(z)  # type: ignore[no-untyped-call]
        if mask is np.ma.nomask:
            return
        fig = self._get_figure(ax)
        color = self._convert_color(color)
        x, y = self._grid_as_2d(x, y)
        fig.scatter(x[mask], y[mask], fill_color=color, marker="circle", size=10)

    def save(
        self,
        filename: str,
        transparent: bool = False,
        *,
        webdriver: WebDriver | None = None,
    ) -> None:
        """Save plots to SVG or PNG file.

        Args:
            filename (str): Filename to save to.
            transparent (bool, optional): Whether background should be transparent, default
                ``False``.
            webdriver (WebDriver, optional): Selenium WebDriver instance to use to create the image.

                .. versionadded:: 1.1.1

        Warning:
            To output to SVG file, ``want_svg=True`` must have been passed to the constructor.
        """
        if transparent:
            for fig in self._figures:
                fig.background_fill_color = None
                fig.border_fill_color = None

        if self._want_svg:
            export_svg(self._layout, filename=filename, webdriver=webdriver)
        else:
            export_png(self._layout, filename=filename, webdriver=webdriver)

    def save_to_buffer(self, *, webdriver: WebDriver | None = None) -> io.BytesIO:
        """Save plots to an ``io.BytesIO`` buffer.

        Args:
            webdriver (WebDriver, optional): Selenium WebDriver instance to use to create the image.

                .. versionadded:: 1.1.1

        Return:
            BytesIO: PNG image buffer.
        """
        image = get_screenshot_as_png(self._layout, driver=webdriver)
        buffer = io.BytesIO()
        image.save(buffer, "png")
        return buffer

    def show(self) -> None:
        """Show plots in web browser, in usual Bokeh manner.
        """
        show(self._layout)

    def title(self, title: str, ax: figure | int = 0, color: str | None = None) -> None:
        """Set the title of a single plot.

        Args:
            title (str): Title text.
            ax (int or Bokeh Figure, optional): Which plot to set the title of, default ``0``.
            color (str, optional): Color to set title. May be a string color or the letter ``"C"``
                followed by an integer in the range ``"C0"`` to ``"C9"`` to use a color from the
                ``Category10`` palette. Default ``None`` which is ``black``.
        """
        fig = self._get_figure(ax)
        fig.title = title
        fig.title.align = "center"  # type: ignore[attr-defined]
        if color is not None:
            fig.title.text_color = self._convert_color(color)  # type: ignore[attr-defined]

    def z_values(
        self,
        x: ArrayLike,
        y: ArrayLike,
        z: ArrayLike,
        ax: figure | int = 0,
        color: str = "green",
        fmt: str = ".1f",
        quad_as_tri: bool = False,
    ) -> None:
        """Show ``z`` values on a single plot.

        Args:
            x (array-like of shape (ny, nx) or (nx,)): The x-coordinates of the grid points.
            y (array-like of shape (ny, nx) or (ny,)): The y-coordinates of the grid points.
            z (array-like of shape (ny, nx): z-values.
            ax (int or Bokeh Figure, optional): Which plot to use, default ``0``.
            color (str, optional): Color of added text. May be a string color or the letter ``"C"``
                followed by an integer in the range ``"C0"`` to ``"C9"`` to use a color from the
                ``Category10`` palette. Default ``"green"``.
            fmt (str, optional): Format to display z-values, default ``".1f"``.
            quad_as_tri (bool, optional): Whether to show z-values at the ``quad_as_tri`` centres
                of quads.

        Warning:
            ``quad_as_tri=True`` shows z-values for all quads, even if masked.
        """
        fig = self._get_figure(ax)
        color = self._convert_color(color)
        x, y = self._grid_as_2d(x, y)
        z = np.asarray(z)
        ny, nx = z.shape
        kwargs = {"text_color": color, "text_align": "center", "text_baseline": "middle"}
        for j in range(ny):
            for i in range(nx):
                label = Label(x=x[j, i], y=y[j, i], text=f"{z[j, i]:{fmt}}", **kwargs)  # type: ignore[arg-type]
                fig.add_layout(label)
        if quad_as_tri:
            for j in range(ny-1):
                for i in range(nx-1):
                    xx = np.mean(x[j:j+2, i:i+2])
                    yy = np.mean(y[j:j+2, i:i+2])
                    zz = np.mean(z[j:j+2, i:i+2])
                    fig.add_layout(Label(x=xx, y=yy, text=f"{zz:{fmt}}", **kwargs))  # type: ignore[arg-type]
