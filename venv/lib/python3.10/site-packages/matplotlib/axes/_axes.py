import functools
import itertools
import logging
import math
from numbers import Integral, Number, Real

import re
import numpy as np

import matplotlib as mpl
import matplotlib.category  # Register category unit converter as side effect.
import matplotlib.cbook as cbook
import matplotlib.collections as mcoll
import matplotlib.colorizer as mcolorizer
import matplotlib.colors as mcolors
import matplotlib.contour as mcontour
import matplotlib.dates  # noqa: F401, Register date unit converter as side effect.
import matplotlib.image as mimage
import matplotlib.inset as minset
import matplotlib.legend as mlegend
import matplotlib.lines as mlines
import matplotlib.markers as mmarkers
import matplotlib.mlab as mlab
import matplotlib.patches as mpatches
import matplotlib.path as mpath
import matplotlib.quiver as mquiver
import matplotlib.stackplot as mstack
import matplotlib.streamplot as mstream
import matplotlib.table as mtable
import matplotlib.text as mtext
import matplotlib.ticker as mticker
import matplotlib.transforms as mtransforms
import matplotlib.tri as mtri
import matplotlib.units as munits
from matplotlib import _api, _docstring, _preprocess_data
from matplotlib.axes._base import (
    _AxesBase, _TransformedBoundsLocator, _process_plot_format)
from matplotlib.axes._secondary_axes import SecondaryAxis
from matplotlib.container import BarContainer, ErrorbarContainer, StemContainer
from matplotlib.transforms import _ScaledRotation

_log = logging.getLogger(__name__)


# The axes module contains all the wrappers to plotting functions.
# All the other methods should go in the _AxesBase class.


def _make_axes_method(func):
    """
    Patch the qualname for functions that are directly added to Axes.

    Some Axes functionality is defined in functions in other submodules.
    These are simply added as attributes to Axes. As a result, their
    ``__qualname__`` is e.g. only "table" and not "Axes.table". This
    function fixes that.

    Note that the function itself is patched, so that
    ``matplotlib.table.table.__qualname__` will also show "Axes.table".
    However, since these functions are not intended to be standalone,
    this is bearable.
    """
    func.__qualname__ = f"Axes.{func.__name__}"
    return func


@_docstring.interpd
class Axes(_AxesBase):
    """
    An Axes object encapsulates all the elements of an individual (sub-)plot in
    a figure.

    It contains most of the (sub-)plot elements: `~.axis.Axis`,
    `~.axis.Tick`, `~.lines.Line2D`, `~.text.Text`, `~.patches.Polygon`, etc.,
    and sets the coordinate system.

    Like all visible elements in a figure, Axes is an `.Artist` subclass.

    The `Axes` instance supports callbacks through a callbacks attribute which
    is a `~.cbook.CallbackRegistry` instance.  The events you can connect to
    are 'xlim_changed' and 'ylim_changed' and the callback will be called with
    func(*ax*) where *ax* is the `Axes` instance.

    .. note::

        As a user, you do not instantiate Axes directly, but use Axes creation
        methods instead; e.g. from `.pyplot` or `.Figure`:
        `~.pyplot.subplots`, `~.pyplot.subplot_mosaic` or `.Figure.add_axes`.

    """
    ### Labelling, legend and texts

    def get_title(self, loc="center"):
        """
        Get an Axes title.

        Get one of the three available Axes titles. The available titles
        are positioned above the Axes in the center, flush with the left
        edge, and flush with the right edge.

        Parameters
        ----------
        loc : {'center', 'left', 'right'}, str, default: 'center'
            Which title to return.

        Returns
        -------
        str
            The title text string.

        """
        titles = {'left': self._left_title,
                  'center': self.title,
                  'right': self._right_title}
        title = _api.check_getitem(titles, loc=loc.lower())
        return title.get_text()

    def set_title(self, label, fontdict=None, loc=None, pad=None, *, y=None,
                  **kwargs):
        """
        Set a title for the Axes.

        Set one of the three available Axes titles. The available titles
        are positioned above the Axes in the center, flush with the left
        edge, and flush with the right edge.

        Parameters
        ----------
        label : str
            Text to use for the title

        fontdict : dict

            .. admonition:: Discouraged

               The use of *fontdict* is discouraged. Parameters should be passed as
               individual keyword arguments or using dictionary-unpacking
               ``set_title(..., **fontdict)``.

            A dictionary controlling the appearance of the title text,
            the default *fontdict* is::

               {'fontsize': rcParams['axes.titlesize'],
                'fontweight': rcParams['axes.titleweight'],
                'color': rcParams['axes.titlecolor'],
                'verticalalignment': 'baseline',
                'horizontalalignment': loc}

        loc : {'center', 'left', 'right'}, default: :rc:`axes.titlelocation`
            Which title to set.

        y : float, default: :rc:`axes.titley`
            Vertical Axes location for the title (1.0 is the top).  If
            None (the default) and :rc:`axes.titley` is also None, y is
            determined automatically to avoid decorators on the Axes.

        pad : float, default: :rc:`axes.titlepad`
            The offset of the title from the top of the Axes, in points.

        Returns
        -------
        `.Text`
            The matplotlib text instance representing the title

        Other Parameters
        ----------------
        **kwargs : `~matplotlib.text.Text` properties
            Other keyword arguments are text properties, see `.Text` for a list
            of valid text properties.
        """
        if loc is None:
            loc = mpl.rcParams['axes.titlelocation']

        if y is None:
            y = mpl.rcParams['axes.titley']
        if y is None:
            y = 1.0
        else:
            self._autotitlepos = False
        kwargs['y'] = y

        titles = {'left': self._left_title,
                  'center': self.title,
                  'right': self._right_title}
        title = _api.check_getitem(titles, loc=loc.lower())
        default = {
            'fontsize': mpl.rcParams['axes.titlesize'],
            'fontweight': mpl.rcParams['axes.titleweight'],
            'verticalalignment': 'baseline',
            'horizontalalignment': loc.lower()}
        titlecolor = mpl.rcParams['axes.titlecolor']
        if not cbook._str_lower_equal(titlecolor, 'auto'):
            default["color"] = titlecolor
        if pad is None:
            pad = mpl.rcParams['axes.titlepad']
        self._set_title_offset_trans(float(pad))
        title.set_text(label)
        title.update(default)
        if fontdict is not None:
            title.update(fontdict)
        title._internal_update(kwargs)
        return title

    def get_legend_handles_labels(self, legend_handler_map=None):
        """
        Return handles and labels for legend

        ``ax.legend()`` is equivalent to ::

          h, l = ax.get_legend_handles_labels()
          ax.legend(h, l)
        """
        # pass through to legend.
        handles, labels = mlegend._get_legend_handles_labels(
            [self], legend_handler_map)
        return handles, labels

    @_docstring.interpd
    def legend(self, *args, **kwargs):
        """
        Place a legend on the Axes.

        Call signatures::

            legend()
            legend(handles, labels)
            legend(handles=handles)
            legend(labels)

        The call signatures correspond to the following different ways to use
        this method:

        **1. Automatic detection of elements to be shown in the legend**

        The elements to be added to the legend are automatically determined,
        when you do not pass in any extra arguments.

        In this case, the labels are taken from the artist. You can specify
        them either at artist creation or by calling the
        :meth:`~.Artist.set_label` method on the artist::

            ax.plot([1, 2, 3], label='Inline label')
            ax.legend()

        or::

            line, = ax.plot([1, 2, 3])
            line.set_label('Label via method')
            ax.legend()

        .. note::
            Specific artists can be excluded from the automatic legend element
            selection by using a label starting with an underscore, "_".
            A string starting with an underscore is the default label for all
            artists, so calling `.Axes.legend` without any arguments and
            without setting the labels manually will result in a ``UserWarning``
            and an empty legend being drawn.


        **2. Explicitly listing the artists and labels in the legend**

        For full control of which artists have a legend entry, it is possible
        to pass an iterable of legend artists followed by an iterable of
        legend labels respectively::

            ax.legend([line1, line2, line3], ['label1', 'label2', 'label3'])


        **3. Explicitly listing the artists in the legend**

        This is similar to 2, but the labels are taken from the artists'
        label properties. Example::

            line1, = ax.plot([1, 2, 3], label='label1')
            line2, = ax.plot([1, 2, 3], label='label2')
            ax.legend(handles=[line1, line2])


        **4. Labeling existing plot elements**

        .. admonition:: Discouraged

            This call signature is discouraged, because the relation between
            plot elements and labels is only implicit by their order and can
            easily be mixed up.

        To make a legend for all artists on an Axes, call this function with
        an iterable of strings, one for each legend item. For example::

            ax.plot([1, 2, 3])
            ax.plot([5, 6, 7])
            ax.legend(['First line', 'Second line'])


        Parameters
        ----------
        handles : list of (`.Artist` or tuple of `.Artist`), optional
            A list of Artists (lines, patches) to be added to the legend.
            Use this together with *labels*, if you need full control on what
            is shown in the legend and the automatic mechanism described above
            is not sufficient.

            The length of handles and labels should be the same in this
            case. If they are not, they are truncated to the smaller length.

            If an entry contains a tuple, then the legend handler for all Artists in the
            tuple will be placed alongside a single label.

        labels : list of str, optional
            A list of labels to show next to the artists.
            Use this together with *handles*, if you need full control on what
            is shown in the legend and the automatic mechanism described above
            is not sufficient.

        Returns
        -------
        `~matplotlib.legend.Legend`

        Other Parameters
        ----------------
        %(_legend_kw_axes)s

        See Also
        --------
        .Figure.legend

        Notes
        -----
        Some artists are not supported by this function.  See
        :ref:`legend_guide` for details.

        Examples
        --------
        .. plot:: gallery/text_labels_and_annotations/legend.py
        """
        handles, labels, kwargs = mlegend._parse_legend_args([self], *args, **kwargs)
        self.legend_ = mlegend.Legend(self, handles, labels, **kwargs)
        self.legend_._remove_method = self._remove_legend
        return self.legend_

    def _remove_legend(self, legend):
        self.legend_ = None

    def inset_axes(self, bounds, *, transform=None, zorder=5, **kwargs):
        """
        Add a child inset Axes to this existing Axes.


        Parameters
        ----------
        bounds : [x0, y0, width, height]
            Lower-left corner of inset Axes, and its width and height.

        transform : `.Transform`
            Defaults to `ax.transAxes`, i.e. the units of *rect* are in
            Axes-relative coordinates.

        projection : {None, 'aitoff', 'hammer', 'lambert', 'mollweide', \
'polar', 'rectilinear', str}, optional
            The projection type of the inset `~.axes.Axes`. *str* is the name
            of a custom projection, see `~matplotlib.projections`. The default
            None results in a 'rectilinear' projection.

        polar : bool, default: False
            If True, equivalent to projection='polar'.

        axes_class : subclass type of `~.axes.Axes`, optional
            The `.axes.Axes` subclass that is instantiated.  This parameter
            is incompatible with *projection* and *polar*.  See
            :ref:`axisartist_users-guide-index` for examples.

        zorder : number
            Defaults to 5 (same as `.Axes.legend`).  Adjust higher or lower
            to change whether it is above or below data plotted on the
            parent Axes.

        **kwargs
            Other keyword arguments are passed on to the inset Axes class.

        Returns
        -------
        ax
            The created `~.axes.Axes` instance.

        Examples
        --------
        This example makes two inset Axes, the first is in Axes-relative
        coordinates, and the second in data-coordinates::

            fig, ax = plt.subplots()
            ax.plot(range(10))
            axin1 = ax.inset_axes([0.8, 0.1, 0.15, 0.15])
            axin2 = ax.inset_axes(
                    [5, 7, 2.3, 2.3], transform=ax.transData)

        """
        if transform is None:
            transform = self.transAxes
        kwargs.setdefault('label', 'inset_axes')

        # This puts the rectangle into figure-relative coordinates.
        inset_locator = _TransformedBoundsLocator(bounds, transform)
        bounds = inset_locator(self, None).bounds
        fig = self.get_figure(root=False)
        projection_class, pkw = fig._process_projection_requirements(**kwargs)
        inset_ax = projection_class(fig, bounds, zorder=zorder, **pkw)

        # this locator lets the axes move if in data coordinates.
        # it gets called in `ax.apply_aspect() (of all places)
        inset_ax.set_axes_locator(inset_locator)

        self.add_child_axes(inset_ax)

        return inset_ax

    @_docstring.interpd
    def indicate_inset(self, bounds=None, inset_ax=None, *, transform=None,
                       facecolor='none', edgecolor='0.5', alpha=0.5,
                       zorder=None, **kwargs):
        """
        Add an inset indicator to the Axes.  This is a rectangle on the plot
        at the position indicated by *bounds* that optionally has lines that
        connect the rectangle to an inset Axes (`.Axes.inset_axes`).

        Warnings
        --------
        This method is experimental as of 3.0, and the API may change.

        Parameters
        ----------
        bounds : [x0, y0, width, height], optional
            Lower-left corner of rectangle to be marked, and its width
            and height.  If not set, the bounds will be calculated from the
            data limits of *inset_ax*, which must be supplied.

        inset_ax : `.Axes`, optional
            An optional inset Axes to draw connecting lines to.  Two lines are
            drawn connecting the indicator box to the inset Axes on corners
            chosen so as to not overlap with the indicator box.

        transform : `.Transform`
            Transform for the rectangle coordinates. Defaults to
            ``ax.transAxes``, i.e. the units of *rect* are in Axes-relative
            coordinates.

        facecolor : :mpltype:`color`, default: 'none'
            Facecolor of the rectangle.

        edgecolor : :mpltype:`color`, default: '0.5'
            Color of the rectangle and color of the connecting lines.

        alpha : float or None, default: 0.5
            Transparency of the rectangle and connector lines.  If not
            ``None``, this overrides any alpha value included in the
            *facecolor* and *edgecolor* parameters.

        zorder : float, default: 4.99
            Drawing order of the rectangle and connector lines.  The default,
            4.99, is just below the default level of inset Axes.

        **kwargs
            Other keyword arguments are passed on to the `.Rectangle` patch:

            %(Rectangle:kwdoc)s

        Returns
        -------
        inset_indicator : `.inset.InsetIndicator`
            An artist which contains

            inset_indicator.rectangle : `.Rectangle`
                The indicator frame.

            inset_indicator.connectors : 4-tuple of `.patches.ConnectionPatch`
                The four connector lines connecting to (lower_left, upper_left,
                lower_right upper_right) corners of *inset_ax*. Two lines are
                set with visibility to *False*,  but the user can set the
                visibility to True if the automatic choice is not deemed correct.

            .. versionchanged:: 3.10
                Previously the rectangle and connectors tuple were returned.
        """
        # to make the Axes connectors work, we need to apply the aspect to
        # the parent Axes.
        self.apply_aspect()

        if transform is None:
            transform = self.transData
        kwargs.setdefault('label', '_indicate_inset')

        indicator_patch = minset.InsetIndicator(
            bounds, inset_ax=inset_ax,
            facecolor=facecolor, edgecolor=edgecolor, alpha=alpha,
            zorder=zorder, transform=transform, **kwargs)
        self.add_artist(indicator_patch)

        return indicator_patch

    def indicate_inset_zoom(self, inset_ax, **kwargs):
        """
        Add an inset indicator rectangle to the Axes based on the axis
        limits for an *inset_ax* and draw connectors between *inset_ax*
        and the rectangle.

        Warnings
        --------
        This method is experimental as of 3.0, and the API may change.

        Parameters
        ----------
        inset_ax : `.Axes`
            Inset Axes to draw connecting lines to.  Two lines are
            drawn connecting the indicator box to the inset Axes on corners
            chosen so as to not overlap with the indicator box.

        **kwargs
            Other keyword arguments are passed on to `.Axes.indicate_inset`

        Returns
        -------
        inset_indicator : `.inset.InsetIndicator`
            An artist which contains

            inset_indicator.rectangle : `.Rectangle`
                The indicator frame.

            inset_indicator.connectors : 4-tuple of `.patches.ConnectionPatch`
                The four connector lines connecting to (lower_left, upper_left,
                lower_right upper_right) corners of *inset_ax*. Two lines are
                set with visibility to *False*,  but the user can set the
                visibility to True if the automatic choice is not deemed correct.

            .. versionchanged:: 3.10
                Previously the rectangle and connectors tuple were returned.
        """

        return self.indicate_inset(None, inset_ax, **kwargs)

    @_docstring.interpd
    def secondary_xaxis(self, location, functions=None, *, transform=None, **kwargs):
        """
        Add a second x-axis to this `~.axes.Axes`.

        For example if we want to have a second scale for the data plotted on
        the xaxis.

        %(_secax_docstring)s

        Examples
        --------
        The main axis shows frequency, and the secondary axis shows period.

        .. plot::

            fig, ax = plt.subplots()
            ax.loglog(range(1, 360, 5), range(1, 360, 5))
            ax.set_xlabel('frequency [Hz]')

            def invert(x):
                # 1/x with special treatment of x == 0
                x = np.array(x).astype(float)
                near_zero = np.isclose(x, 0)
                x[near_zero] = np.inf
                x[~near_zero] = 1 / x[~near_zero]
                return x

            # the inverse of 1/x is itself
            secax = ax.secondary_xaxis('top', functions=(invert, invert))
            secax.set_xlabel('Period [s]')
            plt.show()

        To add a secondary axis relative to your data, you can pass a transform
        to the new axis.

        .. plot::

            fig, ax = plt.subplots()
            ax.plot(range(0, 5), range(-1, 4))

            # Pass 'ax.transData' as a transform to place the axis
            # relative to your data at y=0
            secax = ax.secondary_xaxis(0, transform=ax.transData)
        """
        if not (location in ['top', 'bottom'] or isinstance(location, Real)):
            raise ValueError('secondary_xaxis location must be either '
                             'a float or "top"/"bottom"')

        secondary_ax = SecondaryAxis(self, 'x', location, functions,
                                     transform, **kwargs)
        self.add_child_axes(secondary_ax)
        return secondary_ax

    @_docstring.interpd
    def secondary_yaxis(self, location, functions=None, *, transform=None, **kwargs):
        """
        Add a second y-axis to this `~.axes.Axes`.

        For example if we want to have a second scale for the data plotted on
        the yaxis.

        %(_secax_docstring)s

        Examples
        --------
        Add a secondary Axes that converts from radians to degrees

        .. plot::

            fig, ax = plt.subplots()
            ax.plot(range(1, 360, 5), range(1, 360, 5))
            ax.set_ylabel('degrees')
            secax = ax.secondary_yaxis('right', functions=(np.deg2rad,
                                                           np.rad2deg))
            secax.set_ylabel('radians')

        To add a secondary axis relative to your data, you can pass a transform
        to the new axis.

        .. plot::

            fig, ax = plt.subplots()
            ax.plot(range(0, 5), range(-1, 4))

            # Pass 'ax.transData' as a transform to place the axis
            # relative to your data at x=3
            secax = ax.secondary_yaxis(3, transform=ax.transData)
        """
        if not (location in ['left', 'right'] or isinstance(location, Real)):
            raise ValueError('secondary_yaxis location must be either '
                             'a float or "left"/"right"')

        secondary_ax = SecondaryAxis(self, 'y', location, functions,
                                     transform, **kwargs)
        self.add_child_axes(secondary_ax)
        return secondary_ax

    @_docstring.interpd
    def text(self, x, y, s, fontdict=None, **kwargs):
        """
        Add text to the Axes.

        Add the text *s* to the Axes at location *x*, *y* in data coordinates,
        with a default ``horizontalalignment`` on the ``left`` and
        ``verticalalignment`` at the ``baseline``. See
        :doc:`/gallery/text_labels_and_annotations/text_alignment`.

        Parameters
        ----------
        x, y : float
            The position to place the text. By default, this is in data
            coordinates. The coordinate system can be changed using the
            *transform* parameter.

        s : str
            The text.

        fontdict : dict, default: None

            .. admonition:: Discouraged

               The use of *fontdict* is discouraged. Parameters should be passed as
               individual keyword arguments or using dictionary-unpacking
               ``text(..., **fontdict)``.

            A dictionary to override the default text properties. If fontdict
            is None, the defaults are determined by `.rcParams`.

        Returns
        -------
        `.Text`
            The created `.Text` instance.

        Other Parameters
        ----------------
        **kwargs : `~matplotlib.text.Text` properties.
            Other miscellaneous text parameters.

            %(Text:kwdoc)s

        Examples
        --------
        Individual keyword arguments can be used to override any given
        parameter::

            >>> text(x, y, s, fontsize=12)

        The default transform specifies that text is in data coords,
        alternatively, you can specify text in axis coords ((0, 0) is
        lower-left and (1, 1) is upper-right).  The example below places
        text in the center of the Axes::

            >>> text(0.5, 0.5, 'matplotlib', horizontalalignment='center',
            ...      verticalalignment='center', transform=ax.transAxes)

        You can put a rectangular box around the text instance (e.g., to
        set a background color) by using the keyword *bbox*.  *bbox* is
        a dictionary of `~matplotlib.patches.Rectangle`
        properties.  For example::

            >>> text(x, y, s, bbox=dict(facecolor='red', alpha=0.5))
        """
        effective_kwargs = {
            'verticalalignment': 'baseline',
            'horizontalalignment': 'left',
            'transform': self.transData,
            'clip_on': False,
            **(fontdict if fontdict is not None else {}),
            **kwargs,
        }
        t = mtext.Text(x, y, text=s, **effective_kwargs)
        if t.get_clip_path() is None:
            t.set_clip_path(self.patch)
        self._add_text(t)
        return t

    @_docstring.interpd
    def annotate(self, text, xy, xytext=None, xycoords='data', textcoords=None,
                 arrowprops=None, annotation_clip=None, **kwargs):
        # Signature must match Annotation. This is verified in
        # test_annotate_signature().
        a = mtext.Annotation(text, xy, xytext=xytext, xycoords=xycoords,
                             textcoords=textcoords, arrowprops=arrowprops,
                             annotation_clip=annotation_clip, **kwargs)
        a.set_transform(mtransforms.IdentityTransform())
        if kwargs.get('clip_on', False) and a.get_clip_path() is None:
            a.set_clip_path(self.patch)
        self._add_text(a)
        return a
    annotate.__doc__ = mtext.Annotation.__init__.__doc__
    #### Lines and spans

    @_docstring.interpd
    def axhline(self, y=0, xmin=0, xmax=1, **kwargs):
        """
        Add a horizontal line spanning the whole or fraction of the Axes.

        Note: If you want to set x-limits in data coordinates, use
        `~.Axes.hlines` instead.

        Parameters
        ----------
        y : float, default: 0
            y position in :ref:`data coordinates <coordinate-systems>`.

        xmin : float, default: 0
            The start x-position in :ref:`axes coordinates <coordinate-systems>`.
            Should be between 0 and 1, 0 being the far left of the plot,
            1 the far right of the plot.

        xmax : float, default: 1
            The end x-position in :ref:`axes coordinates <coordinate-systems>`.
            Should be between 0 and 1, 0 being the far left of the plot,
            1 the far right of the plot.

        Returns
        -------
        `~matplotlib.lines.Line2D`
            A `.Line2D` specified via two points ``(xmin, y)``, ``(xmax, y)``.
            Its transform is set such that *x* is in
            :ref:`axes coordinates <coordinate-systems>` and *y* is in
            :ref:`data coordinates <coordinate-systems>`.

            This is still a generic line and the horizontal character is only
            realized through using identical *y* values for both points. Thus,
            if you want to change the *y* value later, you have to provide two
            values ``line.set_ydata([3, 3])``.

        Other Parameters
        ----------------
        **kwargs
            Valid keyword arguments are `.Line2D` properties, except for
            'transform':

            %(Line2D:kwdoc)s

        See Also
        --------
        hlines : Add horizontal lines in data coordinates.
        axhspan : Add a horizontal span (rectangle) across the axis.
        axline : Add a line with an arbitrary slope.

        Examples
        --------
        * draw a thick red hline at 'y' = 0 that spans the xrange::

            >>> axhline(linewidth=4, color='r')

        * draw a default hline at 'y' = 1 that spans the xrange::

            >>> axhline(y=1)

        * draw a default hline at 'y' = .5 that spans the middle half of
          the xrange::

            >>> axhline(y=.5, xmin=0.25, xmax=0.75)
        """
        self._check_no_units([xmin, xmax], ['xmin', 'xmax'])
        if "transform" in kwargs:
            raise ValueError("'transform' is not allowed as a keyword "
                             "argument; axhline generates its own transform.")
        ymin, ymax = self.get_ybound()

        # Strip away the units for comparison with non-unitized bounds.
        yy, = self._process_unit_info([("y", y)], kwargs)
        scaley = (yy < ymin) or (yy > ymax)

        trans = self.get_yaxis_transform(which='grid')
        l = mlines.Line2D([xmin, xmax], [y, y], transform=trans, **kwargs)
        self.add_line(l)
        l.get_path()._interpolation_steps = mpl.axis.GRIDLINE_INTERPOLATION_STEPS
        if scaley:
            self._request_autoscale_view("y")
        return l

    @_docstring.interpd
    def axvline(self, x=0, ymin=0, ymax=1, **kwargs):
        """
        Add a vertical line spanning the whole or fraction of the Axes.

        Note: If you want to set y-limits in data coordinates, use
        `~.Axes.vlines` instead.

        Parameters
        ----------
        x : float, default: 0
            x position in :ref:`data coordinates <coordinate-systems>`.

        ymin : float, default: 0
            The start y-position in :ref:`axes coordinates <coordinate-systems>`.
            Should be between 0 and 1, 0 being the bottom of the plot, 1 the
            top of the plot.

        ymax : float, default: 1
            The end y-position in :ref:`axes coordinates <coordinate-systems>`.
            Should be between 0 and 1, 0 being the bottom of the plot, 1 the
            top of the plot.

        Returns
        -------
        `~matplotlib.lines.Line2D`
            A `.Line2D` specified via two points ``(x, ymin)``, ``(x, ymax)``.
            Its transform is set such that *x* is in
            :ref:`data coordinates <coordinate-systems>` and *y* is in
            :ref:`axes coordinates <coordinate-systems>`.

            This is still a generic line and the vertical character is only
            realized through using identical *x* values for both points. Thus,
            if you want to change the *x* value later, you have to provide two
            values ``line.set_xdata([3, 3])``.

        Other Parameters
        ----------------
        **kwargs
            Valid keyword arguments are `.Line2D` properties, except for
            'transform':

            %(Line2D:kwdoc)s

        See Also
        --------
        vlines : Add vertical lines in data coordinates.
        axvspan : Add a vertical span (rectangle) across the axis.
        axline : Add a line with an arbitrary slope.

        Examples
        --------
        * draw a thick red vline at *x* = 0 that spans the yrange::

            >>> axvline(linewidth=4, color='r')

        * draw a default vline at *x* = 1 that spans the yrange::

            >>> axvline(x=1)

        * draw a default vline at *x* = .5 that spans the middle half of
          the yrange::

            >>> axvline(x=.5, ymin=0.25, ymax=0.75)
        """
        self._check_no_units([ymin, ymax], ['ymin', 'ymax'])
        if "transform" in kwargs:
            raise ValueError("'transform' is not allowed as a keyword "
                             "argument; axvline generates its own transform.")
        xmin, xmax = self.get_xbound()

        # Strip away the units for comparison with non-unitized bounds.
        xx, = self._process_unit_info([("x", x)], kwargs)
        scalex = (xx < xmin) or (xx > xmax)

        trans = self.get_xaxis_transform(which='grid')
        l = mlines.Line2D([x, x], [ymin, ymax], transform=trans, **kwargs)
        self.add_line(l)
        l.get_path()._interpolation_steps = mpl.axis.GRIDLINE_INTERPOLATION_STEPS
        if scalex:
            self._request_autoscale_view("x")
        return l

    @staticmethod
    def _check_no_units(vals, names):
        # Helper method to check that vals are not unitized
        for val, name in zip(vals, names):
            if not munits._is_natively_supported(val):
                raise ValueError(f"{name} must be a single scalar value, "
                                 f"but got {val}")

    @_docstring.interpd
    def axline(self, xy1, xy2=None, *, slope=None, **kwargs):
        """
        Add an infinitely long straight line.

        The line can be defined either by two points *xy1* and *xy2*, or
        by one point *xy1* and a *slope*.

        This draws a straight line "on the screen", regardless of the x and y
        scales, and is thus also suitable for drawing exponential decays in
        semilog plots, power laws in loglog plots, etc. However, *slope*
        should only be used with linear scales; It has no clear meaning for
        all other scales, and thus the behavior is undefined. Please specify
        the line using the points *xy1*, *xy2* for non-linear scales.

        The *transform* keyword argument only applies to the points *xy1*,
        *xy2*. The *slope* (if given) is always in data coordinates. This can
        be used e.g. with ``ax.transAxes`` for drawing grid lines with a fixed
        slope.

        Parameters
        ----------
        xy1, xy2 : (float, float)
            Points for the line to pass through.
            Either *xy2* or *slope* has to be given.
        slope : float, optional
            The slope of the line. Either *xy2* or *slope* has to be given.

        Returns
        -------
        `.AxLine`

        Other Parameters
        ----------------
        **kwargs
            Valid kwargs are `.Line2D` properties

            %(Line2D:kwdoc)s

        See Also
        --------
        axhline : for horizontal lines
        axvline : for vertical lines

        Examples
        --------
        Draw a thick red line passing through (0, 0) and (1, 1)::

            >>> axline((0, 0), (1, 1), linewidth=4, color='r')
        """
        if slope is not None and (self.get_xscale() != 'linear' or
                                  self.get_yscale() != 'linear'):
            raise TypeError("'slope' cannot be used with non-linear scales")

        datalim = [xy1] if xy2 is None else [xy1, xy2]
        if "transform" in kwargs:
            # if a transform is passed (i.e. line points not in data space),
            # data limits should not be adjusted.
            datalim = []

        line = mlines.AxLine(xy1, xy2, slope, **kwargs)
        # Like add_line, but correctly handling data limits.
        self._set_artist_props(line)
        if line.get_clip_path() is None:
            line.set_clip_path(self.patch)
        if not line.get_label():
            line.set_label(f"_child{len(self._children)}")
        self._children.append(line)
        line._remove_method = self._children.remove
        self.update_datalim(datalim)

        self._request_autoscale_view()
        return line

    @_docstring.interpd
    def axhspan(self, ymin, ymax, xmin=0, xmax=1, **kwargs):
        """
        Add a horizontal span (rectangle) across the Axes.

        The rectangle spans from *ymin* to *ymax* vertically, and, by default,
        the whole x-axis horizontally.  The x-span can be set using *xmin*
        (default: 0) and *xmax* (default: 1) which are in axis units; e.g.
        ``xmin = 0.5`` always refers to the middle of the x-axis regardless of
        the limits set by `~.Axes.set_xlim`.

        Parameters
        ----------
        ymin : float
            Lower y-coordinate of the span, in data units.
        ymax : float
            Upper y-coordinate of the span, in data units.
        xmin : float, default: 0
            Lower x-coordinate of the span, in x-axis (0-1) units.
        xmax : float, default: 1
            Upper x-coordinate of the span, in x-axis (0-1) units.

        Returns
        -------
        `~matplotlib.patches.Rectangle`
            Horizontal span (rectangle) from (xmin, ymin) to (xmax, ymax).

        Other Parameters
        ----------------
        **kwargs : `~matplotlib.patches.Rectangle` properties

        %(Rectangle:kwdoc)s

        See Also
        --------
        axvspan : Add a vertical span across the Axes.
        """
        # Strip units away.
        self._check_no_units([xmin, xmax], ['xmin', 'xmax'])
        (ymin, ymax), = self._process_unit_info([("y", [ymin, ymax])], kwargs)

        p = mpatches.Rectangle((xmin, ymin), xmax - xmin, ymax - ymin, **kwargs)
        p.set_transform(self.get_yaxis_transform(which="grid"))
        # For Rectangles and non-separable transforms, add_patch can be buggy
        # and update the x limits even though it shouldn't do so for an
        # yaxis_transformed patch, so undo that update.
        ix = self.dataLim.intervalx.copy()
        mx = self.dataLim.minposx
        self.add_patch(p)
        self.dataLim.intervalx = ix
        self.dataLim.minposx = mx
        p.get_path()._interpolation_steps = mpl.axis.GRIDLINE_INTERPOLATION_STEPS
        self._request_autoscale_view("y")
        return p

    @_docstring.interpd
    def axvspan(self, xmin, xmax, ymin=0, ymax=1, **kwargs):
        """
        Add a vertical span (rectangle) across the Axes.

        The rectangle spans from *xmin* to *xmax* horizontally, and, by
        default, the whole y-axis vertically.  The y-span can be set using
        *ymin* (default: 0) and *ymax* (default: 1) which are in axis units;
        e.g. ``ymin = 0.5`` always refers to the middle of the y-axis
        regardless of the limits set by `~.Axes.set_ylim`.

        Parameters
        ----------
        xmin : float
            Lower x-coordinate of the span, in data units.
        xmax : float
            Upper x-coordinate of the span, in data units.
        ymin : float, default: 0
            Lower y-coordinate of the span, in y-axis units (0-1).
        ymax : float, default: 1
            Upper y-coordinate of the span, in y-axis units (0-1).

        Returns
        -------
        `~matplotlib.patches.Rectangle`
            Vertical span (rectangle) from (xmin, ymin) to (xmax, ymax).

        Other Parameters
        ----------------
        **kwargs : `~matplotlib.patches.Rectangle` properties

        %(Rectangle:kwdoc)s

        See Also
        --------
        axhspan : Add a horizontal span across the Axes.

        Examples
        --------
        Draw a vertical, green, translucent rectangle from x = 1.25 to
        x = 1.55 that spans the yrange of the Axes.

        >>> axvspan(1.25, 1.55, facecolor='g', alpha=0.5)

        """
        # Strip units away.
        self._check_no_units([ymin, ymax], ['ymin', 'ymax'])
        (xmin, xmax), = self._process_unit_info([("x", [xmin, xmax])], kwargs)

        p = mpatches.Rectangle((xmin, ymin), xmax - xmin, ymax - ymin, **kwargs)
        p.set_transform(self.get_xaxis_transform(which="grid"))
        # For Rectangles and non-separable transforms, add_patch can be buggy
        # and update the y limits even though it shouldn't do so for an
        # xaxis_transformed patch, so undo that update.
        iy = self.dataLim.intervaly.copy()
        my = self.dataLim.minposy
        self.add_patch(p)
        self.dataLim.intervaly = iy
        self.dataLim.minposy = my
        p.get_path()._interpolation_steps = mpl.axis.GRIDLINE_INTERPOLATION_STEPS
        self._request_autoscale_view("x")
        return p

    @_api.make_keyword_only("3.10", "label")
    @_preprocess_data(replace_names=["y", "xmin", "xmax", "colors"],
                      label_namer="y")
    def hlines(self, y, xmin, xmax, colors=None, linestyles='solid',
               label='', **kwargs):
        """
        Plot horizontal lines at each *y* from *xmin* to *xmax*.

        Parameters
        ----------
        y : float or array-like
            y-indexes where to plot the lines.

        xmin, xmax : float or array-like
            Respective beginning and end of each line. If scalars are
            provided, all lines will have the same length.

        colors : :mpltype:`color` or list of color , default: :rc:`lines.color`

        linestyles : {'solid', 'dashed', 'dashdot', 'dotted'}, default: 'solid'

        label : str, default: ''

        Returns
        -------
        `~matplotlib.collections.LineCollection`

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER
        **kwargs :  `~matplotlib.collections.LineCollection` properties.

        See Also
        --------
        vlines : vertical lines
        axhline : horizontal line across the Axes
        """

        # We do the conversion first since not all unitized data is uniform
        xmin, xmax, y = self._process_unit_info(
            [("x", xmin), ("x", xmax), ("y", y)], kwargs)

        if not np.iterable(y):
            y = [y]
        if not np.iterable(xmin):
            xmin = [xmin]
        if not np.iterable(xmax):
            xmax = [xmax]

        # Create and combine masked_arrays from input
        y, xmin, xmax = cbook._combine_masks(y, xmin, xmax)
        y = np.ravel(y)
        xmin = np.ravel(xmin)
        xmax = np.ravel(xmax)

        masked_verts = np.ma.empty((len(y), 2, 2))
        masked_verts[:, 0, 0] = xmin
        masked_verts[:, 0, 1] = y
        masked_verts[:, 1, 0] = xmax
        masked_verts[:, 1, 1] = y

        lines = mcoll.LineCollection(masked_verts, colors=colors,
                                     linestyles=linestyles, label=label)
        self.add_collection(lines, autolim=False)
        lines._internal_update(kwargs)

        if len(y) > 0:
            # Extreme values of xmin/xmax/y.  Using masked_verts here handles
            # the case of y being a masked *object* array (as can be generated
            # e.g. by errorbar()), which would make nanmin/nanmax stumble.
            updatex = True
            updatey = True
            if self.name == "rectilinear":
                datalim = lines.get_datalim(self.transData)
                t = lines.get_transform()
                updatex, updatey = t.contains_branch_seperately(self.transData)
                minx = np.nanmin(datalim.xmin)
                maxx = np.nanmax(datalim.xmax)
                miny = np.nanmin(datalim.ymin)
                maxy = np.nanmax(datalim.ymax)
            else:
                minx = np.nanmin(masked_verts[..., 0])
                maxx = np.nanmax(masked_verts[..., 0])
                miny = np.nanmin(masked_verts[..., 1])
                maxy = np.nanmax(masked_verts[..., 1])

            corners = (minx, miny), (maxx, maxy)
            self.update_datalim(corners, updatex, updatey)
            self._request_autoscale_view()
        return lines

    @_api.make_keyword_only("3.10", "label")
    @_preprocess_data(replace_names=["x", "ymin", "ymax", "colors"],
                      label_namer="x")
    def vlines(self, x, ymin, ymax, colors=None, linestyles='solid',
               label='', **kwargs):
        """
        Plot vertical lines at each *x* from *ymin* to *ymax*.

        Parameters
        ----------
        x : float or array-like
            x-indexes where to plot the lines.

        ymin, ymax : float or array-like
            Respective beginning and end of each line. If scalars are
            provided, all lines will have the same length.

        colors : :mpltype:`color` or list of color, default: :rc:`lines.color`

        linestyles : {'solid', 'dashed', 'dashdot', 'dotted'}, default: 'solid'

        label : str, default: ''

        Returns
        -------
        `~matplotlib.collections.LineCollection`

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER
        **kwargs : `~matplotlib.collections.LineCollection` properties.

        See Also
        --------
        hlines : horizontal lines
        axvline : vertical line across the Axes
        """

        # We do the conversion first since not all unitized data is uniform
        x, ymin, ymax = self._process_unit_info(
            [("x", x), ("y", ymin), ("y", ymax)], kwargs)

        if not np.iterable(x):
            x = [x]
        if not np.iterable(ymin):
            ymin = [ymin]
        if not np.iterable(ymax):
            ymax = [ymax]

        # Create and combine masked_arrays from input
        x, ymin, ymax = cbook._combine_masks(x, ymin, ymax)
        x = np.ravel(x)
        ymin = np.ravel(ymin)
        ymax = np.ravel(ymax)

        masked_verts = np.ma.empty((len(x), 2, 2))
        masked_verts[:, 0, 0] = x
        masked_verts[:, 0, 1] = ymin
        masked_verts[:, 1, 0] = x
        masked_verts[:, 1, 1] = ymax

        lines = mcoll.LineCollection(masked_verts, colors=colors,
                                     linestyles=linestyles, label=label)
        self.add_collection(lines, autolim=False)
        lines._internal_update(kwargs)

        if len(x) > 0:
            # Extreme values of x/ymin/ymax.  Using masked_verts here handles
            # the case of x being a masked *object* array (as can be generated
            # e.g. by errorbar()), which would make nanmin/nanmax stumble.
            updatex = True
            updatey = True
            if self.name == "rectilinear":
                datalim = lines.get_datalim(self.transData)
                t = lines.get_transform()
                updatex, updatey = t.contains_branch_seperately(self.transData)
                minx = np.nanmin(datalim.xmin)
                maxx = np.nanmax(datalim.xmax)
                miny = np.nanmin(datalim.ymin)
                maxy = np.nanmax(datalim.ymax)
            else:
                minx = np.nanmin(masked_verts[..., 0])
                maxx = np.nanmax(masked_verts[..., 0])
                miny = np.nanmin(masked_verts[..., 1])
                maxy = np.nanmax(masked_verts[..., 1])

            corners = (minx, miny), (maxx, maxy)
            self.update_datalim(corners, updatex, updatey)
            self._request_autoscale_view()
        return lines

    @_api.make_keyword_only("3.10", "orientation")
    @_preprocess_data(replace_names=["positions", "lineoffsets",
                                     "linelengths", "linewidths",
                                     "colors", "linestyles"])
    @_docstring.interpd
    def eventplot(self, positions, orientation='horizontal', lineoffsets=1,
                  linelengths=1, linewidths=None, colors=None, alpha=None,
                  linestyles='solid', **kwargs):
        """
        Plot identical parallel lines at the given positions.

        This type of plot is commonly used in neuroscience for representing
        neural events, where it is usually called a spike raster, dot raster,
        or raster plot.

        However, it is useful in any situation where you wish to show the
        timing or position of multiple sets of discrete events, such as the
        arrival times of people to a business on each day of the month or the
        date of hurricanes each year of the last century.

        Parameters
        ----------
        positions : array-like or list of array-like
            A 1D array-like defines the positions of one sequence of events.

            Multiple groups of events may be passed as a list of array-likes.
            Each group can be styled independently by passing lists of values
            to *lineoffsets*, *linelengths*, *linewidths*, *colors* and
            *linestyles*.

            Note that *positions* can be a 2D array, but in practice different
            event groups usually have different counts so that one will use a
            list of different-length arrays rather than a 2D array.

        orientation : {'horizontal', 'vertical'}, default: 'horizontal'
            The direction of the event sequence:

            - 'horizontal': the events are arranged horizontally.
              The indicator lines are vertical.
            - 'vertical': the events are arranged vertically.
              The indicator lines are horizontal.

        lineoffsets : float or array-like, default: 1
            The offset of the center of the lines from the origin, in the
            direction orthogonal to *orientation*.

            If *positions* is 2D, this can be a sequence with length matching
            the length of *positions*.

        linelengths : float or array-like, default: 1
            The total height of the lines (i.e. the lines stretches from
            ``lineoffset - linelength/2`` to ``lineoffset + linelength/2``).

            If *positions* is 2D, this can be a sequence with length matching
            the length of *positions*.

        linewidths : float or array-like, default: :rc:`lines.linewidth`
            The line width(s) of the event lines, in points.

            If *positions* is 2D, this can be a sequence with length matching
            the length of *positions*.

        colors : :mpltype:`color` or list of color, default: :rc:`lines.color`
            The color(s) of the event lines.

            If *positions* is 2D, this can be a sequence with length matching
            the length of *positions*.

        alpha : float or array-like, default: 1
            The alpha blending value(s), between 0 (transparent) and 1
            (opaque).

            If *positions* is 2D, this can be a sequence with length matching
            the length of *positions*.

        linestyles : str or tuple or list of such values, default: 'solid'
            Default is 'solid'. Valid strings are ['solid', 'dashed',
            'dashdot', 'dotted', '-', '--', '-.', ':']. Dash tuples
            should be of the form::

                (offset, onoffseq),

            where *onoffseq* is an even length tuple of on and off ink
            in points.

            If *positions* is 2D, this can be a sequence with length matching
            the length of *positions*.

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Other keyword arguments are line collection properties.  See
            `.LineCollection` for a list of the valid properties.

        Returns
        -------
        list of `.EventCollection`
            The `.EventCollection` that were added.

        Notes
        -----
        For *linelengths*, *linewidths*, *colors*, *alpha* and *linestyles*, if
        only a single value is given, that value is applied to all lines. If an
        array-like is given, it must have the same length as *positions*, and
        each value will be applied to the corresponding row of the array.

        Examples
        --------
        .. plot:: gallery/lines_bars_and_markers/eventplot_demo.py
        """

        lineoffsets, linelengths = self._process_unit_info(
                [("y", lineoffsets), ("y", linelengths)], kwargs)

        # fix positions, noting that it can be a list of lists:
        if not np.iterable(positions):
            positions = [positions]
        elif any(np.iterable(position) for position in positions):
            positions = [np.asanyarray(position) for position in positions]
        else:
            positions = [np.asanyarray(positions)]

        poss = []
        for position in positions:
            poss += self._process_unit_info([("x", position)], kwargs)
        positions = poss

        # prevent 'singular' keys from **kwargs dict from overriding the effect
        # of 'plural' keyword arguments (e.g. 'color' overriding 'colors')
        colors = cbook._local_over_kwdict(colors, kwargs, 'color')
        linewidths = cbook._local_over_kwdict(linewidths, kwargs, 'linewidth')
        linestyles = cbook._local_over_kwdict(linestyles, kwargs, 'linestyle')

        if not np.iterable(lineoffsets):
            lineoffsets = [lineoffsets]
        if not np.iterable(linelengths):
            linelengths = [linelengths]
        if not np.iterable(linewidths):
            linewidths = [linewidths]
        if not np.iterable(colors):
            colors = [colors]
        if not np.iterable(alpha):
            alpha = [alpha]
        if hasattr(linestyles, 'lower') or not np.iterable(linestyles):
            linestyles = [linestyles]

        lineoffsets = np.asarray(lineoffsets)
        linelengths = np.asarray(linelengths)
        linewidths = np.asarray(linewidths)

        if len(lineoffsets) == 0:
            raise ValueError('lineoffsets cannot be empty')
        if len(linelengths) == 0:
            raise ValueError('linelengths cannot be empty')
        if len(linestyles) == 0:
            raise ValueError('linestyles cannot be empty')
        if len(linewidths) == 0:
            raise ValueError('linewidths cannot be empty')
        if len(alpha) == 0:
            raise ValueError('alpha cannot be empty')
        if len(colors) == 0:
            colors = [None]
        try:
            # Early conversion of the colors into RGBA values to take care
            # of cases like colors='0.5' or colors='C1'.  (Issue #8193)
            colors = mcolors.to_rgba_array(colors)
        except ValueError:
            # Will fail if any element of *colors* is None. But as long
            # as len(colors) == 1 or len(positions), the rest of the
            # code should process *colors* properly.
            pass

        if len(lineoffsets) == 1 and len(positions) != 1:
            lineoffsets = np.tile(lineoffsets, len(positions))
            lineoffsets[0] = 0
            lineoffsets = np.cumsum(lineoffsets)
        if len(linelengths) == 1:
            linelengths = np.tile(linelengths, len(positions))
        if len(linewidths) == 1:
            linewidths = np.tile(linewidths, len(positions))
        if len(colors) == 1:
            colors = list(colors) * len(positions)
        if len(alpha) == 1:
            alpha = list(alpha) * len(positions)
        if len(linestyles) == 1:
            linestyles = [linestyles] * len(positions)

        if len(lineoffsets) != len(positions):
            raise ValueError('lineoffsets and positions are unequal sized '
                             'sequences')
        if len(linelengths) != len(positions):
            raise ValueError('linelengths and positions are unequal sized '
                             'sequences')
        if len(linewidths) != len(positions):
            raise ValueError('linewidths and positions are unequal sized '
                             'sequences')
        if len(colors) != len(positions):
            raise ValueError('colors and positions are unequal sized '
                             'sequences')
        if len(alpha) != len(positions):
            raise ValueError('alpha and positions are unequal sized '
                             'sequences')
        if len(linestyles) != len(positions):
            raise ValueError('linestyles and positions are unequal sized '
                             'sequences')

        colls = []
        for position, lineoffset, linelength, linewidth, color, alpha_, \
            linestyle in \
                zip(positions, lineoffsets, linelengths, linewidths,
                    colors, alpha, linestyles):
            coll = mcoll.EventCollection(position,
                                         orientation=orientation,
                                         lineoffset=lineoffset,
                                         linelength=linelength,
                                         linewidth=linewidth,
                                         color=color,
                                         alpha=alpha_,
                                         linestyle=linestyle)
            self.add_collection(coll, autolim=False)
            coll._internal_update(kwargs)
            colls.append(coll)

        if len(positions) > 0:
            # try to get min/max
            min_max = [(np.min(_p), np.max(_p)) for _p in positions
                       if len(_p) > 0]
            # if we have any non-empty positions, try to autoscale
            if len(min_max) > 0:
                mins, maxes = zip(*min_max)
                minpos = np.min(mins)
                maxpos = np.max(maxes)

                minline = (lineoffsets - linelengths).min()
                maxline = (lineoffsets + linelengths).max()

                if orientation == "vertical":
                    corners = (minline, minpos), (maxline, maxpos)
                else:  # "horizontal"
                    corners = (minpos, minline), (maxpos, maxline)
                self.update_datalim(corners)
                self._request_autoscale_view()

        return colls

    #### Basic plotting

    # Uses a custom implementation of data-kwarg handling in
    # _process_plot_var_args.
    @_docstring.interpd
    def plot(self, *args, scalex=True, scaley=True, data=None, **kwargs):
        """
        Plot y versus x as lines and/or markers.

        Call signatures::

            plot([x], y, [fmt], *, data=None, **kwargs)
            plot([x], y, [fmt], [x2], y2, [fmt2], ..., **kwargs)

        The coordinates of the points or line nodes are given by *x*, *y*.

        The optional parameter *fmt* is a convenient way for defining basic
        formatting like color, marker and linestyle. It's a shortcut string
        notation described in the *Notes* section below.

        >>> plot(x, y)        # plot x and y using default line style and color
        >>> plot(x, y, 'bo')  # plot x and y using blue circle markers
        >>> plot(y)           # plot y using x as index array 0..N-1
        >>> plot(y, 'r+')     # ditto, but with red plusses

        You can use `.Line2D` properties as keyword arguments for more
        control on the appearance. Line properties and *fmt* can be mixed.
        The following two calls yield identical results:

        >>> plot(x, y, 'go--', linewidth=2, markersize=12)
        >>> plot(x, y, color='green', marker='o', linestyle='dashed',
        ...      linewidth=2, markersize=12)

        When conflicting with *fmt*, keyword arguments take precedence.


        **Plotting labelled data**

        There's a convenient way for plotting objects with labelled data (i.e.
        data that can be accessed by index ``obj['y']``). Instead of giving
        the data in *x* and *y*, you can provide the object in the *data*
        parameter and just give the labels for *x* and *y*::

        >>> plot('xlabel', 'ylabel', data=obj)

        All indexable objects are supported. This could e.g. be a `dict`, a
        `pandas.DataFrame` or a structured numpy array.


        **Plotting multiple sets of data**

        There are various ways to plot multiple sets of data.

        - The most straight forward way is just to call `plot` multiple times.
          Example:

          >>> plot(x1, y1, 'bo')
          >>> plot(x2, y2, 'go')

        - If *x* and/or *y* are 2D arrays, a separate data set will be drawn
          for every column. If both *x* and *y* are 2D, they must have the
          same shape. If only one of them is 2D with shape (N, m) the other
          must have length N and will be used for every data set m.

          Example:

          >>> x = [1, 2, 3]
          >>> y = np.array([[1, 2], [3, 4], [5, 6]])
          >>> plot(x, y)

          is equivalent to:

          >>> for col in range(y.shape[1]):
          ...     plot(x, y[:, col])

        - The third way is to specify multiple sets of *[x]*, *y*, *[fmt]*
          groups::

          >>> plot(x1, y1, 'g^', x2, y2, 'g-')

          In this case, any additional keyword argument applies to all
          datasets. Also, this syntax cannot be combined with the *data*
          parameter.

        By default, each line is assigned a different style specified by a
        'style cycle'. The *fmt* and line property parameters are only
        necessary if you want explicit deviations from these defaults.
        Alternatively, you can also change the style cycle using
        :rc:`axes.prop_cycle`.


        Parameters
        ----------
        x, y : array-like or float
            The horizontal / vertical coordinates of the data points.
            *x* values are optional and default to ``range(len(y))``.

            Commonly, these parameters are 1D arrays.

            They can also be scalars, or two-dimensional (in that case, the
            columns represent separate data sets).

            These arguments cannot be passed as keywords.

        fmt : str, optional
            A format string, e.g. 'ro' for red circles. See the *Notes*
            section for a full description of the format strings.

            Format strings are just an abbreviation for quickly setting
            basic line properties. All of these and more can also be
            controlled by keyword arguments.

            This argument cannot be passed as keyword.

        data : indexable object, optional
            An object with labelled data. If given, provide the label names to
            plot in *x* and *y*.

            .. note::
                Technically there's a slight ambiguity in calls where the
                second label is a valid *fmt*. ``plot('n', 'o', data=obj)``
                could be ``plt(x, y)`` or ``plt(y, fmt)``. In such cases,
                the former interpretation is chosen, but a warning is issued.
                You may suppress the warning by adding an empty format string
                ``plot('n', 'o', '', data=obj)``.

        Returns
        -------
        list of `.Line2D`
            A list of lines representing the plotted data.

        Other Parameters
        ----------------
        scalex, scaley : bool, default: True
            These parameters determine if the view limits are adapted to the
            data limits. The values are passed on to
            `~.axes.Axes.autoscale_view`.

        **kwargs : `~matplotlib.lines.Line2D` properties, optional
            *kwargs* are used to specify properties like a line label (for
            auto legends), linewidth, antialiasing, marker face color.
            Example::

            >>> plot([1, 2, 3], [1, 2, 3], 'go-', label='line 1', linewidth=2)
            >>> plot([1, 2, 3], [1, 4, 9], 'rs', label='line 2')

            If you specify multiple lines with one plot call, the kwargs apply
            to all those lines. In case the label object is iterable, each
            element is used as labels for each set of data.

            Here is a list of available `.Line2D` properties:

            %(Line2D:kwdoc)s

        See Also
        --------
        scatter : XY scatter plot with markers of varying size and/or color (
            sometimes also called bubble chart).

        Notes
        -----
        **Format Strings**

        A format string consists of a part for color, marker and line::

            fmt = '[marker][line][color]'

        Each of them is optional. If not provided, the value from the style
        cycle is used. Exception: If ``line`` is given, but no ``marker``,
        the data will be a line without markers.

        Other combinations such as ``[color][marker][line]`` are also
        supported, but note that their parsing may be ambiguous.

        **Markers**

        =============   ===============================
        character       description
        =============   ===============================
        ``'.'``         point marker
        ``','``         pixel marker
        ``'o'``         circle marker
        ``'v'``         triangle_down marker
        ``'^'``         triangle_up marker
        ``'<'``         triangle_left marker
        ``'>'``         triangle_right marker
        ``'1'``         tri_down marker
        ``'2'``         tri_up marker
        ``'3'``         tri_left marker
        ``'4'``         tri_right marker
        ``'8'``         octagon marker
        ``'s'``         square marker
        ``'p'``         pentagon marker
        ``'P'``         plus (filled) marker
        ``'*'``         star marker
        ``'h'``         hexagon1 marker
        ``'H'``         hexagon2 marker
        ``'+'``         plus marker
        ``'x'``         x marker
        ``'X'``         x (filled) marker
        ``'D'``         diamond marker
        ``'d'``         thin_diamond marker
        ``'|'``         vline marker
        ``'_'``         hline marker
        =============   ===============================

        **Line Styles**

        =============    ===============================
        character        description
        =============    ===============================
        ``'-'``          solid line style
        ``'--'``         dashed line style
        ``'-.'``         dash-dot line style
        ``':'``          dotted line style
        =============    ===============================

        Example format strings::

            'b'    # blue markers with default shape
            'or'   # red circles
            '-g'   # green solid line
            '--'   # dashed line with default color
            '^k:'  # black triangle_up markers connected by a dotted line

        **Colors**

        The supported color abbreviations are the single letter codes

        =============    ===============================
        character        color
        =============    ===============================
        ``'b'``          blue
        ``'g'``          green
        ``'r'``          red
        ``'c'``          cyan
        ``'m'``          magenta
        ``'y'``          yellow
        ``'k'``          black
        ``'w'``          white
        =============    ===============================

        and the ``'CN'`` colors that index into the default property cycle.

        If the color is the only part of the format string, you can
        additionally use any  `matplotlib.colors` spec, e.g. full names
        (``'green'``) or hex strings (``'#008000'``).
        """
        kwargs = cbook.normalize_kwargs(kwargs, mlines.Line2D)
        lines = [*self._get_lines(self, *args, data=data, **kwargs)]
        for line in lines:
            self.add_line(line)
        if scalex:
            self._request_autoscale_view("x")
        if scaley:
            self._request_autoscale_view("y")
        return lines

    @_api.deprecated("3.9", alternative="plot")
    @_preprocess_data(replace_names=["x", "y"], label_namer="y")
    @_docstring.interpd
    def plot_date(self, x, y, fmt='o', tz=None, xdate=True, ydate=False,
                  **kwargs):
        """
        Plot coercing the axis to treat floats as dates.

        .. deprecated:: 3.9

            This method exists for historic reasons and will be removed in version 3.11.

            - ``datetime``-like data should directly be plotted using
              `~.Axes.plot`.
            -  If you need to plot plain numeric data as :ref:`date-format` or
               need to set a timezone, call ``ax.xaxis.axis_date`` /
               ``ax.yaxis.axis_date`` before `~.Axes.plot`. See
               `.Axis.axis_date`.

        Similar to `.plot`, this plots *y* vs. *x* as lines or markers.
        However, the axis labels are formatted as dates depending on *xdate*
        and *ydate*.  Note that `.plot` will work with `datetime` and
        `numpy.datetime64` objects without resorting to this method.

        Parameters
        ----------
        x, y : array-like
            The coordinates of the data points. If *xdate* or *ydate* is
            *True*, the respective values *x* or *y* are interpreted as
            :ref:`Matplotlib dates <date-format>`.

        fmt : str, optional
            The plot format string. For details, see the corresponding
            parameter in `.plot`.

        tz : timezone string or `datetime.tzinfo`, default: :rc:`timezone`
            The time zone to use in labeling dates.

        xdate : bool, default: True
            If *True*, the *x*-axis will be interpreted as Matplotlib dates.

        ydate : bool, default: False
            If *True*, the *y*-axis will be interpreted as Matplotlib dates.

        Returns
        -------
        list of `.Line2D`
            Objects representing the plotted data.

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER
        **kwargs
            Keyword arguments control the `.Line2D` properties:

            %(Line2D:kwdoc)s

        See Also
        --------
        matplotlib.dates : Helper functions on dates.
        matplotlib.dates.date2num : Convert dates to num.
        matplotlib.dates.num2date : Convert num to dates.
        matplotlib.dates.drange : Create an equally spaced sequence of dates.

        Notes
        -----
        If you are using custom date tickers and formatters, it may be
        necessary to set the formatters/locators after the call to
        `.plot_date`. `.plot_date` will set the default tick locator to
        `.AutoDateLocator` (if the tick locator is not already set to a
        `.DateLocator` instance) and the default tick formatter to
        `.AutoDateFormatter` (if the tick formatter is not already set to a
        `.DateFormatter` instance).
        """
        if xdate:
            self.xaxis_date(tz)
        if ydate:
            self.yaxis_date(tz)
        return self.plot(x, y, fmt, **kwargs)

    # @_preprocess_data() # let 'plot' do the unpacking..
    @_docstring.interpd
    def loglog(self, *args, **kwargs):
        """
        Make a plot with log scaling on both the x- and y-axis.

        Call signatures::

            loglog([x], y, [fmt], data=None, **kwargs)
            loglog([x], y, [fmt], [x2], y2, [fmt2], ..., **kwargs)

        This is just a thin wrapper around `.plot` which additionally changes
        both the x-axis and the y-axis to log scaling. All the concepts and
        parameters of plot can be used here as well.

        The additional parameters *base*, *subs* and *nonpositive* control the
        x/y-axis properties. They are just forwarded to `.Axes.set_xscale` and
        `.Axes.set_yscale`. To use different properties on the x-axis and the
        y-axis, use e.g.
        ``ax.set_xscale("log", base=10); ax.set_yscale("log", base=2)``.

        Parameters
        ----------
        base : float, default: 10
            Base of the logarithm.

        subs : sequence, optional
            The location of the minor ticks. If *None*, reasonable locations
            are automatically chosen depending on the number of decades in the
            plot. See `.Axes.set_xscale`/`.Axes.set_yscale` for details.

        nonpositive : {'mask', 'clip'}, default: 'clip'
            Non-positive values can be masked as invalid, or clipped to a very
            small positive number.

        **kwargs
            All parameters supported by `.plot`.

        Returns
        -------
        list of `.Line2D`
            Objects representing the plotted data.
        """
        dx = {k: v for k, v in kwargs.items()
              if k in ['base', 'subs', 'nonpositive',
                       'basex', 'subsx', 'nonposx']}
        self.set_xscale('log', **dx)
        dy = {k: v for k, v in kwargs.items()
              if k in ['base', 'subs', 'nonpositive',
                       'basey', 'subsy', 'nonposy']}
        self.set_yscale('log', **dy)
        return self.plot(
            *args, **{k: v for k, v in kwargs.items() if k not in {*dx, *dy}})

    # @_preprocess_data() # let 'plot' do the unpacking..
    @_docstring.interpd
    def semilogx(self, *args, **kwargs):
        """
        Make a plot with log scaling on the x-axis.

        Call signatures::

            semilogx([x], y, [fmt], data=None, **kwargs)
            semilogx([x], y, [fmt], [x2], y2, [fmt2], ..., **kwargs)

        This is just a thin wrapper around `.plot` which additionally changes
        the x-axis to log scaling. All the concepts and parameters of plot can
        be used here as well.

        The additional parameters *base*, *subs*, and *nonpositive* control the
        x-axis properties. They are just forwarded to `.Axes.set_xscale`.

        Parameters
        ----------
        base : float, default: 10
            Base of the x logarithm.

        subs : array-like, optional
            The location of the minor xticks. If *None*, reasonable locations
            are automatically chosen depending on the number of decades in the
            plot. See `.Axes.set_xscale` for details.

        nonpositive : {'mask', 'clip'}, default: 'clip'
            Non-positive values in x can be masked as invalid, or clipped to a
            very small positive number.

        **kwargs
            All parameters supported by `.plot`.

        Returns
        -------
        list of `.Line2D`
            Objects representing the plotted data.
        """
        d = {k: v for k, v in kwargs.items()
             if k in ['base', 'subs', 'nonpositive',
                      'basex', 'subsx', 'nonposx']}
        self.set_xscale('log', **d)
        return self.plot(
            *args, **{k: v for k, v in kwargs.items() if k not in d})

    # @_preprocess_data() # let 'plot' do the unpacking..
    @_docstring.interpd
    def semilogy(self, *args, **kwargs):
        """
        Make a plot with log scaling on the y-axis.

        Call signatures::

            semilogy([x], y, [fmt], data=None, **kwargs)
            semilogy([x], y, [fmt], [x2], y2, [fmt2], ..., **kwargs)

        This is just a thin wrapper around `.plot` which additionally changes
        the y-axis to log scaling. All the concepts and parameters of plot can
        be used here as well.

        The additional parameters *base*, *subs*, and *nonpositive* control the
        y-axis properties. They are just forwarded to `.Axes.set_yscale`.

        Parameters
        ----------
        base : float, default: 10
            Base of the y logarithm.

        subs : array-like, optional
            The location of the minor yticks. If *None*, reasonable locations
            are automatically chosen depending on the number of decades in the
            plot. See `.Axes.set_yscale` for details.

        nonpositive : {'mask', 'clip'}, default: 'clip'
            Non-positive values in y can be masked as invalid, or clipped to a
            very small positive number.

        **kwargs
            All parameters supported by `.plot`.

        Returns
        -------
        list of `.Line2D`
            Objects representing the plotted data.
        """
        d = {k: v for k, v in kwargs.items()
             if k in ['base', 'subs', 'nonpositive',
                      'basey', 'subsy', 'nonposy']}
        self.set_yscale('log', **d)
        return self.plot(
            *args, **{k: v for k, v in kwargs.items() if k not in d})

    @_preprocess_data(replace_names=["x"], label_namer="x")
    def acorr(self, x, **kwargs):
        """
        Plot the autocorrelation of *x*.

        Parameters
        ----------
        x : array-like
            Not run through Matplotlib's unit conversion, so this should
            be a unit-less array.

        detrend : callable, default: `.mlab.detrend_none` (no detrending)
            A detrending function applied to *x*.  It must have the
            signature ::

                detrend(x: np.ndarray) -> np.ndarray

        normed : bool, default: True
            If ``True``, input vectors are normalised to unit length.

        usevlines : bool, default: True
            Determines the plot style.

            If ``True``, vertical lines are plotted from 0 to the acorr value
            using `.Axes.vlines`. Additionally, a horizontal line is plotted
            at y=0 using `.Axes.axhline`.

            If ``False``, markers are plotted at the acorr values using
            `.Axes.plot`.

        maxlags : int, default: 10
            Number of lags to show. If ``None``, will return all
            ``2 * len(x) - 1`` lags.

        Returns
        -------
        lags : array (length ``2*maxlags+1``)
            The lag vector.
        c : array  (length ``2*maxlags+1``)
            The auto correlation vector.
        line : `.LineCollection` or `.Line2D`
            `.Artist` added to the Axes of the correlation:

            - `.LineCollection` if *usevlines* is True.
            - `.Line2D` if *usevlines* is False.
        b : `~matplotlib.lines.Line2D` or None
            Horizontal line at 0 if *usevlines* is True
            None *usevlines* is False.

        Other Parameters
        ----------------
        linestyle : `~matplotlib.lines.Line2D` property, optional
            The linestyle for plotting the data points.
            Only used if *usevlines* is ``False``.

        marker : str, default: 'o'
            The marker for plotting the data points.
            Only used if *usevlines* is ``False``.

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Additional parameters are passed to `.Axes.vlines` and
            `.Axes.axhline` if *usevlines* is ``True``; otherwise they are
            passed to `.Axes.plot`.

        Notes
        -----
        The cross correlation is performed with `numpy.correlate` with
        ``mode = "full"``.
        """
        return self.xcorr(x, x, **kwargs)

    @_api.make_keyword_only("3.10", "normed")
    @_preprocess_data(replace_names=["x", "y"], label_namer="y")
    def xcorr(self, x, y, normed=True, detrend=mlab.detrend_none,
              usevlines=True, maxlags=10, **kwargs):
        r"""
        Plot the cross correlation between *x* and *y*.

        The correlation with lag k is defined as
        :math:`\sum_n x[n+k] \cdot y^*[n]`, where :math:`y^*` is the complex
        conjugate of :math:`y`.

        Parameters
        ----------
        x, y : array-like of length n
            Neither *x* nor *y* are run through Matplotlib's unit conversion, so
            these should be unit-less arrays.

        detrend : callable, default: `.mlab.detrend_none` (no detrending)
            A detrending function applied to *x* and *y*.  It must have the
            signature ::

                detrend(x: np.ndarray) -> np.ndarray

        normed : bool, default: True
            If ``True``, input vectors are normalised to unit length.

        usevlines : bool, default: True
            Determines the plot style.

            If ``True``, vertical lines are plotted from 0 to the xcorr value
            using `.Axes.vlines`. Additionally, a horizontal line is plotted
            at y=0 using `.Axes.axhline`.

            If ``False``, markers are plotted at the xcorr values using
            `.Axes.plot`.

        maxlags : int, default: 10
            Number of lags to show. If None, will return all ``2 * len(x) - 1``
            lags.

        Returns
        -------
        lags : array (length ``2*maxlags+1``)
            The lag vector.
        c : array  (length ``2*maxlags+1``)
            The auto correlation vector.
        line : `.LineCollection` or `.Line2D`
            `.Artist` added to the Axes of the correlation:

            - `.LineCollection` if *usevlines* is True.
            - `.Line2D` if *usevlines* is False.
        b : `~matplotlib.lines.Line2D` or None
            Horizontal line at 0 if *usevlines* is True
            None *usevlines* is False.

        Other Parameters
        ----------------
        linestyle : `~matplotlib.lines.Line2D` property, optional
            The linestyle for plotting the data points.
            Only used if *usevlines* is ``False``.

        marker : str, default: 'o'
            The marker for plotting the data points.
            Only used if *usevlines* is ``False``.

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Additional parameters are passed to `.Axes.vlines` and
            `.Axes.axhline` if *usevlines* is ``True``; otherwise they are
            passed to `.Axes.plot`.

        Notes
        -----
        The cross correlation is performed with `numpy.correlate` with
        ``mode = "full"``.
        """
        Nx = len(x)
        if Nx != len(y):
            raise ValueError('x and y must be equal length')

        x = detrend(np.asarray(x))
        y = detrend(np.asarray(y))

        correls = np.correlate(x, y, mode="full")

        if normed:
            correls = correls / np.sqrt(np.dot(x, x) * np.dot(y, y))

        if maxlags is None:
            maxlags = Nx - 1

        if maxlags >= Nx or maxlags < 1:
            raise ValueError('maxlags must be None or strictly '
                             'positive < %d' % Nx)

        lags = np.arange(-maxlags, maxlags + 1)
        correls = correls[Nx - 1 - maxlags:Nx + maxlags]

        if usevlines:
            a = self.vlines(lags, [0], correls, **kwargs)
            # Make label empty so only vertical lines get a legend entry
            kwargs.pop('label', '')
            b = self.axhline(**kwargs)
        else:
            kwargs.setdefault('marker', 'o')
            kwargs.setdefault('linestyle', 'None')
            a, = self.plot(lags, correls, **kwargs)
            b = None
        return lags, correls, a, b

    #### Specialized plotting

    # @_preprocess_data() # let 'plot' do the unpacking..
    def step(self, x, y, *args, where='pre', data=None, **kwargs):
        """
        Make a step plot.

        Call signatures::

            step(x, y, [fmt], *, data=None, where='pre', **kwargs)
            step(x, y, [fmt], x2, y2, [fmt2], ..., *, where='pre', **kwargs)

        This is just a thin wrapper around `.plot` which changes some
        formatting options. Most of the concepts and parameters of plot can be
        used here as well.

        .. note::

            This method uses a standard plot with a step drawstyle: The *x*
            values are the reference positions and steps extend left/right/both
            directions depending on *where*.

            For the common case where you know the values and edges of the
            steps, use `~.Axes.stairs` instead.

        Parameters
        ----------
        x : array-like
            1D sequence of x positions. It is assumed, but not checked, that
            it is uniformly increasing.

        y : array-like
            1D sequence of y levels.

        fmt : str, optional
            A format string, e.g. 'g' for a green line. See `.plot` for a more
            detailed description.

            Note: While full format strings are accepted, it is recommended to
            only specify the color. Line styles are currently ignored (use
            the keyword argument *linestyle* instead). Markers are accepted
            and plotted on the given positions, however, this is a rarely
            needed feature for step plots.

        where : {'pre', 'post', 'mid'}, default: 'pre'
            Define where the steps should be placed:

            - 'pre': The y value is continued constantly to the left from
              every *x* position, i.e. the interval ``(x[i-1], x[i]]`` has the
              value ``y[i]``.
            - 'post': The y value is continued constantly to the right from
              every *x* position, i.e. the interval ``[x[i], x[i+1])`` has the
              value ``y[i]``.
            - 'mid': Steps occur half-way between the *x* positions.

        data : indexable object, optional
            An object with labelled data. If given, provide the label names to
            plot in *x* and *y*.

        **kwargs
            Additional parameters are the same as those for `.plot`.

        Returns
        -------
        list of `.Line2D`
            Objects representing the plotted data.
        """
        _api.check_in_list(('pre', 'post', 'mid'), where=where)
        kwargs['drawstyle'] = 'steps-' + where
        return self.plot(x, y, *args, data=data, **kwargs)

    @staticmethod
    def _convert_dx(dx, x0, xconv, convert):
        """
        Small helper to do logic of width conversion flexibly.

        *dx* and *x0* have units, but *xconv* has already been converted
        to unitless (and is an ndarray).  This allows the *dx* to have units
        that are different from *x0*, but are still accepted by the
        ``__add__`` operator of *x0*.
        """

        # x should be an array...
        assert type(xconv) is np.ndarray

        if xconv.size == 0:
            # xconv has already been converted, but maybe empty...
            return convert(dx)

        try:
            # attempt to add the width to x0; this works for
            # datetime+timedelta, for instance

            # only use the first element of x and x0.  This saves
            # having to be sure addition works across the whole
            # vector.  This is particularly an issue if
            # x0 and dx are lists so x0 + dx just concatenates the lists.
            # We can't just cast x0 and dx to numpy arrays because that
            # removes the units from unit packages like `pint` that
            # wrap numpy arrays.
            try:
                x0 = cbook._safe_first_finite(x0)
            except (TypeError, IndexError, KeyError):
                pass

            try:
                x = cbook._safe_first_finite(xconv)
            except (TypeError, IndexError, KeyError):
                x = xconv

            delist = False
            if not np.iterable(dx):
                dx = [dx]
                delist = True
            dx = [convert(x0 + ddx) - x for ddx in dx]
            if delist:
                dx = dx[0]
        except (ValueError, TypeError, AttributeError):
            # if the above fails (for any reason) just fallback to what
            # we do by default and convert dx by itself.
            dx = convert(dx)
        return dx

    def _parse_bar_color_args(self, kwargs):
        """
        Helper function to process color-related arguments of `.Axes.bar`.

        Argument precedence for facecolors:

        - kwargs['facecolor']
        - kwargs['color']
        - 'Result of ``self._get_patches_for_fill.get_next_color``

        Argument precedence for edgecolors:

        - kwargs['edgecolor']
        - None

        Parameters
        ----------
        self : Axes

        kwargs : dict
            Additional kwargs. If these keys exist, we pop and process them:
            'facecolor', 'edgecolor', 'color'
            Note: The dict is modified by this function.


        Returns
        -------
        facecolor
            The facecolor. One or more colors as (N, 4) rgba array.
        edgecolor
            The edgecolor. Not normalized; may be any valid color spec or None.
        """
        color = kwargs.pop('color', None)

        facecolor = kwargs.pop('facecolor', color)
        edgecolor = kwargs.pop('edgecolor', None)

        facecolor = (facecolor if facecolor is not None
                     else self._get_patches_for_fill.get_next_color())

        try:
            facecolor = mcolors.to_rgba_array(facecolor)
        except ValueError as err:
            raise ValueError(
                "'facecolor' or 'color' argument must be a valid color or "
                "sequence of colors."
            ) from err

        return facecolor, edgecolor

    @_preprocess_data()
    @_docstring.interpd
    def bar(self, x, height, width=0.8, bottom=None, *, align="center",
            **kwargs):
        r"""
        Make a bar plot.

        The bars are positioned at *x* with the given *align*\ment. Their
        dimensions are given by *height* and *width*. The vertical baseline
        is *bottom* (default 0).

        Many parameters can take either a single value applying to all bars
        or a sequence of values, one for each bar.

        Parameters
        ----------
        x : float or array-like
            The x coordinates of the bars. See also *align* for the
            alignment of the bars to the coordinates.

            Bars are often used for categorical data, i.e. string labels below
            the bars. You can provide a list of strings directly to *x*.
            ``bar(['A', 'B', 'C'], [1, 2, 3])`` is often a shorter and more
            convenient notation compared to
            ``bar(range(3), [1, 2, 3], tick_label=['A', 'B', 'C'])``. They are
            equivalent as long as the names are unique. The explicit *tick_label*
            notation draws the names in the sequence given. However, when having
            duplicate values in categorical *x* data, these values map to the same
            numerical x coordinate, and hence the corresponding bars are drawn on
            top of each other.

        height : float or array-like
            The height(s) of the bars.

            Note that if *bottom* has units (e.g. datetime), *height* should be in
            units that are a difference from the value of *bottom* (e.g. timedelta).

        width : float or array-like, default: 0.8
            The width(s) of the bars.

            Note that if *x* has units (e.g. datetime), then *width* should be in
            units that are a difference (e.g. timedelta) around the *x* values.

        bottom : float or array-like, default: 0
            The y coordinate(s) of the bottom side(s) of the bars.

            Note that if *bottom* has units, then the y-axis will get a Locator and
            Formatter appropriate for the units (e.g. dates, or categorical).

        align : {'center', 'edge'}, default: 'center'
            Alignment of the bars to the *x* coordinates:

            - 'center': Center the base on the *x* positions.
            - 'edge': Align the left edges of the bars with the *x* positions.

            To align the bars on the right edge pass a negative *width* and
            ``align='edge'``.

        Returns
        -------
        `.BarContainer`
            Container with all the bars and optionally errorbars.

        Other Parameters
        ----------------
        color : :mpltype:`color` or list of :mpltype:`color`, optional
            The colors of the bar faces. This is an alias for *facecolor*.
            If both are given, *facecolor* takes precedence.

        facecolor : :mpltype:`color` or list of :mpltype:`color`, optional
            The colors of the bar faces.
            If both *color* and *facecolor are given, *facecolor* takes precedence.

        edgecolor : :mpltype:`color` or list of :mpltype:`color`, optional
            The colors of the bar edges.

        linewidth : float or array-like, optional
            Width of the bar edge(s). If 0, don't draw edges.

        tick_label : str or list of str, optional
            The tick labels of the bars.
            Default: None (Use default numeric labels.)

        label : str or list of str, optional
            A single label is attached to the resulting `.BarContainer` as a
            label for the whole dataset.
            If a list is provided, it must be the same length as *x* and
            labels the individual bars. Repeated labels are not de-duplicated
            and will cause repeated label entries, so this is best used when
            bars also differ in style (e.g., by passing a list to *color*.)

        xerr, yerr : float or array-like of shape(N,) or shape(2, N), optional
            If not *None*, add horizontal / vertical errorbars to the bar tips.
            The values are +/- sizes relative to the data:

            - scalar: symmetric +/- values for all bars
            - shape(N,): symmetric +/- values for each bar
            - shape(2, N): Separate - and + values for each bar. First row
              contains the lower errors, the second row contains the upper
              errors.
            - *None*: No errorbar. (Default)

            See :doc:`/gallery/statistics/errorbar_features` for an example on
            the usage of *xerr* and *yerr*.

        ecolor : :mpltype:`color` or list of :mpltype:`color`, default: 'black'
            The line color of the errorbars.

        capsize : float, default: :rc:`errorbar.capsize`
           The length of the error bar caps in points.

        error_kw : dict, optional
            Dictionary of keyword arguments to be passed to the
            `~.Axes.errorbar` method. Values of *ecolor* or *capsize* defined
            here take precedence over the independent keyword arguments.

        log : bool, default: False
            If *True*, set the y-axis to be log scale.

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs : `.Rectangle` properties

        %(Rectangle:kwdoc)s

        See Also
        --------
        barh : Plot a horizontal bar plot.

        Notes
        -----
        Stacked bars can be achieved by passing individual *bottom* values per
        bar. See :doc:`/gallery/lines_bars_and_markers/bar_stacked`.
        """
        kwargs = cbook.normalize_kwargs(kwargs, mpatches.Patch)
        facecolor, edgecolor = self._parse_bar_color_args(kwargs)

        linewidth = kwargs.pop('linewidth', None)
        hatch = kwargs.pop('hatch', None)

        # Because xerr and yerr will be passed to errorbar, most dimension
        # checking and processing will be left to the errorbar method.
        xerr = kwargs.pop('xerr', None)
        yerr = kwargs.pop('yerr', None)
        error_kw = kwargs.pop('error_kw', None)
        error_kw = {} if error_kw is None else error_kw.copy()
        ezorder = error_kw.pop('zorder', None)
        if ezorder is None:
            ezorder = kwargs.get('zorder', None)
            if ezorder is not None:
                # If using the bar zorder, increment slightly to make sure
                # errorbars are drawn on top of bars
                ezorder += 0.01
        error_kw.setdefault('zorder', ezorder)
        ecolor = kwargs.pop('ecolor', 'k')
        capsize = kwargs.pop('capsize', mpl.rcParams["errorbar.capsize"])
        error_kw.setdefault('ecolor', ecolor)
        error_kw.setdefault('capsize', capsize)

        # The keyword argument *orientation* is used by barh() to defer all
        # logic and drawing to bar(). It is considered internal and is
        # intentionally not mentioned in the docstring.
        orientation = kwargs.pop('orientation', 'vertical')
        _api.check_in_list(['vertical', 'horizontal'], orientation=orientation)
        log = kwargs.pop('log', False)
        label = kwargs.pop('label', '')
        tick_labels = kwargs.pop('tick_label', None)

        y = bottom  # Matches barh call signature.
        if orientation == 'vertical':
            if y is None:
                y = 0
        else:  # horizontal
            if x is None:
                x = 0

        if orientation == 'vertical':
            # It is possible for y (bottom) to contain unit information.
            # However, it is also possible for y=0 for the default and height
            # to contain unit information.  This will prioritize the units of y.
            self._process_unit_info(
                [("x", x), ("y", y), ("y", height)], kwargs, convert=False)
            if log:
                self.set_yscale('log', nonpositive='clip')
        else:  # horizontal
            # It is possible for x (left) to contain unit information.
            # However, it is also possible for x=0 for the default and width
            # to contain unit information.  This will prioritize the units of x.
            self._process_unit_info(
                [("x", x), ("x", width), ("y", y)], kwargs, convert=False)
            if log:
                self.set_xscale('log', nonpositive='clip')

        # lets do some conversions now since some types cannot be
        # subtracted uniformly
        if self.xaxis is not None:
            x0 = x
            x = np.asarray(self.convert_xunits(x))
            width = self._convert_dx(width, x0, x, self.convert_xunits)
            if xerr is not None:
                xerr = self._convert_dx(xerr, x0, x, self.convert_xunits)
        if self.yaxis is not None:
            y0 = y
            y = np.asarray(self.convert_yunits(y))
            height = self._convert_dx(height, y0, y, self.convert_yunits)
            if yerr is not None:
                yerr = self._convert_dx(yerr, y0, y, self.convert_yunits)

        x, height, width, y, linewidth, hatch = np.broadcast_arrays(
            # Make args iterable too.
            np.atleast_1d(x), height, width, y, linewidth, hatch)

        # Now that units have been converted, set the tick locations.
        if orientation == 'vertical':
            tick_label_axis = self.xaxis
            tick_label_position = x
        else:  # horizontal
            tick_label_axis = self.yaxis
            tick_label_position = y

        if not isinstance(label, str) and np.iterable(label):
            bar_container_label = '_nolegend_'
            patch_labels = label
        else:
            bar_container_label = label
            patch_labels = ['_nolegend_'] * len(x)
        if len(patch_labels) != len(x):
            raise ValueError(f'number of labels ({len(patch_labels)}) '
                             f'does not match number of bars ({len(x)}).')

        linewidth = itertools.cycle(np.atleast_1d(linewidth))
        hatch = itertools.cycle(np.atleast_1d(hatch))
        facecolor = itertools.chain(itertools.cycle(facecolor),
                                    # Fallback if color == "none".
                                    itertools.repeat('none'))
        if edgecolor is None:
            edgecolor = itertools.repeat(None)
        else:
            edgecolor = itertools.chain(
                itertools.cycle(mcolors.to_rgba_array(edgecolor)),
                # Fallback if edgecolor == "none".
                itertools.repeat('none'))

        # We will now resolve the alignment and really have
        # left, bottom, width, height vectors
        _api.check_in_list(['center', 'edge'], align=align)
        if align == 'center':
            if orientation == 'vertical':
                try:
                    left = x - width / 2
                except TypeError as e:
                    raise TypeError(f'the dtypes of parameters x ({x.dtype}) '
                                    f'and width ({width.dtype}) '
                                    f'are incompatible') from e
                bottom = y
            else:  # horizontal
                try:
                    bottom = y - height / 2
                except TypeError as e:
                    raise TypeError(f'the dtypes of parameters y ({y.dtype}) '
                                    f'and height ({height.dtype}) '
                                    f'are incompatible') from e
                left = x
        else:  # edge
            left = x
            bottom = y

        patches = []
        args = zip(left, bottom, width, height, facecolor, edgecolor, linewidth,
                   hatch, patch_labels)
        for l, b, w, h, c, e, lw, htch, lbl in args:
            r = mpatches.Rectangle(
                xy=(l, b), width=w, height=h,
                facecolor=c,
                edgecolor=e,
                linewidth=lw,
                label=lbl,
                hatch=htch,
                )
            r._internal_update(kwargs)
            r.get_path()._interpolation_steps = 100
            if orientation == 'vertical':
                r.sticky_edges.y.append(b)
            else:  # horizontal
                r.sticky_edges.x.append(l)
            self.add_patch(r)
            patches.append(r)

        if xerr is not None or yerr is not None:
            if orientation == 'vertical':
                # using list comps rather than arrays to preserve unit info
                ex = [l + 0.5 * w for l, w in zip(left, width)]
                ey = [b + h for b, h in zip(bottom, height)]

            else:  # horizontal
                # using list comps rather than arrays to preserve unit info
                ex = [l + w for l, w in zip(left, width)]
                ey = [b + 0.5 * h for b, h in zip(bottom, height)]

            error_kw.setdefault("label", '_nolegend_')

            errorbar = self.errorbar(ex, ey, yerr=yerr, xerr=xerr, fmt='none',
                                     **error_kw)
        else:
            errorbar = None

        self._request_autoscale_view()

        if orientation == 'vertical':
            datavalues = height
        else:  # horizontal
            datavalues = width

        bar_container = BarContainer(patches, errorbar, datavalues=datavalues,
                                     orientation=orientation,
                                     label=bar_container_label)
        self.add_container(bar_container)

        if tick_labels is not None:
            tick_labels = np.broadcast_to(tick_labels, len(patches))
            tick_label_axis.set_ticks(tick_label_position)
            tick_label_axis.set_ticklabels(tick_labels)

        return bar_container

    # @_preprocess_data() # let 'bar' do the unpacking..
    @_docstring.interpd
    def barh(self, y, width, height=0.8, left=None, *, align="center",
             data=None, **kwargs):
        r"""
        Make a horizontal bar plot.

        The bars are positioned at *y* with the given *align*\ment. Their
        dimensions are given by *width* and *height*. The horizontal baseline
        is *left* (default 0).

        Many parameters can take either a single value applying to all bars
        or a sequence of values, one for each bar.

        Parameters
        ----------
        y : float or array-like
            The y coordinates of the bars. See also *align* for the
            alignment of the bars to the coordinates.

            Bars are often used for categorical data, i.e. string labels below
            the bars. You can provide a list of strings directly to *y*.
            ``barh(['A', 'B', 'C'], [1, 2, 3])`` is often a shorter and more
            convenient notation compared to
            ``barh(range(3), [1, 2, 3], tick_label=['A', 'B', 'C'])``. They are
            equivalent as long as the names are unique. The explicit *tick_label*
            notation draws the names in the sequence given. However, when having
            duplicate values in categorical *y* data, these values map to the same
            numerical y coordinate, and hence the corresponding bars are drawn on
            top of each other.

        width : float or array-like
            The width(s) of the bars.

            Note that if *left* has units (e.g. datetime), *width* should be in
            units that are a difference from the value of *left* (e.g. timedelta).

        height : float or array-like, default: 0.8
            The heights of the bars.

            Note that if *y* has units (e.g. datetime), then *height* should be in
            units that are a difference (e.g. timedelta) around the *y* values.

        left : float or array-like, default: 0
            The x coordinates of the left side(s) of the bars.

            Note that if *left* has units, then the x-axis will get a Locator and
            Formatter appropriate for the units (e.g. dates, or categorical).

        align : {'center', 'edge'}, default: 'center'
            Alignment of the base to the *y* coordinates*:

            - 'center': Center the bars on the *y* positions.
            - 'edge': Align the bottom edges of the bars with the *y*
              positions.

            To align the bars on the top edge pass a negative *height* and
            ``align='edge'``.

        Returns
        -------
        `.BarContainer`
            Container with all the bars and optionally errorbars.

        Other Parameters
        ----------------
        color : :mpltype:`color` or list of :mpltype:`color`, optional
            The colors of the bar faces.

        edgecolor : :mpltype:`color` or list of :mpltype:`color`, optional
            The colors of the bar edges.

        linewidth : float or array-like, optional
            Width of the bar edge(s). If 0, don't draw edges.

        tick_label : str or list of str, optional
            The tick labels of the bars.
            Default: None (Use default numeric labels.)

        label : str or list of str, optional
            A single label is attached to the resulting `.BarContainer` as a
            label for the whole dataset.
            If a list is provided, it must be the same length as *y* and
            labels the individual bars. Repeated labels are not de-duplicated
            and will cause repeated label entries, so this is best used when
            bars also differ in style (e.g., by passing a list to *color*.)

        xerr, yerr : float or array-like of shape(N,) or shape(2, N), optional
            If not *None*, add horizontal / vertical errorbars to the bar tips.
            The values are +/- sizes relative to the data:

            - scalar: symmetric +/- values for all bars
            - shape(N,): symmetric +/- values for each bar
            - shape(2, N): Separate - and + values for each bar. First row
              contains the lower errors, the second row contains the upper
              errors.
            - *None*: No errorbar. (default)

            See :doc:`/gallery/statistics/errorbar_features` for an example on
            the usage of *xerr* and *yerr*.

        ecolor : :mpltype:`color` or list of :mpltype:`color`, default: 'black'
            The line color of the errorbars.

        capsize : float, default: :rc:`errorbar.capsize`
           The length of the error bar caps in points.

        error_kw : dict, optional
            Dictionary of keyword arguments to be passed to the
            `~.Axes.errorbar` method. Values of *ecolor* or *capsize* defined
            here take precedence over the independent keyword arguments.

        log : bool, default: False
            If ``True``, set the x-axis to be log scale.

        data : indexable object, optional
            If given, all parameters also accept a string ``s``, which is
            interpreted as ``data[s]`` if  ``s`` is a key in ``data``.

        **kwargs : `.Rectangle` properties

        %(Rectangle:kwdoc)s

        See Also
        --------
        bar : Plot a vertical bar plot.

        Notes
        -----
        Stacked bars can be achieved by passing individual *left* values per
        bar. See
        :doc:`/gallery/lines_bars_and_markers/horizontal_barchart_distribution`.
        """
        kwargs.setdefault('orientation', 'horizontal')
        patches = self.bar(x=left, height=height, width=width, bottom=y,
                           align=align, data=data, **kwargs)
        return patches

    def bar_label(self, container, labels=None, *, fmt="%g", label_type="edge",
                  padding=0, **kwargs):
        """
        Label a bar plot.

        Adds labels to bars in the given `.BarContainer`.
        You may need to adjust the axis limits to fit the labels.

        Parameters
        ----------
        container : `.BarContainer`
            Container with all the bars and optionally errorbars, likely
            returned from `.bar` or `.barh`.

        labels : array-like, optional
            A list of label texts, that should be displayed. If not given, the
            label texts will be the data values formatted with *fmt*.

        fmt : str or callable, default: '%g'
            An unnamed %-style or {}-style format string for the label or a
            function to call with the value as the first argument.
            When *fmt* is a string and can be interpreted in both formats,
            %-style takes precedence over {}-style.

            .. versionadded:: 3.7
               Support for {}-style format string and callables.

        label_type : {'edge', 'center'}, default: 'edge'
            The label type. Possible values:

            - 'edge': label placed at the end-point of the bar segment, and the
              value displayed will be the position of that end-point.
            - 'center': label placed in the center of the bar segment, and the
              value displayed will be the length of that segment.
              (useful for stacked bars, i.e.,
              :doc:`/gallery/lines_bars_and_markers/bar_label_demo`)

        padding : float, default: 0
            Distance of label from the end of the bar, in points.

        **kwargs
            Any remaining keyword arguments are passed through to
            `.Axes.annotate`. The alignment parameters (
            *horizontalalignment* / *ha*, *verticalalignment* / *va*) are
            not supported because the labels are automatically aligned to
            the bars.

        Returns
        -------
        list of `.Annotation`
            A list of `.Annotation` instances for the labels.
        """
        for key in ['horizontalalignment', 'ha', 'verticalalignment', 'va']:
            if key in kwargs:
                raise ValueError(
                    f"Passing {key!r} to bar_label() is not supported.")

        a, b = self.yaxis.get_view_interval()
        y_inverted = a > b
        c, d = self.xaxis.get_view_interval()
        x_inverted = c > d

        # want to know whether to put label on positive or negative direction
        # cannot use np.sign here because it will return 0 if x == 0
        def sign(x):
            return 1 if x >= 0 else -1

        _api.check_in_list(['edge', 'center'], label_type=label_type)

        bars = container.patches
        errorbar = container.errorbar
        datavalues = container.datavalues
        orientation = container.orientation

        if errorbar:
            # check "ErrorbarContainer" for the definition of these elements
            lines = errorbar.lines  # attribute of "ErrorbarContainer" (tuple)
            barlinecols = lines[2]  # 0: data_line, 1: caplines, 2: barlinecols
            barlinecol = barlinecols[0]  # the "LineCollection" of error bars
            errs = barlinecol.get_segments()
        else:
            errs = []

        if labels is None:
            labels = []

        annotations = []

        for bar, err, dat, lbl in itertools.zip_longest(
                bars, errs, datavalues, labels
        ):
            (x0, y0), (x1, y1) = bar.get_bbox().get_points()
            xc, yc = (x0 + x1) / 2, (y0 + y1) / 2

            if orientation == "vertical":
                extrema = max(y0, y1) if dat >= 0 else min(y0, y1)
                length = abs(y0 - y1)
            else:  # horizontal
                extrema = max(x0, x1) if dat >= 0 else min(x0, x1)
                length = abs(x0 - x1)

            if err is None or np.size(err) == 0:
                endpt = extrema
            elif orientation == "vertical":
                endpt = err[:, 1].max() if dat >= 0 else err[:, 1].min()
            else:  # horizontal
                endpt = err[:, 0].max() if dat >= 0 else err[:, 0].min()

            if label_type == "center":
                value = sign(dat) * length
            else:  # edge
                value = extrema

            if label_type == "center":
                xy = (0.5, 0.5)
                kwargs["xycoords"] = (
                    lambda r, b=bar:
                        mtransforms.Bbox.intersection(
                            b.get_window_extent(r), b.get_clip_box()
                        ) or mtransforms.Bbox.null()
                )
            else:  # edge
                if orientation == "vertical":
                    xy = xc, endpt
                else:  # horizontal
                    xy = endpt, yc

            if orientation == "vertical":
                y_direction = -1 if y_inverted else 1
                xytext = 0, y_direction * sign(dat) * padding
            else:  # horizontal
                x_direction = -1 if x_inverted else 1
                xytext = x_direction * sign(dat) * padding, 0

            if label_type == "center":
                ha, va = "center", "center"
            else:  # edge
                if orientation == "vertical":
                    ha = 'center'
                    if y_inverted:
                        va = 'top' if dat > 0 else 'bottom'  # also handles NaN
                    else:
                        va = 'top' if dat < 0 else 'bottom'  # also handles NaN
                else:  # horizontal
                    if x_inverted:
                        ha = 'right' if dat > 0 else 'left'  # also handles NaN
                    else:
                        ha = 'right' if dat < 0 else 'left'  # also handles NaN
                    va = 'center'

            if np.isnan(dat):
                lbl = ''

            if lbl is None:
                if isinstance(fmt, str):
                    lbl = cbook._auto_format_str(fmt, value)
                elif callable(fmt):
                    lbl = fmt(value)
                else:
                    raise TypeError("fmt must be a str or callable")
            annotation = self.annotate(lbl,
                                       xy, xytext, textcoords="offset points",
                                       ha=ha, va=va, **kwargs)
            annotations.append(annotation)

        return annotations

    @_preprocess_data()
    @_docstring.interpd
    def broken_barh(self, xranges, yrange, **kwargs):
        """
        Plot a horizontal sequence of rectangles.

        A rectangle is drawn for each element of *xranges*. All rectangles
        have the same vertical position and size defined by *yrange*.

        Parameters
        ----------
        xranges : sequence of tuples (*xmin*, *xwidth*)
            The x-positions and extents of the rectangles. For each tuple
            (*xmin*, *xwidth*) a rectangle is drawn from *xmin* to *xmin* +
            *xwidth*.
        yrange : (*ymin*, *yheight*)
            The y-position and extent for all the rectangles.

        Returns
        -------
        `~.collections.PolyCollection`

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER
        **kwargs : `.PolyCollection` properties

            Each *kwarg* can be either a single argument applying to all
            rectangles, e.g.::

                facecolors='black'

            or a sequence of arguments over which is cycled, e.g.::

                facecolors=('black', 'blue')

            would create interleaving black and blue rectangles.

            Supported keywords:

            %(PolyCollection:kwdoc)s
        """
        # process the unit information
        xdata = cbook._safe_first_finite(xranges) if len(xranges) else None
        ydata = cbook._safe_first_finite(yrange) if len(yrange) else None
        self._process_unit_info(
            [("x", xdata), ("y", ydata)], kwargs, convert=False)

        vertices = []
        y0, dy = yrange
        y0, y1 = self.convert_yunits((y0, y0 + dy))
        for xr in xranges:  # convert the absolute values, not the x and dx
            try:
                x0, dx = xr
            except Exception:
                raise ValueError(
                    "each range in xrange must be a sequence with two "
                    "elements (i.e. xrange must be an (N, 2) array)") from None
            x0, x1 = self.convert_xunits((x0, x0 + dx))
            vertices.append([(x0, y0), (x0, y1), (x1, y1), (x1, y0)])

        col = mcoll.PolyCollection(np.array(vertices), **kwargs)
        self.add_collection(col, autolim=True)
        self._request_autoscale_view()

        return col

    @_preprocess_data()
    def stem(self, *args, linefmt=None, markerfmt=None, basefmt=None, bottom=0,
             label=None, orientation='vertical'):
        """
        Create a stem plot.

        A stem plot draws lines perpendicular to a baseline at each location
        *locs* from the baseline to *heads*, and places a marker there. For
        vertical stem plots (the default), the *locs* are *x* positions, and
        the *heads* are *y* values. For horizontal stem plots, the *locs* are
        *y* positions, and the *heads* are *x* values.

        Call signature::

          stem([locs,] heads, linefmt=None, markerfmt=None, basefmt=None)

        The *locs*-positions are optional. *linefmt* may be provided as
        positional, but all other formats must be provided as keyword
        arguments.

        Parameters
        ----------
        locs : array-like, default: (0, 1, ..., len(heads) - 1)
            For vertical stem plots, the x-positions of the stems.
            For horizontal stem plots, the y-positions of the stems.

        heads : array-like
            For vertical stem plots, the y-values of the stem heads.
            For horizontal stem plots, the x-values of the stem heads.

        linefmt : str, optional
            A string defining the color and/or linestyle of the vertical lines:

            =========  =============
            Character  Line Style
            =========  =============
            ``'-'``    solid line
            ``'--'``   dashed line
            ``'-.'``   dash-dot line
            ``':'``    dotted line
            =========  =============

            Default: 'C0-', i.e. solid line with the first color of the color
            cycle.

            Note: Markers specified through this parameter (e.g. 'x') will be
            silently ignored. Instead, markers should be specified using
            *markerfmt*.

        markerfmt : str, optional
            A string defining the color and/or shape of the markers at the stem
            heads. If the marker is not given, use the marker 'o', i.e. filled
            circles. If the color is not given, use the color from *linefmt*.

        basefmt : str, default: 'C3-' ('C2-' in classic mode)
            A format string defining the properties of the baseline.

        orientation : {'vertical', 'horizontal'}, default: 'vertical'
            The orientation of the stems.

        bottom : float, default: 0
            The y/x-position of the baseline (depending on *orientation*).

        label : str, optional
            The label to use for the stems in legends.

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        Returns
        -------
        `.StemContainer`
            The container may be treated like a tuple
            (*markerline*, *stemlines*, *baseline*)

        Notes
        -----
        .. seealso::
            The MATLAB function
            `stem <https://www.mathworks.com/help/matlab/ref/stem.html>`_
            which inspired this method.
        """
        if not 1 <= len(args) <= 3:
            raise _api.nargs_error('stem', '1-3', len(args))
        _api.check_in_list(['horizontal', 'vertical'], orientation=orientation)

        if len(args) == 1:
            heads, = args
            locs = np.arange(len(heads))
            args = ()
        elif isinstance(args[1], str):
            heads, *args = args
            locs = np.arange(len(heads))
        else:
            locs, heads, *args = args

        if orientation == 'vertical':
            locs, heads = self._process_unit_info([("x", locs), ("y", heads)])
        else:  # horizontal
            heads, locs = self._process_unit_info([("x", heads), ("y", locs)])

        heads = cbook._check_1d(heads)
        locs = cbook._check_1d(locs)

        # resolve line format
        if linefmt is None:
            linefmt = args[0] if len(args) > 0 else "C0-"
        linestyle, linemarker, linecolor = _process_plot_format(linefmt)

        # resolve marker format
        if markerfmt is None:
            # if not given as kwarg, fall back to 'o'
            markerfmt = "o"
        if markerfmt == '':
            markerfmt = ' '  # = empty line style; '' would resolve rcParams
        markerstyle, markermarker, markercolor = \
            _process_plot_format(markerfmt)
        if markermarker is None:
            markermarker = 'o'
        if markerstyle is None:
            markerstyle = 'None'
        if markercolor is None:
            markercolor = linecolor

        # resolve baseline format
        if basefmt is None:
            basefmt = ("C2-" if mpl.rcParams["_internal.classic_mode"] else
                       "C3-")
        basestyle, basemarker, basecolor = _process_plot_format(basefmt)

        # New behaviour in 3.1 is to use a LineCollection for the stemlines
        if linestyle is None:
            linestyle = mpl.rcParams['lines.linestyle']
        xlines = self.vlines if orientation == "vertical" else self.hlines
        stemlines = xlines(
            locs, bottom, heads,
            colors=linecolor, linestyles=linestyle, label="_nolegend_")

        if orientation == 'horizontal':
            marker_x = heads
            marker_y = locs
            baseline_x = [bottom, bottom]
            baseline_y = [np.min(locs), np.max(locs)]
        else:
            marker_x = locs
            marker_y = heads
            baseline_x = [np.min(locs), np.max(locs)]
            baseline_y = [bottom, bottom]

        markerline, = self.plot(marker_x, marker_y,
                                color=markercolor, linestyle=markerstyle,
                                marker=markermarker, label="_nolegend_")

        baseline, = self.plot(baseline_x, baseline_y,
                              color=basecolor, linestyle=basestyle,
                              marker=basemarker, label="_nolegend_")

        stem_container = StemContainer((markerline, stemlines, baseline),
                                       label=label)
        self.add_container(stem_container)
        return stem_container

    @_api.make_keyword_only("3.10", "explode")
    @_preprocess_data(replace_names=["x", "explode", "labels", "colors"])
    def pie(self, x, explode=None, labels=None, colors=None,
            autopct=None, pctdistance=0.6, shadow=False, labeldistance=1.1,
            startangle=0, radius=1, counterclock=True,
            wedgeprops=None, textprops=None, center=(0, 0),
            frame=False, rotatelabels=False, *, normalize=True, hatch=None):
        """
        Plot a pie chart.

        Make a pie chart of array *x*.  The fractional area of each wedge is
        given by ``x/sum(x)``.

        The wedges are plotted counterclockwise, by default starting from the
        x-axis.

        Parameters
        ----------
        x : 1D array-like
            The wedge sizes.

        explode : array-like, default: None
            If not *None*, is a ``len(x)`` array which specifies the fraction
            of the radius with which to offset each wedge.

        labels : list, default: None
            A sequence of strings providing the labels for each wedge

        colors : :mpltype:`color` or list of :mpltype:`color`, default: None
            A sequence of colors through which the pie chart will cycle.  If
            *None*, will use the colors in the currently active cycle.

        hatch : str or list, default: None
            Hatching pattern applied to all pie wedges or sequence of patterns
            through which the chart will cycle. For a list of valid patterns,
            see :doc:`/gallery/shapes_and_collections/hatch_style_reference`.

            .. versionadded:: 3.7

        autopct : None or str or callable, default: None
            If not *None*, *autopct* is a string or function used to label the
            wedges with their numeric value. The label will be placed inside
            the wedge. If *autopct* is a format string, the label will be
            ``fmt % pct``. If *autopct* is a function, then it will be called.

        pctdistance : float, default: 0.6
            The relative distance along the radius at which the text
            generated by *autopct* is drawn. To draw the text outside the pie,
            set *pctdistance* > 1. This parameter is ignored if *autopct* is
            ``None``.

        labeldistance : float or None, default: 1.1
            The relative distance along the radius at which the labels are
            drawn. To draw the labels inside the pie, set  *labeldistance* < 1.
            If set to ``None``, labels are not drawn but are still stored for
            use in `.legend`.

        shadow : bool or dict, default: False
            If bool, whether to draw a shadow beneath the pie. If dict, draw a shadow
            passing the properties in the dict to `.Shadow`.

            .. versionadded:: 3.8
                *shadow* can be a dict.

        startangle : float, default: 0 degrees
            The angle by which the start of the pie is rotated,
            counterclockwise from the x-axis.

        radius : float, default: 1
            The radius of the pie.

        counterclock : bool, default: True
            Specify fractions direction, clockwise or counterclockwise.

        wedgeprops : dict, default: None
            Dict of arguments passed to each `.patches.Wedge` of the pie.
            For example, ``wedgeprops = {'linewidth': 3}`` sets the width of
            the wedge border lines equal to 3. By default, ``clip_on=False``.
            When there is a conflict between these properties and other
            keywords, properties passed to *wedgeprops* take precedence.

        textprops : dict, default: None
            Dict of arguments to pass to the text objects.

        center : (float, float), default: (0, 0)
            The coordinates of the center of the chart.

        frame : bool, default: False
            Plot Axes frame with the chart if true.

        rotatelabels : bool, default: False
            Rotate each label to the angle of the corresponding slice if true.

        normalize : bool, default: True
            When *True*, always make a full pie by normalizing x so that
            ``sum(x) == 1``. *False* makes a partial pie if ``sum(x) <= 1``
            and raises a `ValueError` for ``sum(x) > 1``.

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        Returns
        -------
        patches : list
            A sequence of `matplotlib.patches.Wedge` instances

        texts : list
            A list of the label `.Text` instances.

        autotexts : list
            A list of `.Text` instances for the numeric labels. This will only
            be returned if the parameter *autopct* is not *None*.

        Notes
        -----
        The pie chart will probably look best if the figure and Axes are
        square, or the Axes aspect is equal.
        This method sets the aspect ratio of the axis to "equal".
        The Axes aspect ratio can be controlled with `.Axes.set_aspect`.
        """
        self.set_aspect('equal')
        # The use of float32 is "historical", but can't be changed without
        # regenerating the test baselines.
        x = np.asarray(x, np.float32)
        if x.ndim > 1:
            raise ValueError("x must be 1D")

        if np.any(x < 0):
            raise ValueError("Wedge sizes 'x' must be non negative values")

        sx = x.sum()

        if normalize:
            x = x / sx
        elif sx > 1:
            raise ValueError('Cannot plot an unnormalized pie with sum(x) > 1')
        if labels is None:
            labels = [''] * len(x)
        if explode is None:
            explode = [0] * len(x)
        if len(x) != len(labels):
            raise ValueError(f"'labels' must be of length 'x', not {len(labels)}")
        if len(x) != len(explode):
            raise ValueError(f"'explode' must be of length 'x', not {len(explode)}")
        if colors is None:
            get_next_color = self._get_patches_for_fill.get_next_color
        else:
            color_cycle = itertools.cycle(colors)

            def get_next_color():
                return next(color_cycle)

        hatch_cycle = itertools.cycle(np.atleast_1d(hatch))

        _api.check_isinstance(Real, radius=radius, startangle=startangle)
        if radius <= 0:
            raise ValueError(f"'radius' must be a positive number, not {radius}")

        # Starting theta1 is the start fraction of the circle
        theta1 = startangle / 360

        if wedgeprops is None:
            wedgeprops = {}
        if textprops is None:
            textprops = {}

        texts = []
        slices = []
        autotexts = []

        for frac, label, expl in zip(x, labels, explode):
            x, y = center
            theta2 = (theta1 + frac) if counterclock else (theta1 - frac)
            thetam = 2 * np.pi * 0.5 * (theta1 + theta2)
            x += expl * math.cos(thetam)
            y += expl * math.sin(thetam)

            w = mpatches.Wedge((x, y), radius, 360. * min(theta1, theta2),
                               360. * max(theta1, theta2),
                               facecolor=get_next_color(),
                               hatch=next(hatch_cycle),
                               clip_on=False,
                               label=label)
            w.set(**wedgeprops)
            slices.append(w)
            self.add_patch(w)

            if shadow:
                # Make sure to add a shadow after the call to add_patch so the
                # figure and transform props will be set.
                shadow_dict = {'ox': -0.02, 'oy': -0.02, 'label': '_nolegend_'}
                if isinstance(shadow, dict):
                    shadow_dict.update(shadow)
                self.add_patch(mpatches.Shadow(w, **shadow_dict))

            if labeldistance is not None:
                xt = x + labeldistance * radius * math.cos(thetam)
                yt = y + labeldistance * radius * math.sin(thetam)
                label_alignment_h = 'left' if xt > 0 else 'right'
                label_alignment_v = 'center'
                label_rotation = 'horizontal'
                if rotatelabels:
                    label_alignment_v = 'bottom' if yt > 0 else 'top'
                    label_rotation = (np.rad2deg(thetam)
                                      + (0 if xt > 0 else 180))
                t = self.text(xt, yt, label,
                              clip_on=False,
                              horizontalalignment=label_alignment_h,
                              verticalalignment=label_alignment_v,
                              rotation=label_rotation,
                              size=mpl.rcParams['xtick.labelsize'])
                t.set(**textprops)
                texts.append(t)

            if autopct is not None:
                xt = x + pctdistance * radius * math.cos(thetam)
                yt = y + pctdistance * radius * math.sin(thetam)
                if isinstance(autopct, str):
                    s = autopct % (100. * frac)
                elif callable(autopct):
                    s = autopct(100. * frac)
                else:
                    raise TypeError(
                        'autopct must be callable or a format string')
                if mpl._val_or_rc(textprops.get("usetex"), "text.usetex"):
                    # escape % (i.e. \%) if it is not already escaped
                    s = re.sub(r"([^\\])%", r"\1\\%", s)
                t = self.text(xt, yt, s,
                              clip_on=False,
                              horizontalalignment='center',
                              verticalalignment='center')
                t.set(**textprops)
                autotexts.append(t)

            theta1 = theta2

        if frame:
            self._request_autoscale_view()
        else:
            self.set(frame_on=False, xticks=[], yticks=[],
                     xlim=(-1.25 + center[0], 1.25 + center[0]),
                     ylim=(-1.25 + center[1], 1.25 + center[1]))

        if autopct is None:
            return slices, texts
        else:
            return slices, texts, autotexts

    @staticmethod
    def _errorevery_to_mask(x, errorevery):
        """
        Normalize `errorbar`'s *errorevery* to be a boolean mask for data *x*.

        This function is split out to be usable both by 2D and 3D errorbars.
        """
        if isinstance(errorevery, Integral):
            errorevery = (0, errorevery)
        if isinstance(errorevery, tuple):
            if (len(errorevery) == 2 and
                    isinstance(errorevery[0], Integral) and
                    isinstance(errorevery[1], Integral)):
                errorevery = slice(errorevery[0], None, errorevery[1])
            else:
                raise ValueError(
                    f'{errorevery=!r} is a not a tuple of two integers')
        elif isinstance(errorevery, slice):
            pass
        elif not isinstance(errorevery, str) and np.iterable(errorevery):
            try:
                x[errorevery]  # fancy indexing
            except (ValueError, IndexError) as err:
                raise ValueError(
                    f"{errorevery=!r} is iterable but not a valid NumPy fancy "
                    "index to match 'xerr'/'yerr'") from err
        else:
            raise ValueError(f"{errorevery=!r} is not a recognized value")
        everymask = np.zeros(len(x), bool)
        everymask[errorevery] = True
        return everymask

    @_api.make_keyword_only("3.10", "ecolor")
    @_preprocess_data(replace_names=["x", "y", "xerr", "yerr"],
                      label_namer="y")
    @_docstring.interpd
    def errorbar(self, x, y, yerr=None, xerr=None,
                 fmt='', ecolor=None, elinewidth=None, capsize=None,
                 barsabove=False, lolims=False, uplims=False,
                 xlolims=False, xuplims=False, errorevery=1, capthick=None,
                 **kwargs):
        """
        Plot y versus x as lines and/or markers with attached errorbars.

        *x*, *y* define the data locations, *xerr*, *yerr* define the errorbar
        sizes. By default, this draws the data markers/lines as well as the
        errorbars. Use fmt='none' to draw errorbars without any data markers.

        .. versionadded:: 3.7
           Caps and error lines are drawn in polar coordinates on polar plots.


        Parameters
        ----------
        x, y : float or array-like
            The data positions.

        xerr, yerr : float or array-like, shape(N,) or shape(2, N), optional
            The errorbar sizes:

            - scalar: Symmetric +/- values for all data points.
            - shape(N,): Symmetric +/-values for each data point.
            - shape(2, N): Separate - and + values for each bar. First row
              contains the lower errors, the second row contains the upper
              errors.
            - *None*: No errorbar.

            All values must be >= 0.

            See :doc:`/gallery/statistics/errorbar_features`
            for an example on the usage of ``xerr`` and ``yerr``.

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

        lolims, uplims, xlolims, xuplims : bool or array-like, default: False
            These arguments can be used to indicate that a value gives only
            upper/lower limits.  In that case a caret symbol is used to
            indicate this. *lims*-arguments may be scalars, or array-likes of
            the same length as *xerr* and *yerr*.  To use limits with inverted
            axes, `~.Axes.set_xlim` or `~.Axes.set_ylim` must be called before
            :meth:`errorbar`.  Note the tricky parameter names: setting e.g.
            *lolims* to True means that the y-value is a *lower* limit of the
            True value, so, only an *upward*-pointing arrow will be drawn!

        errorevery : int or (int, int), default: 1
            draws error bars on a subset of the data. *errorevery* =N draws
            error bars on the points (x[::N], y[::N]).
            *errorevery* =(start, N) draws error bars on the points
            (x[start::N], y[start::N]). e.g. errorevery=(6, 3)
            adds error bars to the data at (x[6], x[9], x[12], x[15], ...).
            Used to avoid overlapping error bars when two series share x-axis
            values.

        Returns
        -------
        `.ErrorbarContainer`
            The container contains:

            - data_line : A `~matplotlib.lines.Line2D` instance of x, y plot markers
              and/or line.
            - caplines : A tuple of `~matplotlib.lines.Line2D` instances of the error
              bar caps.
            - barlinecols : A tuple of `.LineCollection` with the horizontal and
              vertical error ranges.

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            All other keyword arguments are passed on to the `~.Axes.plot` call
            drawing the markers. For example, this code makes big red squares
            with thick green edges::

                x, y, yerr = rand(3, 10)
                errorbar(x, y, yerr, marker='s', mfc='red',
                         mec='green', ms=20, mew=4)

            where *mfc*, *mec*, *ms* and *mew* are aliases for the longer
            property names, *markerfacecolor*, *markeredgecolor*, *markersize*
            and *markeredgewidth*.

            Valid kwargs for the marker properties are:

            - *dashes*
            - *dash_capstyle*
            - *dash_joinstyle*
            - *drawstyle*
            - *fillstyle*
            - *linestyle*
            - *marker*
            - *markeredgecolor*
            - *markeredgewidth*
            - *markerfacecolor*
            - *markerfacecoloralt*
            - *markersize*
            - *markevery*
            - *solid_capstyle*
            - *solid_joinstyle*

            Refer to the corresponding `.Line2D` property for more details:

            %(Line2D:kwdoc)s
        """
        kwargs = cbook.normalize_kwargs(kwargs, mlines.Line2D)
        # Drop anything that comes in as None to use the default instead.
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        kwargs.setdefault('zorder', 2)

        # Casting to object arrays preserves units.
        if not isinstance(x, np.ndarray):
            x = np.asarray(x, dtype=object)
        if not isinstance(y, np.ndarray):
            y = np.asarray(y, dtype=object)

        def _upcast_err(err):
            """
            Safely handle tuple of containers that carry units.

            This function covers the case where the input to the xerr/yerr is a
            length 2 tuple of equal length ndarray-subclasses that carry the
            unit information in the container.

            If we have a tuple of nested numpy array (subclasses), we defer
            coercing the units to be consistent to the underlying unit
            library (and implicitly the broadcasting).

            Otherwise, fallback to casting to an object array.
            """

            if (
                    # make sure it is not a scalar
                    np.iterable(err) and
                    # and it is not empty
                    len(err) > 0 and
                    # and the first element is an array sub-class use
                    # safe_first_element because getitem is index-first not
                    # location first on pandas objects so err[0] almost always
                    # fails.
                    isinstance(cbook._safe_first_finite(err), np.ndarray)
            ):
                # Get the type of the first element
                atype = type(cbook._safe_first_finite(err))
                # Promote the outer container to match the inner container
                if atype is np.ndarray:
                    # Converts using np.asarray, because data cannot
                    # be directly passed to init of np.ndarray
                    return np.asarray(err, dtype=object)
                # If atype is not np.ndarray, directly pass data to init.
                # This works for types such as unyts and astropy units
                return atype(err)
            # Otherwise wrap it in an object array
            return np.asarray(err, dtype=object)

        if xerr is not None and not isinstance(xerr, np.ndarray):
            xerr = _upcast_err(xerr)
        if yerr is not None and not isinstance(yerr, np.ndarray):
            yerr = _upcast_err(yerr)
        x, y = np.atleast_1d(x, y)  # Make sure all the args are iterable.
        if len(x) != len(y):
            raise ValueError("'x' and 'y' must have the same size")

        everymask = self._errorevery_to_mask(x, errorevery)

        label = kwargs.pop("label", None)
        kwargs['label'] = '_nolegend_'

        # Create the main line and determine overall kwargs for child artists.
        # We avoid calling self.plot() directly, or self._get_lines(), because
        # that would call self._process_unit_info again, and do other indirect
        # data processing.
        (data_line, base_style), = self._get_lines._plot_args(
            self, (x, y) if fmt == '' else (x, y, fmt), kwargs, return_kwargs=True)

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
            # Remove alpha=0 color that _get_lines._plot_args returns for
            # 'none' format, and replace it with user-specified color, if
            # supplied.
            base_style.pop('color')
            if 'color' in kwargs:
                base_style['color'] = kwargs.pop('color')

        if 'color' not in base_style:
            base_style['color'] = 'C0'
        if ecolor is None:
            ecolor = base_style['color']

        # Eject any line-specific information from format string, as it's not
        # needed for bars or caps.
        for key in ['marker', 'markersize', 'markerfacecolor',
                    'markerfacecoloralt',
                    'markeredgewidth', 'markeredgecolor', 'markevery',
                    'linestyle', 'fillstyle', 'drawstyle', 'dash_capstyle',
                    'dash_joinstyle', 'solid_capstyle', 'solid_joinstyle',
                    'dashes']:
            base_style.pop(key, None)

        # Make the style dict for the line collections (the bars).
        eb_lines_style = {**base_style, 'color': ecolor}

        if elinewidth is not None:
            eb_lines_style['linewidth'] = elinewidth
        elif 'linewidth' in kwargs:
            eb_lines_style['linewidth'] = kwargs['linewidth']

        for key in ('transform', 'alpha', 'zorder', 'rasterized'):
            if key in kwargs:
                eb_lines_style[key] = kwargs[key]

        # Make the style dict for caps (the "hats").
        eb_cap_style = {**base_style, 'linestyle': 'none'}
        if capsize is None:
            capsize = mpl.rcParams["errorbar.capsize"]
        if capsize > 0:
            eb_cap_style['markersize'] = 2. * capsize
        if capthick is not None:
            eb_cap_style['markeredgewidth'] = capthick

        # For backwards-compat, allow explicit setting of
        # 'markeredgewidth' to over-ride capthick.
        for key in ('markeredgewidth', 'transform', 'alpha',
                    'zorder', 'rasterized'):
            if key in kwargs:
                eb_cap_style[key] = kwargs[key]
        eb_cap_style["markeredgecolor"] = ecolor

        barcols = []
        caplines = {'x': [], 'y': []}

        # Vectorized fancy-indexer.
        def apply_mask(arrays, mask):
            return [array[mask] for array in arrays]

        # dep: dependent dataset, indep: independent dataset
        for (dep_axis, dep, err, lolims, uplims, indep, lines_func,
             marker, lomarker, himarker) in [
                ("x", x, xerr, xlolims, xuplims, y, self.hlines,
                 "|", mlines.CARETRIGHTBASE, mlines.CARETLEFTBASE),
                ("y", y, yerr, lolims, uplims, x, self.vlines,
                 "_", mlines.CARETUPBASE, mlines.CARETDOWNBASE),
        ]:
            if err is None:
                continue
            lolims = np.broadcast_to(lolims, len(dep)).astype(bool)
            uplims = np.broadcast_to(uplims, len(dep)).astype(bool)
            try:
                np.broadcast_to(err, (2, len(dep)))
            except ValueError:
                raise ValueError(
                    f"'{dep_axis}err' (shape: {np.shape(err)}) must be a "
                    f"scalar or a 1D or (2, n) array-like whose shape matches "
                    f"'{dep_axis}' (shape: {np.shape(dep)})") from None
            if err.dtype is np.dtype(object) and np.any(err == None):  # noqa: E711
                raise ValueError(
                    f"'{dep_axis}err' must not contain None. "
                    "Use NaN if you want to skip a value.")

            # Raise if any errors are negative, but not if they are nan.
            # To avoid nan comparisons (which lead to warnings on some
            # platforms), we select with `err==err` (which is False for nan).
            # Also, since datetime.timedelta cannot be compared with 0,
            # we compare with the negative error instead.
            if np.any((check := err[err == err]) < -check):
                raise ValueError(
                    f"'{dep_axis}err' must not contain negative values")
            # This is like
            #     elow, ehigh = np.broadcast_to(...)
            #     return dep - elow * ~lolims, dep + ehigh * ~uplims
            # except that broadcast_to would strip units.
            low, high = dep + np.vstack([-(1 - lolims), 1 - uplims]) * err
            barcols.append(lines_func(
                *apply_mask([indep, low, high], everymask), **eb_lines_style))
            if self.name == "polar" and dep_axis == "x":
                for b in barcols:
                    for p in b.get_paths():
                        p._interpolation_steps = 2
            # Normal errorbars for points without upper/lower limits.
            nolims = ~(lolims | uplims)
            if nolims.any() and capsize > 0:
                indep_masked, lo_masked, hi_masked = apply_mask(
                    [indep, low, high], nolims & everymask)
                for lh_masked in [lo_masked, hi_masked]:
                    # Since this has to work for x and y as dependent data, we
                    # first set both x and y to the independent variable and
                    # overwrite the respective dependent data in a second step.
                    line = mlines.Line2D(indep_masked, indep_masked,
                                         marker=marker, **eb_cap_style)
                    line.set(**{f"{dep_axis}data": lh_masked})
                    caplines[dep_axis].append(line)
            for idx, (lims, hl) in enumerate([(lolims, high), (uplims, low)]):
                if not lims.any():
                    continue
                hlmarker = (
                    himarker
                    if self._axis_map[dep_axis].get_inverted() ^ idx
                    else lomarker)
                x_masked, y_masked, hl_masked = apply_mask(
                    [x, y, hl], lims & everymask)
                # As above, we set the dependent data in a second step.
                line = mlines.Line2D(x_masked, y_masked,
                                     marker=hlmarker, **eb_cap_style)
                line.set(**{f"{dep_axis}data": hl_masked})
                caplines[dep_axis].append(line)
                if capsize > 0:
                    caplines[dep_axis].append(mlines.Line2D(
                        x_masked, y_masked, marker=marker, **eb_cap_style))
        if self.name == 'polar':
            trans_shift = self.transShift
            for axis in caplines:
                for l in caplines[axis]:
                    # Rotate caps to be perpendicular to the error bars
                    for theta, r in zip(l.get_xdata(), l.get_ydata()):
                        rotation = _ScaledRotation(theta=theta, trans_shift=trans_shift)
                        if axis == 'y':
                            rotation += mtransforms.Affine2D().rotate(np.pi / 2)
                        ms = mmarkers.MarkerStyle(marker=marker,
                                                  transform=rotation)
                        self.add_line(mlines.Line2D([theta], [r], marker=ms,
                                                    **eb_cap_style))
        else:
            for axis in caplines:
                for l in caplines[axis]:
                    self.add_line(l)

        self._request_autoscale_view()
        caplines = caplines['x'] + caplines['y']
        errorbar_container = ErrorbarContainer(
            (data_line, tuple(caplines), tuple(barcols)),
            has_xerr=(xerr is not None), has_yerr=(yerr is not None),
            label=label)
        self.add_container(errorbar_container)

        return errorbar_container  # (l0, caplines, barcols)

    @_api.make_keyword_only("3.10", "notch")
    @_preprocess_data()
    @_api.rename_parameter("3.9", "labels", "tick_labels")
    def boxplot(self, x, notch=None, sym=None, vert=None,
                orientation='vertical', whis=None, positions=None,
                widths=None, patch_artist=None, bootstrap=None,
                usermedians=None, conf_intervals=None,
                meanline=None, showmeans=None, showcaps=None,
                showbox=None, showfliers=None, boxprops=None,
                tick_labels=None, flierprops=None, medianprops=None,
                meanprops=None, capprops=None, whiskerprops=None,
                manage_ticks=True, autorange=False, zorder=None,
                capwidths=None, label=None):
        """
        Draw a box and whisker plot.

        The box extends from the first quartile (Q1) to the third
        quartile (Q3) of the data, with a line at the median.
        The whiskers extend from the box to the farthest data point
        lying within 1.5x the inter-quartile range (IQR) from the box.
        Flier points are those past the end of the whiskers.
        See https://en.wikipedia.org/wiki/Box_plot for reference.

        .. code-block:: none

                  Q1-1.5IQR   Q1   median  Q3   Q3+1.5IQR
                               |-----:-----|
               o      |--------|     :     |--------|    o  o
                               |-----:-----|
             flier             <----------->            fliers
                                    IQR


        Parameters
        ----------
        x : Array or a sequence of vectors.
            The input data.  If a 2D array, a boxplot is drawn for each column
            in *x*.  If a sequence of 1D arrays, a boxplot is drawn for each
            array in *x*.

        notch : bool, default: :rc:`boxplot.notch`
            Whether to draw a notched boxplot (`True`), or a rectangular
            boxplot (`False`).  The notches represent the confidence interval
            (CI) around the median.  The documentation for *bootstrap*
            describes how the locations of the notches are computed by
            default, but their locations may also be overridden by setting the
            *conf_intervals* parameter.

            .. note::

                In cases where the values of the CI are less than the
                lower quartile or greater than the upper quartile, the
                notches will extend beyond the box, giving it a
                distinctive "flipped" appearance. This is expected
                behavior and consistent with other statistical
                visualization packages.

        sym : str, optional
            The default symbol for flier points.  An empty string ('') hides
            the fliers.  If `None`, then the fliers default to 'b+'.  More
            control is provided by the *flierprops* parameter.

        vert : bool, optional
            .. deprecated:: 3.11
                Use *orientation* instead.

                This is a pending deprecation for 3.10, with full deprecation
                in 3.11 and removal in 3.13.
                If this is given during the deprecation period, it overrides
                the *orientation* parameter.

            If True, plots the boxes vertically.
            If False, plots the boxes horizontally.

        orientation : {'vertical', 'horizontal'}, default: 'vertical'
            If 'horizontal', plots the boxes horizontally.
            Otherwise, plots the boxes vertically.

            .. versionadded:: 3.10

        whis : float or (float, float), default: 1.5
            The position of the whiskers.

            If a float, the lower whisker is at the lowest datum above
            ``Q1 - whis*(Q3-Q1)``, and the upper whisker at the highest datum
            below ``Q3 + whis*(Q3-Q1)``, where Q1 and Q3 are the first and
            third quartiles.  The default value of ``whis = 1.5`` corresponds
            to Tukey's original definition of boxplots.

            If a pair of floats, they indicate the percentiles at which to
            draw the whiskers (e.g., (5, 95)).  In particular, setting this to
            (0, 100) results in whiskers covering the whole range of the data.

            In the edge case where ``Q1 == Q3``, *whis* is automatically set
            to (0, 100) (cover the whole range of the data) if *autorange* is
            True.

            Beyond the whiskers, data are considered outliers and are plotted
            as individual points.

        bootstrap : int, optional
            Specifies whether to bootstrap the confidence intervals
            around the median for notched boxplots. If *bootstrap* is
            None, no bootstrapping is performed, and notches are
            calculated using a Gaussian-based asymptotic approximation
            (see McGill, R., Tukey, J.W., and Larsen, W.A., 1978, and
            Kendall and Stuart, 1967). Otherwise, bootstrap specifies
            the number of times to bootstrap the median to determine its
            95% confidence intervals. Values between 1000 and 10000 are
            recommended.

        usermedians : 1D array-like, optional
            A 1D array-like of length ``len(x)``.  Each entry that is not
            `None` forces the value of the median for the corresponding
            dataset.  For entries that are `None`, the medians are computed
            by Matplotlib as normal.

        conf_intervals : array-like, optional
            A 2D array-like of shape ``(len(x), 2)``.  Each entry that is not
            None forces the location of the corresponding notch (which is
            only drawn if *notch* is `True`).  For entries that are `None`,
            the notches are computed by the method specified by the other
            parameters (e.g., *bootstrap*).

        positions : array-like, optional
            The positions of the boxes. The ticks and limits are
            automatically set to match the positions. Defaults to
            ``range(1, N+1)`` where N is the number of boxes to be drawn.

        widths : float or array-like
            The widths of the boxes.  The default is 0.5, or ``0.15*(distance
            between extreme positions)``, if that is smaller.

        patch_artist : bool, default: :rc:`boxplot.patchartist`
            If `False` produces boxes with the Line2D artist. Otherwise,
            boxes are drawn with Patch artists.

        tick_labels : list of str, optional
            The tick labels of each boxplot.
            Ticks are always placed at the box *positions*. If *tick_labels* is given,
            the ticks are labelled accordingly. Otherwise, they keep their numeric
            values.

            .. versionchanged:: 3.9
                Renamed from *labels*, which is deprecated since 3.9
                and will be removed in 3.11.

        manage_ticks : bool, default: True
            If True, the tick locations and labels will be adjusted to match
            the boxplot positions.

        autorange : bool, default: False
            When `True` and the data are distributed such that the 25th and
            75th percentiles are equal, *whis* is set to (0, 100) such
            that the whisker ends are at the minimum and maximum of the data.

        meanline : bool, default: :rc:`boxplot.meanline`
            If `True` (and *showmeans* is `True`), will try to render the
            mean as a line spanning the full width of the box according to
            *meanprops* (see below).  Not recommended if *shownotches* is also
            True.  Otherwise, means will be shown as points.

        zorder : float, default: ``Line2D.zorder = 2``
            The zorder of the boxplot.

        Returns
        -------
        dict
          A dictionary mapping each component of the boxplot to a list
          of the `.Line2D` instances created. That dictionary has the
          following keys (assuming vertical boxplots):

          - ``boxes``: the main body of the boxplot showing the
            quartiles and the median's confidence intervals if
            enabled.

          - ``medians``: horizontal lines at the median of each box.

          - ``whiskers``: the vertical lines extending to the most
            extreme, non-outlier data points.

          - ``caps``: the horizontal lines at the ends of the
            whiskers.

          - ``fliers``: points representing data that extend beyond
            the whiskers (fliers).

          - ``means``: points or lines representing the means.

        Other Parameters
        ----------------
        showcaps : bool, default: :rc:`boxplot.showcaps`
            Show the caps on the ends of whiskers.
        showbox : bool, default: :rc:`boxplot.showbox`
            Show the central box.
        showfliers : bool, default: :rc:`boxplot.showfliers`
            Show the outliers beyond the caps.
        showmeans : bool, default: :rc:`boxplot.showmeans`
            Show the arithmetic means.
        capprops : dict, default: None
            The style of the caps.
        capwidths : float or array, default: None
            The widths of the caps.
        boxprops : dict, default: None
            The style of the box.
        whiskerprops : dict, default: None
            The style of the whiskers.
        flierprops : dict, default: None
            The style of the fliers.
        medianprops : dict, default: None
            The style of the median.
        meanprops : dict, default: None
            The style of the mean.
        label : str or list of str, optional
            Legend labels. Use a single string when all boxes have the same style and
            you only want a single legend entry for them. Use a list of strings to
            label all boxes individually. To be distinguishable, the boxes should be
            styled individually, which is currently only possible by modifying the
            returned artists, see e.g. :doc:`/gallery/statistics/boxplot_demo`.

            In the case of a single string, the legend entry will technically be
            associated with the first box only. By default, the legend will show the
            median line (``result["medians"]``); if *patch_artist* is True, the legend
            will show the box `.Patch` artists (``result["boxes"]``) instead.

            .. versionadded:: 3.9

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        See Also
        --------
        .Axes.bxp : Draw a boxplot from pre-computed statistics.
        violinplot : Draw an estimate of the probability density function.
        """

        # Missing arguments default to rcParams.
        if whis is None:
            whis = mpl.rcParams['boxplot.whiskers']
        if bootstrap is None:
            bootstrap = mpl.rcParams['boxplot.bootstrap']

        bxpstats = cbook.boxplot_stats(x, whis=whis, bootstrap=bootstrap,
                                       labels=tick_labels, autorange=autorange)
        if notch is None:
            notch = mpl.rcParams['boxplot.notch']
        if patch_artist is None:
            patch_artist = mpl.rcParams['boxplot.patchartist']
        if meanline is None:
            meanline = mpl.rcParams['boxplot.meanline']
        if showmeans is None:
            showmeans = mpl.rcParams['boxplot.showmeans']
        if showcaps is None:
            showcaps = mpl.rcParams['boxplot.showcaps']
        if showbox is None:
            showbox = mpl.rcParams['boxplot.showbox']
        if showfliers is None:
            showfliers = mpl.rcParams['boxplot.showfliers']

        if boxprops is None:
            boxprops = {}
        if whiskerprops is None:
            whiskerprops = {}
        if capprops is None:
            capprops = {}
        if medianprops is None:
            medianprops = {}
        if meanprops is None:
            meanprops = {}
        if flierprops is None:
            flierprops = {}

        if patch_artist:
            boxprops['linestyle'] = 'solid'  # Not consistent with bxp.
            if 'color' in boxprops:
                boxprops['edgecolor'] = boxprops.pop('color')

        # if non-default sym value, put it into the flier dictionary
        # the logic for providing the default symbol ('b+') now lives
        # in bxp in the initial value of flierkw
        # handle all of the *sym* related logic here so we only have to pass
        # on the flierprops dict.
        if sym is not None:
            # no-flier case, which should really be done with
            # 'showfliers=False' but none-the-less deal with it to keep back
            # compatibility
            if sym == '':
                # blow away existing dict and make one for invisible markers
                flierprops = dict(linestyle='none', marker='', color='none')
                # turn the fliers off just to be safe
                showfliers = False
            # now process the symbol string
            else:
                # process the symbol string
                # discarded linestyle
                _, marker, color = _process_plot_format(sym)
                # if we have a marker, use it
                if marker is not None:
                    flierprops['marker'] = marker
                # if we have a color, use it
                if color is not None:
                    # assume that if color is passed in the user want
                    # filled symbol, if the users want more control use
                    # flierprops
                    flierprops['color'] = color
                    flierprops['markerfacecolor'] = color
                    flierprops['markeredgecolor'] = color

        # replace medians if necessary:
        if usermedians is not None:
            if (len(np.ravel(usermedians)) != len(bxpstats) or
                    np.shape(usermedians)[0] != len(bxpstats)):
                raise ValueError(
                    "'usermedians' and 'x' have different lengths")
            else:
                # reassign medians as necessary
                for stats, med in zip(bxpstats, usermedians):
                    if med is not None:
                        stats['med'] = med

        if conf_intervals is not None:
            if len(conf_intervals) != len(bxpstats):
                raise ValueError(
                    "'conf_intervals' and 'x' have different lengths")
            else:
                for stats, ci in zip(bxpstats, conf_intervals):
                    if ci is not None:
                        if len(ci) != 2:
                            raise ValueError('each confidence interval must '
                                             'have two values')
                        else:
                            if ci[0] is not None:
                                stats['cilo'] = ci[0]
                            if ci[1] is not None:
                                stats['cihi'] = ci[1]

        artists = self.bxp(bxpstats, positions=positions, widths=widths,
                           vert=vert, patch_artist=patch_artist,
                           shownotches=notch, showmeans=showmeans,
                           showcaps=showcaps, showbox=showbox,
                           boxprops=boxprops, flierprops=flierprops,
                           medianprops=medianprops, meanprops=meanprops,
                           meanline=meanline, showfliers=showfliers,
                           capprops=capprops, whiskerprops=whiskerprops,
                           manage_ticks=manage_ticks, zorder=zorder,
                           capwidths=capwidths, label=label,
                           orientation=orientation)
        return artists

    @_api.make_keyword_only("3.10", "widths")
    def bxp(self, bxpstats, positions=None, widths=None, vert=None,
            orientation='vertical', patch_artist=False, shownotches=False,
            showmeans=False, showcaps=True, showbox=True, showfliers=True,
            boxprops=None, whiskerprops=None, flierprops=None,
            medianprops=None, capprops=None, meanprops=None,
            meanline=False, manage_ticks=True, zorder=None,
            capwidths=None, label=None):
        """
        Draw a box and whisker plot from pre-computed statistics.

        The box extends from the first quartile *q1* to the third
        quartile *q3* of the data, with a line at the median (*med*).
        The whiskers extend from *whislow* to *whishi*.
        Flier points are markers past the end of the whiskers.
        See https://en.wikipedia.org/wiki/Box_plot for reference.

        .. code-block:: none

                   whislow    q1    med    q3    whishi
                               |-----:-----|
               o      |--------|     :     |--------|    o  o
                               |-----:-----|
             flier                                      fliers

        .. note::
            This is a low-level drawing function for when you already
            have the statistical parameters. If you want a boxplot based
            on a dataset, use `~.Axes.boxplot` instead.

        Parameters
        ----------
        bxpstats : list of dicts
            A list of dictionaries containing stats for each boxplot.
            Required keys are:

            - ``med``: Median (float).
            - ``q1``, ``q3``: First & third quartiles (float).
            - ``whislo``, ``whishi``: Lower & upper whisker positions (float).

            Optional keys are:

            - ``mean``: Mean (float).  Needed if ``showmeans=True``.
            - ``fliers``: Data beyond the whiskers (array-like).
              Needed if ``showfliers=True``.
            - ``cilo``, ``cihi``: Lower & upper confidence intervals
              about the median. Needed if ``shownotches=True``.
            - ``label``: Name of the dataset (str).  If available,
              this will be used a tick label for the boxplot

        positions : array-like, default: [1, 2, ..., n]
            The positions of the boxes. The ticks and limits
            are automatically set to match the positions.

        widths : float or array-like, default: None
            The widths of the boxes.  The default is
            ``clip(0.15*(distance between extreme positions), 0.15, 0.5)``.

        capwidths : float or array-like, default: None
            Either a scalar or a vector and sets the width of each cap.
            The default is ``0.5*(width of the box)``, see *widths*.

        vert : bool, optional
            .. deprecated:: 3.11
                Use *orientation* instead.

                This is a pending deprecation for 3.10, with full deprecation
                in 3.11 and removal in 3.13.
                If this is given during the deprecation period, it overrides
                the *orientation* parameter.

            If True, plots the boxes vertically.
            If False, plots the boxes horizontally.

        orientation : {'vertical', 'horizontal'}, default: 'vertical'
            If 'horizontal', plots the boxes horizontally.
            Otherwise, plots the boxes vertically.

            .. versionadded:: 3.10

        patch_artist : bool, default: False
            If `False` produces boxes with the `.Line2D` artist.
            If `True` produces boxes with the `~matplotlib.patches.Patch` artist.

        shownotches, showmeans, showcaps, showbox, showfliers : bool
            Whether to draw the CI notches, the mean value (both default to
            False), the caps, the box, and the fliers (all three default to
            True).

        boxprops, whiskerprops, capprops, flierprops, medianprops, meanprops :\
 dict, optional
            Artist properties for the boxes, whiskers, caps, fliers, medians, and
            means.

        meanline : bool, default: False
            If `True` (and *showmeans* is `True`), will try to render the mean
            as a line spanning the full width of the box according to
            *meanprops*. Not recommended if *shownotches* is also True.
            Otherwise, means will be shown as points.

        manage_ticks : bool, default: True
            If True, the tick locations and labels will be adjusted to match the
            boxplot positions.

        label : str or list of str, optional
            Legend labels. Use a single string when all boxes have the same style and
            you only want a single legend entry for them. Use a list of strings to
            label all boxes individually. To be distinguishable, the boxes should be
            styled individually, which is currently only possible by modifying the
            returned artists, see e.g. :doc:`/gallery/statistics/boxplot_demo`.

            In the case of a single string, the legend entry will technically be
            associated with the first box only. By default, the legend will show the
            median line (``result["medians"]``); if *patch_artist* is True, the legend
            will show the box `.Patch` artists (``result["boxes"]``) instead.

            .. versionadded:: 3.9

        zorder : float, default: ``Line2D.zorder = 2``
            The zorder of the resulting boxplot.

        Returns
        -------
        dict
            A dictionary mapping each component of the boxplot to a list
            of the `.Line2D` instances created. That dictionary has the
            following keys (assuming vertical boxplots):

            - ``boxes``: main bodies of the boxplot showing the quartiles, and
              the median's confidence intervals if enabled.
            - ``medians``: horizontal lines at the median of each box.
            - ``whiskers``: vertical lines up to the last non-outlier data.
            - ``caps``: horizontal lines at the ends of the whiskers.
            - ``fliers``: points representing data beyond the whiskers (fliers).
            - ``means``: points or lines representing the means.

        See Also
        --------
        boxplot : Draw a boxplot from data instead of pre-computed statistics.
        """
        # Clamp median line to edge of box by default.
        medianprops = {
            "solid_capstyle": "butt",
            "dash_capstyle": "butt",
            **(medianprops or {}),
        }
        meanprops = {
            "solid_capstyle": "butt",
            "dash_capstyle": "butt",
            **(meanprops or {}),
        }

        # lists of artists to be output
        whiskers = []
        caps = []
        boxes = []
        medians = []
        means = []
        fliers = []

        # empty list of xticklabels
        datalabels = []

        # Use default zorder if none specified
        if zorder is None:
            zorder = mlines.Line2D.zorder

        zdelta = 0.1

        def merge_kw_rc(subkey, explicit, zdelta=0, usemarker=True):
            d = {k.split('.')[-1]: v for k, v in mpl.rcParams.items()
                 if k.startswith(f'boxplot.{subkey}props')}
            d['zorder'] = zorder + zdelta
            if not usemarker:
                d['marker'] = ''
            d.update(cbook.normalize_kwargs(explicit, mlines.Line2D))
            return d

        box_kw = {
            'linestyle': mpl.rcParams['boxplot.boxprops.linestyle'],
            'linewidth': mpl.rcParams['boxplot.boxprops.linewidth'],
            'edgecolor': mpl.rcParams['boxplot.boxprops.color'],
            'facecolor': ('white' if mpl.rcParams['_internal.classic_mode']
                          else mpl.rcParams['patch.facecolor']),
            'zorder': zorder,
            **cbook.normalize_kwargs(boxprops, mpatches.PathPatch)
        } if patch_artist else merge_kw_rc('box', boxprops, usemarker=False)
        whisker_kw = merge_kw_rc('whisker', whiskerprops, usemarker=False)
        cap_kw = merge_kw_rc('cap', capprops, usemarker=False)
        flier_kw = merge_kw_rc('flier', flierprops)
        median_kw = merge_kw_rc('median', medianprops, zdelta, usemarker=False)
        mean_kw = merge_kw_rc('mean', meanprops, zdelta)
        removed_prop = 'marker' if meanline else 'linestyle'
        # Only remove the property if it's not set explicitly as a parameter.
        if meanprops is None or removed_prop not in meanprops:
            mean_kw[removed_prop] = ''

        # vert and orientation parameters are linked until vert's
        # deprecation period expires. vert only takes precedence
        # if set to False.
        if vert is None:
            vert = mpl.rcParams['boxplot.vertical']
        else:
            _api.warn_deprecated(
                "3.11",
                name="vert: bool",
                alternative="orientation: {'vertical', 'horizontal'}",
                pending=True,
            )
        if vert is False:
            orientation = 'horizontal'
        _api.check_in_list(['horizontal', 'vertical'], orientation=orientation)

        if not mpl.rcParams['boxplot.vertical']:
            _api.warn_deprecated(
                "3.10",
                name='boxplot.vertical', obj_type="rcparam"
            )

        # vertical or horizontal plot?
        maybe_swap = slice(None) if orientation == 'vertical' else slice(None, None, -1)

        def do_plot(xs, ys, **kwargs):
            return self.plot(*[xs, ys][maybe_swap], **kwargs)[0]

        def do_patch(xs, ys, **kwargs):
            path = mpath.Path._create_closed(
                np.column_stack([xs, ys][maybe_swap]))
            patch = mpatches.PathPatch(path, **kwargs)
            self.add_artist(patch)
            return patch

        # input validation
        N = len(bxpstats)
        datashape_message = ("List of boxplot statistics and `{0}` "
                             "values must have same the length")
        # check position
        if positions is None:
            positions = list(range(1, N + 1))
        elif len(positions) != N:
            raise ValueError(datashape_message.format("positions"))

        positions = np.array(positions)
        if len(positions) > 0 and not all(isinstance(p, Real) for p in positions):
            raise TypeError("positions should be an iterable of numbers")

        # width
        if widths is None:
            widths = [np.clip(0.15 * np.ptp(positions), 0.15, 0.5)] * N
        elif np.isscalar(widths):
            widths = [widths] * N
        elif len(widths) != N:
            raise ValueError(datashape_message.format("widths"))

        # capwidth
        if capwidths is None:
            capwidths = 0.5 * np.array(widths)
        elif np.isscalar(capwidths):
            capwidths = [capwidths] * N
        elif len(capwidths) != N:
            raise ValueError(datashape_message.format("capwidths"))

        for pos, width, stats, capwidth in zip(positions, widths, bxpstats,
                                               capwidths):
            # try to find a new label
            datalabels.append(stats.get('label', pos))

            # whisker coords
            whis_x = [pos, pos]
            whislo_y = [stats['q1'], stats['whislo']]
            whishi_y = [stats['q3'], stats['whishi']]
            # cap coords
            cap_left = pos - capwidth * 0.5
            cap_right = pos + capwidth * 0.5
            cap_x = [cap_left, cap_right]
            cap_lo = np.full(2, stats['whislo'])
            cap_hi = np.full(2, stats['whishi'])
            # box and median coords
            box_left = pos - width * 0.5
            box_right = pos + width * 0.5
            med_y = [stats['med'], stats['med']]
            # notched boxes
            if shownotches:
                notch_left = pos - width * 0.25
                notch_right = pos + width * 0.25
                box_x = [box_left, box_right, box_right, notch_right,
                         box_right, box_right, box_left, box_left, notch_left,
                         box_left, box_left]
                box_y = [stats['q1'], stats['q1'], stats['cilo'],
                         stats['med'], stats['cihi'], stats['q3'],
                         stats['q3'], stats['cihi'], stats['med'],
                         stats['cilo'], stats['q1']]
                med_x = [notch_left, notch_right]
            # plain boxes
            else:
                box_x = [box_left, box_right, box_right, box_left, box_left]
                box_y = [stats['q1'], stats['q1'], stats['q3'], stats['q3'],
                         stats['q1']]
                med_x = [box_left, box_right]

            # maybe draw the box
            if showbox:
                do_box = do_patch if patch_artist else do_plot
                boxes.append(do_box(box_x, box_y, **box_kw))
                median_kw.setdefault('label', '_nolegend_')
            # draw the whiskers
            whisker_kw.setdefault('label', '_nolegend_')
            whiskers.append(do_plot(whis_x, whislo_y, **whisker_kw))
            whiskers.append(do_plot(whis_x, whishi_y, **whisker_kw))
            # maybe draw the caps
            if showcaps:
                cap_kw.setdefault('label', '_nolegend_')
                caps.append(do_plot(cap_x, cap_lo, **cap_kw))
                caps.append(do_plot(cap_x, cap_hi, **cap_kw))
            # draw the medians
            medians.append(do_plot(med_x, med_y, **median_kw))
            # maybe draw the means
            if showmeans:
                if meanline:
                    means.append(do_plot(
                        [box_left, box_right], [stats['mean'], stats['mean']],
                        **mean_kw
                    ))
                else:
                    means.append(do_plot([pos], [stats['mean']], **mean_kw))
            # maybe draw the fliers
            if showfliers:
                flier_kw.setdefault('label', '_nolegend_')
                flier_x = np.full(len(stats['fliers']), pos, dtype=np.float64)
                flier_y = stats['fliers']
                fliers.append(do_plot(flier_x, flier_y, **flier_kw))

        # Set legend labels
        if label:
            box_or_med = boxes if showbox and patch_artist else medians
            if cbook.is_scalar_or_string(label):
                # assign the label only to the first box
                box_or_med[0].set_label(label)
            else:  # label is a sequence
                if len(box_or_med) != len(label):
                    raise ValueError(datashape_message.format("label"))
                for artist, lbl in zip(box_or_med, label):
                    artist.set_label(lbl)

        if manage_ticks:
            axis_name = "x" if orientation == 'vertical' else "y"
            interval = getattr(self.dataLim, f"interval{axis_name}")
            axis = self._axis_map[axis_name]
            positions = axis.convert_units(positions)
            # The 0.5 additional padding ensures reasonable-looking boxes
            # even when drawing a single box.  We set the sticky edge to
            # prevent margins expansion, in order to match old behavior (back
            # when separate calls to boxplot() would completely reset the axis
            # limits regardless of what was drawn before).  The sticky edges
            # are attached to the median lines, as they are always present.
            interval[:] = (min(interval[0], min(positions) - .5),
                           max(interval[1], max(positions) + .5))
            for median, position in zip(medians, positions):
                getattr(median.sticky_edges, axis_name).extend(
                    [position - .5, position + .5])
            # Modified from Axis.set_ticks and Axis.set_ticklabels.
            locator = axis.get_major_locator()
            if not isinstance(axis.get_major_locator(),
                              mticker.FixedLocator):
                locator = mticker.FixedLocator([])
                axis.set_major_locator(locator)
            locator.locs = np.array([*locator.locs, *positions])
            formatter = axis.get_major_formatter()
            if not isinstance(axis.get_major_formatter(),
                              mticker.FixedFormatter):
                formatter = mticker.FixedFormatter([])
                axis.set_major_formatter(formatter)
            formatter.seq = [*formatter.seq, *datalabels]

            self._request_autoscale_view()

        return dict(whiskers=whiskers, caps=caps, boxes=boxes,
                    medians=medians, fliers=fliers, means=means)

    @staticmethod
    def _parse_scatter_color_args(c, edgecolors, kwargs, xsize,
                                  get_next_color_func):
        """
        Helper function to process color related arguments of `.Axes.scatter`.

        Argument precedence for facecolors:

        - c (if not None)
        - kwargs['facecolor']
        - kwargs['facecolors']
        - kwargs['color'] (==kwcolor)
        - 'b' if in classic mode else the result of ``get_next_color_func()``

        Argument precedence for edgecolors:

        - kwargs['edgecolor']
        - edgecolors (is an explicit kw argument in scatter())
        - kwargs['color'] (==kwcolor)
        - 'face' if not in classic mode else None

        Parameters
        ----------
        c : :mpltype:`color` or array-like or list of :mpltype:`color` or None
            See argument description of `.Axes.scatter`.
        edgecolors : :mpltype:`color` or sequence of color or {'face', 'none'} or None
            See argument description of `.Axes.scatter`.
        kwargs : dict
            Additional kwargs. If these keys exist, we pop and process them:
            'facecolors', 'facecolor', 'edgecolor', 'color'
            Note: The dict is modified by this function.
        xsize : int
            The size of the x and y arrays passed to `.Axes.scatter`.
        get_next_color_func : callable
            A callable that returns a color. This color is used as facecolor
            if no other color is provided.

            Note, that this is a function rather than a fixed color value to
            support conditional evaluation of the next color.  As of the
            current implementation obtaining the next color from the
            property cycle advances the cycle. This must only happen if we
            actually use the color, which will only be decided within this
            method.

        Returns
        -------
        c
            The input *c* if it was not *None*, else a color derived from the
            other inputs or defaults.
        colors : array(N, 4) or None
            The facecolors as RGBA values, or *None* if a colormap is used.
        edgecolors
            The edgecolor.

        """
        facecolors = kwargs.pop('facecolors', None)
        facecolors = kwargs.pop('facecolor', facecolors)
        edgecolors = kwargs.pop('edgecolor', edgecolors)

        kwcolor = kwargs.pop('color', None)

        if kwcolor is not None and c is not None:
            raise ValueError("Supply a 'c' argument or a 'color'"
                             " kwarg but not both; they differ but"
                             " their functionalities overlap.")

        if kwcolor is not None:
            try:
                mcolors.to_rgba_array(kwcolor)
            except ValueError as err:
                raise ValueError(
                    "'color' kwarg must be a color or sequence of color "
                    "specs.  For a sequence of values to be color-mapped, use "
                    "the 'c' argument instead.") from err
            if edgecolors is None:
                edgecolors = kwcolor
            if facecolors is None:
                facecolors = kwcolor

        if edgecolors is None and not mpl.rcParams['_internal.classic_mode']:
            edgecolors = mpl.rcParams['scatter.edgecolors']

        # Raise a warning if both `c` and `facecolor` are set (issue #24404).
        if c is not None and facecolors is not None:
            _api.warn_external(
                "You passed both c and facecolor/facecolors for the markers. "
                "c has precedence over facecolor/facecolors. "
                "This behavior may change in the future."
            )

        c_was_none = c is None
        if c is None:
            c = (facecolors if facecolors is not None
                 else "b" if mpl.rcParams['_internal.classic_mode']
                 else get_next_color_func())
        c_is_string_or_strings = (
            isinstance(c, str)
            or (np.iterable(c) and len(c) > 0
                and isinstance(cbook._safe_first_finite(c), str)))

        def invalid_shape_exception(csize, xsize):
            return ValueError(
                f"'c' argument has {csize} elements, which is inconsistent "
                f"with 'x' and 'y' with size {xsize}.")

        c_is_mapped = False  # Unless proven otherwise below.
        valid_shape = True  # Unless proven otherwise below.
        if not c_was_none and kwcolor is None and not c_is_string_or_strings:
            try:  # First, does 'c' look suitable for value-mapping?
                c = np.asanyarray(c, dtype=float)
            except ValueError:
                pass  # Failed to convert to float array; must be color specs.
            else:
                # handle the documented special case of a 2D array with 1
                # row which as RGB(A) to broadcast.
                if c.shape == (1, 4) or c.shape == (1, 3):
                    c_is_mapped = False
                    if c.size != xsize:
                        valid_shape = False
                # If c can be either mapped values or an RGB(A) color, prefer
                # the former if shapes match, the latter otherwise.
                elif c.size == xsize:
                    c = c.ravel()
                    c_is_mapped = True
                else:  # Wrong size; it must not be intended for mapping.
                    if c.shape in ((3,), (4,)):
                        _api.warn_external(
                            "*c* argument looks like a single numeric RGB or "
                            "RGBA sequence, which should be avoided as value-"
                            "mapping will have precedence in case its length "
                            "matches with *x* & *y*.  Please use the *color* "
                            "keyword-argument or provide a 2D array "
                            "with a single row if you intend to specify "
                            "the same RGB or RGBA value for all points.")
                    valid_shape = False
        if not c_is_mapped:
            try:  # Is 'c' acceptable as PathCollection facecolors?
                colors = mcolors.to_rgba_array(c)
            except (TypeError, ValueError) as err:
                if "RGBA values should be within 0-1 range" in str(err):
                    raise
                else:
                    if not valid_shape:
                        raise invalid_shape_exception(c.size, xsize) from err
                    # Both the mapping *and* the RGBA conversion failed: pretty
                    # severe failure => one may appreciate a verbose feedback.
                    raise ValueError(
                        f"'c' argument must be a color, a sequence of colors, "
                        f"or a sequence of numbers, not {c!r}") from err
            else:
                if len(colors) not in (0, 1, xsize):
                    # NB: remember that a single color is also acceptable.
                    # Besides *colors* will be an empty array if c == 'none'.
                    raise invalid_shape_exception(len(colors), xsize)
        else:
            colors = None  # use cmap, norm after collection is created
        return c, colors, edgecolors

    @_api.make_keyword_only("3.10", "marker")
    @_preprocess_data(replace_names=["x", "y", "s", "linewidths",
                                     "edgecolors", "c", "facecolor",
                                     "facecolors", "color"],
                      label_namer="y")
    @_docstring.interpd
    def scatter(self, x, y, s=None, c=None, marker=None, cmap=None, norm=None,
                vmin=None, vmax=None, alpha=None, linewidths=None, *,
                edgecolors=None, colorizer=None, plotnonfinite=False, **kwargs):
        """
        A scatter plot of *y* vs. *x* with varying marker size and/or color.

        Parameters
        ----------
        x, y : float or array-like, shape (n, )
            The data positions.

        s : float or array-like, shape (n, ), optional
            The marker size in points**2 (typographic points are 1/72 in.).
            Default is ``rcParams['lines.markersize'] ** 2``.

            The linewidth and edgecolor can visually interact with the marker
            size, and can lead to artifacts if the marker size is smaller than
            the linewidth.

            If the linewidth is greater than 0 and the edgecolor is anything
            but *'none'*, then the effective size of the marker will be
            increased by half the linewidth because the stroke will be centered
            on the edge of the shape.

            To eliminate the marker edge either set *linewidth=0* or
            *edgecolor='none'*.

        c : array-like or list of :mpltype:`color` or :mpltype:`color`, optional
            The marker colors. Possible values:

            - A scalar or sequence of n numbers to be mapped to colors using
              *cmap* and *norm*.
            - A 2D array in which the rows are RGB or RGBA.
            - A sequence of colors of length n.
            - A single color format string.

            Note that *c* should not be a single numeric RGB or RGBA sequence
            because that is indistinguishable from an array of values to be
            colormapped. If you want to specify the same RGB or RGBA value for
            all points, use a 2D array with a single row.  Otherwise,
            value-matching will have precedence in case of a size matching with
            *x* and *y*.

            If you wish to specify a single color for all points
            prefer the *color* keyword argument.

            Defaults to `None`. In that case the marker color is determined
            by the value of *color*, *facecolor* or *facecolors*. In case
            those are not specified or `None`, the marker color is determined
            by the next color of the ``Axes``' current "shape and fill" color
            cycle. This cycle defaults to :rc:`axes.prop_cycle`.

        marker : `~.markers.MarkerStyle`, default: :rc:`scatter.marker`
            The marker style. *marker* can be either an instance of the class
            or the text shorthand for a particular marker.
            See :mod:`matplotlib.markers` for more information about marker
            styles.

        %(cmap_doc)s

            This parameter is ignored if *c* is RGB(A).

        %(norm_doc)s

            This parameter is ignored if *c* is RGB(A).

        %(vmin_vmax_doc)s

            This parameter is ignored if *c* is RGB(A).

        alpha : float, default: None
            The alpha blending value, between 0 (transparent) and 1 (opaque).

        linewidths : float or array-like, default: :rc:`lines.linewidth`
            The linewidth of the marker edges. Note: The default *edgecolors*
            is 'face'. You may want to change this as well.

        edgecolors : {'face', 'none', *None*} or :mpltype:`color` or list of \
:mpltype:`color`, default: :rc:`scatter.edgecolors`
            The edge color of the marker. Possible values:

            - 'face': The edge color will always be the same as the face color.
            - 'none': No patch boundary will be drawn.
            - A color or sequence of colors.

            For non-filled markers, *edgecolors* is ignored. Instead, the color
            is determined like with 'face', i.e. from *c*, *colors*, or
            *facecolors*.

        %(colorizer_doc)s

            This parameter is ignored if *c* is RGB(A).

        plotnonfinite : bool, default: False
            Whether to plot points with nonfinite *c* (i.e. ``inf``, ``-inf``
            or ``nan``). If ``True`` the points are drawn with the *bad*
            colormap color (see `.Colormap.set_bad`).

        Returns
        -------
        `~matplotlib.collections.PathCollection`

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER
        **kwargs : `~matplotlib.collections.PathCollection` properties
            %(PathCollection:kwdoc)s

        See Also
        --------
        plot : To plot scatter plots when markers are identical in size and
            color.

        Notes
        -----
        * The `.plot` function will be faster for scatterplots where markers
          don't vary in size or color.

        * Any or all of *x*, *y*, *s*, and *c* may be masked arrays, in which
          case all masks will be combined and only unmasked points will be
          plotted.

        * Fundamentally, scatter works with 1D arrays; *x*, *y*, *s*, and *c*
          may be input as N-D arrays, but within scatter they will be
          flattened. The exception is *c*, which will be flattened only if its
          size matches the size of *x* and *y*.

        """
        # add edgecolors and linewidths to kwargs so they
        # can be processed by normailze_kwargs
        if edgecolors is not None:
            kwargs.update({'edgecolors': edgecolors})
        if linewidths is not None:
            kwargs.update({'linewidths': linewidths})

        kwargs = cbook.normalize_kwargs(kwargs, mcoll.Collection)
        # re direct linewidth and edgecolor so it can be
        # further processed by the rest of the function
        linewidths = kwargs.pop('linewidth', None)
        edgecolors = kwargs.pop('edgecolor', None)
        # Process **kwargs to handle aliases, conflicts with explicit kwargs:
        x, y = self._process_unit_info([("x", x), ("y", y)], kwargs)
        # np.ma.ravel yields an ndarray, not a masked array,
        # unless its argument is a masked array.
        x = np.ma.ravel(x)
        y = np.ma.ravel(y)
        if x.size != y.size:
            raise ValueError("x and y must be the same size")

        if s is None:
            s = (20 if mpl.rcParams['_internal.classic_mode'] else
                 mpl.rcParams['lines.markersize'] ** 2.0)
        s = np.ma.ravel(s)
        if (len(s) not in (1, x.size) or
                (not np.issubdtype(s.dtype, np.floating) and
                 not np.issubdtype(s.dtype, np.integer))):
            raise ValueError(
                "s must be a scalar, "
                "or float array-like with the same size as x and y")

        # get the original edgecolor the user passed before we normalize
        orig_edgecolor = edgecolors
        if edgecolors is None:
            orig_edgecolor = kwargs.get('edgecolor', None)
        c, colors, edgecolors = \
            self._parse_scatter_color_args(
                c, edgecolors, kwargs, x.size,
                get_next_color_func=self._get_patches_for_fill.get_next_color)

        if plotnonfinite and colors is None:
            c = np.ma.masked_invalid(c)
            x, y, s, edgecolors, linewidths = \
                cbook._combine_masks(x, y, s, edgecolors, linewidths)
        else:
            x, y, s, c, colors, edgecolors, linewidths = \
                cbook._combine_masks(
                    x, y, s, c, colors, edgecolors, linewidths)
        # Unmask edgecolors if it was actually a single RGB or RGBA.
        if (x.size in (3, 4)
                and np.ma.is_masked(edgecolors)
                and not np.ma.is_masked(orig_edgecolor)):
            edgecolors = edgecolors.data

        scales = s   # Renamed for readability below.

        # load default marker from rcParams
        if marker is None:
            marker = mpl.rcParams['scatter.marker']

        if isinstance(marker, mmarkers.MarkerStyle):
            marker_obj = marker
        else:
            marker_obj = mmarkers.MarkerStyle(marker)

        path = marker_obj.get_path().transformed(
            marker_obj.get_transform())
        if not marker_obj.is_filled():
            if orig_edgecolor is not None:
                _api.warn_external(
                    f"You passed a edgecolor/edgecolors ({orig_edgecolor!r}) "
                    f"for an unfilled marker ({marker!r}).  Matplotlib is "
                    "ignoring the edgecolor in favor of the facecolor.  This "
                    "behavior may change in the future."
                )
            # We need to handle markers that cannot be filled (like
            # '+' and 'x') differently than markers that can be
            # filled, but have their fillstyle set to 'none'.  This is
            # to get:
            #
            #  - respecting the fillestyle if set
            #  - maintaining back-compatibility for querying the facecolor of
            #    the un-fillable markers.
            #
            # While not an ideal situation, but is better than the
            # alternatives.
            if marker_obj.get_fillstyle() == 'none':
                # promote the facecolor to be the edgecolor
                edgecolors = colors
                # set the facecolor to 'none' (at the last chance) because
                # we cannot fill a path if the facecolor is non-null
                # (which is defendable at the renderer level).
                colors = 'none'
            else:
                # if we are not nulling the face color we can do this
                # simpler
                edgecolors = 'face'

            if linewidths is None:
                linewidths = mpl.rcParams['lines.linewidth']
            elif np.iterable(linewidths):
                linewidths = [
                    lw if lw is not None else mpl.rcParams['lines.linewidth']
                    for lw in linewidths]

        offsets = np.ma.column_stack([x, y])

        collection = mcoll.PathCollection(
            (path,), scales,
            facecolors=colors,
            edgecolors=edgecolors,
            linewidths=linewidths,
            offsets=offsets,
            offset_transform=kwargs.pop('transform', self.transData),
            alpha=alpha,
        )
        collection.set_transform(mtransforms.IdentityTransform())
        if colors is None:
            if colorizer:
                collection._set_colorizer_check_keywords(colorizer, cmap=cmap,
                                                         norm=norm, vmin=vmin,
                                                         vmax=vmax)
            else:
                collection.set_cmap(cmap)
                collection.set_norm(norm)
            collection.set_array(c)
            collection._scale_norm(norm, vmin, vmax)
        else:
            extra_kwargs = {
                    'cmap': cmap, 'norm': norm, 'vmin': vmin, 'vmax': vmax
                    }
            extra_keys = [k for k, v in extra_kwargs.items() if v is not None]
            if any(extra_keys):
                keys_str = ", ".join(f"'{k}'" for k in extra_keys)
                _api.warn_external(
                    "No data for colormapping provided via 'c'. "
                    f"Parameters {keys_str} will be ignored")
        collection._internal_update(kwargs)

        # Classic mode only:
        # ensure there are margins to allow for the
        # finite size of the symbols.  In v2.x, margins
        # are present by default, so we disable this
        # scatter-specific override.
        if mpl.rcParams['_internal.classic_mode']:
            if self._xmargin < 0.05 and x.size > 0:
                self.set_xmargin(0.05)
            if self._ymargin < 0.05 and x.size > 0:
                self.set_ymargin(0.05)

        self.add_collection(collection)
        self._request_autoscale_view()

        return collection

    @_api.make_keyword_only("3.10", "gridsize")
    @_preprocess_data(replace_names=["x", "y", "C"], label_namer="y")
    @_docstring.interpd
    def hexbin(self, x, y, C=None, gridsize=100, bins=None,
               xscale='linear', yscale='linear', extent=None,
               cmap=None, norm=None, vmin=None, vmax=None,
               alpha=None, linewidths=None, edgecolors='face',
               reduce_C_function=np.mean, mincnt=None, marginals=False,
               colorizer=None, **kwargs):
        """
        Make a 2D hexagonal binning plot of points *x*, *y*.

        If *C* is *None*, the value of the hexagon is determined by the number
        of points in the hexagon. Otherwise, *C* specifies values at the
        coordinate (x[i], y[i]). For each hexagon, these values are reduced
        using *reduce_C_function*.

        Parameters
        ----------
        x, y : array-like
            The data positions. *x* and *y* must be of the same length.

        C : array-like, optional
            If given, these values are accumulated in the bins. Otherwise,
            every point has a value of 1. Must be of the same length as *x*
            and *y*.

        gridsize : int or (int, int), default: 100
            If a single int, the number of hexagons in the *x*-direction.
            The number of hexagons in the *y*-direction is chosen such that
            the hexagons are approximately regular.

            Alternatively, if a tuple (*nx*, *ny*), the number of hexagons
            in the *x*-direction and the *y*-direction. In the
            *y*-direction, counting is done along vertically aligned
            hexagons, not along the zig-zag chains of hexagons; see the
            following illustration.

            .. plot::

               import numpy
               import matplotlib.pyplot as plt

               np.random.seed(19680801)
               n= 300
               x = np.random.standard_normal(n)
               y = np.random.standard_normal(n)

               fig, ax = plt.subplots(figsize=(4, 4))
               h = ax.hexbin(x, y, gridsize=(5, 3))
               hx, hy = h.get_offsets().T
               ax.plot(hx[24::3], hy[24::3], 'ro-')
               ax.plot(hx[-3:], hy[-3:], 'ro-')
               ax.set_title('gridsize=(5, 3)')
               ax.axis('off')

            To get approximately regular hexagons, choose
            :math:`n_x = \\sqrt{3}\\,n_y`.

        bins : 'log' or int or sequence, default: None
            Discretization of the hexagon values.

            - If *None*, no binning is applied; the color of each hexagon
              directly corresponds to its count value.
            - If 'log', use a logarithmic scale for the colormap.
              Internally, :math:`log_{10}(i+1)` is used to determine the
              hexagon color. This is equivalent to ``norm=LogNorm()``.
            - If an integer, divide the counts in the specified number
              of bins, and color the hexagons accordingly.
            - If a sequence of values, the values of the lower bound of
              the bins to be used.

        xscale : {'linear', 'log'}, default: 'linear'
            Use a linear or log10 scale on the horizontal axis.

        yscale : {'linear', 'log'}, default: 'linear'
            Use a linear or log10 scale on the vertical axis.

        mincnt : int >= 0, default: *None*
            If not *None*, only display cells with at least *mincnt*
            number of points in the cell.

        marginals : bool, default: *False*
            If marginals is *True*, plot the marginal density as
            colormapped rectangles along the bottom of the x-axis and
            left of the y-axis.

        extent : 4-tuple of float, default: *None*
            The limits of the bins (xmin, xmax, ymin, ymax).
            The default assigns the limits based on
            *gridsize*, *x*, *y*, *xscale* and *yscale*.

            If *xscale* or *yscale* is set to 'log', the limits are
            expected to be the exponent for a power of 10. E.g. for
            x-limits of 1 and 50 in 'linear' scale and y-limits
            of 10 and 1000 in 'log' scale, enter (1, 50, 1, 3).

        Returns
        -------
        `~matplotlib.collections.PolyCollection`
            A `.PolyCollection` defining the hexagonal bins.

            - `.PolyCollection.get_offsets` contains a Mx2 array containing
              the x, y positions of the M hexagon centers in data coordinates.
            - `.PolyCollection.get_array` contains the values of the M
              hexagons.

            If *marginals* is *True*, horizontal
            bar and vertical bar (both PolyCollections) will be attached
            to the return collection as attributes *hbar* and *vbar*.

        Other Parameters
        ----------------
        %(cmap_doc)s

        %(norm_doc)s

        %(vmin_vmax_doc)s

        alpha : float between 0 and 1, optional
            The alpha blending value, between 0 (transparent) and 1 (opaque).

        linewidths : float, default: *None*
            If *None*, defaults to :rc:`patch.linewidth`.

        edgecolors : {'face', 'none', *None*} or color, default: 'face'
            The color of the hexagon edges. Possible values are:

            - 'face': Draw the edges in the same color as the fill color.
            - 'none': No edges are drawn. This can sometimes lead to unsightly
              unpainted pixels between the hexagons.
            - *None*: Draw outlines in the default color.
            - An explicit color.

        reduce_C_function : callable, default: `numpy.mean`
            The function to aggregate *C* within the bins. It is ignored if
            *C* is not given. This must have the signature::

                def reduce_C_function(C: array) -> float

            Commonly used functions are:

            - `numpy.mean`: average of the points
            - `numpy.sum`: integral of the point values
            - `numpy.amax`: value taken from the largest point

            By default will only reduce cells with at least 1 point because some
            reduction functions (such as `numpy.amax`) will error/warn with empty
            input. Changing *mincnt* will adjust the cutoff, and if set to 0 will
            pass empty input to the reduction function.

        %(colorizer_doc)s

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs : `~matplotlib.collections.PolyCollection` properties
            All other keyword arguments are passed on to `.PolyCollection`:

            %(PolyCollection:kwdoc)s

        See Also
        --------
        hist2d : 2D histogram rectangular bins
        """
        self._process_unit_info([("x", x), ("y", y)], kwargs, convert=False)

        x, y, C = cbook.delete_masked_points(x, y, C)

        # Set the size of the hexagon grid
        if np.iterable(gridsize):
            nx, ny = gridsize
        else:
            nx = gridsize
            ny = int(nx / math.sqrt(3))
        # Count the number of data in each hexagon
        x = np.asarray(x, float)
        y = np.asarray(y, float)

        # Will be log()'d if necessary, and then rescaled.
        tx = x
        ty = y

        if xscale == 'log':
            if np.any(x <= 0.0):
                raise ValueError(
                    "x contains non-positive values, so cannot be log-scaled")
            tx = np.log10(tx)
        if yscale == 'log':
            if np.any(y <= 0.0):
                raise ValueError(
                    "y contains non-positive values, so cannot be log-scaled")
            ty = np.log10(ty)
        if extent is not None:
            xmin, xmax, ymin, ymax = extent
            if xmin > xmax:
                raise ValueError("In extent, xmax must be greater than xmin")
            if ymin > ymax:
                raise ValueError("In extent, ymax must be greater than ymin")
        else:
            xmin, xmax = (tx.min(), tx.max()) if len(x) else (0, 1)
            ymin, ymax = (ty.min(), ty.max()) if len(y) else (0, 1)

            # to avoid issues with singular data, expand the min/max pairs
            xmin, xmax = mtransforms.nonsingular(xmin, xmax, expander=0.1)
            ymin, ymax = mtransforms.nonsingular(ymin, ymax, expander=0.1)

        nx1 = nx + 1
        ny1 = ny + 1
        nx2 = nx
        ny2 = ny
        n = nx1 * ny1 + nx2 * ny2

        # In the x-direction, the hexagons exactly cover the region from
        # xmin to xmax. Need some padding to avoid roundoff errors.
        padding = 1.e-9 * (xmax - xmin)
        xmin -= padding
        xmax += padding
        sx = (xmax - xmin) / nx
        sy = (ymax - ymin) / ny
        # Positions in hexagon index coordinates.
        ix = (tx - xmin) / sx
        iy = (ty - ymin) / sy
        ix1 = np.round(ix).astype(int)
        iy1 = np.round(iy).astype(int)
        ix2 = np.floor(ix).astype(int)
        iy2 = np.floor(iy).astype(int)
        # flat indices, plus one so that out-of-range points go to position 0.
        i1 = np.where((0 <= ix1) & (ix1 < nx1) & (0 <= iy1) & (iy1 < ny1),
                      ix1 * ny1 + iy1 + 1, 0)
        i2 = np.where((0 <= ix2) & (ix2 < nx2) & (0 <= iy2) & (iy2 < ny2),
                      ix2 * ny2 + iy2 + 1, 0)

        d1 = (ix - ix1) ** 2 + 3.0 * (iy - iy1) ** 2
        d2 = (ix - ix2 - 0.5) ** 2 + 3.0 * (iy - iy2 - 0.5) ** 2
        bdist = (d1 < d2)

        if C is None:  # [1:] drops out-of-range points.
            counts1 = np.bincount(i1[bdist], minlength=1 + nx1 * ny1)[1:]
            counts2 = np.bincount(i2[~bdist], minlength=1 + nx2 * ny2)[1:]
            accum = np.concatenate([counts1, counts2]).astype(float)
            if mincnt is not None:
                accum[accum < mincnt] = np.nan
            C = np.ones(len(x))
        else:
            # store the C values in a list per hexagon index
            Cs_at_i1 = [[] for _ in range(1 + nx1 * ny1)]
            Cs_at_i2 = [[] for _ in range(1 + nx2 * ny2)]
            for i in range(len(x)):
                if bdist[i]:
                    Cs_at_i1[i1[i]].append(C[i])
                else:
                    Cs_at_i2[i2[i]].append(C[i])
            if mincnt is None:
                mincnt = 1
            accum = np.array(
                [reduce_C_function(acc) if len(acc) >= mincnt else np.nan
                 for Cs_at_i in [Cs_at_i1, Cs_at_i2]
                 for acc in Cs_at_i[1:]],  # [1:] drops out-of-range points.
                float)

        good_idxs = ~np.isnan(accum)

        offsets = np.zeros((n, 2), float)
        offsets[:nx1 * ny1, 0] = np.repeat(np.arange(nx1), ny1)
        offsets[:nx1 * ny1, 1] = np.tile(np.arange(ny1), nx1)
        offsets[nx1 * ny1:, 0] = np.repeat(np.arange(nx2) + 0.5, ny2)
        offsets[nx1 * ny1:, 1] = np.tile(np.arange(ny2), nx2) + 0.5
        offsets[:, 0] *= sx
        offsets[:, 1] *= sy
        offsets[:, 0] += xmin
        offsets[:, 1] += ymin
        # remove accumulation bins with no data
        offsets = offsets[good_idxs, :]
        accum = accum[good_idxs]

        polygon = [sx, sy / 3] * np.array(
            [[.5, -.5], [.5, .5], [0., 1.], [-.5, .5], [-.5, -.5], [0., -1.]])

        if linewidths is None:
            linewidths = [mpl.rcParams['patch.linewidth']]

        if xscale == 'log' or yscale == 'log':
            polygons = np.expand_dims(polygon, 0)
            if xscale == 'log':
                polygons[:, :, 0] = 10.0 ** polygons[:, :, 0]
                xmin = 10.0 ** xmin
                xmax = 10.0 ** xmax
                self.set_xscale(xscale)
            if yscale == 'log':
                polygons[:, :, 1] = 10.0 ** polygons[:, :, 1]
                ymin = 10.0 ** ymin
                ymax = 10.0 ** ymax
                self.set_yscale(yscale)
        else:
            polygons = [polygon]

        collection = mcoll.PolyCollection(
            polygons,
            edgecolors=edgecolors,
            linewidths=linewidths,
            offsets=offsets,
            offset_transform=mtransforms.AffineDeltaTransform(self.transData)
        )

        # Set normalizer if bins is 'log'
        if cbook._str_equal(bins, 'log'):
            if norm is not None:
                _api.warn_external("Only one of 'bins' and 'norm' arguments "
                                   f"can be supplied, ignoring {bins=}")
            else:
                norm = mcolors.LogNorm(vmin=vmin, vmax=vmax)
                vmin = vmax = None
            bins = None

        if bins is not None:
            if not np.iterable(bins):
                minimum, maximum = min(accum), max(accum)
                bins -= 1  # one less edge than bins
                bins = minimum + (maximum - minimum) * np.arange(bins) / bins
            bins = np.sort(bins)
            accum = bins.searchsorted(accum)

        if colorizer:
            collection._set_colorizer_check_keywords(colorizer, cmap=cmap,
                                                     norm=norm, vmin=vmin,
                                                     vmax=vmax)
        else:
            collection.set_cmap(cmap)
            collection.set_norm(norm)
        collection.set_array(accum)
        collection.set_alpha(alpha)
        collection._internal_update(kwargs)
        collection._scale_norm(norm, vmin, vmax)

        # autoscale the norm with current accum values if it hasn't been set
        if norm is not None:
            if collection.norm.vmin is None and collection.norm.vmax is None:
                collection.norm.autoscale()

        corners = ((xmin, ymin), (xmax, ymax))
        self.update_datalim(corners)
        self._request_autoscale_view(tight=True)

        # add the collection last
        self.add_collection(collection, autolim=False)
        if not marginals:
            return collection

        # Process marginals
        bars = []
        for zname, z, zmin, zmax, zscale, nbins in [
                ("x", x, xmin, xmax, xscale, nx),
                ("y", y, ymin, ymax, yscale, 2 * ny),
        ]:

            if zscale == "log":
                bin_edges = np.geomspace(zmin, zmax, nbins + 1)
            else:
                bin_edges = np.linspace(zmin, zmax, nbins + 1)

            verts = np.empty((nbins, 4, 2))
            verts[:, 0, 0] = verts[:, 1, 0] = bin_edges[:-1]
            verts[:, 2, 0] = verts[:, 3, 0] = bin_edges[1:]
            verts[:, 0, 1] = verts[:, 3, 1] = .00
            verts[:, 1, 1] = verts[:, 2, 1] = .05
            if zname == "y":
                verts = verts[:, :, ::-1]  # Swap x and y.

            # Sort z-values into bins defined by bin_edges.
            bin_idxs = np.searchsorted(bin_edges, z) - 1
            values = np.empty(nbins)
            for i in range(nbins):
                # Get C-values for each bin, and compute bin value with
                # reduce_C_function.
                ci = C[bin_idxs == i]
                values[i] = reduce_C_function(ci) if len(ci) > 0 else np.nan

            mask = ~np.isnan(values)
            verts = verts[mask]
            values = values[mask]

            trans = getattr(self, f"get_{zname}axis_transform")(which="grid")
            bar = mcoll.PolyCollection(
                verts, transform=trans, edgecolors="face")
            bar.set_array(values)
            bar.set_cmap(cmap)
            bar.set_norm(norm)
            bar.set_alpha(alpha)
            bar._internal_update(kwargs)
            bars.append(self.add_collection(bar, autolim=False))

        collection.hbar, collection.vbar = bars

        def on_changed(collection):
            collection.hbar.set_cmap(collection.get_cmap())
            collection.hbar.set_cmap(collection.get_cmap())
            collection.vbar.set_clim(collection.get_clim())
            collection.vbar.set_clim(collection.get_clim())

        collection.callbacks.connect('changed', on_changed)

        return collection

    @_docstring.interpd
    def arrow(self, x, y, dx, dy, **kwargs):
        """
        [*Discouraged*] Add an arrow to the Axes.

        This draws an arrow from ``(x, y)`` to ``(x+dx, y+dy)``.

        .. admonition:: Discouraged

            The use of this method is discouraged because it is not guaranteed
            that the arrow renders reasonably. For example, the resulting arrow
            is affected by the Axes aspect ratio and limits, which may distort
            the arrow.

            Consider using `~.Axes.annotate` without a text instead, e.g. ::

                ax.annotate("", xytext=(0, 0), xy=(0.5, 0.5),
                            arrowprops=dict(arrowstyle="->"))

        Parameters
        ----------
        %(FancyArrow)s

        Returns
        -------
        `.FancyArrow`
            The created `.FancyArrow` object.
        """
        # Strip away units for the underlying patch since units
        # do not make sense to most patch-like code
        x = self.convert_xunits(x)
        y = self.convert_yunits(y)
        dx = self.convert_xunits(dx)
        dy = self.convert_yunits(dy)

        a = mpatches.FancyArrow(x, y, dx, dy, **kwargs)
        self.add_patch(a)
        self._request_autoscale_view()
        return a

    @_docstring.copy(mquiver.QuiverKey.__init__)
    def quiverkey(self, Q, X, Y, U, label, **kwargs):
        qk = mquiver.QuiverKey(Q, X, Y, U, label, **kwargs)
        self.add_artist(qk)
        return qk

    # Handle units for x and y, if they've been passed
    def _quiver_units(self, args, kwargs):
        if len(args) > 3:
            x, y = args[0:2]
            x, y = self._process_unit_info([("x", x), ("y", y)], kwargs)
            return (x, y) + args[2:]
        return args

    # args can be a combination of X, Y, U, V, C and all should be replaced
    @_preprocess_data()
    @_docstring.interpd
    def quiver(self, *args, **kwargs):
        """%(quiver_doc)s"""
        # Make sure units are handled for x and y values
        args = self._quiver_units(args, kwargs)
        q = mquiver.Quiver(self, *args, **kwargs)
        self.add_collection(q, autolim=True)
        self._request_autoscale_view()
        return q

    # args can be some combination of X, Y, U, V, C and all should be replaced
    @_preprocess_data()
    @_docstring.interpd
    def barbs(self, *args, **kwargs):
        """%(barbs_doc)s"""
        # Make sure units are handled for x and y values
        args = self._quiver_units(args, kwargs)
        b = mquiver.Barbs(self, *args, **kwargs)
        self.add_collection(b, autolim=True)
        self._request_autoscale_view()
        return b

    # Uses a custom implementation of data-kwarg handling in
    # _process_plot_var_args.
    def fill(self, *args, data=None, **kwargs):
        """
        Plot filled polygons.

        Parameters
        ----------
        *args : sequence of x, y, [color]
            Each polygon is defined by the lists of *x* and *y* positions of
            its nodes, optionally followed by a *color* specifier. See
            :mod:`matplotlib.colors` for supported color specifiers. The
            standard color cycle is used for polygons without a color
            specifier.

            You can plot multiple polygons by providing multiple *x*, *y*,
            *[color]* groups.

            For example, each of the following is legal::

                ax.fill(x, y)                    # a polygon with default color
                ax.fill(x, y, "b")               # a blue polygon
                ax.fill(x, y, x2, y2)            # two polygons
                ax.fill(x, y, "b", x2, y2, "r")  # a blue and a red polygon

        data : indexable object, optional
            An object with labelled data. If given, provide the label names to
            plot in *x* and *y*, e.g.::

                ax.fill("time", "signal",
                        data={"time": [0, 1, 2], "signal": [0, 1, 0]})

        Returns
        -------
        list of `~matplotlib.patches.Polygon`

        Other Parameters
        ----------------
        **kwargs : `~matplotlib.patches.Polygon` properties

        Notes
        -----
        Use :meth:`fill_between` if you would like to fill the region between
        two curves.
        """
        # For compatibility(!), get aliases from Line2D rather than Patch.
        kwargs = cbook.normalize_kwargs(kwargs, mlines.Line2D)
        # _get_patches_for_fill returns a generator, convert it to a list.
        patches = [*self._get_patches_for_fill(self, *args, data=data, **kwargs)]
        for poly in patches:
            self.add_patch(poly)
        self._request_autoscale_view()
        return patches

    def _fill_between_x_or_y(
            self, ind_dir, ind, dep1, dep2=0, *,
            where=None, interpolate=False, step=None, **kwargs):
        # Common implementation between fill_between (*ind_dir*="x") and
        # fill_betweenx (*ind_dir*="y").  *ind* is the independent variable,
        # *dep* the dependent variable.  The docstring below is interpolated
        # to generate both methods' docstrings.
        """
        Fill the area between two {dir} curves.

        The curves are defined by the points (*{ind}*, *{dep}1*) and (*{ind}*,
        *{dep}2*).  This creates one or multiple polygons describing the filled
        area.

        You may exclude some {dir} sections from filling using *where*.

        By default, the edges connect the given points directly.  Use *step*
        if the filling should be a step function, i.e. constant in between
        *{ind}*.

        Parameters
        ----------
        {ind} : array-like
            The {ind} coordinates of the nodes defining the curves.

        {dep}1 : array-like or float
            The {dep} coordinates of the nodes defining the first curve.

        {dep}2 : array-like or float, default: 0
            The {dep} coordinates of the nodes defining the second curve.

        where : array-like of bool, optional
            Define *where* to exclude some {dir} regions from being filled.
            The filled regions are defined by the coordinates ``{ind}[where]``.
            More precisely, fill between ``{ind}[i]`` and ``{ind}[i+1]`` if
            ``where[i] and where[i+1]``.  Note that this definition implies
            that an isolated *True* value between two *False* values in *where*
            will not result in filling.  Both sides of the *True* position
            remain unfilled due to the adjacent *False* values.

        interpolate : bool, default: False
            This option is only relevant if *where* is used and the two curves
            are crossing each other.

            Semantically, *where* is often used for *{dep}1* > *{dep}2* or
            similar.  By default, the nodes of the polygon defining the filled
            region will only be placed at the positions in the *{ind}* array.
            Such a polygon cannot describe the above semantics close to the
            intersection.  The {ind}-sections containing the intersection are
            simply clipped.

            Setting *interpolate* to *True* will calculate the actual
            intersection point and extend the filled region up to this point.

        step : {{'pre', 'post', 'mid'}}, optional
            Define *step* if the filling should be a step function,
            i.e. constant in between *{ind}*.  The value determines where the
            step will occur:

            - 'pre': The {dep} value is continued constantly to the left from
              every *{ind}* position, i.e. the interval ``({ind}[i-1], {ind}[i]]``
              has the value ``{dep}[i]``.
            - 'post': The y value is continued constantly to the right from
              every *{ind}* position, i.e. the interval ``[{ind}[i], {ind}[i+1])``
              has the value ``{dep}[i]``.
            - 'mid': Steps occur half-way between the *{ind}* positions.

        Returns
        -------
        `.FillBetweenPolyCollection`
            A `.FillBetweenPolyCollection` containing the plotted polygons.

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            All other keyword arguments are passed on to
            `.FillBetweenPolyCollection`. They control the `.Polygon` properties:

            %(FillBetweenPolyCollection:kwdoc)s

        See Also
        --------
        fill_between : Fill between two sets of y-values.
        fill_betweenx : Fill between two sets of x-values.
        """
        dep_dir = mcoll.FillBetweenPolyCollection._f_dir_from_t(ind_dir)

        if not mpl.rcParams["_internal.classic_mode"]:
            kwargs = cbook.normalize_kwargs(kwargs, mcoll.Collection)
            if not any(c in kwargs for c in ("color", "facecolor")):
                kwargs["facecolor"] = self._get_patches_for_fill.get_next_color()

        ind, dep1, dep2 = self._fill_between_process_units(
            ind_dir, dep_dir, ind, dep1, dep2, **kwargs)

        collection = mcoll.FillBetweenPolyCollection(
            ind_dir, ind, dep1, dep2,
            where=where, interpolate=interpolate, step=step, **kwargs)

        self.add_collection(collection)
        self._request_autoscale_view()
        return collection

    def _fill_between_process_units(self, ind_dir, dep_dir, ind, dep1, dep2, **kwargs):
        """Handle united data, such as dates."""
        return map(np.ma.masked_invalid, self._process_unit_info(
            [(ind_dir, ind), (dep_dir, dep1), (dep_dir, dep2)], kwargs))

    def fill_between(self, x, y1, y2=0, where=None, interpolate=False,
                     step=None, **kwargs):
        return self._fill_between_x_or_y(
            "x", x, y1, y2,
            where=where, interpolate=interpolate, step=step, **kwargs)

    if _fill_between_x_or_y.__doc__:
        fill_between.__doc__ = _fill_between_x_or_y.__doc__.format(
            dir="horizontal", ind="x", dep="y"
        )
    fill_between = _preprocess_data(
        _docstring.interpd(fill_between),
        replace_names=["x", "y1", "y2", "where"])

    def fill_betweenx(self, y, x1, x2=0, where=None,
                      step=None, interpolate=False, **kwargs):
        return self._fill_between_x_or_y(
            "y", y, x1, x2,
            where=where, interpolate=interpolate, step=step, **kwargs)

    if _fill_between_x_or_y.__doc__:
        fill_betweenx.__doc__ = _fill_between_x_or_y.__doc__.format(
            dir="vertical", ind="y", dep="x"
        )
    fill_betweenx = _preprocess_data(
        _docstring.interpd(fill_betweenx),
        replace_names=["y", "x1", "x2", "where"])

    #### plotting z(x, y): imshow, pcolor and relatives, contour

    @_preprocess_data()
    @_docstring.interpd
    def imshow(self, X, cmap=None, norm=None, *, aspect=None,
               interpolation=None, alpha=None,
               vmin=None, vmax=None, colorizer=None, origin=None, extent=None,
               interpolation_stage=None, filternorm=True, filterrad=4.0,
               resample=None, url=None, **kwargs):
        """
        Display data as an image, i.e., on a 2D regular raster.

        The input may either be actual RGB(A) data, or 2D scalar data, which
        will be rendered as a pseudocolor image. For displaying a grayscale
        image, set up the colormapping using the parameters
        ``cmap='gray', vmin=0, vmax=255``.

        The number of pixels used to render an image is set by the Axes size
        and the figure *dpi*. This can lead to aliasing artifacts when
        the image is resampled, because the displayed image size will usually
        not match the size of *X* (see
        :doc:`/gallery/images_contours_and_fields/image_antialiasing`).
        The resampling can be controlled via the *interpolation* parameter
        and/or :rc:`image.interpolation`.

        Parameters
        ----------
        X : array-like or PIL image
            The image data. Supported array shapes are:

            - (M, N): an image with scalar data. The values are mapped to
              colors using normalization and a colormap. See parameters *norm*,
              *cmap*, *vmin*, *vmax*.
            - (M, N, 3): an image with RGB values (0-1 float or 0-255 int).
            - (M, N, 4): an image with RGBA values (0-1 float or 0-255 int),
              i.e. including transparency.

            The first two dimensions (M, N) define the rows and columns of
            the image.

            Out-of-range RGB(A) values are clipped.

        %(cmap_doc)s

            This parameter is ignored if *X* is RGB(A).

        %(norm_doc)s

            This parameter is ignored if *X* is RGB(A).

        %(vmin_vmax_doc)s

            This parameter is ignored if *X* is RGB(A).

        %(colorizer_doc)s

            This parameter is ignored if *X* is RGB(A).

        aspect : {'equal', 'auto'} or float or None, default: None
            The aspect ratio of the Axes.  This parameter is particularly
            relevant for images since it determines whether data pixels are
            square.

            This parameter is a shortcut for explicitly calling
            `.Axes.set_aspect`. See there for further details.

            - 'equal': Ensures an aspect ratio of 1. Pixels will be square
              (unless pixel sizes are explicitly made non-square in data
              coordinates using *extent*).
            - 'auto': The Axes is kept fixed and the aspect is adjusted so
              that the data fit in the Axes. In general, this will result in
              non-square pixels.

            Normally, None (the default) means to use :rc:`image.aspect`.  However, if
            the image uses a transform that does not contain the axes data transform,
            then None means to not modify the axes aspect at all (in that case, directly
            call `.Axes.set_aspect` if desired).

        interpolation : str, default: :rc:`image.interpolation`
            The interpolation method used.

            Supported values are 'none', 'auto', 'nearest', 'bilinear',
            'bicubic', 'spline16', 'spline36', 'hanning', 'hamming', 'hermite',
            'kaiser', 'quadric', 'catrom', 'gaussian', 'bessel', 'mitchell',
            'sinc', 'lanczos', 'blackman'.

            The data *X* is resampled to the pixel size of the image on the
            figure canvas, using the interpolation method to either up- or
            downsample the data.

            If *interpolation* is 'none', then for the ps, pdf, and svg
            backends no down- or upsampling occurs, and the image data is
            passed to the backend as a native image.  Note that different ps,
            pdf, and svg viewers may display these raw pixels differently. On
            other backends, 'none' is the same as 'nearest'.

            If *interpolation* is the default 'auto', then 'nearest'
            interpolation is used if the image is upsampled by more than a
            factor of three (i.e. the number of display pixels is at least
            three times the size of the data array).  If the upsampling rate is
            smaller than 3, or the image is downsampled, then 'hanning'
            interpolation is used to act as an anti-aliasing filter, unless the
            image happens to be upsampled by exactly a factor of two or one.

            See
            :doc:`/gallery/images_contours_and_fields/interpolation_methods`
            for an overview of the supported interpolation methods, and
            :doc:`/gallery/images_contours_and_fields/image_antialiasing` for
            a discussion of image antialiasing.

            Some interpolation methods require an additional radius parameter,
            which can be set by *filterrad*. Additionally, the antigrain image
            resize filter is controlled by the parameter *filternorm*.

        interpolation_stage : {'auto', 'data', 'rgba'}, default: 'auto'
            Supported values:

            - 'data': Interpolation is carried out on the data provided by the user
              This is useful if interpolating between pixels during upsampling.
            - 'rgba': The interpolation is carried out in RGBA-space after the
              color-mapping has been applied. This is useful if downsampling and
              combining pixels visually.
            - 'auto': Select a suitable interpolation stage automatically. This uses
              'rgba' when downsampling, or upsampling at a rate less than 3, and
              'data' when upsampling at a higher rate.

            See :doc:`/gallery/images_contours_and_fields/image_antialiasing` for
            a discussion of image antialiasing.

        alpha : float or array-like, optional
            The alpha blending value, between 0 (transparent) and 1 (opaque).
            If *alpha* is an array, the alpha blending values are applied pixel
            by pixel, and *alpha* must have the same shape as *X*.

        origin : {'upper', 'lower'}, default: :rc:`image.origin`
            Place the [0, 0] index of the array in the upper left or lower
            left corner of the Axes. The convention (the default) 'upper' is
            typically used for matrices and images.

            Note that the vertical axis points upward for 'lower'
            but downward for 'upper'.

            See the :ref:`imshow_extent` tutorial for
            examples and a more detailed description.

        extent : floats (left, right, bottom, top), optional
            The bounding box in data coordinates that the image will fill.
            These values may be unitful and match the units of the Axes.
            The image is stretched individually along x and y to fill the box.

            The default extent is determined by the following conditions.
            Pixels have unit size in data coordinates. Their centers are on
            integer coordinates, and their center coordinates range from 0 to
            columns-1 horizontally and from 0 to rows-1 vertically.

            Note that the direction of the vertical axis and thus the default
            values for top and bottom depend on *origin*:

            - For ``origin == 'upper'`` the default is
              ``(-0.5, numcols-0.5, numrows-0.5, -0.5)``.
            - For ``origin == 'lower'`` the default is
              ``(-0.5, numcols-0.5, -0.5, numrows-0.5)``.

            See the :ref:`imshow_extent` tutorial for
            examples and a more detailed description.

        filternorm : bool, default: True
            A parameter for the antigrain image resize filter (see the
            antigrain documentation).  If *filternorm* is set, the filter
            normalizes integer values and corrects the rounding errors. It
            doesn't do anything with the source floating point values, it
            corrects only integers according to the rule of 1.0 which means
            that any sum of pixel weights must be equal to 1.0.  So, the
            filter function must produce a graph of the proper shape.

        filterrad : float > 0, default: 4.0
            The filter radius for filters that have a radius parameter, i.e.
            when interpolation is one of: 'sinc', 'lanczos' or 'blackman'.

        resample : bool, default: :rc:`image.resample`
            When *True*, use a full resampling method.  When *False*, only
            resample when the output image is larger than the input image.

        url : str, optional
            Set the url of the created `.AxesImage`. See `.Artist.set_url`.

        Returns
        -------
        `~matplotlib.image.AxesImage`

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs : `~matplotlib.artist.Artist` properties
            These parameters are passed on to the constructor of the
            `.AxesImage` artist.

        See Also
        --------
        matshow : Plot a matrix or an array as an image.

        Notes
        -----
        Unless *extent* is used, pixel centers will be located at integer
        coordinates. In other words: the origin will coincide with the center
        of pixel (0, 0).

        There are two common representations for RGB images with an alpha
        channel:

        -   Straight (unassociated) alpha: R, G, and B channels represent the
            color of the pixel, disregarding its opacity.
        -   Premultiplied (associated) alpha: R, G, and B channels represent
            the color of the pixel, adjusted for its opacity by multiplication.

        `~matplotlib.pyplot.imshow` expects RGB images adopting the straight
        (unassociated) alpha representation.
        """
        im = mimage.AxesImage(self, cmap=cmap, norm=norm, colorizer=colorizer,
                              interpolation=interpolation, origin=origin,
                              extent=extent, filternorm=filternorm,
                              filterrad=filterrad, resample=resample,
                              interpolation_stage=interpolation_stage,
                              **kwargs)

        if aspect is None and not (
                im.is_transform_set()
                and not im.get_transform().contains_branch(self.transData)):
            aspect = mpl.rcParams['image.aspect']
        if aspect is not None:
            self.set_aspect(aspect)

        im.set_data(X)
        im.set_alpha(alpha)
        if im.get_clip_path() is None:
            # image does not already have clipping set, clip to Axes patch
            im.set_clip_path(self.patch)
        im._check_exclusionary_keywords(colorizer, vmin=vmin, vmax=vmax)
        im._scale_norm(norm, vmin, vmax)
        im.set_url(url)

        # update ax.dataLim, and, if autoscaling, set viewLim
        # to tightly fit the image, regardless of dataLim.
        im.set_extent(im.get_extent())

        self.add_image(im)
        return im

    def _pcolorargs(self, funcname, *args, shading='auto', **kwargs):
        # - create X and Y if not present;
        # - reshape X and Y as needed if they are 1-D;
        # - check for proper sizes based on `shading` kwarg;
        # - reset shading if shading='auto' to flat or nearest
        #   depending on size;

        _valid_shading = ['gouraud', 'nearest', 'flat', 'auto']
        try:
            _api.check_in_list(_valid_shading, shading=shading)
        except ValueError:
            _api.warn_external(f"shading value '{shading}' not in list of "
                               f"valid values {_valid_shading}. Setting "
                               "shading='auto'.")
            shading = 'auto'

        if len(args) == 1:
            C = np.asanyarray(args[0])
            nrows, ncols = C.shape[:2]
            if shading in ['gouraud', 'nearest']:
                X, Y = np.meshgrid(np.arange(ncols), np.arange(nrows))
            else:
                X, Y = np.meshgrid(np.arange(ncols + 1), np.arange(nrows + 1))
                shading = 'flat'
        elif len(args) == 3:
            # Check x and y for bad data...
            C = np.asanyarray(args[2])
            # unit conversion allows e.g. datetime objects as axis values
            X, Y = args[:2]
            X, Y = self._process_unit_info([("x", X), ("y", Y)], kwargs)
            X, Y = (cbook.safe_masked_invalid(a, copy=True) for a in [X, Y])

            if funcname == 'pcolormesh':
                if np.ma.is_masked(X) or np.ma.is_masked(Y):
                    raise ValueError(
                        'x and y arguments to pcolormesh cannot have '
                        'non-finite values or be of type '
                        'numpy.ma.MaskedArray with masked values')
            nrows, ncols = C.shape[:2]
        else:
            raise _api.nargs_error(funcname, takes="1 or 3", given=len(args))

        Nx = X.shape[-1]
        Ny = Y.shape[0]
        if X.ndim != 2 or X.shape[0] == 1:
            x = X.reshape(1, Nx)
            X = x.repeat(Ny, axis=0)
        if Y.ndim != 2 or Y.shape[1] == 1:
            y = Y.reshape(Ny, 1)
            Y = y.repeat(Nx, axis=1)
        if X.shape != Y.shape:
            raise TypeError(f'Incompatible X, Y inputs to {funcname}; '
                            f'see help({funcname})')

        if shading == 'auto':
            if ncols == Nx and nrows == Ny:
                shading = 'nearest'
            else:
                shading = 'flat'

        if shading == 'flat':
            if (Nx, Ny) != (ncols + 1, nrows + 1):
                raise TypeError(f"Dimensions of C {C.shape} should"
                                f" be one smaller than X({Nx}) and Y({Ny})"
                                f" while using shading='flat'"
                                f" see help({funcname})")
        else:    # ['nearest', 'gouraud']:
            if (Nx, Ny) != (ncols, nrows):
                raise TypeError('Dimensions of C %s are incompatible with'
                                ' X (%d) and/or Y (%d); see help(%s)' % (
                                    C.shape, Nx, Ny, funcname))
            if shading == 'nearest':
                # grid is specified at the center, so define corners
                # at the midpoints between the grid centers and then use the
                # flat algorithm.
                def _interp_grid(X, require_monotonicity=False):
                    # helper for below. To ensure the cell edges are calculated
                    # correctly, when expanding columns, the monotonicity of
                    # X coords needs to be checked. When expanding rows, the
                    # monotonicity of Y coords needs to be checked.
                    if np.shape(X)[1] > 1:
                        dX = np.diff(X, axis=1) * 0.5
                        if (require_monotonicity and
                                not (np.all(dX >= 0) or np.all(dX <= 0))):
                            _api.warn_external(
                                f"The input coordinates to {funcname} are "
                                "interpreted as cell centers, but are not "
                                "monotonically increasing or decreasing. "
                                "This may lead to incorrectly calculated cell "
                                "edges, in which case, please supply "
                                f"explicit cell edges to {funcname}.")

                        hstack = np.ma.hstack if np.ma.isMA(X) else np.hstack
                        X = hstack((X[:, [0]] - dX[:, [0]],
                                    X[:, :-1] + dX,
                                    X[:, [-1]] + dX[:, [-1]]))
                    else:
                        # This is just degenerate, but we can't reliably guess
                        # a dX if there is just one value.
                        X = np.hstack((X, X))
                    return X

                if ncols == Nx:
                    X = _interp_grid(X, require_monotonicity=True)
                    Y = _interp_grid(Y)
                if nrows == Ny:
                    X = _interp_grid(X.T).T
                    Y = _interp_grid(Y.T, require_monotonicity=True).T
                shading = 'flat'

        C = cbook.safe_masked_invalid(C, copy=True)
        return X, Y, C, shading

    @_preprocess_data()
    @_docstring.interpd
    def pcolor(self, *args, shading=None, alpha=None, norm=None, cmap=None,
               vmin=None, vmax=None, colorizer=None, **kwargs):
        r"""
        Create a pseudocolor plot with a non-regular rectangular grid.

        Call signature::

            pcolor([X, Y,] C, /, **kwargs)

        *X* and *Y* can be used to specify the corners of the quadrilaterals.

        The arguments *X*, *Y*, *C* are positional-only.

        .. hint::

            ``pcolor()`` can be very slow for large arrays. In most
            cases you should use the similar but much faster
            `~.Axes.pcolormesh` instead. See
            :ref:`Differences between pcolor() and pcolormesh()
            <differences-pcolor-pcolormesh>` for a discussion of the
            differences.

        Parameters
        ----------
        C : 2D array-like
            The color-mapped values.  Color-mapping is controlled by *cmap*,
            *norm*, *vmin*, and *vmax*.

        X, Y : array-like, optional
            The coordinates of the corners of quadrilaterals of a pcolormesh::

                (X[i+1, j], Y[i+1, j])       (X[i+1, j+1], Y[i+1, j+1])
                                      ●╶───╴●
                                      │     │
                                      ●╶───╴●
                    (X[i, j], Y[i, j])       (X[i, j+1], Y[i, j+1])

            Note that the column index corresponds to the x-coordinate, and
            the row index corresponds to y. For details, see the
            :ref:`Notes <axes-pcolormesh-grid-orientation>` section below.

            If ``shading='flat'`` the dimensions of *X* and *Y* should be one
            greater than those of *C*, and the quadrilateral is colored due
            to the value at ``C[i, j]``.  If *X*, *Y* and *C* have equal
            dimensions, a warning will be raised and the last row and column
            of *C* will be ignored.

            If ``shading='nearest'``, the dimensions of *X* and *Y* should be
            the same as those of *C* (if not, a ValueError will be raised). The
            color ``C[i, j]`` will be centered on ``(X[i, j], Y[i, j])``.

            If *X* and/or *Y* are 1-D arrays or column vectors they will be
            expanded as needed into the appropriate 2D arrays, making a
            rectangular grid.

        shading : {'flat', 'nearest', 'auto'}, default: :rc:`pcolor.shading`
            The fill style for the quadrilateral. Possible values:

            - 'flat': A solid color is used for each quad. The color of the
              quad (i, j), (i+1, j), (i, j+1), (i+1, j+1) is given by
              ``C[i, j]``. The dimensions of *X* and *Y* should be
              one greater than those of *C*; if they are the same as *C*,
              then a deprecation warning is raised, and the last row
              and column of *C* are dropped.
            - 'nearest': Each grid point will have a color centered on it,
              extending halfway between the adjacent grid centers.  The
              dimensions of *X* and *Y* must be the same as *C*.
            - 'auto': Choose 'flat' if dimensions of *X* and *Y* are one
              larger than *C*.  Choose 'nearest' if dimensions are the same.

            See :doc:`/gallery/images_contours_and_fields/pcolormesh_grids`
            for more description.

        %(cmap_doc)s

        %(norm_doc)s

        %(vmin_vmax_doc)s

        %(colorizer_doc)s

        edgecolors : {'none', None, 'face', color, color sequence}, optional
            The color of the edges. Defaults to 'none'. Possible values:

            - 'none' or '': No edge.
            - *None*: :rc:`patch.edgecolor` will be used. Note that currently
              :rc:`patch.force_edgecolor` has to be True for this to work.
            - 'face': Use the adjacent face color.
            - A color or sequence of colors will set the edge color.

            The singular form *edgecolor* works as an alias.

        alpha : float, default: None
            The alpha blending value of the face color, between 0 (transparent)
            and 1 (opaque). Note: The edgecolor is currently not affected by
            this.

        snap : bool, default: False
            Whether to snap the mesh to pixel boundaries.

        Returns
        -------
        `matplotlib.collections.PolyQuadMesh`

        Other Parameters
        ----------------
        antialiaseds : bool, default: False
            The default *antialiaseds* is False if the default
            *edgecolors*\ ="none" is used.  This eliminates artificial lines
            at patch boundaries, and works regardless of the value of alpha.
            If *edgecolors* is not "none", then the default *antialiaseds*
            is taken from :rc:`patch.antialiased`.
            Stroking the edges may be preferred if *alpha* is 1, but will
            cause artifacts otherwise.

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Additionally, the following arguments are allowed. They are passed
            along to the `~matplotlib.collections.PolyQuadMesh` constructor:

        %(PolyCollection:kwdoc)s

        See Also
        --------
        pcolormesh : for an explanation of the differences between
            pcolor and pcolormesh.
        imshow : If *X* and *Y* are each equidistant, `~.Axes.imshow` can be a
            faster alternative.

        Notes
        -----
        **Masked arrays**

        *X*, *Y* and *C* may be masked arrays. If either ``C[i, j]``, or one
        of the vertices surrounding ``C[i, j]`` (*X* or *Y* at
        ``[i, j], [i+1, j], [i, j+1], [i+1, j+1]``) is masked, nothing is
        plotted.

        .. _axes-pcolor-grid-orientation:

        **Grid orientation**

        The grid orientation follows the standard matrix convention: An array
        *C* with shape (nrows, ncolumns) is plotted with the column number as
        *X* and the row number as *Y*.
        """

        if shading is None:
            shading = mpl.rcParams['pcolor.shading']
        shading = shading.lower()
        X, Y, C, shading = self._pcolorargs('pcolor', *args, shading=shading,
                                            kwargs=kwargs)
        linewidths = (0.25,)
        if 'linewidth' in kwargs:
            kwargs['linewidths'] = kwargs.pop('linewidth')
        kwargs.setdefault('linewidths', linewidths)

        if 'edgecolor' in kwargs:
            kwargs['edgecolors'] = kwargs.pop('edgecolor')
        ec = kwargs.setdefault('edgecolors', 'none')

        # aa setting will default via collections to patch.antialiased
        # unless the boundary is not stroked, in which case the
        # default will be False; with unstroked boundaries, aa
        # makes artifacts that are often disturbing.
        if 'antialiaseds' in kwargs:
            kwargs['antialiased'] = kwargs.pop('antialiaseds')
        if 'antialiased' not in kwargs and cbook._str_lower_equal(ec, "none"):
            kwargs['antialiased'] = False

        kwargs.setdefault('snap', False)

        if np.ma.isMaskedArray(X) or np.ma.isMaskedArray(Y):
            stack = np.ma.stack
            X = np.ma.asarray(X)
            Y = np.ma.asarray(Y)
            # For bounds collections later
            x = X.compressed()
            y = Y.compressed()
        else:
            stack = np.stack
            x = X
            y = Y
        coords = stack([X, Y], axis=-1)

        collection = mcoll.PolyQuadMesh(
            coords, array=C, cmap=cmap, norm=norm, colorizer=colorizer,
            alpha=alpha, **kwargs)
        collection._check_exclusionary_keywords(colorizer, vmin=vmin, vmax=vmax)
        collection._scale_norm(norm, vmin, vmax)

        # Transform from native to data coordinates?
        t = collection._transform
        if (not isinstance(t, mtransforms.Transform) and
                hasattr(t, '_as_mpl_transform')):
            t = t._as_mpl_transform(self.axes)

        if t and any(t.contains_branch_seperately(self.transData)):
            trans_to_data = t - self.transData
            pts = np.vstack([x, y]).T.astype(float)
            transformed_pts = trans_to_data.transform(pts)
            x = transformed_pts[..., 0]
            y = transformed_pts[..., 1]

        self.add_collection(collection, autolim=False)

        minx = np.min(x)
        maxx = np.max(x)
        miny = np.min(y)
        maxy = np.max(y)
        collection.sticky_edges.x[:] = [minx, maxx]
        collection.sticky_edges.y[:] = [miny, maxy]
        corners = (minx, miny), (maxx, maxy)
        self.update_datalim(corners)
        self._request_autoscale_view()
        return collection

    @_preprocess_data()
    @_docstring.interpd
    def pcolormesh(self, *args, alpha=None, norm=None, cmap=None, vmin=None,
                   vmax=None, colorizer=None, shading=None, antialiased=False,
                   **kwargs):
        """
        Create a pseudocolor plot with a non-regular rectangular grid.

        Call signature::

            pcolormesh([X, Y,] C, /, **kwargs)

        *X* and *Y* can be used to specify the corners of the quadrilaterals.

        The arguments *X*, *Y*, *C* are positional-only.

        .. hint::

           `~.Axes.pcolormesh` is similar to `~.Axes.pcolor`. It is much faster
           and preferred in most cases. For a detailed discussion on the
           differences see :ref:`Differences between pcolor() and pcolormesh()
           <differences-pcolor-pcolormesh>`.

        Parameters
        ----------
        C : array-like
            The mesh data. Supported array shapes are:

            - (M, N) or M*N: a mesh with scalar data. The values are mapped to
              colors using normalization and a colormap. See parameters *norm*,
              *cmap*, *vmin*, *vmax*.
            - (M, N, 3): an image with RGB values (0-1 float or 0-255 int).
            - (M, N, 4): an image with RGBA values (0-1 float or 0-255 int),
              i.e. including transparency.

            The first two dimensions (M, N) define the rows and columns of
            the mesh data.

        X, Y : array-like, optional
            The coordinates of the corners of quadrilaterals of a pcolormesh::

                (X[i+1, j], Y[i+1, j])       (X[i+1, j+1], Y[i+1, j+1])
                                      ●╶───╴●
                                      │     │
                                      ●╶───╴●
                    (X[i, j], Y[i, j])       (X[i, j+1], Y[i, j+1])

            Note that the column index corresponds to the x-coordinate, and
            the row index corresponds to y. For details, see the
            :ref:`Notes <axes-pcolormesh-grid-orientation>` section below.

            If ``shading='flat'`` the dimensions of *X* and *Y* should be one
            greater than those of *C*, and the quadrilateral is colored due
            to the value at ``C[i, j]``.  If *X*, *Y* and *C* have equal
            dimensions, a warning will be raised and the last row and column
            of *C* will be ignored.

            If ``shading='nearest'`` or ``'gouraud'``, the dimensions of *X*
            and *Y* should be the same as those of *C* (if not, a ValueError
            will be raised).  For ``'nearest'`` the color ``C[i, j]`` is
            centered on ``(X[i, j], Y[i, j])``.  For ``'gouraud'``, a smooth
            interpolation is carried out between the quadrilateral corners.

            If *X* and/or *Y* are 1-D arrays or column vectors they will be
            expanded as needed into the appropriate 2D arrays, making a
            rectangular grid.

        %(cmap_doc)s

        %(norm_doc)s

        %(vmin_vmax_doc)s

        %(colorizer_doc)s

        edgecolors : {'none', None, 'face', color, color sequence}, optional
            The color of the edges. Defaults to 'none'. Possible values:

            - 'none' or '': No edge.
            - *None*: :rc:`patch.edgecolor` will be used. Note that currently
              :rc:`patch.force_edgecolor` has to be True for this to work.
            - 'face': Use the adjacent face color.
            - A color or sequence of colors will set the edge color.

            The singular form *edgecolor* works as an alias.

        alpha : float, default: None
            The alpha blending value, between 0 (transparent) and 1 (opaque).

        shading : {'flat', 'nearest', 'gouraud', 'auto'}, optional
            The fill style for the quadrilateral; defaults to
            :rc:`pcolor.shading`. Possible values:

            - 'flat': A solid color is used for each quad. The color of the
              quad (i, j), (i+1, j), (i, j+1), (i+1, j+1) is given by
              ``C[i, j]``. The dimensions of *X* and *Y* should be
              one greater than those of *C*; if they are the same as *C*,
              then a deprecation warning is raised, and the last row
              and column of *C* are dropped.
            - 'nearest': Each grid point will have a color centered on it,
              extending halfway between the adjacent grid centers.  The
              dimensions of *X* and *Y* must be the same as *C*.
            - 'gouraud': Each quad will be Gouraud shaded: The color of the
              corners (i', j') are given by ``C[i', j']``. The color values of
              the area in between is interpolated from the corner values.
              The dimensions of *X* and *Y* must be the same as *C*. When
              Gouraud shading is used, *edgecolors* is ignored.
            - 'auto': Choose 'flat' if dimensions of *X* and *Y* are one
              larger than *C*.  Choose 'nearest' if dimensions are the same.

            See :doc:`/gallery/images_contours_and_fields/pcolormesh_grids`
            for more description.

        snap : bool, default: False
            Whether to snap the mesh to pixel boundaries.

        rasterized : bool, optional
            Rasterize the pcolormesh when drawing vector graphics.  This can
            speed up rendering and produce smaller files for large data sets.
            See also :doc:`/gallery/misc/rasterization_demo`.

        Returns
        -------
        `matplotlib.collections.QuadMesh`

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Additionally, the following arguments are allowed. They are passed
            along to the `~matplotlib.collections.QuadMesh` constructor:

        %(QuadMesh:kwdoc)s

        See Also
        --------
        pcolor : An alternative implementation with slightly different
            features. For a detailed discussion on the differences see
            :ref:`Differences between pcolor() and pcolormesh()
            <differences-pcolor-pcolormesh>`.
        imshow : If *X* and *Y* are each equidistant, `~.Axes.imshow` can be a
            faster alternative.

        Notes
        -----
        **Masked arrays**

        *C* may be a masked array. If ``C[i, j]`` is masked, the corresponding
        quadrilateral will be transparent. Masking of *X* and *Y* is not
        supported. Use `~.Axes.pcolor` if you need this functionality.

        .. _axes-pcolormesh-grid-orientation:

        **Grid orientation**

        The grid orientation follows the standard matrix convention: An array
        *C* with shape (nrows, ncolumns) is plotted with the column number as
        *X* and the row number as *Y*.

        .. _differences-pcolor-pcolormesh:

        **Differences between pcolor() and pcolormesh()**

        Both methods are used to create a pseudocolor plot of a 2D array
        using quadrilaterals.

        The main difference lies in the created object and internal data
        handling:
        While `~.Axes.pcolor` returns a `.PolyQuadMesh`, `~.Axes.pcolormesh`
        returns a `.QuadMesh`. The latter is more specialized for the given
        purpose and thus is faster. It should almost always be preferred.

        There is also a slight difference in the handling of masked arrays.
        Both `~.Axes.pcolor` and `~.Axes.pcolormesh` support masked arrays
        for *C*. However, only `~.Axes.pcolor` supports masked arrays for *X*
        and *Y*. The reason lies in the internal handling of the masked values.
        `~.Axes.pcolor` leaves out the respective polygons from the
        PolyQuadMesh. `~.Axes.pcolormesh` sets the facecolor of the masked
        elements to transparent. You can see the difference when using
        edgecolors. While all edges are drawn irrespective of masking in a
        QuadMesh, the edge between two adjacent masked quadrilaterals in
        `~.Axes.pcolor` is not drawn as the corresponding polygons do not
        exist in the PolyQuadMesh. Because PolyQuadMesh draws each individual
        polygon, it also supports applying hatches and linestyles to the collection.

        Another difference is the support of Gouraud shading in
        `~.Axes.pcolormesh`, which is not available with `~.Axes.pcolor`.

        """
        if shading is None:
            shading = mpl.rcParams['pcolor.shading']
        shading = shading.lower()
        kwargs.setdefault('edgecolors', 'none')

        X, Y, C, shading = self._pcolorargs('pcolormesh', *args,
                                            shading=shading, kwargs=kwargs)
        coords = np.stack([X, Y], axis=-1)

        kwargs.setdefault('snap', mpl.rcParams['pcolormesh.snap'])

        collection = mcoll.QuadMesh(
            coords, antialiased=antialiased, shading=shading,
            array=C, cmap=cmap, norm=norm, colorizer=colorizer, alpha=alpha, **kwargs)
        collection._check_exclusionary_keywords(colorizer, vmin=vmin, vmax=vmax)
        collection._scale_norm(norm, vmin, vmax)

        coords = coords.reshape(-1, 2)  # flatten the grid structure; keep x, y

        # Transform from native to data coordinates?
        t = collection._transform
        if (not isinstance(t, mtransforms.Transform) and
                hasattr(t, '_as_mpl_transform')):
            t = t._as_mpl_transform(self.axes)

        if t and any(t.contains_branch_seperately(self.transData)):
            trans_to_data = t - self.transData
            coords = trans_to_data.transform(coords)

        self.add_collection(collection, autolim=False)

        minx, miny = np.min(coords, axis=0)
        maxx, maxy = np.max(coords, axis=0)
        collection.sticky_edges.x[:] = [minx, maxx]
        collection.sticky_edges.y[:] = [miny, maxy]
        corners = (minx, miny), (maxx, maxy)
        self.update_datalim(corners)
        self._request_autoscale_view()
        return collection

    @_preprocess_data()
    @_docstring.interpd
    def pcolorfast(self, *args, alpha=None, norm=None, cmap=None, vmin=None,
                   vmax=None, colorizer=None, **kwargs):
        """
        Create a pseudocolor plot with a non-regular rectangular grid.

        Call signature::

            ax.pcolorfast([X, Y], C, /, **kwargs)

        The arguments *X*, *Y*, *C* are positional-only.

        This method is similar to `~.Axes.pcolor` and `~.Axes.pcolormesh`.
        It's designed to provide the fastest pcolor-type plotting with the
        Agg backend. To achieve this, it uses different algorithms internally
        depending on the complexity of the input grid (regular rectangular,
        non-regular rectangular or arbitrary quadrilateral).

        .. warning::

            This method is experimental. Compared to `~.Axes.pcolor` or
            `~.Axes.pcolormesh` it has some limitations:

            - It supports only flat shading (no outlines)
            - It lacks support for log scaling of the axes.
            - It does not have a pyplot wrapper.

        Parameters
        ----------
        C : array-like
            The image data. Supported array shapes are:

            - (M, N): an image with scalar data.  Color-mapping is controlled
              by *cmap*, *norm*, *vmin*, and *vmax*.
            - (M, N, 3): an image with RGB values (0-1 float or 0-255 int).
            - (M, N, 4): an image with RGBA values (0-1 float or 0-255 int),
              i.e. including transparency.

            The first two dimensions (M, N) define the rows and columns of
            the image.

            This parameter can only be passed positionally.

        X, Y : tuple or array-like, default: ``(0, N)``, ``(0, M)``
            *X* and *Y* are used to specify the coordinates of the
            quadrilaterals. There are different ways to do this:

            - Use tuples ``X=(xmin, xmax)`` and ``Y=(ymin, ymax)`` to define
              a *uniform rectangular grid*.

              The tuples define the outer edges of the grid. All individual
              quadrilaterals will be of the same size. This is the fastest
              version.

            - Use 1D arrays *X*, *Y* to specify a *non-uniform rectangular
              grid*.

              In this case *X* and *Y* have to be monotonic 1D arrays of length
              *N+1* and *M+1*, specifying the x and y boundaries of the cells.

              The speed is intermediate. Note: The grid is checked, and if
              found to be uniform the fast version is used.

            - Use 2D arrays *X*, *Y* if you need an *arbitrary quadrilateral
              grid* (i.e. if the quadrilaterals are not rectangular).

              In this case *X* and *Y* are 2D arrays with shape (M + 1, N + 1),
              specifying the x and y coordinates of the corners of the colored
              quadrilaterals.

              This is the most general, but the slowest to render.  It may
              produce faster and more compact output using ps, pdf, and
              svg backends, however.

            These arguments can only be passed positionally.

        %(cmap_doc)s

            This parameter is ignored if *C* is RGB(A).

        %(norm_doc)s

            This parameter is ignored if *C* is RGB(A).

        %(vmin_vmax_doc)s

            This parameter is ignored if *C* is RGB(A).

        %(colorizer_doc)s

            This parameter is ignored if *C* is RGB(A).

        alpha : float, default: None
            The alpha blending value, between 0 (transparent) and 1 (opaque).

        snap : bool, default: False
            Whether to snap the mesh to pixel boundaries.

        Returns
        -------
        `.AxesImage` or `.PcolorImage` or `.QuadMesh`
            The return type depends on the type of grid:

            - `.AxesImage` for a regular rectangular grid.
            - `.PcolorImage` for a non-regular rectangular grid.
            - `.QuadMesh` for a non-rectangular grid.

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Supported additional parameters depend on the type of grid.
            See return types of *image* for further description.
        """

        C = args[-1]
        nr, nc = np.shape(C)[:2]
        if len(args) == 1:
            style = "image"
            x = [0, nc]
            y = [0, nr]
        elif len(args) == 3:
            x, y = args[:2]
            x = np.asarray(x)
            y = np.asarray(y)
            if x.ndim == 1 and y.ndim == 1:
                if x.size == 2 and y.size == 2:
                    style = "image"
                else:
                    if x.size != nc + 1:
                        raise ValueError(
                            f"Length of X ({x.size}) must be one larger than the "
                            f"number of columns in C ({nc})")
                    if y.size != nr + 1:
                        raise ValueError(
                            f"Length of Y ({y.size}) must be one larger than the "
                            f"number of rows in C ({nr})"
                        )
                    dx = np.diff(x)
                    dy = np.diff(y)
                    if (np.ptp(dx) < 0.01 * abs(dx.mean()) and
                            np.ptp(dy) < 0.01 * abs(dy.mean())):
                        style = "image"
                    else:
                        style = "pcolorimage"
            elif x.ndim == 2 and y.ndim == 2:
                style = "quadmesh"
            else:
                raise TypeError(
                    f"When 3 positional parameters are passed to pcolorfast, the first "
                    f"two (X and Y) must be both 1D or both 2D; the given X was "
                    f"{x.ndim}D and the given Y was {y.ndim}D")
        else:
            raise _api.nargs_error('pcolorfast', '1 or 3', len(args))

        mcolorizer.ColorizingArtist._check_exclusionary_keywords(colorizer, vmin=vmin,
                                                                 vmax=vmax)
        if style == "quadmesh":
            # data point in each cell is value at lower left corner
            coords = np.stack([x, y], axis=-1)
            if np.ndim(C) not in {2, 3}:
                raise ValueError("C must be 2D or 3D")
            collection = mcoll.QuadMesh(
                coords, array=C,
                alpha=alpha, cmap=cmap, norm=norm, colorizer=colorizer,
                antialiased=False, edgecolors="none")
            self.add_collection(collection, autolim=False)
            xl, xr, yb, yt = x.min(), x.max(), y.min(), y.max()
            ret = collection

        else:  # It's one of the two image styles.
            extent = xl, xr, yb, yt = x[0], x[-1], y[0], y[-1]
            if style == "image":
                im = mimage.AxesImage(
                    self, cmap=cmap, norm=norm, colorizer=colorizer,
                    data=C, alpha=alpha, extent=extent,
                    interpolation='nearest', origin='lower',
                    **kwargs)
            elif style == "pcolorimage":
                im = mimage.PcolorImage(
                    self, x, y, C,
                    cmap=cmap, norm=norm, colorizer=colorizer, alpha=alpha,
                    extent=extent, **kwargs)
            self.add_image(im)
            ret = im

        if np.ndim(C) == 2:  # C.ndim == 3 is RGB(A) so doesn't need scaling.
            ret._scale_norm(norm, vmin, vmax)

        if ret.get_clip_path() is None:
            # image does not already have clipping set, clip to Axes patch
            ret.set_clip_path(self.patch)

        ret.sticky_edges.x[:] = [xl, xr]
        ret.sticky_edges.y[:] = [yb, yt]
        self.update_datalim(np.array([[xl, yb], [xr, yt]]))
        self._request_autoscale_view(tight=True)
        return ret

    @_preprocess_data()
    @_docstring.interpd
    def contour(self, *args, **kwargs):
        """
        Plot contour lines.

        Call signature::

            contour([X, Y,] Z, /, [levels], **kwargs)

        The arguments *X*, *Y*, *Z* are positional-only.
        %(contour_doc)s
        """
        kwargs['filled'] = False
        contours = mcontour.QuadContourSet(self, *args, **kwargs)
        self._request_autoscale_view()
        return contours

    @_preprocess_data()
    @_docstring.interpd
    def contourf(self, *args, **kwargs):
        """
        Plot filled contours.

        Call signature::

            contourf([X, Y,] Z, /, [levels], **kwargs)

        The arguments *X*, *Y*, *Z* are positional-only.
        %(contour_doc)s
        """
        kwargs['filled'] = True
        contours = mcontour.QuadContourSet(self, *args, **kwargs)
        self._request_autoscale_view()
        return contours

    def clabel(self, CS, levels=None, **kwargs):
        """
        Label a contour plot.

        Adds labels to line contours in given `.ContourSet`.

        Parameters
        ----------
        CS : `.ContourSet` instance
            Line contours to label.

        levels : array-like, optional
            A list of level values, that should be labeled. The list must be
            a subset of ``CS.levels``. If not given, all levels are labeled.

        **kwargs
            All other parameters are documented in `~.ContourLabeler.clabel`.
        """
        return CS.clabel(levels, **kwargs)

    #### Data analysis

    @_api.make_keyword_only("3.10", "range")
    @_preprocess_data(replace_names=["x", 'weights'], label_namer="x")
    def hist(self, x, bins=None, range=None, density=False, weights=None,
             cumulative=False, bottom=None, histtype='bar', align='mid',
             orientation='vertical', rwidth=None, log=False,
             color=None, label=None, stacked=False, **kwargs):
        """
        Compute and plot a histogram.

        This method uses `numpy.histogram` to bin the data in *x* and count the
        number of values in each bin, then draws the distribution either as a
        `.BarContainer` or `.Polygon`. The *bins*, *range*, *density*, and
        *weights* parameters are forwarded to `numpy.histogram`.

        If the data has already been binned and counted, use `~.bar` or
        `~.stairs` to plot the distribution::

            counts, bins = np.histogram(x)
            plt.stairs(counts, bins)

        Alternatively, plot pre-computed bins and counts using ``hist()`` by
        treating each bin as a single point with a weight equal to its count::

            plt.hist(bins[:-1], bins, weights=counts)

        The data input *x* can be a singular array, a list of datasets of
        potentially different lengths ([*x0*, *x1*, ...]), or a 2D ndarray in
        which each column is a dataset. Note that the ndarray form is
        transposed relative to the list form. If the input is an array, then
        the return value is a tuple (*n*, *bins*, *patches*); if the input is a
        sequence of arrays, then the return value is a tuple
        ([*n0*, *n1*, ...], *bins*, [*patches0*, *patches1*, ...]).

        Masked arrays are not supported.

        Parameters
        ----------
        x : (n,) array or sequence of (n,) arrays
            Input values, this takes either a single array or a sequence of
            arrays which are not required to be of the same length.

        bins : int or sequence or str, default: :rc:`hist.bins`
            If *bins* is an integer, it defines the number of equal-width bins
            in the range.

            If *bins* is a sequence, it defines the bin edges, including the
            left edge of the first bin and the right edge of the last bin;
            in this case, bins may be unequally spaced.  All but the last
            (righthand-most) bin is half-open.  In other words, if *bins* is::

                [1, 2, 3, 4]

            then the first bin is ``[1, 2)`` (including 1, but excluding 2) and
            the second ``[2, 3)``.  The last bin, however, is ``[3, 4]``, which
            *includes* 4.

            If *bins* is a string, it is one of the binning strategies
            supported by `numpy.histogram_bin_edges`: 'auto', 'fd', 'doane',
            'scott', 'stone', 'rice', 'sturges', or 'sqrt'.

        range : tuple or None, default: None
            The lower and upper range of the bins. Lower and upper outliers
            are ignored. If not provided, *range* is ``(x.min(), x.max())``.
            Range has no effect if *bins* is a sequence.

            If *bins* is a sequence or *range* is specified, autoscaling
            is based on the specified bin range instead of the
            range of x.

        density : bool, default: False
            If ``True``, draw and return a probability density: each bin
            will display the bin's raw count divided by the total number of
            counts *and the bin width*
            (``density = counts / (sum(counts) * np.diff(bins))``),
            so that the area under the histogram integrates to 1
            (``np.sum(density * np.diff(bins)) == 1``).

            If *stacked* is also ``True``, the sum of the histograms is
            normalized to 1.

        weights : (n,) array-like or None, default: None
            An array of weights, of the same shape as *x*.  Each value in
            *x* only contributes its associated weight towards the bin count
            (instead of 1).  If *density* is ``True``, the weights are
            normalized, so that the integral of the density over the range
            remains 1.

        cumulative : bool or -1, default: False
            If ``True``, then a histogram is computed where each bin gives the
            counts in that bin plus all bins for smaller values. The last bin
            gives the total number of datapoints.

            If *density* is also ``True`` then the histogram is normalized such
            that the last bin equals 1.

            If *cumulative* is a number less than 0 (e.g., -1), the direction
            of accumulation is reversed.  In this case, if *density* is also
            ``True``, then the histogram is normalized such that the first bin
            equals 1.

        bottom : array-like or float, default: 0
            Location of the bottom of each bin, i.e. bins are drawn from
            ``bottom`` to ``bottom + hist(x, bins)`` If a scalar, the bottom
            of each bin is shifted by the same amount. If an array, each bin
            is shifted independently and the length of bottom must match the
            number of bins. If None, defaults to 0.

        histtype : {'bar', 'barstacked', 'step', 'stepfilled'}, default: 'bar'
            The type of histogram to draw.

            - 'bar' is a traditional bar-type histogram.  If multiple data
              are given the bars are arranged side by side.
            - 'barstacked' is a bar-type histogram where multiple
              data are stacked on top of each other.
            - 'step' generates a lineplot that is by default unfilled.
            - 'stepfilled' generates a lineplot that is by default filled.

        align : {'left', 'mid', 'right'}, default: 'mid'
            The horizontal alignment of the histogram bars.

            - 'left': bars are centered on the left bin edges.
            - 'mid': bars are centered between the bin edges.
            - 'right': bars are centered on the right bin edges.

        orientation : {'vertical', 'horizontal'}, default: 'vertical'
            If 'horizontal', `~.Axes.barh` will be used for bar-type histograms
            and the *bottom* kwarg will be the left edges.

        rwidth : float or None, default: None
            The relative width of the bars as a fraction of the bin width.  If
            ``None``, automatically compute the width.

            Ignored if *histtype* is 'step' or 'stepfilled'.

        log : bool, default: False
            If ``True``, the histogram axis will be set to a log scale.

        color : :mpltype:`color` or list of :mpltype:`color` or None, default: None
            Color or sequence of colors, one per dataset.  Default (``None``)
            uses the standard line color sequence.

        label : str or list of str, optional
            String, or sequence of strings to match multiple datasets.  Bar
            charts yield multiple patches per dataset, but only the first gets
            the label, so that `~.Axes.legend` will work as expected.

        stacked : bool, default: False
            If ``True``, multiple data are stacked on top of each other If
            ``False`` multiple data are arranged side by side if histtype is
            'bar' or on top of each other if histtype is 'step'

        Returns
        -------
        n : array or list of arrays
            The values of the histogram bins. See *density* and *weights* for a
            description of the possible semantics.  If input *x* is an array,
            then this is an array of length *nbins*. If input is a sequence of
            arrays ``[data1, data2, ...]``, then this is a list of arrays with
            the values of the histograms for each of the arrays in the same
            order.  The dtype of the array *n* (or of its element arrays) will
            always be float even if no weighting or normalization is used.

        bins : array
            The edges of the bins. Length nbins + 1 (nbins left edges and right
            edge of last bin).  Always a single array even when multiple data
            sets are passed in.

        patches : `.BarContainer` or list of a single `.Polygon` or list of \
such objects
            Container of individual artists used to create the histogram
            or list of such containers if there are multiple input datasets.

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            `~matplotlib.patches.Patch` properties. The following properties
            additionally accept a sequence of values corresponding to the
            datasets in *x*:
            *edgecolor*, *facecolor*, *linewidth*, *linestyle*, *hatch*.

            .. versionadded:: 3.10
               Allowing sequences of values in above listed Patch properties.

        See Also
        --------
        hist2d : 2D histogram with rectangular bins
        hexbin : 2D histogram with hexagonal bins
        stairs : Plot a pre-computed histogram
        bar : Plot a pre-computed histogram

        Notes
        -----
        For large numbers of bins (>1000), plotting can be significantly
        accelerated by using `~.Axes.stairs` to plot a pre-computed histogram
        (``plt.stairs(*np.histogram(data))``), or by setting *histtype* to
        'step' or 'stepfilled' rather than 'bar' or 'barstacked'.
        """
        # Avoid shadowing the builtin.
        bin_range = range
        from builtins import range

        kwargs = cbook.normalize_kwargs(kwargs, mpatches.Patch)

        if np.isscalar(x):
            x = [x]

        if bins is None:
            bins = mpl.rcParams['hist.bins']

        # Validate string inputs here to avoid cluttering subsequent code.
        _api.check_in_list(['bar', 'barstacked', 'step', 'stepfilled'],
                           histtype=histtype)
        _api.check_in_list(['left', 'mid', 'right'], align=align)
        _api.check_in_list(['horizontal', 'vertical'], orientation=orientation)

        if histtype == 'barstacked' and not stacked:
            stacked = True

        # Massage 'x' for processing.
        x = cbook._reshape_2D(x, 'x')
        nx = len(x)  # number of datasets

        # Process unit information.  _process_unit_info sets the unit and
        # converts the first dataset; then we convert each following dataset
        # one at a time.
        if orientation == "vertical":
            convert_units = self.convert_xunits
            x = [*self._process_unit_info([("x", x[0])], kwargs),
                 *map(convert_units, x[1:])]
        else:  # horizontal
            convert_units = self.convert_yunits
            x = [*self._process_unit_info([("y", x[0])], kwargs),
                 *map(convert_units, x[1:])]

        if bin_range is not None:
            bin_range = convert_units(bin_range)

        if not cbook.is_scalar_or_string(bins):
            bins = convert_units(bins)

        # We need to do to 'weights' what was done to 'x'
        if weights is not None:
            w = cbook._reshape_2D(weights, 'weights')
        else:
            w = [None] * nx

        if len(w) != nx:
            raise ValueError('weights should have the same shape as x')

        input_empty = True
        for xi, wi in zip(x, w):
            len_xi = len(xi)
            if wi is not None and len(wi) != len_xi:
                raise ValueError('weights should have the same shape as x')
            if len_xi:
                input_empty = False

        if color is None:
            colors = [self._get_lines.get_next_color() for i in range(nx)]
        else:
            colors = mcolors.to_rgba_array(color)
            if len(colors) != nx:
                raise ValueError(f"The 'color' keyword argument must have one "
                                 f"color per dataset, but {nx} datasets and "
                                 f"{len(colors)} colors were provided")

        hist_kwargs = dict()

        # if the bin_range is not given, compute without nan numpy
        # does not do this for us when guessing the range (but will
        # happily ignore nans when computing the histogram).
        if bin_range is None:
            xmin = np.inf
            xmax = -np.inf
            for xi in x:
                if len(xi):
                    # python's min/max ignore nan,
                    # np.minnan returns nan for all nan input
                    xmin = min(xmin, np.nanmin(xi))
                    xmax = max(xmax, np.nanmax(xi))
            if xmin <= xmax:  # Only happens if we have seen a finite value.
                bin_range = (xmin, xmax)

        # If bins are not specified either explicitly or via range,
        # we need to figure out the range required for all datasets,
        # and supply that to np.histogram.
        if not input_empty and len(x) > 1:
            if weights is not None:
                _w = np.concatenate(w)
            else:
                _w = None
            bins = np.histogram_bin_edges(
                np.concatenate(x), bins, bin_range, _w)
        else:
            hist_kwargs['range'] = bin_range

        density = bool(density)
        if density and not stacked:
            hist_kwargs['density'] = density

        # List to store all the top coordinates of the histograms
        tops = []  # Will have shape (n_datasets, n_bins).
        # Loop through datasets
        for i in range(nx):
            # this will automatically overwrite bins,
            # so that each histogram uses the same bins
            m, bins = np.histogram(x[i], bins, weights=w[i], **hist_kwargs)
            tops.append(m)
        tops = np.array(tops, float)  # causes problems later if it's an int
        bins = np.array(bins, float)  # causes problems if float16
        if stacked:
            tops = tops.cumsum(axis=0)
            # If a stacked density plot, normalize so the area of all the
            # stacked histograms together is 1
            if density:
                tops = (tops / np.diff(bins)) / tops[-1].sum()
        if cumulative:
            slc = slice(None)
            if isinstance(cumulative, Number) and cumulative < 0:
                slc = slice(None, None, -1)
            if density:
                tops = (tops * np.diff(bins))[:, slc].cumsum(axis=1)[:, slc]
            else:
                tops = tops[:, slc].cumsum(axis=1)[:, slc]

        patches = []

        if histtype.startswith('bar'):

            totwidth = np.diff(bins)

            if rwidth is not None:
                dr = np.clip(rwidth, 0, 1)
            elif (len(tops) > 1 and
                  ((not stacked) or mpl.rcParams['_internal.classic_mode'])):
                dr = 0.8
            else:
                dr = 1.0

            if histtype == 'bar' and not stacked:
                width = dr * totwidth / nx
                dw = width
                boffset = -0.5 * dr * totwidth * (1 - 1 / nx)
            elif histtype == 'barstacked' or stacked:
                width = dr * totwidth
                boffset, dw = 0.0, 0.0

            if align == 'mid':
                boffset += 0.5 * totwidth
            elif align == 'right':
                boffset += totwidth

            if orientation == 'horizontal':
                _barfunc = self.barh
                bottom_kwarg = 'left'
            else:  # orientation == 'vertical'
                _barfunc = self.bar
                bottom_kwarg = 'bottom'

            for top, color in zip(tops, colors):
                if bottom is None:
                    bottom = np.zeros(len(top))
                if stacked:
                    height = top - bottom
                else:
                    height = top
                bars = _barfunc(bins[:-1]+boffset, height, width,
                                align='center', log=log,
                                color=color, **{bottom_kwarg: bottom})
                patches.append(bars)
                if stacked:
                    bottom = top
                boffset += dw
            # Remove stickies from all bars but the lowest ones, as otherwise
            # margin expansion would be unable to cross the stickies in the
            # middle of the bars.
            for bars in patches[1:]:
                for patch in bars:
                    patch.sticky_edges.x[:] = patch.sticky_edges.y[:] = []

        elif histtype.startswith('step'):
            # these define the perimeter of the polygon
            x = np.zeros(4 * len(bins) - 3)
            y = np.zeros(4 * len(bins) - 3)

            x[0:2*len(bins)-1:2], x[1:2*len(bins)-1:2] = bins, bins[:-1]
            x[2*len(bins)-1:] = x[1:2*len(bins)-1][::-1]

            if bottom is None:
                bottom = 0

            y[1:2*len(bins)-1:2] = y[2:2*len(bins):2] = bottom
            y[2*len(bins)-1:] = y[1:2*len(bins)-1][::-1]

            if log:
                if orientation == 'horizontal':
                    self.set_xscale('log', nonpositive='clip')
                else:  # orientation == 'vertical'
                    self.set_yscale('log', nonpositive='clip')

            if align == 'left':
                x -= 0.5*(bins[1]-bins[0])
            elif align == 'right':
                x += 0.5*(bins[1]-bins[0])

            # If fill kwarg is set, it will be passed to the patch collection,
            # overriding this
            fill = (histtype == 'stepfilled')

            xvals, yvals = [], []
            for top in tops:
                if stacked:
                    # top of the previous polygon becomes the bottom
                    y[2*len(bins)-1:] = y[1:2*len(bins)-1][::-1]
                # set the top of this polygon
                y[1:2*len(bins)-1:2] = y[2:2*len(bins):2] = top + bottom

                # The starting point of the polygon has not yet been
                # updated. So far only the endpoint was adjusted. This
                # assignment closes the polygon. The redundant endpoint is
                # later discarded (for step and stepfilled).
                y[0] = y[-1]

                if orientation == 'horizontal':
                    xvals.append(y.copy())
                    yvals.append(x.copy())
                else:
                    xvals.append(x.copy())
                    yvals.append(y.copy())

            # stepfill is closed, step is not
            split = -1 if fill else 2 * len(bins)
            # add patches in reverse order so that when stacking,
            # items lower in the stack are plotted on top of
            # items higher in the stack
            for x, y, color in reversed(list(zip(xvals, yvals, colors))):
                patches.append(self.fill(
                    x[:split], y[:split],
                    closed=True if fill else None,
                    facecolor=color,
                    edgecolor=None if fill else color,
                    fill=fill if fill else None,
                    zorder=None if fill else mlines.Line2D.zorder))
            for patch_list in patches:
                for patch in patch_list:
                    if orientation == 'vertical':
                        patch.sticky_edges.y.append(0)
                    elif orientation == 'horizontal':
                        patch.sticky_edges.x.append(0)

            # we return patches, so put it back in the expected order
            patches.reverse()

        # If None, make all labels None (via zip_longest below); otherwise,
        # cast each element to str, but keep a single str as it.
        labels = [] if label is None else np.atleast_1d(np.asarray(label, str))

        if histtype == "step":
            ec = kwargs.get('edgecolor', colors)
        else:
            ec = kwargs.get('edgecolor', None)
        if ec is None or cbook._str_lower_equal(ec, 'none'):
            edgecolors = itertools.repeat(ec)
        else:
            edgecolors = itertools.cycle(mcolors.to_rgba_array(ec))

        fc = kwargs.get('facecolor', colors)
        if cbook._str_lower_equal(fc, 'none'):
            facecolors = itertools.repeat(fc)
        else:
            facecolors = itertools.cycle(mcolors.to_rgba_array(fc))

        hatches = itertools.cycle(np.atleast_1d(kwargs.get('hatch', None)))
        linewidths = itertools.cycle(np.atleast_1d(kwargs.get('linewidth', None)))
        if 'linestyle' in kwargs:
            linestyles = itertools.cycle(mlines._get_dash_patterns(kwargs['linestyle']))
        else:
            linestyles = itertools.repeat(None)

        for patch, lbl in itertools.zip_longest(patches, labels):
            if not patch:
                continue
            p = patch[0]
            kwargs.update({
                'hatch': next(hatches),
                'linewidth': next(linewidths),
                'linestyle': next(linestyles),
                'edgecolor': next(edgecolors),
                'facecolor': next(facecolors),
            })
            p._internal_update(kwargs)
            if lbl is not None:
                p.set_label(lbl)
            for p in patch[1:]:
                p._internal_update(kwargs)
                p.set_label('_nolegend_')

        if nx == 1:
            return tops[0], bins, patches[0]
        else:
            patch_type = ("BarContainer" if histtype.startswith("bar")
                          else "list[Polygon]")
            return tops, bins, cbook.silent_list(patch_type, patches)

    @_preprocess_data()
    def stairs(self, values, edges=None, *,
               orientation='vertical', baseline=0, fill=False, **kwargs):
        """
        Draw a stepwise constant function as a line or a filled plot.

        *edges* define the x-axis positions of the steps. *values* the function values
        between these steps. Depending on *fill*, the function is drawn either as a
        continuous line with vertical segments at the edges, or as a filled area.

        Parameters
        ----------
        values : array-like
            The step heights.

        edges : array-like
            The step positions, with ``len(edges) == len(vals) + 1``,
            between which the curve takes on vals values.

        orientation : {'vertical', 'horizontal'}, default: 'vertical'
            The direction of the steps. Vertical means that *values* are along
            the y-axis, and edges are along the x-axis.

        baseline : float, array-like or None, default: 0
            The bottom value of the bounding edges or when
            ``fill=True``, position of lower edge. If *fill* is
            True or an array is passed to *baseline*, a closed
            path is drawn.

            If None, then drawn as an unclosed Path.

        fill : bool, default: False
            Whether the area under the step curve should be filled.

            Passing both ``fill=True` and ``baseline=None`` will likely result in
            undesired filling: the first and last points will be connected
            with a straight line and the fill will be between this line and the stairs.


        Returns
        -------
        StepPatch : `~matplotlib.patches.StepPatch`

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            `~matplotlib.patches.StepPatch` properties

        """

        if 'color' in kwargs:
            _color = kwargs.pop('color')
        else:
            _color = self._get_lines.get_next_color()
        if fill:
            kwargs.setdefault('linewidth', 0)
            kwargs.setdefault('facecolor', _color)
        else:
            kwargs.setdefault('edgecolor', _color)

        if edges is None:
            edges = np.arange(len(values) + 1)

        edges, values, baseline = self._process_unit_info(
            [("x", edges), ("y", values), ("y", baseline)], kwargs)

        patch = mpatches.StepPatch(values,
                                   edges,
                                   baseline=baseline,
                                   orientation=orientation,
                                   fill=fill,
                                   **kwargs)
        self.add_patch(patch)
        if baseline is None and fill:
            _api.warn_external(
                f"Both {baseline=} and {fill=} have been passed. "
                "baseline=None is only intended for unfilled stair plots. "
                "Because baseline is None, the Path used to draw the stairs will "
                "not be closed, thus because fill is True the polygon will be closed "
                "by drawing an (unstroked) edge from the first to last point.  It is "
                "very likely that the resulting fill patterns is not the desired "
                "result."
            )

        if baseline is not None:
            if orientation == 'vertical':
                patch.sticky_edges.y.append(np.min(baseline))
                self.update_datalim([(edges[0], np.min(baseline))])
            else:
                patch.sticky_edges.x.append(np.min(baseline))
                self.update_datalim([(np.min(baseline), edges[0])])
        self._request_autoscale_view()
        return patch

    @_api.make_keyword_only("3.10", "range")
    @_preprocess_data(replace_names=["x", "y", "weights"])
    @_docstring.interpd
    def hist2d(self, x, y, bins=10, range=None, density=False, weights=None,
               cmin=None, cmax=None, **kwargs):
        """
        Make a 2D histogram plot.

        Parameters
        ----------
        x, y : array-like, shape (n, )
            Input values

        bins : None or int or [int, int] or array-like or [array, array]

            The bin specification:

            - If int, the number of bins for the two dimensions
              (``nx = ny = bins``).
            - If ``[int, int]``, the number of bins in each dimension
              (``nx, ny = bins``).
            - If array-like, the bin edges for the two dimensions
              (``x_edges = y_edges = bins``).
            - If ``[array, array]``, the bin edges in each dimension
              (``x_edges, y_edges = bins``).

            The default value is 10.

        range : array-like shape(2, 2), optional
            The leftmost and rightmost edges of the bins along each dimension
            (if not specified explicitly in the bins parameters): ``[[xmin,
            xmax], [ymin, ymax]]``. All values outside of this range will be
            considered outliers and not tallied in the histogram.

        density : bool, default: False
            Normalize histogram.  See the documentation for the *density*
            parameter of `~.Axes.hist` for more details.

        weights : array-like, shape (n, ), optional
            An array of values w_i weighing each sample (x_i, y_i).

        cmin, cmax : float, default: None
            All bins that has count less than *cmin* or more than *cmax* will not be
            displayed (set to NaN before passing to `~.Axes.pcolormesh`) and these count
            values in the return value count histogram will also be set to nan upon
            return.

        Returns
        -------
        h : 2D array
            The bi-dimensional histogram of samples x and y. Values in x are
            histogrammed along the first dimension and values in y are
            histogrammed along the second dimension.
        xedges : 1D array
            The bin edges along the x-axis.
        yedges : 1D array
            The bin edges along the y-axis.
        image : `~.matplotlib.collections.QuadMesh`

        Other Parameters
        ----------------
        %(cmap_doc)s

        %(norm_doc)s

        %(vmin_vmax_doc)s

        %(colorizer_doc)s

        alpha : ``0 <= scalar <= 1`` or ``None``, optional
            The alpha blending value.

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Additional parameters are passed along to the
            `~.Axes.pcolormesh` method and `~matplotlib.collections.QuadMesh`
            constructor.

        See Also
        --------
        hist : 1D histogram plotting
        hexbin : 2D histogram with hexagonal bins

        Notes
        -----
        - Currently ``hist2d`` calculates its own axis limits, and any limits
          previously set are ignored.
        - Rendering the histogram with a logarithmic color scale is
          accomplished by passing a `.colors.LogNorm` instance to the *norm*
          keyword argument. Likewise, power-law normalization (similar
          in effect to gamma correction) can be accomplished with
          `.colors.PowerNorm`.
        """

        h, xedges, yedges = np.histogram2d(x, y, bins=bins, range=range,
                                           density=density, weights=weights)

        if cmin is not None:
            h[h < cmin] = None
        if cmax is not None:
            h[h > cmax] = None

        pc = self.pcolormesh(xedges, yedges, h.T, **kwargs)
        self.set_xlim(xedges[0], xedges[-1])
        self.set_ylim(yedges[0], yedges[-1])

        return h, xedges, yedges, pc

    @_preprocess_data(replace_names=["x", "weights"], label_namer="x")
    @_docstring.interpd
    def ecdf(self, x, weights=None, *, complementary=False,
             orientation="vertical", compress=False, **kwargs):
        """
        Compute and plot the empirical cumulative distribution function of *x*.

        .. versionadded:: 3.8

        Parameters
        ----------
        x : 1d array-like
            The input data.  Infinite entries are kept (and move the relevant
            end of the ecdf from 0/1), but NaNs and masked values are errors.

        weights : 1d array-like or None, default: None
            The weights of the entries; must have the same shape as *x*.
            Weights corresponding to NaN data points are dropped, and then the
            remaining weights are normalized to sum to 1.  If unset, all
            entries have the same weight.

        complementary : bool, default: False
            Whether to plot a cumulative distribution function, which increases
            from 0 to 1 (the default), or a complementary cumulative
            distribution function, which decreases from 1 to 0.

        orientation : {"vertical", "horizontal"}, default: "vertical"
            Whether the entries are plotted along the x-axis ("vertical", the
            default) or the y-axis ("horizontal").  This parameter takes the
            same values as in `~.Axes.hist`.

        compress : bool, default: False
            Whether multiple entries with the same values are grouped together
            (with a summed weight) before plotting.  This is mainly useful if
            *x* contains many identical data points, to decrease the rendering
            complexity of the plot. If *x* contains no duplicate points, this
            has no effect and just uses some time and memory.

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Keyword arguments control the `.Line2D` properties:

            %(Line2D:kwdoc)s

        Returns
        -------
        `.Line2D`

        Notes
        -----
        The ecdf plot can be thought of as a cumulative histogram with one bin
        per data entry; i.e. it reports on the entire dataset without any
        arbitrary binning.

        If *x* contains NaNs or masked entries, either remove them first from
        the array (if they should not taken into account), or replace them by
        -inf or +inf (if they should be sorted at the beginning or the end of
        the array).
        """
        _api.check_in_list(["horizontal", "vertical"], orientation=orientation)
        if "drawstyle" in kwargs or "ds" in kwargs:
            raise TypeError("Cannot pass 'drawstyle' or 'ds' to ecdf()")
        if np.ma.getmask(x).any():
            raise ValueError("ecdf() does not support masked entries")
        x = np.asarray(x)
        if np.isnan(x).any():
            raise ValueError("ecdf() does not support NaNs")
        argsort = np.argsort(x)
        x = x[argsort]
        if weights is None:
            # Ensure that we end at exactly 1, avoiding floating point errors.
            cum_weights = (1 + np.arange(len(x))) / len(x)
        else:
            weights = np.take(weights, argsort)   # Reorder weights like we reordered x.
            cum_weights = np.cumsum(weights / np.sum(weights))
        if compress:
            # Get indices of unique x values.
            compress_idxs = [0, *(x[:-1] != x[1:]).nonzero()[0] + 1]
            x = x[compress_idxs]
            cum_weights = cum_weights[compress_idxs]
        if orientation == "vertical":
            if not complementary:
                line, = self.plot([x[0], *x], [0, *cum_weights],
                                  drawstyle="steps-post", **kwargs)
            else:
                line, = self.plot([*x, x[-1]], [1, *1 - cum_weights],
                                  drawstyle="steps-pre", **kwargs)
            line.sticky_edges.y[:] = [0, 1]
        else:  # orientation == "horizontal":
            if not complementary:
                line, = self.plot([0, *cum_weights], [x[0], *x],
                                  drawstyle="steps-pre", **kwargs)
            else:
                line, = self.plot([1, *1 - cum_weights], [*x, x[-1]],
                                  drawstyle="steps-post", **kwargs)
            line.sticky_edges.x[:] = [0, 1]
        return line

    @_api.make_keyword_only("3.10", "NFFT")
    @_preprocess_data(replace_names=["x"])
    @_docstring.interpd
    def psd(self, x, NFFT=None, Fs=None, Fc=None, detrend=None,
            window=None, noverlap=None, pad_to=None,
            sides=None, scale_by_freq=None, return_line=None, **kwargs):
        r"""
        Plot the power spectral density.

        The power spectral density :math:`P_{xx}` by Welch's average
        periodogram method.  The vector *x* is divided into *NFFT* length
        segments.  Each segment is detrended by function *detrend* and
        windowed by function *window*.  *noverlap* gives the length of
        the overlap between segments.  The :math:`|\mathrm{fft}(i)|^2`
        of each segment :math:`i` are averaged to compute :math:`P_{xx}`,
        with a scaling to correct for power loss due to windowing.

        If len(*x*) < *NFFT*, it will be zero padded to *NFFT*.

        Parameters
        ----------
        x : 1-D array or sequence
            Array or sequence containing the data

        %(Spectral)s

        %(PSD)s

        noverlap : int, default: 0 (no overlap)
            The number of points of overlap between segments.

        Fc : int, default: 0
            The center frequency of *x*, which offsets the x extents of the
            plot to reflect the frequency range used when a signal is acquired
            and then filtered and downsampled to baseband.

        return_line : bool, default: False
            Whether to include the line object plotted in the returned values.

        Returns
        -------
        Pxx : 1-D array
            The values for the power spectrum :math:`P_{xx}` before scaling
            (real valued).

        freqs : 1-D array
            The frequencies corresponding to the elements in *Pxx*.

        line : `~matplotlib.lines.Line2D`
            The line created by this function.
            Only returned if *return_line* is True.

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Keyword arguments control the `.Line2D` properties:

            %(Line2D:kwdoc)s

        See Also
        --------
        specgram
            Differs in the default overlap; in not returning the mean of the
            segment periodograms; in returning the times of the segments; and
            in plotting a colormap instead of a line.
        magnitude_spectrum
            Plots the magnitude spectrum.
        csd
            Plots the spectral density between two signals.

        Notes
        -----
        For plotting, the power is plotted as
        :math:`10\log_{10}(P_{xx})` for decibels, though *Pxx* itself
        is returned.

        References
        ----------
        Bendat & Piersol -- Random Data: Analysis and Measurement Procedures,
        John Wiley & Sons (1986)
        """
        if Fc is None:
            Fc = 0

        pxx, freqs = mlab.psd(x=x, NFFT=NFFT, Fs=Fs, detrend=detrend,
                              window=window, noverlap=noverlap, pad_to=pad_to,
                              sides=sides, scale_by_freq=scale_by_freq)
        freqs += Fc

        if scale_by_freq in (None, True):
            psd_units = 'dB/Hz'
        else:
            psd_units = 'dB'

        line = self.plot(freqs, 10 * np.log10(pxx), **kwargs)
        self.set_xlabel('Frequency')
        self.set_ylabel('Power Spectral Density (%s)' % psd_units)
        self.grid(True)

        vmin, vmax = self.get_ybound()
        step = max(10 * int(np.log10(vmax - vmin)), 1)
        ticks = np.arange(math.floor(vmin), math.ceil(vmax) + 1, step)
        self.set_yticks(ticks)

        if return_line is None or not return_line:
            return pxx, freqs
        else:
            return pxx, freqs, line

    @_api.make_keyword_only("3.10", "NFFT")
    @_preprocess_data(replace_names=["x", "y"], label_namer="y")
    @_docstring.interpd
    def csd(self, x, y, NFFT=None, Fs=None, Fc=None, detrend=None,
            window=None, noverlap=None, pad_to=None,
            sides=None, scale_by_freq=None, return_line=None, **kwargs):
        r"""
        Plot the cross-spectral density.

        The cross spectral density :math:`P_{xy}` by Welch's average
        periodogram method.  The vectors *x* and *y* are divided into
        *NFFT* length segments.  Each segment is detrended by function
        *detrend* and windowed by function *window*.  *noverlap* gives
        the length of the overlap between segments.  The product of
        the direct FFTs of *x* and *y* are averaged over each segment
        to compute :math:`P_{xy}`, with a scaling to correct for power
        loss due to windowing.

        If len(*x*) < *NFFT* or len(*y*) < *NFFT*, they will be zero
        padded to *NFFT*.

        Parameters
        ----------
        x, y : 1-D arrays or sequences
            Arrays or sequences containing the data.

        %(Spectral)s

        %(PSD)s

        noverlap : int, default: 0 (no overlap)
            The number of points of overlap between segments.

        Fc : int, default: 0
            The center frequency of *x*, which offsets the x extents of the
            plot to reflect the frequency range used when a signal is acquired
            and then filtered and downsampled to baseband.

        return_line : bool, default: False
            Whether to include the line object plotted in the returned values.

        Returns
        -------
        Pxy : 1-D array
            The values for the cross spectrum :math:`P_{xy}` before scaling
            (complex valued).

        freqs : 1-D array
            The frequencies corresponding to the elements in *Pxy*.

        line : `~matplotlib.lines.Line2D`
            The line created by this function.
            Only returned if *return_line* is True.

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Keyword arguments control the `.Line2D` properties:

            %(Line2D:kwdoc)s

        See Also
        --------
        psd : is equivalent to setting ``y = x``.

        Notes
        -----
        For plotting, the power is plotted as
        :math:`10 \log_{10}(P_{xy})` for decibels, though :math:`P_{xy}` itself
        is returned.

        References
        ----------
        Bendat & Piersol -- Random Data: Analysis and Measurement Procedures,
        John Wiley & Sons (1986)
        """
        if Fc is None:
            Fc = 0

        pxy, freqs = mlab.csd(x=x, y=y, NFFT=NFFT, Fs=Fs, detrend=detrend,
                              window=window, noverlap=noverlap, pad_to=pad_to,
                              sides=sides, scale_by_freq=scale_by_freq)
        # pxy is complex
        freqs += Fc

        line = self.plot(freqs, 10 * np.log10(np.abs(pxy)), **kwargs)
        self.set_xlabel('Frequency')
        self.set_ylabel('Cross Spectrum Magnitude (dB)')
        self.grid(True)

        vmin, vmax = self.get_ybound()
        step = max(10 * int(np.log10(vmax - vmin)), 1)
        ticks = np.arange(math.floor(vmin), math.ceil(vmax) + 1, step)
        self.set_yticks(ticks)

        if return_line is None or not return_line:
            return pxy, freqs
        else:
            return pxy, freqs, line

    @_api.make_keyword_only("3.10", "Fs")
    @_preprocess_data(replace_names=["x"])
    @_docstring.interpd
    def magnitude_spectrum(self, x, Fs=None, Fc=None, window=None,
                           pad_to=None, sides=None, scale=None,
                           **kwargs):
        """
        Plot the magnitude spectrum.

        Compute the magnitude spectrum of *x*.  Data is padded to a
        length of *pad_to* and the windowing function *window* is applied to
        the signal.

        Parameters
        ----------
        x : 1-D array or sequence
            Array or sequence containing the data.

        %(Spectral)s

        %(Single_Spectrum)s

        scale : {'default', 'linear', 'dB'}
            The scaling of the values in the *spec*.  'linear' is no scaling.
            'dB' returns the values in dB scale, i.e., the dB amplitude
            (20 * log10). 'default' is 'linear'.

        Fc : int, default: 0
            The center frequency of *x*, which offsets the x extents of the
            plot to reflect the frequency range used when a signal is acquired
            and then filtered and downsampled to baseband.

        Returns
        -------
        spectrum : 1-D array
            The values for the magnitude spectrum before scaling (real valued).

        freqs : 1-D array
            The frequencies corresponding to the elements in *spectrum*.

        line : `~matplotlib.lines.Line2D`
            The line created by this function.

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Keyword arguments control the `.Line2D` properties:

            %(Line2D:kwdoc)s

        See Also
        --------
        psd
            Plots the power spectral density.
        angle_spectrum
            Plots the angles of the corresponding frequencies.
        phase_spectrum
            Plots the phase (unwrapped angle) of the corresponding frequencies.
        specgram
            Can plot the magnitude spectrum of segments within the signal in a
            colormap.
        """
        if Fc is None:
            Fc = 0

        spec, freqs = mlab.magnitude_spectrum(x=x, Fs=Fs, window=window,
                                              pad_to=pad_to, sides=sides)
        freqs += Fc

        yunits = _api.check_getitem(
            {None: 'energy', 'default': 'energy', 'linear': 'energy',
             'dB': 'dB'},
            scale=scale)
        if yunits == 'energy':
            Z = spec
        else:  # yunits == 'dB'
            Z = 20. * np.log10(spec)

        line, = self.plot(freqs, Z, **kwargs)
        self.set_xlabel('Frequency')
        self.set_ylabel('Magnitude (%s)' % yunits)

        return spec, freqs, line

    @_api.make_keyword_only("3.10", "Fs")
    @_preprocess_data(replace_names=["x"])
    @_docstring.interpd
    def angle_spectrum(self, x, Fs=None, Fc=None, window=None,
                       pad_to=None, sides=None, **kwargs):
        """
        Plot the angle spectrum.

        Compute the angle spectrum (wrapped phase spectrum) of *x*.
        Data is padded to a length of *pad_to* and the windowing function
        *window* is applied to the signal.

        Parameters
        ----------
        x : 1-D array or sequence
            Array or sequence containing the data.

        %(Spectral)s

        %(Single_Spectrum)s

        Fc : int, default: 0
            The center frequency of *x*, which offsets the x extents of the
            plot to reflect the frequency range used when a signal is acquired
            and then filtered and downsampled to baseband.

        Returns
        -------
        spectrum : 1-D array
            The values for the angle spectrum in radians (real valued).

        freqs : 1-D array
            The frequencies corresponding to the elements in *spectrum*.

        line : `~matplotlib.lines.Line2D`
            The line created by this function.

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Keyword arguments control the `.Line2D` properties:

            %(Line2D:kwdoc)s

        See Also
        --------
        magnitude_spectrum
            Plots the magnitudes of the corresponding frequencies.
        phase_spectrum
            Plots the unwrapped version of this function.
        specgram
            Can plot the angle spectrum of segments within the signal in a
            colormap.
        """
        if Fc is None:
            Fc = 0

        spec, freqs = mlab.angle_spectrum(x=x, Fs=Fs, window=window,
                                          pad_to=pad_to, sides=sides)
        freqs += Fc

        lines = self.plot(freqs, spec, **kwargs)
        self.set_xlabel('Frequency')
        self.set_ylabel('Angle (radians)')

        return spec, freqs, lines[0]

    @_api.make_keyword_only("3.10", "Fs")
    @_preprocess_data(replace_names=["x"])
    @_docstring.interpd
    def phase_spectrum(self, x, Fs=None, Fc=None, window=None,
                       pad_to=None, sides=None, **kwargs):
        """
        Plot the phase spectrum.

        Compute the phase spectrum (unwrapped angle spectrum) of *x*.
        Data is padded to a length of *pad_to* and the windowing function
        *window* is applied to the signal.

        Parameters
        ----------
        x : 1-D array or sequence
            Array or sequence containing the data

        %(Spectral)s

        %(Single_Spectrum)s

        Fc : int, default: 0
            The center frequency of *x*, which offsets the x extents of the
            plot to reflect the frequency range used when a signal is acquired
            and then filtered and downsampled to baseband.

        Returns
        -------
        spectrum : 1-D array
            The values for the phase spectrum in radians (real valued).

        freqs : 1-D array
            The frequencies corresponding to the elements in *spectrum*.

        line : `~matplotlib.lines.Line2D`
            The line created by this function.

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Keyword arguments control the `.Line2D` properties:

            %(Line2D:kwdoc)s

        See Also
        --------
        magnitude_spectrum
            Plots the magnitudes of the corresponding frequencies.
        angle_spectrum
            Plots the wrapped version of this function.
        specgram
            Can plot the phase spectrum of segments within the signal in a
            colormap.
        """
        if Fc is None:
            Fc = 0

        spec, freqs = mlab.phase_spectrum(x=x, Fs=Fs, window=window,
                                          pad_to=pad_to, sides=sides)
        freqs += Fc

        lines = self.plot(freqs, spec, **kwargs)
        self.set_xlabel('Frequency')
        self.set_ylabel('Phase (radians)')

        return spec, freqs, lines[0]

    @_api.make_keyword_only("3.10", "NFFT")
    @_preprocess_data(replace_names=["x", "y"])
    @_docstring.interpd
    def cohere(self, x, y, NFFT=256, Fs=2, Fc=0, detrend=mlab.detrend_none,
               window=mlab.window_hanning, noverlap=0, pad_to=None,
               sides='default', scale_by_freq=None, **kwargs):
        r"""
        Plot the coherence between *x* and *y*.

        Coherence is the normalized cross spectral density:

        .. math::

          C_{xy} = \frac{|P_{xy}|^2}{P_{xx}P_{yy}}

        Parameters
        ----------
        %(Spectral)s

        %(PSD)s

        noverlap : int, default: 0 (no overlap)
            The number of points of overlap between blocks.

        Fc : int, default: 0
            The center frequency of *x*, which offsets the x extents of the
            plot to reflect the frequency range used when a signal is acquired
            and then filtered and downsampled to baseband.

        Returns
        -------
        Cxy : 1-D array
            The coherence vector.

        freqs : 1-D array
            The frequencies for the elements in *Cxy*.

        Other Parameters
        ----------------
        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        **kwargs
            Keyword arguments control the `.Line2D` properties:

            %(Line2D:kwdoc)s

        References
        ----------
        Bendat & Piersol -- Random Data: Analysis and Measurement Procedures,
        John Wiley & Sons (1986)
        """
        cxy, freqs = mlab.cohere(x=x, y=y, NFFT=NFFT, Fs=Fs, detrend=detrend,
                                 window=window, noverlap=noverlap,
                                 scale_by_freq=scale_by_freq, sides=sides,
                                 pad_to=pad_to)
        freqs += Fc

        self.plot(freqs, cxy, **kwargs)
        self.set_xlabel('Frequency')
        self.set_ylabel('Coherence')
        self.grid(True)

        return cxy, freqs

    @_api.make_keyword_only("3.10", "NFFT")
    @_preprocess_data(replace_names=["x"])
    @_docstring.interpd
    def specgram(self, x, NFFT=None, Fs=None, Fc=None, detrend=None,
                 window=None, noverlap=None,
                 cmap=None, xextent=None, pad_to=None, sides=None,
                 scale_by_freq=None, mode=None, scale=None,
                 vmin=None, vmax=None, **kwargs):
        """
        Plot a spectrogram.

        Compute and plot a spectrogram of data in *x*.  Data are split into
        *NFFT* length segments and the spectrum of each section is
        computed.  The windowing function *window* is applied to each
        segment, and the amount of overlap of each segment is
        specified with *noverlap*. The spectrogram is plotted as a colormap
        (using imshow).

        Parameters
        ----------
        x : 1-D array or sequence
            Array or sequence containing the data.

        %(Spectral)s

        %(PSD)s

        mode : {'default', 'psd', 'magnitude', 'angle', 'phase'}
            What sort of spectrum to use.  Default is 'psd', which takes the
            power spectral density.  'magnitude' returns the magnitude
            spectrum.  'angle' returns the phase spectrum without unwrapping.
            'phase' returns the phase spectrum with unwrapping.

        noverlap : int, default: 128
            The number of points of overlap between blocks.

        scale : {'default', 'linear', 'dB'}
            The scaling of the values in the *spec*.  'linear' is no scaling.
            'dB' returns the values in dB scale.  When *mode* is 'psd',
            this is dB power (10 * log10).  Otherwise, this is dB amplitude
            (20 * log10). 'default' is 'dB' if *mode* is 'psd' or
            'magnitude' and 'linear' otherwise.  This must be 'linear'
            if *mode* is 'angle' or 'phase'.

        Fc : int, default: 0
            The center frequency of *x*, which offsets the x extents of the
            plot to reflect the frequency range used when a signal is acquired
            and then filtered and downsampled to baseband.

        cmap : `.Colormap`, default: :rc:`image.cmap`

        xextent : *None* or (xmin, xmax)
            The image extent along the x-axis. The default sets *xmin* to the
            left border of the first bin (*spectrum* column) and *xmax* to the
            right border of the last bin. Note that for *noverlap>0* the width
            of the bins is smaller than those of the segments.

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        vmin, vmax : float, optional
            vmin and vmax define the data range that the colormap covers.
            By default, the colormap covers the complete value range of the
            data.

        **kwargs
            Additional keyword arguments are passed on to `~.axes.Axes.imshow`
            which makes the specgram image. The origin keyword argument
            is not supported.

        Returns
        -------
        spectrum : 2D array
            Columns are the periodograms of successive segments.

        freqs : 1-D array
            The frequencies corresponding to the rows in *spectrum*.

        t : 1-D array
            The times corresponding to midpoints of segments (i.e., the columns
            in *spectrum*).

        im : `.AxesImage`
            The image created by imshow containing the spectrogram.

        See Also
        --------
        psd
            Differs in the default overlap; in returning the mean of the
            segment periodograms; in not returning times; and in generating a
            line plot instead of colormap.
        magnitude_spectrum
            A single spectrum, similar to having a single segment when *mode*
            is 'magnitude'. Plots a line instead of a colormap.
        angle_spectrum
            A single spectrum, similar to having a single segment when *mode*
            is 'angle'. Plots a line instead of a colormap.
        phase_spectrum
            A single spectrum, similar to having a single segment when *mode*
            is 'phase'. Plots a line instead of a colormap.

        Notes
        -----
        The parameters *detrend* and *scale_by_freq* do only apply when *mode*
        is set to 'psd'.
        """
        if NFFT is None:
            NFFT = 256  # same default as in mlab.specgram()
        if Fc is None:
            Fc = 0  # same default as in mlab._spectral_helper()
        if noverlap is None:
            noverlap = 128  # same default as in mlab.specgram()
        if Fs is None:
            Fs = 2  # same default as in mlab._spectral_helper()

        if mode == 'complex':
            raise ValueError('Cannot plot a complex specgram')

        if scale is None or scale == 'default':
            if mode in ['angle', 'phase']:
                scale = 'linear'
            else:
                scale = 'dB'
        elif mode in ['angle', 'phase'] and scale == 'dB':
            raise ValueError('Cannot use dB scale with angle or phase mode')

        spec, freqs, t = mlab.specgram(x=x, NFFT=NFFT, Fs=Fs,
                                       detrend=detrend, window=window,
                                       noverlap=noverlap, pad_to=pad_to,
                                       sides=sides,
                                       scale_by_freq=scale_by_freq,
                                       mode=mode)

        if scale == 'linear':
            Z = spec
        elif scale == 'dB':
            if mode is None or mode == 'default' or mode == 'psd':
                Z = 10. * np.log10(spec)
            else:
                Z = 20. * np.log10(spec)
        else:
            raise ValueError(f'Unknown scale {scale!r}')

        Z = np.flipud(Z)

        if xextent is None:
            # padding is needed for first and last segment:
            pad_xextent = (NFFT-noverlap) / Fs / 2
            xextent = np.min(t) - pad_xextent, np.max(t) + pad_xextent
        xmin, xmax = xextent
        freqs += Fc
        extent = xmin, xmax, freqs[0], freqs[-1]

        if 'origin' in kwargs:
            raise _api.kwarg_error("specgram", "origin")

        im = self.imshow(Z, cmap, extent=extent, vmin=vmin, vmax=vmax,
                         origin='upper', **kwargs)
        self.axis('auto')

        return spec, freqs, t, im

    @_api.make_keyword_only("3.10", "precision")
    @_docstring.interpd
    def spy(self, Z, precision=0, marker=None, markersize=None,
            aspect='equal', origin="upper", **kwargs):
        """
        Plot the sparsity pattern of a 2D array.

        This visualizes the non-zero values of the array.

        Two plotting styles are available: image and marker. Both
        are available for full arrays, but only the marker style
        works for `scipy.sparse.spmatrix` instances.

        **Image style**

        If *marker* and *markersize* are *None*, `~.Axes.imshow` is used. Any
        extra remaining keyword arguments are passed to this method.

        **Marker style**

        If *Z* is a `scipy.sparse.spmatrix` or *marker* or *markersize* are
        *None*, a `.Line2D` object will be returned with the value of marker
        determining the marker type, and any remaining keyword arguments
        passed to `~.Axes.plot`.

        Parameters
        ----------
        Z : (M, N) array-like
            The array to be plotted.

        precision : float or 'present', default: 0
            If *precision* is 0, any non-zero value will be plotted. Otherwise,
            values of :math:`|Z| > precision` will be plotted.

            For `scipy.sparse.spmatrix` instances, you can also
            pass 'present'. In this case any value present in the array
            will be plotted, even if it is identically zero.

        aspect : {'equal', 'auto', None} or float, default: 'equal'
            The aspect ratio of the Axes.  This parameter is particularly
            relevant for images since it determines whether data pixels are
            square.

            This parameter is a shortcut for explicitly calling
            `.Axes.set_aspect`. See there for further details.

            - 'equal': Ensures an aspect ratio of 1. Pixels will be square.
            - 'auto': The Axes is kept fixed and the aspect is adjusted so
              that the data fit in the Axes. In general, this will result in
              non-square pixels.
            - *None*: Use :rc:`image.aspect`.

        origin : {'upper', 'lower'}, default: :rc:`image.origin`
            Place the [0, 0] index of the array in the upper left or lower left
            corner of the Axes. The convention 'upper' is typically used for
            matrices and images.

        Returns
        -------
        `~matplotlib.image.AxesImage` or `.Line2D`
            The return type depends on the plotting style (see above).

        Other Parameters
        ----------------
        **kwargs
            The supported additional parameters depend on the plotting style.

            For the image style, you can pass the following additional
            parameters of `~.Axes.imshow`:

            - *cmap*
            - *alpha*
            - *url*
            - any `.Artist` properties (passed on to the `.AxesImage`)

            For the marker style, you can pass any `.Line2D` property except
            for *linestyle*:

            %(Line2D:kwdoc)s
        """
        if marker is None and markersize is None and hasattr(Z, 'tocoo'):
            marker = 's'
        _api.check_in_list(["upper", "lower"], origin=origin)
        if marker is None and markersize is None:
            Z = np.asarray(Z)
            mask = np.abs(Z) > precision

            if 'cmap' not in kwargs:
                kwargs['cmap'] = mcolors.ListedColormap(['w', 'k'],
                                                        name='binary')
            if 'interpolation' in kwargs:
                raise _api.kwarg_error("spy", "interpolation")
            if 'norm' not in kwargs:
                kwargs['norm'] = mcolors.NoNorm()
            ret = self.imshow(mask, interpolation='nearest',
                              aspect=aspect, origin=origin,
                              **kwargs)
        else:
            if hasattr(Z, 'tocoo'):
                c = Z.tocoo()
                if precision == 'present':
                    y = c.row
                    x = c.col
                else:
                    nonzero = np.abs(c.data) > precision
                    y = c.row[nonzero]
                    x = c.col[nonzero]
            else:
                Z = np.asarray(Z)
                nonzero = np.abs(Z) > precision
                y, x = np.nonzero(nonzero)
            if marker is None:
                marker = 's'
            if markersize is None:
                markersize = 10
            if 'linestyle' in kwargs:
                raise _api.kwarg_error("spy", "linestyle")
            ret = mlines.Line2D(
                x, y, linestyle='None', marker=marker, markersize=markersize,
                **kwargs)
            self.add_line(ret)
            nr, nc = Z.shape
            self.set_xlim(-0.5, nc - 0.5)
            if origin == "upper":
                self.set_ylim(nr - 0.5, -0.5)
            else:
                self.set_ylim(-0.5, nr - 0.5)
            self.set_aspect(aspect)
        self.title.set_y(1.05)
        if origin == "upper":
            self.xaxis.tick_top()
        else:  # lower
            self.xaxis.tick_bottom()
        self.xaxis.set_ticks_position('both')
        self.xaxis.set_major_locator(
            mticker.MaxNLocator(nbins=9, steps=[1, 2, 5, 10], integer=True))
        self.yaxis.set_major_locator(
            mticker.MaxNLocator(nbins=9, steps=[1, 2, 5, 10], integer=True))
        return ret

    def matshow(self, Z, **kwargs):
        """
        Plot the values of a 2D matrix or array as color-coded image.

        The matrix will be shown the way it would be printed, with the first
        row at the top.  Row and column numbering is zero-based.

        Parameters
        ----------
        Z : (M, N) array-like
            The matrix to be displayed.

        Returns
        -------
        `~matplotlib.image.AxesImage`

        Other Parameters
        ----------------
        **kwargs : `~matplotlib.axes.Axes.imshow` arguments

        See Also
        --------
        imshow : More general function to plot data on a 2D regular raster.

        Notes
        -----
        This is just a convenience function wrapping `.imshow` to set useful
        defaults for displaying a matrix. In particular:

        - Set ``origin='upper'``.
        - Set ``interpolation='nearest'``.
        - Set ``aspect='equal'``.
        - Ticks are placed to the left and above.
        - Ticks are formatted to show integer indices.

        """
        Z = np.asanyarray(Z)
        kw = {'origin': 'upper',
              'interpolation': 'nearest',
              'aspect': 'equal',          # (already the imshow default)
              **kwargs}
        im = self.imshow(Z, **kw)
        self.title.set_y(1.05)
        self.xaxis.tick_top()
        self.xaxis.set_ticks_position('both')
        self.xaxis.set_major_locator(
            mticker.MaxNLocator(nbins=9, steps=[1, 2, 5, 10], integer=True))
        self.yaxis.set_major_locator(
            mticker.MaxNLocator(nbins=9, steps=[1, 2, 5, 10], integer=True))
        return im

    @_api.make_keyword_only("3.10", "vert")
    @_preprocess_data(replace_names=["dataset"])
    def violinplot(self, dataset, positions=None, vert=None,
                   orientation='vertical', widths=0.5, showmeans=False,
                   showextrema=True, showmedians=False, quantiles=None,
                   points=100, bw_method=None, side='both',):
        """
        Make a violin plot.

        Make a violin plot for each column of *dataset* or each vector in
        sequence *dataset*.  Each filled area extends to represent the
        entire data range, with optional lines at the mean, the median,
        the minimum, the maximum, and user-specified quantiles.

        Parameters
        ----------
        dataset : Array or a sequence of vectors.
            The input data.

        positions : array-like, default: [1, 2, ..., n]
            The positions of the violins; i.e. coordinates on the x-axis for
            vertical violins (or y-axis for horizontal violins).

        vert : bool, optional
            .. deprecated:: 3.10
                Use *orientation* instead.

                If this is given during the deprecation period, it overrides
                the *orientation* parameter.

            If True, plots the violins vertically.
            If False, plots the violins horizontally.

        orientation : {'vertical', 'horizontal'}, default: 'vertical'
            If 'horizontal', plots the violins horizontally.
            Otherwise, plots the violins vertically.

            .. versionadded:: 3.10

        widths : float or array-like, default: 0.5
            The maximum width of each violin in units of the *positions* axis.
            The default is 0.5, which is half the available space when using default
            *positions*.

        showmeans : bool, default: False
            Whether to show the mean with a line.

        showextrema : bool, default: True
            Whether to show extrema with a line.

        showmedians : bool, default: False
            Whether to show the median with a line.

        quantiles : array-like, default: None
            If not None, set a list of floats in interval [0, 1] for each violin,
            which stands for the quantiles that will be rendered for that
            violin.

        points : int, default: 100
            The number of points to evaluate each of the gaussian kernel density
            estimations at.

        bw_method : {'scott', 'silverman'} or float or callable, default: 'scott'
            The method used to calculate the estimator bandwidth.  If a
            float, this will be used directly as `kde.factor`.  If a
            callable, it should take a `matplotlib.mlab.GaussianKDE` instance as
            its only parameter and return a float.

        side : {'both', 'low', 'high'}, default: 'both'
            'both' plots standard violins. 'low'/'high' only
            plots the side below/above the positions value.

        data : indexable object, optional
            DATA_PARAMETER_PLACEHOLDER

        Returns
        -------
        dict
            A dictionary mapping each component of the violinplot to a
            list of the corresponding collection instances created. The
            dictionary has the following keys:

            - ``bodies``: A list of the `~.collections.PolyCollection`
              instances containing the filled area of each violin.

            - ``cmeans``: A `~.collections.LineCollection` instance that marks
              the mean values of each of the violin's distribution.

            - ``cmins``: A `~.collections.LineCollection` instance that marks
              the bottom of each violin's distribution.

            - ``cmaxes``: A `~.collections.LineCollection` instance that marks
              the top of each violin's distribution.

            - ``cbars``: A `~.collections.LineCollection` instance that marks
              the centers of each violin's distribution.

            - ``cmedians``: A `~.collections.LineCollection` instance that
              marks the median values of each of the violin's distribution.

            - ``cquantiles``: A `~.collections.LineCollection` instance created
              to identify the quantile values of each of the violin's
              distribution.

        See Also
        --------
        .Axes.violin : Draw a violin from pre-computed statistics.
        boxplot : Draw a box and whisker plot.
        """

        def _kde_method(X, coords):
            # Unpack in case of e.g. Pandas or xarray object
            X = cbook._unpack_to_numpy(X)
            # fallback gracefully if the vector contains only one value
            if np.all(X[0] == X):
                return (X[0] == coords).astype(float)
            kde = mlab.GaussianKDE(X, bw_method)
            return kde.evaluate(coords)

        vpstats = cbook.violin_stats(dataset, _kde_method, points=points,
                                     quantiles=quantiles)
        return self.violin(vpstats, positions=positions, vert=vert,
                           orientation=orientation, widths=widths,
                           showmeans=showmeans, showextrema=showextrema,
                           showmedians=showmedians, side=side)

    @_api.make_keyword_only("3.10", "vert")
    def violin(self, vpstats, positions=None, vert=None,
               orientation='vertical', widths=0.5, showmeans=False,
               showextrema=True, showmedians=False, side='both'):
        """
        Draw a violin plot from pre-computed statistics.

        Draw a violin plot for each column of *vpstats*. Each filled area
        extends to represent the entire data range, with optional lines at the
        mean, the median, the minimum, the maximum, and the quantiles values.

        Parameters
        ----------
        vpstats : list of dicts
            A list of dictionaries containing stats for each violin plot.
            Required keys are:

            - ``coords``: A list of scalars containing the coordinates that
              the violin's kernel density estimate were evaluated at.

            - ``vals``: A list of scalars containing the values of the
              kernel density estimate at each of the coordinates given
              in *coords*.

            - ``mean``: The mean value for this violin's dataset.

            - ``median``: The median value for this violin's dataset.

            - ``min``: The minimum value for this violin's dataset.

            - ``max``: The maximum value for this violin's dataset.

            Optional keys are:

            - ``quantiles``: A list of scalars containing the quantile values
              for this violin's dataset.

        positions : array-like, default: [1, 2, ..., n]
            The positions of the violins; i.e. coordinates on the x-axis for
            vertical violins (or y-axis for horizontal violins).

        vert : bool, optional
            .. deprecated:: 3.10
                Use *orientation* instead.

                If this is given during the deprecation period, it overrides
                the *orientation* parameter.

            If True, plots the violins vertically.
            If False, plots the violins horizontally.

        orientation : {'vertical', 'horizontal'}, default: 'vertical'
            If 'horizontal', plots the violins horizontally.
            Otherwise, plots the violins vertically.

            .. versionadded:: 3.10

        widths : float or array-like, default: 0.5
            The maximum width of each violin in units of the *positions* axis.
            The default is 0.5, which is half available space when using default
            *positions*.

        showmeans : bool, default: False
            Whether to show the mean with a line.

        showextrema : bool, default: True
            Whether to show extrema with a line.

        showmedians : bool, default: False
            Whether to show the median with a line.

        side : {'both', 'low', 'high'}, default: 'both'
            'both' plots standard violins. 'low'/'high' only
            plots the side below/above the positions value.

        Returns
        -------
        dict
            A dictionary mapping each component of the violinplot to a
            list of the corresponding collection instances created. The
            dictionary has the following keys:

            - ``bodies``: A list of the `~.collections.PolyCollection`
              instances containing the filled area of each violin.

            - ``cmeans``: A `~.collections.LineCollection` instance that marks
              the mean values of each of the violin's distribution.

            - ``cmins``: A `~.collections.LineCollection` instance that marks
              the bottom of each violin's distribution.

            - ``cmaxes``: A `~.collections.LineCollection` instance that marks
              the top of each violin's distribution.

            - ``cbars``: A `~.collections.LineCollection` instance that marks
              the centers of each violin's distribution.

            - ``cmedians``: A `~.collections.LineCollection` instance that
              marks the median values of each of the violin's distribution.

            - ``cquantiles``: A `~.collections.LineCollection` instance created
              to identify the quantiles values of each of the violin's
              distribution.

        See Also
        --------
        violinplot :
            Draw a violin plot from data instead of pre-computed statistics.
        """

        # Statistical quantities to be plotted on the violins
        means = []
        mins = []
        maxes = []
        medians = []
        quantiles = []

        qlens = []  # Number of quantiles in each dataset.

        artists = {}  # Collections to be returned

        N = len(vpstats)
        datashape_message = ("List of violinplot statistics and `{0}` "
                             "values must have the same length")

        # vert and orientation parameters are linked until vert's
        # deprecation period expires. If both are selected,
        # vert takes precedence.
        if vert is not None:
            _api.warn_deprecated(
                "3.11",
                name="vert: bool",
                alternative="orientation: {'vertical', 'horizontal'}",
                pending=True,
            )
            orientation = 'vertical' if vert else 'horizontal'
        _api.check_in_list(['horizontal', 'vertical'], orientation=orientation)

        # Validate positions
        if positions is None:
            positions = range(1, N + 1)
        elif len(positions) != N:
            raise ValueError(datashape_message.format("positions"))

        # Validate widths
        if np.isscalar(widths):
            widths = [widths] * N
        elif len(widths) != N:
            raise ValueError(datashape_message.format("widths"))

        # Validate side
        _api.check_in_list(["both", "low", "high"], side=side)

        # Calculate ranges for statistics lines (shape (2, N)).
        line_ends = [[-0.25 if side in ['both', 'low'] else 0],
                     [0.25 if side in ['both', 'high'] else 0]] \
                          * np.array(widths) + positions

        # Colors.
        if mpl.rcParams['_internal.classic_mode']:
            fillcolor = 'y'
            linecolor = 'r'
        else:
            fillcolor = linecolor = self._get_lines.get_next_color()

        # Check whether we are rendering vertically or horizontally
        if orientation == 'vertical':
            fill = self.fill_betweenx
            if side in ['low', 'high']:
                perp_lines = functools.partial(self.hlines, colors=linecolor,
                                                capstyle='projecting')
                par_lines = functools.partial(self.vlines, colors=linecolor,
                                                capstyle='projecting')
            else:
                perp_lines = functools.partial(self.hlines, colors=linecolor)
                par_lines = functools.partial(self.vlines, colors=linecolor)
        else:
            fill = self.fill_between
            if side in ['low', 'high']:
                perp_lines = functools.partial(self.vlines, colors=linecolor,
                                                capstyle='projecting')
                par_lines = functools.partial(self.hlines, colors=linecolor,
                                                capstyle='projecting')
            else:
                perp_lines = functools.partial(self.vlines, colors=linecolor)
                par_lines = functools.partial(self.hlines, colors=linecolor)

        # Render violins
        bodies = []
        for stats, pos, width in zip(vpstats, positions, widths):
            # The 0.5 factor reflects the fact that we plot from v-p to v+p.
            vals = np.array(stats['vals'])
            vals = 0.5 * width * vals / vals.max()
            bodies += [fill(stats['coords'],
                            -vals + pos if side in ['both', 'low'] else pos,
                            vals + pos if side in ['both', 'high'] else pos,
                            facecolor=fillcolor, alpha=0.3)]
            means.append(stats['mean'])
            mins.append(stats['min'])
            maxes.append(stats['max'])
            medians.append(stats['median'])
            q = stats.get('quantiles')  # a list of floats, or None
            if q is None:
                q = []
            quantiles.extend(q)
            qlens.append(len(q))
        artists['bodies'] = bodies

        if showmeans:  # Render means
            artists['cmeans'] = perp_lines(means, *line_ends)
        if showextrema:  # Render extrema
            artists['cmaxes'] = perp_lines(maxes, *line_ends)
            artists['cmins'] = perp_lines(mins, *line_ends)
            artists['cbars'] = par_lines(positions, mins, maxes)
        if showmedians:  # Render medians
            artists['cmedians'] = perp_lines(medians, *line_ends)
        if quantiles:  # Render quantiles: each width is repeated qlen times.
            artists['cquantiles'] = perp_lines(
                quantiles, *np.repeat(line_ends, qlens, axis=1))

        return artists

    # Methods that are entirely implemented in other modules.

    table = _make_axes_method(mtable.table)

    # args can be either Y or y1, y2, ... and all should be replaced
    stackplot = _preprocess_data()(_make_axes_method(mstack.stackplot))

    streamplot = _preprocess_data(
            replace_names=["x", "y", "u", "v", "start_points"])(
        _make_axes_method(mstream.streamplot))

    tricontour = _make_axes_method(mtri.tricontour)
    tricontourf = _make_axes_method(mtri.tricontourf)
    tripcolor = _make_axes_method(mtri.tripcolor)
    triplot = _make_axes_method(mtri.triplot)

    def _get_aspect_ratio(self):
        """
        Convenience method to calculate the aspect ratio of the Axes in
        the display coordinate system.
        """
        figure_size = self.get_figure().get_size_inches()
        ll, ur = self.get_position() * figure_size
        width, height = ur - ll
        return height / (width * self.get_data_ratio())
