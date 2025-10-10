# for compatibility with 0.5.x

__all__ = ["CurlError", "RequestsError", "CookieConflict", "SessionClosed"]

from ..curl import CurlError
from .exceptions import CookieConflict, SessionClosed
from .exceptions import RequestException as RequestsError
