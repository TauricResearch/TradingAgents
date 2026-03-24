# TradingAgents/graph/portfolio_analysis.py

import json
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from langchain_core.language_models.chat_models import BaseChatModel


class PortfolioAnalyzer:
    """Analyzes multiple stocks and produces a comparative portfolio recommendation.

    Follows the same delegation pattern as SignalProcessor and Reflector —
    the orchestrator (TradingAgentsGraph) owns the graph and LLMs, this class
    owns the portfolio-level prompt, comparison logic, and logging.
    """

    def __init__(self, deep_thinking_llm: BaseChatModel):
        """Initialize with the deep thinking LLM for comparative analysis.

        Args:
            deep_thinking_llm: The LLM instance used for the portfolio summary.
        """
        self.deep_thinking_llm = deep_thinking_llm

    def analyze(
        self,
        tickers: List[str],
        trade_date: str,
        propagate_fn: Callable[[str, str], Tuple[Dict[str, Any], str]],
        debug: bool = False,
    ) -> Dict[str, Any]:
        """Run analysis on multiple stocks and produce a comparative summary.

        Args:
            tickers: List of ticker symbols to analyze.
            trade_date: The trade date string (e.g., "2026-03-23").
            propagate_fn: The single-stock propagation function (typically
                TradingAgentsGraph.propagate).
            debug: Whether to print progress output.

        Returns:
            Dictionary with:
                - "individual_results": dict mapping ticker to its decision and signal
                - "portfolio_summary": the comparative LLM analysis

        Raises:
            ValueError: If tickers is empty.
        """
        if not tickers:
            raise ValueError("tickers must be a non-empty list")

        individual_results = self._analyze_individual(
            tickers, trade_date, propagate_fn, debug
        )

        portfolio_summary = self._generate_summary(
            individual_results, trade_date
        )

        self._log_portfolio(trade_date, tickers, individual_results, portfolio_summary)

        return {
            "individual_results": individual_results,
            "portfolio_summary": portfolio_summary,
        }

    def _analyze_individual(
        self,
        tickers: List[str],
        trade_date: str,
        propagate_fn: Callable,
        debug: bool,
    ) -> Dict[str, Dict[str, str]]:
        """Run the agent pipeline on each ticker, collecting results."""
        individual_results = {}

        for ticker in tickers:
            if debug:
                print(f"\n{'='*60}")
                print(f"Analyzing {ticker}...")
                print(f"{'='*60}\n")

            try:
                final_state, signal = propagate_fn(ticker, trade_date)
                individual_results[ticker] = {
                    "signal": signal,
                    "final_trade_decision": final_state["final_trade_decision"],
                }
            except Exception as e:
                if debug:
                    print(f"Error analyzing {ticker}: {e}")
                individual_results[ticker] = {
                    "signal": "ERROR",
                    "final_trade_decision": f"Analysis failed: {e}\n{traceback.format_exc()}",
                }

        return individual_results

    def _generate_summary(
        self,
        individual_results: Dict[str, Dict[str, str]],
        trade_date: str,
    ) -> str:
        """Use the deep thinking LLM to compare all positions."""
        # Skip summary if all tickers failed
        successful = {
            t: r for t, r in individual_results.items() if r["signal"] != "ERROR"
        }
        if not successful:
            return "Portfolio summary unavailable — all individual analyses failed."

        analyses_text = self._build_analyses_text(successful)
        messages = [
            ("system", self._get_system_prompt()),
            (
                "human",
                f"Here are the individual analyses for my portfolio positions "
                f"as of {trade_date}:\n{analyses_text}\n\n"
                f"Please provide a comparative portfolio recommendation.",
            ),
        ]

        try:
            return self.deep_thinking_llm.invoke(messages).content
        except Exception as e:
            import traceback
            return (
                f"Portfolio summary generation failed: {e}\n{traceback.format_exc()}\n"
                f"Individual signals were: "
                + ", ".join(f"{t}: {r['signal']}" for t, r in individual_results.items())
            )

    def _build_analyses_text(self, results: Dict[str, Dict[str, str]]) -> str:
        """Format individual results into a text block for the LLM prompt."""
        parts = []
        for ticker, result in results.items():
            parts.append(
                f"--- {ticker} ---\n"
                f"Rating: {result['signal']}\n"
                f"Full Analysis:\n{result['final_trade_decision']}"
            )
        return "\n".join(parts)

    def _get_system_prompt(self) -> str:
        """Return the system prompt for the portfolio comparison LLM call."""
        return (
            "You are a senior portfolio strategist. You have received individual "
            "stock analyses for all positions in a portfolio. Your job is to compare "
            "them relative to each other and provide a clear, actionable portfolio "
            "recommendation.\n\n"
            "For each stock, assign one of: KEEP, REDUCE, or EXIT.\n\n"
            "Structure your response as:\n"
            "1. A ranked summary table (best to worst) with ticker, action, and "
            "one-line rationale.\n"
            "2. A brief portfolio-level commentary covering overall risk exposure, "
            "sector concentration, and any suggested rebalancing.\n\n"
            "Be direct and concise. This is for an experienced investor."
        )

    def _log_portfolio(
        self,
        trade_date: str,
        tickers: List[str],
        individual_results: Dict[str, Dict[str, str]],
        portfolio_summary: str,
    ) -> None:
        """Log the portfolio analysis results to a JSON file."""
        directory = Path("eval_results/portfolio/")
        directory.mkdir(parents=True, exist_ok=True)

        log_data = {
            "trade_date": str(trade_date),
            "tickers": tickers,
            "individual_results": individual_results,
            "portfolio_summary": portfolio_summary,
        }

        log_file = directory / f"portfolio_analysis_{trade_date}.json"
        with log_file.open("w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=4)
