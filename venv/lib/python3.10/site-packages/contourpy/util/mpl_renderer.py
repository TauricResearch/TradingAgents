from __future__ import annotations

import io
from itertools import pairwise
from typing import TYPE_CHECKING, Any, cast

import matplotlib.collections as mcollections
import matplotlib.pyplot as plt
import numpy as np

from contourpy import FillType, LineType
from contourpy.convert import convert_filled, convert_lines
from contourpy.enum_util import as_fill_type, as_line_type
from contourpy.util.mpl_util import filled_to_mpl_paths, lines_to_mpl_paths
from contourpy.util.renderer import Renderer

if TYPE_CHECKING:
    from collections.abc import Sequence

    from matplotlib.axes import Axes
    from matplotlib.figure import Figure
    from numpy.typing import ArrayLike

    import contourpy._contourpy as cpy


class MplRenderer(Renderer):
    """Utility renderer using Matplotlib to render a grid of plots over the same (x, y) range.

    Args:
        nrows (int, optional): Number of rows of plots, default ``1``.
        ncols (int, optional): Number of columns of plots, default ``1``.
        figsize (tuple(float, float), optional): Figure size in inches, default ``(9, 9)``.
        show_frame (bool, optional): Whether to show frame and axes ticks, default ``True``.
        backend (str, optional): Matplotlib backend to use or ``None`` for default backend.
            Default ``None``.
        gridspec_kw (dict, optional): Gridspec keyword arguments to pass to ``plt.subplots``,
            default None.
    """
    _axes: Sequence[Axes]
    _fig: Figure
    _want_tight: bool

    def __init__(
        self,
        nrows: int = 1,
        ncols: int = 1,
        figsize: tuple[float, float] = (9, 9),
        show_frame: bool = True,
        backend: str | None = None,
        gridspec_kw: dict[str, Any] | None = None,
    ) -> None:
        if backend is not None:
            import matplotlib as mpl
            mpl.use(backend)

        kwargs: dict[str, Any] = {"figsize": figsize, "squeeze": False,
                                  "sharex": True, "sharey": True}
        if gridspec_kw is not None:
            kwargs["gridspec_kw"] = gridspec_kw
        else:
            kwargs["subplot_kw"] = {"aspect": "equal"}

        self._fig, axes = plt.subplots(nrows, ncols, **kwargs)
        self._axes = axes.flatten()
        if not show_frame:
            for ax in self._axes:
                ax.axis("off")

        self._want_tight = True

    def __del__(self) -> None:
        if hasattr(self, "_fig"):
            plt.close(self._fig)

    def _autoscale(self) -> None:
        # Using axes._need_autoscale attribute if need to autoscale before rendering after adding
        # lines/filled.  Only want to autoscale once per axes regardless of how many lines/filled
        # added.
        for ax in self._axes:
            if getattr(ax, "_need_autoscale", False):
                ax.autoscale_view(tight=True)
                ax._need_autoscale = False  # type: ignore[attr-defined]
        if self._want_tight and len(self._axes) > 1:
            self._fig.tight_layout()

    def _get_ax(self, ax: Axes | int) -> Axes:
        if isinstance(ax, int):
            ax = self._axes[ax]
        return ax

    def filled(
        self,
        filled: cpy.FillReturn,
        fill_type: FillType | str,
        ax: Axes | int = 0,
        color: str = "C0",
        alpha: float = 0.7,
    ) -> None:
        """Plot filled contours on a single Axes.

        Args:
            filled (sequence of arrays): Filled contour data as returned by
                :meth:`~.ContourGenerator.filled`.
            fill_type (FillType or str): Type of :meth:`~.ContourGenerator.filled` data as returned
                by :attr:`~.ContourGenerator.fill_type`, or string equivalent
            ax (int or Maplotlib Axes, optional): Which axes to plot on, default ``0``.
            color (str, optional): Color to plot with. May be a string color or the letter ``"C"``
                followed by an integer in the range ``"C0"`` to ``"C9"`` to use a color from the
                ``tab10`` colormap. Default ``"C0"``.
            alpha (float, optional): Opacity to plot with, default ``0.7``.
        """
        fill_type = as_fill_type(fill_type)
        ax = self._get_ax(ax)
        paths = filled_to_mpl_paths(filled, fill_type)
        collection = mcollections.PathCollection(
            paths, facecolors=color, edgecolors="none", lw=0, alpha=alpha)
        ax.add_collection(collection)
        ax._need_autoscale = True  # type: ignore[attr-defined]

    def grid(
        self,
        x: ArrayLike,
        y: ArrayLike,
        ax: Axes | int = 0,
        color: str = "black",
        alpha: float = 0.1,
        point_color: str | None = None,
        quad_as_tri_alpha: float = 0,
    ) -> None:
        """Plot quad grid lines on a single Axes.

        Args:
            x (array-like of shape (ny, nx) or (nx,)): The x-coordinates of the grid points.
            y (array-like of shape (ny, nx) or (ny,)): The y-coordinates of the grid points.
            ax (int or Matplotlib Axes, optional): Which Axes to plot on, default ``0``.
            color (str, optional): Color to plot grid lines, default ``"black"``.
            alpha (float, optional): Opacity to plot lines with, default ``0.1``.
            point_color (str, optional): Color to plot grid points or ``None`` if grid points
                should not be plotted, default ``None``.
            quad_as_tri_alpha (float, optional): Opacity to plot ``quad_as_tri`` grid, default 0.

        Colors may be a string color or the letter ``"C"`` followed by an integer in the range
        ``"C0"`` to ``"C9"`` to use a color from the ``tab10`` colormap.

        Warning:
            ``quad_as_tri_alpha > 0`` plots all quads as though they are unmasked.
        """
        ax = self._get_ax(ax)
        x, y = self._grid_as_2d(x, y)
        kwargs: dict[str, Any] = {"color": color, "alpha": alpha}
        ax.plot(x, y, x.T, y.T, **kwargs)
        if quad_as_tri_alpha > 0:
            # Assumes no quad mask.
            xmid = 0.25*(x[:-1, :-1] + x[1:, :-1] + x[:-1, 1:] + x[1:, 1:])
            ymid = 0.25*(y[:-1, :-1] + y[1:, :-1] + y[:-1, 1:] + y[1:, 1:])
            kwargs["alpha"] = quad_as_tri_alpha
            ax.plot(
                np.stack((x[:-1, :-1], xmid, x[1:, 1:])).reshape((3, -1)),
                np.stack((y[:-1, :-1], ymid, y[1:, 1:])).reshape((3, -1)),
                np.stack((x[1:, :-1], xmid, x[:-1, 1:])).reshape((3, -1)),
                np.stack((y[1:, :-1], ymid, y[:-1, 1:])).reshape((3, -1)),
                **kwargs)
        if point_color is not None:
            ax.plot(x, y, color=point_color, alpha=alpha, marker="o", lw=0)
        ax._need_autoscale = True  # type: ignore[attr-defined]

    def lines(
        self,
        lines: cpy.LineReturn,
        line_type: LineType | str,
        ax: Axes | int = 0,
        color: str = "C0",
        alpha: float = 1.0,
        linewidth: float = 1,
    ) -> None:
        """Plot contour lines on a single Axes.

        Args:
            lines (sequence of arrays): Contour line data as returned by
                :meth:`~.ContourGenerator.lines`.
            line_type (LineType or str): Type of :meth:`~.ContourGenerator.lines` data as returned
                by :attr:`~.ContourGenerator.line_type`, or string equivalent.
            ax (int or Matplotlib Axes, optional): Which Axes to plot on, default ``0``.
            color (str, optional): Color to plot lines. May be a string color or the letter ``"C"``
                followed by an integer in the range ``"C0"`` to ``"C9"`` to use a color from the
                ``tab10`` colormap. Default ``"C0"``.
            alpha (float, optional): Opacity to plot lines with, default ``1.0``.
            linewidth (float, optional): Width of lines, default ``1``.
        """
        line_type = as_line_type(line_type)
        ax = self._get_ax(ax)
        paths = lines_to_mpl_paths(lines, line_type)
        collection = mcollections.PathCollection(
            paths, facecolors="none", edgecolors=color, lw=linewidth, alpha=alpha)
        ax.add_collection(collection)
        ax._need_autoscale = True  # type: ignore[attr-defined]

    def mask(
        self,
        x: ArrayLike,
        y: ArrayLike,
        z: ArrayLike | np.ma.MaskedArray[Any, Any],
        ax: Axes | int = 0,
        color: str = "black",
    ) -> None:
        """Plot masked out grid points as circles on a single Axes.

        Args:
            x (array-like of shape (ny, nx) or (nx,)): The x-coordinates of the grid points.
            y (array-like of shape (ny, nx) or (ny,)): The y-coordinates of the grid points.
            z (masked array of shape (ny, nx): z-values.
            ax (int or Matplotlib Axes, optional): Which Axes to plot on, default ``0``.
            color (str, optional): Circle color, default ``"black"``.
        """
        mask = np.ma.getmask(z)  # type: ignore[no-untyped-call]
        if mask is np.ma.nomask:
            return
        ax = self._get_ax(ax)
        x, y = self._grid_as_2d(x, y)
        ax.plot(x[mask], y[mask], "o", c=color)

    def save(self, filename: str, transparent: bool = False) -> None:
        """Save plots to SVG or PNG file.

        Args:
            filename (str): Filename to save to.
            transparent (bool, optional): Whether background should be transparent, default
                ``False``.
        """
        self._autoscale()
        self._fig.savefig(filename, transparent=transparent)

    def save_to_buffer(self) -> io.BytesIO:
        """Save plots to an ``io.BytesIO`` buffer.

        Return:
            BytesIO: PNG image buffer.
        """
        self._autoscale()
        buf = io.BytesIO()
        self._fig.savefig(buf, format="png")
        buf.seek(0)
        return buf

    def show(self) -> None:
        """Show plots in an interactive window, in the usual Matplotlib manner.
        """
        self._autoscale()
        plt.show()

    def title(self, title: str, ax: Axes | int = 0, color: str | None = None) -> None:
        """Set the title of a single Axes.

        Args:
            title (str): Title text.
            ax (int or Matplotlib Axes, optional): Which Axes to set the title of, default ``0``.
            color (str, optional): Color to set title. May be a string color or the letter ``"C"``
                followed by an integer in the range ``"C0"`` to ``"C9"`` to use a color from the
                ``tab10`` colormap. Default is ``None`` which uses Matplotlib's default title color
                that depends on the stylesheet in use.
        """
        if color:
            self._get_ax(ax).set_title(title, color=color)
        else:
            self._get_ax(ax).set_title(title)

    def z_values(
        self,
        x: ArrayLike,
        y: ArrayLike,
        z: ArrayLike,
        ax: Axes | int = 0,
        color: str = "green",
        fmt: str = ".1f",
        quad_as_tri: bool = False,
    ) -> None:
        """Show ``z`` values on a single Axes.

        Args:
            x (array-like of shape (ny, nx) or (nx,)): The x-coordinates of the grid points.
            y (array-like of shape (ny, nx) or (ny,)): The y-coordinates of the grid points.
            z (array-like of shape (ny, nx): z-values.
            ax (int or Matplotlib Axes, optional): Which Axes to plot on, default ``0``.
            color (str, optional): Color of added text. May be a string color or the letter ``"C"``
                followed by an integer in the range ``"C0"`` to ``"C9"`` to use a color from the
                ``tab10`` colormap. Default ``"green"``.
            fmt (str, optional): Format to display z-values, default ``".1f"``.
            quad_as_tri (bool, optional): Whether to show z-values at the ``quad_as_tri`` centers
                of quads.

        Warning:
            ``quad_as_tri=True`` shows z-values for all quads, even if masked.
        """
        ax = self._get_ax(ax)
        x, y = self._grid_as_2d(x, y)
        z = np.asarray(z)
        ny, nx = z.shape
        for j in range(ny):
            for i in range(nx):
                ax.text(x[j, i], y[j, i], f"{z[j, i]:{fmt}}", ha="center", va="center",
                        color=color, clip_on=True)
        if quad_as_tri:
            for j in range(ny-1):
                for i in range(nx-1):
                    xx = np.mean(x[j:j+2, i:i+2], dtype=np.float64)
                    yy = np.mean(y[j:j+2, i:i+2], dtype=np.float64)
                    zz = np.mean(z[j:j+2, i:i+2])
                    ax.text(xx, yy, f"{zz:{fmt}}", ha="center", va="center", color=color,
                            clip_on=True)


class MplTestRenderer(MplRenderer):
    """Test renderer implemented using Matplotlib.

    No whitespace around plots and no spines/ticks displayed.
    Uses Agg backend, so can only save to file/buffer, cannot call ``show()``.
    """
    def __init__(
        self,
        nrows: int = 1,
        ncols: int = 1,
        figsize: tuple[float, float] = (9, 9),
    ) -> None:
        gridspec = {
            "left": 0.01,
            "right": 0.99,
            "top": 0.99,
            "bottom": 0.01,
            "wspace": 0.01,
            "hspace": 0.01,
        }
        super().__init__(
            nrows, ncols, figsize, show_frame=True, backend="Agg", gridspec_kw=gridspec,
        )

        for ax in self._axes:
            ax.set_xmargin(0.0)
            ax.set_ymargin(0.0)
            ax.set_xticks([])
            ax.set_yticks([])

        self._want_tight = False


class MplDebugRenderer(MplRenderer):
    """Debug renderer implemented using Matplotlib.

    Extends ``MplRenderer`` to add extra information to help in debugging such as markers, arrows,
    text, etc.
    """
    def __init__(
        self,
        nrows: int = 1,
        ncols: int = 1,
        figsize: tuple[float, float] = (9, 9),
        show_frame: bool = True,
    ) -> None:
        super().__init__(nrows, ncols, figsize, show_frame)

    def _arrow(
        self,
        ax: Axes,
        line_start: cpy.CoordinateArray,
        line_end: cpy.CoordinateArray,
        color: str,
        alpha: float,
        arrow_size: float,
    ) -> None:
        mid = 0.5*(line_start + line_end)
        along = line_end - line_start
        along /= np.sqrt(np.dot(along, along))  # Unit vector.
        right = np.asarray((along[1], -along[0]))
        arrow = np.stack((
            mid - (along*0.5 - right)*arrow_size,
            mid + along*0.5*arrow_size,
            mid - (along*0.5 + right)*arrow_size,
        ))
        ax.plot(arrow[:, 0], arrow[:, 1], "-", c=color, alpha=alpha)

    def filled(
        self,
        filled: cpy.FillReturn,
        fill_type: FillType | str,
        ax: Axes | int = 0,
        color: str = "C1",
        alpha: float = 0.7,
        line_color: str = "C0",
        line_alpha: float = 0.7,
        point_color: str = "C0",
        start_point_color: str = "red",
        arrow_size: float = 0.1,
    ) -> None:
        fill_type = as_fill_type(fill_type)
        super().filled(filled, fill_type, ax, color, alpha)

        if line_color is None and point_color is None:
            return

        ax = self._get_ax(ax)
        filled = convert_filled(filled, fill_type, FillType.ChunkCombinedOffset)

        # Lines.
        if line_color is not None:
            for points, offsets in zip(*filled):
                if points is None:
                    continue
                for start, end in pairwise(offsets):
                    xys = points[start:end]
                    ax.plot(xys[:, 0], xys[:, 1], c=line_color, alpha=line_alpha)

                    if arrow_size > 0.0:
                        n = len(xys)
                        for i in range(n-1):
                            self._arrow(ax, xys[i], xys[i+1], line_color, line_alpha, arrow_size)

        # Points.
        if point_color is not None:
            for points, offsets in zip(*filled):
                if points is None:
                    continue
                mask = np.ones(offsets[-1], dtype=bool)
                mask[offsets[1:]-1] = False  # Exclude end points.
                if start_point_color is not None:
                    start_indices = offsets[:-1]
                    mask[start_indices] = False  # Exclude start points.
                ax.plot(
                    points[:, 0][mask], points[:, 1][mask], "o", c=point_color, alpha=line_alpha)

                if start_point_color is not None:
                    ax.plot(points[:, 0][start_indices], points[:, 1][start_indices], "o",
                            c=start_point_color, alpha=line_alpha)

    def lines(
        self,
        lines: cpy.LineReturn,
        line_type: LineType | str,
        ax: Axes | int = 0,
        color: str = "C0",
        alpha: float = 1.0,
        linewidth: float = 1,
        point_color: str = "C0",
        start_point_color: str = "red",
        arrow_size: float = 0.1,
    ) -> None:
        line_type = as_line_type(line_type)
        super().lines(lines, line_type, ax, color, alpha, linewidth)

        if arrow_size == 0.0 and point_color is None:
            return

        ax = self._get_ax(ax)
        separate_lines = convert_lines(lines, line_type, LineType.Separate)
        if TYPE_CHECKING:
            separate_lines = cast(cpy.LineReturn_Separate, separate_lines)

        if arrow_size > 0.0:
            for line in separate_lines:
                for i in range(len(line)-1):
                    self._arrow(ax, line[i], line[i+1], color, alpha, arrow_size)

        if point_color is not None:
            for line in separate_lines:
                start_index = 0
                end_index = len(line)
                if start_point_color is not None:
                    ax.plot(line[0, 0], line[0, 1], "o", c=start_point_color, alpha=alpha)
                    start_index = 1
                    if line[0][0] == line[-1][0] and line[0][1] == line[-1][1]:
                        end_index -= 1
                ax.plot(line[start_index:end_index, 0], line[start_index:end_index, 1], "o",
                        c=color, alpha=alpha)

    def point_numbers(
        self,
        x: ArrayLike,
        y: ArrayLike,
        z: ArrayLike,
        ax: Axes | int = 0,
        color: str = "red",
    ) -> None:
        ax = self._get_ax(ax)
        x, y = self._grid_as_2d(x, y)
        z = np.asarray(z)
        ny, nx = z.shape
        for j in range(ny):
            for i in range(nx):
                quad = i + j*nx
                ax.text(x[j, i], y[j, i], str(quad), ha="right", va="top", color=color,
                        clip_on=True)

    def quad_numbers(
        self,
        x: ArrayLike,
        y: ArrayLike,
        z: ArrayLike,
        ax: Axes | int = 0,
        color: str = "blue",
    ) -> None:
        ax = self._get_ax(ax)
        x, y = self._grid_as_2d(x, y)
        z = np.asarray(z)
        ny, nx = z.shape
        for j in range(1, ny):
            for i in range(1, nx):
                quad = i + j*nx
                xmid = x[j-1:j+1, i-1:i+1].mean()
                ymid = y[j-1:j+1, i-1:i+1].mean()
                ax.text(xmid, ymid, str(quad), ha="center", va="center", color=color, clip_on=True)

    def z_levels(
        self,
        x: ArrayLike,
        y: ArrayLike,
        z: ArrayLike,
        lower_level: float,
        upper_level: float | None = None,
        ax: Axes | int = 0,
        color: str = "green",
    ) -> None:
        ax = self._get_ax(ax)
        x, y = self._grid_as_2d(x, y)
        z = np.asarray(z)
        ny, nx = z.shape
        for j in range(ny):
            for i in range(nx):
                zz = z[j, i]
                if upper_level is not None and zz > upper_level:
                    z_level = 2
                elif zz > lower_level:
                    z_level = 1
                else:
                    z_level = 0
                ax.text(x[j, i], y[j, i], str(z_level), ha="left", va="bottom", color=color,
                        clip_on=True)
