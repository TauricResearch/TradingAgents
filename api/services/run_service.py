import logging
from collections import defaultdict
from typing import Generator
from api.store.runs_store import RunsStore
from api.models.run import RunConfig, RunStatus

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

        self._store.update_status(run_id, RunStatus.RUNNING)
        config = run.config

        ta_config = DEFAULT_CONFIG.copy()
        ta_config["llm_provider"]            = config.llm_provider
        ta_config["deep_think_llm"]          = config.deep_think_llm
        ta_config["quick_think_llm"]         = config.quick_think_llm
        ta_config["max_debate_rounds"]       = config.max_debate_rounds
        ta_config["max_risk_discuss_rounds"] = config.max_risk_discuss_rounds

        try:
            ta = TradingAgentsGraph(
                debug=False,
                config=ta_config,
                selected_analysts=config.enabled_analysts or
                    ["market", "news", "fundamentals", "social"],
            )

            turn_counts: defaultdict[str, int] = defaultdict(int)

            for step_key, report in ta.stream_propagate(config.ticker, config.date):
                turn = turn_counts[step_key]
                yield {"event": "agent:start",    "data": {"step": step_key, "turn": turn}}
                yield {"event": "agent:complete", "data": {"step": step_key, "turn": turn, "report": report}}
                self._store.add_report(run_id, f"{step_key}:{turn}", report)
                turn_counts[step_key] += 1

            decision = ta._last_decision or "HOLD"
            self._store.update_decision(run_id, decision)
            self._store.update_status(run_id, RunStatus.COMPLETE)
            yield {"event": "run:complete", "data": {"decision": decision, "run_id": run_id}}

        except Exception as e:
            self._store.set_error(run_id, str(e))
            yield {"event": "run:error", "data": {"message": str(e)}}
