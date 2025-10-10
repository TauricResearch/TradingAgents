"""Utility functions, mostly for internal use."""
import os
import inspect
import warnings
import colorsys
from contextlib import contextmanager
from urllib.request import urlopen, urlretrieve
from types import ModuleType

import numpy as np
import pandas as pd
import matplotlib as mpl
from matplotlib.colors import to_rgb
import matplotlib.pyplot as plt
from matplotlib.cbook import normalize_kwargs

from seaborn._core.typing import deprecated
from seaborn.external.version import Version
from seaborn.external.appdirs import user_cache_dir

__all__ = ["desaturate", "saturate", "set_hls_values", "move_legend",
           "despine", "get_dataset_names", "get_data_home", "load_dataset"]

DATASET_SOURCE = "https://raw.githubusercontent.com/mwaskom/seaborn-data/master"
DATASET_NAMES_URL = f"{DATASET_SOURCE}/dataset_names.txt"


def ci_to_errsize(cis, heights):
    """Convert intervals to error arguments relative to plot heights.

    Parameters
    ----------
    cis : 2 x n sequence
        sequence of confidence interval limits
    heights : n sequence
        sequence of plot heights

    Returns
    -------
    errsize : 2 x n array
        sequence of error size relative to height values in correct
        format as argument for plt.bar

    """
    cis = np.atleast_2d(cis).reshape(2, -1)
    heights = np.atleast_1d(heights)
    errsize = []
    for i, (low, high) in enumerate(np.transpose(cis)):
        h = heights[i]
        elow = h - low
        ehigh = high - h
        errsize.append([elow, ehigh])

    errsize = np.asarray(errsize).T
    return errsize


def _draw_figure(fig):
    """Force draw of a matplotlib figure, accounting for back-compat."""
    # See https://github.com/matplotlib/matplotlib/issues/19197 for context
    fig.canvas.draw()
    if fig.stale:
        try:
            fig.draw(fig.canvas.get_renderer())
        except AttributeError:
            pass


def _default_color(method, hue, color, kws, saturation=1):
    """If needed, get a default color by using the matplotlib property cycle."""

    if hue is not None:
        # This warning is probably user-friendly, but it's currently triggered
        # in a FacetGrid context and I don't want to mess with that logic right now
        #  if color is not None:
        #      msg = "`color` is ignored when `hue` is assigned."
        #      warnings.warn(msg)
        return None

    kws = kws.copy()
    kws.pop("label", None)

    if color is not None:
        if saturation < 1:
            color = desaturate(color, saturation)
        return color

    elif method.__name__ == "plot":

        color = normalize_kwargs(kws, mpl.lines.Line2D).get("color")
        scout, = method([], [], scalex=False, scaley=False, color=color)
        color = scout.get_color()
        scout.remove()

    elif method.__name__ == "scatter":

        # Matplotlib will raise if the size of x/y don't match s/c,
        # and the latter might be in the kws dict
        scout_size = max(
            np.atleast_1d(kws.get(key, [])).shape[0]
            for key in ["s", "c", "fc", "facecolor", "facecolors"]
        )
        scout_x = scout_y = np.full(scout_size, np.nan)

        scout = method(scout_x, scout_y, **kws)
        facecolors = scout.get_facecolors()

        if not len(facecolors):
            # Handle bug in matplotlib <= 3.2 (I think)
            # This will limit the ability to use non color= kwargs to specify
            # a color in versions of matplotlib with the bug, but trying to
            # work out what the user wanted by re-implementing the broken logic
            # of inspecting the kwargs is probably too brittle.
            single_color = False
        else:
            single_color = np.unique(facecolors, axis=0).shape[0] == 1

        # Allow the user to specify an array of colors through various kwargs
        if "c" not in kws and single_color:
            color = to_rgb(facecolors[0])

        scout.remove()

    elif method.__name__ == "bar":

        # bar() needs masked, not empty data, to generate a patch
        scout, = method([np.nan], [np.nan], **kws)
        color = to_rgb(scout.get_facecolor())
        scout.remove()
        # Axes.bar adds both a patch and a container
        method.__self__.containers.pop(-1)

    elif method.__name__ == "fill_between":

        kws = normalize_kwargs(kws, mpl.collections.PolyCollection)
        scout = method([], [], **kws)
        facecolor = scout.get_facecolor()
        color = to_rgb(facecolor[0])
        scout.remove()

    if saturation < 1:
        color = desaturate(color, saturation)

    return color


def desaturate(color, prop):
    """Decrease the saturation channel of a color by some percent.

    Parameters
    ----------
    color : matplotlib color
        hex, rgb-tuple, or html color name
    prop : float
        saturation channel of color will be multiplied by this value

    Returns
    -------
    new_color : rgb tuple
        desaturated color code in RGB tuple representation

    """
    # Check inputs
    if not 0 <= prop <= 1:
        raise ValueError("prop must be between 0 and 1")

    # Get rgb tuple rep
    rgb = to_rgb(color)

    # Short circuit to avoid floating point issues
    if prop == 1:
        return rgb

    # Convert to hls
    h, l, s = colorsys.rgb_to_hls(*rgb)

    # Desaturate the saturation channel
    s *= prop

    # Convert back to rgb
    new_color = colorsys.hls_to_rgb(h, l, s)

    return new_color


def saturate(color):
    """Return a fully saturated color with the same hue.

    Parameters
    ----------
    color : matplotlib color
        hex, rgb-tuple, or html color name

    Returns
    -------
    new_color : rgb tuple
        saturated color code in RGB tuple representation

    """
    return set_hls_values(color, s=1)


def set_hls_values(color, h=None, l=None, s=None):  # noqa
    """Independently manipulate the h, l, or s channels of a color.

    Parameters
    ----------
    color : matplotlib color
        hex, rgb-tuple, or html color name
    h, l, s : floats between 0 and 1, or None
        new values for each channel in hls space

    Returns
    -------
    new_color : rgb tuple
        new color code in RGB tuple representation

    """
    # Get an RGB tuple representation
    rgb = to_rgb(color)
    vals = list(colorsys.rgb_to_hls(*rgb))
    for i, val in enumerate([h, l, s]):
        if val is not None:
            vals[i] = val

    rgb = colorsys.hls_to_rgb(*vals)
    return rgb


def axlabel(xlabel, ylabel, **kwargs):
    """Grab current axis and label it.

    DEPRECATED: will be removed in a future version.

    """
    msg = "This function is deprecated and will be removed in a future version"
    warnings.warn(msg, FutureWarning)
    ax = plt.gca()
    ax.set_xlabel(xlabel, **kwargs)
    ax.set_ylabel(ylabel, **kwargs)


def remove_na(vector):
    """Helper method for removing null values from data vectors.

    Parameters
    ----------
    vector : vector object
        Must implement boolean masking with [] subscript syntax.

    Returns
    -------
    clean_clean : same type as ``vector``
        Vector of data with null values removed. May be a copy or a view.

    """
    return vector[pd.notnull(vector)]


def get_color_cycle():
    """Return the list of colors in the current matplotlib color cycle

    Parameters
    ----------
    None

    Returns
    -------
    colors : list
        List of matplotlib colors in the current cycle, or dark gray if
        the current color cycle is empty.
    """
    cycler = mpl.rcParams['axes.prop_cycle']
    return cycler.by_key()['color'] if 'color' in cycler.keys else [".15"]


def despine(fig=None, ax=None, top=True, right=True, left=False,
            bottom=False, offset=None, trim=False):
    """Remove the top and right spines from plot(s).

    fig : matplotlib figure, optional
        Figure to despine all axes of, defaults to the current figure.
    ax : matplotlib axes, optional
        Specific axes object to despine. Ignored if fig is provided.
    top, right, left, bottom : boolean, optional
        If True, remove that spine.
    offset : int or dict, optional
        Absolute distance, in points, spines should be moved away
        from the axes (negative values move spines inward). A single value
        applies to all spines; a dict can be used to set offset values per
        side.
    trim : bool, optional
        If True, limit spines to the smallest and largest major tick
        on each non-despined axis.

    Returns
    -------
    None

    """
    # Get references to the axes we want
    if fig is None and ax is None:
        axes = plt.gcf().axes
    elif fig is not None:
        axes = fig.axes
    elif ax is not None:
        axes = [ax]

    for ax_i in axes:
        for side in ["top", "right", "left", "bottom"]:
            # Toggle the spine objects
            is_visible = not locals()[side]
            ax_i.spines[side].set_visible(is_visible)
            if offset is not None and is_visible:
                try:
                    val = offset.get(side, 0)
                except AttributeError:
                    val = offset
                ax_i.spines[side].set_position(('outward', val))

        # Potentially move the ticks
        if left and not right:
            maj_on = any(
                t.tick1line.get_visible()
                for t in ax_i.yaxis.majorTicks
            )
            min_on = any(
                t.tick1line.get_visible()
                for t in ax_i.yaxis.minorTicks
            )
            ax_i.yaxis.set_ticks_position("right")
            for t in ax_i.yaxis.majorTicks:
                t.tick2line.set_visible(maj_on)
            for t in ax_i.yaxis.minorTicks:
                t.tick2line.set_visible(min_on)

        if bottom and not top:
            maj_on = any(
                t.tick1line.get_visible()
                for t in ax_i.xaxis.majorTicks
            )
            min_on = any(
                t.tick1line.get_visible()
                for t in ax_i.xaxis.minorTicks
            )
            ax_i.xaxis.set_ticks_position("top")
            for t in ax_i.xaxis.majorTicks:
                t.tick2line.set_visible(maj_on)
            for t in ax_i.xaxis.minorTicks:
                t.tick2line.set_visible(min_on)

        if trim:
            # clip off the parts of the spines that extend past major ticks
            xticks = np.asarray(ax_i.get_xticks())
            if xticks.size:
                firsttick = np.compress(xticks >= min(ax_i.get_xlim()),
                                        xticks)[0]
                lasttick = np.compress(xticks <= max(ax_i.get_xlim()),
                                       xticks)[-1]
                ax_i.spines['bottom'].set_bounds(firsttick, lasttick)
                ax_i.spines['top'].set_bounds(firsttick, lasttick)
                newticks = xticks.compress(xticks <= lasttick)
                newticks = newticks.compress(newticks >= firsttick)
                ax_i.set_xticks(newticks)

            yticks = np.asarray(ax_i.get_yticks())
            if yticks.size:
                firsttick = np.compress(yticks >= min(ax_i.get_ylim()),
                                        yticks)[0]
                lasttick = np.compress(yticks <= max(ax_i.get_ylim()),
                                       yticks)[-1]
                ax_i.spines['left'].set_bounds(firsttick, lasttick)
                ax_i.spines['right'].set_bounds(firsttick, lasttick)
                newticks = yticks.compress(yticks <= lasttick)
                newticks = newticks.compress(newticks >= firsttick)
                ax_i.set_yticks(newticks)


def move_legend(obj, loc, **kwargs):
    """
    Recreate a plot's legend at a new location.

    The name is a slight misnomer. Matplotlib legends do not expose public
    control over their position parameters. So this function creates a new legend,
    copying over the data from the original object, which is then removed.

    Parameters
    ----------
    obj : the object with the plot
        This argument can be either a seaborn or matplotlib object:

        - :class:`seaborn.FacetGrid` or :class:`seaborn.PairGrid`
        - :class:`matplotlib.axes.Axes` or :class:`matplotlib.figure.Figure`

    loc : str or int
        Location argument, as in :meth:`matplotlib.axes.Axes.legend`.

    kwargs
        Other keyword arguments are passed to :meth:`matplotlib.axes.Axes.legend`.

    Examples
    --------

    .. include:: ../docstrings/move_legend.rst

    """
    # This is a somewhat hackish solution that will hopefully be obviated by
    # upstream improvements to matplotlib legends that make them easier to
    # modify after creation.

    from seaborn.axisgrid import Grid  # Avoid circular import

    # Locate the legend object and a method to recreate the legend
    if isinstance(obj, Grid):
        old_legend = obj.legend
        legend_func = obj.figure.legend
    elif isinstance(obj, mpl.axes.Axes):
        old_legend = obj.legend_
        legend_func = obj.legend
    elif isinstance(obj, mpl.figure.Figure):
        if obj.legends:
            old_legend = obj.legends[-1]
        else:
            old_legend = None
        legend_func = obj.legend
    else:
        err = "`obj` must be a seaborn Grid or matplotlib Axes or Figure instance."
        raise TypeError(err)

    if old_legend is None:
        err = f"{obj} has no legend attached."
        raise ValueError(err)

    # Extract the components of the legend we need to reuse
    # Import here to avoid a circular import
    from seaborn._compat import get_legend_handles
    handles = get_legend_handles(old_legend)
    labels = [t.get_text() for t in old_legend.get_texts()]

    # Handle the case where the user is trying to override the labels
    if (new_labels := kwargs.pop("labels", None)) is not None:
        if len(new_labels) != len(labels):
            err = "Length of new labels does not match existing legend."
            raise ValueError(err)
        labels = new_labels

    # Extract legend properties that can be passed to the recreation method
    # (Vexingly, these don't all round-trip)
    legend_kws = inspect.signature(mpl.legend.Legend).parameters
    props = {k: v for k, v in old_legend.properties().items() if k in legend_kws}

    # Delegate default bbox_to_anchor rules to matplotlib
    props.pop("bbox_to_anchor")

    # Try to propagate the existing title and font properties; respect new ones too
    title = props.pop("title")
    if "title" in kwargs:
        title.set_text(kwargs.pop("title"))
    title_kwargs = {k: v for k, v in kwargs.items() if k.startswith("title_")}
    for key, val in title_kwargs.items():
        title.set(**{key[6:]: val})
        kwargs.pop(key)

    # Try to respect the frame visibility
    kwargs.setdefault("frameon", old_legend.legendPatch.get_visible())

    # Remove the old legend and create the new one
    props.update(kwargs)
    old_legend.remove()
    new_legend = legend_func(handles, labels, loc=loc, **props)
    new_legend.set_title(title.get_text(), title.get_fontproperties())

    # Let the Grid object continue to track the correct legend object
    if isinstance(obj, Grid):
        obj._legend = new_legend


def _kde_support(data, bw, gridsize, cut, clip):
    """Establish support for a kernel density estimate."""
    support_min = max(data.min() - bw * cut, clip[0])
    support_max = min(data.max() + bw * cut, clip[1])
    support = np.linspace(support_min, support_max, gridsize)

    return support


def ci(a, which=95, axis=None):
    """Return a percentile range from an array of values."""
    p = 50 - which / 2, 50 + which / 2
    return np.nanpercentile(a, p, axis)


def get_dataset_names():
    """Report available example datasets, useful for reporting issues.

    Requires an internet connection.

    """
    with urlopen(DATASET_NAMES_URL) as resp:
        txt = resp.read()

    dataset_names = [name.strip() for name in txt.decode().split("\n")]
    return list(filter(None, dataset_names))


def get_data_home(data_home=None):
    """Return a path to the cache directory for example datasets.

    This directory is used by :func:`load_dataset`.

    If the ``data_home`` argument is not provided, it will use a directory
    specified by the `SEABORN_DATA` environment variable (if it exists)
    or otherwise default to an OS-appropriate user cache location.

    """
    if data_home is None:
        data_home = os.environ.get("SEABORN_DATA", user_cache_dir("seaborn"))
    data_home = os.path.expanduser(data_home)
    if not os.path.exists(data_home):
        os.makedirs(data_home)
    return data_home


def load_dataset(name, cache=True, data_home=None, **kws):
    """Load an example dataset from the online repository (requires internet).

    This function provides quick access to a small number of example datasets
    that are useful for documenting seaborn or generating reproducible examples
    for bug reports. It is not necessary for normal usage.

    Note that some of the datasets have a small amount of preprocessing applied
    to define a proper ordering for categorical variables.

    Use :func:`get_dataset_names` to see a list of available datasets.

    Parameters
    ----------
    name : str
        Name of the dataset (``{name}.csv`` on
        https://github.com/mwaskom/seaborn-data).
    cache : boolean, optional
        If True, try to load from the local cache first, and save to the cache
        if a download is required.
    data_home : string, optional
        The directory in which to cache data; see :func:`get_data_home`.
    kws : keys and values, optional
        Additional keyword arguments are passed to passed through to
        :func:`pandas.read_csv`.

    Returns
    -------
    df : :class:`pandas.DataFrame`
        Tabular data, possibly with some preprocessing applied.

    """
    # A common beginner mistake is to assume that one's personal data needs
    # to be passed through this function to be usable with seaborn.
    # Let's provide a more helpful error than you would otherwise get.
    if isinstance(name, pd.DataFrame):
        err = (
            "This function accepts only strings (the name of an example dataset). "
            "You passed a pandas DataFrame. If you have your own dataset, "
            "it is not necessary to use this function before plotting."
        )
        raise TypeError(err)

    url = f"{DATASET_SOURCE}/{name}.csv"

    if cache:
        cache_path = os.path.join(get_data_home(data_home), os.path.basename(url))
        if not os.path.exists(cache_path):
            if name not in get_dataset_names():
                raise ValueError(f"'{name}' is not one of the example datasets.")
            urlretrieve(url, cache_path)
        full_path = cache_path
    else:
        full_path = url

    df = pd.read_csv(full_path, **kws)

    if df.iloc[-1].isnull().all():
        df = df.iloc[:-1]

    # Set some columns as a categorical type with ordered levels

    if name == "tips":
        df["day"] = pd.Categorical(df["day"], ["Thur", "Fri", "Sat", "Sun"])
        df["sex"] = pd.Categorical(df["sex"], ["Male", "Female"])
        df["time"] = pd.Categorical(df["time"], ["Lunch", "Dinner"])
        df["smoker"] = pd.Categorical(df["smoker"], ["Yes", "No"])

    elif name == "flights":
        months = df["month"].str[:3]
        df["month"] = pd.Categorical(months, months.unique())

    elif name == "exercise":
        df["time"] = pd.Categorical(df["time"], ["1 min", "15 min", "30 min"])
        df["kind"] = pd.Categorical(df["kind"], ["rest", "walking", "running"])
        df["diet"] = pd.Categorical(df["diet"], ["no fat", "low fat"])

    elif name == "titanic":
        df["class"] = pd.Categorical(df["class"], ["First", "Second", "Third"])
        df["deck"] = pd.Categorical(df["deck"], list("ABCDEFG"))

    elif name == "penguins":
        df["sex"] = df["sex"].str.title()

    elif name == "diamonds":
        df["color"] = pd.Categorical(
            df["color"], ["D", "E", "F", "G", "H", "I", "J"],
        )
        df["clarity"] = pd.Categorical(
            df["clarity"], ["IF", "VVS1", "VVS2", "VS1", "VS2", "SI1", "SI2", "I1"],
        )
        df["cut"] = pd.Categorical(
            df["cut"], ["Ideal", "Premium", "Very Good", "Good", "Fair"],
        )

    elif name == "taxis":
        df["pickup"] = pd.to_datetime(df["pickup"])
        df["dropoff"] = pd.to_datetime(df["dropoff"])

    elif name == "seaice":
        df["Date"] = pd.to_datetime(df["Date"])

    elif name == "dowjones":
        df["Date"] = pd.to_datetime(df["Date"])

    return df


def axis_ticklabels_overlap(labels):
    """Return a boolean for whether the list of ticklabels have overlaps.

    Parameters
    ----------
    labels : list of matplotlib ticklabels

    Returns
    -------
    overlap : boolean
        True if any of the labels overlap.

    """
    if not labels:
        return False
    try:
        bboxes = [l.get_window_extent() for l in labels]
        overlaps = [b.count_overlaps(bboxes) for b in bboxes]
        return max(overlaps) > 1
    except RuntimeError:
        # Issue on macos backend raises an error in the above code
        return False


def axes_ticklabels_overlap(ax):
    """Return booleans for whether the x and y ticklabels on an Axes overlap.

    Parameters
    ----------
    ax : matplotlib Axes

    Returns
    -------
    x_overlap, y_overlap : booleans
        True when the labels on that axis overlap.

    """
    return (axis_ticklabels_overlap(ax.get_xticklabels()),
            axis_ticklabels_overlap(ax.get_yticklabels()))


def locator_to_legend_entries(locator, limits, dtype):
    """Return levels and formatted levels for brief numeric legends."""
    raw_levels = locator.tick_values(*limits).astype(dtype)

    # The locator can return ticks outside the limits, clip them here
    raw_levels = [l for l in raw_levels if l >= limits[0] and l <= limits[1]]

    class dummy_axis:
        def get_view_interval(self):
            return limits

    if isinstance(locator, mpl.ticker.LogLocator):
        formatter = mpl.ticker.LogFormatter()
    else:
        formatter = mpl.ticker.ScalarFormatter()
        # Avoid having an offset/scientific notation which we don't currently
        # have any way of representing in the legend
        formatter.set_useOffset(False)
        formatter.set_scientific(False)
    formatter.axis = dummy_axis()

    formatted_levels = formatter.format_ticks(raw_levels)

    return raw_levels, formatted_levels


def relative_luminance(color):
    """Calculate the relative luminance of a color according to W3C standards

    Parameters
    ----------
    color : matplotlib color or sequence of matplotlib colors
        Hex code, rgb-tuple, or html color name.

    Returns
    -------
    luminance : float(s) between 0 and 1

    """
    rgb = mpl.colors.colorConverter.to_rgba_array(color)[:, :3]
    rgb = np.where(rgb <= .03928, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    lum = rgb.dot([.2126, .7152, .0722])
    try:
        return lum.item()
    except ValueError:
        return lum


def to_utf8(obj):
    """Return a string representing a Python object.

    Strings (i.e. type ``str``) are returned unchanged.

    Byte strings (i.e. type ``bytes``) are returned as UTF-8-decoded strings.

    For other objects, the method ``__str__()`` is called, and the result is
    returned as a string.

    Parameters
    ----------
    obj : object
        Any Python object

    Returns
    -------
    s : str
        UTF-8-decoded string representation of ``obj``

    """
    if isinstance(obj, str):
        return obj
    try:
        return obj.decode(encoding="utf-8")
    except AttributeError:  # obj is not bytes-like
        return str(obj)


def _check_argument(param, options, value, prefix=False):
    """Raise if value for param is not in options."""
    if prefix and value is not None:
        failure = not any(value.startswith(p) for p in options if isinstance(p, str))
    else:
        failure = value not in options
    if failure:
        raise ValueError(
            f"The value for `{param}` must be one of {options}, "
            f"but {repr(value)} was passed."
        )
    return value


def _assign_default_kwargs(kws, call_func, source_func):
    """Assign default kwargs for call_func using values from source_func."""
    # This exists so that axes-level functions and figure-level functions can
    # both call a Plotter method while having the default kwargs be defined in
    # the signature of the axes-level function.
    # An alternative would be to have a decorator on the method that sets its
    # defaults based on those defined in the axes-level function.
    # Then the figure-level function would not need to worry about defaults.
    # I am not sure which is better.
    needed = inspect.signature(call_func).parameters
    defaults = inspect.signature(source_func).parameters

    for param in needed:
        if param in defaults and param not in kws:
            kws[param] = defaults[param].default

    return kws


def adjust_legend_subtitles(legend):
    """
    Make invisible-handle "subtitles" entries look more like titles.

    Note: This function is not part of the public API and may be changed or removed.

    """
    # Legend title not in rcParams until 3.0
    font_size = plt.rcParams.get("legend.title_fontsize", None)
    hpackers = legend.findobj(mpl.offsetbox.VPacker)[0].get_children()
    for hpack in hpackers:
        draw_area, text_area = hpack.get_children()
        handles = draw_area.get_children()
        if not all(artist.get_visible() for artist in handles):
            draw_area.set_width(0)
            for text in text_area.get_children():
                if font_size is not None:
                    text.set_size(font_size)


def _deprecate_ci(errorbar, ci):
    """
    Warn on usage of ci= and convert to appropriate errorbar= arg.

    ci was deprecated when errorbar was added in 0.12. It should not be removed
    completely for some time, but it can be moved out of function definitions
    (and extracted from kwargs) after one cycle.

    """
    if ci is not deprecated and ci != "deprecated":
        if ci is None:
            errorbar = None
        elif ci == "sd":
            errorbar = "sd"
        else:
            errorbar = ("ci", ci)
        msg = (
            "\n\nThe `ci` parameter is deprecated. "
            f"Use `errorbar={repr(errorbar)}` for the same effect.\n"
        )
        warnings.warn(msg, FutureWarning, stacklevel=3)

    return errorbar


def _get_transform_functions(ax, axis):
    """Return the forward and inverse transforms for a given axis."""
    axis_obj = getattr(ax, f"{axis}axis")
    transform = axis_obj.get_transform()
    return transform.transform, transform.inverted().transform


@contextmanager
def _disable_autolayout():
    """Context manager for preventing rc-controlled auto-layout behavior."""
    # This is a workaround for an issue in matplotlib, for details see
    # https://github.com/mwaskom/seaborn/issues/2914
    # The only affect of this rcParam is to set the default value for
    # layout= in plt.figure, so we could just do that instead.
    # But then we would need to own the complexity of the transition
    # from tight_layout=True -> layout="tight". This seems easier,
    # but can be removed when (if) that is simpler on the matplotlib side,
    # or if the layout algorithms are improved to handle figure legends.
    orig_val = mpl.rcParams["figure.autolayout"]
    try:
        mpl.rcParams["figure.autolayout"] = False
        yield
    finally:
        mpl.rcParams["figure.autolayout"] = orig_val


def _version_predates(lib: ModuleType, version: str) -> bool:
    """Helper function for checking version compatibility."""
    return Version(lib.__version__) < Version(version)


def _scatter_legend_artist(**kws):

    kws = normalize_kwargs(kws, mpl.collections.PathCollection)

    edgecolor = kws.pop("edgecolor", None)
    rc = mpl.rcParams
    line_kws = {
        "linestyle": "",
        "marker": kws.pop("marker", "o"),
        "markersize": np.sqrt(kws.pop("s", rc["lines.markersize"] ** 2)),
        "markerfacecolor": kws.pop("facecolor", kws.get("color")),
        "markeredgewidth": kws.pop("linewidth", 0),
        **kws,
    }

    if edgecolor is not None:
        if edgecolor == "face":
            line_kws["markeredgecolor"] = line_kws["markerfacecolor"]
        else:
            line_kws["markeredgecolor"] = edgecolor

    return mpl.lines.Line2D([], [], **line_kws)


def _get_patch_legend_artist(fill):

    def legend_artist(**kws):

        color = kws.pop("color", None)
        if color is not None:
            if fill:
                kws["facecolor"] = color
            else:
                kws["edgecolor"] = color
                kws["facecolor"] = "none"

        return mpl.patches.Rectangle((0, 0), 0, 0, **kws)

    return legend_artist
