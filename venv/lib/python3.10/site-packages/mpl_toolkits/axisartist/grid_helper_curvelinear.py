"""
An experimental support for curvilinear grid.
"""

import functools

import numpy as np

import matplotlib as mpl
from matplotlib import _api
from matplotlib.path import Path
from matplotlib.transforms import Affine2D, IdentityTransform
from .axislines import (
    _FixedAxisArtistHelperBase, _FloatingAxisArtistHelperBase, GridHelperBase)
from .axis_artist import AxisArtist
from .grid_finder import GridFinder


def _value_and_jacobian(func, xs, ys, xlims, ylims):
    """
    Compute *func* and its derivatives along x and y at positions *xs*, *ys*,
    while ensuring that finite difference calculations don't try to evaluate
    values outside of *xlims*, *ylims*.
    """
    eps = np.finfo(float).eps ** (1/2)  # see e.g. scipy.optimize.approx_fprime
    val = func(xs, ys)
    # Take the finite difference step in the direction where the bound is the
    # furthest; the step size is min of epsilon and distance to that bound.
    xlo, xhi = sorted(xlims)
    dxlo = xs - xlo
    dxhi = xhi - xs
    xeps = (np.take([-1, 1], dxhi >= dxlo)
            * np.minimum(eps, np.maximum(dxlo, dxhi)))
    val_dx = func(xs + xeps, ys)
    ylo, yhi = sorted(ylims)
    dylo = ys - ylo
    dyhi = yhi - ys
    yeps = (np.take([-1, 1], dyhi >= dylo)
            * np.minimum(eps, np.maximum(dylo, dyhi)))
    val_dy = func(xs, ys + yeps)
    return (val, (val_dx - val) / xeps, (val_dy - val) / yeps)


class FixedAxisArtistHelper(_FixedAxisArtistHelperBase):
    """
    Helper class for a fixed axis.
    """

    def __init__(self, grid_helper, side, nth_coord_ticks=None):
        """
        nth_coord = along which coordinate value varies.
         nth_coord = 0 ->  x axis, nth_coord = 1 -> y axis
        """

        super().__init__(loc=side)

        self.grid_helper = grid_helper
        if nth_coord_ticks is None:
            nth_coord_ticks = self.nth_coord
        self.nth_coord_ticks = nth_coord_ticks

        self.side = side

    def update_lim(self, axes):
        self.grid_helper.update_lim(axes)

    def get_tick_transform(self, axes):
        return axes.transData

    def get_tick_iterators(self, axes):
        """tick_loc, tick_angle, tick_label"""
        v1, v2 = axes.get_ylim() if self.nth_coord == 0 else axes.get_xlim()
        if v1 > v2:  # Inverted limits.
            side = {"left": "right", "right": "left",
                    "top": "bottom", "bottom": "top"}[self.side]
        else:
            side = self.side

        angle_tangent = dict(left=90, right=90, bottom=0, top=0)[side]

        def iter_major():
            for nth_coord, show_labels in [
                    (self.nth_coord_ticks, True), (1 - self.nth_coord_ticks, False)]:
                gi = self.grid_helper._grid_info[["lon", "lat"][nth_coord]]
                for tick in gi["ticks"][side]:
                    yield (*tick["loc"], angle_tangent,
                           (tick["label"] if show_labels else ""))

        return iter_major(), iter([])


class FloatingAxisArtistHelper(_FloatingAxisArtistHelperBase):

    def __init__(self, grid_helper, nth_coord, value, axis_direction=None):
        """
        nth_coord = along which coordinate value varies.
         nth_coord = 0 ->  x axis, nth_coord = 1 -> y axis
        """
        super().__init__(nth_coord, value)
        self.value = value
        self.grid_helper = grid_helper
        self._extremes = -np.inf, np.inf
        self._line_num_points = 100  # number of points to create a line

    def set_extremes(self, e1, e2):
        if e1 is None:
            e1 = -np.inf
        if e2 is None:
            e2 = np.inf
        self._extremes = e1, e2

    def update_lim(self, axes):
        self.grid_helper.update_lim(axes)

        x1, x2 = axes.get_xlim()
        y1, y2 = axes.get_ylim()
        grid_finder = self.grid_helper.grid_finder
        extremes = grid_finder.extreme_finder(grid_finder.inv_transform_xy,
                                              x1, y1, x2, y2)

        lon_min, lon_max, lat_min, lat_max = extremes
        e_min, e_max = self._extremes  # ranges of other coordinates
        if self.nth_coord == 0:
            lat_min = max(e_min, lat_min)
            lat_max = min(e_max, lat_max)
        elif self.nth_coord == 1:
            lon_min = max(e_min, lon_min)
            lon_max = min(e_max, lon_max)

        lon_levs, lon_n, lon_factor = \
            grid_finder.grid_locator1(lon_min, lon_max)
        lat_levs, lat_n, lat_factor = \
            grid_finder.grid_locator2(lat_min, lat_max)

        if self.nth_coord == 0:
            xx0 = np.full(self._line_num_points, self.value)
            yy0 = np.linspace(lat_min, lat_max, self._line_num_points)
            xx, yy = grid_finder.transform_xy(xx0, yy0)
        elif self.nth_coord == 1:
            xx0 = np.linspace(lon_min, lon_max, self._line_num_points)
            yy0 = np.full(self._line_num_points, self.value)
            xx, yy = grid_finder.transform_xy(xx0, yy0)

        self._grid_info = {
            "extremes": (lon_min, lon_max, lat_min, lat_max),
            "lon_info": (lon_levs, lon_n, np.asarray(lon_factor)),
            "lat_info": (lat_levs, lat_n, np.asarray(lat_factor)),
            "lon_labels": grid_finder._format_ticks(
                1, "bottom", lon_factor, lon_levs),
            "lat_labels": grid_finder._format_ticks(
                2, "bottom", lat_factor, lat_levs),
            "line_xy": (xx, yy),
        }

    def get_axislabel_transform(self, axes):
        return Affine2D()  # axes.transData

    def get_axislabel_pos_angle(self, axes):
        def trf_xy(x, y):
            trf = self.grid_helper.grid_finder.get_transform() + axes.transData
            return trf.transform([x, y]).T

        xmin, xmax, ymin, ymax = self._grid_info["extremes"]
        if self.nth_coord == 0:
            xx0 = self.value
            yy0 = (ymin + ymax) / 2
        elif self.nth_coord == 1:
            xx0 = (xmin + xmax) / 2
            yy0 = self.value
        xy1, dxy1_dx, dxy1_dy = _value_and_jacobian(
            trf_xy, xx0, yy0, (xmin, xmax), (ymin, ymax))
        p = axes.transAxes.inverted().transform(xy1)
        if 0 <= p[0] <= 1 and 0 <= p[1] <= 1:
            d = [dxy1_dy, dxy1_dx][self.nth_coord]
            return xy1, np.rad2deg(np.arctan2(*d[::-1]))
        else:
            return None, None

    def get_tick_transform(self, axes):
        return IdentityTransform()  # axes.transData

    def get_tick_iterators(self, axes):
        """tick_loc, tick_angle, tick_label, (optionally) tick_label"""

        lat_levs, lat_n, lat_factor = self._grid_info["lat_info"]
        yy0 = lat_levs / lat_factor

        lon_levs, lon_n, lon_factor = self._grid_info["lon_info"]
        xx0 = lon_levs / lon_factor

        e0, e1 = self._extremes

        def trf_xy(x, y):
            trf = self.grid_helper.grid_finder.get_transform() + axes.transData
            return trf.transform(np.column_stack(np.broadcast_arrays(x, y))).T

        # find angles
        if self.nth_coord == 0:
            mask = (e0 <= yy0) & (yy0 <= e1)
            (xx1, yy1), (dxx1, dyy1), (dxx2, dyy2) = _value_and_jacobian(
                trf_xy, self.value, yy0[mask], (-np.inf, np.inf), (e0, e1))
            labels = self._grid_info["lat_labels"]

        elif self.nth_coord == 1:
            mask = (e0 <= xx0) & (xx0 <= e1)
            (xx1, yy1), (dxx2, dyy2), (dxx1, dyy1) = _value_and_jacobian(
                trf_xy, xx0[mask], self.value, (-np.inf, np.inf), (e0, e1))
            labels = self._grid_info["lon_labels"]

        labels = [l for l, m in zip(labels, mask) if m]

        angle_normal = np.arctan2(dyy1, dxx1)
        angle_tangent = np.arctan2(dyy2, dxx2)
        mm = (dyy1 == 0) & (dxx1 == 0)  # points with degenerate normal
        angle_normal[mm] = angle_tangent[mm] + np.pi / 2

        tick_to_axes = self.get_tick_transform(axes) - axes.transAxes
        in_01 = functools.partial(
            mpl.transforms._interval_contains_close, (0, 1))

        def iter_major():
            for x, y, normal, tangent, lab \
                    in zip(xx1, yy1, angle_normal, angle_tangent, labels):
                c2 = tick_to_axes.transform((x, y))
                if in_01(c2[0]) and in_01(c2[1]):
                    yield [x, y], *np.rad2deg([normal, tangent]), lab

        return iter_major(), iter([])

    def get_line_transform(self, axes):
        return axes.transData

    def get_line(self, axes):
        self.update_lim(axes)
        x, y = self._grid_info["line_xy"]
        return Path(np.column_stack([x, y]))


class GridHelperCurveLinear(GridHelperBase):
    def __init__(self, aux_trans,
                 extreme_finder=None,
                 grid_locator1=None,
                 grid_locator2=None,
                 tick_formatter1=None,
                 tick_formatter2=None):
        """
        Parameters
        ----------
        aux_trans : `.Transform` or tuple[Callable, Callable]
            The transform from curved coordinates to rectilinear coordinate:
            either a `.Transform` instance (which provides also its inverse),
            or a pair of callables ``(trans, inv_trans)`` that define the
            transform and its inverse.  The callables should have signature::

                x_rect, y_rect = trans(x_curved, y_curved)
                x_curved, y_curved = inv_trans(x_rect, y_rect)

        extreme_finder

        grid_locator1, grid_locator2
            Grid locators for each axis.

        tick_formatter1, tick_formatter2
            Tick formatters for each axis.
        """
        super().__init__()
        self._grid_info = None
        self.grid_finder = GridFinder(aux_trans,
                                      extreme_finder,
                                      grid_locator1,
                                      grid_locator2,
                                      tick_formatter1,
                                      tick_formatter2)

    def update_grid_finder(self, aux_trans=None, **kwargs):
        if aux_trans is not None:
            self.grid_finder.update_transform(aux_trans)
        self.grid_finder.update(**kwargs)
        self._old_limits = None  # Force revalidation.

    @_api.make_keyword_only("3.9", "nth_coord")
    def new_fixed_axis(
            self, loc, nth_coord=None, axis_direction=None, offset=None, axes=None):
        if axes is None:
            axes = self.axes
        if axis_direction is None:
            axis_direction = loc
        helper = FixedAxisArtistHelper(self, loc, nth_coord_ticks=nth_coord)
        axisline = AxisArtist(axes, helper, axis_direction=axis_direction)
        # Why is clip not set on axisline, unlike in new_floating_axis or in
        # the floating_axig.GridHelperCurveLinear subclass?
        return axisline

    def new_floating_axis(self, nth_coord, value, axes=None, axis_direction="bottom"):
        if axes is None:
            axes = self.axes
        helper = FloatingAxisArtistHelper(
            self, nth_coord, value, axis_direction)
        axisline = AxisArtist(axes, helper)
        axisline.line.set_clip_on(True)
        axisline.line.set_clip_box(axisline.axes.bbox)
        # axisline.major_ticklabels.set_visible(True)
        # axisline.minor_ticklabels.set_visible(False)
        return axisline

    def _update_grid(self, x1, y1, x2, y2):
        self._grid_info = self.grid_finder.get_grid_info(x1, y1, x2, y2)

    def get_gridlines(self, which="major", axis="both"):
        grid_lines = []
        if axis in ["both", "x"]:
            for gl in self._grid_info["lon"]["lines"]:
                grid_lines.extend(gl)
        if axis in ["both", "y"]:
            for gl in self._grid_info["lat"]["lines"]:
                grid_lines.extend(gl)
        return grid_lines

    @_api.deprecated("3.9")
    def get_tick_iterator(self, nth_coord, axis_side, minor=False):
        angle_tangent = dict(left=90, right=90, bottom=0, top=0)[axis_side]
        lon_or_lat = ["lon", "lat"][nth_coord]
        if not minor:  # major ticks
            for tick in self._grid_info[lon_or_lat]["ticks"][axis_side]:
                yield *tick["loc"], angle_tangent, tick["label"]
        else:
            for tick in self._grid_info[lon_or_lat]["ticks"][axis_side]:
                yield *tick["loc"], angle_tangent, ""
