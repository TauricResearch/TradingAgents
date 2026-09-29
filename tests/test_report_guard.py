"""Integration coverage for duplicate generation across shell launchers."""

import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHERS = [
    'run_missing_today_claude.sh', 'run_missing_today_gemini.sh',
    'run_missing_today_gpt.sh', 'run_all_today.sh',
]


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'repo with spaces'
    (root / 'scripts').mkdir(parents=True)
    (root / 'bin').mkdir()
    for name in LAUNCHERS + ['default_tickers.sh', 'report_guard.py']:
        shutil.copy2(ROOT / 'scripts' / name, root / 'scripts' / name)
    worker = root / 'worker.py'
    worker.write_text('''import os, sys, time
from pathlib import Path
root = Path(os.environ['FIXTURE_ROOT'])
value = lambda flag: sys.argv[sys.argv.index(flag) + 1]
ticker, date, model = value('--ticker'), value('--date'), value('--deep-model')
with (root / 'calls').open('a') as f:
    f.write(f'{ticker} {date} {model}\\n')
print('original worker log', flush=True)
(root / 'ready').touch()
if os.environ.get('WAIT_FOR_RELEASE'):
    deadline = time.monotonic() + 15
    while not (root / 'release').exists():
        if time.monotonic() > deadline:
            raise SystemExit(19)
        time.sleep(0.02)
if os.environ.get('FAIL_WORKER'):
    raise SystemExit(17)
slug = model.strip().translate(str.maketrans({'/': '-', ':': '-', '.': '-'}))
(root / 'docs' / ticker / (date.replace('-', '') + '_' + slug + '_20000102_030405')).mkdir(parents=True)
''')
    uv = root / 'bin/uv'
    uv.write_text(f'#!/bin/bash\nexec {shlex.quote(sys.executable)} {shlex.quote(str(worker))} "$@"\n')
    uv.chmod(0o755)
    env = {
        'PATH': str(root / 'bin') + os.pathsep + os.defpath,
        'TRADINGAGENTS_MODE': 'direct',
        'TRADINGAGENTS_PYTHON': '/usr/bin/true',
        'TRADINGAGENTS_DATE': '2000-01-01',
        'TRADINGAGENTS_DEEP_MODEL': 'provider/model.1:tag',
        'TA_LOGDIR': str(root / 'logs'),
        'FIXTURE_ROOT': str(root),
    }
    return root, env


def invoke(root, env, launcher, *tickers):
    return subprocess.run(
        ['/bin/bash', str(root / 'scripts' / launcher), *tickers],
        env=env, capture_output=True, text=True, timeout=15,
    )


@pytest.mark.parametrize('launcher', LAUNCHERS)
def test_existing_tuple_skipped_but_other_tuples_generate(repo, launcher):
    root, env = repo
    # These must not suppress the requested date/model/ticker.
    for ticker, folder in [
        ('NVDA', '19991231_provider-model-1-tag_20000102_030405'),
        ('NVDA', '20000101_provider-model-1-tag_other_20000102_030405'),
        ('AMD', '20000101_provider-model-1-tag_20000102_030405'),
    ]:
        (root / 'docs' / ticker / folder).mkdir(parents=True)
    result = invoke(root, env, launcher, 'nvda', 'NVDA', 'nvda')
    assert result.returncode == 0, result.stdout + result.stderr
    assert not result.stderr
    assert '=== DONE: 1/1' in result.stdout
    calls = (root / 'calls').read_text().splitlines()
    assert calls == ['NVDA 2000-01-01 provider/model.1:tag']
    log = (root / 'logs/NVDA.log').read_text()
    result = invoke(root, env, launcher, 'NVDA')
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'Nothing to run' in result.stdout
    assert (root / 'calls').read_text().splitlines() == calls
    assert (root / 'logs/NVDA.log').read_text() == log


def wait_until(predicate):
    deadline = time.monotonic() + 10
    while not predicate():
        assert time.monotonic() < deadline, 'timed out waiting for worker/lock'
        time.sleep(0.02)


def test_concurrent_launchers_generate_once(repo):
    root, env = repo
    env['WAIT_FOR_RELEASE'] = '1'
    processes = []
    outputs = []
    try:
        for index, launcher in enumerate(LAUNCHERS):
            output = root / f'output-{index}'
            with output.open('w') as stream:
                process = subprocess.Popen(
                    ['/bin/bash', str(root / 'scripts' / launcher), 'NVDA'],
                    env=env, stdout=stream, stderr=subprocess.STDOUT,
                )
            processes.append(process)
            outputs.append(output)
            if index == 0:
                wait_until(lambda: (root / 'ready').exists())
            else:
                wait_until(lambda path=output: '[WAIT NVDA]' in path.read_text())
        (root / 'release').touch()
        for process, output in zip(processes, outputs, strict=True):
            assert process.wait(timeout=15) == 0, output.read_text()
        assert len((root / 'calls').read_text().splitlines()) == 1
        assert all('[SKIP NVDA]' in path.read_text() for path in outputs[1:])
        assert (root / 'logs/NVDA.log').read_text() == 'original worker log\n'
    finally:
        (root / 'release').touch()
        for process in processes:
            if process.poll() is None:
                process.wait(timeout=15)


def test_failure_can_be_retried_by_another_launcher(repo):
    root, env = repo
    result = invoke(root, dict(env, FAIL_WORKER='1'), LAUNCHERS[0], 'NVDA')
    assert result.returncode == 1
    assert 'STILL FAILING' in result.stdout
    result = invoke(root, env, LAUNCHERS[2], 'NVDA')
    assert result.returncode == 0, result.stdout + result.stderr
    assert len((root / 'calls').read_text().splitlines()) == 2


def test_terminated_guard_releases_lock_after_worker_exits(repo):
    root, env = repo
    env['WAIT_FOR_RELEASE'] = '1'
    command = [
        sys.executable, str(root / 'scripts/report_guard.py'), 'run',
        '--reports-dir', str(root / 'docs'), '--date', '2000-01-01',
        '--model', env['TRADINGAGENTS_DEEP_MODEL'], '--ticker', 'NVDA',
        '--log', str(root / 'logs/NVDA.log'), '--', str(root / 'bin/uv'),
        '--ticker', 'NVDA', '--date', '2000-01-01',
        '--deep-model', env['TRADINGAGENTS_DEEP_MODEL'],
    ]
    process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        wait_until(lambda: (root / 'ready').exists())
        process.terminate()
        process.communicate(timeout=10)
        assert process.returncode == 143
    finally:
        (root / 'release').touch()
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=10)
    result = invoke(root, env, LAUNCHERS[1], 'NVDA')
    assert result.returncode == 0, result.stdout + result.stderr
    assert len((root / 'calls').read_text().splitlines()) == 2


@pytest.mark.parametrize('launcher', LAUNCHERS)
def test_discovery_errors_fail_closed(repo, launcher):
    root, env = repo
    (root / 'scripts/report_guard.py').unlink()
    result = invoke(root, env, launcher, 'NVDA')
    assert result.returncode != 0
    assert 'Nothing to run' not in result.stdout
    assert not (root / 'calls').exists()


@pytest.mark.parametrize('dimension', ['date', 'model', 'ticker'])
def test_different_identities_can_run_concurrently(repo, dimension):
    root, env = repo
    env['WAIT_FOR_RELEASE'] = '1'
    second_env = dict(env, TA_LOGDIR=str(root / 'second-logs'))
    second_ticker = 'NVDA'
    if dimension == 'date':
        second_env['TRADINGAGENTS_DATE'] = '2000-01-02'
    elif dimension == 'model':
        second_env['TRADINGAGENTS_DEEP_MODEL'] = 'different-model'
    else:
        second_ticker = 'AMD'
    processes = []
    try:
        for worker_env, ticker in [(env, 'NVDA'), (second_env, second_ticker)]:
            processes.append(subprocess.Popen(
                ['/bin/bash', str(root / 'scripts/run_missing_today_gpt.sh'), ticker],
                env=worker_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ))
        # Both workers must start before either is allowed to finish.
        wait_until(lambda: (root / 'calls').exists() and len((root / 'calls').read_text().splitlines()) == 2)
        (root / 'release').touch()
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, stdout + stderr
    finally:
        (root / 'release').touch()
        for process in processes:
            if process.poll() is None:
                process.communicate(timeout=15)
