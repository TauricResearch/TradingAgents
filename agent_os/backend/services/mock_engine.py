"""MockEngine — streams scripted events for UI testing without real LLM calls.

Usage (via POST /api/run/mock):
  params = {
    "mock_type": "pipeline" | "scan" | "auto",
    "ticker":    "AAPL",          # used for pipeline / auto
    "tickers":   ["AAPL","NVDA"], # used for auto (overrides ticker list)
    "date":      "2026-03-24",
    "speed":     2.0,             # delay divisor — higher = faster
  }
"""

import asyncio
import time
from typing import AsyncGenerator, Dict, Any


class MockEngine:
    """Generates scripted AgentOS events without calling real LLMs."""

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def run_mock(
        self, run_id: str, params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        mock_type = params.get("mock_type", "pipeline")
        speed = max(float(params.get("speed", 1.0)), 0.1)

        if mock_type == "scan":
            async for evt in self._run_scan(run_id, params, speed):
                yield evt
        elif mock_type == "auto":
            async for evt in self._run_auto(run_id, params, speed):
                yield evt
        else:
            async for evt in self._run_pipeline(run_id, params, speed):
                yield evt

    # ------------------------------------------------------------------
    # Pipeline mock
    # ------------------------------------------------------------------

    async def _run_pipeline(
        self, run_id: str, params: Dict[str, Any], speed: float
    ) -> AsyncGenerator[Dict[str, Any], None]:
        ticker = params.get("ticker", "AAPL").upper()
        date = params.get("date", time.strftime("%Y-%m-%d"))

        yield self._log(f"[MOCK] Starting pipeline for {ticker} on {date}")
        await self._sleep(0.3, speed)

        # Analysts (sequential for simplicity in mock)
        analysts = [
            ("news_analyst",         "gpt-4o-mini", 1.4, 480, 310),
            ("market_analyst",       "gpt-4o-mini", 1.2, 390, 240),
            ("fundamentals_analyst", "gpt-4o",      2.1, 620, 430),
            ("social_analyst",       "gpt-4o-mini", 0.9, 310, 190),
        ]
        for node, model, latency, tok_in, tok_out in analysts:
            async for evt in self._agent_with_tool(
                run_id, node, ticker, model, latency, tok_in, tok_out, speed,
                tool_name=f"get_{node.split('_')[0]}_data",
            ):
                yield evt

        # Research debate
        for node, model, latency, tok_in, tok_out in [
            ("bull_researcher", "gpt-4o",      1.8, 540, 360),
            ("bear_researcher", "gpt-4o",      1.7, 510, 340),
            ("research_manager","gpt-4o",      2.3, 680, 480),
        ]:
            async for evt in self._agent_no_tool(
                run_id, node, ticker, model, latency, tok_in, tok_out, speed
            ):
                yield evt

        # Trading decision
        for node, model, latency, tok_in, tok_out in [
            ("trader",       "gpt-4o",  2.0, 600, 420),
            ("risk_manager", "gpt-4o",  1.5, 450, 310),
            ("risk_judge",   "gpt-4o",  1.1, 380, 260),
        ]:
            async for evt in self._agent_no_tool(
                run_id, node, ticker, model, latency, tok_in, tok_out, speed
            ):
                yield evt

        yield self._log(f"[MOCK] Pipeline for {ticker} completed.")

    # ------------------------------------------------------------------
    # Scan mock
    # ------------------------------------------------------------------

    async def _run_scan(
        self, run_id: str, params: Dict[str, Any], speed: float
    ) -> AsyncGenerator[Dict[str, Any], None]:
        date = params.get("date", time.strftime("%Y-%m-%d"))
        identifier = "MARKET"

        yield self._log(f"[MOCK] Starting market scan for {date}")
        await self._sleep(0.3, speed)

        # Phase 1 — three scanners in "parallel" (interleaved)
        yield self._log("[MOCK] Phase 1: Running geopolitical, market-movers, sector scanners…")
        phase1 = [
            ("geopolitical_scanner",  "gpt-4o-mini", 1.5, 420, 280),
            ("market_movers_scanner", "gpt-4o-mini", 1.3, 380, 250),
            ("sector_scanner",        "gpt-4o-mini", 1.4, 400, 265),
        ]
        # Emit thought events for all three before any complete
        for node, model, _, _, _ in phase1:
            yield self._thought(node, identifier, model, f"[MOCK] Scanning {node.replace('_', ' ')}…")
            await self._sleep(0.1, speed)

        # Then complete them in order
        for node, model, latency, tok_in, tok_out in phase1:
            await self._sleep(latency, speed)
            yield self._result(node, identifier, model, tok_in, tok_out, round(latency * 1000),
                               f"[MOCK] {node.replace('_', ' ').title()} report ready.")

        # Phase 2 — industry deep dive
        yield self._log("[MOCK] Phase 2: Industry deep dive…")
        async for evt in self._agent_no_tool(
            run_id, "industry_deep_dive", identifier, "gpt-4o", 2.2, 680, 460, speed
        ):
            yield evt

        # Phase 3 — macro synthesis
        yield self._log("[MOCK] Phase 3: Macro synthesis + watchlist generation…")
        async for evt in self._agent_no_tool(
            run_id, "macro_synthesis", identifier, "gpt-4o", 2.8, 820, 590, speed
        ):
            yield evt

        yield self._log("[MOCK] Scan completed. Top-10 watchlist generated.")

    # ------------------------------------------------------------------
    # Auto mock (scan → pipeline per ticker → portfolio)
    # ------------------------------------------------------------------

    async def _run_auto(
        self, run_id: str, params: Dict[str, Any], speed: float
    ) -> AsyncGenerator[Dict[str, Any], None]:
        tickers = params.get("tickers") or [params.get("ticker", "AAPL").upper()]

        yield self._log(f"[MOCK] Starting auto run — scan + {len(tickers)} pipeline(s) + portfolio")
        await self._sleep(0.2, speed)

        # Phase 1: Scan
        yield self._log("[MOCK] Phase 1/3: Market scan…")
        async for evt in self._run_scan(run_id, params, speed):
            yield evt

        # Phase 2: Per-ticker pipeline
        for ticker in tickers:
            yield self._log(f"[MOCK] Phase 2/3: Pipeline for {ticker}…")
            async for evt in self._run_pipeline(run_id, {**params, "ticker": ticker}, speed):
                yield evt

        # Phase 3: Portfolio
        yield self._log("[MOCK] Phase 3/3: Portfolio manager…")
        async for evt in self._agent_no_tool(
            run_id, "portfolio_manager", "PORTFOLIO", "gpt-4o", 2.5, 740, 520, speed
        ):
            yield evt

        yield self._log("[MOCK] Auto run completed.")

    # ------------------------------------------------------------------
    # Building blocks
    # ------------------------------------------------------------------

    async def _agent_with_tool(
        self,
        run_id: str,
        node: str,
        identifier: str,
        model: str,
        latency: float,
        tok_in: int,
        tok_out: int,
        speed: float,
        tool_name: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        yield self._thought(node, identifier, model, f"[MOCK] {node} analysing {identifier}…")
        await self._sleep(0.4, speed)

        yield self._tool_call(node, identifier, tool_name, f'{{"ticker": "{identifier}"}}')
        await self._sleep(0.6, speed)

        yield self._tool_result(node, identifier, tool_name,
                                f"[MOCK] Retrieved {tool_name} data for {identifier}.")
        await self._sleep(latency - 1.0, speed)

        yield self._result(node, identifier, model, tok_in, tok_out, round(latency * 1000),
                           f"[MOCK] {node.replace('_', ' ').title()} analysis complete for {identifier}.")

    async def _agent_no_tool(
        self,
        run_id: str,
        node: str,
        identifier: str,
        model: str,
        latency: float,
        tok_in: int,
        tok_out: int,
        speed: float,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        yield self._thought(node, identifier, model, f"[MOCK] {node} processing {identifier}…")
        await self._sleep(latency, speed)

        yield self._result(node, identifier, model, tok_in, tok_out, round(latency * 1000),
                           f"[MOCK] {node.replace('_', ' ').title()} decision for {identifier}.")

    # ------------------------------------------------------------------
    # Event constructors
    # ------------------------------------------------------------------

    @staticmethod
    def _ns() -> str:
        return str(time.time_ns())

    def _log(self, message: str) -> Dict[str, Any]:
        return {
            "id": f"log_{self._ns()}",
            "node_id": "__system__",
            "type": "log",
            "agent": "SYSTEM",
            "identifier": "",
            "message": message,
            "metrics": {},
        }

    def _thought(self, node: str, identifier: str, model: str, message: str) -> Dict[str, Any]:
        return {
            "id": f"thought_{self._ns()}",
            "node_id": node,
            "parent_node_id": "start",
            "type": "thought",
            "agent": node.upper(),
            "identifier": identifier,
            "message": message,
            "prompt": f"[MOCK PROMPT] Analyse {identifier} using available data.",
            "metrics": {"model": model},
        }

    def _tool_call(self, node: str, identifier: str, tool: str, inp: str) -> Dict[str, Any]:
        return {
            "id": f"tool_{self._ns()}",
            "node_id": f"tool_{tool}",
            "parent_node_id": node,
            "type": "tool",
            "agent": node.upper(),
            "identifier": identifier,
            "message": f"▶ Tool: {tool} | {inp}",
            "prompt": inp,
            "metrics": {},
        }

    def _tool_result(self, node: str, identifier: str, tool: str, output: str) -> Dict[str, Any]:
        return {
            "id": f"tool_res_{self._ns()}",
            "node_id": f"tool_{tool}",
            "parent_node_id": node,
            "type": "tool_result",
            "agent": node.upper(),
            "identifier": identifier,
            "message": f"✓ Tool result: {tool} | {output}",
            "response": output,
            "metrics": {},
        }

    def _result(
        self,
        node: str,
        identifier: str,
        model: str,
        tok_in: int,
        tok_out: int,
        latency_ms: int,
        message: str,
    ) -> Dict[str, Any]:
        return {
            "id": f"result_{self._ns()}",
            "node_id": node,
            "type": "result",
            "agent": node.upper(),
            "identifier": identifier,
            "message": message,
            "response": f"[MOCK RESPONSE] {message}",
            "metrics": {
                "model": model,
                "tokens_in": tok_in,
                "tokens_out": tok_out,
                "latency_ms": latency_ms,
            },
        }

    @staticmethod
    async def _sleep(seconds: float, speed: float) -> None:
        delay = max(seconds / speed, 0.01)
        await asyncio.sleep(delay)
