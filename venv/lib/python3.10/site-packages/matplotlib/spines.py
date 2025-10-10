from collections.abc import MutableMapping
import functools

import numpy as np

import matplotlib as mpl
from matplotlib import _api, _docstring
from matplotlib.artist import allow_rasterization
import matplotlib.transforms as mtransforms
import matplotlib.patches as mpatches
import matplotlib.path as mpath


class Spine(mpatches.Patch):
    """
    An axis spine -- the line noting the data area boundaries.

    Spines are the lines connecting the axis tick marks and noting the
    boundaries of the data area. They can be placed at arbitrary
    positions. See `~.Spine.set_position` for more information.

    The default position is ``('outward', 0)``.

    Spines are subclasses of `.Patch`, and inherit much of their behavior.

    Spines draw a line, a circle, or an arc depending on if
    `~.Spine.set_patch_line`, `~.Spine.set_patch_circle`, or
    `~.Spine.set_patch_arc` has been called. Line-like is the default.

    For examples see :ref:`spines_examples`.
    """
    def __str__(self):
        return "Spine"

    @_docstring.interpd
    def __init__(self, axes, spine_type, path, **kwargs):
        """
        Parameters
        ----------
        axes : `~matplotlib.axes.Axes`
            The `~.axes.Axes` instance containing the spine.
        spine_type : str
            The spine type.
        path : `~matplotlib.path.Path`
            The `.Path` instance used to draw the spine.

        Other Parameters
        ----------------
        **kwargs
            Valid keyword arguments are:

            %(Patch:kwdoc)s
        """
        super().__init__(**kwargs)
        self.axes = axes
        self.set_figure(self.axes.get_figure(root=False))
        self.spine_type = spine_type
        self.set_facecolor('none')
        self.set_edgecolor(mpl.rcParams['axes.edgecolor'])
        self.set_linewidth(mpl.rcParams['axes.linewidth'])
        self.set_capstyle('projecting')
        self.axis = None

        self.set_zorder(2.5)
        self.set_transform(self.axes.transData)  # default transform

        self._bounds = None  # default bounds

        # Defer initial position determination. (Not much support for
        # non-rectangular axes is currently implemented, and this lets
        # them pass through the spines machinery without errors.)
        self._position = None
        _api.check_isinstance(mpath.Path, path=path)
        self._path = path

        # To support drawing both linear and circular spines, this
        # class implements Patch behavior three ways. If
        # self._patch_type == 'line', behave like a mpatches.PathPatch
        # instance. If self._patch_type == 'circle', behave like a
        # mpatches.Ellipse instance. If self._patch_type == 'arc', behave like
        # a mpatches.Arc instance.
        self._patch_type = 'line'

        # Behavior copied from mpatches.Ellipse:
        # Note: This cannot be calculated until this is added to an Axes
        self._patch_transform = mtransforms.IdentityTransform()

    def set_patch_arc(self, center, radius, theta1, theta2):
        """Set the spine to be arc-like."""
        self._patch_type = 'arc'
        self._center = center
        self._width = radius * 2
        self._height = radius * 2
        self._theta1 = theta1
        self._theta2 = theta2
        self._path = mpath.Path.arc(theta1, theta2)
        # arc drawn on axes transform
        self.set_transform(self.axes.transAxes)
        self.stale = True

    def set_patch_circle(self, center, radius):
        """Set the spine to be circular."""
        self._patch_type = 'circle'
        self._center = center
        self._width = radius * 2
        self._height = radius * 2
        # circle drawn on axes transform
        self.set_transform(self.axes.transAxes)
        self.stale = True

    def set_patch_line(self):
        """Set the spine to be linear."""
        self._patch_type = 'line'
        self.stale = True

    # Behavior copied from mpatches.Ellipse:
    def _recompute_transform(self):
        """
        Notes
        -----
        This cannot be called until after this has been added to an Axes,
        otherwise unit conversion will fail. This makes it very important to
        call the accessor method and not directly access the transformation
        member variable.
        """
        assert self._patch_type in ('arc', 'circle')
        center = (self.convert_xunits(self._center[0]),
                  self.convert_yunits(self._center[1]))
        width = self.convert_xunits(self._width)
        height = self.convert_yunits(self._height)
        self._patch_transform = mtransforms.Affine2D() \
            .scale(width * 0.5, height * 0.5) \
            .translate(*center)

    def get_patch_transform(self):
        if self._patch_type in ('arc', 'circle'):
            self._recompute_transform()
            return self._patch_transform
        else:
            return super().get_patch_transform()

    def get_window_extent(self, renderer=None):
        """
        Return the window extent of the spines in display space, including
        padding for ticks (but not their labels)

        See Also
        --------
        matplotlib.axes.Axes.get_tightbbox
        matplotlib.axes.Axes.get_window_extent
        """
        # make sure the location is updated so that transforms etc are correct:
        self._adjust_location()
        bb = super().get_window_extent(renderer=renderer)
        if self.axis is None or not self.axis.get_visible():
            return bb
        bboxes = [bb]
        drawn_ticks = self.axis._update_ticks()

        major_tick = next(iter({*drawn_ticks} & {*self.axis.majorTicks}), None)
        minor_tick = next(iter({*drawn_ticks} & {*self.axis.minorTicks}), None)
        for tick in [major_tick, minor_tick]:
            if tick is None:
                continue
            bb0 = bb.frozen()
            tickl = tick._size
            tickdir = tick._tickdir
            if tickdir == 'out':
                padout = 1
                padin = 0
            elif tickdir == 'in':
                padout = 0
                padin = 1
            else:
                padout = 0.5
                padin = 0.5
            dpi = self.get_figure(root=True).dpi
            padout = padout * tickl / 72 * dpi
            padin = padin * tickl / 72 * dpi

            if tick.tick1line.get_visible():
                if self.spine_type == 'left':
                    bb0.x0 = bb0.x0 - padout
                    bb0.x1 = bb0.x1 + padin
                elif self.spine_type == 'bottom':
                    bb0.y0 = bb0.y0 - padout
                    bb0.y1 = bb0.y1 + padin

            if tick.tick2line.get_visible():
                if self.spine_type == 'right':
                    bb0.x1 = bb0.x1 + padout
                    bb0.x0 = bb0.x0 - padin
                elif self.spine_type == 'top':
                    bb0.y1 = bb0.y1 + padout
                    bb0.y0 = bb0.y0 - padout
            bboxes.append(bb0)

        return mtransforms.Bbox.union(bboxes)

    def get_path(self):
        return self._path

    def _ensure_position_is_set(self):
        if self._position is None:
            # default position
            self._position = ('outward', 0.0)  # in points
            self.set_position(self._position)

    def register_axis(self, axis):
        """
        Register an axis.

        An axis should be registered with its corresponding spine from
        the Axes instance. This allows the spine to clear any axis
        properties when needed.
        """
        self.axis = axis
        self.stale = True

    def clear(self):
        """Clear the current spine."""
        self._clear()
        if self.axis is not None:
            self.axis.clear()

    def _clear(self):
        """
        Clear things directly related to the spine.

        In this way it is possible to avoid clearing the Axis as well when calling
        from library code where it is known that the Axis is cleared separately.
        """
        self._position = None  # clear position

    def _adjust_location(self):
        """Automatically set spine bounds to the view interval."""

        if self.spine_type == 'circle':
            return

        if self._bounds is not None:
            low, high = self._bounds
        elif self.spine_type in ('left', 'right'):
            low, high = self.axes.viewLim.intervaly
        elif self.spine_type in ('top', 'bottom'):
            low, high = self.axes.viewLim.intervalx
        else:
            raise ValueError(f'unknown spine spine_type: {self.spine_type}')

        if self._patch_type == 'arc':
            if self.spine_type in ('bottom', 'top'):
                try:
                    direction = self.axes.get_theta_direction()
                except AttributeError:
                    direction = 1
                try:
                    offset = self.axes.get_theta_offset()
                except AttributeError:
                    offset = 0
                low = low * direction + offset
                high = high * direction + offset
                if low > high:
                    low, high = high, low

                self._path = mpath.Path.arc(np.rad2deg(low), np.rad2deg(high))

                if self.spine_type == 'bottom':
                    if self.axis is None:
                        tr = mtransforms.IdentityTransform()
                    else:
                        tr = self.axis.get_transform()
                    rmin, rmax = tr.transform(self.axes.viewLim.intervaly)
                    try:
                        rorigin = self.axes.get_rorigin()
                    except AttributeError:
                        rorigin = rmin
                    else:
                        rorigin = tr.transform(rorigin)
                    scaled_diameter = (rmin - rorigin) / (rmax - rorigin)
                    self._height = scaled_diameter
                    self._width = scaled_diameter

            else:
                raise ValueError('unable to set bounds for spine "%s"' %
                                 self.spine_type)
        else:
            v1 = self._path.vertices
            assert v1.shape == (2, 2), 'unexpected vertices shape'
            if self.spine_type in ['left', 'right']:
                v1[0, 1] = low
                v1[1, 1] = high
            elif self.spine_type in ['bottom', 'top']:
                v1[0, 0] = low
                v1[1, 0] = high
            else:
                raise ValueError('unable to set bounds for spine "%s"' %
                                 self.spine_type)

    @allow_rasterization
    def draw(self, renderer):
        self._adjust_location()
        ret = super().draw(renderer)
        self.stale = False
        return ret

    def set_position(self, position):
        """
        Set the position of the spine.

        Spine position is specified by a 2 tuple of (position type,
        amount). The position types are:

        * 'outward': place the spine out from the data area by the specified
          number of points. (Negative values place the spine inwards.)
        * 'axes': place the spine at the specified Axes coordinate (0 to 1).
        * 'data': place the spine at the specified data coordinate.

        Additionally, shorthand notations define a special positions:

        * 'center' -> ``('axes', 0.5)``
        * 'zero' -> ``('data', 0.0)``

        Examples
        --------
        :doc:`/gallery/spines/spine_placement_demo`
        """
        if position in ('center', 'zero'):  # special positions
            pass
        else:
            if len(position) != 2:
                raise ValueError("position should be 'center' or 2-tuple")
            if position[0] not in ['outward', 'axes', 'data']:
                raise ValueError("position[0] should be one of 'outward', "
                                 "'axes', or 'data' ")
        self._position = position
        self.set_transform(self.get_spine_transform())
        if self.axis is not None:
            self.axis.reset_ticks()
        self.stale = True

    def get_position(self):
        """Return the spine position."""
        self._ensure_position_is_set()
        return self._position

    def get_spine_transform(self):
        """Return the spine transform."""
        self._ensure_position_is_set()

        position = self._position
        if isinstance(position, str):
            if position == 'center':
                position = ('axes', 0.5)
            elif position == 'zero':
                position = ('data', 0)
        assert len(position) == 2, 'position should be 2-tuple'
        position_type, amount = position
        _api.check_in_list(['axes', 'outward', 'data'],
                           position_type=position_type)
        if self.spine_type in ['left', 'right']:
            base_transform = self.axes.get_yaxis_transform(which='grid')
        elif self.spine_type in ['top', 'bottom']:
            base_transform = self.axes.get_xaxis_transform(which='grid')
        else:
            raise ValueError(f'unknown spine spine_type: {self.spine_type!r}')

        if position_type == 'outward':
            if amount == 0:  # short circuit commonest case
                return base_transform
            else:
                offset_vec = {'left': (-1, 0), 'right': (1, 0),
                              'bottom': (0, -1), 'top': (0, 1),
                              }[self.spine_type]
                # calculate x and y offset in dots
                offset_dots = amount * np.array(offset_vec) / 72
                return (base_transform
                        + mtransforms.ScaledTranslation(
                            *offset_dots, self.get_figure(root=False).dpi_scale_trans))
        elif position_type == 'axes':
            if self.spine_type in ['left', 'right']:
                # keep y unchanged, fix x at amount
                return (mtransforms.Affine2D.from_values(0, 0, 0, 1, amount, 0)
                        + base_transform)
            elif self.spine_type in ['bottom', 'top']:
                # keep x unchanged, fix y at amount
                return (mtransforms.Affine2D.from_values(1, 0, 0, 0, 0, amount)
                        + base_transform)
        elif position_type == 'data':
            if self.spine_type in ('right', 'top'):
                # The right and top spines have a default position of 1 in
                # axes coordinates.  When specifying the position in data
                # coordinates, we need to calculate the position relative to 0.
                amount -= 1
            if self.spine_type in ('left', 'right'):
                return mtransforms.blended_transform_factory(
                    mtransforms.Affine2D().translate(amount, 0)
                    + self.axes.transData,
                    self.axes.transData)
            elif self.spine_type in ('bottom', 'top'):
                return mtransforms.blended_transform_factory(
                    self.axes.transData,
                    mtransforms.Affine2D().translate(0, amount)
                    + self.axes.transData)

    def set_bounds(self, low=None, high=None):
        """
        Set the spine bounds.

        Parameters
        ----------
        low : float or None, optional
            The lower spine bound. Passing *None* leaves the limit unchanged.

            The bounds may also be passed as the tuple (*low*, *high*) as the
            first positional argument.

            .. ACCEPTS: (low: float, high: float)

        high : float or None, optional
            The higher spine bound. Passing *None* leaves the limit unchanged.
        """
        if self.spine_type == 'circle':
            raise ValueError(
                'set_bounds() method incompatible with circular spines')
        if high is None and np.iterable(low):
            low, high = low
        old_low, old_high = self.get_bounds() or (None, None)
        if low is None:
            low = old_low
        if high is None:
            high = old_high
        self._bounds = (low, high)
        self.stale = True

    def get_bounds(self):
        """Get the bounds of the spine."""
        return self._bounds

    @classmethod
    def linear_spine(cls, axes, spine_type, **kwargs):
        """Create and return a linear `Spine`."""
        # all values of 0.999 get replaced upon call to set_bounds()
        if spine_type == 'left':
            path = mpath.Path([(0.0, 0.999), (0.0, 0.999)])
        elif spine_type == 'right':
            path = mpath.Path([(1.0, 0.999), (1.0, 0.999)])
        elif spine_type == 'bottom':
            path = mpath.Path([(0.999, 0.0), (0.999, 0.0)])
        elif spine_type == 'top':
            path = mpath.Path([(0.999, 1.0), (0.999, 1.0)])
        else:
            raise ValueError('unable to make path for spine "%s"' % spine_type)
        result = cls(axes, spine_type, path, **kwargs)
        result.set_visible(mpl.rcParams[f'axes.spines.{spine_type}'])

        return result

    @classmethod
    def arc_spine(cls, axes, spine_type, center, radius, theta1, theta2,
                  **kwargs):
        """Create and return an arc `Spine`."""
        path = mpath.Path.arc(theta1, theta2)
        result = cls(axes, spine_type, path, **kwargs)
        result.set_patch_arc(center, radius, theta1, theta2)
        return result

    @classmethod
    def circular_spine(cls, axes, center, radius, **kwargs):
        """Create and return a circular `Spine`."""
        path = mpath.Path.unit_circle()
        spine_type = 'circle'
        result = cls(axes, spine_type, path, **kwargs)
        result.set_patch_circle(center, radius)
        return result

    def set_color(self, c):
        """
        Set the edgecolor.

        Parameters
        ----------
        c : :mpltype:`color`

        Notes
        -----
        This method does not modify the facecolor (which defaults to "none"),
        unlike the `.Patch.set_color` method defined in the parent class.  Use
        `.Patch.set_facecolor` to set the facecolor.
        """
        self.set_edgecolor(c)
        self.stale = True


class SpinesProxy:
    """
    A proxy to broadcast ``set_*()`` and ``set()`` method calls to contained `.Spines`.

    The proxy cannot be used for any other operations on its members.

    The supported methods are determined dynamically based on the contained
    spines. If not all spines support a given method, it's executed only on
    the subset of spines that support it.
    """
    def __init__(self, spine_dict):
        self._spine_dict = spine_dict

    def __getattr__(self, name):
        broadcast_targets = [spine for spine in self._spine_dict.values()
                             if hasattr(spine, name)]
        if (name != 'set' and not name.startswith('set_')) or not broadcast_targets:
            raise AttributeError(
                f"'SpinesProxy' object has no attribute '{name}'")

        def x(_targets, _funcname, *args, **kwargs):
            for spine in _targets:
                getattr(spine, _funcname)(*args, **kwargs)
        x = functools.partial(x, broadcast_targets, name)
        x.__doc__ = broadcast_targets[0].__doc__
        return x

    def __dir__(self):
        names = []
        for spine in self._spine_dict.values():
            names.extend(name
                         for name in dir(spine) if name.startswith('set_'))
        return list(sorted(set(names)))


class Spines(MutableMapping):
    r"""
    The container of all `.Spine`\s in an Axes.

    The interface is dict-like mapping names (e.g. 'left') to `.Spine` objects.
    Additionally, it implements some pandas.Series-like features like accessing
    elements by attribute::

        spines['top'].set_visible(False)
        spines.top.set_visible(False)

    Multiple spines can be addressed simultaneously by passing a list::

        spines[['top', 'right']].set_visible(False)

    Use an open slice to address all spines::

        spines[:].set_visible(False)

    The latter two indexing methods will return a `SpinesProxy` that broadcasts all
    ``set_*()`` and ``set()`` calls to its members, but cannot be used for any other
    operation.
    """
    def __init__(self, **kwargs):
        self._dict = kwargs

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def __getstate__(self):
        return self._dict

    def __setstate__(self, state):
        self.__init__(**state)

    def __getattr__(self, name):
        try:
            return self._dict[name]
        except KeyError:
            raise AttributeError(
                f"'Spines' object does not contain a '{name}' spine")

    def __getitem__(self, key):
        if isinstance(key, list):
            unknown_keys = [k for k in key if k not in self._dict]
            if unknown_keys:
                raise KeyError(', '.join(unknown_keys))
            return SpinesProxy({k: v for k, v in self._dict.items()
                                if k in key})
        if isinstance(key, tuple):
            raise ValueError('Multiple spines must be passed as a single list')
        if isinstance(key, slice):
            if key.start is None and key.stop is None and key.step is None:
                return SpinesProxy(self._dict)
            else:
                raise ValueError(
                    'Spines does not support slicing except for the fully '
                    'open slice [:] to access all spines.')
        return self._dict[key]

    def __setitem__(self, key, value):
        # TODO: Do we want to deprecate adding spines?
        self._dict[key] = value

    def __delitem__(self, key):
        # TODO: Do we want to deprecate deleting spines?
        del self._dict[key]

    def __iter__(self):
        return iter(self._dict)

    def __len__(self):
        return len(self._dict)
