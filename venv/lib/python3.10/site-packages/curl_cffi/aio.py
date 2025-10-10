import asyncio
import sys
import warnings
from contextlib import suppress
from typing import Any, Optional
from weakref import WeakKeyDictionary

from ._wrapper import ffi, lib
from .const import CurlECode, CurlMOpt
from .curl import DEFAULT_CACERT, Curl, CurlError
from .utils import CurlCffiWarning

__all__ = ["AsyncCurl"]

if sys.platform == "win32":
    # registry of asyncio loop : selector thread
    _selectors: WeakKeyDictionary = WeakKeyDictionary()
    PROACTOR_WARNING = """
    Proactor event loop does not implement add_reader family of methods required.
    Registering an additional selector thread for add_reader support.
    To avoid this warning use:
        asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())
    """

    def get_selector(
        asyncio_loop: asyncio.AbstractEventLoop,
    ) -> asyncio.AbstractEventLoop:
        """Get selector-compatible loop

        Returns an object with ``add_reader`` family of methods,
        either the loop itself or a SelectorThread instance.

        Workaround Windows proactor removal of *reader methods.
        """

        if asyncio_loop in _selectors:
            return _selectors[asyncio_loop]

        if not isinstance(
            asyncio_loop, getattr(asyncio, "ProactorEventLoop", type(None))
        ):
            return asyncio_loop

        warnings.warn(PROACTOR_WARNING, CurlCffiWarning, stacklevel=2)

        from ._asyncio_selector import AddThreadSelectorEventLoop

        selector_loop = _selectors[asyncio_loop] = AddThreadSelectorEventLoop(
            asyncio_loop
        )  # type: ignore

        # patch loop.close to also close the selector thread
        loop_close = asyncio_loop.close

        def _close_selector_and_loop():
            # restore original before calling selector.close,
            # which in turn calls eventloop.close!
            asyncio_loop.close = loop_close
            _selectors.pop(asyncio_loop, None)
            selector_loop.close()

        asyncio_loop.close = _close_selector_and_loop
        return selector_loop

else:

    def get_selector(loop: asyncio.AbstractEventLoop) -> asyncio.AbstractEventLoop:
        return loop


CURL_POLL_NONE = 0
CURL_POLL_IN = 1
CURL_POLL_OUT = 2
CURL_POLL_INOUT = 3
CURL_POLL_REMOVE = 4

CURL_SOCKET_TIMEOUT = -1
CURL_SOCKET_BAD = -1

CURL_CSELECT_IN = 0x01
CURL_CSELECT_OUT = 0x02
CURL_CSELECT_ERR = 0x04

CURLMSG_DONE = 1

CURLPIPE_NOTHING = 0
CURLPIPE_HTTP1 = 1  # deprecated
CURLPIPE_MULTIPLEX = 2


"""
libcurl provides an event-based system for multiple handles with the following API:

- curl_multi_socket_action, for detecting events
- curl_multi_info_read, for reading the transfer status

There are 2 callbacks:

- socket_function, set by CURLMOPT_SOCKETFUNCTION, will be called for socket events.
- timer_function, set by CURLMOPT_TIMERFUNCTION, will be called when timeouts happen.

And it works like the following:

Set up handles, callbacks first.

When started, curl_multi_socket_action should be called to start everything.

If there are data in/out, libcurl calls the socket_function callback, and it sets up
`process_data` as asyncio loop reader/writer function. `process_data` will call
curl_multi_info_read to determine whether a certain `await perform` has finished.

When idle, libcurl will call the timer_function callback, which sets up a later call
for socket_action to detect events.
"""


@ffi.def_extern()
def timer_function(curlm, timeout_ms: int, clientp: Any) -> int:
    """
    see: https://curl.se/libcurl/c/CURLMOPT_TIMERFUNCTION.html
    """
    async_curl = ffi.from_handle(clientp)

    # Cancel the timer anyway, if it's -1, yes, libcurl says it should be cancelled.
    # If not, to add a new timer, we need to cancel the old timer.
    if async_curl._timer:
        async_curl._timer.cancel()  # If already called, cancel does nothing.
        async_curl._timer = None

    # libcurl says to install a timer which calls socket_action on fire.
    async_curl._timer = async_curl.loop.call_later(
        timeout_ms / 1000,
        async_curl.process_data,
        CURL_SOCKET_TIMEOUT,  # -1
        CURL_POLL_NONE,  # 0
    )

    return 0


@ffi.def_extern()
def socket_function(curl, sockfd: int, what: int, clientp: Any, data: Any) -> int:
    """This callback is called when libcurl decides it's time to interact with certain
    sockets"""

    async_curl = ffi.from_handle(clientp)
    loop = async_curl.loop

    # Always remove and re-add fds
    if sockfd in async_curl._sockfds:
        loop.remove_reader(sockfd)
        loop.remove_writer(sockfd)

    # Need to read from the socket
    if what & CURL_POLL_IN:
        loop.add_reader(sockfd, async_curl.process_data, sockfd, CURL_CSELECT_IN)
        async_curl._sockfds.add(sockfd)

    # Need to write to the socket
    if what & CURL_POLL_OUT:
        loop.add_writer(sockfd, async_curl.process_data, sockfd, CURL_CSELECT_OUT)
        async_curl._sockfds.add(sockfd)

    # Need to remove the socket
    if what == CURL_POLL_REMOVE:
        async_curl._sockfds.remove(sockfd)

    return 0


class AsyncCurl:
    """Wrapper around curl_multi handle to provide asyncio support. It uses the libcurl
    socket_action APIs."""

    def __init__(self, cacert: str = "", loop=None):
        """
        Parameters:
            cacert: CA cert path to use, by default, certs from ``certifi`` are used.
            loop: EventLoop to use.
        """
        self._curlm = lib.curl_multi_init()
        self._cacert = cacert or DEFAULT_CACERT
        self._curl2future: dict[Curl, asyncio.Future] = {}  # curl to future map
        self._curl2curl: dict[ffi.CData, Curl] = {}  # c curl to Curl
        self._sockfds: set[int] = set()  # sockfds
        self.loop = get_selector(
            loop if loop is not None else asyncio.get_running_loop()
        )
        self._timeout_checker = self.loop.create_task(self._force_timeout())
        self._timer: Optional[asyncio.TimerHandle] = None
        self._setup()

    def _setup(self):
        self.setopt(CurlMOpt.TIMERFUNCTION, lib.timer_function)
        self.setopt(CurlMOpt.SOCKETFUNCTION, lib.socket_function)
        self._self_handle = ffi.new_handle(self)
        self.setopt(CurlMOpt.SOCKETDATA, self._self_handle)
        self.setopt(CurlMOpt.TIMERDATA, self._self_handle)
        # self.setopt(CurlMOpt.PIPELINING, CURLPIPE_NOTHING)

    async def close(self):
        """Close and cleanup running timers, readers, writers and handles."""

        # Close and wait for the force timeout checker to complete
        self._timeout_checker.cancel()
        with suppress(asyncio.CancelledError):
            await self._timeout_checker

        # Close all pending futures
        for curl, future in self._curl2future.items():
            lib.curl_multi_remove_handle(self._curlm, curl._curl)
            if not future.done() and not future.cancelled():
                future.set_result(None)

        # Cleanup curl_multi handle
        lib.curl_multi_cleanup(self._curlm)
        self._curlm = None

        # Remove add readers and writers
        for sockfd in self._sockfds:
            self.loop.remove_reader(sockfd)
            self.loop.remove_writer(sockfd)

        # Cancel all time functions
        if self._timer:
            self._timer.cancel()

    async def _force_timeout(self):
        """This coroutine is used to safeguard from any missing signals from curl, and
        put everything back on track"""
        while True:
            if not self._curlm:
                break
            self.socket_action(CURL_SOCKET_TIMEOUT, CURL_POLL_NONE)
            await asyncio.sleep(0.1)

    def add_handle(self, curl: Curl):
        """Add a curl handle to be managed by curl_multi. This is the equivalent of
        `perform` in the async world."""

        curl._ensure_cacert()
        errcode = lib.curl_multi_add_handle(self._curlm, curl._curl)
        self._check_error(errcode)
        future = self.loop.create_future()
        self._curl2future[curl] = future
        self._curl2curl[curl._curl] = curl
        return future

    def socket_action(self, sockfd: int, ev_bitmask: int) -> int:
        """wrapper for curl_multi_socket_action,
        returns the number of running curl handles."""
        running_handle = ffi.new("int *")
        errcode = lib.curl_multi_socket_action(
            self._curlm, sockfd, ev_bitmask, running_handle
        )
        self._check_error(errcode)
        return running_handle[0]

    def process_data(self, sockfd: int, ev_bitmask: int):
        """Call curl_multi_info_read to read data for given socket."""
        if not self._curlm:
            warnings.warn(
                "Curlm already closed! quitting from process_data",
                CurlCffiWarning,
                stacklevel=2,
            )
            return

        self.socket_action(sockfd, ev_bitmask)

        msg_in_queue = ffi.new("int *")
        while True:
            try:
                curl_msg = lib.curl_multi_info_read(self._curlm, msg_in_queue)
                # NULL is returned as a signal that no more to be get at this point
                if curl_msg == ffi.NULL:
                    break
                if curl_msg.msg == CURLMSG_DONE:
                    curl = self._curl2curl[curl_msg.easy_handle]
                    retcode = curl_msg.data.result
                    if retcode == 0:
                        self.set_result(curl)
                    else:
                        self.set_exception(curl, curl._get_error(retcode, "perform"))
                else:
                    print("NOT DONE")  # Will not reach, for nothing else being defined.
            except Exception:
                warnings.warn(
                    "Unexpected curl multi state in process_data, "
                    "please open an issue on GitHub\n",
                    CurlCffiWarning,
                    stacklevel=2,
                )

    def _pop_future(self, curl: Curl):
        errcode = lib.curl_multi_remove_handle(self._curlm, curl._curl)
        self._check_error(errcode)
        self._curl2curl.pop(curl._curl, None)
        return self._curl2future.pop(curl, None)

    def remove_handle(self, curl: Curl):
        """Cancel a future for given curl handle."""
        future = self._pop_future(curl)
        if future and not future.done() and not future.cancelled():
            future.cancel()

    def set_result(self, curl: Curl):
        """Mark a future as done for given curl handle."""
        future = self._pop_future(curl)
        if future and not future.done() and not future.cancelled():
            future.set_result(None)

    def set_exception(self, curl: Curl, exception):
        """Raise exception of a future for given curl handle."""
        future = self._pop_future(curl)
        if future and not future.done() and not future.cancelled():
            future.set_exception(exception)

    def _check_error(self, errcode: int, *args: Any):
        if errcode == CurlECode.OK:
            return
        errmsg = lib.curl_multi_strerror(errcode)
        action = " ".join([str(a) for a in args])
        raise CurlError(
            f"Failed in {action}, multi: ({errcode}) {errmsg}. "
            "See https://curl.se/libcurl/c/libcurl-errors.html first for more "
            "details. Please open an issue on GitHub to help debug this error.",
        )

    def setopt(self, option, value):
        """Wrapper around curl_multi_setopt."""
        if option in (
            CurlMOpt.PIPELINING,
            CurlMOpt.MAXCONNECTS,
            CurlMOpt.MAX_HOST_CONNECTIONS,
            CurlMOpt.MAX_PIPELINE_LENGTH,
            CurlMOpt.MAX_TOTAL_CONNECTIONS,
            CurlMOpt.MAX_CONCURRENT_STREAMS,
        ):
            c_value = ffi.new("long*", value)
        else:
            c_value = value
        return lib.curl_multi_setopt(self._curlm, option, c_value)
