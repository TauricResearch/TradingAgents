import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr


def load_scenario_file(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_dir() -> Path:
    return Path(__file__).parent / "scenarios"


class ScenarioLLMClient:
    def __init__(self, llm: BaseChatModel):
        self._llm = llm

    def get_llm(self):
        return self._llm


class ScenarioChatModel(BaseChatModel):
    _scenario: Dict[str, Any] = PrivateAttr()
    _seen: List[str] = PrivateAttr(default_factory=list)

    def __init__(self, scenario: Dict[str, Any]):
        super().__init__()
        self._scenario = scenario
        self._seen = []

    @property
    def scenario(self) -> Dict[str, Any]:
        return self._scenario

    @property
    def seen(self) -> List[str]:
        return self._seen

    @property
    def _llm_type(self) -> str:
        return "scenario-chat-model"

    def with_structured_output(self, *args, **kwargs):
        raise NotImplementedError("structured output disabled for scenario model")

    def bind_tools(self, *args, **kwargs):
        return self

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        text = "\n".join(m.content for m in messages if getattr(m, "content", None))
        self._seen.append(text)
        content = self._reply(text)
        msg = AIMessage(content=content)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _reply(self, text: str) -> str:
        expected = (self._scenario.get("expected") or {}).get("rating", "Hold")
        ticker = self._scenario.get("ticker", "TICKER")
        market = self._scenario.get("market") or {}
        indicators = self._scenario.get("indicators") or {}
        news = self._scenario.get("news") or []
        fundamentals = self._scenario.get("fundamentals") or {}
        social = self._scenario.get("social") or {}

        def _news_lines(limit: int = 3) -> str:
            if not news:
                return "No notable headlines."
            out = []
            for item in news[:limit]:
                title = item.get("title", "").strip() or "Untitled"
                sentiment = item.get("sentiment", "unknown")
                out.append(f"- {title} ({sentiment})")
            return "\n".join(out)

        if "You are a Bull Analyst" in text:
            rsi = indicators.get("rsi_14")
            rsi_txt = f"RSI ~{rsi} (overbought risk acknowledged)." if rsi is not None else "RSI unavailable."
            trend = market.get("trend", "trend unclear")
            return (
                f"Trend is {trend} with strong price action. {rsi_txt} "
                f"Negative headlines are noted but may be transient; focus on momentum + positioning."
            )

        if "You are a Bear Analyst" in text:
            rsi = indicators.get("rsi_14")
            rsi_txt = f"RSI ~{rsi} signals overbought / mean-reversion risk." if rsi is not None else "RSI missing increases uncertainty."
            return (
                f"Price strength can be a bull trap. {rsi_txt} "
                f"Headline risk is elevated:\n{_news_lines()}\n"
                f"Risk/reward skews negative until uncertainty clears."
            )

        if "As the Research Manager" in text:
            return (
                f"**Recommendation**: {expected}\n\n"
                f"**Rationale**: Summary based on debate; conflicting signals handled explicitly.\n\n"
                f"**Strategic Actions**: Wait for confirmation; manage risk tightly."
            )

        if "You are a trading agent analyzing market data" in text or "Proposed Investment Plan" in text:
            action = "HOLD"
            if expected in ("Buy", "Overweight"):
                action = "BUY"
            elif expected in ("Underweight", "Sell"):
                action = "SELL"
            return f"**Action**: {action}\n\nReasoning: Execute per plan.\n\nFINAL TRANSACTION PROPOSAL: **{action}**"

        if "As the Aggressive Risk Analyst" in text:
            return "Push for participation but size small; momentum can pay even with noise."
        if "As the Conservative Risk Analyst" in text:
            return "Protect capital first; headline risk and extremes justify staying defensive."
        if "As the Neutral Risk Analyst" in text:
            return "Balance both sides; prefer HOLD unless edge is clear."

        if "Market Research Report" in text and "Market Analyst" in text:
            trend = market.get("trend", "unknown")
            change = market.get("price_change_pct_7d")
            rsi = indicators.get("rsi_14")
            return (
                f"Market report for {ticker}: trend={trend}, 7d_change={change}%. "
                f"RSI_14={rsi}. Key takeaway: momentum vs mean-reversion risk."
            )

        if "News Analyst" in text:
            return f"News report for {ticker}:\n{_news_lines(5)}"

        if "Social Media" in text:
            sent = social.get("sentiment", "neutral")
            return f"Social sentiment for {ticker}: {sent}."

        if "fundamental information" in text or "Fundamentals Analyst" in text:
            summary = fundamentals.get("summary", "No fundamentals summary provided.")
            return f"Fundamentals report for {ticker}: {summary}"

        if "As the Portfolio Manager" in text:
            return (
                f"**Rating**: {expected}\n\n"
                f"**Executive Summary**: Decision reflects scenario risk profile.\n\n"
                f"**Evidence**: Market={market.get('trend')}; RSI={indicators.get('rsi_14')}; headlines considered."
            )

        return f"{ticker}: {expected}"
