class DataVendorError(Exception):
    """Raised by a vendor implementation when it cannot serve a request
    (auth/config missing, network error, daemon down). Signals route_to_vendor
    to try the next vendor in the fallback chain instead of failing the run."""
