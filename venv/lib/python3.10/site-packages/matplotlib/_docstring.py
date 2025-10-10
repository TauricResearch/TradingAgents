import inspect

from . import _api


def kwarg_doc(text):
    """
    Decorator for defining the kwdoc documentation of artist properties.

    This decorator can be applied to artist property setter methods.
    The given text is stored in a private attribute ``_kwarg_doc`` on
    the method.  It is used to overwrite auto-generated documentation
    in the *kwdoc list* for artists. The kwdoc list is used to document
    ``**kwargs`` when they are properties of an artist. See e.g. the
    ``**kwargs`` section in `.Axes.text`.

    The text should contain the supported types, as well as the default
    value if applicable, e.g.:

        @_docstring.kwarg_doc("bool, default: :rc:`text.usetex`")
        def set_usetex(self, usetex):

    See Also
    --------
    matplotlib.artist.kwdoc

    """
    def decorator(func):
        func._kwarg_doc = text
        return func
    return decorator


class Substitution:
    """
    A decorator that performs %-substitution on an object's docstring.

    This decorator should be robust even if ``obj.__doc__`` is None (for
    example, if -OO was passed to the interpreter).

    Usage: construct a docstring.Substitution with a sequence or dictionary
    suitable for performing substitution; then decorate a suitable function
    with the constructed object, e.g.::

        sub_author_name = Substitution(author='Jason')

        @sub_author_name
        def some_function(x):
            "%(author)s wrote this function"

        # note that some_function.__doc__ is now "Jason wrote this function"

    One can also use positional arguments::

        sub_first_last_names = Substitution('Edgar Allen', 'Poe')

        @sub_first_last_names
        def some_function(x):
            "%s %s wrote the Raven"
    """
    def __init__(self, *args, **kwargs):
        if args and kwargs:
            raise TypeError("Only positional or keyword args are allowed")
        self.params = args or kwargs

    def __call__(self, func):
        if func.__doc__:
            func.__doc__ = inspect.cleandoc(func.__doc__) % self.params
        return func


class _ArtistKwdocLoader(dict):
    def __missing__(self, key):
        if not key.endswith(":kwdoc"):
            raise KeyError(key)
        name = key[:-len(":kwdoc")]
        from matplotlib.artist import Artist, kwdoc
        try:
            cls, = (cls for cls in _api.recursive_subclasses(Artist)
                    if cls.__name__ == name)
        except ValueError as e:
            raise KeyError(key) from e
        return self.setdefault(key, kwdoc(cls))


class _ArtistPropertiesSubstitution:
    """
    A class to substitute formatted placeholders in docstrings.

    This is realized in a single instance ``_docstring.interpd``.

    Use `~._ArtistPropertiesSubstition.register` to define placeholders and
    their substitution, e.g. ``_docstring.interpd.register(name="some value")``.

    Use this as a decorator to apply the substitution::

        @_docstring.interpd
        def some_func():
            '''Replace %(name)s.'''

    Decorating a class triggers substitution both on the class docstring and
    on the class' ``__init__`` docstring (which is a commonly required
    pattern for Artist subclasses).

    Substitutions of the form ``%(classname:kwdoc)s`` (ending with the
    literal ":kwdoc" suffix) trigger lookup of an Artist subclass with the
    given *classname*, and are substituted with the `.kwdoc` of that class.
    """

    def __init__(self):
        self.params = _ArtistKwdocLoader()

    def register(self, **kwargs):
        """
        Register substitutions.

        ``_docstring.interpd.register(name="some value")`` makes "name" available
        as a named parameter that will be replaced by "some value".
        """
        self.params.update(**kwargs)

    def __call__(self, obj):
        if obj.__doc__:
            obj.__doc__ = inspect.cleandoc(obj.__doc__) % self.params
        if isinstance(obj, type) and obj.__init__ != object.__init__:
            self(obj.__init__)
        return obj


def copy(source):
    """Copy a docstring from another source function (if present)."""
    def do_copy(target):
        if source.__doc__:
            target.__doc__ = source.__doc__
        return target
    return do_copy


# Create a decorator that will house the various docstring snippets reused
# throughout Matplotlib.
interpd = _ArtistPropertiesSubstitution()
