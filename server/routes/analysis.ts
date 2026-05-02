import { Hono } from "hono";
import { streamSSE } from "hono/streaming";

export const analysisRouter = new Hono();

/**
 * POST /api/analyze — trigger analysis, stream progress via SSE
 *
 * Body: { ticker, date?, analysts?, llm_provider?, debates? }
 *
 * SSE events:
 *   agent_start, tool_call, report, decision, complete, error
 */
analysisRouter.post("/", async (c) => {
  const body = await c.req.json();
  const {
    ticker,
    date = "today",
    analysts = ["market", "news", "fundamentals"],
    debates = 1,
  } = body;

  if (!ticker) {
    return c.json({ error: "ticker is required" }, 400);
  }

  return streamSSE(c, async (stream) => {
    await stream.writeSSE({
      event: "start",
      data: JSON.stringify({ ticker, date }),
    });

    // TODO: spawn Python subprocess: scripts/analyze.py
    // For now, simulate events
    const agents = [
      "Market Analyst",
      "News Analyst",
      "Fundamentals Analyst",
    ];

    for (const agent of analysts) {
      await stream.writeSSE({
        event: "agent_start",
        data: JSON.stringify({ agent }),
      });
      // Simulate work delay
      await new Promise((r) => setTimeout(r, 500));
      await stream.writeSSE({
        event: "agent_complete",
        data: JSON.stringify({ agent }),
      });
    }

    await stream.writeSSE({
      event: "decision",
      data: JSON.stringify({
        signal: "Hold",
        reasoning: "Placeholder — full Python integration coming next.",
      }),
    });

    await stream.writeSSE({
      event: "complete",
      data: JSON.stringify({ ticker }),
    });
  });
});
