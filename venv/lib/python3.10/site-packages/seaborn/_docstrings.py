import re
import pydoc
from .external.docscrape import NumpyDocString


class DocstringComponents:

    regexp = re.compile(r"\n((\n|.)+)\n\s*", re.MULTILINE)

    def __init__(self, comp_dict, strip_whitespace=True):
        """Read entries from a dict, optionally stripping outer whitespace."""
        if strip_whitespace:
            entries = {}
            for key, val in comp_dict.items():
                m = re.match(self.regexp, val)
                if m is None:
                    entries[key] = val
                else:
                    entries[key] = m.group(1)
        else:
            entries = comp_dict.copy()

        self.entries = entries

    def __getattr__(self, attr):
        """Provide dot access to entries for clean raw docstrings."""
        if attr in self.entries:
            return self.entries[attr]
        else:
            try:
                return self.__getattribute__(attr)
            except AttributeError as err:
                # If Python is run with -OO, it will strip docstrings and our lookup
                # from self.entries will fail. We check for __debug__, which is actually
                # set to False by -O (it is True for normal execution).
                # But we only want to see an error when building the docs;
                # not something users should see, so this slight inconsistency is fine.
                if __debug__:
                    raise err
                else:
                    pass

    @classmethod
    def from_nested_components(cls, **kwargs):
        """Add multiple sub-sets of components."""
        return cls(kwargs, strip_whitespace=False)

    @classmethod
    def from_function_params(cls, func):
        """Use the numpydoc parser to extract components from existing func."""
        params = NumpyDocString(pydoc.getdoc(func))["Parameters"]
        comp_dict = {}
        for p in params:
            name = p.name
            type = p.type
            desc = "\n    ".join(p.desc)
            comp_dict[name] = f"{name} : {type}\n    {desc}"

        return cls(comp_dict)


# TODO is "vector" the best term here? We mean to imply 1D data with a variety
# of types?

# TODO now that we can parse numpydoc style strings, do we need to define dicts
# of docstring components, or just write out a docstring?


_core_params = dict(
    data="""
data : :class:`pandas.DataFrame`, :class:`numpy.ndarray`, mapping, or sequence
    Input data structure. Either a long-form collection of vectors that can be
    assigned to named variables or a wide-form dataset that will be internally
    reshaped.
    """,  # TODO add link to user guide narrative when exists
    xy="""
x, y : vectors or keys in ``data``
    Variables that specify positions on the x and y axes.
    """,
    hue="""
hue : vector or key in ``data``
    Semantic variable that is mapped to determine the color of plot elements.
    """,
    palette="""
palette : string, list, dict, or :class:`matplotlib.colors.Colormap`
    Method for choosing the colors to use when mapping the ``hue`` semantic.
    String values are passed to :func:`color_palette`. List or dict values
    imply categorical mapping, while a colormap object implies numeric mapping.
    """,  # noqa: E501
    hue_order="""
hue_order : vector of strings
    Specify the order of processing and plotting for categorical levels of the
    ``hue`` semantic.
    """,
    hue_norm="""
hue_norm : tuple or :class:`matplotlib.colors.Normalize`
    Either a pair of values that set the normalization range in data units
    or an object that will map from data units into a [0, 1] interval. Usage
    implies numeric mapping.
    """,
    color="""
color : :mod:`matplotlib color <matplotlib.colors>`
    Single color specification for when hue mapping is not used. Otherwise, the
    plot will try to hook into the matplotlib property cycle.
    """,
    ax="""
ax : :class:`matplotlib.axes.Axes`
    Pre-existing axes for the plot. Otherwise, call :func:`matplotlib.pyplot.gca`
    internally.
    """,  # noqa: E501
)


_core_returns = dict(
    ax="""
:class:`matplotlib.axes.Axes`
    The matplotlib axes containing the plot.
    """,
    facetgrid="""
:class:`FacetGrid`
    An object managing one or more subplots that correspond to conditional data
    subsets with convenient methods for batch-setting of axes attributes.
    """,
    jointgrid="""
:class:`JointGrid`
    An object managing multiple subplots that correspond to joint and marginal axes
    for plotting a bivariate relationship or distribution.
    """,
    pairgrid="""
:class:`PairGrid`
    An object managing multiple subplots that correspond to joint and marginal axes
    for pairwise combinations of multiple variables in a dataset.
    """,
)


_seealso_blurbs = dict(

    # Relational plots
    scatterplot="""
scatterplot : Plot data using points.
    """,
    lineplot="""
lineplot : Plot data using lines.
    """,

    # Distribution plots
    displot="""
displot : Figure-level interface to distribution plot functions.
    """,
    histplot="""
histplot : Plot a histogram of binned counts with optional normalization or smoothing.
    """,
    kdeplot="""
kdeplot : Plot univariate or bivariate distributions using kernel density estimation.
    """,
    ecdfplot="""
ecdfplot : Plot empirical cumulative distribution functions.
    """,
    rugplot="""
rugplot : Plot a tick at each observation value along the x and/or y axes.
    """,

    # Categorical plots
    stripplot="""
stripplot : Plot a categorical scatter with jitter.
    """,
    swarmplot="""
swarmplot : Plot a categorical scatter with non-overlapping points.
    """,
    violinplot="""
violinplot : Draw an enhanced boxplot using kernel density estimation.
    """,
    pointplot="""
pointplot : Plot point estimates and CIs using markers and lines.
    """,

    # Multiples
    jointplot="""
jointplot : Draw a bivariate plot with univariate marginal distributions.
    """,
    pairplot="""
jointplot : Draw multiple bivariate plots with univariate marginal distributions.
    """,
    jointgrid="""
JointGrid : Set up a figure with joint and marginal views on bivariate data.
    """,
    pairgrid="""
PairGrid : Set up a figure with joint and marginal views on multiple variables.
    """,
)


_core_docs = dict(
    params=DocstringComponents(_core_params),
    returns=DocstringComponents(_core_returns),
    seealso=DocstringComponents(_seealso_blurbs),
)
