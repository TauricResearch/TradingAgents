from __future__ import annotations

__all__ = ["HttpVersionLiteral", "set_curl_options", "not_set"]


import asyncio
import math
import queue
import warnings
from collections import Counter
from io import BytesIO
from json import dumps
from typing import TYPE_CHECKING, Any, Callable, Final, Literal, Optional, Union, cast
from urllib.parse import ParseResult, parse_qsl, quote, urlencode, urljoin, urlparse

from ..const import CurlHttpVersion, CurlOpt, CurlSslVersion
from ..curl import CURL_WRITEFUNC_ERROR, CurlMime
from ..utils import CurlCffiWarning
from .cookies import Cookies
from .exceptions import ImpersonateError, InvalidURL
from .headers import Headers
from .impersonate import (
    TLS_CIPHER_NAME_MAP,
    TLS_EC_CURVES_MAP,
    TLS_VERSION_MAP,
    ExtraFingerprints,
    normalize_browser_type,
    toggle_extension,
)
from .models import Request

if TYPE_CHECKING:
    from ..curl import Curl
    from .cookies import CookieTypes
    from .headers import HeaderTypes
    from .impersonate import BrowserTypeLiteral, ExtraFpDict
    from .session import ProxySpec


HttpMethod = Literal[
    "GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE", "PATCH", "QUERY"
]

HttpVersionLiteral = Literal["v1", "v2", "v2tls", "v2_prior_knowledge", "v3", "v3only"]

SAFE_CHARS = set("!#$%&'()*+,/:;=?@[]~")

not_set: Final[Any] = object()


# ruff: noqa: SIM116
def normalize_http_version(
    version: Union[CurlHttpVersion, HttpVersionLiteral],
) -> CurlHttpVersion:
    if version == "v1":
        return CurlHttpVersion.V1_1
    elif version == "v3":
        return CurlHttpVersion.V3
    elif version == "v3only":
        return CurlHttpVersion.V3ONLY
    elif version == "v2":
        return CurlHttpVersion.V2_0
    elif version == "v2tls":
        return CurlHttpVersion.V2TLS
    elif version == "v2_prior_knowledge":
        return CurlHttpVersion.V2_PRIOR_KNOWLEDGE

    return version  # type: ignore


def is_absolute_url(url: str) -> bool:
    """Check if the provided url is an absolute url"""
    parsed_url = urlparse(url)
    return bool(parsed_url.scheme and parsed_url.hostname)


def quote_path_and_params(url: str, quote_str: str = ""):
    safe = "".join(SAFE_CHARS - set(quote_str))
    parsed_url = urlparse(url)
    parsed_get_args = parse_qsl(parsed_url.query, keep_blank_values=True)
    encoded_get_args = urlencode(parsed_get_args, doseq=True, safe=safe)
    return ParseResult(
        parsed_url.scheme,
        parsed_url.netloc,
        quote(parsed_url.path, safe=safe),
        parsed_url.params,
        encoded_get_args,
        parsed_url.fragment,
    ).geturl()


def update_url_params(url: str, params: Union[dict, list, tuple]) -> str:
    """Add URL query params to provided URL being aware of existing.

    Args:
        url: string of target URL
        params: dict containing requested params to be added

    Returns:
        string with updated URL

    >> url = 'http://stackoverflow.com/test?answers=true'
    >> new_params = {'answers': False, 'data': ['some','values']}
    >> update_url_params(url, new_params)
    'http://stackoverflow.com/test?data=some&data=values&answers=false'
    """
    # No need to unquote, since requote_uri will be called later.
    parsed_url = urlparse(url)

    # Extracting URL arguments from parsed URL, NOTE the result is a list, not dict
    parsed_get_args = parse_qsl(parsed_url.query, keep_blank_values=True)

    # Merging URL arguments dict with new params
    old_args_counter = Counter(x[0] for x in parsed_get_args)
    if isinstance(params, dict):
        params = list(params.items())
    new_args_counter = Counter(x[0] for x in params)
    for key, value in params:
        # Bool and Dict values should be converted to json-friendly values
        if isinstance(value, (bool, dict)):
            value = dumps(value)
        # 1 to 1 mapping, we have to search and update it.
        if old_args_counter.get(key) == 1 and new_args_counter.get(key) == 1:
            parsed_get_args = [
                (x if x[0] != key else (key, value)) for x in parsed_get_args
            ]
        else:
            parsed_get_args.append((key, value))

    # Converting URL argument to proper query string
    encoded_get_args = urlencode(parsed_get_args, doseq=True)

    # Creating new parsed result object based on provided with new
    # URL arguments. Same thing happens inside of urlparse.
    new_url = ParseResult(
        parsed_url.scheme,
        parsed_url.netloc,
        parsed_url.path,
        parsed_url.params,
        encoded_get_args,
        parsed_url.fragment,
    ).geturl()

    return new_url


# Adapted from: https://github.com/psf/requests/blob/1ae6fc3137a11e11565ed22436aa1e77277ac98c/src%2Frequests%2Futils.py#L633-L682
# License: Apache 2.0

# The unreserved URI characters (RFC 3986)
UNRESERVED_SET = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz" + "0123456789-._~"
)


def unquote_unreserved(uri: str) -> str:
    """Un-escape any percent-escape sequences in a URI that are unreserved
    characters. This leaves all reserved, illegal and non-ASCII bytes encoded.
    """
    parts = uri.split("%")
    for i in range(1, len(parts)):
        h = parts[i][0:2]
        if len(h) == 2 and h.isalnum():
            try:
                c = chr(int(h, 16))
            except ValueError as e:
                raise InvalidURL(f"Invalid percent-escape sequence: '{h}'") from e

            if c in UNRESERVED_SET:
                parts[i] = c + parts[i][2:]
            else:
                parts[i] = f"%{parts[i]}"
        else:
            parts[i] = f"%{parts[i]}"
    return "".join(parts)


def requote_uri(uri: str) -> str:
    """Re-quote the given URI.

    This function passes the given URI through an unquote/quote cycle to
    ensure that it is fully and consistently quoted.
    """
    safe_with_percent = "!#$%&'()*+,/:;=?@[]~|"
    safe_without_percent = "!#$&'()*+,/:;=?@[]~|"
    try:
        # Unquote only the unreserved characters
        # Then quote only illegal characters (do not quote reserved,
        # unreserved, or '%')
        return quote(unquote_unreserved(uri), safe=safe_with_percent)
    except InvalidURL:
        # We couldn't unquote the given URI, so let's try quoting it, but
        # there may be unquoted '%'s in the URI. We need to make sure they're
        # properly quoted so they do not cause issues elsewhere.
        return quote(uri, safe=safe_without_percent)


# TODO: should we move this function to headers.py?
def update_header_line(
    header_lines: list[str], key: str, value: str, replace: bool = False
):
    """Update header line list by key value pair."""
    found = False
    for idx, line in enumerate(header_lines):
        if line.lower().startswith(key.lower() + ":"):
            found = True
            if replace:
                header_lines[idx] = f"{key}: {value}"
            break
    if not found:
        header_lines.append(f"{key}: {value}")


def peek_queue(q: queue.Queue, default=None):
    try:
        return q.queue[0]
    except IndexError:
        return default


def peek_aio_queue(q: asyncio.Queue, default=None):
    try:
        return q._queue[0]  # type: ignore
    except IndexError:
        return default


def toggle_extensions_by_ids(curl: Curl, extension_ids):
    # TODO: find a better representation, rather than magic numbers
    default_enabled = {0, 10, 11, 13, 16, 23, 35, 43, 45, 51, 65281}

    to_enable_ids = extension_ids - default_enabled
    for ext_id in to_enable_ids:
        toggle_extension(curl, ext_id, enable=True)

    # print("to_enable: ", to_enable_ids)

    to_disable_ids = default_enabled - extension_ids
    for ext_id in to_disable_ids:
        toggle_extension(curl, ext_id, enable=False)

    # print("to_disable: ", to_disable_ids)


def set_ja3_options(curl: Curl, ja3: str, permute: bool = False):
    """
    Detailed explanation: https://engineering.salesforce.com/tls-fingerprinting-with-ja3-and-ja3s-247362855967/
    """
    tls_version, ciphers, extensions, curves, curve_formats = ja3.split(",")

    curl_tls_version = TLS_VERSION_MAP[int(tls_version)]
    curl.setopt(CurlOpt.SSLVERSION, curl_tls_version | CurlSslVersion.MAX_DEFAULT)
    assert curl_tls_version == CurlSslVersion.TLSv1_2, "Only TLS v1.2 works for now."

    cipher_names = []
    for cipher in ciphers.split("-"):
        cipher_id = int(cipher)
        cipher_name = TLS_CIPHER_NAME_MAP.get(cipher_id)
        if not cipher_name:
            raise ImpersonateError(f"Cipher {hex(cipher_id)} is not found")
        cipher_names.append(cipher_name)

    curl.setopt(CurlOpt.SSL_CIPHER_LIST, ":".join(cipher_names))

    if extensions.endswith("-21"):
        extensions = extensions[:-3]
        warnings.warn(
            "Padding(21) extension found in ja3 string, whether to add it should "
            "be managed by the SSL engine. The TLS client hello packet may contain "
            "or not contain this extension, any of which should be correct.",
            CurlCffiWarning,
            stacklevel=1,
        )
    extension_ids = set(int(e) for e in extensions.split("-"))
    toggle_extensions_by_ids(curl, extension_ids)

    if not permute:
        curl.setopt(CurlOpt.TLS_EXTENSION_ORDER, extensions)

    curve_names = []
    for curve in curves.split("-"):
        curve_id = int(curve)
        curve_name = TLS_EC_CURVES_MAP[curve_id]
        curve_names.append(curve_name)

    curl.setopt(CurlOpt.SSL_EC_CURVES, ":".join(curve_names))

    assert int(curve_formats) == 0, "Only curve_formats == 0 is supported."


def set_akamai_options(curl: Curl, akamai: str):
    """
    Detailed explanation: https://www.blackhat.com/docs/eu-17/materials/eu-17-Shuster-Passive-Fingerprinting-Of-HTTP2-Clients-wp.pdf
    """
    settings, window_update, streams, header_order = akamai.split("|")

    # For compatiblity with tls.peet.ws
    settings = settings.replace(",", ";")

    curl.setopt(CurlOpt.HTTP_VERSION, CurlHttpVersion.V2_0)

    curl.setopt(CurlOpt.HTTP2_SETTINGS, settings)
    curl.setopt(CurlOpt.HTTP2_WINDOW_UPDATE, int(window_update))

    if streams != "0":
        curl.setopt(CurlOpt.HTTP2_STREAMS, streams)

    # m,a,s,p -> masp
    # curl-impersonate only accepts masp format, without commas.
    curl.setopt(CurlOpt.HTTP2_PSEUDO_HEADERS_ORDER, header_order.replace(",", ""))


def set_extra_fp(curl: Curl, fp: ExtraFingerprints):
    if fp.tls_signature_algorithms:
        curl.setopt(CurlOpt.SSL_SIG_HASH_ALGS, ",".join(fp.tls_signature_algorithms))

    curl.setopt(CurlOpt.SSLVERSION, fp.tls_min_version | CurlSslVersion.MAX_DEFAULT)
    curl.setopt(CurlOpt.TLS_GREASE, int(fp.tls_grease))
    curl.setopt(CurlOpt.SSL_PERMUTE_EXTENSIONS, int(fp.tls_permute_extensions))
    curl.setopt(CurlOpt.SSL_CERT_COMPRESSION, fp.tls_cert_compression)
    curl.setopt(CurlOpt.STREAM_WEIGHT, fp.http2_stream_weight)
    curl.setopt(CurlOpt.STREAM_EXCLUSIVE, fp.http2_stream_exclusive)
    if fp.tls_delegated_credential:
        curl.setopt(CurlOpt.TLS_DELEGATED_CREDENTIALS, fp.tls_delegated_credential)
    if fp.tls_record_size_limit:
        curl.setopt(CurlOpt.TLS_RECORD_SIZE_LIMIT, fp.tls_record_size_limit)
    if fp.http2_no_priority:
        curl.setopt(CurlOpt.HTTP2_NO_PRIORITY, fp.http2_no_priority)


def set_curl_options(
    curl: Curl,
    method: HttpMethod,
    url: str,
    *,
    params_list: list[Union[dict, list, tuple, None]] = [],  # noqa: B006
    base_url: Optional[str] = None,
    data: Optional[Union[dict[str, str], list[tuple], str, BytesIO, bytes]] = None,
    json: Optional[dict | list] = None,
    headers_list: list[Optional[HeaderTypes]] = [],  # noqa: B006
    cookies_list: list[Optional[CookieTypes]] = [],  # noqa: B006
    files: Optional[dict] = None,
    auth: Optional[tuple[str, str]] = None,
    timeout: Optional[Union[float, tuple[float, float], object]] = not_set,
    allow_redirects: Optional[bool] = True,
    max_redirects: Optional[int] = 30,
    proxies_list: list[Optional[ProxySpec]] = [],  # noqa: B006
    proxy: Optional[str] = None,
    proxy_auth: Optional[tuple[str, str]] = None,
    verify_list: list[Union[bool, str, None]] = [],  # noqa: B006
    referer: Optional[str] = None,
    accept_encoding: Optional[str] = "gzip, deflate, br, zstd",
    content_callback: Optional[Callable] = None,
    impersonate: Optional[Union[BrowserTypeLiteral, str]] = None,
    ja3: Optional[str] = None,
    akamai: Optional[str] = None,
    extra_fp: Optional[Union[ExtraFingerprints, ExtraFpDict]] = None,
    default_headers: bool = True,
    quote: Union[str, Literal[False]] = "",
    http_version: Optional[Union[CurlHttpVersion, HttpVersionLiteral]] = None,
    interface: Optional[str] = None,
    cert: Optional[Union[str, tuple[str, str]]] = None,
    stream: Optional[bool] = None,
    max_recv_speed: int = 0,
    multipart: Optional[CurlMime] = None,
    queue_class: Any = None,
    event_class: Any = None,
    curl_options: Optional[dict[CurlOpt, str]] = None,
):
    c = curl

    method = method.upper()  # type: ignore

    # method
    if method == "POST":
        c.setopt(CurlOpt.POST, 1)
    elif method != "GET":
        c.setopt(CurlOpt.CUSTOMREQUEST, method.encode())
    if method == "HEAD":
        c.setopt(CurlOpt.NOBODY, 1)

    # url
    base_params, params = params_list
    if base_params:
        url = update_url_params(url, base_params)
    if params:
        url = update_url_params(url, params)
    if base_url:
        url = urljoin(base_url, url)
    if quote:
        url = quote_path_and_params(url, quote_str=quote)
    if quote is not False:
        url = requote_uri(url)
    c.setopt(CurlOpt.URL, url.encode())

    # data/body/json
    if isinstance(data, (dict, list, tuple)):
        body = urlencode(data).encode()
    elif isinstance(data, str):
        body = data.encode()
    elif isinstance(data, BytesIO):
        body = data.read()
    elif isinstance(data, bytes):
        body = data
    elif data is None:
        body = b""
    else:
        raise TypeError("data must be dict/list/tuple, str, BytesIO or bytes")
    if json is not None:
        body = dumps(json, separators=(",", ":")).encode()

    # Tell libcurl to be aware of bodies and related headers when,
    # 1. POST/PUT/PATCH, even if the body is empty, it's up to curl to decide what to do
    # 2. GET/DELETE with body, although it's against the RFC, some applications.
    #   e.g. Elasticsearch, use this.
    if body or method in ("POST", "PUT", "PATCH"):
        c.setopt(CurlOpt.POSTFIELDS, body)
        # necessary if body contains '\0'
        c.setopt(CurlOpt.POSTFIELDSIZE, len(body))
        if method == "GET":
            c.setopt(CurlOpt.CUSTOMREQUEST, method)

    # headers
    base_headers, headers = headers_list
    # let headers encoding take precedence over base headers encoding
    encoding = headers.encoding if isinstance(headers, Headers) else None
    h = Headers(base_headers, encoding=encoding)
    h.update(headers)

    # remove Host header if it's unnecessary, otherwise curl may get confused.
    # Host header will be automatically added by curl if it's not present.
    # https://github.com/lexiforest/curl_cffi/issues/119
    host_header = h.get("Host")
    if host_header is not None:
        u = urlparse(url)
        if host_header == u.netloc or host_header == u.hostname:
            h.pop("Host", None)

    # Make curl always include empty headers.
    # See: https://stackoverflow.com/a/32911474/1061155
    header_lines = []
    for k, v in h.multi_items():
        if v is None:
            header_lines.append(f"{k}:")  # Explictly disable this header
        elif v == "":
            header_lines.append(f"{k};")  # Add an empty valued header
        else:
            header_lines.append(f"{k}: {v}")

    # Add content-type if missing
    if json is not None:
        update_header_line(header_lines, "Content-Type", "application/json")
    if isinstance(data, dict) and method != "POST":
        update_header_line(
            header_lines, "Content-Type", "application/x-www-form-urlencoded"
        )
    if isinstance(data, (str, bytes)):
        update_header_line(header_lines, "Content-Type", "application/octet-stream")

    # Never send `Expect` header.
    update_header_line(header_lines, "Expect", "", replace=True)

    c.setopt(CurlOpt.HTTPHEADER, [h.encode() for h in header_lines])

    req = Request(url, h, method)

    # cookies
    c.setopt(CurlOpt.COOKIEFILE, b"")  # always enable the curl cookie engine first
    c.setopt(CurlOpt.COOKIELIST, "ALL")  # remove all the old cookies first.

    base_cookies, cookies = cookies_list

    if base_cookies:
        for morsel in base_cookies.get_cookies_for_curl(req):  # type: ignore
            curl.setopt(CurlOpt.COOKIELIST, morsel.to_curl_format())
    if cookies:
        temp_cookies = Cookies(cookies)
        for morsel in temp_cookies.get_cookies_for_curl(req):
            curl.setopt(CurlOpt.COOKIELIST, morsel.to_curl_format())

    # files
    if files:
        raise NotImplementedError(
            "files is not supported, use `multipart`. See examples here: "
            "https://github.com/lexiforest/curl_cffi/blob/main/examples/upload.py"
        )

    # multipart
    if multipart:
        # multipart will overrides postfields
        for k, v in cast(dict, data or {}).items():
            multipart.addpart(name=k, data=v.encode() if isinstance(v, str) else v)
        c.setopt(CurlOpt.MIMEPOST, multipart._form)

    # auth
    if auth:
        username, password = auth
        c.setopt(CurlOpt.USERNAME, username.encode())  # pyright: ignore [reportPossiblyUnboundVariable=none]
        c.setopt(CurlOpt.PASSWORD, password.encode())  # pyright: ignore [reportPossiblyUnboundVariable=none]

    # timeout
    if timeout is None:
        timeout = 0  # indefinitely

    if isinstance(timeout, tuple):
        connect_timeout, read_timeout = timeout
        all_timeout = connect_timeout + read_timeout
        c.setopt(CurlOpt.CONNECTTIMEOUT_MS, int(connect_timeout * 1000))
        if not stream:
            c.setopt(CurlOpt.TIMEOUT_MS, int(all_timeout * 1000))
        else:
            # trick from: https://github.com/lexiforest/curl_cffi/issues/156
            c.setopt(CurlOpt.LOW_SPEED_LIMIT, 1)
            c.setopt(CurlOpt.LOW_SPEED_TIME, math.ceil(all_timeout))

    elif isinstance(timeout, (int, float)):
        if not stream:
            c.setopt(CurlOpt.TIMEOUT_MS, int(timeout * 1000))
        else:
            c.setopt(CurlOpt.CONNECTTIMEOUT_MS, int(timeout * 1000))
            c.setopt(CurlOpt.LOW_SPEED_LIMIT, 1)
            c.setopt(CurlOpt.LOW_SPEED_TIME, math.ceil(timeout))

    # allow_redirects
    c.setopt(CurlOpt.FOLLOWLOCATION, int(allow_redirects))  # type: ignore

    # max_redirects
    c.setopt(CurlOpt.MAXREDIRS, max_redirects)

    # proxies
    base_proxies, proxies = proxies_list
    if proxy and proxies:
        raise TypeError("Cannot specify both 'proxy' and 'proxies'")
    if proxy:
        proxies = {"all": proxy}
    if proxies is None:
        proxies = base_proxies

    if proxies:
        # Turn on proxy_credential_no_reuse, which has the following benefits:
        # 1. New connection will be made when proxy username changed
        # 2. New TLS session will be created based on proxy address, i.e. when accessing
        #    the same site with different proxies, TLS session won't leak previous IP.
        c.setopt(CurlOpt.PROXY_CREDENTIAL_NO_REUSE, 1)

        parts = urlparse(url)
        proxy = cast(Optional[str], proxies.get(parts.scheme, proxies.get("all")))
        if parts.hostname:
            proxy = (
                proxies.get(  # type: ignore
                    f"{parts.scheme}://{parts.hostname}",
                    proxies.get(f"all://{parts.hostname}"),
                )
                or proxy
            )

        if proxy is not None:
            c.setopt(CurlOpt.PROXY, proxy)

            if parts.scheme == "https":
                if proxy.startswith("https://"):
                    warnings.warn(
                        "Make sure you are using https over https proxy, otherwise, "
                        "the proxy prefix should be 'http://' not 'https://', "
                        "see: https://github.com/lexiforest/curl_cffi/issues/6",
                        CurlCffiWarning,
                        stacklevel=2,
                    )
                # For https site with http tunnel proxy, tell curl to enable tunneling
                if not proxy.startswith("socks"):
                    c.setopt(CurlOpt.HTTPPROXYTUNNEL, 1)

            # proxy_auth
            if proxy_auth:
                username, password = proxy_auth
                c.setopt(CurlOpt.PROXYUSERNAME, username.encode())
                c.setopt(CurlOpt.PROXYPASSWORD, password.encode())

    # verify
    base_verify, verify = verify_list
    if verify is False or not base_verify and verify is None:
        c.setopt(CurlOpt.SSL_VERIFYPEER, 0)
        c.setopt(CurlOpt.SSL_VERIFYHOST, 0)

    # cert for this single request
    if isinstance(verify, str):
        c.setopt(CurlOpt.CAINFO, verify)

    # cert for the session
    if verify in (None, True) and isinstance(base_verify, str):
        c.setopt(CurlOpt.CAINFO, base_verify)

    # referer
    if referer:
        c.setopt(CurlOpt.REFERER, referer.encode())

    # accept_encoding
    if accept_encoding is not None:
        c.setopt(CurlOpt.ACCEPT_ENCODING, accept_encoding.encode())

    # cert
    if cert:
        if isinstance(cert, str):
            c.setopt(CurlOpt.SSLCERT, cert)
        else:
            cert, key = cert
            c.setopt(CurlOpt.SSLCERT, cert)
            c.setopt(CurlOpt.SSLKEY, key)

    # impersonate
    if impersonate:
        impersonate = normalize_browser_type(impersonate)
        ret = c.impersonate(impersonate, default_headers=default_headers)  # type: ignore
        if ret != 0:
            raise ImpersonateError(f"Impersonating {impersonate} is not supported")

    # extra_fp options
    if extra_fp:
        if isinstance(extra_fp, dict):
            extra_fp = ExtraFingerprints(**extra_fp)
        if impersonate:
            warnings.warn(
                "Extra fingerprints was altered after impersonated version was set.",
                CurlCffiWarning,
                stacklevel=1,
            )
        set_extra_fp(c, extra_fp)

    # ja3 string
    if ja3:
        if impersonate:
            warnings.warn(
                "JA3 fingerprint was altered after impersonated version was set.",
                CurlCffiWarning,
                stacklevel=1,
            )
        permute = False
        if isinstance(extra_fp, ExtraFingerprints) and extra_fp.tls_permute_extensions:
            permute = True
        if isinstance(extra_fp, dict) and extra_fp.get("tls_permute_extensions"):
            permute = True
        set_ja3_options(c, ja3, permute=permute)

    # akamai string
    if akamai:
        if impersonate:
            warnings.warn(
                "Akamai fingerprint was altered after impersonated version was set.",
                CurlCffiWarning,
                stacklevel=1,
            )
        set_akamai_options(c, akamai)

    # http_version, after impersonate, which will change this to http2
    if http_version:
        http_version = normalize_http_version(http_version)
        c.setopt(CurlOpt.HTTP_VERSION, http_version)

    buffer = None
    q = None
    header_recved = None
    quit_now = None
    if stream:
        q = queue_class()
        header_recved = event_class()
        quit_now = event_class()

        def qput(chunk):
            if not header_recved.is_set():
                header_recved.set()
            if quit_now.is_set():
                return CURL_WRITEFUNC_ERROR
            q.put_nowait(chunk)
            return len(chunk)

        c.setopt(CurlOpt.WRITEFUNCTION, qput)
    elif content_callback is not None:
        c.setopt(CurlOpt.WRITEFUNCTION, content_callback)
    else:
        buffer = BytesIO()
        c.setopt(CurlOpt.WRITEDATA, buffer)
    header_buffer = BytesIO()
    c.setopt(CurlOpt.HEADERDATA, header_buffer)

    # interface
    if interface:
        c.setopt(CurlOpt.INTERFACE, interface.encode())

    # max_recv_speed
    # do not check, since 0 is a valid value to disable it
    c.setopt(CurlOpt.MAX_RECV_SPEED_LARGE, max_recv_speed)

    # set extra options, after all others, because it will alter some options
    if curl_options:
        for option, setting in curl_options.items():
            c.setopt(option, setting)

    return req, buffer, header_buffer, q, header_recved, quit_now
