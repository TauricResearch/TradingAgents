import { afterEach, describe, expect, it } from "vitest";

import {
  loadPaneFactors,
  savePaneFactors,
} from "@/components/charts/paneLayout";

afterEach(() => localStorage.clear());

describe("pane factor persistence", () => {
  it("round-trips factors keyed by pane count", () => {
    savePaneFactors(3, [3, 0.8, 1]);
    expect(loadPaneFactors(3)).toEqual([3, 0.8, 1]);
    expect(loadPaneFactors(4)).toBeNull(); // different layout shape
  });

  it("rejects malformed saves and loads", () => {
    savePaneFactors(3, [3, 0.8]); // wrong length
    expect(loadPaneFactors(3)).toBeNull();
    savePaneFactors(2, [3, 0]); // non-positive factor
    expect(loadPaneFactors(2)).toBeNull();
    localStorage.setItem("pro-pane-factors", "{not json");
    expect(loadPaneFactors(2)).toBeNull();
  });
});
