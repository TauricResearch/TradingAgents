from .. import backends

backends._QT_FORCE_QT5_BINDING = True


from .backend_qt import (  # noqa
    SPECIAL_KEYS,
    # Public API
    cursord, _create_qApp, _BackendQT, TimerQT, MainWindow, FigureCanvasQT,
    FigureManagerQT, ToolbarQt, NavigationToolbar2QT, SubplotToolQt,
    SaveFigureQt, ConfigureSubplotsQt, RubberbandQt,
    HelpQt, ToolCopyToClipboardQT,
    # internal re-exports
    FigureCanvasBase,  FigureManagerBase, MouseButton, NavigationToolbar2,
    TimerBase, ToolContainerBase, figureoptions, Gcf
)
from . import backend_qt as _backend_qt  # noqa


@_BackendQT.export
class _BackendQT5(_BackendQT):
    pass


def __getattr__(name):
    if name == 'qApp':
        return _backend_qt.qApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
