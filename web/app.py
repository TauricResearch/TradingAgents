from dotenv import load_dotenv
load_dotenv(override=True)

import asyncio
import json
import re
import threading
import uuid
from pathlib import Path


class JobStream:
    """Replay-buffered event stream for a single analysis job.

    Multiple SSE consumers can connect (e.g. after reconnect) and each
    gets a private cursor into the shared event list, so no events are
    ever dropped.
    """
    def __init__(self):
        self.events: list[dict] = []
        self.done = False
        self._cond = threading.Condition()

    def push(self, event: dict | None):
        with self._cond:
            if event is None:
                self.done = True
            else:
                self.events.append(event)
            self._cond.notify_all()

    def subscribe(self, start: int = 0):
        """Blocking generator — yields (kind, payload) tuples.

        kind == 'event'     → payload is a dict to send
        kind == 'heartbeat' → payload is None (send keep-alive)
        kind == 'complete'  → payload is None (stream finished)
        """
        pos = start
        while True:
            with self._cond:
                while pos >= len(self.events) and not self.done:
                    self._cond.wait(timeout=25)
                batch = self.events[pos:]
                finished = self.done
            for evt in batch:
                pos += 1
                yield ('event', evt)
            if finished and pos >= len(self.events):
                yield ('complete', None)
                return
            if not batch:
                yield ('heartbeat', None)

import mistune
_md = mistune.create_markdown(plugins=["table", "strikethrough"])

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="TradingAgents")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
jobs: dict[str, JobStream] = {}

# Maps graph node names → display metadata
NODE_META = {
    "Market Analyst":        {"label": "Market Analyst",       "stage": 1},
    "tools_market":          {"label": "Market Data Tool",     "stage": 1},
    "Social Analyst":        {"label": "Social Analyst",       "stage": 1},
    "tools_social":          {"label": "Social Data Tool",     "stage": 1},
    "News Analyst":          {"label": "News Analyst",         "stage": 1},
    "tools_news":            {"label": "News Data Tool",       "stage": 1},
    "Fundamentals Analyst":  {"label": "Fundamentals Analyst", "stage": 1},
    "tools_fundamentals":    {"label": "Fundamentals Tool",    "stage": 1},
    "Bull Researcher":       {"label": "Bull Researcher",      "stage": 2},
    "Bear Researcher":       {"label": "Bear Researcher",      "stage": 2},
    "Research Manager":      {"label": "Research Manager",     "stage": 2},
    "Trader":                {"label": "Trader",               "stage": 3},
    "Aggressive Analyst":    {"label": "Aggressive Analyst",   "stage": 4},
    "Neutral Analyst":       {"label": "Neutral Analyst",      "stage": 4},
    "Conservative Analyst":  {"label": "Conservative Analyst", "stage": 4},
    "Portfolio Manager":     {"label": "Portfolio Manager",    "stage": 5},
}


class AnalysisRequest(BaseModel):
    ticker: str
    date: str
    analysts: list[str] = ["market", "social", "news", "fundamentals"]
    language: str = "English"
    research_depth: int = 1
    llm_provider: str = "anthropic"
    quick_llm: str = "claude-sonnet-4-6"
    deep_llm: str = "claude-opus-4-7"
    effort: str | None = "high"


def _run_analysis(ticker: str, trade_date: str, analysts: list[str], q: JobStream,
                  language: str = "English", research_depth: int = 1,
                  llm_provider: str = "anthropic", quick_llm: str = "claude-sonnet-4-6",
                  deep_llm: str = "claude-opus-4-7", effort: str | None = "high"):
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG

        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = llm_provider
        config["quick_think_llm"] = quick_llm
        config["deep_think_llm"] = deep_llm
        config["max_debate_rounds"] = research_depth
        config["max_risk_discuss_rounds"] = research_depth
        config["output_language"] = language
        if llm_provider == "anthropic":
            config["anthropic_effort"] = effort
        elif llm_provider == "openai":
            config["openai_reasoning_effort"] = effort
        elif llm_provider == "google":
            config["google_thinking_level"] = effort
        ta = TradingAgentsGraph(debug=False, config=config, selected_analysts=analysts)
        ta._resolve_pending_entries(ticker)

        past_context = ta.memory_log.get_past_context(ticker)
        init_state = ta.propagator.create_initial_state(ticker, trade_date, past_context=past_context)

        # Accumulate final state while streaming per-node updates
        final_state: dict = {}
        total_tokens_in = 0
        total_tokens_out = 0

        for chunk in ta.graph.stream(
            init_state,
            stream_mode="updates",
            config={"recursion_limit": ta.propagator.max_recur_limit},
        ):
            for node_name, delta in chunk.items():
                if not isinstance(delta, dict):
                    continue

                # Accumulate non-message keys for the final result
                for k, v in delta.items():
                    if k == "messages":
                        final_state.setdefault("messages", [])
                        if isinstance(v, list):
                            final_state["messages"].extend(v)
                    else:
                        final_state[k] = v

                # Emit each new message from this node
                for msg in delta.get("messages", []):
                    # Accumulate token usage
                    usage = getattr(msg, "usage_metadata", None)
                    if isinstance(usage, dict):
                        total_tokens_in  += usage.get("input_tokens", 0)
                        total_tokens_out += usage.get("output_tokens", 0)

                    content = getattr(msg, "content", "")
                    if isinstance(content, list):
                        content = "\n".join(
                            b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    content = (content or "").strip()
                    if not content:
                        continue

                    meta = NODE_META.get(node_name, {"label": node_name, "stage": 0})
                    q.push({
                        "type": "agent_update",
                        "node": node_name,
                        "label": meta["label"],
                        "stage": meta["stage"],
                        "msg_type": type(msg).__name__,
                        "content": content[:5000],
                        "tokens_in": total_tokens_in,
                        "tokens_out": total_tokens_out,
                    })

        final_decision = final_state.get("final_trade_decision", "")
        signal = ta.process_signal(final_decision)

        # Persist reports to disk so the analysis appears in Prior Analyses.
        # web/app.py streams directly via ta.graph.stream() and never calls
        # ta.propagate(), so nothing gets written unless we do it here.
        try:
            reports_dir = LOGS_DIR / ticker / trade_date / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            for fname, content in {
                "final_trade_decision.md":   final_decision,
                "trader_investment_plan.md": final_state.get("trader_investment_plan", ""),
                "investment_plan.md":        final_state.get("investment_plan", ""),
                "market_report.md":          final_state.get("market_report", ""),
                "sentiment_report.md":       final_state.get("sentiment_report", ""),
                "news_report.md":            final_state.get("news_report", ""),
                "fundamentals_report.md":    final_state.get("fundamentals_report", ""),
            }.items():
                if content:
                    (reports_dir / fname).write_text(content, encoding="utf-8")
            (reports_dir / "meta.json").write_text(json.dumps({
                "research_depth": research_depth,
                "llm_provider":   llm_provider,
                "quick_llm":      quick_llm,
                "deep_llm":       deep_llm,
                "tokens_in":      total_tokens_in,
                "tokens_out":     total_tokens_out,
            }), encoding="utf-8")
        except Exception:
            pass  # non-fatal: analysis result still delivered via SSE

        q.push({
            "type": "done",
            "signal": signal,
            "decision": final_decision,
            "market_report": final_state.get("market_report", ""),
            "news_report": final_state.get("news_report", ""),
            "sentiment_report": final_state.get("sentiment_report", ""),
            "fundamentals_report": final_state.get("fundamentals_report", ""),
        })

    except Exception as e:
        import traceback
        q.push({"type": "error", "message": str(e), "detail": traceback.format_exc()})
    finally:
        q.push(None)  # signals stream done


@app.post("/api/analyze")
async def start_analysis(req: AnalysisRequest):
    ticker = req.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker is required")

    job_id = str(uuid.uuid4())
    q = JobStream()
    jobs[job_id] = q

    threading.Thread(
        target=_run_analysis,
        args=(ticker, req.date, req.analysts, q),
        kwargs={
            "language": req.language,
            "research_depth": req.research_depth,
            "llm_provider": req.llm_provider,
            "quick_llm": req.quick_llm,
            "deep_llm": req.deep_llm,
            "effort": req.effort,
        },
        daemon=True,
    ).start()

    return {"job_id": job_id}


@app.get("/api/jobs")
async def list_jobs():
    """Return currently active (in-flight) job IDs."""
    active = {jid: s for jid, s in jobs.items() if not s.done}
    return {"active_jobs": list(active.keys()), "count": len(active)}


@app.get("/api/stream/{job_id}")
async def stream_job(job_id: str, since: int = 0):
    """Stream job events.  `since` lets a reconnecting client skip already-seen events."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    stream = jobs[job_id]

    async def event_gen():
        sub = stream.subscribe(start=since)
        loop = asyncio.get_event_loop()
        while True:
            try:
                kind, payload = await loop.run_in_executor(None, lambda: next(sub))
            except StopIteration:
                return
            if kind == 'event':
                yield f"data: {json.dumps(payload)}\n\n"
            elif kind == 'heartbeat':
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            elif kind == 'complete':
                yield f"data: {json.dumps({'type': 'complete'})}\n\n"
                return

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


LOGS_DIR = Path.home() / ".tradingagents" / "logs"


def _rx(text: str, pattern: str, group: int = 1) -> str:
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return m.group(group).strip() if m else ""


def _first_sentence(text: str) -> str:
    text = text.strip()
    m = re.match(r"(.{20,}?[.!?])\s", text)
    return m.group(1) if m else text[:200]


def _read_meta(reports_dir: Path) -> dict:
    p = reports_dir / "meta.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}


def _parse_md_report(ticker: str, date: str, reports_dir: Path) -> dict:
    def read(name: str) -> str:
        p = reports_dir / name
        return p.read_text(encoding="utf-8") if p.exists() else ""

    final      = read("final_trade_decision.md")
    trader     = read("trader_investment_plan.md")
    invest     = read("investment_plan.md")
    market     = read("market_report.md")
    sentiment  = read("sentiment_report.md")
    news       = read("news_report.md")
    fundament  = read("fundamentals_report.md")

    rating       = _rx(final,   r"\*\*Rating\*\*[:\s]+(.+)")
    price_target = _rx(final,   r"\*\*Price Target\*\*[:\s]+\$?([\d,.]+)")
    time_horizon = _rx(final,   r"\*\*Time Horizon\*\*[:\s]+(.+)")
    exec_sum     = _rx(final,   r"\*\*Executive Summary\*\*[:\s]+(.+)")
    action       = _rx(trader,  r"\*\*Action\*\*[:\s]+(.+)")
    entry_price  = _rx(trader,  r"\*\*Entry Price\*\*[:\s]+\$?([\d,.]+)")
    stop_loss    = _rx(trader,  r"\*\*Stop Loss\*\*[:\s]+\$?([\d,.]+)")
    research_rec = _rx(invest,  r"\*\*Recommendation\*\*[:\s]+(.+)")

    # Last close price — try several formats agents use
    last_price = (_rx(market, r"Last Close[:\s|*]+\$?([\d,.]+)")
               or _rx(market, r"[Cc]losing [Pp]rice[:\s*]+\$?([\d,.]+)")
               or _rx(market, r"[Cc]urrent [Pp]rice[:\s*]+\$?([\d,.]+)")
               or _rx(market, r"[Pp]rice[:\s]+\$?([\d,.]+)")
               or _rx(market, r"\$\s*([\d,.]+)\s*\((?:May|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"))

    # Sentiment direction — first bold line after the "Overall Sentiment" heading
    sent_dir = (_rx(sentiment, r"#+\s*Overall Sentiment[^\n]*\n+\**([^\n*]+)")
             or _rx(sentiment, r"\*\*((?:Bullish|Bearish|Neutral|Mixed|Positive|Negative)[^*]*)\*\*"))

    # Bull / bear one-liners from research manager rationale
    bull_line = _rx(invest, r"([Tt]he bull\b.{0,300}?)(?=[Tt]he bear\b|$)")
    bear_line = _rx(invest, r"([Tt]he bear\b.{0,300}?)(?=\n|$)")
    bull_line = _first_sentence(bull_line) if bull_line else "—"
    bear_line = _first_sentence(bear_line) if bear_line else "—"

    return {
        "ticker": ticker,
        "date": date,
        "banner": {
            "last_price":     last_price or "—",
            "sentiment":      sent_dir or "—",
            "bull":           bull_line,
            "bear":           bear_line,
            "research_mgr":   research_rec or "—",
            "trader_action":  f"{action} @ ${entry_price}" if action and entry_price else action or "—",
            "risk_mgmt":      _first_sentence(exec_sum) if exec_sum else "—",
            "portfolio_mgr":  rating or "—",
        },
        "summary": {
            "action":       action or "—",
            "entry":        entry_price or "—",
            "stop":         stop_loss or "—",
            "target":       price_target or "—",
            "horizon":      time_horizon or "—",
        },
        "reports": {
            "Final Decision":   _md(final)     if final     else "",
            "Trader Plan":      _md(trader)    if trader    else "",
            "Research Plan":    _md(invest)    if invest    else "",
            "Market":           _md(market)    if market    else "",
            "Sentiment":        _md(sentiment) if sentiment else "",
            "News":             _md(news)      if news      else "",
            "Fundamentals":     _md(fundament) if fundament else "",
        },
        "meta": _read_meta(reports_dir),
    }


def _parse_json_report(ticker: str, date: str, json_path: Path) -> dict:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    final   = data.get("final_trade_decision", "")
    invest  = data.get("investment_debate_state", {})
    risk    = data.get("risk_debate_state", {})
    trader  = data.get("trader_investment_decision", "")

    rating       = _rx(final,  r"\*\*Rating\*\*[:\s]+(.+)")
    price_target = _rx(final,  r"\*\*Price Target\*\*[:\s]+\$?([\d,.]+)")
    time_horizon = _rx(final,  r"\*\*Time Horizon\*\*[:\s]+(.+)")
    exec_sum     = _rx(final,  r"\*\*Executive Summary\*\*[:\s]+(.+)")
    action       = _rx(trader, r"\*\*Action\*\*[:\s]+(.+)")
    entry_price  = _rx(trader, r"\*\*Entry Price\*\*[:\s]+\$?([\d,.]+)")
    stop_loss    = _rx(trader, r"\*\*Stop Loss\*\*[:\s]+\$?([\d,.]+)")
    research_rec = _rx(invest.get("judge_decision", ""), r"\*\*Recommendation\*\*[:\s]+(.+)")
    risk_rec     = _rx(risk.get("judge_decision", ""),   r"\*\*Rating\*\*[:\s]+(.+)")

    def _extract_thesis(text: str) -> str:
        s = re.sub(r"^\s*\w[\w ]+:\s*#+[^\n]+\n+", "", text).strip()
        m = re.search(r"##[^\n]+\n+(.*)", s, re.DOTALL)
        return m.group(1).strip() if m else s

    bull_hist   = _extract_thesis(invest.get("bull_history", ""))
    bear_hist   = _extract_thesis(invest.get("bear_history", ""))
    market_text   = data.get("market_report", "")
    sentiment_text = data.get("sentiment_report", "")

    last_price = (_rx(market_text, r"Last Close[:\s|*]+\$?([\d,.]+)")
               or _rx(market_text, r"[Cc]losing [Pp]rice[:\s*]+\$?([\d,.]+)")
               or _rx(market_text, r"[Cc]urrent [Pp]rice[:\s*]+\$?([\d,.]+)")
               or _rx(market_text, r"trading at \*\*\$?([\d,.]+)\*\*")
               or _rx(market_text, r"[Cc]lose[:\s]+\$?([\d,.]+)")
               or _rx(market_text, r"\d{4}-\d{2}-\d{2},[^,]+,[^,]+,[^,]+,([\d.]+)"))

    sent_dir = (_rx(sentiment_text, r"#+\s*Overall Sentiment[^\n]*\n+\**([^\n*]+)")
             or _rx(sentiment_text, r"\*\*((?:Bullish|Bearish|Neutral|Mixed|Positive|Negative)[^*]*)\*\*"))

    return {
        "ticker": ticker,
        "date": date,
        "banner": {
            "last_price":    f"${last_price}" if last_price else "—",
            "sentiment":     sent_dir.strip() if sent_dir else "—",
            "bull":          _first_sentence(bull_hist) if bull_hist else "—",
            "bear":          _first_sentence(bear_hist) if bear_hist else "—",
            "research_mgr":  research_rec or "—",
            "trader_action": f"{action} @ ${entry_price}" if action and entry_price else action or "—",
            "risk_mgmt":     risk_rec or "—",
            "portfolio_mgr": rating or "—",
        },
        "summary": {
            "action":  action or "—",
            "entry":   entry_price or "—",
            "stop":    stop_loss or "—",
            "target":  price_target or "—",
            "horizon": time_horizon or "—",
        },
        "reports": {
            "Final Decision":  _md(final)                            if final                            else "",
            "Trader Plan":     _md(trader)                           if trader                           else "",
            "Research Plan":   _md(invest.get("judge_decision", "")) if invest.get("judge_decision") else "",
            "Market":          _md(data.get("market_report", ""))    if data.get("market_report")    else "",
            "Sentiment":       _md(data.get("sentiment_report", "")) if data.get("sentiment_report") else "",
            "News":            _md(data.get("news_report", ""))      if data.get("news_report")      else "",
            "Fundamentals":    _md(data.get("fundamentals_report",""))if data.get("fundamentals_report") else "",
        },
        "meta": {},
    }


@app.get("/api/reports")
async def list_reports():
    results = []
    if not LOGS_DIR.exists():
        return results

    for ticker_dir in sorted(LOGS_DIR.iterdir()):
        if not ticker_dir.is_dir():
            continue
        ticker = ticker_dir.name

        for date_dir in sorted(ticker_dir.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue
            reports_dir = date_dir / "reports"
            if reports_dir.exists() and (reports_dir / "final_trade_decision.md").exists():
                final_text = (reports_dir / "final_trade_decision.md").read_text(encoding="utf-8")
                rating = _rx(final_text, r"\*\*Rating\*\*[:\s]+(.+)")
                action = _rx(
                    (reports_dir / "trader_investment_plan.md").read_text(encoding="utf-8")
                    if (reports_dir / "trader_investment_plan.md").exists() else "",
                    r"\*\*Action\*\*[:\s]+(.+)"
                )
                results.append({
                    "ticker": ticker,
                    "date": date_dir.name,
                    "rating": rating or "—",
                    "action": action or "—",
                })

        legacy = ticker_dir / "TradingAgentsStrategy_logs"
        if legacy.exists():
            for f in sorted(legacy.glob("full_states_log_*.json"), reverse=True):
                date = f.stem.replace("full_states_log_", "")
                try:
                    jdata = json.loads(f.read_text(encoding="utf-8"))
                    j_action = _rx(jdata.get("trader_investment_decision", ""), r"\*\*Action\*\*[:\s]+(.+)")
                    j_rating = _rx(jdata.get("final_trade_decision", ""), r"\*\*Rating\*\*[:\s]+(.+)")
                except Exception:
                    j_action = j_rating = ""
                results.append({"ticker": ticker, "date": date, "rating": j_rating or "—", "action": j_action or "—"})

    return sorted(results, key=lambda x: x["date"], reverse=True)


@app.get("/api/reports/{ticker}/{date}")
async def get_report(ticker: str, date: str):
    reports_dir = LOGS_DIR / ticker / date / "reports"
    if reports_dir.exists() and (reports_dir / "final_trade_decision.md").exists():
        return _parse_md_report(ticker, date, reports_dir)

    json_path = LOGS_DIR / ticker / "TradingAgentsStrategy_logs" / f"full_states_log_{date}.json"
    if json_path.exists():
        return _parse_json_report(ticker, date, json_path)

    raise HTTPException(status_code=404, detail="Report not found")


@app.get("/api/info/{ticker}")
async def get_ticker_info(ticker: str):
    """Return company name for a ticker."""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        name = info.get("longName") or info.get("shortName") or ""
        return {"name": name}
    except Exception:
        return {"name": ""}


@app.get("/api/chart/{ticker}/{date}")
async def get_chart(ticker: str, date: str):
    """Return ~90 days of price data with MA20 and RSI(14) ending on analysis date."""
    import yfinance as yf
    from datetime import datetime, timedelta
    try:
        end_dt   = datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)
        start_dt = end_dt - timedelta(days=120)
        hist = yf.Ticker(ticker).history(
            start=start_dt.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
        )
        if hist.empty:
            return {"prices": [], "dates": [], "ma20": [], "rsi": []}
        closes = [round(float(p), 2) for p in hist["Close"]]
        dates  = [d.strftime("%Y-%m-%d") for d in hist.index.normalize()]

        # 20-day SMA
        ma20 = [None] * len(closes)
        for i in range(19, len(closes)):
            ma20[i] = round(sum(closes[i-19:i+1]) / 20, 2)

        # RSI(14) — Wilder's smoothing
        rsi = [None] * len(closes)
        n = len(closes)
        if n >= 15:
            deltas = [closes[i] - closes[i-1] for i in range(1, n)]
            gains  = [max(d, 0) for d in deltas]
            losses = [max(-d, 0) for d in deltas]
            avg_g  = sum(gains[:14]) / 14
            avg_l  = sum(losses[:14]) / 14
            rsi[14] = round(100 - 100 / (1 + avg_g / avg_l), 1) if avg_l else 100.0
            for i in range(15, n):
                avg_g = (avg_g * 13 + gains[i-1])  / 14
                avg_l = (avg_l * 13 + losses[i-1]) / 14
                rsi[i] = round(100 - 100 / (1 + avg_g / avg_l), 1) if avg_l else 100.0

        return {"ticker": ticker, "analysis_date": date,
                "prices": closes, "dates": dates, "ma20": ma20, "rsi": rsi}
    except Exception as e:
        return {"prices": [], "dates": [], "ma20": [], "rsi": [], "error": str(e)}


@app.get("/")
async def root():
    return HTMLResponse((STATIC_DIR / "index.html").read_text())
