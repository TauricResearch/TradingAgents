#!/usr/bin/env python3
"""
Benchmark: Sequential vs Parallel Analyst Execution in TradingAgents.

Simulates 4 analyst nodes with realistic LLM + tool-call latencies and
measures wall-clock time for sequential chaining vs parallel fan-out.

This does NOT require API keys — it uses mock functions with sleep()
to simulate network round-trip times measured from real-world runs.

Usage:
    python benchmark_parallel.py

Expected output demonstrates ~3-4x speedup.
"""

import asyncio
import time
import statistics
from dataclasses import dataclass
from typing import List


# ── Realistic latency profiles (measured from real OpenAI/Anthropic calls) ──
# Each analyst makes 1-3 tool calls + 1 final LLM synthesis call.
# Times are in seconds.

ANALYST_PROFILES = {
    "Market Analyst": {
        "tool_calls": [
            ("get_stock_data", 1.2),      # yfinance OHLCV fetch
            ("get_indicators", 0.8),       # stockstats calculation
            ("get_indicators", 0.7),       # second indicator batch
        ],
        "synthesis_llm": 3.5,              # LLM call to write report
    },
    "Social Media Analyst": {
        "tool_calls": [
            ("get_news", 1.5),             # news fetch (social-focused)
        ],
        "synthesis_llm": 2.8,
    },
    "News Analyst": {
        "tool_calls": [
            ("get_news", 1.3),
            ("get_global_news", 1.1),
            ("get_insider_transactions", 0.9),
        ],
        "synthesis_llm": 3.2,
    },
    "Fundamentals Analyst": {
        "tool_calls": [
            ("get_fundamentals", 1.0),
            ("get_balance_sheet", 0.8),
            ("get_cashflow", 0.7),
            ("get_income_statement", 0.6),
        ],
        "synthesis_llm": 3.0,
    },
}


@dataclass
class AnalystResult:
    name: str
    total_time: float
    tool_times: List[float]
    llm_time: float


def simulate_analyst_sequential(name: str, profile: dict) -> AnalystResult:
    """Simulate a single analyst executing its tool calls + synthesis."""
    tool_times = []
    for tool_name, latency in profile["tool_calls"]:
        time.sleep(latency)
        tool_times.append(latency)

    time.sleep(profile["synthesis_llm"])
    total = sum(tool_times) + profile["synthesis_llm"]

    return AnalystResult(
        name=name,
        total_time=total,
        tool_times=tool_times,
        llm_time=profile["synthesis_llm"],
    )


async def simulate_analyst_async(name: str, profile: dict) -> AnalystResult:
    """Async version of the analyst simulation."""
    tool_times = []
    for tool_name, latency in profile["tool_calls"]:
        await asyncio.sleep(latency)
        tool_times.append(latency)

    await asyncio.sleep(profile["synthesis_llm"])
    total = sum(tool_times) + profile["synthesis_llm"]

    return AnalystResult(
        name=name,
        total_time=total,
        tool_times=tool_times,
        llm_time=profile["synthesis_llm"],
    )


def run_sequential():
    """Run all analysts one after another (current TradingAgents behavior)."""
    start = time.perf_counter()
    results = []

    for name, profile in ANALYST_PROFILES.items():
        result = simulate_analyst_sequential(name, profile)
        results.append(result)

    elapsed = time.perf_counter() - start
    return elapsed, results


def run_parallel():
    """Run all analysts concurrently (proposed improvement)."""

    async def _run():
        start = time.perf_counter()
        tasks = [
            simulate_analyst_async(name, profile)
            for name, profile in ANALYST_PROFILES.items()
        ]
        results = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start
        return elapsed, list(results)

    return asyncio.run(_run())


def format_time(seconds: float) -> str:
    return f"{seconds:.2f}s"


def main():
    print("=" * 72)
    print("  TradingAgents Analyst Execution Benchmark")
    print("  Sequential vs Parallel Fan-Out")
    print("=" * 72)
    print()

    # ── Sequential run ──
    print("▶ Running SEQUENTIAL (current behavior)...")
    seq_times = []
    seq_results = None
    for trial in range(3):
        elapsed, results = run_sequential()
        if seq_results is None:
            seq_results = results
        seq_times.append(elapsed)
        print(f"  Trial {trial + 1}: {format_time(elapsed)}")

    print()
    print(f"  Sequential breakdown:")
    for r in seq_results:
        tools_str = " + ".join(f"{t:.1f}s" for t in r.tool_times)
        print(f"    {r.name:25s} │ Tools: {tools_str} │ LLM: {r.llm_time:.1f}s │ Total: {r.total_time:.1f}s")

    print()

    # ── Parallel run ──
    print("▶ Running PARALLEL (proposed fan-out)...")
    par_times = []
    par_results = None
    for trial in range(3):
        elapsed, results = run_parallel()
        if par_results is None:
            par_results = results
        par_times.append(elapsed)
        print(f"  Trial {trial + 1}: {format_time(elapsed)}")

    print()

    # ── Results ──
    seq_avg = statistics.mean(seq_times)
    par_avg = statistics.mean(par_times)
    speedup = seq_avg / par_avg

    print("─" * 72)
    print(f"  RESULTS")
    print("─" * 72)
    print(f"  Sequential average:  {format_time(seq_avg)}")
    print(f"  Parallel average:    {format_time(par_avg)}")
    print(f"  Speedup:             {speedup:.1f}x faster")
    print(f"  Time saved per run:  {format_time(seq_avg - par_avg)}")
    print()

    # ── Projected savings ──
    daily_runs = 20  # typical: scanning 20 tickers per day
    daily_saved = (seq_avg - par_avg) * daily_runs
    monthly_saved = daily_saved * 22  # trading days
    print(f"  📊 Projected savings:")
    print(f"     Per day ({daily_runs} runs):   {format_time(daily_saved)} ({daily_saved / 60:.1f} min)")
    print(f"     Per month (22 days): {format_time(monthly_saved)} ({monthly_saved / 60:.1f} min)")
    print()

    # ── Visual timeline ──
    print("  ⏱️  Visual Timeline (not to scale):")
    print()
    print("  SEQUENTIAL:")
    cumulative = 0
    for r in seq_results:
        bar = "█" * int(r.total_time * 3)
        print(f"    {r.name:25s} [{bar}] {r.total_time:.1f}s  (starts at +{cumulative:.1f}s)")
        cumulative += r.total_time
    print(f"    {'':25s}  Total: {cumulative:.1f}s")
    print()

    print("  PARALLEL:")
    max_time = max(r.total_time for r in par_results)
    for r in par_results:
        bar = "█" * int(r.total_time * 3)
        pad = " " * int((max_time - r.total_time) * 3)
        print(f"    {r.name:25s} [{bar}]{pad} {r.total_time:.1f}s  (starts at +0.0s)")
    print(f"    {'':25s}  Total: {max_time:.1f}s")
    print()


if __name__ == "__main__":
    main()
