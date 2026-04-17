import asyncio
import sys
from pathlib import Path

import pytest

from services.executor import AnalysisExecutorError, LegacySubprocessAnalysisExecutor
from services.request_context import build_request_context


class _FakeStdout:
    def __init__(self, lines, *, stall: bool = False, delay: float = 0.0):
        self._lines = list(lines)
        self._stall = stall
        self._delay = delay

    async def readline(self):
        if self._stall:
            await asyncio.sleep(3600)
        if self._delay:
            await asyncio.sleep(self._delay)
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
        stderr_lines=[],
        ticker="AAPL",
        date="2026-04-12",
        request_context=build_request_context(
            provider_api_key="ctx-key",
            llm_provider="anthropic",
            backend_url="https://api.minimaxi.com/anthropic",
        ),
        contract_version="v1alpha1",
        executor_type="legacy_subprocess",
        stdout_timeout_secs=300.0,
        total_timeout_secs=300.0,
        last_stage="portfolio",
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
    assert output.observation["status"] == "completed"
    assert output.observation["stage"] == "portfolio"


def test_executor_parses_llm_decision_structured_from_signal_detail():
    output = LegacySubprocessAnalysisExecutor._parse_output(
        stdout_lines=[
            'SIGNAL_DETAIL:{"quant_signal":"HOLD","llm_signal":"BUY","confidence":0.6,"llm_decision_structured":{"rating":"BUY","entry_style":"IMMEDIATE"}}',
            'RESULT_META:{"degrade_reason_codes":[],"data_quality":{"state":"ok"}}',
            "ANALYSIS_COMPLETE:BUY",
        ],
        stderr_lines=[],
        ticker="AAPL",
        date="2026-04-12",
        request_context=build_request_context(
            provider_api_key="ctx-key",
            llm_provider="anthropic",
            backend_url="https://api.minimaxi.com/anthropic",
        ),
        contract_version="v1alpha1",
        executor_type="legacy_subprocess",
        stdout_timeout_secs=300.0,
        total_timeout_secs=300.0,
        last_stage="portfolio",
    )

    assert output.llm_decision_structured == {"rating": "BUY", "entry_style": "IMMEDIATE"}


def test_executor_requires_result_meta_on_success():
    with pytest.raises(AnalysisExecutorError, match="required markers: RESULT_META"):
        LegacySubprocessAnalysisExecutor._parse_output(
            stdout_lines=[
                'SIGNAL_DETAIL:{"quant_signal":"HOLD","llm_signal":"BUY","confidence":0.6}',
                "ANALYSIS_COMPLETE:OVERWEIGHT",
            ],
            stderr_lines=[],
            ticker="AAPL",
            date="2026-04-12",
            request_context=build_request_context(
                provider_api_key="ctx-key",
                llm_provider="anthropic",
                backend_url="https://api.minimaxi.com/anthropic",
            ),
            contract_version="v1alpha1",
            executor_type="legacy_subprocess",
            stdout_timeout_secs=300.0,
            total_timeout_secs=300.0,
            last_stage="portfolio",
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
                selected_analysts=["market"],
                analysis_prompt_style="compact",
                llm_timeout=45,
                llm_max_retries=0,
                metadata={
                    "portfolio_context": "Growth exposure already elevated.",
                    "peer_context": "Same-theme rank: leader.",
                    "peer_context_mode": "SAME_THEME_NORMALIZED",
                },
            ),
        )

    asyncio.run(scenario())

    assert captured["env"]["TRADINGAGENTS_LLM_PROVIDER"] == "openai"
    assert captured["env"]["TRADINGAGENTS_BACKEND_URL"] == "https://api.openai.com/v1"
    assert captured["env"]["OPENAI_API_KEY"] == "provider-key"
    assert captured["env"]["TRADINGAGENTS_SELECTED_ANALYSTS"] == "market"
    assert captured["env"]["TRADINGAGENTS_ANALYSIS_PROMPT_STYLE"] == "compact"
    assert captured["env"]["TRADINGAGENTS_LLM_TIMEOUT"] == "45"
    assert captured["env"]["TRADINGAGENTS_LLM_MAX_RETRIES"] == "0"
    assert captured["env"]["TRADINGAGENTS_PORTFOLIO_CONTEXT"] == "Growth exposure already elevated."
    assert captured["env"]["TRADINGAGENTS_PEER_CONTEXT"] == "Same-theme rank: leader."
    assert captured["env"]["TRADINGAGENTS_PEER_CONTEXT_MODE"] == "SAME_THEME_NORMALIZED"
    assert captured["env"]["TRADINGAGENTS_PROVIDER_API_KEY"] == "provider-key"
    assert captured["env"]["TRADINGAGENTS_HEARTBEAT_SECS"] == "10.0"
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


def test_executor_includes_observation_on_timeout(monkeypatch):
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
        with pytest.raises(AnalysisExecutorError) as exc_info:
            await executor.execute(
                task_id="task-timeout-observation",
                ticker="AAPL",
                date="2026-04-13",
                request_context=build_request_context(
                    provider_api_key="ctx-key",
                    llm_provider="anthropic",
                    backend_url="https://api.minimaxi.com/anthropic",
                    metadata={"attempt_index": 0, "attempt_mode": "baseline", "probe_mode": "none"},
                ),
            )
        return exc_info.value

    exc = asyncio.run(scenario())
    assert exc.observation["observation_code"] == "subprocess_stdout_timeout"
    assert exc.observation["attempt_mode"] == "baseline"
    assert exc.observation["provider"] == "anthropic"


def test_executor_collect_markers_tracks_heartbeat_and_auth_checkpoint():
    markers = LegacySubprocessAnalysisExecutor._collect_markers(
        [
            'CHECKPOINT:AUTH:{"provider":"anthropic","api_key_present":true}',
            'HEARTBEAT:{"elapsed_seconds":10.0}',
            "STAGE:trading",
            "RESULT_META:{}",
        ]
    )

    assert markers["auth_checkpoint"] is True
    assert markers["heartbeat"] is True
    assert markers["result_meta"] is True


def test_executor_uses_total_timeout_separately_from_stdout_timeout(monkeypatch):
    process = _FakeProcess(
        _FakeStdout(
            [b'CHECKPOINT:AUTH:{"provider":"anthropic","api_key_present":true}\n'] * 10,
            delay=0.02,
        )
    )

    async def fake_create_subprocess_exec(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    executor = LegacySubprocessAnalysisExecutor(
        analysis_python=Path("/usr/bin/python3"),
        repo_root=Path("."),
        api_key_resolver=lambda: "env-key",
        stdout_timeout_secs=1.0,
    )

    async def scenario():
        with pytest.raises(AnalysisExecutorError, match="total timeout"):
            await executor.execute(
                task_id="task-total-timeout",
                ticker="AAPL",
                date="2026-04-13",
                request_context=build_request_context(
                    provider_api_key="ctx-key",
                    llm_provider="anthropic",
                    backend_url="https://api.minimaxi.com/anthropic",
                    metadata={"stdout_timeout_secs": 1.0, "total_timeout_secs": 0.05},
                ),
            )

    asyncio.run(scenario())

    assert process.kill_called is True


def test_executor_real_subprocess_heartbeat_survives_blocking_sleep(tmp_path):
    script_template = """
import json
import threading
import time

print('CHECKPOINT:AUTH:' + json.dumps({'provider':'anthropic','api_key_present': True}), flush=True)
print('STAGE:analysts', flush=True)
print('STAGE:research', flush=True)
print('STAGE:trading', flush=True)

stop = threading.Event()
def heartbeat():
    while not stop.wait(0.01):
        print('HEARTBEAT:' + json.dumps({'alive': True}), flush=True)

threading.Thread(target=heartbeat, daemon=True).start()
time.sleep(0.12)
stop.set()

print('STAGE:risk', flush=True)
print('STAGE:portfolio', flush=True)
print('SIGNAL_DETAIL:' + json.dumps({'quant_signal':'HOLD','llm_signal':'BUY','confidence':0.8}), flush=True)
print('RESULT_META:' + json.dumps({'degrade_reason_codes': [], 'data_quality': {'state': 'ok'}}), flush=True)
print('ANALYSIS_COMPLETE:BUY', flush=True)
"""

    executor = LegacySubprocessAnalysisExecutor(
        analysis_python=Path(sys.executable),
        repo_root=tmp_path,
        api_key_resolver=lambda: "env-key",
        script_template=script_template,
        stdout_timeout_secs=0.03,
    )

    async def scenario():
        return await executor.execute(
            task_id="task-heartbeat-real",
            ticker="AAPL",
            date="2026-04-13",
            request_context=build_request_context(
                provider_api_key="ctx-key",
                llm_provider="anthropic",
                backend_url="https://api.minimaxi.com/anthropic",
                metadata={
                    "stdout_timeout_secs": 0.03,
                    "total_timeout_secs": 1.0,
                    "heartbeat_interval_secs": 0.01,
                },
            ),
        )

    output = asyncio.run(scenario())
    assert output.decision == "BUY"
    assert output.observation["markers"]["heartbeat"] is True
