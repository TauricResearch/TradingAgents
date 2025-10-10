from collections.abc import Iterable, Sequence
from contextlib import ExitStack
import functools
import inspect
import logging
from numbers import Real
from operator import attrgetter
import re
import types

import numpy as np

import matplotlib as mpl
from matplotlib import _api, cbook, _docstring, offsetbox
import matplotlib.artist as martist
import matplotlib.axis as maxis
from matplotlib.cbook import _OrderedSet, _check_1d, index_of
import matplotlib.collections as mcoll
import matplotlib.colors as mcolors
import matplotlib.font_manager as font_manager
from matplotlib.gridspec import SubplotSpec
import matplotlib.image as mimage
import matplotlib.lines as mlines
import matplotlib.patches as mpatches
from matplotlib.rcsetup import cycler, validate_axisbelow
import matplotlib.spines as mspines
import matplotlib.table as mtable
import matplotlib.text as mtext
import matplotlib.ticker as mticker
import matplotlib.transforms as mtransforms

_log = logging.getLogger(__name__)


class _axis_method_wrapper:
    """
    Helper to generate Axes methods wrapping Axis methods.

    After ::

        get_foo = _axis_method_wrapper("xaxis", "get_bar")

    (in the body of a class) ``get_foo`` is a method that forwards it arguments
    to the ``get_bar`` method of the ``xaxis`` attribute, and gets its
    signature and docstring from ``Axis.get_bar``.

    The docstring of ``get_foo`` is built by replacing "this Axis" by "the
    {attr_name}" (i.e., "the xaxis", "the yaxis") in the wrapped method's
    dedented docstring; additional replacements can be given in *doc_sub*.
    """

    def __init__(self, attr_name, method_name, *, doc_sub=None):
        self.attr_name = attr_name
        self.method_name = method_name
        # Immediately put the docstring in ``self.__doc__`` so that docstring
        # manipulations within the class body work as expected.
        doc = inspect.getdoc(getattr(maxis.Axis, method_name))
        self._missing_subs = []
        if doc:
            doc_sub = {"this Axis": f"the {self.attr_name}", **(doc_sub or {})}
            for k, v in doc_sub.items():
                if k not in doc:  # Delay raising error until we know qualname.
                    self._missing_subs.append(k)
                doc = doc.replace(k, v)
        self.__doc__ = doc

    def __set_name__(self, owner, name):
        # This is called at the end of the class body as
        # ``self.__set_name__(cls, name_under_which_self_is_assigned)``; we
        # rely on that to give the wrapper the correct __name__/__qualname__.
        get_method = attrgetter(f"{self.attr_name}.{self.method_name}")

        def wrapper(self, *args, **kwargs):
            return get_method(self)(*args, **kwargs)

        wrapper.__module__ = owner.__module__
        wrapper.__name__ = name
        wrapper.__qualname__ = f"{owner.__qualname__}.{name}"
        wrapper.__doc__ = self.__doc__
        # Manually copy the signature instead of using functools.wraps because
        # displaying the Axis method source when asking for the Axes method
        # source would be confusing.
        wrapper.__signature__ = inspect.signature(
            getattr(maxis.Axis, self.method_name))

        if self._missing_subs:
            raise ValueError(
                "The definition of {} expected that the docstring of Axis.{} "
                "contains {!r} as substrings".format(
                    wrapper.__qualname__, self.method_name,
                    ", ".join(map(repr, self._missing_subs))))

        setattr(owner, name, wrapper)


class _TransformedBoundsLocator:
    """
    Axes locator for `.Axes.inset_axes` and similarly positioned Axes.

    The locator is a callable object used in `.Axes.set_aspect` to compute the
    Axes location depending on the renderer.
    """

    def __init__(self, bounds, transform):
        """
        *bounds* (a ``[l, b, w, h]`` rectangle) and *transform* together
        specify the position of the inset Axes.
        """
        self._bounds = bounds
        self._transform = transform

    def __call__(self, ax, renderer):
        # Subtracting transSubfigure will typically rely on inverted(),
        # freezing the transform; thus, this needs to be delayed until draw
        # time as transSubfigure may otherwise change after this is evaluated.
        return mtransforms.TransformedBbox(
            mtransforms.Bbox.from_bounds(*self._bounds),
            self._transform - ax.get_figure(root=False).transSubfigure)


def _process_plot_format(fmt, *, ambiguous_fmt_datakey=False):
    """
    Convert a MATLAB style color/line style format string to a (*linestyle*,
    *marker*, *color*) tuple.

    Example format strings include:

    * 'ko': black circles
    * '.b': blue dots
    * 'r--': red dashed lines
    * 'C2--': the third color in the color cycle, dashed lines

    The format is absolute in the sense that if a linestyle or marker is not
    defined in *fmt*, there is no line or marker. This is expressed by
    returning 'None' for the respective quantity.

    See Also
    --------
    matplotlib.Line2D.lineStyles, matplotlib.colors.cnames
        All possible styles and color format strings.
    """

    linestyle = None
    marker = None
    color = None

    # First check whether fmt is just a colorspec, but specifically exclude the
    # grayscale string "1" (not "1.0"), which is interpreted as the tri_down
    # marker "1".  The grayscale string "0" could be unambiguously understood
    # as a color (black) but also excluded for consistency.
    if fmt not in ["0", "1"]:
        try:
            color = mcolors.to_rgba(fmt)
            return linestyle, marker, color
        except ValueError:
            pass

    errfmt = ("{!r} is neither a data key nor a valid format string ({})"
              if ambiguous_fmt_datakey else
              "{!r} is not a valid format string ({})")

    i = 0
    while i < len(fmt):
        c = fmt[i]
        if fmt[i:i+2] in mlines.lineStyles:  # First, the two-char styles.
            if linestyle is not None:
                raise ValueError(errfmt.format(fmt, "two linestyle symbols"))
            linestyle = fmt[i:i+2]
            i += 2
        elif c in mlines.lineStyles:
            if linestyle is not None:
                raise ValueError(errfmt.format(fmt, "two linestyle symbols"))
            linestyle = c
            i += 1
        elif c in mlines.lineMarkers:
            if marker is not None:
                raise ValueError(errfmt.format(fmt, "two marker symbols"))
            marker = c
            i += 1
        elif c in mcolors.get_named_colors_mapping():
            if color is not None:
                raise ValueError(errfmt.format(fmt, "two color symbols"))
            color = c
            i += 1
        elif c == "C":
            cn_color = re.match(r"C\d+", fmt[i:])
            if not cn_color:
                raise ValueError(errfmt.format(fmt, "'C' must be followed by a number"))
            color = mcolors.to_rgba(cn_color[0])
            i += len(cn_color[0])
        else:
            raise ValueError(errfmt.format(fmt, f"unrecognized character {c!r}"))

    if linestyle is None and marker is None:
        linestyle = mpl.rcParams['lines.linestyle']
    if linestyle is None:
        linestyle = 'None'
    if marker is None:
        marker = 'None'

    return linestyle, marker, color


class _process_plot_var_args:
    """
    Process variable length arguments to `~.Axes.plot`, to support ::

      plot(t, s)
      plot(t1, s1, t2, s2)
      plot(t1, s1, 'ko', t2, s2)
      plot(t1, s1, 'ko', t2, s2, 'r--', t3, e3)

    an arbitrary number of *x*, *y*, *fmt* are allowed
    """

    def __init__(self, output='Line2D'):
        _api.check_in_list(['Line2D', 'Polygon', 'coordinates'], output=output)
        self.output = output
        self.set_prop_cycle(None)

    def set_prop_cycle(self, cycler):
        if cycler is None:
            cycler = mpl.rcParams['axes.prop_cycle']
        self._idx = 0
        self._cycler_items = [*cycler]

    def __call__(self, axes, *args, data=None, return_kwargs=False, **kwargs):
        axes._process_unit_info(kwargs=kwargs)

        for pos_only in "xy":
            if pos_only in kwargs:
                raise _api.kwarg_error(inspect.stack()[1].function, pos_only)

        if not args:
            return

        if data is None:  # Process dict views
            args = [cbook.sanitize_sequence(a) for a in args]
        else:  # Process the 'data' kwarg.
            replaced = [mpl._replacer(data, arg) for arg in args]
            if len(args) == 1:
                label_namer_idx = 0
            elif len(args) == 2:  # Can be x, y or y, c.
                # Figure out what the second argument is.
                # 1) If the second argument cannot be a format shorthand, the
                #    second argument is the label_namer.
                # 2) Otherwise (it could have been a format shorthand),
                #    a) if we did perform a substitution, emit a warning, and
                #       use it as label_namer.
                #    b) otherwise, it is indeed a format shorthand; use the
                #       first argument as label_namer.
                try:
                    _process_plot_format(args[1])
                except ValueError:  # case 1)
                    label_namer_idx = 1
                else:
                    if replaced[1] is not args[1]:  # case 2a)
                        _api.warn_external(
                            f"Second argument {args[1]!r} is ambiguous: could "
                            f"be a format string but is in 'data'; using as "
                            f"data.  If it was intended as data, set the "
                            f"format string to an empty string to suppress "
                            f"this warning.  If it was intended as a format "
                            f"string, explicitly pass the x-values as well.  "
                            f"Alternatively, rename the entry in 'data'.",
                            RuntimeWarning)
                        label_namer_idx = 1
                    else:  # case 2b)
                        label_namer_idx = 0
            elif len(args) == 3:
                label_namer_idx = 1
            else:
                raise ValueError(
                    "Using arbitrary long args with data is not supported due "
                    "to ambiguity of arguments; use multiple plotting calls "
                    "instead")
            if kwargs.get("label") is None:
                kwargs["label"] = mpl._label_from_arg(
                    replaced[label_namer_idx], args[label_namer_idx])
            args = replaced
        ambiguous_fmt_datakey = data is not None and len(args) == 2

        if len(args) >= 4 and not cbook.is_scalar_or_string(
                kwargs.get("label")):
            raise ValueError("plot() with multiple groups of data (i.e., "
                             "pairs of x and y) does not support multiple "
                             "labels")

        # Repeatedly grab (x, y) or (x, y, format) from the front of args and
        # massage them into arguments to plot() or fill().

        while args:
            this, args = args[:2], args[2:]
            if args and isinstance(args[0], str):
                this += args[0],
                args = args[1:]
            yield from self._plot_args(
                axes, this, kwargs, ambiguous_fmt_datakey=ambiguous_fmt_datakey,
                return_kwargs=return_kwargs
            )

    def get_next_color(self):
        """Return the next color in the cycle."""
        entry = self._cycler_items[self._idx]
        if "color" in entry:
            self._idx = (self._idx + 1) % len(self._cycler_items)  # Advance cycler.
            return entry["color"]
        else:
            return "k"

    def _getdefaults(self, kw, ignore=frozenset()):
        """
        If some keys in the property cycle (excluding those in the set
        *ignore*) are absent or set to None in the dict *kw*, return a copy
        of the next entry in the property cycle, excluding keys in *ignore*.
        Otherwise, don't advance the property cycle, and return an empty dict.
        """
        defaults = self._cycler_items[self._idx]
        if any(kw.get(k, None) is None for k in {*defaults} - ignore):
            self._idx = (self._idx + 1) % len(self._cycler_items)  # Advance cycler.
            # Return a new dict to avoid exposing _cycler_items entries to mutation.
            return {k: v for k, v in defaults.items() if k not in ignore}
        else:
            return {}

    def _setdefaults(self, defaults, kw):
        """
        Add to the dict *kw* the entries in the dict *default* that are absent
        or set to None in *kw*.
        """
        for k in defaults:
            if kw.get(k, None) is None:
                kw[k] = defaults[k]

    def _make_line(self, axes, x, y, kw, kwargs):
        kw = {**kw, **kwargs}  # Don't modify the original kw.
        self._setdefaults(self._getdefaults(kw), kw)
        seg = mlines.Line2D(x, y, **kw)
        return seg, kw

    def _make_coordinates(self, axes, x, y, kw, kwargs):
        kw = {**kw, **kwargs}  # Don't modify the original kw.
        self._setdefaults(self._getdefaults(kw), kw)
        return (x, y), kw

    def _make_polygon(self, axes, x, y, kw, kwargs):
        # Polygon doesn't directly support unitized inputs.
        x = axes.convert_xunits(x)
        y = axes.convert_yunits(y)

        kw = kw.copy()  # Don't modify the original kw.
        kwargs = kwargs.copy()

        # Ignore 'marker'-related properties as they aren't Polygon
        # properties, but they are Line2D properties, and so they are
        # likely to appear in the default cycler construction.
        # This is done here to the defaults dictionary as opposed to the
        # other two dictionaries because we do want to capture when a
        # *user* explicitly specifies a marker which should be an error.
        # We also want to prevent advancing the cycler if there are no
        # defaults needed after ignoring the given properties.
        ignores = ({'marker', 'markersize', 'markeredgecolor',
                    'markerfacecolor', 'markeredgewidth'}
                   # Also ignore anything provided by *kwargs*.
                   | {k for k, v in kwargs.items() if v is not None})

        # Only using the first dictionary to use as basis
        # for getting defaults for back-compat reasons.
        # Doing it with both seems to mess things up in
        # various places (probably due to logic bugs elsewhere).
        default_dict = self._getdefaults(kw, ignores)
        self._setdefaults(default_dict, kw)

        # Looks like we don't want "color" to be interpreted to
        # mean both facecolor and edgecolor for some reason.
        # So the "kw" dictionary is thrown out, and only its
        # 'color' value is kept and translated as a 'facecolor'.
        # This design should probably be revisited as it increases
        # complexity.
        facecolor = kw.get('color', None)

        # Throw out 'color' as it is now handled as a facecolor
        default_dict.pop('color', None)

        # To get other properties set from the cycler
        # modify the kwargs dictionary.
        self._setdefaults(default_dict, kwargs)

        seg = mpatches.Polygon(np.column_stack((x, y)),
                               facecolor=facecolor,
                               fill=kwargs.get('fill', True),
                               closed=kw['closed'])
        seg.set(**kwargs)
        return seg, kwargs

    def _plot_args(self, axes, tup, kwargs, *,
                   return_kwargs=False, ambiguous_fmt_datakey=False):
        """
        Process the arguments of ``plot([x], y, [fmt], **kwargs)`` calls.

        This processes a single set of ([x], y, [fmt]) parameters; i.e. for
        ``plot(x, y, x2, y2)`` it will be called twice. Once for (x, y) and
        once for (x2, y2).

        x and y may be 2D and thus can still represent multiple datasets.

        For multiple datasets, if the keyword argument *label* is a list, this
        will unpack the list and assign the individual labels to the datasets.

        Parameters
        ----------
        tup : tuple
            A tuple of the positional parameters. This can be one of

            - (y,)
            - (x, y)
            - (y, fmt)
            - (x, y, fmt)

        kwargs : dict
            The keyword arguments passed to ``plot()``.

        return_kwargs : bool
            Whether to also return the effective keyword arguments after label
            unpacking as well.

        ambiguous_fmt_datakey : bool
            Whether the format string in *tup* could also have been a
            misspelled data key.

        Returns
        -------
        result
            If *return_kwargs* is false, a list of Artists representing the
            dataset(s).
            If *return_kwargs* is true, a list of (Artist, effective_kwargs)
            representing the dataset(s). See *return_kwargs*.
            The Artist is either `.Line2D` (if called from ``plot()``) or
            `.Polygon` otherwise.
        """
        if len(tup) > 1 and isinstance(tup[-1], str):
            # xy is tup with fmt stripped (could still be (y,) only)
            *xy, fmt = tup
            linestyle, marker, color = _process_plot_format(
                fmt, ambiguous_fmt_datakey=ambiguous_fmt_datakey)
        elif len(tup) == 3:
            raise ValueError('third arg must be a format string')
        else:
            xy = tup
            linestyle, marker, color = None, None, None

        # Don't allow any None value; these would be up-converted to one
        # element array of None which causes problems downstream.
        if any(v is None for v in tup):
            raise ValueError("x, y, and format string must not be None")

        kw = {}
        for prop_name, val in zip(('linestyle', 'marker', 'color'),
                                  (linestyle, marker, color)):
            if val is not None:
                # check for conflicts between fmt and kwargs
                if (fmt.lower() != 'none'
                        and prop_name in kwargs
                        and val != 'None'):
                    # Technically ``plot(x, y, 'o', ls='--')`` is a conflict
                    # because 'o' implicitly unsets the linestyle
                    # (linestyle='None').
                    # We'll gracefully not warn in this case because an
                    # explicit set via kwargs can be seen as intention to
                    # override an implicit unset.
                    # Note: We don't val.lower() != 'none' because val is not
                    # necessarily a string (can be a tuple for colors). This
                    # is safe, because *val* comes from _process_plot_format()
                    # which only returns 'None'.
                    _api.warn_external(
                        f"{prop_name} is redundantly defined by the "
                        f"'{prop_name}' keyword argument and the fmt string "
                        f'"{fmt}" (-> {prop_name}={val!r}). The keyword '
                        f"argument will take precedence.")
                kw[prop_name] = val

        if len(xy) == 2:
            x = _check_1d(xy[0])
            y = _check_1d(xy[1])
        else:
            x, y = index_of(xy[-1])

        if axes.xaxis is not None:
            axes.xaxis.update_units(x)
        if axes.yaxis is not None:
            axes.yaxis.update_units(y)

        if x.shape[0] != y.shape[0]:
            raise ValueError(f"x and y must have same first dimension, but "
                             f"have shapes {x.shape} and {y.shape}")
        if x.ndim > 2 or y.ndim > 2:
            raise ValueError(f"x and y can be no greater than 2D, but have "
                             f"shapes {x.shape} and {y.shape}")
        if x.ndim == 1:
            x = x[:, np.newaxis]
        if y.ndim == 1:
            y = y[:, np.newaxis]

        if self.output == 'Line2D':
            make_artist = self._make_line
        elif self.output == 'Polygon':
            kw['closed'] = kwargs.get('closed', True)
            make_artist = self._make_polygon
        elif self.output == 'coordinates':
            make_artist = self._make_coordinates
        else:
            _api.check_in_list(['Line2D', 'Polygon', 'coordinates'], output=self.output)

        ncx, ncy = x.shape[1], y.shape[1]
        if ncx > 1 and ncy > 1 and ncx != ncy:
            raise ValueError(f"x has {ncx} columns but y has {ncy} columns")
        if ncx == 0 or ncy == 0:
            return []

        label = kwargs.get('label')
        n_datasets = max(ncx, ncy)

        if cbook.is_scalar_or_string(label):
            labels = [label] * n_datasets
        elif len(label) == n_datasets:
            labels = label
        elif n_datasets == 1:
            msg = (f'Passing label as a length {len(label)} sequence when '
                    'plotting a single dataset is deprecated in Matplotlib 3.9 '
                    'and will error in 3.11.  To keep the current behavior, '
                    'cast the sequence to string before passing.')
            _api.warn_deprecated('3.9', message=msg)
            labels = [label]
        else:
            raise ValueError(
                f"label must be scalar or have the same length as the input "
                f"data, but found {len(label)} for {n_datasets} datasets.")

        result = (make_artist(axes, x[:, j % ncx], y[:, j % ncy], kw,
                              {**kwargs, 'label': label})
                  for j, label in enumerate(labels))

        if return_kwargs:
            return list(result)
        else:
            return [l[0] for l in result]


@_api.define_aliases({"facecolor": ["fc"]})
class _AxesBase(martist.Artist):
    name = "rectilinear"

    # axis names are the prefixes for the attributes that contain the
    # respective axis; e.g. 'x' <-> self.xaxis, containing an XAxis.
    # Note that PolarAxes uses these attributes as well, so that we have
    # 'x' <-> self.xaxis, containing a ThetaAxis. In particular we do not
    # have 'theta' in _axis_names.
    # In practice, this is ('x', 'y') for all 2D Axes and ('x', 'y', 'z')
    # for Axes3D.
    _axis_names = ("x", "y")
    _shared_axes = {name: cbook.Grouper() for name in _axis_names}
    _twinned_axes = cbook.Grouper()

    _subclass_uses_cla = False

    dataLim: mtransforms.Bbox
    """The bounding `.Bbox` enclosing all data displayed in the Axes."""

    spines: mspines.Spines
    """
    The `.Spines` container for the Axes' spines, i.e. the lines denoting the
    data area boundaries.
    """

    xaxis: maxis.XAxis
    """
    The `.XAxis` instance.

    Common axis-related configuration can be achieved through high-level wrapper
    methods on Axes; e.g. `ax.set_xticks <.Axes.set_xticks>` is a shortcut for
    `ax.xaxis.set_ticks <.Axis.set_ticks>`. The *xaxis* attribute gives direct
    direct access to the underlying `~.axis.Axis` if you need more control.

    See also

    - :ref:`Axis wrapper methods on Axes <axes-api-axis>`
    - :doc:`Axis API </api/axis_api>`
    """

    yaxis: maxis.YAxis
    """
    The `.YAxis` instance.

    Common axis-related configuration can be achieved through high-level wrapper
    methods on Axes; e.g. `ax.set_yticks <.Axes.set_yticks>` is a shortcut for
    `ax.yaxis.set_ticks <.Axis.set_ticks>`. The *yaxis* attribute gives direct
    access to the underlying `~.axis.Axis` if you need more control.

    See also

    - :ref:`Axis wrapper methods on Axes <axes-api-axis>`
    - :doc:`Axis API </api/axis_api>`
    """

    @property
    def _axis_map(self):
        """A mapping of axis names, e.g. 'x', to `Axis` instances."""
        return {name: getattr(self, f"{name}axis")
                for name in self._axis_names}

    def __str__(self):
        return "{0}({1[0]:g},{1[1]:g};{1[2]:g}x{1[3]:g})".format(
            type(self).__name__, self._position.bounds)

    def __init__(self, fig,
                 *args,
                 facecolor=None,  # defaults to rc axes.facecolor
                 frameon=True,
                 sharex=None,  # use Axes instance's xaxis info
                 sharey=None,  # use Axes instance's yaxis info
                 label='',
                 xscale=None,
                 yscale=None,
                 box_aspect=None,
                 forward_navigation_events="auto",
                 **kwargs
                 ):
        """
        Build an Axes in a figure.

        Parameters
        ----------
        fig : `~matplotlib.figure.Figure`
            The Axes is built in the `.Figure` *fig*.

        *args
            ``*args`` can be a single ``(left, bottom, width, height)``
            rectangle or a single `.Bbox`.  This specifies the rectangle (in
            figure coordinates) where the Axes is positioned.

            ``*args`` can also consist of three numbers or a single three-digit
            number; in the latter case, the digits are considered as
            independent numbers.  The numbers are interpreted as ``(nrows,
            ncols, index)``: ``(nrows, ncols)`` specifies the size of an array
            of subplots, and ``index`` is the 1-based index of the subplot
            being created.  Finally, ``*args`` can also directly be a
            `.SubplotSpec` instance.

        sharex, sharey : `~matplotlib.axes.Axes`, optional
            The x- or y-`~.matplotlib.axis` is shared with the x- or y-axis in
            the input `~.axes.Axes`.  Note that it is not possible to unshare
            axes.

        frameon : bool, default: True
            Whether the Axes frame is visible.

        box_aspect : float, optional
            Set a fixed aspect for the Axes box, i.e. the ratio of height to
            width. See `~.axes.Axes.set_box_aspect` for details.

        forward_navigation_events : bool or "auto", default: "auto"
            Control whether pan/zoom events are passed through to Axes below
            this one. "auto" is *True* for axes with an invisible patch and
            *False* otherwise.

        **kwargs
            Other optional keyword arguments:

            %(Axes:kwdoc)s

        Returns
        -------
        `~.axes.Axes`
            The new `~.axes.Axes` object.
        """

        super().__init__()
        if "rect" in kwargs:
            if args:
                raise TypeError(
                    "'rect' cannot be used together with positional arguments")
            rect = kwargs.pop("rect")
            _api.check_isinstance((mtransforms.Bbox, Iterable), rect=rect)
            args = (rect,)
        subplotspec = None
        if len(args) == 1 and isinstance(args[0], mtransforms.Bbox):
            self._position = args[0].frozen()
        elif len(args) == 1 and np.iterable(args[0]):
            self._position = mtransforms.Bbox.from_bounds(*args[0])
        else:
            self._position = self._originalPosition = mtransforms.Bbox.unit()
            subplotspec = SubplotSpec._from_subplot_args(fig, args)
        if self._position.width < 0 or self._position.height < 0:
            raise ValueError('Width and height specified must be non-negative')
        self._originalPosition = self._position.frozen()
        self.axes = self
        self._aspect = 'auto'
        self._adjustable = 'box'
        self._anchor = 'C'
        self._stale_viewlims = dict.fromkeys(self._axis_names, False)
        self._forward_navigation_events = forward_navigation_events
        self._sharex = sharex
        self._sharey = sharey
        self.set_label(label)
        self.set_figure(fig)
        # The subplotspec needs to be set after the figure (so that
        # figure-level subplotpars are taken into account), but the figure
        # needs to be set after self._position is initialized.
        if subplotspec:
            self.set_subplotspec(subplotspec)
        else:
            self._subplotspec = None
        self.set_box_aspect(box_aspect)
        self._axes_locator = None  # Optionally set via update(kwargs).

        self._children = []

        # placeholder for any colorbars added that use this Axes.
        # (see colorbar.py):
        self._colorbars = []
        self.spines = mspines.Spines.from_dict(self._gen_axes_spines())

        # this call may differ for non-sep axes, e.g., polar
        self._init_axis()
        if facecolor is None:
            facecolor = mpl.rcParams['axes.facecolor']
        self._facecolor = facecolor
        self._frameon = frameon
        self.set_axisbelow(mpl.rcParams['axes.axisbelow'])

        self._rasterization_zorder = None
        self.clear()

        # funcs used to format x and y - fall back on major formatters
        self.fmt_xdata = None
        self.fmt_ydata = None

        self.set_navigate(True)
        self.set_navigate_mode(None)

        if xscale:
            self.set_xscale(xscale)
        if yscale:
            self.set_yscale(yscale)

        self._internal_update(kwargs)

        for name, axis in self._axis_map.items():
            axis.callbacks._connect_picklable(
                'units', self._unit_change_handler(name))

        rcParams = mpl.rcParams
        self.tick_params(
            top=rcParams['xtick.top'] and rcParams['xtick.minor.top'],
            bottom=rcParams['xtick.bottom'] and rcParams['xtick.minor.bottom'],
            labeltop=(rcParams['xtick.labeltop'] and
                      rcParams['xtick.minor.top']),
            labelbottom=(rcParams['xtick.labelbottom'] and
                         rcParams['xtick.minor.bottom']),
            left=rcParams['ytick.left'] and rcParams['ytick.minor.left'],
            right=rcParams['ytick.right'] and rcParams['ytick.minor.right'],
            labelleft=(rcParams['ytick.labelleft'] and
                       rcParams['ytick.minor.left']),
            labelright=(rcParams['ytick.labelright'] and
                        rcParams['ytick.minor.right']),
            which='minor')

        self.tick_params(
            top=rcParams['xtick.top'] and rcParams['xtick.major.top'],
            bottom=rcParams['xtick.bottom'] and rcParams['xtick.major.bottom'],
            labeltop=(rcParams['xtick.labeltop'] and
                      rcParams['xtick.major.top']),
            labelbottom=(rcParams['xtick.labelbottom'] and
                         rcParams['xtick.major.bottom']),
            left=rcParams['ytick.left'] and rcParams['ytick.major.left'],
            right=rcParams['ytick.right'] and rcParams['ytick.major.right'],
            labelleft=(rcParams['ytick.labelleft'] and
                       rcParams['ytick.major.left']),
            labelright=(rcParams['ytick.labelright'] and
                        rcParams['ytick.major.right']),
            which='major')

    def __init_subclass__(cls, **kwargs):
        parent_uses_cla = super(cls, cls)._subclass_uses_cla
        if 'cla' in cls.__dict__:
            _api.warn_deprecated(
                '3.6',
                pending=True,
                message=f'Overriding `Axes.cla` in {cls.__qualname__} is '
                'pending deprecation in %(since)s and will be fully '
                'deprecated in favor of `Axes.clear` in the future. '
                'Please report '
                f'this to the {cls.__module__!r} author.')
        cls._subclass_uses_cla = 'cla' in cls.__dict__ or parent_uses_cla
        super().__init_subclass__(**kwargs)

    def __getstate__(self):
        state = super().__getstate__()
        # Prune the sharing & twinning info to only contain the current group.
        state["_shared_axes"] = {
            name: self._shared_axes[name].get_siblings(self)
            for name in self._axis_names if self in self._shared_axes[name]}
        state["_twinned_axes"] = (self._twinned_axes.get_siblings(self)
                                  if self in self._twinned_axes else None)
        return state

    def __setstate__(self, state):
        # Merge the grouping info back into the global groupers.
        shared_axes = state.pop("_shared_axes")
        for name, shared_siblings in shared_axes.items():
            self._shared_axes[name].join(*shared_siblings)
        twinned_siblings = state.pop("_twinned_axes")
        if twinned_siblings:
            self._twinned_axes.join(*twinned_siblings)
        self.__dict__ = state
        self._stale = True

    def __repr__(self):
        fields = []
        if self.get_label():
            fields += [f"label={self.get_label()!r}"]
        if hasattr(self, "get_title"):
            titles = {}
            for k in ["left", "center", "right"]:
                title = self.get_title(loc=k)
                if title:
                    titles[k] = title
            if titles:
                fields += [f"title={titles}"]
        for name, axis in self._axis_map.items():
            if axis.label and axis.label.get_text():
                fields += [f"{name}label={axis.label.get_text()!r}"]
        return f"<{self.__class__.__name__}: " + ", ".join(fields) + ">"

    def get_subplotspec(self):
        """Return the `.SubplotSpec` associated with the subplot, or None."""
        return self._subplotspec

    def set_subplotspec(self, subplotspec):
        """Set the `.SubplotSpec`. associated with the subplot."""
        self._subplotspec = subplotspec
        self._set_position(subplotspec.get_position(self.get_figure(root=False)))

    def get_gridspec(self):
        """Return the `.GridSpec` associated with the subplot, or None."""
        return self._subplotspec.get_gridspec() if self._subplotspec else None

    def get_window_extent(self, renderer=None):
        """
        Return the Axes bounding box in display space.

        This bounding box does not include the spines, ticks, ticklabels,
        or other labels.  For a bounding box including these elements use
        `~matplotlib.axes.Axes.get_tightbbox`.

        See Also
        --------
        matplotlib.axes.Axes.get_tightbbox
        matplotlib.axis.Axis.get_tightbbox
        matplotlib.spines.Spine.get_window_extent
        """
        return self.bbox

    def _init_axis(self):
        # This is moved out of __init__ because non-separable axes don't use it
        self.xaxis = maxis.XAxis(self, clear=False)
        self.spines.bottom.register_axis(self.xaxis)
        self.spines.top.register_axis(self.xaxis)
        self.yaxis = maxis.YAxis(self, clear=False)
        self.spines.left.register_axis(self.yaxis)
        self.spines.right.register_axis(self.yaxis)

    def set_figure(self, fig):
        # docstring inherited
        super().set_figure(fig)

        self.bbox = mtransforms.TransformedBbox(self._position,
                                                fig.transSubfigure)
        # these will be updated later as data is added
        self.dataLim = mtransforms.Bbox.null()
        self._viewLim = mtransforms.Bbox.unit()
        self.transScale = mtransforms.TransformWrapper(
            mtransforms.IdentityTransform())

        self._set_lim_and_transforms()

    def _unstale_viewLim(self):
        # We should arrange to store this information once per share-group
        # instead of on every axis.
        need_scale = {
            name: any(ax._stale_viewlims[name]
                      for ax in self._shared_axes[name].get_siblings(self))
            for name in self._axis_names}
        if any(need_scale.values()):
            for name in need_scale:
                for ax in self._shared_axes[name].get_siblings(self):
                    ax._stale_viewlims[name] = False
            self.autoscale_view(**{f"scale{name}": scale
                                   for name, scale in need_scale.items()})

    @property
    def viewLim(self):
        """The view limits as `.Bbox` in data coordinates."""
        self._unstale_viewLim()
        return self._viewLim

    def _request_autoscale_view(self, axis="all", tight=None):
        """
        Mark a single axis, or all of them, as stale wrt. autoscaling.

        No computation is performed until the next autoscaling; thus, separate
        calls to control individual axises incur negligible performance cost.

        Parameters
        ----------
        axis : str, default: "all"
            Either an element of ``self._axis_names``, or "all".
        tight : bool or None, default: None
        """
        axis_names = _api.check_getitem(
            {**{k: [k] for k in self._axis_names}, "all": self._axis_names},
            axis=axis)
        for name in axis_names:
            self._stale_viewlims[name] = True
        if tight is not None:
            self._tight = tight

    def _set_lim_and_transforms(self):
        """
        Set the *_xaxis_transform*, *_yaxis_transform*, *transScale*,
        *transData*, *transLimits* and *transAxes* transformations.

        .. note::

            This method is primarily used by rectilinear projections of the
            `~matplotlib.axes.Axes` class, and is meant to be overridden by
            new kinds of projection Axes that need different transformations
            and limits. (See `~matplotlib.projections.polar.PolarAxes` for an
            example.)
        """
        self.transAxes = mtransforms.BboxTransformTo(self.bbox)

        # Transforms the x and y axis separately by a scale factor.
        # It is assumed that this part will have non-linear components
        # (e.g., for a log scale).
        self.transScale = mtransforms.TransformWrapper(
            mtransforms.IdentityTransform())

        # An affine transformation on the data, generally to limit the
        # range of the axes
        self.transLimits = mtransforms.BboxTransformFrom(
            mtransforms.TransformedBbox(self._viewLim, self.transScale))

        # The parentheses are important for efficiency here -- they
        # group the last two (which are usually affines) separately
        # from the first (which, with log-scaling can be non-affine).
        self.transData = self.transScale + (self.transLimits + self.transAxes)

        self._xaxis_transform = mtransforms.blended_transform_factory(
            self.transData, self.transAxes)
        self._yaxis_transform = mtransforms.blended_transform_factory(
            self.transAxes, self.transData)

    def get_xaxis_transform(self, which='grid'):
        """
        Get the transformation used for drawing x-axis labels, ticks
        and gridlines.  The x-direction is in data coordinates and the
        y-direction is in axis coordinates.

        .. note::

            This transformation is primarily used by the
            `~matplotlib.axis.Axis` class, and is meant to be
            overridden by new kinds of projections that may need to
            place axis elements in different locations.

        Parameters
        ----------
        which : {'grid', 'tick1', 'tick2'}
        """
        if which == 'grid':
            return self._xaxis_transform
        elif which == 'tick1':
            # for cartesian projection, this is bottom spine
            return self.spines.bottom.get_spine_transform()
        elif which == 'tick2':
            # for cartesian projection, this is top spine
            return self.spines.top.get_spine_transform()
        else:
            raise ValueError(f'unknown value for which: {which!r}')

    def get_xaxis_text1_transform(self, pad_points):
        """
        Returns
        -------
        transform : Transform
            The transform used for drawing x-axis labels, which will add
            *pad_points* of padding (in points) between the axis and the label.
            The x-direction is in data coordinates and the y-direction is in
            axis coordinates
        valign : {'center', 'top', 'bottom', 'baseline', 'center_baseline'}
            The text vertical alignment.
        halign : {'center', 'left', 'right'}
            The text horizontal alignment.

        Notes
        -----
        This transformation is primarily used by the `~matplotlib.axis.Axis`
        class, and is meant to be overridden by new kinds of projections that
        may need to place axis elements in different locations.
        """
        labels_align = mpl.rcParams["xtick.alignment"]
        return (self.get_xaxis_transform(which='tick1') +
                mtransforms.ScaledTranslation(
                    0, -1 * pad_points / 72,
                    self.get_figure(root=False).dpi_scale_trans),
                "top", labels_align)

    def get_xaxis_text2_transform(self, pad_points):
        """
        Returns
        -------
        transform : Transform
            The transform used for drawing secondary x-axis labels, which will
            add *pad_points* of padding (in points) between the axis and the
            label.  The x-direction is in data coordinates and the y-direction
            is in axis coordinates
        valign : {'center', 'top', 'bottom', 'baseline', 'center_baseline'}
            The text vertical alignment.
        halign : {'center', 'left', 'right'}
            The text horizontal alignment.

        Notes
        -----
        This transformation is primarily used by the `~matplotlib.axis.Axis`
        class, and is meant to be overridden by new kinds of projections that
        may need to place axis elements in different locations.
        """
        labels_align = mpl.rcParams["xtick.alignment"]
        return (self.get_xaxis_transform(which='tick2') +
                mtransforms.ScaledTranslation(
                    0, pad_points / 72,
                    self.get_figure(root=False).dpi_scale_trans),
                "bottom", labels_align)

    def get_yaxis_transform(self, which='grid'):
        """
        Get the transformation used for drawing y-axis labels, ticks
        and gridlines.  The x-direction is in axis coordinates and the
        y-direction is in data coordinates.

        .. note::

            This transformation is primarily used by the
            `~matplotlib.axis.Axis` class, and is meant to be
            overridden by new kinds of projections that may need to
            place axis elements in different locations.

        Parameters
        ----------
        which : {'grid', 'tick1', 'tick2'}
        """
        if which == 'grid':
            return self._yaxis_transform
        elif which == 'tick1':
            # for cartesian projection, this is bottom spine
            return self.spines.left.get_spine_transform()
        elif which == 'tick2':
            # for cartesian projection, this is top spine
            return self.spines.right.get_spine_transform()
        else:
            raise ValueError(f'unknown value for which: {which!r}')

    def get_yaxis_text1_transform(self, pad_points):
        """
        Returns
        -------
        transform : Transform
            The transform used for drawing y-axis labels, which will add
            *pad_points* of padding (in points) between the axis and the label.
            The x-direction is in axis coordinates and the y-direction is in
            data coordinates
        valign : {'center', 'top', 'bottom', 'baseline', 'center_baseline'}
            The text vertical alignment.
        halign : {'center', 'left', 'right'}
            The text horizontal alignment.

        Notes
        -----
        This transformation is primarily used by the `~matplotlib.axis.Axis`
        class, and is meant to be overridden by new kinds of projections that
        may need to place axis elements in different locations.
        """
        labels_align = mpl.rcParams["ytick.alignment"]
        return (self.get_yaxis_transform(which='tick1') +
                mtransforms.ScaledTranslation(
                    -1 * pad_points / 72, 0,
                    self.get_figure(root=False).dpi_scale_trans),
                labels_align, "right")

    def get_yaxis_text2_transform(self, pad_points):
        """
        Returns
        -------
        transform : Transform
            The transform used for drawing secondart y-axis labels, which will
            add *pad_points* of padding (in points) between the axis and the
            label.  The x-direction is in axis coordinates and the y-direction
            is in data coordinates
        valign : {'center', 'top', 'bottom', 'baseline', 'center_baseline'}
            The text vertical alignment.
        halign : {'center', 'left', 'right'}
            The text horizontal alignment.

        Notes
        -----
        This transformation is primarily used by the `~matplotlib.axis.Axis`
        class, and is meant to be overridden by new kinds of projections that
        may need to place axis elements in different locations.
        """
        labels_align = mpl.rcParams["ytick.alignment"]
        return (self.get_yaxis_transform(which='tick2') +
                mtransforms.ScaledTranslation(
                    pad_points / 72, 0,
                    self.get_figure(root=False).dpi_scale_trans),
                labels_align, "left")

    def _update_transScale(self):
        self.transScale.set(
            mtransforms.blended_transform_factory(
                self.xaxis.get_transform(), self.yaxis.get_transform()))

    def get_position(self, original=False):
        """
        Return the position of the Axes within the figure as a `.Bbox`.

        Parameters
        ----------
        original : bool
            If ``True``, return the original position. Otherwise, return the
            active position. For an explanation of the positions see
            `.set_position`.

        Returns
        -------
        `.Bbox`

        """
        if original:
            return self._originalPosition.frozen()
        else:
            locator = self.get_axes_locator()
            if not locator:
                self.apply_aspect()
            return self._position.frozen()

    def set_position(self, pos, which='both'):
        """
        Set the Axes position.

        Axes have two position attributes. The 'original' position is the
        position allocated for the Axes. The 'active' position is the
        position the Axes is actually drawn at. These positions are usually
        the same unless a fixed aspect is set to the Axes. See
        `.Axes.set_aspect` for details.

        Parameters
        ----------
        pos : [left, bottom, width, height] or `~matplotlib.transforms.Bbox`
            The new position of the Axes in `.Figure` coordinates.

        which : {'both', 'active', 'original'}, default: 'both'
            Determines which position variables to change.

        See Also
        --------
        matplotlib.transforms.Bbox.from_bounds
        matplotlib.transforms.Bbox.from_extents
        """
        self._set_position(pos, which=which)
        # because this is being called externally to the library we
        # don't let it be in the layout.
        self.set_in_layout(False)

    def _set_position(self, pos, which='both'):
        """
        Private version of set_position.

        Call this internally to get the same functionality of `set_position`,
        but not to take the axis out of the constrained_layout hierarchy.
        """
        if not isinstance(pos, mtransforms.BboxBase):
            pos = mtransforms.Bbox.from_bounds(*pos)
        for ax in self._twinned_axes.get_siblings(self):
            if which in ('both', 'active'):
                ax._position.set(pos)
            if which in ('both', 'original'):
                ax._originalPosition.set(pos)
        self.stale = True

    def reset_position(self):
        """
        Reset the active position to the original position.

        This undoes changes to the active position (as defined in
        `.set_position`) which may have been performed to satisfy fixed-aspect
        constraints.
        """
        for ax in self._twinned_axes.get_siblings(self):
            pos = ax.get_position(original=True)
            ax.set_position(pos, which='active')

    def set_axes_locator(self, locator):
        """
        Set the Axes locator.

        Parameters
        ----------
        locator : Callable[[Axes, Renderer], Bbox]
        """
        self._axes_locator = locator
        self.stale = True

    def get_axes_locator(self):
        """
        Return the axes_locator.
        """
        return self._axes_locator

    def _set_artist_props(self, a):
        """Set the boilerplate props for artists added to Axes."""
        a.set_figure(self.get_figure(root=False))
        if not a.is_transform_set():
            a.set_transform(self.transData)

        a.axes = self
        if a.get_mouseover():
            self._mouseover_set.add(a)

    def _gen_axes_patch(self):
        """
        Returns
        -------
        Patch
            The patch used to draw the background of the Axes.  It is also used
            as the clipping path for any data elements on the Axes.

            In the standard Axes, this is a rectangle, but in other projections
            it may not be.

        Notes
        -----
        Intended to be overridden by new projection types.
        """
        return mpatches.Rectangle((0.0, 0.0), 1.0, 1.0)

    def _gen_axes_spines(self, locations=None, offset=0.0, units='inches'):
        """
        Returns
        -------
        dict
            Mapping of spine names to `.Line2D` or `.Patch` instances that are
            used to draw Axes spines.

            In the standard Axes, spines are single line segments, but in other
            projections they may not be.

        Notes
        -----
        Intended to be overridden by new projection types.
        """
        return {side: mspines.Spine.linear_spine(self, side)
                for side in ['left', 'right', 'bottom', 'top']}

    def sharex(self, other):
        """
        Share the x-axis with *other*.

        This is equivalent to passing ``sharex=other`` when constructing the
        Axes, and cannot be used if the x-axis is already being shared with
        another Axes.  Note that it is not possible to unshare axes.
        """
        _api.check_isinstance(_AxesBase, other=other)
        if self._sharex is not None and other is not self._sharex:
            raise ValueError("x-axis is already shared")
        self._shared_axes["x"].join(self, other)
        self._sharex = other
        self.xaxis.major = other.xaxis.major  # Ticker instances holding
        self.xaxis.minor = other.xaxis.minor  # locator and formatter.
        x0, x1 = other.get_xlim()
        self.set_xlim(x0, x1, emit=False, auto=other.get_autoscalex_on())
        self.xaxis._scale = other.xaxis._scale

    def sharey(self, other):
        """
        Share the y-axis with *other*.

        This is equivalent to passing ``sharey=other`` when constructing the
        Axes, and cannot be used if the y-axis is already being shared with
        another Axes.  Note that it is not possible to unshare axes.
        """
        _api.check_isinstance(_AxesBase, other=other)
        if self._sharey is not None and other is not self._sharey:
            raise ValueError("y-axis is already shared")
        self._shared_axes["y"].join(self, other)
        self._sharey = other
        self.yaxis.major = other.yaxis.major  # Ticker instances holding
        self.yaxis.minor = other.yaxis.minor  # locator and formatter.
        y0, y1 = other.get_ylim()
        self.set_ylim(y0, y1, emit=False, auto=other.get_autoscaley_on())
        self.yaxis._scale = other.yaxis._scale

    def __clear(self):
        """Clear the Axes."""
        # The actual implementation of clear() as long as clear() has to be
        # an adapter delegating to the correct implementation.
        # The implementation can move back into clear() when the
        # deprecation on cla() subclassing expires.

        # stash the current visibility state
        if hasattr(self, 'patch'):
            patch_visible = self.patch.get_visible()
        else:
            patch_visible = True

        xaxis_visible = self.xaxis.get_visible()
        yaxis_visible = self.yaxis.get_visible()

        for axis in self._axis_map.values():
            axis.clear()  # Also resets the scale to linear.
        for spine in self.spines.values():
            spine._clear()  # Use _clear to not clear Axis again

        self.ignore_existing_data_limits = True
        self.callbacks = cbook.CallbackRegistry(
            signals=["xlim_changed", "ylim_changed", "zlim_changed"])

        # update the minor locator for x and y axis based on rcParams
        if mpl.rcParams['xtick.minor.visible']:
            self.xaxis.set_minor_locator(mticker.AutoMinorLocator())
        if mpl.rcParams['ytick.minor.visible']:
            self.yaxis.set_minor_locator(mticker.AutoMinorLocator())

        self._xmargin = mpl.rcParams['axes.xmargin']
        self._ymargin = mpl.rcParams['axes.ymargin']
        self._tight = None
        self._use_sticky_edges = True

        self._get_lines = _process_plot_var_args()
        self._get_patches_for_fill = _process_plot_var_args('Polygon')

        self._gridOn = mpl.rcParams['axes.grid']
        # Swap children to minimize time we spend in an invalid state
        old_children, self._children = self._children, []
        for chld in old_children:
            chld._remove_method = None
            chld._parent_figure = None
            chld.axes = None
        # Use list.clear to break the `artist._remove_method` reference cycle
        old_children.clear()
        self._mouseover_set = _OrderedSet()
        self.child_axes = []
        self._current_image = None  # strictly for pyplot via _sci, _gci
        self._projection_init = None  # strictly for pyplot.subplot
        self.legend_ = None
        self.containers = []

        self.grid(False)  # Disable grid on init to use rcParameter
        self.grid(self._gridOn, which=mpl.rcParams['axes.grid.which'],
                  axis=mpl.rcParams['axes.grid.axis'])
        props = font_manager.FontProperties(
            size=mpl.rcParams['axes.titlesize'],
            weight=mpl.rcParams['axes.titleweight'])

        y = mpl.rcParams['axes.titley']
        if y is None:
            y = 1.0
            self._autotitlepos = True
        else:
            self._autotitlepos = False

        self.title = mtext.Text(
            x=0.5, y=y, text='',
            fontproperties=props,
            verticalalignment='baseline',
            horizontalalignment='center',
            )
        self._left_title = mtext.Text(
            x=0.0, y=y, text='',
            fontproperties=props.copy(),
            verticalalignment='baseline',
            horizontalalignment='left', )
        self._right_title = mtext.Text(
            x=1.0, y=y, text='',
            fontproperties=props.copy(),
            verticalalignment='baseline',
            horizontalalignment='right',
            )
        title_offset_points = mpl.rcParams['axes.titlepad']
        # refactor this out so it can be called in ax.set_title if
        # pad argument used...
        self._set_title_offset_trans(title_offset_points)

        for _title in (self.title, self._left_title, self._right_title):
            self._set_artist_props(_title)

        # The patch draws the background of the Axes.  We want this to be below
        # the other artists.  We use the frame to draw the edges so we are
        # setting the edgecolor to None.
        self.patch = self._gen_axes_patch()
        self.patch.set_figure(self.get_figure(root=False))
        self.patch.set_facecolor(self._facecolor)
        self.patch.set_edgecolor('none')
        self.patch.set_linewidth(0)
        self.patch.set_transform(self.transAxes)

        self.set_axis_on()

        self.xaxis.set_clip_path(self.patch)
        self.yaxis.set_clip_path(self.patch)

        if self._sharex is not None:
            self.xaxis.set_visible(xaxis_visible)
            self.patch.set_visible(patch_visible)
        if self._sharey is not None:
            self.yaxis.set_visible(yaxis_visible)
            self.patch.set_visible(patch_visible)

        # This comes last, as the call to _set_lim may trigger an autoscale (in
        # case of shared axes), requiring children to be already set up.
        for name, axis in self._axis_map.items():
            share = getattr(self, f"_share{name}")
            if share is not None:
                getattr(self, f"share{name}")(share)
            else:
                # Although the scale was set to linear as part of clear,
                # polar requires that _set_scale is called again
                if self.name == "polar":
                    axis._set_scale("linear")
                axis._set_lim(0, 1, auto=True)
        self._update_transScale()

        self.stale = True

    def clear(self):
        """Clear the Axes."""
        # Act as an alias, or as the superclass implementation depending on the
        # subclass implementation.
        if self._subclass_uses_cla:
            self.cla()
        else:
            self.__clear()

    def cla(self):
        """Clear the Axes."""
        # Act as an alias, or as the superclass implementation depending on the
        # subclass implementation.
        if self._subclass_uses_cla:
            self.__clear()
        else:
            self.clear()

    class ArtistList(Sequence):
        """
        A sublist of Axes children based on their type.

        The type-specific children sublists were made immutable in Matplotlib
        3.7.  In the future these artist lists may be replaced by tuples. Use
        as if this is a tuple already.
        """
        def __init__(self, axes, prop_name,
                     valid_types=None, invalid_types=None):
            """
            Parameters
            ----------
            axes : `~matplotlib.axes.Axes`
                The Axes from which this sublist will pull the children
                Artists.
            prop_name : str
                The property name used to access this sublist from the Axes;
                used to generate deprecation warnings.
            valid_types : list of type, optional
                A list of types that determine which children will be returned
                by this sublist. If specified, then the Artists in the sublist
                must be instances of any of these types. If unspecified, then
                any type of Artist is valid (unless limited by
                *invalid_types*.)
            invalid_types : tuple, optional
                A list of types that determine which children will *not* be
                returned by this sublist. If specified, then Artists in the
                sublist will never be an instance of these types. Otherwise, no
                types will be excluded.
            """
            self._axes = axes
            self._prop_name = prop_name
            self._type_check = lambda artist: (
                (not valid_types or isinstance(artist, valid_types)) and
                (not invalid_types or not isinstance(artist, invalid_types))
            )

        def __repr__(self):
            return f'<Axes.ArtistList of {len(self)} {self._prop_name}>'

        def __len__(self):
            return sum(self._type_check(artist)
                       for artist in self._axes._children)

        def __iter__(self):
            for artist in list(self._axes._children):
                if self._type_check(artist):
                    yield artist

        def __getitem__(self, key):
            return [artist
                    for artist in self._axes._children
                    if self._type_check(artist)][key]

        def __add__(self, other):
            if isinstance(other, (list, _AxesBase.ArtistList)):
                return [*self, *other]
            if isinstance(other, (tuple, _AxesBase.ArtistList)):
                return (*self, *other)
            return NotImplemented

        def __radd__(self, other):
            if isinstance(other, list):
                return other + list(self)
            if isinstance(other, tuple):
                return other + tuple(self)
            return NotImplemented

    @property
    def artists(self):
        return self.ArtistList(self, 'artists', invalid_types=(
            mcoll.Collection, mimage.AxesImage, mlines.Line2D, mpatches.Patch,
            mtable.Table, mtext.Text))

    @property
    def collections(self):
        return self.ArtistList(self, 'collections',
                               valid_types=mcoll.Collection)

    @property
    def images(self):
        return self.ArtistList(self, 'images', valid_types=mimage.AxesImage)

    @property
    def lines(self):
        return self.ArtistList(self, 'lines', valid_types=mlines.Line2D)

    @property
    def patches(self):
        return self.ArtistList(self, 'patches', valid_types=mpatches.Patch)

    @property
    def tables(self):
        return self.ArtistList(self, 'tables', valid_types=mtable.Table)

    @property
    def texts(self):
        return self.ArtistList(self, 'texts', valid_types=mtext.Text)

    def get_facecolor(self):
        """Get the facecolor of the Axes."""
        return self.patch.get_facecolor()

    def set_facecolor(self, color):
        """
        Set the facecolor of the Axes.

        Parameters
        ----------
        color : :mpltype:`color`
        """
        self._facecolor = color
        self.stale = True
        return self.patch.set_facecolor(color)

    def _set_title_offset_trans(self, title_offset_points):
        """
        Set the offset for the title either from :rc:`axes.titlepad`
        or from set_title kwarg ``pad``.
        """
        self.titleOffsetTrans = mtransforms.ScaledTranslation(
                0.0, title_offset_points / 72,
                self.get_figure(root=False).dpi_scale_trans)
        for _title in (self.title, self._left_title, self._right_title):
            _title.set_transform(self.transAxes + self.titleOffsetTrans)
            _title.set_clip_box(None)

    def set_prop_cycle(self, *args, **kwargs):
        """
        Set the property cycle of the Axes.

        The property cycle controls the style properties such as color,
        marker and linestyle of future plot commands. The style properties
        of data already added to the Axes are not modified.

        Call signatures::

          set_prop_cycle(cycler)
          set_prop_cycle(label=values, label2=values2, ...)
          set_prop_cycle(label, values)

        Form 1 sets given `~cycler.Cycler` object.

        Form 2 creates a `~cycler.Cycler` which cycles over one or more
        properties simultaneously and set it as the property cycle of the
        Axes. If multiple properties are given, their value lists must have
        the same length. This is just a shortcut for explicitly creating a
        cycler and passing it to the function, i.e. it's short for
        ``set_prop_cycle(cycler(label=values, label2=values2, ...))``.

        Form 3 creates a `~cycler.Cycler` for a single property and set it
        as the property cycle of the Axes. This form exists for compatibility
        with the original `cycler.cycler` interface. Its use is discouraged
        in favor of the kwarg form, i.e. ``set_prop_cycle(label=values)``.

        Parameters
        ----------
        cycler : `~cycler.Cycler` or ``None``
            Set the given Cycler. *None* resets to the cycle defined by the
            current style.

            .. ACCEPTS: `~cycler.Cycler`

        label : str
            The property key. Must be a valid `.Artist` property.
            For example, 'color' or 'linestyle'. Aliases are allowed,
            such as 'c' for 'color' and 'lw' for 'linewidth'.

        values : iterable
            Finite-length iterable of the property values. These values
            are validated and will raise a ValueError if invalid.

        See Also
        --------
        matplotlib.rcsetup.cycler
            Convenience function for creating validated cyclers for properties.
        cycler.cycler
            The original function for creating unvalidated cyclers.

        Examples
        --------
        Setting the property cycle for a single property:

        >>> ax.set_prop_cycle(color=['red', 'green', 'blue'])

        Setting the property cycle for simultaneously cycling over multiple
        properties (e.g. red circle, green plus, blue cross):

        >>> ax.set_prop_cycle(color=['red', 'green', 'blue'],
        ...                   marker=['o', '+', 'x'])

        """
        if args and kwargs:
            raise TypeError("Cannot supply both positional and keyword "
                            "arguments to this method.")
        # Can't do `args == (None,)` as that crashes cycler.
        if len(args) == 1 and args[0] is None:
            prop_cycle = None
        else:
            prop_cycle = cycler(*args, **kwargs)
        self._get_lines.set_prop_cycle(prop_cycle)
        self._get_patches_for_fill.set_prop_cycle(prop_cycle)

    def get_aspect(self):
        """
        Return the aspect ratio of the Axes scaling.

        This is either "auto" or a float giving the ratio of y/x-scale.
        """
        return self._aspect

    def set_aspect(self, aspect, adjustable=None, anchor=None, share=False):
        """
        Set the aspect ratio of the Axes scaling, i.e. y/x-scale.

        Parameters
        ----------
        aspect : {'auto', 'equal'} or float
            Possible values:

            - 'auto': fill the position rectangle with data.
            - 'equal': same as ``aspect=1``, i.e. same scaling for x and y.
            - *float*: The displayed size of 1 unit in y-data coordinates will
              be *aspect* times the displayed size of 1 unit in x-data
              coordinates; e.g. for ``aspect=2`` a square in data coordinates
              will be rendered with a height of twice its width.

        adjustable : None or {'box', 'datalim'}, optional
            If not ``None``, this defines which parameter will be adjusted to
            meet the required aspect. See `.set_adjustable` for further
            details.

        anchor : None or str or (float, float), optional
            If not ``None``, this defines where the Axes will be drawn if there
            is extra space due to aspect constraints. The most common way
            to specify the anchor are abbreviations of cardinal directions:

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
        matplotlib.axes.Axes.set_adjustable
            Set how the Axes adjusts to achieve the required aspect ratio.
        matplotlib.axes.Axes.set_anchor
            Set the position in case of extra space.
        """
        if cbook._str_equal(aspect, 'equal'):
            aspect = 1
        if not cbook._str_equal(aspect, 'auto'):
            aspect = float(aspect)  # raise ValueError if necessary
            if aspect <= 0 or not np.isfinite(aspect):
                raise ValueError("aspect must be finite and positive ")

        if share:
            axes = {sibling for name in self._axis_names
                    for sibling in self._shared_axes[name].get_siblings(self)}
        else:
            axes = [self]

        for ax in axes:
            ax._aspect = aspect

        if adjustable is None:
            adjustable = self._adjustable
        self.set_adjustable(adjustable, share=share)  # Handle sharing.

        if anchor is not None:
            self.set_anchor(anchor, share=share)
        self.stale = True

    def get_adjustable(self):
        """
        Return whether the Axes will adjust its physical dimension ('box') or
        its data limits ('datalim') to achieve the desired aspect ratio.

        See Also
        --------
        matplotlib.axes.Axes.set_adjustable
            Set how the Axes adjusts to achieve the required aspect ratio.
        matplotlib.axes.Axes.set_aspect
            For a description of aspect handling.
        """
        return self._adjustable

    def set_adjustable(self, adjustable, share=False):
        """
        Set how the Axes adjusts to achieve the required aspect ratio.

        Parameters
        ----------
        adjustable : {'box', 'datalim'}
            If 'box', change the physical dimensions of the Axes.
            If 'datalim', change the ``x`` or ``y`` data limits. This
            may ignore explicitly defined axis limits.

        share : bool, default: False
            If ``True``, apply the settings to all shared Axes.

        See Also
        --------
        matplotlib.axes.Axes.set_aspect
            For a description of aspect handling.

        Notes
        -----
        Shared Axes (of which twinned Axes are a special case)
        impose restrictions on how aspect ratios can be imposed.
        For twinned Axes, use 'datalim'.  For Axes that share both
        x and y, use 'box'.  Otherwise, either 'datalim' or 'box'
        may be used.  These limitations are partly a requirement
        to avoid over-specification, and partly a result of the
        particular implementation we are currently using, in
        which the adjustments for aspect ratios are done sequentially
        and independently on each Axes as it is drawn.
        """
        _api.check_in_list(["box", "datalim"], adjustable=adjustable)
        if share:
            axs = {sibling for name in self._axis_names
                   for sibling in self._shared_axes[name].get_siblings(self)}
        else:
            axs = [self]
        if (adjustable == "datalim"
                and any(getattr(ax.get_data_ratio, "__func__", None)
                        != _AxesBase.get_data_ratio
                        for ax in axs)):
            # Limits adjustment by apply_aspect assumes that the axes' aspect
            # ratio can be computed from the data limits and scales.
            raise ValueError("Cannot set Axes adjustable to 'datalim' for "
                             "Axes which override 'get_data_ratio'")
        for ax in axs:
            ax._adjustable = adjustable
        self.stale = True

    def get_box_aspect(self):
        """
        Return the Axes box aspect, i.e. the ratio of height to width.

        The box aspect is ``None`` (i.e. chosen depending on the available
        figure space) unless explicitly specified.

        See Also
        --------
        matplotlib.axes.Axes.set_box_aspect
            for a description of box aspect.
        matplotlib.axes.Axes.set_aspect
            for a description of aspect handling.
        """
        return self._box_aspect

    def set_box_aspect(self, aspect=None):
        """
        Set the Axes box aspect, i.e. the ratio of height to width.

        This defines the aspect of the Axes in figure space and is not to be
        confused with the data aspect (see `~.Axes.set_aspect`).

        Parameters
        ----------
        aspect : float or None
            Changes the physical dimensions of the Axes, such that the ratio
            of the Axes height to the Axes width in physical units is equal to
            *aspect*. Defining a box aspect will change the *adjustable*
            property to 'datalim' (see `~.Axes.set_adjustable`).

            *None* will disable a fixed box aspect so that height and width
            of the Axes are chosen independently.

        See Also
        --------
        matplotlib.axes.Axes.set_aspect
            for a description of aspect handling.
        """
        axs = {*self._twinned_axes.get_siblings(self),
               *self._twinned_axes.get_siblings(self)}

        if aspect is not None:
            aspect = float(aspect)
            # when box_aspect is set to other than ´None`,
            # adjustable must be "datalim"
            for ax in axs:
                ax.set_adjustable("datalim")

        for ax in axs:
            ax._box_aspect = aspect
            ax.stale = True

    def get_anchor(self):
        """
        Get the anchor location.

        See Also
        --------
        matplotlib.axes.Axes.set_anchor
            for a description of the anchor.
        matplotlib.axes.Axes.set_aspect
            for a description of aspect handling.
        """
        return self._anchor

    def set_anchor(self, anchor, share=False):
        """
        Define the anchor location.

        The actual drawing area (active position) of the Axes may be smaller
        than the Bbox (original position) when a fixed aspect is required. The
        anchor defines where the drawing area will be located within the
        available space.

        Parameters
        ----------
        anchor : (float, float) or {'C', 'SW', 'S', 'SE', 'E', 'NE', ...}
            Either an (*x*, *y*) pair of relative coordinates (0 is left or
            bottom, 1 is right or top), 'C' (center), or a cardinal direction
            ('SW', southwest, is bottom left, etc.).  str inputs are shorthands
            for (*x*, *y*) coordinates, as shown in the following diagram::

               ┌─────────────────┬─────────────────┬─────────────────┐
               │ 'NW' (0.0, 1.0) │ 'N' (0.5, 1.0)  │ 'NE' (1.0, 1.0) │
               ├─────────────────┼─────────────────┼─────────────────┤
               │ 'W'  (0.0, 0.5) │ 'C' (0.5, 0.5)  │ 'E'  (1.0, 0.5) │
               ├─────────────────┼─────────────────┼─────────────────┤
               │ 'SW' (0.0, 0.0) │ 'S' (0.5, 0.0)  │ 'SE' (1.0, 0.0) │
               └─────────────────┴─────────────────┴─────────────────┘

        share : bool, default: False
            If ``True``, apply the settings to all shared Axes.

        See Also
        --------
        matplotlib.axes.Axes.set_aspect
            for a description of aspect handling.
        """
        if not (anchor in mtransforms.Bbox.coefs or len(anchor) == 2):
            raise ValueError('argument must be among %s' %
                             ', '.join(mtransforms.Bbox.coefs))
        if share:
            axes = {sibling for name in self._axis_names
                    for sibling in self._shared_axes[name].get_siblings(self)}
        else:
            axes = [self]
        for ax in axes:
            ax._anchor = anchor

        self.stale = True

    def get_data_ratio(self):
        """
        Return the aspect ratio of the scaled data.

        Notes
        -----
        This method is intended to be overridden by new projection types.
        """
        txmin, txmax = self.xaxis.get_transform().transform(self.get_xbound())
        tymin, tymax = self.yaxis.get_transform().transform(self.get_ybound())
        xsize = max(abs(txmax - txmin), 1e-30)
        ysize = max(abs(tymax - tymin), 1e-30)
        return ysize / xsize

    def apply_aspect(self, position=None):
        """
        Adjust the Axes for a specified data aspect ratio.

        Depending on `.get_adjustable` this will modify either the
        Axes box (position) or the view limits. In the former case,
        `~matplotlib.axes.Axes.get_anchor` will affect the position.

        Parameters
        ----------
        position : None or .Bbox

            .. note::
                This parameter exists for historic reasons and is considered
                internal. End users should not use it.

            If not ``None``, this defines the position of the
            Axes within the figure as a Bbox. See `~.Axes.get_position`
            for further details.

        Notes
        -----
        This is called automatically when each Axes is drawn.  You may need
        to call it yourself if you need to update the Axes position and/or
        view limits before the Figure is drawn.

        An alternative with a broader scope is `.Figure.draw_without_rendering`,
        which updates all stale components of a figure, not only the positioning /
        view limits of a single Axes.

        See Also
        --------
        matplotlib.axes.Axes.set_aspect
            For a description of aspect ratio handling.
        matplotlib.axes.Axes.set_adjustable
            Set how the Axes adjusts to achieve the required aspect ratio.
        matplotlib.axes.Axes.set_anchor
            Set the position in case of extra space.
        matplotlib.figure.Figure.draw_without_rendering
            Update all stale components of a figure.

        Examples
        --------
        A typical usage example would be the following. `~.Axes.imshow` sets the
        aspect to 1, but adapting the Axes position and extent to reflect this is
        deferred until rendering for performance reasons. If you want to know the
        Axes size before, you need to call `.apply_aspect` to get the correct
        values.

        >>> fig, ax = plt.subplots()
        >>> ax.imshow(np.zeros((3, 3)))
        >>> ax.bbox.width, ax.bbox.height
        (496.0, 369.59999999999997)
        >>> ax.apply_aspect()
        >>> ax.bbox.width, ax.bbox.height
        (369.59999999999997, 369.59999999999997)
        """
        if position is None:
            position = self.get_position(original=True)

        aspect = self.get_aspect()

        if aspect == 'auto' and self._box_aspect is None:
            self._set_position(position, which='active')
            return

        trans = self.get_figure(root=False).transSubfigure
        bb = mtransforms.Bbox.unit().transformed(trans)
        # this is the physical aspect of the panel (or figure):
        fig_aspect = bb.height / bb.width

        if self._adjustable == 'box':
            if self in self._twinned_axes:
                raise RuntimeError("Adjustable 'box' is not allowed in a "
                                   "twinned Axes; use 'datalim' instead")
            box_aspect = aspect * self.get_data_ratio()
            pb = position.frozen()
            pb1 = pb.shrunk_to_aspect(box_aspect, pb, fig_aspect)
            self._set_position(pb1.anchored(self.get_anchor(), pb), 'active')
            return

        # The following is only seen if self._adjustable == 'datalim'
        if self._box_aspect is not None:
            pb = position.frozen()
            pb1 = pb.shrunk_to_aspect(self._box_aspect, pb, fig_aspect)
            self._set_position(pb1.anchored(self.get_anchor(), pb), 'active')
            if aspect == "auto":
                return

        # reset active to original in case it had been changed by prior use
        # of 'box'
        if self._box_aspect is None:
            self._set_position(position, which='active')
        else:
            position = pb1.anchored(self.get_anchor(), pb)

        x_trf = self.xaxis.get_transform()
        y_trf = self.yaxis.get_transform()
        xmin, xmax = x_trf.transform(self.get_xbound())
        ymin, ymax = y_trf.transform(self.get_ybound())
        xsize = max(abs(xmax - xmin), 1e-30)
        ysize = max(abs(ymax - ymin), 1e-30)

        box_aspect = fig_aspect * (position.height / position.width)
        data_ratio = box_aspect / aspect

        y_expander = data_ratio * xsize / ysize - 1
        # If y_expander > 0, the dy/dx viewLim ratio needs to increase
        if abs(y_expander) < 0.005:
            return

        dL = self.dataLim
        x0, x1 = x_trf.transform(dL.intervalx)
        y0, y1 = y_trf.transform(dL.intervaly)
        xr = 1.05 * (x1 - x0)
        yr = 1.05 * (y1 - y0)

        xmarg = xsize - xr
        ymarg = ysize - yr
        Ysize = data_ratio * xsize
        Xsize = ysize / data_ratio
        Xmarg = Xsize - xr
        Ymarg = Ysize - yr
        # Setting these targets to, e.g., 0.05*xr does not seem to help.
        xm = 0
        ym = 0

        shared_x = self in self._shared_axes["x"]
        shared_y = self in self._shared_axes["y"]

        if shared_x and shared_y:
            raise RuntimeError("set_aspect(..., adjustable='datalim') or "
                               "axis('equal') are not allowed when both axes "
                               "are shared.  Try set_aspect(..., "
                               "adjustable='box').")

        # If y is shared, then we are only allowed to change x, etc.
        if shared_y:
            adjust_y = False
        else:
            if xmarg > xm and ymarg > ym:
                adjy = ((Ymarg > 0 and y_expander < 0) or
                        (Xmarg < 0 and y_expander > 0))
            else:
                adjy = y_expander > 0
            adjust_y = shared_x or adjy  # (Ymarg > xmarg)

        if adjust_y:
            yc = 0.5 * (ymin + ymax)
            y0 = yc - Ysize / 2.0
            y1 = yc + Ysize / 2.0
            if not self.get_autoscaley_on():
                _log.warning("Ignoring fixed y limits to fulfill fixed data aspect "
                             "with adjustable data limits.")
            self.set_ybound(y_trf.inverted().transform([y0, y1]))
        else:
            xc = 0.5 * (xmin + xmax)
            x0 = xc - Xsize / 2.0
            x1 = xc + Xsize / 2.0
            if not self.get_autoscalex_on():
                _log.warning("Ignoring fixed x limits to fulfill fixed data aspect "
                             "with adjustable data limits.")
            self.set_xbound(x_trf.inverted().transform([x0, x1]))

    def axis(self, arg=None, /, *, emit=True, **kwargs):
        """
        Convenience method to get or set some axis properties.

        Call signatures::

          xmin, xmax, ymin, ymax = axis()
          xmin, xmax, ymin, ymax = axis([xmin, xmax, ymin, ymax])
          xmin, xmax, ymin, ymax = axis(option)
          xmin, xmax, ymin, ymax = axis(**kwargs)

        Parameters
        ----------
        xmin, xmax, ymin, ymax : float, optional
            The axis limits to be set.  This can also be achieved using ::

                ax.set(xlim=(xmin, xmax), ylim=(ymin, ymax))

        option : bool or str
            If a bool, turns axis lines and labels on or off. If a string,
            possible values are:

            ================ ===========================================================
            Value            Description
            ================ ===========================================================
            'off' or `False` Hide all axis decorations, i.e. axis labels, spines,
                             tick marks, tick labels, and grid lines.
                             This is the same as `~.Axes.set_axis_off()`.
            'on' or `True`   Do not hide all axis decorations, i.e. axis labels, spines,
                             tick marks, tick labels, and grid lines.
                             This is the same as `~.Axes.set_axis_on()`.
            'equal'          Set equal scaling (i.e., make circles circular) by
                             changing the axis limits. This is the same as
                             ``ax.set_aspect('equal', adjustable='datalim')``.
                             Explicit data limits may not be respected in this case.
            'scaled'         Set equal scaling (i.e., make circles circular) by
                             changing dimensions of the plot box. This is the same as
                             ``ax.set_aspect('equal', adjustable='box', anchor='C')``.
                             Additionally, further autoscaling will be disabled.
            'tight'          Set limits just large enough to show all data, then
                             disable further autoscaling.
            'auto'           Automatic scaling (fill plot box with data).
            'image'          'scaled' with axis limits equal to data limits.
            'square'         Square plot; similar to 'scaled', but initially forcing
                             ``xmax-xmin == ymax-ymin``.
            ================ ===========================================================

        emit : bool, default: True
            Whether observers are notified of the axis limit change.
            This option is passed on to `~.Axes.set_xlim` and
            `~.Axes.set_ylim`.

        Returns
        -------
        xmin, xmax, ymin, ymax : float
            The axis limits.

        See Also
        --------
        matplotlib.axes.Axes.set_xlim
        matplotlib.axes.Axes.set_ylim

        Notes
        -----
        For 3D Axes, this method additionally takes *zmin*, *zmax* as
        parameters and likewise returns them.
        """
        if isinstance(arg, (str, bool)):
            if arg is True:
                arg = 'on'
            if arg is False:
                arg = 'off'
            arg = arg.lower()
            if arg == 'on':
                self.set_axis_on()
            elif arg == 'off':
                self.set_axis_off()
            elif arg in [
                    'equal', 'tight', 'scaled', 'auto', 'image', 'square']:
                self.set_autoscale_on(True)
                self.set_aspect('auto')
                self.autoscale_view(tight=False)
                if arg == 'equal':
                    self.set_aspect('equal', adjustable='datalim')
                elif arg == 'scaled':
                    self.set_aspect('equal', adjustable='box', anchor='C')
                    self.set_autoscale_on(False)  # Req. by Mark Bakker
                elif arg == 'tight':
                    self.autoscale_view(tight=True)
                    self.set_autoscale_on(False)
                elif arg == 'image':
                    self.autoscale_view(tight=True)
                    self.set_autoscale_on(False)
                    self.set_aspect('equal', adjustable='box', anchor='C')
                elif arg == 'square':
                    self.set_aspect('equal', adjustable='box', anchor='C')
                    self.set_autoscale_on(False)
                    xlim = self.get_xlim()
                    ylim = self.get_ylim()
                    edge_size = max(np.diff(xlim), np.diff(ylim))[0]
                    self.set_xlim([xlim[0], xlim[0] + edge_size],
                                  emit=emit, auto=False)
                    self.set_ylim([ylim[0], ylim[0] + edge_size],
                                  emit=emit, auto=False)
            else:
                raise ValueError(f"Unrecognized string {arg!r} to axis; "
                                 "try 'on' or 'off'")
        else:
            if arg is not None:
                if len(arg) != 2*len(self._axis_names):
                    raise TypeError(
                        "The first argument to axis() must be an iterable of the form "
                        "[{}]".format(", ".join(
                            f"{name}min, {name}max" for name in self._axis_names)))
                limits = {
                    name: arg[2*i:2*(i+1)]
                    for i, name in enumerate(self._axis_names)
                }
            else:
                limits = {}
                for name in self._axis_names:
                    ax_min = kwargs.pop(f'{name}min', None)
                    ax_max = kwargs.pop(f'{name}max', None)
                    limits[name] = (ax_min, ax_max)
            for name, (ax_min, ax_max) in limits.items():
                ax_auto = (None  # Keep autoscale state as is.
                           if ax_min is None and ax_max is None
                           else False)  # Turn off autoscale.
                set_ax_lim = getattr(self, f'set_{name}lim')
                set_ax_lim(ax_min, ax_max, emit=emit, auto=ax_auto)
        if kwargs:
            raise _api.kwarg_error("axis", kwargs)
        lims = ()
        for name in self._axis_names:
            get_ax_lim = getattr(self, f'get_{name}lim')
            lims += get_ax_lim()
        return lims

    def get_legend(self):
        """Return the `.Legend` instance, or None if no legend is defined."""
        return self.legend_

    def get_images(self):
        r"""Return a list of `.AxesImage`\s contained by the Axes."""
        return cbook.silent_list('AxesImage', self.images)

    def get_lines(self):
        """Return a list of lines contained by the Axes."""
        return cbook.silent_list('Line2D', self.lines)

    def get_xaxis(self):
        """
        [*Discouraged*] Return the XAxis instance.

        .. admonition:: Discouraged

            The use of this function is discouraged. You should instead
            directly access the attribute `~.Axes.xaxis`.
        """
        return self.xaxis

    def get_yaxis(self):
        """
        [*Discouraged*] Return the YAxis instance.

        .. admonition:: Discouraged

            The use of this function is discouraged. You should instead
            directly access the attribute `~.Axes.yaxis`.
        """
        return self.yaxis

    get_xgridlines = _axis_method_wrapper("xaxis", "get_gridlines")
    get_xticklines = _axis_method_wrapper("xaxis", "get_ticklines")
    get_ygridlines = _axis_method_wrapper("yaxis", "get_gridlines")
    get_yticklines = _axis_method_wrapper("yaxis", "get_ticklines")

    # Adding and tracking artists

    def _sci(self, im):
        """
        Set the current image.

        This image will be the target of colormap functions like
        ``pyplot.viridis``, and other functions such as `~.pyplot.clim`.  The
        current image is an attribute of the current Axes.
        """
        _api.check_isinstance((mcoll.Collection, mimage.AxesImage), im=im)
        if im not in self._children:
            raise ValueError("Argument must be an image or collection in this Axes")
        self._current_image = im

    def _gci(self):
        """Helper for `~matplotlib.pyplot.gci`; do not use elsewhere."""
        return self._current_image

    def has_data(self):
        """
        Return whether any artists have been added to the Axes.

        This should not be used to determine whether the *dataLim*
        need to be updated, and may not actually be useful for
        anything.
        """
        return any(isinstance(a, (mcoll.Collection, mimage.AxesImage,
                                  mlines.Line2D, mpatches.Patch))
                   for a in self._children)

    def add_artist(self, a):
        """
        Add an `.Artist` to the Axes; return the artist.

        Use `add_artist` only for artists for which there is no dedicated
        "add" method; and if necessary, use a method such as `update_datalim`
        to manually update the `~.Axes.dataLim` if the artist is to be included
        in autoscaling.

        If no ``transform`` has been specified when creating the artist (e.g.
        ``artist.get_transform() == None``) then the transform is set to
        ``ax.transData``.
        """
        a.axes = self
        self._children.append(a)
        a._remove_method = self._children.remove
        self._set_artist_props(a)
        if a.get_clip_path() is None:
            a.set_clip_path(self.patch)
        self.stale = True
        return a

    def add_child_axes(self, ax):
        """
        Add an `.Axes` to the Axes' children; return the child Axes.

        This is the lowlevel version.  See `.axes.Axes.inset_axes`.
        """

        # normally Axes have themselves as the Axes, but these need to have
        # their parent...
        # Need to bypass the getter...
        ax._axes = self
        ax.stale_callback = martist._stale_axes_callback

        self.child_axes.append(ax)
        ax._remove_method = functools.partial(
            self.get_figure(root=False)._remove_axes, owners=[self.child_axes])
        self.stale = True
        return ax

    def add_collection(self, collection, autolim=True):
        """
        Add a `.Collection` to the Axes; return the collection.
        """
        _api.check_isinstance(mcoll.Collection, collection=collection)
        if not collection.get_label():
            collection.set_label(f'_child{len(self._children)}')
        self._children.append(collection)
        collection._remove_method = self._children.remove
        self._set_artist_props(collection)

        if collection.get_clip_path() is None:
            collection.set_clip_path(self.patch)

        if autolim:
            # Make sure viewLim is not stale (mostly to match
            # pre-lazy-autoscale behavior, which is not really better).
            self._unstale_viewLim()
            datalim = collection.get_datalim(self.transData)
            points = datalim.get_points()
            if not np.isinf(datalim.minpos).all():
                # By definition, if minpos (minimum positive value) is set
                # (i.e., non-inf), then min(points) <= minpos <= max(points),
                # and minpos would be superfluous. However, we add minpos to
                # the call so that self.dataLim will update its own minpos.
                # This ensures that log scales see the correct minimum.
                points = np.concatenate([points, [datalim.minpos]])
            # only update the dataLim for x/y if the collection uses transData
            # in this direction.
            x_is_data, y_is_data = (collection.get_transform()
                                    .contains_branch_seperately(self.transData))
            ox_is_data, oy_is_data = (collection.get_offset_transform()
                                      .contains_branch_seperately(self.transData))
            self.update_datalim(
                points,
                updatex=x_is_data or ox_is_data,
                updatey=y_is_data or oy_is_data,
            )

        self.stale = True
        return collection

    def add_image(self, image):
        """
        Add an `.AxesImage` to the Axes; return the image.
        """
        _api.check_isinstance(mimage.AxesImage, image=image)
        self._set_artist_props(image)
        if not image.get_label():
            image.set_label(f'_child{len(self._children)}')
        self._children.append(image)
        image._remove_method = self._children.remove
        self.stale = True
        return image

    def _update_image_limits(self, image):
        xmin, xmax, ymin, ymax = image.get_extent()
        self.axes.update_datalim(((xmin, ymin), (xmax, ymax)))

    def add_line(self, line):
        """
        Add a `.Line2D` to the Axes; return the line.
        """
        _api.check_isinstance(mlines.Line2D, line=line)
        self._set_artist_props(line)
        if line.get_clip_path() is None:
            line.set_clip_path(self.patch)

        self._update_line_limits(line)
        if not line.get_label():
            line.set_label(f'_child{len(self._children)}')
        self._children.append(line)
        line._remove_method = self._children.remove
        self.stale = True
        return line

    def _add_text(self, txt):
        """
        Add a `.Text` to the Axes; return the text.
        """
        _api.check_isinstance(mtext.Text, txt=txt)
        self._set_artist_props(txt)
        self._children.append(txt)
        txt._remove_method = self._children.remove
        self.stale = True
        return txt

    def _update_line_limits(self, line):
        """
        Figures out the data limit of the given line, updating `.Axes.dataLim`.
        """
        path = line.get_path()
        if path.vertices.size == 0:
            return

        line_trf = line.get_transform()

        if line_trf == self.transData:
            data_path = path
        elif any(line_trf.contains_branch_seperately(self.transData)):
            # Compute the transform from line coordinates to data coordinates.
            trf_to_data = line_trf - self.transData
            # If transData is affine we can use the cached non-affine component
            # of line's path (since the non-affine part of line_trf is
            # entirely encapsulated in trf_to_data).
            if self.transData.is_affine:
                line_trans_path = line._get_transformed_path()
                na_path, _ = line_trans_path.get_transformed_path_and_affine()
                data_path = trf_to_data.transform_path_affine(na_path)
            else:
                data_path = trf_to_data.transform_path(path)
        else:
            # For backwards compatibility we update the dataLim with the
            # coordinate range of the given path, even though the coordinate
            # systems are completely different. This may occur in situations
            # such as when ax.transAxes is passed through for absolute
            # positioning.
            data_path = path

        if not data_path.vertices.size:
            return

        updatex, updatey = line_trf.contains_branch_seperately(self.transData)
        if self.name != "rectilinear":
            # This block is mostly intended to handle axvline in polar plots,
            # for which updatey would otherwise be True.
            if updatex and line_trf == self.get_yaxis_transform():
                updatex = False
            if updatey and line_trf == self.get_xaxis_transform():
                updatey = False
        self.dataLim.update_from_path(data_path,
                                      self.ignore_existing_data_limits,
                                      updatex=updatex, updatey=updatey)
        self.ignore_existing_data_limits = False

    def add_patch(self, p):
        """
        Add a `.Patch` to the Axes; return the patch.
        """
        _api.check_isinstance(mpatches.Patch, p=p)
        self._set_artist_props(p)
        if p.get_clip_path() is None:
            p.set_clip_path(self.patch)
        self._update_patch_limits(p)
        self._children.append(p)
        p._remove_method = self._children.remove
        return p

    def _update_patch_limits(self, patch):
        """Update the data limits for the given patch."""
        # hist can add zero height Rectangles, which is useful to keep
        # the bins, counts and patches lined up, but it throws off log
        # scaling.  We'll ignore rects with zero height or width in
        # the auto-scaling

        # cannot check for '==0' since unitized data may not compare to zero
        # issue #2150 - we update the limits if patch has non zero width
        # or height.
        if (isinstance(patch, mpatches.Rectangle) and
                ((not patch.get_width()) and (not patch.get_height()))):
            return
        p = patch.get_path()
        # Get all vertices on the path
        # Loop through each segment to get extrema for Bezier curve sections
        vertices = []
        for curve, code in p.iter_bezier(simplify=False):
            # Get distance along the curve of any extrema
            _, dzeros = curve.axis_aligned_extrema()
            # Calculate vertices of start, end and any extrema in between
            vertices.append(curve([0, *dzeros, 1]))

        if len(vertices):
            vertices = np.vstack(vertices)

        patch_trf = patch.get_transform()
        updatex, updatey = patch_trf.contains_branch_seperately(self.transData)
        if not (updatex or updatey):
            return
        if self.name != "rectilinear":
            # As in _update_line_limits, but for axvspan.
            if updatex and patch_trf == self.get_yaxis_transform():
                updatex = False
            if updatey and patch_trf == self.get_xaxis_transform():
                updatey = False
        trf_to_data = patch_trf - self.transData
        xys = trf_to_data.transform(vertices)
        self.update_datalim(xys, updatex=updatex, updatey=updatey)

    def add_table(self, tab):
        """
        Add a `.Table` to the Axes; return the table.
        """
        _api.check_isinstance(mtable.Table, tab=tab)
        self._set_artist_props(tab)
        self._children.append(tab)
        if tab.get_clip_path() is None:
            tab.set_clip_path(self.patch)
        tab._remove_method = self._children.remove
        return tab

    def add_container(self, container):
        """
        Add a `.Container` to the Axes' containers; return the container.
        """
        label = container.get_label()
        if not label:
            container.set_label('_container%d' % len(self.containers))
        self.containers.append(container)
        container._remove_method = self.containers.remove
        return container

    def _unit_change_handler(self, axis_name, event=None):
        """
        Process axis units changes: requests updates to data and view limits.
        """
        if event is None:  # Allow connecting `self._unit_change_handler(name)`
            return functools.partial(
                self._unit_change_handler, axis_name, event=object())
        _api.check_in_list(self._axis_map, axis_name=axis_name)
        for line in self.lines:
            line.recache_always()
        self.relim()
        self._request_autoscale_view(axis_name)

    def relim(self, visible_only=False):
        """
        Recompute the data limits based on current artists.

        At present, `.Collection` instances are not supported.

        Parameters
        ----------
        visible_only : bool, default: False
            Whether to exclude invisible artists.
        """
        # Collections are deliberately not supported (yet); see
        # the TODO note in artists.py.
        self.dataLim.ignore(True)
        self.dataLim.set_points(mtransforms.Bbox.null().get_points())
        self.ignore_existing_data_limits = True

        for artist in self._children:
            if not visible_only or artist.get_visible():
                if isinstance(artist, mlines.Line2D):
                    self._update_line_limits(artist)
                elif isinstance(artist, mpatches.Patch):
                    self._update_patch_limits(artist)
                elif isinstance(artist, mimage.AxesImage):
                    self._update_image_limits(artist)

    def update_datalim(self, xys, updatex=True, updatey=True):
        """
        Extend the `~.Axes.dataLim` Bbox to include the given points.

        If no data is set currently, the Bbox will ignore its limits and set
        the bound to be the bounds of the xydata (*xys*). Otherwise, it will
        compute the bounds of the union of its current data and the data in
        *xys*.

        Parameters
        ----------
        xys : 2D array-like
            The points to include in the data limits Bbox. This can be either
            a list of (x, y) tuples or a (N, 2) array.

        updatex, updatey : bool, default: True
            Whether to update the x/y limits.
        """
        xys = np.asarray(xys)
        if not np.any(np.isfinite(xys)):
            return
        self.dataLim.update_from_data_xy(xys, self.ignore_existing_data_limits,
                                         updatex=updatex, updatey=updatey)
        self.ignore_existing_data_limits = False

    def _process_unit_info(self, datasets=None, kwargs=None, *, convert=True):
        """
        Set axis units based on *datasets* and *kwargs*, and optionally apply
        unit conversions to *datasets*.

        Parameters
        ----------
        datasets : list
            List of (axis_name, dataset) pairs (where the axis name is defined
            as in `._axis_map`).  Individual datasets can also be None
            (which gets passed through).
        kwargs : dict
            Other parameters from which unit info (i.e., the *xunits*,
            *yunits*, *zunits* (for 3D Axes), *runits* and *thetaunits* (for
            polar) entries) is popped, if present.  Note that this dict is
            mutated in-place!
        convert : bool, default: True
            Whether to return the original datasets or the converted ones.

        Returns
        -------
        list
            Either the original datasets if *convert* is False, or the
            converted ones if *convert* is True (the default).
        """
        # The API makes datasets a list of pairs rather than an axis_name to
        # dataset mapping because it is sometimes necessary to process multiple
        # datasets for a single axis, and concatenating them may be tricky
        # (e.g. if some are scalars, etc.).
        datasets = datasets or []
        kwargs = kwargs or {}
        axis_map = self._axis_map
        for axis_name, data in datasets:
            try:
                axis = axis_map[axis_name]
            except KeyError:
                raise ValueError(f"Invalid axis name: {axis_name!r}") from None
            # Update from data if axis is already set but no unit is set yet.
            if axis is not None and data is not None and not axis.have_units():
                axis.update_units(data)
        for axis_name, axis in axis_map.items():
            # Return if no axis is set.
            if axis is None:
                continue
            # Check for units in the kwargs, and if present update axis.
            units = kwargs.pop(f"{axis_name}units", axis.units)
            if self.name == "polar":
                # Special case: polar supports "thetaunits"/"runits".
                polar_units = {"x": "thetaunits", "y": "runits"}
                units = kwargs.pop(polar_units[axis_name], units)
            if units != axis.units and units is not None:
                axis.set_units(units)
                # If the units being set imply a different converter,
                # we need to update again.
                for dataset_axis_name, data in datasets:
                    if dataset_axis_name == axis_name and data is not None:
                        axis.update_units(data)
        return [axis_map[axis_name].convert_units(data)
                if convert and data is not None else data
                for axis_name, data in datasets]

    def in_axes(self, mouseevent):
        """
        Return whether the given event (in display coords) is in the Axes.
        """
        return self.patch.contains(mouseevent)[0]

    get_autoscalex_on = _axis_method_wrapper("xaxis", "_get_autoscale_on")
    get_autoscaley_on = _axis_method_wrapper("yaxis", "_get_autoscale_on")
    set_autoscalex_on = _axis_method_wrapper("xaxis", "_set_autoscale_on")
    set_autoscaley_on = _axis_method_wrapper("yaxis", "_set_autoscale_on")

    def get_autoscale_on(self):
        """Return True if each axis is autoscaled, False otherwise."""
        return all(axis._get_autoscale_on()
                   for axis in self._axis_map.values())

    def set_autoscale_on(self, b):
        """
        Set whether autoscaling is applied to each axis on the next draw or
        call to `.Axes.autoscale_view`.

        Parameters
        ----------
        b : bool
        """
        for axis in self._axis_map.values():
            axis._set_autoscale_on(b)

    @property
    def use_sticky_edges(self):
        """
        When autoscaling, whether to obey all `.Artist.sticky_edges`.

        Default is ``True``.

        Setting this to ``False`` ensures that the specified margins
        will be applied, even if the plot includes an image, for
        example, which would otherwise force a view limit to coincide
        with its data limit.

        The changing this property does not change the plot until
        `autoscale` or `autoscale_view` is called.
        """
        return self._use_sticky_edges

    @use_sticky_edges.setter
    def use_sticky_edges(self, b):
        self._use_sticky_edges = bool(b)
        # No effect until next autoscaling, which will mark the Axes as stale.

    def get_xmargin(self):
        """
        Retrieve autoscaling margin of the x-axis.

        .. versionadded:: 3.9

        Returns
        -------
        xmargin : float

        See Also
        --------
        matplotlib.axes.Axes.set_xmargin
        """
        return self._xmargin

    def get_ymargin(self):
        """
        Retrieve autoscaling margin of the y-axis.

        .. versionadded:: 3.9

        Returns
        -------
        ymargin : float

        See Also
        --------
        matplotlib.axes.Axes.set_ymargin
        """
        return self._ymargin

    def set_xmargin(self, m):
        """
        Set padding of X data limits prior to autoscaling.

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
        self._xmargin = m
        self._request_autoscale_view("x")
        self.stale = True

    def set_ymargin(self, m):
        """
        Set padding of Y data limits prior to autoscaling.

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
        self._ymargin = m
        self._request_autoscale_view("y")
        self.stale = True

    def margins(self, *margins, x=None, y=None, tight=True):
        """
        Set or retrieve margins around the data for autoscaling axis limits.

        This allows to configure the padding around the data without having to
        set explicit limits using `~.Axes.set_xlim` / `~.Axes.set_ylim`.

        Autoscaling determines the axis limits by adding *margin* times the
        data interval as padding around the data. See the following illustration:

        .. plot:: _embedded_plots/axes_margins.py

        All input parameters must be floats greater than -0.5. Passing both
        positional and keyword arguments is invalid and will raise a TypeError.
        If no arguments (positional or otherwise) are provided, the current
        margins will remain unchanged and simply be returned.

        The default margins are :rc:`axes.xmargin` and :rc:`axes.ymargin`.

        Parameters
        ----------
        *margins : float, optional
            If a single positional argument is provided, it specifies
            both margins of the x-axis and y-axis limits. If two
            positional arguments are provided, they will be interpreted
            as *xmargin*, *ymargin*. If setting the margin on a single
            axis is desired, use the keyword arguments described below.

        x, y : float, optional
            Specific margin values for the x-axis and y-axis,
            respectively. These cannot be used with positional
            arguments, but can be used individually to alter on e.g.,
            only the y-axis.

        tight : bool or None, default: True
            The *tight* parameter is passed to `~.axes.Axes.autoscale_view`,
            which is executed after a margin is changed; the default
            here is *True*, on the assumption that when margins are
            specified, no additional padding to match tick marks is
            usually desired.  Setting *tight* to *None* preserves
            the previous setting.

        Returns
        -------
        xmargin, ymargin : float

        Notes
        -----
        If a previously used Axes method such as :meth:`pcolor` has set
        `~.Axes.use_sticky_edges` to `True`, only the limits not set by
        the "sticky artists" will be modified. To force all
        margins to be set, set `~.Axes.use_sticky_edges` to `False`
        before calling :meth:`margins`.

        See Also
        --------
        .Axes.set_xmargin, .Axes.set_ymargin
        """

        if margins and (x is not None or y is not None):
            raise TypeError('Cannot pass both positional and keyword '
                            'arguments for x and/or y.')
        elif len(margins) == 1:
            x = y = margins[0]
        elif len(margins) == 2:
            x, y = margins
        elif margins:
            raise TypeError('Must pass a single positional argument for all '
                            'margins, or one for each margin (x, y).')

        if x is None and y is None:
            if tight is not True:
                _api.warn_external(f'ignoring tight={tight!r} in get mode')
            return self._xmargin, self._ymargin

        if tight is not None:
            self._tight = tight
        if x is not None:
            self.set_xmargin(x)
        if y is not None:
            self.set_ymargin(y)

    def set_rasterization_zorder(self, z):
        """
        Set the zorder threshold for rasterization for vector graphics output.

        All artists with a zorder below the given value will be rasterized if
        they support rasterization.

        This setting is ignored for pixel-based output.

        See also :doc:`/gallery/misc/rasterization_demo`.

        Parameters
        ----------
        z : float or None
            The zorder below which artists are rasterized.
            If ``None`` rasterization based on zorder is deactivated.
        """
        self._rasterization_zorder = z
        self.stale = True

    def get_rasterization_zorder(self):
        """Return the zorder value below which artists will be rasterized."""
        return self._rasterization_zorder

    def autoscale(self, enable=True, axis='both', tight=None):
        """
        Autoscale the axis view to the data (toggle).

        Convenience method for simple axis view autoscaling.
        It turns autoscaling on or off, and then,
        if autoscaling for either axis is on, it performs
        the autoscaling on the specified axis or Axes.

        Parameters
        ----------
        enable : bool or None, default: True
            True turns autoscaling on, False turns it off.
            None leaves the autoscaling state unchanged.
        axis : {'both', 'x', 'y'}, default: 'both'
            The axis on which to operate.  (For 3D Axes, *axis* can also be set
            to 'z', and 'both' refers to all three Axes.)
        tight : bool or None, default: None
            If True, first set the margins to zero.  Then, this argument is
            forwarded to `~.axes.Axes.autoscale_view` (regardless of
            its value); see the description of its behavior there.
        """
        if enable is None:
            scalex = True
            scaley = True
        else:
            if axis in ['x', 'both']:
                self.set_autoscalex_on(bool(enable))
                scalex = self.get_autoscalex_on()
            else:
                scalex = False
            if axis in ['y', 'both']:
                self.set_autoscaley_on(bool(enable))
                scaley = self.get_autoscaley_on()
            else:
                scaley = False
        if tight and scalex:
            self._xmargin = 0
        if tight and scaley:
            self._ymargin = 0
        if scalex:
            self._request_autoscale_view("x", tight=tight)
        if scaley:
            self._request_autoscale_view("y", tight=tight)

    def autoscale_view(self, tight=None, scalex=True, scaley=True):
        """
        Autoscale the view limits using the data limits.

        Parameters
        ----------
        tight : bool or None
            If *True*, only expand the axis limits using the margins.  Note
            that unlike for `autoscale`, ``tight=True`` does *not* set the
            margins to zero.

            If *False* and :rc:`axes.autolimit_mode` is 'round_numbers', then
            after expansion by the margins, further expand the axis limits
            using the axis major locator.

            If None (the default), reuse the value set in the previous call to
            `autoscale_view` (the initial value is False, but the default style
            sets :rc:`axes.autolimit_mode` to 'data', in which case this
            behaves like True).

        scalex : bool, default: True
            Whether to autoscale the x-axis.

        scaley : bool, default: True
            Whether to autoscale the y-axis.

        Notes
        -----
        The autoscaling preserves any preexisting axis direction reversal.

        The data limits are not updated automatically when artist data are
        changed after the artist has been added to an Axes instance.  In that
        case, use :meth:`matplotlib.axes.Axes.relim` prior to calling
        autoscale_view.

        If the views of the Axes are fixed, e.g. via `set_xlim`, they will
        not be changed by autoscale_view().
        See :meth:`matplotlib.axes.Axes.autoscale` for an alternative.
        """
        if tight is not None:
            self._tight = bool(tight)

        x_stickies = y_stickies = np.array([])
        if self.use_sticky_edges:
            if self._xmargin and scalex and self.get_autoscalex_on():
                x_stickies = np.sort(np.concatenate([
                    artist.sticky_edges.x
                    for ax in self._shared_axes["x"].get_siblings(self)
                    for artist in ax.get_children()]))
            if self._ymargin and scaley and self.get_autoscaley_on():
                y_stickies = np.sort(np.concatenate([
                    artist.sticky_edges.y
                    for ax in self._shared_axes["y"].get_siblings(self)
                    for artist in ax.get_children()]))
        if self.get_xscale() == 'log':
            x_stickies = x_stickies[x_stickies > 0]
        if self.get_yscale() == 'log':
            y_stickies = y_stickies[y_stickies > 0]

        def handle_single_axis(
                scale, shared_axes, name, axis, margin, stickies, set_bound):

            if not (scale and axis._get_autoscale_on()):
                return  # nothing to do...

            shared = shared_axes.get_siblings(self)
            # Base autoscaling on finite data limits when there is at least one
            # finite data limit among all the shared_axes and intervals.
            values = [val for ax in shared
                      for val in getattr(ax.dataLim, f"interval{name}")
                      if np.isfinite(val)]
            if values:
                x0, x1 = (min(values), max(values))
            elif getattr(self._viewLim, f"mutated{name}")():
                # No data, but explicit viewLims already set:
                # in mutatedx or mutatedy.
                return
            else:
                x0, x1 = (-np.inf, np.inf)
            # If x0 and x1 are nonfinite, get default limits from the locator.
            locator = axis.get_major_locator()
            x0, x1 = locator.nonsingular(x0, x1)
            # Find the minimum minpos for use in the margin calculation.
            minimum_minpos = min(
                getattr(ax.dataLim, f"minpos{name}") for ax in shared)

            # Prevent margin addition from crossing a sticky value.  A small
            # tolerance must be added due to floating point issues with
            # streamplot; it is defined relative to x1-x0 but has
            # no absolute term (e.g. "+1e-8") to avoid issues when working with
            # datasets where all values are tiny (less than 1e-8).
            tol = 1e-5 * abs(x1 - x0)
            # Index of largest element < x0 + tol, if any.
            i0 = stickies.searchsorted(x0 + tol) - 1
            x0bound = stickies[i0] if i0 != -1 else None
            # Index of smallest element > x1 - tol, if any.
            i1 = stickies.searchsorted(x1 - tol)
            x1bound = stickies[i1] if i1 != len(stickies) else None

            # Add the margin in figure space and then transform back, to handle
            # non-linear scales.
            transform = axis.get_transform()
            inverse_trans = transform.inverted()
            x0, x1 = axis._scale.limit_range_for_scale(x0, x1, minimum_minpos)
            x0t, x1t = transform.transform([x0, x1])
            delta = (x1t - x0t) * margin
            if not np.isfinite(delta):
                delta = 0  # If a bound isn't finite, set margin to zero.
            x0, x1 = inverse_trans.transform([x0t - delta, x1t + delta])

            # Apply sticky bounds.
            if x0bound is not None:
                x0 = max(x0, x0bound)
            if x1bound is not None:
                x1 = min(x1, x1bound)

            if not self._tight:
                x0, x1 = locator.view_limits(x0, x1)
            set_bound(x0, x1)
            # End of definition of internal function 'handle_single_axis'.

        handle_single_axis(
            scalex, self._shared_axes["x"], 'x', self.xaxis, self._xmargin,
            x_stickies, self.set_xbound)
        handle_single_axis(
            scaley, self._shared_axes["y"], 'y', self.yaxis, self._ymargin,
            y_stickies, self.set_ybound)

    def _update_title_position(self, renderer):
        """
        Update the title position based on the bounding box enclosing
        all the ticklabels and x-axis spine and xlabel...
        """
        if self._autotitlepos is not None and not self._autotitlepos:
            _log.debug('title position was updated manually, not adjusting')
            return

        titles = (self.title, self._left_title, self._right_title)

        if not any(title.get_text() for title in titles):
            # If the titles are all empty, there is no need to update their positions.
            return

        # Need to check all our twins too, aligned axes, and all the children
        # as well.
        axs = set()
        axs.update(self.child_axes)
        axs.update(self._twinned_axes.get_siblings(self))
        axs.update(
            self.get_figure(root=False)._align_label_groups['title'].get_siblings(self))

        for ax in self.child_axes:  # Child positions must be updated first.
            locator = ax.get_axes_locator()
            ax.apply_aspect(locator(self, renderer) if locator else None)

        top = -np.inf
        for ax in axs:
            bb = None
            if (ax.xaxis.get_ticks_position() in ['top', 'unknown'] or
                    ax.xaxis.get_label_position() == 'top'):
                bb = ax.xaxis.get_tightbbox(renderer)
            if bb is None:
                # Extent of the outline for colorbars, of the axes otherwise.
                bb = ax.spines.get("outline", ax).get_window_extent()
            top = max(top, bb.ymax)

        for title in titles:
            x, _ = title.get_position()
            # need to start again in case of window resizing
            title.set_position((x, 1.0))
            if title.get_text():
                for ax in axs:
                    ax.yaxis.get_tightbbox(renderer)  # update offsetText
                    if ax.yaxis.offsetText.get_text():
                        bb = ax.yaxis.offsetText.get_tightbbox(renderer)
                        if bb.intersection(title.get_tightbbox(renderer), bb):
                            top = bb.ymax
            if top < 0:
                # the top of Axes is not even on the figure, so don't try and
                # automatically place it.
                _log.debug('top of Axes not in the figure, so title not moved')
                return
            if title.get_window_extent(renderer).ymin < top:
                _, y = self.transAxes.inverted().transform((0, top))
                title.set_position((x, y))
                # empirically, this doesn't always get the min to top,
                # so we need to adjust again.
                if title.get_window_extent(renderer).ymin < top:
                    _, y = self.transAxes.inverted().transform(
                        (0., 2 * top - title.get_window_extent(renderer).ymin))
                    title.set_position((x, y))

        ymax = max(title.get_position()[1] for title in titles)
        for title in titles:
            # now line up all the titles at the highest baseline.
            x, _ = title.get_position()
            title.set_position((x, ymax))

    # Drawing
    @martist.allow_rasterization
    def draw(self, renderer):
        # docstring inherited
        if renderer is None:
            raise RuntimeError('No renderer defined')
        if not self.get_visible():
            return
        self._unstale_viewLim()

        renderer.open_group('axes', gid=self.get_gid())

        # prevent triggering call backs during the draw process
        self._stale = True

        # loop over self and child Axes...
        locator = self.get_axes_locator()
        self.apply_aspect(locator(self, renderer) if locator else None)

        artists = self.get_children()
        artists.remove(self.patch)

        # the frame draws the edges around the Axes patch -- we
        # decouple these so the patch can be in the background and the
        # frame in the foreground. Do this before drawing the axis
        # objects so that the spine has the opportunity to update them.
        if not (self.axison and self._frameon):
            for spine in self.spines.values():
                artists.remove(spine)

        self._update_title_position(renderer)

        if not self.axison:
            for _axis in self._axis_map.values():
                artists.remove(_axis)

        if not self.get_figure(root=True).canvas.is_saving():
            artists = [
                a for a in artists
                if not a.get_animated() or isinstance(a, mimage.AxesImage)]
        artists = sorted(artists, key=attrgetter('zorder'))

        # rasterize artists with negative zorder
        # if the minimum zorder is negative, start rasterization
        rasterization_zorder = self._rasterization_zorder

        if (rasterization_zorder is not None and
                artists and artists[0].zorder < rasterization_zorder):
            split_index = np.searchsorted(
                [art.zorder for art in artists],
                rasterization_zorder, side='right'
            )
            artists_rasterized = artists[:split_index]
            artists = artists[split_index:]
        else:
            artists_rasterized = []

        if self.axison and self._frameon:
            if artists_rasterized:
                artists_rasterized = [self.patch] + artists_rasterized
            else:
                artists = [self.patch] + artists

        if artists_rasterized:
            _draw_rasterized(self.get_figure(root=True), artists_rasterized, renderer)

        mimage._draw_list_compositing_images(
            renderer, self, artists, self.get_figure(root=True).suppressComposite)

        renderer.close_group('axes')
        self.stale = False

    def draw_artist(self, a):
        """
        Efficiently redraw a single artist.
        """
        a.draw(self.get_figure(root=True).canvas.get_renderer())

    def redraw_in_frame(self):
        """
        Efficiently redraw Axes data, but not axis ticks, labels, etc.
        """
        with ExitStack() as stack:
            for artist in [*self._axis_map.values(),
                           self.title, self._left_title, self._right_title]:
                stack.enter_context(artist._cm_set(visible=False))
            self.draw(self.get_figure(root=True).canvas.get_renderer())

    # Axes rectangle characteristics

    def get_frame_on(self):
        """Get whether the Axes rectangle patch is drawn."""
        return self._frameon

    def set_frame_on(self, b):
        """
        Set whether the Axes rectangle patch is drawn.

        Parameters
        ----------
        b : bool
        """
        self._frameon = b
        self.stale = True

    def get_axisbelow(self):
        """
        Get whether axis ticks and gridlines are above or below most artists.

        Returns
        -------
        bool or 'line'

        See Also
        --------
        set_axisbelow
        """
        return self._axisbelow

    def set_axisbelow(self, b):
        """
        Set whether axis ticks and gridlines are above or below most artists.

        This controls the zorder of the ticks and gridlines. For more
        information on the zorder see :doc:`/gallery/misc/zorder_demo`.

        Parameters
        ----------
        b : bool or 'line'
            Possible values:

            - *True* (zorder = 0.5): Ticks and gridlines are below patches and
              lines, though still above images.
            - 'line' (zorder = 1.5): Ticks and gridlines are above patches
              (e.g. rectangles, with default zorder = 1) but still below lines
              and markers (with their default zorder = 2).
            - *False* (zorder = 2.5): Ticks and gridlines are above patches
              and lines / markers.

        Notes
        -----
        For more control, call the `~.Artist.set_zorder` method of each axis.

        See Also
        --------
        get_axisbelow
        """
        # Check that b is True, False or 'line'
        self._axisbelow = axisbelow = validate_axisbelow(b)
        zorder = {
            True: 0.5,
            'line': 1.5,
            False: 2.5,
        }[axisbelow]
        for axis in self._axis_map.values():
            axis.set_zorder(zorder)
        self.stale = True

    @_docstring.interpd
    def grid(self, visible=None, which='major', axis='both', **kwargs):
        """
        Configure the grid lines.

        Parameters
        ----------
        visible : bool or None, optional
            Whether to show the grid lines.  If any *kwargs* are supplied, it
            is assumed you want the grid on and *visible* will be set to True.

            If *visible* is *None* and there are no *kwargs*, this toggles the
            visibility of the lines.

        which : {'major', 'minor', 'both'}, optional
            The grid lines to apply the changes on.

        axis : {'both', 'x', 'y'}, optional
            The axis to apply the changes on.

        **kwargs : `~matplotlib.lines.Line2D` properties
            Define the line properties of the grid, e.g.::

                grid(color='r', linestyle='-', linewidth=2)

            Valid keyword arguments are:

            %(Line2D:kwdoc)s

        Notes
        -----
        The axis is drawn as a unit, so the effective zorder for drawing the
        grid is determined by the zorder of each axis, not by the zorder of the
        `.Line2D` objects comprising the grid.  Therefore, to set grid zorder,
        use `.set_axisbelow` or, for more control, call the
        `~.Artist.set_zorder` method of each axis.
        """
        _api.check_in_list(['x', 'y', 'both'], axis=axis)
        if axis in ['x', 'both']:
            self.xaxis.grid(visible, which=which, **kwargs)
        if axis in ['y', 'both']:
            self.yaxis.grid(visible, which=which, **kwargs)

    def ticklabel_format(self, *, axis='both', style=None, scilimits=None,
                         useOffset=None, useLocale=None, useMathText=None):
        r"""
        Configure the `.ScalarFormatter` used by default for linear Axes.

        If a parameter is not set, the corresponding property of the formatter
        is left unchanged.

        Parameters
        ----------
        axis : {'x', 'y', 'both'}, default: 'both'
            The axis to configure.  Only major ticks are affected.

        style : {'sci', 'scientific', 'plain'}
            Whether to use scientific notation.
            The formatter default is to use scientific notation.
            'sci' is equivalent to 'scientific'.

        scilimits : pair of ints (m, n)
            Scientific notation is used only for numbers outside the range
            10\ :sup:`m` to 10\ :sup:`n` (and only if the formatter is
            configured to use scientific notation at all).  Use (0, 0) to
            include all numbers.  Use (m, m) where m != 0 to fix the order of
            magnitude to 10\ :sup:`m`.
            The formatter default is :rc:`axes.formatter.limits`.

        useOffset : bool or float
            If True, the offset is calculated as needed.
            If False, no offset is used.
            If a numeric value, it sets the offset.
            The formatter default is :rc:`axes.formatter.useoffset`.

        useLocale : bool
            Whether to format the number using the current locale or using the
            C (English) locale.  This affects e.g. the decimal separator.  The
            formatter default is :rc:`axes.formatter.use_locale`.

        useMathText : bool
            Render the offset and scientific notation in mathtext.
            The formatter default is :rc:`axes.formatter.use_mathtext`.

        Raises
        ------
        AttributeError
            If the current formatter is not a `.ScalarFormatter`.
        """
        if isinstance(style, str):
            style = style.lower()
        axis = axis.lower()
        if scilimits is not None:
            try:
                m, n = scilimits
                m + n + 1  # check that both are numbers
            except (ValueError, TypeError) as err:
                raise ValueError("scilimits must be a sequence of 2 integers"
                                 ) from err
        STYLES = {'sci': True, 'scientific': True, 'plain': False, '': None, None: None}
        # The '' option is included for backwards-compatibility.
        is_sci_style = _api.check_getitem(STYLES, style=style)
        axis_map = {**{k: [v] for k, v in self._axis_map.items()},
                    'both': list(self._axis_map.values())}
        axises = _api.check_getitem(axis_map, axis=axis)
        try:
            for axis in axises:
                if is_sci_style is not None:
                    axis.major.formatter.set_scientific(is_sci_style)
                if scilimits is not None:
                    axis.major.formatter.set_powerlimits(scilimits)
                if useOffset is not None:
                    axis.major.formatter.set_useOffset(useOffset)
                if useLocale is not None:
                    axis.major.formatter.set_useLocale(useLocale)
                if useMathText is not None:
                    axis.major.formatter.set_useMathText(useMathText)
        except AttributeError as err:
            raise AttributeError(
                "This method only works with the ScalarFormatter") from err

    def locator_params(self, axis='both', tight=None, **kwargs):
        """
        Control behavior of major tick locators.

        Because the locator is involved in autoscaling, `~.Axes.autoscale_view`
        is called automatically after the parameters are changed.

        Parameters
        ----------
        axis : {'both', 'x', 'y'}, default: 'both'
            The axis on which to operate.  (For 3D Axes, *axis* can also be
            set to 'z', and 'both' refers to all three axes.)
        tight : bool or None, optional
            Parameter passed to `~.Axes.autoscale_view`.
            Default is None, for no change.

        Other Parameters
        ----------------
        **kwargs
            Remaining keyword arguments are passed to directly to the
            ``set_params()`` method of the locator. Supported keywords depend
            on the type of the locator. See for example
            `~.ticker.MaxNLocator.set_params` for the `.ticker.MaxNLocator`
            used by default for linear.

        Examples
        --------
        When plotting small subplots, one might want to reduce the maximum
        number of ticks and use tight bounds, for example::

            ax.locator_params(tight=True, nbins=4)

        """
        _api.check_in_list([*self._axis_names, "both"], axis=axis)
        for name in self._axis_names:
            if axis in [name, "both"]:
                loc = self._axis_map[name].get_major_locator()
                loc.set_params(**kwargs)
                self._request_autoscale_view(name, tight=tight)
        self.stale = True

    def tick_params(self, axis='both', **kwargs):
        """
        Change the appearance of ticks, tick labels, and gridlines.

        Tick properties that are not explicitly set using the keyword
        arguments remain unchanged unless *reset* is True. For the current
        style settings, see `.Axis.get_tick_params`.

        Parameters
        ----------
        axis : {'x', 'y', 'both'}, default: 'both'
            The axis to which the parameters are applied.
        which : {'major', 'minor', 'both'}, default: 'major'
            The group of ticks to which the parameters are applied.
        reset : bool, default: False
            Whether to reset the ticks to defaults before updating them.

        Other Parameters
        ----------------
        direction : {'in', 'out', 'inout'}
            Puts ticks inside the Axes, outside the Axes, or both.
        length : float
            Tick length in points.
        width : float
            Tick width in points.
        color : :mpltype:`color`
            Tick color.
        pad : float
            Distance in points between tick and label.
        labelsize : float or str
            Tick label font size in points or as a string (e.g., 'large').
        labelcolor : :mpltype:`color`
            Tick label color.
        labelfontfamily : str
            Tick label font.
        colors : :mpltype:`color`
            Tick color and label color.
        zorder : float
            Tick and label zorder.
        bottom, top, left, right : bool
            Whether to draw the respective ticks.
        labelbottom, labeltop, labelleft, labelright : bool
            Whether to draw the respective tick labels.
        labelrotation : float
            Tick label rotation
        grid_color : :mpltype:`color`
            Gridline color.
        grid_alpha : float
            Transparency of gridlines: 0 (transparent) to 1 (opaque).
        grid_linewidth : float
            Width of gridlines in points.
        grid_linestyle : str
            Any valid `.Line2D` line style spec.

        Examples
        --------
        ::

            ax.tick_params(direction='out', length=6, width=2, colors='r',
                           grid_color='r', grid_alpha=0.5)

        This will make all major ticks be red, pointing out of the box,
        and with dimensions 6 points by 2 points.  Tick labels will
        also be red.  Gridlines will be red and translucent.

        """
        _api.check_in_list(['x', 'y', 'both'], axis=axis)
        if axis in ['x', 'both']:
            xkw = dict(kwargs)
            xkw.pop('left', None)
            xkw.pop('right', None)
            xkw.pop('labelleft', None)
            xkw.pop('labelright', None)
            self.xaxis.set_tick_params(**xkw)
        if axis in ['y', 'both']:
            ykw = dict(kwargs)
            ykw.pop('top', None)
            ykw.pop('bottom', None)
            ykw.pop('labeltop', None)
            ykw.pop('labelbottom', None)
            self.yaxis.set_tick_params(**ykw)

    def set_axis_off(self):
        """
        Hide all visual components of the x- and y-axis.

        This sets a flag to suppress drawing of all axis decorations, i.e.
        axis labels, axis spines, and the axis tick component (tick markers,
        tick labels, and grid lines). Individual visibility settings of these
        components are ignored as long as `set_axis_off()` is in effect.
        """
        self.axison = False
        self.stale = True

    def set_axis_on(self):
        """
        Do not hide all visual components of the x- and y-axis.

        This reverts the effect of a prior `.set_axis_off()` call. Whether the
        individual axis decorations are drawn is controlled by their respective
        visibility settings.

        This is on by default.
        """
        self.axison = True
        self.stale = True

    # data limits, ticks, tick labels, and formatting

    def get_xlabel(self):
        """
        Get the xlabel text string.
        """
        label = self.xaxis.label
        return label.get_text()

    def set_xlabel(self, xlabel, fontdict=None, labelpad=None, *,
                   loc=None, **kwargs):
        """
        Set the label for the x-axis.

        Parameters
        ----------
        xlabel : str
            The label text.

        labelpad : float, default: :rc:`axes.labelpad`
            Spacing in points from the Axes bounding box including ticks
            and tick labels.  If None, the previous value is left as is.

        loc : {'left', 'center', 'right'}, default: :rc:`xaxis.labellocation`
            The label position. This is a high-level alternative for passing
            parameters *x* and *horizontalalignment*.

        Other Parameters
        ----------------
        **kwargs : `~matplotlib.text.Text` properties
            `.Text` properties control the appearance of the label.

        See Also
        --------
        text : Documents the properties supported by `.Text`.
        """
        if labelpad is not None:
            self.xaxis.labelpad = labelpad
        protected_kw = ['x', 'horizontalalignment', 'ha']
        if {*kwargs} & {*protected_kw}:
            if loc is not None:
                raise TypeError(f"Specifying 'loc' is disallowed when any of "
                                f"its corresponding low level keyword "
                                f"arguments ({protected_kw}) are also "
                                f"supplied")

        else:
            loc = (loc if loc is not None
                   else mpl.rcParams['xaxis.labellocation'])
            _api.check_in_list(('left', 'center', 'right'), loc=loc)

            x = {
                'left': 0,
                'center': 0.5,
                'right': 1,
            }[loc]
            kwargs.update(x=x, horizontalalignment=loc)

        return self.xaxis.set_label_text(xlabel, fontdict, **kwargs)

    def invert_xaxis(self):
        """
        Invert the x-axis.

        See Also
        --------
        xaxis_inverted
        get_xlim, set_xlim
        get_xbound, set_xbound
        """
        self.xaxis.set_inverted(not self.xaxis.get_inverted())

    xaxis_inverted = _axis_method_wrapper("xaxis", "get_inverted")

    def get_xbound(self):
        """
        Return the lower and upper x-axis bounds, in increasing order.

        See Also
        --------
        set_xbound
        get_xlim, set_xlim
        invert_xaxis, xaxis_inverted
        """
        left, right = self.get_xlim()
        if left < right:
            return left, right
        else:
            return right, left

    def set_xbound(self, lower=None, upper=None):
        """
        Set the lower and upper numerical bounds of the x-axis.

        This method will honor axis inversion regardless of parameter order.
        It will not change the autoscaling setting (`.get_autoscalex_on()`).

        Parameters
        ----------
        lower, upper : float or None
            The lower and upper bounds. If *None*, the respective axis bound
            is not modified.

            .. ACCEPTS: (lower: float, upper: float)

        See Also
        --------
        get_xbound
        get_xlim, set_xlim
        invert_xaxis, xaxis_inverted
        """
        if upper is None and np.iterable(lower):
            lower, upper = lower

        old_lower, old_upper = self.get_xbound()
        if lower is None:
            lower = old_lower
        if upper is None:
            upper = old_upper

        self.set_xlim(sorted((lower, upper),
                             reverse=bool(self.xaxis_inverted())),
                      auto=None)

    def get_xlim(self):
        """
        Return the x-axis view limits.

        Returns
        -------
        left, right : (float, float)
            The current x-axis limits in data coordinates.

        See Also
        --------
        .Axes.set_xlim
        .Axes.set_xbound, .Axes.get_xbound
        .Axes.invert_xaxis, .Axes.xaxis_inverted

        Notes
        -----
        The x-axis may be inverted, in which case the *left* value will
        be greater than the *right* value.
        """
        return tuple(self.viewLim.intervalx)

    def _validate_converted_limits(self, limit, convert):
        """
        Raise ValueError if converted limits are non-finite.

        Note that this function also accepts None as a limit argument.

        Returns
        -------
        The limit value after call to convert(), or None if limit is None.
        """
        if limit is not None:
            converted_limit = convert(limit)
            if isinstance(converted_limit, np.ndarray):
                converted_limit = converted_limit.squeeze()
            if (isinstance(converted_limit, Real)
                    and not np.isfinite(converted_limit)):
                raise ValueError("Axis limits cannot be NaN or Inf")
            return converted_limit

    def set_xlim(self, left=None, right=None, *, emit=True, auto=False,
                 xmin=None, xmax=None):
        """
        Set the x-axis view limits.

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
            Whether to turn on autoscaling of the x-axis. True turns on,
            False turns off, None leaves unchanged.

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
        case the x-axis values will decrease from left to right.

        Examples
        --------
        >>> set_xlim(left, right)
        >>> set_xlim((left, right))
        >>> left, right = set_xlim(left, right)

        One limit may be left unchanged.

        >>> set_xlim(right=right_lim)

        Limits may be passed in reverse order to flip the direction of
        the x-axis. For example, suppose *x* represents the number of
        years before present. The x-axis limits might be set like the
        following so 5000 years ago is on the left of the plot and the
        present is on the right.

        >>> set_xlim(5000, 0)
        """
        if right is None and np.iterable(left):
            left, right = left
        if xmin is not None:
            if left is not None:
                raise TypeError("Cannot pass both 'left' and 'xmin'")
            left = xmin
        if xmax is not None:
            if right is not None:
                raise TypeError("Cannot pass both 'right' and 'xmax'")
            right = xmax
        return self.xaxis._set_lim(left, right, emit=emit, auto=auto)

    get_xscale = _axis_method_wrapper("xaxis", "get_scale")
    set_xscale = _axis_method_wrapper("xaxis", "_set_axes_scale")
    get_xticks = _axis_method_wrapper("xaxis", "get_ticklocs")
    set_xticks = _axis_method_wrapper("xaxis", "set_ticks",
                                      doc_sub={'set_ticks': 'set_xticks'})
    get_xmajorticklabels = _axis_method_wrapper("xaxis", "get_majorticklabels")
    get_xminorticklabels = _axis_method_wrapper("xaxis", "get_minorticklabels")
    get_xticklabels = _axis_method_wrapper("xaxis", "get_ticklabels")
    set_xticklabels = _axis_method_wrapper(
        "xaxis", "set_ticklabels",
        doc_sub={"Axis.set_ticks": "Axes.set_xticks"})

    def get_ylabel(self):
        """
        Get the ylabel text string.
        """
        label = self.yaxis.label
        return label.get_text()

    def set_ylabel(self, ylabel, fontdict=None, labelpad=None, *,
                   loc=None, **kwargs):
        """
        Set the label for the y-axis.

        Parameters
        ----------
        ylabel : str
            The label text.

        labelpad : float, default: :rc:`axes.labelpad`
            Spacing in points from the Axes bounding box including ticks
            and tick labels.  If None, the previous value is left as is.

        loc : {'bottom', 'center', 'top'}, default: :rc:`yaxis.labellocation`
            The label position. This is a high-level alternative for passing
            parameters *y* and *horizontalalignment*.

        Other Parameters
        ----------------
        **kwargs : `~matplotlib.text.Text` properties
            `.Text` properties control the appearance of the label.

        See Also
        --------
        text : Documents the properties supported by `.Text`.
        """
        if labelpad is not None:
            self.yaxis.labelpad = labelpad
        protected_kw = ['y', 'horizontalalignment', 'ha']
        if {*kwargs} & {*protected_kw}:
            if loc is not None:
                raise TypeError(f"Specifying 'loc' is disallowed when any of "
                                f"its corresponding low level keyword "
                                f"arguments ({protected_kw}) are also "
                                f"supplied")

        else:
            loc = (loc if loc is not None
                   else mpl.rcParams['yaxis.labellocation'])
            _api.check_in_list(('bottom', 'center', 'top'), loc=loc)

            y, ha = {
                'bottom': (0, 'left'),
                'center': (0.5, 'center'),
                'top': (1, 'right')
            }[loc]
            kwargs.update(y=y, horizontalalignment=ha)

        return self.yaxis.set_label_text(ylabel, fontdict, **kwargs)

    def invert_yaxis(self):
        """
        Invert the y-axis.

        See Also
        --------
        yaxis_inverted
        get_ylim, set_ylim
        get_ybound, set_ybound
        """
        self.yaxis.set_inverted(not self.yaxis.get_inverted())

    yaxis_inverted = _axis_method_wrapper("yaxis", "get_inverted")

    def get_ybound(self):
        """
        Return the lower and upper y-axis bounds, in increasing order.

        See Also
        --------
        set_ybound
        get_ylim, set_ylim
        invert_yaxis, yaxis_inverted
        """
        bottom, top = self.get_ylim()
        if bottom < top:
            return bottom, top
        else:
            return top, bottom

    def set_ybound(self, lower=None, upper=None):
        """
        Set the lower and upper numerical bounds of the y-axis.

        This method will honor axis inversion regardless of parameter order.
        It will not change the autoscaling setting (`.get_autoscaley_on()`).

        Parameters
        ----------
        lower, upper : float or None
            The lower and upper bounds. If *None*, the respective axis bound
            is not modified.

         .. ACCEPTS: (lower: float, upper: float)

        See Also
        --------
        get_ybound
        get_ylim, set_ylim
        invert_yaxis, yaxis_inverted
        """
        if upper is None and np.iterable(lower):
            lower, upper = lower

        old_lower, old_upper = self.get_ybound()
        if lower is None:
            lower = old_lower
        if upper is None:
            upper = old_upper

        self.set_ylim(sorted((lower, upper),
                             reverse=bool(self.yaxis_inverted())),
                      auto=None)

    def get_ylim(self):
        """
        Return the y-axis view limits.

        Returns
        -------
        bottom, top : (float, float)
            The current y-axis limits in data coordinates.

        See Also
        --------
        .Axes.set_ylim
        .Axes.set_ybound, .Axes.get_ybound
        .Axes.invert_yaxis, .Axes.yaxis_inverted

        Notes
        -----
        The y-axis may be inverted, in which case the *bottom* value
        will be greater than the *top* value.
        """
        return tuple(self.viewLim.intervaly)

    def set_ylim(self, bottom=None, top=None, *, emit=True, auto=False,
                 ymin=None, ymax=None):
        """
        Set the y-axis view limits.

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
        if top is None and np.iterable(bottom):
            bottom, top = bottom
        if ymin is not None:
            if bottom is not None:
                raise TypeError("Cannot pass both 'bottom' and 'ymin'")
            bottom = ymin
        if ymax is not None:
            if top is not None:
                raise TypeError("Cannot pass both 'top' and 'ymax'")
            top = ymax
        return self.yaxis._set_lim(bottom, top, emit=emit, auto=auto)

    get_yscale = _axis_method_wrapper("yaxis", "get_scale")
    set_yscale = _axis_method_wrapper("yaxis", "_set_axes_scale")
    get_yticks = _axis_method_wrapper("yaxis", "get_ticklocs")
    set_yticks = _axis_method_wrapper("yaxis", "set_ticks",
                                      doc_sub={'set_ticks': 'set_yticks'})
    get_ymajorticklabels = _axis_method_wrapper("yaxis", "get_majorticklabels")
    get_yminorticklabels = _axis_method_wrapper("yaxis", "get_minorticklabels")
    get_yticklabels = _axis_method_wrapper("yaxis", "get_ticklabels")
    set_yticklabels = _axis_method_wrapper(
        "yaxis", "set_ticklabels",
        doc_sub={"Axis.set_ticks": "Axes.set_yticks"})

    xaxis_date = _axis_method_wrapper("xaxis", "axis_date")
    yaxis_date = _axis_method_wrapper("yaxis", "axis_date")

    def format_xdata(self, x):
        """
        Return *x* formatted as an x-value.

        This function will use the `.fmt_xdata` attribute if it is not None,
        else will fall back on the xaxis major formatter.
        """
        return (self.fmt_xdata if self.fmt_xdata is not None
                else self.xaxis.get_major_formatter().format_data_short)(x)

    def format_ydata(self, y):
        """
        Return *y* formatted as a y-value.

        This function will use the `.fmt_ydata` attribute if it is not None,
        else will fall back on the yaxis major formatter.
        """
        return (self.fmt_ydata if self.fmt_ydata is not None
                else self.yaxis.get_major_formatter().format_data_short)(y)

    def format_coord(self, x, y):
        """Return a format string formatting the *x*, *y* coordinates."""
        twins = self._twinned_axes.get_siblings(self)
        if len(twins) == 1:
            return "(x, y) = ({}, {})".format(
                "???" if x is None else self.format_xdata(x),
                "???" if y is None else self.format_ydata(y))
        screen_xy = self.transData.transform((x, y))
        xy_strs = []
        # Retrieve twins in the order of self.figure.axes to sort tied zorders (which is
        # the common case) by the order in which they are added to the figure.
        for ax in sorted(twins, key=attrgetter("zorder")):
            data_x, data_y = ax.transData.inverted().transform(screen_xy)
            xy_strs.append(
                "({}, {})".format(ax.format_xdata(data_x), ax.format_ydata(data_y)))
        return "(x, y) = {}".format(" | ".join(xy_strs))

    def minorticks_on(self):
        """
        Display minor ticks on the Axes.

        Displaying minor ticks may reduce performance; you may turn them off
        using `minorticks_off()` if drawing speed is a problem.
        """
        self.xaxis.minorticks_on()
        self.yaxis.minorticks_on()

    def minorticks_off(self):
        """Remove minor ticks from the Axes."""
        self.xaxis.minorticks_off()
        self.yaxis.minorticks_off()

    # Interactive manipulation

    def can_zoom(self):
        """
        Return whether this Axes supports the zoom box button functionality.
        """
        return True

    def can_pan(self):
        """
        Return whether this Axes supports any pan/zoom button functionality.
        """
        return True

    def get_navigate(self):
        """
        Get whether the Axes responds to navigation commands.
        """
        return self._navigate

    def set_navigate(self, b):
        """
        Set whether the Axes responds to navigation toolbar commands.

        Parameters
        ----------
        b : bool

        See Also
        --------
        matplotlib.axes.Axes.set_forward_navigation_events

        """
        self._navigate = b

    def get_navigate_mode(self):
        """
        Get the navigation toolbar button status: 'PAN', 'ZOOM', or None.
        """
        return self._navigate_mode

    def set_navigate_mode(self, b):
        """
        Set the navigation toolbar button status.

        .. warning::
            This is not a user-API function.

        """
        self._navigate_mode = b

    def _get_view(self):
        """
        Save information required to reproduce the current view.

        This method is called before a view is changed, such as during a pan or zoom
        initiated by the user.  It returns an opaque object that describes the current
        view, in a format compatible with :meth:`_set_view`.

        The default implementation saves the view limits and autoscaling state.
        Subclasses may override this as needed, as long as :meth:`_set_view` is also
        adjusted accordingly.
        """
        return {
            "xlim": self.get_xlim(), "autoscalex_on": self.get_autoscalex_on(),
            "ylim": self.get_ylim(), "autoscaley_on": self.get_autoscaley_on(),
        }

    def _set_view(self, view):
        """
        Apply a previously saved view.

        This method is called when restoring a view (with the return value of
        :meth:`_get_view` as argument), such as with the navigation buttons.

        Subclasses that override :meth:`_get_view` also need to override this method
        accordingly.
        """
        self.set(**view)

    def _prepare_view_from_bbox(self, bbox, direction='in',
                                mode=None, twinx=False, twiny=False):
        """
        Helper function to prepare the new bounds from a bbox.

        This helper function returns the new x and y bounds from the zoom
        bbox. This a convenience method to abstract the bbox logic
        out of the base setter.
        """
        if len(bbox) == 3:
            xp, yp, scl = bbox  # Zooming code
            if scl == 0:  # Should not happen
                scl = 1.
            if scl > 1:
                direction = 'in'
            else:
                direction = 'out'
                scl = 1/scl
            # get the limits of the axes
            (xmin, ymin), (xmax, ymax) = self.transData.transform(
                np.transpose([self.get_xlim(), self.get_ylim()]))
            # set the range
            xwidth = xmax - xmin
            ywidth = ymax - ymin
            xcen = (xmax + xmin)*.5
            ycen = (ymax + ymin)*.5
            xzc = (xp*(scl - 1) + xcen)/scl
            yzc = (yp*(scl - 1) + ycen)/scl
            bbox = [xzc - xwidth/2./scl, yzc - ywidth/2./scl,
                    xzc + xwidth/2./scl, yzc + ywidth/2./scl]
        elif len(bbox) != 4:
            # should be len 3 or 4 but nothing else
            _api.warn_external(
                "Warning in _set_view_from_bbox: bounding box is not a tuple "
                "of length 3 or 4. Ignoring the view change.")
            return

        # Original limits.
        xmin0, xmax0 = self.get_xbound()
        ymin0, ymax0 = self.get_ybound()
        # The zoom box in screen coords.
        startx, starty, stopx, stopy = bbox
        # Convert to data coords.
        (startx, starty), (stopx, stopy) = self.transData.inverted().transform(
            [(startx, starty), (stopx, stopy)])
        # Clip to axes limits.
        xmin, xmax = np.clip(sorted([startx, stopx]), xmin0, xmax0)
        ymin, ymax = np.clip(sorted([starty, stopy]), ymin0, ymax0)
        # Don't double-zoom twinned axes or if zooming only the other axis.
        if twinx or mode == "y":
            xmin, xmax = xmin0, xmax0
        if twiny or mode == "x":
            ymin, ymax = ymin0, ymax0

        if direction == "in":
            new_xbound = xmin, xmax
            new_ybound = ymin, ymax

        elif direction == "out":
            x_trf = self.xaxis.get_transform()
            sxmin0, sxmax0, sxmin, sxmax = x_trf.transform(
                [xmin0, xmax0, xmin, xmax])  # To screen space.
            factor = (sxmax0 - sxmin0) / (sxmax - sxmin)  # Unzoom factor.
            # Move original bounds away by
            # (factor) x (distance between unzoom box and Axes bbox).
            sxmin1 = sxmin0 - factor * (sxmin - sxmin0)
            sxmax1 = sxmax0 + factor * (sxmax0 - sxmax)
            # And back to data space.
            new_xbound = x_trf.inverted().transform([sxmin1, sxmax1])

            y_trf = self.yaxis.get_transform()
            symin0, symax0, symin, symax = y_trf.transform(
                [ymin0, ymax0, ymin, ymax])
            factor = (symax0 - symin0) / (symax - symin)
            symin1 = symin0 - factor * (symin - symin0)
            symax1 = symax0 + factor * (symax0 - symax)
            new_ybound = y_trf.inverted().transform([symin1, symax1])

        return new_xbound, new_ybound

    def _set_view_from_bbox(self, bbox, direction='in',
                            mode=None, twinx=False, twiny=False):
        """
        Update view from a selection bbox.

        .. note::

            Intended to be overridden by new projection types, but if not, the
            default implementation sets the view limits to the bbox directly.

        Parameters
        ----------
        bbox : 4-tuple or 3 tuple
            * If bbox is a 4 tuple, it is the selected bounding box limits,
              in *display* coordinates.
            * If bbox is a 3 tuple, it is an (xp, yp, scl) triple, where
              (xp, yp) is the center of zooming and scl the scale factor to
              zoom by.

        direction : str
            The direction to apply the bounding box.
                * `'in'` - The bounding box describes the view directly, i.e.,
                           it zooms in.
                * `'out'` - The bounding box describes the size to make the
                            existing view, i.e., it zooms out.

        mode : str or None
            The selection mode, whether to apply the bounding box in only the
            `'x'` direction, `'y'` direction or both (`None`).

        twinx : bool
            Whether this axis is twinned in the *x*-direction.

        twiny : bool
            Whether this axis is twinned in the *y*-direction.
        """
        new_xbound, new_ybound = self._prepare_view_from_bbox(
            bbox, direction=direction, mode=mode, twinx=twinx, twiny=twiny)
        if not twinx and mode != "y":
            self.set_xbound(new_xbound)
            self.set_autoscalex_on(False)
        if not twiny and mode != "x":
            self.set_ybound(new_ybound)
            self.set_autoscaley_on(False)

    def start_pan(self, x, y, button):
        """
        Called when a pan operation has started.

        Parameters
        ----------
        x, y : float
            The mouse coordinates in display coords.
        button : `.MouseButton`
            The pressed mouse button.

        Notes
        -----
        This is intended to be overridden by new projection types.
        """
        self._pan_start = types.SimpleNamespace(
            lim=self.viewLim.frozen(),
            trans=self.transData.frozen(),
            trans_inverse=self.transData.inverted().frozen(),
            bbox=self.bbox.frozen(),
            x=x,
            y=y)

    def end_pan(self):
        """
        Called when a pan operation completes (when the mouse button is up.)

        Notes
        -----
        This is intended to be overridden by new projection types.
        """
        del self._pan_start

    def _get_pan_points(self, button, key, x, y):
        """
        Helper function to return the new points after a pan.

        This helper function returns the points on the axis after a pan has
        occurred. This is a convenience method to abstract the pan logic
        out of the base setter.
        """
        def format_deltas(key, dx, dy):
            if key == 'control':
                if abs(dx) > abs(dy):
                    dy = dx
                else:
                    dx = dy
            elif key == 'x':
                dy = 0
            elif key == 'y':
                dx = 0
            elif key == 'shift':
                if 2 * abs(dx) < abs(dy):
                    dx = 0
                elif 2 * abs(dy) < abs(dx):
                    dy = 0
                elif abs(dx) > abs(dy):
                    dy = dy / abs(dy) * abs(dx)
                else:
                    dx = dx / abs(dx) * abs(dy)
            return dx, dy

        p = self._pan_start
        dx = x - p.x
        dy = y - p.y
        if dx == dy == 0:
            return
        if button == 1:
            dx, dy = format_deltas(key, dx, dy)
            result = p.bbox.translated(-dx, -dy).transformed(p.trans_inverse)
        elif button == 3:
            try:
                dx = -dx / self.bbox.width
                dy = -dy / self.bbox.height
                dx, dy = format_deltas(key, dx, dy)
                if self.get_aspect() != 'auto':
                    dx = dy = 0.5 * (dx + dy)
                alpha = np.power(10.0, (dx, dy))
                start = np.array([p.x, p.y])
                oldpoints = p.lim.transformed(p.trans)
                newpoints = start + alpha * (oldpoints - start)
                result = (mtransforms.Bbox(newpoints)
                          .transformed(p.trans_inverse))
            except OverflowError:
                _api.warn_external('Overflow while panning')
                return
        else:
            return

        valid = np.isfinite(result.transformed(p.trans))
        points = result.get_points().astype(object)
        # Just ignore invalid limits (typically, underflow in log-scale).
        points[~valid] = None
        return points

    def drag_pan(self, button, key, x, y):
        """
        Called when the mouse moves during a pan operation.

        Parameters
        ----------
        button : `.MouseButton`
            The pressed mouse button.
        key : str or None
            The pressed key, if any.
        x, y : float
            The mouse coordinates in display coords.

        Notes
        -----
        This is intended to be overridden by new projection types.
        """
        points = self._get_pan_points(button, key, x, y)
        if points is not None:
            self.set_xlim(points[:, 0])
            self.set_ylim(points[:, 1])

    def get_children(self):
        # docstring inherited.
        return [
            *self._children,
            *self.spines.values(),
            *self._axis_map.values(),
            self.title, self._left_title, self._right_title,
            *self.child_axes,
            *([self.legend_] if self.legend_ is not None else []),
            self.patch,
        ]

    def contains(self, mouseevent):
        # docstring inherited.
        return self.patch.contains(mouseevent)

    def contains_point(self, point):
        """
        Return whether *point* (pair of pixel coordinates) is inside the Axes
        patch.
        """
        return self.patch.contains_point(point, radius=1.0)

    def get_default_bbox_extra_artists(self):
        """
        Return a default list of artists that are used for the bounding box
        calculation.

        Artists are excluded either by not being visible or
        ``artist.set_in_layout(False)``.
        """

        artists = self.get_children()

        for axis in self._axis_map.values():
            # axis tight bboxes are calculated separately inside
            # Axes.get_tightbbox() using for_layout_only=True
            artists.remove(axis)
        if not (self.axison and self._frameon):
            # don't do bbox on spines if frame not on.
            for spine in self.spines.values():
                artists.remove(spine)

        artists.remove(self.title)
        artists.remove(self._left_title)
        artists.remove(self._right_title)

        # always include types that do not internally implement clipping
        # to Axes. may have clip_on set to True and clip_box equivalent
        # to ax.bbox but then ignore these properties during draws.
        noclip = (_AxesBase, maxis.Axis,
                  offsetbox.AnnotationBbox, offsetbox.OffsetBox)
        return [a for a in artists if a.get_visible() and a.get_in_layout()
                and (isinstance(a, noclip) or not a._fully_clipped_to_axes())]

    def get_tightbbox(self, renderer=None, *, call_axes_locator=True,
                      bbox_extra_artists=None, for_layout_only=False):
        """
        Return the tight bounding box of the Axes, including axis and their
        decorators (xlabel, title, etc).

        Artists that have ``artist.set_in_layout(False)`` are not included
        in the bbox.

        Parameters
        ----------
        renderer : `.RendererBase` subclass
            renderer that will be used to draw the figures (i.e.
            ``fig.canvas.get_renderer()``)

        bbox_extra_artists : list of `.Artist` or ``None``
            List of artists to include in the tight bounding box.  If
            ``None`` (default), then all artist children of the Axes are
            included in the tight bounding box.

        call_axes_locator : bool, default: True
            If *call_axes_locator* is ``False``, it does not call the
            ``_axes_locator`` attribute, which is necessary to get the correct
            bounding box. ``call_axes_locator=False`` can be used if the
            caller is only interested in the relative size of the tightbbox
            compared to the Axes bbox.

        for_layout_only : default: False
            The bounding box will *not* include the x-extent of the title and
            the xlabel, or the y-extent of the ylabel.

        Returns
        -------
        `.BboxBase`
            Bounding box in figure pixel coordinates.

        See Also
        --------
        matplotlib.axes.Axes.get_window_extent
        matplotlib.axis.Axis.get_tightbbox
        matplotlib.spines.Spine.get_window_extent
        """

        bb = []
        if renderer is None:
            renderer = self.get_figure(root=True)._get_renderer()

        if not self.get_visible():
            return None

        locator = self.get_axes_locator()
        self.apply_aspect(
            locator(self, renderer) if locator and call_axes_locator else None)

        for axis in self._axis_map.values():
            if self.axison and axis.get_visible():
                ba = martist._get_tightbbox_for_layout_only(axis, renderer)
                if ba:
                    bb.append(ba)
        self._update_title_position(renderer)
        axbbox = self.get_window_extent(renderer)
        bb.append(axbbox)

        for title in [self.title, self._left_title, self._right_title]:
            if title.get_visible():
                bt = title.get_window_extent(renderer)
                if for_layout_only and bt.width > 0:
                    # make the title bbox 1 pixel wide so its width
                    # is not accounted for in bbox calculations in
                    # tight/constrained_layout
                    bt.x0 = (bt.x0 + bt.x1) / 2 - 0.5
                    bt.x1 = bt.x0 + 1.0
                bb.append(bt)

        bbox_artists = bbox_extra_artists
        if bbox_artists is None:
            bbox_artists = self.get_default_bbox_extra_artists()

        for a in bbox_artists:
            bbox = a.get_tightbbox(renderer)
            if (bbox is not None
                    and 0 < bbox.width < np.inf
                    and 0 < bbox.height < np.inf):
                bb.append(bbox)
        return mtransforms.Bbox.union(
            [b for b in bb if b.width != 0 or b.height != 0])

    def _make_twin_axes(self, *args, **kwargs):
        """Make a twinx Axes of self. This is used for twinx and twiny."""
        if 'sharex' in kwargs and 'sharey' in kwargs:
            # The following line is added in v2.2 to avoid breaking Seaborn,
            # which currently uses this internal API.
            if kwargs["sharex"] is not self and kwargs["sharey"] is not self:
                raise ValueError("Twinned Axes may share only one axis")
        ss = self.get_subplotspec()
        if ss:
            twin = self.get_figure(root=False).add_subplot(ss, *args, **kwargs)
        else:
            twin = self.get_figure(root=False).add_axes(
                self.get_position(True), *args, **kwargs,
                axes_locator=_TransformedBoundsLocator(
                    [0, 0, 1, 1], self.transAxes))
        self.set_adjustable('datalim')
        twin.set_adjustable('datalim')
        twin.set_zorder(self.zorder)

        self._twinned_axes.join(self, twin)
        return twin

    def twinx(self):
        """
        Create a twin Axes sharing the xaxis.

        Create a new Axes with an invisible x-axis and an independent
        y-axis positioned opposite to the original one (i.e. at right). The
        x-axis autoscale setting will be inherited from the original
        Axes.  To ensure that the tick marks of both y-axes align, see
        `~matplotlib.ticker.LinearLocator`.

        Returns
        -------
        Axes
            The newly created Axes instance

        Notes
        -----
        For those who are 'picking' artists while using twinx, pick
        events are only called for the artists in the top-most Axes.
        """
        ax2 = self._make_twin_axes(sharex=self)
        ax2.yaxis.tick_right()
        ax2.yaxis.set_label_position('right')
        ax2.yaxis.set_offset_position('right')
        ax2.set_autoscalex_on(self.get_autoscalex_on())
        self.yaxis.tick_left()
        ax2.xaxis.set_visible(False)
        ax2.patch.set_visible(False)
        ax2.xaxis.units = self.xaxis.units
        return ax2

    def twiny(self):
        """
        Create a twin Axes sharing the yaxis.

        Create a new Axes with an invisible y-axis and an independent
        x-axis positioned opposite to the original one (i.e. at top). The
        y-axis autoscale setting will be inherited from the original Axes.
        To ensure that the tick marks of both x-axes align, see
        `~matplotlib.ticker.LinearLocator`.

        Returns
        -------
        Axes
            The newly created Axes instance

        Notes
        -----
        For those who are 'picking' artists while using twiny, pick
        events are only called for the artists in the top-most Axes.
        """
        ax2 = self._make_twin_axes(sharey=self)
        ax2.xaxis.tick_top()
        ax2.xaxis.set_label_position('top')
        ax2.set_autoscaley_on(self.get_autoscaley_on())
        self.xaxis.tick_bottom()
        ax2.yaxis.set_visible(False)
        ax2.patch.set_visible(False)
        ax2.yaxis.units = self.yaxis.units
        return ax2

    def get_shared_x_axes(self):
        """Return an immutable view on the shared x-axes Grouper."""
        return cbook.GrouperView(self._shared_axes["x"])

    def get_shared_y_axes(self):
        """Return an immutable view on the shared y-axes Grouper."""
        return cbook.GrouperView(self._shared_axes["y"])

    def label_outer(self, remove_inner_ticks=False):
        """
        Only show "outer" labels and tick labels.

        x-labels are only kept for subplots on the last row (or first row, if
        labels are on the top side); y-labels only for subplots on the first
        column (or last column, if labels are on the right side).

        Parameters
        ----------
        remove_inner_ticks : bool, default: False
            If True, remove the inner ticks as well (not only tick labels).

            .. versionadded:: 3.8
        """
        self._label_outer_xaxis(skip_non_rectangular_axes=False,
                                remove_inner_ticks=remove_inner_ticks)
        self._label_outer_yaxis(skip_non_rectangular_axes=False,
                                remove_inner_ticks=remove_inner_ticks)

    def _get_subplotspec_with_optional_colorbar(self):
        """
        Return the subplotspec for this Axes, except that if this Axes has been
        moved to a subgridspec to make room for a colorbar, then return the
        subplotspec that encloses both this Axes and the colorbar Axes.
        """
        ss = self.get_subplotspec()
        if any(cax.get_subplotspec() for cax in self._colorbars):
            ss = ss.get_gridspec()._subplot_spec
        return ss

    def _label_outer_xaxis(self, *, skip_non_rectangular_axes,
                           remove_inner_ticks=False):
        # see documentation in label_outer.
        if skip_non_rectangular_axes and not isinstance(self.patch,
                                                        mpl.patches.Rectangle):
            return
        ss = self._get_subplotspec_with_optional_colorbar()
        if ss is None:
            return
        label_position = self.xaxis.get_label_position()
        if not ss.is_first_row():  # Remove top label/ticklabels/offsettext.
            if label_position == "top":
                self.set_xlabel("")
            top_kw = {'top': False} if remove_inner_ticks else {}
            self.xaxis.set_tick_params(
                which="both", labeltop=False, **top_kw)
            if self.xaxis.offsetText.get_position()[1] == 1:
                self.xaxis.offsetText.set_visible(False)
        if not ss.is_last_row():  # Remove bottom label/ticklabels/offsettext.
            if label_position == "bottom":
                self.set_xlabel("")
            bottom_kw = {'bottom': False} if remove_inner_ticks else {}
            self.xaxis.set_tick_params(
                which="both", labelbottom=False, **bottom_kw)
            if self.xaxis.offsetText.get_position()[1] == 0:
                self.xaxis.offsetText.set_visible(False)

    def _label_outer_yaxis(self, *, skip_non_rectangular_axes,
                           remove_inner_ticks=False):
        # see documentation in label_outer.
        if skip_non_rectangular_axes and not isinstance(self.patch,
                                                        mpl.patches.Rectangle):
            return
        ss = self._get_subplotspec_with_optional_colorbar()
        if ss is None:
            return
        label_position = self.yaxis.get_label_position()
        if not ss.is_first_col():  # Remove left label/ticklabels/offsettext.
            if label_position == "left":
                self.set_ylabel("")
            left_kw = {'left': False} if remove_inner_ticks else {}
            self.yaxis.set_tick_params(
                which="both", labelleft=False, **left_kw)
            if self.yaxis.offsetText.get_position()[0] == 0:
                self.yaxis.offsetText.set_visible(False)
        if not ss.is_last_col():  # Remove right label/ticklabels/offsettext.
            if label_position == "right":
                self.set_ylabel("")
            right_kw = {'right': False} if remove_inner_ticks else {}
            self.yaxis.set_tick_params(
                which="both", labelright=False, **right_kw)
            if self.yaxis.offsetText.get_position()[0] == 1:
                self.yaxis.offsetText.set_visible(False)

    def set_forward_navigation_events(self, forward):
        """
        Set how pan/zoom events are forwarded to Axes below this one.

        Parameters
        ----------
        forward : bool or "auto"
            Possible values:

            - True: Forward events to other axes with lower or equal zorder.
            - False: Events are only executed on this axes.
            - "auto": Default behaviour (*True* for axes with an invisible
              patch and *False* otherwise)

        See Also
        --------
        matplotlib.axes.Axes.set_navigate

        """
        self._forward_navigation_events = forward

    def get_forward_navigation_events(self):
        """Get how pan/zoom events are forwarded to Axes below this one."""
        return self._forward_navigation_events


def _draw_rasterized(figure, artists, renderer):
    """
    A helper function for rasterizing the list of artists.

    The bookkeeping to track if we are or are not in rasterizing mode
    with the mixed-mode backends is relatively complicated and is now
    handled in the matplotlib.artist.allow_rasterization decorator.

    This helper defines the absolute minimum methods and attributes on a
    shim class to be compatible with that decorator and then uses it to
    rasterize the list of artists.

    This is maybe too-clever, but allows us to reuse the same code that is
    used on normal artists to participate in the "are we rasterizing"
    accounting.

    Please do not use this outside of the "rasterize below a given zorder"
    functionality of Axes.

    Parameters
    ----------
    figure : matplotlib.figure.Figure
        The figure all of the artists belong to (not checked).  We need this
        because we can at the figure level suppress composition and insert each
        rasterized artist as its own image.

    artists : List[matplotlib.artist.Artist]
        The list of Artists to be rasterized.  These are assumed to all
        be in the same Figure.

    renderer : matplotlib.backendbases.RendererBase
        The currently active renderer

    Returns
    -------
    None

    """
    class _MinimalArtist:
        def get_rasterized(self):
            return True

        def get_agg_filter(self):
            return None

        def __init__(self, figure, artists):
            self.figure = figure
            self.artists = artists

        def get_figure(self, root=False):
            if root:
                return self.figure.get_figure(root=True)
            else:
                return self.figure

        @martist.allow_rasterization
        def draw(self, renderer):
            for a in self.artists:
                a.draw(renderer)

    return _MinimalArtist(figure, artists).draw(renderer)
