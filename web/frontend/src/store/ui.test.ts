import { describe, it, expect, beforeEach } from "vitest";
import { useUiStore } from "./ui";

describe("ui store: backgroundRunsOpen", () => {
  beforeEach(() => {
    useUiStore.setState({ backgroundRunsOpen: false });
  });

  it("defaults to false", () => {
    expect(useUiStore.getState().backgroundRunsOpen).toBe(false);
  });

  it("setBackgroundRunsOpen toggles the flag", () => {
    useUiStore.getState().setBackgroundRunsOpen(true);
    expect(useUiStore.getState().backgroundRunsOpen).toBe(true);
    useUiStore.getState().setBackgroundRunsOpen(false);
    expect(useUiStore.getState().backgroundRunsOpen).toBe(false);
  });
});
