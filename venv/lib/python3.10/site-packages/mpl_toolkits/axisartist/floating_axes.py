"""
An experimental support for curvilinear grid.
"""

# TODO :
# see if tick_iterator method can be simplified by reusing the parent method.

import functools

import numpy as np

import matplotlib as mpl
from matplotlib import _api, cbook
import matplotlib.patches as mpatches
from matplotlib.path import Path

from mpl_toolkits.axes_grid1.parasite_axes import host_axes_class_factory

from . import axislines, grid_helper_curvelinear
from .axis_artist import AxisArtist
from .grid_finder import ExtremeFinderSimple


class FloatingAxisArtistHelper(
        grid_helper_curvelinear.FloatingAxisArtistHelper):
    pass


class FixedAxisArtistHelper(grid_helper_curvelinear.FloatingAxisArtistHelper):

    def __init__(self, grid_helper, side, nth_coord_ticks=None):
        """
        nth_coord = along which coordinate value varies.
         nth_coord = 0 ->  x axis, nth_coord = 1 -> y axis
        """
        lon1, lon2, lat1, lat2 = grid_helper.grid_finder.extreme_finder(*[None] * 5)
        value, nth_coord = _api.check_getitem(
            dict(left=(lon1, 0), right=(lon2, 0), bottom=(lat1, 1), top=(lat2, 1)),
            side=side)
        super().__init__(grid_helper, nth_coord, value, axis_direction=side)
        if nth_coord_ticks is None:
            nth_coord_ticks = nth_coord
        self.nth_coord_ticks = nth_coord_ticks

        self.value = value
        self.grid_helper = grid_helper
        self._side = side

    def update_lim(self, axes):
        self.grid_helper.update_lim(axes)
        self._grid_info = self.grid_helper._grid_info

    def get_tick_iterators(self, axes):
        """tick_loc, tick_angle, tick_label, (optionally) tick_label"""

        grid_finder = self.grid_helper.grid_finder

        lat_levs, lat_n, lat_factor = self._grid_info["lat_info"]
        yy0 = lat_levs / lat_factor

        lon_levs, lon_n, lon_factor = self._grid_info["lon_info"]
        xx0 = lon_levs / lon_factor

        extremes = self.grid_helper.grid_finder.extreme_finder(*[None] * 5)
        xmin, xmax = sorted(extremes[:2])
        ymin, ymax = sorted(extremes[2:])

        def trf_xy(x, y):
            trf = grid_finder.get_transform() + axes.transData
            return trf.transform(np.column_stack(np.broadcast_arrays(x, y))).T

        if self.nth_coord == 0:
            mask = (ymin <= yy0) & (yy0 <= ymax)
            (xx1, yy1), (dxx1, dyy1), (dxx2, dyy2) = \
                grid_helper_curvelinear._value_and_jacobian(
                    trf_xy, self.value, yy0[mask], (xmin, xmax), (ymin, ymax))
            labels = self._grid_info["lat_labels"]

        elif self.nth_coord == 1:
            mask = (xmin <= xx0) & (xx0 <= xmax)
            (xx1, yy1), (dxx2, dyy2), (dxx1, dyy1) = \
                grid_helper_curvelinear._value_and_jacobian(
                    trf_xy, xx0[mask], self.value, (xmin, xmax), (ymin, ymax))
            labels = self._grid_info["lon_labels"]

        labels = [l for l, m in zip(labels, mask) if m]

        angle_normal = np.arctan2(dyy1, dxx1)
        angle_tangent = np.arctan2(dyy2, dxx2)
        mm = (dyy1 == 0) & (dxx1 == 0)  # points with degenerate normal
        angle_normal[mm] = angle_tangent[mm] + np.pi / 2

        tick_to_axes = self.get_tick_transform(axes) - axes.transAxes
        in_01 = functools.partial(
            mpl.transforms._interval_contains_close, (0, 1))

        def f1():
            for x, y, normal, tangent, lab \
                    in zip(xx1, yy1, angle_normal, angle_tangent, labels):
                c2 = tick_to_axes.transform((x, y))
                if in_01(c2[0]) and in_01(c2[1]):
                    yield [x, y], *np.rad2deg([normal, tangent]), lab

        return f1(), iter([])

    def get_line(self, axes):
        self.update_lim(axes)
        k, v = dict(left=("lon_lines0", 0),
                    right=("lon_lines0", 1),
                    bottom=("lat_lines0", 0),
                    top=("lat_lines0", 1))[self._side]
        xx, yy = self._grid_info[k][v]
        return Path(np.column_stack([xx, yy]))


class ExtremeFinderFixed(ExtremeFinderSimple):
    # docstring inherited

    def __init__(self, extremes):
        """
        This subclass always returns the same bounding box.

        Parameters
        ----------
        extremes : (float, float, float, float)
            The bounding box that this helper always returns.
        """
        self._extremes = extremes

    def __call__(self, transform_xy, x1, y1, x2, y2):
        # docstring inherited
        return self._extremes


class GridHelperCurveLinear(grid_helper_curvelinear.GridHelperCurveLinear):

    def __init__(self, aux_trans, extremes,
                 grid_locator1=None,
                 grid_locator2=None,
                 tick_formatter1=None,
                 tick_formatter2=None):
        # docstring inherited
        super().__init__(aux_trans,
                         extreme_finder=ExtremeFinderFixed(extremes),
                         grid_locator1=grid_locator1,
                         grid_locator2=grid_locator2,
                         tick_formatter1=tick_formatter1,
                         tick_formatter2=tick_formatter2)

    def new_fixed_axis(
            self, loc, nth_coord=None, axis_direction=None, offset=None, axes=None):
        if axes is None:
            axes = self.axes
        if axis_direction is None:
            axis_direction = loc
        # This is not the same as the FixedAxisArtistHelper class used by
        # grid_helper_curvelinear.GridHelperCurveLinear.new_fixed_axis!
        helper = FixedAxisArtistHelper(
            self, loc, nth_coord_ticks=nth_coord)
        axisline = AxisArtist(axes, helper, axis_direction=axis_direction)
        # Perhaps should be moved to the base class?
        axisline.line.set_clip_on(True)
        axisline.line.set_clip_box(axisline.axes.bbox)
        return axisline

    # new_floating_axis will inherit the grid_helper's extremes.

    # def new_floating_axis(self, nth_coord, value, axes=None, axis_direction="bottom"):
    #     axis = super(GridHelperCurveLinear,
    #                  self).new_floating_axis(nth_coord,
    #                                          value, axes=axes,
    #                                          axis_direction=axis_direction)
    #     # set extreme values of the axis helper
    #     if nth_coord == 1:
    #         axis.get_helper().set_extremes(*self._extremes[:2])
    #     elif nth_coord == 0:
    #         axis.get_helper().set_extremes(*self._extremes[2:])
    #     return axis

    def _update_grid(self, x1, y1, x2, y2):
        if self._grid_info is None:
            self._grid_info = dict()

        grid_info = self._grid_info

        grid_finder = self.grid_finder
        extremes = grid_finder.extreme_finder(grid_finder.inv_transform_xy,
                                              x1, y1, x2, y2)

        lon_min, lon_max = sorted(extremes[:2])
        lat_min, lat_max = sorted(extremes[2:])
        grid_info["extremes"] = lon_min, lon_max, lat_min, lat_max  # extremes

        lon_levs, lon_n, lon_factor = \
            grid_finder.grid_locator1(lon_min, lon_max)
        lon_levs = np.asarray(lon_levs)
        lat_levs, lat_n, lat_factor = \
            grid_finder.grid_locator2(lat_min, lat_max)
        lat_levs = np.asarray(lat_levs)

        grid_info["lon_info"] = lon_levs, lon_n, lon_factor
        grid_info["lat_info"] = lat_levs, lat_n, lat_factor

        grid_info["lon_labels"] = grid_finder._format_ticks(
            1, "bottom", lon_factor, lon_levs)
        grid_info["lat_labels"] = grid_finder._format_ticks(
            2, "bottom", lat_factor, lat_levs)

        lon_values = lon_levs[:lon_n] / lon_factor
        lat_values = lat_levs[:lat_n] / lat_factor

        lon_lines, lat_lines = grid_finder._get_raw_grid_lines(
            lon_values[(lon_min < lon_values) & (lon_values < lon_max)],
            lat_values[(lat_min < lat_values) & (lat_values < lat_max)],
            lon_min, lon_max, lat_min, lat_max)

        grid_info["lon_lines"] = lon_lines
        grid_info["lat_lines"] = lat_lines

        lon_lines, lat_lines = grid_finder._get_raw_grid_lines(
            # lon_min, lon_max, lat_min, lat_max)
            extremes[:2], extremes[2:], *extremes)

        grid_info["lon_lines0"] = lon_lines
        grid_info["lat_lines0"] = lat_lines

    def get_gridlines(self, which="major", axis="both"):
        grid_lines = []
        if axis in ["both", "x"]:
            grid_lines.extend(self._grid_info["lon_lines"])
        if axis in ["both", "y"]:
            grid_lines.extend(self._grid_info["lat_lines"])
        return grid_lines


class FloatingAxesBase:

    def __init__(self, *args, grid_helper, **kwargs):
        _api.check_isinstance(GridHelperCurveLinear, grid_helper=grid_helper)
        super().__init__(*args, grid_helper=grid_helper, **kwargs)
        self.set_aspect(1.)

    def _gen_axes_patch(self):
        # docstring inherited
        x0, x1, y0, y1 = self.get_grid_helper().grid_finder.extreme_finder(*[None] * 5)
        patch = mpatches.Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        patch.get_path()._interpolation_steps = 100
        return patch

    def clear(self):
        super().clear()
        self.patch.set_transform(
            self.get_grid_helper().grid_finder.get_transform()
            + self.transData)
        # The original patch is not in the draw tree; it is only used for
        # clipping purposes.
        orig_patch = super()._gen_axes_patch()
        orig_patch.set_figure(self.get_figure(root=False))
        orig_patch.set_transform(self.transAxes)
        self.patch.set_clip_path(orig_patch)
        self.gridlines.set_clip_path(orig_patch)
        self.adjust_axes_lim()

    def adjust_axes_lim(self):
        bbox = self.patch.get_path().get_extents(
            # First transform to pixel coords, then to parent data coords.
            self.patch.get_transform() - self.transData)
        bbox = bbox.expanded(1.02, 1.02)
        self.set_xlim(bbox.xmin, bbox.xmax)
        self.set_ylim(bbox.ymin, bbox.ymax)


floatingaxes_class_factory = cbook._make_class_factory(FloatingAxesBase, "Floating{}")
FloatingAxes = floatingaxes_class_factory(host_axes_class_factory(axislines.Axes))
FloatingSubplot = FloatingAxes
