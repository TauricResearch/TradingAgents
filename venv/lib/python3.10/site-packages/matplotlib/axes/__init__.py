from . import _base
from ._axes import Axes

# Backcompat.
Subplot = Axes


class _SubplotBaseMeta(type):
    def __instancecheck__(self, obj):
        return (isinstance(obj, _base._AxesBase)
                and obj.get_subplotspec() is not None)


class SubplotBase(metaclass=_SubplotBaseMeta):
    pass


def subplot_class_factory(cls): return cls
