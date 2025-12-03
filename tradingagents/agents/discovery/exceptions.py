class DiscoveryError(Exception):
    pass


class NewsUnavailableError(DiscoveryError):
    pass


class DiscoveryTimeoutError(DiscoveryError):
    pass


class TickerResolutionError(DiscoveryError):
    pass
