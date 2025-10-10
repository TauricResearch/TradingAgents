from .. import backends

backends._QT_FORCE_QT5_BINDING = True
from .backend_qtcairo import (  # noqa: F401, E402 # pylint: disable=W0611
    _BackendQTCairo, FigureCanvasQTCairo, FigureCanvasCairo, FigureCanvasQT
)


@_BackendQTCairo.export
class _BackendQT5Cairo(_BackendQTCairo):
    pass
