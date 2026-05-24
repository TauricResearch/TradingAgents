# Services & Daemons Playbook

**Objective**: Ensure the TradingAgents dashboard server follows a consistent
lifecycle, logging, and management pattern.

**One-sentence rule:** `just start` means start. Kill whatever is on the port,
write the PID, print "started", exit. No ifs, no buts.

---

## 1. Architecture: Single-Service Daemon

TradingAgents runs one background service: the dashboard server. It is managed
by `scripts/server-lifecycle.ts` using PID files and log capture.

**Key Principles**:
1.  **PID File Tracking**: Exact process identity. No `ps | grep` fragility.
2.  **Log Capture**: Server stdout/stderr written to `~/.tradingagents/server.log`.
3.  **Kill Port Before Start**: Whatever is on port 3000 dies. No questions.
4.  **Stale Cleanup**: Remove dead PID files before starting.
5.  **Graceful Shutdown**: SIGTERM → wait → SIGKILL fallback.

---

## 2. Port Registry

| Service | Port | Env Var | Description |
|---------|------|---------|-------------|
| Dashboard Server | 3000 | `TA_DASHBOARD_PORT` | Hono + HTMX web UI |

---

## 3. File Locations

```
~/.tradingagents/
├── server.pid          # PID of running dashboard server
├── server.log          # stdout/stderr from last run
└── server.prev.log     # rotated on restart
```

Created on first run if absent.

---

## 4. Standard Interface

All service commands use `scripts/server-lifecycle.ts`:

| Command | What |
|---------|------|
| `just start` | Start dashboard server (kills port 3000 first) |
| `just serve` | Alias for `just start` |
| `just stop` | Stop dashboard server |
| `just restart` | Kill port 3000, kill PID, start fresh |
| `just status` | Show service status |
| `just ports` | Show all listening ports |

---

## 5. Implementation Details

### Start Protocol

**Philosophy: Start means start. No ifs, no buts.**

```
START:
  1. Kill whatever is listening on port 3000 (lsof | xargs kill -9)
  2. Kill whatever PID is in server.pid (SIGKILL)
  3. Remove stale PID file
  4. Rotate log: server.log → server.prev.log
  5. Spawn server with stdout/stderr → server.log
  6. Write PID to server.pid
  7. Health check: curl http://localhost:3000/health
```

**Why kill first?**
- We own the machine. We decide what runs.
- If port 3000 is occupied, something is stale or wrong.
- No "Port already in use" errors. No manual `pkill` dances.
- Just start. It works.

### How to Spawn the Server

**Use the shell. Do NOT use `Bun.spawn` with pipes.**

```typescript
// ✅ CORRECT: nohup + shell redirection. Parent exits immediately.
const cmd = `nohup bun run src/server/index.tsx > "${LOG_FILE}" 2>&1 & echo $!`
const pid = parseInt(execSync(cmd, { shell: "/bin/bash", encoding: "utf-8" }).trim(), 10)
```

```typescript
// ❌ WRONG: Bun.spawn with pipes hangs the parent process.
const child = spawn("bun", ["run", "src/server/index.tsx"], {
  detached: true,
  stdio: ["ignore", "pipe", "pipe"],
})
child.stdout?.on("data", (d) => logFd.write(d))  // This listener keeps the event loop alive
child.unref()  // Does NOT help — the pipe streams hold references
```

**Why `Bun.spawn` with pipes fails for daemons:**
- The `stdout`/`stderr` pipes create event listeners in the parent
- `detached: true` and `unref()` do not close these listeners
- The parent's event loop stays alive until the child exits
- Result: the parent process hangs forever, printing "Command aborted"

**When to use `Bun.spawn`:** Short-lived commands where you capture all output and then exit. When the command finishes, the pipes close and the parent can exit.

**When to use `execSync` with `nohup`:** Long-running background services where the parent must exit immediately.

### Stop Protocol

Use `just srv stop`. It handles PID detection, SIGTERM/SIGKILL, and cleanup automatically.

| Step | Handled by `just srv stop` |
|------|---------------------------|
| PID detection + liveness check | ✅ |
| SIGTERM → wait 5s → SIGKILL | ✅ |
| Stale PID file removal | ✅ |
| PID file cleanup | ✅ |

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

---

## 6. Best Practices

- **Never use `ps | grep` for PID discovery.** Always use the PID file.
- **Always redirect stdout/stderr to log file.** Otherwise output is lost.
- **Rotate logs on restart.** Prevents unbounded log growth.
- **Kill port before start.** Whatever is on port 3000 dies first. No errors.
- **Health check after start.** Verify `/health` responds within 5 seconds.

### The "Start Means Start" Rule

```
❌ Old: "Port already in use" → user must manually pkill
✅ New: just start → kills port → starts server → done

❌ Old: "PID file exists, server already running" → abort
✅ New: just start → kills old PID → starts fresh → done

❌ Old: restart = stop → wait → check → start → may fail
✅ New: restart = kill port → kill PID → start → always works
```

---

## 7. Future Expansion

If additional services are added (e.g. price sync daemon, analysis queue):

1. Add port to registry (3001, 3002, ...)
2. Add PID file: `~/.tradingagents/<service>.pid`
3. Add log file: `~/.tradingagents/<service>.log`
4. Add just verb: `just <service>-start`, `just <service>-stop`
5. Add to `just status` table
