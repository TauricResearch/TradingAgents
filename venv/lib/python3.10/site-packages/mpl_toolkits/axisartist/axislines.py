"""
Axislines includes modified implementation of the Axes class. The
biggest difference is that the artists responsible for drawing the axis spine,
ticks, ticklabels and axis labels are separated out from Matplotlib's Axis
class. Originally, this change was motivated to support curvilinear
grid. Here are a few reasons that I came up with a new axes class:

* "top" and "bottom" x-axis (or "left" and "right" y-axis) can have
  different ticks (tick locations and labels). This is not possible
  with the current Matplotlib, although some twin axes trick can help.

* Curvilinear grid.

* angled ticks.

In the new axes class, xaxis and yaxis is set to not visible by
default, and new set of artist (AxisArtist) are defined to draw axis
line, ticks, ticklabels and axis label. Axes.axis attribute serves as
a dictionary of these artists, i.e., ax.axis["left"] is a AxisArtist
instance responsible to draw left y-axis. The default Axes.axis contains
"bottom", "left", "top" and "right".

AxisArtist can be considered as a container artist and has the following
children artists which will draw ticks, labels, etc.

* line
* major_ticks, major_ticklabels
* minor_ticks, minor_ticklabels
* offsetText
* label

Note that these are separate artists from `matplotlib.axis.Axis`, thus most
tick-related functions in Matplotlib won't work. For example, color and
markerwidth of the ``ax.axis["bottom"].major_ticks`` will follow those of
Axes.xaxis unless explicitly specified.

In addition to AxisArtist, the Axes will have *gridlines* attribute,
which obviously draws grid lines. The gridlines needs to be separated
from the axis as some gridlines can never pass any axis.
"""

import numpy as np

import matplotlib as mpl
from matplotlib import _api
import matplotlib.axes as maxes
from matplotlib.path import Path
from mpl_toolkits.axes_grid1 import mpl_axes
from .axisline_style import AxislineStyle  # noqa
from .axis_artist import AxisArtist, GridlinesCollection


class _AxisArtistHelperBase:
    """
    Base class for axis helper.

    Subclasses should define the methods listed below.  The *axes*
    argument will be the ``.axes`` attribute of the caller artist. ::

        # Construct the spine.

        def get_line_transform(self, axes):
            return transform

        def get_line(self, axes):
            return path

        # Construct the label.

        def get_axislabel_transform(self, axes):
            return transform

        def get_axislabel_pos_angle(self, axes):
            return (x, y), angle

        # Construct the ticks.

        def get_tick_transform(self, axes):
            return transform

        def get_tick_iterators(self, axes):
            # A pair of iterables (one for major ticks, one for minor ticks)
            # that yield (tick_position, tick_angle, tick_label).
            return iter_major, iter_minor
    """

    def __init__(self, nth_coord):
        self.nth_coord = nth_coord

    def update_lim(self, axes):
        pass

    def get_nth_coord(self):
        return self.nth_coord

    def _to_xy(self, values, const):
        """
        Create a (*values.shape, 2)-shape array representing (x, y) pairs.

        The other coordinate is filled with the constant *const*.

        Example::

            >>> self.nth_coord = 0
            >>> self._to_xy([1, 2, 3], const=0)
            array([[1, 0],
                   [2, 0],
                   [3, 0]])
        """
        if self.nth_coord == 0:
            return np.stack(np.broadcast_arrays(values, const), axis=-1)
        elif self.nth_coord == 1:
            return np.stack(np.broadcast_arrays(const, values), axis=-1)
        else:
            raise ValueError("Unexpected nth_coord")


class _FixedAxisArtistHelperBase(_AxisArtistHelperBase):
    """Helper class for a fixed (in the axes coordinate) axis."""

    @_api.delete_parameter("3.9", "nth_coord")
    def __init__(self, loc, nth_coord=None):
        """``nth_coord = 0``: x-axis; ``nth_coord = 1``: y-axis."""
        super().__init__(_api.check_getitem(
            {"bottom": 0, "top": 0, "left": 1, "right": 1}, loc=loc))
        self._loc = loc
        self._pos = {"bottom": 0, "top": 1, "left": 0, "right": 1}[loc]
        # axis line in transAxes
        self._path = Path(self._to_xy((0, 1), const=self._pos))

    # LINE

    def get_line(self, axes):
        return self._path

    def get_line_transform(self, axes):
        return axes.transAxes

    # LABEL

    def get_axislabel_transform(self, axes):
        return axes.transAxes

    def get_axislabel_pos_angle(self, axes):
        """
        Return the label reference position in transAxes.

        get_label_transform() returns a transform of (transAxes+offset)
        """
        return dict(left=((0., 0.5), 90),  # (position, angle_tangent)
                    right=((1., 0.5), 90),
                    bottom=((0.5, 0.), 0),
                    top=((0.5, 1.), 0))[self._loc]

    # TICK

    def get_tick_transform(self, axes):
        return [axes.get_xaxis_transform(), axes.get_yaxis_transform()][self.nth_coord]


class _FloatingAxisArtistHelperBase(_AxisArtistHelperBase):
    def __init__(self, nth_coord, value):
        self._value = value
        super().__init__(nth_coord)

    def get_line(self, axes):
        raise RuntimeError("get_line method should be defined by the derived class")


class FixedAxisArtistHelperRectilinear(_FixedAxisArtistHelperBase):

    @_api.delete_parameter("3.9", "nth_coord")
    def __init__(self, axes, loc, nth_coord=None):
        """
        nth_coord = along which coordinate value varies
        in 2D, nth_coord = 0 ->  x axis, nth_coord = 1 -> y axis
        """
        super().__init__(loc)
        self.axis = [axes.xaxis, axes.yaxis][self.nth_coord]

    # TICK

    def get_tick_iterators(self, axes):
        """tick_loc, tick_angle, tick_label"""
        angle_normal, angle_tangent = {0: (90, 0), 1: (0, 90)}[self.nth_coord]

        major = self.axis.major
        major_locs = major.locator()
        major_labels = major.formatter.format_ticks(major_locs)

        minor = self.axis.minor
        minor_locs = minor.locator()
        minor_labels = minor.formatter.format_ticks(minor_locs)

        tick_to_axes = self.get_tick_transform(axes) - axes.transAxes

        def _f(locs, labels):
            for loc, label in zip(locs, labels):
                c = self._to_xy(loc, const=self._pos)
                # check if the tick point is inside axes
                c2 = tick_to_axes.transform(c)
                if mpl.transforms._interval_contains_close((0, 1), c2[self.nth_coord]):
                    yield c, angle_normal, angle_tangent, label

        return _f(major_locs, major_labels), _f(minor_locs, minor_labels)


class FloatingAxisArtistHelperRectilinear(_FloatingAxisArtistHelperBase):

    def __init__(self, axes, nth_coord,
                 passingthrough_point, axis_direction="bottom"):
        super().__init__(nth_coord, passingthrough_point)
        self._axis_direction = axis_direction
        self.axis = [axes.xaxis, axes.yaxis][self.nth_coord]

    def get_line(self, axes):
        fixed_coord = 1 - self.nth_coord
        data_to_axes = axes.transData - axes.transAxes
        p = data_to_axes.transform([self._value, self._value])
        return Path(self._to_xy((0, 1), const=p[fixed_coord]))

    def get_line_transform(self, axes):
        return axes.transAxes

    def get_axislabel_transform(self, axes):
        return axes.transAxes

    def get_axislabel_pos_angle(self, axes):
        """
        Return the label reference position in transAxes.

        get_label_transform() returns a transform of (transAxes+offset)
        """
        angle = [0, 90][self.nth_coord]
        fixed_coord = 1 - self.nth_coord
        data_to_axes = axes.transData - axes.transAxes
        p = data_to_axes.transform([self._value, self._value])
        verts = self._to_xy(0.5, const=p[fixed_coord])
        return (verts, angle) if 0 <= verts[fixed_coord] <= 1 else (None, None)

    def get_tick_transform(self, axes):
        return axes.transData

    def get_tick_iterators(self, axes):
        """tick_loc, tick_angle, tick_label"""
        angle_normal, angle_tangent = {0: (90, 0), 1: (0, 90)}[self.nth_coord]

        major = self.axis.major
        major_locs = major.locator()
        major_labels = major.formatter.format_ticks(major_locs)

        minor = self.axis.minor
        minor_locs = minor.locator()
        minor_labels = minor.formatter.format_ticks(minor_locs)

        data_to_axes = axes.transData - axes.transAxes

        def _f(locs, labels):
            for loc, label in zip(locs, labels):
                c = self._to_xy(loc, const=self._value)
                c1, c2 = data_to_axes.transform(c)
                if 0 <= c1 <= 1 and 0 <= c2 <= 1:
                    yield c, angle_normal, angle_tangent, label

        return _f(major_locs, major_labels), _f(minor_locs, minor_labels)


class AxisArtistHelper:  # Backcompat.
    Fixed = _FixedAxisArtistHelperBase
    Floating = _FloatingAxisArtistHelperBase


class AxisArtistHelperRectlinear:  # Backcompat.
    Fixed = FixedAxisArtistHelperRectilinear
    Floating = FloatingAxisArtistHelperRectilinear


class GridHelperBase:

    def __init__(self):
        self._old_limits = None
        super().__init__()

    def update_lim(self, axes):
        x1, x2 = axes.get_xlim()
        y1, y2 = axes.get_ylim()
        if self._old_limits != (x1, x2, y1, y2):
            self._update_grid(x1, y1, x2, y2)
            self._old_limits = (x1, x2, y1, y2)

    def _update_grid(self, x1, y1, x2, y2):
        """Cache relevant computations when the axes limits have changed."""

    def get_gridlines(self, which, axis):
        """
        Return list of grid lines as a list of paths (list of points).

        Parameters
        ----------
        which : {"both", "major", "minor"}
        axis : {"both", "x", "y"}
        """
        return []


class GridHelperRectlinear(GridHelperBase):

    def __init__(self, axes):
        super().__init__()
        self.axes = axes

    @_api.delete_parameter(
        "3.9", "nth_coord", addendum="'nth_coord' is now inferred from 'loc'.")
    def new_fixed_axis(
            self, loc, nth_coord=None, axis_direction=None, offset=None, axes=None):
        if axes is None:
            _api.warn_external(
                "'new_fixed_axis' explicitly requires the axes keyword.")
            axes = self.axes
        if axis_direction is None:
            axis_direction = loc
        return AxisArtist(axes, FixedAxisArtistHelperRectilinear(axes, loc),
                          offset=offset, axis_direction=axis_direction)

    def new_floating_axis(self, nth_coord, value, axis_direction="bottom", axes=None):
        if axes is None:
            _api.warn_external(
                "'new_floating_axis' explicitly requires the axes keyword.")
            axes = self.axes
        helper = FloatingAxisArtistHelperRectilinear(
            axes, nth_coord, value, axis_direction)
        axisline = AxisArtist(axes, helper, axis_direction=axis_direction)
        axisline.line.set_clip_on(True)
        axisline.line.set_clip_box(axisline.axes.bbox)
        return axisline

    def get_gridlines(self, which="major", axis="both"):
        """
        Return list of gridline coordinates in data coordinates.

        Parameters
        ----------
        which : {"both", "major", "minor"}
        axis : {"both", "x", "y"}
        """
        _api.check_in_list(["both", "major", "minor"], which=which)
        _api.check_in_list(["both", "x", "y"], axis=axis)
        gridlines = []

        if axis in ("both", "x"):
            locs = []
            y1, y2 = self.axes.get_ylim()
            if which in ("both", "major"):
                locs.extend(self.axes.xaxis.major.locator())
            if which in ("both", "minor"):
                locs.extend(self.axes.xaxis.minor.locator())
            gridlines.extend([[x, x], [y1, y2]] for x in locs)

        if axis in ("both", "y"):
            x1, x2 = self.axes.get_xlim()
            locs = []
            if self.axes.yaxis._major_tick_kw["gridOn"]:
                locs.extend(self.axes.yaxis.major.locator())
            if self.axes.yaxis._minor_tick_kw["gridOn"]:
                locs.extend(self.axes.yaxis.minor.locator())
            gridlines.extend([[x1, x2], [y, y]] for y in locs)

        return gridlines


class Axes(maxes.Axes):

    def __init__(self, *args, grid_helper=None, **kwargs):
        self._axisline_on = True
        self._grid_helper = grid_helper if grid_helper else GridHelperRectlinear(self)
        super().__init__(*args, **kwargs)
        self.toggle_axisline(True)

    def toggle_axisline(self, b=None):
        if b is None:
            b = not self._axisline_on
        if b:
            self._axisline_on = True
            self.spines[:].set_visible(False)
            self.xaxis.set_visible(False)
            self.yaxis.set_visible(False)
        else:
            self._axisline_on = False
            self.spines[:].set_visible(True)
            self.xaxis.set_visible(True)
            self.yaxis.set_visible(True)

    @property
    def axis(self):
        return self._axislines

    def clear(self):
        # docstring inherited

        # Init gridlines before clear() as clear() calls grid().
        self.gridlines = gridlines = GridlinesCollection(
            [],
            colors=mpl.rcParams['grid.color'],
            linestyles=mpl.rcParams['grid.linestyle'],
            linewidths=mpl.rcParams['grid.linewidth'])
        self._set_artist_props(gridlines)
        gridlines.set_grid_helper(self.get_grid_helper())

        super().clear()

        # clip_path is set after Axes.clear(): that's when a patch is created.
        gridlines.set_clip_path(self.axes.patch)

        # Init axis artists.
        self._axislines = mpl_axes.Axes.AxisDict(self)
        new_fixed_axis = self.get_grid_helper().new_fixed_axis
        self._axislines.update({
            loc: new_fixed_axis(loc=loc, axes=self, axis_direction=loc)
            for loc in ["bottom", "top", "left", "right"]})
        for axisline in [self._axislines["top"], self._axislines["right"]]:
            axisline.label.set_visible(False)
            axisline.major_ticklabels.set_visible(False)
            axisline.minor_ticklabels.set_visible(False)

    def get_grid_helper(self):
        return self._grid_helper

    def grid(self, visible=None, which='major', axis="both", **kwargs):
        """
        Toggle the gridlines, and optionally set the properties of the lines.
        """
        # There are some discrepancies in the behavior of grid() between
        # axes_grid and Matplotlib, because axes_grid explicitly sets the
        # visibility of the gridlines.
        super().grid(visible, which=which, axis=axis, **kwargs)
        if not self._axisline_on:
            return
        if visible is None:
            visible = (self.axes.xaxis._minor_tick_kw["gridOn"]
                       or self.axes.xaxis._major_tick_kw["gridOn"]
                       or self.axes.yaxis._minor_tick_kw["gridOn"]
                       or self.axes.yaxis._major_tick_kw["gridOn"])
        self.gridlines.set(which=which, axis=axis, visible=visible)
        self.gridlines.set(**kwargs)

    def get_children(self):
        if self._axisline_on:
            children = [*self._axislines.values(), self.gridlines]
        else:
            children = []
        children.extend(super().get_children())
        return children

    def new_fixed_axis(self, loc, offset=None):
        return self.get_grid_helper().new_fixed_axis(loc, offset=offset, axes=self)

    def new_floating_axis(self, nth_coord, value, axis_direction="bottom"):
        return self.get_grid_helper().new_floating_axis(
            nth_coord, value, axis_direction=axis_direction, axes=self)


class AxesZero(Axes):

    def clear(self):
        super().clear()
        new_floating_axis = self.get_grid_helper().new_floating_axis
        self._axislines.update(
            xzero=new_floating_axis(
                nth_coord=0, value=0., axis_direction="bottom", axes=self),
            yzero=new_floating_axis(
                nth_coord=1, value=0., axis_direction="left", axes=self),
        )
        for k in ["xzero", "yzero"]:
            self._axislines[k].line.set_clip_path(self.patch)
            self._axislines[k].set_visible(False)


Subplot = Axes
SubplotZero = AxesZero
