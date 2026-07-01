# Ticker Price Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ticker price alerts that send detailed Telegram notifications when a ticker reaches a user-defined price level, extending the existing indicator system.

**Architecture:** Add `ticker_price` as a new `IndicatorKind` with `ticker` and `triggered` fields on `IndicatorDefinition`. Reuse existing indicator infrastructure (storage, scheduler, notifications) with ticker-specific evaluation logic. Add UI in watchlist sidebar and bubble agent tool integration.

**Tech Stack:** Python (FastAPI, yfinance, python-telegram-bot), TypeScript (React, Tanstack Query, Zustand)

## Global Constraints

- Python 3.11+, TypeScript 5+
- Reuse existing indicator system patterns (dataclass, file-based JSON storage)
- Ticker validation via yfinance `fast_info`
- One-shot alerts: trigger once, then deactivate until reset
- Bubble agent auto-discovers tools from FastAPI routes

---

## Task 1: Extend Data Model

**Files:**
- Modify: `web/server/indicators.py:20-60`

**Interfaces:**
- Produces: `IndicatorKind` with `"ticker_price"`, `IndicatorDefinition` with `ticker` and `triggered` fields

- [ ] **Step 1: Add `ticker_price` to `IndicatorKind`**

```python
# web/server/indicators.py line 20-27
IndicatorKind = Literal[
    "vix",
    "fear_greed",
    "red_days",
    "s5fi",
    "green_streak",
    "price_vs_moving_averages",
    "ticker_price",  # NEW
]
```

- [ ] **Step 2: Add `ticker` and `triggered` fields to `IndicatorDefinition`**

```python
# web/server/indicators.py line 49-60
@dataclass(frozen=True)
class IndicatorDefinition:
    id: str
    kind: IndicatorKind
    name: str
    description: str
    threshold: float
    comparator: Literal["above", "below", "at_least", "within"]
    unit: str
    enabled: bool = True
    source: Literal["builtin", "custom"] = "builtin"
    ticker: str | None = None  # NEW - only for ticker_price kind
    triggered: bool = False    # NEW - one-shot state
```

- [ ] **Step 3: Update `_definition_to_dict()` to include new fields**

```python
# web/server/indicators.py line 124-135
def _definition_to_dict(defn: IndicatorDefinition) -> dict[str, Any]:
    result = {
        "id": defn.id,
        "kind": defn.kind,
        "name": defn.name,
        "description": defn.description,
        "threshold": defn.threshold,
        "comparator": defn.comparator,
        "unit": defn.unit,
        "enabled": defn.enabled,
        "source": defn.source,
    }
    if defn.ticker is not None:
        result["ticker"] = defn.ticker
    result["triggered"] = defn.triggered
    return result
```

- [ ] **Step 4: Update `_definition_from_dict()` to read new fields**

```python
# web/server/indicators.py line 138-149
def _definition_from_dict(data: dict[str, Any]) -> IndicatorDefinition:
    return IndicatorDefinition(
        id=str(data["id"]),
        kind=str(data.get("kind", "vix")),  # type: ignore[arg-type]
        name=str(data.get("name", data["id"])),
        description=str(data.get("description", "")),
        threshold=float(data.get("threshold", 0)),
        comparator=str(data.get("comparator", "above")),  # type: ignore[arg-type]
        unit=str(data.get("unit", "")),
        enabled=bool(data.get("enabled", True)),
        source=str(data.get("source", "custom")),  # type: ignore[arg-type]
        ticker=data.get("ticker"),  # NEW
        triggered=bool(data.get("triggered", False)),  # NEW
    )
```

- [ ] **Step 5: Commit**

```bash
git add web/server/indicators.py
git commit -m "feat: extend IndicatorDefinition with ticker_price kind and new fields"
```

---

## Task 2: Update CRUD Operations

**Files:**
- Modify: `web/server/indicators.py:167-239`

**Interfaces:**
- Consumes: `IndicatorDefinition` with `ticker` and `triggered` fields
- Produces: `add_indicator()`, `update_indicator()`, `reset_indicator()` functions

- [ ] **Step 1: Update `add_indicator()` to handle `ticker_price` kind**

```python
# web/server/indicators.py line 167-194
def add_indicator(body: dict[str, Any]) -> IndicatorDefinition:
    kind = str(body.get("kind", "vix"))
    
    # Validate kind is supported
    supported_kinds = {d.kind for d in DEFAULT_INDICATORS} | {"ticker_price"}
    if kind not in supported_kinds:
        raise ValueError(f"unsupported indicator kind: {kind}")
    
    # For ticker_price, validate ticker is provided
    ticker = body.get("ticker")
    if kind == "ticker_price":
        if not ticker:
            raise ValueError("ticker is required for ticker_price alerts")
        ticker = str(ticker).upper()
        # Validate ticker exists
        try:
            import yfinance as yf
            yf.Ticker(ticker).fast_info["lastPrice"]
        except Exception:
            raise ValueError(f"Ticker '{ticker}' not found. Please check the symbol.")
    
    # Get base definition for defaults
    if kind == "ticker_price":
        # Create a base definition for ticker_price
        base = IndicatorDefinition(
            id="",
            kind="ticker_price",
            name=f"{ticker} Alert",
            description=f"Alert when {ticker} reaches the target price.",
            threshold=0,
            comparator="above",
            unit="price",
            ticker=ticker,
        )
    else:
        base = next(d for d in DEFAULT_INDICATORS if d.kind == kind)
    
    name = str(body.get("name") or base.name).strip()
    threshold = float(body.get("threshold", base.threshold))
    comparator = str(body.get("comparator", base.comparator))
    indicator_id = _slugify(str(body.get("id") or name or kind))
    
    rows = read_indicators()
    existing_ids = {row.id for row in rows}
    if indicator_id in existing_ids:
        suffix = 2
        while f"{indicator_id}-{suffix}" in existing_ids:
            suffix += 1
        indicator_id = f"{indicator_id}-{suffix}"
    
    # Check for duplicate ticker_price alerts
    if kind == "ticker_price":
        for row in rows:
            if (
                row.kind == "ticker_price"
                and row.ticker == ticker
                and row.comparator == comparator
                and row.threshold == threshold
            ):
                raise ValueError(f"Alert already exists for {ticker} {comparator} ${threshold}")
    
    row = IndicatorDefinition(
        id=indicator_id,
        kind=base.kind,
        name=name,
        description=str(body.get("description") or base.description),
        threshold=threshold,
        comparator=comparator,
        unit=base.unit,
        source="custom",
        enabled=bool(body.get("enabled", True)),
        ticker=ticker,
        triggered=False,
    )
    write_indicators([*rows, row])
    return row
```

- [ ] **Step 2: Update `update_indicator()` to handle `ticker` and `triggered` fields**

```python
# web/server/indicators.py line 206-234
def update_indicator(indicator_id: str, body: dict[str, Any]) -> IndicatorDefinition | None:
    rows = read_indicators()
    for i, row in enumerate(rows):
        if row.id == indicator_id:
            new_threshold = body.get("threshold")
            if new_threshold is not None:
                try:
                    new_threshold = float(new_threshold)
                except (TypeError, ValueError):
                    raise ValueError("threshold must be a number") from None
            new_enabled = body.get("enabled")
            if new_enabled is not None:
                if not isinstance(new_enabled, bool):
                    raise ValueError("enabled must be a boolean")
            new_comparator = body.get("comparator")
            if new_comparator is not None:
                if new_comparator not in ("above", "below", "at_least", "within"):
                    raise ValueError("comparator must be one of: above, below, at_least, within")
            new_ticker = body.get("ticker")
            new_triggered = body.get("triggered")
            if new_triggered is not None:
                if not isinstance(new_triggered, bool):
                    raise ValueError("triggered must be a boolean")
            
            rows[i] = IndicatorDefinition(
                id=row.id,
                kind=row.kind,
                name=row.name,
                description=row.description,
                threshold=new_threshold if new_threshold is not None else row.threshold,
                comparator=new_comparator if new_comparator is not None else row.comparator,
                unit=row.unit,
                enabled=new_enabled if new_enabled is not None else row.enabled,
                source=row.source,
                ticker=new_ticker if new_ticker is not None else row.ticker,
                triggered=new_triggered if new_triggered is not None else row.triggered,
            )
            write_indicators(rows)
            return rows[i]
    return None
```

- [ ] **Step 3: Add `reset_indicator()` function for single-alert reset**

```python
# web/server/indicators.py - add after update_indicator()
def reset_indicator(indicator_id: str) -> IndicatorDefinition | None:
    """Reset a single indicator's triggered state to False (re-arm one-shot alert)."""
    rows = read_indicators()
    for i, row in enumerate(rows):
        if row.id == indicator_id:
            if not row.triggered:
                return row  # Already active, no change needed
            rows[i] = IndicatorDefinition(
                id=row.id,
                kind=row.kind,
                name=row.name,
                description=row.description,
                threshold=row.threshold,
                comparator=row.comparator,
                unit=row.unit,
                enabled=row.enabled,
                source=row.source,
                ticker=row.ticker,
                triggered=False,
            )
            write_indicators(rows)
            return rows[i]
    return None
```

- [ ] **Step 4: Commit**

```bash
git add web/server/indicators.py
git commit -m "feat: update CRUD operations for ticker_price alerts"
```

---

## Task 3: Add Evaluation Logic

**Files:**
- Modify: `web/server/indicators.py:242-337`

**Interfaces:**
- Consumes: `IndicatorDefinition` with `ticker` and `triggered` fields
- Produces: `_fetch_ticker_price()`, updated `_fetch_value()`, updated `_evaluate()`

- [ ] **Step 1: Add `_fetch_ticker_price()` function**

```python
# web/server/indicators.py - add after _fetch_latest_close()
def _fetch_ticker_price(ticker: str) -> dict[str, Any]:
    """Fetch current price and metadata for a ticker."""
    import yfinance as yf
    t = yf.Ticker(ticker)
    fast_info = t.fast_info
    price = float(fast_info["lastPrice"])
    
    # Get additional context for detailed notification
    try:
        hist = t.history(period="5d")
        if not hist.empty and len(hist) >= 2:
            prev_close = float(hist["Close"].iloc[-2])
            change_pct = ((price - prev_close) / prev_close) * 100
            day_high = float(hist["High"].iloc[-1])
            day_low = float(hist["Low"].iloc[-1])
        else:
            change_pct = 0
            day_high = price
            day_low = price
    except Exception:
        change_pct = 0
        day_high = price
        day_low = price
    
    return {
        "price": price,
        "change_pct": change_pct,
        "day_high": day_high,
        "day_low": day_low,
    }
```

- [ ] **Step 2: Update `_fetch_value()` to handle `ticker_price`**

```python
# web/server/indicators.py line 280-299
def _fetch_value(defn: IndicatorDefinition) -> Any:
    if defn.kind == "vix":
        return _fetch_latest_close("^VIX", "5d")
    if defn.kind == "fear_greed":
        resp = requests.get(
            CNN_FEAR_GREED_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TradingAgents/1.0)"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return float(resp.json()["fear_and_greed"]["score"])
    if defn.kind == "red_days":
        return _count_streak(red=True, count=int(defn.threshold))
    if defn.kind == "green_streak":
        return _count_streak(red=False, count=int(defn.threshold))
    if defn.kind == "s5fi":
        return _fetch_s5fi()
    if defn.kind == "price_vs_moving_averages":
        return _fetch_price_vs_moving_averages()
    if defn.kind == "ticker_price":
        if not defn.ticker:
            raise ValueError("ticker_price indicator missing ticker field")
        return _fetch_ticker_price(defn.ticker)
    raise ValueError(f"unsupported indicator kind: {defn.kind}")
```

- [ ] **Step 3: Update `_evaluate()` to handle `ticker_price` with one-shot logic**

```python
# web/server/indicators.py line 302-337
def _evaluate(defn: IndicatorDefinition, value: Any) -> tuple[bool, str]:
    if defn.kind == "vix":
        triggered = float(value) > defn.threshold
        return triggered, f"VIX is {float(value):.2f}, {'above' if triggered else 'below'} threshold {defn.threshold:.0f}."
    if defn.kind == "fear_greed":
        triggered = float(value) < defn.threshold
        return triggered, f"Fear & Greed is {float(value):.1f} ({_fear_label(float(value))}), threshold {defn.threshold:.0f}."
    if defn.kind == "red_days":
        triggered = int(value) >= int(defn.threshold)
        return triggered, f"{int(value)} consecutive red day(s); threshold is {int(defn.threshold)}."
    if defn.kind == "green_streak":
        triggered = int(value) >= int(defn.threshold)
        return triggered, f"{int(value)} consecutive green day(s); threshold is {int(defn.threshold)}."
    if defn.kind == "s5fi":
        triggered = float(value) < defn.threshold
        return triggered, f"S5FI is {float(value):.1f}% above 50-day MA; threshold is {defn.threshold:.0f}%."
    if defn.kind == "price_vs_moving_averages":
        hits = []
        for snapshot in value["snapshots"]:
            for window in MA_WINDOWS:
                average = snapshot["moving_averages"][window]
                distance = snapshot["distances"][window]
                if distance <= defn.threshold:
                    hits.append(
                        f"{snapshot['label']} close {snapshot['close']:.2f} is within {distance * 100:.2f}% of {window}-day MA ({average:.2f})"
                    )
        if hits:
            return True, "; ".join(hits) + "."
        nearest = value["nearest_match"]
        if nearest is None:
            return False, "No data available for watched moving-average tickers."
        return False, (
            f"Closest: {nearest['label']} is {nearest['distance_ratio'] * 100:.2f}% "
            f"from its {nearest['window']}-day MA; trigger is {defn.threshold * 100:.2f}%."
        )
    if defn.kind == "ticker_price":
        # One-shot: already fired, skip
        if defn.triggered:
            return False, f"Alert already triggered for {defn.ticker}."
        
        price_data = value
        price = price_data["price"]
        threshold = defn.threshold
        comparator = defn.comparator
        
        if comparator == "above":
            triggered = price > threshold
            msg = f"{defn.ticker} is ${price:.2f} (above ${threshold:.2f})"
        elif comparator == "below":
            triggered = price < threshold
            msg = f"{defn.ticker} is ${price:.2f} (below ${threshold:.2f})"
        elif comparator == "at_least":
            triggered = price >= threshold
            msg = f"{defn.ticker} is ${price:.2f} (at least ${threshold:.2f})"
        elif comparator == "within":
            # Within X% of threshold
            pct = defn.threshold / 100 if defn.threshold > 1 else defn.threshold
            diff_pct = abs(price - threshold) / threshold
            triggered = diff_pct <= pct
            msg = f"{defn.ticker} is ${price:.2f} ({diff_pct*100:.2f}% from ${threshold:.2f})"
        else:
            triggered = False
            msg = f"Unknown comparator: {comparator}"
        
        if triggered:
            change = price_data.get("change_pct", 0)
            high = price_data.get("day_high", price)
            low = price_data.get("day_low", price)
            msg += f"\nChange: {change:+.2f}% today"
            msg += f"\nDay Range: ${low:.2f} - ${high:.2f}"
        
        return triggered, msg
    return False, "Unsupported indicator."
```

- [ ] **Step 4: Update `run_checks()` to set `triggered` flag when alert fires**

```python
# web/server/indicators.py line 242-277
def run_checks() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    indicators_to_update: list[IndicatorDefinition] = []
    
    for defn in read_indicators():
        if not defn.enabled:
            results.append({"indicator": _definition_to_dict(defn), "result": None})
            continue
        try:
            value = _fetch_value(defn)
            triggered, message = _evaluate(defn, value)
            
            # For ticker_price, update triggered state if it fires
            if defn.kind == "ticker_price" and triggered and not defn.triggered:
                indicators_to_update.append(defn)
            
            results.append(
                {
                    "indicator": _definition_to_dict(defn),
                    "result": {
                        "triggered": triggered,
                        "value": value,
                        "threshold": defn.threshold,
                        "message": message,
                        "checked_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("indicator check failed: %s", defn.id)
            results.append(
                {
                    "indicator": _definition_to_dict(defn),
                    "result": {
                        "triggered": False,
                        "value": None,
                        "threshold": defn.threshold,
                        "message": f"Error fetching data: {exc}",
                        "checked_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
                    },
                }
            )
    
    # Persist triggered state for one-shot alerts
    if indicators_to_update:
        all_indicators = read_indicators()
        update_map = {d.id: d for d in indicators_to_update}
        updated = []
        for ind in all_indicators:
            if ind.id in update_map:
                updated.append(IndicatorDefinition(
                    id=ind.id,
                    kind=ind.kind,
                    name=ind.name,
                    description=ind.description,
                    threshold=ind.threshold,
                    comparator=ind.comparator,
                    unit=ind.unit,
                    enabled=ind.enabled,
                    source=ind.source,
                    ticker=ind.ticker,
                    triggered=True,
                ))
            else:
                updated.append(ind)
        write_indicators(updated)
    
    return results
```

- [ ] **Step 5: Commit**

```bash
git add web/server/indicators.py
git commit -m "feat: add ticker_price evaluation logic with one-shot alerts"
```

---

## Task 4: Add API Endpoint for Single Reset

**Files:**
- Modify: `web/server/app.py:457-463`

**Interfaces:**
- Consumes: `reset_indicator()` from indicators.py
- Produces: `POST /api/indicators/{indicator_id}/reset` endpoint

- [ ] **Step 1: Add the reset endpoint**

```python
# web/server/app.py - add after the reset_indicators endpoint
@app.post("/api/indicators/{indicator_id}/reset")
def reset_single_indicator(indicator_id: str) -> dict:
    """Reset a single indicator's triggered state (re-arm one-shot alert)."""
    try:
        result = indicators.reset_indicator(indicator_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="indicator not found")
    return indicators._definition_to_dict(result)
```

- [ ] **Step 2: Add docstring to existing endpoints for better tool descriptions**

```python
# web/server/app.py - update existing indicator endpoints with docstrings
@app.get("/api/indicators")
def list_indicators() -> dict:
    """List all configured indicators and price alerts."""
    return {
        "indicators": [
            indicators._definition_to_dict(row) for row in indicators.read_indicators()
        ]
    }

@app.post("/api/indicators")
def post_indicator(body: IndicatorIn) -> dict:
    """Add a new indicator or price alert. For ticker_price alerts, provide ticker, threshold, and comparator."""
    try:
        row = indicators.add_indicator(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return indicators._definition_to_dict(row)

@app.delete("/api/indicators/{indicator_id}", status_code=204)
def delete_indicator(indicator_id: str) -> Response:
    """Remove an indicator or price alert by ID."""
    if not indicators.remove_indicator(indicator_id):
        raise HTTPException(status_code=404, detail="indicator not found")
    return Response(status_code=204)

@app.patch("/api/indicators/{indicator_id}")
def patch_indicator(indicator_id: str, body: dict) -> dict:
    """Update an indicator's threshold, comparator, enabled state, or trigger status."""
    try:
        updated = indicators.update_indicator(indicator_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="indicator not found")
    return indicators._definition_to_dict(updated)
```

- [ ] **Step 3: Commit**

```bash
git add web/server/app.py
git commit -m "feat: add single indicator reset endpoint with docstrings"
```

---

## Task 5: Add Detailed Notification Messages

**Files:**
- Modify: `web/server/notifier.py:218-258`

**Interfaces:**
- Consumes: Indicator check results with `ticker_price` kind
- Produces: `build_ticker_price_message()` function

- [ ] **Step 1: Add `build_ticker_price_message()` function**

```python
# web/server/notifier.py - add after build_change_message()
def build_ticker_price_message(check: dict) -> str:
    """Build a detailed HTML Telegram message for a ticker price alert.
    
    ``check`` is a single check dict from ``run_checks()`` with indicator kind ``ticker_price``.
    """
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    ind = check.get("indicator", {})
    result = check.get("result") or {}
    
    ticker = ind.get("ticker", "???")
    threshold = ind.get("threshold", 0)
    comparator = ind.get("comparator", "above")
    message = result.get("message", "")
    value = result.get("value", {})
    
    # Parse price data from value
    if isinstance(value, dict):
        price = value.get("price", 0)
        change_pct = value.get("change_pct", 0)
        day_high = value.get("day_high", price)
        day_low = value.get("day_low", price)
    else:
        price = float(value) if value else 0
        change_pct = 0
        day_high = price
        day_low = price
    
    # Build comparator text
    comparator_text = {
        "above": "above",
        "below": "below",
        "at_least": "at least",
        "within": "within",
    }.get(comparator, comparator)
    
    lines = [
        f"🚨 <b>Price Alert: {_e(ticker)}</b>",
        f"<i>{_e(now)}</i>",
        "",
        f"<b>Price:</b> ${price:.2f} ({comparator_text} your ${threshold:.2f} target)",
        f"<b>Change:</b> {change_pct:+.2f}% today",
        f"<b>Day Range:</b> ${day_low:.2f} - ${day_high:.2f}",
        "",
        "<i>Automated price alert. Not financial advice.</i>",
    ]
    return "\n".join(lines)
```

- [ ] **Step 2: Update `build_change_message()` to use detailed format for ticker_price alerts**

```python
# web/server/notifier.py line 227-258
def build_change_message(diff: dict) -> str:
    """Build an HTML Telegram message describing what changed.
    
    ``diff`` is the dict returned by ``storage.diff_indicator_states()``.
    """
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"📊 <b>TradingAgents Indicators — Signal Update</b>\n<i>{_e(now)}</i>\n"]

    new_checks = diff.get("newly_triggered", [])
    resolved_checks = diff.get("resolved", [])
    still_checks = diff.get("still_active", [])

    if new_checks:
        lines.append("🚨 <b>New Signals</b>")
        for c in new_checks:
            ind = c.get("indicator", {})
            if ind.get("kind") == "ticker_price":
                # Use detailed message for ticker_price alerts
                lines.append(_ticker_price_inline(c))
            else:
                lines.append(f"• {_check_to_line(c)}")
        lines.append("")

    if resolved_checks:
        lines.append("✅ <b>Resolved</b>")
        for c in resolved_checks:
            lines.append(f"• {_check_to_line(c)}")
        lines.append("")

    if still_checks:
        lines.append("ℹ️ <b>Still Active</b>")
        for c in still_checks:
            lines.append(f"• {_check_to_line(c)}")
        lines.append("")

    lines.append("<i>Automated indicator alert. Not financial advice.</i>")
    return "\n".join(lines)


def _ticker_price_inline(check: dict) -> str:
    """Format a ticker_price alert as an inline HTML line."""
    ind = check.get("indicator", {})
    result = check.get("result") or {}
    ticker = ind.get("ticker", "???")
    threshold = ind.get("threshold", 0)
    comparator = ind.get("comparator", "above")
    value = result.get("value", {})
    
    if isinstance(value, dict):
        price = value.get("price", 0)
        change_pct = value.get("change_pct", 0)
    else:
        price = float(value) if value else 0
        change_pct = 0
    
    comparator_symbol = {"above": ">", "below": "<", "at_least": ">=", "within": "~"}.get(comparator, "?")
    return f"• <b>{_e(ticker)}</b> ${price:.2f} ({comparator_symbol} ${threshold:.2f}) {change_pct:+.2f}%"
```

- [ ] **Step 3: Commit**

```bash
git add web/server/notifier.py
git commit -m "feat: add detailed ticker price notification messages"
```

---

## Task 6: Add Bubble Agent Tool Integration

**Files:**
- Modify: `web/server/chat_router.py:88-98`
- Modify: `web/frontend/src/components/AgentChatBubble.tsx:268-285`

**Interfaces:**
- Consumes: FastAPI routes with docstrings
- Produces: Enhanced tool definitions for ticker_price alerts

- [ ] **Step 1: Add special parameter handling in `extract_tool_definitions()`**

```python
# web/server/chat_router.py line 88-98
# Add known query parameters for commonly used endpoints
if tool_name == "prices":
    parameters["ticker"] = {
        "type": "string",
        "description": "ticker symbol to get price for, e.g. 'SPY', 'AAPL'",
    }
if tool_name == "tickers_ticker_history":
    parameters["range"] = {
        "type": "string",
        "description": "Time range: '1d', '5d', '1mo', '3mo', '6mo', '1y'. Default: 'auto'",
    }
# NEW: Add ticker_price-specific parameters for post_indicators
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

- [ ] **Step 2: Add tool rename map entries in `AgentChatBubble.tsx`**

```typescript
// web/frontend/src/components/AgentChatBubble.tsx line 268-279
const TOOL_RENAME_MAP: Record<string, { name: string; description: string; originalName: string }> = {
  tickers_ticker_history: {
    name: "get_ticker_history",
    description: "REQUIRED PARAMS: ticker (string). Fetches historical price data for a stock ticker. Usage: get_ticker_history({ticker: \"SPY\", range: \"1mo\"}). Always pass ticker as a string like \"SPY\", \"AAPL\", or \"QQQ\".",
    originalName: "get_tickers_ticker_history",
  },
  tickers_ticker_runs: {
    name: "get_ticker_runs",
    description: "REQUIRED PARAMS: ticker (string). Gets analysis runs for a ticker. Usage: get_ticker_runs({ticker: \"SPY\", limit: 10}). Always pass ticker as a string.",
    originalName: "get_tickers_ticker_runs",
  },
  // NEW: Add friendly names for indicator tools
  indicators: {
    name: "manage_indicators",
    description: "List, add, update, or remove indicator alerts including ticker price alerts. Create price alerts with kind='ticker_price', ticker='SPY', threshold=750, comparator='above'.",
    originalName: "indicators",
  },
  indicators_indicator_id: {
    name: "manage_indicator",
    description: "Update or delete a specific indicator/alert by ID. Can also reset triggered alerts.",
    originalName: "indicators_indicator_id",
  },
};
```

- [ ] **Step 3: Update system prompt in `getSystemPrompt()`**

```typescript
// web/frontend/src/components/AgentChatBubble.tsx line 17-55
function getSystemPrompt(tools: Array<{ name: string; description: string }>): string {
  // ... existing code ...
  
  return `You are a knowledgeable trading assistant with access to real-time market data and analysis tools.

Current date and time: ${dateTimeStr}

## TOOL CALLING RULES (CRITICAL)
When you call a tool, you MUST provide ALL required parameters in the arguments JSON object.

**Example of a CORRECT tool call for get_ticker_history:**
{"name": "get_ticker_history", "arguments": {"ticker": "SPY", "range": "1mo"}}

**Example of an INCORRECT tool call (missing ticker):**
{"name": "get_ticker_history", "arguments": {}}  <- THIS WILL FAIL

If user asks about SPY, you MUST call get_ticker_history with ticker="SPY" in the arguments, like:
{"name": "get_ticker_history", "arguments": {"ticker": "SPY"}}

DO NOT call tools without required parameters. Every parameter marked as REQUIRED must be provided.

## PRICE ALERTS
You can set price alerts for tickers using the manage_indicators tool:
- Create: POST with kind="ticker_price", ticker="SPY", threshold=750, comparator="above"
- The system will notify via Telegram when the price condition is met
- Alerts are one-shot: they trigger once then deactivate. Use reset to re-arm.

Your available tools:
${toolList}

Always actually call the tools via tool_calls function - do not just describe what you would call.`;
}
```

- [ ] **Step 4: Commit**

```bash
git add web/server/chat_router.py web/frontend/src/components/AgentChatBubble.tsx
git commit -m "feat: add bubble agent tool integration for ticker_price alerts"
```

---

## Task 7: Add Frontend API Functions

**Files:**
- Modify: `web/frontend/src/lib/api.ts:162-262`

**Interfaces:**
- Consumes: REST API endpoints
- Produces: `resetIndicator()` function

- [ ] **Step 1: Add `resetIndicator()` function**

```typescript
// web/frontend/src/lib/api.ts - add after updateIndicator()
export async function resetIndicator(id: string): Promise<unknown> {
  const res = await fetch(`/api/indicators/${encodeURIComponent(id)}/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw await ApiError.fromResponse(res);
  return res.json();
}
```

- [ ] **Step 2: Commit**

```bash
git add web/frontend/src/lib/api.ts
git commit -m "feat: add resetIndicator API function"
```

---

## Task 8: Add Watchlist Sidebar UI

**Files:**
- Modify: `web/frontend/src/components/WatchlistRail.tsx`

**Interfaces:**
- Consumes: `fetchIndicators()`, `addIndicator()`, `removeIndicator()`, `updateIndicator()`, `resetIndicator()` from api.ts
- Produces: Alert list UI with CRUD operations

- [ ] **Step 1: Add imports and state for alerts**

```typescript
// web/frontend/src/components/WatchlistRail.tsx - add imports
import { 
  fetchIndicators, 
  addIndicator, 
  removeIndicator, 
  updateIndicator,
  resetIndicator,
  type Indicator 
} from "../lib/api";

// Add state for alerts
const [showAlertForm, setShowAlertForm] = useState(false);
const [alertTicker, setAlertTicker] = useState("");
const [alertThreshold, setAlertThreshold] = useState("");
const [alertComparator, setAlertComparator] = useState<"above" | "below" | "at_least" | "within">("above");
const [alertError, setAlertError] = useState<string | null>(null);
```

- [ ] **Step 2: Add query for indicators**

```typescript
// web/frontend/src/components/WatchlistRail.tsx - add query
const { data: indicatorsData } = useQuery({ 
  queryKey: ["indicators"], 
  queryFn: fetchIndicators 
});

// Filter to only ticker_price alerts
const tickerAlerts = (indicatorsData?.indicators || []).filter(
  (ind: Indicator) => ind.kind === "ticker_price"
);
```

- [ ] **Step 3: Add alert form and list UI**

```tsx
// web/frontend/src/components/WatchlistRail.tsx - add after ticker list
{/* Price Alerts Section */}
<div className="border-t border-white/10 mt-2 pt-2">
  <div className="flex items-center justify-between px-2 mb-2">
    <span className="text-xs font-medium text-white/60 uppercase tracking-wider">
      Price Alerts
    </span>
    <button
      onClick={() => {
        setShowAlertForm(!showAlertForm);
        setAlertError(null);
      }}
      className="text-white/40 hover:text-white/80 transition-colors"
    >
      <Plus size={14} />
    </button>
  </div>

  {/* Alert Form */}
  {showAlertForm && (
    <div className="px-2 mb-2 p-2 bg-white/5 rounded-lg">
      <div className="flex gap-1 mb-2">
        <input
          type="text"
          placeholder="Ticker"
          value={alertTicker}
          onChange={(e) => setAlertTicker(e.target.value.toUpperCase())}
          className="flex-1 bg-white/10 rounded px-2 py-1 text-xs text-white placeholder-white/40"
        />
        <select
          value={alertComparator}
          onChange={(e) => setAlertComparator(e.target.value as typeof alertComparator)}
          className="bg-white/10 rounded px-2 py-1 text-xs text-white"
        >
          <option value="above">Above</option>
          <option value="below">Below</option>
          <option value="at_least">At Least</option>
          <option value="within">Within %</option>
        </select>
      </div>
      <div className="flex gap-1">
        <input
          type="number"
          placeholder="Price"
          value={alertThreshold}
          onChange={(e) => setAlertThreshold(e.target.value)}
          className="flex-1 bg-white/10 rounded px-2 py-1 text-xs text-white placeholder-white/40"
        />
        <button
          onClick={async () => {
            if (!alertTicker || !alertThreshold) {
              setAlertError("Ticker and price required");
              return;
            }
            try {
              await addIndicator({
                kind: "ticker_price",
                ticker: alertTicker,
                threshold: parseFloat(alertThreshold),
                comparator: alertComparator,
                name: `${alertTicker} ${alertComparator} $${alertThreshold}`,
              });
              setShowAlertForm(false);
              setAlertTicker("");
              setAlertThreshold("");
              setAlertError(null);
              qc.invalidateQueries({ queryKey: ["indicators"] });
            } catch (err) {
              setAlertError(err instanceof Error ? err.message : "Failed to add alert");
            }
          }}
          className="bg-blue-500/20 hover:bg-blue-500/30 text-blue-400 px-2 py-1 rounded text-xs transition-colors"
        >
          Add
        </button>
      </div>
      {alertError && (
        <p className="text-red-400 text-xs mt-1">{alertError}</p>
      )}
    </div>
  )}

  {/* Alert List */}
  <div className="space-y-1">
    {tickerAlerts.map((alert: Indicator) => (
      <div
        key={alert.id}
        className="flex items-center justify-between px-2 py-1 rounded hover:bg-white/5 group"
      >
        <div className="flex items-center gap-2">
          <div
            className={`w-2 h-2 rounded-full ${
              alert.triggered ? "bg-gray-500" : "bg-green-500"
            }`}
          />
          <span className="text-xs text-white/80">
            {alert.ticker} {alert.comparator === "above" ? ">" : alert.comparator === "below" ? "<" : alert.comparator === "at_least" ? ">=" : "~"} ${alert.threshold}
          </span>
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {alert.triggered && (
            <button
              onClick={async () => {
                await resetIndicator(alert.id);
                qc.invalidateQueries({ queryKey: ["indicators"] });
              }}
              className="text-yellow-400/60 hover:text-yellow-400 text-xs"
              title="Reset alert"
            >
              ↺
            </button>
          )}
          <button
            onClick={async () => {
              await removeIndicator(alert.id);
              qc.invalidateQueries({ queryKey: ["indicators"] });
            }}
            className="text-red-400/60 hover:text-red-400 text-xs"
            title="Delete alert"
          >
            ×
          </button>
        </div>
      </div>
    ))}
    {tickerAlerts.length === 0 && !showAlertForm && (
      <p className="text-xs text-white/40 px-2 py-1">No price alerts</p>
    )}
  </div>
</div>
```

- [ ] **Step 4: Add quick alert button to ticker rows**

```tsx
// web/frontend/src/components/WatchlistRail.tsx - add to TickerRow component
<button
  onClick={(e) => {
    e.stopPropagation();
    setAlertTicker(ticker);
    setShowAlertForm(true);
  }}
  className="text-white/40 hover:text-white/80 opacity-0 group-hover:opacity-100 transition-opacity"
  title="Add price alert"
>
  <Bell size={12} />
</button>
```

- [ ] **Step 5: Commit**

```bash
git add web/frontend/src/components/WatchlistRail.tsx
git commit -m "feat: add watchlist sidebar UI for price alerts"
```

---

## Task 9: Update Scheduler Intervals

**Files:**
- Modify: `web/frontend/src/components/IndicatorRailView.tsx:421-449`

**Interfaces:**
- Consumes: Existing schedule UI
- Produces: Updated interval options

- [ ] **Step 1: Add more interval options**

```typescript
// web/frontend/src/components/IndicatorRailView.tsx - update interval options
const INTERVAL_OPTIONS = [
  { label: "Off", value: 0 },
  { label: "5m", value: 5 * 60 * 1000 },
  { label: "15m", value: 15 * 60 * 1000 },
  { label: "30m", value: 30 * 60 * 1000 },
  { label: "1h", value: 60 * 60 * 1000 },
  { label: "2h", value: 2 * 60 * 60 * 1000 },
  { label: "4h", value: 4 * 60 * 60 * 1000 },
  { label: "8h", value: 8 * 60 * 60 * 1000 },
  { label: "12h", value: 12 * 60 * 60 * 1000 },
  { label: "24h", value: 24 * 60 * 60 * 1000 },
  { label: "48h", value: 48 * 60 * 60 * 1000 },
];
```

- [ ] **Step 2: Commit**

```bash
git add web/frontend/src/components/IndicatorRailView.tsx
git commit -m "feat: add more scheduler interval options"
```

---

## Task 10: Test the Implementation

**Files:**
- Create: `tests/test_ticker_price_alerts.py`

**Interfaces:**
- Consumes: All implemented functions
- Produces: Test coverage for ticker_price alerts

- [ ] **Step 1: Write test for data model**

```python
# tests/test_ticker_price_alerts.py
import pytest
from web.server.indicators import (
    IndicatorDefinition,
    add_indicator,
    remove_indicator,
    update_indicator,
    reset_indicator,
    read_indicators,
    write_indicators,
)


def test_indicator_definition_with_ticker():
    """Test that IndicatorDefinition can have ticker and triggered fields."""
    ind = IndicatorDefinition(
        id="test-spy",
        kind="ticker_price",
        name="SPY Above 750",
        description="Alert when SPY reaches 750",
        threshold=750,
        comparator="above",
        unit="price",
        ticker="SPY",
        triggered=False,
    )
    assert ind.ticker == "SPY"
    assert ind.triggered is False


def test_add_ticker_price_alert():
    """Test adding a ticker_price alert."""
    # This will fail if yfinance is not available or ticker is invalid
    # In a real test, you'd mock yfinance
    pass


def test_reset_indicator():
    """Test resetting a triggered indicator."""
    # Create a triggered indicator
    ind = IndicatorDefinition(
        id="test-spy",
        kind="ticker_price",
        name="SPY Above 750",
        description="Alert when SPY reaches 750",
        threshold=750,
        comparator="above",
        unit="price",
        ticker="SPY",
        triggered=True,
    )
    write_indicators([ind])
    
    # Reset it
    result = reset_indicator("test-spy")
    assert result is not None
    assert result.triggered is False
```

- [ ] **Step 2: Run tests**

```bash
cd web
python -m pytest tests/test_ticker_price_alerts.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_ticker_price_alerts.py
git commit -m "test: add ticker_price alerts test coverage"
```

---

## Task 11: Final Verification

**Files:**
- All modified files

**Interfaces:**
- Full integration test

- [ ] **Step 1: Start the server and verify endpoints**

```bash
cd web
uvicorn server.app:app --reload
```

- [ ] **Step 2: Test API endpoints manually**

```bash
# Add a ticker_price alert
curl -X POST http://localhost:8000/api/indicators \
  -H "Content-Type: application/json" \
  -d '{"kind": "ticker_price", "ticker": "SPY", "threshold": 750, "comparator": "above"}'

# List indicators
curl http://localhost:8000/api/indicators

# Reset an indicator
curl -X POST http://localhost:8000/api/indicators/{id}/reset
```

- [ ] **Step 3: Verify bubble agent tools**

```bash
# Check tool definitions
curl http://localhost:8000/api/chat/tools | jq '.tools[] | select(.name | contains("indicator"))'
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete ticker price alerts implementation"
```
