from __future__ import annotations

import re
import struct
import sys
import warnings
from http.cookies import SimpleCookie
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional, Union, cast

import certifi

from ._wrapper import ffi, lib
from .const import CurlECode, CurlHttpVersion, CurlInfo, CurlOpt, CurlWsFlag
from .utils import CurlCffiWarning

DEFAULT_CACERT = certifi.where()
REASON_PHRASE_RE = re.compile(rb"HTTP/\d\.\d [0-9]{3} (.*)")
STATUS_LINE_RE = re.compile(rb"HTTP/(\d\.\d) ([0-9]{3}) (.*)")

if TYPE_CHECKING:

    class CurlWsFrame:
        age: int
        flags: int
        offset: int
        bytesleft: int
        len: int


class CurlError(Exception):
    """Base exception for curl_cffi package"""

    def __init__(self, msg, code: Union[CurlECode, Literal[0]] = 0, *args, **kwargs):
        super().__init__(msg, *args, **kwargs)
        self.code: Union[CurlECode, Literal[0]] = code


CURLINFO_TEXT = 0
CURLINFO_HEADER_IN = 1
CURLINFO_HEADER_OUT = 2
CURLINFO_DATA_IN = 3
CURLINFO_DATA_OUT = 4
CURLINFO_SSL_DATA_IN = 5
CURLINFO_SSL_DATA_OUT = 6

CURL_WRITEFUNC_PAUSE = 0x10000001
CURL_WRITEFUNC_ERROR = 0xFFFFFFFF


@ffi.def_extern()
def debug_function(curl, type_: int, data, size: int, clientp) -> int:
    """ffi callback for curl debug info"""
    callback = ffi.from_handle(clientp)
    text = ffi.buffer(data, size)[:]
    callback(type_, text)
    return 0


def bytes_to_hex(b: bytes, uppercase: bool = False) -> str:
    """
    Convert a bytes object to a space-separated hex string, e.g. "0a ff 3c".
    If uppercase=True, letters will be A–F instead of a–f.
    """
    fmt = "{:02X}" if uppercase else "{:02x}"
    return " ".join(fmt.format(byte) for byte in b)


def debug_function_default(type_: int, data: bytes) -> None:
    PREFIXES = {
        CURLINFO_TEXT: "*",
        CURLINFO_HEADER_IN: "<",
        CURLINFO_HEADER_OUT: ">",
        CURLINFO_DATA_IN: "< DATA",
        CURLINFO_DATA_OUT: "> DATA",
        CURLINFO_SSL_DATA_IN: "< SSL",
        CURLINFO_SSL_DATA_OUT: "> SSL",
    }
    MAX_SHOW_BYTES = 40
    prefix = PREFIXES.get(type_, "*")

    # always show ssl data in binary format
    if type_ in (CURLINFO_SSL_DATA_IN, CURLINFO_SSL_DATA_OUT):
        hex_str = bytes_to_hex(data[:MAX_SHOW_BYTES])
        postfix = "" if len(data) <= MAX_SHOW_BYTES else "..."
        sys.stderr.write(f"{prefix} [{len(data)} bytes]: {hex_str}{postfix}\n")
    else:
        try:
            text = data.decode("utf-8")
            sys.stderr.write(f"{prefix} {text}")
            if type_ not in (CURLINFO_TEXT, CURLINFO_HEADER_IN, CURLINFO_HEADER_OUT):
                sys.stderr.write("\n")
        except UnicodeDecodeError:
            # Fallback to hex representation of first MAX_SHOW_BYTES bytes
            hex_str = bytes_to_hex(data[:MAX_SHOW_BYTES])
            postfix = "" if len(data) <= MAX_SHOW_BYTES else "..."
            sys.stderr.write(f"{prefix} [{len(data)} bytes]: {hex_str}{postfix}\n")


@ffi.def_extern()
def buffer_callback(ptr, size, nmemb, userdata):
    """ffi callback for curl write function, directly writes to a buffer"""
    # assert size == 1
    buffer = ffi.from_handle(userdata)
    buffer.write(ffi.buffer(ptr, nmemb)[:])
    return nmemb * size


def ensure_int(s):
    if not s:
        return 0
    return int(s)


@ffi.def_extern()
def write_callback(ptr, size, nmemb, userdata):
    """ffi callback for curl write function, calls the callback python function"""
    # although similar enough to the function above, kept here for performance reasons
    callback = ffi.from_handle(userdata)
    wrote = callback(ffi.buffer(ptr, nmemb)[:])
    wrote = ensure_int(wrote)
    if wrote == CURL_WRITEFUNC_PAUSE or wrote == CURL_WRITEFUNC_ERROR:  # noqa: SIM109
        return wrote
    # should make this an exception in future versions
    if wrote != nmemb * size:
        warnings.warn("Wrote bytes != received bytes.", CurlCffiWarning, stacklevel=2)
    return nmemb * size


# Credits: @alexio777 on https://github.com/lexiforest/curl_cffi/issues/4
def slist_to_list(head) -> list[bytes]:
    """Converts curl slist to a python list."""
    result = []
    ptr = head
    while ptr:
        result.append(ffi.string(ptr.data))
        ptr = ptr.next
    lib.curl_slist_free_all(head)
    return result


class Curl:
    """
    Wrapper for ``curl_easy_*`` functions of libcurl.
    """

    def __init__(self, cacert: str = "", debug: bool = False, handle=None) -> None:
        """
        Parameters:
            cacert: CA cert path to use, by default, certs from ``certifi`` are used.
            debug: whether to show curl debug messages.
            handle: a curl handle instance from ``curl_easy_init``.
        """
        self._curl = handle if handle else lib.curl_easy_init()
        self._headers = ffi.NULL
        self._proxy_headers = ffi.NULL
        self._resolve = ffi.NULL
        self._cacert = cacert or DEFAULT_CACERT
        self._is_cert_set = False
        self._write_handle: Any = None
        self._header_handle: Any = None
        self._debug_handle: Any = None
        self._body_handle: Any = None
        # TODO: use CURL_ERROR_SIZE
        self._error_buffer = ffi.new("char[]", 256)
        self._debug = debug
        self._set_error_buffer()

    def _set_error_buffer(self) -> None:
        ret = lib._curl_easy_setopt(self._curl, CurlOpt.ERRORBUFFER, self._error_buffer)
        if ret != 0:
            warnings.warn("Failed to set error buffer", CurlCffiWarning, stacklevel=2)
        if self._debug:
            self.debug()

    def debug(self) -> None:
        """Set debug to True"""
        self.setopt(CurlOpt.VERBOSE, 1)
        self.setopt(CurlOpt.DEBUGFUNCTION, True)

    def __del__(self) -> None:
        self.close()

    def _check_error(self, errcode: int, *args: Any) -> None:
        error = self._get_error(errcode, *args)
        if error is not None:
            raise error

    def _get_error(self, errcode: int, *args: Any):
        if errcode != 0:
            errmsg = ffi.string(self._error_buffer).decode(errors="backslashreplace")
            action = " ".join([str(a) for a in args])
            return CurlError(
                f"Failed to {action}, curl: ({errcode}) {errmsg}. "
                "See https://curl.se/libcurl/c/libcurl-errors.html first for more "
                "details.",
                code=cast(CurlECode, errcode),
            )

    def setopt(self, option: CurlOpt, value: Any) -> int:
        """Wrapper for ``curl_easy_setopt``.

        Args:
            option: option to set, using constants from CurlOpt enum
            value: value to set, strings will be handled automatically

        Returns:
            0 if no error, see ``CurlECode``.
        """
        input_option = {
            # this should be int in curl, but cffi requires pointer for void*
            # it will be convert back in the glue c code.
            0: "long*",
            10000: "char*",
            20000: "void*",
            30000: "int64_t*",  # offset type
            40000: "void*",  # blob type
        }
        # print("option", option, "value", value)

        # Convert value
        value_type = input_option.get((option // 10000) * 10000)
        if value_type == "long*" or value_type == "int64_t*":
            c_value = ffi.new(value_type, value)
        elif option == CurlOpt.WRITEDATA:
            c_value = ffi.new_handle(value)
            self._write_handle = c_value
            lib._curl_easy_setopt(
                self._curl, CurlOpt.WRITEFUNCTION, lib.buffer_callback
            )
        elif option == CurlOpt.HEADERDATA:
            c_value = ffi.new_handle(value)
            self._header_handle = c_value
            lib._curl_easy_setopt(
                self._curl, CurlOpt.HEADERFUNCTION, lib.buffer_callback
            )
        elif option == CurlOpt.WRITEFUNCTION:
            c_value = ffi.new_handle(value)
            self._write_handle = c_value
            lib._curl_easy_setopt(self._curl, CurlOpt.WRITEFUNCTION, lib.write_callback)
            option = CurlOpt.WRITEDATA
        elif option == CurlOpt.HEADERFUNCTION:
            c_value = ffi.new_handle(value)
            self._header_handle = c_value
            lib._curl_easy_setopt(
                self._curl, CurlOpt.HEADERFUNCTION, lib.write_callback
            )
            option = CurlOpt.HEADERDATA
        elif option == CurlOpt.DEBUGFUNCTION:
            if value is True:
                value = debug_function_default
            c_value = ffi.new_handle(value)
            self._debug_handle = c_value
            lib._curl_easy_setopt(self._curl, CurlOpt.DEBUGFUNCTION, lib.debug_function)
            option = CurlOpt.DEBUGDATA
        elif value_type == "char*":
            c_value = value.encode() if isinstance(value, str) else value
            # Must keep a reference, otherwise may be GCed.
            if option == CurlOpt.POSTFIELDS:
                self._body_handle = c_value
        else:
            raise NotImplementedError(f"Option unsupported: {option}")

        if option == CurlOpt.HTTPHEADER:
            for header in value:
                self._headers = lib.curl_slist_append(self._headers, header)
            ret = lib._curl_easy_setopt(self._curl, option, self._headers)
        elif option == CurlOpt.PROXYHEADER:
            for proxy_header in value:
                self._proxy_headers = lib.curl_slist_append(
                    self._proxy_headers, proxy_header
                )
            ret = lib._curl_easy_setopt(self._curl, option, self._proxy_headers)
        elif option == CurlOpt.RESOLVE:
            for resolve in value:
                if isinstance(resolve, str):
                    resolve = resolve.encode()
                self._resolve = lib.curl_slist_append(self._resolve, resolve)
            ret = lib._curl_easy_setopt(self._curl, option, self._resolve)
        else:
            ret = lib._curl_easy_setopt(self._curl, option, c_value)
        self._check_error(ret, "setopt", option, value)

        if option == CurlOpt.CAINFO:
            self._is_cert_set = True

        return ret

    def getinfo(self, option: CurlInfo) -> Union[bytes, int, float, list]:
        """Wrapper for ``curl_easy_getinfo``. Gets information in response after
        curl.perform.

        Parameters:
            option: option to get info of, using constants from ``CurlInfo`` enum

        Returns:
            value retrieved from last perform.
        """
        ret_option = {
            0x100000: "char**",
            0x200000: "long*",
            0x300000: "double*",
            0x400000: "struct curl_slist **",
            0x500000: "long*",
            0x600000: "int64_t*",
        }
        ret_cast_option = {
            0x100000: ffi.string,
            0x200000: int,
            0x300000: float,
            0x500000: int,
            0x600000: int,
        }
        c_value = ffi.new(ret_option[option & 0xF00000])
        ret = lib.curl_easy_getinfo(self._curl, option, c_value)
        self._check_error(ret, "getinfo", option)
        # cookielist and ssl_engines starts with 0x400000, see also: const.py
        if option & 0xF00000 == 0x400000:
            return slist_to_list(c_value[0])
        if c_value[0] == ffi.NULL:
            return b""
        return ret_cast_option[option & 0xF00000](c_value[0])

    def version(self) -> bytes:
        """Get the underlying libcurl version."""
        return ffi.string(lib.curl_version())

    def impersonate(self, target: str, default_headers: bool = True) -> int:
        """Set the browser type to impersonate.

        Parameters:
            target: browser to impersonate.
            default_headers: whether to add default headers, like User-Agent.

        Returns:
            0 if no error.
        """
        return lib.curl_easy_impersonate(
            self._curl, target.encode(), int(default_headers)
        )

    def _ensure_cacert(self) -> None:
        if not self._is_cert_set:
            ret = self.setopt(CurlOpt.CAINFO, self._cacert)
            self._check_error(ret, "set cacert")
            ret = self.setopt(CurlOpt.PROXY_CAINFO, self._cacert)
            self._check_error(ret, "set proxy cacert")

    def perform(self, clear_headers: bool = True) -> None:
        """Wrapper for ``curl_easy_perform``, performs a curl request.

        Parameters:
            clear_headers: clear header slist used in this perform

        Raises:
            CurlError: if the perform was not successful.
        """
        # make sure we set a cacert store
        self._ensure_cacert()

        # here we go
        ret = lib.curl_easy_perform(self._curl)

        try:
            self._check_error(ret, "perform")
        finally:
            # cleaning
            self.clean_after_perform(clear_headers)

    def upkeep(self) -> int:
        return lib.curl_easy_upkeep(self._curl)

    def clean_after_perform(self, clear_headers: bool = True) -> None:
        """Clean up handles and buffers after ``perform``, called at the end of
        ``perform``."""
        self._write_handle = None
        self._header_handle = None
        self._debug_handle = None
        self._body_handle = None
        if clear_headers:
            if self._headers != ffi.NULL:
                lib.curl_slist_free_all(self._headers)
            self._headers = ffi.NULL

            if self._proxy_headers != ffi.NULL:
                lib.curl_slist_free_all(self._proxy_headers)
            self._proxy_headers = ffi.NULL

    def duphandle(self) -> Curl:
        """Wrapper for ``curl_easy_duphandle``.

        This is not a full copy of entire curl object in python. For example, headers
        handle is not copied, you have to set them again."""
        new_handle = lib.curl_easy_duphandle(self._curl)
        c = Curl(cacert=self._cacert, debug=self._debug, handle=new_handle)
        return c

    def reset(self) -> None:
        """Reset all curl options, wrapper for ``curl_easy_reset``."""
        self._is_cert_set = False
        if self._curl is not None:
            lib.curl_easy_reset(self._curl)
            self._set_error_buffer()
        self._resolve = ffi.NULL

    def parse_cookie_headers(self, headers: list[bytes]) -> SimpleCookie:
        """Extract ``cookies.SimpleCookie`` from header lines.

        Parameters:
            headers: list of headers in bytes.

        Returns:
            A parsed cookies.SimpleCookie instance.
        """
        cookie: SimpleCookie = SimpleCookie()
        for header in headers:
            if header.lower().startswith(b"set-cookie: "):
                cookie.load(header[12:].decode())  # len("set-cookie: ") == 12
        return cookie

    @staticmethod
    def get_reason_phrase(status_line: bytes) -> bytes:
        """Extract reason phrase, like ``OK``, ``Not Found`` from response status
        line."""
        m = REASON_PHRASE_RE.match(status_line)
        return m.group(1) if m else b""

    @staticmethod
    def parse_status_line(status_line: bytes) -> tuple[CurlHttpVersion, int, bytes]:
        """Parse status line.

        Returns:
            http_version, status_code, and reason phrase
        """
        m = STATUS_LINE_RE.match(status_line)
        if not m:
            return CurlHttpVersion.V1_0, 0, b""
        if m.group(1) == "2.0":
            http_version = CurlHttpVersion.V2_0
        elif m.group(1) == "1.1":
            http_version = CurlHttpVersion.V1_1
        elif m.group(1) == "1.0":
            http_version = CurlHttpVersion.V1_0
        else:
            http_version = CurlHttpVersion.NONE
        status_code = int(m.group(2))
        reason = m.group(3)

        return http_version, status_code, reason

    def close(self) -> None:
        """Close and cleanup curl handle, wrapper for ``curl_easy_cleanup``."""
        if self._curl:
            lib.curl_easy_cleanup(self._curl)
            self._curl = None
        ffi.release(self._error_buffer)
        self._resolve = ffi.NULL

    def ws_recv(self, n: int = 1024) -> tuple[bytes, CurlWsFrame]:
        """Receive a frame from a websocket connection.

        Args:
            n: maximum data to receive.

        Returns:
            a tuple of frame content and curl frame meta struct.

        Raises:
            CurlError: if failed.
        """
        buffer = ffi.new("char[]", n)
        n_recv = ffi.new("size_t *")
        p_frame = ffi.new("struct curl_ws_frame **")

        ret = lib.curl_ws_recv(self._curl, buffer, n, n_recv, p_frame)
        self._check_error(ret, "WS_RECV")

        # Frame meta explained: https://curl.se/libcurl/c/curl_ws_meta.html
        frame = p_frame[0]

        return ffi.buffer(buffer)[: n_recv[0]], frame

    def ws_send(self, payload: bytes, flags: CurlWsFlag = CurlWsFlag.BINARY) -> int:
        """Send data to a websocket connection.

        Args:
            payload: content to send.
            flags: websocket flag to set for the frame, default: binary.

        Returns:
            0 if no error.

        Raises:
            CurlError: if failed.
        """
        n_sent = ffi.new("size_t *")
        buffer = ffi.from_buffer(payload)
        ret = lib.curl_ws_send(self._curl, buffer, len(payload), n_sent, 0, flags)
        self._check_error(ret, "WS_SEND")
        return n_sent[0]

    def ws_close(self, code: int = 1000, message: bytes = b"") -> int:
        """Close a websocket connection. Shorthand for :meth:`ws_send`
        with close code and message. Note that to completely close the connection,
        you must close the curl handle after this call with :meth:`close`.

        Args:
            code: close code.
            message: close message.

        Returns:
            0 if no error.

        Raises:
            CurlError: if failed.
        """
        return self.ws_send(struct.pack("!H", code) + message)


class CurlMime:
    """Wrapper for the ``curl_mime_`` API."""

    def __init__(self, curl: Optional[Curl] = None):
        """
        Args:
            curl: Curl instance to use.
        """
        self._curl = curl if curl else Curl()
        self._form = lib.curl_mime_init(self._curl._curl)

    def addpart(
        self,
        name: str,
        *,
        content_type: Optional[str] = None,
        filename: Optional[str] = None,
        local_path: Optional[Union[str, bytes, Path]] = None,
        data: Optional[bytes] = None,
    ) -> None:
        """Add a mime part for a mutlipart html form.

        Note: You can only use either local_path or data, not both.

        Args:
            name: name of the field.
            content_type: content_type for the field. for example: ``image/png``.
            filename: filename for the server.
            local_path: file to upload on local disk.
            data: file content to upload.
        """
        part = lib.curl_mime_addpart(self._form)

        ret = lib.curl_mime_name(part, name.encode())
        if ret != 0:
            raise CurlError("Add field failed.")

        # mime type
        if content_type is not None:
            ret = lib.curl_mime_type(part, content_type.encode())
            if ret != 0:
                raise CurlError("Add field failed.")

        # remote file name
        if filename is not None:
            ret = lib.curl_mime_filename(part, filename.encode())
            if ret != 0:
                raise CurlError("Add field failed.")

        if local_path and data:
            raise CurlError("Can not use local_path and data at the same time.")

        # this is a filename
        if local_path is not None:
            if isinstance(local_path, Path):
                local_path_str = str(local_path)
            elif isinstance(local_path, bytes):
                local_path_str = local_path.decode()
            else:
                local_path_str = local_path

            if not Path(local_path_str).exists():
                raise FileNotFoundError(f"File not found at {local_path_str}")
            ret = lib.curl_mime_filedata(part, local_path_str.encode())
            if ret != 0:
                raise CurlError("Add field failed.")

        if data is not None:
            if not isinstance(data, bytes):
                data = str(data).encode()
            ret = lib.curl_mime_data(part, data, len(data))

    @classmethod
    def from_list(cls, files: list[dict]):
        """Create a multipart instance from a list of dict, for keys, see ``addpart``"""
        form = cls()
        for file in files:
            form.addpart(**file)
        return form

    def attach(self, curl: Optional[Curl] = None) -> None:
        """Attach the mime instance to a curl instance."""
        c = curl if curl else self._curl
        c.setopt(CurlOpt.MIMEPOST, self._form)

    def close(self) -> None:
        """Close the mime instance and underlying files. This method must be called
        after ``perform`` or ``request``."""
        lib.curl_mime_free(self._form)
        self._form = ffi.NULL

    def __del__(self) -> None:
        self.close()
