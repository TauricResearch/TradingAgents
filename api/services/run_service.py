import logging
from collections import defaultdict
from typing import Generator
from api.store.runs_store import RunsStore
from api.models.run import RunConfig, RunStatus
from api.callbacks.token_handler import TokenCallbackHandler

logger = logging.getLogger(__name__)

try:
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG
except ImportError:
    TradingAgentsGraph = None  # type: ignore
    DEFAULT_CONFIG = {}


class RunService:
    def __init__(self, store: RunsStore):
        self._store = store

    def stream_events(self, run_id: str) -> Generator[dict, None, None]:
        run = self._store.get(run_id)
        if not run or not run.config:
            yield {"event": "run:error", "data": {"message": "Run not found"}}
            return

        if run.status == RunStatus.COMPLETE:
            token_usage = {k: v.model_dump() for k, v in (run.token_usage or {}).items()}
            for key, report in run.reports.items():
                if ":" not in key:
                    logger.warning(
                        "Skipping malformed report key %r for run %s", key, run_id
                    )
                    continue
                step_key, turn_str = key.rsplit(":", 1)
                if not turn_str.isdigit():
                    logger.warning(
                        "Skipping report key with non-numeric turn %r for run %s", key, run_id
                    )
                    continue
                turn = int(turn_str)
                raw = token_usage.get(key, {"tokens_in": 0, "tokens_out": 0})
                yield {"event": "agent:start",    "data": {"step": step_key, "turn": turn}}
                yield {"event": "agent:complete", "data": {
                    "step": step_key, "turn": turn, "report": report,
                    "tokens_in": raw.get("tokens_in", 0),
                    "tokens_out": raw.get("tokens_out", 0),
                }}
            yield {"event": "run:complete", "data": {"decision": run.decision or "HOLD", "run_id": run_id}}
            return

        if run.status == RunStatus.RUNNING:
            yield {"event": "run:error", "data": {"message": "Run is already in progress"}}
            return

        self._store.clear_reports(run_id)
        self._store.clear_token_usage(run_id)
        self._store.update_status(run_id, RunStatus.RUNNING)
        config = run.config

        ta_config = DEFAULT_CONFIG.copy()
        ta_config["llm_provider"]            = config.llm_provider
        ta_config["deep_think_llm"]          = config.deep_think_llm
        ta_config["quick_think_llm"]         = config.quick_think_llm
        ta_config["max_debate_rounds"]       = config.max_debate_rounds
        ta_config["max_risk_discuss_rounds"] = config.max_risk_discuss_rounds

        try:
            token_handler = TokenCallbackHandler()
            ta = TradingAgentsGraph(
                debug=False,
                config=ta_config,
                selected_analysts=config.enabled_analysts or
                    ["market", "news", "fundamentals", "social"],
                callbacks=[token_handler],
            )

            turn_counts: defaultdict[str, int] = defaultdict(int)

            for step_key, report in ta.stream_propagate(config.ticker, config.date):
                tokens = token_handler.snapshot_and_reset()
                turn = turn_counts[step_key]
                yield {"event": "agent:start",    "data": {"step": step_key, "turn": turn}}
                yield {"event": "agent:complete", "data": {
                    "step": step_key, "turn": turn, "report": report,
                    "tokens_in": tokens["in"], "tokens_out": tokens["out"],
                }}
                self._store.add_report(run_id, f"{step_key}:{turn}", report)
                # Normalize to TokenUsage field names before persisting
                self._store.add_token_usage(
                    run_id, f"{step_key}:{turn}",
                    {"tokens_in": tokens["in"], "tokens_out": tokens["out"]},
                )
                turn_counts[step_key] += 1

            decision = ta._last_decision or "HOLD"
            self._store.update_decision(run_id, decision)
            self._store.update_status(run_id, RunStatus.COMPLETE)
            yield {"event": "run:complete", "data": {"decision": decision, "run_id": run_id}}

        except Exception as e:
            self._store.set_error(run_id, str(e))
            yield {"event": "run:error", "data": {"message": str(e)}}
