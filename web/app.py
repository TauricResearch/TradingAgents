"""FastAPI web application for TradingAgents."""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import lightweight config
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.model_catalog import get_model_options, get_known_models
from tradingagents.llm_clients.api_key_env import get_api_key_env, PROVIDER_API_KEY_ENV

# Heavy imports (trading_graph imports yfinance, etc.) will be done lazily in background tasks

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state for active analysis
active_analyses: Dict[str, Dict[str, Any]] = {}

# Sensible default models per provider, used when the chosen provider does
# not match the configured models (e.g. provider=anthropic but the default
# config still points deep_think_llm at an OpenAI "gpt-5.5"). Keeps the
# provider and model in sync so the right SDK/key is exercised.
PROVIDER_DEFAULT_MODELS: Dict[str, Dict[str, str]] = {
    "openai":     {"deep": "gpt-5.5",            "quick": "gpt-5.4-mini"},
    "anthropic":  {"deep": "claude-opus-4-8",    "quick": "claude-haiku-4-5"},
    "google":     {"deep": "gemini-3.1-pro",     "quick": "gemini-3.1-flash"},
    "xai":        {"deep": "grok-4",             "quick": "grok-4-mini"},
    "deepseek":   {"deep": "deepseek-reasoner",  "quick": "deepseek-chat"},
    "qwen":       {"deep": "qwen3.7-max",        "quick": "qwen3.6-flash"},
    "qwen-cn":    {"deep": "qwen3.7-max",        "quick": "qwen3.6-flash"},
    "glm":        {"deep": "glm-5.1",            "quick": "glm-5-turbo"},
    "glm-cn":     {"deep": "glm-5.1",            "quick": "glm-5-turbo"},
}


def _first_configured_provider() -> Optional[str]:
    """Return the first provider (in preference order) that has an API key set."""
    preference = [
        "openai", "anthropic", "google", "xai", "deepseek",
        "qwen", "qwen-cn", "glm", "glm-cn", "minimax", "minimax-cn",
        "openrouter",
    ]
    for provider in preference:
        env_var = get_api_key_env(provider)
        if env_var and os.environ.get(env_var):
            return provider
    return None


def _resolve_provider_models(provider: str, config: Dict[str, Any]) -> None:
    """Ensure config's models match the chosen provider, in-place.

    If the user left the model as the default (or it belongs to a different
    provider family), substitute that provider's recommended models so the
    correct client and API key are used.
    """
    defaults = PROVIDER_DEFAULT_MODELS.get(provider)
    if not defaults:
        return

    deep = config.get("deep_think_llm") or DEFAULT_CONFIG.get("deep_think_llm", "")
    quick = config.get("quick_think_llm") or DEFAULT_CONFIG.get("quick_think_llm", "")

    # Detect a provider/model family mismatch via known model-name prefixes.
    family_prefixes = {
        "openai": "gpt", "anthropic": "claude", "google": "gemini",
        "xai": "grok", "deepseek": "deepseek", "qwen": "qwen", "qwen-cn": "qwen",
        "glm": "glm", "glm-cn": "glm",
    }
    prefix = family_prefixes.get(provider, "")

    if not deep or (prefix and not deep.lower().startswith(prefix)):
        config["deep_think_llm"] = defaults["deep"]
    if not quick or (prefix and not quick.lower().startswith(prefix)):
        config["quick_think_llm"] = defaults["quick"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    logger.info("TradingAgents Web App Starting")
    yield
    logger.info("TradingAgents Web App Shutting Down")


app = FastAPI(
    title="TradingAgents Web",
    description="Multi-Agent LLM Financial Trading Framework",
    version="0.2.5",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Routes
# ============================================================================


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main web app."""
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(html_path) as f:
        return f.read()


@app.get("/api/config")
async def get_config():
    """Get current configuration and available options."""
    providers = {
        "openai": "OpenAI",
        "google": "Google Gemini",
        "anthropic": "Anthropic Claude",
        "xai": "xAI Grok",
        "deepseek": "DeepSeek",
        "qwen": "Qwen (International)",
        "qwen-cn": "Qwen (China)",
        "glm": "GLM (International)",
        "glm-cn": "GLM (China)",
        "minimax": "MiniMax (Global)",
        "minimax-cn": "MiniMax (China)",
        "openrouter": "OpenRouter",
        "ollama": "Ollama (Local)",
        "azure": "Azure OpenAI",
    }

    # Get models for each provider
    models_by_provider = {}
    for provider in providers.keys():
        try:
            # Get quick and deep thinking models for the provider
            quick_models = get_model_options(provider, "quick")
            deep_models = get_model_options(provider, "deep")

            # Combine and deduplicate
            all_models = list(set([m[1] for m in quick_models + deep_models]))[:10]
            models_by_provider[provider] = [
                {"id": model_id, "name": model_id}
                for model_id in all_models
            ]
        except Exception as e:
            logger.warning(f"Error loading models for {provider}: {e}")
            models_by_provider[provider] = []

    # Detect which providers have their API key configured in the environment
    provider_key_status = {}
    for provider in providers.keys():
        env_var = get_api_key_env(provider)
        if env_var is None:
            # Local runtimes (ollama) need no key
            provider_key_status[provider] = {"required": False, "configured": True, "env_var": None}
        else:
            provider_key_status[provider] = {
                "required": True,
                "configured": bool(os.environ.get(env_var)),
                "env_var": env_var,
            }

    return {
        "providers": providers,
        "models_by_provider": models_by_provider,
        "provider_key_status": provider_key_status,
        "default_config": {
            "llm_provider": DEFAULT_CONFIG.get("llm_provider", "openai"),
            "deep_think_llm": DEFAULT_CONFIG.get("deep_think_llm", "gpt-5.5"),
            "quick_think_llm": DEFAULT_CONFIG.get("quick_think_llm", "gpt-5.4"),
            "temperature": DEFAULT_CONFIG.get("temperature", 0.7),
            "max_debate_rounds": DEFAULT_CONFIG.get("max_debate_rounds", 2),
            "max_risk_discuss_rounds": DEFAULT_CONFIG.get("max_risk_discuss_rounds", 1),
            "checkpoint_enabled": DEFAULT_CONFIG.get("checkpoint_enabled", False),
            "output_language": DEFAULT_CONFIG.get("output_language", "en"),
        },
        "analysts": [
            {"id": "market", "name": "Market Analyst", "description": "Technical indicators and price patterns"},
            {"id": "social", "name": "Sentiment Analyst", "description": "StockTwits, Reddit sentiment"},
            {"id": "news", "name": "News Analyst", "description": "News and macroeconomic impact"},
            {"id": "fundamentals", "name": "Fundamentals Analyst", "description": "Financial statements and metrics"},
        ],
    }


@app.post("/api/analyze/start")
async def start_analysis(background_tasks: BackgroundTasks, request_data: Dict[str, Any]):
    """Start a new analysis."""
    try:
        ticker = request_data.get("ticker", "").upper()
        date = request_data.get("date", datetime.now().strftime("%Y-%m-%d"))
        config = request_data.get("config", {})
        analysts = request_data.get("analysts", ["market", "social", "news", "fundamentals"])

        # Validate inputs
        if not ticker:
            raise HTTPException(status_code=400, detail="Ticker is required")
        if not date:
            raise HTTPException(status_code=400, detail="Date is required")

        # Resolve provider: use the requested one, else the configured default,
        # else auto-pick the first provider that has an API key configured.
        provider = config.get("llm_provider") or DEFAULT_CONFIG.get("llm_provider", "openai")
        env_var = get_api_key_env(provider)
        if env_var is not None and not os.environ.get(env_var):
            # The requested provider has no key. Try to auto-select one that does.
            available = _first_configured_provider()
            if available:
                logger.info(
                    f"Provider '{provider}' has no key; auto-selecting '{available}'"
                )
                provider = available
                env_var = get_api_key_env(provider)
            else:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"No API key configured for provider '{provider}'. "
                        f"Set the {env_var} environment variable in your Railway "
                        f"service (Variables tab) and redeploy. No other provider "
                        f"has a key configured either."
                    ),
                )

        # Lock in the resolved provider and keep its models in sync.
        config["llm_provider"] = provider
        _resolve_provider_models(provider, config)

        # Create analysis ID
        analysis_id = f"{ticker}_{int(datetime.now().timestamp())}"

        # Store analysis state
        active_analyses[analysis_id] = {
            "id": analysis_id,
            "ticker": ticker,
            "date": date,
            "status": "queued",
            "progress": 0,
            "messages": [],
            "result": None,
            "error": None,
            "started_at": datetime.now().isoformat(),
        }

        # Run analysis in background
        background_tasks.add_task(run_analysis_task, analysis_id, ticker, date, config, analysts)

        return {"analysis_id": analysis_id, "status": "queued"}

    except Exception as e:
        logger.error(f"Error starting analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analyze/{analysis_id}")
async def get_analysis_status(analysis_id: str):
    """Get analysis status and progress."""
    if analysis_id not in active_analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")

    analysis = active_analyses[analysis_id]
    return {
        "id": analysis["id"],
        "ticker": analysis["ticker"],
        "date": analysis["date"],
        "status": analysis["status"],
        "progress": analysis["progress"],
        "message_count": len(analysis["messages"]),
        "result": analysis["result"],
        "error": analysis["error"],
        "started_at": analysis["started_at"],
    }


@app.get("/api/analyze/{analysis_id}/messages")
async def get_analysis_messages(analysis_id: str, skip: int = 0, limit: int = 50):
    """Get analysis messages."""
    if analysis_id not in active_analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")

    messages = active_analyses[analysis_id]["messages"]
    return {
        "total": len(messages),
        "messages": messages[skip : skip + limit],
    }


@app.websocket("/ws/analyze/{analysis_id}")
async def websocket_analyze(websocket: WebSocket, analysis_id: str):
    """WebSocket endpoint for real-time analysis updates."""
    if analysis_id not in active_analyses:
        await websocket.close(code=4004, reason="Analysis not found")
        return

    await websocket.accept()

    # Send initial state
    analysis = active_analyses[analysis_id]
    await websocket.send_json({
        "type": "status",
        "data": {
            "id": analysis["id"],
            "ticker": analysis["ticker"],
            "date": analysis["date"],
            "status": analysis["status"],
        },
    })

    # Keep connection open and send updates
    try:
        last_message_count = 0
        while analysis["status"] not in ["completed", "failed"]:
            current_message_count = len(analysis["messages"])

            # Send new messages
            if current_message_count > last_message_count:
                new_messages = analysis["messages"][last_message_count:]
                for message in new_messages:
                    await websocket.send_json({
                        "type": "message",
                        "data": message,
                    })
                last_message_count = current_message_count

            # Send progress update
            await websocket.send_json({
                "type": "progress",
                "data": {"progress": analysis["progress"], "status": analysis["status"]},
            })

            await asyncio.sleep(0.5)

        # Send final result
        await websocket.send_json({
            "type": "complete",
            "data": {
                "status": analysis["status"],
                "result": analysis["result"],
                "error": analysis["error"],
            },
        })

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()


# ============================================================================
# Background Tasks
# ============================================================================


def run_analysis_task(
    analysis_id: str,
    ticker: str,
    date: str,
    config: Dict[str, Any],
    analysts: list,
):
    """Run the trading agents analysis in background."""
    # Import here to avoid loading heavy dependencies at startup
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    analysis = active_analyses[analysis_id]

    try:
        analysis["status"] = "running"
        analysis["progress"] = 10

        # Merge config with defaults
        merged_config = DEFAULT_CONFIG.copy()
        merged_config.update(config)

        # Log start
        add_message(analysis_id, "info", f"Starting analysis for {ticker} on {date}")
        add_message(
            analysis_id,
            "info",
            f"Provider: {merged_config.get('llm_provider')} | "
            f"deep: {merged_config.get('deep_think_llm')} | "
            f"quick: {merged_config.get('quick_think_llm')}",
        )
        analysis["progress"] = 20

        # Initialize graph
        add_message(analysis_id, "info", f"Selected analysts: {', '.join(analysts)}")
        ta = TradingAgentsGraph(
            selected_analysts=analysts,
            debug=True,
            config=merged_config,
        )
        analysis["progress"] = 30

        # Run analysis
        add_message(analysis_id, "info", f"Analyzing {ticker}...")
        event_stream, decision = ta.propagate(ticker, date)
        analysis["progress"] = 90

        # Store result - ensure JSON serializable
        analysis["result"] = {
            "ticker": ticker,
            "date": date,
            "decision": str(decision) if decision else None,
            "summary": "Analysis completed successfully",
        }
        analysis["progress"] = 100
        analysis["status"] = "completed"

        add_message(analysis_id, "success", f"Analysis completed for {ticker}")

    except Exception as e:
        logger.error(f"Analysis error: {e}", exc_info=True)
        analysis["status"] = "failed"
        analysis["error"] = str(e)
        add_message(analysis_id, "error", f"Analysis failed: {str(e)}")


def add_message(analysis_id: str, level: str, content: str):
    """Add a message to an analysis."""
    if analysis_id in active_analyses:
        analysis = active_analyses[analysis_id]
        analysis["messages"].append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "content": content,
        })


# ============================================================================
# Static Files & Health Check
# ============================================================================


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.2.5"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
