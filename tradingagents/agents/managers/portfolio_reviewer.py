"""Portfolio Reviewer: judges the whole book from its risk metrics and per-ticker decisions.

Runs after the graph, not inside it. Each holding has already been through the
full pipeline on its own; this agent sees what none of them could: how the
positions sit together. It takes the computed portfolio metrics and the
per-ticker ratings and returns a typed ``PortfolioAssessment``, falling back to
free text when the provider has no structured output.
"""

from __future__ import annotations

from tradingagents.agents.context import get_language_instruction
from tradingagents.agents.schemas import PortfolioAssessment, render_portfolio_assessment
from tradingagents.agents.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)


def create_portfolio_reviewer(llm):
    structured_llm = bind_structured(llm, PortfolioAssessment, "Portfolio Reviewer")

    def review(metrics_report: str, decisions_report: str) -> str:
        prompt = f"""As the Portfolio Reviewer, assess the portfolio as a whole and recommend what to do with each holding.

Each holding was analyzed on its own by the full research, trading and risk pipeline. Those single-ticker views could not see how the positions interact. Your job is the book: concentration, correlation, sector tilt, volatility and drawdown, cash, and whether the single-ticker calls add up to a coherent portfolio.

## Portfolio metrics

{metrics_report}

## Single-ticker decisions

{decisions_report}

---

Ground every point in the numbers above. A Buy on a position that is already the largest weight, or highly correlated with another large one, may still warrant Hold or Trim at the portfolio level; say so when it does. A holding marked as not analyzed has no single-ticker view, so judge it on the metrics alone and say that you did. Metrics are historical and computed over the stated lookback; do not present them as forecasts. Options are counted at their delta-equivalent exposure to the underlying: judge the leverage they add, the premium at risk, time decay and time to expiry, and give each option contract its own recommendation alongside the shares. Recommend no change when the book is already sound.

{NO_EXTERNAL_TOOLS}{get_language_instruction()}"""

        return invoke_structured_or_freetext(
            structured_llm, llm, prompt, render_portfolio_assessment, "Portfolio Reviewer",
        )

    return review
