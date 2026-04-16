import json
import logging
import os
import re
from datetime import datetime, timezone

from orchestrator.config import OrchestratorConfig
from orchestrator.contracts.error_taxonomy import ReasonCode
from orchestrator.contracts.result_contract import Signal, build_error_signal
from tradingagents.agents.utils.agent_states import extract_research_provenance

logger = logging.getLogger(__name__)

# Provider × base_url validation matrix
# Note: ollama/openrouter share openai's canonical provider but have different URL patterns
_PROVIDER_BASE_URL_PATTERNS = {
    "anthropic": [r"api\.anthropic\.com", r"api\.minimaxi\.com/anthropic"],
    "openai": [r"api\.openai\.com"],
    "google": [r"generativelanguage\.googleapis\.com"],
    "xai": [r"api\.x\.ai"],
    "ollama": [r"localhost:\d+", r"127\.0\.0\.1:\d+", r"ollama"],
    "openrouter": [r"openrouter\.ai"],
}

# Precompile regex patterns for efficiency
_COMPILED_PATTERNS = {
    provider: [re.compile(pattern) for pattern in patterns]
    for provider, patterns in _PROVIDER_BASE_URL_PATTERNS.items()
}

# Recommended timeout thresholds by analyst count
_RECOMMENDED_TIMEOUTS = {
    1: {"analyst": 75.0, "research": 30.0},
    2: {"analyst": 90.0, "research": 45.0},
    3: {"analyst": 105.0, "research": 60.0},
    4: {"analyst": 120.0, "research": 75.0},
}


def _build_data_quality(state: str, **details):
    payload = {"state": state}
    payload.update({key: value for key, value in details.items() if value is not None})
    return payload


def _extract_research_metadata(final_state: dict | None) -> dict | None:
    if not isinstance(final_state, dict):
        return None
    debate_state = final_state.get("investment_debate_state") or {}
    return extract_research_provenance(debate_state)


def _looks_like_provider_auth_failure(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "authentication_error",
        "login fail",
        "please carry the api secret key",
        "invalid api key",
        "unauthorized",
        "error code: 401",
    )
    return any(marker in text for marker in markers)


class LLMRunner:
    def __init__(self, config: OrchestratorConfig):
        self._config = config
        self._graph = None  # Lazy-initialized on first get_signal() call (requires API key)
        self.cache_dir = config.cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self._validate_timeout_config()

    def _validate_timeout_config(self):
        """Warn if timeout configuration may be insufficient for selected analysts."""
        trading_cfg = self._config.trading_agents_config or {}
        selected_analysts = trading_cfg.get("selected_analysts", ["market", "social", "news", "fundamentals"])
        analyst_count = len(selected_analysts) if selected_analysts else 4

        analyst_timeout = float(trading_cfg.get("analyst_node_timeout_secs", 75.0))
        research_timeout = float(trading_cfg.get("research_node_timeout_secs", 30.0))

        # Get recommended thresholds (use max if analyst_count > 4)
        recommended = _RECOMMENDED_TIMEOUTS.get(analyst_count, _RECOMMENDED_TIMEOUTS[4])

        warnings = []
        if analyst_timeout < recommended["analyst"]:
            warnings.append(
                f"analyst_node_timeout_secs={analyst_timeout:.1f}s may be insufficient "
                f"for {analyst_count} analyst(s) (recommended: {recommended['analyst']:.1f}s)"
            )
        if research_timeout < recommended["research"]:
            warnings.append(
                f"research_node_timeout_secs={research_timeout:.1f}s may be insufficient "
                f"for {analyst_count} analyst(s) (recommended: {recommended['research']:.1f}s)"
            )

        for warning in warnings:
            logger.warning("LLMRunner: %s", warning)

    def _get_graph(self):
        """Lazy-initialize TradingAgentsGraph (heavy, requires API key at init time)."""
        if self._graph is None:
            from tradingagents.graph.trading_graph import TradingAgentsGraph
            trading_cfg = self._config.trading_agents_config if self._config.trading_agents_config else None
            graph_kwargs = {"config": trading_cfg}
            if trading_cfg and "selected_analysts" in trading_cfg:
                graph_kwargs["selected_analysts"] = trading_cfg["selected_analysts"]
            self._graph = TradingAgentsGraph(**graph_kwargs)
        return self._graph

    def _detect_provider_mismatch(self):
        """Validate provider × base_url compatibility using pattern matrix.

        Uses the original provider name (not canonical) for validation since
        ollama/openrouter share openai's canonical provider but have different URLs.
        """
        trading_cfg = self._config.trading_agents_config or {}
        provider = str(trading_cfg.get("llm_provider", "")).lower()
        base_url = str(trading_cfg.get("backend_url", "") or "").lower()

        if not provider or not base_url:
            return None

        # Use original provider name for pattern matching (not canonical)
        # This handles ollama/openrouter which share openai's canonical provider
        compiled_patterns = _COMPILED_PATTERNS.get(provider, [])
        if not compiled_patterns:
            # No validation rules defined for this provider
            return None

        for pattern in compiled_patterns:
            if pattern.search(base_url):
                return None  # Match found, no mismatch

        # No pattern matched - return raw patterns for error message
        return {
            "provider": provider,
            "backend_url": trading_cfg.get("backend_url"),
            "expected_patterns": _PROVIDER_BASE_URL_PATTERNS[provider],
        }

    def get_signal(self, ticker: str, date: str) -> Signal:
        """获取指定股票在指定日期的 LLM 信号，带缓存。"""
        # Validate configuration first (lightweight, prevents returning stale cache on config errors)
        mismatch = self._detect_provider_mismatch()
        if mismatch is not None:
            return build_error_signal(
                ticker=ticker,
                source="llm",
                reason_code=ReasonCode.PROVIDER_MISMATCH.value,
                message=(
                    f"provider '{mismatch['provider']}' does not match backend_url "
                    f"'{mismatch['backend_url']}'"
                ),
                metadata={
                    "data_quality": _build_data_quality("provider_mismatch", **mismatch),
                },
            )

        # Check cache after validation
        safe_ticker = ticker.replace("/", "_")
        cache_path = os.path.join(self.cache_dir, f"{safe_ticker}_{date}.json")

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("LLMRunner: cache hit for %s %s", ticker, date)
            return Signal(
                ticker=ticker,
                direction=data["direction"],
                confidence=data["confidence"],
                source="llm",
                timestamp=datetime.fromisoformat(data["timestamp"]),
                metadata=data,
            )
        except FileNotFoundError:
            pass  # Continue to LLM call

        try:
            _final_state, processed_signal = self._get_graph().propagate(ticker, date)
            rating = processed_signal if isinstance(processed_signal, str) else str(processed_signal)
            direction, confidence = self._map_rating(rating)
            now = datetime.now(timezone.utc)
            research_metadata = _extract_research_metadata(_final_state)
            if research_metadata and research_metadata.get("research_status") != "full":
                data_quality = _build_data_quality(
                    "research_degraded",
                    research_status=research_metadata.get("research_status"),
                    research_mode=research_metadata.get("research_mode"),
                    degraded_reason=research_metadata.get("degraded_reason"),
                    timed_out_nodes=research_metadata.get("timed_out_nodes"),
                )
            else:
                data_quality = _build_data_quality("ok")

            cache_data = {
                "rating": rating,
                "direction": direction,
                "confidence": confidence,
                "timestamp": now.isoformat(),
                "ticker": ticker,
                "date": date,
                "decision_structured": (
                    (_final_state or {}).get("final_trade_decision_structured")
                    if isinstance(_final_state, dict)
                    else None
                ),
                "data_quality": data_quality,
                "research": research_metadata,
                "sample_quality": (
                    "degraded_research"
                    if research_metadata and research_metadata.get("research_status") != "full"
                    else "full_research"
                ),
            }
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            return Signal(
                ticker=ticker,
                direction=direction,
                confidence=confidence,
                source="llm",
                timestamp=now,
                metadata=cache_data,
            )
        except Exception as e:
            logger.error("LLMRunner: propagate failed for %s %s: %s", ticker, date, e)
            reason_code = ReasonCode.LLM_SIGNAL_FAILED.value
            if "Unsupported LLM provider" in str(e):
                reason_code = ReasonCode.PROVIDER_MISMATCH.value
            elif _looks_like_provider_auth_failure(e):
                reason_code = ReasonCode.PROVIDER_AUTH_FAILED.value

            # Map reason code to data quality state
            state_map = {
                ReasonCode.PROVIDER_MISMATCH.value: "provider_mismatch",
                ReasonCode.PROVIDER_AUTH_FAILED.value: "provider_auth_failed",
            }
            state = state_map.get(reason_code, "unknown")

            return build_error_signal(
                ticker=ticker,
                source="llm",
                reason_code=reason_code,
                message=str(e),
                metadata={
                    "data_quality": _build_data_quality(
                        state,
                        provider=(self._config.trading_agents_config or {}).get("llm_provider"),
                        backend_url=(self._config.trading_agents_config or {}).get("backend_url"),
                    ),
                },
            )

    def _map_rating(self, rating: str) -> tuple[int, float]:
        """将 5 级评级映射为 (direction, confidence)。"""
        mapping = {
            "BUY": (1, 0.9),
            "OVERWEIGHT": (1, 0.6),
            "HOLD": (0, 0.5),
            "UNDERWEIGHT": (-1, 0.6),
            "SELL": (-1, 0.9),
        }
        result = mapping.get(rating.upper() if rating else "", None)
        if result is None:
            logger.warning("LLMRunner: unknown rating %r, falling back to HOLD", rating)
            return (0, 0.5)
        return result
