from copy import deepcopy


def immutable(self, *_args, **_kwargs):
    r"""
    Function for not implemented method since the object is immutable
    """
    
    raise AttributeError(
        f"'{self.__class__.__name__}' object is read-only"
    )


_empty_frozendict = None
_module_name = "frozendict"


# noinspection PyPep8Naming
class frozendict(dict):
    r"""
    A simple immutable dictionary.

    The API is the same as `dict`, without methods that can change the
    immutability. In addition, it supports __hash__().
    """
    
    __slots__ = (
        "_hash",
    )
    
    @classmethod
    def fromkeys(cls, *args, **kwargs):
        r"""
        Identical to dict.fromkeys().
        """
        
        return cls(dict.fromkeys(*args, **kwargs))
    
    # noinspection PyMethodParameters
    def __new__(e4b37cdf_d78a_4632_bade_6f0579d8efac, *args, **kwargs):
        cls = e4b37cdf_d78a_4632_bade_6f0579d8efac
        
        has_kwargs = bool(kwargs)
        continue_creation = True
        self = None
        
        # check if there's only an argument and it's of the same class
        if len(args) == 1 and not has_kwargs:
            it = args[0]
            
            # no isinstance, to avoid subclassing problems
            if it.__class__ == frozendict and cls == frozendict:
                self = it
                continue_creation = False
        
        if continue_creation:
            self = dict.__new__(cls, *args, **kwargs)
            
            dict.__init__(self, *args, **kwargs)
            
            # empty singleton - start
            
            if self.__class__ == frozendict and not len(self):
                global _empty_frozendict
                
                if _empty_frozendict is None:
                    _empty_frozendict = self
                else:
                    self = _empty_frozendict
                    continue_creation = False
            
            # empty singleton - end
            
            if continue_creation:
                object.__setattr__(self, "_hash", -1)
        
        return self
    
    # noinspection PyMissingConstructor
    def __init__(self, *args, **kwargs):
        pass
    
    def __hash__(self, *args, **kwargs):
        r"""
        Calculates the hash if all values are hashable, otherwise
        raises a TypeError.
        """
        
        if self._hash != -1:
            _hash = self._hash
        else:
            fs = frozenset(self.items())
            _hash = hash(fs)
            
            object.__setattr__(self, "_hash", _hash)
        
        return _hash
    
    def __repr__(self, *args, **kwargs):
        r"""
        Identical to dict.__repr__().
        """
        
        body = super().__repr__(*args, **kwargs)
        klass = self.__class__
        
        if klass == frozendict:
            name = f"{_module_name}.{klass.__name__}"
        else:
            name = klass.__name__
        
        return f"{name}({body})"
    
    def copy(self):
        r"""
        Return the object itself, as it's an immutable.
        """
        
        klass = self.__class__
        
        if klass == frozendict:
            return self
        
        return klass(self)
    
    def __copy__(self, *args, **kwargs):
        r"""
        See copy().
        """
        
        return self.copy()
    
    def __deepcopy__(self, memo, *args, **kwargs):
        r"""
        As for tuples, if hashable, see copy(); otherwise, it returns a
        deepcopy.
        """
        
        klass = self.__class__
        return_copy = klass == frozendict
        
        if return_copy:
            try:
                hash(self)
            except TypeError:
                return_copy = False
        
        if return_copy:
            return self.copy()
        
        tmp = deepcopy(dict(self))
        
        return klass(tmp)
    
    def __reduce__(self, *args, **kwargs):
        r"""
        Support for `pickle`.
        """
        
        return (self.__class__, (dict(self),))
    
    def set(self, key, val):
        new_self = dict(self)
        new_self[key] = val
        
        return self.__class__(new_self)
    
    def setdefault(self, key, default=None):
        if key in self:
            return self
        
        new_self = dict(self)
        
        new_self[key] = default
        
        return self.__class__(new_self)
    
    def delete(self, key):
        new_self = dict(self)
        del new_self[key]
        
        if new_self:
            return self.__class__(new_self)
        
        return self.__class__()
    
    def _get_by_index(self, collection, index):
        try:
            return collection[index]
        except IndexError:
            maxindex = len(collection) - 1
            name = self.__class__.__name__
            raise IndexError(
                f"{name} index {index} out of range {maxindex}"
            ) from None
    
    def key(self, index=0):
        collection = tuple(self.keys())
        
        return self._get_by_index(collection, index)
    
    def value(self, index=0):
        collection = tuple(self.values())
        
        return self._get_by_index(collection, index)
    
    def item(self, index=0):
        collection = tuple(self.items())
        
        return self._get_by_index(collection, index)
    
    def __setitem__(self, key, val, *args, **kwargs):
        raise TypeError(
            f"'{self.__class__.__name__}' object doesn't support item "
            "assignment"
        )
    
    def __delitem__(self, key, *args, **kwargs):
        raise TypeError(
            f"'{self.__class__.__name__}' object doesn't support item "
            "deletion"
        )


def frozendict_or(self, other, *_args, **_kwargs):
    res = {}
    res.update(self)
    res.update(other)
    
    return self.__class__(res)


frozendict.__or__ = frozendict_or
frozendict.__ior__ = frozendict_or

try:
    # noinspection PyStatementEffect
    frozendict.__reversed__
except AttributeError:  # pragma: no cover
    def frozendict_reversed(self, *_args, **_kwargs):
        return reversed(tuple(self))
    
    
    frozendict.__reversed__ = frozendict_reversed

frozendict.clear = immutable
frozendict.pop = immutable
frozendict.popitem = immutable
frozendict.update = immutable
frozendict.__delattr__ = immutable
frozendict.__setattr__ = immutable
frozendict.__module__ = _module_name

__all__ = (frozendict.__name__,)
