import os
import sys
from pathlib import Path

from fastapi import APIRouter

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS  # noqa: E402

from ...models.schemas import (  # noqa: E402
    APIKeyInfo,
    APIKeysStatusResponse,
    APIKeysUpdateRequest,
    ConfigOptionsResponse,
)

router = APIRouter(prefix="/config", tags=["Configuration"])

KEY_DEFINITIONS = [
    {"provider": "openai", "env_var": "OPENAI_API_KEY", "category": "llm"},
    {"provider": "anthropic", "env_var": "ANTHROPIC_API_KEY", "category": "llm"},
    {"provider": "google", "env_var": "GOOGLE_API_KEY", "category": "llm"},
    {"provider": "deepseek", "env_var": "DEEPSEEK_API_KEY", "category": "llm"},
    {"provider": "groq", "env_var": "GROQ_API_KEY", "category": "llm"},
    {"provider": "openrouter", "env_var": "OPENROUTER_API_KEY", "category": "llm"},
    {"provider": "openai_compatible", "env_var": "OPENAI_COMPATIBLE_API_KEY", "category": "llm"},
    {"provider": "minimax", "env_var": "MINIMAX_API_KEY", "category": "llm"},
    {"provider": "fmp", "env_var": "FINANCIAL_MODELING_PREP_API_KEY", "category": "data"},
    {"provider": "alpha_vantage", "env_var": "ALPHA_VANTAGE_API_KEY", "category": "data"},
    {"provider": "fred", "env_var": "FRED_API_KEY", "category": "data"},
]


def _mask_key(val: str | None) -> str:
    if not val:
        return ""
    val = val.strip()
    if len(val) >= 8:
        return f"{val[:3]}...{val[-4:]}"
    elif len(val) > 2:
        return f"{val[0]}...{val[-1]}"
    return "***"

ANALYSTS_METADATA = [
    {
        "key": "market",
        "name": "Market Analyst",
        "description": "Technical indicators (MA, MACD, RSI, Bollinger Bands, ATR) and price action trends."
    },
    {
        "key": "social",
        "name": "Sentiment Analyst",
        "description": "Social sentiment aggregation from StockTwits, Reddit, and retail chatter."
    },
    {
        "key": "news",
        "name": "News Analyst",
        "description": "Global macro affairs, FRED interest rates, inflation, and Polymarket probabilities."
    },
    {
        "key": "fundamentals",
        "name": "Fundamentals Analyst",
        "description": "Financial statements: Balance Sheet, Cash Flow, Income Statement, P/E, EPS."
    }
]

LANGUAGES = [
    "English",
    "Vietnamese",
    "Chinese",
    "Japanese",
    "Korean",
    "German",
    "French",
    "Spanish"
]

PROVIDERS = [
    {"id": "openai", "name": "OpenAI (GPT-5.x / GPT-4.x)", "default_deep": "gpt-5.6", "default_quick": "gpt-5.6-luna"},
    {"id": "google", "name": "Google (Gemini 2.5 / 3.x)", "default_deep": "gemini-3.1-pro", "default_quick": "gemini-3.1-flash"},
    {"id": "anthropic", "name": "Anthropic (Claude 4.x / 5.x)", "default_deep": "claude-sonnet-5", "default_quick": "claude-haiku-4.5"},
    {"id": "deepseek", "name": "DeepSeek (V3 / R1 / V4)", "default_deep": "deepseek-reasoner", "default_quick": "deepseek-chat"},
    {"id": "qwen", "name": "Qwen / Alibaba Cloud", "default_deep": "qwen3.7-max", "default_quick": "qwen3.7-plus"},
    {"id": "glm", "name": "GLM / Zhipu AI", "default_deep": "glm-5.3", "default_quick": "glm-5.3-flash"},
    {"id": "minimax", "name": "MiniMax", "default_deep": "MiniMax-M3", "default_quick": "MiniMax-M3"},
    {"id": "ollama", "name": "Ollama (Local Open-Source)", "default_deep": "llama3.3:70b", "default_quick": "llama3.2:3b"},
    {"id": "openai_compatible", "name": "Custom OpenAI-Compatible (vLLM / LM Studio)", "default_deep": "default", "default_quick": "default"}
]

@router.get("/options", response_model=ConfigOptionsResponse)
async def get_config_options():
    """Get available providers, model catalog, analysts, and languages."""
    # Convert MODEL_OPTIONS to JSON-serializable dict
    formatted_models = {}
    for prov, mode_dict in MODEL_OPTIONS.items():
        formatted_models[prov] = {
            mode: [{"label": opt[0], "value": opt[1]} for opt in opts]
            for mode, opts in mode_dict.items()
        }

    env_lang = os.getenv("TRADINGAGENTS_OUTPUT_LANGUAGE") or os.getenv("DEFAULT_LANGUAGE") or os.getenv("LANGUAGE")
    resolved_lang = DEFAULT_CONFIG.get("output_language", "English")
    if env_lang:
        clean_lang = env_lang.strip().lower()
        if clean_lang in ("vi", "vietnamese", "tieng viet", "tiếng việt"):
            resolved_lang = "Vietnamese"
        elif clean_lang in ("en", "english"):
            resolved_lang = "English"
        elif clean_lang in ("zh", "chinese", "cn"):
            resolved_lang = "Chinese"
        elif clean_lang in ("ja", "japanese", "jp"):
            resolved_lang = "Japanese"
        else:
            resolved_lang = env_lang.capitalize()

    # Dynamic provider model defaults for openai_compatible
    providers = []
    custom_deep = DEFAULT_CONFIG.get("deep_think_llm") or os.getenv("TRADINGAGENTS_DEEP_THINK_LLM") or "ag/gemini-3.8-flash-high"
    custom_quick = DEFAULT_CONFIG.get("quick_think_llm") or os.getenv("TRADINGAGENTS_QUICK_THINK_LLM") or "ag/gemini-3.8-flash-high"
    for p in PROVIDERS:
        p_copy = p.copy()
        if p["id"] == "openai_compatible":
            p_copy["default_deep"] = custom_deep
            p_copy["default_quick"] = custom_quick
        providers.append(p_copy)

    return {
        "providers": providers,
        "models": formatted_models,
        "analysts": ANALYSTS_METADATA,
        "languages": LANGUAGES,
        "default_config": {
            "llm_provider": DEFAULT_CONFIG.get("llm_provider", "openai"),
            "deep_think_llm": DEFAULT_CONFIG.get("deep_think_llm", custom_deep),
            "quick_think_llm": DEFAULT_CONFIG.get("quick_think_llm", custom_quick),
            "max_debate_rounds": DEFAULT_CONFIG.get("max_debate_rounds", 1),
            "max_risk_discuss_rounds": DEFAULT_CONFIG.get("max_risk_discuss_rounds", 1),
            "output_language": resolved_lang,
        }
    }

@router.get("/keys", response_model=APIKeysStatusResponse)
async def get_api_keys_status():
    """Get configuration status of API keys (masked for safety)."""
    items = []
    for item in KEY_DEFINITIONS:
        val = os.getenv(item["env_var"])
        is_set = bool(val and val.strip())
        items.append(
            APIKeyInfo(
                provider=item["provider"],
                env_var=item["env_var"],
                category=item["category"],
                configured=is_set,
                preview=_mask_key(val) if is_set else ""
            )
        )
    return {"keys": items}

@router.post("/keys", response_model=APIKeysStatusResponse)
async def update_api_keys(payload: APIKeysUpdateRequest):
    """Update active API keys in the running backend environment."""
    for provider, new_val in payload.keys.items():
        # Match against KEY_DEFINITIONS
        for item in KEY_DEFINITIONS:
            if item["provider"] == provider or item["env_var"] == provider:
                val_clean = new_val.strip() if new_val else ""
                if val_clean:
                    os.environ[item["env_var"]] = val_clean
                elif new_val == "":  # Explicit clear
                    os.environ.pop(item["env_var"], None)
    return await get_api_keys_status()

