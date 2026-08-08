"""Small helpers for safe, low-cardinality diagnostics."""


def safe_exception_type(exc: BaseException) -> str:
    """Return a bounded exception class name without rendering its message."""
    name = type(exc).__name__
    if (
        1 <= len(name) <= 64
        and name.isascii()
        and name[0].isalpha()
        and all(char.isalnum() or char == "_" for char in name)
    ):
        return name
    return "Exception"
