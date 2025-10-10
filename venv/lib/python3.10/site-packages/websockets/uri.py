from __future__ import annotations

import dataclasses
import urllib.parse
import urllib.request

from .exceptions import InvalidProxy, InvalidURI


__all__ = ["parse_uri", "WebSocketURI"]


# All characters from the gen-delims and sub-delims sets in RFC 3987.
DELIMS = ":/?#[]@!$&'()*+,;="


@dataclasses.dataclass
class WebSocketURI:
    """
    WebSocket URI.

    Attributes:
        secure: :obj:`True` for a ``wss`` URI, :obj:`False` for a ``ws`` URI.
        host: Normalized to lower case.
        port: Always set even if it's the default.
        path: May be empty.
        query: May be empty if the URI doesn't include a query component.
        username: Available when the URI contains `User Information`_.
        password: Available when the URI contains `User Information`_.

    .. _User Information: https://datatracker.ietf.org/doc/html/rfc3986#section-3.2.1

    """

    secure: bool
    host: str
    port: int
    path: str
    query: str
    username: str | None = None
    password: str | None = None

    @property
    def resource_name(self) -> str:
        if self.path:
            resource_name = self.path
        else:
            resource_name = "/"
        if self.query:
            resource_name += "?" + self.query
        return resource_name

    @property
    def user_info(self) -> tuple[str, str] | None:
        if self.username is None:
            return None
        assert self.password is not None
        return (self.username, self.password)


def parse_uri(uri: str) -> WebSocketURI:
    """
    Parse and validate a WebSocket URI.

    Args:
        uri: WebSocket URI.

    Returns:
        Parsed WebSocket URI.

    Raises:
        InvalidURI: If ``uri`` isn't a valid WebSocket URI.

    """
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme not in ["ws", "wss"]:
        raise InvalidURI(uri, "scheme isn't ws or wss")
    if parsed.hostname is None:
        raise InvalidURI(uri, "hostname isn't provided")
    if parsed.fragment != "":
        raise InvalidURI(uri, "fragment identifier is meaningless")

    secure = parsed.scheme == "wss"
    host = parsed.hostname
    port = parsed.port or (443 if secure else 80)
    path = parsed.path
    query = parsed.query
    username = parsed.username
    password = parsed.password
    # urllib.parse.urlparse accepts URLs with a username but without a
    # password. This doesn't make sense for HTTP Basic Auth credentials.
    if username is not None and password is None:
        raise InvalidURI(uri, "username provided without password")

    try:
        uri.encode("ascii")
    except UnicodeEncodeError:
        # Input contains non-ASCII characters.
        # It must be an IRI. Convert it to a URI.
        host = host.encode("idna").decode()
        path = urllib.parse.quote(path, safe=DELIMS)
        query = urllib.parse.quote(query, safe=DELIMS)
        if username is not None:
            assert password is not None
            username = urllib.parse.quote(username, safe=DELIMS)
            password = urllib.parse.quote(password, safe=DELIMS)

    return WebSocketURI(secure, host, port, path, query, username, password)


@dataclasses.dataclass
class Proxy:
    """
    Proxy.

    Attributes:
        scheme: ``"socks5h"``, ``"socks5"``, ``"socks4a"``, ``"socks4"``,
            ``"https"``, or ``"http"``.
        host: Normalized to lower case.
        port: Always set even if it's the default.
        username: Available when the proxy address contains `User Information`_.
        password: Available when the proxy address contains `User Information`_.

    .. _User Information: https://datatracker.ietf.org/doc/html/rfc3986#section-3.2.1

    """

    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    @property
    def user_info(self) -> tuple[str, str] | None:
        if self.username is None:
            return None
        assert self.password is not None
        return (self.username, self.password)


def parse_proxy(proxy: str) -> Proxy:
    """
    Parse and validate a proxy.

    Args:
        proxy: proxy.

    Returns:
        Parsed proxy.

    Raises:
        InvalidProxy: If ``proxy`` isn't a valid proxy.

    """
    parsed = urllib.parse.urlparse(proxy)
    if parsed.scheme not in ["socks5h", "socks5", "socks4a", "socks4", "https", "http"]:
        raise InvalidProxy(proxy, f"scheme {parsed.scheme} isn't supported")
    if parsed.hostname is None:
        raise InvalidProxy(proxy, "hostname isn't provided")
    if parsed.path not in ["", "/"]:
        raise InvalidProxy(proxy, "path is meaningless")
    if parsed.query != "":
        raise InvalidProxy(proxy, "query is meaningless")
    if parsed.fragment != "":
        raise InvalidProxy(proxy, "fragment is meaningless")

    scheme = parsed.scheme
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    username = parsed.username
    password = parsed.password
    # urllib.parse.urlparse accepts URLs with a username but without a
    # password. This doesn't make sense for HTTP Basic Auth credentials.
    if username is not None and password is None:
        raise InvalidProxy(proxy, "username provided without password")

    try:
        proxy.encode("ascii")
    except UnicodeEncodeError:
        # Input contains non-ASCII characters.
        # It must be an IRI. Convert it to a URI.
        host = host.encode("idna").decode()
        if username is not None:
            assert password is not None
            username = urllib.parse.quote(username, safe=DELIMS)
            password = urllib.parse.quote(password, safe=DELIMS)

    return Proxy(scheme, host, port, username, password)


def get_proxy(uri: WebSocketURI) -> str | None:
    """
    Return the proxy to use for connecting to the given WebSocket URI, if any.

    """
    if urllib.request.proxy_bypass(f"{uri.host}:{uri.port}"):
        return None

    # According to the _Proxy Usage_ section of RFC 6455, use a SOCKS5 proxy if
    # available, else favor the proxy for HTTPS connections over the proxy for
    # HTTP connections.

    # The priority of a proxy for WebSocket connections is unspecified. We give
    # it the highest priority. This makes it easy to configure a specific proxy
    # for websockets.

    # getproxies() may return SOCKS proxies as {"socks": "http://host:port"} or
    # as {"https": "socks5h://host:port"} depending on whether they're declared
    # in the operating system or in environment variables.

    proxies = urllib.request.getproxies()
    if uri.secure:
        schemes = ["wss", "socks", "https"]
    else:
        schemes = ["ws", "socks", "https", "http"]

    for scheme in schemes:
        proxy = proxies.get(scheme)
        if proxy is not None:
            if scheme == "socks" and proxy.startswith("http://"):
                proxy = "socks5h://" + proxy[7:]
            return proxy
    else:
        return None
