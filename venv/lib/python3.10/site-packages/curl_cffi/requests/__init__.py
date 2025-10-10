__all__ = [
    "Session",
    "AsyncSession",
    "BrowserType",
    "BrowserTypeLiteral",
    "CurlWsFlag",
    "request",
    "head",
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "RequestsError",
    "Cookies",
    "Headers",
    "Request",
    "Response",
    "AsyncWebSocket",
    "WebSocket",
    "WebSocketError",
    "WebSocketClosed",
    "WebSocketTimeout",
    "WsCloseCode",
    "ExtraFingerprints",
    "CookieTypes",
    "HeaderTypes",
    "ProxySpec",
]

from typing import Optional, TYPE_CHECKING, TypedDict

from ..const import CurlWsFlag
from .cookies import Cookies, CookieTypes
from .errors import RequestsError
from .headers import Headers, HeaderTypes
from .impersonate import BrowserType, BrowserTypeLiteral, ExtraFingerprints
from .models import Request, Response
from .session import (
    AsyncSession,
    HttpMethod,
    ProxySpec,
    Session,
    ThreadType,
    RequestParams,
    Unpack,
)
from .websockets import (
    AsyncWebSocket,
    WebSocket,
    WebSocketClosed,
    WebSocketError,
    WebSocketTimeout,
    WsCloseCode,
)

if TYPE_CHECKING:

    class SessionRequestParams(RequestParams, total=False):
        thread: Optional[ThreadType]
        curl_options: Optional[dict]
        debug: Optional[bool]
else:
    SessionRequestParams = TypedDict


def request(
    method: HttpMethod,
    url: str,
    thread: Optional[ThreadType] = None,
    curl_options: Optional[dict] = None,
    debug: Optional[bool] = None,
    **kwargs: Unpack[RequestParams],
) -> Response:
    """Send an http request.

    Parameters:
        method: http method for the request: GET/POST/PUT/DELETE etc.
        url: url for the requests.
        params: query string for the requests.
        data: form values(dict/list/tuple) or binary data to use in body,
            ``Content-Type: application/x-www-form-urlencoded`` will be added if a dict
            is given.
        json: json values to use in body, `Content-Type: application/json` will be added
            automatically.
        headers: headers to send.
        cookies: cookies to use.
        files: not supported, use ``multipart`` instead.
        auth: HTTP basic auth, a tuple of (username, password), only basic auth is
            supported.
        timeout: how many seconds to wait before giving up.
        allow_redirects: whether to allow redirection.
        max_redirects: max redirect counts, default 30, use -1 for unlimited.
        proxies: dict of proxies to use, prefer to use ``proxy`` if they are the same.
            format: ``{"http": proxy_url, "https": proxy_url}``.
        proxy: proxy to use, format: "http://user@pass:proxy_url".
            Can't be used with `proxies` parameter.
        proxy_auth: HTTP basic auth for proxy, a tuple of (username, password).
        verify: whether to verify https certs.
        referer: shortcut for setting referer header.
        accept_encoding: shortcut for setting accept-encoding header.
        content_callback: a callback function to receive response body.
            ``def callback(chunk: bytes) -> None:``
        impersonate: which browser version to impersonate.
        ja3: ja3 string to impersonate.
        akamai: akamai string to impersonate.
        extra_fp: extra fingerprints options, in complement to ja3 and akamai strings.
        thread: thread engine to use for working with other thread implementations.
            choices: eventlet, gevent.
        default_headers: whether to set default browser headers when impersonating.
        default_encoding: encoding for decoding response content if charset is not found
            in headers. Defaults to "utf-8". Can be set to a callable for automatic
            detection.
        quote: Set characters to be quoted, i.e. percent-encoded. Default safe string
            is ``!#$%&'()*+,/:;=?@[]~``. If set to a sting, the character will be
            removed from the safe string, thus quoted. If set to False, the url will be
            kept as is, without any automatic percent-encoding, you must encode the URL
            yourself.
        curl_options: extra curl options to use.
        http_version: limiting http version, defaults to http2.
        debug: print extra curl debug info.
        interface: which interface to use.
        cert: a tuple of (cert, key) filenames for client cert.
        stream: streaming the response, default False.
        max_recv_speed: maximum receive speed, bytes per second.
        multipart: upload files using the multipart format, see examples for details.
        discard_cookies: discard cookies from server. Default to False.

    Returns:
        A ``Response`` object.
    """
    debug = False if debug is None else debug
    with Session(thread=thread, curl_options=curl_options, debug=debug) as s:
        return s.request(method=method, url=url, **kwargs)


def head(url: str, **kwargs: Unpack[SessionRequestParams]):
    return request(method="HEAD", url=url, **kwargs)


def get(url: str, **kwargs: Unpack[SessionRequestParams]):
    return request(method="GET", url=url, **kwargs)


def post(url: str, **kwargs: Unpack[SessionRequestParams]):
    return request(method="POST", url=url, **kwargs)


def put(url: str, **kwargs: Unpack[SessionRequestParams]):
    return request(method="PUT", url=url, **kwargs)


def patch(url: str, **kwargs: Unpack[SessionRequestParams]):
    return request(method="PATCH", url=url, **kwargs)


def delete(url: str, **kwargs: Unpack[SessionRequestParams]):
    return request(method="DELETE", url=url, **kwargs)


def options(url: str, **kwargs: Unpack[SessionRequestParams]):
    return request(method="OPTIONS", url=url, **kwargs)


def trace(url: str, **kwargs: Unpack[SessionRequestParams]):
    return request(method="TRACE", url=url, **kwargs)


def query(url: str, **kwargs: Unpack[SessionRequestParams]):
    return request(method="QUERY", url=url, **kwargs)
