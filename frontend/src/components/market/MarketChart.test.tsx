import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { MarketBarDTO, MarketEventDTO } from "../../api/contracts";

const mockClient = vi.hoisted(() => ({
  getMarketView: vi.fn(),
  getMarketEventLayer2: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  getMarketView: mockClient.getMarketView,
  getMarketEventLayer2: mockClient.getMarketEventLayer2,
}));

import {
  CanvasSpatialIndex,
  MarketChart,
  deriveAttribution,
  eventRadius,
  nearestBarForEvent,
  nearestIndexForX,
  rangeForIndex,
} from "./MarketChart";

const bars: MarketBarDTO[] = [
  { timestamp: "2026-07-21", open: 10, high: 12, low: 9, close: 11, artifact_id: "data:a" },
  { timestamp: "2026-07-22", open: 11, high: 13, low: 10, close: 12, artifact_id: "data:a" },
];

const events: MarketEventDTO[] = [
  { timestamp: "2026-07-21", title: "positive", sentiment: "bullish", artifact_id: "data:b" },
  { timestamp: "2026-07-22", title: "negative", sentiment: "bearish", artifact_id: "data:b" },
  { timestamp: "2026-07-22", title: "unknown", artifact_id: "data:b" },
];

describe("MarketChart spatial/index helpers", () => {
  const canvasContext = {
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    fillRect: vi.fn(),
    setLineDash: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    fillText: vi.fn(),
    measureText: vi.fn(() => ({ width: 40 })),
  } as unknown as CanvasRenderingContext2D;
  let getContext: { mockRestore: () => void };

  beforeAll(() => {
    getContext = vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(canvasContext);
  });

  afterAll(() => getContext.mockRestore());

  beforeEach(() => {
    mockClient.getMarketView.mockReset();
    mockClient.getMarketEventLayer2.mockReset();
  });
  it("uses a sorted-x nearest lookup without scanning all candles", () => {
    const xs = [50, 220, 390, 560];

    expect(nearestIndexForX(xs, 10)).toBe(0);
    expect(nearestIndexForX(xs, 289)).toBe(1);
    expect(nearestIndexForX(xs, 480)).toBe(3);
    expect(nearestIndexForX([], 10)).toBeNull();
  });

  it("uses a fixed-cell spatial index for canvas hit targets", () => {
    const index = new CanvasSpatialIndex<string>(20);
    index.insert({ x0: 0, y0: 0, x1: 9, y1: 9, value: "first" });
    index.insert({ x0: 45, y0: 45, x1: 55, y1: 55, value: "second" });

    expect(index.queryPoint(5, 5)).toEqual(["first"]);
    expect(index.queryPoint(50, 50)).toEqual(["second"]);
    expect(index.queryPoint(25, 25)).toEqual([]);
  });

  it("attributes only captured event sentiment in the selected local range", () => {
    expect(deriveAttribution(events, bars)).toEqual({
      bar_count: 2,
      event_count: 3,
      bullish_count: 1,
      bearish_count: 1,
      neutral_count: 1,
    });
  });

  it("encodes the nearest bar's return magnitude as the event particle radius", () => {
    const flatBar: MarketBarDTO = { timestamp: "2026-07-21", open: 10, high: 10, low: 10, close: 10, artifact_id: "data:a" };
    const moveBar: MarketBarDTO = { timestamp: "2026-07-21", open: 10, high: 11, low: 9, close: 11, artifact_id: "data:a" };
    const limitBar: MarketBarDTO = { timestamp: "2026-07-21", open: 10, high: 12, low: 9, close: 12, artifact_id: "data:a" };

    // No bar to anchor on -> baseline; a flat day also stays at baseline.
    expect(eventRadius(null)).toBe(4);
    expect(eventRadius(flatBar)).toBe(4);
    // A 10% move reaches the maximum radius; larger moves clamp there.
    expect(eventRadius(moveBar)).toBeCloseTo(10, 5);
    expect(eventRadius(limitBar)).toBeCloseTo(10, 5);
  });

  it("picks the closest bar by timestamp for an event", () => {
    const event: MarketEventDTO = { timestamp: "2026-07-22", title: "e", artifact_id: "data:b" };
    expect(nearestBarForEvent(event, bars)?.timestamp).toBe("2026-07-22");
    expect(nearestBarForEvent(event, [])).toBeNull();
  });

  it("turns a brush drag into a local inclusive range and resets a click", () => {
    expect(rangeForIndex(5, 2)).toEqual([2, 5]);
    expect(rangeForIndex(2, 5)).toEqual([2, 5]);
    expect(rangeForIndex(3, 3)).toBeNull();
  });

  it("only checks the local Layer 2 cache after a persisted event marker is clicked", async () => {
    mockClient.getMarketView.mockResolvedValue({
      bars,
      events: [events[0]],
      coverage: {
        bar_source_artifact_ids: ["data:a"],
        event_source_artifact_ids: ["data:b"],
        skipped_artifact_count: 0,
        as_of_sequence: 2,
      },
    });
    mockClient.getMarketEventLayer2.mockResolvedValue({
      status: "cached",
      event: {
        artifact_id: "data:b",
        timestamp: "2026-07-21",
        title: "positive",
      },
      trigger: { reasons: ["evidence_thin"], cache_key: "a".repeat(64) },
      cache_configured: true,
      conclusion: {
        conclusion: "Read the official announcement.",
        evidence_gaps: ["filing"],
        material_risks: [],
        source_ids: ["data:b"],
      },
    });
    render(<MarketChart run_id="run_20260723T000000000000Z_1234abcd" latest_sequence={2} artifact_count={1} />);

    await waitFor(() => expect(mockClient.getMarketView).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("img", { name: "已捕获 2 根K线和 1 条事件；拖动底部区间条筛选本地归因" })).toBeInTheDocument();
    expect(mockClient.getMarketEventLayer2).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "读取 positive 的已缓存深度审阅" }));

    await waitFor(() => {
      expect(mockClient.getMarketEventLayer2).toHaveBeenCalledWith(
        "run_20260723T000000000000Z_1234abcd",
        events[0],
      );
    });
    expect(await screen.findByText("Read the official announcement.")).toBeInTheDocument();
    expect(screen.getByText("证据缺口：")).toBeInTheDocument();
  });

  it("states an honest cache-miss degradation instead of inventing a deep result", async () => {
    mockClient.getMarketView.mockResolvedValue({
      bars,
      events: [events[0]],
      coverage: {
        bar_source_artifact_ids: ["data:a"],
        event_source_artifact_ids: ["data:b"],
        skipped_artifact_count: 0,
        as_of_sequence: 2,
      },
    });
    mockClient.getMarketEventLayer2.mockResolvedValue({
      status: "not_available",
      event: {
        artifact_id: "data:b",
        timestamp: "2026-07-21",
        title: "positive",
      },
      trigger: { reasons: ["evidence_thin"], cache_key: "b".repeat(64) },
      cache_configured: true,
    });
    render(<MarketChart run_id="run_20260723T000000000000Z_1234abcd" latest_sequence={2} artifact_count={1} />);

    await screen.findByRole("button", { name: "读取 positive 的已缓存深度审阅" });
    fireEvent.click(screen.getByRole("button", { name: "读取 positive 的已缓存深度审阅" }));

    expect(
      await screen.findByText("当前事件没有可用的 Layer 2 缓存；不会为界面发起供应商或深度模型请求。"),
    ).toBeInTheDocument();
  });
});
