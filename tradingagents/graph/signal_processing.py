# TradingAgents/graph/signal_processing.py


from langchain_core.language_models.chat_models import BaseChatModel


class SignalProcessor:
    """Processes trading signals to extract actionable decisions."""

    def __init__(self, quick_thinking_llm: BaseChatModel, config):
        """Initialize with an LLM for processing."""
        language = config["output_language"]
        language_prompts = {
            "en": "",
            "zh-tw": "Use Traditional Chinese as the output.",
            "zh-cn": "Use Simplified Chinese as the output.",
        }
        self.language_prompt = language_prompts.get(language, "")

        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> str:
        """
        Process a full trading signal to extract the core decision.

        Args:
            full_signal: Complete trading signal text

        Returns:
            Extracted decision (BUY, SELL, or HOLD)
        """
        messages = [
            (
                "system",
                f"""
You are an efficient assistant designed to analyze paragraphs or financial reports provided by a group of analysts. 
Your task is to extract the investment decision: SELL, BUY, or HOLD.
Provide only the extracted decision (SELL, BUY, or HOLD) as your output, without adding any additional text or information.

Output language: ***{self.language_prompt}***
                """,
            ),
            ("human", full_signal),
        ]

        return self.quick_thinking_llm.invoke(messages).content
