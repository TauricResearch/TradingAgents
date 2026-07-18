"""Errors that must never be mistaken for provider/model fallback failures."""


class ObservationError(RuntimeError):
    pass


class ObservationPersistenceError(ObservationError):
    pass
