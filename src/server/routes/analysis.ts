import { spawn } from "node:child_process"
import { existsSync } from "node:fs"
import { join } from "node:path"
import { DatabaseFactory } from "@lib/db"
import type { Context } from "hono"
import { Hono } from "hono"
import { streamSSE } from "hono/streaming"
import { sanitizeForDb } from "../lib/sanitize.ts"
import { projectRoot, venvPython } from "../lib/subprocess.ts"

// Type helper to get request logger from context
function getRequestLogger(c: Context) {
  return (
    c.get("requestLogger") ?? (console as unknown as { error: (msg: string, err: unknown) => void })
  )
}

export const analysisRouter = new Hono()

/**
 * POST /api/analyze — trigger analysis, stream progress via SSE
 *
 * Body: { ticker, date?, analysts?, llm_provider?, debates? }
 *
 * SSE events: start, agent_report, debate_round, risk_assessment,
 *             decision, complete, error
 *
 * After completion, the full analysis state (all agent reports, debate rounds,
 * risk assessment, final decision) is saved to the analyses table as JSON
 * in the raw_state column.
 */
analysisRouter.post("/", async (c) => {
  const body = await c.req.json()
  const { ticker, analysts, debates, date } = body

  if (!ticker) return c.json({ error: "ticker is required" }, 400)

  const analystsStr = typeof analysts === "string" ? analysts : "market,news,fundamentals"
  const debatesNum = Math.min(Math.max(1, Number(debates) || 1), 5)
  const dateStr = typeof date === "string" && date ? date : new Date().toISOString().slice(0, 10)
  const config = JSON.stringify({ analysts: analystsStr, debates: debatesNum, date: dateStr })

  // ── Pre-create analyses record ──────────────────────────────────────
  let analysisId: number | null = null
  try {
    const db = DatabaseFactory.get()
    const result = db
      .prepare(
        "INSERT INTO analyses (ticker, date, config, decision, platform) VALUES (?, ?, ?, ?, ?)",
      )
      .run(ticker, dateStr, config, null, "unknown")
    analysisId = result.lastInsertRowid as number
  } catch (err) {
    const reqLogger = getRequestLogger(c)
    reqLogger.error({ err }, "Failed to create analyses record")
    // Proceed without analysis ID — stream still works, just no DB state
  }

  // ── Event collector ─────────────────────────────────────────────────
  // Collect all events so we can save the full state after stream ends
  const events: Array<{ event: string; data: unknown }> = []

  const python = venvPython()
  const root = projectRoot()
  const script = join(root, "scripts", "analyze_stream.py")

  if (!existsSync(script)) {
    return c.json(
      {
        error: `analyze_stream.py not found at ${script}`,
        hint: "Ensure tradingagents is installed and the scripts directory exists",
      },
      500,
    )
  }

  // Position context from DB
  let positionContext: string | null = null
  try {
    const db = DatabaseFactory.get()
    const row = db
      .query("SELECT * FROM positions WHERE ticker = ? AND status = 'open' LIMIT 1")
      .get(ticker) as Record<string, unknown> | undefined
    if (row) {
      const qty = row.quantity as number
      const cost = row.avg_cost as number
      const thesis = (row.thesis as string) || null
      positionContext = `${qty} shares @ ${cost}`
      if (thesis) positionContext += ` — thesis: ${thesis}`
    }
  } catch {
    // DB not ready
  }

  return streamSSE(c, async (stream) => {
    // Build args with timeout and heartbeat defaults
    const buildArgs = (retry: boolean) => {
      const a = [
        script,
        ticker,
        "--date",
        dateStr,
        "--analysts",
        analystsStr,
        "--debates",
        String(debatesNum),
        "--timeout",
        "240",
        "--heartbeat-interval",
        "15",
      ]
      if (positionContext) a.push("--position-context", positionContext)
      if (retry) a.push("--retry")
      return a
    }

    let stderr = ""
    const MAX_STDERR = 8192
    let buf = ""
    let retries = 0
    const MAX_RETRIES = 1

    const abortController = new AbortController()

    const abortHandler = () => abortController.abort()
    if (stream.onAbort) stream.onAbort(abortHandler)
    c.req.raw.signal.addEventListener("abort", abortHandler, { once: true })

    // ── Persist full analysis state to DB ──────────────────────────────
    function persistState() {
      if (analysisId === null) return
      try {
        const db = DatabaseFactory.get()
        const decisionEvent = events.find((e) => e.event === "decision")
        const decisionText = decisionEvent
          ? `${(decisionEvent.data as Record<string, unknown>).signal ?? "hold"} — ${sanitizeForDb((decisionEvent.data as Record<string, unknown>).reasoning as string) ?? ""}`
          : null
        db.prepare("UPDATE analyses SET raw_state = ?, decision = ? WHERE id = ?").run(
          JSON.stringify(events),
          decisionText,
          analysisId,
        )
      } catch (err) {
        const reqLogger = getRequestLogger(c)
        reqLogger.error({ err }, "Failed to persist analysis state")
      }
    }

    // ── Main run loop with retry support ────────────────────────────────
    await new Promise<void>((resolve) => {
      let child: ReturnType<typeof spawn> | null = null
      let timedOut = false
      let finished = false

      const finish = () => {
        if (finished) return
        finished = true
        clearTimeout(jsTimeout)
        resolve()
      }

      function runChild(retry: boolean) {
        if (abortController.signal.aborted || timedOut) {
          finish()
          return
        }

        const args = buildArgs(retry)
        child = spawn(python, args, {
          cwd: root,
          env: { ...process.env, PYTHONUNBUFFERED: "1" },
          // Bun spawn doesn't directly support AbortSignal.timeout, so we
          // set a JS timeout that kills the process if Python's signal.alarm
          // doesn't fire (defence-in-depth).
          signal: abortController.signal,
        })

        if (!child.stdout) return
        child.stdout.on("data", (chunk: Buffer) => {
          buf += chunk.toString()
          const idx = buf.lastIndexOf("\n")
          if (idx === -1) return
          const complete = buf.slice(0, idx)
          buf = buf.slice(idx + 1)

          for (const line of complete.split("\n").filter(Boolean)) {
            try {
              const parsed = JSON.parse(line)
              if (parsed.event && parsed.data !== undefined) {
                events.push({ event: parsed.event, data: parsed.data })
                if (parsed.event === "decision") {
                  const d = parsed.data as Record<string, unknown>
                  try {
                    const db = DatabaseFactory.get()
                    db.prepare(
                      "INSERT INTO signals (ticker, date, signal, reasoning, confidence) VALUES (?, ?, ?, ?, ?)",
                    ).run(
                      ticker,
                      dateStr,
                      (d.signal as string) ?? "hold",
                      sanitizeForDb(d.reasoning as string) ?? null,
                      (d.confidence as string) ?? null,
                    )
                  } catch {
                    /* DB write failure shouldn't break the stream */
                  }
                }
                stream
                  .writeSSE({ event: parsed.event, data: JSON.stringify(parsed.data) })
                  .catch(() => {})
              }
            } catch {
              // Skip non-JSON output
            }
          }
        })

        if (!child.stderr) return
        child.stderr.on("data", (chunk: Buffer) => {
          const text = chunk.toString()
          stderr += text
          if (stderr.length > MAX_STDERR) stderr = stderr.slice(-MAX_STDERR)
          // Forward heartbeat events from stderr as SSE
          const lines = text.split("\n").filter(Boolean)
          for (const line of lines) {
            if (!line.trim().startsWith("{")) continue
            try {
              const parsed = JSON.parse(line.trim())
              if (parsed.event === "heartbeat") {
                stream
                  .writeSSE({ event: "heartbeat", data: JSON.stringify(parsed.data) })
                  .catch(() => {})
              }
            } catch {
              // Non-JSON stderr — accumulate in stderr buffer for error reporting
            }
          }
        })

        child.on("close", (code) => {
          if (abortController.signal.aborted || timedOut) {
            finish()
            return
          }

          // Flush remaining stdout buffer
          const remaining = buf.trim()
          if (remaining) {
            try {
              const parsed = JSON.parse(remaining)
              if (parsed.event && parsed.data !== undefined) {
                events.push({ event: parsed.event, data: parsed.data })
                stream
                  .writeSSE({ event: parsed.event, data: JSON.stringify(parsed.data) })
                  .catch(() => {})
              }
            } catch {
              /* not valid JSON */
            }
          }

          if (code === 0 || code === null) {
            persistState()
            finish()
            return
          }

          // Non-zero exit — retry once if we haven't already
          if (retry || retries >= MAX_RETRIES) {
            persistState()
            stream
              .writeSSE({
                event: "error",
                data: JSON.stringify({
                  error: `Analysis failed (exit code ${code})`,
                  detail: stderr.slice(-2000) || undefined,
                  hint:
                    retries > 0
                      ? "Retry attempted but failed"
                      : "Exit plan analysis or fix pipeline",
                }),
              })
              .catch(() => {})
            finish()
            return
          }

          retries++
          stderr = ""
          buf = ""
          // Re-spawn with --retry flag
          runChild(true)
        })

        child.on("error", (err) => {
          persistState()
          stream
            .writeSSE({
              event: "error",
              data: JSON.stringify({ error: "Python process error", detail: err.message }),
            })
            .catch(() => {})
          finish()
        })
      }

      // JS-level timeout as defence-in-depth (Python signal.alarm is the primary)
      const jsTimeout = setTimeout(() => {
        timedOut = true
        if (child) child.kill("SIGTERM")
        persistState()
        stream
          .writeSSE({
            event: "error",
            data: JSON.stringify({
              error: "Analysis timed out",
              detail: "Python signal.alarm did not fire within 240s",
              hint: "Check for deadlocks or infinite loops in the Python pipeline",
            }),
          })
          .catch(() => {})
        finish()
      }, 250_000) // 250s — slightly more than Python's 240s timeout

      runChild(false)

      abortController.signal.addEventListener(
        "abort",
        () => {
          clearTimeout(jsTimeout)
          if (child) child.kill("SIGTERM")
          finish()
        },
        { once: true },
      )
    })
  })
})
