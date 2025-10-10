"""Generic visitor pattern implementation for Python objects."""

import enum
import weakref


class Visitor(object):
    defaultStop = False

    _visitors = {
        # By default we skip visiting weak references to avoid recursion
        # issues. Users can override this by registering a visit
        # function for weakref.ProxyType.
        weakref.ProxyType: {None: lambda self, obj, *args, **kwargs: False}
    }

    @classmethod
    def _register(celf, clazzes_attrs):
        assert celf != Visitor, "Subclass Visitor instead."
        if "_visitors" not in celf.__dict__:
            celf._visitors = {}

        def wrapper(method):
            assert method.__name__ == "visit"
            for clazzes, attrs in clazzes_attrs:
                if type(clazzes) != tuple:
                    clazzes = (clazzes,)
                if type(attrs) == str:
                    attrs = (attrs,)
                for clazz in clazzes:
                    _visitors = celf._visitors.setdefault(clazz, {})
                    for attr in attrs:
                        assert attr not in _visitors, (
                            "Oops, class '%s' has visitor function for '%s' defined already."
                            % (clazz.__name__, attr)
                        )
                        _visitors[attr] = method
            return None

        return wrapper

    @classmethod
    def register(celf, clazzes):
        if type(clazzes) != tuple:
            clazzes = (clazzes,)
        return celf._register([(clazzes, (None,))])

    @classmethod
    def register_attr(celf, clazzes, attrs):
        clazzes_attrs = []
        if type(clazzes) != tuple:
            clazzes = (clazzes,)
        if type(attrs) == str:
            attrs = (attrs,)
        for clazz in clazzes:
            clazzes_attrs.append((clazz, attrs))
        return celf._register(clazzes_attrs)

    @classmethod
    def register_attrs(celf, clazzes_attrs):
        return celf._register(clazzes_attrs)

    @classmethod
    def _visitorsFor(celf, thing, _default={}):
        typ = type(thing)

        for celf in celf.mro():
            _visitors = getattr(celf, "_visitors", None)
            if _visitors is None:
                break

            for base in typ.mro():
                m = celf._visitors.get(base, None)
                if m is not None:
                    return m

        return _default

    def visitObject(self, obj, *args, **kwargs):
        """Called to visit an object. This function loops over all non-private
        attributes of the objects and calls any user-registered (via
        ``@register_attr()`` or ``@register_attrs()``) ``visit()`` functions.

        The visitor will proceed to call ``self.visitAttr()``, unless there is a
        user-registered visit function and:

        * It returns ``False``; or
        * It returns ``None`` (or doesn't return anything) and
          ``visitor.defaultStop`` is ``True`` (non-default).
        """

        keys = sorted(vars(obj).keys())
        _visitors = self._visitorsFor(obj)
        defaultVisitor = _visitors.get("*", None)
        for key in keys:
            if key[0] == "_":
                continue
            value = getattr(obj, key)
            visitorFunc = _visitors.get(key, defaultVisitor)
            if visitorFunc is not None:
                ret = visitorFunc(self, obj, key, value, *args, **kwargs)
                if ret == False or (ret is None and self.defaultStop):
                    continue
            self.visitAttr(obj, key, value, *args, **kwargs)

    def visitAttr(self, obj, attr, value, *args, **kwargs):
        """Called to visit an attribute of an object."""
        self.visit(value, *args, **kwargs)

    def visitList(self, obj, *args, **kwargs):
        """Called to visit any value that is a list."""
        for value in obj:
            self.visit(value, *args, **kwargs)

    def visitDict(self, obj, *args, **kwargs):
        """Called to visit any value that is a dictionary."""
        for value in obj.values():
            self.visit(value, *args, **kwargs)

    def visitLeaf(self, obj, *args, **kwargs):
        """Called to visit any value that is not an object, list,
        or dictionary."""
        pass

    def visit(self, obj, *args, **kwargs):
        """This is the main entry to the visitor. The visitor will visit object
        ``obj``.

        The visitor will first determine if there is a registered (via
        ``@register()``) visit function for the type of object. If there is, it
        will be called, and ``(visitor, obj, *args, **kwargs)`` will be passed
        to the user visit function.

        The visitor will not recurse if there is a user-registered visit
        function and:

        * It returns ``False``; or
        * It returns ``None`` (or doesn't return anything) and
          ``visitor.defaultStop`` is ``True`` (non-default)

        Otherwise,  the visitor will proceed to dispatch to one of
        ``self.visitObject()``, ``self.visitList()``, ``self.visitDict()``, or
        ``self.visitLeaf()`` (any of which can be overriden in a subclass).
        """

        visitorFunc = self._visitorsFor(obj).get(None, None)
        if visitorFunc is not None:
            ret = visitorFunc(self, obj, *args, **kwargs)
            if ret == False or (ret is None and self.defaultStop):
                return
        if hasattr(obj, "__dict__") and not isinstance(obj, enum.Enum):
            self.visitObject(obj, *args, **kwargs)
        elif isinstance(obj, list):
            self.visitList(obj, *args, **kwargs)
        elif isinstance(obj, dict):
            self.visitDict(obj, *args, **kwargs)
        else:
            self.visitLeaf(obj, *args, **kwargs)
