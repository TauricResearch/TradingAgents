import { describe, expect, it } from "vitest";
import { guardDebateAttribution } from "./debateAttribution";

function appendAtOffset(current: string, marker: string, offset: number): string {
  if (current.length > offset) throw new Error(`offset ${offset} already passed`);
  return `${current}${"x".repeat(offset - current.length)}${marker}`;
}

describe("guardDebateAttribution", () => {
  it("marks the real historical pollution pattern and shows only the bull span", () => {
    let polluted = "Historical bull payload. ";
    polluted = appendAtOffset(polluted, "**Moderator:**", 118);
    polluted += " introduces the panel. ";
    polluted = appendAtOffset(polluted, "**Bear Analyst:**", 252);
    polluted += " fabricated bearish case. ";
    polluted = appendAtOffset(polluted, "**Bull Analyst:**", 1282);
    polluted += " the actual bull case starts here.";

    expect(polluted.indexOf("**Moderator:**")).toBe(118);
    expect(polluted.indexOf("**Bear Analyst:**")).toBe(252);
    expect(polluted.indexOf("**Bull Analyst:**")).toBe(1282);

    const result = guardDebateAttribution("researcher.bull", polluted);
    expect(result.hasForeignAttribution).toBe(true);
    expect(result.foreignLabels).toEqual(["Moderator", "Bear Analyst"]);
    expect(result.text).toBe("the actual bull case starts here.");
    expect(result.text).not.toContain("fabricated bearish case");
  });

  it("does not mark a clean post-3A turn", () => {
    const clean = "## Investment case\n\nDemand and margins support the thesis.";
    expect(guardDebateAttribution("researcher.bull", clean)).toEqual({
      text: clean,
      hasForeignAttribution: false,
      foreignLabels: [],
    });
  });

  it("suppresses a redundant leading self label", () => {
    expect(
      guardDebateAttribution(
        "researcher.bear",
        "**Bear Analyst:** The downside case.",
      ),
    ).toEqual({
      text: "The downside case.",
      hasForeignAttribution: false,
      foreignLabels: [],
    });
  });

  it("withholds a mixed body when no self-labelled span can be isolated", () => {
    const result = guardDebateAttribution(
      "researcher.bull",
      "**Moderator:** Begin. **Bear Analyst:** downside.",
    );
    expect(result.hasForeignAttribution).toBe(true);
    expect(result.text).toBeNull();
  });
});
