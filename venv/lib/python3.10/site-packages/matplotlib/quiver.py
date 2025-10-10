"""
Support for plotting vector fields.

Presently this contains Quiver and Barb. Quiver plots an arrow in the
direction of the vector, with the size of the arrow related to the
magnitude of the vector.

Barbs are like quiver in that they point along a vector, but
the magnitude of the vector is given schematically by the presence of barbs
or flags on the barb.

This will also become a home for things such as standard
deviation ellipses, which can and will be derived very easily from
the Quiver code.
"""

import math

import numpy as np
from numpy import ma

from matplotlib import _api, cbook, _docstring
import matplotlib.artist as martist
import matplotlib.collections as mcollections
from matplotlib.patches import CirclePolygon
import matplotlib.text as mtext
import matplotlib.transforms as transforms


_quiver_doc = """
Plot a 2D field of arrows.

Call signature::

  quiver([X, Y], U, V, [C], /, **kwargs)

*X*, *Y* define the arrow locations, *U*, *V* define the arrow directions, and
*C* optionally sets the color. The arguments *X*, *Y*, *U*, *V*, *C* are
positional-only.

**Arrow length**

The default settings auto-scales the length of the arrows to a reasonable size.
To change this behavior see the *scale* and *scale_units* parameters.

**Arrow shape**

The arrow shape is determined by *width*, *headwidth*, *headlength* and
*headaxislength*. See the notes below.

**Arrow styling**

Each arrow is internally represented by a filled polygon with a default edge
linewidth of 0. As a result, an arrow is rather a filled area, not a line with
a head, and `.PolyCollection` properties like *linewidth*, *edgecolor*,
*facecolor*, etc. act accordingly.


Parameters
----------
X, Y : 1D or 2D array-like, optional
    The x and y coordinates of the arrow locations.

    If not given, they will be generated as a uniform integer meshgrid based
    on the dimensions of *U* and *V*.

    If *X* and *Y* are 1D but *U*, *V* are 2D, *X*, *Y* are expanded to 2D
    using ``X, Y = np.meshgrid(X, Y)``. In this case ``len(X)`` and ``len(Y)``
    must match the column and row dimensions of *U* and *V*.

U, V : 1D or 2D array-like
    The x and y direction components of the arrow vectors. The interpretation
    of these components (in data or in screen space) depends on *angles*.

    *U* and *V* must have the same number of elements, matching the number of
    arrow locations in *X*, *Y*. *U* and *V* may be masked. Locations masked
    in any of *U*, *V*, and *C* will not be drawn.

C : 1D or 2D array-like, optional
    Numeric data that defines the arrow colors by colormapping via *norm* and
    *cmap*.

    This does not support explicit colors. If you want to set colors directly,
    use *color* instead.  The size of *C* must match the number of arrow
    locations.

angles : {'uv', 'xy'} or array-like, default: 'uv'
    Method for determining the angle of the arrows.

    - 'uv':  Arrow directions are based on
      :ref:`display coordinates <coordinate-systems>`; i.e. a 45° angle will
      always show up as diagonal on the screen, irrespective of figure or Axes
      aspect ratio or Axes data ranges. This is useful when the arrows represent
      a quantity whose direction is not tied to the x and y data coordinates.

      If *U* == *V* the orientation of the arrow on the plot is 45 degrees
      counter-clockwise from the horizontal axis (positive to the right).

    - 'xy': Arrow direction in data coordinates, i.e. the arrows point from
      (x, y) to (x+u, y+v). This is ideal for vector fields or gradient plots
      where the arrows should directly represent movements or gradients in the
      x and y directions.

    - Arbitrary angles may be specified explicitly as an array of values
      in degrees, counter-clockwise from the horizontal axis.

      In this case *U*, *V* is only used to determine the length of the
      arrows.

      For example, ``angles=[30, 60, 90]`` will orient the arrows at 30, 60, and 90
      degrees respectively, regardless of the *U* and *V* components.

    Note: inverting a data axis will correspondingly invert the
    arrows only with ``angles='xy'``.

pivot : {'tail', 'mid', 'middle', 'tip'}, default: 'tail'
    The part of the arrow that is anchored to the *X*, *Y* grid. The arrow
    rotates about this point.

    'mid' is a synonym for 'middle'.

scale : float, optional
    Scales the length of the arrow inversely.

    Number of data values represented by one unit of arrow length on the plot.
    For example, if the data represents velocity in meters per second (m/s), the
    scale parameter determines how many meters per second correspond to one unit of
    arrow length relative to the width of the plot.
    Smaller scale parameter makes the arrow longer.

    By default, an autoscaling algorithm is used to scale the arrow length to a
    reasonable size, which is based on the average vector length and the number of
    vectors.

    The arrow length unit is given by the *scale_units* parameter.

scale_units : {'width', 'height', 'dots', 'inches', 'x', 'y', 'xy'}, default: 'width'

    The physical image unit, which is used for rendering the scaled arrow data *U*, *V*.

    The rendered arrow length is given by

        length in x direction = $\\frac{u}{\\mathrm{scale}} \\mathrm{scale_unit}$

        length in y direction = $\\frac{v}{\\mathrm{scale}} \\mathrm{scale_unit}$

    For example, ``(u, v) = (0.5, 0)`` with ``scale=10, scale_units="width"`` results
    in a horizontal arrow with a length of *0.5 / 10 * "width"*, i.e. 0.05 times the
    Axes width.

    Supported values are:

    - 'width' or 'height': The arrow length is scaled relative to the width or height
       of the Axes.
       For example, ``scale_units='width', scale=1.0``, will result in an arrow length
       of width of the Axes.

    - 'dots': The arrow length of the arrows is in measured in display dots (pixels).

    - 'inches': Arrow lengths are scaled based on the DPI (dots per inch) of the figure.
       This ensures that the arrows have a consistent physical size on the figure,
       in inches, regardless of data values or plot scaling.
       For example, ``(u, v) = (1, 0)`` with ``scale_units='inches', scale=2`` results
       in a 0.5 inch-long arrow.

    - 'x' or 'y': The arrow length is scaled relative to the x or y axis units.
       For example, ``(u, v) = (0, 1)`` with ``scale_units='x', scale=1`` results
       in a vertical arrow with the length of 1 x-axis unit.

    - 'xy': Arrow length will be same as 'x' or 'y' units.
       This is useful for creating vectors in the x-y plane where u and v have
       the same units as x and y. To plot vectors in the x-y plane with u and v having
       the same units as x and y, use ``angles='xy', scale_units='xy', scale=1``.

    Note: Setting *scale_units* without setting scale does not have any effect because
    the scale units only differ by a constant factor and that is rescaled through
    autoscaling.

units : {'width', 'height', 'dots', 'inches', 'x', 'y', 'xy'}, default: 'width'
    Affects the arrow size (except for the length). In particular, the shaft
    *width* is measured in multiples of this unit.

    Supported values are:

    - 'width', 'height': The width or height of the Axes.
    - 'dots', 'inches': Pixels or inches based on the figure dpi.
    - 'x', 'y', 'xy': *X*, *Y* or :math:`\\sqrt{X^2 + Y^2}` in data units.

    The following table summarizes how these values affect the visible arrow
    size under zooming and figure size changes:

    =================  =================   ==================
    units              zoom                figure size change
    =================  =================   ==================
    'x', 'y', 'xy'     arrow size scales   —
    'width', 'height'  —                   arrow size scales
    'dots', 'inches'   —                   —
    =================  =================   ==================

width : float, optional
    Shaft width in arrow units. All head parameters are relative to *width*.

    The default depends on choice of *units* above, and number of vectors;
    a typical starting value is about 0.005 times the width of the plot.

headwidth : float, default: 3
    Head width as multiple of shaft *width*. See the notes below.

headlength : float, default: 5
    Head length as multiple of shaft *width*. See the notes below.

headaxislength : float, default: 4.5
    Head length at shaft intersection as multiple of shaft *width*.
    See the notes below.

minshaft : float, default: 1
    Length below which arrow scales, in units of head length. Do not
    set this to less than 1, or small arrows will look terrible!

minlength : float, default: 1
    Minimum length as a multiple of shaft width; if an arrow length
    is less than this, plot a dot (hexagon) of this diameter instead.

color : :mpltype:`color` or list :mpltype:`color`, optional
    Explicit color(s) for the arrows. If *C* has been set, *color* has no
    effect.

    This is a synonym for the `.PolyCollection` *facecolor* parameter.

Other Parameters
----------------
data : indexable object, optional
    DATA_PARAMETER_PLACEHOLDER

**kwargs : `~matplotlib.collections.PolyCollection` properties, optional
    All other keyword arguments are passed on to `.PolyCollection`:

    %(PolyCollection:kwdoc)s

Returns
-------
`~matplotlib.quiver.Quiver`

See Also
--------
.Axes.quiverkey : Add a key to a quiver plot.

Notes
-----

**Arrow shape**

The arrow is drawn as a polygon using the nodes as shown below. The values
*headwidth*, *headlength*, and *headaxislength* are in units of *width*.

.. image:: /_static/quiver_sizes.svg
   :width: 500px

The defaults give a slightly swept-back arrow. Here are some guidelines how to
get other head shapes:

- To make the head a triangle, make *headaxislength* the same as *headlength*.
- To make the arrow more pointed, reduce *headwidth* or increase *headlength*
  and *headaxislength*.
- To make the head smaller relative to the shaft, scale down all the head
  parameters proportionally.
- To remove the head completely, set all *head* parameters to 0.
- To get a diamond-shaped head, make *headaxislength* larger than *headlength*.
- Warning: For *headaxislength* < (*headlength* / *headwidth*), the "headaxis"
  nodes (i.e. the ones connecting the head with the shaft) will protrude out
  of the head in forward direction so that the arrow head looks broken.
""" % _docstring.interpd.params

_docstring.interpd.register(quiver_doc=_quiver_doc)


class QuiverKey(martist.Artist):
    """Labelled arrow for use as a quiver plot scale key."""
    halign = {'N': 'center', 'S': 'center', 'E': 'left', 'W': 'right'}
    valign = {'N': 'bottom', 'S': 'top', 'E': 'center', 'W': 'center'}
    pivot = {'N': 'middle', 'S': 'middle', 'E': 'tip', 'W': 'tail'}

    def __init__(self, Q, X, Y, U, label,
                 *, angle=0, coordinates='axes', color=None, labelsep=0.1,
                 labelpos='N', labelcolor=None, fontproperties=None,
                 zorder=None, **kwargs):
        """
        Add a key to a quiver plot.

        The positioning of the key depends on *X*, *Y*, *coordinates*, and
        *labelpos*.  If *labelpos* is 'N' or 'S', *X*, *Y* give the position of
        the middle of the key arrow.  If *labelpos* is 'E', *X*, *Y* positions
        the head, and if *labelpos* is 'W', *X*, *Y* positions the tail; in
        either of these two cases, *X*, *Y* is somewhere in the middle of the
        arrow+label key object.

        Parameters
        ----------
        Q : `~matplotlib.quiver.Quiver`
            A `.Quiver` object as returned by a call to `~.Axes.quiver()`.
        X, Y : float
            The location of the key.
        U : float
            The length of the key.
        label : str
            The key label (e.g., length and units of the key).
        angle : float, default: 0
            The angle of the key arrow, in degrees anti-clockwise from the
            horizontal axis.
        coordinates : {'axes', 'figure', 'data', 'inches'}, default: 'axes'
            Coordinate system and units for *X*, *Y*: 'axes' and 'figure' are
            normalized coordinate systems with (0, 0) in the lower left and
            (1, 1) in the upper right; 'data' are the axes data coordinates
            (used for the locations of the vectors in the quiver plot itself);
            'inches' is position in the figure in inches, with (0, 0) at the
            lower left corner.
        color : :mpltype:`color`
            Overrides face and edge colors from *Q*.
        labelpos : {'N', 'S', 'E', 'W'}
            Position the label above, below, to the right, to the left of the
            arrow, respectively.
        labelsep : float, default: 0.1
            Distance in inches between the arrow and the label.
        labelcolor : :mpltype:`color`, default: :rc:`text.color`
            Label color.
        fontproperties : dict, optional
            A dictionary with keyword arguments accepted by the
            `~matplotlib.font_manager.FontProperties` initializer:
            *family*, *style*, *variant*, *size*, *weight*.
        zorder : float
            The zorder of the key. The default is 0.1 above *Q*.
        **kwargs
            Any additional keyword arguments are used to override vector
            properties taken from *Q*.
        """
        super().__init__()
        self.Q = Q
        self.X = X
        self.Y = Y
        self.U = U
        self.angle = angle
        self.coord = coordinates
        self.color = color
        self.label = label
        self._labelsep_inches = labelsep

        self.labelpos = labelpos
        self.labelcolor = labelcolor
        self.fontproperties = fontproperties or dict()
        self.kw = kwargs
        self.text = mtext.Text(
            text=label,
            horizontalalignment=self.halign[self.labelpos],
            verticalalignment=self.valign[self.labelpos],
            fontproperties=self.fontproperties)
        if self.labelcolor is not None:
            self.text.set_color(self.labelcolor)
        self._dpi_at_last_init = None
        self.zorder = zorder if zorder is not None else Q.zorder + 0.1

    @property
    def labelsep(self):
        return self._labelsep_inches * self.Q.axes.get_figure(root=True).dpi

    def _init(self):
        if True:  # self._dpi_at_last_init != self.axes.get_figure().dpi
            if self.Q._dpi_at_last_init != self.Q.axes.get_figure(root=True).dpi:
                self.Q._init()
            self._set_transform()
            with cbook._setattr_cm(self.Q, pivot=self.pivot[self.labelpos],
                                   # Hack: save and restore the Umask
                                   Umask=ma.nomask):
                u = self.U * np.cos(np.radians(self.angle))
                v = self.U * np.sin(np.radians(self.angle))
                self.verts = self.Q._make_verts([[0., 0.]],
                                                np.array([u]), np.array([v]), 'uv')
            kwargs = self.Q.polykw
            kwargs.update(self.kw)
            self.vector = mcollections.PolyCollection(
                self.verts,
                offsets=[(self.X, self.Y)],
                offset_transform=self.get_transform(),
                **kwargs)
            if self.color is not None:
                self.vector.set_color(self.color)
            self.vector.set_transform(self.Q.get_transform())
            self.vector.set_figure(self.get_figure())
            self._dpi_at_last_init = self.Q.axes.get_figure(root=True).dpi

    def _text_shift(self):
        return {
            "N": (0, +self.labelsep),
            "S": (0, -self.labelsep),
            "E": (+self.labelsep, 0),
            "W": (-self.labelsep, 0),
        }[self.labelpos]

    @martist.allow_rasterization
    def draw(self, renderer):
        self._init()
        self.vector.draw(renderer)
        pos = self.get_transform().transform((self.X, self.Y))
        self.text.set_position(pos + self._text_shift())
        self.text.draw(renderer)
        self.stale = False

    def _set_transform(self):
        fig = self.Q.axes.get_figure(root=False)
        self.set_transform(_api.check_getitem({
            "data": self.Q.axes.transData,
            "axes": self.Q.axes.transAxes,
            "figure": fig.transFigure,
            "inches": fig.dpi_scale_trans,
        }, coordinates=self.coord))

    def set_figure(self, fig):
        super().set_figure(fig)
        self.text.set_figure(fig)

    def contains(self, mouseevent):
        if self._different_canvas(mouseevent):
            return False, {}
        # Maybe the dictionary should allow one to
        # distinguish between a text hit and a vector hit.
        if (self.text.contains(mouseevent)[0] or
                self.vector.contains(mouseevent)[0]):
            return True, {}
        return False, {}


def _parse_args(*args, caller_name='function'):
    """
    Helper function to parse positional parameters for colored vector plots.

    This is currently used for Quiver and Barbs.

    Parameters
    ----------
    *args : list
        list of 2-5 arguments. Depending on their number they are parsed to::

            U, V
            U, V, C
            X, Y, U, V
            X, Y, U, V, C

    caller_name : str
        Name of the calling method (used in error messages).
    """
    X = Y = C = None

    nargs = len(args)
    if nargs == 2:
        # The use of atleast_1d allows for handling scalar arguments while also
        # keeping masked arrays
        U, V = np.atleast_1d(*args)
    elif nargs == 3:
        U, V, C = np.atleast_1d(*args)
    elif nargs == 4:
        X, Y, U, V = np.atleast_1d(*args)
    elif nargs == 5:
        X, Y, U, V, C = np.atleast_1d(*args)
    else:
        raise _api.nargs_error(caller_name, takes="from 2 to 5", given=nargs)

    nr, nc = (1, U.shape[0]) if U.ndim == 1 else U.shape

    if X is not None:
        X = X.ravel()
        Y = Y.ravel()
        if len(X) == nc and len(Y) == nr:
            X, Y = (a.ravel() for a in np.meshgrid(X, Y))
        elif len(X) != len(Y):
            raise ValueError('X and Y must be the same size, but '
                             f'X.size is {X.size} and Y.size is {Y.size}.')
    else:
        indexgrid = np.meshgrid(np.arange(nc), np.arange(nr))
        X, Y = (np.ravel(a) for a in indexgrid)
    # Size validation for U, V, C is left to the set_UVC method.
    return X, Y, U, V, C


def _check_consistent_shapes(*arrays):
    all_shapes = {a.shape for a in arrays}
    if len(all_shapes) != 1:
        raise ValueError('The shapes of the passed in arrays do not match')


class Quiver(mcollections.PolyCollection):
    """
    Specialized PolyCollection for arrows.

    The only API method is set_UVC(), which can be used
    to change the size, orientation, and color of the
    arrows; their locations are fixed when the class is
    instantiated.  Possibly this method will be useful
    in animations.

    Much of the work in this class is done in the draw()
    method so that as much information as possible is available
    about the plot.  In subsequent draw() calls, recalculation
    is limited to things that might have changed, so there
    should be no performance penalty from putting the calculations
    in the draw() method.
    """

    _PIVOT_VALS = ('tail', 'middle', 'tip')

    @_docstring.Substitution(_quiver_doc)
    def __init__(self, ax, *args,
                 scale=None, headwidth=3, headlength=5, headaxislength=4.5,
                 minshaft=1, minlength=1, units='width', scale_units=None,
                 angles='uv', width=None, color='k', pivot='tail', **kwargs):
        """
        The constructor takes one required argument, an Axes
        instance, followed by the args and kwargs described
        by the following pyplot interface documentation:
        %s
        """
        self._axes = ax  # The attr actually set by the Artist.axes property.
        X, Y, U, V, C = _parse_args(*args, caller_name='quiver')
        self.X = X
        self.Y = Y
        self.XY = np.column_stack((X, Y))
        self.N = len(X)
        self.scale = scale
        self.headwidth = headwidth
        self.headlength = float(headlength)
        self.headaxislength = headaxislength
        self.minshaft = minshaft
        self.minlength = minlength
        self.units = units
        self.scale_units = scale_units
        self.angles = angles
        self.width = width

        if pivot.lower() == 'mid':
            pivot = 'middle'
        self.pivot = pivot.lower()
        _api.check_in_list(self._PIVOT_VALS, pivot=self.pivot)

        self.transform = kwargs.pop('transform', ax.transData)
        kwargs.setdefault('facecolors', color)
        kwargs.setdefault('linewidths', (0,))
        super().__init__([], offsets=self.XY, offset_transform=self.transform,
                         closed=False, **kwargs)
        self.polykw = kwargs
        self.set_UVC(U, V, C)
        self._dpi_at_last_init = None

    def _init(self):
        """
        Initialization delayed until first draw;
        allow time for axes setup.
        """
        # It seems that there are not enough event notifications
        # available to have this work on an as-needed basis at present.
        if True:  # self._dpi_at_last_init != self.axes.figure.dpi
            trans = self._set_transform()
            self.span = trans.inverted().transform_bbox(self.axes.bbox).width
            if self.width is None:
                sn = np.clip(math.sqrt(self.N), 8, 25)
                self.width = 0.06 * self.span / sn

            # _make_verts sets self.scale if not already specified
            if (self._dpi_at_last_init != self.axes.get_figure(root=True).dpi
                    and self.scale is None):
                self._make_verts(self.XY, self.U, self.V, self.angles)

            self._dpi_at_last_init = self.axes.get_figure(root=True).dpi

    def get_datalim(self, transData):
        trans = self.get_transform()
        offset_trf = self.get_offset_transform()
        full_transform = (trans - transData) + (offset_trf - transData)
        XY = full_transform.transform(self.XY)
        bbox = transforms.Bbox.null()
        bbox.update_from_data_xy(XY, ignore=True)
        return bbox

    @martist.allow_rasterization
    def draw(self, renderer):
        self._init()
        verts = self._make_verts(self.XY, self.U, self.V, self.angles)
        self.set_verts(verts, closed=False)
        super().draw(renderer)
        self.stale = False

    def set_UVC(self, U, V, C=None):
        # We need to ensure we have a copy, not a reference
        # to an array that might change before draw().
        U = ma.masked_invalid(U, copy=True).ravel()
        V = ma.masked_invalid(V, copy=True).ravel()
        if C is not None:
            C = ma.masked_invalid(C, copy=True).ravel()
        for name, var in zip(('U', 'V', 'C'), (U, V, C)):
            if not (var is None or var.size == self.N or var.size == 1):
                raise ValueError(f'Argument {name} has a size {var.size}'
                                 f' which does not match {self.N},'
                                 ' the number of arrow positions')

        mask = ma.mask_or(U.mask, V.mask, copy=False, shrink=True)
        if C is not None:
            mask = ma.mask_or(mask, C.mask, copy=False, shrink=True)
            if mask is ma.nomask:
                C = C.filled()
            else:
                C = ma.array(C, mask=mask, copy=False)
        self.U = U.filled(1)
        self.V = V.filled(1)
        self.Umask = mask
        if C is not None:
            self.set_array(C)
        self.stale = True

    def _dots_per_unit(self, units):
        """Return a scale factor for converting from units to pixels."""
        bb = self.axes.bbox
        vl = self.axes.viewLim
        return _api.check_getitem({
            'x': bb.width / vl.width,
            'y': bb.height / vl.height,
            'xy': np.hypot(*bb.size) / np.hypot(*vl.size),
            'width': bb.width,
            'height': bb.height,
            'dots': 1.,
            'inches': self.axes.get_figure(root=True).dpi,
        }, units=units)

    def _set_transform(self):
        """
        Set the PolyCollection transform to go
        from arrow width units to pixels.
        """
        dx = self._dots_per_unit(self.units)
        self._trans_scale = dx  # pixels per arrow width unit
        trans = transforms.Affine2D().scale(dx)
        self.set_transform(trans)
        return trans

    # Calculate angles and lengths for segment between (x, y), (x+u, y+v)
    def _angles_lengths(self, XY, U, V, eps=1):
        xy = self.axes.transData.transform(XY)
        uv = np.column_stack((U, V))
        xyp = self.axes.transData.transform(XY + eps * uv)
        dxy = xyp - xy
        angles = np.arctan2(dxy[:, 1], dxy[:, 0])
        lengths = np.hypot(*dxy.T) / eps
        return angles, lengths

    # XY is stacked [X, Y].
    # See quiver() doc for meaning of X, Y, U, V, angles.
    def _make_verts(self, XY, U, V, angles):
        uv = (U + V * 1j)
        str_angles = angles if isinstance(angles, str) else ''
        if str_angles == 'xy' and self.scale_units == 'xy':
            # Here eps is 1 so that if we get U, V by diffing
            # the X, Y arrays, the vectors will connect the
            # points, regardless of the axis scaling (including log).
            angles, lengths = self._angles_lengths(XY, U, V, eps=1)
        elif str_angles == 'xy' or self.scale_units == 'xy':
            # Calculate eps based on the extents of the plot
            # so that we don't end up with roundoff error from
            # adding a small number to a large.
            eps = np.abs(self.axes.dataLim.extents).max() * 0.001
            angles, lengths = self._angles_lengths(XY, U, V, eps=eps)

        if str_angles and self.scale_units == 'xy':
            a = lengths
        else:
            a = np.abs(uv)

        if self.scale is None:
            sn = max(10, math.sqrt(self.N))
            if self.Umask is not ma.nomask:
                amean = a[~self.Umask].mean()
            else:
                amean = a.mean()
            # crude auto-scaling
            # scale is typical arrow length as a multiple of the arrow width
            scale = 1.8 * amean * sn / self.span

        if self.scale_units is None:
            if self.scale is None:
                self.scale = scale
            widthu_per_lenu = 1.0
        else:
            if self.scale_units == 'xy':
                dx = 1
            else:
                dx = self._dots_per_unit(self.scale_units)
            widthu_per_lenu = dx / self._trans_scale
            if self.scale is None:
                self.scale = scale * widthu_per_lenu
        length = a * (widthu_per_lenu / (self.scale * self.width))
        X, Y = self._h_arrows(length)
        if str_angles == 'xy':
            theta = angles
        elif str_angles == 'uv':
            theta = np.angle(uv)
        else:
            theta = ma.masked_invalid(np.deg2rad(angles)).filled(0)
        theta = theta.reshape((-1, 1))  # for broadcasting
        xy = (X + Y * 1j) * np.exp(1j * theta) * self.width
        XY = np.stack((xy.real, xy.imag), axis=2)
        if self.Umask is not ma.nomask:
            XY = ma.array(XY)
            XY[self.Umask] = ma.masked
            # This might be handled more efficiently with nans, given
            # that nans will end up in the paths anyway.

        return XY

    def _h_arrows(self, length):
        """Length is in arrow width units."""
        # It might be possible to streamline the code
        # and speed it up a bit by using complex (x, y)
        # instead of separate arrays; but any gain would be slight.
        minsh = self.minshaft * self.headlength
        N = len(length)
        length = length.reshape(N, 1)
        # This number is chosen based on when pixel values overflow in Agg
        # causing rendering errors
        # length = np.minimum(length, 2 ** 16)
        np.clip(length, 0, 2 ** 16, out=length)
        # x, y: normal horizontal arrow
        x = np.array([0, -self.headaxislength,
                      -self.headlength, 0],
                     np.float64)
        x = x + np.array([0, 1, 1, 1]) * length
        y = 0.5 * np.array([1, 1, self.headwidth, 0], np.float64)
        y = np.repeat(y[np.newaxis, :], N, axis=0)
        # x0, y0: arrow without shaft, for short vectors
        x0 = np.array([0, minsh - self.headaxislength,
                       minsh - self.headlength, minsh], np.float64)
        y0 = 0.5 * np.array([1, 1, self.headwidth, 0], np.float64)
        ii = [0, 1, 2, 3, 2, 1, 0, 0]
        X = x[:, ii]
        Y = y[:, ii]
        Y[:, 3:-1] *= -1
        X0 = x0[ii]
        Y0 = y0[ii]
        Y0[3:-1] *= -1
        shrink = length / minsh if minsh != 0. else 0.
        X0 = shrink * X0[np.newaxis, :]
        Y0 = shrink * Y0[np.newaxis, :]
        short = np.repeat(length < minsh, 8, axis=1)
        # Now select X0, Y0 if short, otherwise X, Y
        np.copyto(X, X0, where=short)
        np.copyto(Y, Y0, where=short)
        if self.pivot == 'middle':
            X -= 0.5 * X[:, 3, np.newaxis]
        elif self.pivot == 'tip':
            # numpy bug? using -= does not work here unless we multiply by a
            # float first, as with 'mid'.
            X = X - X[:, 3, np.newaxis]
        elif self.pivot != 'tail':
            _api.check_in_list(["middle", "tip", "tail"], pivot=self.pivot)

        tooshort = length < self.minlength
        if tooshort.any():
            # Use a heptagonal dot:
            th = np.arange(0, 8, 1, np.float64) * (np.pi / 3.0)
            x1 = np.cos(th) * self.minlength * 0.5
            y1 = np.sin(th) * self.minlength * 0.5
            X1 = np.repeat(x1[np.newaxis, :], N, axis=0)
            Y1 = np.repeat(y1[np.newaxis, :], N, axis=0)
            tooshort = np.repeat(tooshort, 8, 1)
            np.copyto(X, X1, where=tooshort)
            np.copyto(Y, Y1, where=tooshort)
        # Mask handling is deferred to the caller, _make_verts.
        return X, Y


_barbs_doc = r"""
Plot a 2D field of wind barbs.

Call signature::

  barbs([X, Y], U, V, [C], /, **kwargs)

Where *X*, *Y* define the barb locations, *U*, *V* define the barb
directions, and *C* optionally sets the color.

The arguments *X*, *Y*, *U*, *V*, *C* are positional-only and may be
1D or 2D. *U*, *V*, *C* may be masked arrays, but masked *X*, *Y*
are not supported at present.

Barbs are traditionally used in meteorology as a way to plot the speed
and direction of wind observations, but can technically be used to
plot any two dimensional vector quantity.  As opposed to arrows, which
give vector magnitude by the length of the arrow, the barbs give more
quantitative information about the vector magnitude by putting slanted
lines or a triangle for various increments in magnitude, as show
schematically below::

  :                   /\    \
  :                  /  \    \
  :                 /    \    \    \
  :                /      \    \    \
  :               ------------------------------

The largest increment is given by a triangle (or "flag"). After those
come full lines (barbs). The smallest increment is a half line.  There
is only, of course, ever at most 1 half line.  If the magnitude is
small and only needs a single half-line and no full lines or
triangles, the half-line is offset from the end of the barb so that it
can be easily distinguished from barbs with a single full line.  The
magnitude for the barb shown above would nominally be 65, using the
standard increments of 50, 10, and 5.

See also https://en.wikipedia.org/wiki/Wind_barb.

Parameters
----------
X, Y : 1D or 2D array-like, optional
    The x and y coordinates of the barb locations. See *pivot* for how the
    barbs are drawn to the x, y positions.

    If not given, they will be generated as a uniform integer meshgrid based
    on the dimensions of *U* and *V*.

    If *X* and *Y* are 1D but *U*, *V* are 2D, *X*, *Y* are expanded to 2D
    using ``X, Y = np.meshgrid(X, Y)``. In this case ``len(X)`` and ``len(Y)``
    must match the column and row dimensions of *U* and *V*.

U, V : 1D or 2D array-like
    The x and y components of the barb shaft.

C : 1D or 2D array-like, optional
    Numeric data that defines the barb colors by colormapping via *norm* and
    *cmap*.

    This does not support explicit colors. If you want to set colors directly,
    use *barbcolor* instead.

length : float, default: 7
    Length of the barb in points; the other parts of the barb
    are scaled against this.

pivot : {'tip', 'middle'} or float, default: 'tip'
    The part of the arrow that is anchored to the *X*, *Y* grid. The barb
    rotates about this point. This can also be a number, which shifts the
    start of the barb that many points away from grid point.

barbcolor : :mpltype:`color` or color sequence
    The color of all parts of the barb except for the flags.  This parameter
    is analogous to the *edgecolor* parameter for polygons, which can be used
    instead. However this parameter will override facecolor.

flagcolor : :mpltype:`color` or color sequence
    The color of any flags on the barb.  This parameter is analogous to the
    *facecolor* parameter for polygons, which can be used instead. However,
    this parameter will override facecolor.  If this is not set (and *C* has
    not either) then *flagcolor* will be set to match *barbcolor* so that the
    barb has a uniform color. If *C* has been set, *flagcolor* has no effect.

sizes : dict, optional
    A dictionary of coefficients specifying the ratio of a given
    feature to the length of the barb. Only those values one wishes to
    override need to be included.  These features include:

    - 'spacing' - space between features (flags, full/half barbs)
    - 'height' - height (distance from shaft to top) of a flag or full barb
    - 'width' - width of a flag, twice the width of a full barb
    - 'emptybarb' - radius of the circle used for low magnitudes

fill_empty : bool, default: False
    Whether the empty barbs (circles) that are drawn should be filled with
    the flag color.  If they are not filled, the center is transparent.

rounding : bool, default: True
    Whether the vector magnitude should be rounded when allocating barb
    components.  If True, the magnitude is rounded to the nearest multiple
    of the half-barb increment.  If False, the magnitude is simply truncated
    to the next lowest multiple.

barb_increments : dict, optional
    A dictionary of increments specifying values to associate with
    different parts of the barb. Only those values one wishes to
    override need to be included.

    - 'half' - half barbs (Default is 5)
    - 'full' - full barbs (Default is 10)
    - 'flag' - flags (default is 50)

flip_barb : bool or array-like of bool, default: False
    Whether the lines and flags should point opposite to normal.
    Normal behavior is for the barbs and lines to point right (comes from wind
    barbs having these features point towards low pressure in the Northern
    Hemisphere).

    A single value is applied to all barbs. Individual barbs can be flipped by
    passing a bool array of the same size as *U* and *V*.

Returns
-------
barbs : `~matplotlib.quiver.Barbs`

Other Parameters
----------------
data : indexable object, optional
    DATA_PARAMETER_PLACEHOLDER

**kwargs
    The barbs can further be customized using `.PolyCollection` keyword
    arguments:

    %(PolyCollection:kwdoc)s
""" % _docstring.interpd.params

_docstring.interpd.register(barbs_doc=_barbs_doc)


class Barbs(mcollections.PolyCollection):
    """
    Specialized PolyCollection for barbs.

    The only API method is :meth:`set_UVC`, which can be used to
    change the size, orientation, and color of the arrows.  Locations
    are changed using the :meth:`set_offsets` collection method.
    Possibly this method will be useful in animations.

    There is one internal function :meth:`_find_tails` which finds
    exactly what should be put on the barb given the vector magnitude.
    From there :meth:`_make_barbs` is used to find the vertices of the
    polygon to represent the barb based on this information.
    """

    # This may be an abuse of polygons here to render what is essentially maybe
    # 1 triangle and a series of lines.  It works fine as far as I can tell
    # however.

    @_docstring.interpd
    def __init__(self, ax, *args,
                 pivot='tip', length=7, barbcolor=None, flagcolor=None,
                 sizes=None, fill_empty=False, barb_increments=None,
                 rounding=True, flip_barb=False, **kwargs):
        """
        The constructor takes one required argument, an Axes
        instance, followed by the args and kwargs described
        by the following pyplot interface documentation:
        %(barbs_doc)s
        """
        self.sizes = sizes or dict()
        self.fill_empty = fill_empty
        self.barb_increments = barb_increments or dict()
        self.rounding = rounding
        self.flip = np.atleast_1d(flip_barb)
        transform = kwargs.pop('transform', ax.transData)
        self._pivot = pivot
        self._length = length

        # Flagcolor and barbcolor provide convenience parameters for
        # setting the facecolor and edgecolor, respectively, of the barb
        # polygon.  We also work here to make the flag the same color as the
        # rest of the barb by default

        if None in (barbcolor, flagcolor):
            kwargs['edgecolors'] = 'face'
            if flagcolor:
                kwargs['facecolors'] = flagcolor
            elif barbcolor:
                kwargs['facecolors'] = barbcolor
            else:
                # Set to facecolor passed in or default to black
                kwargs.setdefault('facecolors', 'k')
        else:
            kwargs['edgecolors'] = barbcolor
            kwargs['facecolors'] = flagcolor

        # Explicitly set a line width if we're not given one, otherwise
        # polygons are not outlined and we get no barbs
        if 'linewidth' not in kwargs and 'lw' not in kwargs:
            kwargs['linewidth'] = 1

        # Parse out the data arrays from the various configurations supported
        x, y, u, v, c = _parse_args(*args, caller_name='barbs')
        self.x = x
        self.y = y
        xy = np.column_stack((x, y))

        # Make a collection
        barb_size = self._length ** 2 / 4  # Empirically determined
        super().__init__(
            [], (barb_size,), offsets=xy, offset_transform=transform, **kwargs)
        self.set_transform(transforms.IdentityTransform())

        self.set_UVC(u, v, c)

    def _find_tails(self, mag, rounding=True, half=5, full=10, flag=50):
        """
        Find how many of each of the tail pieces is necessary.

        Parameters
        ----------
        mag : `~numpy.ndarray`
            Vector magnitudes; must be non-negative (and an actual ndarray).
        rounding : bool, default: True
            Whether to round or to truncate to the nearest half-barb.
        half, full, flag : float, defaults: 5, 10, 50
            Increments for a half-barb, a barb, and a flag.

        Returns
        -------
        n_flags, n_barbs : int array
            For each entry in *mag*, the number of flags and barbs.
        half_flag : bool array
            For each entry in *mag*, whether a half-barb is needed.
        empty_flag : bool array
            For each entry in *mag*, whether nothing is drawn.
        """
        # If rounding, round to the nearest multiple of half, the smallest
        # increment
        if rounding:
            mag = half * np.around(mag / half)
        n_flags, mag = divmod(mag, flag)
        n_barb, mag = divmod(mag, full)
        half_flag = mag >= half
        empty_flag = ~(half_flag | (n_flags > 0) | (n_barb > 0))
        return n_flags.astype(int), n_barb.astype(int), half_flag, empty_flag

    def _make_barbs(self, u, v, nflags, nbarbs, half_barb, empty_flag, length,
                    pivot, sizes, fill_empty, flip):
        """
        Create the wind barbs.

        Parameters
        ----------
        u, v
            Components of the vector in the x and y directions, respectively.

        nflags, nbarbs, half_barb, empty_flag
            Respectively, the number of flags, number of barbs, flag for
            half a barb, and flag for empty barb, ostensibly obtained from
            :meth:`_find_tails`.

        length
            The length of the barb staff in points.

        pivot : {"tip", "middle"} or number
            The point on the barb around which the entire barb should be
            rotated.  If a number, the start of the barb is shifted by that
            many points from the origin.

        sizes : dict
            Coefficients specifying the ratio of a given feature to the length
            of the barb. These features include:

            - *spacing*: space between features (flags, full/half barbs).
            - *height*: distance from shaft of top of a flag or full barb.
            - *width*: width of a flag, twice the width of a full barb.
            - *emptybarb*: radius of the circle used for low magnitudes.

        fill_empty : bool
            Whether the circle representing an empty barb should be filled or
            not (this changes the drawing of the polygon).

        flip : list of bool
            Whether the features should be flipped to the other side of the
            barb (useful for winds in the southern hemisphere).

        Returns
        -------
        list of arrays of vertices
            Polygon vertices for each of the wind barbs.  These polygons have
            been rotated to properly align with the vector direction.
        """

        # These control the spacing and size of barb elements relative to the
        # length of the shaft
        spacing = length * sizes.get('spacing', 0.125)
        full_height = length * sizes.get('height', 0.4)
        full_width = length * sizes.get('width', 0.25)
        empty_rad = length * sizes.get('emptybarb', 0.15)

        # Controls y point where to pivot the barb.
        pivot_points = dict(tip=0.0, middle=-length / 2.)

        endx = 0.0
        try:
            endy = float(pivot)
        except ValueError:
            endy = pivot_points[pivot.lower()]

        # Get the appropriate angle for the vector components.  The offset is
        # due to the way the barb is initially drawn, going down the y-axis.
        # This makes sense in a meteorological mode of thinking since there 0
        # degrees corresponds to north (the y-axis traditionally)
        angles = -(ma.arctan2(v, u) + np.pi / 2)

        # Used for low magnitude.  We just get the vertices, so if we make it
        # out here, it can be reused.  The center set here should put the
        # center of the circle at the location(offset), rather than at the
        # same point as the barb pivot; this seems more sensible.
        circ = CirclePolygon((0, 0), radius=empty_rad).get_verts()
        if fill_empty:
            empty_barb = circ
        else:
            # If we don't want the empty one filled, we make a degenerate
            # polygon that wraps back over itself
            empty_barb = np.concatenate((circ, circ[::-1]))

        barb_list = []
        for index, angle in np.ndenumerate(angles):
            # If the vector magnitude is too weak to draw anything, plot an
            # empty circle instead
            if empty_flag[index]:
                # We can skip the transform since the circle has no preferred
                # orientation
                barb_list.append(empty_barb)
                continue

            poly_verts = [(endx, endy)]
            offset = length

            # Handle if this barb should be flipped
            barb_height = -full_height if flip[index] else full_height

            # Add vertices for each flag
            for i in range(nflags[index]):
                # The spacing that works for the barbs is a little to much for
                # the flags, but this only occurs when we have more than 1
                # flag.
                if offset != length:
                    offset += spacing / 2.
                poly_verts.extend(
                    [[endx, endy + offset],
                     [endx + barb_height, endy - full_width / 2 + offset],
                     [endx, endy - full_width + offset]])

                offset -= full_width + spacing

            # Add vertices for each barb.  These really are lines, but works
            # great adding 3 vertices that basically pull the polygon out and
            # back down the line
            for i in range(nbarbs[index]):
                poly_verts.extend(
                    [(endx, endy + offset),
                     (endx + barb_height, endy + offset + full_width / 2),
                     (endx, endy + offset)])

                offset -= spacing

            # Add the vertices for half a barb, if needed
            if half_barb[index]:
                # If the half barb is the first on the staff, traditionally it
                # is offset from the end to make it easy to distinguish from a
                # barb with a full one
                if offset == length:
                    poly_verts.append((endx, endy + offset))
                    offset -= 1.5 * spacing
                poly_verts.extend(
                    [(endx, endy + offset),
                     (endx + barb_height / 2, endy + offset + full_width / 4),
                     (endx, endy + offset)])

            # Rotate the barb according the angle. Making the barb first and
            # then rotating it made the math for drawing the barb really easy.
            # Also, the transform framework makes doing the rotation simple.
            poly_verts = transforms.Affine2D().rotate(-angle).transform(
                poly_verts)
            barb_list.append(poly_verts)

        return barb_list

    def set_UVC(self, U, V, C=None):
        # We need to ensure we have a copy, not a reference to an array that
        # might change before draw().
        self.u = ma.masked_invalid(U, copy=True).ravel()
        self.v = ma.masked_invalid(V, copy=True).ravel()

        # Flip needs to have the same number of entries as everything else.
        # Use broadcast_to to avoid a bloated array of identical values.
        # (can't rely on actual broadcasting)
        if len(self.flip) == 1:
            flip = np.broadcast_to(self.flip, self.u.shape)
        else:
            flip = self.flip

        if C is not None:
            c = ma.masked_invalid(C, copy=True).ravel()
            x, y, u, v, c, flip = cbook.delete_masked_points(
                self.x.ravel(), self.y.ravel(), self.u, self.v, c,
                flip.ravel())
            _check_consistent_shapes(x, y, u, v, c, flip)
        else:
            x, y, u, v, flip = cbook.delete_masked_points(
                self.x.ravel(), self.y.ravel(), self.u, self.v, flip.ravel())
            _check_consistent_shapes(x, y, u, v, flip)

        magnitude = np.hypot(u, v)
        flags, barbs, halves, empty = self._find_tails(
            magnitude, self.rounding, **self.barb_increments)

        # Get the vertices for each of the barbs

        plot_barbs = self._make_barbs(u, v, flags, barbs, halves, empty,
                                      self._length, self._pivot, self.sizes,
                                      self.fill_empty, flip)
        self.set_verts(plot_barbs)

        # Set the color array
        if C is not None:
            self.set_array(c)

        # Update the offsets in case the masked data changed
        xy = np.column_stack((x, y))
        self._offsets = xy
        self.stale = True

    def set_offsets(self, xy):
        """
        Set the offsets for the barb polygons.  This saves the offsets passed
        in and masks them as appropriate for the existing U/V data.

        Parameters
        ----------
        xy : sequence of pairs of floats
        """
        self.x = xy[:, 0]
        self.y = xy[:, 1]
        x, y, u, v = cbook.delete_masked_points(
            self.x.ravel(), self.y.ravel(), self.u, self.v)
        _check_consistent_shapes(x, y, u, v)
        xy = np.column_stack((x, y))
        super().set_offsets(xy)
        self.stale = True
