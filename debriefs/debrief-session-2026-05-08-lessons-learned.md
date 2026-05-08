# Debrief: Server Lifecycle — How We Got Hung Up

**Date:** 2026-05-08
**Topic:** `scripts/server-lifecycle.ts` rewrite
**Status:** Resolved

---

## The Symptom

`just start` and `just restart` would:
1. Print "Server started (PID xxx)"
2. Then hang or print "Command aborted"
3. The shell prompt would not return
4. We'd try to fix it, test again, same result
5. Loop for 20+ minutes

## Root Cause: Bun.spawn with Pipes

The original script used `Bun.spawn` with `stdio: ["ignore", "pipe", "pipe"]` and event listeners:

```typescript
const child = spawn("bun", ["run", "src/server/index.tsx"], {
  detached: true,
  stdio: ["ignore", "pipe", "pipe"],
})

child.stdout?.on("data", (d: Buffer) => logFd.write(d))
child.stderr?.on("data", (d: Buffer) => logFd.write(d))
child.unref()
```

**Why it hung:**
- `detached: true` and `unref()` are Node-isms that don't translate cleanly to Bun's spawn model
- The `stdout`/`stderr` pipes keep the parent process's event loop alive
- Even with `unref()`, the event listeners (`on("data", ...)`) hold references
- The parent can't exit until the streams close — which they never do while the server runs

**The lesson:** Bun.spawn with pipe redirection is for short-lived processes where you read all output and then exit. For daemon-style processes, don't capture streams in the parent.

## The Loop

| Attempt | Fix | Result |
|---------|-----|--------|
| 1 | Add `child.unref()` | Still hung |
| 2 | Make async/await | Still hung |
| 3 | Add timeouts | Still hung |
| 4 | Try `Bun.file().writer()` | Still hung |
| 5 | Use `nohup` shell command | **Fixed** |

**Why we looped:** Each fix addressed a symptom (async, unref, timeouts) without addressing the root cause (pipe streams keeping the event loop alive).

## The Fix

Use the shell. The shell knows how to background processes:

```typescript
const cmd = `nohup bun run src/server/index.tsx > "${LOG_FILE}" 2>&1 & echo $!`
const pid = parseInt(execSync(cmd, { shell: "/bin/bash", encoding: "utf-8" }).trim(), 10)
```

- `nohup` — ignores SIGHUP, keeps running after parent exits
- `> file 2>&1` — redirects stdout and stderr to log file directly, no pipes in parent
- `&` — backgrounds the process
- `echo $!` — prints the PID so we can capture it
- `execSync` — runs the shell command, gets the PID string, exits immediately

**No async. No event listeners. No pipes. Just a shell command.**

## Broader Lesson: When the Tool Fights You, Switch Tools

We tried to make Bun.spawn do something it isn't designed for (daemon management with log capture). Bun.spawn is for:
- Running a command and capturing its output
- Running a command and waiting for it to finish

Bun.spawn is NOT for:
- Backgrounding long-running services with detached log capture
- Process management (PID files, health checks, lifecycle)

The right tool for daemon management is either:
1. **The shell** (`nohup`, `&`, `disown`) — for simple cases
2. **A process manager** (`pm2`, `supervisord`, `systemd`) — for production
3. **Bun's built-in server** (`bun run src/server/index.tsx` directly) — for development

## General Principles

1. **If a function has more than 3 async/await calls, it's probably over-engineered.**
2. **If you're fighting the runtime (Bun, Node, etc.), you're using the wrong API.**
3. **Shell commands exist for a reason.** Use them when the task matches shell semantics (redirect, background, pipeline).
4. **Kill the port first, ask questions later.** For a dev server, port occupancy is a failure mode, not a user error.
5. **"Start means start" is a design principle, not an implementation detail.** The user's intent is "I want the server running." The system should satisfy that intent by any means necessary.

## What We Should Have Done

Instead of iterating on `Bun.spawn` with increasingly complex options:

```bash
# Simple test to verify the hypothesis
bun -e "const c = Bun.spawn(['sleep', '10'], { detached: true, stdio: ['ignore', 'pipe', 'pipe'] }); c.stdout?.on('data', d => console.log(d)); c.unref(); console.log('unref called')"
# Result: hangs. Hypothesis confirmed: pipes keep event loop alive.

# Fix: use nohup instead
nohup sleep 10 > /tmp/test.log 2>&1 & echo $!
# Result: works. Background process, no hang.
```

**15 seconds of experimentation would have saved 20 minutes of looping.**

## The Services Playbook Update

The playbook now documents:
- Kill port first, no "already running" errors
- Use `nohup` + shell redirection for daemon processes
- The "start means start" rule with before/after examples
