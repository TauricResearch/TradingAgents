from types import MappingProxyType
from array import array
from frozendict import frozendict
from collections.abc import MutableMapping, MutableSequence, MutableSet
from enum import Enum

# fix for python 3.9-

# coverage does not work here!
if not issubclass(array, MutableSequence):   # pragma: no cover
    # noinspection PyUnresolvedReferences
    MutableSequence.register(array)


def isIterableNotString(o):
    from collections import abc
    
    return (
        isinstance(o, abc.Iterable) and 
        not isinstance(o, memoryview) and 
        not hasattr(o, "isalpha")
    )


def getItems(o):
    from collections import abc
    
    if not isinstance(o, abc.Iterable):
        raise TypeError("object must be an iterable")
    
    if isinstance(o, abc.Mapping):
        return dict.items
    
    return enumerate


def nil(x):
    return x


_freeze_conversion_map = frozendict({
    MutableMapping: frozendict, 
    bytearray: bytes, 
    MutableSequence: tuple, 
    MutableSet: frozenset,
    Enum: nil,
})

_freeze_conversion_map_custom = {}


class FreezeError(Exception):
    pass


class FreezeWarning(UserWarning):
    pass


def register(to_convert, converter, *, inverse = False):
    r"""
    Adds a `converter` for a type `to_convert`. `converter`
    must be callable. The new converter will be used by `deepfreeze()`
    and has precedence over any previous converter.
    
    If `to_covert` has already a converter, a FreezeWarning is raised.
    
    If `inverse` is True, the conversion is considered from an immutable 
    type to a mutable one. This make it possible to convert mutable
    objects nested in the registered immutable one.
    """
    
    if not issubclass(type(to_convert), type):
        raise ValueError(
            f"`to_convert` parameter must be a type, {to_convert} found"
        )
    
    try:
        converter.__call__
    except AttributeError:
        raise ValueError(
            f"`converter` parameter must be a callable, {converter}" +
            "found"
        )
    
    if inverse:
        freeze_conversion_map = getFreezeConversionInverseMap()
    else:
        freeze_conversion_map = getFreezeConversionMap()
    
    if to_convert in freeze_conversion_map:
        import warnings
        
        warnings.warn(
            f"{to_convert.__name__} is already in the conversion map",
            FreezeWarning
        )
    
    if inverse:
        freeze_conversion_map = _freeze_conversion_inverse_map_custom
    else:
        freeze_conversion_map = _freeze_conversion_map_custom
    
    freeze_conversion_map[to_convert] = converter


def unregister(type, inverse = False):
    r"""
    Unregister a type from custom conversion. If `inverse` is `True`,
    the unregistered conversion is an inverse conversion
    (see `register()`).
    """
    
    if inverse:
        freeze_conversion_map = _freeze_conversion_inverse_map_custom
    else:
        freeze_conversion_map = _freeze_conversion_map_custom
    
    try:
        del freeze_conversion_map[type]
    except KeyError:
        raise FreezeError(f"{type.__name__} is not registered")


def getFreezeConversionMap():
    return _freeze_conversion_map | _freeze_conversion_map_custom


_freeze_conversion_inverse_map = frozendict({
    frozendict: dict, 
    MappingProxyType: dict, 
    tuple: list, 
})

_freeze_conversion_inverse_map_custom = {}


def getFreezeConversionInverseMap():
    return (
        _freeze_conversion_inverse_map |
        _freeze_conversion_inverse_map_custom
    )


_freeze_types = (
    [x for x in _freeze_conversion_map] +
    [x for x in _freeze_conversion_inverse_map]
)


def getFreezeTypes():
    return (tuple(
        _freeze_types + 
        [x for x in _freeze_conversion_map_custom] + 
        [x for x in _freeze_conversion_inverse_map_custom]
    ))


_freeze_types_plain = (MutableSet, bytearray, array)


def deepfreeze(
        o,
        custom_converters = None,
        custom_inverse_converters = None
):
    r"""
    Converts the object and all the objects nested in it in its
    immutable counterparts.
    
    The conversion map is in getFreezeConversionMap().
    
    You can register a new conversion using `register()` You can also
    pass a map of custom converters with `custom_converters` and a map
    of custom inverse converters with `custom_inverse_converters`,
    without using `register()`.
    
    By default, if the type is not registered and has a `__dict__`
    attribute, it's converted to the `frozendict` of that `__dict__`.
    
    This function assumes that hashable == immutable (that is not
    always true).
    
    This function uses recursion, with all the limits of recursions in
    Python.
    
    Where is a good old tail call when you need it?
    """
    
    from frozendict import frozendict
    
    if custom_converters is None:
        custom_converters = frozendict()
    
    if custom_inverse_converters is None:
        custom_inverse_converters = frozendict()
    
    for type_i, converter in custom_converters.items():
        if not issubclass(type(type_i), type):
            raise ValueError(
                f"{type_i} in `custom_converters` parameter is not a " +
                "type"
            )
        
        try:
            converter.__call__
        except AttributeError:
            raise ValueError(
                f"converter for {type_i} in `custom_converters` " + 
                "parameter is not a callable"
            )
    
    for type_i, converter in custom_inverse_converters.items():
        if not issubclass(type(type_i), type):
            raise ValueError(
                f"{type_i} in `custom_inverse_converters` parameter " +
                "is not a type"
            )
        
        try:
            converter.__call__
        except AttributeError:
            raise ValueError(
                f"converter for {type_i} in  " +
                "`custom_inverse_converters`parameter is not a callable"
            )
    
    type_o = type(o)
    
    freeze_types = tuple(custom_converters.keys()) + getFreezeTypes()
    
    base_type_o = None
    
    for freeze_type in freeze_types:
        if isinstance(o, freeze_type):
            base_type_o = freeze_type
            break
    
    if base_type_o is None:
        # this is before hash check because all object in Python are
        # hashable by default, if not explicitly suppressed
        try:
            o.__dict__
        except AttributeError:
            pass
        else:
            return frozendict(o.__dict__)
        
        try:
            hash(o)
        except TypeError:
            pass
        else:
            # without a converter, we can only hope that
            # hashable == immutable
            return o
        
        supported_types = ", ".join((x.__name__ for x in freeze_types))
        
        err = (
            f"type {type_o} is not hashable or is not equal or a " +
            f"subclass of the supported types: {supported_types}"
        )
        
        raise TypeError(err)
    
    freeze_conversion_map = getFreezeConversionMap()
    
    freeze_conversion_map = freeze_conversion_map | custom_converters
    
    if base_type_o in _freeze_types_plain:
        return freeze_conversion_map[base_type_o](o)
    
    if not isIterableNotString(o):
        return freeze_conversion_map[base_type_o](o)
    
    freeze_conversion_inverse_map = getFreezeConversionInverseMap()
    
    freeze_conversion_inverse_map = (
        freeze_conversion_inverse_map |
        custom_inverse_converters
    )
    
    frozen_type = base_type_o in freeze_conversion_inverse_map
    
    if frozen_type:
        o = freeze_conversion_inverse_map[base_type_o](o)
    
    from copy import copy
    
    o_copy = copy(o)
    
    for k, v in getItems(o_copy)(o_copy):
        o_copy[k] = deepfreeze(
            v,
            custom_converters = custom_converters,
            custom_inverse_converters = custom_inverse_converters
        )
    
    try:
        freeze = freeze_conversion_map[base_type_o]
    except KeyError:
        if frozen_type:
            freeze = type_o
        else:  # pragma: no cover
            raise
    
    return freeze(o_copy)


__all__ = (
    deepfreeze.__name__, 
    register.__name__, 
    unregister.__name__, 
    getFreezeConversionMap.__name__, 
    getFreezeConversionInverseMap.__name__, 
    FreezeError.__name__, 
    FreezeWarning.__name__, 
)

del MappingProxyType
del array
del frozendict
del MutableMapping
del MutableSequence
del MutableSet
del Enum
