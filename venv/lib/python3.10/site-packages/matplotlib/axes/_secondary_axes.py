import numbers

import numpy as np

from matplotlib import _api, _docstring, transforms
import matplotlib.ticker as mticker
from matplotlib.axes._base import _AxesBase, _TransformedBoundsLocator
from matplotlib.axis import Axis
from matplotlib.transforms import Transform


class SecondaryAxis(_AxesBase):
    """
    General class to hold a Secondary_X/Yaxis.
    """

    def __init__(self, parent, orientation, location, functions, transform=None,
                 **kwargs):
        """
        See `.secondary_xaxis` and `.secondary_yaxis` for the doc string.
        While there is no need for this to be private, it should really be
        called by those higher level functions.
        """
        _api.check_in_list(["x", "y"], orientation=orientation)
        self._functions = functions
        self._parent = parent
        self._orientation = orientation
        self._ticks_set = False

        fig = self._parent.get_figure(root=False)
        if self._orientation == 'x':
            super().__init__(fig, [0, 1., 1, 0.0001], **kwargs)
            self._axis = self.xaxis
            self._locstrings = ['top', 'bottom']
            self._otherstrings = ['left', 'right']
        else:  # 'y'
            super().__init__(fig, [0, 1., 0.0001, 1], **kwargs)
            self._axis = self.yaxis
            self._locstrings = ['right', 'left']
            self._otherstrings = ['top', 'bottom']
        self._parentscale = None
        # this gets positioned w/o constrained_layout so exclude:

        self.set_location(location, transform)
        self.set_functions(functions)

        # styling:
        otheraxis = self.yaxis if self._orientation == 'x' else self.xaxis
        otheraxis.set_major_locator(mticker.NullLocator())
        otheraxis.set_ticks_position('none')

        self.spines[self._otherstrings].set_visible(False)
        self.spines[self._locstrings].set_visible(True)

        if self._pos < 0.5:
            # flip the location strings...
            self._locstrings = self._locstrings[::-1]
        self.set_alignment(self._locstrings[0])

    def set_alignment(self, align):
        """
        Set if axes spine and labels are drawn at top or bottom (or left/right)
        of the Axes.

        Parameters
        ----------
        align : {'top', 'bottom', 'left', 'right'}
            Either 'top' or 'bottom' for orientation='x' or
            'left' or 'right' for orientation='y' axis.
        """
        _api.check_in_list(self._locstrings, align=align)
        if align == self._locstrings[1]:  # Need to change the orientation.
            self._locstrings = self._locstrings[::-1]
        self.spines[self._locstrings[0]].set_visible(True)
        self.spines[self._locstrings[1]].set_visible(False)
        self._axis.set_ticks_position(align)
        self._axis.set_label_position(align)

    def set_location(self, location, transform=None):
        """
        Set the vertical or horizontal location of the axes in
        parent-normalized coordinates.

        Parameters
        ----------
        location : {'top', 'bottom', 'left', 'right'} or float
            The position to put the secondary axis.  Strings can be 'top' or
            'bottom' for orientation='x' and 'right' or 'left' for
            orientation='y'. A float indicates the relative position on the
            parent Axes to put the new Axes, 0.0 being the bottom (or left)
            and 1.0 being the top (or right).

        transform : `.Transform`, optional
            Transform for the location to use. Defaults to
            the parent's ``transAxes``, so locations are normally relative to
            the parent axes.

            .. versionadded:: 3.9
        """

        _api.check_isinstance((transforms.Transform, None), transform=transform)

        # This puts the rectangle into figure-relative coordinates.
        if isinstance(location, str):
            _api.check_in_list(self._locstrings, location=location)
            self._pos = 1. if location in ('top', 'right') else 0.
        elif isinstance(location, numbers.Real):
            self._pos = location
        else:
            raise ValueError(
                f"location must be {self._locstrings[0]!r}, "
                f"{self._locstrings[1]!r}, or a float, not {location!r}")

        self._loc = location

        if self._orientation == 'x':
            # An x-secondary axes is like an inset axes from x = 0 to x = 1 and
            # from y = pos to y = pos + eps, in the parent's transAxes coords.
            bounds = [0, self._pos, 1., 1e-10]

            # If a transformation is provided, use its y component rather than
            # the parent's transAxes. This can be used to place axes in the data
            # coords, for instance.
            if transform is not None:
                transform = transforms.blended_transform_factory(
                    self._parent.transAxes, transform)
        else:  # 'y'
            bounds = [self._pos, 0, 1e-10, 1]
            if transform is not None:
                transform = transforms.blended_transform_factory(
                    transform, self._parent.transAxes)  # Use provided x axis

        # If no transform is provided, use the parent's transAxes
        if transform is None:
            transform = self._parent.transAxes

        # this locator lets the axes move in the parent axes coordinates.
        # so it never needs to know where the parent is explicitly in
        # figure coordinates.
        # it gets called in ax.apply_aspect() (of all places)
        self.set_axes_locator(_TransformedBoundsLocator(bounds, transform))

    def apply_aspect(self, position=None):
        # docstring inherited.
        self._set_lims()
        super().apply_aspect(position)

    @_docstring.copy(Axis.set_ticks)
    def set_ticks(self, ticks, labels=None, *, minor=False, **kwargs):
        ret = self._axis.set_ticks(ticks, labels, minor=minor, **kwargs)
        self.stale = True
        self._ticks_set = True
        return ret

    def set_functions(self, functions):
        """
        Set how the secondary axis converts limits from the parent Axes.

        Parameters
        ----------
        functions : 2-tuple of func, or `Transform` with an inverse.
            Transform between the parent axis values and the secondary axis
            values.

            If supplied as a 2-tuple of functions, the first function is
            the forward transform function and the second is the inverse
            transform.

            If a transform is supplied, then the transform must have an
            inverse.
        """

        if (isinstance(functions, tuple) and len(functions) == 2 and
                callable(functions[0]) and callable(functions[1])):
            # make an arbitrary convert from a two-tuple of functions
            # forward and inverse.
            self._functions = functions
        elif isinstance(functions, Transform):
            self._functions = (
                 functions.transform,
                 lambda x: functions.inverted().transform(x)
            )
        elif functions is None:
            self._functions = (lambda x: x, lambda x: x)
        else:
            raise ValueError('functions argument of secondary Axes '
                             'must be a two-tuple of callable functions '
                             'with the first function being the transform '
                             'and the second being the inverse')
        self._set_scale()

    def draw(self, renderer):
        """
        Draw the secondary Axes.

        Consults the parent Axes for its limits and converts them
        using the converter specified by
        `~.axes._secondary_axes.set_functions` (or *functions*
        parameter when Axes initialized.)
        """
        self._set_lims()
        # this sets the scale in case the parent has set its scale.
        self._set_scale()
        super().draw(renderer)

    def _set_scale(self):
        """
        Check if parent has set its scale
        """

        if self._orientation == 'x':
            pscale = self._parent.xaxis.get_scale()
            set_scale = self.set_xscale
        else:  # 'y'
            pscale = self._parent.yaxis.get_scale()
            set_scale = self.set_yscale
        if pscale == self._parentscale:
            return

        if self._ticks_set:
            ticks = self._axis.get_ticklocs()

        # need to invert the roles here for the ticks to line up.
        set_scale('functionlog' if pscale == 'log' else 'function',
                  functions=self._functions[::-1])

        # OK, set_scale sets the locators, but if we've called
        # axsecond.set_ticks, we want to keep those.
        if self._ticks_set:
            self._axis.set_major_locator(mticker.FixedLocator(ticks))

        # If the parent scale doesn't change, we can skip this next time.
        self._parentscale = pscale

    def _set_lims(self):
        """
        Set the limits based on parent limits and the convert method
        between the parent and this secondary Axes.
        """
        if self._orientation == 'x':
            lims = self._parent.get_xlim()
            set_lim = self.set_xlim
        else:  # 'y'
            lims = self._parent.get_ylim()
            set_lim = self.set_ylim
        order = lims[0] < lims[1]
        lims = self._functions[0](np.array(lims))
        neworder = lims[0] < lims[1]
        if neworder != order:
            # Flip because the transform will take care of the flipping.
            lims = lims[::-1]
        set_lim(lims)

    def set_aspect(self, *args, **kwargs):
        """
        Secondary Axes cannot set the aspect ratio, so calling this just
        sets a warning.
        """
        _api.warn_external("Secondary Axes can't set the aspect ratio")

    def set_color(self, color):
        """
        Change the color of the secondary Axes and all decorators.

        Parameters
        ----------
        color : :mpltype:`color`
        """
        axis = self._axis_map[self._orientation]
        axis.set_tick_params(colors=color)
        for spine in self.spines.values():
            if spine.axis is axis:
                spine.set_color(color)
        axis.label.set_color(color)


_secax_docstring = '''
Warnings
--------
This method is experimental as of 3.1, and the API may change.

Parameters
----------
location : {'top', 'bottom', 'left', 'right'} or float
    The position to put the secondary axis.  Strings can be 'top' or
    'bottom' for orientation='x' and 'right' or 'left' for
    orientation='y'. A float indicates the relative position on the
    parent Axes to put the new Axes, 0.0 being the bottom (or left)
    and 1.0 being the top (or right).

functions : 2-tuple of func, or Transform with an inverse

    If a 2-tuple of functions, the user specifies the transform
    function and its inverse.  i.e.
    ``functions=(lambda x: 2 / x, lambda x: 2 / x)`` would be an
    reciprocal transform with a factor of 2. Both functions must accept
    numpy arrays as input.

    The user can also directly supply a subclass of
    `.transforms.Transform` so long as it has an inverse.

    See :doc:`/gallery/subplots_axes_and_figures/secondary_axis`
    for examples of making these conversions.

transform : `.Transform`, optional
    If specified, *location* will be
    placed relative to this transform (in the direction of the axis)
    rather than the parent's axis. i.e. a secondary x-axis will
    use the provided y transform and the x transform of the parent.

    .. versionadded:: 3.9

Returns
-------
ax : axes._secondary_axes.SecondaryAxis

Other Parameters
----------------
**kwargs : `~matplotlib.axes.Axes` properties.
    Other miscellaneous Axes parameters.
'''
_docstring.interpd.register(_secax_docstring=_secax_docstring)
