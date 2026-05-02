import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { spawn } from "node:child_process";
import { join, dirname } from "node:path";
import { existsSync } from "node:fs";
import { DatabaseFactory } from "../lib/db.ts";

export const analysisRouter = new Hono();

/**
 * Resolve the TradingAgents project root.
 * Order: TA_ROOT env → sibling directory → parent directory
 */
function findProjectRoot(): string {
  // 1. Explicit env var
  if (process.env.TA_ROOT) return process.env.TA_ROOT;

  // 2. Sibling directory (worktree layout: TradingAgents-sse, TradingAgents)
  //    import.meta.dir in server/routes/analysis.ts → go up 2 levels to project root
  const projectRoot = dirname(dirname(import.meta.dir));
  const sibling = join(projectRoot, "..", "TradingAgents");
  if (existsSync(join(sibling, "scripts", "analyze_stream.py"))) {
    return sibling;
  }

  // 3. Current directory (monolith layout)
  if (existsSync(join(projectRoot, "scripts", "analyze_stream.py"))) {
    return projectRoot;
  }

  throw new Error(
    "Cannot find TradingAgents root. Set TA_ROOT env var.",
  );
}

/**
 * POST /api/analyze — trigger analysis, stream progress via SSE
 *
 * Body: { ticker, date?, analysts?, llm_provider?, debates? }
 *
 * SSE events: start, agent_report, debate_round, risk_assessment,
 *             decision, complete, error
 */
analysisRouter.post("/", async (c) => {
  const body = await c.req.json();
  const {
    ticker,
    date = "today",
    analysts = "market,news,fundamentals",
    debates = 1,
  } = body;

  if (!ticker) {
    return c.json({ error: "ticker is required" }, 400);
  }

  const root = findProjectRoot();
  const venvPython = join(root, ".venv", "bin", "python3");
  const script = join(root, "scripts", "analyze_stream.py");

  if (!existsSync(script)) {
    return c.json(
      { error: `analyze_stream.py not found at ${script}` },
      500,
    );
  }

  // Look up position context from portfolio DB
  let positionContext: string | null = null;
  try {
    const db = DatabaseFactory.get();
    const row = db
      .query("SELECT * FROM positions WHERE ticker = ? AND status = 'open' LIMIT 1")
      .get(ticker) as Record<string, unknown> | undefined;
    if (row) {
      const qty = row.quantity as number;
      const cost = row.avg_cost as number;
      const thesis = (row.thesis as string) || null;
      positionContext = `${qty} shares @ ${cost}`;
      if (thesis) positionContext += ` — thesis: ${thesis}`;
    }
  } catch {
    // DB not ready or no positions — proceed without context
  }

  return streamSSE(c, async (stream) => {
    await stream.writeSSE({
      event: "start",
      data: JSON.stringify({ ticker, date }),
    });

    const args = [
      script,
      ticker,
      "--date", date,
      "--analysts", analysts,
      "--debates", String(debates),
    ];
    if (positionContext) {
      args.push("--position-context", positionContext);
    }

    const child = spawn(venvPython, args, {
        cwd: root,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: "1",
        },
      },
    );

    let stderr = "";

    child.stdout.on("data", (chunk: Buffer) => {
      const lines = chunk.toString().split("\n").filter(Boolean);
      for (const line of lines) {
        try {
          const parsed = JSON.parse(line);
          if (parsed.event && parsed.data !== undefined) {
            // Auto-save decision as a signal in the DB
            if (parsed.event === "decision") {
              try {
                const db = DatabaseFactory.get();
                const d = parsed.data;
                db.prepare(
                  "INSERT INTO signals (ticker, date, signal, reasoning, confidence) VALUES (?, ?, ?, ?, ?)",
                ).run(
                  ticker,
                  date === "today" ? new Date().toISOString().slice(0, 10) : date,
                  d.signal ?? "hold",
                  d.reasoning ?? null,
                  d.confidence ?? null,
                );
              } catch { /* DB write failure shouldn't break the stream */ }
            }
            stream.writeSSE({
              event: parsed.event,
              data: JSON.stringify(parsed.data),
            }).catch(() => {});
          }
        } catch {
          // Skip non-JSON output (warnings, etc.)
        }
      }
    });

    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    await new Promise<void>((resolve, reject) => {
      child.on("close", (code) => {
        if (code !== 0) {
          stream.writeSSE({
            event: "error",
            data: JSON.stringify({
              message: `Python process exited with code ${code}`,
              stderr: stderr.slice(-2000),
            }),
          }).catch(() => {});
        }
        resolve();
      });

      child.on("error", (err) => {
        stream.writeSSE({
          event: "error",
          data: JSON.stringify({ message: err.message }),
        }).catch(() => {});
        resolve();
      });
    });
  });
});
