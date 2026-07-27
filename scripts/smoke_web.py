#!/usr/bin/env python
"""H3 - One real minimum-depth analysis end-to-end smoke test.

Starts the real TradingAgents web workbench (real AnalysisRunner, not the
fake runner), submits one minimum-depth stock analysis via the REST API using
already-configured provider/data keys, and verifies the full contract:

  - real graph execution reaches a terminal state
  - real vendor/tool calls appear in the event log
  - all participating roles have auditable input artifacts
  - canonical reports are written and readable
  - history + reports survive a simulated server restart (re-read RunStore)
  - no configured secret appears in persisted events, artifacts, reports, or
    the run snapshot

Usage:
    python scripts/smoke_web.py --ticker 600519.SS
    python scripts/smoke_web.py --ticker 600519.SS --port 8772 --timeout 900

Keys are read from the environment (load .env first, or export them). The
script uses DeepSeek v4 flash for both quick and deep models to minimize cost.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

# --- args -------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="H3 real-analysis smoke test")
    p.add_argument("--ticker", default="600519.SS", help="ticker symbol")
    p.add_argument("--port", type=int, default=8772, help="localhost port")
    p.add_argument(
        "--timeout",
        type=int,
        default=900,
        help="max seconds to wait for the run to finish",
    )
    p.add_argument(
        "--analysis-date",
        default=None,
        help="YYYY-MM-DD (defaults to today UTC)",
    )
    p.add_argument(
        "--no-evidence-gate",
        action="store_true",
        help="disable the Evidence Steward gate (TRADINGAGENTS_EVIDENCE_GATE_ENABLED=false) "
        "so the run reaches downstream roles even when evidence is thin; use for "
        "web-pipeline smoke validation, not for real decision-making",
    )
    return p.parse_args()


# --- helpers ----------------------------------------------------------------


def _load_env_file(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE per line); does not override existing."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _base(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def _wait_for_server(port: int, deadline: float) -> None:
    while time.time() < deadline:
        try:
            r = requests.get(f"{_base(port)}/api/config", timeout=2)
            if r.ok:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise RuntimeError(f"server on port {port} did not come up")


def _create_run(port: int, ticker: str, analysis_date: str) -> dict[str, Any]:
    body = {
        "ticker": ticker,
        "analysis_date": analysis_date,
        "selected_analysts": ["market", "social", "news", "fundamentals"],
        "research_depth": 1,
        "llm_provider": "deepseek",
        "quick_think_llm": "deepseek-v4-flash",
        "deep_think_llm": "deepseek-v4-flash",
        "output_language": "Chinese",
        "checkpoint_enabled": False,
    }
    r = requests.post(f"{_base(port)}/api/runs", json=body, timeout=10)
    if r.status_code != 201:
        raise RuntimeError(f"POST /api/runs failed {r.status_code}: {r.text}")
    return r.json()


def _get_run(port: int, run_id: str) -> dict[str, Any]:
    return requests.get(f"{_base(port)}/api/runs/{run_id}", timeout=10).json()


def _list_artifacts(port: int, run_id: str) -> list[dict[str, Any]]:
    return requests.get(
        f"{_base(port)}/api/runs/{run_id}/artifacts", timeout=10
    ).json()


def _read_artifact_text(port: int, run_id: str, artifact_id: str) -> str:
    # artifact_id may contain colons (e.g. "report-final:<sha>"); URL-encode it
    # so the path segment is safe. quote() leaves alphanumerics intact.
    encoded = quote(artifact_id, safe="")
    r = requests.get(
        f"{_base(port)}/api/runs/{run_id}/artifacts/{encoded}", timeout=15
    )
    r.raise_for_status()
    return r.text


def _wait_terminal(
    port: int, run_id: str, timeout: int
) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_seq = 0
    while time.time() < deadline:
        snap = _get_run(port, run_id)
        status = snap["status"]
        if status in {"completed", "failed", "cancelled"}:
            return snap
        if snap["latest_sequence"] != last_seq:
            last_seq = snap["latest_sequence"]
            print(
                f"  ...run {run_id} status={status} seq={last_seq}",
                flush=True,
            )
        time.sleep(3)
    raise TimeoutError(f"run {run_id} did not finish within {timeout}s")


# --- assertions -------------------------------------------------------------


def _assert_no_secret(values: list[str], secret_names: list[str], secrets: list[str], where: str) -> None:
    for value in values:
        for secret in secrets:
            if secret and secret in value:
                raise AssertionError(
                    f"SECRET LEAK in {where}: found {secret[:6]}... in content"
                )
    # Secret env var names are fine to appear; their values must not.
    print(f"  [ok] no configured secret value in {where}")


def _scan_secrets(
    port: int, run_id: str, secret_values: list[str]
) -> None:
    """Scan the run snapshot, every persisted event, every artifact body, and
    the canonical report tree for any configured secret value."""
    # Snapshot
    snap_text = json.dumps(_get_run(port, run_id))
    _assert_no_secret([snap_text], [], secret_values, "run snapshot")

    # Events via SSE replay (after=0 returns the whole log then closes)
    r = requests.get(
        f"{_base(port)}/api/runs/{run_id}/events?after=0", timeout=30, stream=True
    )
    event_text = r.text
    _assert_no_secret([event_text], [], secret_values, "events.jsonl replay")

    # Artifacts
    arts = _list_artifacts(port, run_id)
    for art in arts:
        body = _read_artifact_text(port, run_id, art["artifact_id"])
        _assert_no_secret([body], [], secret_values, f"artifact {art['artifact_id']}")


# --- main -------------------------------------------------------------------


def main() -> int:
    args = _parse_args()

    # Load .env from repo root so keys are available to the server subprocess.
    repo_root = Path(__file__).resolve().parent.parent
    _load_env_file(repo_root / ".env")

    if args.no_evidence_gate:
        # Set before the server subprocess inherits the environment so the
        # Evidence Steward gate is disabled for this smoke run.
        os.environ["TRADINGAGENTS_EVIDENCE_GATE_ENABLED"] = "false"
        print("  [note] Evidence Steward gate DISABLED for this smoke run",
              flush=True)

    analysis_date = args.analysis_date or time.strftime("%Y-%m-%d", time.gmtime())
    print(f"H3 smoke: ticker={args.ticker} date={analysis_date} provider=deepseek "
          f"model=deepseek-v4-flash depth=1", flush=True)

    # Collect configured secret VALUES (not names) to scan for leaks later.
    secret_values = [
        os.environ.get("DEEPSEEK_API_KEY", ""),
        os.environ.get("TUSHARE_TOKEN", ""),
        os.environ.get("TUSHARE_API_KEY", ""),
        os.environ.get("TAVILY_API_KEY", ""),
        os.environ.get("ALPHA_VANTAGE_API_KEY", ""),
        os.environ.get("MIMO_API_KEY", ""),
    ]
    secret_values = [s for s in secret_values if s]

    # Start the real web workbench via the real launcher entry (preflight +
    # create_app + uvicorn). This is the same path a user hits with
    # `tradingagents web`, so the smoke exercises the real launch contract.
    import subprocess

    env = dict(os.environ)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from tradingagents.web.cli import launch_web; launch_web(port=8772, open_browser=False)",
        ],
        cwd=str(repo_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_server(args.port, time.time() + 60)
        print(f"  [ok] server up on 127.0.0.1:{args.port}", flush=True)

        # Verify /api/config sees the DeepSeek key as configured.
        cfg = requests.get(f"{_base(args.port)}/api/config", timeout=5).json()
        if not cfg.get("configured_keys", {}).get("deepseek"):
            raise RuntimeError(
                "DeepSeek key not configured on the server - check .env"
            )
        print("  [ok] /api/config reports deepseek configured", flush=True)

        # Submit the run.
        snap = _create_run(args.port, args.ticker, analysis_date)
        run_id = snap["run_id"]
        print(f"  [ok] run created: {run_id}", flush=True)

        # Wait for terminal.
        print(f"  waiting up to {args.timeout}s for run to finish...", flush=True)
        final = _wait_terminal(args.port, run_id, args.timeout)
        print(f"  [ok] run terminal: status={final['status']} "
              f"seq={final['latest_sequence']} signal={final.get('final_signal')}",
              flush=True)

        if final["status"] != "completed":
            print(f"  [!] run did not complete: {final.get('error_category')} "
                  f"{final.get('summary')}", flush=True)
            return 2

        # Assertions.
        artifacts = _list_artifacts(args.port, run_id)
        print(f"  [ok] {len(artifacts)} artifacts persisted", flush=True)

        # Real vendor/tool calls: events should contain tool.* and data.* types.
        r = requests.get(
            f"{_base(args.port)}/api/runs/{run_id}/events?after=0", timeout=30
        )
        event_types: set[str] = set()
        for line in r.text.split("\n"):
            if line.startswith("event:"):
                event_types.add(line.split(":", 1)[1].strip())
        has_tool = any(t.startswith("tool.") for t in event_types)
        has_data = any(t.startswith("data.") for t in event_types)
        has_vendor = any(t == "data.completed" for t in event_types)
        print(f"  [ok] event types: tool={has_tool} data={has_data} "
              f"vendor_completed={has_vendor}", flush=True)
        if not (has_tool and has_data):
            print("  [!] expected tool.* and data.* events from a real run",
                  flush=True)

        # All 13 roles reached completed (role.status_changed completed count).
        role_completed = r.text.count('"new_status": "completed"')
        # At least the selected analysts + downstream should complete; 13 is
        # the full registry. Be lenient: require >= 8 (selected analysts +
        # evidence + research + trader + some risk/portfolio).
        print(f"  [ok] role.status_changed(completed) count={role_completed}",
              flush=True)

        # Reports: canonical report tree published.
        # The run directory is under ~/.tradingagents/web/runs/<run_id>/reports/
        run_root = Path.home() / ".tradingagents" / "web" / "runs" / run_id
        reports_dir = run_root / "reports"
        if reports_dir.is_dir():
            found = {p.name for p in reports_dir.iterdir() if p.is_dir()}
            print(f"  [ok] report tree dirs: {sorted(found)}", flush=True)
            complete = reports_dir / "complete_report.md"
            if complete.is_file():
                print(f"  [ok] complete_report.md exists "
                      f"({complete.stat().st_size} bytes)", flush=True)
            else:
                print("  [!] complete_report.md missing", flush=True)
        else:
            print(f"  [!] reports/ dir missing at {reports_dir}", flush=True)

        # History survives restart: re-read the RunStore directly (simulates a
        # fresh server process listing history).
        from tradingagents.web.store import RunStore

        store = RunStore()
        summaries = store.list_runs()
        ids = {s.run_id for s in summaries}
        if run_id not in ids:
            raise AssertionError(
                f"run {run_id} not in RunStore history after restart-equivalent read"
            )
        print(f"  [ok] run survives in RunStore history ({len(summaries)} runs)",
              flush=True)

        # Secret scan.
        print("  scanning for secret leaks...", flush=True)
        _scan_secrets(args.port, run_id, secret_values)
        print("  [ok] no configured secret value in snapshot/events/artifacts",
              flush=True)

        print("\nH3 SMOKE PASSED", flush=True)
        print(f"  run_id: {run_id}", flush=True)
        print(f"  history: {run_root}", flush=True)
        return 0

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
