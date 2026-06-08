import { describe, it, expect, vi, afterEach } from "vitest";
import {
  startBackgroundRun,
  getBackgroundRuns,
  getBackgroundRun,
  cancelBackgroundRun,
  pauseBackgroundRun,
  resumeBackgroundRun,
  type StartBackgroundRunRequest,
  type BackgroundRunState,
} from "./api";

afterEach(() => vi.restoreAllMocks());

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
    )
  );
}

describe("background-runs api", () => {
  it("startBackgroundRun POSTs and returns job_id", async () => {
    mockFetch(201, { job_id: "bgr_TEST" });
    const body: StartBackgroundRunRequest = {
      ticker: "NVDA", date_from: "2024-01-01", date_to: "2024-01-05",
      every: "1d", parallel: 1,
    };
    const out = await startBackgroundRun(body);
    expect(out.job_id).toBe("bgr_TEST");
    const init = (globalThis.fetch as any).mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual(body);
  });

  it("startBackgroundRun surfaces 422 detail", async () => {
    mockFetch(422, { detail: "parallel must be in [1, 4]" });
    await expect(startBackgroundRun({
      ticker: "NVDA", date_from: "2024-01-01", date_to: "2024-01-05", every: "1d", parallel: 99,
    })).rejects.toThrow(/parallel/);
  });

  it("getBackgroundRuns GETs and returns jobs", async () => {
    mockFetch(200, { jobs: [{ job_id: "bgr_A" }] });
    const out = await getBackgroundRuns();
    expect(out.jobs).toEqual([{ job_id: "bgr_A" }]);
  });

  it("getBackgroundRun GETs by id", async () => {
    mockFetch(200, { job_id: "bgr_A", ticker: "NVDA", status: "running" } as BackgroundRunState);
    const out = await getBackgroundRun("bgr_A");
    expect(out.job_id).toBe("bgr_A");
  });

  it("cancel/pause/resume POST to their sub-paths", async () => {
    mockFetch(200, { status: "ok" });
    await cancelBackgroundRun("bgr_A");
    expect((globalThis.fetch as any).mock.calls[0][0]).toMatch(/\/cancel$/);
    await pauseBackgroundRun("bgr_A");
    expect((globalThis.fetch as any).mock.calls[1][0]).toMatch(/\/pause$/);
    await resumeBackgroundRun("bgr_A");
    expect((globalThis.fetch as any).mock.calls[2][0]).toMatch(/\/resume$/);
  });
});
