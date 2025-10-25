# app.py  — micro-service FastAPI pour TradingAgents
import os, hmac, hashlib, time, datetime as dt
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

app = FastAPI(title="TradingAgents Service")

# --------- Sécurité ----------
SERVICE_SECRET = os.getenv("SERVICE_SECRET", "")
ALLOWED_DRIFT_SEC = 120  # horodatage valide +/- 2 min

def verify_hmac(x_timestamp: str | None, x_signature: str | None, body_bytes: bytes):
    if not SERVICE_SECRET:
        return  # pas d’auth activée
    if not x_timestamp or not x_signature:
        raise HTTPException(status_code=401, detail="Missing auth headers")
    try:
        ts = int(x_timestamp)
    except Exception:
        raise HTTPException(status_code=401, detail="Bad timestamp")

    now = int(time.time())
    if abs(now - ts) > ALLOWED_DRIFT_SEC:
        raise HTTPException(status_code=401, detail="Stale request")

    # signature = HMAC_SHA256(secret, f"{timestamp}.{body}")
    msg = f"{x_timestamp}.".encode("utf-8") + body_bytes
    expected = hmac.new(SERVICE_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_signature):
        raise HTTPException(status_code=401, detail="Bad signature")

# --------- Schéma requête ----------
class RunBody(BaseModel):
    ticker: str
    date: str | None = None           # "YYYY-MM-DD" (optionnel)
    deep_llm: str = "gpt-4.1-mini"
    fast_llm: str = "gpt-4.1-mini"
    debates: int = 1

def build_graph(deep_llm: str, fast_llm: str, debates: int):
    cfg = DEFAULT_CONFIG.copy()
    cfg["deep_think_llm"] = deep_llm
    cfg["quick_think_llm"] = fast_llm
    cfg["max_debate_rounds"] = debates
    return TradingAgentsGraph(debug=False, config=cfg)

@app.get("/")
def health():
    return {"ok": True, "service": "TradingAgents"}

@app.post("/run")
async def run(request: Request,
              x_secret: str | None = Header(default=None),
              x_timestamp: str | None = Header(default=None),
              x_signature: str | None = Header(default=None)):
    # 1) Secret statique (simple)
    if SERVICE_SECRET and x_secret != SERVICE_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 2) HMAC anti-rejeu (recommandé). Dé-commente si tu veux l’activer en plus du secret:
    # body_bytes = await request.body()
    # verify_hmac(x_timestamp, x_signature, body_bytes)
    # body = RunBody.model_validate_json(body_bytes)

    # Si tu n'actives pas l'HMAC, on parse normalement :
    body = RunBody.model_validate(await request.json())

    date = body.date or dt.date.today().isoformat()
    graph = build_graph(body.deep_llm, body.fast_llm, body.debates)
    _, decision = graph.propagate(body.ticker.upper(), date)
    return decision
