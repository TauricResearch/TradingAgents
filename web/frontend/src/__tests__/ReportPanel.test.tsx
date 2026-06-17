import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { ReportPanel } from "../components/ReportPanel";

// ReportPanel depends on hooks that read from Zustand store.
// When no events are available (default store state), it renders nothing.
describe("ReportPanel", () => {
  it("renders nothing when no run has finished", () => {
    const { container } = render(<ReportPanel />);
    expect(container.firstChild).toBeNull();
  });

  it("accepts the component without crashing", () => {
    expect(() => render(<ReportPanel />)).not.toThrow();
  });
});
