class DataVendorUnavailable(Exception):
    """Raised when a vendor cannot serve a request and fallback should be attempted."""
