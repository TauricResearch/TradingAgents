import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  startRun,
  fetchTickerRuns,
  type LlmCallRow,
  type RunDetail,
} from "../lib/api";

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

describe("startRun", () => {
  it("posts the ticker and force=false when force is not set", async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ run_id: "NVDA:2026-06-04T03:21:57Z" }) });
    const result = await startRun("NVDA");
    expect(result).toEqual({ run_id: "NVDA:2026-06-04T03:21:57Z" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/runs");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ ticker: "NVDA", force: false });
  });

  it("forwards the force flag when set", async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ run_id: "NVDA:2026-06-04T03:21:58Z" }) });
    await startRun("NVDA", true);
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ ticker: "NVDA", force: true });
  });

  it("throws on non-2xx", async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) });
    await expect(startRun("NVDA")).rejects.toThrow(/start/);
  });
});

describe("fetchTickerRuns", () => {
  it("GETs the per-ticker endpoint and returns the array", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => [
        { id: "NVDA:7", slug: "2026-06-04T03-21-57Z", ticker: "NVDA", status: "done", started_at: null, finished_at: null, cancel_requested: false, decision_action: null, decision_target: null, decision_rationale: null, decision_confidence: null },
        { id: "NVDA:5", slug: "2026-06-04T03-20-00Z", ticker: "NVDA", status: "done", started_at: null, finished_at: null, cancel_requested: false, decision_action: null, decision_target: null, decision_rationale: null, decision_confidence: null },
      ],
    });
    const rows = await fetchTickerRuns("NVDA");
    expect(rows).toHaveLength(2);
    expect(rows[0].id).toBe("NVDA:7");
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/tickers/NVDA/runs");
  });

  it("throws on non-2xx", async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 404, json: async () => ({}) });
    await expect(fetchTickerRuns("ZZZZ")).rejects.toThrow(/ticker-runs/);
  });
});

// Type-level sanity checks. These don't assert anything at runtime —
// they just verify the public types compile with the expected fields.
const _llmCallShape: LlmCallRow = {
  id: "1",
  run_id: "NVDA:1",
  ticker: "NVDA",
  node_name: "Market Analyst",
  started_at: null,
  model: "gpt-4o",
  prompt_text: "",
  response_text: "",
  tool_calls: [],
  input_tokens: 0,
  output_tokens: 0,
  total_tokens: 0,
  duration_ms: 0,
};
const _runDetailShape: RunDetail = {
  id: "NVDA:1",
  slug: "2026-06-04T03-21-57Z",
  ticker: "NVDA",
  started_at: null,
  finished_at: null,
  status: "done",
  cancel_requested: false,
  decision_action: null,
  decision_target: null,
  decision_rationale: null,
  decision_confidence: null,
  llm_provider: null,
  deep_think_model: null,
  quick_think_model: null,
  start_price: null,
  start_price_at: null,
  total_duration_s: null,
  elapsed_s: null,
  events: [],
  llm_calls: [_llmCallShape],
  stages: [],
};
void _llmCallShape;
void _runDetailShape;
