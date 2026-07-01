# Ticker Price Alerts Design

## Overview

Add the ability for users to define price alerts for specific tickers in their watchlist. When a ticker reaches a pre-defined price, a detailed Telegram notification is sent. This extends the existing indicator system with a new `ticker_price` indicator kind.

## Approach: Hybrid - Extend Indicators with Ticker Support

Add `IndicatorKind: "ticker_price"` with a new `ticker` field on `IndicatorDefinition`. Same storage, API, and scheduler as existing indicators, with ticker-specific evaluation logic.

---

## Data Model

### IndicatorDefinition Changes

Add `ticker_price` to `IndicatorKind` and add optional fields:

```python
IndicatorKind = Literal[
    "vix", "fear_greed", "red_days", "s5fi", "green_streak",
    "price_vs_moving_averages", "ticker_price"  # NEW
]

@dataclass
class IndicatorDefinition:
    id: str
    kind: IndicatorKind
    name: str
    description: str
    threshold: float
    comparator: Literal["above", "below", "at_least", "within"]
    unit: str
    enabled: bool
    source: Literal["builtin", "custom"]
    ticker: str | None = None  # NEW - only for ticker_price kind
    triggered: bool = False    # NEW - one-shot state (True = already fired, don't re-alert)
```

### Storage Format

`ticker_price` alerts stored in the same `indicators.json` file, with the `ticker` field differentiating them from market indicators.

### One-Shot Logic

When an alert triggers:
1. Set `triggered: True` in the indicator definition
2. Write to disk
3. Skip triggered alerts in subsequent checks
4. User can "reset" an alert to make it fire again

---

## Evaluation Logic

### How `run_checks()` Handles `ticker_price`

```python
# In _fetch_value()
if kind == "ticker_price":
    return _fetch_ticker_price(indicator.ticker)

# In _evaluate()
if kind == "ticker_price" and indicator.triggered:
    return False  # One-shot: already fired, skip

# New function
def _fetch_ticker_price(ticker: str) -> float:
    return yf.Ticker(ticker).fast_info["lastPrice"]
```

### Change Detection

Reuses the existing `diff_indicator_states()` — when a `ticker_price` alert transitions from not-triggered to triggered, it appears in the "newly triggered" set and sends a Telegram notification.

### Notification Message Format

```
🚨 Price Alert: SPY
Price: $747.77 (above your $748 target)
Change: +0.78% today
Day Range: $743.15 - $750.18
Alert: triggered at 7:08 AM
```

---

## API Endpoints

### New/Modified Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `POST /api/indicators` | POST | Add new alert (kind=ticker_price, ticker, threshold, comparator) |
| `DELETE /api/indicators/{id}` | DELETE | Remove alert |
| `PATCH /api/indicators/{id}` | PATCH | Update threshold, comparator, enabled, or reset `triggered` |
| `POST /api/indicators/{id}/reset` | POST | Reset `triggered` to False (re-arm one-shot alert) |

### Request Bodies

**Add ticker_price alert:**
```json
{
  "kind": "ticker_price",
  "name": "SPY Above 750",
  "ticker": "SPY",
  "threshold": 750,
  "comparator": "above"
}
```

**Update alert:**
```json
{
  "threshold": 760,
  "comparator": "below"
}
```

**Reset alert:**
```json
{}
```

Validation: `ticker` must be provided when `kind=ticker_price`.

---

## UI - Watchlist Sidebar

### Layout

The watchlist sidebar gets a new "Alerts" section below the ticker list:

```
┌─────────────────────────┐
│  Watchlist          [+] │
├─────────────────────────┤
│  AAPL    $198.45  [+alert] │
│  SPY     $746.77  [+alert] │
│  QQQ     $520.30  [+alert] │
├─────────────────────────┤
│  🚨 Price Alerts         │
│  ┌───────────────────┐  │
│  │ SPY > $750    [x] │  │
│  │ AAPL < $195   [x] │  │
│  └───────────────────┘  │
│  + Add Alert            │
└─────────────────────────┘
```

### Add Alert Flow

1. Click `[+alert]` next to a ticker OR click `+ Add Alert`
2. Inline form appears:
   - Ticker (pre-filled if clicked from ticker)
   - Condition dropdown: Above / Below / Within % / Crosses
   - Price input
3. Save → alert appears in the list

### Alert List Items

Each alert shows:
- Ticker + condition + price (e.g. "SPY > $750")
- Status dot: green (active) / gray (triggered)
- Edit button: change price or condition
- Delete button: remove alert
- Reset button (if triggered): re-arm the alert

---

## Scheduler Flexibility

### Current Behavior

The indicator scheduler runs `run_checks()` on a shared interval. All indicators — including new `ticker_price` alerts — share this schedule.

### Changes

1. **More interval options**: Add 5m, 15m, 30m intervals (currently starts at 1h)
2. **Market hours awareness**: Only check during market hours (9:30 AM - 4:00 PM ET) by default, with option to check 24/7
3. **Immediate check on add/update**: When a user adds or updates a ticker_price alert, run a check immediately for that alert

### Updated Intervals

```
Off, 5m, 15m, 30m, 1h, 2h, 4h, 8h, 12h, 24h, 48h
```

---

## Error Handling

### Invalid Ticker

When adding a `ticker_price` alert:
- Validate ticker exists via `yf.Ticker(ticker).fast_info` before saving
- Return clear error: `"Ticker 'XYZZ' not found. Please check the symbol."`

### Price Fetch Failure

During `run_checks()`:
- If yfinance fails to fetch price, log warning and skip that alert
- Don't crash the entire check cycle
- Alert remains active, will retry on next scheduled check

### Duplicate Alerts

- Prevent duplicate: same ticker + same comparator + same threshold
- Return error: `"Alert already exists for SPY above $750"`

### One-Shot Reset

- Resetting a triggered alert sets `triggered: False`
- Alert re-enters the check cycle on next scheduled run

---

## Bubble Agent Tool Integration

The bubble agent auto-discovers tools from FastAPI routes, so new endpoints become available automatically. However, we need to enhance the tool experience:

### Special Parameter Handling

In `web/server/chat_router.py` `extract_tool_definitions()`, add special cases for `ticker_price` tools:

```python
# post_indicators gets ticker_price-specific parameters
if tool_name == "indicators" and method == "POST":
    parameters["kind"] = {
        "type": "string",
        "enum": ["ticker_price"],
        "description": "Type of alert. Use 'ticker_price' for price alerts on specific tickers.",
    }
    parameters["ticker"] = {
        "type": "string",
        "description": "REQUIRED for ticker_price alerts. The ticker symbol (e.g. 'SPY', 'AAPL').",
    }
    parameters["threshold"] = {
        "type": "number",
        "description": "The price level to trigger the alert (e.g. 750).",
    }
    parameters["comparator"] = {
        "type": "string",
        "enum": ["above", "below", "at_least", "within"],
        "description": "Comparison type: 'above' (price > threshold), 'below' (price < threshold), 'at_least' (price >= threshold), 'within' (price within X% of threshold).",
    }
```

### Tool Rename Map

In `web/frontend/src/components/AgentChatBubble.tsx` `TOOL_RENAME_MAP`, add friendly names:

```typescript
indicators: {
  name: "manage_indicators",
  description: "List, add, update, or remove indicator alerts including ticker price alerts.",
},
indicators_indicator_id: {
  name: "manage_indicator",
  description: "Update or delete a specific indicator/alert by ID.",
},
```

### System Prompt Update

In `getSystemPrompt()` in `AgentChatBubble.tsx`, add:

```
You can set price alerts for tickers using the manage_indicators tool:
- Create: POST with kind="ticker_price", ticker="SPY", threshold=750, comparator="above"
- The system will notify via Telegram when the price condition is met
- Alerts are one-shot: they trigger once then deactivate. Use reset to re-arm.
```

---

## Files to Modify

| File | Changes |
|---|---|
| `web/server/indicators.py` | Add `ticker_price` kind, `ticker`/`triggered` fields, `_fetch_ticker_price()`, validation |
| `web/server/app.py` | Add `/reset` endpoint, immediate check on add/update |
| `web/server/notifier.py` | Add `build_ticker_price_message()` for detailed notifications |
| `web/server/storage.py` | Update `diff_indicator_states()` to handle `triggered` field |
| `web/server/chat_router.py` | Add special parameter handling for ticker_price tools |
| `web/frontend/src/components/WatchlistRail.tsx` | Add alerts section with CRUD UI |
| `web/frontend/src/components/AgentChatBubble.tsx` | Add tool rename entries and system prompt updates |
| `web/frontend/src/lib/api.ts` | Add `resetIndicator()` API function |

## Files to Create

None — all changes extend existing files.
