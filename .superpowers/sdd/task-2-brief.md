# Task 2: Backend — Add `PATCH /api/indicators/{indicator_id}` Endpoint

## Task Description

**Files:**
- Modify: `web/server/indicators.py`
- Modify: `web/server/app.py`

## Requirements

### Step 1: Add `update_indicator` in `indicators.py`

Add this function after the `remove_indicator` function:

```python
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
                new_enabled = bool(new_enabled)
            rows[i] = IndicatorDefinition(
                id=row.id,
                kind=row.kind,
                name=row.name,
                description=row.description,
                threshold=new_threshold if new_threshold is not None else row.threshold,
                comparator=row.comparator,
                unit=row.unit,
                enabled=new_enabled if new_enabled is not None else row.enabled,
                source=row.source,
            )
            write_indicators(rows)
            return rows[i]
    return None
```

### Step 2: Register the PATCH endpoint in `app.py`

Inside `create_app()`, after the DELETE endpoint, add:

```python
@app.patch("/api/indicators/{indicator_id}")
def patch_indicator(indicator_id: str, body: dict) -> dict:
    try:
        updated = indicators.update_indicator(indicator_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="indicator not found")
    return indicators._definition_to_dict(updated)
```

### Step 3: Verify

Run `pytest tests/ -v -k "indicator" --tb=short` — must pass with no regressions.

## Context

The indicator infrastructure (models, storage, background scheduler, and all other CRUD endpoints) was added in Task 1. The `indicators` module and `from . import indicators` import already exist in `app.py`. The DELETE endpoint already exists at `@app.delete("/api/indicators/{indicator_id}", status_code=204)` — add the PATCH right after it.

## Report File

Write your full report to: `.superpowers/sdd/task-2-report.md`

Report back with:
- **Status:** DONE | BLOCKED
- Commits created
- One-line test summary
- Report file path