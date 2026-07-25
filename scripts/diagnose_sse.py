"""诊断 broker live-queue race。

Python 客户端在 run 进行中订阅 SSE，统计收到的事件数 vs persist 的事件数。
- 若收到数 < persist 数 -> broker 丢事件（方案 C 对症）
- 若收到数 == persist 数 -> broker 正常，问题在前端 onClose（Bug 1）

用法：先启动 e2e_server（python scripts/e2e_server.py），再跑本脚本。
"""
from __future__ import annotations

import asyncio
import time

import httpx

BASE = "http://127.0.0.1:8771"

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

TERMINAL_EVENTS = {
    "event: run.completed",
    "event: run.failed",
    "event: run.cancelled",
    "event: run.interrupted",
}


async def main() -> None:
    async with httpx.AsyncClient(
        base_url=BASE, timeout=httpx.Timeout(30.0)
    ) as client:
        t0 = time.time()
        resp = await client.post("/api/runs", json=BODY)
        assert resp.status_code == 201, resp.text
        run_id = resp.json()["run_id"]
        print(f"[{time.time() - t0:.3f}s] run created: {run_id}")

        seqs: list[int] = []
        event_types: list[str] = []
        t_sub = time.time()
        terminal_seen = False
        async with client.stream(
            "GET", f"/api/runs/{run_id}/events?after=0"
        ) as r:
            print(
                f"[{time.time() - t0:.3f}s] SSE connected, "
                f"status={r.status_code}, "
                f"content-type={r.headers.get('content-type')}"
            )
            async for line in r.aiter_lines():
                if line.startswith("id:"):
                    seqs.append(int(line.split(":")[1].strip()))
                elif line.startswith("event:"):
                    event_types.append(line.split(":", 1)[1].strip())
                    if line in TERMINAL_EVENTS:
                        terminal_seen = True
                if terminal_seen:
                    # 给一帧时间让 data 行读完
                    break
                if time.time() - t_sub > 20:
                    print("[timeout] 20s 无 terminal 事件")
                    break

        t_elapsed = time.time() - t0
        await asyncio.sleep(0.5)
        snap = (await client.get(f"/api/runs/{run_id}")).json()
        latest = snap["latest_sequence"]
        status = snap["status"]

        print(f"\n=== 诊断结果 ===")
        print(f"SSE 收到 {len(seqs)} 个事件")
        print(f"first seq={seqs[0] if seqs else None}, last seq={seqs[-1] if seqs else None}")
        print(f"persist {latest} 个事件, run status={status}")
        missing = sorted(set(range(1, latest + 1)) - set(seqs))
        print(f"缺失 {len(missing)} 个: {missing[:30]}")
        print(f"收到的事件类型: {event_types[:10]} ... {event_types[-5:] if len(event_types) > 10 else ''}")
        print(f"总耗时 {t_elapsed:.3f}s")

        if len(seqs) == latest:
            print("\n结论: broker 未丢事件 -> 问题在前端（Bug 1 onClose 重置）")
        elif len(seqs) < latest:
            print(f"\n结论: broker 丢事件 {latest - len(seqs)} 个 -> 方案 C 对症")
        else:
            print(f"\n异常: 收到 > persist?!")


if __name__ == "__main__":
    asyncio.run(main())
