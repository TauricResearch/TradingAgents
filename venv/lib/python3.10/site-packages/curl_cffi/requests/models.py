from contextlib import suppress
import queue
import re
import warnings
from concurrent.futures import Future
from typing import Any, Callable, Optional, Union
from collections.abc import Awaitable

from ..curl import Curl
from ..utils import CurlCffiWarning
from .cookies import Cookies
from .exceptions import HTTPError, RequestException
from .headers import Headers

# Use orjson if present
try:
    from orjson import loads
except ImportError:
    from json import loads

with suppress(ImportError):
    from markdownify import markdownify as md
    import readability as rd

CHARSET_RE = re.compile(r"charset=([\w-]+)")
STREAM_END = object()


def clear_queue(q: queue.Queue):
    with q.mutex:
        q.queue.clear()
        q.all_tasks_done.notify_all()
        q.unfinished_tasks = 0


class Request:
    """Representing a sent request."""

    def __init__(self, url: str, headers: Headers, method: str):
        self.url = url
        self.headers = headers
        self.method = method


class Response:
    """Contains information the server sends.

    Attributes:
        url: url used in the request.
        content: response body in bytes.
        text: response body in str.
        status_code: http status code.
        reason: http response reason, such as OK, Not Found.
        ok: is status_code in [200, 400)?
        headers: response headers.
        cookies: response cookies.
        elapsed: how many seconds the request cost.
        encoding: http body encoding.
        charset: alias for encoding.
        primary_ip: primary ip of the server.
        primary_port: primary port of the server.
        local_ip: local ip used in this connection.
        local_port: local port used in this connection.
        charset_encoding: encoding specified by the Content-Type header.
        default_encoding: encoding for decoding response content if charset is not found
            in headers. Defaults to "utf-8". Can be set to a callable for automatic
            detection.
        redirect_count: how many redirects happened.
        redirect_url: the final redirected url.
        http_version: http version used.
        history: history redirections, only headers are available.
    """

    def __init__(self, curl: Optional[Curl] = None, request: Optional[Request] = None):
        self.curl = curl
        self.request = request
        self.url = ""
        self.content = b""
        self.status_code = 200
        self.reason = "OK"
        self.ok = True
        self.headers = Headers()
        self.cookies = Cookies()
        self.elapsed = 0.0
        self.default_encoding: Union[str, Callable[[bytes], str]] = "utf-8"
        self.redirect_count = 0
        self.redirect_url = ""
        self.http_version = 0
        self.primary_ip: str = ""
        self.primary_port: int = 0
        self.local_ip: str = ""
        self.local_port: int = 0
        self.history: list[dict[str, Any]] = []
        self.infos: dict[str, Any] = {}
        self.queue: Optional[queue.Queue] = None
        self.stream_task: Optional[Future] = None
        self.astream_task: Optional[Awaitable] = None
        self.quit_now = None

    @property
    def charset(self) -> str:
        """Alias for encoding."""
        return self.encoding

    @property
    def encoding(self) -> str:
        """
        Determines the encoding to decode byte content into text.

        The method follows a specific priority to decide the encoding:
        1. If ``.encoding`` has been explicitly set, it is used.
        2. The encoding specified by the ``charset`` parameter in the ``Content-Type``
            header.
        3. The encoding specified by the ``default_encoding`` attribute. This can either
            be a string (e.g., "utf-8") or a callable for charset autodetection.
        """
        if not hasattr(self, "_encoding"):
            encoding = self.charset_encoding
            if encoding is None:
                if isinstance(self.default_encoding, str):
                    encoding = self.default_encoding
                elif callable(self.default_encoding):
                    encoding = self.default_encoding(self.content)
            self._encoding = encoding or "utf-8"
        return self._encoding

    @encoding.setter
    def encoding(self, value: str) -> None:
        if hasattr(self, "_text"):
            raise ValueError("Cannot set encoding after text has been accessed")
        self._encoding = value

    @property
    def charset_encoding(self) -> Optional[str]:
        """Return the encoding, as specified by the Content-Type header."""
        content_type = self.headers.get("Content-Type")
        if content_type:
            charset_match = CHARSET_RE.search(content_type)
            return charset_match.group(1) if charset_match else None
        return None

    @property
    def text(self) -> str:
        if not hasattr(self, "_text"):
            if not self.content:
                self._text = ""
            else:
                self._text = self._decode(self.content)
        return self._text

    def markdown(self) -> str:
        doc = rd.Document(self.content)
        title = doc.title()
        summary = doc.summary(html_partial=True)
        body_as_md = md(f"<h1>{title}</h1><main>{summary}</main>")
        return body_as_md

    def _decode(self, content: bytes) -> str:
        try:
            return content.decode(self.encoding, errors="replace")
        except (UnicodeDecodeError, LookupError):
            return content.decode("utf-8-sig")

    def raise_for_status(self):
        """Raise an error if status code is not in [200, 400)"""
        if not self.ok:
            raise HTTPError(f"HTTP Error {self.status_code}: {self.reason}", 0, self)

    def iter_lines(self, chunk_size=None, decode_unicode=False, delimiter=None):
        """
        iterate streaming content line by line, separated by ``\\n``.

        Copied from: https://requests.readthedocs.io/en/latest/_modules/requests/models/
        which is under the License: Apache 2.0
        """
        pending = None

        for chunk in self.iter_content(
            chunk_size=chunk_size, decode_unicode=decode_unicode
        ):
            if pending is not None:
                chunk = pending + chunk
            lines = chunk.split(delimiter) if delimiter else chunk.splitlines()
            pending = (
                lines.pop()
                if lines and lines[-1] and chunk and lines[-1][-1] == chunk[-1]
                else None
            )

            yield from lines

        if pending is not None:
            yield pending

    def iter_content(self, chunk_size=None, decode_unicode=False):
        """
        iterate streaming content chunk by chunk in bytes.
        """
        if chunk_size:
            warnings.warn(
                "chunk_size is ignored, there is no way to tell curl that.",
                CurlCffiWarning,
                stacklevel=2,
            )
        if decode_unicode:
            raise NotImplementedError()

        assert self.queue and self.curl, "stream mode is not enabled."

        while True:
            chunk = self.queue.get()

            # re-raise the exception if something wrong happened.
            if isinstance(chunk, RequestException):
                self.curl.reset()
                raise chunk

            # end of stream.
            if chunk is STREAM_END:
                break

            yield chunk

    def json(self, **kw):
        """return a parsed json object of the content."""
        return loads(self.content, **kw)

    def close(self):
        """Close the streaming connection, only valid in stream mode."""

        if self.quit_now:
            self.quit_now.set()
        if self.stream_task:
            self.stream_task.result()

    async def aiter_lines(self, chunk_size=None, decode_unicode=False, delimiter=None):
        """
        iterate streaming content line by line, separated by ``\\n``.

        Copied from: https://requests.readthedocs.io/en/latest/_modules/requests/models/
        which is under the License: Apache 2.0
        """
        pending = None

        async for chunk in self.aiter_content(
            chunk_size=chunk_size, decode_unicode=decode_unicode
        ):
            if pending is not None:
                chunk = pending + chunk
            lines = chunk.split(delimiter) if delimiter else chunk.splitlines()
            pending = (
                lines.pop()
                if lines and lines[-1] and chunk and lines[-1][-1] == chunk[-1]
                else None
            )

            for line in lines:
                yield line

        if pending is not None:
            yield pending

    async def aiter_content(self, chunk_size=None, decode_unicode=False):
        """
        iterate streaming content chunk by chunk in bytes.
        """
        if chunk_size:
            warnings.warn(
                "chunk_size is ignored, there is no way to tell curl that.",
                CurlCffiWarning,
                stacklevel=2,
            )
        if decode_unicode:
            raise NotImplementedError()

        assert self.queue and self.curl, "stream mode is not enabled."

        while True:
            chunk = await self.queue.get()

            # re-raise the exception if something wrong happened.
            if isinstance(chunk, RequestException):
                await self.aclose()
                raise chunk

            # end of stream.
            if chunk is STREAM_END:
                await self.aclose()
                return

            yield chunk

    async def atext(self) -> str:
        """
        Return a decoded string.
        """
        return self._decode(await self.acontent())

    async def acontent(self) -> bytes:
        """wait and read the streaming content in one bytes object."""
        chunks = []
        async for chunk in self.aiter_content():
            chunks.append(chunk)
        return b"".join(chunks)

    async def aclose(self):
        """Close the streaming connection, only valid in stream mode."""

        if self.astream_task:
            await self.astream_task

    # It prints the status code of the response instead of the object's memory location.
    def __repr__(self) -> str:
        return f"<Response [{self.status_code}]>"
