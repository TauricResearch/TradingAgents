import os
from copy import deepcopy

from cli.models import AnalystType
from cli.utils import detect_asset_type, filter_analysts_for_asset_type
from tradingagents.default_config import DEFAULT_CONFIG
from web.models import AnalysisRequest


ANALYST_ORDER = ["market", "social", "news", "fundamentals"]
DEFAULT_OLLAMA_BACKEND_URL = "http://localhost:11434/v1"


def resolve_backend_url(provider: str, requested_url: str | None) -> str | None:
    if requested_url:
        return requested_url
    if provider.lower() == "ollama":
        return os.environ.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BACKEND_URL
    return None


def build_web_config(request: AnalysisRequest) -> tuple[dict, list[str], str]:
    asset_type = detect_asset_type(request.ticker)
    requested = [AnalystType(value) for value in request.analysts]
    allowed = filter_analysts_for_asset_type(requested, asset_type)
    selected = [analyst.value for analyst in allowed]

    if not selected:
        raise ValueError("At least one analyst must be selected for this asset type.")

    selected = [value for value in ANALYST_ORDER if value in set(selected)]

    config = deepcopy(DEFAULT_CONFIG)
    config["max_debate_rounds"] = request.research_depth
    config["max_risk_discuss_rounds"] = request.research_depth
    config["quick_think_llm"] = request.quick_think_llm
    config["deep_think_llm"] = request.deep_think_llm
    config["llm_provider"] = request.llm_provider.lower()
    config["backend_url"] = resolve_backend_url(config["llm_provider"], request.backend_url)
    config["google_thinking_level"] = request.google_thinking_level
    config["openai_reasoning_effort"] = request.openai_reasoning_effort
    config["anthropic_effort"] = request.anthropic_effort
    config["output_language"] = request.output_language
    config["checkpoint_enabled"] = request.checkpoint_enabled

    return config, selected, asset_type.value
