# Apache 2.0 License
# Vendored from https://github.com/psf/requests/blob/main/src/requests/exceptions.py
# With our own addtions

import json
from typing import Literal, Union

from ..const import CurlECode
from ..curl import CurlError


# Note IOError is an alias of OSError in Python 3.x
class RequestException(CurlError, OSError):
    """Base exception for curl_cffi.requests package"""

    def __init__(
        self,
        msg,
        code: Union[CurlECode, Literal[0]] = 0,
        response=None,
        *args,
        **kwargs,
    ):
        super().__init__(msg, code, *args, **kwargs)
        self.response = response


class CookieConflict(RequestException):
    """Same cookie exists for different domains."""


class SessionClosed(RequestException):
    """The session has already been closed."""


class ImpersonateError(RequestException):
    """The impersonate config was wrong or impersonate failed."""


# not used
class InvalidJSONError(RequestException):
    """A JSON error occurred. not used"""


# not used
class JSONDecodeError(InvalidJSONError, json.JSONDecodeError):
    """Couldn't decode the text into json. not used"""


class HTTPError(RequestException):
    """An HTTP error occurred."""


class IncompleteRead(HTTPError):
    """Incomplete read of content"""


class ConnectionError(RequestException):
    """A Connection error occurred."""


class DNSError(ConnectionError):
    """Could not resolve"""


class ProxyError(RequestException):
    """A proxy error occurred."""


class SSLError(ConnectionError):
    """An SSL error occurred."""


class CertificateVerifyError(SSLError):
    """Raised when certificate validated has failed"""


class Timeout(RequestException):
    """The request timed out."""


# not used
class ConnectTimeout(ConnectionError, Timeout):
    """The request timed out while trying to connect to the remote server.

    Requests that produced this error are safe to retry.

    not used
    """


# not used
class ReadTimeout(Timeout):
    """The server did not send any data in the allotted amount of time. not used"""


# not used
class URLRequired(RequestException):
    """A valid URL is required to make a request. not used"""


class TooManyRedirects(RequestException):
    """Too many redirects."""


# not used
class MissingSchema(RequestException, ValueError):
    """The URL scheme (e.g. http or https) is missing. not used"""


class InvalidSchema(RequestException, ValueError):
    """The URL scheme provided is either invalid or unsupported. not used"""


class InvalidURL(RequestException, ValueError):
    """The URL provided was somehow invalid."""


# not used
class InvalidHeader(RequestException, ValueError):
    """The header value provided was somehow invalid. not used"""


# not used
class InvalidProxyURL(InvalidURL):
    """The proxy URL provided is invalid. not used"""


# not used
class ChunkedEncodingError(RequestException):
    """The server declared chunked encoding but sent an invalid chunk. not used"""


# not used
class ContentDecodingError(RequestException):
    """Failed to decode response content. not used"""


# not used
class StreamConsumedError(RequestException, TypeError):
    """The content for this response was already consumed. not used"""


# does not support
class RetryError(RequestException):
    """Custom retries logic failed. not used"""


# not used
class UnrewindableBodyError(RequestException):
    """Requests encountered an error when trying to rewind a body. not used"""


class InterfaceError(RequestException):
    """A specified outgoing interface could not be used."""


# Warnings


# TODO: use this warning as a base
class RequestsWarning(Warning):
    """Base warning for Requests. not used"""


# not used
class FileModeWarning(RequestsWarning, DeprecationWarning):
    """A file was opened in text mode, but Requests determined its binary length.
    not used"""


# not used
class RequestsDependencyWarning(RequestsWarning):
    """An imported dependency doesn't match the expected version range."""


CODE2ERROR = {
    0: RequestException,
    CurlECode.UNSUPPORTED_PROTOCOL: InvalidSchema,
    CurlECode.URL_MALFORMAT: InvalidURL,
    CurlECode.COULDNT_RESOLVE_PROXY: ProxyError,
    CurlECode.COULDNT_RESOLVE_HOST: DNSError,
    CurlECode.COULDNT_CONNECT: ConnectionError,
    CurlECode.WEIRD_SERVER_REPLY: ConnectionError,
    CurlECode.REMOTE_ACCESS_DENIED: ConnectionError,
    CurlECode.HTTP2: HTTPError,
    CurlECode.HTTP_RETURNED_ERROR: HTTPError,
    CurlECode.WRITE_ERROR: RequestException,
    CurlECode.READ_ERROR: RequestException,
    CurlECode.OUT_OF_MEMORY: RequestException,
    CurlECode.OPERATION_TIMEDOUT: Timeout,
    CurlECode.SSL_CONNECT_ERROR: SSLError,
    CurlECode.INTERFACE_FAILED: InterfaceError,
    CurlECode.TOO_MANY_REDIRECTS: TooManyRedirects,
    CurlECode.UNKNOWN_OPTION: RequestException,
    CurlECode.SETOPT_OPTION_SYNTAX: RequestException,
    CurlECode.GOT_NOTHING: ConnectionError,
    CurlECode.SSL_ENGINE_NOTFOUND: SSLError,
    CurlECode.SSL_ENGINE_SETFAILED: SSLError,
    CurlECode.SEND_ERROR: ConnectionError,
    CurlECode.RECV_ERROR: ConnectionError,
    CurlECode.SSL_CERTPROBLEM: SSLError,
    CurlECode.SSL_CIPHER: SSLError,
    CurlECode.PEER_FAILED_VERIFICATION: CertificateVerifyError,
    CurlECode.BAD_CONTENT_ENCODING: HTTPError,
    CurlECode.SSL_ENGINE_INITFAILED: SSLError,
    CurlECode.SSL_CACERT_BADFILE: SSLError,
    CurlECode.SSL_CRL_BADFILE: SSLError,
    CurlECode.SSL_ISSUER_ERROR: SSLError,
    CurlECode.SSL_PINNEDPUBKEYNOTMATCH: SSLError,
    CurlECode.SSL_INVALIDCERTSTATUS: SSLError,
    CurlECode.HTTP2_STREAM: HTTPError,
    CurlECode.HTTP3: HTTPError,
    CurlECode.QUIC_CONNECT_ERROR: ConnectionError,
    CurlECode.PROXY: ProxyError,
    CurlECode.SSL_CLIENTCERT: SSLError,
    CurlECode.ECH_REQUIRED: SSLError,
    CurlECode.PARTIAL_FILE: IncompleteRead,
}


# credits: https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/networking/_curlcffi.py#L241
# Unlicense
def code2error(code: Union[CurlECode, Literal[0]], msg: str):
    if code == CurlECode.RECV_ERROR and "CONNECT" in msg:
        return ProxyError
    return CODE2ERROR.get(code, RequestException)
