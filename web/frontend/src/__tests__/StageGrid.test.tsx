import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StageGrid } from "../components/StageGrid";
import { useUi } from "../store/ui";

describe("StageGrid", () => {
  it("renders a card per stage", () => {
    render(<StageGrid />);
    for (const name of ["Market", "Sentiment", "News", "Fundamentals", "Research", "Risk", "Trader"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
  });

  it("marks a stage done after analyst_completed", () => {
    useUi.setState({
      eventBuffer: [
        { v: 1, type: "analyst_completed", ts: "t", run_id: 1, data: { stage: "market" }, id: 1 },
      ],
    });
    render(<StageGrid />);
    const card = screen.getByTestId("stage-market");
    expect(card.getAttribute("data-status")).toBe("done");
  });
});
