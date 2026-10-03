# BRIEF: ALERTS-PHASE2 — Custom User-Defined Alerts

## Context

ALERTS-PHASE1 (`src/cli/commands/alerts.ts`) delivered a read-only exit-plan checker: runs against YAML exit plans, prints gum-formatted tables, no configuration.

**The gap:** Users cannot define custom alert rules (e.g. "alert me when AAPL drops below $150" or "tell me when NVDA moves 5% in a day"). The system is passive — someone must run `trading alerts` manually.

ALERTS-PHASE2 fills this gap: a persistent alert rule store in SQLite, CRUD CLI, and Telegram dispatch.

---

## Goals

1. **Persistent alert rules** — stored in SQLite, survive restarts
2. **CRUD CLI** — `trading alerts create|list|delete|edit`
3. **Alert matching engine** — lightweight TypeScript function (no daemon yet)
4. **Telegram dispatch** — send alert notifications via existing Telegram setup
5. **Dashboard route** — view active alerts in browser

Not in scope (ALERTS-PHASE3): monitoring daemon, SSE push stream.

---

## Design

### 1. SQLite Schema — `alerts` table

```sql
CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    ticker      TEXT,                           -- NULL = cross-ticker (e.g. % change)
    condition   TEXT NOT NULL,                 -- JSON: {type, threshold, direction}
    platform    TEXT DEFAULT 'all',
    severity    TEXT DEFAULT 'warning' CHECK(severity IN ('critical','warning','info')),
    message     TEXT,                           -- custom message template
    channel     TEXT DEFAULT 'telegram' CHECK(channel IN ('telegram','email','webhook','none')),
    enabled     INTEGER DEFAULT 1,
    last_checked TEXT,
    last_triggered TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(name)
);
```

### 2. Condition Types

| Type | Description | Example |
|------|-------------|---------|
| `price_below` | Close ≤ threshold | `{type:"price_below", threshold:150.0}` |
| `price_above` | Close ≥ threshold | `{type:"price_above", threshold:200.0}` |
| `pct_change_day` | \|daily % change\| ≥ threshold | `{type:"pct_change_day", threshold:5.0}` |
| `pct_change_week` | Weekly % change ≥ threshold | `{type:"pct_change_week", threshold:10.0}` |
| `signal_change` | Signal differs from last | `{type:"signal_change"}` |
| `price_cross` | Price crosses threshold (direction) | `{type:"price_cross", threshold:155.0, direction:"down"}` |

### 3. CLI Commands

```
trading alerts create [flags]
  --name           Alert name (unique)
  --ticker         Ticker to monitor (optional)
  --condition      JSON condition object (required)
  --platform       Filter by platform (default: all)
  --severity       critical|warning|info (default: warning)
  --message        Custom message (optional)
  --channel        telegram|email|webhook|none (default: telegram)

trading alerts list              # tabular view of all alerts
trading alerts delete <id>       # delete by ID
trading alerts edit <id> [flags] # update fields
trading alerts check             # run matching engine (dry-run: show what would fire)
trading alerts fire --id <id>   # manually trigger dispatch for one alert
```

### 4. Alert Matching Engine — `src/server/lib/alerts-engine.ts`

Pure function: given `alerts[]` and `prices{}` map, returns triggered alerts.

```typescript
interface TriggeredAlert {
  alert: AlertRule
  currentPrice: number | null
  pctChange?: number
  message: string
}

// Returns all alerts whose conditions are currently met
function matchAlerts(alerts: AlertRule[], prices: Record<string, number>): TriggeredAlert[]
```

### 5. Telegram Dispatch — `src/server/lib/telegram.ts`

Reuse existing Telegram setup (check `playbooks/` for existing Telegram skill). Send via Bot API.

```typescript
interface TelegramMessage {
  text: string          // Markdown-formatted
  parse_mode: "MarkdownV2"
  chat_id: string       // from config
}
```

**Config key:** `TELEGRAM_CHAT_ID` (IG config already has skate; check if TELEGRAM_BOT_TOKEN is in env).

### 6. Dashboard Route — `src/server/routes/alerts.tsx`

- `GET /alerts` — full page: list of alert rules with status, create form
- `GET /alerts/partial` — HTMX partial: just the table (for refresh)
- `POST /alerts` — create alert (HTMX response with swap)
- `DELETE /alerts/:id` — delete alert

---

## File Map

```
src/server/lib/
  alerts-engine.ts    ← matching engine (new)
  alerts-db.ts       ← SQLite CRUD helpers (new)
  telegram.ts        ← send helper (new)

src/cli/commands/
  alerts.ts          ← extend: add create|list|delete|edit subcommands (edit existing)

src/server/routes/
  alerts.tsx         ← dashboard route (new)

src/server/views/
  alerts.tsx         ← dashboard view (new)

src/server/lib/schema.sql
  alerts table DDL   ← add to existing schema

scripts/
  check-alerts.ts    ← CLI runner for alert matching + dispatch (new)
```

---

## Constraints

- **No new Python** — alerts engine is TypeScript
- **No daemon** — `check-alerts.ts` is a one-shot or `just check-alerts` manual run
- **Telegram secrets** — must not hardcode; read from environment/config
- **Graceful degradation** — if Telegram send fails, log error, don't crash

---

## Testing Strategy

1. Smoke test: `sqlite3 portfolio.db "SELECT 1"` confirms schema
2. CRUD test: create → list → delete → list (verify gone)
3. Engine test: seed alerts + prices → `matchAlerts()` → assert triggered set
4. Manual: `trading alerts create ... && just check-alerts`

---

## Success Criteria

- [ ] `trading alerts create --name "NVDA below 100" --ticker NVDA --condition '{"type":"price_below","threshold":100}' --severity critical` creates a rule
- [ ] `trading alerts list` shows the new rule
- [ ] `scripts/check-alerts.ts` correctly identifies triggered alerts
- [ ] Dashboard at `/alerts` displays all rules with create form
- [ ] Telegram message fires on triggered alert (manual test)
- [ ] `just check` green throughout

---

## Dependencies

- `TELEGRAM_BOT_TOKEN` — Bot API token (check env or skate config)
- `TELEGRAM_CHAT_ID` — Target chat ID
- SQLite `alerts` table (migrations via `just migrate` or inline IF NOT EXISTS)
