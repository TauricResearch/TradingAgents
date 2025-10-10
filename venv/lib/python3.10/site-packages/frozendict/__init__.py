r"""
Provides frozendict, a simple immutable dictionary.
"""

try:   # pragma: no cover
    from ._frozendict import *
    c_ext = True
    # noinspection PyUnresolvedReferences
    del _frozendict
except ImportError:
    from ._frozendict_py import *
    c_ext = False

from .version import version as __version__
from . import monkeypatch
from .cool import *
from . import cool


def _getFrozendictJsonEncoder(BaseJsonEncoder = None):
    if BaseJsonEncoder is None:  # pragma: no cover
        from json.encoder import JSONEncoder
        
        BaseJsonEncoder = JSONEncoder
    
    class FrozendictJsonEncoderInternal(BaseJsonEncoder):
        def default(self, obj):
            if isinstance(obj, frozendict):  # pragma: no cover
                # TODO create a C serializer
                return dict(obj)
            
            return BaseJsonEncoder.default(
                self,
                obj
            )  # pragma: no cover
    
    return FrozendictJsonEncoderInternal


FrozendictJsonEncoder = _getFrozendictJsonEncoder()
monkeypatch.patchOrUnpatchAll(patch = True, warn = False)


from collections.abc import Mapping

# noinspection PyUnresolvedReferences
Mapping.register(frozendict)
del Mapping


if c_ext:  # pragma: no cover
    __all__ = (frozendict.__name__, )
else:
    __all__ = _frozendict_py.__all__
    del _frozendict_py

# TODO deprecated, to remove in future versions
FrozenOrderedDict = frozendict

__all__ += cool.__all__
__all__ += (FrozendictJsonEncoder.__name__, "FrozenOrderedDict")
