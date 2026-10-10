"""FastAPI backend for the TradingAgents web UI.

Mirrors the interactive CLI wizard (cli/main.py) as a chat-style flow: the
frontend walks the same ordered steps, then opens a WebSocket that streams
graph progress and report sections as they land.

Option lists are read from the same sources the CLI uses rather than being
duplicated here, so a new provider or model shows up in the web UI without a
change to this file.
"""

from __future__ import annotations

import asyncio
import os
import traceback
from datetime import date
from queue import Empty, Queue
from threading import Thread

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Load .env from the repo root so API keys are present exactly as the CLI sees
# them. The backend is always started from the repo root.
load_dotenv()

from cli.models import AnalystType  # noqa: E402
from cli.prompts import _llm_provider_table, provider_default_url  # noqa: E402
from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.llm_clients.model_catalog import get_model_options  # noqa: E402

app = FastAPI(title="TradingAgents Web UI")

# The Vite dev server runs on a different port, so the browser needs CORS to
# reach the API. Origins are the two ports Vite falls back between.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Report sections in the order the graph produces them, with the labels the CLI
# prints. Drives both the progress rail and the transcript headings.
REPORT_SECTIONS = [
    ("market_report", "Market Analysis", "market"),
    ("sentiment_report", "Social Sentiment", "social"),
    ("news_report", "News Analysis", "news"),
    ("fundamentals_report", "Fundamentals Analysis", "fundamentals"),
    ("investment_plan", "Research Team Decision", None),
    ("trader_investment_plan", "Trading Team Plan", None),
    ("final_trade_decision", "Portfolio Management Decision", None),
]

LANGUAGES = [
    ("English (default)", "English"),
    ("Chinese (中文)", "Chinese"),
    ("Japanese (日本語)", "Japanese"),
    ("Korean (한국어)", "Korean"),
    ("Hindi (हिन्दी)", "Hindi"),
    ("Spanish (Español)", "Spanish"),
    ("Portuguese (Português)", "Portuguese"),
    ("French (Français)", "French"),
    ("German (Deutsch)", "German"),
    ("Arabic (العربية)", "Arabic"),
    ("Russian (Русский)", "Russian"),
]

DEPTH_OPTIONS = [
    ("Shallow", "Quick research, few debate and strategy rounds", 1),
    ("Medium", "Middle ground, moderate debate rounds", 3),
    ("Deep", "Comprehensive research, in-depth debate", 5),
]

ANALYSTS = [
    ("Market Analyst", AnalystType.MARKET.value),
    ("Sentiment Analyst", AnalystType.SOCIAL.value),
    ("News Analyst", AnalystType.NEWS.value),
    ("Fundamentals Analyst", AnalystType.FUNDAMENTALS.value),
]

# Which env var must be set for a provider to be usable, so the UI can mark
# providers the user has no key for. Providers absent from this map need no key.
PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "glm": "ZHIPU_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
    "groq": "GROQ_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "openai_compatible": "OPENAI_COMPATIBLE_API_KEY",
}

# Provider-specific reasoning knob. Key is the provider; value is the config key
# plus the choices, matching ask_gemini_thinking_config / ask_openai_reasoning_
# effort / ask_anthropic_effort in cli/utils.py.
EFFORT_STEPS = {
    "google": {
        "config_key": "google_thinking_level",
        "title": "Thinking Mode",
        "prompt": "Configure Gemini thinking mode",
        "options": [
            ("Enable Thinking (recommended)", "high"),
            ("Minimal / Disable Thinking", "minimal"),
        ],
    },
    "openai": {
        "config_key": "openai_reasoning_effort",
        "title": "Reasoning Effort",
        "prompt": "Configure OpenAI reasoning effort level",
        "options": [
            ("High", "high"),
            ("Medium", "medium"),
            ("Low", "low"),
        ],
    },
    "anthropic": {
        "config_key": "anthropic_effort",
        "title": "Effort Level",
        "prompt": "Configure Claude effort level",
        "options": [
            ("High (recommended)", "high"),
            ("Medium (balanced)", "medium"),
            ("Low (faster, cheaper)", "low"),
        ],
    },
}


def _providers() -> list[dict]:
    out = []
    for display, key, url in _llm_provider_table():
        env = PROVIDER_KEY_ENV.get(key)
        out.append(
            {
                "label": display,
                "value": key,
                "backend_url": url,
                "key_env": env,
                # A provider with no env requirement (ollama, azure, bedrock)
                # is never marked missing; its credentials live elsewhere.
                "has_key": True if env is None else bool(os.environ.get(env)),
            }
        )
    return out


@app.get("/api/options")
def options() -> dict:
    """Everything the wizard needs to render its steps in one round trip."""
    return {
        "today": date.today().isoformat(),
        "languages": [{"label": lbl, "value": val} for lbl, val in LANGUAGES],
        "depths": [
            {"label": lbl, "description": desc, "value": val}
            for lbl, desc, val in DEPTH_OPTIONS
        ],
        "analysts": [{"label": lbl, "value": val} for lbl, val in ANALYSTS],
        "providers": _providers(),
        "effort_steps": EFFORT_STEPS,
        "sections": [
            {"key": k, "label": lbl, "analyst": a} for k, lbl, a in REPORT_SECTIONS
        ],
        "defaults": {
            "language": DEFAULT_CONFIG.get("output_language", "English"),
            "depth": 3,
            "analysts": [a for _, a in ANALYSTS],
        },
    }


@app.get("/api/models")
def models(provider: str, mode: str = "quick") -> dict:
    """Model choices for a provider, straight from the shared catalog.

    OpenRouter and Azure are free-text in the CLI (a live model list and a
    deployment name respectively); the UI renders a text input for those.
    """
    key = provider.lower()
    if key in ("openrouter", "azure"):
        return {
            "free_text": True,
            "hint": (
                "Enter an OpenRouter model ID (e.g. google/gemma-4-26b-a4b-it)"
                if key == "openrouter"
                else f"Enter the Azure deployment name ({mode}-thinking)"
            ),
            "options": [],
        }
    try:
        opts = get_model_options(key, mode)
    except Exception:
        opts = []
    return {
        "free_text": False,
        "hint": "",
        "options": [{"label": d, "value": v} for d, v in opts],
    }


# Common mistakes worth naming outright: a company name typed instead of its
# symbol, or an Indian listing without its exchange suffix. Yahoo needs the
# exact symbol, and a wrong one otherwise fails deep inside a run that has
# already spent LLM calls.
_SUGGESTIONS = {
    "APPLE": "AAPL",
    "GOOGLE": "GOOGL",
    "ALPHABET": "GOOGL",
    "AMAZON": "AMZN",
    "MICROSOFT": "MSFT",
    "META": "META",
    "FACEBOOK": "META",
    "TESLA": "TSLA",
    "NVIDIA": "NVDA",
    "NETFLIX": "NFLX",
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "INFOSYS": "INFY.NS",
    "INFY": "INFY.NS",
    "HDFC": "HDFCBANK.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "ICICI": "ICICIBANK.NS",
    "SBI": "SBIN.NS",
    "TATA": "TATAMOTORS.NS",
    "WIPRO": "WIPRO.NS",
    "AIRTEL": "BHARTIARTL.NS",
    "BITCOIN": "BTC-USD",
    "ETHEREUM": "ETH-USD",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
}


@app.get("/api/validate")
def validate(symbol: str) -> dict:
    """Check a ticker prices on Yahoo before a run is allowed to start.

    Without this the graph starts, the market analyst burns LLM calls, and only
    then does the data layer raise NoMarketDataError — an expensive way to learn
    the symbol was wrong, especially on a rate-limited free tier.
    """
    from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component
    from tradingagents.dataflows.vendors.yahoo.ohlcv import load_ohlcv

    raw = (symbol or "").strip()
    if not raw:
        return {"ok": False, "message": "Enter a ticker symbol."}

    upper = raw.upper()
    hint = _SUGGESTIONS.get(upper)

    try:
        safe_ticker_component(upper)
    except ValueError:
        return {
            "ok": False,
            "message": f"`{raw}` isn't a valid symbol format.",
            "suggestion": hint,
        }

    canonical = normalize_symbol(raw)

    # A bare suffix like ".NS" is a common half-edit; name it specifically
    # rather than letting it read as a generic lookup failure.
    if canonical.startswith("."):
        return {
            "ok": False,
            "message": (
                f"`{canonical}` is only an exchange suffix, not a ticker. "
                "It needs a symbol in front of it — for example `RELIANCE.NS`."
            ),
        }

    try:
        rows = load_ohlcv(canonical, date.today().isoformat(), fill_gaps=False)
        if rows is None or len(rows) == 0:
            raise ValueError("no rows")
    except Exception:
        msg = f"Yahoo Finance has no price data for `{canonical}`."
        if hint:
            msg += f" Did you mean `{hint}`?"
        else:
            msg += (
                " Check the exchange suffix — Indian listings need `.NS` or `.BO`"
                " (e.g. `RELIANCE.NS`), London `.L`, Tokyo `.T`, Hong Kong `.HK`,"
                " and crypto uses a pair like `BTC-USD`."
            )
        return {"ok": False, "message": msg, "suggestion": hint}

    return {"ok": True, "canonical": canonical, "rows": int(len(rows))}


def _build_config(sel: dict) -> dict:
    config = DEFAULT_CONFIG.copy()
    provider = sel["llm_provider"].lower()
    config["llm_provider"] = provider
    config["quick_think_llm"] = sel["quick_think_llm"]
    config["deep_think_llm"] = sel["deep_think_llm"]
    config["output_language"] = sel.get("output_language", "English")

    # On by default here (unlike the CLI, where it is opt-in): a browser run has
    # no terminal to retry from, and free-tier provider quotas make a mid-run
    # failure likely. Resuming costs no extra requests for work already done.
    config["checkpoint_enabled"] = True

    depth = int(sel.get("research_depth", 3))
    config["max_debate_rounds"] = depth
    config["max_risk_discuss_rounds"] = depth

    backend_url = sel.get("backend_url") or provider_default_url(provider)
    if backend_url:
        config["backend_url"] = backend_url

    # Only the knob belonging to the chosen provider is set; the others stay at
    # their defaults so an unrelated provider is never handed a foreign param.
    step = EFFORT_STEPS.get(provider)
    if step and sel.get("effort"):
        config[step["config_key"]] = sel["effort"]

    return config


def _run_graph_into(queue: Queue, sel: dict) -> None:
    """Run the graph on a worker thread, pushing events onto ``queue``.

    The graph is synchronous and long-running, so it cannot share the event
    loop; the WebSocket handler drains this queue instead.
    """

    def emit(kind: str, **payload):
        queue.put({"type": kind, **payload})

    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        analysts = sel.get("analysts") or [a for _, a in ANALYSTS]
        config = _build_config(sel)

        emit("status", message="Initializing agents…")
        graph = TradingAgentsGraph(
            selected_analysts=analysts, debug=False, config=config
        )

        ticker = sel["ticker"].strip().upper()
        trade_date = sel["analysis_date"]
        asset_type = sel.get("asset_type") or "stock"

        emit("status", message=f"Analyzing {ticker} as of {trade_date}…")

        # The same richer state the CLI builds: settled decision log, past
        # context and resolved instrument identity.
        init_state = graph.create_run_state(ticker, trade_date, asset_type, None)
        args = graph.propagator.get_graph_args()

        # Recompile with a checkpointer and inject the thread_id so a run that
        # dies partway (a provider rate limit, most often) resumes from the last
        # completed node instead of spending quota redoing finished work.
        # No-op when checkpointing is disabled. Torn down in the finally below.
        thread_id = graph.begin_checkpoint(ticker, trade_date, asset_type, None)
        if thread_id is not None:
            args.setdefault("config", {}).setdefault("configurable", {})[
                "thread_id"
            ] = thread_id
            if getattr(graph, "_resuming", False):
                emit("status", message="Resuming from the last checkpoint…")

        seen: dict[str, str] = {}
        final_state: dict = {}

        try:
            # On resume, feed None so LangGraph continues the interrupted run
            # rather than re-appending the initial state through the reducer.
            for chunk in graph.graph.stream(graph.checkpoint_input(init_state), **args):
                if not isinstance(chunk, dict):
                    continue
                final_state.update(chunk)
                # Emit each report section the first time it appears, and again
                # if a later node revises it (debate rounds rewrite
                # investment_plan).
                for key, label, _analyst in REPORT_SECTIONS:
                    value = chunk.get(key)
                    if value and isinstance(value, str) and seen.get(key) != value:
                        seen[key] = value
                        emit("section", key=key, label=label, content=value)

            # Only a clean run logs the decision and drops its checkpoint; a
            # mid-stream failure skips both so the next attempt can resume.
            graph.record_decision(ticker, trade_date, final_state)
            graph.clear_checkpoint_on_success(ticker, trade_date, asset_type, None)
        finally:
            graph.end_checkpoint()

        decision = final_state.get("final_trade_decision") or ""
        emit("done", decision=decision)

    except Exception as exc:  # surfaced to the UI rather than dying silently
        emit("error", message=str(exc), detail=traceback.format_exc())
    finally:
        queue.put({"type": "__closed__"})


@app.websocket("/ws/run")
async def ws_run(ws: WebSocket) -> None:
    await ws.accept()
    try:
        sel = await ws.receive_json()
    except (WebSocketDisconnect, RuntimeError):
        return

    queue: Queue = Queue()
    worker = Thread(target=_run_graph_into, args=(queue, sel), daemon=True)
    worker.start()

    try:
        while True:
            try:
                event = queue.get_nowait()
            except Empty:
                # Yield to the loop so the socket stays responsive while the
                # synchronous graph works.
                await asyncio.sleep(0.15)
                continue
            if event.get("type") == "__closed__":
                break
            await ws.send_json(event)
    except WebSocketDisconnect:
        return
    finally:
        try:
            await ws.close()
        except RuntimeError:
            pass


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}
