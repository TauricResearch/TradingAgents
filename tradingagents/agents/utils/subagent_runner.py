from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any


def _invoke_dimension(llm, dimension: str, prompt: str) -> dict[str, Any]:
    started_at = time.monotonic()
    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return {
            "dimension": dimension,
            "content": str(content).strip(),
            "ok": True,
            "error": None,
            "elapsed_s": round(time.monotonic() - started_at, 3),
        }
    except Exception as exc:
        return {
            "dimension": dimension,
            "content": "",
            "ok": False,
            "error": str(exc),
            "elapsed_s": round(time.monotonic() - started_at, 3),
        }


def run_parallel_subagents(
    *,
    llm,
    dimension_configs: list[dict[str, Any]],
    timeout_per_subagent: float = 25.0,
    max_workers: int = 4,
) -> list[dict[str, Any]]:
    if not dimension_configs:
        return []

    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = {
        executor.submit(
            _invoke_dimension,
            llm,
            config["dimension"],
            config["prompt"],
        ): config["dimension"]
        for config in dimension_configs
    }

    results: list[dict[str, Any]] = []
    try:
        for future, dimension in futures.items():
            try:
                results.append(future.result(timeout=timeout_per_subagent))
            except TimeoutError:
                results.append(
                    {
                        "dimension": dimension,
                        "content": "",
                        "ok": False,
                        "error": "timeout",
                        "elapsed_s": round(timeout_per_subagent, 3),
                    }
                )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return results


def synthesize_subagent_results(
    subagent_results: list[dict[str, Any]],
    *,
    max_chars_per_result: int = 200,
) -> tuple[str, dict[str, Any]]:
    lines: list[str] = []
    timings: dict[str, float] = {}
    failures: dict[str, str] = {}

    for result in subagent_results:
        dimension = str(result.get("dimension") or "unknown")
        timings[dimension] = float(result.get("elapsed_s") or 0.0)

        content = str(result.get("content") or "").strip()
        if not result.get("ok"):
            failure_reason = str(result.get("error") or "unknown error")
            failures[dimension] = failure_reason
            content = f"[UNAVAILABLE: {failure_reason}]"

        if len(content) > max_chars_per_result:
            content = f"{content[:max_chars_per_result - 3]}..."

        lines.append(f"[{dimension.upper()}]\n{content or '[NO OUTPUT]'}")

    return "\n\n".join(lines), {
        "subagent_timings": timings,
        "failures": failures,
    }
