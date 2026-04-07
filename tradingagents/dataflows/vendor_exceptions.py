class VendorInputError(ValueError):
    """Raised when the user input is invalid and should not trigger vendor fallback."""


class VendorConfigurationError(RuntimeError):
    """Raised when a vendor is unavailable because credentials or config are missing."""


class VendorTransientError(RuntimeError):
    """Raised when a vendor hit a transient/network/service issue."""


class VendorMalformedResponseError(RuntimeError):
    """Raised when a vendor response is structurally invalid."""
