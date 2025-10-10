"""
axes3d.py, original mplot3d version by John Porter
Created: 23 Sep 2005

Parts fixed by Reinier Heeres <reinier@heeres.eu>
Minor additions by Ben Axelrod <baxelrod@coroware.com>
Significant updates and revisions by Ben Root <ben.v.root@gmail.com>

Module containing Axes3D, an object which can plot 3D objects on a
2D matplotlib figure.
"""

from collections import defaultdict
import itertools
import math
import textwrap
import warnings

import numpy as np

import matplotlib as mpl
from matplotlib import _api, cbook, _docstring, _preprocess_data
import matplotlib.artist as martist
import matplotlib.collections as mcoll
import matplotlib.colors as mcolors
import matplotlib.image as mimage
import matplotlib.lines as mlines
import matplotlib.patches as mpatches
import matplotlib.container as mcontainer
import matplotlib.transforms as mtransforms
from matplotlib.axes import Axes
from matplotlib.axes._base import _axis_method_wrapper, _process_plot_format
from matplotlib.transforms import Bbox
from matplotlib.tri._triangulation import Triangulation

from . import art3d
from . import proj3d
from . import axis3d


@_docstring.interpd
@_api.define_aliases({
    "xlim": ["xlim3d"], "ylim": ["ylim3d"], "zlim": ["zlim3d"]})
class Axes3D(Axes):
    """
    3D Axes object.

    .. note::

        As a user, you do not instantiate Axes directly, but use Axes creation
        methods instead; e.g. from `.pyplot` or `.Figure`:
        `~.pyplot.subplots`, `~.pyplot.subplot_mosaic` or `.Figure.add_axes`.
    """
    name = '3d'

    _axis_names = ("x", "y", "z")
    Axes._shared_axes["z"] = cbook.Grouper()
    Axes._shared_axes["view"] = cbook.Grouper()

    def __init__(
        self, fig, rect=None, *args,
        elev=30, azim=-60, roll=0, shareview=None, sharez=None,
        proj_type='persp', focal_length=None,
        box_aspect=None,
        computed_zorder=True,
        **kwargs,
    ):
        """
        Parameters
        ----------
        fig : Figure
            The parent figure.
        rect : tuple (left, bottom, width, height), default: None.
            The ``(left, bottom, width, height)`` Axes position.
        elev : float, default: 30
            The elevation angle in degrees rotates the camera above and below
            the x-y plane, with a positive angle corresponding to a location
            above the plane.
        azim : float, default: -60
            The azimuthal angle in degrees rotates the camera about the z axis,
            with a positive angle corresponding to a right-handed rotation. In
            other words, a positive azimuth rotates the camera about the origin
            from its location along the +x axis towards the +y axis.
        roll : float, default: 0
            The roll angle in degrees rotates the camera about the viewing
            axis. A positive angle spins the camera clockwise, causing the
            scene to rotate counter-clockwise.
        shareview : Axes3D, optional
            Other Axes to share view angles with.  Note that it is not possible
            to unshare axes.
        sharez : Axes3D, optional
            Other Axes to share z-limits with.  Note that it is not possible to
            unshare axes.
        proj_type : {'persp', 'ortho'}
            The projection type, default 'persp'.
        focal_length : float, default: None
            For a projection type of 'persp', the focal length of the virtual
            camera. Must be > 0. If None, defaults to 1.
            For a projection type of 'ortho', must be set to either None
            or infinity (numpy.inf). If None, defaults to infinity.
            The focal length can be computed from a desired Field Of View via
            the equation: focal_length = 1/tan(FOV/2)
        box_aspect : 3-tuple of floats, default: None
            Changes the physical dimensions of the Axes3D, such that the ratio
            of the axis lengths in display units is x:y:z.
            If None, defaults to 4:4:3
        computed_zorder : bool, default: True
            If True, the draw order is computed based on the average position
            of the `.Artist`\\s along the view direction.
            Set to False if you want to manually control the order in which
            Artists are drawn on top of each other using their *zorder*
            attribute. This can be used for fine-tuning if the automatic order
            does not produce the desired result. Note however, that a manual
            zorder will only be correct for a limited view angle. If the figure
            is rotated by the user, it will look wrong from certain angles.

        **kwargs
            Other optional keyword arguments:

            %(Axes3D:kwdoc)s
        """

        if rect is None:
            rect = [0.0, 0.0, 1.0, 1.0]

        self.initial_azim = azim
        self.initial_elev = elev
        self.initial_roll = roll
        self.set_proj_type(proj_type, focal_length)
        self.computed_zorder = computed_zorder

        self.xy_viewLim = Bbox.unit()
        self.zz_viewLim = Bbox.unit()
        xymargin = 0.05 * 10/11  # match mpl3.8 appearance
        self.xy_dataLim = Bbox([[xymargin, xymargin],
                                [1 - xymargin, 1 - xymargin]])
        # z-limits are encoded in the x-component of the Bbox, y is un-used
        self.zz_dataLim = Bbox.unit()

        # inhibit autoscale_view until the axes are defined
        # they can't be defined until Axes.__init__ has been called
        self.view_init(self.initial_elev, self.initial_azim, self.initial_roll)

        self._sharez = sharez
        if sharez is not None:
            self._shared_axes["z"].join(self, sharez)
            self._adjustable = 'datalim'

        self._shareview = shareview
        if shareview is not None:
            self._shared_axes["view"].join(self, shareview)

        if kwargs.pop('auto_add_to_figure', False):
            raise AttributeError(
                'auto_add_to_figure is no longer supported for Axes3D. '
                'Use fig.add_axes(ax) instead.'
            )

        super().__init__(
            fig, rect, frameon=True, box_aspect=box_aspect, *args, **kwargs
        )
        # Disable drawing of axes by base class
        super().set_axis_off()
        # Enable drawing of axes by Axes3D class
        self.set_axis_on()
        self.M = None
        self.invM = None

        self._view_margin = 1/48  # default value to match mpl3.8
        self.autoscale_view()

        # func used to format z -- fall back on major formatters
        self.fmt_zdata = None

        self.mouse_init()
        fig = self.get_figure(root=True)
        fig.canvas.callbacks._connect_picklable(
            'motion_notify_event', self._on_move)
        fig.canvas.callbacks._connect_picklable(
            'button_press_event', self._button_press)
        fig.canvas.callbacks._connect_picklable(
            'button_release_event', self._button_release)
        self.set_top_view()

        self.patch.set_linewidth(0)
        # Calculate the pseudo-data width and height
        pseudo_bbox = self.transLimits.inverted().transform([(0, 0), (1, 1)])
        self._pseudo_w, self._pseudo_h = pseudo_bbox[1] - pseudo_bbox[0]

        # mplot3d currently manages its own spines and needs these turned off
        # for bounding box calculations
        self.spines[:].set_visible(False)

    def set_axis_off(self):
        self._axis3don = False
        self.stale = True

    def set_axis_on(self):
        self._axis3don = True
        self.stale = True

    def convert_zunits(self, z):
        """
        For artists in an Axes, if the zaxis has units support,
        convert *z* using zaxis unit type
        """
        return self.zaxis.convert_units(z)

    def set_top_view(self):
        # this happens to be the right view for the viewing coordinates
        # moved up and to the left slightly to fit labels and axes
        xdwl = 0.95 / self._dist
        xdw = 0.9 / self._dist
        ydwl = 0.95 / self._dist
        ydw = 0.9 / self._dist
        # Set the viewing pane.
        self.viewLim.intervalx = (-xdwl, xdw)
        self.viewLim.intervaly = (-ydwl, ydw)
        self.stale = True

    def _init_axis(self):
        """Init 3D Axes; overrides creation of regular X/Y Axes."""
        self.xaxis = axis3d.XAxis(self)
        self.yaxis = axis3d.YAxis(self)
        self.zaxis = axis3d.ZAxis(self)

    def get_zaxis(self):
        """Return the ``ZAxis`` (`~.axis3d.Axis`) instance."""
        return self.zaxis

    get_zgridlines = _axis_method_wrapper("zaxis", "get_gridlines")
    get_zticklines = _axis_method_wrapper("zaxis", "get_ticklines")

    def _transformed_cube(self, vals):
        """Return cube with limits from *vals* transformed by self.M."""
        minx, maxx, miny, maxy, minz, maxz = vals
        xyzs = [(minx, miny, minz),
                (maxx, miny, minz),
                (maxx, maxy, minz),
                (minx, maxy, minz),
                (minx, miny, maxz),
                (maxx, miny, maxz),
                (maxx, maxy, maxz),
                (minx, maxy, maxz)]
        return proj3d._proj_points(xyzs, self.M)

    def set_aspect(self, aspect, adjustable=None, anchor=None, share=False):
        """
        Set the aspect ratios.

        Parameters
        ----------
        aspect : {'auto', 'equal', 'equalxy', 'equalxz', 'equalyz'}
            Possible values:

            =========   ==================================================
            value       description
            =========   ==================================================
            'auto'      automatic; fill the position rectangle with data.
            'equal'     adapt all the axes to have equal aspect ratios.
            'equalxy'   adapt the x and y axes to have equal aspect ratios.
            'equalxz'   adapt the x and z axes to have equal aspect ratios.
            'equalyz'   adapt the y and z axes to have equal aspect ratios.
            =========   ==================================================

        adjustable : None or {'box', 'datalim'}, optional
            If not *None*, this defines which parameter will be adjusted to
            meet the required aspect. See `.set_adjustable` for further
            details.

        anchor : None or str or 2-tuple of float, optional
            If not *None*, this defines where the Axes will be drawn if there
            is extra space due to aspect constraints. The most common way to
            specify the anchor are abbreviations of cardinal directions:

            =====   =====================
            value   description
            =====   =====================
            'C'     centered
            'SW'    lower left corner
            'S'     middle of bottom edge
            'SE'    lower right corner
            etc.
            =====   =====================

            See `~.Axes.set_anchor` for further details.

        share : bool, default: False
            If ``True``, apply the settings to all shared Axes.

        See Also
        --------
        mpl_toolkits.mplot3d.axes3d.Axes3D.set_box_aspect
        """
        _api.check_in_list(('auto', 'equal', 'equalxy', 'equalyz', 'equalxz'),
                           aspect=aspect)
        super().set_aspect(
            aspect='auto', adjustable=adjustable, anchor=anchor, share=share)
        self._aspect = aspect

        if aspect in ('equal', 'equalxy', 'equalxz', 'equalyz'):
            ax_indices = self._equal_aspect_axis_indices(aspect)

            view_intervals = np.array([self.xaxis.get_view_interval(),
                                       self.yaxis.get_view_interval(),
                                       self.zaxis.get_view_interval()])
            ptp = np.ptp(view_intervals, axis=1)
            if self._adjustable == 'datalim':
                mean = np.mean(view_intervals, axis=1)
                scale = max(ptp[ax_indices] / self._box_aspect[ax_indices])
                deltas = scale * self._box_aspect

                for i, set_lim in enumerate((self.set_xlim3d,
                                             self.set_ylim3d,
                                             self.set_zlim3d)):
                    if i in ax_indices:
                        set_lim(mean[i] - deltas[i]/2., mean[i] + deltas[i]/2.,
                                auto=True, view_margin=None)
            else:  # 'box'
                # Change the box aspect such that the ratio of the length of
                # the unmodified axis to the length of the diagonal
                # perpendicular to it remains unchanged.
                box_aspect = np.array(self._box_aspect)
                box_aspect[ax_indices] = ptp[ax_indices]
                remaining_ax_indices = {0, 1, 2}.difference(ax_indices)
                if remaining_ax_indices:
                    remaining = remaining_ax_indices.pop()
                    old_diag = np.linalg.norm(self._box_aspect[ax_indices])
                    new_diag = np.linalg.norm(box_aspect[ax_indices])
                    box_aspect[remaining] *= new_diag / old_diag
                self.set_box_aspect(box_aspect)

    def _equal_aspect_axis_indices(self, aspect):
        """
        Get the indices for which of the x, y, z axes are constrained to have
        equal aspect ratios.

        Parameters
        ----------
        aspect : {'auto', 'equal', 'equalxy', 'equalxz', 'equalyz'}
            See descriptions in docstring for `.set_aspect()`.
        """
        ax_indices = []  # aspect == 'auto'
        if aspect == 'equal':
            ax_indices = [0, 1, 2]
        elif aspect == 'equalxy':
            ax_indices = [0, 1]
        elif aspect == 'equalxz':
            ax_indices = [0, 2]
        elif aspect == 'equalyz':
            ax_indices = [1, 2]
        return ax_indices

    def set_box_aspect(self, aspect, *, zoom=1):
        """
        Set the Axes box aspect.

        The box aspect is the ratio of height to width in display
        units for each face of the box when viewed perpendicular to
        that face.  This is not to be confused with the data aspect (see
        `~.Axes3D.set_aspect`). The default ratios are 4:4:3 (x:y:z).

        To simulate having equal aspect in data space, set the box
        aspect to match your data range in each dimension.

        *zoom* controls the overall size of the Axes3D in the figure.

        Parameters
        ----------
        aspect : 3-tuple of floats or None
            Changes the physical dimensions of the Axes3D, such that the ratio
            of the axis lengths in display units is x:y:z.
            If None, defaults to (4, 4, 3).

        zoom : float, default: 1
            Control overall size of the Axes3D in the figure. Must be > 0.
        """
        if zoom <= 0:
            raise ValueError(f'Argument zoom = {zoom} must be > 0')

        if aspect is None:
            aspect = np.asarray((4, 4, 3), dtype=float)
        else:
            aspect = np.asarray(aspect, dtype=float)
            _api.check_shape((3,), aspect=aspect)
        # The scale 1.8294640721620434 is tuned to match the mpl3.2 appearance.
        # The 25/24 factor is to compensate for the change in automargin
        # behavior in mpl3.9. This comes from the padding of 1/48 on both sides
        # of the axes in mpl3.8.
        aspect *= 1.8294640721620434 * 25/24 * zoom / np.linalg.norm(aspect)

        self._box_aspect = self._roll_to_vertical(aspect, reverse=True)
        self.stale = True

    def apply_aspect(self, position=None):
        if position is None:
            position = self.get_position(original=True)

        # in the superclass, we would go through and actually deal with axis
        # scales and box/datalim. Those are all irrelevant - all we need to do
        # is make sure our coordinate system is square.
        trans = self.get_figure().transSubfigure
        bb = mtransforms.Bbox.unit().transformed(trans)
        # this is the physical aspect of the panel (or figure):
        fig_aspect = bb.height / bb.width

        box_aspect = 1
        pb = position.frozen()
        pb1 = pb.shrunk_to_aspect(box_aspect, pb, fig_aspect)
        self._set_position(pb1.anchored(self.get_anchor(), pb), 'active')

    @martist.allow_rasterization
    def draw(self, renderer):
        if not self.get_visible():
            return
        self._unstale_viewLim()

        # draw the background patch
        self.patch.draw(renderer)
        self._frameon = False

        # first, set the aspect
        # this is duplicated from `axes._base._AxesBase.draw`
        # but must be called before any of the artist are drawn as
        # it adjusts the view limits and the size of the bounding box
        # of the Axes
        locator = self.get_axes_locator()
        self.apply_aspect(locator(self, renderer) if locator else None)

        # add the projection matrix to the renderer
        self.M = self.get_proj()
        self.invM = np.linalg.inv(self.M)

        collections_and_patches = (
            artist for artist in self._children
            if isinstance(artist, (mcoll.Collection, mpatches.Patch))
            and artist.get_visible())
        if self.computed_zorder:
            # Calculate projection of collections and patches and zorder
            # them. Make sure they are drawn above the grids.
            zorder_offset = max(axis.get_zorder()
                                for axis in self._axis_map.values()) + 1
            collection_zorder = patch_zorder = zorder_offset

            for artist in sorted(collections_and_patches,
                                 key=lambda artist: artist.do_3d_projection(),
                                 reverse=True):
                if isinstance(artist, mcoll.Collection):
                    artist.zorder = collection_zorder
                    collection_zorder += 1
                elif isinstance(artist, mpatches.Patch):
                    artist.zorder = patch_zorder
                    patch_zorder += 1
        else:
            for artist in collections_and_patches:
                artist.do_3d_projection()

        if self._axis3don:
            # Draw panes first
            for axis in self._axis_map.values():
                axis.draw_pane(renderer)
            # Then gridlines
            for axis in self._axis_map.values():
                axis.draw_grid(renderer)
            # Then axes, labels, text, and ticks
            for axis in self._axis_map.values():
                axis.draw(renderer)

        # Then rest
        super().draw(renderer)

    def get_axis_position(self):
        tc = self._transformed_cube(self.get_w_lims())
        xhigh = tc[1][2] > tc[2][2]
        yhigh = tc[3][2] > tc[2][2]
        zhigh = tc[0][2] > tc[2][2]
        return xhigh, yhigh, zhigh

    def update_datalim(self, xys, **kwargs):
        """
        Not implemented in `~mpl_toolkits.mplot3d.axes3d.Axes3D`.
        """
        pass

    get_autoscalez_on = _axis_method_wrapper("zaxis", "_get_autoscale_on")
    set_autoscalez_on = _axis_method_wrapper("zaxis", "_set_autoscale_on")

    def get_zmargin(self):
        """
        Retrieve autoscaling margin of the z-axis.

        .. versionadded:: 3.9

        Returns
        -------
        zmargin : float

        See Also
        --------
        mpl_toolkits.mplot3d.axes3d.Axes3D.set_zmargin
        """
        return self._zmargin

    def set_zmargin(self, m):
        """
        Set padding of Z data limits prior to autoscaling.

        *m* times the data interval will be added to each end of that interval
        before it is used in autoscaling.  If *m* is negative, this will clip
        the data range instead of expanding it.

        For example, if your data is in the range [0, 2], a margin of 0.1 will
        result in a range [-0.2, 2.2]; a margin of -0.1 will result in a range
        of [0.2, 1.8].

        Parameters
        ----------
        m : float greater than -0.5
        """
        if m <= -0.5:
            raise ValueError("margin must be greater than -0.5")
        self._zmargin = m
        self._request_autoscale_view("z")
        self.stale = True

    def margins(self, *margins, x=None, y=None, z=None, tight=True):
        """
        Set or retrieve autoscaling margins.

        See `.Axes.margins` for full documentation.  Because this function
        applies to 3D Axes, it also takes a *z* argument, and returns
        ``(xmargin, ymargin, zmargin)``.
        """
        if margins and (x is not None or y is not None or z is not None):
            raise TypeError('Cannot pass both positional and keyword '
                            'arguments for x, y, and/or z.')
        elif len(margins) == 1:
            x = y = z = margins[0]
        elif len(margins) == 3:
            x, y, z = margins
        elif margins:
            raise TypeError('Must pass a single positional argument for all '
                            'margins, or one for each margin (x, y, z).')

        if x is None and y is None and z is None:
            if tight is not True:
                _api.warn_external(f'ignoring tight={tight!r} in get mode')
            return self._xmargin, self._ymargin, self._zmargin

        if x is not None:
            self.set_xmargin(x)
        if y is not None:
            self.set_ymargin(y)
        if z is not None:
            self.set_zmargin(z)

        self.autoscale_view(
            tight=tight, scalex=(x is not None), scaley=(y is not None),
            scalez=(z is not None)
        )

    def autoscale(self, enable=True, axis='both', tight=None):
        """
        Convenience method for simple axis view autoscaling.

        See `.Axes.autoscale` for full documentation.  Because this function
        applies to 3D Axes, *axis* can also be set to 'z', and setting *axis*
        to 'both' autoscales all three axes.
        """
        if enable is None:
            scalex = True
            scaley = True
            scalez = True
        else:
            if axis in ['x', 'both']:
                self.set_autoscalex_on(enable)
                scalex = self.get_autoscalex_on()
            else:
                scalex = False
            if axis in ['y', 'both']:
                self.set_autoscaley_on(enable)
                scaley = self.get_autoscaley_on()
            else:
                scaley = False
            if axis in ['z', 'both']:
                self.set_autoscalez_on(enable)
                scalez = self.get_autoscalez_on()
            else:
                scalez = False
        if scalex:
            self._request_autoscale_view("x", tight=tight)
        if scaley:
            self._request_autoscale_view("y", tight=tight)
        if scalez:
            self._request_autoscale_view("z", tight=tight)

    def auto_scale_xyz(self, X, Y, Z=None, had_data=None):
        # This updates the bounding boxes as to keep a record as to what the
        # minimum sized rectangular volume holds the data.
        if np.shape(X) == np.shape(Y):
            self.xy_dataLim.update_from_data_xy(
                np.column_stack([np.ravel(X), np.ravel(Y)]), not had_data)
        else:
            self.xy_dataLim.update_from_data_x(X, not had_data)
            self.xy_dataLim.update_from_data_y(Y, not had_data)
        if Z is not None:
            self.zz_dataLim.update_from_data_x(Z, not had_data)
        # Let autoscale_view figure out how to use this data.
        self.autoscale_view()

    def autoscale_view(self, tight=None,
                       scalex=True, scaley=True, scalez=True):
        """
        Autoscale the view limits using the data limits.

        See `.Axes.autoscale_view` for full documentation.  Because this
        function applies to 3D Axes, it also takes a *scalez* argument.
        """
        # This method looks at the rectangular volume (see above)
        # of data and decides how to scale the view portal to fit it.
        if tight is None:
            _tight = self._tight
            if not _tight:
                # if image data only just use the datalim
                for artist in self._children:
                    if isinstance(artist, mimage.AxesImage):
                        _tight = True
                    elif isinstance(artist, (mlines.Line2D, mpatches.Patch)):
                        _tight = False
                        break
        else:
            _tight = self._tight = bool(tight)

        if scalex and self.get_autoscalex_on():
            x0, x1 = self.xy_dataLim.intervalx
            xlocator = self.xaxis.get_major_locator()
            x0, x1 = xlocator.nonsingular(x0, x1)
            if self._xmargin > 0:
                delta = (x1 - x0) * self._xmargin
                x0 -= delta
                x1 += delta
            if not _tight:
                x0, x1 = xlocator.view_limits(x0, x1)
            self.set_xbound(x0, x1, self._view_margin)

        if scaley and self.get_autoscaley_on():
            y0, y1 = self.xy_dataLim.intervaly
            ylocator = self.yaxis.get_major_locator()
            y0, y1 = ylocator.nonsingular(y0, y1)
            if self._ymargin > 0:
                delta = (y1 - y0) * self._ymargin
                y0 -= delta
                y1 += delta
            if not _tight:
                y0, y1 = ylocator.view_limits(y0, y1)
            self.set_ybound(y0, y1, self._view_margin)

        if scalez and self.get_autoscalez_on():
            z0, z1 = self.zz_dataLim.intervalx
            zlocator = self.zaxis.get_major_locator()
            z0, z1 = zlocator.nonsingular(z0, z1)
            if self._zmargin > 0:
                delta = (z1 - z0) * self._zmargin
                z0 -= delta
                z1 += delta
            if not _tight:
                z0, z1 = zlocator.view_limits(z0, z1)
            self.set_zbound(z0, z1, self._view_margin)

    def get_w_lims(self):
        """Get 3D world limits."""
        minx, maxx = self.get_xlim3d()
        miny, maxy = self.get_ylim3d()
        minz, maxz = self.get_zlim3d()
        return minx, maxx, miny, maxy, minz, maxz

    def _set_bound3d(self, get_bound, set_lim, axis_inverted,
                     lower=None, upper=None, view_margin=None):
        """
        Set 3D axis bounds.
        """
        if upper is None and np.iterable(lower):
            lower, upper = lower

        old_lower, old_upper = get_bound()
        if lower is None:
            lower = old_lower
        if upper is None:
            upper = old_upper

        set_lim(sorted((lower, upper), reverse=bool(axis_inverted())),
                auto=None, view_margin=view_margin)

    def set_xbound(self, lower=None, upper=None, view_margin=None):
        """
        Set the lower and upper numerical bounds of the x-axis.

        This method will honor axis inversion regardless of parameter order.
        It will not change the autoscaling setting (`.get_autoscalex_on()`).

        Parameters
        ----------
        lower, upper : float or None
            The lower and upper bounds. If *None*, the respective axis bound
            is not modified.
        view_margin : float or None
            The margin to apply to the bounds. If *None*, the margin is handled
            by `.set_xlim`.

        See Also
        --------
        get_xbound
        get_xlim, set_xlim
        invert_xaxis, xaxis_inverted
        """
        self._set_bound3d(self.get_xbound, self.set_xlim, self.xaxis_inverted,
                          lower, upper, view_margin)

    def set_ybound(self, lower=None, upper=None, view_margin=None):
        """
        Set the lower and upper numerical bounds of the y-axis.

        This method will honor axis inversion regardless of parameter order.
        It will not change the autoscaling setting (`.get_autoscaley_on()`).

        Parameters
        ----------
        lower, upper : float or None
            The lower and upper bounds. If *None*, the respective axis bound
            is not modified.
        view_margin : float or None
            The margin to apply to the bounds. If *None*, the margin is handled
            by `.set_ylim`.

        See Also
        --------
        get_ybound
        get_ylim, set_ylim
        invert_yaxis, yaxis_inverted
        """
        self._set_bound3d(self.get_ybound, self.set_ylim, self.yaxis_inverted,
                          lower, upper, view_margin)

    def set_zbound(self, lower=None, upper=None, view_margin=None):
        """
        Set the lower and upper numerical bounds of the z-axis.
        This method will honor axis inversion regardless of parameter order.
        It will not change the autoscaling setting (`.get_autoscaley_on()`).

        Parameters
        ----------
        lower, upper : float or None
            The lower and upper bounds. If *None*, the respective axis bound
            is not modified.
        view_margin : float or None
            The margin to apply to the bounds. If *None*, the margin is handled
            by `.set_zlim`.

        See Also
        --------
        get_zbound
        get_zlim, set_zlim
        invert_zaxis, zaxis_inverted
        """
        self._set_bound3d(self.get_zbound, self.set_zlim, self.zaxis_inverted,
                          lower, upper, view_margin)

    def _set_lim3d(self, axis, lower=None, upper=None, *, emit=True,
                   auto=False, view_margin=None, axmin=None, axmax=None):
        """
        Set 3D axis limits.
        """
        if upper is None:
            if np.iterable(lower):
                lower, upper = lower
            elif axmax is None:
                upper = axis.get_view_interval()[1]
        if lower is None and axmin is None:
            lower = axis.get_view_interval()[0]
        if axmin is not None:
            if lower is not None:
                raise TypeError("Cannot pass both 'lower' and 'min'")
            lower = axmin
        if axmax is not None:
            if upper is not None:
                raise TypeError("Cannot pass both 'upper' and 'max'")
            upper = axmax
        if np.isinf(lower) or np.isinf(upper):
            raise ValueError(f"Axis limits {lower}, {upper} cannot be infinite")
        if view_margin is None:
            if mpl.rcParams['axes3d.automargin']:
                view_margin = self._view_margin
            else:
                view_margin = 0
        delta = (upper - lower) * view_margin
        lower -= delta
        upper += delta
        return axis._set_lim(lower, upper, emit=emit, auto=auto)

    def set_xlim(self, left=None, right=None, *, emit=True, auto=False,
                 view_margin=None, xmin=None, xmax=None):
        """
        Set the 3D x-axis view limits.

        Parameters
        ----------
        left : float, optional
            The left xlim in data coordinates. Passing *None* leaves the
            limit unchanged.

            The left and right xlims may also be passed as the tuple
            (*left*, *right*) as the first positional argument (or as
            the *left* keyword argument).

            .. ACCEPTS: (left: float, right: float)

        right : float, optional
            The right xlim in data coordinates. Passing *None* leaves the
            limit unchanged.

        emit : bool, default: True
            Whether to notify observers of limit change.

        auto : bool or None, default: False
            Whether to turn on autoscaling of the x-axis. *True* turns on,
            *False* turns off, *None* leaves unchanged.

        view_margin : float, optional
            The additional margin to apply to the limits.

        xmin, xmax : float, optional
            They are equivalent to left and right respectively, and it is an
            error to pass both *xmin* and *left* or *xmax* and *right*.

        Returns
        -------
        left, right : (float, float)
            The new x-axis limits in data coordinates.

        See Also
        --------
        get_xlim
        set_xbound, get_xbound
        invert_xaxis, xaxis_inverted

        Notes
        -----
        The *left* value may be greater than the *right* value, in which
        case the x-axis values will decrease from *left* to *right*.

        Examples
        --------
        >>> set_xlim(left, right)
        >>> set_xlim((left, right))
        >>> left, right = set_xlim(left, right)

        One limit may be left unchanged.

        >>> set_xlim(right=right_lim)

        Limits may be passed in reverse order to flip the direction of
        the x-axis. For example, suppose ``x`` represents depth of the
        ocean in m. The x-axis limits might be set like the following
        so 5000 m depth is at the left of the plot and the surface,
        0 m, is at the right.

        >>> set_xlim(5000, 0)
        """
        return self._set_lim3d(self.xaxis, left, right, emit=emit, auto=auto,
                               view_margin=view_margin, axmin=xmin, axmax=xmax)

    def set_ylim(self, bottom=None, top=None, *, emit=True, auto=False,
                 view_margin=None, ymin=None, ymax=None):
        """
        Set the 3D y-axis view limits.

        Parameters
        ----------
        bottom : float, optional
            The bottom ylim in data coordinates. Passing *None* leaves the
            limit unchanged.

            The bottom and top ylims may also be passed as the tuple
            (*bottom*, *top*) as the first positional argument (or as
            the *bottom* keyword argument).

            .. ACCEPTS: (bottom: float, top: float)

        top : float, optional
            The top ylim in data coordinates. Passing *None* leaves the
            limit unchanged.

        emit : bool, default: True
            Whether to notify observers of limit change.

        auto : bool or None, default: False
            Whether to turn on autoscaling of the y-axis. *True* turns on,
            *False* turns off, *None* leaves unchanged.

        view_margin : float, optional
            The additional margin to apply to the limits.

        ymin, ymax : float, optional
            They are equivalent to bottom and top respectively, and it is an
            error to pass both *ymin* and *bottom* or *ymax* and *top*.

        Returns
        -------
        bottom, top : (float, float)
            The new y-axis limits in data coordinates.

        See Also
        --------
        get_ylim
        set_ybound, get_ybound
        invert_yaxis, yaxis_inverted

        Notes
        -----
        The *bottom* value may be greater than the *top* value, in which
        case the y-axis values will decrease from *bottom* to *top*.

        Examples
        --------
        >>> set_ylim(bottom, top)
        >>> set_ylim((bottom, top))
        >>> bottom, top = set_ylim(bottom, top)

        One limit may be left unchanged.

        >>> set_ylim(top=top_lim)

        Limits may be passed in reverse order to flip the direction of
        the y-axis. For example, suppose ``y`` represents depth of the
        ocean in m. The y-axis limits might be set like the following
        so 5000 m depth is at the bottom of the plot and the surface,
        0 m, is at the top.

        >>> set_ylim(5000, 0)
        """
        return self._set_lim3d(self.yaxis, bottom, top, emit=emit, auto=auto,
                               view_margin=view_margin, axmin=ymin, axmax=ymax)

    def set_zlim(self, bottom=None, top=None, *, emit=True, auto=False,
                 view_margin=None, zmin=None, zmax=None):
        """
        Set the 3D z-axis view limits.

        Parameters
        ----------
        bottom : float, optional
            The bottom zlim in data coordinates. Passing *None* leaves the
            limit unchanged.

            The bottom and top zlims may also be passed as the tuple
            (*bottom*, *top*) as the first positional argument (or as
            the *bottom* keyword argument).

            .. ACCEPTS: (bottom: float, top: float)

        top : float, optional
            The top zlim in data coordinates. Passing *None* leaves the
            limit unchanged.

        emit : bool, default: True
            Whether to notify observers of limit change.

        auto : bool or None, default: False
            Whether to turn on autoscaling of the z-axis. *True* turns on,
            *False* turns off, *None* leaves unchanged.

        view_margin : float, optional
            The additional margin to apply to the limits.

        zmin, zmax : float, optional
            They are equivalent to bottom and top respectively, and it is an
            error to pass both *zmin* and *bottom* or *zmax* and *top*.

        Returns
        -------
        bottom, top : (float, float)
            The new z-axis limits in data coordinates.

        See Also
        --------
        get_zlim
        set_zbound, get_zbound
        invert_zaxis, zaxis_inverted

        Notes
        -----
        The *bottom* value may be greater than the *top* value, in which
        case the z-axis values will decrease from *bottom* to *top*.

        Examples
        --------
        >>> set_zlim(bottom, top)
        >>> set_zlim((bottom, top))
        >>> bottom, top = set_zlim(bottom, top)

        One limit may be left unchanged.

        >>> set_zlim(top=top_lim)

        Limits may be passed in reverse order to flip the direction of
        the z-axis. For example, suppose ``z`` represents depth of the
        ocean in m. The z-axis limits might be set like the following
        so 5000 m depth is at the bottom of the plot and the surface,
        0 m, is at the top.

        >>> set_zlim(5000, 0)
        """
        return self._set_lim3d(self.zaxis, bottom, top, emit=emit, auto=auto,
                               view_margin=view_margin, axmin=zmin, axmax=zmax)

    set_xlim3d = set_xlim
    set_ylim3d = set_ylim
    set_zlim3d = set_zlim

    def get_xlim(self):
        # docstring inherited
        return tuple(self.xy_viewLim.intervalx)

    def get_ylim(self):
        # docstring inherited
        return tuple(self.xy_viewLim.intervaly)

    def get_zlim(self):
        """
        Return the 3D z-axis view limits.

        Returns
        -------
        left, right : (float, float)
            The current z-axis limits in data coordinates.

        See Also
        --------
        set_zlim
        set_zbound, get_zbound
        invert_zaxis, zaxis_inverted

        Notes
        -----
        The z-axis may be inverted, in which case the *left* value will
        be greater than the *right* value.
        """
        return tuple(self.zz_viewLim.intervalx)

    get_zscale = _axis_method_wrapper("zaxis", "get_scale")

    # Redefine all three methods to overwrite their docstrings.
    set_xscale = _axis_method_wrapper("xaxis", "_set_axes_scale")
    set_yscale = _axis_method_wrapper("yaxis", "_set_axes_scale")
    set_zscale = _axis_method_wrapper("zaxis", "_set_axes_scale")
    set_xscale.__doc__, set_yscale.__doc__, set_zscale.__doc__ = map(
        """
        Set the {}-axis scale.

        Parameters
        ----------
        value : {{"linear"}}
            The axis scale type to apply.  3D Axes currently only support
            linear scales; other scales yield nonsensical results.

        **kwargs
            Keyword arguments are nominally forwarded to the scale class, but
            none of them is applicable for linear scales.
        """.format,
        ["x", "y", "z"])

    get_zticks = _axis_method_wrapper("zaxis", "get_ticklocs")
    set_zticks = _axis_method_wrapper("zaxis", "set_ticks")
    get_zmajorticklabels = _axis_method_wrapper("zaxis", "get_majorticklabels")
    get_zminorticklabels = _axis_method_wrapper("zaxis", "get_minorticklabels")
    get_zticklabels = _axis_method_wrapper("zaxis", "get_ticklabels")
    set_zticklabels = _axis_method_wrapper(
        "zaxis", "set_ticklabels",
        doc_sub={"Axis.set_ticks": "Axes3D.set_zticks"})

    zaxis_date = _axis_method_wrapper("zaxis", "axis_date")
    if zaxis_date.__doc__:
        zaxis_date.__doc__ += textwrap.dedent("""

        Notes
        -----
        This function is merely provided for completeness, but 3D Axes do not
        support dates for ticks, and so this may not work as expected.
        """)

    def clabel(self, *args, **kwargs):
        """Currently not implemented for 3D Axes, and returns *None*."""
        return None

    def view_init(self, elev=None, azim=None, roll=None, vertical_axis="z",
                  share=False):
        """
        Set the elevation and azimuth of the Axes in degrees (not radians).

        This can be used to rotate the Axes programmatically.

        To look normal to the primary planes, the following elevation and
        azimuth angles can be used. A roll angle of 0, 90, 180, or 270 deg
        will rotate these views while keeping the axes at right angles.

        ==========   ====  ====
        view plane   elev  azim
        ==========   ====  ====
        XY           90    -90
        XZ           0     -90
        YZ           0     0
        -XY          -90   90
        -XZ          0     90
        -YZ          0     180
        ==========   ====  ====

        Parameters
        ----------
        elev : float, default: None
            The elevation angle in degrees rotates the camera above the plane
            pierced by the vertical axis, with a positive angle corresponding
            to a location above that plane. For example, with the default
            vertical axis of 'z', the elevation defines the angle of the camera
            location above the x-y plane.
            If None, then the initial value as specified in the `Axes3D`
            constructor is used.
        azim : float, default: None
            The azimuthal angle in degrees rotates the camera about the
            vertical axis, with a positive angle corresponding to a
            right-handed rotation. For example, with the default vertical axis
            of 'z', a positive azimuth rotates the camera about the origin from
            its location along the +x axis towards the +y axis.
            If None, then the initial value as specified in the `Axes3D`
            constructor is used.
        roll : float, default: None
            The roll angle in degrees rotates the camera about the viewing
            axis. A positive angle spins the camera clockwise, causing the
            scene to rotate counter-clockwise.
            If None, then the initial value as specified in the `Axes3D`
            constructor is used.
        vertical_axis : {"z", "x", "y"}, default: "z"
            The axis to align vertically. *azim* rotates about this axis.
        share : bool, default: False
            If ``True``, apply the settings to all Axes with shared views.
        """

        self._dist = 10  # The camera distance from origin. Behaves like zoom

        if elev is None:
            elev = self.initial_elev
        if azim is None:
            azim = self.initial_azim
        if roll is None:
            roll = self.initial_roll
        vertical_axis = _api.check_getitem(
            {name: idx for idx, name in enumerate(self._axis_names)},
            vertical_axis=vertical_axis,
        )

        if share:
            axes = {sibling for sibling
                    in self._shared_axes['view'].get_siblings(self)}
        else:
            axes = [self]

        for ax in axes:
            ax.elev = elev
            ax.azim = azim
            ax.roll = roll
            ax._vertical_axis = vertical_axis

    def set_proj_type(self, proj_type, focal_length=None):
        """
        Set the projection type.

        Parameters
        ----------
        proj_type : {'persp', 'ortho'}
            The projection type.
        focal_length : float, default: None
            For a projection type of 'persp', the focal length of the virtual
            camera. Must be > 0. If None, defaults to 1.
            The focal length can be computed from a desired Field Of View via
            the equation: focal_length = 1/tan(FOV/2)
        """
        _api.check_in_list(['persp', 'ortho'], proj_type=proj_type)
        if proj_type == 'persp':
            if focal_length is None:
                focal_length = 1
            elif focal_length <= 0:
                raise ValueError(f"focal_length = {focal_length} must be "
                                 "greater than 0")
            self._focal_length = focal_length
        else:  # 'ortho':
            if focal_length not in (None, np.inf):
                raise ValueError(f"focal_length = {focal_length} must be "
                                 f"None for proj_type = {proj_type}")
            self._focal_length = np.inf

    def _roll_to_vertical(
        self, arr: "np.typing.ArrayLike", reverse: bool = False
    ) -> np.ndarray:
        """
        Roll arrays to match the different vertical axis.

        Parameters
        ----------
        arr : ArrayLike
            Array to roll.
        reverse : bool, default: False
            Reverse the direction of the roll.
        """
        if reverse:
            return np.roll(arr, (self._vertical_axis - 2) * -1)
        else:
            return np.roll(arr, (self._vertical_axis - 2))

    def get_proj(self):
        """Create the projection matrix from the current viewing position."""

        # Transform to uniform world coordinates 0-1, 0-1, 0-1
        box_aspect = self._roll_to_vertical(self._box_aspect)
        worldM = proj3d.world_transformation(
            *self.get_xlim3d(),
            *self.get_ylim3d(),
            *self.get_zlim3d(),
            pb_aspect=box_aspect,
        )

        # Look into the middle of the world coordinates:
        R = 0.5 * box_aspect

        # elev: elevation angle in the z plane.
        # azim: azimuth angle in the xy plane.
        # Coordinates for a point that rotates around the box of data.
        # p0, p1 corresponds to rotating the box only around the vertical axis.
        # p2 corresponds to rotating the box only around the horizontal axis.
        elev_rad = np.deg2rad(self.elev)
        azim_rad = np.deg2rad(self.azim)
        p0 = np.cos(elev_rad) * np.cos(azim_rad)
        p1 = np.cos(elev_rad) * np.sin(azim_rad)
        p2 = np.sin(elev_rad)

        # When changing vertical axis the coordinates changes as well.
        # Roll the values to get the same behaviour as the default:
        ps = self._roll_to_vertical([p0, p1, p2])

        # The coordinates for the eye viewing point. The eye is looking
        # towards the middle of the box of data from a distance:
        eye = R + self._dist * ps

        # Calculate the viewing axes for the eye position
        u, v, w = self._calc_view_axes(eye)
        self._view_u = u  # _view_u is towards the right of the screen
        self._view_v = v  # _view_v is towards the top of the screen
        self._view_w = w  # _view_w is out of the screen

        # Generate the view and projection transformation matrices
        if self._focal_length == np.inf:
            # Orthographic projection
            viewM = proj3d._view_transformation_uvw(u, v, w, eye)
            projM = proj3d._ortho_transformation(-self._dist, self._dist)
        else:
            # Perspective projection
            # Scale the eye dist to compensate for the focal length zoom effect
            eye_focal = R + self._dist * ps * self._focal_length
            viewM = proj3d._view_transformation_uvw(u, v, w, eye_focal)
            projM = proj3d._persp_transformation(-self._dist,
                                                 self._dist,
                                                 self._focal_length)

        # Combine all the transformation matrices to get the final projection
        M0 = np.dot(viewM, worldM)
        M = np.dot(projM, M0)
        return M

    def mouse_init(self, rotate_btn=1, pan_btn=2, zoom_btn=3):
        """
        Set the mouse buttons for 3D rotation and zooming.

        Parameters
        ----------
        rotate_btn : int or list of int, default: 1
            The mouse button or buttons to use for 3D rotation of the Axes.
        pan_btn : int or list of int, default: 2
            The mouse button or buttons to use to pan the 3D Axes.
        zoom_btn : int or list of int, default: 3
            The mouse button or buttons to use to zoom the 3D Axes.
        """
        self.button_pressed = None
        # coerce scalars into array-like, then convert into
        # a regular list to avoid comparisons against None
        # which breaks in recent versions of numpy.
        self._rotate_btn = np.atleast_1d(rotate_btn).tolist()
        self._pan_btn = np.atleast_1d(pan_btn).tolist()
        self._zoom_btn = np.atleast_1d(zoom_btn).tolist()

    def disable_mouse_rotation(self):
        """Disable mouse buttons for 3D rotation, panning, and zooming."""
        self.mouse_init(rotate_btn=[], pan_btn=[], zoom_btn=[])

    def can_zoom(self):
        # doc-string inherited
        return True

    def can_pan(self):
        # doc-string inherited
        return True

    def sharez(self, other):
        """
        Share the z-axis with *other*.

        This is equivalent to passing ``sharez=other`` when constructing the
        Axes, and cannot be used if the z-axis is already being shared with
        another Axes.  Note that it is not possible to unshare axes.
        """
        _api.check_isinstance(Axes3D, other=other)
        if self._sharez is not None and other is not self._sharez:
            raise ValueError("z-axis is already shared")
        self._shared_axes["z"].join(self, other)
        self._sharez = other
        self.zaxis.major = other.zaxis.major  # Ticker instances holding
        self.zaxis.minor = other.zaxis.minor  # locator and formatter.
        z0, z1 = other.get_zlim()
        self.set_zlim(z0, z1, emit=False, auto=other.get_autoscalez_on())
        self.zaxis._scale = other.zaxis._scale

    def shareview(self, other):
        """
        Share the view angles with *other*.

        This is equivalent to passing ``shareview=other`` when constructing the
        Axes, and cannot be used if the view angles are already being shared
        with another Axes.  Note that it is not possible to unshare axes.
        """
        _api.check_isinstance(Axes3D, other=other)
        if self._shareview is not None and other is not self._shareview:
            raise ValueError("view angles are already shared")
        self._shared_axes["view"].join(self, other)
        self._shareview = other
        vertical_axis = self._axis_names[other._vertical_axis]
        self.view_init(elev=other.elev, azim=other.azim, roll=other.roll,
                       vertical_axis=vertical_axis, share=True)

    def clear(self):
        # docstring inherited.
        super().clear()
        if self._focal_length == np.inf:
            self._zmargin = mpl.rcParams['axes.zmargin']
        else:
            self._zmargin = 0.

        xymargin = 0.05 * 10/11  # match mpl3.8 appearance
        self.xy_dataLim = Bbox([[xymargin, xymargin],
                                [1 - xymargin, 1 - xymargin]])
        # z-limits are encoded in the x-component of the Bbox, y is un-used
        self.zz_dataLim = Bbox.unit()
        self._view_margin = 1/48  # default value to match mpl3.8
        self.autoscale_view()

        self.grid(mpl.rcParams['axes3d.grid'])

    def _button_press(self, event):
        if event.inaxes == self:
            self.button_pressed = event.button
            self._sx, self._sy = event.xdata, event.ydata
            toolbar = self.get_figure(root=True).canvas.toolbar
            if toolbar and toolbar._nav_stack() is None:
                toolbar.push_current()
            if toolbar:
                toolbar.set_message(toolbar._mouse_event_to_message(event))

    def _button_release(self, event):
        self.button_pressed = None
        toolbar = self.get_figure(root=True).canvas.toolbar
        # backend_bases.release_zoom and backend_bases.release_pan call
        # push_current, so check the navigation mode so we don't call it twice
        if toolbar and self.get_navigate_mode() is None:
            toolbar.push_current()
        if toolbar:
            toolbar.set_message(toolbar._mouse_event_to_message(event))

    def _get_view(self):
        # docstring inherited
        return {
            "xlim": self.get_xlim(), "autoscalex_on": self.get_autoscalex_on(),
            "ylim": self.get_ylim(), "autoscaley_on": self.get_autoscaley_on(),
            "zlim": self.get_zlim(), "autoscalez_on": self.get_autoscalez_on(),
        }, (self.elev, self.azim, self.roll)

    def _set_view(self, view):
        # docstring inherited
        props, (elev, azim, roll) = view
        self.set(**props)
        self.elev = elev
        self.azim = azim
        self.roll = roll

    def format_zdata(self, z):
        """
        Return *z* string formatted.  This function will use the
        :attr:`fmt_zdata` attribute if it is callable, else will fall
        back on the zaxis major formatter
        """
        try:
            return self.fmt_zdata(z)
        except (AttributeError, TypeError):
            func = self.zaxis.get_major_formatter().format_data_short
            val = func(z)
            return val

    def format_coord(self, xv, yv, renderer=None):
        """
        Return a string giving the current view rotation angles, or the x, y, z
        coordinates of the point on the nearest axis pane underneath the mouse
        cursor, depending on the mouse button pressed.
        """
        coords = ''

        if self.button_pressed in self._rotate_btn:
            # ignore xv and yv and display angles instead
            coords = self._rotation_coords()

        elif self.M is not None:
            coords = self._location_coords(xv, yv, renderer)

        return coords

    def _rotation_coords(self):
        """
        Return the rotation angles as a string.
        """
        norm_elev = art3d._norm_angle(self.elev)
        norm_azim = art3d._norm_angle(self.azim)
        norm_roll = art3d._norm_angle(self.roll)
        coords = (f"elevation={norm_elev:.0f}\N{DEGREE SIGN}, "
                  f"azimuth={norm_azim:.0f}\N{DEGREE SIGN}, "
                  f"roll={norm_roll:.0f}\N{DEGREE SIGN}"
                  ).replace("-", "\N{MINUS SIGN}")
        return coords

    def _location_coords(self, xv, yv, renderer):
        """
        Return the location on the axis pane underneath the cursor as a string.
        """
        p1, pane_idx = self._calc_coord(xv, yv, renderer)
        xs = self.format_xdata(p1[0])
        ys = self.format_ydata(p1[1])
        zs = self.format_zdata(p1[2])
        if pane_idx == 0:
            coords = f'x pane={xs}, y={ys}, z={zs}'
        elif pane_idx == 1:
            coords = f'x={xs}, y pane={ys}, z={zs}'
        elif pane_idx == 2:
            coords = f'x={xs}, y={ys}, z pane={zs}'
        return coords

    def _get_camera_loc(self):
        """
        Returns the current camera location in data coordinates.
        """
        cx, cy, cz, dx, dy, dz = self._get_w_centers_ranges()
        c = np.array([cx, cy, cz])
        r = np.array([dx, dy, dz])

        if self._focal_length == np.inf:  # orthographic projection
            focal_length = 1e9  # large enough to be effectively infinite
        else:  # perspective projection
            focal_length = self._focal_length
        eye = c + self._view_w * self._dist * r / self._box_aspect * focal_length
        return eye

    def _calc_coord(self, xv, yv, renderer=None):
        """
        Given the 2D view coordinates, find the point on the nearest axis pane
        that lies directly below those coordinates. Returns a 3D point in data
        coordinates.
        """
        if self._focal_length == np.inf:  # orthographic projection
            zv = 1
        else:  # perspective projection
            zv = -1 / self._focal_length

        # Convert point on view plane to data coordinates
        p1 = np.array(proj3d.inv_transform(xv, yv, zv, self.invM)).ravel()

        # Get the vector from the camera to the point on the view plane
        vec = self._get_camera_loc() - p1

        # Get the pane locations for each of the axes
        pane_locs = []
        for axis in self._axis_map.values():
            xys, loc = axis.active_pane()
            pane_locs.append(loc)

        # Find the distance to the nearest pane by projecting the view vector
        scales = np.zeros(3)
        for i in range(3):
            if vec[i] == 0:
                scales[i] = np.inf
            else:
                scales[i] = (p1[i] - pane_locs[i]) / vec[i]
        pane_idx = np.argmin(abs(scales))
        scale = scales[pane_idx]

        # Calculate the point on the closest pane
        p2 = p1 - scale*vec
        return p2, pane_idx

    def _arcball(self, x: float, y: float) -> np.ndarray:
        """
        Convert a point (x, y) to a point on a virtual trackball.

        This is Ken Shoemake's arcball (a sphere), modified
        to soften the abrupt edge (optionally).
        See: Ken Shoemake, "ARCBALL: A user interface for specifying
        three-dimensional rotation using a mouse." in
        Proceedings of Graphics Interface '92, 1992, pp. 151-156,
        https://doi.org/10.20380/GI1992.18
        The smoothing of the edge is inspired by Gavin Bell's arcball
        (a sphere combined with a hyperbola), but here, the sphere
        is combined with a section of a cylinder, so it has finite support.
        """
        s = mpl.rcParams['axes3d.trackballsize'] / 2
        b = mpl.rcParams['axes3d.trackballborder'] / s
        x /= s
        y /= s
        r2 = x*x + y*y
        r = np.sqrt(r2)
        ra = 1 + b
        a = b * (1 + b/2)
        ri = 2/(ra + 1/ra)
        if r < ri:
            p = np.array([np.sqrt(1 - r2), x, y])
        elif r < ra:
            dr = ra - r
            p = np.array([a - np.sqrt((a + dr) * (a - dr)), x, y])
            p /= np.linalg.norm(p)
        else:
            p = np.array([0, x/r, y/r])
        return p

    def _on_move(self, event):
        """
        Mouse moving.

        By default, button-1 rotates, button-2 pans, and button-3 zooms;
        these buttons can be modified via `mouse_init`.
        """

        if not self.button_pressed:
            return

        if self.get_navigate_mode() is not None:
            # we don't want to rotate if we are zooming/panning
            # from the toolbar
            return

        if self.M is None:
            return

        x, y = event.xdata, event.ydata
        # In case the mouse is out of bounds.
        if x is None or event.inaxes != self:
            return

        dx, dy = x - self._sx, y - self._sy
        w = self._pseudo_w
        h = self._pseudo_h

        # Rotation
        if self.button_pressed in self._rotate_btn:
            # rotate viewing point
            # get the x and y pixel coords
            if dx == 0 and dy == 0:
                return

            style = mpl.rcParams['axes3d.mouserotationstyle']
            if style == 'azel':
                roll = np.deg2rad(self.roll)
                delev = -(dy/h)*180*np.cos(roll) + (dx/w)*180*np.sin(roll)
                dazim = -(dy/h)*180*np.sin(roll) - (dx/w)*180*np.cos(roll)
                elev = self.elev + delev
                azim = self.azim + dazim
                roll = self.roll
            else:
                q = _Quaternion.from_cardan_angles(
                        *np.deg2rad((self.elev, self.azim, self.roll)))

                if style == 'trackball':
                    k = np.array([0, -dy/h, dx/w])
                    nk = np.linalg.norm(k)
                    th = nk / mpl.rcParams['axes3d.trackballsize']
                    dq = _Quaternion(np.cos(th), k*np.sin(th)/nk)
                else:  # 'sphere', 'arcball'
                    current_vec = self._arcball(self._sx/w, self._sy/h)
                    new_vec = self._arcball(x/w, y/h)
                    if style == 'sphere':
                        dq = _Quaternion.rotate_from_to(current_vec, new_vec)
                    else:  # 'arcball'
                        dq = _Quaternion(0, new_vec) * _Quaternion(0, -current_vec)

                q = dq * q
                elev, azim, roll = np.rad2deg(q.as_cardan_angles())

            # update view
            vertical_axis = self._axis_names[self._vertical_axis]
            self.view_init(
                elev=elev,
                azim=azim,
                roll=roll,
                vertical_axis=vertical_axis,
                share=True,
            )
            self.stale = True

        # Pan
        elif self.button_pressed in self._pan_btn:
            # Start the pan event with pixel coordinates
            px, py = self.transData.transform([self._sx, self._sy])
            self.start_pan(px, py, 2)
            # pan view (takes pixel coordinate input)
            self.drag_pan(2, None, event.x, event.y)
            self.end_pan()

        # Zoom
        elif self.button_pressed in self._zoom_btn:
            # zoom view (dragging down zooms in)
            scale = h/(h - dy)
            self._scale_axis_limits(scale, scale, scale)

        # Store the event coordinates for the next time through.
        self._sx, self._sy = x, y
        # Always request a draw update at the end of interaction
        self.get_figure(root=True).canvas.draw_idle()

    def drag_pan(self, button, key, x, y):
        # docstring inherited

        # Get the coordinates from the move event
        p = self._pan_start
        (xdata, ydata), (xdata_start, ydata_start) = p.trans_inverse.transform(
            [(x, y), (p.x, p.y)])
        self._sx, self._sy = xdata, ydata
        # Calling start_pan() to set the x/y of this event as the starting
        # move location for the next event
        self.start_pan(x, y, button)
        du, dv = xdata - xdata_start, ydata - ydata_start
        dw = 0
        if key == 'x':
            dv = 0
        elif key == 'y':
            du = 0
        if du == 0 and dv == 0:
            return

        # Transform the pan from the view axes to the data axes
        R = np.array([self._view_u, self._view_v, self._view_w])
        R = -R / self._box_aspect * self._dist
        duvw_projected = R.T @ np.array([du, dv, dw])

        # Calculate pan distance
        minx, maxx, miny, maxy, minz, maxz = self.get_w_lims()
        dx = (maxx - minx) * duvw_projected[0]
        dy = (maxy - miny) * duvw_projected[1]
        dz = (maxz - minz) * duvw_projected[2]

        # Set the new axis limits
        self.set_xlim3d(minx + dx, maxx + dx, auto=None)
        self.set_ylim3d(miny + dy, maxy + dy, auto=None)
        self.set_zlim3d(minz + dz, maxz + dz, auto=None)

    def _calc_view_axes(self, eye):
        """
        Get the unit vectors for the viewing axes in data coordinates.
        `u` is towards the right of the screen
        `v` is towards the top of the screen
        `w` is out of the screen
        """
        elev_rad = np.deg2rad(art3d._norm_angle(self.elev))
        roll_rad = np.deg2rad(art3d._norm_angle(self.roll))

        # Look into the middle of the world coordinates
        R = 0.5 * self._roll_to_vertical(self._box_aspect)

        # Define which axis should be vertical. A negative value
        # indicates the plot is upside down and therefore the values
        # have been reversed:
        V = np.zeros(3)
        V[self._vertical_axis] = -1 if abs(elev_rad) > np.pi/2 else 1

        u, v, w = proj3d._view_axes(eye, R, V, roll_rad)
        return u, v, w

    def _set_view_from_bbox(self, bbox, direction='in',
                            mode=None, twinx=False, twiny=False):
        """
        Zoom in or out of the bounding box.

        Will center the view in the center of the bounding box, and zoom by
        the ratio of the size of the bounding box to the size of the Axes3D.
        """
        (start_x, start_y, stop_x, stop_y) = bbox
        if mode == 'x':
            start_y = self.bbox.min[1]
            stop_y = self.bbox.max[1]
        elif mode == 'y':
            start_x = self.bbox.min[0]
            stop_x = self.bbox.max[0]

        # Clip to bounding box limits
        start_x, stop_x = np.clip(sorted([start_x, stop_x]),
                                  self.bbox.min[0], self.bbox.max[0])
        start_y, stop_y = np.clip(sorted([start_y, stop_y]),
                                  self.bbox.min[1], self.bbox.max[1])

        # Move the center of the view to the center of the bbox
        zoom_center_x = (start_x + stop_x)/2
        zoom_center_y = (start_y + stop_y)/2

        ax_center_x = (self.bbox.max[0] + self.bbox.min[0])/2
        ax_center_y = (self.bbox.max[1] + self.bbox.min[1])/2

        self.start_pan(zoom_center_x, zoom_center_y, 2)
        self.drag_pan(2, None, ax_center_x, ax_center_y)
        self.end_pan()

        # Calculate zoom level
        dx = abs(start_x - stop_x)
        dy = abs(start_y - stop_y)
        scale_u = dx / (self.bbox.max[0] - self.bbox.min[0])
        scale_v = dy / (self.bbox.max[1] - self.bbox.min[1])

        # Keep aspect ratios equal
        scale = max(scale_u, scale_v)

        # Zoom out
        if direction == 'out':
            scale = 1 / scale

        self._zoom_data_limits(scale, scale, scale)

    def _zoom_data_limits(self, scale_u, scale_v, scale_w):
        """
        Zoom in or out of a 3D plot.

        Will scale the data limits by the scale factors. These will be
        transformed to the x, y, z data axes based on the current view angles.
        A scale factor > 1 zooms out and a scale factor < 1 zooms in.

        For an Axes that has had its aspect ratio set to 'equal', 'equalxy',
        'equalyz', or 'equalxz', the relevant axes are constrained to zoom
        equally.

        Parameters
        ----------
        scale_u : float
            Scale factor for the u view axis (view screen horizontal).
        scale_v : float
            Scale factor for the v view axis (view screen vertical).
        scale_w : float
            Scale factor for the w view axis (view screen depth).
        """
        scale = np.array([scale_u, scale_v, scale_w])

        # Only perform frame conversion if unequal scale factors
        if not np.allclose(scale, scale_u):
            # Convert the scale factors from the view frame to the data frame
            R = np.array([self._view_u, self._view_v, self._view_w])
            S = scale * np.eye(3)
            scale = np.linalg.norm(R.T @ S, axis=1)

            # Set the constrained scale factors to the factor closest to 1
            if self._aspect in ('equal', 'equalxy', 'equalxz', 'equalyz'):
                ax_idxs = self._equal_aspect_axis_indices(self._aspect)
                min_ax_idxs = np.argmin(np.abs(scale[ax_idxs] - 1))
                scale[ax_idxs] = scale[ax_idxs][min_ax_idxs]

        self._scale_axis_limits(scale[0], scale[1], scale[2])

    def _scale_axis_limits(self, scale_x, scale_y, scale_z):
        """
        Keeping the center of the x, y, and z data axes fixed, scale their
        limits by scale factors. A scale factor > 1 zooms out and a scale
        factor < 1 zooms in.

        Parameters
        ----------
        scale_x : float
            Scale factor for the x data axis.
        scale_y : float
            Scale factor for the y data axis.
        scale_z : float
            Scale factor for the z data axis.
        """
        # Get the axis centers and ranges
        cx, cy, cz, dx, dy, dz = self._get_w_centers_ranges()

        # Set the scaled axis limits
        self.set_xlim3d(cx - dx*scale_x/2, cx + dx*scale_x/2, auto=None)
        self.set_ylim3d(cy - dy*scale_y/2, cy + dy*scale_y/2, auto=None)
        self.set_zlim3d(cz - dz*scale_z/2, cz + dz*scale_z/2, auto=None)

    def _get_w_centers_ranges(self):
        """Get 3D world centers and axis ranges."""
        # Calculate center of axis limits
        minx, maxx, miny, maxy, minz, maxz = self.get_w_lims()
        cx = (maxx + minx)/2
        cy = (maxy + miny)/2
        cz = (maxz + minz)/2

        # Calculate range of axis limits
        dx = (maxx - minx)
        dy = (maxy - miny)
        dz = (maxz - minz)
        return cx, cy, cz, dx, dy, dz

    def set_zlabel(self, zlabel, fontdict=None, labelpad=None, **kwargs):
        """
        Set zlabel.  See doc for `.set_ylabel` for description.
        """
        if labelpad is not None:
            self.zaxis.labelpad = labelpad
        return self.zaxis.set_label_text(zlabel, fontdict, **kwargs)

    def get_zlabel(self):
        """
        Get the z-label text string.
        """
        label = self.zaxis.label
        return label.get_text()

    # Axes rectangle characteristics

    # The frame_on methods are not available for 3D axes.
    # Python will raise a TypeError if they are called.
    get_frame_on = None
    set_frame_on = None

    def grid(self, visible=True, **kwargs):
        """
        Set / unset 3D grid.

        .. note::

            Currently, this function does not behave the same as
            `.axes.Axes.grid`, but it is intended to eventually support that
            behavior.
        """
        # TODO: Operate on each axes separately
        if len(kwargs):
            visible = True
        self._draw_grid = visible
        self.stale = True

    def tick_params(self, axis='both', **kwargs):
        """
        Convenience method for changing the appearance of ticks and
        tick labels.

        See `.Axes.tick_params` for full documentation.  Because this function
        applies to 3D Axes, *axis* can also be set to 'z', and setting *axis*
        to 'both' autoscales all three axes.

        Also, because of how Axes3D objects are drawn very differently
        from regular 2D Axes, some of these settings may have
        ambiguous meaning.  For simplicity, the 'z' axis will
        accept settings as if it was like the 'y' axis.

        .. note::
           Axes3D currently ignores some of these settings.
        """
        _api.check_in_list(['x', 'y', 'z', 'both'], axis=axis)
        if axis in ['x', 'y', 'both']:
            super().tick_params(axis, **kwargs)
        if axis in ['z', 'both']:
            zkw = dict(kwargs)
            zkw.pop('top', None)
            zkw.pop('bottom', None)
            zkw.pop('labeltop', None)
            zkw.pop('labelbottom', None)
            self.zaxis.set_tick_params(**zkw)

    # data limits, ticks, tick labels, and formatting

    def invert_zaxis(self):
        """
        Invert the z-axis.

        See Also
        --------
        zaxis_inverted
        get_zlim, set_zlim
        get_zbound, set_zbound
        """
        bottom, top = self.get_zlim()
        self.set_zlim(top, bottom, auto=None)

    zaxis_inverted = _axis_method_wrapper("zaxis", "get_inverted")

    def get_zbound(self):
        """
        Return the lower and upper z-axis bounds, in increasing order.

        See Also
        --------
        set_zbound
        get_zlim, set_zlim
        invert_zaxis, zaxis_inverted
        """
        lower, upper = self.get_zlim()
        if lower < upper:
            return lower, upper
        else:
            return upper, lower

    def text(self, x, y, z, s, zdir=None, *, axlim_clip=False, **kwargs):
        """
        Add the text *s* to the 3D Axes at location *x*, *y*, *z* in data coordinates.

        Parameters
        ----------
        x, y, z : float
            The position to place the text.
        s : str
            The text.
        zdir : {'x', 'y', 'z', 3-tuple}, optional
            The direction to be used as the z-direction. Default: 'z'.
            See `.get_dir_vector` for a description of the values.
        axlim_clip : bool, default: False
            Whether to hide text that is outside the axes view limits.

            .. versionadded:: 3.10
        **kwargs
            Other arguments are forwarded to `matplotlib.axes.Axes.text`.

        Returns
        -------
        `.Text3D`
            The created `.Text3D` instance.
        """
        text = super().text(x, y, s, **kwargs)
        art3d.text_2d_to_3d(text, z, zdir, axlim_clip)
        return text

    text3D = text
    text2D = Axes.text

    def plot(self, xs, ys, *args, zdir='z', axlim_clip=False, **kwargs):
        """
        Plot 2D or 3D data.

        Parameters
        ----------
        xs : 1D array-like
            x coordinates of vertices.
        ys : 1D array-like
            y coordinates of vertices.
        zs : float or 1D array-like
            z coordinates of vertices; either one for all points or one for
            each point.
        zdir : {'x', 'y', 'z'}, default: 'z'
            When plotting 2D data, the direction to use as z.
        axlim_clip : bool, default: False
            Whether to hide data that is outside the axes view limits.

            .. versionadded:: 3.10
        **kwargs
            Other arguments are forwarded to `matplotlib.axes.Axes.plot`.
        """
        had_data = self.has_data()

        # `zs` can be passed positionally or as keyword; checking whether
        # args[0] is a string matches the behavior of 2D `plot` (via
        # `_process_plot_var_args`).
        if args and not isinstance(args[0], str):
            zs, *args = args
            if 'zs' in kwargs:
                raise TypeError("plot() for multiple values for argument 'zs'")
        else:
            zs = kwargs.pop('zs', 0)

        xs, ys, zs = cbook._broadcast_with_masks(xs, ys, zs)

        lines = super().plot(xs, ys, *args, **kwargs)
        for line in lines:
            art3d.line_2d_to_3d(line, zs=zs, zdir=zdir, axlim_clip=axlim_clip)

        xs, ys, zs = art3d.juggle_axes(xs, ys, zs, zdir)
        self.auto_scale_xyz(xs, ys, zs, had_data)
        return lines

    plot3D = plot

    def fill_between(self, x1, y1, z1, x2, y2, z2, *,
                     where=None, mode='auto', facecolors=None, shade=None,
                     axlim_clip=False, **kwargs):
        """
        Fill the area between two 3D curves.

        The curves are defined by the points (*x1*, *y1*, *z1*) and
        (*x2*, *y2*, *z2*). This creates one or multiple quadrangle
        polygons that are filled. All points must be the same length N, or a
        single value to be used for all points.

        Parameters
        ----------
        x1, y1, z1 : float or 1D array-like
            x, y, and z  coordinates of vertices for 1st line.

        x2, y2, z2 : float or 1D array-like
            x, y, and z coordinates of vertices for 2nd line.

        where : array of bool (length N), optional
            Define *where* to exclude some regions from being filled. The
            filled regions are defined by the coordinates ``pts[where]``,
            for all x, y, and z pts. More precisely, fill between ``pts[i]``
            and ``pts[i+1]`` if ``where[i] and where[i+1]``. Note that this
            definition implies that an isolated *True* value between two
            *False* values in *where* will not result in filling. Both sides of
            the *True* position remain unfilled due to the adjacent *False*
            values.

        mode : {'quad', 'polygon', 'auto'}, default: 'auto'
            The fill mode. One of:

            - 'quad':  A separate quadrilateral polygon is created for each
              pair of subsequent points in the two lines.
            - 'polygon': The two lines are connected to form a single polygon.
              This is faster and can render more cleanly for simple shapes
              (e.g. for filling between two lines that lie within a plane).
            - 'auto': If the points all lie on the same 3D plane, 'polygon' is
              used. Otherwise, 'quad' is used.

        facecolors : list of :mpltype:`color`, default: None
            Colors of each individual patch, or a single color to be used for
            all patches.

        shade : bool, default: None
            Whether to shade the facecolors. If *None*, then defaults to *True*
            for 'quad' mode and *False* for 'polygon' mode.

        axlim_clip : bool, default: False
            Whether to hide data that is outside the axes view limits.

            .. versionadded:: 3.10

        **kwargs
            All other keyword arguments are passed on to `.Poly3DCollection`.

        Returns
        -------
        `.Poly3DCollection`
            A `.Poly3DCollection` containing the plotted polygons.

        """
        _api.check_in_list(['auto', 'quad', 'polygon'], mode=mode)

        had_data = self.has_data()
        x1, y1, z1, x2, y2, z2 = cbook._broadcast_with_masks(x1, y1, z1, x2, y2, z2)

        if facecolors is None:
            facecolors = [self._get_patches_for_fill.get_next_color()]
        facecolors = list(mcolors.to_rgba_array(facecolors))

        if where is None:
            where = True
        else:
            where = np.asarray(where, dtype=bool)
            if where.size != x1.size:
                raise ValueError(f"where size ({where.size}) does not match "
                                 f"size ({x1.size})")
        where = where & ~np.isnan(x1)  # NaNs were broadcast in _broadcast_with_masks

        if mode == 'auto':
            if art3d._all_points_on_plane(np.concatenate((x1[where], x2[where])),
                                          np.concatenate((y1[where], y2[where])),
                                          np.concatenate((z1[where], z2[where])),
                                          atol=1e-12):
                mode = 'polygon'
            else:
                mode = 'quad'

        if shade is None:
            if mode == 'quad':
                shade = True
            else:
                shade = False

        polys = []
        for idx0, idx1 in cbook.contiguous_regions(where):
            x1i = x1[idx0:idx1]
            y1i = y1[idx0:idx1]
            z1i = z1[idx0:idx1]
            x2i = x2[idx0:idx1]
            y2i = y2[idx0:idx1]
            z2i = z2[idx0:idx1]

            if not len(x1i):
                continue

            if mode == 'quad':
                # Preallocate the array for the region's vertices, and fill it in
                n_polys_i = len(x1i) - 1
                polys_i = np.empty((n_polys_i, 4, 3))
                polys_i[:, 0, :] = np.column_stack((x1i[:-1], y1i[:-1], z1i[:-1]))
                polys_i[:, 1, :] = np.column_stack((x1i[1:], y1i[1:], z1i[1:]))
                polys_i[:, 2, :] = np.column_stack((x2i[1:], y2i[1:], z2i[1:]))
                polys_i[:, 3, :] = np.column_stack((x2i[:-1], y2i[:-1], z2i[:-1]))
                polys = polys + [*polys_i]
            elif mode == 'polygon':
                line1 = np.column_stack((x1i, y1i, z1i))
                line2 = np.column_stack((x2i[::-1], y2i[::-1], z2i[::-1]))
                poly = np.concatenate((line1, line2), axis=0)
                polys.append(poly)

        polyc = art3d.Poly3DCollection(polys, facecolors=facecolors, shade=shade,
                                       axlim_clip=axlim_clip, **kwargs)
        self.add_collection(polyc)

        self.auto_scale_xyz([x1, x2], [y1, y2], [z1, z2], had_data)
        return polyc

    def plot_surface(self, X, Y, Z, *, norm=None, vmin=None,
                     vmax=None, lightsource=None, axlim_clip=False, **kwargs):
        """
        Create a surface plot.

        By default, it will be colored in shades of a solid color, but it also
        supports colormapping by supplying the *cmap* argument.

        .. note::

           The *rcount* and *ccount* kwargs, which both default to 50,
           determine the maximum number of samples used in each direction.  If
           the input data is larger, it will be downsampled (by slicing) to
           these numbers of points.

        .. note::

           To maximize rendering speed consider setting *rstride* and *cstride*
           to divisors of the number of rows minus 1 and columns minus 1
           respectively. For example, given 51 rows rstride can be any of the
           divisors of 50.

           Similarly, a setting of *rstride* and *cstride* equal to 1 (or
           *rcount* and *ccount* equal the number of rows and columns) can use
           the optimized path.

        Parameters
        ----------
        X, Y, Z : 2D arrays
            Data values.

        rcount, ccount : int
            Maximum number of samples used in each direction.  If the input
            data is larger, it will be downsampled (by slicing) to these
            numbers of points.  Defaults to 50.

        rstride, cstride : int
            Downsampling stride in each direction.  These arguments are
            mutually exclusive with *rcount* and *ccount*.  If only one of
            *rstride* or *cstride* is set, the other defaults to 10.

            'classic' mode uses a default of ``rstride = cstride = 10`` instead
            of the new default of ``rcount = ccount = 50``.

        color : :mpltype:`color`
            Color of the surface patches.

        cmap : Colormap, optional
            Colormap of the surface patches.

        facecolors : list of :mpltype:`color`
            Colors of each individual patch.

        norm : `~matplotlib.colors.Normalize`, optional
            Normalization for the colormap.

        vmin, vmax : float, optional
            Bounds for the normalization.

        shade : bool, default: True
            Whether to shade the facecolors.  Shading is always disabled when
            *cmap* is specified.

        lightsource : `~matplotlib.colors.LightSource`, optional
            The lightsource to use when *shade* is True.

        axlim_clip : bool, default: False
            Whether to hide patches with a vertex outside the axes view limits.

            .. versionadded:: 3.10

        **kwargs
            Other keyword arguments are forwarded to `.Poly3DCollection`.
        """

        had_data = self.has_data()

        if Z.ndim != 2:
            raise ValueError("Argument Z must be 2-dimensional.")

        Z = cbook._to_unmasked_float_array(Z)
        X, Y, Z = np.broadcast_arrays(X, Y, Z)
        rows, cols = Z.shape

        has_stride = 'rstride' in kwargs or 'cstride' in kwargs
        has_count = 'rcount' in kwargs or 'ccount' in kwargs

        if has_stride and has_count:
            raise ValueError("Cannot specify both stride and count arguments")

        rstride = kwargs.pop('rstride', 10)
        cstride = kwargs.pop('cstride', 10)
        rcount = kwargs.pop('rcount', 50)
        ccount = kwargs.pop('ccount', 50)

        if mpl.rcParams['_internal.classic_mode']:
            # Strides have priority over counts in classic mode.
            # So, only compute strides from counts
            # if counts were explicitly given
            compute_strides = has_count
        else:
            # If the strides are provided then it has priority.
            # Otherwise, compute the strides from the counts.
            compute_strides = not has_stride

        if compute_strides:
            rstride = int(max(np.ceil(rows / rcount), 1))
            cstride = int(max(np.ceil(cols / ccount), 1))

        fcolors = kwargs.pop('facecolors', None)

        cmap = kwargs.get('cmap', None)
        shade = kwargs.pop('shade', cmap is None)
        if shade is None:
            raise ValueError("shade cannot be None.")

        colset = []  # the sampled facecolor
        if (rows - 1) % rstride == 0 and \
           (cols - 1) % cstride == 0 and \
           fcolors is None:
            polys = np.stack(
                [cbook._array_patch_perimeters(a, rstride, cstride)
                 for a in (X, Y, Z)],
                axis=-1)
        else:
            # evenly spaced, and including both endpoints
            row_inds = list(range(0, rows-1, rstride)) + [rows-1]
            col_inds = list(range(0, cols-1, cstride)) + [cols-1]

            polys = []
            for rs, rs_next in itertools.pairwise(row_inds):
                for cs, cs_next in itertools.pairwise(col_inds):
                    ps = [
                        # +1 ensures we share edges between polygons
                        cbook._array_perimeter(a[rs:rs_next+1, cs:cs_next+1])
                        for a in (X, Y, Z)
                    ]
                    # ps = np.stack(ps, axis=-1)
                    ps = np.array(ps).T
                    polys.append(ps)

                    if fcolors is not None:
                        colset.append(fcolors[rs][cs])

        # In cases where there are non-finite values in the data (possibly NaNs from
        # masked arrays), artifacts can be introduced. Here check whether such values
        # are present and remove them.
        if not isinstance(polys, np.ndarray) or not np.isfinite(polys).all():
            new_polys = []
            new_colset = []

            # Depending on fcolors, colset is either an empty list or has as
            # many elements as polys. In the former case new_colset results in
            # a list with None entries, that is discarded later.
            for p, col in itertools.zip_longest(polys, colset):
                new_poly = np.array(p)[np.isfinite(p).all(axis=1)]
                if len(new_poly):
                    new_polys.append(new_poly)
                    new_colset.append(col)

            # Replace previous polys and, if fcolors is not None, colset
            polys = new_polys
            if fcolors is not None:
                colset = new_colset

        # note that the striding causes some polygons to have more coordinates
        # than others

        if fcolors is not None:
            polyc = art3d.Poly3DCollection(
                polys, edgecolors=colset, facecolors=colset, shade=shade,
                lightsource=lightsource, axlim_clip=axlim_clip, **kwargs)
        elif cmap:
            polyc = art3d.Poly3DCollection(polys, axlim_clip=axlim_clip, **kwargs)
            # can't always vectorize, because polys might be jagged
            if isinstance(polys, np.ndarray):
                avg_z = polys[..., 2].mean(axis=-1)
            else:
                avg_z = np.array([ps[:, 2].mean() for ps in polys])
            polyc.set_array(avg_z)
            if vmin is not None or vmax is not None:
                polyc.set_clim(vmin, vmax)
            if norm is not None:
                polyc.set_norm(norm)
        else:
            color = kwargs.pop('color', None)
            if color is None:
                color = self._get_lines.get_next_color()
            color = np.array(mcolors.to_rgba(color))

            polyc = art3d.Poly3DCollection(
                polys, facecolors=color, shade=shade, lightsource=lightsource,
                axlim_clip=axlim_clip, **kwargs)

        self.add_collection(polyc)
        self.auto_scale_xyz(X, Y, Z, had_data)

        return polyc

    def plot_wireframe(self, X, Y, Z, *, axlim_clip=False, **kwargs):
        """
        Plot a 3D wireframe.

        .. note::

           The *rcount* and *ccount* kwargs, which both default to 50,
           determine the maximum number of samples used in each direction.  If
           the input data is larger, it will be downsampled (by slicing) to
           these numbers of points.

        Parameters
        ----------
        X, Y, Z : 2D arrays
            Data values.

        axlim_clip : bool, default: False
            Whether to hide lines and patches with vertices outside the axes
            view limits.

            .. versionadded:: 3.10

        rcount, ccount : int
            Maximum number of samples used in each direction.  If the input
            data is larger, it will be downsampled (by slicing) to these
            numbers of points.  Setting a count to zero causes the data to be
            not sampled in the corresponding direction, producing a 3D line
            plot rather than a wireframe plot.  Defaults to 50.

        rstride, cstride : int
            Downsampling stride in each direction.  These arguments are
            mutually exclusive with *rcount* and *ccount*.  If only one of
            *rstride* or *cstride* is set, the other defaults to 1.  Setting a
            stride to zero causes the data to be not sampled in the
            corresponding direction, producing a 3D line plot rather than a
            wireframe plot.

            'classic' mode uses a default of ``rstride = cstride = 1`` instead
            of the new default of ``rcount = ccount = 50``.

        **kwargs
            Other keyword arguments are forwarded to `.Line3DCollection`.
        """

        had_data = self.has_data()
        if Z.ndim != 2:
            raise ValueError("Argument Z must be 2-dimensional.")
        # FIXME: Support masked arrays
        X, Y, Z = np.broadcast_arrays(X, Y, Z)
        rows, cols = Z.shape

        has_stride = 'rstride' in kwargs or 'cstride' in kwargs
        has_count = 'rcount' in kwargs or 'ccount' in kwargs

        if has_stride and has_count:
            raise ValueError("Cannot specify both stride and count arguments")

        rstride = kwargs.pop('rstride', 1)
        cstride = kwargs.pop('cstride', 1)
        rcount = kwargs.pop('rcount', 50)
        ccount = kwargs.pop('ccount', 50)

        if mpl.rcParams['_internal.classic_mode']:
            # Strides have priority over counts in classic mode.
            # So, only compute strides from counts
            # if counts were explicitly given
            if has_count:
                rstride = int(max(np.ceil(rows / rcount), 1)) if rcount else 0
                cstride = int(max(np.ceil(cols / ccount), 1)) if ccount else 0
        else:
            # If the strides are provided then it has priority.
            # Otherwise, compute the strides from the counts.
            if not has_stride:
                rstride = int(max(np.ceil(rows / rcount), 1)) if rcount else 0
                cstride = int(max(np.ceil(cols / ccount), 1)) if ccount else 0

        # We want two sets of lines, one running along the "rows" of
        # Z and another set of lines running along the "columns" of Z.
        # This transpose will make it easy to obtain the columns.
        tX, tY, tZ = np.transpose(X), np.transpose(Y), np.transpose(Z)

        if rstride:
            rii = list(range(0, rows, rstride))
            # Add the last index only if needed
            if rows > 0 and rii[-1] != (rows - 1):
                rii += [rows-1]
        else:
            rii = []
        if cstride:
            cii = list(range(0, cols, cstride))
            # Add the last index only if needed
            if cols > 0 and cii[-1] != (cols - 1):
                cii += [cols-1]
        else:
            cii = []

        if rstride == 0 and cstride == 0:
            raise ValueError("Either rstride or cstride must be non zero")

        # If the inputs were empty, then just
        # reset everything.
        if Z.size == 0:
            rii = []
            cii = []

        xlines = [X[i] for i in rii]
        ylines = [Y[i] for i in rii]
        zlines = [Z[i] for i in rii]

        txlines = [tX[i] for i in cii]
        tylines = [tY[i] for i in cii]
        tzlines = [tZ[i] for i in cii]

        lines = ([list(zip(xl, yl, zl))
                 for xl, yl, zl in zip(xlines, ylines, zlines)]
                 + [list(zip(xl, yl, zl))
                 for xl, yl, zl in zip(txlines, tylines, tzlines)])

        linec = art3d.Line3DCollection(lines, axlim_clip=axlim_clip, **kwargs)
        self.add_collection(linec)
        self.auto_scale_xyz(X, Y, Z, had_data)

        return linec

    def plot_trisurf(self, *args, color=None, norm=None, vmin=None, vmax=None,
                     lightsource=None, axlim_clip=False, **kwargs):
        """
        Plot a triangulated surface.

        The (optional) triangulation can be specified in one of two ways;
        either::

          plot_trisurf(triangulation, ...)

        where triangulation is a `~matplotlib.tri.Triangulation` object, or::

          plot_trisurf(X, Y, ...)
          plot_trisurf(X, Y, triangles, ...)
          plot_trisurf(X, Y, triangles=triangles, ...)

        in which case a Triangulation object will be created.  See
        `.Triangulation` for an explanation of these possibilities.

        The remaining arguments are::

          plot_trisurf(..., Z)

        where *Z* is the array of values to contour, one per point
        in the triangulation.

        Parameters
        ----------
        X, Y, Z : array-like
            Data values as 1D arrays.
        color
            Color of the surface patches.
        cmap
            A colormap for the surface patches.
        norm : `~matplotlib.colors.Normalize`, optional
            An instance of Normalize to map values to colors.
        vmin, vmax : float, optional
            Minimum and maximum value to map.
        shade : bool, default: True
            Whether to shade the facecolors.  Shading is always disabled when
            *cmap* is specified.
        lightsource : `~matplotlib.colors.LightSource`, optional
            The lightsource to use when *shade* is True.
        axlim_clip : bool, default: False
            Whether to hide patches with a vertex outside the axes view limits.

            .. versionadded:: 3.10
        **kwargs
            All other keyword arguments are passed on to
            :class:`~mpl_toolkits.mplot3d.art3d.Poly3DCollection`

        Examples
        --------
        .. plot:: gallery/mplot3d/trisurf3d.py
        .. plot:: gallery/mplot3d/trisurf3d_2.py
        """

        had_data = self.has_data()

        # TODO: Support custom face colours
        if color is None:
            color = self._get_lines.get_next_color()
        color = np.array(mcolors.to_rgba(color))

        cmap = kwargs.get('cmap', None)
        shade = kwargs.pop('shade', cmap is None)

        tri, args, kwargs = \
            Triangulation.get_from_args_and_kwargs(*args, **kwargs)
        try:
            z = kwargs.pop('Z')
        except KeyError:
            # We do this so Z doesn't get passed as an arg to PolyCollection
            z, *args = args
        z = np.asarray(z)

        triangles = tri.get_masked_triangles()
        xt = tri.x[triangles]
        yt = tri.y[triangles]
        zt = z[triangles]
        verts = np.stack((xt, yt, zt), axis=-1)

        if cmap:
            polyc = art3d.Poly3DCollection(verts, *args,
                                           axlim_clip=axlim_clip, **kwargs)
            # average over the three points of each triangle
            avg_z = verts[:, :, 2].mean(axis=1)
            polyc.set_array(avg_z)
            if vmin is not None or vmax is not None:
                polyc.set_clim(vmin, vmax)
            if norm is not None:
                polyc.set_norm(norm)
        else:
            polyc = art3d.Poly3DCollection(
                verts, *args, shade=shade, lightsource=lightsource,
                facecolors=color, axlim_clip=axlim_clip, **kwargs)

        self.add_collection(polyc)
        self.auto_scale_xyz(tri.x, tri.y, z, had_data)

        return polyc

    def _3d_extend_contour(self, cset, stride=5):
        """
        Extend a contour in 3D by creating
        """

        dz = (cset.levels[1] - cset.levels[0]) / 2
        polyverts = []
        colors = []
        for idx, level in enumerate(cset.levels):
            path = cset.get_paths()[idx]
            subpaths = [*path._iter_connected_components()]
            color = cset.get_edgecolor()[idx]
            top = art3d._paths_to_3d_segments(subpaths, level - dz)
            bot = art3d._paths_to_3d_segments(subpaths, level + dz)
            if not len(top[0]):
                continue
            nsteps = max(round(len(top[0]) / stride), 2)
            stepsize = (len(top[0]) - 1) / (nsteps - 1)
            polyverts.extend([
                (top[0][round(i * stepsize)], top[0][round((i + 1) * stepsize)],
                 bot[0][round((i + 1) * stepsize)], bot[0][round(i * stepsize)])
                for i in range(round(nsteps) - 1)])
            colors.extend([color] * (round(nsteps) - 1))
        self.add_collection3d(art3d.Poly3DCollection(
            np.array(polyverts),  # All polygons have 4 vertices, so vectorize.
            facecolors=colors, edgecolors=colors, shade=True))
        cset.remove()

    def add_contour_set(
            self, cset, extend3d=False, stride=5, zdir='z', offset=None,
            axlim_clip=False):
        zdir = '-' + zdir
        if extend3d:
            self._3d_extend_contour(cset, stride)
        else:
            art3d.collection_2d_to_3d(
                cset, zs=offset if offset is not None else cset.levels, zdir=zdir,
                axlim_clip=axlim_clip)

    def add_contourf_set(self, cset, zdir='z', offset=None, *, axlim_clip=False):
        self._add_contourf_set(cset, zdir=zdir, offset=offset,
                               axlim_clip=axlim_clip)

    def _add_contourf_set(self, cset, zdir='z', offset=None, axlim_clip=False):
        """
        Returns
        -------
        levels : `numpy.ndarray`
            Levels at which the filled contours are added.
        """
        zdir = '-' + zdir

        midpoints = cset.levels[:-1] + np.diff(cset.levels) / 2
        # Linearly interpolate to get levels for any extensions
        if cset._extend_min:
            min_level = cset.levels[0] - np.diff(cset.levels[:2]) / 2
            midpoints = np.insert(midpoints, 0, min_level)
        if cset._extend_max:
            max_level = cset.levels[-1] + np.diff(cset.levels[-2:]) / 2
            midpoints = np.append(midpoints, max_level)

        art3d.collection_2d_to_3d(
            cset, zs=offset if offset is not None else midpoints, zdir=zdir,
            axlim_clip=axlim_clip)
        return midpoints

    @_preprocess_data()
    def contour(self, X, Y, Z, *args,
                extend3d=False, stride=5, zdir='z', offset=None, axlim_clip=False,
                **kwargs):
        """
        Create a 3D contour plot.

        Parameters
        ----------
        X, Y, Z : array-like,
            Input data. See `.Axes.contour` for supported data shapes.
        extend3d : bool, default: False
            Whether to extend contour in 3D.
        stride : int, default: 5
            Step size for extending contour.
        zdir : {'x', 'y', 'z'}, default: 'z'
            The direction to use.
        offset : float, optional
            If specified, plot a projection of the contour lines at this
            position in a plane normal to *zdir*.
        axlim_clip : bool, default: False
            Whether to hide lines with a vertex outside the axes view limits.

            .. versionadded:: 3.10
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        *args, **kwargs
            Other arguments are forwarded to `matplotlib.axes.Axes.contour`.

        Returns
        -------
        matplotlib.contour.QuadContourSet
        """
        had_data = self.has_data()

        jX, jY, jZ = art3d.rotate_axes(X, Y, Z, zdir)
        cset = super().contour(jX, jY, jZ, *args, **kwargs)
        self.add_contour_set(cset, extend3d, stride, zdir, offset, axlim_clip)

        self.auto_scale_xyz(X, Y, Z, had_data)
        return cset

    contour3D = contour

    @_preprocess_data()
    def tricontour(self, *args,
                   extend3d=False, stride=5, zdir='z', offset=None, axlim_clip=False,
                   **kwargs):
        """
        Create a 3D contour plot.

        .. note::
            This method currently produces incorrect output due to a
            longstanding bug in 3D PolyCollection rendering.

        Parameters
        ----------
        X, Y, Z : array-like
            Input data. See `.Axes.tricontour` for supported data shapes.
        extend3d : bool, default: False
            Whether to extend contour in 3D.
        stride : int, default: 5
            Step size for extending contour.
        zdir : {'x', 'y', 'z'}, default: 'z'
            The direction to use.
        offset : float, optional
            If specified, plot a projection of the contour lines at this
            position in a plane normal to *zdir*.
        axlim_clip : bool, default: False
            Whether to hide lines with a vertex outside the axes view limits.

            .. versionadded:: 3.10
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER
        *args, **kwargs
            Other arguments are forwarded to `matplotlib.axes.Axes.tricontour`.

        Returns
        -------
        matplotlib.tri._tricontour.TriContourSet
        """
        had_data = self.has_data()

        tri, args, kwargs = Triangulation.get_from_args_and_kwargs(
                *args, **kwargs)
        X = tri.x
        Y = tri.y
        if 'Z' in kwargs:
            Z = kwargs.pop('Z')
        else:
            # We do this so Z doesn't get passed as an arg to Axes.tricontour
            Z, *args = args

        jX, jY, jZ = art3d.rotate_axes(X, Y, Z, zdir)
        tri = Triangulation(jX, jY, tri.triangles, tri.mask)

        cset = super().tricontour(tri, jZ, *args, **kwargs)
        self.add_contour_set(cset, extend3d, stride, zdir, offset, axlim_clip)

        self.auto_scale_xyz(X, Y, Z, had_data)
        return cset

    def _auto_scale_contourf(self, X, Y, Z, zdir, levels, had_data):
        # Autoscale in the zdir based on the levels added, which are
        # different from data range if any contour extensions are present
        dim_vals = {'x': X, 'y': Y, 'z': Z, zdir: levels}
        # Input data and levels have different sizes, but auto_scale_xyz
        # expected same-size input, so manually take min/max limits
        limits = [(np.nanmin(dim_vals[dim]), np.nanmax(dim_vals[dim]))
                  for dim in ['x', 'y', 'z']]
        self.auto_scale_xyz(*limits, had_data)

    @_preprocess_data()
    def contourf(self, X, Y, Z, *args,
                 zdir='z', offset=None, axlim_clip=False, **kwargs):
        """
        Create a 3D filled contour plot.

        Parameters
        ----------
        X, Y, Z : array-like
            Input data. See `.Axes.contourf` for supported data shapes.
        zdir : {'x', 'y', 'z'}, default: 'z'
            The direction to use.
        offset : float, optional
            If specified, plot a projection of the contour lines at this
            position in a plane normal to *zdir*.
        axlim_clip : bool, default: False
            Whether to hide lines with a vertex outside the axes view limits.

            .. versionadded:: 3.10
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER
        *args, **kwargs
            Other arguments are forwarded to `matplotlib.axes.Axes.contourf`.

        Returns
        -------
        matplotlib.contour.QuadContourSet
        """
        had_data = self.has_data()

        jX, jY, jZ = art3d.rotate_axes(X, Y, Z, zdir)
        cset = super().contourf(jX, jY, jZ, *args, **kwargs)
        levels = self._add_contourf_set(cset, zdir, offset, axlim_clip)

        self._auto_scale_contourf(X, Y, Z, zdir, levels, had_data)
        return cset

    contourf3D = contourf

    @_preprocess_data()
    def tricontourf(self, *args, zdir='z', offset=None, axlim_clip=False, **kwargs):
        """
        Create a 3D filled contour plot.

        .. note::
            This method currently produces incorrect output due to a
            longstanding bug in 3D PolyCollection rendering.

        Parameters
        ----------
        X, Y, Z : array-like
            Input data. See `.Axes.tricontourf` for supported data shapes.
        zdir : {'x', 'y', 'z'}, default: 'z'
            The direction to use.
        offset : float, optional
            If specified, plot a projection of the contour lines at this
            position in a plane normal to zdir.
        axlim_clip : bool, default: False
            Whether to hide lines with a vertex outside the axes view limits.

            .. versionadded:: 3.10
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER
        *args, **kwargs
            Other arguments are forwarded to
            `matplotlib.axes.Axes.tricontourf`.

        Returns
        -------
        matplotlib.tri._tricontour.TriContourSet
        """
        had_data = self.has_data()

        tri, args, kwargs = Triangulation.get_from_args_and_kwargs(
                *args, **kwargs)
        X = tri.x
        Y = tri.y
        if 'Z' in kwargs:
            Z = kwargs.pop('Z')
        else:
            # We do this so Z doesn't get passed as an arg to Axes.tricontourf
            Z, *args = args

        jX, jY, jZ = art3d.rotate_axes(X, Y, Z, zdir)
        tri = Triangulation(jX, jY, tri.triangles, tri.mask)

        cset = super().tricontourf(tri, jZ, *args, **kwargs)
        levels = self._add_contourf_set(cset, zdir, offset, axlim_clip)

        self._auto_scale_contourf(X, Y, Z, zdir, levels, had_data)
        return cset

    def add_collection3d(self, col, zs=0, zdir='z', autolim=True, *,
                         axlim_clip=False):
        """
        Add a 3D collection object to the plot.

        2D collection types are converted to a 3D version by
        modifying the object and adding z coordinate information,
        *zs* and *zdir*.

        Supported 2D collection types are:

        - `.PolyCollection`
        - `.LineCollection`
        - `.PatchCollection` (currently not supporting *autolim*)

        Parameters
        ----------
        col : `.Collection`
            A 2D collection object.
        zs : float or array-like, default: 0
            The z-positions to be used for the 2D objects.
        zdir : {'x', 'y', 'z'}, default: 'z'
            The direction to use for the z-positions.
        autolim : bool, default: True
            Whether to update the data limits.
        axlim_clip : bool, default: False
            Whether to hide the scatter points outside the axes view limits.

            .. versionadded:: 3.10
        """
        had_data = self.has_data()

        zvals = np.atleast_1d(zs)
        zsortval = (np.min(zvals) if zvals.size
                    else 0)  # FIXME: arbitrary default

        # FIXME: use issubclass() (although, then a 3D collection
        #       object would also pass.)  Maybe have a collection3d
        #       abstract class to test for and exclude?
        if type(col) is mcoll.PolyCollection:
            art3d.poly_collection_2d_to_3d(col, zs=zs, zdir=zdir,
                                           axlim_clip=axlim_clip)
            col.set_sort_zpos(zsortval)
        elif type(col) is mcoll.LineCollection:
            art3d.line_collection_2d_to_3d(col, zs=zs, zdir=zdir,
                                           axlim_clip=axlim_clip)
            col.set_sort_zpos(zsortval)
        elif type(col) is mcoll.PatchCollection:
            art3d.patch_collection_2d_to_3d(col, zs=zs, zdir=zdir,
                                            axlim_clip=axlim_clip)
            col.set_sort_zpos(zsortval)

        if autolim:
            if isinstance(col, art3d.Line3DCollection):
                self.auto_scale_xyz(*np.array(col._segments3d).transpose(),
                                    had_data=had_data)
            elif isinstance(col, art3d.Poly3DCollection):
                self.auto_scale_xyz(*col._vec[:-1], had_data=had_data)
            elif isinstance(col, art3d.Patch3DCollection):
                pass
                # FIXME: Implement auto-scaling function for Patch3DCollection
                # Currently unable to do so due to issues with Patch3DCollection
                # See https://github.com/matplotlib/matplotlib/issues/14298 for details

        collection = super().add_collection(col)
        return collection

    @_preprocess_data(replace_names=["xs", "ys", "zs", "s",
                                     "edgecolors", "c", "facecolor",
                                     "facecolors", "color"])
    def scatter(self, xs, ys,
                zs=0, zdir='z', s=20, c=None, depthshade=True, *args,
                axlim_clip=False, **kwargs):
        """
        Create a scatter plot.

        Parameters
        ----------
        xs, ys : array-like
            The data positions.
        zs : float or array-like, default: 0
            The z-positions. Either an array of the same length as *xs* and
            *ys* or a single value to place all points in the same plane.
        zdir : {'x', 'y', 'z', '-x', '-y', '-z'}, default: 'z'
            The axis direction for the *zs*. This is useful when plotting 2D
            data on a 3D Axes. The data must be passed as *xs*, *ys*. Setting
            *zdir* to 'y' then plots the data to the x-z-plane.

            See also :doc:`/gallery/mplot3d/2dcollections3d`.

        s : float or array-like, default: 20
            The marker size in points**2. Either an array of the same length
            as *xs* and *ys* or a single value to make all markers the same
            size.
        c : :mpltype:`color`, sequence, or sequence of colors, optional
            The marker color. Possible values:

            - A single color format string.
            - A sequence of colors of length n.
            - A sequence of n numbers to be mapped to colors using *cmap* and
              *norm*.
            - A 2D array in which the rows are RGB or RGBA.

            For more details see the *c* argument of `~.axes.Axes.scatter`.
        depthshade : bool, default: True
            Whether to shade the scatter markers to give the appearance of
            depth. Each call to ``scatter()`` will perform its depthshading
            independently.
        axlim_clip : bool, default: False
            Whether to hide the scatter points outside the axes view limits.

            .. versionadded:: 3.10
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER
        **kwargs
            All other keyword arguments are passed on to `~.axes.Axes.scatter`.

        Returns
        -------
        paths : `~matplotlib.collections.PathCollection`
        """

        had_data = self.has_data()
        zs_orig = zs

        xs, ys, zs = cbook._broadcast_with_masks(xs, ys, zs)
        s = np.ma.ravel(s)  # This doesn't have to match x, y in size.

        xs, ys, zs, s, c, color = cbook.delete_masked_points(
            xs, ys, zs, s, c, kwargs.get('color', None)
            )
        if kwargs.get("color") is not None:
            kwargs['color'] = color

        # For xs and ys, 2D scatter() will do the copying.
        if np.may_share_memory(zs_orig, zs):  # Avoid unnecessary copies.
            zs = zs.copy()

        patches = super().scatter(xs, ys, s=s, c=c, *args, **kwargs)
        art3d.patch_collection_2d_to_3d(patches, zs=zs, zdir=zdir,
                                        depthshade=depthshade,
                                        axlim_clip=axlim_clip)

        if self._zmargin < 0.05 and xs.size > 0:
            self.set_zmargin(0.05)

        self.auto_scale_xyz(xs, ys, zs, had_data)

        return patches

    scatter3D = scatter

    @_preprocess_data()
    def bar(self, left, height, zs=0, zdir='z', *args,
            axlim_clip=False, **kwargs):
        """
        Add 2D bar(s).

        Parameters
        ----------
        left : 1D array-like
            The x coordinates of the left sides of the bars.
        height : 1D array-like
            The height of the bars.
        zs : float or 1D array-like, default: 0
            Z coordinate of bars; if a single value is specified, it will be
            used for all bars.
        zdir : {'x', 'y', 'z'}, default: 'z'
            When plotting 2D data, the direction to use as z ('x', 'y' or 'z').
        axlim_clip : bool, default: False
            Whether to hide bars with points outside the axes view limits.

            .. versionadded:: 3.10
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER
        **kwargs
            Other keyword arguments are forwarded to
            `matplotlib.axes.Axes.bar`.

        Returns
        -------
        mpl_toolkits.mplot3d.art3d.Patch3DCollection
        """
        had_data = self.has_data()

        patches = super().bar(left, height, *args, **kwargs)

        zs = np.broadcast_to(zs, len(left), subok=True)

        verts = []
        verts_zs = []
        for p, z in zip(patches, zs):
            vs = art3d._get_patch_verts(p)
            verts += vs.tolist()
            verts_zs += [z] * len(vs)
            art3d.patch_2d_to_3d(p, z, zdir, axlim_clip)
            if 'alpha' in kwargs:
                p.set_alpha(kwargs['alpha'])

        if len(verts) > 0:
            # the following has to be skipped if verts is empty
            # NOTE: Bugs could still occur if len(verts) > 0,
            #       but the "2nd dimension" is empty.
            xs, ys = zip(*verts)
        else:
            xs, ys = [], []

        xs, ys, verts_zs = art3d.juggle_axes(xs, ys, verts_zs, zdir)
        self.auto_scale_xyz(xs, ys, verts_zs, had_data)

        return patches

    @_preprocess_data()
    def bar3d(self, x, y, z, dx, dy, dz, color=None,
              zsort='average', shade=True, lightsource=None, *args,
              axlim_clip=False, **kwargs):
        """
        Generate a 3D barplot.

        This method creates three-dimensional barplot where the width,
        depth, height, and color of the bars can all be uniquely set.

        Parameters
        ----------
        x, y, z : array-like
            The coordinates of the anchor point of the bars.

        dx, dy, dz : float or array-like
            The width, depth, and height of the bars, respectively.

        color : sequence of colors, optional
            The color of the bars can be specified globally or
            individually. This parameter can be:

            - A single color, to color all bars the same color.
            - An array of colors of length N bars, to color each bar
              independently.
            - An array of colors of length 6, to color the faces of the
              bars similarly.
            - An array of colors of length 6 * N bars, to color each face
              independently.

            When coloring the faces of the boxes specifically, this is
            the order of the coloring:

            1. -Z (bottom of box)
            2. +Z (top of box)
            3. -Y
            4. +Y
            5. -X
            6. +X

        zsort : {'average', 'min', 'max'}, default: 'average'
            The z-axis sorting scheme passed onto `~.art3d.Poly3DCollection`

        shade : bool, default: True
            When true, this shades the dark sides of the bars (relative
            to the plot's source of light).

        lightsource : `~matplotlib.colors.LightSource`, optional
            The lightsource to use when *shade* is True.

        axlim_clip : bool, default: False
            Whether to hide the bars with points outside the axes view limits.

            .. versionadded:: 3.10

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Any additional keyword arguments are passed onto
            `~.art3d.Poly3DCollection`.

        Returns
        -------
        collection : `~.art3d.Poly3DCollection`
            A collection of three-dimensional polygons representing the bars.
        """

        had_data = self.has_data()

        x, y, z, dx, dy, dz = np.broadcast_arrays(
            np.atleast_1d(x), y, z, dx, dy, dz)
        minx = np.min(x)
        maxx = np.max(x + dx)
        miny = np.min(y)
        maxy = np.max(y + dy)
        minz = np.min(z)
        maxz = np.max(z + dz)

        # shape (6, 4, 3)
        # All faces are oriented facing outwards - when viewed from the
        # outside, their vertices are in a counterclockwise ordering.
        cuboid = np.array([
            # -z
            (
                (0, 0, 0),
                (0, 1, 0),
                (1, 1, 0),
                (1, 0, 0),
            ),
            # +z
            (
                (0, 0, 1),
                (1, 0, 1),
                (1, 1, 1),
                (0, 1, 1),
            ),
            # -y
            (
                (0, 0, 0),
                (1, 0, 0),
                (1, 0, 1),
                (0, 0, 1),
            ),
            # +y
            (
                (0, 1, 0),
                (0, 1, 1),
                (1, 1, 1),
                (1, 1, 0),
            ),
            # -x
            (
                (0, 0, 0),
                (0, 0, 1),
                (0, 1, 1),
                (0, 1, 0),
            ),
            # +x
            (
                (1, 0, 0),
                (1, 1, 0),
                (1, 1, 1),
                (1, 0, 1),
            ),
        ])

        # indexed by [bar, face, vertex, coord]
        polys = np.empty(x.shape + cuboid.shape)

        # handle each coordinate separately
        for i, p, dp in [(0, x, dx), (1, y, dy), (2, z, dz)]:
            p = p[..., np.newaxis, np.newaxis]
            dp = dp[..., np.newaxis, np.newaxis]
            polys[..., i] = p + dp * cuboid[..., i]

        # collapse the first two axes
        polys = polys.reshape((-1,) + polys.shape[2:])

        facecolors = []
        if color is None:
            color = [self._get_patches_for_fill.get_next_color()]

        color = list(mcolors.to_rgba_array(color))

        if len(color) == len(x):
            # bar colors specified, need to expand to number of faces
            for c in color:
                facecolors.extend([c] * 6)
        else:
            # a single color specified, or face colors specified explicitly
            facecolors = color
            if len(facecolors) < len(x):
                facecolors *= (6 * len(x))

        col = art3d.Poly3DCollection(polys,
                                     zsort=zsort,
                                     facecolors=facecolors,
                                     shade=shade,
                                     lightsource=lightsource,
                                     axlim_clip=axlim_clip,
                                     *args, **kwargs)
        self.add_collection(col)

        self.auto_scale_xyz((minx, maxx), (miny, maxy), (minz, maxz), had_data)

        return col

    def set_title(self, label, fontdict=None, loc='center', **kwargs):
        # docstring inherited
        ret = super().set_title(label, fontdict=fontdict, loc=loc, **kwargs)
        (x, y) = self.title.get_position()
        self.title.set_y(0.92 * y)
        return ret

    @_preprocess_data()
    def quiver(self, X, Y, Z, U, V, W, *,
               length=1, arrow_length_ratio=.3, pivot='tail', normalize=False,
               axlim_clip=False, **kwargs):
        """
        Plot a 3D field of arrows.

        The arguments can be array-like or scalars, so long as they can be
        broadcast together. The arguments can also be masked arrays. If an
        element in any of argument is masked, then that corresponding quiver
        element will not be plotted.

        Parameters
        ----------
        X, Y, Z : array-like
            The x, y and z coordinates of the arrow locations (default is
            tail of arrow; see *pivot* kwarg).

        U, V, W : array-like
            The x, y and z components of the arrow vectors.

        length : float, default: 1
            The length of each quiver.

        arrow_length_ratio : float, default: 0.3
            The ratio of the arrow head with respect to the quiver.

        pivot : {'tail', 'middle', 'tip'}, default: 'tail'
            The part of the arrow that is at the grid point; the arrow
            rotates about this point, hence the name *pivot*.

        normalize : bool, default: False
            Whether all arrows are normalized to have the same length, or keep
            the lengths defined by *u*, *v*, and *w*.

        axlim_clip : bool, default: False
            Whether to hide arrows with points outside the axes view limits.

            .. versionadded:: 3.10

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Any additional keyword arguments are delegated to
            :class:`.Line3DCollection`
        """

        def calc_arrows(UVW):
            # get unit direction vector perpendicular to (u, v, w)
            x = UVW[:, 0]
            y = UVW[:, 1]
            norm = np.linalg.norm(UVW[:, :2], axis=1)
            x_p = np.divide(y, norm, where=norm != 0, out=np.zeros_like(x))
            y_p = np.divide(-x,  norm, where=norm != 0, out=np.ones_like(x))
            # compute the two arrowhead direction unit vectors
            rangle = math.radians(15)
            c = math.cos(rangle)
            s = math.sin(rangle)
            # construct the rotation matrices of shape (3, 3, n)
            r13 = y_p * s
            r32 = x_p * s
            r12 = x_p * y_p * (1 - c)
            Rpos = np.array(
                [[c + (x_p ** 2) * (1 - c), r12, r13],
                 [r12, c + (y_p ** 2) * (1 - c), -r32],
                 [-r13, r32, np.full_like(x_p, c)]])
            # opposite rotation negates all the sin terms
            Rneg = Rpos.copy()
            Rneg[[0, 1, 2, 2], [2, 2, 0, 1]] *= -1
            # Batch n (3, 3) x (3) matrix multiplications ((3, 3, n) x (n, 3)).
            Rpos_vecs = np.einsum("ij...,...j->...i", Rpos, UVW)
            Rneg_vecs = np.einsum("ij...,...j->...i", Rneg, UVW)
            # Stack into (n, 2, 3) result.
            return np.stack([Rpos_vecs, Rneg_vecs], axis=1)

        had_data = self.has_data()

        input_args = cbook._broadcast_with_masks(X, Y, Z, U, V, W,
                                                 compress=True)

        if any(len(v) == 0 for v in input_args):
            # No quivers, so just make an empty collection and return early
            linec = art3d.Line3DCollection([], **kwargs)
            self.add_collection(linec)
            return linec

        shaft_dt = np.array([0., length], dtype=float)
        arrow_dt = shaft_dt * arrow_length_ratio

        _api.check_in_list(['tail', 'middle', 'tip'], pivot=pivot)
        if pivot == 'tail':
            shaft_dt -= length
        elif pivot == 'middle':
            shaft_dt -= length / 2

        XYZ = np.column_stack(input_args[:3])
        UVW = np.column_stack(input_args[3:]).astype(float)

        # Normalize rows of UVW
        if normalize:
            norm = np.linalg.norm(UVW, axis=1)
            norm[norm == 0] = 1
            UVW = UVW / norm.reshape((-1, 1))

        if len(XYZ) > 0:
            # compute the shaft lines all at once with an outer product
            shafts = (XYZ - np.multiply.outer(shaft_dt, UVW)).swapaxes(0, 1)
            # compute head direction vectors, n heads x 2 sides x 3 dimensions
            head_dirs = calc_arrows(UVW)
            # compute all head lines at once, starting from the shaft ends
            heads = shafts[:, :1] - np.multiply.outer(arrow_dt, head_dirs)
            # stack left and right head lines together
            heads = heads.reshape((len(arrow_dt), -1, 3))
            # transpose to get a list of lines
            heads = heads.swapaxes(0, 1)

            lines = [*shafts, *heads[::2], *heads[1::2]]
        else:
            lines = []

        linec = art3d.Line3DCollection(lines, axlim_clip=axlim_clip, **kwargs)
        self.add_collection(linec)

        self.auto_scale_xyz(XYZ[:, 0], XYZ[:, 1], XYZ[:, 2], had_data)

        return linec

    quiver3D = quiver

    def voxels(self, *args, facecolors=None, edgecolors=None, shade=True,
               lightsource=None, axlim_clip=False, **kwargs):
        """
        ax.voxels([x, y, z,] /, filled, facecolors=None, edgecolors=None, \
**kwargs)

        Plot a set of filled voxels

        All voxels are plotted as 1x1x1 cubes on the axis, with
        ``filled[0, 0, 0]`` placed with its lower corner at the origin.
        Occluded faces are not plotted.

        Parameters
        ----------
        filled : 3D np.array of bool
            A 3D array of values, with truthy values indicating which voxels
            to fill

        x, y, z : 3D np.array, optional
            The coordinates of the corners of the voxels. This should broadcast
            to a shape one larger in every dimension than the shape of
            *filled*.  These can be used to plot non-cubic voxels.

            If not specified, defaults to increasing integers along each axis,
            like those returned by :func:`~numpy.indices`.
            As indicated by the ``/`` in the function signature, these
            arguments can only be passed positionally.

        facecolors, edgecolors : array-like, optional
            The color to draw the faces and edges of the voxels. Can only be
            passed as keyword arguments.
            These parameters can be:

            - A single color value, to color all voxels the same color. This
              can be either a string, or a 1D RGB/RGBA array
            - ``None``, the default, to use a single color for the faces, and
              the style default for the edges.
            - A 3D `~numpy.ndarray` of color names, with each item the color
              for the corresponding voxel. The size must match the voxels.
            - A 4D `~numpy.ndarray` of RGB/RGBA data, with the components
              along the last axis.

        shade : bool, default: True
            Whether to shade the facecolors.

        lightsource : `~matplotlib.colors.LightSource`, optional
            The lightsource to use when *shade* is True.

        axlim_clip : bool, default: False
            Whether to hide voxels with points outside the axes view limits.

            .. versionadded:: 3.10

        **kwargs
            Additional keyword arguments to pass onto
            `~mpl_toolkits.mplot3d.art3d.Poly3DCollection`.

        Returns
        -------
        faces : dict
            A dictionary indexed by coordinate, where ``faces[i, j, k]`` is a
            `.Poly3DCollection` of the faces drawn for the voxel
            ``filled[i, j, k]``. If no faces were drawn for a given voxel,
            either because it was not asked to be drawn, or it is fully
            occluded, then ``(i, j, k) not in faces``.

        Examples
        --------
        .. plot:: gallery/mplot3d/voxels.py
        .. plot:: gallery/mplot3d/voxels_rgb.py
        .. plot:: gallery/mplot3d/voxels_torus.py
        .. plot:: gallery/mplot3d/voxels_numpy_logo.py
        """

        # work out which signature we should be using, and use it to parse
        # the arguments. Name must be voxels for the correct error message
        if len(args) >= 3:
            # underscores indicate position only
            def voxels(__x, __y, __z, filled, **kwargs):
                return (__x, __y, __z), filled, kwargs
        else:
            def voxels(filled, **kwargs):
                return None, filled, kwargs

        xyz, filled, kwargs = voxels(*args, **kwargs)

        # check dimensions
        if filled.ndim != 3:
            raise ValueError("Argument filled must be 3-dimensional")
        size = np.array(filled.shape, dtype=np.intp)

        # check xyz coordinates, which are one larger than the filled shape
        coord_shape = tuple(size + 1)
        if xyz is None:
            x, y, z = np.indices(coord_shape)
        else:
            x, y, z = (np.broadcast_to(c, coord_shape) for c in xyz)

        def _broadcast_color_arg(color, name):
            if np.ndim(color) in (0, 1):
                # single color, like "red" or [1, 0, 0]
                return np.broadcast_to(color, filled.shape + np.shape(color))
            elif np.ndim(color) in (3, 4):
                # 3D array of strings, or 4D array with last axis rgb
                if np.shape(color)[:3] != filled.shape:
                    raise ValueError(
                        f"When multidimensional, {name} must match the shape "
                        "of filled")
                return color
            else:
                raise ValueError(f"Invalid {name} argument")

        # broadcast and default on facecolors
        if facecolors is None:
            facecolors = self._get_patches_for_fill.get_next_color()
        facecolors = _broadcast_color_arg(facecolors, 'facecolors')

        # broadcast but no default on edgecolors
        edgecolors = _broadcast_color_arg(edgecolors, 'edgecolors')

        # scale to the full array, even if the data is only in the center
        self.auto_scale_xyz(x, y, z)

        # points lying on corners of a square
        square = np.array([
            [0, 0, 0],
            [1, 0, 0],
            [1, 1, 0],
            [0, 1, 0],
        ], dtype=np.intp)

        voxel_faces = defaultdict(list)

        def permutation_matrices(n):
            """Generate cyclic permutation matrices."""
            mat = np.eye(n, dtype=np.intp)
            for i in range(n):
                yield mat
                mat = np.roll(mat, 1, axis=0)

        # iterate over each of the YZ, ZX, and XY orientations, finding faces
        # to render
        for permute in permutation_matrices(3):
            # find the set of ranges to iterate over
            pc, qc, rc = permute.T.dot(size)
            pinds = np.arange(pc)
            qinds = np.arange(qc)
            rinds = np.arange(rc)

            square_rot_pos = square.dot(permute.T)
            square_rot_neg = square_rot_pos[::-1]

            # iterate within the current plane
            for p in pinds:
                for q in qinds:
                    # iterate perpendicularly to the current plane, handling
                    # boundaries. We only draw faces between a voxel and an
                    # empty space, to avoid drawing internal faces.

                    # draw lower faces
                    p0 = permute.dot([p, q, 0])
                    i0 = tuple(p0)
                    if filled[i0]:
                        voxel_faces[i0].append(p0 + square_rot_neg)

                    # draw middle faces
                    for r1, r2 in itertools.pairwise(rinds):
                        p1 = permute.dot([p, q, r1])
                        p2 = permute.dot([p, q, r2])

                        i1 = tuple(p1)
                        i2 = tuple(p2)

                        if filled[i1] and not filled[i2]:
                            voxel_faces[i1].append(p2 + square_rot_pos)
                        elif not filled[i1] and filled[i2]:
                            voxel_faces[i2].append(p2 + square_rot_neg)

                    # draw upper faces
                    pk = permute.dot([p, q, rc-1])
                    pk2 = permute.dot([p, q, rc])
                    ik = tuple(pk)
                    if filled[ik]:
                        voxel_faces[ik].append(pk2 + square_rot_pos)

        # iterate over the faces, and generate a Poly3DCollection for each
        # voxel
        polygons = {}
        for coord, faces_inds in voxel_faces.items():
            # convert indices into 3D positions
            if xyz is None:
                faces = faces_inds
            else:
                faces = []
                for face_inds in faces_inds:
                    ind = face_inds[:, 0], face_inds[:, 1], face_inds[:, 2]
                    face = np.empty(face_inds.shape)
                    face[:, 0] = x[ind]
                    face[:, 1] = y[ind]
                    face[:, 2] = z[ind]
                    faces.append(face)

            # shade the faces
            facecolor = facecolors[coord]
            edgecolor = edgecolors[coord]

            poly = art3d.Poly3DCollection(
                faces, facecolors=facecolor, edgecolors=edgecolor,
                shade=shade, lightsource=lightsource, axlim_clip=axlim_clip,
                **kwargs)
            self.add_collection3d(poly)
            polygons[coord] = poly

        return polygons

    @_preprocess_data(replace_names=["x", "y", "z", "xerr", "yerr", "zerr"])
    def errorbar(self, x, y, z, zerr=None, yerr=None, xerr=None, fmt='',
                 barsabove=False, errorevery=1, ecolor=None, elinewidth=None,
                 capsize=None, capthick=None, xlolims=False, xuplims=False,
                 ylolims=False, yuplims=False, zlolims=False, zuplims=False,
                 axlim_clip=False,
                 **kwargs):
        """
        Plot lines and/or markers with errorbars around them.

        *x*/*y*/*z* define the data locations, and *xerr*/*yerr*/*zerr* define
        the errorbar sizes. By default, this draws the data markers/lines as
        well the errorbars. Use fmt='none' to draw errorbars only.

        Parameters
        ----------
        x, y, z : float or array-like
            The data positions.

        xerr, yerr, zerr : float or array-like, shape (N,) or (2, N), optional
            The errorbar sizes:

            - scalar: Symmetric +/- values for all data points.
            - shape(N,): Symmetric +/-values for each data point.
            - shape(2, N): Separate - and + values for each bar. First row
              contains the lower errors, the second row contains the upper
              errors.
            - *None*: No errorbar.

            Note that all error arrays should have *positive* values.

        fmt : str, default: ''
            The format for the data points / data lines. See `.plot` for
            details.

            Use 'none' (case-insensitive) to plot errorbars without any data
            markers.

        ecolor : :mpltype:`color`, default: None
            The color of the errorbar lines.  If None, use the color of the
            line connecting the markers.

        elinewidth : float, default: None
            The linewidth of the errorbar lines. If None, the linewidth of
            the current style is used.

        capsize : float, default: :rc:`errorbar.capsize`
            The length of the error bar caps in points.

        capthick : float, default: None
            An alias to the keyword argument *markeredgewidth* (a.k.a. *mew*).
            This setting is a more sensible name for the property that
            controls the thickness of the error bar cap in points. For
            backwards compatibility, if *mew* or *markeredgewidth* are given,
            then they will over-ride *capthick*. This may change in future
            releases.

        barsabove : bool, default: False
            If True, will plot the errorbars above the plot
            symbols. Default is below.

        xlolims, ylolims, zlolims : bool, default: False
            These arguments can be used to indicate that a value gives only
            lower limits. In that case a caret symbol is used to indicate
            this. *lims*-arguments may be scalars, or array-likes of the same
            length as the errors. To use limits with inverted axes,
            `~.set_xlim`, `~.set_ylim`, or `~.set_zlim` must be
            called before `errorbar`. Note the tricky parameter names: setting
            e.g. *ylolims* to True means that the y-value is a *lower* limit of
            the True value, so, only an *upward*-pointing arrow will be drawn!

        xuplims, yuplims, zuplims : bool, default: False
            Same as above, but for controlling the upper limits.

        errorevery : int or (int, int), default: 1
            draws error bars on a subset of the data. *errorevery* =N draws
            error bars on the points (x[::N], y[::N], z[::N]).
            *errorevery* =(start, N) draws error bars on the points
            (x[start::N], y[start::N], z[start::N]). e.g. *errorevery* =(6, 3)
            adds error bars to the data at (x[6], x[9], x[12], x[15], ...).
            Used to avoid overlapping error bars when two series share x-axis
            values.

        axlim_clip : bool, default: False
            Whether to hide error bars that are outside the axes limits.

            .. versionadded:: 3.10

        Returns
        -------
        errlines : list
            List of `~mpl_toolkits.mplot3d.art3d.Line3DCollection` instances
            each containing an errorbar line.
        caplines : list
            List of `~mpl_toolkits.mplot3d.art3d.Line3D` instances each
            containing a capline object.
        limmarks : list
            List of `~mpl_toolkits.mplot3d.art3d.Line3D` instances each
            containing a marker with an upper or lower limit.

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            All other keyword arguments for styling errorbar lines are passed
            `~mpl_toolkits.mplot3d.art3d.Line3DCollection`.

        Examples
        --------
        .. plot:: gallery/mplot3d/errorbar3d.py
        """
        had_data = self.has_data()

        kwargs = cbook.normalize_kwargs(kwargs, mlines.Line2D)
        # Drop anything that comes in as None to use the default instead.
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        kwargs.setdefault('zorder', 2)

        self._process_unit_info([("x", x), ("y", y), ("z", z)], kwargs,
                                convert=False)

        # make sure all the args are iterable; use lists not arrays to
        # preserve units
        x = x if np.iterable(x) else [x]
        y = y if np.iterable(y) else [y]
        z = z if np.iterable(z) else [z]

        if not len(x) == len(y) == len(z):
            raise ValueError("'x', 'y', and 'z' must have the same size")

        everymask = self._errorevery_to_mask(x, errorevery)

        label = kwargs.pop("label", None)
        kwargs['label'] = '_nolegend_'

        # Create the main line and determine overall kwargs for child artists.
        # We avoid calling self.plot() directly, or self._get_lines(), because
        # that would call self._process_unit_info again, and do other indirect
        # data processing.
        (data_line, base_style), = self._get_lines._plot_args(
            self, (x, y) if fmt == '' else (x, y, fmt), kwargs, return_kwargs=True)
        art3d.line_2d_to_3d(data_line, zs=z, axlim_clip=axlim_clip)

        # Do this after creating `data_line` to avoid modifying `base_style`.
        if barsabove:
            data_line.set_zorder(kwargs['zorder'] - .1)
        else:
            data_line.set_zorder(kwargs['zorder'] + .1)

        # Add line to plot, or throw it away and use it to determine kwargs.
        if fmt.lower() != 'none':
            self.add_line(data_line)
        else:
            data_line = None
            # Remove alpha=0 color that _process_plot_format returns.
            base_style.pop('color')

        if 'color' not in base_style:
            base_style['color'] = 'C0'
        if ecolor is None:
            ecolor = base_style['color']

        # Eject any line-specific information from format string, as it's not
        # needed for bars or caps.
        for key in ['marker', 'markersize', 'markerfacecolor',
                    'markeredgewidth', 'markeredgecolor', 'markevery',
                    'linestyle', 'fillstyle', 'drawstyle', 'dash_capstyle',
                    'dash_joinstyle', 'solid_capstyle', 'solid_joinstyle']:
            base_style.pop(key, None)

        # Make the style dict for the line collections (the bars).
        eb_lines_style = {**base_style, 'color': ecolor}

        if elinewidth:
            eb_lines_style['linewidth'] = elinewidth
        elif 'linewidth' in kwargs:
            eb_lines_style['linewidth'] = kwargs['linewidth']

        for key in ('transform', 'alpha', 'zorder', 'rasterized'):
            if key in kwargs:
                eb_lines_style[key] = kwargs[key]

        # Make the style dict for caps (the "hats").
        eb_cap_style = {**base_style, 'linestyle': 'None'}
        if capsize is None:
            capsize = mpl.rcParams["errorbar.capsize"]
        if capsize > 0:
            eb_cap_style['markersize'] = 2. * capsize
        if capthick is not None:
            eb_cap_style['markeredgewidth'] = capthick
        eb_cap_style['color'] = ecolor

        def _apply_mask(arrays, mask):
            # Return, for each array in *arrays*, the elements for which *mask*
            # is True, without using fancy indexing.
            return [[*itertools.compress(array, mask)] for array in arrays]

        def _extract_errs(err, data, lomask, himask):
            # For separate +/- error values we need to unpack err
            if len(err.shape) == 2:
                low_err, high_err = err
            else:
                low_err, high_err = err, err

            lows = np.where(lomask | ~everymask, data, data - low_err)
            highs = np.where(himask | ~everymask, data, data + high_err)

            return lows, highs

        # collect drawn items while looping over the three coordinates
        errlines, caplines, limmarks = [], [], []

        # list of endpoint coordinates, used for auto-scaling
        coorderrs = []

        # define the markers used for errorbar caps and limits below
        # the dictionary key is mapped by the `i_xyz` helper dictionary
        capmarker = {0: '|', 1: '|', 2: '_'}
        i_xyz = {'x': 0, 'y': 1, 'z': 2}

        # Calculate marker size from points to quiver length. Because these are
        # not markers, and 3D Axes do not use the normal transform stack, this
        # is a bit involved. Since the quiver arrows will change size as the
        # scene is rotated, they are given a standard size based on viewing
        # them directly in planar form.
        quiversize = eb_cap_style.get('markersize',
                                      mpl.rcParams['lines.markersize']) ** 2
        quiversize *= self.get_figure(root=True).dpi / 72
        quiversize = self.transAxes.inverted().transform([
            (0, 0), (quiversize, quiversize)])
        quiversize = np.mean(np.diff(quiversize, axis=0))
        # quiversize is now in Axes coordinates, and to convert back to data
        # coordinates, we need to run it through the inverse 3D transform. For
        # consistency, this uses a fixed elevation, azimuth, and roll.
        with cbook._setattr_cm(self, elev=0, azim=0, roll=0):
            invM = np.linalg.inv(self.get_proj())
        # elev=azim=roll=0 produces the Y-Z plane, so quiversize in 2D 'x' is
        # 'y' in 3D, hence the 1 index.
        quiversize = np.dot(invM, [quiversize, 0, 0, 0])[1]
        # Quivers use a fixed 15-degree arrow head, so scale up the length so
        # that the size corresponds to the base. In other words, this constant
        # corresponds to the equation tan(15) = (base / 2) / (arrow length).
        quiversize *= 1.8660254037844388
        eb_quiver_style = {**eb_cap_style,
                           'length': quiversize, 'arrow_length_ratio': 1}
        eb_quiver_style.pop('markersize', None)

        # loop over x-, y-, and z-direction and draw relevant elements
        for zdir, data, err, lolims, uplims in zip(
                ['x', 'y', 'z'], [x, y, z], [xerr, yerr, zerr],
                [xlolims, ylolims, zlolims], [xuplims, yuplims, zuplims]):

            dir_vector = art3d.get_dir_vector(zdir)
            i_zdir = i_xyz[zdir]

            if err is None:
                continue

            if not np.iterable(err):
                err = [err] * len(data)

            err = np.atleast_1d(err)

            # arrays fine here, they are booleans and hence not units
            lolims = np.broadcast_to(lolims, len(data)).astype(bool)
            uplims = np.broadcast_to(uplims, len(data)).astype(bool)

            # a nested list structure that expands to (xl,xh),(yl,yh),(zl,zh),
            # where x/y/z and l/h correspond to dimensions and low/high
            # positions of errorbars in a dimension we're looping over
            coorderr = [
                _extract_errs(err * dir_vector[i], coord, lolims, uplims)
                for i, coord in enumerate([x, y, z])]
            (xl, xh), (yl, yh), (zl, zh) = coorderr

            # draws capmarkers - flat caps orthogonal to the error bars
            nolims = ~(lolims | uplims)
            if nolims.any() and capsize > 0:
                lo_caps_xyz = _apply_mask([xl, yl, zl], nolims & everymask)
                hi_caps_xyz = _apply_mask([xh, yh, zh], nolims & everymask)

                # setting '_' for z-caps and '|' for x- and y-caps;
                # these markers will rotate as the viewing angle changes
                cap_lo = art3d.Line3D(*lo_caps_xyz, ls='',
                                      marker=capmarker[i_zdir],
                                      axlim_clip=axlim_clip,
                                      **eb_cap_style)
                cap_hi = art3d.Line3D(*hi_caps_xyz, ls='',
                                      marker=capmarker[i_zdir],
                                      axlim_clip=axlim_clip,
                                      **eb_cap_style)
                self.add_line(cap_lo)
                self.add_line(cap_hi)
                caplines.append(cap_lo)
                caplines.append(cap_hi)

            if lolims.any():
                xh0, yh0, zh0 = _apply_mask([xh, yh, zh], lolims & everymask)
                self.quiver(xh0, yh0, zh0, *dir_vector, **eb_quiver_style)
            if uplims.any():
                xl0, yl0, zl0 = _apply_mask([xl, yl, zl], uplims & everymask)
                self.quiver(xl0, yl0, zl0, *-dir_vector, **eb_quiver_style)

            errline = art3d.Line3DCollection(np.array(coorderr).T,
                                             axlim_clip=axlim_clip,
                                             **eb_lines_style)
            self.add_collection(errline)
            errlines.append(errline)
            coorderrs.append(coorderr)

        coorderrs = np.array(coorderrs)

        def _digout_minmax(err_arr, coord_label):
            return (np.nanmin(err_arr[:, i_xyz[coord_label], :, :]),
                    np.nanmax(err_arr[:, i_xyz[coord_label], :, :]))

        minx, maxx = _digout_minmax(coorderrs, 'x')
        miny, maxy = _digout_minmax(coorderrs, 'y')
        minz, maxz = _digout_minmax(coorderrs, 'z')
        self.auto_scale_xyz((minx, maxx), (miny, maxy), (minz, maxz), had_data)

        # Adapting errorbar containers for 3d case, assuming z-axis points "up"
        errorbar_container = mcontainer.ErrorbarContainer(
            (data_line, tuple(caplines), tuple(errlines)),
            has_xerr=(xerr is not None or yerr is not None),
            has_yerr=(zerr is not None),
            label=label)
        self.containers.append(errorbar_container)

        return errlines, caplines, limmarks

    def get_tightbbox(self, renderer=None, *, call_axes_locator=True,
                      bbox_extra_artists=None, for_layout_only=False):
        ret = super().get_tightbbox(renderer,
                                    call_axes_locator=call_axes_locator,
                                    bbox_extra_artists=bbox_extra_artists,
                                    for_layout_only=for_layout_only)
        batch = [ret]
        if self._axis3don:
            for axis in self._axis_map.values():
                if axis.get_visible():
                    axis_bb = martist._get_tightbbox_for_layout_only(
                        axis, renderer)
                    if axis_bb:
                        batch.append(axis_bb)
        return mtransforms.Bbox.union(batch)

    @_preprocess_data()
    def stem(self, x, y, z, *, linefmt='C0-', markerfmt='C0o', basefmt='C3-',
             bottom=0, label=None, orientation='z', axlim_clip=False):
        """
        Create a 3D stem plot.

        A stem plot draws lines perpendicular to a baseline, and places markers
        at the heads. By default, the baseline is defined by *x* and *y*, and
        stems are drawn vertically from *bottom* to *z*.

        Parameters
        ----------
        x, y, z : array-like
            The positions of the heads of the stems. The stems are drawn along
            the *orientation*-direction from the baseline at *bottom* (in the
            *orientation*-coordinate) to the heads. By default, the *x* and *y*
            positions are used for the baseline and *z* for the head position,
            but this can be changed by *orientation*.

        linefmt : str, default: 'C0-'
            A string defining the properties of the vertical lines. Usually,
            this will be a color or a color and a linestyle:

            =========  =============
            Character  Line Style
            =========  =============
            ``'-'``    solid line
            ``'--'``   dashed line
            ``'-.'``   dash-dot line
            ``':'``    dotted line
            =========  =============

            Note: While it is technically possible to specify valid formats
            other than color or color and linestyle (e.g. 'rx' or '-.'), this
            is beyond the intention of the method and will most likely not
            result in a reasonable plot.

        markerfmt : str, default: 'C0o'
            A string defining the properties of the markers at the stem heads.

        basefmt : str, default: 'C3-'
            A format string defining the properties of the baseline.

        bottom : float, default: 0
            The position of the baseline, in *orientation*-coordinates.

        label : str, optional
            The label to use for the stems in legends.

        orientation : {'x', 'y', 'z'}, default: 'z'
            The direction along which stems are drawn.

        axlim_clip : bool, default: False
            Whether to hide stems that are outside the axes limits.

            .. versionadded:: 3.10

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        Returns
        -------
        `.StemContainer`
            The container may be treated like a tuple
            (*markerline*, *stemlines*, *baseline*)

        Examples
        --------
        .. plot:: gallery/mplot3d/stem3d_demo.py
        """

        from matplotlib.container import StemContainer

        had_data = self.has_data()

        _api.check_in_list(['x', 'y', 'z'], orientation=orientation)

        xlim = (np.min(x), np.max(x))
        ylim = (np.min(y), np.max(y))
        zlim = (np.min(z), np.max(z))

        # Determine the appropriate plane for the baseline and the direction of
        # stemlines based on the value of orientation.
        if orientation == 'x':
            basex, basexlim = y, ylim
            basey, baseylim = z, zlim
            lines = [[(bottom, thisy, thisz), (thisx, thisy, thisz)]
                     for thisx, thisy, thisz in zip(x, y, z)]
        elif orientation == 'y':
            basex, basexlim = x, xlim
            basey, baseylim = z, zlim
            lines = [[(thisx, bottom, thisz), (thisx, thisy, thisz)]
                     for thisx, thisy, thisz in zip(x, y, z)]
        else:
            basex, basexlim = x, xlim
            basey, baseylim = y, ylim
            lines = [[(thisx, thisy, bottom), (thisx, thisy, thisz)]
                     for thisx, thisy, thisz in zip(x, y, z)]

        # Determine style for stem lines.
        linestyle, linemarker, linecolor = _process_plot_format(linefmt)
        if linestyle is None:
            linestyle = mpl.rcParams['lines.linestyle']

        # Plot everything in required order.
        baseline, = self.plot(basex, basey, basefmt, zs=bottom,
                              zdir=orientation, label='_nolegend_')
        stemlines = art3d.Line3DCollection(
            lines, linestyles=linestyle, colors=linecolor, label='_nolegend_',
            axlim_clip=axlim_clip)
        self.add_collection(stemlines)
        markerline, = self.plot(x, y, z, markerfmt, label='_nolegend_')

        stem_container = StemContainer((markerline, stemlines, baseline),
                                       label=label)
        self.add_container(stem_container)

        jx, jy, jz = art3d.juggle_axes(basexlim, baseylim, [bottom, bottom],
                                       orientation)
        self.auto_scale_xyz([*jx, *xlim], [*jy, *ylim], [*jz, *zlim], had_data)

        return stem_container

    stem3D = stem


def get_test_data(delta=0.05):
    """Return a tuple X, Y, Z with a test data set."""
    x = y = np.arange(-3.0, 3.0, delta)
    X, Y = np.meshgrid(x, y)

    Z1 = np.exp(-(X**2 + Y**2) / 2) / (2 * np.pi)
    Z2 = (np.exp(-(((X - 1) / 1.5)**2 + ((Y - 1) / 0.5)**2) / 2) /
          (2 * np.pi * 0.5 * 1.5))
    Z = Z2 - Z1

    X = X * 10
    Y = Y * 10
    Z = Z * 500
    return X, Y, Z


class _Quaternion:
    """
    Quaternions
    consisting of scalar, along 1, and vector, with components along i, j, k
    """

    def __init__(self, scalar, vector):
        self.scalar = scalar
        self.vector = np.array(vector)

    def __neg__(self):
        return self.__class__(-self.scalar, -self.vector)

    def __mul__(self, other):
        """
        Product of two quaternions
        i*i = j*j = k*k = i*j*k = -1
        Quaternion multiplication can be expressed concisely
        using scalar and vector parts,
        see <https://en.wikipedia.org/wiki/Quaternion#Scalar_and_vector_parts>
        """
        return self.__class__(
            self.scalar*other.scalar - np.dot(self.vector, other.vector),
            self.scalar*other.vector + self.vector*other.scalar
            + np.cross(self.vector, other.vector))

    def conjugate(self):
        """The conjugate quaternion -(1/2)*(q+i*q*i+j*q*j+k*q*k)"""
        return self.__class__(self.scalar, -self.vector)

    @property
    def norm(self):
        """The 2-norm, q*q', a scalar"""
        return self.scalar*self.scalar + np.dot(self.vector, self.vector)

    def normalize(self):
        """Scaling such that norm equals 1"""
        n = np.sqrt(self.norm)
        return self.__class__(self.scalar/n, self.vector/n)

    def reciprocal(self):
        """The reciprocal, 1/q = q'/(q*q') = q' / norm(q)"""
        n = self.norm
        return self.__class__(self.scalar/n, -self.vector/n)

    def __div__(self, other):
        return self*other.reciprocal()

    __truediv__ = __div__

    def rotate(self, v):
        # Rotate the vector v by the quaternion q, i.e.,
        # calculate (the vector part of) q*v/q
        v = self.__class__(0, v)
        v = self*v/self
        return v.vector

    def __eq__(self, other):
        return (self.scalar == other.scalar) and (self.vector == other.vector).all

    def __repr__(self):
        return "_Quaternion({}, {})".format(repr(self.scalar), repr(self.vector))

    @classmethod
    def rotate_from_to(cls, r1, r2):
        """
        The quaternion for the shortest rotation from vector r1 to vector r2
        i.e., q = sqrt(r2*r1'), normalized.
        If r1 and r2 are antiparallel, then the result is ambiguous;
        a normal vector will be returned, and a warning will be issued.
        """
        k = np.cross(r1, r2)
        nk = np.linalg.norm(k)
        th = np.arctan2(nk, np.dot(r1, r2))
        th /= 2
        if nk == 0:  # r1 and r2 are parallel or anti-parallel
            if np.dot(r1, r2) < 0:
                warnings.warn("Rotation defined by anti-parallel vectors is ambiguous")
                k = np.zeros(3)
                k[np.argmin(r1*r1)] = 1  # basis vector most perpendicular to r1-r2
                k = np.cross(r1, k)
                k = k / np.linalg.norm(k)  # unit vector normal to r1-r2
                q = cls(0, k)
            else:
                q = cls(1, [0, 0, 0])  # = 1, no rotation
        else:
            q = cls(np.cos(th), k*np.sin(th)/nk)
        return q

    @classmethod
    def from_cardan_angles(cls, elev, azim, roll):
        """
        Converts the angles to a quaternion
            q = exp((roll/2)*e_x)*exp((elev/2)*e_y)*exp((-azim/2)*e_z)
        i.e., the angles are a kind of Tait-Bryan angles, -z,y',x".
        The angles should be given in radians, not degrees.
        """
        ca, sa = np.cos(azim/2), np.sin(azim/2)
        ce, se = np.cos(elev/2), np.sin(elev/2)
        cr, sr = np.cos(roll/2), np.sin(roll/2)

        qw = ca*ce*cr + sa*se*sr
        qx = ca*ce*sr - sa*se*cr
        qy = ca*se*cr + sa*ce*sr
        qz = ca*se*sr - sa*ce*cr
        return cls(qw, [qx, qy, qz])

    def as_cardan_angles(self):
        """
        The inverse of `from_cardan_angles()`.
        Note that the angles returned are in radians, not degrees.
        The angles are not sensitive to the quaternion's norm().
        """
        qw = self.scalar
        qx, qy, qz = self.vector[..., :]
        azim = np.arctan2(2*(-qw*qz+qx*qy), qw*qw+qx*qx-qy*qy-qz*qz)
        elev = np.arcsin(np.clip(2*(qw*qy+qz*qx)/(qw*qw+qx*qx+qy*qy+qz*qz), -1, 1))
        roll = np.arctan2(2*(qw*qx-qy*qz), qw*qw-qx*qx-qy*qy+qz*qz)
        return elev, azim, roll
