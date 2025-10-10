from .registry import BackendFilter, backend_registry  # noqa: F401

# NOTE: plt.switch_backend() (called at import time) will add a "backend"
# attribute here for backcompat.
_QT_FORCE_QT5_BINDING = False
