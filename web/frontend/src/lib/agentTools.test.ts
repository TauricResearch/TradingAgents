/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, it, expect, vi, afterEach } from "vitest";
import {
  fetchTools,
  executeTool,
  clearToolCache,
  type ToolDefinition,
} from "./agentTools";

afterEach(() => {
  vi.restoreAllMocks();
  clearToolCache();
});

function mockFetchRoutes(routes: Record<string, { status: number; body: unknown }>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((url: string | URL | Request) => {
    const path = typeof url === "string" ? url : url.toString();
    for (const [pattern, response] of Object.entries(routes)) {
      if (path.includes(pattern)) {
        return Promise.resolve(
          new Response(JSON.stringify(response.body), {
            status: response.status,
            headers: { "Content-Type": "application/json" },
          })
        );
      }
    }
    return Promise.resolve(new Response("Not Found", { status: 404 }));
  });
}

const sampleTools: ToolDefinition[] = [
  {
    name: "get_watchlist",
    description: "Get the watchlist",
    method: "GET",
    path: "/api/watchlist",
    parameters: {},
  },
  {
    name: "add_to_watchlist",
    description: "Add a ticker to the watchlist",
    method: "POST",
    path: "/api/watchlist",
    parameters: {
      ticker: { type: "string", description: "Ticker symbol" },
      company_name: { type: "string", description: "Company name" },
      exchange: { type: "string", description: "Exchange" },
    },
  },
];

describe("fetchTools", () => {
  it("fetches tools from /api/chat/tools", async () => {
    mockFetchRoutes({ "api/chat/tools": { status: 200, body: { tools: sampleTools } } });
    const tools = await fetchTools();
    expect(tools).toEqual(sampleTools);
    expect((globalThis.fetch as any).mock.calls[0][0]).toBe("/api/chat/tools");
  });

  it("caches results after first call", async () => {
    const spy = mockFetchRoutes({ "api/chat/tools": { status: 200, body: { tools: sampleTools } } });
    await fetchTools();
    await fetchTools();
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("throws on non-OK response", async () => {
    mockFetchRoutes({ "api/chat/tools": { status: 500, body: { detail: "Internal Server Error" } } });
    await expect(fetchTools()).rejects.toThrow("Failed to fetch tools");
  });

  it("returns null cached tools after clearToolCache", async () => {
    const spy = mockFetchRoutes({ "api/chat/tools": { status: 200, body: { tools: sampleTools } } });
    await fetchTools();
    clearToolCache();
    await fetchTools();
    expect(spy).toHaveBeenCalledTimes(2);
  });
});

describe("executeTool", () => {
  it("returns error for unknown tool", async () => {
    mockFetchRoutes({ "api/chat/tools": { status: 200, body: { tools: sampleTools } } });
    const result = await executeTool("nonexistent_tool", {});
    expect(result.success).toBe(false);
    expect(result.error).toBe("Tool not found: nonexistent_tool");
  });

  it("executes GET tool via proxy", async () => {
    mockFetchRoutes({
      "api/chat/tools": { status: 200, body: { tools: sampleTools } },
      "api/chat/proxy": { status: 200, body: { watchlist: [] } },
    });
    const result = await executeTool("get_watchlist", { ticker: "AAPL" });
    expect(result.success).toBe(true);
    expect(result.data).toEqual({ watchlist: [] });
    const call = (globalThis.fetch as any).mock.calls[1];
    expect(call[0]).toBe("/api/chat/proxy");
    const body = JSON.parse(call[1].body);
    expect(body).toEqual({
      method: "GET",
      path: "/api/watchlist",
      params: { ticker: "AAPL" },
      body: undefined,
    });
  });

  it("executes POST tool via proxy", async () => {
    mockFetchRoutes({
      "api/chat/tools": { status: 200, body: { tools: sampleTools } },
      "api/chat/proxy": { status: 201, body: { status: "ok" } },
    });
    const params = { ticker: "AAPL", company_name: "Apple", exchange: "NASDAQ" };
    const result = await executeTool("add_to_watchlist", params);
    expect(result.success).toBe(true);
    const call = (globalThis.fetch as any).mock.calls[1];
    const body = JSON.parse(call[1].body);
    expect(body).toEqual({
      method: "POST",
      path: "/api/watchlist",
      params: undefined,
      body: params,
    });
  });

  it("returns error on proxy failure", async () => {
    mockFetchRoutes({
      "api/chat/tools": { status: 200, body: { tools: sampleTools } },
      "api/chat/proxy": { status: 400, body: { detail: "Bad Request" } },
    });
    const result = await executeTool("get_watchlist", {});
    expect(result.success).toBe(false);
    expect(result.error).toContain("Request failed");
  });

  it("returns error on network exception", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((url: string | URL | Request) => {
      const path = typeof url === "string" ? url : url.toString();
      if (path.includes("api/chat/tools")) {
        return Promise.resolve(
          new Response(JSON.stringify({ tools: sampleTools }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        );
      }
      return Promise.reject(new Error("Network error"));
    });
    const result = await executeTool("get_watchlist", {});
    expect(result.success).toBe(false);
    expect(result.error).toBe("Network error");
  });
});
