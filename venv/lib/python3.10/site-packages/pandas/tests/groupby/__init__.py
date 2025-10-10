def get_groupby_method_args(name, obj):
    """
    Get required arguments for a groupby method.

    When parametrizing a test over groupby methods (e.g. "sum", "mean", "fillna"),
    it is often the case that arguments are required for certain methods.

    Parameters
    ----------
    name: str
        Name of the method.
    obj: Series or DataFrame
        pandas object that is being grouped.

    Returns
    -------
    A tuple of required arguments for the method.
    """
    if name in ("nth", "fillna", "take"):
        return (0,)
    if name == "quantile":
        return (0.5,)
    if name == "corrwith":
        return (obj,)
    return ()
