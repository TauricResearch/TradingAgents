"""Screening pipeline graph for swing trading stock discovery.

A simpler LangGraph StateGraph that scans the market universe
and produces ranked candidate stocks for deep analysis.
"""

import logging
from typing import Annotated

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from tradingagents.agents.screener.candidate_ranker import create_candidate_ranker
from tradingagents.agents.screener.fundamental_screener import fundamental_screen
from tradingagents.agents.screener.technical_screener import technical_screen
from tradingagents.agents.screener.universe_builder import build_universe

logger = logging.getLogger(__name__)


class ScreeningState(TypedDict):
    market: Annotated[str, "Target market: KRX or US"]
    trade_date: Annotated[str, "Current trading date YYYY-MM-DD"]
    existing_positions: Annotated[list[str], "Tickers already held"]
    portfolio_context: Annotated[str, "Portfolio summary for ranking context"]
    max_candidates: Annotated[int, "Maximum candidates to output"]
    # Outputs
    universe_size: Annotated[int, "Number of stocks in universe"]
    technical_candidates: Annotated[list[dict], "Stocks passing technical screen"]
    fundamental_candidates: Annotated[list[dict], "Stocks passing fundamental screen"]
    final_candidates: Annotated[list[dict], "Ranked final candidates"]
    screening_report: Annotated[str, "Human-readable screening report"]


class ScreeningGraph:
    """Screening pipeline for swing trading stock discovery."""

    def __init__(self, config: dict):
        self.config = config
        self._build_graph()

    def _build_graph(self):
        """Build the screening pipeline graph."""
        graph = StateGraph(ScreeningState)

        graph.add_node("build_universe", self._build_universe_node)
        graph.add_node("technical_screen", self._technical_screen_node)
        graph.add_node("fundamental_screen", self._fundamental_screen_node)
        graph.add_node("rank_candidates", self._rank_candidates_node)
        graph.add_node("generate_report", self._generate_report_node)

        graph.add_edge(START, "build_universe")
        graph.add_edge("build_universe", "technical_screen")
        graph.add_edge("technical_screen", "fundamental_screen")
        graph.add_edge("fundamental_screen", "rank_candidates")
        graph.add_edge("rank_candidates", "generate_report")
        graph.add_edge("generate_report", END)

        self.graph = graph.compile()

    def run(
        self,
        trade_date: str,
        market: str = "KRX",
        existing_positions: list[str] | None = None,
        portfolio_context: str = "",
        max_candidates: int = 5,
    ) -> dict:
        """Run the screening pipeline.

        Returns:
            Dict with final_candidates and screening_report
        """
        initial_state: ScreeningState = {
            "market": market,
            "trade_date": trade_date,
            "existing_positions": existing_positions or [],
            "portfolio_context": portfolio_context,
            "max_candidates": max_candidates,
            "universe_size": 0,
            "technical_candidates": [],
            "fundamental_candidates": [],
            "final_candidates": [],
            "screening_report": "",
        }

        result = self.graph.invoke(initial_state)
        return {
            "candidates": result["final_candidates"],
            "report": result["screening_report"],
            "stats": {
                "universe_size": result["universe_size"],
                "technical_passed": len(result["technical_candidates"]),
                "fundamental_passed": len(result["fundamental_candidates"]),
                "final_selected": len(result["final_candidates"]),
            },
        }

    def _build_universe_node(self, state: ScreeningState) -> dict:
        """Build stock universe."""
        universe = build_universe(self.config)
        return {"universe_size": len(universe), "_universe_df": universe}

    def _technical_screen_node(self, state: ScreeningState) -> dict:
        """Run technical screening."""
        # Rebuild universe (state doesn't carry DataFrames well)
        universe = build_universe(self.config)

        candidates = technical_screen(
            universe=universe,
            trade_date=state["trade_date"],
            market=state["market"],
            existing_positions=state["existing_positions"],
        )
        return {"technical_candidates": candidates}

    def _fundamental_screen_node(self, state: ScreeningState) -> dict:
        """Run fundamental screening on technical candidates."""
        candidates = fundamental_screen(
            technical_candidates=state["technical_candidates"],
            trade_date=state["trade_date"],
            market=state["market"],
        )
        return {"fundamental_candidates": candidates}

    def _rank_candidates_node(self, state: ScreeningState) -> dict:
        """Rank candidates using LLM."""
        from tradingagents.llm_clients import create_llm_client

        client = create_llm_client(
            provider=self.config.get("llm_provider", "openai"),
            model=self.config.get("quick_think_llm", "gpt-5-mini"),
            base_url=self.config.get("backend_url"),
        )
        llm = client.get_llm()
        ranker = create_candidate_ranker(llm)

        ranked = ranker(
            candidates=state["fundamental_candidates"],
            portfolio_context=state["portfolio_context"],
            max_candidates=state["max_candidates"],
        )
        return {"final_candidates": ranked}

    def _generate_report_node(self, state: ScreeningState) -> dict:
        """Generate human-readable screening report."""
        lines = [
            "=" * 60,
            f"스윙 트레이딩 스크리닝 리포트",
            f"날짜: {state['trade_date']} / 시장: {state['market']}",
            "=" * 60,
            "",
            f"유니버스 크기: {state['universe_size']}개",
            f"기술적 통과: {len(state['technical_candidates'])}개",
            f"펀더멘탈 통과: {len(state['fundamental_candidates'])}개",
            f"최종 선정: {len(state['final_candidates'])}개",
            "",
            "-" * 60,
            "최종 후보 종목",
            "-" * 60,
        ]

        for i, c in enumerate(state["final_candidates"], 1):
            lines.append(f"\n[{i}] {c['ticker']} - {c['name']}")
            lines.append(f"    기술적 신호: {', '.join(c['signals'])}")
            lines.append(f"    펀더멘탈: {c.get('fundamental_check', 'N/A')}")

            ind = c.get("indicators", {})
            if ind:
                price = ind.get("current_price", "N/A")
                rsi = ind.get("rsi")
                vol_ratio = ind.get("volume_ratio")
                rsi_str = f"{rsi:.1f}" if isinstance(rsi, float) else "N/A"
                vol_str = f"{vol_ratio:.1f}x" if isinstance(vol_ratio, float) else "N/A"
                lines.append(f"    현재가: {price} / RSI: {rsi_str} / 거래량: {vol_str}")

            if "ranking_reason" in c:
                lines.append(f"    선정 이유: {c['ranking_reason']}")

        if not state["final_candidates"]:
            lines.append("\n  스크리닝 조건을 충족하는 종목이 없습니다.")

        lines.append("\n" + "=" * 60)

        report = "\n".join(lines)
        return {"screening_report": report}
