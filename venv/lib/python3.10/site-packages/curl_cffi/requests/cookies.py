# Adapted from: https://github.com/encode/httpx/blob/master/httpx/_models.py,
# which is licensed under the BSD License.
# See https://github.com/encode/httpx/blob/master/LICENSE.md

__all__ = ["Cookies"]

import re
import time
import warnings
from dataclasses import dataclass
from http.cookiejar import Cookie, CookieJar
from http.cookies import _unquote
from typing import Optional, Union
from collections.abc import Iterator, MutableMapping
from urllib.parse import urlparse

from ..utils import CurlCffiWarning
from .errors import CookieConflict, RequestsError

CookieTypes = Union["Cookies", CookieJar, dict[str, str], list[tuple[str, str]]]


@dataclass
class CurlMorsel:
    name: str
    value: str
    hostname: str = ""
    subdomains: bool = False
    path: str = "/"
    secure: bool = False
    expires: int = 0
    http_only: bool = False

    @staticmethod
    def parse_bool(s):
        return s == "TRUE"

    @staticmethod
    def dump_bool(s):
        return "TRUE" if s else "FALSE"

    @classmethod
    def from_curl_format(cls, set_cookie_line: bytes):
        (
            hostname,
            subdomains,
            path,
            secure,
            expires,
            name,
            value,
        ) = set_cookie_line.decode().split("\t")
        if hostname and hostname[0] == "#":
            http_only = True
            # e.g. #HttpOnly_postman-echo.com
            domain = hostname[10:]  # len("#HttpOnly_") == 10
        else:
            http_only = False
            domain = hostname
        return cls(
            hostname=domain,
            subdomains=cls.parse_bool(subdomains),
            path=path,
            secure=cls.parse_bool(secure),
            expires=int(expires),
            name=name,
            value=_unquote(value),
            http_only=http_only,
        )

    def to_curl_format(self):
        if not self.hostname:
            raise RequestsError(f"Domain not found for cookie {self.name}={self.value}")
        return "\t".join(
            [
                self.hostname,
                self.dump_bool(self.subdomains),
                self.path,
                self.dump_bool(self.secure),
                str(self.expires),
                self.name,
                self.value,
            ]
        )

    @classmethod
    def from_cookiejar_cookie(cls, cookie: Cookie):
        return cls(
            name=cookie.name,
            value=cookie.value or "",
            hostname=cookie.domain,
            subdomains=cookie.domain_specified,
            path=cookie.path,
            secure=cookie.secure,
            expires=int(cookie.expires or 0),
            http_only=False,
        )

    def to_cookiejar_cookie(self) -> Cookie:
        # the leading dot actually does not mean anything nowadays
        # https://stackoverflow.com/a/20884869/1061155
        # https://github.com/python/cpython/blob/d6555abfa7384b5a40435a11bdd2aa6bbf8f5cfc/Lib/http/cookiejar.py#L1535
        return Cookie(
            version=0,
            name=self.name,
            value=self.value,
            port=None,
            port_specified=False,
            domain=self.hostname,
            domain_specified=self.subdomains,
            domain_initial_dot=bool(self.hostname.startswith(".")),
            path=self.path,
            path_specified=bool(self.path),
            secure=self.secure,
            # using if explicitly to make it clear.
            expires=None if self.expires == 0 else self.expires,
            discard=self.expires == 0,
            comment=None,
            comment_url=None,
            rest=dict(http_only=f"{self.http_only}"),
            rfc2109=False,
        )


cut_port_re = re.compile(r":\d+$", re.ASCII)
IPV4_RE = re.compile(r"\.\d+$", re.ASCII)


class Cookies(MutableMapping[str, str]):
    """
    HTTP Cookies, as a mutable mapping.
    """

    def __init__(self, cookies: Optional[CookieTypes] = None) -> None:
        if cookies is None or isinstance(cookies, dict):
            self.jar = CookieJar()
            if isinstance(cookies, dict):
                for key, value in cookies.items():
                    self.set(key, value)
        elif isinstance(cookies, list):
            self.jar = CookieJar()
            for key, value in cookies:
                self.set(key, value)
        elif isinstance(cookies, Cookies):
            self.jar = CookieJar()
            for cookie in cookies.jar:
                self.jar.set_cookie(cookie)
        else:
            self.jar = cookies

    def _eff_request_host(self, request) -> str:
        """
        Almost equivalent to the eff_request_host function in:
            https://github.com/python/cpython/blob/3.11/Lib/http/cookiejar.py#L636
        """
        host = urlparse(request.url)[1]
        if host == "":
            host = request.headers.get("Host", "")

        # remove port, if present
        host = cut_port_re.sub("", host, 1)
        host = host.lower()
        if host.find(".") == -1 and not IPV4_RE.search(host):
            host += ".local"
        return host

    def get_cookies_for_curl(self, request) -> list[CurlMorsel]:
        """the process is similar to ``cookiejar.add_cookie_header``, but load all
        cookies"""
        self.jar._cookies_lock.acquire()  # type: ignore
        morsels = []
        try:
            self.jar._policy._now = self._now = int(time.time())  # type: ignore
            for cookie in self.jar:
                morsel = CurlMorsel.from_cookiejar_cookie(cookie)
                if not morsel.hostname:
                    morsel.hostname = self._eff_request_host(request)
                morsels.append(morsel)
        finally:
            self.jar._cookies_lock.release()  # type: ignore

        self.jar.clear_expired_cookies()
        return morsels

    def update_cookies_from_curl(self, morsels: list[CurlMorsel]):
        for morsel in morsels:
            cookie = morsel.to_cookiejar_cookie()
            self.jar.set_cookie(cookie)
        self.jar.clear_expired_cookies()

    def set(
        self, name: str, value: str, domain: str = "", path: str = "/", secure=False
    ) -> None:
        """
        Set a cookie value by name. May optionally include domain and path.
        """
        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie
        if name.startswith("__Secure-") and secure is False:
            warnings.warn(
                "`secure` changed to True for `__Secure-` prefixed cookies",
                CurlCffiWarning,
                stacklevel=2,
            )
            secure = True
        elif name.startswith("__Host-") and (secure is False or domain or path != "/"):
            warnings.warn(
                "`host` changed to True, `domain` removed, `path` changed to `/` "
                "for `__Host-` prefixed cookies",
                CurlCffiWarning,
                stacklevel=2,
            )
            secure = True
            domain = ""
            path = "/"
        kwargs = {
            "version": 0,
            "name": name,
            "value": value,
            "port": None,
            "port_specified": False,
            "domain": domain,
            "domain_specified": bool(domain),
            "domain_initial_dot": domain.startswith("."),
            "path": path,
            "path_specified": bool(path),
            "secure": secure,
            "expires": None,
            "discard": True,
            "comment": None,
            "comment_url": None,
            "rest": {"HttpOnly": None},
            "rfc2109": False,
        }
        cookie = Cookie(**kwargs)
        self.jar.set_cookie(cookie)

    def get(  # type: ignore
        self,
        name: str,
        default: Optional[str] = None,
        domain: Optional[str] = None,
        path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get a cookie by name. May optionally include domain and path
        in order to specify exactly which cookie to retrieve.
        """
        value = None
        matched_domain = ""
        for cookie in self.jar:
            if (
                cookie.name == name
                and (domain is None or cookie.domain == domain)
                and (path is None or cookie.path == path)
            ):
                # if cookies on two different domains do not share a same value
                if (
                    value is not None
                    and not matched_domain.endswith(cookie.domain)
                    and not str(cookie.domain).endswith(matched_domain)
                    and value != cookie.value
                ):
                    message = (
                        f"Multiple cookies exist with name={name} on "
                        f"{matched_domain} and {cookie.domain}, add domain "
                        "parameter to suppress this error."
                    )
                    raise CookieConflict(message)
                value = cookie.value
                matched_domain = cookie.domain or ""

        if value is None:
            return default
        return value

    def get_dict(
        self, domain: Optional[str] = None, path: Optional[str] = None
    ) -> dict:
        """
        Cookies with the same name on different domains may overwrite each other,
        do NOT use this function as a method of serialization.
        """
        ret = {}
        for cookie in self.jar:
            if (domain is None or cookie.domain == domain) and (
                path is None or cookie.path == path
            ):
                ret[cookie.name] = cookie.value
        return ret

    def delete(
        self,
        name: str,
        domain: Optional[str] = None,
        path: Optional[str] = None,
    ) -> None:
        """
        Delete a cookie by name. May optionally include domain and path
        in order to specify exactly which cookie to delete.
        """
        if domain is not None and path is not None:
            return self.jar.clear(domain, path, name)

        remove = [
            cookie
            for cookie in self.jar
            if cookie.name == name
            and (domain is None or cookie.domain == domain)
            and (path is None or cookie.path == path)
        ]

        for cookie in remove:
            self.jar.clear(cookie.domain, cookie.path, cookie.name)

    def clear(self, domain: Optional[str] = None, path: Optional[str] = None) -> None:
        """
        Delete all cookies. Optionally include a domain and path in
        order to only delete a subset of all the cookies.
        """
        args = []
        if domain is not None:
            args.append(domain)
        if path is not None:
            assert domain is not None
            args.append(path)
        self.jar.clear(*args)

    def update(self, cookies: Optional[CookieTypes] = None) -> None:  # type: ignore
        cookies = Cookies(cookies)
        for cookie in cookies.jar:
            self.jar.set_cookie(cookie)

    def __setitem__(self, name: str, value: str) -> None:
        return self.set(name, value)

    def __getitem__(self, name: str) -> str:
        value = self.get(name)
        if value is None:
            raise KeyError(name)
        return value

    def __delitem__(self, name: str) -> None:
        return self.delete(name)

    def __len__(self) -> int:
        return len(self.jar)

    def __iter__(self) -> Iterator[str]:
        return (cookie.name for cookie in self.jar)

    def __bool__(self) -> bool:
        for _ in self.jar:
            return True
        return False

    def __repr__(self) -> str:
        cookies_repr = ", ".join(
            [
                f"<Cookie {cookie.name}={cookie.value} for {cookie.domain} />"
                for cookie in self.jar
            ]
        )

        return f"<Cookies[{cookies_repr}]>"
