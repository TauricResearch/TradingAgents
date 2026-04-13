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
        with pytest.raises(AnalysisExecutorError, match="required markers: RESULT_META, ANALYSIS_COMPLETE"):
            await executor.execute(
                task_id="task-1",
                ticker="AAPL",
                date="2026-04-13",
                request_context=build_request_context(
                    provider_api_key="ctx-key",
                    llm_provider="anthropic",
                    backend_url="https://api.minimaxi.com/anthropic",
                ),
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
                request_context=build_request_context(
                    provider_api_key="ctx-key",
                    llm_provider="anthropic",
                    backend_url="https://api.minimaxi.com/anthropic",
                ),
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


def test_executor_requires_result_meta_on_success():
    with pytest.raises(AnalysisExecutorError, match="required markers: RESULT_META"):
        LegacySubprocessAnalysisExecutor._parse_output(
            stdout_lines=[
                'SIGNAL_DETAIL:{"quant_signal":"HOLD","llm_signal":"BUY","confidence":0.6}',
                "ANALYSIS_COMPLETE:OVERWEIGHT",
            ],
            ticker="AAPL",
            date="2026-04-12",
            contract_version="v1alpha1",
            executor_type="legacy_subprocess",
        )


def test_executor_injects_provider_specific_env(monkeypatch):
    captured = {}
    process = _FakeProcess(
        _FakeStdout(
            [
                b'SIGNAL_DETAIL:{"quant_signal":"BUY","llm_signal":"BUY","confidence":0.8}\n',
                b'RESULT_META:{"degrade_reason_codes":[],"data_quality":{"state":"ok"}}\n',
                b"ANALYSIS_COMPLETE:BUY\n",
            ]
        ),
        returncode=0,
    )

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["env"] = kwargs["env"]
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    executor = LegacySubprocessAnalysisExecutor(
        analysis_python=Path("/usr/bin/python3"),
        repo_root=Path("."),
        api_key_resolver=lambda provider="openai": "fallback-key",
    )

    async def scenario():
        await executor.execute(
            task_id="task-provider",
            ticker="AAPL",
            date="2026-04-13",
            request_context=build_request_context(
                auth_key="dashboard-key",
                provider_api_key="provider-key",
                llm_provider="openai",
                backend_url="https://api.openai.com/v1",
                deep_think_llm="gpt-5.4",
                quick_think_llm="gpt-5.4-mini",
            ),
        )

    asyncio.run(scenario())

    assert captured["env"]["TRADINGAGENTS_LLM_PROVIDER"] == "openai"
    assert captured["env"]["TRADINGAGENTS_BACKEND_URL"] == "https://api.openai.com/v1"
    assert captured["env"]["OPENAI_API_KEY"] == "provider-key"
    assert "ANTHROPIC_API_KEY" not in captured["env"]


def test_executor_requires_result_meta_on_failure(monkeypatch):
    process = _FakeProcess(
        _FakeStdout([]),
        stderr=b"ANALYSIS_ERROR:boom\n",
        returncode=1,
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
        with pytest.raises(AnalysisExecutorError, match="required markers: RESULT_META"):
            await executor.execute(
                task_id="task-failure",
                ticker="AAPL",
                date="2026-04-13",
                request_context=build_request_context(
                    provider_api_key="ctx-key",
                    llm_provider="anthropic",
                    backend_url="https://api.minimaxi.com/anthropic",
                ),
            )

    asyncio.run(scenario())
