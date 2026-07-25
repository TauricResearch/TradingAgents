"""阶段 4 性能基线测量：list_runs / list_artifacts / read_artifact 延迟。

启动 e2e_server（fake runner），串行造 20 个 run（SingleRunManager 限制），
测量三个 API 的中位数延迟。只测量不优化（准确度优先）。

用法：python scripts/perf_baseline.py
结果追加到 docs/web-workbench-test-plan.md 的 §12。
"""
from __future__ import annotations

import asyncio
import os
import statistics
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn

sys.path.insert(0, str(Path(__file__).parent))
os.environ["TRADINGAGENTS_E2E_RUN_ROOT"] = "/tmp/tradingagents-perf-runs"

from e2e_server import build_app  # noqa: E402

BASE = "http://127.0.0.1:8772"
BODY = {
    "ticker": "600519.SS",
    "analysis_date": "2026-07-18",
    "selected_analysts": ["market"],
    "research_depth": 1,
    "llm_provider": "deepseek",
    "quick_think_llm": "deepseek-chat",
    "deep_think_llm": "deepseek-reasoner",
    "output_language": "Chinese",
    "checkpoint_enabled": False,
}
TERMINAL = {"completed", "failed", "cancelled"}


async def wait_server(client: httpx.AsyncClient) -> None:
    for _ in range(40):
        try:
            if (await client.get("/api/config")).status_code == 200:
                return
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError("server did not start")


async def create_run_and_wait(client: httpx.AsyncClient) -> str:
    resp = await client.post("/api/runs", json=BODY)
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["run_id"]
    for _ in range(100):
        snap = (await client.get(f"/api/runs/{run_id}")).json()
        if snap["status"] in TERMINAL:
            return run_id
        await asyncio.sleep(0.1)
    raise RuntimeError(f"run {run_id} did not finish")


async def median_ms(client: httpx.AsyncClient, method: str, url: str, n: int = 5) -> float:
    times: list[float] = []
    for _ in range(n):
        t = time.perf_counter()
        r = await client.request(method, url)
        r.raise_for_status()
        times.append((time.perf_counter() - t) * 1000)
    return statistics.median(times)


async def main() -> None:
    config = uvicorn.Config(
        build_app(), host="127.0.0.1", port=8772, log_level="warning"
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        await wait_server(client)
        print("server ready, creating 20 runs...")
        run_ids: list[str] = []
        for i in range(20):
            rid = await create_run_and_wait(client)
            run_ids.append(rid)
            if (i + 1) % 5 == 0:
                print(f"  {i + 1}/20 done")

        list_runs = await median_ms(client, "GET", "/api/runs")
        first = run_ids[0]
        list_art = await median_ms(client, "GET", f"/api/runs/{first}/artifacts")
        artifacts = (await client.get(f"/api/runs/{first}/artifacts")).json()
        first_art = artifacts[0]["artifact_id"]
        read_art = await median_ms(
            client, "GET", f"/api/runs/{first}/artifacts/{first_art}"
        )

        print("\n=== 性能基线（20 run × ~95 事件，5 次中位数）===")
        print(f"GET /api/runs              (list_runs):     {list_runs:7.1f} ms")
        print(f"GET /api/runs/{{id}}/artifacts (list_artifacts): {list_art:7.1f} ms")
        print(f"GET /api/runs/{{id}}/artifacts/{{aid}} (read):   {read_art:7.1f} ms")

        report = f"""
## 12. 性能基线（阶段4测量，{time.strftime("%Y-%m-%d")}）

测量条件：20 个 fake run（每个 ~95 事件），e2e_server 端口 8772，每个 API 跑 5 次取中位数。

| API | 中位数延迟 |
|-----|----------|
| GET /api/runs (list_runs) | {list_runs:.1f} ms |
| GET /api/runs/{{id}}/artifacts (list_artifacts) | {list_art:.1f} ms |
| GET /api/runs/{{id}}/artifacts/{{aid}} (read_artifact) | {read_art:.1f} ms |

已知性能隐患（未优化，准确度优先）：
- `store.py:list_runs` 遍历每个 run 的 events.jsonl 找最后 sequence
- `api.py:_artifact_metadata` 遍历所有事件提取 artifact 元数据
- `api.py:read_artifact` 两次遍历（read_snapshot + _artifact_metadata）

结论：当前性能可接受（用户明确准确度优先于性能），优化延后。
"""
        with open(
            "/Users/david/codespace/TradingAgents/docs/web-workbench-test-plan.md",
            "a",
        ) as f:
            f.write(report)
        print("\n结果已追加到 docs/web-workbench-test-plan.md §12")


if __name__ == "__main__":
    asyncio.run(main())
