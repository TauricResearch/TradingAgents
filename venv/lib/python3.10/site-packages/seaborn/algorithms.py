"""Algorithms to support fitting routines in seaborn plotting functions."""
import numpy as np
import warnings


def bootstrap(*args, **kwargs):
    """Resample one or more arrays with replacement and store aggregate values.

    Positional arguments are a sequence of arrays to bootstrap along the first
    axis and pass to a summary function.

    Keyword arguments:
        n_boot : int, default=10000
            Number of iterations
        axis : int, default=None
            Will pass axis to ``func`` as a keyword argument.
        units : array, default=None
            Array of sampling unit IDs. When used the bootstrap resamples units
            and then observations within units instead of individual
            datapoints.
        func : string or callable, default="mean"
            Function to call on the args that are passed in. If string, uses as
            name of function in the numpy namespace. If nans are present in the
            data, will try to use nan-aware version of named function.
        seed : Generator | SeedSequence | RandomState | int | None
            Seed for the random number generator; useful if you want
            reproducible resamples.

    Returns
    -------
    boot_dist: array
        array of bootstrapped statistic values

    """
    # Ensure list of arrays are same length
    if len(np.unique(list(map(len, args)))) > 1:
        raise ValueError("All input arrays must have the same length")
    n = len(args[0])

    # Default keyword arguments
    n_boot = kwargs.get("n_boot", 10000)
    func = kwargs.get("func", "mean")
    axis = kwargs.get("axis", None)
    units = kwargs.get("units", None)
    random_seed = kwargs.get("random_seed", None)
    if random_seed is not None:
        msg = "`random_seed` has been renamed to `seed` and will be removed"
        warnings.warn(msg)
    seed = kwargs.get("seed", random_seed)
    if axis is None:
        func_kwargs = dict()
    else:
        func_kwargs = dict(axis=axis)

    # Initialize the resampler
    if isinstance(seed, np.random.RandomState):
        rng = seed
    else:
        rng = np.random.default_rng(seed)

    # Coerce to arrays
    args = list(map(np.asarray, args))
    if units is not None:
        units = np.asarray(units)

    if isinstance(func, str):

        # Allow named numpy functions
        f = getattr(np, func)

        # Try to use nan-aware version of function if necessary
        missing_data = np.isnan(np.sum(np.column_stack(args)))

        if missing_data and not func.startswith("nan"):
            nanf = getattr(np, f"nan{func}", None)
            if nanf is None:
                msg = f"Data contain nans but no nan-aware version of `{func}` found"
                warnings.warn(msg, UserWarning)
            else:
                f = nanf

    else:
        f = func

    # Handle numpy changes
    try:
        integers = rng.integers
    except AttributeError:
        integers = rng.randint

    # Do the bootstrap
    if units is not None:
        return _structured_bootstrap(args, n_boot, units, f,
                                     func_kwargs, integers)

    boot_dist = []
    for i in range(int(n_boot)):
        resampler = integers(0, n, n, dtype=np.intp)  # intp is indexing dtype
        sample = [a.take(resampler, axis=0) for a in args]
        boot_dist.append(f(*sample, **func_kwargs))
    return np.array(boot_dist)


def _structured_bootstrap(args, n_boot, units, func, func_kwargs, integers):
    """Resample units instead of datapoints."""
    unique_units = np.unique(units)
    n_units = len(unique_units)

    args = [[a[units == unit] for unit in unique_units] for a in args]

    boot_dist = []
    for i in range(int(n_boot)):
        resampler = integers(0, n_units, n_units, dtype=np.intp)
        sample = [[a[i] for i in resampler] for a in args]
        lengths = map(len, sample[0])
        resampler = [integers(0, n, n, dtype=np.intp) for n in lengths]
        sample = [[c.take(r, axis=0) for c, r in zip(a, resampler)] for a in sample]
        sample = list(map(np.concatenate, sample))
        boot_dist.append(func(*sample, **func_kwargs))
    return np.array(boot_dist)
