# api/main.py

import os
import re
import json
import uuid
import time
import sqlite3
import logging
import datetime
import threading
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

import jwt
import redis
import redis.asyncio as aioredis
import yfinance as yf

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse
from pydantic import BaseModel, Field

# Import TradingAgentsGraph and configuration
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.rating import parse_rating

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("pulse-trading-signals-service")

# Resolve database path
DEFAULT_DB_PATH = os.path.expanduser("~/.tradingagents/db/signals.db")
DB_PATH = os.getenv("TRADINGAGENTS_SIGNALS_DB_PATH", DEFAULT_DB_PATH)

# Ensure the database directory exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Redis Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)

# JWT Configuration
JWT_SECRET = os.getenv("PULSE_JWT_SECRET", os.getenv("JWT_SECRET", "pulse-secret-key"))
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# Auth service entitlements URL
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "https://staging-backend.pulsenow.io")

# ---------------------------------------------------------------------------
# Ticker Universe (12-ticker global watchlist matching the design)
# ---------------------------------------------------------------------------

TICKER_NAMES: Dict[str, str] = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "SOL": "Solana",
    "AVAX": "Avalanche",
    "LINK": "Chainlink",
    "ARB": "Arbitrum",
    "DOGE": "Dogecoin",
    "NVDA": "NVIDIA Corp",
    "TSLA": "Tesla Inc",
    "AMD": "AMD Corp",
    "AAPL": "Apple Inc",
    "MSFT": "Microsoft Corp",
}

GLOBAL_TICKERS: List[tuple] = [
    ("BTC", "crypto"),
    ("ETH", "crypto"),
    ("SOL", "crypto"),
    ("AVAX", "crypto"),
    ("LINK", "crypto"),
    ("ARB", "crypto"),
    ("DOGE", "crypto"),
    ("NVDA", "stocks"),
    ("TSLA", "stocks"),
    ("AMD", "stocks"),
    ("AAPL", "stocks"),
    ("MSFT", "stocks"),
]

# ---------------------------------------------------------------------------
# Pydantic Schemas for API Contracts
# ---------------------------------------------------------------------------


class EntitlementBlock(BaseModel):
    tier: str = Field(description="Subscribed tier: 'free' or 'pro'")
    remaining_views: int = Field(
        description="Number of views remaining in the current 24h window"
    )
    reset_at: Optional[datetime.datetime] = Field(
        None, description="ISO timestamp when the view count resets"
    )
    locked: bool = Field(description="True if the user has exhausted their views")
    cooldown_ends_at: Optional[datetime.datetime] = Field(
        None, description="ISO timestamp when cooldown lock expires"
    )


class SignalPayload(BaseModel):
    id: str
    ticker: str
    asset_type: str
    name: Optional[str] = None
    signal_type: str
    confidence: float
    time_horizon: Optional[str] = None
    price_target: Optional[float] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    position_sizing: Optional[str] = None
    reasoning_summary: str
    generated_at: datetime.datetime
    source_run_id: Optional[str] = None
    grade: Optional[str] = None
    rr: Optional[float] = None
    agent_votes: Optional[Dict[str, Any]] = None
    sentiment_score: Optional[float] = None
    sentiment_band: Optional[str] = None


class SignalsResponse(BaseModel):
    signals: List[SignalPayload]
    entitlement: EntitlementBlock


class StatsResponse(BaseModel):
    signals_today: int
    buy_signals: int
    sell_signals: int
    hold_signals: int
    avg_confidence: float
    active_watchlist: int
    win_rate_30d: Optional[float] = None


class TickerStats(BaseModel):
    ticker: str
    asset_type: str
    added_at: datetime.datetime
    signals_count: int
    last_signal_at: Optional[datetime.datetime] = None


class TickersResponse(BaseModel):
    tickers: List[TickerStats]
    entitlement: EntitlementBlock


class HealthResponse(BaseModel):
    status: str
    database: str
    uptime: float
    provider: str
    deep_model: str
    quick_model: str


# ---------------------------------------------------------------------------
# SQLite Database Integration & Connection Helpers
# ---------------------------------------------------------------------------


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Verify that tables exist and initialize schema if needed."""
    conn = get_db_connection()
    try:
        # Check if tables exist, create them if missing (fail-safe bootstrap)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist_tickers (
                ticker VARCHAR(10) PRIMARY KEY,
                asset_type VARCHAR(10) NOT NULL,
                added_at DATETIME NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_signals (
                id VARCHAR(36) PRIMARY KEY,
                ticker VARCHAR(10) NOT NULL,
                asset_type VARCHAR(10) NOT NULL,
                signal_type VARCHAR(20) NOT NULL,
                confidence FLOAT NOT NULL,
                time_horizon VARCHAR(50),
                price_target FLOAT,
                entry_price FLOAT,
                stop_loss FLOAT,
                position_sizing VARCHAR(50),
                reasoning_summary TEXT NOT NULL,
                generated_at DATETIME NOT NULL,
                source_run_id VARCHAR(100),
                name TEXT,
                grade TEXT,
                rr FLOAT,
                agent_votes TEXT,
                sentiment_score FLOAT,
                sentiment_band TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_quota_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(100) NOT NULL,
                viewed_at DATETIME NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(100) NOT NULL,
                ticker VARCHAR(10) NOT NULL,
                asset_type VARCHAR(10) NOT NULL,
                added_at DATETIME NOT NULL,
                UNIQUE(user_id, ticker)
            );
        """)
        # Migrations: add new columns to existing tables (safe — ignored if column exists)
        _new_signal_cols = [
            ("name", "TEXT"),
            ("grade", "TEXT"),
            ("rr", "FLOAT"),
            ("agent_votes", "TEXT"),
            ("sentiment_score", "FLOAT"),
            ("sentiment_band", "TEXT"),
        ]
        for col, col_type in _new_signal_cols:
            try:
                conn.execute(f"ALTER TABLE trading_signals ADD COLUMN {col} {col_type}")
            except Exception:
                pass  # column already exists
        conn.commit()
        logger.info(f"Database successfully verified at: {DB_PATH}")
    except Exception as e:
        logger.error(f"Error initializing signals database: {e}")
    finally:
        conn.close()


# Initialize DB on import/start
init_db()


def seed_global_watchlist():
    """Inserts the 12 canonical tickers into watchlist_tickers if not already present."""
    conn = get_db_connection()
    try:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for ticker, asset_type in GLOBAL_TICKERS:
            conn.execute(
                "INSERT OR IGNORE INTO watchlist_tickers (ticker, asset_type, added_at) VALUES (?, ?, ?)",
                (ticker, asset_type, now),
            )
        conn.commit()
        logger.info("Global watchlist seeded with %d tickers.", len(GLOBAL_TICKERS))
    finally:
        conn.close()


def _yf_symbol(ticker: str, asset_type: str) -> str:
    if asset_type == "crypto" and not ticker.endswith("-USD"):
        return f"{ticker}-USD"
    return ticker


def get_live_price(ticker: str, asset_type: str) -> Optional[float]:
    try:
        sym = _yf_symbol(ticker, asset_type)
        return float(yf.Ticker(sym).fast_info.last_price)
    except Exception:
        return None


def validate_price(
    price: Optional[float], live_price: Optional[float]
) -> Optional[float]:
    if price is None or live_price is None or live_price == 0:
        return price
    ratio = price / live_price
    if ratio > 10 or ratio < 0.1:
        return None
    return price


# ---------------------------------------------------------------------------
# SSE Pub/Sub Hub
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Redis SSE Pub/Sub Hub
# ---------------------------------------------------------------------------


class RedisSSEHub:
    """Broadcasts newly generated signals to Redis channel."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url

    def broadcast(self, signal: Dict[str, Any]):
        try:
            r = redis.from_url(self.redis_url, decode_responses=True)
            r.publish("pulse:trading_signals", json.dumps(signal, default=str))
            logger.info(
                "Successfully published new signal to Redis channel 'pulse:trading_signals'"
            )
        except Exception as e:
            logger.error(f"Failed to publish signal to Redis: {e}")


sse_hub = RedisSSEHub(REDIS_URL)

# Uptime tracker
START_TIME = datetime.datetime.now()

# ---------------------------------------------------------------------------
# Entitlement & Quota Verification Helper
# ---------------------------------------------------------------------------


async def _resolve_identity_from_auth_service(token: str) -> tuple[str, str]:
    """Validates token via auth service and returns (user_id, tier).

    Auth service is the single source of truth — we never trust unverified JWT
    claims. user_id is read from the JWT only AFTER the auth service confirms
    the token is valid (200 OK). Caches (user_id, tier) in Redis for 60s.
    """
    import urllib.error as _ue
    import urllib.request as _ur

    import hashlib

    cache_key = f"identity:{hashlib.sha256(token.encode()).hexdigest()}"
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            user_id, tier = cached.split(":", 1)
            return user_id, tier
    except Exception:
        pass

    # Call auth service — this validates the token signature
    try:
        req = _ur.Request(
            f"{AUTH_SERVICE_URL}/auth-ms/me/entitlements",
            headers={"Authorization": f"Bearer {token}"},
        )
        with _ur.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        tier = "pro" if data.get("is_pro") else "free"
    except _ue.HTTPError as e:
        if e.code == 401:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        # Auth service unreachable — fail closed, don't grant access
        raise HTTPException(status_code=503, detail="Auth service unavailable")
    except Exception:
        raise HTTPException(status_code=503, detail="Auth service unavailable")

    # Token is now confirmed valid — safe to read sub from JWT
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        user_id = str(payload.get("sub") or payload.get("user_id") or "")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID missing from token")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Malformed token")

    try:
        await redis_client.setex(cache_key, 60, f"{user_id}:{tier}")
    except Exception:
        pass

    return user_id, tier


async def get_user_claims_async(request: Request) -> tuple[str, str]:
    """Validates bearer token via auth service and returns (user_id, tier)."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")
    return await _resolve_identity_from_auth_service(auth[7:])


def get_user_claims(request: Request) -> tuple[str, str]:
    """Sync fallback for non-quota paths (SSE stream). Does not resolve tier."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return "anonymous", "free"
    try:
        payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return str(payload.get("sub") or "anonymous"), "free"
    except Exception:
        return "anonymous", "free"


def enforce_quota(user_id: str, tier: str, log_view: bool = False) -> EntitlementBlock:
    """Checks the user views quota against the DB and optionally logs a new view."""
    if tier == "pro":
        return EntitlementBlock(tier="pro", remaining_views=999999, locked=False)

    # Free Tier quota check: 3 views per 24 hours (configurable via environment)
    limit = int(os.getenv("FREE_TIER_QUOTA_LIMIT", "3"))
    now = datetime.datetime.now()
    twenty_four_hours_ago = now - datetime.timedelta(hours=24)

    conn = get_db_connection()
    try:
        # Fetch views count in last 24 hours
        cursor = conn.execute(
            "SELECT COUNT(*) as cnt FROM user_quota_logs WHERE user_id = ? AND viewed_at >= ?",
            (user_id, twenty_four_hours_ago.strftime("%Y-%m-%d %H:%M:%S")),
        )
        count = cursor.fetchone()["cnt"]

        # Fetch oldest log in the active 24h window to calculate cooldown reset
        cursor = conn.execute(
            "SELECT viewed_at FROM user_quota_logs WHERE user_id = ? AND viewed_at >= ? ORDER BY viewed_at ASC LIMIT 1",
            (user_id, twenty_four_hours_ago.strftime("%Y-%m-%d %H:%M:%S")),
        )
        oldest_row = cursor.fetchone()

        reset_at = None
        cooldown_ends_at = None

        if oldest_row:
            oldest_time = datetime.datetime.strptime(
                oldest_row["viewed_at"], "%Y-%m-%d %H:%M:%S"
            )
            reset_at = oldest_time + datetime.timedelta(hours=24)
            cooldown_ends_at = reset_at

        locked = count >= limit

        if not locked and log_view:
            conn.execute(
                "INSERT INTO user_quota_logs (user_id, viewed_at) VALUES (?, ?)",
                (user_id, now.strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
            count += 1
            locked = count >= limit

        remaining_views = max(0, limit - count)
        return EntitlementBlock(
            tier="free",
            remaining_views=remaining_views,
            reset_at=reset_at,
            locked=locked,
            cooldown_ends_at=cooldown_ends_at if locked else None,
        )
    finally:
        conn.close()


def mask_signal(signal: SignalPayload) -> SignalPayload:
    """Masks all proprietary recommendation and reasoning details for locked Free users."""
    return SignalPayload(
        id=signal.id,
        ticker=signal.ticker,
        asset_type=signal.asset_type,
        name=signal.name,
        signal_type="locked",
        confidence=0.0,
        time_horizon="Locked",
        price_target=None,
        entry_price=None,
        stop_loss=None,
        position_sizing="Locked",
        reasoning_summary="Upgrade to Pro to view this trading signal details.",
        generated_at=signal.generated_at,
        source_run_id=None,
        grade=None,
        rr=None,
        agent_votes=None,
        sentiment_score=None,
        sentiment_band=None,
    )


# ---------------------------------------------------------------------------
# Signal Normalization Helpers
# ---------------------------------------------------------------------------


def parse_markdown_fields(text: str) -> Dict[str, str]:
    """Extract key-value fields from agent rendered markdown."""
    fields = {}
    current_key = None
    current_value = []

    for line in text.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue
        m = re.match(r"\*\*([^*]+)\*\*:\s*(.*)", line_stripped)
        if m:
            if current_key:
                fields[current_key] = "\n".join(current_value).strip()
            current_key = m.group(1).strip().lower().replace(" ", "_")
            val = m.group(2).strip()
            current_value = [val] if val else []
        else:
            if current_key:
                current_value.append(line_stripped)

    if current_key:
        fields[current_key] = "\n".join(current_value).strip()

    return fields


def _extract_sentiment(sentiment_report: str) -> tuple:
    """Parse sentiment band and score from rendered SentimentReport markdown.
    Format: **Overall Sentiment:** **Bullish** (Score: 7.2/10)
    """
    m = re.search(
        r"\*\*Overall Sentiment:\*\*\s+\*\*([^*]+)\*\*.*?Score:\s*([\d.]+)",
        sentiment_report,
    )
    if m:
        band = m.group(1).strip()
        try:
            score = float(m.group(2))
        except Exception:
            score = None
        return band, score
    return None, None


def _vote_from_keywords(text: str, default_vote: str) -> tuple:
    """Derive vote (bullish/bearish/neutral) and score (0-100) from report text."""
    t = text.lower()
    bull = sum(
        t.count(w)
        for w in ["bullish", "buy", "overweight", "upside", "positive", "outperform"]
    )
    bear = sum(
        t.count(w)
        for w in [
            "bearish",
            "sell",
            "underweight",
            "downside",
            "negative",
            "underperform",
        ]
    )
    if bull > bear:
        return "bullish", min(90, 50 + bull * 5)
    if bear > bull:
        return "bearish", min(90, 50 + bear * 5)
    return default_vote, 50


def _compute_rr(
    signal_type: str,
    entry: Optional[float],
    target: Optional[float],
    stop: Optional[float],
) -> Optional[float]:
    if entry is None or target is None or stop is None:
        return None
    if signal_type in ("buy", "overweight"):
        denom = entry - stop
        return round((target - entry) / denom, 2) if denom > 0 else None
    if signal_type in ("sell", "underweight"):
        denom = stop - entry
        return round((entry - target) / denom, 2) if denom > 0 else None
    return None


def _compute_grade(confidence: float) -> str:
    if confidence >= 0.85:
        return "A"
    if confidence >= 0.70:
        return "B"
    if confidence >= 0.55:
        return "C"
    return "D"


def normalize_signal(
    ticker: str, asset_type: str, final_state: Dict[str, Any]
) -> Dict[str, Any]:
    """Transforms raw multi-agent final state output into a canonical signal payload."""
    pm_decision_text = final_state.get("final_trade_decision", "")
    trader_plan_text = final_state.get("trader_investment_plan", "")
    sentiment_report = final_state.get("sentiment_report", "")
    market_report = final_state.get("market_report", "")
    fundamentals_report = final_state.get("fundamentals_report", "")
    risk_debate = final_state.get("risk_debate_state", {})
    risk_judge = (
        risk_debate.get("judge_decision", "") if isinstance(risk_debate, dict) else ""
    )

    # Parse rating (Buy, Overweight, Hold, Underweight, Sell)
    rating = parse_rating(pm_decision_text).lower()

    # Parse PM fields (price_target, time_horizon, executive_summary)
    pm_fields = parse_markdown_fields(pm_decision_text)

    # Parse Trader fields (entry_price, stop_loss, position_sizing)
    trader_fields = parse_markdown_fields(trader_plan_text)

    # Fetch live price for magnitude validation
    live_price = get_live_price(ticker, asset_type)

    # Extract and validate prices
    price_target = None
    if pm_fields.get("price_target"):
        try:
            price_target = validate_price(
                float(re.findall(r"[\d\.]+", pm_fields["price_target"])[0]), live_price
            )
        except Exception:
            pass

    entry_price = None
    if trader_fields.get("entry_price"):
        try:
            entry_price = validate_price(
                float(re.findall(r"[\d\.]+", trader_fields["entry_price"])[0]),
                live_price,
            )
        except Exception:
            pass

    stop_loss = None
    if trader_fields.get("stop_loss"):
        try:
            stop_loss = validate_price(
                float(re.findall(r"[\d\.]+", trader_fields["stop_loss"])[0]), live_price
            )
        except Exception:
            pass

    # Fall back to live price as entry if LLM price failed validation
    if entry_price is None and live_price is not None:
        entry_price = round(live_price, 2)

    time_horizon = pm_fields.get("time_horizon")
    position_sizing = trader_fields.get("position_sizing")
    reasoning_summary = (
        pm_fields.get("executive_summary")
        or pm_fields.get("investment_thesis")
        or "Thesis generated by Portfolio Manager."
    )

    # Confidence: decisiveness + PM/Trader alignment
    base_confidence = 0.4
    if rating in ("buy", "sell"):
        base_confidence = 0.8
    elif rating in ("overweight", "underweight"):
        base_confidence = 0.6

    trader_action = trader_fields.get("action", "").lower()
    alignment_boost = 0.0
    if (
        (rating in ("buy", "overweight") and trader_action == "buy")
        or (rating in ("sell", "underweight") and trader_action == "sell")
        or (rating == "hold" and trader_action == "hold")
    ):
        alignment_boost = 0.15

    confidence = min(0.98, max(0.1, base_confidence + alignment_boost))

    # Sentiment from structured report
    sentiment_band, sentiment_score = _extract_sentiment(sentiment_report)

    # Agent votes derived from each report's keyword density
    default_vote = (
        "bullish"
        if rating in ("buy", "overweight")
        else ("bearish" if rating in ("sell", "underweight") else "neutral")
    )
    tech_vote, tech_score = _vote_from_keywords(market_report, default_vote)
    fund_vote, fund_score = _vote_from_keywords(fundamentals_report, default_vote)
    risk_vote, risk_score = _vote_from_keywords(risk_judge, default_vote)

    if sentiment_band:
        band_lower = sentiment_band.lower()
        sent_vote = (
            "bullish"
            if "bullish" in band_lower
            else ("bearish" if "bearish" in band_lower else "neutral")
        )
        sent_score = round((sentiment_score / 10) * 100) if sentiment_score else 50
    else:
        sent_vote, sent_score = default_vote, 50

    agent_votes = {
        "fundamental": {"vote": fund_vote, "score": fund_score},
        "technical": {"vote": tech_vote, "score": tech_score},
        "sentiment": {"vote": sent_vote, "score": sent_score},
        "risk": {"vote": risk_vote, "score": risk_score},
    }

    rr = _compute_rr(rating, entry_price, price_target, stop_loss)
    grade = _compute_grade(confidence)
    display_ticker = ticker.upper().replace("-USD", "")
    name = TICKER_NAMES.get(display_ticker, display_ticker)

    return {
        "id": str(uuid.uuid4()),
        "ticker": ticker.upper(),
        "asset_type": asset_type.lower(),
        "name": name,
        "signal_type": rating,
        "confidence": round(confidence, 2),
        "time_horizon": time_horizon,
        "price_target": price_target,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "position_sizing": position_sizing,
        "reasoning_summary": reasoning_summary,
        "generated_at": datetime.datetime.now(),
        "source_run_id": str(uuid.uuid4()),
        "grade": grade,
        "rr": rr,
        "agent_votes": agent_votes,
        "sentiment_score": sentiment_score,
        "sentiment_band": sentiment_band,
    }


# ---------------------------------------------------------------------------
# Background Agent Runner & Scheduler Thread
# ---------------------------------------------------------------------------


class SignalScheduler:
    """Manages watchlist execution cadence and invokes TradingAgentsGraph."""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._running = False
        # default cadence: check every 60s, run tickers if last run is > 24 hours (1440 mins)
        self.check_interval_seconds = int(
            os.getenv("TRADING_SIGNALS_CHECK_INTERVAL_SECONDS", "60")
        )
        self.run_cadence_hours = int(os.getenv("TRADING_SIGNALS_CADENCE_HOURS", "24"))

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("SignalScheduler background thread started.")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self):
        while self._running:
            try:
                self.run_scheduler_cycle()
            except Exception as e:
                logger.error(f"Error in scheduler execution loop: {e}")

            # Sleep in increments so we can exit quickly
            for _ in range(self.check_interval_seconds):
                if not self._running:
                    break
                # Synchronous sleep inside thread
                import time

                time.sleep(1)

    def run_scheduler_cycle(self, force_ticker: Optional[str] = None):
        """Checks the watchlist and executes TradingAgents run if needed."""
        conn = get_db_connection()
        tickers = []
        try:
            if force_ticker:
                cursor = conn.execute(
                    "SELECT ticker, asset_type FROM watchlist_tickers WHERE ticker = ?",
                    (force_ticker.upper(),),
                )
                row = cursor.fetchone()
                if row:
                    tickers = [dict(row)]
            else:
                cursor = conn.execute(
                    "SELECT ticker, asset_type FROM watchlist_tickers"
                )
                tickers = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

        for t_info in tickers:
            ticker = t_info["ticker"]
            asset_type = t_info["asset_type"]

            # Check latest signal in DB
            conn = get_db_connection()
            run_needed = True
            try:
                cursor = conn.execute(
                    "SELECT generated_at, signal_type, reasoning_summary FROM trading_signals WHERE ticker = ? ORDER BY generated_at DESC LIMIT 1",
                    (ticker,),
                )
                latest_sig = cursor.fetchone()
                if latest_sig:
                    last_run_time = datetime.datetime.strptime(
                        latest_sig["generated_at"],
                        "%Y-%m-%d %H:%M:%S"
                        if "." not in latest_sig["generated_at"]
                        else "%Y-%m-%d %H:%M:%S.%f",
                    )
                    if not force_ticker and (
                        datetime.datetime.now() - last_run_time
                    ) < datetime.timedelta(hours=self.run_cadence_hours):
                        run_needed = False
            finally:
                conn.close()

            if run_needed:
                logger.info(f"Triggering TradingAgents run for ticker: {ticker}")
                try:
                    self.execute_agent_run(ticker, asset_type, latest_sig)
                except Exception as e:
                    logger.error(f"Failed analysis run for {ticker}: {e}")

    def execute_agent_run(
        self, ticker: str, asset_type: str, latest_sig: Optional[sqlite3.Row] = None
    ):
        """Initializes and runs the multi-agent graph, then saves and broadcasts the signal."""
        # Initialize graph using DEFAULT_CONFIG + Environment
        config = DEFAULT_CONFIG.copy()

        # Override output_language for normalized parsing
        config["output_language"] = "English"

        # Instantiate graph (disable debug prints to prevent stdout noise in logs)
        graph = TradingAgentsGraph(config=config, debug=False)

        # Run propagate for current date
        trade_date = datetime.datetime.now().strftime("%Y-%m-%d")
        final_state, decision = graph.propagate(
            ticker, trade_date, asset_type=asset_type
        )

        # Normalize outputs to canonical schema
        signal_dict = normalize_signal(ticker, asset_type, final_state)

        # Deduplication check: Ticker + Signal Type + Reasoning within 24h
        if latest_sig:
            if (
                latest_sig["signal_type"] == signal_dict["signal_type"]
                and latest_sig["reasoning_summary"] == signal_dict["reasoning_summary"]
            ):
                logger.info(
                    f"Skipping duplicate signal insert for {ticker} (thesis unchanged)."
                )
                return

        # Save to DB
        conn = get_db_connection()
        try:
            conn.execute(
                """
                INSERT INTO trading_signals (
                    id, ticker, asset_type, signal_type, confidence, time_horizon,
                    price_target, entry_price, stop_loss, position_sizing,
                    reasoning_summary, generated_at, source_run_id,
                    name, grade, rr, agent_votes, sentiment_score, sentiment_band
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_dict["id"],
                    signal_dict["ticker"],
                    signal_dict["asset_type"],
                    signal_dict["signal_type"],
                    signal_dict["confidence"],
                    signal_dict["time_horizon"],
                    signal_dict["price_target"],
                    signal_dict["entry_price"],
                    signal_dict["stop_loss"],
                    signal_dict["position_sizing"],
                    signal_dict["reasoning_summary"],
                    signal_dict["generated_at"].strftime("%Y-%m-%d %H:%M:%S.%f"),
                    signal_dict["source_run_id"],
                    signal_dict.get("name"),
                    signal_dict.get("grade"),
                    signal_dict.get("rr"),
                    json.dumps(signal_dict.get("agent_votes"))
                    if signal_dict.get("agent_votes")
                    else None,
                    signal_dict.get("sentiment_score"),
                    signal_dict.get("sentiment_band"),
                ),
            )
            conn.commit()
            logger.info(
                f"New signal successfully generated & saved for {ticker}: {signal_dict['signal_type'].upper()}"
            )
        finally:
            conn.close()

        # Broadcast real-time signal via SSE pub/sub
        sse_hub.broadcast(signal_dict)


scheduler = SignalScheduler()

# ---------------------------------------------------------------------------
# FastAPI Lifespan & App Setup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_global_watchlist()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(
    title="Pulse Trading Signals Microservice",
    description="Standalone signals microservice wrapping the TradingAgents multi-agent framework.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def root_redirect():
    """Redirects base requests to the interactive Swagger documentation."""
    return RedirectResponse(url="/docs")


def _row_to_signal(row) -> SignalPayload:
    """Convert a DB row to SignalPayload, handling new optional columns."""
    gen_at_str = row["generated_at"]
    fmt = "%Y-%m-%d %H:%M:%S" if "." not in gen_at_str else "%Y-%m-%d %H:%M:%S.%f"
    gen_at = datetime.datetime.strptime(gen_at_str, fmt)

    agent_votes = None
    try:
        if row["agent_votes"]:
            agent_votes = json.loads(row["agent_votes"])
    except Exception:
        pass

    # Backfill name from TICKER_NAMES if DB column is empty
    name = (
        row["name"]
        if row["name"]
        else TICKER_NAMES.get(row["ticker"].replace("-USD", ""), row["ticker"])
    )

    return SignalPayload(
        id=row["id"],
        ticker=row["ticker"],
        asset_type=row["asset_type"],
        name=name,
        signal_type=row["signal_type"],
        confidence=row["confidence"],
        time_horizon=row["time_horizon"],
        price_target=row["price_target"],
        entry_price=row["entry_price"],
        stop_loss=row["stop_loss"],
        position_sizing=row["position_sizing"],
        reasoning_summary=row["reasoning_summary"],
        generated_at=gen_at,
        source_run_id=row["source_run_id"],
        grade=row["grade"],
        rr=row["rr"],
        agent_votes=agent_votes,
        sentiment_score=row["sentiment_score"],
        sentiment_band=row["sentiment_band"],
    )


# CORS configuration to connect with the dashboard frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this to Pulse frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@app.get("/signals-ms/signals", response_model=SignalsResponse)
async def get_signals_feed(
    request: Request,
    ticker: Optional[str] = Query(None, description="Filter by ticker (e.g. AAPL)"),
    signal_type: Optional[str] = Query(
        None, description="Filter by signal (buy/sell/hold)"
    ),
    start_date: Optional[str] = Query(
        None, description="Filter by start ISO date (YYYY-MM-DD)"
    ),
    end_date: Optional[str] = Query(
        None, description="Filter by end ISO date (YYYY-MM-DD)"
    ),
    limit: int = Query(20, ge=1, le=100, description="Pagination limit"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """Retrieves paginated signal feed, enforcing Free user view quotas."""
    user_id, tier = await get_user_claims_async(request)

    # Check current quota and increment view log if not locked
    entitlement = enforce_quota(user_id, tier, log_view=True)

    conn = get_db_connection()
    try:
        # Build query
        query_parts = ["SELECT * FROM trading_signals WHERE 1=1"]
        params = []

        if ticker:
            query_parts.append("AND ticker = ?")
            params.append(ticker.upper())
        if signal_type:
            query_parts.append("AND signal_type = ?")
            params.append(signal_type.lower())
        if start_date:
            query_parts.append("AND generated_at >= ?")
            params.append(start_date)
        if end_date:
            query_parts.append("AND generated_at <= ?")
            params.append(end_date)

        query_parts.append("ORDER BY generated_at DESC LIMIT ? OFFSET ?")
        params.extend([limit, offset])

        cursor = conn.execute(" ".join(query_parts), tuple(params))
        rows = cursor.fetchall()

        signals = []
        for row in rows:
            sig = _row_to_signal(row)
            if entitlement.locked:
                sig = mask_signal(sig)
            signals.append(sig)

        return SignalsResponse(signals=signals, entitlement=entitlement)
    finally:
        conn.close()


@app.get("/signals-ms/signals/latest", response_model=SignalsResponse)
async def get_latest_signals(request: Request):
    """Retrieves the most recent signal for each tracked ticker."""
    user_id, tier = await get_user_claims_async(request)
    entitlement = enforce_quota(user_id, tier, log_view=True)

    conn = get_db_connection()
    try:
        query = """
            SELECT s1.* FROM trading_signals s1
            INNER JOIN (
                SELECT ticker, MAX(generated_at) as max_gen
                FROM trading_signals
                GROUP BY ticker
            ) s2 ON s1.ticker = s2.ticker AND s1.generated_at = s2.max_gen
            ORDER BY s1.ticker ASC
        """
        cursor = conn.execute(query)
        rows = cursor.fetchall()

        signals = []
        for row in rows:
            sig = _row_to_signal(row)
            if entitlement.locked:
                sig = mask_signal(sig)
            signals.append(sig)

        return SignalsResponse(signals=signals, entitlement=entitlement)
    finally:
        conn.close()


@app.get("/signals-ms/tickers", response_model=TickersResponse)
async def get_tracked_tickers(request: Request):
    """Retrieves the list of tracked tickers on the watchlist with basic execution statistics."""
    user_id, tier = await get_user_claims_async(request)
    entitlement = enforce_quota(
        user_id, tier, log_view=False
    )  # viewing tickers metadata doesn't burn view log

    conn = get_db_connection()
    try:
        query = """
            SELECT w.ticker, w.asset_type, w.added_at,
                   COUNT(s.id) as signals_count, MAX(s.generated_at) as last_signal_at
            FROM watchlist_tickers w
            LEFT JOIN trading_signals s ON w.ticker = s.ticker
            GROUP BY w.ticker
            ORDER BY w.ticker ASC
        """
        cursor = conn.execute(query)
        rows = cursor.fetchall()

        tickers = []
        for row in rows:
            # Parse Added Date
            added_at_str = row["added_at"]
            fmt_added = (
                "%Y-%m-%d %H:%M:%S"
                if "." not in added_at_str
                else "%Y-%m-%d %H:%M:%S.%f"
            )
            added_at = datetime.datetime.strptime(added_at_str, fmt_added)

            # Parse Last Signal Date
            last_signal_at = None
            if row["last_signal_at"]:
                last_sig_str = row["last_signal_at"]
                fmt_sig = (
                    "%Y-%m-%d %H:%M:%S"
                    if "." not in last_sig_str
                    else "%Y-%m-%d %H:%M:%S.%f"
                )
                last_signal_at = datetime.datetime.strptime(last_sig_str, fmt_sig)

            tickers.append(
                TickerStats(
                    ticker=row["ticker"],
                    asset_type=row["asset_type"],
                    added_at=added_at,
                    signals_count=row["signals_count"],
                    last_signal_at=last_signal_at,
                )
            )

        return TickersResponse(tickers=tickers, entitlement=entitlement)
    finally:
        conn.close()


# Pydantic schema for adding a ticker
class WatchlistAddPayload(BaseModel):
    ticker: str = Field(..., description="Ticker symbol to track (e.g., MSFT, ETH-USD)")
    asset_type: str = Field("stocks", description="Asset type: 'stocks' or 'crypto'")


@app.post("/signals-ms/tickers", status_code=201)
def add_watchlist_ticker(payload: WatchlistAddPayload):
    """Adds a ticker to the watchlist database table."""
    ticker_upper = payload.ticker.strip().upper()
    asset_type = payload.asset_type.strip().lower()

    if asset_type not in ("stocks", "crypto"):
        raise HTTPException(
            status_code=400, detail="asset_type must be either 'stocks' or 'crypto'"
        )

    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist_tickers (ticker, asset_type, added_at) VALUES (?, ?, ?)",
            (
                ticker_upper,
                asset_type,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
        logger.info(f"Watchlist: added ticker {ticker_upper} ({asset_type})")
        return {
            "status": "success",
            "message": f"Ticker {ticker_upper} added to watchlist.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.delete("/signals-ms/tickers/{ticker}")
def delete_watchlist_ticker(ticker: str):
    """Removes a ticker from the watchlist database table."""
    ticker_upper = ticker.strip().upper()
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM watchlist_tickers WHERE ticker = ?", (ticker_upper,)
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404, detail=f"Ticker {ticker_upper} not found in watchlist."
            )
        logger.info(f"Watchlist: deleted ticker {ticker_upper}")
        return {
            "status": "success",
            "message": f"Ticker {ticker_upper} removed from watchlist.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/signals-ms/stream")
async def sse_live_stream(
    request: Request,
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
):
    """SSE real-time stream. Sends newly generated trading signals immediately (supports Pro and Free tiers)."""
    # 1. JWT verification on SSE connection establishment (reject 401 before stream opens)
    jwt_token = None
    if authorization and authorization.startswith("Bearer "):
        jwt_token = authorization[7:]
    elif token:
        jwt_token = token

    if not jwt_token:
        raise HTTPException(status_code=401, detail="Authentication token required")

    user_id, tier = await _resolve_identity_from_auth_service(jwt_token)

    # 2. Check entitlement on connect
    entitlement = enforce_quota(user_id, tier, log_view=False)
    if entitlement.locked:
        # If quota is exhausted, send a quota_exhausted event and close the stream
        async def quota_exhausted_generator():
            data = {
                "tier": entitlement.tier,
                "remaining_views": entitlement.remaining_views,
                "reset_at": entitlement.reset_at.isoformat()
                if entitlement.reset_at
                else None,
                "locked": entitlement.locked,
                "cooldown_ends_at": entitlement.cooldown_ends_at.isoformat()
                if entitlement.cooldown_ends_at
                else None,
            }
            yield f"event: quota_exhausted\ndata: {json.dumps(data)}\n\n"

        return StreamingResponse(
            quota_exhausted_generator(), media_type="text/event-stream"
        )

    # 3. Replace in-memory broadcast hub with a Redis pub/sub backend
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("pulse:trading_signals")

    async def event_generator():
        last_heartbeat = time.time()
        try:
            # Send initial connection event
            yield "event: connection\ndata: Connected to real-time signals stream\n\n"

            while True:
                # Disconnect if client leaves
                if await request.is_disconnected():
                    break

                try:
                    # Read from Redis pubsub with timeout
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                    if message:
                        data = message["data"]
                        signal = json.loads(data)

                        # Format generated_at back to string
                        if "generated_at" in signal and isinstance(
                            signal["generated_at"], datetime.datetime
                        ):
                            signal["generated_at"] = signal["generated_at"].isoformat()

                        # 4. Check entitlement on message
                        if tier == "free":
                            current_entitlement = enforce_quota(
                                user_id, tier, log_view=False
                            )
                            if current_entitlement.locked:
                                data = {
                                    "tier": current_entitlement.tier,
                                    "remaining_views": current_entitlement.remaining_views,
                                    "reset_at": current_entitlement.reset_at.isoformat()
                                    if current_entitlement.reset_at
                                    else None,
                                    "locked": current_entitlement.locked,
                                    "cooldown_ends_at": current_entitlement.cooldown_ends_at.isoformat()
                                    if current_entitlement.cooldown_ends_at
                                    else None,
                                }
                                yield f"event: quota_exhausted\ndata: {json.dumps(data)}\n\n"
                                break

                            # Yield signal to user
                            yield f"event: signal\ndata: {json.dumps(signal)}\n\n"

                            # Consume the view quota
                            current_entitlement = enforce_quota(
                                user_id, tier, log_view=True
                            )
                            if current_entitlement.locked:
                                data = {
                                    "tier": current_entitlement.tier,
                                    "remaining_views": current_entitlement.remaining_views,
                                    "reset_at": current_entitlement.reset_at.isoformat()
                                    if current_entitlement.reset_at
                                    else None,
                                    "locked": current_entitlement.locked,
                                    "cooldown_ends_at": current_entitlement.cooldown_ends_at.isoformat()
                                    if current_entitlement.cooldown_ends_at
                                    else None,
                                }
                                yield f"event: quota_exhausted\ndata: {json.dumps(data)}\n\n"
                                break
                        else:
                            # Pro tier gets unlimited stream signals
                            yield f"event: signal\ndata: {json.dumps(signal)}\n\n"
                    else:
                        # Heartbeat keep-alive every 20 seconds
                        if time.time() - last_heartbeat > 20:
                            yield "event: heartbeat\ndata: ping\n\n"
                            last_heartbeat = time.time()
                except Exception as e:
                    logger.error(f"Error in SSE stream generator: {e}")
                    yield "event: error\ndata: Internal stream processing error\n\n"
                    break
        finally:
            await pubsub.unsubscribe("pulse:trading_signals")
            await pubsub.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/signals-ms/stats", response_model=StatsResponse)
async def get_signals_stats(request: Request):
    """Dashboard summary stats: signals today, buy/sell/hold counts, avg confidence, active watchlist."""
    await get_user_claims_async(request)  # auth required but no quota cost

    today = datetime.datetime.now().date().isoformat()
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "SELECT signal_type, confidence FROM trading_signals WHERE generated_at >= ?",
            (today,),
        )
        rows = cursor.fetchall()

        signals_today = len(rows)
        buy_signals = sum(1 for r in rows if r["signal_type"] in ("buy", "overweight"))
        sell_signals = sum(
            1 for r in rows if r["signal_type"] in ("sell", "underweight")
        )
        hold_signals = sum(1 for r in rows if r["signal_type"] == "hold")
        avg_confidence = (
            round(sum(r["confidence"] for r in rows) / signals_today, 2)
            if signals_today
            else 0.0
        )

        active_watchlist = conn.execute(
            "SELECT COUNT(*) as cnt FROM watchlist_tickers"
        ).fetchone()["cnt"]
    finally:
        conn.close()

    return StatsResponse(
        signals_today=signals_today,
        buy_signals=buy_signals,
        sell_signals=sell_signals,
        hold_signals=hold_signals,
        avg_confidence=avg_confidence,
        active_watchlist=active_watchlist,
    )


@app.get("/signals-ms/watchlist")
async def get_user_watchlist(request: Request):
    """Returns the authenticated user's personal watchlist."""
    user_id, _ = await get_user_claims_async(request)
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT ticker, asset_type, added_at FROM user_watchlist WHERE user_id = ? ORDER BY added_at DESC",
            (user_id,),
        ).fetchall()
        return {"watchlist": [dict(r) for r in rows]}
    finally:
        conn.close()


class UserWatchlistPayload(BaseModel):
    ticker: str
    asset_type: str = "stocks"


@app.post("/signals-ms/watchlist", status_code=201)
async def add_to_user_watchlist(payload: UserWatchlistPayload, request: Request):
    """Adds a ticker to the authenticated user's personal watchlist."""
    user_id, _ = await get_user_claims_async(request)
    ticker = payload.ticker.strip().upper()
    asset_type = payload.asset_type.strip().lower()
    if asset_type not in ("stocks", "crypto"):
        raise HTTPException(
            status_code=400, detail="asset_type must be 'stocks' or 'crypto'"
        )
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO user_watchlist (user_id, ticker, asset_type, added_at) VALUES (?, ?, ?, ?)",
            (
                user_id,
                ticker,
                asset_type,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
        return {"status": "success", "ticker": ticker}
    finally:
        conn.close()


@app.delete("/signals-ms/watchlist/{ticker}")
async def remove_from_user_watchlist(ticker: str, request: Request):
    """Removes a ticker from the authenticated user's personal watchlist."""
    user_id, _ = await get_user_claims_async(request)
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM user_watchlist WHERE user_id = ? AND ticker = ?",
            (user_id, ticker.upper()),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404, detail=f"{ticker.upper()} not in your watchlist"
            )
        return {"status": "success"}
    finally:
        conn.close()


@app.post("/signals-ms/analyze")
async def analyze_on_demand(
    request: Request,
    background_tasks: BackgroundTasks,
    ticker: str = Query(..., description="Ticker to analyze (e.g. AAPL, BTC)"),
    asset_type: str = Query("stocks", description="'stocks' or 'crypto'"),
):
    """Triggers an immediate on-demand signal generation for any ticker (Pro only)."""
    user_id, tier = await get_user_claims_async(request)
    if tier != "pro":
        raise HTTPException(
            status_code=403, detail="On-demand analysis requires Pro tier"
        )
    ticker_upper = ticker.strip().upper()
    background_tasks.add_task(
        scheduler.execute_agent_run, ticker_upper, asset_type.lower(), None
    )
    return {"status": "triggered", "ticker": ticker_upper, "asset_type": asset_type}


@app.get("/signals-ms/health", response_model=HealthResponse)
def get_service_health():
    """Service health check detailing active models and DB connection."""
    # Check DB connection
    database_status = "connected"
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
    except Exception:
        database_status = "error"

    uptime_seconds = (datetime.datetime.now() - START_TIME).total_seconds()

    return HealthResponse(
        status="healthy",
        database=database_status,
        uptime=round(uptime_seconds, 2),
        provider=DEFAULT_CONFIG.get("llm_provider", "openai"),
        deep_model=DEFAULT_CONFIG.get("deep_think_llm", ""),
        quick_model=DEFAULT_CONFIG.get("quick_think_llm", ""),
    )


@app.post("/signals-ms/generate")
def force_generate_signals(
    background_tasks: BackgroundTasks,
    ticker: Optional[str] = Query(
        None, description="Force generation for a specific ticker"
    ),
):
    """Triggers the background execution of the TradingAgents analysis immediately."""
    background_tasks.add_task(scheduler.run_scheduler_cycle, ticker)
    return {
        "status": "triggered",
        "message": f"Signal generation cycle started for: {ticker or 'all watchlist tickers'}.",
    }
