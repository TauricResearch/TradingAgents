"""
2D lines with support for a variety of line styles, markers, colors, etc.
"""

import copy

from numbers import Integral, Number, Real
import logging

import numpy as np

import matplotlib as mpl
from . import _api, cbook, colors as mcolors, _docstring
from .artist import Artist, allow_rasterization
from .cbook import (
    _to_unmasked_float_array, ls_mapper, ls_mapper_r, STEP_LOOKUP_MAP)
from .markers import MarkerStyle
from .path import Path
from .transforms import Bbox, BboxTransformTo, TransformedPath
from ._enums import JoinStyle, CapStyle

# Imported here for backward compatibility, even though they don't
# really belong.
from . import _path
from .markers import (  # noqa
    CARETLEFT, CARETRIGHT, CARETUP, CARETDOWN,
    CARETLEFTBASE, CARETRIGHTBASE, CARETUPBASE, CARETDOWNBASE,
    TICKLEFT, TICKRIGHT, TICKUP, TICKDOWN)

_log = logging.getLogger(__name__)


def _get_dash_pattern(style):
    """Convert linestyle to dash pattern."""
    # go from short hand -> full strings
    if isinstance(style, str):
        style = ls_mapper.get(style, style)
    # un-dashed styles
    if style in ['solid', 'None']:
        offset = 0
        dashes = None
    # dashed styles
    elif style in ['dashed', 'dashdot', 'dotted']:
        offset = 0
        dashes = tuple(mpl.rcParams[f'lines.{style}_pattern'])
    #
    elif isinstance(style, tuple):
        offset, dashes = style
        if offset is None:
            raise ValueError(f'Unrecognized linestyle: {style!r}')
    else:
        raise ValueError(f'Unrecognized linestyle: {style!r}')

    # normalize offset to be positive and shorter than the dash cycle
    if dashes is not None:
        dsum = sum(dashes)
        if dsum:
            offset %= dsum

    return offset, dashes


def _get_dash_patterns(styles):
    """Convert linestyle or sequence of linestyles to list of dash patterns."""
    try:
        patterns = [_get_dash_pattern(styles)]
    except ValueError:
        try:
            patterns = [_get_dash_pattern(x) for x in styles]
        except ValueError as err:
            emsg = f'Do not know how to convert {styles!r} to dashes'
            raise ValueError(emsg) from err

    return patterns


def _get_inverse_dash_pattern(offset, dashes):
    """Return the inverse of the given dash pattern, for filling the gaps."""
    # Define the inverse pattern by moving the last gap to the start of the
    # sequence.
    gaps = dashes[-1:] + dashes[:-1]
    # Set the offset so that this new first segment is skipped
    # (see backend_bases.GraphicsContextBase.set_dashes for offset definition).
    offset_gaps = offset + dashes[-1]

    return offset_gaps, gaps


def _scale_dashes(offset, dashes, lw):
    if not mpl.rcParams['lines.scale_dashes']:
        return offset, dashes
    scaled_offset = offset * lw
    scaled_dashes = ([x * lw if x is not None else None for x in dashes]
                     if dashes is not None else None)
    return scaled_offset, scaled_dashes


def segment_hits(cx, cy, x, y, radius):
    """
    Return the indices of the segments in the polyline with coordinates (*cx*,
    *cy*) that are within a distance *radius* of the point (*x*, *y*).
    """
    # Process single points specially
    if len(x) <= 1:
        res, = np.nonzero((cx - x) ** 2 + (cy - y) ** 2 <= radius ** 2)
        return res

    # We need to lop the last element off a lot.
    xr, yr = x[:-1], y[:-1]

    # Only look at line segments whose nearest point to C on the line
    # lies within the segment.
    dx, dy = x[1:] - xr, y[1:] - yr
    Lnorm_sq = dx ** 2 + dy ** 2  # Possibly want to eliminate Lnorm==0
    u = ((cx - xr) * dx + (cy - yr) * dy) / Lnorm_sq
    candidates = (u >= 0) & (u <= 1)

    # Note that there is a little area near one side of each point
    # which will be near neither segment, and another which will
    # be near both, depending on the angle of the lines.  The
    # following radius test eliminates these ambiguities.
    point_hits = (cx - x) ** 2 + (cy - y) ** 2 <= radius ** 2
    candidates = candidates & ~(point_hits[:-1] | point_hits[1:])

    # For those candidates which remain, determine how far they lie away
    # from the line.
    px, py = xr + u * dx, yr + u * dy
    line_hits = (cx - px) ** 2 + (cy - py) ** 2 <= radius ** 2
    line_hits = line_hits & candidates
    points, = point_hits.ravel().nonzero()
    lines, = line_hits.ravel().nonzero()
    return np.concatenate((points, lines))


def _mark_every_path(markevery, tpath, affine, ax):
    """
    Helper function that sorts out how to deal the input
    `markevery` and returns the points where markers should be drawn.

    Takes in the `markevery` value and the line path and returns the
    sub-sampled path.
    """
    # pull out the two bits of data we want from the path
    codes, verts = tpath.codes, tpath.vertices

    def _slice_or_none(in_v, slc):
        """Helper function to cope with `codes` being an ndarray or `None`."""
        if in_v is None:
            return None
        return in_v[slc]

    # if just an int, assume starting at 0 and make a tuple
    if isinstance(markevery, Integral):
        markevery = (0, markevery)
    # if just a float, assume starting at 0.0 and make a tuple
    elif isinstance(markevery, Real):
        markevery = (0.0, markevery)

    if isinstance(markevery, tuple):
        if len(markevery) != 2:
            raise ValueError('`markevery` is a tuple but its len is not 2; '
                             f'markevery={markevery}')
        start, step = markevery
        # if step is an int, old behavior
        if isinstance(step, Integral):
            # tuple of 2 int is for backwards compatibility,
            if not isinstance(start, Integral):
                raise ValueError(
                    '`markevery` is a tuple with len 2 and second element is '
                    'an int, but the first element is not an int; '
                    f'markevery={markevery}')
            # just return, we are done here

            return Path(verts[slice(start, None, step)],
                        _slice_or_none(codes, slice(start, None, step)))

        elif isinstance(step, Real):
            if not isinstance(start, Real):
                raise ValueError(
                    '`markevery` is a tuple with len 2 and second element is '
                    'a float, but the first element is not a float or an int; '
                    f'markevery={markevery}')
            if ax is None:
                raise ValueError(
                    "markevery is specified relative to the Axes size, but "
                    "the line does not have a Axes as parent")

            # calc cumulative distance along path (in display coords):
            fin = np.isfinite(verts).all(axis=1)
            fverts = verts[fin]
            disp_coords = affine.transform(fverts)

            delta = np.empty((len(disp_coords), 2))
            delta[0, :] = 0
            delta[1:, :] = disp_coords[1:, :] - disp_coords[:-1, :]
            delta = np.hypot(*delta.T).cumsum()
            # calc distance between markers along path based on the Axes
            # bounding box diagonal being a distance of unity:
            (x0, y0), (x1, y1) = ax.transAxes.transform([[0, 0], [1, 1]])
            scale = np.hypot(x1 - x0, y1 - y0)
            marker_delta = np.arange(start * scale, delta[-1], step * scale)
            # find closest actual data point that is closest to
            # the theoretical distance along the path:
            inds = np.abs(delta[np.newaxis, :] - marker_delta[:, np.newaxis])
            inds = inds.argmin(axis=1)
            inds = np.unique(inds)
            # return, we are done here
            return Path(fverts[inds], _slice_or_none(codes, inds))
        else:
            raise ValueError(
                f"markevery={markevery!r} is a tuple with len 2, but its "
                f"second element is not an int or a float")

    elif isinstance(markevery, slice):
        # mazol tov, it's already a slice, just return
        return Path(verts[markevery], _slice_or_none(codes, markevery))

    elif np.iterable(markevery):
        # fancy indexing
        try:
            return Path(verts[markevery], _slice_or_none(codes, markevery))
        except (ValueError, IndexError) as err:
            raise ValueError(
                f"markevery={markevery!r} is iterable but not a valid numpy "
                f"fancy index") from err
    else:
        raise ValueError(f"markevery={markevery!r} is not a recognized value")


@_docstring.interpd
@_api.define_aliases({
    "antialiased": ["aa"],
    "color": ["c"],
    "drawstyle": ["ds"],
    "linestyle": ["ls"],
    "linewidth": ["lw"],
    "markeredgecolor": ["mec"],
    "markeredgewidth": ["mew"],
    "markerfacecolor": ["mfc"],
    "markerfacecoloralt": ["mfcalt"],
    "markersize": ["ms"],
})
class Line2D(Artist):
    """
    A line - the line can have both a solid linestyle connecting all
    the vertices, and a marker at each vertex.  Additionally, the
    drawing of the solid line is influenced by the drawstyle, e.g., one
    can create "stepped" lines in various styles.
    """

    lineStyles = _lineStyles = {  # hidden names deprecated
        '-':    '_draw_solid',
        '--':   '_draw_dashed',
        '-.':   '_draw_dash_dot',
        ':':    '_draw_dotted',
        'None': '_draw_nothing',
        ' ':    '_draw_nothing',
        '':     '_draw_nothing',
    }

    _drawStyles_l = {
        'default':    '_draw_lines',
        'steps-mid':  '_draw_steps_mid',
        'steps-pre':  '_draw_steps_pre',
        'steps-post': '_draw_steps_post',
    }

    _drawStyles_s = {
        'steps': '_draw_steps_pre',
    }

    # drawStyles should now be deprecated.
    drawStyles = {**_drawStyles_l, **_drawStyles_s}
    # Need a list ordered with long names first:
    drawStyleKeys = [*_drawStyles_l, *_drawStyles_s]

    # Referenced here to maintain API.  These are defined in
    # MarkerStyle
    markers = MarkerStyle.markers
    filled_markers = MarkerStyle.filled_markers
    fillStyles = MarkerStyle.fillstyles

    zorder = 2

    _subslice_optim_min_size = 1000

    def __str__(self):
        if self._label != "":
            return f"Line2D({self._label})"
        elif self._x is None:
            return "Line2D()"
        elif len(self._x) > 3:
            return "Line2D(({:g},{:g}),({:g},{:g}),...,({:g},{:g}))".format(
                self._x[0], self._y[0],
                self._x[1], self._y[1],
                self._x[-1], self._y[-1])
        else:
            return "Line2D(%s)" % ",".join(
                map("({:g},{:g})".format, self._x, self._y))

    def __init__(self, xdata, ydata, *,
                 linewidth=None,  # all Nones default to rc
                 linestyle=None,
                 color=None,
                 gapcolor=None,
                 marker=None,
                 markersize=None,
                 markeredgewidth=None,
                 markeredgecolor=None,
                 markerfacecolor=None,
                 markerfacecoloralt='none',
                 fillstyle=None,
                 antialiased=None,
                 dash_capstyle=None,
                 solid_capstyle=None,
                 dash_joinstyle=None,
                 solid_joinstyle=None,
                 pickradius=5,
                 drawstyle=None,
                 markevery=None,
                 **kwargs
                 ):
        """
        Create a `.Line2D` instance with *x* and *y* data in sequences of
        *xdata*, *ydata*.

        Additional keyword arguments are `.Line2D` properties:

        %(Line2D:kwdoc)s

        See :meth:`set_linestyle` for a description of the line styles,
        :meth:`set_marker` for a description of the markers, and
        :meth:`set_drawstyle` for a description of the draw styles.

        """
        super().__init__()

        # Convert sequences to NumPy arrays.
        if not np.iterable(xdata):
            raise RuntimeError('xdata must be a sequence')
        if not np.iterable(ydata):
            raise RuntimeError('ydata must be a sequence')

        if linewidth is None:
            linewidth = mpl.rcParams['lines.linewidth']

        if linestyle is None:
            linestyle = mpl.rcParams['lines.linestyle']
        if marker is None:
            marker = mpl.rcParams['lines.marker']
        if color is None:
            color = mpl.rcParams['lines.color']

        if markersize is None:
            markersize = mpl.rcParams['lines.markersize']
        if antialiased is None:
            antialiased = mpl.rcParams['lines.antialiased']
        if dash_capstyle is None:
            dash_capstyle = mpl.rcParams['lines.dash_capstyle']
        if dash_joinstyle is None:
            dash_joinstyle = mpl.rcParams['lines.dash_joinstyle']
        if solid_capstyle is None:
            solid_capstyle = mpl.rcParams['lines.solid_capstyle']
        if solid_joinstyle is None:
            solid_joinstyle = mpl.rcParams['lines.solid_joinstyle']

        if drawstyle is None:
            drawstyle = 'default'

        self._dashcapstyle = None
        self._dashjoinstyle = None
        self._solidjoinstyle = None
        self._solidcapstyle = None
        self.set_dash_capstyle(dash_capstyle)
        self.set_dash_joinstyle(dash_joinstyle)
        self.set_solid_capstyle(solid_capstyle)
        self.set_solid_joinstyle(solid_joinstyle)

        self._linestyles = None
        self._drawstyle = None
        self._linewidth = linewidth
        self._unscaled_dash_pattern = (0, None)  # offset, dash
        self._dash_pattern = (0, None)  # offset, dash (scaled by linewidth)

        self.set_linewidth(linewidth)
        self.set_linestyle(linestyle)
        self.set_drawstyle(drawstyle)

        self._color = None
        self.set_color(color)
        if marker is None:
            marker = 'none'  # Default.
        if not isinstance(marker, MarkerStyle):
            self._marker = MarkerStyle(marker, fillstyle)
        else:
            self._marker = marker

        self._gapcolor = None
        self.set_gapcolor(gapcolor)

        self._markevery = None
        self._markersize = None
        self._antialiased = None

        self.set_markevery(markevery)
        self.set_antialiased(antialiased)
        self.set_markersize(markersize)

        self._markeredgecolor = None
        self._markeredgewidth = None
        self._markerfacecolor = None
        self._markerfacecoloralt = None

        self.set_markerfacecolor(markerfacecolor)  # Normalizes None to rc.
        self.set_markerfacecoloralt(markerfacecoloralt)
        self.set_markeredgecolor(markeredgecolor)  # Normalizes None to rc.
        self.set_markeredgewidth(markeredgewidth)

        # update kwargs before updating data to give the caller a
        # chance to init axes (and hence unit support)
        self._internal_update(kwargs)
        self.pickradius = pickradius
        self.ind_offset = 0
        if (isinstance(self._picker, Number) and
                not isinstance(self._picker, bool)):
            self._pickradius = self._picker

        self._xorig = np.asarray([])
        self._yorig = np.asarray([])
        self._invalidx = True
        self._invalidy = True
        self._x = None
        self._y = None
        self._xy = None
        self._path = None
        self._transformed_path = None
        self._subslice = False
        self._x_filled = None  # used in subslicing; only x is needed

        self.set_data(xdata, ydata)

    def contains(self, mouseevent):
        """
        Test whether *mouseevent* occurred on the line.

        An event is deemed to have occurred "on" the line if it is less
        than ``self.pickradius`` (default: 5 points) away from it.  Use
        `~.Line2D.get_pickradius` or `~.Line2D.set_pickradius` to get or set
        the pick radius.

        Parameters
        ----------
        mouseevent : `~matplotlib.backend_bases.MouseEvent`

        Returns
        -------
        contains : bool
            Whether any values are within the radius.
        details : dict
            A dictionary ``{'ind': pointlist}``, where *pointlist* is a
            list of points of the line that are within the pickradius around
            the event position.

            TODO: sort returned indices by distance
        """
        if self._different_canvas(mouseevent):
            return False, {}

        # Make sure we have data to plot
        if self._invalidy or self._invalidx:
            self.recache()
        if len(self._xy) == 0:
            return False, {}

        # Convert points to pixels
        transformed_path = self._get_transformed_path()
        path, affine = transformed_path.get_transformed_path_and_affine()
        path = affine.transform_path(path)
        xy = path.vertices
        xt = xy[:, 0]
        yt = xy[:, 1]

        # Convert pick radius from points to pixels
        fig = self.get_figure(root=True)
        if fig is None:
            _log.warning('no figure set when check if mouse is on line')
            pixels = self._pickradius
        else:
            pixels = fig.dpi / 72. * self._pickradius

        # The math involved in checking for containment (here and inside of
        # segment_hits) assumes that it is OK to overflow, so temporarily set
        # the error flags accordingly.
        with np.errstate(all='ignore'):
            # Check for collision
            if self._linestyle in ['None', None]:
                # If no line, return the nearby point(s)
                ind, = np.nonzero(
                    (xt - mouseevent.x) ** 2 + (yt - mouseevent.y) ** 2
                    <= pixels ** 2)
            else:
                # If line, return the nearby segment(s)
                ind = segment_hits(mouseevent.x, mouseevent.y, xt, yt, pixels)
                if self._drawstyle.startswith("steps"):
                    ind //= 2

        ind += self.ind_offset

        # Return the point(s) within radius
        return len(ind) > 0, dict(ind=ind)

    def get_pickradius(self):
        """
        Return the pick radius used for containment tests.

        See `.contains` for more details.
        """
        return self._pickradius

    def set_pickradius(self, pickradius):
        """
        Set the pick radius used for containment tests.

        See `.contains` for more details.

        Parameters
        ----------
        pickradius : float
            Pick radius, in points.
        """
        if not isinstance(pickradius, Real) or pickradius < 0:
            raise ValueError("pick radius should be a distance")
        self._pickradius = pickradius

    pickradius = property(get_pickradius, set_pickradius)

    def get_fillstyle(self):
        """
        Return the marker fill style.

        See also `~.Line2D.set_fillstyle`.
        """
        return self._marker.get_fillstyle()

    def set_fillstyle(self, fs):
        """
        Set the marker fill style.

        Parameters
        ----------
        fs : {'full', 'left', 'right', 'bottom', 'top', 'none'}
            Possible values:

            - 'full': Fill the whole marker with the *markerfacecolor*.
            - 'left', 'right', 'bottom', 'top': Fill the marker half at
              the given side with the *markerfacecolor*. The other
              half of the marker is filled with *markerfacecoloralt*.
            - 'none': No filling.

            For examples see :ref:`marker_fill_styles`.
        """
        self.set_marker(MarkerStyle(self._marker.get_marker(), fs))
        self.stale = True

    def set_markevery(self, every):
        """
        Set the markevery property to subsample the plot when using markers.

        e.g., if ``every=5``, every 5-th marker will be plotted.

        Parameters
        ----------
        every : None or int or (int, int) or slice or list[int] or float or \
(float, float) or list[bool]
            Which markers to plot.

            - ``every=None``: every point will be plotted.
            - ``every=N``: every N-th marker will be plotted starting with
              marker 0.
            - ``every=(start, N)``: every N-th marker, starting at index
              *start*, will be plotted.
            - ``every=slice(start, end, N)``: every N-th marker, starting at
              index *start*, up to but not including index *end*, will be
              plotted.
            - ``every=[i, j, m, ...]``: only markers at the given indices
              will be plotted.
            - ``every=[True, False, True, ...]``: only positions that are True
              will be plotted. The list must have the same length as the data
              points.
            - ``every=0.1``, (i.e. a float): markers will be spaced at
              approximately equal visual distances along the line; the distance
              along the line between markers is determined by multiplying the
              display-coordinate distance of the Axes bounding-box diagonal
              by the value of *every*.
            - ``every=(0.5, 0.1)`` (i.e. a length-2 tuple of float): similar
              to ``every=0.1`` but the first marker will be offset along the
              line by 0.5 multiplied by the
              display-coordinate-diagonal-distance along the line.

            For examples see
            :doc:`/gallery/lines_bars_and_markers/markevery_demo`.

        Notes
        -----
        Setting *markevery* will still only draw markers at actual data points.
        While the float argument form aims for uniform visual spacing, it has
        to coerce from the ideal spacing to the nearest available data point.
        Depending on the number and distribution of data points, the result
        may still not look evenly spaced.

        When using a start offset to specify the first marker, the offset will
        be from the first data point which may be different from the first
        the visible data point if the plot is zoomed in.

        If zooming in on a plot when using float arguments then the actual
        data points that have markers will change because the distance between
        markers is always determined from the display-coordinates
        axes-bounding-box-diagonal regardless of the actual axes data limits.

        """
        self._markevery = every
        self.stale = True

    def get_markevery(self):
        """
        Return the markevery setting for marker subsampling.

        See also `~.Line2D.set_markevery`.
        """
        return self._markevery

    def set_picker(self, p):
        """
        Set the event picker details for the line.

        Parameters
        ----------
        p : float or callable[[Artist, Event], tuple[bool, dict]]
            If a float, it is used as the pick radius in points.
        """
        if not callable(p):
            self.set_pickradius(p)
        self._picker = p

    def get_bbox(self):
        """Get the bounding box of this line."""
        bbox = Bbox([[0, 0], [0, 0]])
        bbox.update_from_data_xy(self.get_xydata())
        return bbox

    def get_window_extent(self, renderer=None):
        bbox = Bbox([[0, 0], [0, 0]])
        trans_data_to_xy = self.get_transform().transform
        bbox.update_from_data_xy(trans_data_to_xy(self.get_xydata()),
                                 ignore=True)
        # correct for marker size, if any
        if self._marker:
            ms = (self._markersize / 72.0 * self.get_figure(root=True).dpi) * 0.5
            bbox = bbox.padded(ms)
        return bbox

    def set_data(self, *args):
        """
        Set the x and y data.

        Parameters
        ----------
        *args : (2, N) array or two 1D arrays

        See Also
        --------
        set_xdata
        set_ydata
        """
        if len(args) == 1:
            (x, y), = args
        else:
            x, y = args

        self.set_xdata(x)
        self.set_ydata(y)

    def recache_always(self):
        self.recache(always=True)

    def recache(self, always=False):
        if always or self._invalidx:
            xconv = self.convert_xunits(self._xorig)
            x = _to_unmasked_float_array(xconv).ravel()
        else:
            x = self._x
        if always or self._invalidy:
            yconv = self.convert_yunits(self._yorig)
            y = _to_unmasked_float_array(yconv).ravel()
        else:
            y = self._y

        self._xy = np.column_stack(np.broadcast_arrays(x, y)).astype(float)
        self._x, self._y = self._xy.T  # views

        self._subslice = False
        if (self.axes
                and len(x) > self._subslice_optim_min_size
                and _path.is_sorted_and_has_non_nan(x)
                and self.axes.name == 'rectilinear'
                and self.axes.get_xscale() == 'linear'
                and self._markevery is None
                and self.get_clip_on()
                and self.get_transform() == self.axes.transData):
            self._subslice = True
            nanmask = np.isnan(x)
            if nanmask.any():
                self._x_filled = self._x.copy()
                indices = np.arange(len(x))
                self._x_filled[nanmask] = np.interp(
                    indices[nanmask], indices[~nanmask], self._x[~nanmask])
            else:
                self._x_filled = self._x

        if self._path is not None:
            interpolation_steps = self._path._interpolation_steps
        else:
            interpolation_steps = 1
        xy = STEP_LOOKUP_MAP[self._drawstyle](*self._xy.T)
        self._path = Path(np.asarray(xy).T,
                          _interpolation_steps=interpolation_steps)
        self._transformed_path = None
        self._invalidx = False
        self._invalidy = False

    def _transform_path(self, subslice=None):
        """
        Put a TransformedPath instance at self._transformed_path;
        all invalidation of the transform is then handled by the
        TransformedPath instance.
        """
        # Masked arrays are now handled by the Path class itself
        if subslice is not None:
            xy = STEP_LOOKUP_MAP[self._drawstyle](*self._xy[subslice, :].T)
            _path = Path(np.asarray(xy).T,
                         _interpolation_steps=self._path._interpolation_steps)
        else:
            _path = self._path
        self._transformed_path = TransformedPath(_path, self.get_transform())

    def _get_transformed_path(self):
        """Return this line's `~matplotlib.transforms.TransformedPath`."""
        if self._transformed_path is None:
            self._transform_path()
        return self._transformed_path

    def set_transform(self, t):
        # docstring inherited
        self._invalidx = True
        self._invalidy = True
        super().set_transform(t)

    @allow_rasterization
    def draw(self, renderer):
        # docstring inherited

        if not self.get_visible():
            return

        if self._invalidy or self._invalidx:
            self.recache()
        self.ind_offset = 0  # Needed for contains() method.
        if self._subslice and self.axes:
            x0, x1 = self.axes.get_xbound()
            i0 = self._x_filled.searchsorted(x0, 'left')
            i1 = self._x_filled.searchsorted(x1, 'right')
            subslice = slice(max(i0 - 1, 0), i1 + 1)
            self.ind_offset = subslice.start
            self._transform_path(subslice)
        else:
            subslice = None

        if self.get_path_effects():
            from matplotlib.patheffects import PathEffectRenderer
            renderer = PathEffectRenderer(self.get_path_effects(), renderer)

        renderer.open_group('line2d', self.get_gid())
        if self._lineStyles[self._linestyle] != '_draw_nothing':
            tpath, affine = (self._get_transformed_path()
                             .get_transformed_path_and_affine())
            if len(tpath.vertices):
                gc = renderer.new_gc()
                self._set_gc_clip(gc)
                gc.set_url(self.get_url())

                gc.set_antialiased(self._antialiased)
                gc.set_linewidth(self._linewidth)

                if self.is_dashed():
                    cap = self._dashcapstyle
                    join = self._dashjoinstyle
                else:
                    cap = self._solidcapstyle
                    join = self._solidjoinstyle
                gc.set_joinstyle(join)
                gc.set_capstyle(cap)
                gc.set_snap(self.get_snap())
                if self.get_sketch_params() is not None:
                    gc.set_sketch_params(*self.get_sketch_params())

                # We first draw a path within the gaps if needed.
                if self.is_dashed() and self._gapcolor is not None:
                    lc_rgba = mcolors.to_rgba(self._gapcolor, self._alpha)
                    gc.set_foreground(lc_rgba, isRGBA=True)

                    offset_gaps, gaps = _get_inverse_dash_pattern(
                        *self._dash_pattern)

                    gc.set_dashes(offset_gaps, gaps)
                    renderer.draw_path(gc, tpath, affine.frozen())

                lc_rgba = mcolors.to_rgba(self._color, self._alpha)
                gc.set_foreground(lc_rgba, isRGBA=True)

                gc.set_dashes(*self._dash_pattern)
                renderer.draw_path(gc, tpath, affine.frozen())
                gc.restore()

        if self._marker and self._markersize > 0:
            gc = renderer.new_gc()
            self._set_gc_clip(gc)
            gc.set_url(self.get_url())
            gc.set_linewidth(self._markeredgewidth)
            gc.set_antialiased(self._antialiased)

            ec_rgba = mcolors.to_rgba(
                self.get_markeredgecolor(), self._alpha)
            fc_rgba = mcolors.to_rgba(
                self._get_markerfacecolor(), self._alpha)
            fcalt_rgba = mcolors.to_rgba(
                self._get_markerfacecolor(alt=True), self._alpha)
            # If the edgecolor is "auto", it is set according to the *line*
            # color but inherits the alpha value of the *face* color, if any.
            if (cbook._str_equal(self._markeredgecolor, "auto")
                    and not cbook._str_lower_equal(
                        self.get_markerfacecolor(), "none")):
                ec_rgba = ec_rgba[:3] + (fc_rgba[3],)
            gc.set_foreground(ec_rgba, isRGBA=True)
            if self.get_sketch_params() is not None:
                scale, length, randomness = self.get_sketch_params()
                gc.set_sketch_params(scale/2, length/2, 2*randomness)

            marker = self._marker

            # Markers *must* be drawn ignoring the drawstyle (but don't pay the
            # recaching if drawstyle is already "default").
            if self.get_drawstyle() != "default":
                with cbook._setattr_cm(
                        self, _drawstyle="default", _transformed_path=None):
                    self.recache()
                    self._transform_path(subslice)
                    tpath, affine = (self._get_transformed_path()
                                     .get_transformed_points_and_affine())
            else:
                tpath, affine = (self._get_transformed_path()
                                 .get_transformed_points_and_affine())

            if len(tpath.vertices):
                # subsample the markers if markevery is not None
                markevery = self.get_markevery()
                if markevery is not None:
                    subsampled = _mark_every_path(
                        markevery, tpath, affine, self.axes)
                else:
                    subsampled = tpath

                snap = marker.get_snap_threshold()
                if isinstance(snap, Real):
                    snap = renderer.points_to_pixels(self._markersize) >= snap
                gc.set_snap(snap)
                gc.set_joinstyle(marker.get_joinstyle())
                gc.set_capstyle(marker.get_capstyle())
                marker_path = marker.get_path()
                marker_trans = marker.get_transform()
                w = renderer.points_to_pixels(self._markersize)

                if cbook._str_equal(marker.get_marker(), ","):
                    gc.set_linewidth(0)
                else:
                    # Don't scale for pixels, and don't stroke them
                    marker_trans = marker_trans.scale(w)
                renderer.draw_markers(gc, marker_path, marker_trans,
                                      subsampled, affine.frozen(),
                                      fc_rgba)

                alt_marker_path = marker.get_alt_path()
                if alt_marker_path:
                    alt_marker_trans = marker.get_alt_transform()
                    alt_marker_trans = alt_marker_trans.scale(w)
                    renderer.draw_markers(
                            gc, alt_marker_path, alt_marker_trans, subsampled,
                            affine.frozen(), fcalt_rgba)

            gc.restore()

        renderer.close_group('line2d')
        self.stale = False

    def get_antialiased(self):
        """Return whether antialiased rendering is used."""
        return self._antialiased

    def get_color(self):
        """
        Return the line color.

        See also `~.Line2D.set_color`.
        """
        return self._color

    def get_drawstyle(self):
        """
        Return the drawstyle.

        See also `~.Line2D.set_drawstyle`.
        """
        return self._drawstyle

    def get_gapcolor(self):
        """
        Return the line gapcolor.

        See also `~.Line2D.set_gapcolor`.
        """
        return self._gapcolor

    def get_linestyle(self):
        """
        Return the linestyle.

        See also `~.Line2D.set_linestyle`.
        """
        return self._linestyle

    def get_linewidth(self):
        """
        Return the linewidth in points.

        See also `~.Line2D.set_linewidth`.
        """
        return self._linewidth

    def get_marker(self):
        """
        Return the line marker.

        See also `~.Line2D.set_marker`.
        """
        return self._marker.get_marker()

    def get_markeredgecolor(self):
        """
        Return the marker edge color.

        See also `~.Line2D.set_markeredgecolor`.
        """
        mec = self._markeredgecolor
        if cbook._str_equal(mec, 'auto'):
            if mpl.rcParams['_internal.classic_mode']:
                if self._marker.get_marker() in ('.', ','):
                    return self._color
                if (self._marker.is_filled()
                        and self._marker.get_fillstyle() != 'none'):
                    return 'k'  # Bad hard-wired default...
            return self._color
        else:
            return mec

    def get_markeredgewidth(self):
        """
        Return the marker edge width in points.

        See also `~.Line2D.set_markeredgewidth`.
        """
        return self._markeredgewidth

    def _get_markerfacecolor(self, alt=False):
        if self._marker.get_fillstyle() == 'none':
            return 'none'
        fc = self._markerfacecoloralt if alt else self._markerfacecolor
        if cbook._str_lower_equal(fc, 'auto'):
            return self._color
        else:
            return fc

    def get_markerfacecolor(self):
        """
        Return the marker face color.

        See also `~.Line2D.set_markerfacecolor`.
        """
        return self._get_markerfacecolor(alt=False)

    def get_markerfacecoloralt(self):
        """
        Return the alternate marker face color.

        See also `~.Line2D.set_markerfacecoloralt`.
        """
        return self._get_markerfacecolor(alt=True)

    def get_markersize(self):
        """
        Return the marker size in points.

        See also `~.Line2D.set_markersize`.
        """
        return self._markersize

    def get_data(self, orig=True):
        """
        Return the line data as an ``(xdata, ydata)`` pair.

        If *orig* is *True*, return the original data.
        """
        return self.get_xdata(orig=orig), self.get_ydata(orig=orig)

    def get_xdata(self, orig=True):
        """
        Return the xdata.

        If *orig* is *True*, return the original data, else the
        processed data.
        """
        if orig:
            return self._xorig
        if self._invalidx:
            self.recache()
        return self._x

    def get_ydata(self, orig=True):
        """
        Return the ydata.

        If *orig* is *True*, return the original data, else the
        processed data.
        """
        if orig:
            return self._yorig
        if self._invalidy:
            self.recache()
        return self._y

    def get_path(self):
        """Return the `~matplotlib.path.Path` associated with this line."""
        if self._invalidy or self._invalidx:
            self.recache()
        return self._path

    def get_xydata(self):
        """Return the *xy* data as a (N, 2) array."""
        if self._invalidy or self._invalidx:
            self.recache()
        return self._xy

    def set_antialiased(self, b):
        """
        Set whether to use antialiased rendering.

        Parameters
        ----------
        b : bool
        """
        if self._antialiased != b:
            self.stale = True
        self._antialiased = b

    def set_color(self, color):
        """
        Set the color of the line.

        Parameters
        ----------
        color : :mpltype:`color`
        """
        mcolors._check_color_like(color=color)
        self._color = color
        self.stale = True

    def set_drawstyle(self, drawstyle):
        """
        Set the drawstyle of the plot.

        The drawstyle determines how the points are connected.

        Parameters
        ----------
        drawstyle : {'default', 'steps', 'steps-pre', 'steps-mid', \
'steps-post'}, default: 'default'
            For 'default', the points are connected with straight lines.

            The steps variants connect the points with step-like lines,
            i.e. horizontal lines with vertical steps. They differ in the
            location of the step:

            - 'steps-pre': The step is at the beginning of the line segment,
              i.e. the line will be at the y-value of point to the right.
            - 'steps-mid': The step is halfway between the points.
            - 'steps-post: The step is at the end of the line segment,
              i.e. the line will be at the y-value of the point to the left.
            - 'steps' is equal to 'steps-pre' and is maintained for
              backward-compatibility.

            For examples see :doc:`/gallery/lines_bars_and_markers/step_demo`.
        """
        if drawstyle is None:
            drawstyle = 'default'
        _api.check_in_list(self.drawStyles, drawstyle=drawstyle)
        if self._drawstyle != drawstyle:
            self.stale = True
            # invalidate to trigger a recache of the path
            self._invalidx = True
        self._drawstyle = drawstyle

    def set_gapcolor(self, gapcolor):
        """
        Set a color to fill the gaps in the dashed line style.

        .. note::

            Striped lines are created by drawing two interleaved dashed lines.
            There can be overlaps between those two, which may result in
            artifacts when using transparency.

            This functionality is experimental and may change.

        Parameters
        ----------
        gapcolor : :mpltype:`color` or None
            The color with which to fill the gaps. If None, the gaps are
            unfilled.
        """
        if gapcolor is not None:
            mcolors._check_color_like(color=gapcolor)
        self._gapcolor = gapcolor
        self.stale = True

    def set_linewidth(self, w):
        """
        Set the line width in points.

        Parameters
        ----------
        w : float
            Line width, in points.
        """
        w = float(w)
        if self._linewidth != w:
            self.stale = True
        self._linewidth = w
        self._dash_pattern = _scale_dashes(*self._unscaled_dash_pattern, w)

    def set_linestyle(self, ls):
        """
        Set the linestyle of the line.

        Parameters
        ----------
        ls : {'-', '--', '-.', ':', '', (offset, on-off-seq), ...}
            Possible values:

            - A string:

              ==========================================  =================
              linestyle                                   description
              ==========================================  =================
              ``'-'`` or ``'solid'``                      solid line
              ``'--'`` or  ``'dashed'``                   dashed line
              ``'-.'`` or  ``'dashdot'``                  dash-dotted line
              ``':'`` or ``'dotted'``                     dotted line
              ``'none'``, ``'None'``, ``' '``, or ``''``  draw nothing
              ==========================================  =================

            - Alternatively a dash tuple of the following form can be
              provided::

                  (offset, onoffseq)

              where ``onoffseq`` is an even length tuple of on and off ink
              in points. See also :meth:`set_dashes`.

            For examples see :doc:`/gallery/lines_bars_and_markers/linestyles`.
        """
        if isinstance(ls, str):
            if ls in [' ', '', 'none']:
                ls = 'None'
            _api.check_in_list([*self._lineStyles, *ls_mapper_r], ls=ls)
            if ls not in self._lineStyles:
                ls = ls_mapper_r[ls]
            self._linestyle = ls
        else:
            self._linestyle = '--'
        self._unscaled_dash_pattern = _get_dash_pattern(ls)
        self._dash_pattern = _scale_dashes(
            *self._unscaled_dash_pattern, self._linewidth)
        self.stale = True

    @_docstring.interpd
    def set_marker(self, marker):
        """
        Set the line marker.

        Parameters
        ----------
        marker : marker style string, `~.path.Path` or `~.markers.MarkerStyle`
            See `~matplotlib.markers` for full description of possible
            arguments.
        """
        self._marker = MarkerStyle(marker, self._marker.get_fillstyle())
        self.stale = True

    def _set_markercolor(self, name, has_rcdefault, val):
        if val is None:
            val = mpl.rcParams[f"lines.{name}"] if has_rcdefault else "auto"
        attr = f"_{name}"
        current = getattr(self, attr)
        if current is None:
            self.stale = True
        else:
            neq = current != val
            # Much faster than `np.any(current != val)` if no arrays are used.
            if neq.any() if isinstance(neq, np.ndarray) else neq:
                self.stale = True
        setattr(self, attr, val)

    def set_markeredgecolor(self, ec):
        """
        Set the marker edge color.

        Parameters
        ----------
        ec : :mpltype:`color`
        """
        self._set_markercolor("markeredgecolor", True, ec)

    def set_markerfacecolor(self, fc):
        """
        Set the marker face color.

        Parameters
        ----------
        fc : :mpltype:`color`
        """
        self._set_markercolor("markerfacecolor", True, fc)

    def set_markerfacecoloralt(self, fc):
        """
        Set the alternate marker face color.

        Parameters
        ----------
        fc : :mpltype:`color`
        """
        self._set_markercolor("markerfacecoloralt", False, fc)

    def set_markeredgewidth(self, ew):
        """
        Set the marker edge width in points.

        Parameters
        ----------
        ew : float
             Marker edge width, in points.
        """
        if ew is None:
            ew = mpl.rcParams['lines.markeredgewidth']
        if self._markeredgewidth != ew:
            self.stale = True
        self._markeredgewidth = ew

    def set_markersize(self, sz):
        """
        Set the marker size in points.

        Parameters
        ----------
        sz : float
             Marker size, in points.
        """
        sz = float(sz)
        if self._markersize != sz:
            self.stale = True
        self._markersize = sz

    def set_xdata(self, x):
        """
        Set the data array for x.

        Parameters
        ----------
        x : 1D array

        See Also
        --------
        set_data
        set_ydata
        """
        if not np.iterable(x):
            raise RuntimeError('x must be a sequence')
        self._xorig = copy.copy(x)
        self._invalidx = True
        self.stale = True

    def set_ydata(self, y):
        """
        Set the data array for y.

        Parameters
        ----------
        y : 1D array

        See Also
        --------
        set_data
        set_xdata
        """
        if not np.iterable(y):
            raise RuntimeError('y must be a sequence')
        self._yorig = copy.copy(y)
        self._invalidy = True
        self.stale = True

    def set_dashes(self, seq):
        """
        Set the dash sequence.

        The dash sequence is a sequence of floats of even length describing
        the length of dashes and spaces in points.

        For example, (5, 2, 1, 2) describes a sequence of 5 point and 1 point
        dashes separated by 2 point spaces.

        See also `~.Line2D.set_gapcolor`, which allows those spaces to be
        filled with a color.

        Parameters
        ----------
        seq : sequence of floats (on/off ink in points) or (None, None)
            If *seq* is empty or ``(None, None)``, the linestyle will be set
            to solid.
        """
        if seq == (None, None) or len(seq) == 0:
            self.set_linestyle('-')
        else:
            self.set_linestyle((0, seq))

    def update_from(self, other):
        """Copy properties from *other* to self."""
        super().update_from(other)
        self._linestyle = other._linestyle
        self._linewidth = other._linewidth
        self._color = other._color
        self._gapcolor = other._gapcolor
        self._markersize = other._markersize
        self._markerfacecolor = other._markerfacecolor
        self._markerfacecoloralt = other._markerfacecoloralt
        self._markeredgecolor = other._markeredgecolor
        self._markeredgewidth = other._markeredgewidth
        self._unscaled_dash_pattern = other._unscaled_dash_pattern
        self._dash_pattern = other._dash_pattern
        self._dashcapstyle = other._dashcapstyle
        self._dashjoinstyle = other._dashjoinstyle
        self._solidcapstyle = other._solidcapstyle
        self._solidjoinstyle = other._solidjoinstyle

        self._linestyle = other._linestyle
        self._marker = MarkerStyle(marker=other._marker)
        self._drawstyle = other._drawstyle

    @_docstring.interpd
    def set_dash_joinstyle(self, s):
        """
        How to join segments of the line if it `~Line2D.is_dashed`.

        The default joinstyle is :rc:`lines.dash_joinstyle`.

        Parameters
        ----------
        s : `.JoinStyle` or %(JoinStyle)s
        """
        js = JoinStyle(s)
        if self._dashjoinstyle != js:
            self.stale = True
        self._dashjoinstyle = js

    @_docstring.interpd
    def set_solid_joinstyle(self, s):
        """
        How to join segments if the line is solid (not `~Line2D.is_dashed`).

        The default joinstyle is :rc:`lines.solid_joinstyle`.

        Parameters
        ----------
        s : `.JoinStyle` or %(JoinStyle)s
        """
        js = JoinStyle(s)
        if self._solidjoinstyle != js:
            self.stale = True
        self._solidjoinstyle = js

    def get_dash_joinstyle(self):
        """
        Return the `.JoinStyle` for dashed lines.

        See also `~.Line2D.set_dash_joinstyle`.
        """
        return self._dashjoinstyle.name

    def get_solid_joinstyle(self):
        """
        Return the `.JoinStyle` for solid lines.

        See also `~.Line2D.set_solid_joinstyle`.
        """
        return self._solidjoinstyle.name

    @_docstring.interpd
    def set_dash_capstyle(self, s):
        """
        How to draw the end caps if the line is `~Line2D.is_dashed`.

        The default capstyle is :rc:`lines.dash_capstyle`.

        Parameters
        ----------
        s : `.CapStyle` or %(CapStyle)s
        """
        cs = CapStyle(s)
        if self._dashcapstyle != cs:
            self.stale = True
        self._dashcapstyle = cs

    @_docstring.interpd
    def set_solid_capstyle(self, s):
        """
        How to draw the end caps if the line is solid (not `~Line2D.is_dashed`)

        The default capstyle is :rc:`lines.solid_capstyle`.

        Parameters
        ----------
        s : `.CapStyle` or %(CapStyle)s
        """
        cs = CapStyle(s)
        if self._solidcapstyle != cs:
            self.stale = True
        self._solidcapstyle = cs

    def get_dash_capstyle(self):
        """
        Return the `.CapStyle` for dashed lines.

        See also `~.Line2D.set_dash_capstyle`.
        """
        return self._dashcapstyle.name

    def get_solid_capstyle(self):
        """
        Return the `.CapStyle` for solid lines.

        See also `~.Line2D.set_solid_capstyle`.
        """
        return self._solidcapstyle.name

    def is_dashed(self):
        """
        Return whether line has a dashed linestyle.

        A custom linestyle is assumed to be dashed, we do not inspect the
        ``onoffseq`` directly.

        See also `~.Line2D.set_linestyle`.
        """
        return self._linestyle in ('--', '-.', ':')


class AxLine(Line2D):
    """
    A helper class that implements `~.Axes.axline`, by recomputing the artist
    transform at draw time.
    """

    def __init__(self, xy1, xy2, slope, **kwargs):
        """
        Parameters
        ----------
        xy1 : (float, float)
            The first set of (x, y) coordinates for the line to pass through.
        xy2 : (float, float) or None
            The second set of (x, y) coordinates for the line to pass through.
            Both *xy2* and *slope* must be passed, but one of them must be None.
        slope : float or None
            The slope of the line. Both *xy2* and *slope* must be passed, but one of
            them must be None.
        """
        super().__init__([0, 1], [0, 1], **kwargs)

        if (xy2 is None and slope is None or
                xy2 is not None and slope is not None):
            raise TypeError(
                "Exactly one of 'xy2' and 'slope' must be given")

        self._slope = slope
        self._xy1 = xy1
        self._xy2 = xy2

    def get_transform(self):
        ax = self.axes
        points_transform = self._transform - ax.transData + ax.transScale

        if self._xy2 is not None:
            # two points were given
            (x1, y1), (x2, y2) = \
                points_transform.transform([self._xy1, self._xy2])
            dx = x2 - x1
            dy = y2 - y1
            if dx == 0:
                if dy == 0:
                    raise ValueError(
                        f"Cannot draw a line through two identical points "
                        f"(x={(x1, x2)}, y={(y1, y2)})")
                slope = np.inf
            else:
                slope = dy / dx
        else:
            # one point and a slope were given
            x1, y1 = points_transform.transform(self._xy1)
            slope = self._slope
        (vxlo, vylo), (vxhi, vyhi) = ax.transScale.transform(ax.viewLim)
        # General case: find intersections with view limits in either
        # direction, and draw between the middle two points.
        if slope == 0:
            start = vxlo, y1
            stop = vxhi, y1
        elif np.isinf(slope):
            start = x1, vylo
            stop = x1, vyhi
        else:
            _, start, stop, _ = sorted([
                (vxlo, y1 + (vxlo - x1) * slope),
                (vxhi, y1 + (vxhi - x1) * slope),
                (x1 + (vylo - y1) / slope, vylo),
                (x1 + (vyhi - y1) / slope, vyhi),
            ])
        return (BboxTransformTo(Bbox([start, stop]))
                + ax.transLimits + ax.transAxes)

    def draw(self, renderer):
        self._transformed_path = None  # Force regen.
        super().draw(renderer)

    def get_xy1(self):
        """Return the *xy1* value of the line."""
        return self._xy1

    def get_xy2(self):
        """Return the *xy2* value of the line."""
        return self._xy2

    def get_slope(self):
        """Return the *slope* value of the line."""
        return self._slope

    def set_xy1(self, *args, **kwargs):
        """
        Set the *xy1* value of the line.

        Parameters
        ----------
        xy1 : tuple[float, float]
            Points for the line to pass through.
        """
        params = _api.select_matching_signature([
            lambda self, x, y: locals(), lambda self, xy1: locals(),
        ], self, *args, **kwargs)
        if "x" in params:
            _api.warn_deprecated("3.10", message=(
                "Passing x and y separately to AxLine.set_xy1 is deprecated since "
                "%(since)s; pass them as a single tuple instead."))
            xy1 = params["x"], params["y"]
        else:
            xy1 = params["xy1"]
        self._xy1 = xy1

    def set_xy2(self, *args, **kwargs):
        """
        Set the *xy2* value of the line.

        .. note::

            You can only set *xy2* if the line was created using the *xy2*
            parameter. If the line was created using *slope*, please use
            `~.AxLine.set_slope`.

        Parameters
        ----------
        xy2 : tuple[float, float]
            Points for the line to pass through.
        """
        if self._slope is None:
            params = _api.select_matching_signature([
                lambda self, x, y: locals(), lambda self, xy2: locals(),
            ], self, *args, **kwargs)
            if "x" in params:
                _api.warn_deprecated("3.10", message=(
                    "Passing x and y separately to AxLine.set_xy2 is deprecated since "
                    "%(since)s; pass them as a single tuple instead."))
                xy2 = params["x"], params["y"]
            else:
                xy2 = params["xy2"]
            self._xy2 = xy2
        else:
            raise ValueError("Cannot set an 'xy2' value while 'slope' is set;"
                             " they differ but their functionalities overlap")

    def set_slope(self, slope):
        """
        Set the *slope* value of the line.

        .. note::

            You can only set *slope* if the line was created using the *slope*
            parameter. If the line was created using *xy2*, please use
            `~.AxLine.set_xy2`.

        Parameters
        ----------
        slope : float
            The slope of the line.
        """
        if self._xy2 is None:
            self._slope = slope
        else:
            raise ValueError("Cannot set a 'slope' value while 'xy2' is set;"
                             " they differ but their functionalities overlap")


class VertexSelector:
    """
    Manage the callbacks to maintain a list of selected vertices for `.Line2D`.
    Derived classes should override the `process_selected` method to do
    something with the picks.

    Here is an example which highlights the selected verts with red circles::

        import numpy as np
        import matplotlib.pyplot as plt
        import matplotlib.lines as lines

        class HighlightSelected(lines.VertexSelector):
            def __init__(self, line, fmt='ro', **kwargs):
                super().__init__(line)
                self.markers, = self.axes.plot([], [], fmt, **kwargs)

            def process_selected(self, ind, xs, ys):
                self.markers.set_data(xs, ys)
                self.canvas.draw()

        fig, ax = plt.subplots()
        x, y = np.random.rand(2, 30)
        line, = ax.plot(x, y, 'bs-', picker=5)

        selector = HighlightSelected(line)
        plt.show()
    """

    def __init__(self, line):
        """
        Parameters
        ----------
        line : `~matplotlib.lines.Line2D`
            The line must already have been added to an `~.axes.Axes` and must
            have its picker property set.
        """
        if line.axes is None:
            raise RuntimeError('You must first add the line to the Axes')
        if line.get_picker() is None:
            raise RuntimeError('You must first set the picker property '
                               'of the line')
        self.axes = line.axes
        self.line = line
        self.cid = self.canvas.callbacks._connect_picklable(
            'pick_event', self.onpick)
        self.ind = set()

    canvas = property(lambda self: self.axes.get_figure(root=True).canvas)

    def process_selected(self, ind, xs, ys):
        """
        Default "do nothing" implementation of the `process_selected` method.

        Parameters
        ----------
        ind : list of int
            The indices of the selected vertices.
        xs, ys : array-like
            The coordinates of the selected vertices.
        """
        pass

    def onpick(self, event):
        """When the line is picked, update the set of selected indices."""
        if event.artist is not self.line:
            return
        self.ind ^= set(event.ind)
        ind = sorted(self.ind)
        xdata, ydata = self.line.get_data()
        self.process_selected(ind, xdata[ind], ydata[ind])


lineStyles = Line2D._lineStyles
lineMarkers = MarkerStyle.markers
drawStyles = Line2D.drawStyles
fillStyles = MarkerStyle.fillstyles
