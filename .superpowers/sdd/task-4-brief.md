# Task 4: Add API Endpoint for Single Reset

**Files:**
- Modify: `web/server/app.py:457-463`

**Interfaces:**
- Consumes: `reset_indicator()` from indicators.py (from Task 2)
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

- [ ] **Step 2: Add docstrings to existing endpoints for better tool descriptions**

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
