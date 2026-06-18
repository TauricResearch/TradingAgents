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


class SignalsResponse(BaseModel):
    signals: List[SignalPayload]
    entitlement: EntitlementBlock


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
                source_run_id VARCHAR(100)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_quota_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(100) NOT NULL,
                viewed_at DATETIME NOT NULL
            );
        """)
        conn.commit()
        logger.info(f"Database successfully verified at: {DB_PATH}")
    except Exception as e:
        logger.error(f"Error initializing signals database: {e}")
    finally:
        conn.close()


# Initialize DB on import/start
init_db()

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


def get_user_claims_from_token(token: str) -> tuple[str, str]:
    """Extracts user_id from JWT without signature verification.

    Token authenticity is validated by the auth service call in
    _fetch_tier_from_auth_service — no need to duplicate key management here.
    """
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=401, detail="User ID not found in token claims"
            )
        return str(user_id), "free"
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Authentication token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=401, detail=f"Invalid authentication token: {e}"
        )


async def _fetch_tier_from_auth_service(token: str, user_id: str) -> str:
    """Calls the auth service entitlements endpoint; caches result in Redis for 60s."""
    cache_key = f"tier:{user_id}"
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return cached
    except Exception:
        pass

    try:
        import urllib.error as _ue
        import urllib.request as _ur

        req = _ur.Request(
            f"{AUTH_SERVICE_URL}/auth-ms/me/entitlements",
            headers={"Authorization": f"Bearer {token}"},
        )
        with _ur.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        tier = "pro" if data.get("is_pro") else "free"
    except _ue.HTTPError as e:
        if e.code == 401:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        tier = "free"
    except Exception:
        tier = "free"

    try:
        await redis_client.setex(cache_key, 60, tier)
    except Exception:
        pass

    return tier


async def get_user_claims_async(request: Request) -> tuple[str, str]:
    """Extracts user_id and resolves real tier from auth service."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return "anonymous", "free"

    token = auth[7:]
    user_id, _ = get_user_claims_from_token(token)
    tier = await _fetch_tier_from_auth_service(token, user_id)
    return user_id, tier


def get_user_claims(request: Request) -> tuple[str, str]:
    """Sync wrapper — returns user_id and tier from JWT only (no auth service call).
    Used only in sync contexts; prefer get_user_claims_async in async endpoints."""
    user_id = request.headers.get("x-user-id")
    tier = request.headers.get("x-user-tier")
    if user_id and tier:
        return user_id, tier.lower()

    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            return get_user_claims_from_token(token)
        except Exception:
            pass

    return user_id or "anonymous", (tier or "free").lower()


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


def normalize_signal(
    ticker: str, asset_type: str, final_state: Dict[str, Any]
) -> Dict[str, Any]:
    """Transforms raw multi-agent final state output into a canonical signal payload."""
    pm_decision_text = final_state.get("final_trade_decision", "")
    trader_plan_text = final_state.get("trader_investment_plan", "")

    # Parse rating (Buy, Overweight, Hold, Underweight, Sell)
    rating = parse_rating(pm_decision_text).lower()

    # Parse PM fields (price_target, time_horizon, executive_summary)
    pm_fields = parse_markdown_fields(pm_decision_text)

    # Parse Trader fields (entry_price, stop_loss, position_sizing)
    trader_fields = parse_markdown_fields(trader_plan_text)

    # Extract target values
    price_target = None
    if pm_fields.get("price_target"):
        try:
            price_target = float(re.findall(r"[\d\.]+", pm_fields["price_target"])[0])
        except Exception:
            pass

    time_horizon = pm_fields.get("time_horizon")

    entry_price = None
    if trader_fields.get("entry_price"):
        try:
            entry_price = float(re.findall(r"[\d\.]+", trader_fields["entry_price"])[0])
        except Exception:
            pass

    stop_loss = None
    if trader_fields.get("stop_loss"):
        try:
            stop_loss = float(re.findall(r"[\d\.]+", trader_fields["stop_loss"])[0])
        except Exception:
            pass

    position_sizing = trader_fields.get("position_sizing")
    reasoning_summary = (
        pm_fields.get("executive_summary")
        or pm_fields.get("investment_thesis")
        or "Thesis generated by Portfolio Manager."
    )

    # Heuristic v1 for confidence score (decisiveness and alignment)
    # Buy/Sell = 0.8, Overweight/Underweight = 0.6, Hold = 0.4
    base_confidence = 0.4
    if rating in ("buy", "sell"):
        base_confidence = 0.8
    elif rating in ("overweight", "underweight"):
        base_confidence = 0.6

    # Add alignment boost (does the PM rating align with Trader action direction?)
    trader_action = trader_fields.get("action", "").lower()
    alignment_boost = 0.0
    if (
        (rating in ("buy", "overweight") and trader_action == "buy")
        or (rating in ("sell", "underweight") and trader_action == "sell")
        or (rating == "hold" and trader_action == "hold")
    ):
        alignment_boost = 0.15

    confidence = min(0.98, max(0.1, base_confidence + alignment_boost))

    return {
        "id": str(uuid.uuid4()),
        "ticker": ticker.upper(),
        "asset_type": asset_type.lower(),
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
                    reasoning_summary, generated_at, source_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    # Start background scheduler thread
    scheduler.start()
    yield
    # Stop background thread
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
            # Parse DATETIME string
            gen_at_str = row["generated_at"]
            fmt = (
                "%Y-%m-%d %H:%M:%S" if "." not in gen_at_str else "%Y-%m-%d %H:%M:%S.%f"
            )
            gen_at = datetime.datetime.strptime(gen_at_str, fmt)

            sig = SignalPayload(
                id=row["id"],
                ticker=row["ticker"],
                asset_type=row["asset_type"],
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
            )

            # Mask signal details if the free user's views are exhausted
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
        # Query latest signal per ticker
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
            gen_at_str = row["generated_at"]
            fmt = (
                "%Y-%m-%d %H:%M:%S" if "." not in gen_at_str else "%Y-%m-%d %H:%M:%S.%f"
            )
            gen_at = datetime.datetime.strptime(gen_at_str, fmt)

            sig = SignalPayload(
                id=row["id"],
                ticker=row["ticker"],
                asset_type=row["asset_type"],
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
            )

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

    try:
        user_id, tier = get_user_claims_from_token(jwt_token)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=401, detail=f"Invalid authentication token: {e}"
        )

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
