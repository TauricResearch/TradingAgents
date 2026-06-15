# Pulse Trading Signals Microservice (`pulse-trading-signals-service`)

This microservice wraps the `TradingAgents` AI multi-agent simulation framework and exposes it via a production-grade FastAPI REST server. It queries a local SQLite database (`signals.db`) to serve normalized signals, manage watchlists, enforce subscription views quotas, and stream live updates in real-time.

---

## Getting Started (Natively)

### 1. Installation & Environment Configuration
You **must** install the dependencies inside the `pulse-trading-agent` virtual environment for the service to run and for your IDE to resolve imports correctly:
```bash
source ~/pulse-trading-agent/bin/activate
pip install .
```

> [!TIP]
> **VS Code / Pylance "Import could not be resolved" Warning:**
> If your IDE displays import errors for `fastapi` or `pydantic`, it is because the editor is using the global system Python instead of your virtual environment. 
> To resolve this in VS Code, open the Command Palette (`Cmd+Shift+P`), select **"Python: Select Interpreter"**, and choose the python path located at `~/pulse-trading-agent/bin/python`.

### 2. Configure Environment Variables
Create a `.env` file in the root directory and configure the service parameters:
```env
GOOGLE_API_KEY=your_gemini_api_key_here

# Optional LLM Config (Google Gemini 2.5/3.5 Flash)
TRADINGAGENTS_LLM_PROVIDER=google
TRADINGAGENTS_DEEP_THINK_LLM=gemini-2.5-flash
TRADINGAGENTS_QUICK_THINK_LLM=gemini-2.5-flash

# Redis Connection URL
REDIS_URL=redis://localhost:6379/0

# JWT Auth Settings
PULSE_JWT_SECRET=pulse-secret-key
JWT_ALGORITHM=HS256

# Subscription Quota Limit (Free tier views per 24 hours)
FREE_TIER_QUOTA_LIMIT=3
```

### 3. Run the Service
Start the FastAPI application using Uvicorn:
```bash
source ~/pulse-trading-agent/bin/activate
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```
Once started, the interactive API documentation will be available at: **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**.

---

## Deploying with Docker

### 1. Build the Docker Image
Build the container using the root Dockerfile:
```bash
docker build -t pulse-trading-signals-service .
```

### 2. Run with Docker
Run the container, passing your API key and mounting the volume to persist signals:
```bash
docker run -d -p 8000:8000 \
  -e GOOGLE_API_KEY="your_api_key_here" \
  -v ~/.tradingagents:/home/appuser/.tradingagents \
  pulse-trading-signals-service
```

---

## Deploying with Docker Compose

A pre-configured `docker-compose.yml` file is provided to simplify orchestration. It automatically spins up:
1. An official Redis instance (`redis:7-alpine`) on port `6379`.
2. The `trading-signals-service` container, linked to the Redis service container using Docker network bridge.

### 1. Start the Service
Run the following command to start the microservice and its Redis pub/sub broker in the background:
```bash
docker compose up -d
```

### 2. Stop the Service
To stop and clean up the containers:
```bash
docker compose down
```

### 3. Check Service Logs
```bash
docker compose logs -f trading-signals-service
```

---

## Database Schema (`signals.db`)

The database is bootstrapped automatically at `~/.tradingagents/db/signals.db` with the following schema:

### `watchlist_tickers`
Holds the tickers scheduled for signal generation.
* `ticker` (VARCHAR(10), Primary Key) — e.g., `AAPL` or `BTC-USD`
* `asset_type` (VARCHAR(10)) — `stocks` or `crypto`
* `added_at` (DATETIME)

### `trading_signals`
Stores normalized outputs generated from the Multi-Agent framework run.
* `id` (VARCHAR(36), Primary Key)
* `ticker` (VARCHAR(10))
* `asset_type` (VARCHAR(10))
* `signal_type` (VARCHAR(20)) — `buy` | `overweight` | `hold` | `underweight` | `sell`
* `confidence` (FLOAT) — Heuristic score `0.0` - `1.0`
* `time_horizon` (VARCHAR(50)) — e.g., `'3-6 months'`
* `price_target` (FLOAT)
* `entry_price` (FLOAT)
* `stop_loss` (FLOAT)
* `position_sizing` (VARCHAR(50)) — e.g. `'5% of portfolio'`
* `reasoning_summary` (TEXT) — Brief executive case thesis
* `generated_at` (DATETIME)
* `source_run_id` (VARCHAR(100)) — Traceability identifier

### `user_quota_logs`
Audit logs for Free tier consumption tracking.
* `id` (INTEGER, Primary Key AUTOINCREMENT)
* `user_id` (VARCHAR(100))
* `viewed_at` (DATETIME)

---

## API Endpoints

All responses contain a root-level `entitlement` object tracking user tiers and quota states.

### 1. `GET /signals-ms/signals`
Retrieves a paginated, filterable feed of trading signals.
* **Headers**:
  * `Authorization: Bearer <JWT>` OR `X-User-Id` and `X-User-Tier`
* **Query Parameters**:
  * `ticker` (string, optional)
  * `signal_type` (string, optional) — `buy` | `overweight` | `hold` | `underweight` | `sell`
  * `start_date` (string, optional) — `YYYY-MM-DD`
  * `end_date` (string, optional) — `YYYY-MM-DD`
  * `limit` (int, default 20)
  * `offset` (int, default 0)
* **Response Example (Free - Unlocked)**:
  ```json
  {
    "signals": [
      {
        "id": "7471a21c-2cce-4819-42c9-9de5daaa6452",
        "ticker": "AAPL",
        "asset_type": "stocks",
        "signal_type": "buy",
        "confidence": 0.95,
        "time_horizon": "3-6 months",
        "price_target": 240.0,
        "entry_price": 222.5,
        "stop_loss": 210.0,
        "position_sizing": "5% of portfolio",
        "reasoning_summary": "Strong momentum and fundamentals support growth.",
        "generated_at": "2026-06-10T12:00:00Z",
        "source_run_id": "84851256-1632-4224-8140-55287c85de8c"
      }
    ],
    "entitlement": {
      "tier": "free",
      "remaining_views": 9,
      "reset_at": "2026-06-11T12:00:00Z",
      "locked": false,
      "cooldown_ends_at": null
    }
  }
  ```

* **Response Example (Free - Locked/Exhausted)**:
  ```json
  {
    "signals": [
      {
        "id": "7471a21c-2cce-4819-42c9-9de5daaa6452",
        "ticker": "AAPL",
        "asset_type": "stocks",
        "signal_type": "locked",
        "confidence": 0.0,
        "time_horizon": "Locked",
        "price_target": null,
        "entry_price": null,
        "stop_loss": null,
        "position_sizing": "Locked",
        "reasoning_summary": "Upgrade to Pro to view this trading signal details.",
        "generated_at": "2026-06-10T12:00:00Z",
        "source_run_id": null
      }
    ],
    "entitlement": {
      "tier": "free",
      "remaining_views": 0,
      "reset_at": "2026-06-11T12:00:00Z",
      "locked": true,
      "cooldown_ends_at": "2026-06-11T12:00:00Z"
    }
  }
  ```

### 2. `GET /signals-ms/signals/latest`
Gets the single most recent signal for each ticker on the watchlist.
* **Headers**: Standard Auth headers
* **Response**: Same structure as `/signals-ms/signals`

### 3. `GET /signals-ms/tickers`
Returns all tracked tickers and basic signals stats. (Does not consume free tier views).

### 4. `POST /signals-ms/tickers`
Adds a new ticker symbol to the watchlist.
* **Payload**:
  ```json
  {
    "ticker": "MSFT",
    "asset_type": "stocks"
  }
  ```
* **Response**:
  ```json
  {
    "status": "success",
    "message": "Ticker MSFT added to watchlist."
  }
  ```

### 5. `DELETE /signals-ms/tickers/{ticker}`
Removes a ticker symbol from the watchlist.

### 6. `GET /signals-ms/stream`
Server-Sent Events (SSE) real-time stream. Sends newly generated trading signals immediately. Supports both Free and Pro tier users.
* **Format**: `text/event-stream`
* **Authentication**: Must provide a valid JWT via the `Authorization: Bearer <JWT>` header or the `token` query parameter (e.g., `/signals-ms/stream?token=<JWT>`).
* **Quota / Entitlement Gating**:
  * **Pro Tier**: Receives unlimited live streaming signal events.
  * **Free Tier**: Limited to a maximum of 3 signal views per 24 hours (governed by `FREE_TIER_QUOTA_LIMIT`).
  * If a user has exhausted their quota at connection time or consumes it mid-stream, they will receive a structured `quota_exhausted` event and the server will close the connection.

* **SSE Event Types**:
  1. `event: connection`
     * Sent immediately on connection.
     * Payload: `Connected to real-time signals stream`
  2. `event: signal`
     * Broadcasts newly generated signals.
     * Payload: A JSON object matching the `SignalPayload` schema.
  3. `event: quota_exhausted`
     * Sent when the user's quota is exhausted. The stream is closed immediately after.
     * Payload: A JSON object matching the `EntitlementBlock` schema:
       ```json
       {
         "tier": "free",
         "remaining_views": 0,
         "reset_at": "2026-06-16T12:00:00",
         "locked": true,
         "cooldown_ends_at": "2026-06-16T12:00:00"
       }
       ```
  4. `event: heartbeat`
     * Keep-alive ping sent every 20 seconds.
     * Payload: `ping`
  5. `event: error`
     * Sent on internal streaming errors before closing.

### 7. `GET /signals-ms/health`
Basic health and model verification endpoint. (No authentication required).

### 8. `POST /signals-ms/generate`
Force-trigger background analysis for all watchlist tickers or a single ticker.

---

## Guidelines for Other Developers

### 🔑 Guidelines for Authentication & Security Developers
The backend is designed to decapsulate JWT claims directly for authorization context.
1. **JWT Header Injection**:
   * Ensure `pulse-auth-service` JWT tokens contain a `sub` (or `user_id`) claim and a `tier` (or `role`) claim containing either `"free"` or `"pro"`.
   * For reverse proxies (like Nginx/Kong) doing authentication upstream, they can map verified JWT parameters to custom headers before forwarding requests:
     * `X-User-Id`: The user's account identifier.
     * `X-User-Tier`: The tier value (`"free"` or `"pro"`).
2. **CORS Handling**:
   * The API contains standard CORS middleware allowing `*`. Make sure to restrict `allow_origins` in `api/main.py` once the staging/production domain is set.

### 🎨 Guidelines for Frontend Developers
1. **Handling Locked Signals**:
   * When `entitlement.locked` is `true`, signals will return with `signal_type: "locked"`.
   * Bind the UI to display a premium lock overlay on top of the signal details card. Hide indicators, stops, targets, and display the masked `reasoning_summary` next to a call-to-action button prompting the user to upgrade to Pro.
2. **Real-time SSE Streams**:
   * Since native browser `EventSource` does not support custom headers, you should pass the JWT token as a query parameter `?token=...`:
     ```javascript
     const eventSource = new EventSource(`/signals-ms/stream?token=${userToken}`);
     
     // Listen for incoming trading signals
     eventSource.addEventListener('signal', (event) => {
       const newSignal = JSON.parse(event.data);
       // prepend newSignal to your UI feed state
     });

     // Listen for quota exhaustion event
     eventSource.addEventListener('quota_exhausted', (event) => {
       const entitlement = JSON.parse(event.data);
       console.warn("Free tier quota limit reached:", entitlement);
       // Show upgrade overlay, locked status, and close source locally
       eventSource.close();
     });
     ```
3. **Displaying Cooldown Timers**:
   * If `entitlement.locked` is true, use `entitlement.cooldown_ends_at` (returned in HTTP responses or in the `quota_exhausted` SSE payload) to render a ticking countdown clock.
