# Services & Daemons Playbook

**Objective**: Ensure the TradingAgents dashboard server follows a consistent
lifecycle, logging, and management pattern.

## 1. Architecture: Single-Service Daemon

TradingAgents runs one background service: the dashboard server. It is managed
by `scripts/server-lifecycle.ts` using PID files and log capture.

**Key Principles**:
1.  **PID File Tracking**: Exact process identity. No `ps | grep` fragility.
2.  **Log Capture**: Server stdout/stderr written to `~/.tradingagents/server.log`.
3.  **Port Check**: Verify port 3000 is free before starting.
4.  **Stale Cleanup**: Remove dead PID files before starting.
5.  **Graceful Shutdown**: SIGTERM → wait → SIGKILL fallback.

## 2. Port Registry

| Service | Port | Env Var | Description |
|---------|------|---------|-------------|
| Dashboard Server | 3000 | `TA_DASHBOARD_PORT` | Hono + HTMX web UI |

## 3. File Locations

```
~/.tradingagents/
├── server.pid          # PID of running dashboard server
├── server.log          # stdout/stderr from last run
└── server.prev.log     # rotated on restart
```

Created on first run if absent.

## 4. Standard Interface

All service commands use `scripts/server-lifecycle.ts`:

| Command | What |
|---------|------|
| `just start` | Start dashboard server |
| `just serve` | Alias for `just start` |
| `just stop` | Stop dashboard server |
| `just restart` | Stop then start |
| `just status` | Show service status |
| `just ports` | Show all listening ports |

## 5. Implementation Details

### PID File Protocol

```
START:
  1. Read PID file if exists
  2. If PID alive → already running, abort
  3. If PID dead → remove stale file, continue
  4. Check port 3000 is free
  5. Spawn server with stdout/stderr → server.log
  6. Write PID to server.pid
  7. Health check: curl http://localhost:3000/health

STOP:
  1. Read PID from server.pid
  2. If no PID file → not running
  3. If PID not alive → stale file, remove it
  4. Send SIGTERM to PID
  5. Wait up to 5s, poll every 500ms
  6. If still alive → SIGKILL
  7. Remove PID file
```

### Log Rotation

On `restart`:
1. Rename `server.log` → `server.prev.log`
2. Start new server (creates fresh `server.log`)

### Stale PID Detection

```typescript
function isProcessAlive(pid: number): boolean {
  try { process.kill(pid, 0); return true }
  catch { return false }
}
```

`kill(pid, 0)` checks if process exists without sending a signal.

## 6. Best Practices

- **Never use `ps | grep` for PID discovery.** Always use the PID file.
- **Always redirect stdout/stderr to log file.** Otherwise output is lost.
- **Rotate logs on restart.** Prevents unbounded log growth.
- **Check port before start.** Fail fast with clear error: "Port 3000 in use by PID X".
- **Health check after start.** Verify `/health` responds within 5 seconds.

## 7. Future Expansion

If additional services are added (e.g. price sync daemon, analysis queue):

1. Add port to registry (3001, 3002, ...)
2. Add PID file: `~/.tradingagents/<service>.pid`
3. Add log file: `~/.tradingagents/<service>.log`
4. Add just verb: `just <service>-start`, `just <service>-stop`
5. Add to `just status` table
