"""
Helper functions for managing the Matplotlib API.

This documentation is only relevant for Matplotlib developers, not for users.

.. warning::

    This module and its submodules are for internal use only.  Do not use them
    in your own code.  We may change the API at any time with no warning.

"""

import functools
import itertools
import pathlib
import re
import sys
import warnings

from .deprecation import (  # noqa: F401
    deprecated, warn_deprecated,
    rename_parameter, delete_parameter, make_keyword_only,
    deprecate_method_override, deprecate_privatize_attribute,
    suppress_matplotlib_deprecation_warning,
    MatplotlibDeprecationWarning)


class classproperty:
    """
    Like `property`, but also triggers on access via the class, and it is the
    *class* that's passed as argument.

    Examples
    --------
    ::

        class C:
            @classproperty
            def foo(cls):
                return cls.__name__

        assert C.foo == "C"
    """

    def __init__(self, fget, fset=None, fdel=None, doc=None):
        self._fget = fget
        if fset is not None or fdel is not None:
            raise ValueError('classproperty only implements fget.')
        self.fset = fset
        self.fdel = fdel
        # docs are ignored for now
        self._doc = doc

    def __get__(self, instance, owner):
        return self._fget(owner)

    @property
    def fget(self):
        return self._fget


# In the following check_foo() functions, the first parameter is positional-only to make
# e.g. `_api.check_isinstance([...], types=foo)` work.

def check_isinstance(types, /, **kwargs):
    """
    For each *key, value* pair in *kwargs*, check that *value* is an instance
    of one of *types*; if not, raise an appropriate TypeError.

    As a special case, a ``None`` entry in *types* is treated as NoneType.

    Examples
    --------
    >>> _api.check_isinstance((SomeClass, None), arg=arg)
    """
    none_type = type(None)
    types = ((types,) if isinstance(types, type) else
             (none_type,) if types is None else
             tuple(none_type if tp is None else tp for tp in types))

    def type_name(tp):
        return ("None" if tp is none_type
                else tp.__qualname__ if tp.__module__ == "builtins"
                else f"{tp.__module__}.{tp.__qualname__}")

    for k, v in kwargs.items():
        if not isinstance(v, types):
            names = [*map(type_name, types)]
            if "None" in names:  # Move it to the end for better wording.
                names.remove("None")
                names.append("None")
            raise TypeError(
                "{!r} must be an instance of {}, not a {}".format(
                    k,
                    ", ".join(names[:-1]) + " or " + names[-1]
                    if len(names) > 1 else names[0],
                    type_name(type(v))))


def check_in_list(values, /, *, _print_supported_values=True, **kwargs):
    """
    For each *key, value* pair in *kwargs*, check that *value* is in *values*;
    if not, raise an appropriate ValueError.

    Parameters
    ----------
    values : iterable
        Sequence of values to check on.
    _print_supported_values : bool, default: True
        Whether to print *values* when raising ValueError.
    **kwargs : dict
        *key, value* pairs as keyword arguments to find in *values*.

    Raises
    ------
    ValueError
        If any *value* in *kwargs* is not found in *values*.

    Examples
    --------
    >>> _api.check_in_list(["foo", "bar"], arg=arg, other_arg=other_arg)
    """
    if not kwargs:
        raise TypeError("No argument to check!")
    for key, val in kwargs.items():
        if val not in values:
            msg = f"{val!r} is not a valid value for {key}"
            if _print_supported_values:
                msg += f"; supported values are {', '.join(map(repr, values))}"
            raise ValueError(msg)


def check_shape(shape, /, **kwargs):
    """
    For each *key, value* pair in *kwargs*, check that *value* has the shape *shape*;
    if not, raise an appropriate ValueError.

    *None* in the shape is treated as a "free" size that can have any length.
    e.g. (None, 2) -> (N, 2)

    The values checked must be numpy arrays.

    Examples
    --------
    To check for (N, 2) shaped arrays

    >>> _api.check_shape((None, 2), arg=arg, other_arg=other_arg)
    """
    for k, v in kwargs.items():
        data_shape = v.shape

        if (len(data_shape) != len(shape)
                or any(s != t and t is not None for s, t in zip(data_shape, shape))):
            dim_labels = iter(itertools.chain(
                'NMLKJIH',
                (f"D{i}" for i in itertools.count())))
            text_shape = ", ".join([str(n) if n is not None else next(dim_labels)
                                    for n in shape[::-1]][::-1])
            if len(shape) == 1:
                text_shape += ","

            raise ValueError(
                f"{k!r} must be {len(shape)}D with shape ({text_shape}), "
                f"but your input has shape {v.shape}"
            )


def check_getitem(mapping, /, **kwargs):
    """
    *kwargs* must consist of a single *key, value* pair.  If *key* is in
    *mapping*, return ``mapping[value]``; else, raise an appropriate
    ValueError.

    Examples
    --------
    >>> _api.check_getitem({"foo": "bar"}, arg=arg)
    """
    if len(kwargs) != 1:
        raise ValueError("check_getitem takes a single keyword argument")
    (k, v), = kwargs.items()
    try:
        return mapping[v]
    except KeyError:
        raise ValueError(
            f"{v!r} is not a valid value for {k}; supported values are "
            f"{', '.join(map(repr, mapping))}") from None


def caching_module_getattr(cls):
    """
    Helper decorator for implementing module-level ``__getattr__`` as a class.

    This decorator must be used at the module toplevel as follows::

        @caching_module_getattr
        class __getattr__:  # The class *must* be named ``__getattr__``.
            @property  # Only properties are taken into account.
            def name(self): ...

    The ``__getattr__`` class will be replaced by a ``__getattr__``
    function such that trying to access ``name`` on the module will
    resolve the corresponding property (which may be decorated e.g. with
    ``_api.deprecated`` for deprecating module globals).  The properties are
    all implicitly cached.  Moreover, a suitable AttributeError is generated
    and raised if no property with the given name exists.
    """

    assert cls.__name__ == "__getattr__"
    # Don't accidentally export cls dunders.
    props = {name: prop for name, prop in vars(cls).items()
             if isinstance(prop, property)}
    instance = cls()

    @functools.cache
    def __getattr__(name):
        if name in props:
            return props[name].__get__(instance)
        raise AttributeError(
            f"module {cls.__module__!r} has no attribute {name!r}")

    return __getattr__


def define_aliases(alias_d, cls=None):
    """
    Class decorator for defining property aliases.

    Use as ::

        @_api.define_aliases({"property": ["alias", ...], ...})
        class C: ...

    For each property, if the corresponding ``get_property`` is defined in the
    class so far, an alias named ``get_alias`` will be defined; the same will
    be done for setters.  If neither the getter nor the setter exists, an
    exception will be raised.

    The alias map is stored as the ``_alias_map`` attribute on the class and
    can be used by `.normalize_kwargs` (which assumes that higher priority
    aliases come last).
    """
    if cls is None:  # Return the actual class decorator.
        return functools.partial(define_aliases, alias_d)

    def make_alias(name):  # Enforce a closure over *name*.
        @functools.wraps(getattr(cls, name))
        def method(self, *args, **kwargs):
            return getattr(self, name)(*args, **kwargs)
        return method

    for prop, aliases in alias_d.items():
        exists = False
        for prefix in ["get_", "set_"]:
            if prefix + prop in vars(cls):
                exists = True
                for alias in aliases:
                    method = make_alias(prefix + prop)
                    method.__name__ = prefix + alias
                    method.__doc__ = f"Alias for `{prefix + prop}`."
                    setattr(cls, prefix + alias, method)
        if not exists:
            raise ValueError(
                f"Neither getter nor setter exists for {prop!r}")

    def get_aliased_and_aliases(d):
        return {*d, *(alias for aliases in d.values() for alias in aliases)}

    preexisting_aliases = getattr(cls, "_alias_map", {})
    conflicting = (get_aliased_and_aliases(preexisting_aliases)
                   & get_aliased_and_aliases(alias_d))
    if conflicting:
        # Need to decide on conflict resolution policy.
        raise NotImplementedError(
            f"Parent class already defines conflicting aliases: {conflicting}")
    cls._alias_map = {**preexisting_aliases, **alias_d}
    return cls


def select_matching_signature(funcs, *args, **kwargs):
    """
    Select and call the function that accepts ``*args, **kwargs``.

    *funcs* is a list of functions which should not raise any exception (other
    than `TypeError` if the arguments passed do not match their signature).

    `select_matching_signature` tries to call each of the functions in *funcs*
    with ``*args, **kwargs`` (in the order in which they are given).  Calls
    that fail with a `TypeError` are silently skipped.  As soon as a call
    succeeds, `select_matching_signature` returns its return value.  If no
    function accepts ``*args, **kwargs``, then the `TypeError` raised by the
    last failing call is re-raised.

    Callers should normally make sure that any ``*args, **kwargs`` can only
    bind a single *func* (to avoid any ambiguity), although this is not checked
    by `select_matching_signature`.

    Notes
    -----
    `select_matching_signature` is intended to help implementing
    signature-overloaded functions.  In general, such functions should be
    avoided, except for back-compatibility concerns.  A typical use pattern is
    ::

        def my_func(*args, **kwargs):
            params = select_matching_signature(
                [lambda old1, old2: locals(), lambda new: locals()],
                *args, **kwargs)
            if "old1" in params:
                warn_deprecated(...)
                old1, old2 = params.values()  # note that locals() is ordered.
            else:
                new, = params.values()
            # do things with params

    which allows *my_func* to be called either with two parameters (*old1* and
    *old2*) or a single one (*new*).  Note that the new signature is given
    last, so that callers get a `TypeError` corresponding to the new signature
    if the arguments they passed in do not match any signature.
    """
    # Rather than relying on locals() ordering, one could have just used func's
    # signature (``bound = inspect.signature(func).bind(*args, **kwargs);
    # bound.apply_defaults(); return bound``) but that is significantly slower.
    for i, func in enumerate(funcs):
        try:
            return func(*args, **kwargs)
        except TypeError:
            if i == len(funcs) - 1:
                raise


def nargs_error(name, takes, given):
    """Generate a TypeError to be raised by function calls with wrong arity."""
    return TypeError(f"{name}() takes {takes} positional arguments but "
                     f"{given} were given")


def kwarg_error(name, kw):
    """
    Generate a TypeError to be raised by function calls with wrong kwarg.

    Parameters
    ----------
    name : str
        The name of the calling function.
    kw : str or Iterable[str]
        Either the invalid keyword argument name, or an iterable yielding
        invalid keyword arguments (e.g., a ``kwargs`` dict).
    """
    if not isinstance(kw, str):
        kw = next(iter(kw))
    return TypeError(f"{name}() got an unexpected keyword argument '{kw}'")


def recursive_subclasses(cls):
    """Yield *cls* and direct and indirect subclasses of *cls*."""
    yield cls
    for subcls in cls.__subclasses__():
        yield from recursive_subclasses(subcls)


def warn_external(message, category=None):
    """
    `warnings.warn` wrapper that sets *stacklevel* to "outside Matplotlib".

    The original emitter of the warning can be obtained by patching this
    function back to `warnings.warn`, i.e. ``_api.warn_external =
    warnings.warn`` (or ``functools.partial(warnings.warn, stacklevel=2)``,
    etc.).
    """
    kwargs = {}
    if sys.version_info[:2] >= (3, 12):
        # Go to Python's `site-packages` or `lib` from an editable install.
        basedir = pathlib.Path(__file__).parents[2]
        kwargs['skip_file_prefixes'] = (str(basedir / 'matplotlib'),
                                        str(basedir / 'mpl_toolkits'))
    else:
        frame = sys._getframe()
        for stacklevel in itertools.count(1):
            if frame is None:
                # when called in embedded context may hit frame is None
                kwargs['stacklevel'] = stacklevel
                break
            if not re.match(r"\A(matplotlib|mpl_toolkits)(\Z|\.(?!tests\.))",
                            # Work around sphinx-gallery not setting __name__.
                            frame.f_globals.get("__name__", "")):
                kwargs['stacklevel'] = stacklevel
                break
            frame = frame.f_back
        # preemptively break reference cycle between locals and the frame
        del frame
    warnings.warn(message, category, **kwargs)
