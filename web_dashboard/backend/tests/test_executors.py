import asyncio
from pathlib import Path

import pytest

from services.executor import AnalysisExecutorError, LegacySubprocessAnalysisExecutor
from services.request_context import build_request_context


class _FakeStdout:
    def __init__(self, lines, *, stall: bool = False):
        self._lines = list(lines)
        self._stall = stall

    async def readline(self):
        if self._stall:
            await asyncio.sleep(3600)
        if self._lines:
            return self._lines.pop(0)
        return b""


class _FakeStderr:
    def __init__(self, payload: bytes = b""):
        self._payload = payload

    async def read(self):
        return self._payload


class _FakeProcess:
    def __init__(self, stdout, *, stderr: bytes = b"", returncode=None):
        self.stdout = stdout
        self.stderr = _FakeStderr(stderr)
        self.returncode = returncode
        self.kill_called = False
        self.wait_called = False

    async def wait(self):
        self.wait_called = True
        if self.returncode is None:
            self.returncode = -9 if self.kill_called else 0
        return self.returncode

    def kill(self):
        self.kill_called = True
        self.returncode = -9


def test_executor_raises_when_required_markers_missing(monkeypatch):
    process = _FakeProcess(
        _FakeStdout(
            [
                b"STAGE:analysts\n",
                b"STAGE:portfolio\n",
                b"SIGNAL_DETAIL:{\"quant_signal\":\"BUY\",\"llm_signal\":\"BUY\",\"confidence\":0.8}\n",
            ],
        ),
        returncode=0,
    )

    async def fake_create_subprocess_exec(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    executor = LegacySubprocessAnalysisExecutor(
        analysis_python=Path("/usr/bin/python3"),
        repo_root=Path("."),
        api_key_resolver=lambda: "env-key",
    )

    async def scenario():
        with pytest.raises(AnalysisExecutorError, match="required markers: ANALYSIS_COMPLETE"):
            await executor.execute(
                task_id="task-1",
                ticker="AAPL",
                date="2026-04-13",
                request_context=build_request_context(api_key="ctx-key"),
            )

    asyncio.run(scenario())


def test_executor_kills_subprocess_on_timeout(monkeypatch):
    process = _FakeProcess(_FakeStdout([], stall=True))

    async def fake_create_subprocess_exec(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    executor = LegacySubprocessAnalysisExecutor(
        analysis_python=Path("/usr/bin/python3"),
        repo_root=Path("."),
        api_key_resolver=lambda: "env-key",
        stdout_timeout_secs=0.01,
    )

    async def scenario():
        with pytest.raises(AnalysisExecutorError, match="timed out"):
            await executor.execute(
                task_id="task-2",
                ticker="AAPL",
                date="2026-04-13",
                request_context=build_request_context(api_key="ctx-key"),
            )

    asyncio.run(scenario())

    assert process.kill_called is True
    assert process.wait_called is True


def test_executor_marks_degraded_success_when_result_meta_reports_data_quality():
    output = LegacySubprocessAnalysisExecutor._parse_output(
        stdout_lines=[
            'SIGNAL_DETAIL:{"quant_signal":"HOLD","llm_signal":"BUY","confidence":0.6}',
            'RESULT_META:{"degrade_reason_codes":["non_trading_day"],"data_quality":{"state":"non_trading_day","requested_date":"2026-04-12"}}',
            "ANALYSIS_COMPLETE:OVERWEIGHT",
        ],
        ticker="AAPL",
        date="2026-04-12",
        contract_version="v1alpha1",
        executor_type="legacy_subprocess",
    )

    contract = output.to_result_contract(
        task_id="task-3",
        ticker="AAPL",
        date="2026-04-12",
        created_at="2026-04-12T10:00:00",
        elapsed_seconds=3,
    )

    assert contract["status"] == "degraded_success"
    assert contract["data_quality"]["state"] == "non_trading_day"
    assert contract["degradation"]["reason_codes"] == ["non_trading_day"]
