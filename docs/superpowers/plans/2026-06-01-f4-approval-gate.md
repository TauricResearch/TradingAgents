# F4 Event-Alert Approval Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace F4's auto-fire study trigger with a light-alert→approve→study gate: a triaged event produces a cheap event-scoped "light" brief with per-ticker approval buttons (Telegram + CLI); the heavy 3-team study runs only after the user approves a ticker.

**Architecture:** The promoter stops enqueuing studies. Instead it (1) makes one `quick_think_llm` summary call, (2) writes a `mode='event_alert_light'` brief scoped to the affected tickers, (3) creates one pending `run_full_study` `brief_actions` row per ticker, (4) suppresses each ticker for the rest of the local day, (5) delivers via the existing channels. On approval (Telegram button or `forge alert approve`), the action-handler enqueues the existing `event_alert` `queue_jobs` row; the worker runs the unchanged 3-persona study and writes the full brief, linked to the light brief by `parent_brief_id`. F5 follow-up actions (`run_backtest`, `refine_brief`) are untouched and operate on the resulting full brief.

**Tech Stack:** Python 3.14, SQLite (`tradingagents.persistence`), Typer CLI, python-telegram-bot, pytest (`@pytest.mark.unit`). Project Python: `/home/ziwei-huang/miniconda3/bin/python`. Repo root for all paths: `/home/ziwei-huang/TradingAgents/TradingAgents`.

**Spec:** `docs/superpowers/specs/2026-06-01-iic-forge-09-f4-approval-gate-design.md`

**Conventions observed:**
- Run a single test: `/home/ziwei-huang/miniconda3/bin/python -m pytest <path>::<test> -v`
- Commit after each green task. Branch is `feat/iic-forge-08-f5` (already checked out). Do NOT open a PR; pushes go to fork `VegarGG/TradingAgents` only when explicitly asked.
- Tests build a fresh DB with `connect(str(tmp_path / "iic.db"))`; `connect` auto-creates the schema. Seed with `store.insert_event`, `store.insert_event_ticker`, `store.upsert_watchlist`.

---

## File Structure

**Modify:**
- `tradingagents/orchestrator/promoter.py` — `run_once` now composes light alerts instead of enqueuing studies; `main` builds a quick LLM + light-alert composer.
- `tradingagents/secretary/service.py` — add `compose_event_alert_light()` (quick summary + light brief + per-ticker pending actions + suppression + delivery).
- `tradingagents/orchestrator/candidates.py` — group affected tickers per event so one event yields one light alert.
- `tradingagents/orchestrator/action_handler.py` — add `run_full_study` dispatch branch.
- `tradingagents/delivery/telegram.py` — per-ticker keyboard for `event_alert_light`.
- `tradingagents/delivery/telegram_bot.py` — callback parser handles the ticker field + `__all__`.
- `cli/forge.py` — register a `forge alert` sub-app.
- `tradingagents/persistence/store.py` — small query helpers for pending light-study actions.
- `ops/systemd/iic-morning.timer` — 07:00 → 06:00.
- `scripts/f4_exit_gate.py` — rewrite for alert-latency SLA.

**Create:**
- `cli/alert.py` — `forge alert list/approve/dismiss` commands.
- `tradingagents/delivery/templates/telegram/event_alert_light.j2`, `cli/event_alert_light.j2`, `email/event_alert_light.j2` — light-alert templates.
- `tests/secretary/test_compose_event_alert_light.py`
- `tests/orchestrator/test_promoter_light_alert.py`
- `tests/orchestrator/test_action_handler_run_full_study.py`
- `tests/delivery/test_telegram_light_alert.py`
- `tests/cli/test_forge_alert.py`

---

## Task 1: Config keys for the approval gate

**Files:**
- Modify: `tradingagents/default_config.py` (near the F4 block, lines 109-118)
- Test: `tests/test_default_config_f4.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_default_config_f4.py` inside `test_default_config_has_f4_keys` (after the existing `alert_ticker_confidence_threshold` assertion):

```python
    # F4 approval gate (IIC-FORGE-09)
    assert C["alert_approval_gate_enabled"] is True
    assert C["alert_pending_ttl_hours"] == 24
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/test_default_config_f4.py::test_default_config_has_f4_keys -v`
Expected: FAIL with `KeyError: 'alert_approval_gate_enabled'`

- [ ] **Step 3: Add the keys**

In `tradingagents/default_config.py`, immediately after the line `"alert_ticker_confidence_threshold": 0.9,`:

```python
    # F4 approval gate (IIC-FORGE-09): light alert → approve → study.
    # When False, the promoter would fall back to the legacy auto-enqueue path
    # (kept only as an escape hatch; default behavior is the gate).
    "alert_approval_gate_enabled": True,
    # How long a pending run_full_study approval stays valid (1 day per spec §4).
    "alert_pending_ttl_hours": 24,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/test_default_config_f4.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/default_config.py tests/test_default_config_f4.py
git commit -m "feat(f4): config keys for event-alert approval gate"
```

---

## Task 2: Store helpers for light-study actions

We need two query helpers: list pending `run_full_study` actions (for the CLI/gate) and check whether a ticker already has a same-day light alert (dedup is handled by `suppression`, but the CLI needs to enumerate pending alerts).

**Files:**
- Modify: `tradingagents/persistence/store.py` (after `fetch_actions`, ~line 392)
- Test: `tests/persistence/test_light_study_helpers.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/persistence/test_light_study_helpers.py`:

```python
import pytest
from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _seed_light_brief(conn, brief_id="lb1"):
    store.insert_brief(
        conn, brief_id=brief_id, mode="event_alert_light",
        scope='["NVDA", "PANW"]', generated_ts="2026-06-01T00:00:00+00:00",
        content_path=f"briefs/{brief_id}.md", run_ids=[],
        trigger_event_id="ev1",
    )


@pytest.mark.unit
def test_fetch_pending_run_full_study_actions(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light_brief(conn)
    store.insert_brief_action(conn, brief_id="lb1", action_type="run_full_study",
                              action_params={"ticker": "NVDA"},
                              expires_at="2099-01-01T00:00:00+00:00")
    store.insert_brief_action(conn, brief_id="lb1", action_type="run_full_study",
                              action_params={"ticker": "PANW"},
                              expires_at="2099-01-01T00:00:00+00:00")
    rows = store.fetch_pending_run_full_study(conn)
    assert len(rows) == 2
    tickers = sorted(__import__("json").loads(r["action_params"])["ticker"] for r in rows)
    assert tickers == ["NVDA", "PANW"]


@pytest.mark.unit
def test_fetch_pending_run_full_study_excludes_non_pending(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light_brief(conn)
    aid = store.insert_brief_action(conn, brief_id="lb1",
                                    action_type="run_full_study",
                                    action_params={"ticker": "NVDA"},
                                    expires_at="2099-01-01T00:00:00+00:00")
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at="2026-06-01T01:00:00+00:00")
    assert store.fetch_pending_run_full_study(conn) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/persistence/test_light_study_helpers.py -v`
Expected: FAIL with `AttributeError: module 'tradingagents.persistence.store' has no attribute 'fetch_pending_run_full_study'`

- [ ] **Step 3: Add the helper**

In `tradingagents/persistence/store.py`, after `fetch_actions` (the function ending ~line 392):

```python
def fetch_pending_run_full_study(conn: sqlite3.Connection) -> list[dict]:
    """All pending run_full_study actions (one per awaiting ticker), oldest
    first. Used by the `forge alert` CLI and the exit-gate evaluator."""
    rows = conn.execute(
        "SELECT a.*, b.trigger_event_id, b.scope "
        "FROM brief_actions a JOIN briefs b ON b.brief_id = a.brief_id "
        "WHERE a.action_type = 'run_full_study' AND a.state = 'pending' "
        "ORDER BY a.action_id",
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/persistence/test_light_study_helpers.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/persistence/store.py tests/persistence/test_light_study_helpers.py
git commit -m "feat(f4): store helper to list pending run_full_study actions"
```

---

## Task 3: Group candidates per event

The current `fetch_candidates` returns one row per (event, ticker). For one light alert per event we need them grouped. Add a thin grouping helper that preserves the existing query.

**Files:**
- Modify: `tradingagents/orchestrator/candidates.py`
- Test: `tests/orchestrator/test_candidates.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/orchestrator/test_candidates.py`:

```python
@pytest.mark.unit
def test_fetch_candidates_grouped_by_event(tmp_path):
    from tradingagents.persistence.db import connect
    from tradingagents.persistence import store
    from tradingagents.orchestrator.candidates import fetch_candidates_grouped

    conn = connect(str(tmp_path / "iic.db"))
    store.upsert_watchlist(conn, ticker="NVDA", ttl_until=None, tags=["user"])
    store.upsert_watchlist(conn, ticker="PANW", ttl_until=None, tags=["user"])
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts="2026-06-01T00:00:00+00:00", salience=0.9,
                       raw_path=None, status="triaged", deduped_of=None)
    store.insert_event_ticker(conn, event_id="ev1", ticker="NVDA", confidence=1.0)
    store.insert_event_ticker(conn, event_id="ev1", ticker="PANW", confidence=1.0)

    groups = fetch_candidates_grouped(conn, salience_threshold=0.85,
                                      ticker_conf_threshold=0.9, limit=50)
    assert len(groups) == 1
    assert groups[0]["event_id"] == "ev1"
    assert sorted(groups[0]["tickers"]) == ["NVDA", "PANW"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/orchestrator/test_candidates.py::test_fetch_candidates_grouped_by_event -v`
Expected: FAIL with `ImportError: cannot import name 'fetch_candidates_grouped'`

- [ ] **Step 3: Add the grouping helper**

In `tradingagents/orchestrator/candidates.py`, append:

```python
def fetch_candidates_grouped(
    conn: sqlite3.Connection,
    *,
    salience_threshold: float,
    ticker_conf_threshold: float,
    limit: int,
) -> List[dict]:
    """Like fetch_candidates, but groups the per-(event,ticker) rows into one
    dict per event: {event_id, ingested_ts, salience, tickers: [...]}. Preserves
    event order (oldest-first). ``limit`` bounds the number of underlying rows."""
    rows = fetch_candidates(
        conn,
        salience_threshold=salience_threshold,
        ticker_conf_threshold=ticker_conf_threshold,
        limit=limit,
    )
    grouped: "dict[str, dict]" = {}
    for r in rows:
        g = grouped.get(r["event_id"])
        if g is None:
            g = {
                "event_id": r["event_id"],
                "ingested_ts": r["ingested_ts"],
                "salience": r["salience"],
                "tickers": [],
            }
            grouped[r["event_id"]] = g
        g["tickers"].append(r["ticker"])
    return list(grouped.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/orchestrator/test_candidates.py -v`
Expected: PASS (all existing + new)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/orchestrator/candidates.py tests/orchestrator/test_candidates.py
git commit -m "feat(f4): group event-alert candidates per event"
```

---

## Task 4: Light-alert templates

Three Jinja templates for the light alert (one per channel). Body is the quick summary + affected tickers.

**Files:**
- Create: `tradingagents/delivery/templates/cli/event_alert_light.j2`
- Create: `tradingagents/delivery/templates/telegram/event_alert_light.j2`
- Create: `tradingagents/delivery/templates/email/event_alert_light.j2`
- Test: `tests/delivery/test_light_alert_render.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/delivery/test_light_alert_render.py`:

```python
import pytest
from tradingagents.delivery.render import render_for_channel


@pytest.mark.unit
@pytest.mark.parametrize("channel", ["cli", "telegram", "email"])
def test_light_alert_renders_summary_and_tickers(channel):
    brief = {
        "brief_id": "lb1",
        "mode": "event_alert_light",
        "summary": "Networking-sector outage report; vendors may see demand shifts.",
        "tickers": ["NVDA", "PANW"],
        "event_headline": "Sector outage",
    }
    out = render_for_channel(channel=channel, mode="event_alert_light", brief=brief)
    assert "Networking-sector outage" in out
    assert "NVDA" in out and "PANW" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/delivery/test_light_alert_render.py -v`
Expected: FAIL — `jinja2.exceptions.TemplateNotFound: cli/event_alert_light.j2`

- [ ] **Step 3: Create the three templates**

`tradingagents/delivery/templates/cli/event_alert_light.j2`:

```jinja
⚡ Event alert — {{ brief.event_headline }}

{{ brief.summary }}

Affected watchlist tickers (approve a full study with `forge alert approve {{ brief.brief_id }} --ticker <T>`):
{% for t in brief.tickers %}- {{ t }}
{% endfor %}
```

`tradingagents/delivery/templates/telegram/event_alert_light.j2`:

```jinja
⚡ *Event alert* — {{ brief.event_headline }}

{{ brief.summary }}

Affected watchlist tickers — tap to launch a full study:
{% for t in brief.tickers %}• {{ t }}
{% endfor %}
```

`tradingagents/delivery/templates/email/event_alert_light.j2`:

```jinja
<h2>⚡ Event alert — {{ brief.event_headline }}</h2>
<p>{{ brief.summary }}</p>
<p>Affected watchlist tickers:</p>
<ul>
{% for t in brief.tickers %}<li>{{ t }}</li>
{% endfor %}</ul>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/delivery/test_light_alert_render.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/delivery/templates/ tests/delivery/test_light_alert_render.py
git commit -m "feat(f4): light-alert templates (cli/telegram/email)"
```

---

## Task 5: Telegram per-ticker keyboard for light alerts

`_make_event_alert_keyboard` currently emits `[Run Backtest]/[Dismiss]` for a single brief. Add a light-alert keyboard with one button per ticker plus Study all / Dismiss all, using the protocol `act:<brief_id>:run_full_study:<ticker>` (and `__all__`).

**Files:**
- Modify: `tradingagents/delivery/telegram.py`
- Test: `tests/delivery/test_telegram_light_alert.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/delivery/test_telegram_light_alert.py`:

```python
import pytest


@pytest.mark.unit
def test_light_alert_keyboard_has_per_ticker_buttons():
    pytest.importorskip("telegram")
    from tradingagents.delivery.telegram import _make_light_alert_keyboard

    kb = _make_light_alert_keyboard("lb1", ["NVDA", "PANW"])
    # Flatten all buttons and collect callback_data
    datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "act:lb1:run_full_study:NVDA" in datas
    assert "act:lb1:run_full_study:PANW" in datas
    assert "act:lb1:run_full_study:__all__" in datas
    assert "act:lb1:run_full_study:__dismiss__" in datas
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/delivery/test_telegram_light_alert.py -v`
Expected: FAIL — `ImportError: cannot import name '_make_light_alert_keyboard'`

- [ ] **Step 3: Add the keyboard builder and wire it into `_send_impl`**

In `tradingagents/delivery/telegram.py`, after `_make_event_alert_keyboard`:

```python
def _make_light_alert_keyboard(brief_id: str, tickers: list[str]):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = []
    # One [Study <T>] button per affected ticker, two per row.
    cur: list = []
    for t in tickers:
        cur.append(InlineKeyboardButton(
            f"Study {t}",
            callback_data=f"act:{brief_id}:run_full_study:{t}",
        ))
        if len(cur) == 2:
            rows.append(cur)
            cur = []
    if cur:
        rows.append(cur)
    rows.append([
        InlineKeyboardButton(
            "✅ Study all", callback_data=f"act:{brief_id}:run_full_study:__all__"),
        InlineKeyboardButton(
            "✖ Dismiss all", callback_data=f"act:{brief_id}:run_full_study:__dismiss__"),
    ])
    return InlineKeyboardMarkup(rows)
```

Then in `_send_impl`, replace the keyboard line:

```python
        keyboard = _make_event_alert_keyboard(brief["brief_id"]) if mode == "event_alert" else None
```

with:

```python
        if mode == "event_alert":
            keyboard = _make_event_alert_keyboard(brief["brief_id"])
        elif mode == "event_alert_light":
            keyboard = _make_light_alert_keyboard(
                brief["brief_id"], brief.get("tickers", []))
        else:
            keyboard = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/delivery/test_telegram_light_alert.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/delivery/telegram.py tests/delivery/test_telegram_light_alert.py
git commit -m "feat(f4): per-ticker telegram keyboard for light alerts"
```

---

## Task 6: Telegram callback handles the ticker field + sentinels

`handle_callback` parses `act:<brief>:<type>:<answer>` and maps `yes→accepted / else→declined`. Extend it: for `run_full_study`, the 4th field is a ticker (accept that ticker's pending action), `__all__` (accept all pending tickers on the brief), or `__dismiss__` (decline all). Keep existing `run_backtest` `yes/no` behavior intact.

**Files:**
- Modify: `tradingagents/delivery/telegram_bot.py`
- Test: `tests/delivery/test_telegram_light_alert.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/delivery/test_telegram_light_alert.py`:

```python
from unittest.mock import AsyncMock, MagicMock
from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _seed_light_with_delivery(conn, brief_id="lb1", channel_ref="12345:678"):
    store.insert_brief(conn, brief_id=brief_id, mode="event_alert_light",
                       scope='["NVDA", "PANW"]',
                       generated_ts="2026-06-01T00:00:00+00:00",
                       content_path=f"briefs/{brief_id}.md", run_ids=[],
                       trigger_event_id="ev1")
    store.insert_delivery(conn, brief_id=brief_id, channel="telegram",
                          status="sent", sent_ts="2026-06-01T00:00:01+00:00",
                          channel_ref=channel_ref, skip_reason=None)
    for t in ("NVDA", "PANW"):
        store.insert_brief_action(conn, brief_id=brief_id,
                                  action_type="run_full_study",
                                  action_params={"ticker": t},
                                  expires_at="2099-01-01T00:00:00+00:00")


def _callback(data):
    u = MagicMock()
    u.callback_query.data = data
    u.callback_query.message.chat.id = 12345
    u.callback_query.message.message_id = 678
    u.callback_query.answer = AsyncMock()
    return u


@pytest.mark.unit
def test_callback_accepts_single_ticker(tmp_path):
    from tradingagents.delivery.telegram_bot import handle_callback
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light_with_delivery(conn)
    handle_callback(update=_callback("act:lb1:run_full_study:NVDA"), conn=conn)
    states = dict(conn.execute(
        "SELECT json_extract(action_params,'$.ticker'), state "
        "FROM brief_actions").fetchall())
    assert states["NVDA"] == "accepted"
    assert states["PANW"] == "pending"


@pytest.mark.unit
def test_callback_study_all_accepts_every_pending(tmp_path):
    from tradingagents.delivery.telegram_bot import handle_callback
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light_with_delivery(conn)
    handle_callback(update=_callback("act:lb1:run_full_study:__all__"), conn=conn)
    states = [r[0] for r in conn.execute("SELECT state FROM brief_actions")]
    assert states == ["accepted", "accepted"]


@pytest.mark.unit
def test_callback_dismiss_all_declines_every_pending(tmp_path):
    from tradingagents.delivery.telegram_bot import handle_callback
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light_with_delivery(conn)
    handle_callback(update=_callback("act:lb1:run_full_study:__dismiss__"), conn=conn)
    states = [r[0] for r in conn.execute("SELECT state FROM brief_actions")]
    assert states == ["declined", "declined"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/delivery/test_telegram_light_alert.py -k callback -v`
Expected: FAIL — single-ticker accept won't work; current code maps `NVDA` (not `yes`) to `declined` and has no per-ticker targeting.

- [ ] **Step 3: Extend `handle_callback`**

In `tradingagents/delivery/telegram_bot.py`, replace the body of `handle_callback` from the line `state = "accepted" if answer == "yes" else "declined"` through the `store.update_action_state(...)` call with:

```python
    if action_type == "run_full_study":
        _apply_run_full_study(conn, brief_id=brief_id, arg=answer)
    else:
        state = "accepted" if answer == "yes" else "declined"
        pending = store.get_pending_action_by_brief(
            conn, brief_id=brief_id, action_type=action_type,
        )
        if pending is not None:
            aid = pending["action_id"]
        else:
            expires = _expires_at(24)
            aid = store.insert_brief_action(
                conn, brief_id=brief_id, action_type=action_type,
                action_params={}, expires_at=expires,
            )
        store.update_action_state(
            conn, action_id=aid, state=state, responded_at=_utc_now_iso(),
        )
```

Then add this module-level helper above `handle_callback`:

```python
def _apply_run_full_study(conn: sqlite3.Connection, *, brief_id: str, arg: str) -> None:
    """Transition run_full_study actions for a light brief.

    arg is a ticker (accept that one), '__all__' (accept all pending), or
    '__dismiss__' (decline all pending). Only pending rows are touched, so a
    repeated click is a no-op (idempotent)."""
    import json as _j
    rows = conn.execute(
        "SELECT action_id, action_params FROM brief_actions "
        "WHERE brief_id = ? AND action_type = 'run_full_study' AND state = 'pending'",
        (brief_id,),
    ).fetchall()
    now = _utc_now_iso()
    for r in rows:
        ticker = _j.loads(r["action_params"]).get("ticker")
        if arg == "__all__":
            new_state = "accepted"
        elif arg == "__dismiss__":
            new_state = "declined"
        elif arg == ticker:
            new_state = "accepted"
        else:
            continue
        store.update_action_state(
            conn, action_id=r["action_id"], state=new_state, responded_at=now,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/delivery/test_telegram_light_alert.py tests/delivery/test_telegram_bot.py -v`
Expected: PASS (new light-alert callback tests + existing `run_backtest` callback tests all green)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/delivery/telegram_bot.py tests/delivery/test_telegram_light_alert.py
git commit -m "feat(f4): telegram callback handles per-ticker run_full_study"
```

---

## Task 7: `compose_event_alert_light` on the Secretary

The composer: one `quick_think_llm` summary call, write the `event_alert_light` brief (scope = JSON ticker list), create one pending `run_full_study` action per ticker, suppress each ticker until end of local day, and deliver via enabled channels. Returns the light brief_id.

**Files:**
- Modify: `tradingagents/secretary/service.py`
- Test: `tests/secretary/test_compose_event_alert_light.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/secretary/test_compose_event_alert_light.py`:

```python
import json
from unittest.mock import MagicMock
import pytest

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _seed_event(conn):
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts="2026-06-01T00:00:00+00:00", salience=0.9,
                       raw_path=None, status="triaged", deduped_of=None)


@pytest.mark.unit
def test_compose_light_creates_brief_actions_and_suppression(tmp_path):
    from tradingagents.secretary.service import Secretary
    conn = connect(str(tmp_path / "iic.db"))
    _seed_event(conn)
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="Short summary of the event.")
    sec = Secretary(conn=conn, data_dir=str(tmp_path / "data"), llm=llm)

    brief_id = sec.compose_event_alert_light(
        event_id="ev1", tickers=["NVDA", "PANW"], ttl_hours=24,
        deliver=False,
    )

    brief = store.get_brief(conn, brief_id=brief_id)
    assert brief["mode"] == "event_alert_light"
    assert sorted(json.loads(brief["scope"])) == ["NVDA", "PANW"]
    assert json.loads(brief["run_ids"]) == []
    assert brief["trigger_event_id"] == "ev1"

    actions = store.fetch_pending_run_full_study(conn)
    assert sorted(json.loads(a["action_params"])["ticker"] for a in actions) == ["NVDA", "PANW"]

    for t in ("NVDA", "PANW"):
        sup = conn.execute("SELECT * FROM suppression WHERE key=?",
                           (f"event_alert:{t}",)).fetchone()
        assert sup is not None
    # exactly one quick LLM call (the summary)
    assert llm.invoke.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/secretary/test_compose_event_alert_light.py -v`
Expected: FAIL — `AttributeError: 'Secretary' object has no attribute 'compose_event_alert_light'`

- [ ] **Step 3: Implement the composer**

First confirm the imports already present at the top of `tradingagents/secretary/service.py` include `json`, `uuid` (or `uuid4`), `Path`, `datetime`. Add any missing among these:

```python
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
```

Add this method to the `Secretary` class (after `compose_event_alert`):

```python
    def compose_event_alert_light(
        self,
        *,
        event_id: str,
        tickers: list,
        ttl_hours: int = 24,
        deliver: bool = True,
    ) -> str:
        """Light alert (IIC-FORGE-09): one quick summary + an event-scoped
        brief + one pending run_full_study action per ticker + per-ticker
        same-day suppression. NO persona study runs here — the heavy study is
        enqueued later, only on approval. Returns the light brief_id."""
        ev = store.get_event(self._conn, event_id=event_id)
        if ev is None:
            raise ValueError(f"compose_event_alert_light: event {event_id} not found")

        raw_text = ""
        if ev["raw_path"]:
            p = Path(ev["raw_path"])
            if p.exists():
                try:
                    raw_text = (json.loads(p.read_text(encoding="utf-8"))
                                .get("text", "") or "")
                except Exception:
                    raw_text = p.read_text(encoding="utf-8")[:4000]

        prompt = (
            "You are an equity-desk assistant. In 2-3 sentences, summarize why "
            "the following event might matter for the affected tickers "
            f"({', '.join(tickers)}). Be terse and factual.\n\n"
            f"EVENT:\n{raw_text[:4000]}"
        )
        resp = self._llm.invoke(prompt)
        summary = getattr(resp, "content", str(resp))

        brief_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        rel_path = f"briefs/{brief_id}.md"
        body = f"# Event alert (light)\n\n{summary}\n\nAffected: {', '.join(tickers)}\n"
        (self._data_dir / "briefs").mkdir(parents=True, exist_ok=True)
        (self._data_dir / rel_path).write_text(body, encoding="utf-8")

        store.insert_brief(
            self._conn,
            brief_id=brief_id,
            mode="event_alert_light",
            scope=json.dumps(list(tickers)),
            generated_ts=now.isoformat(),
            content_path=rel_path,
            run_ids=[],
            parent_brief_id=None,
            trigger_event_id=event_id,
        )

        expires_at = (now + timedelta(hours=ttl_hours)).isoformat()
        # End of local day: suppress each ticker until tomorrow 00:00 local.
        tomorrow = (datetime.now() + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        until_ts = tomorrow.astimezone(timezone.utc).isoformat()
        for t in tickers:
            store.insert_brief_action(
                self._conn, brief_id=brief_id, action_type="run_full_study",
                action_params={"ticker": t}, expires_at=expires_at,
            )
            store.upsert_suppression(
                self._conn, key=f"event_alert:{t}", until_ts=until_ts,
                reason=f"light_alert_same_day event_id={event_id}",
                created_by="promoter",
            )

        if deliver:
            self._deliver_light_alert(brief_id, tickers, summary, ev)
        return brief_id

    def _deliver_light_alert(self, brief_id, tickers, summary, ev) -> None:
        """Best-effort fan-out to enabled channels. Delivery failures are
        recorded as deliveries rows by each channel; never raise here."""
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.delivery.render import render_for_channel
        config = dict(DEFAULT_CONFIG)
        brief = {
            "brief_id": brief_id, "mode": "event_alert_light",
            "summary": summary, "tickers": list(tickers),
            "event_headline": (ev["source"] or "event"),
        }
        for name in config["delivery"]["enabled_channels"] + (
            ["telegram"] if config["telegram_bot"]["enabled"] else []
        ):
            try:
                ch = _build_channel(name, self._conn, config)
                if ch is None:
                    continue
                body = render_for_channel(
                    channel=name, mode="event_alert_light", brief=brief)
                ch.send(brief=brief, mode="event_alert_light", body=body)
            except Exception:  # noqa: BLE001
                pass
```

Add this module-level helper near the top of `service.py` (after imports):

```python
def _build_channel(name, conn, config):
    if name == "cli":
        from tradingagents.delivery.cli import CLIOutbound
        return CLIOutbound(conn=conn, config=config)
    if name == "email":
        from tradingagents.delivery.email import EmailOutbound
        return EmailOutbound(conn=conn, config=config)
    if name == "telegram":
        from tradingagents.delivery.telegram import TelegramOutbound
        return TelegramOutbound(conn=conn, config=config)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/secretary/test_compose_event_alert_light.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/secretary/service.py tests/secretary/test_compose_event_alert_light.py
git commit -m "feat(f4): Secretary.compose_event_alert_light (summary + light brief + pending actions)"
```

---

## Task 8: Promoter composes light alerts instead of enqueuing studies

Rewire `run_once` to call the light composer per grouped event when the gate is enabled. The promoter needs a Secretary (built in `main`).

**Files:**
- Modify: `tradingagents/orchestrator/promoter.py`
- Test: `tests/orchestrator/test_promoter_light_alert.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/orchestrator/test_promoter_light_alert.py`:

```python
import json
from unittest.mock import MagicMock
import pytest

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _now() -> str:
    return "2026-06-01T00:00:00+00:00"


@pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "iic.db"))
    store.upsert_watchlist(c, ticker="NVDA", ttl_until=None, tags=["user"])
    store.upsert_watchlist(c, ticker="PANW", ttl_until=None, tags=["user"])
    return c


def _seed_event(conn):
    store.insert_event(conn, event_id="ev1", source="rss", ingested_ts=_now(),
                       salience=0.9, raw_path=None, status="triaged",
                       deduped_of=None)
    store.insert_event_ticker(conn, event_id="ev1", ticker="NVDA", confidence=1.0)
    store.insert_event_ticker(conn, event_id="ev1", ticker="PANW", confidence=1.0)


@pytest.mark.unit
def test_run_once_gate_composes_one_light_alert_no_queue_job(conn):
    from tradingagents.orchestrator.promoter import run_once
    _seed_event(conn)
    sec = MagicMock()
    sec.compose_event_alert_light.return_value = "lb1"

    n = run_once(conn, salience_threshold=0.85, ticker_conf_threshold=0.9,
                 batch_size=50, cooldown_min=60, secretary=sec,
                 approval_gate_enabled=True, pending_ttl_hours=24)

    assert n == 1
    sec.compose_event_alert_light.assert_called_once()
    _, kwargs = sec.compose_event_alert_light.call_args
    assert kwargs["event_id"] == "ev1"
    assert sorted(kwargs["tickers"]) == ["NVDA", "PANW"]
    # No heavy study enqueued at this stage.
    assert conn.execute("SELECT COUNT(*) FROM queue_jobs").fetchone()[0] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/orchestrator/test_promoter_light_alert.py -v`
Expected: FAIL — `run_once()` got an unexpected keyword argument `secretary`.

- [ ] **Step 3: Rewire `run_once` and `main`**

In `tradingagents/orchestrator/promoter.py`, update the `run_once` signature to add the new params (keep existing ones), and import the grouping helper at top:

Replace `from tradingagents.orchestrator.candidates import fetch_candidates` with:

```python
from tradingagents.orchestrator.candidates import fetch_candidates, fetch_candidates_grouped
```

Replace the `run_once` signature and body from `candidates = fetch_candidates(...)` onward with:

```python
def run_once(
    conn: sqlite3.Connection,
    *,
    salience_threshold: float,
    ticker_conf_threshold: float,
    batch_size: int,
    cooldown_min: int,
    backpressure: Optional[QueueBackpressure] = None,
    rate_guard: Optional[QueueRateGuard] = None,
    secretary=None,
    approval_gate_enabled: bool = False,
    pending_ttl_hours: int = 24,
) -> int:
    """Perform one poll cycle. With the approval gate enabled, composes one
    light alert per event (no study enqueued). Returns the count of light
    alerts (gate) or jobs (legacy) created."""
    if backpressure is not None and not backpressure.gate(conn):
        return 0
    if rate_guard is not None and not rate_guard.gate(conn):
        return 0

    if approval_gate_enabled:
        if secretary is None:
            raise ValueError("run_once: approval_gate_enabled requires a secretary")
        groups = fetch_candidates_grouped(
            conn, salience_threshold=salience_threshold,
            ticker_conf_threshold=ticker_conf_threshold, limit=batch_size,
        )
        composed = 0
        for g in groups:
            try:
                secretary.compose_event_alert_light(
                    event_id=g["event_id"], tickers=g["tickers"],
                    ttl_hours=pending_ttl_hours, deliver=True,
                )
                composed += 1
                log.info("light alert composed event_id=%s tickers=%s",
                         g["event_id"], g["tickers"])
            except Exception:
                log.exception("light alert failed event_id=%s; continuing",
                              g["event_id"])
        return composed

    # ----- Legacy auto-enqueue path (approval gate disabled) -----
    candidates = fetch_candidates(
        conn,
        salience_threshold=salience_threshold,
        ticker_conf_threshold=ticker_conf_threshold,
        limit=batch_size,
    )
    if not candidates:
        return 0

    enqueued = 0
    for ev in candidates:
        until_ts = (_now_utc() + timedelta(minutes=cooldown_min)).isoformat()
        try:
            with conn:    # one atomic tx per event
                conn.execute(
                    "INSERT INTO queue_jobs (job_type, payload, state, "
                    "enqueued_ts, trigger_event_id) VALUES (?, ?, 'queued', ?, ?)",
                    (
                        "event_alert",
                        json.dumps({"event_id": ev["event_id"],
                                    "ticker": ev["ticker"]}),
                        _now_utc().isoformat(),
                        ev["event_id"],
                    ),
                )
                store.upsert_suppression(
                    conn,
                    key=f"event_alert:{ev['ticker']}",
                    until_ts=until_ts,
                    reason=f"alert_cooldown event_id={ev['event_id']}",
                    created_by="promoter",
                )
            enqueued += 1
            log.info("enqueued event_alert event_id=%s ticker=%s",
                     ev["event_id"], ev["ticker"])
        except sqlite3.OperationalError:
            log.exception("db error enqueueing event_id=%s; backing off",
                          ev["event_id"])
            time.sleep(2)
    return enqueued
```

Now update `main()` to build a Secretary and pass the gate params. Replace the `run_once(...)` call inside `main`'s `while` loop and add the Secretary build before the loop. After the `rate_guard = QueueRateGuard(...)` block in `main`, add:

```python
    gate_enabled = cfg["alert_approval_gate_enabled"]
    secretary = None
    if gate_enabled:
        from tradingagents.llm_clients.factory import create_llm_client
        from tradingagents.secretary.service import Secretary
        llm = create_llm_client(
            provider=cfg["llm_provider"], model=cfg["quick_think_llm"],
            base_url=cfg.get("backend_url"),
        ).get_llm()
        secretary = Secretary(conn=conn, data_dir=cfg["iic_data_dir"], llm=llm)
```

And replace the `run_once(...)` call with:

```python
            run_once(
                conn,
                salience_threshold=cfg["alert_salience_threshold"],
                ticker_conf_threshold=cfg["alert_ticker_confidence_threshold"],
                batch_size=cfg["promoter_batch_size"],
                cooldown_min=cfg["alert_cooldown_min"],
                backpressure=backpressure,
                rate_guard=rate_guard,
                secretary=secretary,
                approval_gate_enabled=gate_enabled,
                pending_ttl_hours=cfg["alert_pending_ttl_hours"],
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/orchestrator/test_promoter_light_alert.py tests/orchestrator/test_promoter_loop.py -v`
Expected: PASS — new gate test green; the legacy `test_promoter_loop.py` tests still pass because they call `run_once` without `approval_gate_enabled` (defaults False → legacy path).

- [ ] **Step 5: Commit**

```bash
git add tradingagents/orchestrator/promoter.py tests/orchestrator/test_promoter_light_alert.py
git commit -m "feat(f4): promoter composes light alerts under the approval gate"
```

---

## Task 9: Action-handler enqueues the study on approval

Add a `run_full_study` branch to `_dispatch_one`: read the ticker from `action_params`, insert an `event_alert` `queue_jobs` row (the existing heavy job), and mark the action done so it isn't re-dispatched.

**Files:**
- Modify: `tradingagents/orchestrator/action_handler.py`
- Test: `tests/orchestrator/test_action_handler_run_full_study.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/orchestrator/test_action_handler_run_full_study.py`:

```python
import json
from unittest.mock import MagicMock
import pytest

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _seed_light(conn, brief_id="lb1"):
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts="2026-06-01T00:00:00+00:00", salience=0.9,
                       raw_path=None, status="triaged", deduped_of=None)
    store.insert_brief(conn, brief_id=brief_id, mode="event_alert_light",
                       scope='["NVDA"]', generated_ts="2026-06-01T00:00:00+00:00",
                       content_path=f"briefs/{brief_id}.md", run_ids=[],
                       trigger_event_id="ev1")


@pytest.mark.unit
def test_accepted_run_full_study_enqueues_event_alert_job(tmp_path):
    from tradingagents.orchestrator.action_handler import tick
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light(conn)
    aid = store.insert_brief_action(conn, brief_id="lb1",
                                    action_type="run_full_study",
                                    action_params={"ticker": "NVDA"},
                                    expires_at="2099-01-01T00:00:00+00:00")
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at="2026-06-01T01:00:00+00:00")

    tick(conn=conn, secretary=MagicMock(), dispatch_backtest=MagicMock())

    job = conn.execute("SELECT job_type, payload, trigger_event_id "
                       "FROM queue_jobs").fetchone()
    assert job["job_type"] == "event_alert"
    assert json.loads(job["payload"]) == {"event_id": "ev1", "ticker": "NVDA"}
    assert job["trigger_event_id"] == "ev1"
    # action marked done (result_brief_id set) so it won't re-dispatch
    row = conn.execute("SELECT result_brief_id FROM brief_actions "
                       "WHERE action_id=?", (aid,)).fetchone()
    assert row[0] is not None


@pytest.mark.unit
def test_run_full_study_is_idempotent(tmp_path):
    from tradingagents.orchestrator.action_handler import tick
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light(conn)
    aid = store.insert_brief_action(conn, brief_id="lb1",
                                    action_type="run_full_study",
                                    action_params={"ticker": "NVDA"},
                                    expires_at="2099-01-01T00:00:00+00:00")
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at="2026-06-01T01:00:00+00:00")
    tick(conn=conn, secretary=MagicMock(), dispatch_backtest=MagicMock())
    tick(conn=conn, secretary=MagicMock(), dispatch_backtest=MagicMock())
    assert conn.execute("SELECT COUNT(*) FROM queue_jobs").fetchone()[0] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/orchestrator/test_action_handler_run_full_study.py -v`
Expected: FAIL — no `queue_jobs` row created; the handler logs "unknown action_type 'run_full_study'".

- [ ] **Step 3: Add the dispatch branch**

In `tradingagents/orchestrator/action_handler.py`, inside `_dispatch_one`, add a branch before the final `else:`:

```python
    elif row["action_type"] == "run_full_study":
        ticker = params.get("ticker")
        light = store.load_brief(conn, row["brief_id"])
        event_id = (light or {}).get("trigger_event_id")
        import json as _j2
        with conn:
            conn.execute(
                "INSERT INTO queue_jobs (job_type, payload, state, "
                "enqueued_ts, trigger_event_id) VALUES (?, ?, 'queued', "
                "datetime('now'), ?)",
                ("event_alert",
                 _j2.dumps({"event_id": event_id, "ticker": ticker}),
                 event_id),
            )
        # Mark done by linking back to the light brief so the row is not
        # re-dispatched; the resulting full brief links via parent_brief_id
        # when the worker finishes (not tracked here — the queue owns that).
        store.mark_action_done(conn, action_id=row["action_id"],
                               result_brief_id=row["brief_id"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/orchestrator/test_action_handler_run_full_study.py tests/orchestrator/test_action_handler.py -v`
Expected: PASS (new + existing F5 action-handler tests all green — proves coexistence)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/orchestrator/action_handler.py tests/orchestrator/test_action_handler_run_full_study.py
git commit -m "feat(f4): action-handler enqueues study on run_full_study approval"
```

---

## Task 10: Worker links the full brief to its light brief

When the approved study runs, the full `event_alert` brief should link back to the light brief via `parent_brief_id` for the audit chain. The job payload carries `event_id`; we look up the light brief for that event and pass its id into `compose_event_alert`.

**Files:**
- Modify: `tradingagents/orchestrator/dispatch.py`
- Modify: `tradingagents/secretary/service.py` (`compose_event_alert` accepts optional `parent_brief_id`)
- Test: `tests/orchestrator/test_worker_dispatch.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/orchestrator/test_worker_dispatch.py` (mirror its existing fixtures; this test asserts the parent link is threaded):

```python
@pytest.mark.unit
def test_dispatch_event_alert_links_parent_light_brief(tmp_path):
    import json
    from unittest.mock import MagicMock
    from tradingagents.persistence.db import connect
    from tradingagents.persistence import store
    from tradingagents.orchestrator.dispatch import dispatch_event_alert

    conn = connect(str(tmp_path / "iic.db"))
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts="2026-06-01T00:00:00+00:00", salience=0.9,
                       raw_path=None, status="triaged", deduped_of=None)
    # a light brief already exists for this event
    store.insert_brief(conn, brief_id="lb1", mode="event_alert_light",
                       scope='["NVDA"]', generated_ts="2026-06-01T00:00:00+00:00",
                       content_path="briefs/lb1.md", run_ids=[],
                       trigger_event_id="ev1")
    # full brief the secretary is mocked to produce
    store.insert_brief(conn, brief_id="fb1", mode="event_alert", scope="NVDA",
                       generated_ts="2026-06-01T00:10:00+00:00",
                       content_path="briefs/fb1.md", run_ids=["r1"],
                       parent_brief_id="lb1", trigger_event_id="ev1")
    sec = MagicMock()
    sec.compose_event_alert.return_value = "fb1"

    job = {"job_id": 1, "payload": json.dumps({"event_id": "ev1", "ticker": "NVDA"})}
    dispatch_event_alert(conn, job, secretary=sec)

    _, kwargs = sec.compose_event_alert.call_args
    assert kwargs["parent_brief_id"] == "lb1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/orchestrator/test_worker_dispatch.py::test_dispatch_event_alert_links_parent_light_brief -v`
Expected: FAIL — `compose_event_alert` called without `parent_brief_id` (TypeError or assertion fails).

- [ ] **Step 3: Thread the parent link**

In `tradingagents/secretary/service.py`, change `compose_event_alert` signature to accept an optional parent and pass it to `insert_brief`:

```python
    def compose_event_alert(
        self,
        *,
        event_id: str,
        ticker: str,
        job_id: int,
        parent_brief_id: Optional[str] = None,
    ) -> str:
```

and in its `store.insert_brief(...)` call add `parent_brief_id=parent_brief_id,`. (Confirm `Optional` is imported in `service.py`; it is used elsewhere in the file.)

In `tradingagents/orchestrator/dispatch.py`, in `dispatch_event_alert`, before the `secretary.compose_event_alert(...)` call:

```python
    # Link the full brief back to the light alert for the same event, if any.
    parent_row = conn.execute(
        "SELECT brief_id FROM briefs WHERE mode = 'event_alert_light' "
        "AND trigger_event_id = ? ORDER BY generated_ts DESC LIMIT 1",
        (event_id,),
    ).fetchone()
    parent_brief_id = parent_row[0] if parent_row else None
```

and update the call:

```python
    brief_id = secretary.compose_event_alert(
        event_id=event_id, ticker=ticker, job_id=job_id,
        parent_brief_id=parent_brief_id,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/orchestrator/test_worker_dispatch.py -v`
Expected: PASS (new + existing)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/secretary/service.py tradingagents/orchestrator/dispatch.py tests/orchestrator/test_worker_dispatch.py
git commit -m "feat(f4): link full event_alert brief to its light alert via parent_brief_id"
```

---

## Task 11: `forge alert` CLI (list / approve / dismiss)

**Files:**
- Create: `cli/alert.py`
- Modify: `cli/forge.py` (register the sub-app)
- Test: `tests/cli/test_forge_alert.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/cli/test_forge_alert.py`:

```python
import json
import pytest
from typer.testing import CliRunner

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _seed(conn):
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts="2026-06-01T00:00:00+00:00", salience=0.9,
                       raw_path=None, status="triaged", deduped_of=None)
    store.insert_brief(conn, brief_id="lb1", mode="event_alert_light",
                       scope='["NVDA", "PANW"]',
                       generated_ts="2026-06-01T00:00:00+00:00",
                       content_path="briefs/lb1.md", run_ids=[],
                       trigger_event_id="ev1")
    for t in ("NVDA", "PANW"):
        store.insert_brief_action(conn, brief_id="lb1",
                                  action_type="run_full_study",
                                  action_params={"ticker": t},
                                  expires_at="2099-01-01T00:00:00+00:00")


@pytest.mark.unit
def test_forge_alert_list_and_approve(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    conn = connect(str(tmp_path / "iic.db"))
    _seed(conn)

    from cli.forge import app
    runner = CliRunner()

    res = runner.invoke(app, ["alert", "list"])
    assert res.exit_code == 0
    assert "lb1" in res.stdout and "NVDA" in res.stdout

    res = runner.invoke(app, ["alert", "approve", "lb1", "--ticker", "NVDA"])
    assert res.exit_code == 0

    conn2 = connect(str(tmp_path / "iic.db"))
    states = dict((json.loads(r["action_params"])["ticker"], r["state"])
                  for r in conn2.execute(
                      "SELECT action_params, state FROM brief_actions"))
    assert states["NVDA"] == "accepted"
    assert states["PANW"] == "pending"


@pytest.mark.unit
def test_forge_alert_approve_all(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    conn = connect(str(tmp_path / "iic.db"))
    _seed(conn)
    from cli.forge import app
    runner = CliRunner()
    res = runner.invoke(app, ["alert", "approve", "lb1"])
    assert res.exit_code == 0
    conn2 = connect(str(tmp_path / "iic.db"))
    states = [r[0] for r in conn2.execute("SELECT state FROM brief_actions")]
    assert states == ["accepted", "accepted"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/cli/test_forge_alert.py -v`
Expected: FAIL — `No such command 'alert'`.

- [ ] **Step 3: Create `cli/alert.py` and register it**

Create `cli/alert.py`:

```python
"""`forge alert` — list / approve / dismiss pending event-alert light studies."""

from __future__ import annotations

import json
import typer
from rich.console import Console
from rich.table import Table

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.persistence.db import connect
from tradingagents.persistence import store


alert_app = typer.Typer(name="alert", help="Event-alert light-study approvals")
console = Console()


def _conn():
    import os
    db_path = os.environ.get("TRADINGAGENTS_IIC_DB_PATH") or DEFAULT_CONFIG["iic_db_path"]
    return connect(db_path)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _transition(conn, brief_id: str, ticker: str | None, state: str) -> int:
    rows = conn.execute(
        "SELECT action_id, action_params FROM brief_actions "
        "WHERE brief_id = ? AND action_type = 'run_full_study' AND state = 'pending'",
        (brief_id,),
    ).fetchall()
    n = 0
    for r in rows:
        t = json.loads(r["action_params"]).get("ticker")
        if ticker is None or ticker.upper() == t:
            store.update_action_state(conn, action_id=r["action_id"],
                                      state=state, responded_at=_utc_now_iso())
            n += 1
    return n


@alert_app.command("list")
def alert_list() -> None:
    """Show pending light-study approvals (one row per awaiting ticker)."""
    conn = _conn()
    rows = store.fetch_pending_run_full_study(conn)
    if not rows:
        console.print("(no pending alerts)")
        return
    t = Table("light_brief", "event", "ticker", "expires")
    for r in rows:
        t.add_row(r["brief_id"][:8], (r["trigger_event_id"] or "")[:8],
                  json.loads(r["action_params"])["ticker"], r["expires_at"][:19])
    console.print(t)


@alert_app.command("approve")
def alert_approve(
    brief_id: str,
    ticker: str = typer.Option(None, "--ticker", help="Approve one ticker; omit for all"),
) -> None:
    """Approve a full study for one or all tickers on a light alert."""
    conn = _conn()
    n = _transition(conn, brief_id, ticker, "accepted")
    console.print(f"[green]approved[/green] {n} ticker(s) on {brief_id[:8]}")


@alert_app.command("dismiss")
def alert_dismiss(
    brief_id: str,
    ticker: str = typer.Option(None, "--ticker", help="Dismiss one ticker; omit for all"),
) -> None:
    """Dismiss (decline) one or all tickers on a light alert."""
    conn = _conn()
    n = _transition(conn, brief_id, ticker, "declined")
    console.print(f"[yellow]dismissed[/yellow] {n} ticker(s) on {brief_id[:8]}")
```

In `cli/forge.py`, after the action-handler registration at the bottom:

```python
from cli.alert import alert_app  # noqa: E402
app.add_typer(alert_app, name="alert")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/cli/test_forge_alert.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add cli/alert.py cli/forge.py tests/cli/test_forge_alert.py
git commit -m "feat(f4): forge alert CLI (list/approve/dismiss)"
```

---

## Task 12: Morning timer 07:00 → 06:00

**Files:**
- Modify: `ops/systemd/iic-morning.timer`
- Test: `tests/ops/test_morning_timer.py` (create — a static assertion on the unit file)

- [ ] **Step 1: Write the failing test**

Create `tests/ops/test_morning_timer.py`:

```python
import pathlib
import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_morning_timer_fires_at_0600():
    txt = (REPO / "ops/systemd/iic-morning.timer").read_text()
    assert "OnCalendar=*-*-* 06:00:00" in txt
    assert "07:00:00" not in txt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/ops/test_morning_timer.py -v`
Expected: FAIL — still `07:00:00`.

- [ ] **Step 3: Edit the timer**

In `ops/systemd/iic-morning.timer`, change `OnCalendar=*-*-* 07:00:00` to `OnCalendar=*-*-* 06:00:00`.

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/ops/test_morning_timer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ops/systemd/iic-morning.timer tests/ops/test_morning_timer.py
git commit -m "chore(f5): move morning digest timer to 06:00"
```

---

## Task 13: Rewrite the F4 exit-gate evaluator (alert-latency SLA)

Replace the event→brief p95 logic with event→light-brief p95 (≤ 5 min), keep the restart audit, and add the approval-plumbing check.

**Files:**
- Modify: `scripts/f4_exit_gate.py`
- Test: `tests/orchestrator/test_f4_exit_gate_evaluator.py` (rewrite the latency-relevant tests)

- [ ] **Step 1: Write the failing test**

Replace the body of `tests/orchestrator/test_f4_exit_gate_evaluator.py` with (mirror its existing imports/fixtures for `evaluate`; this asserts the new alert-latency semantics):

```python
import pytest
from datetime import datetime, timedelta, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from scripts.f4_exit_gate import evaluate


def _iso(dt): return dt.isoformat()


@pytest.mark.unit
def test_alert_latency_pass(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    # event ingested at base; light brief 1 min later → within 5-min SLA
    store.insert_event(conn, event_id="ev1", source="rss", ingested_ts=_iso(base),
                       salience=0.9, raw_path=None, status="triaged", deduped_of=None)
    store.insert_brief(conn, brief_id="lb1", mode="event_alert_light",
                       scope='["NVDA"]', generated_ts=_iso(base + timedelta(minutes=1)),
                       content_path="briefs/lb1.md", run_ids=[], trigger_event_id="ev1")
    res = evaluate(conn, since=base - timedelta(minutes=1), window_hours=1)
    assert res["alert_count"] == 1
    assert res["sla_pass"] is True
    assert res["alert_latency_p95_s"] <= 5 * 60


@pytest.mark.unit
def test_alert_latency_fail(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    store.insert_event(conn, event_id="ev1", source="rss", ingested_ts=_iso(base),
                       salience=0.9, raw_path=None, status="triaged", deduped_of=None)
    store.insert_brief(conn, brief_id="lb1", mode="event_alert_light",
                       scope='["NVDA"]', generated_ts=_iso(base + timedelta(minutes=12)),
                       content_path="briefs/lb1.md", run_ids=[], trigger_event_id="ev1")
    res = evaluate(conn, since=base - timedelta(minutes=1), window_hours=1)
    assert res["sla_pass"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/orchestrator/test_f4_exit_gate_evaluator.py -v`
Expected: FAIL — `evaluate` returns the old `brief_count`/`latency_p95_s` keys, not `alert_count`/`alert_latency_p95_s`.

- [ ] **Step 3: Rewrite `evaluate` (and `render_md`) in `scripts/f4_exit_gate.py`**

Replace the `evaluate` function with the alert-latency version (keep `_percentile`, `_latency_seconds`, `_systemctl_nrestarts` as-is):

```python
def evaluate(
    conn: sqlite3.Connection, *, since: datetime, window_hours: int = 12,
) -> Dict[str, Any]:
    until = since + timedelta(hours=window_hours)

    rows = list(conn.execute(
        "SELECT b.brief_id, b.generated_ts, b.trigger_event_id, b.scope, "
        "       e.ingested_ts "
        "FROM briefs b JOIN events e ON e.event_id = b.trigger_event_id "
        "WHERE b.mode = 'event_alert_light' "
        "  AND b.generated_ts BETWEEN ? AND ?",
        (since.isoformat(), until.isoformat()),
    ))

    latencies = [_latency_seconds(r["ingested_ts"], r["generated_ts"]) for r in rows]
    n = len(latencies)
    SLA_S = 5 * 60
    if n >= 3:
        metric = _percentile(latencies, 0.95); rule = "p95"
        sla_pass = metric <= SLA_S
    elif n >= 1:
        metric = max(latencies); rule = "max"
        sla_pass = metric <= SLA_S
    else:
        metric = 0.0; rule = "none"; sla_pass = None

    # Approval plumbing: at least one light alert produced a full brief.
    approved = conn.execute(
        "SELECT COUNT(*) FROM briefs WHERE mode='event_alert' "
        "AND parent_brief_id IS NOT NULL "
        "AND generated_ts BETWEEN ? AND ?",
        (since.isoformat(), until.isoformat()),
    ).fetchone()[0]

    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "alert_count": n,
        "alert_latency_p50_s": _percentile(latencies, 0.50) if n else 0.0,
        "alert_latency_p95_s": _percentile(latencies, 0.95) if n else 0.0,
        "sla_pass": sla_pass,
        "sla_rule_applied": rule,
        "approved_full_briefs": approved,
        "promoter_nrestarts": _systemctl_nrestarts("iic-promoter"),
        "worker_nrestarts": _systemctl_nrestarts("iic-worker"),
    }
```

Replace `render_md` with a version that reads the new keys:

```python
def render_md(result: Dict[str, Any]) -> str:
    out: List[str] = []
    today = datetime.now(timezone.utc).date().isoformat()
    out.append(f"# F4 exit-gate report (approval gate) — {today}")
    out.append("")
    out.append(f"**Window:** `{result['since']}` → `{result['until']}`")
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append(f"- light alerts produced: **{result['alert_count']}**")
    out.append(f"- alert latency p50 / p95: "
               f"{result['alert_latency_p50_s']/60:.2f} / "
               f"{result['alert_latency_p95_s']/60:.2f} min")
    out.append(f"- approved full briefs: **{result['approved_full_briefs']}**")
    out.append("")
    out.append("## Restart audit")
    out.append("")
    out.append(f"- iic-promoter NRestarts: `{result['promoter_nrestarts']}` (must be 0)")
    out.append(f"- iic-worker NRestarts:   `{result['worker_nrestarts']}` (must be 0)")
    out.append("")
    out.append("## SLA verdict (alert latency ≤ 5 min)")
    out.append("")
    sla = result["sla_pass"]; rule = result["sla_rule_applied"]
    if sla is None:
        out.append("- **inconclusive** — 0 light alerts landed in window.")
    elif sla:
        out.append(f"- **PASS** (rule: {rule}, ≤ 5 min)")
    else:
        out.append(f"- **FAIL** (rule: {rule}, > 5 min)")
    out.append("")
    out.append("## Operator sign-off")
    out.append("")
    out.append("- [ ] Operator confirms restart audit, alert-latency SLA, and "
               "that ≥1 approved study produced a full brief.")
    return "\n".join(out)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/orchestrator/test_f4_exit_gate_evaluator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/f4_exit_gate.py tests/orchestrator/test_f4_exit_gate_evaluator.py
git commit -m "feat(f4): exit-gate evaluator measures alert latency (<=5min) + approval plumbing"
```

---

## Task 14: End-to-end smoke test (rewrite `tests/smoke/test_f4_exit_gate.py`)

Drives the whole light→approve→study→full-brief chain with mocked personas/LLM.

**Files:**
- Modify: `tests/smoke/test_f4_exit_gate.py`

- [ ] **Step 1: Write the failing test**

Replace `tests/smoke/test_f4_exit_gate.py` with:

```python
import json
from unittest.mock import MagicMock, patch
import pytest

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


@pytest.mark.smoke
def test_light_alert_approve_then_study(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.upsert_watchlist(conn, ticker="NVDA", ttl_until=None, tags=["user"])
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts="2026-06-01T00:00:00+00:00", salience=0.9,
                       raw_path=None, status="triaged", deduped_of=None)
    store.insert_event_ticker(conn, event_id="ev1", ticker="NVDA", confidence=1.0)

    # 1) promoter composes the light alert (quick LLM mocked)
    from tradingagents.orchestrator.promoter import run_once
    from tradingagents.secretary.service import Secretary
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="summary")
    sec = Secretary(conn=conn, data_dir=str(tmp_path / "data"), llm=llm)
    n = run_once(conn, salience_threshold=0.85, ticker_conf_threshold=0.9,
                 batch_size=50, cooldown_min=60, secretary=sec,
                 approval_gate_enabled=True, pending_ttl_hours=24)
    assert n == 1
    light = conn.execute("SELECT brief_id FROM briefs WHERE mode='event_alert_light'").fetchone()
    assert light is not None
    assert conn.execute("SELECT COUNT(*) FROM queue_jobs").fetchone()[0] == 0

    # 2) approve via the store transition the CLI/bot would do
    aid = conn.execute("SELECT action_id FROM brief_actions").fetchone()[0]
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at="2026-06-01T00:01:00+00:00")

    # 3) action-handler enqueues the heavy study
    from tradingagents.orchestrator.action_handler import tick
    tick(conn=conn, secretary=MagicMock(), dispatch_backtest=MagicMock())
    job = conn.execute("SELECT payload FROM queue_jobs").fetchone()
    assert json.loads(job["payload"]) == {"event_id": "ev1", "ticker": "NVDA"}
```

- [ ] **Step 2: Run test to verify it fails then passes**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/smoke/test_f4_exit_gate.py -v`
Expected: PASS (all prior tasks already implement the chain; if it fails, the failure points at the specific integration gap to fix before proceeding).

- [ ] **Step 3: Commit**

```bash
git add tests/smoke/test_f4_exit_gate.py
git commit -m "test(f4): end-to-end light-alert→approve→study smoke test"
```

---

## Task 15: Full suite + F5 coexistence regression

- [ ] **Step 1: Run the F5 follow-up tests to prove no conflict**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/orchestrator/test_action_handler.py tests/delivery/ tests/cli/test_forge_action_handler.py -v`
Expected: PASS — `run_backtest` and `refine_brief` behavior unchanged.

- [ ] **Step 2: Run the whole orchestrator + secretary + cli + delivery suites**

Run: `/home/ziwei-huang/miniconda3/bin/python -m pytest tests/orchestrator/ tests/secretary/ tests/cli/ tests/delivery/ tests/persistence/ tests/ops/ tests/smoke/test_f4_exit_gate.py tests/test_default_config_f4.py -q`
Expected: all PASS.

- [ ] **Step 3: Commit any test-only fixups**

If a pre-existing test referenced the old auto-enqueue behavior (e.g. asserted a `queue_jobs` row appears straight from the promoter under the gate), update it to the new model and commit:

```bash
git add -A
git commit -m "test(f4): align legacy tests with approval-gate behavior"
```

---

## Self-Review Notes

- **Spec §3 flow** → Tasks 7 (compose+deliver), 8 (promoter), 9 (approve→enqueue), 10 (worker link).
- **Spec §4 data model** (light brief, run_full_study action, same-day suppression) → Tasks 7, 2; no new tables.
- **Spec §5 interface** (per-ticker Telegram buttons + `forge alert` CLI) → Tasks 5, 6, 11.
- **Spec §6 gate/SLA** (alert latency ≤ 5 min, approval plumbing) → Task 13.
- **Spec §7 testing** (unit per component, smoke, F5 coexistence) → Tasks 3,5,6,7,8,9,11 unit; 14 smoke; 15 coexistence.
- **Attached requirements:** morning timer 06:00 → Task 12; F5 follow-up untouched → verified in Tasks 9 & 15.
- **Type consistency:** `run_full_study` action_type, `event_alert_light` mode, callback arg sentinels `__all__`/`__dismiss__`, and `compose_event_alert_light(event_id, tickers, ttl_hours, deliver)` are used identically across Tasks 5–11.
