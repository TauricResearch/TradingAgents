import json
import tempfile
from pathlib import Path

import pytest

from tradingagents.logging import StructuredLogger, get_logger, LogContext


@pytest.mark.unit
class TestStructuredLogger:
    def test_basic_logging(self, tmp_path):
        logger = StructuredLogger("test_basic", log_dir=tmp_path, run_id="test-run")
        logger.info("hello world", key="value")
        logger.close()

        log_files = list(tmp_path.glob("*.jsonl"))
        assert len(log_files) == 1
        assert log_files[0].name == "test-run.jsonl"

        entries = [json.loads(line) for line in log_files[0].read_text().strip().splitlines()]
        assert len(entries) == 1
        assert entries[0]["level"] == "INFO"
        assert entries[0]["message"] == "hello world"
        assert entries[0]["run_id"] == "test-run"

    def test_severity_levels(self, tmp_path):
        logger = StructuredLogger("test_severity", log_dir=tmp_path, run_id="sev-run")
        logger.debug("debug msg")
        logger.info("info msg")
        logger.warning("warn msg")
        logger.error("error msg")
        logger.close()

        log_files = list(tmp_path.rglob("*.jsonl"))
        assert len(log_files) == 1

        entries = [json.loads(line) for line in log_files[0].read_text().strip().splitlines()]
        assert len(entries) == 4
        assert entries[0]["level"] == "DEBUG"
        assert entries[1]["level"] == "INFO"
        assert entries[2]["level"] == "WARNING"
        assert entries[3]["level"] == "ERROR"

    def test_context_enrichment(self, tmp_path):
        logger = StructuredLogger("test_context", log_dir=tmp_path, run_id="ctx-run")
        logger.info("no context")
        logger.info("with context", ticker="AAPL", date="2026-01-15")
        logger.info("no context again")
        logger.close()

        log_files = list(tmp_path.rglob("*.jsonl"))
        entries = [json.loads(line) for line in log_files[0].read_text().strip().splitlines()]

        assert entries[0]["ticker"] is None
        assert entries[1]["ticker"] == "AAPL"
        assert entries[1]["date"] == "2026-01-15"
        assert entries[2]["ticker"] is None

    def test_logcontext_context_manager(self, tmp_path):
        logger = StructuredLogger("test_ctxmgr", log_dir=tmp_path, run_id="ctxmgr-run")

        with LogContext(ticker="SPY", date="2026-05-10", agent="Market Analyst"):
            logger.info("inside context")

        logger.info("outside context")
        logger.close()

        log_files = list(tmp_path.rglob("*.jsonl"))
        entries = [json.loads(line) for line in log_files[0].read_text().strip().splitlines()]

        assert entries[0]["ticker"] == "SPY"
        assert entries[0]["date"] == "2026-05-10"
        assert entries[0]["agent"] == "Market Analyst"
        assert entries[1]["ticker"] is None

    def test_run_id_unique(self):
        logger1 = StructuredLogger("test_a", run_id="custom-a")
        logger2 = StructuredLogger("test_b", run_id="custom-b")
        assert logger1.run_id == "custom-a"
        assert logger2.run_id == "custom-b"
        logger1.close()
        logger2.close()


@pytest.mark.unit
class TestGetLogger:
    def test_returns_cached_instance(self, tmp_path):
        a = get_logger("cached_test", log_dir=tmp_path, run_id="r1")
        b = get_logger("cached_test")
        assert a is b
        a.close()


@pytest.mark.unit
class TestLogContext:
    def test_context_isolation(self, tmp_path):
        logger = StructuredLogger("test_isolation", log_dir=tmp_path, run_id="iso-run")

        with LogContext(ticker="A"):
            logger.info("msg1")
            with LogContext(ticker="B"):
                logger.info("msg2")
            logger.info("msg3")

        logger.close()
        log_files = list(tmp_path.rglob("*.jsonl"))
        entries = [json.loads(line) for line in log_files[0].read_text().strip().splitlines()]

        assert entries[0]["ticker"] == "A"
        assert entries[1]["ticker"] == "B"
        assert entries[2]["ticker"] == "A"
