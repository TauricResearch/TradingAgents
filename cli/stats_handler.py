from typing import Any

from tradingagents.usage import UsageTrackingCallback


class StatsCallbackHandler(UsageTrackingCallback):
    """CLI live-display handler: the shared usage tracker plus a get_stats() shim.

    Token/call tracking lives in tradingagents.usage.UsageTrackingCallback (the
    single source of truth used by both the CLI and the Python API); this
    subclass only preserves the dict shape the CLI status panel expects.
    """

    def get_stats(self) -> dict[str, Any]:
        """Return current statistics in the CLI's expected shape."""
        s = self.summary()
        return {
            "llm_calls": s["llm_calls"],
            "tool_calls": s["tool_calls"],
            "tokens_in": s["tokens_in"],
            "tokens_out": s["tokens_out"],
        }
