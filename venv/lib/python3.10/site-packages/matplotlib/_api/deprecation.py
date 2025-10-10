"""
Helper functions for deprecating parts of the Matplotlib API.

This documentation is only relevant for Matplotlib developers, not for users.

.. warning::

    This module is for internal use only.  Do not use it in your own code.
    We may change the API at any time with no warning.

"""

import contextlib
import functools
import inspect
import math
import warnings


class MatplotlibDeprecationWarning(DeprecationWarning):
    """A class for issuing deprecation warnings for Matplotlib users."""


def _generate_deprecation_warning(
        since, message='', name='', alternative='', pending=False, obj_type='',
        addendum='', *, removal=''):
    if pending:
        if removal:
            raise ValueError("A pending deprecation cannot have a scheduled removal")
    elif removal == '':
        macro, meso, *_ = since.split('.')
        removal = f'{macro}.{int(meso) + 2}'
    if not message:
        message = (
            ("The %(name)s %(obj_type)s" if obj_type else "%(name)s") +
            (" will be deprecated in a future version" if pending else
             (" was deprecated in Matplotlib %(since)s" +
              (" and will be removed in %(removal)s" if removal else ""))) +
            "." +
            (" Use %(alternative)s instead." if alternative else "") +
            (" %(addendum)s" if addendum else ""))
    warning_cls = PendingDeprecationWarning if pending else MatplotlibDeprecationWarning
    return warning_cls(message % dict(
        func=name, name=name, obj_type=obj_type, since=since, removal=removal,
        alternative=alternative, addendum=addendum))


def warn_deprecated(
        since, *, message='', name='', alternative='', pending=False,
        obj_type='', addendum='', removal=''):
    """
    Display a standardized deprecation.

    Parameters
    ----------
    since : str
        The release at which this API became deprecated.
    message : str, optional
        Override the default deprecation message.  The ``%(since)s``,
        ``%(name)s``, ``%(alternative)s``, ``%(obj_type)s``, ``%(addendum)s``,
        and ``%(removal)s`` format specifiers will be replaced by the values
        of the respective arguments passed to this function.
    name : str, optional
        The name of the deprecated object.
    alternative : str, optional
        An alternative API that the user may use in place of the deprecated
        API.  The deprecation warning will tell the user about this alternative
        if provided.
    pending : bool, optional
        If True, uses a PendingDeprecationWarning instead of a
        DeprecationWarning.  Cannot be used together with *removal*.
    obj_type : str, optional
        The object type being deprecated.
    addendum : str, optional
        Additional text appended directly to the final message.
    removal : str, optional
        The expected removal version.  With the default (an empty string), a
        removal version is automatically computed from *since*.  Set to other
        Falsy values to not schedule a removal date.  Cannot be used together
        with *pending*.

    Examples
    --------
    ::

        # To warn of the deprecation of "matplotlib.name_of_module"
        warn_deprecated('1.4.0', name='matplotlib.name_of_module',
                        obj_type='module')
    """
    warning = _generate_deprecation_warning(
        since, message, name, alternative, pending, obj_type, addendum,
        removal=removal)
    from . import warn_external
    warn_external(warning, category=MatplotlibDeprecationWarning)


def deprecated(since, *, message='', name='', alternative='', pending=False,
               obj_type=None, addendum='', removal=''):
    """
    Decorator to mark a function, a class, or a property as deprecated.

    When deprecating a classmethod, a staticmethod, or a property, the
    ``@deprecated`` decorator should go *under* ``@classmethod`` and
    ``@staticmethod`` (i.e., `deprecated` should directly decorate the
    underlying callable), but *over* ``@property``.

    When deprecating a class ``C`` intended to be used as a base class in a
    multiple inheritance hierarchy, ``C`` *must* define an ``__init__`` method
    (if ``C`` instead inherited its ``__init__`` from its own base class, then
    ``@deprecated`` would mess up ``__init__`` inheritance when installing its
    own (deprecation-emitting) ``C.__init__``).

    Parameters are the same as for `warn_deprecated`, except that *obj_type*
    defaults to 'class' if decorating a class, 'attribute' if decorating a
    property, and 'function' otherwise.

    Examples
    --------
    ::

        @deprecated('1.4.0')
        def the_function_to_deprecate():
            pass
    """

    def deprecate(obj, message=message, name=name, alternative=alternative,
                  pending=pending, obj_type=obj_type, addendum=addendum):
        from matplotlib._api import classproperty

        if isinstance(obj, type):
            if obj_type is None:
                obj_type = "class"
            func = obj.__init__
            name = name or obj.__name__
            old_doc = obj.__doc__

            def finalize(wrapper, new_doc):
                try:
                    obj.__doc__ = new_doc
                except AttributeError:  # Can't set on some extension objects.
                    pass
                obj.__init__ = functools.wraps(obj.__init__)(wrapper)
                return obj

        elif isinstance(obj, (property, classproperty)):
            if obj_type is None:
                obj_type = "attribute"
            func = None
            name = name or obj.fget.__name__
            old_doc = obj.__doc__

            class _deprecated_property(type(obj)):
                def __get__(self, instance, owner=None):
                    if instance is not None or owner is not None \
                            and isinstance(self, classproperty):
                        emit_warning()
                    return super().__get__(instance, owner)

                def __set__(self, instance, value):
                    if instance is not None:
                        emit_warning()
                    return super().__set__(instance, value)

                def __delete__(self, instance):
                    if instance is not None:
                        emit_warning()
                    return super().__delete__(instance)

                def __set_name__(self, owner, set_name):
                    nonlocal name
                    if name == "<lambda>":
                        name = set_name

            def finalize(_, new_doc):
                return _deprecated_property(
                    fget=obj.fget, fset=obj.fset, fdel=obj.fdel, doc=new_doc)

        else:
            if obj_type is None:
                obj_type = "function"
            func = obj
            name = name or obj.__name__
            old_doc = func.__doc__

            def finalize(wrapper, new_doc):
                wrapper = functools.wraps(func)(wrapper)
                wrapper.__doc__ = new_doc
                return wrapper

        def emit_warning():
            warn_deprecated(
                since, message=message, name=name, alternative=alternative,
                pending=pending, obj_type=obj_type, addendum=addendum,
                removal=removal)

        def wrapper(*args, **kwargs):
            emit_warning()
            return func(*args, **kwargs)

        old_doc = inspect.cleandoc(old_doc or '').strip('\n')

        notes_header = '\nNotes\n-----'
        second_arg = ' '.join([t.strip() for t in
                               (message, f"Use {alternative} instead."
                                if alternative else "", addendum) if t])
        new_doc = (f"[*Deprecated*] {old_doc}\n"
                   f"{notes_header if notes_header not in old_doc else ''}\n"
                   f".. deprecated:: {since}\n"
                   f"   {second_arg}")

        if not old_doc:
            # This is to prevent a spurious 'unexpected unindent' warning from
            # docutils when the original docstring was blank.
            new_doc += r'\ '

        return finalize(wrapper, new_doc)

    return deprecate


class deprecate_privatize_attribute:
    """
    Helper to deprecate public access to an attribute (or method).

    This helper should only be used at class scope, as follows::

        class Foo:
            attr = _deprecate_privatize_attribute(*args, **kwargs)

    where *all* parameters are forwarded to `deprecated`.  This form makes
    ``attr`` a property which forwards read and write access to ``self._attr``
    (same name but with a leading underscore), with a deprecation warning.
    Note that the attribute name is derived from *the name this helper is
    assigned to*.  This helper also works for deprecating methods.
    """

    def __init__(self, *args, **kwargs):
        self.deprecator = deprecated(*args, **kwargs)

    def __set_name__(self, owner, name):
        setattr(owner, name, self.deprecator(
            property(lambda self: getattr(self, f"_{name}"),
                     lambda self, value: setattr(self, f"_{name}", value)),
            name=name))


# Used by _copy_docstring_and_deprecators to redecorate pyplot wrappers and
# boilerplate.py to retrieve original signatures.  It may seem natural to store
# this information as an attribute on the wrapper, but if the wrapper gets
# itself functools.wraps()ed, then such attributes are silently propagated to
# the outer wrapper, which is not desired.
DECORATORS = {}


def rename_parameter(since, old, new, func=None):
    """
    Decorator indicating that parameter *old* of *func* is renamed to *new*.

    The actual implementation of *func* should use *new*, not *old*.  If *old*
    is passed to *func*, a DeprecationWarning is emitted, and its value is
    used, even if *new* is also passed by keyword (this is to simplify pyplot
    wrapper functions, which always pass *new* explicitly to the Axes method).
    If *new* is also passed but positionally, a TypeError will be raised by the
    underlying function during argument binding.

    Examples
    --------
    ::

        @_api.rename_parameter("3.1", "bad_name", "good_name")
        def func(good_name): ...
    """

    decorator = functools.partial(rename_parameter, since, old, new)

    if func is None:
        return decorator

    signature = inspect.signature(func)
    assert old not in signature.parameters, (
        f"Matplotlib internal error: {old!r} cannot be a parameter for "
        f"{func.__name__}()")
    assert new in signature.parameters, (
        f"Matplotlib internal error: {new!r} must be a parameter for "
        f"{func.__name__}()")

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if old in kwargs:
            warn_deprecated(
                since, message=f"The {old!r} parameter of {func.__name__}() "
                f"has been renamed {new!r} since Matplotlib {since}; support "
                f"for the old name will be dropped in %(removal)s.")
            kwargs[new] = kwargs.pop(old)
        return func(*args, **kwargs)

    # wrapper() must keep the same documented signature as func(): if we
    # instead made both *old* and *new* appear in wrapper()'s signature, they
    # would both show up in the pyplot function for an Axes method as well and
    # pyplot would explicitly pass both arguments to the Axes method.

    DECORATORS[wrapper] = decorator
    return wrapper


class _deprecated_parameter_class:
    def __repr__(self):
        return "<deprecated parameter>"


_deprecated_parameter = _deprecated_parameter_class()


def delete_parameter(since, name, func=None, **kwargs):
    """
    Decorator indicating that parameter *name* of *func* is being deprecated.

    The actual implementation of *func* should keep the *name* parameter in its
    signature, or accept a ``**kwargs`` argument (through which *name* would be
    passed).

    Parameters that come after the deprecated parameter effectively become
    keyword-only (as they cannot be passed positionally without triggering the
    DeprecationWarning on the deprecated parameter), and should be marked as
    such after the deprecation period has passed and the deprecated parameter
    is removed.

    Parameters other than *since*, *name*, and *func* are keyword-only and
    forwarded to `.warn_deprecated`.

    Examples
    --------
    ::

        @_api.delete_parameter("3.1", "unused")
        def func(used_arg, other_arg, unused, more_args): ...
    """

    decorator = functools.partial(delete_parameter, since, name, **kwargs)

    if func is None:
        return decorator

    signature = inspect.signature(func)
    # Name of `**kwargs` parameter of the decorated function, typically
    # "kwargs" if such a parameter exists, or None if the decorated function
    # doesn't accept `**kwargs`.
    kwargs_name = next((param.name for param in signature.parameters.values()
                        if param.kind == inspect.Parameter.VAR_KEYWORD), None)
    if name in signature.parameters:
        kind = signature.parameters[name].kind
        is_varargs = kind is inspect.Parameter.VAR_POSITIONAL
        is_varkwargs = kind is inspect.Parameter.VAR_KEYWORD
        if not is_varargs and not is_varkwargs:
            name_idx = (
                # Deprecated parameter can't be passed positionally.
                math.inf if kind is inspect.Parameter.KEYWORD_ONLY
                # If call site has no more than this number of parameters, the
                # deprecated parameter can't have been passed positionally.
                else [*signature.parameters].index(name))
            func.__signature__ = signature = signature.replace(parameters=[
                param.replace(default=_deprecated_parameter)
                if param.name == name else param
                for param in signature.parameters.values()])
        else:
            name_idx = -1  # Deprecated parameter can always have been passed.
    else:
        is_varargs = is_varkwargs = False
        # Deprecated parameter can't be passed positionally.
        name_idx = math.inf
        assert kwargs_name, (
            f"Matplotlib internal error: {name!r} must be a parameter for "
            f"{func.__name__}()")

    addendum = kwargs.pop('addendum', None)

    @functools.wraps(func)
    def wrapper(*inner_args, **inner_kwargs):
        if len(inner_args) <= name_idx and name not in inner_kwargs:
            # Early return in the simple, non-deprecated case (much faster than
            # calling bind()).
            return func(*inner_args, **inner_kwargs)
        arguments = signature.bind(*inner_args, **inner_kwargs).arguments
        if is_varargs and arguments.get(name):
            warn_deprecated(
                since, message=f"Additional positional arguments to "
                f"{func.__name__}() are deprecated since %(since)s and "
                f"support for them will be removed in %(removal)s.")
        elif is_varkwargs and arguments.get(name):
            warn_deprecated(
                since, message=f"Additional keyword arguments to "
                f"{func.__name__}() are deprecated since %(since)s and "
                f"support for them will be removed in %(removal)s.")
        # We cannot just check `name not in arguments` because the pyplot
        # wrappers always pass all arguments explicitly.
        elif any(name in d and d[name] != _deprecated_parameter
                 for d in [arguments, arguments.get(kwargs_name, {})]):
            deprecation_addendum = (
                f"If any parameter follows {name!r}, they should be passed as "
                f"keyword, not positionally.")
            warn_deprecated(
                since,
                name=repr(name),
                obj_type=f"parameter of {func.__name__}()",
                addendum=(addendum + " " + deprecation_addendum) if addendum
                         else deprecation_addendum,
                **kwargs)
        return func(*inner_args, **inner_kwargs)

    DECORATORS[wrapper] = decorator
    return wrapper


def make_keyword_only(since, name, func=None):
    """
    Decorator indicating that passing parameter *name* (or any of the following
    ones) positionally to *func* is being deprecated.

    When used on a method that has a pyplot wrapper, this should be the
    outermost decorator, so that :file:`boilerplate.py` can access the original
    signature.
    """

    decorator = functools.partial(make_keyword_only, since, name)

    if func is None:
        return decorator

    signature = inspect.signature(func)
    POK = inspect.Parameter.POSITIONAL_OR_KEYWORD
    KWO = inspect.Parameter.KEYWORD_ONLY
    assert (name in signature.parameters
            and signature.parameters[name].kind == POK), (
        f"Matplotlib internal error: {name!r} must be a positional-or-keyword "
        f"parameter for {func.__name__}(). If this error happens on a function with a "
        f"pyplot wrapper, make sure make_keyword_only() is the outermost decorator.")
    names = [*signature.parameters]
    name_idx = names.index(name)
    kwonly = [name for name in names[name_idx:]
              if signature.parameters[name].kind == POK]

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Don't use signature.bind here, as it would fail when stacked with
        # rename_parameter and an "old" argument name is passed in
        # (signature.bind would fail, but the actual call would succeed).
        if len(args) > name_idx:
            warn_deprecated(
                since, message="Passing the %(name)s %(obj_type)s "
                "positionally is deprecated since Matplotlib %(since)s; the "
                "parameter will become keyword-only in %(removal)s.",
                name=name, obj_type=f"parameter of {func.__name__}()")
        return func(*args, **kwargs)

    # Don't modify *func*'s signature, as boilerplate.py needs it.
    wrapper.__signature__ = signature.replace(parameters=[
        param.replace(kind=KWO) if param.name in kwonly else param
        for param in signature.parameters.values()])
    DECORATORS[wrapper] = decorator
    return wrapper


def deprecate_method_override(method, obj, *, allow_empty=False, **kwargs):
    """
    Return ``obj.method`` with a deprecation if it was overridden, else None.

    Parameters
    ----------
    method
        An unbound method, i.e. an expression of the form
        ``Class.method_name``.  Remember that within the body of a method, one
        can always use ``__class__`` to refer to the class that is currently
        being defined.
    obj
        Either an object of the class where *method* is defined, or a subclass
        of that class.
    allow_empty : bool, default: False
        Whether to allow overrides by "empty" methods without emitting a
        warning.
    **kwargs
        Additional parameters passed to `warn_deprecated` to generate the
        deprecation warning; must at least include the "since" key.
    """

    def empty(): pass
    def empty_with_docstring(): """doc"""

    name = method.__name__
    bound_child = getattr(obj, name)
    bound_base = (
        method  # If obj is a class, then we need to use unbound methods.
        if isinstance(bound_child, type(empty)) and isinstance(obj, type)
        else method.__get__(obj))
    if (bound_child != bound_base
            and (not allow_empty
                 or (getattr(getattr(bound_child, "__code__", None),
                             "co_code", None)
                     not in [empty.__code__.co_code,
                             empty_with_docstring.__code__.co_code]))):
        warn_deprecated(**{"name": name, "obj_type": "method", **kwargs})
        return bound_child
    return None


@contextlib.contextmanager
def suppress_matplotlib_deprecation_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MatplotlibDeprecationWarning)
        yield
