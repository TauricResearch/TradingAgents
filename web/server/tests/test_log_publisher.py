import logging
from unittest.mock import AsyncMock

from web.server.log_publisher import LogPublisher, setup_log_publisher, teardown_log_publisher


class TestLogPublisher:
    def test_emit_fans_out_to_subscribers(self):
        pub = LogPublisher()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        pub.subscribe(ws1)
        pub.subscribe(ws2)

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="",
            lineno=0, msg="hello", args=(), exc_info=None
        )
        pub.emit(record)
        assert ws1.send_json.called
        assert ws2.send_json.called

    def test_unsubscribe_removes_client(self):
        pub = LogPublisher()
        ws = AsyncMock()
        pub.subscribe(ws)
        pub.unsubscribe(ws)

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="",
            lineno=0, msg="hello", args=(), exc_info=None
        )
        pub.emit(record)
        assert not ws.send_json.called

    def test_level_filter_excludes_debug_when_threshold_is_info(self):
        pub = LogPublisher(min_level=logging.INFO)
        ws = AsyncMock()
        pub.subscribe(ws)

        debug_record = logging.LogRecord(
            name="test", level=logging.DEBUG, pathname="",
            lineno=0, msg="debug msg", args=(), exc_info=None
        )
        pub.emit(debug_record)
        assert not ws.send_json.called

    def test_level_filter_allows_info_when_threshold_is_info(self):
        pub = LogPublisher(min_level=logging.INFO)
        ws = AsyncMock()
        pub.subscribe(ws)

        info_record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="",
            lineno=0, msg="info msg", args=(), exc_info=None
        )
        pub.emit(info_record)
        assert ws.send_json.called

    def test_setup_and_teardown(self):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            pub = setup_log_publisher(loop, min_level=logging.INFO)
            assert pub is not None
            teardown_log_publisher()
        finally:
            loop.close()
