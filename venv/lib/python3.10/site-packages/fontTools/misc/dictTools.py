"""Misc dict tools."""

__all__ = ["hashdict"]


# https://stackoverflow.com/questions/1151658/python-hashable-dicts
class hashdict(dict):
    """
    hashable dict implementation, suitable for use as a key into
    other dicts.

        >>> h1 = hashdict({"apples": 1, "bananas":2})
        >>> h2 = hashdict({"bananas": 3, "mangoes": 5})
        >>> h1+h2
        hashdict(apples=1, bananas=3, mangoes=5)
        >>> d1 = {}
        >>> d1[h1] = "salad"
        >>> d1[h1]
        'salad'
        >>> d1[h2]
        Traceback (most recent call last):
        ...
        KeyError: hashdict(bananas=3, mangoes=5)

    based on answers from
       http://stackoverflow.com/questions/1151658/python-hashable-dicts

    """

    def __key(self):
        return tuple(sorted(self.items()))

    def __repr__(self):
        return "{0}({1})".format(
            self.__class__.__name__,
            ", ".join("{0}={1}".format(str(i[0]), repr(i[1])) for i in self.__key()),
        )

    def __hash__(self):
        return hash(self.__key())

    def __setitem__(self, key, value):
        raise TypeError(
            "{0} does not support item assignment".format(self.__class__.__name__)
        )

    def __delitem__(self, key):
        raise TypeError(
            "{0} does not support item assignment".format(self.__class__.__name__)
        )

    def clear(self):
        raise TypeError(
            "{0} does not support item assignment".format(self.__class__.__name__)
        )

    def pop(self, *args, **kwargs):
        raise TypeError(
            "{0} does not support item assignment".format(self.__class__.__name__)
        )

    def popitem(self, *args, **kwargs):
        raise TypeError(
            "{0} does not support item assignment".format(self.__class__.__name__)
        )

    def setdefault(self, *args, **kwargs):
        raise TypeError(
            "{0} does not support item assignment".format(self.__class__.__name__)
        )

    def update(self, *args, **kwargs):
        raise TypeError(
            "{0} does not support item assignment".format(self.__class__.__name__)
        )

    # update is not ok because it mutates the object
    # __add__ is ok because it creates a new object
    # while the new object is under construction, it's ok to mutate it
    def __add__(self, right):
        result = hashdict(self)
        dict.update(result, right)
        return result
