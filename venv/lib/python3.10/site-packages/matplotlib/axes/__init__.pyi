from typing import TypeVar

from ._axes import Axes as Axes


_T = TypeVar("_T")

# Backcompat.
Subplot = Axes

class _SubplotBaseMeta(type):
    def __instancecheck__(self, obj) -> bool: ...

class SubplotBase(metaclass=_SubplotBaseMeta): ...

def subplot_class_factory(cls: type[_T]) -> type[_T]: ...
