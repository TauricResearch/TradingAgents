"""Statistical transformations for visualization.

This module is currently private, but is being written to eventually form part
of the public API.

The classes should behave roughly in the style of scikit-learn.

- All data-independent parameters should be passed to the class constructor.
- Each class should implement a default transformation that is exposed through
  __call__. These are currently written for vector arguments, but I think
  consuming a whole `plot_data` DataFrame and return it with transformed
  variables would make more sense.
- Some class have data-dependent preprocessing that should be cached and used
  multiple times (think defining histogram bins off all data and then counting
  observations within each bin multiple times per data subsets). These currently
  have unique names, but it would be good to have a common name. Not quite
  `fit`, but something similar.
- Alternatively, the transform interface could take some information about grouping
  variables and do a groupby internally.
- Some classes should define alternate transforms that might make the most sense
  with a different function. For example, KDE usually evaluates the distribution
  on a regular grid, but it would be useful for it to transform at the actual
  datapoints. Then again, this could be controlled by a parameter at  the time of
  class instantiation.

"""
from numbers import Number
from statistics import NormalDist
import numpy as np
import pandas as pd
try:
    from scipy.stats import gaussian_kde
    _no_scipy = False
except ImportError:
    from .external.kde import gaussian_kde
    _no_scipy = True

from .algorithms import bootstrap
from .utils import _check_argument


class KDE:
    """Univariate and bivariate kernel density estimator."""
    def __init__(
        self, *,
        bw_method=None,
        bw_adjust=1,
        gridsize=200,
        cut=3,
        clip=None,
        cumulative=False,
    ):
        """Initialize the estimator with its parameters.

        Parameters
        ----------
        bw_method : string, scalar, or callable, optional
            Method for determining the smoothing bandwidth to use; passed to
            :class:`scipy.stats.gaussian_kde`.
        bw_adjust : number, optional
            Factor that multiplicatively scales the value chosen using
            ``bw_method``. Increasing will make the curve smoother. See Notes.
        gridsize : int, optional
            Number of points on each dimension of the evaluation grid.
        cut : number, optional
            Factor, multiplied by the smoothing bandwidth, that determines how
            far the evaluation grid extends past the extreme datapoints. When
            set to 0, truncate the curve at the data limits.
        clip : pair of numbers or None, or a pair of such pairs
            Do not evaluate the density outside of these limits.
        cumulative : bool, optional
            If True, estimate a cumulative distribution function. Requires scipy.

        """
        if clip is None:
            clip = None, None

        self.bw_method = bw_method
        self.bw_adjust = bw_adjust
        self.gridsize = gridsize
        self.cut = cut
        self.clip = clip
        self.cumulative = cumulative

        if cumulative and _no_scipy:
            raise RuntimeError("Cumulative KDE evaluation requires scipy")

        self.support = None

    def _define_support_grid(self, x, bw, cut, clip, gridsize):
        """Create the grid of evaluation points depending for vector x."""
        clip_lo = -np.inf if clip[0] is None else clip[0]
        clip_hi = +np.inf if clip[1] is None else clip[1]
        gridmin = max(x.min() - bw * cut, clip_lo)
        gridmax = min(x.max() + bw * cut, clip_hi)
        return np.linspace(gridmin, gridmax, gridsize)

    def _define_support_univariate(self, x, weights):
        """Create a 1D grid of evaluation points."""
        kde = self._fit(x, weights)
        bw = np.sqrt(kde.covariance.squeeze())
        grid = self._define_support_grid(
            x, bw, self.cut, self.clip, self.gridsize
        )
        return grid

    def _define_support_bivariate(self, x1, x2, weights):
        """Create a 2D grid of evaluation points."""
        clip = self.clip
        if clip[0] is None or np.isscalar(clip[0]):
            clip = (clip, clip)

        kde = self._fit([x1, x2], weights)
        bw = np.sqrt(np.diag(kde.covariance).squeeze())

        grid1 = self._define_support_grid(
            x1, bw[0], self.cut, clip[0], self.gridsize
        )
        grid2 = self._define_support_grid(
            x2, bw[1], self.cut, clip[1], self.gridsize
        )

        return grid1, grid2

    def define_support(self, x1, x2=None, weights=None, cache=True):
        """Create the evaluation grid for a given data set."""
        if x2 is None:
            support = self._define_support_univariate(x1, weights)
        else:
            support = self._define_support_bivariate(x1, x2, weights)

        if cache:
            self.support = support

        return support

    def _fit(self, fit_data, weights=None):
        """Fit the scipy kde while adding bw_adjust logic and version check."""
        fit_kws = {"bw_method": self.bw_method}
        if weights is not None:
            fit_kws["weights"] = weights

        kde = gaussian_kde(fit_data, **fit_kws)
        kde.set_bandwidth(kde.factor * self.bw_adjust)

        return kde

    def _eval_univariate(self, x, weights=None):
        """Fit and evaluate a univariate on univariate data."""
        support = self.support
        if support is None:
            support = self.define_support(x, cache=False)

        kde = self._fit(x, weights)

        if self.cumulative:
            s_0 = support[0]
            density = np.array([
                kde.integrate_box_1d(s_0, s_i) for s_i in support
            ])
        else:
            density = kde(support)

        return density, support

    def _eval_bivariate(self, x1, x2, weights=None):
        """Fit and evaluate a univariate on bivariate data."""
        support = self.support
        if support is None:
            support = self.define_support(x1, x2, cache=False)

        kde = self._fit([x1, x2], weights)

        if self.cumulative:

            grid1, grid2 = support
            density = np.zeros((grid1.size, grid2.size))
            p0 = grid1.min(), grid2.min()
            for i, xi in enumerate(grid1):
                for j, xj in enumerate(grid2):
                    density[i, j] = kde.integrate_box(p0, (xi, xj))

        else:

            xx1, xx2 = np.meshgrid(*support)
            density = kde([xx1.ravel(), xx2.ravel()]).reshape(xx1.shape)

        return density, support

    def __call__(self, x1, x2=None, weights=None):
        """Fit and evaluate on univariate or bivariate data."""
        if x2 is None:
            return self._eval_univariate(x1, weights)
        else:
            return self._eval_bivariate(x1, x2, weights)


# Note: we no longer use this for univariate histograms in histplot,
# preferring _stats.Hist. We'll deprecate this once we have a bivariate Stat class.
class Histogram:
    """Univariate and bivariate histogram estimator."""
    def __init__(
        self,
        stat="count",
        bins="auto",
        binwidth=None,
        binrange=None,
        discrete=False,
        cumulative=False,
    ):
        """Initialize the estimator with its parameters.

        Parameters
        ----------
        stat : str
            Aggregate statistic to compute in each bin.

            - `count`: show the number of observations in each bin
            - `frequency`: show the number of observations divided by the bin width
            - `probability` or `proportion`: normalize such that bar heights sum to 1
            - `percent`: normalize such that bar heights sum to 100
            - `density`: normalize such that the total area of the histogram equals 1

        bins : str, number, vector, or a pair of such values
            Generic bin parameter that can be the name of a reference rule,
            the number of bins, or the breaks of the bins.
            Passed to :func:`numpy.histogram_bin_edges`.
        binwidth : number or pair of numbers
            Width of each bin, overrides ``bins`` but can be used with
            ``binrange``.
        binrange : pair of numbers or a pair of pairs
            Lowest and highest value for bin edges; can be used either
            with ``bins`` or ``binwidth``. Defaults to data extremes.
        discrete : bool or pair of bools
            If True, set ``binwidth`` and ``binrange`` such that bin
            edges cover integer values in the dataset.
        cumulative : bool
            If True, return the cumulative statistic.

        """
        stat_choices = [
            "count", "frequency", "density", "probability", "proportion", "percent",
        ]
        _check_argument("stat", stat_choices, stat)

        self.stat = stat
        self.bins = bins
        self.binwidth = binwidth
        self.binrange = binrange
        self.discrete = discrete
        self.cumulative = cumulative

        self.bin_kws = None

    def _define_bin_edges(self, x, weights, bins, binwidth, binrange, discrete):
        """Inner function that takes bin parameters as arguments."""
        if binrange is None:
            start, stop = x.min(), x.max()
        else:
            start, stop = binrange

        if discrete:
            bin_edges = np.arange(start - .5, stop + 1.5)
        elif binwidth is not None:
            step = binwidth
            bin_edges = np.arange(start, stop + step, step)
            # Handle roundoff error (maybe there is a less clumsy way?)
            if bin_edges.max() < stop or len(bin_edges) < 2:
                bin_edges = np.append(bin_edges, bin_edges.max() + step)
        else:
            bin_edges = np.histogram_bin_edges(
                x, bins, binrange, weights,
            )
        return bin_edges

    def define_bin_params(self, x1, x2=None, weights=None, cache=True):
        """Given data, return numpy.histogram parameters to define bins."""
        if x2 is None:

            bin_edges = self._define_bin_edges(
                x1, weights, self.bins, self.binwidth, self.binrange, self.discrete,
            )

            if isinstance(self.bins, (str, Number)):
                n_bins = len(bin_edges) - 1
                bin_range = bin_edges.min(), bin_edges.max()
                bin_kws = dict(bins=n_bins, range=bin_range)
            else:
                bin_kws = dict(bins=bin_edges)

        else:

            bin_edges = []
            for i, x in enumerate([x1, x2]):

                # Resolve out whether bin parameters are shared
                # or specific to each variable

                bins = self.bins
                if not bins or isinstance(bins, (str, Number)):
                    pass
                elif isinstance(bins[i], str):
                    bins = bins[i]
                elif len(bins) == 2:
                    bins = bins[i]

                binwidth = self.binwidth
                if binwidth is None:
                    pass
                elif not isinstance(binwidth, Number):
                    binwidth = binwidth[i]

                binrange = self.binrange
                if binrange is None:
                    pass
                elif not isinstance(binrange[0], Number):
                    binrange = binrange[i]

                discrete = self.discrete
                if not isinstance(discrete, bool):
                    discrete = discrete[i]

                # Define the bins for this variable

                bin_edges.append(self._define_bin_edges(
                    x, weights, bins, binwidth, binrange, discrete,
                ))

            bin_kws = dict(bins=tuple(bin_edges))

        if cache:
            self.bin_kws = bin_kws

        return bin_kws

    def _eval_bivariate(self, x1, x2, weights):
        """Inner function for histogram of two variables."""
        bin_kws = self.bin_kws
        if bin_kws is None:
            bin_kws = self.define_bin_params(x1, x2, cache=False)

        density = self.stat == "density"

        hist, *bin_edges = np.histogram2d(
            x1, x2, **bin_kws, weights=weights, density=density
        )

        area = np.outer(
            np.diff(bin_edges[0]),
            np.diff(bin_edges[1]),
        )

        if self.stat == "probability" or self.stat == "proportion":
            hist = hist.astype(float) / hist.sum()
        elif self.stat == "percent":
            hist = hist.astype(float) / hist.sum() * 100
        elif self.stat == "frequency":
            hist = hist.astype(float) / area

        if self.cumulative:
            if self.stat in ["density", "frequency"]:
                hist = (hist * area).cumsum(axis=0).cumsum(axis=1)
            else:
                hist = hist.cumsum(axis=0).cumsum(axis=1)

        return hist, bin_edges

    def _eval_univariate(self, x, weights):
        """Inner function for histogram of one variable."""
        bin_kws = self.bin_kws
        if bin_kws is None:
            bin_kws = self.define_bin_params(x, weights=weights, cache=False)

        density = self.stat == "density"
        hist, bin_edges = np.histogram(
            x, **bin_kws, weights=weights, density=density,
        )

        if self.stat == "probability" or self.stat == "proportion":
            hist = hist.astype(float) / hist.sum()
        elif self.stat == "percent":
            hist = hist.astype(float) / hist.sum() * 100
        elif self.stat == "frequency":
            hist = hist.astype(float) / np.diff(bin_edges)

        if self.cumulative:
            if self.stat in ["density", "frequency"]:
                hist = (hist * np.diff(bin_edges)).cumsum()
            else:
                hist = hist.cumsum()

        return hist, bin_edges

    def __call__(self, x1, x2=None, weights=None):
        """Count the occurrences in each bin, maybe normalize."""
        if x2 is None:
            return self._eval_univariate(x1, weights)
        else:
            return self._eval_bivariate(x1, x2, weights)


class ECDF:
    """Univariate empirical cumulative distribution estimator."""
    def __init__(self, stat="proportion", complementary=False):
        """Initialize the class with its parameters

        Parameters
        ----------
        stat : {{"proportion", "percent", "count"}}
            Distribution statistic to compute.
        complementary : bool
            If True, use the complementary CDF (1 - CDF)

        """
        _check_argument("stat", ["count", "percent", "proportion"], stat)
        self.stat = stat
        self.complementary = complementary

    def _eval_bivariate(self, x1, x2, weights):
        """Inner function for ECDF of two variables."""
        raise NotImplementedError("Bivariate ECDF is not implemented")

    def _eval_univariate(self, x, weights):
        """Inner function for ECDF of one variable."""
        sorter = x.argsort()
        x = x[sorter]
        weights = weights[sorter]
        y = weights.cumsum()

        if self.stat in ["percent", "proportion"]:
            y = y / y.max()
        if self.stat == "percent":
            y = y * 100

        x = np.r_[-np.inf, x]
        y = np.r_[0, y]

        if self.complementary:
            y = y.max() - y

        return y, x

    def __call__(self, x1, x2=None, weights=None):
        """Return proportion or count of observations below each sorted datapoint."""
        x1 = np.asarray(x1)
        if weights is None:
            weights = np.ones_like(x1)
        else:
            weights = np.asarray(weights)

        if x2 is None:
            return self._eval_univariate(x1, weights)
        else:
            return self._eval_bivariate(x1, x2, weights)


class EstimateAggregator:

    def __init__(self, estimator, errorbar=None, **boot_kws):
        """
        Data aggregator that produces an estimate and error bar interval.

        Parameters
        ----------
        estimator : callable or string
            Function (or method name) that maps a vector to a scalar.
        errorbar : string, (string, number) tuple, or callable
            Name of errorbar method (either "ci", "pi", "se", or "sd"), or a tuple
            with a method name and a level parameter, or a function that maps from a
            vector to a (min, max) interval, or None to hide errorbar. See the
            :doc:`errorbar tutorial </tutorial/error_bars>` for more information.
        boot_kws
            Additional keywords are passed to bootstrap when error_method is "ci".

        """
        self.estimator = estimator

        method, level = _validate_errorbar_arg(errorbar)
        self.error_method = method
        self.error_level = level

        self.boot_kws = boot_kws

    def __call__(self, data, var):
        """Aggregate over `var` column of `data` with estimate and error interval."""
        vals = data[var]
        if callable(self.estimator):
            # You would think we could pass to vals.agg, and yet:
            # https://github.com/mwaskom/seaborn/issues/2943
            estimate = self.estimator(vals)
        else:
            estimate = vals.agg(self.estimator)

        # Options that produce no error bars
        if self.error_method is None:
            err_min = err_max = np.nan
        elif len(data) <= 1:
            err_min = err_max = np.nan

        # Generic errorbars from user-supplied function
        elif callable(self.error_method):
            err_min, err_max = self.error_method(vals)

        # Parametric options
        elif self.error_method == "sd":
            half_interval = vals.std() * self.error_level
            err_min, err_max = estimate - half_interval, estimate + half_interval
        elif self.error_method == "se":
            half_interval = vals.sem() * self.error_level
            err_min, err_max = estimate - half_interval, estimate + half_interval

        # Nonparametric options
        elif self.error_method == "pi":
            err_min, err_max = _percentile_interval(vals, self.error_level)
        elif self.error_method == "ci":
            units = data.get("units", None)
            boots = bootstrap(vals, units=units, func=self.estimator, **self.boot_kws)
            err_min, err_max = _percentile_interval(boots, self.error_level)

        return pd.Series({var: estimate, f"{var}min": err_min, f"{var}max": err_max})


class WeightedAggregator:

    def __init__(self, estimator, errorbar=None, **boot_kws):
        """
        Data aggregator that produces a weighted estimate and error bar interval.

        Parameters
        ----------
        estimator : string
            Function (or method name) that maps a vector to a scalar. Currently
            supports only "mean".
        errorbar : string or (string, number) tuple
            Name of errorbar method or a tuple with a method name and a level parameter.
            Currently the only supported method is "ci".
        boot_kws
            Additional keywords are passed to bootstrap when error_method is "ci".

        """
        if estimator != "mean":
            # Note that, while other weighted estimators may make sense (e.g. median),
            # I'm not aware of an implementation in our dependencies. We can add one
            # in seaborn later, if there is sufficient interest. For now, limit to mean.
            raise ValueError(f"Weighted estimator must be 'mean', not {estimator!r}.")
        self.estimator = estimator

        method, level = _validate_errorbar_arg(errorbar)
        if method is not None and method != "ci":
            # As with the estimator, weighted 'sd' or 'pi' error bars may make sense.
            # But we'll keep things simple for now and limit to (bootstrap) CI.
            raise ValueError(f"Error bar method must be 'ci', not {method!r}.")
        self.error_method = method
        self.error_level = level

        self.boot_kws = boot_kws

    def __call__(self, data, var):
        """Aggregate over `var` column of `data` with estimate and error interval."""
        vals = data[var]
        weights = data["weight"]

        estimate = np.average(vals, weights=weights)

        if self.error_method == "ci" and len(data) > 1:

            def error_func(x, w):
                return np.average(x, weights=w)

            boots = bootstrap(vals, weights, func=error_func, **self.boot_kws)
            err_min, err_max = _percentile_interval(boots, self.error_level)

        else:
            err_min = err_max = np.nan

        return pd.Series({var: estimate, f"{var}min": err_min, f"{var}max": err_max})


class LetterValues:

    def __init__(self, k_depth, outlier_prop, trust_alpha):
        """
        Compute percentiles of a distribution using various tail stopping rules.

        Parameters
        ----------
        k_depth: "tukey", "proportion", "trustworthy", or "full"
            Stopping rule for choosing tail percentiled to show:

            - tukey: Show a similar number of outliers as in a conventional boxplot.
            - proportion: Show approximately `outlier_prop` outliers.
            - trust_alpha: Use `trust_alpha` level for most extreme tail percentile.

        outlier_prop: float
            Parameter for `k_depth="proportion"` setting the expected outlier rate.
        trust_alpha: float
            Parameter for `k_depth="trustworthy"` setting the confidence threshold.

        Notes
        -----
        Based on the proposal in this paper:
        https://vita.had.co.nz/papers/letter-value-plot.pdf

        """
        k_options = ["tukey", "proportion", "trustworthy", "full"]
        if isinstance(k_depth, str):
            _check_argument("k_depth", k_options, k_depth)
        elif not isinstance(k_depth, int):
            err = (
                "The `k_depth` parameter must be either an integer or string "
                f"(one of {k_options}), not {k_depth!r}."
            )
            raise TypeError(err)

        self.k_depth = k_depth
        self.outlier_prop = outlier_prop
        self.trust_alpha = trust_alpha

    def _compute_k(self, n):

        # Select the depth, i.e. number of boxes to draw, based on the method
        if self.k_depth == "full":
            # extend boxes to 100% of the data
            k = int(np.log2(n)) + 1
        elif self.k_depth == "tukey":
            # This results with 5-8 points in each tail
            k = int(np.log2(n)) - 3
        elif self.k_depth == "proportion":
            k = int(np.log2(n)) - int(np.log2(n * self.outlier_prop)) + 1
        elif self.k_depth == "trustworthy":
            normal_quantile_func = np.vectorize(NormalDist().inv_cdf)
            point_conf = 2 * normal_quantile_func(1 - self.trust_alpha / 2) ** 2
            k = int(np.log2(n / point_conf)) + 1
        else:
            # Allow having k directly specified as input
            k = int(self.k_depth)

        return max(k, 1)

    def __call__(self, x):
        """Evaluate the letter values."""
        k = self._compute_k(len(x))
        exp = np.arange(k + 1, 1, -1), np.arange(2, k + 2)
        levels = k + 1 - np.concatenate([exp[0], exp[1][1:]])
        percentiles = 100 * np.concatenate([0.5 ** exp[0], 1 - 0.5 ** exp[1]])
        if self.k_depth == "full":
            percentiles[0] = 0
            percentiles[-1] = 100
        values = np.percentile(x, percentiles)
        fliers = np.asarray(x[(x < values.min()) | (x > values.max())])
        median = np.percentile(x, 50)

        return {
            "k": k,
            "levels": levels,
            "percs": percentiles,
            "values": values,
            "fliers": fliers,
            "median": median,
        }


def _percentile_interval(data, width):
    """Return a percentile interval from data of a given width."""
    edge = (100 - width) / 2
    percentiles = edge, 100 - edge
    return np.nanpercentile(data, percentiles)


def _validate_errorbar_arg(arg):
    """Check type and value of errorbar argument and assign default level."""
    DEFAULT_LEVELS = {
        "ci": 95,
        "pi": 95,
        "se": 1,
        "sd": 1,
    }

    usage = "`errorbar` must be a callable, string, or (string, number) tuple"

    if arg is None:
        return None, None
    elif callable(arg):
        return arg, None
    elif isinstance(arg, str):
        method = arg
        level = DEFAULT_LEVELS.get(method, None)
    else:
        try:
            method, level = arg
        except (ValueError, TypeError) as err:
            raise err.__class__(usage) from err

    _check_argument("errorbar", list(DEFAULT_LEVELS), method)
    if level is not None and not isinstance(level, Number):
        raise TypeError(usage)

    return method, level
