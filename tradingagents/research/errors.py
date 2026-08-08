"""Typed failures at external research-provider boundaries."""


class ForecastUnavailableError(RuntimeError):
    """The forecast provider could not return a usable structured response."""


class OutcomeUnavailableError(RuntimeError):
    """The outcome provider could not complete an observation request."""
