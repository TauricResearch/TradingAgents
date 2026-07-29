import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ArtifactRecord, ReducerState, RunMeta, Turn } from "../../state/model";
import { RunDisclosure } from "./RunDisclosure";

const mockClient = vi.hoisted(() => ({ readArtifactText: vi.fn() }));
vi.mock("../../api/client", () => ({ readArtifactText: mockClient.readArtifactText }));

function meta(): RunMeta {
  return {
    run_id: "disclosure-run", status: "completed", ticker: "TSLA", asset_type: "stock",
    analysis_date: "2026-07-28", selected_analysts: ["market", "news"], research_depth: 3,
    max_debate_rounds: 2, max_risk_discuss_rounds: 1, output_language: "zh",
    llm_provider: "openai", quick_think_llm: "gpt-quick", deep_think_llm: "gpt-deep",
    configured_keys: {}, checkpoint_enabled: true, created_at: "2026-07-28T00:00:00Z",
    updated_at: "2026-07-28T00:10:00Z", latest_sequence: 20,
    redaction_manifest: [], event_schema_version: 1,
  };
}
function artifact(id: string, kind: string, sequence: number): ArtifactRecord {
  return { artifact_id: id, kind, media_type: "text/markdown", content_sha256: `sha-${id}`,
    byte_size: 100 + sequence, locator: `runs/disclosure-run/${id}`, written_sequence: sequence,
    input_capture_kinds: [], turn_id: "turn-report" };
}
function buildState(): ReducerState {
  const reportTurn: Turn = {
    turn_id: "turn-report", role_instance_id: "disclosure-run:analyst.market", actor_id: "analyst.market",
    turn_index: 1, status: "completed", artifact_id: "report-artifact", model_call_ids: [],
    tool_call_ids: [], vendor_call_ids: [],
  };
  const artifacts = [artifact("report-artifact", "response", 1), artifact("audit-artifact", "state_snapshot", 2)];
  return {
    meta: meta(), roles: {}, turns: { "turn-report": reportTurn }, model_calls: {}, tool_calls: {},
    vendor_calls: {}, artifacts: Object.fromEntries(artifacts.map((a) => [a.artifact_id, a])),
    reports: [{ turn_id: "turn-report", report_kind: "market_report", revision: 1, artifact_id: "report-artifact" }],
    graph_tasks: {}, latest_graph_step: 1,
  };
}

describe("RunDisclosure", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockClient.readArtifactText.mockResolvedValue("## Published body\nResearch prose.");
  });

  it("keeps run detail and report bodies lazy while exposing the complete artifact index", async () => {
    const { container } = render(<RunDisclosure state={buildState()} />);
    const root = container.querySelector("details.run-disclosure") as HTMLDetailsElement;
    expect(root.open).toBe(false);
    expect(screen.getByText("1 份已发布报告 · 2 个 artifacts")).toBeInTheDocument();
    expect(mockClient.readArtifactText).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText("运行输入与产物"));
    expect(root.open).toBe(true);
    expect(screen.getByRole("heading", { name: "本次输入" })).toBeInTheDocument();
    expect(screen.getByText("TSLA")).toBeInTheDocument();
    expect(screen.getByText(/仅列出通过 report\.updated 发布的报告/)).toBeInTheDocument();
    expect(screen.getByText(/未出现的角色不表示没有执行/)).toBeInTheDocument();
    expect(screen.queryByText(/13 份/)).not.toBeInTheDocument();

    const index = screen.getByRole("heading", { name: "完整 Artifact 索引" }).closest("section")!;
    expect(within(index).getByText("report-artifact")).toBeInTheDocument();
    expect(within(index).getByText("audit-artifact")).toBeInTheDocument();
    expect(within(index).getByText("sha-report-artifact")).toBeInTheDocument();
    expect(mockClient.readArtifactText).not.toHaveBeenCalled();

    const reportSummary = screen.getByText("市场分析师").closest("summary")!;
    fireEvent.click(reportSummary);
    expect(await screen.findByText("Research prose.")).toBeInTheDocument();
    expect(mockClient.readArtifactText).toHaveBeenCalledTimes(1);
    expect(mockClient.readArtifactText).toHaveBeenCalledWith("disclosure-run", "report-artifact");
    expect(container.querySelector(".run-report .prose")).not.toBeNull();
  });
});
